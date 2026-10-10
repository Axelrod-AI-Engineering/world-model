"""Command-line interface (§11.3)."""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(help="Axelrod World Model command-line interface.", no_args_is_help=True,
                  pretty_exceptions_show_locals=False)

PASS, FAIL = "✓", "✗"


SESSION_FILE = "session.json"


def _runner(scenario: str, *, headless: bool = True, auto_approve: bool = False, seed: Optional[int] = None,
            trace: bool = True, storage=None, config: Optional[str] = None):
    from axelrod_wm.repo.snapshots import MemoryBackend
    from axelrod_wm.sim.runner import build_runner
    from axelrod_wm.trace import RecordingTracer

    tracer = None
    if trace:
        tracer = RecordingTracer(run_id=f"run-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}",
                                 directory=Path("var/axelrod/traces"))
    # DECISION: scenario runs, theses, and evaluations from the CLI keep their state in memory, so they
    # never overwrite the session that `axelrod init` and `axelrod update` keep under var/axelrod.
    return build_runner(scenario, interactive=not headless, auto_approve=auto_approve, seed=seed, tracer=tracer,
                        storage=storage if storage is not None else MemoryBackend(), config_path=config)


def _session_storage(config: Optional[str], scenario: str):
    from axelrod_wm.engine.config import load_config
    from axelrod_wm.repo.snapshots import FilesBackend
    from axelrod_wm.sim.scenario import ScenarioScript

    script = ScenarioScript.load(scenario)
    overrides = [script.config_overrides] if script.config_overrides else []
    cfg = load_config(config, overrides=overrides) if config else load_config(overrides=overrides)
    return Path(cfg.storage.path), FilesBackend(path=cfg.storage.path)


def _write_session(runner, path: Path) -> None:
    runner.controller.engine.storage.close()        # the session file must point at durable versions
    rec = runner.session_record()
    (path / SESSION_FILE).write_text(json.dumps(rec, indent=2))


@app.command("init")
def init_cmd(scenario: str = typer.Argument("oil_shock_demo"),
             seed: Optional[int] = typer.Option(None, "--seed", help="Override the scenario's seed."),
             config: Optional[str] = typer.Option(None, "--config")) -> None:
    """Build and cache the init snapshot, and start a session under var/axelrod (session.json)."""
    t = time.time()
    path, storage = _session_storage(config, scenario)
    r = _runner(scenario, seed=seed, trace=False, storage=storage, config=config)
    st = r.load()
    _write_session(r, path)
    wm = r.controller.engine.wm
    typer.echo(f"{scenario}: initialized at version {st.version} from {r.init_info.get('history_events')} history "
               f"events over {r.init_info.get('days')} days in {time.time() - t:.1f}s")
    typer.echo(f"  last processed day {wm.deviations.date_of(wm.last_processed_day)}; cache {r._init_cache_path()}")
    typer.echo(f"  session: {path / SESSION_FILE}")


