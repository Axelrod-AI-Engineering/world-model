"""The unified world model, `/v1/erid` (Oct 19; api/v1/compartments.py, world_model/docs/design/api.md §4): the whole graph for
internal staff, and its compartments.

Its own routes describe it and its compartments. Its reads mirror the per-world-model reads of the graph
(`/world-models/{id}/entities`, `…/relationships`, `…/graph`, …) with an optional `compartment` that narrows them:
the same handlers, the same scopes, run on the unified model. Writes go through the unified model's own world model
(`/v1/world-models/{world_model_id}` in `GET /v1/erid`), with the same review and audit; learning lands in the
unified graph and reaches every compartment it belongs to."""

from __future__ import annotations

import inspect
import typing
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from axelrod_wm.api.tokens import READ
from axelrod_wm.api.v1 import routes_model
from axelrod_wm.api.v1 import schemas as s
from axelrod_wm.api.v1.compartments import Compartment, internal_orgs, narrow, owners
from axelrod_wm.api.v1.context import Model, decode_cursor, many, one, page, principal, require, unified
from axelrod_wm.api.v1.context import version_ref as vref
from axelrod_wm.api.v1.problems import V1Route

router = APIRouter(prefix="/v1", route_class=V1Route, tags=["v1"])
E = "/erid"
W = "/v1/world-models/{world_model_id}"
# the per-world-model reads of the graph that erid mirrors (each narrows to a compartment)
MIRRORED = ("/versions", "/versions/{version_ref}", "/entities", "/entities/{entity_id}",
            "/entities/{entity_id}/attributes", "/entities/{entity_id}/attributes/{attribute_key}",
            "/entities/{entity_id}/attributes/{attribute_key}/observations",
            "/entities/{entity_id}/attributes/{attribute_key}/states", "/entities/{entity_id}/compositions",
            "/entities/{entity_id}/compositions/{composition_id}", "/entities/{entity_id}/paths",
            "/entities/{entity_id}/paths/{path_id}", "/entities/{entity_id}/construction",
            "/entities/{entity_id}/traces", "/relationships", "/relationships/{relationship_id}",
            "/relationships/{relationship_id}/evidence", "/evidence/{evidence_id}", "/graph")
CompartmentQ = Annotated[str | None, Query(description="A compartment of the unified model: reads see only it")]


@dataclass
class Erid:
    model: Model
    internal: frozenset[str]
    compartments: dict[str, Compartment]
    owners: dict[str, str]                  # compartment -> the organization it is assigned to


def build(world_models: dict[str, Model], main_id: str) -> Erid:
    from axelrod_wm.api.v1.compartments import discover

    m = world_models[main_id]
    return Erid(model=m, internal=internal_orgs(m.org), compartments=discover(m.st.first_scenario), owners=owners())


# -- its own routes -----------------------------------------------------------------------------------------------------
def counts(wm: Any) -> s.CompartmentCounts:
    g = wm.graph
    return s.CompartmentCounts(entities=len(g.entities), attributes=len(g.subentities),
                               relationships=len(g.active_interactions()))


def visible(request: Request) -> list[Compartment]:
    erid = request.app.state.erid
    org = principal(request).org
    return [c for _k, c in sorted(erid.compartments.items()) if org in erid.internal or erid.owners.get(c.id) == org]


def compartment_view(m: Model, c: Compartment) -> s.Compartment:
    return s.Compartment(id=c.id, title=c.title, base=c.spec.base, companies=list(c.spec.companies),
                         counts=counts(narrow(m.st.controller.engine.wm, c)))


@router.get(E, summary="The unified world model: the whole graph (internal staff)")
async def get_erid(request: Request) -> Response:
    m = unified(request, "", READ)
    eng = m.st.controller.engine
    body = s.UnifiedWorldModel(id="erid", scenario=m.st.first_scenario, world_model_id=m.id,
                               latest_version=eng.version, clock=eng.wm.clock, counts=await m.st.call(counts, eng.wm),
                               compartment_ids=sorted(request.app.state.erid.compartments))
    return one(request, body, await m.st.call(vref, m.st), tag=True)


@router.get(E + "/compartments", summary="The compartments of the unified model the credential may read")
async def list_compartments(request: Request, limit: routes_model.Limit = 50,
                            cursor: routes_model.Cursor = None) -> Response:
    require(request, READ)
    m = request.app.state.erid.model
    off, _v = decode_cursor(cursor)
    rows = [await m.st.call(compartment_view, m, c) for c in visible(request)]
    chunk, nxt = page(rows, off, limit, None)
    return many(request, chunk, limit, nxt, await m.st.call(vref, m.st))


@router.get(E + "/compartments/{compartment_id}", summary="One compartment: its companies and size")
async def get_compartment(request: Request, compartment_id: str) -> Response:
    m = unified(request, compartment_id, READ)
    return one(request, await m.st.call(compartment_view, m, m.compartment), await m.st.call(vref, m.st))


# -- the mirrored reads ---------------------------------------------------------------------------------------------------
def mirror(route: Any) -> Any:
    """A per-world-model read run on the unified model: the same handler, without `world_model_id`, with an optional
    `compartment`."""
    original = route.endpoint
    hints = typing.get_type_hints(original, include_extras=True)
    params = [p.replace(annotation=hints.get(p.name, p.annotation))
              for p in inspect.signature(original).parameters.values() if p.name != "world_model_id"]
    params.append(inspect.Parameter("compartment", inspect.Parameter.KEYWORD_ONLY, default=None,
                                    annotation=CompartmentQ))

    async def endpoint(request: Request, compartment: str | None = None, **kw: Any) -> Response:
        request.scope["axelrod_erid"] = compartment or ""
        return await original(request=request, world_model_id="erid", **kw)

    endpoint.__signature__ = inspect.Signature(params, return_annotation=Response)
    endpoint.__name__ = f"erid_{original.__name__}"
    return endpoint


for _route in list(routes_model.router.routes):
    _suffix = _route.path.removeprefix(W)
    if _route.path.startswith(W) and _suffix in MIRRORED:
        router.add_api_route(E + _suffix, mirror(_route), methods=["GET"],
                             summary=f"{_route.summary} (the unified model, or a compartment)")
