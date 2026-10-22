"""The construction scripts of the second round (Oct 18) on a synthetic world and corpus: the input search
(scripts/construction/inputs.py) and the reconciliation table (scripts/construction/check.py)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from tests.unit.model.test_business_construction import acme_construction, world

ROOT = Path(__file__).resolve().parents[3]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_script", ROOT / "world_model" / "scripts" / "construction" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


inputs = _load("inputs")
check = _load("check")


def corpus(tmp_path):
    c = tmp_path / "corpus"
    (c / "research").mkdir(parents=True)
    (c / "research" / "note.md").write_text("Acme results\n\nEligible import volume was 410k units in FY25.\n")
    (c / "research" / "other.txt").write_text("Nothing relevant.\n")
    (c / "research" / "broken.pdf").write_bytes(b"not a pdf")
    (c / "research" / "skip.bin").write_bytes(b"\x00")
    (c / "bench").mkdir()
    (c / "bench" / "blind.md").write_text("eligible import volume (never read)\n")
    return c


def test_the_input_search_writes_a_local_report_and_never_edits_the_world(tmp_path, capsys):
    d = world(tmp_path, acme_construction())
    before = (d / "construction" / "acme.yaml").read_text()
    c = corpus(tmp_path)
    assert inputs.main([str(d), "--entities", "acme", "--corpus", str(c),
                        "--extra-terms", "eligible import volume=FY25 imports"]) == 0
    out = capsys.readouterr().out
    assert "skipped broken.pdf" in out and "parsed 2 of 3 file(s)" in out
    assert "eligible import volume: now not_yet_reviewed; suggested found_not_connected (1 candidate(s) in research/note.md)" in out
    rows = json.loads((c / "construction" / "acme" / "input_search.json").read_text())
    assert rows[0]["candidates"][0]["file"] == "research/note.md" and rows[0]["queries"][1] == "corpus: fy25 imports"
    assert "bench/blind.md" not in rows[0]["searched_files"]                        # an excluded folder is skipped
    assert (c / "construction" / "acme" / "input_search.md").read_text().startswith("# acme: input search")
    assert (d / "construction" / "acme.yaml").read_text() == before
    assert inputs.main([str(d), "--entities", "acme", "--corpus", str(c), "--files", "research/other.txt"]) == 0
    assert "suggested not_disclosed_in_reviewed_sources (nothing in 1 file(s))" in capsys.readouterr().out
    assert inputs.main([str(d), "--entities", "ghost", "--corpus", str(c)]) == 1
    assert "ghost: no such entity" in capsys.readouterr().out


def test_the_input_search_helpers(tmp_path):
    assert inputs.extra_terms(["a b=x, y", "a b=z", "c="]) == {"a b": ["x", "y", "z"], "c": []}
    c = corpus(tmp_path)
    got = inputs.corpus_files(c, [], ["research", str(c / "bench")], ["bench"])
    assert [f.name for f in got] == ["broken.pdf", "note.md", "other.txt", "blind.md"]   # a named folder is read
    assert inputs.corpus_files(c, [str(c / "x.md")], [], []) == [c / "x.md"]
    assert inputs.tracked(c / "report.json") is False                                    # not in a repository
    assert inputs.tracked(ROOT / "world_model" / "src" / "report.json") is True
    assert inputs.tracked(ROOT / "data" / "work" / "sally" / "report.json") is False         # ignored: client data
    assert inputs.world_dir("small_demo").resolve() == (ROOT / "world_model" / "examples" / "worlds" / "small_demo").resolve()
    assert inputs.world_dir("acme_demo").resolve() == (ROOT / "tests" / "fixtures" / "clients" / "worlds" / "acme_demo").resolve()      # a client world, by name


def test_the_input_search_refuses_to_write_where_git_tracks(tmp_path, capsys, monkeypatch):
    d = world(tmp_path, acme_construction())
    monkeypatch.setattr(inputs, "tracked", lambda p: True)
    assert inputs.main([str(d), "--entities", "acme", "--corpus", str(corpus(tmp_path))]) == 1
    assert "REFUSED" in capsys.readouterr().out


def test_the_reconciliation_table(capsys):
    rows = [{"composition_id": "C1", "total_level": 10.0, "sum": 19.0, "difference": -9.0, "relative_difference": -0.9,
             "status": "flag", "unit": "bn", "unit_mismatches": ["x.a"], "missing_levels": ["x.b"], "residual": None,
             "residual_to_close": -9.0},
            {"composition_id": "C2", "total_level": None, "sum": None, "difference": None, "relative_difference": None,
             "status": "flag", "unit": "bn", "unit_mismatches": [], "missing_levels": [], "residual": "x.r",
             "residual_to_close": None},
            {"composition_id": "C3", "total_level": 5.0, "sum": 5.0, "difference": 0.0, "relative_difference": 0.0,
             "status": "ok", "unit": "bn", "unit_mismatches": [], "missing_levels": [], "residual": "x.r",
             "residual_to_close": 1.0}]
    assert check.print_reconciliation(rows, "the model's levels", suggest=True) == 2
    out = capsys.readouterr().out
    assert "-90.00%" in out and "FLAG" in out and "OK" in out and "unit differs from the total's (bn): x.a" in out
    assert "no level: x.b" in out and "residual to close: a new residual = -9" in out and "2 flag(s)" in out
    assert "x.r =" not in out                                                         # nothing to close for C2 and C3
