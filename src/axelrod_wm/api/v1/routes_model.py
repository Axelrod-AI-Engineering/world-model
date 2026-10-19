"""v1 reads of the model (docs/api/openapi.yaml): the credential, world models, versions, entities and attributes,
construction, relationships and evidence, concepts and groups, the graph, exports, and the audit log."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import Response

from axelrod_wm.api.tokens import ADMIN, READ
from axelrod_wm.api.v1 import project as pj
from axelrod_wm.api.v1 import schemas as s
from axelrod_wm.api.v1.context import (
    Model,
    decode_cursor,
    lake,
    many,
    model,
    models_of,
    one,
    page,
    pinned,
    require,
)
from axelrod_wm.api.v1.context import version_ref as vref
from axelrod_wm.api.v1.problems import API_VERSION, ApiError, V1Route

router = APIRouter(prefix="/v1", route_class=V1Route, tags=["v1"])
W = "/world-models/{world_model_id}"

Version = Annotated[int | None, Query(ge=1)]
AsOf = Annotated[datetime | None, Query()]
Limit = Annotated[int, Query(ge=1, le=200)]
Cursor = Annotated[str | None, Query()]


async def read_at(m: Model, version: int | None, as_of: datetime | None, cursor: str | None = None):
    """(working memory, long-term memory, version ref, offset) for a pinned read; a cursor keeps its version."""
    off, cv = decode_cursor(cursor)

    def run():
        wm, ltm, v = pinned(m.st, version or cv, as_of)
        return wm, ltm, vref(m.st, v)

    wm, ltm, ref = await m.st.call(run)
    return wm, ltm, ref, off


def attribute_id(graph, entity_id: str, key: str) -> str:
    """An entity's attribute by its key (`operating_profit`) or its full id (`toyota.operating_profit`)."""
    entity_of(graph, entity_id)
    sid = key if key.startswith(f"{entity_id}.") else f"{entity_id}.{key}"
    if sid not in graph.subentities:
        raise ApiError("attribute_not_found", f"entity {entity_id} has no attribute {key}")
    return sid


def entity_of(graph, entity_id: str) -> None:
    if entity_id not in graph.entities:
        raise ApiError("entity_not_found", f"no entity {entity_id}")


def live(graph) -> list:
    return sorted(graph.active_interactions(), key=lambda x: x.id)


# -- the credential and world models ------------------------------------------------------------------------------------
@router.get("/me", summary="Who the credential is")
async def get_me(request: Request) -> Response:
    p = require(request, READ)
    return one(request, s.Me(actor=p.actor(), scopes=sorted(p.scopes),
                             world_model_ids=[m.id for m in models_of(request, p.org)]))


def world_model_view(request: Request, m: Model) -> dict:
    eng = m.st.controller.engine
    g = eng.wm.graph
    stats = lake(request.app).stats(m.org)
    return s.WorldModel(
        id=m.id, name=m.st.runner.script.title.split(":")[0], organization=m.org, latest_version=eng.version,
        clock=eng.wm.clock, counts=s.Counts(entities=len(g.entities), attributes=len(g.subentities),
                                            relationships=len(g.active_interactions()), groups=len(g.instances),
                                            documents=stats["documents"], bundles=stats["bundles"])
    ).model_dump(mode="json")


@router.get("/world-models", summary="The organization's world models")
async def list_world_models(request: Request, limit: Limit = 50, cursor: Cursor = None) -> Response:
    p = require(request, READ)
    off, _v = decode_cursor(cursor)
    items = [await m.st.call(world_model_view, request, m) for m in models_of(request, p.org)]
    chunk, nxt = page(items, off, limit, None)
    return many(request, chunk, limit, nxt)


@router.get(W, summary="One world model")
async def get_world_model(request: Request, world_model_id: str) -> Response:
    m = model(request, world_model_id, READ)
    ref = await m.st.call(vref, m.st)
    return one(request, await m.st.call(world_model_view, request, m), ref, tag=True)


@router.get(W + "/audit-events", summary="The audit log, newest first")
async def list_audit_events(request: Request, world_model_id: str, limit: Limit = 50,
                            cursor: Cursor = None) -> Response:
    m = model(request, world_model_id, ADMIN)
    off, _v = decode_cursor(cursor)
    rows = [s.AuditEvent(id=r.id, at=r.at, request_id=r.request_id, world_model_id=r.world_model_id, method=r.method,
                         route=r.route, status=r.status, actor=r.actor, scopes=r.scopes, resource_ids=r.resource_ids)
            for r in lake(request.app).list_audit(m.org, m.id)]
    chunk, nxt = page(rows, off, limit, None)
    return many(request, chunk, limit, nxt)


