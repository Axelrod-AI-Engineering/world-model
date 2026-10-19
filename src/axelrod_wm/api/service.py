"""The world model as a service (Oct 17): the API other services call, at /api/world-model.

It follows core's conventions (Axelrod-AI-Engineering/core, docs/conventions.md): every response carries
`X-Axelrod-API-Version: 1`; errors are `{"error": {"code", "message", "details"?}}`; request bodies are strict
(unknown fields are refused); writes are idempotent (a document is stored once per content hash, an imported item
once per id). Every read says which state it read (`state.version`, `state.state_hash`, `state.as_of`), and reads
can be pinned to a past version or date, because a reproducible read cannot rest on "latest".

A caller authenticates with an API key (api/keys.py) and acts as one login: its engine and its partition of the
lakehouse (the tenant). The same functions back the MCP tools (api/mcp.py). docs/api.md is the reference.

    state & reads   GET  /state  /query  /nodes  /entities/{id}  /values/{id}  /taxonomy  /context/v4
    documents       POST /documents (multipart)   GET /documents  /documents/{id}  .../text  .../chunks  .../raw
                    POST /documents/{id}/extract   DELETE /documents/{id}
    bundles         POST /bundles   GET /bundles  /bundles/{id}   POST /bundles/{id}/import
    search          GET  /search?q=&mode=keyword|prefix|semantic|graph|hybrid
    review          GET  /proposals   POST /proposals/{id}/approve  /proposals/{id}/reject
    forecasts       POST /forecasts   GET /forecasts  /forecasts/{id}  /forecasts/{id}/brief
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from axelrod_wm.api.app import AppState, state_for
from axelrod_wm.control.controller import ControllerError
from axelrod_wm.ingest.pipeline import Ingestor, IngestResult
from axelrod_wm.lake.search import MODES, Searcher
from axelrod_wm.lake.store import DEFAULT_TENANT, LakeStore
from axelrod_wm.repo.snapshots import RestoreError

API_VERSION = "1"
MAX_UPLOAD = 50 * 1024 * 1024
MAX_FILES = 20


# -- core's envelope and header ---------------------------------------------------------------------------------------
class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


def envelope(status: int, code: str, message: str, details: Any = None) -> JSONResponse:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(body, status_code=status, headers={"X-Axelrod-API-Version": API_VERSION})


CODES = {400: "invalid_request", 401: "authentication_required", 403: "forbidden", 404: "not_found",
         409: "conflict", 413: "payload_too_large", 415: "unsupported_media_type", 422: "invalid_request"}


class ServiceRoute(APIRoute):
    """Every service route answers in core's envelope and carries the API version header."""

    def get_route_handler(self) -> Callable:
        handler = super().get_route_handler()

        async def wrapped(request: Request) -> Response:
            try:
                resp = await handler(request)
            except ServiceError as e:
                return envelope(e.status, e.code, e.message, e.details)
            except RequestValidationError as e:
                return envelope(422, "invalid_request", "the request is not valid", json.loads(json.dumps(
                    e.errors(), default=str)))
            except ValidationError as e:
                return envelope(422, "invalid_request", "the request is not valid", json.loads(e.json()))
            except HTTPException as e:
                return envelope(e.status_code, CODES.get(e.status_code, "error"), str(e.detail))
            except ControllerError as e:
                return envelope(409, "conflict", str(e))
            except RestoreError as e:
                return envelope(404, "version_not_found", str(e))
            except KeyError as e:
                return envelope(404, "not_found", f"not found: {e.args[0] if e.args else ''}")
            except ValueError as e:
                return envelope(400, "invalid_request", str(e))
            resp.headers["X-Axelrod-API-Version"] = API_VERSION
            return resp

        return wrapped


router = APIRouter(prefix="/api/world-model", route_class=ServiceRoute, tags=["world model service"])


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# -- who is asking, and their engine and lakehouse ------------------------------------------------------------------
def st_of(request: Request) -> AppState:
    return state_for(request.app, request.scope)


def tenant_of(request: Request) -> str:
    return request.scope.get("axelrod_login") or DEFAULT_TENANT


ON_BEHALF_OF = "x-axelrod-on-behalf-of"
_PERSON = re.compile(r"[A-Za-z0-9._:@/-]{1,128}")


def caller_of(request: Request) -> str:
    """Who is asking: the key's caller, and, when a service such as core calls for one of its users, that user
    (`X-Axelrod-On-Behalf-Of`), so approvals and imports record the person as well as the service."""
    caller = request.scope.get("axelrod_caller") or "anonymous"
    who = request.headers.get(ON_BEHALF_OF)
    if who is None:
        return caller
    if not _PERSON.fullmatch(who):
        raise ServiceError(400, "invalid_request", f"{ON_BEHALF_OF} must be 1-128 letters, digits, or ._:@/-")
    return f"{caller} for {who}"


