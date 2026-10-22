"""Shared fixtures. The isolated lake, the hashing embedder, and no LLM step come from the plugin the package ships."""

from __future__ import annotations

import json

import pytest

from axelrod_ingest.contract.world_view import WorldView
from tests.where import ACME_WORLD_VIEW

pytest_plugins = ["axelrod_ingest.testing"]


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
