"""Sources (Oct 22): what kind of document a file is, and the manifest that says where a pack's files came from.

**The manifest.** A pack arrives with a `MANIFEST.md`: Markdown with a title, an "Updated" line, bullet lists under `##`
headings, and tables whose rows list each saved file with its source URL and SHA-256. `read_manifest` reads that structure
and nothing else: a table whose first column is "file" (and whose rows name files with an extension) lists entries; a heading
over it is the entry's `section`, its position in the table its `rank` (the order the pack lists them in); every other heading's
bullets are kept as `notes`. The text is data. Nothing in it is run, followed, or obeyed, and nothing in it changes a document's
content: it only labels files (a URL, a section, a hash to compare) and is stored beside them.

**Source typing.** `classify` gives each file one of: `filing`, `report` (an annual, interim, or quarterly report, or financial
statements), `transcript` (a call, or a record of management Q&A), `presentation`, `news`, `data_aggregate` (a third party's series),
`index_page`, or `other`. The evidence, strongest first:

1. A file named an index (INDEX_ONLY, "index of ...", "transcript index"): an index page, excluded. One named a notice only
   (NOTICE_ONLY) is `other` and still read.
2. The page itself: a page with no prose (only a menu, a script shell, a list of links) or one that says it is gated (enable
   JavaScript, subscribe to read, access denied) has no content. It is typed `other` (or `index_page` when it is a list of
   links), with the reason, and **excluded from extraction**. A scan that still needs OCR is not judged by its empty text, nor is an upload nobody asked to screen.
   A web page is judged by its prose (twelve ideographs or eight words a line), a PDF by its letters and digits.
3. A report named in the file name (annual, interim, quarterly report; financial statements), then the URL's host and path (an
   exchange or regulator; a transcript service; a press room; a statistics body), then the file name's other words (transcript,
   presentation, voluntary announcement, ...), then the manifest's section (a risk folder holds news). Anything else is `other` and
   still extracted.

Every answer carries its `reason`. The type maps to the contract's `source_type` (`SOURCE_OF`) when the caller gave none.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

# -- the manifest -----------------------------------------------------------------------------------------------
# bounded, so a cell of many "[" stays linear (a manifest can now arrive over HTTP: console /v1/manifest)
LINK = re.compile(r"\[([^\]\[\n]{0,500})\]\(([^()\s]{0,2000})\)")
SEPARATOR = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$")
PUBLISHER_COLUMN = re.compile(r"publisher|issuer|outlet|author|published by", re.I)
FILE_NAME = re.compile(r"[^/\\\s]+\.[A-Za-z0-9]{2,5}")      # matched against the last path segment only (is_file_name)


@dataclass(frozen=True)
class ManifestEntry:
    file: str                              # the saved file's name
    section: str                           # the heading over its table
    rank: int                              # its place in that table, from 1
    url: str = ""                          # the source URL the manifest gives
    sha256: str = ""                       # the hash the manifest gives for its bytes
    cells: tuple[tuple[str, str], ...] = ()    # every cell by its column heading, as written
    publisher: str = ""                    # the cell under a "Publisher" (or "Issuer", "Outlet", "Author") column, when the pack has one


@dataclass(frozen=True)
class Manifest:
    title: str = ""
    updated: str = ""
    entries: tuple[ManifestEntry, ...] = ()
    notes: tuple[tuple[str, tuple[str, ...]], ...] = ()    # heading -> its bullet lines

    def entry_for(self, filename: str) -> ManifestEntry | None:
        return next((e for e in self.entries if e.file == filename), None)

    def notes_of(self, heading: str) -> tuple[str, ...]:
        return next((lines for h, lines in self.notes if h == heading), ())


def is_file_name(text: str) -> bool:
    """Whether a cell names a file: its last path segment looks like name.ext (checked without backtracking)."""
    last = re.split(r"[/\\\s]", text.strip())[-1]
    return FILE_NAME.fullmatch(last) is not None


def _cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def _plain(cell: str) -> tuple[str, str]:
    """A cell's text and the first link's URL: `[name](url)` reads as name and url; backticks are dropped."""
    link = LINK.search(cell)
    return LINK.sub(lambda m: m.group(1), cell).replace("`", "").strip(), (link.group(2) if link else "")


def read_manifest(text: str) -> Manifest:
    """The structure of a MANIFEST.md: title, "Updated" line, file tables by section, and each other section's bullets."""
    lines = text.splitlines()
    title = next((ln[2:].strip() for ln in lines if ln.startswith("# ")), "")
    updated = next((m.group(1).strip() for ln in lines if (m := re.match(r"^Updated:\s*(\S.*)$", ln))), "")
    entries: list[ManifestEntry] = []
    notes: dict[str, list[str]] = {}
    section, header, ranks = "", None, 0
    for k, ln in enumerate(lines):
        if ln.startswith("## "):
            section, header, ranks = ln[3:].strip(), None, 0
        elif ln.startswith("- ") and section:
            notes.setdefault(section, []).append(ln[2:].strip())
        elif ln.startswith("|"):
            if header is None and k + 1 < len(lines) and SEPARATOR.match(lines[k + 1].strip()):
                header = [_plain(c)[0] for c in _cells(ln)]
                ranks = 0
            elif header is not None and not SEPARATOR.match(ln.strip()):
                cells = [_plain(c) for c in _cells(ln)]
                name = cells[0][0] if cells else ""
                if "file" in header[0].lower() and is_file_name(name):
                    ranks += 1
                    row = dict(zip(header, cells, strict=False))
                    url = next((u for h, (_t, u) in row.items() if re.search(r"url|source", h, re.I) and u), "")
                    sha = next((t for h, (t, _u) in row.items() if "sha" in h.lower()), "")
                    who = next((t for h, (t, _u) in row.items() if PUBLISHER_COLUMN.fullmatch(h.strip()) and t), "")
                    entries.append(ManifestEntry(name, section, ranks, url, sha.lower(),
                                                 tuple((h, t) for h, (t, _u) in row.items()), who))
        else:
            header = None if not ln.strip() else header
    return Manifest(title, updated, tuple(entries), tuple((h, tuple(v)) for h, v in notes.items()))


