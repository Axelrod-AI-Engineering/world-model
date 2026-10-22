"""A raw document through ingestion, drawn as the graph update it would make (api/ingest_view.py, routes.py): uploaded
or picked from the lakehouse, op by op with its evidence, the same every time, and nothing changed until imported."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.repo.snapshots import MemoryBackend

# synthetic text, written for this test
NOTE = (b"Desk rates note, October 5, 2026.\n\n"
        b"The central bank raised its policy rate by 25bp to 4.25%. The dollar index fell to 98 as the dollar weakened.\n\n"
        b"Crude oil lifts Acme Re adjusted net income. Higher oil prices lift headline inflation.\n\n"
        b"Acme Motors's operating profit rose 4% y/y.")
BUNDLE = {"format": "axelrod.import/v1", "title": "Hand-written bundle", "items": [
    {"id": "T-1", "published_at": "2026-10-06T08:00:00Z", "source": "Test desk", "headline": "Two claims, one unknown",
     "signals": [{"type": "move", "value_of": "acme_motors.operating_profit", "delta": 0.5, "mode": "standardized",
                  "quote": "Two claims"},
                 {"type": "observe", "value_of": "nowhere.nothing", "value": 1.0, "quote": "one unknown"}]}]}


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    app = create_app(scenario="acme_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0,
                     lake_dir=tmp_path_factory.mktemp("lake"))
    with TestClient(app) as c:
        yield c


def upload(client, data: bytes = NOTE, name: str = "2026-10-05_desk_note.md", **form):
    return client.post("/api/import/document", files={"file": (name, data, "text/markdown")},
                       data={"source": "Desk", "source_type": "broker_research", **form})


@pytest.fixture(scope="module")
def view(client):
    r = upload(client)
    assert r.status_code == 200, r.text
    return r.json()


def test_a_document_becomes_a_bundle_and_its_update_op_by_op(client, view):
    before = client.get("/api/sim/status").json()["version"]
    assert view["document"]["status"] == "extracted" and view["document"]["event_time"].startswith("2026-10-05")
    assert view["trace"]["new"] is True and view["trace"]["chunks"] >= 3 and view["trace"]["signals"] >= 5
    assert view["bundle"]["format"] == "axelrod.import/v1" and view["bundle_id"]
    ops: dict = {}
    for o in (o for it in view["items"] for o in it["ops"]):
        ops.setdefault((o["op"], o["signal"]), o)          # the first of each kind, in the document's order
    level = ops[("observe_value", "observe")]
    assert level["values"] == ["central_bank.policy_rate"] and level["value"] == 4.25 and level["z"] > 0
    assert level["quote"] == "The central bank raised its policy rate by 25bp to 4.25%." and level["table_row"] is False
    move = ops[("change_value", "move")]
    assert move["mode"] in ("absolute", "relative") and move["z"] > 0
    new = ops[("add_interaction", "link")]
    assert (new["source"], new["target"], new["polarity"]) == ("crude_oil.price", "acme_re.operating_profit", 1)
    assert new["effect"] > 0 and new["label"] == "lifts"
    ev = ops[("reweight_interaction", "support")]
    assert (ev["source"], ev["target"], ev["supports"]) == ("crude_oil.price", "economy.headline_inflation", True)
    assert ev["interaction_id"] in {i["id"] for i in client.get("/api/state").json()["links"]}
    # every value an op touches is described, and every item names its chunk, whose text holds the quote
    touched = {v for it in view["items"] for o in it["ops"] for v in o["values"]}
    assert touched <= set(view["values"]) and view["values"]["central_bank.policy_rate"]["entity"] == "Central bank"
    chunks = {c["ord"]: c["text"] for c in view["chunks"]}
    for it in view["items"]:
        assert it["event_id"] == f"GUE-IM-{it['id']}" and it["imported"] is False and it["dropped"] == []
        assert all(o["quote"] in chunks[it["chunk"]] for o in it["ops"])
    # nothing changed in the model
    assert client.get("/api/sim/status").json()["version"] == before
    assert client.get("/api/proposals?status=pending").json() == []


def test_the_same_document_draws_the_same_update(client, view):
    again = upload(client).json()
    assert again["trace"]["new"] is False
    assert again["bundle_id"] == view["bundle_id"]
    assert json.dumps(again["items"], sort_keys=True) == json.dumps(view["items"], sort_keys=True)
    assert again["values"] == view["values"] and again["chunks"] == view["chunks"]


def test_a_stored_document_is_listed_and_read_again(client, view):
    docs = client.get("/api/import/documents").json()
    assert view["document"]["id"] in {d["id"] for d in docs}
    got = client.post(f"/api/import/documents/{view['document']['id']}").json()
    assert got["bundle_id"] == view["bundle_id"] and got["items"] == view["items"]
    r = client.post("/api/import/documents/nope")
    assert r.status_code == 404


def test_a_bundle_file_shows_what_cannot_be_mapped(client):
    data = json.dumps(BUNDLE).encode()
    v = client.post("/api/import/document", files={"file": ("bundle.json", data, "application/json")}).json()
    (it,) = v["items"]
    assert it["chunk"] is None and it["page"] is None
    (op,) = it["ops"]
    assert (op["op"], op["mode"], op["z"]) == ("change_value", "standardized", 0.5)
    assert it["dropped"] == [{"signal": "observe", "quote": "one unknown", "reason": "no value nowhere.nothing"}]


def test_a_document_without_a_bundle_says_why(client):
    v = upload(client, b"%PDF-1.4 this is not really a pdf", name="broken.pdf").json()
    assert v["bundle"] is None and v["bundle_id"] is None and v["items"] == []
    assert v["document"]["status"] == "failed" and v["trace"]["warnings"]


def test_imported_items_are_marked(client, view):
    first = view["items"][0]["id"]
    assert client.post("/api/import", json={"bundle": view["bundle"], "ids": [first]}).status_code == 200
    got = client.post(f"/api/import/documents/{view['document']['id']}").json()
    assert {it["id"]: it["imported"] for it in got["items"]}[first] is True


def test_bad_uploads_are_refused(client, monkeypatch):
    assert upload(client, source_type="gossip").status_code == 422
    assert upload(client, b"").status_code == 422
    import axelrod_wm.api.v1.routes_ingest as service

    monkeypatch.setattr(service, "MAX_UPLOAD", 4)
    assert upload(client).status_code == 413


def test_a_scenario_without_imports_has_no_document_view(tmp_path):
    app = create_app(scenario="small_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0, lake_dir=tmp_path)
    with TestClient(app) as c:
        assert upload(c).status_code == 404
