"""Duplicates across language and basis (Oct 22): one disclosure, however many files carry it.

A company's results reach the lake as an English HKEX filing, a Chinese A-share filing, a bilingual report, and a summary:
different bytes, different languages, sometimes a different accounting basis, the same reported figures. The lakehouse
stores each once by content hash, but the figures would be read, and counted, once per copy. This links the copies.

**Fingerprint.** The reported figures of a document, normalized: every number with at least five significant digits
(`MIN_DIGITS`), as its significant digits alone, so "777,102" and "777102.00" and the same figure in thousands or in units all read
"777102", and a figure printed in another language is the same figure. A fingerprint is the document's period end, plus the
sorted multiset of these figures (its digest is a SHA-256 of both). Equal digests are the same figures to the digit.

**Same disclosure.** Two documents are one disclosure when they report the same period (the period's end date, from dates.py;
a document with no period is never matched), and the smaller one's figures are found in the larger at a rate of at least
`containment` (0.8) with at least `min_shared` (40) in common. The test is containment, not equality, because a summary holds a
fraction of a full report's figures and a translation drops some tables. The copies form a group (connected through such
pairs), with a `shared_origin` id.

**Primary.** Exactly one copy of a group is the one to read: the first by an ordered list of rules (`primary`), a rule being the name
of a test of a copy: `english_ifrs` (English text that states IFRS), `english`, `ifrs`, `completeness` (the most distinct
figures), `length`, `earliest`, `latest` (by publication date). Ties break on the document id, so the choice never depends on the
order the files arrived in. The default is English IFRS first, then the most complete. Every copy is kept, with its own text,
chunks, and bundle; only the link and the primary are recorded, in each copy's metadata (`shared_origin`).

Standard library only; the text is read from the lake, so linking is a pure function of what the lake holds.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from axelrod_ingest.lake.store import LakeStore, canonical_json

MIN_DIGITS = 5
FIGURE = re.compile(r"(?<![A-Za-z0-9_.,])[-+(]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![A-Za-z0-9_.,])\d+\.\d+|(?<![A-Za-z0-9_.,])\d{4,}")
IFRS = re.compile(r"\bK?-?IFRS\b|International Financial Reporting Standards|国际财务报告准则|國際財務報告準則|국제회계기준")
PAGE = 200
LINKED = ("parsed", "extracted")             # the statuses of a document that has text to read


@dataclass(frozen=True)
class DedupeConfig:
    containment: float = 0.8
    min_shared: int = 40
    require_period: bool = True              # a document with no period end is never matched
    primary: tuple[str, ...] = ("english_ifrs", "completeness")


@dataclass(frozen=True)
class Fingerprint:
    period_end: str
    figures: Counter
    digest: str
    english: bool
    ifrs: bool
    chars: int
    published: str

    @property
    def distinct(self) -> frozenset[str]:
        return frozenset(self.figures)


@dataclass(frozen=True)
class Group:
    id: str
    members: tuple[str, ...]                 # document ids, sorted
    primary: str
    rule: str
    containment: dict[str, float]            # each other member's containment against the primary, by document id


def figure_key(token: str) -> str:
    """A figure as its significant digits: "(777,102.50)" and "777102500" are "7771025"."""
    digits = token.replace(",", "").lstrip("-+(").replace(".", "")
    return digits.lstrip("0").rstrip("0")


def figures_of(text: str) -> Counter:
    """The multiset of a text's reported figures, normalized (see the module's docstring)."""
    keys = (figure_key(m.group(0)) for m in FIGURE.finditer(text))
    return Counter(k for k in keys if len(k) >= MIN_DIGITS)


def fingerprint(text: str, *, period_end: str = "", language: str = "", published: str = "") -> Fingerprint:
    figures = figures_of(text)
    digest = hashlib.sha256(canonical_json([period_end, sorted(figures.items())]).encode()).hexdigest()
    return Fingerprint(period_end, figures, digest, language == "en", bool(IFRS.search(text)), len(text), published)


def containment(a: Fingerprint, b: Fingerprint) -> tuple[float, int]:
    """(the share of the smaller figure set found in the larger, how many figures they share)."""
    small, large = sorted((a.distinct, b.distinct), key=len)
    shared = len(small & large)
    return (shared / len(small) if small else 0.0), shared


RULES = {
    "english_ifrs": lambda f: f.english and f.ifrs,
    "english": lambda f: f.english,
    "ifrs": lambda f: f.ifrs,
    "completeness": lambda f: len(f.figures),
    "length": lambda f: f.chars,
    "latest": lambda f: f.published or "0",
    "earliest": lambda f: tuple(-ord(c) for c in f.published) if f.published else (-10**6,),
}


def _best_first(v: Any) -> Any:
    """A rule's value turned around so that the best sorts first: a bool or a number by negation, a date text by its
    characters (a later date first), a tuple by its parts."""
    if isinstance(v, bool | int):
        return -int(v)
    if isinstance(v, tuple):
        return tuple(_best_first(x) for x in v)
    return tuple(-ord(c) for c in v)


def choose_primary(prints: dict[str, Fingerprint], rules: tuple[str, ...]) -> str:
    """The document of a group to read: best by the rules in order, then the smallest id."""
    return min(prints, key=lambda d: (tuple(_best_first(RULES[r](prints[d])) for r in rules), d))


def groups_of(prints: dict[str, Fingerprint], config: DedupeConfig = DedupeConfig()) -> list[Group]:
    """The groups of documents that are one disclosure, from their fingerprints (document id to fingerprint)."""
    ids = sorted(prints)
    parent = {d: d for d in ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    by_period: dict[str, list[str]] = {}
    for d in ids:
        if prints[d].period_end or not config.require_period:
            by_period.setdefault(prints[d].period_end, []).append(d)
    for members in by_period.values():
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                share, shared = containment(prints[a], prints[b])
                if shared >= config.min_shared and share >= config.containment:
                    parent[find(b)] = find(a)
    clusters: dict[str, list[str]] = {}
    for d in ids:
        clusters.setdefault(find(d), []).append(d)
    out = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        primary = choose_primary({d: prints[d] for d in members}, config.primary)
        gid = "so-" + hashlib.sha256("|".join(sorted(members)).encode()).hexdigest()[:16]
        out.append(Group(gid, tuple(sorted(members)), primary, ">".join(config.primary),
                         {d: round(containment(prints[d], prints[primary])[0], 4) for d in sorted(members) if d != primary}))
    return sorted(out, key=lambda g: g.id)


def link_duplicates(store: LakeStore, tenant: str, config: DedupeConfig = DedupeConfig()) -> list[Group]:
    """Find the groups among a tenant's documents and record them in each copy's metadata (`shared_origin`); a document that
    belongs to no group has none. Idempotent: the same lake gives the same groups, and a second run changes nothing."""
    docs, offset = [], 0
    while True:
        page = store.list_documents(tenant, limit=PAGE, offset=offset, order="ingested_at")
        docs += page
        if len(page) < PAGE:
            break
        offset += PAGE
    prints = {}
    for doc in sorted((d for d in docs if d.status in LINKED), key=lambda d: d.id):
        text = (store.get_text(tenant, doc.id) or ("", ""))[0]
        dates = doc.meta.get("dates", {})
        prints[doc.id] = fingerprint(text, period_end=dates.get("period_end", ""), language=doc.meta.get("language", ""),
                                     published=dates.get("published_at", ""))
    groups = groups_of(prints, config)
    where = {d: g for g in groups for d in g.members}
    for doc in docs:
        meta = {k: v for k, v in doc.meta.items() if k != "shared_origin"}
        g = where.get(doc.id)
        if g is not None:
            meta["shared_origin"] = {"group": g.id, "role": "primary" if doc.id == g.primary else "duplicate",
                                     "primary": g.primary, "members": list(g.members), "rule": g.rule,
                                     "containment": g.containment.get(doc.id, 1.0), "figures": len(prints[doc.id].figures)}
        if meta != doc.meta:
            store.update_document(tenant, doc.id, meta=meta)
    return groups
