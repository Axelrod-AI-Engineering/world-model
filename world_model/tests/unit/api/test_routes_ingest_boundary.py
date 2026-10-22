"""routes_ingest.py is the part of the service that is ingestion's: it imports only axelrod_ingest, the web framework,
and the v1 plumbing (tokens, schemas, context, problems), never the rest of the world model."""

import ast

from tests.where import SRC

PLUMBING = {"axelrod_wm.api.tokens", "axelrod_wm.api.v1.schemas", "axelrod_wm.api.v1.context", "axelrod_wm.api.v1.problems"}


def test_routes_ingest_imports_only_ingestion_and_the_plumbing():
    tree = ast.parse((SRC / "api" / "v1" / "routes_ingest.py").read_text())
    mods = {f"{n.module}.{a.name}" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module for a in n.names}
    mods |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    wm = {m for m in mods if m.startswith("axelrod_wm")}
    assert any(m.startswith("axelrod_ingest.pipeline") for m in mods)
    assert all(any(m == p or m.startswith(p + ".") for p in PLUMBING) for m in wm), wm
