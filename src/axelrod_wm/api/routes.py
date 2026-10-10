"""HTTP endpoints (§12.1). Handlers run engine calls in a worker thread under the app lock (§12.4)."""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from typing import Any

import yaml
from fastapi import APIRouter, Body, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from axelrod_wm.api.app import AppState
from axelrod_wm.api.views import (
    entity_view,
    forecast_view,
    hypothesis_evidence,
    hypothesis_view,
    interaction_view,
    learning_tasks_view,
    memory_summary,
    pattern_view,
    proposal_view,
    taxonomy_view,
    update_run_view,
)
from axelrod_wm.control.updates import UpdateRequest, UpdateState, UserMarketEventInput, end_of, has_world_ops
from axelrod_wm.engine.initialize import resolve_path
from axelrod_wm.evaluation.backtest import EvaluationRequest
from axelrod_wm.events.graph_update import GraphUpdateEvent
from axelrod_wm.events.thesis import Thesis
from axelrod_wm.model.hypothesis import Hypothesis
from axelrod_wm.sim.scenario import list_scenarios
from axelrod_wm.trace import Phase

router = APIRouter(prefix="/api")


def S(request: Request) -> AppState:
    return request.app.state.axelrod


def _json(model: Any) -> Any:
    if isinstance(model, BaseModel):
        return model.model_dump(mode="json")
    if isinstance(model, list):
        return [_json(m) for m in model]
    return model


class ReviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    by: str = "human"
    note: str | None = None
    keep: list[int] | None = None       # approve only these operations (the reviewer's selection)
    confidence: float | None = None     # the reviewer's confidence in the article's changes, 0..1 (Oct 8)
    op_confidence: dict[int, float | None] | None = None   # per operation index; None returns it to the article's
    ripple: dict[str, float | None] | None = None   # subentity id -> probability its ripple arrives (Oct 9); None: 1


class EditBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    by: str = "human"
    event: GraphUpdateEvent


class PolicyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy: str


class PoseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_thesis_id: str | None = None


class StatusBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str


class UpdateBody(BaseModel):
    """POST /api/updates: every field optional (§12.1)."""

    model_config = ConfigDict(extra="forbid")

    until: date | None = None
    requested_at: datetime | None = None
    requested_by: str = "user"
    user_market_events: list[UserMarketEventInput] = []
    user_graph_update_events: list[GraphUpdateEvent] = []
    sources: list[str] | None = None


class LoadBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: str | None = None
    interactive: bool = True


class PlayBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    until_step: int | None = None


# -- health and config ------------------------------------------------------------------------
@router.get("/health")
async def health(request: Request) -> dict:
    st = S(request)
    version = st.runner.controller.engine.version if st.runner is not None and st.runner.loaded else 0
    return {"ok": True, "version": version}


def _config(st: AppState) -> dict:
    cfg = st.controller.config
    from axelrod_wm.engine.engine import all_slots

    comps = {}
    for slot in all_slots(cfg):
        name, params = cfg.component(slot)
        comps[slot] = {"name": name, "params": params}
    translators = {}
    for kind in cfg.translators:
        translators[kind] = [{"name": name, "params": params} for name, params in cfg.translator_chain(kind)]
    return {"components": comps, "translators": translators,
            "review_policy": cfg.review.policy, "config_hash": cfg.config_hash(),
            "params": cfg.model_dump(mode="json", exclude={"components", "translators"})}


@router.get("/config")
async def get_config(request: Request) -> dict:
    st = S(request)
    return await st.call(_config, st)


@router.patch("/config/review")
async def patch_review(request: Request, body: PolicyBody) -> dict:
    st = S(request)
    if body.policy not in ("default", "auto_approve_all"):
        raise HTTPException(422, f"unknown review policy {body.policy!r}")

    def run() -> dict:
        st.controller.set_review_policy(body.policy)
        return _config(st)

    return await st.call(run)


# -- state and records -------------------------------------------------------------------------
@router.get("/state")
async def get_state(request: Request, version: int | None = None) -> dict:
    st = S(request)
    return await st.call(lambda: _json(st.controller.state_view(version)))


@router.get("/versions")
async def get_versions(request: Request) -> list:
    st = S(request)
    return await st.call(lambda: _json(list(st.controller.engine.storage.versions())))


@router.get("/entities/{entity_id}")
async def get_entity(request: Request, entity_id: str) -> dict:
    st = S(request)
    eng = st.controller.engine
    return await st.call(entity_view, entity_id, eng.wm, eng.ltm)


@router.get("/interactions/{interaction_id}")
async def get_interaction(request: Request, interaction_id: str) -> dict:
    st = S(request)
    eng = st.controller.engine
    return await st.call(interaction_view, interaction_id, eng.wm, eng.ltm)


@router.get("/superentities/{pattern_id}")
async def get_pattern(request: Request, pattern_id: str) -> dict:
    st = S(request)
    eng = st.controller.engine
    return await st.call(pattern_view, pattern_id, eng.wm, eng.ltm)


