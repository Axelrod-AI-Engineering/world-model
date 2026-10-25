"""The data service and its client (Oct 24): every route through `RemoteLake` against the app in process, bearer auth with
RFC 9457 problems, the store's exceptions mapped to 404 and 422 and raised again as the same types, binary files and
float32 vectors round-tripped exactly, `nearest` equal to the local result, reads retried and writes not, and the
environment choosing between the local lake and the service. The store's own behaviours run through `RemoteLake` in the
lake suite (tests/lake/conftest.py parametrizes the `lake` fixture)."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

import axelrod_ingest.lake.sqlite as sqlite_module
from axelrod_ingest.lake import server
from axelrod_ingest.lake.embed import HashingEmbedder
from axelrod_ingest.lake.remote import RemoteLake, RemoteLakeError, is_absent, lake_from_env, raise_for
from axelrod_ingest.lake.server import create_lake_app
from axelrod_ingest.lake.sqlite import SQLiteLake
from tests.lake.conftest import T0, TOKEN, add_doc, make_doc, remote_of

AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def backing(tmp_path):
    store = SQLiteLake(tmp_path / "lk")
    yield store
    store.close()


@pytest.fixture
def raw(backing):
    """The service's own HTTP surface, for what the client never sends."""
    return TestClient(create_lake_app(backing, TOKEN))


