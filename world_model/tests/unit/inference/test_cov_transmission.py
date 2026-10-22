"""Transmission (addition): channels forced off and duplicate edges between the same two values."""

from __future__ import annotations

import numpy as np

from axelrod_wm.dynamics.propagation import Channel
from axelrod_wm.inference.transmission import transmission_map
from axelrod_wm.model.distributions import Beta, Gaussian
from axelrod_wm.model.interaction import EdgeDynamics
from axelrod_wm.model.temporal import KernelSpec

H = 20


def _ch(key, src, tgt, beta, delay=3, forced=None):
    dyn = EdgeDynamics(effect=Gaussian(mu=beta, sigma=0.01),
                       kernel=KernelSpec.model_validate({"delay_days": delay, "lag_days": 2, "duration_days": None}))
    return Channel(interaction_id=key, source_id=src, target_id=tgt, dynamics=dyn, existence=Beta(alpha=9, beta=1),
                   key=key, forced=forced)


def _effect(sid):
    return np.tile(np.linspace(0.0, 0.2, H + 1), (5, 1))


def test_a_channel_forced_off_carries_nothing():
    chans = [_ch("ab", "a", "b", 0.8, forced=False), _ch("ac", "a", "c", 0.5, forced=True)]
    out = transmission_map(["a"], chans, _effect, H)
    assert [e.subentity_id for e in out] == ["c"]
    c = out[0]
    assert c.order == 1 and c.shock_id == "a" and [h.interaction_id for h in c.path] == ["ac"]
    assert c.effect == 0.2 and c.peak == 0.2 and c.peak_day == H and c.material


def test_the_strongest_of_two_edges_between_the_same_values_is_the_path():
    for chans in ([_ch("strong", "a", "b", 0.9, delay=5), _ch("weak", "a", "b", 0.1, delay=1)],
                  [_ch("weak", "a", "b", 0.1, delay=1), _ch("strong", "a", "b", 0.9, delay=5)]):
        (b,) = transmission_map(["a"], chans, _effect, H)
        assert [h.interaction_id for h in b.path] == ["strong"]
        assert b.path[0].effect == 0.9 and b.arrives_day == b.path[0].delay_days
