"""The packet protocol on the invented suite: prepare writes the layout and no hint, collect turns answer files into the
grader's results (missing, invalid and blocked answers stay blocked with their reason), the same answers give the same bytes,
and the grader reports the transcripts and the graded answers. No client data."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from axelrod_wm.evaluation import inner_loop as il
from axelrod_wm.evaluation import inner_loop_grade as g
from axelrod_wm.evaluation import inner_loop_packets as pk
from tests.where import INNER_LOOP_EXPORT, INNER_LOOP_KEY, INNER_LOOP_SUITE, SRC

CASES = ["TST-01-01", "TST-01-02", "TST-01-03", "TST-01-05"]


def prepared(tmp_path: Path, only: list[str] | None = None) -> tuple[Path, il.Suite, dict]:
    out = tmp_path / "packets"
    shutil.copytree(INNER_LOOP_EXPORT, out / "export")
    suite = il.load_suite(INNER_LOOP_SUITE, il.Access([INNER_LOOP_SUITE, out]))
    meta = pk.prepare_packets(suite, out, "r1", tools_command="uv run il_tools", export_dir=out / "export",
                              memo_dir=out / "model_reads", only=only or CASES)
    return out, suite, meta


def answer(tid: str, **kw) -> dict:
    return {"test_id": tid, "status": "answered", "answer": {"x": 1}, **kw}


def write(out: Path, tid: str, body: dict | str) -> None:
    (out / "answers" / f"{tid}.json").write_text(body if isinstance(body, str) else json.dumps(body), encoding="utf-8")


def test_prepare_writes_one_packet_per_case_and_the_shared_export(tmp_path: Path) -> None:
    out, _, meta = prepared(tmp_path)
    assert [c["test_id"] for c in meta["cases"]] == CASES and meta["export_files"] == 3
    assert json.loads((out / "run.json").read_text())["run"] == "r1" and (out / "answers").is_dir()
    p = out / "TST-01-03"
    assert sorted(f.name for f in p.iterdir()) == ["answer.schema.json", "excerpt_index.json", "excerpts", "task.md"]
    assert sorted(f.name for f in (p / "excerpts").iterdir()) == ["T-001.pdf", "T-001.txt"]      # the page and its layout
    idx = json.loads((p / "excerpt_index.json").read_text())
    assert idx[0]["excerpt_id"] == "T-001" and idx[0]["availability_date"] == "2030-04-10" and idx[0]["printed_page"] == "1"
    assert (p / "excerpts" / "T-001.txt").read_text() == (INNER_LOOP_SUITE / "excerpts" / "T-001.txt").read_text()
    assert json.loads((out / "TST-01-02" / "fixture_inputs.json").read_text()) == {"price": 12, "units": 10, "nested": {"deep": 4}}
    shutil.rmtree(tmp_path / "second", ignore_errors=True)
    out2, _, _ = prepared(tmp_path / "second", ["TST-05-04"])
    assert sorted(f.name for f in (out2 / "TST-05-04" / "excerpts").iterdir()) == ["T-002.txt"]       # no layout copy to take
    assert not (out / "TST-01-01" / "fixture_inputs.json").exists() and not (out / "TST-01-01" / "excerpts" / "T-001.txt").exists()


def test_the_task_has_the_question_the_contract_and_no_hint(tmp_path: Path) -> None:
    out, suite, _ = prepared(tmp_path)
    text = (out / "TST-01-03" / "task.md").read_text()
    assert "What does the page report for revenue, costs and the totals?" in text
    assert "uv run il_tools calc --expr" in text and f"{out.resolve() / 'answers' / 'TST-01-03.json'}" in text
    assert "answer.schema.json" in text and suite.meta["adapter_field_policy"] in text
    assert "No fixture inputs" in text and "excerpts/" in text and "No source pages are bound" not in text
    fx = (out / "TST-01-02" / "task.md").read_text()
    assert "fixture_inputs.json" in fx and "No source pages are bound" in fx
    tail = lambda s: s.split("## Tools", 1)[1].replace(s.split()[2], "X")        # noqa: E731
    assert tail(text).replace("TST-01-03", "X").split("## Return")[0] == tail(fx).replace("TST-01-02", "X").split("## Return")[0]
    for word in ("holdout", "answer_key", "development", "validation", "split"):
        assert word not in text.lower() and word not in (out / "TST-01-02" / "fixture_inputs.json").read_text().lower()


def test_prepare_refuses_a_page_that_changed_or_is_missing_and_a_missing_export(tmp_path: Path) -> None:
    out = tmp_path / "p"
    shutil.copytree(INNER_LOOP_EXPORT, out / "export")
    suite = il.load_suite(INNER_LOOP_SUITE, il.Access([INNER_LOOP_SUITE]))
    for only, why in ((["TST-04-01"], "differs from the hash"), (["TST-04-02"], "not in the suite folder")):
        with pytest.raises(il.Blocked, match=why):
            pk.prepare_packets(suite, out, "r", tools_command="t", export_dir=out / "export", memo_dir=out / "m", only=only)
    with pytest.raises(FileNotFoundError, match="has not been produced"):
        pk.prepare_packets(suite, out, "r", tools_command="t", export_dir=out / "nope", memo_dir=out / "m")


def test_the_schema_checks_the_shape_of_an_answer() -> None:
    s = pk.answer_schema()
    assert pk.validate(answer("X"), s) == []
    assert pk.validate([], s) == ["$: expected object"]
    bad = pk.validate({"status": "maybe", "extra": 1, "evidence": [{"excerpt_id": "a"}], "objects": [3]}, s)
    assert "$: missing test_id" in bad and any("is not one of" in b for b in bad) and "$: unexpected field extra" in bad
    assert "$.evidence[0]: missing location" in bad and "$.objects[0]: expected string" in bad
    ok = answer("X", unit="JPY", units={"x": "m"}, evidence=[{"excerpt_id": "a", "location": "l", "passage": "p"}],
                calculations=[{"expression": "1", "value": 1}], objects=["o"], missing_inputs=["m"])
    assert pk.validate(ok, s) == []


def test_collect_turns_answers_into_the_grader_contract(tmp_path: Path) -> None:
    out, suite, _ = prepared(tmp_path)
    write(out, "TST-01-01", answer("TST-01-01", unit="million", units={"x": "thousand"}, period="Q2", scope={"entity": "acme"},
                                   assumptions=["same basis"], missing_inputs=["q3"], baseline={"selected": "b"}))
    (out / "TST-01-01" / "calc_log.jsonl").write_text(json.dumps({"expression": "h - q", "inputs": {}, "value": 130}) + "\n")
    write(out, "TST-01-03", answer("TST-01-03", evidence=[
        {"excerpt_id": "T-001", "location": "table", "passage": "Revenue\n 1,000"},
        {"excerpt_id": "T-001", "location": "table", "passage": "a sentence that is not on the page"},
        {"excerpt_id": "T-002", "location": "elsewhere", "passage": "Other"}],
        calculations=[{"expression": "h - q", "value": 130}, {"expression": "a + b", "inputs": {"a": 1}, "value": 3}], objects=["acme.units"]))
    (out / "TST-01-03" / "calc_log.jsonl").write_text(json.dumps({"expression": "h - q", "inputs": {}, "value": 130}) + "\n")
    write(out, "TST-01-05", {"test_id": "TST-01-05", "status": "blocked", "reason": "the page is not available"})
    r = pk.collect(suite, out, [])
    by = {x["test_id"]: x for x in r["results"]}
    a = by["TST-01-01"]
    assert a["status"] == il.ANSWERED and a["actual_result"] == {"x": 1, "unresolved": ["q3"]}
    assert a["scope_period_units_when_applicable"] == {"period": "Q2", "unit": "million", "units": {"x": "thousand"}, "scope": {"entity": "acme"}}
    assert a["selected_baseline_scenario_version_when_applicable"] == {"selected": "b"}
    assert a["calculation_trace_when_applicable"] == [{"expression": "h - q", "inputs": {}, "value": 130, "verified_by_tool": True}]
    assert a["assumptions_and_unresolved_inputs"] == {"assumptions": ["same basis"], "unresolved": ["q3"]}
    assert a["internal"]["grounding"]["operation"] == "agent"
    c = by["TST-01-03"]
    ev = c["evidence_and_object_bindings_when_applicable"]
    assert [(e["bound_to_case"], e["passage_found_on_page"]) for e in ev["evidence"]] == [(True, True), (True, False), (False, False)]
    assert ev["objects"] == [{"id": "acme.units"}] and c["internal"]["grounding"]["source_excerpts"] == ["T-001", "T-002"]
    assert [x["verified_by_tool"] for x in c["calculation_trace_when_applicable"]] == [True, False]
    assert c["scope_period_units_when_applicable"]["applicable"] is False
    assert c["selected_baseline_scenario_version_when_applicable"]["applicable"] is False
    b = by["TST-01-05"]
    assert (b["status"], b["reason"]) == (il.BLOCKED, "the page is not available")
    assert by["TST-01-02"]["status"] == il.BLOCKED and by["TST-01-02"]["reason"] == "no answer file was written"
    assert a["evidence_and_object_bindings_when_applicable"]["applicable"] is False


def test_invalid_answers_are_blocked_with_the_reason(tmp_path: Path) -> None:
    out, suite, _ = prepared(tmp_path)
    write(out, "TST-01-01", "{not json")
    write(out, "TST-01-02", {"test_id": "TST-01-02", "status": "maybe"})
    write(out, "TST-01-03", answer("TST-01-01"))
    write(out, "TST-01-05", {"test_id": "TST-01-05", "status": "blocked", "reason": "  "})
    by = {x["test_id"]: x["reason"] for x in pk.collect(suite, out)["results"]}
    assert by["TST-01-01"].startswith("invalid answer: not JSON")
    assert "is not one of" in by["TST-01-02"] and "$.test_id: 'TST-01-01' is not 'TST-01-03'" in by["TST-01-03"]
    assert "a blocked answer states its reason" in by["TST-01-05"]
    write(out, "TST-01-05", {"test_id": "TST-01-05", "status": "answered", "answer": {}})
    assert "an answered case returns its result" in {x["test_id"]: x["reason"] for x in pk.collect(suite, out)["results"]}["TST-01-05"]


def test_the_same_answers_give_the_same_bytes_and_are_recorded(tmp_path: Path) -> None:
    out, suite, _ = prepared(tmp_path)
    write(out, "TST-01-01", answer("TST-01-01"))
    write(out, "TST-01-02", "{bad")
    t = tmp_path / "transcript.txt"
    t.write_text("the agent read the packet")
    fresh = lambda: il.load_suite(INNER_LOOP_SUITE, il.Access([INNER_LOOP_SUITE, out]))     # noqa: E731
    a = il.dumps(pk.collect(fresh(), out, [t]))
    b = il.dumps(pk.collect(fresh(), out, [t]))
    assert a == b
    r = json.loads(a)
    assert r["answers"]["files"] == 2 and set(r["answers"]["by_case"]) == {"TST-01-01", "TST-01-02"} and len(r["answers"]["sha256"]) == 64
    assert r["answers"]["dir"] == str(out.resolve() / "answers") and r["run"]["run"] == "r1"
    assert r["transcripts"] == [{"path": str(t), "bytes": 25, "sha256": pk.sha(b"the agent read the packet")}]
    write(out, "TST-01-01", answer("TST-01-01", unit="u"))
    assert json.loads(il.dumps(pk.collect(suite, out)))["answers"]["sha256"] != r["answers"]["sha256"]
    only = pk.collect(suite, out, only=["TST-01-01"])
    assert [x["test_id"] for x in only["results"]] == ["TST-01-01"]


def test_the_collector_reads_only_the_suite_and_the_packets(tmp_path: Path) -> None:
    out, suite, _ = prepared(tmp_path)
    r = pk.collect(suite, out)
    roots = {Path(x).resolve() for x in r["access"]["roots"]}
    assert roots == {INNER_LOOP_SUITE.resolve(), out.resolve()}
    for f in r["access"]["files_read"]:
        assert any(Path(f["path"]).is_relative_to(x) for x in roots)
    for name in ("inner_loop", "inner_loop_packets", "inner_loop_tools"):
        text = (SRC / "evaluation" / f"{name}.py").read_text(encoding="utf-8").lower()
        assert "holdout" not in text and "answer_key" not in text and "answer-key" not in text


def test_the_grader_reports_the_graded_answers_and_what_the_transcripts_mention(tmp_path: Path) -> None:
    out, suite, _ = prepared(tmp_path)
    clean, dirty = tmp_path / "clean.txt", tmp_path / "dirty.txt"
    clean.write_text("read packets/TST-01-01/task.md and the export")
    dirty.write_text(f"opened {INNER_LOOP_KEY} and the heldout folder")
    r = json.loads(il.dumps(pk.collect(suite, out, [clean])))
    card = g.grade(r, INNER_LOOP_KEY, "t")
    sep = card["review_gates"]["answer_key_separation"]
    assert sep["no_transcript_mentions_the_key"] is True and sep["transcripts"]["transcripts_scanned"] == 1
    assert card["graded_inputs"]["sha256"] == r["answers"]["sha256"]
    assert f"Graded answers: `{r['answers']['dir']}`" in g.markdown(card)
    r2 = {**r, "transcripts": [*r["transcripts"], {"path": str(dirty)}, {"path": str(tmp_path / "gone.txt")}]}
    scan = g.transcript_scan(INNER_LOOP_KEY, r2, ("heldout", ""))
    assert scan["transcripts_scanned"] == 2 and scan["transcripts_unreadable"] == 1
    assert scan["mentions"] == {str(INNER_LOOP_KEY): 1, "answer_key.json": 1, "heldout": 1}
    assert g.grade(r2, INNER_LOOP_KEY, "t", ("heldout",))["review_gates"]["answer_key_separation"][
        "no_transcript_mentions_the_key"] is False
    assert "graded_inputs" in g.grade({"results": [], "access": {"roots": [], "files_read": []}}, INNER_LOOP_KEY)
