"""Client content lives outside the tracked tree (Oct 21).

A client's scenarios, worlds, configs, and construction pages are kept in a client root, never committed. It mirrors the
repository: `scenarios/<id>/scenario.yaml`, `worlds/<name>/`, `configs/<name>.yaml`, `docs/construction/<company>.md`.
The root is `WORLD_MODEL_CLIENT_DIR` (default `<data>/clients`; the hosted service mounts a volume there). The
variable may name several roots separated by `os.pathsep`, searched in order.

Every path the repository resolves comes from here. The tracked, synthetic content lives under `world_model/`: the
examples (`world_model/examples/{scenarios,worlds}`) and the shared taxonomy (`world_model/taxonomy`). Everything under
`data/` is local and gitignored (`WORLD_MODEL_DATA_DIR` moves it): `clients/` (the client root), `sources/<client>/` (raw
drops), `work/<client>/` (construction pages, days, bundles, golden, bench), `exports/<client>/`.

One rule for the paths a scenario.yaml names: a relative path is resolved against the root that holds the scenario (a
client root for a client scenario, the repository otherwise), then against the repository, so a client scenario can
still use the shared `world_model/taxonomy`. `load_scenario_yaml` applies it once, when the file is read.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from axelrod_wm.paths import REPO_ROOT, WM_ROOT

CLIENT_DIR_ENV = "WORLD_MODEL_CLIENT_DIR"
DATA_DIR_ENV = "WORLD_MODEL_DATA_DIR"
DATA_DIR = Path(os.environ.get(DATA_DIR_ENV) or REPO_ROOT / "data")      # local and gitignored
EXAMPLES_DIR = WM_ROOT / "examples"                    # tracked: scenarios/<id>/, worlds/<name>/
TAXONOMY_DIR = WM_ROOT / "taxonomy"                    # tracked: the shared taxonomy


def client_roots() -> list[Path]:
    raw = os.environ.get(CLIENT_DIR_ENV, "")
    roots = [Path(r).expanduser() for r in raw.split(os.pathsep) if r.strip()]
    return roots or [DATA_DIR / "clients"]


def scenario_dirs() -> list[Path]:
    """Where scenarios are looked for, in order: the repository's, then each client root's."""
    return [EXAMPLES_DIR / "scenarios", *(r / "scenarios" for r in client_roots())]


def find_scenario(scenario_id: str) -> Path | None:
    """The folder of a scenario by id, or None."""
    for d in scenario_dirs():
        if (d / scenario_id / "scenario.yaml").exists():
            return d / scenario_id
    return None


def find_world(name: str) -> Path | None:
    """The folder of a world by name: the repository's examples, then each client root's worlds."""
    for d in (EXAMPLES_DIR / "worlds", *(r / "worlds" for r in client_roots())):
        if (d / name).is_dir():
            return d / name
    return None


def scenario_root(scenario_dir: str | Path) -> Path:
    """The root that holds a scenario folder: its client root, else the repository."""
    here = Path(scenario_dir).resolve()
    for r in client_roots():
        if here.is_relative_to(r.resolve()):
            return r
    return REPO_ROOT


def anchor(path: str, root: Path) -> str:
    """A scenario.yaml path made absolute when it names something under `root` (a client root); otherwise as written,
    for resolve_path to find in the repository."""
    if root == REPO_ROOT or Path(path).is_absolute() or not (root / path).exists():
        return path
    return str(root / path)


def anchor_paths(raw: dict[str, Any], root: Path) -> dict[str, Any]:
    """`raw` (a scenario.yaml as data) with every path it names anchored by the rule above."""
    out = dict(raw)
    ini = dict(raw.get("initialization") or {})
    if "construction_dirs" in ini:
        # a unified scenario names several worlds; everything downstream reads them as `construction_dir`, a list
        dirs = ini.pop("construction_dirs")
        if ini.get("construction_dir"):
            raise ValueError("a scenario names construction_dir or construction_dirs, not both")
        if not isinstance(dirs, list) or not dirs:
            raise ValueError("construction_dirs is a list of world folders")
        ini["construction_dir"] = dirs
    for key in ("construction_dir", "taxonomy_dir", "seeds", "layout"):
        if isinstance(ini.get(key), list):
            ini[key] = [anchor(x, root) for x in ini[key]]
        elif ini.get(key):
            ini[key] = anchor(ini[key], root)
    if ini.get("history"):
        ini["history"] = {**ini["history"], "regimes": anchor(ini["history"]["regimes"], root)}
    if ini:
        out["initialization"] = ini
    if raw.get("world"):
        out["world"] = {**raw["world"], "truth": anchor(raw["world"]["truth"], root)}
    for key in ("config_overrides", "imports_dir"):
        if raw.get(key):
            out[key] = anchor(raw[key], root)
    return out


def load_scenario_yaml(path: str | Path) -> dict[str, Any]:
    """A scenario.yaml as data, its paths anchored to the root that holds it."""
    p = Path(path)
    return anchor_paths(yaml.safe_load(p.read_text()) or {}, scenario_root(p.parent))