@router.get("/taxonomies/{kind}")
async def get_taxonomy(request: Request, kind: str) -> dict:
    if kind not in ("object", "interaction"):
        raise HTTPException(404, f"unknown taxonomy {kind!r}")
    st = S(request)
    return await st.call(taxonomy_view, kind, st.controller.engine.ltm, st.controller.config)


@router.get("/find")
async def get_find(request: Request, q: str = Query("", max_length=200)) -> dict:
    """Find (Oct 9): semantic search and filters over entities, values, interactions, and superentities."""
    from axelrod_wm.api.find import find

    st = S(request)
    return await st.call(find, st.controller, q)


@router.get("/checks")
async def get_checks(request: Request) -> dict:
    """Checks (Oct 9): each kind (when it runs, how, what it updates, its bound), and what is being checked now."""
    from axelrod_wm.api.checks import checks_view

    st = S(request)
    return await st.call(checks_view, st.controller)


@router.get("/memory")
async def get_memory(request: Request) -> dict:
    st = S(request)
    eng = st.controller.engine
    return await st.call(memory_summary, eng.wm, eng.ltm, st.controller.config)


@router.get("/learning-tasks")
async def learning_tasks(request: Request) -> list[dict]:
    st = S(request)
    return await st.call(learning_tasks_view, st.controller)


@router.get("/frontier")
async def get_frontier(request: Request) -> list:
    st = S(request)

    def run() -> list:
        eng = st.controller.engine
        dev = eng.wm.deviations
        spacing = int(eng.config.frontier.evidence_spacing_days)
        out = []
        for e in sorted(eng.ltm.correlation_frontier.entries.values(), key=lambda e: (-e.support, e.id)):
            d = e.model_dump(mode="json")
            # the first day the entry may be verified again (evidence spacing, §8.7)
            d["next_eligible"] = (dev.date_of(e.last_verified_day + spacing).isoformat()
                                  if e.last_verified_day is not None else None)
            out.append(d)
        return out

    return await st.call(run)


@router.get("/frontier/{entry_id}/series")
async def get_frontier_series(request: Request, entry_id: str) -> dict:
    st = S(request)

    def run() -> dict:
        co = st.controller.engine.ltm.correlation_frontier.entries[entry_id]
        return {"pairs": [[x, y] for x, y in co.corr.pairs], "lag_days": co.lag_days,
                "earlier": co.earlier_id, "later": co.later_id, "sign": co.sign, "corr": co.corr.corr()}

    return await st.call(run)


# -- hypotheses --------------------------------------------------------------------------------
@router.get("/hypotheses")
async def get_hypotheses(request: Request, sort: str = "voi") -> list:
    st = S(request)

    def run() -> list:
        ctl = st.controller
        hs = list(ctl.engine.wm.hypotheses.values())
        if sort == "voi":
            hs.sort(key=lambda h: (-h.current_value(ctl.now), h.id))
        else:
            hs.sort(key=lambda h: h.id)
        return [hypothesis_view(h, ctl.now) for h in hs]

    return await st.call(run)


@router.post("/hypotheses")
async def post_hypothesis(request: Request, body: dict = Body(...)) -> dict:
    st = S(request)

    def run() -> dict:
        ctl = st.controller
        data = {"probability": 0.5, "scored_at": ctl.now.isoformat(), "id": "", **body}
        h = ctl.add_hypothesis(Hypothesis.model_validate(data))
        return hypothesis_view(h, ctl.now)

    return await st.call(run)


@router.get("/hypotheses/{hypothesis_id}/evidence")
async def get_hypothesis_evidence(request: Request, hypothesis_id: str) -> dict:
    """What bears on a hypothesis: its probability's basis, its series, its evidence, and the news (addition)."""
    st = S(request)

    def run() -> dict:
        ctl = st.controller
        h = ctl.engine.wm.hypotheses[hypothesis_id]
        return hypothesis_evidence(h, ctl)

    return await st.call(run)


@router.post("/hypotheses/{hypothesis_id}/pose")
async def pose_hypothesis(request: Request, hypothesis_id: str, body: PoseBody | None = None) -> dict:
    st = S(request)

    def run() -> dict:
        ctl = st.controller
        fc = ctl.pose_hypothesis(hypothesis_id, body.base_thesis_id if body else None)
        return forecast_view(fc, ctl.explanation(fc.explanation_id), ctl.engine.wm, ctl.watchlist())

    return await st.call(run)


@router.post("/hypotheses/{hypothesis_id}/status")
async def hypothesis_status(request: Request, hypothesis_id: str, body: StatusBody) -> dict:
    st = S(request)

    def run() -> dict:
        ctl = st.controller
        h = ctl.set_hypothesis_status(hypothesis_id, body.status)
        return hypothesis_view(h, ctl.now)

    return await st.call(run)


