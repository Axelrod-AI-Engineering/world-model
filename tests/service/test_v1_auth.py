"""Who may do what on v1 (docs/design/core-mcp-auth.md): every route's scope, organizations kept apart (another's world
model is 404), decisions by a person only, and the audit log naming the actor, organization, channel, act and jti."""

from __future__ import annotations

import re

import pytest
import yaml

from tests.service.helpers import (
    NOTE,
    ROOT,
    V1,
    WM,
    Signer,
    data,
    decide_all,
    etag_now,
    problem,
    propose,
    service,
    upload,
)

SIGNER = Signer()
SPEC = yaml.safe_load((ROOT / "docs/api/openapi.yaml").read_text())
A, B, R, ADM = "a" * 32, "b" * 32, "r" * 32, "m" * 32
TWO_ORGS = dict(
    WORLD_MODEL_BASIC_AUTH_USERNAME="admin", WORLD_MODEL_BASIC_AUTH_PASSWORD="pw-admin",
    WORLD_MODEL_LOGINS="eve:pw-eve:small_demo,dup:pw-dup:acme_demo",
    WORLD_MODEL_OWNERS="dup=acme",
    WORLD_MODEL_API_KEYS=(f"tester:{A}:admin:world_model:read+documents:create+changes:create+simulations:create+admin,"
                          f"eve-tool:{B}:eve,reader:{R}:admin,ops:{ADM}:admin:admin"),
)


@pytest.fixture(scope="module")
def c():
    with service(SIGNER, headers={"Authorization": f"Bearer {A}"}, **TWO_ORGS) as client:
        yield client


def as_(key):
    return {"Authorization": f"Bearer {key}"}


def operations():
    for path, ops in SPEC["paths"].items():
        for method, op in ops.items():
            if method in ("get", "post", "delete"):
                yield method, path, op


def concrete(path):
    fixed = (V1 + path).replace("{world_model_id}", "acme_demo").replace("{version_ref}", "1").replace(
        "{ordinal}", "0")
    return re.sub(r"\{[a-z_]+\}", "x", fixed)


def resolve(x):
    while "$ref" in x:
        node = SPEC
        for part in x["$ref"][2:].split("/"):
            node = node[part]
        x = node
    return x


def required_query(op):
    params = [resolve(p) for p in op.get("parameters", [])]
    return {p["name"]: "x" for p in params if p.get("in") == "query" and p.get("required")}


def call(c, method, path, op, headers):
    url = concrete(path)
    if method == "post" and path.endswith("/documents"):
        return c.post(url, files=[("files", ("x.txt", b"x", "text/plain"))], headers=headers)
    bodies = {"/changes": {"bundle_id": "x"}, "/rejections": {"reason": "x"}, "/theses": {"template_id": "S-T1"},
              "/bundles": {"format": "axelrod.import/v1", "items": []}}
    body = next((b for suffix, b in bodies.items() if path.endswith(suffix)), {})
    return c.request(method.upper(), url, params=required_query(op), json=body if method == "post" else None,
                     headers=headers)


# -- scopes ---------------------------------------------------------------------------------------------------------------
def test_every_route_needs_its_scope(c):
    """A key holding only `world_model:read` (a key's default), and one holding only `admin`: each route answers 403
    to the one without its scope; a decision tells a key that a person decides, before any scope."""
    swept = 0
    for method, path, op in operations():
        need = op["x-required-scope"]
        for key, has in ((R, {"world_model:read"}), (ADM, {"admin"})):
            if need in has:
                continue
            r = call(c, method, path, op, as_(key))
            if need == "changes:approve":
                problem(r, 403, "human_approval_required")
            else:
                body = problem(r, 403, "insufficient_scope")
                assert need in body["detail"] and f'scope="{need}"' in r.headers["www-authenticate"], (method, path)
            swept += 1
    assert swept >= 60


def test_a_token_carries_only_the_scopes_it_names(c):
    h = SIGNER.bearer(org="admin", scope="world_model:read made:up")
    me = data(c.get(f"{V1}/me", headers=h))
    assert me["scopes"] == ["world_model:read"] and me["actor"]["kind"] == "token" and me["actor"]["azp"] == "core-web"
    problem(c.post(f"{WM}/theses", json={"template_id": "S-T1"}, headers=h), 403, "insufficient_scope")


def test_me_names_the_key_and_its_models(c):
    me = data(c.get(f"{V1}/me"))
    assert me["actor"] == {"kind": "key", "org": "admin", "sub": "tester", "name": None, "azp": None, "act": None,
                           "jti": None}
    assert "changes:approve" not in me["scopes"] and me["world_model_ids"] == ["acme_demo"]


# -- organizations ---------------------------------------------------------------------------------------------------------
def test_each_organization_sees_only_its_world_models(c):
    assert [m["id"] for m in data(c.get(f"{V1}/world-models"))] == ["acme_demo"]
    eve = data(c.get(f"{V1}/world-models", headers=as_(B)))
    assert [m["id"] for m in eve] == ["small_demo"] and eve[0]["organization"] == "eve"
    for url in (WM, f"{WM}/entities", f"{WM}/changes", f"{WM}/jobs/job_x"):
        problem(c.get(url, headers=as_(B)), 404, "world_model_not_found")
    problem(c.get(f"{V1}/world-models/small_demo"), 404, "world_model_not_found")
    problem(c.get(f"{V1}/world-models/nope"), 404, "world_model_not_found")
    # a second engine on the same scenario is named by its login, and WORLD_MODEL_OWNERS puts it in acme
    acme = data(c.get(f"{V1}/world-models", headers=SIGNER.bearer(org="acme")))
    assert [m["id"] for m in acme] == ["dup-acme_demo"] and acme[0]["organization"] == "acme"


