"""The lakehouse's records and its storage interface (Oct 17).

Ids are derived from content, so the same bytes always get the same document id and uploading a file twice stores it
once. Times are UTC: `ingested_at` is when the lake received a document, `event_time` when what it reports happened
(the document's date, or its items' dates). Records are frozen pydantic models; the store returns them sorted, so
every read is deterministic.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_TENANT = "default"


def content_id(data: bytes) -> str:
    """A document's id: the first 24 hex digits of its SHA-256 (collisions are not a practical concern)."""
    return hashlib.sha256(data).hexdigest()[:24]


def canonical_json(obj: Any) -> str:
    """JSON with sorted keys and no extra whitespace: the same object always serializes to the same bytes."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()


class _R(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Document(_R):
    tenant: str
    id: str                                   # content_id of the raw bytes
    sha256: str
    filename: str
    mime: str
    size: int
    source: str = ""                          # who or what produced it (a broker, a feed, an analyst)
    source_type: str = "other"                # the import schema's source types (broker_research, news, ...)
    title: str = ""
    published_at: datetime | None = None      # the document's own date, when known
    event_time: datetime                      # when what it reports happened (published_at, else ingested_at)
    ingested_at: datetime                     # when the lake received it
    uploaded_by: str = ""                     # the API caller or login that uploaded it
    meta: dict[str, Any] = Field(default_factory=dict)
    status: str = "stored"                    # stored -> parsed -> extracted -> imported (or failed)
    error: str = ""


class Chunk(_R):
    tenant: str
    doc_id: str
    ord: int                                  # its position in the document
    start: int                                # character span in the document's text
    end: int
    text: str
    page: int | None = None                   # the page or sheet it came from, when the format has them
    section: str = ""


class Mention(_R):
    tenant: str
    doc_id: str
    ord: int
    entity_id: str
    subentity_id: str | None = None
    surface: str                              # the words that named it


class BundleRecord(_R):
    tenant: str
    id: str                                   # digest of the bundle's canonical JSON
    doc_ids: list[str]
    created_at: datetime
    extractor_version: str
    items: int
    signals: int
    bundle: dict[str, Any]


class ImportRecord(_R):
    tenant: str
    bundle_id: str
    imported_at: datetime
    update_id: str | None
    item_ids: list[str]
    by: str = ""


class WorldModelRecord(_R):
    """One world model and the organization that owns it (Oct 18: the registry; world_model/docs/design/core-mcp-auth.md)."""

    id: str
    org_id: str
    name: str
    created_at: datetime


class AuditRecord(_R):
    """One write to a world model: who (a structured actor), when, what, and the answer's status. Append-only."""

    org: str
    id: str
    at: datetime
    request_id: str
    world_model_id: str
    method: str
    route: str
    status: int
    actor: dict[str, Any]
    scopes: list[str]
    resource_ids: list[str]


class IdempotencyRecord(_R):
    """The first answer to a create, kept forever (Oct 19, with Manav: storage is negligible, determinism first): per
    organization, world model, operation, and key (a client's Idempotency-Key, or `content:<sha256>` for documents and
    bundles). The fingerprint is the request's; another request under the key is refused."""

    org: str
    world_model_id: str
    operation: str
    key: str
    fingerprint: str
    status: int
    body: str
    headers: dict[str, str]
    created_at: datetime


class Hit(_R):
    """One search result: a chunk (or an entity, for graph search) with its score and why it matched."""

    kind: str                                 # chunk | entity | attribute
    doc_id: str | None = None
    ord: int | None = None
    ref: str | None = None                    # entity or attribute id, for name and graph hits
    entity_id: str | None = None              # the entity a name or graph hit is (or belongs to)
    score: float
    text: str
    title: str = ""
    filename: str = ""
    event_time: datetime | None = None
    why: list[str] = []


CHANNELS = ("keyword", "semantic", "graph")
RRF_K = 60                                    # reciprocal-rank fusion: 1 / (RRF_K + rank)
MAX_DEPTH = 1000                              # the deepest a retrieval pages: offset + limit


