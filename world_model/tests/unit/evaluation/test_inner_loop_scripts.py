"""The two command-line scripts, end to end on the invented suite: the runner writes byte-stable results, and the grader
(handed the invented key by path) writes the scorecard as .json and .md."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.where import INNER_LOOP_KEY, INNER_LOOP_SUITE, SCRIPTS


def run(script: str, *args: str) -> str:
    done = subprocess.run([sys.executable, str(SCRIPTS / "evaluation" / script), *args], capture_output=True, text=True,
                          check=True)
    return done.stdout


def test_the_runner_script_writes_byte_stable_results(tmp_path: Path) -> None:
    args = ["--suite", str(INNER_LOOP_SUITE), "--recipes", str(INNER_LOOP_SUITE / "recipes.yaml"),
            "--only", "TST-01-01,TST-01-02,TST-01-09"]
    out = run("inner_loop.py", *args, "--out", str(tmp_path / "a" / "results.json"))
    run("inner_loop.py", *args, "--out", str(tmp_path / "b.json"))
    assert "3 cases: answered 2, blocked 1" in out
    assert (tmp_path / "a" / "results.json").read_bytes() == (tmp_path / "b.json").read_bytes()
    body = json.loads((tmp_path / "b.json").read_text())
    assert [r["status"] for r in body["results"]] == ["answered", "answered", "blocked"]


def test_the_grader_script_writes_the_scorecard_and_explains_development_failures(tmp_path: Path) -> None:
    results = tmp_path / "results.json"
    run("inner_loop.py", "--suite", str(INNER_LOOP_SUITE), "--recipes", str(INNER_LOOP_SUITE / "recipes.yaml"),
        "--only", "TST-01-01", "--out", str(results))
    out = run("inner_loop_grade.py", "--results", str(results), "--key", str(INNER_LOOP_KEY), "--run", "t",
              "--out", str(tmp_path / "card"), "--explain")
    card = json.loads((tmp_path / "card.json").read_text())
    assert card["run"] == "t" and card["main"]["not_run"] == card["main"]["cases"]
    assert "# Inner-loop accuracy scorecard" in (tmp_path / "card.md").read_text()
    assert "main: pass 0 fail 0 blocked 0 not_run 19" in out and "review gates:" in out
    out2 = run("inner_loop_grade.py", "--results", str(results), "--key", str(INNER_LOOP_KEY), "--out", str(tmp_path / "c2"))
    assert "G-01-02" not in out2                                      # without --explain nothing is listed
