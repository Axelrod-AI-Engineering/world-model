"""The MCP server (api/mcp.py), through the SDK's own client over Streamable HTTP at /mcp: every tool answers from the
service's routes as the caller's API key, and every failure comes back as a tool error naming core's error code."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import httpx2
import pytest
from fastapi.testclient import TestClient
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from axelrod_wm.api.app import create_app
from axelrod_wm.api.mcp import _headers
from axelrod_wm.repo.snapshots import MemoryBackend

KEY = "k" * 32
NOTE = ("Rates note, October 5, 2026.\n\n"
        "The BoJ raised its policy rate by 25bp to 1.25% on a 7-2 vote. USD/JPY fell to 152 as the yen strengthened.")


@pytest.fixture(scope="module")
def client():
    mp = pytest.MonkeyPatch()
    mp.setenv("WORLD_MODEL_API_KEYS", f"harness:{KEY}:default")
    app = create_app(scenario="sally_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        yield c
    mp.undo()


def session(client, body, key: str = KEY):
    """Run `body(session)` in an MCP client session over the app's /mcp route."""

    async def main():
        http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=client.app), base_url="http://wm",
                                  headers={"Authorization": f"Bearer {key}"})
        async with streamable_http_client("http://wm/mcp", http_client=http) as streams:
            async with ClientSession(streams[0], streams[1]) as s:
                await s.initialize()
                return await body(s)

    return client.portal.call(main)


def calls(client, *steps):
    """Call tools in order; each step is (name, args) or a function of the results so far giving (name, args)."""

    async def body(s):
        out = []
        for step in steps:
            name, args = step(out) if callable(step) else step
            r = await s.call_tool(name, args)
            out.append((r.is_error, r.content[0].text))
        return out

    return session(client, body)


def code_of(text: str) -> str:
    """The error code after the SDK's "Error executing tool <name>: " prefix."""
    return text.split(": ", 1)[1].split(":", 1)[0] if text.startswith("Error executing tool") else text.split(":", 1)[0]


def ok(result) -> dict:
    is_error, text = result
    assert not is_error, text
    return json.loads(text)


def test_the_server_lists_every_tool_with_annotations(client):
    async def body(s):
        return (await s.list_tools()).tools

    tools = {t.name: t for t in session(client, body)}
    assert len(tools) == 17 and all(n.startswith("world_model_") for n in tools)
    assert tools["world_model_query"].annotations.read_only_hint is True
    assert tools["world_model_import_bundle"].annotations.read_only_hint is False


def test_reads(client):
    state, query, pinned, nodes, ent, val, tax, ctx = calls(
        client, ("world_model_state", {}),
        ("world_model_query", {"q": "Bank of Japan", "depth": 1}),
        ("world_model_query", {"node_ids": ["boj"], "version": 1, "as_of": "2026-09-01T00:00:00Z", "limit": 5}),
        ("world_model_search_nodes", {"q": "Tok", "limit": 3}),
        ("world_model_get_entity", {"entity_id": "boj"}),
        ("world_model_get_value", {"value_id": "boj.policy_rate"}),
        ("world_model_taxonomy", {}),
        ("world_model_context_v4", {}))
    assert ok(state)["caller"] == "harness" and ok(state)["state"]["scenario"] == "sally_demo"
    assert ok(query)["entities"] and ok(pinned)["state"]["version"] >= 1
    assert ok(nodes)["nodes"] and ok(ent)["entity"]["id"] == "boj" and ok(val)["value"]["id"] == "boj.policy_rate"
    assert ok(tax)["concepts"] and ok(ctx)["manifest"]["schema_version"] == "v4.1.4"


