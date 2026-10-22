"""A client's inner-loop suite as a file protocol (client data: skipped when it is absent).

Prepares one packet per case from the suite folder found in the client's data, collects with no answers written, and asserts that
every case is reported blocked with its reason, that each packet holds only what its case is bound to and none of the suite's own
labels, and that the answer-key separation holds (what the runner read, and its modules' text). It does not assert a pass rate:
the suite measures the model, and a release decision is not a test."""

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
SUITES = sorted((DATA_DIR / "clients").glob("*/inner_loop_*/questions.json"))
if not SUITES:
    pytest.skip("no inner-loop suite in the client's data (data/ is local and gitignored)", allow_module_level=True)
SUITE = SUITES[-1].parent


@pytest.fixture(scope="module")
def run(tmp_path_factory) -> tuple[Path, dict, il.Access]:
    out = tmp_path_factory.mktemp("packets")
    shutil.copytree(INNER_LOOP_EXPORT, out / "export")             # a stand-in export: the packets do not depend on its content
    access = il.Access([SUITE, out])
    suite = il.load_suite(SUITE, access)
    pk.prepare_packets(suite, out, "test", tools_command="tools", export_dir=out / "export", memo_dir=out / "memo")
    return out, pk.collect(suite, out), access


def cases() -> list[dict]:
    return json.loads((SUITE / "questions.json").read_text())["cases"]


def test_every_case_has_a_packet_and_reports_blocked_without_an_answer(run) -> None:
    out, res, _ = run
    assert len(res["results"]) == len(cases()) and all((out / c["test_id"] / "task.md").exists() for c in cases())
    assert {r["status"] for r in res["results"]} == {il.BLOCKED}
    assert {r["reason"] for r in res["results"]} == {"no answer file was written"}
    assert res["answers"]["files"] == 0


def test_a_packet_holds_only_its_cases_pages_and_no_label(run) -> None:
    out, _, _ = run
    for c in cases():
        have = {p.stem for p in (out / c["test_id"] / "excerpts").glob("*.txt")}
        assert have == set(c["frozen_excerpt_ids"]), c["test_id"]
        text = (out / c["test_id"] / "task.md").read_text(encoding="utf-8").lower()
        assert "development_split" not in text and "validation_candidate" not in text
        fx = out / c["test_id"] / "fixture_inputs.json"
        if fx.exists():
            body = json.loads(fx.read_text())
            assert "development_split" not in body and "execution_mode" not in body


def test_the_runner_read_only_the_suite_and_the_packets(run) -> None:
    _, res, access = run
    roots = [Path(r) for r in res["access"]["roots"]]
    files = [Path(f["path"]) for f in res["access"]["files_read"]]
    assert files and all(any(f.is_relative_to(r) for r in roots) for f in files)
    assert not any("holdout" in part for f in files for part in f.parts)
    assert not access.allowed(DATA_DIR / "holdout")


def test_the_modules_do_not_name_the_answer_key() -> None:
    for mod in (il, pk):
        text = Path(mod.__file__).read_text(encoding="utf-8").lower()
        assert "holdout" not in text and "answer_key" not in text
