"""Async ingest jobs (Oct 26): `POST /v1/ingest?mode=async` answers 202 at once and a worker runs the pipeline; the job is
polled at `GET /v1/jobs/{id}`. A gated pipeline step makes the queued and running states deterministic; no test sleeps."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from axelrod_ingest import service
from axelrod_ingest.lake.embed import HashingEmbedder
from axelrod_ingest.lake.sqlite import SQLiteLake
from axelrod_ingest.lake.store import content_id
from axelrod_ingest.pipeline import Ingestor
from axelrod_ingest.service import create_ingest_app
from tests.conftest import acme_graph

NOW = datetime(2026, 10, 6, 12, tzinfo=UTC)
AUTH = {"Authorization": "Bearer job-token"}
NOTE = b"# Policy watch\n\nThe central bank raised its policy rate by 25bp to 4.25%.\n"
OTHER = b"<html><body><p>Acme Bank's net interest income rose 4% in Q3.</p></body></html>"
WAIT = 10        # seconds a test will wait for a worker before it fails (never reached when it works)


class Stack:
    def __init__(self, tmp_path, **kw):
        self.store = SQLiteLake(tmp_path / "lake")
        self.app = create_ingest_app(self.store, HashingEmbedder(), None, None, "job-token", clock=lambda: NOW,
                                     timer=lambda: 0.0, **kw)
        self.http = TestClient(self.app, base_url="http://ingest")
        self.jobs = self.app.state.jobs

    def post(self, files=(("note.md", NOTE),), query="", headers=None, meta=None, view=None):
        meta = json.dumps(meta or {"tenant": "desk", "source": "Desk"})
        view = view if view is not None else acme_graph().to_json()
        parts = [("files", (name, data)) for name, data in files] + [("world_view", ("view.json", view))]
        return self.http.post(f"/v1/ingest{query}", data={"meta": meta}, files=parts, headers={**AUTH, **(headers or {})})

    def get(self, job_id):
        return self.http.get(f"/v1/jobs/{job_id}", headers=AUTH)

    def finish(self, job_id):
        assert self.jobs.get(job_id).finished.wait(WAIT)
        return self.get(job_id).json()


@pytest.fixture
def stack(tmp_path):
    return Stack(tmp_path)


@pytest.fixture
def gate(monkeypatch):
    """A slow pipeline step: each `ingest_file` signals `started`, then waits for `release` before doing its work."""
    started, release, real = threading.Event(), threading.Event(), Ingestor.ingest_file

    def slow(self, tenant, data, name, graph, **meta):
        started.set()
        assert release.wait(WAIT)
        return real(self, tenant, data, name, graph, **meta)

    monkeypatch.setattr(service.Ingestor, "ingest_file", slow)
    yield started, release
    release.set()


def test_a_job_goes_from_queued_to_running_to_succeeded(stack, gate):
    started, release = gate
    r = stack.post(files=(("note.md", NOTE), ("banks.html", OTHER)), query="?mode=async")
    body = r.json()
    assert r.status_code == 202 and r.headers["location"] == f"/v1/jobs/{body['id']}"
    assert r.headers["preference-applied"] == "respond-async"
    assert body["status"] == "queued"
    assert body["files"] == [{"name": "note.md", "size": len(NOTE), "content_id": content_id(NOTE)},
                             {"name": "banks.html", "size": len(OTHER), "content_id": content_id(OTHER)}]
    assert started.wait(WAIT)
    running = stack.get(body["id"]).json()
    assert running["status"] == "running" and running["started_at"] and running["finished_at"] is None
    assert running["progress"] == {"done": 0, "total": 2, "current": "note.md"} and running["results"] is None
    assert stack.store.list_documents("desk") == []                  # nothing stored until the work gets there
    release.set()
    done = stack.finish(body["id"])
    assert done["status"] == "succeeded" and done["error"] is None and done["finished_at"]
    assert done["progress"] == {"done": 2, "total": 2, "current": None}
    assert {r["document"]["id"] for r in done["results"]} == {content_id(NOTE), content_id(OTHER)}
    times = [r["document"]["event_time"] for r in done["results"]]
    assert times == sorted(times)
    assert {d.id for d in stack.store.list_documents("desk")} == {content_id(NOTE), content_id(OTHER)}


def test_the_prefer_header_asks_for_a_job_and_the_sync_mode_wins_when_named(stack):
    r = stack.post(headers={"Prefer": "wait=5, respond-async; x=1"})
    assert r.status_code == 202
    assert stack.finish(r.json()["id"])["status"] == "succeeded"
    again = stack.post(headers={"Prefer": "respond-async"}, query="?mode=sync")
    assert again.status_code == 200 and again.json()["results"][0]["new"] is False
    assert stack.post(headers={"Prefer": "return=minimal"}).status_code == 200


def test_a_job_that_raises_fails_and_the_next_one_still_runs(stack, monkeypatch):
    real = Ingestor.ingest_file

    def boom(self, tenant, data, name, graph, **meta):
        if name == "bad.md":
            raise RuntimeError("the embedder went away")
        return real(self, tenant, data, name, graph, **meta)

    monkeypatch.setattr(service.Ingestor, "ingest_file", boom)
    first = stack.post(files=(("bad.md", NOTE),), query="?mode=async").json()["id"]
    second = stack.post(files=(("ok.md", OTHER),), query="?mode=async").json()["id"]
    failed = stack.finish(first)
    assert failed["status"] == "failed" and failed["error"] == "RuntimeError: the embedder went away"
    assert failed["results"] is None and failed["finished_at"]
    assert stack.finish(second)["status"] == "succeeded"


def test_a_file_the_pipeline_rejects_is_a_succeeded_job_with_a_failed_document(stack):
    done = stack.finish(stack.post(files=(("broken.pdf", b"not a pdf"),), query="?mode=async").json()["id"])
    assert done["status"] == "succeeded" and done["results"][0]["document"]["status"] == "failed"


def test_an_unknown_job_is_a_404_problem_that_names_the_restart(stack):
    r = stack.get("0" * 32)
    assert r.status_code == 404 and r.headers["content-type"].startswith("application/problem+json")
    assert "restarted" in r.json()["detail"] and "lake" in r.json()["detail"]


def test_only_the_newest_finished_jobs_are_remembered_and_a_live_one_never_is(tmp_path, gate):
    started, release = gate
    stack = Stack(tmp_path, job_history=1)
    one = stack.post(query="?mode=async").json()["id"]
    assert started.wait(WAIT)
    two = stack.post(files=(("banks.html", OTHER),), query="?mode=async").json()["id"]
    assert stack.get(one).status_code == 200 and stack.get(two).status_code == 200      # nothing finished: none evicted
    release.set()
    stack.finish(one)
    stack.finish(two)
    three = stack.post(files=(("note.md", NOTE),), query="?mode=async").json()["id"]
    stack.finish(three)
    assert stack.get(one).status_code == 404 and stack.get(three).status_code == 200
    assert len(stack.jobs._jobs) <= 2


def test_too_many_waiting_jobs_are_refused_with_retry_after(tmp_path, gate):
    started, _release = gate
    stack = Stack(tmp_path, job_backlog=1)
    stack.post(query="?mode=async")
    assert started.wait(WAIT)                                         # the first is running, so the queue is empty
    waiting = stack.post(query="?mode=async")                         # one waiting
    assert waiting.status_code == 202 and stack.get(waiting.json()["id"]).json()["status"] == "queued"
    r = stack.post(query="?mode=async")
    assert r.status_code == 503 and r.headers["retry-after"] == "30" and "waiting" in r.json()["detail"]


def test_a_bad_request_is_refused_at_once_and_makes_no_job(tmp_path):
    stack = Stack(tmp_path, max_bytes=10)
    assert stack.post(files=(("big.md", NOTE),), query="?mode=async").status_code == 413
    ok = Stack(tmp_path / "ok")
    assert ok.post(query="?mode=async", meta={"tenant": "desk", "bogus": 1}).status_code == 422
    assert ok.post(query="?mode=async", meta={"source": "no tenant"}).status_code == 422
    assert ok.post(query="?mode=async", view="not json").status_code == 422
    assert ok.post(query="?mode=later").status_code == 422
    assert ok.http.post("/v1/ingest?mode=async", data={"meta": "{}"}).status_code == 401
    assert ok.http.get("/v1/jobs/abc").status_code == 401
    assert stack.jobs._jobs == {} and ok.jobs._jobs == {}


def test_sync_mode_is_unchanged(stack):
    r = stack.post(files=(("note.md", NOTE), ("banks.html", OTHER)))
    assert r.status_code == 200 and "location" not in r.headers and len(r.json()["results"]) == 2
    assert stack.jobs._jobs == {}
