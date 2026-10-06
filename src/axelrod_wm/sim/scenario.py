"""Scenario scripts (§11.2) and the scenario's theses, hypotheses, and decisions (§14.8)."""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from axelrod_wm.core.hypothesis import Hypothesis
from axelrod_wm.engine.initialize import REPO_ROOT
from axelrod_wm.events.thesis import Thesis

SCENARIOS_DIR = REPO_ROOT / "data" / "scenarios"


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HistorySpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: date = Field(alias="from")
    to: date
    regimes: str


class InitializationSpec(_M):
    construction_dir: str
    taxonomy_dir: str
    seeds: str
    layout: str | None = None
    history: dict[str, Any]

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


class ScenarioStep(_M):
    at: datetime
    update: UpdateStepSpec | None = None
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
    world: WorldSpec
    config_overrides: str | None = None
    steps: list[ScenarioStep]

    @classmethod
    def load(cls, scenario: str | Path) -> ScenarioScript:
        p = Path(scenario)
        if not p.exists():
            p = SCENARIOS_DIR / str(scenario) / "scenario.yaml"
        elif p.is_dir():
            p = p / "scenario.yaml"
        return cls.model_validate(yaml.safe_load(p.read_text()))

    @property
    def directory(self) -> Path:
        return SCENARIOS_DIR / self.id


class DecisionSpec(_M):
    id: str
    agent_id: str
    recommendation: str
    rationale: str = ""
    cites: list[str]
    review_after_days: int


def load_theses(scenario_dir: Path, posed_at: datetime | None = None) -> tuple[dict[str, dict], dict[str, Hypothesis | dict]]:
    """Raw thesis dicts (filled when posed) and hypothesis dicts from theses.yaml."""
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
    out = []
    for d in sorted(SCENARIOS_DIR.iterdir()) if SCENARIOS_DIR.exists() else []:
        p = d / "scenario.yaml"
        if p.exists():
            raw = yaml.safe_load(p.read_text()) or {}
            out.append({"id": raw.get("id", d.name), "title": raw.get("title", d.name)})
    return out

