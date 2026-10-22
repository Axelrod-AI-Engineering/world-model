"""Inference engine: pluggable stages behind interfaces (§8).

# DECISION: default component modules are imported by ``load_defaults()`` (called from
# ``build_engine``) rather than at package import time. Memory and control modules import
# engine record types (Forecast, Explanation, ...), so eager imports here would be circular.
"""

from __future__ import annotations

_LOADED = False

DEFAULT_MODULES = (
    "axelrod_wm.shared.parse",
    "axelrod_wm.shared.classify",
    "axelrod_wm.shared.recall",
    "axelrod_wm.shared.prefill",
    "axelrod_wm.shared.recognize",
    "axelrod_wm.learning.abduction",
    "axelrod_wm.shared.analyze",
    "axelrod_wm.dynamics.propagation",
    "axelrod_wm.dynamics.daily",
    "axelrod_wm.learning.fold",
    "axelrod_wm.learning.generalize",
    "axelrod_wm.learning.kernel_learning",
    "axelrod_wm.learning.frontier_test",
    "axelrod_wm.shared.explain",
    "axelrod_wm.inference.voi",
    "axelrod_wm.learning.consolidate",
    "axelrod_wm.inference.isolate",
    "axelrod_wm.inference.predict",
    "axelrod_wm.inference.couple",
    "axelrod_wm.inference.unify",
    "axelrod_wm.engine.defaults",
)


def load_defaults() -> None:
    """Import every default module so that registration happens."""
    global _LOADED
    if _LOADED:
        return
    import importlib

    for name in DEFAULT_MODULES:
        importlib.import_module(name)
    _LOADED = True
