"""Parse, op by op, on the constructed economy: real events through the transaction, theses through the
overlay, and the errors a malformed event raises."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from axelrod_wm.engine.context import GraphOverlay
from axelrod_wm.events.graph_update import ChangeMode, EventValidationError, GraphUpdateEvent
from axelrod_wm.memory.working import DeviationPoint, PendingRefinement, point_key
from axelrod_wm.model.distributions import Beta, Gaussian, LogNormal
from axelrod_wm.model.evidence import Evidence, Origin, SourceType
from axelrod_wm.model.hypothesis import Hypothesis, HypothesisKind, HypothesisStatus
from axelrod_wm.shared.parse import DefaultParser, change_size, source_type_for
from tests.conftest import constructed_engine, real_event

AT = datetime(2023, 1, 1, 23, 59, 59, tzinfo=timezone.utc)
RATE, FUND = "interest_rates.us_policy_rate", "credit_availability.us_bank_funding_cost"


def conc(sid):
    return {"kind": "concrete", "subentity_id": sid}


@pytest.fixture
def eng():
    return constructed_engine(build=True)


def parse_real(eng, ops, notes=None, **kw):
    ev = real_event(ops, at=AT, **kw)
    ctx = eng.context(learn=True, now=AT)
    ctx.notes.update(notes or {})
    with eng.mutator.begin("parse", at=AT) as txn:
        parsed = eng.components["parser"].parse(ev, eng.wm, eng.ltm, ctx, txn)
    return parsed, ctx


def parse_hyp(eng, ops, scope="T-9", **kw):
    ev = GraphUpdateEvent.model_validate({"id": "GUE-H", "kind": "hypothetical", "occurred_at": AT, "recorded_at": AT,
                                          "produced_by": "human", "ops": ops, **kw})
    ctx = eng.context(learn=False, now=AT)
    ctx.overlay = GraphOverlay(eng.wm, scope=scope)
    ctx.scope = scope
    return eng.components["parser"].parse(ev, ctx.wm, eng.ltm, ctx, None), ctx


# ----- helpers ----------------------------------------------------------------------------------

def test_source_type_for():
    assert source_type_for("data_feed") == SourceType.DATA and source_type_for("human") == SourceType.HUMAN
    assert source_type_for("engine.fold") == SourceType.MODEL and source_type_for("someone") == SourceType.NEWS


def test_change_size_modes_and_uncertainty(eng):
    g = eng.wm.graph
    sub = g.subentities[RATE].model_copy(update={"scale": 0.5})
    eta, _ = sub.posterior.link_moments()
    assert change_size(sub, ChangeMode.ABSOLUTE, 1.0) == (pytest.approx(2.0), 0.0)
    assert change_size(sub, ChangeMode.STANDARDIZED, 1.5, 0.2) == (pytest.approx(1.5), 0.2)
    size, sd = change_size(sub, ChangeMode.ABSOLUTE, 1.0, 0.25)
    assert size == pytest.approx(2.0) and sd == pytest.approx(0.5)
    oil = sub.model_copy(update={"posterior": LogNormal(mu=math.log(80.0), sigma=0.1), "scale": 0.1})
    size, sd = change_size(oil, ChangeMode.RELATIVE, 0.1, 0.05)
    assert size == pytest.approx(math.log(1.1) / 0.1)
    assert sd == pytest.approx((math.log(1.15) - math.log(1.05)) / 0.2)
    assert eta == sub.posterior.mean()


# ----- creation -------------------------------------------------------------------------------

def test_final_ids_never_collide(eng):
    ops = [{"op": "add_entity", "temp_id": "new:interest_rates", "name": "Rates 2", "kind": "market"},
           {"op": "add_entity", "temp_id": "new:interest_rates_2", "name": "Rates 3", "kind": "market"},
           {"op": "add_entity", "temp_id": "new:interest_rates", "name": "Rates 4", "kind": "market"}]
    parsed, _ = parse_real(eng, ops)
    assert parsed.new_entity_ids == ["interest_rates_2", "interest_rates_2_2", "interest_rates_3"]
    assert parsed.temp_map["new:interest_rates"] == "interest_rates_3"


def test_subentity_prior_family_wins_and_decision_variable(eng):
    ops = [{"op": "add_subentity", "entity": "interest_rates", "temp_id": "new:interest_rates.oil_hedge",
            "name": "Hedge", "attribute_kind": "policy_rate", "unit": "usd", "family": "gaussian",
            "prior": {"family": "lognormal", "mu": 1.0, "sigma": 0.2}, "scale": 0.3,
            "features": {"decision_variable": "true"}}]
    parsed, ctx = parse_real(eng, ops)
    sid = "interest_rates.oil_hedge"
    sub = eng.wm.graph.subentities[sid]
    assert sub.posterior.family == "lognormal" and sub.anchor == 1.0 and sub.scale == 0.3
    assert sid in eng.wm.decision_variables and sid in eng.wm.graph.entities["interest_rates"].subentity_ids
    assert ctx.notes["new_subentities"][sid] == ["prior", "scale", "family"]
    assert parsed.touched_entity_ids == ["interest_rates"]


def test_add_interaction_origins_reverse_and_low_confidence(eng):
    ops = [{"op": "add_interaction", "source": conc(RATE), "target": conc(FUND), "label": "lifts", "polarity": 1,
            "direction": "bidirectional", "existence": {"alpha": 5.0, "beta": 1.0}, "confidence": 0.5}]
    parsed, ctx = parse_real(eng, ops, notes={"proposal_kind": "frontier_promotion"}, produced_by="llm")
    inter = eng.wm.graph.interactions[parsed.new_interaction_ids[0]]
    assert inter.origin == Origin.FRONTIER_PROMOTION and inter.reverse == inter.forward
    assert (inter.existence.alpha, inter.existence.beta) == (3.0, 1.0)      # 1 + c * (a - 1)
    assert inter.evidence[0].strength == 0.5 and inter.evidence[0].source_type == SourceType.NEWS
    assert ctx.notes["polarity"][inter.id] == 1
    parsed2, _ = parse_real(eng, [dict(ops[0], confidence=None, hedge="pending:x")],
                            notes={"proposal_kind": "missing_relation"}, produced_by="engine")
    inter2 = eng.wm.graph.interactions[parsed2.new_interaction_ids[0]]
    assert inter2.origin == Origin.INFERENCE and inter2.tags == ["hedge:pending:x"]


def test_add_interaction_inside_one_entity_is_internal(eng):
    ops = [{"op": "add_interaction", "source": conc(RATE), "target": conc("interest_rates.real_rate"),
            "label": "lifts", "polarity": 1}]
    parsed, _ = parse_real(eng, ops, produced_by="hand_drawn")
    iid = parsed.new_interaction_ids[0]
    assert eng.wm.graph.interactions[iid].internal and eng.wm.graph.interactions[iid].origin == Origin.EVENT_PARSING
    assert iid in eng.wm.graph.entities["interest_rates"].internal_interaction_ids


# ----- edits ------------------------------------------------------------------------------------

def test_reweight_and_annotate_real(eng):
    before = eng.wm.graph.interactions["e01"].existence
    ev_kw = {"evidence": [Evidence(id="EV-x", source_type=SourceType.NEWS, excerpt="quote", observed_at=AT,
                                   strength=0.6).model_dump()]}
    ops = [{"op": "reweight_interaction", "interaction_id": "e01", "supports": False, "strength": 0.4},
           {"op": "annotate_interaction", "interaction_id": "e01", "note": "temporary", "valid_from": AT,
            "valid_to": AT + timedelta(days=30)}]
    parsed, _ = parse_real(eng, ops, **ev_kw)
    inter = eng.wm.graph.interactions["e01"]
    assert inter.existence.beta == pytest.approx(before.beta + 0.4) and inter.existence.alpha == before.alpha
    notes = [t.note for t in inter.time_states]
    assert "reweight" in notes and "temporary (until 2023-01-31)" in notes
    assert inter.evidence[-1].excerpt == "quote" and inter.evidence[-1].strength == pytest.approx(0.6)
    assert parsed.annotated_interaction_ids == ["e01"] and parsed.touched_interaction_ids == ["e01"]


def test_evidence_beyond_fifty_is_counted(eng):
    inter = eng.wm.graph.interactions["e01"]
    old = [Evidence(id=f"EV-{k}", source_type=SourceType.NEWS, excerpt="x", observed_at=AT, strength=0.1)
           for k in range(50)]
    with eng.mutator.begin("seed", at=AT) as txn:
        txn.update("wm.graph.interactions", "e01", evidence=old)
    parse_real(eng, [{"op": "reweight_interaction", "interaction_id": "e01", "supports": True}])
    inter = eng.wm.graph.interactions["e01"]
    assert len(inter.evidence) == 50 and inter.evidence_dropped == 1 and inter.evidence[0].id == "EV-1"


@pytest.mark.parametrize("op", [
    {"op": "reweight_interaction", "interaction_id": "nope", "supports": True},
    {"op": "annotate_interaction", "interaction_id": "nope", "note": "n", "valid_from": AT},
    {"op": "retire_interaction", "interaction_id": "nope", "reason": "r"},
    {"op": "retire_entity", "entity_id": "nope", "reason": "r"},
    {"op": "add_subentity", "entity": "nope", "temp_id": "new:nope.x", "name": "x", "attribute_kind": "policy_rate",
     "unit": "pct"},
    {"op": "observe_value", "target": conc("nope.x"), "value": 1.0, "observed_at": AT},
    {"op": "change_value", "target": {"kind": "abstract", "attribute_kind": "policy_rate"}, "delta": 1.0,
     "mode": "absolute", "at": AT},
])
def test_unknown_references_and_fuzzy_ends_raise(eng, op):
    with pytest.raises(EventValidationError):
        parse_real(eng, [op])


def test_structural_ops_and_missing_transaction_raise(eng):
    pattern = {"id": "pat-x", "name": "x", "roles": [], "relations": [], "created_at": AT.isoformat()}
    with pytest.raises(EventValidationError, match="StructuralApplier"):
        parse_real(eng, [{"op": "propose_superentity", "pattern": pattern}])
    ev = real_event([], at=AT)
    with pytest.raises(ValueError, match="needs a transaction"):
        eng.components["parser"].parse(ev, eng.wm, eng.ltm, eng.context(learn=True, now=AT), None)


def test_undefined_temp_ids_are_caught_by_validation(eng):
    op = {"op": "observe_value", "target": conc("new:x.y"), "value": 1.0, "observed_at": AT}
    with pytest.raises(EventValidationError, match="before it is defined"):
        parse_real(eng, [op])
    assert DefaultParser()._resolve("new:x", {"new:x": "x_2"}) == "x_2" and DefaultParser()._resolve("x", {}) == "x"


def test_subentity_prior_of_the_named_family(eng):
    ops = [{"op": "add_subentity", "entity": "interest_rates", "temp_id": "new:interest_rates.alt",
            "name": "Alt", "attribute_kind": "policy_rate", "unit": "pct",
            "prior": {"family": "gaussian", "mu": 2.0, "sigma": 0.5}}]
    parse_real(eng, ops)
    sub = eng.wm.graph.subentities["interest_rates.alt"]
    assert sub.posterior == Gaussian(mu=2.0, sigma=0.5) and sub.anchor == 2.0 and sub.scale == 1.0


def test_new_interaction_closes_its_frontier_entry(eng):
    from axelrod_wm.memory.frontier import CoMovement

    h = Hypothesis(id="H-f", kind=HypothesisKind.INTERACTION_PRESENT, statement="s", source_id=RATE,
                   target_id="inflation.headline_cpi", probability=0.5, scored_at=AT, origin=Origin.INFERENCE)
    co = CoMovement(id="CM-1", earlier_id=RATE, later_id="inflation.headline_cpi", lag_days=5, sign=1,
                    first_seen=AT, last_seen=AT, hypothesis_id="H-f")
    co2 = co.model_copy(update={"id": "CM-2", "hypothesis_id": "H-gone"})
    with eng.mutator.begin("seed", at=AT) as txn:
        txn.add("wm.hypotheses", h)
        txn.add("ltm.correlation_frontier.entries", co)
        txn.add("ltm.correlation_frontier.entries", co2)
    ops = [{"op": "add_interaction", "source": conc(RATE), "target": conc("inflation.headline_cpi"),
            "label": "lifts", "polarity": 1}]
    parse_real(eng, ops)
    assert eng.ltm.correlation_frontier.entries == {}
    assert eng.wm.hypotheses["H-f"].status == HypothesisStatus.SUPPORTED


def test_observed_value_names_the_channels_that_explain_it(eng):
    day = eng.wm.processing_day()
    del eng.wm.channels["e01"]                                  # so the recorded phi is read
    eng.wm.channel_phi[f"e01|{day}"] = 5.0                     # e01 feeds the funding cost
    ops = [{"op": "observe_value", "target": conc(FUND), "value": 1.0, "observed_at": AT},
           {"op": "observe_value", "target": conc(FUND), "value": 1.1, "observed_at": AT}]
    parsed, _ = parse_real(eng, ops)
    assert parsed.touched_interaction_ids == ["e01"]
    assert parsed.z_before == {} and parsed.max_abs_move == 0.0       # no point today: no move measured


# ----- values -----------------------------------------------------------------------------------

def test_observe_and_change_values_measure_the_move(eng):
    day = eng.wm.deviations.day_of(AT) + 1
    sub = eng.wm.graph.subentities[RATE]
    with eng.mutator.begin("pt", at=AT) as txn:
        txn.add("wm.deviations.points", DeviationPoint(z=0.0, var=0.1, level=0.0), key=point_key(RATE, day))
    value = sub.anchor + 2.5 * sub.scale                                    # gaussian: identity link
    ops = [{"op": "observe_value", "target": conc(RATE), "value": value, "observed_at": AT, "confidence": 0.25},
           {"op": "change_value", "target": conc(FUND), "delta": 1.0, "mode": "standardized", "at": AT,
            "confidence": 0.5}]
    parsed, _ = parse_real(eng, ops)
    (sid, val, noise, _), = parsed.observations
    assert sid == RATE and val == value and noise == pytest.approx(0.05 / math.sqrt(0.25))
    sh = parsed.shocks[0]
    assert sh.size == pytest.approx(0.5) and sh.size_sd == pytest.approx(math.sqrt(0.5 * 0.5 * 1.0))
    assert sh.start_day == 1 and not sh.intervention
    assert parsed.change_observations[0][2] >= sh.size_sd
    assert parsed.max_abs_move == pytest.approx(2.5)
    assert parsed.z_before == {RATE: 0.0}


# ----- retirement -------------------------------------------------------------------------------

def test_retire_interaction_twice_retires_once(eng):
    ops = [{"op": "retire_interaction", "interaction_id": "e01", "reason": "gone"},
           {"op": "retire_interaction", "interaction_id": "e01", "reason": "again"}]
    parsed, _ = parse_real(eng, ops)
    assert parsed.retired_interaction_ids == ["e01"]
    assert eng.wm.graph.interactions["e01"].retired_at == AT
    assert eng.wm.graph.interactions["e01"].time_states[-1].note == "retired: gone"


def test_retire_entity_cleans_up_around_it(eng):
    wm = eng.wm
    ent = wm.graph.entities["interest_rates"]
    gone_sub = ent.subentity_ids[0]
    h_open = Hypothesis(id="H-a", kind=HypothesisKind.INTERACTION_PRESENT, statement="s", source_id=gone_sub,
                        target_id=FUND, probability=0.5, scored_at=AT, origin=Origin.INFERENCE)
    h_other = h_open.model_copy(update={"id": "H-b", "source_id": "inflation.headline_cpi",
                                        "subject_entity_ids": ["inflation"]})
    h_done = h_open.model_copy(update={"id": "H-c", "status": HypothesisStatus.SUPPORTED})
    pend = PendingRefinement(id="PEND-1", op={"op": "observe_value", "target": conc(RATE), "value": 1.0,
                                              "observed_at": AT},
                             end="subject", reached=1, node_id="interest_rates", candidates={}, evidence=[],
                             source_event_id="E", created_at=AT, expires_at=AT)
    pend_other = pend.model_copy(update={"id": "PEND-2", "node_id": "inflation"})
    with eng.mutator.begin("seed", at=AT) as txn:
        for h in (h_open, h_other, h_done):
            txn.add("wm.hypotheses", h)
        txn.add("wm.pending_refinements", pend)
        txn.add("wm.pending_refinements", pend_other)
        txn.set("wm.decision_variables", list(wm.decision_variables) + [gone_sub])
    ops = [{"op": "retire_interaction", "interaction_id": "e01", "reason": "first"},
           {"op": "retire_entity", "entity_id": "interest_rates", "reason": "merged"}]
    parsed, _ = parse_real(eng, ops)
    assert "interest_rates" not in wm.graph.entities and gone_sub not in wm.graph.subentities
    assert parsed.retired_entity_ids == ["interest_rates"] and gone_sub in parsed.retired_subentity_ids
    assert parsed.retired_interaction_ids.count("e01") == 1 and "e02" in parsed.retired_interaction_ids
    assert "inst-S1" not in wm.graph.instances and "inst-S2" in wm.graph.instances
    assert wm.hypotheses["H-a"].status == HypothesisStatus.EXPIRED
    assert wm.hypotheses["H-b"].status == HypothesisStatus.OPEN
    assert wm.hypotheses["H-c"].status == HypothesisStatus.SUPPORTED
    assert list(wm.pending_refinements) == ["PEND-2"] and gone_sub not in wm.decision_variables


def test_retire_a_bare_entity(eng):
    ops = [{"op": "add_entity", "temp_id": "new:lonely", "name": "Lonely", "kind": "company"}]
    parse_real(eng, ops)
    dvs = list(eng.wm.decision_variables)
    parsed, _ = parse_real(eng, [{"op": "retire_entity", "entity_id": "lonely", "reason": "r"}])
    assert parsed.retired_entity_ids == ["lonely"] and parsed.retired_interaction_ids == []
    assert eng.wm.decision_variables == dvs and len(eng.wm.graph.instances) == 20


# ----- theses (the overlay) ---------------------------------------------------------------------

def test_hypothetical_parse_writes_only_the_overlay(eng):
    h = Hypothesis(id="", kind=HypothesisKind.INTERACTION_ABSENT, statement="s", interaction_id="e01",
                   probability=0.4, scored_at=AT, origin=Origin.INFERENCE)
    ops = [{"op": "add_entity", "temp_id": "new:shadow", "name": "Shadow", "kind": "company"},
           {"op": "add_subentity", "entity": "new:shadow", "temp_id": "new:shadow.rate", "name": "Rate",
            "attribute_kind": "policy_rate", "unit": "pct"},
           {"op": "add_interaction", "source": conc("new:shadow.rate"), "target": conc(FUND), "label": "lifts",
            "polarity": 1},
           {"op": "reweight_interaction", "interaction_id": "e02", "supports": True, "strength": 1.0},
           {"op": "annotate_interaction", "interaction_id": "e02", "note": "ignored in a thesis", "valid_from": AT},
           {"op": "propose_hypothesis", "hypothesis": h.model_dump(mode="json")},
           {"op": "change_value", "target": conc(RATE), "delta": 0.5, "mode": "standardized",
            "at": AT + timedelta(days=10), "intervention": True, "window_days": 5}]
    base_alpha = eng.wm.graph.interactions["e02"].existence.alpha
    parsed, ctx = parse_hyp(eng, ops)
    ov = ctx.overlay
    assert "shadow" in ov.graph.entities and "shadow" not in eng.wm.graph.entities
    assert ov.graph.entities["shadow"].subentity_ids == ["shadow.rate"]
    iid = parsed.new_interaction_ids[0]
    assert iid == "int-T-9-1" and iid in ov.graph.interactions
    assert ov.graph.interactions["e02"].existence.alpha == base_alpha + 1.0
    assert eng.wm.graph.interactions["e02"].existence.alpha == base_alpha
    assert parsed.annotated_interaction_ids == [] and ov.graph.interactions["e02"].time_states == \
        eng.wm.graph.interactions["e02"].time_states
    (hid,) = ov.created["hypotheses"]
    assert hid == "H-T-9-1" and ov.wm.hypotheses[hid].from_thesis == "T-9" and not eng.wm.hypotheses
    sh = parsed.shocks[0]
    assert sh.start_day == 10 and sh.intervention and sh.hold_days == 5
    assert parsed.change_observations == []


def test_hypothesis_ids_are_kept_when_free(eng):
    h = Hypothesis(id="H-free", kind=HypothesisKind.INTERACTION_ABSENT, statement="s", interaction_id="e01",
                   probability=0.4, scored_at=AT, origin=Origin.INFERENCE)
    parse_real(eng, [{"op": "propose_hypothesis", "hypothesis": h.model_dump(mode="json")}])
    assert "H-free" in eng.wm.hypotheses and eng.wm.hypotheses["H-free"].from_thesis is None
    parse_real(eng, [{"op": "propose_hypothesis", "hypothesis": h.model_dump(mode="json")}])
    assert len(eng.wm.hypotheses) == 2                                      # the second got a fresh id


def test_overlay_thesis_scope_falls_back_to_the_event(eng):
    h = Hypothesis(id="H-z", kind=HypothesisKind.INTERACTION_ABSENT, statement="s", interaction_id="e01",
                   probability=0.4, scored_at=AT, origin=Origin.INFERENCE)
    _, ctx = parse_hyp(eng, [{"op": "propose_hypothesis", "hypothesis": h.model_dump(mode="json")}], scope="")
    assert ctx.overlay.wm.hypotheses["H-z"].from_thesis == "GUE-H"
    assert isinstance(Beta(alpha=1, beta=1), Beta) and isinstance(Gaussian(mu=0, sigma=1), Gaussian)
