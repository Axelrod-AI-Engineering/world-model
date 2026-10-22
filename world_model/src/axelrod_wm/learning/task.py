"""Learning, as the update run calls it: one entry point per vetted event and per day.

Learning is two processes, each with its own commits (see working_memory.py and long_term.py):

    per vetted event   working memory: read the event and fold it in         -> commit <event id>
                       long-term memory: register what it teaches             -> commit ltm:<event id>
    per day            working memory: open the day (predict)                 -> commit predict:<date>
                       ... the day's events ...
                       working memory: record the day                         -> commit record:<date>
                       long-term memory: distill the day                      -> commit distill:<date>
                       working memory: close the day                          -> commit close:<date>

Only backend users' vetted changes reach learning; everyone else uses the model for prediction only.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from axelrod_wm.learning.fold import FoldResult
from axelrod_wm.learning.long_term import LongTermLearning, LongTermRecord
from axelrod_wm.learning.working_memory import WorkingMemoryLearning, WorkingMemoryRecord
from axelrod_wm.memory.frontier import FrontierResult
from axelrod_wm.repo.ledger import LedgerKind
from axelrod_wm.shared.process import SharedResult
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.events.graph_update import GraphUpdateEvent
    from axelrod_wm.learning.consolidate import ConsolidationReport


class LearningResult(BaseModel):
    """Both commits of one event, and what callers read from them."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    shared: SharedResult
    fold: FoldResult
    frontier: FrontierResult
    explanation: Any
    proposal_events: list[dict] = []
    working: WorkingMemoryRecord | None = None
    long_term: LongTermRecord | None = None


class LearningTask:
    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self.working = WorkingMemoryLearning(engine)
        self.long_term = LongTermLearning(engine)

    @property
    def shared(self) -> Any:
        return self.engine.shared

    def run(self, event: GraphUpdateEvent, now: datetime, processing_day: int | None = None, *,
            headline: str | None = None, proposal_kind: str | None = None, proposal_id: str | None = None,
            vetted_by: str | None = None) -> LearningResult:
        """One vetted event: working memory first, then long-term memory (§7.8)."""
        wm_rec = self.working.learn(event, now, processing_day, headline=headline, proposal_kind=proposal_kind,
                                    proposal_id=proposal_id, vetted_by=vetted_by)
        lt_rec = self.long_term.register(wm_rec, now, processing_day)
        return LearningResult(shared=wm_rec.shared, fold=wm_rec.fold, frontier=lt_rec.frontier,
                              explanation=lt_rec.explanation,
                              proposal_events=list(wm_rec.proposal_events) + list(lt_rec.proposal_events),
                              working=wm_rec, long_term=lt_rec)

    def open_day(self, d: int) -> None:
        self.working.open_day(d)

    def close_day(self, d: int, now: datetime) -> ConsolidationReport:
        """After the day's events: record (working), distill (long-term), close (working)."""
        eng = self.engine
        ctx = eng.context(learn=True, now=now, processing_day=d)
        self.working.record_day(d, ctx)
        report = self.long_term.distill(d, ctx)
        self.working.close_day(d, ctx, report)
        report.version = eng.version
        report.proposals = [p.get("event", {}).get("id", "") for p in report.proposal_events]
        ltm = eng.ltm
        eng.ledger.append(LedgerKind.CONSOLIDATION, report.model_dump(mode="json", exclude={"proposal_events"}),
                          recorded_at=ctx.now)
        ctx.tracer.emit(Phase.CONSOLIDATE, "consolidation.done", refs=[report.episode_id] if report.episode_id else [],
                        report={"day": report.day.isoformat(), "episode_id": report.episode_id,
                                "patterns_supported": report.patterns_supported,
                                "frontier_decayed": report.frontier_decayed,
                                "hypotheses_expired": report.hypotheses_expired,
                                "kernels_updated": report.kernels_updated, "candidates": report.candidates,
                                "version": report.version,
                                "episodes": len(ltm.prior_states.episodes)})
        return report
