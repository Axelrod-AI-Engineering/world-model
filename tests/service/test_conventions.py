"""Every route of the outward service keeps the API's conventions (docs/api.md, Conventions), checked across all of
them rather than one at a time, so a route added later cannot quietly skip one: it is documented and summarized, it
refuses a caller without a key, every answer carries the version header, every failure is core's envelope with a
documented code, and a JSON body with an unknown field is refused."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.api.service import router
from axelrod_wm.repo.snapshots import MemoryBackend

B = "/api/world-model"
KEY = "k" * 32
DOC = Path("docs/api.md").read_text()
# the codes the docs list in the Conventions table, plus the auth one
CODES = set(re.findall(r"`([a-z_]+)`", DOC[DOC.index("| Status | Codes |"):DOC.index("- **Bodies**")]))


def _routes() -> list[tuple[str, str]]:
    return sorted((m, r.path) for r in router.routes for m in r.methods if m != "HEAD")


ROUTES = _routes()


def _concrete(path: str) -> str:
    """A route's path with every parameter filled by an id that names nothing."""
    return re.sub(r"\{[^}]+\}", "nothing-here", path)


@pytest.fixture(scope="module")
def client():
    mp = pytest.MonkeyPatch()
    mp.setenv("WORLD_MODEL_BASIC_AUTH_USERNAME", "admin")
    mp.setenv("WORLD_MODEL_BASIC_AUTH_PASSWORD", "pw-admin")
    mp.setenv("WORLD_MODEL_API_KEYS", f"tester:{KEY}:admin")
    mp.setenv("WORLD_MODEL_EMBEDDER", "hashing")
    mp.setenv("WORLD_MODEL_LAKE_DIR", tempfile.mkdtemp())
    app = create_app(scenario="sally_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        yield c
    mp.undo()


def test_the_service_has_the_routes_this_test_walks():
    assert len(ROUTES) >= 25 and ("GET", f"{B}/state") in ROUTES and ("POST", f"{B}/forecasts") in ROUTES


def _norm(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path.split("?")[0])


# every route the docs name in a table cell or in prose, as "METHOD /path" (parameter names differ: {id}, {doc_id})
DOCUMENTED = {(m, _norm(p)) for m, p in re.findall(r"`(GET|POST|DELETE) (/[^`\s]*)", DOC)}
DOCUMENTED |= {("GET", _norm(p)) for p in re.findall(r"`GET [^`]*`, `GET (/[^`\s]*)", DOC)}


@pytest.mark.parametrize("method,path", ROUTES)
def test_every_route_is_documented_and_summarized(method, path):
    route = next(r for r in router.routes if r.path == path and method in r.methods)
    assert route.summary, f"{method} {path} has no summary for /docs"
    assert (method, _norm(path.removeprefix(B))) in DOCUMENTED, f"{method} {path} is not in docs/api.md"


@pytest.mark.parametrize("method,path", ROUTES)
def test_every_route_refuses_a_caller_without_a_key(client, method, path):
    for headers in ({}, {"Authorization": "Bearer " + "x" * 32}):
        r = client.request(method, _concrete(path), headers=headers)
        assert r.status_code == 401, (method, path, r.status_code)
        assert r.json()["error"]["code"] == "authentication_required" and r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("method,path", ROUTES)
def test_every_answer_has_the_version_header_and_every_failure_the_envelope(client, method, path):
    r = client.request(method, _concrete(path), headers={"Authorization": f"Bearer {KEY}"})
    assert r.headers.get("x-axelrod-api-version") == "1", (method, path, r.status_code)
    assert r.status_code < 500, (method, path, r.text[:300])
    if r.status_code >= 400:
        body = r.json()
        assert set(body) == {"error"} and {"code", "message"} <= set(body["error"]), (method, path, body)
        assert body["error"]["code"] in CODES, (method, path, body["error"]["code"], "not in docs/api.md's table")


JSON_BODIES = [(m, p) for m, p in ROUTES if m == "POST" and not p.endswith("/documents")]


@pytest.mark.parametrize("method,path", JSON_BODIES)
def test_every_json_body_refuses_an_unknown_field(client, method, path):
    r = client.request(method, _concrete(path), json={"surely_not_a_field": 1},
                       headers={"Authorization": f"Bearer {KEY}"})
    assert r.headers["x-axelrod-api-version"] == "1"
    # a route whose target does not exist may answer 404 before reading the body; any other answer must refuse
    assert r.status_code in (404, 422), (method, path, r.status_code, r.text[:200])
    assert r.json()["error"]["code"] in ("invalid_request", "not_found") or r.json()["error"]["code"].endswith(
        "_not_found"), (method, path, r.json())


def test_the_openapi_schema_lists_every_route(client):
    schema = client.app.openapi()                       # what /openapi.json serves (behind the site's sign-in)
    listed = {(m.upper(), p) for p, ops in schema["paths"].items() for m in ops}
    assert {(m, p) for m, p in ROUTES} <= listed
