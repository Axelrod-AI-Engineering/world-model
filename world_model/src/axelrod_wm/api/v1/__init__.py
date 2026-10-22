"""The world model API, v1 (Oct 18): the routes docs/api/openapi.yaml specifies, under /v1/world-models/{id}.

    problems.py       RFC 9457 problems, the standard headers, the route class
    context.py        the principal, the world model registry, pinning, cursors, envelopes, idempotency, audit, jobs
    schemas.py        the API model (the contract's shapes)
    project.py        the domain model projected onto the API model
    routes_model.py   reads of the model: world models, versions, entities, attributes, construction, relationships,
                      evidence, concepts, groups, the graph, exports, the audit log
    routes_ingest.py  documents, passages, bundles and their items, search: only axelrod_ingest and the plumbing
    routes_work.py    events, changes and their review, theses, simulations, jobs
"""

from __future__ import annotations

from typing import Any

from starlette.exceptions import HTTPException as StarletteHTTPException


def install(app: Any) -> None:
    """Mount v1 on the app: its routes, its registry of world models, and its in-memory stores."""
    from fastapi.exception_handlers import http_exception_handler

    from axelrod_wm.api.v1 import routes_erid
    from axelrod_wm.api.v1.context import build_registry
    from axelrod_wm.api.v1.problems import not_found_handler
    from axelrod_wm.api.v1.routes_ingest import router as ingest_router
    from axelrod_wm.api.v1.routes_model import router as model_router
    from axelrod_wm.api.v1.routes_work import router as work_router

    app.include_router(model_router)
    app.include_router(ingest_router)
    app.include_router(work_router)
    app.include_router(routes_erid.router)
    app.state.world_models = build_registry(app)
    # the unified world model (erid) is the main engine's: a deployment runs its fullest scenario there
    app.state.erid = routes_erid.build(app.state.world_models, app.state.axelrod.first_scenario)
    app.state.theses = {}
    app.state.proposing = set()             # world models with a proposal starting (POST .../changes)
    app.add_exception_handler(StarletteHTTPException, not_found_handler(http_exception_handler))
