"""The lake sync (api/lake_sync.py; world_model/docs/design/unified-model.md, "Lake sync"): a document put straight into an
organization's lake tenant, as the ingestion console does (read with no world view, so no names recognized), is read again
against the model and imported by the app itself. Synthetic notes only; the lake and the ingestor are in process, and a
tick is driven by hand (`LakeSync.tick`) except in the one test of the background task."""

from __future__ import annotations

import asyncio
import time

from axelrod_ingest.contract.world_view import WorldView
from axelrod_wm.api.lake_sync import settings_from_env
from tests.service.helpers import (
    NOTE,
    OIL_NOTE,
    RATE_NOTE,
    SPREAD_NOTE,
    WM,
    Signer,
    data,
    propose,
    service,
    upload,
)

SIGNER = Signer()
ORG = "default"


def console_add(c, payload: bytes, name: str, source_type: str = "central_bank", *, process: bool = True):
    """What the console (or the ingestion service's /v1/ingest) does: store the file in the tenant and, unless told not
    to, read it with an empty world view."""
    ing = c.app.state.ingestor
    if not process:
        return ing.store_file(ORG, payload, name, source="Synthetic wire", source_type=source_type)[0]
    return ing.ingest_file(ORG, payload, name, WorldView(), source="Synthetic wire", source_type=source_type).document


def tick(c, times: int = 1) -> dict:
    c.app.state.lake_sync.enabled = True
    for _ in range(times):
        asyncio.run(c.app.state.lake_sync.tick())
    return data(c.get(f"{WM}/sync"))


def changes(c, status: str = "all") -> list[dict]:
    return data(c.get(f"{WM}/changes", params={"status": status, "limit": 200}))


def held(c) -> list[tuple]:
    return [(x["id"], x["event_id"], x["status"]) for x in changes(c)]


def test_a_document_added_to_the_lake_is_read_with_recognition_imported_and_applied_by_policy(tmp_path):
    with service(SIGNER, tmp_path, review=None) as c:
        good = console_add(c, OIL_NOTE, "oil.txt")
        assert data(c.get(f"{WM}/documents/{good.id}"))["status"] == "extracted"
        assert data(c.get(f"{WM}/documents/{good.id}/chunks"))[0]["mentions"] == []       # the console knew no names
        assert changes(c) == []
        before = data(c.get(f"{WM}/sync"))
        assert before["enabled"] is False and before["last_tick_at"] is None and before["seen"] == 0
        s = tick(c)
        assert (s["seen"], s["read"], s["waiting"], s["failures"], s["last_error"], s["paused"]) == (1, 1, 0, 0, None, None)
        assert s["imported"] == 1 and s["pending"] == 0 and s["last_tick_at"]
        # recognition: the passages now carry the model's names
        assert any(ch["mentions"] for ch in data(c.get(f"{WM}/documents/{good.id}/chunks")))
        applied = changes(c, "auto_applied")
        assert len(applied) == 1 and all(x["decided_by"]["sub"] == "policy:standards" for x in applied)
        imports = c.app.state.lake.list_imports(ORG)
        assert [(r.by, len(r.item_ids)) for r in imports] == [("lake-sync", 1)]


def test_a_document_the_gate_sends_to_a_person_stays_pending_with_its_reasons_and_the_rest_go_on(tmp_path):
    with service(SIGNER, tmp_path, review=None) as c:
        console_add(c, SPREAD_NOTE, "spreads.txt", "news")          # no publisher: for a person
        console_add(c, RATE_NOTE, "rates.txt", "central_bank")      # well attributed: applied
        s = tick(c)
        assert s["read"] == 2 and s["imported"] >= 2 and s["pending"] >= 1
        pend = changes(c, "pending")
        assert len(pend) == s["pending"] and all(x["review_reasons"] for x in pend)
        assert any("publisher" in r for x in pend for r in x["review_reasons"])
        assert changes(c, "auto_applied")