def test_ingest_search_and_import_through_review(client):
    b64 = base64.b64encode(NOTE.encode()).decode()
    up, again, docs, search = calls(
        client,
        ("world_model_ingest_document", {"filename": "2026-10-05_note.md", "content_base64": b64, "source": "Desk",
                                         "source_type": "broker_research", "published_at": "2026-10-05T00:00:00Z"}),
        ("world_model_ingest_document", {"filename": "copy.md", "text": NOTE}),
        ("world_model_list_documents", {"order": "ingested_at"}),
        ("world_model_search", {"q": "policy rate", "mode": "keyword"}))
    res = ok(up)["results"][0]
    assert res["new"] is True and ok(again)["results"][0]["new"] is False
    assert ok(docs)["documents"] and ok(search)["hits"]
    bid = res["bundle"]["id"]
    bundle, imported, pending = calls(
        client, ("world_model_get_bundle", {"bundle_id": bid}),
        ("world_model_import_bundle", {"bundle_id": bid, "review": "queue"}),
        ("world_model_list_proposals", {"status": "pending"}))
    assert ok(bundle)["id"] == bid and ok(imported)["pending_proposals"]
    first = ok(pending)["proposals"][0]["id"]
    approve, rejected_no_note = calls(
        client, ("world_model_decide_proposal", {"proposal_id": first, "decision": "approve", "note": "fine"}),
        ("world_model_decide_proposal", {"proposal_id": first, "decision": "reject"}))
    assert ok(approve)["proposal_id"] == first
    assert rejected_no_note[0] and code_of(rejected_no_note[1]) in ("already_decided", "note_required")
    while True:
        (left,) = calls(client, ("world_model_list_proposals", {}))
        ids = [p["id"] for p in ok(left)["proposals"]]
        if not ids:
            break
        calls(client, *[("world_model_decide_proposal", {"proposal_id": i, "decision": "approve"}) for i in ids])


def test_forecasts(client):
    fc, got, brief, ctx = calls(
        client, ("world_model_forecast", {"thesis_id": "S-T3"}),
        lambda out: ("world_model_get_forecast", {"forecast_id": ok(out[0])["forecast"]["id"]}),
        lambda out: ("world_model_forecast_brief", {"forecast_id": ok(out[0])["forecast"]["id"]}),
        lambda out: ("world_model_context_v4", {"forecast_id": ok(out[0])["forecast"]["id"]}))
    fid = ok(fc)["forecast"]["id"]
    assert ok(got)["forecast"]["id"] == fid and ok(brief)["question"] and ok(ctx)["forecast"]["forecast_id"] == fid
    (q,) = calls(client, ("world_model_forecast", {"question": "What if the BoJ hiked by 25bp?", "horizon_days": 90}))
    assert ok(q)["forecast"]["horizon_days"] == 90


@pytest.mark.parametrize("name, args, code", [
    ("world_model_get_entity", {"entity_id": "nope"}, "node_not_found"),
    ("world_model_get_bundle", {"bundle_id": "nope"}, "bundle_not_found"),
    ("world_model_get_forecast", {"forecast_id": "FC-nope"}, "forecast_not_found"),
    ("world_model_query", {"version": 10_000}, "version_not_found"),
    ("world_model_ingest_document", {"filename": "x.txt"}, "invalid_request"),
    ("world_model_ingest_document", {"filename": "x.txt", "text": "a", "content_base64": "YQ=="}, "invalid_request"),
])
def test_failures_are_tool_errors_with_cores_codes(client, name, args, code):
    ((is_error, text),) = calls(client, (name, args))
    assert is_error and code_of(text) == code


def test_a_wrong_key_cannot_reach_the_server(client):
    async def body(s):
        return "connected"

    with pytest.raises(ExceptionGroup):
        session(client, body, key="x" * 32)
    r = client.post("/mcp", json={}, headers={"Authorization": "Bearer " + "x" * 32})
    assert r.status_code == 401 and r.json()["error"]["code"] == "authentication_required"


def test_a_response_that_is_not_json_is_a_tool_error(client, monkeypatch):
    import httpx

    async def not_json(self, method, url, **kw):
        return httpx.Response(502, text="<html>bad gateway</html>")

    monkeypatch.setattr(httpx.AsyncClient, "request", not_json)
    ((is_error, text),) = calls(client, ("world_model_state", {}))
    assert is_error and code_of(text) == "bad_response"


def test_a_json_answer_that_is_not_an_object_still_errors(client, monkeypatch):
    import httpx

    async def listed(self, method, url, **kw):
        return httpx.Response(500, json=["oops"])

    monkeypatch.setattr(httpx.AsyncClient, "request", listed)
    ((is_error, text),) = calls(client, ("world_model_state", {}))
    assert is_error and code_of(text) == "error"


@pytest.mark.parametrize("ctx, out", [
    (None, {}),
    (SimpleNamespace(headers=None), {}),
    (SimpleNamespace(headers={"Authorization": "Bearer a"}), {"authorization": "Bearer a"}),
    (SimpleNamespace(headers={"authorization": "Bearer b"}), {"authorization": "Bearer b"}),
    (SimpleNamespace(headers={"x": "y"}), {}),
])
def test_the_callers_authorization_is_forwarded(ctx, out):
    assert _headers(ctx) == out
