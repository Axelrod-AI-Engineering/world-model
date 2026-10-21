"""Calibrating a link from a disclosed sensitivity (model/calibrate.py), the exact text edit that writes it
(engine/construction_edit.py), and the script (scripts/construction/calibrate.py), on a synthetic world."""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import pytest
import yaml

from axelrod_wm.engine import construction_edit as ce
from axelrod_wm.engine.construction_edit import (
    EditError,
    Edits,
    append_to_list,
    child,
    edit_calibration,
    find_interaction,
    interaction_file,
    scalar,
)
from axelrod_wm.engine.initialize import ConstructionSpec, load_vocabulary
from axelrod_wm.model.calibrate import (
    CalibrationError,
    calibrate_from_sensitivity,
    calibrated_entry,
    standardized_change,
    unquantified_change,
)
from axelrod_wm.model.distributions import Link
from tests.unit.engine.test_cov_initialize import _taxonomy, _write
from tests.unit.model.test_business_construction import ATTRS, TRANSITION, _s, acme_construction, world

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("calibrate_script", ROOT / "scripts" / "construction" / "calibrate.py")
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)


def construction():
    c = acme_construction()
    c["subentities"] += [{"entity": "acme", **_s("acme.price", family="lognormal", mean=50.0, scale=0.1)},
                         {"entity": "acme", **_s("acme.margin", family="beta", mean=0.2, scale=0.5)}]
    c["interactions"] += [
        {"id": "t4", "source": "macro.tariff", "target": "acme.japan", "label": "dents", "effect": {"mu": -0.2},
         "kernel": {"delay_days": 1, "lag_days": 5, "duration_days": None},
         "transition": {**TRANSITION, "sign": None, "evidence": {"magnitude": "unknown", "sources": ["s1"]}},
         "note": "kept"},
        {"id": "t5", "source": "macro.tariff", "target": "acme.price", "label": "moves", "direction": "bidirectional",
         "reverse": {"effect": {"mu": 0.1}, "kernel": {"delay_days": 1, "lag_days": 5, "duration_days": None}},
         "transition": {**TRANSITION, "sign": None}},
        {"id": "t6", "source": "acme.landed_cost", "target": "acme.finance", "label": "costs", "calibration": "uncalibrated",
         "transition": {**TRANSITION, "sign": "-"}},
        {"id": "t7", "source": "macro.tariff", "target": "acme.margin", "label": "thins", "calibration": "uncalibrated",
         "transition": {**TRANSITION, "sign": "-"}},
    ]
    return json.loads(json.dumps(c))         # no shared objects, so the YAML has no anchors


@pytest.fixture
def acme(tmp_path):
    d = world(tmp_path, construction())
    tax = _taxonomy(tmp_path, attrs=ATTRS)
    return d, ConstructionSpec.load(d, tax), load_vocabulary(tax)


def cal(acme, iid="t1", src=0.5, tgt=2.0, **kw):
    _, spec, vocab = acme
    return calibrate_from_sensitivity(spec, vocab, iid, source_change=src, target_change=tgt, evidence="acme.10k", **kw)


# -- the conversion ---------------------------------------------------------------------------------------------------
def test_a_disclosed_sensitivity_becomes_an_effect_in_sd_per_sd(acme):
    c = cal(acme)                                   # 0.5 pt of tariff (scale 1) moves landed cost (scale 1) by 2
    assert (c.source_z, c.target_z, c.effect, c.sigma, c.sign) == (0.5, 2.0, 4.0, 1.0, "+")
    assert c.sigma_rule == "0.25 of the effect (no range given)" and c.flip_reason is None
    assert c.before == {"calibration": "uncalibrated", "effect": None, "sign": "+", "magnitude": "unknown",
                        "sources": [], "state": None}
    assert c.notes[0].startswith("units: the source in % (level 2, scale 1 identity)")
    assert any("over 3 sd/sd" in n for n in c.notes) and any("default timing" in n for n in c.notes)
    c2 = cal(acme, "t5", src=1.0, tgt=5.0, sigma_fraction=0.1)      # a lognormal target converts in log units
    assert c2.target_z == pytest.approx(math.log(55 / 50) / 0.1) and c2.sigma == pytest.approx(c2.effect * 0.1, abs=1e-4)
    assert any("bidirectional" in n for n in c2.notes)
    assert not any("default timing" in n for n in cal(acme, "t4", tgt=-1.0).notes)        # t4 has its timing
    assert standardized_change(0.2, 0.1, 0.5, Link.LOGIT, "x") == pytest.approx((math.log(0.3 / 0.7) - math.log(0.25)) / 0.5)


