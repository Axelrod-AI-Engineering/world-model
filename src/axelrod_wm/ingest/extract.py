"""Extraction (Oct 17): recognized sentences into import signals, by rules, deterministically.

For each sentence, the values it names (gazetteer.py) and the numbers, directions, and causal verbs around them
decide what it claims:

    move      a value with a direction and a size:   "the BoJ raised its policy rate by 25bp", "a 25bp cut",
              "net interest income rose 4%"
    observe   a value with a level in its unit:       "held rates at 3.875%", "USD/JPY fell to 152"
    move      a value with a direction and no size:   "estimates for Komatsu were cut" (a small standardized move)
    support / contradict
              two values joined by a causal verb when the model has a link between them: "higher JGB yields lift
              Tokio Marine's income" supports jgbs -> tokio_marine if the link's sign agrees
    link      the same, when the model has no link yet (proposed for review, with a modest effect)

Numbers must fit the value's unit (a percent for a rate, a currency or plain number near a price's level), and a level
must be plausible for the value (within a wide band of its posterior), so years, page numbers, and footnotes never
become levels. Every signal quotes its sentence exactly. Sentences are grouped into items by chunk.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from axelrod_wm.ingest.chunk import sentences
from axelrod_wm.ingest.gazetteer import Gazetteer, Match

# -- numbers ------------------------------------------------------------------------------------------------------
NUMBER = re.compile(
    r"(?P<sign>[+\-−–])?\s?(?P<cur>[$¥€£])?\s?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s?"
    r"(?:(?P<scale>trillion|tn|billion|bn|million|mn|mm|m|k)\b)?\s?"
    r"(?P<unit>%|percentage points?|pct pts?|ppts?|pp|per ?cent|percent|pct|basis points?|bps?|x\b)?", re.I)
DIRECTION_UP = r"(?:rais|hik|lift|increas|ris(?:e|es|en|ing)\b|rose|climb|jump|gain|surg|beat|upgrad|improv|widen|strengthen|higher|up\b|grew|grow|expand|accelerat|boost)"
DIRECTION_DOWN = r"(?:cut|lower|reduc|fell|fall|drop|declin|slip|slid|plung|miss|downgrad|weaken|narrow|contract|shrink|shrank|decreas|eas|trim|compress|slow|down\b|soft)"
# at a word's start: "crisis", "again", and "release" name no direction ("risk" is not "rise" either)
UP = re.compile(r"\b" + DIRECTION_UP + r"\w*", re.I)
DOWN = re.compile(r"\b" + DIRECTION_DOWN + r"\w*", re.I)
BY = re.compile(r"\bby\s+(?:about\s+|around\s+|roughly\s+|~)?$", re.I)
LEVEL = re.compile(r"\b(?:at|to|of|is|was|stands? at|stood at|reached|reach|hit|near|around|~|=|:)\s*(?:about\s+|around\s+|roughly\s+|~)?$", re.I)
CAUSAL_UP = re.compile(r"\b(?:lifts?|lifting|boosts?|boosting|supports?|supporting|raises?|raising|drives?|driving|"
                       r"increases?|increasing|benefits?|benefiting|helps?|helping|pushes up|adds? to|feeds?|feeding)\b", re.I)
CAUSAL_DOWN = re.compile(r"\b(?:weighs? on|weighing on|hurts?|hurting|pressures?|pressuring|compress(?:es)?|compressing|"
                         r"reduces?|reducing|cuts? into|lowers?|lowering|drags? on|dragging on|erodes?|eroding|"
                         r"squeezes?|squeezing|dampens?|dampening)\b", re.I)
SOURCE_DOWN = re.compile(r"\b(?:lower|falling|weaker|declining|cheaper|softer|reduced)\b", re.I)
SOURCE_REACH = 28                      # how far before the source a "lower" still qualifies it ("lower Bund yields")
SCALE = {"k": 1e3, "m": 1e6, "mn": 1e6, "mm": 1e6, "million": 1e6, "bn": 1e9, "billion": 1e9, "tn": 1e12, "trillion": 1e12}
CURRENCY = {"$": ("$", "usd", "dollar"), "¥": ("¥", "jpy", "yen"), "€": ("€", "eur", "euro"), "£": ("£", "gbp")}
UNDIRECTED_SD = 0.5                    # a direction without a size: half a standard unit, as a weak move
LINK_EFFECT = 0.3                      # a proposed new link's size before review
LLM_CONFIDENCE = 0.5                   # an item the LLM step alone read

# -- dates --------------------------------------------------------------------------------------------------------
MONTHS = {m: k + 1 for k, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
DATE_PATTERNS = [
    re.compile(r"\b(?P<y>20\d{2})-(?P<m>\d{2})-(?P<d>\d{2})\b"),
    re.compile(r"\b(?P<mon>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+(?P<d>\d{1,2}),?\s+(?P<y>20\d{2})\b"),
    re.compile(r"\b(?P<d>\d{1,2})\s+(?P<mon>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?,?\s+(?P<y>20\d{2})\b"),
]
FILENAME_DATE = re.compile(r"(?<!\d)(?P<y>20\d{2})[-_]?(?P<m>[01]\d)[-_]?(?P<d>[0-3]\d)(?!\d)")


def _date(y: str, m: str | None, d: str, mon: str | None = None) -> datetime | None:
    try:
        month = MONTHS[mon.lower()[:3]] if mon else int(m)
        return datetime(int(y), month, int(d), tzinfo=UTC)
    except (ValueError, KeyError, TypeError):
        return None


def find_date(text: str, filename: str = "") -> datetime | None:
    """The document's date: the first date in its opening text, else one in its file name."""
    head = text[:3000]
    found = []
    for pat in DATE_PATTERNS:
        for m in pat.finditer(head):
            g = m.groupdict()
            dt = _date(g["y"], g.get("m"), g["d"], g.get("mon"))
            if dt is not None:
                found.append((m.start(), dt))
    if found:
        return sorted(found)[0][1]
    m = FILENAME_DATE.search(filename)
    return _date(m.group("y"), m.group("m"), m.group("d")) if m else None


