"""Where the ingestion tests' inputs are."""

from __future__ import annotations

from pathlib import Path

TESTS = Path(__file__).resolve().parent

FIXTURES = TESTS / "fixtures"
IMPORT_BUNDLE_SAMPLE = FIXTURES / "import_bundle_sample.json"
ACME_WORLD_VIEW = FIXTURES / "world_view_acme.json"     # world_model/scripts/export_world_view.py writes it
