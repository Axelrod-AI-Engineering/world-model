"""Where the tests' inputs are, from the package's own roots (axelrod_wm/paths.py), so the working directory never
matters. Every path a test names comes from here."""

from __future__ import annotations

from pathlib import Path

from axelrod_wm.paths import REPO_ROOT, WM_ROOT

TESTS = Path(__file__).resolve().parent
FIXTURES = TESTS / "fixtures"
FIXTURE_CLIENTS = FIXTURES / "clients"              # the synthetic client: scenarios acme_demo, worlds acme_demo
IMPORT_BUNDLE_SAMPLE = FIXTURES / "import_bundle_sample.json"
INNER_LOOP_SUITE = FIXTURES / "inner_loop"          # a small invented suite: questions, fixtures, excerpts, recipes
INNER_LOOP_KEY = FIXTURES / "inner_loop_key" / "answer_key.json"      # its invented key, read only by the grader's tests

EXAMPLES = WM_ROOT / "examples"
TAXONOMY = WM_ROOT / "taxonomy"
ECONOMY = EXAMPLES / "worlds" / "economy"
SMALL_DEMO_WORLD = EXAMPLES / "worlds" / "small_demo"
OIL_DIR = EXAMPLES / "scenarios" / "oil_shock_demo"
OIL_YAML = OIL_DIR / "scenario.yaml"
SMALL_DEMO_DIR = EXAMPLES / "scenarios" / "small_demo"
ACME_SCENARIO = FIXTURE_CLIENTS / "scenarios" / "acme_demo" / "scenario.yaml"
ACME_WORLD = FIXTURE_CLIENTS / "worlds" / "acme_demo"

SRC = WM_ROOT / "src" / "axelrod_wm"
SCRIPTS = WM_ROOT / "scripts"
DOCS = WM_ROOT / "docs"
OPENAPI = DOCS / "api" / "openapi.yaml"
FLOWCHART = REPO_ROOT / "docs" / "flowchart.svg"
CORE_PATCH = REPO_ROOT / "integrations" / "core" / "0001-world-model-service-mcp-tools.patch"
INGESTION_FIXTURES = REPO_ROOT / "ingestion" / "tests" / "fixtures"
ACME_WORLD_VIEW = INGESTION_FIXTURES / "world_view_acme.json"       # written by scripts/export_world_view.py
EXPORT_WORLD_VIEW = SCRIPTS / "export_world_view.py"
