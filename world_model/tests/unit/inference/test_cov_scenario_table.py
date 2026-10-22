"""The scenario table (Oct 15): values unknown to the graph, an empty book, and a band with no draws."""

from __future__ import annotations

from types import SimpleNamespace as NS

import numpy as np
import pytest

from axelrod_wm.inference.scenario_table import build_scenario_table, native

H = 10


def _graph():
    subs = {"acme.share_price": NS(entity_id="acme", name="Acme share price", posterior=NS(family="lognormal"),
                                   scale=0.1, unit="USD"),
            "bolt.share_price": NS(entity_id="bolt", name="Bolt share price", posterior=NS(family="lognormal"),
                                   scale=0.1, unit="USD"),
            "rates.policy": NS(entity_id="rates", name="Rates policy rate", posterior=NS(family="gaussian"),
                               scale=0.5, unit="pp")}
    ents = {"acme": NS(name="Acme", subentity_ids=["acme.share_price"]),
            "bolt": NS(name="Bolt", subentity_ids=["bolt.share_price"]),
            "rates": NS(name="Rates", subentity_ids=["rates.policy"])}
    return NS(subentities=subs, entities=ents)


def test_a_value_unknown_to_the_graph_is_read_in_standard_units_only():
    assert native("nowhere.value", 0.12345, _graph()) == {"sd": 0.123}
    assert native("rates.policy", 0.5, _graph()) == {"sd": 0.5, "change": 0.25, "unit": "pp"}


def test_a_book_with_no_name_in_the_graph_has_no_table():
    mix = NS(effect=lambda sid: np.zeros((8, H + 1)))
    assert build_scenario_table(mix, [], ["ghost", "phantom"], _graph(), {}, H) == {}


def test_draws_split_two_ways_leave_the_base_band_empty():
    # half the draws lift the book by 1 sd, half sink it by 1 sd: the quartiles are the two values themselves, so no
    # draw falls strictly between them and the base band holds none
    book = np.array([1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, -1.0])
    paths = {"acme.share_price": book, "bolt.share_price": book, "rates.policy": 0.5 * book}

    def effect(sid):
        out = np.zeros((book.size, H + 1))
        out[:, H] = paths[sid]
        return out

    table = build_scenario_table(NS(effect=effect), [NS(id="SC-1", name="only", weight=1.0)], ["acme", "bolt"],
                                 _graph(), {}, H)
    rows = {r["band"]: r for r in table["rows"]}
    assert rows["Base"] == {"band": "Base", "probability": 0.0, "draws": 0}
    assert rows["Bull"]["probability"] == rows["Bear"]["probability"] == 0.5
    assert rows["Bull"]["book_move"] == 1.0 and rows["Bear"]["book_move"] == -1.0
    assert [f["entity"] for f in rows["Bull"]["favored"]] == ["acme", "bolt"] and rows["Bull"]["hurt"] == []
    assert rows["Bull"]["favored"][0]["pct"] == pytest.approx(10.52, abs=0.01)
    assert rows["Bull"]["mechanism"][0]["value"] == "rates.policy"
    assert table["changes_the_read"]["kind"] == "driver" and table["rival_scenarios"] == []
    assert table["p_book_up"] == table["p_book_down"] == 0.5