def test_a_range_sets_the_spread_as_two_sigma_either_side(acme):
    assert cal(acme, sd_range=(5.0, 3.0)).sigma == 0.5
    c = cal(acme, target_range=(1.5, 2.5))
    assert c.sigma == 0.5 and "3.0000 to 5.0000" in c.sigma_rule
    with pytest.raises(CalibrationError, match="outside its range"):
        cal(acme, sd_range=(5.0, 6.0))
    with pytest.raises(CalibrationError, match="two different ends"):
        cal(acme, sd_range=(4.0, 4.0))
    with pytest.raises(CalibrationError, match="give one range"):
        cal(acme, sd_range=(3.0, 5.0), target_range=(1.5, 2.5))


@pytest.mark.parametrize("iid, kw, msg", [
    ("zz", {}, "no interaction 'zz'"),
    ("a0", {}, "accounting link"),
    ("t3", {}, "no transition"),
    ("t1", {"support": "rumour"}, "support must be one of"),
    ("t1", {"src": 0.0}, "source change of zero"),
    ("t1", {"tgt": 0.0}, "target change of zero"),
    ("t1", {"sigma_fraction": 0.0}, "sigma fraction must be positive"),
    ("t5", {"tgt": -60.0}, "leaves the value's domain"),
    ("t7", {"tgt": 0.9}, "leaves the value's domain"),
    ("t1", {"tgt": -1.0}, r"gives - but t1 states \+"),
    ("t4", {"tgt": 1.0}, r"gives \+ but t4 states -"),               # no transition sign: the effect's
    ("t1", {"tgt": -1.0, "allow_sign_flip": True}, "with a --reason"),
    ("t1", {"tgt": -1.0, "allow_sign_flip": True, "reason": "  "}, "with a --reason"),
])
def test_what_the_method_refuses(acme, iid, kw, msg):
    with pytest.raises(CalibrationError, match=msg):
        cal(acme, iid, **kw)


def test_a_sign_flip_needs_permission_and_a_reason_and_is_recorded(acme):
    c = cal(acme, tgt=-1.0, allow_sign_flip=True, reason=" restated by the company ")
    assert c.sign == "-" and c.flip_reason == "restated by the company"
    raw = {"id": "t1", "label": "x", "calibration": "uncalibrated", "note": "old",
           "transition": {"mechanism": "m", "sign": "+", "evidence": {"sources": ["acme.10k"]}}}
    out = calibrated_entry(raw, c)
    assert out["effect"] == {"mu": c.effect, "sigma": c.sigma} and "calibration" not in out
    assert out["transition"]["sign"] == "-" and out["transition"]["evidence"] == {
        "sources": ["acme.10k"], "magnitude": "documented", "direction": "documented"}
    assert out["note"] == "old | sign set to - by calibration from acme.10k: restated by the company"
    assert raw["transition"]["sign"] == "+"                              # the original is untouched
    assert cal(acme, "t5", tgt=-1.0).sign == "-"                          # no stated sign: nothing to contradict


def test_which_forecasts_stop_listing_the_link(acme):
    _, spec, _ = acme
    shocks = {"S/T1": ["macro.tariff"], "S/T2": ["acme.japan"], "S/T3": ["acme.price"]}
    assert unquantified_change(spec, shocks, "t1") == {
        "S/T1": {"leaves": "t1", "enters": ["t6"]},                       # landed cost is now reached, so t6 is
        "S/T3": {"leaves": "t1", "enters": ["t6"]}}                       # t5 is bidirectional: price reaches tariff
    assert unquantified_change(spec, {"S/T2": ["acme.japan"]}, "t1") == {}