def test_a_restart_reads_and_imports_nothing_twice(tmp_path):
    with service(SIGNER, tmp_path, review=None) as c:
        console_add(c, OIL_NOTE, "oil.txt")
        console_add(c, SPREAD_NOTE, "spreads.txt", "news")
        first = tick(c)
        assert first["read"] == 2
        total = held(c)
        assert tick(c)["read"] == 2 and tick(c)["skipped"] == 2     # same process: the ledger is in memory
    with service(SIGNER, tmp_path, review=None) as c:               # a restart: the ledger is in the lake
        assert held(c) == total
        s = tick(c, 2)
        assert (s["read"], s["imported"], s["skipped"], s["waiting"]) == (0, 0, 2, 0)
        assert held(c) == total
        assert len(c.app.state.lake.list_imports(ORG)) == 2
        console_add(c, RATE_NOTE, "later.txt")                      # a new one is still picked up
        assert tick(c)["read"] == 1 and len(held(c)) > len(total)


def test_documents_that_were_read_elsewhere_have_no_signal_or_cannot_be_read_are_noted_and_left(tmp_path):
    with service(SIGNER, tmp_path, review=None) as c:
        up = upload(c, NOTE, "api.txt")                             # read against the model on upload: it has mentions
        quiet = console_add(c, b"Notes of the week, October 1, 2026. Nothing about any name the model holds.", "q.txt")
        broken = console_add(c, b"not a pdf at all", "bad.pdf", process=False)       # stored, never read
        gone = console_add(c, b"x" * 40, "excluded.txt", process=False)
        c.app.state.lake.update_document(ORG, gone.id, status="excluded")
        s = tick(c)
        assert s["seen"] == 4 and s["read"] == 2 and s["imported"] == 0 and s["waiting"] == 0
        assert changes(c) == []
        assert data(c.get(f"{WM}/documents/{broken.id}"))["status"] == "failed"
        ledger = {r.key: r.fingerprint for r in (c.app.state.lake.get_idempotency(ORG, "acme_demo", "lake-sync", d)
                                                 for d in (up["document_id"], quiet.id, broken.id, gone.id)) if r}
        assert ledger == {up["document_id"]: "read_elsewhere", quiet.id: "no_signals", broken.id: "failed"}
        s = tick(c)                                                 # none is read again; the failed one is now skipped
        assert (s["read"], s["skipped"]) == (2, 4)
        # deleting a document forgets what the sync did with it
        c.delete(f"{WM}/documents/{quiet.id}")
        assert c.app.state.lake.get_idempotency(ORG, "acme_demo", "lake-sync", quiet.id) is None


def test_a_disabled_sync_does_nothing(tmp_path):
    with service(SIGNER, tmp_path, review=None) as c:
        console_add(c, OIL_NOTE, "oil.txt")
        asyncio.run(c.app.state.lake_sync.tick())
        s = data(c.get(f"{WM}/sync"))
        assert s["enabled"] is False and s["seen"] == 0 and s["read"] == 0 and s["last_tick_at"] is None
        assert changes(c) == [] and c.app.state.lake_sync.task is None


def test_an_unreachable_lake_is_reported_and_backed_off_and_the_app_keeps_serving(tmp_path):
    with service(SIGNER, tmp_path, review=None) as c:
        console_add(c, OIL_NOTE, "oil.txt")
        lk = c.app.state.lake
        real = lk.list_documents

        def down(*a, **k):
            raise ConnectionError("lake unreachable")

        lk.list_documents = down
        try:
            s = tick(c)
            assert s["failures"] == 1 and "ConnectionError: lake unreachable" in s["last_error"] and s["read"] == 0
            assert c.get(WM).status_code == 200 and c.get(f"{WM}/entities").status_code == 200   # still serving
            assert tick(c)["failures"] == 1                          # backed off: the second tick did not try
            c.app.state.lake_sync.models["acme_demo"].retry_at = 0.0
            assert tick(c)["failures"] == 2
        finally:
            lk.list_documents = real
        c.app.state.lake_sync.models["acme_demo"].retry_at = 0.0
        s = tick(c)
        assert (s["failures"], s["last_error"], s["read"], s["imported"]) == (0, None, 1, 1)


