"""The patch that puts this service's tools in core's MCP catalog (integrations/core) stays in step with the service:
every route it calls is a v1 route the contract specifies and this service serves, with the method it uses, and it
publishes no tool that decides a change (world_model/docs/design/core-mcp-auth.md: approval is human-only)."""

from __future__ import annotations

import re

import yaml

from axelrod_wm.api.v1.routes_ingest import router as ingest_router
from axelrod_wm.api.v1.routes_model import router as model_router
from axelrod_wm.api.v1.routes_work import router as work_router
from tests.where import CORE_PATCH, OPENAPI

PATCH = CORE_PATCH.read_text()
SPEC = yaml.safe_load(OPENAPI.read_text())
W = "/world-models/{}"


def _norm(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path)


def _served() -> set[tuple[str, str]]:
    return {(m, _norm(r.path.removeprefix("/v1"))) for router in (model_router, ingest_router, work_router) for r in router.routes
            for m in r.methods}


def _specified() -> set[tuple[str, str]]:
    return {(m.upper(), _norm(p)) for p, item in SPEC["paths"].items() for m in item}


def calls() -> list[tuple[str, str]]:
    """(method, path) of every request the patch's tools make, with `path` variables followed."""
    out = []
    path_var = ""
    for line in PATCH.splitlines():
        m = re.search(r'path = await model_path\(world_model_id\)(?: \+ f?"([^"]*)")?', line)
        if m:
            path_var = W + _norm(m.group(1) or "")
        m = re.search(r'(?:call|request)\("(GET|POST|DELETE)", (.*)', line)
        if not m:
            continue
        method, rest = m.groups()
        if rest.startswith("await model_path(world_model_id)"):
            tail = re.match(r'await model_path\(world_model_id\)(?: \+ f?"([^"]*)")?', rest).group(1) or ""
            out.append((method, W + _norm(tail)))
        elif rest.startswith("path"):
            tail = re.match(r'path(?: \+ f?"([^"]*)")?', rest).group(1) or ""
            out.append((method, path_var + _norm(tail)))
        else:
            out.append((method, _norm(re.match(r'f?"([^"]*)"', rest).group(1))))
    return out


def test_every_route_the_patch_calls_is_specified_and_served():
    made = calls()
    assert len(made) >= 18 and {m for m, _p in made} == {"GET"}          # read only (the API review, Oct 19)
    served, specified = _served(), _specified()
    for method, path in made:
        assert (method, path) in specified, (method, path, "not in world_model/docs/api/openapi.yaml")
        assert (method, path) in served, (method, path, "not served")


def test_the_patch_publishes_reads_only():
    """Core's backend MCP reads the world model and nothing else: no tool ingests, proposes, simulates or decides."""
    tools = set(re.findall(r"^\+    async def (world_model_\w+)\(", PATCH, re.M))
    assert {"world_model_get_world_model", "world_model_graph", "world_model_get_attribute", "world_model_construction",
            "world_model_trace", "world_model_get_simulation", "world_model_list_changes"} <= tools and len(tools) == 17
    assert not {t for t in tools if re.search("decide|approv|reject|simulate|ingest|propose", t)}
    assert '"POST"' not in PATCH.split("+++ b/src/axelrod_app/mcp_world_model.py", 1)[1].split("diff --git", 1)[0]
    assert "/approvals" not in PATCH and "/rejections" not in PATCH and '"auto"' not in PATCH
    assert "X-Axelrod-On-Behalf-Of" not in PATCH.split("+++ b/src/axelrod_app/mcp_world_model.py", 1)[1]
    assert "/api/world-model" not in PATCH and 'WORLD_MODEL_API = "/v1"' in PATCH
