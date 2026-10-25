"""A compartment's memory (api/v1/compartments.py `narrow` and `narrow_ltm`), on the unified demo's engine: what stays in the
working and long-term memory of a compartment over northwind_air, and what is cut."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from axelrod_wm.api.v1.compartments import Compartment, narrow, narrow_ltm
from axelrod_wm.engine.focus import FocusSpec, focus_result
from axelrod_wm.memory.entity_memory import (
    DecisionObservation,
    DecisionProfile,
    EntityMemory,
    EntityMemoryEntry,
)
from axelrod_wm.memory.frontier import CoMovement
from axelrod_wm.memory.working import ForecastLayer, RippleJudgment
from axelrod_wm.model.distributions import DistSummary
from axelrod_wm.model.evidence import Origin
from axelrod_wm.model.explanation import Explanation
from axelrod_wm.model.hypothesis import Hypothesis, HypothesisKind
from axelrod_wm.repo.snapshots import MemoryBackend
from axelrod_wm.sim.runner import build_runner
from axelrod_wm.trace import NullTracer

NOW = datetime(2026, 8, 3, tzinfo=timezone.utc)
COMP = Compartment(id="northwind_focus", title="Northwind", spec=FocusSpec(base="unified_demo", companies=["northwind_air"]))


@pytest.fixture(scope="module")
def engine():
    runner = build_runner("unified_demo", interactive=True, storage=MemoryBackend(), tracer=NullTracer())
    runner.load()
    return runner.controller.engine


class Dump:
    """Something a memory holds by id, with the one method the narrowing reads."""

    def __init__(self, text: str, channel_id: str = "") -> None:
        self.text, self.channel_id = text, channel_id

    def model_dump(self, mode: str = "python") -> dict:
        return {"candidates": {self.text: 1.0}}


def hypothesis(hid: str, source: str, target: str, statement: str = "moves with") -> Hypothesis:
    return Hypothesis(id=hid, kind=HypothesisKind.INTERACTION_PRESENT, statement=statement, source_id=source,
                      target_id=target, probability=0.5, scored_at=NOW, origin=Origin.INFERENCE)


def test_the_working_memory_keeps_the_compartment_and_cuts_the_rest(engine):
    wm = engine.wm.model_copy(update={
        "hypotheses": {"H-in": hypothesis("H-in", "crude_oil.price", "northwind_air.fuel_cost"),
                       "H-by-id": hypothesis("H-by-id", "crude_oil.price", "harbor_steel.operating_profit"),
                       "H-by-name": hypothesis("H-by-name", "crude_oil.price", "jet_fuel.price", "it hits Harbor Steel Works"),
                       "H-other-entity": hypothesis("H-other-entity", "central_bank.policy_rate", "crude_oil.price")},
        "pending_refinements": {"P-in": Dump("jet_fuel"), "P-out": Dump("acme_motors")},
        "ripple_judgments": {"in": RippleJudgment(event_id="E", subentity_id="jet_fuel.price", weight=1.0, start_day=1, path=[0.1]),
                             "out": RippleJudgment(event_id="E", subentity_id="harbor_steel.operating_profit", weight=1.0,
                                                   start_day=1, path=[0.1])},
        "channels": {"n02": SimpleNamespace(channel_id="n02"), "n02:rev": SimpleNamespace(channel_id="n02:rev"),
                     "n04": SimpleNamespace(channel_id="n04")},
        "channel_phi": {"n02|3": 0.5, "n02:rev|3": 0.5, "n04|3": 0.5},
        "activity_log": {"3|n02": SimpleNamespace(channel_id="n02"), "3|n04": SimpleNamespace(channel_id="n04")},
        "fold_accumulators": {"n02": (1.0, 2.0), "n04": (1.0, 2.0)},
        "forecast_layer": ForecastLayer(order=["T-1"]), "episode_buffer": [object()], "source_cursors": {"web": NOW},
        "late_queue": {"PR-1": 3}, "missing_relation_log": {"x": NOW}, "pending_episode_tags": ["tag"]})
    out = narrow(wm, COMP)
    assert set(out.graph.entities) == {"crude_oil", "jet_fuel", "northwind_air"}
    assert set(out.hypotheses) == {"H-in"}
    assert set(out.pending_refinements) == {"P-in"} and set(out.ripple_judgments) == {"in"}
    assert set(out.channels) == {"n02", "n02:rev"} and set(out.channel_phi) == {"n02|3", "n02:rev|3"}
    assert set(out.activity_log) == {"3|n02"} and set(out.fold_accumulators) == {"n02"}
    assert out.forecast_layer.order == [] and out.episode_buffer == [] and out.source_cursors == {}
    assert out.late_queue == {} and out.missing_relation_log == {} and out.pending_episode_tags == []
    # nothing was changed in the memory it was made from
    assert len(wm.graph.entities) == 24 and wm.forecast_layer.order == ["T-1"] and len(wm.hypotheses) == 4


def summary() -> DistSummary:
    return DistSummary(mean=1.0, sd=0.1, q05=0.8, q10=0.85, q25=0.9, q50=1.0, q75=1.1, q90=1.15, q95=1.2)


def test_the_long_term_memory_keeps_the_compartments_concepts_and_values(engine):
    ltm = engine.ltm
    ltm = ltm.model_copy(update={
        "entity_memories": {
            "northwind_air": EntityMemory(
                entity_id="northwind_air",
                entries=[EntityMemoryEntry(at=NOW, subentity_summaries={"northwind_air.fuel_cost": summary(),
                                                                       "harbor_steel.operating_profit": summary()},
                                           z={"northwind_air.fuel_cost": 0.5, "harbor_steel.operating_profit": 0.1})],
                decisions=[DecisionObservation(subentity_id="northwind_air.fuel_cost", at=NOW, change=1.0,
                                               context={"jet_fuel.price": 0.5, "harbor_steel.operating_profit": 0.2}),
                           DecisionObservation(subentity_id="harbor_steel.operating_profit", at=NOW, change=1.0, context={})],
                profiles={"northwind_air.fuel_cost": DecisionProfile(by_context={"jet_fuel.price>+0.75": [1, 0, 0],
                                                                                 "harbor_steel.operating_profit<-0.75": [0, 1, 0]}),
                          "harbor_steel.operating_profit": DecisionProfile()}),
            "harbor_steel": EntityMemory(entity_id="harbor_steel")}})
    frontier = ltm.correlation_frontier.model_copy(update={"entries": {
        "CM-in": CoMovement(id="CM-in", earlier_id="crude_oil.price", later_id="jet_fuel.price", lag_days=3, sign=1,
                            first_seen=NOW, last_seen=NOW, hypothesis_id="H-in"),
        "CM-out": CoMovement(id="CM-out", earlier_id="crude_oil.price", later_id="harbor_steel.operating_profit", lag_days=3,
                             sign=1, first_seen=NOW, last_seen=NOW, hypothesis_id="H-out")}})
    ltm = ltm.model_copy(update={"correlation_frontier": frontier})
    og = ltm.object_generalizations
    ex = Explanation.model_construct(id="EX-1")
    ltm = ltm.model_copy(update={
        "object_generalizations": og.model_copy(update={"super_interaction_labels": {"N1->N1": "keeps", "N1->N2": "drops"}}),
        "prior_states": ltm.prior_states.model_copy(update={"explanations": {"EX-1": ex}})})
    wm = narrow(engine.wm, COMP)
    out = narrow_ltm(ltm, COMP, wm)
    assert set(out.entity_memories) == {"northwind_air"}
    mem = out.entity_memories["northwind_air"]
    assert set(mem.entries[0].subentity_summaries) == {"northwind_air.fuel_cost"} and set(mem.entries[0].z) == {"northwind_air.fuel_cost"}
    assert [d.subentity_id for d in mem.decisions] == ["northwind_air.fuel_cost"]
    assert mem.decisions[0].context == {"jet_fuel.price": 0.5}
    assert set(mem.profiles) == {"northwind_air.fuel_cost"}
    assert set(mem.profiles["northwind_air.fuel_cost"].by_context) == {"jet_fuel.price>+0.75"}
    assert set(out.correlation_frontier.entries) == {"CM-in"}
    assert out.prior_states.explanations == {} and out.prior_states.episodes == {}
    assert set(out.object_generalizations.patterns) == {"N1"}                # N2 names harbor_steel; the seeds name the rest
    assert out.object_generalizations.super_interaction_labels == {"N1->N1": "keeps"}
    nodes = out.object_generalizations.taxonomy.nodes
    held = {i for n in nodes.values() for i in n.instance_ids}
    assert held <= {"crude_oil", "jet_fuel", "northwind_air", "N1"} and "crude_oil" in held
    links = {i for n in out.interaction_generalizations.taxonomy.nodes.values() for i in n.instance_ids}
    assert links <= set(wm.graph.interactions)
    # the memory it was made from is as it was
    assert "EX-1" in ltm.prior_states.explanations and len(og.patterns) == 12


def test_a_focus_names_what_it_removed(engine):
    fr = focus_result(COMP.spec)
    assert fr.leaks("harbor_steel") and fr.leaks({"x": ["harbor_steel.operating_profit"]}) and fr.leaks({"central_bank": 1})
    assert fr.leaks("a note on Harbor Steel Works") and fr.leaks(["m02"])
    assert not fr.leaks({"crude_oil": ["jet_fuel.price", "northwind_air"]}) and not fr.leaks(3)
