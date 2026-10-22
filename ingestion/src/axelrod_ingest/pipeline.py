"""The ingestion pipeline (Oct 17): a file into the lakehouse and out as an import bundle, deterministically.

    ingest_file   store the bytes (once per content hash), parse, chunk, index (keyword and semantic), recognize the
                  model's names, extract signals by rules, ask the cached LLM step about chunks the rules left empty,
                  and build an `axelrod.import/v1` bundle, validated, stored, and returned
    extract       the same from an already stored document, against the model as it is now (the model's names and
                  links change as it learns, so a document can be read again)
    ingest_many   several files; their results come back in event-time order, the order they fold into the model

A document's event time is the date given with it, else (for a file a manifest lists) the date in its file name, else the
first date in its opening text, else a date in its file name, else when it was ingested (dates.py); the period it reports on
(a month, a quarter, a year) is kept beside it, as the item's `occurred_at`. A document is also typed (sources.py: filing,
report, transcript, ...), one that holds no content (an index, a gated page, a script shell) is excluded from extraction with its
reason, a scan with no text layer is read by OCR when there is an engine and marked `needs_ocr` when there is not (ocr.py),
and a bare ¥ is resolved to yen or yuan from the document, with the evidence (units.py). Folding the bundle into the model is
a separate step (the import, reviewed item by item), so storing and processing stay decoupled from learning.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from axelrod_ingest import EXTRACTOR_VERSION
from axelrod_ingest.chunk import chunk
from axelrod_ingest.contract.bundle import FORMAT, ImportBundle
from axelrod_ingest.contract.world_view import WorldView
from axelrod_ingest.dates import Dates
from axelrod_ingest.dates import resolve as resolve_dates
from axelrod_ingest.extract import Reading, Rules, claims_of_chunk, item_of, keep_best
from axelrod_ingest.gazetteer import Gazetteer
from axelrod_ingest.lake.embed import Embedder
from axelrod_ingest.lake.store import BundleRecord, Document, LakeStore, Mention, content_id, digest
from axelrod_ingest.llm import Provider, propose
from axelrod_ingest.ocr import Ocr
from axelrod_ingest.parse import PARSER_VERSION, Parsed, ParseError, mime_of, parse
from axelrod_ingest.sources import SOURCE_OF, Kind, classify
from axelrod_ingest.units import language_of, resolve_yen

KIND_OF = {"data": "data", "filing": "filing", "broker_research": "analyst", "expert_call": "analyst",
           "client_model": "analyst"}
PROFILE_CHARS = 3000          # the opening text that says what a document is about (its subject and region)
SOURCE_TYPES = ("broker_research", "expert_call", "news", "central_bank", "data", "filing", "client_model", "other")
SCREENED = ("html", "pdf")      # the formats whose pages can hold no content (a menu, a shell, a scan): checked unless typed


# what process() derives and writes again each time (a key the caller gave, "manifest" or "hints", is kept)
DERIVED_META = {"format", "pages", "slides", "sheets", "encoding", "needs_ocr", "ocr", "language", "dates", "currency",
                "doc_type", "shared_origin"}


def bundle_id(bundle: dict) -> str:
    """A bundle's id: the hash of its content, without `collected_at` (when it was read, a clock), so the same file
    read by any service, for any login, at any time gives the same bundle id."""
    return digest({k: v for k, v in bundle.items() if k != "collected_at"})[:24]


@dataclass
class IngestResult:
    document: Document
    new: bool                                   # False when the same bytes were ingested before
    bundle: BundleRecord | None
    chunks: int = 0
    mentions: int = 0
    signals: int = 0
    llm_signals: int = 0
    warnings: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)   # seconds per stage (benchmarks); never in the bundle


class Stopwatch:
    """Seconds per stage: `lap(name)` adds the time since the last lap to `name`."""

    def __init__(self, timer: Callable[[], float] = time.perf_counter) -> None:
        self.timer = timer
        self.laps: dict[str, float] = {}
        self.t = timer()

    def lap(self, name: str) -> None:
        now = self.timer()
        self.laps[name] = self.laps.get(name, 0.0) + (now - self.t)
        self.t = now


GUIDANCE = re.compile(r"guidance|outlook|forecast|budget", re.I)     # a file named for what it plans, not what happened


def _partial(dates: Dates) -> bool:
    """Whether the document reports a month, a quarter, or a half (so a headline figure is the part's, not the year's)."""
    return dates.period is not None and dates.period.kind in ("month", "quarter", "half") and not dates.forward


def _period_end(dates: Dates) -> datetime | None:
    """The end of the period a document reports on, when it ended before the document was published."""
    p = dates.period
    return None if p is None or dates.forward else datetime(p.end.year, p.end.month, p.end.day, tzinfo=UTC)


def _utc(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=UTC)


class Ingestor:
    def __init__(self, store: LakeStore, embedder: Embedder, *, provider: Provider | None = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 inverted: frozenset[str] = frozenset(), ocr: Ocr | None = None, screen: bool = False,
                 timer: Callable[[], float] = time.perf_counter) -> None:
        self.ocr = ocr                          # reads the pages of a scanned PDF (ocr.ocr_from_env); None: they are needs_ocr
        self.screen = screen                    # exclude an untyped web page or PDF that holds no content (sources.classify);
        # off by default: an upload of a short note is a document, a pack's index page is not
        self.store = store
        self.timer = timer
        self.embedder = embedder
        self.provider = provider
        self.clock = clock
        self.inverted = inverted

    # -- storing ------------------------------------------------------------------------------------------------
    def store_file(self, tenant: str, data: bytes, filename: str, *, mime: str = "", source: str = "",
                   source_type: str = "other", published_at: datetime | None = None,
                   uploaded_by: str = "", meta: dict[str, Any] | None = None) -> tuple[Document, bool]:
        if source_type not in SOURCE_TYPES:
            raise ValueError(f"source_type must be one of {', '.join(SOURCE_TYPES)}")
        now = _utc(self.clock())
        pub = _utc(published_at) if published_at else None
        doc = Document(tenant=tenant, id=content_id(data), sha256=hashlib.sha256(data).hexdigest(),
                       filename=filename, mime=mime or mime_of(filename), size=len(data), source=source,
                       source_type=source_type, published_at=pub, event_time=pub or now, ingested_at=now,
                       uploaded_by=uploaded_by, meta=dict(meta or {}))
        return self.store.put_document(doc, data)

    # -- processing ---------------------------------------------------------------------------------------------
    def process(self, tenant: str, doc_id: str, graph: WorldView) -> IngestResult:
        """Parse, index, and extract a stored document against `graph`."""
        doc = self.store.get_document(tenant, doc_id)
        if doc is None:
            raise KeyError(doc_id)
        sw = Stopwatch(self.timer)
        data = self.store.raw_bytes(tenant, doc_id)
        try:
            parsed = parse(data or b"", doc.filename, doc.mime, ocr=self.ocr)
        except ParseError as err:
            doc = self.store.update_document(tenant, doc_id, status="failed", error=str(err))
            sw.lap("parse")
            return IngestResult(doc, False, None, warnings=[str(err)], timings=sw.laps)
        sw.lap("parse")
        manifest = doc.meta.get("manifest") or {}
        # a date the upload gave stays the upload's on a second reading; one this pipeline derived is derived again
        given = doc.published_at if doc.meta.get("dates", {}).get("published_source", "upload") == "upload" else None
        dates = resolve_dates(parsed.text, doc.filename, upload=given, manifest=bool(manifest), not_after=doc.ingested_at)
        language = language_of(parsed.text)
        yen = resolve_yen(parsed.text, language=language, issuer=(doc.meta.get("hints") or {}).get("issuer_country"))
        needs_ocr = parsed.meta.get("needs_ocr", [])
        screened = self.screen and parsed.format in SCREENED and doc.source_type == "other"
        kind = classify(doc.filename, parsed.text, url=manifest.get("url", ""), section=manifest.get("section", ""),
                        judge=screened and not needs_ocr, fmt=parsed.format)
        if kind.type == "news":                  # a story is about when it ran: any month or quarter it mentions is no period
            dates = Dates(dates.published, dates.source)
        meta = {k: v for k, v in doc.meta.items() if k not in DERIVED_META}
        meta.update({"format": parsed.format, **{k: v for k, v in parsed.meta.items() if k != "bundle"},
                     "language": language, "dates": dates.meta(), "currency": {"yen": yen.meta()}, "doc_type": kind.meta()})
        if manifest.get("sha256"):
            meta["manifest"] = {**manifest, "sha256_matches": manifest["sha256"] == doc.sha256}
        source_type = doc.source_type if doc.source_type != "other" else SOURCE_OF[kind.type]
        published = dates.published
        fields = {"title": doc.title or parsed.title or doc.filename, "published_at": published, "source_type": source_type,
                  "event_time": published or doc.ingested_at, "meta": meta}
        self.store.put_text(tenant, doc_id, parsed.text, f"{parsed.format}/{PARSER_VERSION}")
        if kind.excluded:
            self.store.put_chunks(tenant, doc_id, [])
            self.store.put_embeddings(tenant, doc_id, self.embedder.name, [])
            doc = self.store.update_document(tenant, doc_id, **{**fields, "source_type": "other"}, status="excluded",
                                             error=kind.reason)
            return IngestResult(doc, False, None, warnings=[f"excluded from extraction: {kind.reason}"], timings=sw.laps)
        if needs_ocr and not parsed.text.strip():
            why = f"{len(needs_ocr)} page(s) have no text layer and no OCR engine read them: needs_ocr"
            self.store.put_chunks(tenant, doc_id, [])
            self.store.put_embeddings(tenant, doc_id, self.embedder.name, [])
            doc = self.store.update_document(tenant, doc_id, **fields, status="needs_ocr", error=why)
            return IngestResult(doc, False, None, warnings=[why], timings=sw.laps)
        chunks = chunk(parsed, tenant, doc_id)
        sw.lap("chunk")
        self.store.put_chunks(tenant, doc_id, chunks)
        sw.lap("index")
        self.store.put_embeddings(tenant, doc_id, self.embedder.name, self.embedder.embed([c.text for c in chunks]))
        sw.lap("embed")
        doc = self.store.update_document(tenant, doc_id, **fields, status="parsed", error="")
        warnings = ([f"page(s) {needs_ocr} have no text layer and no OCR engine read them: needs_ocr"] if needs_ocr else []) + (
            [] if parsed.text.strip() or parsed.format == "bundle" else ["no text could be read from the document"])
        res = (self._passthrough(doc, parsed, graph, len(chunks)) if parsed.format == "bundle"
               else self._extract(doc, chunks, graph, sw, dates=dates, kind=kind, language=language, yen=yen.currency))
        res.warnings = warnings + res.warnings
        sw.lap("bundle")
        res.timings = sw.laps
        return res

    def _passthrough(self, doc: Document, parsed: Parsed, graph: WorldView, n_chunks: int) -> IngestResult:
        """An import bundle uploaded as a file: validated and stored as it is (its signals were written for the model)."""
        try:
            bundle = ImportBundle.model_validate(parsed.meta["bundle"]).model_dump(mode="json")
        except ValidationError as err:
            # a file that claims to be a bundle and is not one fails like any unreadable file
            why = f"not a valid {FORMAT} bundle: {err.error_count()} problem(s), first: {err.errors()[0]['msg']}"
            doc = self.store.update_document(doc.tenant, doc.id, status="failed", error=why)
            return IngestResult(doc, False, None, chunks=n_chunks, warnings=[why])
        rec = self._record(doc, bundle)
        doc = self.store.update_document(doc.tenant, doc.id, status="extracted")
        return IngestResult(doc, False, rec, chunks=n_chunks, signals=rec.signals)

    def _extract(self, doc: Document, chunks: list, graph: WorldView, sw: Stopwatch, *, dates: Dates, kind: Kind,
                 language: str, yen: str) -> IngestResult:
        gz = Gazetteer(graph)
        rules = Rules(graph, gz, self.inverted, yen=yen)
        tags = [f"doc_type:{kind.type}", f"lang:{language}", *([f"period:{dates.period.label}"] if dates.period else [])]
        items, mentions, warnings = [], [], []
        head = " ".join(c.text for c in chunks)[:PROFILE_CHARS]
        subject, region = gz.profile(f"{doc.title} {doc.filename}", head)
        reading = Reading(subject=subject, region=region, date=doc.event_time, ref=_period_end(dates),
                          forward=bool(GUIDANCE.search(doc.filename)), partial=_partial(dates))
        n_llm = 0
        prefix = f"D{doc.id[:10]}"
        read = []
        for c in chunks:
            claims, reading = claims_of_chunk(rules, c.ord, c.text, reading, page=c.page)
            mentions += [Mention(tenant=doc.tenant, doc_id=doc.id, ord=c.ord, entity_id=m.entity_id,
                                 subentity_id=m.subentity_id, surface=m.surface) for m in claims.mentions]
            read.append((c, claims, bool(claims.found)))
        keep_best([claims for _c, claims, _had in read])          # one claim per value in the document
        for c, claims, had in read:
            if not had and claims.entities and self.provider is not None:
                sw.lap("extract")
                sigs = propose(c.text, graph, claims.entities, provider=self.provider, store=self.store,
                               gazetteer_digest=gz.digest)
                sw.lap("llm")
                n_llm += len(sigs)
            else:
                sigs = []
            item = item_of(graph, claims, doc_prefix=prefix, published_at=doc.event_time, source=doc.source,
                           source_type=doc.source_type, kind=KIND_OF.get(doc.source_type, "news"), title=doc.title,
                           extra=sigs)
            if item is not None:
                item["tags"] = [*item["tags"], *tags]
                if dates.period is not None and not dates.forward:   # the period the figures are about, beside when they were published
                    item["occurred_at"] = datetime(*dates.period.end.timetuple()[:3], tzinfo=UTC).isoformat()
                items.append(item)
        sw.lap("extract")
        self.store.put_mentions(doc.tenant, doc.id, mentions)
        if not items:
            warnings.append("no claims about the model's values were found")
        n_signals = sum(len(i["signals"]) for i in items)
        bundle = {"format": FORMAT, "title": doc.title, "collected_by": f"axelrod ingest {EXTRACTOR_VERSION}",
                  "collected_at": doc.ingested_at.isoformat(), "synthetic": False, "items": items,
                  "description": f"Extracted from {doc.filename} ({doc.id}) against the world model's names "
                                 f"(gazetteer {gz.digest}): {n_signals} signal(s) in {len(items)} item(s)."}
        bundle = ImportBundle.model_validate(bundle).model_dump(mode="json")
        rec = self._record(doc, bundle)
        doc = self.store.update_document(doc.tenant, doc.id, status="extracted")
        return IngestResult(doc, False, rec, chunks=len(chunks), mentions=len(mentions), signals=n_signals,
                            llm_signals=n_llm, warnings=warnings)

    def _record(self, doc: Document, bundle: dict) -> BundleRecord:
        rec = BundleRecord(tenant=doc.tenant, id=bundle_id(bundle), doc_ids=[doc.id], created_at=doc.ingested_at,
                           extractor_version=EXTRACTOR_VERSION, items=len(bundle["items"]),
                           signals=sum(len(i["signals"]) for i in bundle["items"]), bundle=bundle)
        return self.store.put_bundle(rec)

    # -- the whole path -----------------------------------------------------------------------------------------
    def ingest_file(self, tenant: str, data: bytes, filename: str, graph: WorldView, **meta: Any) -> IngestResult:
        t0 = self.timer()
        doc, new = self.store_file(tenant, data, filename, **meta)
        stored = self.timer() - t0
        res = self.process(tenant, doc.id, graph)
        res.new = new
        res.timings = {"store": stored, **res.timings}
        return res

    def ingest_many(self, tenant: str, files: list[tuple[bytes, str]], graph: WorldView, **meta: Any) -> list[IngestResult]:
        """Several files, each stored and processed; the results in event-time order (then by document id)."""
        out = [self.ingest_file(tenant, data, name, graph, **meta) for data, name in files]
        return sorted(out, key=lambda r: (r.document.event_time, r.document.id))
