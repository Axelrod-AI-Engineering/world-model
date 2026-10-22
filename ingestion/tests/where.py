"""Where the ingestion tests' inputs are."""

from __future__ import annotations

from pathlib import Path

TESTS = Path(__file__).resolve().parent

# TEMPORARY (until the WorldView fixture replaces the world model's graph in these tests): the synthetic client's files
WM_FIXTURE_CLIENTS = TESTS.parents[1] / "world_model" / "tests" / "fixtures" / "clients"
ACME_WORLD = WM_FIXTURE_CLIENTS / "worlds" / "acme_demo"

FIXTURES = TESTS / "fixtures"
IMPORT_BUNDLE_SAMPLE = FIXTURES / "import_bundle_sample.json"
