"""The text of a document, page by page (Nov 2): what a reader reads, what the validator checks each quote against, and
what the evaluation corpus holds, so the three always agree.

A PDF is read with poppler's `pdftotext -layout` when it is installed, one call per page: layout mode keeps a table's row on
one line, so a figure can be quoted with its row. Without poppler, and for every other format, the ingestion parser's
segments are the pages (a Word file or a web page is one page; a deck's slides and a workbook's sheets are pages). The
engine is recorded with the document, since a quote is checked against the text of the engine that read it.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from axelrod_ingest.parse import PARSER_VERSION, parse

POPPLER = "pdftotext-layout"
WS = re.compile(r"\s+")


def has_poppler() -> bool:
    return bool(shutil.which("pdftotext") and shutil.which("pdfinfo"))


def _poppler(data: bytes) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "doc.pdf"
        f.write_bytes(data)
        info = subprocess.run(["pdfinfo", str(f)], capture_output=True, text=True, check=True).stdout
        n = int(re.search(r"^Pages:\s+(\d+)", info, re.M)[1])
        return [subprocess.run(["pdftotext", "-layout", "-f", str(p), "-l", str(p), str(f), "-"], capture_output=True,
                               text=True, check=True).stdout for p in range(1, n + 1)]


def page_texts(data: bytes, filename: str, *, poppler: bool | None = None) -> tuple[list[str], str]:
    """The pages' text and the engine that read them."""
    use_poppler = has_poppler() if poppler is None else poppler
    if filename.lower().endswith(".pdf") and use_poppler:
        return _poppler(data), POPPLER
    parsed = parse(data, filename)
    pages: dict[int, list[str]] = {}
    for s in parsed.segments:
        pages.setdefault(s.page or 1, []).append(s.text)
    n = max(pages, default=1)
    return ["\n\n".join(pages.get(k, [])) for k in range(1, n + 1)], f"axelrod-parse/{PARSER_VERSION}"


def norm(text: str) -> str:
    """Text as the validator compares it: whitespace collapsed (no-break spaces too), lower case."""
    return WS.sub(" ", text.replace(" ", " ")).strip().lower()


def write(folder: Path, pages: list[str]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for k, t in enumerate(pages, 1):
        (folder / f"p{k:03d}.txt").write_text(t, encoding="utf-8")


def read(folder: Path, count: int) -> list[str]:
    return [(folder / f"p{k:03d}.txt").read_text(encoding="utf-8") for k in range(1, count + 1)]


def as_document(pages: list[str]) -> str:
    """One text with a marker before each page, as a reader is given it."""
    return "\n".join(f"=== PAGE {k} ===\n{t.rstrip()}\n" for k, t in enumerate(pages, 1))


__all__ = ["POPPLER", "as_document", "has_poppler", "norm", "page_texts", "read", "write"]
