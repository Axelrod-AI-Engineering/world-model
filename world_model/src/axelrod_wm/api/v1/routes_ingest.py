"""v1 ingestion routes (world_model/docs/api/openapi.yaml): documents (upload, read, delete, read again), their passages and
content, the bundles extracted from them (or written by an agent), a bundle's items, and search over the lakehouse and
the model's names. It imports only axelrod_ingest and the v1 plumbing, so it is the part of the service that moves
with ingestion if that is ever served on its own; the world model reaches it only through the world view."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi import Path as FPath
from fastapi.responses import Response

from axelrod_ingest.pipeline import Ingestor, IngestResult
from axelrod_wm.api.tokens import ADMIN, DOCUMENTS, READ
from axelrod_wm.api.v1 import schemas as s
from axelrod_wm.api.v1.context import (
    Cursor,
    Limit,
    Model,
    audit,
    base,
    decode_cursor,
    encode_cursor,
    fingerprint,
    idempotent,
    inverted_surfaces,
    lake,
    many,
    model,
    one,
    page,
    principal,
    run_job,
    view_of,
)
from axelrod_wm.api.v1.context import (
    version_ref as vref,
)
from axelrod_wm.api.v1.problems import ApiError, V1Route

router = APIRouter(prefix="/v1", route_class=V1Route, tags=["v1"])
W = "/world-models/{world_model_id}"
MAX_UPLOAD = 50 * 1024 * 1024
MAX_FILES = 20
SourceType = Literal["broker_research", "expert_call", "news", "central_bank", "data", "filing", "client_model", "other"]


# -- documents ---------------------------------------------------------------------------------------------------------------
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
                return ingestor_for(request, m).ingest_many(m.org, blobs, view_of(m),
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
                                                                           view_of(m)))
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
            m.org, data, f"{body.get('title') or 'bundle'}.json"[:120], view_of(m),
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
                        view_of(m)).search(m.org, q, mode, limit)
        return [s.Hit(kind=h.kind, score=h.score, text=h.text, why=list(h.why), document_id=h.doc_id, ordinal=h.ord,
                      title=h.title, filename=h.filename, event_time=h.event_time, ref=h.ref, entity_id=h.entity_id)
                for h in hits], vref(m.st)

    rows, ref = await m.st.call(run)
    return many(request, rows, limit, None, ref)
