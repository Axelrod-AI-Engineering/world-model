"""The command-line interface: the commands that need no session (version, contracts, flows, traces, the demos'
example lists and headless runs, and serving, with the server itself replaced)."""

from __future__ import annotations

import pytest
import uvicorn
from fastapi import FastAPI
from typer.testing import CliRunner

from axelrod_wm import __version__
from axelrod_wm.cli import app
from axelrod_wm.engine.contracts import contracts_table
from axelrod_wm.sim.examples.prod import PROD
from axelrod_wm.sim.examples.small import SMALL

cli = CliRunner()


@pytest.fixture
def in_tmp(tmp_path, monkeypatch):
    """Run in a scratch folder, so var/axelrod is the test's own."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("WORLD_MODEL_LOGINS", raising=False)
    return tmp_path


@pytest.fixture
def served(monkeypatch):
    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda app_, **kw: calls.append((app_, kw)))
    return calls


def test_version():
    out = cli.invoke(app, ["version"])
    assert out.exit_code == 0 and out.output.strip() == __version__


def test_contracts():
    out = cli.invoke(app, ["contracts"])
    assert out.exit_code == 0 and out.output.strip() == contracts_table().strip()


def test_flows_with_and_without_the_svg(in_tmp):
    plain = cli.invoke(app, ["flows"])
    assert plain.exit_code == 0 and "wrote" not in plain.output
    out = cli.invoke(app, ["flows", "--svg", "out/overview.svg"])
    assert out.exit_code == 0 and out.output.startswith(plain.output)
    assert out.output.rstrip().endswith("wrote out/overview.svg")
    assert (in_tmp / "out" / "overview.svg").read_text().lstrip().startswith("<svg")


def test_export_trace(in_tmp):
    missing = cli.invoke(app, ["export-trace", "run-x", "copy.jsonl"])
    assert missing.exit_code == 1 and "no trace var/axelrod/traces/run-x.jsonl" in missing.output
    src = in_tmp / "var" / "axelrod" / "traces"
    src.mkdir(parents=True)
    (src / "run-x.jsonl").write_text('{"seq": 1}\n')
    out = cli.invoke(app, ["export-trace", "run-x", "copy.jsonl"])
    assert out.exit_code == 0 and "wrote copy.jsonl" in out.output
    assert (in_tmp / "copy.jsonl").read_text() == '{"seq": 1}\n'


@pytest.mark.parametrize(("command", "catalog"), [("small_demo", SMALL), ("prod_demo", PROD)])
def test_list_the_examples(command, catalog):
    out = cli.invoke(app, [command, "--list"])
    assert out.exit_code == 0
    lines = out.output.splitlines()
    assert len(lines) == len(catalog.examples)
    for ex, line in zip(catalog.examples, lines):
        assert line.split()[:2] == [str(ex.n), ex.id] and ex.title in line
        more = [e for e in catalog.library if e.feature == ex.feature]
        assert (f"(+{len(more)} more like it)" in line) == bool(more)


def test_small_demo_headless_up_to_an_example():
    out = cli.invoke(app, ["small_demo", "links", "--headless"])
    assert out.exit_code == 0, out.output
    first, second = SMALL.example("1"), SMALL.example("links")
    assert f"1. {first.title}" in out.output and f"{second.n}. {second.title}" in out.output
    assert f"{second.n + 1}. " not in out.output
    assert out.output.rstrip().splitlines()[-1].startswith("2 examples in ")


def test_small_demo_serves_at_an_example(in_tmp, served):
    out = cli.invoke(app, ["small_demo", "ripple", "--port", "9001", "--host", "0.0.0.0"])
    assert out.exit_code == 0 and "Serving small_demo at example ripple at http://0.0.0.0:9001" in out.output
    (served_app, kw), = served
    assert isinstance(served_app, FastAPI) and kw == {"host": "0.0.0.0", "port": 9001, "log_level": "warning"}


def test_prod_demo_serves_from_the_start(in_tmp, served):
    out = cli.invoke(app, ["prod_demo"])
    assert out.exit_code == 0 and "Serving prod_demo at http://127.0.0.1:8765" in out.output
    assert served[0][1]["port"] == 8765


def test_demo_serves_a_scenario(in_tmp, served):
    out = cli.invoke(app, ["demo", "--scenario", "small_demo", "--port", "8123"])
    assert out.exit_code == 0 and "Serving small_demo at http://127.0.0.1:8123" in out.output
    assert isinstance(served[0][0], FastAPI) and served[0][1]["port"] == 8123


def test_run_as_a_module(monkeypatch, capsys):
    import runpy
    import sys

    monkeypatch.setattr(sys, "argv", ["axelrod", "version"])
    with pytest.raises(SystemExit) as done:
        runpy.run_module("axelrod_wm.cli", run_name="__main__")
    assert done.value.code == 0 and capsys.readouterr().out.strip() == __version__
