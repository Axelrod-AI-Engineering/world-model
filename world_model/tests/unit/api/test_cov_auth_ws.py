"""Sign-in edge cases (api/auth.py) and the /ws stream (api/ws.py): replay without duplicates, a session without a
loaded demo, a client that never says hello, and pings."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from axelrod_wm.api import ws
from axelrod_wm.api.app import create_app
from axelrod_wm.api.auth import BasicAuthMiddleware
from axelrod_wm.repo.snapshots import MemoryBackend


def _clear_auth_env(monkeypatch):
    for k in ("WORLD_MODEL_REQUIRE_BASIC_AUTH", "RAILWAY_ENVIRONMENT_ID", "WORLD_MODEL_BASIC_AUTH_USERNAME",
              "WORLD_MODEL_BASIC_AUTH_PASSWORD", "WORLD_MODEL_LOGINS", "WORLD_MODEL_SESSION_SECRET"):
        monkeypatch.delenv(k, raising=False)


def test_extra_logins_need_the_main_login(monkeypatch):
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("WORLD_MODEL_LOGINS", "eve:pw:acme_demo")
    with pytest.raises(RuntimeError, match="needs the main Basic Auth login"):
        BasicAuthMiddleware(None)


def test_a_login_form_sent_in_pieces(monkeypatch):
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("WORLD_MODEL_BASIC_AUTH_USERNAME", "manav")
    monkeypatch.setenv("WORLD_MODEL_BASIC_AUTH_PASSWORD", "test-password")
    mw = BasicAuthMiddleware(None)
    chunks = [b"username=manav&", b"password=test-password&", b"next=/api/state"]
    messages = [{"type": "http.request", "body": c, "more_body": k < len(chunks) - 1} for k, c in enumerate(chunks)]
    sent = []

    async def receive():
        return messages.pop(0)

    async def send(msg):
        sent.append(msg)

    scope = {"type": "http", "method": "POST", "path": "/login", "query_string": b"", "headers": [], "scheme": "http"}
    asyncio.run(mw.login(scope, receive, send))
    start = sent[0]
    headers = dict(start["headers"])
    assert start["status"] == 303 and headers[b"location"] == b"/api/state" and b"axelrod_session" in headers[b"set-cookie"]
    assert messages == []                       # every piece of the form was read


# -- the stream -------------------------------------------------------------------------------------------------
class FakeSocket:
    def __init__(self):
        self.sent = []

    async def send_text(self, text):
        self.sent.append(json.loads(text))


def test_a_trace_event_is_sent_once():
    async def go():
        s = ws._Session(FakeSocket(), SimpleNamespace(runner=None))
        await s.send_trace({"seq": 3})
        await s.send_trace({"seq": 3})            # already sent during a replay
        await s.send_trace({"seq": 2})
        assert s.ws.sent == [{"type": "trace", "event": {"seq": 3}}]

    asyncio.run(go())


def test_replay_without_a_loaded_demo_sends_no_status():
    async def go():
        tracer = SimpleNamespace(since=lambda seq: [])
        for runner in (None, SimpleNamespace(loaded=False)):
            s = ws._Session(FakeSocket(), SimpleNamespace(runner=runner, tracer=tracer))
            assert s.status() is None
            await s.replay(0)
            assert s.ws.sent == []

    asyncio.run(go())


@pytest.fixture(scope="module")
def client():
    app = create_app(scenario="small_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        yield c


def _until(sock, kind):
    for _ in range(10_000):
        msg = sock.receive_json()
        if msg.get("type") == kind:
            return msg
    raise AssertionError(f"no {kind}")


def test_hello_again_and_ping(client):
    with client.websocket_connect("/ws") as sock:
        sock.send_json({"type": "hello", "since_seq": 10**9})
        assert _until(sock, "status")["status"]["scenario_id"] == "small_demo"
        sock.send_json({"type": "ping"})
        assert _until(sock, "pong") == {"type": "pong"}
        sock.send_json({"type": "hello", "since_seq": 10**9})       # a second hello replays and resends the status
        assert _until(sock, "status")["status"]["loaded"] is True
        sock.send_json(["not", "a", "message"])                     # ignored
        sock.send_json({"type": "ping"})
        assert _until(sock, "pong") == {"type": "pong"}


def test_a_client_that_starts_with_something_else_streams_from_now(client):
    with client.websocket_connect("/ws") as sock:
        sock.send_json({"type": "ping"})
        msg = sock.receive_json()
        assert msg["type"] == "status"                # no replay of earlier trace events


def test_a_client_that_never_says_hello(client, monkeypatch):
    monkeypatch.setattr(ws, "HELLO_TIMEOUT_S", 0.05)
    with client.websocket_connect("/ws") as sock:
        assert sock.receive_json()["type"] == "status"


def test_a_login_whose_scenario_is_missing_opens_the_main_engine(monkeypatch, caplog, tmp_path):
    from axelrod_wm.api.app import create_app

    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("WORLD_MODEL_BASIC_AUTH_USERNAME", "main")
    monkeypatch.setenv("WORLD_MODEL_BASIC_AUTH_PASSWORD", "test-password")
    monkeypatch.setenv("WORLD_MODEL_LOGINS", "eve:other-password:acme_demo,zed:third-password:not_on_this_machine")
    with caplog.at_level("WARNING", logger="axelrod_wm.api.app"):
        app = create_app(storage=MemoryBackend(), load_on_startup=False, trace_dir=None, cache_dir=tmp_path)
    assert set(app.state.axelrod_by_login) == {"eve"}
    assert "zed: scenario not_on_this_machine not found" in caplog.text
