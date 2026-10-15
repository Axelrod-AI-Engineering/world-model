"""The canvas's questions (Oct 9) on the small demo: every node's open node, what is being checked and how, and find as
a semantic filter over nodes and edges."""

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
        c.post("/api/examples/frontier")
        t0 = time.time()
        while c.get("/api/sim/status").json()["state"] == "running" and time.time() - t0 < 300:
            time.sleep(0.2)
        yield c


def test_every_node_carries_an_open_node(client):
    v = client.get("/api/state").json()
    assert all(0.0 <= x["open"] <= 1.0 for x in v["entities"] + v["subentities"] + v["hulls"])
    subs = {s["id"]: s["open"] for s in v["subentities"]}
    # nothing in the graph drives oil; oil drives Delta's fuel cost almost entirely
    assert subs["resources_energy.oil_price"] == pytest.approx(1.0)
    assert subs["delta.fuel_cost"] < 0.3
    tax = client.get("/api/taxonomies/object").json()["nodes"]
    for n in tax:
        assert n["open"] == pytest.approx(1.0 / (n["support"] + 1.0), abs=1e-3)


def test_checks_say_when_how_and_what_they_update(client):
    c = client.get("/api/checks").json()
    ids = [x["id"] for x in c["catalog"]]
    assert ids == ["hedge", "existence", "frontier", "superentity", "kinds"]
    assert all(x["when"] and x["how"] and x["updates"] and x["bound"] for x in c["catalog"])
    kinds = {x["kind"] for x in c["live"]}
    assert {"hedge", "frontier"} <= kinds
    for x in c["live"]:
        assert x["progress"] and all({"what", "value", "bound"} <= set(m) for m in x["progress"]) and x["next"]


def test_find_filters_nodes_and_edges_by_meaning(client):
    def hits(q):
        return client.get("/api/find", params={"q": q}).json()

    airline = hits("airline")
    ents = {h["id"] for h in airline["hits"] if h["kind"] == "entity"}
    assert {"delta", "skybridge"} <= ents and all("concept" in h["why"] for h in airline["hits"] if h["id"] in ("delta", "skybridge"))
    rates = hits("rates")
    assert any(h["id"] == "federal_reserve.policy_rate" for h in rates["hits"])
    assert any(h["kind"] == "interaction" for h in rates["hits"])
    learned = hits("learned")
    assert learned["hits"] and all(h["kind"] == "interaction" for h in learned["hits"])
    blind = hits("open>0.9")
    assert any(h["id"] == "resources_energy" for h in blind["hits"])
    assert not hits("zzzz")["hits"]


def test_superentities_nest_and_the_path_names_each_level(client):
    for pv in client.get("/api/proposals", params={"status": "pending"}).json():
        client.post(f"/api/proposals/{pv['proposal']['id']}/approve", json={"by": "backend user"})
    out = client.post("/api/examples/nest").json()
    t0 = time.time()
    while client.get("/api/sim/status").json()["state"] == "running" and time.time() - t0 < 300:
        time.sleep(0.2)
    pid = out["proposal_id"]
    assert client.post(f"/api/proposals/{pid}/approve", json={"by": "backend user"}).status_code == 200
    for _ in range(100):
        hulls = {h["pattern_id"]: h for h in client.get("/api/state").json()["hulls"]}
        if "SE-NEST" in hulls:
            break
        time.sleep(0.1)
    nest = hulls["SE-NEST"]
    kids = {h["id"]: h for h in hulls.values() if h["id"] in nest["child_instance_ids"]}
    assert len(kids) == 2 and "SE-POLICY" in {h["pattern_id"] for h in kids.values()}
    assert {"federal_reserve", "inflation", "resources_energy", "delta"} <= set(nest["members"])
