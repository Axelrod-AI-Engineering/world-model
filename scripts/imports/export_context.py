"""Export a scenario's world model in a client's v4.1.4 layout (context/v4.py) to a folder, as the upload set.

Loads the scenario, optionally folds in a folder of daily import bundles (each approved, as a reviewer would), optionally
poses the scenario's ready theses, and writes each part under the file name the load order gives it: the 03x domain
pack, its 020 registry entry, the current state as an evidence pack, one evidence pack per forecast, and the manifest.
With --client-core, the client's own 000, 010, and 020 are copied beside them (020 with our registry row appended), so
the folder is a complete upload set.

    uv run python scripts/imports/export_context.py sally_demo data/sally_data/exports/<name> \\
        --days data/sally_data/days --theses --client-core data/sally_data/unpacked/world_model_v4/<folder>

Client material stays local: point the output and the client core at a gitignored folder (data/<client>_data).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.repo.snapshots import MemoryBackend


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
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    app = create_app(scenario=args.scenario, storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        if args.days:
            c.patch("/api/config/review", json={"policy": "auto_approve_all", "approve_pending": True})
            files = sorted(Path(args.days).glob("*.json"))
            for f in files:
                c.post("/api/import", json={"bundle": json.loads(f.read_text())})
                while c.get("/api/sim/status").json()["state"] == "running":
                    time.sleep(0.2)
            print(f"folded in {len(files)} bundle(s)")
        st = c.get("/api/sim/status").json()
        print(f"model as of {st['sim_time'][:10]}, version {st['version']}")
        ctx = c.get("/api/context/v4").json()
        m = ctx["manifest"]
        files = {f["source"]: f["file"] for f in m["load_order"]}
        write(out / files["this export: domain_pack"], ctx["domain_pack"])
        write(out / files["this export: evidence"], ctx["evidence"])
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
        write(out / "axelrod_manifest.json", m)
    print(f"done: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
