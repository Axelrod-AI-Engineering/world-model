"""The command-line scripts, end to end on the invented suite: collect (answers in, results out, byte-stable), the grader
(handed the invented key by path), the earlier recipe runner, and the packet tools."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from axelrod_wm.evaluation import inner_loop as il
from axelrod_wm.evaluation import inner_loop_packets as pk
from tests.where import INNER_LOOP_EXPORT, INNER_LOOP_KEY, INNER_LOOP_SUITE, SCRIPTS


def run(script: str, *args: str) -> str:
    done = subprocess.run([sys.executable, str(SCRIPTS / "evaluation" / script), *args], capture_output=True, text=True,
                          check=True)
    return done.stdout


def packets(tmp_path: Path) -> Path:
    out = tmp_path / "packets"
    shutil.copytree(INNER_LOOP_EXPORT, out / "export")
    suite = il.load_suite(INNER_LOOP_SUITE, il.Access([INNER_LOOP_SUITE]))
    pk.prepare_packets(suite, out, "r", tools_command="t", export_dir=out / "export", memo_dir=out / "m",
                       only=["TST-01-01", "TST-01-02"])
    (out / "answers" / "TST-01-01.json").write_text(json.dumps({"test_id": "TST-01-01", "status": "answered", "answer": {"q2": 130}}))
    return out


def test_collect_writes_byte_stable_results_and_the_grader_reads_them(tmp_path: Path) -> None:
    out = packets(tmp_path)
    t = tmp_path / "t.txt"
    t.write_text("transcript")
    args = ["collect", "--suite", str(INNER_LOOP_SUITE), "--packets", str(out), "--transcripts", str(t)]
    said = run("inner_loop.py", *args, "--out", str(tmp_path / "a" / "results.json"))
    run("inner_loop.py", *args, "--out", str(tmp_path / "b.json"))
    assert "46 cases: answered 1, blocked 45" in said and "answers sha256" in said
    assert (tmp_path / "a" / "results.json").read_bytes() == (tmp_path / "b.json").read_bytes()
    graded = run("inner_loop_grade.py", "--results", str(tmp_path / "b.json"), "--key", str(INNER_LOOP_KEY), "--run", "t",
                 "--out", str(tmp_path / "card"), "--forbid", "heldout", "--explain")
    card = json.loads((tmp_path / "card.json").read_text())
    assert card["run"] == "t" and card["graded_inputs"]["files"] == 1 and "review gates:" in graded
    assert "Graded answers:" in (tmp_path / "card.md").read_text()
    assert card["review_gates"]["answer_key_separation"]["transcripts"]["mentions"]["heldout"] == 0
    only = run("inner_loop.py", *args, "--only", "TST-01-01", "--out", str(tmp_path / "c.json"))
    assert "1 cases: answered 1" in only
    no_explain = run("inner_loop_grade.py", "--results", str(tmp_path / "b.json"), "--key", str(INNER_LOOP_KEY), "--out", str(tmp_path / "c2"))
    assert "G-01-02" not in no_explain


def test_the_earlier_recipe_runner_still_works(tmp_path: Path) -> None:
    said = run("inner_loop.py", "run-recipes", "--suite", str(INNER_LOOP_SUITE), "--recipes", str(INNER_LOOP_SUITE / "recipes.yaml"),
               "--only", "TST-01-01,TST-01-02", "--out", str(tmp_path / "r.json"))
    assert said.startswith("2 cases") and json.loads((tmp_path / "r.json").read_text())["results"][0]["status"] == "answered"


def test_the_packet_tools_run_from_the_command_line() -> None:
    out = json.loads(run("il_tools.py", "calc", "--expr", "a * b", "--input", "a=1,234", "--input", "b=2"))
    assert out["value"] == 2468
    listing = json.loads(run("il_tools.py", "export-list", "--export", str(INNER_LOOP_EXPORT)))
    assert listing[0]["file"] == "domain_pack.json"
    refused = subprocess.run([sys.executable, str(SCRIPTS / "evaluation" / "il_tools.py"), "op-update-undo", "--payload",
                              str(INNER_LOOP_SUITE / "fixture_inputs.json")], capture_output=True, text=True, check=True)
    body = json.loads(refused.stdout)
    assert body["supported"] is False and "undo" in body["reason"]
