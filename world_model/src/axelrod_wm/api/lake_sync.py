"""The lake sync (world_model/docs/design/unified-model.md, "Lake sync"): a document added straight to the lake (through the
ingestion console, or the ingestion service's /v1/ingest) is stored and searchable, but ingestion read it without the
model's world view, so nothing in it was recognized and nothing reached the model. This task reads such documents again
against the model and imports them, for each world model the process serves, with the code the API's own routes use:

- reading is `POST .../documents/{id}/bundles` (`Ingestor.process` against the model's view), and
- importing is `POST .../changes` (`run_proposal`, `record_import`); a compartment's view narrows the bundle, and the
  review policy decides (under `standards`, what is well attributed applies and the rest stays pending, with reasons).

**Which documents.** In an organization's tenant, in ingested order, a document whose status is `stored` or `extracted`
and that has no mention recorded (ingestion found no name of the model in it, or never had the view) and no ledger entry
for this model. A document that already has mentions was read against a model (an upload through the API); it is left to
the person who uploaded it, and noted in the ledger. `excluded`, `failed`, `needs_ocr`, and `parsed` documents are left
alone.

**The ledger.** Each document the sync has dealt with is recorded in the lakehouse as an idempotency record under the
operation `lake-sync` (organization, world model, document id; the body names the document and what happened), so a
restart reads nothing twice, and deleting a document forgets its entry. The items themselves are deduplicated by the
import map as always.

**Never in the way.** One engine at a time, under the proposal claim (`claim_proposal`): while an update is running or
waiting for review (`review_all`), or another import is starting, the engine is skipped this tick and the status says so.
An error (the lake or the ingestion service unreachable) is kept in the status and backs the engine off, doubling up to ten
minutes; it never reaches the app.
"""

from __future__ import annotations

import asyncio
import functools
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import anyio

from axelrod_ingest.lake.store import IdempotencyRecord

logger = logging.getLogger(__name__)

OPERATION = "lake-sync"
READABLE = ("stored", "extracted")
DEFAULT_SECONDS = 30.0
MAX_BACKOFF = 600.0
PAGE = 500
BY = "lake-sync"


def settings_from_env(enabled: bool | None = None, seconds: float | None = None) -> tuple[bool, float]:
    """(on, interval): given, else WORLD_MODEL_LAKE_SYNC (1/0), else on exactly when the lake is a service
    (WORLD_MODEL_LAKE_URL); WORLD_MODEL_LAKE_SYNC_SECONDS (default 30)."""
    if enabled is None:
        raw = os.environ.get("WORLD_MODEL_LAKE_SYNC", "").strip().lower()
        enabled = raw in ("1", "true", "yes", "on") if raw else bool(os.environ.get("WORLD_MODEL_LAKE_URL"))
    if seconds is None:
        seconds = float(os.environ.get("WORLD_MODEL_LAKE_SYNC_SECONDS") or DEFAULT_SECONDS)
    return enabled, seconds


@dataclass
class ModelSync:
    """One world model's sync state, in memory (the ledger is the lakehouse's)."""

    last_tick_at: datetime | None = None
    seen: int = 0
    read: int = 0
    imported: int = 0
    pending: int = 0
    skipped: int = 0
    waiting: int = 0
    paused: str | None = None
    failures: int = 0
    last_error: str | None = None
    retry_at: float = 0.0
    done: set[str] = field(default_factory=set)         # document ids known to be in the ledger
    changes: set[str] = field(default_factory=set)      # the changes this sync proposed


