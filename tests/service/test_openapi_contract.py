"""The contract, docs/api/openapi.yaml, against the service: the spec is valid OpenAPI 3.1; every route the app serves
under /v1 is in the spec and every operation in the spec is served (same methods); every answer, success or problem, has
a status the operation declares and a body its schema accepts; the problem codes are the spec's; and docs/api/README.md's
generated reference is current."""

from __future__ import annotations

import importlib.util
import re

import jsonschema
import pytest
import yaml
from openapi_spec_validator import validate

from axelrod_wm.api.v1.problems import CODES
from tests.service.helpers import NOTE, ROOT, V1, WM, Signer, data, decide_all, propose, service, upload

SPEC = yaml.safe_load((ROOT / "docs/api/openapi.yaml").read_text())
METHODS = ("get", "post", "put", "patch", "delete")
SIGNER = Signer()


def test_the_spec_is_valid_openapi():
    validate(SPEC)
    assert SPEC["openapi"] == "3.1.0" and SPEC["servers"][0]["url"].endswith("/v1")


def test_every_operation_is_complete():
    ids = []
    for path, item in SPEC["paths"].items():
        for method in METHODS:
            if method in item:
                op = item[method]
                ids.append(op["operationId"])
                assert op["summary"] and op["tags"] and op["x-required-scope"], (method, path)
                assert {"401", "403"} <= set(op["responses"]), (method, path)
                assert any(s.startswith("2") for s in op["responses"]), (method, path)
    assert len(ids) == len(set(ids)) >= 60


def test_the_problem_codes_are_the_specs():
    assert set(CODES) == set(SPEC["components"]["schemas"]["ProblemCode"]["enum"])


def test_the_reference_in_docs_api_readme_is_current():
    spec = importlib.util.spec_from_file_location("reference", ROOT / "scripts/api/reference.py")
    ref = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ref)
    assert ref.main(["--check"]) == 0


# -- route parity -----------------------------------------------------------------------------------------------------------
def served(app) -> set[tuple[str, str]]:
    """Every route the app serves under /v1, from the app's own generated schema (what is mounted, as FastAPI sees it),
    and from the v1 routers themselves (so no route hides from the schema)."""
    from axelrod_wm.api.v1 import routes_erid, routes_model, routes_work

    mounted = {(m, p.removeprefix(V1)) for p, ops in app.openapi()["paths"].items() if p.startswith(V1 + "/")
               for m in ops}
    routed = {(m.lower(), r.path.removeprefix(V1)) for router in (routes_model.router, routes_work.router, routes_erid.router)
              for r in router.routes for m in r.methods if m != "HEAD"}
    assert mounted == routed
    return mounted


def specified() -> set[tuple[str, str]]:
    return {(m, p) for p, item in SPEC["paths"].items() for m in METHODS if m in item}


@pytest.fixture(scope="module")
def c():
    with service(SIGNER) as client:
        yield client


def test_every_served_route_is_specified_and_the_reverse(c):
    have, want = served(c.app), specified()
    assert have - want == set(), "served but not in openapi.yaml"
    assert want - have == set(), "in openapi.yaml but not served"


# -- every answer matches its declared response --------------------------------------------------------------------------------
def resolve(x: dict) -> dict:
    while "$ref" in x:
        node = SPEC
        for part in x["$ref"][2:].split("/"):
            node = node[part]
        x = node
    return x


def check(op: dict, r) -> None:
    """The answer's status is declared by the operation, and its body is valid against the declared schema."""
    declared = op["responses"]
    assert str(r.status_code) in declared, (op["operationId"], r.status_code, r.text[:300])
    resp = resolve(declared[str(r.status_code)])
    content = resp.get("content")
    if not content:
        assert not r.content, op["operationId"]
        return
    ctype = r.headers["content-type"].split(";")[0]
    assert ctype in content, (op["operationId"], ctype, list(content))
    schema = content[ctype].get("schema")
    if schema is None or not ctype.endswith("json"):
        return
    jsonschema.Draft202012Validator({**schema, "components": SPEC["components"]}).validate(r.json())


def op_of(method: str, path: str) -> dict:
    return SPEC["paths"][path][method]


@pytest.fixture(scope="module")
def ids(c):
    """A model with one of everything: an uploaded note, its change approved, a thesis run."""
    res = upload(c, NOTE, "contract.md")
    propose(c, res["bundle_id"])
    decide_all(c, SIGNER)
    thesis = data(c.post(f"{WM}/theses", json={"template_id": "S-T3"}), 201)["id"]
    job = data(c.post(f"{WM}/theses/{thesis}/simulations"), 202)
    comp = data(c.get(f"{WM}/entities/acme_motors/compositions"))[0]["id"]
    path = data(c.get(f"{WM}/entities/acme_motors/paths"))[0]["id"]
    evidence = data(c.get(f"{WM}/relationships/m24/evidence"))
    return {
        "world_model_id": "acme_demo", "version_ref": "1", "entity_id": "acme_motors", "attribute_key": "operating_profit",
        "composition_id": comp, "path_id": path, "relationship_id": "m24",
        "evidence_id": evidence[0]["id"] if evidence else "EV-none",
        "concept_id": data(c.get(f"{WM}/concepts"))[0]["id"], "group_id": data(c.get(f"{WM}/groups"))[0]["id"],
        "event_id": data(c.get(f"{WM}/events"))[0]["id"], "document_id": res["document_id"], "ordinal": "0",
        "bundle_id": res["bundle_id"], "change_id": data(c.get(f"{WM}/changes", params={"status": "all"}))[0]["id"],
        "thesis_id": thesis, "compartment_id": "acme_focus", "simulation_id": job["result"]["ids"][0], "job_id": job["id"],
    }


