"""The inner-loop runner on an invented suite (tests/fixtures/inner_loop): every operation, every way a case is blocked,
the contract's fields, the separation guard, and determinism. No client data."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from axelrod_wm.evaluation import inner_loop as il
from tests.where import INNER_LOOP_SUITE, SRC


class FakeReader:
    """A world with one composition that has a residual and eliminations, and one that has neither."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def construction(self, entity_id: str) -> dict:
        self.calls.append(entity_id)
        return {"attributes": [{"id": "attr.a"}], "identities": [{"id": "id.x"}], "paths": [{"id": "path.p"}],
                "compositions": [
                    {"id": "c.seg", "role": "driving", "total_attribute_id": "attr.total",
                     "member_attribute_ids": ["attr.a", "attr.b"], "residual_attribute_id": "attr.r",
                     "eliminations_attribute_id": "attr.e"},
                    {"id": "c.plain", "total_attribute_id": "attr.total", "member_attribute_ids": ["attr.a", "attr.b"],
                     "residual_attribute_id": None, "eliminations_attribute_id": None}]}


class FakeService:
    """The intake side of a clean world: it dedups identical bytes, as the real one does."""

    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}

    def upload(self, name: str, data: bytes) -> dict:
        key = str(hash(data))
        self.docs.setdefault(key, {"id": f"doc-{len(self.docs)}", "name": name})
        return {"document_id": self.docs[key]["id"], "signals": 2}

    def documents(self) -> list[dict]:
        return list(self.docs.values())

    def bundles(self) -> list[dict]:
        return list(self.docs.values())


class DoublingService(FakeService):
    """A world that wrongly makes a second document for the same bytes."""

    def upload(self, name: str, data: bytes) -> dict:
        self.docs[f"d{len(self.docs)}"] = {"id": f"doc-{len(self.docs)}", "name": name}
        return {"document_id": f"doc-{len(self.docs) - 1}", "signals": 2}


class FakeStore:
    """A store of dated records that selects the latest available record at a cutoff and keeps all of them."""

    can_state_supersession = True

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def ingest(self, record: dict) -> None:
        self.rows.append(record)

    def current(self, as_of: date) -> dict | None:
        ok = [r for r in self.rows if date.fromisoformat(r["available_on"]) <= as_of]
        return max(ok, key=lambda r: r["available_on"])

    def history(self) -> list[dict]:
        return self.rows


class NoSupersessionStore(FakeStore):
    can_state_supersession = False


def suite(access: il.Access | None = None) -> il.Suite:
    return il.load_suite(INNER_LOOP_SUITE, access)


def recipes(s: il.Suite) -> dict:
    return il.load_recipes(INNER_LOOP_SUITE / "recipes.yaml", s.access)


def run(**kw) -> dict:
    s = suite()
    return il.run_suite(s, recipes(s), **kw)


def by_id(r: dict) -> dict[str, dict]:
    return {x["test_id"]: x for x in r["results"]}


@pytest.fixture(scope="module")
def full() -> dict:
    return by_id(run(reader=FakeReader(), services=FakeService, stores=FakeStore,
                     skip={"TST-01-10": "told to skip"}))


def answer(full: dict, tid: str) -> dict:
    assert full[tid]["status"] == il.ANSWERED, full[tid]["reason"]
    return full[tid]["actual_result"]


def test_a_difference_of_cumulative_figures_with_its_contract(full) -> None:
    r = full["TST-01-01"]
    assert answer(full, "TST-01-01") == {"Q2": 130, "q1": 100, "kind": "derived", "unresolved": ["the third quarter"]}
    assert r["scope_period_units_when_applicable"] == {"period": "second quarter", "unit": "million",
                                                       "units": {"q1": "thousand"}}
    assert r["calculation_trace_when_applicable"] == [
        {"name": "Q2", "expression": "h1 - q1", "inputs": {"h1": 230, "q1": 100}, "value": 130}]
    assert r["assumptions_and_unresolved_inputs"] == {"assumptions": ["same basis"], "unresolved": ["the third quarter"]}
    assert r["evidence_and_object_bindings_when_applicable"]["applicable"] is False
    assert r["selected_baseline_scenario_version_when_applicable"]["applicable"] is False
    assert r["internal"]["mechanism"] == "a difference of cumulative figures"
    assert r["internal"]["grounding"]["operation"] == "calc"


