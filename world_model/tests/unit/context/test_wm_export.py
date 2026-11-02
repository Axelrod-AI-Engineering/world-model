"""The evaluation export (context/wm_export.py, Oct 31): a built construction as `axelrod.wm-export/v1`, with invented
sources, citations and repair data (no client figures). What it must never do is state more than the model knows: an
uncalibrated link has no effect, a value's support is its input class, a dangling path step stays visible, and every
record says whether the versioned state holds it."""

from __future__ import annotations

import json
from types import SimpleNamespace as NS

import pytest

from axelrod_wm.context import wm_export as wx
from axelrod_wm.engine.engine import build_engine
from axelrod_wm.model.construction import NamedPath, Observable, PathStep, Transition
from axelrod_wm.repo.history import log
from tests.conftest import observe_event, run_days
from tests.unit.context.test_construction_export import engine


@pytest.mark.parametrize("text, unit, scale, currency, per, flow", [
    ("¥tn per quarter", "JPY", "trillion", "JPY", None, "per_quarter"),
    ("$m", "USD", "million", "USD", None, None),
    ("€bn annual", "EUR", "billion", "EUR", None, "per_year"),
    ("£k", "GBP", "thousand", "GBP", None, None),
    ("¥m/unit", "JPY", "million", "JPY", "unit", None),
    ("¥/share", "JPY", "unit", "JPY", "share", None),
    ("m units/yr", "units", "million", None, None, "per_year"),
    ("thousand units per quarter", "units", "thousand", None, None, "per_quarter"),
    ("vehicles per month", "units", "unit", None, None, "per_month"),
    ("bn shares", "shares", "billion", None, None, None),
    ("pct", "percent", "unit", None, None, None),
    ("%", "percent", "unit", None, None, None),
    ("percent of sales", "percent", "unit", None, None, None),
    ("pp", "pp", "unit", None, None, None),
    ("x", "ratio", "unit", None, None, None),
    ("bn/yr", "other", "billion", None, None, "per_year"),
    ("local ccy", "other", "unit", None, None, None),
    ("", None, None, None, None, None),
    (None, None, None, None, None, None),
])
def test_a_unit_string_splits_into_unit_scale_currency_and_flow(text, unit, scale, currency, per, flow):
    u = wx.parse_unit(text)
    assert (u["unit"], u["scale"], u["currency"], u["per"], u["flow"]) == (unit, scale, currency, per, flow)
    assert u["unit_text"] == (text or "")


@pytest.mark.parametrize("scope, kind, level, geo", [
    ({"basis": "share of profit of investments accounted for using the equity method"}, "", "equity_method", None),
    ({"basis": "IFRS"}, "reported actual (subsidiary basis)", "subsidiary", None),
    ({"basis": "US GAAP, consolidated TMCC"}, "", "subsidiary", None),
    ({"basis": "IFRS", "view": "reporting_segments"}, "", "segment", None),
    ({"basis": "IFRS segment operating results"}, "", "segment", None),
    ({"basis": "IFRS", "view": "customer_location"}, "", "region", "customer_location"),
    ({"basis": "IFRS geographic information"}, "", "region", None),
    ({"basis": "IFRS", "perimeter": "consolidated"}, "", "consolidated", None),
    ({"basis": "IFRS", "perimeter": "consolidated Toyota Motor Corporation and subsidiaries"}, "reported actual",
     "consolidated", None),
    ({"basis": "operating income of consolidated subsidiaries", "perimeter": "subsidiaries"}, "", "subsidiary", None),
    ({"basis": "IFRS", "perimeter": "listed subsidiaries"}, "", "subsidiary", None),
    ({"basis": "company reference table"}, "", None, None),
    (None, "", None, None),
])
def test_a_free_text_scope_reads_as_a_consolidation_level_or_stays_unknown(scope, kind, level, geo):
    s = wx.consolidation(scope, kind)
    assert (s["consolidation"], s["geography_basis"]) == (level, geo)


@pytest.mark.parametrize("obs, status", [
    ({"kind": "reported actual", "class": "externally_estimated"}, "third_party"),
    ({"kind": "broker statement (third party)"}, "third_party"),
    ({"kind": "reported actual (rounded)"}, "reported"),
    ({"kind": "company guidance"}, "guidance"),
    ({"kind": "workbook"}, "unknown"),
    ({}, "unknown"),
])
def test_an_observation_kind_is_its_kind_of_claim(obs, status):
    assert wx.epistemic_of_observation(obs) == status


