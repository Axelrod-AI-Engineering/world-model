"""Retrieval through v1 (Oct 26): `GET …/chunks` ranks passages across documents for a query, filters by document, pages
with a cursor bound to the query, and cites each passage's document."""

from __future__ import annotations

import base64
import json

import pytest

import axelrod_ingest.lake.store as store
from axelrod_wm.api.v1.routes_ingest import retrieval_cursor
from tests.service.helpers import NOTE, OIL_NOTE, RATE_NOTE, WM, data, problem, service, upload
from tests.service.test_openapi_contract import check, op_of

CHUNKS = f"{WM}/chunks"


@pytest.fixture(scope="module")
def c():
    with service() as client:
        yield client


@pytest.fixture(scope="module")
def docs(c):
    return {"note": upload(c, NOTE, "20261005 - Desk Research - Rates note - 1 pages.md", source="Desk",
                           source_type="broker_research"),
            "oil": upload(c, OIL_NOTE, "oil.txt", source="Wire", source_type="news"),
            "rate": upload(c, RATE_NOTE, "rate.txt", source="Wire", source_type="news")}


def ids(body):
    return [(p["document_id"], p["ordinal"]) for p in body["data"]]


def test_a_query_returns_ranked_passages_with_citations(c, docs):
    r = c.get(CHUNKS, params={"q": "central bank policy rate", "context": 1})
    check(op_of("get", "/world-models/{world_model_id}/chunks"), r)             # the contract's PassagePage
    body = r.json()
    top = body["data"][0]
    assert "policy rate" in top["text"] and top["why"][0] == "keyword" and top["scores"]["keyword"] > 0
    assert top["score"] == max(p["score"] for p in body["data"])
    cite = next(p["citation"] for p in body["data"] if p["document_id"] == docs["note"]["document_id"])
    assert cite["publisher"] == "Desk Research" and cite["source_type"] == "broker_research"
    assert cite["event_time"].startswith("2026-10-05") and cite["url"] is None
    assert body["meta"]["version"]["number"] >= 0 and body["meta"]["limit"] == 10
    assert {m["entity_id"] for p in body["data"] for m in p["mentions"]} >= {"central_bank"}


@pytest.mark.parametrize("mode", ["keyword", "semantic", "graph"])
def test_each_mode_alone(c, docs, mode):
    rows = data(c.get(CHUNKS, params={"q": "central bank policy rate", "mode": mode}))
    assert rows and all(p["why"][0] == mode for p in rows)


def test_filters_narrow_the_documents(c, docs):
    news = data(c.get(CHUNKS, params={"q": "central bank", "source_type": "news"}))
    assert {p["document_id"] for p in news} <= {docs["oil"]["document_id"], docs["rate"]["document_id"]}
    one = data(c.get(CHUNKS, params={"q": "central bank", "document_id": docs["rate"]["document_id"]}))
    assert {p["document_id"] for p in one} == {docs["rate"]["document_id"]}
    wire = data(c.get(CHUNKS, params=[("q", "rate"), ("source", "WIRE"), ("source", "nobody")]))
    assert wire and all(p["citation"]["publisher"] == "Wire" for p in wire)
    dated = data(c.get(CHUNKS, params={"q": "central bank", "published_from": "2026-09-04T00:00:00Z",
                                       "published_to": "2026-10-01T00:00:00Z"}))
    assert {p["document_id"] for p in dated} == {docs["rate"]["document_id"]}
    named = data(c.get(CHUNKS, params={"q": "rate", "entity_id": "acme_bank"}))
    assert {p["document_id"] for p in named} == {docs["note"]["document_id"]}


def test_pages_follow_a_cursor_bound_to_the_query(c, docs):
    whole = c.get(CHUNKS, params={"q": "central bank rate", "limit": 4}).json()
    first = c.get(CHUNKS, params={"q": "central bank rate", "limit": 2}).json()
    cursor = first["meta"]["next_cursor"]
    second = c.get(CHUNKS, params={"q": "central bank rate", "limit": 2, "cursor": cursor}).json()
    assert ids(first) + ids(second) == ids(whole)
    problem(c.get(CHUNKS, params={"q": "something else", "cursor": cursor}), 400, "invalid_cursor")
    problem(c.get(CHUNKS, params={"q": "x", "cursor": "not-a-cursor"}), 400, "invalid_cursor")


def test_a_page_never_reaches_past_the_deepest(c, docs, monkeypatch):
    monkeypatch.setattr(store, "MAX_DEPTH", 3)
    first = c.get(CHUNKS, params={"q": "central bank rate", "limit": 2}).json()
    last = c.get(CHUNKS, params={"q": "central bank rate", "limit": 5, "cursor": first["meta"]["next_cursor"]}).json()
    assert len(last["data"]) == 1 and last["meta"]["limit"] == 1 and last["meta"]["next_cursor"] is None
    cursor = first["meta"]["next_cursor"]
    query = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))["q"]
    problem(c.get(CHUNKS, params={"q": "central bank rate", "cursor": retrieval_cursor(3, query)}), 400, "invalid_cursor")


def test_context_and_the_per_document_cap(c, docs):
    rows = data(c.get(CHUNKS, params={"q": "net interest income", "mode": "keyword", "context": 1}))
    assert rows[0]["ordinal"] == 2 and rows[0]["before"] and rows[0]["after"] == []
    capped = data(c.get(CHUNKS, params={"q": "central bank rate", "per_document": 1, "limit": 50}))
    assert len({p["document_id"] for p in capped}) == len(capped)


def test_bad_requests_are_problems(c, docs):
    problem(c.get(CHUNKS, params={"q": ""}), 422, "invalid_request")
    problem(c.get(CHUNKS, params={"q": "x", "mode": "prefix"}), 422, "invalid_request")
    problem(c.get(CHUNKS, params={"q": "x", "context": 4}), 422, "invalid_request")
    problem(c.get(CHUNKS, params=[("q", "x"), *[("document_id", f"d{k}") for k in range(101)]]), 422, "invalid_request")
    problem(c.get("/v1/world-models/nope/chunks", params={"q": "x"}), 404, "world_model_not_found")