# -- versions ------------------------------------------------------------------------------------------------------------
def versions_of(m: Model) -> list[s.Version]:
    ctl = m.st.controller
    by_version: dict[int, list[str]] = {}
    for pid, p in sorted(ctl.proposals.items()):
        if p.version_after is not None:
            by_version.setdefault(p.version_after, []).append(pid)
    return [s.Version(number=v.version, state_hash=v.state_hash, committed_at=v.recorded_at, cause=v.cause,
                      change_ids=by_version.get(v.version, []))
            for v in sorted(ctl.engine.snapshots.storage.versions(), key=lambda v: -v.version)]


@router.get(W + "/versions", summary="Committed versions, newest first")
async def list_versions(request: Request, world_model_id: str, limit: Limit = 50, cursor: Cursor = None) -> Response:
    m = model(request, world_model_id, READ)
    off, _v = decode_cursor(cursor)
    rows = await m.st.call(versions_of, m)
    chunk, nxt = page(rows, off, limit, None)
    return many(request, chunk, limit, nxt, await m.st.call(vref, m.st))


@router.get(W + "/versions/{version_ref}", summary="One committed version (`latest` for the newest)")
async def get_version(request: Request, world_model_id: str,
                      version_ref: Annotated[str, Path(pattern=r"^(latest|[1-9][0-9]*)$")]) -> Response:
    m = model(request, world_model_id, READ)
    rows = await m.st.call(versions_of, m)
    found = rows[0] if version_ref == "latest" else next((v for v in rows if v.number == int(version_ref)), None)
    if found is None:
        raise ApiError("version_not_found", f"no version {version_ref}")
    return one(request, found, await m.st.call(vref, m.st, found.number), tag=True)


# -- entities and attributes -------------------------------------------------------------------------------------------
@router.get(W + "/entities", summary="Entities, filtered by type, concept, group or name")
async def list_entities(request: Request, world_model_id: str, type: s.EntityType | None = None,
                        concept: str | None = None, group: str | None = None,
                        q: Annotated[str, Query(max_length=200)] = "", version: Version = None, as_of: AsOf = None,
                        limit: Limit = 50, cursor: Cursor = None) -> Response:
    m = model(request, world_model_id, READ)
    wm, ltm, ref, off = await read_at(m, version, as_of, cursor)
    g = wm.graph
    p = q.strip().lower()

    def named(x, xid: str) -> bool:
        return not p or any(p in n.lower() for n in (x.name, *x.aliases, xid))

    attrs: dict[str, list[str]] = {}
    for sid, sub in sorted(g.subentities.items()):
        if p and named(sub, sid.removeprefix(f"{sub.entity_id}.")):
            attrs.setdefault(sub.entity_id, []).append(sid)
    under = set()
    if concept is not None:
        tax = ltm.object_generalizations.taxonomy
        under = {e for nid, n in tax.nodes.items() if nid == concept or concept in tax.path_from_root(nid)
                 for e in n.instance_ids}
    bound = {e for i in g.instances.values() if i.id == group for e in i.bindings.values()}

    def keep(eid: str) -> bool:
        e = g.entities[eid]
        return ((type is None or str(e.kind) == type) and (concept is None or eid in under)
                and (group is None or eid in bound) and (named(e, eid) or eid in attrs))

    def starts(eid: str) -> bool:
        names = (g.entities[eid].name, *(g.subentities[x].name for x in attrs.get(eid, [])))
        return any(n.lower().startswith(p) for n in names)

    ids = sorted((eid for eid in g.entities if keep(eid)), key=lambda eid: (0 if starts(eid) else 1, eid))
    chunk, nxt = page(ids, off, limit, ref["number"])
    rows = [pj.entity(wm, ltm, eid, None if not p or named(g.entities[eid], eid) else attrs[eid], occurred=occurred_of(m))
            for eid in chunk]
    return many(request, rows, limit, nxt, ref)