def test_small_parsers():
    assert wx.parse_date("2026-08-03 (Update Log: latest)") == "2026-08-03"
    assert wx.parse_date("2026-06 (filed after results)") is None and wx.parse_date(None) is None
    assert wx._r("x") is None and wx._r(None) is None and wx._r(1.23456789) == 1.234568
    assert wx._iso(None) is None and wx._iso("2026-01-01") == "2026-01-01"
    assert wx._text({"class": "targeted extraction", "note": "page 2"}) == "class: targeted extraction; note: page 2"
    assert wx._text({}) is None and wx._text(None) is None


class _NoQuantile:
    """A posterior whose family has no quantiles: the estimate carries no interval."""

    def mean(self):
        return -1.0

    def sd(self):
        return 0.5


SOURCES = {
    "catalogue": {
        "s.fsum": {"source_id": "s.fsum", "document": "data/sources/acme/q1_summary.pdf", "kind": "financial summary",
                   "publication_date": "2024-02-05 (with the results)"},
        "s.deck": {"source_id": "s.deck", "document": ["data/sources/acme/deck_a.pdf", "data/sources/acme/deck_b.pdf"],
                   "kind": "results deck", "publication_date": "with each results release"},
        "s.none": {"source_id": "s.none", "document": None, "kind": "public statement", "publication_date": None},
    },
    "citations": {
        "acme.auto": [{"source": "s.fsum", "location": "page 3", "passage": "Automotive operating income 10.0"}] * 2,
        "t2": [{"source": "s.deck", "location": "slide 7", "passage": "landed cost weighs on regional profit"}],
    },
}
HASHES = {"data/sources/acme/q1_summary.pdf": "a" * 64, "data/sources/acme/own_filing.pdf": "b" * 64}
REPAIR = {
    "repair_version": "test-1", "entity": "acme", "company_id": "N_ACME",
    "input_classes": {"acme.finance": {"class": "derived", "basis": "auto minus eliminations"},
                      "acme.home": {"class": "assumed", "basis": "a round prior", "resolution": "the segment note"}},
    "observations": [
        {"observation_id": "OBS_PROFIT_Q1", "metric_id": "acme.profit", "line_id": None, "label": "Operating income",
         "period": {"label": "Q1 FY24", "type": "quarter", "start": "2024-01-01", "end": "2024-03-31"},
         "value": 10.0, "unit": "bn per quarter", "kind": "reported actual",
         "scope": {"basis": "IFRS", "perimeter": "consolidated"}, "available_at": "2024-05-08",
         "raw": {"amount": 10000, "unit": "million"},
         "source": {"source_id": "s.own", "document": "data/sources/acme/own_filing.pdf", "location": "page 4",
                    "page": 4, "printed_page": "3"},
         "citations": [{"source_id": "s.own", "document": "data/sources/acme/press.pdf", "location": "PDF page 2",
                        "page": 2, "quote": "operating income of 10.0bn"}]},
        {"observation_id": "OBS_SHARE", "metric_id": "rival.share", "line_id": "share", "label": None,
         "period": {"label": "2023", "type": "season", "start": None, "end": "2023-12-31"}, "value": None,
         "unit": "pct", "kind": "broker statement (third party)", "scope": {"basis": "third-party broker statement"},
         "available_at": "2024-01-10", "derived_from": "sum of the two sides",
         "source": {"source_id": "s.fsum", "location": "p. 2", "quote": "share near a third"}},
        {"observation_id": "OBS_NOPERIOD", "metric_id": None, "label": None, "line_id": None,
         "value": 1.0, "unit": "", "kind": "", "available_at": None, "source": {}},
    ],
}
OTHER = {"repair_version": "x", "entity": "zeta", "company_id": "acme", "observations": [{"observation_id": "Z"}]}


def built(tmp_path):
    eng = engine(tmp_path, build_engine)
    dev = eng.wm.deviations
    run_days(eng, 3, lambda d: [observe_event(f"o{d}", {"acme.profit": 14.0 + d, "acme.na": 9.0}, dev.date_of(d))])
    g = eng.wm.graph
    g.interactions["t3"] = g.interactions["t3"].model_copy(update={"transition": Transition(
        mechanism="landed cost squeezes segment profit", observable=Observable(name="segment margin"))})
    tr = g.interactions["t2"].transition
    g.interactions["t2"] = g.interactions["t2"].model_copy(update={"transition": tr.model_copy(update={
        "evidence": tr.evidence.model_copy(update={"sources": ["s.deck", "s.none", "s.deck"]})})})
    g.paths["P0"] = NamedPath(id="P0", name="Gone", entity_id="acme", trigger="t", endpoint="acme.profit",
                              steps=[PathStep(interaction_id="ghost")])
    g.compositions["C2"] = g.compositions["C2"].model_copy(update={"drives": False})
    g.subentities["acme.elims"] = g.subentities["acme.elims"].model_copy(update={"posterior": _NoQuantile()})
    g.subentities["acme.na"] = g.subentities["acme.na"].model_copy(update={"features": {
        "view": "regions", "input_class": "reported", "prior": "synthetic"}})
    g.subentities["acme.landed_cost"] = g.subentities["acme.landed_cost"].model_copy(update={"features": {
        "view": "operating_state", "proxy_for": "peer landed cost", "input_class": "a guess"}})
    g.subentities["acme.headcount"] = g.subentities["acme.home"].model_copy(update={   # nothing places it
        "id": "acme.headcount", "name": "headcount", "unit": "thousand people", "features": {}, "history": []})
    g.identities["I1"] = NS(target="acme.finance", terms=lambda: [("acme.auto", 1), ("acme.elims", -1)],
                            formula=lambda: "finance = auto - elims")
    g.stock_flows["F1"] = NS(stock="acme.home", terms=lambda: [("acme.na", 1)], formula=lambda: "home += na")
    return eng


