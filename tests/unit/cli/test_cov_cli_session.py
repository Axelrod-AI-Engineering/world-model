"""The command-line session on the oil-shock world (loaded from the shared init cache): `axelrod init`, `update`,
`log`, `show`, and `diff`, with and without --config, plus run-scenario, thesis, and evaluate. Every command runs
in a scratch folder, so the session under var/axelrod is the test's own."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from axelrod_wm import cli as cli_mod
from axelrod_wm.cli import app
from axelrod_wm.engine.config import DEFAULT_CONFIG_PATH
from axelrod_wm.sim import checklist
from axelrod_wm.sim.scenario import SCENARIOS_DIR, load_theses, thesis_from_spec

cli = CliRunner()
OIL = SCENARIOS_DIR / "oil_shock_demo"


def invoke(*args: str):
    out = cli.invoke(app, list(args))
    if out.exception is not None and not isinstance(out.exception, SystemExit):
        raise out.exception
    return out


def config_at(path: Path, storage: Path) -> Path:
    cfg = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text())
    cfg["storage"]["path"] = str(storage)
    path.write_text(yaml.safe_dump(cfg))
    return path


@pytest.fixture(scope="module")
def session(tmp_path_factory):
    """init, then three updates: a plain one; one with a typed event and a drawn deletion after a thesis was pinned
    (as the demo server would); and one through --config with --auto-approve that has no days left to process."""
    root = tmp_path_factory.mktemp("cli")
    mp = pytest.MonkeyPatch()
    mp.chdir(root)
    try:
        out = {"init": invoke("init", "oil_shock_demo", "--seed", "11"), "update1": invoke("update")}
        r = cli_mod._session_runner(None)
        ctl = r.controller
        theses, _ = load_theses(OIL)
        ctl.pose_thesis(thesis_from_spec(theses["T-00"], ctl.now))
        ctl.pin_thesis("T-00")
        ctl.engine.save_snapshot()
        cli_mod._write_session(r, Path("var/axelrod"))
        (root / "event.json").write_text(json.dumps({"headline": "Zorbulon flarps the quibble"}))
        (root / "draw.json").write_text(json.dumps({
            "id": "GUE-DRAW-1", "kind": "real", "occurred_at": "2026-01-27T11:00:00Z",
            "recorded_at": "2026-01-27T12:00:00Z", "produced_by": "human",
            "ops": [{"op": "retire_interaction", "interaction_id": "e43", "reason": "a test"}]}))
        out["update2"] = invoke("update", "--until", "2026-02-03", "--event", "event.json", "--draw", "draw.json")
        cfg = config_at(root / "cfg.yaml", root / "var" / "axelrod")
        out["update3"] = invoke("update", "--until", "2026-02-03", "--auto-approve", "--config", str(cfg))
        out["session"] = json.loads((root / "var" / "axelrod" / "session.json").read_text())
        yield root, cfg, out
    finally:
        mp.undo()


@pytest.fixture
def in_session(session, monkeypatch):
    root, cfg, out = session
    monkeypatch.chdir(root)
    return cfg, out


def test_init_starts_a_session(in_session):
    cfg, out = in_session
    text = out["init"].output
    assert out["init"].exit_code == 0
    assert re.match(r"oil_shock_demo: initialized at version \d+ from \d+ history events over \d+ days", text)
    assert "last processed day 2026-01-25" in text and "session: var/axelrod/session.json" in text
    s = out["session"]
    assert s["scenario"] == "oil_shock_demo" and s["seed"] == 11
    assert s["config"] == str(cfg)                              # the last update ran through --config


def test_a_plain_update_processes_the_next_day(in_session):
    _cfg, out = in_session
    text = out["update1"].output
    assert out["update1"].exit_code == 0
    assert re.search(r"UPD-\d+: done through 2026-01-26 in [\d.]+s; version \d+ -> \d+", text)
    assert "days 1;" in text and "biggest moves: " in text
    for absent in ("  deferred PR-", "no translation", "model edits proposed", "re-posed", "await review"):
        assert absent not in text


def test_an_update_with_typed_and_drawn_events(in_session):
    _cfg, out = in_session
    text = out["update2"].output
    assert out["update2"].exit_code == 0
    assert re.search(r"deferred PR-\d+ \(graph_update, ME-02\): translated from text", text)  # the CLI never waits
    assert "no translation: ME-U-1" in text                     # nonsense has no translation
    assert re.search(r"model edits proposed: PR-\d+", text)      # the drawn deletion
    assert "re-posed: T-00" in text                             # the pinned baseline
    assert "1 proposals await review" in text                   # a deletion always waits for a person
    assert "days 8;" in text


def test_an_update_through_a_config_with_nothing_left_to_process(in_session):
    _cfg, out = in_session
    text = out["update3"].output
    assert out["update3"].exit_code == 0
    assert "through 2026-02-03" in text and "days 0;" in text
    assert "biggest moves" not in text and "re-posed" not in text


def test_log_show_and_diff(in_session):
    log = invoke("log", "--limit", "8", "--process", "day.close", "--process", "learn.working", "--memory", "working")
    lines = log.output.splitlines()
    assert log.exit_code == 0 and 1 <= len(lines) <= 8
    assert all(re.search(r" (day\.close|learn\.working) +working ", ln) for ln in lines)
    versions = [int(ln.split()[0][1:]) for ln in lines]
    assert versions == sorted(versions, reverse=True)
    learned = next(int(ln.split()[0][1:]) for ln in lines if " learn.working " in ln)
    show = invoke("show", str(learned))
    assert show.exit_code == 0 and show.output.startswith(f"v{learned} ") and "learn.working" in show.output
    assert "; vetted by " in show.output
    assert re.search(r"^  updated +subentities +\S", show.output, re.M)     # the values it changed
    missing = invoke("show", "99999999")
    assert missing.exit_code == 1 and "no commit produced version 99999999" in missing.output
    v = versions[0]
    diff = invoke("diff", str(v - 3), str(v))
    assert diff.exit_code == 0 and diff.output.startswith(f"v{v - 3} -> v{v}: 3 commits")
    assert "by process: " in diff.output and "by memory: " in diff.output


def test_no_session_yet(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for args in (["update"], ["log"], ["update", "--config", str(config_at(tmp_path / "c.yaml", tmp_path / "s"))]):
        out = invoke(*args)
        assert out.exit_code == 1 and "no session: run `axelrod init <scenario>` first" in out.output


# -- run-scenario, thesis, evaluate --------------------------------------------------------------------
def test_run_scenario_pauses_for_review(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = invoke("run-scenario", "oil_shock_demo", "--until-step", "3", "--verbose")
    assert out.exit_code == 0                                    # partial runs never fail
    text = out.output
    assert re.search(r"step  1 2026-01-28 20:00 events=\d+ proposals=\d+", text)
    assert "Paused at step 2: 1 proposals await review." in text
    assert "✓  1. Load" in text and "✗  3. item 3: not reached" in text
    assert text.rstrip().endswith("2/17 checklist items passed")
    assert list((tmp_path / "var" / "axelrod" / "traces").glob("run-*.jsonl"))


def test_run_scenario_fails_when_a_check_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = yaml.safe_load((OIL / "scenario.yaml").read_text())
    script["steps"] = script["steps"][:1]                       # the same world and cache, one step
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(script))
    monkeypatch.setattr(checklist, "LOOSE", {"an entity the world does not have"})
    out = invoke("run-scenario", str(path), "--headless", "--auto-approve")
    assert out.exit_code == 1
    assert "✗  1. Load" in out.output and "      counts=True patterns=True loose=False" in out.output


def test_thesis(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = invoke("thesis", "oil_shock_demo", "What if oil prices doubled next quarter?", "--until-step", "0",
                 "--horizon-days", "91")
    assert out.exit_code == 0
    lines = out.output.splitlines()
    assert re.match(r"FC-\S+ at version \d+: What if oil prices doubled next quarter\?", lines[0])
    assert any(re.match(r"  scenario .+: weight [\d.]+", ln) for ln in lines)
    assert lines[-1].startswith("  ") and "moves" in lines[-1]           # the explanation
    assert any(re.match(r"  \S+: median -?[\d.]+ \(5-95%: -?[\d.]+ to -?[\d.]+\); effect [+-][\d.]+ sd", ln)
               for ln in lines)


def test_evaluate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = invoke("evaluate", "oil_shock_demo", "--freeze-at", "2026-01-31T23:59:59", "--market-events", "ME-02",
                 "--until-step", "3", "--horizon-days", "30")
    assert out.exit_code == 0
    rep = json.loads(out.output)
    assert rep["freeze_at"] == "2026-01-31T23:59:59Z" and rep["thesis_ids"] == [f"{rep['id']}-ME-02"]
    assert set(rep["coverage"]) == {"50", "80", "90"} and rep["frozen_version"] > 0
    nothing = json.loads(invoke("evaluate", "oil_shock_demo", "--freeze-at", "2026-01-20T00:00:00+00:00",
                                "--until-step", "0").output)
    assert nothing["thesis_ids"] == [] and nothing["freeze_at"] == "2026-01-20T00:00:00Z"
