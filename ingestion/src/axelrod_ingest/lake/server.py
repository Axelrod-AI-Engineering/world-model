"""The data service (Oct 24): the lakehouse behind HTTP, so one process owns the SQLite file.

The world model and the ingestion service each reach the lake through `RemoteLake` (lake/remote.py), which calls these
routes on the private network, and both read and write one lake, with organizations as tenants.
There is one route per `LakeStore` method under `/v1/lake`. Records travel as the pydantic records of lake/store.py in JSON;
raw files travel as binary (a multipart file part going up, an octet-stream coming down), embedding vectors as float32
bytes (the same bytes the store keeps), and `nearest` runs here, against the cached matrix, so no vector crosses the
network on a search.

Every route but `GET /health` needs `Authorization: Bearer <LAKE_TOKEN>`, compared in constant time. Failures are RFC 9457
problem bodies (the shape the world model's /v1 uses): a `KeyError` from the store is a 404 (`not_found`), a `ValueError`
a 422 (`invalid_request`), and a lookup that finds nothing is a 404 with code `absent`, so the client can tell "no such
record" from "no such route".

    LAKE_DIR     the volume's folder (default /data/lake)
    LAKE_TOKEN   the shared secret (required: the service refuses to start without it)
    PORT         the port (default 8000)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from array import array
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from axelrod_ingest.lake.store import (
    AuditRecord,
    BundleRecord,
    Chunk,
    Document,
    IdempotencyRecord,
    ImportRecord,
    LakeStore,
    Mention,
    WorldModelRecord,
    content_id,
)

PROBLEM_BASE = "https://docs.axelrod.ai/problems/"
TITLES = {401: "Authentication required", 404: "Not found", 413: "Payload too large", 422: "Invalid request"}
CODES = {401: "authentication_required", 404: "not_found", 413: "payload_too_large", 422: "invalid_request"}
TIMES = ("published_at", "event_time", "ingested_at")      # the Document fields that are datetimes


class Problem(Exception):
    """A failure to answer as an RFC 9457 problem."""

    def __init__(self, status: int, detail: str, code: str | None = None, headers: dict[str, str] | None = None) -> None:
        super().__init__(detail)
        self.status, self.detail, self.code, self.headers = status, detail, code or CODES.get(status, "error"), headers or {}


def problem(status: int, code: str, detail: str, instance: str, headers: dict[str, str] | None = None) -> JSONResponse:
    body = {"type": PROBLEM_BASE + code, "title": TITLES.get(status, "Error"), "status": status, "detail": detail,
            "instance": instance, "code": code}
    return JSONResponse(body, status_code=status, media_type="application/problem+json", headers=headers)


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TextBody(_Body):
    text: str
    parser: str


class ChunksBody(_Body):
    chunks: list[Chunk]


class MentionsBody(_Body):
    mentions: list[Mention]


class NearestBody(_Body):
    tenant: str
    model: str
    query: list[float]
    limit: int = 20


class ChunkCountsBody(_Body):
    tenant: str
    doc_ids: list[str] | None = None


class FieldsBody(_Body):
    fields: dict[str, Any]


class CacheGetBody(_Body):
    key: str


class CachePutBody(_Body):
    key: str
    provider: str
    model: str
    value: dict


class ForgetBody(_Body):
    org: str
    world_model_id: str
    naming: str


class JobBody(_Body):
    org: str
    world_model_id: str
    job: dict[str, Any]


def _when(fields: Mapping[str, Any]) -> dict[str, Any]:
    """A document update's fields, with the datetimes the client sent as ISO strings parsed back."""
    out = dict(fields)
    for k in TIMES:
        if isinstance(out.get(k), str):
            out[k] = datetime.fromisoformat(out[k])
    return out


def _found(value: Any, what: str) -> Any:
    if value is None:
        raise Problem(404, f"no {what}", "absent")
    return value


