"""Graph update events: specificity, per-op confidence, and §7.2 validation; theses must be hypothetical."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from axelrod_wm.events.graph_update import (
    AbstractTarget,
    AddEntity,
    AddInteraction,
    AddSubentity,
    ChangeValue,
    ConcreteTarget,
    DissolveSuperentity,
    EventValidationError,
    GraphUpdateEvent,
    ObserveValue,
    RetireEntity,
    RetireInteraction,
    ReweightInteraction,
    Specificity,
    op_confidence,
    op_ends,
    op_specificity,
    target_specificity,
    validate_event,
)
from axelrod_wm.events.thesis import TargetGroup, Thesis, ThesisMode

T0 = datetime(2026, 4, 1, tzinfo=timezone.utc)


def ev(ops, *, kind="real", produced_by="human", user_confidence=1.0) -> GraphUpdateEvent:
    return GraphUpdateEvent(id="E1", kind=kind, occurred_at=T0, recorded_at=T0, ops=ops, produced_by=produced_by,
                            user_confidence=user_confidence)


def change(target, confidence=None) -> ChangeValue:
    return ChangeValue(target=target, delta=0.1, mode="relative", at=T0, confidence=confidence)


def test_target_specificity_by_kind():
    assert target_specificity(ConcreteTarget(subentity_id="a.b")) == Specificity.SUBENTITY
    assert target_specificity(AbstractTarget(entity_id="a")) == Specificity.ENTITY
    assert target_specificity(AbstractTarget()) == Specificity.GENERALIZATION


def test_op_ends_and_specificity():
    c = ConcreteTarget(subentity_id="a.b")
    g = AbstractTarget(generalization_id="gen:obj:x")
    edge = AddInteraction(source=c, target=g, label="moves", polarity=1)
    assert op_ends(edge) == [("source", c), ("target", g)]
    assert op_ends(change(c)) == [("subject", c)]
    assert op_ends(ReweightInteraction(interaction_id="e1", supports=True)) == []
    assert op_specificity(edge) == Specificity.GENERALIZATION
    # an op without ends counts as concrete
    assert op_specificity(ReweightInteraction(interaction_id="e1", supports=True)) == Specificity.SUBENTITY
    assert ev([change(c), edge]).specificity() == Specificity.GENERALIZATION
    assert ev([]).specificity() == Specificity.SUBENTITY


def test_op_confidence_own_or_event_and_clamped():
    c = ConcreteTarget(subentity_id="a.b")
    e = ev([], user_confidence=0.4)
    assert op_confidence(e, change(c)) == 0.4
    assert op_confidence(e, change(c, confidence=0.9)) == 0.9
    assert op_confidence(e, change(c, confidence=1.7)) == 1.0
    assert op_confidence(e, change(c, confidence=-0.2)) == 0.0


def test_validate_accepts_temp_ids_defined_before_use():
    ops = [AddEntity(temp_id="new:acme", name="Acme", kind="company"),
           AddSubentity(entity="new:acme", temp_id="new:acme.revenue", name="Revenue", attribute_kind="revenue",
                        unit="usd"),
           change(ConcreteTarget(subentity_id="new:acme.revenue")),
           change(AbstractTarget(entity_id="new:acme")),
           change(AbstractTarget(generalization_id="gen:obj:x")),
           change(ConcreteTarget(subentity_id="existing.one"))]
    validate_event(ev(ops))   # no error


@pytest.mark.parametrize("ops, kind, produced_by, msg", [
    ([DissolveSuperentity(pattern_id="S1", reason="x")], "real", "llm", "cannot come from a translator"),
    ([ObserveValue(target=ConcreteTarget(subentity_id="a.b"), value=1.0, observed_at=T0)], "hypothetical", "human",
     "may not contain observe_value"),
    ([RetireInteraction(interaction_id="e1", reason="x")], "hypothetical", "human", "cannot retire structure"),
    ([RetireEntity(entity_id="a", reason="x")], "hypothetical", "human", "cannot retire structure"),
    ([AddEntity(temp_id="acme", name="Acme", kind="company")], "real", "human", "add_entity temp_id"),
    ([AddSubentity(entity="a", temp_id="a.rev", name="R", attribute_kind="revenue", unit="usd")], "real", "human",
     "add_subentity temp_id"),
    ([AddSubentity(entity="new:ghost", temp_id="new:ghost.r", name="R", attribute_kind="revenue", unit="usd")],
     "real", "human", "before it is defined"),
    ([change(ConcreteTarget(subentity_id="new:ghost.r"))], "real", "human", "before it is defined"),
    ([change(AbstractTarget(entity_id="new:ghost"))], "real", "human", "before it is defined"),
])
def test_validate_rejects(ops, kind, produced_by, msg):
    with pytest.raises(EventValidationError, match=msg):
        validate_event(ev(ops, kind=kind, produced_by=produced_by))


def test_superentity_ops_from_a_person_are_allowed():
    validate_event(ev([DissolveSuperentity(pattern_id="S1", reason="x")], produced_by="human"))


def test_thesis_requires_a_hypothetical_event_and_groups_have_ids():
    hyp = ev([change(ConcreteTarget(subentity_id="a.b"))], kind="hypothetical")
    th = Thesis(id="T1", question="q", mode=ThesisMode.SCAFFOLDED, event=hyp, posed_by="me", posed_at=T0,
                target_groups=[TargetGroup(kind="sector", ref="energy")])
    assert th.target_groups[0].id == "sector:energy" and th.horizon_days == 182
    with pytest.raises(ValueError, match="must be hypothetical"):
        Thesis(id="T2", question="q", mode=ThesisMode.OPEN_ENDED, event=ev([]), posed_by="me", posed_at=T0)
