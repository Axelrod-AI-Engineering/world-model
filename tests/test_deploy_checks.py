"""The deploy checks' own parts (scripts/deploy): the content the boot check plants, the variables it boots with, and the
file check that runs before client content is pushed. The boots themselves run in the `deploy` CI job."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "deploy" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


boot = load("boot_check")
content = load("check_client_content")


def test_the_boot_runs_the_synthetic_unified_model_with_a_macs_junk_beside_it(tmp_path):
    root = boot.plant_content(tmp_path)
    assert (root / "scenarios" / boot.SCENARIO / "scenario.yaml").is_file()
    assert all((root / "scenarios" / s / "scenario.yaml").is_file() for s in boot.LOGINS.values())
    assert all((root / rel).read_bytes() == boot.APPLE_DOUBLE for rel in boot.JUNK)
    problems, junk = content.check_files(root)
    assert problems == [] and sorted(junk) == sorted(boot.JUNK)


def test_the_boot_runs_as_dev_does():
    env = boot.environment("admin", "pw", "k" * 32)
    assert env["RAILWAY_ENVIRONMENT_NAME"] == "dev" and env["WORLD_MODEL_SCENARIO"] == boot.SCENARIO
    assert env["WORLD_MODEL_LOGINS"] == "acme:pw:acme_unified_focus,nw:pw:northwind_focus"
    assert env["WORLD_MODEL_API_KEYS"].startswith("boot:" + "k" * 32 + ":")


def test_files_that_would_stop_the_boot_are_named(tmp_path):
    (tmp_path / "worlds" / "w").mkdir(parents=True)
    (tmp_path / "worlds" / "w" / "entities.yaml").write_bytes(b"name: caf\xe9\n")
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "c.yaml").write_text("a: [1,\n")
    (tmp_path / "configs" / "notes.txt").write_bytes(b"\xff")              # not YAML: not read
    problems, junk = content.check_files(tmp_path)
    assert problems[0] == "worlds/w/entities.yaml: not UTF-8 (byte 0xe9 at 9)"
    assert problems[1].startswith("configs/c.yaml: not YAML (") and len(problems) == 2
    assert junk == []


def test_a_missing_scenario_stops_the_check(tmp_path, capsys):
    (tmp_path / "scenarios").mkdir()
    assert content.main([str(tmp_path), "--scenario", "unified"]) == 1
    assert "no scenario 'unified'" in capsys.readouterr().err
