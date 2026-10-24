"""The lake over HTTP (Oct 24): a `LakeStore` that calls the data service (lake/server.py), so a process that is not the
volume's owner reads and writes the same lake.

Results come back as the same records in the same order, and the exceptions are the store's (`KeyError` for a missing
record, `ValueError` for a bad argument); a failure of the service itself is a `RemoteLakeError`. Vectors travel as float32
bytes, the bytes the store keeps, so a value read back is exactly the value stored, and `nearest` is computed in the
service against its cached matrix.

Reads are retried (three tries, a short fixed pause) on connection errors, timeouts, and 5xx answers. Writes are sent once:
a write whose answer was lost is not known to have happened, and repeating it blindly is the caller's decision. The
store's writes are idempotent (a document's id is its content hash, a put replaces what its key held, a bundle is its
digest), so a caller that retries a write cannot duplicate anything, but a client that retried on its own could hide a
service that is down behind a long wait.

`lake_from_env` is how every process picks its lake: the data service when WORLD_MODEL_LAKE_URL is set, else the SQLite
lake in WORLD_MODEL_LAKE_DIR (default var/lake).
"""

from __future__ import annotations

import base64
import os
import time
from array import array
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

import httpx
from pydantic_core import to_jsonable_python

from axelrod_ingest.lake.sqlite import SQLiteLake
from axelrod_ingest.lake.store import (
    AuditRecord,
    BundleRecord,
    Chunk,
    Document,
    Hit,
    IdempotencyRecord,
    ImportRecord,
    LakeStore,
    Mention,
    WorldModelRecord,
)

TRIES = 3                      # attempts for a read
PAUSE = 0.25                   # seconds between attempts
JSON = {"Content-Type": "application/json"}
TIMEOUT = httpx.Timeout(120.0, connect=10.0)     # a file of tens of MB goes up in one request


class RemoteLakeError(RuntimeError):
    """The data service did not answer, or answered with a failure that is not the store's own."""


def raise_for(resp: httpx.Response) -> None:
    """Re-raise a problem answer as the exception the store would have raised."""
    if resp.status_code < 400:
        return
    try:
        detail = str(resp.json().get("detail", ""))
    except (ValueError, AttributeError):
        detail = resp.text[:200]
    if resp.status_code == 404:
        raise KeyError(detail)
    if resp.status_code == 422:
        raise ValueError(detail)
    raise RemoteLakeError(f"{resp.status_code} from the lake: {detail}")


def is_absent(resp: httpx.Response) -> bool:
    """An answer for a lookup that found nothing (404 with code `absent`), not an error."""
    if resp.status_code != 404:
        return False
    try:
        return resp.json().get("code") == "absent"
    except (ValueError, AttributeError):
        return False


