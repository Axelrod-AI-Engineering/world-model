"""The inner-loop suite for the real Toyota world, as a file protocol (client data: skipped when it is absent).

Prepares one packet per case from the client's suite folder, collects with no answers written, and asserts that every case is
reported blocked with its reason, that each packet holds only what its case is bound to, and that the answer-key separation
holds (what the runner read, and its modules' text). It does not assert a pass rate: the suite measures the model, and a
release decision is not a test."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from axelrod_wm.clients import DATA_DIR
from axelrod_wm.evaluation import inner_loop as il
from axelrod_wm.evaluation import inner_loop_packets as pk
from tests.clients import skip_without_client
from tests.where import INNER_LOOP_EXPORT

skip_without_client("sally_demo")
SUITE = DATA_DIR / "clients" / "sally" / "inner_loop_v1_1"
if not (SUITE / "questions.json").exists():
    pytest.skip("the inner-loop suite is absent (data/ is local and gitignored)", allow_module_level=True)


@pytest.fixture(scope="module")
def run(tmp_path_factory) -> tuple[Path, dict, il.Access]:
    out = tmp_path_factory.mktemp("packets")
    shutil.copytree(INNER_LOOP_EXPORT, out / "export")             # a stand-in export: the packets do not depend on its content
    access = il.Access([SUITE, out])
    suite = il.load_suite(SUITE, access)
    pk.prepare_packets(suite, out, "test", tools_command="tools", export_dir=out / "export", memo_dir=out / "memo")
    return out, pk.collect(suite, out), access


def test_every_case_has_a_packet_and_reports_blocked_without_an_answer(run) -> None:
    out, res, _ = run
    assert len(res["results"]) == 100 and len(list(out.glob("TWM-*"))) == 100
    assert {r["status"] for r in res["results"]} == {il.BLOCKED}
    assert {r["reason"] for r in res["results"]} == {"no answer file was written"}
    assert res["answers"]["files"] == 0 and sum(r["scorecard_group"] == "review_gate" for r in res["results"]) == 2


def test_a_packet_holds_only_its_cases_pages_and_no_label(run) -> None:
    out, _, _ = run
    bound = {c["test_id"]: c["frozen_excerpt_ids"] for c in json.loads((SUITE / "questions.json").read_text())["cases"]}
    for tid, ids in bound.items():
        have = {p.stem for p in (out / tid / "excerpts").glob("*.txt")}
        assert have == set(ids), tid
        text = (out / tid / "task.md").read_text(encoding="utf-8").lower()
        assert "development_split" not in text and "validation_candidate" not in text
    fx = json.loads((out / "TWM-09-07" / "fixture_inputs.json").read_text())
    assert "development_split" not in fx and "execution_mode" not in fx and fx["economic_gross_fx"] == 100


def test_the_runner_read_only_the_suite_and_the_packets(run) -> None:
    out, res, access = run
    roots = [Path(r) for r in res["access"]["roots"]]
    files = [Path(f["path"]) for f in res["access"]["files_read"]]
    assert files and all(any(f.is_relative_to(r) for r in roots) for f in files)
    assert not any("holdout" in part for f in files for part in f.parts)
    assert not access.allowed(DATA_DIR / "holdout" / "sally" / "inner_loop_v1_1" / "answer_key.json")


def test_the_modules_do_not_name_the_answer_key() -> None:
    for mod in (il, pk):
        text = Path(mod.__file__).read_text(encoding="utf-8").lower()
        assert "holdout" not in text and "answer_key" not in text
