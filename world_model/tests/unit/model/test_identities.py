"""Identities that are not sums (Oct 18): products, ratios and differences with derived weights, stocks that accumulate
flows, cross-classified (matrix) views, reconciling views, and state-dependent responses written in construction YAML
(model/construction.py, engine/initialize.compile_construction), on a synthetic bank (acme)."""

from __future__ import annotations

import copy
import json

import pytest

from axelrod_wm.engine.initialize import ConstructionError, ConstructionSpec, load_vocabulary
from axelrod_wm.model.construction import (
    Identity,
    Matrix,
    ResponseState,
    StockFlow,
    Threshold,
    bundle_series,
    composition_role,
    identity_weights,
    log_per_sd,
    model_levels,
    native_per_sd,
    reconcile,
    reconcile_identities,
    reconcile_matrices,
    reconcile_stock_flows,
    reconciling_views,
    stock_flow_weights,
    validate_construction,
)
from axelrod_wm.model.interaction import EdgeType, ParameterForm
from tests.unit.engine.test_cov_initialize import _taxonomy
from tests.unit.model.test_business_construction import ATTRS, TRANSITION, _s, build, world


def _v(sid, mean, scale, unit="bn", **kw):
    return {"entity": "acme", **_s(sid, mean=mean, scale=scale, unit=unit, **kw)}


def bank() -> dict:
    """A small bank: NII = 0.01 x earning assets x NIM; CET1 ratio = 100 x CET1 capital / RWA; NII ex Markets = NII -
    Markets NII; capital accumulates income less dividends each quarter; revenue by segment x line; responses that
    depend on the state."""
    return json.loads(json.dumps({
        "subentities": [
            _v("acme.assets", 100.0, 0.1, family="lognormal"), _v("acme.nim", 2.5, 0.25, unit="%"),
            _v("acme.nii", 2.5, 0.1, family="lognormal"), _v("acme.mkt_nii", 0.5, 0.1), _v("acme.nii_ex", 2.0, 0.2),
            _v("acme.capital", 12.0, 1.0), _v("acme.rwa", 100.0, 0.05, family="lognormal"),
            _v("acme.cet1", 12.0, 0.5, unit="%"), _v("acme.income", 1.0, 0.2), _v("acme.dividends", 0.4, 0.1),
            _v("acme.buybacks", 0.3, 0.1), _v("acme.reinvest", 1.0, 1.0),
            _v("acme.rev", 10.0, 1.0), _v("acme.seg_a", 6.0, 1.0), _v("acme.seg_b", 4.0, 1.0),
            _v("acme.line_x", 7.0, 1.0), _v("acme.line_y", 3.0, 1.0), _v("acme.a_x", 4.0, 1.0),
            _v("acme.a_y", 2.0, 1.0), _v("acme.b_x", 3.0, 1.0), _v("acme.b_y", 1.0, 1.0),
            _v("acme.dom", 5.0, 1.0), _v("acme.intl", 5.0, 1.0),
        ],
        "identities": [
            {"id": "acme.id.nii", "entity_id": "acme", "form": "product", "target": "acme.nii",
             "factors": ["acme.assets", "acme.nim"], "coefficient": 0.01, "unit_check": "bn = bn x % x 0.01"},
            {"id": "acme.id.cet1", "entity_id": "acme", "form": "ratio", "target": "acme.cet1",
             "numerator": ["acme.capital"], "denominator": ["acme.rwa"], "coefficient": 100},
            {"id": "acme.id.nii_ex", "entity_id": "acme", "form": "difference", "target": "acme.nii_ex",
             "of": "acme.nii", "minus": ["acme.mkt_nii"]},
        ],
        "stock_flows": [{"id": "acme.sf.capital", "entity_id": "acme", "stock": "acme.capital", "period_days": 91,
                         "inflows": ["acme.income"], "outflows": ["acme.dividends"]}],
        "interactions": [
            # a builder's own link for one term, to carry a transition; its weight is still derived
            {"id": "w-assets", "source": "acme.assets", "target": "acme.nii", "label": "earns on", "edge_type": "identity",
             "identity": "acme.id.nii", "transition": {**TRANSITION, "mechanism": "balances earn the margin"}},
            {"id": "w-income", "source": "acme.income", "target": "acme.capital", "label": "retained",
             "edge_type": "stock_flow", "identity": "acme.sf.capital", "kernel": {"delay_days": 2}},
            {"id": "s-beta", "source": "macro.tariff", "target": "acme.nim", "label": "reprices",
             "state": {"asymmetry": {"rises": {"mu": 0.6, "sigma": 0.1}, "falls": {"mu": 0.3}}}},
            {"id": "s-buyback", "source": "acme.capital", "target": "acme.buybacks", "label": "funds",
             "effect": {"mu": 0.5}, "state": {"threshold": {"value": "acme.cet1", "above": 11.5}},
             "note": "buybacks stop below the requirement"},
            {"id": "s-reinvest", "source": "macro.tariff", "target": "acme.reinvest", "label": "reinvests",
             "effect": {"mu": 0.4}, "state": {"sign_flip": {"value": "acme.nim", "at": 2.0, "positive": "below"}}},
            *[{"id": f"m-{p}", "source": f"acme.{p}", "target": "acme.rev", "label": "adds to", "edge_type": "accounting",
               "effect": {"mu": 0.5, "sigma": 0.001}} for p in ("seg_a", "seg_b")],
            *[{"id": f"c-{c}-{p}", "source": f"acme.{c}", "target": f"acme.{p}", "label": "adds to",
               "edge_type": "accounting", "effect": {"mu": 0.5, "sigma": 0.001}}
              for c, ps in (("a_x", ("seg_a", "line_x")), ("a_y", ("seg_a", "line_y")), ("b_x", ("seg_b", "line_x")),
                            ("b_y", ("seg_b", "line_y"))) for p in ps],
        ],
        "compositions": [
            {"id": "R", "entity_id": "acme", "view": "reporting_segments", "basis": "b", "unit": "bn",
             "total": "acme.rev", "members": ["acme.seg_a", "acme.seg_b"]},
            {"id": "L", "entity_id": "acme", "view": "lines", "basis": "b", "unit": "bn", "total": "acme.rev",
             "members": ["acme.line_x", "acme.line_y"]},
            {"id": "G", "entity_id": "acme", "view": "regions", "basis": "b", "unit": "bn", "total": "acme.rev",
             "members": ["acme.dom", "acme.intl"], "drives": False},
        ],
        "matrices": [{"id": "M", "entity_id": "acme", "rows": "R", "columns": "L",
                      "cells": {"acme.seg_a": {"acme.line_x": "acme.a_x", "acme.line_y": "acme.a_y"},
                                "acme.seg_b": {"acme.line_x": "acme.b_x", "acme.line_y": "acme.b_y"}}}],
    }))