def proposals():
    return [NS(id="p2", kind="graph_update", status="pending", review_reasons=["unattributed"], decided_by=None),
            NS(id="p1", kind="graph_update", status="auto_applied", review_reasons=[], decided_by="policy:standards"),
            NS(id="p3", kind="graph_update", status="approved", review_reasons=[], decided_by="eve")]


def export(eng, **kw):
    return wx.wm_export(eng.wm, eng.ltm, world_model_id="acme-wm", label="Acme", version=eng.version,
                        state_hash=eng.state_hash, generated_at="2024-01-09T00:00:00Z", subjects=["Acme"], **kw)


def test_the_export_says_what_the_model_holds_and_no_more(tmp_path):
    eng = built(tmp_path)
    changes = log(eng, limit=500)
    vetted = changes[0].model_copy(update={"vetted_by": "eve"})
    doc = export(eng, sources=SOURCES, repairs=[REPAIR, OTHER], document_hashes=HASHES,
                 versions=eng.storage.versions(), changes=[vetted, *changes[1:]], proposals=proposals(),
                 scenario={"series_id": "s", "step": 0}, commit="abc123")
    assert doc == json.loads(json.dumps(doc))                          # plain JSON, nothing left as an object
    m = doc["manifest"]
    assert doc["schema_version"] == "axelrod.wm-export/v1" and m["version"] == str(eng.version)
    assert m["generator"] == {"name": "karthik-world-model", "version": "0.1.0", "commit": "abc123"}
    assert [a["name"] for a in m["attachments"]] == ["sources", "repair:acme"] and m["scenario"]["step"] == 0
    assert doc["capabilities"]["supersession"] is False and doc["capabilities"]["as_of"] is True
    assert {g["concept"] for g in doc["schema_gaps"]} >= {"supersession", "undo"}

    rel = {r["relation_id"]: r for r in doc["relations"]}
    assert rel["t1"]["effect"] is None and rel["t1"]["timing"]["lag_days"] is None       # uncalibrated: no size, not 0
    assert rel["t1"]["sign"] == "+" and rel["t1"]["evidence_support"]["existence"] == "documented"
    assert rel["a0"]["effect"]["mean"] is not None and rel["a0"]["timing"]["onset"] == "unknown"
    assert rel["t3"]["observable"] == "segment margin" and rel["t3"]["sign"] == "-"      # a transition without a sign
    assert rel["a4"]["drives"] is False and rel["a0"]["drives"] is True                  # the reconciling view's links
    binds = {b["binding_id"]: b for b in doc["bindings"]}
    t2 = [binds[b] for b in rel["t2"]["bindings"]]
    assert sorted((b["source_id"], b["evidence_type"]) for b in t2) == [
        ("s.deck", "citation"), ("s.none", "source")]                                    # cited once; s.deck covered
    assert all(b["document_sha256"] is None for b in t2)                                 # a deck of two documents

    var = {v["variable_id"]: v for v in doc["variables"]}
    assert var["acme.profit"]["role"] == "financial_endpoint" and var["macro.tariff"]["role"] == "driver"
    assert var["acme.landed_cost"]["role"] == "operating_state" and var["macro.tariff"]["unit"] == "percent"
    assert var["acme.headcount"]["role"] is None and len(var["acme.auto"]["bindings"]) == 1   # one passage cited twice
    assert {k: var[k]["input_class"] for k in ("acme.profit", "acme.finance", "acme.na", "acme.auto",
                                              "acme.landed_cost")} == {
        "acme.profit": "reported", "acme.finance": "derived", "acme.na": "reported",
        "acme.auto": "externally_estimated", "acme.landed_cost": "assumed"}
    assert var["acme.na"]["calibration_status"] == "synthetic" and var["acme.landed_cost"]["calibration_status"] == "proxy"
    assert var["acme.auto"]["calibration_status"] is None and var["acme.auto"]["epistemic_status"] == "estimated"
    assert var["acme.elims"]["estimate"] == {"kind": "model", "mean": -1.0, "sd": 0.5, "q05": None, "q95": None}
    assert var["acme.finance"]["derived_from"] == {"operands": ["acme.auto", "acme.elims"], "rule": "finance = auto - elims"}
    assert var["acme.home"]["derived_from"]["operands"] == ["acme.na"]
    assumed = {a["variable_id"]: a for a in doc["assumptions"]}
    assert assumed["acme.home"]["replaced_by"] == "the segment note" and "acme.landed_cost" in assumed

    rec = {r["record_id"]: r for r in doc["records"]}
    q1 = rec["OBS_PROFIT_Q1"]
    assert q1["origin"] == "attachment" and q1["period"]["type"] == "quarter" and q1["scope"]["consolidation"] == "consolidated"
    assert (q1["unit"], q1["scale"], q1["epistemic_status"]) == ("other", "billion", "reported")
    assert q1["as_reported"] == {"value": 10000.0, "unit_text": "million"}
    b = binds[q1["bindings"][0]]
    assert (b["document_sha256"], b["page"], b["printed_page"], b["document_name"]) == ("b" * 64, 4, "3", "own_filing.pdf")
    also = binds[q1["bindings"][1]]                                                       # a further document, same figure
    assert (also["document_name"], also["page"], also["passage"]) == ("press.pdf", 2, "operating income of 10.0bn")
    share = rec["OBS_SHARE"]
    assert share["variable_id"] is None and share["value_state"] == "unknown" and share["period"]["type"] == "other"
    assert share["epistemic_status"] == "third_party" and share["derived_from"]["rule"] == "sum of the two sides"
    assert binds[share["bindings"][0]]["document_sha256"] == "a" * 64                   # the source's one document
    assert rec["OBS_NOPERIOD"]["period"]["type"] is None and rec["OBS_NOPERIOD"]["as_reported"] is None
    folded = [r for r in doc["records"] if r["origin"] == "model_state"]
    assert folded and {r["variable_id"] for r in folded} == {"acme.profit", "acme.na"}
    assert all(r["epistemic_status"] == "unknown" and r["recorded_at"] for r in folded)
    assert "Z" not in rec                                                                # another company's repair data

    views = {v["view_id"]: v for v in doc["views"]}
    assert views["C1"]["eliminations"] == [{"variable_id": "acme.elims", "sign": "+"}]
    assert views["C1"]["non_additive_with"] == ["C2"] and views["C2"]["eliminations"] == []
    paths = {p["path_id"]: p for p in doc["paths"]}
    assert [s["relation_id"] for s in paths["P0"]["steps"]] == ["ghost"]                # a dangling step stays
    src = {s["source_id"]: s for s in doc["sources"]}
    assert src["s.fsum"]["available_at"] == "2024-02-05" and src["s.fsum"]["documents"][0]["sha256"] == "a" * 64
    assert len(src["s.deck"]["documents"]) == 2 and src["s.deck"]["available_at"] is None
    assert src["s.none"]["documents"] == [] and src["s.none"]["title"] is None

    h = doc["history"]
    assert [v["version"] for v in h["versions"]] == sorted(v["version"] for v in h["versions"])
    assert h["changes"][-1]["actor_kind"] == "person" and h["changes"][0]["actor_kind"] == "system"
    assert all(isinstance(n, int) for n in h["changes"][0]["counts"].values())
    assert [(p["proposal_id"], p["decided_by_kind"]) for p in h["proposals"]] == [
        ("p1", "system"), ("p2", None), ("p3", "person")]
    assert export(eng, sources=SOURCES, repairs=[REPAIR], document_hashes=HASHES, versions=eng.storage.versions(),
                  changes=[vetted, *changes[1:]], proposals=proposals(), scenario={"series_id": "s", "step": 0},
                  commit="abc123") == doc                                               # the same inputs, the same export


def test_a_narrowed_export_keeps_only_its_entities_and_marks_links_that_leave_them(tmp_path):
    eng = built(tmp_path)
    doc = export(eng, entity_ids=["macro", "nobody"])
    assert [e["entity_id"] for e in doc["entities"]] == ["macro"]
    assert {r["relation_id"] for r in doc["relations"]} == {"t1"}                      # acme's own links are left out
    assert doc["relations"][0]["endpoints_exported"] is False
    assert doc["views"] == [] and doc["paths"] == [] and doc["manifest"]["attachments"] == []
    assert doc["variables"][0]["input_class"] == "assumed" and doc["bindings"] == []
