"""A kind's default subentities and links (addition): similar objects have similar subentities."""

from __future__ import annotations

import pytest
import yaml

from axelrod_wm.api.views import build_graph_view
from axelrod_wm.engine.initialize import ConstructionError, ConstructionSpec

SPEC = ConstructionSpec.load("world_model/examples/worlds/economy", "world_model/taxonomy")


def _subs(eid: str) -> dict[str, str]:
    """slot -> subentity id for one entity."""
    e = next(e for e in SPEC.entities if e.id == eid)
    return {s.slot: s.id for s in e.subentities if s.slot}


def test_siblings_get_the_same_slots_in_the_same_order():
    delta = next(e for e in SPEC.entities if e.id == "delta")
    united = next(e for e in SPEC.entities if e.id == "united_airlines")
    assert [s.slot for s in delta.subentities] == [s.slot for s in united.subentities] == [
        "revenue", "operating_margin", "share_price", "fuel_cost", "passenger_traffic", "market_share"]
    assert _subs("united_airlines")["fuel_cost"] == "united_airlines.fuel_cost"      # United gains Delta's fuel cost
    firms = [e for e in SPEC.entities if str(e.kind) == "company"]
    assert len(firms) == 15 and all({"revenue", "operating_margin", "share_price"} <= set(_subs(e.id)) for e in firms)


def test_own_subentities_fill_slots_and_keep_their_ids():
    assert _subs("nvidia")["china_sales"] == "nvidia.china_revenue"   # fills the slot under another id
    nvidia = next(e for e in SPEC.entities if e.id == "nvidia")
    assert [s.id for s in nvidia.subentities if s.slot is None] == [
        "nvidia.datacenter_revenue", "nvidia.gpu_share", "nvidia.capex"]  # its own, last, in its order
    samsung = {s.id: s for e in SPEC.entities if e.id == "samsung" for s in e.subentities}
    assert samsung["samsung.revenue"].name == "Samsung revenue" and samsung["samsung.china_sales"].slot_of == "gen:obj:chipmaker"
    assert samsung["samsung.revenue"].mean == 55.0                     # the entity's level, not the kind's 20


def test_default_links_are_added_once():
    ids = {i.id: i for i in SPEC.interactions}
    pairs = [(i.source, i.target) for i in SPEC.interactions]
    assert len(pairs) == len(set(pairs))
    assert "d-delta-oil_price-fuel_cost" not in ids                    # Delta writes this link out (e78)
    u = ids["d-united_airlines-oil_price-fuel_cost"]
    assert (u.source, u.target, u.effect["mu"], u.generalization) == (
        "resources_energy.oil_price", "united_airlines.fuel_cost", 0.9, "gen:int:energy_to_prices")
    assert ids["d-amd-export_controls-china_sales"].generalization == "gen:int:trade_restriction"
    # a typical link applies where the member has both ends: toolmakers' orders, not Samsung's missing capex
    assert "d-asml-orders-revenue" in ids and "d-tokyo_electron-orders-revenue" in ids
    assert not any(i.startswith("d-samsung-") and i.endswith("-capex") for i in ids)


def test_entities_without_a_kind_are_unchanged():
    raw = yaml.safe_load(open("world_model/examples/worlds/economy/entities.yaml"))
    written = {e["id"]: [s["id"] for s in e.get("subentities", [])] for e in raw["entities"]}
    for e in SPEC.entities:
        if str(e.kind) != "company":
            assert [s.id for s in e.subentities] == written[e.id]


def test_a_link_no_instance_can_have_is_an_error(tmp_path):
    objects = yaml.safe_load(open("world_model/taxonomy/objects.yaml"))
    for n in objects["nodes"]:
        if n["id"] == "gen:obj:airline":
            n["default_links"].append({"source": "no_such_value", "target": "revenue", "label": "x", "effect": 0.1,
                                       "kernel": {"delay_days": 1, "lag_days": 1, "duration_days": None}})
    (tmp_path / "objects.yaml").write_text(yaml.safe_dump(objects))
    with pytest.raises(ConstructionError, match="applies to no instance"):
        ConstructionSpec.load("world_model/examples/worlds/economy", tmp_path)


def test_the_model_files_default_links_and_the_view_names_the_kind(m1_engine):
    g, ltm = m1_engine.wm.graph, m1_engine.ltm
    assert g.interactions["d-united_airlines-fuel_cost-operating_margin"].generalization_id == "gen:int:margin_squeeze"
    tax = ltm.interaction_generalizations.taxonomy
    assert "d-united_airlines-fuel_cost-operating_margin" in tax.nodes["gen:int:margin_squeeze"].instance_ids
    assert g.entities["nvidia"].generalization_id == "gen:obj:chipmaker"
    view = build_graph_view(m1_engine.wm, ltm, None, 1)
    sub = next(s for s in view.subentities if s.id == "united_airlines.fuel_cost")
    assert (sub.slot, sub.slot_kind) == ("fuel_cost", "Airline")
    assert next(e for e in view.entities if e.id == "amd").kind_name == "Chipmaker"
