"""v1 work on the model (world_model/docs/api/openapi.yaml): events and what they did, changes and their review (human only),
theses and simulations, and jobs. Documents, bundles, and search are routes_ingest.py."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import Response

from axelrod_wm.api.tokens import APPROVE, CHANGES, READ, SIMULATIONS
from axelrod_wm.api.v1 import project as pj
from axelrod_wm.api.v1 import schemas as s
from axelrod_wm.api.v1.context import (
    AsOf,
    Cursor,
    Limit,
    Model,
    Version,
    audit,
    base,
    decode_cursor,
    etag,
    fingerprint,
    idempotent,
    job_of,
    lake,
    many,
    model,
    one,
    page,
    principal,
    require,
    run_job,
)
from axelrod_wm.api.v1.context import version_ref as vref
from axelrod_wm.api.v1.problems import ApiError, V1Route
from axelrod_wm.api.v1.routes_ingest import bundle_of
from axelrod_wm.api.v1.routes_model import read_at
from axelrod_wm.control.controller import ControllerError

router = APIRouter(prefix="/v1", route_class=V1Route, tags=["v1"])
W = "/world-models/{world_model_id}"


# -- events ----------------------------------------------------------------------------------------------------------------
def changes_of_event(ctl: Any, event_id: str) -> list[Any]:
    return [p for _k, p in sorted(ctl.proposals.items()) if p.market_event_id == event_id]


def event_of(ctl: Any, event_id: str) -> Any:
    me = ctl.market_events.get(event_id)
    if me is None:
        raise ApiError("event_not_found", f"no event {event_id}")
    return me


@router.get(W + "/events", summary="Market events, by publication time")
async def list_events(request: Request, world_model_id: str, type: Literal["news", "data_release", "company_filing",
                                                                            "research"] | None = None,
                      published_from: datetime | None = None, published_to: datetime | None = None,
                      entity: str | None = None, limit: Limit = 50, cursor: Cursor = None) -> Response:
    m = model(request, world_model_id, READ)
    off, _v = decode_cursor(cursor)

    def utc(t: datetime) -> datetime:
        return t if t.tzinfo else t.replace(tzinfo=UTC)

    def run() -> list[s.Event]:
        ctl = m.st.controller
        rows = sorted(ctl.market_events.values(), key=lambda e: (e.published_at, e.id))
        rows = [e for e in rows if (type is None or pj.EVENT_TYPE[str(e.kind)] == type)
                and (published_from is None or e.published_at >= utc(published_from))
                and (published_to is None or e.published_at <= utc(published_to))
                and (entity is None or entity in e.mentions)]
        return [pj.event(e, [p.id for p in changes_of_event(ctl, e.id)]) for e in rows]

    chunk, nxt = page(await m.st.call(run), off, limit, None)
    return many(request, chunk, limit, nxt)


@router.get(W + "/events/{event_id}", summary="One market event")
async def get_event(request: Request, world_model_id: str, event_id: str) -> Response:
    m = model(request, world_model_id, READ)

    def run() -> s.Event:
        ctl = m.st.controller
        return pj.event(event_of(ctl, event_id), [p.id for p in changes_of_event(ctl, event_id)])

    return one(request, await m.st.call(run))


@router.get(W + "/events/{event_id}/impact-analysis", summary="What an event did")
async def impact_analysis(request: Request, world_model_id: str, event_id: str, version: Version = None,
                          as_of: AsOf = None) -> Response:
    """The attributes the event's changes move directly (the size the model folded in, in sd, once approved; the
    operation's sign before), then one relationship on from each."""
    m = model(request, world_model_id, READ)
    wm, _ltm, ref, _o = await read_at(m, version, as_of)

    def run() -> dict:
        ctl = m.st.controller
        event_of(ctl, event_id)
        props = changes_of_event(ctl, event_id)
        status = "completed" if any(str(p.status) in ("approved", "auto_applied") for p in props) else \
            "pending_review" if any(str(p.status) == "pending" for p in props) else "not_imported"
        g = wm.graph
        direct: dict[str, tuple[int, float | None]] = {}
        for p in props:
            for op in p.event.ops:
                sid = getattr(getattr(op, "target", None), "subentity_id", None)
                if sid is None or sid not in g.subentities:
                    continue
                folded = [ts.values["z"] for ts in g.subentities[sid].history
                          if ts.source_event_id == p.event.id and "z" in ts.values]
                delta = getattr(op, "delta", None)
                if folded:
                    direct[sid] = (1 if folded[-1] >= 0 else -1, round(float(folded[-1]), 4))
                elif delta is not None:
                    direct[sid] = (1 if delta >= 0 else -1, None)
        impacts = [s.Impact(entity_id=pj.owner_of(sid), attribute_id=sid,
                            direction="positive" if d > 0 else "negative", size_sd=size, confidence=1.0, order=0,
                            causal_path_ids=[]) for sid, (d, size) in sorted(direct.items())]
        for i in sorted(g.active_interactions(), key=lambda x: x.id):
            if i.source_id not in direct or i.target_id in direct:
                continue
            d, size = direct[i.source_id]
            sign = i.polarity()
            impacts.append(s.Impact(
                entity_id=pj.owner_of(i.target_id), attribute_id=i.target_id,
                direction="positive" if d * sign > 0 else "negative",
                size_sd=round(size * float(i.forward.effect.mean()), 4) if size is not None and i.quantified else None,
                confidence=round(float(i.existence.mean()), 6), order=1, causal_path_ids=[i.id]))
        return s.ImpactAnalysis(event_id=event_id, status=status, model_version=ref["number"],
                                impacts=impacts).model_dump(mode="json")

    return one(request, await m.st.call(run), ref)


