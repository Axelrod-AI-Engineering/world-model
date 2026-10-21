"""Reset to the original demo (Oct 15): every demo a login has opened goes back to its initial state, and the login's
first demo is served again."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.repo.snapshots import MemoryBackend


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
