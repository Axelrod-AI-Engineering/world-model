"""The scenario checklist (§15.3). A short run of the mini scenario records what it can for real (load, ME-01,
ME-02, restore, update runs, daily propagation); each later item is checked against a small stand-in of the
controller, both when it holds and when it does not."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace as NS

import pytest

from axelrod_wm.repo.review import ProposalKind
from axelrod_wm.sim import checklist as ck
from axelrod_wm.sim.checklist import N_ITEMS, ChecklistRecorder
from axelrod_wm.sim.runner import StepReport

T0 = datetime(2026, 3, 30, 18, tzinfo=UTC)


# ---------------------------------------------------------------------------------------------------------------
# a real run
# ---------------------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def ran(tmp_path_factory):
    import yaml

    from axelrod_wm.repo.snapshots import MemoryBackend
    from axelrod_wm.sim.runner import ScenarioRunner
    from axelrod_wm.sim.scenario import ScenarioScript

    root = tmp_path_factory.mktemp("ck")
    (root / "regimes.yaml").write_text("regimes: []\n")
    raw = yaml.safe_load(open("data/scenarios/oil_shock_demo/scenario.yaml"))
    raw["initialization"]["history"]["from"] = "2026-01-19"
    raw["initialization"]["history"]["regimes"] = str(root / "regimes.yaml")
    raw["steps"] = [{"at": "2026-01-26T00:00:00Z"}, {"at": "2026-01-28T20:00:00Z", "update": {}},
                    {"at": "2026-02-02T14:00:00Z", "update": {}}]
    r = ScenarioRunner(None, None, ScenarioScript.model_validate(raw), False, auto_approve=True,
                       storage=MemoryBackend(), cache_dir=root / "cache")
    r.recorder = ChecklistRecorder()
    r.load()
    r.reset()                                           # attaching again replaces the recorder's listeners
    r.play()
    return r


def test_a_short_run_records_the_items_it_reaches(ran):
    rec = ran.recorder
    assert [fn for fn in ran.listeners if getattr(fn, "__self__", None) is rec] == [rec.on_runner]
    ok = {n: o for n, (_, o, _) in rec.items.items()}
    # load (Figure 1's graph after a week of history), ME-01's stance, ME-02's oil move, and the restore all hold
    assert ok[1] and ok[2] and ok[3] and ok[15]
    assert "counts=True patterns=True loose=True frontier=True" in rec.details()[1]
    assert rec.details()[2].startswith("ops=['change_value']")
    # the run is too short for the rest: no mirror (ME-03), no UG-01, no re-posed T-00, nvidia's capex unmoved
    assert ok[16] is False and "mirror=False" in rec.details()[16] and "repeat_empty=True" in rec.details()[16]
    assert ok[17] is False and rec.details()[17].startswith("observed_days=0")
    assert [x[:3] for x in rec.facts["runs"]] == [(1, ran.update_ids[0], "done"), (2, ran.update_ids[1], "done")]
    out = ran.checklist()
    assert len(out) == N_ITEMS
    assert out[3] == (" 4. item 4: not reached", False) and out[0][0].startswith(" 1. Load") and out[0][1]


# ---------------------------------------------------------------------------------------------------------------
# a stand-in controller
# ---------------------------------------------------------------------------------------------------------------
class Graph:
    def __init__(self, interactions=None, instances=None, subentities=None, entities=None):
        self.interactions = interactions or {}
        self.instances = instances or {}
        self.subentities = subentities or {}
        self.entities = entities or {}

    def interaction_between(self, a: str, b: str) -> list[str]:
        return [i for i, x in sorted(self.interactions.items()) if {x.source_id, x.target_id} == {a, b}]


class Tax:
    def __init__(self, nodes: dict, paths: dict | None = None):
        self.nodes = nodes
        self.paths = paths or {}

    def path_from_root(self, gid: str) -> list[str]:
        return self.paths.get(gid, [gid])


def stand_in(graph: Graph | None = None, **over) -> NS:
    tdiff = NS(stats=NS(support=2.0))
    ltm = NS(correlation_frontier=NS(entries={}),
             object_generalizations=NS(patterns={}, taxonomy=Tax({})),
             interaction_generalizations=NS(taxonomy=Tax({"gen:int:technology_diffusion": tdiff})),
             prior_states=NS(episodes={}))
    eng = NS(wm=NS(graph=graph or Graph(), deviations=NS(z=lambda sid, day: 0.0), pending_refinements={}),
             ltm=ltm, config=NS(refinement=NS(commit_posterior=0.8)), version=7)
    ctl = NS(engine=eng, market_events={}, listeners=[], evaluations={}, decisions={}, theses={}, updates={})
    for k, v in over.items():
        setattr(ctl, k, v)
    return NS(controller=ctl, step_index=3, listeners=[], forecasts_by_thesis={}, script=NS(steps=[None] * 99))


def recorder(runner: NS) -> ChecklistRecorder:
    rec = ChecklistRecorder()
    rec.runner = runner
    return rec


def report(idx: int, mes: list[str] | None = None, notes: list[str] | None = None,
           update_id: str | None = None) -> StepReport:
    return StepReport(step_index=idx, at=T0, update_id=update_id, market_event_ids=mes or [], proposal_ids=[],
                      forecast_ids=[], notes=notes or [])


def proposal(kind, pid="PR-1", **kw) -> NS:
    return NS(kind=kind, id=pid, **kw)


# ---------------------------------------------------------------------------------------------------------------
# controller events
# ---------------------------------------------------------------------------------------------------------------
def test_a_promotion_of_inflation_to_confidence_is_noted_once_and_its_edge_read_when_applied():
    g = Graph()
    r = stand_in(g)
    fr = r.controller.engine.ltm.correlation_frontier.entries
    fr["CM-1"] = NS(earlier_id=ck.CPI, later_id=ck.CONF, support=4.5)
    fr["CM-2"] = NS(earlier_id=ck.OIL, later_id=ck.CPI, support=9.0)
    rec = recorder(r)
    rec.on_controller("proposed", proposal(ProposalKind.FRONTIER_PROMOTION, "PR-2", subject_id="CM-2"))
    rec.on_controller("proposed", proposal(ProposalKind.FRONTIER_PROMOTION, "PR-0", subject_id="CM-gone"))
    assert "promotion" not in rec.facts
    rec.on_controller("proposed", proposal(ProposalKind.FRONTIER_PROMOTION, "PR-1", subject_id="CM-1"))
    r.step_index = 9
    rec.on_controller("proposed", proposal(ProposalKind.FRONTIER_PROMOTION, "PR-9", subject_id="CM-1"))
    assert rec.facts["promotion"] == {"step": 3, "support": 4.5, "proposal": "PR-1"}
    applied = proposal(ProposalKind.FRONTIER_PROMOTION, "PR-1", market_event_id=None)
    g.interactions["e1"] = NS(source_id=ck.CPI, target_id=ck.CONF, edge_type="causal")
    rec.on_controller("applied", applied)
    assert rec.facts["promotion"]["applied_existence"] is None          # no learned edge yet
    g.interactions["e2"] = NS(source_id=ck.CPI, target_id=ck.CONF, edge_type="learned_causal",
                              existence=NS(mean=lambda: 0.25))
    rec.on_controller("applied", applied)
    assert rec.facts["promotion"]["applied_existence"] == 0.25
    rec.on_controller("deferred", applied)                             # other kinds are ignored
    assert set(rec.facts) == {"promotion"}


def admission(pid: str, pattern: NS) -> NS:
    return proposal(ProposalKind.SUPERENTITY_ADMISSION, pid, event=NS(ops=[NS(pattern=pattern)]))


def test_the_export_controls_pattern_is_found_by_its_bound_edge_or_its_relations():
    ctl_edge = NS(source_id=ck.CONTROLS, target_id=ck.CHIPS)
    other = NS(source_id=ck.OIL, target_id=ck.CPI)
    g = Graph(interactions={"x": ctl_edge, "y": other},
              instances={"I1": NS(pattern_id="SE-A", interaction_ids=["gone", "y"]),
                         "I2": NS(pattern_id="SE-B", interaction_ids=["y", "x"])})
    r = stand_in(g)
    rec = recorder(r)
    unrelated = NS(id="SE-A", support=5.0, relations=[NS(source_role="oil", target_role="inflation", target_attr="x")])
    rec.on_controller("proposed", admission("PR-A", unrelated))
    assert "admission" not in rec.facts
    by_edge = NS(id="SE-B", support=4.0, relations=[])
    rec.on_controller("proposed", admission("PR-B", by_edge))
    assert rec.facts["admission"] == {"step": 3, "support": 4.0, "pattern": "SE-B", "proposal": "PR-B"}
    # unbound, but its relations say export controls -> trade flow
    rec2 = recorder(stand_in(Graph()))
    by_rel = NS(id="SE-C", support=6.0, relations=[NS(source_role="legal_regulatory", target_role="cross_border_trade",
                                                      target_attr="trade_flow")])
    rec2.on_controller("proposed", admission("PR-C", by_rel))
    assert rec2.facts["admission"]["pattern"] == "SE-C"
    # applied: admitted, classified under Configuration, and bound
    og = r.controller.engine.ltm.object_generalizations
    og.patterns["SE-B"] = NS(status="admitted", generalization_id="gen:obj:se_b")
    og.taxonomy = Tax({"gen:obj:se_b": NS()}, {"gen:obj:se_b": ["gen:obj:root", "gen:obj:configuration",
                                                                  "gen:obj:se_b"]})
    rec.on_controller("applied", proposal(ProposalKind.SUPERENTITY_ADMISSION, "PR-B", market_event_id=None))
    ad = rec.facts["admission"]
    assert (ad["admitted"], ad["classified"], ad["bound"]) == (True, True, True)
    # a pattern that never made it into long-term memory
    rec2.on_controller("applied", proposal(ProposalKind.SUPERENTITY_ADMISSION, "PR-C", market_event_id=None))
    assert rec2.facts["admission"]["admitted"] is False and rec2.facts["admission"]["classified"] is False
    assert rec2.facts["admission"]["bound"] is False


def test_the_chips_to_capex_refinement_is_noted_and_its_class_read_when_applied():
    g = Graph()
    r = stand_in(g)
    rec = recorder(r)
    ops = [NS(op="observe_value"),
           NS(op="add_interaction", source=NS(subentity_id=ck.OIL), target=NS(subentity_id=ck.CAPEX)),
           NS(op="add_interaction", source=NS(subentity_id=ck.CHIPS), target=NS(subentity_id=ck.CAPEX))]
    rec.on_controller("proposed", proposal(ProposalKind.REFINEMENT, "PR-R", event=NS(ops=ops)))
    rec.on_controller("proposed", proposal(ProposalKind.GRAPH_UPDATE, "PR-G"))
    assert rec.facts == {"refinement": {"step": 3, "proposal": "PR-R"}}
    applied = proposal(ProposalKind.REFINEMENT, "PR-R", market_event_id=None)
    rec.on_controller("applied", applied)
    assert rec.facts["refinement"]["generalization"] is None
    g.interactions["e9"] = NS(source_id=ck.CHIPS, target_id=ck.CAPEX, generalization_id="gen:int:supply_chain")
    rec.on_controller("applied", applied)
    assert rec.facts["refinement"]["generalization"] == "gen:int:supply_chain"


def _shared(top=None, z_before=None, moves=None, analogs=None):
    return NS(shared=NS(recall=NS(superentities=top or [], analogs=analogs or []),
                        parsed=NS(z_before=z_before or {}), analysis=NS(expected_moves=moves or {})),
              fold=NS(day=40))


def test_market_event_items_two_three_and_nine():
    g = Graph(subentities={ck.STANCE: NS(posterior=NS(mean=lambda: 4.74))},
              instances={"I1": NS(pattern_id="HP2", interaction_ids=[])})
    r = stand_in(g, market_events={"ME-01": NS(data={ck.STANCE: 4.75})})
    eng = r.controller.engine
    eng.wm.deviations = NS(z=lambda sid, day: 2.0)
    eng.ltm.prior_states.episodes = {"EP-1": NS(tags=["bank-run-like"]), "EP-2": NS(tags=["calm"])}
    rec = recorder(r)
    me01 = proposal("graph_update", market_event_id="ME-01", event=NS(ops=[NS(op="change_value")]))
    rec.on_controller("applied", me01, result=None)                    # a model edit: no result, no check
    assert 2 not in rec.items
    top = [NS(pattern_id="S8", attention=0.9), NS(pattern_id="S1", attention=0.5)]
    rec.on_controller("applied", me01, result=_shared(top=top))
    assert rec.items[2][1] is True and "top3=['S8', 'S1']" in rec.items[2][2]
    me02 = proposal("graph_update", market_event_id="ME-02")
    rec.on_controller("applied", me02, result=_shared(z_before={ck.OIL: 0.2}, moves={ck.CPI: NS(q50=0.3)}))
    assert rec.items[3][1] is True and rec.items[3][2] == "dz=1.80 cpi=0.3"
    rec.on_controller("applied", me02, result=_shared(z_before={}, moves={}))
    assert rec.items[3] == (rec.items[3][0], False, "dz=2.00 cpi=None")
    me06 = proposal("graph_update", market_event_id="ME-06")
    rec.on_controller("applied", me06, result=_shared(analogs=[NS(episode_id="EP-1"), NS(episode_id="EP-2")]))
    assert rec.items[9][1] is True and rec.items[9][2] == "bound=['HP2'] tags=['bank-run-like', 'calm']"


# ---------------------------------------------------------------------------------------------------------------
# runner events
# ---------------------------------------------------------------------------------------------------------------
def test_update_runs_and_the_dropped_mirror_are_noted():
    runs = {"UPD-1": NS(id="UPD-1", state="done", report=object(), duplicate_ids=["ME-03-mirror"]),
            "UPD-2": NS(id="UPD-2", state="done", report=None, duplicate_ids=[])}
    r = stand_in(get_update=lambda uid: runs[uid])
    rec = recorder(r)
    rec.on_runner("step", report(1, update_id="UPD-1"))
    rec.on_runner("step", report(2, update_id="UPD-2"))
    rec.on_runner("step", report(3))
    assert rec.facts == {"runs": [(1, "UPD-1", "done", True), (2, "UPD-2", "done", False)], "mirror_dropped": True}


def test_me03_chip_exports_and_me04_the_rbi():
    tax = Tax({"gen:obj:central_bank": NS()},
              {"gen:obj:central_bank": ["gen:obj:root", "gen:obj:actor", "gen:obj:monetary_authority",
                                        "gen:obj:central_bank"]})
    g = Graph(subentities={ck.CHIPS: NS(origin="event_parsing", features={"product": "semiconductors"}),
                           "rbi.policy_stance": NS(prior_source_id="gen:obj:central_bank")},
              interactions={"x": NS(source_id=ck.CONTROLS, target_id=ck.CHIPS,
                                    generalization_id="gen:int:trade_restriction"),
                            "f": NS(source_id="interest_rates.india_policy_rate",
                                    target_id="credit_availability.india_bank_funding_cost",
                                    generalization_id="gen:int:policy_rate_to_bank_funding",
                                    prior_source_id="gen:int:policy_rate_to_bank_funding")},
              entities={"rbi": NS(generalization_id="gen:obj:central_bank")})
    r = stand_in(g, market_events={"ME-04": NS(channel="user", update_id="UPD-4")},
                 get_update=lambda uid: NS(id=uid, state="done", report=None, duplicate_ids=[]))
    eng = r.controller.engine
    eng.ltm.object_generalizations.taxonomy = tax
    eng.wm.pending_refinements = {"P1": NS(reached=0, node_id="gen:obj:supply_factor"),
                                  "P2": NS(reached=1, node_id="gen:obj:supply_factor")}
    rec = recorder(r)
    rec.facts["tdiff_support_at_load"] = 1.0
    rec.on_runner("step", report(3, ["ME-03"]))
    assert rec.items[4][1] is True and rec.items[4][2] == "pending=1 tdiff=2.00"
    rec.on_runner("step", report(4, ["ME-04"], update_id="UPD-4"))
    assert rec.items[5][1] is True and "channel=user update=UPD-4" in rec.items[5][2]
    # without chip exports or the RBI, both fail
    bare = recorder(stand_in(market_events={"ME-04": NS(channel="scraper", update_id=None)}))
    bare.on_runner("step", report(3, ["ME-03", "ME-04"]))
    assert bare.items[4][1] is False and bare.items[5][1] is False and "path=[]" in bare.items[5][2]


def test_me09_the_hedge_narrows_to_tech_capex():
    r = stand_in()
    rec = recorder(r)
    rec.on_runner("step", report(10, ["ME-09"]))                       # no hedge on tech capex yet
    assert rec.items[8][1] is False and rec.items[8][2].endswith("support=None")
    hedge = NS(alpha={ck.CAPEX: 9.0, "x": 1.0}, support=2.0,
               posterior=lambda: {ck.CAPEX: 0.85, "x": 0.05, "__open__": 0.1},
               checks=[NS(event_id="GUE-ME-08", market_event_id="ME-08"),
                       NS(event_id="GUE-ME09", market_event_id=None)])
    r.controller.engine.wm.pending_refinements = {"P": hedge}
    rec.on_runner("step", report(10, ["ME-09"]))
    assert rec.items[8][1] is True and "support=2.0" in rec.items[8][2]


def test_ug01_at_step_six_and_the_step_twelve_checks():
    g = Graph(interactions={"h": NS(source_id=ck.HAWK, target_id=ck.YIELDS, origin="human"),
                            "k": NS(source_id=ck.YIELDS, target_id=ck.HAWK, origin="human")})
    rec = recorder(stand_in(g))
    rec.on_runner("step", report(6))
    assert rec.facts["ug01"] is True
    rec2 = recorder(stand_in(Graph(interactions={"k": NS(source_id=ck.YIELDS, target_id=ck.HAWK, origin="human")})))
    rec2.on_runner("step", report(6))
    assert rec2.facts["ug01"] is False
    # step 12: nothing seen yet
    rec.on_runner("step", report(12))
    assert rec.items[6][1] is False and rec.items[7][1] is False and rec.items[6][2] == "None"
    rec.facts["promotion"] = {"step": 11, "support": 3.5, "applied_existence": 0.2}
    rec.facts["admission"] = {"step": 12, "support": 4.0, "admitted": True, "classified": True, "bound": True}
    rec.on_runner("step", report(12))
    assert rec.items[6][1] is True and rec.items[7][1] is True


def forecast(fid: str, rate: float, **kw) -> NS:
    base = {"id": fid, "effect_summary": {ck.RATE: [NS(q50=rate)], ck.CPI: [NS(q50=0.4)]}, "based_on_version": 7,
            "scenarios": [], "networks": [], "decomposition": {}, "explanation_id": None, "summary": {"a": 1}}
    base.update(kw)
    return NS(**base)


def test_t01_its_scenarios_and_a_reproducible_repose():
    s8 = NS(name="S8 tightens", weight=0.6, effect_summary={ck.RATE: [NS(q50=0.5)]}, network_ids=["n1", "n2"])
    s9 = NS(name="S9 holds", weight=0.4, effect_summary={ck.RATE: [NS(q50=0.1)]}, network_ids=["n1"])
    fc = forecast("FC-1", 0.4, scenarios=[s8, s9],
                  networks=[NS(pattern_id="S1", kind="pattern"), NS(pattern_id="S2", kind="pattern"),
                            NS(pattern_id=None, kind="residual")],
                  decomposition={ck.CPI: {"n1": 0.1, "n2": 0.2, "coupling": 0.0}}, explanation_id="EX-1")
    hashes = iter(["h", "h"])
    r = stand_in(forecast=lambda fid: fc, explanation=lambda eid: NS(top_paths=[1, 2, 3]),
                 pose_thesis=lambda th: forecast("FC-2", 0.4, summary=fc.summary, effect_summary=fc.effect_summary),
                 theses={"T-01": object()})
    r.controller.engine.full_state_hash = lambda: next(hashes)
    r.forecasts_by_thesis["T-01"] = "FC-1"
    rec = recorder(r)
    rec.on_runner("step", report(12))                                  # not step 13: T-01 waits
    assert "t01" not in rec.facts
    rec.on_runner("step", report(13))
    assert rec.items[10][1] is True and rec.items[11][1] is True and rec.facts["t01"] == "FC-1"
    assert "rate={'S8 tightens': 0.5, 'S9 holds': 0.1}" in rec.items[10][2] and "pats=['S1', 'S2']" in rec.items[10][2]
    rec.items.pop(10)
    rec.on_runner("step", report(13))                                  # checked once
    assert 10 not in rec.items


def test_t01_without_its_parts_fails():
    fc = forecast("FC-1", 0.4, scenarios=[NS(name="only", weight=1.0, effect_summary={}, network_ids=[])],
                  effect_summary={})
    r = stand_in(forecast=lambda fid: fc, explanation=lambda eid: None,
                 pose_thesis=lambda th: forecast("FC-2", 0.9), theses={"T-01": object()})
    r.controller.engine.full_state_hash = lambda: "h"
    r.forecasts_by_thesis["T-01"] = "FC-1"
    rec = recorder(r)
    rec._check_t01(r)
    assert rec.items[10][1] is False and rec.items[10][2].endswith("cpi=None paths=None")
    assert rec.items[11][1] is False


def test_t02_lowers_the_policy_rate_effect():
    fcs = {"FC-1": forecast("FC-1", 0.5), "FC-2": forecast("FC-2", 0.2), "FC-3": forecast("FC-3", 0.0,
                                                                                       effect_summary={})}
    r = stand_in(forecast=lambda fid: fcs[fid])
    r.forecasts_by_thesis.update({"T-01": "FC-1", "T-02": "FC-2"})
    rec = recorder(r)
    rec.facts["t01"] = "FC-1"
    rec.on_runner("step", report(14))
    assert rec.items[12] == (rec.items[12][0], True, "T-01=0.5 T-02=0.2")
    rec.on_runner("step", report(15))                                  # item 12 is not checked again
    r.forecasts_by_thesis["T-02"] = "FC-3"
    rec.items.pop(12)
    rec.on_runner("step", report(15))
    assert rec.items[12][1] is False and rec.items[12][2] == "T-01=0.5 T-02=None"


def test_evaluation_decision_and_outcome_notes():
    ev = NS(omission_rate=0.1, commission_rate=0.2, crps=0.3, coverage={"50": 0.5, "80": 0.8, "90": 0.9},
            pattern_hits={"S1": [1, 1]})
    dec = NS(id="D-01", state_version=7, outcome=None)
    trace = NS(hash_verified=True, forecasts=[1, 2])
    fcs = {"FC-0": NS(based_on_version=7), "FC-1": NS(based_on_version=7)}
    r = stand_in(evaluations={"EV-1": ev}, decisions={"D-01": dec}, forecast=lambda fid: fcs[fid],
                 trace_decision=lambda did: trace)
    r.forecasts_by_thesis.update({"T-00": "FC-0", "T-01": "FC-1"})
    rec = recorder(r)
    rec.on_runner("step", report(15, notes=["evaluation EV-1"]))
    assert rec.items[13][1] is True and rec.items[13][2].startswith("om=0.10 com=0.20 crps=0.300")
    rec.on_runner("step", report(16, notes=["decision D-01 at version 7"]))
    assert rec.facts["decision"] == {"recorded": True, "trace": True}
    rec.on_runner("step", report(17, notes=["outcome crps 0.5"]))     # no outcome on record yet
    assert rec.items[14][1] is False and rec.items[14][2].endswith("crps=None")
    dec.outcome = NS(crps=0.5)
    rec.on_runner("step", report(17, notes=["outcome crps 0.5"]))
    assert rec.items[14][1] is True
    ev.coverage = {"50": float("nan"), "80": 0.8, "90": 0.9}
    rec.on_runner("step", report(15, notes=["evaluation EV-1"]))
    assert rec.items[13][1] is False


def test_finite_and_the_report_of_unreached_items():
    assert ck._finite(1.0, 2.0) and not ck._finite(1.0, None) and not ck._finite(float("inf"))
    rec = ChecklistRecorder()
    rec._set(3, "three", 1, "d")
    out = rec.evaluate(None)
    assert out[2] == (" 3. three", True) and out[0] == (" 1. item 1: not reached", False) and len(out) == N_ITEMS
    assert rec.details() == {3: "d"}
