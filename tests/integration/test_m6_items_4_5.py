"""Checklist items 4 and 5 (§15.3), starting from the M1 graph with warmed taxonomy statistics."""

from __future__ import annotations

from datetime import datetime, timezone

from axelrod_wm.control.review import ProposalStatus
from axelrod_wm.events.graph_update import Specificity
from tests.conftest import make_controller, market_event, warm_taxonomies


def test_items_4_and_5():
    ctl = make_controller()
    eng = ctl.engine
    warm_taxonomies(eng)
    ctl.set_time(datetime(2026, 2, 9, tzinfo=timezone.utc))
    tdiff_before = eng.ltm.interaction_taxonomy.nodes["gen:int:technology_diffusion"].stats.support
    (p3,) = ctl.ingest(market_event("ME-03"))
    assert p3.status == ProposalStatus.PENDING
    ctl.approve(p3.id, "reviewer")
    g = eng.wm.graph
    # item 4
    sub = g.subentities["cross_border_trade.chip_exports"]
    assert sub.origin == "event_parsing" and sub.features == {"product": "semiconductors"}
    (iid,) = g.interaction_between("legal_regulatory.export_controls", "cross_border_trade.chip_exports")
    assert g.interactions[iid].generalization_id == "gen:int:trade_restriction"
    pend = list(eng.wm.pending_refinements.values())
    assert len(pend) == 1 and pend[0].reached == Specificity.GENERALIZATION and pend[0].node_id == "gen:obj:supply_factor"
    assert eng.ltm.interaction_taxonomy.nodes["gen:int:technology_diffusion"].stats.support > tdiff_before
    # item 5
    (p4,) = ctl.ingest(market_event("ME-04"))
    ctl.approve(p4.id, "reviewer")
    rbi = g.entities["rbi"]
    tax = eng.ltm.object_taxonomy
    assert tax.path_from_root(rbi.generalization_id) == ["gen:obj:root", "gen:obj:actor", "gen:obj:monetary_authority",
                                                         "gen:obj:central_bank"]
    assert g.subentities["rbi.policy_stance"].prior_source_id == "gen:obj:central_bank"
    (fid,) = g.interaction_between("interest_rates.india_policy_rate", "credit_availability.india_bank_funding_cost")
    funding = g.interactions[fid]
    assert funding.generalization_id == "gen:int:policy_rate_to_bank_funding" == funding.prior_source_id
