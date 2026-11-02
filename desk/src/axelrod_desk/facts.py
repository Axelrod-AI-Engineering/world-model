"""One fact per figure, with every document that gives it (decided Nov 2).

Figures are grouped by what they are and who says it: company, metric (or label, when the figure has no metric), period
start and end, unit, the class of claim, the speaker, and for a view held as of a date (an estimate, a target, a rating,
consensus, guidance) that date, so a later note's revised estimate is a revision, not a conflict. The speaker is the company for its own disclosures and the
publisher for anyone else, so a broker never shares a fact with the company or with another broker: a broker restating
the company's result stays the broker's view. Within a group, values within 0.5% of each other are one fact, citing every
document that gives them; when a group holds values further apart, each value is its own fact and all of them are
flagged as a conflict, to be looked at.

The base model's own reported figures (its construction's repair data) take part as facts of the company, without a page.
A newly read figure that matches one of them does not become a new fact; it becomes another citation of the old one.

A fact's key is stable across runs (a hash of the group and the value it settled on), so a review recorded against it
holds until the figures change.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

TOLERANCE = 0.005
CLASS_OF = {
    "company-reported actual": "reported", "company operating data": "reported", "company capital action": "reported",
    "company management statement": "statement", "company guidance": "guidance",
    "broker-reported actual": "reported", "broker estimate": "estimate", "broker estimate revision": "estimate",
    "broker target price": "target", "broker rating": "rating", "broker-quoted consensus": "consensus",
    "broker market data": "market data",
    "third party reported figure": "reported", "third party estimate": "estimate", "third party market data": "market data",
}
# views held as of a date: a later note or update with another value is a revision, not a conflict
DATED = ("estimate", "estimate before results", "target", "rating", "consensus", "guidance")
BEFORE_RESULTS = re.compile(r"before (the |\w+ )?results", re.I)
WS = re.compile(r"\s+")


@dataclass
class Fact:
    key: str
    company: str
    metric_id: str | None
    label: str
    period: dict[str, Any]
    unit: str
    claim: str                               # the class of claim (CLASS_OF), with a broker's estimate before results apart
    speaker: str                             # "company", or the publisher
    value: float | None
    citations: list[dict[str, Any]] = field(default_factory=list)
    conflict: bool = False
    baseline: bool = False                   # the base model already holds this figure

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "company": self.company, "metric_id": self.metric_id, "label": self.label,
                "period": self.period, "unit": self.unit, "claim": self.claim, "speaker": self.speaker, "value": self.value,
                "citations": self.citations, "conflict": self.conflict, "baseline": self.baseline}


def _norm(s: str | None) -> str:
    return WS.sub(" ", (s or "").strip().lower())


def claim_of(o: dict[str, Any]) -> str:
    kind = o.get("kind", "")
    text = f"{(o.get('scope') or {}).get('basis', '')} {o.get('label', '')}"
    if kind in ("broker estimate", "broker estimate revision") and BEFORE_RESULTS.search(text):
        return "estimate before results"
    return CLASS_OF.get(kind) or ("guidance" if "guidance" in kind else "reported")


def speaker_of(o: dict[str, Any], publisher: str | None) -> str:
    return "company" if o.get("kind", "").startswith(("company", "reported")) else _norm(publisher) or "unnamed"


def group_of(company: str, o: dict[str, Any], publisher: str | None, published: str | None = None) -> tuple:
    p = o.get("period") or {}
    claim = claim_of(o)
    as_of = (published or o.get("available_at")) if claim in DATED else None
    return (company, o.get("metric_id") or "label:" + _norm(o.get("label")), p.get("start"), p.get("end"),
            _norm(o.get("unit")), claim, speaker_of(o, publisher), as_of)


def close(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is b
    return abs(a - b) <= TOLERANCE * max(abs(a), abs(b))


def _key(group: tuple, value: float | None) -> str:
    return "f_" + hashlib.sha256(json.dumps([*group, value], default=str).encode()).hexdigest()[:16]


def resolve(records: list[dict[str, Any]], baseline: list[dict[str, Any]] = ()) -> list[Fact]:
    """Facts from accepted records (each: company, publisher, sha256, published, and the observation) and the base
    model's observations (each: company and the observation). In key order."""
    groups: dict[tuple, list[tuple[float | None, dict[str, Any]]]] = {}
    for b in baseline:
        o = b["observation"]
        cite = {"baseline": True, "observation_id": o.get("observation_id"), "source_id": (o.get("source") or {}).get("source_id"),
                "location": (o.get("source") or {}).get("location"), "available_at": o.get("available_at")}
        groups.setdefault(group_of(b["company"], o, None), []).append((o.get("value"), {"o": o, "cite": cite}))
    for r in records:
        o = r["observation"]
        cite = {"sha256": r["sha256"], "record_id": r["id"], "page": o.get("page"), "quote": o.get("quote"),
                "publisher": r.get("publisher"), "published": r.get("published"), "doc_type": r.get("doc_type"),
                "filename": r.get("filename")}
        groups.setdefault(group_of(r["company"], o, r.get("publisher"), r.get("published")), []).append(
            (o.get("value"), {"o": o, "cite": cite}))
    facts = []
    for g, items in groups.items():
        clusters: list[list[tuple[float | None, dict[str, Any]]]] = []
        for v, it in sorted(items, key=lambda x: (x[0] is None, x[0] or 0)):
            if clusters and close(clusters[-1][0][0], v):
                clusters[-1].append((v, it))
            else:
                clusters.append([(v, it)])
        for cl in clusters:
            lead = next((it for _, it in cl if it["cite"].get("baseline")), cl[0][1])
            o = lead["o"]
            cites = sorted((it["cite"] for _, it in cl), key=_rank)
            facts.append(Fact(_key(g, cl[0][0]), g[0], o.get("metric_id"), o.get("label") or "", dict(o.get("period") or {}),
                              o.get("unit") or "", g[5], g[6], o.get("value"), cites, conflict=len(clusters) > 1,
                              baseline=any(c.get("baseline") for c in cites)))
    return sorted(facts, key=lambda f: f.key)


def _rank(c: dict[str, Any]) -> tuple:
    """The order of a fact's citations: the base model's first, then filings, then other documents, earliest first."""
    kind = {"filing": 0, "presentation": 1}.get(c.get("doc_type") or "", 2)
    return (0 if c.get("baseline") else 1, kind, c.get("published") or "", c.get("sha256") or "", c.get("page") or 0)


__all__ = ["CLASS_OF", "DATED", "TOLERANCE", "Fact", "claim_of", "close", "group_of", "resolve", "speaker_of"]
