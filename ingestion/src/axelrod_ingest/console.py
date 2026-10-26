"""The ingestion console (Oct 24): a debugging page on the ingestion service, and the JSON routes behind it.

An internal tool for engineers to understand and debug stages 1 to 5 of ingestion (docs/console.md): what the lake holds,
adding files, searching, and a dry run of the pipeline on one file. The page is a static one (`console/index.html`, `app.js`,
`app.css`, no framework, no build step, no network dependency) at `GET /` and `GET /ui`; it is open, and every JSON route is under
the service's bearer token like the rest of `/v1`.

    GET  /v1/tenants                                  the lake's tenants, and each one's document count
    GET  /v1/supported                                the file extensions and MIME types parse takes, and the source types
    POST /v1/manifest                                 a MANIFEST.md's text: its entries by file name
    GET  /v1/lake/{tenant}/changes                    a version and counts, cheap: what the page polls (`since`: how many are newer)
    GET  /v1/lake/{tenant}/summary                    stats, and documents by status, type, and language (and the version)
    GET  /v1/lake/{tenant}/activity                   the latest ingests, newest first
    GET  /v1/lake/{tenant}/documents                  the table: filters, sort, paging
    GET  /v1/lake/{tenant}/documents/{id}             metadata, text, chunks, counts
    GET  /v1/lake/{tenant}/documents/{id}/raw         the raw file
    DELETE /v1/lake/{tenant}/documents/{id}           the document and what it owns, and its unshared, unimported bundles
    POST /v1/search                                   tenant, q, mode, limit, and an optional world view
    POST /v1/similar                                  tenant, doc_id, ord, limit: passages like a chunk
    POST /v1/debug/stages                             a multipart file and meta, or {tenant, doc_id}: the dry run (debug.py)

It reads the lake: the dry run is `debug.dry_run`, uploading is the existing `POST /v1/ingest`, reprocessing the existing
`POST /v1/process`, and the only write of its own is the delete.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from axelrod_ingest.contract.world_view import WorldView
from axelrod_ingest.debug import dry_run
from axelrod_ingest.lake.embed import Embedder
from axelrod_ingest.lake.search import MODES, Searcher
from axelrod_ingest.lake.server import Problem
from axelrod_ingest.lake.store import Document, LakeStore, digest
from axelrod_ingest.ocr import Ocr
from axelrod_ingest.parse import MIMES, PARSERS
from axelrod_ingest.pipeline import SOURCE_TYPES, upload_date
from axelrod_ingest.sources import read_manifest

PAGE = Path(__file__).parent / "console"
FILES = {"/": ("index.html", "text/html"), "/ui": ("index.html", "text/html"), "/ui/app.js": ("app.js", "text/javascript"),
         "/ui/app.css": ("app.css", "text/css")}
HEADERS = {"Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
                                      "img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
           "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "Cache-Control": "no-store"}
SCAN = 500                    # documents read per call when a filter or a summary needs them all
DIRECTIONS = ("asc", "desc")
ORDERS = ("event_time", "ingested_at")
DRY_RUN = ("clock", "screen", "ignore_future_dates", "timer")      # the Ingestor options a dry run takes too


class SearchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant: str
    q: str
    mode: str = "hybrid"
    limit: int = 20
    world_view: str | None = None


class SimilarBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant: str
    doc_id: str
    ord: int
    limit: int = 10


class ManifestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=1_000_000)     # a manifest is a page of tables; a megabyte is far beyond any real one


class DebugBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant: str
    doc_id: str


class DebugMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant: str = ""
    mime: str = ""
    source_type: str = "other"
    published_at: datetime | None = None
    manifest: dict[str, Any] | None = None


def _all(store: LakeStore, tenant: str, order: str = "ingested_at") -> list[Document]:
    out: list[Document] = []
    while page := store.list_documents(tenant, order=order, limit=SCAN, offset=len(out)):
        out += page
    return out


def _type(d: Document) -> str:
    return d.meta.get("doc_type", {}).get("type", "")


def _language(d: Document) -> str:
    return d.meta.get("language", "")


def _count(docs: list[Document], key: Callable[[Document], str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in docs:
        out[key(d) or "unknown"] = out.get(key(d) or "unknown", 0) + 1
    return dict(sorted(out.items()))


def _rows(store: LakeStore, tenant: str, docs: list[Document]) -> list[dict[str, Any]]:
    counts = store.count_chunks(tenant, [d.id for d in docs]) if docs else {}
    return [_row(d, counts[d.id]) for d in docs]


def _row(d: Document, chunks: int) -> dict[str, Any]:
    dates = d.meta.get("dates", {})
    pages = d.meta.get("pages") or d.meta.get("slides") or len(d.meta.get("sheets") or []) or None
    return {"id": d.id, "filename": d.filename, "title": d.title, "status": d.status, "type": _type(d),
            "language": _language(d), "published_at": d.published_at.isoformat() if d.published_at else None,
            "published_source": dates.get("published_source", ""), "period": dates.get("period", ""),
            "pages": pages if isinstance(pages, int) else None, "chunks": chunks,
            "size": d.size, "event_time": d.event_time.isoformat(), "ingested_at": d.ingested_at.isoformat(),
            "error": d.error}


def _version(store: LakeStore, tenant: str, since: datetime | None = None) -> dict[str, Any]:
    """The cheap facts about a tenant and a version that changes whenever any of them does."""
    ov, stats = store.overview(tenant, since=since), store.stats(tenant)
    return {"version": digest([stats, ov["statuses"], ov["last_ingested_at"]])[:16], "documents": stats["documents"],
            "stats": stats, "statuses": ov["statuses"], "last_ingested_at": ov["last_ingested_at"], "new": ov["new"]}


def mount_console(app: FastAPI, *, store: LakeStore, embedder: Embedder, ocr: Ocr | None, authorize: Callable[..., None],
                  max_bytes: int, **options: Any) -> None:
    """Add the console's page and routes to `app`, which reads `store` and embeds with `embedder`. `authorize` is the
    service's bearer check; `options` are the `Ingestor` options (a dry run takes the ones it shares)."""
    shared = {k: v for k, v in options.items() if k in DRY_RUN}
    cache: dict[str, bytes] = {}

    def page(path: str) -> Response:
        name, kind = FILES[path]
        if name not in cache:
            cache[name] = (PAGE / name).read_bytes()
        return Response(cache[name], media_type=kind, headers=HEADERS)

    for path in FILES:
        app.add_api_route(path, lambda path=path: page(path), methods=["GET"], include_in_schema=False)

    r = APIRouter(prefix="/v1", dependencies=[Depends(authorize)])

    @r.get("/tenants")
    def tenants() -> dict:
        names = store.tenants()
        return {"tenants": names, "documents": {t: sum(store.overview(t)["statuses"].values()) for t in names}}

    @r.get("/supported")
    def supported() -> dict:
        return {"extensions": sorted(PARSERS), "mimes": sorted(MIMES), "source_types": list(SOURCE_TYPES)}

    @r.post("/manifest")
    def manifest(body: ManifestBody) -> dict:
        m = read_manifest(body.text)
        return {"title": m.title, "updated": m.updated,
                "entries": {e.file: {"file": e.file, "url": e.url, "section": e.section, "rank": e.rank,
                                     "sha256": e.sha256, "publisher": e.publisher} for e in m.entries}}

    @r.get("/lake/{tenant}/changes")
    def changes(tenant: str, since: datetime | None = None) -> dict:
        return _version(store, tenant, since)

    @r.get("/lake/{tenant}/activity")
    def activity(tenant: str, limit: int = Query(12, ge=1, le=100)) -> dict:
        total = store.stats(tenant)["documents"]
        n = min(limit, total)
        docs = store.list_documents(tenant, order="ingested_at", limit=n, offset=total - n)[::-1] if n else []
        return {"documents": _rows(store, tenant, docs)}

    @r.get("/lake/{tenant}/summary")
    def summary(tenant: str) -> dict:
        v = _version(store, tenant)
        docs = _all(store, tenant)
        return {"tenant": tenant, "version": v["version"], "last_ingested_at": v["last_ingested_at"], "stats": store.stats(tenant), "embedder": {"name": embedder.name, "dim": embedder.dim},
                "by_status": _count(docs, lambda d: d.status), "by_type": _count(docs, _type),
                "by_language": _count(docs, _language)}

    @r.get("/lake/{tenant}/documents")
    def documents(tenant: str, status: str = "", type: str = "", language: str = "", q: str = "",
                  order: str = "event_time", dir: str = "desc", limit: int = Query(50, ge=1, le=SCAN),
                  offset: int = Query(0, ge=0)) -> dict:
        if dir not in DIRECTIONS:
            raise ValueError(f"dir must be one of {', '.join(DIRECTIONS)}")
        if order not in ORDERS:
            raise ValueError(f"order must be one of {', '.join(ORDERS)}")
        if not (status or type or language or q):
            # no filter: the store pages it (newest first is the end of the ascending order, read backwards)
            total = store.stats(tenant)["documents"]
            if dir == "asc":
                page_ = store.list_documents(tenant, order=order, limit=limit, offset=offset)
            else:
                n = max(0, min(limit, total - offset))
                page_ = store.list_documents(tenant, order=order, limit=n, offset=total - offset - n)[::-1] if n else []
        else:
            want = q.lower()
            docs = [d for d in _all(store, tenant, order)
                    if (not status or d.status == status) and (not type or _type(d) == type)
                    and (not language or _language(d) == language)
                    and (not want or want in d.filename.lower() or want in d.title.lower())]
            docs = docs if dir == "asc" else docs[::-1]
            total, page_ = len(docs), docs[offset:offset + limit]
        return {"total": total, "limit": limit, "offset": offset, "documents": _rows(store, tenant, page_)}

    @r.get("/lake/{tenant}/documents/{doc_id}")
    def document(tenant: str, doc_id: str) -> dict:
        doc = store.get_document(tenant, doc_id)
        if doc is None:
            raise KeyError(f"no document {doc_id}")
        text, parser = store.get_text(tenant, doc_id) or ("", "")
        bundles = store.list_bundles(tenant, doc_id=doc_id)
        return {"document": doc.model_dump(mode="json"), "text": text, "parser": parser,
                "chunks": [c.model_dump(mode="json") for c in store.get_chunks(tenant, doc_id)],
                "mentions": len(store.mentions_of(tenant, doc_id=doc_id)),
                "bundles": [{"id": b.id, "items": b.items, "signals": b.signals} for b in bundles],
                "signals": sum(b.signals for b in bundles)}

    @r.delete("/lake/{tenant}/documents/{doc_id}")
    def delete(tenant: str, doc_id: str) -> dict:
        if store.get_document(tenant, doc_id) is None:
            raise KeyError(f"no document {doc_id}")
        store.delete_document(tenant, doc_id)
        removed = store.delete_bundles_of(tenant, doc_id)
        return {"deleted": True, "bundles_removed": removed,
                "bundles_kept": len(store.list_bundles(tenant, doc_id=doc_id, limit=1000))}

    @r.get("/lake/{tenant}/documents/{doc_id}/raw")
    def raw(tenant: str, doc_id: str) -> Response:
        doc, data = store.get_document(tenant, doc_id), store.raw_bytes(tenant, doc_id)
        if doc is None or data is None:
            raise KeyError(f"no file for {doc_id}")
        return Response(data, media_type="application/octet-stream",
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(doc.filename)}"})

    @r.post("/search")
    def search(body: SearchBody) -> dict:
        if not 1 <= body.limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        if body.mode not in MODES:
            raise ValueError(f"mode must be one of {', '.join(MODES)}")
        if body.mode == "graph" and body.world_view is None:
            raise ValueError("graph search needs a world view")
        graph = None if body.world_view is None else WorldView.from_json(body.world_view)
        hits = Searcher(store, embedder, graph).search(body.tenant, body.q, body.mode, body.limit)
        return {"mode": body.mode, "hits": [_hit(store, body.tenant, h.model_dump(mode="json")) for h in hits]}

    @r.post("/similar")
    def similar(body: SimilarBody) -> dict:
        if not 1 <= body.limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        chunk = next((c for c in store.get_chunks(body.tenant, body.doc_id) if c.ord == body.ord), None)
        if chunk is None:
            raise KeyError(f"no chunk {body.ord} of {body.doc_id}")
        # the chunk's own vector: its text embedded again (the embedder is deterministic), so no matrix leaves the lake
        near = store.nearest(body.tenant, embedder.name, embedder.embed([chunk.text])[0], body.limit + 1)
        hits = [(s, d, o) for s, d, o in near if (d, o) != (body.doc_id, body.ord)][:body.limit]
        return {"hits": [_hit(store, body.tenant, {"kind": "chunk", "doc_id": d, "ord": o, "score": s, "why": ["similar"]})
                         for s, d, o in hits]}

    @r.post("/debug/stages")
    async def debug_stages(request: Request) -> Response:
        if request.headers.get("content-type", "").startswith("application/json"):
            body = DebugBody.model_validate(await request.json())
            doc = store.get_document(body.tenant, body.doc_id)
            data = store.raw_bytes(body.tenant, body.doc_id)
            if doc is None or data is None:
                raise KeyError(f"no document {body.doc_id}")
            args: dict[str, Any] = {"filename": doc.filename, "mime": doc.mime, "published_at": upload_date(doc),
                                    "manifest": doc.meta.get("manifest") or {}, "tenant": body.tenant,
                                    "source_type": doc.source_type, "ingested_at": doc.ingested_at,
                                    "issuer": (doc.meta.get("hints") or {}).get("issuer_country")}
        else:
            form = await request.form()
            file, meta = form.get("file"), form.get("meta")
            if file is None or not hasattr(file, "read") or not isinstance(meta, str):
                raise ValueError("a file and meta (JSON) are required")
            m = DebugMeta.model_validate_json(meta)
            if m.source_type not in SOURCE_TYPES:
                raise ValueError(f"source_type must be one of {', '.join(SOURCE_TYPES)}")
            data = await file.read()
            args = {"filename": file.filename or "upload.bin", "mime": m.mime, "published_at": m.published_at,
                    "manifest": m.manifest, "tenant": m.tenant, "source_type": m.source_type}
        if len(data) > max_bytes:
            raise Problem(413, f"the file is {len(data)} bytes; the limit is {max_bytes}")
        res = await run_in_threadpool(lambda: dry_run(data, ocr=ocr, embedder=embedder, store=store, **args, **shared))
        return Response(json.dumps(res, ensure_ascii=False, default=str), media_type="application/json")

    app.include_router(r)


def _hit(store: LakeStore, tenant: str, hit: dict[str, Any]) -> dict[str, Any]:
    """A hit with what the table needs of its chunk and document: the text (a similar passage has none yet), page, title."""
    if hit["kind"] != "chunk":
        return hit
    doc = store.get_document(tenant, hit["doc_id"])
    chunk = next((c for c in store.get_chunks(tenant, hit["doc_id"]) if c.ord == hit["ord"]), None)
    if doc is None or chunk is None:
        return hit                                  # a stale index entry: what the search gave, no more
    return {**hit, "page": chunk.page, "section": chunk.section, "text": chunk.text, "title": doc.title or doc.filename,
            "filename": doc.filename, "event_time": doc.event_time.isoformat()}


__all__ = ["mount_console"]
