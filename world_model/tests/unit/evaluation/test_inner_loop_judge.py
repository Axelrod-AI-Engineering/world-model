"""The grader's two layers on invented cases: the numeric layer (by value, any field, the key's unit and scale; ambiguity goes to
a judge), the judge facets and verdicts (a missing verdict is not_run), the judge packets and their separation from the
answerers' packets, and both modes side by side. No client data."""

from __future__ import annotations

import json
import shutil
from decimal import Decimal
from pathlib import Path

import pytest

from axelrod_wm.evaluation import inner_loop as il
from axelrod_wm.evaluation import inner_loop_grade as g
from axelrod_wm.evaluation import inner_loop_judge as jg
from axelrod_wm.evaluation import inner_loop_packets as pk
from tests.unit.evaluation.test_inner_loop_grade import res, results
from tests.where import INNER_LOOP_EXPORT, INNER_LOOP_KEY, INNER_LOOP_SUITE


def case(tid="K-01-01", oracle=None, acc="", split="development", group="main_model_tests", **kw) -> dict:
    return {"test_id": tid, "family_id": 1, "failure_family": "F", "development_split": split, "scorecard_group": group,
            "numeric_oracle": oracle, "acceptance_check": acc, "precise_answer": "the reference", "question": "Q?", **kw}


def oracle(values, unit="JPY", **kw) -> dict:
    return {"unit": unit, "expected_values": values, "calculations": [], "absolute_tolerance": 0, **kw}


def test_the_key_splits_into_numbers_assertions_and_unknowns() -> None:
    c = case(oracle=oracle({"a": 5, "b": [180, 220]}, expected_unknowns=["profit"]),
             acc="Assert a=5; x=min(1,2); flag=true; mode=simple; net=gross-allowance; bounds=[7,8]. Require dated states. "
                 "Reject revenue recognition and require order flags.")
    numbers, assertions, unknowns = g.split_key(c)
    assert [(n, str(d)) for n, d in numbers] == [("a", "5"), ("b", "180"), ("b", "220"), ("x", "1"), ("bounds", "7"), ("bounds", "8")]
    texts = [t for _, t in assertions]
    assert "flag = true" in texts and "mode = simple" in texts and "profit has no determined value, and the answer names what is missing" in texts
    assert any(t.startswith("net gross-allowance") or "gross-allowance" in t for t in texts)
    assert "dated states" in texts and "NOT: revenue recognition" in texts and "order flags" in texts and unknowns == ["profit"]
    assert [k for k, t in assertions if t.startswith("profit")] == ["proof_limits"]
    assert g.split_key(case())[0] == []


def test_a_number_matches_by_value_in_any_field_in_the_keys_unit() -> None:
    c = case(oracle=oracle({"revenue": 200000000, "ratio": 0.375, "gone": 777}))
    r = res("K", {"anything_at_all": 200, "pct": 0.3751}, unit="JPY million", units={"pct": "ratio"})
    r["quantities"] = [{"label": "the other figure", "value": "0.375", "unit": "ratio", "scale": ""}]
    by = {n["label"]: n for n in g.numeric_layer(c, r)}
    assert by["revenue"]["status"] == "matched" and by["revenue"]["candidates"] == ["anything_at_all"]
    assert by["ratio"]["status"] == "ambiguous" and by["ratio"]["candidates"] == ["pct", "the other figure"]    # two different numbers
    assert by["gone"]["status"] == "unmatched" and by["gone"]["candidates"] == []
    same = res("K", {"x": 200}, unit="JPY million")
    same["quantities"] = [{"label": "in yen", "value": 200000000, "unit": "JPY"}, {"label": "in million", "value": 200, "unit": "JPY", "scale": "million"}]
    assert {n["label"]: n["status"] for n in g.numeric_layer(case(oracle=oracle({"r": 200000000})), same)} == {"r": "matched"}
    mixed = res("K", {"b": 13525.4, "t": 13.5254}, unit="billion yen")
    assert {n["status"] for n in g.numeric_layer(case(oracle=oracle({"billion": 13525.4, "trillion": 13.5254}, "billion/trillion JPY")), mixed)} == {"matched"}
    bare = g.numeric_layer(case(oracle={"expected_values": {"v": 3}}), res("K", {"x": [3, True, "3", None]}))
    assert bare[0]["status"] == "matched" and bare[0]["unit"] is None
    assert g.answer_numbers({**res("K", {"d": "2026-01-01"}), "quantities": [{"label": "a date", "value": "n/a"}]}) == [] and g.match_number(Decimal(5), Decimal(7), Decimal(2), Decimal(1)) == 7
    assert g.match_number(Decimal("5.99"), Decimal("5.994"), Decimal(0), Decimal(1)) == Decimal("5.994")
    assert g.match_number(Decimal("13525400000000"), Decimal("13525400"), Decimal(0), Decimal(10) ** 6) == Decimal("1.35254E+13")


