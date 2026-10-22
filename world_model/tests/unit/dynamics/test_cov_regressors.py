"""Regressor helpers on a tiny engine: moderators, phi lookups, channels, systems, bounds, frames."""

from __future__ import annotations

import math
from datetime import timedelta

import numpy as np
import pytest

from axelrod_wm.dynamics import regressors as R
from axelrod_wm.dynamics.kernels import KernelRecursion
from axelrod_wm.dynamics.propagation import PropagationResult
from axelrod_wm.memory.working import ChannelState
from axelrod_wm.model.distributions import Gaussian, LogNormal
from axelrod_wm.model.entity import EconomicConstraint
from axelrod_wm.model.interaction import ParameterBinding, ParameterForm
from axelrod_wm.trace import Phase
from tests.unit.dynamics.kit import NOW, ListTracer, tiny_engine
from tests.unit.model.graphkit import small_graph, sub


def _param(form, gamma=0.5, thr=None, mod="c.w"):
    return ParameterBinding(name="m", moderator_id=mod, form=form, coefficient=Gaussian(mu=gamma, sigma=0.0),
                            threshold=thr)


def _ctx(eng, **kw):
    return eng.context(learn=True, now=NOW, **kw)


def test_config_readers():
    eng = tiny_engine()
    ctx = _ctx(eng)
    assert R.min_delay_of(ctx) == 1 and R.clip_of(ctx) == (0.0, 3.0)
    assert R.horizon_for(ctx) == int(ctx.config.time.horizon_days)
    ctx.notes["horizon_days"] = 9
    assert R.horizon_for(ctx) == 9
    eng2 = tiny_engine(propagation={"min_delay_days": 0})
    assert R.min_delay_of(_ctx(eng2)) == 1


def test_moderator_terms_all_forms():
    eng = tiny_engine(z={"c.w": [0.0] * 4 + [2.0]})
    dev = eng.wm.deviations
    # the moderator's z is read on day - 1 = 4
    assert R.moderator_terms([], dev, 5, (0.0, 3.0)) == (1.0, 0.0)
    assert R.moderator_terms([_param(ParameterForm.MULTIPLICATIVE)], dev, 5, (0.0, 3.0)) == (2.0, 0.0)
    assert R.moderator_terms([_param(ParameterForm.MULTIPLICATIVE, gamma=5.0)], dev, 5, (0.0, 3.0)) == (3.0, 0.0)
    assert R.moderator_terms([_param(ParameterForm.THRESHOLD)], dev, 5, (0.0, 3.0)) == (1.0, 0.0)
    assert R.moderator_terms([_param(ParameterForm.THRESHOLD, thr=2.5)], dev, 5, (0.0, 3.0)) == (0.0, 0.0)
    assert R.moderator_terms([_param(ParameterForm.ADDITIVE, gamma=0.25)], dev, 5, (0.0, 3.0)) == (1.0, 0.5)
    assert R.moderator_terms([_param(ParameterForm.THRESHOLD)], dev, 3, (0.0, 3.0)) == (0.0, 0.0)   # z = 0 is not > 0


def test_phi_at_prefers_state_then_record_then_warm_start():
    eng = tiny_engine(z={"a.x": [1.0] * 21})
    wm = eng.wm
    dyn = wm.graph.interactions["int-1"].forward       # delay 7, lag 14, permanent
    warm = R.warm_recursion(dyn, "a.x", wm, 20)
    assert (warm.d, warm.l, warm.lam) == (7, 14, 1.0)
    assert warm.phi() == pytest.approx(1.0)               # 14 days of z = 1 in the boxcar, divided by l
    assert R.phi_at(wm, "int-1", "a.x", dyn, 20) == pytest.approx(1.0)
    wm.channel_phi["int-1|20"] = 0.3
    assert R.phi_at(wm, "int-1", "a.x", dyn, 20) == 0.3
    wm.channels["int-1"] = ChannelState(channel_id="int-1", recursion=KernelRecursion(d=1, l=2, lam=1.0, S=1.0), day=20)
    assert R.phi_at(wm, "int-1", "a.x", dyn, 20) == 0.5
    assert R.phi_at(wm, "int-1", "a.x", dyn, 19) == pytest.approx(13 / 14)   # state on another day: warm start
    assert R.warm_recursion(dyn, "a.x", wm, 20, multiplier=0.5).l == 7


