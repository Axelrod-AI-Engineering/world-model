"""Grade a runner's results against the inner-loop suite's answer key and write the scorecard (.json and .md).

    python world_model/scripts/evaluation/inner_loop_grade.py --results <results.json> --key <answer key> \
        --run <label> --out <scorecard base path, without extension> [--explain]

The key path is an explicit argument: only this script and its module are handed it. The console shows the counts
and, with --explain, each failed check of a *development* case; a validation candidate shows only its status in the
files and never an expected answer.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from axelrod_wm.evaluation.inner_loop_grade import grade, markdown  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--run", default="run")
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default="", help="grade only these test ids (comma separated); the others are left out, not counted")
    ap.add_argument("--mode", choices=("judge", "lexical"), default="judge", help="which grading sets the headline; both are reported")
    ap.add_argument("--verdicts", help="the folder of judge verdicts (inner_loop_judge.py prepare writes the packets)")
    ap.add_argument("--explain", action="store_true")
    ap.add_argument("--forbid", action="append", default=[], help="a marker to look for in the agents' transcripts (e.g. the held-out folder name)")
    a = ap.parse_args(argv)
    results = json.loads(Path(a.results).read_text(encoding="utf-8"))
    card = grade(results, Path(a.key), a.run, tuple(a.forbid), tuple(x for x in a.only.split(",") if x), a.mode,
                 Path(a.verdicts) if a.verdicts else None)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(card, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    out.with_suffix(".md").write_text(markdown(card), encoding="utf-8")
    m = card["main"]
    print(f"main: pass {m['pass']} fail {m['fail']} blocked {m['blocked']} not_run {m['not_run']}; "
          f"executed pass rate {m['executed_pass_rate']}; execution coverage {m['execution_coverage']}")
    for fam, v in card["by_family"].items():
        print(f"  {fam}: pass {v['pass']} fail {v['fail']} blocked {v['blocked']} not_run {v['not_run']}")
    for mode, v in card["modes"].items():
        print(f"  [{mode}] pass {v['pass']} fail {v['fail']} blocked {v['blocked']} not_run {v['not_run']} "
              f"executed pass rate {v['executed_pass_rate']}")
    g = card["review_gates"]["counts"]
    print(f"review gates: pass {g['pass']} fail {g['fail']} blocked {g['blocked']} not_run {g['not_run']}")
    if a.explain:
        for r in card["cases"]:
            if r["status"] in ("fail", "blocked") and r["split"] == "development":
                print(f"{r['test_id']} {r['status']}: {r['reason']}")
                for d in r.get("detail", []):
                    print(f"    {d['facet']} {d['label']}: expected {d['expected']!r}, got {d['actual']!r}")
                if "key_text" in r:
                    print(f"    key: {r['key_text']['acceptance_check']} || {r['key_text']['precise_answer']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
