"""Keep a table of contents at the top of every document in docs/, world_model/docs/, ingestion/docs/ (and the README).

The contents go between `<!-- toc -->` and `<!-- /toc -->`, right after the title and its opening paragraph; a
document without the markers gets them there. Entries link to the document's sections (## headings, and ###
under them in long documents), with GitHub's anchors.

    uv run python scripts/docs/toc.py            # write them
    uv run python scripts/docs/toc.py --check    # exit 1 if any is missing or stale
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BEGIN, END = "<!-- toc -->", "<!-- /toc -->"
DEEP_AT = 400            # a document this many lines long also lists its ### headings


def slug(heading: str, seen: dict[str, int]) -> str:
    s = re.sub(r"[`*_]|\[([^\]]*)\]\([^)]*\)", r"\1", heading).strip().lower()
    s = re.sub(r"[^\w\- ]", "", s).replace(" ", "-")
    n = seen.get(s, 0)
    seen[s] = n + 1
    return s if n == 0 else f"{s}-{n}"


def headings(text: str) -> list[tuple[int, str, str]]:
    body = re.sub(r"```.*?```", "", text, flags=re.S)
    seen: dict[str, int] = {}
    out = []
    for m in re.finditer(r"^(#{1,4}) (.+?)\s*$", body, re.M):
        level, title = len(m.group(1)), m.group(2)
        anchor = slug(title, seen)
        out.append((level, title, anchor))
    return out


def toc(text: str) -> str:
    deep = text.count("\n") >= DEEP_AT
    lines = []
    for level, title, anchor in headings(text):
        if level == 2 or (deep and level == 3):
            plain = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", title)
            lines.append(f"{'  ' * (level - 2)}- [{plain}](#{anchor})")
    if len(lines) < 2:
        return ""
    return "**Contents**\n\n" + "\n".join(lines)


def place_markers(text: str) -> str:
    """After the H1 and its first paragraph (or the H1 alone, if a heading or table follows it)."""
    m = re.search(r"^# .+\n", text, re.M)
    if not m:
        return f"{BEGIN}\n{END}\n\n" + text
    rest = text[m.end():]
    para = re.match(r"\n((?:(?!#|\||```|<!--)[^\n]+\n)+)", rest)
    at = m.end() + (para.end() if para else 0)
    return text[:at] + f"\n{BEGIN}\n{END}\n" + text[at:]


def update(text: str) -> str:
    if BEGIN not in text:
        text = place_markers(text)
    contents = toc(text)
    block = f"{BEGIN}\n{contents}\n{END}" if contents else f"{BEGIN}\n{END}"
    return re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), lambda _: block, text, count=1, flags=re.S)


def files() -> list[Path]:
    return [ROOT / "README.md", *(p for folder in ("docs", "world_model/docs", "ingestion/docs")
                                  for p in sorted((ROOT / folder).rglob("*.md")))]


def main() -> int:
    check = "--check" in sys.argv
    stale = []
    for path in files():
        text = path.read_text()
        new = update(text)
        if new != text:
            stale.append(path.relative_to(ROOT))
            if not check:
                path.write_text(new)
    for p in stale:
        print(("stale: " if check else "updated: ") + str(p))
    return 1 if (check and stale) else 0


if __name__ == "__main__":
    sys.exit(main())
