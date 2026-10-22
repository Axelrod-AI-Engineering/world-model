"""The reviewer's second round (Oct 18), on synthetic fixtures only: sources and citations that resolve
(context/construction.load_sources, citation_check; context/v4.attach_sources), inputs by status and the search of
the supplied material before an input is declared missing (search_inputs), and reconciliation of each additive
composition (model/construction.reconcile)."""

from __future__ import annotations

import json
from types import SimpleNamespace as NS

import pytest

from axelrod_wm.context import v4
from axelrod_wm.context.construction import (
    citation_check,
    company_citations,
    evidence_refs,
    input_needs,
    inputs_by_status,
    load_sources,
    material_claims,
    passages,
    query_terms,
    score_passage,
    search_inputs,
    search_markdown,
)
from axelrod_wm.ingest.parse import parse
from axelrod_wm.model.construction import Transition, bundle_levels, model_levels, reconcile
from tests.unit.model.test_business_construction import acme_construction, build, world


@pytest.fixture
def graph(tmp_path):
    return build(world(tmp_path, acme_construction()), tmp_path)


def _sources(tmp_path, citations=None):
    root = tmp_path / "construction"
    (root / "acme").mkdir(parents=True)
    (root / "acme" / "sources.json").write_text(json.dumps({"company": "acme", "sources": {
        "ac.wb": {"file": "acme_model.xlsx", "kind": "workbook", "publication_date": "2026-05-01", "period": "FY25",
                  "accounting_basis": "IFRS", "read_state": "read", "proof_limits": "no hedges", "rows": [1, 2]},
        "ac.ir": {"file": "acme_results.pdf", "kind": "results", "location": "p. 4"}}}))
    (root / "acme" / "citations.json").write_text(json.dumps(citations if citations is not None else {
        "t1": [{"source": "ac.wb", "location": "Segments!C4", "passage": "NA imports 40% of units"},
               {"source": "ac.ghost", "location": "p. 1", "passage": "x"}],
        "acme.auto": [{"source": "ac.ir", "location": "p. 4", "passage": "Automotive 10.0"}],
        "nothing.here": [{"source": "ac.ir"}]}))
    (root / "beta").mkdir()                                                  # a flat sources.json, no citations
    (root / "beta" / "sources.json").write_text(json.dumps({"ac.wb": {"file": "dup.xlsx"}, "bt.co": {"file": "b.pdf"},
                                                             "note": "not a source"}))
    (root / "empty").mkdir()                                                 # neither file: not a company folder
    return root


# -- sources and citations ------------------------------------------------------------------------------------------------
def test_sources_load_from_both_layouts_and_a_duplicate_id_is_reported(tmp_path):
    s = load_sources(_sources(tmp_path))
    assert s["companies"] == ["acme", "beta"] and sorted(s["catalogue"]) == ["ac.ir", "ac.wb", "bt.co"]
    wb = s["catalogue"]["ac.wb"]
    assert wb == {"source_id": "ac.wb", "company": "acme", "document": "acme_model.xlsx", "kind": "workbook",
                  "publication_date": "2026-05-01", "period": "FY25", "basis": "IFRS", "read_state": "read",
                  "proof_limits": "no hedges", "location": None}
    assert s["problems"] == ["source id 'ac.wb' is defined by acme and beta"]
    assert s["citations"]["nothing.here"] == [{"source": "ac.ir", "location": "", "passage": "", "company": "acme"}]


def test_a_citations_file_without_a_sources_file(tmp_path):
    (tmp_path / "solo").mkdir()
    (tmp_path / "solo" / "citations.json").write_text(json.dumps({"t1": None}))
    s = load_sources(tmp_path)
    assert s["companies"] == ["solo"] and s["catalogue"] == {} and s["citations"] == {}


