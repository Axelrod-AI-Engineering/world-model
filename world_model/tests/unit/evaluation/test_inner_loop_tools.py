"""The packet tools on an invented export and a fake world: the calculator, the export reads and their guard, the memoized
model reads and their route whitelist, the operations' honest "unsupported", and the command line. No client data."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from axelrod_ingest.contract.bundle import ImportItem
from axelrod_wm.evaluation import inner_loop_tools as t
from tests.where import INNER_LOOP_EXPORT, WM_ROOT


class Resp:
    def __init__(self, status: int, body: dict) -> None:
        self.status_code, self._b = status, body

    def json(self) -> dict:
        return self._b


class FakeWorld:
    """A client with a world-model list, an entity's construction, and a 404."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def get(self, path: str, params: dict | None = None) -> Resp:
        self.calls.append(path)
        if path == "/v1/world-models":
            return Resp(200, {"data": [{"id": "w1"}]})
        if path == "/v1/world-models/w1/entities/co/construction":
            return Resp(200, {"data": {"compositions": [{"id": "c.one", "view": "regions"}, {"id": "c.two", "view": "product"}],
                                       "identities": {"i": {"id": "id.x"}}, "attributes": []}})
        if path == "/v1/world-models/w1/entities/zz/construction":
            return Resp(404, {"detail": "nope"})
        return Resp(200, {"data": [{"echo": path, "params": params}]})


def run(*argv: str, world=None, ops=None) -> tuple[int, dict]:
    lines: list[str] = []
    code = t.main(list(argv), world=world, ops=ops, out=lines.append)
    return code, json.loads(lines[0])


def test_the_calculator_reads_numbers_as_printed_and_dates() -> None:
    r = t.calculate("a * b - c", {"a": "1,234", "b": 5, "c": "(285)"})
    assert r == {"expression": "a * b - c", "inputs": {"a": 1234, "b": 5, "c": -285}, "value": 6455}
    assert t.calculate("d > e", {"d": "2026-08-04", "e": "2026-07-31"})["value"] is True
    assert t.calculate("x", {"x": "text"})["value"] == "text" and t.calculate("x", {"x": True})["value"] is True
    with pytest.raises(t.ToolError, match="cannot calculate"):
        t.calculate("1 / 0", {})


def test_the_export_is_listed_searched_and_read_through_the_guard() -> None:
    ex = t.Export(INNER_LOOP_EXPORT)
    assert [f["file"] for f in ex.listing()] == ["domain_pack.json", "reading/00_START_HERE.md", "reading/10_company.md"]
    assert [f["file"] for f in ex.listing("reading/")] == ["reading/00_START_HERE.md", "reading/10_company.md"]
    r = ex.read("reading/10_company.md", 2, 10)
    assert r["text"] == "Acme Motor" and r["start"] == 2 and r["end"] == 12 and r["total_characters"] > 50
    hits = ex.search("operating profit")
    assert [(h["file"], h["line"]) for h in hits] == [("domain_pack.json", 1), ("reading/10_company.md", 3)]
    assert len(ex.search("acme", limit=1)) == 1 and ex.search("zzzz") == []
    with pytest.raises(t.ToolError, match="empty"):
        ex.search("  ")
    for bad in ("../where.py", "reading", "nope.md", "/etc/hosts"):
        with pytest.raises(t.ToolError, match="not a file of the export"):
            ex.read(bad)
    assert any(p.endswith("10_company.md") for p in (f["path"] for f in ex.access.report()["files_read"]))


def test_the_export_refuses_a_path_outside_it(tmp_path: Path) -> None:
    (tmp_path / "export").mkdir()
    (tmp_path / "secret.md").write_text("elsewhere")
    ex = t.Export(tmp_path / "export")
    with pytest.raises(t.ToolError):
        ex.read("../secret.md")


def test_model_reads_are_memoized_on_disk_and_only_routes_of_reads_are_allowed(tmp_path: Path) -> None:
    w = FakeWorld()
    reads = t.ModelReads(tmp_path / "memo", lambda memo: w)
    a = reads.get("/entities/co/attributes/units/observations", {"as_of": "2026-07-31", "limit": 5})
    assert a["status"] == 200 and a["body"]["data"][0]["params"] == {"as_of": "2026-07-31", "limit": "5"}
    assert w.calls == ["/v1/world-models", "/v1/world-models/w1/entities/co/attributes/units/observations"]
    again = t.ModelReads(tmp_path / "memo", lambda memo: pytest.fail("the memo should answer"))
    assert again.get("/entities/co/attributes/units/observations", {"limit": 5, "as_of": "2026-07-31"}) == a
    for ok in ("/search", "/graph", "/entities", "/entities/co", "/entities/co/traces", "/entities/co/compositions/c.one",
               "/relationships/r1/evidence", "/evidence/e1", "/versions/latest", "/concepts", "/groups/g1"):
        assert t.ROUTES.match(ok), ok
    for bad in ("/documents", "/changes", "/bundles", "/entities/co/attributes/x/other", "/../x", "/theses"):
        with pytest.raises(t.ToolError, match="not a read route"):
            reads.get(bad)


