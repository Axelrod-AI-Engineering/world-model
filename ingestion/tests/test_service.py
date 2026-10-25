"""The ingestion service and its client (Oct 24): a file ingested through the service, backed by a `RemoteLake` on an
in-process data service, gives the same results, bundle ids, and lake digest as the local path; the service is the only
embedder (`/v1/embed`); it keeps no file bytes on disk; and the pipeline's exceptions come back as the same types."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from axelrod_ingest import service
from axelrod_ingest.ingest_client import RemoteEmbedder, RemoteIngestError, RemoteIngestor, ingestor_from_env
from axelrod_ingest.lake.embed import HashingEmbedder
from axelrod_ingest.lake.sqlite import SQLiteLake
from axelrod_ingest.pack import lake_digest
from axelrod_ingest.pipeline import Ingestor, IngestResult
from axelrod_ingest.service import create_ingest_app
from tests.conftest import acme_graph, acme_inverted
from tests.lake.conftest import remote_of

NOW = datetime(2026, 10, 6, 12, tzinfo=UTC)
T = "desk"
NOTE = (b"# Policy watch\n\nThe central bank raised its policy rate by 25bp to 4.25%. Government bonds 10Y yield rose "
        b"10bp, and the dollar index rose 2%.\n\nHigher government bonds 10Y yield lifts Acme Re domestic P&C profit.\n")
OTHER = (b"<html><head><title>Banks</title></head><body><p>Acme Bank's net interest income rose 4% in Q3. "
         b"The central bank policy rate weighs on Acme Bank net interest income.</p></body></html>")
FILES = [(NOTE, "policy_2026-10-05.md"), (OTHER, "banks.html")]
OPTIONS = {"clock": lambda: NOW, "timer": lambda: 0.0}      # no clock or stopwatch left to differ between the two paths


def stack(tmp_path, **kw):
    """The service over a `RemoteLake` on a data service over its own SQLite file; and its client."""
    backing = SQLiteLake(tmp_path / "data")
    app = create_ingest_app(remote_of(backing), HashingEmbedder(), None, None, "ingest-token", **{**OPTIONS, **kw})
    client = RemoteIngestor("http://ingest", "ingest-token", TestClient(app, base_url="http://ingest"))
    client.inverted = acme_inverted()
    return client, backing, app


def local(tmp_path):
    store = SQLiteLake(tmp_path / "local")
    return Ingestor(store, HashingEmbedder(), inverted=acme_inverted(), **OPTIONS), store


def test_the_service_gives_the_local_results_and_the_same_lake(tmp_path):
    remote, backing, _ = stack(tmp_path)
    ing, store = local(tmp_path)
    meta = {"source": "Desk", "source_type": "broker_research", "uploaded_by": "ada"}
    got = remote.ingest_many(T, FILES, acme_graph(), **meta)
    want = ing.ingest_many(T, FILES, acme_graph(), **meta)
    assert [r.to_json() for r in got] == [r.to_json() for r in want]
    assert all(r.bundle is not None and r.signals > 0 for r in got)
    assert got[0].bundle.id == want[0].bundle.id
    assert lake_digest(backing, T) == lake_digest(store, T)
    assert lake_digest(backing, T)["all"] == lake_digest(store, T)["all"]
    again = remote.ingest_file(T, NOTE, "policy_2026-10-05.md", acme_graph(), **meta)
    assert again.new is False and again.bundle.id == want[0].bundle.id


def test_a_stored_document_is_read_again_through_the_service(tmp_path):
    remote, backing, _ = stack(tmp_path)
    ing, store = local(tmp_path)
    first = remote.ingest_file(T, NOTE, "policy.md", acme_graph())
    ing.ingest_file(T, NOTE, "policy.md", acme_graph())
    assert remote.process(T, first.document.id, acme_graph()).to_json() == ing.process(
        T, first.document.id, acme_graph()).to_json()
    with pytest.raises(KeyError, match="nope"):
        remote.process(T, "nope", acme_graph())


def test_dates_and_meta_travel_and_a_failed_file_has_no_bundle(tmp_path):
    remote, _backing, _ = stack(tmp_path)
    pub = datetime(2026, 9, 1, tzinfo=UTC)
    res = remote.ingest_file(T, NOTE, "n.md", acme_graph(), published_at=pub, mime="text/markdown",
                             meta={"hints": {"issuer_country": "US"}})
    assert res.document.published_at == pub and res.document.mime == "text/markdown"
    assert res.document.meta["hints"] == {"issuer_country": "US"}
    bad = remote.ingest_file(T, b"not a pdf", "broken.pdf", acme_graph())
    assert bad.bundle is None and bad.document.status == "failed" and bad.warnings
    assert IngestResult.from_json(bad.to_json()).to_json() == bad.to_json()
    with pytest.raises(ValueError, match="source_type"):
        remote.ingest_file(T, NOTE, "n.md", acme_graph(), source_type="gossip")


def test_the_service_is_the_only_embedder(tmp_path):
    remote, _b, app = stack(tmp_path)
    emb = remote.embedder
    assert isinstance(emb, RemoteEmbedder)
    assert (emb.name, emb.dim) == (HashingEmbedder().name, 256)
    assert emb.embed(["oil prices rose", "the dollar fell"]) == HashingEmbedder().embed(["oil prices rose", "the dollar fell"])
    assert emb.embed([]) == []
    ask = TestClient(app).post("/v1/embed", json={"texts": []}, headers={"Authorization": "Bearer ingest-token"})
    assert ask.json() == {"name": "hashing-256", "dim": 256, "vectors": []}


def test_no_file_is_left_on_disk(tmp_path, monkeypatch):
    spare, scratch = tmp_path / "cwd", tmp_path / "tmp"
    spare.mkdir()
    scratch.mkdir()
    remote, _b, _ = stack(tmp_path)           # the lake's own volume is elsewhere
    monkeypatch.chdir(spare)
    monkeypatch.setenv("TMPDIR", str(scratch))
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    remote.ingest_many(T, FILES, acme_graph())
    assert list(spare.iterdir()) == [] and list(scratch.iterdir()) == []


def test_every_route_but_health_needs_the_token(tmp_path):
    _r, _b, app = stack(tmp_path)
    c = TestClient(app)
    assert c.get("/health").json() == {"ok": True, "service": "ingestion"}
    for path in ("/v1/ingest", "/v1/process", "/v1/embed"):
        r = c.post(path, headers={"Authorization": "Bearer wrong"})
        assert r.status_code == 401 and r.json()["code"] == "authentication_required"
        assert r.headers["content-type"].startswith("application/problem+json")
    r = c.post("/v1/process", json={}, headers={"Authorization": "Bearer ingest-token"})
    assert r.status_code == 422 and r.json()["code"] == "invalid_request"
    assert c.get("/v1/nowhere").json()["code"] == "not_found"
    assert c.get("/v1/ingest", headers={"Authorization": "Bearer ingest-token"}).json()["code"] == "error"
    with pytest.raises(ValueError, match="token"):
        create_ingest_app(SQLiteLake(tmp_path / "x"), HashingEmbedder(), None, None, "")


def test_a_wrong_token_or_a_missing_service_is_an_error(tmp_path):
    _r, _b, app = stack(tmp_path)
    wrong = RemoteIngestor("http://ingest", "nope", TestClient(app, base_url="http://ingest"))
    with pytest.raises(RemoteIngestError, match="401"):
        wrong.ingest_file(T, NOTE, "n.md", acme_graph())

    def refuse(request):
        raise httpx.ConnectError("x")

    down = RemoteIngestor("http://ingest", "t", httpx.Client(transport=httpx.MockTransport(refuse)))
    with pytest.raises(RemoteIngestError, match="ConnectError"):
        down.process(T, "d", acme_graph())
    assert down.ping() is False and wrong.ping() is True
    flaw = RemoteIngestor("http://ingest", "t", httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(502))))
    with pytest.raises(RemoteIngestError, match="502"):
        flaw.process(T, "d", acme_graph())


def test_the_environment_chooses_the_ingestor():
    assert ingestor_from_env({}) is None
    one = ingestor_from_env({"WORLD_MODEL_INGEST_URL": "http://i/", "WORLD_MODEL_INGEST_TOKEN": "t"})
    assert isinstance(one, RemoteIngestor) and one.url == "http://i"
    with pytest.raises(ValueError, match="WORLD_MODEL_INGEST_TOKEN"):
        ingestor_from_env({"WORLD_MODEL_INGEST_URL": "http://i"})


def test_main_serves_the_pipeline_and_refuses_to_run_open(tmp_path, monkeypatch):
    import uvicorn

    import axelrod_ingest.ocr as ocr

    monkeypatch.delenv("INGEST_TOKEN", raising=False)
    with pytest.raises(SystemExit, match="INGEST_TOKEN"):
        service.main()
    served, seen = {}, {}
    monkeypatch.setattr(uvicorn, "run", lambda app, host, port: served.update(app=app, host=host, port=port))
    monkeypatch.setattr(ocr, "ocr_from_env", lambda env: seen.update(env) or None)
    monkeypatch.setenv("INGEST_TOKEN", "ingest-token")
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("AXELROD_OCR_CACHE", raising=False)
    service.main()
    assert served["port"] == 8000 and served["host"] == "" and TestClient(served["app"]).get("/health").status_code == 200
    # OCR's page cache is a cache keyed by content: temporary storage, never the lake's volume
    assert seen["AXELROD_OCR_CACHE"].endswith("axelrod-ocr")
    monkeypatch.setenv("AXELROD_OCR_CACHE", str(tmp_path / "ocr"))
    monkeypatch.setenv("PORT", "9001")
    service.main()
    assert seen["AXELROD_OCR_CACHE"] == str(tmp_path / "ocr") and served["port"] == 9001
