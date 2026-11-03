"""The desk end to end, without the network or Claude: documents in, a reader's figures checked and kept, facts reviewed,
and a world model built into its files (the export scripts are stood in for by tests.conftest.fake_export)."""

from __future__ import annotations

import json
import subprocess
import time
import zipfile
from datetime import UTC, datetime, timedelta

import pytest
import yaml

from axelrod_desk import builds as bx
from axelrod_desk.desk import MAX_FAILURES, STALE
from tests.conftest import REPORT, pdf
from tests.test_reading import obs


def figures(page_quote=("Revenue for the quarter was JPY 120.5 bn", 2)):
    q, page = page_quote
    return {"observations": [
        obs(page=page, quote=q),
        obs(metric_id="acme.units", label="Units sold", value=50000, unit="units", raw={"amount": 50000, "unit": "units"},
            quote="Units sold 50,000"),
        obs(metric_id=None, label="Revenue outlook", kind="company guidance", value=130, unit="JPY bn per quarter",
            page=3, quote="Outlook: revenue of JPY 130 bn next quarter", raw={"amount": 130, "unit": "JPY bn"},
            period={"label": "Q4 2026", "type": "quarter", "start": "2026-10-01", "end": "2026-12-31"}, note="a target"),
        obs(page=9)],
        "themes": [{"theme": "growth", "summary": "s", "citations": [{"page": 1, "quote": "Acme Motors Q3 2026 results"}]}],
        "rounds": 2, "cost": 0.4, "model": "claude-x"}


@pytest.fixture
def read_doc(desk, person):
    a = desk.library.add(pdf(REPORT), "acme_q3.pdf", account=person, publisher="Acme Motors", published="2026-10-30")
    job = desk.claim(person, "laptop")
    desk.submit(job["reading_id"], figures())
    return a.sha256


def test_the_queue_hands_out_the_oldest_document_with_a_company(desk, person):
    assert desk.claim(person) is None
    desk.library.add(b"no company named", "memo.txt", account=person)
    late = desk.library.add(pdf(["Acme Motors later"]), "late.pdf", account=person, published="2026-10-31")
    early = desk.library.add(pdf(["Acme Motors earlier"]), "early.pdf", account=person, published="2026-10-01")
    job = desk.claim(person, "laptop")
    assert job["document"]["sha256"] == early.sha256 and job["company_name"] == "Acme Motors"
    assert job["pages"] == ["Acme Motors earlier"] and job["catalog"][0]["metric_id"] == "acme.revenue"
    assert desk.library.get(early.sha256)["status"] == "reading"
    assert desk.claim(person)["document"]["sha256"] == late.sha256 and desk.claim(person) is None
    status = desk.queue_status()
    assert status["documents"] == {"needs company": 1, "reading": 2} and len(status["running"]) == 2


def test_a_stale_claim_is_handed_out_again(desk, person):
    desk.library.add(pdf(["Acme Motors"]), "a.pdf", account=person)
    job = desk.claim(person)
    old = (datetime.now(UTC) - STALE - timedelta(minutes=1)).replace(microsecond=0).isoformat()
    desk.db.update("readings", "id", job["reading_id"], {"started_at": old})
    again = desk.claim(person)
    assert again["document"]["sha256"] == job["document"]["sha256"] and again["reading_id"] != job["reading_id"]
    assert desk.db.one("select status from readings where id = ?", [job["reading_id"]])["status"] == "abandoned"
    with pytest.raises(ValueError, match="abandoned"):
        desk.submit(job["reading_id"], {})


def test_submitted_figures_are_checked_again_and_kept(desk, person, read_doc):
    d = desk.document(read_doc)
    assert d["document"]["status"] == "read" and [r["ok"] for r in d["records"]] == [1, 1, 1, 0]
    assert d["records"][3]["problems"] and d["themes"][0]["theme"] == "growth" and d["copies"] == []
    r = d["readings"][0]
    assert (r["status"], r["accepted"], r["rejected"], r["rounds"], r["model"]) == ("done", 3, 1, 2, "claude-x")
    assert d["uploads"][0]["name"] == "Ada"
    with pytest.raises(KeyError):
        desk.submit(999, {})
    with pytest.raises(KeyError):
        desk.document("0" * 64)