def test_material_claims_and_evidence_refs(tmp_path):
    assert material_claims(None) == []
    assert material_claims({"existence": "documented", "direction": "assumption", "magnitude": "broker"}) == [
        "existence: documented", "magnitude: broker"]
    s = load_sources(_sources(tmp_path))
    refs = evidence_refs("t1", ["ac.wb", "ac.ir", "ac.ir", "zz"], s)
    assert refs[0] == {"source_id": "ac.wb", "document": "acme_model.xlsx", "location": "Segments!C4",
                       "passage": "NA imports 40% of units"}
    assert refs[1]["document"] is None                                        # ac.ghost does not resolve
    assert refs[2:] == [{"source_id": "ac.ir", "document": "acme_results.pdf", "location": None, "passage": None},
                        {"source_id": "zz", "document": None, "location": None, "passage": None}]
    assert evidence_refs("none", [], s) == []


def test_the_citation_check_reports_what_does_not_resolve_and_what_is_uncited(tmp_path):
    s = load_sources(_sources(tmp_path))
    links = [("t1", {"evidence": {"existence": "documented", "sources": ["ac.wb", "ac.missing"]}}),
             ("t2", {"evidence": {"magnitude": "guidance", "sources": ["ac.missing", "ac.missing"]}}),
             ("t3", {"evidence": {"existence": "assumption"}}), ("a0", None)]
    c = citation_check(links, ["acme.auto", "acme.na"], s, known={"t1", "t2", "acme.auto"}, company="acme")
    assert c["resolved"] == ["ac.ir", "ac.wb"]
    assert c["unresolved"] == [{"source_id": "ac.ghost", "cited_by": ["t1"]},
                               {"source_id": "ac.missing", "cited_by": ["t1", "t2"]}]
    assert c["claims_without_citation"] == [{"interaction_id": "t2", "claims": ["magnitude: guidance"],
                                             "sources": ["ac.missing", "ac.missing"]}]
    assert c["unknown_citation_keys"] == ["nothing.here"] and c["cited_links"] == 1 and c["cited_values"] == 1
    assert citation_check(links, [], s, known={"t1"}, company="beta")["unknown_citation_keys"] == []
    assert citation_check(links, [], s)["unknown_citation_keys"] == []        # without `known`, nothing is unknown


def test_a_citation_without_a_location_does_not_cover_a_material_claim(tmp_path):
    s = load_sources(_sources(tmp_path, {"t1": [{"source": "ac.wb", "passage": "p"}]}))
    c = citation_check([("t1", {"evidence": {"direction": "model"}})], [], s)
    assert [x["interaction_id"] for x in c["claims_without_citation"]] == ["t1"]


def test_a_companys_citations_come_from_the_links_that_touch_its_values(graph, tmp_path):
    s = load_sources(_sources(tmp_path))
    c = company_citations(graph, "acme", s)
    # t1 is documented (existence, direction) and cited with a location; t2 too, but nothing cites it
    assert [x["interaction_id"] for x in c["claims_without_citation"]] == ["t2"]
    assert c["unresolved"] == [{"source_id": "ac.ghost", "cited_by": ["t1"]}]
    assert c["unknown_citation_keys"] == ["nothing.here"] and c["cited_values"] == 1