# -- changes and their review ---------------------------------------------------------------------------------------------------
def actors(request: Request, m: Model) -> tuple[dict[str, dict], dict[str, dict]]:
    """(update id -> who proposed it, change id -> who decided it), from the audit log."""
    proposed: dict[str, dict] = {}
    decided: dict[str, dict] = {}
    for r in reversed(lake(request.app).list_audit(m.org, m.id)):
        if r.route.endswith("/changes"):
            for rid in r.resource_ids:
                proposed.setdefault(rid, r.actor)
        elif r.route.endswith(("/approvals", "/rejections")):
            for rid in r.resource_ids:
                decided.setdefault(rid, r.actor)
    return proposed, decided


def change_view(request: Request, m: Model, p: Any, who: tuple[dict, dict]) -> s.Change:
    return pj.change(p, m.org, who[0].get(p.update_id) if p.update_id else None, who[1].get(p.id))


def claim_proposal(app: Any, m: Model) -> str:
    """Under the engine's lock: no update active and no other proposal starting, so two at once cannot both pass.
    "claimed" (the caller then discards `app.state.proposing`'s entry), "update" (one is running or waiting for review),
    or "busy" (another proposal is starting)."""
    ctl = m.st.main_controller() if m.st.is_view else m.st.controller       # a compartment imports into the main engine
    if ctl.active_update is not None:
        return "update"
    if m.id in app.state.proposing:
        return "busy"
    app.state.proposing.add(m.id)
    return "claimed"


def run_proposal(m: Model, rec: Any, item_ids: list[str] | None) -> dict:
    """Propose a stored bundle's items on the model (under the engine's lock): the ids imported, the late ones, the
    changes proposed, and the version before. A compartment's view narrows the bundle first (sim/imports.py)."""
    from axelrod_wm.api.routes import _importer

    ctl = m.st.controller
    runner = _importer(m.st)
    before = {p.id for p in ctl.pending_proposals()}
    preview = runner.preview(rec.bundle)
    late = [x["id"] for x in preview["items"] if x["status"] == "late" and (item_ids is None or x["id"] in item_ids)]
    version_before = ctl.engine.version
    try:
        out = runner.import_items(rec.bundle, item_ids)
    except ControllerError as err:
        if "nothing new" not in str(err):
            raise
        out = {"update_id": None, "imported": []}
    proposed = sorted(p.id for p in ctl.pending_proposals() if p.id not in before)
    return {"out": out, "late": late, "proposed": proposed, "version_before": version_before}


def record_import(app: Any, m: Model, bundle_id: str, r: dict, by: str) -> None:
    """Keep what a proposal imported as the lakehouse's import record."""
    from axelrod_ingest.lake.store import ImportRecord

    if r["out"]["imported"]:
        lake(app).put_import(ImportRecord(tenant=m.org, bundle_id=bundle_id, imported_at=datetime.now(UTC),
                                          update_id=r["out"]["update_id"], item_ids=r["out"]["imported"], by=by))