def test_the_contract_keeps_our_fields_and_maps_the_suites(full) -> None:
    r = full["TST-01-02"]
    assert set(r) >= {"test_id", "status", "actual_result", "scope_period_units_when_applicable", "internal", "family"}
    assert "calculation_trace_when_applicable" not in r             # the fixture asks for four fields only
    assert r["actual_result"] == {"revenue": 120}
    assert r["internal"]["answer"] == {"revenue": 120} and r["internal"]["calculations"][0]["name"] == "revenue"
    assert r["scope_period_units_when_applicable"] == {"scope": {"entity": "synthetic"}, "currency": "CU",
                                                       "basis": "stipulated"}
    assert il.FIELD_MAP["actual_result"] == "answer"
    # the fixture supplied its own input: the stated reasons come from the recipe
    assert r["internal"]["baseline"]["reason"] == "a stipulated fixture"
    assert r["internal"]["evidence_and_objects"]["reason"] == "the fixture supplies its own inputs"


def test_figures_are_read_from_a_frozen_page_by_locator(full) -> None:
    a = answer(full, "TST-01-03")
    assert a == {"growth": 200, "margin": 300, "segments": 500, "flipped": 700, "tail": 200, "total": 450}
    ev = full["TST-01-03"]["evidence_and_object_bindings_when_applicable"]["evidence"]
    assert [e["excerpt_id"] for e in ev] == ["T-001"]
    assert ev[0]["availability_date"] == "2030-04-10" and ev[0]["pdf_pages"] == [1] and ev[0]["printed_page"] == "1"
    assert ev[0]["locations"][0]["passage"].startswith("Revenue")
    assert full["TST-01-03"]["internal"]["grounding"]["source_excerpts"] == ["T-001"]


def test_text_dates_dashes_and_stated_facts(full) -> None:
    a = answer(full, "TST-01-04")
    assert a == {"start": "2030-01-01", "note": "figures exclude Unit Z", "dash": "－", "window": "2030-03-31",
                 "stated": True, "nothing": None, "count": 3}
    assert full["TST-01-04"]["selected_baseline_scenario_version_when_applicable"] == {"selected": "synthetic baseline"}


def test_a_release_after_the_cutoff_is_not_usable(full) -> None:
    assert answer(full, "TST-01-05") == {"usable": False, "late": True, "version": "synthetic v1"}


def test_a_reconciliation_takes_its_parts_from_the_models_composition(full) -> None:
    a = answer(full, "TST-01-06")
    assert (a["row_sum"], a["reported"], a["residual"], a["difference"], a["reconciles"], a["check"]) == (450, 450, 0, 0, True, 0)
    objs = full["TST-01-06"]["evidence_and_object_bindings_when_applicable"]["objects"]
    assert objs[0]["id"] == "c.seg" and objs[0]["parts"] == ["attr.a", "attr.b", "attr.r", "attr.e"]


def test_every_way_a_case_is_blocked_names_its_reason(full) -> None:
    why = {t: r["reason"] for t, r in full.items() if r["status"] == il.BLOCKED}
    assert "division" in why["TST-01-07"].lower() or "DivisionByZero" in why["TST-01-07"]
    assert "not one of this case's frozen excerpts" in why["TST-01-08"]
    assert why["TST-01-09"].startswith("no recipe")
    assert "has parts with no figure in the source: attr.b, attr.r, attr.e" in why["TST-02-01"]
    assert "has no part attr.zz" in why["TST-02-02"]
    assert why["TST-02-04"] == "not in the world model's construction of co: attr.missing"
    assert "InvalidOperation" in why["TST-03-03"]
    assert "does not allow" in why["TST-03-04"] and "Call" in why["TST-03-04"]
    assert "nobody" in why["TST-03-05"]
    assert "cannot read the expression" in why["TST-03-06"]
    assert why["TST-03-07"] == "unknown locator ['bogus']"
    assert why["TST-03-08"] == "the fixture has no fixture_inputs.nope"
    assert "has no group 1" in why["TST-03-09"]
    assert "not in the source index" in why["TST-03-10"]
    assert "differs from the hash" in why["TST-04-01"]
    assert "not in the suite folder" in why["TST-04-02"]
    assert why["TST-04-03"] == "not a date: 'Unit Z'"
    assert "match 0 not found" in why["TST-04-04"]
    assert why["TST-04-05"] == "the specified check cannot be run here"
    assert "not in the source index" in why["TST-04-07"]
    assert "composition c.nope is not in" in why["TST-05-02"]
    assert full["TST-01-09"]["actual_result"] == {"applicable": False, "reason": why["TST-01-09"]}


