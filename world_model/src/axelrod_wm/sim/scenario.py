"""Scenario scripts (§11.2) and the scenario's theses, hypotheses, and decisions (§14.8)."""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from axelrod_wm.clients import EXAMPLES_DIR, find_scenario, load_scenario_yaml, scenario_dirs
from axelrod_wm.engine.focus import FocusSpec, focus_result
from axelrod_wm.events.thesis import Thesis
from axelrod_wm.model.hypothesis import Hypothesis

SCENARIOS_DIR = EXAMPLES_DIR / "scenarios"      # the repository's own; client scenarios: axelrod_wm/clients.py


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HistorySpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: date = Field(alias="from")
    to: date
    regimes: str


class InitializationSpec(_M):
    # one world folder, or a list of them (`construction_dirs` in scenario.yaml: a unified scenario, merged in order by
    # engine/initialize.read_construction); `seeds` is likewise one file or a list, merged by read_seeds
    construction_dir: str | list[str]
    taxonomy_dir: str
    seeds: str | list[str] | None = None          # a blank canvas (the small demo) has no seeds and no history
    layout: str | None = None
    history: dict[str, Any] | None = None
    focus: FocusSpec | None = None    # set from the scenario's `focus`: the world is narrowed on load (engine/focus.py)

    def history_spec(self) -> HistorySpec:
        return HistorySpec.model_validate(self.history)


class WorldSpec(_M):
    truth: str


class PoseHypothesisStep(_M):
    hypothesis: str
    base_thesis: str | None = None


class UpdateStepSpec(_M):
    """An update request (§11.2): user_market_events are ids from market_events.jsonl with channel
    "user", user_graph_update_events ids from user_events.yaml."""

    user_market_events: list[str] = []
    user_graph_update_events: list[str] = []
    sources: list[str] | None = None


class GroupSpec(_M):
    """Collapse: a superentity made of these entities and the interactions among them."""

    id: str | None = None
    name: str
    members: list[str]
    interactions: list[str] = []
    description: str = ""


class DissolveSpec(_M):
    """Expand: an admitted superentity breaks back into its constituents."""

    pattern: str
    reason: str


class RetireSpec(_M):
    """Delete: one entity (with its subentities and interactions) or one interaction."""

    entity: str | None = None
    interaction: str | None = None
    reason: str


class StructureAction(_M):
    """A backend user's own structural edit (restructure). It is proposed and vetted like any edit, and
    approval commits it once (process: structural)."""

    group: GroupSpec | None = None
    dissolve: DissolveSpec | None = None
    retire: RetireSpec | None = None
    by: str = "backend user"


class ScenarioStep(_M):
    at: datetime
    update: UpdateStepSpec | None = None
    structure: list[StructureAction] = []
    thesis: str | list[str] | None = None
    pose_hypothesis: PoseHypothesisStep | None = None
    evaluate: dict[str, Any] | None = None
    decision: str | None = None
    resolve_decision: str | None = None
    pin: list[str] = []
    caption: str | None = None

    @field_validator("at", mode="before")
    @classmethod
    def _date_to_datetime(cls, v: Any) -> Any:
        if isinstance(v, date) and not isinstance(v, datetime):
            return datetime.combine(v, time(0)).isoformat() + "+00:00"
        return v

    def theses(self) -> list[str]:
        if self.thesis is None:
            return []
        return [self.thesis] if isinstance(self.thesis, str) else list(self.thesis)


class ScenarioScript(_M):
    """The pydantic model for scenario.yaml."""

    id: str
    title: str
    start: date
    seed: int | None = None
    initialization: InitializationSpec
    world: WorldSpec | None = None
    config_overrides: str | None = None
    checklist: bool = False           # the scenario keeps a checklist (sim/checklist.py): oil_shock_demo
    # "scripted": built from construction files and history, then stepped; "blank": an empty canvas that a
    # chain of examples builds up (the small demo, sim/examples); "seeded": construction files and superentities
    # only, brought up to date by imports (emily_demo, sim/imports)
    canvas: Literal["scripted", "blank", "seeded"] = "scripted"
    imports: bool = False             # new information arrives as import bundles (sim/imports.py)
    imports_dir: str | None = None    # a server-side folder of bundles, when it exists (never committed)
    examples: str | None = None       # a demo with a chain of examples: "small" or "prod" (sim/examples)
    base: str | None = None           # a demo built on another scenario's world and history (prod_demo)
    # the client-format export's identity (context/v4.py): domain_pack_id, name, slug, file_index, edge_id_start
    context_pack: dict = {}
    # Oct 18: a focused scenario narrows another's world to some of its covered companies (engine/focus.py). It
    # inherits every field it does not set from the base, and its world, groups, theses, and expected paths
    focus: FocusSpec | None = None
    steps: list[ScenarioStep]

    @classmethod
    def load(cls, scenario: str | Path) -> ScenarioScript:
        return cls.model_validate(scenario_raw(scenario))

    @property
    def directory(self) -> Path:
        return find_scenario(self.id) or SCENARIOS_DIR / self.id


