"""Packs (Oct 22): a folder of documents with a manifest, ingested into a lake, and what happened to every file.

A pack is a folder (nested folders allowed) holding a `MANIFEST.md` (sources.py reads it) and the files it lists. `ingest_pack`
reads them in a fixed order (by path), hands each to the `Ingestor` with what the manifest says of it (its source URL, its
section, its place in the table, the hash it states), then links the copies of one disclosure (dedupe.py). The result is a
`PackReport`: a row per file (status, type, language, pages, chunks, signals, warnings, how it was dated, how ¥ was read),
the groups of duplicates, and the counts, all plain data. Nothing in a pack is trusted: its files are read as data, the
manifest only labels them, and a file that cannot be read is a row with its error, never a stop.

`lake_digest` is the determinism check: a hash of everything a lake holds for a tenant (documents with their metadata, texts,
chunks, mentions, embeddings, bundles), so two runs over the same pack give equal digests exactly when their contents are
byte for byte the same.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from axelrod_ingest.contract.world_view import WorldView
from axelrod_ingest.dedupe import DedupeConfig, Group, link_duplicates
from axelrod_ingest.lake.embed import embedder_from_env
from axelrod_ingest.lake.sqlite import SQLiteLake
from axelrod_ingest.lake.store import LakeStore, canonical_json
from axelrod_ingest.llm import provider_from_env
from axelrod_ingest.ocr import ocr_from_env
from axelrod_ingest.parse import supported
from axelrod_ingest.pipeline import Ingestor
from axelrod_ingest.sources import Manifest, read_manifest

MANIFEST = "MANIFEST.md"


@dataclass
class FileRow:
    path: str                                  # relative to the pack
    doc_id: str = ""
    status: str = ""                           # extracted | excluded | needs_ocr | failed | skipped
    error: str = ""
    doc_type: str = ""
    type_reason: str = ""
    language: str = ""
    format: str = ""
    pages: int = 0
    chunks: int = 0
    mentions: int = 0
    signals: int = 0
    bundle_id: str = ""
    published_at: str = ""
    published_source: str = ""
    period: str = ""
    yen: str = ""
    yen_basis: str = ""
    yen_signs: int = 0                         # how many bare ¥ signs the document has
    in_manifest: bool = False
    sha256_matches: bool | None = None
    needs_ocr: list[int] = field(default_factory=list)
    ocr_pages: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class PackReport:
    root: str
    manifest_title: str = ""
    rows: list[FileRow] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)          # listed in the manifest, not on disk
    stats: dict[str, int] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        rows = self.rows
        ok = [r for r in rows if r.status == "extracted"]
        return {
            "files": len(rows), "documents": len({r.doc_id for r in rows if r.doc_id}), "chunks": sum(r.chunks for r in rows),
            "signals": sum(r.signals for r in rows), "mentions": sum(r.mentions for r in rows),
            "extracted": len(ok), "excluded": sum(r.status == "excluded" for r in rows),
            "needs_ocr": sum(r.status == "needs_ocr" or bool(r.needs_ocr) for r in rows),
            "failed": sum(r.status == "failed" for r in rows), "skipped": sum(r.status == "skipped" for r in rows),
            "ocr_pages": sum(r.ocr_pages for r in rows),
            "types": dict(sorted(Counter(r.doc_type for r in rows if r.doc_type).items())),
            "languages": dict(sorted(Counter(r.language for r in rows if r.language).items())),
            "yen": dict(sorted(Counter(f"{r.yen}/{r.yen_basis}" for r in rows if r.yen_signs).items())),
            "duplicate_groups": len(self.groups), "duplicate_copies": sum(len(g.members) - 1 for g in self.groups),
            "hash_mismatches": sum(r.sha256_matches is False for r in rows), "not_in_manifest": sum(
                not r.in_manifest for r in rows if r.status != "skipped"), "manifest_missing": len(self.missing)}


def pack_files(root: Path) -> list[Path]:
    """Every file under the pack, in the order of their relative paths, the manifest and hidden files left out."""
    return sorted((p for p in root.rglob("*") if p.is_file() and p.name != MANIFEST and not p.name.startswith(".")),
                  key=lambda p: p.relative_to(root).as_posix())


def find_manifest(root: Path) -> Manifest:
    """The pack's manifest (the first MANIFEST.md at or under the root, by path), or an empty one."""
    found = sorted(root.rglob(MANIFEST), key=lambda p: p.relative_to(root).as_posix())
    return read_manifest(found[0].read_text(encoding="utf-8", errors="replace")) if found else Manifest()