def load(tmp_path, c):
    tax = _taxonomy(tmp_path, attrs=ATTRS)
    return ConstructionSpec.load(world(tmp_path, c), tax)


@pytest.fixture
def g(tmp_path):
    return build(world(tmp_path, bank()), tmp_path)


# -- the objects ------------------------------------------------------------------------------------------------------
def test_identity_forms_terms_roles_and_formulas():
    p = Identity(id="p", entity_id="e", form="product", target="e.y", factors=["e.a", "e.b"], coefficient=0.01)
    assert p.terms() == [("e.a", 1), ("e.b", 1)] and p.role("e.a") == "factor"
    assert p.formula({"e.y": "NII"}) == "NII = 0.01 x e.a x e.b"
    r = Identity(id="r", entity_id="e", form="ratio", target="e.y", numerator=["e.a"], denominator=["e.b", "e.c"])
    assert r.terms() == [("e.a", 1), ("e.b", -1), ("e.c", -1)] and r.role("e.a") == "numerator"
    assert r.role("e.b") == "denominator" and r.formula() == "e.y = e.a / (e.b x e.c)"
    one = Identity(id="r", entity_id="e", form="ratio", target="e.y", numerator=["e.a"], denominator=["e.b"])
    assert one.formula() == "e.y = e.a / e.b"
    d = Identity(id="d", entity_id="e", form="difference", target="e.y", of="e.a", minus=["e.b"])
    assert d.terms() == [("e.a", 1), ("e.b", -1)] and d.role("e.a") == "total" and d.role("e.b") == "deduction"
    assert d.formula() == "e.y = e.a - e.b"


