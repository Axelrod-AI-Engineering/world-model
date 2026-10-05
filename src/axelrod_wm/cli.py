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


def _runner(scenario: str, *, headless: bool = True, auto_approve: bool = False, seed: Optional[int] = None,
            trace: bool = True):
    from axelrod_wm.sim.runner import build_runner
    from axelrod_wm.trace import RecordingTracer

    tracer = None
    if trace:
        tracer = RecordingTracer(run_id=f"run-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}",
                                 directory=Path("var/axelrod/traces"))
    return build_runner(scenario, interactive=not headless, auto_approve=auto_approve, seed=seed, tracer=tracer)


@app.command("init")
def init_cmd(scenario: str = typer.Argument("oil_shock_demo")) -> None:
    """Build and cache the init snapshot."""
    t = time.time()
    r = _runner(scenario, trace=False)
    st = r.load()
    typer.echo(f"{scenario}: initialized at version {st.version} from {r.init_info.get('history_events')} history "
               f"events in {time.time() - t:.1f}s (cache: {r._init_cache_path()})")


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
