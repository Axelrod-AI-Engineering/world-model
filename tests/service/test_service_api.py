"""The world model as a service (api/service.py): reads pinned to a state, documents into bundles, bundles into the
model through review, search, forecasts, and core's error envelope on every failure."""

from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.repo.snapshots import MemoryBackend

NOTE = (b"Rates note, October 5, 2026.\n\n"
        b"The BoJ raised its policy rate by 25bp to 1.25% on a 7-2 vote. USD/JPY fell to 152 as the yen strengthened.\n\n"
        b"JPMorgan's net interest income rose 4% y/y. Lower Bund yields weigh on UniCredit's net interest income.")
NOTHING = b"Nothing here names anything the model knows about, on purpose."
B = "/api/world-model"


@pytest.fixture(scope="module")
def client():
    app = create_app(scenario="sally_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def uploaded(client):
    r = client.post(f"{B}/documents", files=[("files", ("2026-10-05_note.md", NOTE, "text/markdown"))],
                    data={"source": "Desk", "source_type": "broker_research"})
    assert r.status_code == 201, r.text
    return r.json()["results"][0]


def err(r, status: int, code: str) -> None:
    assert r.status_code == status, r.text
    assert r.headers["x-axelrod-api-version"] == "1"
    assert r.json()["error"]["code"] == code


# -- reads ----------------------------------------------------------------------------------------------------------------
def test_state_names_the_version_and_counts(client):
    body = client.get(f"{B}/state").json()
    assert body["state"]["scenario"] == "sally_demo" and body["state"]["version"] >= 1
    assert body["counts"]["entities"] >= 30 and set(body["lake"]) >= {"documents", "chunks", "bundles"}


def test_query_returns_erid_compatible_nodes_and_causal_edges(client):
    body = client.get(f"{B}/query", params={"q": "Tokio Marine", "depth": 1}).json()
    tm = next(e for e in body["entities"] if e["id"] == "tokio_marine")
    assert tm["erid_kind"] == "company" and tm["concepts"][-1] == "Insurance"
    kpi = next(v for v in body["values"] if v["id"] == "tokio_marine.share_price")
    assert kpi["erid_kind"] == "kpi" and {"mean", "sd", "unit"} <= set(kpi)
    e = body["edges"][0]
    assert e["relation"] == "causes" and {"from_id", "to_id", "effect_sd_per_sd", "existence_p", "lag_days"} <= set(e)
    assert body["missing_data"] == [] and body["truncated"] is False


def test_query_by_ids_depth_and_limit(client):
    body = client.get(f"{B}/query", params={"node_ids": "boj,jgbs.yield_10y", "depth": 0}).json()
    assert {v["id"] for v in body["values"]} == {"boj.policy_rate", "jgbs.yield_10y"}
    whole = client.get(f"{B}/query", params={"depth": 0, "limit": 5}).json()
    assert len(whole["values"]) == 5 and whole["truncated"] is True
    err(client.get(f"{B}/query", params={"node_ids": "nope"}), 404, "node_not_found")


def test_reads_can_be_pinned_to_a_past_version_or_date(client):
    first = client.get(f"{B}/query", params={"node_ids": "boj", "version": 1}).json()
    assert first["state"]["version"] == 1 and first["state"]["state_hash"]
    dated = client.get(f"{B}/query", params={"node_ids": "boj", "as_of": "2026-08-02T23:59:59"}).json()
    assert dated["state"]["version"] == 2                     # seeded: no closed day yet, so the latest by that date
    err(client.get(f"{B}/query", params={"node_ids": "boj", "as_of": "2020-01-01T00:00:00Z"}), 404, "version_not_found")
    latest = client.get(f"{B}/state").json()["state"]["latest_version"]
    same = client.get(f"{B}/query", params={"node_ids": "boj", "version": latest}).json()
    assert same["state"]["version"] == latest
    err(client.get(f"{B}/query", params={"node_ids": "boj", "version": latest + 50}), 404, "version_not_found")


def test_nodes_entities_values_and_taxonomy(client):
    found = client.get(f"{B}/nodes", params={"q": "tokio", "limit": 2}).json()
    assert found["nodes"][0]["caption"].lower().startswith("tokio") and found["truncated"] is True
    assert len(client.get(f"{B}/nodes", params={"limit": 1000}).json()["nodes"]) > 50
    ent = client.get(f"{B}/entities/boj").json()
    assert ent["entity"]["caption"] == "Bank of Japan" and ent["values"] and ent["edges"]
    val = client.get(f"{B}/values/boj.policy_rate").json()
    assert val["value"]["unit"] == "pct" and val["effects"]
    err(client.get(f"{B}/entities/nope"), 404, "node_not_found")
    err(client.get(f"{B}/values/nope"), 404, "node_not_found")
    tax = client.get(f"{B}/taxonomy").json()
    banks = next(c for c in tax["concepts"] if c["name"] == "Banks")
    assert "jpmorgan" in banks["entity_ids"]


def test_context_export(client):
    ctx = client.get(f"{B}/context/v4").json()
    assert ctx["domain_pack"]["file_role"] == "DOMAIN_PACK__LOAD_AFTER_CORE_WHEN_ACTIVATED"
    err(client.get(f"{B}/context/v4", params={"forecast": "FC-nope"}), 404, "forecast_not_found")


# -- documents ------------------------------------------------------------------------------------------------------------
def test_an_upload_is_stored_parsed_and_read_into_a_bundle(uploaded):
    doc = uploaded["document"]
    assert doc["status"] == "extracted" and doc["event_time"].startswith("2026-10-05") and uploaded["new"] is True
    assert uploaded["chunks"] == 3 and uploaded["signals"] >= 4 and uploaded["bundle"]["items"] == 2


def test_the_same_bytes_are_stored_once(client, uploaded):
    again = client.post(f"{B}/documents", files=[("files", ("copy.md", NOTE, "text/markdown"))]).json()["results"][0]
    assert again["new"] is False and again["document"]["id"] == uploaded["document"]["id"]
    assert again["bundle"]["id"] == uploaded["bundle"]["id"]


def test_documents_list_detail_text_chunks_raw(client, uploaded):
    did = uploaded["document"]["id"]
    docs = client.get(f"{B}/documents", params={"order": "ingested_at"}).json()["documents"]
    assert any(d["id"] == did for d in docs)
    detail = client.get(f"{B}/documents/{did}").json()
    assert detail["chunks"] == 3 and detail["mentions"] > 0 and detail["bundles"][0]["id"] == uploaded["bundle"]["id"]
    text = client.get(f"{B}/documents/{did}/text").json()
    assert text["text"].startswith("Rates note") and text["parser"].startswith("markdown/")
    chunks = client.get(f"{B}/documents/{did}/chunks").json()["chunks"]
    assert any(m["value_id"] == "boj.policy_rate" for c in chunks for m in c["mentions"])
    raw = client.get(f"{B}/documents/{did}/raw")
    assert raw.content == NOTE and "attachment" in raw.headers["content-disposition"]
    err(client.get(f"{B}/documents/nope"), 404, "document_not_found")
    err(client.get(f"{B}/documents", params={"order": "nope"}), 422, "invalid_request")


def test_a_document_with_no_claims_and_an_unreadable_one(client):
    r = client.post(f"{B}/documents", files=[("files", ("empty.txt", NOTHING, "text/plain")),
                                              ("files", ("broken.pdf", b"not a pdf", "application/pdf"))]).json()
    by_name = {x["document"]["filename"]: x for x in r["results"]}
    assert by_name["empty.txt"]["warnings"] and by_name["empty.txt"]["bundle"]["items"] == 0
    assert by_name["broken.pdf"]["document"]["status"] == "failed" and by_name["broken.pdf"]["bundle"] is None
    did = by_name["broken.pdf"]["document"]["id"]
    err(client.get(f"{B}/documents/{did}/text"), 409, "not_parsed")


def test_extract_again_and_delete(client):
    r = client.post(f"{B}/documents", files=[("files", ("x.md", b"The ECB cut its deposit rate by 25bp.", "text/markdown"))])
    did = r.json()["results"][0]["document"]["id"]
    again = client.post(f"{B}/documents/{did}/extract").json()["result"]
    assert again["signals"] == 1
    assert client.delete(f"{B}/documents/{did}").json() == {"deleted": did}
    err(client.delete(f"{B}/documents/{did}"), 404, "document_not_found")


def test_upload_limits(client, monkeypatch):
    import axelrod_wm.api.service as svc

    monkeypatch.setattr(svc, "MAX_FILES", 1)
    err(client.post(f"{B}/documents", files=[("files", ("a.txt", b"a", "text/plain")), ("files", ("b.txt", b"b", "text/plain"))]),
        413, "too_many_files")
    monkeypatch.setattr(svc, "MAX_UPLOAD", 3)
    err(client.post(f"{B}/documents", files=[("files", ("a.txt", b"abcdef", "text/plain"))]), 413, "payload_too_large")


def test_a_raw_file_gone_from_the_volume(client, uploaded, monkeypatch):
    lake = client.app.state.lake
    monkeypatch.setattr(lake, "raw_bytes", lambda tenant, doc_id: None)
    err(client.get(f"{B}/documents/{uploaded['document']['id']}/raw"), 404, "file_missing")


# -- bundles and import -----------------------------------------------------------------------------------------------------
def test_a_bundle_posted_whole_is_stored(client):
    bundle = {"format": "axelrod.import/v1", "title": "Agent research", "items": [
        {"id": "AG-1", "published_at": "2026-08-10T00:00:00Z", "source": "agent", "headline": "BoJ at 1.25%",
         "signals": [{"type": "observe", "value_of": "boj.policy_rate", "value": 1.25, "quote": "BoJ at 1.25%"}]}]}
    res = client.post(f"{B}/bundles", json=bundle).json()["result"]
    assert res["bundle"]["items"] == 1 and res["document"]["meta"]["format"] == "bundle"
    listed = client.get(f"{B}/bundles").json()["bundles"]
    assert any(b["id"] == res["bundle"]["id"] for b in listed)
    err(client.post(f"{B}/bundles", content=b"{not json", headers={"content-type": "application/json"}), 400, "invalid_json")
    err(client.post(f"{B}/bundles", json={"format": "axelrod.import/v1", "items": [{"id": "x"}]}), 422, "invalid_request")


def test_import_queues_items_for_review_then_review_decides(client, uploaded):
    bid = uploaded["bundle"]["id"]
    out = client.post(f"{B}/bundles/{bid}/import", json={"review": "queue"}).json()
    assert out["imported"] and out["pending_proposals"] and out["approved"] == []
    pending = client.get(f"{B}/proposals").json()["proposals"]
    assert {p["id"] for p in pending} >= set(out["pending_proposals"][:1])
    first = out["pending_proposals"][0]
    err(client.post(f"{B}/proposals/{first}/reject", json={"note": " "}), 422, "note_required")
    decided = client.post(f"{B}/proposals/{first}/approve", json={"note": "fine"}).json()
    assert decided["status"].endswith("approved")
    err(client.post(f"{B}/proposals/{first}/approve"), 409, "already_decided")
    err(client.post(f"{B}/proposals/PR-nope/approve"), 404, "proposal_not_found")
    while True:
        left = client.get(f"{B}/proposals").json()["proposals"]
        if not left:
            break
        client.post(f"{B}/proposals/{left[0]['id']}/reject", json={"note": "not this one"})
    assert client.get(f"{B}/proposals", params={"status": "all", "limit": 1000}).json()["proposals"]
    again = client.post(f"{B}/bundles/{bid}/import").json()
    assert again["imported"] == [] and again["update_id"] is None
    detail = client.get(f"{B}/bundles/{bid}").json()
    assert detail["imports"] and detail["bundle"]["format"] == "axelrod.import/v1"


def test_import_with_auto_review_moves_the_model(client):
    note = b"Data, September 1, 2026. The Fed held rates at 3.875%. Brent crude rose to $103 a barrel."
    res = client.post(f"{B}/documents", files=[("files", ("fed.txt", note, "text/plain"))]).json()["results"][0]
    out = client.post(f"{B}/bundles/{res['bundle']['id']}/import", json={"review": "auto"}).json()
    assert out["approved"] and out["pending_proposals"] == [] and out["state"]["version"] > out["version_before"]
    brent = client.get(f"{B}/values/oil.brent").json()["value"]
    assert brent["observed"] is True


def test_import_errors(client, uploaded):
    err(client.post(f"{B}/bundles/nope/import"), 404, "bundle_not_found")
    err(client.get(f"{B}/bundles/nope"), 404, "bundle_not_found")
    err(client.post(f"{B}/bundles/{uploaded['bundle']['id']}/import", json={"review": "sometimes"}), 422, "invalid_request")


def test_an_import_while_another_update_waits_is_a_conflict(client):
    a = client.post(f"{B}/documents", files=[("files", ("a.txt", b"Oct 20, 2026. The ECB cut its deposit rate by 25bp.", "text/plain"))]).json()
    b = client.post(f"{B}/documents", files=[("files", ("b.txt", b"Oct 21, 2026. The BoJ raised its policy rate by 25bp.", "text/plain"))]).json()
    first = client.post(f"{B}/bundles/{a['results'][0]['bundle']['id']}/import").json()
    assert first["pending_proposals"]
    err(client.post(f"{B}/bundles/{b['results'][0]['bundle']['id']}/import"), 409, "update_in_progress")
    for p in client.get(f"{B}/proposals").json()["proposals"]:
        client.post(f"{B}/proposals/{p['id']}/approve")


# -- search -----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("mode", ["keyword", "prefix", "semantic", "graph", "hybrid"])
def test_every_search_mode_answers(client, uploaded, mode):
    body = client.get(f"{B}/search", params={"q": "BoJ policy rate", "mode": mode}).json()
    assert body["mode"] == mode and body["hits"]


def test_search_rejects_an_unknown_mode_and_an_empty_query(client):
    err(client.get(f"{B}/search", params={"q": "x", "mode": "psychic"}), 422, "invalid_request")
    err(client.get(f"{B}/search", params={"q": ""}), 422, "invalid_request")


# -- forecasts --------------------------------------------------------------------------------------------------------------
def test_forecasts_from_a_question_or_a_ready_thesis(client):
    q = client.post(f"{B}/forecasts", json={"question": "What if the BoJ hiked by 25bp next quarter?", "horizon_days": 120})
    assert q.status_code == 201
    fc = q.json()["forecast"]
    assert fc["targets"] and fc["transmission"] and fc["horizon_days"] == 120
    t = client.post(f"{B}/forecasts", json={"thesis_id": "S-T3"}).json()["forecast"]
    assert t["thesis_id"] == "S-T3" and t["scenario_table"]["rows"]
    listed = client.get(f"{B}/forecasts").json()["forecasts"]
    assert {fc["id"], t["id"]} <= {f["id"] for f in listed}
    got = client.get(f"{B}/forecasts/{t['id']}").json()
    assert got["forecast"]["id"] == t["id"] and got["state"]["version"] == t["based_on_version"]
    brief = client.get(f"{B}/forecasts/{t['id']}/brief").json()
    assert brief["question"]
    ctx = client.get(f"{B}/context/v4", params={"forecast": t["id"]}).json()
    assert ctx["forecast"]["forecast_id"] == t["id"]


def test_forecast_errors(client):
    err(client.post(f"{B}/forecasts", json={}), 422, "invalid_request")
    err(client.post(f"{B}/forecasts", json={"question": "x", "thesis_id": "S-T1"}), 422, "invalid_request")
    err(client.post(f"{B}/forecasts", json={"thesis_id": "S-nope"}), 404, "thesis_not_found")
    err(client.post(f"{B}/forecasts", json={"question": "What is the meaning of life?"}), 422, "question_not_understood")
    err(client.post(f"{B}/forecasts", json={"question": "x", "extra": 1}), 422, "invalid_request")
    err(client.get(f"{B}/forecasts/FC-nope"), 404, "forecast_not_found")
    err(client.get(f"{B}/forecasts/FC-nope/brief"), 404, "forecast_not_found")


# -- a scenario that takes no imports, and one without templates --------------------------------------------------------------
def test_a_scenario_without_imports_answers_reads_and_refuses_imports():
    app = create_app(scenario="small_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        assert c.get(f"{B}/state").status_code == 200
        res = c.post(f"{B}/documents", files=[("files", ("n.txt", NOTE, "text/plain"))]).json()["results"][0]
        err(c.post(f"{B}/bundles/{res['bundle']['id']}/import"), 404, "not_found")
        err(c.post(f"{B}/forecasts", json={"thesis_id": "S-T1"}), 404, "thesis_not_found")


def test_inverted_surfaces_come_from_the_worlds_templates(client, monkeypatch, tmp_path):
    from axelrod_wm.api.service import inverted_surfaces, st_of

    class Req:
        app = client.app
        scope: dict = {}

    st = st_of(Req())
    assert any("yen" in p for p in inverted_surfaces(st))
    monkeypatch.setattr(st.controller, "world_dir", lambda: tmp_path)
    assert inverted_surfaces(st) == []
    monkeypatch.setattr(st.controller, "world_dir", lambda: None)
    assert inverted_surfaces(st) == []
    (tmp_path / "templates.yaml").write_text("subjects: []\n")
    monkeypatch.setattr(st.controller, "world_dir", lambda: tmp_path)
    assert inverted_surfaces(st) == []


def test_unexpected_errors_still_answer_in_the_envelope(client, monkeypatch):
    import axelrod_wm.api.service as svc

    def boom(*a, **k):
        raise ValueError("bad value")

    monkeypatch.setattr(svc, "state_identity", boom)
    err(client.get(f"{B}/state"), 400, "invalid_request")

    def missing(*a, **k):
        raise KeyError("thing")

    monkeypatch.setattr(svc, "state_identity", missing)
    err(client.get(f"{B}/state"), 404, "not_found")


def test_upload_bytes_round_trip_in_a_multipart_stream(client):
    body = io.BytesIO(NOTE)
    r = client.post(f"{B}/documents", files={"files": ("stream.md", body, "text/markdown")})
    assert r.status_code == 201 and json.loads(r.text)["results"][0]["new"] is False


def test_conflicts_and_missing_versions_answer_in_the_envelope(client, monkeypatch):
    import axelrod_wm.api.service as svc
    from axelrod_wm.control.controller import ControllerError
    from axelrod_wm.repo.snapshots import RestoreError

    for exc, status, code in ((ControllerError("busy"), 409, "conflict"),
                              (RestoreError("gone"), 404, "version_not_found")):
        def boom(*a, exc=exc, **k):
            raise exc

        monkeypatch.setattr(svc, "state_identity", boom)
        err(client.get(f"{B}/state"), status, code)


def test_a_value_summary_without_quantiles_and_an_entity_without_a_concept():
    from types import SimpleNamespace

    from axelrod_wm.api.service import _summary, concept_names

    class Plain:
        def mean(self):
            return 1.0

        def sd(self):
            return 0.5

    assert _summary(SimpleNamespace(posterior=Plain())) == {"mean": 1.0, "sd": 0.5}
    tax = SimpleNamespace(nodes={}, root_id="root")
    ltm = SimpleNamespace(object_generalizations=SimpleNamespace(taxonomy=tax))
    assert concept_names(ltm, None) == [] and concept_names(ltm, "nope") == []


def test_approvals_that_leave_nothing_to_resume(client, monkeypatch):
    """When an approval wakes no waiting update, the service answers without driving one; here the test drives the
    woken update itself, so the module's model is left as the real path would leave it."""
    import axelrod_wm.api.routes as routes
    from axelrod_wm.api.service import state_for

    real, woken = routes._resume_if_awaited, []

    def quiet(st, pid):
        run_id = real(st, pid)
        if run_id is not None:
            woken.append(run_id)
        return None

    monkeypatch.setattr(routes, "_resume_if_awaited", quiet)
    note = b"Oct 22, 2026. The ECB cut its deposit rate by 25bp."
    res = client.post(f"{B}/documents", files=[("files", ("quiet.txt", note, "text/plain"))]).json()["results"][0]
    out = client.post(f"{B}/bundles/{res['bundle']['id']}/import", json={"review": "auto"})
    assert out.status_code == 200, out.text
    st = state_for(client.app, {})

    def drive_woken():
        while woken:
            client.portal.call(st.drive, woken.pop(0))

    drive_woken()
    queued = client.post(f"{B}/documents", files=[("files", ("quiet2.txt", b"Oct 23, 2026. The BoJ raised its policy rate by 25bp.", "text/plain"))]).json()["results"][0]
    client.post(f"{B}/bundles/{queued['bundle']['id']}/import")
    pending = client.get(f"{B}/proposals").json()["proposals"]
    assert pending
    while pending:
        for p in pending:
            assert client.post(f"{B}/proposals/{p['id']}/approve").status_code == 200
        drive_woken()
        pending = client.get(f"{B}/proposals").json()["proposals"]
