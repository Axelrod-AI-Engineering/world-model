"""Write judge packets for a collected run (grader side: it reads the answer key).

    python world_model/scripts/evaluation/inner_loop_judge.py prepare --results <results.json> --key <answer key> \
        --run <run> --out <judge folder> [--only id,id]

The judges write <judge folder>/verdicts/<test_id>.json. The grader combines them:

    python world_model/scripts/evaluation/inner_loop_grade.py --results <results.json> --key <answer key> \
        --verdicts <judge folder>/verdicts --out <scorecard path> [--mode judge|lexical]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from axelrod_wm.evaluation.inner_loop_judge import prepare_judge  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--results", required=True)
    p.add_argument("--key", required=True)
    p.add_argument("--run", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--only", default="")
    a = ap.parse_args(argv)
    meta = prepare_judge(json.loads(Path(a.results).read_text(encoding="utf-8")), Path(a.key), Path(a.out), a.run,
                         tuple(x for x in a.only.split(",") if x))
    print(f"{len(meta['cases'])} judge packets: {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