# -- the text edit ----------------------------------------------------------------------------------------------------
FILE = """\
# a hand-written construction file
entities: []
interactions:
  # flow entries
  - {id: f1, source: macro.tariff, target: acme.landed_cost, label: raises,   # why
     calibration: uncalibrated,
     transition: {mechanism: "m, with a comma", sign: "+", actor: Acme's buyers, breaker: 'it''s capped',
       evidence: {existence: documented, sources: []}}}
  - {id: "f2", source: macro.tariff, target: acme.landed_cost, label: lifts, calibration: uncalibrated, transition: {mechanism: m, sign: "+", evidence: {}}}
  - {id: f3, source: macro.tariff, target: acme.landed_cost, label: adds, transition: {sign: "+", mechanism: "say \\"so\\""}}
  - id: b1
    source: macro.tariff
    target: acme.landed_cost
    label: pushes  # a trailing comment
    effect:
      mu: 0.3
      sigma: 0.1
    calibration: uncalibrated   # was
    transition:

      # a comment inside
      mechanism: >-
        a folded
        mechanism
      sign: "+"
      evidence:
        magnitude: unknown
        sources:
        - a.src
    note: "old"
  - id: b2
    source: macro.tariff
    target: acme.landed_cost
    label: x
    effect: {mu: 0.5}  # a comment
    transition: {mechanism: m, sign: "+", evidence: {magnitude: unknown, sources: [s1]}}
paths: []
"""


def fake(iid, effect=4.0, sigma=1.0, sign="+", flip=None, evidence="acme.10k"):
    from axelrod_wm.model.calibrate import LinkCalibration

    return LinkCalibration(interaction_id=iid, source_id="a", target_id="b", source_change=1, target_change=1,
                           source_z=1, target_z=1, effect=effect, sigma=sigma, sigma_rule="r", support="guidance",
                           evidence=evidence, sign=sign, before={}, flip_reason=flip)


def test_a_multi_line_flow_entry_changes_only_its_keys():
    new = edit_calibration(FILE, fake("f1", flip="restated"))
    want = calibrated_entry(yaml.safe_load(FILE)["interactions"][0], fake("f1", flip="restated"))
    assert yaml.safe_load(new)["interactions"][0] == want
    assert new.count("\n") == FILE.count("\n") and "# why" in new and "# a hand-written" in new
    assert ("  - {id: f1, source: macro.tariff, target: acme.landed_cost, label: raises, note: \"sign set to + by "
            "calibration from acme.10k: restated\",   # why") in new
    assert "\n     effect: {mu: 4, sigma: 1},\n" in new                    # calibration's line now carries the effect
    assert "     transition: {mechanism: \"m, with a comma\", sign: \"+\"," in new
    assert "evidence: {existence: documented, sources: [acme.10k], magnitude: guidance, direction: guidance}}}" in new


def test_a_one_line_flow_entry_and_an_empty_evidence_mapping():
    new = edit_calibration(FILE, fake("f2"))
    line = next(x for x in new.splitlines() if '"f2"' in x)
    assert line == ('  - {id: "f2", source: macro.tariff, target: acme.landed_cost, label: lifts, '
                    'effect: {mu: 4, sigma: 1}, transition: {mechanism: m, sign: "+", '
                    'evidence: {magnitude: guidance, sources: [acme.10k]}}}')


def test_an_entry_without_calibration_or_effect_or_evidence_gains_them():
    new = edit_calibration(FILE, fake("f3", sign="-", flip="why"))
    line = next(x for x in new.splitlines() if "id: f3" in x)
    assert ", label: adds, effect: {mu: 4, sigma: 1}, note: \"sign set to - by calibration from acme.10k: why\"" in line
    assert line.endswith('transition: {sign: "-", mechanism: "say \\"so\\"", '
                         'evidence: {direction: guidance, magnitude: guidance, sources: [acme.10k]}}}')


