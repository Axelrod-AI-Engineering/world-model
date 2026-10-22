"""The inner-loop grader on an invented key (tests/fixtures/inner_loop_key): values at displayed precision, the named
tolerances only, assertions by facet, unknowns, prose directives, statuses and rates, the review section, the
withheld detail of validation candidates, and the separation evidence. No client data."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from axelrod_wm.evaluation import inner_loop as il
from axelrod_wm.evaluation import inner_loop_grade as g
from tests.where import INNER_LOOP_KEY, INNER_LOOP_SUITE


def res(tid: str, answer: dict | None = None, unit: str | None = None, units: dict | None = None,
        status: str = il.ANSWERED, reason: str = "", trace: list | None = None) -> dict:
    scope = {k: v for k, v in (("unit", unit), ("units", units)) if v}
    return {"test_id": tid, "status": status, "reason": reason, "actual_result": answer,
            "scope_period_units_when_applicable": scope, "calculation_trace_when_applicable": trace or [],
            "internal": {"grounding": {"operation": "calc", "model_objects": ["a"], "source_excerpts": [], "stated": ["x"]}}}


def results(rows: list[dict], files: list[str] | None = None, roots: list[str] | None = None) -> dict:
    return {"results": rows, "access": {"roots": roots or [str(INNER_LOOP_SUITE)],
                                        "files_read": [{"path": f, "sha256": "0" * 64} for f in (files or [])]}}


GOOD_FACTS = {"dated_readiness_states": "announced then commissioned", "invented_margin": None,
              "revenue_recognition": False, "order_flags": "duplicates flagged", "unit_scale": 1000,
              "audit_trail": "kept"}
ROWS = [
    res("G-01-01", {"revenue": 200, "ratio": 0.3751}, "JPY million", units={"ratio": "ratio"}),
    res("G-01-02", {"revenue": 201}, "JPY million"),
    res("G-01-03", {"total": 11}, "JPY million"),
    res("G-01-04", {"margin": 5.998}, "percent"),
    res("G-01-05", {"unrelated": 1}),
    res("G-01-06", {"delivered": 105, "income": 14, "coefficient": None, "flag": True, "mode": "simple mode",
                    "bounds": [180, 220], "net": 970}, units={"delivered": "vehicles"}, unit="JPY million",
        trace=[{"name": "net", "expression": "gross - allowance", "inputs": {"gross": 1000, "allowance": 30},
                "value": 970}]),
    res("G-01-07", {"economic_net": 40, "reported_profit_delta": "undetermined", "unresolved": ["accounting"]}),
    res("G-01-08", {"economic_net": 40, "reported_profit_delta": 0, "unresolved": ["accounting"]}),
    res("G-01-09", GOOD_FACTS),
    res("G-01-10", {**GOOD_FACTS, "invented_margin": 5}),
    res("G-01-11", {"anything": 1}),
    res("G-02-01", GOOD_FACTS),
    res("G-02-03", None, status=il.BLOCKED, reason="the source page is missing"),
    res("G-02-04", None, status=il.NOT_RUN, reason="told to skip"),
    res("G-02-08", {"margin": 5.998}, "percent"),
    res("G-02-09", {"flag": True, "stated_words": "some"}),
    res("G-03-09", {"revenue": 120}),
    res("G-03-08", {"revenue": 99}),
    res("G-03-10", {"revenue": 120}),
]
STATUS = {"G-01-01": "pass", "G-01-02": "fail", "G-01-03": "pass", "G-01-04": "fail", "G-01-05": "fail",
          "G-01-06": "pass", "G-01-07": "pass", "G-01-08": "fail", "G-01-09": "pass", "G-01-10": "fail",
          "G-01-11": "fail", "G-02-01": "pass", "G-02-02": "not_run", "G-02-03": "blocked", "G-02-04": "not_run",
          "G-02-08": "pass", "G-02-09": "pass"}


@pytest.fixture(scope="module")
def card() -> dict:
    return g.grade(results(ROWS), INNER_LOOP_KEY, "t1", mode="lexical")


def row(card: dict, tid: str) -> dict:
    return next(r for r in [*card["cases"], *card["review_gates"]["cases"]] if r["test_id"] == tid)


@pytest.mark.parametrize("tid,status", sorted(STATUS.items()))
def test_each_case_has_the_status_its_checks_give(card, tid, status) -> None:
    assert row(card, tid)["status"] == status, row(card, tid)["reason"]


def test_values_are_matched_at_displayed_precision_and_in_the_keys_unit(card) -> None:
    assert row(card, "G-01-01")["facets"]["values"] == {"checked": 2, "failed": 0}
    assert [d["label"] for d in row(card, "G-01-02")["detail"]] == ["revenue"]
    assert row(card, "G-01-02")["detail"][0]["actual"] == 201


def test_a_tolerance_is_kept_only_where_the_clarifications_name_one(card) -> None:
    assert row(card, "G-01-03")["status"] == "pass"               # one million yen on a rounding residual
    assert row(card, "G-01-04")["status"] == "fail"               # 0.5 is not a named tolerance for this case
    assert row(card, "G-02-08")["status"] == "pass"               # 0.005 percentage point for the margin case
    assert g.tolerance({"test_id": "X-02-08"}, {"absolute_tolerance": 0.5, "unit": "percent"}) == Decimal("0.005")
    assert g.tolerance({"test_id": "X"}, {"absolute_tolerance": 7, "unit": "JPY million"}) == Decimal(1)
    assert g.tolerance({"test_id": "X"}, {"absolute_tolerance": 7, "unit": "JPY"}) == Decimal(0)
    assert g.tolerance({"test_id": "X"}, {}) == Decimal(0)


def test_a_missing_field_fails_with_what_was_expected(card) -> None:
    d = row(card, "G-01-05")["detail"]
    assert d == [{"facet": "values", "label": "missing_one", "expected": 1, "actual": None}]


def test_assertions_may_be_expressions_flags_nulls_words_lists_and_formulas(card) -> None:
    r = row(card, "G-01-06")
    assert r["facets"]["assertions"]["failed"] == 0 and r["facets"]["assertions"]["checked"] >= 7
    pairs, rest = g.scan_pairs("Assert a=min(1,2) and b=3*4=12; c=[1,2], d=x. Done.")
    assert pairs == [("a", "min(1,2)"), ("b", "12"), ("c", "[1,2]"), ("d", "x")] and "Done" in rest
    assert g.expected_of("min(110,105)") == 105 and g.expected_of("null") is None and g.expected_of("TRUE") is True
    assert g.scan_pairs("Assert x=f(a=1) now.")[0] == [("x", "f(a=1)")]
    assert g.expected_of("[1,2]") == [1, 2] and g.expected_of("word") == "word"


def test_an_expected_unknown_must_be_a_non_number_with_its_inputs_named(card) -> None:
    assert row(card, "G-01-07")["facets"]["proof_limits"] == {"checked": 1, "failed": 0}
    bad = row(card, "G-01-08")["detail"][0]
    assert bad["facet"] == "proof_limits" and bad["actual"] == 0


def test_prose_directives_need_their_statements_and_negatives_need_a_no(card) -> None:
    assert row(card, "G-01-09")["status"] == "pass"
    bad = row(card, "G-01-10")
    assert bad["status"] == "fail" and any(d["label"].startswith("not ") for d in bad["detail"])
    assert g.clauses("Assert the narrative. Keep this. Reject revenue recognition and require order flags.") == [
        ({"narra"}, False), ({"reven", "recog"}, True), ({"order", "flags"}, False)]
    assert g.clauses("No invented margin; Preserve audit now") == [({"inven", "margi"}, True), ({"audit", "now"}, False)]
    assert g.negative(None) and g.negative(False) and g.negative("none yet") and not g.negative(5) and not g.negative("yes")


def test_a_case_with_nothing_the_key_can_check_fails_rather_than_passes(card) -> None:
    r = row(card, "G-01-11")
    assert r["status"] == "fail" and r["reason"] == "no check could be made"


def test_blocked_not_run_and_unreported_cases_keep_their_reasons(card) -> None:
    assert row(card, "G-02-03")["reason"] == "the source page is missing"
    assert row(card, "G-02-04")["reason"] == "told to skip"
    assert row(card, "G-02-02")["reason"] == "the runner did not report it"


def test_validation_candidates_show_status_only(card) -> None:
    ok, bad = row(card, "G-03-09"), row(card, "G-03-08")
    assert (ok["status"], bad["status"]) == ("pass", "fail")
    for r in (ok, bad):
        assert r["reason"] == "validation candidate: detail withheld" and "detail" not in r and "key_text" not in r
    assert "key_text" in row(card, "G-01-02") and row(card, "G-01-01")["grounding"]["operation"] == "calc"


def test_the_rates_follow_the_scorecard_rules(card) -> None:
    m = card["main"]
    assert m["cases"] == 19 and m["pass"] + m["fail"] + m["blocked"] + m["not_run"] == 19
    assert m["executed"] == m["pass"] + m["fail"]
    assert m["executed_pass_rate"] == round(m["pass"] / m["executed"], 4)
    assert m["execution_coverage"] == round(m["executed"] / 98, 4)
    assert card["blocked"] == [["G-02-03", "the source page is missing"]] or card["blocked"] == [("G-02-03", "the source page is missing")]
    assert {t for t, _ in card["not_run"]} == {"G-02-02", "G-02-04"}
    assert g.rates([])["executed_pass_rate"] is None
    assert card["note"].startswith("A high executed pass rate does not resolve")
    assert sum(v["cases"] for v in card["by_family"].values()) == 19


def test_the_review_gates_have_their_own_section_and_the_separation_evidence(card) -> None:
    rg = card["review_gates"]
    assert [r["test_id"] for r in rg["cases"]] == ["G-03-10", "G-03-11"]
    assert rg["counts"]["pass"] == 1 and rg["counts"]["not_run"] == 1
    sep = rg["answer_key_separation"]
    assert sep == {"runner_read_files": 0, "runner_read_anything_under_key_folder": False,
                   "runner_roots_exclude_key_folder": True, "runner_source_names_key_location": False,
                   "grader_takes_key_path_as_argument": True, "no_transcript_mentions_the_key": True,
                   "transcripts": {"transcripts_scanned": 0, "transcripts_unreadable": 0,
                                   "mentions": {str(INNER_LOOP_KEY): 0, "answer_key.json": 0}}}
    assert all(r["test_id"] not in {x["test_id"] for x in rg["cases"]} for r in card["cases"])


def test_the_separation_evidence_catches_a_runner_that_read_the_key_folder() -> None:
    key_dir = INNER_LOOP_KEY.parent
    bad = g.separation_evidence(INNER_LOOP_KEY, results([], files=[str(key_dir / "answer_key.json")],
                                                        roots=[str(key_dir.parent)]))
    assert bad["runner_read_anything_under_key_folder"] is True and bad["runner_roots_exclude_key_folder"] is False


def test_matching_our_fields_to_the_keys_labels() -> None:
    f = {"a.net_receivables": 970, "delta": 1, "delta_units": -1000, "gross": 1, "also.gross": 2}
    assert g.find_field("net_receivables", f) == ("a.net_receivables", 970)
    assert g.find_field("net", f) == ("a.net_receivables", 970)
    assert g.find_field("delta", f) == ("delta", 1)                 # the exact name first
    assert g.find_field("gross", f)[1] == 1
    assert g.find_field("units", f) == ("delta_units", -1000)
    assert g.find_field("nothing", f) is None
    assert g.find_field("net", {"net_a": 1, "net_b": 2}) is None    # ambiguity is no match
    assert g.tokens("delta_change") == {"delta", "change"} and g.tokens("net_delta") == {"net"}
    assert g.flatten({"a": {"b": 1}, "c": [1, 2]}) == {"a.b": 1, "c": [1, 2]}


def test_values_compare_numbers_words_flags_lists_and_nulls() -> None:
    assert g.values_match(13.5254, 13.52541) and not g.values_match(13.5254, 13.5255)
    assert g.values_match(5, 5.4) is True and g.values_match(5, "5.4%")
    assert g.values_match(200000000, 200, factor=Decimal(10) ** 6)
    assert g.values_match(1, 2, tol=Decimal(1)) and not g.values_match(1, 3, tol=Decimal(1))
    assert g.values_match("thousand", "thousand vehicles") and not g.values_match("thousand", "units")
    assert g.values_match(True, True) and not g.values_match(True, False) and g.values_match("false", False)
    assert g.values_match(None, None) and not g.values_match(None, 0)
    assert g.values_match([1, 2], [1.0, 2]) and not g.values_match([1, 2], [1]) and not g.values_match([1], 1)
    assert not g.values_match("", "x")
    assert g.to_decimal(None) is None and g.to_decimal(True) is None and g.to_decimal("1,234") == 1234
    assert g.to_decimal("abc") is None
    assert g.decimals_of(0.25) == 2 and g.decimals_of(3) == 0
    assert g.unit_scale("billion and trillion JPY") == Decimal(10) ** 9 and g.unit_scale("vehicles") == 1
    assert g.unit_scale(None) == 1 and g.facet_of("accounting destination") == "accounting_destination"
    assert g.facet_of("mechanism") == "mechanism" and g.facet_of("limit") == "proof_limits" and g.facet_of("zzz") == "assertions"


def test_the_clause_check_needs_most_of_the_stems_and_a_negative_needs_a_no() -> None:
    hay = [({"alpha", "beta"}, "text"), ({"gamma"}, False)]
    assert g.clause_ok({"alpha"}, False, hay) and not g.clause_ok({"alpha", "zeta"}, False, hay)
    assert g.clause_ok({"gamma"}, True, hay) and not g.clause_ok({"alpha"}, True, hay)
    assert g.clause_ok({"a", "b", "c", "d", "e"}, False, [({"a", "b", "c"}, 1)])           # 3 of 5
    assert not g.clause_ok({"a", "b", "c", "d", "e"}, False, [({"a", "b"}, 1)])
    assert not g.clause_ok({"a"}, False, [])
    assert g.stems("The 2026-04-01 for2026 audit") == {"2026", "audit"}


def test_the_markdown_scorecard_lists_every_part(card) -> None:
    md = g.markdown(card)
    for part in ("## Main scorecard", "## By family", "## Cases", "## Review checks (10-09 and 10-10), scored separately",
                 "Answer-key separation, by evidence:", "does not resolve a material blocked"):
        assert part in md
    assert "n/a" in g.markdown({**card, "main": {**card["main"], "executed_pass_rate": None}})
    assert md == g.markdown(card) and md.endswith("\n")
    no_sep = {k: v for k, v in card["review_gates"].items() if k != "answer_key_separation"}
    assert "Answer-key separation" not in g.markdown({**card, "review_gates": no_sep})


def test_grading_is_deterministic_and_takes_the_key_path_only_as_an_argument(tmp_path: Path) -> None:
    key_copy = tmp_path / "somewhere" / "key.json"
    key_copy.parent.mkdir()
    key_copy.write_text(INNER_LOOP_KEY.read_text(encoding="utf-8"), encoding="utf-8")
    a = json.dumps(g.grade(results(ROWS), key_copy, "r"), sort_keys=True)
    b = json.dumps(g.grade(results(ROWS), INNER_LOOP_KEY, "r"), sort_keys=True)
    assert a.replace(str(tmp_path), "") != "" and json.loads(a)["main"] == json.loads(b)["main"]


def test_a_calculation_may_have_the_answer_shape_or_the_recipe_shape() -> None:
    answer_shape = [{"expression": "gross - allowance", "inputs": {"gross": 1000, "allowance": 30}, "value": 970}]
    recipe_shape = [{"name": "net", "expression": "gross - allowance", "inputs": {"gross": 1000, "allowance": 30}, "value": 970}]
    for trace in (answer_shape, recipe_shape, [{"expression": "x", "value": 1}]):
        hay = g.haystack(res("G", {"a": 1}, trace=trace), {"a": 1})
        assert hay[-1][1] == trace[0]["value"]
    assert {"gross", "allow"} <= g.haystack(res("G", {"a": 1}, trace=answer_shape), {"a": 1})[-1][0]
    card = g.grade(results([res("G-01-06", {"delivered": 105, "income": 14, "coefficient": None, "flag": True,
                                            "mode": "simple mode", "bounds": [180, 220]}, trace=answer_shape)]),
                   INNER_LOOP_KEY, "t", only=("G-01-06",), mode="lexical")
    assert row(card, "G-01-06")["status"] in ("pass", "fail")           # graded, not crashed


def test_only_leaves_the_other_cases_out_rather_than_counting_them() -> None:
    card = g.grade(results(ROWS), INNER_LOOP_KEY, "t", only=("G-01-01", "G-01-02", "G-03-10"), mode="lexical")
    assert [r["test_id"] for r in card["cases"]] == ["G-01-01", "G-01-02"]
    assert card["main"]["cases"] == 2 and card["main"]["not_run"] == 0 and card["main"]["blocked"] == 0
    assert [r["test_id"] for r in card["review_gates"]["cases"]] == ["G-03-10"] and card["only"] == ["G-01-01", "G-01-02", "G-03-10"]
    assert g.grade(results(ROWS), INNER_LOOP_KEY, "t")["only"] is None


def test_a_key_unit_that_mixes_scales_is_compared_in_each_fields_own_scale() -> None:
    assert g.mixed_scales("billion/trillion JPY") and not g.mixed_scales("JPY million") and not g.mixed_scales(None)
    case = {"test_id": "X-01-05", "numeric_oracle": {"unit": "billion/trillion JPY", "absolute_tolerance": 0,
                                                     "expected_values": {"billion": 13525.4, "trillion": 13.5254}}}
    r = res("X", {"value_billion_yen": 13525.4, "value_trillion_yen": 13.5254}, units={"value_billion_yen": "billion yen",
                                                                                     "value_trillion_yen": "trillion yen"})
    ok, facets, _ = g.check_case({**case, "acceptance_check": ""}, r)
    assert ok and facets["values"] == {"checked": 2, "failed": 0}
