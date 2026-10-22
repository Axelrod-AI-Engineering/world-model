"""Business construction (model/construction.py, Oct 17): transitions on links, uncalibrated and accounting links,
named paths, compositions, how a world's construction files load, and what the structure check catches."""

from __future__ import annotations

from datetime import date

import pytest
import yaml

from axelrod_wm.engine.engine import Engine
from axelrod_wm.engine.initialize import ConstructionError, ConstructionSpec, Initializer, load_vocabulary
from axelrod_wm.model.construction import Composition, NamedPath, PathStep, Transition, validate_construction
from axelrod_wm.model.interaction import Calibration, EdgeType
from axelrod_wm.repo.snapshots import MemoryBackend
from axelrod_wm.trace import NullTracer
from tests.conftest import make_config
from tests.unit.engine.test_cov_initialize import _taxonomy, _write

ATTRS = {"rate": {"parent": None, "family": "gaussian"}, "flow": {"parent": None, "family": "gaussian"}}


def _s(sid, kind="flow", unit="bn/yr", mean=10.0, scale=1.0, **kw):
    return {"id": sid, "name": sid.split(".")[1].replace("_", " "), "attribute_kind": kind, "unit": unit, "mean": mean,
            "scale": scale, **kw}


TRANSITION = {"mechanism": "a tariff raises the landed cost of imported vehicles", "sign": "+", "actor": "importer",
              "business_unit": "North America", "condition": "vehicles are imported under the tariff",
              "condition_observable": "import share of sales", "timing": {"onset": "at customs entry"},
              "evidence": {"existence": "documented", "direction": "documented", "magnitude": "unknown"},
              "breaker": "local sourcing", "next_state": "landed cost", "unresolved": ["eligible import volume"]}


def world(tmp_path, construction=None, *, entities=None, interactions=None):
    """A small world: a macro driver and a company (acme), and the given construction file."""
    d = tmp_path / "world"
    (d / "construction").mkdir(parents=True)
    _write(d / "entities.yaml", {"entities": entities if entities is not None else [
        {"id": "macro", "name": "Macro", "kind": "macro_factor", "category_tags": ["MF"],
         "subentities": [_s("macro.tariff", kind="rate", unit="%", mean=2.0)]},
        {"id": "acme", "name": "Acme", "kind": "company", "category_tags": ["SD"],
         "subentities": [_s("acme.profit", scale=3.0)]}]})
    _write(d / "interactions.yaml", {"interactions": interactions or []})
    if construction is not None:
        _write(d / "construction" / "acme.yaml", construction)
    return d


def acme_construction():
    return {
        "subentities": [
            {"entity": "acme", **_s("acme.auto", features={"view": "reporting_segments"})},
            {"entity": "acme", **_s("acme.finance", features={"view": "reporting_segments"})},
            {"entity": "acme", **_s("acme.elims", mean=-1.0)},
            {"entity": "acme", **_s("acme.home", features={"view": "regions"})},
            {"entity": "acme", **_s("acme.na", features={"view": "regions"})},
            {"entity": "acme", **_s("acme.landed_cost", features={"view": "operating_state"})},
        ],
        "interactions": [
            *[{"id": f"a{k}", "source": f"acme.{p}", "target": "acme.profit", "label": "adds to", "edge_type": "accounting",
               "effect": {"mu": 0.33, "sigma": 0.001}} for k, p in enumerate(["auto", "finance", "elims", "home", "na"])],
            {"id": "t1", "source": "macro.tariff", "target": "acme.landed_cost", "label": "raises", "calibration": "uncalibrated",
             "transition": TRANSITION},
            {"id": "t2", "source": "acme.landed_cost", "target": "acme.na", "label": "squeezes",
             "effect": {"mu": -0.4}, "transition": {**TRANSITION, "mechanism": "landed cost squeezes regional profit"}},
            {"id": "t3", "source": "acme.landed_cost", "target": "acme.auto", "label": "squeezes", "effect": {"mu": -0.3}},
        ],
        "paths": [{"id": "P1", "name": "Tariffs and sourcing", "entity_id": "acme", "trigger": "a tariff rises",
                   "endpoint": "acme.profit",
                   "steps": [{"interaction_id": "t1"}, {"interaction_id": "t2", "branch": "regional"},
                             {"interaction_id": "t3", "branch": "segment"}, {"interaction_id": "a4"}]}],
        "compositions": [
            {"id": "C1", "entity_id": "acme", "view": "reporting_segments", "basis": "segment operating income",
             "unit": "bn/yr", "total": "acme.profit", "members": ["acme.auto", "acme.finance"], "eliminations": "acme.elims"},
            {"id": "C2", "entity_id": "acme", "view": "regions", "basis": "regional operating income", "unit": "bn/yr",
             "total": "acme.profit", "members": ["acme.home", "acme.na"], "note": "overlaps C1"}],
    }