def test_an_export_carries_evidence_refs_a_catalogue_and_citation_gaps(tmp_path):
    s = load_sources(_sources(tmp_path))
    tr = {"evidence": {"existence": "documented", "sources": ["ac.wb"]}}
    ctx = {"manifest": {"load_order": [{"file": "a", "source": "yours"}, {"file": "e.json", "source": "this export: evidence"},
                                       {"file": "f.json", "source": "this export: forecast"}]},
           "domain_pack": {"domain_pack_id": "PACK_X", "company_edge_relationships": [
               {"axelrod": {"interaction_id": "t1", "transition": tr}},
               {"axelrod": {"interaction_id": "t9", "transition": {"evidence": {"magnitude": "broker"}}}}],
               "domain_specific_support_objects": {"schema_gaps": [{"concept": "c"}], "macro_transmission_links": [
                   {"axelrod": {"interaction_id": "m1"}}]}},
           "evidence": {"values": [{"metric_id": "acme.auto"}, {"metric_id": "acme.na"}]}}
    doc = v4.attach_sources(ctx, s)
    rels = ctx["domain_pack"]["company_edge_relationships"]
    assert [r["source_id"] for r in rels[0]["evidence_refs"]] == ["ac.wb", "ac.ghost"] and "evidence_refs" not in rels[1]
    assert "evidence_refs" not in ctx["domain_pack"]["domain_specific_support_objects"]["macro_transmission_links"][0]
    assert ctx["evidence"]["values"][0]["evidence_refs"][0]["location"] == "p. 4"
    assert "evidence_refs" not in ctx["evidence"]["values"][1]
    assert [f["source"] for f in ctx["manifest"]["load_order"]] == ["yours", "this export: evidence", "this export: sources",
                                                                    "this export: forecast"]
    assert ctx["manifest"]["load_order"][2]["file"] == "source_catalogue_axelrod_pack_x.json" == v4.source_catalogue_file(
        ctx["domain_pack"])
    sup = ctx["domain_pack"]["domain_specific_support_objects"]
    assert sup["schema_gaps"][-1] is v4.SOURCE_GAP and sup["citation_gaps"] is doc["citation_gaps"]
    assert doc["counts"] == {"sources": 3, "resolved_ids": 2, "unresolved_ids": 1, "cited_links": 1, "cited_values": 1,
                             "claims_without_citation": 1, "unknown_citation_keys": 1}
    assert [x["source_id"] for x in doc["sources"]] == ["ac.ir", "ac.wb", "bt.co"] and ctx["sources"] is doc
    assert doc["citation_gaps"]["catalogue_problems"] == s["problems"]


# -- inputs -----------------------------------------------------------------------------------------------------------------
def test_inputs_are_grouped_by_name_and_status():
    a = Transition(mechanism="m", unresolved=["hedge notional", {"input": "ladder", "status": "found_not_connected",
                                                                  "found_in": ["s.a"]}])
    b = Transition(mechanism="m", unresolved=[{"input": "ladder", "status": "found_not_connected", "found_in": ["s.b"]},
                                              {"input": "ladder", "status": "not_disclosed_in_reviewed_sources",
                                               "searched": ["s.c"]}])
    rows = input_needs([("x1", a), ("x2", b), ("x3", None)])
    assert [(r["input"], r["status"], r["interaction_ids"]) for r in rows] == [
        ("hedge notional", "not_yet_reviewed", ["x1"]), ("ladder", "found_not_connected", ["x1", "x2"]),
        ("ladder", "not_disclosed_in_reviewed_sources", ["x2"])]
    assert rows[1]["found_in"] == ["s.a", "s.b"] and rows[2]["searched"] == ["s.c"]


def test_a_companys_inputs_by_status(graph):
    ins = inputs_by_status(graph, "acme")
    assert ins["counts"] == {"found_connected": 0, "found_not_connected": 0, "found_proxy": 0, "not_yet_reviewed": 1, "disclosed_not_supplied": 0,
                             "not_disclosed_in_reviewed_sources": 0}
    assert ins["not_yet_reviewed"] == ["eligible import volume"] and ins["inputs"][0]["interaction_ids"] == ["t1", "t2"]


def test_query_terms_and_scoring():
    assert query_terms("The eligible import volumes", [" CBU units ", ""]) == (
        ["the eligible import volumes", "cbu units"], ["eligible", "import", "volume"])
    phrases, words = query_terms("eligible import volume")
    assert score_passage("Eligible import volume: 1.2m units", phrases, words) == (4.0, ["eligible import volume",
                                                                                         "eligible", "import", "volume"])
    assert score_passage("import volumes rose", phrases, words)[0] == pytest.approx(2 / 3)    # two of three words
    assert score_passage("imports only", phrases, words) == (0.0, [])                         # one of three: not enough
    assert score_passage("anything", ["x"], []) == (0.0, [])
    assert score_passage("Hedging policy", *query_terms("hedging"))[0] == pytest.approx(4.0)
    assert score_passage("the hedge", [], ["hedge"])[0] == 1.0                               # the only word