def test_a_failed_reading_puts_the_document_back_until_it_fails_too_often(desk, person):
    a = desk.library.add(pdf(["Acme Motors"]), "a.pdf", account=person)
    for k in range(MAX_FAILURES):
        job = desk.claim(person)
        res = desk.fail(job["reading_id"], "Claude Code is not signed in")
        assert res["document_status"] == ("failed" if k == MAX_FAILURES - 1 else "new")
    assert desk.claim(person) is None
    assert desk.reread(a.sha256)["status"] == "new"
    loose = desk.library.add(b"words", "memo.txt", account=person)
    with pytest.raises(ValueError, match="company"):
        desk.reread(loose.sha256)
    with pytest.raises(KeyError):
        desk.reread("0" * 64)


def test_facts_of_read_documents_and_their_reviews(desk, person, read_doc):
    fs = desk.facts("acme")
    assert {f["label"] for f in fs} == {"Revenue, Q3", "Units sold", "Revenue outlook"} and not any(f["conflict"] for f in fs)
    key = next(f["key"] for f in fs if f["label"] == "Revenue, Q3")
    assert desk.review(key, "approve", person, "checked")["decision"] == "approve"
    assert next(f for f in desk.facts("acme") if f["key"] == key)["review"]["note"] == "checked"
    desk.review(key, "clear", person)
    assert next(f for f in desk.facts("acme") if f["key"] == key)["review"] is None
    assert desk.facts("acme", conflicts=True) == [] and desk.facts("rival", classes=["company"]) == []
    with pytest.raises(ValueError):
        desk.review(key, "maybe", person)
    with pytest.raises(KeyError):
        desk.facts("ghost")


def test_world_models_belong_to_their_person(desk, person):
    from axelrod_desk import accounts

    other = accounts.create(desk.db, "k@example.com", "K", "another long one")
    w = desk.save_world_model(person, {"name": " Autos ", "groups": ["sector:autos"], "classes": ["company", "sell_side"],
                                       "apply": True})
    assert (w["name"], w["apply"], w["companies"]) == ("Autos", True, [])
    w = desk.save_world_model(person, {"name": "Acme", "companies": ["acme"], "classes": ["company"]}, w["id"])
    assert desk.world_models(person)[0]["name"] == "Acme" and desk.world_models(other) == []
    for body, why in (({"name": ""}, "name"), ({"name": "x", "companies": ["acme"]}, "source classes"),
                      ({"name": "x", "companies": ["acme"], "classes": ["rumour"]}, "source classes"),
                      ({"name": "x", "classes": ["company"]}, "at least one"),
                      ({"name": "x", "companies": ["ghost"], "classes": ["company"]}, "ghost")):
        with pytest.raises(ValueError, match=why):
            desk.save_world_model(person, body)
    with pytest.raises(KeyError):
        desk.world_model(w["id"], other)
    with pytest.raises(KeyError):
        desk.build(1, person)
    desk.delete_world_model(w["id"], person)
    assert desk.world_models(person) == []


