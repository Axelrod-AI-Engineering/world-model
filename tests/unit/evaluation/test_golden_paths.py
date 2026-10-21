"""The golden-bank harness, the remaining paths, on an invented company ("Acme") with invented figures: the v1 reader,
case loading, identity forms, the delta engine's edge cases, baselines and the grader's every outcome."""

from __future__ import annotations

from axelrod_wm.evaluation.golden import (
    Answer,
    Case,
    Model,
    Responder,
    V1Reader,
    _num,
    comp_parts,
    dump,
    eval_identity,
    grade,
    load_cases,
    run,
    summary_line,
)


# -- the v1 reader over a scripted client ---------------------------------------------------------------------------------
class Resp:
    def __init__(self, body, status=200):
        self._b, self.status_code = body, status

    def json(self):
        return self._b


class Client:
    """Scripted GETs: a path maps to a body, or to a list of bodies served one per call (paging)."""

    def __init__(self, routes):
        self.routes, self.seen = routes, []

    def get(self, path, params=None):
        self.seen.append((path, params))
        r = self.routes.get(path)
        if isinstance(r, list):
            r = r.pop(0)
        return r if r is not None else Resp({}, 404)


def test_v1_reader_reads_each_resource_and_tolerates_misses():
    base = "/v1/world-models/wm1"
    c = Client({
        "/v1/world-models": Resp({"data": [{"id": "wm1"}]}),
        base + "/entities/acme/construction": Resp({"data": {"attributes": []}}),
        base + "/entities/zed/construction": Resp({}, 404),
        base + "/relationships": [Resp({"data": [{"id": "a"}], "meta": {"next_cursor": "c2"}}), Resp({"data": [{"id": "b"}]})],
        base + "/entities/acme/traces": Resp({"data": {"routes": []}}),
        base + "/search": Resp({"data": [{"ref": "acme.x"}]}),
        base + "/entities/acme/attributes/rev": Resp({"data": {"level": {"mean": 1.0}}}),
        base + "/entities/acme/attributes/rev/observations": Resp({"data": [{"value": 1}]}),
    })
    rd = V1Reader(c)
    assert rd.base == base
    assert rd.construction("acme") == {"attributes": []} and rd.construction("zed") == {}
    assert set(rd.links("acme")) == {"a", "b"}
    assert rd.trace("acme", "acme.x") == {"routes": []}
    assert len(rd.search("q")) == 2
    assert rd.attribute("acme.rev")["observations"] == [{"value": 1}]
    assert rd.attribute("acme.gone") is None
    assert any("?" in x for x in rd.calls) and "/relationships" in rd.calls
    assert V1Reader(Client({}), "wm9").base == "/v1/world-models/wm9"
    assert V1Reader(Client({base + "/relationships": Resp({}, 500)}), "wm1").links("acme") == {}


# -- cases ----------------------------------------------------------------------------------------------------------------
def test_load_cases_reads_seeds_and_filters(tmp_path):
    p = tmp_path / "bank.yaml"
    p.write_text("seeds:\n  - {id: A1, question: q1}\n  - {id: A2, category: c, question: q2, entity: acme, fixture: {hold: [x]},"
                 " grading: {evidence: {ids: [x]}}}\n")
    cases = load_cases(p)
    assert [c.id for c in cases] == ["A1", "A2"] and cases[0].entity == "toyota" and cases[1].entity == "acme"
    assert [c.id for c in load_cases(p, only=["A2"])] == ["A2"]
    (tmp_path / "empty.yaml").write_text("")
    assert load_cases(tmp_path / "empty.yaml") == []


