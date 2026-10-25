"""The top bar's demo menu (api/app.py AppState.switch): switching a running server between demos, each kept as it was
left, with its own storage and trace stream, per login."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.repo.snapshots import FilesBackend, MemoryBackend


def wait_for(client: TestClient, demo: str, timeout: float = 120.0, headers: dict | None = None) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        out = client.get("/api/demos", headers=headers).json()
        if out["current"] == demo and out["switching"] is None:
            return out
        assert (out["switching"] or {}).get("phase") != "error", out["switching"]
        time.sleep(0.1)
    raise AssertionError(f"never switched to {demo}")


@pytest.fixture(scope="module")
def client():
    app = create_app(scenario="small_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        yield c


def test_the_menu_lists_the_repositorys_demos_and_the_clients(client):
    out = client.get("/api/demos").json()
    ids = [d["id"] for d in out["demos"]]
    assert ids[:4] == ["small_demo", "prod_demo", "oil_shock_demo", "acme_demo"]    # then any real client demos
    assert "acme_focus" not in ids                                                  # a focused view is no demo
    assert [d["label"] for d in out["demos"]][:4] == ["Small demo", "Production demo", "Full demo", "Acme's demo"]
    assert out["current"] == "small_demo" and out["switching"] is None
    cur = {d["id"]: d for d in out["demos"]}
    assert cur["small_demo"]["current"] and cur["small_demo"]["ready"]
    assert not cur["acme_demo"]["ready"] and not cur["acme_demo"]["cold"]      # no history to replay
    assert client.post("/api/demos/no_such_demo").status_code == 404


def test_switching_keeps_each_demo_as_it_was_left(client):
    ran = client.post("/api/examples/1")
    assert ran.status_code == 200
    pending = client.get("/api/sim/status").json()["pending_proposals"]
    assert pending >= 1
    small_trace = client.get("/api/trace").json()

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "hello", "since_seq": 10**9})
        first = client.post("/api/demos/acme_demo").json()
        assert first["switching"] is None or first["switching"]["demo"] == "acme_demo"
        out = wait_for(client, "acme_demo")
        # the page streaming the small demo is told to reload
        for _ in range(50):
            msg = ws.receive_json()
            if msg.get("type") == "switched":
                assert msg["scenario"] == "acme_demo"
                break
        else:
            raise AssertionError("no switched message")
    assert {d["id"]: d["ready"] for d in out["demos"]}["acme_demo"]
    st = client.get("/api/sim/status").json()
    assert st["scenario_id"] == "acme_demo" and st["imports"] is True and st["pending_proposals"] == 0
    # its own trace stream: none of the small demo's events
    acme_trace = client.get("/api/trace").json()
    loaded = [e for e in acme_trace if e["kind"] == "scenario.loaded"]
    assert loaded and all(e["refs"] == ["acme_demo"] for e in loaded)
    assert len(acme_trace) < len(small_trace) + 50

    # back to the small demo: immediate, and the waiting review is still there
    back = client.post("/api/demos/small_demo").json()
    assert back["current"] == "small_demo" and back["switching"] is None
    st = client.get("/api/sim/status").json()
    assert st["scenario_id"] == "small_demo" and st["pending_proposals"] == pending


def test_sim_load_still_reloads_a_demo_from_its_start(client):
    client.post("/api/demos/small_demo")
    st = client.post("/api/sim/load", json={"scenario": "small_demo"}).json()
    assert st["scenario_id"] == "small_demo" and st["pending_proposals"] == 0
    st = client.post("/api/sim/load", json={"scenario": "acme_demo"}).json()
    assert st["scenario_id"] == "acme_demo"
    assert client.get("/api/demos").json()["current"] == "acme_demo"


def _sign_in(c: TestClient, username: str, password: str) -> None:
    r = c.post("/login", data={"username": username, "password": password, "next": "/"}, follow_redirects=False)
    assert r.status_code in (302, 303)


def test_a_login_switches_only_its_own_engine(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)          # the extra login's storage goes under var/
    monkeypatch.setenv("WORLD_MODEL_BASIC_AUTH_USERNAME", "manav")
    monkeypatch.setenv("WORLD_MODEL_BASIC_AUTH_PASSWORD", "test-password")
    monkeypatch.setenv("WORLD_MODEL_LOGINS", "eve:other-password:acme_demo")
    # the main engine on files, so each login's engine is stored beside it (var/axelrod/demo-<login>)
    app = create_app(scenario="small_demo", storage=FilesBackend(path=tmp_path / "var" / "axelrod" / "demo"), trace_dir=None)

    with TestClient(app) as c:
        _sign_in(c, "eve", "other-password")
        assert c.get("/api/demos").json()["current"] == "acme_demo"
        c.post("/api/demos/small_demo")
        wait_for(c, "small_demo")
        c.cookies.clear()
        # the main login still serves its own demo, and switching it leaves Acme's engine where she put it
        _sign_in(c, "manav", "test-password")
        assert c.get("/api/demos").json()["current"] == "small_demo"
        c.post("/api/demos/acme_demo")
        wait_for(c, "acme_demo")
        c.cookies.clear()
        _sign_in(c, "eve", "other-password")
        assert c.get("/api/demos").json()["current"] == "small_demo"
        state = app.state
        assert state.axelrod.runners["acme_demo"] is not state.axelrod_by_login["eve"].runners["acme_demo"]
        assert (tmp_path / "var" / "axelrod" / "demo-eve-small_demo").is_dir()
