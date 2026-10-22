"""I2. The review flow over MCP, through the SDK's own client at /mcp: the data-ingestion pipeline (a static key with
documents:create and changes:create) ingests a synthetic note, reads its bundle, and proposes its changes; a person
decides; the tools read the attribute before and after, pinned. Proves the tools compose into the whole flow, that no
tool and no key can decide a change, that core's MCP channel reads only (the access boundary, Oct 19), and that the
tools' answers are the REST answers."""

from __future__ import annotations

import json

import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from tests.integration.service.conftest import RATES_NOTE, SIGNER, WM, review_all
from tests.service.helpers import problem, service

pytestmark = pytest.mark.integration
KEY = "m" * 32
ENV = {"WORLD_MODEL_API_KEYS": f"agent:{KEY}:default:world_model:read+documents:create+changes:create"}
AS_AGENT = {"Authorization": f"Bearer {KEY}"}


def run_tools(c, script):
    """Run `script(tool)` in one MCP session; `tool(name, **args)` returns the decoded answer or raises on a tool error."""

    async def main():
        http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=c.app), base_url="http://wm", headers=AS_AGENT)
        async with streamable_http_client("http://wm/mcp", http_client=http) as streams:
            async with ClientSession(streams[0], streams[1]) as s:
                await s.initialize()

                async def tool(name: str, **args):
                    r = await s.call_tool(name, args)
                    if r.is_error:
                        raise AssertionError(r.content[0].text)
                    return json.loads(r.content[0].text)

                return await script(tool)

    return c.portal.call(main)


def test_an_agent_proposes_over_mcp_and_a_person_decides():
    with service(SIGNER, headers=AS_AGENT, **ENV) as c:
        async def propose(tool):
            start = (await tool("world_model_get_world_model"))["meta"]["version"]
            crude0 = (await tool("world_model_get_attribute", entity_id="crude_oil", attribute="price"))["data"]
            job = (await tool("world_model_ingest_document", filename="2026-09-01_data.txt",
                              text=RATES_NOTE.decode(), source="Data desk", source_type="data"))["data"]
            up = job["result"]["detail"]["results"][0]
            bundle = await tool("world_model_get_bundle", bundle_id=up["bundle_id"])
            proposed = (await tool("world_model_propose_changes", bundle_id=up["bundle_id"]))["data"]
            pending = (await tool("world_model_list_changes"))["data"]
            return start, crude0, up, bundle, proposed, pending

        start, crude0, up, bundle, proposed, pending = run_tools(c, propose)
        assert up["new"] and c.get(f"{WM}/documents/{up['document_id']}").json()["data"]["uploaded_by"] == "agent"
        assert any(s.get("value_of") == "crude_oil.price" for i in bundle["items"] for s in i["signals"])
        assert proposed["status"] == "succeeded" and proposed["result"]["detail"]["version_before"] == start["number"]
        assert pending and all(ch["proposed_by"]["sub"] == "agent" for ch in pending)

        # core's MCP channel reads only: a core-mcp token is refused a proposal, whatever scopes it names
        core = SIGNER.bearer(azp="core-mcp", act={"sub": "mcp-client:claude"},
                             scope="world_model:read documents:create changes:create")
        problem(c.post(f"{WM}/changes", json={"bundle_id": up["bundle_id"]}, headers=core), 403, "insufficient_scope")
        # the pipeline cannot decide: no tool does, and a key never approves
        tag = c.get(WM).headers["etag"]
        problem(c.post(f"{WM}/changes/{pending[0]['id']}/approvals", json={}, headers={"If-Match": tag}), 403,
                "human_approval_required")
        decided = review_all(c, note="checked against the release")
        assert decided and all(d["decided_by"]["kind"] == "token" for d in decided)

        async def read(tool):
            now = await tool("world_model_get_attribute", entity_id="crude_oil", attribute="crude_oil.price")
            then = await tool("world_model_get_attribute", entity_id="crude_oil", attribute="price",
                              version=start["number"])
            hits = await tool("world_model_search", q="crude price", mode="keyword")
            names = await tool("world_model_list_entities", q="crude")
            changes = await tool("world_model_get_change", change_id=decided[0]["change_id"])
            return now, then, hits, names, changes

        now, then, hits, names, changes = run_tools(c, read)
        assert then["data"] == crude0 and then["meta"]["version"]["number"] == start["number"]
        assert now["meta"]["version"]["number"] > start["number"] and now["data"]["observed"]
        assert abs(now["data"]["level"]["mean"] - 103) < abs(crude0["level"]["mean"] - 103)
        assert hits["data"][0]["document_id"] == up["document_id"]
        assert any(a["id"] == "crude_oil.price" for e in names["data"] for a in e["attributes"])
        assert changes["data"]["status"] == "approved" and changes["data"]["decided_by"]["azp"] == "core-web"

        # the same read over REST gives the same answer
        rest = c.get(f"{WM}/entities/crude_oil/attributes/price", params={"version": start["number"]}).json()
        assert rest["data"] == then["data"] and rest["meta"]["version"] == then["meta"]["version"]