# -- small helpers --------------------------------------------------------------------------------------------------------
def test_identity_forms_and_helpers():
    wavg = {"form": "weighted_average", "terms": [{"value": "a", "weight": 0.25}, {"value": "b"}]}
    assert eval_identity(wavg, {"a": 4.0, "b": 8.0}) == 1.0
    ratio = {"form": "ratio", "coefficient": 2, "terms": [{"value": "n", "role": "numerator"}, {"value": "d", "role": "denominator"}]}
    assert eval_identity(ratio, {"n": 1.0, "d": 0.0}) is None
    assert eval_identity({"form": "mystery", "terms": []}, {}) is None
    assert _num("x") is None and _num("2") == 2.0 and _num(None) is None
    c = {"member_attribute_ids": ["m"], "residual_attribute_id": "r", "eliminations_attribute_id": "e"}
    assert comp_parts(c) == ["m", "r", "e"] and comp_parts({}) == []


def test_answer_records_are_never_duplicated():
    a = Answer(case_id="X")
    a.add_calc(key="k", result=1)
    a.add_calc(key="k", result=2)
    a.note("n")
    a.note("n")
    a.unsized(link="l", value=None)
    a.unsized(link="l", value=None)
    a.mech(link="l")
    a.mech(link="l")
    assert len(a.calculations) == len(a.notes) == len(a.unsized_steps) == len(a.mechanisms) == 1 and a.calc("nope") is None


# -- a scripted reader over any construction ------------------------------------------------------------------------------
def lk(lid, s, t, type_="causal", slope=None, sign=None, identity=None, transition=None, profile=True):
    x = {"id": lid, "source_attribute_id": s, "target_attribute_id": t, "type": type_, "identity_id": identity}
    if sign:
        x["sign"] = sign
    if profile:
        x["profile"] = {"native_slope": slope}
    if transition is not None:
        x["transition"] = transition
    return x


class Reader:
    def __init__(self, con, links, hits=(), attrs=None, traces=None):
        self.con, self._links, self.hits, self.attrs, self.traces = con, links, list(hits), attrs or {}, traces or {}
        self.calls: list[str] = []

    def construction(self, entity_id):
        return self.con

    def links(self, entity_id):
        return {x["id"]: x for x in self._links}

    def trace(self, entity_id, start):
        return self.traces.get(start)

    def search(self, q):
        return self.hits

    def attribute(self, value_id):
        return self.attrs.get(value_id)


def answer(con, links, fx, **kw):
    r = Reader(con, links, **kw)
    return Responder(r).answer({"id": "Q", "question": "q", "fixture": fx, "entity": "ac"})


def test_model_classifies_edges_and_signs():
    con = {"identities": [{"id": "i", "target": "ac.t", "form": "product", "terms": []}],
           "compositions": [{"id": "d", "role": "driving", "total_attribute_id": "ac.t2", "member_attribute_ids": ["ac.p"]},
                            {"id": "r", "role": "reconciling", "total_attribute_id": "ac.t2", "member_attribute_ids": ["ac.p", "ac.q"]}]}
    m = Model(con, {})
    assert ("ac.q", "ac.t2") in m.reconciling_edges and ("ac.p", "ac.t2") not in m.reconciling_edges
    assert m.edge_kind({"source_attribute_id": "ac.s", "target_attribute_id": "ac.t", "identity_id": "i"}) == "identity"
    assert m.edge_kind({"source_attribute_id": "ac.q", "target_attribute_id": "ac.t2"}) == "view"
    assert Model.sign({"transition": {"sign": "-"}}) == -1 and Model.sign({}) == 1


def test_no_construction_and_no_hits_still_answers():
    a = answer({}, [], {"outputs": ["ac.x"]}, hits=[{"kind": "attribute"}, {"ref": "ac.here"}, {"ref": "ac.here"}])
    assert a.retrieved_ids == ["ac.here", "ac.x"]


def test_engine_stops_without_outputs_and_reuses_the_model_per_entity():
    links = [lk("l1", "ac.u", "ac.o", slope=1.0)]
    r = Reader({}, links)
    resp = Responder(r)
    a = resp.answer({"id": "Q", "question": "q", "fixture": {"deltas": {"ac.u": 1.0}}, "entity": "ac"})
    resp.answer({"id": "Q2", "question": "q", "fixture": {"deltas": {"ac.u": 1.0}}, "entity": "ac"})
    assert a.calculations == [] and len(resp._m) == 1
    assert Model({}, {}).edge_kind({"type": "stock_flow", "source_attribute_id": "a", "target_attribute_id": "b"}) == "stock_flow"


