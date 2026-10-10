"""The API on the small demo (Oct 8 restructure): the flowchart and its stage flowcharts, contracts, the examples
(a chain with rewind) and the library, the staged review with selective approval, the commit log, and structure
edits."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.repo.snapshots import MemoryBackend


@pytest.fixture(scope="module")
def client():
    app = create_app(scenario="small_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        yield c


def settle(client: TestClient, timeout: float = 60.0) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = client.get("/api/sim/status").json()
        if st["state"] != "running":
            return st
        time.sleep(0.1)
    raise AssertionError("the demo kept running")


def test_flowchart_and_contracts(client):
    flows = {f["id"]: f for f in client.get("/api/flows").json()}
    phases = flows["world-model"]["phases"]
    assert [p["id"] for p in phases] == ["intake", "working", "long_term", "review", "commit"]
    assert [p["id"] for p in flows["inference"]["phases"]][0] == "pose" and "inf-score" in flows
    assert all(p["input"] and p["output"] and p["flow"] in flows for p in phases)
    svg = client.get("/api/flows/stage-review/svg?bare=true")
    assert svg.status_code == 200 and 'data-node="restage"' in svg.text and "fl-title" not in svg.text.split("<style>")[0]
    assert client.get("/api/flows/nope/svg").status_code == 404
    slots = {c["slot"] for c in client.get("/api/contracts").json()}
    assert {"parser", "folder", "inducer", "review_policy", "unifier", "storage"} <= slots


def test_the_small_demo_starts_blank(client):
    st = client.get("/api/sim/status").json()
    assert st["canvas"] == "blank" and st["examples"] == "small"
    assert client.get("/api/state").json()["entities"] == []
    ex = client.get("/api/examples").json()
    assert [x["id"] for x in ex][:4] == ["create", "links", "refine", "ripple"]
    assert ex[3]["plays_first"] == 3 and ex[3]["status"] == "ready" and ex[3]["steps"][0]["article"]["headline"]
    assert {m["id"] for m in ex[3]["more"]} >= {"oil-falls", "fuel-spike"}


def test_run_stage_select_and_approve(client):
    out = client.post("/api/examples/select").json()
    pid = out["proposal_id"]
    assert out["played"] == ["create", "links", "refine", "ripple", "expert_add"] and out["proposal"]["proposal"]["status"] == "pending"
    assert settle(client)["state"] == "awaiting_review"
    assert client.post("/api/examples/fold").status_code == 409       # one example waits for review at a time
    full = client.get(f"/api/proposals/{pid}/stage").json()
    assert len(full["items"]) == 7 and full["graph"]["entities"]
    assert full["article"]["spans"] and full["stages"][3]["status"] == "waiting"
    some = client.get(f"/api/proposals/{pid}/stage?keep=0,1,4&graph=false").json()
    assert some["keep"] == [0, 1, 4] and some["graph"] is None
    live = {e["id"] for e in client.get("/api/state").json()["entities"]}
    assert live == {"resources_energy", "delta", "air_travel"}      # staging changed nothing
    r = client.post(f"/api/proposals/{pid}/approve", json={"by": "backend user", "keep": [0, 1, 4]})
    assert r.status_code == 200
    for _ in range(100):
        ents = {e["id"] for e in client.get("/api/state").json()["entities"]}
        if "inflation" in ents:
            break
        time.sleep(0.1)
    assert "inflation" in ents and "federal_reserve" not in ents
    settle(client)
    done = {x["id"]: x["status"] for x in client.get("/api/examples").json()}
    assert done["select"] == "done" and done["create"] == "done"


def test_a_library_event_and_a_rewind(client):
    out = client.post("/api/library/oil-falls").json()
    assert out["proposal_id"] and not out["played"]
    client.post(f"/api/proposals/{out['proposal_id']}/reject", json={"by": "backend user", "note": "not today"})
    back = client.post("/api/examples/ripple").json()
    assert back["rewound"] and back["proposal_id"]
    ex = client.get("/api/examples").json()
    assert [x["status"] for x in ex][:5] == ["done", "done", "done", "waiting", "ready"]
    client.post(f"/api/proposals/{back['proposal_id']}/approve", json={"by": "backend user"})
    settle(client)


def test_a_thesis_example_returns_its_question(client):
    out = client.post("/api/examples/inference").json()
    assert out["proposal_id"] is None and "oil" in out["question"].lower()


def test_structure_edits_wait_for_review(client):
    r = client.post("/api/structure/retire", json={"interaction_id": "nope", "reason": "x"})
    assert r.status_code == 422
    links = client.get("/api/state").json()["links"]
    lid = next(l["id"] for l in links if l["target"] == "delta.fuel_cost")
    pv = client.post("/api/structure/retire", json={"interaction_id": lid, "reason": "test", "by": "backend user"}).json()
    pid = pv["proposal"]["id"]
    assert pv["proposal"]["status"] == "pending"
    staged = client.get(f"/api/proposals/{pid}/stage?graph=false").json()
    assert staged["marks"]["retired"] == [lid] and staged["items"][0]["action"] == "retire"
    client.post(f"/api/proposals/{pid}/reject", json={"by": "backend user", "note": "keep it"})
    assert any(l["id"] == lid for l in client.get("/api/state").json()["links"])


def test_the_log_show_and_diff(client):
    commits = client.get("/api/repo/log?limit=40").json()
    assert commits and commits[0]["version"] == client.get("/api/health").json()["version"]
    working = client.get("/api/repo/log?limit=40&process=learn.working").json()
    assert working and all(c["process"] == "learn.working" for c in working)
    vetted = {c["vetted_by"] for c in working}
    assert "backend user" in vetted and "demo setup" in vetted
    one = client.get(f"/api/repo/commits/{working[0]['version']}").json()
    assert one["commit"]["process"] == "learn.working"
    d = client.get(f"/api/repo/diff?from={working[-1]['version'] - 1}").json()
    assert d["commits"] >= 1 and d["changes"]


def test_reset_returns_a_blank_canvas(client):
    client.post("/api/sim/reset")
    assert client.get("/api/state").json()["entities"] == []
    assert all(x["status"] == "ready" for x in client.get("/api/examples").json())


def test_anyone_can_add_from_their_own_knowledge(client):
    vocab = client.get("/api/vocabulary").json()
    assert any(k["id"] == "traffic_flow" for k in vocab["attribute_kinds"]) and "company" in vocab["entity_kinds"]
    spec = {"entity": {"id": "rail", "name": "Rail freight", "kind": "market", "tags": ["SC"]},
            "values": [{"slug": "carloads", "name": "Rail carloads", "attribute_kind": "traffic_flow", "unit": "k/week",
                        "family": "lognormal", "typical": 250.0, "spread": 0.05}],
            "interactions": [], "confidence": 0.6, "note": "Freight volumes lead the cycle."}
    pv = client.post("/api/manual", json={"manual": spec, "by": "backend user"}).json()
    pid = pv["proposal"]["id"]
    staged = client.get(f"/api/proposals/{pid}/stage?graph=false").json()
    assert staged["manual"]["note"] == "Freight volumes lead the cycle." and staged["confidence"] == 0.6
    assert client.post("/api/manual", json={"manual": {}}).status_code == 422
    client.post(f"/api/proposals/{pid}/reject", json={"by": "backend user", "note": "test only"})
