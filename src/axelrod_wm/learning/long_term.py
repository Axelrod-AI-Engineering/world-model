"""Long-term-memory learning: what generalizes across time and entities (§8.6.2, §8.7, §8.8, §8.12).

It runs at two cadences, and every run is one commit to long-term memory:

- per working-memory commit (`register`): the event's new items join their kinds and the kinds'
  statistics update (and a crowded kind may split); decisions the fold observed go into the deciding
  entity's memory; the moves the graph did not explain are tested on the correlation frontier; and the
  explanation of what was learned is stored with the prior states;
- per day (`distill`, the daily distillation): the day becomes an episode, analog responses are pooled,
  forecast explanations are kept, superentity support is counted (candidates are proposed, and admissions
  and dissolutions are proposed for review), entity memories gain their weekly entry, the frontier
  decays, and the kinds touched today may grow.

What it proposes (a new interaction from the frontier, a superentity to admit or dissolve) waits for
review, like a market event does. Two hand-offs back to working memory are deliberate and named in the
component contracts: a frontier entry opens a presence hypothesis on the hypothesis frontier, and an
entity's memory sets how noisy its values are (level noise).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from axelrod_wm.memory.entity_memory import DecisionObservation, DecisionProfile, EntityMemory, action_of
from axelrod_wm.memory.frontier import FrontierResult
from axelrod_wm.memory.working import EpisodeEntry
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.learning.consolidate import ConsolidationReport
    from axelrod_wm.learning.working_memory import WorkingMemoryRecord
    from axelrod_wm.model.explanation import Explanation
    from axelrod_wm.repo.mutator import MutationTxn
    from axelrod_wm.shared.process import ParsedEvent


class LongTermRecord(BaseModel):
    """What one event's long-term commit produced."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    event_id: str
    frontier: FrontierResult
    explanation: Any
    proposal_events: list[dict] = []   # structural proposals that wait for review
    created_generalization_ids: list[str] = []
    version: int
    changeset_id: str | None = None
    commit: Any = None                 # the ChangeSet itself


def episode_entry(parsed: ParsedEvent, explanation: Explanation | None, at: datetime) -> EpisodeEntry:
    return EpisodeEntry(event_id=parsed.event_id, at=at, event_type=parsed.event_type, tags=list(parsed.tags),
                        signature=set(parsed.signature), routine=parsed.is_routine(),
                        explanation_id=explanation.id if explanation is not None else None,
                        touched_entity_ids=list(parsed.touched_entity_ids))


def record_decision(obs: DecisionObservation, ctx: ProcessContext, txn: MutationTxn) -> None:
    """Append a decision to the deciding entity's memory and count it in its decision profile, by the
    context it was made in (§8.12): the profile is what an entity-decision hypothesis reads."""
    from axelrod_wm.inference.voi import context_bucket
    from axelrod_wm.learning.fold import native_scale

    sub = ctx.wm.graph.subentities[obs.subentity_id]
    eid = sub.entity_id
    mem = ctx.ltm.entity_memories.get(eid)
    if mem is None:
        txn.add("ltm.entity_memories", EntityMemory(entity_id=eid, decisions=[obs]))
        profiles: dict[str, DecisionProfile] = {}
    else:
        txn.append_to("ltm.entity_memories", eid, "decisions", obs, keep_last=EntityMemory.MAX_DECISIONS)
        profiles = {k: v.model_copy(deep=True) for k, v in mem.profiles.items()}
    prof = profiles.setdefault(obs.subentity_id, DecisionProfile())
    counts = prof.by_context.setdefault(context_bucket(obs.context), [0, 0, 0])
    counts[("raised", "cut", "held").index(action_of(obs.change, native_scale(sub)))] += 1
    txn.update("ltm.entity_memories", eid, profiles=profiles)