def test_a_held_value_is_not_expanded_and_unselected_links_are_not_applicable():
    links = [lk("l1", "ac.u", "ac.h", slope=2.0), lk("l2", "ac.h", "ac.o", slope=3.0),
             lk("l3", "ac.s", "ac.o", slope=1.0, transition={"mechanism": "s moves o"}), lk("l4", "ac.s", "ac.z", slope=1.0)]
    a = answer({}, links, {"deltas": {"ac.u": 1.0}, "hold": ["ac.h"], "outputs": ["ac.o"]})
    assert a.states["ac.h"] == "held constant"
    a = answer({}, links, {"shock": {"ac.s": 1.0}, "outputs": ["ac.o"]})
    assert a.calc("delta ac.o")["result"] == 1.0 and a.states["l4"] == "not applicable"


def test_unequal_paths_wait_for_their_sources_and_partial_sizes_are_reported():
    links = [lk("a", "ac.u", "ac.a", slope=1.0), lk("b", "ac.a", "ac.b", slope=1.0), lk("c", "ac.b", "ac.o", slope=1.0),
             lk("d", "ac.u", "ac.o", slope=2.0), lk("e", "ac.u", "ac.p", slope=1.0), lk("f", "ac.w", "ac.p", slope=None),
             lk("g", "ac.w", "ac.q", slope=None)]
    a = answer({}, links, {"deltas": {"ac.u": 1.0, "ac.w": 1.0}, "outputs": ["ac.o", "ac.p", "ac.q"]})
    assert a.calc("delta ac.o")["result"] == 3.0
    assert a.calc("delta ac.p")["result"] == 1.0 and a.calc("delta ac.p")["partial_excludes"] == ["f"]
    assert a.calc("delta ac.q")["result"] is None
    assert any("the sized part only" in n for n in a.notes) and any("represented but unsized" in n for n in a.notes)


def test_an_unmoved_identity_leaves_its_downstream_value_unsized_but_not_unknown():
    con = {"identities": [{"id": "i", "form": "product", "target": "ac.x", "terms": [
        {"value": "ac.a", "role": "factor"}, {"value": "ac.b", "role": "factor"}]}]}
    links = [lk("l1", "ac.a", "ac.x", "identity"), lk("l2", "ac.x", "ac.o", slope=1.0)]
    a = answer(con, links, {"deltas": {"ac.a": 0.0}, "outputs": ["ac.o"]})
    assert a.calc("delta ac.o") is None and a.calc("delta ac.x") is None


def test_identities_without_levels_or_with_unknown_terms_leave_the_target_unknown():
    con = {"identities": [
        {"id": "i1", "form": "product", "target": "ac.x", "terms": [{"value": "ac.a", "role": "factor"}, {"value": "ac.b", "role": "factor"}]},
        {"id": "i2", "form": "ratio", "target": "ac.r", "terms": [{"value": "ac.n", "role": "numerator"}, {"value": "ac.d", "role": "denominator"}]},
        {"id": "i3", "form": "difference", "target": "ac.net", "terms": [{"value": "ac.rev", "role": "total"}, {"value": "ac.cost", "role": "deduction"}]},
    ]}
    links = [lk("la", "ac.a", "ac.x", "identity"), lk("lb", "ac.b", "ac.x", "identity"), lk("ln", "ac.n", "ac.r", "identity"),
             lk("ld", "ac.d", "ac.r", "identity"), lk("lr", "ac.u", "ac.rev", slope=1.0), lk("lc", "ac.m", "ac.cost", slope=None),
             lk("l1", "ac.rev", "ac.net", "identity"), lk("l2", "ac.cost", "ac.net", "identity")]
    a = answer(con, links, {"deltas": {"ac.a": 1.0, "ac.b": 1.0}, "outputs": ["ac.x"]})
    assert a.calc("delta ac.x")["result"] is None and {s["value"] for s in a.unsized_steps} == {"ac.a", "ac.b"}
    a = answer(con, links, {"levels": {"ac.n": 1.0, "ac.d": 0.0}, "deltas": {"ac.n": 1.0}, "outputs": ["ac.r"]})
    assert a.calc("delta ac.r")["result"] is None
    a = answer(con, links, {"deltas": {"ac.u": 1.0, "ac.m": 1.0}, "outputs": ["ac.net"]})
    assert a.calc("delta ac.net")["result"] is None
    a = answer(con, links, {"levels": {"ac.cost": 5.0}, "deltas": {"ac.u": 2.0}, "outputs": ["ac.net"]})
    assert a.calc("delta ac.net")["result"] == 2.0       # linear in the moving term: its base level drops out
    a = answer(con, links, {"levels": {"ac.a": 2.0, "ac.b": 3.0}, "deltas": {"ac.a": 1.0}, "outputs": ["ac.x"]})
    assert a.calc("delta ac.x")["result"] == 3.0 and a.calc("delta ac.x")["parts"] is None


