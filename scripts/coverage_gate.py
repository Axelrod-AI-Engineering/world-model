"""The coverage gate: every source file of a workspace member is covered, every line and every branch, by that member's own
tests. No floor to ratchet, no strict list, no pragmas, no omissions: an unreachable line is deleted.

Each member is gated alone, from its own directory, so a member cannot lean on another member's tests:

    cd ingestion  && uv run pytest --cov --cov-report=json:coverage.json --junitxml=junit.xml
    uv run python scripts/coverage_gate.py ingestion/coverage.json --member ingestion --junit ingestion/junit.xml
    cd world_model && uv run pytest --cov --cov-report=json:coverage.json --junitxml=junit.xml
    uv run python scripts/coverage_gate.py world_model/coverage.json --member world_model --junit world_model/junit.xml

The gate reads coverage.py's JSON report (and, optionally, pytest's JUnit XML), and fails when

1. a file under the member's `src/<package>/` has a line or a branch not covered;
2. a source file on disk is missing from the report (it was never imported, so never measured);
3. the report holds no source file of the member at all (a gate that checked nothing);
4. a test failed (the JUnit XML names it).

`--summary FILE` appends a table of coverage per sub-package (CI passes $GITHUB_STEP_SUMMARY).
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEMBERS = {"ingestion": "axelrod_ingest", "world_model": "axelrod_wm"}      # member folder -> its import package


def pct(hit: int, total: int) -> float:
    return 100.0 if total == 0 else round(100.0 * hit / total, 2)


def norm(path: str) -> str:
    """A report path relative to the member's src folder: 'axelrod_wm/api/app.py'."""
    p = path.replace("\\", "/")
    return p[p.index("src/") + 4:] if "src/" in p else p


def member_files(report: dict, package: str) -> dict[str, dict]:
    return {norm(p): f for p, f in report["files"].items() if norm(p).startswith(package + "/")}


def source_files(member: str, root: Path = ROOT) -> set[str]:
    """Every Python file under the member's src, as the report would name it."""
    package = MEMBERS[member]
    base = root / member / "src"
    return {p.relative_to(base).as_posix() for p in (base / package).rglob("*.py")}


def failures(report: dict, member: str, root: Path = ROOT) -> list[str]:
    files = member_files(report, MEMBERS[member])
    out = []
    if not files:
        return [f"no source file of {member} in the report (is coverage measuring {MEMBERS[member]}?)"]
    for name in sorted(source_files(member, root) - set(files)):
        out.append(f"{name}: not in the report (never imported, so never measured)")
    for name, f in sorted(files.items()):
        t = f["summary"]
        if t["missing_lines"] or t.get("missing_branches", 0):
            out.append(f"{name}: {t['missing_lines']} lines and {t.get('missing_branches', 0)} branches not covered "
                       f"(lines {f.get('missing_lines', [])})")
    return out


def totals(files: dict[str, dict]) -> dict:
    s: dict[str, int] = defaultdict(int)
    for f in files.values():
        t = f["summary"]
        s["lines"] += t["num_statements"]
        s["lines_hit"] += t["covered_lines"]
        s["branches"] += t.get("num_branches", 0)
        s["branches_hit"] += t.get("covered_branches", 0)
    return {"lines": pct(s["lines_hit"], s["lines"]), "branches": pct(s["branches_hit"], s["branches"]),
            "n_lines": s["lines"], "n_branches": s["branches"]}


def by_subpackage(files: dict[str, dict]) -> dict[str, dict]:
    groups: dict[str, dict] = defaultdict(dict)
    for name, f in files.items():
        parts = name.split("/")
        groups[parts[1] if len(parts) > 2 else "(top level)"][name] = f
    return {k: totals(v) for k, v in sorted(groups.items())}


def junit_counts(path: Path) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "skipped": 0}
    for case in ET.parse(path).getroot().iter("testcase"):
        kids = {c.tag for c in case}
        counts["failed" if kids & {"failure", "error"} else "skipped" if "skipped" in kids else "passed"] += 1
    return counts


def summary(member: str, files: dict[str, dict], counts: dict[str, int] | None) -> str:
    rows = [f"### {member}", ""]
    if counts:
        rows += [f"Tests: {counts['passed']} passed, {counts['failed']} failed, {counts['skipped']} skipped", ""]
    rows += ["| Package | Lines | Branches |", "|---|---:|---:|"]
    rows += [f"| `{pkg}` | {t['lines']:.2f}% | {t['branches']:.2f}% |" for pkg, t in by_subpackage(files).items()]
    t = totals(files)
    rows += [f"| **all** | **{t['lines']:.2f}%** | **{t['branches']:.2f}%** |", ""]
    return "\n".join(rows)


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("report", type=Path, help="coverage.py's JSON report")
    ap.add_argument("--member", required=True, choices=sorted(MEMBERS))
    ap.add_argument("--junit", type=Path, help="pytest's JUnit XML")
    ap.add_argument("--summary", type=Path, help="append a table here (e.g. $GITHUB_STEP_SUMMARY)")
    a = ap.parse_args(argv)

    report = json.loads(a.report.read_text())
    problems = failures(report, a.member, root)
    counts = junit_counts(a.junit) if a.junit else None
    if counts and counts["failed"]:
        problems.append(f"{counts['failed']} tests failed")
    files = member_files(report, MEMBERS[a.member])
    now = totals(files)
    print(f"{a.member}: lines {now['lines']:.2f}% ({now['n_lines']})  branches {now['branches']:.2f}% ({now['n_branches']})")
    if a.summary:
        with a.summary.open("a") as f:
            f.write(summary(a.member, files, counts) + "\n")
    for p in problems:
        print(f"FAIL {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