@app.command("update")
def update_cmd(until: Optional[str] = typer.Option(None, "--until", help="Last day to process (YYYY-MM-DD); "
                                                                           "default: the day after the last processed day."),
               event: list[str] = typer.Option([], "--event", help="A typed user market event (JSON file)."),
               draw: list[str] = typer.Option([], "--draw", help="A drawn model edit (GraphUpdateEvent JSON file)."),
               auto_approve: bool = typer.Option(False, "--auto-approve", help="Use the auto_approve_all policy."),
               config: Optional[str] = typer.Option(None, "--config")) -> None:
    """Run one update (§7.8) against the session in var/axelrod, using its scenario and config."""
    from datetime import date as _date
    from datetime import time as _time

    from axelrod_wm.control.updates import UpdateRequest, UpdateState, UserMarketEventInput
    from axelrod_wm.events.graph_update import GraphUpdateEvent

    t = time.time()
    path = Path("var/axelrod")
    if config is None:
        sess_file = path / SESSION_FILE
    else:
        sess_file = _session_storage(config, "oil_shock_demo")[0] / SESSION_FILE
    if not sess_file.exists():
        typer.echo("no session: run `axelrod init <scenario>` first", err=True)
        raise typer.Exit(code=1)
    session = json.loads(sess_file.read_text())
    cfg_path = config or session.get("config")
    path, storage = _session_storage(cfg_path, session["scenario"])
    r = _runner(session["scenario"], auto_approve=auto_approve, seed=session.get("seed"), trace=True,
                storage=storage, config=cfg_path)
    r.resume(session)
    ctl = r.controller
    wm = ctl.engine.wm
    day = _date.fromisoformat(until) if until else wm.deviations.date_of(wm.last_processed_day + 1)
    # DECISION: a CLI update is requested at the end of its last day (simulated time), so it collects
    # everything published through that day.
    at = datetime.combine(day, _time(23, 59, 59), tzinfo=UTC)
    events = [UserMarketEventInput.model_validate(json.loads(Path(f).read_text())) for f in event]
    draws = [GraphUpdateEvent.model_validate(json.loads(Path(f).read_text())) for f in draw]
    run = ctl.request_update(UpdateRequest(requested_by="user", until=day, requested_at=at,
                                           user_market_events=events, user_graph_update_events=draws))
    while run.state == UpdateState.AWAITING_REVIEW:
        # DECISION: without --auto-approve the CLI defers what needs review (reported below), so the run
        # always finishes; deferred items can be approved later and then fold in late.
        p = ctl.proposals[run.waiting_on]
        typer.echo(f"  deferred {p.id} ({p.kind}, {p.market_event_id or p.event.id}): {', '.join(p.review_reasons)}")
        run = ctl.continue_update(run.id)
    _write_session(r, path)
    rep = run.report
    typer.echo(f"{run.id}: {run.state} through {day} in {time.time() - t:.1f}s; version "
               f"{rep.version_before if rep else '?'} -> {rep.version_after if rep else ctl.engine.version}")
    if rep is not None:
        typer.echo(f"  days {rep.days}; collected {rep.collected}; duplicates dropped {rep.duplicates_dropped}; "
                   f"late {rep.late_collected}")
        typer.echo(f"  translated {rep.translated}; auto-applied {rep.auto_applied}; approved {rep.approved}; "
                   f"rejected {rep.rejected}; deferred {rep.deferred}; late folded {rep.late_folded}")
        if rep.not_translated:
            typer.echo(f"  no translation: {', '.join(rep.not_translated[:10])}")
        if rep.model_edits_proposed:
            typer.echo(f"  model edits proposed: {', '.join(rep.model_edits_proposed[:10])}")
        if rep.biggest_moves:
            typer.echo("  biggest moves: " + ", ".join(f"{s} {m:+.2f}" for s, m in rep.biggest_moves[:6]))
        if rep.reposed_theses:
            typer.echo(f"  re-posed: {', '.join(rep.reposed_theses)}")
    pending = ctl.pending_proposals()
    if pending:
        typer.echo(f"  {len(pending)} proposals await review")


