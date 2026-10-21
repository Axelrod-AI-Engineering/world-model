"""Import bundles (intake/bundle.py): the schema, and how signals become operations."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from axelrod_wm.intake.bundle import (
    ImportBundle,
    Link,
    Move,
    Observe,
    Support,
    market_event_of,
    signal_ops,
    translate_item,
)

SAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "import_bundle_sample.json"
AT = datetime(2026, 9, 18, tzinfo=UTC)


class Interaction:
    def __init__(self, iid, src, dst):
        self.id, self.source_id, self.target_id = iid, src, dst


class Graph:
    subentities = {"boj.policy_rate": 1, "dollar_yen.usd_jpy": 1, "acme_motors.operating_profit": 1}

    def active_interactions(self):
        return [Interaction("m16", "boj.policy_rate", "dollar_yen.usd_jpy")]


def test_sample_bundle_parses():
    b = ImportBundle.model_validate(json.loads(SAMPLE.read_text()))
    assert [i.id for i in b.items] == ["T-002", "T-001", "T-003"]
    assert {type(s).__name__ for i in b.items for s in i.signals} == {"Observe", "Support", "Link"}


def test_unknown_signal_type_and_extra_fields_fail():
    with pytest.raises(ValidationError):
        ImportBundle.model_validate({"items": [{"id": "x", "published_at": "2026-09-01T00:00:00Z", "source": "s",
                                                "headline": "h", "signals": [{"type": "guess", "value_of": "a"}]}]})
    with pytest.raises(ValidationError):
        ImportBundle.model_validate({"items": [], "surprise": 1})


def test_signals_become_operations():
    g = Graph()
    ops, why = signal_ops(Observe(type="observe", value_of="boj.policy_rate", value=1.25), g, AT)
    assert why is None and ops[0]["op"] == "observe_value" and ops[0]["value"] == 1.25
    ops, _ = signal_ops(Move(type="move", value_of="acme_motors.operating_profit", delta=-0.04, mode="relative"), g, AT)
    assert ops[0]["op"] == "change_value" and ops[0]["mode"] == "relative"
    # a link already in the model is evidence for it, not a second link
    ops, _ = signal_ops(Link(type="link", source="boj.policy_rate", target="dollar_yen.usd_jpy", label="x", effect=-0.4), g, AT)
    assert ops[0]["op"] == "reweight_interaction" and ops[0]["interaction_id"] == "m16"
    ops, _ = signal_ops(Link(type="link", source="dollar_yen.usd_jpy", target="acme_motors.operating_profit", label="lifts",
                             effect=0.4), g, AT)
    assert ops[0]["op"] == "add_interaction" and ops[0]["polarity"] == 1
    ops, _ = signal_ops(Support(type="contradict", source="boj.policy_rate", target="dollar_yen.usd_jpy"), g, AT)
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
