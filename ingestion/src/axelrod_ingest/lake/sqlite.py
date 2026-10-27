"""The lakehouse on SQLite (Oct 17): one database file and a folder of raw files, on the volume; no other service.

Keyword search uses SQLite's FTS5 with Porter stemming; prefix search a second, unstemmed FTS5 index (a stemmed index
holds "oper" for "operating", so the prefix "opera" would miss it); embeddings are stored as float32 blobs
and compared exactly, as one matrix product per query over a tenant's vectors (NumPy), held in memory until that
tenant's embeddings change or another connection commits to the file (`PRAGMA data_version`). A lock serializes writers, so the API's worker threads can share one store. Every query has
an explicit ORDER BY, so reads are deterministic.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
from array import array
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from axelrod_ingest.lake.store import (
    CHANNELS,
    MAX_DEPTH,
    RRF_K,
    AuditRecord,
    BundleRecord,
    Chunk,
    Document,
    Hit,
    IdempotencyRecord,
    ImportRecord,
    LakeStore,
    Mention,
    Passage,
    Retrieval,
    RetrievalFilter,
    RetrievalSpec,
    WorldModelRecord,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  tenant TEXT NOT NULL, id TEXT NOT NULL, sha256 TEXT NOT NULL, filename TEXT NOT NULL, mime TEXT NOT NULL,
  size INTEGER NOT NULL, source TEXT NOT NULL, source_type TEXT NOT NULL, title TEXT NOT NULL, published_at TEXT,
  event_time TEXT NOT NULL, ingested_at TEXT NOT NULL, uploaded_by TEXT NOT NULL, meta TEXT NOT NULL,
  status TEXT NOT NULL, error TEXT NOT NULL, PRIMARY KEY (tenant, id));
CREATE INDEX IF NOT EXISTS documents_event ON documents (tenant, event_time);
CREATE INDEX IF NOT EXISTS documents_ingested ON documents (tenant, ingested_at);
CREATE TABLE IF NOT EXISTS texts (
  tenant TEXT NOT NULL, doc_id TEXT NOT NULL, parser TEXT NOT NULL, text TEXT NOT NULL, PRIMARY KEY (tenant, doc_id));
CREATE TABLE IF NOT EXISTS chunks (
  tenant TEXT NOT NULL, doc_id TEXT NOT NULL, ord INTEGER NOT NULL, start INTEGER NOT NULL, "end" INTEGER NOT NULL,
  text TEXT NOT NULL, page INTEGER, section TEXT NOT NULL, PRIMARY KEY (tenant, doc_id, ord));
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  text, tenant UNINDEXED, doc_id UNINDEXED, ord UNINDEXED, tokenize='porter unicode61 remove_diacritics 2',
  prefix='2 3 4');
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_prefix USING fts5(
  text, tenant UNINDEXED, doc_id UNINDEXED, ord UNINDEXED, tokenize='unicode61 remove_diacritics 2', prefix='2 3 4');
CREATE TABLE IF NOT EXISTS mentions (
  tenant TEXT NOT NULL, doc_id TEXT NOT NULL, ord INTEGER NOT NULL, entity_id TEXT NOT NULL, subentity_id TEXT,
  surface TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS mentions_entity ON mentions (tenant, entity_id);
CREATE INDEX IF NOT EXISTS mentions_doc ON mentions (tenant, doc_id);
CREATE TABLE IF NOT EXISTS embeddings (
  tenant TEXT NOT NULL, doc_id TEXT NOT NULL, ord INTEGER NOT NULL, model TEXT NOT NULL, vec BLOB NOT NULL,
  PRIMARY KEY (tenant, doc_id, ord, model));
CREATE TABLE IF NOT EXISTS bundles (
  tenant TEXT NOT NULL, id TEXT NOT NULL, doc_ids TEXT NOT NULL, created_at TEXT NOT NULL,
  extractor_version TEXT NOT NULL, items INTEGER NOT NULL, signals INTEGER NOT NULL, bundle TEXT NOT NULL,
  PRIMARY KEY (tenant, id));
CREATE TABLE IF NOT EXISTS imports (
  tenant TEXT NOT NULL, bundle_id TEXT NOT NULL, imported_at TEXT NOT NULL, update_id TEXT, item_ids TEXT NOT NULL,
  by TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS world_models (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, name TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_events (
  org TEXT NOT NULL, id TEXT NOT NULL, at TEXT NOT NULL, request_id TEXT NOT NULL, world_model_id TEXT NOT NULL,
  method TEXT NOT NULL, route TEXT NOT NULL, status INTEGER NOT NULL, actor TEXT NOT NULL, scopes TEXT NOT NULL,
  resource_ids TEXT NOT NULL, PRIMARY KEY (org, id));
CREATE TABLE IF NOT EXISTS idempotency_keys (
  org TEXT NOT NULL, world_model_id TEXT NOT NULL, operation TEXT NOT NULL, key TEXT NOT NULL,
  fingerprint TEXT NOT NULL, status INTEGER NOT NULL, body TEXT NOT NULL, headers TEXT NOT NULL,
  created_at TEXT NOT NULL, PRIMARY KEY (org, world_model_id, operation, key));
CREATE TABLE IF NOT EXISTS jobs (
  org TEXT NOT NULL, world_model_id TEXT NOT NULL, id TEXT NOT NULL, job TEXT NOT NULL,
  PRIMARY KEY (org, world_model_id, id));
CREATE TABLE IF NOT EXISTS llm_cache (
  key TEXT PRIMARY KEY, provider TEXT NOT NULL, model TEXT NOT NULL, value TEXT NOT NULL);
"""

