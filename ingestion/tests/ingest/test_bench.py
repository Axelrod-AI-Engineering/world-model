"""The ingestion benchmark's scoring (ingest/bench.py): matching predictions to gold, recall and precision, the
out-of-reach accounting, stage timings, and the report."""

from __future__ import annotations

import pytest

from axelrod_ingest.bench import (
    GoldSignal,
    Score,
    _pct,
    agrees,
    ends,
    label_key,
    load_gold,
    located,
    negatives,
    only_split,
    report,
    score,
    split_of,
    timing,
)

OBS = {"type": "observe", "value_of": "central_bank.policy_rate", "value": 4.25, "quote": "to 4.25%"}
UP = {"type": "move", "value_of": "gov_bonds.yield_10y", "delta": 0.1, "mode": "absolute", "quote": "rose 10bp"}
SUP = {"type": "support", "source": "dollar.index", "target": "acme_motors.operating_profit", "quote": "stronger dollar"}


def test_ends_names_a_value_or_a_pair():
    assert ends(OBS) == ("central_bank.policy_rate",)
    assert ends(SUP) == ("dollar.index", "acme_motors.operating_profit")


@pytest.mark.parametrize("pred, gold, ok", [
    (OBS, OBS, True),
    ({**OBS, "value": 4.27}, OBS, True),                     # within 0.05 in its unit
    ({**OBS, "value": 4.4}, OBS, False),
    ({**OBS, "value": 101.5}, {**OBS, "value": 100.0}, True),  # within 2%
    ({**OBS, "value": 103.0}, {**OBS, "value": 100.0}, False),
    (UP, OBS | {"value_of": "gov_bonds.yield_10y"}, False),       # a move does not observe a level
    (UP, {**UP, "delta": 0.5, "mode": "standardized"}, True),  # same direction, any size or mode
    ({**UP, "delta": -0.1}, UP, False),
    ({**UP, "delta": 0.0}, {**UP, "delta": 0.0}, False),     # no direction says nothing
    ({**OBS, "value_of": "gov_bonds.yield_10y", "value": 1.0}, UP, False),
    (SUP, SUP, True),
    ({**SUP, "type": "link", "label": "lifts", "effect": 0.3}, SUP, True),
    (SUP, {**SUP, "type": "link"}, True),
    ({**SUP, "type": "contradict"}, SUP, False),
    ({**SUP, "type": "contradict"}, {**SUP, "type": "contradict"}, True),
    (SUP, {**SUP, "type": "contradict"}, False),
    ({**SUP, "target": "ridge_energy.operating_profit"}, SUP, False),
])
def test_agreement(pred, gold, ok):
    assert agrees(pred, gold) is ok


def test_located_needs_only_the_same_value_or_ends():
    assert located({**UP, "delta": -1}, UP) and not located(OBS, UP)


def test_label_keys_are_stable_and_distinguish_files_and_quotes():
    assert label_key("a.pdf", OBS) == label_key("a.pdf", dict(reversed(list(OBS.items()))))
    assert label_key("a.pdf", OBS) != label_key("b.pdf", OBS)
    assert label_key("a.pdf", OBS) != label_key("a.pdf", {**OBS, "quote": "other"})
    assert len(label_key("a.pdf", {k: v for k, v in OBS.items() if k != "quote"})) == 16


def test_gold_comes_from_items_and_their_annotations():
    items = [{"id": "B", "signals": [UP]}, {"id": "A", "signals": [OBS, SUP]}]
    notes = [{"item_id": "A", "files": ["x.pdf"], "signals": [{"index": 1, "verdict": "partly", "extractable": "table"}]}]
    gold = load_gold(items, notes)
    assert [(g.item_id, g.index) for g in gold] == [("A", 0), ("A", 1), ("B", 0)]
    assert gold[0].files == ("x.pdf",) and gold[0].verdict == "supported" and gold[0].extractable == "sentence"
    assert gold[1].verdict == "partly" and gold[1].extractable == "table" and gold[1].counted
    assert gold[2].files == () and not gold[2].counted


