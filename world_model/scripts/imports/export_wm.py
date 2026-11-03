"""Write a world model as an evaluation export (`axelrod.wm-export/v1`, context/wm_export.py), for core's Mission Control
World Model quality tab (Oct 31).

    snapshot  load a scenario as export_context.py does (optionally folding a folder of day bundles, every item approved),
              attach the construction sources and repair data, hash the cited documents, and write one export:

        uv run python world_model/scripts/imports/export_wm.py snapshot sally_focus data/exports/sally/wm-export.json \\
            --days data/work/sally/days --construction-sources data/work/sally/construction \\
            --remap data/sally_data/=data/sources/sally/ --world-model-id toyota --label Toyota --subject Toyota

    series    run the update-mechanics series (context/wm_export_series.py) on a scenario with two bundles, writing one
              export per step into a folder:

        WORLD_MODEL_CLIENT_DIR=world_model/tests/fixtures/clients uv run python world_model/scripts/imports/export_wm.py \\
            series acme_demo first.json second.json data/exports/acme-series --world-model-id acme --label Acme

Document hashes are sha256 of the files the sources and repair observations name; `--remap OLD=NEW` rewrites a path
prefix first (sources.json still names the old data/sally_data/ layout). Client material stays local: write the export
to a gitignored folder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.clients import find_scenario, load_scenario_yaml
from axelrod_wm.context.construction import load_sources
from axelrod_wm.context.earnings import load_repair
from axelrod_wm.context.wm_export import wm_export
from axelrod_wm.context.wm_export_series import update_series
from axelrod_wm.engine.focus import focus_result
from axelrod_wm.repo.history import log
from axelrod_wm.repo.snapshots import MemoryBackend
from axelrod_wm.sim.imports import ImportRunner
from axelrod_wm.sim.scenario import ScenarioScript


def now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def document_hashes(sources: dict, repairs: list[dict], remap: list[tuple[str, str]]) -> dict[str, str]:
    """sha256 of every document a source or a repair observation names, keyed by the path as written."""
    paths: set[str] = set()
    for s in sources["catalogue"].values():
        d = s.get("document")
        paths |= {d} if isinstance(d, str) else {x for x in d or [] if isinstance(x, str)}
    for r in repairs:
        for o in r.get("observations", []):
            paths |= {c["document"] for c in [o.get("source") or {}, *o.get("citations", [])]
                      if isinstance(c.get("document"), str)}
    out = {}
    for p in sorted(x for x in paths if x):
        local = p
        for old, new in remap:
            local = new + local[len(old):] if local.startswith(old) else local
        f = Path(local)
        if f.is_file():
            out[p] = hashlib.sha256(f.read_bytes()).hexdigest()
    print(f"hashed {len(out)} of {len(paths)} cited document path(s)")
    return out


def snapshot(args: argparse.Namespace) -> int:
    focus = ScenarioScript.load(args.scenario).initialization.focus
    app = create_app(scenario=args.scenario, storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        if args.days:
            c.patch("/api/config/review", json={"policy": "auto_approve_all", "approve_pending": True})
            for f in sorted(Path(args.days).glob("*.json")):
                bundle = json.loads(f.read_text())
                if focus is not None:
                    bundle, _ = focus_result(focus).narrow_bundle(bundle)
                    if not bundle["items"]:
                        continue
                c.post("/api/import", json={"bundle": bundle})
                while c.get("/api/sim/status").json()["state"] == "running":
                    time.sleep(0.2)
        runner = app.state.axelrod.runner
        ctl = runner.controller
        eng = ctl.engine
        g = eng.wm.graph
        companies = {e for e, x in g.entities.items() if str(x.kind) == "company"}
        sources, repairs = {"catalogue": {}, "citations": {}}, []
        if args.construction_sources:
            raw = load_sources(args.construction_sources)
            keep = [c for c in raw["companies"] if c in companies]
            sources = {"catalogue": {k: v for k, v in raw["catalogue"].items() if v["company"] in keep},
                       "citations": {k: [r for r in v if r["company"] in keep] for k, v in raw["citations"].items()}}
            repairs = [r for r in load_repair(args.construction_sources) if r.get("entity") in companies]
        remap = [tuple(x.split("=", 1)) for x in args.remap]
        doc = wm_export(eng.wm, eng.ltm, world_model_id=args.world_model_id, label=args.label, version=eng.version,
                        state_hash=eng.state_hash, generated_at=now(), entity_ids=args.entity or None,
                        subjects=args.subject, sources=sources, repairs=repairs,
                        document_hashes=document_hashes(sources, repairs, remap), versions=eng.storage.versions(),
                        changes=log(eng, limit=100_000), proposals=list(ctl.proposals.values()), commit=commit())
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    n = {k: len(doc[k]) for k in ("entities", "variables", "records", "bindings", "relations", "views", "paths")}
    print(f"version {doc['manifest']['version']} as of {doc['manifest']['as_of']}: {n} -> {out}")
    return 0


def series(args: argparse.Namespace) -> int:
    def make() -> ImportRunner:
        found = find_scenario(args.scenario)
        raw = load_scenario_yaml(found / "scenario.yaml" if found is not None else args.scenario)
        raw["imports_dir"] = None
        r = ImportRunner(None, None, ScenarioScript.model_validate(raw), True, storage=MemoryBackend())
        r.load()
        return r

    first, second = (json.loads(Path(p).read_text()) for p in (args.first, args.second))
    docs = update_series(make, first, second, world_model_id=args.world_model_id, label=args.label,
                         generated_at=now(), series_id=args.series_id or f"{args.world_model_id}-updates",
                         subjects=tuple(args.subject))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for d in docs:
        sc = d["manifest"]["scenario"]
        f = out / f"step{sc['step']}_{sc['operation']}.json"
        f.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n")
        print(f"step {sc['step']} {sc['operation']}: version {d['manifest']['version']} -> {f.name}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("snapshot", "series"):
        p = sub.add_parser(name)
        p.add_argument("scenario")
        if name == "series":
            p.add_argument("first", help="the first import bundle (JSON)")
            p.add_argument("second", help="the second import bundle (JSON)")
            p.add_argument("--series-id")
        p.add_argument("out")
        p.add_argument("--world-model-id", required=True)
        p.add_argument("--label", required=True)
        p.add_argument("--subject", action="append", default=[])
        if name == "snapshot":
            p.add_argument("--days", help="a folder of import bundles to fold in first, each item approved")
            p.add_argument("--construction-sources", help="a folder of <company>/sources.json, citations.json, repair.json")
            p.add_argument("--remap", action="append", default=[], help="OLD=NEW path prefix for hashing documents")
            p.add_argument("--entity", action="append", default=[], help="export only these entities (all by default)")
    args = ap.parse_args()
    return snapshot(args) if args.command == "snapshot" else series(args)


if __name__ == "__main__":
    sys.exit(main())
