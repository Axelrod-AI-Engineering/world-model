"""v1 work on the model (docs/api/openapi.yaml): events and what they did, documents, bundles, search, changes and
their review (human only), theses and simulations, and jobs."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi import Path as FPath
from fastapi.responses import Response

from axelrod_ingest.pipeline import Ingestor, IngestResult
from axelrod_wm.api.tokens import ADMIN, APPROVE, CHANGES, DOCUMENTS, READ, SIMULATIONS
from axelrod_wm.api.v1 import project as pj
from axelrod_wm.api.v1 import schemas as s
from axelrod_wm.api.v1.context import (
    Model,
    audit,
    decode_cursor,
    encode_cursor,
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
from axelrod_wm.api.v1.routes_model import AsOf, Cursor, Limit, Version, read_at
from axelrod_wm.control.controller import ControllerError

router = APIRouter(prefix="/v1", route_class=V1Route, tags=["v1"])
W = "/world-models/{world_model_id}"
MAX_UPLOAD = 50 * 1024 * 1024
MAX_FILES = 20
SourceType = Literal["broker_research", "expert_call", "news", "central_bank", "data", "filing", "client_model", "other"]


def base(m: Model) -> str:
    return f"/v1/world-models/{m.id}"


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


# -- documents ---------------------------------------------------------------------------------------------------------------
def inverted_surfaces(st: Any) -> list[str]:
    """The question subjects the world's templates mark as an attribute's reciprocal ("the yen" for USD/JPY)."""
    wd = st.controller.world_dir()
    path = Path(wd) / "templates.yaml" if wd is not None else None
    if path is None or not path.exists():
        return []
    rules = yaml.safe_load(path.read_text()) or {}
    return sorted(x["pattern"] for x in rules.get("subjects", []) if x.get("invert"))


def ingestor_for(request: Request, m: Model) -> Ingestor:
    ing: Ingestor = request.app.state.ingestor
    ing.inverted = frozenset(inverted_surfaces(m.st))
    return ing


def document_view(doc: Any) -> s.Document:
    return s.Document(id=doc.id, filename=doc.filename, media_type=doc.mime, size=doc.size, sha256=doc.sha256,
                      title=doc.title, source=doc.source, source_type=doc.source_type, status=doc.status,
                      published_at=doc.published_at, event_time=doc.event_time, ingested_at=doc.ingested_at,
                      uploaded_by=doc.uploaded_by, error=doc.error, meta=doc.meta)


def ingest_summary(r: IngestResult) -> dict:
    return {"document_id": r.document.id, "new": r.new, "status": r.document.status, "chunks": r.chunks,
            "mentions": r.mentions, "signals": r.signals, "warnings": r.warnings,
            "bundle_id": None if r.bundle is None else r.bundle.id}


@router.post(W + "/documents", status_code=202, summary="Upload files")
async def create_documents(request: Request, world_model_id: str,
                           files: list[UploadFile] = File(..., description="one or more files"),
                           source: str = Form(""), source_type: SourceType = Form("other"),
                           published_at: datetime | None = Form(None)) -> Response:
    m = model(request, world_model_id, DOCUMENTS)
    if len(files) > MAX_FILES:
        raise ApiError("too_many_files", f"at most {MAX_FILES} files per request")
    blobs = []
    for f in files:
        data = await f.read()
        if len(data) > MAX_UPLOAD:
            raise ApiError("payload_too_large", f"{f.filename} is over {MAX_UPLOAD // (1024 * 1024)} MB")
        blobs.append((data, f.filename or "upload.bin"))
    sub = principal(request).sub

    async def make() -> Response:
        async def work() -> dict:
            def run() -> list[IngestResult]:
                return ingestor_for(request, m).ingest_many(m.org, blobs, m.st.controller.engine.wm.graph,
                                                            source=source, source_type=source_type,
                                                            published_at=published_at, uploaded_by=sub)

            results = await m.st.call(run)
            return {"resource": "documents", "ids": [r.document.id for r in results],
                    "detail": {"results": [ingest_summary(r) for r in results]}}

        return await run_job(request, m, "document_ingestion", work)

    content = fingerprint([(name, hashlib.sha256(data).hexdigest()) for data, name in blobs])
    fp = fingerprint(content, source, source_type, str(published_at))
    return await idempotent(request, m, fp, make, content=content)


@router.get(W + "/documents", summary="Stored documents")
async def list_documents(request: Request, world_model_id: str,
                         order: Literal["event_time", "ingested_at"] = "event_time",
                         published_from: datetime | None = None, published_to: datetime | None = None,
                         limit: Limit = 50, cursor: Cursor = None) -> Response:
    m = model(request, world_model_id, READ)
    off, _v = decode_cursor(cursor)
    docs = lake(request.app).list_documents(m.org, since=published_from, until=published_to, order=order,
                                            limit=limit + 1, offset=off)
    nxt = encode_cursor(off + limit, None) if len(docs) > limit else None
    return many(request, [document_view(d) for d in docs[:limit]], limit, nxt)


def doc_of(request: Request, m: Model, document_id: str) -> Any:
    doc = lake(request.app).get_document(m.org, document_id)
    if doc is None:
        raise ApiError("document_not_found", f"no document {document_id}")
    return doc


@router.get(W + "/documents/{document_id}", summary="One document")
async def get_document(request: Request, world_model_id: str, document_id: str) -> Response:
    m = model(request, world_model_id, READ)
    return one(request, document_view(doc_of(request, m, document_id)))


@router.delete(W + "/documents/{document_id}", status_code=204, summary="Delete a document")
async def delete_document(request: Request, world_model_id: str, document_id: str) -> Response:
    m = model(request, world_model_id, ADMIN)
    doc_of(request, m, document_id)
    lake(request.app).delete_document(m.org, document_id)
    # the answers that named it would name a document that is gone: the same content uploads afresh
    lake(request.app).forget_idempotency(m.org, m.id, document_id)
    audit(request, m, 204, [document_id])
    return Response(status_code=204)


def chunks_of(request: Request, m: Model, document_id: str) -> list[s.Chunk]:
    lk = lake(request.app)
    mentions: dict[int, list[s.Mention]] = {}
    for x in lk.mentions_of(m.org, doc_id=document_id):
        mentions.setdefault(x.ord, []).append(s.Mention(entity_id=x.entity_id, attribute_id=x.subentity_id,
                                                        surface=x.surface))
    return [s.Chunk(document_id=document_id, ordinal=c.ord, start=c.start, end=c.end, page=c.page, section=c.section,
                    text=c.text, mentions=mentions.get(c.ord, [])) for c in lk.get_chunks(m.org, document_id)]


@router.get(W + "/documents/{document_id}/chunks", summary="A document's passages")
async def list_chunks(request: Request, world_model_id: str, document_id: str, limit: Limit = 50,
                      cursor: Cursor = None) -> Response:
    m = model(request, world_model_id, READ)
    off, _v = decode_cursor(cursor)
    doc_of(request, m, document_id)
    chunk, nxt = page(chunks_of(request, m, document_id), off, limit, None)
    return many(request, chunk, limit, nxt)


@router.get(W + "/documents/{document_id}/chunks/{ordinal}", summary="One passage")
async def get_chunk(request: Request, world_model_id: str, document_id: str,
                    ordinal: Annotated[int, FPath(ge=0)]) -> Response:
    m = model(request, world_model_id, READ)
    doc_of(request, m, document_id)
    found = next((c for c in chunks_of(request, m, document_id) if c.ordinal == ordinal), None)
    if found is None:
        raise ApiError("chunk_not_found", f"document {document_id} has no passage {ordinal}")
    return one(request, found)


@router.get(W + "/documents/{document_id}/content", summary="The extracted text, or the file as uploaded")
async def get_content(request: Request, world_model_id: str, document_id: str,
                      format: Literal["text", "raw"] = "text") -> Response:
    m = model(request, world_model_id, READ)
    doc = doc_of(request, m, document_id)
    if format == "raw":
        data = lake(request.app).raw_bytes(m.org, document_id)
        if data is None:
            raise ApiError("file_missing", "the stored file is missing")
        safe = re.sub(r'[^\w.\- ]', "_", doc.filename)
        return Response(data, media_type=doc.mime, headers={"Content-Disposition": f'attachment; filename="{safe}"'})
    got = lake(request.app).get_text(m.org, document_id)
    if got is None:
        raise ApiError("not_parsed", "this document has not been parsed")
    return one(request, s.DocumentText(document_id=document_id, parser=got[1], text=got[0]))


@router.post(W + "/documents/{document_id}/bundles", status_code=202, summary="Read a stored document again")
async def extract_document(request: Request, world_model_id: str, document_id: str) -> Response:
    m = model(request, world_model_id, DOCUMENTS)
    doc_of(request, m, document_id)

    async def make() -> Response:
        async def work() -> dict:
            res = await m.st.call(lambda: ingestor_for(request, m).process(m.org, document_id,
                                                                           m.st.controller.engine.wm.graph))
            return {"resource": "bundles", "ids": [] if res.bundle is None else [res.bundle.id],
                    "detail": ingest_summary(res)}

        return await run_job(request, m, "document_extraction", work)

    return await idempotent(request, m, fingerprint(document_id), make)


# -- bundles -------------------------------------------------------------------------------------------------------------------
def bundle_view(rec: Any) -> s.BundleSummary:
    return s.BundleSummary(id=rec.id, title=str(rec.bundle.get("title") or ""), document_ids=list(rec.doc_ids),
                           created_at=rec.created_at, extractor_version=rec.extractor_version, item_count=rec.items,
                           signal_count=rec.signals)


@router.post(W + "/bundles", status_code=201, summary="Store a bundle an agent wrote")
async def create_bundle(request: Request, world_model_id: str) -> Response:
    from axelrod_ingest.contract.bundle import ImportBundle

    m = model(request, world_model_id, DOCUMENTS)
    if not request.headers.get("content-type", "").startswith("application/json"):
        raise ApiError("unsupported_media_type", "a bundle is application/json")
    try:
        body = await request.json()
    except json.JSONDecodeError as err:
        raise ApiError("invalid_json", f"the body is not JSON: {err}") from err
    ImportBundle.model_validate(body)
    data = json.dumps(body, sort_keys=True, ensure_ascii=False).encode()
    sub = principal(request).sub

    async def make() -> Response:
        res = await m.st.call(lambda: ingestor_for(request, m).ingest_file(
            m.org, data, f"{body.get('title') or 'bundle'}.json"[:120], m.st.controller.engine.wm.graph,
            uploaded_by=sub))
        audit(request, m, 201, [res.document.id, res.bundle.id])
        return one(request, bundle_view(res.bundle), status=201, location=f"{base(m)}/bundles/{res.bundle.id}")

    content = fingerprint(body)
    return await idempotent(request, m, content, make, content=content)


@router.get(W + "/bundles", summary="Stored bundles, oldest first")
async def list_bundles(request: Request, world_model_id: str, document_id: str | None = None, limit: Limit = 50,
                       cursor: Cursor = None) -> Response:
    m = model(request, world_model_id, READ)
    off, _v = decode_cursor(cursor)
    recs = lake(request.app).list_bundles(m.org, doc_id=document_id, limit=100000)
    chunk, nxt = page(recs, off, limit, None)
    return many(request, [bundle_view(r) for r in chunk], limit, nxt)


def bundle_of(request: Request, m: Model, bundle_id: str) -> Any:
    rec = lake(request.app).get_bundle(m.org, bundle_id)
    if rec is None:
        raise ApiError("bundle_not_found", f"no bundle {bundle_id}")
    return rec


@router.get(W + "/bundles/{bundle_id}", summary="One bundle")
async def get_bundle(request: Request, world_model_id: str, bundle_id: str) -> Response:
    m = model(request, world_model_id, READ)
    return one(request, bundle_view(bundle_of(request, m, bundle_id)))


@router.get(W + "/bundles/{bundle_id}/items", summary="A bundle's dated items and their signals")
async def list_bundle_items(request: Request, world_model_id: str, bundle_id: str, limit: Limit = 50,
                            cursor: Cursor = None) -> Response:
    m = model(request, world_model_id, READ)
    off, _v = decode_cursor(cursor)
    chunk, nxt = page(list(bundle_of(request, m, bundle_id).bundle.get("items", [])), off, limit, None)
    return many(request, chunk, limit, nxt)


# -- search --------------------------------------------------------------------------------------------------------------------
@router.get(W + "/search", summary="Search passages and the model's names")
async def search(request: Request, world_model_id: str, q: Annotated[str, Query(min_length=1, max_length=500)],
                 mode: Literal["keyword", "prefix", "semantic", "graph", "hybrid"] = "hybrid",
                 limit: Annotated[int, Query(ge=1, le=200)] = 20) -> Response:
    from axelrod_ingest.lake.search import Searcher

    m = model(request, world_model_id, READ)

    def run() -> tuple[list[s.Hit], dict]:
        hits = Searcher(lake(request.app), request.app.state.ingestor.embedder,
                        m.st.controller.engine.wm.graph).search(m.org, q, mode, limit)
        return [s.Hit(kind=h.kind, score=h.score, text=h.text, why=list(h.why), document_id=h.doc_id, ordinal=h.ord,
                      title=h.title, filename=h.filename, event_time=h.event_time, ref=h.ref, entity_id=h.entity_id)
                for h in hits], vref(m.st)

    rows, ref = await m.st.call(run)
    return many(request, rows, limit, None, ref)


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


@router.post(W + "/changes", status_code=202, summary="Propose one change per bundle item")
async def create_changes(request: Request, world_model_id: str, body: s.ChangeCreate) -> Response:
    from axelrod_ingest.lake.store import ImportRecord
    from axelrod_wm.api.routes import _importer

    m = model(request, world_model_id, CHANGES)
    rec = bundle_of(request, m, body.bundle_id)
    sub = principal(request).sub
    claims: set = request.app.state.proposing

    def claim() -> bool:
        # under the engine's lock: no update active and no other proposal starting, so two at once cannot both pass
        if m.st.controller.active_update is not None or m.id in claims:
            return False
        claims.add(m.id)
        return True

    async def make() -> Response:
        if not await m.st.call(claim):
            raise ApiError("update_in_progress", "another update is running or waiting for review; decide its "
                                                 "changes first")
        try:
            return await propose_job()
        finally:
            claims.discard(m.id)

    async def propose_job() -> Response:
        async def work() -> dict:
            def run() -> dict:
                ctl = m.st.controller
                runner = _importer(m.st)
                before = {p.id for p in ctl.pending_proposals()}
                preview = runner.preview(rec.bundle)
                late = [x["id"] for x in preview["items"] if x["status"] == "late"
                        and (body.item_ids is None or x["id"] in body.item_ids)]
                version_before = ctl.engine.version
                try:
                    out = runner.import_items(rec.bundle, body.item_ids)
                except ControllerError as err:
                    if "nothing new" not in str(err):
                        raise
                    out = {"update_id": None, "imported": []}
                proposed = sorted(p.id for p in ctl.pending_proposals() if p.id not in before)
                return {"out": out, "late": late, "proposed": proposed, "version_before": version_before}

            r = await m.st.call(run)
            if r["out"]["imported"]:
                lake(request.app).put_import(ImportRecord(
                    tenant=m.org, bundle_id=body.bundle_id, imported_at=datetime.now(UTC),
                    update_id=r["out"]["update_id"], item_ids=r["out"]["imported"], by=sub))
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
            ctl.approve(change_id, by=p.sub, note=note or None)
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