@router.post(W + "/changes", status_code=202, summary="Propose one change per bundle item")
async def create_changes(request: Request, world_model_id: str, body: s.ChangeCreate) -> Response:
    m = model(request, world_model_id, CHANGES)
    rec = bundle_of(request, m, body.bundle_id)
    sub = principal(request).sub

    async def make() -> Response:
        while (got := await m.st.call(claim_proposal, request.app, m)) != "claimed":
            if got == "update" or await m.st.call(lambda: m.st.controller.engine.components["review_policy"].pauses_run):
                raise ApiError("update_in_progress", "another update is running or waiting for review; decide its "
                                                     "changes first")
            await asyncio.sleep(0.02)           # one import at a time: this one starts when the other is done
        try:
            return await propose_job()
        finally:
            request.app.state.proposing.discard(m.id)

    async def propose_job() -> Response:
        async def work() -> dict:
            r = await m.st.call(run_proposal, m, rec, body.item_ids)
            record_import(request.app, m, body.bundle_id, r, sub)
            detail = {"bundle_id": body.bundle_id, "imported_item_ids": r["out"]["imported"],
                      "late_item_ids": r["late"], "version_before": r["version_before"]}
            if r["out"]["update_id"]:
                detail["update_id"] = r["out"]["update_id"]
            return {"resource": "changes", "ids": r["proposed"], "detail": detail}

        return await run_job(request, m, "change_proposal", work)

    return await idempotent(request, m, fingerprint(body.model_dump()), make)


@router.get(W + "/changes", summary="Proposed changes")
async def list_changes(request: Request, world_model_id: str,
                       status: Literal["pending", "approved", "rejected", "deferred", "auto_applied", "all"] = "pending",
                       limit: Limit = 50, cursor: Cursor = None) -> Response:
    m = model(request, world_model_id, READ)
    off, _v = decode_cursor(cursor)
    who = actors(request, m)

    def run() -> list[Any]:
        ps = [p for p in m.st.controller.proposals.values() if status == "all" or str(p.status) == status]
        return sorted(ps, key=lambda p: (p.created_at, p.id))

    chunk, nxt = page(await m.st.call(run), off, limit, None)
    return many(request, [change_view(request, m, p, who) for p in chunk], limit, nxt)


def change_of(m: Model, change_id: str) -> Any:
    p = m.st.controller.proposals.get(change_id)
    if p is None:
        raise ApiError("change_not_found", f"no change {change_id}")
    return p


@router.get(W + "/changes/{change_id}", summary="One change")
async def get_change(request: Request, world_model_id: str, change_id: str) -> Response:
    m = model(request, world_model_id, READ)
    p = await m.st.call(change_of, m, change_id)
    ref = await m.st.call(vref, m.st)
    return one(request, change_view(request, m, p, actors(request, m)), ref, tag=True)


@router.get(W + "/changes/{change_id}/diff", summary="What approving the change would do")
async def get_change_diff(request: Request, world_model_id: str, change_id: str) -> Response:
    m = model(request, world_model_id, READ)
    p = await m.st.call(change_of, m, change_id)
    return one(request, {"change_id": p.id, "operations": [pj.operation(op) for op in p.event.ops]})


async def decide(request: Request, world_model_id: str, change_id: str, approve: bool, note: str) -> Response:
    from axelrod_wm.api.routes import _resume_if_awaited

    # who before what: a key or an agent is told a person decides, whatever its scopes; a person needs the scope
    m = model(request, world_model_id, None)
    p = principal(request)
    if not p.human:
        raise ApiError("human_approval_required", "a change is decided by a person: not by a static key, and not "
                                                  "through an agent")
    require(request, APPROVE)
    want = request.headers.get("if-match")
    if want is None:
        raise ApiError("precondition_required", "send If-Match with the ETag of the version you reviewed")

    def run() -> None:
        ctl = m.st.controller
        prop = change_of(m, change_id)
        if want.strip() != etag(vref(m.st)):
            raise ApiError("version_moved", "the model has moved since that version: read the change again")
        if str(prop.status) != "pending":
            raise ApiError("already_decided", f"change {change_id} is {prop.status}")
        if approve:
            try:
                ctl.approve(change_id, by=p.sub, note=note or None)
            except ControllerError as err:          # a change an import left pending, on a model that has moved on
                raise ApiError("conflict", str(err)) from err
        else:
            ctl.reject(change_id, by=p.sub, note=note)

    async def make() -> Response:
        await m.st.call(run)
        run_id = await m.st.call(_resume_if_awaited, m.st, change_id)
        if run_id is not None:
            await m.st.drive(run_id)
        audit(request, m, 201, [change_id])
        prop = await m.st.call(change_of, m, change_id)
        body = s.Decision(change_id=change_id, status=str(prop.status), decided_by=p.actor(),
                          decided_at=prop.decided_at, note=prop.note, version=await m.st.call(vref, m.st))
        return one(request, body, status=201)

    return await idempotent(request, m, fingerprint(change_id, approve, note), make)


