"""A sized link's native slope on invented values ("Acme" units and price): the ratio of native standard units, None for
an unsized link or a missing value, and None for a value without a usable prior."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from axelrod_wm.model.construction import native_slope


def sub(mean: float, scale: float):
    return SimpleNamespace(scale=scale, prior=SimpleNamespace(link="identity", link_moments=lambda: (mean, 1.0)))


def link(source="acme.units", target="acme.revenue", quantified=True, effect=0.5):
    return SimpleNamespace(quantified=quantified, source_id=source, target_id=target,
                           forward=SimpleNamespace(effect=np.array([effect, effect])))


def test_native_slope_is_the_effect_times_the_native_sd_ratio():
    graph = SimpleNamespace(subentities={"acme.units": sub(10.0, 2.0), "acme.revenue": sub(100.0, 8.0)})
    assert native_slope(graph, link()) == 2.0


def test_native_slope_is_none_without_a_size_or_a_value():
    graph = SimpleNamespace(subentities={"acme.units": sub(10.0, 2.0), "acme.revenue": sub(100.0, 8.0)})
    assert native_slope(graph, link(quantified=False)) is None
    assert native_slope(graph, link(source="acme.gone")) is None
    assert native_slope(graph, link(target="acme.gone")) is None


def test_native_slope_is_none_when_a_value_has_no_usable_prior():
    graph = SimpleNamespace(subentities={"acme.units": sub(10.0, 2.0), "acme.revenue": SimpleNamespace(scale=1.0)})
    assert native_slope(graph, link()) is None
    zero = SimpleNamespace(subentities={"acme.units": sub(10.0, 0.0), "acme.revenue": sub(100.0, 8.0)})
    assert native_slope(zero, link()) is None