@app.command("run-scenario")
def run_scenario(scenario: str = typer.Argument("oil_shock_demo"),
                 headless: bool = typer.Option(False, "--headless", help="Run without the browser."),
                 auto_approve: bool = typer.Option(False, "--auto-approve", help="Use the auto_approve_all policy."),
                 until_step: Optional[int] = typer.Option(None, "--until-step", help="Stop after this many steps."),
                 seed: Optional[int] = typer.Option(None, "--seed", help="Override the scenario's seed."),
                 verbose: bool = typer.Option(False, "--verbose", "-v", help="Print each step.")) -> None:
    """Run a scenario and print the checklist (§15.3)."""
    t = time.time()
    r = _runner(scenario, headless=headless, auto_approve=auto_approve, seed=seed)
    st = r.load()
    typer.echo(f"Loaded {scenario} (version {st.version}, {st.total_steps} steps) in {time.time() - t:.1f}s")
    last = st.total_steps if until_step is None else min(until_step, st.total_steps)
    while r.step_index < last:
        rep = r.step()
        if verbose:
            typer.echo(f"  step {rep.step_index:2d} {rep.at:%Y-%m-%d %H:%M} events={len(rep.market_event_ids)} "
                       f"proposals={len(rep.proposal_ids)} forecasts={rep.forecast_ids} {rep.notes}")
        if r.state == "awaiting_review":
            typer.echo(f"Paused at step {r.step_index}: {len(r.controller.pending_proposals())} proposals await review.")
            break
    typer.echo(f"Ran {r.step_index} steps in {time.time() - t:.1f}s; version {r.controller.engine.version}")
    items = r.checklist()
    details = r.recorder.details() if r.recorder else {}
    failed = 0
    for n, (label, ok) in enumerate(items, start=1):
        typer.echo(f"{PASS if ok else FAIL} {label}")
        if not ok:
            failed += 1
            if n in details and details[n]:
                typer.echo(f"      {details[n]}")
    typer.echo(f"{len(items) - failed}/{len(items)} checklist items passed")
    if until_step is None and failed:
        raise typer.Exit(code=1)


@app.command()
def demo(scenario: str = typer.Option("oil_shock_demo", "--scenario"),
         port: int = typer.Option(8000, "--port"), host: str = typer.Option("127.0.0.1", "--host"),
         config: Optional[str] = typer.Option(None, "--config")) -> None:
    """Serve the browser demo at http://127.0.0.1:8000."""
    import uvicorn

    from axelrod_wm.api.app import create_app

    typer.echo(f"Serving {scenario} at http://{host}:{port}")
    uvicorn.run(create_app(config, scenario), host=host, port=port, log_level="warning")


@app.command()
def thesis(scenario: str = typer.Argument("oil_shock_demo"), question: str = typer.Argument(...),
           until_step: int = typer.Option(12, "--until-step", help="Advance the scenario this far first."),
           horizon_days: int = typer.Option(182, "--horizon-days")) -> None:
    """Pose a question as a thesis and print the forecast."""
    r = _runner(scenario, auto_approve=True, trace=False)
    r.load()
    r.play(until_step)
    ctl = r.controller
    th = ctl.thesis_from_question(question, horizon_days=horizon_days)
    fc = ctl.pose_thesis(th)
    ex = ctl.explanation(fc.explanation_id)
    typer.echo(f"{fc.id} at version {fc.based_on_version}: {question}")
    for s in fc.scenarios:
        typer.echo(f"  scenario {s.name}: weight {s.weight:.2f}")
    for t in fc.targets:
        lv, ef = fc.summary[t][-1], fc.effect_summary[t][-1]
        typer.echo(f"  {t}: median {lv.q50:.3f} (5-95%: {lv.q05:.3f} to {lv.q95:.3f}); effect {ef.q50:+.2f} sd")
    if ex is not None:
        typer.echo(f"  {ex.text}")


@app.command()
def evaluate(scenario: str = typer.Argument("oil_shock_demo"),
             freeze_at: str = typer.Option(..., "--freeze-at"),
             market_events: list[str] = typer.Option([], "--market-events"),
             horizon_days: int = typer.Option(63, "--horizon-days"),
             until_step: int = typer.Option(13, "--until-step")) -> None:
    """Freeze at a past date, pose what later happened, and score."""
    from axelrod_wm.evaluation.backtest import EvaluationRequest

    r = _runner(scenario, auto_approve=True, trace=False)
    r.load()
    r.play(until_step)
    fz = datetime.fromisoformat(freeze_at)
    if fz.tzinfo is None:
        fz = fz.replace(tzinfo=UTC)
    rep = r.controller.evaluate(EvaluationRequest(freeze_at=fz, market_event_ids=market_events, horizon_days=horizon_days))
    typer.echo(json.dumps(rep.model_dump(mode="json"), indent=2))