@router.get(W + "/entities/{entity_id}", summary="One entity, with its attributes (and relationships)")
async def get_entity(request: Request, world_model_id: str, entity_id: str,
                     include: Literal["attributes", "relationships", "attributes,relationships"] = "attributes",
                     version: Version = None, as_of: AsOf = None) -> Response:
    m = model(request, world_model_id, READ)
    wm, ltm, ref, _o = await read_at(m, version, as_of)
    entity_of(wm.graph, entity_id)
    rels = None
    if "relationships" in include:
        own = set(pj.own_attributes(wm, entity_id))
        rels = [pj.relationship(i, wm.graph) for i in live(wm.graph) if i.source_id in own or i.target_id in own]
    return one(request, pj.entity(wm, ltm, entity_id, relationships=rels, occurred=occurred_of(m)), ref, tag=True)


@router.get(W + "/entities/{entity_id}/attributes", summary="An entity's attributes")
async def list_attributes(request: Request, world_model_id: str, entity_id: str, version: Version = None,
                          as_of: AsOf = None, limit: Limit = 50, cursor: Cursor = None) -> Response:
    m = model(request, world_model_id, READ)
    wm, _ltm, ref, off = await read_at(m, version, as_of, cursor)
    entity_of(wm.graph, entity_id)
    chunk, nxt = page(pj.own_attributes(wm, entity_id), off, limit, ref["number"])
    return many(request, [pj.attribute(wm, x, occurred_of(m)) for x in chunk], limit, nxt, ref)


@router.get(W + "/entities/{entity_id}/attributes/{attribute_key}", summary="One attribute")
async def get_attribute(request: Request, world_model_id: str, entity_id: str, attribute_key: str,
                        version: Version = None, as_of: AsOf = None) -> Response:
    m = model(request, world_model_id, READ)
    wm, _ltm, ref, _o = await read_at(m, version, as_of)
    return one(request, pj.attribute(wm, attribute_id(wm.graph, entity_id, attribute_key), occurred_of(m)), ref, tag=True)


def _window(rows: list, start: datetime | None, end: datetime | None, at) -> list:
    def utc(t: datetime) -> datetime:
        return t if t.tzinfo else t.replace(tzinfo=UTC)

    return [r for r in rows if (start is None or at(r) >= utc(start)) and (end is None or at(r) <= utc(end))]


@router.get(W + "/entities/{entity_id}/attributes/{attribute_key}/observations",
            summary="An attribute's dated observations")
async def list_observations(request: Request, world_model_id: str, entity_id: str, attribute_key: str,
                            valid_from: datetime | None = None, valid_to: datetime | None = None,
                            version: Version = None, as_of: AsOf = None, limit: Limit = 50,
                            cursor: Cursor = None) -> Response:
    m = model(request, world_model_id, READ)
    wm, _ltm, ref, off = await read_at(m, version, as_of, cursor)
    sub = wm.graph.subentities[attribute_id(wm.graph, entity_id, attribute_key)]
    rows = _window(pj.observations(sub, occurred_of(m)), valid_from, valid_to, lambda r: r.valid_at)
    chunk, nxt = page(rows, off, limit, ref["number"])
    return many(request, chunk, limit, nxt, ref)


@router.get(W + "/entities/{entity_id}/attributes/{attribute_key}/states",
            summary="The model's state of an attribute over time")
async def list_states(request: Request, world_model_id: str, entity_id: str, attribute_key: str,
                      from_: Annotated[datetime | None, Query(alias="from")] = None,
                      to: datetime | None = None, version: Version = None, as_of: AsOf = None, limit: Limit = 50,
                      cursor: Cursor = None) -> Response:
    m = model(request, world_model_id, READ)
    wm, _ltm, ref, off = await read_at(m, version, as_of, cursor)
    sub = wm.graph.subentities[attribute_id(wm.graph, entity_id, attribute_key)]
    rows = _window(pj.states(sub), from_, to, lambda r: r.valid_at)
    chunk, nxt = page(rows, off, limit, ref["number"])
    return many(request, chunk, limit, nxt, ref)


# -- construction --------------------------------------------------------------------------------------------------------
@router.get(W + "/entities/{entity_id}/compositions", summary="An entity's business views")
async def list_compositions(request: Request, world_model_id: str, entity_id: str, version: Version = None,
                            as_of: AsOf = None, limit: Limit = 50, cursor: Cursor = None) -> Response:
    m = model(request, world_model_id, READ)
    wm, _ltm, ref, off = await read_at(m, version, as_of, cursor)
    entity_of(wm.graph, entity_id)
    rows = [pj.composition(wm.graph, c) for c in sorted(wm.graph.compositions.values(), key=lambda c: c.id)
            if c.entity_id == entity_id]
    chunk, nxt = page(rows, off, limit, ref["number"])
    return many(request, chunk, limit, nxt, ref)


