"""Run the inner-loop accuracy suite against a world: the runner answers a questions-only bank from the world model.

    python world_model/scripts/evaluation/inner_loop.py --suite <suite folder> --recipes <recipes.yaml> [more.yaml ...] \
        [--world sally_demo] [--only TWM-01-01,...] --out <results.json>

The runner reads only the suite folder and the recipes (the guard in `Access` refuses anything else). It is never given
the answer key; the grader (inner_loop_grade.py) is. Results are deterministic: the same inputs give the same bytes.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from axelrod_wm.evaluation.inner_loop import Access, dumps, load_recipes, load_suite, run_suite  # noqa: E402


class BundleContractStore:
    """A clean store reached through the v1 bundle contract. It says whether the contract can state that one item
    corrects and supersedes another, by looking at the contract's own fields; until it can, nothing is ingested."""

    def __init__(self) -> None:
        from axelrod_ingest.contract.bundle import ImportItem

        self.can_state_supersession = any("supersed" in f for f in ImportItem.model_fields)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--suite", required=True)
    ap.add_argument("--recipes", required=True, nargs="+")
    ap.add_argument("--world", default="")
    ap.add_argument("--only", default="")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    logging.disable(logging.INFO)
    access = Access([Path(a.suite), *{Path(r).parent for r in a.recipes}])
    suite = load_suite(Path(a.suite), access)
    recipes = {k: v for r in a.recipes for k, v in load_recipes(Path(r), access).items()}
    only = [x for x in a.only.split(",") if x] or None
    if a.world:
        from fastapi.testclient import TestClient

        from axelrod_wm.api.app import create_app
        from axelrod_wm.evaluation.golden import V1Reader
        from axelrod_wm.evaluation.inner_loop import V1Service
        from axelrod_wm.repo.snapshots import MemoryBackend

        def fresh_service():
            """A clean world per use: a new app on its own in-memory storage."""
            clean = create_app(scenario=a.world, storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
            stack.append(TestClient(clean))
            return V1Service(stack[-1].__enter__(), a.world)

        stack: list = []
        app = create_app(scenario=a.world, storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
        with TestClient(app) as c:
            run = run_suite(suite, recipes, V1Reader(c), only, services=fresh_service, stores=BundleContractStore)
        for client in stack:
            client.__exit__(None, None, None)
    else:
        run = run_suite(suite, recipes, None, only)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(dumps(run), encoding="utf-8")
    counts: dict[str, int] = {}
    for r in run["results"]:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"{len(run['results'])} cases: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
