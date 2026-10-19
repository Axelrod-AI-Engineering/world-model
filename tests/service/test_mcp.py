"""The MCP server (api/mcp.py), through the SDK's own client over Streamable HTTP at /mcp: every tool answers from the
v1 routes as the caller's credential, defaults to the organization's only world model, never decides a change, and
every failure comes back as a tool error naming the problem's code."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from axelrod_wm.api.mcp import _headers
from tests.service.helpers import ALL_BUT_REVIEW, KEY, NOTE, Signer, decide_all, service

SIGNER = Signer()
GHOST = "g" * 32
TOOLS = {
    "world_model_list_world_models", "world_model_get_world_model", "world_model_list_versions", "world_model_graph",
    "world_model_list_entities", "world_model_get_entity", "world_model_get_attribute", "world_model_list_observations",
    "world_model_list_relationships", "world_model_get_relationship", "world_model_list_concepts",
    "world_model_construction", "world_model_trace", "world_model_list_events", "world_model_impact_analysis",
    "world_model_search", "world_model_ingest_document", "world_model_list_documents", "world_model_get_bundle",
    "world_model_propose_changes", "world_model_list_changes", "world_model_get_change", "world_model_simulate",
    "world_model_get_simulation", "world_model_simulation_brief", "world_model_export_v4", "world_model_get_job",
}


@pytest.fixture(scope="module")
def client():
    keys = f"harness:{KEY}:default:{ALL_BUT_REVIEW},ghost:{GHOST}:nobody"
    with service(SIGNER, WORLD_MODEL_API_KEYS=keys) as c:
        yield c


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


def calls(client, *steps, key: str = KEY):
    """Call tools in order; each step is (name, args) or a function of the results so far giving (name, args)."""

    async def body(s):
        out = []
        for step in steps:
            name, args = step(out) if callable(step) else step
            r = await s.call_tool(name, args)
            out.append((r.is_error, r.content[0].text))
        return out

    return session(client, body, key)


def code_of(text: str) -> str:
    """The error code after the SDK's "Error executing tool <name>: " prefix."""
    return text.split(": ", 1)[1].split(":", 1)[0] if text.startswith("Error executing tool") else text.split(":", 1)[0]


def ok(result) -> dict:
    is_error, text = result
    assert not is_error, text
    return json.loads(text)


def tools_of(client) -> dict:
    async def body(s):
        return (await s.list_tools()).tools

    return {t.name: t for t in session(client, body)}


def test_the_server_lists_every_tool_with_annotations(client):
    tools = tools_of(client)
    assert set(tools) == TOOLS
    assert tools["world_model_graph"].annotations.read_only_hint is True
    for name in ("world_model_ingest_document", "world_model_propose_changes", "world_model_simulate"):
        assert tools[name].annotations.read_only_hint is False and tools[name].annotations.destructive_hint is False
    assert not any(w in n for n in tools for w in ("decide", "approve", "reject"))
    assert set(tools["world_model_get_attribute"].input_schema["required"]) == {"entity_id", "attribute"}


def test_reads_default_to_the_organizations_world_model(client):
    wms, one, versions, graph, ents, ent, att, obs, rels, rel, concepts = calls(
        client, ("world_model_list_world_models", {}), ("world_model_get_world_model", {}),
        ("world_model_list_versions", {"limit": 2}),
        ("world_model_graph", {"entities": ["boj"], "depth": 1, "version": 1}),
        ("world_model_list_entities", {"q": "Toyota"}),
        ("world_model_get_entity", {"entity_id": "toyota", "include_relationships": True}),
        ("world_model_get_attribute", {"entity_id": "toyota", "attribute": "operating_profit",
                                       "as_of": "2100-01-01T00:00:00Z"}),
        ("world_model_list_observations", {"entity_id": "oil", "attribute": "brent"}),
        ("world_model_list_relationships", {"entity": "toyota", "limit": 5}),
        ("world_model_get_relationship", {"relationship_id": "m29"}),
        ("world_model_list_concepts", {}))
    assert [m["id"] for m in ok(wms)["data"]] == ["sally_demo"] and ok(one)["data"]["id"] == "sally_demo"
    assert ok(versions)["meta"]["limit"] == 2 and ok(graph)["meta"]["version"]["number"] == 1
    assert "toyota" in {e["id"] for e in ok(ents)["data"]} and ok(ent)["data"]["relationships"] is not None
    assert ok(att)["data"]["id"] == "toyota.operating_profit" and "data" in ok(obs)
    assert ok(rels)["data"] and ok(rel)["data"]["id"] == "m29" and isinstance(ok(rel)["evidence"], list)
    assert ok(concepts)["data"]