@pytest.mark.parametrize("kw, msg", [
    ({"form": "product", "factors": ["e.a"]}, "at least two factors"),
    ({"form": "product", "factors": ["e.a", "e.b"], "minus": ["e.c"]}, "a product has no minus"),
    ({"form": "ratio", "numerator": ["e.a"]}, "a numerator and a denominator"),
    ({"form": "difference", "of": "e.a"}, "needs `of` and at least one `minus`"),
    ({"form": "difference", "of": "e.a", "minus": ["e.b"], "coefficient": 2.0}, "a difference has no coefficient"),
    ({"form": "product", "factors": ["e.a", "e.b"], "coefficient": 0.0}, "zero coefficient"),
    ({"form": "product", "factors": ["e.a", "e.a"]}, "e.a appears twice"),
    ({"form": "product", "factors": ["e.a", "e.y"]}, "the target is also a term"),
])
def test_a_malformed_identity_is_refused(kw, msg):
    with pytest.raises(ValueError, match=msg):
        Identity(id="x", entity_id="e", target="e.y", **kw)


@pytest.mark.parametrize("kw, msg", [
    ({"period_days": 0, "inflows": ["e.a"]}, "period must be positive"),
    ({"period_days": 91}, "no flows"),
    ({"period_days": 91, "inflows": ["e.a"], "outflows": ["e.a"]}, "appears twice"),
    ({"period_days": 91, "inflows": ["e.s"]}, "the stock is also a flow"),
])
def test_a_malformed_stock_flow_is_refused(kw, msg):
    with pytest.raises(ValueError, match=msg):
        StockFlow(id="x", entity_id="e", stock="e.s", **kw)


def test_stock_flow_and_matrix_shapes():
    sf = StockFlow(id="s", entity_id="e", stock="e.s", period_days=91, inflows=["e.in"], outflows=["e.out"])
    assert sf.terms() == [("e.in", 1), ("e.out", -1)]
    assert sf.formula({"e.s": "capital"}) == "capital (closing) = capital (opening) + e.in - e.out, per 91 days"
    m = Matrix(id="m", entity_id="e", rows="R", columns="C", drives="columns", cells={"r1": {"c1": "e.v"}})
    assert (m.driving, m.passive, m.cell_list()) == ("C", "R", [("r1", "c1", "e.v")])
    with pytest.raises(ValueError, match="exactly one of"):
        Threshold(value="e.v")
    assert ResponseState().asymmetry is None


def test_derived_weights_by_link_function():
    assert native_per_sd(100.0, 0.1, "log") == pytest.approx(10.0)
    assert native_per_sd(0.2, 0.5, "logit") == pytest.approx(0.08)
    assert native_per_sd(5.0, 2.0, "identity") == 2.0
    assert log_per_sd(100.0, 0.1, "log", "x") == 0.1 and log_per_sd(-4.0, 1.0, "identity", "x") == -0.25
    with pytest.raises(ValueError, match="level of zero"):
        log_per_sd(0.0, 1.0, "identity", "acme.x")
    vals = {"y": (2.5, 0.1, "log"), "a": (100.0, 0.1, "log"), "b": (2.5, 0.25, "identity")}
    p = Identity(id="p", entity_id="e", form="product", target="y", factors=["a", "b"], coefficient=0.01)
    assert identity_weights(p, vals) == pytest.approx({"a": 1.0, "b": 1.0})
    sf = StockFlow(id="s", entity_id="e", stock="y", period_days=91, inflows=["b"])
    assert stock_flow_weights(sf, vals) == pytest.approx({"b": 0.25 / 0.25})


# -- loading: derived weights, generated links, compiled states -------------------------------------------------------
def test_identity_links_carry_derived_weights_and_are_fixed(g):
    ints = g.interactions
    assert ints["w-assets"].forward.effect.mean() == pytest.approx(1.0)            # (0.1) / (0.1)
    assert ints["acme.id.nii:acme.nim"].forward.effect.mean() == pytest.approx(1.0)  # (0.25 / 2.5) / 0.1
    assert ints["acme.id.cet1:acme.capital"].forward.effect.mean() == pytest.approx(2.0)   # (1/12) / (0.5/12)
    assert ints["acme.id.cet1:acme.rwa"].forward.effect.mean() == pytest.approx(-1.2)     # -0.05 / (0.5/12)
    assert ints["acme.id.nii_ex:acme.nii"].forward.effect.mean() == pytest.approx(1.25)   # 2.5 x 0.1 / 0.2
    assert ints["acme.id.nii_ex:acme.mkt_nii"].forward.effect.mean() == pytest.approx(-0.5)
    for iid in ("w-assets", "acme.id.cet1:acme.rwa", "w-income", "acme.sf.capital:acme.dividends"):
        i = ints[iid]
        assert i.fixed and i.quantified and i.existence.mean() > 0.9999
    gen = ints["acme.id.cet1:acme.rwa"]
    assert gen.edge_type == EdgeType.IDENTITY and gen.identity == "acme.id.cet1" and gen.label == "denominator in acme.id.cet1"
    assert gen.tags == ["derived_weight"] and gen.transition.sign == "-" and gen.transition.evidence.magnitude == "inferred"
    assert "CET1 capital" not in gen.transition.mechanism and "cet1 = 100 x capital / rwa" in gen.transition.mechanism
    assert ints["w-assets"].transition.mechanism == "balances earn the margin"          # the builder's transition stays


