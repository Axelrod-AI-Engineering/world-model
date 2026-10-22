"""Registers default components that live outside the engine package (§8.16)."""

from __future__ import annotations

from axelrod_wm.engine.registry import registry
from axelrod_wm.evaluation import backtest as _backtest  # noqa: F401  (scorer)
from axelrod_wm.intake import refiner as _refiner  # noqa: F401  (refiner)
from axelrod_wm.intake import resolver as _resolver  # noqa: F401  (entity_resolver)
from axelrod_wm.intake import structured as _structured  # noqa: F401  (translator "structured")
from axelrod_wm.intake import translators as _translators  # noqa: F401  (translator)
from axelrod_wm.model.distributions import LinkKalmanUpdater, PosteriorUpdater
from axelrod_wm.repo import review as _review  # noqa: F401  (review_policy)
from axelrod_wm.repo.snapshots import FilesBackend, MemoryBackend, StorageBackend

_pu = registry("posterior_updater", PosteriorUpdater)
if "link_kalman" not in _pu.names():
    _pu.register("link_kalman")(LinkKalmanUpdater)

_st = registry("storage", StorageBackend)
for _name, _cls in (("files", FilesBackend), ("memory", MemoryBackend)):
    if _name not in _st.names():
        _st.register(_name)(_cls)
