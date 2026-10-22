"""Every registry slot has a contract, and every contract's flowchart steps exist."""

from __future__ import annotations

from axelrod_wm.engine import load_defaults
from axelrod_wm.engine.config import DEFAULT_COMPONENTS
from axelrod_wm.engine.contracts import CONTRACTS, contracts_table
from axelrod_wm.engine.registry import REGISTRIES
from axelrod_wm.flows import FLOWS


def test_every_slot_has_a_contract():
    load_defaults()
    import axelrod_wm.intake.sources  # noqa: F401  (the source registry)

    assert set(REGISTRIES) == set(CONTRACTS), (set(REGISTRIES) ^ set(CONTRACTS))
    assert set(DEFAULT_COMPONENTS) <= set(CONTRACTS)


def test_contract_flow_nodes_exist():
    for c in CONTRACTS.values():
        for ref in c.flow_nodes:
            flow_id, node_id = ref.split(":")
            assert flow_id in FLOWS, ref
            assert node_id in {n.id for n in FLOWS[flow_id].nodes}, ref
        for user in c.used_by:
            assert user in CONTRACTS or user in ("structural",), (c.slot, user)
        if not c.mandatory:
            assert c.condition or c.used_by, f"{c.slot}: say when an optional slot runs"


def test_table_lists_every_slot():
    table = contracts_table()
    for slot in CONTRACTS:
        assert f"`{slot}`" in table