def test_stock_flow_links_accumulate_over_the_period(g):
    inc, div = g.interactions["w-income"], g.interactions["acme.sf.capital:acme.dividends"]
    assert inc.edge_type == EdgeType.STOCK_FLOW and inc.forward.effect.mean() == pytest.approx(0.2)
    assert div.forward.effect.mean() == pytest.approx(-0.1) and div.label == "flows out of"
    assert inc.forward.kernel.accumulates and inc.forward.kernel.lag.mean() == pytest.approx(91)
    assert inc.forward.kernel.delay.mean() == pytest.approx(2) and div.forward.kernel.delay.mean() == pytest.approx(1)
    assert inc.forward.kernel.duration is None
    assert validate_construction(g) == []


def test_state_dependent_responses_compile_to_piecewise_moderators(g):
    beta = g.interactions["s-beta"]
    assert beta.forward.effect.mean() == pytest.approx(0.6) and beta.forward.effect.sd() == pytest.approx(0.1)
    (p,) = beta.parameters
    assert (p.form, p.moderator_id, p.side, p.threshold) == (ParameterForm.PIECEWISE, "macro.tariff", "above", 0.0)
    assert p.coefficient.mean() == pytest.approx(0.5) and beta.state.asymmetry.falls == {"mu": 0.3}
    (t,) = g.interactions["s-buyback"].parameters
    assert (t.moderator_id, t.side, t.coefficient.mean()) == ("acme.cet1", "above", 0.0)
    assert t.threshold == pytest.approx(-1.0)                       # 11.5 against 12 at a scale of 0.5
    (f,) = g.interactions["s-reinvest"].parameters
    assert (f.side, f.coefficient.mean(), f.threshold) == ("below", -1.0, pytest.approx(-2.0))
    assert f.on(-3.0) and not f.on(0.0) and p.on(0.5) and not p.on(-0.5)


def test_an_asymmetry_with_no_rise_uses_the_fall_and_a_level(tmp_path):
    c = bank()
    c["interactions"][2]["state"]["asymmetry"] = {"rises": {"mu": 0.0}, "falls": {"mu": 0.3}, "at": 3.0,
                                                  "value": "macro.tariff"}
    spec = load(tmp_path, c)
    i = next(x for x in spec.interactions if x.id == "s-beta")
    (p,) = i.parameters
    assert i.effect == {"mu": 0.3, "sigma": 0.15} and (p.side, p.coefficient["mu"]) == ("below", 0.0)
    assert p.threshold == pytest.approx(1.0)                        # macro.tariff 3 against 2, scale 1


def mutate(fn):
    c = bank()
    fn(c)
    return c


def _link(c, iid):
    return next(x for x in c["interactions"] if x["id"] == iid)


@pytest.mark.parametrize("change, msg", [
    (lambda c: _link(c, "w-assets").update(effect={"mu": 1.0}), "weight is derived from acme.id.nii; do not write"),
    (lambda c: _link(c, "w-assets").update(target="acme.nii_ex"), "must point at acme.nii"),
    (lambda c: _link(c, "w-assets").update(calibration="uncalibrated", transition={**TRANSITION}),
     "never uncalibrated"),
    (lambda c: c["interactions"].append({**_link(c, "w-assets"), "id": "w2", "label": "again"}), "has 2 links"),
    (lambda c: c["interactions"].append({"id": "w3", "source": "acme.dom", "target": "acme.nii", "label": "x",
                                         "edge_type": "identity", "identity": "nope"}), "names no declared identity"),
    (lambda c: c["interactions"].append({"id": "w4", "source": "acme.dom", "target": "acme.capital", "label": "x",
                                         "edge_type": "stock_flow", "identity": "acme.id.nii"}),
     "names no declared stock-flow"),
    (lambda c: c["interactions"].append({"id": "w5", "source": "acme.dom", "target": "acme.nii", "label": "x",
                                         "edge_type": "identity", "identity": "acme.id.nii"}), "w5 is not a term"),
    (lambda c: c["identities"][0]["factors"].append("acme.none"), "'acme.none' is not a known subentity"),
    (lambda c: _link(c, "w-income").update(kernel={"lag_days": 30}), "accumulates over its period"),
    (lambda c: _link(c, "w-income").update(kernel={"duration_days": 30}), "accumulates over its period"),
    (lambda c: _link(c, "s-beta").update(effect={"mu": 0.5}), "sizes are its state.asymmetry"),
    (lambda c: _link(c, "s-beta").update(state={"asymmetry": {"rises": {"mu": 0}, "falls": {"mu": 0}}}),
     "no size either way"),
    (lambda c: _link(c, "s-buyback").update(state={"threshold": {"value": "acme.none", "below": 1.0}}),
     "state value 'acme.none'"),
])
def test_what_loading_refuses(tmp_path, change, msg):
    with pytest.raises(ConstructionError, match=msg):
        load(tmp_path, mutate(change))


