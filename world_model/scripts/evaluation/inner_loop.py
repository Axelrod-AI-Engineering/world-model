"""The inner-loop accuracy suite as a file protocol.

    prepare   task packets (one folder per case) and the shared export, from a questions-only suite
    collect   the answers the agents wrote, checked against the schema, as results for the grader

    python world_model/scripts/evaluation/inner_loop.py prepare --suite <suite> --world sally_demo --run <run> --out <packets>
    python world_model/scripts/evaluation/inner_loop.py collect --suite <suite> --packets <packets> --out <results.json>

The runner reads only the suite folder (and, to collect, the packets): a guard refuses anything else and logs every file
read. It is never given the answer key; the grader (inner_loop_grade.py) is.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from axelrod_wm.clients import DATA_DIR  # noqa: E402
from axelrod_wm.evaluation.inner_loop import Access, dumps, load_suite  # noqa: E402
from axelrod_wm.evaluation.inner_loop_packets import collect, prepare_packets  # noqa: E402
from axelrod_wm.evaluation.inner_loop_tools import ModelReads  # noqa: E402

# the commands name the data folder, so a tool run from a worktree finds the world and its client content
TOOLS = f"WORLD_MODEL_DATA_DIR={DATA_DIR} uv run python {ROOT / 'scripts' / 'evaluation' / 'il_tools.py'}"


def world_client(scenario: str):
    from fastapi.testclient import TestClient

    from axelrod_wm.api.app import create_app
    from axelrod_wm.repo.snapshots import MemoryBackend

    logging.disable(logging.INFO)
    return TestClient(create_app(scenario=scenario, storage=MemoryBackend(), trace_dir=None, play_delay=0.0)).__enter__()


def make_export(a: argparse.Namespace, out: Path) -> Path:
    """The shared export: a current export of the world under test (export_context.py), or a copy of one already made."""
    dest = out / "export"
    if a.export_from:
        shutil.copytree(a.export_from, dest, dirs_exist_ok=True)
        return dest
    cmd = [sys.executable, str(ROOT / "scripts" / "imports" / "export_context.py"), a.world, str(dest)]
    for flag, value in (("--days", a.days), ("--construction-sources", a.construction_sources)):
        if value:
            cmd += [flag, value]
    subprocess.run(cmd, check=True, cwd=ROOT.parent)
    return dest


def prewarm(memo: Path, scenario: str) -> int:
    """Read once what an agent asks first: the entities, and the construction of each."""
    memo.mkdir(parents=True, exist_ok=True)
    (memo / "world.txt").write_text(scenario + "\n", encoding="utf-8")
    reads = ModelReads(memo, lambda _m: world_client(scenario))
    listing = reads.get("/entities", {"limit": 200})
    n = 1
    for e in listing["body"].get("data", []):
        reads.get(f"/entities/{e['id']}/construction")
        n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--suite", required=True)
    p.add_argument("--world", required=True)
    p.add_argument("--run", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--days")
    p.add_argument("--construction-sources")
    p.add_argument("--export-from")
    p.add_argument("--only", default="")
    c = sub.add_parser("collect")
    c.add_argument("--suite", required=True)
    c.add_argument("--packets", required=True)
    c.add_argument("--transcripts", nargs="*", default=[])
    c.add_argument("--out", required=True)
    c.add_argument("--only", default="")
    a = ap.parse_args(argv)
    only = [x for x in getattr(a, "only", "").split(",") if x] or None
    if a.cmd == "prepare":
        out = Path(a.out)
        suite = load_suite(Path(a.suite), Access([Path(a.suite)]))
        export = make_export(a, out)
        memo = out / "model_reads"
        n = prewarm(memo, a.world)
        meta = prepare_packets(suite, out, a.run, tools_command=TOOLS, export_dir=export, memo_dir=memo, only=only)
        print(f"{len(meta['cases'])} packets, an export of {meta['export_files']} files, {n} memoized reads: {out}")
        return 0
    if a.cmd == "collect":
        packets = Path(a.packets)
        suite = load_suite(Path(a.suite), Access([Path(a.suite), packets]))
        res = collect(suite, packets, [Path(t) for t in a.transcripts], only)
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(dumps(res), encoding="utf-8")
        counts: dict[str, int] = {}
        for x in res["results"]:
            counts[x["status"]] = counts.get(x["status"], 0) + 1
        print(f"{len(res['results'])} cases: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
              + f"; answers sha256 {res['answers']['sha256']}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
