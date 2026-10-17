"""Recognition (Oct 17): the world model's own names, found in text, deterministically.

The gazetteer is built from the graph: every entity's name, short name, and aliases, and every value's name and
aliases, plus each value's own phrase without its entity ("net interest income" for "JPMorgan net interest income").
Matching runs over word tokens, longest match first, left to right, never overlapping; a surface written in capitals
(BoJ, ECB, MS) matches only in that case, others match in any case; one-letter surfaces never match.

A value's own phrase is shared by many entities ("share price"), so it is resolved to the nearest entity named in the
same sentence (the one before it first), else the last entity named earlier in the chunk; if no entity has that
value, it stays unresolved and yields no signal. Recognition never guesses beyond that.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

TOKEN = re.compile(r"[A-Za-z0-9]+(?:[&./-][A-Za-z0-9]+)*|[&$¥€£%]")
POSSESSIVE = re.compile(r"^(?:s|S)$")


def norm(word: str) -> str:
    """A token's matching form: lower case, and a plural's -s dropped (yields, rates), so forms meet."""
    w = word.lower()
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")) and w.isalpha():
        w = w[:-1]
    return w


@dataclass(frozen=True)
class Surface:
    words: tuple[str, ...]          # lower-cased tokens
    kind: str                        # entity | value | slot
    ref: str                         # entity id, value id, or slot name (for kind == slot)
    exact: str | None = None         # the original casing, when matching must respect it


@dataclass(frozen=True)
class Match:
    kind: str                        # entity | value
    entity_id: str
    subentity_id: str | None
    start: int                       # character span in the text searched
    end: int
    surface: str


def tokens(text: str) -> list[tuple[str, int, int]]:
    """Word tokens with their spans; a possessive's s ("JPMorgan's", "Tokio Marine’s") is not a token of its own."""
    out = []
    for m in TOKEN.finditer(text):
        if POSSESSIVE.match(m.group(0)) and m.start() > 0 and text[m.start() - 1] in "'’":
            continue
        out.append((m.group(0), m.start(), m.end()))
    return out


def _words(s: str) -> tuple[str, ...]:
    return tuple(norm(t) for t, _a, _b in tokens(s))


def _case_sensitive(s: str) -> bool:
    """A surface written mostly in capitals (BoJ, ECB, MS, CCB) must match in that case: 'ms' is a common word."""
    letters = [c for c in s if c.isalpha()]
    return len(s) <= 5 and sum(c.isupper() for c in letters) >= max(1, len(letters) - 1)