class RemoteLake(LakeStore):
    def __init__(self, url: str, token: str, client: httpx.Client | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.url = url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"}
        self.client = client or httpx.Client(timeout=TIMEOUT)
        self.sleep = sleep

    # -- the wire ---------------------------------------------------------------------------------------------
    def _send(self, method: str, path: str, *, read: bool = False, headers: dict[str, str] | None = None,
              **kw: Any) -> httpx.Response:
        """One call. A read is tried up to TRIES times on a connection error or a 5xx; a write once."""
        def once() -> httpx.Response:
            return self.client.request(method, self.url + "/v1/lake" + path, headers={**self.headers, **(headers or {})}, **kw)

        for _ in range(TRIES - 1 if read else 0):
            try:
                resp = once()
                if resp.status_code < 500:
                    return resp
            except httpx.TransportError:
                pass
            self.sleep(PAUSE)
        try:
            return once()
        except httpx.TransportError as err:
            raise RemoteLakeError(f"the lake did not answer: {type(err).__name__}") from err

    def _call(self, method: str, path: str, *, read: bool = False, **kw: Any) -> Any:
        resp = self._send(method, path, read=read, **kw)
        raise_for(resp)
        return resp.json()

    def _lookup(self, path: str, **params: Any) -> Any | None:
        """A read by key: the JSON answer, or None when nothing is stored under it."""
        resp = self._send("GET", path, read=True, params=params)
        if is_absent(resp):
            return None
        raise_for(resp)
        return resp.json()

    def ping(self) -> bool:
        """Whether the data service answers its health check."""
        try:
            return self.client.get(self.url + "/health", timeout=3.0).status_code == 200
        except httpx.TransportError:
            return False

    # -- documents --------------------------------------------------------------------------------------------
    def put_document(self, doc: Document, data: bytes) -> tuple[Document, bool]:
        body = self._call("POST", "/documents", data={"document": doc.model_dump_json()},
                          files={"data": (doc.filename, data, "application/octet-stream")})
        return Document.model_validate(body["document"]), body["new"]

    def get_document(self, tenant: str, doc_id: str) -> Document | None:
        body = self._lookup(f"/documents/{doc_id}", tenant=tenant)
        return None if body is None else Document.model_validate(body)

    def raw_bytes(self, tenant: str, doc_id: str) -> bytes | None:
        resp = self._send("GET", f"/documents/{doc_id}/raw", read=True, params={"tenant": tenant})
        if is_absent(resp):
            return None
        raise_for(resp)
        return resp.content

    def list_documents(self, tenant: str, *, since: datetime | None = None, until: datetime | None = None,
                       order: str = "event_time", limit: int = 100, offset: int = 0) -> list[Document]:
        params = {"tenant": tenant, "order": order, "limit": limit, "offset": offset,
                  **({"since": since.isoformat()} if since else {}), **({"until": until.isoformat()} if until else {})}
        return [Document.model_validate(d) for d in self._call("GET", "/documents", read=True, params=params)]

    def update_document(self, tenant: str, doc_id: str, **fields: Any) -> Document:
        body = self._call("PATCH", f"/documents/{doc_id}", params={"tenant": tenant},
                          json={"fields": to_jsonable_python(fields)})
        return Document.model_validate(body)

    def delete_document(self, tenant: str, doc_id: str) -> bool:
        return self._call("DELETE", f"/documents/{doc_id}", params={"tenant": tenant})["deleted"]

    # -- text, chunks, mentions, embeddings ------------------------------------------------------------------
    def put_text(self, tenant: str, doc_id: str, text: str, parser: str) -> None:
        self._call("PUT", f"/documents/{doc_id}/text", params={"tenant": tenant}, json={"text": text, "parser": parser})

    def get_text(self, tenant: str, doc_id: str) -> tuple[str, str] | None:
        body = self._lookup(f"/documents/{doc_id}/text", tenant=tenant)
        return None if body is None else (body["text"], body["parser"])

    def put_chunks(self, tenant: str, doc_id: str, chunks: list[Chunk]) -> None:
        self._call("PUT", f"/documents/{doc_id}/chunks", params={"tenant": tenant},
                   json={"chunks": [c.model_dump(mode="json") for c in chunks]})

    def get_chunks(self, tenant: str, doc_id: str) -> list[Chunk]:
        return [Chunk.model_validate(c) for c in
                self._call("GET", f"/documents/{doc_id}/chunks", read=True, params={"tenant": tenant})]

    def put_mentions(self, tenant: str, doc_id: str, mentions: list[Mention]) -> None:
        self._call("PUT", f"/documents/{doc_id}/mentions", params={"tenant": tenant},
                   json={"mentions": [m.model_dump(mode="json") for m in mentions]})

    def mentions_of(self, tenant: str, *, entity_id: str | None = None, subentity_id: str | None = None,
                    doc_id: str | None = None) -> list[Mention]:
        params = {k: v for k, v in (("tenant", tenant), ("entity_id", entity_id), ("subentity_id", subentity_id),
                                    ("doc_id", doc_id)) if v is not None}
        return [Mention.model_validate(m) for m in self._call("GET", "/mentions", read=True, params=params)]

    def put_embeddings(self, tenant: str, doc_id: str, model: str, vectors: list[list[float]]) -> None:
        flat = array("f")
        for v in vectors:
            flat.extend(v)
        self._call("PUT", f"/documents/{doc_id}/embeddings", content=flat.tobytes(),
                   params={"tenant": tenant, "model": model, "dim": len(vectors[0]) if vectors else 1},
                   headers={"Content-Type": "application/octet-stream"})

    def embeddings(self, tenant: str, model: str) -> list[tuple[str, int, list[float]]]:
        body = self._call("GET", "/embeddings", read=True, params={"tenant": tenant, "model": model})
        flat = array("f")
        flat.frombytes(base64.b64decode(body["vectors"]))
        dim = body["dim"]
        return [(d, o, flat[k * dim:(k + 1) * dim].tolist()) for k, (d, o) in enumerate(body["keys"])]

    def nearest(self, tenant: str, model: str, query: list[float], limit: int = 20) -> list[tuple[float, str, int]]:
        rows = self._call("POST", "/nearest", read=True,
                          json={"tenant": tenant, "model": model, "query": list(query), "limit": limit})
        return [(float(s), d, o) for s, d, o in rows]

    # -- search -----------------------------------------------------------------------------------------------
    def keyword_search(self, tenant: str, query: str, *, prefix: bool = False, limit: int = 20) -> list[Hit]:
        rows = self._call("GET", "/search/keyword", read=True,
                          params={"tenant": tenant, "q": query, "prefix": prefix, "limit": limit})
        return [Hit.model_validate(h) for h in rows]

    # -- bundles and imports ----------------------------------------------------------------------------------
    def put_bundle(self, rec: BundleRecord) -> BundleRecord:
        return BundleRecord.model_validate(self._call("PUT", "/bundles", content=rec.model_dump_json(),
                                                      headers=JSON))

    def get_bundle(self, tenant: str, bundle_id: str) -> BundleRecord | None:
        body = self._lookup(f"/bundles/{bundle_id}", tenant=tenant)
        return None if body is None else BundleRecord.model_validate(body)

    def list_bundles(self, tenant: str, *, doc_id: str | None = None, limit: int = 100) -> list[BundleRecord]:
        params = {"tenant": tenant, "limit": limit, **({"doc_id": doc_id} if doc_id is not None else {})}
        return [BundleRecord.model_validate(b) for b in self._call("GET", "/bundles", read=True, params=params)]

    def put_import(self, rec: ImportRecord) -> None:
        self._call("POST", "/imports", content=rec.model_dump_json(), headers=JSON)

    def list_imports(self, tenant: str, *, bundle_id: str | None = None) -> list[ImportRecord]:
        params = {"tenant": tenant, **({"bundle_id": bundle_id} if bundle_id is not None else {})}
        return [ImportRecord.model_validate(i) for i in self._call("GET", "/imports", read=True, params=params)]

    # -- the LLM step's replay cache --------------------------------------------------------------------------
    def cache_get(self, key: str) -> dict | None:
        return self._call("POST", "/cache/get", read=True, json={"key": key})["value"]

    def cache_put(self, key: str, provider: str, model: str, value: dict) -> None:
        self._call("POST", "/cache/put", json={"key": key, "provider": provider, "model": model, "value": value})

    # -- the world model registry and the audit log ----------------------------------------------------------
    def register_world_model(self, rec: WorldModelRecord) -> WorldModelRecord:
        return WorldModelRecord.model_validate(self._call("PUT", "/world-models", content=rec.model_dump_json(),
                                                          headers=JSON))

    def world_models(self, org_id: str | None = None) -> list[WorldModelRecord]:
        params = {} if org_id is None else {"org_id": org_id}
        return [WorldModelRecord.model_validate(w) for w in self._call("GET", "/world-models", read=True, params=params)]

    def put_audit(self, rec: AuditRecord) -> None:
        self._call("POST", "/audit", content=rec.model_dump_json(), headers=JSON)

    def list_audit(self, org: str, world_model_id: str) -> list[AuditRecord]:
        rows = self._call("GET", "/audit", read=True, params={"org": org, "world_model_id": world_model_id})
        return [AuditRecord.model_validate(a) for a in rows]

    # -- idempotency keys and jobs ----------------------------------------------------------------------------
    def get_idempotency(self, org: str, world_model_id: str, operation: str, key: str) -> IdempotencyRecord | None:
        body = self._lookup("/idempotency", org=org, world_model_id=world_model_id, operation=operation, key=key)
        return None if body is None else IdempotencyRecord.model_validate(body)

    def put_idempotency(self, rec: IdempotencyRecord) -> None:
        self._call("PUT", "/idempotency", content=rec.model_dump_json(), headers=JSON)

    def forget_idempotency(self, org: str, world_model_id: str, naming: str) -> int:
        return self._call("POST", "/idempotency/forget",
                          json={"org": org, "world_model_id": world_model_id, "naming": naming})["dropped"]

    def put_job(self, org: str, world_model_id: str, job: dict[str, Any]) -> None:
        self._call("PUT", "/jobs", json={"org": org, "world_model_id": world_model_id, "job": job})

    def get_job(self, org: str, world_model_id: str, job_id: str) -> dict[str, Any] | None:
        return self._lookup("/jobs", org=org, world_model_id=world_model_id, job_id=job_id)

    # -- housekeeping -----------------------------------------------------------------------------------------
    def stats(self, tenant: str) -> dict[str, int]:
        return self._call("GET", "/stats", read=True, params={"tenant": tenant})

    def tenants(self) -> list[str]:
        return self._call("GET", "/tenants", read=True)

    def close(self) -> None:
        self.client.close()


def lake_from_env(env: Mapping[str, str] | None = None) -> LakeStore:
    """The data service when WORLD_MODEL_LAKE_URL is set (with WORLD_MODEL_LAKE_TOKEN), else the SQLite lake in
    WORLD_MODEL_LAKE_DIR (default var/lake)."""
    env = os.environ if env is None else env
    url = (env.get("WORLD_MODEL_LAKE_URL") or "").strip()
    if not url:
        return SQLiteLake(env.get("WORLD_MODEL_LAKE_DIR") or "var/lake")
    token = env.get("WORLD_MODEL_LAKE_TOKEN") or ""
    if not token:
        raise ValueError("WORLD_MODEL_LAKE_URL is set but WORLD_MODEL_LAKE_TOKEN is not")
    return RemoteLake(url, token)


__all__ = ["RemoteLake", "RemoteLakeError", "lake_from_env"]
