"""A compartment login on the persistent unified engine (Oct 25): what a view needs to see again after a restart, who may
reset the unified model, and the standards gate on a compartment's imports."""

from __future__ import annotations

import time

import pytest

from tests.integration.service.conftest import SIGNER
from tests.integration.service.test_compartment_logins import ENV, MAIN, NW, NW_OWN, WN, U, data, sign_in
from tests.service.helpers import service

pytestmark = pytest.mark.integration
ENV_GHOST = {**ENV, "WORLD_MODEL_LOGINS": ENV["WORLD_MODEL_LOGINS"] + ",ghost:pw-ghost:no_such_scenario"}


def bundle(item_id: str, day: int, **extra) -> dict:
    return {"format": "axelrod.import/v1", "title": "Jet fuel (synthetic)", "collected_by": "test", "synthetic": True,
            "items": [{"id": item_id, "published_at": f"2026-09-{day}T10:00:00Z", "source": "Synthetic regulator",
                       "source_type": "central_bank", "kind": "data", "headline": "Jet fuel rises",
                       "summary": "Jet fuel rose to 2.9 a gallon.", "entities": ["jet_fuel"], "relevance": 0.8,
                       "signals": [{"type": "observe", "value_of": "jet_fuel.price", "value": 2.9}], **extra}]}


def settle(c) -> dict:
    t0 = time.time()
    while time.time() - t0 < 60:
        st = c.get("/api/sim/status").json()
        if st["state"] != "running":
            return st
        time.sleep(0.1)
    raise AssertionError("still running")


def pending(c) -> list[str]:
    return [p["proposal"]["id"] for p in c.get("/api/proposals?status=pending").json()]


def test_a_compartment_sees_its_pending_proposal_again_after_a_restart_and_can_approve_it(tmp_path):
    with service(SIGNER, tmp_path, scenario="unified_demo", **ENV) as c:
        sign_in(c, "nw")
        out = c.post("/api/import", json={"bundle": bundle("R-1", 13)}).json()      # no document named: it waits for review
        assert settle(c)["pending_proposals"] == 1
        pid = out["waiting_on"]
        assert pending(c) == [pid]
        version = c.get(WN, headers=NW).headers["etag"]

    with service(SIGNER, tmp_path, scenario="unified_demo", **ENV) as c:
        assert c.app.state.axelrod.runner.controller.proposals[pid].status == "pending"
        sign_in(c, "nw")
        assert pending(c) == [pid] and settle(c)["pending_proposals"] == 1
        assert [e["id"] for e in c.get("/api/market-events").json()] == ["IM-R-1"]
        assert c.get(WN, headers=NW).headers["etag"] == version
        sign_in(c, "acme")
        assert pending(c) == [] and c.get("/api/market-events").json() == []
        assert c.post(f"/api/proposals/{pid}/approve", json={"by": "acme"}).status_code == 409
        sign_in(c, "admin")
        assert pending(c) == [pid]                              # the main login sees the whole queue
        sign_in(c, "nw")
        done = c.post(f"/api/proposals/{pid}/approve", json={"by": "nw person"})
        assert done.status_code == 200 and done.json()["proposal"]["status"] == "approved"
        assert settle(c)["state"] == "idle" and pending(c) == []

    with service(SIGNER, tmp_path, scenario="unified_demo", **ENV) as c:      # and a decided proposal stays decided
        sign_in(c, "nw")
        assert pending(c) == []
        assert [p["proposal"]["status"] for p in c.get("/api/proposals").json()] == ["approved"]


def test_only_internal_staff_reset_the_unified_model(tmp_path):
    with service(SIGNER, tmp_path, scenario="unified_demo", **ENV_GHOST) as c:
        sign_in(c, "nw")
        c.post("/api/import", json={"bundle": bundle("R-2", 14)})
        settle(c)
        main = c.app.state.axelrod
        # a compartment's login cannot, and neither can an account that merely opens the main engine
        for user in ("nw", "acme"):
            sign_in(c, user)
            assert c.post("/api/sim/reset-all").status_code == 409 and c.post("/api/sim/reset").status_code == 409
        sign_in(c, "ghost")
        assert c.post("/api/sim/reset-all").status_code == 403 and c.post("/api/sim/reset").status_code == 403
        assert len(main.runner.controller.pending_proposals()) == 1
        # the main login can: every account's imported state goes
        sign_in(c, "admin")
        assert c.post("/api/sim/reset-all").status_code == 200
        assert main.runner.controller.proposals == {}
        assert c.post("/api/sim/reset").status_code == 200


def test_a_well_attributed_item_from_a_compartment_is_applied_by_the_standards_gate(tmp_path):
    with service(SIGNER, tmp_path, scenario="unified_demo", review=None, **ENV) as c:
        assert c.app.state.axelrod.runner.controller.config.review.policy == "standards"
        sign_in(c, "nw")
        ok = bundle("R-3", 15, document="Statement 7", coverage="full", plausible=True, confidence=0.8)
        before = c.get(f"{WN}/entities/jet_fuel/attributes/price", headers=NW).json()["data"]["level"]["mean"]
        out = c.post("/api/import", json={"bundle": ok})
        assert out.status_code == 200 and out.json()["state"] == "done" and out.json()["waiting_on"] is None
        assert settle(c)["pending_proposals"] == 0 and pending(c) == []
        applied = [p for p in c.get("/api/proposals").json()]
        assert [p["proposal"]["status"] for p in applied] == ["auto_applied"]
        assert applied[0]["proposal"]["decided_by"] == "policy:standards"
        # applied on the main engine, and visible in this compartment
        main = c.app.state.axelrod.runner.controller
        assert [str(p.status) for p in main.proposals.values()] == ["auto_applied"]
        assert c.get(f"{WN}/entities/jet_fuel/attributes/price", headers=NW).json()["data"]["level"]["mean"] != before
        assert data(c.get(U + "/entities/jet_fuel/attributes/price", headers=MAIN))["level"]["mean"] != before
        assert {e["id"] for e in c.get("/api/state").json()["entities"]} == NW_OWN