def test_every_route_but_health_needs_the_token(raw):
    assert raw.get("/health").json() == {"ok": True, "service": "data"}
    for headers in ({}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic " + TOKEN}):
        r = raw.get("/v1/lake/stats", params={"tenant": "acme"}, headers=headers)
        body = r.json()
        assert r.status_code == 401 and r.headers["content-type"].startswith("application/problem+json")
        assert body["code"] == "authentication_required" and body["status"] == 401
        assert body["type"].endswith("/authentication_required")
        assert body["instance"] == "/v1/lake/stats" and r.headers["www-authenticate"] == "Bearer"
    assert raw.get("/v1/lake/stats", params={"tenant": "acme"}, headers=AUTH).json()["documents"] == 0


def test_a_lake_needs_a_token(backing):
    with pytest.raises(ValueError, match="token"):
        create_lake_app(backing, "")


def test_a_wrong_token_through_the_client_is_an_error(backing):
    bad = RemoteLake("http://lake", "nope", TestClient(create_lake_app(backing, TOKEN)))
    with pytest.raises(RemoteLakeError, match="401"):
        bad.stats("acme")


def test_errors_map_to_problems_and_back_to_the_same_exceptions(backing, raw):
    lake = remote_of(backing)
    with pytest.raises(KeyError, match="nope"):
        lake.update_document("acme", "nope", title="x")
    with pytest.raises(ValueError, match="order must be"):
        lake.list_documents("acme", order="bogus")
    r = raw.patch("/v1/lake/documents/nope", params={"tenant": "acme"}, json={"fields": {}}, headers=AUTH)
    assert r.status_code == 404 and r.json()["code"] == "not_found"
    r = raw.get("/v1/lake/documents", params={"tenant": "acme", "order": "x"}, headers=AUTH)
    assert r.status_code == 422 and r.json()["code"] == "invalid_request"
    r = raw.get("/v1/lake/documents", headers=AUTH)          # a missing query argument
    assert r.status_code == 422 and "tenant" in r.json()["detail"]
    assert raw.get("/v1/lake/nowhere", headers=AUTH).json()["code"] == "not_found"
    assert raw.post("/v1/lake/documents", data={"document": "{}"}, files={"data": ("a", b"x")},
                    headers=AUTH).status_code == 422


def test_a_lookup_that_finds_nothing_is_none_not_an_error(backing, raw):
    lake = remote_of(backing)
    assert lake.get_document("acme", "x") is None and lake.raw_bytes("acme", "x") is None
    assert lake.get_text("acme", "x") is None and lake.get_bundle("acme", "x") is None
    assert lake.get_idempotency("o", "w", "op", "k") is None and lake.get_job("o", "w", "j") is None
    assert raw.get("/v1/lake/documents/x", params={"tenant": "acme"}, headers=AUTH).json()["code"] == "absent"


def test_files_and_vectors_round_trip_exactly(backing):
    lake = remote_of(backing)
    data = bytes(range(256)) * 4096                      # a binary body, not text
    doc, new = lake.put_document(make_doc(data, filename="blob.bin"), data)
    assert new and lake.raw_bytes("acme", doc.id) == data and lake.put_document(doc, data) == (doc, False)
    vectors = [[0.1, 0.123457, -0.5], [1 / 3, 2 / 3, 1e-7]]
    lake.put_embeddings("acme", doc.id, "m", vectors)
    assert lake.embeddings("acme", "m") == backing.embeddings("acme", "m")
    lake.put_embeddings("acme", doc.id, "m", [])
    assert lake.embeddings("acme", "m") == []


def test_embeddings_of_a_bad_shape_are_refused(raw):
    r = raw.put("/v1/lake/documents/d/embeddings", params={"tenant": "a", "model": "m", "dim": 3}, content=bytes(16),
                headers=AUTH)
    assert r.status_code == 422
    r = raw.put("/v1/lake/documents/d/embeddings", params={"tenant": "a", "model": "m", "dim": 0}, content=b"",
                headers=AUTH)
    assert r.status_code == 422


def test_nearest_equals_the_local_result(backing):
    lake = remote_of(backing)
    texts = ["oil prices rose", "the dollar fell", "rates held steady", "oil supply fell"]
    doc = add_doc(backing, b"v", texts)
    emb = HashingEmbedder()
    backing.put_embeddings("acme", doc.id, emb.name, emb.embed(texts))
    q = emb.embed(["oil"])[0]
    got = lake.nearest("acme", emb.name, q, 3)
    assert got == backing.nearest("acme", emb.name, q, 3) and len(got) == 3
    assert lake.nearest("acme", "other", q) == []


def test_document_updates_carry_datetimes_and_nested_meta(backing):
    lake = remote_of(backing)
    doc, _ = lake.put_document(make_doc(b"u"), b"u")
    new = lake.update_document("acme", doc.id, title="T", published_at=T0, event_time=T0, meta={"a": {"b": [1, 2.5]}})
    assert new.published_at == T0 and new.meta == {"a": {"b": [1, 2.5]}}
    assert new == backing.get_document("acme", doc.id)
    assert lake.update_document("acme", doc.id, status="parsed").status == "parsed"


def test_listing_filters_by_time_and_the_other_reads(backing):
    lake = remote_of(backing)
    doc = add_doc(backing, b"l", ["alpha beta", "gamma"])
    assert [d.id for d in lake.list_documents("acme", since=T0, until=T0.replace(year=2030))] == [doc.id]
    assert lake.list_documents("acme", until=T0) == []
    assert lake.get_chunks("acme", doc.id) == backing.get_chunks("acme", doc.id)
    hits = lake.keyword_search("acme", "alpha", prefix=True)
    assert hits == backing.keyword_search("acme", "alpha", prefix=True) and hits
    assert lake.stats("acme") == backing.stats("acme")
    assert lake.get_text("acme", doc.id) == ("alpha beta\ngamma", "plain")
    assert lake.delete_document("acme", doc.id) is True and lake.delete_document("acme", doc.id) is False


def test_the_cache_and_jobs_hold_json_values(backing):
    lake = remote_of(backing)
    assert lake.cache_get("k") is None
    lake.cache_put("k", "p", "m", {"x": [1, {"y": 2.5}]})
    assert lake.cache_get("k") == {"x": [1, {"y": 2.5}]} == backing.cache_get("k")
    lake.put_job("o", "w", {"id": "j1", "status": "ok"})
    assert lake.get_job("o", "w", "j1") == {"id": "j1", "status": "ok"}


def flaky(backing, fail: list, calls: list):
    """A client whose transport fails as `fail` says (an exception, or a status), then answers as the service."""
    app = TestClient(create_lake_app(backing, TOKEN))

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        if fail:
            f = fail.pop(0)
            if isinstance(f, Exception):
                raise f
            return httpx.Response(f, text="down")
        r = app.request(request.method, str(request.url), headers=dict(request.headers), content=request.content)
        return httpx.Response(r.status_code, headers=dict(r.headers), content=r.content)

    return RemoteLake("http://testserver", TOKEN, httpx.Client(transport=httpx.MockTransport(handler)),
                      sleep=lambda _s: None)


def test_reads_are_retried_on_connection_errors_and_5xx(backing):
    calls: list = []
    lake = flaky(backing, [httpx.ConnectError("x"), 503], calls)
    assert lake.stats("acme")["documents"] == 0 and len(calls) == 3


def test_a_read_gives_up_after_three_tries(backing):
    calls: list = []
    lake = flaky(backing, [500, httpx.ReadTimeout("x"), 502], calls)
    with pytest.raises(RemoteLakeError, match="502"):
        lake.stats("acme")
    assert len(calls) == 3
    lake = flaky(backing, [httpx.ConnectError("x")] * 3, calls)
    with pytest.raises(RemoteLakeError, match="ConnectError"):
        lake.stats("acme")


def test_a_write_is_sent_once(backing):
    calls: list = []
    lake = flaky(backing, [httpx.ConnectError("x")], calls)
    with pytest.raises(RemoteLakeError):
        lake.put_text("acme", "d", "t", "p")
    assert len(calls) == 1
    lake.put_text("acme", "d", "t", "p")          # the next call goes through


def test_ping_reports_whether_the_service_answers(backing):
    assert remote_of(backing).ping() is True

    def refuse(request):
        raise httpx.ConnectError("x")

    down = RemoteLake("http://lake", TOKEN, httpx.Client(transport=httpx.MockTransport(refuse)))
    assert down.ping() is False


def test_problem_answers_that_are_not_json_are_still_errors():
    assert not is_absent(httpx.Response(404, text="<html>"))
    assert not is_absent(httpx.Response(404, json=[1]))
    assert not is_absent(httpx.Response(200))
    with pytest.raises(RemoteLakeError, match="gateway"):
        raise_for(httpx.Response(502, text="bad gateway"))
    with pytest.raises(RemoteLakeError):
        raise_for(httpx.Response(500, json=[1]))
    with pytest.raises(KeyError):
        raise_for(httpx.Response(404, json={"detail": "x", "code": "not_found"}))


def test_the_environment_chooses_the_lake(tmp_path):
    local = lake_from_env({"WORLD_MODEL_LAKE_DIR": str(tmp_path / "here")})
    assert isinstance(local, SQLiteLake) and local.root == tmp_path / "here"
    local.close()
    remote = lake_from_env({"WORLD_MODEL_LAKE_URL": "http://data/", "WORLD_MODEL_LAKE_TOKEN": "t"})
    assert isinstance(remote, RemoteLake) and remote.url == "http://data"
    remote.close()
    with pytest.raises(ValueError, match="WORLD_MODEL_LAKE_TOKEN"):
        lake_from_env({"WORLD_MODEL_LAKE_URL": "http://data"})


def test_remote_mode_opens_no_local_lake(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    remote = lake_from_env({"WORLD_MODEL_LAKE_URL": "http://data", "WORLD_MODEL_LAKE_TOKEN": "t",
                            "WORLD_MODEL_LAKE_DIR": str(tmp_path / "never")})
    remote.close()
    assert list(tmp_path.iterdir()) == []


def test_main_serves_the_lake_in_lake_dir_and_refuses_to_run_open(tmp_path, monkeypatch):
    import uvicorn

    monkeypatch.delenv("LAKE_TOKEN", raising=False)
    with pytest.raises(SystemExit, match="LAKE_TOKEN"):
        server.main()
    served = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, host, port: served.update(app=app, host=host, port=port))
    monkeypatch.setenv("LAKE_TOKEN", TOKEN)
    monkeypatch.setenv("LAKE_DIR", str(tmp_path / "vol"))
    monkeypatch.setenv("PORT", "9123")
    server.main()
    assert served["port"] == 9123 and served["host"] == "" and (tmp_path / "vol" / "lake.sqlite3").exists()
    assert TestClient(served["app"]).get("/health").status_code == 200
    # the defaults are /data/lake and 8000 (the lake class is swapped for a recorder so no such folder is made)
    monkeypatch.delenv("LAKE_DIR")
    monkeypatch.delenv("PORT")
    seen = []
    monkeypatch.setattr(sqlite_module, "SQLiteLake", lambda root: seen.append(root) or SQLiteLake(tmp_path / "dflt"))
    server.main()
    assert seen == ["/data/lake"] and served["port"] == 8000