def test_passages_name_their_sheet_or_page():
    xl = NS(segments=[NS(text="Sheet: Seg\nAuto | 10\n\nFinance | 2", page=1, label="Seg"),
                      NS(text="first line", page=3, label=""), NS(text="plain", page=None, label="")])
    assert passages("m.xlsx", xl) == [("m.xlsx", "Seg, line 1", "Sheet: Seg"), ("m.xlsx", "Seg, line 2", "Auto | 10"),
                                      ("m.xlsx", "Seg, line 4", "Finance | 2"), ("m.xlsx", "page 3, line 1", "first line"),
                                      ("m.xlsx", "text, line 1", "plain")]


def test_the_search_suggests_a_status_per_input_and_is_deterministic():
    docs = [("notes.md", parse(b"# Notes\n\nNorth America eligible import volume was 410k units.\n\n"
                               b"Import volume guidance: flat.", "notes.md")),
            ("other.txt", parse(b"Nothing about it here.", "other.txt"))]
    needs = [{"input": "eligible import volume", "status": "not_yet_reviewed", "interaction_ids": ["t1"],
              "searched": [], "found_in": []},
             {"input": "hedge ratio", "status": "not_yet_reviewed", "interaction_ids": ["t2"], "searched": [],
              "found_in": []},
             {"input": "bound", "status": "found_connected", "interaction_ids": ["t3"], "searched": [], "found_in": ["x"]}]
    rows = search_inputs(needs, docs, {"hedge ratio": ["hedged share"]}, top=1)
    assert [r["input"] for r in rows] == ["eligible import volume", "hedge ratio"]          # connected: not searched
    hit, miss = rows
    assert hit["suggested_status"] == "found_not_connected" and hit["suggested_found_in"] == ["notes.md"]
    assert len(hit["candidates"]) == 1 and hit["candidates"][0]["location"] == "text, line 3"
    assert hit["candidates"][0]["passage"].startswith("North America eligible import volume")
    assert miss["suggested_status"] == "not_disclosed_in_reviewed_sources"
    assert miss["suggested_searched"] == ["notes.md", "other.txt", "corpus: hedge ratio", "corpus: hedged share"]
    assert search_inputs(needs, docs, {"hedge ratio": ["hedged share"]}, top=1) == rows
    assert search_inputs(needs[:1], [])[0]["suggested_status"] == "not_disclosed_in_reviewed_sources"
    md = search_markdown("acme", rows)
    assert md.startswith("# acme: input search") and "## eligible import volume" in md
    assert "| 4.0 | notes.md | text, line 3 | North America" in md and "Nothing found in 2 file(s)." in md


# -- reconciliation -------------------------------------------------------------------------------------------------------
def test_reconciliation_at_the_models_levels_flags_parts_that_do_not_add_up(graph):
    rows = {r["composition_id"]: r for r in reconcile(graph)}
    c1 = rows["C1"]                      # auto 10 + finance 10 + elims -1 against profit 10
    assert c1["total_level"] == pytest.approx(10.0) and c1["sum"] == pytest.approx(19.0)
    assert c1["difference"] == pytest.approx(-9.0) and c1["relative_difference"] == pytest.approx(-0.9)
    assert c1["status"] == "flag" and c1["residual_to_close"] == pytest.approx(-9.0) and c1["unit"] == "bn/yr"
    assert c1["parts"] == ["acme.auto", "acme.finance", "acme.elims"] and c1["unit_mismatches"] == []
    assert rows["C2"]["sum"] == pytest.approx(20.0)


def test_reconciliation_at_given_levels(graph):
    g = graph.model_copy(deep=True)
    g.compositions["C1"] = g.compositions["C1"].model_copy(update={"residual": "acme.home"})
    lv = {"acme.profit": 10.0, "acme.auto": 6.0, "acme.finance": 4.5, "acme.elims": -0.5, "acme.home": 0.02}
    c1 = next(r for r in reconcile(g, lv) if r["composition_id"] == "C1")
    assert c1["status"] == "ok" and c1["relative_difference"] == pytest.approx(-0.002)       # within 0.5%
    assert c1["residual_to_close"] == pytest.approx(0.0)                                     # the residual's 0.02 - 0.02
    assert next(r for r in reconcile(g, lv, tolerance=0.001) if r["composition_id"] == "C1")["status"] == "flag"
    c2 = next(r for r in reconcile(g, lv) if r["composition_id"] == "C2")
    assert c2["missing_levels"] == ["acme.na"] and c2["status"] == "blocked" and c2["blocked_by"] == ["acme.na"]


