"""I4. A restart, as a deploy restarts: a second service on the same snapshot and lakehouse directories.

What it proves:
- The lakehouse survives whole: documents, their text, chunks and raw bytes, bundles, the audit log, the world model
  registry, idempotency keys and jobs (kept forever), and search.
- The model survives too (Oct 25, unified-model.md): the service resumes from its snapshot store at the version it
  stopped at, with the versions before the restart still readable.
- Without its snapshot store, replaying the stored bundle with the same decisions reproduces the state exactly: the
  same version and state hash. The lakehouse's bundles and its audit log of decisions are enough to rebuild the model.
"""

from __future__ import annotations

import pytest

from tests.integration.service.conftest import (
    RATES_NOTE,
    SIGNER,
    WM,
    attribute,
    propose,
    review_all,
    upload,
    version,
)
from tests.service.helpers import data, problem, service

pytestmark = pytest.mark.integration
ADMIN = {"Authorization": "Bearer " + "k" * 32}


def kept_of(c, res) -> dict:
    doc = f"{WM}/documents/{res['document_id']}"
    return {
        "doc": data(c.get(doc)),
        "text": data(c.get(f"{doc}/content")),
        "chunks": data(c.get(f"{doc}/chunks")),
        "raw": c.get(f"{doc}/content", params={"format": "raw"}).content,
        "bundle": data(c.get(f"{WM}/bundles/{res['bundle_id']}")),
        "items": data(c.get(f"{WM}/bundles/{res['bundle_id']}/items")),
        "hits": data(c.get(f"{WM}/search", params={"q": "crude price", "mode": "keyword"})),
        "counts": {k: v for k, v in data(c.get(WM))["counts"].items() if k in ("documents", "bundles")},
        "audit": data(c.get(f"{WM}/audit-events", params={"limit": 200}, headers=ADMIN)),
    }


def test_the_lakehouse_survives_a_restart_and_a_replay_rebuilds_the_model(tmp_path):
    with service(SIGNER, tmp_path) as c:
        start = version(c)
        res = upload(c, RATES_NOTE, "2026-09-01_data.txt", source="Data desk")
        propose(c, res["bundle_id"])
        review_all(c, note="matches the release")
        moved = version(c)
        crude = attribute(c, "crude_oil", "price")["data"]
        keyed = c.post(f"{WM}/documents", files=[("files", ("keyed.txt", b"Oct 9, 2026. The central bank held.", "text/plain"))],
                       headers={"Idempotency-Key": "restart-1"})
        assert keyed.status_code == 202
        kept = kept_of(c, res)
        assert moved["number"] > start["number"] and kept["counts"] == {"documents": 2, "bundles": 2}
        assert {a["route"].rsplit("/", 1)[-1] for a in kept["audit"]} >= {"documents", "changes", "approvals"}

    with service(SIGNER, tmp_path) as c:
        # the lakehouse: all of it, unchanged
        assert kept_of(c, res) == kept and kept["raw"] == RATES_NOTE
        assert [m.id for m in c.app.state.lake.world_models()] == ["acme_demo"]
        # idempotency keys and jobs are permanent: the same key, and the same content, get the first answers
        replayed = c.post(f"{WM}/documents", files=[("files", ("keyed.txt", b"Oct 9, 2026. The central bank held.",
                                                                "text/plain"))], headers={"Idempotency-Key": "restart-1"})
        assert replayed.json() == keyed.json() and replayed.headers["location"] == keyed.headers["location"]
        assert data(c.get(keyed.headers["location"]))["status"] == "succeeded"
        problem(c.post(f"{WM}/documents", files=[("files", ("other.txt", b"Other.", "text/plain"))],
                       headers={"Idempotency-Key": "restart-1"}), 422, "idempotency_key_reused")
        again = upload(c, RATES_NOTE, "2026-09-01_data.txt")
        assert again["new"] is True and again["bundle_id"] == res["bundle_id"]     # the first upload's answer

        # the model: resumed at the version it stopped at, its earlier versions still readable
        now = version(c)
        assert (now["number"], now["state_hash"]) == (moved["number"], moved["state_hash"])
        assert data(c.get(f"{WM}/versions/{moved['number']}"))["number"] == moved["number"]
        assert attribute(c, "crude_oil", "price")["data"] == crude

    # without the snapshot store, a replay of the stored bundle, with the same decisions, rebuilds the same state
    (tmp_path / "snapshots").rename(tmp_path / "snapshots.gone")
    with service(SIGNER, tmp_path) as c:
        fresh = version(c)
        assert (fresh["number"], fresh["state_hash"]) == (start["number"], start["state_hash"])
        propose(c, res["bundle_id"])
        review_all(c, note="matches the release")
        replay = version(c)
        assert (replay["number"], replay["state_hash"]) == (moved["number"], moved["state_hash"])
        assert attribute(c, "crude_oil", "price")["data"] == crude