# -- the flowchart, contracts, the two demos, and the log ----------------------------
@app.command()
def flows(svg: Optional[str] = typer.Option(None, "--svg", help="Also write the flowchart as an SVG here.")) -> None:
    """Print the flowcharts of learning and of inference (each stage's input and output), then each stage's own
    flowchart, step by step."""
    from axelrod_wm.flows import INFERENCE, INFERENCE_FLOWS, STAGE_FLOWS, WORLD_MODEL
    from axelrod_wm.flows.render import flow_markdown, render_svg

    for f in (WORLD_MODEL, *STAGE_FLOWS, INFERENCE, *INFERENCE_FLOWS):
        typer.echo(flow_markdown(f))
    if svg:
        Path(svg).parent.mkdir(parents=True, exist_ok=True)
        Path(svg).write_text(render_svg(WORLD_MODEL))
        typer.echo(f"wrote {svg}")


@app.command()
def contracts() -> None:
    """Print every component's contract: process, cadence, inputs, outputs, writes, and when it runs."""
    from axelrod_wm.engine.contracts import contracts_table

    typer.echo(contracts_table())


def _example_demo(scenario: str, example: Optional[str], port: int, host: str, headless: bool, list_only: bool,
                  config: Optional[str]) -> None:
    from axelrod_wm.sim.examples.session import examples_text, run_examples

    if list_only or headless:
        if list_only:
            if scenario == "small_demo":
                from axelrod_wm.sim.examples.small import SMALL as catalog
            else:
                from axelrod_wm.sim.examples.prod import PROD as catalog
            for ex in catalog.examples:
                more = [e.title for e in catalog.library if e.feature == ex.feature]
                typer.echo(f"{ex.n:>2} {ex.id:<12} [{ex.memory}] {ex.title}" + (f"  (+{len(more)} more like it)" if more else ""))
            return
        t = time.time()
        records, _runner = run_examples(scenario, upto=example)
        typer.echo(examples_text(records))
        typer.echo(f"{len(records)} examples in {time.time() - t:.1f}s")
        return
    import uvicorn

    from axelrod_wm.api.app import create_app

    where = f" at example {example}" if example else ""
    typer.echo(f"Serving {scenario}{where} at http://{host}:{port}")
    uvicorn.run(create_app(config, scenario, start_example=example), host=host, port=port, log_level="warning")


@app.command("small_demo")
def small_demo(example: Optional[str] = typer.Argument(None, help="Open at this example (its number or id): the examples "
                                                                  "before it are played, and it waits for review."),
               port: int = typer.Option(8765, "--port"), host: str = typer.Option("127.0.0.1", "--host"),
               headless: bool = typer.Option(False, "--headless", help="Print each example's review in the terminal "
                                                                        "instead (up to EXAMPLE, if given)."),
               list_only: bool = typer.Option(False, "--list", help="List the examples and stop."),
               config: Optional[str] = typer.Option(None, "--config")) -> None:
    """The small demo: a blank canvas built up one feature at a time, each from a sample article."""
    _example_demo("small_demo", example, port, host, headless, list_only, config)


@app.command("prod_demo")
def prod_demo(example: Optional[str] = typer.Argument(None, help="Open at this example (its number or id)."),
              port: int = typer.Option(8765, "--port"), host: str = typer.Option("127.0.0.1", "--host"),
              headless: bool = typer.Option(False, "--headless", help="Print each example's review in the terminal instead."),
              list_only: bool = typer.Option(False, "--list", help="List the examples and stop."),
              config: Optional[str] = typer.Option(None, "--config")) -> None:
    """The production demo: the same features in the oil-shock world after three years of synthetic history."""
    _example_demo("prod_demo", example, port, host, headless, list_only, config)


