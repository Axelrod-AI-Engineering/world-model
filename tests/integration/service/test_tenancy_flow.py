"""I6. Two organizations through the whole flow, side by side: each uploads, proposes, reviews, simulates, and reads
its own world model, and neither ever sees the other's world model, documents, bundles, changes, simulations, versions,
or audit log (each is 404 to the other). The same file in both is the same document and bundle id (content hashes),
held twice, proposed independently."""

from __future__ import annotations

import pytest

from tests.integration.service.conftest import (
    CUT_NOTE,
    DOLLAR_NOTE,
    RATES_NOTE,
    SIGNER,
    attribute,
    propose,
    review_all,
    upload,
    version,
)
from tests.service.helpers import data, problem, service

pytestmark = pytest.mark.integration
KA, KB = "a" * 32, "b" * 32
SCOPES = "world_model:read+documents:create+changes:create+simulations:create+admin"
A = {"Authorization": f"Bearer {KA}"}
BB = {"Authorization": f"Bearer {KB}"}
ENV = {"WORLD_MODEL_BASIC_AUTH_USERNAME": "admin", "WORLD_MODEL_BASIC_AUTH_PASSWORD": "pw-admin",
       "WORLD_MODEL_LOGINS": "bravo:pw-bravo:acme_demo",
       "WORLD_MODEL_API_KEYS": f"alpha:{KA}:admin:{SCOPES},beta:{KB}:bravo:{SCOPES}"}
WA, WB = "/v1/world-models/acme_demo", "/v1/world-models/bravo-acme_demo"


def flow(c, wm: str, h: dict, org: str, note: bytes, name: str) -> dict:
    """One organization's flow: upload, propose, a person approves, simulate. What it made."""
    before = version(c, wm, h)
    res = upload(c, note, name, wm, h)
    job = propose(c, res["bundle_id"], wm, h)
    decided = review_all(c, wm, h, org=org)
    thesis = data(c.post(f"{wm}/theses", json={"template_id": "S-T3", "horizon_days": 60}, headers=h), 201)
    sim = data(c.post(f"{wm}/theses/{thesis['id']}/simulations", headers=h), 202)["result"]["ids"][0]
    return {"before": before, "after": version(c, wm, h), "doc": res["document_id"], "bundle": res["bundle_id"],
            "changes": [d["change_id"] for d in decided], "simulation": sim, "job": job["id"]}


def test_two_organizations_never_see_each_other_through_the_whole_flow():
    with service(SIGNER, headers={"Authorization": ""}, **ENV) as c:
        assert [m["id"] for m in data(c.get("/v1/world-models", headers=A))] == ["acme_demo"]
        assert [m["id"] for m in data(c.get("/v1/world-models", headers=BB))] == ["bravo-acme_demo"]
        a = flow(c, WA, A, "admin", RATES_NOTE, "alpha_rates.txt")
        b_start = version(c, WB, BB)
        assert (b_start["number"], b_start["state_hash"]) == (a["before"]["number"], a["before"]["state_hash"])
        b = flow(c, WB, BB, "bravo", DOLLAR_NOTE, "beta_dollar.txt")

        for mine, theirs, wm, other_wm, h, org in ((a, b, WA, WB, A, "admin"), (b, a, WB, WA, BB, "bravo")):
            # the other organization's world model, by any route, is not there
            for path in ("", "/documents", f"/documents/{theirs['doc']}", f"/bundles/{theirs['bundle']}",
                         f"/changes/{theirs['changes'][0]}", f"/simulations/{theirs['simulation']}",
                         f"/jobs/{theirs['job']}", "/audit-events"):
                problem(c.get(other_wm + path, headers=h), 404, "world_model_not_found")
            problem(c.post(f"{other_wm}/changes", json={"bundle_id": theirs["bundle"]}, headers=h), 404,
                    "world_model_not_found")
            # nor in its own: their ids name nothing here
            assert theirs["doc"] not in {d["id"] for d in data(c.get(f"{wm}/documents", headers=h))}
            problem(c.get(f"{wm}/documents/{theirs['doc']}", headers=h), 404, "document_not_found")
            problem(c.get(f"{wm}/bundles/{theirs['bundle']}", headers=h), 404, "bundle_not_found")
            listed = {ch["id"]: ch for ch in data(c.get(f"{wm}/changes", params={"status": "all", "limit": 200},
                                                        headers=h))}
            assert set(mine["changes"]) <= set(listed)
            assert all(listed[x]["decided_by"]["org"] == org for x in mine["changes"])
            assert mine["simulation"] in {s["id"] for s in data(c.get(f"{wm}/simulations", headers=h))}
            assert version(c, wm, h)["number"] == mine["after"]["number"]
            audit = data(c.get(f"{wm}/audit-events", params={"limit": 200}, headers=h))
            assert audit and all(r["actor"]["org"] == org for r in audit)
            # a person of one organization cannot decide in the other's
            tag = c.get(wm, headers=h).headers["etag"]
            problem(c.post(f"{other_wm}/changes/{theirs['changes'][0]}/approvals", json={},
                           headers={**SIGNER.bearer(org=org), "If-Match": tag}), 404, "world_model_not_found")

        # alpha's note moved alpha's crude price and not bravo's; bravo's moved bravo's dollar index and not alpha's
        crude_a, crude_b = (attribute(c, "crude_oil", "price", wm, h)["data"]["level"]["mean"] for wm, h in ((WA, A), (WB, BB)))
        dollar_a, dollar_b = (attribute(c, "dollar", "index", wm, h)["data"]["level"]["mean"]
                        for wm, h in ((WA, A), (WB, BB)))
        assert abs(crude_a - 103) < abs(crude_b - 103) and abs(dollar_b - 104) < abs(dollar_a - 104)

        # one file in both: the same ids, two copies, two independent proposals
        same_a = upload(c, CUT_NOTE, "cut.txt", WA, A)
        same_b = upload(c, CUT_NOTE, "cut.txt", WB, BB)
        assert same_a["new"] and same_b["new"]
        assert (same_a["document_id"], same_a["bundle_id"]) == (same_b["document_id"], same_b["bundle_id"])
        assert propose(c, same_a["bundle_id"], WA, A)["result"]["ids"]
        assert data(c.get(f"{WB}/changes", headers=BB)) == []