def lake(app: Any) -> LakeStore:
    return app.state.lake


def ingestor(app: Any) -> Ingestor:
    return app.state.ingestor


def searcher(app: Any, graph: Any) -> Searcher:
    return Searcher(lake(app), ingestor(app).embedder, graph)


def inverted_surfaces(st: AppState) -> list[str]:
    """The question subjects the world's templates mark as a value's reciprocal ("the yen" for USD/JPY)."""
    wd = st.controller.world_dir()
    path = Path(wd) / "templates.yaml" if wd is not None else None
    if path is None or not path.exists():
        return []
    rules = yaml.safe_load(path.read_text()) or {}
    return sorted(s["pattern"] for s in rules.get("subjects", []) if s.get("invert"))


# -- the state a read is of --------------------------------------------------------------------------------------------
def state_identity(st: AppState, version: int | None = None) -> dict:
    eng = st.controller.engine
    v = eng.version if version is None else version
    info = eng.snapshots.version_info(v) if v > 0 else None
    return {"scenario": st.scenario, "version": v, "state_hash": info.state_hash if info else eng.state_hash,
            "as_of": (info.recorded_at if info else eng.wm.clock).isoformat(), "latest_version": eng.version,
            "clock": eng.wm.clock.isoformat()}


def pinned(st: AppState, version: int | None, as_of: datetime | None) -> tuple[Any, Any, int]:
    """(working memory, long-term memory, version) for a read: the current state, or a past one by version or date."""
    eng = st.controller.engine
    if as_of is not None:
        # the last whole processed day at or before the date (a day's close); a model with no closed day yet (a
        # seeded one, before its first import) answers with its latest version at or before the date
        t = as_of if as_of.tzinfo else as_of.replace(tzinfo=UTC)
        known = [v for v in eng.snapshots.storage.versions() if v.recorded_at <= t]
        closes = [v.version for v in known if v.cause.startswith(("close:", "consolidation:"))]
        best = max(closes) if closes else max((v.version for v in known), default=0)
        if best == 0:
            raise ServiceError(404, "version_not_found", f"the world model has no state at or before {t.isoformat()}")
        wm, ltm = eng.snapshots.restore(best)
        return wm, ltm, best
    if version is None or version == eng.version:
        return eng.wm, eng.ltm, eng.version
    if not 0 < version < eng.version:
        raise ServiceError(404, "version_not_found", f"version {version} is not in this world model (latest {eng.version})")
    wm, ltm = eng.snapshots.restore(version)
    return wm, ltm, version


# -- nodes and edges, Erid-compatible ----------------------------------------------------------------------------------
def _summary(s: Any) -> dict:
    d = s.posterior
    out = {"mean": round(float(d.mean()), 6), "sd": round(float(d.sd()), 6)}
    try:
        out |= {"q05": round(float(d.quantile(0.05)), 6), "q95": round(float(d.quantile(0.95)), 6)}
    except (AttributeError, ValueError):
        pass
    return out


def concept_names(ltm: Any, gid: str | None) -> list[str]:
    tax = ltm.object_generalizations.taxonomy
    if not gid or gid not in tax.nodes:
        return []
    return [tax.nodes[n].name for n in tax.path_from_root(gid) if n != tax.root_id]


def entity_node(wm: Any, ltm: Any, eid: str) -> dict:
    e = wm.graph.entities[eid]
    kind = str(e.kind)
    return {"id": eid, "node_type": "entity", "erid_kind": "company" if kind == "company" else kind,
            "caption": e.name, "aliases": list(e.aliases), "description": e.description,
            "concepts": concept_names(ltm, e.generalization_id), "features": dict(e.features),
            "value_ids": list(e.subentity_ids)}


def value_node(wm: Any, sid: str) -> dict:
    s = wm.graph.subentities[sid]
    owner = wm.graph.entities.get(s.entity_id)
    return {"id": sid, "node_type": "value", "erid_kind": "kpi" if owner is not None and str(owner.kind) == "company" else "factor",
            "caption": s.name, "aliases": list(s.aliases), "entity_id": s.entity_id, "unit": s.unit,
            "value_concept": s.attribute_kind, "family": str(s.posterior.family), "observed": bool(s.observed),
            **_summary(s)}