def test_a_company_construction_is_read_by_section_and_word(tmp_path: Path) -> None:
    reads = t.ModelReads(tmp_path, lambda memo: FakeWorld())
    r = reads.construction("co", "compositions", "REGIONS")
    assert (r["matched"], r["of"], [x["id"] for x in r["rows"]]) == (1, 2, ["c.one"])
    assert reads.construction("co", "identities")["rows"] == [{"id": "id.x"}]
    assert reads.construction("co", "attributes")["of"] == 0
    assert reads.construction("zz", "paths")["of"] == 0
    with pytest.raises(t.ToolError, match="section is one of"):
        reads.construction("co", "everything")


def test_an_operation_the_system_cannot_run_is_reported_not_simulated() -> None:
    ops = t.capabilities(list(ImportItem.model_fields), t.openapi_paths(WM_ROOT / "docs" / "api" / "openapi.yaml"))
    a, b = ops.ingest_orders({}), ops.update_undo({})
    assert a["supported"] is False and "supersedes" in a["reason"]
    assert b["supported"] is False and "undo" in b["reason"]
    both = t.capabilities(["id", "supersedes_id"], ["/a", "/changes/{id}/undo"])
    assert both.ingest_orders({})["reason"].startswith("the system has the capability but no runner")
    done = t.Operations(True, True, lambda name, payload: {"ran": name, **payload})
    assert done.update_undo({"x": 1}) == {"operation": "update_undo", "supported": True, "result": {"ran": "update_undo", "x": 1}}
    assert t.capabilities([], ["/revert"]).undo is True


def test_the_command_line(tmp_path: Path) -> None:
    log = tmp_path / "calc.jsonl"
    code, out = run("calc", "--expr", "a * b", "--input", "a=1,234", "--input", "b=5", "--inputs-json", '{"c": 1}', "--log", str(log))
    assert code == 0 and out["value"] == 6170 and json.loads(log.read_text().splitlines()[0])["value"] == 6170
    run("calc", "--expr", "a", "--input", "a=2", "--log", str(log))
    assert len(log.read_text().splitlines()) == 2
    assert run("calc", "--expr", "1 + 1")[1]["value"] == 2                           # no log: nothing is written
    assert run("calc", "--expr", "1 +")[0] == 2
    e = str(INNER_LOOP_EXPORT)
    assert [f["file"] for f in run("export-list", "--export", e, "--prefix", "reading/")[1]] == [
        "reading/00_START_HERE.md", "reading/10_company.md"]
    assert run("export-search", "--export", e, "units", "--limit", "5")[1][0]["file"] == "domain_pack.json"
    assert run("export-read", "--export", e, "reading/00_START_HERE.md", "--length", "7")[1]["text"] == "# Start"
    assert run("export-read", "--export", e, "../where.py")[0] == 2
    memo = str(tmp_path / "memo")
    code, got = run("model-get", "--memo", memo, "/search", "--param", "q=acme", world=lambda m: FakeWorld())
    assert code == 0 and got["body"]["data"][0]["params"] == {"q": "acme"}
    code, big = run("model-get", "--memo", memo, "/graph", world=lambda m: type("W", (FakeWorld,), {"get": lambda s, p, params=None: Resp(
        200, {"data": "x" * 30000}) if p.endswith("graph") else FakeWorld.get(s, p, params)})())
    assert big["body"]["truncated"] is True and len(big["body"]["text"]) == t.LIMIT
    code, con = run("model-construction", "--memo", memo, "co", "compositions", "--match", "product", world=lambda m: FakeWorld())
    assert con["matched"] == 1
    assert run("model-get", "--memo", memo, "/search")[0] == 2                      # no world reachable from here
    payload = tmp_path / "p.json"
    payload.write_text('{"records": []}')
    assert run("op-ingest-orders", "--payload", str(payload), ops=t.Operations(False, False))[1]["supported"] is False
    assert run("op-update-undo", "--payload", str(payload), ops=t.Operations(False, False))[1]["supported"] is False
    assert run("op-update-undo", "--payload", str(payload))[0] == 2                 # no operations wired
