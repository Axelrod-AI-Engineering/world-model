"""Calibration of state-dependent responses and from disclosed scenarios (model/calibrate.py, Oct 18): one side of an
asymmetric link, the conditions a disclosure states, several scenarios solved jointly by least squares (a net
sensitivity spread over parallel links), the exact edits that write them, and the script."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

from axelrod_wm.engine.construction_edit import edit_calibration, flow
from axelrod_wm.engine.initialize import ConstructionSpec, load_vocabulary
from axelrod_wm.model.calibrate import (
    CalibrationError,
    Scenario,
    calibrate_from_scenarios,
    calibrate_from_sensitivity,
    calibrated_entry,
)
from tests.unit.engine.test_cov_initialize import _taxonomy
from tests.unit.model.test_business_construction import ATTRS, TRANSITION, _s, world
from tests.unit.model.test_identities import bank

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("calibrate_script2", ROOT / "world_model" / "scripts" / "construction" / "calibrate.py")
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)


def construction():
    c = bank()
    for i in c["interactions"]:
        if i["id"].startswith("s-"):
            i["transition"] = {**TRANSITION, "sign": "+", "evidence": {"magnitude": "unknown"}}
    c["subentities"].append({"entity": "acme", **_s("acme.pretax", mean=10.0, scale=1.0, unit="bn")})
    c["interactions"] += [
        {"id": "l-short", "source": "macro.tariff", "target": "acme.pretax", "label": "short end",
         "calibration": "uncalibrated", "transition": {**TRANSITION, "sign": "+"}},
        {"id": "l-long", "source": "acme.nim", "target": "acme.pretax", "label": "long end",
         "calibration": "uncalibrated", "transition": {**TRANSITION, "sign": "+"}, "note": "kept"},
        {"id": "l-plain", "source": "acme.dom", "target": "acme.pretax", "label": "plain", "effect": {"mu": 0.2},
         "transition": {**TRANSITION, "sign": None}},
    ]
    return json.loads(json.dumps(c))


@pytest.fixture
def acme(tmp_path):
    d = world(tmp_path, construction())
    tax = _taxonomy(tmp_path, attrs=ATTRS)
    return d, ConstructionSpec.load(d, tax), load_vocabulary(tax)


def sc(i, target, **changes):
    return Scenario(id=i, changes={k.replace("_", "."): v for k, v in changes.items()}, target_change=target)


PARALLEL = Scenario(id="parallel", changes={"macro.tariff": 1.0, "acme.nim": 0.25}, target_change=3.0)
STEEPER = Scenario(id="steeper", changes={"acme.nim": 0.25}, target_change=1.0)


def solve(acme, scenarios, links=("l-short", "l-long"), **kw):
    _, spec, vocab = acme
    return calibrate_from_scenarios(spec, vocab, target="acme.pretax", links=list(links), scenarios=scenarios,
                                    evidence="acme.co", **kw)


# -- one side of an asymmetric link, and conditions ------------------------------------------------------------------
def test_a_side_of_an_asymmetric_link(acme):
    _, spec, vocab = acme
    c = calibrate_from_sensitivity(spec, vocab, "s-beta", source_change=1.0, target_change=0.1, evidence="acme.r1",
                                   side="falls")
    assert c.effect == pytest.approx(0.4) and c.asymmetry == {"falls": {"mu": 0.4, "sigma": 0.1},
                                                               "rises": {"mu": 0.6, "sigma": 0.1}}
    assert c.before["state"]["asymmetry"]["rises"] == {"mu": 0.6, "sigma": 0.1} and "sized its falls" in c.notes[-1]
    plain = calibrate_from_sensitivity(spec, vocab, "s-buyback", source_change=1.0, target_change=0.05,
                                       evidence="acme.r1", side="rises", stop_when=("acme.cet1", "above", 11.0),
                                       flip_when=("acme.nim", "below", 2.0))
    assert plain.asymmetry == {"rises": {"mu": 0.5, "sigma": 0.125}, "falls": {"mu": 0.5}}
    assert plain.state == {"threshold": {"value": "acme.cet1", "above": 11.0},
                           "sign_flip": {"value": "acme.nim", "at": 2.0, "positive": "below"}}


@pytest.mark.parametrize("iid, kw, msg", [
    ("l-short", {"side": "rises"}, "needs the falls size"),
    ("s-beta", {"side": "up"}, "side must be one of"),
    ("w-assets", {}, "identity link: its weight is an identity"),
    ("w-income", {}, "stock_flow link"),
    ("s-buyback", {"stop_when": ("acme.none", "above", 1.0)}, "threshold: no value 'acme.none'"),
    ("s-buyback", {"flip_when": ("acme.nim", "over", 1.0)}, "sign_flip: the side is 'above' or 'below'"),
])
def test_what_side_and_condition_calibration_refuses(acme, iid, kw, msg):
    _, spec, vocab = acme
    with pytest.raises(CalibrationError, match=msg):
        calibrate_from_sensitivity(spec, vocab, iid, source_change=1.0, target_change=0.1, evidence="e", **kw)


def test_the_edit_moves_sizes_into_the_state_and_the_world_still_loads(acme, tmp_path):
    d, spec, vocab = acme
    f = d / "construction" / "acme.yaml"
    cal = calibrate_from_sensitivity(spec, vocab, "s-buyback", source_change=1.0, target_change=0.05,
                                     evidence="acme.r1", side="rises", stop_when=("acme.cet1", "below", 13.0))
    new = edit_calibration(f.read_text(), cal)
    entry = next(x for x in yaml.safe_load(new)["interactions"] if x["id"] == "s-buyback")
    assert "effect" not in entry and entry["state"] == {"threshold": {"value": "acme.cet1", "below": 13.0},
                                                        "asymmetry": {"rises": {"mu": 0.5, "sigma": 0.125},
                                                                      "falls": {"mu": 0.5}}}
    f.write_text(new)
    again = ConstructionSpec.load(d, _taxonomy(tmp_path, attrs=ATTRS))
    i = next(x for x in again.interactions if x.id == "s-buyback")
    assert [p.form for p in i.parameters] == ["piecewise", "piecewise"]
    # sizing the other side keeps the first, and an uncalibrated link's line goes
    cal = calibrate_from_sensitivity(again, vocab, "s-buyback", source_change=1.0, target_change=0.03,
                                     evidence="acme.r2", side="falls")
    entry = next(x for x in yaml.safe_load(edit_calibration(f.read_text(), cal))["interactions"]
                 if x["id"] == "s-buyback")
    assert entry["state"]["asymmetry"] == {"rises": {"mu": 0.5, "sigma": 0.125}, "falls": {"mu": 0.3, "sigma": 0.075}}


def test_a_condition_alone_keeps_the_effect(acme):
    _, spec, vocab = acme
    cal = calibrate_from_sensitivity(spec, vocab, "l-short", source_change=1.0, target_change=2.0, evidence="e",
                                     flip_when=("acme.nim", "above", 2.0))
    entry = calibrated_entry({"id": "l-short", "transition": {"mechanism": "m"}}, cal)
    assert entry["effect"] == {"mu": 2.0, "sigma": 0.5}
    assert entry["state"] == {"sign_flip": {"value": "acme.nim", "at": 2.0, "positive": "above"}}


def test_flow_text():
    assert flow({"a": [1, 2.5], "b": None, "c": True, "d": False, "e": "x y"}) == \
        '{a: [1, 2.5], b: null, c: true, d: false, e: "x y"}'


# -- scenarios ------------------------------------------------------------------------------------------------------
def test_two_scenarios_separate_two_parallel_links(acme):
    res = solve(acme, [PARALLEL, STEEPER])
    assert res.unknowns == ["l-short", "l-long"] and res.scenarios == ["parallel", "steeper"]
    assert res.design == [[1.0, 1.0], [0.0, 1.0]] and res.observed == [3.0, 1.0] and res.residual_sd is None
    short, long_ = res.links
    assert (short.effect, long_.effect) == (pytest.approx(2.0), pytest.approx(1.0))
    assert short.sigma == pytest.approx(0.5) and "fit exactly" in short.sigma_rule
    assert short.scenarios == ["parallel"] and long_.scenarios == ["parallel", "steeper"]
    assert long_.scenario_note == ("sized by least squares over the disclosed scenarios parallel, steeper (acme.co), "
                                   "jointly with l-short")
    assert short.source_change is None and short.before["calibration"] == "uncalibrated"
    entry = calibrated_entry({"id": "l-long", "note": "kept", "calibration": "uncalibrated",
                              "transition": {"mechanism": "m"}}, long_)
    assert entry["note"].startswith("kept | sized by least squares") and entry["effect"] == {"mu": 1.0, "sigma": 0.25}


def test_spare_scenarios_give_a_standard_error(acme):
    res = solve(acme, [PARALLEL, STEEPER, Scenario(id="short", changes={"macro.tariff": 1.0}, target_change=2.3)])
    assert res.residual_sd is not None and res.residual_sd > 0 and "residual standard error" in res.notes[-1]
    assert "standard error over 1 spare" in res.links[0].sigma_rule and res.links[0].sigma > 0


def test_rises_and_falls_from_scenarios_both_ways(acme):
    up = Scenario(id="up", changes={"macro.tariff": 1.0}, target_change=2.0)
    down = Scenario(id="down", changes={"macro.tariff": -1.0}, target_change=-1.0)
    res = solve(acme, [up, down, STEEPER], split=["l-short"])
    assert res.unknowns == ["l-short:rises", "l-short:falls", "l-long"]
    short = res.links[0]
    assert short.asymmetry == {"rises": {"mu": 2.0, "sigma": 0.5}, "falls": {"mu": 1.0, "sigma": 0.25}}
    # a link that already has an asymmetry is split by itself, about its own level
    _, spec, vocab = acme
    res = calibrate_from_scenarios(spec, vocab, target="acme.nim", links=["s-beta"], evidence="e",
                                   scenarios=[Scenario(id="u", changes={"macro.tariff": 1.0}, target_change=0.15),
                                              Scenario(id="d", changes={"macro.tariff": -1.0}, target_change=-0.05)])
    assert res.links[0].asymmetry == {"rises": {"mu": 0.6, "sigma": 0.15}, "falls": {"mu": 0.2, "sigma": 0.05}}


def test_the_scenario_edit_writes_every_link(acme):
    d, _, _ = acme
    f = d / "construction" / "acme.yaml"
    text = f.read_text()
    for cal in solve(acme, [PARALLEL, STEEPER, Scenario(id="down", changes={"macro.tariff": -1.0}, target_change=-1.0)],
                     split=["l-short"]).links:
        text = edit_calibration(text, cal)
    by = {x["id"]: x for x in yaml.safe_load(text)["interactions"]}
    assert "calibration" not in by["l-short"] and "effect" not in by["l-short"]
    assert by["l-short"]["state"]["asymmetry"]["falls"]["mu"] == pytest.approx(1.0)
    assert by["l-long"]["effect"] == {"mu": 1.0, "sigma": 0.25} and by["l-long"]["note"].startswith("kept | sized")


@pytest.mark.parametrize("scenarios, kw, msg", [
    ([PARALLEL], {}, "underdetermined: 1 scenario"),
    ([PARALLEL, Scenario(id="twice", changes={"macro.tariff": 2.0, "acme.nim": 0.5}, target_change=6.0)], {},
     "of rank 1 cannot separate"),
    ([STEEPER, Scenario(id="s2", changes={"acme.nim": 0.5}, target_change=2.0)], {}, "no scenario moves l-short"),
    ([PARALLEL, STEEPER], {"links": ("l-short", "l-short")}, "each link to size once"),
    ([PARALLEL, STEEPER], {"links": ()}, "each link to size once"),
    ([PARALLEL, STEEPER], {"links": ("l-short", "s-beta")}, "points at acme.nim"),
    ([PARALLEL, STEEPER], {"links": ("l-short", "w-assets")}, "identity link"),
    ([PARALLEL, STEEPER], {"split": ["l-plain"]}, "split names links that are not sized here: l-plain"),
    ([PARALLEL, PARALLEL], {}, "scenario ids must be distinct"),
    ([PARALLEL, Scenario(id="x", changes={"acme.dom": 1.0}, target_change=1.0)], {}, "moves acme.dom, which none"),
    ([PARALLEL, STEEPER], {"support": "rumour"}, "support must be one of"),
    ([PARALLEL, STEEPER], {"sigma_fraction": 0.0}, "sigma fraction must be positive"),
    ([Scenario(id="a", changes={"macro.tariff": 1.0}, target_change=0.0), STEEPER], {}, "no size and no direction"),
    ([Scenario(id="a", changes={"macro.tariff": 1.0, "acme.nim": 0.25}, target_change=-1.0), STEEPER], {},
     r"gives - but l-short states \+"),
    ([Scenario(id="a", changes={"macro.tariff": 1.0}, target_change=-20.0), STEEPER], {"links": ("l-short", "l-long")},
     r"gives - but l-short"),
])
def test_what_scenario_calibration_refuses(acme, scenarios, kw, msg):
    with pytest.raises(CalibrationError, match=msg):
        solve(acme, scenarios, **kw)


def test_a_contradicting_scenario_sign_needs_a_reason(acme):
    flipped = Scenario(id="a", changes={"macro.tariff": 1.0, "acme.nim": 0.25}, target_change=-1.0)
    res = solve(acme, [flipped, STEEPER], allow_sign_flip=True, reason="the short end costs this bank")
    assert res.links[0].flip_reason == "the short end costs this bank" and res.links[0].sign == "-"
    assert res.links[1].flip_reason is None


def test_a_size_borrowed_from_a_peer_is_wider_and_labelled(acme):
    _, spec, vocab = acme
    c = calibrate_from_sensitivity(spec, vocab, "l-short", source_change=1.0, target_change=2.0, evidence="peer.r1",
                                   support="peer")
    assert c.support == "peer" and c.sigma == pytest.approx(1.0) and c.sigma_rule.startswith("0.5 of the effect")
    res = solve(acme, [PARALLEL, STEEPER], support="peer")
    assert res.links[0].sigma == pytest.approx(1.0)


@pytest.mark.parametrize("support", ["model", "inferred"])
def test_a_size_split_by_us_or_solved_as_a_remainder_is_wider_and_labelled(acme, support):
    _, spec, vocab = acme
    c = calibrate_from_sensitivity(spec, vocab, "l-short", source_change=1.0, target_change=2.0, evidence="acme.r1",
                                   support=support)
    assert c.support == support and c.sigma == pytest.approx(1.0) and c.sigma_rule.startswith("0.5 of the effect")


# -- the script -------------------------------------------------------------------------------------------------------
def test_the_script_solves_scenarios_and_writes(acme, tmp_path, capsys):
    d, _, _ = acme
    f = tmp_path / "disclosure.yaml"
    f.write_text(yaml.safe_dump({"target": "acme.pretax", "links": ["l-short", "l-long"], "evidence": "acme.co",
                                 "scenarios": [{"id": "parallel", "changes": {"macro.tariff": 1.0, "acme.nim": 0.25},
                                                "target_change": 3.0},
                                               {"id": "steeper", "changes": {"acme.nim": 0.25}, "target_change": 1.0}]}))
    assert script.main([str(d), "--disclosure", str(f)]) == 0
    out = capsys.readouterr().out
    assert "scenarios parallel, steeper -> acme.pretax: sizes l-short, l-long" in out
    assert "parallel: target +3.0000 sd, fitted +3.0000 sd" in out and "dry run" in out
    assert script.main([str(d), "--disclosure", str(f), "--write"]) == 0
    assert "wrote" in capsys.readouterr().out
    by = {x["id"]: x for x in yaml.safe_load((d / "construction" / "acme.yaml").read_text())["interactions"]}
    assert by["l-short"]["effect"]["mu"] == pytest.approx(2.0)
    f.write_text(yaml.safe_dump({"target": "acme.pretax", "links": ["l-short"], "scenarios": []}))
    assert script.main([str(d), "--disclosure", str(f)]) == 1
    assert "REFUSED" in capsys.readouterr().out


def test_the_script_sizes_a_side_with_a_condition(acme, capsys):
    d, _, _ = acme
    assert script.main([str(d), "s-buyback", "--source-change", "1", "--target-change", "0.05", "--evidence", "r1",
                        "--side", "rises", "--stop-when", "acme.cet1", "above", "11.5", "--write"]) == 0
    out = capsys.readouterr().out
    assert "after:  calibrated, rises {'mu': 0.5, 'sigma': 0.125}, falls {'mu': 0.5}" in out
    assert "state.threshold: {'value': 'acme.cet1', 'above': 11.5}" in out
    assert script.main([str(d), "s-buyback", "--source-change", "1", "--target-change", "0.05", "--evidence", "r1",
                        "--side", "falls"]) == 0
    assert "state {'asymmetry'" in capsys.readouterr().out                   # the state as it was
    with pytest.raises(SystemExit):
        script.main([str(d), "s-buyback"])
