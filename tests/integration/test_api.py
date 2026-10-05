"""The HTTP API and the /ws stream through FastAPI's TestClient (§12, §15.2)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.engine.config import DEFAULT_CONFIG_PATH, deep_merge
from axelrod_wm.memory.snapshots import MemoryBackend

T01 = {
    "id": "T-api", "question": "What if oil prices doubled next quarter?", "mode": "scaffolded", "horizon_days": 182,
    "targets": ["inflation.headline_cpi", "interest_rates.us_policy_rate", "credit_availability.credit_growth"],
    "event": {"kind": "hypothetical", "event_type": "supply_shock", "occurred_at": "2026-04-01T00:00:00Z",
              "ops": [{"op": "change_value", "target": {"kind": "concrete", "subentity_id": "resources_energy.oil_price"},
                       "delta": 1.0, "mode": "relative", "persistence": "step", "at": "2026-04-01T00:00:00Z"}]},
}


@pytest.fixture(scope="module")
def client():
    app = create_app(scenario="oil_shock_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        yield c


def wait_until_not_running(client: TestClient, timeout: float = 600.0) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = client.get("/api/sim/status").json()
        if st["state"] != "running":
            return st
        time.sleep(0.2)
    raise AssertionError("the scenario kept running")


def test_read_endpoints_after_load(client):
    h = client.get("/api/health").json()
    assert h["ok"] is True and h["version"] > 0
    view = client.get("/api/state").json()
    assert view["version"] == h["version"]
    assert len(view["entities"]) == 33 and len(view["subentities"]) == 69
    assert {x["pattern_id"] for x in view["hulls"]} >= {f"S{i}" for i in range(1, 10)}
    assert len(view["frontier"]) == 1 and view["frontier"][0]["earlier"] == "inflation.headline_cpi"
    assert client.get("/api/versions").json()
    cfg = client.get("/api/config").json()
    assert cfg["components"]["propagator"]["name"] == "mc_impulse"
    assert "e08" in [x["id"] for x in view["links"]]
    assert client.get("/api/entities/inflation").json()["entity"]["id"] == "inflation"
    rec = client.get("/api/interactions/e08").json()
    assert rec["source"] == "resources_energy.oil_price" and rec["kernel_means"]["delay_days"] > 0
    assert client.get("/api/superentities/S2").json()["pattern"]["id"] == "S2"
    tax = client.get("/api/taxonomies/object").json()
    assert any(n["id"] == "gen:obj:central_bank" for n in tax["nodes"])
    assert client.get("/api/taxonomies/nope").status_code == 404
    mem = client.get("/api/memory").json()
    assert mem["episodes"] > 0 and mem["patterns"] >= 11
    fr = client.get("/api/frontier").json()
    series = client.get(f"/api/frontier/{fr[0]['id']}/series").json()
    assert "pairs" in series and series["lag_steps"] == fr[0]["lag_steps"]
    hyps = client.get("/api/hypotheses?sort=voi").json()
    assert any(x["hypothesis"]["id"] == "H-fed-hold" for x in hyps)
    assert client.get("/api/scenarios").json()[0]["id"] == "oil_shock_demo"
    layout = client.get("/api/layouts/figure1").json()
    assert layout
    assert client.get("/api/entities/nope").status_code == 404
    assert client.get("/api/sim/status").json()["step_index"] == 0


def test_ws_replays_and_streams_trace_events(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "hello", "since_seq": 0})
        first = ws.receive_json()
        assert first["type"] in ("trace", "status")
        seen_status = first["type"] == "status"
        while not seen_status:
            msg = ws.receive_json()
            seen_status = msg["type"] == "status"
        rep = client.post("/api/sim/step").json()
        assert rep["step_index"] == 0
        kinds, seqs = set(), []
        while True:
            msg = ws.receive_json()
            if msg["type"] == "trace":
                kinds.add(msg["event"]["kind"])
                seqs.append(msg["event"]["seq"])
            elif msg["status"]["step_index"] >= 1:
                break
        assert "scenario.caption" in kinds
        assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    trace = client.get(f"/api/trace?since_seq={seqs[0] - 1}").json()
    assert [e["seq"] for e in trace][: len(seqs)] == seqs


def test_step_until_review_then_approve(client):
    v0 = client.get("/api/health").json()["version"]
    for _ in range(4):
        st = client.get("/api/sim/status").json()
        if st["pending_proposals"]:
            break
        client.post("/api/sim/step")
    pending = client.get("/api/proposals?status=pending").json()
    assert pending, "a news event should wait for review"
    st = client.get("/api/sim/status").json()
    assert st["state"] == "awaiting_review"
    p = pending[0]
    assert p["ops"] and p["review_reasons"]
    out = client.post(f"/api/proposals/{p['proposal']['id']}/approve", json={"by": "tester", "note": "ok"}).json()
    assert out["proposal"]["status"] == "approved"
    assert client.get("/api/health").json()["version"] > v0
    again = client.post(f"/api/proposals/{p['proposal']['id']}/approve", json={"by": "tester"})
    assert again.status_code == 409
    for q in client.get("/api/proposals?status=pending").json():
        client.post(f"/api/proposals/{q['proposal']['id']}/defer", json={"by": "tester"})
    assert client.get("/api/sim/status").json()["state"] != "awaiting_review"


def test_pose_thesis_and_read_the_forecast(client):
    v = client.get("/api/health").json()["version"]
    r = client.post("/api/theses", json=T01)
    assert r.status_code == 200, r.text
    fv = r.json()
    fc = fv["forecast"]
    assert fc["based_on_version"] == v and fv["targets"] and fv["dates"]
    assert abs(sum(s["weight"] for s in fv["scenarios"]) - 1.0) < 1e-9
    assert client.get("/api/health").json()["version"] == v          # posing never bumps the version
    listed = client.get("/api/forecasts").json()
    assert fc["id"] in [x["id"] for x in listed]
    assert client.get(f"/api/forecasts/{fc['id']}").json()["forecast"]["id"] == fc["id"]
    if fc.get("explanation_id"):
        assert client.get(f"/api/explanations/{fc['explanation_id']}").json()["id"] == fc["explanation_id"]
    q = client.post("/api/theses", json={"question": "What if oil prices doubled next quarter?"})
    assert q.status_code in (200, 422), q.text
    if q.status_code == 422:
        assert "unbound" in q.json()


def test_a_hand_drawn_edge_becomes_a_proposal(client):
    """The payload the Draw tool posts (§13.5): a concrete source and an entity-level target."""
    now = client.get("/api/sim/status").json()["sim_time"]
    ev = {"id": "GUE-DRAW-test", "kind": "real", "event_type": "hand_drawn", "occurred_at": now, "recorded_at": now,
          "produced_by": "human",
          "ops": [{"op": "add_interaction", "source": {"kind": "concrete", "subentity_id": "resources_energy.oil_price"},
                   "target": {"kind": "abstract", "entity_id": "consumer_spending"}, "label": "squeezes", "polarity": -1,
                   "dynamics": {"effect": {"family": "gaussian", "mu": -0.2, "sigma": 0.2},
                                "kernel": {"delay_days": 14, "lag_days": 30, "duration_days": None}}}]}
    r = client.post("/api/graph-update-events", json=ev)
    assert r.status_code == 200, r.text
    pv = r.json()
    assert pv["proposal"]["event"]["produced_by"] == "human"
    assert pv["proposal"]["status"] in ("auto_applied", "pending")      # auto_approve_human applies it
    assert pv["refinement_steps"], "the refiner ranks the target entity's subentities"


def test_restore_an_earlier_version(client):
    versions = client.get("/api/versions").json()
    first = versions[0]["version"]
    now = client.get("/api/health").json()["version"]
    assert now > first
    old = client.get(f"/api/state?version={first}").json()
    assert old["version"] == first
    cur = client.get("/api/state").json()
    assert cur["version"] == now
    assert client.get("/api/state?version=999999").status_code == 404


def test_review_policy_and_play_pause(client):
    cfg = client.patch("/api/config/review", json={"policy": "auto_approve_all"}).json()
    assert cfg["review_policy"] == "auto_approve_all"
    assert client.patch("/api/config/review", json={"policy": "nope"}).status_code == 422
    st0 = client.get("/api/sim/status").json()
    client.post("/api/sim/play", json={"until_step": st0["step_index"] + 2})
    st = wait_until_not_running(client)
    assert st["step_index"] == st0["step_index"] + 2
    assert client.post("/api/sim/pause").json()["state"] in ("idle", "awaiting_review", "done")
    reset = client.post("/api/sim/reset").json()
    assert reset["step_index"] == 0


# -- every shipped alternative runs the scenario to the end (§15.2) --------------------------------
ALTERNATIVES = [
    ("taxonomy_grower", {"components": {"taxonomy_grower": "none"}}),
    ("recaller", {"components": {"recaller": "recency"}}),
    ("prefiller", {"components": {"prefiller": "none"}}),
    ("propagator", {"components": {"propagator": "deterministic_mean"}}),
    ("kernel_updater", {"components": {"kernel_updater": "none"}}),
    ("isolator", {"components": {"isolator": "k_hop"}}),
    ("coupler", {"components": {"coupler": "iterative_block"}}),
    ("scenario_weighter", {"components": {"scenario_weighter": "uniform"}}),
    ("unifier", {"components": {"unifier": "weighted_mixture"}}),
    ("review_policy", {"components": {"review_policy": "auto_approve_all"}, "review": {"policy": "auto_approve_all"}}),
    ("translator", {"translators": {"news": "template"}}),
    ("storage", {"storage": {"backend": "memory"}}),
]


@pytest.mark.slow
@pytest.mark.parametrize("slot,override", ALTERNATIVES, ids=[a[0] for a in ALTERNATIVES])
def test_each_alternative_runs_the_scenario_to_the_end(slot, override, tmp_path: Path):
    base = yaml.safe_load(Path(DEFAULT_CONFIG_PATH).read_text())
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(deep_merge(base, override)))
    storage = None if slot == "storage" else MemoryBackend()
    app = create_app(str(cfg_path), "oil_shock_demo", storage=storage, trace_dir=None, play_delay=0.0,
                     cache_dir=tmp_path / "cache", load_on_startup=False)
    with TestClient(app) as c:
        st = c.post("/api/sim/load", json={"scenario": "oil_shock_demo", "interactive": False}).json()
        assert st["loaded"] and st["step_index"] == 0
        c.post("/api/sim/play", json={})
        st = wait_until_not_running(c, timeout=1800)
        assert st["state"] == "done" and st["step_index"] == st["total_steps"]
        name = c.get("/api/config").json()
        if slot in name["components"]:
            assert name["components"][slot]["name"] == override["components"][slot]