def test_a_zero_level_cannot_be_linearized(tmp_path):
    c = bank()
    c["subentities"].append(_v("acme.zero", 0.0, 1.0))
    c["identities"].append({"id": "z", "entity_id": "acme", "form": "product", "target": "acme.nim",
                            "factors": ["acme.zero", "acme.assets"]})
    with pytest.raises(ConstructionError, match="z: acme.zero: a level of zero"):
        load(tmp_path, c)


def test_validate_spec_names_unknown_values_of_the_new_objects(tmp_path):
    spec = load(tmp_path, bank())
    vocab = load_vocabulary(_taxonomy(tmp_path, attrs=ATTRS))
    spec.validate_spec(vocab)
    bad = spec.model_copy(update={"stock_flows": [spec.stock_flows[0].model_copy(update={"stock": "acme.none"})]})
    with pytest.raises(ConstructionError, match="'acme.none' is not a known subentity"):
        bad.validate_spec(vocab)
    bad = spec.model_copy(update={"matrices": [spec.matrices[0].model_copy(update={"rows": "ZZ"})]})
    with pytest.raises(ConstructionError, match="'ZZ' is not a composition"):
        bad.validate_spec(vocab)


def test_a_world_without_attributes_loads_without_compiling(tmp_path):
    tax = _taxonomy(tmp_path, attrs=ATTRS)
    (tax / "attributes.yaml").unlink()
    spec = ConstructionSpec.load(world(tmp_path, bank()), tax)
    assert next(x for x in spec.interactions if x.id == "w-assets").effect is None


# -- the structure check ----------------------------------------------------------------------------------------------
def test_the_check_finds_broken_identities_stock_flows_and_matrices(g):
    h = g.model_copy(deep=True)
    h.identities["acme.id.ghost"] = Identity(id="acme.id.ghost", entity_id="ghost", form="product", target="acme.none",
                                             factors=["acme.nim", "acme.zz"])
    rid = "acme.id.cet1:acme.rwa"
    h.interactions[rid] = h.interactions[rid].model_copy(update={"retired_at": h.interactions[rid].created_at})
    k = h.interactions["w-income"].forward
    h.interactions["w-income"] = h.interactions["w-income"].model_copy(update={"forward": k.model_copy(update={
        "kernel": k.kernel.model_copy(update={"shape": "ramp_decay"})})})
    h.interactions["stray"] = h.interactions["w-assets"].model_copy(update={"id": "stray", "source_id": "acme.dom"})
    h.interactions["orphan"] = h.interactions["w-assets"].model_copy(update={"id": "orphan", "identity": "nope"})
    h.matrices["M2"] = Matrix(id="M2", entity_id="ghost", rows="R", columns="ZZ")
    h.matrices["M3"] = Matrix(id="M3", entity_id="acme", rows="R", columns="R")
    h.matrices["M4"] = Matrix(id="M4", entity_id="acme", rows="R", columns="G",
                              cells={"acme.seg_a": {"acme.dom": "acme.none", "acme.zz": "acme.a_x"},
                                     "acme.seg_b": {"acme.dom": "acme.b_x"}})
    problems = validate_construction(h)
    expected = [
        "identity acme.id.ghost: unknown entity 'ghost'", "identity acme.id.ghost: unknown value 'acme.none'",
        "identity acme.id.ghost: unknown value 'acme.zz'",
        "identity acme.id.ghost: acme.nim needs one identity link to acme.none naming it (found 0)",
        "identity acme.id.cet1: acme.rwa needs one identity link to acme.cet1 naming it (found 0)",
        "stock-flow acme.sf.capital: link w-income must accumulate over 91 days",
        "interaction stray: acme.dom -> acme.nii is not a term of acme.id.nii",
        "interaction orphan: an identity link names no identity ('nope')",
        "matrix M2: unknown entity 'ghost'",
        "matrix M2: rows and columns must be two compositions (unknown ZZ)",
        "matrix M3: rows and columns must be two compositions (the same one twice)",
        "matrix M4: cell acme.a_x sits at (acme.seg_a, acme.zz), which is not a row part and a column part",
        "matrix M4: unknown cell value 'acme.none'",
        "matrix M4: cell acme.b_x has no accounting link to acme.dom",
    ]
    for e in expected:
        assert e in problems, e
    h.compositions["G"] = h.compositions["G"].model_copy(update={"additive": False})
    assert "matrix M4: R and G must be additive views of one total of one entity" in validate_construction(h)


