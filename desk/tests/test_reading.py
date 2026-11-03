"""The checks on a figure, the reader's Claude Code run and its fix rounds, and one fact per figure."""

from __future__ import annotations

import json
import subprocess

import pytest

from axelrod_desk import facts as fx
from axelrod_desk.reader import FIX, Answer, ClaudeCode, ReaderError, prompt_for, read
from axelrod_desk.records import KINDS, check, check_all, check_theme, schema_for, shown

PAGES = ["Acme Motors Q3 2026", "Revenue for the quarter was JPY 120.5 bn\nUnits sold 50,000"]
CAT = {"acme.revenue", "acme.units"}


def obs(**kw):
    o = {"metric_id": "acme.revenue", "label": "Revenue, Q3", "kind": "company-reported actual", "value": 120.5,
         "unit": "JPY bn per quarter", "page": 2, "quote": "Revenue for the quarter was JPY 120.5 bn",
         "period": {"label": "Q3 2026", "type": "quarter", "start": "2026-07-01", "end": "2026-09-30"},
         "scope": {"perimeter": "consolidated", "basis": "reported"}, "raw": {"amount": 120.5, "unit": "JPY bn"}}
    return {**o, **kw}


def test_a_good_figure_passes_and_each_fault_is_named():
    assert check(obs(), source_class="company", pages=PAGES, catalog=CAT) == []
    cases = [
        (obs(kind="broker estimate"), "kind"),
        (obs(metric_id="acme.ghost"), "catalog"),
        (obs(period={"type": "decade", "start": "2026-07-01", "end": "2026-09-30"}), "period.type"),
        (obs(period={"type": "quarter", "start": "July", "end": "2026-09-30"}), "YYYY-MM-DD"),
        (obs(period={"type": "quarter", "start": 5, "end": "2026-09-30"}), "YYYY-MM-DD"),
        (obs(period={"type": "quarter", "start": "2026-10-01", "end": "2026-09-30"}), "after"),
        (obs(page=9), "not a page"),
        (obs(page="2"), "not a page"),
        (obs(quote="Revenue was JPY 99 bn"), "not on page 2"),
        (obs(quote=""), "not on page 2"),
        (obs(value=None), "missing"),
        (obs(value="120.5"), "must be a number"),
        (obs(value=True), "must be a number"),
        (obs(unit=" "), "needs a unit"),
        (obs(raw={"amount": 77.0, "unit": "bn"}), "77.0 is not in the quote"),
    ]
    for o, why in cases:
        problems = check(o, source_class="company", pages=PAGES, catalog=CAT)
        assert any(why in p for p in problems), (o, problems)
    rating = obs(kind="broker rating", value=None, metric_id=None, quote="Acme Motors Q3 2026", page=1)
    assert check(rating, source_class="sell_side", pages=PAGES, catalog=CAT) == []
    no_raw = obs(raw=None, value=50000, unit="units", metric_id="acme.units", quote="Units sold 50,000")
    assert check(no_raw, source_class="company", pages=PAGES, catalog=CAT) == []
    assert "50,000" in shown(50000.0) and "120.5" in shown(120.5) and "1,234.5" in shown(-1234.5)


def test_themes_and_the_schema_per_class():
    good = {"theme": "t", "summary": "s", "citations": [{"page": 2, "quote": "units sold 50,000"}]}
    bad = {"theme": "u", "summary": "s", "citations": [{"page": 3, "quote": "x"}]}
    assert check_theme(good, PAGES) == [] and check_theme(bad, PAGES)
    out = check_all({"observations": [obs(), obs(page=9)], "themes": [good, bad]}, source_class="company", pages=PAGES,
                    catalog=CAT)
    assert out["failed"] == 1 and out["themes"] == [good] and out["observations"][0]["problems"] == []
    s = schema_for("sell_side")
    assert s["properties"]["observations"]["items"]["properties"]["kind"]["enum"] == list(KINDS["sell_side"])


