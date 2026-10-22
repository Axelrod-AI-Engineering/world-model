"""Explanations: kernel values, top paths, reach, and the learning and forecast write-ups, on hand-built
inputs (records are stand-ins with only the fields the explainer reads)."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from types import SimpleNamespace as NS

import numpy as np
import pytest

from axelrod_wm.dynamics.propagation import Channel, PropagationResult, ShockInput
from axelrod_wm.events.graph_update import EventKind
from axelrod_wm.model.distributions import Beta, summarize_samples
from axelrod_wm.shared.explain import (
    Explainer,
    PathAttributionExplainer,
    _ancestors,
    _reaches,
    kernel_value,
    top_paths,
)
from axelrod_wm.shared.process import ParsedEvent
from tests.unit.dynamics.kit import NOW, tiny_engine
from tests.unit.model.graphkit import dyn, small_graph

T = datetime(2026, 3, 1, tzinfo=timezone.utc)


def ch(s, t, beta=0.5, delay=2, lag=3, duration=None, existence=9.0, forced=None, key=None):
    return Channel(interaction_id=key or f"{s}>{t}", source_id=s, target_id=t,
                   dynamics=dyn(beta, delay=delay, lag=lag, duration=duration),
                   existence=Beta(alpha=existence, beta=1.0), forced=forced, key=key)


# ----- pure helpers -----------------------------------------------------------------------------

def test_kernel_value_matches_the_step_response():
    c = ch("a", "b", delay=2, lag=3, duration=30)
    assert [kernel_value(c, d) for d in (0, 1)] == [0.0, 0.0]
    assert [kernel_value(c, d) for d in (2, 3, 4)] == pytest.approx([1 / 3, 2 / 3, 1.0])
    assert kernel_value(c, 6) == pytest.approx(math.exp(-0.1) ** 2)
    assert kernel_value(c, 2, min_delay=3) == 0.0


def test_top_paths_gains_and_shares():
    chans = [ch("a", "b", 0.5), ch("b", "c", 0.4), ch("a", "c", 0.1),
             ch("a", "b", 0.2, existence=1.0, key="weaker"),          # a weaker duplicate of a -> b
             ch("c", "a", 0.9, forced=False)]                          # switched off
    paths = top_paths(chans, [("a", 2.0), ("zz", 1.0), ("c", 1.0)], ["c", "a", "nope"], horizon=20, k=1)
    assert len(paths) == 1                                             # c -> a is off; c is its own shock
    p = paths[0]
    assert p.interaction_ids == ["a>b", "b>c"] and p.share == 1.0
    assert p.gain == pytest.approx(2.0 * 0.5 * 0.4)
    both = top_paths(chans, [("a", 1.0)], ["c"], horizon=20, k=3)
    assert [x.interaction_ids for x in both] == [["a>b", "b>c"], ["a>c"]]
    assert sum(x.share for x in both) == pytest.approx(1.0)
    assert top_paths(chans, [("a", 1.0)], ["c"], horizon=20, max_edges=0) == []
    zero = top_paths([ch("a", "b", 0.0)], [("a", 1.0)], ["b"], horizon=20)
    assert zero[0].share == 0.0
    assert top_paths([ch("a", "b"), ch("c", "d")], [("a", 1.0)], ["d"], horizon=5) == []      # no path


def test_top_paths_rescales_strong_edges():
    strong = [ch("a", "b", 3.0, existence=1e6), ch("b", "c", 2.0, existence=1e6)]
    (p,) = top_paths(strong, [("a", 1.0)], ["c"], horizon=50)
    assert p.gain == pytest.approx(6.0)


def test_ancestors_and_reaches():
    g = small_graph()
    assert _ancestors(g, {"b.y"}) == {"b.y", "a.x", "b.z"}              # b.z through the reverse channel
    assert _ancestors(g, {"c.w"}) == {"c.w"}
    reach = {"b.y"}
    assert _reaches(g, "int-1", reach) and not _reaches(g, "int-2", reach) and _reaches(g, "int-2:rev", reach)
    assert _reaches(g, "ghost", set())


def test_explainer_interface_stubs():
    e = PathAttributionExplainer()
    assert Explainer.explain_forecast(e, None, [], [], None, None) is None
    assert Explainer.explain_learning(e, None, None, None, None) is None


# ----- learning ---------------------------------------------------------------------------------

def _parsed(**kw):
    base = dict(event_id="GUE-1", kind=EventKind.REAL, event_type=None, day=20, processing_day=20, shocks=[],
                observations=[], touched_subentity_ids=[], touched_entity_ids=[], new_entity_ids=[],
                new_interaction_ids=[], touched_interaction_ids=[])
    base.update(kw)
    return ParsedEvent(**base)


def _shared(parsed, expected=None, result=None, channels=None, notes=(), superentities=(), analogs=()):
    return NS(parsed=parsed,
              analysis=NS(result=result, expected_moves=expected or {}, horizon_days=10),
              model=NS(channels=channels or {}, notes=list(notes)),
              recall=NS(superentities=list(superentities), analogs=list(analogs)))


def test_explain_learning_minimal_outside_a_transaction():
    eng = tiny_engine()
    ctx = eng.context(learn=True, now=NOW)
    shared = _shared(_parsed())
    fold = NS(effect_changes={}, existence_changes={})
    frontier = NS(logged=[], proposals=[], tested=[])
    ex = PathAttributionExplainer().explain_learning(shared, fold, frontier, ctx)
    assert ex.id == "EX-GUE-1" and ex.text == "GUE-1." and ex.top_paths == [] and ex.key_interactions == []


def test_explain_learning_full():
    g = small_graph()
    g.interactions["int-1"].generalization_id = "gen:int:x"
    eng = tiny_engine(g)
    ctx = eng.context(learn=True, now=NOW)
    pending = NS(candidates={"b.y": 0.5})
    eng.wm.pending_refinements = {"PEND-1": pending, "PEND-2": NS(candidates={"zz.q": 1.0})}
    shocks = [ShockInput(subentity_id="a.x", size=1.0)]
    parsed = _parsed(event_type="news", shocks=shocks, touched_entity_ids=["b", "a", "ghost"],
                     observations=[("a.x", 1.0, 0.1, T)])
    moves = {"b.y": summarize_samples(np.array([0.4, 0.5, 0.6])), "b.z": summarize_samples(np.array([-0.1]))}
    chans = {"int-1": ch("a.x", "b.y", 0.8, key="int-1"), "int-2": ch("b.y", "b.z", -0.4, key="int-2")}
    shared = _shared(parsed, expected=moves, result=object(), channels=chans, notes=["n1"],
                     superentities=[NS(pattern_id="S1")], analogs=[NS(episode_id="EP-1", attention=0.1234567)])
    fold = NS(effect_changes={"int-1": 0.2, "gone": 0.5}, existence_changes={"int-2": 0.1})
    frontier = NS(logged=["CM-1"], proposals=[], tested=["CM-2"])
    with eng.mutator.begin("x", at=NOW):
        ex = PathAttributionExplainer().explain_learning(shared, fold, frontier, ctx)
    assert ex.id.startswith("EX-0")
    assert [i for i, _ in ex.key_interactions] == ["gone", "int-1", "int-2"]
    assert ex.index_keys == {"gen:int:x", "gen:obj:firm", "S1"}
    assert ex.top_paths and ex.top_paths[0].interaction_ids == ["int-1"]
    assert ex.text.startswith("GUE-1 (news); shocks a.x +1.00 sd; 1 observations; expected b.y +0.50 sd")
    assert "largest updates: gone, int-1, int-2" in ex.text and "frontier: 1 logged, 0 proposed" in ex.text
    assert ex.frontier_changes == ["CM-1", "CM-2"] and ex.pending_touched == ["PEND-1"]
    assert ex.analogs == [("EP-1", 0.123457)] and ex.notes == ["n1"]


# ----- forecasts --------------------------------------------------------------------------------

def _summ(values):
    return [summarize_samples(np.array(v, dtype=float)) for v in values]


def _forecast(effect, z=None, decomposition=None, targets=None, H=2):
    return NS(id="FC-1", horizon_days=H, targets=targets if targets is not None else list(effect),
              effect_summary=effect, z_summary=z or {}, decomposition=decomposition or {}, based_on_version=3,
              created_at=T)


def test_explain_forecast_with_no_moves():
    eng = tiny_engine()
    ctx = eng.context(learn=False, now=NOW)
    fc = _forecast({}, targets=["b.y"])
    ex = PathAttributionExplainer().explain_forecast(fc, [], [], _shared(_parsed()), ctx)
    assert ex.text == "No subentity moves by 0.1 standard units or more at the horizon."
    assert ex.id == "EX-FC-1" and ex.state_version == 3 and ex.networks == []


def _coupled(keys, values):
    """A coupled run whose channel contributions at the horizon are `values`."""
    contrib = np.zeros((2, len(keys), 3))
    for c, v in enumerate(values):
        contrib[:, c, 2] = v
    return PropagationResult({}, {k: c for c, k in enumerate(keys)}, np.zeros((2, 0, 3)), contrib)


def test_explain_forecast_ablates_ranks_and_writes_text():
    g = small_graph()
    g.interactions["int-1"].generalization_id = "gen:int:x"
    eng = tiny_engine(g)
    ctx = eng.context(learn=False, now=NOW)
    ctx.notes["coupled"] = {"SC-a": _coupled(["int-1", "int-2", "int-2:rev", "ghost"], [0.5, 0.3, 0.2, 0.9])}
    ctx.notes["ablate"] = lambda top, key: {"b.y": {None: 1.0, "int-1": 0.2}.get(key, 0.9)}
    shocks = [ShockInput(subentity_id="a.x", size=1.0), ShockInput(subentity_id="c.w", size=1.0, intervention=True)]
    net = NS(id="NW-1", name="", channels=[ch("a.x", "b.y", 0.8, key="int-1"), ch("b.y", "b.z", -0.4, key="int-2"),
                                           ch("a.x", "b.y", 0.8, key="int-1")],
             forced_absent=["int-9"], pattern_id="S1")
    other = NS(id="NW-2", name="Other", channels=[ch("c.w", "b.y", key="int-7")], forced_absent=[], pattern_id=None)
    scen = [NS(id="SC-a", name="Main", weight=0.7, network_ids=["NW-1"], forced_existence={"int-2": False},
               branched_hypothesis_ids={"H-1": True, "H-2": False}),
            NS(id="SC-b", name="Alt", weight=0.3, network_ids=["NW-2"], forced_existence={},
               branched_hypothesis_ids={})]
    effect = {"a.x": _summ([[0], [0], [1.0]]), "b.y": _summ([[0], [0], [0.4, 0.5, 0.6]])}
    fc = _forecast(effect, z={"b.y": _summ([[0], [0], [0.5]])},
                   decomposition={"a.x": {"NW-1": 0.3, "NW-2": -0.1, "coupling": 5.0}})   # the largest mover's
    ex = PathAttributionExplainer().explain_forecast(fc, [net, other], scen, _shared(_parsed(shocks=shocks)), ctx)
    # int-1 is the only channel whose removal changes b.y; ghost (not in the graph) is still a candidate
    assert ex.key_interactions[0] == ("int-1", 0.8)                 # base 1.0 less 0.2 without int-1
    assert {i for i, _ in ex.key_interactions} == {"int-1", "int-2", "ghost"}
    assert ex.networks == [("NW-1", 0.75), ("NW-2", 0.25)]
    assert ex.assumptions == ["Main: H-1 holds", "Main: H-2 does not hold", "NW-1 says int-9 is absent"]
    assert ex.index_keys == {"gen:int:x", "gen:obj:firm", "S1"}
    assert ex.scenarios == [("Main", 0.7), ("Alt", 0.3)]
    b_y = g.subentities["b.y"]
    assert ex.text.startswith(f"A.X +1.0 sd moves {b_y.name} by +0.50 usd (+0.42 to +0.58) by Mar 2026"
                              .replace("A.X", g.subentities["a.x"].name))
    assert ", mostly through int-1 (100%)." in ex.text
    assert ex.text.endswith("The leading scenario, Main (70%), is one of 2.")


def test_explain_forecast_without_ablation_or_paths():
    eng = tiny_engine()
    ctx = eng.context(learn=False, now=NOW)
    ctx.notes["coupled"] = {"SC-a": _coupled(["int-1", "int-2"], [0.5, 0.3])}
    scen = [NS(id="SC-a", name="Main", weight=1.0, network_ids=[], forced_existence={}, branched_hypothesis_ids={})]
    effect = {"q.unknown": _summ([[0], [0], [0.3]]), "b.y": _summ([[0], [0], [0.1]])}
    fc = _forecast(effect, decomposition={"q.unknown": {"NW-1": 0.0}})
    ex = PathAttributionExplainer().explain_forecast(fc, [], scen, _shared(_parsed()), ctx)
    assert ex.key_interactions == [("int-1", 0.5), ("int-2", 0.3)]    # by mean contribution, without ablation
    assert ex.text == "The baseline moves q.unknown by +0.30 sd by Mar 2026, mostly through int-1."
    assert ex.networks == [("NW-1", 0.0)]


def test_explain_forecast_with_neither_paths_nor_key_interactions():
    eng = tiny_engine()
    ctx = eng.context(learn=False, now=NOW)
    effect = {"b.y": _summ([[0], [0], [0.3]])}
    fc = _forecast(effect)
    ex = PathAttributionExplainer().explain_forecast(fc, [NS(id="NW-1", name="n", channels=[], forced_absent=[],
                                                              pattern_id=None)], [], _shared(_parsed()), ctx)
    assert ex.text.endswith("by Mar 2026.") and ex.key_interactions == [] and ex.networks == []