def test_one_view_drives_a_total(g):
    assert composition_role(g, "R") == "driving" and composition_role(g, "L") == "reconciling"
    assert composition_role(g, "G") == "reconciling"
    assert reconciling_views(g) == {"G": "drives: false", "L": "matrix M"}
    h = g.model_copy(deep=True)
    h.compositions["G"] = h.compositions["G"].model_copy(update={"drives": True})
    h.interactions["m-dom"] = h.interactions["m-seg_a"].model_copy(update={"id": "m-dom", "source_id": "acme.dom"})
    h.interactions["m-intl"] = h.interactions["m-seg_a"].model_copy(update={"id": "m-intl", "source_id": "acme.intl"})
    assert validate_construction(h) == ["acme.rev has 2 driving views (G, R); one view drives a total: mark the others "
                                        "`drives: false` (reconciling) or declare them as a matrix"]
    h.compositions["G"] = h.compositions["G"].model_copy(update={"drives": False})
    assert validate_construction(h) == [
        "composition G: acme.dom drives acme.rev, but G is a reconciling view (drives: false); only the driving view "
        "links to the total",
        "composition G: acme.intl drives acme.rev, but G is a reconciling view (drives: false); only the driving view "
        "links to the total"]
    h.compositions["R"] = h.compositions["R"].model_copy(update={"drives": False})
    assert "matrix M: its driving view R is marked `drives: false`" in validate_construction(h)
    h.compositions["X"] = h.compositions["G"].model_copy(update={"id": "X", "additive": False})
    assert composition_role(h, "X") == "non_additive"


# -- reconciliation ---------------------------------------------------------------------------------------------------
def test_identities_reconcile_at_the_construction_levels(g):
    rows = {r["identity_id"]: r for r in reconcile_identities(g, model_levels(g, "median"))}
    assert all(r["status"] == "ok" for r in rows.values())
    nii = rows["acme.id.nii"]
    assert nii["implied"] == pytest.approx(2.5) and nii["formula"].startswith("nii = 0.01 x assets x nim")
    assert nii["unit_check"] == "bn = bn x % x 0.01" and rows["acme.id.cet1"]["implied"] == pytest.approx(12.0)
    assert rows["acme.id.nii_ex"]["implied"] == pytest.approx(2.0)
    lv = model_levels(g, "median") | {"acme.nim": 250.0, "acme.rwa": 0.0}
    rows = {r["identity_id"]: r for r in reconcile_identities(g, lv)}
    assert rows["acme.id.nii"]["status"] == "flag" and rows["acme.id.nii"]["relative_difference"] == pytest.approx(-99.0)
    assert rows["acme.id.cet1"]["implied"] == float("inf") and rows["acme.id.cet1"]["difference"] is None
    assert reconcile_identities(g, {})[1]["missing_levels"] == ["acme.nii", "acme.assets", "acme.nim"]
    h = g.model_copy(deep=True)
    h.subentities["acme.mkt_nii"] = h.subentities["acme.mkt_nii"].model_copy(update={"unit": "m"})
    row = next(r for r in reconcile_identities(h, model_levels(h, "median")) if r["identity_id"] == "acme.id.nii_ex")
    assert row["unit_mismatches"] == ["acme.mkt_nii"] and row["status"] == "flag"
    zero = reconcile_identities(g, model_levels(g, "median") | {"acme.nii_ex": 0.0, "acme.nii": 0.5})
    assert next(r for r in zero if r["identity_id"] == "acme.id.nii_ex")["relative_difference"] == 0.0