def test_the_sync_waits_while_an_update_is_held_for_review_or_another_import_is_starting(tmp_path):
    with service(SIGNER, tmp_path, review="review_all") as c:
        up = upload(c, NOTE, "held.txt")
        propose(c, up["bundle_id"])                                 # review_all: a run now waits for a person
        doc = console_add(c, OIL_NOTE, "oil.txt")
        s = tick(c)
        assert (s["paused"], s["read"], s["waiting"], s["failures"]) == ("update", 0, 1, 0)
        assert data(c.get(f"{WM}/documents/{doc.id}"))["status"] == "extracted"
        assert c.app.state.lake.get_idempotency(ORG, "acme_demo", "lake-sync", doc.id) is None
    with service(SIGNER, tmp_path / "busy", review=None) as c:
        doc = console_add(c, OIL_NOTE, "oil.txt")
        c.app.state.proposing.add("acme_demo")                      # an import is starting
        s = tick(c)
        assert (s["paused"], s["read"], s["waiting"]) == ("busy", 0, 1)
        c.app.state.proposing.discard("acme_demo")
        s = tick(c)
        assert (s["paused"], s["read"], s["waiting"], s["imported"]) == (None, 1, 0, 1)
        assert not c.app.state.proposing


def test_the_background_task_picks_a_document_up_by_itself_and_the_flags_decide_whether_it_runs(tmp_path):
    with service(SIGNER, tmp_path, review=None, WORLD_MODEL_LAKE_SYNC="1", WORLD_MODEL_LAKE_SYNC_SECONDS="0.05") as c:
        sync = c.app.state.lake_sync
        assert sync.enabled and sync.interval == 0.05 and sync.task is not None
        console_add(c, OIL_NOTE, "oil.txt")
        for _ in range(200):
            if data(c.get(f"{WM}/sync"))["imported"]:
                break
            time.sleep(0.05)
        s = data(c.get(f"{WM}/sync"))
        assert s["imported"] == 1 and s["read"] == 1 and s["last_error"] is None
    assert sync.task is None                                        # stopped with the app


def test_the_flags():
    import os

    keep = {k: os.environ.pop(k, None) for k in ("WORLD_MODEL_LAKE_SYNC", "WORLD_MODEL_LAKE_SYNC_SECONDS", "WORLD_MODEL_LAKE_URL")}
    try:
        assert settings_from_env() == (False, 30.0)                 # no lake service: off
        os.environ["WORLD_MODEL_LAKE_URL"] = "http://data.internal"
        assert settings_from_env() == (True, 30.0)                  # the hosted three-service mode: on
        os.environ["WORLD_MODEL_LAKE_SYNC"] = "0"
        assert settings_from_env() == (False, 30.0)
        os.environ["WORLD_MODEL_LAKE_SYNC"] = "yes"
        os.environ["WORLD_MODEL_LAKE_SYNC_SECONDS"] = "5"
        assert settings_from_env() == (True, 5.0)
        assert settings_from_env(False, 1.0) == (False, 1.0)
    finally:
        for k, v in keep.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


def test_a_tenant_larger_than_a_page_is_read_page_by_page(tmp_path, monkeypatch):
    from axelrod_wm.api import lake_sync

    monkeypatch.setattr(lake_sync, "PAGE", 2)
    with service(SIGNER, tmp_path, review=None) as c:
        for i, note in enumerate((OIL_NOTE, RATE_NOTE, SPREAD_NOTE)):
            console_add(c, note, f"n{i}.txt")
        s = tick(c)
        assert (s["seen"], s["read"], s["waiting"]) == (3, 3, 0)
