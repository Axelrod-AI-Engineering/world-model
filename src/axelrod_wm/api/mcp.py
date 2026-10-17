"""The world model's MCP server (Oct 17): its service as tools, at /mcp, for Claude, the LLM harness, and core.

It follows core's MCP conventions (Axelrod-AI-Engineering/core, src/axelrod_app/mcp_server.py): the official `mcp`
2.x SDK (`MCPServer`, not FastMCP), stateless Streamable HTTP at /mcp on the same FastAPI app, snake_case tool names
with read-only / destructive / idempotent annotations, and errors as `ToolError("<code>: <message>")`. Core reserves
`world_model.query` for point-in-time reads; here it is `world_model_query`.

A tool calls the service's own HTTP routes in process (api/service.py), forwarding the caller's
`Authorization: Bearer <API key>`, so MCP and REST share one implementation: the same auth, validation, tenancy, and
answers. Core can mount it the way it mounts EODHD's MCP server (`MCPServerStreamableHttp` with a Bearer header).
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any, Literal

import httpx
from fastapi import FastAPI
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
DECIDE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
BASE = "/api/world-model"


def _headers(ctx: Context | None) -> dict[str, str]:
    raw = dict(getattr(ctx, "headers", None) or {}) if ctx is not None else {}
    auth = raw.get("authorization") or raw.get("Authorization")
    return {"authorization": auth} if auth else {}


def build_mcp(app: FastAPI) -> MCPServer:
    server = MCPServer(name="axelrod-world-model", title="Axelrod World Model",
                       instructions="The Axelrod world model: entities, values, and causal links learned from reviewed "
                                    "research, with point-in-time reads, search over ingested documents, forecasts, and "
                                    "ingestion of new files. Every read names the state version it was served from.")

    async def call(ctx: Context | None, method: str, path: str, **kw: Any) -> Any:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://world-model") as client:
            r = await client.request(method, BASE + path, headers=_headers(ctx), timeout=600, **kw)
        try:
            body = r.json()
        except json.JSONDecodeError:
            body = {"error": {"code": "bad_response", "message": r.text[:200]}}
        if r.status_code >= 400:
            err = body.get("error", {}) if isinstance(body, dict) else {}
            raise ToolError(f"{err.get('code', 'error')}: {err.get('message', r.text[:200])}")
        return body

    def p(**params: Any) -> dict:
        """Query parameters or a JSON body without the empty ones."""
        return {k: v for k, v in params.items() if v not in (None, "")}

    # -- reads ----------------------------------------------------------------------------------------------------
    @server.tool(title="World model state", description="The state reads are served from: version, state hash, the "
                 "model's clock, and counts of entities, values, interactions, and stored documents.", annotations=READ)
    async def world_model_state(ctx: Context) -> dict:
        return await call(ctx, "GET", "/state")

    @server.tool(title="Query the world model", description="Entities, values (levels with spreads, in their units), "
                 "and causal edges (effect, existence probability, timing, evidence), for the named nodes or names in "
                 "q and their neighbours up to `depth` links, at the current state or pinned to a version or date.",
                 annotations=READ)
    async def world_model_query(ctx: Context, node_ids: list[str] | None = None, q: str = "", depth: int = 1,
                                version: int | None = None, as_of: datetime | None = None, limit: int = 200) -> dict:
        return await call(ctx, "GET", "/query", params=q_params(node_ids, q, depth, version, as_of, limit))

    def q_params(node_ids: list[str] | None, qs: str, depth: int, version: int | None, as_of: datetime | None,
                 limit: int) -> dict:
        return p(node_ids=",".join(node_ids or []), q=qs, depth=depth, version=version,
                 as_of=as_of.isoformat() if as_of else None, limit=limit)

    @server.tool(title="Find nodes", description="Entities and values whose names contain q (prefix matches first).",
                 annotations=READ)
    async def world_model_search_nodes(ctx: Context, q: str = "", limit: int = 50) -> dict:
        return await call(ctx, "GET", "/nodes", params=p(q=q, limit=limit))

    @server.tool(title="Get an entity", description="One entity: its values, concepts, and the links in and out.",
                 annotations=READ)
    async def world_model_get_entity(ctx: Context, entity_id: str) -> dict:
        return await call(ctx, "GET", f"/entities/{entity_id}")

    @server.tool(title="Get a value", description="One value: its level and spread, its drivers, and its effects.",
                 annotations=READ)
    async def world_model_get_value(ctx: Context, value_id: str) -> dict:
        return await call(ctx, "GET", f"/values/{value_id}")

    @server.tool(title="Taxonomy", description="The static taxonomy of concepts and the entities under each.",
                 annotations=READ)
    async def world_model_taxonomy(ctx: Context) -> dict:
        return await call(ctx, "GET", "/taxonomy")

    # -- documents and search ---------------------------------------------------------------------------------------
    @server.tool(title="Search documents and the model", description="Keyword, prefix, semantic, graph, or hybrid "
                 "search over ingested documents' chunks and the model's names.", annotations=READ)
    async def world_model_search(ctx: Context, q: str, mode: Literal["keyword", "prefix", "semantic", "graph", "hybrid"] = "hybrid",
                                 limit: int = 20) -> dict:
        return await call(ctx, "GET", "/search", params=p(q=q, mode=mode, limit=limit))

    @server.tool(title="Ingest a document", description="Store a file (base64 `content`, or plain `text`), parse and "
                 "index it, and read it into an import bundle of proposed graph updates. Idempotent: the same bytes "
                 "are stored once. Nothing changes the model until the bundle is imported and reviewed.", annotations=WRITE)
    async def world_model_ingest_document(ctx: Context, filename: str, content_base64: str = "", text: str = "",
                                          source: str = "", source_type: str = "other",
                                          published_at: datetime | None = None) -> dict:
        if bool(content_base64) == bool(text):
            raise ToolError("invalid_request: give exactly one of content_base64 and text")
        data = base64.b64decode(content_base64) if content_base64 else text.encode()
        form = p(source=source, source_type=source_type, published_at=published_at.isoformat() if published_at else None)
        return await call(ctx, "POST", "/documents", files=[("files", (filename, data))], data=form)

    @server.tool(title="List documents", description="Stored documents, by event time or ingestion time.",
                 annotations=READ)
    async def world_model_list_documents(ctx: Context, order: Literal["event_time", "ingested_at"] = "event_time",
                                         limit: int = 100, offset: int = 0) -> dict:
        return await call(ctx, "GET", "/documents", params=p(order=order, limit=limit, offset=offset))

    @server.tool(title="Get a bundle", description="One import bundle: its items and their signals, with quotes.",
                 annotations=READ)
    async def world_model_get_bundle(ctx: Context, bundle_id: str) -> dict:
        return await call(ctx, "GET", f"/bundles/{bundle_id}")

    @server.tool(title="Import a bundle", description="Fold a bundle's items into the model, in event-time order, one "
                 "graph update each. review=queue leaves each for a person; review=auto approves each as the caller.",
                 annotations=DECIDE)
    async def world_model_import_bundle(ctx: Context, bundle_id: str, review: Literal["queue", "auto"] = "queue",
                                        item_ids: list[str] | None = None) -> dict:
        return await call(ctx, "POST", f"/bundles/{bundle_id}/import", json=p(review=review, item_ids=item_ids))

    # -- review ---------------------------------------------------------------------------------------------------------
    @server.tool(title="List proposals", description="Proposed graph updates (pending by default).", annotations=READ)
    async def world_model_list_proposals(ctx: Context, status: Literal["pending", "approved", "rejected", "all"] = "pending",
                                         limit: int = 100) -> dict:
        return await call(ctx, "GET", "/proposals", params=p(status=status, limit=limit))

    @server.tool(title="Decide a proposal", description="Approve or reject a proposed graph update as the caller; a "
                 "rejection needs a note.", annotations=DECIDE)
    async def world_model_decide_proposal(ctx: Context, proposal_id: str, decision: Literal["approve", "reject"],
                                          note: str = "") -> dict:
        return await call(ctx, "POST", f"/proposals/{proposal_id}/{decision}", json={"note": note})

    # -- forecasts --------------------------------------------------------------------------------------------------------
    @server.tool(title="Forecast a what-if", description="Pose a thesis (a what-if question, or a ready thesis id) and "
                 "forecast it: targets with ranges, transmission by order, and the scenario table.", annotations=DECIDE)
    async def world_model_forecast(ctx: Context, question: str = "", thesis_id: str = "", horizon_days: int = 182) -> dict:
        return await call(ctx, "POST", "/forecasts", json=p(question=question, thesis_id=thesis_id, horizon_days=horizon_days))

    @server.tool(title="Get a forecast", description="One forecast, as posed.", annotations=READ)
    async def world_model_get_forecast(ctx: Context, forecast_id: str) -> dict:
        return await call(ctx, "GET", f"/forecasts/{forecast_id}")

    @server.tool(title="A forecast's brief", description="Summary, expected timing, exposures, indicators, evidence.",
                 annotations=READ)
    async def world_model_forecast_brief(ctx: Context, forecast_id: str) -> dict:
        return await call(ctx, "GET", f"/forecasts/{forecast_id}/brief")

    @server.tool(title="Export as agent context", description="The world model (and a forecast, when given) in a client's "
                 "v4.1.4 world-model format: domain pack, registry entry, evidence packs, load order.", annotations=READ)
    async def world_model_context_v4(ctx: Context, forecast_id: str = "") -> dict:
        return await call(ctx, "GET", "/context/v4", params=p(forecast=forecast_id))

    return server


def install_mcp(app: FastAPI, server: MCPServer) -> None:
    """The SDK's Streamable HTTP route at /mcp, on the FastAPI host (stateless, as core runs it). The SDK's session
    manager must run for the app's lifetime: api/app.py's lifespan enters `server.session_manager.run()`."""
    sdk_app = server.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=True,
                                         transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
    app.router.routes.extend(sdk_app.routes)