# -- typing -----------------------------------------------------------------------------------------------------
TYPES = ("filing", "report", "transcript", "presentation", "news", "data_aggregate", "index_page", "other")
SOURCE_OF = {"filing": "filing", "report": "filing", "presentation": "filing", "transcript": "expert_call", "news": "news",
             "data_aggregate": "data", "index_page": "other", "other": "other"}
MIN_SUBSTANCE = 500                        # characters of prose and table rows an HTML page needs to be a document
MIN_TEXT = 200                             # letters and digits a PDF needs (its pages are not menus)
PROSE_WORDS = 8                            # a line of this many words is prose
PROSE_CJK = 12                             # ... or this many ideographs or Hangul syllables (a menu item has a few)
LINK_LIST_LINES = 15                       # a page of this many short lines and no prose is a list of links
HEAD_CHARS = 3000
GATED_LIMIT = 1500                         # a page with more prose than this is no gate, whatever words it quotes
CJK_RUN = re.compile("[\u3400-\u9fff\uac00-\ud7af\u3040-\u30ff]")
TOKEN = re.compile(r"[a-z0-9]+")
GATED = re.compile(r"enable javascript|javascript (?:is|must be) (?:disabled|required|enabled)|please wait|잠시만 기다려|"
                   r"subscribe to (?:read|continue)|sign in to (?:read|view|continue)|log ?in to (?:read|view|continue)|"
                   r"access denied|403 forbidden|paywall|premium (?:content|subscription)|请开启javascript|请启用javascript|"
                   r"no content to display|content (?:is )?not available|page not found|available only to",
                   re.I)
GATED_NAME = re.compile(r"js gated|gated|paywall")
INDEX_ONLY = re.compile(r"index only")
NOTICE_ONLY = re.compile(r"notice only")
INDEX_FILE = re.compile(r"\bindex (?:of|page)\b|\b(?:transcript|filing|notice|release|document)s? index\b")
INDEX_NAME = re.compile(r"\b(?:index|archive|filing search|search|listing)\b")
URL_RULES = (
    ("filing", re.compile(r"hkexnews\.hk|cninfo\.com\.cn|dart\.fss\.or\.kr|sec\.gov|szse\.cn|sse\.com\.cn|krx\.co\.kr|edinet|"
                          r"/ir/notices/|federalregister\.gov", re.I)),
    ("transcript", re.compile(r"transcript", re.I)),
    ("data_aggregate", re.compile(r"sneresearch|cabia|statista|/statistics?/", re.I)),
    ("news", re.compile(r"/newsroom/|/news/|press[-_]?release|reuters\.com|bloomberg\.com|investing\.com|cls\.cn|ithome\.com|"
                        r"10jqka|cnfin|stockstar|eastmoney", re.I)),
)
# a file name as words ("ir-record" is "ir record"): the first type whose pattern is found. A report is named before the
# address is asked (an annual report on an exchange's site is a report, not "a filing").
NAME_FIRST = (("report", re.compile(r"(?:annual|interim|quarterly|half year|business|statutory|esg|sustainability|integrated) report|"
                                    r"financial statements|first quarterly")),)