def forget_retired(parsed: ParsedEvent, ctx: ProcessContext, txn: MutationTxn) -> None:
    """Retired items leave the kinds' member lists, and frontier entries about retired values decay. The
    retired entity's own memory stays (restructure)."""
    from axelrod_wm.memory.frontier import CoMovementStatus

    gone = set(parsed.retired_entity_ids) | set(parsed.retired_interaction_ids)
    if not gone and not parsed.retired_subentity_ids:
        return
    ltm = ctx.ltm
    for coll, tax in (("ltm.object_generalizations.taxonomy.nodes", ltm.object_generalizations.taxonomy),
                      ("ltm.interaction_generalizations.taxonomy.nodes", ltm.interaction_generalizations.taxonomy)):
        for gid, node in sorted(tax.nodes.items()):
            if gone & set(node.instance_ids):
                txn.update(coll, gid, instance_ids=[i for i in node.instance_ids if i not in gone])
    subs = set(parsed.retired_subentity_ids)
    for cid, co in sorted(ltm.correlation_frontier.entries.items()):
        if (co.earlier_id in subs or co.later_id in subs) and co.status != CoMovementStatus.DECAYED:
            txn.update("ltm.correlation_frontier.entries", cid, status=CoMovementStatus.DECAYED)


class LongTermLearning:
    def __init__(self, engine: Any) -> None:
        self.engine = engine

    # -- per working-memory commit ---------------------------------------------------------------
    def register(self, record: WorkingMemoryRecord, now: datetime, processing_day: int | None = None) -> LongTermRecord:
        """What one event teaches long-term memory: one commit, right after the event's working-memory
        commit."""
        eng = self.engine
        comp = eng.components
        ctx = eng.context(learn=True, now=now, processing_day=processing_day)
        if record.headline:
            ctx.notes["headline"] = record.headline
        shared, fold = record.shared, record.fold
        created: list[str] = []
        with ctx.mutator.begin(cause=f"ltm:{record.event_id}", at=now, process="learn.long_term",
                               message=f"Lessons of {record.event_id}") as txn:
            # 0. what working memory retired leaves its kinds and the correlation frontier
            forget_retired(shared.parsed, ctx, txn)
            # 1. the kinds: new items join their generalizations, whose statistics update
            for c in shared.classifications:
                created.extend(comp["classifier"].incorporate(c, ctx, txn))
            comp["generalization_updater"].update(shared.classifications, eng.ltm, ctx, txn)
            # 2. decisions observed today go into the deciding entity's memory
            for obs in fold.decisions:
                record_decision(obs, ctx, txn)
            # 3. the correlation frontier: unexplained moves paired with earlier moves elsewhere
            frontier = FrontierResult() if ctx.initializing else comp["frontier"].test(fold, eng.wm, eng.ltm, ctx, txn)
            # 4. the explanation of what was learned, kept with the prior states
            explanation = comp["explainer"].explain_learning(shared, fold, frontier, ctx)
            txn.add("ltm.prior_states.explanations", explanation)
            ctx.tracer.emit(Phase.EXPLAIN, "explain.stored", refs=[explanation.id, record.event_id],
                            explanation_id=explanation.id, top_paths=[], text=explanation.text)
            # 5. the day's episode buffer, which the daily distillation reads
            txn.append("wm.episode_buffer", episode_entry(shared.parsed, explanation, now))
        cs = eng.mutator.last_changeset
        mine = cs if cs is not None and cs.cause == f"ltm:{record.event_id}" else None
        events = list(shared.induction.proposal_events) + list(getattr(frontier, "proposal_events", []))
        return LongTermRecord(event_id=record.event_id, frontier=frontier, explanation=explanation,
                              proposal_events=events, created_generalization_ids=created, version=eng.version,
                              changeset_id=mine.id if mine is not None else None, commit=mine)

    # -- per day -------------------------------------------------------------------------------
    def distill(self, d: int, ctx: ProcessContext) -> ConsolidationReport:
        """The daily distillation of working memory into long-term memory: one commit."""
        return self.engine.components["consolidator"].run(d, ctx)