def test_construction_trace_search_and_export(client):
    as_json, as_md, traced, hits, export = calls(
        client, ("world_model_construction", {"entity_id": "toyota"}),
        ("world_model_construction", {"entity_id": "toyota", "format": "markdown", "version": 1}),
        ("world_model_trace", {"entity_id": "toyota", "start": "dollar_yen.usd_jpy"}),
        ("world_model_search", {"q": "Toyota op", "mode": "prefix"}),
        ("world_model_export_v4", {}))
    assert ok(as_json)["data"]["entity_id"] == "toyota"
    assert not as_md[0] and as_md[1].startswith("# Toyota Motor")
    assert ok(traced)["data"]["entity_id"] == "toyota" and ok(hits)["data"]
    assert ok(export)["data"]["manifest"]["schema_version"] == "v4.1.4"


def test_ingest_propose_and_a_person_decides_outside_mcp(client):
    b64 = base64.b64encode(NOTE).decode()
    up, again, docs = calls(
        client,
        ("world_model_ingest_document", {"filename": "2026-10-05_note.md", "content_base64": b64, "source": "Desk",
                                         "source_type": "broker_research", "published_at": "2026-10-05T00:00:00Z"}),
        ("world_model_ingest_document", {"filename": "copy.md", "text": NOTE.decode()}),
        ("world_model_list_documents", {"order": "ingested_at"}))
    job = ok(up)["data"]
    res = job["result"]["detail"]["results"][0]
    assert job["status"] == "succeeded" and res["new"] is True
    assert ok(again)["data"]["result"]["detail"]["results"][0]["new"] is False and ok(docs)["data"]
    bid = res["bundle_id"]
    bundle, proposed, pending, polled = calls(
        client, ("world_model_get_bundle", {"bundle_id": bid}),
        ("world_model_propose_changes", {"bundle_id": bid}),
        ("world_model_list_changes", {}),
        lambda out: ("world_model_get_job", {"job_id": ok(out[1])["data"]["id"]}))
    assert ok(bundle)["data"]["id"] == bid and ok(bundle)["items"]
    assert ok(proposed)["data"]["result"]["ids"] and ok(polled)["data"]["status"] == "succeeded"
    first = ok(pending)["data"][0]
    (change,) = calls(client, ("world_model_get_change", {"change_id": first["id"]}))
    assert ok(change)["data"]["status"] == "pending" and ok(change)["operations"]
    decide_all(client, SIGNER)
    events, = calls(client, ("world_model_list_events", {"limit": 200}))
    eid = first["event_id"]
    assert eid in {e["id"] for e in ok(events)["data"]}
    (impact,) = calls(client, ("world_model_impact_analysis", {"event_id": eid}))
    assert ok(impact)["data"]["status"] == "completed"


def test_simulate_and_read_the_simulation(client):
    sim, q = calls(client, ("world_model_simulate", {"template_id": "S-T3"}),
                   ("world_model_simulate", {"question": "What if the BoJ hiked by 25bp?", "horizon_days": 90}))
    sid = ok(sim)["job"]["result"]["ids"][0]
    assert ok(sim)["thesis"]["id"] and ok(q)["job"]["status"] == "succeeded"
    got, brief, export = calls(client, ("world_model_get_simulation", {"simulation_id": sid}),
                               ("world_model_simulation_brief", {"simulation_id": sid}),
                               ("world_model_export_v4", {"simulation_id": sid}))
    assert ok(got)["data"]["id"] == sid and ok(got)["coverage"]["summary"]
    assert ok(brief)["data"]["question"] and ok(export)["data"]["forecast"]["forecast_id"] == sid


