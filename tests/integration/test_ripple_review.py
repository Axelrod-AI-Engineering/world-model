"""The ripple in review (Oct 9): it is not in the article, but it moves working memory day by day, so the reviewer can
deselect a value's ripple or give the probability it arrives, and the approval stores that judgment."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.dynamics.daily import in_channel_index, predict_state
from axelrod_wm.dynamics.regressors import clip_of
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


def test_a_reviewer_weighs_the_ripple(client):
    pid = client.post("/api/examples/ripple").json()["proposal_id"]
    settle(client)
    full = client.get(f"/api/proposals/{pid}/stage?graph=false").json()
    ripple = [a for a in full["ripple"] if a["order"] >= 1]
    assert ripple and all(a["weight"] == 1.0 for a in ripple)
    first = ripple[0]["subentity_id"]
    later = [a for a in ripple if first in a["hops"][:-1]]
    # deselecting a value's ripple (probability 0) shows on that value, and nothing live changes
    some = client.get(f"/api/proposals/{pid}/stage?graph=false&ripple={first}:0.5").json()
    weights = {a["subentity_id"]: a["weight"] for a in some["ripple"]}
    assert weights[first] == 0.5 and all(weights[a["subentity_id"]] == 1.0 for a in later)
    ctl = client.app.state.axelrod.controller
    assert not ctl.engine.wm.ripple_judgments
    # approved with the weight, the judgment is stored when the event folds on its day
    r = client.post(f"/api/proposals/{pid}/approve", json={"by": "backend user", "ripple": {first: 0.0}})
    assert r.status_code == 200
    settle(client)
    wm = ctl.engine.wm
    for _ in range(100):
        if wm.ripple_judgments:
            break
        time.sleep(0.1)
        wm = ctl.engine.wm
    js = [j for j in wm.ripple_judgments.values() if j.subentity_id == first]
    assert len(js) == 1 and js[0].weight == 0.0 and any(abs(x) > 0 for x in js[0].path)
    # the daily prediction takes the expected ripple back out of that value
    j = js[0]
    k = max(range(len(j.path)), key=lambda t: abs(j.path[t]))
    sub = wm.graph.subentities[first]
    ctx = ctl.engine.context(learn=False, now=ctl.now)
    with_j = predict_state(sub, in_channel_index(wm.graph).get(first, []), wm, j.start_day + k, clip_of(ctx)).z
    saved = dict(wm.ripple_judgments)
    wm.ripple_judgments.clear()
    try:
        without = predict_state(sub, in_channel_index(wm.graph).get(first, []), wm, j.start_day + k, clip_of(ctx)).z
    finally:
        wm.ripple_judgments.update(saved)
    assert with_j == pytest.approx(without - j.path[k])
