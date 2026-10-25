"""An imported model (acme_demo, sim/imports.py) through the API: seeded, a bundle previewed and imported, each item
reviewed in date order, and a ready-made question posed."""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.repo.snapshots import MemoryBackend
from tests.where import IMPORT_BUNDLE_SAMPLE

SAMPLE = json.loads(IMPORT_BUNDLE_SAMPLE.read_text())


@pytest.fixture(scope="module")
def client():
    app = create_app(scenario="acme_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        yield c


def settle(client: TestClient, timeout: float = 120.0) -> dict:
    """The API drives a resumed update in the background: wait until it rests."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = client.get("/api/sim/status").json()
        if st["state"] != "running":
            return st
        time.sleep(0.1)
    raise AssertionError("the import kept running")


def test_seeded_model(client):
    st = client.get("/api/sim/status").json()
    assert st["imports"] is True and st["canvas"] == "seeded" and st["examples"] is None
    view = client.get("/api/state").json()
    assert {"central_bank", "dollar", "acme_re", "acme_motors"} <= {e["id"] for e in view["entities"]}
    assert {h["pattern_id"] for h in view["hulls"]} >= {"S1", "S3", "G1"}
    ready = client.get("/api/scenario-theses").json()
    assert {t["id"] for t in ready} >= {"S-T1", "S-T4"}


def test_preview_import_and_review_in_date_order(client):
    pv = client.post("/api/import/preview", json={"bundle": SAMPLE}).json()
    assert [x["id"] for x in pv["items"]] == ["T-001", "T-002", "T-003"]       # by date
    first = pv["items"][0]
    assert first["status"] == "new" and first["changes"] == 1 and first["dropped"]
    bad = client.post("/api/import/preview", json={"bundle": {"items": [{"id": 1}]}})
    assert bad.status_code in (400, 409, 422)

    out = client.post("/api/import", json={"bundle": SAMPLE, "ids": ["T-001", "T-002"]}).json()
    assert out["imported"] == ["T-001", "T-002"] and out["proposal"]["proposal"]["market_event_id"] == "IM-T-001"
    seen = []
    while True:
        settle(client)
        pending = client.get("/api/proposals?status=pending").json()
        if not pending:
            break
        pid = pending[0]["proposal"]["id"]
        seen.append(pending[0]["proposal"]["market_event_id"])
        assert client.post(f"/api/proposals/{pid}/approve", json={"by": "eve"}).status_code == 200
    assert seen == ["IM-T-001", "IM-T-002"]
    again = client.post("/api/import/preview", json={"bundle": SAMPLE}).json()
    assert {x["id"]: x["status"] for x in again["items"]} == {"T-001": "imported", "T-002": "imported", "T-003": "new"}
    assert client.post("/api/import", json={"bundle": SAMPLE, "ids": ["T-001"]}).status_code in (400, 409)


def test_ready_made_question_forecasts_the_book(client):
    fv = client.post("/api/theses/S-T1/pose").json()
    moved = {v["id"] for v in fv["transmission"]["values"]}
    assert "crude_oil.price" in moved or "crude_oil.price" in {s["id"] for s in fv["transmission"]["shocked"]}
    book = {n["id"]: n["status"] for n in fv["transmission"]["watchlist"]["names"]}
    assert book["acme_re"] in ("moves", "small")


def test_local_bundles_listed_only_where_the_folder_exists(client):
    assert isinstance(client.get("/api/import/local").json(), list)


def test_auto_accept_approves_what_waits_and_what_comes(client):
    out = client.post("/api/import", json={"bundle": SAMPLE, "ids": ["T-003"]}).json()
    assert out["waiting_on"]
    cfg = client.patch("/api/config/review", json={"policy": "auto_approve_all", "approve_pending": True}).json()
    assert cfg["review_policy"] == "auto_approve_all"
    settle(client)
    assert client.get("/api/proposals?status=pending").json() == []
    assert client.post("/api/import/preview", json={"bundle": SAMPLE}).json()["items"][-1]["status"] == "imported"
    assert client.patch("/api/config/review", json={"policy": "review_all"}).json()["review_policy"] == "review_all"
    assert client.patch("/api/config/review", json={"policy": "nonsense"}).status_code == 422
    standards = client.patch("/api/config/review", json={"policy": "standards", "by": "eve"}).json()
    assert standards["review_policy"] == "standards"
