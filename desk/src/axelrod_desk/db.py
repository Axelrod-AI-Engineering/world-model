"""The desk's own state, in one SQLite file (Nov 2): accounts and their sessions, the library's documents, readings and the
records they produced, fact reviews, world models (a person's saved selections) and their builds.

The documents' bytes and page text live beside it, under the home (`files/`, `text/`); the lake (`lake/`) holds what
ingestion makes of them. One connection is shared behind a lock, as the lake's SQLite store does, so the web app's worker
threads and a running build never write at once.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
create table if not exists accounts (
  id integer primary key, email text unique not null, name text not null, pw text not null,
  admin integer not null default 0, created_at text not null);
create table if not exists sessions (
  token text primary key, account_id integer not null references accounts(id), kind text not null,
  created_at text not null, last_used text);
create table if not exists documents (
  sha256 text primary key, filename text not null, ext text not null, size integer not null, pages integer not null,
  text_engine text not null, title text, company text, source_class text not null, publisher text, published text,
  url text, section text, language text, doc_type text, period text, origin_group text, origin_role text,
  origin_primary text, status text not null, added_by integer, added_at text not null, note text);
create table if not exists uploads (
  id integer primary key, sha256 text not null, account_id integer, filename text not null, at text not null,
  outcome text not null);
create table if not exists readings (
  id integer primary key, sha256 text not null, account_id integer, reader text not null, model text,
  started_at text not null, finished_at text, status text not null, accepted integer not null default 0,
  rejected integer not null default 0, rounds integer not null default 0, cost real, error text);
create table if not exists records (
  id text primary key, sha256 text not null, reading_id integer not null, company text not null, ok integer not null,
  problems text not null, data text not null);
create table if not exists themes (
  id integer primary key, sha256 text not null, reading_id integer not null, data text not null);
create table if not exists reviews (
  fact_key text primary key, decision text not null, account_id integer, at text not null, note text);
create table if not exists world_models (
  id integer primary key, account_id integer not null, name text not null, companies text not null,
  groups text not null, classes text not null, apply integer not null, created_at text not null);
create table if not exists builds (
  id integer primary key, world_model_id integer not null, account_id integer, status text not null,
  started_at text not null, finished_at text, out_dir text, zip text, summary text, error text);
create index if not exists records_by_doc on records(sha256);
create index if not exists readings_by_doc on readings(sha256);
"""
JSON_COLUMNS = {"problems", "data", "companies", "groups", "classes", "summary"}


def now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class Db:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def all(self, sql: str, args: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self.lock:
            return [_row(r) for r in self.conn.execute(sql, tuple(args)).fetchall()]

    def one(self, sql: str, args: Iterable[Any] = ()) -> dict[str, Any] | None:
        rows = self.all(sql, args)
        return rows[0] if rows else None

    def run(self, sql: str, args: Iterable[Any] = ()) -> int:
        """Execute and commit; the new row's id (for an insert)."""
        with self.lock:
            cur = self.conn.execute(sql, tuple(_cell(a) for a in args))
            self.conn.commit()
            return cur.lastrowid or 0

    def insert(self, table: str, row: dict[str, Any], *, replace: bool = False) -> int:
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        verb = "insert or replace" if replace else "insert"
        return self.run(f"{verb} into {table} ({cols}) values ({marks})", row.values())

    def update(self, table: str, key: str, value: Any, fields: dict[str, Any]) -> None:
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.run(f"update {table} set {sets} where {key} = ?", [*fields.values(), value])


def _cell(v: Any) -> Any:
    return json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v


def _row(r: sqlite3.Row) -> dict[str, Any]:
    return {k: json.loads(r[k]) if k in JSON_COLUMNS and isinstance(r[k], str) else r[k] for k in r.keys()}


__all__ = ["Db", "SCHEMA", "now"]
