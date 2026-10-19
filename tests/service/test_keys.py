"""Static scoped keys (api/keys.py) and the service's front door (api/auth.py): a key is a caller in one organization
with its scopes, opens only /v1 and /mcp, and every refusal is an RFC 9457 problem."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from axelrod_wm.api import tokens
from axelrod_wm.api.app import create_app
from axelrod_wm.api.auth import extra_logins, login_of, org_of, owners
from axelrod_wm.api.keys import ApiKey, api_keys, bearer, is_service_path, match
from axelrod_wm.api.tokens import READ
from axelrod_wm.repo.snapshots import MemoryBackend
from tests.service.helpers import Signer, problem, service

KEY_A = "a" * 32
KEY_S = "s" * 32


def test_keys_parse_from_the_environment_format():
    keys = api_keys(f" zsolt:{KEY_A}:acme , kedar:{KEY_S}:sally:world_model:read+admin ,")
    assert keys == [ApiKey("zsolt", KEY_A, "acme", frozenset({READ})),
                    ApiKey("kedar", KEY_S, "sally", frozenset({"world_model:read", "admin"}))]
    assert api_keys("") == []
    two = api_keys(f"z:{KEY_A}:acme,z:{KEY_S}:acme")
    assert [k.key for k in two] == [KEY_A, KEY_S]


@pytest.mark.parametrize("raw, why", [
    ("zsolt:short:acme", "shorter"),
    ("zsolt:" + KEY_A, "caller:key:org"),
    (":" + KEY_A + ":acme", "caller:key:org"),
    (f"z:{KEY_A}:a:world_model:read+telepathy", "unknown scopes: telepathy"),
    (f"z:{KEY_A}:a:+", r"unknown scopes: \(none\)"),
    (f"z:{KEY_A}:a:world_model:read+changes:approve", "only a person"),
    (f"z:{KEY_A}:a,z:{KEY_S}:a,z:{'c' * 32}:a", "more than twice"),
    (f"z:{KEY_A}:a,z:{KEY_S}:b", "two organizations"),
    (f"z:{KEY_A}:a,y:{KEY_A}:a", "one key twice"),
])
def test_malformed_keys_refuse_to_start(raw, why):
    with pytest.raises(RuntimeError, match=why):
        api_keys(raw)


def test_keys_are_read_from_the_environment_by_default(monkeypatch):
    monkeypatch.setenv("WORLD_MODEL_API_KEYS", f"c:{KEY_A}:l")
    assert api_keys() == [ApiKey("c", KEY_A, "l")]


@pytest.mark.parametrize("headers, token", [
    ({b"authorization": b"Bearer abc"}, "abc"),
    ({"authorization": "bearer  xyz "}, "xyz"),
    ({b"authorization": b"Basic abc"}, None),
    ({b"authorization": b"Bearer "}, None),
    ({}, None),
])
def test_bearer_tokens_are_read_from_either_header_form(headers, token):
    assert bearer(headers) == token


def test_a_token_matches_its_key_and_nothing_else():
    keys = api_keys(f"a:{KEY_A}:x,s:{KEY_S}:y")
    assert match(keys, KEY_S).caller == "s"
    assert match(keys, "nope" * 8) is None
    assert match(keys, None) is None
    assert match([], KEY_A) is None


@pytest.mark.parametrize("path, ok", [("/v1", True), ("/v1/world-models", True), ("/mcp", True), ("/mcp/x", True),
                                      ("/api/state", False), ("/v1x", False), ("/api/world-model", False),
                                      ("/", False)])
def test_service_paths(path, ok):
    assert is_service_path(path) is ok


# -- organizations of logins ---------------------------------------------------------------------------------------------
def test_owners_and_the_organization_of_a_login(monkeypatch):
    assert owners(" a=acme , b = beta ,") == {"a": "acme", "b": "beta"}
    with pytest.raises(RuntimeError, match="login=org"):
        owners("nobody")
    with pytest.raises(RuntimeError, match="username:password:scenario"):
        extra_logins("x:y")
    for var in ("WORLD_MODEL_BASIC_AUTH_USERNAME", "WORLD_MODEL_LOGINS", "WORLD_MODEL_OWNERS"):
        monkeypatch.delenv(var, raising=False)
    assert owners() == {} and org_of(None) == "default"
    assert login_of("default") is None and login_of("acme") is None
    monkeypatch.setenv("WORLD_MODEL_BASIC_AUTH_USERNAME", "admin")
    monkeypatch.setenv("WORLD_MODEL_LOGINS", "sally:pw:sally_demo")
    monkeypatch.setenv("WORLD_MODEL_OWNERS", "sally=tokio")
    assert org_of(None) == "admin" and org_of("sally") == "tokio" and org_of("other") == "other"
    assert login_of("admin") == "admin" and login_of("tokio") == "sally" and login_of("sally") is None


# -- the front door -------------------------------------------------------------------------------------------------------
SIGNER = Signer()


@pytest.fixture(scope="module")
def hosted():
    """A hosted-style app: a main login, Sally's login, a key for Sally's organization and one for an organization with
    no world model, and a trusted issuer."""
    with service(SIGNER, headers={"Authorization": ""}, WORLD_MODEL_BASIC_AUTH_USERNAME="admin",
                 WORLD_MODEL_BASIC_AUTH_PASSWORD="pw-admin", WORLD_MODEL_LOGINS="sally:pw-sally:sally_demo",
                 WORLD_MODEL_API_KEYS=f"zsolt:{KEY_A}:sally,ghost:{KEY_S}:nobody", scenario="small_demo") as c:
        yield c


def test_a_key_acts_in_its_organization(hosted):
    r = hosted.get("/v1/world-models", headers={"Authorization": f"Bearer {KEY_A}"})
    assert r.status_code == 200 and r.headers["x-axelrod-api-version"] == "1"
    assert [m["id"] for m in r.json()["data"]] == ["sally_demo"]
    me = hosted.get("/v1/me", headers={"Authorization": f"Bearer {KEY_A}"}).json()["data"]
    assert me["actor"]["sub"] == "zsolt" and me["actor"]["org"] == "sally"


def test_a_key_for_an_organization_without_models_sees_none(hosted):
    assert hosted.get("/v1/world-models", headers={"Authorization": f"Bearer {KEY_S}"}).json()["data"] == []


def test_no_credential_or_a_wrong_one_is_refused(hosted):
    body = problem(hosted.get("/v1/me"), 401, "authentication_required")
    assert "Bearer" in body["detail"]
    for token in ("x" * 32, "eyJ.not.ajwt"):
        r = hosted.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
        problem(r, 401, "invalid_token")
        assert r.headers["www-authenticate"] == "Bearer" and r.headers["cache-control"] == "no-store"


def test_a_service_token_acts_as_its_person(hosted):
    me = hosted.get("/v1/me", headers=SIGNER.bearer(org="sally")).json()["data"]
    assert me["actor"]["kind"] == "token" and me["actor"]["sub"] == "org_user_9" and me["actor"]["jti"]


def test_an_unknown_signing_key_is_401_and_an_issuer_down_is_503(hosted, monkeypatch):
    other = Signer(kid="rotated")
    problem(hosted.get("/v1/me", headers=other.bearer(org="sally")), 401, "invalid_token")

    def down(self, token):
        raise tokens.TokenError("issuer_unavailable", "the JWKS cannot be reached")

    monkeypatch.setattr(tokens.Verifier, "verify", down)
    problem(hosted.get("/v1/me", headers=SIGNER.bearer(org="sally")), 503, "issuer_unavailable")


def test_a_key_does_not_open_the_ui_or_its_api(hosted):
    assert hosted.get("/api/state", headers={"Authorization": f"Bearer {KEY_A}"}).status_code == 401


def test_a_signed_in_browser_may_call_the_service_as_its_login(hosted):
    hosted.post("/login", data={"username": "sally", "password": "pw-sally"}, follow_redirects=False)
    try:
        me = hosted.get("/v1/me").json()["data"]
        assert me["actor"] == {"kind": "session", "org": "sally", "sub": "sally", "name": None, "azp": None,
                               "act": None, "jti": None}
        assert "changes:approve" in me["scopes"]
    finally:
        hosted.cookies.clear()


def test_a_websocket_to_the_service_without_a_key_is_closed(hosted):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with hosted.websocket_connect("/mcp/ws"):
            pass


def test_a_local_run_without_keys_logins_or_issuers_is_open(monkeypatch):
    for var in ("WORLD_MODEL_BASIC_AUTH_USERNAME", "WORLD_MODEL_BASIC_AUTH_PASSWORD", "WORLD_MODEL_LOGINS",
                "WORLD_MODEL_REQUIRE_BASIC_AUTH", "RAILWAY_ENVIRONMENT_ID", "WORLD_MODEL_API_KEYS",
                "WORLD_MODEL_TRUSTED_ISSUERS"):
        monkeypatch.delenv(var, raising=False)
    app = create_app(scenario="small_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        me = c.get("/v1/me").json()["data"]
        assert me["actor"]["kind"] == "local" and me["actor"]["org"] == "default"


def test_a_local_run_with_keys_requires_one(monkeypatch):
    for var in ("WORLD_MODEL_BASIC_AUTH_USERNAME", "WORLD_MODEL_BASIC_AUTH_PASSWORD", "WORLD_MODEL_LOGINS",
                "WORLD_MODEL_TRUSTED_ISSUERS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("WORLD_MODEL_API_KEYS", f"local-tool:{KEY_A}:default")
    app = create_app(scenario="small_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        problem(c.get("/v1/me"), 401, "authentication_required")
        me = c.get("/v1/me", headers={"Authorization": f"Bearer {KEY_A}"}).json()["data"]
        assert me["actor"]["sub"] == "local-tool" and me["world_model_ids"] == ["small_demo"]
