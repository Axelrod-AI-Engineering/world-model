"""The world model with its lake and ingestion on their own services (Oct 24): with WORLD_MODEL_LAKE_URL and
WORLD_MODEL_INGEST_URL set, an upload and a search through /v1 give what the in-process lakehouse gives, the model's
process opens no lake directory and loads no embedder (the data service holds the files and the matrix, the ingestion
service the weights), and /api/health says which mode runs without naming an address. Both services run in process here:
the clients are handed `TestClient`s on their apps. With no variables set, nothing changes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from axelrod_ingest.ingest_client import RemoteEmbedder, RemoteIngestor
from axelrod_ingest.lake.embed import HashingEmbedder
from axelrod_ingest.lake.remote import RemoteLake
from axelrod_ingest.lake.server import create_lake_app
from axelrod_ingest.lake.sqlite import SQLiteLake
from axelrod_ingest.service import create_ingest_app
from axelrod_wm.api.app import create_app
from axelrod_wm.repo.snapshots import MemoryBackend
from tests.service.helpers import NOTE, OIL_NOTE, WM, data, service, upload

pytestmark = pytest.mark.integration
LAKE_TOKEN, INGEST_TOKEN = "lake-secret", "ingest-secret"


@pytest.fixture
def services(tmp_path, monkeypatch):
    """The data and ingestion services in process, and the environment that points the world model at them."""
    backing = SQLiteLake(tmp_path / "data")
    lake_app = create_lake_app(backing, LAKE_TOKEN)
    ingest_store = RemoteLake("http://lake", LAKE_TOKEN, TestClient(lake_app, base_url="http://lake"))
    ingest_app = create_ingest_app(ingest_store, HashingEmbedder(), None, None, INGEST_TOKEN)
    clients = {"http://lake": TestClient(lake_app, base_url="http://lake"),
               "http://ingest": TestClient(ingest_app, base_url="http://ingest")}
    lake_init, ingest_init = RemoteLake.__init__, RemoteIngestor.__init__
    monkeypatch.setattr(RemoteLake, "__init__", lambda self, url, token, client=None, **kw: lake_init(
        self, url, token, client or clients[url], **kw))
    monkeypatch.setattr(RemoteIngestor, "__init__", lambda self, url, token, client=None: ingest_init(
        self, url, token, client or clients[url]))
    never = tmp_path / "never" / "lake"
    yield {"WORLD_MODEL_LAKE_URL": "http://lake", "WORLD_MODEL_LAKE_TOKEN": LAKE_TOKEN,
           "WORLD_MODEL_INGEST_URL": "http://ingest", "WORLD_MODEL_INGEST_TOKEN": INGEST_TOKEN,
           "WORLD_MODEL_LAKE_DIR": str(never), "WORLD_MODEL_EMBED_CACHE": str(tmp_path / "never" / "models")}
    backing.close()


def flow(c) -> dict:
    """Two uploads and every kind of search; what a caller sees."""
    a = upload(c, NOTE, "rates.txt")
    b = upload(c, OIL_NOTE, "oil.txt")
    searches = {mode: data(c.get(f"{WM}/search", params={"q": "central bank policy rate", "mode": mode}))
                for mode in ("keyword", "prefix", "semantic", "graph", "hybrid")}
    docs = data(c.get(f"{WM}/documents"))
    return {"uploads": [a, b], "searches": searches, "documents": [d["id"] for d in docs]}


def test_uploads_and_search_through_the_services_match_the_local_lakehouse(services):
    with service() as local:
        want = flow(local)
    with service(**services) as remote:
        got = flow(remote)
    assert got == want
    assert len(got["searches"]["semantic"]) > 0 and got["uploads"][0]["bundle_id"]


def test_the_model_opens_no_lake_and_loads_no_embedder(services, tmp_path):
    with service(**services) as c:
        state = c.app.state
        assert isinstance(state.lake, RemoteLake) and isinstance(state.ingestor, RemoteIngestor)
        assert isinstance(state.ingestor.embedder, RemoteEmbedder)
        upload(c, NOTE, "rates.txt")
        data(c.get(f"{WM}/search", params={"q": "policy rate", "mode": "semantic"}))
    assert not (tmp_path / "never").exists()          # neither WORLD_MODEL_LAKE_DIR nor the embedding cache was made
    assert list((tmp_path / "data").glob("**/raw/*"))      # the files are in the data service's volume, and only there


def test_the_legacy_import_view_reads_through_the_services(services):
    with service(**services) as c:
        r = c.post("/api/import/document", files={"file": ("n.md", NOTE, "text/markdown")},
                   data={"source_type": "broker_research"})
        assert r.status_code == 200 and r.json()["bundle_id"]
        docs = c.get("/api/import/documents").json()
        assert [d["filename"] for d in docs] == ["n.md"]
        again = c.post(f"/api/import/documents/{docs[0]['id']}")
        assert again.status_code == 200 and again.json()["bundle_id"] == r.json()["bundle_id"]


def test_health_says_which_mode_runs_and_names_no_address(services):
    with service(**services) as c:
        body = c.get("/api/health").json()
        assert body["services"] == {"lake": {"mode": "remote", "reachable": True},
                                    "ingestion": {"mode": "remote", "reachable": True}}
        text = c.get("/api/health").text
        assert "http://" not in text and LAKE_TOKEN not in text and INGEST_TOKEN not in text
    with service() as c:
        assert c.get("/api/health").json()["services"] == {"lake": {"mode": "local"}, "ingestion": {"mode": "local"}}


def test_the_ingestion_service_needs_the_data_service(monkeypatch):
    monkeypatch.setenv("WORLD_MODEL_INGEST_URL", "http://ingest")
    monkeypatch.setenv("WORLD_MODEL_INGEST_TOKEN", "t")
    monkeypatch.delenv("WORLD_MODEL_LAKE_URL", raising=False)
    with pytest.raises(ValueError, match="WORLD_MODEL_LAKE_URL"):
        create_app(scenario="acme_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
