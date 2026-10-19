"""Coverage gate and the README's test widget (Oct 17).

Reads coverage.py's JSON report (and, optionally, pytest's JUnit XML) and:

1. **Strict modules** must be fully covered: every line and every branch. They are the ingestion pipeline, the
   lakehouse, and the outward service (STRICT below). No pragmas, no omissions: an unreachable line is deleted.
2. **Everything else ratchets.** `coverage-floor.json` holds the repository's line, branch, and combined coverage;
   a run below the floor fails, and `--update` raises the floor when a run beats it (never lowers it).
3. **The README widget.** `--readme README.md` rewrites the block between `<!-- tests:start -->` and
   `<!-- tests:end -->`: tests passed per suite (from the JUnit XML) and coverage per package.

    uv run pytest --cov=axelrod_wm --cov-branch --cov-report=json:coverage.json --junitxml=junit.xml
    uv run python scripts/coverage_gate.py coverage.json --junit junit.xml [--update] [--readme README.md]
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

STRICT = ("src/axelrod_wm/lake/*.py", "src/axelrod_wm/ingest/*.py", "src/axelrod_wm/api/v1/*.py",
          "src/axelrod_wm/api/tokens.py", "src/axelrod_wm/api/mcp.py", "src/axelrod_wm/api/keys.py")
FLOOR = Path("coverage-floor.json")
TOLERANCE = 0.05          # percentage points: platform noise in branch counting, nothing more
START, END = "<!-- tests:start -->", "<!-- tests:end -->"


def pct(hit: int, total: int) -> float:
    return 100.0 if total == 0 else round(100.0 * hit / total, 2)


def totals(files: dict) -> dict:
    s = defaultdict(int)
    for f in files.values():
        t = f["summary"]
        s["lines"] += t["num_statements"]
        s["lines_hit"] += t["covered_lines"]
        s["branches"] += t.get("num_branches", 0)
        s["branches_hit"] += t.get("covered_branches", 0)
    return {"lines": pct(s["lines_hit"], s["lines"]), "branches": pct(s["branches_hit"], s["branches"]),
            "combined": pct(s["lines_hit"] + s["branches_hit"], s["lines"] + s["branches"]),
            "n_lines": s["lines"], "n_branches": s["branches"]}


def norm(path: str) -> str:
    p = path.replace("\\", "/")
    return p[p.index("src/"):] if "src/" in p else p


def strict_failures(files: dict) -> list[str]:
    out = []
    for path, f in sorted(files.items()):
        if not any(fnmatch.fnmatch(norm(path), pat) for pat in STRICT):
            continue
        t = f["summary"]
        if t["missing_lines"] or t.get("missing_branches", 0):
            out.append(f"{norm(path)}: {t['missing_lines']} lines and {t.get('missing_branches', 0)} branches "
                       f"not covered (lines {f.get('missing_lines', [])})")
    return out


def by_package(files: dict) -> dict[str, dict]:
    groups: dict[str, dict] = defaultdict(dict)
    for path, f in files.items():
        parts = norm(path).split("/")
        pkg = parts[2] if len(parts) > 3 else "(top level)"
        groups[pkg][path] = f
    return {k: totals(v) for k, v in sorted(groups.items())}


def junit_suites(path: Path) -> dict[str, dict]:
    """Passed, failed, and skipped tests per suite folder (tests/<suite>/...)."""
    out: dict[str, dict] = defaultdict(lambda: {"passed": 0, "failed": 0, "skipped": 0})
    for case in ET.parse(path).getroot().iter("testcase"):
        cls = case.get("classname", "")
        suite = cls.split(".")[1] if cls.startswith("tests.") and cls.count(".") >= 2 else "other"
        kids = {c.tag for c in case}
        key = "failed" if kids & {"failure", "error"} else "skipped" if "skipped" in kids else "passed"
        out[suite][key] += 1
    return dict(sorted(out.items()))


def widget(files: dict, suites: dict[str, dict] | None) -> str:
    rows = [START, ""]
    if suites:
        rows += ["| Suite | Passed | Failed | Skipped |", "|---|---:|---:|---:|"]
        for name, s in suites.items():
            mark = "✅" if s["failed"] == 0 else "❌"
            rows.append(f"| {mark} `tests/{name}` | {s['passed']} | {s['failed']} | {s['skipped']} |")
        rows.append("")
    strict = {norm(p) for p in files if any(fnmatch.fnmatch(norm(p), pat) for pat in STRICT)}
    rows += ["| Package | Lines | Branches | Gate |", "|---|---:|---:|---|"]
    for pkg, t in by_package(files).items():
        gate = "100% required" if any(s.split("/")[2] == pkg for s in strict) else "ratchet"
        if pkg == "api":
            gate = "100% for service, mcp, keys; ratchet"
        rows.append(f"| `{pkg}` | {t['lines']:.1f}% | {t['branches']:.1f}% | {gate} |")
    t = totals(files)
    rows += [f"| **all** | **{t['lines']:.1f}%** | **{t['branches']:.1f}%** | floor in `coverage-floor.json` |", "",
             "Slow scenario runs (`--runslow`) are not in these numbers. "
             "Regenerate with `scripts/coverage_gate.py` (see its docstring).", "", END]
    return "\n".join(rows)


def write_readme(readme: Path, block: str) -> None:
    text = readme.read_text()
    if START not in text or END not in text:
        raise SystemExit(f"{readme} has no {START} ... {END} block")
    head, rest = text.split(START, 1)
    readme.write_text(head + block + rest.split(END, 1)[1])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("report", type=Path)
    ap.add_argument("--junit", type=Path)
    ap.add_argument("--floor", type=Path, default=FLOOR)
    ap.add_argument("--update", action="store_true", help="raise the floor when this run beats it")
    ap.add_argument("--readme", type=Path)
    ap.add_argument("--summary", type=Path, help="also write the widget here (e.g. $GITHUB_STEP_SUMMARY)")
    a = ap.parse_args(argv)

    files = json.loads(a.report.read_text())["files"]
    now = totals(files)
    problems = strict_failures(files)
    floor = json.loads(a.floor.read_text()) if a.floor.exists() else {}
    for k in ("lines", "branches", "combined"):
        if k in floor and now[k] < floor[k] - TOLERANCE:
            problems.append(f"{k} coverage {now[k]:.2f}% fell below the floor {floor[k]:.2f}%")
    suites = junit_suites(a.junit) if a.junit else None
    for name, s in (suites or {}).items():
        if s["failed"]:
            problems.append(f"tests/{name}: {s['failed']} failed")

    print(f"coverage: lines {now['lines']:.2f}%  branches {now['branches']:.2f}%  combined {now['combined']:.2f}%")
    if a.update and not problems:
        raised = {k: max(now[k], floor.get(k, 0.0)) for k in ("lines", "branches", "combined")}
        if raised != {k: floor.get(k) for k in raised}:
            a.floor.write_text(json.dumps(raised, indent=2) + "\n")
            print(f"floor raised to {raised}")
    block = widget(files, suites)
    if a.readme:
        write_readme(a.readme, block)
    if a.summary:
        with a.summary.open("a") as f:
            f.write(block.replace(START, "").replace(END, "") + "\n")
    for p in problems:
        print(f"FAIL {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
