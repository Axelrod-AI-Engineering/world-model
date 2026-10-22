"""Every v1 route keeps the API's conventions (docs/api/README.md, Conventions), checked across all of them so a route added
later cannot skip one: it has a summary, it refuses a caller without a credential, every answer carries X-Request-Id
(echoing the caller's) and X-Axelrod-API-Version, traceparent is echoed, every failure is an RFC 9457 problem with a
code of the contract's, and a JSON body with an unknown field is refused."""

from __future__ import annotations

import re

import pytest
import yaml

from axelrod_wm.api.v1 import routes_erid, routes_model, routes_work
from tests.service.helpers import ROOT, V1, Signer, service

SPEC = yaml.safe_load((ROOT / "world_model/docs/api/openapi.yaml").read_text())
CODES = set(SPEC["components"]["schemas"]["ProblemCode"]["enum"])
ROUTES = sorted((m, r.path) for router in (routes_model.router, routes_work.router, routes_erid.router) for r in router.routes
                for m in r.methods if m != "HEAD")
SIGNER = Signer()
TRACE = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def concrete(path: str) -> str:
    """A route's path in the acme_demo model, every other parameter filled by an id that names nothing."""
    return re.sub(r"\{[^}]+\}", "nothing-here", path.replace("{world_model_id}", "acme_demo")).replace(
        "versions/nothing-here", "versions/999")


@pytest.fixture(scope="module")
def client():
    with service(SIGNER) as c:
        yield c


def test_the_walk_covers_the_routes():
    assert len(ROUTES) >= 60 and ("GET", f"{V1}/me") in ROUTES


@pytest.mark.parametrize("method,path", ROUTES)
def test_every_route_has_a_summary(method, path):
    route = next(r for router in (routes_model.router, routes_work.router, routes_erid.router) for r in router.routes
                 if r.path == path and method in r.methods)
    assert route.summary, f"{method} {path} has no summary"


@pytest.mark.parametrize("method,path", ROUTES)
def test_every_route_refuses_a_caller_without_a_credential(client, method, path):
    for headers in ({"Authorization": ""}, {"Authorization": "Bearer " + "x" * 32}):
        r = client.request(method, concrete(path), headers=headers)
        assert r.status_code == 401, (method, path, r.status_code)
        assert r.headers["content-type"].startswith("application/problem+json")
        assert r.json()["code"] in ("authentication_required", "invalid_token")
        assert r.headers["www-authenticate"] == "Bearer" and r.headers["x-axelrod-api-version"] == "1"


@pytest.mark.parametrize("method,path", ROUTES)
def test_every_answer_has_the_headers_and_every_failure_is_a_problem(client, method, path):
    rid = "req_from_the_caller_1"
    r = client.request(method, concrete(path), headers={"X-Request-Id": rid, "traceparent": TRACE})
    assert r.headers.get("x-axelrod-api-version") == "1", (method, path, r.status_code)
    assert r.headers["x-request-id"] == rid and r.headers["traceparent"] == TRACE, (method, path)
    assert r.status_code < 500, (method, path, r.text[:300])
    if r.status_code >= 400:
        assert r.headers["content-type"].startswith("application/problem+json"), (method, path)
        body = r.json()
        assert body["code"] in CODES and body["request_id"] == rid and body["status"] == r.status_code, (path, body)


def test_a_request_id_that_is_not_safe_is_replaced(client):
    r = client.get(f"{V1}/me", headers={"X-Request-Id": "bad id\twith spaces" + "x" * 300})
    assert r.headers["x-request-id"].startswith("req_")


JSON_BODIES = [(m, p) for m, p in ROUTES if m == "POST" and not p.endswith(("/documents", "/bundles"))]


@pytest.mark.parametrize("method,path", JSON_BODIES)
def test_every_json_body_refuses_an_unknown_field(client, method, path):
    r = client.request(method, concrete(path), json={"surely_not_a_field": 1},
                       headers={**SIGNER.bearer(), "If-Match": '"x"'})
    assert r.headers["x-axelrod-api-version"] == "1"
    # a route whose target does not exist may answer 404 before reading the body; any other answer must refuse
    assert r.status_code in (404, 422), (method, path, r.status_code, r.text[:200])
    code = r.json()["code"]
    assert code == "invalid_request" or code.endswith("_not_found"), (method, path, code)


def test_an_unknown_v1_path_is_a_problem(client):
    r = client.get(f"{V1}/nothing/here")
    assert r.status_code == 404 and r.json()["code"] == "not_found"
    assert r.headers["content-type"].startswith("application/problem+json") and r.headers["x-request-id"]
    # outside /v1, a missing route answers as the app always has
    other = client.get("/api/no-such-route")
    assert other.status_code == 404 and not other.headers["content-type"].startswith("application/problem+json")
