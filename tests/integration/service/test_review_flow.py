"""I1. A document becomes a reviewed change, end to end: upload a synthetic note, read the bundle it gives, propose its
changes, have a person approve each one, and read the model before and after, pinned. Proves that the note's claim is
not in the model before review, that approval commits a new version naming its reviewer, and that the version before
stays readable."""

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
from tests.service.helpers import data, service

pytestmark = pytest.mark.integration


def test_upload_propose_review_and_read_before_and_after():
    with service(SIGNER) as c:
        start = version(c)
        brent0 = attribute(c, "oil", "brent")["data"]

        # 1. the upload: stored, parsed, read into a bundle; nothing in the model moves
        res = upload(c, RATES_NOTE, "2026-09-01_data.txt", source="Data desk", source_type="data")
        assert res["new"] and res["status"] == "extracted" and res["bundle_id"]
        items = data(c.get(f"{WM}/bundles/{res['bundle_id']}/items"))
        assert "oil.brent" in {s.get("value_of") for item in items for s in item["signals"]}
        assert version(c)["number"] == start["number"]

        # 2. the proposal: changes wait; the update may close the days before the note's, but the note's level is not
        #    in the model until a person approves it
        job = propose(c, res["bundle_id"])
        assert job["result"]["ids"] and job["result"]["detail"]["version_before"] == start["number"]
        waiting = attribute(c, "oil", "brent")["data"]
        assert abs(waiting["level"]["mean"] - brent0["level"]["mean"]) < 0.25 * abs(103 - brent0["level"]["mean"])
        pending = data(c.get(f"{WM}/changes"))
        assert pending and all(ch["proposed_by"]["sub"] == "tester" for ch in pending)

        # 3. review: each change approved by a person (a core-web token), against the version reviewed
        decided = review_all(c, note="matches the release")
        assert decided and all(d["decided_by"]["sub"] == "org_user_9" and d["decided_by"]["kind"] == "token"
                               for d in decided)
        after = version(c)
        assert after["number"] > start["number"] and after["state_hash"] != start["state_hash"]
        history = {ch["id"]: ch for ch in data(c.get(f"{WM}/changes", params={"status": "approved", "limit": 200}))}
        assert all(history[d["change_id"]]["version_after"] for d in decided)
        assert all(history[d["change_id"]]["decided_by"]["azp"] == "core-web" for d in decided)

        # 4. the change, and the state before it, pinned
        now = attribute(c, "oil", "brent")
        then = attribute(c, "oil", "brent", version=start["number"])
        assert then["data"] == brent0 and then["meta"]["version"]["state_hash"] == start["state_hash"]
        assert now["data"]["observed"] and abs(now["data"]["level"]["mean"] - 103) < abs(brent0["level"]["mean"] - 103)
        g_then = data(c.get(f"{WM}/graph", params={"attributes": "oil.brent", "depth": 1, "version": start["number"]}))
        g_now = data(c.get(f"{WM}/graph", params={"attributes": "oil.brent", "depth": 1}))
        assert {r["id"] for r in g_then["relationships"]} <= {r["id"] for r in g_now["relationships"]}
        # by date: the day before the note closed without it
        dated = attribute(c, "oil", "brent", as_of="2026-08-31T23:59:59Z")
        assert dated["meta"]["version"]["number"] < min(history[d["change_id"]]["version_after"] for d in decided)
        moved = abs(now["data"]["level"]["mean"] - brent0["level"]["mean"])
        assert abs(dated["data"]["level"]["mean"] - brent0["level"]["mean"]) < moved

        # 5. what the document left behind: searchable, and its bundle proposed once
        hits = data(c.get(f"{WM}/search", params={"q": "Brent crude", "mode": "keyword"}))
        assert hits and hits[0]["document_id"] == res["document_id"]
        again = propose(c, res["bundle_id"])
        assert again["result"]["ids"] == [] and version(c)["number"] == after["number"]


def test_a_rejected_change_leaves_the_model_where_it_was():
    with service(SIGNER) as c:
        start = version(c)
        brent0 = attribute(c, "oil", "brent")["data"]
        res = upload(c, RATES_NOTE, "2026-09-01_data.txt")
        propose(c, res["bundle_id"])
        rejected = review_all(c, approve=False, note="the number is a typo")
        assert rejected and all(d["status"] == "rejected" and d["note"] == "the number is a typo" for d in rejected)
        assert attribute(c, "oil", "brent")["data"]["level"]["mean"] == pytest.approx(brent0["level"]["mean"], rel=0.05)
        assert version(c)["number"] >= start["number"]