def test_blocked_without_a_world_a_service_or_a_store() -> None:
    r = by_id(run())
    assert "no world model was supplied" in r["TST-02-03"]["reason"]
    assert "needs the world model's composition" in r["TST-04-08"]["reason"]
    assert "needs the world model's composition" in r["TST-01-06"]["reason"]
    assert "clean world to import into" in r["TST-04-09"]["reason"]
    assert "clean stores to ingest into" in r["TST-04-10"]["reason"]


def test_skipped_cases_are_not_run_with_their_reason(full) -> None:
    assert full["TST-01-10"]["status"] == il.NOT_RUN and full["TST-01-10"]["reason"] == "told to skip"
    assert full["TST-01-10"]["actual_result"]["applicable"] is False


def test_objects_are_bound_to_the_models_kinds(full) -> None:
    objs = full["TST-02-03"]["evidence_and_object_bindings_when_applicable"]["objects"]
    assert [(o["id"], o["kind"]) for o in objs] == [("attr.a", "attribute"), ("c.seg", "composition"),
                                                     ("id.x", "identity"), ("path.p", "path")]
    assert full["TST-02-03"]["internal"]["grounding"]["model_objects"] == ["attr.a", "c.seg", "id.x", "path.p"]


def test_update_and_undo_keeps_the_audit_history(full) -> None:
    a = answer(full, "TST-02-05")
    assert (a["before_x"], a["before_y"]) == (10, 32)
    assert (a["updated_x"], a["updated_y"]) == (7, 23)
    assert (a["restored_x"], a["restored_y"]) == (10, 32)
    assert a["restored_equals_before"] and a["audit_retained"] and a["undo_linked_to_update"]
    assert [e["event"] for e in a["audit"]] == ["initialize", "update", "undo"]
    assert a["audit"][2]["undoes"] == a["audit"][1]["seq"] == 1
    assert full["TST-02-05"]["selected_baseline_scenario_version_when_applicable"] == {"baseline_id": "B1",
                                                                                      "scenario_id": "C1"}


def test_importing_the_same_source_twice_adds_nothing(full) -> None:
    a = answer(full, "TST-02-06")
    assert a["unique_economic_records"] and a["computed_totals_unchanged_after_identical_reimport"]
    assert a["duplicate_documents_created"] == 0 and a["same_document_id"] is True
    assert a["documents_after_first_import"] == a["documents_after_second_import"] == 1
    bad = by_id(run(reader=FakeReader(), services=DoublingService))["TST-02-06"]["actual_result"]
    assert bad["unique_economic_records"] is False and bad["duplicate_documents_created"] == 1
    assert bad["computed_totals_unchanged_after_identical_reimport"] is False


def test_both_ingestion_orders_select_the_same_record_and_keep_history(full) -> None:
    a = answer(full, "TST-02-07")
    assert a["store_A_current"] == a["store_B_current"] == 105
    assert a["store_A_current_source"] == a["store_B_current_source"] == "S2"
    assert a["same_current_record"] and a["history_retained"]
    assert a["store_A_history"] == a["store_B_history"] == ["S1", "S2"]


def test_a_store_that_cannot_state_supersession_blocks_the_case() -> None:
    r = by_id(run(reader=FakeReader(), stores=NoSupersessionStore))["TST-02-08"]
    assert r["status"] == il.BLOCKED and "cannot record that one source explicitly corrects" in r["reason"]


def test_a_store_that_loses_history_fails_the_check() -> None:
    class Forgetful(FakeStore):
        def history(self) -> list[dict]:
            return self.rows[:1]

    a = by_id(run(reader=FakeReader(), stores=Forgetful))["TST-02-07"]["actual_result"]
    assert a["history_retained"] is False


def test_mapping_review_refuses_borrowed_coefficients_and_missing_evidence(full) -> None:
    c = answer(full, "TST-02-09")["candidates"]
    assert c["candidate_A"] == {"decision": "reject", "reasons": ["coefficient from another business",
                                                                   "no evidence from the business it maps"]}
    assert c["candidate_B"] == {"decision": "approve_with_limits", "reasons": [], "unquantified": ["tax"]}
    assert c["candidate_C"]["decision"] == "reject" and c["candidate_C"]["reasons"] == ["no evidence from the business it maps"]
    assert answer(full, "TST-02-09")["result"] == 30