def ingest_pack(root: Path, ingestor: Ingestor, graph: WorldView, *, tenant: str = "default",
                dedupe: DedupeConfig = DedupeConfig()) -> PackReport:
    """Ingest every file of the pack, link the duplicates, and report."""
    manifest = find_manifest(root)
    report = PackReport(root.name, manifest.title)
    seen = set()
    for path in pack_files(root):
        rel = path.relative_to(root).as_posix()
        entry = manifest.entry_for(path.name)
        row = FileRow(rel, in_manifest=entry is not None)
        report.rows.append(row)
        seen.add(path.name)
        if not supported(path.name):
            row.status, row.error = "skipped", "unsupported file type"
            continue
        meta: dict[str, Any] = {}
        source = ""
        if entry is not None:
            meta["manifest"] = {"file": entry.file, "url": entry.url, "section": entry.section, "rank": entry.rank,
                                "sha256": entry.sha256, "publisher": entry.publisher}
            source = urlsplit(entry.url).netloc
        res = ingestor.ingest_file(tenant, path.read_bytes(), path.name, graph, source=source, meta=meta)
        doc = res.document
        m = doc.meta
        dates, yen = m.get("dates", {}), m.get("currency", {}).get("yen", {})
        row.doc_id, row.status, row.error = doc.id, doc.status, doc.error
        row.doc_type, row.type_reason = m.get("doc_type", {}).get("type", ""), m.get("doc_type", {}).get("reason", "")
        row.language, row.format = m.get("language", ""), m.get("format", "")
        row.pages = m.get("pages", 0) or m.get("slides", 0)
        row.chunks, row.mentions, row.signals = res.chunks, res.mentions, res.signals
        row.bundle_id = res.bundle.id if res.bundle else ""
        row.published_at, row.published_source = dates.get("published_at", ""), dates.get("published_source", "")
        row.period = dates.get("period", "")
        row.yen, row.yen_basis, row.yen_signs = yen.get("code", ""), yen.get("basis", ""), yen.get("signs", 0)
        row.sha256_matches = m.get("manifest", {}).get("sha256_matches")
        row.needs_ocr, row.ocr_pages = m.get("needs_ocr", []), len(m.get("ocr", {}).get("pages", []))
        row.warnings = res.warnings
    report.missing = sorted(e.file for e in manifest.entries if e.file not in seen)
    report.groups = link_duplicates(ingestor.store, tenant, dedupe)
    report.stats = ingestor.store.stats(tenant)
    return report


def lake_digest(store: LakeStore, tenant: str = "default", *, embedder: str = "hashing") -> dict[str, str]:
    """A digest per kind of record a lake holds for a tenant, and one over all of them: equal exactly when the lakes'
    contents are equal."""
    docs, offset = [], 0
    while page := store.list_documents(tenant, limit=500, offset=offset, order="ingested_at"):
        docs += page
        offset += 500
    docs.sort(key=lambda d: d.id)
    parts: dict[str, Any] = {
        "documents": [d.model_dump(mode="json") for d in docs],
        "texts": [[d.id, store.get_text(tenant, d.id)] for d in docs],
        "chunks": [[c.model_dump(mode="json") for c in store.get_chunks(tenant, d.id)] for d in docs],
        "mentions": [m.model_dump(mode="json") for m in store.mentions_of(tenant)],
        "embeddings": store.embeddings(tenant, embedder),
        "bundles": [b.model_dump(mode="json") for b in store.list_bundles(tenant, limit=10**9)],
    }
    out = {k: hashlib.sha256(canonical_json(v).encode()).hexdigest() for k, v in parts.items()}
    out["all"] = hashlib.sha256(canonical_json(out).encode()).hexdigest()
    return out


