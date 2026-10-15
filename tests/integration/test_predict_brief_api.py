"""Predict's brief (Oct 14): the forecast beside its baseline, the brief's timeline table and rewindable transmission
paths, readers' annotations (logged, never state), and re-running a thesis (the earlier forecast stays)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.repo.snapshots import MemoryBackend


@pytest.fixture(scope="module")
def client():
    app = create_app(scenario="emily_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def posed(client):
    r = client.post("/api/theses/E-T1/pose")
    assert r.status_code == 200, r.text
    return r.json()


def test_each_target_and_group_shows_its_forecast_beside_its_baseline(posed):
    items = [*posed["targets"], *posed["groups"]]
    assert items
    for t in items:
        s = t["split"]
        assert s["baseline"] and s["forecast"]
        lo, hi = s["domain"]
        assert lo <= 0 <= hi
        assert abs(s["baseline_q"][1]) < 1e-6                     # measured from the baseline's median
        assert s["shift"] == pytest.approx(s["forecast_q"][1] - s["baseline_q"][1], abs=1e-3)
        assert s["forecast_q"][0] <= s["forecast_q"][1] <= s["forecast_q"][2]


def test_the_brief_has_a_timeline_table_and_rewindable_transmission_paths(client, posed):
    fid = posed["forecast"]["id"]
    b = client.get(f"/api/forecasts/{fid}/brief").json()
    steps = b["transmission"]["steps"]
    assert steps and steps[0]["order"] == 0                       # step 0 is the shock
    assert [s["order"] for s in steps] == sorted(s["order"] for s in steps)
    known = {v["id"] for s in steps for v in s["values"]}
    for s in steps[1:]:
        for v in s["values"]:
            assert v["from"] and all(f["id"] in known for f in v["from"])   # each step joins what came before
            assert v["onset"] and v["onset_day"] >= 0
    # the same values the grid shows by default
    grid = client.get(f"/api/paths/forecast/{fid}").json()
    assert known == set(grid["values"])
    assert b["timeline"]
    for row in b["timeline"]:
        assert {"onset", "name", "peak", "order", "via"} <= set(row)
        if row["kind"] == "value":
            assert row["order"] >= 1 and len(row["via"]) == row["order"]
    assert [r["onset_day"] for r in b["timeline"]] == sorted(r["onset_day"] for r in b["timeline"])
    assert b["runs"] and b["runs"][-1]["id"] == fid and b["latest_version"] >= b["version"]
    assert b["annotations"] == []


def test_annotations_are_logged_and_never_change_the_model(client, posed):
    fid = posed["forecast"]["id"]
    v = client.get("/api/health").json()["version"]
    state = client.get("/api/state").json()
    a = client.post(f"/api/forecasts/{fid}/annotations", json={"anchor": "section:bottom", "text": "Check against the BoJ minutes."})
    assert a.status_code == 200, a.text
    note = a.json()
    assert note["anchor"] == "section:bottom" and note["forecast_id"] == fid and note["id"].startswith("AN-")
    b = client.post(f"/api/forecasts/{fid}/annotations", json={"anchor": "row:dollar_yen.usd_jpy", "text": "Too fast?"}).json()
    assert [n["id"] for n in client.get(f"/api/forecasts/{fid}/annotations").json()] == [note["id"], b["id"]]
    assert [n["text"] for n in client.get(f"/api/forecasts/{fid}/brief").json()["annotations"]] == [
        "Check against the BoJ minutes.", "Too fast?"]
    assert client.delete(f"/api/forecasts/{fid}/annotations/{b['id']}").status_code == 200
    assert [n["id"] for n in client.get(f"/api/forecasts/{fid}/annotations").json()] == [note["id"]]
    # inference never learns: no version, no state change
    assert client.get("/api/health").json()["version"] == v
    after = client.get("/api/state").json()
    assert after["entities"] == state["entities"] and after["links"] == state["links"]
    # the ledger keeps them as their own kind of record
    from axelrod_wm.repo.ledger import LedgerKind

    ledger = client.app.state.axelrod.controller.engine.ledger
    assert [e.payload["action"] for e in ledger.of_kind(LedgerKind.ANNOTATION)] == ["add", "add", "remove"]
    assert client.post(f"/api/forecasts/{fid}/annotations", json={"text": "  "}).status_code == 409
    assert client.post("/api/forecasts/FC-nope/annotations", json={"text": "x"}).status_code == 404
    assert client.delete(f"/api/forecasts/{fid}/annotations/AN-nope").status_code == 404


def test_rerun_poses_the_same_thesis_again_and_keeps_the_old_forecast(client, posed):
    old = posed["forecast"]
    r = client.post(f"/api/forecasts/{old['id']}/rerun")
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["rerun_of"] == old["id"]
    assert new["forecast"]["thesis_id"] == old["thesis_id"] and new["forecast"]["id"] != old["id"]
    assert new["forecast"]["based_on_version"] == client.get("/api/health").json()["version"]
    assert client.get(f"/api/forecasts/{old['id']}").status_code == 200          # still reachable
    assert {old["id"], new["forecast"]["id"]} <= {f["id"] for f in client.get("/api/forecasts").json()}
    th = client.get(f"/api/theses/{old['thesis_id']}").json()
    assert th["question"] == old["question"] and th["event"]["ops"]
    assert [f["id"] for f in th["forecasts"]][-2:] == [old["id"], new["forecast"]["id"]]
    assert client.post("/api/forecasts/FC-nope/rerun").status_code == 404
    assert client.get("/api/theses/T-nope").status_code == 404
