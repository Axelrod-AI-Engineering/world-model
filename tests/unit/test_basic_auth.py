import base64

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from axelrod_wm.api.auth import BasicAuthMiddleware


def header(username="manav", password="test-password"):
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("WORLD_MODEL_REQUIRE_BASIC_AUTH", "1")
    monkeypatch.setenv("WORLD_MODEL_BASIC_AUTH_USERNAME", "manav")
    monkeypatch.setenv("WORLD_MODEL_BASIC_AUTH_PASSWORD", "test-password")

    async def page(request):
        return PlainTextResponse("protected")

    async def stream(ws):
        await ws.accept()
        await ws.send_text("protected")
        await ws.close()

    app = Starlette(routes=[Route("/{path:path}", page, methods=["GET", "POST"]),
                            WebSocketRoute("/ws", stream)])
    app.add_middleware(BasicAuthMiddleware)
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("path", ["/", "/js/main.js", "/api/state", "/docs", "/openapi.json"])
def test_all_content_requires_auth(client, path):
    response = client.get(path)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"].startswith("Basic ")
    assert client.get(path, headers=header()).status_code == 200


@pytest.mark.parametrize("authorization", ["Basic bad", "Bearer token", "Basic ////", "Basic Og=="])
def test_malformed_credentials_fail_closed(client, authorization):
    assert client.get("/", headers={"Authorization": authorization}).status_code == 401


def test_wrong_credentials_and_mutations(client):
    assert client.get("/", headers=header(password="wrong")).status_code == 401
    assert client.get("/", headers=header(username="wrong")).status_code == 401
    assert client.post("/api/sim/play").status_code == 401
    assert client.post("/api/health").status_code == 401
    assert client.get("/api/health").status_code == 200


def test_websocket_requires_same_credentials(client):
    with pytest.raises(WebSocketDisconnect) as error, client.websocket_connect("/ws"):
        pass
    assert error.value.code == 1008
    with client.websocket_connect("/ws", headers=header()) as ws:
        assert ws.receive_text() == "protected"


def test_required_auth_rejects_missing_credentials(monkeypatch):
    monkeypatch.setenv("WORLD_MODEL_REQUIRE_BASIC_AUTH", "1")
    monkeypatch.delenv("WORLD_MODEL_BASIC_AUTH_USERNAME", raising=False)
    monkeypatch.delenv("WORLD_MODEL_BASIC_AUTH_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="both username and password"):
        BasicAuthMiddleware(None)


def test_railway_requires_auth_even_without_explicit_flag(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "dev-environment")
    for name in ("WORLD_MODEL_REQUIRE_BASIC_AUTH", "WORLD_MODEL_BASIC_AUTH_USERNAME",
                 "WORLD_MODEL_BASIC_AUTH_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="both username and password"):
        BasicAuthMiddleware(None)


def test_local_demo_without_credentials_remains_available(monkeypatch):
    for name in ("RAILWAY_ENVIRONMENT_ID", "WORLD_MODEL_REQUIRE_BASIC_AUTH",
                 "WORLD_MODEL_BASIC_AUTH_USERNAME", "WORLD_MODEL_BASIC_AUTH_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    middleware = BasicAuthMiddleware(None)
    assert not middleware.username


# -- logins that open their own scenario (WORLD_MODEL_LOGINS) -------------------------------------------------------
@pytest.fixture
def logins_client(monkeypatch):
    monkeypatch.setenv("WORLD_MODEL_REQUIRE_BASIC_AUTH", "1")
    monkeypatch.setenv("WORLD_MODEL_BASIC_AUTH_USERNAME", "manav")
    monkeypatch.setenv("WORLD_MODEL_BASIC_AUTH_PASSWORD", "test-password")
    monkeypatch.setenv("WORLD_MODEL_LOGINS", "emily:other-password:emily_demo")

    async def page(request):
        return PlainTextResponse(str(request.scope.get("axelrod_login")))

    app = Starlette(routes=[Route("/{path:path}", page)])
    app.add_middleware(BasicAuthMiddleware)
    with TestClient(app) as c:
        yield c


def test_each_login_is_named_in_the_scope(logins_client):
    assert logins_client.get("/", headers=header()).text == "manav"
    assert logins_client.get("/", headers=header("emily", "other-password")).text == "emily"
    # one login's password does not open another
    assert logins_client.get("/", headers=header("emily", "test-password")).status_code == 401
    assert logins_client.get("/", headers=header("manav", "other-password")).status_code == 401


@pytest.mark.parametrize("raw", ["emily:pw", "emily::emily_demo", ":pw:emily_demo"])
def test_malformed_logins_fail_closed(monkeypatch, raw):
    monkeypatch.setenv("WORLD_MODEL_BASIC_AUTH_USERNAME", "manav")
    monkeypatch.setenv("WORLD_MODEL_BASIC_AUTH_PASSWORD", "test-password")
    monkeypatch.setenv("WORLD_MODEL_LOGINS", raw)
    with pytest.raises(RuntimeError):
        BasicAuthMiddleware(lambda *a: None)


def test_each_login_serves_its_own_scenario(monkeypatch, tmp_path):
    from axelrod_wm.api.app import create_app
    from axelrod_wm.repo.snapshots import MemoryBackend

    monkeypatch.chdir(tmp_path)          # the extra login's storage goes under var/
    monkeypatch.setenv("WORLD_MODEL_BASIC_AUTH_USERNAME", "manav")
    monkeypatch.setenv("WORLD_MODEL_BASIC_AUTH_PASSWORD", "test-password")
    monkeypatch.setenv("WORLD_MODEL_LOGINS", "emily:other-password:emily_demo")
    app = create_app(scenario="small_demo", storage=MemoryBackend(), trace_dir=None)
    with TestClient(app) as c:
        assert c.get("/api/sim/status", headers=header()).json()["scenario_id"] == "small_demo"
        assert c.get("/api/sim/status", headers=header("emily", "other-password")).json()["scenario_id"] == "emily_demo"
