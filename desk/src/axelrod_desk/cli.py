"""`axelrod-desk`: serve the desk, run a reader, and the few things done from a terminal (Nov 2).

    axelrod-desk serve [--host 127.0.0.1] [--port 8765]          the web app (DESK_HOME holds desk.toml and the data)
    axelrod-desk reader --url URL --token TOKEN [--drain]         read on this machine's Claude Code (worker.py)
    axelrod-desk account EMAIL NAME [--admin]                     add an account (asks for the password)
    axelrod-desk add PATH... --as EMAIL [--company C] [--class K] add files or folders to the library
    axelrod-desk import-records FILE... --as EMAIL --reader LABEL import figures read before the desk existed
    axelrod-desk build WORLD_MODEL_ID --as EMAIL                  build a world model here, in the foreground

`import-records` takes the records files of the Oct 31 to Nov 2 reads (`q3_records_<company>.json`,
`broker_records_<company>.json`: sources with their files, observations with source page and quote): it adds each source's
file to the library, with the records' company and the class their kinds imply, and hands its figures in as one reading by
`--reader`, which the desk checks like any other.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path
from typing import Any

from axelrod_desk import accounts, settings
from axelrod_desk.db import now
from axelrod_desk.desk import Desk

KEEP = ("metric_id", "label", "period", "value", "unit", "kind", "raw", "previous", "note")


def _account(desk: Desk, email: str) -> dict[str, Any]:
    a = desk.db.one("select * from accounts where email = ?", [email.strip().lower()])
    if a is None:
        raise SystemExit(f"no account {email}")
    return accounts.public(a)


def as_desk_observation(o: dict[str, Any]) -> dict[str, Any]:
    """A records-file observation in the reader's form: its source page and quote on the observation itself."""
    s = o.get("source") or {}
    scope = o.get("scope") or {}
    return {**{k: o[k] for k in KEEP if k in o}, "scope": {"perimeter": scope.get("perimeter", ""), "basis": scope.get("basis", "")},
            "page": s.get("page"), "quote": s.get("quote", "")}


def import_records(desk: Desk, path: Path, account: dict[str, Any], reader: str) -> list[dict[str, Any]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    co = doc["company"]
    out = []
    for sid, src in doc["sources"].items():
        obs = [o for o in doc["observations"] if (o.get("source") or {}).get("source_id") == sid]
        kinds = {o.get("kind", "") for o in obs}
        klass = "sell_side" if any(k.startswith("broker") for k in kinds) else "company"
        f = Path(src["file"])
        added = desk.library.add(f.read_bytes(), f.name, account=account, company=co, source_class=klass,
                                 publisher=src.get("publisher"), published=src.get("publication_date"))
        d = desk.library.get(added.sha256)
        if d["status"] not in ("new", "needs company"):
            out.append({"file": f.name, "skipped": f"already {d['status']}"})
            continue
        desk.library.edit(added.sha256, company=co, source_class=klass)
        desk.db.update("documents", "sha256", added.sha256, {"status": "reading"})
        rid = desk.db.insert("readings", {"sha256": added.sha256, "account_id": account["id"], "reader": reader,
                                          "started_at": now(), "status": "running"})
        themes = [{"theme": t["theme"], "summary": t.get("summary", ""),
                   "citations": [{"page": c.get("page"), "quote": c.get("quote", "")} for c in t.get("sources", [])
                                 if c.get("source_id") == sid]} for t in doc.get("themes", [])]
        res = desk.submit(rid, {"observations": [as_desk_observation(o) for o in obs],
                                "themes": [t for t in themes if t["citations"]], "rounds": 1})
        out.append({"file": f.name, **res})
    desk.library.link()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="axelrod-desk", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("serve")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p = sub.add_parser("reader")
    p.add_argument("--url", required=True)
    p.add_argument("--token", required=True)
    p.add_argument("--claude", default="claude", help="the Claude Code command (default: claude)")
    p.add_argument("--model", help="a Claude model for the reading (default: your Claude Code default)")
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--drain", action="store_true", help="stop when no document is left")
    p = sub.add_parser("account")
    p.add_argument("email")
    p.add_argument("name")
    p.add_argument("--admin", action="store_true")
    p = sub.add_parser("add")
    p.add_argument("paths", nargs="+")
    p.add_argument("--as", dest="email", required=True)
    p.add_argument("--company")
    p.add_argument("--class", dest="source_class")
    p = sub.add_parser("import-records")
    p.add_argument("files", nargs="+")
    p.add_argument("--as", dest="email", required=True)
    p.add_argument("--reader", required=True)
    p = sub.add_parser("build")
    p.add_argument("world_model", type=int)
    p.add_argument("--as", dest="email", required=True)
    args = ap.parse_args(argv)

    if args.cmd == "reader":
        from axelrod_desk.reader import ClaudeCode, ReaderError
        from axelrod_desk.worker import DeskClient, check_claude, run

        claude = ClaudeCode(binary=args.claude, model=args.model)
        try:
            print(f"Claude Code answers here ({check_claude(claude)}); reading for {args.url}")
        except ReaderError as err:
            print(err, file=sys.stderr)
            return 1
        n = run(DeskClient(args.url, args.token), claude, drain=args.drain, rounds=args.rounds)
        print(f"{n} document(s) read")
        return 0

    desk = Desk(settings.load())
    try:
        if args.cmd == "serve":
            import uvicorn

            from axelrod_desk.app import create_app

            uvicorn.run(create_app(desk), host=args.host, port=args.port)
        elif args.cmd == "account":
            a = accounts.create(desk.db, args.email, args.name, getpass.getpass("Password: "), admin=args.admin)
            print(f"account {a['email']} added")
        elif args.cmd == "add":
            a = _account(desk, args.email)
            kw = {"account": a, "company": args.company, "source_class": args.source_class}
            for raw in args.paths:
                path = Path(raw)
                added = desk.library.add_folder(path, **kw) if path.is_dir() else [desk.library.add(path.read_bytes(), path.name, **kw)]
                for x in added:
                    print(f"{x.outcome:15} {x.status:14} {x.filename}{' — ' + x.error if x.error else ''}")
            print(f"{desk.library.link()} group(s) of copies")
        elif args.cmd == "import-records":
            a = _account(desk, args.email)
            for f in args.files:
                for row in import_records(desk, Path(f), a, args.reader):
                    print(json.dumps(row, ensure_ascii=False))
        else:
            a = _account(desk, args.email)
            desk.world_model(args.world_model, a)
            bid = desk.db.insert("builds", {"world_model_id": args.world_model, "account_id": a["id"], "status": "queued",
                                            "started_at": now()})
            b = desk.run_build(bid)
            print(json.dumps({k: b[k] for k in ("id", "status", "zip", "error")}, indent=1))
            return 0 if b["status"] == "done" else 1
    finally:
        desk.close()
    return 0


__all__ = ["as_desk_observation", "import_records", "main"]