TWO_DRIVING = ("acme.profit has 2 driving views (C1, C2); one view drives a total: mark the others `drives: false` "
               "(reconciling) or declare them as a matrix")


def build(d, tmp_path):
    tax = _taxonomy(tmp_path, attrs=ATTRS, objects={"root": "gen:obj:root", "nodes": [
        {"id": "gen:obj:root", "name": "Object", "parent": None}]})
    spec = ConstructionSpec.load(d, tax)
    eng = Engine(make_config(), MemoryBackend(), NullTracer(), vocab=load_vocabulary(tax))
    Initializer(eng).construct(spec, tax, start=date(2024, 1, 1), vocab=load_vocabulary(tax))
    return eng.wm.graph


@pytest.fixture
def graph(tmp_path):
    return build(world(tmp_path, acme_construction()), tmp_path)


# -- loading --------------------------------------------------------------------------------------------------------
def test_a_construction_file_adds_values_links_paths_and_compositions(graph):
    acme = graph.entities["acme"]
    assert {"acme.auto", "acme.finance", "acme.landed_cost"} <= set(acme.subentity_ids)
    assert graph.subentities["acme.auto"].features == {"view": "reporting_segments"}
    assert graph.interactions["a0"].edge_type == EdgeType.ACCOUNTING
    t1 = graph.interactions["t1"]
    assert t1.calibration == Calibration.UNCALIBRATED and t1.transition.timing.onset == "at customs entry"
    assert t1.transition.timing.build == "unknown" and t1.transition.evidence.magnitude == "unknown"
    assert set(graph.paths) == {"P1"} and set(graph.compositions) == {"C1", "C2"}
    assert graph.paths["P1"].steps[1] == PathStep(interaction_id="t2", branch="regional")
    assert validate_construction(graph) == [TWO_DRIVING]          # the fixture keeps two driving views (pre Oct 18)


def test_a_world_without_construction_files_loads_as_before(tmp_path):
    d = world(tmp_path)
    (d / "construction").rmdir()
    g = build(d, tmp_path)
    assert g.paths == {} and g.compositions == {} and validate_construction(g) == []


@pytest.mark.parametrize("change, msg", [
    (lambda c: c["subentities"].append({"entity": "nobody", **_s("nobody.x")}), "names unknown entity 'nobody'"),
    (lambda c: c["interactions"][5].update(transition={**TRANSITION, "sign": None}), "must state a sign"),
    (lambda c: c["interactions"][5].pop("transition"), "must state a sign"),
    (lambda c: c["paths"][0]["steps"].append({"interaction_id": "zz"}), "unknown interaction 'zz'"),
    (lambda c: c["paths"][0].update(endpoint="acme.none"), "endpoint 'acme.none'"),
    (lambda c: c["compositions"][0]["members"].append("acme.none"), "'acme.none' is not a known subentity"),
])
def test_a_bad_construction_refuses_to_load(tmp_path, change, msg):
    c = acme_construction()
    change(c)
    with pytest.raises(ConstructionError, match=msg):
        tax = _taxonomy(tmp_path, attrs=ATTRS)
        spec = ConstructionSpec.load(world(tmp_path, c), tax)
        spec.validate_spec(load_vocabulary(tax))


# -- links ------------------------------------------------------------------------------------------------------------
def test_an_uncalibrated_link_has_no_numeric_channels_but_keeps_its_sign(graph):
    t1, t2 = graph.interactions["t1"], graph.interactions["t2"]
    assert not t1.quantified and t1.channels() == [] and t1.channel_items() == []
    assert t1.polarity() == 1 and t2.quantified and t2.polarity() == -1
    assert all(k != "t1" for k, *_ in graph.channel_items())             # nothing numeric reads it
    minus = t1.model_copy(update={"transition": t1.transition.model_copy(update={"sign": "-"})})
    assert minus.polarity() == -1
    unsigned = t1.model_copy(update={"transition": None})
    assert unsigned.polarity() == (1 if t1.forward.effect.mean() >= 0 else -1)   # falls back to the placeholder


