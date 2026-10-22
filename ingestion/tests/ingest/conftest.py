"""Shared fixtures for the ingestion tests: Acme's world (loaded once per module), its inverted surfaces, a lake."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from axelrod_ingest.extract import Rules
from axelrod_ingest.gazetteer import Gazetteer
from axelrod_ingest.lake.embed import HashingEmbedder
from axelrod_ingest.lake.sqlite import SQLiteLake
from axelrod_ingest.pipeline import Ingestor
from tests.conftest import acme_inverted

NOW = datetime(2026, 10, 17, 9, 30, tzinfo=UTC)


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