# -- the rules ------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Num:
    value: float                       # in the number's own unit (a percent stays 4.0 for "4%")
    unit: str                          # "%", "bp", "pp", "x", or ""
    currency: str                      # "$", "¥", ... or ""
    scale: float
    start: int
    end: int
    negative: bool


def _unit(u: str) -> str:
    if u == "pp" or u.startswith(("percentagepoint", "pctpt", "ppt")):
        return "pp"
    if u in ("%", "pct") or u.startswith("percent") or u.startswith("perc"):
        return "%"
    if u.startswith(("basispoint", "bp")):
        return "bp"
    return "x" if u == "x" else ""


def numbers(text: str) -> list[Num]:
    out = []
    for m in NUMBER.finditer(text):
        v = float(m.group("num").replace(",", ""))
        unit = _unit((m.group("unit") or "").lower().replace(" ", ""))
        scale_word = (m.group("scale") or "").lower()
        # a lone "m" after a number is only a scale when the number carries a currency ("$5m"), not "5 m" in prose
        scale = SCALE.get(scale_word, 1.0) if scale_word not in ("m",) or m.group("cur") else 1.0
        sign = m.group("sign") or ""
        first = min(x for x in (m.start("sign") if sign else None, m.start("cur") if m.group("cur") else None,
                                m.start("num")) if x is not None)
        out.append(Num(v, unit, m.group("cur") or "", scale, first, m.end(), negative=bool(sign) and sign in "-−–"))
    return out


def _unit_kind(unit: str) -> str:
    u = unit.lower()
    if u.startswith("pct") or u == "%" or "pct" in u:
        return "rate"
    return "level"


@dataclass
class Found:
    """A signal the rules found, before it becomes an import signal."""

    type: str                          # observe | move | support | contradict | link
    value_of: str | None = None
    value: float | None = None
    delta: float | None = None
    mode: str = "absolute"
    source: str | None = None
    target: str | None = None
    label: str = ""
    effect: float = 0.0
    quote: str = ""
    rule: str = ""
    confidence: float = 0.7
    direction: int = 0                 # +1 up, -1 down, 0 neither (for the item's stance)

    def signal(self) -> dict[str, Any]:
        note = f"rule: {self.rule}"
        if self.type == "observe":
            return {"type": "observe", "value_of": self.value_of, "value": round(self.value, 6), "quote": self.quote, "note": note}
        if self.type == "move":
            return {"type": "move", "value_of": self.value_of, "delta": round(self.delta, 6), "mode": self.mode,
                    "quote": self.quote, "note": note}
        if self.type == "link":
            return {"type": "link", "source": self.source, "target": self.target, "label": self.label,
                    "effect": self.effect, "quote": self.quote, "note": note}
        return {"type": self.type, "source": self.source, "target": self.target, "strength": 0.5, "quote": self.quote,
                "note": note}


