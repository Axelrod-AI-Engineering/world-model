"""Decoding (Oct 22): a text file's bytes into a string, deterministically, and say how.

The order is fixed. A byte-order mark decides first (UTF-8, UTF-16, UTF-32). Then, for HTML, the page's own declaration:
`<meta charset>`, `<meta http-equiv="Content-Type" content="...; charset=...">`, or an XML declaration, read from the
first bytes. Then UTF-8, and only when that fails, Latin-1, which never fails and is reported as a fallback, so a page
that was read wrongly is visible in the document's metadata instead of silent.

A declared name is read as the encoding web browsers read it as: the superset that decodes every byte the older name
could (gb2312 and gbk as gb18030, euc-kr and ks_c_5601-1987 as cp949, shift_jis as cp932, big5 as big5hkscs, latin-1
and ascii as cp1252). A declaration the bytes do not fit, or one Python does not know, is ignored, never trusted.
"""

from __future__ import annotations

import codecs
import re
from dataclasses import dataclass

SNIFF_BYTES = 4096                       # how far into a page a charset declaration is looked for
BOMS = ((codecs.BOM_UTF32_LE, "utf-32"), (codecs.BOM_UTF32_BE, "utf-32"),
        (codecs.BOM_UTF16_LE, "utf-16"), (codecs.BOM_UTF16_BE, "utf-16"), (codecs.BOM_UTF8, "utf-8-sig"))
ALIASES = {"gb2312": "gb18030", "gbk": "gb18030", "gb_2312-80": "gb18030", "x-gbk": "gb18030", "euc-cn": "gb18030",
           "euc-kr": "cp949", "ks_c_5601-1987": "cp949", "ks_c_5601": "cp949", "x-windows-949": "cp949",
           "shift_jis": "cp932", "shift-jis": "cp932", "sjis": "cp932", "x-sjis": "cp932", "windows-31j": "cp932",
           "big5": "big5hkscs", "big5-hkscs": "big5hkscs",
           "iso-8859-1": "cp1252", "latin1": "cp1252", "latin-1": "cp1252", "ascii": "cp1252", "us-ascii": "cp1252"}
# the declarations, each a short pattern over ASCII bytes (read as Latin-1, which maps every byte to one character)
DECLARATION = re.compile(r"<meta\b[^>]{0,400}?\bcharset\s{0,3}=\s{0,3}[\"']?\s{0,3}([\w:.-]{1,40})"
                         r"|<\?xml\b[^>]{0,200}?\bencoding\s{0,3}=\s{0,3}[\"']([\w:.-]{1,40})", re.I)


@dataclass(frozen=True)
class Decoded:
    text: str
    encoding: str                        # the codec used ("gb18030", "utf-8", "latin-1")
    how: str                             # bom | declared | utf-8 | fallback


def declared(data: bytes) -> str | None:
    """The charset a page declares, as a codec Python knows (browser-style supersets applied), or None."""
    m = DECLARATION.search(data[:SNIFF_BYTES].decode("latin-1"))
    label = ((m.group(1) or m.group(2)) if m else "").lower()
    if not label:
        return None
    name = ALIASES.get(label, label)
    try:
        return codecs.lookup(name).name
    except LookupError:
        return None


def decode(data: bytes, *, html: bool = False) -> Decoded:
    """The text of `data` and how it was decoded (see the module's order)."""
    for bom, name in BOMS:
        if data.startswith(bom):
            try:
                return Decoded(data.decode(name), name.removesuffix("-sig"), "bom")
            except UnicodeDecodeError:
                break                                     # a mark the rest of the bytes do not fit: no mark at all
    name = declared(data) if html else None
    if name:
        try:
            return Decoded(data.decode(name), name, "declared")
        except UnicodeDecodeError:
            pass                                          # the page says one thing and holds another
    try:
        return Decoded(data.decode("utf-8"), "utf-8", "utf-8")
    except UnicodeDecodeError:
        return Decoded(data.decode("latin-1"), "latin-1", "fallback")
