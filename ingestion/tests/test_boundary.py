"""The boundary: ingestion never imports the world model, and its contract imports only the standard library and
pydantic. Both are read from the source (an AST walk), so a lazy import inside a function is caught too."""

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "axelrod_ingest"
TESTS = Path(__file__).resolve().parent
STDLIB = set(sys.stdlib_module_names)


def imports(path: Path) -> list[tuple[int, str]]:
    """(line, top-level module) of every import in a file; a relative import is inside the package."""
    out = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out += [(node.lineno, a.name.split(".")[0]) for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.append((node.lineno, node.module.split(".")[0]))
    return out


def test_the_walk_sees_the_package():
    assert len(list(SRC.rglob("*.py"))) > 15 and (SRC / "contract" / "bundle.py").exists()


@pytest.mark.parametrize("root", [SRC, TESTS], ids=["src", "tests"])
def test_nothing_in_ingestion_imports_the_world_model(root):
    bad = [f"{p.relative_to(root.parent)}:{line}" for p in sorted(root.rglob("*.py")) for line, mod in imports(p)
           if mod == "axelrod_wm"]
    assert not bad, f"ingestion must not import the world model: {bad}"


def test_the_contract_imports_only_the_standard_library_pydantic_and_itself():
    allowed = STDLIB | {"pydantic", "axelrod_ingest"}
    files = sorted((SRC / "contract").rglob("*.py"))
    assert {p.name for p in files} >= {"bundle.py", "world_view.py"}
    bad = [f"{p.name}:{line} {mod}" for p in files for line, mod in imports(p) if mod not in allowed]
    assert not bad, f"the contract may import only the standard library and pydantic: {bad}"


def test_the_contract_reaches_into_ingestion_only_through_itself():
    for p in sorted((SRC / "contract").rglob("*.py")):
        for node in ast.walk(ast.parse(p.read_text())):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and node.module.startswith("axelrod_ingest"):
                assert node.module.startswith("axelrod_ingest.contract"), f"{p.name}:{node.lineno} {node.module}"


def test_the_checker_catches_what_it_checks_for(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("import os\nfrom axelrod_wm.intake import x\n\ndef g():\n    import numpy\n")
    assert imports(f) == [(1, "os"), (2, "axelrod_wm"), (5, "numpy")]
