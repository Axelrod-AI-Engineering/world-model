"""Settings, the database, accounts, page text and the catalog."""

from __future__ import annotations

import subprocess

import pytest

from axelrod_desk import accounts, pages, settings
from axelrod_desk.catalog import Catalog
from axelrod_desk.db import Db
from tests.conftest import WORLD_VIEW, pdf, write_home


def test_settings_read_the_toml_beside_the_home(home):
    s = settings.load(home)
    assert s.repo == home / "repo" and s.client_core == home / "data" / "core" and s.remaps == ("old/=new/",)
    assert (s.db, s.files, s.text, s.lake, s.builds, s.scenarios) == (
        home / "desk.sqlite3", home / "files", home / "text", home / "lake", home / "builds", home / "clients")
    assert s.groups == {"mine": ["acme", "solo"]} and s.python[0] == "uv" and s.tenant == "desk"


def test_settings_without_a_client_core_and_the_home_from_the_environment(tmp_path, monkeypatch):
    home = write_home(tmp_path / "h", client_core=False)
    monkeypatch.setenv(settings.HOME_ENV, str(home))
    assert settings.home_of() == home.resolve() and settings.load().client_core is None
    assert settings.home_of({}).name == "desk"


def test_the_database_keeps_json_columns_as_json(tmp_path):
    db = Db(tmp_path / "x" / "d.sqlite3")
    rid = db.insert("world_models", {"account_id": 1, "name": "w", "companies": ["a"], "groups": [], "classes": ["company"],
                                     "apply": 0, "created_at": "t"})
    assert db.one("select * from world_models where id = ?", [rid])["companies"] == ["a"]
    db.update("world_models", "id", rid, {"name": "v"})
    assert db.all("select name from world_models") == [{"name": "v"}] and db.one("select 1 x where 0") is None
    db.close()


def test_accounts_passwords_sessions_and_reader_tokens(tmp_path):
    db = Db(tmp_path / "d.sqlite3")
    a = accounts.create(db, " Ada@Example.com ", "", "a long password", admin=True)
    assert a == {"id": a["id"], "email": "ada@example.com", "name": "ada@example.com", "admin": True}
    for email, pw, why in (("nobody", "a long password", "email"), ("x@y.z", "short", "8 characters"),
                           ("ada@example.com", "a long password", "already")):
        with pytest.raises(ValueError, match=why):
            accounts.create(db, email, "n", pw)
    assert accounts.sign_in(db, "ada@example.com", "a long password") == a
    assert accounts.sign_in(db, "ada@example.com", "wrong password") is None
    assert accounts.sign_in(db, "who@example.com", "a long password") is None
    web = accounts.issue(db, a["id"])
    assert accounts.resolve(db, web, "web") == a and accounts.resolve(db, web, "reader") is None
    assert db.one("select token from sessions")["token"] != web                       # only its hash is kept
    first = accounts.issue(db, a["id"], "reader")
    second = accounts.issue(db, a["id"], "reader")
    assert accounts.resolve(db, first, "reader") is None and accounts.resolve(db, second, "reader") == a
    assert accounts.has_reader(db, a["id"])["last_used"]
    accounts.revoke(db, web)
    assert accounts.resolve(db, web, "web") is None
    with pytest.raises(ValueError):
        accounts.issue(db, a["id"], "root")


def test_pages_from_the_parser_and_from_poppler(monkeypatch):
    texts, engine = pages.page_texts(pdf(["one", "two"]), "r.pdf", poppler=False)
    assert texts == ["one", "two"] and engine.startswith("axelrod-parse/")
    assert pages.page_texts(b"just text", "n.txt")[0] == ["just text"]
    calls = []

    def run(cmd, **kw):
        calls.append(cmd[0])
        out = "Title: x\nPages:          2\n" if cmd[0] == "pdfinfo" else f"page {cmd[cmd.index('-f') + 1]}\n"
        return subprocess.CompletedProcess(cmd, 0, out, "")

    monkeypatch.setattr(pages.subprocess, "run", run)
    monkeypatch.setattr(pages.shutil, "which", lambda name: f"/bin/{name}")
    assert pages.has_poppler()
    assert pages.page_texts(b"%PDF", "r.PDF") == (["page 1\n", "page 2\n"], pages.POPPLER)
    assert calls == ["pdfinfo", "pdftotext", "pdftotext"]


def test_page_files_norm_and_the_marked_document(tmp_path):
    pages.write(tmp_path / "p", ["a  b", "c"])
    assert pages.read(tmp_path / "p", 2) == ["a  b", "c"]
    assert pages.norm("  A \n B ") == "a b"
    assert pages.as_document(["x\n", "y"]) == "=== PAGE 1 ===\nx\n\n=== PAGE 2 ===\ny\n"


def test_the_catalog_companies_metrics_groups_and_detection(home):
    cat = Catalog(WORLD_VIEW, scenario_dirs=[home / "data" / "clients" / "scenarios"], groups={"mine": ["acme", "ghost"]})
    assert [c["id"] for c in cat.company_list()] == ["acme", "plain", "rival", "solo"]
    assert cat.related("acme") == ["boj"] and cat.related("rival") == []
    assert [m["metric_id"] for m in cat.metrics("acme")] == ["acme.revenue", "acme.units", "boj.rate", "usd_jpy.rate"]
    assert cat.unit_of("acme.revenue") == "JPY bn per quarter" and cat.unit_of("nothing") == ""
    assert cat.groups == {"sector:autos": {"name": "Sector: autos", "companies": ["acme", "rival"]},
                          "sector:banks": {"name": "Sector: banks", "companies": ["solo"]},
                          "focus:focus_autos": {"name": "Focus: autos", "companies": ["acme", "rival"]},
                          "group:mine": {"name": "mine", "companies": ["acme"]}}
    assert cat.expand(["solo"], ["sector:autos"]) == ["acme", "rival", "solo"]
    with pytest.raises(ValueError, match="ghost, nope"):
        cat.expand(["nope"], ["ghost"])
    assert cat.detect("20261029 - Broker - 7203_JP - Acme - 4 pages.pdf", "Acme Motors grew") == "acme"
    assert cat.detect("report.pdf", "Acme and Rival", "Acme, Rival") is None              # neither leads
    assert cat.detect("report.pdf", "nothing here") is None
    assert Catalog.load(home / "data" / "world_view.json").companies.keys() == cat.companies.keys()
