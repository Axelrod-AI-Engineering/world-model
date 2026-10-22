"""Sentences and chunks (Oct 17), deterministically.

A sentence ends at ., ! or ? followed by space and a capital, digit, or opening quote, unless the word before is a
known abbreviation (U.S., Inc., e.g., vs., No., Q3) or the period sits inside a number; a line break that starts a
bullet, a new paragraph, or a capitalized line after a short or title-case one (a heading or a label; after a
full-width line of prose it is the same sentence wrapped) also ends one, and so does every row of a table (a line with " | " cells, as the spreadsheet,
CSV, and HTML parsers write them, or a line that ends in two or more figures, as a PDF's tables read). A sentence longer than a chunk (a run-on line from a PDF) is cut at a line break,
else at a space. Chunks group whole sentences up to a size, within one paragraph of one page or sheet, so a search hit
(and an imported item) never straddles two, and every chunk's span indexes the document's text exactly.
"""

from __future__ import annotations

import re

from axelrod_wm.ingest.parse import Parsed
from axelrod_wm.lake.store import Chunk

CHUNK_CHARS = 700
ROW_CHARS = 12000        # a table row longer than a chunk stays one sentence and one chunk, up to this
ABBREV = {"u.s", "u.k", "e.g", "i.e", "inc", "corp", "co", "ltd", "plc", "vs", "no", "nos", "mr", "mrs", "ms", "dr",
          "st", "jr", "sr", "fig", "est", "approx", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept",
          "oct", "nov", "dec", "etc", "al", "bn", "mn", "tn", "yr", "yrs", "q1", "q2", "q3", "q4", "h1", "h2", "fy",
          "p", "pp", "vol", "ed", "e.u", "u.n", "s.a", "n.v", "a.g", "s.p.a"}