JOB = {"document": {"sha256": "a" * 64, "filename": "acme.pdf", "title": "", "publisher": None, "published": None,
                    "source_class": "company"}, "company_name": "Acme Motors", "pages": PAGES,
       "catalog": [{"metric_id": "acme.revenue", "name": "Acme revenue", "model_unit": "JPY bn per quarter"},
                   {"metric_id": "acme.units", "name": "Acme units", "model_unit": "units"}]}


def test_the_prompt_names_the_document_and_what_to_record():
    p = prompt_for(JOB)
    assert "Acme Motors" in p and "acme.pdf" in p and "publisher not stated" in p and "2 page(s)" in p
    assert "company-reported actual" in p


def test_a_reading_is_checked_and_its_failures_sent_back_until_fixed():
    calls = []

    def claude(prompt, work, schema, resume=None):
        calls.append((prompt[:40], resume, (work / "document.txt").read_text().count("=== PAGE"),
                      json.loads((work / "catalog.json").read_text())[0]["metric_id"]))
        if resume is None:
            return Answer({"observations": [obs(), obs(page=9)], "themes": []}, "s1", 0.5, "m")
        return Answer({"observations": [obs()], "themes": []}, "s1", 0.25, "m")

    out = read(JOB, claude, rounds=3)
    assert out["rounds"] == 2 and out["cost"] == 0.75 and out["model"] == "m" and len(out["observations"]) == 1
    assert calls[1][1] == "s1" and calls[1][0] == FIX[:40] and calls[0][2:] == (2, "acme.revenue")


def test_after_the_last_round_failures_are_kept_with_their_problems():
    out = read(JOB, lambda *a, **k: Answer({"observations": [obs(page=9)], "themes": []}, "s", 0, ""), rounds=1)
    assert out["rounds"] == 1 and out["observations"][0]["problems"]


def completed(stdout, code=0, stderr=""):
    return lambda cmd, **kw: subprocess.CompletedProcess(cmd, code, stdout, stderr)


def test_claude_code_is_run_headless_with_the_schema(tmp_path):
    seen = {}

    def run(cmd, **kw):
        seen.update(cmd=cmd, cwd=kw["cwd"])
        return subprocess.CompletedProcess(cmd, 0, json.dumps({
            "structured_output": {"observations": [], "themes": []}, "session_id": "abc", "total_cost_usd": 0.1,
            "modelUsage": {"claude-x": {}}}), "")

    a = ClaudeCode(model="claude-x", run=run)("read it", tmp_path, {"type": "object"}, resume="prev")
    assert (a.session, a.cost, a.model) == ("abc", 0.1, "claude-x") and seen["cwd"] == tmp_path
    cmd = seen["cmd"]
    assert cmd[:3] == ["claude", "-p", "read it"] and cmd[cmd.index("--permission-mode") + 1] == "dontAsk"
    assert cmd[-4:] == ["--model", "claude-x", "--resume", "prev"] and "--json-schema" in cmd
    plain = ClaudeCode(run=completed(json.dumps({"structured_output": {}, "session_id": "s"})))("p", tmp_path, {})
    assert plain.model == "" and plain.cost == 0


@pytest.mark.parametrize("run, why", [
    (completed("not json", 1, "boom"), "without JSON"),
    (completed(json.dumps({"is_error": True, "result": "Not logged in"})), "Not logged in"),
    (completed(json.dumps({"result": "no answer"})), "no figures"),
])
def test_claude_code_failures_are_reader_errors(tmp_path, run, why):
    with pytest.raises(ReaderError, match=why):
        ClaudeCode(run=run)("p", tmp_path, {})


def test_a_missing_or_slow_claude_code(tmp_path):
    def missing(cmd, **kw):
        raise FileNotFoundError(cmd[0])

    def slow(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 1)

    with pytest.raises(ReaderError, match="not installed"):
        ClaudeCode(run=missing)("p", tmp_path, {})
    with pytest.raises(ReaderError, match="did not finish"):
        ClaudeCode(run=slow, timeout=1)("p", tmp_path, {})


