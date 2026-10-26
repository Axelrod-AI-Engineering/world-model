"""The standards gate (repo/review.py, `standards`): an imported item applies without a person only when every check
passes; anything else waits with each failed check as a reason. Each check is tested alone, then the policy as a whole."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace as NS

import pytest

from axelrod_ingest.contract.bundle import ImportItem
from axelrod_wm.engine.registry import registry
from axelrod_wm.repo.review import (
    GATE_CHECKS,
    GateInput,
    ImportContext,
    Proposal,
    ProposalKind,
    StandardsPolicy,
    check_attributed,
    check_coverage_labelled,
    check_cross_company_cited,
    check_not_structural,
    check_not_text,
    check_one_basis,
    check_plausible_confident,
    company_of,
)
from axelrod_wm.repo.snapshots import empty_state
from tests.conftest import real_event

AT = datetime(2024, 1, 1, tzinfo=UTC)
OBSERVE = {"op": "observe_value", "target": {"kind": "concrete", "subentity_id": "a.x"}, "value": 1.0,
           "observed_at": AT}


def proposal(ops=(OBSERVE,), kind=ProposalKind.GRAPH_UPDATE, **ev) -> Proposal:
    return Proposal(id="P-1", kind=kind, event=real_event(list(ops), **{"produced_by": "structured", **ev}), created_at=AT,
                    market_event_id="IM-A")


def item(**kw) -> ImportItem:
    base = {"id": "A", "published_at": AT, "source": "Synthetic regulator", "source_type": "central_bank",
            "headline": "h", "document": "Statement 12", "coverage": "full", "plausible": True, "confidence": 0.8,
            "signals": [{"type": "observe", "value_of": "a.x", "value": 1.0}]}
    return ImportItem.model_validate({**base, **kw})


def gate(p=None, it=None, graph=None, **ctx) -> GateInput:
    context = ImportContext(item=it, **ctx) if it is not None else None
    wm = NS(graph=graph) if graph is not None else empty_state()[0]
    return GateInput(proposal=p or proposal(), wm=wm, context=context, text_translators={"llm"})


# -- the graph the cross-company check reads: two companies, a shared bank, and one value a company file added --------
def fake_graph():
    ents = {"co1": NS(kind="company"), "co2": NS(kind="company"), "bank": NS(kind="agency")}
    subs = {"co1.sales": NS(entity_id="co1"), "co2.sales": NS(entity_id="co2"), "bank.rate": NS(entity_id="bank"),
            "bank.extra": NS(entity_id="bank")}
    inter = {"i1": NS(source_id="co1.sales", target_id="co2.sales"), "i2": NS(source_id="co1.sales", target_id="bank.rate")}
    return NS(entities=ents, subentities=subs, interactions=inter)


def test_company_of_an_entity_a_value_a_shared_player_and_a_value_a_company_file_added():
    g = fake_graph()
    assert company_of(g, {}, "co1") == "co1" and company_of(g, {}, "co2.sales") == "co2"
    assert company_of(g, {}, "bank.rate") is None and company_of(g, {}, "unknown") is None
    assert company_of(g, {"bank.extra": "co2"}, "bank.extra") == "co2"
    assert company_of(g, {"bank.extra": "bank"}, "bank.extra") is None        # a file stem that is no company


# -- not structural ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("op", [
    {"op": "add_entity", "temp_id": "new:z", "name": "Z", "kind": "company"},
    {"op": "add_interaction", "source": {"kind": "concrete", "subentity_id": "a.x"},
     "target": {"kind": "concrete", "subentity_id": "a.y"}, "label": "l", "polarity": 1}])
def test_adding_structure_is_structural(op):
    assert "adds or changes structure" in check_not_structural(gate(proposal([op])))


def test_a_deletion_is_never_waved_through():
    op = {"op": "retire_interaction", "interaction_id": "m01", "reason": "r"}
    assert check_not_structural(gate(proposal([op]))) == "deletes structure (D-12)"


def test_a_structural_proposal_kind_is_structural_and_a_plain_update_is_not():
    assert "adds or changes structure" in check_not_structural(gate(proposal(kind=ProposalKind.REFINEMENT)))
    assert check_not_structural(gate()) is None


def test_text_translation_is_never_waved_through():
    assert check_not_text(gate(proposal(produced_by="llm"))) == "translated from text"
    assert check_not_text(gate()) is None


# -- cross-company links (R20) ----------------------------------------------------------------------------------
def reweight(iid):
    return {"op": "reweight_interaction", "interaction_id": iid, "supports": True, "strength": 0.4}


def add_link(a, b):
    return {"op": "add_interaction", "source": {"kind": "concrete", "subentity_id": a},
            "target": {"kind": "concrete", "subentity_id": b}, "label": "l", "polarity": 1}


def test_a_reweighted_link_between_two_companies_needs_a_citation():
    g = fake_graph()
    p = proposal([reweight("i1")])
    assert "between co1 and co2 needs a citation" in check_cross_company_cited(gate(p, item(), g))
    assert check_cross_company_cited(gate(p, item(citation="Filing 3, note 7"), g)) is None
    assert "needs a citation" in check_cross_company_cited(gate(p, None, g))          # no item: no citation


def test_a_link_inside_a_company_or_to_a_shared_player_needs_none():
    g = fake_graph()
    for ops in ([reweight("i2")], [reweight("missing")], [add_link("co1.sales", "bank.rate")],
                [add_link("new:co1.x", "co1.sales")], [OBSERVE]):
        assert check_cross_company_cited(gate(proposal(ops), item(), g)) is None


def test_an_added_link_between_two_companies_needs_a_citation_too():
    p = proposal([add_link("co1.sales", "co2.sales")])
    assert check_cross_company_cited(gate(p, item(), fake_graph()))
    assert check_cross_company_cited(gate(p, item(citation="c"), fake_graph(), origin={})) is None


# -- attributed (R21) -------------------------------------------------------------------------------------------
def test_an_item_names_its_source_and_document():
    assert check_attributed(gate(it=item())) is None
    assert check_attributed(gate(it=item(document="", url="https://example.test/d"))) is None
    assert "no source document" in check_attributed(gate())
    assert "does not name its source document" in check_attributed(gate(it=item(document="")))
    assert "does not name its source document" in check_attributed(gate(it=item(source=" ")))


def test_third_party_material_names_its_publisher_and_its_mark():
    third = {"source_type": "broker_research"}
    assert "without its publisher" in check_attributed(gate(it=item(**third)))
    assert "not marked direct" in check_attributed(gate(it=item(publisher="Synthetic Securities", **third)))
    ok = item(publisher="Synthetic Securities", basis="proxy", **third)
    assert check_attributed(gate(it=ok)) is None
    ctx = item(publisher="Synthetic Securities", basis="context_only", **third)
    assert "context-only material cannot move" in check_attributed(gate(it=ctx))
    assert check_attributed(gate(it=item(publisher="P", basis="context_only", signals=[], **third))) is None


# -- one basis (R19) --------------------------------------------------------------------------------------------
def test_overlapping_views_in_one_item_fail_the_check(monkeypatch):
    warn = [{"scope": "item", "total": "t", "compositions": ["C1", "C2"]}]
    monkeypatch.setattr("axelrod_wm.repo.review.overlap_guard", lambda graph, items, folded, held: ({}, warn))
    assert check_one_basis(gate(it=item())) == "counts t through overlapping views (C1, C2) (item rule, R19)"
    monkeypatch.setattr("axelrod_wm.repo.review.overlap_guard", lambda graph, items, folded, held: ({}, []))
    assert check_one_basis(gate(it=item())) is None
    assert "no signals" in check_one_basis(gate())


# -- plausible and confident ------------------------------------------------------------------------------------
def test_the_plausibility_band_and_the_confidence_floor():
    assert check_plausible_confident(gate(it=item())) is None
    assert "no plausibility band" in check_plausible_confident(gate())
    assert check_plausible_confident(gate(it=item(plausible=None))) == "plausibility was not checked"
    bare = {"type": "move", "value_of": "a.x", "delta": -0.5, "mode": "standardized"}
    assert check_plausible_confident(gate(it=item(plausible=None, signals=[bare]))) == \
        "a direction with no size from evidence (R4)"
    link = {"type": "support", "source": "a.x", "target": "a.y"}
    assert check_plausible_confident(gate(it=item(plausible=None, signals=[link]))) == \
        "a link whose size is not from evidence (R4)"
    assert "outside the extractor's plausibility band" in check_plausible_confident(gate(it=item(plausible=False)))
    assert "below 0.6" in check_plausible_confident(gate(it=item(confidence=0.5)))
    assert "below 0.6" in check_plausible_confident(gate(proposal(confidence=0.4), item()))
    low_op = dict(OBSERVE, confidence=0.3)
    assert "0.30 is below 0.6" in check_plausible_confident(gate(proposal([low_op]), item()))


# -- labelled coverage (R18) ------------------------------------------------------------------------------------
def test_coverage_is_labelled_full_or_partial():
    assert check_coverage_labelled(gate(it=item())) is None
    assert check_coverage_labelled(gate(it=item(coverage="partial"))) is None
    assert "not labelled" in check_coverage_labelled(gate(it=item(coverage=None)))
    assert "not labelled" in check_coverage_labelled(gate())


# -- the policy -------------------------------------------------------------------------------------------------
def test_the_policy_is_registered_and_an_item_that_meets_every_standard_applies():
    pol = registry("review_policy").create("standards", config=None)
    assert isinstance(pol, StandardsPolicy) and pol.actor == "policy:standards" and len(GATE_CHECKS) == 7
    wm = empty_state()[0]
    assert pol.assess(proposal(), wm).needs_review                      # nothing bound: no item behind it: it waits
    pol.bind(lambda mid: ImportContext(item=item()) if mid == "IM-A" else None)
    req = pol.assess(proposal(), wm)
    assert not req.needs_review and req.reasons == []


def test_an_item_that_fails_waits_with_every_failed_check_as_a_reason():
    pol = StandardsPolicy()
    pol.bind(lambda mid: ImportContext(item=item(document="", coverage=None, plausible=False)))
    req = pol.assess(proposal(), empty_state()[0])
    assert req.needs_review and len(req.reasons) == 3
    assert any("source document" in r for r in req.reasons) and any("coverage" in r for r in req.reasons)


def test_an_event_without_a_market_event_has_no_item_and_waits():
    pol = StandardsPolicy()
    p = proposal().model_copy(update={"market_event_id": None})
    req = pol.assess(p, empty_state()[0])
    assert req.needs_review and "no source document" in " ".join(req.reasons)


def test_a_person_s_own_edit_applies_at_once_except_a_deletion():
    pol = StandardsPolicy()
    wm = empty_state()[0]
    own = Proposal(id="P-2", kind=ProposalKind.GRAPH_UPDATE, created_at=AT,
                   event=real_event([OBSERVE], produced_by="human"))
    assert not pol.assess(own, wm).needs_review
    gone = Proposal(id="P-3", kind=ProposalKind.GRAPH_UPDATE, created_at=AT,
                    event=real_event([{"op": "retire_entity", "entity_id": "z", "reason": "r"}], produced_by="human"))
    assert pol.assess(gone, wm).needs_review and "deletes structure (D-12)" in pol.assess(gone, wm).reasons