@router.post(W + "/changes/{change_id}/approvals", status_code=201, summary="Approve a change")
async def approve_change(request: Request, world_model_id: str, change_id: str,
                         body: s.ApprovalCreate | None = None) -> Response:
    return await decide(request, world_model_id, change_id, True, (body or s.ApprovalCreate()).note)


@router.post(W + "/changes/{change_id}/rejections", status_code=201, summary="Reject a change")
async def reject_change(request: Request, world_model_id: str, change_id: str, body: s.RejectionCreate) -> Response:
    if not body.reason.strip():
        raise ApiError("note_required", "a rejection needs a reason")
    return await decide(request, world_model_id, change_id, False, body.reason)


# -- theses and simulations ----------------------------------------------------------------------------------------------------
def templates_of(m: Model) -> dict:
    from axelrod_wm.sim.scenario import load_theses

    ctl = m.st.controller
    return load_theses(ctl.scenario_dir)[0] if ctl.scenario_dir is not None else {}


def theses_of(request: Request, m: Model) -> dict[str, Any]:
    """The theses posed through the API, and the ones the engine has run (their refined form)."""
    mine = request.app.state.theses.setdefault((m.org, m.id), {})
    return {**mine, **m.st.controller.theses}


def simulation_ids(m: Model, thesis_id: str) -> list[str]:
    return sorted(f.id for f in m.st.controller.forecasts.values() if f.thesis_id == thesis_id)


@router.get(W + "/thesis-templates", summary="Ready theses the world model ships with")
async def list_thesis_templates(request: Request, world_model_id: str, limit: Limit = 50,
                                cursor: Cursor = None) -> Response:
    m = model(request, world_model_id, READ)
    off, _v = decode_cursor(cursor)
    specs = await m.st.call(templates_of, m)
    rows = [s.ThesisTemplate(id=k, question=str(v.get("question", "")), horizon_days=int(v.get("horizon_days", 182)))
            for k, v in sorted(specs.items())]
    chunk, nxt = page(rows, off, limit, None)
    return many(request, chunk, limit, nxt)


@router.post(W + "/theses", status_code=201, summary="Pose a what-if")
async def create_thesis(request: Request, world_model_id: str, body: s.ThesisCreate) -> Response:
    m = model(request, world_model_id, SIMULATIONS)
    if bool(body.question) == bool(body.template_id):
        raise ApiError("invalid_request", "give exactly one of question and template_id")
    sub = principal(request).sub

    async def make() -> Response:
        def run() -> Any:
            ctl = m.st.controller
            if body.template_id:
                from axelrod_wm.sim.scenario import thesis_from_spec

                specs = templates_of(m)
                if body.template_id not in specs:
                    raise ApiError("thesis_not_found", f"no thesis template {body.template_id}")
                return thesis_from_spec(specs[body.template_id], ctl.now)
            try:
                return ctl.thesis_from_question(body.question, horizon_days=body.horizon_days, posed_by=sub)
            except ControllerError as err:
                raise ApiError("question_not_understood", str(err)) from err

        thesis = await m.st.call(run)
        request.app.state.theses.setdefault((m.org, m.id), {})[thesis.id] = thesis
        audit(request, m, 201, [thesis.id])
        return one(request, pj.thesis(thesis, simulation_ids(m, thesis.id)), status=201,
                   location=f"{base(m)}/theses/{thesis.id}")

    return await idempotent(request, m, fingerprint(body.model_dump()), make)


@router.get(W + "/theses", summary="Theses posed so far")
async def list_theses(request: Request, world_model_id: str, limit: Limit = 50, cursor: Cursor = None) -> Response:
    m = model(request, world_model_id, READ)
    off, _v = decode_cursor(cursor)
    rows = sorted(theses_of(request, m).values(), key=lambda t: (t.posed_at, t.id))
    chunk, nxt = page(rows, off, limit, None)
    return many(request, [pj.thesis(t, simulation_ids(m, t.id)) for t in chunk], limit, nxt)


