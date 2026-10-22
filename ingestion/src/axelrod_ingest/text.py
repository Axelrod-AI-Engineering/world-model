"""Text, the one way: how a document's words are cut and compared. Recognition (gazetteer.py) and search
(lake/search.py) both match on these forms, so they live here, with no dependency on either."""

from __future__ import annotations

import re

from axelrod_ingest.cjk import HAN, HANGUL, KANA

# A word, a sign, or one ideograph, kana, or Hangul syllable: those scripts are matched by their characters (a name is a
# run of tokens, found longest first), because Chinese has no spaces and a Korean word carries its particle ("영업이익은").
TOKEN = re.compile(rf"[A-Za-z0-9]+(?:[&./-][A-Za-z0-9]+)*|[&$¥€£₩%]|[{HAN}{KANA}{HANGUL}]")
POSSESSIVE = re.compile(r"^(?:s|S)$")


def norm(word: str) -> str:
    """A token's matching form: lower case, and a plural's -s dropped (yields, rates), so forms meet."""
    w = word.lower()
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")) and w.isalpha():
        w = w[:-1]
    return w


def tokens(text: str) -> list[tuple[str, int, int]]:
    """Word tokens with their spans; a possessive's s ("JPMorgan's", "Tokio Marine’s") is not a token of its own."""
    out = []
    for m in TOKEN.finditer(text):
        if POSSESSIVE.match(m.group(0)) and m.start() > 0 and text[m.start() - 1] in "'’":
            continue
        out.append((m.group(0), m.start(), m.end()))
    return out
