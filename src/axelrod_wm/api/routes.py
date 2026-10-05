"""HTTP endpoints (§12.1). Handlers run engine calls in a worker thread under the app lock (§12.4)."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from typing import Any

import yaml
from fastapi import APIRouter, Body, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from axelrod_wm.api.app import AppState
from axelrod_wm.api.views import (
    entity_view,
    forecast_view,
    hypothesis_view,
    interaction_view,
    memory_summary,
    pattern_view,
    proposal_view,
    taxonomy_view,
)
from axelrod_wm.core.hypothesis import Hypothesis
from axelrod_wm.engine.initialize import resolve_path
from axelrod_wm.evaluation.backtest import EvaluationRequest
from axelrod_wm.events.graph_update import GraphUpdateEvent
from axelrod_wm.events.market import MarketEvent
from axelrod_wm.events.thesis import Thesis
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


class ConsolidateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: date | None = None


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
        name, params = cfg.translator(kind)
        translators[kind] = {"name": name, "params": params}
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
    return await st.call(taxonomy_view, kind, st.controller.engine.ltm)


@router.get("/memory")
async def get_memory(request: Request) -> dict:
    st = S(request)
    eng = st.controller.engine
    return await st.call(memory_summary, eng.wm, eng.ltm)


@router.get("/frontier")
async def get_frontier(request: Request) -> list:
    st = S(request)

    def run() -> list:
        entries = st.controller.engine.ltm.frontier.entries.values()
        return [e.model_dump(mode="json") for e in sorted(entries, key=lambda e: (-e.support, e.id))]

    return await st.call(run)


@router.get("/frontier/{entry_id}/series")
async def get_frontier_series(request: Request, entry_id: str) -> dict:
    st = S(request)

    def run() -> dict:
        co = st.controller.engine.ltm.frontier.entries[entry_id]
        return {"pairs": [[x, y] for x, y in co.corr.pairs], "lag_steps": co.lag_steps,
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


@router.post("/hypotheses/{hypothesis_id}/pose")
async def pose_hypothesis(request: Request, hypothesis_id: str, body: PoseBody | None = None) -> dict:
    st = S(request)

    def run() -> dict:
        ctl = st.controller
        fc = ctl.pose_hypothesis(hypothesis_id, body.base_thesis_id if body else None)
        return forecast_view(fc, ctl.explanation(fc.explanation_id), ctl.engine.wm)

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


@router.post("/market-events")
async def post_market_event(request: Request, event: MarketEvent) -> list:
    st = S(request)

    def run() -> list:
        ctl = st.controller
        eng = ctl.engine
        return [proposal_view(p, eng.wm, eng.ltm) for p in ctl.ingest(event)]

    return await st.call(run)


@router.post("/graph-update-events")
async def post_graph_update(request: Request, event: GraphUpdateEvent, by: str = "human") -> dict:
    st = S(request)

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


@router.post("/proposals/{proposal_id}/approve")
async def approve(request: Request, proposal_id: str, body: ReviewBody | None = None) -> dict:
    st = S(request)
    b = body or ReviewBody()

    def run() -> dict:
        st.controller.approve(proposal_id, by=b.by, note=b.note)
        return _proposal_after(st, proposal_id)

    return await st.call(run)


@router.post("/proposals/{proposal_id}/reject")
async def reject(request: Request, proposal_id: str, body: ReviewBody) -> dict:
    st = S(request)
    if not body.note:
        raise HTTPException(422, "a rejection needs a note")

    def run() -> dict:
        st.controller.reject(proposal_id, by=body.by, note=body.note)
        return _proposal_after(st, proposal_id)

    return await st.call(run)


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

    def run() -> dict:
        st.controller.defer(proposal_id, by=b.by)
        return _proposal_after(st, proposal_id)

    return await st.call(run)


# -- theses, forecasts, explanations -------------------------------------------------------------
@router.post("/theses")
async def post_thesis(request: Request, body: dict = Body(...)) -> dict:
    st = S(request)

    def run() -> dict:
        ctl = st.controller
        if set(body) <= {"question", "horizon_days", "targets"} and "question" in body:
            thesis = ctl.thesis_from_question(body["question"], horizon_days=int(body.get("horizon_days", 182)),
                                              targets=body.get("targets"))
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
        return forecast_view(fc, ctl.explanation(fc.explanation_id), ctl.engine.wm)

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


@router.get("/forecasts/{forecast_id}")
async def get_forecast(request: Request, forecast_id: str) -> dict:
    st = S(request)

    def run() -> dict:
        ctl = st.controller
        fc = ctl.forecast(forecast_id)
        if fc is None:
            raise KeyError(forecast_id)
        return forecast_view(fc, ctl.explanation(fc.explanation_id), ctl.engine.wm)

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


# -- consolidation, evaluation, decisions --------------------------------------------------------
@router.post("/consolidate")
async def consolidate(request: Request, body: ConsolidateBody | None = None) -> dict:
    st = S(request)

    def run() -> dict:
        ctl = st.controller
        day = body.day if body is not None and body.day is not None else ctl.now.date()
        return ctl.consolidate(day).model_dump(mode="json")

    return await st.call(run)


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
    rep = await st.call(runner.step)
    return rep.model_dump(mode="json")


async def _play_loop(st: AppState, until_step: int | None) -> None:
    runner = st.runner
    total = len(runner.script.steps)
    last = total if until_step is None else min(int(until_step), total)
    runner.playing = True
    runner.error = None
    try:
        while runner.step_index < last and not runner._pause.is_set():
            if runner.state == "awaiting_review" and runner.controller.pending_proposals():
                break
            if runner.step_index + 1 >= last:
                runner.playing = False         # the last step of this play ends in idle
            await st.call(runner.step)
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


@router.get("/sim/status")
async def sim_status(request: Request) -> dict:
    st = S(request)
    runner = st.ensure_loaded()
    return (await st.call(runner.status)).model_dump(mode="json")


# -- trace ---------------------------------------------------------------------------------------
@router.get("/trace")
async def get_trace(request: Request, since_seq: int = 0, limit: int | None = None) -> list:
    st = S(request)
    evs = st.tracer.since(since_seq)
    if limit is not None:
        evs = evs[: max(0, int(limit))]
    return [e.model_dump(mode="json") for e in evs]