class LakeSync:
    def __init__(self, app: Any, *, enabled: bool, interval: float) -> None:
        self.app = app
        self.enabled = enabled
        self.interval = interval
        self.models: dict[str, ModelSync] = {}
        self.task: asyncio.Task | None = None

    # -- the task ------------------------------------------------------------------------------------
    def start(self) -> None:
        if self.enabled and self.task is None:
            self.task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None

    async def run(self) -> None:
        while True:
            await self.tick()
            await asyncio.sleep(self.interval)

    async def tick(self) -> None:
        """One pass over every world model this process serves, in id order. Does nothing when the sync is off."""
        if not self.enabled:
            return
        for wid, m in sorted(self.app.state.world_models.items()):
            await self.sync_model(wid, m)

    # -- status --------------------------------------------------------------------------------------
    def status_of(self, wid: str) -> dict:
        s = self.models.get(wid) or ModelSync()
        return {"enabled": self.enabled, "interval_seconds": self.interval, "last_tick_at": s.last_tick_at,
                "seen": s.seen, "read": s.read, "imported": s.imported, "pending": s.pending, "skipped": s.skipped,
                "waiting": s.waiting, "paused": s.paused, "failures": s.failures, "last_error": s.last_error}

    # -- one world model -----------------------------------------------------------------------------
    async def sync_model(self, wid: str, m: Any) -> None:
        s = self.models.setdefault(wid, ModelSync())
        if time.monotonic() < s.retry_at:
            return
        s.last_tick_at = datetime.now(UTC)
        try:
            await self._sync(m, s)
            s.failures, s.last_error, s.retry_at = 0, None, 0.0
        except Exception as exc:                # unreachable lake or ingestion, a failed read: report, back off, go on
            s.failures += 1
            s.last_error = f"{type(exc).__name__}: {exc}"
            s.retry_at = time.monotonic() + min(self.interval * 2 ** s.failures, MAX_BACKOFF)
            logger.warning("lake sync of %s failed (%d in a row): %s", wid, s.failures, s.last_error)

    async def _documents(self, org: str) -> list[Any]:
        lk = self.app.state.lake
        out: list[Any] = []
        while True:
            got = await anyio.to_thread.run_sync(functools.partial(lk.list_documents, org, order="ingested_at",
                                                                   limit=PAGE, offset=len(out)))
            out += got
            if len(got) < PAGE:
                return out

    async def _in_ledger(self, m: Any, s: ModelSync, doc_id: str) -> bool:
        if doc_id in s.done:
            return True
        rec = await anyio.to_thread.run_sync(lambda: self.app.state.lake.get_idempotency(m.org, m.id, OPERATION, doc_id))
        if rec is not None:
            s.done.add(doc_id)
        return rec is not None

    async def _note(self, m: Any, s: ModelSync, doc_id: str, outcome: str, **more: Any) -> None:
        body = json.dumps({"document_id": doc_id, "outcome": outcome, **more}, sort_keys=True)
        rec = IdempotencyRecord(org=m.org, world_model_id=m.id, operation=OPERATION, key=doc_id, fingerprint=outcome,
                                status=200, body=body, headers={}, created_at=datetime.now(UTC))
        await anyio.to_thread.run_sync(self.app.state.lake.put_idempotency, rec)
        s.done.add(doc_id)

    def _read(self, m: Any, doc_id: str) -> Any:
        """Read a stored document against the model as it is now (under the engine's lock)."""
        from axelrod_wm.api.v1.context import view_of
        from axelrod_wm.api.v1.routes_ingest import ingestor_of

        return ingestor_of(self.app, m).process(m.org, doc_id, view_of(m))

    async def _sync(self, m: Any, s: ModelSync) -> None:
        from axelrod_wm.api.v1.routes_work import claim_proposal, record_import, run_proposal

        lk = self.app.state.lake
        docs = await self._documents(m.org)
        s.seen, s.paused = len(docs), None
        s.skipped = s.waiting = 0
        for i, doc in enumerate(docs):
            if doc.status not in READABLE or await self._in_ledger(m, s, doc.id):
                s.skipped += 1
                continue
            if await anyio.to_thread.run_sync(functools.partial(lk.mentions_of, m.org, doc_id=doc.id)):
                await self._note(m, s, doc.id, "read_elsewhere")
                s.skipped += 1
                continue
            got = await m.st.call(claim_proposal, self.app, m)
            if got != "claimed":                # an update runs or waits for review, or an import is starting
                s.paused = got
                s.waiting = sum(1 for d in docs[i:] if d.status in READABLE and d.id not in s.done)
                break
            try:
                res = await m.st.call(self._read, m, doc.id)
                s.read += 1
                if res.bundle is None or not res.signals:
                    await self._note(m, s, doc.id, "no_signals" if res.bundle is not None else res.document.status,
                                     bundle_id=None if res.bundle is None else res.bundle.id)
                    continue
                r = await m.st.call(run_proposal, m, res.bundle, None)
                record_import(self.app, m, res.bundle.id, r, BY)
                s.imported += len(r["out"]["imported"])
                s.changes.update(r["proposed"])
                await self._note(m, s, doc.id, "imported", bundle_id=res.bundle.id, items=r["out"]["imported"],
                                 changes=r["proposed"])
            finally:
                self.app.state.proposing.discard(m.id)
        s.pending = await m.st.call(lambda: sum(1 for c in s.changes
                                                if str(getattr(m.st.controller.proposals.get(c), "status", "")) == "pending"))
