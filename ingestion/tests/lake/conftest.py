"""Shared helpers for the lakehouse tests: documents built from bytes, and a fresh SQLite lake per test."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from axelrod_ingest.lake.sqlite import SQLiteLake
from axelrod_ingest.lake.store import Chunk, Document, content_id

T0 = datetime(2026, 3, 1, tzinfo=UTC)


def make_doc(data: bytes, *, tenant: str = "acme", filename: str = "note.txt", event_time: datetime = T0,
             ingested_at: datetime = T0, **kw) -> Document:
    return Document(tenant=tenant, id=content_id(data), sha256=hashlib.sha256(data).hexdigest(), filename=filename,
                    mime="text/plain", size=len(data), event_time=event_time, ingested_at=ingested_at, **kw)


def make_chunks(tenant: str, doc_id: str, texts: list[str]) -> list[Chunk]:
    out, pos = [], 0
    for k, t in enumerate(texts):
        out.append(Chunk(tenant=tenant, doc_id=doc_id, ord=k, start=pos, end=pos + len(t), text=t))
        pos += len(t) + 1
    return out


def add_doc(lake: SQLiteLake, data: bytes, texts: list[str], **kw) -> Document:
    """Store a document whose text is `texts` joined, chunked one text per chunk."""
    doc, _new = lake.put_document(make_doc(data, **kw), data)
    lake.put_text(doc.tenant, doc.id, "\n".join(texts), "plain")
    lake.put_chunks(doc.tenant, doc.id, make_chunks(doc.tenant, doc.id, texts))
    return doc


@pytest.fixture
def lake(tmp_path):
    store = SQLiteLake(tmp_path / "lk")
    yield store
    store.close()
