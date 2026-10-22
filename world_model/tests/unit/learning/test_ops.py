"""One test per op in §8.4.1: each creates or changes exactly what the table says, through the mutator."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from axelrod_wm.engine.initialize import Initializer, SeedFile
from axelrod_wm.events.graph_update import EventValidationError
from axelrod_wm.model.evidence import Origin
from axelrod_wm.model.hypothesis import HypothesisStatus
from axelrod_wm.repo.ledger import LedgerKind
from tests.conftest import SEEDS, real_event

AT = datetime(2026, 2, 16, 5, 30, tzinfo=timezone.utc)


def _changes(eng):
    """The last event's working-memory commit (its long-term commit follows it)."""
    from axelrod_wm.repo.ledger import LedgerKind

    for e in reversed(eng.ledger.of_kind(LedgerKind.CHANGESET)):
        if e.payload.get("process") == "learn.working":
            from axelrod_wm.repo.mutator import ChangeSet

            return ChangeSet.model_validate(e.payload)
    return None


def test_add_entity(warm_engine):
    eng = warm_engine
    v = eng.version
    eng.learning.run(real_event([{"op": "add_entity", "temp_id": "new:snb", "name": "Swiss National Bank", "kind": "agency",
                                  "category_tags": ["MF"], "features": {"region": "CH", "function": "monetary_policy"},
                                  "aliases": ["SNB"]}], "GUE-E", AT, produced_by="hand_drawn"), AT, 0)
    ent = eng.wm.graph.entities["snb"]
    assert ent.origin == Origin.EVENT_PARSING and ent.aliases == ["SNB"] and ent.category_tags == {"MF"}
    assert eng.version == v + 2      # two commits: working memory, then long-term memory
    assert any(c.collection == "wm.graph.entities" and c.id == "snb" for c in _changes(eng).changes)


def test_temp_ids_get_a_suffix_when_taken(warm_engine):
    eng = warm_engine
    eng.learning.run(real_event([{"op": "add_entity", "temp_id": "new:inflation", "name": "Inflation 2",
                                  "kind": "macro_factor"}], "GUE-E2", AT), AT, 0)
    assert "inflation_2" in eng.wm.graph.entities


def test_add_subentity(warm_engine):
    eng = warm_engine
    eng.learning.run(real_event([{"op": "add_subentity", "entity": "inflation", "temp_id": "new:inflation.food_cpi",
                                  "name": "Food CPI", "attribute_kind": "inflation_rate", "unit": "pct"}], "GUE-S", AT), AT, 0)
    sub = eng.wm.graph.subentities["inflation.food_cpi"]
    assert "inflation.food_cpi" in eng.wm.graph.entities["inflation"].subentity_ids
    assert sub.prior_source_id == "gen:obj:price_level"
    assert sub.anchor == pytest.approx(sub.prior.link_moments()[0])
    assert sub.origin == Origin.HUMAN       # produced_by="human"


def test_add_interaction_closes_the_frontier(warm_engine):
    eng = warm_engine
    Initializer(eng).load_frontier_seeds(SeedFile.load(SEEDS), now=AT)
    (co,) = [e for e in eng.ltm.correlation_frontier.entries.values() if e.earlier_id == "inflation.headline_cpi"]
    ev = real_event([{"op": "add_interaction",
                      "source": {"kind": "concrete", "subentity_id": "inflation.headline_cpi"},
                      "target": {"kind": "concrete", "subentity_id": "confidence.consumer_confidence"},
                      "label": "erodes", "polarity": -1}], "GUE-I", AT, produced_by="hand_drawn",
                    evidence=[{"id": "EV-X", "source_type": "news", "excerpt": "prices hit sentiment",
                               "observed_at": AT.isoformat(), "strength": 0.6}])
    eng.learning.run(ev, AT, 0)
    (iid,) = eng.wm.graph.interaction_between("inflation.headline_cpi", "confidence.consumer_confidence")
    inter = eng.wm.graph.interactions[iid]
    assert inter.origin == Origin.EVENT_PARSING and not inter.internal
    assert inter.evidence and inter.evidence[0].excerpt == "prices hit sentiment"
    assert inter.forward.effect.mean() < 0 and inter.generalization_id is not None
    assert co.id not in eng.ltm.correlation_frontier.entries
    assert eng.wm.hypotheses[co.hypothesis_id].status == HypothesisStatus.SUPPORTED
    # every interaction has a ChannelState per direction from the moment it is created (§6.12)
    assert iid in eng.wm.channels and eng.wm.channels[iid].day == 0


def test_internal_interaction_is_marked(warm_engine):
    eng = warm_engine
    eng.learning.run(real_event([{"op": "add_interaction",
                                  "source": {"kind": "concrete", "subentity_id": "inflation.core_cpi"},
                                  "target": {"kind": "concrete", "subentity_id": "inflation.headline_cpi"},
                                  "label": "feeds", "polarity": 1}], "GUE-IN", AT), AT, 0)
    (iid,) = eng.wm.graph.interaction_between("inflation.core_cpi", "inflation.headline_cpi")
    assert eng.wm.graph.interactions[iid].internal
    assert eng.wm.graph.interactions[iid].origin == Origin.HUMAN
    assert iid in eng.wm.graph.entities["inflation"].internal_interaction_ids