WORD = re.compile(r"[\w][\w'.&-]*", re.UNICODE)
EXT = re.compile(r"[^a-z0-9]+")
DOC_ID = re.compile(r"[0-9a-f]{24}")        # a content id (store.content_id): the only name a raw file may have


def _iso(t: datetime | None) -> str | None:
    return None if t is None else t.isoformat()


def _dt(s: str | None) -> datetime | None:
    return None if s is None else datetime.fromisoformat(s)


def _utc_iso(t: datetime) -> str:
    """A filter time as the stored times are written (UTC ISO), so comparing the strings compares the times."""
    return (t.astimezone(UTC) if t.tzinfo else t.replace(tzinfo=UTC)).isoformat()


def _admits(tenant: str, f: RetrievalFilter) -> tuple[str, list[Any]]:
    """SQL over `documents d` that holds for the documents the filter admits, and its arguments."""
    def among(col: str, values: list[str]) -> str:
        return f"{col} IN ({','.join('?' * len(values))})"

    sql, args = ["d.tenant=?"], [tenant]
    for col, values in (("d.id", f.document_ids), ("d.source_type", f.source_types),
                        ("lower(d.source)", [v.lower() for v in f.sources])):
        if values:
            sql.append(among(col, values))
            args += values
    if f.published_from is not None:
        sql.append("d.event_time>=?")
        args.append(_utc_iso(f.published_from))
    if f.published_to is not None:
        sql.append("d.event_time<?")
        args.append(_utc_iso(f.published_to))
    if f.entity_ids:
        sql.append(f"d.id IN (SELECT doc_id FROM mentions WHERE tenant=? AND {among('entity_id', f.entity_ids)})")
        args += [tenant, *f.entity_ids]
    return " AND ".join(sql), args


def fts_query(query: str, *, prefix: bool = False, any_term: bool = False) -> str | None:
    """A safe FTS5 query: each word quoted (so no operator in the input is interpreted), all required unless
    any_term; with prefix, the last word matches as a prefix."""
    words = [w.strip(".'&-") for w in WORD.findall(query)]
    words = [w for w in words if w]
    if not words:
        return None
    terms = ['"' + w.replace('"', '""') + '"' for w in words]
    if prefix:
        terms[-1] += "*"
    return (" OR " if any_term else " ").join(terms)