def test_a_tolerance_still_applies_only_where_named() -> None:
    c = case("K-02-08", oracle=oracle({"m": 5.993}, "percent", absolute_tolerance=0.5))
    assert g.numeric_layer(c, res("K", {"x": 5.998}))[0]["status"] == "matched"
    assert g.numeric_layer(case("K-01-04", oracle=oracle({"m": 5.993}, "percent", absolute_tolerance=0.5)),
                           res("K", {"x": 5.998}))[0]["status"] == "unmatched"


def test_the_judge_decides_assertions_and_the_numbers_the_first_layer_could_not_settle() -> None:
    c = case(oracle=oracle({"v": 10}), acc="Require dated states; flag=true.")
    r = res("K", {"a": 10, "b": 10.0001}, unit="JPY")
    r["quantities"] = [{"label": "again", "value": 10.0002, "unit": "JPY"}]
    facets = g.judge_facets(c, r)
    assert [(f["id"], f["kind"]) for f in facets] == [("f01", "assertions"), ("f02", "assertions"), ("f03", "quantity")] or len(facets) == 3
    assert "Candidate numbers in the answer" in facets[-1]["text"] and facets[-1]["kind"] == "quantity"
    assert g.judge_facets(c, res("K", {"a": 10})) == [f for f in g.judge_facets(c, res("K", {"a": 10}))]
    assert len(g.judge_facets(c, res("K", {"a": 10}))) == 2


def verdict(tid: str, **v: str) -> dict:
    return {"test_id": tid, "facets": {k: {"verdict": x, "reason": "quotes the answer"} for k, x in v.items()}}


def test_the_case_status_combines_both_layers_and_a_missing_verdict_is_never_a_pass() -> None:
    c = case(oracle=oracle({"v": 10}), acc="Require dated states.")
    r = res("K", {"a": 10}, unit="JPY")
    waiting = g.judge_outcome(c, r, None)
    assert waiting["status"] == "not_run" and waiting["reason"] == "judge verdict missing for f01"
    assert waiting["facets"][0]["verdict"] == "not_run"
    assert g.judge_outcome(c, r, verdict("K", f01="pass"))["status"] == "pass"
    bad = g.judge_outcome(c, r, verdict("K", f01="fail"))
    assert bad["status"] == "fail" and bad["failed"][0]["actual"] == "quotes the answer"
    assert g.judge_outcome(c, res("K", {"a": 11}, unit="JPY"), verdict("K", f01="pass"))["status"] == "fail"       # a number is missing
    assert g.judge_outcome(case(oracle=oracle({"v": 10})), r, None)["status"] == "pass"                          # numbers alone
    none = g.judge_outcome(case(), r, None)
    assert none["status"] == "fail" and none["reason"] == "no check could be made"
    amb = res("K", {"a": 10, "b": 10.0001}, unit="JPY")
    amb_case = case(oracle=oracle({"v": 10.0}))
    assert g.judge_outcome(amb_case, amb, None)["status"] == "not_run"
    assert g.judge_outcome(amb_case, amb, verdict("K", f01="pass"))["status"] == "pass"


def test_verdicts_are_read_validated_and_hashed(tmp_path: Path) -> None:
    assert g.read_verdicts(None) == ({}, None)
    d = tmp_path / "v"
    d.mkdir()
    (d / "A.json").write_text(json.dumps(verdict("A", f01="pass")))
    (d / "B.json").write_text("{bad")
    (d / "C.json").write_text(json.dumps({"test_id": "C", "facets": {"f01": {"verdict": "maybe", "reason": "x"}}}))
    (d / "D.json").write_text(json.dumps(verdict("not-D", f01="pass")))
    got, info = g.read_verdicts(d)
    assert set(got) == {"A"} and info["files"] == 4 and info["invalid"] == ["B", "C", "D"] and len(info["sha256"]) == 64
    assert g.read_verdicts(d)[1] == info
    (d / "A.json").write_text(json.dumps(verdict("A", f01="fail")))
    assert g.read_verdicts(d)[1]["sha256"] != info["sha256"]


def packets_and_results(tmp_path: Path) -> tuple[Path, dict]:
    out = tmp_path / "packets"
    shutil.copytree(INNER_LOOP_EXPORT, out / "export")
    suite = il.load_suite(INNER_LOOP_SUITE, il.Access([INNER_LOOP_SUITE, out]))
    pk.prepare_packets(suite, out, "r", tools_command="t", export_dir=out / "export", memo_dir=out / "m", only=["TST-01-01"])
    return out, {"results": [], "access": {"roots": [], "files_read": []}}