def test_the_registry_is_in_the_lakehouse(c):
    rows = {r.id: r.org_id for r in c.app.state.lake.world_models()}
    assert rows == {"acme_demo": "admin", "small_demo": "eve", "dup-acme_demo": "acme"}
    assert [r.id for r in c.app.state.lake.world_models(org_id="eve")] == ["small_demo"]


def test_another_organizations_documents_stay_its_own(c):
    mine = upload(c, NOTE, "mine.md")
    problem(c.get(f"{V1}/world-models/small_demo/documents/{mine['document_id']}", headers=as_(B)), 404,
            "document_not_found")
    problem(c.get(f"{WM}/documents/{mine['document_id']}", headers=as_(B)), 404, "world_model_not_found")


# -- decisions by a person --------------------------------------------------------------------------------------------------
def test_only_a_person_decides(c):
    res = upload(c, b"Oct 6, 2026. The BoJ raised its policy rate by 25bp to 1.25%.", "boj.txt")
    first = propose(c, res["bundle_id"])["result"]["ids"][0]
    url = f"{WM}/changes/{first}/approvals"
    agent = dict(org="admin", act={"sub": "mcp-client:claude", "name": "Claude"})
    for h in (as_(A), SIGNER.bearer(**agent), SIGNER.bearer(org="admin", azp="core-mcp")):
        problem(c.post(url, json={}, headers={**h, "If-Match": etag_now(c)}), 403, "human_approval_required")
    # a token without the review scope
    problem(c.post(url, json={}, headers={**SIGNER.bearer(org="admin", scope="world_model:read"), "If-Match": etag_now(c)}), 403,
            "insufficient_scope")
    # a person signed in to this service
    c.post("/login", data={"username": "admin", "password": "pw-admin"}, follow_redirects=False)
    try:
        session = {"Authorization": ""}
        me = data(c.get(f"{V1}/me", headers=session))
        assert me["actor"]["kind"] == "session" and "changes:approve" in me["scopes"]
        ok = data(c.post(url, json={"note": "read it"}, headers={**session, "If-Match": etag_now(c)}), 201)
        assert ok["decided_by"]["kind"] == "session" and ok["decided_by"]["sub"] == "admin"
    finally:
        c.cookies.clear()
    decide_all(c, SIGNER, org="admin")


# -- the audit log --------------------------------------------------------------------------------------------------------
def test_every_write_is_audited_with_who_asked(c):
    # core's MCP and any agent read only (Oct 19): a write from them is refused, and a person's write is audited
    agent = SIGNER.bearer(org="admin", azp="core-mcp", act={"sub": "mcp-client:claude", "name": "Claude"},
                          scope="world_model:read simulations:create")
    problem(c.post(f"{WM}/theses", json={"template_id": "S-T1"}, headers=agent), 403, "insufficient_scope")
    person = SIGNER.bearer(org="admin", scope="world_model:read simulations:create", jti="jti-person-1")
    t = data(c.post(f"{WM}/theses", json={"template_id": "S-T1"}, headers=person), 201)
    rows = data(c.get(f"{WM}/audit-events", params={"limit": 200}, headers=as_(ADM)))
    assert rows and all(r["world_model_id"] == "acme_demo" for r in rows)
    newest = rows[0]
    assert newest["method"] == "POST" and newest["route"] == "/v1/world-models/{world_model_id}/theses"
    assert newest["status"] == 201 and t["id"] in newest["resource_ids"] and newest["request_id"]
    assert newest["actor"]["act"] is None and newest["actor"]["sub"] == "org_user_9"
    assert newest["actor"]["azp"] == "core-web" and newest["actor"]["jti"] == "jti-person-1"
    assert newest["actor"]["org"] == "admin" and newest["scopes"] == ["simulations:create", "world_model:read"]
    routes = {r["route"].rsplit("/", 1)[-1] for r in rows}
    assert {"documents", "changes", "approvals", "theses"} <= routes
    decided = [r for r in rows if r["route"].endswith("/approvals")]
    assert decided and all(r["actor"]["kind"] in ("token", "session") for r in decided)
    page1 = c.get(f"{WM}/audit-events", params={"limit": 1}, headers=as_(ADM)).json()
    assert page1["meta"]["next_cursor"] and page1["data"][0] == newest
    assert data(c.get(f"{V1}/world-models/small_demo/audit-events", headers=SIGNER.bearer(org="eve",
                                                                                          scope="admin"))) == []


def test_a_rejected_request_is_not_audited(c):
    before = len(data(c.get(f"{WM}/audit-events", params={"limit": 200}, headers=as_(ADM))))
    problem(c.post(f"{WM}/theses", json={"template_id": "S-nope"}), 404, "thesis_not_found")
    assert len(data(c.get(f"{WM}/audit-events", params={"limit": 200}, headers=as_(ADM)))) == before


# -- an open local run ---------------------------------------------------------------------------------------------------------
def test_a_local_run_is_open_but_never_decides():
    nothing = {k: "" for k in TWO_ORGS} | {"WORLD_MODEL_TRUSTED_ISSUERS": ""}
    with service(headers={"Authorization": ""}, **nothing) as c:
        me = data(c.get(f"{V1}/me"))
        assert me["actor"]["kind"] == "local" and me["actor"]["org"] == "default"
        assert "admin" in me["scopes"] and "changes:approve" not in me["scopes"]
        problem(c.post(f"{WM}/changes/PR-1/approvals", json={}, headers={"If-Match": '"x"'}), 403,
                "human_approval_required")