def test_golden_review_names_what_it_cannot_evidence(full) -> None:
    a = answer(full, "TST-02-10")
    c = a["candidates"]
    assert a["independent_oracle"] == 120
    assert c["G1"]["decision"] == "ineligible" and len(c["G1"]["reasons"]) == 3
    assert c["G2"]["decision"] == "eligible_conditional" and c["G2"]["claimed_controls"] == ["fixture retained"]
    assert c["G3"]["decision"] == "ineligible" and c["G3"]["reasons"] == [
        "expected answer differs from the independent calculation"]
    assert a["artifacts"] == {"required": ["external arithmetic record", "reviewer approval record"],
                              "supplied_by_this_run": ["external arithmetic record"],
                              "not_supplied": ["reviewer approval record"]}
    assert a["access_evidence"]["files_read"] > 0
    full2 = answer(full, "TST-03-02")["candidates"]
    assert full2["G2"]["decision"] == "eligible"                  # nothing required is missing


def test_a_gate_in_the_review_group_is_answered_like_any_case(full) -> None:
    assert full["TST-03-01"]["scorecard_group"] == "review_gate"
    assert answer(full, "TST-03-01")["candidates"]["candidate_A"]["decision"] == "reject"


def test_the_calculator_functions_and_operators(full) -> None:
    a = answer(full, "TST-05-01")
    assert a["m"] == 3.5 and a["mx"] == 3.5 and a["ab"] == 2 and a["s"] == 2.5
    assert a["r"] == 10.5 and a["r0"] == 4 and a["lst"] == [3.5, -2] and a["pair"] == [3.5, -2]
    assert a["notb"] is True and a["cmp"] is True and a["cmp2"] is False
    assert a["bo"] is True and a["bo2"] is True and a["ifx"] == 5 and a["ifx2"] == 6
    assert (a["up"], a["fd"], a["md"], a["pw"]) == (-2, 3, 3, 8)
    assert a["neq"] and a["eq"] and a["ge"] and a["le"] and a["gt"]
    assert a["a"] == 3.5 and a["words"] == "some text" and a["flag"] is True
    assert full["TST-05-01"]["scope_period_units_when_applicable"]["reason"] == "no period, unit or scope"


def test_numbers_are_parsed_as_the_page_prints_them() -> None:
    assert il.parse_number("1,063,473") == Decimal(1063473)
    assert il.parse_number("(285,617)") == Decimal(-285617)
    assert il.parse_number("−40.5") == Decimal("-40.5")
    assert il.parse_date("April 1, 2026") == date(2026, 4, 1) and il.parse_date("2026-04-01") == date(2026, 4, 1)
    assert il.plain(Decimal("2.50")) == 2.5 and il.plain(Decimal("3")) == 3
    assert il.plain({"a": [Decimal(1), date(2026, 1, 2)]}) == {"a": [1, "2026-01-02"]}
    assert il.as_value(True) is True and il.as_value("x") == "x" and il.as_value(2) == Decimal(2)


def test_the_run_reads_only_what_it_is_given_and_logs_it(tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere.json"
    outside.write_text("{}")
    access = il.Access([INNER_LOOP_SUITE])
    with pytest.raises(il.AccessDenied):
        access.read_text(outside)
    assert not access.allowed(outside) and access.allowed(INNER_LOOP_SUITE / "questions.json")
    s = suite(access)
    il.run_suite(s, recipes(s), only=["TST-01-03"])
    rep = access.report()
    names = {Path(f["path"]).name for f in rep["files_read"]}
    assert {"questions.json", "fixture_inputs.json", "source_index.json", "T-001.txt", "recipes.yaml"} <= names
    assert all(len(f["sha256"]) == 64 for f in rep["files_read"])
    assert rep["roots"] == [str(INNER_LOOP_SUITE.resolve())]


def test_the_runner_never_names_the_answer_key() -> None:
    text = (SRC / "evaluation" / "inner_loop.py").read_text(encoding="utf-8").lower()
    for word in ("holdout", "answer_key", "answer-key"):
        assert word not in text
    assert "inner_loop_grade" not in " ".join(line for line in text.splitlines() if line.startswith(("import", "from")))


def test_the_same_inputs_give_the_same_bytes() -> None:
    a = il.dumps(run(reader=FakeReader(), services=FakeService, stores=FakeStore))
    b = il.dumps(run(reader=FakeReader(), services=FakeService, stores=FakeStore))
    assert a == b and a.endswith("\n") and json.loads(a)["field_map"] == il.FIELD_MAP


def test_only_selects_cases_and_the_run_carries_the_suites_policy() -> None:
    r = run(only=["TST-01-01", "TST-01-02"])
    assert [x["test_id"] for x in r["results"]] == ["TST-01-01", "TST-01-02"]
    assert r["suite_id"] == "SYNTHETIC-1" and r["adapter_field_policy"] == "Labels are semantic targets."
