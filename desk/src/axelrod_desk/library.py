"""The shared library (Nov 2): every document anyone adds, stored once, with what is known about it, and its copies linked.

Adding a file:

1. **Once by content.** Its SHA-256 is its id. The same bytes added again, by anyone, are recorded as an upload of the
   document already there and change nothing else.
2. **Pages.** Its text page by page (pages.py), kept under `text/<sha256>/`.
3. **Ingestion.** The ingestion pipeline stores it in the desk's lake (one tenant), types it, dates it and reads its
   language and period, against the base model's world view. Its own signals are not used: the reader reads the figures.
4. **What it is.** Its title (the manifest's Title or Document column, else the file name: a PDF's own title is often an
   aggregator's or an editor's, the same on every note), its company, source class (`company`: the company's own
   disclosures; `sell_side`: broker research; `other`), publisher and publication date come from what the person adding it said, else a folder's `MANIFEST.md`, else
   ingestion (a broker note's file name gives its publisher; the type says research or filing), else the text (the company
   it names most). A document without a company waits ("needs company") until someone sets one.
5. **Copies.** After each batch, ingestion's duplicate linking groups copies of one disclosure (a translation, a summary,
   the same report on another exchange: the same period and most of the same figures) and names one primary, an English
   copy first (PRIMARY). Only the primary is read; the others stay in the library as its copies ("duplicate").

A folder's manifests (`MANIFEST.md`, or any `*MANIFEST.md` a pack carries) label its files and are not documents.
"""

from __future__ import annotations

import hashlib
import mimetypes
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from axelrod_desk import pages as pg
from axelrod_desk.catalog import Catalog
from axelrod_desk.db import Db, now
from axelrod_ingest.contract.world_view import WorldView
from axelrod_ingest.dedupe import DedupeConfig, link_duplicates
from axelrod_ingest.lake.embed import HashingEmbedder
from axelrod_ingest.lake.sqlite import SQLiteLake
from axelrod_ingest.lake.store import LakeStore
from axelrod_ingest.pack import find_manifest, pack_files
from axelrod_ingest.parse import supported
from axelrod_ingest.pipeline import Ingestor
from axelrod_ingest.sources import ManifestEntry, publisher_in_name

CLASSES = ("company", "sell_side", "other")
# the copy to read: English first (an A-share company's English report states no IFRS, so ingestion's default rule would pick
# its Chinese filing), then the copy with the most figures
PRIMARY = DedupeConfig(primary=("english_ifrs", "english", "completeness"))
SELL_SIDE = re.compile(r"sell[- ]side|broker|research", re.I)
OPEN = ("new", "needs company")             # statuses a document can still be read from


@dataclass
class Added:
    sha256: str
    filename: str
    outcome: str                            # new, already stored, failed
    status: str = ""
    error: str = ""


