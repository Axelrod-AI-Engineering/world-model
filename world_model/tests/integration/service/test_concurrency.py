"""I7. Concurrent updates: two proposals sent at the same moment by two callers of one organization. One update runs
and waits for review; the other is refused with `409 update_in_progress`, and goes through once the first is
reviewed. Reads stay answerable while the update waits."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.integration.service.conftest import CUT_NOTE, DOLLAR_NOTE, SIGNER, WM, propose, review_all, upload
from tests.service.helpers import problem, service

pytestmark = pytest.mark.integration


def test_two_proposals_at_once_one_runs_one_is_refused():
    with service(SIGNER) as c:
        a = upload(c, CUT_NOTE, "cut.txt")["bundle_id"]
        b = upload(c, DOLLAR_NOTE, "dollar.txt")["bundle_id"]

        def post(bid: str):
            return c.post(f"{WM}/changes", json={"bundle_id": bid})

        with ThreadPoolExecutor(2) as pool:
            ra, rb = pool.map(post, (a, b))
        (ran, _), (refused, refused_bundle) = sorted([(ra, a), (rb, b)], key=lambda x: x[0].status_code)
        assert ran.status_code == 202 and ran.json()["data"]["status"] == "succeeded"
        assert ran.json()["data"]["result"]["ids"]
        problem(refused, 409, "update_in_progress")
        # reads answer while the update waits for review
        assert c.get(f"{WM}/entities/dollar").status_code == 200 and c.get(WM).status_code == 200

        review_all(c)
        assert propose(c, refused_bundle)["result"]["ids"]
        review_all(c)