# -- market events, graph updates, and review ----------------------------------------------------
@router.get("/market-events/{event_id}")
async def get_market_event(request: Request, event_id: str) -> dict:
    st = S(request)

    def run() -> dict:
        ctl = st.controller
        ev = ctl.market_events.get(event_id)
        if ev is None and st.runner is not None and getattr(st.runner, "market_source", None) is not None:
            ev = st.runner.market_source.get(event_id)
        if ev is None:
            raise KeyError(event_id)
        tr = ctl.translations.get(event_id)
        return {"event": ev.model_dump(mode="json"), "translation": _json(tr) if tr is not None else None,
                "status": ctl.market_status.get(event_id)}

    return await st.call(run)


@router.get("/market-events")
async def get_market_events(request: Request, update_id: str | None = Query(None)) -> list:
    """Market events with their channel, day, and status, optionally for one update run."""
    st = S(request)

    def run() -> list:
        ctl = st.controller
        dev = ctl.engine.wm.deviations
        days: dict[str, int] = {}
        runs = [ctl.get_update(update_id)] if update_id else list(ctl.updates.values())
        for r in runs:
            for d, ids in r.queue.items():
                for i in ids:
                    days[i] = d
        out = []
        for mid, ev in ctl.market_events.items():
            if update_id and ev.update_id != update_id:
                continue
            day = days.get(mid, dev.day_of(ev.published_at))
            out.append({"id": mid, "kind": str(ev.kind), "channel": str(ev.channel), "source": ev.source,
                        "headline": ev.headline, "published_at": ev.published_at.isoformat(),
                        "day": dev.date_of(day).isoformat(), "update_id": ev.update_id,
                        "status": ctl.market_status.get(mid, ""), "synthetic": ev.synthetic})
        out.sort(key=lambda x: (x["published_at"], x["id"]))
        return out

    return await st.call(run)


@router.post("/graph-update-events")
async def post_graph_update(request: Request, event: GraphUpdateEvent, by: str = "human") -> dict:
    st = S(request)
    if has_world_ops(event):
        raise HTTPException(422, "a drawn event cannot contain observe_value or change_value ops; "
                                 "type the news as a market event with an update instead")

    def run() -> dict:
        ctl = st.controller
        p = ctl.submit_graph_update(event, by)
        return proposal_view(p, ctl.engine.wm, ctl.engine.ltm)

    return await st.call(run)


@router.get("/proposals")
async def get_proposals(request: Request, status: str | None = Query(None)) -> list:
    st = S(request)

    def run() -> list:
        ctl = st.controller
        eng = ctl.engine
        ps = [p for p in ctl.proposals.values() if status is None or str(p.status) == status]
        return [proposal_view(p, eng.wm, eng.ltm) for p in ps]

    return await st.call(run)


def _proposal_after(st: AppState, proposal_id: str) -> dict:
    ctl = st.controller
    runner = st.runner
    if runner is not None:
        runner.status()          # leaves awaiting_review once the queue is empty
        runner._broadcast()
    return proposal_view(ctl.proposals[proposal_id], ctl.engine.wm, ctl.engine.ltm)


def _resume_if_awaited(st: AppState, proposal_id: str) -> str | None:
    """If the active update run was waiting on this proposal and it is now decided, resume the run
    (the caller drives its days in the background). Returns the run id to drive."""
    ctl = st.controller
    run = ctl.updates.get(ctl.active_update) if ctl.active_update else None
    if run is None or run.state != UpdateState.AWAITING_REVIEW or run.waiting_on != proposal_id:
        return None
    if str(ctl.proposals[proposal_id].status) == "pending":
        return None
    ctl.cycle.resume(run, run_to_end=False)
    return run.id


async def _decided(st: AppState, proposal_id: str) -> dict:
    run_id = await st.call(_resume_if_awaited, st, proposal_id)
    if run_id is not None:
        st.start_drive(run_id)
    return await st.call(_proposal_after, st, proposal_id)


@router.post("/proposals/{proposal_id}/approve")
async def approve(request: Request, proposal_id: str, body: ReviewBody | None = None) -> dict:
    st = S(request)
    b = body or ReviewBody()

    await st.call(lambda: st.controller.approve(proposal_id, by=b.by, note=b.note, keep=b.keep,
                                                confidence=b.confidence, op_confidence=b.op_confidence,
                                                ripple=b.ripple))
    return await _decided(st, proposal_id)


def _op_confidence(raw: str | None) -> dict[int, float | None] | None:
    """"2:0.6,5:0.3" -> {2: 0.6, 5: 0.3}; "3:" clears op 3's own confidence."""
    if not raw:
        return None
    out: dict[int, float | None] = {}
    for part in raw.split(","):
        if ":" in part:
            i, v = part.split(":", 1)
            out[int(i)] = float(v) if v.strip() else None
    return out


def _ripple(raw: str | None) -> dict[str, float | None] | None:
    """"delta.margin:0.5,fed.rate:0" -> {...}; "delta.margin:" lets that ripple arrive as expected again."""
    if not raw:
        return None
    out: dict[str, float | None] = {}
    for part in raw.split(","):
        if ":" in part:
            sid, v = part.rsplit(":", 1)
            out[sid.strip()] = float(v) if v.strip() else None
    return out


