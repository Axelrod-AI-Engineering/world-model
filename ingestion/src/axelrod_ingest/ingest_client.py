"""The ingestion service's client (Oct 24): the `Ingestor` methods the world model calls, over HTTP.

`RemoteIngestor` has the surface the routes use (`ingest_many`, `ingest_file`, `process`, and the `inverted` and
`embedder` attributes) and returns `IngestResult`s rebuilt from the service's JSON, equal to what a local `Ingestor` returns.
Its `embedder` is a `RemoteEmbedder`: the service holds the only embedding model, so search queries are embedded there
(`POST /v1/embed`) and the world model never loads weights.
The service raises the pipeline's exceptions (`KeyError`, `ValueError`) as 404 and 422 problems, and they are re-raised
here as the same types; an ingestion that cannot be reached is a `RemoteIngestError`. Nothing is retried: an upload is
a write that can take minutes, and the world model's idempotency keys already make a repeat safe for the caller to send.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

import httpx
from pydantic_core import to_jsonable_python

from axelrod_ingest.contract.world_view import WorldView
from axelrod_ingest.lake.remote import raise_for
from axelrod_ingest.lake.store import canonical_json
from axelrod_ingest.pipeline import IngestResult

TIMEOUT = httpx.Timeout(900.0, connect=10.0)      # a batch of scanned PDFs is read page by page


class RemoteIngestError(RuntimeError):
    """The ingestion service did not answer, or failed."""


class RemoteEmbedder:
    """The `Embedder` interface (name, dim, embed) over the ingestion service. The name and dimension are asked once."""

    def __init__(self, ingestor: RemoteIngestor) -> None:
        self.ingestor = ingestor
        self._about: dict[str, Any] | None = None

    def _ask(self, texts: list[str]) -> dict[str, Any]:
        return self.ingestor._post("/v1/embed", json={"texts": texts})

    @property
    def about(self) -> dict[str, Any]:
        if self._about is None:
            self._about = self._ask([])
        return self._about

    @property
    def name(self) -> str:
        return self.about["name"]

    @property
    def dim(self) -> int:
        return self.about["dim"]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._ask(texts)["vectors"]


class RemoteIngestor:
    def __init__(self, url: str, token: str, client: httpx.Client | None = None) -> None:
        self.url = url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"}
        self.embedder = RemoteEmbedder(self)
        self.inverted: frozenset[str] = frozenset()
        self.client = client or httpx.Client(timeout=TIMEOUT)

    def _post(self, path: str, **kw: Any) -> Any:
        try:
            resp = self.client.post(self.url + path, headers=self.headers, **kw)
        except httpx.TransportError as err:
            raise RemoteIngestError(f"the ingestion service did not answer: {type(err).__name__}") from err
        if resp.status_code >= 500 or resp.status_code in (401, 403):
            raise RemoteIngestError(f"{resp.status_code} from the ingestion service")
        raise_for(resp)
        return resp.json()

    def ingest_many(self, tenant: str, files: list[tuple[bytes, str]], graph: WorldView, **meta: Any) -> list[IngestResult]:
        body = {"tenant": tenant, "inverted": sorted(self.inverted), **to_jsonable_python(meta)}
        parts = [("files", (name, data, "application/octet-stream")) for data, name in files]
        parts.append(("world_view", ("world_view.json", graph.to_json().encode(), "application/json")))
        out = self._post("/v1/ingest", data={"meta": canonical_json(body)}, files=parts)
        return [IngestResult.from_dict(r) for r in out["results"]]

    def ingest_file(self, tenant: str, data: bytes, filename: str, graph: WorldView, **meta: Any) -> IngestResult:
        return self.ingest_many(tenant, [(data, filename)], graph, **meta)[0]

    def process(self, tenant: str, doc_id: str, graph: WorldView) -> IngestResult:
        body = {"tenant": tenant, "doc_id": doc_id, "world_view": graph.to_json(), "inverted": sorted(self.inverted)}
        return IngestResult.from_dict(self._post("/v1/process", json=body)["result"])

    def ping(self) -> bool:
        """Whether the service answers its health check."""
        try:
            return self.client.get(self.url + "/health", timeout=3.0).status_code == 200
        except httpx.TransportError:
            return False


def ingestor_from_env(env: Mapping[str, str] | None = None) -> RemoteIngestor | None:
    """The ingestion service when WORLD_MODEL_INGEST_URL is set (with WORLD_MODEL_INGEST_TOKEN), else None."""
    env = os.environ if env is None else env
    url = (env.get("WORLD_MODEL_INGEST_URL") or "").strip()
    if not url:
        return None
    token = env.get("WORLD_MODEL_INGEST_TOKEN") or ""
    if not token:
        raise ValueError("WORLD_MODEL_INGEST_URL is set but WORLD_MODEL_INGEST_TOKEN is not")
    return RemoteIngestor(url, token)


__all__ = ["RemoteEmbedder", "RemoteIngestError", "RemoteIngestor", "ingestor_from_env"]
