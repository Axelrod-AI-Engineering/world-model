"""Shared fixtures: every test gets a lakehouse of its own and the exact hashing embedder, with no LLM step."""

from __future__ import annotations

import os

import pytest

from tests.where import WM_FIXTURE_CLIENTS

os.environ["WORLD_MODEL_CLIENT_DIR"] = str(WM_FIXTURE_CLIENTS)      # TEMPORARY: the acme graph is built by the world model


@pytest.fixture(autouse=True, scope="session")
def _session_lake(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setenv("WORLD_MODEL_LAKE_DIR", str(tmp_path_factory.mktemp("session") / "lake"))
    mp.setenv("WORLD_MODEL_EMBEDDER", "hashing")
    mp.delenv("WORLD_MODEL_LLM_PROVIDER", raising=False)
    yield
    mp.undo()


@pytest.fixture(autouse=True)
def _isolated_lake(tmp_path, monkeypatch):
    monkeypatch.setenv("WORLD_MODEL_LAKE_DIR", str(tmp_path / "lake"))
    monkeypatch.setenv("WORLD_MODEL_EMBEDDER", "hashing")
    monkeypatch.delenv("WORLD_MODEL_LLM_PROVIDER", raising=False)