@router.get("/proposals/{proposal_id}/stage")
async def stage_proposal(request: Request, proposal_id: str, keep: str | None = Query(None),
                         graph: bool = True, conf: float | None = Query(None, ge=0, le=1),
                         opconf: str | None = Query(None), ripple: str | None = Query(None)) -> dict:
    """The proposal's learning, run on a copy of the state with only the `keep` operations (comma-separated
    indices; all when absent), at the reviewer's confidence (`conf`, the article's; `opconf`, "i:c,..." per
    operation; `ripple`, "subentity:p,..." the probability each value's ripple arrives): every change it would
    commit, by memory and by order, and the staged graph."""
    from axelrod_wm.control.stage import stage

    st = S(request)
    kept = None if keep is None else [int(x) for x in keep.split(",") if x.strip()]
    oc = _op_confidence(opconf)
    return await st.call(lambda: stage(st.controller, proposal_id, kept, with_graph=graph, confidence=conf,
                                       op_confidence=oc, ripple=_ripple(ripple)).model_dump(mode="json"))


@router.post("/proposals/{proposal_id}/reject")
async def reject(request: Request, proposal_id: str, body: ReviewBody) -> dict:
    st = S(request)
    if not body.note:
        raise HTTPException(422, "a rejection needs a note")

    await st.call(lambda: st.controller.reject(proposal_id, by=body.by, note=body.note))
    return await _decided(st, proposal_id)


@router.post("/proposals/{proposal_id}/edit")
async def edit(request: Request, proposal_id: str, body: EditBody) -> dict:
    st = S(request)

    def run() -> dict:
        st.controller.edit(proposal_id, body.event, by=body.by)
        return _proposal_after(st, proposal_id)

    return await st.call(run)


@router.post("/proposals/{proposal_id}/defer")
async def defer(request: Request, proposal_id: str, body: ReviewBody | None = None) -> dict:
    st = S(request)
    b = body or ReviewBody()

    await st.call(lambda: st.controller.defer(proposal_id, by=b.by))
    return await _decided(st, proposal_id)


# -- theses, forecasts, explanations -------------------------------------------------------------
@router.get("/scenario-theses")
async def scenario_theses(request: Request) -> list[dict]:
    """The scenario's stored theses (addition), so the Ask tab can offer the ready-made ones the script does not
    pose (a design partner's questions)."""
    st = S(request)
    runner = st.runner
    specs = getattr(runner, "theses_spec", None) or {}
    scripted = set()
    for step in getattr(getattr(runner, "script", None), "steps", []) or []:
        scripted |= set(step.theses()) if hasattr(step, "theses") else set()
    return [{"id": tid, "question": spec.get("question", tid), "horizon_days": spec.get("horizon_days"),
             "scripted": tid in scripted} for tid, spec in specs.items()]


@router.post("/theses/{thesis_id}/pose")
async def pose_stored_thesis(request: Request, thesis_id: str) -> dict:
    st = S(request)

    def run() -> dict:
        from axelrod_wm.sim.scenario import thesis_from_spec

        ctl = st.controller
        specs = getattr(st.runner, "theses_spec", None) or {}
        if thesis_id not in specs:
            raise KeyError(thesis_id)
        fc = ctl.pose_thesis(thesis_from_spec(specs[thesis_id], ctl.now))
        return forecast_view(fc, ctl.explanation(fc.explanation_id), ctl.engine.wm, ctl.watchlist())

    return await st.call(run)


@router.post("/theses")
async def post_thesis(request: Request, body: dict = Body(...)) -> dict:
    st = S(request)

    def run() -> dict:
        ctl = st.controller
        if set(body) <= {"question", "horizon_days", "targets", "target_groups"} and "question" in body:
            thesis = ctl.thesis_from_question(body["question"], horizon_days=int(body.get("horizon_days", 182)),
                                              targets=body.get("targets"), target_groups=body.get("target_groups"))
        else:
            data = dict(body)
            data.setdefault("posed_at", ctl.now.isoformat())
            data.setdefault("posed_by", "human")
            ev = dict(data.get("event", {}))
            ev.setdefault("id", f"GUE-{data.get('id', 'T')}")
            ev.setdefault("recorded_at", ctl.now.isoformat())
            ev.setdefault("produced_by", "human")
            ev.setdefault("kind", "hypothetical")
            data["event"] = ev
            thesis = Thesis.model_validate(data)
        fc = ctl.pose_thesis(thesis)
        return forecast_view(fc, ctl.explanation(fc.explanation_id), ctl.engine.wm, ctl.watchlist())

    return await st.call(run)


@router.get("/forecasts")
async def get_forecasts(request: Request) -> list:
    st = S(request)

    def run() -> list:
        ctl = st.controller
        out = []
        for fc in ctl.forecasts.values():
            th = ctl.theses.get(fc.thesis_id)
            out.append({"id": fc.id, "thesis_id": fc.thesis_id, "question": th.question if th else fc.thesis_id,
                        "version": fc.based_on_version, "created": fc.created_at.isoformat(),
                        "baseline": fc.is_baseline})
        return out

    return await st.call(run)


