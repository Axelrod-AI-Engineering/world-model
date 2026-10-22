"""Prefill on a hand-built graph: the focus, instances' channels, analog evidence pooled from siblings,
drifts, and the plain prefiller."""

from __future__ import annotations

from datetime import date

import pytest

from axelrod_wm.engine.interfaces import RecallResult, ScoredEpisode, ScoredSuperentity
from axelrod_wm.events.graph_update import EventKind
from axelrod_wm.memory.long_term import Episode
from axelrod_wm.memory.working import DeviationPoint, point_key
from axelrod_wm.model.distributions import Gaussian
from axelrod_wm.model.superentity import SuperentityInstance
from axelrod_wm.model.taxonomy import Generalization, Taxonomy, TaxonomyKind
from axelrod_wm.shared.prefill import AnalogEmpiricalBayesPrefiller, NonePrefiller, focus_of, level_drift
from axelrod_wm.shared.process import ParsedEvent
from axelrod_wm.shared.recognize import InductionResult
from tests.unit.dynamics.kit import NOW, tiny_engine
from tests.unit.model.graphkit import T0, inter, small_graph


def _episode(eid, response=None, edges=None, tags=(), patterns=()):
    return Episode(id=eid, day=date(1970, 1, 10), trigger_event_ids=[], routine=False, signature=set(),
                   key_signature=set(), deltas={}, edge_effects=edges or {}, response_effects=response or {},
                   active_interaction_ids=[], active_pattern_ids=list(patterns), tags=list(tags))


def _parsed(kind=EventKind.HYPOTHETICAL, touched=(), shocks=()):
    return ParsedEvent(event_id="E", kind=kind, event_type=None, day=20, processing_day=20, shocks=list(shocks),
                       observations=[], touched_subentity_ids=list(touched), touched_entity_ids=[], new_entity_ids=[],
                       new_interaction_ids=[], touched_interaction_ids=[])


def _engine():
    g = small_graph()
    g.interactions["int-1"].generalization_id = "g:int"
    g.interactions["int-1"].forward.effect = Gaussian(mu=0.8, sigma=0.5)
    g.interactions["int-3"] = inter("int-3", "a.x", "c.w", 0.3, generalization_id="g:int")
    g.interactions["int-4"] = inter("int-4", "c.w", "b.z", -0.3, generalization_id="g:int")   # the other sign
    g.interactions["int-old"] = inter("int-old", "c.w", "a.x", 0.3, retired_at=T0)
    g.instances["inst-1"] = SuperentityInstance(id="inst-1", pattern_id="pat-1", bindings={"r": "a"},
                                                interaction_ids=["int-1", "int-gone", "int-old"],
                                                absent_interaction_ids=["int-4"])
    z = {"a.x": [0.0] * 41, "c.w": [0.0] * 41}
    eng = tiny_engine(g, z=z, today=40)
    dev = eng.wm.deviations
    dev.points[point_key("c.w", 40)] = DeviationPoint(z=0.8, var=0.1, level=0.6)       # moved 0.8 over the window
    dev.points[point_key("a.x", 40)] = DeviationPoint(z=0.0, var=0.1, level=5.0)       # a level drift, clipped
    eng.ltm.interaction_generalizations.taxonomy = Taxonomy(kind=TaxonomyKind.INTERACTION, root_id="g:int", nodes={
        "g:int": Generalization(id="g:int", kind=TaxonomyKind.INTERACTION, name="int", parent_id=None,
                                instance_ids=["int-1", "int-3", "int-4", "int-gone"])})
    eps = eng.ltm.prior_states.episodes
    eps["EP-1"] = _episode("EP-1", response={"int-3": (0.6, 2.0), "int-4": (-9.0, 5.0)}, tags=["oil-like"],
                           patterns=["pat-1"])
    eps["EP-2"] = _episode("EP-2", edges={"int-1": (0.9, 0.0)})
    eps["EP-3"] = _episode("EP-3", response={"int-3": (0.5, 0.0)})
    eps["EP-4"] = _episode("EP-4", response={"int-1": (2.0, 50.0)})
    return eng


