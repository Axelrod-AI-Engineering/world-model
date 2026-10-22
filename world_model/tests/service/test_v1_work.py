"""v1 work on the model (docs/api/openapi.yaml): documents into bundles (202 and a job), bundles, search, changes and
their human review (If-Match), events and what they did, theses run as simulations, jobs, and Idempotency-Key."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import axelrod_wm.api.v1.routes_ingest as ingest
import axelrod_wm.api.v1.routes_work as work
from tests.service.helpers import (
    NOTE,
    OIL_NOTE,
    SPREAD_NOTE,
    WM,
    Signer,
    data,
    decide_all,
    etag_now,
    problem,
    propose,
    service,
    upload,
)

SIGNER = Signer()
SUPPORT = {"format": "axelrod.import/v1", "title": "Agent research", "items": [
    {"id": "AG-1", "published_at": "2026-08-10T00:00:00Z", "source": "agent", "headline": "A stronger dollar trims Acme Motors",
     "signals": [{"type": "support", "source": "dollar.index", "target": "acme_motors.operating_profit",
                  "strength": 0.6, "quote": "A stronger dollar trims Acme Motors"}]}]}
# evidence on an earlier link, so that reading a later link's record by its id passes over other records first
SUPPORT_EARLY = {"format": "axelrod.import/v1", "title": "Agent research, earlier link", "items": [
    {"id": "AG-0", "published_at": "2026-08-09T00:00:00Z", "source": "agent", "headline": "The policy rate anchors the two-year yield",
     "signals": [{"type": "support", "source": "central_bank.policy_rate", "target": "gov_bonds.yield_2y",
                  "strength": 0.6, "quote": "The policy rate anchors the two-year yield"}]}]}


@pytest.fixture(scope="module")
def c():
    with service(SIGNER) as client:
        yield client


@pytest.fixture(scope="module")
def note(c):
    return upload(c, NOTE, "2026-10-05_note.md", source="Desk", source_type="broker_research")


def reviewer(**kw):
    return SIGNER.bearer(**kw)


# -- documents -------------------------------------------------------------------------------------------------------------
def test_an_upload_is_a_finished_job_naming_its_document_and_bundle(c, note):
    assert note["new"] is True and note["status"] == "extracted" and note["chunks"] == 3 and note["bundle_id"]
    doc = data(c.get(f"{WM}/documents/{note['document_id']}"))
    assert doc["event_time"].startswith("2026-10-05") and doc["uploaded_by"] == "tester" and doc["source"] == "Desk"


def test_upload_answers_202_with_a_location_to_poll(c):
    r = c.post(f"{WM}/documents", files=[("files", ("x.txt", SPREAD_NOTE, "text/plain"))])
    assert r.status_code == 202 and r.headers["location"] == f"{WM}/jobs/{r.json()['data']['id']}"
    job = data(c.get(r.headers["location"]))
    assert job == r.json()["data"] and job["type"] == "document_ingestion" and job["finished_at"]
    problem(c.get(f"{WM}/jobs/job_nope"), 404, "job_not_found")


def test_documents_list_by_cursor_one_chunks_content(c, note):
    did = note["document_id"]
    first = c.get(f"{WM}/documents", params={"order": "ingested_at", "limit": 1}).json()
    assert len(first["data"]) == 1 and first["meta"]["next_cursor"]
    rest = data(c.get(f"{WM}/documents", params={"order": "ingested_at", "limit": 200,
                                                 "cursor": first["meta"]["next_cursor"]}))
    assert first["data"][0]["id"] not in {d["id"] for d in rest}
    dated = data(c.get(f"{WM}/documents", params={"published_from": "2026-10-01T00:00:00Z",
                                                  "published_to": "2026-10-31T00:00:00Z"}))
    assert did in {d["id"] for d in dated}
    chunks = data(c.get(f"{WM}/documents/{did}/chunks"))
    assert [ch["ordinal"] for ch in chunks] == [0, 1, 2]
    mentions = [m for ch in chunks for m in ch["mentions"]]
    assert {"central_bank.policy_rate"} <= {m["attribute_id"] for m in mentions}
    assert data(c.get(f"{WM}/documents/{did}/chunks/1")) == chunks[1]
    problem(c.get(f"{WM}/documents/{did}/chunks/9"), 404, "chunk_not_found")
    problem(c.get(f"{WM}/documents/{did}/chunks/-1"), 422, "invalid_request")
    text = data(c.get(f"{WM}/documents/{did}/content"))
    assert text["text"].startswith("Rates note") and text["parser"].startswith("markdown/")
    raw = c.get(f"{WM}/documents/{did}/content", params={"format": "raw"})
    assert raw.content == NOTE and raw.headers["content-disposition"].startswith("attachment")
    for path in ("", "/chunks", "/chunks/0", "/content"):
        problem(c.get(f"{WM}/documents/nope{path}"), 404, "document_not_found")


def test_an_unreadable_document_and_a_file_gone(c, note, monkeypatch):
    r = c.post(f"{WM}/documents", files=[("files", ("broken.pdf", b"not a pdf", "application/pdf"))])
    bad = data(r, 202)["result"]["detail"]["results"][0]
    assert bad["status"] == "failed" and bad["bundle_id"] is None
    problem(c.get(f"{WM}/documents/{bad['document_id']}/content"), 409, "not_parsed")
    monkeypatch.setattr(c.app.state.lake, "raw_bytes", lambda tenant, doc_id: None)
    problem(c.get(f"{WM}/documents/{note['document_id']}/content", params={"format": "raw"}), 404, "file_missing")


def test_read_again_and_delete(c):
    res = upload(c, b"Oct 2, 2026. Credit spreads rose by 25bp.", "again.txt")
    job = data(c.post(f"{WM}/documents/{res['document_id']}/bundles"), 202)
    assert job["type"] == "document_extraction" and job["result"]["ids"] == [res["bundle_id"]]
    problem(c.post(f"{WM}/documents/nope/bundles"), 404, "document_not_found")
    r = c.delete(f"{WM}/documents/{res['document_id']}")
    assert r.status_code == 204 and not r.content and r.headers["x-request-id"]
    problem(c.delete(f"{WM}/documents/{res['document_id']}"), 404, "document_not_found")
    # the kept answers that named it are forgotten, so the same content uploads afresh
    assert upload(c, b"Oct 2, 2026. Credit spreads rose by 25bp.", "again.txt")["new"] is True


def test_a_failed_read_is_a_failed_job(c, monkeypatch):
    res = upload(c, b"Oct 3, 2026. The central bank held.", "fails.txt")

    def boom(*a, **k):
        raise ValueError("the parser broke")

    monkeypatch.setattr(ingest.Ingestor, "process", boom)
    job = data(c.post(f"{WM}/documents/{res['document_id']}/bundles"), 202)
    assert job["status"] == "failed" and job["error"]["code"] == "invalid_request" and job["result"] is None


def test_a_bug_in_a_job_is_not_hidden(c, monkeypatch):
    res = upload(c, b"Oct 4, 2026. The central bank held.", "bug.txt")

    def bug(*a, **k):
        raise RuntimeError("a bug")

    monkeypatch.setattr(ingest.Ingestor, "process", bug)
    with pytest.raises(RuntimeError):
        c.post(f"{WM}/documents/{res['document_id']}/bundles")


def test_upload_limits_and_validation(c, monkeypatch):
    monkeypatch.setattr(ingest, "MAX_FILES", 2)
    files = [("files", (f"n{k}.txt", f"limit note {k}".encode(), "text/plain")) for k in range(3)]
    assert c.post(f"{WM}/documents", files=files[:2]).status_code == 202
    problem(c.post(f"{WM}/documents", files=files), 413, "too_many_files")
    monkeypatch.setattr(ingest, "MAX_UPLOAD", 8)
    assert c.post(f"{WM}/documents", files=[("files", ("s.txt", b"x" * 8, "text/plain"))]).status_code == 202
    problem(c.post(f"{WM}/documents", files=[("files", ("s.txt", b"x" * 9, "text/plain"))]), 413, "payload_too_large")
    problem(c.post(f"{WM}/documents", data={"source": "x"}), 422, "invalid_request")
    problem(c.post(f"{WM}/documents", files=[("files", ("a.txt", b"a", "text/plain"))], data={"source_type": "gossip"}),
            422, "invalid_request")


def test_the_real_limits_are_the_documented_ones():
    assert ingest.MAX_FILES == 20 and ingest.MAX_UPLOAD == 50 * 1024 * 1024


# -- bundles -----------------------------------------------------------------------------------------------------------------
def test_a_bundle_posted_whole_listed_and_its_items(c, note):
    r = c.post(f"{WM}/bundles", json=SUPPORT)
    b = data(r, 201)
    assert b["item_count"] == 1 and b["signal_count"] == 1 and r.headers["location"] == f"{WM}/bundles/{b['id']}"
    assert data(c.get(f"{WM}/bundles/{b['id']}")) == b
    items = data(c.get(f"{WM}/bundles/{b['id']}/items"))
    assert items[0]["id"] == "AG-1" and items[0]["signals"][0]["type"] == "support"
    listed = data(c.get(f"{WM}/bundles", params={"limit": 200}))
    assert b["id"] in {x["id"] for x in listed}
    mine = data(c.get(f"{WM}/bundles", params={"document_id": note["document_id"]}))
    assert [x["id"] for x in mine] == [note["bundle_id"]]
    problem(c.get(f"{WM}/bundles/nope"), 404, "bundle_not_found")
    problem(c.get(f"{WM}/bundles/nope/items"), 404, "bundle_not_found")
    problem(c.post(f"{WM}/bundles", content=b"{nope", headers={"content-type": "application/json"}), 400,
            "invalid_json")
    problem(c.post(f"{WM}/bundles", content=b"items", headers={"content-type": "text/plain"}), 415,
            "unsupported_media_type")
    problem(c.post(f"{WM}/bundles", json={"format": "axelrod.import/v1", "items": [{"id": "x"}]}), 422,
            "invalid_request")


# -- search ----------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("mode", ["keyword", "prefix", "semantic", "graph", "hybrid"])
def test_every_search_mode(c, note, mode):
    body = c.get(f"{WM}/search", params={"q": "central bank policy rate", "mode": mode}).json()
    assert body["data"] and body["meta"]["next_cursor"] is None and body["meta"]["version"]


def test_search_names_attributes_with_their_entity(c):
    hits = data(c.get(f"{WM}/search", params={"q": "Acme Motors op", "mode": "prefix"}))
    att = next(h for h in hits if h["ref"] == "acme_motors.operating_profit")
    assert att["kind"] == "attribute" and att["entity_id"] == "acme_motors"
    problem(c.get(f"{WM}/search", params={"q": ""}), 422, "invalid_request")
    problem(c.get(f"{WM}/search", params={"q": "x", "mode": "psychic"}), 422, "invalid_request")


# -- changes and their review -----------------------------------------------------------------------------------------------------
def test_propose_review_and_decide(c, note):
    job = propose(c, note["bundle_id"])
    assert job["type"] == "change_proposal" and job["result"]["ids"]
    detail = job["result"]["detail"]
    assert detail["imported_item_ids"] and detail["update_id"] and detail["bundle_id"] == note["bundle_id"]
    first = job["result"]["ids"][0]
    r = c.get(f"{WM}/changes/{first}")
    ch = data(r)
    assert ch["status"] == "pending" and ch["proposed_by"]["sub"] == "tester" and ch["decided_by"] is None
    assert r.headers["etag"] == etag_now(c)
    diff = data(c.get(f"{WM}/changes/{first}/diff"))
    assert diff["operations"] and all(op["summary"] and op["op"] for op in diff["operations"])
    # human only, against the version reviewed
    url = f"{WM}/changes/{first}/approvals"
    problem(c.post(url, json={}), 403, "human_approval_required")                  # a key: a person decides
    problem(c.post(url, json={}, headers=reviewer(act={"sub": "mcp-client:x"}, scope="changes:approve")), 403,
            "human_approval_required")
    problem(c.post(url, json={}, headers=reviewer(azp="core-mcp")), 403, "human_approval_required")
    problem(c.post(url, json={}, headers=reviewer()), 428, "precondition_required")
    problem(c.post(url, json={}, headers={**reviewer(), "If-Match": '"stale"'}), 412, "version_moved")
    ok = data(c.post(url, json={"note": "matches the note"}, headers={**reviewer(), "If-Match": etag_now(c)}), 201)
    assert ok["status"] == "approved" and ok["decided_by"]["sub"] == "org_user_9" and ok["decided_by"]["jti"]
    assert ok["note"] == "matches the note" and ok["version"]["number"] >= 1
    problem(c.post(url, json={}, headers={**reviewer(), "If-Match": etag_now(c)}), 409, "already_decided")
    after = data(c.get(f"{WM}/changes/{first}"))
    assert after["decided_by"]["azp"] == "core-web" and after["version_after"]
    problem(c.post(f"{WM}/changes/PR-nope/approvals", json={}, headers={**reviewer(), "If-Match": etag_now(c)}), 404,
            "change_not_found")
    rest = decide_all(c, SIGNER, approve=False, note="not this one")
    assert all(d["status"] == "rejected" for d in rest)
    every = data(c.get(f"{WM}/changes", params={"status": "all", "limit": 200}))
    assert {x["status"] for x in every} >= {"approved", "rejected"}
    assert data(c.get(f"{WM}/changes", params={"status": "approved"})) and data(c.get(f"{WM}/changes")) == []
    again = propose(c, note["bundle_id"])
    assert again["result"]["ids"] == [] and again["result"]["detail"]["imported_item_ids"] == []
    for path in ("", "/diff"):
        problem(c.get(f"{WM}/changes/PR-nope{path}"), 404, "change_not_found")


def test_a_rejection_needs_a_reason(c):
    h = {**reviewer(), "If-Match": etag_now(c)}
    problem(c.post(f"{WM}/changes/PR-1/rejections", json={"reason": "  "}, headers=h), 422, "note_required")
    problem(c.post(f"{WM}/changes/PR-1/rejections", json={}, headers=h), 422, "invalid_request")


def test_a_second_proposal_while_one_waits_is_a_conflict(c):
    a = upload(c, b"Oct 20, 2026. Credit spreads rose by 25bp.", "a.txt")
    b = upload(c, b"Oct 21, 2026. The central bank raised its policy rate by 25bp.", "b.txt")
    assert propose(c, a["bundle_id"])["result"]["ids"]
    problem(c.post(f"{WM}/changes", json={"bundle_id": b["bundle_id"]}), 409, "update_in_progress")
    problem(c.post(f"{WM}/changes", json={"bundle_id": "nope"}), 404, "bundle_not_found")
    problem(c.post(f"{WM}/changes", json={"bundle_id": b["bundle_id"], "review": "auto"}), 422, "invalid_request")
    decide_all(c, SIGNER)
    # another proposal starting at the same moment (tests/integration/service/test_concurrency.py runs the race)
    c.app.state.proposing.add("acme_demo")
    try:
        problem(c.post(f"{WM}/changes", json={"bundle_id": b["bundle_id"]}), 409, "update_in_progress")
    finally:
        c.app.state.proposing.discard("acme_demo")
    assert propose(c, b["bundle_id"])["result"]["ids"] and not c.app.state.proposing
    decide_all(c, SIGNER)


def test_evidence_from_an_approved_support(c):
    early = data(c.post(f"{WM}/bundles", json=SUPPORT_EARLY), 201)
    propose(c, early["id"])
    decide_all(c, SIGNER)
    b = data(c.post(f"{WM}/bundles", json=SUPPORT), 201)
    before = data(c.get(f"{WM}/relationships/m24"))["evidence_count"]
    propose(c, b["id"])
    decide_all(c, SIGNER)
    assert data(c.get(f"{WM}/relationships/m24"))["evidence_count"] == before + 1
    ev = data(c.get(f"{WM}/relationships/m24/evidence", params={"limit": 200}))
    assert ev[-1]["relationship_id"] == "m24" and ev[-1]["evidence_type"] and ev[-1]["epistemic_type"]
    assert data(c.get(f"{WM}/evidence/{ev[-1]['id']}")) == ev[-1]


# -- events and what they did -------------------------------------------------------------------------------------------------------
def test_events_and_their_impact(c):
    res = upload(c, OIL_NOTE, "oil.txt", source_type="data")
    job = propose(c, res["bundle_id"])
    ch = data(c.get(f"{WM}/changes/{job['result']['ids'][0]}"))
    pending = data(c.get(f"{WM}/events/{ch['event_id']}/impact-analysis"))
    assert pending["status"] == "pending_review" and pending["event_id"] == ch["event_id"]
    decide_all(c, SIGNER)
    ev = data(c.get(f"{WM}/events/{ch['event_id']}"))
    assert ch["id"] in ev["change_ids"] and ev["type"] in ("news", "data_release", "company_filing", "research")
    done = data(c.get(f"{WM}/events/{ch['event_id']}/impact-analysis"))
    direct = [i for i in done["impacts"] if i["order"] == 0]
    assert done["status"] == "completed" and "crude_oil.price" in {i["attribute_id"] for i in direct}
    assert all(i["size_sd"] is not None for i in direct)
    on = [i for i in done["impacts"] if i["order"] == 1]
    assert on and all(i["causal_path_ids"] and i["confidence"] is not None for i in on)
    listed = data(c.get(f"{WM}/events", params={"limit": 200}))
    assert ch["event_id"] in {e["id"] for e in listed}
    t = ev["type"]
    assert ch["event_id"] in {e["id"] for e in data(c.get(f"{WM}/events", params={"type": t, "limit": 200}))}
    assert data(c.get(f"{WM}/events", params={"published_from": "2100-01-01T00:00:00"})) == []
    assert data(c.get(f"{WM}/events", params={"published_to": "2000-01-01T00:00:00Z"})) == []
    assert data(c.get(f"{WM}/events", params={"entity": "nobody"})) == []
    problem(c.get(f"{WM}/events/nope"), 404, "event_not_found")
    problem(c.get(f"{WM}/events/nope/impact-analysis"), 404, "event_not_found")


def test_what_an_event_did_before_and_without_a_change(c, monkeypatch):
    """An event with no change is not imported; a pending change's value change has a direction but no size yet, and an
    operation that targets no attribute moves nothing."""
    eid = data(c.get(f"{WM}/events", params={"limit": 1}))[0]["id"]
    monkeypatch.setattr(work, "changes_of_event", lambda ctl, event_id: [])
    assert data(c.get(f"{WM}/events/{eid}/impact-analysis")) == {
        "event_id": eid, "status": "not_imported", "model_version": data(c.get(WM))["latest_version"], "impacts": []}
    ops = [SimpleNamespace(), SimpleNamespace(target=SimpleNamespace(subentity_id="nobody.nothing")),
           SimpleNamespace(target=SimpleNamespace(subentity_id="crude_oil.price"), delta=-3.0)]
    pending = SimpleNamespace(status="pending", event=SimpleNamespace(id="ME-unapplied", ops=ops))
    monkeypatch.setattr(work, "changes_of_event", lambda ctl, event_id: [pending])
    out = data(c.get(f"{WM}/events/{eid}/impact-analysis"))
    assert out["status"] == "pending_review"
    direct = [i for i in out["impacts"] if i["order"] == 0]
    assert [(i["attribute_id"], i["direction"], i["size_sd"]) for i in direct] == [("crude_oil.price", "negative", None)]
    assert all(i["size_sd"] is None for i in out["impacts"] if i["order"] == 1)


def test_a_decision_no_update_waits_on_and_an_import_that_fails(c, monkeypatch):
    import axelrod_wm.api.routes as demo
    from axelrod_wm.control.controller import ControllerError

    res = upload(c, NOTE.replace(b"October 5", b"October 23"), "rates-again.md")
    first = propose(c, res["bundle_id"])["result"]["ids"][0]
    versions = data(c.get(f"{WM}/versions", params={"limit": 200}))
    assert first not in {x for v in versions for x in v["change_ids"]}          # pending: in no version yet
    # a change no update run is waiting on (as the engine's own proposals are): recorded, nothing to drive
    monkeypatch.setattr(demo, "_resume_if_awaited", lambda st, change_id: None)
    ok = data(c.post(f"{WM}/changes/{first}/approvals", json={}, headers={**reviewer(), "If-Match": etag_now(c)}), 201)
    assert ok["status"] == "approved"
    monkeypatch.undo()
    st = c.app.state.world_models["acme_demo"].st
    c.portal.call(st.drive, demo._resume_if_awaited(st, first))                # let this test's update finish
    decide_all(c, SIGNER)
    other = upload(c, b"Oct 24, 2026. Credit spreads held steady.", "spreads2.txt")

    def busy(*a, **k):
        raise ControllerError("the engine is busy")

    monkeypatch.setattr(st.ensure_loaded(), "import_items", busy)
    job = data(c.post(f"{WM}/changes", json={"bundle_id": other["bundle_id"]}), 202)
    assert job["status"] == "failed" and job["error"]["code"] == "conflict"


# -- theses and simulations --------------------------------------------------------------------------------------------------------------
def test_theses_from_a_question_or_a_template_and_their_simulations(c):
    templates = data(c.get(f"{WM}/thesis-templates", params={"limit": 200}))
    assert "S-T3" in {t["id"] for t in templates}
    r = c.post(f"{WM}/theses", json={"question": "What if the central bank hiked by 25bp next quarter?", "horizon_days": 120})
    q = data(r, 201)
    assert q["horizon_days"] == 120 and q["simulation_ids"] == [] and r.headers["location"].endswith(q["id"])
    t = data(c.post(f"{WM}/theses", json={"template_id": "S-T3"}), 201)
    assert t["mode"] == "template" and data(c.get(f"{WM}/theses/{t['id']}")) == t
    job = data(c.post(f"{WM}/theses/{t['id']}/simulations"), 202)
    assert job["type"] == "simulation" and job["status"] == "succeeded"
    sid = job["result"]["ids"][0]
    short = data(c.post(f"{WM}/theses/{q['id']}/simulations", json={"horizon_days": 30}), 202)
    qs = data(c.get(f"{WM}/simulations/{short['result']['ids'][0]}"))
    assert qs["horizon_days"] == 30
    sim = c.get(f"{WM}/simulations/{sid}")
    s = data(sim)
    assert s["thesis_id"] == "S-T3" and s["targets"] and sim.json()["meta"]["version"]["number"] == s["version"]
    assert all(x["attribute_id"].split(".", 1)[0] == x["entity_id"] for x in s["targets"])
    tx = c.get(f"{WM}/simulations/{sid}/transmission", params={"limit": 5}).json()
    assert tx["data"] and [x["order"] for x in tx["data"]] == sorted(x["order"] for x in tx["data"])
    cov = data(c.get(f"{WM}/simulations/{sid}/coverage"))
    assert {"contributed", "excluded", "blocking_inputs", "targets", "summary"} <= set(cov)
    brief = data(c.get(f"{WM}/simulations/{sid}/brief"))
    assert brief["coverage"] == cov and brief["question"]
    pack = data(c.get(f"{WM}/exports/v4.1.4", params={"simulation": sid}))
    assert pack["forecast"]["forecast_id"] == sid and pack["forecast"]["calculation_coverage"] == cov
    listed = data(c.get(f"{WM}/simulations", params={"limit": 200}))
    assert sid in {x["id"] for x in listed}
    theses = data(c.get(f"{WM}/theses", params={"limit": 200}))
    assert {q["id"], "S-T3"} <= {x["id"] for x in theses}
    assert sid in data(c.get(f"{WM}/theses/S-T3"))["simulation_ids"]
    for path in ("", "/transmission", "/coverage", "/brief"):
        problem(c.get(f"{WM}/simulations/FC-nope{path}"), 404, "simulation_not_found")


def test_thesis_errors(c, monkeypatch):
    problem(c.post(f"{WM}/theses", json={}), 422, "invalid_request")
    problem(c.post(f"{WM}/theses", json={"question": "x", "template_id": "S-T1"}), 422, "invalid_request")
    problem(c.post(f"{WM}/theses", json={"template_id": "S-nope"}), 404, "thesis_not_found")
    problem(c.post(f"{WM}/theses", json={"question": "What is the meaning of life?"}), 422, "question_not_understood")
    problem(c.post(f"{WM}/theses", json={"question": "x", "extra": 1}), 422, "invalid_request")
    problem(c.post(f"{WM}/theses", json={"question": "x", "horizon_days": 6}), 422, "invalid_request")
    problem(c.get(f"{WM}/theses/T-nope"), 404, "thesis_not_found")
    problem(c.post(f"{WM}/theses/T-nope/simulations"), 404, "thesis_not_found")
    st = c.app.state.world_models["acme_demo"].st
    monkeypatch.setattr(st.controller, "scenario_dir", None)
    assert data(c.get(f"{WM}/thesis-templates")) == []


def test_an_unbound_thesis_is_a_failed_job(c, monkeypatch):
    from axelrod_wm.inference.task import UnboundThesis

    t = data(c.post(f"{WM}/theses", json={"template_id": "S-T1"}), 201)
    st = c.app.state.world_models["acme_demo"].st

    def unbound(thesis):
        raise UnboundThesis([{"op_index": 0, "end": "target", "candidates": []}])

    monkeypatch.setattr(st.controller, "pose_thesis", unbound)
    job = data(c.post(f"{WM}/theses/{t['id']}/simulations"), 202)
    assert job["status"] == "failed" and job["error"]["code"] == "thesis_unbound"


# -- idempotency ------------------------------------------------------------------------------------------------------------------------
def test_a_retry_with_the_same_key_gets_the_first_answer(c, monkeypatch):
    h = {"Idempotency-Key": "upload-1"}
    files = [("files", ("idem.txt", b"Idempotent note: Oct 9, 2026. Credit spreads held.", "text/plain"))]
    first = c.post(f"{WM}/documents", files=files, headers=h)
    again = c.post(f"{WM}/documents", files=files, headers=h)
    assert first.status_code == again.status_code == 202 and again.json() == first.json()
    assert again.headers["location"] == first.headers["location"]
    other = [("files", ("idem.txt", b"Another note entirely.", "text/plain"))]
    problem(c.post(f"{WM}/documents", files=other, headers=h), 422, "idempotency_key_reused")
    problem(c.post(f"{WM}/bundles", json=SUPPORT, headers={"Idempotency-Key": "x" * 256}), 422, "invalid_request")
    tid = {"Idempotency-Key": "thesis-1"}
    a = c.post(f"{WM}/theses", json={"template_id": "S-T2"}, headers=tid)
    b = c.post(f"{WM}/theses", json={"template_id": "S-T2"}, headers=tid)
    assert a.json()["data"] == b.json()["data"]
    # a failure is not remembered: the retry runs again
    bad = {"Idempotency-Key": "thesis-2"}
    problem(c.post(f"{WM}/theses", json={"template_id": "S-nope"}, headers=bad), 404, "thesis_not_found")
    problem(c.post(f"{WM}/theses", json={"template_id": "S-nope"}, headers=bad), 404, "thesis_not_found")
    # keys never expire: they are rows in the lakehouse catalog, with no time on them
    kept = c.app.state.lake.get_idempotency("default", "acme_demo", "/v1/world-models/{world_model_id}/documents",
                                            "upload-1")
    assert kept.status == 202 and kept.headers["location"] == first.headers["location"]
    assert c.post(f"{WM}/documents", files=files, headers=h).json() == first.json()


def test_the_same_content_gets_the_same_answer_whoever_sends_it(c):
    """Documents and bundles are keyed on their content too: with no header, from another caller, with other
    metadata, the same files (names and bytes) get the first answer, and its job stays readable."""
    files = [("files", ("same.txt", b"Content note: Oct 11, 2026. The central bank held.", "text/plain"))]
    first = c.post(f"{WM}/documents", files=files, data={"source": "Desk"})
    assert first.status_code == 202 and first.json()["data"]["result"]["detail"]["results"][0]["new"] is True
    person = SIGNER.bearer(scope="world_model:read documents:create")
    again = c.post(f"{WM}/documents", files=files, data={"source": "Another desk"}, headers=person)
    assert again.json() == first.json() and again.headers["location"] == first.headers["location"]
    with_key = c.post(f"{WM}/documents", files=files, headers={"Idempotency-Key": "fresh-key"})
    assert with_key.json() == first.json()
    assert data(c.get(first.headers["location"]))["id"] == first.json()["data"]["id"]
    renamed = [("files", ("other-name.txt", files[0][1][1], "text/plain"))]
    assert c.post(f"{WM}/documents", files=renamed).json()["data"]["id"] != first.json()["data"]["id"]
    b1 = c.post(f"{WM}/bundles", json={**SUPPORT, "title": "Content-keyed"})
    b2 = c.post(f"{WM}/bundles", json={**SUPPORT, "title": "Content-keyed"}, headers=person)
    assert b1.status_code == b2.status_code == 201 and b1.json() == b2.json()
