"""The stage interfaces: abstract contracts, recall attention, and analog pooling of edge dynamics."""

from __future__ import annotations

import pytest

from axelrod_wm.dynamics.propagation import Channel
from axelrod_wm.engine.interfaces import (
    AnalogEvidence,
    Analyzer,
    AttentionPolicy,
    Classification,
    Classifier,
    EventParser,
    PrefilledModel,
    Prefiller,
    Recaller,
    RecallResult,
    ScoredSuperentity,
    TaxonomyGrower,
)
from axelrod_wm.model.distributions import Beta, Gaussian, LogNormal
from axelrod_wm.model.interaction import EdgeDynamics
from axelrod_wm.model.taxonomy import TaxonomyKind
from axelrod_wm.model.temporal import parse_kernel

KERNEL = parse_kernel({"delay_days": 3, "lag_days": 5, "duration_days": None})


class _Parser(EventParser):
    def parse(self, *a, **kw):
        return super().parse(*a, **kw)


class _Classifier(Classifier):
    def classify(self, *a, **kw):
        return super().classify(*a, **kw)


class _Grower(TaxonomyGrower):
    def maybe_split(self, *a, **kw):
        return super().maybe_split(*a, **kw)


class _Attention(AttentionPolicy):
    def select(self, *a, **kw):
        return super().select(*a, **kw)


class _Recaller(Recaller):
    def recall(self, *a, **kw):
        return super().recall(*a, **kw)


class _Prefiller(Prefiller):
    def prefill(self, *a, **kw):
        return super().prefill(*a, **kw)


class _Analyzer(Analyzer):
    def analyze(self, *a, **kw):
        return super().analyze(*a, **kw)


def test_abstract_stages_cannot_be_instantiated():
    for cls in (EventParser, Classifier, TaxonomyGrower, AttentionPolicy, Recaller, Prefiller, Analyzer):
        with pytest.raises(TypeError):
            cls()


def test_abstract_bodies_return_nothing():
    assert _Parser().parse(None, None, None, None, None) is None
    assert _Classifier().classify(TaxonomyKind.OBJECT, "x", False, None, None) is None
    assert _Grower().maybe_split(None, "g", None, None) is None
    assert _Attention().select({"a": 1.0}, 1) is None
    assert _Recaller().recall(None, None, None, None) is None
    assert _Prefiller().prefill(None, None, None, None, None, None) is None
    assert _Analyzer().analyze(None, None, None, None) is None


def test_default_incorporate_adds_nothing():
    c = Classification(item_id="x", taxonomy=TaxonomyKind.OBJECT, path=["root"], prior_source_id="root")
    assert _Classifier().incorporate(c, None, None) == []


def test_attention_of_is_the_highest_for_a_pattern_and_zero_when_absent():
    r = RecallResult(superentities=[ScoredSuperentity(pattern_id="S1", instance_id=None, score=1.0, attention=0.2),
                                    ScoredSuperentity(pattern_id="S1", instance_id="i", score=2.0, attention=0.7),
                                    ScoredSuperentity(pattern_id="S2", instance_id=None, score=1.0, attention=0.9)],
                     analogs=[])
    assert r.attention_of("S1") == 0.7 and r.attention_of("S3") == 0.0


def _model(effect, evidence, noise=None):
    ch = Channel(interaction_id="e1", source_id="a.x", target_id="b.y",
                 dynamics=EdgeDynamics(effect=effect, kernel=KERNEL), existence=Beta(alpha=9, beta=1))
    return PrefilledModel(channels={"e1": ch}, analog_evidence={"e1": evidence}, network_episodes={}, drifts={},
                          instance_ids=[], notes=[], target_noise=noise or {})


def test_dynamics_for_an_unknown_channel_raises():
    with pytest.raises(KeyError):
        _model(Gaussian(mu=0.5, sigma=0.2), []).dynamics_for("e9", {"E1"})


def test_dynamics_for_pools_each_episode_once():
    ev = [AnalogEvidence(episode_id="E1", implied_effect=1.0, weight=1.0, attention=1.0),
          AnalogEvidence(episode_id="E1", implied_effect=-5.0, weight=1.0, attention=1.0),   # a repeat: ignored
          AnalogEvidence(episode_id="E2", implied_effect=9.0, weight=1.0, attention=1.0)]    # not asked for
    m = _model(Gaussian(mu=0.5, sigma=0.2), ev, noise={"e1": 0.1})
    pooled_var = 0.1 ** 2 / 1.0 + 0.1 ** 2
    prec = 1 / 0.04 + 1 / pooled_var
    expected = (0.5 / 0.04 + 1.0 / pooled_var) / prec
    d = m.dynamics_for("e1", {"E1"})
    assert isinstance(d.effect, Gaussian)
    assert d.effect.mu == pytest.approx(expected) and d.effect.sigma == pytest.approx(prec ** -0.5)
    assert m.dynamics_for("e1", set()) is m.channels["e1"].dynamics       # no episodes: the plain posterior


def test_dynamics_for_without_weight_keeps_the_plain_posterior():
    ev = [AnalogEvidence(episode_id="E1", implied_effect=1.0, weight=0.0, attention=1.0)]
    m = _model(Gaussian(mu=0.5, sigma=0.2), ev)
    assert m.dynamics_for("e1", {"E1"}) is m.channels["e1"].dynamics


def test_dynamics_for_a_non_gaussian_effect_refits_its_family():
    base = LogNormal(mu=0.0, sigma=0.3)
    ev = [AnalogEvidence(episode_id="E1", implied_effect=2.0, weight=4.0, attention=1.0)]
    d = _model(base, ev).dynamics_for("e1", {"E1"})
    assert isinstance(d.effect, LogNormal) and d.kernel == KERNEL
    assert d.effect.mean() > base.mean()            # pulled toward the analogs' larger effect


def test_channel_with_keeps_or_overrides_forced():
    ev = [AnalogEvidence(episode_id="E1", implied_effect=1.0, weight=1.0, attention=1.0)]
    m = _model(Gaussian(mu=0.5, sigma=0.2), ev)
    assert m.channel_with("e1", set()).forced is None
    ch = m.channel_with("e1", {"E1"}, forced=True)
    assert ch.forced is True and ch.dynamics.effect.mu > 0.5