def test_a_part_with_a_negative_accounting_link_subtracts(graph):
    g = graph.model_copy(deep=True)
    for iid in ("a1", "a2"):                         # finance (as a cost) and the eliminations, held positive
        i = g.interactions[iid]
        g.interactions[iid] = i.model_copy(update={"forward": i.forward.model_copy(update={
            "effect": i.forward.effect.model_copy(update={"mu": -0.33})})})
    g.compositions["C1"] = g.compositions["C1"].model_copy(update={"residual": "acme.finance", "members": ["acme.auto"]})
    lv = {"acme.profit": 10.0, "acme.auto": 13.0, "acme.finance": 2.0, "acme.elims": 0.5}
    c1 = next(r for r in reconcile(g, lv) if r["composition_id"] == "C1")
    assert c1["subtracted"] == ["acme.finance", "acme.elims"] and c1["sum"] == pytest.approx(10.5)
    assert c1["difference"] == pytest.approx(-0.5) and c1["status"] == "flag"
    assert c1["residual_to_close"] == pytest.approx(2.5)                     # a larger cost closes the gap
    lv["acme.finance"] = 2.5
    assert next(r for r in reconcile(g, lv) if r["composition_id"] == "C1")["status"] == "ok"


def test_reconciliation_of_a_zero_total_a_unit_mismatch_and_no_levels(graph):
    g = graph.model_copy(deep=True)
    g.subentities["acme.na"] = g.subentities["acme.na"].model_copy(update={"unit": "%"})
    rows = {r["composition_id"]: r for r in reconcile(g, {"acme.profit": 0.0, "acme.home": 0.0, "acme.na": 0.0})}
    assert rows["C2"]["relative_difference"] == 0.0 and rows["C2"]["unit_mismatches"] == ["acme.na"]
    assert rows["C2"]["status"] == "flag"
    z = reconcile(g, {"acme.profit": 0.0, "acme.home": 1.0, "acme.na": 0.0})
    assert next(r for r in z if r["composition_id"] == "C2")["relative_difference"] is None
    none = next(r for r in reconcile(g, {}) if r["composition_id"] == "C1")
    assert none["sum"] is None and none["difference"] is None and none["status"] == "blocked"
    g.compositions["C2"] = g.compositions["C2"].model_copy(update={"additive": False})
    assert [r["composition_id"] for r in reconcile(g, {})] == ["C1"]                        # non-additive: skipped


def test_model_levels_skip_a_value_without_a_mean(graph):
    g = graph.model_copy(deep=True)
    g.subentities["acme.auto"] = g.subentities["acme.auto"].model_copy(update={"posterior": NS(mean=lambda: 1 / 0)})
    lv = model_levels(g)
    assert "acme.auto" not in lv and lv["acme.profit"] == pytest.approx(10.0)
    med = model_levels(graph, "median")
    assert med["acme.profit"] == pytest.approx(10.0) and med["acme.elims"] == pytest.approx(-1.0)   # Gaussian: equal


def test_baseline_levels_are_each_values_latest_observe():
    bundle = {"format": "axelrod.import/v1", "items": [
        {"published_at": "2026-05-02", "signals": [{"type": "observe", "value_of": "a.x", "value": 2},
                                                   {"type": "move", "value_of": "a.y", "value": 9},
                                                   {"type": "observe", "value_of": "a.z"}]},
        {"published_at": "2026-05-01", "signals": [{"type": "observe", "value_of": "a.x", "value": 1},
                                                   {"type": "observe", "value_of": "a.y", "value": 3}]},
        {"published_at": "2026-05-02", "signals": [{"type": "observe", "value_of": "a.x", "value": 4}]},
        {"signals": None}]}
    assert bundle_levels(bundle) == {"a.x": 4.0, "a.y": 3.0}
    assert bundle_levels({}) == {}
