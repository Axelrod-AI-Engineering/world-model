"""The refiner (§7.5) and review (§7.6)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from axelrod_wm.control.review import ProposalStatus
from axelrod_wm.events.graph_update import GraphUpdateEvent, Specificity
from axelrod_wm.events.ledger import LedgerKind
from axelrod_wm.memory.snapshots import state_hash
from tests.conftest import make_controller, market_event, real_event, warm_taxonomies

AT = datetime(2026, 2, 9, 14, 0, tzinfo=timezone.utc)


@pytest.fixture
def ctl():
    c = make_controller()
    warm_taxonomies(c.engine)
    c.set_time(AT)
    return c


def _me03_event(ctl):
    return ctl.translator_for("news").translate(market_event("ME-03"), _tctx(ctl)).events[0]


def _tctx(ctl):
    from axelrod_wm.ingest.translators import TranslationContext

    return TranslationContext(ctl.engine.wm, ctl.engine.ltm, ctl.now)


def test_refiner_writes_nothing_and_reports_specificity(ctl):
    ev = _me03_event(ctl)
    assert ev.specificity() == Specificity.GENERALIZATION
    h, v = state_hash(ctl.engine.wm, ctl.engine.ltm), ctl.engine.version
    ref = ctl.refine(ev)
    assert state_hash(ctl.engine.wm, ctl.engine.ltm) == h and ctl.engine.version == v
    ops = [op.op for op in ref.event.ops]
    assert ops == ["change_value", "add_subentity", "add_interaction"]
    assert ref.event.ops[0].target.subentity_id == "legal_regulatory.export_controls"
    created = ref.event.ops[1]
    assert created.temp_id == "new:cross_border_trade.chip_exports" and created.features == {"product": "semiconductors"}
    assert ref.event.ops[2].source.subentity_id == "legal_regulatory.export_controls"
    assert ref.event.ops[2].target.subentity_id == "new:cross_border_trade.chip_exports"
    (pend,) = ref.pending
    assert pend.reached == Specificity.GENERALIZATION and pend.node_id == "gen:obj:supply_factor" and pend.end == "target"
    assert set(pend.candidates) == {"productivity_tech"} and pend.candidates["productivity_tech"] < 0.6
    assert pend.op.source.subentity_id == "cross_border_trade.chip_exports"     # bound to the created subentity
    assert pend.attribute_filter == ["spending_flow", "growth_rate"] and not pend.explicit_attribute
    assert ref.soft_support == {"gen:int:technology_diffusion": 0.6}
    assert ref.event.specificity() == Specificity.SUBENTITY
    steps = [(s.op_index, s.end, int(s.to_level), s.node_id, s.created) for s in ref.steps]
    assert (0, "subject", 0, "gen:obj:structural_factor", False) not in steps   # already given
    assert (0, "subject", 1, "legal_regulatory", False) in steps
    assert (1, "target", 2, "cross_border_trade.chip_exports", True) in steps


def test_candidate_entity_ids_are_ranked(ctl):
    op = {"op": "change_value", "target": {"kind": "abstract", "candidate_entity_ids": ["inflation", "resources_energy",
                                                                                         "supply_chains"],
                                            "attribute_kind": "commodity_price", "mention": "oil"},
          "delta": 0.1, "mode": "relative", "at": AT.isoformat()}
    ref = ctl.refine(real_event([op], "GUE-draw", AT))
    assert ref.event.ops[0].target.subentity_id == "resources_energy.oil_price"
    step = next(s for s in ref.steps if s.to_level == Specificity.ENTITY)
    assert step.candidates[0][0] == "resources_energy"


def test_low_scores_stay_at_generalization(ctl):
    op = {"op": "change_value", "target": {"kind": "abstract", "generalization_id": "gen:obj:demand_flow",
                                            "attribute_kind": "spending_flow", "mention": "zzz qqq"},
          "delta": 0.1, "mode": "relative", "at": AT.isoformat()}
    ref = ctl.refine(real_event([op], "GUE-low", AT))
    assert ref.event.ops == [] and ref.pending[0].reached == Specificity.GENERALIZATION


def test_relation_fills_attribute_kind_and_filters_candidates(ctl):
    op = {"op": "add_interaction",
          "source": {"kind": "concrete", "subentity_id": "interest_rates.us_policy_rate"},
          "target": {"kind": "abstract", "entity_id": "credit_availability", "mention": "funding"},
          "label": "raises funding costs", "polarity": 1,
          "interaction_generalization_id": "gen:int:policy_rate_to_bank_funding"}
    ref = ctl.refine(real_event([op], "GUE-rel", AT))
    # the relation limits the target to bank funding costs, but "funding" is ambiguous: stay at ENTITY
    (pend,) = ref.pending
    assert pend.reached == Specificity.ENTITY and pend.attribute_filter == ["bank_funding_cost"]
    assert set(pend.candidates) == {"credit_availability.us_bank_funding_cost",
                                    "credit_availability.euro_bank_funding_cost"}
    op["target"]["mention"] = "US funding"
    ref = ctl.refine(real_event([op], "GUE-rel2", AT))
    assert ref.event.ops[0].target.subentity_id == "credit_availability.us_bank_funding_cost"


def test_default_policy_review_rules(ctl):
    data = ctl.ingest(market_event("ME-01"))      # a data observation applies automatically
    assert data[0].status == ProposalStatus.AUTO_APPLIED
    news = ctl.ingest(market_event("ME-02"))      # translated from text
    assert news[0].status == ProposalStatus.PENDING and "translated from text" in news[0].review_reasons
    struct = ctl.submit_graph_update(real_event([{"op": "add_entity", "temp_id": "new:x", "name": "X",
                                                  "kind": "other"}], "GUE-x", AT, produced_by="analyst_bot"), "kim")
    assert struct.status == ProposalStatus.PENDING and "structural change" in struct.review_reasons
    human = ctl.submit_graph_update(real_event([{"op": "add_entity", "temp_id": "new:y", "name": "Y",
                                                 "kind": "other"}], "GUE-y", AT, produced_by="human"), "kim")
    assert human.status == ProposalStatus.AUTO_APPLIED


def test_approve_reject_edit_defer_write_ledger_entries(ctl):
    p1 = ctl.ingest(market_event("ME-02"))[0]
    p2 = ctl.ingest(market_event("ME-05"))[0]
    p3 = ctl.ingest(market_event("ME-07"))[0]
    p4 = ctl.ingest(market_event("ME-08"))[0]
    n = len(ctl.engine.ledger.of_kind(LedgerKind.REVIEW_DECISION))
    cs = ctl.approve(p1.id, "kim", "ok")
    assert cs is not None and p1.status == ProposalStatus.APPROVED and p1.changeset_id == cs.id
    ctl.reject(p2.id, "kim", "not convinced")
    edited = GraphUpdateEvent.model_validate({**p3.event.model_dump(mode="json"), "confidence": 0.95})
    ctl.edit(p3.id, edited, "kim")
    assert p3.edited_from is not None and p3.edited_from.confidence == 0.85 and p3.event.confidence == 0.95
    ctl.defer(p4.id, "kim")
    assert p2.status == ProposalStatus.REJECTED and p4.status == ProposalStatus.DEFERRED
    entries = ctl.engine.ledger.of_kind(LedgerKind.REVIEW_DECISION)[n:]
    assert [e.payload["action"] for e in entries] == ["approved", "rejected", "edited", "deferred"]
    assert entries[2].payload["diff"]["before"]["confidence"] == 0.85
    ctl.approve(p4.id, "kim")                     # deferred proposals can still be approved
    assert p4.status == ProposalStatus.APPROVED
