"""Read-only tools for an agent that answers inner-loop cases from a task packet (Oct 22).

The agent is a person-like reader (a Claude Code subagent) with a packet and these commands, the way an analyst's agent uses
our export. Every tool is generic: none knows a case. All are read-only, except that a read of the world model is memoized
on disk (so a second agent asking the same question does not boot the world again) and the operations run on clean
temporary worlds when the system can run them.

    calc                a deterministic Decimal calculator (the runner's own), with an optional log the collector reads
    export-list         the files of the export (its `reading/` shards, the domain and evidence packs, the catalogue)
    export-search       a word search over those files, with file, line and the line's text
    export-read         a slice of one file
    model-get           a read of the v1 API: search, an entity, a value, its observations (as_of, available_at), evidence
    model-construction  a company's compositions, identities, values, paths or stock-flows, filtered by a word
    op-ingest-orders    the same dated records ingested in two orders into clean stores (10-04's operation)
    op-update-undo      an update, a recompute and an undo with the audit history (10-06's operation)

A tool reads only inside the export it is handed (a path that leaves it is refused) and never names an answer key. An
operation the system cannot run reports `supported: false` with the reason; it is never simulated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from axelrod_wm.evaluation import inner_loop as il

LIMIT = 20_000                                           # characters returned by one read
READABLE = (".md", ".json", ".txt", ".csv", ".yaml")
ROUTES = re.compile(
    r"^/(search|graph|concepts(/[^/]+)?|groups(/[^/]+)?|versions(/[^/]+)?|evidence/[^/]+|relationships(/[^/]+(/evidence)?)?"
    r"|entities(/[^/]+(/(construction|traces|compositions(/[^/]+)?|paths(/[^/]+)?"
    r"|attributes(/[^/]+(/(observations|states))?)?))?)?)$")
SECTIONS = ("compositions", "identities", "attributes", "paths", "stock_flows", "matrices", "links")


class ToolError(Exception):
    """A tool could not do what it was asked; the message says why."""


def dumps(x: Any) -> str:
    return json.dumps(x, indent=2, sort_keys=True, ensure_ascii=False)


# -- the calculator --------------------------------------------------------------------------------------------------------
def coerce(v: Any) -> Any:
    """A command-line or JSON input as the calculator's value: numbers (printed as '1,234' or '(5)') and ISO dates."""
    if isinstance(v, str):
        if re.fullmatch(il.NUMBER.pattern, v.strip()):
            return il.parse_number(v.strip())
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v.strip()):
            return il.parse_date(v.strip())
        return v
    return il.as_value(v)


def calculate(expression: str, inputs: dict[str, Any]) -> dict:
    env = {k: coerce(v) for k, v in inputs.items()}
    try:
        value = il.evaluate(expression, env)
    except il.Blocked as b:
        raise ToolError(str(b)) from b
    return {"expression": expression, "inputs": il.plain(env), "value": il.plain(value)}


