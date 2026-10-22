"""The HTTP API and the /ws stream through FastAPI's TestClient (§12, §15.2)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.engine.config import DEFAULT_CONFIG_PATH, deep_merge
from axelrod_wm.repo.snapshots import MemoryBackend

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
    assert len(view["entities"]) == 53 and len(view["subentities"]) == 159
    assert {x["pattern_id"] for x in view["hulls"]} >= {f"S{i}" for i in range(1, 10)}
    assert len(view["frontier"]) == 6 and view["frontier"][0]["earlier"] == "inflation.headline_cpi"   # plus five more seeds
    assert client.get("/api/versions").json()
    cfg = client.get("/api/config").json()
    assert cfg["components"]["propagator"]["name"] == "mc_impulse"
    # the history replay approves everything, but the session keeps the configured policy
    assert cfg["review_policy"] == "default"
    # the composite seed, its parts, and the descriptions the demo shows
    s10 = next(x for x in view["hulls"] if x["pattern_id"] == "S10")
    assert s10["child_instance_ids"] == ["inst-S2", "inst-S1"] and s10["description"]
    assert all(e["description"] for e in view["entities"])
    assert all(f["next_eligible"] is None or len(f["next_eligible"]) == 10 for f in client.get("/api/frontier").json())
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
    assert list(mem)[:5] == ["object_generalizations", "interaction_generalizations", "entity_memories",
                             "correlation_frontier", "prior_states"]
    assert all("observed_today" in s for s in view["subentities"])
    # each value's scale (Oct 17), so the canvas can show a move in sd in the value's own unit
    assert all(s["scale"] > 0 for s in view["subentities"])
    fr = client.get("/api/frontier").json()
    series = client.get(f"/api/frontier/{fr[0]['id']}/series").json()
    assert "pairs" in series and series["lag_days"] == fr[0]["lag_days"]
    hyps = client.get("/api/hypotheses?sort=voi").json()
    assert any(x["hypothesis"]["id"] == "H-fed-hold" for x in hyps)
    assert {"oil_shock_demo", "small_demo", "acme_demo"} <= {s["id"] for s in client.get("/api/scenarios").json()}
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


def wait_for_update(client: TestClient, update_id: str, timeout: float = 600.0) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        run = client.get(f"/api/updates/{update_id}").json()
        if run["state"] not in ("running", "collecting"):
            return run
        time.sleep(0.1)
    raise AssertionError("the update kept running")


def test_step_until_review_then_approve(client):
    v0 = client.get("/api/health").json()["version"]
    for _ in range(4):
        st = client.get("/api/sim/status").json()
        if st["state"] == "awaiting_review":
            break
        client.post("/api/sim/step")
    st = client.get("/api/sim/status").json()
    assert st["state"] == "awaiting_review" and st["update_id"], "a news event should pause the update for review"
    run = client.get(f"/api/updates/{st['update_id']}").json()
    assert run["state"] == "awaiting_review" and run["waiting_on"]
    # the day's news items wait one at a time; approving each resumes the run until the next
    approved = []
    while run["state"] == "awaiting_review":
        pending = client.get("/api/proposals?status=pending").json()
        p = next(x for x in pending if x["proposal"]["id"] == run["waiting_on"][0])
        assert p["ops"] and p["review_reasons"] and p["proposal"]["world_event"]
        out = client.post(f"/api/proposals/{p['proposal']['id']}/approve", json={"by": "tester", "note": "ok"}).json()
        assert out["proposal"]["status"] == "approved"
        approved.append(p["proposal"]["id"])
        run = wait_for_update(client, run["id"])
    assert run["state"] == "done" and run["report"]["approved"] >= len(approved) >= 1
    assert client.get("/api/health").json()["version"] > v0
    again = client.post(f"/api/proposals/{approved[0]}/approve", json={"by": "tester"})
    assert again.status_code == 409
    wait_until_not_running(client)
    assert client.get("/api/sim/status").json()["step_index"] >= 3


def test_an_update_with_a_typed_event_pauses_and_resumes(client):
    st = client.get("/api/sim/status").json()
    if st["state"] == "awaiting_review":
        for q in client.get("/api/proposals?status=pending").json():
            client.post(f"/api/proposals/{q['proposal']['id']}/defer", json={"by": "tester"})
        wait_until_not_running(client)
    today = client.get("/api/state").json()["today"]
    from datetime import date, timedelta

    until = (date.fromisoformat(today) + timedelta(days=3)).isoformat()
    body = {"until": until, "user_market_events": [{"headline": "Oil jumps by 10% after a pipeline outage",
                                                    "kind": "news"}]}
    run = client.post("/api/updates", json=body).json()
    assert run["requested_by"] == "user" and run["days_total"] == 3
    run = wait_for_update(client, run["id"])
    assert run["state"] == "awaiting_review"               # a typed news item is translated from text
    me = [m for m in client.get(f"/api/market-events?update_id={run['id']}").json() if m["channel"] == "user"]
    assert me and me[0]["id"].startswith("ME-U-")
    client.post(f"/api/proposals/{run['waiting_on'][0]}/approve", json={"by": "tester"})
    run = wait_for_update(client, run["id"])
    assert run["state"] == "done" and run["report"]["collected"].get("user") == 1
    assert run["report"]["days"] == 3
    assert any(r["id"] == run["id"] for r in client.get("/api/updates").json())
    # a repeat collects nothing and processes no days
    again = wait_for_update(client, client.post("/api/updates", json={"until": until}).json()["id"])
    assert again["state"] == "done" and again["report"]["days"] == 0


def test_drawn_events_with_world_ops_are_refused(client):
    now = client.get("/api/sim/status").json()["sim_time"]
    ev = {"id": "GUE-DRAW-world", "kind": "real", "occurred_at": now, "recorded_at": now, "produced_by": "human",
          "ops": [{"op": "observe_value", "target": {"kind": "concrete", "subentity_id": "inflation.headline_cpi"},
                   "value": 3.0, "observed_at": now}]}
    assert client.post("/api/graph-update-events", json=ev).status_code == 422
    assert client.post("/api/market-events", json={}).status_code in (404, 405)
    assert client.post("/api/consolidate", json={}).status_code in (404, 405)


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


def test_a_question_forecasts_actors_and_sectors_and_its_trace_replays_alone(client):
    """A question with coarser targets (an actor, a sector) and the trace of just that question, which the
    walkthrough replays step by step (additions)."""
    r = client.post("/api/theses", json={"question": "What if OPEC cuts output by 10%?", "horizon_days": 120,
                                         "targets": ["inflation.headline_cpi"],
                                         "target_groups": [{"kind": "entity", "ref": "delta"},
                                                           {"kind": "sector", "ref": "airlines"}]})
    assert r.status_code == 200, r.text
    fv = r.json()
    assert [g["id"] for g in fv["groups"]] == ["entity:delta", "sector:airlines"]
    for g in fv["groups"]:
        assert g["members"] > 0 and len(g["effects"]) == len(fv["dates"]) and g["top"]
    cpi = next(t for t in fv["targets"] if t["id"] == "inflation.headline_cpi")
    assert cpi["entity"] and "effect_density" in cpi
    tid = fv["forecast"]["thesis_id"]
    evs = client.get(f"/api/trace?since_seq=0&scope={tid}").json()
    kinds = [e["kind"] for e in evs]
    assert evs and all(e["scope"] == tid for e in evs)
    assert kinds[0] == "thesis.posed" and "forecast.ready" in kinds and "isolate.networks" in kinds
    assert evs[0]["payload"]["ops"] and evs[0]["payload"]["target_groups"] == ["entity:delta", "sector:airlines"]


def test_a_forecast_brief_reads_the_forecast_and_the_news_behind_it(client):
    """The brief (addition): a bottom line, a timeline, who is affected, why, the news that shaped it, and
    what to watch, built only from what the model holds."""
    r = client.post("/api/theses", json={"question": "What if OPEC cuts output by 10%?", "horizon_days": 150,
                                         "targets": ["inflation.headline_cpi"],
                                         "target_groups": [{"kind": "sector", "ref": "airlines"}]})
    assert r.status_code == 200, r.text
    fv = r.json()
    assert fv["movers"] and all(abs(m["effect"]) >= 0.02 for m in fv["movers"])
    assert "opec_plus.quota" not in {m["id"] for m in fv["movers"]}        # the shock itself is not a mover
    b = client.get(f"/api/forecasts/{fv['forecast']['id']}/brief").json()
    assert b["forecast_id"] == fv["forecast"]["id"] and b["question"]
    assert b["bottom_line"].startswith("By ") and b["effects"]
    assert b["why"] and all(w["interaction_ids"] for w in b["why"])
    assert {"shaped_by", "since", "tracking", "watch", "change", "caveats", "timeline", "affected", "movers"} <= set(b)
    assert any("synthetic" in c for c in b["caveats"])
    for e in b["shaped_by"] + b["since"]:
        assert 0 < e["relevance"] <= 1 and e["reasons"]
    assert client.get("/api/forecasts/FC-nope/brief").status_code == 404


def test_a_held_decision_brief_states_the_lucas_critique(client):
    """Posing a decision hypothesis holds the decision (graph surgery); its brief says what that assumes."""
    r = client.post("/api/hypotheses/H-fed-hold/pose", json={})
    assert r.status_code == 200, r.text
    b = client.get(f"/api/forecasts/{r.json()['forecast']['id']}/brief").json()
    assert any("Lucas critique" in c and c.startswith("Changing ") for c in b["caveats"])


def test_the_script_lists_every_scripted_step(client):
    steps = client.get("/api/sim/script").json()
    assert len(steps) == 18 and [s["index"] for s in steps] == list(range(18))
    assert {s["kind"] for s in steps} >= {"update", "question", "evaluation", "decision"}
    assert all(s["caption"] for s in steps)


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