class Gazetteer:
    def __init__(self, graph: Any) -> None:
        self.entities = {eid: e for eid, e in graph.entities.items()}
        self.values = {sid: s for sid, s in graph.subentities.items()}
        self.slots: dict[str, dict[str, str]] = {}          # slot phrase -> {entity id: value id}
        heads: dict[str, dict[str, set[str]]] = {}          # head word -> {entity id: its values with that head}
        surfaces: list[Surface] = []

        def add(text: str, kind: str, ref: str) -> None:
            w = _words(text)
            if not w or (len(w) == 1 and len(w[0]) < 2):
                return
            surfaces.append(Surface(w, kind, ref, text if _case_sensitive(text) else None))

        for eid, e in sorted(self.entities.items()):
            for s in (e.name, getattr(e, "short", None), *e.aliases):
                if s:
                    add(s, "entity", eid)
        for sid, s in sorted(self.values.items()):
            ent = self.entities.get(s.entity_id)
            for text in (s.name, *s.aliases):
                add(text, "value", sid)
            # the value's own phrase: its name without its entity's names, and its slot id in words
            own = {sid.split(".", 1)[-1].replace("_", " ")}
            if ent is not None:
                # drop the leading words that belong to the entity's names ("Bund 10Y yield" -> "10Y yield")
                ent_words = {w for n in (ent.name, getattr(ent, "short", None) or "", *ent.aliases) for w in _words(n)}
                toks = tokens(s.name)
                k = 0
                while k < len(toks) - 1 and norm(toks[k][0]) in ent_words:
                    k += 1
                if k:
                    own.add(s.name[toks[k][1]:])
            for phrase in sorted(own):
                w = _words(re.sub(r"\s*\([^)]*\)", "", phrase))
                if w:
                    key = " ".join(w)
                    self.slots.setdefault(key, {})[s.entity_id] = sid
                    surfaces.append(Surface(w, "slot", key))
                    # the phrase's head word alone ("yields" for "10Y yield"): resolved only to an entity with
                    # exactly one value of that head
                    if len(w) > 1 and w[-1].isalpha() and len(w[-1]) > 2:
                        heads.setdefault(w[-1], {}).setdefault(s.entity_id, set()).add(sid)
        for head, owners in sorted(heads.items()):
            unique = {e: next(iter(v)) for e, v in owners.items() if len(v) == 1}
            if not unique:
                continue
            if head not in self.slots:
                surfaces.append(Surface((head,), "slot", head))
            for e, sid in sorted(unique.items()):
                self.slots.setdefault(head, {}).setdefault(e, sid)
        # a trie over word tuples; at each end, the surfaces that end there (sorted, so ties resolve the same way)
        self.trie: dict = {}
        for sf in sorted(set(surfaces), key=lambda x: (x.words, x.kind, x.ref, x.exact or "")):
            node = self.trie
            for w in sf.words:
                node = node.setdefault(w, {})
            node.setdefault(None, []).append(sf)
        self.digest = hashlib.sha256("|".join(f"{'/'.join(x.words)}:{x.kind}:{x.ref}:{x.exact}" for x in sorted(
            set(surfaces), key=lambda x: (x.words, x.kind, x.ref, x.exact or ""))).encode()).hexdigest()[:16]

    def _scan(self, text: str) -> list[tuple[int, int, Surface, str]]:
        """Longest non-overlapping matches, left to right: (start, end, surface, matched text)."""
        toks = tokens(text)
        out = []
        i = 0
        while i < len(toks):
            node, best, j = self.trie, None, i
            while j < len(toks) and norm(toks[j][0]) in node:
                node = node[norm(toks[j][0])]
                j += 1
                if None in node:
                    raw = text[toks[i][1]:toks[j - 1][2]]
                    hits = [sf for sf in node[None] if sf.exact is None or sf.exact == raw]
                    if hits:
                        best = (j, hits)
            if best is None:
                i += 1
                continue
            j, hits = best
            # one span can name an entity and a value (e.g. an alias shared); prefer value, then entity, then slot
            rank = {"value": 0, "entity": 1, "slot": 2}
            sf = sorted(hits, key=lambda x: (rank[x.kind], x.ref))[0]
            out.append((toks[i][1], toks[j - 1][2], sf, text[toks[i][1]:toks[j - 1][2]]))
            i = j
        return out

    def find(self, text: str, context_entity: str | None = None) -> list[Match]:
        """Entities and values named in `text` (one sentence); `context_entity` is the last entity named before it,
        used to resolve a value phrase the sentence leaves without an entity."""
        raw = self._scan(text)
        named = [(a, sf.ref if sf.kind == "entity" else self.values[sf.ref].entity_id)
                 for a, _b, sf, _t in raw if sf.kind in ("entity", "value")]
        out: list[Match] = []
        for a, b, sf, surface in raw:
            if sf.kind == "entity":
                out.append(Match("entity", sf.ref, None, a, b, surface))
            elif sf.kind == "value":
                out.append(Match("value", self.values[sf.ref].entity_id, sf.ref, a, b, surface))
            else:
                owners = self.slots.get(sf.ref, {})
                before = [e for pos, e in named if pos < a and e in owners]
                after = [e for pos, e in named if pos > a and e in owners]
                ent = (before[-1] if before else after[0] if after else
                       context_entity if context_entity in owners else None)
                if ent is not None:
                    out.append(Match("value", ent, owners[ent], a, b, surface))
        return out