class Library:
    def __init__(self, db: Db, catalog: Catalog, *, files: Path, text: Path, lake: LakeStore | Path,
                 world_view: WorldView, tenant: str = "desk", poppler: bool | None = None) -> None:
        self.db, self.catalog, self.files, self.text = db, catalog, files, text
        self.lake = SQLiteLake(lake) if isinstance(lake, Path) else lake
        self.ingestor = Ingestor(self.lake, HashingEmbedder())
        self.graph, self.tenant, self.poppler = world_view, tenant, poppler

    # -- adding ---------------------------------------------------------------------------------------------------------
    def add(self, data: bytes, filename: str, *, account: dict[str, Any] | None = None, company: str | None = None,
            source_class: str | None = None, publisher: str | None = None, published: str | None = None,
            entry: ManifestEntry | None = None) -> Added:
        """Add one file (see the module docstring). Call `link` after a batch."""
        sha = hashlib.sha256(data).hexdigest()
        aid = account["id"] if account else None
        old = self.get(sha)
        if old:
            self._upload(sha, aid, filename, "already stored")
            return Added(sha, filename, "already stored", old["status"])
        if company and company not in self.catalog.companies:
            raise ValueError(f"{company} is not a covered company")
        if source_class and source_class not in CLASSES:
            raise ValueError(f"a source class is one of {CLASSES}")
        try:
            texts, engine = pg.page_texts(data, filename, poppler=self.poppler)
        except Exception as err:            # an unreadable file is reported, not stored
            self._upload(sha, aid, filename, "failed")
            return Added(sha, filename, "failed", error=str(err))
        ext = Path(filename).suffix.lower()
        path = self.path_of(sha, ext)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        pg.write(self.text / sha, texts)
        meta: dict[str, Any] = {}
        if entry is not None:
            meta["manifest"] = {"file": entry.file, "url": entry.url, "section": entry.section, "rank": entry.rank,
                                "sha256": entry.sha256, "publisher": entry.publisher}
        res = self.ingestor.ingest_file(self.tenant, data, filename, self.graph, source=urlsplit(entry.url).netloc if entry else "",
                                        uploaded_by=(account or {}).get("email", ""), meta=meta)
        m = res.document.meta
        doc_type = (m.get("doc_type") or {}).get("type", "")
        dates = m.get("dates") or {}
        publisher = publisher or (entry.publisher if entry else "") or publisher_in_name(filename) or m.get("publisher", "")
        company = company or self.catalog.detect(filename, publisher, *texts[:2])
        source_class = source_class or self._class(entry, res.document.source_type, publisher, company)
        published = published or _cell_date(entry) or (dates.get("published_at") or "")[:10] or None
        self.db.insert("documents", {
            "sha256": sha, "filename": filename, "ext": ext, "size": len(data), "pages": len(texts), "text_engine": engine,
            "title": _cell(entry, r"title|document") or Path(filename).stem, "company": company, "source_class": source_class,
            "publisher": publisher or None, "published": published, "url": entry.url if entry else None,
            "section": entry.section if entry else None, "language": m.get("language") or None, "doc_type": doc_type or None,
            "period": dates.get("period") or None, "status": "new" if company else "needs company", "added_by": aid,
            "added_at": now()})
        self._upload(sha, aid, filename, "new")
        return Added(sha, filename, "new", "new" if company else "needs company")

    def add_folder(self, root: Path, **kw: Any) -> list[Added]:
        """Every supported file under a folder, each with its row of the folder's MANIFEST.md, then the copies linked."""
        manifest = find_manifest(root)
        out = [self.add(p.read_bytes(), p.name, entry=manifest.entry_for(p.name), **kw)
               for p in pack_files(root) if wanted(p.name)]
        self.link()
        return out

    def _class(self, entry: ManifestEntry | None, source_type: str, publisher: str, company: str | None) -> str:
        if (entry and SELL_SIDE.search(entry.section)) or source_type == "broker_research":
            return "sell_side"
        names = [n.lower() for n in self._names(company)]
        if source_type == "filing" or (publisher and any(n in publisher.lower() for n in names)):
            return "company"
        return "other"

    def _names(self, company: str | None) -> list[str]:
        e = self.catalog.companies.get(company or "", {})
        return [n for n in [e.get("name", ""), *e.get("aliases", [])] if len(n) >= 3]

    def _upload(self, sha: str, aid: int | None, filename: str, outcome: str) -> None:
        self.db.insert("uploads", {"sha256": sha, "account_id": aid, "filename": filename, "at": now(), "outcome": outcome})

    # -- copies ---------------------------------------------------------------------------------------------------------
    def link(self) -> int:
        """Link copies of one disclosure (ingestion's dedupe over the lake); a copy not yet read is not read. The groups."""
        groups = link_duplicates(self.lake, self.tenant, PRIMARY)
        by_id = {content_id_of(d["sha256"]): d for d in self.db.all("select sha256, status from documents")}
        for d in by_id.values():                     # a copy no longer in a group (or now its primary) is read again
            d["status"] = "new" if d["status"] == "duplicate" else d["status"]
            self.db.update("documents", "sha256", d["sha256"], {"origin_group": None, "origin_role": None,
                                                                "origin_primary": None, "status": d["status"]})
        for g in groups:
            primary = by_id.get(g.primary)
            for member in g.members:
                d = by_id.get(member)
                if d is None or primary is None:
                    continue
                fields = {"origin_group": g.id, "origin_role": "primary" if member == g.primary else "duplicate",
                          "origin_primary": primary["sha256"]}
                if member != g.primary and d["status"] in OPEN:
                    fields["status"] = "duplicate"
                self.db.update("documents", "sha256", d["sha256"], fields)
        return len(groups)

    # -- reading it back ------------------------------------------------------------------------------------------------
    def path_of(self, sha: str, ext: str) -> Path:
        return self.files / sha[:2] / f"{sha}{ext}"

    def get(self, sha: str) -> dict[str, Any] | None:
        return self.db.one("select * from documents where sha256 = ?", [sha])

    def pages(self, sha: str) -> list[str]:
        d = self.get(sha)
        if d is None:
            raise KeyError(sha)
        return pg.read(self.text / sha, d["pages"])

    def list(self, *, company: str = "", source_class: str = "", status: str = "") -> list[dict[str, Any]]:
        where, args = [], []
        for col, v in (("company", company), ("source_class", source_class), ("status", status)):
            if v:
                where.append(f"{col} = ?")
                args.append(v)
        sql = "select * from documents" + (" where " + " and ".join(where) if where else "")
        return self.db.all(sql + " order by coalesce(published, added_at) desc, filename", args)

    def edit(self, sha: str, **fields: Any) -> dict[str, Any]:
        """Correct what is known about a document (company, source class, publisher, publication date)."""
        d = self.get(sha)
        if d is None:
            raise KeyError(sha)
        allowed = {"company", "source_class", "publisher", "published", "note"}
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"cannot change {', '.join(sorted(bad))}")
        if fields.get("company") and fields["company"] not in self.catalog.companies:
            raise ValueError(f"{fields['company']} is not a covered company")
        if fields.get("source_class") and fields["source_class"] not in CLASSES:
            raise ValueError(f"a source class is one of {CLASSES}")
        if fields.get("published"):
            date.fromisoformat(fields["published"])
        if fields.get("company") and d["status"] == "needs company":
            fields["status"] = "new"
        self.db.update("documents", "sha256", sha, fields)
        return self.get(sha)

    def mime_of(self, d: dict[str, Any]) -> str:
        return mimetypes.guess_type(d["filename"])[0] or "application/octet-stream"


def wanted(filename: str) -> bool:
    """Whether a file of a folder or an upload is a document: readable, and not a manifest (MANIFEST.md, or a pack's own
    SOURCE_MANIFEST.md) or a hidden file."""
    return supported(filename) and not filename.startswith(".") and not filename.upper().endswith("MANIFEST.MD")


def content_id_of(sha: str) -> str:
    """The lake's id for a document with this SHA-256."""
    return sha[:24]


def _cell(entry: ManifestEntry | None, heading: str) -> str | None:
    """The manifest row's cell under a column whose heading matches (case ignored)."""
    return next((cell for head, cell in (entry.cells if entry else ()) if re.search(heading, head, re.I) and cell), None)


def _cell_date(entry: ManifestEntry | None) -> str | None:
    """A publication date from the manifest row's cells (a column headed Published or Date)."""
    found = (re.search(r"\d{4}-\d{2}-\d{2}", cell) for head, cell in (entry.cells if entry else ())
             if re.search(r"publish|date", head, re.I))
    return next((m[0] for m in found if m), None)


__all__ = ["CLASSES", "PRIMARY", "Added", "Library", "content_id_of", "wanted"]