def create_lake_app(store: LakeStore, token: str) -> FastAPI:
    """The data service over `store`. `token` is the bearer credential every route but /health requires."""
    if not token:
        raise ValueError("a lake token is required")
    app = FastAPI(title="Axelrod Data Service", version="1", docs_url=None, redoc_url=None, openapi_url=None)
    want = token.encode()

    def authorize(request: Request) -> None:
        scheme, _, given = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(given.encode(), want):
            raise Problem(401, "a valid bearer token is required", headers={"WWW-Authenticate": "Bearer"})

    @app.exception_handler(Problem)
    async def _problem(request: Request, exc: Problem) -> JSONResponse:
        return problem(exc.status, exc.code, exc.detail, request.url.path, exc.headers)

    @app.exception_handler(KeyError)
    async def _key(request: Request, exc: KeyError) -> JSONResponse:
        return problem(404, "not_found", str(exc.args[0]) if exc.args else "not found", request.url.path)

    @app.exception_handler(ValueError)
    async def _value(request: Request, exc: ValueError) -> JSONResponse:
        return problem(422, "invalid_request", str(exc), request.url.path)

    @app.exception_handler(RequestValidationError)
    async def _invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        return problem(422, "invalid_request", "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
                                                         for e in exc.errors()), request.url.path)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return problem(exc.status_code, CODES.get(exc.status_code, "error"), str(exc.detail), request.url.path)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "data"}

    r = APIRouter(prefix="/v1/lake", dependencies=[Depends(authorize)])

    # -- documents --------------------------------------------------------------------------------------------
    @r.post("/documents")
    def put_document(document: str = Form(...), data: UploadFile = File(...)) -> dict:
        doc, blob = Document.model_validate_json(document), data.file.read()
        if doc.id != content_id(blob) or doc.sha256 != hashlib.sha256(blob).hexdigest():
            raise ValueError("the document's id and sha256 must be those of its bytes")   # ids name files: never trust one
        doc, new = store.put_document(doc, blob)
        return {"document": doc.model_dump(mode="json"), "new": new}

    @r.get("/documents/{doc_id}")
    def get_document(doc_id: str, tenant: str) -> dict:
        return _found(store.get_document(tenant, doc_id), f"document {doc_id}").model_dump(mode="json")

    @r.get("/documents/{doc_id}/raw")
    def raw_bytes(doc_id: str, tenant: str) -> Response:
        return Response(_found(store.raw_bytes(tenant, doc_id), f"file for {doc_id}"),
                        media_type="application/octet-stream")

    @r.get("/documents")
    def list_documents(tenant: str, since: datetime | None = None, until: datetime | None = None,
                       order: str = "event_time", limit: int = 100, offset: int = 0) -> list[dict]:
        return [d.model_dump(mode="json") for d in store.list_documents(tenant, since=since, until=until, order=order,
                                                                          limit=limit, offset=offset)]

    @r.patch("/documents/{doc_id}")
    def update_document(doc_id: str, tenant: str, body: FieldsBody) -> dict:
        return store.update_document(tenant, doc_id, **_when(body.fields)).model_dump(mode="json")

    @r.delete("/documents/{doc_id}")
    def delete_document(doc_id: str, tenant: str) -> dict:
        return {"deleted": store.delete_document(tenant, doc_id)}

    @r.get("/overview")
    def overview(tenant: str, since: datetime | None = None) -> dict:
        return store.overview(tenant, since=since)

    # -- text, chunks, mentions, embeddings -----------------------------------------------------------------
    @r.put("/documents/{doc_id}/text")
    def put_text(doc_id: str, tenant: str, body: TextBody) -> dict:
        store.put_text(tenant, doc_id, body.text, body.parser)
        return {}

    @r.get("/documents/{doc_id}/text")
    def get_text(doc_id: str, tenant: str) -> dict:
        text, parser = _found(store.get_text(tenant, doc_id), f"text for {doc_id}")
        return {"text": text, "parser": parser}

    @r.put("/documents/{doc_id}/chunks")
    def put_chunks(doc_id: str, tenant: str, body: ChunksBody) -> dict:
        store.put_chunks(tenant, doc_id, body.chunks)
        return {}

    @r.get("/documents/{doc_id}/chunks")
    def get_chunks(doc_id: str, tenant: str) -> list[dict]:
        return [c.model_dump(mode="json") for c in store.get_chunks(tenant, doc_id)]

    @r.post("/chunk-counts")
    def chunk_counts(body: ChunkCountsBody) -> dict:
        return store.count_chunks(body.tenant, body.doc_ids)

    @r.put("/documents/{doc_id}/mentions")
    def put_mentions(doc_id: str, tenant: str, body: MentionsBody) -> dict:
        store.put_mentions(tenant, doc_id, body.mentions)
        return {}

    @r.get("/mentions")
    def mentions_of(tenant: str, entity_id: str | None = None, subentity_id: str | None = None,
                    doc_id: str | None = None) -> list[dict]:
        return [m.model_dump(mode="json") for m in store.mentions_of(tenant, entity_id=entity_id,
                                                                      subentity_id=subentity_id, doc_id=doc_id)]

    @r.put("/documents/{doc_id}/embeddings")
    async def put_embeddings(request: Request, doc_id: str, tenant: str, model: str, dim: int) -> dict:
        """The body is the document's vectors as float32 bytes, row by row; `dim` is the length of a row."""
        flat = array("f")
        flat.frombytes(await request.body())
        if dim < 1 or len(flat) % dim:
            raise ValueError(f"{len(flat)} floats do not divide into rows of {dim}")
        rows = [flat[i:i + dim].tolist() for i in range(0, len(flat), dim)]
        await run_in_threadpool(store.put_embeddings, tenant, doc_id, model, rows)
        return {}

    @r.get("/embeddings")
    def embeddings(tenant: str, model: str) -> dict:
        """{"keys": [[doc id, ordinal], ...], "dim": n, "vectors": base64 of the rows as float32 bytes}."""
        rows = store.embeddings(tenant, model)
        flat = array("f")
        for _doc, _ord, v in rows:
            flat.extend(v)
        return {"keys": [[d, o] for d, o, _v in rows], "dim": len(rows[0][2]) if rows else 0,
                "vectors": base64.b64encode(flat.tobytes()).decode()}

    @r.post("/nearest")
    def nearest(body: NearestBody) -> list[list]:
        return [[s, d, o] for s, d, o in store.nearest(body.tenant, body.model, body.query, body.limit)]

    # -- search -------------------------------------------------------------------------------------------------
    @r.get("/search/keyword")
    def keyword_search(tenant: str, q: str, prefix: bool = False, limit: int = 20) -> list[dict]:
        return [h.model_dump(mode="json") for h in store.keyword_search(tenant, q, prefix=prefix, limit=limit)]

    # -- bundles and imports ------------------------------------------------------------------------------------
    @r.put("/bundles")
    def put_bundle(rec: BundleRecord) -> dict:
        return store.put_bundle(rec).model_dump(mode="json")

    @r.get("/bundles/{bundle_id}")
    def get_bundle(bundle_id: str, tenant: str) -> dict:
        return _found(store.get_bundle(tenant, bundle_id), f"bundle {bundle_id}").model_dump(mode="json")

    @r.get("/bundles")
    def list_bundles(tenant: str, doc_id: str | None = None, limit: int = 100) -> list[dict]:
        return [b.model_dump(mode="json") for b in store.list_bundles(tenant, doc_id=doc_id, limit=limit)]

    @r.delete("/documents/{doc_id}/bundles")
    def delete_bundles_of(doc_id: str, tenant: str) -> dict:
        return {"deleted": store.delete_bundles_of(tenant, doc_id)}

    @r.post("/imports")
    def put_import(rec: ImportRecord) -> dict:
        store.put_import(rec)
        return {}

    @r.get("/imports")
    def list_imports(tenant: str, bundle_id: str | None = None) -> list[dict]:
        return [i.model_dump(mode="json") for i in store.list_imports(tenant, bundle_id=bundle_id)]

    # -- the LLM step's replay cache (a POST for the read: keys are not path-safe) ----------------------------
    @r.post("/cache/get")
    def cache_get(body: CacheGetBody) -> dict:
        return {"value": store.cache_get(body.key)}

    @r.post("/cache/put")
    def cache_put(body: CachePutBody) -> dict:
        store.cache_put(body.key, body.provider, body.model, body.value)
        return {}

    # -- the world model registry and the audit log -----------------------------------------------------------
    @r.put("/world-models")
    def register_world_model(rec: WorldModelRecord) -> dict:
        return store.register_world_model(rec).model_dump(mode="json")

    @r.get("/world-models")
    def world_models(org_id: str | None = None) -> list[dict]:
        return [w.model_dump(mode="json") for w in store.world_models(org_id)]

    @r.post("/audit")
    def put_audit(rec: AuditRecord) -> dict:
        store.put_audit(rec)
        return {}

    @r.get("/audit")
    def list_audit(org: str, world_model_id: str) -> list[dict]:
        return [a.model_dump(mode="json") for a in store.list_audit(org, world_model_id)]

    # -- idempotency keys and jobs ------------------------------------------------------------------------------
    @r.get("/idempotency")
    def get_idempotency(org: str, world_model_id: str, operation: str, key: str) -> dict:
        return _found(store.get_idempotency(org, world_model_id, operation, key), "idempotency key").model_dump(mode="json")

    @r.put("/idempotency")
    def put_idempotency(rec: IdempotencyRecord) -> dict:
        store.put_idempotency(rec)
        return {}

    @r.post("/idempotency/forget")
    def forget_idempotency(body: ForgetBody) -> dict:
        return {"dropped": store.forget_idempotency(body.org, body.world_model_id, body.naming)}

    @r.put("/jobs")
    def put_job(body: JobBody) -> dict:
        store.put_job(body.org, body.world_model_id, body.job)
        return {}

    @r.get("/jobs")
    def get_job(org: str, world_model_id: str, job_id: str) -> dict:
        return _found(store.get_job(org, world_model_id, job_id), f"job {job_id}")

    @r.get("/tenants")
    def tenants() -> list[str]:
        return store.tenants()

    @r.get("/stats")
    def stats(tenant: str) -> dict:
        return store.stats(tenant)

    app.include_router(r)
    return app


def main() -> None:
    """`axelrod-lake`: serve the lake in LAKE_DIR on PORT. Refuses to start without LAKE_TOKEN."""
    import uvicorn

    from axelrod_ingest.lake.sqlite import SQLiteLake

    token = os.environ.get("LAKE_TOKEN", "")
    if not token:
        raise SystemExit("LAKE_TOKEN is required: the data service does not run open")
    app = create_lake_app(SQLiteLake(os.environ.get("LAKE_DIR") or "/data/lake"), token)
    # "" is every address of both families (asyncio opens one IPv4 and one IPv6 socket; "::" alone would be IPv6-only):
    # Railway's private network reaches a service over IPv6, its healthcheck over IPv4
    uvicorn.run(app, host="", port=int(os.environ.get("PORT") or 8000))


__all__ = ["create_lake_app", "main"]
