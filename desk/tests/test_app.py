"""The web app over HTTP (FastAPI's test client), the reader loop against it, and the command line."""

from __future__ import annotations

import json
import subprocess
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from axelrod_desk import cli, worker
from axelrod_desk.app import COOKIE, create_app
from axelrod_desk.reader import Answer, ClaudeCode, ReaderError
from tests.conftest import REPORT, pdf
from tests.test_reading import obs

FIRST = {"email": "ada@example.com", "password": "a long password", "name": "Ada"}


@pytest.fixture
def client(desk):
    return TestClient(create_app(desk))


@pytest.fixture
def signed(client):
    assert client.get("/api/setup").json() == {"needed": True}
    assert client.post("/api/setup", json=FIRST).json()["admin"] is True
    return client


def test_the_page_and_its_assets(client):
    assert "Export desk" in client.get("/").text and client.get("/app.js").headers["content-type"].startswith("text/javascript")
    assert "--bg" in client.get("/app.css").text


def test_first_admin_sign_in_out_and_accounts(client, desk):
    assert client.get("/api/me").status_code == 401
    client.post("/api/setup", json=FIRST)
    assert client.get("/api/setup").json() == {"needed": False}
    assert client.post("/api/setup", json={**FIRST, "email": "x@example.com"}).status_code == 403
    me = client.get("/api/me").json()
    assert me["name"] == "Ada" and me["reader"] is None
    assert client.post("/api/accounts", json={"email": "k@example.com", "name": "K", "password": "another long one"}).status_code == 201
    assert [a["email"] for a in client.get("/api/accounts").json()] == ["ada@example.com", "k@example.com"]
    assert client.post("/api/accounts", json={"email": "bad", "password": "another long one"}).status_code == 422
    assert client.post("/api/logout").json() == {"ok": True}
    assert client.get("/api/me").status_code == 401
    assert client.post("/api/login", json={"email": "k@example.com", "password": "wrong one!"}).status_code == 401
    assert client.post("/api/login", json={"email": "k@example.com", "password": "another long one"}).json()["admin"] is False
    assert client.get("/api/accounts").status_code == 403 and COOKIE in client.cookies


def test_library_routes(signed, desk):
    files = [("files", ("acme_q3.pdf", pdf(REPORT), "application/pdf")), ("files", ("notes.bin", b"\x00", "x/y")),
             ("files", ("MANIFEST.md", b"# P\n\n## Filings\n\n| File | Publisher |\n|---|---|\n| acme_q3.pdf | Acme Motors |\n",
                        "text/markdown"))]
    res = signed.post("/api/documents", files=files, data={"published": "2026-10-30"}).json()
    assert [a["outcome"] for a in res["added"]] == ["new"] and res["skipped"] == ["notes.bin"] and res["groups"] == 0
    sha = res["added"][0]["sha256"]
    d = signed.get("/api/documents", params={"company": "acme"}).json()[0]
    assert (d["sha256"], d["publisher"], d["published"]) == (sha, "Acme Motors", "2026-10-30")
    assert signed.get(f"/api/documents/{sha}").json()["document"]["status"] == "new"
    assert signed.patch(f"/api/documents/{sha}", json={"note": "seen"}).json()["note"] == "seen"
    assert signed.patch(f"/api/documents/{sha}", json={"company": "ghost"}).status_code == 422
    assert signed.get(f"/api/documents/{sha}/file").content == pdf(REPORT)
    assert signed.get(f"/api/documents/{sha}/pages/2").json()["text"].startswith("Revenue")
    assert signed.get(f"/api/documents/{sha}/pages/9").status_code == 404
    assert signed.get(f"/api/documents/{'0' * 64}/file").status_code == 404
    assert signed.post(f"/api/documents/{sha}/reread").json()["status"] == "new"
    cat = signed.get("/api/catalog").json()
    assert {c["id"] for c in cat["companies"]} >= {"acme", "rival"} and "sector:autos" in cat["groups"]


