"""The inner-loop suite against the real Toyota world, end to end (client data: skipped when it is absent).

It asserts that the run completes, that every case reports one of the statuses the scorecard knows, and that the
answer-key separation holds (what the runner read, and what the grader's evidence says). It does not assert a pass rate:
the suite measures the model, and a release decision is not a test."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.clients import DATA_DIR
from axelrod_wm.evaluation import inner_loop as il
from axelrod_wm.evaluation.golden import V1Reader
from axelrod_wm.repo.snapshots import MemoryBackend
from tests.clients import skip_without_client

skip_without_client("sally_demo")
SUITE = DATA_DIR / "clients" / "sally" / "inner_loop_v1_1"
RECIPES = sorted((DATA_DIR / "work" / "sally" / "inner_loop").glob("recipes*.yaml"))
if not (SUITE / "questions.json").exists() or not RECIPES:
    pytest.skip("the inner-loop suite or its recipes are absent (data/ is local and gitignored)", allow_module_level=True)


@pytest.fixture(scope="module")
def run() -> tuple[dict, il.Access]:
    logging.disable(logging.INFO)
    access = il.Access([SUITE, *{r.parent for r in RECIPES}])
    suite = il.load_suite(SUITE, access)
    recipes = {k: v for r in RECIPES for k, v in il.load_recipes(r, access).items()}
    with TestClient(create_app(scenario="sally_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)) as c:
        out = il.run_suite(suite, recipes, V1Reader(c))
    return out, access


def test_every_case_is_reported_with_a_status_and_a_reason(run) -> None:
    out, _ = run
    assert len(out["results"]) == 100
    assert {r["status"] for r in out["results"]} <= {il.ANSWERED, il.BLOCKED, il.NOT_RUN}
    assert all(r["reason"] for r in out["results"] if r["status"] != il.ANSWERED)
    assert sum(r["scorecard_group"] == "review_gate" for r in out["results"]) == 2


def test_the_runner_read_only_the_suite_and_the_recipes(run) -> None:
    out, access = run
    roots = [Path(r) for r in out["access"]["roots"]]
    files = [Path(f["path"]) for f in out["access"]["files_read"]]
    assert files and all(any(f.is_relative_to(r) for r in roots) for f in files)
    assert not any("holdout" in part for f in files for part in f.parts)
    assert not any("holdout" in part for r in roots for part in r.parts)
    assert not access.allowed(DATA_DIR / "holdout" / "sally" / "inner_loop_v1_1" / "answer_key.json")


def test_the_runner_module_does_not_name_the_answer_key() -> None:
    text = Path(il.__file__).read_text(encoding="utf-8").lower()
    assert "holdout" not in text and "answer_key" not in text