def test_a_feedback_loop_is_cut_and_listed():
    links = [lk("l1", "ac.u", "ac.a", slope=1.0), lk("l2", "ac.a", "ac.b", slope=1.0), lk("l3", "ac.b", "ac.a", slope=0.5),
             lk("l4", "ac.b", "ac.o", slope=1.0)]
    a = answer({}, links, {"deltas": {"ac.u": 1.0}, "outputs": ["ac.o"]})
    assert a.calc("delta ac.o")["result"] == 1.0
    assert any("feedback loop" in s["why"] for s in a.unsized_steps) and a.states["l3"] == "unknown or unimplemented"


def test_reconciling_views_without_moved_parts_are_skipped_and_three_term_products_split_the_movers():
    con = {"compositions": [{"id": "ac.drv", "role": "driving", "total_attribute_id": "ac.t", "member_attribute_ids": ["ac.m1"]},
                            {"id": "ac.rec", "role": "reconciling", "total_attribute_id": "ac.t", "member_attribute_ids": ["ac.r1", "ac.r2"]}],
           "identities": [{"id": "i", "form": "product", "target": "ac.rev", "terms": [
               {"value": "ac.a", "role": "factor"}, {"value": "ac.b", "role": "factor"}, {"value": "ac.c", "role": "factor"}]}]}
    links = [lk("l1", "ac.m1", "ac.t", "accounting", 1.0)]
    a = answer(con, links, {"deltas": {"ac.m1": 2.0}, "outputs": ["ac.t"]})
    assert a.calc("delta ac.t")["result"] == 2.0 and a.calc("check ac.rec") is None
    irev = [lk("a", "ac.a", "ac.rev", "identity"), lk("b", "ac.b", "ac.rev", "identity"), lk("c", "ac.c", "ac.rev", "identity")]
    a = answer(con, irev, {"levels": {"ac.a": 2.0, "ac.b": 3.0, "ac.c": 4.0}, "deltas": {"ac.a": 1.0, "ac.b": 1.0, "ac.c": 0.0},
                           "outputs": ["ac.rev"]})
    assert a.calc("delta ac.rev")["result"] == 3 * 4 * 4 - 24 and a.calc("part ac.rev ac.c") is None


