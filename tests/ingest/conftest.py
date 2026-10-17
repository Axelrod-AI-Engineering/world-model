"""Shared fixtures for the ingestion tests: Sally's world (loaded once per module), its inverted surfaces, a lake."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import yaml

from axelrod_wm.ingest.extract import Rules
from axelrod_wm.ingest.gazetteer import Gazetteer
from axelrod_wm.ingest.pipeline import Ingestor
from axelrod_wm.lake.embed import HashingEmbedder
from axelrod_wm.lake.sqlite import SQLiteLake

NOW = datetime(2026, 10, 17, 9, 30, tzinfo=UTC)


def sally_graph():
    from axelrod_wm.repo.snapshots import MemoryBackend
    from axelrod_wm.sim.runner import build_runner

    r = build_runner("sally_demo", interactive=True, storage=MemoryBackend(), record_checklist=False)
    r.load()
    return r.controller.engine.wm.graph


def sally_inverted() -> frozenset[str]:
    """The world's subject patterns marked invert: true ("the yen" names USD/JPY's reciprocal)."""
    with open("data/worlds/sally_demo/templates.yaml") as f:
        subjects = yaml.safe_load(f)["subjects"]
    return frozenset(s["pattern"] for s in subjects if s.get("invert"))


@pytest.fixture(scope="module")
def graph():
    return sally_graph()


@pytest.fixture(scope="module")
def gz(graph):
    return Gazetteer(graph)


@pytest.fixture(scope="module")
def inverted():
    return sally_inverted()


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