class Rules:
    def __init__(self, graph: Any, gazetteer: Gazetteer, inverted: frozenset[str] | set[str] = frozenset()) -> None:
        self.graph = graph
        self.gz = gazetteer
        # patterns for surfaces that name a value's reciprocal ("the yen" for USD/JPY), from the world's templates
        self.inverted = [re.compile(p, re.I) for p in sorted(inverted)]
        self.links = {(i.source_id, i.target_id): i for i in graph.active_interactions()}

    # -- one value, one number --------------------------------------------------------------------------------
    def _posterior(self, sid: str) -> tuple[float, float]:
        s = self.graph.subentities[sid]
        return float(s.posterior.mean()), max(float(s.posterior.sd()), 1e-9)

    def _family(self, sid: str) -> str:
        return str(getattr(self.graph.subentities[sid].posterior, "family", "gaussian"))

    def plausible_level(self, sid: str, v: float) -> bool:
        mean, sd = self._posterior(sid)
        scale = float(getattr(self.graph.subentities[sid], "scale", 1.0) or 1.0)
        if self._family(sid) in ("lognormal", "gamma"):
            return v > 0 and mean > 0 and abs(math.log(v / mean)) <= math.log(3.0)
        return abs(v - mean) <= 6 * sd + 4 * scale

    def _level(self, sid: str, n: Num) -> float | None:
        """The number as a level of the value, in its unit, or None when the units don't fit."""
        unit = self.graph.subentities[sid].unit
        kind = _unit_kind(unit)
        if kind == "rate":
            if n.unit == "%":
                v = n.value
            elif n.unit == "bp":
                v = n.value / 100.0
            else:
                return None
        else:
            if n.unit in ("%", "bp", "pp", "x"):
                return None
            # the unit's own currency is the first one it names ("¥ per $" is in yen, "€ per ¥100" in euros)
            low = unit.lower()
            named = sorted((low.find(x), c) for c, names in CURRENCY.items() for x in names if x in low)
            want = named[0][1] if named else ""
            if n.currency and want and n.currency != want:
                return None
            v = n.value * (n.scale / (1e9 if "bn" in unit.lower() else 1e12 if "tn" in unit.lower() else 1.0)) \
                if n.scale != 1.0 else n.value
        v = -v if n.negative else v
        return v if self.plausible_level(sid, v) else None

    def _delta(self, sid: str, n: Num, direction: int) -> tuple[float, str] | None:
        """The number as a change of the value: (delta, mode), signed by the direction."""
        unit = self.graph.subentities[sid].unit
        rate = _unit_kind(unit) == "rate"
        if n.unit == "bp":
            d, mode = n.value / 100.0, "absolute"
            if not rate:
                return None
        elif n.unit == "pp":
            if not rate:
                return None
            d, mode = n.value, "absolute"
        elif n.unit == "%":
            if rate:
                d, mode = n.value, "absolute"          # "rose by 0.25%" of a rate is a quarter point
            else:
                d, mode = n.value / 100.0, "relative"
        else:
            return None
        if d == 0 or d > (5.0 if mode == "absolute" else 0.9):
            return None
        return (direction * abs(d), mode)

    @staticmethod
    def _direction(text: str) -> int:
        up = UP.search(text)
        down = DOWN.search(text)
        if up and not down:
            return 1
        if down and not up:
            return -1
        if up and down:
            return 1 if up.start() < down.start() else -1
        return 0

    def value_claims(self, sent: str, m: Match, nums: list[Num], prev_end: int, next_start: int) -> list[Found]:
        """What the sentence says about one value: its level when stated, else a move with a size, else a bare
        direction. The direction is read from the value's clause: from the previous mention to the next."""
        sid = m.subentity_id
        assert sid is not None
        flip = -1 if any(r.fullmatch(m.surface) for r in self.inverted) else 1   # "the yen strengthened": USD/JPY fell
        clause = sent[prev_end:next_start]
        after = [n for n in nums if m.end <= n.start < next_start]
        before = [n for n in nums if prev_end <= n.start and n.end <= m.start and m.start - n.end <= 14]
        # 1. a level: "at 3.875%", "to 1.25%", "fell to 152"
        for n in after:
            gap = sent[m.end:n.start]
            if LEVEL.search(gap) and flip == 1:
                lvl = self._level(sid, n)
                if lvl is not None:
                    return [Found("observe", value_of=sid, value=lvl, quote=sent, rule="level", confidence=0.75,
                                  direction=self._direction(clause))]
        # 2. a move with a size: "raised ... by 25bp", "rose 4%", "a 25bp cut in ..."
        direction = flip * self._direction(clause)
        if direction:
            for n in after:
                gap = sent[m.end:n.start]
                if BY.search(gap) or (n.unit in ("%", "bp", "pp") and len(gap) <= 40):
                    got = self._delta(sid, n, direction)
                    if got:
                        return [Found("move", value_of=sid, delta=got[0], mode=got[1], quote=sent,
                                      rule="direction + size", confidence=0.8, direction=direction)]
            for n in reversed(before):
                got = self._delta(sid, n, direction)
                if got:
                    return [Found("move", value_of=sid, delta=got[0], mode=got[1], quote=sent,
                                  rule="size + direction before", confidence=0.75, direction=direction)]
            # 3. a bare direction, unless a causal verb makes the clause about a link
            if not CAUSAL_UP.search(clause) and not CAUSAL_DOWN.search(clause):
                return [Found("move", value_of=sid, delta=direction * UNDIRECTED_SD, mode="standardized", quote=sent,
                              rule="direction without size", confidence=0.45, direction=direction)]
        return []

    # -- two values and a causal verb -------------------------------------------------------------------------
    def causal_claims(self, sent: str, matches: list[Match]) -> list[Found]:
        out: list[Found] = []
        for k, a in enumerate(matches):
            for b in matches[k + 1:]:
                between = sent[a.end:b.start]
                up, down = CAUSAL_UP.search(between), CAUSAL_DOWN.search(between)
                if not (up or down) or len(between) > 80:
                    continue
                first = up if up and (not down or up.start() < down.start()) else down
                sign = 1 if first is up else -1              # the first causal verb decides, and names the link
                if SOURCE_DOWN.search(sent[max(0, a.start - SOURCE_REACH):a.start]):
                    sign = -sign                             # "lower yields lift ..." claims a negative link
                pairs = self._pairs(a, b)
                if len(pairs) != 1 or pairs[0][0] == pairs[0][1]:      # ambiguous, or one value named twice
                    continue
                src, dst = pairs[0]
                verb = first.group(0)
                link = self.links.get((src, dst))
                if link is not None:
                    polarity = 1 if float(link.forward.effect.mean()) >= 0 else -1
                    out.append(Found("support" if polarity == sign else "contradict", source=src, target=dst,
                                     quote=sent, rule=f"causal verb '{verb}' on a known link", confidence=0.6))
                else:                                # no link: both are values (an entity pairs only via links)
                    out.append(Found("link", source=src, target=dst, label=verb.lower(), effect=sign * LINK_EFFECT,
                                     quote=sent, rule=f"causal verb '{verb}', no link yet", confidence=0.4))
        return out

    def _pairs(self, a: Match, b: Match) -> list[tuple[str, str]]:
        """The value pairs two mentions can stand for: their own values, or (for an entity) the values of it that
        a link joins to the other side."""
        srcs = [a.subentity_id] if a.subentity_id else self.graph.entities[a.entity_id].subentity_ids
        dsts = [b.subentity_id] if b.subentity_id else self.graph.entities[b.entity_id].subentity_ids
        if a.subentity_id and b.subentity_id:
            return [(a.subentity_id, b.subentity_id)]
        return sorted({(s, d) for s in srcs for d in dsts if (s, d) in self.links})


