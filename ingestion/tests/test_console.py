"""The ingestion console (Oct 24): its page is served open, every JSON route is under the bearer token, the lake tables filter
and page, search runs in every mode, a dry run writes nothing, and the JS only calls routes the app has. Every document is
invented."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import axelrod_ingest.console as console
from axelrod_ingest.lake.embed import HashingEmbedder
from axelrod_ingest.lake.sqlite import SQLiteLake
from axelrod_ingest.pack import lake_digest
from axelrod_ingest.pipeline import Ingestor
from axelrod_ingest.service import create_ingest_app
from tests.conftest import acme_graph
from tests.where import ACME_WORLD_VIEW

NOW = datetime(2026, 10, 6, 12, tzinfo=UTC)
T = "desk"
AUTH = {"Authorization": "Bearer console-token"}
NOTE = (b"# Policy watch\n\nThe central bank raised its policy rate by 25bp to 4.25%. Government bonds 10Y yield rose "
        b"10bp, and the dollar index rose 2%.\n\nHigher government bonds 10Y yield lifts Acme Re domestic P&C profit.\n")
BANKS = (b"<html><head><title>Banks</title></head><body><p>Acme Bank's net interest income rose 4% in Q3. "
         b"The central bank policy rate weighs on Acme Bank net interest income.</p></body></html>")
ZH = "截至2025年12月31日止年度的合并业绩。营业收入为人民币777,102百万元。".encode()
UI = Path(console.__file__).parent / "console"


class Lake:
    def __init__(self, tmp_path, **kw):
        self.store = SQLiteLake(tmp_path / "lake")
        self.app = create_ingest_app(self.store, HashingEmbedder(), None, None, "console-token", clock=lambda: NOW,
                                     timer=lambda: 0.0, **kw)
        self.http = TestClient(self.app, base_url="http://ingest")
        ing = Ingestor(self.store, HashingEmbedder(), clock=lambda: NOW, timer=lambda: 0.0)
        self.ids = {name: ing.ingest_file(T, data, name, acme_graph(), source_type=st).document.id
                    for name, data, st in (("policy_2026-10-05.md", NOTE, "broker_research"), ("banks.html", BANKS, "news"),
                                           ("zh.txt", ZH, "other"), ("broken.pdf", b"nope", "other"))}

    def get(self, path, **params):
        return self.http.get(path, params=params, headers=AUTH)

    def post(self, path, **body):
        return self.http.post(path, json=body, headers=AUTH)

    def debug(self, meta, **files):
        return self.http.post("/v1/debug/stages", headers=AUTH, data=meta, files=files)


@pytest.fixture
def lake(tmp_path):
    return Lake(tmp_path)


def test_the_page_is_open_and_holds_the_four_tabs(lake):
    for path in ("/", "/ui"):
        r = lake.http.get(path)
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
        assert "script-src 'self'" in r.headers["content-security-policy"] and r.headers["cache-control"] == "no-store"
        for tab in ("lake", "add", "search", "debug"):
            assert f'data-tab="{tab}"' in r.text and f'id="tab-{tab}"' in r.text
    assert lake.http.get("/ui/app.js").headers["content-type"].startswith("text/javascript")
    assert lake.http.get("/ui/app.css").headers["content-type"].startswith("text/css")
    assert lake.http.get("/ui/app.js").content == (UI / "app.js").read_bytes()
    assert lake.http.get("/ui/other.js").status_code == 404


def test_every_json_route_needs_the_bearer_token(lake):
    some = lake.ids["zh.txt"]
    routes = [("GET", "/v1/tenants"), ("GET", f"/v1/lake/{T}/summary"), ("GET", f"/v1/lake/{T}/documents"),
              ("GET", f"/v1/lake/{T}/documents/{some}"), ("GET", f"/v1/lake/{T}/documents/{some}/raw"),
              ("POST", "/v1/search"), ("POST", "/v1/similar"), ("POST", "/v1/debug/stages")]
    for method, path in routes:
        for headers in ({}, {"Authorization": "Bearer wrong"}):
            r = lake.http.request(method, path, headers=headers, json={})
            assert r.status_code == 401 and r.json()["title"] == "Authentication required"
            assert r.headers["www-authenticate"] == "Bearer" and "console-token" not in r.text


def test_the_tenants_and_the_summary(lake):
    assert lake.get("/v1/tenants").json() == {"tenants": [T]}
    s = lake.get(f"/v1/lake/{T}/summary").json()
    assert s["stats"]["documents"] == 4 and s["embedder"] == {"name": "hashing-256", "dim": 256}
    assert s["by_status"] == {"extracted": 3, "failed": 1}
    assert sum(s["by_type"].values()) == 4 and s["by_type"]["unknown"] == 1          # the failed file was never typed
    assert s["by_language"]["en"] == 2 and s["by_language"]["zh"] == 1 and s["by_language"]["unknown"] == 1
    assert lake.get("/v1/lake/nobody/summary").json()["stats"]["documents"] == 0


def test_the_document_table_filters_sorts_and_pages(lake):
    def table(**kw):
        r = lake.get(f"/v1/lake/{T}/documents", **kw)
        assert r.status_code == 200
        return r.json()
    everything = table(order="ingested_at", dir="asc")
    assert everything["total"] == 4 and everything["limit"] == 50
    row = next(d for d in everything["documents"] if d["filename"] == "policy_2026-10-05.md")
    assert row["status"] == "extracted" and row["chunks"] >= 1 and row["language"] == "en"
    assert row["published_source"] == "filename" and row["published_at"].startswith("2026-10-05") and row["size"] == len(NOTE)
    # newest first (the end of the ascending order read backwards) and oldest first are mirror images
    desc, asc = table(dir="desc"), table(dir="asc")
    assert [d["id"] for d in desc["documents"]] == [d["id"] for d in asc["documents"]][::-1]
    # paging, in either direction, covers every document once
    for direction in ("asc", "desc"):
        seen = []
        for offset in (0, 3):
            seen += [d["id"] for d in table(dir=direction, limit=3, offset=offset)["documents"]]
        assert seen == [d["id"] for d in table(dir=direction)["documents"]] and len(set(seen)) == 4
    assert table(offset=9)["documents"] == [] and table(offset=9)["total"] == 4
    # filters
    assert [d["filename"] for d in table(status="failed")["documents"]] == ["broken.pdf"]
    assert {d["filename"] for d in table(language="zh")["documents"]} == {"zh.txt"}
    assert {d["filename"] for d in table(type="news")["documents"]} <= {"banks.html"}
    assert table(q="POLICY")["total"] == 1 and table(q="banks")["total"] == 1       # file name, case-insensitive
    assert table(q="nothing like this")["documents"] == []
    paged = table(status="extracted", limit=2, offset=1, dir="asc", order="event_time")
    assert paged["total"] == 3 and len(paged["documents"]) == 2
    assert table(status="extracted", language="zh", q="zh")["total"] == 1
    # the title is searched too
    lake.store.update_document(T, lake.ids["zh.txt"], title="Annual results of the group")
    assert table(q="annual results")["total"] == 1
    for bad in ({"dir": "up"}, {"order": "size"}, {"limit": 0}, {"limit": 501}, {"offset": -1}):
        assert lake.get(f"/v1/lake/{T}/documents", **bad).status_code == 422


def test_a_document_in_full_and_its_raw_file(lake):
    pid = lake.ids["policy_2026-10-05.md"]
    d = lake.get(f"/v1/lake/{T}/documents/{pid}").json()
    assert d["document"]["id"] == pid and d["text"].startswith("# Policy watch") and d["parser"].startswith("markdown/")
    assert d["chunks"] and d["document"]["meta"]["doc_type"]["type"] and d["document"]["meta"]["dates"]
    assert d["mentions"] >= 1 and d["signals"] >= 1 and d["bundles"][0]["signals"] == d["signals"]
    failed = lake.get(f"/v1/lake/{T}/documents/{lake.ids['broken.pdf']}").json()
    assert failed["document"]["status"] == "failed" and failed["text"] == "" and failed["chunks"] == []
    raw = lake.get(f"/v1/lake/{T}/documents/{pid}/raw")
    assert raw.content == NOTE and raw.headers["content-disposition"] == "attachment; filename*=UTF-8''policy_2026-10-05.md"
    for path in (f"/v1/lake/{T}/documents/nope", f"/v1/lake/{T}/documents/nope/raw", f"/v1/lake/other/documents/{pid}",
                 f"/v1/lake/other/documents/{pid}/raw"):
        r = lake.get(path)
        assert r.status_code == 404 and r.headers["content-type"].startswith("application/problem+json")
        assert r.json()["title"] == "Not found" and r.json()["detail"]


def test_search_runs_in_every_mode_and_graph_needs_a_world_view(lake):
    wv = json.dumps(json.loads(ACME_WORLD_VIEW.read_text())["world_view"])
    for mode in ("keyword", "prefix", "semantic", "hybrid"):
        r = lake.post("/v1/search", tenant=T, q="policy rate", mode=mode, limit=5)
        assert r.status_code == 200 and r.json()["mode"] == mode
        hits = r.json()["hits"]
        assert hits and all(h["kind"] == "chunk" and h["text"] and h["title"] and "event_time" in h for h in hits)
    kw = lake.post("/v1/search", tenant=T, q="policy rate", mode="keyword").json()["hits"]
    assert kw[0]["ord"] is not None and "page" in kw[0] and kw[0]["score"] >= kw[-1]["score"] and kw[0]["why"]
    assert lake.post("/v1/search", tenant=T, q="x", mode="graph").status_code == 422
    graph = lake.post("/v1/search", tenant=T, q="Acme Bank", mode="graph", world_view=wv).json()["hits"]
    assert {h["kind"] for h in graph} >= {"entity"} and any(h["kind"] == "chunk" for h in graph)
    names = lake.post("/v1/search", tenant=T, q="Acme", mode="prefix", world_view=wv).json()["hits"]
    assert names[0]["kind"] == "entity" and names[0]["why"] == ["name prefix"]
    assert not any(h["kind"] == "entity" for h in lake.post("/v1/search", tenant=T, q="Acme", mode="prefix").json()["hits"])
    assert lake.post("/v1/search", tenant=T, q="x", mode="fuzzy").status_code == 422
    assert lake.post("/v1/search", tenant=T, q="x", limit=0).status_code == 422
    assert lake.post("/v1/search", tenant=T, q="x", limit=201).status_code == 422
    assert lake.post("/v1/search", tenant=T).status_code == 422                     # q is required


def test_a_stale_hit_is_passed_through_as_the_search_gave_it():
    hit = {"kind": "chunk", "doc_id": "gone", "ord": 0, "score": 1.0, "why": ["x"], "text": "kept"}
    store = SQLiteLake.__new__(SQLiteLake)
    store.get_document = lambda tenant, doc: None
    store.get_chunks = lambda tenant, doc: []
    assert console._hit(store, T, hit) == hit
    assert console._hit(store, T, {"kind": "entity", "text": "Acme"}) == {"kind": "entity", "text": "Acme"}


def test_similar_passages_exclude_the_chunk_itself(lake):
    pid = lake.ids["policy_2026-10-05.md"]
    chunks = lake.get(f"/v1/lake/{T}/documents/{pid}").json()["chunks"]
    r = lake.post("/v1/similar", tenant=T, doc_id=pid, ord=chunks[-1]["ord"], limit=3)
    assert r.status_code == 200
    hits = r.json()["hits"]
    assert 1 <= len(hits) <= 3 and all((h["doc_id"], h["ord"]) != (pid, chunks[-1]["ord"]) for h in hits)
    assert hits[0]["why"] == ["similar"] and hits[0]["text"] and hits[0]["score"] >= hits[-1]["score"]
    assert lake.post("/v1/similar", tenant=T, doc_id=pid, ord=99).status_code == 404
    assert lake.post("/v1/similar", tenant=T, doc_id="nope", ord=0).status_code == 404
    assert lake.post("/v1/similar", tenant=T, doc_id=pid, ord=0, limit=0).status_code == 422


def test_the_debug_route_runs_a_stored_document_and_an_upload_and_writes_nothing(lake):
    before = lake_digest(lake.store, T)
    pid = lake.ids["policy_2026-10-05.md"]
    stored = lake.post("/v1/debug/stages", tenant=T, doc_id=pid)
    assert stored.status_code == 200
    res = stored.json()
    assert res["doc_id"] == pid and [s["id"] for s in res["stages"]] == ["store", "parse", "type", "chunk", "index", "duplicates"]
    assert res["stages"][0]["data"]["stored"]["status"] == "extracted"
    doc = lake.store.get_document(T, pid)
    assert res["stages"][2]["data"]["dates"] == doc.meta["dates"] and res["stages"][2]["data"]["doc_type"] == doc.meta["doc_type"]
    assert res["stages"][4]["data"]["nearest"] is not None
    meta = json.dumps({"tenant": T, "source_type": "news", "published_at": "2026-09-01T00:00:00Z", "mime": "text/markdown"})
    up = lake.debug({"meta": meta}, file=("new.md", NOTE + b"more.\n"))
    assert up.status_code == 200 and up.json()["stages"][0]["data"]["stored"] is None
    assert up.json()["stages"][2]["data"]["published_at"].startswith("2026-09-01")
    assert up.json()["stages"][2]["data"]["source_type"] == "news"
    assert lake.debug({"meta": json.dumps({"tenant": T})}, file=("x.pdf", b"nope")).json()["stopped"]["stage"] == "parse"
    assert lake_digest(lake.store, T) == before and lake.store.stats(T)["documents"] == 4


def test_the_debug_route_refuses_what_it_cannot_run(lake):
    meta = json.dumps({"tenant": T})
    assert lake.post("/v1/debug/stages", tenant=T, doc_id="nope").status_code == 404
    assert lake.post("/v1/debug/stages", tenant=T).status_code == 422
    assert lake.debug({"meta": meta}).status_code == 422                                          # no file
    assert lake.debug({}, file=("a.md", NOTE)).status_code == 422                                 # no meta
    assert lake.debug({"meta": json.dumps({"tenant": T, "x": 1})}, file=("a.md", NOTE)).status_code == 422
    assert lake.debug({"meta": json.dumps({"source_type": "gossip"})}, file=("a.md", NOTE)).status_code == 422
    assert lake.debug({"meta": "file"}, file=("a.md", NOTE)).status_code == 422
    assert lake.http.post("/v1/debug/stages", headers=AUTH, data={"meta": meta, "file": "text"}).status_code == 422


def test_the_size_limit_applies_to_ingest_and_the_dry_run(tmp_path):
    small = Lake(tmp_path, max_bytes=len(NOTE) - 1)
    r = small.debug({"meta": json.dumps({"tenant": T})}, file=("a.md", NOTE))
    assert r.status_code == 413 and r.json()["title"] == "Payload too large" and r.json()["code"] == "payload_too_large"
    wv = acme_graph().to_json().encode()
    meta = {"meta": json.dumps({"tenant": T})}
    ing = small.http.post("/v1/ingest", headers=AUTH, data=meta, files={"world_view": ("w.json", wv), "files": ("a.md", NOTE)})
    assert ing.status_code == 413 and "a.md" in ing.json()["detail"]
    ok = small.http.post("/v1/ingest", headers=AUTH, data=meta, files={"world_view": ("w.json", wv), "files": ("a.md", NOTE[:50])})
    assert ok.status_code == 200


def test_an_empty_world_view_stores_and_chunks_but_recognizes_nothing(lake):
    empty = b'{"entities":[],"values":[],"links":[]}'
    meta = json.dumps({"tenant": "fresh", "source": "Desk", "source_type": "broker_research", "inverted": []})
    r = lake.http.post("/v1/ingest", headers=AUTH, data={"meta": meta},
                       files={"world_view": ("world_view.json", empty), "files": ("n.md", NOTE)})
    res = r.json()["results"][0]
    assert r.status_code == 200 and res["new"] and res["document"]["status"] == "extracted"
    assert res["chunks"] >= 1 and res["mentions"] == 0 and res["signals"] == 0 and "store" in res["timings"]
    assert lake.get("/v1/tenants").json()["tenants"] == [T, "fresh"]


# -- the JS smoke test ---------------------------------------------------------------------------------------------------
def test_every_route_the_page_calls_exists(lake):
    js = (UI / "app.js").read_text()
    have = {(m.upper(), re.sub(r"\{[^}]+\}", "{}", path)) for path, ops in lake.app.openapi()["paths"].items() for m in ops}

    def shape(path):
        return re.sub(r"\$\{[^}]+\}", "{}", path)

    # api("/v1/...") calls, with their method; fetch( appears once, inside api()
    calls = re.findall(r"""api\(\s*([`"'])(/v1/[^`"'?]*)[^`"']*\1(?:,\s*\{([^}]*)\})?""", js)
    assert js.count("fetch(") == 1 and calls
    for _q, path, opts in calls:
        assert ("POST" if "POST" in opts else "GET", shape(path)) in have, path
    # api(lakePath(tenant, "/suffix")) calls are under /v1/lake/{tenant}
    lakes = re.findall(r"""api\(lakePath\([^,()]+,\s*([`"'])([^`"']*)\1\)(?:[^)]*\{[^}]*(blob)[^}]*\})?""", js)
    assert lakes
    for _q, suffix, _blob in lakes:
        assert ("GET", shape("/v1/lake/{}" + suffix)) in have, suffix
    called = {p for _q, p, _o in calls}
    assert called >= {"/v1/tenants", "/v1/search", "/v1/similar", "/v1/ingest", "/v1/debug/stages"}
    assert {s for _q, s, _b in lakes} >= {"/summary", "/documents", "/documents/${encodeURIComponent(id)}/raw"}


def test_the_page_never_turns_data_into_markup_or_keeps_the_token_anywhere_else():
    js = (UI / "app.js").read_text()
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(|new Function", js)
    assert "localStorage" not in js and "console.log" not in js
    assert re.search(r"try \{[^}]*sessionStorage", js) and "location.hash" not in js and "location.search" not in js
    html = (UI / "index.html").read_text()
    assert re.findall(r"<script\b[^>]*>", html) == ['<script src="/ui/app.js">']
    assert "<style" not in html and " style=" not in html and not re.search(r"""(?:src|href)=["']https?:""", html)
    assert "http://" not in js and "https://" not in (UI / "app.css").read_text()
