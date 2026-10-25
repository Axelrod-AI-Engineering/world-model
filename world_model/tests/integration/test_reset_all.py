"""Reset to the original demo (Oct 15): every demo a login has opened goes back to its initial state, and the login's
first demo is served again."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.repo.snapshots import FilesBackend, MemoryBackend


@pytest.fixture()
def client():
    app = create_app(scenario="acme_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        yield c


def test_reset_clears_forecasts_and_returns_to_the_initial_version(client):
    start = client.get("/api/sim/status").json()
    assert client.post("/api/theses/S-T2/pose").status_code == 200
    assert client.get("/api/forecasts").json()
    r = client.post("/api/sim/reset-all")
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["scenario_id"] == "acme_demo" and after["version"] == start["version"]
    assert client.get("/api/forecasts").json() == []
    assert client.get("/api/demos").json()["switching"] is None


def test_an_imported_model_is_kept_across_a_restart_and_a_reset_forgets_it(tmp_path):
    bundle = {"title": "Kept", "synthetic": True, "items": [{
        "id": "K-1", "published_at": "2026-08-04T09:00:00Z", "source": "Synthetic central bank",
        "source_type": "central_bank", "document": "Statement K-1", "coverage": "full", "plausible": True,
        "headline": "The central bank sets its policy rate at 0.5%", "entities": ["central_bank"],
        "signals": [{"type": "observe", "value_of": "central_bank.policy_rate", "value": 0.5}]}]}

    def start():
        return create_app(scenario="acme_demo", storage=FilesBackend(path=tmp_path / "m"), trace_dir=None,
                          play_delay=0.0)

    with TestClient(start()) as c:
        assert c.post("/api/import", json={"bundle": bundle}).status_code == 200
        version = c.get("/api/sim/status").json()["version"]
        assert c.get("/api/config").json()["review_policy"] == "standards"
    with TestClient(start()) as c:                                 # a restart: the same model, items and policy
        assert c.get("/api/sim/status").json()["version"] == version
        assert c.post("/api/import/preview", json={"bundle": bundle}).json()["items"][0]["status"] == "imported"
        assert c.post("/api/sim/reset-all").status_code == 200       # a reset is explicit: the stored model goes
        assert c.get("/api/sim/status").json()["version"] < version
        assert c.post("/api/import/preview", json={"bundle": bundle}).json()["items"][0]["status"] != "imported"


def test_reset_of_a_scripted_demo_needs_no_stored_model_to_forget():
    with TestClient(create_app(scenario="small_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)) as c:
        before = c.get("/api/sim/status").json()["version"]
        assert c.post("/api/sim/reset-all").json()["version"] == before
