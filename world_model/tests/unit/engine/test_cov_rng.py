"""Deterministic random streams."""

from __future__ import annotations

import numpy as np

from axelrod_wm.engine.rng import make_rng, stable_key, substream


def test_stable_key_for_bools_ints_and_strings():
    assert stable_key(True) == 1 and stable_key(False) == 0
    assert stable_key(-1) == 0xFFFFFFFFFFFFFFFF
    assert stable_key("oil") == stable_key("oil") != stable_key("gas")


def test_substream_is_reproducible_and_leaves_the_base_alone():
    base = make_rng(7, "a")
    first = substream(base, "k").random(3)
    assert np.array_equal(first, substream(base, "k").random(3))
    assert np.array_equal(base.random(3), make_rng(7, "a").random(3))
    assert not np.array_equal(first, substream(base, "other").random(3))
