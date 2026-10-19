"""I4. A restart, as a deploy restarts: a second service on the same snapshot and lakehouse directories.

What it proves today:
- The lakehouse survives whole: documents, their text, chunks and raw bytes, bundles, the audit log, the world model
  registry, and search.
- The model does not: a service loads its scenario from the initial snapshot and resets the snapshot store
  (sim/runner.py, `_session_storage`), so the versions committed before the restart are gone (404 version_not_found).
- Replaying the stored bundle, with the same decisions, reproduces the lost state exactly: the same version and state
  hash. The lakehouse's bundles and its audit log of decisions are therefore enough to rebuild the model.

When versions should survive a restart, the second half of this test changes to expect them; the replay check stays.
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
        "hits": data(c.get(f"{WM}/search", params={"q": "Brent crude", "mode": "keyword"})),
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
        brent = attribute(c, "oil", "brent")["data"]
        kept = kept_of(c, res)
        assert moved["number"] > start["number"] and kept["counts"] == {"documents": 1, "bundles": 1}
        assert {a["route"].rsplit("/", 1)[-1] for a in kept["audit"]} >= {"documents", "changes", "approvals"}

    with service(SIGNER, tmp_path) as c:
        # the lakehouse: all of it, unchanged
        assert kept_of(c, res) == kept and kept["raw"] == RATES_NOTE
        assert [m.id for m in c.app.state.lake.world_models()] == ["sally_demo"]
        again = upload(c, RATES_NOTE, "2026-09-01_data.txt")
        assert again["new"] is False and again["bundle_id"] == res["bundle_id"]

        # the model: back at its initial state; the versions before the restart are gone
        now = version(c)
        assert (now["number"], now["state_hash"]) == (start["number"], start["state_hash"])
        problem(c.get(f"{WM}/versions/{moved['number']}"), 404, "version_not_found")
        problem(c.get(f"{WM}/graph", params={"entities": "oil", "version": moved["number"]}), 404, "version_not_found")

        # a replay of the stored bundle, with the same decisions, rebuilds the same state, exactly
        propose(c, res["bundle_id"])
        review_all(c, note="matches the release")
        replay = version(c)
        assert (replay["number"], replay["state_hash"]) == (moved["number"], moved["state_hash"])
        assert attribute(c, "oil", "brent")["data"] == brent
