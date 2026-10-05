"""The controller façade (§7.6). The API, the CLI, and the scenario runner call only this class."""

from __future__ import annotations

import math
import threading
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from axelrod_wm.control.decisions import DecisionError, DecisionRecord, DecisionTrace, Outcome
from axelrod_wm.control.review import Proposal, ProposalKind, ProposalStatus
from axelrod_wm.core.hypothesis import Hypothesis, HypothesisKind, HypothesisStatus
from axelrod_wm.core.ids import IdFactory
from axelrod_wm.engine.performance.task import UnboundThesis
from axelrod_wm.engine.registry import registry
from axelrod_wm.events.graph_update import ChangeValue, EventKind, GraphUpdateEvent
from axelrod_wm.events.ledger import LedgerKind
from axelrod_wm.events.market import MarketEvent
from axelrod_wm.events.thesis import Thesis, ThesisMode
from axelrod_wm.ingest.pipeline import IngestionPipeline
from axelrod_wm.memory.frontier import CoMovementStatus, pair_key
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.control.mutator import ChangeSet
    from axelrod_wm.engine.consolidate import ConsolidationReport
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
        self.ids = IdFactory(counters=dict(control_ids or {}))
        self.now: datetime = engine.wm.clock
        self.lock = threading.RLock()
        self.pipeline = IngestionPipeline(self)
        self._translators: dict[str, Any] = {}
        self.auto_consolidate = True
        self.listeners: list[Any] = []          # callables (kind, **info), e.g. the scenario checklist

    # ---------------------------------------------------------------------------------------
    # plumbing
    # ---------------------------------------------------------------------------------------
    @property
    def config(self) -> Any:
        return self.engine.config

    def translator_for(self, kind: str) -> Any:
        if kind not in self._translators:
            name, params = self.config.translator(kind)
            cls = registry("translator").get(name)
            kwargs: dict[str, Any] = dict(params)
            if name == "hand_drawn" and "directory" not in kwargs and self.scenario_dir is not None:
                kwargs["directory"] = self.scenario_dir / "translations"
            self._translators[kind] = cls(config=self.config, **kwargs)
        return self._translators[kind]

    def set_time(self, t: datetime) -> list[ConsolidationReport]:
        """Advance the simulation clock, consolidating at each day boundary that had applied events."""
        reports = []
        days = self.engine.wm.touched_days()
        if self.auto_consolidate and days and t.date() > days[-1]:
            reports.append(self.consolidate(days[-1]))
        if t > self.now:
            self.now = t
        self.engine.tracer.set_context(sim_time=self.now, state_version=self.engine.version)
        return reports

    def refine(self, event: GraphUpdateEvent, now: datetime | None = None) -> RefinementResult:
        ctx = self.engine.context(learn=event.kind == EventKind.REAL, now=now or self.now)
        return self.engine.components["refiner"].refine(event, self.engine.wm, self.engine.ltm, ctx)

    def _ledger_proposal(self, p: Proposal) -> None:
        self.engine.ledger.append(LedgerKind.PROPOSAL, p, recorded_at=self.now)

    def _decision_entry(self, p: Proposal, action: str, by: str, note: str | None, diff: dict | None = None) -> None:
        self.engine.ledger.append(LedgerKind.REVIEW_DECISION, {
            "proposal_id": p.id, "kind": str(p.kind), "action": action, "by": by, "note": note,
            "decided_at": self.now.isoformat(), "changeset_id": p.changeset_id, "diff": diff}, recorded_at=self.now)

    # ---------------------------------------------------------------------------------------
    # proposals
    # ---------------------------------------------------------------------------------------
    def propose(self, kind: str | ProposalKind, event: GraphUpdateEvent | dict, *, steps: list | None = None,
                pending: list | None = None, soft_support: dict | None = None, market_event_id: str | None = None,
                reasons: list[str] | None = None, subject_id: str | None = None,
                retires_pending_id: str | None = None) -> Proposal:
        if isinstance(event, dict):
            event = GraphUpdateEvent.model_validate(event)
        p = Proposal(id=self.ids.next("PR"), kind=ProposalKind(kind), event=event,
                     market_event_id=market_event_id or event.market_event_id, refinement_steps=steps or [],
                     created_at=self.now, pending=pending or [], soft_support=soft_support or {},
                     retires_pending_id=retires_pending_id, subject_id=subject_id,
                     reason="; ".join(reasons or []) or None)
        req = self.engine.components["review_policy"].assess(p, self.engine.wm)
        p.review_reasons = req.reasons
        self.proposals[p.id] = p
        self._ledger_proposal(p)
        self._notify("proposed", proposal=p)
        if req.needs_review:
            p.status = ProposalStatus.PENDING
            if p.market_event_id:
                self.market_status[p.market_event_id] = "awaiting review"
            self.engine.tracer.emit(Phase.REVIEW, "review.queued", refs=[p.id, event.id], proposal_id=p.id,
                                    kind=str(p.kind), reasons=p.review_reasons, subject_id=subject_id,
                                    market_event_id=p.market_event_id)
        else:
            self.engine.tracer.emit(Phase.REVIEW, "review.auto", refs=[p.id, event.id], proposal_id=p.id,
                                    kind=str(p.kind), reasons=[], subject_id=subject_id,
                                    market_event_id=p.market_event_id)
            self._apply(p, by="policy", note=None, auto=True)
        return p

    def submit_graph_update(self, event: GraphUpdateEvent, by: str) -> Proposal:
        with self.lock:
            event = event.model_copy(update={"produced_by": event.produced_by or "human"})
            ref = self.refine(event)
            return self.propose(ProposalKind.GRAPH_UPDATE, ref.event, steps=ref.steps, pending=ref.pending,
                                soft_support=ref.soft_support)

    def _apply(self, p: Proposal, by: str, note: str | None, auto: bool) -> ChangeSet | None:
        eng = self.engine
        ev = p.event
        result = None
        headline = None
        if p.market_event_id and p.market_event_id in self.market_events:
            headline = self.market_events[p.market_event_id].headline
        before_seq = eng.ledger.next_seq
        with eng.mutator.begin(cause=p.id, now=self.now) as txn:
            for pend in p.pending:
                txn.add("pending_refinements", pend.model_copy(update={"id": txn.new_id("PEND"), "created_at": self.now}))
            for gid, amount in sorted(p.soft_support.items()):
                node = eng.ltm.interaction_taxonomy.nodes.get(gid)
                if node is not None:
                    st = node.stats.model_copy(deep=True)
                    st.support += float(amount)
                    txn.update("generalizations.interaction", gid, stats=st)
            if p.retires_pending_id and p.retires_pending_id in eng.wm.pending_refinements:
                txn.remove("pending_refinements", p.retires_pending_id)
            if ev.ops:
                if p.kind in (ProposalKind.GRAPH_UPDATE, ProposalKind.REFINEMENT) and ev.kind == EventKind.REAL:
                    result = eng.learning.run(ev, self.now, headline=headline)
                else:
                    eng.structural.apply(ev, self.now, str(p.kind))
            if p.kind == ProposalKind.FRONTIER_PROMOTION and p.subject_id in eng.ltm.frontier.entries:
                txn.update("frontier", p.subject_id, status=CoMovementStatus.PROMOTED)
        cs = eng.mutator.last_changeset if eng.ledger.next_seq > before_seq else None
        p.status = ProposalStatus.AUTO_APPLIED if auto else ProposalStatus.APPROVED
        p.decided_at, p.decided_by, p.note = self.now, by, note
        p.changeset_id = cs.id if cs is not None else None
        p.version_after = eng.version
        self._decision_entry(p, "auto_applied" if auto else "approved", by, note)
        eng.tracer.emit(Phase.REVIEW, "review.decided", refs=[p.id, ev.id], proposal_id=p.id, kind=str(p.kind),
                        decision=str(p.status), by=by, changeset_id=p.changeset_id, version=eng.version,
                        market_event_id=p.market_event_id)
        if ev.kind == EventKind.REAL and ev.ops:
            self.applied_events.append(ev)
        if p.market_event_id:
            self.market_status[p.market_event_id] = "applied"
        self._notify("applied", proposal=p, result=result)
        # follow-ups: engine proposals and retried refinements
        if result is not None:
            for pe in result.proposal_events:
                self.propose(pe["kind"], pe["event"], reasons=[pe.get("reason", "")], subject_id=pe.get("subject_id"))
        if ev.kind == EventKind.REAL and ev.ops:
            self._retry_pending(ev)
        return cs

    def _retry_pending(self, applied: GraphUpdateEvent) -> None:
        eng = self.engine
        if not eng.wm.pending_refinements:
            return
        ctx = eng.context(learn=True, now=self.now)
        open_ids = {p.retires_pending_id for p in self.proposals.values()
                    if p.kind == ProposalKind.REFINEMENT and p.status in (ProposalStatus.PENDING, ProposalStatus.DEFERRED)}
        for ev in eng.components["refiner"].retry_pending(applied, eng.wm, eng.ltm, ctx):
            pid = ev.id[len("GUE-REF-"):] if ev.id.startswith("GUE-REF-") else None
            if pid in open_ids or pid not in eng.wm.pending_refinements:
                continue
            open_ids.add(pid)
            self.propose(ProposalKind.REFINEMENT, ev, retires_pending_id=pid, reasons=[f"new evidence from {applied.id}"])

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

    def approve(self, proposal_id: str, by: str, note: str | None = None) -> ChangeSet | None:
        with self.lock:
            p = self._get_open(proposal_id)
            return self._apply(p, by=by, note=note, auto=False)

    def reject(self, proposal_id: str, by: str, note: str) -> None:
        with self.lock:
            p = self._get_open(proposal_id)
            eng = self.engine
            if p.kind == ProposalKind.FRONTIER_PROMOTION and p.subject_id in eng.ltm.frontier.entries:
                co = eng.ltm.frontier.entries[p.subject_id]
                until = self.now + timedelta(days=float(self.config.frontier.reject_cooldown_days))
                with eng.mutator.begin(cause=p.id, now=self.now) as txn:
                    txn.update("frontier", co.id, status=CoMovementStatus.DECAYED)
                    if co.hypothesis_id in eng.wm.hypotheses:
                        txn.update("hypotheses", co.hypothesis_id, status=HypothesisStatus.REFUTED)
                    txn.merge("ltm.frontier.blocked_until", {pair_key(co.earlier_id, co.later_id): until})
            p.status = ProposalStatus.REJECTED
            p.decided_at, p.decided_by, p.note = self.now, by, note
            self._decision_entry(p, "rejected", by, note)
            if p.market_event_id:
                self.market_status[p.market_event_id] = "rejected"
            eng.tracer.emit(Phase.REVIEW, "review.decided", refs=[p.id, p.event.id], proposal_id=p.id, kind=str(p.kind),
                            decision="rejected", by=by, note=note, market_event_id=p.market_event_id)

    def edit(self, proposal_id: str, event: GraphUpdateEvent, by: str) -> Proposal:
        with self.lock:
            p = self._get_open(proposal_id)
            old = p.event
            ref = self.refine(event)
            if p.edited_from is None:
                p.edited_from = old
            p.event = ref.event
            p.refinement_steps = ref.steps
            p.pending = ref.pending
            p.soft_support = ref.soft_support
            diff = {"before": old.model_dump(mode="json"), "after": ref.event.model_dump(mode="json")}
            self._decision_entry(p, "edited", by, None, diff)
            self.engine.tracer.emit(Phase.REVIEW, "review.decided", refs=[p.id, ref.event.id], proposal_id=p.id,
                                    kind=str(p.kind), decision="edited", by=by)
            return p

    def defer(self, proposal_id: str, by: str) -> None:
        with self.lock:
            p = self._get_open(proposal_id)
            p.status = ProposalStatus.DEFERRED
            p.decided_by = by
            self._decision_entry(p, "deferred", by, None)
            self.engine.tracer.emit(Phase.REVIEW, "review.decided", refs=[p.id], proposal_id=p.id, kind=str(p.kind),
                                    decision="deferred", by=by)

    def pending_proposals(self) -> list[Proposal]:
        return [p for p in self.proposals.values() if p.status == ProposalStatus.PENDING]

    def set_review_policy(self, name: str) -> None:
        with self.lock:
            policy = registry("review_policy").create(name, config=self.config)
            self.engine.components["review_policy"] = policy
            self.config.review.policy = name

    # ---------------------------------------------------------------------------------------
    # market events
    # ---------------------------------------------------------------------------------------
    def ingest(self, market_event: MarketEvent) -> list[Proposal]:
        with self.lock:
            t = max(self.now, market_event.published_at)
            self.set_time(t)
            return self.pipeline.ingest(market_event, t)

    # ---------------------------------------------------------------------------------------
    # theses and hypotheses
    # ---------------------------------------------------------------------------------------
    def thesis_from_question(self, question: str, *, horizon_days: int = 182, targets: list[str] | None = None,
                             posed_by: str = "human") -> Thesis:
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
            "targets": targets or [], "posed_by": posed_by, "posed_at": self.now.isoformat(),
            "event": {"id": f"GUE-{tid}", "kind": "hypothetical", "occurred_at": ops[0]["at"],
                      "recorded_at": self.now.isoformat(), "produced_by": "template", "ops": ops}})

    def pose_thesis(self, thesis: Thesis | str) -> Forecast:
        with self.lock:
            if isinstance(thesis, str):
                thesis = self.thesis_from_question(thesis)
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
            with eng.mutator.begin(cause=f"hypothesis:{hypothesis.id}", now=self.now) as txn:
                hid = hypothesis.id if hypothesis.id and hypothesis.id not in eng.wm.hypotheses else txn.new_id("H")
                h = hypothesis.model_copy(update={"id": hid, "scored_at": self.now})
                scorer = eng.components["hypothesis_scorer"]
                h = h.model_copy(update={"probability": scorer.probability(h, eng.wm, eng.ltm, ctx)})
                txn.add("hypotheses", h)
                scorer.rescore(h, eng.wm, eng.ltm, ctx, txn, force=True)
            return eng.wm.hypotheses[hid]

    def set_hypothesis_status(self, hypothesis_id: str, status: str) -> Hypothesis:
        with self.lock:
            eng = self.engine
            if hypothesis_id not in eng.wm.hypotheses:
                raise ControllerError(f"unknown hypothesis {hypothesis_id}")
            with eng.mutator.begin(cause=f"hypothesis:{hypothesis_id}", now=self.now) as txn:
                txn.update("hypotheses", hypothesis_id, status=HypothesisStatus(status))
            return eng.wm.hypotheses[hypothesis_id]

    # ---------------------------------------------------------------------------------------
    # consolidation, evaluation
    # ---------------------------------------------------------------------------------------
    def consolidate(self, day: date) -> ConsolidationReport:
        with self.lock:
            eng = self.engine
            at = max(end_of_day(day), self.now) if self.now.date() == day else end_of_day(day)
            ctx = eng.context(learn=True, now=at)
            report = eng.components["consolidator"].run(day, ctx)
            ids = []
            for pe in report.proposal_events:
                p = self.propose(pe["kind"], pe["event"], reasons=[pe.get("reason", "")], subject_id=pe.get("subject_id"))
                ids.append(p.id)
            report.proposals = ids
            report.proposal_events = []
            self.consolidations.append(report)
            return report

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

        ltm = self.engine.ltm
        if explanation_id in ltm.explanations.explanations:
            return ltm.explanations.explanations[explanation_id]
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
            from axelrod_wm.evaluation.backtest import pattern_hit, realized_series
            from axelrod_wm.evaluation.metrics import crps_quantiles

            rec = self.decisions.get(decision_id)
            if rec is None:
                raise DecisionError(f"unknown decision {decision_id}")
            if self.now < rec.review_after:
                raise DecisionError(f"decision {decision_id} can be resolved after {rec.review_after.isoformat()}")
            base = next(f for f in (self.forecast(i) for i in rec.forecast_ids) if f is not None and f.is_baseline)
            eng = self.engine
            dev = eng.wm.deviations
            steps = max(1, min(base.horizon_steps, int(math.floor((self.now - base.created_at).days / base.step_days))))
            realized: dict[str, float] = {}
            crps = []
            series: dict[str, list] = {}
            for sid in base.targets:
                s = realized_series(dev, sid, base.created_at, base.horizon_steps, base.step_days)
                series[sid] = s
                y = s[steps] if steps < len(s) else None
                if y is None or sid not in base.z_summary:
                    continue
                realized[sid] = float(y)
                crps.append(crps_quantiles(base.z_summary[sid][steps], float(y)))
            outcome = Outcome(resolved_at=self.now, realized=realized,
                              crps=float(sum(crps) / len(crps)) if crps else 0.0,
                              notes=f"scored at step {steps} of the baseline forecast {base.id}")
            hits = {}
            sig = float(self.config.evaluation.significant_effect)
            for n in base.networks:
                if n.pattern_id:
                    hit = pattern_hit(n.subentity_ids, base, series, sig)
                    if hit is not None:
                        hits[n.pattern_id] = hit
            with eng.mutator.begin(cause=f"outcome:{decision_id}", now=self.now) as txn:
                if hits:
                    txn.set("ltm.reliability", eng.ltm.reliability.updated(hits))
                txn.set("wm.pending_episode_tags", sorted(set(eng.wm.pending_episode_tags) | {"decision-outcome"}))
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

