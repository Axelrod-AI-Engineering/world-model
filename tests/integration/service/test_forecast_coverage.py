"""I3. A simulation that says what its numbers leave out: every uncalibrated relationship the shock reaches
(`unquantified_relationships`) is named again in its calculation coverage as excluded for being uncalibrated, reads as
size-unknown (null, never 0) where the API serves the relationship, and the same coverage reaches the brief and the
v4.1.4 export."""

from __future__ import annotations

import pytest

from tests.integration.service.conftest import SIGNER, WM
from tests.service.helpers import data, service

pytestmark = pytest.mark.integration
SIGN = {"+": "positive", "-": "negative"}


def test_a_simulation_names_its_unquantified_relationships_everywhere_it_is_read():
    with service(SIGNER) as c:
        thesis = data(c.post(f"{WM}/theses", json={"question": "What if the BoJ hiked by 25bp next quarter?"}), 201)
        job = data(c.post(f"{WM}/theses/{thesis['id']}/simulations"), 202)
        sid = job["result"]["ids"][0]
        sim = data(c.get(f"{WM}/simulations/{sid}"))
        cov = data(c.get(f"{WM}/simulations/{sid}/coverage"))
        unq = sim["unquantified_relationships"]
        assert unq, "the BoJ shock reaches uncalibrated relationships in sally_demo"
        excluded = {e["interaction_id"]: e for e in cov["excluded"]}
        for u in unq:
            e = excluded[u["interaction_id"]]
            assert e["reason"] == "uncalibrated" and (e["source"], e["target"]) == (u["source"], u["target"])
            assert e["sign"] == u["sign"] and e["mechanism"] == u["mechanism"]
            # the relationship as the API serves it: a sign, no size, no timing
            rel = data(c.get(f"{WM}/relationships/{u['interaction_id']}"))
            assert rel["calibration"] == "uncalibrated" and rel["effect"] is None and rel["kernel"]["lag_days"] is None
            assert rel["sign"] == SIGN[u["sign"]] and rel["target_attribute_id"] == u["target"]
        assert not set(excluded) & {x["interaction_id"] for x in cov["contributed"]}
        assert cov["summary"]["excluded_by_reason"]["uncalibrated"] >= len(unq)
        partial = [t for t in cov["targets"] if t["routes"] and t["share_quantified"] < 1]
        assert partial                  # some target is reached by a route through a relationship with no size
        assert all(0 <= t["quantified_routes"] <= t["routes"] for t in cov["targets"])

        # the same coverage wherever the simulation is read
        assert data(c.get(f"{WM}/simulations/{sid}/brief"))["coverage"] == cov
        pack = data(c.get(f"{WM}/exports/v4.1.4", params={"simulation": sid}))
        assert pack["forecast"]["calculation_coverage"] == cov