@pytest.mark.parametrize("name, args, code", [
    ("world_model_get_entity", {"entity_id": "nope"}, "entity_not_found"),
    ("world_model_get_world_model", {"world_model_id": "nope"}, "world_model_not_found"),
    ("world_model_get_bundle", {"bundle_id": "nope"}, "bundle_not_found"),
    ("world_model_get_simulation", {"simulation_id": "FC-nope"}, "simulation_not_found"),
    ("world_model_graph", {"version": 10_000}, "version_not_found"),
    ("world_model_construction", {"entity_id": "nobody", "format": "markdown"}, "entity_not_found"),
    ("world_model_ingest_document", {"filename": "x.txt"}, "invalid_request"),
    ("world_model_ingest_document", {"filename": "x.txt", "text": "a", "content_base64": "YQ=="}, "invalid_request"),
])
def test_failures_are_tool_errors_with_the_problems_code(client, name, args, code):
    ((is_error, text),) = calls(client, (name, args))
    assert is_error and code_of(text) == code


def test_an_organization_without_one_world_model_must_name_it(client):
    ((is_error, text),) = calls(client, ("world_model_list_entities", {}), key=GHOST)
    assert is_error and code_of(text) == "invalid_request" and "has 0" in text
    ((is_error, text),) = calls(client, ("world_model_list_entities", {"world_model_id": "sally_demo"}), key=GHOST)
    assert is_error and code_of(text) == "world_model_not_found"


def test_a_wrong_key_cannot_reach_the_server(client):
    async def body(s):
        return "connected"

    with pytest.raises(ExceptionGroup):
        session(client, body, key="x" * 32)
    r = client.post("/mcp", json={}, headers={"Authorization": "Bearer " + "x" * 32})
    assert r.status_code == 401 and r.json()["code"] == "invalid_token"


@pytest.mark.parametrize("answer, code", [
    (lambda httpx: httpx.Response(200, text="<html>ok</html>"), "bad_response"),
    (lambda httpx: httpx.Response(502, text="<html>bad gateway</html>"), "error"),
    (lambda httpx: httpx.Response(500, json=["oops"]), "error"),
])
def test_an_answer_that_is_not_the_contracts_is_a_tool_error(client, monkeypatch, answer, code):
    import httpx

    async def fake(self, method, url, **kw):
        return answer(httpx)

    monkeypatch.setattr(httpx.AsyncClient, "request", fake)
    ((is_error, text),) = calls(client, ("world_model_get_world_model", {"world_model_id": "sally_demo"}))
    assert is_error and code_of(text) == code


@pytest.mark.parametrize("ctx, out", [
    (None, {}),
    (SimpleNamespace(headers=None), {}),
    (SimpleNamespace(headers={"Authorization": "Bearer a"}), {"authorization": "Bearer a"}),
    (SimpleNamespace(headers={"authorization": "Bearer b", "traceparent": "00-x", "X-Request-Id": "r1",
                              "X-Axelrod-On-Behalf-Of": "acme/u1", "Cookie": "c"}),
     {"authorization": "Bearer b", "traceparent": "00-x", "x-request-id": "r1"}),
    (SimpleNamespace(headers={"x": "y"}), {}),
])
def test_the_callers_credential_and_trace_are_forwarded_and_nothing_else(ctx, out):
    assert _headers(ctx) == out


def test_a_tool_called_outside_a_request_sends_no_headers():
    class Outside:
        @property
        def headers(self):
            raise ValueError("no request")

    assert _headers(Outside()) == {}
