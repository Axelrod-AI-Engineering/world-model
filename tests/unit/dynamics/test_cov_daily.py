"""The daily model's helpers and its predict and record steps, on a tiny hand-built engine."""

from __future__ import annotations

import math

import numpy as np
import pytest

from axelrod_wm.dynamics import daily as D
from axelrod_wm.dynamics.kernels import KernelRecursion, phi_direct
from axelrod_wm.memory.working import (
    ActivityRecord,
    ChannelState,
    DeviationPoint,
    RippleJudgment,
    point_key,
)
from axelrod_wm.model.distributions import Beta, Gamma, Gaussian, LogNormal
from axelrod_wm.model.interaction import Direction, ParameterBinding, ParameterForm
from axelrod_wm.model.superentity import SuperentityInstance
from axelrod_wm.model.temporal import Bitemporal, KernelSpec, TimeState
from tests.unit.dynamics.kit import NOW, tiny_engine
from tests.unit.model.graphkit import small_graph


def _ctx(eng, day=None):
    return eng.context(learn=True, now=NOW, processing_day=day)


def _ramp(n=21):
    return [0.1 * d for d in range(n)]


# ----- indexes and small helpers ----------------------------------------------------------------

def test_in_channel_index_channel_sources_and_pair_key():
    g = small_graph()
    g.interactions["int-2"].parameters = [ParameterBinding(name="p", moderator_id="c.w",
                                                           coefficient=Gaussian(mu=1.0, sigma=0.0))]
    idx = D.in_channel_index(g)
    assert sorted(idx) == ["b.y", "b.z"]
    assert [(c.key, c.source, c.side) for c in idx["b.y"]] == [("int-1", "a.x", "forward"),
                                                               ("int-2:rev", "b.z", "reverse")]
    assert idx["b.z"][0].params and idx["b.y"][1].params == []
    src = D.channel_sources(g)
    assert sorted(src) == ["int-1", "int-2", "int-2:rev"] and src["int-2:rev"][:2] == ("b.z", "b.y")
    assert D.pair_key("b", "a") == "a|b" == D.pair_key("a", "b")


def test_state_prior_keeps_bounded_covariances():
    sub = small_graph().subentities["b.y"]
    theta, P = D.state_prior(sub, ["level"], [0.5], [2.0])
    assert theta.tolist() == [0.5] and P.tolist() == [[2.0]]
    sub.state_cov = {"c1|level": 0.3, "c1|c2": 10.0}
    theta, P = D.state_prior(sub, ["level", "c1", "c2"], [0.0, 1.0, 2.0], [1.0, 1.0, 4.0])
    assert P[0, 1] == P[1, 0] == 0.3
    assert P[1, 2] == pytest.approx(0.999 * 2.0)          # clamped to keep P positive definite
    assert P[0, 2] == 0.0


def test_refit_effect_moment_matches():
    g = D.refit_effect(Gaussian(mu=0.0, sigma=1.0), 0.4, 0.09)
    assert isinstance(g, Gaussian) and g.mu == 0.4 and g.sigma == pytest.approx(0.3)
    ln = D.refit_effect(LogNormal(mu=0.0, sigma=0.1), 2.0, 0.5)
    assert isinstance(ln, LogNormal)
    assert ln.mean() == pytest.approx(2.0) and ln.var() == pytest.approx(0.5)      # exact for the lognormal
    ga = D.refit_effect(Gamma(k=2.0, theta=1.0), 3.0, 0.9)
    assert isinstance(ga, Gamma) and ga.k == pytest.approx(1.0 / math.log1p(0.1)) and ga.mean() == pytest.approx(3.0)
    neg = D.refit_effect(LogNormal(mu=0.0, sigma=0.1), -1.0, 0.5)          # no positive mean: link moments as given
    assert neg.mu == -1.0 and neg.sigma == pytest.approx(math.sqrt(0.5))
    b = D.refit_effect(Beta(alpha=2.0, beta=2.0), 0.0, -1.0)
    assert isinstance(b, Beta) and b.mean() == pytest.approx(0.5)


def test_channel_phi_today_lookups():
    eng = tiny_engine()
    wm = eng.wm
    assert D.channel_phi_today(wm, "int-1", 20) == 0.0
    wm.channel_phi["int-1|20"] = 0.25
    assert D.channel_phi_today(wm, "int-1", 20) == 0.25
    wm.channels["int-1"] = ChannelState(channel_id="int-1", recursion=KernelRecursion(d=1, l=4, lam=1.0, S=2.0), day=20)
    assert D.channel_phi_today(wm, "int-1", 20) == 0.5
    assert D.channel_phi_today(wm, "int-1", 21) == 0.0


