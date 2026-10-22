"""The read-only tools of an inner-loop task packet: calc, export-list, export-search, export-read, model-get,
model-construction, op-ingest-orders, op-update-undo. See axelrod_wm/evaluation/inner_loop_tools.py.

    uv run python world_model/scripts/evaluation/il_tools.py calc --expr "a * b" --input a=2 --input b=3
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from axelrod_wm.evaluation.inner_loop_tools import capabilities, main, openapi_paths  # noqa: E402


def world(memo: Path):
    """The world the packets were prepared against (named in <memo>/world.txt), in process on a throwaway in-memory store."""
    from fastapi.testclient import TestClient

    from axelrod_wm.api.app import create_app
    from axelrod_wm.repo.snapshots import MemoryBackend

    logging.disable(logging.INFO)
    scenario = (memo / "world.txt").read_text(encoding="utf-8").strip()
    return TestClient(create_app(scenario=scenario, storage=MemoryBackend(), trace_dir=None, play_delay=0.0)).__enter__()


def operations():
    from axelrod_ingest.contract.bundle import ImportItem

    return capabilities(list(ImportItem.model_fields), openapi_paths(ROOT / "docs" / "api" / "openapi.yaml"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], world=world, ops=operations()))