def world_from_file(path: Path) -> tuple[WorldView, frozenset[str]]:
    """The world view and the inverted patterns a file holds (world_model/scripts/export_world_view.py writes it)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return WorldView.from_json(json.dumps(data["world_view"])), frozenset(data.get("inverted", []))


def run(pack: Path, world: Path, lake_dir: Path, *, tenant: str, clock: datetime, embedder: str = "hashing",
        env: dict[str, str] | None = None) -> tuple[PackReport, dict[str, str]]:
    """Ingest a pack into a lake folder of its own (created if needed) as of a fixed clock: the report and the lake's digest.
    OCR runs when an engine is found (and AXELROD_OCR is not "off"), its cache inside the lake folder; the LLM step runs only
    when WORLD_MODEL_LLM_PROVIDER is already set in the environment (temperature 0, cached in the lake)."""
    env = {**os.environ, **(env or {}), "WORLD_MODEL_LAKE_DIR": str(lake_dir), "WORLD_MODEL_EMBEDDER": embedder}
    graph, inverted = world_from_file(world)
    store = SQLiteLake(lake_dir)
    try:
        ing = Ingestor(store, embedder_from_env(env), provider=provider_from_env(env), clock=lambda: clock, inverted=inverted,
                       ocr=ocr_from_env(env), screen=True, ignore_future_dates=True)
        report = ingest_pack(pack, ing, graph, tenant=tenant)
        return report, lake_digest(store, tenant, embedder=ing.embedder.name)
    finally:
        store.close()


def main(argv: list[str] | None = None) -> int:
    """`ingest_pack PACK --world-view FILE --lake-dir DIR [--twice DIR2] [--report FILE]`: ingest a pack, print its
    summary, optionally write the full report, and with --twice run it again into a second lake and compare the two."""
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("pack", type=Path)
    ap.add_argument("--world-view", type=Path, required=True)
    ap.add_argument("--lake-dir", type=Path, required=True)
    ap.add_argument("--tenant", default="")
    ap.add_argument("--clock", default="2026-10-22T00:00:00+00:00", help="the lake's clock: fixed, so a rerun is identical")
    ap.add_argument("--embedder", default="hashing", choices=["hashing", "fastembed"])
    ap.add_argument("--report", type=Path)
    ap.add_argument("--twice", type=Path, help="run again into this lake folder and compare")
    a = ap.parse_args(argv)
    clock = datetime.fromisoformat(a.clock).astimezone(UTC)
    tenant = a.tenant or a.pack.name
    report, digest = run(a.pack, a.world_view, a.lake_dir, tenant=tenant, clock=clock, embedder=a.embedder)
    out: dict[str, Any] = {"summary": report.summary(), "digest": digest}
    if a.twice:
        again, digest2 = run(a.pack, a.world_view, a.twice, tenant=tenant, clock=clock, embedder=a.embedder)
        same_bundles = [r.bundle_id for r in report.rows] == [r.bundle_id for r in again.rows]
        out["determinism"] = {"identical": digest == digest2 and same_bundles, "bundle_ids_equal": same_bundles,
                              "differing": sorted(k for k in digest if digest[k] != digest2[k])}
    if a.report:
        a.report.write_text(json.dumps({**out, "report": asdict(report)}, indent=1, sort_keys=True, ensure_ascii=False,
                                       default=str) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0 if out.get("determinism", {"identical": True})["identical"] else 1