def test_channel_regressor_moderates_only_the_forward_channel():
    g = small_graph()
    g.interactions["int-2"].parameters = [_param(ParameterForm.ADDITIVE, gamma=1.0, mod="a.x")]
    eng = tiny_engine(g, z={"a.x": [0.0] * 19 + [0.4, 0.4], "b.y": [1.0] * 21})
    ctx = _ctx(eng)
    inter = eng.wm.graph.interactions["int-2"]
    eng.wm.channel_phi["int-2|20"] = 2.0
    eng.wm.channel_phi["int-2:rev|20"] = 3.0
    assert R.channel_regressor(eng.wm, inter, "int-2", "b.y", inter.forward, 20, ctx) == (2.0, pytest.approx(0.4))
    assert R.channel_regressor(eng.wm, inter, "int-2:rev", "b.z", inter.reverse, 20, ctx) == (3.0, 0.0)


def test_obs_and_level_noise():
    eng = tiny_engine()
    ctx = _ctx(eng)
    wm = eng.wm
    s = wm.graph.subentities["a.x"]
    assert R.obs_noise_of(s.model_copy(update={"obs_noise": 0.07}), wm, eng.vocab) == 0.07
    assert R.obs_noise_of(s, wm, eng.vocab) == pytest.approx(0.05)         # policy_rate is a rate
    wm.decision_variables = ["a.x"]
    assert R.obs_noise_of(s, wm, eng.vocab) == 0.02
    assert R.level_noise_of(s, ctx) == float(ctx.config.learning.level_process_noise)
    assert R.level_noise_of(s.model_copy(update={"level_noise": 0.3}), ctx) == 0.3


def test_channel_of_and_graph_channels():
    g = small_graph()
    g.interactions["int-2"].parameters = [_param(ParameterForm.MULTIPLICATIVE)]
    eng = tiny_engine(g)
    wm = eng.wm
    i2 = wm.graph.interactions["int-2"]
    fwd = R.channel_of(i2, "int-2", "b.y", "b.z", i2.forward, forced=True)
    rev = R.channel_of(i2, "int-2:rev", "b.z", "b.y", i2.reverse)
    assert fwd.parameters and fwd.forced is True and fwd.channel_key == "int-2"
    assert rev.parameters == [] and rev.channel_key == "int-2:rev" and rev.existence == i2.existence
    chans = R.graph_channels(wm)
    assert sorted(chans) == ["int-1", "int-2", "int-2:rev"]
    assert sorted(R.graph_channels(wm, {"int-2:rev"})) == ["int-2:rev"]
    del wm.graph.subentities["a.x"]
    assert sorted(R.graph_channels(wm)) == ["int-2", "int-2:rev"]


def test_initial_states_and_build_system():
    g = small_graph()
    g.subentities["a.x"].level_noise = 0.2
    g.interactions["int-1"].parameters = [_param(ParameterForm.MULTIPLICATIVE, mod="c.w")]
    g.subentities["b.y"].constraint = EconomicConstraint(max=1.0)
    eng = tiny_engine(g, z={"a.x": [0.0] * 20 + [0.7]})
    ctx = _ctx(eng)
    init = R.initial_states(["a.x", "b.y", "ghost"], eng.wm, ctx, {"b.y": 0.01})
    assert init["a.x"].z_now == 0.7 and init["a.x"].level_noise == 0.2 and init["a.x"].drift == 0.0
    assert init["b.y"].drift == 0.01 and init["b.y"].level_noise is None
    assert init["ghost"].z_now == 0.0 and init["ghost"].level_noise is None
    assert R.initial_states(["a.x"], eng.wm, ctx)["a.x"].drift == 0.0
    chans = list(R.graph_channels(eng.wm).values())
    system = R.build_system(chans, eng.wm, ctx, 30, extra_subentities=["c.w", "ghost", "a.x"])
    assert system.subentity_ids == ["a.x", "b.y", "c.w", "b.z"]
    assert system.horizon_days == 30 and system.today == 20 and system.min_delay_days == 1
    assert system.bounds == {"b.y": (None, 1.0)}
    system2 = R.build_system(chans[:1], eng.wm, ctx, 5, extra_subentities=["b.z"])
    assert system2.subentity_ids == ["a.x", "b.y", "c.w", "b.z"]
    chans[0].parameters.append(_param(ParameterForm.ADDITIVE, mod="b.y"))      # a moderator already listed
    assert R.build_system(chans[:1], eng.wm, ctx, 5).subentity_ids == ["a.x", "b.y", "c.w"]