def test_a_block_entry_keeps_its_comments_and_layout():
    new = edit_calibration(FILE, fake("b1", effect=-0.25, sigma=0.0625, sign="-", flip="restated", evidence="a.src"))
    old_b1 = FILE[FILE.index("  - id: b1"):FILE.index("  - id: b2")]
    new_b1 = new[new.index("  - id: b1"):new.index("  - id: b2")]
    assert new_b1 == old_b1.replace("    effect:\n      mu: 0.3\n      sigma: 0.1\n",
                                    "    effect: {mu: -0.25, sigma: 0.0625}\n").replace(
        "    calibration: uncalibrated   # was\n", "").replace('      sign: "+"', '      sign: "-"').replace(
        "        magnitude: unknown\n", "        magnitude: guidance\n").replace(
        "        - a.src\n", "        - a.src\n        direction: guidance\n").replace(
        '    note: "old"', '    note: "old | sign set to - by calibration from a.src: restated"')
    added = edit_calibration(FILE, fake("b1", evidence="b.src"))
    assert "        - a.src\n        - b.src\n    note" in added


def test_a_calibrated_entry_is_recalibrated_in_place():
    new = edit_calibration(FILE, fake("b2"))
    assert "    effect: {mu: 4, sigma: 1}  # a comment\n" in new
    assert "evidence: {magnitude: guidance, sources: [s1, acme.10k]}}" in new


def test_a_flow_entry_with_an_effect_loses_its_calibration_key_and_one_comma():
    text = ("interactions:\n"
            '  - {id: f4, source: a.x, target: b.y, label: l, effect: {mu: 1}, calibration: uncalibrated, '
            'transition: {mechanism: m, sign: "+"}}\n'
            "  - {id: f5, source: a.x, target: b.y, label: l, effect: {mu: 1}, calibration: uncalibrated,\n"
            '     transition: {mechanism: m, sign: "+"}}\n'
            '  - {id: f6, source: a.x, target: b.y, label: l, transition: {mechanism: m, sign: "+"}, '
            'effect: {mu: 1}, calibration: uncalibrated }\n')
    for iid in ("f4", "f5", "f6"):
        text = edit_calibration(text, fake(iid))
    lines = text.splitlines()
    ev = "evidence: {magnitude: guidance, sources: [acme.10k]}"
    assert lines[1] == ('  - {id: f4, source: a.x, target: b.y, label: l, effect: {mu: 4, sigma: 1}, '
                        f'transition: {{mechanism: m, sign: "+", {ev}}}}}')
    assert lines[2] == "  - {id: f5, source: a.x, target: b.y, label: l, effect: {mu: 4, sigma: 1},"
    assert lines[4] == ('  - {id: f6, source: a.x, target: b.y, label: l, '
                        f'transition: {{mechanism: m, sign: "+", {ev}}}, effect: {{mu: 4, sigma: 1}} }}')


def test_the_edit_refuses_what_it_cannot_make_exactly(monkeypatch):
    with pytest.raises(EditError, match="no entry for nope"):
        edit_calibration(FILE, fake("nope"))
    with pytest.raises(EditError, match="has no interactions"):
        find_interaction("entities: []\n", "f1")
    monkeypatch.setattr(ce, "calibrated_entry", lambda raw, c: {**raw, "surprise": 1})
    with pytest.raises(EditError, match="would change more than the link"):
        edit_calibration(FILE, fake("b2"))


def test_the_text_helpers_on_unusual_layouts():
    assert scalar(0.30000001) == "0.3" and scalar(-2.0) == "-2" and scalar("tm.co") == "tm.co"
    assert scalar("true") == '"true"' and scalar("two words") == '"two words"'
    node = find_interaction(FILE, "b2")
    with pytest.raises(EditError, match="'label' is not a mapping"):
        child(node, "label")
    with pytest.raises(EditError, match="'label' is not a list"):
        append_to_list(node, Edits(), "label", "x")
    for bad, msg in [("interactions:\n  - {id: q, a: [1, 2\n", "unterminated flow"),
                     ('interactions:\n  - {id: q, a: "open\n', "unterminated quoted"),
                     ("interactions:\n  - {id: q, 'k': 1}\n", "unexpected flow key"),
                     ("interactions:\n  - id: q\n    ? k\n", "unexpected line")]:
        with pytest.raises(EditError, match=msg):
            find_interaction(bad, "q")
    # a flow comment, a value on the next line, and a block entry at the end of a file without a newline
    flow = find_interaction("interactions:\n  - {id: q,  # c\n     k:\n       v}\n", "q")
    assert [(e.key, flow.text[e.value_start:e.value_end]) for e in flow.entries] == [("id", "q"), ("k", "v")]
    tail = "interactions:\n- id: q\n  transition:\n    sign: '+'"
    ed = Edits()
    tr = child(find_interaction(tail, "q"), "transition")
    tr.set(ed, "evidence", "{magnitude: guidance}")
    assert ed.apply(tail) == tail + "\n    evidence: {magnitude: guidance}"
    lst = "interactions:\n- id: q\n  sources:\n  - a"
    ed = Edits()
    append_to_list(find_interaction(lst, "q"), ed, "sources", "b")
    assert ed.apply(lst) == lst + "\n  - b"


