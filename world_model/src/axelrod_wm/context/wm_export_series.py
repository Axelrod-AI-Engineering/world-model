"""Update mechanics as a series of evaluation exports (Oct 31): what a world model does when it is updated, shown as
exports an evaluator can compare without running the model.

core's Mission Control scores an uploaded export; it cannot call the model. So the operations a world model must support
are exercised here, on a fresh model built from a scenario, and an export (context/wm_export.py) is written after each
step, its `manifest.scenario` naming the step, the operation and the step it is to be compared with:

    0 build          the model as constructed
    1 ingest         after the first bundle
    2 export_again   the same state exported again             (compare with 1: identical except generated_at)
    3 reingest       the first bundle imported again           (compare with 1: nothing changes)
    4 ingest         after the second bundle (first, second)
    5 ingest         a second model given second, then first   (compare with 4: the same current values?)
    6 as_of          the state read as of step 1's clock       (compare with 1)
    7 restore        step 1's version restored                 (compare with 1: the same state hash)

The series states what happened and does not judge it: step 5 differs from step 4 today, because an earlier-dated item
imported later is folded on the next processed day (sim/imports.py), and that is for the evaluator to report.
Supersession and undo are not exercised: the model does not support them, and its export says so (`capabilities`).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from axelrod_wm.context.wm_export import wm_export
from axelrod_wm.control.controller import ControllerError
from axelrod_wm.repo.history import log


def attempt(run: Callable[[dict], dict], bundle: dict) -> str:
    """What an import answered: its run's state ("regated" when a waiting change was read again), or the refusal, which
    for a bundle already imported is "nothing new to import"."""
    try:
        return str(run(bundle).get("state"))
    except ControllerError as e:
        return str(e)


def update_series(make_runner: Callable[[], Any], first: dict, second: dict, *, world_model_id: str, label: str,
                  generated_at: str, series_id: str, subjects: tuple[str, ...] = ()) -> list[dict]:
    """The eight exports above; `make_runner` returns a freshly loaded import runner (sim/imports.ImportRunner) each
    time it is called, and `first` and `second` are import bundles."""

    def snap(r: Any, step: int, operation: str, *, inputs: tuple[str, ...] = (), order: str | None = None,
             target_step: int | None = None, note: str | None = None, state: tuple | None = None,
             as_of: Any = None) -> dict:
        eng = r.controller.engine
        if state is None:
            wm, ltm, version, state_hash = eng.wm, eng.ltm, eng.version, eng.state_hash
            proposals = list(r.controller.proposals.values())
        else:
            wm, ltm, version = state
            state_hash, proposals = eng.version_info(version).state_hash, []
        scenario = {"series_id": series_id, "step": step, "operation": operation, "inputs": list(inputs),
                    "order": order, "target_step": target_step, "note": note,
                    "as_of_requested": None if as_of is None else as_of.isoformat()}
        return wm_export(wm, ltm, world_model_id=world_model_id, label=label, version=version, state_hash=state_hash,
                         generated_at=generated_at, subjects=subjects,
                         versions=[v for v in eng.storage.versions() if v.version <= version],
                         changes=log(eng, limit=100_000, before_version=version + 1), proposals=proposals,
                         scenario=scenario)

    a, b = first["title"], second["title"]
    one = make_runner()
    out = [snap(one, 0, "build")]
    one.import_items(first)
    eng = one.controller.engine
    version_1, clock_1 = eng.version, eng.wm.clock
    out.append(snap(one, 1, "ingest", inputs=(a,)))
    out.append(snap(one, 2, "export_again", inputs=(a,), target_step=1))
    out.append(snap(one, 3, "reingest", inputs=(a,), target_step=1, note=attempt(one.import_items, first)))
    one.import_items(second)
    out.append(snap(one, 4, "ingest", inputs=(a, b), order="first,second"))
    two = make_runner()
    two.import_items(second)
    two.import_items(first)
    out.append(snap(two, 5, "ingest", inputs=(b, a), order="second,first", target_step=4))
    wm, ltm, v = eng.snapshots.as_of(clock_1)
    out.append(snap(one, 6, "as_of", target_step=1, state=(wm, ltm, v), as_of=clock_1))
    wm, ltm = eng.restore(version_1)
    out.append(snap(one, 7, "restore", target_step=1, state=(wm, ltm, version_1)))
    return out