def test_standard_bounds_through_the_link():
    g = small_graph()
    price = sub("c.w", "price", constraint=EconomicConstraint(min=50.0, max=float("inf")))
    price = price.model_copy(update={"prior": LogNormal(mu=math.log(80.0), sigma=0.1),
                                     "posterior": LogNormal(mu=math.log(80.0), sigma=0.1),
                                     "anchor": math.log(80.0), "scale": 0.1})
    g.subentities["c.w"] = price
    g.subentities["b.z"].constraint = EconomicConstraint()
    eng = tiny_engine(g)
    out = R.standard_bounds(["a.x", "b.z", "c.w", "ghost"], eng.wm)
    assert list(out) == ["c.w"]
    lo, hi = out["c.w"]
    assert lo == pytest.approx((math.log(50.0) - math.log(80.0)) / 0.1) and hi is None


def test_days_until():
    eng = tiny_engine()
    ctx = _ctx(eng)
    assert R.days_until(ctx, None) == 1 and R.days_until(ctx, None, minimum=3) == 3
    assert R.days_until(ctx, NOW + timedelta(days=5)) == 5
    assert R.days_until(ctx, NOW - timedelta(days=5)) == 1


def test_frame_days():
    assert R.frame_days(0, 10) == [0]
    assert R.frame_days(4, 10) == [0, 1, 2, 3, 4]
    assert R.frame_days(100, 5) == [0, 25, 50, 75, 100]
    assert R.frame_days(10, 1) == [0, 10]


def _result(with_contrib=True):
    z = np.zeros((3, 2, 4))
    z[:, 0, 2] = [0.1, 0.2, 0.3]
    z[:, 1, 2] = [0.0, 0.01, 0.02]
    c = np.zeros((3, 1, 4))
    c[:, 0, 2] = [1.0, 1.0, 2.0]
    return PropagationResult({"a.x": 0, "b.y": 1}, {"int-1": 0}, z, c if with_contrib else None)


def test_frame_payload():
    z, flow = R.frame_payload(_result(), 2)
    assert z == {"a.x": 0.2} and flow == {"int-1": 1.0}
    z, flow = R.frame_payload(_result(False), 2, threshold=0.0)
    assert z == {"a.x": 0.2, "b.y": 0.01} and flow == {}


def test_emit_frames_respects_the_tracer():
    tr = ListTracer()
    eng = tiny_engine(tracer=tr, propagation={"max_frames": 2})
    ctx = _ctx(eng)
    tr.events.clear()
    R.emit_frames(ctx, Phase.DAILY, "run-1", None)
    tr.muted = 1
    R.emit_frames(ctx, Phase.DAILY, "run-1", _result())
    tr.muted = 0
    tr.enabled = False
    R.emit_frames(ctx, Phase.DAILY, "run-1", _result())
    assert tr.events == []
    tr.enabled = True
    R.emit_frames(ctx, Phase.DAILY, "run-1", _result(), refs=["x"])
    assert [(k, kw["day"]) for _, k, kw in tr.events] == [("propagation.frame", 0), ("propagation.frame", 3)]
    assert tr.events[0][2]["refs"] == ["x"] and tr.events[0][2]["run_id"] == "run-1"
    R.emit_frames(ctx, Phase.DAILY, "run-2", _result())
    assert tr.events[-1][2]["refs"] == []
    null_eng = tiny_engine()
    R.emit_frames(_ctx(null_eng), Phase.DAILY, "run-1", _result())     # a NullTracer: nothing to do
