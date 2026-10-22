"""The example catalogs: lookups by id or number, and the operation helpers."""

from __future__ import annotations

import pytest

from axelrod_wm.sim.examples.catalog import FIRM, link, value
from axelrod_wm.sim.examples.prod import PROD
from axelrod_wm.sim.examples.small import SMALL


def test_lookups():
    assert SMALL.example("1").id == "create" and SMALL.index("links") == 1
    assert SMALL.event("rumor").after == "ripple"
    with pytest.raises(KeyError, match="unknown example 'nope'"):
        SMALL.example("nope")
    with pytest.raises(KeyError, match="unknown library event 'nope'"):
        PROD.event("nope")


def test_a_value_without_a_typical_level_has_no_prior():
    op = value("delta", "seats", "Delta seats", "capacity", "seats", new_entity=False)
    assert op["entity"] == "delta" and op["temp_id"] == "new:delta.seats"
    assert "prior" not in op and "scale" not in op
    with_prior = value("jet", "price", "Jet fuel price", "commodity_price", "$/gal", "lognormal", 2.5, 0.09)
    assert with_prior["entity"] == "new:jet" and with_prior["scale"] == 0.09 and with_prior["prior"]


def test_a_link_with_dynamics_is_stated_firmly():
    assert "existence" not in link("a.x", "b.y", "moves", 1)
    firm = link({"kind": "abstract", "mention": "x"}, "b.y", "moves", -1, {"effect": {}})
    assert firm["existence"] == FIRM and firm["source"] == {"kind": "abstract", "mention": "x"}
