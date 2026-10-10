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
