"""Default registrations that live outside the engine package."""

from __future__ import annotations

import importlib

from axelrod_wm.engine import defaults
from axelrod_wm.engine.registry import registry
from axelrod_wm.model.distributions import LinkKalmanUpdater
from axelrod_wm.repo.snapshots import FilesBackend, MemoryBackend


def test_defaults_register_once_when_reloaded():
    pu, st = registry("posterior_updater"), registry("storage")
    assert (pu.get("link_kalman"), st.get("files"), st.get("memory")) == (LinkKalmanUpdater, FilesBackend, MemoryBackend)
    importlib.reload(defaults)            # already registered: nothing is replaced or duplicated
    assert (pu.get("link_kalman"), st.get("files"), st.get("memory")) == (LinkKalmanUpdater, FilesBackend, MemoryBackend)
    assert st.names() == ["files", "memory"]