def test_predict_state_with_moderator_and_ripple():
    g = small_graph()
    g.interactions["int-1"].parameters = [ParameterBinding(name="p", moderator_id="c.w", form=ParameterForm.ADDITIVE,
                                                           coefficient=Gaussian(mu=0.5, sigma=0.0))]
    g.subentities["b.y"].level_mean = 0.1
    eng = tiny_engine(g, z={"c.w": [0.0] * 19 + [2.0]})
    wm = eng.wm
    wm.channel_phi["int-1|20"] = 1.0
    wm.ripple_judgments["E|b.y"] = RippleJudgment(event_id="E", subentity_id="b.y", weight=0.5, start_day=19,
                                                  path=[0.2, 0.4])
    chans = D.in_channel_index(wm.graph)["b.y"]
    pred = D.predict_state(wm.graph.subentities["b.y"], chans, wm, 20, (0.0, 3.0))
    assert pred.names == ["level", "int-1", "int-2:rev"]
    # level 0.1 + beta 0.8 * phi 1 + rev 0.2 * phi 0 + additive 0.5 * 2 + ripple (0.5 - 1) * 0.4
    assert pred.z == pytest.approx(0.1 + 0.8 + 1.0 - 0.2)
    assert pred.var == pytest.approx(1.0 + 1e-12 * 1.0)


# ----- time states ------------------------------------------------------------------------------

def test_time_states():
    eng = tiny_engine()
    wm = eng.wm
    assert D.time_state_due([], wm, 20)
    ts = TimeState(at=Bitemporal(valid_at=wm.deviations.day_end(14), recorded_at=NOW), values={})
    assert not D.time_state_due([ts], wm, 20) and D.time_state_due([ts], wm, 21)
    sub = wm.graph.subentities["a.x"]
    p = DeviationPoint(z=0.5, var=0.1, level=0.2, innovation=1.5, observed=True)
    s = D.subentity_time_state(sub, p, NOW, NOW, 20, source_event_id="E", y=0.7)
    assert s.values == {"mean": 0.0, "sd": 1.0, "z": 0.5, "level": 0.2, "day": 20.0, "innovation": 1.5, "y": 0.7}
    assert s.source_event_id == "E"
    plain = D.subentity_time_state(sub, DeviationPoint(z=0.0, var=0.1, level=0.0), NOW, NOW, 3)
    assert "innovation" not in plain.values and "y" not in plain.values
    i1 = wm.graph.interactions["int-1"]
    it = D.interaction_time_state(i1, NOW, NOW, phi=0.3)
    assert it.values["phi"] == 0.3 and it.values["effect_mean"] == 0.8 and it.values["existence_mean"] == 0.9
    assert "phi" not in D.interaction_time_state(i1, NOW, NOW).values


# ----- channel states ---------------------------------------------------------------------------

def test_build_channel_state_recomputes_the_window():
    z = _ramp()
    eng = tiny_engine(z={"a.x": z})
    ctx = _ctx(eng, 20)
    with eng.mutator.begin("t", at=NOW) as txn:
        dyn = eng.wm.graph.interactions["int-1"].forward
        cs = D.build_channel_state(eng.wm, "int-1", "a.x", dyn, 20, ctx, txn)
    ref = phi_direct(7, 14, 1.0, np.array(z))
    assert cs.day == 20 and cs.recursion.phi() == pytest.approx(ref[20])
    # the window (28 days) reaches back to day 0: every day's phi is rewritten with the new kernel
    assert [eng.wm.channel_phi[f"int-1|{t}"] for t in range(20)] == pytest.approx(list(ref[:20]))


def test_window_phi_with_nothing_to_do():
    eng = tiny_engine()
    with eng.mutator.begin("t", at=NOW) as txn:
        D._window_phi(eng.wm, "int-1", "a.x", KernelRecursion(d=1, l=1, lam=1.0), 0, 28, txn)
    assert eng.wm.channel_phi == {}


def test_ensure_channel_states_drops_a_stale_reverse_channel():
    eng = tiny_engine()
    ctx = _ctx(eng, 20)
    i2 = eng.wm.graph.interactions["int-2"]
    with eng.mutator.begin("t", at=NOW) as txn:
        assert D.ensure_channel_states(i2, eng.wm, ctx, txn) == ["int-2", "int-2:rev"]
        txn.update("wm.graph.interactions", "int-2", direction=Direction.UNIDIRECTIONAL, reverse=None)
        assert D.ensure_channel_states(eng.wm.graph.interactions["int-2"], eng.wm, ctx, txn, day=20) == ["int-2"]
    assert sorted(eng.wm.channels) == ["int-2"] and eng.wm.channels["int-2"].day == 20


