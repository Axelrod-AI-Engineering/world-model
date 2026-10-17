"""Sentences and chunks (Oct 17), deterministically.

A sentence ends at ., ! or ? followed by space and a capital, digit, or opening quote, unless the word before is a
known abbreviation (U.S., Inc., e.g., vs., No., Q3) or the period sits inside a number; a line break that starts a
bullet or a new paragraph also ends one. Chunks group whole sentences up to a size, within one paragraph of one page or sheet, so
a search hit (and an imported item) never straddles two, and every chunk's span indexes the document's text exactly.
"""

from __future__ import annotations

import re

from axelrod_wm.ingest.parse import Parsed
from axelrod_wm.lake.store import Chunk

CHUNK_CHARS = 700
ABBREV = {"u.s", "u.k", "e.g", "i.e", "inc", "corp", "co", "ltd", "plc", "vs", "no", "nos", "mr", "mrs", "ms", "dr",
          "st", "jr", "sr", "fig", "est", "approx", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept",
          "oct", "nov", "dec", "etc", "al", "bn", "mn", "tn", "yr", "yrs", "q1", "q2", "q3", "q4", "h1", "h2", "fy",
          "p", "pp", "vol", "ed", "e.u", "u.n", "s.a", "n.v", "a.g", "s.p.a"}
_END = re.compile(r"[.!?]+[\"'”’)\]]*(?=\s+[\"'“‘(\[]?[A-Z0-9])")
_BREAK = re.compile(r"\n(?=\s*(?:[-•*·▪●]\s|\d+[.)]\s|[A-Z]))|\n{2,}")


def _is_abbrev(text: str, at: int) -> bool:
    """Whether the period at `at` ends a known abbreviation or an initial (a single capital letter)."""
    m = re.search(r"([A-Za-z][A-Za-z.]*)$", text[:at])
    if not m:
        return False
    word = m.group(1).lower().rstrip(".")
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
    edges = sorted(cuts)
    out = []
    for a, b in zip(edges, edges[1:]):
        seg = text[a:b]
        lead = len(seg) - len(seg.lstrip())
        trail = len(seg.rstrip())
        if trail > lead:
            out.append((base + a + lead, base + a + trail))
    return out


def chunk(parsed: Parsed, tenant: str, doc_id: str, max_chars: int = CHUNK_CHARS) -> list[Chunk]:
    """Chunks of whole sentences, at most `max_chars` long (a longer sentence is its own chunk), within a page."""
    text = parsed.text
    out: list[Chunk] = []
    for start, end, seg in parsed.spans():
        cur: list[tuple[int, int]] = []
        for s in sentences(text[start:end], base=start):
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