@router.get(W + "/entities/{entity_id}/compositions/{composition_id}", summary="One business view")
async def get_composition(request: Request, world_model_id: str, entity_id: str, composition_id: str,
                          version: Version = None, as_of: AsOf = None) -> Response:
    m = model(request, world_model_id, READ)
    wm, _ltm, ref, _o = await read_at(m, version, as_of)
    entity_of(wm.graph, entity_id)
    c = wm.graph.compositions.get(composition_id)
    if c is None or c.entity_id != entity_id:
        raise ApiError("composition_not_found", f"entity {entity_id} has no composition {composition_id}")
    return one(request, pj.composition(wm.graph, c), ref)


@router.get(W + "/entities/{entity_id}/paths", summary="An entity's named paths")
async def list_paths(request: Request, world_model_id: str, entity_id: str, version: Version = None,
                     as_of: AsOf = None, limit: Limit = 50, cursor: Cursor = None) -> Response:
    m = model(request, world_model_id, READ)
    wm, _ltm, ref, off = await read_at(m, version, as_of, cursor)
    entity_of(wm.graph, entity_id)
    rows = [pj.path(wm.graph, p) for p in sorted(wm.graph.paths.values(), key=lambda p: p.id)
            if p.entity_id == entity_id]
    chunk, nxt = page(rows, off, limit, ref["number"])
    return many(request, chunk, limit, nxt, ref)


@router.get(W + "/entities/{entity_id}/paths/{path_id}", summary="One named path")
async def get_path(request: Request, world_model_id: str, entity_id: str, path_id: str, version: Version = None,
                   as_of: AsOf = None) -> Response:
    m = model(request, world_model_id, READ)
    wm, _ltm, ref, _o = await read_at(m, version, as_of)
    entity_of(wm.graph, entity_id)
    p = wm.graph.paths.get(path_id)
    if p is None or p.entity_id != entity_id:
        raise ApiError("path_not_found", f"entity {entity_id} has no path {path_id}")
    return one(request, pj.path(wm.graph, p), ref)


@router.get(W + "/entities/{entity_id}/construction", summary="A company's whole construction (JSON, or markdown)")
async def get_construction(request: Request, world_model_id: str, entity_id: str,
                           format: Literal["json", "markdown"] = "json", version: Version = None,
                           as_of: AsOf = None) -> Response:
    from axelrod_wm.context.construction import construction_view, to_markdown

    m = model(request, world_model_id, READ)
    wm, _ltm, ref, _o = await read_at(m, version, as_of)
    entity_of(wm.graph, entity_id)
    if format == "markdown" or "text/markdown" in request.headers.get("accept", ""):
        return Response(to_markdown(construction_view(wm.graph, entity_id)), media_type="text/markdown",
                        headers={"X-Axelrod-API-Version": API_VERSION})
    return one(request, pj.construction(wm.graph, entity_id), ref)


@router.get(W + "/entities/{entity_id}/traces", summary="Every route from a change in one attribute to the accounts")
async def trace_into_entity(request: Request, world_model_id: str, entity_id: str,
                            from_: Annotated[str, Query(alias="from", min_length=1)], through_totals: bool = False,
                            max_depth: Annotated[int, Query(ge=1, le=16)] = 8, version: Version = None,
                            as_of: AsOf = None) -> Response:
    m = model(request, world_model_id, READ)
    wm, _ltm, ref, _o = await read_at(m, version, as_of)
    g = wm.graph
    entity_of(g, entity_id)
    sid = from_ if from_ in g.subentities else attribute_id(g, entity_id, from_)
    return one(request, pj.trace(g, sid, entity_id, through_totals, max_depth), ref)


