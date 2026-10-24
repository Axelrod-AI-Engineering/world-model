"""The stage debugger's dry run (Oct 24): stages 1 to 5 of ingestion on one file, writing nothing, with each stage's input,
output, decision, and timing, so an engineer can see why a document came out as it did (console.md).

It calls the functions `Ingestor.process` calls, in the same order and with the same arguments: `parse`, `analyze`
(dates, language, yen, type: pipeline.py), `chunk`, and the embedder. It makes no decision of its own, and writes nothing to the
store (it only reads: the document, its neighbours' text, `nearest`). A test holds its answers equal to what `process`
stores for the same file, and holds the lake's digest unchanged by a dry run.

The result is plain JSON data: `stages` is the six cards in order (`store`, `parse`, `type`, `chunk`, `index`, `duplicates`),
each `{id, title, status, seconds, decision, data}`, with status `ok`, `failed`, `stopped` (the document would stop here:
the cards after it are `skipped`), or `skipped`.
"""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from axelrod_ingest.chunk import CELL, CHUNK_CHARS, ROW_CHARS, sentences
from axelrod_ingest.chunk import chunk as chunk_of
from axelrod_ingest.cjk import weight
from axelrod_ingest.dedupe import LINKED, DedupeConfig, containment, fingerprint, groups_of
from axelrod_ingest.lake.embed import Embedder
from axelrod_ingest.lake.store import LakeStore, content_id
from axelrod_ingest.ocr import Ocr
from axelrod_ingest.parse import PARSER_VERSION, ParseError, mime_of, parse
from axelrod_ingest.pipeline import analyze, typed_source
from axelrod_ingest.sources import substance
from axelrod_ingest.text import norm, tokens

DETAIL_CHUNKS = 200           # chunks given terms and vectors in full (a long document has thousands)
NEAREST_CHUNKS = 50           # chunks whose nearest stored passages are looked up (each is a search of the lake)
HEAD = 8                      # components of a vector shown
BINS = 10                     # bars of the weight histogram, up to CHUNK_CHARS
TITLES = (("store", "1. Store"), ("parse", "2. Parse"), ("type", "3. Type, date, language, currency"),
          ("chunk", "4. Chunk"), ("index", "5. Index and embed"), ("duplicates", "6. Duplicates"))
FTS = "FTS5 tokenizes with unicode61 (diacritics removed) and then applies the Porter stemmer to each token, at index and query time"


