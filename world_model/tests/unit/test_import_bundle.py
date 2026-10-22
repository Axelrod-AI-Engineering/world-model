"""Import bundles into the world model (intake/structured.py): how signals become operations. The schema's own tests
are ingestion's (ingestion/tests/contract)."""

import json
from datetime import UTC, datetime

from axelrod_ingest.contract.bundle import ImportBundle, Link, Move, Observe, Support
from axelrod_wm.intake.structured import market_event_of, signal_ops, translate_item
from tests.where import IMPORT_BUNDLE_SAMPLE

SAMPLE = IMPORT_BUNDLE_SAMPLE
AT = datetime(2026, 9, 18, tzinfo=UTC)


class Interaction:
    def __init__(self, iid, src, dst):
        self.id, self.source_id, self.target_id = iid, src, dst


class Graph:
    subentities = {"central_bank.policy_rate": 1, "dollar.index": 1, "acme_motors.operating_profit": 1}

    def active_interactions(self):
        return [Interaction("m16", "central_bank.policy_rate", "dollar.index")]


def test_signals_become_operations():
    g = Graph()
    ops, why = signal_ops(Observe(type="observe", value_of="central_bank.policy_rate", value=4.25), g, AT)
    assert why is None and ops[0]["op"] == "observe_value" and ops[0]["value"] == 4.25
    ops, _ = signal_ops(Move(type="move", value_of="acme_motors.operating_profit", delta=-0.04, mode="relative"), g, AT)
    assert ops[0]["op"] == "change_value" and ops[0]["mode"] == "relative"
    # a link already in the model is evidence for it, not a second link
    ops, _ = signal_ops(Link(type="link", source="central_bank.policy_rate", target="dollar.index", label="x", effect=-0.4), g, AT)
    assert ops[0]["op"] == "reweight_interaction" and ops[0]["interaction_id"] == "m16"
    ops, _ = signal_ops(Link(type="link", source="dollar.index", target="acme_motors.operating_profit", label="lifts",
                             effect=0.4), g, AT)
    assert ops[0]["op"] == "add_interaction" and ops[0]["polarity"] == 1
    ops, _ = signal_ops(Support(type="contradict", source="central_bank.policy_rate", target="dollar.index"), g, AT)
    assert ops[0]["supports"] is False
    ops, why = signal_ops(Observe(type="observe", value_of="nowhere.x", value=1), g, AT)
    assert ops == [] and "nowhere.x" in why


def test_translate_item_drops_what_does_not_map_and_highlights_quotes():
    b = ImportBundle.model_validate(json.loads(SAMPLE.read_text()))
    item = next(i for i in b.items if i.id == "T-002")
    item.signals = item.signals[:1]
    me = market_event_of(item, "IM-T-002")
    res, dropped = translate_item(item, me, Graph())
    assert dropped == [] and res.events[0].produced_by == "structured"
    start, end, op = res.spans[0]
    assert f"{item.headline}\n{item.summary}"[start:end] == item.signals[0].quote and op == 0
    assert me.published_at == item.published_at and "rates" in me.tags


def test_the_structured_translator_is_registered_by_the_engine_defaults_alone():
    """Importing engine.defaults (and nothing that names the translator) registers it, in a fresh interpreter."""
    import subprocess
    import sys

    code = ("import axelrod_wm.engine.defaults; from axelrod_wm.engine.registry import registry; "
            "print('structured' in registry('translator').names())")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "True"
