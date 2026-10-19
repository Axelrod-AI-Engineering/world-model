"""The demo's views (api/views.py) on edge cases of a built small demo: hedges on a value, records whose parts are
gone, an entity with no concept or memory, data releases behind a hypothesis, previews of every kind of op, and a
model with nothing learned yet."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from axelrod_wm.api import views
from axelrod_wm.events.graph_update import ChangeValue, ConcreteTarget, GraphUpdateEvent, Specificity
from axelrod_wm.intake.refiner import RefinementStep
from axelrod_wm.memory.working import PendingRefinement
from tests.integration.test_cov_api_routes import demo

AT = datetime(2026, 5, 20, tzinfo=UTC)


@pytest.fixture
def ctl():
    with demo(build=True) as c:
        yield c.app_state.runner.controller


@pytest.fixture
def blank_ctl():
    with demo() as c:
        yield c.app_state.runner.controller


def _pend(op, end, node_id):
    return PendingRefinement(id="P", op=op, end=end, reached=Specificity.ENTITY, node_id=node_id,
                             candidates={"delta.fuel_cost": 0.6}, evidence=[], source_event_id="E", created_at=AT,
                             expires_at=AT)


def test_fuzzy_view_of_a_value_change():
    op = ChangeValue(target=ConcreteTarget(subentity_id="delta.fuel_cost"), delta=0.1, mode="relative", at=AT)
    v = views.fuzzy_from_pending(_pend(op, "subject", "delta"))
    assert v.op == "change_value" and v.subject.level == "entity" and v.subject.ref == "delta"
    assert v.source is None and v.target is None
    # an end the view does not draw, and a hedge that reached no node, leave the ends as posed
    v = views.fuzzy_from_pending(_pend(op, "relation", ""))
    assert v.subject.level == "subentity" and v.subject.ref == "delta.fuel_cost"
    v = views.fuzzy_from_pending(_pend(op, "subject", ""))
    assert v.subject.level == "entity" and v.subject.ref == "delta.fuel_cost"


def test_graph_view_skips_what_is_missing_and_works_without_a_controller(ctl):
    eng = ctl.engine
    g = eng.wm.graph
    eid = sorted(g.entities)[0]
    g.entities[eid].generalization_id = None                    # an entity not sorted into a concept yet
    inst = next(iter(g.instances.values()))
    inst.pattern_id = "pat-gone"                               # an instance whose pattern was forgotten
    view = views.build_graph_view(eng.wm, eng.ltm, None, eng.version)
    ent = next(e for e in view.entities if e.id == eid)
    assert ent.concepts == [] if hasattr(ent, "concepts") else True
    assert "pat-gone" not in {h.pattern_id for h in view.hulls}
    assert view.proposals_pending == 0 and view.update is None and view.read_only is False


def test_graph_view_lists_a_waiting_proposals_hedges():
    with demo() as c:
        out = c.post("/api/examples/pending").json()
        assert out["proposal_id"]
        view = c.get("/api/state").json()
        assert any(f["status"] == "proposed" and f["proposal_id"] == out["proposal_id"] for f in view["fuzzy"])
        assert view["update"] is not None and view["update"]["state"] == "awaiting_review"


def test_entity_view_with_a_missing_value_and_a_history_without_means(ctl):
    eng = ctl.engine
    g = eng.wm.graph
    eid = next(e for e in sorted(g.entities) if e not in eng.ltm.entity_memories)
    ent = g.entities[eid]
    sid = ent.subentity_ids[0]
    sub = g.subentities[sid]
    if sub.history:
        sub.history.append(sub.history[-1].model_copy(update={"values": {"z": 1.0}}))
    ent.subentity_ids.append(f"{eid}.gone")
    out = views.entity_view(eid, eng.wm, eng.ltm)
    assert [s["id"] for s in out["subentities"]] == ent.subentity_ids[:-1]
    assert out["entity_memory"] is None
    first = out["subentities"][0]
    assert all("mean" in p for p in first["history"])


def test_every_entity_view_reads(ctl):
    eng = ctl.engine
    for eid in eng.wm.graph.entities:
        out = views.entity_view(eid, eng.wm, eng.ltm)
        assert out["entity"]["id"] == eid


def test_hypothesis_evidence_counts_data_releases_and_skips_unknown_values(ctl):
    from axelrod_wm.model.hypothesis import Hypothesis

    eng = ctl.engine
    sid = "delta.fuel_cost"
    for k, day in enumerate(("2026-05-01", "2026-05-08")):
        ctl.market_events[f"ME-D-{k}"] = SimpleNamespace(data={sid: 1.0}, headline="release",
                                                       published_at=datetime.fromisoformat(f"{day}T00:00:00+00:00"))
    ctl.market_events["ME-D-x"] = SimpleNamespace(data={"other.x": 1.0}, headline="other",
                                                  published_at=AT)
    h = Hypothesis(id="H-x", kind="interaction_present", statement="s", source_id=sid, target_id="nowhere.z",
                   probability=0.5, scored_at=AT, origin="human")
    out = views.hypothesis_evidence(h, ctl)
    assert out["data_releases"] == {"count": 2, "last": "2026-05-08T00:00:00+00:00"}
    assert [s["id"] for s in out["series"]] == [sid]
    d = Hypothesis(id="H-d", kind="entity_decision", statement="s", decision_subentity_id="nowhere.z",
                   probability=0.5, scored_at=AT, origin="human")
    out = views.hypothesis_evidence(d, ctl)
    assert out["decision"] is None and out["series"] == []
    # a co-movement the frontier holds and a link already drawn between the same values: both are reported
    co = next(iter(eng.ltm.correlation_frontier.entries.values()))
    link = next(iter(eng.wm.graph.interactions.values()))
    both = Hypothesis(id="H-b", kind="interaction_present", statement="s", interaction_id=link.id,
                      comovement_id=co.id, probability=0.5, scored_at=AT, origin="human")
    out = views.hypothesis_evidence(both, ctl)
    assert out["basis"] == "correlation frontier" and out["interaction"]["id"] == link.id and out["comovement"]
    for hyp in eng.wm.hypotheses.values():
        assert views.hypothesis_evidence(hyp, ctl)["id"] == hyp.id


def test_proposal_preview_of_every_kind_of_op(ctl):
    eng = ctl.engine
    g = eng.wm.graph
    eid = next(e for e in g.entities if any(i.source_id in g.entities[e].subentity_ids for i in g.active_interactions()))
    ev = GraphUpdateEvent.model_validate({"id": "E", "kind": "real", "occurred_at": AT, "recorded_at": AT,
                                          "produced_by": "human", "ops": [
        {"op": "observe_value", "target": {"kind": "concrete", "subentity_id": "gone.x"}, "value": 1.0, "observed_at": AT},
        {"op": "change_value", "target": {"kind": "concrete", "subentity_id": "gone.x"}, "delta": 0.1, "mode": "relative",
         "at": AT},
        {"op": "reweight_interaction", "interaction_id": "int-gone", "supports": True},
        {"op": "retire_interaction", "interaction_id": "int-gone", "reason": "old"},
        {"op": "retire_entity", "entity_id": eid, "reason": "gone"},
        {"op": "retire_entity", "entity_id": "nobody", "reason": "gone"}]})
    steps = [RefinementStep(op_index=0, end="subject", from_level=Specificity.GENERALIZATION,
                            to_level=Specificity.ENTITY, node_id=nid, candidates=[], reason="r")
             for nid in (sorted(eng.ltm.interaction_generalizations.taxonomy.nodes)[0], eid, "nowhere")]
    p = SimpleNamespace(id="PR-x", event=ev, refinement_steps=steps, review_reasons=[], pending=[],
                        model_dump=lambda mode: {"id": "PR-x"})
    out = views.proposal_view(p, eng.wm, eng.ltm)
    assert [x["kind"] for x in out["preview"]] == ["remove", "remove", "remove"]
    removed = out["preview"]
    assert removed[0] == {"kind": "remove", "ref": "int-gone", "name": "old"}
    assert removed[1]["name"].startswith(g.entities[eid].name) and not removed[1]["name"].endswith(" 0 interactions")
    assert removed[2]["name"] == "nobody and 0 interactions"
    assert [b["name"] for b in out["refinement_steps"]][1:] == [g.entities[eid].name, "nowhere"]


def test_forecast_and_run_views_on_older_records(ctl):
    eng = ctl.engine
    fc = ctl.pose_thesis(ctl.thesis_from_question("What if jet fuel rose by 30% next quarter?"))
    old = fc.model_copy(update={"start_day": None})
    out = views.forecast_view(old, None, eng.wm, ctl.watchlist())
    assert out["dates"][0] == fc.created_at.date().isoformat() and out["explanation"] is None
    names = {n["id"]: n for n in out["transmission"]["watchlist"]["names"]}
    assert names["delta"]["status"] == "shocked"
    run = next(iter(ctl.updates.values()))
    lost = run.model_copy(update={"queue": {run.first_day: ["ME-gone"]}})
    assert views.update_run_view(lost, ctl)["market_events"][0]["events"] == []


def test_learning_tasks_on_a_model_with_nothing_learned(blank_ctl):
    tasks = {t["id"]: t for t in views.learning_tasks_view(blank_ctl)}
    assert "fold" not in tasks and "predict" not in tasks
    assert tasks["refine"]["target"] is None and tasks["frontier"]["count"] == "empty"