def edge(i: Any) -> dict:
    """A link as an edge. An accounting link is `part_of` its total. An uncalibrated link has a sign but no size: its
    effect and timing are null, never 0, so a reader cannot take "size unknown" for "no effect"."""
    k = i.forward.kernel
    sized = i.quantified
    return {"id": i.id, "from_id": i.source_id, "to_id": i.target_id,
            "relation": "part_of" if str(i.edge_type) == "accounting" else "causes", "label": i.label,
            "edge_type": str(i.edge_type), "calibration": str(i.calibration), "sign": "+" if i.polarity() > 0 else "-",
            "effect_sd_per_sd": round(float(i.forward.effect.mean()), 6) if sized else None,
            "existence_p": round(float(i.existence.mean()), 6),
            "delay_days": round(float(k.delay.mean()), 3) if sized else None,
            "lag_days": round(float(k.lag.mean()), 3) if sized else None,
            "duration_days": None if k.duration is None or not sized else round(float(k.duration.mean()), 3),
            "mechanism": i.transition.mechanism if i.transition is not None else None,
            "evidence_count": len(i.evidence) + i.evidence_dropped, "origin": str(i.origin)}


def query_graph(wm: Any, ltm: Any, *, node_ids: list[str], q: str, depth: int, limit: int) -> dict:
    g = wm.graph
    seeds: set[str] = set()
    for nid in node_ids:
        if nid in g.entities:
            seeds |= set(g.entities[nid].subentity_ids)
        elif nid in g.subentities:
            seeds.add(nid)
        else:
            raise ServiceError(404, "node_not_found", f"no entity or value {nid}")
    if q.strip():
        from axelrod_wm.ingest.gazetteer import Gazetteer

        for m in Gazetteer(g).find(q):
            seeds |= {m.subentity_id} if m.subentity_id else set(g.entities[m.entity_id].subentity_ids)
    if not node_ids and not q.strip():
        seeds = set(g.subentities)
    reach = set(seeds)
    live = sorted(g.active_interactions(), key=lambda x: x.id)
    frontier = set(seeds)
    for _ in range(max(0, depth)):
        nxt = {i.target_id for i in live if i.source_id in frontier} | {i.source_id for i in live if i.target_id in frontier}
        frontier = nxt - reach
        reach |= nxt
    values = sorted(reach)[:limit]
    keep = set(values)
    ents = sorted({g.subentities[s].entity_id for s in values})
    return {"entities": [entity_node(wm, ltm, e) for e in ents], "values": [value_node(wm, s) for s in values],
            "edges": [edge(i) for i in live if i.source_id in keep and i.target_id in keep],
            "missing_data": [], "truncated": len(reach) > limit}


# -- state and reads ----------------------------------------------------------------------------------------------------
@router.get("/state", summary="The state reads are served from: version, hash, clock, and counts")
async def get_state(request: Request) -> dict:
    st = st_of(request)

    def run() -> dict:
        g = st.controller.engine.wm.graph
        return {"state": state_identity(st), "tenant": tenant_of(request), "caller": caller_of(request),
                "counts": {"entities": len(g.entities), "values": len(g.subentities),
                           "interactions": len(g.active_interactions()), "superentity_instances": len(g.instances)},
                "lake": lake(request.app).stats(tenant_of(request))}

    return await st.call(run)


@router.get("/query", summary="world_model_query: entities, values, and causal edges at a version or date")
async def query(request: Request, node_ids: str = Query("", description="comma-separated entity or value ids"),
                q: str = Query("", description="names to find, e.g. 'Tokio Marine yields'"),
                depth: int = Query(1, ge=0, le=4), limit: int = Query(200, ge=1, le=2000),
                version: int | None = Query(None, ge=1), as_of: datetime | None = Query(None)) -> dict:
    st = st_of(request)

    def run() -> dict:
        wm, ltm, v = pinned(st, version, as_of)
        ids = [x.strip() for x in node_ids.split(",") if x.strip()]
        return {"state": state_identity(st, v), **query_graph(wm, ltm, node_ids=ids, q=q, depth=depth, limit=limit)}

    return await st.call(run)


@router.get("/nodes", summary="Entities and values whose names contain or start with q")
async def nodes(request: Request, q: str = Query("", max_length=200), limit: int = Query(50, ge=1, le=1000)) -> dict:
    st = st_of(request)

    def run() -> dict:
        wm, ltm = st.controller.engine.wm, st.controller.engine.ltm
        p = q.strip().lower()
        found = []
        for eid, e in sorted(wm.graph.entities.items()):
            if not p or any(p in n.lower() for n in (e.name, *e.aliases, eid)):
                found.append(entity_node(wm, ltm, eid))
        for sid, s in sorted(wm.graph.subentities.items()):
            if not p or any(p in n.lower() for n in (s.name, *s.aliases, sid)):
                found.append(value_node(wm, sid))
        found.sort(key=lambda n: (0 if n["caption"].lower().startswith(p) else 1, n["node_type"], n["id"]))
        return {"state": state_identity(st), "nodes": found[:limit], "truncated": len(found) > limit}

    return await st.call(run)


