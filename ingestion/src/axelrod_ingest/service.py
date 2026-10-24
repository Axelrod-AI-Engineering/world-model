"""The ingestion service (Oct 24): the pipeline behind HTTP, so uploads are parsed, embedded, and extracted off the world
model's process.

It holds no state. The lake it reads and writes is whatever `store` is (the data service, through `RemoteLake`, when
deployed); the world model sends the files and a `WorldView` of its model, and gets `IngestResult`s back as JSON, in the
order `ingest_many` returns them (`ingest_client.RemoteIngestor` is the caller). The view is sent as a file part, not a
form field, because it can be hundreds of KB and form fields are capped. This service holds the only embedding model: the world
model embeds its search queries here (`/v1/embed`), so the two can never disagree on the embedder. It writes no file
bytes to disk (a document is held in memory while it is processed) and keeps its OCR page cache in temporary storage.

    POST /v1/ingest    multipart: `files`, `world_view` (WorldView.to_json), `meta` (JSON: tenant, inverted, source,
                       source_type, published_at, uploaded_by, mime, meta)
    POST /v1/process   JSON: tenant, doc_id, world_view, inverted (a stored document read again)
    POST /v1/embed     JSON: texts; answers name, dim, and the vectors as exact JSON floats (no texts: just name and dim)
    GET  /health

Every route but /health needs `Authorization: Bearer <INGEST_TOKEN>`; failures are RFC 9457 problems (a `KeyError` is a
404, a `ValueError` a 422), like the data service's.

    INGEST_TOKEN   the shared secret (required)
    PORT           the port (default 8000)
    WORLD_MODEL_LAKE_URL / WORLD_MODEL_LAKE_TOKEN   the data service (else a local lake in WORLD_MODEL_LAKE_DIR)
    WORLD_MODEL_EMBEDDER, WORLD_MODEL_LLM_PROVIDER, ...   as everywhere
"""

from __future__ import annotations

import hmac
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

from axelrod_ingest.contract.world_view import WorldView
from axelrod_ingest.lake.embed import Embedder
from axelrod_ingest.lake.server import Problem, problem
from axelrod_ingest.lake.store import LakeStore, canonical_json
from axelrod_ingest.llm import Provider
from axelrod_ingest.ocr import Ocr
from axelrod_ingest.pipeline import Ingestor


class IngestMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant: str
    inverted: list[str] = []
    mime: str = ""
    source: str = ""
    source_type: str = "other"
    published_at: datetime | None = None
    uploaded_by: str = ""
    meta: dict[str, Any] | None = None


class EmbedBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texts: list[str]


class ProcessBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant: str
    doc_id: str
    world_view: str
    inverted: list[str] = []


def create_ingest_app(store: LakeStore, embedder: Embedder, provider: Provider | None, ocr: Ocr | None, token: str,
                      **ingestor: Any) -> FastAPI:
    """The ingestion service over `store`. `ingestor` passes the rest of `Ingestor`'s options (clock, screen, ...)."""
    if not token:
        raise ValueError("an ingestion token is required")
    app = FastAPI(title="Axelrod Ingestion Service", version="1", docs_url=None, redoc_url=None, openapi_url=None)
    want = token.encode()

    def authorize(request: Request) -> None:
        scheme, _, given = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(given.encode(), want):
            raise Problem(401, "a valid bearer token is required", headers={"WWW-Authenticate": "Bearer"})

    def ingestor_for(inverted: list[str]) -> Ingestor:
        # one per request: `inverted` belongs to the caller's model, so a shared instance would carry it between callers
        return Ingestor(store, embedder, provider=provider, ocr=ocr, inverted=frozenset(inverted), **ingestor)

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
        return problem(exc.status_code, "not_found" if exc.status_code == 404 else "error", str(exc.detail),
                       request.url.path)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "ingestion"}

    @app.post("/v1/ingest", dependencies=[Depends(authorize)])
    def ingest(meta: str = Form(...), world_view: UploadFile = File(...), files: list[UploadFile] = File(...)) -> Response:
        m = IngestMeta.model_validate_json(meta)
        graph = WorldView.from_json(world_view.file.read().decode())
        extra = {k: v for k, v in m.model_dump().items() if k not in ("tenant", "inverted")}
        results = ingestor_for(m.inverted).ingest_many(
            m.tenant, [(f.file.read(), f.filename or "upload.bin") for f in files], graph, **extra)
        return _json({"results": [r.to_dict() for r in results]})

    @app.post("/v1/process", dependencies=[Depends(authorize)])
    def process(body: ProcessBody) -> Response:
        res = ingestor_for(body.inverted).process(body.tenant, body.doc_id, WorldView.from_json(body.world_view))
        return _json({"result": res.to_dict()})

    @app.post("/v1/embed", dependencies=[Depends(authorize)])
    def embed(body: EmbedBody) -> dict:
        return {"name": embedder.name, "dim": embedder.dim, "vectors": embedder.embed(body.texts) if body.texts else []}

    return app


def _json(body: dict) -> Response:
    return Response(canonical_json(body), media_type="application/json")


def main() -> None:
    """`axelrod-ingest`: serve the pipeline on PORT. Refuses to start without INGEST_TOKEN."""
    import uvicorn

    from axelrod_ingest.lake.embed import LazyEmbedder
    from axelrod_ingest.lake.remote import lake_from_env
    from axelrod_ingest.llm import provider_from_env
    from axelrod_ingest.ocr import ocr_from_env

    token = os.environ.get("INGEST_TOKEN", "")
    if not token:
        raise SystemExit("INGEST_TOKEN is required: the ingestion service does not run open")
    # OCR's page cache is a cache keyed by content, so it lives in temporary storage, not on any volume
    env = {**os.environ}
    env.setdefault("AXELROD_OCR_CACHE", str(Path(tempfile.gettempdir()) / "axelrod-ocr"))
    app = create_ingest_app(lake_from_env(env), LazyEmbedder(env), provider_from_env(env), ocr_from_env(env), token)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT") or 8000))


__all__ = ["create_ingest_app", "main"]