@router.get("/forecasts/{forecast_id}/brief")
async def get_forecast_brief(request: Request, forecast_id: str) -> dict:
    """A written brief of a forecast (addition): bottom line, timeline, who is affected, why, the news
    that shaped it and the news since, how it is tracking, and what to watch."""
    from axelrod_wm.api.brief import brief_view

    st = S(request)
    return await st.call(lambda: brief_view(st.controller, forecast_id))


@router.get("/forecasts/{forecast_id}")
async def get_forecast(request: Request, forecast_id: str) -> dict:
    st = S(request)

    def run() -> dict:
        ctl = st.controller
        fc = ctl.forecast(forecast_id)
        if fc is None:
            raise KeyError(forecast_id)
        return forecast_view(fc, ctl.explanation(fc.explanation_id), ctl.engine.wm, ctl.watchlist())

    return await st.call(run)


@router.get("/explanations/{explanation_id}")
async def get_explanation(request: Request, explanation_id: str) -> dict:
    st = S(request)

    def run() -> dict:
        ex = st.controller.explanation(explanation_id)
        if ex is None:
            raise KeyError(explanation_id)
        return ex.model_dump(mode="json")

    return await st.call(run)


# -- update runs (§7.8, §12.1) ---------------------------------------------------------------
@router.post("/updates")
async def post_update(request: Request, body: UpdateBody | None = None) -> dict:
    """Request an update. It continues in the background, one day per lock acquisition, and streams
    trace events; a run that reaches a news item needing review pauses there."""
    st = S(request)
    b = body or UpdateBody()

    def start() -> str:
        ctl = st.controller
        wm = ctl.engine.wm
        # DECISION: `until` defaults to the scenario's current date, or the next day to process if that
        # day is already done, so the Update button always moves forward.
        nxt = wm.deviations.date_of(wm.last_processed_day + 1)
        until = b.until or max(ctl.now.date(), nxt)
        req = UpdateRequest(requested_by=b.requested_by, until=until, requested_at=b.requested_at or end_of(until),
                            user_market_events=list(b.user_market_events),
                            user_graph_update_events=list(b.user_graph_update_events), sources=b.sources)
        run = ctl.request_update(req, run_to_end=False)
        return run.id

    run_id = await st.call(start)
    st.start_drive(run_id)
    return await st.call(lambda: update_run_view(st.controller.get_update(run_id), st.controller))


@router.get("/updates")
async def get_updates(request: Request) -> list:
    st = S(request)

    def run() -> list:
        ctl = st.controller
        runs = sorted(ctl.updates.values(), key=lambda r: r.started_at, reverse=True)
        return [update_run_view(r, ctl) for r in sorted(runs, key=lambda r: int(r.id.split("-")[-1]), reverse=True)]

    return await st.call(run)


@router.get("/updates/{update_id}")
async def get_update(request: Request, update_id: str) -> dict:
    st = S(request)
    return await st.call(lambda: update_run_view(st.controller.get_update(update_id), st.controller))


@router.post("/updates/{update_id}/continue")
async def continue_update(request: Request, update_id: str) -> dict:
    """Continue a paused run (deferring its awaited proposal if still undecided) or a stalled one."""
    st = S(request)

    def run() -> str:
        ctl = st.controller
        r = ctl.get_update(update_id)
        if r.state == UpdateState.AWAITING_REVIEW:
            ctl.cycle.resume(r, run_to_end=False)
        return str(r.state)

    state = await st.call(run)
    if state == "running":
        st.start_drive(update_id)
    return await st.call(lambda: update_run_view(st.controller.get_update(update_id), st.controller))


@router.post("/updates/{update_id}/cancel")
async def cancel_update(request: Request, update_id: str) -> dict:
    st = S(request)
    task = st.update_task
    if task is not None and not task.done():
        # the background run finishes its current day and stops
        await st.call(lambda: setattr(st.controller.get_update(update_id), "cancel_requested", True))
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=600)
        except (TimeoutError, asyncio.CancelledError):
            pass
    await st.call(lambda: st.controller.cancel_update(update_id))
    runner = st.runner
    if runner is not None and runner.pending_update() == update_id:
        await st.call(runner.step, False)
    return await st.call(lambda: update_run_view(st.controller.get_update(update_id), st.controller))


# -- evaluation, decisions ---------------------------------------------------------------------


@router.post("/evaluate")
async def evaluate(request: Request, body: EvaluationRequest) -> dict:
    st = S(request)
    return await st.call(lambda: st.controller.evaluate(body).model_dump(mode="json"))


@router.get("/decisions")
async def get_decisions(request: Request) -> list:
    st = S(request)
    return await st.call(lambda: [d.model_dump(mode="json") for d in st.controller.decisions.values()])


@router.post("/decisions")
async def post_decision(request: Request, body: dict = Body(...)) -> dict:
    st = S(request)

    def run() -> dict:
        ctl = st.controller
        data = dict(body)
        data.pop("id", None)
        data.setdefault("created_at", ctl.now.isoformat())
        return ctl.record_decision(data).model_dump(mode="json")

    return await st.call(run)