# -- a document into items --------------------------------------------------------------------------------------------
CATEGORY = {"policy_rate": "rates", "bond_yield": "rates", "interest_rate": "rates", "real_rate": "rates",
            "fx_rate": "fx", "inflation_rate": "macro", "growth_rate": "macro", "commodity_price": "commodities",
            "asset_price": "markets", "revenue_flow": "earnings", "volatility": "markets", "capital_flow": "flows",
            "margin": "earnings", "production_flow": "markets", "spending_flow": "macro", "loss_flow": "credit",
            "share": "earnings", "stress_index": "credit"}


@dataclass
class ChunkClaims:
    ord: int
    text: str
    found: list[Found] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    mentions: list[Match] = field(default_factory=list)
    sentence_spans: list[tuple[int, int]] = field(default_factory=list)


def claims_of_chunk(rules: Rules, ord_: int, text: str, context: str | None) -> tuple[ChunkClaims, str | None]:
    out = ChunkClaims(ord_, text)
    for a, b in sentences(text):
        sent = text[a:b]
        ms = rules.gz.find(sent, context)
        out.sentence_spans.append((a, b))
        for m in ms:
            out.mentions.append(Match(m.kind, m.entity_id, m.subentity_id, a + m.start, a + m.end, m.surface))
            if m.entity_id not in out.entities:
                out.entities.append(m.entity_id)
        if ms:
            context = ms[-1].entity_id
        nums = numbers(sent)
        vals = [m for m in ms if m.subentity_id]
        claimed: set[str] = set()                    # one claim per value per sentence
        for k, m in enumerate(vals):
            if m.subentity_id in claimed:
                continue
            prev_end = vals[k - 1].end if k else 0
            nxt = vals[k + 1].start if k + 1 < len(vals) else len(sent)
            for f in rules.value_claims(sent, m, nums, prev_end, nxt):
                out.found.append(f)
                claimed.add(m.subentity_id)
        for f in rules.causal_claims(sent, ms):
            if not any(g.type == f.type and g.source == f.source and g.target == f.target and g.quote == f.quote
                       for g in out.found):
                out.found.append(f)
    return out, context


