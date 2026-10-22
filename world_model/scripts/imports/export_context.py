"""Export a scenario's world model in a client's v4.1.4 layout (context/v4.py) to a folder, as the upload set.

Loads the scenario, optionally folds in a folder of daily import bundles (each approved, as a reviewer would), optionally
poses the scenario's ready theses, and writes each part under the file name the load order gives it: the 03x domain
pack, its 020 registry entry, the current state as an evidence pack, one evidence pack per forecast, and the manifest.
By default it also writes reading/ (context/reading.py): the pack split into files of at most --max-file-kb (100) that
an answering agent can open, with 00_START_HERE.md; the whole pack stays as the machine-import file.
With --client-core, the client's own 000, 010, and 020 are copied beside them (020 with our registry row appended), so
the folder is a complete upload set.

With --construction-sources (a folder of <company>/sources.json and citations.json), the export resolves its evidence
(context/v4.attach_sources): each relationship whose transition cites sources, and each cited value baseline, carries
`evidence_refs` (source id, document, location, passage); the source catalogue is written as its own file, listed in the
manifest's load order after the evidence pack; and the domain pack's `citation_gaps` lists source ids that do not
resolve and material claims without a citation. The script prints the counts. Passages are the client's text.

    uv run python world_model/scripts/imports/export_context.py sally_demo data/exports/sally/<name> \\
        --days data/work/sally/days --theses --client-core data/sources/sally/unpacked/world_model_v4/<folder> \\
        --construction-sources data/work/sally/construction

A focused scenario (engine/focus.py, world_model/docs/construction/focus.md) imports only the bundle items about its companies and
the players they connect to (the script prints what each bundle kept and dropped), and the source catalogue keeps only
the exported companies' folders.

Client material stays local: point the output and the client core at a gitignored folder (data/<client>_data).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.context.construction import load_sources
from axelrod_wm.context.earnings import attach_repair, load_repair
from axelrod_wm.context.reading import build_reading_set
from axelrod_wm.context.v4 import attach_sources
from axelrod_wm.engine.focus import focus_result
from axelrod_wm.repo.snapshots import MemoryBackend
from axelrod_wm.sim.scenario import ScenarioScript


def restrict_sources(sources: dict, companies: set[str]) -> dict:
    """`load_sources`' result with only these companies' folders: their catalogue entries and citations."""
    keep = [c for c in sources["companies"] if c in companies]
    left = sorted(set(sources["companies"]) - set(keep))
    if left:
        print(f"sources: left out the folders of {len(left)} company(ies) not in this export")
    cites = {k: [r for r in refs if r["company"] in keep] for k, refs in sources["citations"].items()}
    return {"catalogue": {k: v for k, v in sources["catalogue"].items() if v["company"] in keep},
            "citations": {k: v for k, v in cites.items() if v}, "companies": keep,
            "problems": [p for p in sources["problems"] if not any(c in p for c in left)]}


def write(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n")
    print(f"  wrote {path.name}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenario")
    ap.add_argument("out")
    ap.add_argument("--days", help="a folder of import bundles to fold in first, in file order, each item approved")
    ap.add_argument("--theses", action="store_true", help="also pose the scenario's ready theses and export their evidence")
    ap.add_argument("--client-core", help="the client's folder holding 000, 010, and 020, to copy beside the export")
    ap.add_argument("--max-file-kb", type=int, default=100,
                    help="also write reading/, files of at most this many KB for an answering agent (0 = none)")
    ap.add_argument("--construction-sources", help="a folder of <company>/sources.json and citations.json")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    focus = ScenarioScript.load(args.scenario).initialization.focus
    app = create_app(scenario=args.scenario, storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        if args.days:
            c.patch("/api/config/review", json={"policy": "auto_approve_all", "approve_pending": True})
            files = sorted(Path(args.days).glob("*.json"))
            folded = 0
            for f in files:
                bundle = json.loads(f.read_text())
                if focus is not None:
                    # a focused world imports only what concerns it (engine/focus.narrow_bundle; the import does the same)
                    bundle, n = focus_result(focus).narrow_bundle(bundle)
                    print(f"  {f.name}: {n['items_kept']} item(s) kept, {len(n['items_dropped'])} dropped as about a "
                          f"removed company, {n['signals_dropped']} signal(s) on removed values left out")
                    if not bundle["items"]:
                        continue
                c.post("/api/import", json={"bundle": bundle})
                folded += 1
                while c.get("/api/sim/status").json()["state"] == "running":
                    time.sleep(0.2)
            print(f"folded in {folded} of {len(files)} bundle(s)")
        st = c.get("/api/sim/status").json()
        print(f"model as of {st['sim_time'][:10]}, version {st['version']}")
        ctx = c.get("/api/context/v4").json()
        m = ctx["manifest"]
        if args.construction_sources:
            # only the exported companies' sources: a focused world never carries a removed company's documents
            exported = {r["axelrod_entity_id"] for r in ctx["domain_pack"]["companies"]}
            doc = attach_sources(ctx, restrict_sources(load_sources(args.construction_sources), exported))
            n = doc["counts"]
            print(f"sources: {n['sources']} in the catalogue ({', '.join(doc['companies'])}); {n['resolved_ids']} cited "
                  f"id(s) resolve, {n['unresolved_ids']} do not; {n['cited_links']} link(s) and {n['cited_values']} "
                  f"value(s) cited; {n['claims_without_citation']} material claim(s) without a citation; "
                  f"{n['unknown_citation_keys']} citation key(s) name nothing exported")
            for u in doc["citation_gaps"]["unresolved_source_ids"]:
                print(f"  UNRESOLVED {u['source_id']} (cited by {len(u['cited_by'])} link(s) or value(s))")
            for p in doc["citation_gaps"]["catalogue_problems"]:
                print(f"  SOURCES {p}")
            # Oct 19: a company's repair data (<company>/repair.json) binds its reported observations, bridges and assumptions
            for rep in load_repair(args.construction_sources, {c["company_id"] for c in ctx["domain_pack"]["companies"]}):
                n = attach_repair(ctx, rep, args.days)
                print(f"repair {rep['repair_version']} for {rep['company_id']}: {n['values_with_reported_observation']} of {n['values']} values carry a reported "
                      f"observation; {n['observations']} observations, {n['evidence_records']} explanations, {n['bridges']} bridges, {n['pairs']} pairs, "
                      f"{n['reconciliations']} reconciliations (not ok: {', '.join(n['reconciliations_not_ok']) or 'none'}), input classes "
                      f"{n['input_classes']}, {n['assumption_records']} assumptions, {n['checks']} checks")
        files = {f["source"]: f["file"] for f in m["load_order"]}
        write(out / files["this export: domain_pack"], ctx["domain_pack"])
        write(out / files["this export: evidence"], ctx["evidence"])
        if "sources" in ctx:
            write(out / files["this export: sources"], ctx["sources"])
        write(out / m["registry_entry_file"], ctx["registry_entry"])
        forecasts = []
        if args.theses:
            for t in c.get("/api/scenario-theses").json():
                fid = c.post(f"/api/theses/{t['id']}/pose").json()["forecast"]["id"]
                fctx = c.get("/api/context/v4", params={"forecast": fid}).json()
                name = next(f["file"] for f in fctx["manifest"]["load_order"] if f["source"] == "this export: forecast")
                write(out / name, fctx["forecast"])
                forecasts.append({"file": name, "source": "this export: forecast", "thesis_id": t["id"],
                                  "question": fctx["forecast"]["question"]})
        m["load_order"] = [*m["load_order"], *forecasts]
        if args.client_core:
            core = Path(args.client_core)
            copied = {}
            for prefix in ("000_", "010_", "020_"):
                src = next(iter(sorted(core.glob(f"{prefix}*"))), None)
                if src is None:
                    continue
                if prefix == "020_":
                    reg = json.loads(src.read_text())
                    row = ctx["registry_entry"]["domains"][0]
                    reg["domains"] = [d for d in reg.get("domains", []) if d.get("domain_pack_id") != row["domain_pack_id"]] + [row]
                    if isinstance(reg.get("numbering_scheme"), dict):
                        reg["numbering_scheme"][row["file_index"]] = row["domain_pack_name"]
                    write(out / src.name, reg)
                else:
                    shutil.copyfile(src, out / src.name)
                    print(f"  copied {src.name}")
                copied[prefix] = src.name
            for f in m["load_order"]:
                for prefix, name in copied.items():
                    if f["file"].startswith(prefix):
                        f["file"] = name
                        f["source"] = "yours" + (", with our registry row appended" if prefix == "020_" else ", unchanged")
        if args.max_file_kb:
            check = build_reading_set(out, ctx, m, cap_kb=args.max_file_kb)
            files = m["reading_set"]["files"]
            print(f"reading set: {len(files)} file(s) in reading/, largest {max(f['bytes'] for f in files) / 1024:.1f} KB; "
                  f"{check['shard_objects']} of {check['objects']} pack objects, "
                  f"{check['missing']} missing, {check['unexpected_or_duplicated']} duplicated or unexpected")
        # a version for every file (its sha256): a changed file is visible; the as-of and decision dates do not move with the run
        m["file_versions"] = {f["file"]: hashlib.sha256((out / f["file"]).read_bytes()).hexdigest()[:16]
                              for f in m["load_order"] if (out / f["file"]).exists()}
        write(out / "axelrod_manifest.json", m)
    print(f"done: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
