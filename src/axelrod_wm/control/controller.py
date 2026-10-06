"""The controller façade (§7.6). The API, the CLI, and the scenario runner call only this class."""

from __future__ import annotations

import threading
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from axelrod_wm.control.decisions import DecisionError, DecisionRecord, DecisionTrace, Outcome
from axelrod_wm.control.review import Proposal, ProposalKind, ProposalStatus
from axelrod_wm.control.updates import UpdateCycle, UpdateRequest, UpdateRun, UpdateState
from axelrod_wm.core.hypothesis import Hypothesis, HypothesisKind, HypothesisStatus
from axelrod_wm.core.ids import IdFactory
from axelrod_wm.engine.performance.task import UnboundThesis
from axelrod_wm.engine.registry import registry
from axelrod_wm.events.graph_update import ChangeValue, EventKind, GraphUpdateEvent
from axelrod_wm.events.ledger import LedgerKind
from axelrod_wm.events.market import MarketEvent
from axelrod_wm.events.thesis import Thesis, ThesisMode
from axelrod_wm.ingest.pipeline import IngestionPipeline
from axelrod_wm.ingest.scrapers import dedup_keys
from axelrod_wm.memory.frontier import CoMovementStatus, pair_key
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.control.mutator import ChangeSet
    from axelrod_wm.engine.engine import Engine
    from axelrod_wm.engine.performance.records import Forecast
    from axelrod_wm.evaluation.backtest import EvaluationReport, EvaluationRequest
    from axelrod_wm.ingest.refiner import RefinementResult


class ControllerError(ValueError):
    pass


def end_of_day(day: date) -> datetime:
    return datetime.combine(day, time(23, 59, 59), tzinfo=UTC)


