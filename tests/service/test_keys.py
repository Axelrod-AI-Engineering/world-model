"""API keys and the service's authentication (api/keys.py, api/auth.py): a key acts as one login, opens only the
service's paths, and every failure answers in core's envelope."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.api.keys import ApiKey, api_keys, bearer, is_service_path, match
from axelrod_wm.repo.snapshots import MemoryBackend

KEY_A = "a" * 32
KEY_S = "s" * 32


def test_keys_parse_from_the_environment_format():
    keys = api_keys(f" zsolt:{KEY_A}:admin , kedar:{KEY_S}:sally ,")
    assert keys == [ApiKey("zsolt", KEY_A, "admin"), ApiKey("kedar", KEY_S, "sally")]
    assert api_keys("") == []


@pytest.mark.parametrize("raw, why", [
    ("zsolt:short:admin", "shorter"),
    ("zsolt:" + KEY_A, "caller:key:login"),
    (":" + KEY_A + ":admin", "caller:key:login"),
    (f"z:{KEY_A}:a,z:{KEY_S}:b", "twice"),
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


@pytest.mark.parametrize("path, ok", [("/api/world-model", True), ("/api/world-model/state", True), ("/mcp", True),
                                      ("/mcp/x", True), ("/api/state", False), ("/api/world-modelx", False), ("/", False)])
def test_service_paths(path, ok):
    assert is_service_path(path) is ok


# -- the middleware ---------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def hosted():
    """A hosted-style app: a main login, Sally's login, and two API keys (one for a login that does not exist)."""
    mp = pytest.MonkeyPatch()
    mp.setenv("WORLD_MODEL_BASIC_AUTH_USERNAME", "admin")
    mp.setenv("WORLD_MODEL_BASIC_AUTH_PASSWORD", "pw-admin")
    mp.setenv("WORLD_MODEL_LOGINS", "sally:pw-sally:sally_demo")
    mp.setenv("WORLD_MODEL_API_KEYS", f"zsolt:{KEY_A}:sally,ghost:{KEY_S}:nobody")
    mp.setenv("WORLD_MODEL_EMBEDDER", "hashing")
    import tempfile

    mp.setenv("WORLD_MODEL_LAKE_DIR", tempfile.mkdtemp())
    app = create_app(scenario="small_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        yield c
    mp.undo()


def test_a_key_acts_as_its_login(hosted):
    r = hosted.get("/api/world-model/state", headers={"Authorization": f"Bearer {KEY_A}"})
    assert r.status_code == 200 and r.headers["x-axelrod-api-version"] == "1"
    body = r.json()
    assert body["tenant"] == "sally" and body["caller"] == "zsolt" and body["state"]["scenario"] == "sally_demo"


def test_no_key_a_wrong_key_or_a_key_for_an_unknown_login_is_refused(hosted):
    for headers in ({}, {"Authorization": "Bearer " + "x" * 32}, {"Authorization": f"Bearer {KEY_S}"}):
        r = hosted.get("/api/world-model/state", headers=headers)
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "authentication_required"
        assert r.headers["www-authenticate"] == "Bearer"


def test_a_key_does_not_open_the_ui_or_its_api(hosted):
    r = hosted.get("/api/state", headers={"Authorization": f"Bearer {KEY_A}"})
    assert r.status_code == 401


def test_a_signed_in_browser_may_call_the_service_as_its_login(hosted):
    hosted.post("/login", data={"username": "sally", "password": "pw-sally"}, follow_redirects=False)
    r = hosted.get("/api/world-model/state")
    assert r.status_code == 200 and r.json()["caller"] == "session:sally" and r.json()["tenant"] == "sally"
    hosted.cookies.clear()


def test_a_websocket_to_the_service_without_a_key_is_closed(hosted):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with hosted.websocket_connect("/mcp/ws"):
            pass


def test_a_local_run_without_keys_or_logins_leaves_the_service_open(tmp_path, monkeypatch):
    for var in ("WORLD_MODEL_BASIC_AUTH_USERNAME", "WORLD_MODEL_BASIC_AUTH_PASSWORD", "WORLD_MODEL_LOGINS",
                "WORLD_MODEL_REQUIRE_BASIC_AUTH", "RAILWAY_ENVIRONMENT_ID"):
        monkeypatch.delenv(var, raising=False)
    app = create_app(scenario="small_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        body = c.get("/api/world-model/state").json()
        assert body["caller"] == "local" and body["tenant"] == "default"


def test_a_local_run_with_keys_requires_one_and_serves_the_main_engine(monkeypatch):
    for var in ("WORLD_MODEL_BASIC_AUTH_USERNAME", "WORLD_MODEL_BASIC_AUTH_PASSWORD", "WORLD_MODEL_LOGINS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("WORLD_MODEL_API_KEYS", f"local-tool:{KEY_A}:anything")
    app = create_app(scenario="small_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        assert c.get("/api/world-model/state").status_code == 401
        body = c.get("/api/world-model/state", headers={"Authorization": f"Bearer {KEY_A}"}).json()
        assert body["caller"] == "local-tool" and body["tenant"] == "default"
