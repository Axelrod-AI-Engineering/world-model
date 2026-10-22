"""The coverage gate (scripts/coverage_gate.py): what it passes, and each way it fails."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "coverage_gate.py"
spec = importlib.util.spec_from_file_location("coverage_gate", SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def entry(lines=(10, 10), branches=(4, 4), missing=()):
    stmts, hit = lines
    nb, hb = branches
    return {"summary": {"num_statements": stmts, "covered_lines": hit, "missing_lines": stmts - hit,
                        "num_branches": nb, "covered_branches": hb, "missing_branches": nb - hb},
            "missing_lines": list(missing)}


@pytest.fixture
def repo(tmp_path):
    """A workspace with two source files in each member."""
    for member, pkg in gate.MEMBERS.items():
        d = tmp_path / member / "src" / pkg / "sub"
        d.mkdir(parents=True)
        (d.parent / "__init__.py").write_text("")
        (d / "a.py").write_text("x = 1\n")
    return tmp_path


def report(member, **files):
    pkg = gate.MEMBERS[member]
    return {"files": {f"src/{pkg}/{name}": e for name, e in files.items()}}


FULL = {"__init__.py": entry((0, 0), (0, 0)), "sub/a.py": entry()}


def test_a_fully_covered_member_passes(repo):
    assert gate.failures(report("ingestion", **FULL), "ingestion", repo) == []


def test_an_uncovered_line_or_branch_fails_and_names_the_file(repo):
    r = report("ingestion", **{"__init__.py": entry((0, 0), (0, 0)), "sub/a.py": entry((10, 9), (4, 3), missing=[7])})
    (msg,) = gate.failures(r, "ingestion", repo)
    assert "axelrod_ingest/sub/a.py" in msg and "1 lines and 1 branches" in msg and "[7]" in msg


def test_a_file_never_measured_fails(repo):
    r = report("ingestion", **{"__init__.py": entry((0, 0), (0, 0))})
    assert gate.failures(r, "ingestion", repo) == ["axelrod_ingest/sub/a.py: not in the report (never imported, so never measured)"]


def test_a_report_with_none_of_the_members_files_fails(repo):
    assert "no source file of world_model" in gate.failures(report("ingestion", **FULL), "world_model", repo)[0]


def test_paths_are_read_relative_to_src_in_either_form(repo):
    r = {"files": {"/abs/ci/ingestion/src/axelrod_ingest/__init__.py": entry((0, 0), (0, 0)),
                   "src\\axelrod_ingest\\sub\\a.py": entry()}}
    assert gate.failures(r, "ingestion", repo) == []


def test_totals_and_the_table_by_subpackage():
    files = {"axelrod_wm/x.py": entry((10, 9), (4, 4)), "axelrod_wm/api/y.py": entry((10, 10), (0, 0)),
             "axelrod_wm/api/z.py": entry((0, 0), (0, 0))}
    assert gate.totals(files) == {"lines": 95.0, "branches": 100.0, "n_lines": 20, "n_branches": 4}
    assert list(gate.by_subpackage(files)) == ["(top level)", "api"]
    text = gate.summary("world_model", files, {"passed": 3, "failed": 0, "skipped": 1})
    assert "3 passed, 0 failed, 1 skipped" in text and "| `api` | 100.00% | 100.00% |" in text


def test_pct_of_nothing_is_complete():
    assert gate.pct(0, 0) == 100.0 and gate.pct(1, 3) == 33.33


def write_junit(path, *tags):
    cases = "".join(f'<testcase classname="t" name="n{i}">{"<" + t + "/>" if t != "pass" else ""}</testcase>'
                    for i, t in enumerate(tags))
    path.write_text(f'<testsuites><testsuite>{cases}</testsuite></testsuites>')
    return path


def run(repo, tmp_path, member, rep, junit=None, summary=None):
    f = tmp_path / "coverage.json"
    f.write_text(json.dumps(rep))
    argv = [str(f), "--member", member]
    if junit:
        argv += ["--junit", str(junit)]
    if summary:
        argv += ["--summary", str(summary)]
    return gate.main(argv, repo)


def test_main_passes_prints_and_writes_the_summary(repo, tmp_path, capsys):
    j = write_junit(tmp_path / "j.xml", "pass", "skipped")
    out = tmp_path / "summary.md"
    assert run(repo, tmp_path, "ingestion", report("ingestion", **FULL), j, out) == 0
    assert "ingestion: lines 100.00%" in capsys.readouterr().out
    assert "### ingestion" in out.read_text()


def test_main_fails_on_a_failed_test_even_when_coverage_is_complete(repo, tmp_path, capsys):
    j = write_junit(tmp_path / "j.xml", "pass", "failure", "error")
    assert run(repo, tmp_path, "ingestion", report("ingestion", **FULL), j) == 1
    assert "2 tests failed" in capsys.readouterr().err


def test_main_fails_on_a_gap_and_reports_it_on_stderr(repo, tmp_path, capsys):
    assert run(repo, tmp_path, "world_model", report("ingestion", **FULL)) == 1
    assert "FAIL no source file of world_model" in capsys.readouterr().err


def test_the_real_workspace_lists_its_sources():
    for member in gate.MEMBERS:
        assert f"{gate.MEMBERS[member]}/__init__.py" in gate.source_files(member)
