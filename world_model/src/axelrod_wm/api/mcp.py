"""The world model's MCP (Model Context Protocol) server: the v1 API as tools, at /mcp, for engineers, the LLM harness,
and the data-ingestion pipeline (Oct 18; brought current Oct 19).

It follows core's MCP conventions (Axelrod-AI-Engineering/core, src/axelrod_app/mcp_server.py): the official `mcp`
2.x SDK (`MCPServer`, not FastMCP), stateless Streamable HTTP at /mcp on the same FastAPI app, snake_case tool names
with read-only / destructive / idempotent annotations, and errors as `ToolError("<code>: <detail>")`.

A tool calls the v1 routes in process (api/v1), forwarding the caller's `Authorization`, so MCP and REST share one
implementation: the same credentials, scopes, validation, tenancy, and answers.

- **World models.** Every tool takes `world_model_id`, which defaults to the organization's only world model.
  `world_model_id="erid"` reads the unified world model (internal staff), and `compartment` narrows those reads to a
  client's view (world_model/docs/design/api.md §4).
- **Scopes** are the REST ones: reads need `world_model:read`; `world_model_ingest_document` needs `documents:create`,
  `world_model_propose_changes` `changes:create`, `world_model_simulate` `simulations:create`. A static key with no
  scopes listed reads only, and a token from core's MCP channel or driven by an agent (`act`) reads only, whatever it
  asks for (the access boundary, Oct 19). No tool decides a change: approval is a person's step in a review UI.
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
PROPOSE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
BASE = "/v1"
UNIFIED = "erid"
COMPARTMENT = ("`compartment` narrows the read to a compartment of the unified world model (world_model_id='erid'): "
               "a client's companies, the players upstream of them, and one link downstream.")


def _headers(ctx: Context | None) -> dict[str, str]:
    try:
        raw = dict(getattr(ctx, "headers", None) or {}) if ctx is not None else {}
    except ValueError:                   # a tool called in process, outside an HTTP request, has no headers
        raw = {}
    low = {k.lower(): v for k, v in raw.items()}
    return {k: low[k] for k in ("authorization", "traceparent", "x-request-id") if low.get(k)}


def build_mcp(app: FastAPI) -> MCPServer:
    server = MCPServer(name="axelrod-world-model", title="Axelrod World Model",
                       instructions="The Axelrod world model: entities with their attributes (an entity's measured "
                                    "quantities, e.g. toyota.operating_profit), relationships between attributes with "
                                    "their evidence and retrieval profile, read at a stated version; documents read "
                                    "into proposed changes that a person reviews; theses run as simulations. Every "
                                    "read names the version it was served from. world_model_id='erid' is the unified "
                                    "world model (internal staff), narrowed by `compartment`. No tool approves a "
                                    "change.")

    async def request(ctx: Context | None, method: str, path: str, **kw: Any) -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://world-model") as client:
            r = await client.request(method, BASE + path, headers={**_headers(ctx), **kw.pop("headers", {})},
                                     timeout=600, **kw)
        if r.status_code >= 400:
            try:
                body = r.json()
            except json.JSONDecodeError:
                body = {}
            body = body if isinstance(body, dict) else {}
            raise ToolError(f"{body.get('code', 'error')}: {body.get('detail', r.text[:200])}")
        return r

    async def call(ctx: Context | None, method: str, path: str, **kw: Any) -> Any:
        r = await request(ctx, method, path, **kw)
        try:
            return r.json()
        except json.JSONDecodeError as err:
            raise ToolError(f"bad_response: {r.text[:200]}") from err

    async def wm(ctx: Context | None, world_model_id: str, compartment: str = "") -> str:
        """The world model's path: the unified one (`erid`), the one named, or the organization's only one."""
        if world_model_id == UNIFIED:
            return "/erid"
        if compartment:
            raise ToolError("invalid_request: a compartment narrows the unified world model: pass world_model_id='erid'")
        if world_model_id:
            return f"/world-models/{world_model_id}"
        ids = [m["id"] for m in (await call(ctx, "GET", "/world-models"))["data"]]
        if len(ids) != 1:
            raise ToolError(f"invalid_request: name a world_model_id (this organization has {len(ids)})")
        return f"/world-models/{ids[0]}"

    def p(**params: Any) -> dict:
        """Query parameters or a JSON body without the empty ones."""
        return {k: v for k, v in params.items() if v not in (None, "")}

    def pin(version: int | None, as_of: datetime | None) -> dict:
        return {"version": version, "as_of": as_of.isoformat() if as_of else None}

    # -- world models, the unified one, versions -------------------------------------------------------------------
    @server.tool(title="World models", description="The organization's world models: each one's latest version, "
                 "clock, and counts.", annotations=READ)
    async def world_model_list_world_models(ctx: Context) -> dict:
        return await call(ctx, "GET", "/world-models")

    @server.tool(title="A world model", description="One world model: its latest version, the model's clock, and counts "
                 "of entities, attributes, relationships, groups, documents and bundles.", annotations=READ)
    async def world_model_get_world_model(ctx: Context, world_model_id: str = "") -> dict:
        return await call(ctx, "GET", await wm(ctx, world_model_id))

    @server.tool(title="The unified world model", description="erid, the unified world model: the whole graph (internal "
                 "staff only), its scenario, version, counts, and compartments. Read it with world_model_id='erid'.",
                 annotations=READ)
    async def world_model_get_unified(ctx: Context) -> dict:
        return await call(ctx, "GET", "/erid")

    @server.tool(title="Compartments", description="The compartments of the unified world model this credential may "
                 "read: each one's companies and size.", annotations=READ)
    async def world_model_list_compartments(ctx: Context, limit: int = 50, cursor: str = "") -> dict:
        return await call(ctx, "GET", "/erid/compartments", params=p(limit=limit, cursor=cursor))

    @server.tool(title="Versions", description="Committed versions, newest first, each with the changes that committed "
                 "it.", annotations=READ)
    async def world_model_list_versions(ctx: Context, world_model_id: str = "", limit: int = 50,
                                        cursor: str = "") -> dict:
        return await call(ctx, "GET", await wm(ctx, world_model_id) + "/versions", params=p(limit=limit, cursor=cursor))

    # -- the model -------------------------------------------------------------------------------------------------
    @server.tool(title="A subgraph", description="Entities with the attributes reached nested (levels with spreads, in "
                 "their units) and the relationships between them (effect, confidence, timing, retrieval profile), for "
                 "the named entities or attributes or the names in q and their neighbours up to `depth` relationships, "
                 "at the current version or pinned to a version or date. " + COMPARTMENT, annotations=READ)
    async def world_model_graph(ctx: Context, world_model_id: str = "", compartment: str = "",
                                entities: list[str] | None = None, attributes: list[str] | None = None, q: str = "",
                                depth: int = 1, limit: int = 200, version: int | None = None,
                                as_of: datetime | None = None) -> dict:
        return await call(ctx, "GET", await wm(ctx, world_model_id, compartment) + "/graph", params=p(
            compartment=compartment, entities=",".join(entities or []), attributes=",".join(attributes or []), q=q,
            depth=depth, limit=limit, **pin(version, as_of)))

    @server.tool(title="Entities", description="Entities by type, concept, group, or name (q matches entity and "
                 "attribute names; an entity matched through its attributes nests just those). " + COMPARTMENT,
                 annotations=READ)
    async def world_model_list_entities(ctx: Context, world_model_id: str = "", compartment: str = "", q: str = "",
                                        type: str = "", concept: str = "", group: str = "", limit: int = 50,
                                        cursor: str = "", version: int | None = None,
                                        as_of: datetime | None = None) -> dict:
        return await call(ctx, "GET", await wm(ctx, world_model_id, compartment) + "/entities", params=p(
            compartment=compartment, q=q, type=type, concept=concept, group=group, limit=limit, cursor=cursor,
            **pin(version, as_of)))

    @server.tool(title="An entity", description="One entity with all its attributes nested; include_relationships adds "
                 "the relationships into and out of them. " + COMPARTMENT, annotations=READ)
    async def world_model_get_entity(ctx: Context, entity_id: str, world_model_id: str = "", compartment: str = "",
                                     include_relationships: bool = False, version: int | None = None,
                                     as_of: datetime | None = None) -> dict:
        include = "attributes,relationships" if include_relationships else "attributes"
        return await call(ctx, "GET", await wm(ctx, world_model_id, compartment) + f"/entities/{entity_id}",
                          params=p(compartment=compartment, include=include, **pin(version, as_of)))

    @server.tool(title="An attribute", description="One attribute of an entity: level, spread, unit, view, basis, and "
                 "its latest observation (with occurred_at). `attribute` is its key in the entity (operating_profit) "
                 "or its full id (toyota.operating_profit). " + COMPARTMENT, annotations=READ)
    async def world_model_get_attribute(ctx: Context, entity_id: str, attribute: str, world_model_id: str = "",
                                        compartment: str = "", version: int | None = None,
                                        as_of: datetime | None = None) -> dict:
        return await call(ctx, "GET", await wm(ctx, world_model_id, compartment)
                          + f"/entities/{entity_id}/attributes/{attribute}",
                          params=p(compartment=compartment, **pin(version, as_of)))

    @server.tool(title="Observations", description="An attribute's dated observations: value in its unit, occurred_at "
                 "(when it happened), valid_at (when it applies) and observed_at (when the model learned it). "
                 + COMPARTMENT, annotations=READ)
    async def world_model_list_observations(ctx: Context, entity_id: str, attribute: str, world_model_id: str = "",
                                            compartment: str = "", limit: int = 50, cursor: str = "") -> dict:
        return await call(ctx, "GET", await wm(ctx, world_model_id, compartment)
                          + f"/entities/{entity_id}/attributes/{attribute}/observations",
                          params=p(compartment=compartment, limit=limit, cursor=cursor))

    @server.tool(title="States", description="The model's state of an attribute over time (mean, sd, z), for "
                 "trajectories; from and to bound the dates. " + COMPARTMENT, annotations=READ)
    async def world_model_list_states(ctx: Context, entity_id: str, attribute: str, world_model_id: str = "",
                                      compartment: str = "", start: datetime | None = None,
                                      end: datetime | None = None, limit: int = 50, cursor: str = "") -> dict:
        return await call(ctx, "GET", await wm(ctx, world_model_id, compartment)
                          + f"/entities/{entity_id}/attributes/{attribute}/states",
                          params=p(**{"from": start.isoformat() if start else None,
                                      "to": end.isoformat() if end else None},
                                   compartment=compartment, limit=limit, cursor=cursor))

    @server.tool(title="Relationships", description="Relationships between attributes, filtered by source, target, "
                 "entity, type, or calibration, each with its retrieval profile (exposure, unit, date, hedge, "
                 "pass-through, endpoint, calculation, source). An uncalibrated one has a sign and no size (effect "
                 "null, never 0). " + COMPARTMENT, annotations=READ)
    async def world_model_list_relationships(ctx: Context, world_model_id: str = "", compartment: str = "",
                                             source: str = "", target: str = "", entity: str = "", type: str = "",
                                             calibration: str = "", limit: int = 50, cursor: str = "",
                                             version: int | None = None, as_of: datetime | None = None) -> dict:
        return await call(ctx, "GET", await wm(ctx, world_model_id, compartment) + "/relationships", params=p(
            compartment=compartment, source=source, target=target, entity=entity, type=type, calibration=calibration,
            limit=limit, cursor=cursor, **pin(version, as_of)))

    @server.tool(title="A relationship", description="One relationship with its retrieval profile, and its evidence "
                 "records (each with its evidence and epistemic type). " + COMPARTMENT, annotations=READ)
    async def world_model_get_relationship(ctx: Context, relationship_id: str, world_model_id: str = "",
                                           compartment: str = "", version: int | None = None,
                                           as_of: datetime | None = None) -> dict:
        path = await wm(ctx, world_model_id, compartment) + f"/relationships/{relationship_id}"
        rel = await call(ctx, "GET", path, params=p(compartment=compartment, **pin(version, as_of)))
        ev = await call(ctx, "GET", path + "/evidence", params=p(compartment=compartment, limit=200,
                                                                 **pin(version, as_of)))
        return {**rel, "evidence": ev["data"]}

    @server.tool(title="Concepts", description="The taxonomy's concepts and the entities under each.", annotations=READ)
    async def world_model_list_concepts(ctx: Context, world_model_id: str = "", limit: int = 200,
                                        cursor: str = "") -> dict:
        return await call(ctx, "GET", await wm(ctx, world_model_id) + "/concepts", params=p(limit=limit, cursor=cursor))

    # -- construction ------------------------------------------------------------------------------------------------
    @server.tool(title="A company's construction", description="How a company is built: its attributes, business "
                 "compositions (driving, reconciling, or not a sum), identities, stock-flows, named paths with each "
                 "transition, link counts and problems. format=markdown for a readable page. " + COMPARTMENT,
                 annotations=READ)
    async def world_model_construction(ctx: Context, entity_id: str, world_model_id: str = "", compartment: str = "",
                                       format: Literal["json", "markdown"] = "json", version: int | None = None,
                                       as_of: datetime | None = None) -> Any:
        path = await wm(ctx, world_model_id, compartment) + f"/entities/{entity_id}/construction"
        if format == "markdown":
            return (await request(ctx, "GET", path, params=p(compartment=compartment, format="markdown",
                                                             **pin(version, as_of)))).text
        return await call(ctx, "GET", path, params=p(compartment=compartment, **pin(version, as_of)))

    @server.tool(title="Compositions", description="A company's business views: each total split into parts, its role "
                 "(driving, reconciling, or non_additive) and basis. " + COMPARTMENT, annotations=READ)
    async def world_model_list_compositions(ctx: Context, entity_id: str, world_model_id: str = "",
                                            compartment: str = "", limit: int = 50, cursor: str = "") -> dict:
        return await call(ctx, "GET", await wm(ctx, world_model_id, compartment) + f"/entities/{entity_id}/compositions",
                          params=p(compartment=compartment, limit=limit, cursor=cursor))

    @server.tool(title="Named paths", description="A company's named paths: each step a relationship with its "
                 "calibration and transition. " + COMPARTMENT, annotations=READ)
    async def world_model_list_paths(ctx: Context, entity_id: str, world_model_id: str = "", compartment: str = "",
                                     limit: int = 50, cursor: str = "") -> dict:
        return await call(ctx, "GET", await wm(ctx, world_model_id, compartment) + f"/entities/{entity_id}/paths",
                          params=p(compartment=compartment, limit=limit, cursor=cursor))

    @server.tool(title="Trace a change into a company", description="Every route from a change in one attribute "
                 "(`start`: a full id, or a key of the company's attributes) to the company's accounts, calibrated or "
                 "not: where each stops, and which steps are uncalibrated or lack a transition. through_totals goes "
                 "on through the totals a route reaches, within max_depth relationships. " + COMPARTMENT,
                 annotations=READ)
    async def world_model_trace(ctx: Context, entity_id: str, start: str, world_model_id: str = "",
                                compartment: str = "", through_totals: bool = False, max_depth: int = 8,
                                version: int | None = None, as_of: datetime | None = None) -> dict:
        return await call(ctx, "GET", await wm(ctx, world_model_id, compartment) + f"/entities/{entity_id}/traces",
                          params=p(**{"from": start}, compartment=compartment, through_totals=through_totals,
                                   max_depth=max_depth, **pin(version, as_of)))

    # -- events ------------------------------------------------------------------------------------------------------
    @server.tool(title="Events", description="Market events by publication time, filtered by type or entity.",
                 annotations=READ)
    async def world_model_list_events(ctx: Context, world_model_id: str = "", type: str = "", entity: str = "",
                                      limit: int = 50, cursor: str = "") -> dict:
        return await call(ctx, "GET", await wm(ctx, world_model_id) + "/events",
                          params=p(type=type, entity=entity, limit=limit, cursor=cursor))

    @server.tool(title="What an event did", description="The attributes an event moves directly, and one relationship "
                 "on: direction, size in sd (null when unknown), confidence.", annotations=READ)
    async def world_model_impact_analysis(ctx: Context, event_id: str, world_model_id: str = "") -> dict:
        return await call(ctx, "GET", await wm(ctx, world_model_id) + f"/events/{event_id}/impact-analysis")

    # -- documents, bundles, search ---------------------------------------------------------------------------------
    @server.tool(title="Search", description="Keyword, prefix, semantic, graph, or hybrid search over ingested "
                 "passages and the model's names; a hit is a chunk, an entity, or an attribute (with its entity_id).",
                 annotations=READ)
    async def world_model_search(ctx: Context, q: str, world_model_id: str = "",
                                 mode: Literal["keyword", "prefix", "semantic", "graph", "hybrid"] = "hybrid",
                                 limit: int = 20) -> dict:
        return await call(ctx, "GET", await wm(ctx, world_model_id) + "/search", params=p(q=q, mode=mode, limit=limit))

    @server.tool(title="Retrieve passages", description="Ranked passages across the ingested documents for a question, "
                 "each with its citation (title, publisher, date), the names in it, and how each channel ranked it. "
                 "Filter by document, source type, source, entity, or date; `context` adds neighbouring passages; "
                 "`per_document` caps each document; pass `cursor` from meta.next_cursor for the next page.",
                 annotations=READ)
    async def world_model_retrieve(ctx: Context, q: str, world_model_id: str = "",
                                   mode: Literal["hybrid", "keyword", "semantic", "graph"] = "hybrid",
                                   document_id: list[str] | None = None, source_type: list[str] | None = None,
                                   source: list[str] | None = None, entity_id: list[str] | None = None,
                                   published_from: datetime | None = None, published_to: datetime | None = None,
                                   context: int = 0, per_document: int = 0, limit: int = 10, cursor: str = "") -> dict:
        return await call(ctx, "GET", await wm(ctx, world_model_id) + "/chunks", params=p(
            q=q, mode=mode, document_id=document_id, source_type=source_type, source=source, entity_id=entity_id,
            published_from=published_from.isoformat() if published_from else None,
            published_to=published_to.isoformat() if published_to else None, context=context,
            per_document=per_document, limit=limit, cursor=cursor))

    @server.tool(title="Ingest a document", description="Needs documents:create (the data-ingestion pipeline). Store a "
                 "file (base64 `content_base64`, or plain `text`), parse and index it, and read it into a bundle of "
                 "proposed updates. Answers with the finished job. The same content always gets the same answer; "
                 "nothing changes the model until a change is proposed and a person approves it.", annotations=WRITE)
    async def world_model_ingest_document(ctx: Context, filename: str, world_model_id: str = "",
                                          content_base64: str = "", text: str = "", source: str = "",
                                          source_type: str = "other", published_at: datetime | None = None) -> dict:
        if bool(content_base64) == bool(text):
            raise ToolError("invalid_request: give exactly one of content_base64 and text")
        data = base64.b64decode(content_base64) if content_base64 else text.encode()
        form = p(source=source, source_type=source_type, published_at=published_at.isoformat() if published_at else None)
        return await call(ctx, "POST", await wm(ctx, world_model_id) + "/documents",
                          files=[("files", (filename, data))], data=form)

    @server.tool(title="Documents", description="Stored documents, by event time or ingestion time.", annotations=READ)
    async def world_model_list_documents(ctx: Context, world_model_id: str = "",
                                         order: Literal["event_time", "ingested_at"] = "event_time", limit: int = 50,
                                         cursor: str = "") -> dict:
        return await call(ctx, "GET", await wm(ctx, world_model_id) + "/documents",
                          params=p(order=order, limit=limit, cursor=cursor))

    @server.tool(title="A bundle", description="One bundle and its dated items, each with its signals and quotes.",
                 annotations=READ)
    async def world_model_get_bundle(ctx: Context, bundle_id: str, world_model_id: str = "") -> dict:
        path = await wm(ctx, world_model_id) + f"/bundles/{bundle_id}"
        bundle = await call(ctx, "GET", path)
        items = await call(ctx, "GET", path + "/items", params={"limit": 200})
        return {**bundle, "items": items["data"]}

    # -- changes ----------------------------------------------------------------------------------------------------------
    @server.tool(title="Propose changes", description="Needs changes:create (the data-ingestion pipeline). Propose one "
                 "change per bundle item (in event-time order). Each waits for a person's review; this tool never "
                 "approves.", annotations=PROPOSE)
    async def world_model_propose_changes(ctx: Context, bundle_id: str, world_model_id: str = "",
                                          item_ids: list[str] | None = None) -> dict:
        return await call(ctx, "POST", await wm(ctx, world_model_id) + "/changes",
                          json=p(bundle_id=bundle_id, item_ids=item_ids))

    @server.tool(title="Changes", description="Proposed changes (pending by default), with who proposed and decided "
                 "each.", annotations=READ)
    async def world_model_list_changes(ctx: Context, world_model_id: str = "",
                                       status: Literal["pending", "approved", "rejected", "deferred", "auto_applied",
                                                       "all"] = "pending", limit: int = 50, cursor: str = "") -> dict:
        return await call(ctx, "GET", await wm(ctx, world_model_id) + "/changes",
                          params=p(status=status, limit=limit, cursor=cursor))

    @server.tool(title="A change", description="One change and its diff: the operations approving it would apply.",
                 annotations=READ)
    async def world_model_get_change(ctx: Context, change_id: str, world_model_id: str = "") -> dict:
        path = await wm(ctx, world_model_id) + f"/changes/{change_id}"
        change = await call(ctx, "GET", path)
        diff = await call(ctx, "GET", path + "/diff")
        return {**change, "operations": diff["data"]["operations"]}

    # -- theses and simulations --------------------------------------------------------------------------------------------
    @server.tool(title="Simulate a what-if", description="Needs simulations:create. Pose a thesis (a question, or a "
                 "ready thesis template_id) and run it as a simulation on the latest version: the finished job names "
                 "the simulation.", annotations=PROPOSE)
    async def world_model_simulate(ctx: Context, world_model_id: str = "", question: str = "", template_id: str = "",
                                   horizon_days: int = 182) -> dict:
        path = await wm(ctx, world_model_id)
        thesis = await call(ctx, "POST", path + "/theses",
                            json=p(question=question, template_id=template_id, horizon_days=horizon_days))
        job = await call(ctx, "POST", path + f"/theses/{thesis['data']['id']}/simulations",
                         json={"horizon_days": horizon_days})
        return {"thesis": thesis["data"], "job": job["data"]}

    @server.tool(title="A simulation", description="One simulation: targets with ranges, the scenario table, and its "
                 "calculation coverage (what the numbers are made of, and the uncalibrated relationships they leave "
                 "out).", annotations=READ)
    async def world_model_get_simulation(ctx: Context, simulation_id: str, world_model_id: str = "") -> dict:
        path = await wm(ctx, world_model_id) + f"/simulations/{simulation_id}"
        sim = await call(ctx, "GET", path)
        cov = await call(ctx, "GET", path + "/coverage")
        return {**sim, "coverage": cov["data"]}

    @server.tool(title="A simulation's brief", description="Summary, expected timing, exposures, indicators, evidence.",
                 annotations=READ)
    async def world_model_simulation_brief(ctx: Context, simulation_id: str, world_model_id: str = "") -> dict:
        return await call(ctx, "GET", await wm(ctx, world_model_id) + f"/simulations/{simulation_id}/brief")

    @server.tool(title="Export (v4.1.4)", description="The world model (and a simulation, when given) in the client's "
                 "v4.1.4 world-model format.", annotations=READ)
    async def world_model_export_v4(ctx: Context, world_model_id: str = "", simulation_id: str = "") -> dict:
        return await call(ctx, "GET", await wm(ctx, world_model_id) + "/exports/v4.1.4",
                          params=p(simulation=simulation_id))

    @server.tool(title="A job", description="One job: its status, and what it produced or why it failed.",
                 annotations=READ)
    async def world_model_get_job(ctx: Context, job_id: str, world_model_id: str = "") -> dict:
        return await call(ctx, "GET", await wm(ctx, world_model_id) + f"/jobs/{job_id}")

    return server


def install_mcp(app: FastAPI, server: MCPServer) -> None:
    """The SDK's Streamable HTTP route at /mcp, on the FastAPI host (stateless, as core runs it). The SDK's session
    manager must run for the app's lifetime: api/app.py's lifespan enters `server.session_manager.run()`."""
    sdk_app = server.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=True,
                                         transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
    app.router.routes.extend(sdk_app.routes)
