"""Shared fixtures for the ingestion tests: Acme's world (loaded once per module), its inverted surfaces, a lake."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import yaml

from axelrod_ingest.extract import Rules
from axelrod_ingest.gazetteer import Gazetteer
from axelrod_ingest.lake.embed import HashingEmbedder
from axelrod_ingest.lake.sqlite import SQLiteLake
from axelrod_ingest.pipeline import Ingestor
from tests.where import ACME_WORLD

NOW = datetime(2026, 10, 17, 9, 30, tzinfo=UTC)


def acme_graph():
    from axelrod_wm.repo.snapshots import MemoryBackend
    from axelrod_wm.sim.runner import build_runner

    r = build_runner("acme_demo", interactive=True, storage=MemoryBackend(), record_checklist=False)
    r.load()
    return r.controller.engine.wm.graph


def acme_inverted() -> frozenset[str]:
    """The world's subject patterns marked invert: true ("the euro" names the dollar index's reciprocal)."""
    with open(ACME_WORLD / "templates.yaml") as f:
        subjects = yaml.safe_load(f)["subjects"]
    return frozenset(s["pattern"] for s in subjects if s.get("invert"))


@pytest.fixture(scope="module")
def graph():
    return acme_graph()


@pytest.fixture(scope="module")
def gz(graph):
    return Gazetteer(graph)


@pytest.fixture(scope="module")
def inverted():
    return acme_inverted()


@pytest.fixture(scope="module")
def rules(graph, gz, inverted):
    return Rules(graph, gz, inverted)


@pytest.fixture
def lake(tmp_path):
    store = SQLiteLake(tmp_path / "lake")
    yield store
    store.close()


@pytest.fixture
def ingestor(lake, inverted):
    return Ingestor(lake, HashingEmbedder(), clock=lambda: NOW, inverted=inverted)