@router.get("/decisions/{decision_id}/trace")
async def decision_trace(request: Request, decision_id: str) -> dict:
    st = S(request)

    def run() -> dict:
        tr = st.controller.trace_decision(decision_id)
        return {"decision": tr.decision.model_dump(mode="json"),
                "forecasts": [f.model_dump(mode="json") for f in tr.forecasts],
                "explanations": [x.model_dump(mode="json") for x in tr.explanations],
                "state_hash_at_version": tr.state_hash_at_version, "hash_verified": tr.hash_verified,
                "changes_since": _json(tr.changes_since), "view_at_version": _json(tr.view_at_version)}

    return await st.call(run)


@router.post("/decisions/{decision_id}/resolve")
async def resolve_decision(request: Request, decision_id: str) -> dict:
    st = S(request)
    return await st.call(lambda: st.controller.resolve_decision(decision_id).model_dump(mode="json"))


# -- scenarios and layouts -----------------------------------------------------------------------
@router.get("/scenarios")
async def get_scenarios() -> list:
    return list_scenarios()


@router.get("/layouts/figure1")
async def get_layout(request: Request) -> dict:
    st = S(request)
    runner = st.ensure_loaded()
    path = runner.script.initialization.layout
    p = resolve_path(path) if path else runner.scenario_dir / "figure1_layout.yaml"
    if not p.exists():
        raise HTTPException(404, "this scenario has no layout")
    return json.loads(json.dumps(yaml.safe_load(p.read_text()) or {}, default=str))


# -- simulation ------------------------------------------------------------------------------
@router.post("/sim/load")
async def sim_load(request: Request, body: LoadBody | None = None) -> dict:
    st = S(request)
    b = body or LoadBody()
    await _stop_play(st)
    status = await st.call(st.load, b.scenario, b.interactive)
    return status.model_dump(mode="json")


@router.post("/sim/step")
async def sim_step(request: Request) -> dict:
    st = S(request)
    if st.play_task is not None and not st.play_task.done():
        raise HTTPException(409, "the scenario is playing; pause it first")
    runner = st.ensure_loaded()
    rep = await st.call(runner.step, False)
    run_id = runner.pending_update()
    if run_id is not None:
        state = await st.drive(run_id)
        if state not in ("running", "awaiting_review") and runner.reports:
            rep = runner.reports[-1]
    return rep.model_dump(mode="json")


async def _play_loop(st: AppState, until_step: int | None) -> None:
    runner = st.runner
    total = len(runner.script.steps)
    last = total if until_step is None else min(int(until_step), total)
    runner.playing = True
    runner.error = None
    try:
        while runner.step_index < last and not runner._pause.is_set():
            if runner.pending_update() is not None:
                run = runner.controller.get_update(runner.pending_update())
                if run.state == UpdateState.AWAITING_REVIEW:
                    break
            elif runner.state == "awaiting_review" and runner.controller.pending_proposals():
                break
            if runner.step_index + 1 >= last:
                runner.playing = False         # the last step of this play ends in idle
            await st.call(runner.step, False)
            run_id = runner.pending_update()
            if run_id is not None:
                state = await st.drive(run_id)   # one day per lock acquisition; finishes the step when done
                if state == "awaiting_review":
                    break
            if runner.state in ("awaiting_review", "done") or runner._pause.is_set():
                break
            await asyncio.sleep(st.play_delay)
    except Exception as exc:                    # surfaced in the status and the trace, not swallowed
        runner.error = f"{type(exc).__name__}: {exc}"
        st.tracer.emit(Phase.SCENARIO, "scenario.error", refs=[], error=runner.error, step_index=runner.step_index)
    finally:
        runner.playing = False
        if runner.state == "running":
            runner.state = "idle"
        runner._broadcast()


async def _stop_play(st: AppState) -> None:
    task = st.play_task
    if task is not None and not task.done():
        if st.runner is not None:
            st.runner._pause.set()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=600)
        except (TimeoutError, asyncio.CancelledError):
            task.cancel()
    st.play_task = None


@router.post("/sim/play")
async def sim_play(request: Request, body: PlayBody | None = None) -> dict:
    st = S(request)
    runner = st.ensure_loaded()
    st.play_requested = True
    if st.play_task is None or st.play_task.done():
        runner._pause.clear()
        if runner.state != "awaiting_review" or not runner.controller.pending_proposals():
            runner.playing = True
            runner.state = "running"
            runner._broadcast()
        st.play_task = asyncio.create_task(_play_loop(st, body.until_step if body else None))
        await asyncio.sleep(0)
    return runner.status().model_dump(mode="json")


@router.post("/sim/pause")
async def sim_pause(request: Request) -> dict:
    st = S(request)
    runner = st.ensure_loaded()
    st.play_requested = False
    runner._pause.set()
    task = st.play_task
    if task is not None and not task.done():
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=600)
        except (TimeoutError, asyncio.CancelledError):
            pass
    st.play_task = None
    return (await st.call(runner.pause)).model_dump(mode="json")