def test_reader_routes_facts_world_models_and_builds(signed, desk):
    sha = signed.post("/api/documents", files=[("files", ("acme_q3.pdf", pdf(REPORT), "application/pdf"))],
                      data={"source_class": "company", "company": "acme"}).json()["added"][0]["sha256"]
    assert signed.post("/api/reader/claim", json={}).status_code == 401
    token = signed.post("/api/me/reader-token").json()["token"]
    r = TestClient(signed.app)
    r.headers["Authorization"] = f"Bearer {token}"
    assert r.post("/api/reader/claim", json={"reader": "laptop"}).json()["document"]["sha256"] == sha
    assert r.post("/api/reader/claim", json={}).status_code == 204
    assert r.get("/api/me").status_code == 401                                           # a reader token is not a session
    assert r.post("/api/reader/readings/1", json={"observations": [obs()], "themes": []}).json()["accepted"] == 1
    assert r.post("/api/reader/readings/1/fail", json={"error": "x"}).status_code == 422  # not running any more
    assert signed.get("/api/reader/status").json()["documents"] == {"read": 1}
    fact = signed.get("/api/facts", params={"company": "acme"}).json()[0]
    assert signed.post("/api/facts/review", json={"key": fact["key"], "decision": "approve"}).json()["decision"] == "approve"
    assert signed.get("/api/facts", params={"company": "ghost"}).status_code == 404
    w = signed.post("/api/world-models", json={"name": "Acme", "companies": ["acme"], "classes": ["company"]}).json()
    assert signed.put(f"/api/world-models/{w['id']}", json={**w, "apply": True}).json()["apply"] is True
    assert signed.post("/api/world-models", json={"name": "x", "classes": ["company"]}).status_code == 422
    b = signed.post(f"/api/world-models/{w['id']}/builds").json()
    assert signed.get(f"/api/builds/{b['id']}/download").status_code in (200, 422)
    while signed.get(f"/api/builds/{b['id']}").json()["status"] in ("queued", "running"):
        time.sleep(0.05)
    assert signed.get(f"/api/builds/{b['id']}").json()["status"] == "done"
    assert signed.get(f"/api/builds/{b['id']}/download").headers["content-type"] == "application/zip"
    assert signed.get("/api/world-models").json()[0]["builds"][0]["status"] == "done"
    assert signed.get("/api/builds/99").status_code == 404
    assert signed.delete(f"/api/world-models/{w['id']}").status_code == 204


def test_a_failed_build_cannot_be_downloaded(signed, desk):
    desk.builder.run_cmd = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "boom")
    w = signed.post("/api/world-models", json={"name": "Acme", "companies": ["acme"], "classes": ["company"]}).json()
    b = signed.post(f"/api/world-models/{w['id']}/builds").json()
    while signed.get(f"/api/builds/{b['id']}").json()["status"] in ("queued", "running"):
        time.sleep(0.05)
    assert signed.get(f"/api/builds/{b['id']}/download").json()["detail"] == f"build {b['id']} is failed"


# -- the reader loop -----------------------------------------------------------------------------------------------------
class FakeDesk:
    def __init__(self, jobs):
        self.jobs, self.done, self.failed = list(jobs), [], []

    def claim(self, reader):
        return self.jobs.pop(0) if self.jobs else None

    def submit(self, rid, result):
        self.done.append(rid)
        return {"accepted": len(result["observations"]), "rejected": 0, "themes": 0}

    def fail(self, rid, error):
        self.failed.append((rid, error))


def test_the_reader_reads_until_drained_and_reports_failures(monkeypatch):
    from tests.test_reading import JOB

    calls = []

    def claude(prompt, work, schema, resume=None):
        calls.append(1)
        if len(calls) == 2:
            raise ReaderError("rate limited")
        return Answer({"observations": [obs()], "themes": []}, "s", 0, "m")

    claude.binary = "claude"
    desk = FakeDesk([{**JOB, "reading_id": 1}, {**JOB, "reading_id": 2}, None, {**JOB, "reading_id": 3}])
    desk.jobs = [j for j in desk.jobs if j]
    lines, sleeps = [], []
    assert worker.run(desk, claude, drain=True, log=lines.append) == 2
    assert desk.done == [1, 3] and desk.failed == [(2, "rate limited")] and "failed: rate limited" in lines[3]
    idle = FakeDesk([])
    idle.claim = lambda reader, n=[0]: (n.append(1), None)[1] if len(n) < 3 else (_ for _ in ()).throw(KeyboardInterrupt)
    with pytest.raises(KeyboardInterrupt):
        worker.run(idle, claude, sleep=sleeps.append, idle=7, log=lines.append)
    assert sleeps == [7, 7]


def test_the_desk_client_speaks_the_reader_routes():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.headers["authorization"]))
        if request.url.path == "/api/reader/claim":
            return httpx.Response(204) if len(seen) > 1 else httpx.Response(200, json={"reading_id": 4})
        if request.url.path.endswith("/fail"):
            return httpx.Response(422, json={"detail": "not running"})
        return httpx.Response(200, json={"accepted": 1})

    c = worker.DeskClient("http://desk", "tok", client=httpx.Client(base_url="http://desk", transport=httpx.MockTransport(handler)))
    assert c.claim("me") == {"reading_id": 4} and c.claim("me") is None and c.submit(4, {}) == {"accepted": 1}
    with pytest.raises(RuntimeError, match="422"):
        c.fail(4, "x")
    assert seen[0] == ("/api/reader/claim", "Bearer tok")
    assert worker.DeskClient("http://desk/", "t").http.base_url == "http://desk"


