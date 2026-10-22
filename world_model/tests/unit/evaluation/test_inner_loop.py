"""The inner-loop suite's shared parts on an invented suite (tests/fixtures/inner_loop): the read guard and its log, the suite and
its frozen pages, the calculator, the number and date readers, and the contract. No client data."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from axelrod_wm.evaluation import inner_loop as il
from tests.where import INNER_LOOP_SUITE, SRC


def test_the_suite_is_questions_fixtures_and_a_source_index() -> None:
    s = il.load_suite(INNER_LOOP_SUITE)
    assert s.meta["suite_id"] == "SYNTHETIC-1" and [c["test_id"] for c in s.cases][:2] == ["TST-01-01", "TST-01-02"]
    assert s.fixtures["TST-01-02"]["fixture_inputs"]["price"] == 12 and s.excerpt("T-001")["source_id"] == "T"
    assert s.excerpt("nope") is None


def test_a_frozen_page_is_read_against_the_hash_the_index_froze() -> None:
    s = il.load_suite(INNER_LOOP_SUITE)
    assert "SYNTHETIC REPORT" in s.excerpt_text("T-001") and s.excerpt_text("T-001") is s.excerpt_text("T-001")
    for eid, why in (("T-003", "differs from the hash"), ("T-004", "not in the suite folder"), ("T-009", "not in the source index")):
        with pytest.raises(il.Blocked, match=why):
            s.excerpt_text(eid)


def test_the_run_reads_only_what_it_is_given_and_logs_it(tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere.json"
    outside.write_text("{}")
    access = il.Access([INNER_LOOP_SUITE])
    with pytest.raises(il.AccessDenied):
        access.read_text(outside)
    assert not access.allowed(outside) and access.allowed(INNER_LOOP_SUITE / "questions.json")
    s = il.load_suite(INNER_LOOP_SUITE, access)
    s.excerpt_text("T-001")
    rep = access.report()
    names = {Path(f["path"]).name for f in rep["files_read"]}
    assert {"questions.json", "fixture_inputs.json", "source_index.json", "T-001.txt"} <= names
    assert all(len(f["sha256"]) == 64 for f in rep["files_read"]) and rep["roots"] == [str(INNER_LOOP_SUITE.resolve())]


def test_the_modules_on_the_runner_side_never_name_the_answer_key() -> None:
    for name in ("inner_loop", "inner_loop_packets", "inner_loop_tools"):
        text = (SRC / "evaluation" / f"{name}.py").read_text(encoding="utf-8").lower()
        for word in ("holdout", "answer_key", "answer-key"):
            assert word not in text, (name, word)


def test_numbers_dates_and_values_are_read_as_the_page_prints_them() -> None:
    assert il.parse_number("1,063,473") == Decimal(1063473)
    assert il.parse_number("(285,617)") == Decimal(-285617)
    assert il.parse_number("−40.5") == Decimal("-40.5")
    assert il.parse_date("April 1, 2026") == date(2026, 4, 1) and il.parse_date("2026-04-01") == date(2026, 4, 1)
    with pytest.raises(il.Blocked, match="not a date"):
        il.parse_date("Unit Z")
    assert il.plain(Decimal("2.50")) == 2.5 and il.plain(Decimal("3")) == 3
    assert il.plain({"a": [Decimal(1), date(2026, 1, 2)]}) == {"a": [1, "2026-01-02"]}
    assert il.as_value(True) is True and il.as_value("x") == "x" and il.as_value(2) == Decimal(2)


def test_the_calculator_functions_and_operators() -> None:
    env = {"a": Decimal("3.5"), "b": Decimal(-2)}
    ev = lambda x: il.evaluate(x, env)                                           # noqa: E731
    assert (ev("min(a, 9)"), ev("max(a, b)"), ev("abs(b)"), ev("sum(a, b, 1)")) == (Decimal("3.5"), Decimal("3.5"), 2, Decimal("2.5"))
    assert ev("round(a * 3, 1)") == Decimal("10.5") and ev("round(a)") == 4 and ev("[a, b]") == [Decimal("3.5"), Decimal(-2)]
    assert ev("(a, b)") == [Decimal("3.5"), Decimal(-2)]
    assert ev("not (a < b)") is True and ev("1 < a < 9") is True and ev("1 < a < 2") is False
    assert ev("a > 1 and b < 0") is True and ev("a < 1 or b < 0") is True and ev("5 if a > 3 else 6") == 5 and ev("5 if a > 4 else 6") == 6
    assert (ev("+b"), ev("7 // 2"), ev("7 % 4"), ev("2 ** 3")) == (-2, 3, 3, 8)
    assert ev("a != b") and ev("a == a") and ev("a >= 3.5") and ev("a <= 3.5") and ev("a > b")
    assert il.evaluate("d > e", {"d": date(2026, 8, 4), "e": date(2026, 7, 31)}) is True


def test_what_the_calculator_cannot_do_is_blocked_with_the_reason() -> None:
    for expr, why in (("1 / 0", "DivisionByZero"), ("0 / 0", "InvalidOperation"), ("1 +", "cannot read the expression"),
                      ("nobody + 1", "nobody"), ("__import__('os')", "does not allow"), ("a.b", "does not allow")):
        with pytest.raises(il.Blocked, match=why):
            il.evaluate(expr, {"a": Decimal(1)})


def test_the_contract_keeps_our_fields_and_maps_the_suites() -> None:
    case = {"test_id": "X-01-01", "failure_family": "F", "scorecard_group": "main_model_tests"}
    internal = {"answer": {"v": 1}, "scope": {"unit": "u"}, "quantities": [{"label": "l", "value": 1}], "baseline": il.na("none")}
    r = il.to_contract(case, il.ANSWERED, internal, "", il.CONTRACT_FIELDS)
    assert r["actual_result"] == {"v": 1} and r["scope_period_units_when_applicable"] == {"unit": "u"}
    assert r["selected_baseline_scenario_version_when_applicable"] == {"applicable": False, "reason": "none"}
    assert r["internal"] is internal and r["quantities"] == internal["quantities"] and r["family"] == "F"
    assert r["calculation_trace_when_applicable"] == {"applicable": False, "reason": "not answered"}
    few = il.to_contract(case, il.BLOCKED, None, "no source", ("test_id", "actual_result"))
    assert set(few) >= {"test_id", "status", "actual_result", "internal"} and "scope_period_units_when_applicable" not in few
    assert few["actual_result"] == {"applicable": False, "reason": "no source"} and few["quantities"] == []
    assert il.FIELD_MAP["actual_result"] == "answer"


def test_results_serialize_to_the_same_bytes() -> None:
    text = il.dumps({"b": 1, "a": [1, {"d": 2, "c": 3}]})
    assert text == il.dumps({"a": [1, {"c": 3, "d": 2}], "b": 1}) and text.endswith("\n") and json.loads(text)["a"][0] == 1