class SQLiteLake(LakeStore):
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root / "lake.sqlite3", check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)
        self.db.commit()
        # (tenant, model) -> (doc ids, ordinals, unit-length float64 rows); valid while data_version is unchanged
        self._vectors: dict[tuple[str, str], tuple[list[str], list[int], np.ndarray]] = {}
        self._version = self._data_version()

    # -- files ------------------------------------------------------------------------------------------------
    def _raw_path(self, tenant: str, doc: Document) -> Path:
        ext = EXT.sub("", Path(doc.filename).suffix.lower())[:8]
        safe_tenant = EXT.sub("_", tenant.lower()).strip("_") or "default"
        if safe_tenant != tenant:                 # keep sanitized names apart: "Acme" and "acme" are two silos
            safe_tenant += "-" + hashlib.sha256(tenant.encode()).hexdigest()[:8]
        # a document id names a file, so it must be a content id; a remote caller could send anything else ("../x")
        if not DOC_ID.fullmatch(doc.id):
            raise ValueError(f"not a content id: {doc.id!r}")
        root = os.path.realpath(self.root)
        path = os.path.realpath(os.path.join(root, safe_tenant, "raw", f"{doc.id}{'.' + ext if ext else ''}"))
        if not path.startswith(root + os.sep):
            raise ValueError(f"not a content id: {doc.id!r}")
        return Path(path)

    # -- documents --------------------------------------------------------------------------------------------
    def _doc(self, row: tuple) -> Document:
        (tenant, id_, sha, filename, mime, size, source, source_type, title, published_at, event_time, ingested_at,
         uploaded_by, meta, status, error) = row
        return Document(tenant=tenant, id=id_, sha256=sha, filename=filename, mime=mime, size=size, source=source,
                        source_type=source_type, title=title, published_at=_dt(published_at),
                        event_time=_dt(event_time), ingested_at=_dt(ingested_at), uploaded_by=uploaded_by,
                        meta=json.loads(meta), status=status, error=error)

    def put_document(self, doc: Document, data: bytes) -> tuple[Document, bool]:
        with self.lock:
            old = self.get_document(doc.tenant, doc.id)
            if old is not None:
                return old, False
            path = self._raw_path(doc.tenant, doc)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            self.db.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                doc.tenant, doc.id, doc.sha256, doc.filename, doc.mime, doc.size, doc.source, doc.source_type,
                doc.title, _iso(doc.published_at), _iso(doc.event_time), _iso(doc.ingested_at), doc.uploaded_by,
                json.dumps(doc.meta, sort_keys=True), doc.status, doc.error))
            self.db.commit()
            return doc, True

    def get_document(self, tenant: str, doc_id: str) -> Document | None:
        with self.lock:
            row = self.db.execute("SELECT * FROM documents WHERE tenant=? AND id=?", (tenant, doc_id)).fetchone()
        return None if row is None else self._doc(row)

    def raw_bytes(self, tenant: str, doc_id: str) -> bytes | None:
        doc = self.get_document(tenant, doc_id)
        if doc is None:
            return None
        path = self._raw_path(tenant, doc)
        return path.read_bytes() if path.exists() else None

    def list_documents(self, tenant: str, *, since: datetime | None = None, until: datetime | None = None,
                       order: str = "event_time", limit: int = 100, offset: int = 0) -> list[Document]:
        col = {"event_time": "event_time", "ingested_at": "ingested_at"}.get(order)
        if col is None:
            raise ValueError(f"order must be event_time or ingested_at, not {order!r}")
        sql = f"SELECT * FROM documents WHERE tenant=?{' AND ' + col + '>=?' if since else ''}" \
              f"{' AND ' + col + '<?' if until else ''} ORDER BY {col}, id LIMIT ? OFFSET ?"
        args: list[Any] = [tenant, *([_iso(since)] if since else []), *([_iso(until)] if until else []), limit, offset]
        with self.lock:
            rows = self.db.execute(sql, args).fetchall()
        return [self._doc(r) for r in rows]

    def update_document(self, tenant: str, doc_id: str, **fields: Any) -> Document:
        with self.lock:
            doc = self.get_document(tenant, doc_id)
            if doc is None:
                raise KeyError(doc_id)
            new = doc.model_copy(update=fields)
            self.db.execute("UPDATE documents SET source=?, source_type=?, title=?, published_at=?, event_time=?, "
                            "meta=?, status=?, error=? WHERE tenant=? AND id=?",
                            (new.source, new.source_type, new.title, _iso(new.published_at), _iso(new.event_time),
                             json.dumps(new.meta, sort_keys=True), new.status, new.error, tenant, doc_id))
            self.db.commit()
            return new

    def delete_document(self, tenant: str, doc_id: str) -> bool:
        with self.lock:
            doc = self.get_document(tenant, doc_id)
            if doc is None:
                return False
            for table in ("texts", "chunks", "mentions", "embeddings"):
                self.db.execute(f"DELETE FROM {table} WHERE tenant=? AND doc_id=?", (tenant, doc_id))
            self._forget(tenant)
            for fts in ("chunks_fts", "chunks_prefix"):
                self.db.execute(f"DELETE FROM {fts} WHERE tenant=? AND doc_id=?", (tenant, doc_id))
            self.db.execute("DELETE FROM documents WHERE tenant=? AND id=?", (tenant, doc_id))
            self.db.commit()
            path = self._raw_path(tenant, doc)
            if path.exists():
                path.unlink()
            return True

    def overview(self, tenant: str, *, since: datetime | None = None) -> dict[str, Any]:
        with self.lock:
            statuses = dict(self.db.execute("SELECT status, COUNT(*) FROM documents WHERE tenant=? GROUP BY status ORDER BY status",
                                            (tenant,)).fetchall())
            last = self.db.execute("SELECT MAX(ingested_at) FROM documents WHERE tenant=?", (tenant,)).fetchone()[0]
            new = 0 if since is None else self.db.execute("SELECT COUNT(*) FROM documents WHERE tenant=? AND ingested_at>?",
                                                          (tenant, _iso(since))).fetchone()[0]
        return {"statuses": statuses, "last_ingested_at": last, "new": new}

    # -- text, chunks, mentions, embeddings ------------------------------------------------------------------
    def put_text(self, tenant: str, doc_id: str, text: str, parser: str) -> None:
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO texts VALUES (?,?,?,?)", (tenant, doc_id, parser, text))
            self.db.commit()

    def get_text(self, tenant: str, doc_id: str) -> tuple[str, str] | None:
        with self.lock:
            row = self.db.execute("SELECT text, parser FROM texts WHERE tenant=? AND doc_id=?", (tenant, doc_id)).fetchone()
        return None if row is None else (row[0], row[1])

    def put_chunks(self, tenant: str, doc_id: str, chunks: list[Chunk]) -> None:
        with self.lock:
            self.db.execute("DELETE FROM chunks WHERE tenant=? AND doc_id=?", (tenant, doc_id))
            self.db.executemany("INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?)", [
                (tenant, doc_id, c.ord, c.start, c.end, c.text, c.page, c.section) for c in chunks])
            for fts in ("chunks_fts", "chunks_prefix"):
                self.db.execute(f"DELETE FROM {fts} WHERE tenant=? AND doc_id=?", (tenant, doc_id))
                self.db.executemany(f"INSERT INTO {fts} (text, tenant, doc_id, ord) VALUES (?,?,?,?)", [
                    (c.text, tenant, doc_id, c.ord) for c in chunks])
            self.db.commit()

    def get_chunks(self, tenant: str, doc_id: str) -> list[Chunk]:
        with self.lock:
            rows = self.db.execute('SELECT tenant, doc_id, ord, start, "end", text, page, section FROM chunks '
                                   "WHERE tenant=? AND doc_id=? ORDER BY ord", (tenant, doc_id)).fetchall()
        return [Chunk(tenant=r[0], doc_id=r[1], ord=r[2], start=r[3], end=r[4], text=r[5], page=r[6], section=r[7])
                for r in rows]

    def count_chunks(self, tenant: str, doc_ids: list[str] | None = None) -> dict[str, int]:
        if doc_ids is None:
            with self.lock:
                rows = self.db.execute("SELECT doc_id, COUNT(*) FROM chunks WHERE tenant=? GROUP BY doc_id ORDER BY doc_id",
                                       (tenant,)).fetchall()
            return {d: n for d, n in rows}
        out = {d: 0 for d in doc_ids}
        for k in range(0, len(doc_ids), 500):                     # SQLite caps the variables in one statement
            part = doc_ids[k:k + 500]
            with self.lock:
                rows = self.db.execute(f"SELECT doc_id, COUNT(*) FROM chunks WHERE tenant=? AND doc_id IN "
                                       f"({','.join('?' * len(part))}) GROUP BY doc_id", (tenant, *part)).fetchall()
            out.update({d: n for d, n in rows})
        return out

    def put_mentions(self, tenant: str, doc_id: str, mentions: list[Mention]) -> None:
        with self.lock:
            self.db.execute("DELETE FROM mentions WHERE tenant=? AND doc_id=?", (tenant, doc_id))
            self.db.executemany("INSERT INTO mentions VALUES (?,?,?,?,?,?)", [
                (tenant, doc_id, m.ord, m.entity_id, m.subentity_id, m.surface) for m in mentions])
            self.db.commit()

    def mentions_of(self, tenant: str, *, entity_id: str | None = None, subentity_id: str | None = None,
                    doc_id: str | None = None) -> list[Mention]:
        sql = "SELECT tenant, doc_id, ord, entity_id, subentity_id, surface FROM mentions WHERE tenant=?"
        args: list[Any] = [tenant]
        for col, val in (("entity_id", entity_id), ("subentity_id", subentity_id), ("doc_id", doc_id)):
            if val is not None:
                sql += f" AND {col}=?"
                args.append(val)
        sql += " ORDER BY doc_id, ord, entity_id, subentity_id, surface"
        with self.lock:
            rows = self.db.execute(sql, args).fetchall()
        return [Mention(tenant=r[0], doc_id=r[1], ord=r[2], entity_id=r[3], subentity_id=r[4], surface=r[5]) for r in rows]

    def put_embeddings(self, tenant: str, doc_id: str, model: str, vectors: list[list[float]]) -> None:
        with self.lock:
            self.db.execute("DELETE FROM embeddings WHERE tenant=? AND doc_id=? AND model=?", (tenant, doc_id, model))
            self.db.executemany("INSERT INTO embeddings VALUES (?,?,?,?,?)", [
                (tenant, doc_id, k, model, array("f", v).tobytes()) for k, v in enumerate(vectors)])
            self.db.commit()
            self._forget(tenant)

    def embeddings(self, tenant: str, model: str) -> list[tuple[str, int, list[float]]]:
        with self.lock:
            rows = self.db.execute("SELECT doc_id, ord, vec FROM embeddings WHERE tenant=? AND model=? "
                                   "ORDER BY doc_id, ord", (tenant, model)).fetchall()
        out = []
        for doc_id, ord_, blob in rows:
            a = array("f")
            a.frombytes(blob)
            out.append((doc_id, ord_, a.tolist()))
        return out

    def nearest(self, tenant: str, model: str, query: list[float], limit: int = 20) -> list[tuple[float, str, int]]:
        with self.lock:
            docs, ords, rows = self._matrix(tenant, model)
        if not docs:
            return []
        q = np.asarray(query, dtype=np.float64)
        q = q / (float(np.linalg.norm(q)) or 1.0)
        scores = np.round(rows @ q, 6)
        # rows are in (doc, ordinal) order, so a stable sort on the score alone breaks ties by document then position
        top = np.argsort(-scores, kind="stable")[:limit]
        return [(float(scores[i]), docs[i], ords[i]) for i in top]

    def _data_version(self) -> int:
        return self.db.execute("PRAGMA data_version").fetchone()[0]

    def _forget(self, tenant: str) -> None:
        for key in [k for k in self._vectors if k[0] == tenant]:
            del self._vectors[key]

    def _matrix(self, tenant: str, model: str) -> tuple[list[str], list[int], np.ndarray]:
        """A tenant's vectors as unit-length rows, built once and reused until they change (called under the lock)."""
        version = self._data_version()
        if version != self._version:          # another connection committed: anything held may be stale
            self._vectors.clear()
            self._version = version
        if (tenant, model) not in self._vectors:
            rows = self.db.execute("SELECT doc_id, ord, vec FROM embeddings WHERE tenant=? AND model=? "
                                   "ORDER BY doc_id, ord", (tenant, model)).fetchall()
            m = (np.vstack([np.frombuffer(b, dtype=np.float32) for _d, _o, b in rows]).astype(np.float64)
                 if rows else np.zeros((0, 0)))
            norms = np.linalg.norm(m, axis=1, keepdims=True) if rows else m
            self._vectors[(tenant, model)] = ([d for d, _o, _b in rows], [o for _d, o, _b in rows],
                                              m / np.where(norms == 0, 1.0, norms) if rows else m)
        return self._vectors[(tenant, model)]

    # -- search -----------------------------------------------------------------------------------------------
    def keyword_search(self, tenant: str, query: str, *, prefix: bool = False, limit: int = 20) -> list[Hit]:
        hits: list[Hit] = []
        fts = "chunks_prefix" if prefix else "chunks_fts"
        for any_term in (False, True):          # every word first; any word when that finds nothing
            q = fts_query(query, prefix=prefix, any_term=any_term)
            if q is None:
                return []
            with self.lock:
                rows = self.db.execute(
                    f"SELECT f.doc_id, f.ord, f.text, bm25({fts}) AS s, d.title, d.filename, d.event_time "
                    f"FROM {fts} f JOIN documents d ON d.tenant=f.tenant AND d.id=f.doc_id "
                    f"WHERE {fts} MATCH ? AND f.tenant=? ORDER BY s, f.doc_id, f.ord LIMIT ?",
                    (q, tenant, limit)).fetchall()
            hits = [Hit(kind="chunk", doc_id=r[0], ord=int(r[1]), score=round(-float(r[3]), 6), text=r[2], title=r[4],
                        filename=r[5], event_time=_dt(r[6]),
                        why=["prefix" if prefix else "keyword", *(["any word"] if any_term else [])]) for r in rows]
            if hits:
                break
        return hits

    # -- retrieval --------------------------------------------------------------------------------------------
    def retrieve(self, tenant: str, spec: RetrievalSpec) -> Retrieval:
        if not spec.channels or set(spec.channels) - set(CHANNELS):
            raise ValueError(f"channels must be some of {', '.join(CHANNELS)}")
        if spec.offset + spec.limit > MAX_DEPTH:
            raise ValueError(f"a retrieval pages at most {MAX_DEPTH} passages deep; narrow it with a filter")
        where, args = _admits(tenant, spec.filter)
        depth = min(MAX_DEPTH, 3 * (spec.offset + spec.limit) + 50)    # candidates per channel: room for the cap
        ranked: list[list[tuple[str, int, float, list[str]]]] = []
        with self.lock:
            if "keyword" in spec.channels:
                ranked.append(self._keyword_ranks(spec.query, where, args, depth))
            if "semantic" in spec.channels and spec.vector is not None:
                admitted = {r[0] for r in self.db.execute(f"SELECT d.id FROM documents d WHERE {where}", args)}
                ranked.append(self._semantic_ranks(tenant, spec, admitted, depth))
            if "graph" in spec.channels and (spec.entity_ids or spec.attribute_ids):
                ranked.append(self._graph_ranks(tenant, spec, where, args, depth))
        fused: dict[tuple[str, int], float] = {}
        scores: dict[tuple[str, int], dict[str, float]] = {}
        why: dict[tuple[str, int], list[str]] = {}
        for hits in ranked:
            for rank, (doc_id, ord_, score, tags) in enumerate(hits):
                key = (doc_id, ord_)
                fused[key] = fused.get(key, 0.0) + 1.0 / (RRF_K + rank + 1)
                scores.setdefault(key, {})[tags[0]] = score
                why.setdefault(key, []).extend(t for t in tags if t not in why.get(key, []))
        order = sorted(fused, key=lambda k: (-round(fused[k], 9), k))
        if spec.per_document:
            capped, seen = [], dict.fromkeys((d for d, _o in order), 0)
            for k in order:
                seen[k[0]] += 1
                if seen[k[0]] <= spec.per_document:
                    capped.append(k)
            order = capped
        keys = order[spec.offset:spec.offset + spec.limit]
        return Retrieval(passages=self._passages(tenant, keys, spec.context, fused, scores, why),
                         more=len(order) > spec.offset + spec.limit)

    def _keyword_ranks(self, query: str, where: str, args: list[Any], depth: int) -> list[tuple[str, int, float, list[str]]]:
        """BM25 over the admitted documents' chunks: every word first, any word when that finds nothing."""
        for any_term in (False, True):
            q = fts_query(query, any_term=any_term)
            if q is None:
                return []
            rows = self.db.execute(
                "SELECT f.doc_id, f.ord, bm25(chunks_fts) AS s FROM chunks_fts f "
                f"JOIN documents d ON d.tenant=f.tenant AND d.id=f.doc_id WHERE chunks_fts MATCH ? AND {where} "
                "ORDER BY s, f.doc_id, f.ord LIMIT ?", (q, *args, depth)).fetchall()
            if rows:
                return [(d, int(o), round(-float(s), 6), ["keyword", *(["any word"] if any_term else [])])
                        for d, o, s in rows]
        return []

    def _semantic_ranks(self, tenant: str, spec: RetrievalSpec, admitted: set[str],
                        depth: int) -> list[tuple[str, int, float, list[str]]]:
        """Cosine similarity against the admitted documents' chunks, exactly, from the cached matrix."""
        docs, ords, rows = self._matrix(tenant, spec.model)
        keep = np.flatnonzero(np.fromiter((d in admitted for d in docs), dtype=bool, count=len(docs)))
        if not keep.size:
            return []
        q = np.asarray(spec.vector, dtype=np.float64)
        q = q / (float(np.linalg.norm(q)) or 1.0)
        scores = np.round(rows[keep] @ q, 6)
        top = np.argsort(-scores, kind="stable")[:depth]          # rows are in (doc, ordinal) order: ties stay so
        return [(docs[keep[i]], ords[keep[i]], float(scores[i]), ["semantic"]) for i in top]

    def _graph_ranks(self, tenant: str, spec: RetrievalSpec, where: str, args: list[Any],
                     depth: int) -> list[tuple[str, int, float, list[str]]]:
        """The admitted chunks that name what the query names, most mentions first. With attributes named, a mention
        counts when it is of one of them, or of an entity alone."""
        ents = sorted(set(spec.entity_ids))
        sql = (f"SELECT m.doc_id, m.ord, COUNT(*) AS n FROM mentions m JOIN documents d ON d.tenant=m.tenant AND "
               f"d.id=m.doc_id WHERE {where} AND m.entity_id IN ({','.join('?' * len(ents))})")
        extra: list[Any] = list(ents)
        if spec.attribute_ids:
            vals = sorted(set(spec.attribute_ids))
            sql += f" AND (m.subentity_id IS NULL OR m.subentity_id IN ({','.join('?' * len(vals))}))"
            extra += vals
        rows = self.db.execute(sql + " GROUP BY m.doc_id, m.ord ORDER BY n DESC, m.doc_id, m.ord LIMIT ?",
                               (*args, *extra, depth)).fetchall()
        top = max((n for _d, _o, n in rows), default=1)
        return [(d, o, round(n / top, 6), ["graph"]) for d, o, n in rows]

    def _passages(self, tenant: str, keys: list[tuple[str, int]], context: int, fused: dict, scores: dict,
                  why: dict) -> list[Passage]:
        """The page's passages, read in three queries whatever its length. A chunk that is gone (an embedding outliving
        a re-read) is left out."""
        doc_ids = sorted({d for d, _o in keys})
        if not doc_ids:
            return []
        marks = ",".join("?" * len(doc_ids))
        spans = " OR ".join("(doc_id=? AND ord BETWEEN ? AND ?)" for _k in keys)
        span_args = [x for d, o in keys for x in (d, o - context, o + context)]
        with self.lock:
            docs = {r[1]: self._doc(r) for r in self.db.execute(
                f"SELECT * FROM documents WHERE tenant=? AND id IN ({marks})", (tenant, *doc_ids))}
            chunks = {(r[1], r[2]): Chunk(tenant=r[0], doc_id=r[1], ord=r[2], start=r[3], end=r[4], text=r[5], page=r[6],
                                          section=r[7]) for r in self.db.execute(
                'SELECT tenant, doc_id, ord, start, "end", text, page, section FROM chunks '
                f"WHERE tenant=? AND ({spans})", (tenant, *span_args))}
            mentions: dict[tuple[str, int], list[Mention]] = {}
            for r in self.db.execute("SELECT tenant, doc_id, ord, entity_id, subentity_id, surface FROM mentions "
                                     f"WHERE tenant=? AND doc_id IN ({marks}) "
                                     "ORDER BY doc_id, ord, entity_id, subentity_id, surface", (tenant, *doc_ids)):
                mentions.setdefault((r[1], r[2]), []).append(Mention(tenant=r[0], doc_id=r[1], ord=r[2], entity_id=r[3],
                                                                     subentity_id=r[4], surface=r[5]))
        out = []
        for d, o in keys:
            if (d, o) not in chunks or d not in docs:
                continue
            out.append(Passage(chunk=chunks[(d, o)], document=docs[d], score=round(fused[(d, o)], 6),
                               scores=scores[(d, o)], why=why[(d, o)], mentions=mentions.get((d, o), []),
                               before=[chunks[(d, k)] for k in range(o - context, o) if (d, k) in chunks],
                               after=[chunks[(d, k)] for k in range(o + 1, o + context + 1) if (d, k) in chunks]))
        return out

    # -- bundles and imports ----------------------------------------------------------------------------------
    def put_bundle(self, rec: BundleRecord) -> BundleRecord:
        with self.lock:
            old = self.get_bundle(rec.tenant, rec.id)
            if old is not None:
                return old
            self.db.execute("INSERT INTO bundles VALUES (?,?,?,?,?,?,?,?)", (
                rec.tenant, rec.id, json.dumps(rec.doc_ids), _iso(rec.created_at), rec.extractor_version, rec.items,
                rec.signals, json.dumps(rec.bundle, sort_keys=True, default=str)))
            self.db.commit()
            return rec

    def _bundle(self, r: tuple) -> BundleRecord:
        return BundleRecord(tenant=r[0], id=r[1], doc_ids=json.loads(r[2]), created_at=_dt(r[3]), extractor_version=r[4],
                            items=r[5], signals=r[6], bundle=json.loads(r[7]))

    def get_bundle(self, tenant: str, bundle_id: str) -> BundleRecord | None:
        with self.lock:
            row = self.db.execute("SELECT * FROM bundles WHERE tenant=? AND id=?", (tenant, bundle_id)).fetchone()
        return None if row is None else self._bundle(row)

    def list_bundles(self, tenant: str, *, doc_id: str | None = None, limit: int = 100) -> list[BundleRecord]:
        with self.lock:
            rows = self.db.execute("SELECT * FROM bundles WHERE tenant=? ORDER BY created_at, id", (tenant,)).fetchall()
        recs = [self._bundle(r) for r in rows]
        if doc_id is not None:
            recs = [r for r in recs if doc_id in r.doc_ids]
        return recs[:limit]

    def delete_bundles_of(self, tenant: str, doc_id: str) -> int:
        with self.lock:
            rows = self.db.execute("SELECT id, doc_ids FROM bundles WHERE tenant=? AND doc_ids LIKE ?",
                                   (tenant, f'%"{doc_id}"%')).fetchall()
            used = {r[0] for r in self.db.execute("SELECT bundle_id FROM imports WHERE tenant=?", (tenant,)).fetchall()}
            gone = [b for b, ids in rows if json.loads(ids) == [doc_id] and b not in used]
            self.db.executemany("DELETE FROM bundles WHERE tenant=? AND id=?", [(tenant, b) for b in gone])
            self.db.commit()
        return len(gone)

    def put_import(self, rec: ImportRecord) -> None:
        with self.lock:
            self.db.execute("INSERT INTO imports VALUES (?,?,?,?,?,?)", (
                rec.tenant, rec.bundle_id, _iso(rec.imported_at), rec.update_id, json.dumps(rec.item_ids), rec.by))
            self.db.commit()

    def list_imports(self, tenant: str, *, bundle_id: str | None = None) -> list[ImportRecord]:
        sql = "SELECT * FROM imports WHERE tenant=?" + (" AND bundle_id=?" if bundle_id else "") + \
              " ORDER BY imported_at, bundle_id"
        with self.lock:
            rows = self.db.execute(sql, (tenant, bundle_id) if bundle_id else (tenant,)).fetchall()
        return [ImportRecord(tenant=r[0], bundle_id=r[1], imported_at=_dt(r[2]), update_id=r[3],
                             item_ids=json.loads(r[4]), by=r[5]) for r in rows]

    # -- the world model registry and the audit log ---------------------------------------------------------
    def register_world_model(self, rec: WorldModelRecord) -> WorldModelRecord:
        with self.lock:
            self.db.execute("INSERT INTO world_models VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                            "org_id=excluded.org_id, name=excluded.name", (rec.id, rec.org_id, rec.name,
                                                                          _iso(rec.created_at)))
            self.db.commit()
            row = self.db.execute("SELECT * FROM world_models WHERE id=?", (rec.id,)).fetchone()
        return WorldModelRecord(id=row[0], org_id=row[1], name=row[2], created_at=_dt(row[3]))

    def world_models(self, org_id: str | None = None) -> list[WorldModelRecord]:
        sql = "SELECT * FROM world_models" + (" WHERE org_id=?" if org_id is not None else "") + " ORDER BY id"
        with self.lock:
            rows = self.db.execute(sql, (org_id,) if org_id is not None else ()).fetchall()
        return [WorldModelRecord(id=r[0], org_id=r[1], name=r[2], created_at=_dt(r[3])) for r in rows]

    def put_audit(self, rec: AuditRecord) -> None:
        with self.lock:
            self.db.execute("INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
                rec.org, rec.id, _iso(rec.at), rec.request_id, rec.world_model_id, rec.method, rec.route, rec.status,
                json.dumps(rec.actor, sort_keys=True), json.dumps(rec.scopes), json.dumps(rec.resource_ids)))
            self.db.commit()

    def list_audit(self, org: str, world_model_id: str) -> list[AuditRecord]:
        with self.lock:
            rows = self.db.execute("SELECT * FROM audit_events WHERE org=? AND world_model_id=? ORDER BY at DESC, id DESC",
                                   (org, world_model_id)).fetchall()
        return [AuditRecord(org=r[0], id=r[1], at=_dt(r[2]), request_id=r[3], world_model_id=r[4], method=r[5],
                            route=r[6], status=r[7], actor=json.loads(r[8]), scopes=json.loads(r[9]),
                            resource_ids=json.loads(r[10])) for r in rows]

    # -- idempotency keys and jobs (Oct 19): kept forever ------------------------------------------------------
    def get_idempotency(self, org: str, world_model_id: str, operation: str, key: str) -> IdempotencyRecord | None:
        with self.lock:
            r = self.db.execute("SELECT * FROM idempotency_keys WHERE org=? AND world_model_id=? AND operation=? AND "
                                "key=?", (org, world_model_id, operation, key)).fetchone()
        return None if r is None else IdempotencyRecord(
            org=r[0], world_model_id=r[1], operation=r[2], key=r[3], fingerprint=r[4], status=r[5], body=r[6],
            headers=json.loads(r[7]), created_at=_dt(r[8]))

    def put_idempotency(self, rec: IdempotencyRecord) -> None:
        with self.lock:
            self.db.execute("INSERT OR IGNORE INTO idempotency_keys VALUES (?,?,?,?,?,?,?,?,?)", (
                rec.org, rec.world_model_id, rec.operation, rec.key, rec.fingerprint, rec.status, rec.body,
                json.dumps(rec.headers, sort_keys=True), _iso(rec.created_at)))
            self.db.commit()

    def forget_idempotency(self, org: str, world_model_id: str, naming: str) -> int:
        with self.lock:
            n = self.db.execute("DELETE FROM idempotency_keys WHERE org=? AND world_model_id=? AND instr(body, ?) > 0",
                                (org, world_model_id, naming)).rowcount
            self.db.commit()
        return n

    def put_job(self, org: str, world_model_id: str, job: dict) -> None:
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO jobs VALUES (?,?,?,?)",
                            (org, world_model_id, job["id"], json.dumps(job, sort_keys=True)))
            self.db.commit()

    def get_job(self, org: str, world_model_id: str, job_id: str) -> dict | None:
        with self.lock:
            r = self.db.execute("SELECT job FROM jobs WHERE org=? AND world_model_id=? AND id=?",
                                (org, world_model_id, job_id)).fetchone()
        return None if r is None else json.loads(r[0])

    # -- the LLM step's replay cache --------------------------------------------------------------------------
    def cache_get(self, key: str) -> dict | None:
        with self.lock:
            row = self.db.execute("SELECT value FROM llm_cache WHERE key=?", (key,)).fetchone()
        return None if row is None else json.loads(row[0])

    def cache_put(self, key: str, provider: str, model: str, value: dict) -> None:
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO llm_cache VALUES (?,?,?,?)",
                            (key, provider, model, json.dumps(value, sort_keys=True)))
            self.db.commit()

    # -- housekeeping -----------------------------------------------------------------------------------------
    def stats(self, tenant: str) -> dict[str, int]:
        out = {}
        with self.lock:
            for table, key in (("documents", "documents"), ("chunks", "chunks"), ("mentions", "mentions"),
                               ("embeddings", "embeddings"), ("bundles", "bundles"), ("imports", "imports")):
                out[key] = int(self.db.execute(f"SELECT COUNT(*) FROM {table} WHERE tenant=?", (tenant,)).fetchone()[0])
        return out

    def tenants(self) -> list[str]:
        with self.lock:
            return [r[0] for r in self.db.execute("SELECT DISTINCT tenant FROM documents ORDER BY tenant").fetchall()]

    def close(self) -> None:
        with self.lock:
            self.db.close()
