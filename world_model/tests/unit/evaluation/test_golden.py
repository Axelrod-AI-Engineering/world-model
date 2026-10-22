"""The golden-bank harness on synthetic cases only (no client figures): the responder answers from model reads, the
grader scores four outcomes apart and lists critical failures, and unsized steps are never counted as zero."""

from __future__ import annotations

from axelrod_wm.evaluation.golden import Answer, Case, Responder, eval_identity, grade, run


def link(lid, s, t, type_="causal", slope=None, sign="positive", identity=None):
    return {"id": lid, "source_attribute_id": s, "target_attribute_id": t, "type": type_, "sign": sign,
            "identity_id": identity, "profile": {"native_slope": slope, "hedge": "unknown", "pass_through": "unknown"},
            "transition": {"mechanism": f"{s} moves {t}", "timing": {"onset": "same period", "recognition": "in the period"},
                           "evidence": {"sources": ["src.a"]}}}


class FakeReader:
    """A tiny company: units x price = revenue; two regions add to profit (driving), a business view reconciles;
    a market drives units through an unsized link; a stock-flow; a rate module with two clocks."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.con = {
            "attributes": [{"id": "co.price", "unit": "k/unit"}, {"id": "co.profit", "unit": "bn"},
                           {"id": "co.share_price", "concept": "asset_price"}],
            "identities": [
                {"id": "id.rev", "form": "product", "target": "co.revenue", "coefficient": 1.0,
                 "terms": [{"value": "co.units", "role": "factor", "interaction_id": "l_units_rev"},
                           {"value": "co.price", "role": "factor", "interaction_id": "l_price_rev"}]},
                {"id": "id.inc", "form": "product", "target": "co.inc", "coefficient": 0.01,
                 "terms": [{"value": "co.assets", "role": "factor"}, {"value": "co.yield", "role": "factor"}]},
                {"id": "id.exp", "form": "product", "target": "co.exp", "coefficient": 0.01,
                 "terms": [{"value": "co.debt", "role": "factor"}, {"value": "co.rate", "role": "factor"}]},
                {"id": "id.nii", "form": "difference", "target": "co.nii",
                 "terms": [{"value": "co.inc", "role": "total"}, {"value": "co.exp", "role": "deduction"}]},
            ],
            "stock_flows": [{"id": "sf.stock", "stock": "co.stock",
                             "flows": [{"value": "co.made", "role": "inflow", "interaction_id": "l_made"},
                                       {"value": "co.sold", "role": "outflow", "interaction_id": "l_sold"}]}],
            "compositions": [
                {"id": "comp.regions", "role": "driving", "additive": True, "total_attribute_id": "co.profit",
                 "member_attribute_ids": ["co.east", "co.west"]},
                {"id": "comp.business", "role": "reconciling", "additive": True, "total_attribute_id": "co.profit",
                 "member_attribute_ids": ["co.autos", "co.finance"]},
            ],
            "paths": [{"id": "path.alloc", "steps": [{"relationship_id": "l_support_east"}]}],
        }
        self._links = {x["id"]: x for x in [
            link("l_units_rev", "co.units", "co.revenue", "identity", 0.5, identity="id.rev"),
            link("l_price_rev", "co.price", "co.revenue", "identity", 0.5, identity="id.rev"),
            link("l_cost_east", "co.cost", "co.east", slope=-1.0, sign="negative"),
            link("l_support_east", "co.support", "co.east", slope=1.0),
            link("l_support_west", "co.support", "co.west", slope=-1.0, sign="negative"),
            link("l_east", "co.east", "co.profit", "accounting", 0.99),
            link("l_west", "co.west", "co.profit", "accounting", 1.01),
            link("l_autos", "co.autos", "co.profit", "accounting", None),
            link("l_cost_autos", "co.cost", "co.autos", slope=-1.0, sign="negative"),
            link("l_market_units", "mkt.size", "co.units", slope=None),
            link("l_units_profit", "co.units", "co.east", slope=None),
            link("l_profit_price", "co.profit", "co.share_price", slope=0.3),
            link("l_made", "co.made", "co.stock", "stock_flow"),
            link("l_sold", "co.sold", "co.stock", "stock_flow", sign="negative"),
            link("l_input_cost", "co.input", "co.cost", slope=None),
        ]}

    def construction(self, entity_id):
        return self.con

    def links(self, entity_id):
        return self._links

    def trace(self, entity_id, start):
        steps = [{"relationship_id": x["id"], "source_attribute_id": x["source_attribute_id"],
                  "target_attribute_id": x["target_attribute_id"],
                  "calibration": "calibrated" if x["profile"]["native_slope"] is not None else "uncalibrated"}
                 for x in self._links.values() if x["source_attribute_id"] == start]
        return {"routes": [{"steps": [s]} for s in steps]}

    def search(self, q):
        return [{"kind": "attribute", "ref": "co.profit"}, {"kind": "attribute", "ref": "other.thing"}]

    def attribute(self, value_id):
        obs = {"co.profit": 3.0, "co.east": 1.0, "co.west": 2.0, "co.autos": 2.5, "co.finance": 0.5}
        if value_id not in obs:
            return {"level": {"mean": 1.0}, "observations": []}
        return {"level": {"mean": 2.9 if value_id == "co.profit" else obs[value_id]}, "unit": "bn",
                "observations": [{"value": obs[value_id], "valid_at": "2026-05-01T00:00:00Z", "occurred_at": "2026-03-31T00:00:00Z"}]}


def ask(fixture, qid="S1", question="what happens?"):
    return Responder(FakeReader()).answer({"id": qid, "question": question, "fixture": fixture, "entity": "co"})


def test_identities_evaluate_by_form():
    prod = {"form": "product", "coefficient": 0.01, "terms": [{"value": "a", "role": "factor"}, {"value": "b", "role": "factor"}]}
    ratio = {"form": "ratio", "coefficient": 1000, "terms": [{"value": "n", "role": "numerator"}, {"value": "d", "role": "denominator"}]}
    diff = {"form": "difference", "terms": [{"value": "a", "role": "total"}, {"value": "b", "role": "deduction"}]}
    assert eval_identity(prod, {"a": 10, "b": 20}) == 2.0
    assert eval_identity(ratio, {"n": 3, "d": 12}) == 250.0
    assert eval_identity(diff, {"a": 5, "b": 2}) == 3
    assert eval_identity(prod, {"a": 10}) is None


def test_two_term_change_through_a_product_is_exact_and_decomposed():
    a = ask({"levels": {"co.units": 10.0, "co.price": 2.0}, "deltas": {"co.units": -1.0, "co.price": 0.5},
             "outputs": ["co.revenue"]})
    assert abs(a.calc("delta co.revenue")["result"] - (9 * 2.5 - 20)) < 1e-12
    parts = a.calc("part co.revenue co.units")["result"] + a.calc("part co.revenue co.price")["result"]
    assert abs(parts - a.calc("delta co.revenue")["result"]) < 1e-12
    assert any("controlled fixture" in x for x in a.labels)


def test_reallocation_nets_to_zero_at_the_group_and_reconciling_views_are_never_added():
    a = ask({"deltas": {"co.cost": 0.1, "co.support": 0.03}, "outputs": ["co.east", "co.west", "co.profit"]})
    assert abs(a.calc("delta co.east")["result"] - (-0.07)) < 1e-12
    assert abs(a.calc("delta co.west")["result"] - (-0.03)) < 1e-12
    assert abs(a.calc("delta co.profit")["result"] - (-0.1)) < 1e-12     # accounting links one for one, signed
    assert abs(a.calc("check comp.business")["result"] - (-0.1)) < 1e-12     # the business view checks the same total
    assert "comp.regions" in a.retrieved_ids and "path.alloc" in a.retrieved_ids
    assert "other.thing" not in a.retrieved_ids                            # other companies' search hits dropped


def test_an_unsized_route_is_unknown_not_zero():
    a = ask({"shock": {"mkt.size": -1.0}, "outputs": ["co.profit"]})
    c = a.calc("delta co.profit")
    assert c["result"] is None and c["state"] == "unknown or unimplemented"
    assert a.states["l_market_units"] == "unknown or unimplemented"
    assert all(s["state"] != "measured zero" for s in a.unsized_steps)


def test_a_held_value_is_labelled_and_a_stipulated_slope_is_used():
    a = ask({"deltas": {"co.cost": 1.0}, "hold": ["co.autos"], "slopes": {"l_cost_east": -0.25}, "outputs": ["co.east"]})
    assert a.calc("delta co.east")["result"] == -0.25
    assert a.states["co.autos"] == "held constant"


def test_clocks_reprice_only_the_reset_share_for_the_time_active_and_variants_rerun():
    fx = {"levels": {"co.assets": 1000.0, "co.debt": 1000.0},
          "clocks": {"co.yield": {"shock": 1.0, "reset_share": 0.2, "time": 1.0},
                     "co.rate": {"shock": 1.0, "reset_share": 0.3, "time": 1.0}},
          "variants": [{"label": "half", "clocks": {"co.yield": {"shock": 1.0, "reset_share": 0.2, "time": 0.5},
                                                    "co.rate": {"shock": 1.0, "reset_share": 0.3, "time": 0.5}}}],
          "outputs": ["co.nii"]}
    a = ask(fx)
    assert abs(a.calc("delta co.nii")["result"] - (-1.0)) < 1e-12
    assert abs(a.calc("delta co.nii [half]")["result"] - (-0.5)) < 1e-12


def test_stock_flow_periods_solve_the_missing_flow_and_balance():
    a = ask({"periods": [{"label": "P1", "deltas": {"co.made": -10.0, "co.stock": -4.0}},
                         {"label": "P2", "deltas": {"co.made": 3.0, "co.stock": 0.0}}], "outputs": ["co.stock"]})
    assert a.calc("delta co.sold [P1]")["result"] == -6.0
    assert a.calc("delta co.sold [P2]")["result"] == 3.0
    assert a.calc("cumulative delta co.sold")["result"] == -3.0
    assert a.calc("balance check sf.stock")["result"] == 0.0


def test_offsets_apply_pass_through_after_hedges_and_conversion_is_stated():
    a = ask({"offsets": {"l_input_cost": {"gross": 20.0, "hedge": 0.25, "pass_through": 0.4}}, "convert": {"factor": 2.0, "unit": "x"}})
    assert a.calc("net l_input_cost")["result"] == 9.0                    # the link is positive: a cost rises by the net
    assert a.calc("exposed l_input_cost")["result"] == 15.0 and a.calc("recovery l_input_cost")["result"] == 6.0
    assert a.calc("net l_input_cost (converted)")["result"] == 18.0


def test_baseline_keeps_dated_actuals_apart_from_the_state_and_checks_each_view_per_period():
    a = ask({})
    assert a.calc("observed co.profit @2026-03-31")["result"] == 3.0
    assert a.calc("state co.profit")["result"] == 2.9
    assert a.calc("view comp.regions @2026-03-31")["result"] == 3.0
    assert any("is not the dated actual" in n for n in a.notes)
    assert any("never added" in n for n in a.notes)


def test_grader_scores_four_outcomes_apart_and_lists_critical_failures():
    ans = Answer(case_id="S", retrieved_ids=["x"], calculations=[{"key": "k", "result": 5.0}],
                 mechanisms=[{"link": "l1", "sized": True}], labels=["controlled fixture: ..."])
    g = grade(ans, {"evidence": {"ids": ["x", "y"]}, "mechanism": {"required": ["l1"]},
                    "calculation": [{"key": "k", "expected": -5.0, "tolerance": 0.1}], "timing": {"fixture_label": True}})
    assert (g["evidence"], g["mechanism"], g["calculation"], g["timing"]) == ("Partial", "Pass", "Fail", "Pass")
    assert g["critical"] == [{"dimension": "calculation", "key": "k", "kind": "wrong sign"}]
    g = grade(ans, {"mechanism": {"required": ["l1"], "forbidden": [{"kind": "sized_link", "link": "l1"}]}})
    assert g["mechanism"] == "Fail" and g["critical"] and g["evidence"] == "Not tested"
    unknown = Answer(case_id="U", calculations=[{"key": "d", "result": 0.0}])
    g = grade(unknown, {"calculation": [{"key": "d", "expected_state": "unknown or unimplemented"}]})
    assert g["calculation"] == "Fail" and g["critical"][0]["kind"] == "a numeric zero for an unknown"


def test_the_responder_never_sees_the_grading():
    case = Case(id="S9", category="x", question="q", fixture={"deltas": {"co.cost": 1.0}, "outputs": ["co.east"]},
                entity="co", grading={"calculation": [{"key": "delta co.east", "expected": -1.0}]})
    assert "grading" not in case.public()
    out = run([case], FakeReader())
    assert out[0]["grade"]["calculation"] == "Pass"