def test_a_build_writes_the_construction_bundles_exports_corpus_and_zip(desk, person, read_doc):
    note = desk.library.add(pdf(["Acme Motors: Nomura view", "Revenue for the quarter was JPY 120.5 bn"]),
                            "20261031 - Nomura - 7203_JP - Acme - 2 pages.pdf", account=person, published="2026-10-31")
    job = desk.claim(person)
    desk.submit(job["reading_id"], {"observations": [obs(kind="broker-reported actual"),
                                                     obs(kind="broker rating", value=None, metric_id=None, page=1,
                                                         quote="Acme Motors: Nomura view")], "themes": []})
    again = desk.library.add(pdf(["Acme Motors press release", "Revenue for the quarter was JPY 120.5 bn"]), "press.pdf",
                             account=person, publisher="Acme Motors", published="2026-10-31")
    job = desk.claim(person)
    desk.submit(job["reading_id"], {"observations": [obs(), obs(metric_id="acme.units", label="Units", value=1, unit="pct",
                                                                 quote="Revenue for the quarter was JPY 120.5 bn",
                                                                 raw={"amount": 120.5, "unit": "x"})], "themes": []})
    fs = {f["label"] + "/" + f["speaker"]: f for f in desk.facts("acme")}
    desk.review(fs["Revenue, Q3/company"]["key"], "approve", person)
    desk.review(fs["Units sold/company"]["key"], "approve", person)
    desk.review(fs["Units/company"]["key"], "approve", person)
    desk.review(fs["Revenue outlook/company"]["key"], "reject", person)
    desk.review(fs["Revenue, Q3/nomura"]["key"], "approve", person)
    w = desk.save_world_model(person, {"name": "Acme with sell-side", "companies": ["acme"], "groups": ["group:mine"],
                                       "classes": ["company", "sell_side"], "apply": True})
    b = desk.start_build(w["id"], person)
    while desk.build(b["id"], person)["status"] in ("queued", "running"):
        time.sleep(0.05)
    b = desk.build(b["id"], person)
    assert b["status"] == "done", b["error"]
    out = desk.s.builds / f"{b['id']:04d}"
    s = b["summary"]
    assert s["companies"] == ["acme", "solo"] and s["documents"] == 3 and s["apply"]
    assert s["counts"] == {"applied": 2, "approved, not applied: not a company-reported figure": 1,
                           "approved, not applied: unit is not the metric's": 1, "held out (no value)": 1, "new figures": 4,
                           "rejected": 1}
    rep = json.loads((out / "construction" / "acme" / "repair.json").read_text())
    new = {(o["label"], o["scope"]["view"]): o for o in rep["observations"] if o["observation_id"].startswith("DESK_")}
    rev = new[("Revenue, Q3", "company")]
    assert rev["kind"] == "reported actual" and len(rev["citations"]) == 1 and rev["source"]["page"] == 2
    assert new[("Revenue, Q3", "broker-reported actual")]["kind"] == "broker-reported actual"
    assert new[("Units sold", "company")]["selected_baseline"] is False
    src = json.loads((out / "construction" / "acme" / "sources.json").read_text())["sources"]
    assert {k for k in src if k.startswith("desk.")} == {f"desk.{s[:12]}" for s in (read_doc, note.sha256, again.sha256)}
    bundles = sorted((out / "bundles").glob("*.json"))
    items = [json.loads(p.read_text())["items"][0] for p in bundles]
    assert [len(i["signals"]) for i in items] == [2, 0, 0] and items[1]["source_type"] in ("filing", "broker_research")
    scen = yaml.safe_load((desk.s.scenarios / "scenarios" / f"desk_{b['id']:04d}" / "scenario.yaml").read_text())
    assert scen["focus"] == {"base": "unified", "companies": ["acme", "solo"]}
    assert json.loads((out / "wm-export.json").read_text())["remaps"] == ["old/=new/", f"data/={desk.s.data}/"]
    corpus = json.loads((out / "corpus.json").read_text())
    assert [len(d["pages"]) for d in corpus["documents"]] == [3, 2, 2]
    names = zipfile.ZipFile(b["zip"]).namelist()
    assert {"wm-export.json", "corpus.json", "summary.json"} <= set(names) and any(n.endswith("00_START_HERE.md") for n in names)
    assert "HTTP Request" not in (out / "export_v4.log").read_text()


def test_a_build_beside_the_baseline_carries_figures_but_applies_none(desk, person, read_doc):
    base = desk.library.add(pdf(["Acme Motors filing", "Revenue for the quarter was JPY 100 bn"]), "h1.pdf", account=person,
                            publisher="Acme Motors")
    job = desk.claim(person)
    desk.submit(job["reading_id"], {"observations": [obs(value=100.0, quote="Revenue for the quarter was JPY 100 bn",
                                                         raw={"amount": 100, "unit": "JPY bn"},
                                                         period={"label": "Q2", "type": "quarter", "start": "2026-04-01",
                                                                 "end": "2026-06-30"})], "themes": []})
    w = desk.save_world_model(person, {"name": "Acme", "companies": ["acme"], "classes": ["company"]})
    b = desk.run_build(desk.db.insert("builds", {"world_model_id": w["id"], "account_id": person["id"], "status": "queued",
                                                 "started_at": "t"}))
    assert b["status"] == "done", b["error"]
    counts = b["summary"]["counts"]
    assert counts["citations added to base figures"] == 1 and "applied" not in counts
    rep = json.loads((desk.s.builds / f"{b['id']:04d}" / "construction" / "acme" / "repair.json").read_text())
    base_obs = next(o for o in rep["observations"] if o["observation_id"] == "OBS_ACME_REV_Q2")
    assert base_obs["citations"][0]["source_id"] == f"desk.{base.sha256[:12]}"
    days = sorted(p.name[:10] for p in (desk.s.builds / f"{b['id']:04d}" / "bundles").glob("*.json"))
    assert sorted(days) == sorted(["2026-10-30", datetime.now(UTC).date().isoformat()])     # undated: the day it was added


