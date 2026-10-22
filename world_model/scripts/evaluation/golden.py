"""Run a golden test bank against a world: the responder answers through v1 reads only, the grader scores four outcomes.

    python scripts/evaluation/golden.py --world sally_demo --cases <bank.yaml> [--only T01A,T02A] \
        [--baselines <bundle.json> ...] --out <results.json>

`--baselines` is operator setup, not part of any answer: each bundle is imported through the v1 bundle and change
routes and approved in process, so dated observations exist before the questions are asked. The bank and the results
stay wherever the caller keeps client data (never in tracked files).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from axelrod_wm.api.app import create_app  # noqa: E402
from axelrod_wm.evaluation.golden import V1Reader, dump, load_cases, run, summary_line  # noqa: E402
from axelrod_wm.repo.snapshots import MemoryBackend  # noqa: E402


def load_baselines(client: TestClient, app, paths: list[str]) -> list[str]:
    """Import each bundle through v1 and approve its changes in process (operator setup)."""
    wm = "/v1/world-models/" + client.get("/v1/world-models").json()["data"][0]["id"]
    log = []
    for i, p in enumerate(paths):
        body = json.loads(Path(p).read_text())
        r = client.post(wm + "/bundles", json=body, headers={"Idempotency-Key": f"golden-b{i}"})
        if r.status_code >= 300:
            log.append(f"{Path(p).name}: bundle refused ({r.status_code})")
            continue
        bid = r.json()["data"]["id"]
        r = client.post(wm + "/changes", json={"bundle_id": bid}, headers={"Idempotency-Key": f"golden-c{i}"})
        log.append(f"{Path(p).name}: changes {r.status_code}")
    from axelrod_wm.api.routes import _resume_if_awaited

    st = app.state.world_models[wm.rsplit("/", 1)[-1]].st
    ctl = st.controller
    approved = 0
    for _ in range(1000):                      # the update run waits on one change at a time: approve, then drive on
        pending = list(ctl.pending_proposals())
        if not pending:
            break
        for prop in pending:
            client.portal.call(st.call, partial(ctl.approve, prop.id, by="operator-setup",
                                                note="golden bank: baselines loaded before the questions"))
            approved += 1
            run_id = client.portal.call(st.call, _resume_if_awaited, st, prop.id)
            if run_id is not None:
                client.portal.call(st.drive, run_id)
    log.append(f"approved {approved} changes; {len(ctl.pending_proposals())} still pending")
    return log


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--world", default="sally_demo")
    ap.add_argument("--cases", required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--baselines", nargs="*", default=[])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    logging.disable(logging.INFO)
    only = [x for x in a.only.split(",") if x] or None
    cases = load_cases(Path(a.cases), only)
    app = create_app(scenario=a.world, storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        setup = load_baselines(c, app, a.baselines) if a.baselines else []
        results = run(cases, V1Reader(c))
    for r in results:
        r["setup"] = setup
        r["world"] = a.world
    dump(results, Path(a.out))
    for line in setup:
        print("setup:", line)
    for r in results:
        print(summary_line(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