@router.get("/entities/{entity_id}", summary="One entity: its values, concepts, and the links in and out")
async def get_entity(request: Request, entity_id: str) -> dict:
    st = st_of(request)

    def run() -> dict:
        wm, ltm = st.controller.engine.wm, st.controller.engine.ltm
        if entity_id not in wm.graph.entities:
            raise ServiceError(404, "node_not_found", f"no entity {entity_id}")
        vals = set(wm.graph.entities[entity_id].subentity_ids)
        links = [edge(i) for i in sorted(wm.graph.active_interactions(), key=lambda x: x.id)
                 if i.source_id in vals or i.target_id in vals]
        return {"state": state_identity(st), "entity": entity_node(wm, ltm, entity_id),
                "values": [value_node(wm, s) for s in sorted(vals) if s in wm.graph.subentities], "edges": links}

    return await st.call(run)


@router.get("/values/{value_id}", summary="One value: its level and spread, and its drivers and effects")
async def get_value(request: Request, value_id: str) -> dict:
    st = st_of(request)

    def run() -> dict:
        wm = st.controller.engine.wm
        if value_id not in wm.graph.subentities:
            raise ServiceError(404, "node_not_found", f"no value {value_id}")
        live = sorted(wm.graph.active_interactions(), key=lambda x: x.id)
        return {"state": state_identity(st), "value": value_node(wm, value_id),
                "drivers": [edge(i) for i in live if i.target_id == value_id],
                "effects": [edge(i) for i in live if i.source_id == value_id]}

    return await st.call(run)


@router.get("/construction/{entity_id}", summary="A company's business construction: compositions, paths, transitions")
async def construction(request: Request, entity_id: str, format: Literal["json", "markdown"] = "json",
                       version: int | None = Query(None, ge=1), as_of: datetime | None = Query(None)) -> Any:
    """The company's compositions, its named paths with every transition (calibrated or not), its links' calibration,
    and any structural problems (context/construction.py), at the current state or a pinned one."""
    from axelrod_wm.context.construction import construction_view, to_markdown

    st = st_of(request)

    def run() -> Any:
        wm, _ltm, v = pinned(st, version, as_of)
        if entity_id not in wm.graph.entities:
            raise ServiceError(404, "node_not_found", f"no entity {entity_id}")
        view = construction_view(wm.graph, entity_id)
        if format == "markdown":
            return Response(to_markdown(view), media_type="text/markdown",
                            headers={"X-Axelrod-API-Version": API_VERSION})
        return {"state": state_identity(st, v), "construction": view}

    return await st.call(run)


@router.get("/construction/{entity_id}/trace", summary="Trace a change through every link to a company's endpoints")
async def construction_trace(request: Request, entity_id: str, start: str = Query(..., min_length=1),
                             version: int | None = Query(None, ge=1), as_of: datetime | None = Query(None),
                             through_totals: bool = Query(False), max_depth: int = Query(8, ge=1, le=16)) -> dict:
    """Each route from `start` to the company's values, where it ends, and what it rests on (uncalibrated steps,
    steps without a transition). With `through_totals`, routes go on through the totals they reach (within
    `max_depth` links)."""
    from axelrod_wm.context.construction import trace

    st = st_of(request)

    def run() -> dict:
        wm, _ltm, v = pinned(st, version, as_of)
        if entity_id not in wm.graph.entities:
            raise ServiceError(404, "node_not_found", f"no entity {entity_id}")
        if start not in wm.graph.subentities:
            raise ServiceError(404, "node_not_found", f"no value {start}")
        return {"state": state_identity(st, v),
                "trace": trace(wm.graph, start, entity_id, max_depth=max_depth, through_totals=through_totals)}

    return await st.call(run)


@router.get("/taxonomy", summary="The static taxonomy: concepts, their parents, and their entities")
async def taxonomy(request: Request) -> dict:
    st = st_of(request)

    def run() -> dict:
        tax = st.controller.engine.ltm.object_generalizations.taxonomy
        concepts = [{"id": nid, "name": n.name, "parent": n.parent_id, "entity_ids": sorted(n.instance_ids)}
                    for nid, n in sorted(tax.nodes.items()) if nid != tax.root_id]
        return {"state": state_identity(st), "root": tax.root_id, "concepts": concepts}

    return await st.call(run)


@router.get("/context/v4", summary="The world model in a client's v4.1.4 world-model format")
async def context_v4(request: Request, forecast: str | None = None) -> dict:
    from axelrod_wm.context.v4 import context_pack

    st = st_of(request)

    def run() -> dict:
        ctl = st.controller
        fc = ctl.forecast(forecast) if forecast else None
        if forecast and fc is None:
            raise ServiceError(404, "forecast_not_found", f"no forecast {forecast}")
        script = st.runner.script
        eng = ctl.engine
        return context_pack(eng.wm, eng.ltm, scenario_id=script.id, title=script.title.split(":")[0],
                            book=list((ctl.watchlist() or {}).get("entities", [])), version=eng.version,
                            state_hash=eng.state_hash, forecast=fc,
                            explanation=ctl.explanation(fc.explanation_id) if fc else None, pack_cfg=script.context_pack)

    return await st.call(run)