def dry_run(data: bytes, filename: str, *, mime: str = "", published_at: datetime | None = None,
            manifest: dict | None = None, ocr: Ocr | None = None, embedder: Embedder, store: LakeStore | None = None,
            tenant: str | None = None, source_type: str = "other", issuer: str | None = None,
            ingested_at: datetime | None = None, clock: Callable[[], datetime] = lambda: datetime.now(UTC),
            screen: bool = False, ignore_future_dates: bool = False, timer: Callable[[], float] = time.perf_counter,
            vectors: bool = False) -> dict[str, Any]:
    """Run stages 1 to 5 (and the duplicate check, with a `store` and a `tenant`) on `data` without writing anything.
    `published_at` is the date the upload gave, `manifest` the manifest entry, `issuer` the issuer country a hint gave,
    `ingested_at` when the lake received it (now, for a new file). `vectors` adds every chunk's full vector."""
    cards: dict[str, dict[str, Any]] = {}
    ledger = {"t": timer()}

    def card(key: str, status: str, decision: str, body: dict[str, Any]) -> None:
        now = timer()
        cards[key] = {"id": key, "title": dict(TITLES)[key], "status": status, "seconds": now - ledger["t"],
                      "decision": decision, "data": body}
        ledger["t"] = now

    tenant = tenant or ""
    doc_id = content_id(data)
    sha = hashlib.sha256(data).hexdigest()
    known = store.get_document(tenant, doc_id) if store is not None and tenant else None
    now = ingested_at or (known.ingested_at if known is not None else clock())
    card("store", "ok", "already in the lake" if known is not None else "not in the lake: ingesting would store it",
         {"doc_id": doc_id, "sha256": sha, "size": len(data), "mime": mime or mime_of(filename),
          "stored": None if known is None else {"status": known.status, "filename": known.filename,
                                               "ingested_at": known.ingested_at.isoformat(), "error": known.error}})
    out: dict[str, Any] = {"filename": filename, "tenant": tenant, "doc_id": doc_id, "stopped": None, "stages": []}

    def finish() -> dict[str, Any]:
        out["stages"] = [cards.get(k) or {"id": k, "title": t, "status": "skipped", "seconds": 0.0,
                                          "decision": "not reached" + (f": {out['stopped']['reason']}" if out["stopped"] else ""),
                                          "data": {}} for k, t in TITLES]
        return out

    try:
        parsed = parse(data, filename, mime, ocr=ocr)
    except ParseError as err:
        card("parse", "failed", str(err), {"error": str(err)})
        out["stopped"] = {"stage": "parse", "reason": str(err)}
        return finish()
    text = parsed.text
    spans = parsed.spans()
    where = iter(spans)
    segments = []
    for i, seg in enumerate(parsed.segments):
        at, end = next(where)[:2] if seg.text else (None, None)
        segments.append({"index": i, "page": seg.page, "label": seg.label, "chars": len(seg.text), "start": at, "end": end})
    needs_ocr = parsed.meta.get("needs_ocr", [])
    card("parse", "ok", f"{parsed.format}: {len(parsed.segments)} segment(s), {len(text)} characters",
         {"format": parsed.format, "parser": f"{parsed.format}/{PARSER_VERSION}", "title": parsed.title,
          "segments": segments, "needs_ocr": needs_ocr, "ocr": parsed.meta.get("ocr"),
          "encoding": parsed.meta.get("encoding"), "meta": {k: v for k, v in parsed.meta.items() if k != "bundle"},
          "chars": len(text), "text": text})

    a = analyze(parsed, filename, source_type=source_type, manifest=manifest or {}, given=published_at, ingested_at=now,
                issuer=issuer, screen=screen, ignore_future_dates=ignore_future_dates)
    dates, kind = a.dates, a.kind
    stop = None
    if kind.excluded:
        stop = f"excluded from extraction: {kind.reason}"
    elif needs_ocr and not text.strip():
        stop = f"{len(needs_ocr)} page(s) have no text layer and no OCR engine read them: needs_ocr"
    body = {"doc_type": kind.meta(), "substance": substance(text), "source_type": typed_source(source_type, kind),
            "dates": dates.meta(), "published_at": dates.published.isoformat() if dates.published else None,
            "published_source": dates.source or "ingested_at", "period": dates.meta().get("period"),
            "period_source": dates.meta().get("period_source"), "language": a.language, "yen": a.yen.meta(),
            "screened": a.screened}
    card("type", "stopped" if stop else "ok", stop or f"{kind.type} ({kind.basis}): {kind.reason}", body)
    if stop:
        out["stopped"] = {"stage": "type", "reason": stop}
        return finish()

    chunks = chunk_of(parsed, tenant, doc_id)
    cut = _long_sentences(text, spans)
    shown = []
    for c in chunks:
        w = weight(c.text)
        shown.append({"ord": c.ord, "page": c.page, "section": c.section, "start": c.start, "end": c.end, "weight": w,
                      "text": c.text, "sentences": [list(s) for s in sentences(c.text)],
                      "cut": any(c.start < b and a_ < c.end for a_, b in cut)})
    step = CHUNK_CHARS / BINS
    bins = [{"from": round(i * step), "to": round((i + 1) * step), "count": 0} for i in range(BINS)]
    over = 0
    for c in shown:
        if c["weight"] > CHUNK_CHARS:
            over += 1
        else:
            bins[min(BINS - 1, max(0, math.ceil(c["weight"] / step) - 1))]["count"] += 1
    card("chunk", "ok", f"{len(chunks)} chunk(s), {sum(c['cut'] for c in shown)} cut from a long sentence",
         {"chunks": shown, "limit": CHUNK_CHARS, "row_limit": ROW_CHARS,
          "histogram": {"limit": CHUNK_CHARS, "bins": bins, "over": over}})

    vecs = embedder.embed([c.text for c in chunks]) if chunks else []
    terms = []
    for c, v in list(zip(shown, vecs))[:DETAIL_CHUNKS]:
        seen: dict[str, dict[str, Any]] = {}
        for tok, _a, _b in tokens(c["text"]):
            t = seen.setdefault(tok.lower(), {"term": tok.lower(), "norm": norm(tok), "count": 0})
            t["count"] += 1
        terms.append({"ord": c["ord"], "terms": sorted(seen.values(), key=lambda t: (-t["count"], t["term"]))})
    near = []
    if store is not None and tenant:
        for c, v in list(zip(shown, vecs))[:NEAREST_CHUNKS]:
            near.append({"ord": c["ord"], "hits": _nearest(store, tenant, embedder.name, v, doc_id, len(chunks))})
    card("index", "ok", f"{len(chunks)} chunk(s) indexed for keyword search, embedded by {embedder.name}",
         {"keyword": {"note": FTS, "chunks": terms, "detail_chunks": DETAIL_CHUNKS},
          "embedding": {"name": embedder.name, "dim": embedder.dim, "chunks": [
              {"ord": c["ord"], "norm": math.sqrt(sum(x * x for x in v)), "head": v[:HEAD],
               **({"vector": v} if vectors else {})} for c, v in list(zip(shown, vecs))[:DETAIL_CHUNKS]],
              "vectors": vecs if vectors else None},
          "nearest": near if store is not None and tenant else None, "nearest_chunks": NEAREST_CHUNKS})

    card("duplicates", "ok", *_duplicates(text, dates.meta(), a.language, store, tenant, doc_id))
    return finish()