def _recall(*eps, instances=()):
    return RecallResult(superentities=[ScoredSuperentity(pattern_id="pat-1", instance_id=i, score=1.0, attention=1.0)
                                       for i in instances],
                        analogs=[ScoredEpisode(episode_id=e, score=1.0, attention=1.0 / len(eps),
                                               shared_generalizations=[]) for e in eps])


def test_level_drift():
    eng = _engine()
    assert level_drift(eng.wm, "c.w", 40, 10, 1.0) == pytest.approx(0.06)
    assert level_drift(eng.wm, "a.x", 40, 10, 0.1) == 0.1
    assert level_drift(eng.wm, "b.y", 40, 10, 1.0) == 0.0
    assert level_drift(eng.wm, "c.w", 40, 0, 1.0) == 0.0


def test_focus_without_shocks_adds_the_movers_and_the_watch_list():
    eng = _engine()
    ctx = eng.context(learn=False, now=NOW)
    ctx.notes["targets"] = ["b.z", "ghost", "a.x"]
    focus = focus_of(_parsed(touched=["a.x"]), eng.wm, ctx)
    assert focus[:2] == ["a.x", "b.z"] and "c.w" in focus and "ghost" not in focus


def test_real_event_without_shocks_gets_an_empty_model():
    eng = _engine()
    ctx = eng.context(learn=True, now=NOW)
    m = AnalogEmpiricalBayesPrefiller().prefill(_parsed(EventKind.REAL), _recall(), InductionResult(
        bound_instance_ids=["inst-1"]), eng.wm, eng.ltm, ctx)
    assert m.channels == {} and m.instance_ids == ["inst-1"]


def test_prefill_pools_analogs_and_drifts():
    eng = _engine()
    ctx = eng.context(learn=False, now=NOW)
    recall = _recall("EP-1", "EP-2", "EP-3", "EP-missing", instances=["inst-1", "inst-ghost"])
    m = AnalogEmpiricalBayesPrefiller().prefill(_parsed(touched=["b.y", "nowhere.q"]), recall, InductionResult(),
                                                eng.wm, eng.ltm, ctx)
    assert m.instance_ids == ["inst-1", "inst-ghost"]
    assert {"int-1", "int-2", "int-2:rev", "int-3", "int-4"} <= set(m.channels) and "int-old" not in m.channels
    # int-1 has no response of its own in EP-1; its positive sibling int-3 stands in (int-4 has the other sign)
    ev = m.analog_evidence["int-1"]
    assert [(e.episode_id, e.implied_effect, e.weight) for e in ev] == [("EP-1", 0.6, 2.0)]
    assert "int-2" not in m.analog_evidence                   # no generalization: no siblings
    assert m.network_episodes == {"inst-1": ["EP-1"]}
    assert m.drifts["a.x"] == pytest.approx(float(ctx.config.prefill.max_drift_per_day))
    assert m.target_noise["int-1"] == pytest.approx(0.15)
    assert m.recalled_episode_ids == ["EP-1", "EP-2", "EP-3", "EP-missing"]
    (note,) = [n for n in m.notes if n.startswith("int-1 ")]
    assert note.startswith("int-1 effect 0.80 -> 0.6") and note.endswith("from 1 oil-like analogs")


def test_prefill_notes_an_untagged_adjustment():
    eng = _engine()
    ctx = eng.context(learn=False, now=NOW)
    m = AnalogEmpiricalBayesPrefiller().prefill(_parsed(touched=["b.y"]), _recall("EP-4"), InductionResult(),
                                                eng.wm, eng.ltm, ctx)
    (note,) = [n for n in m.notes if n.startswith("int-1 ")]
    assert note.startswith("int-1 effect 0.80 -> ") and note.endswith("from 1 analogs")


def test_none_prefiller_uses_no_analogs_or_trends():
    eng = _engine()
    ctx = eng.context(learn=False, now=NOW)
    m = NonePrefiller().prefill(_parsed(touched=["b.y"]), _recall("EP-1"), InductionResult(), eng.wm, eng.ltm, ctx)
    assert m.analog_evidence == {} and m.drifts == {} and m.notes == [] and m.channels
