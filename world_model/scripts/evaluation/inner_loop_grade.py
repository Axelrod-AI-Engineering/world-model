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
    ap.add_argument("--explain", action="store_true")
    a = ap.parse_args(argv)
    results = json.loads(Path(a.results).read_text(encoding="utf-8"))
    card = grade(results, Path(a.key), a.run)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(card, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    out.with_suffix(".md").write_text(markdown(card), encoding="utf-8")
    m = card["main"]
    print(f"main: pass {m['pass']} fail {m['fail']} blocked {m['blocked']} not_run {m['not_run']}; "
          f"executed pass rate {m['executed_pass_rate']}; execution coverage {m['execution_coverage']}")
    for fam, v in card["by_family"].items():
        print(f"  {fam}: pass {v['pass']} fail {v['fail']} blocked {v['blocked']} not_run {v['not_run']}")
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