def _long_sentences(text: str, spans: list) -> list[tuple[int, int]]:
    """The sentences too long for a chunk (they are cut), by the rule `chunk` applies: a table row is never cut."""
    out = []
    for start, end, _seg in spans:
        for s in sentences(text[start:end], base=start):
            if CELL not in text[s[0]:s[1]] and weight(text[s[0]:s[1]]) > CHUNK_CHARS:
                out.append(s)
    return out


def _nearest(store: LakeStore, tenant: str, model: str, vector: list[float], own: str, n_own: int) -> list[dict]:
    """The three nearest stored passages from other documents (the document's own chunks, once stored, are skipped)."""
    found = [(s, d, o) for s, d, o in store.nearest(tenant, model, vector, 3 + n_own) if d != own][:3]
    docs: dict[str, Any] = {}
    out = []
    for score, d, o in found:
        if d not in docs:
            doc = store.get_document(tenant, d)
            docs[d] = (doc, {c.ord: c for c in store.get_chunks(tenant, d)})
        doc, chunks = docs[d]
        c = chunks.get(o)
        out.append({"score": score, "doc_id": d, "ord": o, "title": (doc.title or doc.filename) if doc else "",
                    "page": c.page if c else None, "text": c.text if c else ""})
    return out


def _duplicates(text: str, dates: dict, language: str, store: LakeStore | None, tenant: str,
                doc_id: str) -> tuple[str, dict]:
    """The duplicate check `dedupe.link_duplicates` makes, for this document against the tenant's stored ones."""
    period_end = dates.get("period_end", "")
    fp = fingerprint(text, period_end=period_end, language=language, published=dates.get("published_at", ""))
    body: dict[str, Any] = {"period_end": period_end, "figures": len(fp.figures), "distinct": len(fp.distinct),
                            "digest": fp.digest, "compared": None, "group": None}
    if store is None or not tenant:
        return "no lake to compare against", body
    if not period_end:
        return "no period end: a document with no period is never matched", body
    config = DedupeConfig()
    prints, compared, offset = {doc_id: fp}, [], 0
    while page := store.list_documents(tenant, limit=500, offset=offset, order="ingested_at"):
        offset += 500
        for d in page:
            if d.id == doc_id or d.status not in LINKED or d.meta.get("dates", {}).get("period_end", "") != period_end:
                continue
            other = fingerprint((store.get_text(tenant, d.id) or ("", ""))[0], period_end=period_end,
                                language=d.meta.get("language", ""), published=d.meta.get("dates", {}).get("published_at", ""))
            prints[d.id] = other
            share, shared = containment(fp, other)
            compared.append({"doc_id": d.id, "title": d.title or d.filename, "containment": round(share, 4),
                             "shared": shared, "figures": len(other.figures),
                             "matches": shared >= config.min_shared and share >= config.containment})
    body["compared"] = compared
    mine = next((g for g in groups_of(prints, config) if doc_id in g.members), None)
    if mine is None:
        return f"{len(compared)} stored document(s) with this period end; none is the same disclosure", body
    body["group"] = {"id": mine.id, "members": list(mine.members), "primary": mine.primary, "rule": mine.rule,
                     "role": "primary" if mine.primary == doc_id else "duplicate"}
    return f"would join shared_origin {mine.id} as the {body['group']['role']}", body