# -- documents -----------------------------------------------------------------------------------------------------------
SourceType = Literal["broker_research", "expert_call", "news", "central_bank", "data", "filing", "client_model", "other"]


def result_view(r: IngestResult) -> dict:
    doc = r.document.model_dump(mode="json")
    return {"document": doc, "new": r.new, "chunks": r.chunks, "mentions": r.mentions, "signals": r.signals,
            "llm_signals": r.llm_signals, "warnings": r.warnings,
            "bundle": None if r.bundle is None else {"id": r.bundle.id, "items": r.bundle.items, "signals": r.bundle.signals}}


def _ingestor_for(request: Request, st: AppState) -> Ingestor:
    ing = ingestor(request.app)
    ing.inverted = frozenset(inverted_surfaces(st))
    return ing


@router.post("/documents", status_code=201,
             summary="Upload files: stored once per content hash, parsed, indexed, and read into an import bundle")
async def upload(request: Request, files: list[UploadFile] = File(..., description="one or more files"),
                 source: str = Form(""), source_type: SourceType = Form("other"),
                 published_at: datetime | None = Form(None, description="the documents' date, when known")) -> dict:
    st = st_of(request)
    if len(files) > MAX_FILES:
        raise ServiceError(413, "too_many_files", f"at most {MAX_FILES} files per request")
    blobs = []
    for f in files:
        data = await f.read()
        if len(data) > MAX_UPLOAD:
            raise ServiceError(413, "payload_too_large", f"{f.filename} is over {MAX_UPLOAD // (1024 * 1024)} MB")
        blobs.append((data, f.filename or "upload.bin"))
    tenant, caller = tenant_of(request), caller_of(request)

    def run() -> list[dict]:
        ing = _ingestor_for(request, st)
        out = ing.ingest_many(tenant, blobs, st.controller.engine.wm.graph, source=source, source_type=source_type,
                              published_at=published_at, uploaded_by=caller)
        return [result_view(r) for r in out]

    results = await st.call(run)
    return {"state": await st.call(state_identity, st), "results": results}


@router.get("/documents", summary="Stored documents, by event time (default) or ingestion time")
async def list_documents(request: Request, order: Literal["event_time", "ingested_at"] = "event_time",
                         since: datetime | None = None, until: datetime | None = None,
                         limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)) -> dict:
    docs = lake(request.app).list_documents(tenant_of(request), since=since, until=until, order=order,
                                            limit=limit, offset=offset)
    return {"documents": [d.model_dump(mode="json") for d in docs], "order": order, "limit": limit, "offset": offset}


def _doc(request: Request, doc_id: str) -> Any:
    doc = lake(request.app).get_document(tenant_of(request), doc_id)
    if doc is None:
        raise ServiceError(404, "document_not_found", f"no document {doc_id}")
    return doc


@router.get("/documents/{doc_id}", summary="One document, its bundles, and how many chunks and mentions it has")
async def get_document(request: Request, doc_id: str) -> dict:
    doc = _doc(request, doc_id)
    lk, t = lake(request.app), tenant_of(request)
    return {"document": doc.model_dump(mode="json"), "chunks": len(lk.get_chunks(t, doc_id)),
            "mentions": len(lk.mentions_of(t, doc_id=doc_id)),
            "bundles": [{"id": b.id, "items": b.items, "signals": b.signals, "created_at": b.created_at.isoformat()}
                        for b in lk.list_bundles(t, doc_id=doc_id)]}


@router.get("/documents/{doc_id}/text", summary="The text the parser extracted")
async def document_text(request: Request, doc_id: str) -> dict:
    _doc(request, doc_id)
    got = lake(request.app).get_text(tenant_of(request), doc_id)
    if got is None:
        raise ServiceError(409, "not_parsed", "this document has not been parsed")
    return {"id": doc_id, "parser": got[1], "text": got[0]}


@router.get("/documents/{doc_id}/chunks", summary="The document's chunks and the names recognized in each")
async def document_chunks(request: Request, doc_id: str) -> dict:
    _doc(request, doc_id)
    lk, t = lake(request.app), tenant_of(request)
    mentions: dict[int, list[dict]] = {}
    for m in lk.mentions_of(t, doc_id=doc_id):
        mentions.setdefault(m.ord, []).append({"entity_id": m.entity_id, "value_id": m.subentity_id, "surface": m.surface})
    return {"id": doc_id, "chunks": [{**c.model_dump(mode="json"), "mentions": mentions.get(c.ord, [])}
                                     for c in lk.get_chunks(t, doc_id)]}