def _scenario_path(scenario: str | Path) -> Path:
    p = Path(scenario)
    if not p.exists():
        found = find_scenario(str(scenario))
        if found is None and not (SCENARIOS_DIR / str(scenario) / "scenario.yaml").exists():
            where = ", ".join(str(d) for d in scenario_dirs())
            raise FileNotFoundError(
                f"no scenario {str(scenario)!r}: looked for <root>/{scenario}/scenario.yaml in {where}. A client root "
                f"(WORLD_MODEL_CLIENT_DIR) holds scenarios/, worlds/ and configs/ side by side, not worlds/ alone")
        return (found or SCENARIOS_DIR / str(scenario)) / "scenario.yaml"
    return p / "scenario.yaml" if p.is_dir() else p


def scenario_raw(scenario: str | Path) -> dict:
    """scenario.yaml as data, its paths anchored to the root that holds it (axelrod_wm/clients.py); a focused
    scenario's is its base's, overlaid with its own fields."""
    raw = load_scenario_yaml(_scenario_path(scenario))
    if not raw.get("focus"):
        return raw
    focus = FocusSpec.model_validate(raw["focus"])
    base = load_scenario_yaml(_scenario_path(focus.base))
    out = {**base, **raw, "context_pack": {**(base.get("context_pack") or {}), **(raw.get("context_pack") or {})}}
    out["initialization"] = {**(base.get("initialization") or {}), **(raw.get("initialization") or {}),
                             "focus": focus.model_dump()}
    return out


def scenario_focus(scenario_dir: Path) -> FocusSpec | None:
    """The focus a scenario folder's scenario.yaml declares, if any."""
    p = Path(scenario_dir) / "scenario.yaml"
    raw = (yaml.safe_load(p.read_text()) or {}) if p.exists() else {}
    return FocusSpec.model_validate(raw["focus"]) if raw.get("focus") else None


def load_expected_paths(scenario_dir: Path) -> dict:
    """What a scenario's research expects of each thesis's path (expected_paths.yaml); narrowed for a focused one."""
    focus = scenario_focus(scenario_dir)
    if focus is not None:
        return focus_result(focus).expected_paths()
    p = Path(scenario_dir) / "expected_paths.yaml"
    return (yaml.safe_load(p.read_text()) or {}) if p.exists() else {}


def load_watchlist(scenario_dir: Path) -> dict | None:
    """The names a portfolio tracks (watchlist.yaml); a focused scenario's keeps those its world keeps."""
    focus = scenario_focus(scenario_dir)
    if focus is not None:
        return focus_result(focus).watchlist()
    p = Path(scenario_dir) / "watchlist.yaml"
    return (yaml.safe_load(p.read_text()) or None) if p.exists() else None


class DecisionSpec(_M):
    id: str
    agent_id: str
    recommendation: str
    rationale: str = ""
    cites: list[str]
    review_after_days: int


def load_theses(scenario_dir: Path, posed_at: datetime | None = None) -> tuple[dict[str, dict], dict[str, Hypothesis | dict]]:
    """Raw thesis dicts (filled when posed) and hypothesis dicts from theses.yaml; a focused scenario's are its
    base's, narrowed to its world (engine/focus.py)."""
    focus = scenario_focus(scenario_dir)
    if focus is not None:
        raw = focus_result(focus).theses()
        return {t["id"]: t for t in raw["theses"]}, {}
    p = scenario_dir / "theses.yaml"
    if not p.exists():
        return {}, {}
    raw = yaml.safe_load(p.read_text()) or {}
    theses = {t["id"]: t for t in raw.get("theses", [])}
    hyps = {h["id"]: h for h in raw.get("hypotheses", [])}
    return theses, hyps


def thesis_from_spec(spec: dict, posed_at: datetime, posed_by: str = "scenario") -> Thesis:
    """The loader fills id, recorded_at, and produced_by for the embedded event."""
    ev = dict(spec.get("event", {}))
    ev.setdefault("id", f"GUE-{spec['id']}")
    ev.setdefault("recorded_at", posed_at.isoformat())
    ev.setdefault("produced_by", "human")
    ev.setdefault("kind", "hypothetical")
    data = {k: v for k, v in spec.items() if k != "event"}
    data["event"] = ev
    data.setdefault("posed_by", posed_by)
    data.setdefault("posed_at", posed_at.isoformat())
    return Thesis.model_validate(data)


def load_user_events(scenario_dir: Path) -> dict[str, dict]:
    """Raw graph update events the user draws during the scenario (user_events.yaml)."""
    p = scenario_dir / "user_events.yaml"
    if not p.exists():
        return {}
    raw = yaml.safe_load(p.read_text()) or {}
    return {e["id"]: e for e in raw.get("graph_update_events", [])}


def load_decisions(scenario_dir: Path) -> dict[str, DecisionSpec]:
    p = scenario_dir / "decisions.yaml"
    if not p.exists():
        return {}
    raw = yaml.safe_load(p.read_text()) or {}
    return {d["id"]: DecisionSpec.model_validate(d) for d in raw.get("decisions", [])}


def list_scenarios() -> list[dict[str, str]]:
    """Every scenario, the repository's then each client root's (the first of an id wins)."""
    out: dict[str, dict[str, str]] = {}
    for root in scenario_dirs():
        for d in sorted(root.iterdir()) if root.exists() else []:
            p = d / "scenario.yaml"
            if p.exists():
                raw = scenario_raw(p)
                out.setdefault(raw.get("id", d.name), {
                    "id": raw.get("id", d.name), "title": raw.get("title", d.name),
                    "canvas": raw.get("canvas", "scripted"), "examples": raw.get("examples"),
                    "imports": bool(raw.get("imports"))})
    return list(out.values())