def test_views_and_matrix_cells_reconcile(g):
    rows = {r["composition_id"]: r for r in reconcile(g)}
    assert rows["L"]["role"] == "reconciling" and rows["L"]["status"] == "ok" and rows["G"]["status"] == "ok"
    assert rows["R"]["role"] == "driving"
    (m,) = reconcile_matrices(g)
    assert m["status"] == "ok" and m["incomplete"] == [] and len(m["lines"]) == 4
    assert m["lines"][0] == {"axis": "row", "part": "acme.seg_a", "level": pytest.approx(6.0), "sum_of_cells": 6.0,
                             "cells": ["acme.a_x", "acme.a_y"], "difference": pytest.approx(0.0),
                             "relative_difference": pytest.approx(0.0), "missing_levels": [], "status": "ok"}
    h = g.model_copy(deep=True)
    h.matrices["M"] = h.matrices["M"].model_copy(update={"cells": {"acme.seg_a": {"acme.line_x": "acme.a_x"}}})
    (m,) = reconcile_matrices(h, {"acme.seg_a": 6.0})
    assert m["incomplete"] == ["acme.seg_a", "acme.seg_b", "acme.line_x", "acme.line_y"] and m["lines"] == []
    h.matrices["M"] = h.matrices["M"].model_copy(update={"cells": {"acme.seg_a": {"acme.line_x": "acme.a_x",
                                                                                 "acme.line_y": "acme.a_y"}}})
    (m,) = reconcile_matrices(h, {"acme.seg_a": 7.0, "acme.a_x": 4.0})
    assert m["status"] == "blocked" and m["lines"][0]["missing_levels"] == ["acme.a_y"]
    h.matrices["Z"] = Matrix(id="Z", entity_id="acme", rows="R", columns="ZZ")
    assert [r["matrix_id"] for r in reconcile_matrices(h)] == ["M"]


def bundle(*obs):
    return {"items": [{"published_at": at, "signals": [{"type": "observe", "value_of": v, "value": x}
                                                       for v, x in vals.items()] + [{"type": "move", "value_of": "a"}]}
                      for at, vals in obs]}


def test_roll_forwards_reconcile_between_dated_stock_levels(g):
    b = bundle(("2025-03-31T00:00:00Z", {"acme.capital": 12.0}),
               ("2025-06-30T00:00:00Z", {"acme.capital": 12.6, "acme.income": 1.0, "acme.dividends": 0.4}),
               ("2025-09-30T00:00:00Z", {"acme.capital": 13.5, "acme.income": 1.1}),
               ("2025-09-30T00:00:00Z", {"acme.capital": 13.0}))           # a later level the same day wins
    s = bundle_series(b)
    assert s["acme.capital"] == [("2025-03-31", 12.0), ("2025-06-30", 12.6), ("2025-09-30", 13.0)]
    rows = reconcile_stock_flows(g, s)
    assert [(r["opening_at"], r["closing_at"], r["status"]) for r in rows] == [
        ("2025-03-31", "2025-06-30", "ok"), ("2025-06-30", "2025-09-30", "blocked")]
    assert rows[0]["implied_closing"] == pytest.approx(12.6) and rows[0]["outflows"] == {"acme.dividends": 0.4}
    assert rows[1]["missing_flows"] == ["acme.dividends"] and rows[1]["implied_closing"] == pytest.approx(13.7)
    assert reconcile_stock_flows(g, {}) == []
    zero = reconcile_stock_flows(g, {"acme.capital": [("a", 0.0), ("b", 0.0)], "acme.income": [("b", 0.0)],
                                     "acme.dividends": [("b", 0.0)]})
    assert zero[0]["relative_difference"] == 0.0 and zero[0]["status"] == "ok"
    off = reconcile_stock_flows(g, {"acme.capital": [("a", 1.0), ("b", 0.0)], "acme.income": [("b", 0.0)],
                                    "acme.dividends": [("b", 0.0)]})
    assert off[0]["relative_difference"] is None and off[0]["status"] == "flag"


def test_notes_proxies_and_calendar_timing(g):
    from axelrod_wm.model.construction import InputNeed, Timing

    assert g.interactions["s-buyback"].note == "buybacks stop below the requirement"
    assert g.interactions["w-assets"].note is None
    proxy = InputNeed(input="deposit beta", status="found_proxy", found_in=["peer.dash"], note="peer median")
    assert proxy.status == "found_proxy"
    with pytest.raises(ValueError, match="needs the sources it was found in"):
        InputNeed(input="deposit beta", status="found_proxy")
    assert Timing(calendar="resets on 1 January").calendar == "resets on 1 January" and Timing().calendar == ""