def test_the_file_that_defines_a_link(acme, tmp_path):
    d, _, _ = acme
    assert interaction_file(d, "t1") == d / "construction" / "acme.yaml"
    _write(d / "interactions.yaml", {"interactions": [{"id": "m1"}]})
    assert interaction_file(d, "m1") == d / "interactions.yaml"
    with pytest.raises(EditError, match="kind's default link"):
        interaction_file(tmp_path / "nowhere", "t1")


# -- the script -------------------------------------------------------------------------------------------------------
def scenarios(tmp_path, d):
    s = tmp_path / "scenarios"
    for name, cdir, theses in [("on_it", str(d), True), ("elsewhere", "data/worlds/small_demo", True),
                               ("bare", str(d), False), ("blank", None, False)]:
        (s / name).mkdir(parents=True)
        _write(s / name / "scenario.yaml", {"initialization": {"construction_dir": cdir}} if cdir else {})
        if theses:
            _write(s / name / "theses.yaml", {"theses": [
                {"id": "T1", "event": {"ops": [{"op": "change_value", "target": {"subentity_id": "macro.tariff"}},
                                               {"op": "add_entity"}]}},
                {"id": "T2"}]})
    return s


def test_the_script_prints_and_writes(acme, tmp_path, capsys):
    d, _, _ = acme
    s = scenarios(tmp_path, d)
    assert script.thesis_shocks(d, s) == {"on_it/T1": ["macro.tariff"], "on_it/T2": []}
    before = (d / "construction" / "acme.yaml").read_text()
    args = [str(d), "t1", "--source-change", "0.5", "--target-change", "2", "--evidence", "acme.10k",
            "--scenarios", str(s)]
    assert script.main(args) == 0
    out = capsys.readouterr().out
    assert "before: uncalibrated, effect None, sign +" in out and "effect {mu: 4.0, sigma: 1.0}" in out
    assert "forecast on_it/T1: leaves unquantified; enters: t6" in out and "dry run" in out
    assert (d / "construction" / "acme.yaml").read_text() == before
    assert script.main([*args, "--target-change", "-2", "--allow-sign-flip", "--reason", "restated", "--write",
                        "--sd-range", "-5", "-3"]) == 0
    out = capsys.readouterr().out
    assert "sign flipped: restated" in out and "wrote" in out
    t1 = next(i for i in ConstructionSpec.load(d, tmp_path / "taxonomy").interactions if i.id == "t1")
    assert t1.calibration == "calibrated" and t1.effect == {"mu": -4.0, "sigma": 0.5}
    assert t1.transition.sign == "-" and t1.transition.evidence.magnitude == "documented"
    assert script.main([str(d), "t4", "--source-change", "1", "--target-change", "-1", "--evidence", "x",
                        "--target-range", "-2", "-0.5", "--scenarios", str(tmp_path / "none")]) == 0
    assert "no forecast of this world's scenarios" in capsys.readouterr().out
    assert script.main([str(d), "a0", "--source-change", "1", "--target-change", "1", "--evidence", "x"]) == 1
    assert "REFUSED" in capsys.readouterr().out
    assert script.world_dir("small_demo").resolve() == ROOT / "data" / "worlds" / "small_demo"
    assert script.world_dir("acme_demo").resolve() == (ROOT / "tests" / "fixtures" / "clients" / "worlds" / "acme_demo").resolve()      # a client world, by name