QUERY = {"/world-models/{world_model_id}/entities/{entity_id}/traces": {"from": "dollar.index"}}
ADMIN_HEADERS = {}


def get_operations():
    return sorted(p for m, p in specified() if m == "get")


@pytest.mark.parametrize("path", get_operations())
def test_every_read_answers_as_declared(c, ids, path):
    url = V1 + re.sub(r"\{([a-z_]+)\}", lambda m: ids[m.group(1)], path)
    op = op_of("get", path)
    check(op, c.get(url, params=QUERY.get(path, {})))
    # and a world model that is not there is a declared 404 problem
    if "{world_model_id}" in path:
        check(op, c.get(url.replace("/acme_demo", "/nope", 1), params=QUERY.get(path, {})))


@pytest.mark.parametrize("path", [p for p in get_operations() if re.search(r"\{(?!world_model_id|version_ref)", p)])
def test_every_missing_resource_is_a_declared_problem(c, ids, path):
    names = re.findall(r"\{([a-z_]+)\}", path)
    last = names[-1]
    fake = {**ids, last: "999" if last == "ordinal" else "nope"}
    url = V1 + re.sub(r"\{([a-z_]+)\}", lambda m: fake[m.group(1)], path)
    r = c.get(url, params=QUERY.get(path, {}))
    assert r.status_code in (404, 422), (path, r.status_code)
    check(op_of("get", path), r)


def test_the_writes_answer_as_declared(c, ids):
    p = "/world-models/{world_model_id}"
    files = [("files", ("w.txt", b"Oct 22, 2026. Credit spreads rose by 25bp.", "text/plain"))]
    r = c.post(f"{WM}/documents", files=files)
    check(op_of("post", p + "/documents"), r)
    doc = r.json()["data"]["result"]["detail"]["results"][0]
    check(op_of("post", p + "/documents/{document_id}/bundles"), c.post(f"{WM}/documents/{doc['document_id']}/bundles"))
    check(op_of("post", p + "/bundles"), c.post(f"{WM}/bundles", json={"format": "axelrod.import/v1", "items": []}))
    check(op_of("post", p + "/bundles"), c.post(f"{WM}/bundles", content=b"x", headers={"content-type": "text/plain"}))
    r = c.post(f"{WM}/changes", json={"bundle_id": doc["bundle_id"]})
    check(op_of("post", p + "/changes"), r)
    check(op_of("post", p + "/changes"), c.post(f"{WM}/changes", json={"bundle_id": doc["bundle_id"]}))
    pending = data(c.get(f"{WM}/changes"))
    etag = c.get(WM).headers["etag"]
    url = f"{WM}/changes/{pending[0]['id']}"
    check(op_of("post", p + "/changes/{change_id}/approvals"), c.post(url + "/approvals", json={}))
    check(op_of("post", p + "/changes/{change_id}/approvals"),
          c.post(url + "/approvals", json={}, headers=SIGNER.bearer()))
    check(op_of("post", p + "/changes/{change_id}/approvals"),
          c.post(url + "/approvals", json={}, headers={**SIGNER.bearer(), "If-Match": '"old"'}))
    check(op_of("post", p + "/changes/{change_id}/rejections"),
          c.post(url + "/rejections", json={"reason": "no"}, headers={**SIGNER.bearer(), "If-Match": etag}))
    check(op_of("post", p + "/changes/{change_id}/rejections"),
          c.post(url + "/rejections", json={"reason": "no"}, headers={**SIGNER.bearer(), "If-Match": etag}))
    decide_all(c, SIGNER)
    check(op_of("post", p + "/theses"), c.post(f"{WM}/theses", json={"question": "What if the central bank hiked by 25bp?"}))
    check(op_of("post", p + "/theses"), c.post(f"{WM}/theses", json={"nonsense": 1}))
    check(op_of("post", p + "/theses/{thesis_id}/simulations"), c.post(f"{WM}/theses/{ids['thesis_id']}/simulations"))
    check(op_of("post", p + "/theses/{thesis_id}/simulations"), c.post(f"{WM}/theses/T-nope/simulations"))
    check(op_of("delete", p + "/documents/{document_id}"), c.delete(f"{WM}/documents/{doc['document_id']}"))
    check(op_of("delete", p + "/documents/{document_id}"), c.delete(f"{WM}/documents/{doc['document_id']}"))


def test_every_companys_construction_answers_as_declared(c):
    """Every company built in the world (its compositions, paths, identities, stock-flows), not just one: each view
    projects onto the contract."""
    g = c.app.state.world_models["acme_demo"].st.controller.engine.wm.graph
    companies = sorted({x.entity_id for x in g.compositions.values()} | {p.entity_id for p in g.paths.values()})
    assert len(companies) >= 3
    p = "/world-models/{world_model_id}/entities/{entity_id}"
    for eid in companies:
        for suffix in ("/construction", "/compositions", "/paths"):
            check(op_of("get", p + suffix), c.get(f"{WM}/entities/{eid}{suffix}", params={"limit": 200}))


def test_refusals_answer_as_declared(c):
    op = op_of("get", "/world-models/{world_model_id}/entities")
    check(op, c.get(f"{WM}/entities", headers={"Authorization": ""}))
    check(op, c.get(f"{WM}/entities", headers={"Authorization": "Bearer " + "x" * 32}))
    check(op, c.get(f"{WM}/entities", params={"limit": 0}))
    check(op, c.get(f"{WM}/entities", params={"cursor": "!!"}))
    check(op_of("get", "/world-models/{world_model_id}/audit-events"),
          c.get(f"{WM}/audit-events", headers=SIGNER.bearer(scope="world_model:read")))