def _session_runner(config: Optional[str]):
    """The var/axelrod session that `axelrod init` and `axelrod update` keep, resumed read-only."""
    path = Path("var/axelrod")
    sess_file = path / SESSION_FILE if config is None else _session_storage(config, "oil_shock_demo")[0] / SESSION_FILE
    if not sess_file.exists():
        typer.echo("no session: run `axelrod init <scenario>` first", err=True)
        raise typer.Exit(code=1)
    session = json.loads(sess_file.read_text())
    cfg_path = config or session.get("config")
    _path, storage = _session_storage(cfg_path, session["scenario"])
    r = _runner(session["scenario"], seed=session.get("seed"), trace=False, storage=storage, config=cfg_path)
    r.resume(session)
    return r


@app.command("log")
def log_cmd(limit: int = typer.Option(30, "--limit"), process: list[str] = typer.Option([], "--process"),
            memory: Optional[str] = typer.Option(None, "--memory", help="working, long_term, or both."),
            config: Optional[str] = typer.Option(None, "--config")) -> None:
    """The session's commits, newest first: version, process, memory, message, and who vetted it."""
    from axelrod_wm.repo.history import log

    eng = _session_runner(config).controller.engine
    for c in log(eng, limit=limit, processes=set(process) or None, memory=memory):
        who = f" [{c.vetted_by}]" if c.vetted_by else ""
        typer.echo(f"v{c.version:<6} {c.recorded_at:%Y-%m-%d %H:%M} {c.process:<16} {c.memory:<9} {c.message}{who}")


@app.command("show")
def show_cmd(version: int, config: Optional[str] = typer.Option(None, "--config")) -> None:
    """One commit: its process, message, and the structure it changed."""
    from axelrod_wm.repo.history import show

    out = show(_session_runner(config).controller.engine, version)
    if out is None:
        typer.echo(f"no commit produced version {version}", err=True)
        raise typer.Exit(code=1)
    c = out["commit"]
    typer.echo(f"v{c['version']} {c['id']} {c['process']} ({c['memory']}): {c['message']}")
    typer.echo(f"  cause {c['cause']}; {c['total_changes']} changes; vetted by {c['vetted_by'] or '-'}")
    for kind, verbs in c["counts"].items():
        typer.echo(f"  {kind}: " + ", ".join(f"{n} {v}" for v, n in verbs.items()))
    for ch in out["changes"]:
        typer.echo(f"  {ch['action']:<8} {ch['kind']:<24} {ch['name']}")


@app.command("diff")
def diff_cmd(from_version: int, to_version: Optional[int] = typer.Argument(None),
             config: Optional[str] = typer.Option(None, "--config")) -> None:
    """What changed between two versions: commits by process and memory, and the net structural changes."""
    from axelrod_wm.repo.history import diff

    out = diff(_session_runner(config).controller.engine, from_version, to_version)
    typer.echo(f"v{out['from_version']} -> v{out['to_version']}: {out['commits']} commits")
    typer.echo("  by process: " + ", ".join(f"{k} {v}" for k, v in sorted(out["by_process"].items())))
    typer.echo("  by memory: " + ", ".join(f"{k} {v}" for k, v in sorted(out["by_memory"].items())))
    for ch in out["changes"]:
        typer.echo(f"  {ch['action']:<8} {ch['kind']:<24} {ch['name']}")


@app.command("export-trace")
def export_trace(run_id: str, path: str) -> None:
    """Copy a recorded trace to a file."""
    src = Path("var/axelrod/traces") / f"{run_id}.jsonl"
    if not src.exists():
        typer.echo(f"no trace {src}", err=True)
        raise typer.Exit(code=1)
    Path(path).write_text(src.read_text())
    typer.echo(f"wrote {path}")


@app.command()
def version() -> None:
    """Print the package version."""
    from axelrod_wm import __version__

    typer.echo(__version__)


if __name__ == "__main__":
    sys.exit(app())