def test_sync_channel_states_builds_rebuilds_advances_and_drops():
    z = _ramp()
    eng = tiny_engine(z={"a.x": z, "b.y": [0.0] * 21})
    wm = eng.wm
    ctx = _ctx(eng, 20)
    with eng.mutator.begin("t", at=NOW) as txn:
        # a channel that no longer exists, int-1 at day 15 (stale), int-2 with a wrong kernel, int-2:rev ahead
        txn.add("wm.channels", ChannelState(channel_id="ghost", recursion=KernelRecursion(d=1, l=1, lam=1.0), day=1))
        D.build_channel_state(wm, "int-1", "a.x", wm.graph.interactions["int-1"].forward, 15, ctx, txn)
        txn.add("wm.channels", ChannelState(channel_id="int-2", recursion=KernelRecursion(d=2, l=2, lam=1.0), day=20))
        txn.add("wm.channels", ChannelState(channel_id="int-2:rev",
                                            recursion=KernelRecursion(d=7, l=14, lam=1.0), day=25))
        rebuilt = D.sync_channel_states(wm, ctx, txn, 20)
    assert rebuilt == ["int-2", "int-2:rev"]
    assert "ghost" not in wm.channels
    assert wm.channels["int-1"].day == 20
    assert wm.channels["int-1"].recursion.phi() == pytest.approx(phi_direct(7, 14, 1.0, np.array(z))[20])
    assert (wm.channels["int-2"].recursion.d, wm.channels["int-2"].recursion.l) == (7, 14)
    with eng.mutator.begin("t2", at=NOW) as txn:
        assert D.sync_channel_states(wm, ctx, txn, 20) == []        # all current: nothing to do


def test_sync_rebuilds_when_only_the_tail_changes():
    eng = tiny_engine()
    ctx = _ctx(eng, 20)
    with eng.mutator.begin("t", at=NOW) as txn:
        D.ensure_channel_states(eng.wm.graph.interactions["int-1"], eng.wm, ctx, txn)
        txn.update("wm.graph.interactions", "int-1", **{"forward.kernel": KernelSpec.model_validate(
            {"delay_days": 7, "lag_days": 14, "duration_days": 30})})
        assert D.sync_channel_states(eng.wm, ctx, txn, 20) == ["int-1", "int-2", "int-2:rev"]
    assert eng.wm.channels["int-1"].recursion.lam == pytest.approx(math.exp(-0.1))


# ----- predict and record -----------------------------------------------------------------------

def test_predict_adds_process_noise_and_replaces_points():
    eng = tiny_engine(z={"a.x": _ramp()})
    wm = eng.wm
    ctx = _ctx(eng, 20)
    kp = D.KalmanPredict()
    var_before = wm.graph.interactions["int-2"].reverse.effect.var()
    with eng.mutator.begin("t", at=NOW) as txn:
        kp.predict(20, wm, ctx, txn)
    q = float(ctx.config.learning.effect_process_noise) ** 2
    assert wm.graph.interactions["int-1"].forward.effect.var() == pytest.approx(q)
    assert wm.graph.interactions["int-2"].reverse.effect.var() == pytest.approx(var_before + q)
    qa = float(ctx.config.learning.level_process_noise)
    assert wm.graph.subentities["a.x"].level_var == pytest.approx(1.0 + qa * qa)
    assert wm.deviations.point("a.x", 20).z == 0.0            # replaced by the prediction (level 0, no in-channels)
    assert wm.deviations.point("c.w", 20) is not None          # added


def test_predict_without_effect_noise():
    eng = tiny_engine(learning={"effect_process_noise": 0.0})
    with eng.mutator.begin("t", at=NOW) as txn:
        D.KalmanPredict().predict(20, eng.wm, _ctx(eng, 20), txn)
    assert eng.wm.graph.interactions["int-1"].forward.effect.var() == 0.0


