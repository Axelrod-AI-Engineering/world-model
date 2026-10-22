"""Export a scenario's world model as the view ingestion reads (axelrod_ingest.contract.world_view), with the world's
inverted subject patterns, as one canonical JSON file. Ingestion's tests and its bench run against this file, so
they never need the world model.

    uv run python world_model/scripts/export_world_view.py acme_demo ingestion/tests/fixtures/world_view_acme.json \\
        --client-dir world_model/tests/fixtures/clients
    uv run python world_model/scripts/export_world_view.py sally_demo data/work/sally/world_view.json   # a client's

The file is {"inverted": [...patterns...], "world_view": {...}}: sorted, with sorted keys, so equal worlds give equal bytes.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def export(scenario: str) -> dict:
    """The scenario's world view and inverted patterns, as plain data."""
    import yaml

    from axelrod_wm.intake.world_view import world_view_of
    from axelrod_wm.repo.snapshots import MemoryBackend
    from axelrod_wm.sim.runner import build_runner

    r = build_runner(scenario, interactive=True, storage=MemoryBackend(), record_checklist=False)
    r.load()
    world_dir = r.controller.world_dir()
    templates = Path(world_dir) / "templates.yaml" if world_dir is not None else None
    subjects = (yaml.safe_load(templates.read_text()) or {}).get("subjects", []) if templates and templates.exists() else []
    return {"inverted": sorted(s["pattern"] for s in subjects if s.get("invert")),
            "world_view": json.loads(world_view_of(r.controller.engine.wm.graph).to_json())}


def render(data: dict) -> str:
    return json.dumps(data, sort_keys=True, indent=1, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("scenario")
    ap.add_argument("out", type=Path)
    ap.add_argument("--client-dir", help="the client root to find the scenario in (WORLD_MODEL_CLIENT_DIR)")
    a = ap.parse_args(argv)
    if a.client_dir:
        os.environ["WORLD_MODEL_CLIENT_DIR"] = str(Path(a.client_dir).resolve())
    a.out.write_text(render(export(a.scenario)))
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
