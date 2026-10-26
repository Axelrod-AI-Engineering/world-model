"""`Prefer: respond-async` on the routes that run a job: the 202 comes at once, the job ends in the background, and what it
stores is what the synchronous path stores."""

from __future__ import annotations

import logging
import time

import pytest

import axelrod_wm.api.v1.context as context
import axelrod_wm.api.v1.routes_ingest as ingest
from tests.service.helpers import NOTE, WM, Signer, data, service, upload

ASYNC = {"Prefer": "respond-async"}


@pytest.fixture(scope="module")
def c():
    with service(Signer()) as client:
        yield client


def settle(c, location: str) -> dict:
    """Poll a job's Location until it is no longer running."""
    for _ in range(500):
        job = data(c.get(location))
        if job["status"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("the job did not end")


def reread(c, doc: str, headers: dict | None = None):
    return c.post(f"{WM}/documents/{doc}/bundles", headers=headers or {})


def test_async_answers_at_once_and_ends_with_the_synchronous_result(c):
    doc = upload(c, b"Oct 6, 2026. The central bank held its rate.", "bg.txt")["document_id"]
    sync = data(reread(c, doc), 202)
    r = reread(c, doc, {"Prefer": "return=minimal, respond-async; wait=5"})
    assert r.status_code == 202 and r.headers["preference-applied"] == "respond-async"
    first = r.json()["data"]
    assert first["status"] == "running" and first["result"] is None and first["finished_at"] is None
    assert r.headers["location"] == f"{WM}/jobs/{first['id']}"
    job = settle(c, r.headers["location"])
    assert job["status"] == "succeeded" and job["error"] is None and job["finished_at"]
    assert job["type"] == sync["type"] and job["result"] == sync["result"]


def test_without_the_header_the_work_runs_before_the_answer(c):
    doc = upload(c, b"Oct 7, 2026. Credit spreads rose by 25bp.", "sync.txt")["document_id"]
    r = reread(c, doc, {"Prefer": "return=minimal"})
    assert "preference-applied" not in r.headers
    assert data(r, 202)["status"] == "succeeded"


def test_a_failing_background_job_ends_failed_with_a_problem(c, monkeypatch):
    doc = upload(c, b"Oct 8, 2026. The central bank cut its rate.", "fail.txt")["document_id"]

    def boom(*a, **k):
        raise ValueError("the parser broke")

    monkeypatch.setattr(ingest.Ingestor, "process", boom)
    r = reread(c, doc, ASYNC)
    job = settle(c, r.headers["location"])
    assert job["status"] == "failed" and job["result"] is None and job["finished_at"]
    err = job["error"]
    assert err["code"] == "invalid_request" and err["type"].endswith("/invalid_request") and err["status"] == 422
    assert err["instance"] == f"{WM}/documents/{doc}/bundles" and err["request_id"] == r.headers["x-request-id"]


def test_a_bug_in_a_background_job_is_a_failed_job_not_a_crash(c, monkeypatch, caplog):
    doc = upload(c, b"Oct 9, 2026. The central bank held.", "bug.txt")["document_id"]

    def bug(*a, **k):
        raise RuntimeError("a bug")

    monkeypatch.setattr(ingest.Ingestor, "process", bug)
    with caplog.at_level(logging.ERROR):
        job = settle(c, reread(c, doc, ASYNC).headers["location"])
    assert job["status"] == "failed" and job["error"]["code"] == "internal_error" and job["error"]["status"] == 500
    assert "a bug" in caplog.text
    assert data(c.get(WM)) is not None                      # the app still serves


def test_a_record_that_cannot_be_kept_is_logged_not_raised(c, monkeypatch, caplog):
    doc = upload(c, b"Oct 10, 2026. Oil fell by 2 percent.", "audit.txt")["document_id"]

    def full(*a, **k):
        raise OSError("the audit log is full")

    monkeypatch.setattr(context, "audit", full)
    with caplog.at_level(logging.ERROR):
        r = reread(c, doc, ASYNC)
        for _ in range(500):
            if "could not be recorded" in caplog.text:
                break
            time.sleep(0.02)
    assert r.status_code == 202 and "could not be recorded" in caplog.text


def test_a_job_that_cannot_be_recorded_releases_its_claim(c, monkeypatch):
    note = upload(c, NOTE, "claim.md", source_type="broker_research")

    def down(*a, **k):
        raise OSError("the lake is down")

    monkeypatch.setattr(c.app.state.lake, "put_job", down)
    with pytest.raises(OSError):
        c.post(f"{WM}/changes", json={"bundle_id": note["bundle_id"]})
    assert not c.app.state.proposing


def test_proposals_in_the_background_release_their_claim_and_replay_by_key(c):
    note = upload(c, NOTE, "2026-10-11_note.md", source="Desk", source_type="broker_research")
    h = {**ASYNC, "Idempotency-Key": "bg-propose-1"}
    r = c.post(f"{WM}/changes", json={"bundle_id": note["bundle_id"]}, headers=h)
    assert r.status_code == 202 and r.headers["preference-applied"] == "respond-async"
    job = settle(c, r.headers["location"])
    assert job["status"] == "succeeded" and job["result"]["ids"]
    assert not c.app.state.proposing                         # the claim ended with the work
    again = c.post(f"{WM}/changes", json={"bundle_id": note["bundle_id"]}, headers=h)
    assert again.status_code == 202 and again.json()["data"]["id"] == job["id"]
    assert again.headers["location"] == r.headers["location"]