# -- the export ------------------------------------------------------------------------------------------------------------
class Export:
    """A folder the tools may read, through the runner's guard (every read logged with its hash)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.access = il.Access([self.root])

    def files(self) -> list[Path]:
        return sorted(p for p in self.root.rglob("*") if p.is_file() and p.suffix in READABLE)

    def name(self, p: Path) -> str:
        return p.relative_to(self.root).as_posix()

    def resolve(self, name: str) -> Path:
        p = (self.root / name).resolve()
        if not self.access.allowed(p) or not p.is_file():
            raise ToolError(f"{name}: not a file of the export")
        return p

    def listing(self, prefix: str = "") -> list[dict]:
        return [{"file": self.name(p), "bytes": p.stat().st_size} for p in self.files() if self.name(p).startswith(prefix)]

    def read(self, name: str, start: int = 0, length: int = LIMIT) -> dict:
        text = self.access.read_text(self.resolve(name))
        length = min(length, LIMIT)
        return {"file": name, "start": start, "end": min(start + length, len(text)), "total_characters": len(text),
                "text": text[start:start + length]}

    def search(self, query: str, limit: int = 20) -> list[dict]:
        words = [w for w in re.split(r"\s+", query.lower().strip()) if w]
        if not words:
            raise ToolError("an empty query")
        hits = []
        for p in self.files():
            for n, line in enumerate(self.access.read_text(p).splitlines(), 1):
                if all(w in line.lower() for w in words):
                    hits.append({"file": self.name(p), "line": n, "text": line.strip()[:300]})
                    if len(hits) >= limit:
                        return hits
        return hits


# -- the world model -------------------------------------------------------------------------------------------------------
class ModelReads:
    """v1 GETs against the world under test, memoized on disk. `world` is a factory (given the memo folder) of a client with
    `get(path, params=)` (a TestClient in process: no server), called once, lazily, on the first read not in the memo."""

    def __init__(self, cache_dir: Path, world: Callable[[Path], Any]) -> None:
        self.dir, self.world, self.base, self._client = Path(cache_dir), world, "", None

    def key(self, path: str, params: dict) -> Path:
        digest = hashlib.sha256(json.dumps([path, params], sort_keys=True).encode()).hexdigest()
        return self.dir / f"{digest}.json"

    def get(self, path: str, params: dict | None = None) -> dict:
        params = {k: str(v) for k, v in (params or {}).items()}
        if not ROUTES.match(path):
            raise ToolError(f"{path}: not a read route of the world model")
        f = self.key(path, params)
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
        if self._client is None:
            self._client = self.world(self.dir)
            self.base = f"/v1/world-models/{self._client.get('/v1/world-models').json()['data'][0]['id']}"
        r = self._client.get(self.base + path, params=params)
        out = {"path": path, "params": params, "status": r.status_code, "body": r.json()}
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(out, sort_keys=True), encoding="utf-8")
        tmp.replace(f)
        return out

    def construction(self, entity: str, section: str, match: str = "") -> dict:
        if section not in SECTIONS:
            raise ToolError(f"section is one of {', '.join(SECTIONS)}")
        r = self.get(f"/entities/{entity}/construction")
        body = (r["body"].get("data") or {}) if r["status"] == 200 else {}
        rows = body.get(section) or []
        rows = list(rows.values()) if isinstance(rows, dict) else rows
        word = match.lower()
        kept = [x for x in rows if word in json.dumps(x, sort_keys=True).lower()]
        return {"entity": entity, "section": section, "match": match, "matched": len(kept), "of": len(rows), "rows": kept}


# -- the operations --------------------------------------------------------------------------------------------------------
class Operations:
    """Operations on clean temporary worlds. What the system cannot do is reported, not simulated: `can_state_supersession`
    and `can_undo` come from the system's own contract and API description, and `runner` (a callable) performs the
    operation when both exist."""

    def __init__(self, can_state_supersession: bool, can_undo: bool, runner: Callable[[str, dict], dict] | None = None) -> None:
        self.supersession, self.undo, self.runner = can_state_supersession, can_undo, runner

    def _run(self, name: str, ok: bool, why: str, payload: dict) -> dict:
        if not ok:
            return {"operation": name, "supported": False, "reason": why}
        if self.runner is None:
            return {"operation": name, "supported": False, "reason": "the system has the capability but no runner is wired here"}
        return {"operation": name, "supported": True, "result": self.runner(name, payload)}

    def ingest_orders(self, payload: dict) -> dict:
        return self._run("ingest_orders", self.supersession,
                         "the bundle contract has no field to say that one source explicitly corrects and supersedes another, "
                         "so the fixture's records cannot be ingested", payload)

    def update_undo(self, payload: dict) -> dict:
        return self._run("update_undo", self.undo,
                         "the v1 API has no route to undo a committed change; a commit is append-only and a correction is a "
                         "new change set, so an update and its undo cannot be run on the world", payload)


def capabilities(contract_fields: list[str], api_paths: list[str]) -> Operations:
    """Operations whose capabilities are read from the contract's field names and the API's route paths."""
    return Operations(any("supersed" in f for f in contract_fields), any("undo" in p or "revert" in p for p in api_paths))


def openapi_paths(spec: Path) -> list[str]:
    return list((yaml.safe_load(spec.read_text(encoding="utf-8")) or {}).get("paths", {}))


# -- the command line ------------------------------------------------------------------------------------------------------
def log_calc(path: str | None, entry: dict) -> None:
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")


def main(argv: list[str], *, world: Callable[[Path], Any] | None = None, ops: Operations | None = None,
         out: Callable[[str], None] = print) -> int:
    ap = argparse.ArgumentParser(prog="il_tools", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("calc")
    c.add_argument("--expr", required=True)
    c.add_argument("--input", action="append", default=[], help="name=value, repeatable (numbers as printed, ISO dates)")
    c.add_argument("--inputs-json", default="{}")
    c.add_argument("--log", help="append the calculation to this file (the collector reads it)")
    for name in ("export-list", "export-search", "export-read"):
        e = sub.add_parser(name)
        e.add_argument("--export", required=True)
    sub.choices["export-list"].add_argument("--prefix", default="")
    sub.choices["export-search"].add_argument("query")
    sub.choices["export-search"].add_argument("--limit", type=int, default=20)
    sub.choices["export-read"].add_argument("file")
    sub.choices["export-read"].add_argument("--start", type=int, default=0)
    sub.choices["export-read"].add_argument("--length", type=int, default=LIMIT)
    for name in ("model-get", "model-construction"):
        m = sub.add_parser(name)
        m.add_argument("--memo", required=True, help="the shared folder of memoized reads")
    sub.choices["model-get"].add_argument("path")
    sub.choices["model-get"].add_argument("--param", action="append", default=[], help="name=value (as_of, limit, mode, q, ...)")
    sub.choices["model-construction"].add_argument("entity")
    sub.choices["model-construction"].add_argument("section")
    sub.choices["model-construction"].add_argument("--match", default="")
    for name in ("op-ingest-orders", "op-update-undo"):
        sub.add_parser(name).add_argument("--payload", required=True, help="a JSON file describing the operation's inputs")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "calc":
            inputs = {**json.loads(a.inputs_json), **dict(kv.split("=", 1) for kv in a.input)}
            result = calculate(a.expr, inputs)
            log_calc(a.log, result)
        elif a.cmd.startswith("export-"):
            ex = Export(Path(a.export))
            result = {"export-list": lambda: ex.listing(a.prefix), "export-search": lambda: ex.search(a.query, a.limit),
                      "export-read": lambda: ex.read(a.file, a.start, a.length)}[a.cmd]()
        elif a.cmd.startswith("model-"):
            reads = ModelReads(Path(a.memo), world or _no_world)
            if a.cmd == "model-get":
                result = reads.get(a.path, dict(kv.split("=", 1) for kv in a.param))
                result = {**result, "body": _clip(result["body"])}
            else:
                result = reads.construction(a.entity, a.section, a.match)
                result = {**result, "rows": _clip(result["rows"])}
        else:
            payload = json.loads(Path(a.payload).read_text(encoding="utf-8"))
            if ops is None:
                raise ToolError("no operations are wired")
            result = ops.ingest_orders(payload) if a.cmd == "op-ingest-orders" else ops.update_undo(payload)
    except ToolError as e:
        out(dumps({"error": str(e)}))
        return 2
    out(dumps(result))
    return 0


def _no_world(memo: Path) -> Any:
    raise ToolError("the world model is not reachable from here")


def _clip(x: Any) -> Any:
    """A result that fits a reader's window: the JSON text is cut at LIMIT characters, and says so."""
    text = json.dumps(x, sort_keys=True, ensure_ascii=False)
    return x if len(text) <= LIMIT else {"truncated": True, "total_characters": len(text), "text": text[:LIMIT]}