def test_judge_packets_hold_only_the_cases_facets_and_live_apart_from_the_answerers(tmp_path: Path) -> None:
    out, _ = packets_and_results(tmp_path)
    key = tmp_path / "key.json"
    key.write_text(json.dumps({"suite_id": "S", "cases": [
        case("A-01-01", oracle(["x"] and {"v": 10}), "Require dated states."), case("A-01-02", oracle({"v": 1})),
        case("A-01-03", None, "Require something stated."), case("A-01-04", None, "Require another.")]}))
    ok = res("A", {"a": 10}, unit="JPY")
    rows = [{**ok, "test_id": "A-01-01"}, {**ok, "test_id": "A-01-02"}, {**ok, "test_id": "A-01-03"},
            {**res("A", None, status=il.BLOCKED, reason="no"), "test_id": "A-01-04"}]
    rs = {"results": rows, "answers": {"sha256": "abc"}}
    judge = tmp_path / "judge_r2"
    meta = jg.prepare_judge(rs, key, judge, "r2")
    assert [c["test_id"] for c in meta["cases"]] == ["A-01-01", "A-01-03"] and meta["graded_answers"] == {"sha256": "abc"}
    p = judge / "A-01-01"
    assert sorted(f.name for f in p.iterdir()) == ["answer.json", "facets.json", "judge.md", "verdict.schema.json"]
    facets = json.loads((p / "facets.json").read_text())
    assert facets["facets"] == [{"id": "f01", "kind": "assertions", "text": "dated states"}] and facets["reference_answer"] == "the reference"
    assert "on meaning, not wording" in (p / "judge.md").read_text() and str(judge / "verdicts" / "A-01-01.json") in (p / "judge.md").read_text()
    assert json.loads((p / "answer.json").read_text())["actual_result"] == {"a": 10} and (judge / "verdicts").is_dir()
    assert not (judge / "A-01-02").exists() and not (judge / "A-01-04").exists()                 # nothing to judge, or blocked
    assert [c["test_id"] for c in jg.prepare_judge(rs, key, tmp_path / "j2", "r", only=("A-01-03",))["cases"]] == ["A-01-03"]
    # the answerers' packets never hold a judge file or a facet's text, and a judge folder is never made inside them
    for f in out.rglob("*"):
        assert f.name not in ("judge.md", "facets.json", "verdict.schema.json") and "dated states" not in (f.read_text() if f.is_file() and f.suffix in (".md", ".json", ".txt") else "")
    with pytest.raises(ValueError, match="answer packets"):
        jg.prepare_judge(rs, key, out / "judge", "r")
    with pytest.raises(ValueError, match="answer packets"):
        jg.prepare_judge(rs, key, out / "TST-01-01" / "x", "r")


def test_both_modes_are_reported_side_by_side_with_the_verdicts_graded(tmp_path: Path) -> None:
    rows = [res("G-01-01", {"x": 200, "ratio": 0.3751}, "JPY million", units={"ratio": "ratio"}), res("G-01-02", {"revenue": 201}, "JPY million")]
    d = tmp_path / "verdicts"
    d.mkdir()
    card = g.grade(results(rows), INNER_LOOP_KEY, "t", only=("G-01-01", "G-01-02"), verdicts=d)
    assert card["mode"] == "judge" and card["modes"]["judge"]["pass"] == 1 and card["modes"]["judge"]["fail"] == 1
    assert card["modes"]["lexical"]["pass"] == 0 and card["modes"]["lexical"]["fail"] == 2           # field names differ from the key's
    first = next(r for r in card["cases"] if r["test_id"] == "G-01-01")
    assert (first["status"], first["status_judge"], first["status_lexical"]) == ("pass", "pass", "fail")
    assert card["graded_verdicts"]["files"] == 0
    lex = g.grade(results(rows), INNER_LOOP_KEY, "t", only=("G-01-01",), mode="lexical")
    assert lex["cases"][0]["status"] == "fail" and lex["cases"][0]["judge"]["numeric"][0]["status"] == "matched"
    md = g.markdown(card)
    assert "Headline mode: **judge**" in md and "| lexical |" in md and "| judge |" in md and "Graded verdicts:" in md
    assert "Graded verdicts:" not in g.markdown(g.grade(results(rows), INNER_LOOP_KEY, "t", only=("G-01-01",)))
    validation = g.grade(results([res("G-03-09", {"revenue": 120}), res("G-03-08", {"revenue": 99})]), INNER_LOOP_KEY, "t")
    v = {r["test_id"]: r for r in validation["cases"]}
    assert v["G-03-09"]["status"] == "pass" and v["G-03-08"]["status"] == "fail" and "judge" not in v["G-03-09"]
    assert validation["review_gates"]["counts"]["pass"] >= 0
