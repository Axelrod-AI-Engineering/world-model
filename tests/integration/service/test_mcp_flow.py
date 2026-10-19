"""I2. The review flow with an agent over MCP, through the SDK's own client at /mcp, as an agent (Claude, core) runs it:
ingest a synthetic note, read its bundle, propose its changes, wait for a person, and read the attribute before and
after, pinned. Proves the tools compose into the whole flow with the caller's key, that no tool and no key can decide a
change (a person does, in a review UI), and that the tools' answers are the REST answers."""

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
ENV = {"WORLD_MODEL_API_KEYS": f"agent:{KEY}:default"}
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
            brent0 = (await tool("world_model_get_attribute", entity_id="oil", attribute="brent"))["data"]
            job = (await tool("world_model_ingest_document", filename="2026-09-01_data.txt",
                              text=RATES_NOTE.decode(), source="Data desk", source_type="data"))["data"]
            up = job["result"]["detail"]["results"][0]
            bundle = await tool("world_model_get_bundle", bundle_id=up["bundle_id"])
            proposed = (await tool("world_model_propose_changes", bundle_id=up["bundle_id"]))["data"]
            pending = (await tool("world_model_list_changes"))["data"]
            return start, brent0, up, bundle, proposed, pending

        start, brent0, up, bundle, proposed, pending = run_tools(c, propose)
        assert up["new"] and c.get(f"{WM}/documents/{up['document_id']}").json()["data"]["uploaded_by"] == "agent"
        assert any(s.get("value_of") == "oil.brent" for i in bundle["items"] for s in i["signals"])
        assert proposed["status"] == "succeeded" and proposed["result"]["detail"]["version_before"] == start["number"]
        assert pending and all(ch["proposed_by"]["sub"] == "agent" for ch in pending)

        # the agent cannot decide: no tool does, and its key has no review scope
        tag = c.get(WM).headers["etag"]
        problem(c.post(f"{WM}/changes/{pending[0]['id']}/approvals", json={}, headers={"If-Match": tag}), 403,
                "insufficient_scope")
        decided = review_all(c, note="checked against the release")
        assert decided and all(d["decided_by"]["kind"] == "token" for d in decided)

        async def read(tool):
            now = await tool("world_model_get_attribute", entity_id="oil", attribute="oil.brent")
            then = await tool("world_model_get_attribute", entity_id="oil", attribute="brent",
                              version=start["number"])
            hits = await tool("world_model_search", q="Brent crude", mode="keyword")
            names = await tool("world_model_list_entities", q="brent")
            changes = await tool("world_model_get_change", change_id=decided[0]["change_id"])
            return now, then, hits, names, changes

        now, then, hits, names, changes = run_tools(c, read)
        assert then["data"] == brent0 and then["meta"]["version"]["number"] == start["number"]
        assert now["meta"]["version"]["number"] > start["number"] and now["data"]["observed"]
        assert abs(now["data"]["level"]["mean"] - 103) < abs(brent0["level"]["mean"] - 103)
        assert hits["data"][0]["document_id"] == up["document_id"]
        assert any(a["id"] == "oil.brent" for e in names["data"] for a in e["attributes"])
        assert changes["data"]["status"] == "approved" and changes["data"]["decided_by"]["azp"] == "core-web"

        # the same read over REST gives the same answer
        rest = c.get(f"{WM}/entities/oil/attributes/brent", params={"version": start["number"]}).json()
        assert rest["data"] == then["data"] and rest["meta"]["version"] == then["meta"]["version"]