def thesis_of(request: Request, m: Model, thesis_id: str) -> Any:
    t = theses_of(request, m).get(thesis_id)
    if t is None:
        raise ApiError("thesis_not_found", f"no thesis {thesis_id}")
    return t


@router.get(W + "/theses/{thesis_id}", summary="One thesis")
async def get_thesis(request: Request, world_model_id: str, thesis_id: str) -> Response:
    m = model(request, world_model_id, READ)
    return one(request, pj.thesis(thesis_of(request, m, thesis_id), simulation_ids(m, thesis_id)))


@router.post(W + "/theses/{thesis_id}/simulations", status_code=202, summary="Run a thesis on the latest version")
async def run_simulation(request: Request, world_model_id: str, thesis_id: str,
                         body: s.SimulationCreate | None = None) -> Response:
    m = model(request, world_model_id, SIMULATIONS)
    thesis = thesis_of(request, m, thesis_id)
    b = body or s.SimulationCreate()

    async def make() -> Response:
        async def work() -> dict:
            t = thesis if b.horizon_days is None else thesis.model_copy(update={"horizon_days": b.horizon_days})
            fc = await m.st.call(m.st.controller.pose_thesis, t)
            return {"resource": "simulations", "ids": [fc.id], "detail": {"thesis_id": thesis_id}}

        return await run_job(request, m, "simulation", work)

    return await idempotent(request, m, fingerprint(thesis_id, b.model_dump()), make)


def simulation_of(m: Model, simulation_id: str) -> Any:
    fc = m.st.controller.forecast(simulation_id)
    if fc is None:
        raise ApiError("simulation_not_found", f"no simulation {simulation_id}")
    return fc


@router.get(W + "/simulations", summary="Simulations run so far, oldest first")
async def list_simulations(request: Request, world_model_id: str, limit: Limit = 50, cursor: Cursor = None) -> Response:
    m = model(request, world_model_id, READ)
    off, _v = decode_cursor(cursor)

    def run() -> list[s.Simulation]:
        g = m.st.controller.engine.wm.graph
        fcs = sorted(m.st.controller.forecasts.values(), key=lambda f: (f.created_at, f.id))
        return [pj.simulation(g, f) for f in fcs]

    chunk, nxt = page(await m.st.call(run), off, limit, None)
    return many(request, chunk, limit, nxt)


@router.get(W + "/simulations/{simulation_id}", summary="One simulation")
async def get_simulation(request: Request, world_model_id: str, simulation_id: str) -> Response:
    m = model(request, world_model_id, READ)

    def run() -> tuple[s.Simulation, dict]:
        fc = simulation_of(m, simulation_id)
        return pj.simulation(m.st.controller.engine.wm.graph, fc), vref(m.st, fc.based_on_version)

    sim, ref = await m.st.call(run)
    return one(request, sim, ref, tag=True)


@router.get(W + "/simulations/{simulation_id}/transmission", summary="The shock's path, by order")
async def get_transmission(request: Request, world_model_id: str, simulation_id: str, limit: Limit = 50,
                           cursor: Cursor = None) -> Response:
    m = model(request, world_model_id, READ)
    off, _v = decode_cursor(cursor)
    rows = await m.st.call(lambda: pj.transmission(m.st.controller.engine.wm.graph, simulation_of(m, simulation_id)))
    chunk, nxt = page(rows, off, limit, None)
    return many(request, chunk, limit, nxt)


@router.get(W + "/simulations/{simulation_id}/coverage", summary="What the simulation's numbers are made of")
async def get_coverage(request: Request, world_model_id: str, simulation_id: str) -> Response:
    m = model(request, world_model_id, READ)
    fc = await m.st.call(simulation_of, m, simulation_id)
    return one(request, fc.coverage)


@router.get(W + "/simulations/{simulation_id}/brief", summary="A reader's summary of a simulation")
async def get_brief(request: Request, world_model_id: str, simulation_id: str) -> Response:
    from axelrod_wm.api.brief import brief_view

    m = model(request, world_model_id, READ)

    def run() -> dict:
        fc = simulation_of(m, simulation_id)
        return {**brief_view(m.st.controller, simulation_id), "coverage": fc.coverage}

    return one(request, await m.st.call(run))


# -- jobs --------------------------------------------------------------------------------------------------------------------------
@router.get(W + "/jobs/{job_id}", summary="One job")
async def get_job(request: Request, world_model_id: str, job_id: str) -> Response:
    m = model(request, world_model_id, READ)
    return one(request, job_of(request, m, job_id))