@pytest.mark.parametrize("g, counted", [
    (GoldSignal("A", 0, OBS, ("f",)), True),
    (GoldSignal("A", 0, OBS, ("f",), verdict="unsupported"), False),
    (GoldSignal("A", 0, OBS, ("f",), extractable="chart_only"), False),
    (GoldSignal("A", 0, OBS, ("f",), extractable="inference"), False),
    (GoldSignal("A", 0, OBS, ()), False),
])
def test_what_counts_toward_recall(g, counted):
    assert g.counted is counted


def test_scoring_matches_each_gold_once_and_judges_the_rest_by_labels():
    gold = [GoldSignal("A", 0, OBS, ("f",)), GoldSignal("A", 1, OBS, ("f",)),       # the same claim twice
            GoldSignal("B", 0, UP, ("g",)), GoldSignal("C", 0, SUP, ("f", "g")),
            GoldSignal("D", 0, OBS, ("f",), verdict="unsupported"), GoldSignal("E", 0, OBS, ()),
            GoldSignal("F", 0, OBS, ("f",), extractable="chart_only")]
    wrong = {**UP, "delta": -0.1}
    extra = {"type": "observe", "value_of": "crude_oil.price", "value": 90.0, "quote": "Crude at $90"}
    junk = {"type": "observe", "value_of": "crude_oil.price", "value": 9.0, "quote": "9"}
    unknown = {"type": "move", "value_of": "crude_oil.price", "delta": 1.0, "quote": "?"}
    preds = {"f": [OBS, extra, junk], "g": [wrong, SUP, unknown]}
    labels = {label_key("f", extra): "correct", label_key("f", junk): "incorrect"}
    sc = score(preds, gold, labels)
    assert (sc.counted, sc.found, sc.located) == (4, 2, 4)                   # OBS once, SUP; the rest located
    assert sc.by_type == {"observe": [2, 1], "move": [1, 0], "support": [1, 1]}
    assert sc.by_verdict == {"supported": [4, 2]}
    assert sc.out_of_reach == {"unsupported": 1, "no file": 1, "chart_only": 1}
    assert (sc.predicted, sc.correct, sc.incorrect, sc.unlabelled) == (6, 3, 1, 2)
    assert [m["item_id"] for m in sc.misses] == ["A", "B"]
    assert sc.misses[1]["near"] == [wrong] and sc.misses[0]["near"] == [OBS]
    assert sc.errors == [{"file": "f", "signal": junk}]
    assert sc.recall == 0.5 and sc.location_recall == 1.0 and sc.precision == 0.75
    assert sc.f1 == pytest.approx(0.6)


def test_empty_scores_are_well_defined():
    sc = score({}, [])
    assert (sc.recall, sc.location_recall, sc.precision) == (1.0, 1.0, 1.0) and sc.f1 == 1.0
    assert Score(counted=1, correct=0, incorrect=1).f1 == 0.0


def test_quantiles_by_nearest_rank():
    xs = [5.0, 1.0, 3.0, 2.0, 4.0]
    assert (_pct(xs, 0.5), _pct(xs, 0.95), _pct(xs, 0.0), _pct([7.0], 0.5)) == (3.0, 5.0, 1.0, 7.0)


def test_timing_summarizes_stages_and_throughput():
    rows = [{"bytes": 2_000_000, "pages": 10, "timings": {"parse": 1.0, "extract": 1.0}},
            {"bytes": 1_000_000, "pages": 5, "timings": {"parse": 2.0}}]
    tm = timing(rows)
    assert (tm["documents"], tm["seconds"], tm["pages"], tm["megabytes"]) == (2, 4.0, 15, 3.0)
    assert tm["stages"]["parse"] == {"total": 3.0, "mean": 1.5, "p50": 1.0, "p95": 2.0, "share": 0.75}
    assert tm["per_document"] == {"p50": 2.0, "p95": 2.0, "max": 2.0}
    assert tm["throughput"] == {"documents_per_s": 0.5, "pages_per_s": 3.75, "mb_per_s": 0.75}
    zero = timing([{"bytes": 1, "timings": {"parse": 0.0}}])
    assert zero["throughput"] == {} and zero["stages"]["parse"]["share"] == 0.0 and zero["pages"] == 0
    assert timing([]) == {"documents": 0, "seconds": 0, "pages": 0, "megabytes": 0.0, "stages": {},
                          "per_document": {}, "throughput": {}}


