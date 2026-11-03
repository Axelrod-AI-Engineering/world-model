"""A cited figure, as a reader writes it, and the checks every one must pass before it counts (Nov 2).

This is the form the Q3 and sell-side reads of Oct 31 to Nov 2 used (their validators, `validate_q3.py` and
`validate_records.py`, are the model for `check`), less what the desk fills in itself: the document (the one being read),
its source entry, and the publication date. A reader returns `{"observations": [...], "themes": [...]}`.

An observation must:
- have a kind its document's class allows (a company's own document gives company kinds, a broker note broker kinds);
- name a metric in its company's catalog, or none (`metric_id` null, with a precise label);
- have a closed period (type, start and end, ISO dates, start not after end); a point in time has start = end;
- cite a page of the document whose text holds its quote verbatim (whitespace collapsed, lower case, nothing else);
- show its printed figure (`raw.amount`) in that quote, and carry a number and a unit, except a broker rating (no value).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from axelrod_desk.pages import norm

COMPANY_KINDS = ("company-reported actual", "company operating data", "company guidance", "company capital action",
                 "company management statement")
BROKER_KINDS = ("broker-reported actual", "broker estimate", "broker estimate revision", "broker target price",
                "broker rating", "broker-quoted consensus", "broker market data")
OTHER_KINDS = ("third party reported figure", "third party estimate", "third party market data")
KINDS = {"company": COMPANY_KINDS, "sell_side": BROKER_KINDS, "other": OTHER_KINDS}
PERIODS = ("quarter", "half", "year", "nine_months", "point", "month", "other")

_PERIOD = {"type": "object", "additionalProperties": False, "required": ["label", "type", "start", "end"],
           "properties": {"label": {"type": "string"}, "type": {"enum": list(PERIODS)},
                          "start": {"type": "string"}, "end": {"type": "string"}}}
_RAW = {"type": "object", "additionalProperties": False, "required": ["amount", "unit"],
        "properties": {"line": {"type": "string"}, "amount": {"type": ["number", "null"]}, "unit": {"type": "string"}}}
OBSERVATION = {
    "type": "object", "additionalProperties": False,
    "required": ["metric_id", "label", "period", "value", "unit", "scope", "kind", "page", "quote", "raw"],
    "properties": {
        "metric_id": {"type": ["string", "null"]}, "label": {"type": "string"}, "period": _PERIOD,
        "value": {"type": ["number", "null"]}, "unit": {"type": "string"},
        "scope": {"type": "object", "additionalProperties": False, "required": ["perimeter", "basis"],
                  "properties": {"perimeter": {"type": "string"}, "basis": {"type": "string"}}},
        "kind": {"type": "string"}, "page": {"type": "integer", "minimum": 1}, "quote": {"type": "string"}, "raw": _RAW,
        "previous": {"type": "object", "additionalProperties": False,
                     "properties": {"value": {"type": "number"}, "quote": {"type": "string"}}},
        "note": {"type": "string"}}}
THEME = {"type": "object", "additionalProperties": False, "required": ["theme", "summary", "citations"],
         "properties": {"theme": {"type": "string"}, "summary": {"type": "string"},
                        "citations": {"type": "array", "items": {
                            "type": "object", "additionalProperties": False, "required": ["page", "quote"],
                            "properties": {"page": {"type": "integer", "minimum": 1}, "quote": {"type": "string"}}}}}}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["observations", "themes"],
          "properties": {"observations": {"type": "array", "items": OBSERVATION},
                         "themes": {"type": "array", "items": THEME}}}


def schema_for(source_class: str) -> dict[str, Any]:
    """SCHEMA with the kinds of one source class spelled out, so a reader cannot use another class's."""
    obs = {**OBSERVATION, "properties": {**OBSERVATION["properties"], "kind": {"enum": list(KINDS[source_class])}}}
    return {**SCHEMA, "properties": {**SCHEMA["properties"], "observations": {"type": "array", "items": obs}}}


def shown(x: float) -> set[str]:
    """Ways a figure may be printed: 12.3, 12,345, 1,234.5, 12345 (sign dropped; trailing zeros with and without)."""
    a = abs(x)
    out = {f"{a:g}", f"{a:,.0f}", f"{a:.0f}", f"{a:,.1f}", f"{a:.1f}", f"{a:,.2f}", f"{a:.2f}"}
    return {s.rstrip("0").rstrip(".") if "." in s else s for s in out} | out


def _date(s: Any) -> date | None:
    try:
        return date.fromisoformat(s) if isinstance(s, str) else None
    except ValueError:
        return None


def check(o: dict[str, Any], *, source_class: str, pages: list[str], catalog: set[str]) -> list[str]:
    """The problems with one observation (none when it counts)."""
    problems = []
    kinds = KINDS[source_class]
    if o.get("kind") not in kinds:
        problems.append(f"kind {o.get('kind')!r} is not one of {', '.join(kinds)}")
    if o.get("metric_id") is not None and o["metric_id"] not in catalog:
        problems.append(f"metric_id {o['metric_id']!r} is not in the company's catalog (use null and a precise label)")
    p = o.get("period") or {}
    start, end = _date(p.get("start")), _date(p.get("end"))
    if p.get("type") not in PERIODS:
        problems.append(f"period.type {p.get('type')!r} is not one of {', '.join(PERIODS)}")
    if start is None or end is None:
        problems.append("period.start and period.end must be YYYY-MM-DD")
    elif start > end:
        problems.append("period.start is after period.end")
    page, quote = o.get("page"), norm(o.get("quote") or "")
    if not isinstance(page, int) or not 1 <= page <= len(pages):
        problems.append(f"page {page!r} is not a page of the document (1 to {len(pages)})")
    elif not quote or quote not in norm(pages[page - 1]):
        problems.append(f"the quote is not on page {page} verbatim: {quote[:80]!r}")
    v = o.get("value")
    if v is None:
        if o.get("kind") != "broker rating":
            problems.append("value is missing (only a broker rating has none)")
    elif not isinstance(v, (int, float)) or isinstance(v, bool):
        problems.append("value must be a number")
    else:
        if not (o.get("unit") or "").strip():
            problems.append("a value needs a unit")
        raw = (o.get("raw") or {}).get("amount")
        amount = v if raw is None else raw
        if isinstance(amount, (int, float)) and not any(s.replace(" ", "") in quote.replace(" ", "")
                                                        for s in shown(float(amount))):
            problems.append(f"the printed figure {amount} is not in the quote")
    return problems


def check_theme(t: dict[str, Any], pages: list[str]) -> list[str]:
    problems = []
    for c in t.get("citations", []):
        page = c.get("page")
        if not isinstance(page, int) or not 1 <= page <= len(pages) or norm(c.get("quote") or "") not in norm(pages[page - 1]):
            problems.append(f"theme {t.get('theme')!r}: a quote is not on page {page}")
    return problems


def check_all(reading: dict[str, Any], *, source_class: str, pages: list[str], catalog: set[str]) -> dict[str, Any]:
    """Each observation with its problems, and each theme that passed (a theme with a bad quote is dropped)."""
    obs = [{**o, "problems": check(o, source_class=source_class, pages=pages, catalog=catalog)}
           for o in reading.get("observations", [])]
    themes = [t for t in reading.get("themes", []) if not check_theme(t, pages)]
    return {"observations": obs, "themes": themes, "failed": sum(1 for o in obs if o["problems"])}


__all__ = ["BROKER_KINDS", "COMPANY_KINDS", "KINDS", "OTHER_KINDS", "PERIODS", "SCHEMA", "check", "check_all",
           "check_theme", "schema_for", "shown"]