@router.get("/documents/{doc_id}/raw", summary="The file as uploaded")
async def document_raw(request: Request, doc_id: str) -> Response:
    doc = _doc(request, doc_id)
    data = lake(request.app).raw_bytes(tenant_of(request), doc_id)
    if data is None:
        raise ServiceError(404, "file_missing", "the stored file is missing")
    safe = re.sub(r'[^\w.\- ]', "_", doc.filename)
    return Response(data, media_type=doc.mime, headers={"Content-Disposition": f'attachment; filename="{safe}"'})


@router.post("/documents/{doc_id}/extract", summary="Read a stored document again, against the model as it is now")
async def extract_again(request: Request, doc_id: str) -> dict:
    st = st_of(request)
    _doc(request, doc_id)
    tenant = tenant_of(request)
    res = await st.call(lambda: _ingestor_for(request, st).process(tenant, doc_id, st.controller.engine.wm.graph))
    return {"state": await st.call(state_identity, st), "result": result_view(res)}


@router.delete("/documents/{doc_id}", summary="Delete a document, its text, chunks, indexes, and mentions")
async def delete_document(request: Request, doc_id: str) -> dict:
    _doc(request, doc_id)
    lake(request.app).delete_document(tenant_of(request), doc_id)
    return {"deleted": doc_id}


# -- bundles --------------------------------------------------------------------------------------------------------------
@router.post("/bundles", status_code=201, summary="Store an import bundle (axelrod.import/v1) written by another agent")
async def post_bundle(request: Request) -> dict:
    st = st_of(request)
    try:
        body = await request.json()
    except json.JSONDecodeError as err:
        raise ServiceError(400, "invalid_json", f"the body is not JSON: {err}") from err
    from axelrod_wm.intake.bundle import ImportBundle

    ImportBundle.model_validate(body)
    data = json.dumps(body, sort_keys=True, ensure_ascii=False).encode()
    tenant, caller = tenant_of(request), caller_of(request)
    res = await st.call(lambda: _ingestor_for(request, st).ingest_file(
        tenant, data, f"{body.get('title') or 'bundle'}.json"[:120], st.controller.engine.wm.graph, uploaded_by=caller))
    return {"state": await st.call(state_identity, st), "result": result_view(res)}


@router.get("/bundles", summary="Stored bundles, oldest first")
async def list_bundles(request: Request, doc_id: str | None = None, limit: int = Query(100, ge=1, le=1000)) -> dict:
    recs = lake(request.app).list_bundles(tenant_of(request), doc_id=doc_id, limit=limit)
    return {"bundles": [{"id": b.id, "doc_ids": b.doc_ids, "items": b.items, "signals": b.signals,
                         "created_at": b.created_at.isoformat(), "extractor_version": b.extractor_version} for b in recs]}


@router.get("/bundles/{bundle_id}", summary="One bundle, whole")
async def get_bundle(request: Request, bundle_id: str) -> dict:
    rec = lake(request.app).get_bundle(tenant_of(request), bundle_id)
    if rec is None:
        raise ServiceError(404, "bundle_not_found", f"no bundle {bundle_id}")
    return {"id": rec.id, "doc_ids": rec.doc_ids, "created_at": rec.created_at.isoformat(),
            "extractor_version": rec.extractor_version, "bundle": rec.bundle,
            "imports": [i.model_dump(mode="json") for i in lake(request.app).list_imports(tenant_of(request), bundle_id=bundle_id)]}


class ImportIn(_In):
    review: Literal["queue", "auto"] = Field("queue", description="queue: each item waits for a person's review; "
                                                                   "auto: each is approved as the caller")
    item_ids: list[str] | None = Field(None, description="only these items (default: all)")


@router.post("/bundles/{bundle_id}/import",
             summary="Fold a bundle into the model: its items, in event-time order, one graph update each")