def test_the_report_names_scores_speed_misses_and_errors():
    gold = [GoldSignal("A", 0, OBS, ("f",)), GoldSignal("B", 0, UP, ("f",)), GoldSignal("C", 0, SUP, ("f",)),
            GoldSignal("D", 0, OBS, ("f",), verdict="unsupported")]
    link = {"type": "link", "source": "a.x", "target": "b.y", "label": "lifts", "effect": 0.3, "quote": "q"}
    preds = {"f": [{**UP, "delta": -0.2}, link]}
    sc = score(preds, gold, {label_key("f", link): "incorrect"})
    tm = timing([{"bytes": 1_000_000, "pages": 3, "timings": {"parse": 0.5, "extract": 1.5}}])
    text = report(sc, tm, title="T", misses=2)
    assert text.startswith("# T\n") and "**Recall** 0.0% (0 of 3" in text and "**Precision** 0.0%" in text
    assert "| move | 1 | 0 | 0% |" in text and "Not counted: unsupported 1." in text
    assert "## Speed" in text and "| extract | 1.5 | 75% |" in text
    assert "## Misses (first 2 of 3)" in text and "- A#0: observe central_bank.policy_rate = 4.25" in text
    assert "- B#0: move gov_bonds.yield_10y +0.1 (absolute); read as move gov_bonds.yield_10y -0.2 (absolute)" in text
    assert "C#0" not in text                                                    # past the first two
    assert "## Incorrect predictions (1)" in text and "- f: link a.x → b.y" in text
    bare = report(score({}, []), timing([]))
    assert "## Speed" not in bare and "## Misses" not in bare and "| Type |" not in bare and "Not counted" not in bare


def test_splits_are_fixed_by_path_and_hold_out_about_a_third():
    files = [f"doc{k}.pdf" for k in range(300)]
    test = [f for f in files if split_of(f) == "test"]
    assert split_of("doc1.pdf") == split_of("doc1.pdf") and 70 < len(test) < 130
    gold = [GoldSignal("A", 0, OBS, (test[0],)), GoldSignal("B", 0, OBS, (files[0] if files[0] not in test else files[1],)),
            GoldSignal("C", 0, OBS, ())]
    preds = {test[0]: [OBS], "x.pdf" if split_of("x.pdf") == "dev" else "y.pdf": [UP]}
    p, g = only_split(preds, gold, "test")
    assert list(p) == [test[0]] and [x.item_id for x in g] == ["A"]
    p, g = only_split(preds, gold, "dev")
    assert test[0] not in p and [x.item_id for x in g] == ["B"]
    assert only_split(preds, gold, "all") == (preds, gold)


def test_the_report_gives_recall_by_verdict():
    gold = [GoldSignal("A", 0, OBS, ("f",)), GoldSignal("B", 0, UP, ("f",), verdict="partly")]
    text = report(score({"f": [OBS]}, gold), timing([]))
    assert "Recall on gold the file states fully: 100.0% (1 of 1)" in text
    assert "Recall on gold the file states partly: 0.0% (0 of 1)" in text


def test_negative_controls_count_what_is_read_from_files_with_no_claim():
    notes = [{"item_id": "A", "files": ["a.pdf"]}, {"item_id": "N1", "files": ["n1.pdf"], "negative_control": True},
             {"item_id": "N2", "files": ["n2.pdf"], "negative_control": True, "signals": []}]
    ctl = negatives({"a.pdf": [OBS], "n1.pdf": [OBS, UP]}, notes)
    assert ctl == {"n1.pdf": 2, "n2.pdf": 0}
    text = report(score({}, []), timing([]), controls=ctl)
    assert "Negative controls: 2 signal(s) read from 2 file(s) that state no claim (1 with any)" in text
    assert "Negative controls" not in report(score({}, []), timing([]))