@router.post("/sim/reset")
async def sim_reset(request: Request) -> dict:
    st = S(request)
    await _stop_play(st)
    runner = st.ensure_loaded()
    return (await st.call(runner.reset)).model_dump(mode="json")


@router.get("/sim/script")
async def sim_script(request: Request) -> list:
    """The loaded scenario's steps, for the Admin window's Story list (addition)."""
    st = S(request)
    runner = st.ensure_loaded()
    out = []
    for i, step in enumerate(runner.script.steps):
        # a step that runs an update and then asks questions (step 13) counts as a question
        kind = ("question" if step.theses() else "update" if step.update is not None else "hypothesis" if step.pose_hypothesis
                else "evaluation" if step.evaluate else "decision" if step.decision or step.resolve_decision else "caption")
        out.append({"index": i, "at": step.at.isoformat(), "kind": kind, "caption": step.caption or "",
                    "theses": step.theses()})
    return out


@router.get("/sim/status")
async def sim_status(request: Request) -> dict:
    st = S(request)
    runner = st.ensure_loaded()
    return (await st.call(runner.status)).model_dump(mode="json")


# -- trace ---------------------------------------------------------------------------------------
@router.get("/trace")
async def get_trace(request: Request, since_seq: int = 0, limit: int | None = None,
                    scope: str | None = Query(None)) -> list:
    """Trace events after `since_seq`; with `scope`, only one market event's, thesis's, or day's
    events (the demo's walkthrough reads them as the steps the model took)."""
    st = S(request)
    evs = st.tracer.since(since_seq)
    if scope is not None:
        evs = [e for e in evs if e.scope == scope]
    if limit is not None:
        evs = evs[: max(0, int(limit))]
    return [e.model_dump(mode="json") for e in evs]


# -- the flowchart, contracts, history, structure edits, and the demos' examples -------------------
class GroupBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    members: list[str]
    interactions: list[str] = []
    id: str | None = None
    description: str = ""
    by: str = "human"


class DissolveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern_id: str
    reason: str
    by: str = "human"


class RetireBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str | None = None
    interaction_id: str | None = None
    reason: str
    by: str = "human"


@router.get("/flows")
async def get_flows() -> list[dict]:
    """The flowchart as data: its stages (input and output), steps, decisions, commits, and edges."""
    from axelrod_wm.flows import FLOWS

    return [f.model_dump(mode="json") for f in FLOWS.values()]


@router.get("/flows/{flow_id}/svg")
async def get_flow_svg(flow_id: str, bare: bool = False) -> Any:
    from fastapi.responses import Response

    from axelrod_wm.flows import FLOWS
    from axelrod_wm.flows.render import render_svg

    if flow_id not in FLOWS:
        raise HTTPException(404, f"unknown flow {flow_id!r}")
    return Response(content=render_svg(FLOWS[flow_id], bare=bare), media_type="image/svg+xml")


@router.get("/contracts")
async def get_contracts() -> list[dict]:
    """Every pluggable component's inputs, outputs, reads, writes, and when it runs."""
    from axelrod_wm.engine.contracts import CONTRACTS

    return [c.model_dump(mode="json") for c in CONTRACTS.values()]


@router.get("/repo/log")
async def repo_log(request: Request, limit: int = Query(50, ge=1, le=500), before: int | None = None,
                   process: list[str] | None = Query(None), memory: str | None = None) -> list[dict]:
    """The commit log, newest first: each version's process, memory, message, and who vetted it."""
    from axelrod_wm.repo.history import log

    st = S(request)
    return await st.call(lambda: [c.model_dump(mode="json") for c in log(
        st.controller.engine, limit=limit, before_version=before, processes=set(process or []) or None,
        memory=memory)])


@router.get("/repo/commits/{version}")
async def repo_show(request: Request, version: int) -> dict:
    from axelrod_wm.repo.history import show

    st = S(request)

    def run() -> dict:
        out = show(st.controller.engine, version)
        if out is None:
            raise HTTPException(404, f"no commit produced version {version}")
        return out

    return await st.call(run)


@router.get("/repo/diff")
async def repo_diff(request: Request, from_version: int = Query(..., alias="from"),
                    to_version: int | None = Query(None, alias="to")) -> dict:
    from axelrod_wm.repo.history import diff

    st = S(request)
    return await st.call(diff, st.controller.engine, from_version, to_version)


@router.get("/repo/processes")
async def repo_processes() -> dict:
    from axelrod_wm.repo.mutator import PROCESSES

    return PROCESSES


@router.post("/structure/group")
async def structure_group(request: Request, body: GroupBody) -> dict:
    """Collapse: propose a superentity made of these entities (it waits for review)."""
    from axelrod_wm.control.controller import ControllerError

    st = S(request)

    def run() -> dict:
        ctl = st.controller
        try:
            p = ctl.propose_group(body.name, body.members, interactions=body.interactions or None,
                                  pattern_id=body.id, description=body.description, by=body.by)
        except ControllerError as exc:
            raise HTTPException(422, str(exc)) from exc
        return _proposal_after(st, p.id)

    return await st.call(run)


