"""The update loop (§7.8, D14).

An update run collects new market events from the configured sources and any events the user adds,
then processes every whole day from the day after the last processed day through the requested
date: it predicts each day's state, folds in that day's events in time order, and consolidates. A
run that reaches a news item needing review pauses there until the reviewer decides.

`UpdateRun` records live in the controller and the ledger (UPDATE entries), not in working memory:
they are control records. Everything a later run needs (cursors, the late queue, pending
refinements) is in working memory.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from axelrod_wm.events.graph_update import ChangeValue, GraphUpdateEvent, ObserveValue
from axelrod_wm.events.market import MarketEvent, MarketEventChannel, MarketEventKind
from axelrod_wm.repo.ledger import LedgerKind
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.control.controller import WorldModelController


class UserMarketEventInput(BaseModel):
    """What the user types in. The controller turns it into a MarketEvent with id ME-U-<n>,
    channel USER, source "user", and occurred_at = published_at unless given."""

    model_config = ConfigDict(extra="forbid")

    headline: str
    body: str = ""
    kind: MarketEventKind = MarketEventKind.ANALYST
    published_at: datetime | None = None     # default: requested_at, kept inside the window
    occurred_at: datetime | None = None
    mentions: list[str] = []
    tags: list[str] = []


class UpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_by: str                                   # "user", "schedule", "scenario", or "init"
    until: date                                         # last day to process; sources are polled through its end
    requested_at: datetime | None = None                # simulated time of the request; default: now
    user_market_events: list[MarketEvent | UserMarketEventInput] = []   # full MarketEvents only from scenario files
    user_graph_update_events: list[GraphUpdateEvent] = []   # drawn by the user; model edits only
    sources: list[str] | None = None                    # None: config.update.sources


class UpdateState(StrEnum):
    COLLECTING = "collecting"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"


class UpdateReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: int
    collected: dict[str, int]          # source name (or "user") -> new market events
    duplicates_dropped: int
    late_collected: int                # published before the first day; folded in on the first day
    translated: int
    not_translated: list[str]          # market event ids with no translation
    auto_applied: int
    approved: int
    rejected: int
    deferred: int
    late_folded: int                   # from wm.late_queue
    pending_refinements_created: int
    model_edits_proposed: list[str]    # proposal ids raised during the run (promotions, admissions, ...)
    biggest_moves: list[tuple[str, float]]   # subentity, change in z over the run (top 10)
    reposed_theses: list[str]
    version_before: int
    version_after: int


class UpdateRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str                            # UPD-<n>
    request: UpdateRequest
    state: UpdateState
    first_day: int
    last_day: int
    current_day: int | None = None
    queue: dict[int, list[str]] = {}   # day -> market event ids, in published_at order
    cursor: int = 0                    # position in the current day's queue
    proposals: dict[int, list[str]] = {}   # day -> world-event proposal ids
    waiting_on: str | None = None      # the proposal the run is paused at
    report: UpdateReport | None = None
    started_at: datetime
    finished_at: datetime | None = None
    # bookkeeping for resuming and for the report
    requested_at: datetime | None = None
    late_from: dict[str, int] = {}     # market event id -> the day it was published (queued late)
    walk: dict[str, list[str]] = {}    # market event id -> its world-event proposal ids
    handled: list[str] = []            # world-event proposals folded, rejected, or deferred
    predicted_day: int | None = None   # the last day whose predict step ran
    collected: dict[str, int] = {}
    duplicates_dropped: int = 0
    duplicate_ids: list[str] = []
    late_collected: int = 0
    late_folded: int = 0
    model_edits: list[str] = []
    version_before: int = 0
    cancel_requested: bool = False
    error: str | None = None


def end_of(day: date) -> datetime:
    return datetime.combine(day, time(23, 59, 59), tzinfo=UTC)


def has_world_ops(event: GraphUpdateEvent) -> bool:
    return any(isinstance(op, (ObserveValue, ChangeValue)) for op in event.ops)


class UpdateCycle:
    def __init__(self, controller: WorldModelController) -> None:
        self.c = controller

    # -- helpers ---------------------------------------------------------------------------
    @property
    def engine(self) -> Any:
        return self.c.engine

    def _ledger(self, run: UpdateRun, state: str, **extra: Any) -> None:
        payload = {"update_id": run.id, "state": state, "requested_by": run.request.requested_by,
                   "until": run.request.until.isoformat(), "first_day": run.first_day, "last_day": run.last_day,
                   **extra}
        self.engine.ledger.append(LedgerKind.UPDATE, payload, recorded_at=self.c.now)

    def _date(self, day: int) -> date:
        return self.engine.wm.deviations.date_of(day)

    # -- start -----------------------------------------------------------------------------
    def start(self, request: UpdateRequest, *, run_to_end: bool = True) -> UpdateRun:
        """Validate, collect, apply model edits, and (by default) walk the days until the run is done
        or pauses for review."""
        c = self.c
        eng = self.engine
        wm = eng.wm
        if c.active_update is not None and c.updates[c.active_update].state not in (
                UpdateState.DONE, UpdateState.CANCELLED, UpdateState.FAILED):
            from axelrod_wm.control.controller import ControllerError

            raise ControllerError(f"update run {c.active_update} is still active")
        requested_at = request.requested_at or c.now
        if requested_at.tzinfo is None:
            requested_at = requested_at.replace(tzinfo=UTC)
        c.advance_now(max(requested_at, wm.clock) if request.requested_by != "init" else wm.clock)
        dev = wm.deviations
        first = int(wm.last_processed_day) + 1
        last = dev.day_of_date(request.until)
        run = UpdateRun(id=c.ids.next("UPD"), request=request, state=UpdateState.COLLECTING, first_day=first,
                        last_day=last, started_at=c.now, requested_at=requested_at, version_before=eng.version)
        c.updates[run.id] = run
        eng.tracer.emit(Phase.UPDATE, "update.started", refs=[run.id], update_id=run.id,
                        requested_by=request.requested_by, until=request.until.isoformat(), first_day=first,
                        last_day=last, first_date=dev.date_of(first).isoformat(),
                        last_date=request.until.isoformat())
        self._ledger(run, "started", request=request.model_dump(mode="json"))
        if last < first:
            # nothing to process; nothing is collected
            run.state = UpdateState.DONE
            run.finished_at = c.now
            run.report = self._report(run, reposed=[])
            self._ledger(run, "done", report=run.report.model_dump(mode="json"))
            eng.tracer.emit(Phase.UPDATE, "update.done", refs=[run.id], update_id=run.id,
                            report=run.report.model_dump(mode="json"))
            return run
        c.active_update = run.id
        try:
            self._collect(run, requested_at)
            self._model_edits(run)
            run.state = UpdateState.RUNNING
            run.current_day = first
            if run_to_end:
                self.run_days(run)
        except Exception as exc:
            self._fail(run, exc)
            raise
        return run

    def _fail(self, run: UpdateRun, exc: Exception) -> None:
        run.state = UpdateState.FAILED
        run.error = f"{type(exc).__name__}: {exc}"
        run.finished_at = self.c.now
        if self.c.active_update == run.id:
            self.c.active_update = None
        self._ledger(run, "failed", error=run.error)
        self.engine.tracer.emit(Phase.UPDATE, "update.failed", refs=[run.id], update_id=run.id, error=run.error)

    # -- collect ---------------------------------------------------------------------------
    def _collect(self, run: UpdateRun, requested_at: datetime) -> None:
        c = self.c
        eng = self.engine
        wm = eng.wm
        dev = wm.deviations
        end = end_of(run.request.until)
        names = run.request.sources if run.request.sources is not None else list(eng.config.update.sources)
        new_events: list[MarketEvent] = []
        cursors: dict[str, datetime] = {}
        for name in names:
            src = c.source(name)
            since = wm.source_cursors.get(name)
            polled = src.poll(since, end)
            dropped = int(getattr(src, "last_dropped", 0))
            fresh = []
            for ev in polled:
                status = c.collect_status(ev)
                if status == "duplicate":
                    dropped += 1
                    run.duplicate_ids.append(ev.id)
                    continue
                if status == "processed":
                    continue        # returned again after an earlier run's request time: already folded
                fresh.append(ev)
            run.collected[name] = len(fresh)
            run.duplicates_dropped += dropped
            new_events.extend(fresh)
            cursors[name] = min(end, requested_at) if run.request.requested_by != "init" else end
            eng.tracer.emit(Phase.COLLECT, "scrape.result", refs=[e.id for e in fresh][:50], update_id=run.id,
                            source=name, fetched=len(polled), new=len(fresh), duplicates_dropped=dropped)
        # the user's typed events, kept inside the window
        n_user = 0
        for item in run.request.user_market_events:
            ev = self._user_event(item, run, requested_at)
            if c.collect_status(ev) == "duplicate":
                run.duplicates_dropped += 1
                run.duplicate_ids.append(ev.id)
                continue
            new_events.append(ev)
            n_user += 1
        if run.request.user_market_events:
            run.collected["user"] = n_user
        # record, queue, and put the cursors
        for ev in sorted(new_events, key=lambda e: (e.published_at, e.id)):
            ev = ev.model_copy(update={"update_id": run.id})
            first_time = c.remember_market_event(ev)
            if first_time:
                eng.ledger.append(LedgerKind.MARKET_EVENT, ev, occurred_at=ev.occurred_at, recorded_at=c.now)
            day = dev.day_of(ev.published_at)
            if day < run.first_day:
                run.late_from[ev.id] = day
                run.late_collected += 1
                day = run.first_day
            day = min(day, run.last_day)
            run.queue.setdefault(day, []).append(ev.id)
        for day in run.queue:
            run.queue[day].sort(key=lambda i: (c.market_events[i].published_at, i))
        if cursors:
            with eng.mutator.begin(f"collect:{run.id}", at=wm.clock, process="intake",
                                   message=f"Collect {run.id}: move the sources' cursors") as txn:
                for name, at in sorted(cursors.items()):
                    txn.put("wm.source_cursors", name, at)
        eng.tracer.emit(Phase.COLLECT, "update.collected", refs=[i for q in run.queue.values() for i in q][:100],
                        update_id=run.id,
                        by_day={self._date(d).isoformat(): [{"id": i, "channel": str(c.market_events[i].channel),
                                                              "headline": c.market_events[i].headline[:120]}
                                                             for i in ids]
                                for d, ids in sorted(run.queue.items())},
                        collected=dict(run.collected), duplicates_dropped=run.duplicates_dropped,
                        late=sorted(run.late_from))

    def _user_event(self, item: MarketEvent | UserMarketEventInput, run: UpdateRun,
                    requested_at: datetime) -> MarketEvent:
        if isinstance(item, MarketEvent):
            ev = item
            if ev.channel != MarketEventChannel.USER:
                ev = ev.model_copy(update={"channel": MarketEventChannel.USER})
            return ev
        c = self.c
        dev = self.engine.wm.deviations
        lo = dev.day_start(run.first_day)
        hi = end_of(run.request.until)
        pub = item.published_at or requested_at
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=UTC)
        pub = min(max(pub, lo), hi)
        n = c.ids.next("ME-U").split("-")[-1].lstrip("0") or "0"
        return MarketEvent(id=f"ME-U-{n}", kind=item.kind, channel=MarketEventChannel.USER, source="user",
                           headline=item.headline, body=item.body, published_at=pub,
                           occurred_at=item.occurred_at or pub, mentions=list(item.mentions), tags=list(item.tags))

    def _model_edits(self, run: UpdateRun) -> None:
        """The user's drawn events apply as model edits (§7.6), at wm.clock when the run starts."""
        for ev in run.request.user_graph_update_events:
            p = self.c.submit_graph_update(ev, by=run.request.requested_by, update_id=run.id)
            run.model_edits.append(p.id)

    # -- the day loop ----------------------------------------------------------------------
    def run_days(self, run: UpdateRun, max_days: int | None = None) -> UpdateRun:
        """Process days until the run is done, pauses for review, or `max_days` days are closed
        (the API's background task processes one day at a time, releasing the lock between days)."""
        closed = 0
        while run.state == UpdateState.RUNNING:
            d = run.current_day if run.current_day is not None else run.first_day
            if d > run.last_day:
                self._finish(run)
                break
            if not self.step_day(run, d):
                break                     # paused for review
            closed += 1
            if run.cancel_requested:
                self._finish(run, cancelled=True)
                break
            if max_days is not None and closed >= max_days:
                break
        return run

    def step_day(self, run: UpdateRun, d: int) -> bool:
        """Process day d to its end. Returns False if the run paused for review."""
        c = self.c
        eng = self.engine
        dev = eng.wm.deviations
        if run.predicted_day != d:
            c.advance_now(dev.day_start(d))
            with eng.tracer.scoped(f"day:{dev.date_of(d).isoformat()}"):
                eng.tracer.emit(Phase.UPDATE, "update.day", refs=[run.id], update_id=run.id, day=d,
                                date=dev.date_of(d).isoformat(), queued=list(run.queue.get(d, [])))
                self._predict(d)
            run.predicted_day = d
            run.cursor = 0
            run.late_folded += self._fold_late_queue(run, d)
        if not self._walk(run, d):
            return False
        self._close_day(run, d)
        run.current_day = d + 1
        return True

    def _predict(self, d: int) -> None:
        """Working memory opens the day: its prediction, before the day's events."""
        self.engine.learning.open_day(d)

    def _fold_late_queue(self, run: UpdateRun, d: int) -> int:
        """Proposals approved after their day are folded in first on the next processed day."""
        c = self.c
        wm = self.engine.wm
        n = 0
        for pid, due in sorted(wm.late_queue.items(), key=lambda kv: (kv[1], kv[0])):
            p = c.proposals.get(pid)
            if p is None:
                with self.engine.mutator.begin(f"late:{pid}", at=wm.deviations.day_start(d)) as txn:
                    txn.remove("wm.late_queue", pid)
                continue
            c.fold_world_event(p, d, late_from=int(due), update_id=run.id)
            n += 1
        return n

    def _walk(self, run: UpdateRun, d: int) -> bool:
        """Walk the day's queue in published_at order from run.cursor. Returns False if it paused."""
        queue = run.queue.get(d, [])
        pause = bool(self.engine.config.update.pause_for_review)
        while run.cursor < len(queue):
            me_id = queue[run.cursor]
            if not self._walk_one(run, d, me_id, pause):
                return False
            run.cursor += 1
        return True

    def _walk_one(self, run: UpdateRun, d: int, me_id: str, pause: bool) -> bool:
        """One market event of the day: ingest it once, then fold, defer, or wait on its proposals."""
        from axelrod_wm.repo.review import ProposalStatus

        c = self.c
        eng = self.engine
        dev = eng.wm.deviations
        with eng.tracer.scoped(me_id):
            if me_id not in run.walk:
                ev = c.market_events[me_id]
                now = max(ev.published_at, dev.day_start(d))
                c.advance_now(now)
                props = c.pipeline.ingest(ev, now)
                ids = []
                for p in props:
                    p.update_id = run.id
                    p.due_day = d
                    ids.append(p.id)
                run.walk[me_id] = ids
                run.proposals.setdefault(d, []).extend(ids)
            for pid in run.walk[me_id]:
                if pid in run.handled:
                    continue
                p = c.proposals[pid]
                if p.status == ProposalStatus.PENDING and not p.needs_review:
                    c.fold_world_event(p, d, auto=True, update_id=run.id)
                elif p.status == ProposalStatus.APPROVED and p.folded_day is None:
                    c.fold_world_event(p, d, update_id=run.id)
                elif p.status == ProposalStatus.PENDING:
                    if pause and not run.cancel_requested:
                        run.waiting_on = pid
                        run.state = UpdateState.AWAITING_REVIEW
                        # the run's own state goes in the entry, so a restart can pick the run up where it paused
                        self._ledger(run, "awaiting_review", proposal_id=pid, day=d, run_state=run.model_dump(mode="json"))
                        eng.tracer.emit(Phase.UPDATE, "update.awaiting_review", refs=[run.id, pid],
                                        update_id=run.id, day=d, date=dev.date_of(d).isoformat(),
                                        proposal_ids=[pid])
                        return False
                    c.defer(pid, by="update")
                run.handled.append(pid)
        return True

    def _close_day(self, run: UpdateRun, d: int) -> None:
        """The day's end: working memory records it, long-term memory distills it, and working memory
        closes it (which sets wm.clock to the end of d). Snapshots on schedule."""
        c = self.c
        eng = self.engine
        dev = eng.wm.deviations
        end = dev.day_end(d)
        c.advance_now(end)
        with eng.tracer.scoped(f"day:{dev.date_of(d).isoformat()}"):
            report = eng.learning.close_day(d, end)
            ids = []
            for pe in report.proposal_events:
                p = c.propose(pe["kind"], pe["event"], reasons=[pe.get("reason", "")],
                              subject_id=pe.get("subject_id"), update_id=run.id)
                ids.append(p.id)
        run.model_edits.extend(ids)
        report.proposals = ids
        report.proposal_events = []
        c.consolidations.append(report)
        every = max(1, int(eng.config.snapshots.every_days))
        if (d - run.first_day + 1) % every == 0:
            eng.save_snapshot()

    # -- resume, cancel, finish ------------------------------------------------------------
    def resume(self, run: UpdateRun, *, run_to_end: bool = True) -> UpdateRun:
        """Called when the awaited proposal is decided (or by continue_update, which defers it first)."""
        from axelrod_wm.repo.review import ProposalStatus

        c = self.c
        if run.state != UpdateState.AWAITING_REVIEW:
            return run
        p = c.proposals.get(run.waiting_on)          # a paused run always waits on a proposal
        if p is not None and p.status == ProposalStatus.PENDING:
            c.defer(p.id, by="update")
        run.waiting_on = None
        run.state = UpdateState.RUNNING
        self._ledger(run, "resumed", day=run.current_day)
        self.engine.tracer.emit(Phase.UPDATE, "update.resumed", refs=[run.id], update_id=run.id, day=run.current_day)
        if run_to_end:
            try:
                self.run_days(run)
            except Exception as exc:
                self._fail(run, exc)
                raise
        return run

    def cancel(self, run: UpdateRun) -> UpdateRun:
        """Never leaves a day half done: defers the awaited proposal, walks the rest of the current day
        with every event that would need review deferred, closes that day, and stops. Cursors are put
        back to the end of the last processed day so the next run collects the rest again."""
        c = self.c
        if run.state in (UpdateState.DONE, UpdateState.CANCELLED, UpdateState.FAILED):
            return run
        run.cancel_requested = True
        if run.state == UpdateState.AWAITING_REVIEW:     # a paused run always waits on a proposal
            run.state = UpdateState.RUNNING
            c.defer(run.waiting_on, by="cancel")
            run.waiting_on = None
        # the run is running (or still collecting): finish the day in progress, then stop
        d = run.current_day if run.current_day is not None else run.first_day
        if run.predicted_day == d and d <= run.last_day:
            self._walk(run, d)
            self._close_day(run, d)
            run.current_day = d + 1
        self._finish(run, cancelled=True)
        return run

    def _finish(self, run: UpdateRun, cancelled: bool = False) -> None:
        c = self.c
        eng = self.engine
        wm = eng.wm
        if cancelled:
            # unprocessed queued events will be collected again by the next run
            back = wm.clock
            names = run.request.sources if run.request.sources is not None else list(eng.config.update.sources)
            with eng.mutator.begin(f"cancel:{run.id}", at=wm.clock) as txn:
                for name in names:
                    cur = wm.source_cursors.get(name)
                    if cur is None or cur > back:
                        txn.put("wm.source_cursors", name, back)
            for day, ids in run.queue.items():
                if day > wm.last_processed_day:
                    for i in ids:
                        c.market_status[i] = "queued"
        eng.save_snapshot()
        reposed: list[str] = []
        if not cancelled and eng.config.update.repose_pinned and run.request.requested_by != "init":
            reposed = c.repose_pinned()
        run.report = self._report(run, reposed)
        run.state = UpdateState.CANCELLED if cancelled else UpdateState.DONE
        run.finished_at = c.now
        run.current_day = min(run.current_day or run.first_day, run.last_day + 1)
        if c.active_update == run.id:
            c.active_update = None
        self._ledger(run, "cancelled" if cancelled else "done", report=run.report.model_dump(mode="json"))
        eng.tracer.emit(Phase.UPDATE, "update.done", refs=[run.id], update_id=run.id, state=str(run.state),
                        report=run.report.model_dump(mode="json"))

    def _report(self, run: UpdateRun, reposed: list[str]) -> UpdateReport:
        from axelrod_wm.repo.review import ProposalStatus

        c = self.c
        eng = self.engine
        wm = eng.wm
        dev = wm.deviations
        world = [c.proposals[p] for ids in run.proposals.values() for p in ids if p in c.proposals]
        walked = [i for ids in run.queue.values() for i in ids if i in run.walk]
        not_translated = [i for i in walked if not run.walk[i]]
        moves: list[tuple[str, float]] = []
        last = min(int(wm.last_processed_day), run.last_day)
        if last >= run.first_day:
            for sid in sorted(wm.graph.subentities):
                moves.append((sid, round(dev.z(sid, last) - dev.z(sid, run.first_day - 1), 6)))
            moves.sort(key=lambda m: (-abs(m[1]), m[0]))
        pend_created = sum(len(p.pending) for p in world if p.status in (ProposalStatus.APPROVED,
                                                                        ProposalStatus.AUTO_APPLIED))
        return UpdateReport(
            days=max(0, last - run.first_day + 1), collected=dict(run.collected),
            duplicates_dropped=run.duplicates_dropped, late_collected=run.late_collected,
            translated=sum(1 for i in walked if run.walk[i]), not_translated=not_translated,
            auto_applied=sum(1 for p in world if p.status == ProposalStatus.AUTO_APPLIED),
            approved=sum(1 for p in world if p.status == ProposalStatus.APPROVED),
            rejected=sum(1 for p in world if p.status == ProposalStatus.REJECTED),
            deferred=sum(1 for p in world if p.status == ProposalStatus.DEFERRED),
            late_folded=run.late_folded, pending_refinements_created=pend_created,
            model_edits_proposed=list(run.model_edits), biggest_moves=moves[:10], reposed_theses=reposed,
            version_before=run.version_before, version_after=eng.version)