async def import_bundle(request: Request, bundle_id: str, body: ImportIn | None = None) -> dict:
    from axelrod_wm.api.routes import _importer, _resume_if_awaited
    from axelrod_wm.lake.store import ImportRecord

    b = body or ImportIn()
    st = st_of(request)
    tenant, caller = tenant_of(request), caller_of(request)
    rec = lake(request.app).get_bundle(tenant, bundle_id)
    if rec is None:
        raise ServiceError(404, "bundle_not_found", f"no bundle {bundle_id}")
    before = await st.call(lambda: st.controller.engine.version)
    late_ids: list[str] = []

    def start() -> dict:
        runner = _importer(st)
        preview = runner.preview(rec.bundle)
        late_ids.extend(x["id"] for x in preview["items"] if x["status"] == "late"
                        and (b.item_ids is None or x["id"] in b.item_ids))
        try:
            return runner.import_items(rec.bundle, b.item_ids)
        except ControllerError as err:
            if "nothing new" in str(err):
                return {"update_id": None, "imported": [], "waiting_on": None, "state": "done"}
            raise ServiceError(409, "update_in_progress", str(err)) from err

    out = await st.call(start)
    approved: list[str] = []

    async def approve_all() -> None:
        # approve each item as it comes up for review, as the caller, and let the update run on to the next
        while True:
            pending = await st.call(lambda: [p.id for p in st.controller.pending_proposals()])
            if not pending:
                return
            for pid in pending:
                await st.call(lambda pid=pid: st.controller.approve(pid, by=caller, note="approved by API (review=auto)"))
                approved.append(pid)
                run_id = await st.call(_resume_if_awaited, st, pid)
                if run_id is not None:
                    await st.drive(run_id)

    if b.review == "auto" and out.get("update_id"):
        await approve_all()
    if out.get("imported"):
        lake(request.app).put_import(ImportRecord(tenant=tenant, bundle_id=bundle_id, imported_at=datetime.now(UTC),
                                                  update_id=out.get("update_id"), item_ids=out["imported"], by=caller))
    pending = await st.call(lambda: [p.id for p in st.controller.pending_proposals()])
    return {"state": await st.call(state_identity, st), "version_before": before, "update_id": out.get("update_id"),
            "imported": out.get("imported", []), "late": late_ids, "approved": approved,
            "pending_proposals": pending}


# -- search -----------------------------------------------------------------------------------------------------------------
@router.get("/search", summary="Keyword, prefix, semantic, graph, or hybrid search over documents and the model")
async def search(request: Request, q: str = Query(..., min_length=1, max_length=500),
                 mode: str = Query("hybrid", description=" | ".join(MODES)), limit: int = Query(20, ge=1, le=200)) -> dict:
    if mode not in MODES:
        raise ServiceError(422, "invalid_request", f"mode must be one of {', '.join(MODES)}")
    st = st_of(request)
    tenant = tenant_of(request)

    def run() -> dict:
        hits = searcher(request.app, st.controller.engine.wm.graph).search(tenant, q, mode, limit)
        return {"state": state_identity(st), "mode": mode, "hits": [h.model_dump(mode="json") for h in hits]}

    return await st.call(run)


# -- review -----------------------------------------------------------------------------------------------------------------
@router.get("/proposals", summary="Proposed graph updates, waiting for review by default")
async def proposals(request: Request, status: Literal["pending", "approved", "rejected", "all"] = "pending",
                    limit: int = Query(100, ge=1, le=1000)) -> dict:
    st = st_of(request)

    def run() -> dict:
        ctl = st.controller
        ps = [p for p in ctl.proposals.values() if status == "all" or str(p.status).endswith(status)]
        ps.sort(key=lambda p: (p.created_at, p.id))
        return {"state": state_identity(st), "proposals": [
            {"id": p.id, "kind": str(p.kind), "status": str(p.status), "title": getattr(p, "title", ""),
             "created_at": p.created_at.isoformat(), "market_event_id": getattr(p, "market_event_id", None),
             "ops": len(getattr(getattr(p, "event", None), "ops", []) or [])} for p in ps[:limit]]}

    return await st.call(run)


class DecisionIn(_In):
    note: str = Field("", max_length=2000)


async def _decide(request: Request, proposal_id: str, approve: bool, note: str) -> dict:
    from axelrod_wm.api.routes import _resume_if_awaited

    st = st_of(request)
    caller = caller_of(request)

    def decide() -> None:
        ctl = st.controller
        if proposal_id not in ctl.proposals:
            raise ServiceError(404, "proposal_not_found", f"no proposal {proposal_id}")
        if not str(ctl.proposals[proposal_id].status).endswith("pending"):
            raise ServiceError(409, "already_decided", f"proposal {proposal_id} is {ctl.proposals[proposal_id].status}")
        if approve:
            ctl.approve(proposal_id, by=caller, note=note or None)
        else:
            ctl.reject(proposal_id, by=caller, note=note)

    await st.call(decide)
    run_id = await st.call(_resume_if_awaited, st, proposal_id)
    if run_id is not None:
        await st.drive(run_id)
    return {"state": await st.call(state_identity, st), "proposal_id": proposal_id,
            "status": await st.call(lambda: str(st.controller.proposals[proposal_id].status))}


@router.post("/proposals/{proposal_id}/approve", summary="Approve a proposed graph update (as the caller)")
async def approve(request: Request, proposal_id: str, body: DecisionIn | None = None) -> dict:
    return await _decide(request, proposal_id, True, (body or DecisionIn()).note)


@router.post("/proposals/{proposal_id}/reject", summary="Reject a proposed graph update; a note is required")
async def reject(request: Request, proposal_id: str, body: DecisionIn) -> dict:
    if not body.note.strip():
        raise ServiceError(422, "note_required", "a rejection needs a note")
    return await _decide(request, proposal_id, False, body.note)