def category_of(graph: Any, found: list[Found]) -> str:
    for f in found:
        sid = f.value_of or f.target
        if sid in graph.subentities:
            return CATEGORY.get(graph.subentities[sid].attribute_kind, "other")
    return "other"


def stance_of(found: list[Found]) -> str:
    ups = sum(1 for f in found if f.direction > 0)
    downs = sum(1 for f in found if f.direction < 0)
    return "up" if ups > downs else "down" if downs > ups else ("mixed" if ups else "")


TICKER = re.compile(r"^(?:\d{3,6} [A-Z]{2}|[A-Z]{1,5})$")


def item_of(graph: Any, claims: ChunkClaims, *, doc_prefix: str, published_at: datetime, source: str,
            source_type: str, kind: str, title: str, extra: list[dict] | None = None) -> dict[str, Any] | None:
    """One import item for a chunk: its rule signals, then any the LLM step added (`extra`); None when it has none."""
    extra = list(extra or [])
    if not claims.found and not extra:
        return None
    first = claims.text[claims.sentence_spans[0][0]:claims.sentence_spans[0][1]] if claims.sentence_spans else claims.text
    headline = first if len(first) <= 200 else first[:197].rstrip() + "…"
    tickers = sorted({a for e in claims.entities if str(graph.entities[e].kind) == "company"
                      for a in graph.entities[e].aliases if TICKER.match(a) and len(a) > 1})
    conf = sum(f.confidence for f in claims.found) / len(claims.found) if claims.found else LLM_CONFIDENCE
    first_id = next((x for x in (extra[0].get("value_of"), extra[0].get("target")) if x), None) if extra else None
    category = category_of(graph, claims.found) if claims.found else CATEGORY.get(
        graph.subentities[first_id].attribute_kind, "other") if first_id in graph.subentities else "other"
    return {
        "id": f"{doc_prefix}-{claims.ord:04d}", "published_at": published_at.isoformat(), "source": source or title,
        "source_type": source_type, "kind": kind, "headline": headline, "summary": claims.text,
        "entities": sorted(claims.entities), "tickers": tickers, "category": category,
        "stance": stance_of(claims.found), "relevance": round(min(0.9, 0.4 + 0.1 * (len(claims.found) + len(extra))), 2),
        "confidence": round(conf, 3), "tags": ["extracted", *(["llm"] if extra else [])],
        "signals": [f.signal() for f in claims.found] + extra,
    }