@router.post("/structure/dissolve")
async def structure_dissolve(request: Request, body: DissolveBody) -> dict:
    """Expand: propose that a superentity break back into its constituents."""
    from axelrod_wm.control.controller import ControllerError

    st = S(request)

    def run() -> dict:
        try:
            p = st.controller.propose_dissolve(body.pattern_id, body.reason, by=body.by)
        except ControllerError as exc:
            raise HTTPException(422, str(exc)) from exc
        return _proposal_after(st, p.id)

    return await st.call(run)


@router.post("/structure/retire")
async def structure_retire(request: Request, body: RetireBody) -> dict:
    """Delete: propose retiring an entity (with its values and interactions) or one interaction."""
    from axelrod_wm.control.controller import ControllerError

    st = S(request)

    def run() -> dict:
        try:
            p = st.controller.propose_retire(entity_id=body.entity_id, interaction_id=body.interaction_id,
                                             reason=body.reason, by=body.by)
        except ControllerError as exc:
            raise HTTPException(422, str(exc)) from exc
        return _proposal_after(st, p.id)

    return await st.call(run)


# -- the demos' examples: a chain of features, with rewind, and a library of further events ---------------
def _session(st: AppState) -> Any:
    runner = st.ensure_loaded()
    if not hasattr(runner, "run_example"):
        raise HTTPException(404, "the loaded scenario has no examples; load small_demo or prod_demo")
    return runner


@router.get("/examples")
async def get_examples(request: Request) -> list[dict]:
    """The examples, in chain order: what each isolates, its articles, whether it is done, and its "more like this"
    events (an empty list when the loaded scenario has none)."""
    st = S(request)

    def run() -> list[dict]:
        runner = st.ensure_loaded()
        return runner.examples() if hasattr(runner, "examples") else []

    return await st.call(run)


class ManualBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manual: dict | None = None          # the "Add from your own knowledge" form (see sim/examples/catalog.manual_ops)
    by: str = "backend user"


@router.post("/examples/{example_id}")
async def run_example(request: Request, example_id: str, body: ManualBody | None = None) -> dict:
    """Run one example: play (or rewind to) the examples before it, then stage it and stop at the review (a thesis
    returns its question for the Ask panel instead). A manual example takes the person's form in the body."""
    st = S(request)

    def run() -> dict:
        runner = _session(st)
        out = runner.run_example(example_id, manual=(body.manual if body else None))
        if out["proposal_id"]:
            out["proposal"] = _proposal_after(st, out["proposal_id"])
        runner._broadcast()
        return out

    return await st.call(run)


@router.post("/examples/{example_id}/prepare")
async def prepare_example(request: Request, example_id: str) -> dict:
    """Bring the canvas to just before an example (playing or rewinding the ones before it) without running it: a
    manual example's form opens over what the earlier examples built."""
    st = S(request)

    def run() -> dict:
        runner = _session(st)
        return runner.prepare_example(example_id)

    return await st.call(run)


@router.post("/library/{event_id}")
async def run_library_event(request: Request, event_id: str) -> dict:
    """Add one more event like an example's, on the current state; it stops at the review."""
    st = S(request)

    def run() -> dict:
        runner = _session(st)
        out = runner.run_library(event_id)
        if out["proposal_id"]:
            out["proposal"] = _proposal_after(st, out["proposal_id"])
        runner._broadcast()
        return out

    return await st.call(run)


# -- a backend user's own knowledge (Oct 9) ------------------------------------------------------------
@router.post("/manual")
async def add_manual(request: Request, body: ManualBody) -> dict:
    """Stage what a backend user adds from their own knowledge (an entity, its values, interactions) for review, like
    any article, with their confidence on it. No article is needed."""
    from axelrod_wm.sim.examples.catalog import manual_event

    st = S(request)
    if not body.manual:
        raise HTTPException(422, "nothing to add")

    def run() -> dict:
        ctl = st.controller
        n = sum(1 for p in ctl.proposals.values() if p.event.event_type == "manual_addition") + 1
        try:
            event = manual_event(body.manual, ctl.now, f"GUE-MAN-U{n:03d}")
        except (KeyError, ValueError) as exc:
            raise HTTPException(422, f"the form is incomplete: {exc}") from exc
        p = ctl.submit_graph_update(event, by=body.by)
        return proposal_view(p, ctl.engine.wm, ctl.engine.ltm)

    return await st.call(run)


@router.get("/vocabulary")
async def get_vocabulary(request: Request) -> dict:
    """What the form offers: value kinds (with their distribution family), entity kinds, and category tags."""
    from axelrod_wm.model.entity import EntityKind

    st = S(request)

    def run() -> dict:
        vocab = st.controller.engine.vocab
        kinds = [{"id": k, "family": v.family, "parent": v.parent} for k, v in sorted(vocab.kinds.items())]
        return {"attribute_kinds": kinds, "entity_kinds": [str(k) for k in EntityKind],
                "category_tags": ["SD", "MF", "SC", "DI", "DF", "EN", "EX", "SH"]}

    return await st.call(run)