NAME_AFTER = (
    ("transcript", re.compile(r"transcript|ir (?:activity )?record|activity record|earnings call|investor relations activity")),
    ("presentation", re.compile(r"presentation|investor day|\bdeck\b|slides|ir conference|briefing")),
    ("data_aggregate", re.compile(r"back series|installation data|market share|statistics|\bsne research|cabia")),
    ("filing", re.compile(r"announcement|disclosure|prospectus|\b10 ?[kq]\b|allotment|regulatory|notice|results release|"
                          r"press release|guidance")),
)
SECTION_RULES = (("news", re.compile(r"risk|event|capital action|news", re.I)),)


@dataclass(frozen=True)
class Kind:
    type: str
    reason: str
    excluded: bool = False
    basis: str = ""                        # name | url | content | section | default

    def meta(self) -> dict:
        return {"type": self.type, "reason": self.reason, "excluded": self.excluded, "basis": self.basis}


def substance(text: str) -> int:
    """How much of a page is prose or data: the characters of lines that read as prose (eight words, or twelve ideographs
    or syllables) and of table rows with a figure. A menu, a footer, and a script shell have none."""
    total = 0
    for line in text.splitlines():
        row = " | " in line and any(c.isdigit() for c in line)
        if row or len(line.split()) >= PROSE_WORDS or len(CJK_RUN.findall(line)) >= PROSE_CJK:
            total += len(line)
    return total


def _words(name: str) -> str:
    return " ".join(TOKEN.findall(name.lower()))


def _empty(filename: str, text: str, where: str, fmt: str) -> Kind | None:
    """A page that holds no content, as a Kind (excluded), or None when it holds some. A web page is judged by its prose (a menu
    and a footer around a short body are common); a PDF by its letters and digits (its pages are not menus)."""
    name = _words(filename)
    if fmt == "pdf":
        letters = sum(c.isalnum() for c in text)
        if letters >= MIN_TEXT:
            return None
        return Kind("other", f"no content: {letters} letters and digits in the whole document", True, "content")
    prose = substance(text)
    gate = GATED.search(text[:2 * HEAD_CHARS]) if prose < GATED_LIMIT else None      # a long page may quote the phrases
    if prose >= MIN_SUBSTANCE and gate is None:
        return None
    lines = [ln for ln in text.splitlines() if any(c.isalnum() for c in ln)]
    if gate or GATED_NAME.search(name):
        return Kind("other", f"no content: a gated page ({gate.group(0).strip() if gate else 'named as gated'}); "
                             f"{prose} characters of prose", True, "content")
    if INDEX_NAME.search(name) or INDEX_NAME.search(where) or len(lines) >= LINK_LIST_LINES:
        return Kind("index_page", f"a list of links: only {prose} characters of prose or data among {len(lines)} short lines",
                    True, "content")
    return Kind("other", f"no content: {prose} characters of prose or data (a script shell, a menu, or an empty page)", True,
                "content")


def classify(filename: str, text: str, *, url: str = "", section: str = "", judge: bool = True, fmt: str = "html") -> Kind:
    """The file's type, and whether it is excluded from extraction, with the evidence (see the module's order). With
    `judge` false the page itself is not judged (a scan not yet read, or an upload nobody asked to screen): only its
    address, name, and section type it, and nothing is excluded. `fmt` is the parsed format ("pdf" or a web page)."""
    host = urlsplit(url)
    where = f"{host.netloc}{host.path}"
    name = _words(filename)
    if judge and (INDEX_ONLY.search(name) or INDEX_FILE.search(name)):
        return Kind("index_page", f"the file is named an index ({filename[:80]})", True, "name")
    if NOTICE_ONLY.search(name):
        return Kind("other", "the pack names it a notice only: a notice, not the report", False, "name")
    if judge and (empty := _empty(filename, text, where, fmt)) is not None:
        return empty
    for kind, pat in NAME_FIRST:
        if found := pat.search(name):
            return Kind(kind, f"the file name says so ({found.group(0)})", False, "name")
    for kind, pat in URL_RULES:
        if where and pat.search(where):
            return Kind(kind, f"the source address says so ({host.netloc})", False, "url")
    for kind, pat in NAME_AFTER:
        if found := pat.search(name):
            return Kind(kind, f"the file name says so ({found.group(0)})", False, "name")
    for kind, pat in SECTION_RULES:
        if section and pat.search(section):
            return Kind(kind, f"the manifest's section says so ({section})", False, "section")
    return Kind("other", "no evidence of a more specific type", False, "default")
