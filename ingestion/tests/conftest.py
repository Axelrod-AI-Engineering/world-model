"""Shared fixtures: every test gets a lakehouse of its own and the exact hashing embedder, with no LLM step."""

from __future__ import annotations

import json

import pytest

from axelrod_ingest.contract.world_view import WorldView
from tests.where import ACME_WORLD_VIEW


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


def _acme() -> dict:
    return json.loads(ACME_WORLD_VIEW.read_text())


def acme_graph() -> WorldView:
    """Acme's world as the view ingestion reads (world_model/scripts/export_world_view.py wrote the file; a drift test in
    the world model keeps it equal to the world)."""
    return WorldView.from_json(json.dumps(_acme()["world_view"]))


def acme_inverted() -> frozenset[str]:
    """The world's subject patterns marked invert: true ("the euro" names the dollar index's reciprocal)."""
    return frozenset(_acme()["inverted"])


@pytest.fixture(scope="module")
def graph():
    return acme_graph()
