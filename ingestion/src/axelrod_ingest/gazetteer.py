"""Recognition (Oct 17): the world model's own names, found in text, deterministically.

The gazetteer is built from the world view (contract/world_view.py): every entity's name and aliases, and every value's name and
aliases, plus each value's own phrase without its entity ("net interest income" for "JPMorgan net interest income").
Matching runs over word tokens, longest match first, left to right, never overlapping; a surface written in capitals
(BoJ, ECB, MS) matches only in that case, others match in any case; one-letter surfaces never match. A Chinese or Korean
text is matched by its characters (one token each, text.py), so a surface of one or two characters ("收入", revenue) matches only
at the start of a run of them or after a particle such as 的, never inside a longer word ("利息收入", interest income).

**Shared and generic phrases.** A value's own phrase is shared by many entities ("share price", "NII", "10-year
yield"), so it is a *slot*, resolved to an entity that owns it, in this order:

1. the nearest owner named in the same sentence (the one before it first);
2. the owner named in the previous sentences (the context), when this sentence names no value itself (in a report on
   one company, a peer named earlier does not take the subject's figures);
3. the document's subject (the company a report is about, see `profile`), when the sentence names no other company
   (one of the model's, or a ticker in the possessive: "BAMI's");
4. for a market or an agency (never a company, never an economy), the one owner from the region the sentence names
   ("In the US, 2Y yields rose"), else, for markets and agencies only, the document's region ("10-year yields" in a
   note on the US are Treasuries'; a policy rate found this way serves channels only).

Otherwise it stays unresolved and yields no signal. An alias becomes a slot when values of two or more entities share
it, or when it names a company's value without naming the company ("NII", "operating profit"); a one-word lower-case
alias of a company's value ("markets", "advisory") is too loose to name anything. A value's alias that names a regional
value without its region ("core inflation", "home sales") is dropped when the text is about another region.

A value phrase's head word alone ("yields" for "Bund 10Y yield", "price" for a share price) names the value of an
entity with exactly one value of that head, and only right after that entity's name or its verb ("Bund yields",
"Komatsu's profit", "the Fed raised rates"), or, for the subject, as a key-data label or after a qualifier ("Price
(31 Jul 2026) ¥6,994", "the stock's closing price"); never after another modifier ("net income" is not net interest
income, "oil price" is not a share price). An agency's name before "hike" or "cut" stands for its policy rate ("the
ECB hike"), and a currency code beside a figure ("240 JPY") is a unit, not the currency.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass

from axelrod_ingest.cjk import CJK_CHAR
from axelrod_ingest.contract.world_view import WorldView
from axelrod_ingest.text import norm, tokens

# a name right before a head word: "Bund yields", "Komatsu's profit", "the Fed raised rates", "the BoJ held its rate"
RATE_WORDS = re.compile(r"\b(?:rate (?:hikes?|cuts?|rises?)|hikes|hike|hiking)\b", re.I)
OTHER_HIKES = re.compile(r"\b(?:price|prices|tariff|tariffs|tax|taxes|wage|wages|fee|fees|rent|cost|costs|premium|"
                         r"premiums|salary|salaries|dividend)\s+$", re.I)
OTHER_NAME = re.compile(r"\b([A-Z][A-Za-z]{1,5})\s+$")      # a name right before: "the PSL rate cut", "a BoE rate hike"
RATE_ACTION = re.compile(r"['’]?s?\s{1,8}(?:rate\s{1,8})?(?:hikes?|hiking|cuts?|cutting|tightening|easing)\b", re.I)
ADJACENT = re.compile(r"\s?(?:['’]s?\s?)?|\s(?:raised|raises|raise|raising|hiked|hikes|hike|hiking|cut|cuts|cutting|"
                      r"lowered|lowers|held|holds|kept|keeps|left|leaves|lifted|increased|reduced|eased|tightened)"
                      r"(?:\s(?:its|their|the|policy))?\s")
KEY_LINE = 90                       # a key-data line is short, and its label comes first: "Price (31 Jul 2026)
KEY_LEAD = {"shr", "share", "stock", "current", "last", "closing", "close", "latest", "static"}   # "Shr price, close", ...
# ... but a noun after it makes it something else's label: "Price Index rebased", "Income statement"
# the words after a name that RATE_ACTION and KEY_NEXT read: a short window, so neither scans a whole long text
# (CodeQL: polynomial regular expression on runs of spaces); their spaces are bounded too
LOOKAHEAD = 64
KEY_NEXT = re.compile(r"\s{1,8}(?!(?:was|is|of|at|stood|stands|closed|ended|on|as|for|in|to|reached|rose|fell|has|had|"
                      r"were)\b)[A-Za-z]{2,}")
# a sector report names many listed companies by ticker: "(WFC)", "KEY US", "8316 JT"; it has no single subject
TICKERS = re.compile(r"\((?:[A-Z]{1,5}|\d{4})(?:\.[A-Z]{1,2})?\)|\b(?:[A-Z]{1,5}|\d{4}) (?:US|JP|JT|IM|LN|FP|GY|HK|CN|SW)\b"
                     r"|\b[A-Z]{2,5}\b(?=,?\s(?:&|and)\s[A-Z]{1,5}\b|,\s[A-Z]{2,5}\b)")    # "USB, FITB & CFG"
SECTOR_TICKERS = 5
# accounting and market abbreviations, which a list of tickers is not made of
METRICS = {"EPS", "DPS", "BPS", "BVPS", "TBVPS", "NAV", "PBT", "PAT", "NI", "OP", "ROE", "ROA", "ROTE", "ROTCE", "ROIC",
           "CET", "RWA", "RWAS", "NIM", "NII", "NIR", "EBIT", "EBITDA", "PE", "PB", "PER", "PBR", "FCF", "OPEX", "CAPEX",
           "GAAP", "IFRS", "ADS", "ADR", "YOY", "QOQ", "LTM", "NTM", "TTM", "CAGR", "AUM", "AUA", "PPNR", "DCF", "SOTP"}
PUBLISHER = re.compile(r"\s*(?:&\s*Co\b|Research\b|Securities\b|Global\s+(?:Investment\s+)?Research\b|Global\s+Markets\b|"
                       r"Investment\s+Research\b|Equity\s+Research\b|Capital\s+Markets\b|International\s+plc\b|"
                       r"MUFG\b|Smith\s+Barney\b|Wealth\s+Management\s+Research\b)")
CODE = re.compile(r"^(?:USD|JPY|EUR|GBP|CNY|RMB)$")
FIGURE_NEAR = re.compile(r"\d")
# a ticker in the possessive ("BAMI's"), heading a table row ("WFC 1.88 1.84 2%"), or reporting ("BAC guided to")
OTHER_COMPANY = re.compile(r"\b([A-Z]{2,5})['’]s\b|^\s*([A-Z]{2,5})\s+(?=[\d$(+-])|\b([A-Z]{2,5})\s+(?=(?:guided|reported|"
                           r"posted|expects|expected|raised|lowered|reiterated|sees|said|beat|missed)\b)")


# a Chinese character that is a word of its own between nouns ("公司的收入": the company's revenue)
FUNCTION_CHARS = frozenset("的之及和与或于对将有是为在从至其该本等")


@dataclass(frozen=True)
class Surface:
    words: tuple[str, ...]          # lower-cased tokens
    kind: str                        # entity | value | slot
    ref: str                         # entity id, value id, or slot name (for kind == slot)
    exact: str | None = None         # the original casing, when matching must respect it
    loose: bool = False              # a value named without its entity: checked against the region in view
    head: bool = False               # a slot that is a head word alone: only a whole noun phrase


@dataclass(frozen=True)
class Match:
    kind: str                        # entity | value
    entity_id: str
    subentity_id: str | None
    start: int                       # character span in the text searched
    end: int
    surface: str
    via: str = "name"                # how a value was resolved: name | sentence | context | subject | region


def _words(s: str) -> tuple[str, ...]:
    return tuple(norm(t) for t, _a, _b in tokens(s))


def _case_sensitive(s: str) -> bool:
    """A surface written mostly in capitals (BoJ, ECB, MS, CCB) must match in that case: 'ms' is a common word."""
    letters = [c for c in s if c.isalpha()]
    return len(s) <= 5 and sum(c.isupper() for c in letters) >= max(1, len(letters) - 1)


class Gazetteer:
    def __init__(self, view: WorldView) -> None:
        self.entities = dict(view.entities)
        self.values = dict(view.values)
        self.region = {eid: e.region for eid, e in self.entities.items()}
        self.companies = {eid for eid, e in self.entities.items() if e.kind == "company"}
        # markets and agencies: what a region's yields and policy rates belong to
        self.markets = {eid for eid, e in self.entities.items() if e.kind in ("market", "agency")}
        # an agency's one policy rate, which its name stands for before "hike" or "cut" ("the ECB hike", "BoJ hikes")
        self.policy = {}
        for sid, s in sorted(self.values.items()):
            if s.attribute_kind == "policy_rate":
                self.policy[s.entity_id] = None if s.entity_id in self.policy else sid
        self.slots: dict[str, dict[str, str]] = {}          # slot phrase -> {entity id: value id}
        heads: dict[str, dict[str, set[str]]] = {}          # head word -> {entity id: its values with that head}
        surfaces: list[Surface] = []

        def add(text: str, kind: str, ref: str, loose: bool = False) -> None:
            w = _words(text)
            if not w or (len(w) == 1 and len(w[0]) < 2):
                return
            surfaces.append(Surface(w, kind, ref, text if _case_sensitive(text) else None, loose))

        def slot(text: str, eid: str, sid: str) -> None:
            w = _words(text)
            key = " ".join(w)
            exact = text if _case_sensitive(text) else None
            self.slots.setdefault(key, {}).setdefault(eid, sid)
            surfaces.append(Surface(w, "slot", key, exact, head=len(w) == 1 and exact is None))

        ent_words = {eid: {w for n in (e.name, *e.aliases) for w in _words(n)}
                     for eid, e in self.entities.items()}
        sharers: dict[tuple[str, ...], set[str]] = {}       # an alias's words -> the entities whose values use it
        for s in self.values.values():
            for a in s.aliases:
                sharers.setdefault(_words(a), set()).add(s.entity_id)
        for eid, e in sorted(self.entities.items()):
            for s in (e.name, *e.aliases):
                add(s, "entity", eid)                # an empty name has no words, and add() skips it
        for sid, s in sorted(self.values.items()):
            ent = self.entities.get(s.entity_id)
            mine = ent_words.get(s.entity_id, set())
            company = s.entity_id in self.companies
            for text in (s.name, *s.aliases):
                w = _words(text)
                named = bool(set(w) & mine)
                if w and (len(sharers.get(w, ())) > 1 or (company and not named)):
                    if not (company and len(w) == 1 and text.islower()):
                        slot(text, s.entity_id, sid)
                    continue
                add(text, "value", sid, loose=ent is not None and not named and self.region[s.entity_id] is not None)
            # the value's own phrase: its name without its entity's names, and its slot id in words
            own = {sid.split(".", 1)[-1].replace("_", " ")}
            if ent is not None:
                # drop the leading words that belong to the entity's names ("Bund 10Y yield" -> "10Y yield")
                toks = tokens(s.name)
                k = 0
                while k < len(toks) - 1 and norm(toks[k][0]) in mine:
                    k += 1
                if k:
                    own.add(s.name[toks[k][1]:])
            for phrase in sorted(own):
                w = _words(re.sub(r"\s*\([^)]*\)", "", phrase))
                if w:
                    slot(" ".join(w), s.entity_id, sid)
                    # the phrase's head word alone ("yields" for "10Y yield"): resolved only to an entity with
                    # exactly one value of that head
                    if len(w) > 1 and w[-1].isalpha() and len(w[-1]) > 2:
                        heads.setdefault(w[-1], {}).setdefault(s.entity_id, set()).add(sid)
        for head, owners in sorted(heads.items()):
            unique = {e: next(iter(v)) for e, v in owners.items() if len(v) == 1}
            if not unique:
                continue
            if head not in self.slots:
                surfaces.append(Surface((head,), "slot", head, head=True))
            for e, sid in sorted(unique.items()):
                self.slots.setdefault(head, {}).setdefault(e, sid)
        self.surface_words = {w for sf in surfaces for w in sf.words} | {sf.exact for sf in surfaces if sf.exact}
        # a trie over word tuples; at each end, the surfaces that end there (sorted, so ties resolve the same way)
        self.trie: dict = {}
        ordered = sorted(set(surfaces), key=lambda x: (x.words, x.kind, x.ref, x.exact or "", x.loose, x.head))
        for sf in ordered:
            node = self.trie
            for w in sf.words:
                node = node.setdefault(w, {})
            node.setdefault(None, []).append(sf)
        self.digest = hashlib.sha256("|".join(f"{'/'.join(x.words)}:{x.kind}:{x.ref}:{x.exact}:{x.loose}:{x.head}"
                                              for x in ordered).encode()).hexdigest()[:16]

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
            first = toks[i][1]
            if j - i <= 2 and i and toks[i - 1][2] == first and CJK_CHAR.match(text[first]) and CJK_CHAR.match(
                    text[first - 1]) and text[first - 1] not in FUNCTION_CHARS:
                i += 1                                   # "收入" inside "利息收入" (interest income) names nothing
                continue
            if CODE.match(text[toks[i][1]:toks[j - 1][2]]) and FIGURE_NEAR.search(
                    text[max(0, toks[i][1] - 2):toks[i][1]] + text[toks[j - 1][2]:toks[j - 1][2] + 2]):
                i = j                                    # "240 JPY", "EUR 84.47": a currency code, not the currency
                continue
            # one span can name an entity and a value (e.g. an alias shared); prefer value, then entity, then slot
            rank = {"value": 0, "entity": 1, "slot": 2}
            sf = sorted(hits, key=lambda x: (rank[x.kind], x.ref))[0]
            out.append((toks[i][1], toks[j - 1][2], sf, text[toks[i][1]:toks[j - 1][2]]))
            i = j
        return out

    def find(self, text: str, context_entity: str | list[str] | None = None, *, subject: str | None = None,
             region: str | None = None) -> list[Match]:
        """Entities and values named in `text` (one sentence). `context_entity` is the last entity named before it (or
        the entities named in the last few sentences, the most recent last),
        `subject` the company the document is about, and `region` the region it is about: they resolve a value
        phrase the sentence leaves without an entity."""
        raw = self._scan(text)
        named = [(a, sf.ref if sf.kind == "entity" else self.values[sf.ref].entity_id)
                 for a, _b, sf, _t in raw if sf.kind == "entity" or (sf.kind == "value" and not sf.loose)]
        has_value = any(sf.kind == "value" for _a, _b, sf, _t in raw)
        here = {self.region.get(e) for _a, e in named} - {None}
        recent = [context_entity] if isinstance(context_entity, str) else list(context_entity or [])
        last = recent[-1] if recent else None
        view = here or ({self.region.get(last)} - {None}) or ({region} - {None})
        # another company named: one of the model's, or a ticker in the possessive ("BAMI's minimum")
        ticker_at = [(m.start(), t) for m in OTHER_COMPANY.finditer(text) for t in m.groups()
                     if t and t not in self.surface_words and t.lower() not in self.surface_words]
        tickers = {t for _p, t in ticker_at}
        out: list[Match] = []
        for k, (a, b, sf, surface) in enumerate(raw):
            if sf.kind == "entity" and self.policy.get(sf.ref) and RATE_ACTION.match(text[b:b + LOOKAHEAD]):
                out.append(Match("value", sf.ref, self.policy[sf.ref], a, b, surface))
            elif sf.kind == "entity":
                out.append(Match("entity", sf.ref, None, a, b, surface))
            elif sf.kind == "value":
                eid = self.values[sf.ref].entity_id
                if not (sf.loose and view and self.region[eid] not in view):
                    out.append(Match("value", eid, sf.ref, a, b, surface))
            else:
                owners = self.slots[sf.ref]
                if sf.head:
                    # a bare head word: the name right before it ("Bund yields", "Komatsu's profit"), or the
                    # subject when it labels a short key-data line ("Price (31 Jul 2026) ¥6,994")
                    _pa, pb, psf, _pt = raw[k - 1] if k else (0, 0, sf, "")
                    adjacent = psf.kind != "slot" and ADJACENT.fullmatch(text[pb:a])
                    pe = (psf.ref if psf.kind == "entity" else self.values[psf.ref].entity_id) if adjacent else None
                    lead = [norm(t) for t, _x, _y in tokens(text[:a])]
                    q = 0
                    while q < len(lead) and lead[-1 - q] in KEY_LEAD:
                        q += 1
                    # a key-data label ("Price (31 Jul 2026) ¥6,994") or a qualified price ("the stock's closing price")
                    # (the subject's own name may head it: "Komatsu (6301 JP) ¥6,900 (Stock Price as of ...)")
                    own = not named or (q > 0 and len(text) <= KEY_LINE and {e for _p, e in named} == {subject})
                    keyed = own and not KEY_NEXT.match(text[b:b + LOOKAHEAD]) and (q > 0 or (not lead and len(text) <= KEY_LINE))
                    ent, via = (pe, "sentence") if pe in owners else (subject, "subject") if (
                        keyed and subject in owners) else (None, "")
                else:
                    # in a table row, the names in the value's own cell ("CET1 ratio | ... | JPM P&L" is not JPM's)
                    lo, hi = text.rfind(" | ", 0, a), text.find(" | ", b)
                    hi = len(text) if hi < 0 else hi
                    before = [e for pos, e in named if lo < pos < a and e in owners]
                    after = [e for pos, e in named if a < pos < hi and e in owners]
                    rivals = {e for pos, e in named if lo < pos < hi and e in self.companies and e != subject} | tickers
                    # a market's value by the region the sentence names, else (a yield, a rate) the document's
                    markets = here or ({region} - {None} if not any(e in self.companies for e in owners) else set())
                    local = [e for e in owners if self.region.get(e) in markets and e not in self.companies]
                    # the entity before, else after; the previous sentence's only when this one names no value itself
                    # ("core CPI fell to 2.4% y/y; the rate ..." is not the Fed's rate because the Fed came up earlier)
                    # the most recent owner named in the context
                    # (not when a company that is no owner was named after it: "Next is Acme Capital. Sales rose ..." is not Acme's)
                    elsewhere = bool(recent) and recent[-1] in self.companies and recent[-1] != subject and recent[-1] not in owners
                    ctx = None if elsewhere else next((e for e in reversed(recent) if e in owners), None)
                    # the nearest company named before it must be an owner ("BAC guided to NII up 6-8%; JPM guided
                    # to ..." leaves the first NII to BAC, "JPM guided ...; PNC guided to NII up 15%" the second)
                    rival_at = [p for p, _t in ticker_at if lo < p < a] + [
                        pos for pos, e in named if lo < pos < a and e in self.companies and e not in owners]
                    owner_at = [pos for pos, e in named if lo < pos < a and e in owners]
                    if rival_at and max(rival_at) > max(owner_at, default=-1):
                        before, after = [], []           # the nearest company before it is another's
                    ent, via = ((before[-1], "sentence") if before else (after[0], "sentence") if after else
                                (ctx, "context") if ctx and not has_value and not (rivals - {ctx}) and (
                                    subject in (None, ctx) or ctx not in self.companies) else
                                (subject, "subject") if subject in owners and not has_value and not rivals and not elsewhere else
                                (local[0], "region" if here else "document") if len(local) == 1 else (None, ""))
                if ent is not None:
                    out.append(Match("value", ent, owners[ent], a, b, surface, via))
        return self._rate_actions(text, raw, out, here)

    def _rate_actions(self, text: str, raw: list, out: list[Match], regions: set[str]) -> list[Match]:
        """A policy action named without its agency ("the Fed ... continued hiking", "two more rate hikes"): the
        policy rate of the agency named last before it, else (for a "rate hike" or "rate cut") of the one agency of
        the region the sentence names, else the document's. A price, tax, or wage hike, or another instrument's ("the PSL
        rate cut"), is not it."""
        taken = [(a, b + 3 if x.kind == "value" else b) for a, b, x in ((x.start, x.end, x) for x in out)]
        for m in RATE_WORDS.finditer(text):
            # not a word some name already covers ("the ECB hike" is the ECB's), nor a price's or a wage's hike
            name = OTHER_NAME.search(text[:m.start()])
            if any(a < m.end() and m.start() < b for a, b in taken) or OTHER_HIKES.search(text[:m.start()]) or (
                    name and not any(b == name.end(1) for _a, b, _sf, _t in raw)):
                continue                                 # another's hike: a price's, the PSL's, the BoE's
            named = [sf.ref for _a, b, sf, _t in raw if b <= m.start() and sf.kind == "entity" and self.policy.get(sf.ref)]
            local = [e for e, sid in self.policy.items() if sid and self.region.get(e) in regions]
            explicit = m.group(0).lower().startswith("rate")       # "rate hikes" says whose: the region's central bank
            ent, via = ((named[-1], "sentence") if named else (local[0], "region") if len(local) == 1 and explicit
                        else (None, ""))
            if ent is not None:
                out.append(Match("value", ent, self.policy[ent], m.start(), m.end(), m.group(0), via))
        return sorted(out, key=lambda x: x.start)

    def profile(self, title: str, head: str) -> tuple[str | None, str | None]:
        """What a document is about: (its subject company, its region). The subject is the one company its title
        names when the opening text names it too (or names no company and no other ticker), else the company its
        opening text names most, twice as often as any other, among the companies its
        title names (a title can name the publisher too), else among all (at least three times); a report that lists
        many tickers covers a sector and has none. The region is the subject's, else the region most of the opening
        text's names belong to."""
        # a broker named as the publisher ("Morgan Stanley Research", "Citi Global Markets") is not the subject
        publishers = {m.entity_id for m in self.find(title) if PUBLISHER.match(title[m.end:])}
        in_title = sorted({m.entity_id for m in self.find(title) if m.entity_id in self.companies} - publishers)
        counts = Counter(m.entity_id for m in self.find(head) if m.entity_id not in publishers)
        tickers = {t for t in TICKERS.findall(head) if t.strip("()") not in METRICS}   # "NII, NIR" are measures
        sector = len(tickers) >= SECTOR_TICKERS
        ranked = sorted(((n, e) for e, n in counts.items() if e in self.companies and (e in in_title or not in_title)),
                        key=lambda x: (-x[0], x[1]))
        top_company = ranked[0][1] if ranked and ranked[0][0] >= (1 if in_title else 3) and (
            len(ranked) == 1 or ranked[0][0] >= 2 * ranked[1][0]) else None
        named = [e for e in counts if e in self.companies]
        # the one company the title names, if the opening text names it too, or names no company and few tickers
        alone = len(in_title) == 1 and (counts[in_title[0]] or (not named and len(tickers) < 2))
        subject = None if sector else in_title[0] if alone else top_company
        if subject is not None:
            return subject, self.region[subject]
        regions = Counter()
        for e, n in counts.items():
            if self.region.get(e):
                regions[self.region[e]] += n
        top = sorted(regions.items(), key=lambda x: (-x[1], x[0]))
        return None, (top[0][0] if top and top[0][1] * 2 > sum(regions.values()) else None)