def test_clocks_skip_outputs_and_terms_that_cannot_reprice():
    def prod(i, t, x, y):
        return {"id": i, "form": "product", "target": t, "coefficient": 0.5, "terms": [{"value": x, "role": "factor"}, {"value": y, "role": "factor"}]}
    con = {"identities": [
        prod("p1", "ac.skip1", "ac.k1", "ac.k2"), prod("p2", "ac.skip2", "ac.yield", "ac.nobal"), prod("p3", "ac.inc", "ac.assets", "ac.yield"),
        {"id": "r1", "form": "ratio", "target": "ac.rat", "terms": []},
        {"id": "d1", "form": "difference", "target": "ac.dskip", "terms": [
            {"value": "ac.skip1", "role": "total"}, {"value": "ac.raw", "role": "deduction"}, {"value": "ac.rat", "role": "deduction"},
            {"value": "ac.skip2", "role": "deduction"}]},
        {"id": "d2", "form": "difference", "target": "ac.net", "terms": [{"value": "ac.inc", "role": "total"}]},
    ]}
    fx = {"levels": {"ac.assets": 100.0}, "clocks": {"ac.yield": {"shock": 1.0}}, "outputs": ["ac.nothing", "ac.skip1", "ac.dskip", "ac.net"]}
    a = answer(con, [], fx)
    assert a.calc("delta ac.net")["result"] == 50.0 and a.calc("delta ac.dskip") is None


def test_stock_flow_periods_solve_each_missing_term_and_skip_underdetermined_periods():
    con = {"stock_flows": [{"id": "sf", "stock": "ac.stock", "flows": [
        {"value": "ac.made", "role": "inflow", "interaction_id": "lm"}, {"value": "ac.sold", "role": "outflow"}]}]}
    links = [lk("lm", "ac.src", "ac.made", slope=1.0, transition={"mechanism": "supply"})]
    periods = [{"label": "P1", "deltas": {"ac.made": 10.0, "ac.sold": 4.0}}, {"label": "P2", "deltas": {"ac.stock": 2.0, "ac.sold": 1.0}},
               {"label": "P3", "deltas": {}}]
    a = answer(con, links, {"periods": periods, "outputs": ["ac.stock", "ac.nostock"]})
    assert a.calc("delta ac.stock [P1]")["result"] == 6.0 and a.calc("delta ac.made [P2]")["result"] == 3.0
    assert any("P3" in n for n in a.notes) and any(m.get("via") == "feeds a flow" for m in a.mechanisms)
    a = answer(con, links, {"periods": [{"label": "P", "deltas": {}}], "outputs": ["ac.stock"]})
    assert a.calc("balance check sf") is None


def test_offsets_name_a_missing_link():
    a = answer({}, [], {"offsets": {"nope": {"gross": 1.0}}})
    assert any("no such link" in n for n in a.notes)


def obs(v, at="2026-03-31T00:00:00Z"):
    return {"value": v, "occurred_at": at}


def baseline_con(extra_comp=True):
    comps = [{"id": "ac.reg", "role": "driving", "additive": True, "total_attribute_id": "ac.tot", "member_attribute_ids": ["ac.e", "ac.w"]}]
    if extra_comp:
        comps.append({"id": "ac.biz", "role": "reconciling", "additive": True, "total_attribute_id": "ac.tot", "member_attribute_ids": ["ac.x"]})
    return {"compositions": comps}


def test_baseline_compares_state_to_the_dated_actual_and_checks_each_view():
    attrs = {"ac.tot": {"level": {"mean": 3.0}, "observations": [obs(3.0)]}, "ac.e": {"observations": [obs(1.0)]},
             "ac.w": {"observations": [obs(2.0)]}, "ac.x": {"observations": [obs(3.0)]}}
    a = answer(baseline_con(), [], {}, attrs=attrs, hits=[{"ref": "ac.reg"}])
    assert a.calc("view ac.reg @2026-03-31")["result"] == 3.0 and not any("not the dated actual" in n for n in a.notes)
    assert a.retrieved_ids[0] == "ac.reg" and "ac.tot" in a.retrieved_ids and any("never added" in n for n in a.notes)
    attrs["ac.tot"]["level"] = {}
    a = answer(baseline_con(), [], {}, attrs=attrs)
    assert a.calc("state ac.tot")["result"] is None