def test_reweight_interaction(warm_engine):
    eng = warm_engine
    before = eng.wm.graph.interactions["e43"].existence
    n_ts = len(eng.wm.graph.interactions["e43"].time_states)
    n_ev = len(eng.wm.graph.interactions["e43"].evidence)
    eng.learning.run(real_event([{"op": "reweight_interaction", "interaction_id": "e43", "supports": True,
                                  "strength": 0.6}], "GUE-R", AT), AT, 0)
    after = eng.wm.graph.interactions["e43"]
    assert after.existence.alpha == pytest.approx(before.alpha + 0.6) and after.existence.beta == before.beta
    assert len(after.time_states) == n_ts + 1 and after.time_states[-1].source_event_id == "GUE-R"
    assert len(after.evidence) == n_ev + 1
    eng.learning.run(real_event([{"op": "reweight_interaction", "interaction_id": "e43", "supports": False,
                                  "strength": 0.5}], "GUE-R2", AT), AT, 0)
    assert eng.wm.graph.interactions["e43"].existence.beta == pytest.approx(before.beta + 0.5)


def test_annotate_interaction(warm_engine):
    eng = warm_engine
    eng.learning.run(real_event([{"op": "annotate_interaction", "interaction_id": "e08", "note": "OPEC+ cut: supply-driven",
                                  "valid_from": "2026-02-02T13:00:00Z"}], "GUE-AN", AT), AT, 0)
    ts = eng.wm.graph.interactions["e08"].time_states[-1]
    assert ts.note == "OPEC+ cut: supply-driven" and ts.source_event_id == "GUE-AN"
    assert ts.at.valid_at == datetime(2026, 2, 2, 13, tzinfo=timezone.utc)


def test_propose_hypothesis(warm_engine):
    eng = warm_engine
    eng.learning.run(real_event([{"op": "propose_hypothesis", "hypothesis": {
        "id": "H-x", "kind": "interaction_absent", "statement": "The Fed looks through oil", "interaction_id": "e43",
        "source_id": "inflation.headline_cpi", "target_id": "federal_reserve.policy_stance", "probability": 0.4,
        "scored_at": AT.isoformat(), "origin": "human"}}], "GUE-H", AT), AT, 0)
    h = eng.wm.hypotheses["H-x"]
    assert h.subject_entity_ids == ["federal_reserve", "inflation"]
    assert h.informational_value >= 0.0 and h.scored_at == AT


def test_observe_value(warm_engine):
    eng = warm_engine
    eng.learning.run(real_event([{"op": "observe_value",
                                  "target": {"kind": "concrete", "subentity_id": "federal_reserve.policy_stance"},
                                  "value": 4.75, "observed_at": "2026-01-28T19:00:00Z"}], "GUE-O", AT,
                                produced_by="data_feed", event_type="data_release"), AT, 0)
    sub = eng.wm.graph.subentities["federal_reserve.policy_stance"]
    assert sub.posterior.mean() == pytest.approx(4.75, abs=0.05)
    # applied on the processing day (0), whatever its observed_at
    p = eng.wm.deviations.point("federal_reserve.policy_stance", 0)
    assert p.observed and p.z == pytest.approx(2.0, abs=0.2) and p.innovation is not None


def test_change_value_shocks_and_observes(warm_engine):
    eng = warm_engine
    res = eng.learning.run(real_event([{"op": "change_value",
                                        "target": {"kind": "concrete", "subentity_id": "resources_energy.oil_price"},
                                        "delta": 0.35, "mode": "relative", "at": "2026-02-02T13:00:00Z"}],
                                      "GUE-C", AT, event_type="supply_shock"), AT, 0)
    (shock,) = res.shared.parsed.shocks
    assert shock.size == pytest.approx(0.30010459245 / 0.08, rel=1e-6) and shock.start_day == 1
    z = eng.wm.deviations.z("resources_energy.oil_price", 0)
    assert z > 3.5
    assert "inflation.headline_cpi" in res.shared.analysis.expected_moves
    assert res.shared.analysis.expected_moves["inflation.headline_cpi"].q50 > 0


def test_superentity_ops_only_through_the_structural_applier(warm_engine):
    eng = warm_engine
    with pytest.raises(EventValidationError):
        eng.learning.run(real_event([{"op": "dissolve_superentity", "pattern_id": "S6", "reason": "x"}], "GUE-D", AT,
                                    produced_by="engine"), AT, 0)
    eng.structural.apply(real_event([{"op": "dissolve_superentity", "pattern_id": "S6", "reason": "x"}], "GUE-D2", AT,
                                    produced_by="engine"), AT)
    assert eng.ltm.object_generalizations.patterns["S6"].status == "dissolved"
    assert not any(i.pattern_id == "S6" for i in eng.wm.graph.instances.values())


def test_hypothetical_events_reject_observations():
    ev = real_event([{"op": "observe_value", "target": {"kind": "concrete", "subentity_id": "inflation.headline_cpi"},
                      "value": 3.0, "observed_at": AT.isoformat()}], "GUE-HY", AT).model_copy(update={"kind": "hypothetical"})
    with pytest.raises(EventValidationError):
        from axelrod_wm.events.graph_update import validate_event

        validate_event(ev)


def test_every_learning_event_writes_a_changeset(warm_engine):
    eng = warm_engine
    n = len(eng.ledger.of_kind(LedgerKind.CHANGESET))
    eng.learning.run(real_event([{"op": "annotate_interaction", "interaction_id": "e01", "note": "n",
                                  "valid_from": AT.isoformat()}], "GUE-L", AT), AT, 0)
    sets = eng.ledger.of_kind(LedgerKind.CHANGESET)[n:]
    assert [(e.payload["cause"], e.payload["process"], e.payload["memory"]) for e in sets] == [
        ("GUE-L", "learn.working", "working"), ("ltm:GUE-L", "learn.long_term", "both")]
    assert eng.wm.episode_buffer[-1].event_id == "GUE-L"
    assert eng.wm.episode_buffer[-1].explanation_id in eng.ltm.prior_states.explanations
