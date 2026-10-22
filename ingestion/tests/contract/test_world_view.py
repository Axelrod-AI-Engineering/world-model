"""The world view (axelrod_ingest/contract/world_view.py): frozen records and a deterministic JSON round trip."""

import dataclasses
import json

import pytest
from tests.conftest import acme_graph

from axelrod_ingest.contract.world_view import EntityView, LinkView, ValueView, WorldView


def small() -> WorldView:
    return WorldView(
        entities={"b": EntityView("b", "Beta", "company", aliases=("BT",), region="US", sector="banking",
                                  subentity_ids=("b.x", "b.y")),
                  "a": EntityView("a", "Alpha", "market")},
        values={"b.y": ValueView("b.y", "b", "Beta y", "level", unit="pct", scale=2.5, family="lognormal", mean=1.5, sd=0.25,
                                 aliases=("why",)),
                "b.x": ValueView("b.x", "b", "Beta x", "level")},
        links=(LinkView("l1", "b.x", "b.y"),
               LinkView("l2", "b.y", "b.x", "lifts", fixed=True, effect_mean=-0.5, polarity=-1)))


def test_records_are_frozen():
    v = small()
    with pytest.raises(dataclasses.FrozenInstanceError):
        v.entities["a"].name = "x"                               # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        v.links[0].fixed = False                                 # type: ignore[misc]


def test_json_round_trips_to_an_equal_view_and_equal_bytes():
    v = small()
    again = WorldView.from_json(v.to_json())
    assert again == v and again.to_json() == v.to_json()


def test_json_is_canonical_sorted_by_id_with_sorted_keys_and_no_spaces():
    body = json.loads(small().to_json())
    assert [e["id"] for e in body["entities"]] == ["a", "b"]
    assert [x["id"] for x in body["values"]] == ["b.x", "b.y"]
    assert [i["id"] for i in body["links"]] == ["l1", "l2"]
    text = small().to_json()
    assert ": " not in text and ", " not in text and list(body["entities"][0]) == sorted(body["entities"][0])


def test_the_same_view_built_in_another_order_gives_the_same_json():
    v = small()
    shuffled = WorldView(entities=dict(reversed(list(v.entities.items()))), values=dict(reversed(list(v.values.items()))),
                         links=tuple(reversed(v.links)))
    assert shuffled.to_json() == v.to_json()


def test_the_acme_fixture_is_a_world_view_that_round_trips():
    v = acme_graph()
    assert v.entities and v.values and v.links
    assert WorldView.from_json(v.to_json()) == v