def test_checking_claude_code_before_reading(tmp_path):
    ok = ClaudeCode(run=lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, json.dumps(
        {"structured_output": {"ok": True}, "modelUsage": {"claude-x": {}}}), ""))
    assert worker.check_claude(ok) == "claude-x"
    plain = ClaudeCode(run=lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, json.dumps({"structured_output": {}}), ""))
    assert worker.check_claude(plain) == "your default model"
    bad = ClaudeCode(run=lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, json.dumps({"is_error": True,
                                                                                           "result": "Not logged in"}), ""))
    with pytest.raises(ReaderError, match="sign in"):
        worker.check_claude(bad)


# -- the command line ----------------------------------------------------------------------------------------------------
@pytest.fixture
def cli_home(home, monkeypatch):
    monkeypatch.setenv("DESK_HOME", str(home))
    monkeypatch.setattr(cli, "Desk", lambda s: __import__("axelrod_desk.desk", fromlist=["Desk"]).Desk(
        s, poppler=False, run=__import__("tests.conftest", fromlist=["fake_export"]).fake_export))
    return home


def test_cli_accounts_adding_importing_and_building(cli_home, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "a long password")
    assert cli.main(["account", "ada@example.com", "Ada", "--admin"]) == 0
    folder = tmp_path / "pack"
    folder.mkdir()
    (folder / "acme_q3.pdf").write_bytes(pdf(REPORT))
    (folder / "bad.pdf").write_bytes(b"%PDF-1.4 no")
    loose = tmp_path / "memo.txt"
    loose.write_text("Solo Bank memo")
    assert cli.main(["add", str(folder), str(loose), "--as", "ada@example.com", "--company", "acme"]) == 0
    out = capsys.readouterr().out
    assert "new" in out and "failed" in out and "group(s) of copies" in out
    with pytest.raises(SystemExit, match="no account"):
        cli.main(["add", str(loose), "--as", "who@example.com"])
    note = tmp_path / "note.pdf"
    note.write_bytes(pdf(["Rival note", "Revenue for the quarter was JPY 120.5 bn"]))
    records = tmp_path / "broker_records_rival.json"
    o = obs(kind="broker-reported actual", metric_id="rival.revenue", unit="RMB bn")
    records.write_text(json.dumps({"company": "rival", "sources": {
        "ss.x": {"file": str(note), "publisher": "Nomura", "publication_date": "2026-10-31"}},
        "observations": [{**{k: v for k, v in o.items() if k not in ("page", "quote")},
                          "source": {"source_id": "ss.x", "page": 2, "quote": o["quote"]}}],
        "themes": [{"theme": "t", "summary": "s", "sources": [{"source_id": "ss.x", "page": 1, "quote": "Rival note"},
                                                             {"source_id": "ss.z", "page": 1, "quote": "x"}]}]}))
    assert cli.main(["import-records", str(records), "--as", "ada@example.com", "--reader", "agent"]) == 0
    row = json.loads(capsys.readouterr().out)
    assert (row["accepted"], row["rejected"], row["themes"]) == (1, 0, 1)
    assert cli.main(["import-records", str(records), "--as", "ada@example.com", "--reader", "agent"]) == 0
    assert json.loads(capsys.readouterr().out) == {"file": "note.pdf", "skipped": "already read"}
    from axelrod_desk import settings
    from axelrod_desk.desk import Desk

    d = Desk(settings.load(cli_home), poppler=False)
    a = d.db.one("select id from accounts")
    wid = d.save_world_model({"id": a["id"]}, {"name": "Rival", "companies": ["rival"], "classes": ["sell_side"]})["id"]
    d.close()
    assert cli.main(["build", str(wid), "--as", "ada@example.com"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "done"


def test_cli_build_failure_and_serve(cli_home, monkeypatch, capsys):
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "a long password")
    cli.main(["account", "ada@example.com", "Ada"])
    from axelrod_desk import settings
    from axelrod_desk.desk import Desk

    d = Desk(settings.load(cli_home), poppler=False)
    wid = d.save_world_model({"id": 1}, {"name": "Acme", "companies": ["acme"], "classes": ["company"]})["id"]
    d.close()
    monkeypatch.setattr("tests.conftest.fake_export", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "x"))
    assert cli.main(["build", str(wid), "--as", "ada@example.com"]) == 1
    served = {}
    monkeypatch.setattr("uvicorn.run", lambda app, host, port: served.update(host=host, port=port))
    assert cli.main(["serve", "--port", "9999"]) == 0 and served == {"host": "127.0.0.1", "port": 9999}


def test_cli_reader(monkeypatch, capsys):
    monkeypatch.setattr(worker, "check_claude", lambda c: "claude-x")
    monkeypatch.setattr(worker, "run", lambda client, claude, drain, rounds: 3)
    assert cli.main(["reader", "--url", "http://desk", "--token", "t", "--drain", "--model", "m"]) == 0
    assert "3 document(s) read" in capsys.readouterr().out

    def refuse(c):
        raise ReaderError("Claude Code is not installed here")

    monkeypatch.setattr(worker, "check_claude", refuse)
    assert cli.main(["reader", "--url", "http://desk", "--token", "t"]) == 1
    assert "not installed" in capsys.readouterr().err
