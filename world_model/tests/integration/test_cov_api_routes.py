"""The demo API's remaining endpoints on the small demo (api/routes.py, api/views.py): find, hypotheses and their
evidence, market events, review edits and deferrals, stored theses, forecasts and their grids, update runs,
decisions, layouts, the trace, the commit log, structure edits, examples, imports, and the manual form."""

from __future__ import annotations

import contextlib
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.repo.snapshots import MemoryBackend
from tests.where import SMALL_DEMO_DIR

QUESTION = "What if oil rose by 30% next quarter?"


@contextlib.contextmanager
def demo(build: bool = False):
    """A small-demo server; with build, every example played and approved (about two seconds)."""
    app = create_app(scenario="small_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        c.app_state = app.state.axelrod
        if build:
            for ex in c.get("/api/examples").json():
                out = c.post(f"/api/examples/{ex['id']}").json()
                if out.get("proposal_id"):
                    assert c.post(f"/api/proposals/{out['proposal_id']}/approve", json={"by": "t"}).status_code == 200
        yield c


@pytest.fixture(scope="module")
def built():
    """Read-only tests share one built demo."""
    with demo(build=True) as c:
        c.forecast = c.post("/api/theses", json={"question": QUESTION}).json()["forecast"]
        yield c


@pytest.fixture
def fresh_built():
    with demo(build=True) as c:
        yield c


@pytest.fixture
def blank():
    with demo() as c:
        yield c


# -- reads ----------------------------------------------------------------------------------------------
def test_session_find_and_learning_tasks(built):
    assert built.get("/api/session").json() == {"login": None}
    hits = built.get("/api/find", params={"q": "fuel"}).json()
    assert hits["words"] == ["fuel"] and hits["hits"]
    assert all("fuel" in " ".join(h["why"] + [h["name"].lower()]) or h["why"] for h in hits["hits"])
    tasks = {t["id"]: t for t in built.get("/api/learning-tasks").json()}
    assert {"refine", "fold", "frontier", "abduce", "entity_memories", "generalize"} <= set(tasks)
    assert tasks["refine"]["target"]["kind"] == "walk"


def test_hypotheses_sorted_by_id_and_their_evidence(built):
    hs = built.get("/api/hypotheses", params={"sort": "id"}).json()
    ids = [h["hypothesis"]["id"] for h in hs]
    assert ids == sorted(ids) and len(hs[0]["decay_points"]) == 9
    ev = built.get(f"/api/hypotheses/{ids[0]}/evidence").json()
    assert ev["id"] == ids[0] and ev["basis"] in ("correlation frontier", "interaction existence", "prior")
    assert ev["comovement"] is not None and {s["id"] for s in ev["series"]} == {
        hs[0]["hypothesis"]["source_id"], hs[0]["hypothesis"]["target_id"]}
    assert built.get("/api/hypotheses/H-nope/evidence").status_code == 404


def test_market_events_one_by_one(built):
    mid = built.get("/api/market-events").json()[0]["id"]
    one = built.get(f"/api/market-events/{mid}").json()
    assert one["event"]["id"] == mid and one["status"]
    assert built.get("/api/market-events/ME-nope").status_code == 404


def test_market_events_fall_back_to_the_runners_source(built, monkeypatch):
    ev = SimpleNamespace(model_dump=lambda mode: {"id": "ME-SRC"})
    monkeypatch.setattr(built.app_state.runner, "market_source", SimpleNamespace(get={"ME-SRC": ev}.get),
                        raising=False)
    out = built.get("/api/market-events/ME-SRC").json()
    assert out == {"event": {"id": "ME-SRC"}, "translation": None, "status": None}
    assert built.get("/api/market-events/ME-nope").status_code == 404


def test_trace_with_a_limit(built):
    assert len(built.get("/api/trace", params={"limit": 3}).json()) == 3
    assert built.get("/api/trace", params={"limit": -1}).json() == []


def test_repo_processes_and_a_missing_commit(built):
    assert built.get("/api/repo/processes").json()
    assert built.get("/api/repo/commits/999999").status_code == 404


def test_layout_missing(built, monkeypatch):
    init = built.app_state.runner.script.initialization
    monkeypatch.setattr(init, "layout", str(SMALL_DEMO_DIR / "no_such_layout.yaml"))
    r = built.get("/api/layouts/figure1")
    assert r.status_code == 200 and r.json() == {}       # the canvas lays the graph out itself


def test_past_versions_restore(built):
    # a regression: learning wrote into an approved event's interaction dynamics in place, so a hedge's stored op
    # drifted from the ledger and restoring a past version failed its hash check (shared/parse.py)
    versions = [v["version"] for v in built.get("/api/versions").json()]
    for v in (versions[len(versions) // 2], versions[-2]):
        r = built.get("/api/state", params={"version": v})
        assert r.status_code == 200 and r.json()["version"] == v and r.json()["read_only"] is True


# -- hypotheses written through the API -----------------------------------------------------------------
def test_post_a_hypothesis_set_its_status_and_read_its_evidence(fresh_built):
    c = fresh_built
    link = c.get("/api/state").json()["links"][0]
    made = c.post("/api/hypotheses", json={"kind": "interaction_present", "statement": "the link holds",
                                          "interaction_id": link["id"], "origin": "human"}).json()
    hid = made["hypothesis"]["id"]
    assert made["hypothesis"]["kind"] == "interaction_present" and 0 < made["hypothesis"]["probability"] <= 1
    ev = c.get(f"/api/hypotheses/{hid}/evidence").json()
    assert ev["basis"] == "interaction existence" and ev["interaction"]["id"] == link["id"]
    out = c.post(f"/api/hypotheses/{hid}/status", json={"status": "refuted"}).json()
    assert out["hypothesis"]["status"] == "refuted"


def test_a_decision_hypothesis_reads_the_entity_memory(fresh_built):
    c = fresh_built
    sid = "federal_reserve.policy_rate"
    made = c.post("/api/hypotheses", json={"kind": "entity_decision", "statement": "the Fed holds",
                                          "decision_subentity_id": sid, "decision_change": 0.0,
                                          "decision_window_days": 30, "origin": "human"}).json()
    ev = c.get(f"/api/hypotheses/{made['hypothesis']['id']}/evidence").json()
    assert ev["decision"]["subentity"] == sid and ev["series"][0]["id"] == sid
    assert ev["basis"] in ("entity memory", "prior")


# -- review: stage parameters, reject without a note, edit, defer ---------------------------------------
def test_stage_parses_per_op_confidence_and_ripples(blank):
    pid = blank.post("/api/examples/create").json()["proposal_id"]
    out = blank.get(f"/api/proposals/{pid}/stage",
                    params={"graph": "false", "opconf": "0:0.5,1:,bad", "ripple": "x.y:0.5,z.w:,junk"})
    assert out.status_code == 200
    assert blank.post(f"/api/proposals/{pid}/reject", json={"by": "t"}).status_code == 422


def test_edit_and_defer_a_proposal(blank):
    out = blank.post("/api/examples/create").json()
    pid = out["proposal_id"]
    event = out["proposal"]["proposal"]["event"]
    edited = blank.post(f"/api/proposals/{pid}/edit", json={"by": "kim", "event": {**event, "ops": event["ops"][:1]}})
    assert edited.status_code == 200 and len(edited.json()["ops"]) == 1
    deferred = blank.post(f"/api/proposals/{pid}/defer").json()
    assert deferred["proposal"]["status"] == "deferred"


# -- theses and forecasts -------------------------------------------------------------------------------
def test_stored_theses_and_scripted_steps(built, monkeypatch):
    runner = built.app_state.runner
    monkeypatch.setattr(runner, "theses_spec", {"T-A": {"question": "a?", "horizon_days": 30}, "T-B": {}},
                        raising=False)
    steps = [SimpleNamespace(theses=lambda: ["T-A"]), SimpleNamespace()]
    monkeypatch.setattr(runner, "script", SimpleNamespace(steps=steps))
    assert built.get("/api/scenario-theses").json() == [
        {"id": "T-A", "question": "a?", "horizon_days": 30, "scripted": True},
        {"id": "T-B", "question": "T-B", "horizon_days": None, "scripted": False}]


def test_unknown_forecasts_and_explanations_are_404(built):
    assert built.post("/api/theses/T-nope/pose").status_code == 404
    for path in ("/api/forecasts/FC-nope/annotations", "/api/paths/forecast/FC-nope", "/api/forecasts/FC-nope",
                 "/api/explanations/EX-nope"):
        assert built.get(path).status_code == 404, path


def test_forecast_grid_methods(built):
    fid = built.forecast["id"]
    assert built.get(f"/api/paths/forecast/{fid}", params={"method": "nope"}).status_code == 400
    grid = built.get(f"/api/paths/forecast/{fid}", params={"outputs": "delta.avg_fare"}).json()
    assert grid["title"] == QUESTION and grid.get("empty") is not True


def test_an_empty_grid(built, monkeypatch):
    fc = built.app_state.runner.controller.forecast(built.forecast["id"])
    monkeypatch.setattr(fc, "paths", {})
    grid = built.get(f"/api/paths/forecast/{fc.id}").json()
    assert grid["empty"] is True and grid["values"] == {} and grid["methods"]


def test_proposal_grid(blank):
    pid = blank.post("/api/examples/ripple").json()["proposal_id"]
    grid = blank.get(f"/api/paths/proposal/{pid}", params={"keep": "0,1", "opconf": "0:1", "ripple": "a.b:1",
                                                           "outputs": ""})
    assert grid.status_code == 200 and "values" in grid.json()


# -- update runs --------------------------------------------------------------------------------------
def test_continue_a_run_waiting_on_review_then_cancel_it(blank):
    blank.post("/api/examples/create")
    uid = blank.get("/api/sim/status").json()["update_id"]
    assert blank.get(f"/api/updates/{uid}").json()["state"] == "awaiting_review"
    out = blank.post(f"/api/updates/{uid}/continue").json()
    assert out["id"] == uid and out["state"] in ("running", "done")
    done = blank.post(f"/api/updates/{uid}/cancel").json()
    assert done["state"] == "done" and done["market_events"][0]["events"][0]["status"] == "deferred"
    again = blank.post(f"/api/updates/{uid}/continue").json()       # a finished run stays finished
    assert again["state"] == "done"


# -- decisions ------------------------------------------------------------------------------------------
def test_decisions_cite_a_baseline_forecast(fresh_built):
    c = fresh_built
    shocked = c.post("/api/theses", json={"question": QUESTION}).json()["forecast"]
    base = c.post("/api/theses", json={"id": "T-base", "question": "where things go", "mode": "open_ended",
                                      "horizon_days": 30, "targets": ["delta.avg_fare"],
                                      "event": {"occurred_at": "2026-05-20T00:00:00Z", "ops": []}}).json()["forecast"]
    assert base["is_baseline"] is True
    body = {"agent_id": "pm", "recommendation": "hold", "thesis_ids": ["T-base"], "state_version": base["based_on_version"],
            "review_after": "2026-06-01T00:00:00Z", "id": "ignored"}
    refused = c.post("/api/decisions", json={**body, "forecast_ids": [shocked["id"]]})
    assert refused.status_code == 409 and "baseline" in refused.json()["detail"]
    rec = c.post("/api/decisions", json={**body, "forecast_ids": [base["id"]]}).json()
    assert rec["id"] != "ignored" and rec["agent_id"] == "pm"
    assert [d["id"] for d in c.get("/api/decisions").json()] == [rec["id"]]
    tr = c.get(f"/api/decisions/{rec['id']}/trace").json()
    assert tr["decision"]["id"] == rec["id"] and tr["changes_since"] == [] and tr["hash_verified"] is True
    assert [f["id"] for f in tr["forecasts"]] == [base["id"]]
    out = c.post(f"/api/decisions/{rec['id']}/resolve")
    assert out.status_code in (200, 409)
    assert c.get("/api/decisions/D-nope/trace").status_code == 409


def test_evaluate_runs_through_the_controller(fresh_built):
    r = fresh_built.post("/api/evaluate", json={"freeze_at": "2026-05-01T00:00:00Z", "horizon_days": 7})
    assert r.status_code in (200, 404)        # 404: the version at the freeze cannot be restored
    assert fresh_built.post("/api/evaluate", json={"horizon_days": 7}).status_code == 422


def test_a_thesis_on_values_not_in_the_graph_is_refused(blank):
    r = blank.post("/api/theses", json={"question": QUESTION})
    assert r.status_code == 422


# -- simulation -----------------------------------------------------------------------------------------
def test_step_is_refused_while_playing(blank, monkeypatch):
    with monkeypatch.context() as m:              # undone before the server shuts down
        m.setattr(blank.app_state, "play_task", SimpleNamespace(done=lambda: False))
        r = blank.post("/api/sim/step")
    assert r.status_code == 409 and "pause it first" in r.json()["detail"]


# -- structure edits ------------------------------------------------------------------------------------
def test_group_and_dissolve(fresh_built):
    c = fresh_built
    link = next(x for x in c.get("/api/state").json()["links"] if x["source"].split(".")[0] != x["target"].split(".")[0])
    ents = [link["source"].split(".")[0], link["target"].split(".")[0]]
    p = c.post("/api/structure/group", json={"name": "Pair", "members": ents, "by": "kim"}).json()
    assert p["proposal"]["status"] == "pending" and p["ops"][0]["op"] == "propose_superentity"
    assert c.post("/api/structure/group", json={"name": "None", "members": []}).status_code == 422
    hull = next(h for h in c.get("/api/state").json()["hulls"] if h["status"] == "admitted")
    d = c.post("/api/structure/dissolve", json={"pattern_id": hull["pattern_id"], "reason": "test"}).json()
    assert d["ops"][0]["op"] == "dissolve_superentity"
    assert c.post("/api/structure/dissolve", json={"pattern_id": "nope", "reason": "x"}).status_code == 422


# -- examples, the library, imports, and the manual form -------------------------------------------------
def test_prepare_an_example_and_a_library_event(blank):
    prep = blank.post("/api/examples/links/prepare").json()
    assert prep["example"] == "links"
    out = blank.post("/api/library/jet-fuel-market").json()
    assert "proposal_id" in out


def test_library_event_without_a_proposal(blank, monkeypatch):
    monkeypatch.setattr(blank.app_state.runner, "run_library", lambda key: {"proposal_id": None, "event": key})
    assert blank.post("/api/library/x").json() == {"proposal_id": None, "event": "x"}


def test_examples_and_imports_need_a_runner_that_has_them(blank, monkeypatch):
    for path in ("/api/import/local", "/api/import/local/x.json"):
        assert blank.get(path).status_code == 404
    with monkeypatch.context() as m:              # undone before the server shuts down
        m.setattr(blank.app_state, "runner", SimpleNamespace(loaded=True))
        assert blank.get("/api/examples").json() == []
        r = blank.post("/api/examples/create")
    assert r.status_code == 404 and "no examples" in r.json()["detail"]


def test_import_routes_on_a_runner_that_takes_imports(blank, monkeypatch):
    runner = blank.app_state.runner
    monkeypatch.setattr(runner, "local_bundle", lambda name: {"name": name}, raising=False)
    monkeypatch.setattr(runner, "import_items", lambda bundle, ids: {"waiting_on": None, "ids": ids}, raising=False)
    assert blank.get("/api/import/local/b.json").json() == {"name": "b.json"}
    assert blank.post("/api/import", json={"bundle": {}, "ids": ["a"]}).json() == {"waiting_on": None, "ids": ["a"]}


def test_an_incomplete_manual_form(blank):
    r = blank.post("/api/manual", json={"manual": {"values": [{}]}})
    assert r.status_code == 422 and r.json()["detail"].startswith("the form is incomplete")