def test_nested_bridges_of_different_totals_are_allowed(g):
    """A segment's revenue is a part of group revenue and a line of its own segment bridge: a tree, not an overlap."""
    from axelrod_wm.model.construction import Composition

    h = g.model_copy(deep=True)
    h.compositions["S"] = Composition(id="S", entity_id="acme", view="segment_bridge", basis="b", unit="bn",
                                      total="acme.a_y", members=["acme.seg_a"])
    h.interactions["n1"] = h.interactions["m-seg_a"].model_copy(update={"id": "n1", "target_id": "acme.a_y"})
    assert validate_construction(h) == []
    h.compositions["T"] = h.compositions["S"].model_copy(update={"id": "T", "drives": False})
    assert "acme.seg_a is a part of more than one additive view" not in " ".join(validate_construction(h))


def test_a_period_average_stock_lags_half_a_period(tmp_path):
    c = bank()
    c["stock_flows"][0]["measure"] = "period_average"
    spec = load(tmp_path, c)
    sf = spec.stock_flows[0]
    assert sf.formula().endswith("per 91 days; the stock is a period average")
    div = next(x for x in spec.interactions if x.id == "acme.sf.capital:acme.dividends")
    assert div.kernel["delay_days"] == pytest.approx(1 + 45.5)
    g = build(world(tmp_path / "b", c), tmp_path / "b")
    assert reconcile_stock_flows(g, {"acme.capital": [("a", 1.0), ("b", 2.0)]}) == []
    assert validate_construction(g) == []


def test_a_weighted_average_identity(tmp_path):
    """A basket rate = 0.6 x the dom rate + 0.4 x the intl rate: linear, with stated weights."""
    w = Identity(id="w", entity_id="e", form="weighted_average", target="e.y", weights={"e.a": 0.6, "e.b": 0.4})
    assert w.terms() == [("e.a", 1), ("e.b", 1)] and w.role("e.a") == "weight 0.6" and w.linear()
    assert w.formula() == "e.y = 0.6 x e.a + 0.4 x e.b" and w.coefficients() == {"e.a": 0.6, "e.b": 0.4}
    for kw, msg in (({"weights": {"e.a": 0.6, "e.b": 0.6}}, "sum to 1"), ({"weights": {"e.a": 1.0}}, "two or more"),
                    ({"weights": {"e.a": 0.5, "e.b": 0.5}, "coefficient": 2.0}, "a weighted_average has no coefficient")):
        with pytest.raises(ValueError, match=msg):
            Identity(id="w", entity_id="e", form="weighted_average", target="e.y", **kw)
    c = bank()
    c["subentities"].append(_v("acme.basket", 5.0, 0.5))
    c["identities"].append({"id": "acme.id.basket", "entity_id": "acme", "form": "weighted_average",
                            "target": "acme.basket", "weights": {"acme.dom": 0.6, "acme.intl": 0.4}})
    g = build(world(tmp_path, c), tmp_path)
    assert g.interactions["acme.id.basket:acme.dom"].forward.effect.mean() == pytest.approx(0.6 * 1.0 / 0.5)
    row = next(r for r in reconcile_identities(g) if r["identity_id"] == "acme.id.basket")
    assert row["implied"] == pytest.approx(5.0) and row["status"] == "ok"
    assert validate_construction(g) == []


def test_inputs_disclosed_publicly_but_not_supplied():
    from axelrod_wm.model.construction import EvidenceBasis, InputNeed

    need = InputNeed(input="AFS duration", status="disclosed_not_supplied", searched=["ms.wb"], note="10-K p.88")
    assert need.status == "disclosed_not_supplied"
    with pytest.raises(ValueError, match="'disclosed_not_supplied' needs the sources that were searched"):
        InputNeed(input="AFS duration", status="disclosed_not_supplied")
    assert EvidenceBasis(magnitude="public_not_supplied").magnitude == "public_not_supplied"


def test_a_copy_of_the_spec_round_trips(tmp_path):
    spec = load(tmp_path, bank())
    again = ConstructionSpec.model_validate(copy.deepcopy(spec.model_dump(mode="json")))
    assert again.spec_hash() == spec.spec_hash()
