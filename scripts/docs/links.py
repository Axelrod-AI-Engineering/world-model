"""Check every relative link in the repository's Markdown: the file it names exists, and so does the section it names.

    uv run python scripts/docs/links.py     # list the broken links, exit 1 if there are any

A link is `[text](target)` outside code. External links (http, https, mailto) are not followed. A target with
`#section` must match a heading of the target document, by GitHub's anchor (the same rule scripts/docs/toc.py uses).
Folders that are not part of the tracked tree (data, feedback, var, caches, virtual environments) are skipped.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP = {".git", ".venv", "node_modules", "data", "feedback", "var", "__pycache__", ".pytest_cache", ".ruff_cache", "media"}
LINK = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
EXTERNAL = ("http://", "https://", "mailto:")

_toc = importlib.util.spec_from_file_location("toc", Path(__file__).with_name("toc.py"))
toc = importlib.util.module_from_spec(_toc)
_toc.loader.exec_module(toc)


def markdown_files(root: Path = ROOT) -> list[Path]:
    return sorted(p for p in root.rglob("*.md") if not (set(p.relative_to(root).parts) & SKIP))


def links_of(text: str) -> list[str]:
    """Targets of the links outside fenced and inline code."""
    body = re.sub(r"```.*?```", "", text, flags=re.S)
    body = re.sub(r"`[^`\n]*`", "", body)
    return LINK.findall(body)


def anchors_of(path: Path, cache: dict[Path, set[str]]) -> set[str]:
    if path not in cache:
        cache[path] = {a for _l, _t, a in toc.headings(path.read_text())}
    return cache[path]


def broken(root: Path = ROOT) -> list[str]:
    out, cache = [], {}
    for doc in markdown_files(root):
        for target in links_of(doc.read_text()):
            if target.startswith(EXTERNAL):
                continue
            path, _, frag = target.partition("#")
            dest = doc if not path else (doc.parent / path).resolve()
            where = f"{doc.relative_to(root)}: {target}"
            if not dest.exists():
                out.append(f"{where} (no such file)")
            elif frag and dest.suffix == ".md" and frag not in anchors_of(dest, cache):
                out.append(f"{where} (no such section)")
    return out


def main() -> int:
    bad = broken()
    for b in bad:
        print(b)
    print(f"{len(bad)} broken link(s) in {len(markdown_files())} documents")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