# -- facts ---------------------------------------------------------------------------------------------------------------
def rec(i, sha, o, publisher="Acme Motors", published="2026-10-30", doc_type="filing"):
    return {"id": f"r{i}", "sha256": sha, "company": "acme", "publisher": publisher, "published": published,
            "doc_type": doc_type, "filename": f"{sha}.pdf", "observation": o}


def test_one_fact_per_figure_with_every_citation_and_conflicts_flagged():
    base = [{"company": "acme", "observation": {
        "observation_id": "OBS1", "metric_id": "acme.revenue", "label": "Revenue, Q3", "kind": "reported actual",
        "value": 120.5, "unit": "JPY bn per quarter", "period": obs()["period"], "available_at": "2026-10-30",
        "source": {"source_id": "s.acme", "location": "page 3"}}}]
    records = [
        rec(1, "a", obs()),                                                               # equals the base figure
        rec(2, "b", obs(value=120.6), doc_type="news", published="2026-10-29"),           # within 0.5%: the same fact
        rec(3, "c", obs(value=130.0)),                                                    # far apart: a conflict
        rec(4, "d", obs(kind="broker-reported actual"), publisher="Nomura"),             # a broker: its own fact
        rec(5, "e", obs(kind="broker estimate", scope={"perimeter": "", "basis": "estimate before results"}),
            publisher="Nomura"),
        rec(6, "f", obs(metric_id=None, label="Dealer stock", value=None, kind="company guidance")),
        rec(7, "g", obs(metric_id=None, label="  dealer   STOCK ", value=None, kind="company guidance")),
    ]
    out = fx.resolve(records, base)
    by = {(f.speaker, f.claim, f.value): f for f in out}
    company = by[("company", "reported", 120.5)]
    assert company.baseline and company.conflict and [c.get("sha256") for c in company.citations] == [None, "a", "b"]
    assert by[("company", "reported", 130.0)].conflict and not by[("company", "reported", 130.0)].baseline
    assert not by[("nomura", "reported", 120.5)].conflict
    assert ("nomura", "estimate before results", 120.5) in by
    guide = by[("company", "guidance", None)]
    assert len(guide.citations) == 2 and not guide.conflict and guide.metric_id is None
    assert guide.to_dict()["key"] == guide.key and len({f.key for f in out}) == len(out) == 5
    assert out == sorted(out, key=lambda f: f.key)


def test_claims_speakers_and_closeness():
    assert fx.claim_of({"kind": "company guidance"}) == "guidance"
    assert fx.claim_of({"kind": "reported actual (capital action)"}) == "reported"
    assert fx.claim_of({"kind": "some guidance note"}) == "guidance"
    assert fx.claim_of({"kind": "broker estimate revision", "label": "FY26E before 3Q26 results"}) == "estimate before results"
    assert fx.speaker_of({"kind": "broker estimate"}, None) == "unnamed"
    assert fx.speaker_of({"kind": "reported actual"}, "x") == "company"
    assert fx.close(None, None) and not fx.close(None, 1.0) and fx.close(0.0, 0.0) and not fx.close(100, 101)


def test_a_revised_estimate_or_guidance_is_a_new_view_not_a_conflict():
    est = obs(kind="broker estimate")
    out = fx.resolve([rec(1, "a", est, publisher="JPM", published="2026-10-07"),
                      rec(2, "b", {**est, "value": 125.0}, publisher="JPM", published="2026-10-19"),
                      rec(3, "c", {**est, "value": 125.1}, publisher="JPM", published="2026-10-19"),
                      rec(4, "d", obs(kind="broker-reported actual"), publisher="JPM", published="2026-10-07"),
                      rec(5, "e", obs(kind="broker-reported actual", value=121.6), publisher="JPM", published="2026-10-19")])
    assert sorted((f.claim, f.value, len(f.citations), f.conflict) for f in out) == [
        ("estimate", 120.5, 1, False), ("estimate", 125.0, 2, False), ("reported", 120.5, 1, True), ("reported", 121.6, 1, True)]
    assert fx.group_of("acme", {"kind": "company guidance", "available_at": "2026-08-01"}, None)[-1] == "2026-08-01"