def test_record_closes_the_day():
    g = small_graph()
    g.instances["inst-1"] = SuperentityInstance(id="inst-1", pattern_id="p", bindings={"r": "a"},
                                                interaction_ids=["int-1", "int-2"])
    g.instances["inst-0"] = SuperentityInstance(id="inst-0", pattern_id="p", bindings={"r": "a"},
                                                interaction_ids=[])
    g.instances["inst-t"] = SuperentityInstance(id="inst-t", pattern_id="p", bindings={"r": "a"},
                                                interaction_ids=["int-1"], transient=True)
    g.interactions["int-1"].parameters = [ParameterBinding(name="p", moderator_id="c.w",
                                                           coefficient=Gaussian(mu=0.0, sigma=0.0))]
    z = [0.0] * 21 + [0.0] * 30
    for d in range(10, 51):
        z[d] = 3.0                                        # a.x stepped up on day 10
    eng = tiny_engine(g, z={"a.x": z[:50]}, today=49)
    wm = eng.wm
    wm.deviations.points[point_key("b.y", 50)] = DeviationPoint(z=0.4, var=0.2, level=0.0)
    wm.deviations.points[point_key("a.x", 50)] = DeviationPoint(z=3.0, var=0.01, level=3.0, observed=True)
    wm.activity_log["49|int-1"] = ActivityRecord(day=49, channel_id="int-1", contribution_change=1.0, target_move=0.0)
    wm.channel_phi["int-2|22"] = 0.0
    ctx = _ctx(eng, 50)
    ts_old = TimeState(at=Bitemporal(valid_at=wm.deviations.day_end(49), recorded_at=NOW), values={})
    wm.graph.subentities["c.w"].history = [ts_old]
    with eng.mutator.begin("t", at=NOW) as txn:
        D.ensure_channel_states(wm.graph.interactions["int-1"], wm, ctx, txn, day=50)
        txn.add("wm.channels", ChannelState(channel_id="gone", recursion=KernelRecursion(d=1, l=1, lam=1.0), day=50))
        moves = D.KalmanPredict().record(50, wm, ctx, txn)
    # b.y had a point: refit from it; c.w had none: predicted and added
    by = wm.graph.subentities["b.y"]
    assert by.posterior.mean() == pytest.approx(0.4) and by.posterior.var() == pytest.approx(0.2)
    assert wm.deviations.point("c.w", 50) is not None
    assert wm.graph.subentities["a.x"].posterior.mean() == 0.0          # observed: not refit here
    assert moves["a.x"] == 0.0 and moves["b.y"] == pytest.approx(0.4)
    assert len(wm.graph.subentities["c.w"].history) == 1                # not due again within the week
    assert len(wm.graph.subentities["b.y"].history) == 1
    assert len(wm.graph.interactions["int-1"].time_states) == 1
    assert "gone" not in wm.channels and wm.channels["int-1"].day == 51
    # int-1's regressor rose over the window; its moderator multiplies by 1 + 0 * z
    rec = wm.activity_log["50|int-1"]
    assert rec.contribution_change == pytest.approx(0.8 * (3.0 - wm.channel_phi["int-1|22"]))
    assert rec.target_id == "b.y" and rec.target_move == pytest.approx(0.4)
    assert "50|int-2" not in wm.activity_log
    assert wm.graph.instances["inst-1"].activation == 0.5
    assert wm.graph.instances["inst-0"].activation == 0.0 and wm.graph.instances["inst-t"].activation == 0.0


def test_activity_warm_starts_the_old_regressor_when_it_was_not_recorded():
    z = [0.0] * 5 + [2.0] * 46
    eng = tiny_engine(z={"a.x": z}, today=49, abduction={"window_days": 10})
    wm = eng.wm
    ctx = _ctx(eng, 50)
    with eng.mutator.begin("t", at=NOW) as txn:
        D.KalmanPredict()._activity(50, wm, ctx, txn, (0.0, 3.0))
    # phi today is 0 (no channel state, nothing recorded); 40 days back it is warm-started from the history
    old = KernelRecursion.warm_start(7, 14, 1.0, wm.deviations.series("a.x"), 40).phi()
    assert old == pytest.approx(2.0)
    assert wm.activity_log["50|int-1"].contribution_change == pytest.approx(0.8 * (0.0 - old))
    assert wm.channel_phi["int-1|50"] == 0.0


def test_activity_early_in_the_history_compares_with_zero_and_skips_recent_time_states():
    eng = tiny_engine(z={"a.x": [1.0] * 21})
    wm = eng.wm
    ctx = _ctx(eng, 20)
    wm.channel_phi["int-1|20"] = 0.5
    recent = TimeState(at=Bitemporal(valid_at=wm.deviations.day_end(19), recorded_at=NOW), values={})
    wm.graph.interactions["int-1"].time_states = [recent]
    with eng.mutator.begin("t", at=NOW) as txn:
        D.KalmanPredict().record(20, wm, ctx, txn)
    # 20 - 28 is before the history: the old regressor counts as 0
    assert wm.activity_log["20|int-1"].contribution_change == pytest.approx(0.8 * 0.5)
    assert wm.graph.interactions["int-1"].time_states == [recent]
    assert len(wm.graph.interactions["int-2"].time_states) == 1


def test_daily_propagator_interface_stubs():
    eng = tiny_engine()
    kp = D.KalmanPredict()
    assert D.DailyPropagator.predict(kp, 0, eng.wm, None, None) is None
    assert D.DailyPropagator.record(kp, 0, eng.wm, None, None) is None
    assert kp.move_threshold == 0.05