# -- forecasts --------------------------------------------------------------------------------------------------------------
class ForecastIn(_In):
    question: str | None = Field(None, max_length=500, description="a what-if, e.g. 'What if the BoJ hiked by 25bp next quarter?'")
    thesis_id: str | None = Field(None, description="or a ready thesis of the scenario")
    horizon_days: int = Field(182, ge=7, le=1095)


def forecast_summary(st: AppState, fc: Any) -> dict:
    g = st.controller.engine.wm.graph

    def nm(sid: str) -> str:
        return g.subentities[sid].name if sid in g.subentities else sid

    targets = []
    for sid in fc.targets:
        es = fc.effect_summary.get(sid) or []
        last = es[-1] if es else None
        targets.append({"value_id": sid, "caption": nm(sid), "effect_sd": None if last is None else
                        {"q05": round(last.q05, 4), "q50": round(last.q50, 4), "q95": round(last.q95, 4)}})
    return {"id": fc.id, "thesis_id": fc.thesis_id, "question": fc.question, "based_on_version": fc.based_on_version,
            "seed": fc.seed, "config_hash": fc.config_hash, "horizon_days": fc.horizon_days,
            "created_at": fc.created_at.isoformat(), "targets": targets,
            "transmission": [{"value_id": t.subentity_id, "caption": nm(t.subentity_id), "order": t.order,
                              "peak_sd": round(t.peak, 4), "peak_day": t.peak_day, "arrives_day": t.arrives_day,
                              "effect_sd": round(t.effect, 4), "material": t.material}
                             for t in sorted(fc.transmission or [], key=lambda t: (t.order, -abs(t.effect)))][:60],
            "scenario_table": fc.scenario_table, "unquantified": fc.unquantified, "coverage": fc.coverage}


@router.post("/forecasts", status_code=201, summary="Pose a thesis (a what-if question, or a ready thesis) and forecast it")
async def post_forecast(request: Request, body: ForecastIn) -> dict:
    if bool(body.question) == bool(body.thesis_id):
        raise ServiceError(422, "invalid_request", "give exactly one of question and thesis_id")
    st = st_of(request)

    def run() -> dict:
        ctl = st.controller
        if body.thesis_id:
            from axelrod_wm.sim.scenario import load_theses, thesis_from_spec

            specs, _h = load_theses(ctl.scenario_dir) if ctl.scenario_dir is not None else ({}, {})
            if body.thesis_id not in specs:
                raise ServiceError(404, "thesis_not_found", f"no ready thesis {body.thesis_id}")
            thesis = thesis_from_spec(specs[body.thesis_id], ctl.now)
        else:
            try:
                thesis = ctl.thesis_from_question(body.question, horizon_days=body.horizon_days)
            except Exception as err:
                raise ServiceError(422, "question_not_understood", str(err)) from err
        fc = ctl.pose_thesis(thesis)
        return {"state": state_identity(st), "forecast": forecast_summary(st, fc)}

    return await st.call(run)


@router.get("/forecasts", summary="Forecasts posed so far, oldest first")
async def list_forecasts(request: Request) -> dict:
    st = st_of(request)

    def run() -> dict:
        fcs = sorted(st.controller.forecasts.values(), key=lambda f: (f.created_at, f.id))
        return {"forecasts": [{"id": f.id, "thesis_id": f.thesis_id, "question": f.question,
                               "based_on_version": f.based_on_version, "created_at": f.created_at.isoformat()} for f in fcs]}

    return await st.call(run)


@router.get("/forecasts/{forecast_id}", summary="One forecast: targets, transmission by order, and the scenario table")
async def get_forecast(request: Request, forecast_id: str) -> dict:
    st = st_of(request)

    def run() -> dict:
        fc = st.controller.forecast(forecast_id)
        if fc is None:
            raise ServiceError(404, "forecast_not_found", f"no forecast {forecast_id}")
        return {"state": state_identity(st, fc.based_on_version), "forecast": forecast_summary(st, fc)}

    return await st.call(run)


@router.get("/forecasts/{forecast_id}/brief", summary="A forecast's brief: summary, timing, exposures, evidence")
async def get_brief(request: Request, forecast_id: str) -> dict:
    from axelrod_wm.api.brief import brief_view

    st = st_of(request)

    def run() -> dict:
        fc = st.controller.forecast(forecast_id)
        if fc is None:
            raise ServiceError(404, "forecast_not_found", f"no forecast {forecast_id}")
        # Oct 18: what the brief's numbers are made of (calculation coverage), beside them
        return {**brief_view(st.controller, forecast_id), "coverage": fc.coverage}

    return await st.call(run)