_END = re.compile(r"[.!?]+[\"'”’)\]]*(?=\s+[\"'“‘(\[]?[A-Z0-9])")
_BREAK = re.compile(r"\n(?=\s*(?:[-•*·▪●◦‣]\s|[◆◇■□►▶➢➤✓✔\uf0a7\uf0b7\uf0d8\uf076]|\*\S|\d+[.)]\s))|\n{2,}")
_CAPITAL_LINE = re.compile(r"\n(?=\s*[A-Z])")
SHORT_LINE = 50          # a line this short before a capitalized one is a heading or a label, not wrapped prose
CELL = " | "
# a line that ends in two or more figures is a row of a table drawn as text ("Operating profit (¥bn) 3,766.2 3,843.4")
ROW = re.compile(r"(?:\s[-+(]?[$¥€£]?\d[\d,]*(?:\.\d+)?%?\)?){2,}\s*$")
# ... and so is a line of column periods ("3/26 3/27E 3/28E", "1 Oct 3M 6M 12M", "2023 2024 2025E ... 3Q25 4Q25")
PERIOD_WORD = re.compile(r"^(?:(?:FY|CY)?['’]?\d[\d/.'’-]*[EeAaFfMYQH]?\d*[Ee]?|[1-4][QH]\d{2,4}[Ee]?|Q[1-4][-]?\d{2,4}[Ee]?|"
                         r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$")


def tabular(line: str) -> bool:
    """A row of a table drawn as text: a line that ends in two or more figures, or one mostly of periods."""
    words = line.split()
    return bool(ROW.search(line)) or (len(words) >= 3 and sum(bool(PERIOD_WORD.match(w)) for w in words) * 2 >= len(words))


def _is_abbrev(text: str, at: int) -> bool:
    """Whether the period at `at` ends a known abbreviation or an initial (a single capital letter)."""
    m = re.search(r"([A-Za-z][A-Za-z.]*)$", text[max(0, at - 24):at])     # the word before; never the whole text
    if not m:
        return False
    word = m.group(1).lower().rstrip(".")
    # a single letter is an initial ("J. Smith"); a word right after a figure is a unit ("$96.5b.", "$5bn.")
    if m.start(1) > 0 and text[max(0, at - 24):at][m.start(1) - 1].isdigit():
        return False
    return word in ABBREV or (len(word) == 1 and word.isalpha())


def sentences(text: str, base: int = 0) -> list[tuple[int, int]]:
    """Spans (start, end) of the sentences of `text`, offset by `base`; whitespace is trimmed off each span."""
    cuts = {0, len(text)}
    for m in _END.finditer(text):
        if text[m.start()] == "." and _is_abbrev(text, m.start()):
            continue
        cuts.add(m.end())
    for m in _BREAK.finditer(text):
        cuts.add(m.start())
    for m in _CAPITAL_LINE.finditer(text):
        # a capitalized line starts a sentence after a short line (a heading, a label); after a long one it is wrapped
        # prose ("... in North\nAmerica is recovering")
        line = text[text.rfind("\n", 0, m.start()) + 1:m.start()].strip()
        words = re.findall(r"[A-Za-z][A-Za-z'’-]*", line)
        heading = len(words) >= 3 and sum(w[0].isupper() for w in words) >= 0.6 * len(words)
        if len(line) < SHORT_LINE or heading:
            cuts.add(m.start())
    at = 0
    lines = text.split("\n")
    for line, nxt in zip([*lines, ""], [*lines[1:], ""]):   # a table row is a sentence of its own, never cut
        if CELL in line:
            cuts -= set(range(at + 1, at + len(line)))
        at += len(line)
        if CELL in line or CELL in nxt or tabular(line) or tabular(nxt):
            cuts.add(at)
        at += 1
    edges = sorted(cuts)
    out = []
    for a, b in zip(edges, edges[1:]):
        seg = text[a:b]
        lead = len(seg) - len(seg.lstrip())
        trail = len(seg.rstrip())
        if trail > lead:
            out.append((base + a + lead, base + a + trail))
    return out


def split_long(text: str, span: tuple[int, int], max_chars: int) -> list[tuple[int, int]]:
    """A span cut into pieces of at most `max_chars`: at the last line break before the limit, else the last space,
    else at the limit; whitespace is trimmed off each piece."""
    a, b = span
    out = []
    while b - a > max_chars:
        window = text[a:a + max_chars + 1]
        cut = window.rfind("\n")
        if cut <= 0:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = max_chars
        out.append((a, a + len(text[a:a + cut].rstrip())))      # a piece starts on a non-space, so it is never empty
        a += cut
        while text[a].isspace():                                # the span ends on a non-space, so this stops in it
            a += 1
    out.append((a, b))
    return out


def chunk(parsed: Parsed, tenant: str, doc_id: str, max_chars: int = CHUNK_CHARS) -> list[Chunk]:
    """Chunks of whole sentences, at most `max_chars` long, within a paragraph of a page (a longer sentence is cut)."""
    text = parsed.text
    out: list[Chunk] = []
    for start, end, seg in parsed.spans():
        cur: list[tuple[int, int]] = []
        # a spreadsheet's row stays whole (its cells line up with its header's), up to a limit; prose is cut
        spans = [p for sp in sentences(text[start:end], base=start)
                 for p in split_long(text, sp, ROW_CHARS if CELL in text[sp[0]:sp[1]] else max_chars)]
        for s in spans:
            # a chunk never crosses a paragraph break (a blank line) and stays under max_chars
            if cur and (s[1] - cur[0][0] > max_chars or "\n\n" in text[cur[-1][1]:s[0]]):
                out.append(Chunk(tenant=tenant, doc_id=doc_id, ord=len(out), start=cur[0][0], end=cur[-1][1],
                                 text=text[cur[0][0]:cur[-1][1]], page=seg.page, section=seg.label))
                cur = []
            cur.append(s)
        if cur:
            out.append(Chunk(tenant=tenant, doc_id=doc_id, ord=len(out), start=cur[0][0], end=cur[-1][1],
                             text=text[cur[0][0]:cur[-1][1]], page=seg.page, section=seg.label))
    return out