# -- relationships and evidence --------------------------------------------------------------------------------------------
@router.get(W + "/relationships", summary="Relationships, filtered")
async def list_relationships(request: Request, world_model_id: str, source: str | None = None,
                             target: str | None = None, entity: str | None = None,
                             type: s.RelationshipType | None = None, calibration: s.Calibration | None = None,
                             status: Literal["active", "retired", "all"] = "active", version: Version = None,
                             as_of: AsOf = None, limit: Limit = 50, cursor: Cursor = None) -> Response:
    m = model(request, world_model_id, READ)
    wm, _ltm, ref, off = await read_at(m, version, as_of, cursor)

    def keep(i) -> bool:
        retired = i.retired_at is not None
        return ((status == "all" or (status == "retired") == retired) and (source is None or i.source_id == source)
                and (target is None or i.target_id == target)
                and (entity is None or entity in (pj.owner_of(i.source_id), pj.owner_of(i.target_id)))
                and (type is None or str(i.edge_type) == type)
                and (calibration is None or str(i.calibration) == calibration))

    rows = [i for _k, i in sorted(wm.graph.interactions.items()) if keep(i)]
    chunk, nxt = page(rows, off, limit, ref["number"])
    return many(request, [pj.relationship(i, wm.graph) for i in chunk], limit, nxt, ref)


def occurred_of(m) -> dict:
    """When each update's facts occurred (a reported figure's period end), by event id, from the reviewed changes."""
    return {pr.event.id: pr.event.occurred_at for pr in m.st.controller.proposals.values()
            if getattr(pr, "event", None) is not None and getattr(pr.event, "occurred_at", None) is not None}


def relationship_of(graph, rid: str):
    i = graph.interactions.get(rid)
    if i is None:
        raise ApiError("relationship_not_found", f"no relationship {rid}")
    return i


@router.get(W + "/relationships/{relationship_id}", summary="One relationship")
async def get_relationship(request: Request, world_model_id: str, relationship_id: str, version: Version = None,
                           as_of: AsOf = None) -> Response:
    m = model(request, world_model_id, READ)
    wm, _ltm, ref, _o = await read_at(m, version, as_of)
    return one(request, pj.relationship(relationship_of(wm.graph, relationship_id), wm.graph), ref, tag=True)


@router.get(W + "/relationships/{relationship_id}/evidence", summary="A relationship's evidence")
async def list_relationship_evidence(request: Request, world_model_id: str, relationship_id: str,
                                     version: Version = None, as_of: AsOf = None, limit: Limit = 50,
                                     cursor: Cursor = None) -> Response:
    m = model(request, world_model_id, READ)
    wm, _ltm, ref, off = await read_at(m, version, as_of, cursor)
    i = relationship_of(wm.graph, relationship_id)
    chunk, nxt = page(list(i.evidence), off, limit, ref["number"])
    return many(request, [pj.evidence(e, i.id) for e in chunk], limit, nxt, ref)


@router.get(W + "/evidence/{evidence_id}", summary="One evidence record")
async def get_evidence(request: Request, world_model_id: str, evidence_id: str, version: Version = None,
                       as_of: AsOf = None) -> Response:
    m = model(request, world_model_id, READ)
    wm, _ltm, ref, _o = await read_at(m, version, as_of)
    for _k, i in sorted(wm.graph.interactions.items()):
        for e in i.evidence:
            if e.id == evidence_id:
                return one(request, pj.evidence(e, i.id), ref)
    raise ApiError("evidence_not_found", f"no evidence {evidence_id}")


# -- concepts and groups ----------------------------------------------------------------------------------------------------
@router.get(W + "/concepts", summary="The taxonomy's concepts")
async def list_concepts(request: Request, world_model_id: str, version: Version = None, as_of: AsOf = None,
                        limit: Limit = 50, cursor: Cursor = None) -> Response:
    m = model(request, world_model_id, READ)
    _wm, ltm, ref, off = await read_at(m, version, as_of, cursor)
    tax = ltm.object_generalizations.taxonomy
    chunk, nxt = page(sorted(n for n in tax.nodes if n != tax.root_id), off, limit, ref["number"])
    return many(request, [pj.concept(tax, n) for n in chunk], limit, nxt, ref)


@router.get(W + "/concepts/{concept_id}", summary="One concept and its entities")
async def get_concept(request: Request, world_model_id: str, concept_id: str, version: Version = None,
                      as_of: AsOf = None) -> Response:
    m = model(request, world_model_id, READ)
    _wm, ltm, ref, _o = await read_at(m, version, as_of)
    tax = ltm.object_generalizations.taxonomy
    if concept_id not in tax.nodes or concept_id == tax.root_id:
        raise ApiError("concept_not_found", f"no concept {concept_id}")
    return one(request, pj.concept(tax, concept_id), ref)


