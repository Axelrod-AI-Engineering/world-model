"""Inference engine: pluggable stages behind interfaces (§8).

# DECISION: default component modules are imported by ``load_defaults()`` (called from
# ``build_engine``) rather than at package import time. Memory and control modules import
# engine record types (Forecast, Explanation, ...), so eager imports here would be circular.
"""

from __future__ import annotations

_LOADED = False

DEFAULT_MODULES = (
    "axelrod_wm.engine.parse",
    "axelrod_wm.engine.classify",
    "axelrod_wm.engine.recall",
    "axelrod_wm.engine.prefill",
    "axelrod_wm.engine.abduction",
    "axelrod_wm.engine.analyze",
    "axelrod_wm.engine.propagation",
    "axelrod_wm.engine.learning",
    "axelrod_wm.engine.kernel_update",
    "axelrod_wm.engine.frontier_test",
    "axelrod_wm.engine.explain",
    "axelrod_wm.engine.voi",
    "axelrod_wm.engine.consolidate",
    "axelrod_wm.engine.performance.isolate",
    "axelrod_wm.engine.performance.predict",
    "axelrod_wm.engine.performance.couple",
    "axelrod_wm.engine.performance.unify",
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
