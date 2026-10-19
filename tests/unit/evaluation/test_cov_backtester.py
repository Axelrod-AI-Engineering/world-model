"""The backtester on the small demo: freeze at a past day, pose an article that came later, score the forecast
against what the model then observed, and credit the patterns whose members moved as predicted."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from axelrod_wm.evaluation.backtest import EvaluationRequest
from axelrod_wm.events.graph_update import EventValidationError
from axelrod_wm.repo.ledger import LedgerKind
from axelrod_wm.sim.examples.session import run_examples
from axelrod_wm.trace import RecordingTracer


@pytest.fixture
def ctl():
    _records, runner = run_examples("small_demo", tracer=RecordingTracer(run_id="eval"))
    return runner.controller


def at(day: str) -> datetime:
    return datetime.fromisoformat(day).replace(tzinfo=UTC)


def evaluations(eng) -> list:
    return [e for e in eng.ledger.read(0) if e.kind == LedgerKind.EVALUATION]


def test_a_pattern_that_moved_as_predicted_gains_a_hit(ctl):
    eng = ctl.engine
    before = eng.ltm.object_generalizations.patterns["pat-000001"].track_record
    version = eng.version
    rep = ctl.evaluate(EvaluationRequest(freeze_at=at("2026-05-01"), market_event_ids=["EX-024"], horizon_days=30))
    assert rep.thesis_ids == [f"{rep.id}-EX-024"] and rep.forecast_ids == [f"FC-{rep.id}-EX-024-1"]
    assert 0 < rep.frozen_version < version
    assert rep.pattern_hits == {"pat-000001": (1, 1)}
    after = eng.ltm.object_generalizations.patterns["pat-000001"].track_record
    assert (after.hits, after.misses) == (before.hits + 1, before.misses)
    assert eng.version > version                                  # the track record is a commit on the live model
    assert rep.omission_rate == 0.0 and rep.commission_rate == 0.0
    assert set(rep.coverage) == {"50", "80", "90"} and rep.crps >= 0.0
    assert "resources_energy.oil_price" in rep.per_target
    assert ctl.evaluations[rep.id] == rep
    assert [e.payload["id"] for e in evaluations(eng)] == [rep.id]
    done = [e for e in eng.tracer.events if e.kind == "evaluation.done"]
    assert done and done[-1].refs == [rep.id, *rep.thesis_ids]


def test_no_hit_when_the_pattern_members_did_not_move(ctl):
    eng = ctl.engine
    records = {pid: p.track_record for pid, p in eng.ltm.object_generalizations.patterns.items()}
    version = eng.version
    rep = ctl.evaluate(EvaluationRequest(freeze_at=at("2026-04-20"), market_event_ids=["EX-022"], horizon_days=30))
    assert rep.pattern_hits == {}
    assert {pid: p.track_record for pid, p in eng.ltm.object_generalizations.patterns.items()} == records
    assert eng.version == version
    assert rep.omission_rate == 0.0 and rep.commission_rate == 1.0     # it predicted a move that did not come


def test_several_articles_are_averaged_and_unknown_ones_are_left_out(ctl):
    rep = ctl.evaluate(EvaluationRequest(freeze_at=at("2026-03-01"), market_event_ids=["EX-017", "EX-020", "nope"],
                                         horizon_days=30))
    assert rep.thesis_ids == [f"{rep.id}-EX-017", f"{rep.id}-EX-020"]
    assert len(rep.forecast_ids) == 2
    assert 0.0 <= rep.omission_rate <= 1.0 and 0.0 <= rep.commission_rate <= 1.0
    assert {"resources_energy.oil_price", "delta.fuel_cost"} <= set(rep.per_target)


def test_nothing_to_pose_scores_nothing(ctl):
    rep = ctl.evaluate(EvaluationRequest(freeze_at=at("2026-03-01"), market_event_ids=["nope"], horizon_days=30))
    assert rep.thesis_ids == [] and rep.forecast_ids == [] and rep.pattern_hits == {}
    assert rep.coverage == {"50": 0.0, "80": 0.0, "90": 0.0}
    assert rep.omission_rate == rep.commission_rate == rep.crps == 0.0 and rep.per_target == {}
    assert len(evaluations(ctl.engine)) == 1                      # still recorded


def test_an_article_about_something_not_yet_built_cannot_be_posed(ctl):
    # on Jan 5 the canvas has no oil price yet
    with pytest.raises(EventValidationError, match="unknown subentity"):
        ctl.evaluate(EvaluationRequest(freeze_at=at("2026-01-05"), market_event_ids=["EX-004"], horizon_days=30))


def test_every_version_of_the_chain_restores_to_its_recorded_hash(ctl):
    """Regression: an interaction shared its dynamics with the op it came from, so the daily refit of the
    interaction also changed the op in a pending refinement, outside the mutator, and a frozen state no longer
    matched its recorded hash (the backtest's freeze failed)."""
    eng = ctl.engine
    for v in range(1, eng.version + 1):
        eng.snapshots.restore(v)                 # raises RestoreError on a hash mismatch