class RetrievalFilter(_R):
    """Which documents a retrieval reads. Every condition given holds; a list holds when any of its values does."""

    document_ids: list[str] = []
    source_types: list[str] = []
    sources: list[str] = []                   # the document's `source`, ignoring case
    published_from: datetime | None = None    # on event_time (the document's date, else when it was ingested)
    published_to: datetime | None = None      # exclusive
    entity_ids: list[str] = []                # documents with a passage that names one of these entities


class RetrievalSpec(_R):
    """One retrieval: the query, what it was resolved to (its embedding, the names it holds), the filter, and the page."""

    query: str
    channels: list[str] = list(CHANNELS)
    vector: list[float] | None = None         # the query's embedding, for the semantic channel
    model: str = ""                           # the embedder that made it
    entity_ids: list[str] = []                # the entities the query names, for the graph channel
    attribute_ids: list[str] = []             # ... and the attributes
    filter: RetrievalFilter = RetrievalFilter()
    offset: int = Field(0, ge=0)
    limit: int = Field(10, ge=1)
    context: int = Field(0, ge=0, le=3)       # neighbouring passages returned on each side
    per_document: int = Field(0, ge=0)        # at most this many passages from one document (0: no cap)


class Passage(_R):
    """A retrieved chunk with its document, the names in it, its neighbours, and how each channel ranked it."""

    chunk: Chunk
    document: Document
    score: float                              # reciprocal-rank fusion of the channels that found it
    scores: dict[str, float]                  # each channel's own score: BM25, cosine, share of the top mention count
    why: list[str]
    mentions: list[Mention] = []
    before: list[Chunk] = []                  # up to `context` chunks before it, in order
    after: list[Chunk] = []


class Retrieval(_R):
    passages: list[Passage]
    more: bool                                # whether a further page holds passages