# -- the structure check ------------------------------------------------------------------------------------------
def test_two_views_of_one_business_share_no_part_and_only_one_drives(graph):
    assert graph.compositions["C1"].total == graph.compositions["C2"].total
    assert validate_construction(graph) == [TWO_DRIVING]
    g = graph.model_copy(deep=True)
    g.compositions["C2"] = g.compositions["C2"].model_copy(update={"drives": False})
    for iid in ("a3", "a4"):                                         # a reconciling view carries nothing into the total
        g.interactions[iid] = g.interactions[iid].model_copy(update={"retired_at": g.interactions[iid].created_at})
    assert validate_construction(g) == ["path P1: step 3 (a4) is retired"]     # only the path that used it


def test_the_check_finds_broken_paths_and_compositions(graph):
    g = graph.model_copy(deep=True)
    g.paths["P2"] = NamedPath(id="P2", name="x", entity_id="ghost", trigger="t", endpoint="acme.none", steps=[])
    g.paths["P3"] = NamedPath(id="P3", name="x", entity_id="acme", trigger="t", endpoint="acme.profit",
                              steps=[PathStep(interaction_id="nope")])
    g.paths["P4"] = NamedPath(id="P4", name="x", entity_id="acme", trigger="t", endpoint="acme.profit",
                              steps=[PathStep(interaction_id="t1"), PathStep(interaction_id="a0"),
                                     PathStep(interaction_id="t2", branch="b"), PathStep(interaction_id="a1", branch="b")])
    g.interactions["a1"] = g.interactions["a1"].model_copy(update={"retired_at": g.interactions["a1"].created_at})
    g.paths["P5"] = NamedPath(id="P5", name="x", entity_id="acme", trigger="t", endpoint="acme.home",
                              steps=[PathStep(interaction_id="t1")])
    g.compositions["C3"] = Composition(id="C3", entity_id="ghost", view="v", basis="b", unit="u", total="acme.profit",
                                       members=["acme.profit", "acme.none", "acme.landed_cost", "acme.auto"])
    g.compositions["C4"] = Composition(id="C4", entity_id="acme", view="products", basis="b", unit="u",
                                       total="acme.profit", members=["acme.home"], additive=False)
    g.interactions["t1"] = g.interactions["t1"].model_copy(update={"transition": None})
    problems = validate_construction(g)
    expected = [
        "path P2: unknown entity 'ghost'", "path P2: unknown endpoint 'acme.none'", "path P2: no steps",
        "path P3: unknown interactions ['nope']",
        "path P4: step 1 (a0) starts at acme.auto, which no earlier step reaches",
        "path P4: step 3 (a1) is retired",
        "path P4: branch 'b' steps start at different values ['acme.finance', 'acme.landed_cost']",
        "path P5: no step reaches its endpoint acme.home",
        "composition C3: unknown entity 'ghost'", "composition C3: unknown value 'acme.none'",
        "composition C3: the total is also a part",
        "composition C3: acme.profit has no accounting link to its total acme.profit",
        "composition C3: acme.landed_cost has no accounting link to its total acme.profit",
        "acme.auto is a part of more than one additive view (C1, C3); views overlap and must not be added to each other",
        "interaction t1: uncalibrated, so it needs a transition with a sign",
    ]
    for e in expected:
        assert e in problems, e
    assert not any("C4" in p for p in problems)                              # a non-additive view needs no links


def test_an_input_says_whether_the_material_was_searched():
    from axelrod_wm.model.construction import InputNeed

    t = Transition(mechanism="m", unresolved=["hedge notional", {"input": "maturity ladder",
                   "status": "not_disclosed_in_reviewed_sources", "searched": ["src.a", "corpus: maturity"]}])
    assert [(u.input, u.status) for u in t.unresolved] == [("hedge notional", "not_yet_reviewed"),
                                                           ("maturity ladder", "not_disclosed_in_reviewed_sources")]
    assert InputNeed(input="x", status="found_connected", found_in=["src.a"]).found_in == ["src.a"]
    with pytest.raises(ValueError, match="needs the sources that were searched"):
        InputNeed(input="x", status="not_disclosed_in_reviewed_sources")
    with pytest.raises(ValueError, match="needs the sources it was found in"):
        InputNeed(input="x", status="found_not_connected")


def test_transition_defaults_say_unknown():
    t = Transition(mechanism="m")
    assert (t.timing.onset, t.evidence.existence, t.sign, t.observable) == ("unknown", "unknown", None, None)


def test_spec_round_trips_through_yaml(tmp_path):
    c = acme_construction()
    assert yaml.safe_load(yaml.safe_dump(c)) == c
