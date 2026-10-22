"""Scenario scripts: loading by id, folder, or file; steps; and the theses, user events, and decisions files."""

from __future__ import annotations

from datetime import date, datetime, timezone

import yaml

from axelrod_wm.sim.scenario import (
    SCENARIOS_DIR,
    ScenarioScript,
    ScenarioStep,
    list_scenarios,
    load_decisions,
    load_theses,
    load_user_events,
    thesis_from_spec,
)

OIL = SCENARIOS_DIR / "oil_shock_demo"
AT = datetime(2026, 5, 4, 21, 0, tzinfo=timezone.utc)


def test_load_by_id_folder_or_file():
    by_id = ScenarioScript.load("oil_shock_demo")
    assert by_id.id == "oil_shock_demo" and by_id.directory == OIL
    assert ScenarioScript.load(OIL) == by_id
    assert ScenarioScript.load(OIL / "scenario.yaml") == by_id
    hist = by_id.initialization.history_spec()
    assert hist.from_ == date(2023, 1, 2) and hist.to == date(2026, 1, 25) and hist.regimes.endswith("history_regimes.yaml")
    small = ScenarioScript.load("small_demo")
    assert small.canvas == "blank" and small.initialization.seeds is None


def test_steps_take_dates_or_times_and_one_or_more_theses():
    s = ScenarioStep.model_validate({"at": date(2026, 2, 1)})
    assert s.at == datetime(2026, 2, 1, tzinfo=timezone.utc) and s.theses() == []
    s = ScenarioStep.model_validate({"at": "2026-02-01T12:00:00Z", "thesis": "T-01"})
    assert s.at.hour == 12 and s.theses() == ["T-01"]
    assert ScenarioStep.model_validate({"at": AT, "thesis": ["T-00", "T-01"]}).theses() == ["T-00", "T-01"]


def test_theses_and_hypotheses():
    theses, hyps = load_theses(OIL)
    assert {"T-00", "T-01"} <= set(theses) and hyps
    th = thesis_from_spec(theses["T-01"], AT)
    assert th.id == "T-01" and th.posed_by == "scenario" and th.posed_at == AT
    assert th.event.id == "GUE-T-01" and th.event.recorded_at == AT and th.event.produced_by == "human"
    assert th.event.kind == "hypothetical"
    assert thesis_from_spec(theses["T-00"], AT, posed_by="tester").posed_by == "tester"


def test_missing_or_empty_files(tmp_path):
    assert load_theses(tmp_path) == ({}, {})
    assert load_user_events(tmp_path) == {}
    assert load_decisions(tmp_path) == {}
    for name in ("theses.yaml", "user_events.yaml", "decisions.yaml"):
        (tmp_path / name).write_text("")
    assert load_theses(tmp_path) == ({}, {})
    assert load_user_events(tmp_path) == {}
    assert load_decisions(tmp_path) == {}


def test_user_events_and_decisions():
    assert "UG-01" in load_user_events(OIL)
    d = load_decisions(OIL)["D-01"]
    assert d.agent_id == "demo-agent" and d.cites == ["T-00", "T-01"] and d.review_after_days == 89


def test_list_scenarios(tmp_path, monkeypatch):
    monkeypatch.setenv("WORLD_MODEL_CLIENT_DIR", str(tmp_path / "missing"))        # a root that does not exist
    repo = [s["id"] for s in list_scenarios()]
    assert {"oil_shock_demo", "small_demo", "prod_demo"} <= set(repo)
    root = tmp_path / "scenarios"
    (root / "a_full").mkdir(parents=True)
    (root / "a_full" / "scenario.yaml").write_text(yaml.safe_dump(
        {"id": "full", "title": "Full", "canvas": "blank", "examples": "small", "imports": True}))
    (root / "b_empty").mkdir()
    (root / "b_empty" / "scenario.yaml").write_text("")
    (root / "c_no_script").mkdir()
    monkeypatch.setenv("WORLD_MODEL_CLIENT_DIR", str(tmp_path))                    # a client root's, after the repository's
    listed = list_scenarios()
    assert [s["id"] for s in listed][:len(repo)] == repo
    assert listed[len(repo):] == [
        {"id": "full", "title": "Full", "canvas": "blank", "examples": "small", "imports": True},
        {"id": "b_empty", "title": "b_empty", "canvas": "scripted", "examples": None, "imports": False},
    ]