def test_baseline_notes_missing_observations_and_unchecked_views():
    attrs = {"ac.tot": {"level": {"mean": 3.0}, "observations": []}}
    a = answer(baseline_con(False), [], {}, attrs=attrs, hits=[{"ref": "ac.tot"}])
    assert any("no dated observation" in n for n in a.notes) and any("no period with every part" in n for n in a.notes)
    assert not any("one driving view" in n for n in a.notes)
    attrs = {"ac.tot": {"observations": [obs("n/a")]}, "ac.e": {"observations": [obs("n/a")]}, "ac.w": {"observations": [obs(2.0)]}}
    a = answer(baseline_con(False), [], {}, attrs=attrs)
    assert a.calc("view ac.reg @2026-03-31") is None and not any("no period" in n for n in a.notes)


def test_a_used_link_without_timing_adds_no_timing_entry():
    a = answer({}, [lk("l1", "ac.u", "ac.o", slope=1.0, transition={"mechanism": "m"})], {"deltas": {"ac.u": 1.0}, "outputs": ["ac.o"]})
    assert a.timing == []


# -- the grader -----------------------------------------------------------------------------------------------------------
def test_grader_forbidden_moves_each_fail_the_mechanism():
    ans = Answer(case_id="G", calculations=[{"key": "k", "result": 2.0}, {"key": "z", "result": 0}],
                 unsized_steps=[{"state": "measured zero"}], mechanisms=[{"link": "l", "sized": False}])
    spec = {"mechanism": {"required": ["l"], "forbidden": [{"kind": "zero_for_unsized"}, {"kind": "calculation_key", "key": "k"},
                                                            {"kind": "numeric_zero", "key": "z"}, {"kind": "sized_link", "link": "l"}]}}
    g = grade(ans, spec)
    assert g["mechanism"] == "Fail" and len(g["critical"]) == 3


def test_grader_calculation_outcomes_and_timing_checks():
    ans = Answer(case_id="G", calculations=[{"key": "unk", "result": None, "state": "unknown or unimplemented"}, {"key": "none", "result": None},
                                            {"key": "mag", "result": 5.0}],
                 unsized_steps=[{"state": "unknown or unimplemented"}], timing=[{"link": "l"}], notes=["Held Constant here"])
    g = grade(ans, {"calculation": [{"key": "unk", "expected_state": "unknown or unimplemented"}, {"key": "absent", "expected_state": "x"},
                                    {"key": "none", "expected": 1.0}, {"key": "mag", "expected": 6.0, "critical": "wrong unit"},
                                    {"key": "mag", "expected": 7.0}],
                    "timing": {"timing_entries": True, "unsized_listed": True, "notes_contain": ["held constant", "missing note"]}})
    assert g["calculation"] == "Partial"
    assert {x["status"] for x in g["reasons"]["calculation"]} == {"ok", "wrong", "missing"}
    assert g["critical"] == [{"dimension": "calculation", "key": "mag", "kind": "wrong unit"}]
    assert g["timing"] == "Partial" and [c["ok"] for c in g["reasons"]["timing"]] == [True, True, True, False]


class Bare:
    """A reader with no call log."""

    def construction(self, entity_id):
        return {}

    def links(self, entity_id):
        return {}

    def trace(self, entity_id, start):
        return {}

    def search(self, q):
        return []

    def attribute(self, value_id):
        return None


def test_run_summarises_and_dumps(tmp_path):
    ok = Case(id="C1", category="c", question="q", fixture={"hold": ["ac.h"]}, entity="ac", grading={"evidence": {"ids": ["ac.h"]}})
    bad = Case(id="C2", category="c", question="q", entity="ac",
               grading={"calculation": [{"key": "state ac.x", "expected": 1.0}], "mechanism": {"required": ["gone"]}})
    res = run([ok, bad], Bare())
    assert summary_line(res[0]) == "C1: evidence Pass, mechanism Not tested, calculation Not tested, timing Not tested"
    wrong = {"case": "C3", "grade": {"critical": [{}], "evidence": "Fail", "mechanism": "Fail", "calculation": "Fail", "timing": "Fail"}}
    assert summary_line(wrong).endswith("; CRITICAL 1")
    dump(res, tmp_path / "out.json")
    assert (tmp_path / "out.json").read_text().startswith("[")
