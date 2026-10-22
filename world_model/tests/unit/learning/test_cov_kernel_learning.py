"""The "none" kernel updater: closing a day on its schedule leaves every interaction's timing alone."""

from __future__ import annotations

from axelrod_wm.learning.kernel_learning import NoKernelUpdater
from tests.conftest import close_day, constructed_engine, make_config, predict_day


def test_the_none_updater_changes_no_kernel():
    cfg = make_config(components={"kernel_updater": "none"})
    eng = constructed_engine(build=True, config=cfg)
    assert isinstance(eng.components["kernel_updater"], NoKernelUpdater)
    kernels = {i: inter.forward.kernel.model_dump() for i, inter in eng.wm.graph.interactions.items()}
    every = max(1, int(cfg.kernel_update.every_days))
    d = eng.wm.last_processed_day + 1
    while (d + 1) % every:
        d += 1
    predict_day(eng, d)
    _moves, report = close_day(eng, d)
    assert report.kernels_updated == []
    assert {i: inter.forward.kernel.model_dump() for i, inter in eng.wm.graph.interactions.items()} == kernels
