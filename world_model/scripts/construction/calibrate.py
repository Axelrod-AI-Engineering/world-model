"""Calibrate a link from a disclosed sensitivity (model/calibrate.py), and optionally write it into the world's files.

    uv run python world_model/scripts/construction/calibrate.py sally_demo tm-c-exposure --source-change 1 --target-change 12 \\
        --evidence tm.co [--support documented|guidance|broker|peer|model|inferred] [--sd-range LO HI | --target-range LO HI] \\
        [--sigma-fraction 0.25] [--allow-sign-flip --reason "..."] [--write]

    uv run python world_model/scripts/construction/calibrate.py sally_demo --disclosure disclosure.yaml [--write]

"A 1-unit move in X changes Y by Z": --source-change is the move in X and --target-change the change in Y, each in the
value's native unit. --side rises|falls sizes one side of an asymmetric link; --stop-when VALUE above|below LEVEL and
--flip-when VALUE above|below LEVEL write the condition the disclosure states (state.threshold, state.sign_flip).

--disclosure takes a file of disclosed scenarios that size one or more links into one target jointly (least squares;
refused when underdetermined):

    target: acme.nii
    links: [l-short, l-long]          # each into the target
    split: [l-short]                  # optional: sized separately for rises and falls
    evidence: acme.co
    support: documented
    scenarios:
      - {id: parallel_up_100, changes: {macro.fed: 1.0, macro.ust10: 1.0}, target_change: 2.9}
      - {id: steeper, changes: {macro.ust10: 1.0}, target_change: 0.9}
 Prints the link before and after, how the effect and its spread were computed, and which of the
world's forecasts (the theses of every scenario built on it) stop listing the link under `unquantified`. With --write it
edits the one interaction's entry in place (engine/construction_edit.py); without it nothing changes. Exits 1 when the
calibration is refused.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from axelrod_wm.clients import find_world, load_scenario_yaml, scenario_dirs
from axelrod_wm.engine.construction_edit import EditError, edit_calibration, interaction_file
from axelrod_wm.engine.initialize import ConstructionSpec, load_vocabulary, resolve_path, world_taxonomy_dir
from axelrod_wm.model.calibrate import (
    SIDES,
    SUPPORTS,
    CalibrationError,
    LinkCalibration,
    Scenario,
    calibrate_from_scenarios,
    calibrate_from_sensitivity,
    unquantified_change,
)


def world_dir(world: str) -> Path:
    p = resolve_path(world)
    return p if p.is_dir() else find_world(world) or resolve_path(f"world_model/examples/worlds/{world}")


def thesis_shocks(world: Path, scenarios: Path | None = None) -> dict[str, list[str]]:
    """'<scenario>/<thesis id>' -> the values its event changes, for every scenario built on `world`. `scenarios` is a
    folder of scenarios; by default the repository's and the client roots' (axelrod_wm/clients.py)."""
    out: dict[str, list[str]] = {}
    for f in sorted(p for d in ([scenarios] if scenarios else scenario_dirs()) for p in d.glob("*/scenario.yaml")):
        raw = load_scenario_yaml(f)
        built_on = (raw.get("initialization") or {}).get("construction_dir")
        if not built_on or resolve_path(built_on).resolve() != world.resolve():
            continue
        theses = f.parent / "theses.yaml"
        for t in (yaml.safe_load(theses.read_text()) or {}).get("theses", []) if theses.exists() else []:
            ops = (t.get("event") or {}).get("ops", [])
            out[f"{f.parent.name}/{t['id']}"] = sorted({(op.get("target") or {}).get("subentity_id") for op in ops}
                                                       - {None})
    return out


def _condition(raw: list[str] | None) -> tuple[str, str, float] | None:
    return None if raw is None else (raw[0], raw[1], float(raw[2]))


def _print(cal: LinkCalibration, f: Path) -> None:
    b = cal.before
    print(f"{cal.interaction_id}: {cal.source_id} -> {cal.target_id}  ({f})")
    print(f"  before: {b['calibration']}, effect {b['effect']}, sign {b['sign']}, magnitude {b['magnitude']}, "
          f"sources {b['sources']}" + (f", state {b['state']}" if b["state"] else ""))
    if cal.source_change is not None:
        print(f"  disclosed: {cal.source_change:g} in the source ({cal.source_z:.4f} sd) changes the target by "
              f"{cal.target_change:g} ({cal.target_z:.4f} sd)")
    size = f"rises {cal.asymmetry['rises']}, falls {cal.asymmetry['falls']}" if cal.asymmetry else \
        f"effect {{mu: {cal.effect}, sigma: {cal.sigma}}} sd/sd (sigma: {cal.sigma_rule})"
    print(f"  after:  calibrated, {size}, sign {cal.sign}, magnitude {cal.support}, evidence {cal.evidence}")
    for k, v in cal.state.items():
        print(f"  state.{k}: {v}")
    if cal.flip_reason:
        print(f"  sign flipped: {cal.flip_reason}")
    for n in cal.notes:
        print(f"  note: {n}")


def scenario_main(a: argparse.Namespace, world: Path, spec: ConstructionSpec, vocab: object) -> int:
    raw = yaml.safe_load(a.disclosure.read_text()) or {}
    try:
        res = calibrate_from_scenarios(
            spec, vocab, target=raw.get("target", ""), links=list(raw.get("links") or []),
            scenarios=[Scenario(id=str(x["id"]), changes={k: float(v) for k, v in (x.get("changes") or {}).items()},
                                target_change=float(x["target_change"])) for x in raw.get("scenarios") or []],
            evidence=str(raw.get("evidence", a.evidence or "")), support=raw.get("support", a.support),
            split=list(raw.get("split") or []), sigma_fraction=a.sigma_fraction,
            allow_sign_flip=a.allow_sign_flip, reason=a.reason)
        edits = []
        for cal in res.links:
            f = interaction_file(world, cal.interaction_id)
            text = dict(edits).get(f, f.read_text())
            edits = [(g, t) for g, t in edits if g != f] + [(f, edit_calibration(text, cal))]
    except (CalibrationError, EditError, KeyError) as exc:
        print(f"REFUSED {exc}")
        return 1
    print(f"scenarios {', '.join(res.scenarios)} -> {res.target_id}: sizes {', '.join(res.unknowns)}")
    for sc, obs, fit in zip(res.scenarios, res.observed, res.fitted):
        print(f"  {sc}: target {obs:+.4f} sd, fitted {fit:+.4f} sd")
    for n in res.notes:
        print(f"  note: {n}")
    for cal in res.links:
        _print(cal, interaction_file(world, cal.interaction_id))
    if a.write:
        for f, text in edits:
            f.write_text(text)
            print(f"wrote {f}")
    else:
        print("dry run: pass --write to edit the files")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("world", help="a world name (world_model/examples/worlds/<name>) or folder")
    ap.add_argument("interaction_id", nargs="?")
    ap.add_argument("--source-change", type=float, help="the move in the source, native units")
    ap.add_argument("--target-change", type=float, help="the change in the target, native units")
    ap.add_argument("--evidence", help="the source id of the disclosure")
    ap.add_argument("--side", choices=SIDES, help="size one side of an asymmetric link")
    ap.add_argument("--stop-when", nargs=3, metavar=("VALUE", "SIDE", "LEVEL"),
                    help="the response acts only while VALUE is above|below LEVEL (native)")
    ap.add_argument("--flip-when", nargs=3, metavar=("VALUE", "SIDE", "LEVEL"),
                    help="the stated sign holds while VALUE is above|below LEVEL (native), reversed otherwise")
    ap.add_argument("--disclosure", type=Path, help="a file of disclosed scenarios (see the module)")
    ap.add_argument("--support", choices=SUPPORTS, default="documented", help="what supports the size")
    rng = ap.add_mutually_exclusive_group()
    rng.add_argument("--sd-range", type=float, nargs=2, metavar=("LO", "HI"), help="the effect's range, sd/sd")
    rng.add_argument("--target-range", type=float, nargs=2, metavar=("LO", "HI"),
                     help="the target change's disclosed range, native units")
    ap.add_argument("--sigma-fraction", type=float, default=None,
                    help="sigma as a fraction of the effect, when no range is given (0.25; 0.5 for --support peer)")
    ap.add_argument("--allow-sign-flip", action="store_true")
    ap.add_argument("--reason", help="why the sign changes (recorded on the link)")
    ap.add_argument("--scenarios", type=Path, default=None, help="a folder of scenarios (default: the repository's and the client roots')")
    ap.add_argument("--write", action="store_true", help="edit the construction file in place")
    a = ap.parse_args(argv)

    world = world_dir(a.world)
    tax = world_taxonomy_dir(world)
    spec = ConstructionSpec.load(world, tax)
    if a.disclosure is not None:
        return scenario_main(a, world, spec, load_vocabulary(tax))
    if a.interaction_id is None or a.source_change is None or a.target_change is None or a.evidence is None:
        ap.error("give an interaction id, --source-change, --target-change and --evidence (or --disclosure)")
    try:
        cal = calibrate_from_sensitivity(
            spec, load_vocabulary(tax), a.interaction_id, source_change=a.source_change,
            target_change=a.target_change, evidence=a.evidence, support=a.support,
            sd_range=tuple(a.sd_range) if a.sd_range else None,
            target_range=tuple(a.target_range) if a.target_range else None, sigma_fraction=a.sigma_fraction,
            allow_sign_flip=a.allow_sign_flip, reason=a.reason, side=a.side,
            stop_when=_condition(a.stop_when), flip_when=_condition(a.flip_when))
        f = interaction_file(world, cal.interaction_id)
        new = edit_calibration(f.read_text(), cal)
    except (CalibrationError, EditError) as exc:
        print(f"REFUSED {exc}")
        return 1
    _print(cal, f)
    changes = unquantified_change(spec, thesis_shocks(world, a.scenarios), cal.interaction_id)
    if not changes:
        print("  no forecast of this world's scenarios lists the link under unquantified")
    for tid, ch in changes.items():
        enters = f"; enters: {', '.join(ch['enters'])}" if ch["enters"] else ""
        print(f"  forecast {tid}: leaves unquantified{enters}")
    if a.write:
        f.write_text(new)
        print(f"wrote {f}")
    else:
        print("dry run: pass --write to edit the file")
    return 0


if __name__ == "__main__":
    sys.exit(main())