class LakeStore(ABC):
    """Storage for the lakehouse. Every method takes the tenant; nothing reads across tenants."""

    # -- documents --------------------------------------------------------------------------------------------
    @abstractmethod
    def put_document(self, doc: Document, data: bytes) -> tuple[Document, bool]:
        """Store a document and its bytes; returns the stored record and whether it was new (same bytes: not new)."""

    @abstractmethod
    def get_document(self, tenant: str, doc_id: str) -> Document | None: ...

    @abstractmethod
    def raw_bytes(self, tenant: str, doc_id: str) -> bytes | None: ...

    @abstractmethod
    def list_documents(self, tenant: str, *, since: datetime | None = None, until: datetime | None = None,
                       order: str = "event_time", limit: int = 100, offset: int = 0) -> list[Document]: ...

    @abstractmethod
    def update_document(self, tenant: str, doc_id: str, **fields: Any) -> Document: ...

    @abstractmethod
    def delete_document(self, tenant: str, doc_id: str) -> bool: ...

    @abstractmethod
    def overview(self, tenant: str, *, since: datetime | None = None) -> dict[str, Any]:
        """What changes when documents arrive or are processed, in one cheap read (no document is loaded):
        `statuses` (document count by status), `last_ingested_at` (ISO time of the newest document, or None) and `new`
        (documents ingested after `since`, 0 without it). The console polls this to know whether to read more."""

    # -- text, chunks, mentions, embeddings ------------------------------------------------------------------
    @abstractmethod
    def put_text(self, tenant: str, doc_id: str, text: str, parser: str) -> None: ...

    @abstractmethod
    def get_text(self, tenant: str, doc_id: str) -> tuple[str, str] | None:
        """(text, parser) for a parsed document."""

    @abstractmethod
    def put_chunks(self, tenant: str, doc_id: str, chunks: list[Chunk]) -> None:
        """Replace the document's chunks (and their keyword index)."""

    @abstractmethod
    def get_chunks(self, tenant: str, doc_id: str) -> list[Chunk]: ...

    @abstractmethod
    def count_chunks(self, tenant: str, doc_ids: list[str] | None = None) -> dict[str, int]:
        """Chunks per document in one read: for `doc_ids`, every id (0 when it has none); for None, every document that has
        any."""

    @abstractmethod
    def put_mentions(self, tenant: str, doc_id: str, mentions: list[Mention]) -> None: ...

    @abstractmethod
    def mentions_of(self, tenant: str, *, entity_id: str | None = None, subentity_id: str | None = None,
                    doc_id: str | None = None) -> list[Mention]: ...

    @abstractmethod
    def put_embeddings(self, tenant: str, doc_id: str, model: str, vectors: list[list[float]]) -> None: ...

    @abstractmethod
    def embeddings(self, tenant: str, model: str) -> list[tuple[str, int, list[float]]]: ...

    @abstractmethod
    def nearest(self, tenant: str, model: str, query: list[float], limit: int = 20) -> list[tuple[float, str, int]]:
        """The chunks whose embeddings are closest to `query` by cosine similarity, exactly (every chunk is scored):
        (score rounded to 6 decimals, doc id, ordinal), best first, ties by document then position."""

    # -- search -----------------------------------------------------------------------------------------------
    @abstractmethod
    def keyword_search(self, tenant: str, query: str, *, prefix: bool = False, limit: int = 20) -> list[Hit]: ...

    @abstractmethod
    def retrieve(self, tenant: str, spec: RetrievalSpec) -> Retrieval:
        """Ranked passages, in one call: each channel in `spec.channels` ranks the chunks of the documents `spec.filter`
        admits, the ranks are fused (reciprocal rank, ties by document then position), `per_document` caps each
        document, and the page at `offset` comes back with its documents, mentions, and neighbours. The same spec over the
        same data always returns the same page. `offset + limit` may not exceed MAX_DEPTH."""

    # -- bundles and imports ----------------------------------------------------------------------------------
    @abstractmethod
    def put_bundle(self, rec: BundleRecord) -> BundleRecord: ...

    @abstractmethod
    def get_bundle(self, tenant: str, bundle_id: str) -> BundleRecord | None: ...

    @abstractmethod
    def list_bundles(self, tenant: str, *, doc_id: str | None = None, limit: int = 100) -> list[BundleRecord]: ...

    @abstractmethod
    def delete_bundles_of(self, tenant: str, doc_id: str) -> int:
        """Delete the bundles made from `doc_id` alone that no import used; how many were deleted. A bundle built from
        several documents, or one the world model imported, is kept: others depend on it."""

    @abstractmethod
    def put_import(self, rec: ImportRecord) -> None: ...

    @abstractmethod
    def list_imports(self, tenant: str, *, bundle_id: str | None = None) -> list[ImportRecord]: ...

    # -- the LLM step's replay cache --------------------------------------------------------------------------
    @abstractmethod
    def cache_get(self, key: str) -> dict | None: ...

    @abstractmethod
    def cache_put(self, key: str, provider: str, model: str, value: dict) -> None: ...

    # -- the world model registry and the audit log (Oct 18) ----------------------------------------------
    @abstractmethod
    def register_world_model(self, rec: WorldModelRecord) -> WorldModelRecord:
        """Record a world model and its owner (the deployment's configuration decides it); one registered before
        keeps its created_at. Returns the record as stored."""

    @abstractmethod
    def world_models(self, org_id: str | None = None) -> list[WorldModelRecord]: ...

    @abstractmethod
    def put_audit(self, rec: AuditRecord) -> None: ...

    @abstractmethod
    def list_audit(self, org: str, world_model_id: str) -> list[AuditRecord]:
        """Newest first."""

    # -- idempotency keys and jobs (Oct 19): kept forever ------------------------------------------------------
    @abstractmethod
    def get_idempotency(self, org: str, world_model_id: str, operation: str, key: str) -> IdempotencyRecord | None: ...

    @abstractmethod
    def put_idempotency(self, rec: IdempotencyRecord) -> None:
        """Keep the first answer under its key; a later one under the same key is ignored."""

    @abstractmethod
    def forget_idempotency(self, org: str, world_model_id: str, naming: str) -> int:
        """Drop the kept answers that name `naming` (a deleted document's id); how many were dropped. The only removal:
        keys otherwise never expire."""

    @abstractmethod
    def put_job(self, org: str, world_model_id: str, job: dict[str, Any]) -> None:
        """Record a job (by its `id`), replacing what was recorded for it."""

    @abstractmethod
    def get_job(self, org: str, world_model_id: str, job_id: str) -> dict[str, Any] | None: ...

    # -- housekeeping -----------------------------------------------------------------------------------------
    @abstractmethod
    def stats(self, tenant: str) -> dict[str, int]: ...

    @abstractmethod
    def tenants(self) -> list[str]:
        """The tenants that hold at least one document, sorted."""

    @abstractmethod
    def close(self) -> None: ...
