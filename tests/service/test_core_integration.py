"""The patch that puts this service's tools in core's MCP catalog (integrations/core) stays in step with the service:
every route it calls is served here, and it publishes no tool that approves a change."""

from __future__ import annotations

import re
from pathlib import Path

from axelrod_wm.api.service import router

PATCH = Path("integrations/core/0001-world-model-service-mcp-tools.patch").read_text()


def _routes() -> set[tuple[str, str]]:
    out = set()
    for r in router.routes:
        for m in r.methods:
            out.add((m, re.sub(r"\{[^}]+\}", "{}", r.path)))
    return out


def test_every_route_the_patch_calls_is_served_here():
    calls = re.findall(r'(?:call|request)\("(GET|POST|DELETE)", f?"(/[^"]*)"', PATCH)
    assert len(calls) >= 18
    served = _routes()
    for method, path in calls:
        assert (method, "/api/world-model" + re.sub(r"\{[^}]+\}", "{}", path)) in served, (method, path)


def test_the_patch_publishes_reads_and_proposals_but_never_an_approval():
    tools = set(re.findall(r"^\+    async def (world_model_\w+)\(", PATCH, re.M))
    assert {"world_model_state", "world_model_query", "world_model_construction", "world_model_trace",
            "world_model_ingest_source", "world_model_import_bundle"} <= tools and len(tools) == 19
    assert "world_model_decide_proposal" not in tools and "/approve" not in PATCH and "/reject" not in PATCH
    assert 'review="queue"' in PATCH and '"auto"' not in PATCH
    assert "X-Axelrod-On-Behalf-Of" in PATCH
