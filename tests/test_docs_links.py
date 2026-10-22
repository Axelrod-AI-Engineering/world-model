"""Every relative link in the repository's Markdown resolves (scripts/docs/links.py): the file exists, and so does the
section it names."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "docs" / "links.py"
spec = importlib.util.spec_from_file_location("links", SCRIPT)
links = importlib.util.module_from_spec(spec)
spec.loader.exec_module(links)


def test_the_repositorys_links_resolve():
    assert links.broken() == []


def test_the_walk_covers_every_members_documents():
    docs = {p.relative_to(links.ROOT).as_posix() for p in links.markdown_files()}
    assert {"README.md", "docs/README.md", "ingestion/docs/contract.md", "world_model/docs/README.md"} <= docs


def test_links_in_code_are_not_links():
    text = "see [a](x.md) and `[b](y.md)` but\n```\n[c](z.md)\n```\n and ![img](i.png) and [d](http://e.org)"
    assert links.links_of(text) == ["x.md", "http://e.org"]


def test_a_broken_file_and_a_broken_section_are_both_reported(tmp_path):
    (tmp_path / "a.md").write_text("# A\n\n## Real\n\n[ok](b.md#thing) [gone](nope.md) [badsec](b.md#missing) [self](#real) [bad](#nope)\n")
    (tmp_path / "b.md").write_text("# B\n\n## Thing\n")
    got = links.broken(tmp_path)
    assert got == ["a.md: nope.md (no such file)", "a.md: b.md#missing (no such section)", "a.md: #nope (no such section)"]
