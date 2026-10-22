"""A pytest plugin for any suite that runs ingestion: every test gets a lakehouse directory of its own, the exact
`hashing` embedder (no model download), and no LLM step, so nothing reads or writes a shared lake. Turn it on from a
top-level conftest:

    pytest_plugins = ["axelrod_ingest.testing"]

The fixtures are autouse at three scopes, because module- and session-scoped apps are built before any function
fixture runs and must not share a lake either.
"""

from __future__ import annotations

import pytest

LAKE_DIR, EMBEDDER, LLM_PROVIDER = "WORLD_MODEL_LAKE_DIR", "WORLD_MODEL_EMBEDDER", "WORLD_MODEL_LLM_PROVIDER"


@pytest.fixture(autouse=True, scope="session")
def _session_lake(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setenv(LAKE_DIR, str(tmp_path_factory.mktemp("session") / "lake"))
    mp.setenv(EMBEDDER, "hashing")
    mp.delenv(LLM_PROVIDER, raising=False)
    yield
    mp.undo()


@pytest.fixture(autouse=True, scope="module")
def _module_lake(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setenv(LAKE_DIR, str(tmp_path_factory.mktemp("module") / "lake"))
    yield
    mp.undo()


@pytest.fixture(autouse=True)
def _isolated_lake(tmp_path, monkeypatch):
    monkeypatch.setenv(LAKE_DIR, str(tmp_path / "lake"))
    monkeypatch.setenv(EMBEDDER, "hashing")
    monkeypatch.delenv(LLM_PROVIDER, raising=False)