@router.get(W + "/groups", summary="Recurring configurations of entities")
async def list_groups(request: Request, world_model_id: str, version: Version = None, as_of: AsOf = None,
                      limit: Limit = 50, cursor: Cursor = None) -> Response:
    m = model(request, world_model_id, READ)
    wm, ltm, ref, off = await read_at(m, version, as_of, cursor)
    chunk, nxt = page(sorted(wm.graph.instances), off, limit, ref["number"])
    return many(request, [pj.group(ltm, wm.graph.instances[i]) for i in chunk], limit, nxt, ref)


@router.get(W + "/groups/{group_id}", summary="One group")
async def get_group(request: Request, world_model_id: str, group_id: str, version: Version = None,
                    as_of: AsOf = None) -> Response:
    m = model(request, world_model_id, READ)
    wm, ltm, ref, _o = await read_at(m, version, as_of)
    if group_id not in wm.graph.instances:
        raise ApiError("group_not_found", f"no group {group_id}")
    return one(request, pj.group(ltm, wm.graph.instances[group_id]), ref)


# -- the graph and exports -----------------------------------------------------------------------------------------------------
@router.get(W + "/graph", summary="A subgraph for an agent's context window")
async def get_graph(request: Request, world_model_id: str, entities: str = "", attributes: str = "",
                    q: Annotated[str, Query(max_length=200)] = "", depth: Annotated[int, Query(ge=0, le=4)] = 1,
                    limit: Annotated[int, Query(ge=1, le=2000)] = 200, version: Version = None,
                    as_of: AsOf = None) -> Response:
    m = model(request, world_model_id, READ)
    wm, ltm, ref, _o = await read_at(m, version, as_of)
    g = wm.graph
    seeds: set[str] = set()
    for eid in (x.strip() for x in entities.split(",") if x.strip()):
        entity_of(g, eid)
        seeds |= set(pj.own_attributes(wm, eid))
    for sid in (x.strip() for x in attributes.split(",") if x.strip()):
        if sid not in g.subentities:
            raise ApiError("attribute_not_found", f"no attribute {sid}")
        seeds.add(sid)
    if q.strip():
        from axelrod_wm.ingest.gazetteer import Gazetteer

        for hit in Gazetteer(g).find(q):
            seeds |= {hit.subentity_id} if hit.subentity_id else set(pj.own_attributes(wm, hit.entity_id))
    if not entities.strip() and not attributes.strip() and not q.strip():
        seeds = set(g.subentities)
    reach, frontier = set(seeds), set(seeds)
    links = live(g)
    for _ in range(depth):
        nxt = {i.target_id for i in links if i.source_id in frontier} | {i.source_id for i in links if i.target_id in frontier}
        frontier = nxt - reach
        reach |= nxt
    keep = sorted(reach)[:limit]
    by_entity: dict[str, list[str]] = {}
    for sid in keep:
        by_entity.setdefault(g.subentities[sid].entity_id, []).append(sid)
    kept = set(keep)
    body = {"entities": [pj.entity(wm, ltm, e, by_entity[e], occurred=occurred_of(m)) for e in sorted(by_entity)],
            "relationships": [pj.relationship(i, wm.graph).model_dump(mode="json") for i in links
                              if i.source_id in kept and i.target_id in kept],
            "truncated": len(reach) > limit}
    return one(request, body, ref)


@router.get(W + "/exports/v4.1.4", summary="The world model in the client's v4.1.4 format")
async def export_v414(request: Request, world_model_id: str, simulation: str | None = None) -> Response:
    from axelrod_wm.context.v4 import context_pack

    m = model(request, world_model_id, READ)

    def run() -> tuple[dict, dict]:
        ctl = m.st.controller
        fc = ctl.forecast(simulation) if simulation else None
        if simulation and fc is None:
            raise ApiError("simulation_not_found", f"no simulation {simulation}")
        script = m.st.runner.script
        eng = ctl.engine
        pack = context_pack(eng.wm, eng.ltm, scenario_id=script.id, title=script.title.split(":")[0],
                            book=list((ctl.watchlist() or {}).get("entities", [])), version=eng.version,
                            state_hash=eng.state_hash, forecast=fc,
                            explanation=ctl.explanation(fc.explanation_id) if fc else None,
                            pack_cfg=script.context_pack)
        return pack, vref(m.st)

    pack, ref = await m.st.call(run)
    return one(request, pack, ref)