def test_a_company_without_a_construction_has_no_baseline_and_its_figures_are_held_out(desk, person):
    loans = "Loans to customers were USD 41.2 bn"
    desk.library.add(pdf(["Solo Bank results", loans]), "solo_q3.pdf", account=person, publisher="Solo Bank",
                     published="2026-10-30", company="solo")
    job = desk.claim(person)
    desk.submit(job["reading_id"], {"observations": [obs(metric_id="solo.loans", label="Loans", value=41.2, unit="USD bn",
                                                         quote=loans, raw={"amount": 41.2, "unit": "USD bn"},
                                                         period={"label": "30 Sep 2026", "type": "point",
                                                                 "start": "2026-09-30", "end": "2026-09-30"})],
                                    "themes": []})
    assert [f["value"] for f in desk.facts("solo")] == [41.2]
    w = desk.save_world_model(person, {"name": "Solo", "companies": ["solo"], "classes": ["company"]})
    b = desk.run_build(desk.db.insert("builds", {"world_model_id": w["id"], "account_id": person["id"], "status": "queued",
                                                 "started_at": "t"}))
    assert b["status"] == "done", b["error"]
    assert b["summary"]["counts"] == {"held out (no construction for the company)": 1}
    folder = desk.s.builds / f"{b['id']:04d}" / "construction" / "solo"
    assert sorted(p.name for p in folder.iterdir()) == ["citations.json", "sources.json"]


def test_a_failed_export_fails_the_build_with_its_log(desk, person, read_doc):
    desk.builder.run_cmd = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 2, "", "Traceback: no scenario")
    w = desk.save_world_model(person, {"name": "Acme", "companies": ["acme"], "classes": ["company"]})
    bid = desk.db.insert("builds", {"world_model_id": w["id"], "account_id": person["id"], "status": "queued", "started_at": "t"})
    desk.run_build(bid)
    b = desk.run_build(bid)                                                       # a rebuild clears the old folder first
    assert b["status"] == "failed" and "no scenario" in b["error"] and "v4.1.4 export" in b["error"]


def test_the_build_helpers():
    assert bx.slug("BYD, CATL & Hyundai!") == "byd_catl_hyundai" and bx.slug("!!!") == "build"
    assert bx.view_of({"kind": "broker estimate revision"}, "estimate") == "broker estimate"
    assert bx.view_of({"kind": "broker estimate"}, "estimate before results") == "broker estimate before results"
    assert bx.view_of({"kind": "third party estimate"}, "estimate") == "third party"
    assert bx.unit_matches("RMB bn per quarter", "rmb bn/quarter") and not bx.unit_matches("", "")
    assert not bx.unit_matches("units", "pct")


def test_a_selection_without_companies_cannot_build(desk, person):
    with pytest.raises(bx.BuildError):
        desk.builder.build(1, {"name": "x", "companies": [], "groups": [], "classes": ["company"], "apply": 0})


def test_builds_queue_behind_one_worker_and_a_build_without_a_client_core(tmp_path, person):
    from axelrod_desk import settings
    from axelrod_desk.desk import Desk
    from tests.conftest import fake_export, write_home

    d = Desk(settings.load(write_home(tmp_path / "h", client_core=False)), poppler=False, run=fake_export)
    try:
        a = {"id": d.db.insert("accounts", {"email": "e@x.y", "name": "E", "pw": "x", "admin": 1, "created_at": "t"})}
        w = d.save_world_model(a, {"name": "Rival", "companies": ["rival"], "classes": ["company"]})
        first, second = d.start_build(w["id"], a), d.start_build(w["id"], a)
        while d.build(second["id"], a)["status"] in ("queued", "running") or d.build(first["id"], a)["status"] == "queued":
            time.sleep(0.05)
        assert d.build(second["id"], a)["status"] == "done"
        assert not any("--client-core" in str(x) for x in (d.s.builds / f"{second['id']:04d}" / "export_v4.log").read_text())
    finally:
        d.close()