class WorldModelController:
    def __init__(self, engine: Engine, *, scenario_dir: str | Path | None = None,
                 control_ids: dict[str, int] | None = None) -> None:
        self.engine = engine
        self.scenario_dir = Path(scenario_dir) if scenario_dir is not None else None
        self.proposals: dict[str, Proposal] = {}
        self.market_events: dict[str, MarketEvent] = {}
        self.translations: dict[str, Any] = {}
        self.market_status: dict[str, str] = {}
        self.applied_events: list[GraphUpdateEvent] = []
        self.forecasts: dict[str, Forecast] = {}
        self.theses: dict[str, Thesis] = {}
        self.decisions: dict[str, DecisionRecord] = {}
        self.evaluations: dict[str, Any] = {}
        self.consolidations: list[Any] = []
        self.updates: dict[str, UpdateRun] = {}
        self.active_update: str | None = None
        self.ids = IdFactory(counters=dict(control_ids or {}))
        self.now: datetime = engine.wm.clock
        self.lock = threading.RLock()
        self.pipeline = IngestionPipeline(self)
        self.cycle = UpdateCycle(self)
        self.auto_resume = True                 # approving the awaited proposal resumes the run at once
        self._translators: dict[str, list[Any]] = {}
        self._sources: dict[str, Any] = {}
        self._known_keys: dict[str, str] = {}   # dedup key -> market event id
        self._effects_applied: set[str] = set()
        self.listeners: list[Any] = []          # callables (kind, **info), e.g. the scenario checklist

    # ---------------------------------------------------------------------------------------
    # plumbing
    # ---------------------------------------------------------------------------------------
    @property
    def config(self) -> Any:
        return self.engine.config

    def advance_now(self, t: datetime) -> datetime:
        """Simulated time only moves forward."""
        if t > self.now:
            self.now = t
        self.engine.tracer.set_context(sim_time=self.now, state_version=self.engine.version)
        return self.now

    def translator_chain(self, kind: str) -> list[Any]:
        """The configured translators for a market event kind, tried in order (§7.4)."""
        if kind not in self._translators:
            chain = []
            for name, params in self.config.translator_chain(kind):
                cls = registry("translator").get(name)
                kwargs: dict[str, Any] = dict(params)
                if name == "hand_drawn" and "directory" not in kwargs and self.scenario_dir is not None:
                    kwargs["directory"] = self.scenario_dir / "translations"
                chain.append(cls(config=self.config, **kwargs))
            self._translators[kind] = chain
        return self._translators[kind]

    def translator_for(self, kind: str) -> Any:
        return self.translator_chain(kind)[0]

    def register_source(self, name: str, source: Any) -> None:
        source.name = name
        self._sources[name] = source

    def source(self, name: str) -> Any:
        """A market event source by name: one registered by the runner, else one built from the
        `source` registry with config.update.source_params[name]."""
        if name not in self._sources:
            cls = registry("source").get(name)
            params = dict(self.config.update.source_params.get(name, {}))
            if self.scenario_dir is not None:
                params.setdefault("scenario_dir", self.scenario_dir)
            src = cls(config=self.config, **params)
            src.name = name
            self._sources[name] = src
        return self._sources[name]

    def collect_status(self, ev: MarketEvent) -> str:
        """"new", "requeue" (collected by a cancelled run but never processed), "processed" (already
        returned and folded), or "duplicate" (same URL, or same site and title, as a known item)."""
        if ev.id in self.market_events:
            return "requeue" if self.market_status.get(ev.id) == "queued" else "processed"
        if any(self._known_keys.get(k, ev.id) != ev.id for k in dedup_keys(ev)):
            return "duplicate"
        return "new"

    def remember_market_event(self, ev: MarketEvent) -> bool:
        """Record a collected market event; returns False if it was already known (a requeue)."""
        first = ev.id not in self.market_events
        self.market_events[ev.id] = ev
        for k in dedup_keys(ev):
            self._known_keys.setdefault(k, ev.id)
        self.market_status[ev.id] = "queued"
        return first

    def refine(self, event: GraphUpdateEvent, now: datetime | None = None) -> RefinementResult:
        ctx = self.engine.context(learn=event.kind == EventKind.REAL, now=now or self.now)
        return self.engine.components["refiner"].refine(event, self.engine.wm, self.engine.ltm, ctx)

    def _ledger_proposal(self, p: Proposal) -> None:
        self.engine.ledger.append(LedgerKind.PROPOSAL, p, recorded_at=self.now)

    def _decision_entry(self, p: Proposal, action: str, by: str, note: str | None, diff: dict | None = None,
                        **extra: Any) -> None:
        self.engine.ledger.append(LedgerKind.REVIEW_DECISION, {
            "proposal_id": p.id, "kind": str(p.kind), "action": action, "by": by, "note": note,
            "decided_at": self.now.isoformat(), "changeset_id": p.changeset_id, "diff": diff, **extra},
            recorded_at=self.now)

    # ---------------------------------------------------------------------------------------
    # proposals
    # ---------------------------------------------------------------------------------------
    def propose(self, kind: str | ProposalKind, event: GraphUpdateEvent | dict, *, steps: list | None = None,
                pending: list | None = None, soft_support: dict | None = None, market_event_id: str | None = None,
                reasons: list[str] | None = None, subject_id: str | None = None,
                retires_pending_id: str | None = None, world: bool = False,
                update_id: str | None = None) -> Proposal:
        """Create and assess a proposal. A world event waits for the update run's day loop to fold it;
        a model edit applies at once if it needs no review (§7.6)."""
        if isinstance(event, dict):
            event = GraphUpdateEvent.model_validate(event)
        p = Proposal(id=self.ids.next("PR"), kind=ProposalKind(kind), event=event,
                     market_event_id=market_event_id or event.market_event_id, refinement_steps=steps or [],
                     created_at=self.now, pending=pending or [], soft_support=soft_support or {},
                     retires_pending_id=retires_pending_id, subject_id=subject_id,
                     reason="; ".join(r for r in (reasons or []) if r) or None, world_event=world,
                     update_id=update_id or self.active_update)
        req = self.engine.components["review_policy"].assess(p, self.engine.wm)
        p.review_reasons = req.reasons
        p.needs_review = req.needs_review
        self.proposals[p.id] = p
        self._ledger_proposal(p)
        self._notify("proposed", proposal=p)
        tracer = self.engine.tracer
        if req.needs_review:
            p.status = ProposalStatus.PENDING
            if p.market_event_id:
                self.market_status[p.market_event_id] = "awaiting review"
            tracer.emit(Phase.REVIEW, "review.queued", refs=[p.id, event.id], proposal_id=p.id, kind=str(p.kind),
                        reasons=p.review_reasons, subject_id=subject_id, market_event_id=p.market_event_id,
                        world_event=world, update_id=p.update_id)
        else:
            tracer.emit(Phase.REVIEW, "review.auto", refs=[p.id, event.id], proposal_id=p.id, kind=str(p.kind),
                        reasons=[], subject_id=subject_id, market_event_id=p.market_event_id, world_event=world,
                        update_id=p.update_id)
            if not world:
                self._apply_model_edit(p, by="policy", note=None, auto=True)
        return p

    def submit_graph_update(self, event: GraphUpdateEvent, by: str, update_id: str | None = None) -> Proposal:
        """A drawn model edit (§7.6). An event with world ops (observe_value, change_value) is refused;
        the user types the news as a market event instead."""
        with self.lock:
            from axelrod_wm.control.updates import has_world_ops

            if has_world_ops(event):
                raise ControllerError("a drawn event cannot contain observe_value or change_value ops; "
                                      "add the news as a market event with an update instead")
            event = event.model_copy(update={"produced_by": event.produced_by or "human"})
            with self.engine.tracer.scoped(event.id):
                ref = self.refine(event)
                return self.propose(ProposalKind.GRAPH_UPDATE, ref.event, steps=ref.steps, pending=ref.pending,
                                    soft_support=ref.soft_support, update_id=update_id)

    def _apply_effects(self, p: Proposal, txn: Any) -> None:
        """What approval itself does: store the pending items, add the soft support, and retire the
        pending item a refinement resolves (§7.6)."""
        if p.id in self._effects_applied:
            return
        self._effects_applied.add(p.id)
        eng = self.engine
        for pend in p.pending:
            txn.add("wm.pending_refinements", pend.model_copy(update={"id": txn.new_id("PEND"), "created_at": self.now}))
        nodes = eng.ltm.interaction_generalizations.taxonomy.nodes
        for gid, amount in sorted(p.soft_support.items()):
            node = nodes.get(gid)
            if node is not None:
                st = node.stats.model_copy(deep=True)
                st.support += float(amount)
                txn.update("ltm.interaction_generalizations.taxonomy.nodes", gid, stats=st)
        if p.retires_pending_id and p.retires_pending_id in eng.wm.pending_refinements:
            txn.remove("wm.pending_refinements", p.retires_pending_id)

    def _apply_model_edit(self, p: Proposal, by: str, note: str | None, auto: bool) -> ChangeSet | None:
        eng = self.engine
        ev = p.event
        before_seq = eng.ledger.next_seq
        with eng.mutator.begin(cause=p.id, at=self.now) as txn:
            self._apply_effects(p, txn)
            if ev.ops:
                eng.structural.apply(ev, self.now, str(p.kind))
            frontier = eng.ltm.correlation_frontier
            if p.kind == ProposalKind.FRONTIER_PROMOTION and p.subject_id in frontier.entries:
                txn.update("ltm.correlation_frontier.entries", p.subject_id, status=CoMovementStatus.PROMOTED)
        cs = eng.mutator.last_changeset if eng.ledger.next_seq > before_seq else None
        self._mark_decided(p, ProposalStatus.AUTO_APPLIED if auto else ProposalStatus.APPROVED, by, note, cs)
        self._notify("applied", proposal=p, result=None)
        return cs

    def _mark_decided(self, p: Proposal, status: ProposalStatus, by: str, note: str | None,
                      cs: ChangeSet | None, **extra: Any) -> None:
        eng = self.engine
        p.status = status
        p.decided_at, p.decided_by, p.note = self.now, by, note
        if cs is not None:
            p.changeset_id = cs.id
        p.version_after = eng.version
        action = {ProposalStatus.AUTO_APPLIED: "auto_applied", ProposalStatus.APPROVED: "approved"}.get(status, str(status))
        self._decision_entry(p, action, by, note, **extra)
        eng.tracer.emit(Phase.REVIEW, "review.decided", refs=[p.id, p.event.id], proposal_id=p.id, kind=str(p.kind),
                        decision=str(p.status), by=by, changeset_id=p.changeset_id, version=eng.version,
                        market_event_id=p.market_event_id, world_event=p.world_event, **extra)

    @staticmethod
    def scope_of(p: Proposal) -> str:
        """The trace scope of a proposal's events: its market event, else its graph update event."""
        return p.market_event_id or p.event.id

    def fold_world_event(self, p: Proposal, day: int, *, auto: bool = False, late_from: int | None = None,
                         update_id: str | None = None) -> ChangeSet | None:
        """Fold an approved (or auto-applied) world event into processing day `day`, at the later of
        its publication and the start of the day (the start of the day for a late event)."""
        with self.engine.tracer.scoped(self.scope_of(p)):
            return self._fold_world_event(p, day, auto=auto, late_from=late_from, update_id=update_id)

    def _fold_world_event(self, p: Proposal, day: int, *, auto: bool, late_from: int | None,
                          update_id: str | None) -> ChangeSet | None:
        eng = self.engine
        dev = eng.wm.deviations
        me = self.market_events.get(p.market_event_id) if p.market_event_id else None
        published = me.published_at if me is not None else p.created_at
        now = dev.day_start(day) if late_from is not None else max(published, dev.day_start(day))
        self.advance_now(now)
        headline = me.headline if me is not None else None
        before_seq = eng.ledger.next_seq
        result = None
        with eng.mutator.begin(cause=p.id, at=now) as txn:
            self._apply_effects(p, txn)
            if late_from is not None and p.id in eng.wm.late_queue:
                txn.remove("wm.late_queue", p.id)
            if p.event.ops:
                result = eng.learning.run(p.event, now, day, headline=headline)
        cs = eng.mutator.last_changeset if eng.ledger.next_seq > before_seq else None
        p.folded_day = day
        p.late_from = late_from
        if auto:
            self._mark_decided(p, ProposalStatus.AUTO_APPLIED, "policy", None, cs, day=day)
        else:
            if cs is not None:
                p.changeset_id = cs.id
            p.version_after = eng.version
            self.engine.ledger.append(LedgerKind.REVIEW_DECISION, {
                "proposal_id": p.id, "kind": str(p.kind), "action": "folded", "day": day, "late_from": late_from,
                "changeset_id": p.changeset_id}, recorded_at=self.now)
            if late_from is not None:
                eng.tracer.emit(Phase.FOLD, "fold.late", refs=[p.id], proposal_id=p.id, day=day, late_from=late_from)
        self.applied_events.append(p.event)
        if p.market_event_id:
            self.market_status[p.market_event_id] = "applied"
        self._notify("applied", proposal=p, result=result)
        if result is not None:
            for pe in result.proposal_events:
                self.propose(pe["kind"], pe["event"], reasons=[pe.get("reason", "")], subject_id=pe.get("subject_id"),
                             update_id=update_id)
        if p.event.ops:
            self._retry_pending(p.event, update_id)
        return cs

    def _retry_pending(self, applied: GraphUpdateEvent, update_id: str | None = None) -> None:
        eng = self.engine
        if not eng.wm.pending_refinements:
            return
        ctx = eng.context(learn=True, now=self.now, processing_day=int(eng.wm.last_processed_day) + 1)
        open_ids = {p.retires_pending_id for p in self.proposals.values()
                    if p.kind == ProposalKind.REFINEMENT and p.status in (ProposalStatus.PENDING, ProposalStatus.DEFERRED)}
        for ev in eng.components["refiner"].retry_pending(applied, eng.wm, eng.ltm, ctx):
            pid = ev.id[len("GUE-REF-"):] if ev.id.startswith("GUE-REF-") else None
            if pid in open_ids or pid not in eng.wm.pending_refinements:
                continue
            open_ids.add(pid)
            self.propose(ProposalKind.REFINEMENT, ev, retires_pending_id=pid, reasons=[f"new evidence from {applied.id}"],
                         update_id=update_id)

    def _notify(self, kind: str, **info: Any) -> None:
        for fn in list(self.listeners):
            fn(kind, **info)

    def _get_open(self, proposal_id: str) -> Proposal:
        p = self.proposals.get(proposal_id)
        if p is None:
            raise ControllerError(f"unknown proposal {proposal_id}")
        if p.status not in (ProposalStatus.PENDING, ProposalStatus.DEFERRED):
            raise ControllerError(f"proposal {proposal_id} is already {p.status}")
        return p

    def _awaiting(self, proposal_id: str) -> UpdateRun | None:
        run = self.updates.get(self.active_update) if self.active_update else None
        if run is not None and run.state == UpdateState.AWAITING_REVIEW and run.waiting_on == proposal_id:
            return run
        return None

    def approve(self, proposal_id: str, by: str, note: str | None = None) -> ChangeSet | None:
        with self.lock:
            p = self._get_open(proposal_id)
            eng = self.engine
            with eng.tracer.scoped(self.scope_of(p)):
                if not p.world_event:
                    return self._apply_model_edit(p, by=by, note=note, auto=False)
                # a world event: approval stores its side effects now; the day loop folds it on its day
                before_seq = eng.ledger.next_seq
                with eng.mutator.begin(cause=f"approve:{p.id}", at=self.now) as txn:
                    self._apply_effects(p, txn)
                    late = p.due_day is not None and p.due_day <= eng.wm.last_processed_day and p.folded_day is None
                    if late:
                        txn.put("wm.late_queue", p.id, int(p.due_day))
                cs = eng.mutator.last_changeset if eng.ledger.next_seq > before_seq else None
                self._mark_decided(p, ProposalStatus.APPROVED, by, note, cs)
            run = self._awaiting(proposal_id)
            if run is not None and self.auto_resume:
                self.cycle.resume(run)
            return cs

    def reject(self, proposal_id: str, by: str, note: str) -> None:
        with self.lock:
            p = self._get_open(proposal_id)
            eng = self.engine
            frontier = eng.ltm.correlation_frontier
            if p.kind == ProposalKind.FRONTIER_PROMOTION and p.subject_id in frontier.entries:
                co = frontier.entries[p.subject_id]
                until = self.now + timedelta(days=float(self.config.frontier.reject_cooldown_days))
                with eng.mutator.begin(cause=p.id, at=self.now) as txn:
                    txn.update("ltm.correlation_frontier.entries", co.id, status=CoMovementStatus.DECAYED)
                    if co.hypothesis_id in eng.wm.hypotheses:
                        txn.update("wm.hypotheses", co.hypothesis_id, status=HypothesisStatus.REFUTED)
                    txn.put("ltm.correlation_frontier.blocked_until", pair_key(co.earlier_id, co.later_id), until)
            p.status = ProposalStatus.REJECTED
            p.decided_at, p.decided_by, p.note = self.now, by, note
            self._decision_entry(p, "rejected", by, note)
            if p.market_event_id:
                self.market_status[p.market_event_id] = "rejected"
            with eng.tracer.scoped(self.scope_of(p)):
                eng.tracer.emit(Phase.REVIEW, "review.decided", refs=[p.id, p.event.id], proposal_id=p.id,
                                kind=str(p.kind), decision="rejected", by=by, note=note,
                                market_event_id=p.market_event_id, world_event=p.world_event)
            run = self._awaiting(proposal_id)
            if run is not None and self.auto_resume:
                self.cycle.resume(run)

    def edit(self, proposal_id: str, event: GraphUpdateEvent, by: str) -> Proposal:
        with self.lock:
            p = self._get_open(proposal_id)
            old = p.event
            with self.engine.tracer.scoped(self.scope_of(p)):
                ref = self.refine(event)
            if p.edited_from is None:
                p.edited_from = old
            p.event = ref.event
            p.refinement_steps = ref.steps
            p.pending = ref.pending
            p.soft_support = ref.soft_support
            diff = {"before": old.model_dump(mode="json"), "after": ref.event.model_dump(mode="json")}
            self._decision_entry(p, "edited", by, None, diff)
            with self.engine.tracer.scoped(self.scope_of(p)):
                self.engine.tracer.emit(Phase.REVIEW, "review.decided", refs=[p.id, ref.event.id], proposal_id=p.id,
                                        kind=str(p.kind), decision="edited", by=by)
            return p

    def defer(self, proposal_id: str, by: str) -> None:
        with self.lock:
            p = self._get_open(proposal_id)
            p.status = ProposalStatus.DEFERRED
            p.decided_by = by
            self._decision_entry(p, "deferred", by, None)
            if p.market_event_id:
                self.market_status[p.market_event_id] = "deferred"
            with self.engine.tracer.scoped(self.scope_of(p)):
                self.engine.tracer.emit(Phase.REVIEW, "review.decided", refs=[p.id], proposal_id=p.id,
                                        kind=str(p.kind), decision="deferred", by=by, world_event=p.world_event)
            run = self._awaiting(proposal_id)
            if run is not None and self.auto_resume and by not in ("update", "cancel"):
                self.cycle.resume(run)

    def pending_proposals(self) -> list[Proposal]:
        return [p for p in self.proposals.values() if p.status == ProposalStatus.PENDING and p.needs_review]

    def set_review_policy(self, name: str) -> None:
        with self.lock:
            policy = registry("review_policy").create(name, config=self.config)
            self.engine.components["review_policy"] = policy
            self.config.review.policy = name

    # ---------------------------------------------------------------------------------------
    # update runs (§7.8)
    # ---------------------------------------------------------------------------------------
    def request_update(self, request: UpdateRequest | dict, *, run_to_end: bool = True) -> UpdateRun:
        with self.lock:
            if isinstance(request, dict):
                request = UpdateRequest.model_validate(request)
            return self.cycle.start(request, run_to_end=run_to_end)

    def continue_update(self, update_id: str) -> UpdateRun:
        with self.lock:
            run = self.get_update(update_id)
            if run.state == UpdateState.AWAITING_REVIEW:
                return self.cycle.resume(run)
            if run.state == UpdateState.RUNNING:
                return self.cycle.run_days(run)
            return run

    def cancel_update(self, update_id: str) -> UpdateRun:
        with self.lock:
            return self.cycle.cancel(self.get_update(update_id))

    def get_update(self, update_id: str) -> UpdateRun:
        run = self.updates.get(update_id)
        if run is None:
            raise ControllerError(f"unknown update {update_id}")
        return run

    def repose_pinned(self) -> list[str]:
        """Re-pose every pinned thesis against the new state (§7.8 Finish)."""
        out = []
        layer = self.engine.wm.forecast_layer
        for tid in sorted(layer.pinned):
            thesis = self.theses.get(tid)
            if thesis is None and tid in layer.by_thesis and layer.by_thesis[tid].thesis:
                thesis = Thesis.model_validate(layer.by_thesis[tid].thesis)
            if thesis is None:
                continue
            self.pose_thesis(thesis.model_copy(update={"pinned": True}))
            out.append(tid)
        return out

    def pin_thesis(self, thesis_id: str, pinned: bool = True) -> None:
        with self.lock:
            eng = self.engine
            layer = eng.wm.forecast_layer
            cur = set(layer.pinned)
            new = cur | {thesis_id} if pinned else cur - {thesis_id}
            if new != cur:
                with eng.mutator.begin(f"pin:{thesis_id}", at=self.now) as txn:
                    txn.set("wm.forecast_layer.pinned", new)
            if thesis_id in self.theses:
                self.theses[thesis_id] = self.theses[thesis_id].model_copy(update={"pinned": pinned})

    # ---------------------------------------------------------------------------------------
    # theses and hypotheses
    # ---------------------------------------------------------------------------------------
    def thesis_from_question(self, question: str, *, horizon_days: int = 182, targets: list[str] | None = None,
                             posed_by: str = "human", target_groups: list[dict] | None = None) -> Thesis:
        tr = self._translators.get("_template")
        if tr is None:
            from axelrod_wm.ingest.translators import TemplateTranslator

            tr = self._translators["_template"] = TemplateTranslator(self.config)
        ops, _ = tr.parse(question, self.now)
        if not ops:
            raise ControllerError(f"could not translate the question: {question!r}")
        n = self.ids.next("TQ")
        tid = f"T-Q{n.split('-')[1].lstrip('0') or '0'}"
        return Thesis.model_validate({
            "id": tid, "question": question, "mode": "open_ended", "horizon_days": horizon_days,
            "targets": targets or [], "target_groups": target_groups or [], "posed_by": posed_by,
            "posed_at": self.now.isoformat(),
            "event": {"id": f"GUE-{tid}", "kind": "hypothetical", "occurred_at": ops[0]["at"],
                      "recorded_at": self.now.isoformat(), "produced_by": "template", "ops": ops}})

    def pose_thesis(self, thesis: Thesis | str) -> Forecast:
        with self.lock:
            if isinstance(thesis, str):
                thesis = self.thesis_from_question(thesis)
            with self.engine.tracer.scoped(thesis.id):
                return self._pose_thesis(thesis)

    def _pose_thesis(self, thesis: Thesis) -> Forecast:
        from axelrod_wm.ingest.pipeline import op_ends_view, op_summary

        # the walkthrough's first step: the question and its operations, ends as fuzzy as they were posed
        self.engine.tracer.emit(Phase.TRANSLATE, "thesis.posed", refs=[thesis.id, thesis.event.id], thesis_id=thesis.id,
                                question=thesis.question, horizon_days=thesis.horizon_days,
                                ops=[{"index": i, "op": op.op, "summary": op_summary(op), "ends": op_ends_view(op)}
                                     for i, op in enumerate(thesis.event.ops)],
                                targets=list(thesis.targets), target_groups=[g.id for g in thesis.target_groups])
        ref = self.refine(thesis.event)
        unbound = []
        for pend in ref.pending:
            if isinstance(pend.op, ChangeValue):
                idx = int(pend.id.rsplit(":", 1)[-1]) if pend.id.count(":") >= 2 else 0
                unbound.append({"op_index": idx, "end": pend.end, "candidates": sorted(
                    ([k, round(v, 4)] for k, v in pend.candidates.items()), key=lambda x: -x[1])})
        if unbound:
            raise UnboundThesis(unbound)
        refined = thesis.model_copy(update={"event": ref.event})
        forecast = self.engine.performance.run(refined, self.now)
        self.forecasts[forecast.id] = forecast
        self.theses[thesis.id] = refined
        return forecast

    def pose_hypothesis(self, hypothesis_id: str, base_thesis_id: str | None = None) -> Forecast:
        with self.lock:
            h = self.engine.wm.hypotheses.get(hypothesis_id)
            if h is None:
                raise ControllerError(f"unknown hypothesis {hypothesis_id}")
            if h.kind != HypothesisKind.ENTITY_DECISION or not h.decision_subentity_id:
                raise ControllerError("only entity-decision hypotheses can be posed as theses")
            base = self.theses.get(base_thesis_id) if base_thesis_id else None
            if base_thesis_id and base is None:
                raise ControllerError(f"unknown thesis {base_thesis_id}")
            ops = [op.model_dump(mode="json") for op in base.event.ops] if base else []
            ops.append({"op": "change_value", "target": {"kind": "concrete", "subentity_id": h.decision_subentity_id},
                        "delta": float(h.decision_change or 0.0), "mode": "absolute", "persistence": "step",
                        "intervention": True, "window_days": int(h.decision_window_days or 90),
                        "at": self.now.isoformat()})
            tid = f"{base.id}+{h.id}" if base else f"T-base+{h.id}"
            thesis = Thesis.model_validate({
                "id": tid, "question": base.question if base else h.statement, "mode": ThesisMode.SCAFFOLDED,
                "horizon_days": base.horizon_days if base else int(h.decision_window_days or 182),
                "targets": list(base.targets) if base else [], "posed_by": "human", "posed_at": self.now.isoformat(),
                "event": {"id": f"GUE-{tid}", "kind": "hypothetical",
                          "event_type": base.event.event_type if base else "decision",
                          "occurred_at": (base.event.occurred_at if base else self.now).isoformat(),
                          "recorded_at": self.now.isoformat(), "produced_by": "human", "ops": ops}})
            return self.pose_thesis(thesis)

    def add_hypothesis(self, hypothesis: Hypothesis) -> Hypothesis:
        with self.lock:
            eng = self.engine
            ctx = eng.context(learn=True, now=self.now)
            with eng.mutator.begin(cause=f"hypothesis:{hypothesis.id}", at=self.now) as txn:
                hid = hypothesis.id if hypothesis.id and hypothesis.id not in eng.wm.hypotheses else txn.new_id("H")
                h = hypothesis.model_copy(update={"id": hid, "scored_at": self.now})
                scorer = eng.components["hypothesis_scorer"]
                h = h.model_copy(update={"probability": scorer.probability(h, eng.wm, eng.ltm, ctx)})
                txn.add("wm.hypotheses", h)
                scorer.rescore(h, eng.wm, eng.ltm, ctx, txn, force=True)
            return eng.wm.hypotheses[hid]

    def set_hypothesis_status(self, hypothesis_id: str, status: str) -> Hypothesis:
        with self.lock:
            eng = self.engine
            if hypothesis_id not in eng.wm.hypotheses:
                raise ControllerError(f"unknown hypothesis {hypothesis_id}")
            with eng.mutator.begin(cause=f"hypothesis:{hypothesis_id}", at=self.now) as txn:
                txn.update("wm.hypotheses", hypothesis_id, status=HypothesisStatus(status))
            return eng.wm.hypotheses[hypothesis_id]

    # ---------------------------------------------------------------------------------------
    # evaluation
    # ---------------------------------------------------------------------------------------
    def evaluate(self, request: EvaluationRequest) -> EvaluationReport:
        with self.lock:
            from axelrod_wm.evaluation.backtest import Backtester

            report = Backtester(self).run(request)
            self.evaluations[report.id] = report
            return report

    # ---------------------------------------------------------------------------------------
    # decisions
    # ---------------------------------------------------------------------------------------
    def forecast(self, forecast_id: str) -> Forecast | None:
        if forecast_id in self.forecasts:
            return self.forecasts[forecast_id]
        from axelrod_wm.engine.performance.records import Forecast as _F

        for e in reversed(self.engine.ledger.of_kind(LedgerKind.FORECAST)):
            if e.payload["forecast"]["id"] == forecast_id:
                fc = _F.model_validate(e.payload["forecast"])
                self.forecasts[forecast_id] = fc
                return fc
        return None

    def explanation(self, explanation_id: str) -> Any:
        from axelrod_wm.engine.explain_records import Explanation

        stored = self.engine.ltm.prior_states.explanations
        if explanation_id in stored:
            return stored[explanation_id]
        for view in self.engine.wm.forecast_layer.by_thesis.values():
            if view.explanation.id == explanation_id:
                return view.explanation
        for e in reversed(self.engine.ledger.of_kind(LedgerKind.FORECAST)):
            if e.payload["explanation"]["id"] == explanation_id:
                return Explanation.model_validate(e.payload["explanation"])
        return None

    def record_decision(self, decision: DecisionRecord | dict) -> DecisionRecord:
        with self.lock:
            data = decision.model_dump(mode="json") if isinstance(decision, DecisionRecord) else dict(decision)
            if not data.get("id"):
                data["id"] = f"D-{self.ids.next('D').split('-')[1]}"
            data.setdefault("created_at", self.now.isoformat())
            rec = DecisionRecord.model_validate(data)
            fcs = []
            for fid in rec.forecast_ids:
                fc = self.forecast(fid)
                if fc is None:
                    raise DecisionError(f"cited forecast {fid} does not exist")
                fcs.append(fc)
            baselines = [f for f in fcs if f.is_baseline]
            if not baselines:
                raise DecisionError("a decision must cite at least one baseline forecast (a thesis with no shocks)")
            if not any(rec.state_version == b.based_on_version for b in baselines):
                raise DecisionError(f"state_version {rec.state_version} differs from the baseline forecast's version "
                                    f"{baselines[0].based_on_version}")
            for f in fcs:
                if f.based_on_version > rec.state_version:
                    raise DecisionError(f"forecast {f.id} is based on a later version ({f.based_on_version})")
            self.decisions[rec.id] = rec
            self.engine.ledger.append(LedgerKind.DECISION, rec, recorded_at=self.now)
            self.engine.tracer.emit(Phase.DECIDE, "decision.recorded", refs=[rec.id] + rec.forecast_ids,
                                    decision_id=rec.id, agent_id=rec.agent_id, state_version=rec.state_version)
            return rec

    def resolve_decision(self, decision_id: str) -> Outcome:
        with self.lock:
            from axelrod_wm.evaluation.backtest import (
                apply_track_records,
                last_observed,
                pattern_hit,
                realized_series,
            )
            from axelrod_wm.evaluation.metrics import crps_quantiles

            rec = self.decisions.get(decision_id)
            if rec is None:
                raise DecisionError(f"unknown decision {decision_id}")
            if self.now < rec.review_after:
                raise DecisionError(f"decision {decision_id} can be resolved after {rec.review_after.isoformat()}")
            base = next(f for f in (self.forecast(i) for i in rec.forecast_ids) if f is not None and f.is_baseline)
            eng = self.engine
            dev = eng.wm.deviations
            # the baseline forecast's day 0 is the last day processed when it was posed
            start_day = base.start_day if base.start_day is not None else dev.day_of(base.created_at)
            days = max(1, min(base.horizon_days, int(eng.wm.last_processed_day) - start_day))
            realized: dict[str, float] = {}
            crps = []
            series: dict[str, list] = {}
            for sid in sorted(set(base.targets) | {s for n in base.networks for s in n.subentity_ids}):
                series[sid] = realized_series(dev, sid, start_day, base.horizon_days)
            for sid in base.targets:
                s = series[sid]
                t_last = last_observed(s[: days + 1], days)
                if t_last is None or sid not in base.z_summary:
                    continue
                realized[sid] = float(s[t_last])
                crps.append(crps_quantiles(base.z_summary[sid][t_last], float(s[t_last])))
            outcome = Outcome(resolved_at=self.now, realized=realized,
                              crps=float(sum(crps) / len(crps)) if crps else 0.0,
                              notes=f"scored at day {days} of the baseline forecast {base.id}, on observed days only")
            hits: dict[str, tuple[int, int]] = {}
            sig = float(self.config.evaluation.significant_effect)
            for n in base.networks:
                if n.pattern_id:
                    hit = pattern_hit(n.subentity_ids, base, series, sig)
                    if hit is not None:
                        h0, n0 = hits.get(n.pattern_id, (0, 0))
                        hits[n.pattern_id] = (h0 + int(hit), n0 + 1)
            if hits:
                apply_track_records(eng, hits, f"outcome:{decision_id}", self.now)
            with eng.mutator.begin(cause=f"outcome:{decision_id}", at=self.now) as txn:
                txn.append("wm.pending_episode_tags", "decision-outcome")
            rec.outcome = outcome
            eng.ledger.append(LedgerKind.OUTCOME, {"decision_id": decision_id, **outcome.model_dump(mode="json")},
                              recorded_at=self.now)
            eng.tracer.emit(Phase.DECIDE, "decision.resolved", refs=[decision_id], decision_id=decision_id,
                            crps=outcome.crps)
            return outcome

    def trace_decision(self, decision_id: str) -> DecisionTrace:
        with self.lock:
            from axelrod_wm.memory.snapshots import state_hash

            rec = self.decisions.get(decision_id)
            if rec is None:
                raise DecisionError(f"unknown decision {decision_id}")
            eng = self.engine
            fcs = [f for f in (self.forecast(i) for i in rec.forecast_ids) if f is not None]
            exps = [e for e in (self.explanation(f.explanation_id) for f in fcs if f.explanation_id) if e is not None]
            info = eng.version_info(rec.state_version)
            wm, ltm = eng.restore(rec.state_version)
            h = state_hash(wm, ltm)
            stored = info.state_hash if info is not None else h
            changes = [e.payload["id"] for e in eng.ledger.of_kind(LedgerKind.CHANGESET)
                       if e.payload["version_after"] > rec.state_version and e.payload["version_after"] != e.payload["version_before"]]
            view = self.state_view(rec.state_version, wm=wm, ltm=ltm)
            return DecisionTrace(decision=rec, forecasts=fcs, explanations=exps, state_hash_at_version=stored,
                                 view_at_version=view, changes_since=changes, hash_verified=(h == stored))

    # ---------------------------------------------------------------------------------------
    # views
    # ---------------------------------------------------------------------------------------
    def state_view(self, version: int | None = None, wm: Any = None, ltm: Any = None) -> Any:
        from axelrod_wm.api.views import build_graph_view

        eng = self.engine
        if version is not None and version != eng.version and wm is None:
            wm, ltm = eng.restore(version)
        return build_graph_view(wm or eng.wm, ltm or eng.ltm, self, version if version is not None else eng.version)

    def control_state(self) -> dict[str, Any]:
        return {"ids": dict(self.ids.counters)}

