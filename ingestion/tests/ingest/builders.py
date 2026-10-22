"""Documents built in the test, byte for byte (no binary fixtures): minimal PDF, DOCX, PPTX, and XLSX files."""

from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _zip(files: dict[str, str | bytes]) -> bytes:
    """A zip with fixed timestamps and order, so the same files always give the same bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, body in files.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, body)
    return buf.getvalue()


def pdf(pages: list[str], title: str | None = None) -> bytes:
    """A real PDF: one Helvetica text line per page (each string is drawn with Tj), with a correct xref table."""
    n = len(pages)
    font = 3 + 2 * n
    objs: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>",
                         ("<< /Type /Pages /Kids [" + " ".join(f"{3 + 2 * k} 0 R" for k in range(n))
                          + f"] /Count {n} >>").encode()]
    for k, text in enumerate(pages):
        lines = text.split("\n")
        ops = "BT /F1 12 Tf 72 720 Td 14 TL " + " ".join(
            "(" + ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj T*" for ln in lines) + " ET"
        stream = ops.encode("latin-1")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * k} 0 R "
                    f"/Resources << /Font << /F1 {font} 0 R >> >> >>".encode())
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    info = None
    if title is not None:
        objs.append(f"<< /Title ({title}) >>".encode("latin-1"))
        info = len(objs)
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for k, body in enumerate(objs):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % (k + 1) + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R" % (len(objs) + 1)
    out += (b" /Info %d 0 R" % info if info else b"") + b" >>\nstartxref\n%d\n%%%%EOF\n" % xref
    return bytes(out)


def docx(body_xml: str) -> bytes:
    """A DOCX whose word/document.xml body is `body_xml` (w: paragraphs)."""
    doc = f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{W_NS}"><w:body>{body_xml}</w:body></w:document>'
    return _zip({"[Content_Types].xml": "<Types/>", "word/document.xml": doc})


def para(*runs: str) -> str:
    """A w:p of text runs; "\\t" becomes a w:tab and "\\n" a w:br."""
    out = []
    for r in runs:
        if r == "\t":
            out.append("<w:r><w:tab/></w:r>")
        elif r == "\n":
            out.append("<w:r><w:br/></w:r>")
        else:
            out.append(f"<w:r><w:t>{escape(r)}</w:t></w:r>")
    return "<w:p>" + "".join(out) + "</w:p>"


def pptx(slides: dict[int, list[str]], extra: dict[str, str | bytes] | None = None) -> bytes:
    """A PPTX with ppt/slides/slide{n}.xml for each n, each paragraph one a:p (written in the given order)."""
    files: dict[str, str | bytes] = {"[Content_Types].xml": "<Types/>"}
    for n, paras in slides.items():
        ps = "".join(f"<a:p><a:r><a:t>{escape(p)}</a:t></a:r></a:p>" for p in paras)
        files[f"ppt/slides/slide{n}.xml"] = (f'<p:sld xmlns:p="{P_NS}" xmlns:a="{A_NS}"><p:cSld><p:spTree><p:sp>'
                                            f"<p:txBody>{ps}</p:txBody></p:sp></p:spTree></p:cSld></p:sld>")
    files.update(extra or {})
    return _zip(files)


def xlsx(sheets: dict[str, list[list[object]]]) -> bytes:
    """An XLSX (openpyxl) with the given sheets and rows."""
    from openpyxl import Workbook

    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r, row in enumerate(rows, start=1):
            for c, v in enumerate(row, start=1):
                if v is not None:
                    ws.cell(row=r, column=c, value=v)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def zip_of(files: dict[str, str | bytes]) -> bytes:
    return _zip(files)


def scanned_pdf(pages: list[str | None]) -> bytes:
    """A PDF whose pages are as the spec says: a string is a page with that text layer, None a page that is a picture (one
    gray image across the whole page, no text), "" a blank page with nothing drawn, "~" a page with only drawn lines
    (a vector rule, no image, no text), and "^text" a picture with that text over it (a footer on a scanned slide)."""
    n = len(pages)
    font = 3 + 2 * n
    image = font + 1
    objs: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>",
                         ("<< /Type /Pages /Kids [" + " ".join(f"{3 + 2 * k} 0 R" for k in range(n))
                          + f"] /Count {n} >>").encode()]
    for k, spec in enumerate(pages):
        if spec is None:
            ops = "q 612 0 0 792 0 0 cm /Im0 Do Q"
        elif spec == "~":
            ops = "72 700 m 540 700 l S"
        elif spec == "":
            ops = ""
        elif spec.startswith("^"):
            ops = f"q 612 0 0 792 0 0 cm /Im0 Do Q BT /F1 12 Tf 72 40 Td ({spec[1:]}) Tj ET"
        else:
            ops = "BT /F1 12 Tf 72 720 Td (" + spec.replace("(", "\\(").replace(")", "\\)") + ") Tj ET"
        stream = ops.encode("latin-1")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * k} 0 R /Resources "
                    f"<< /Font << /F1 {font} 0 R >> /XObject << /Im0 {image} 0 R >> >> >>".encode())
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    pixels = bytes([0, 85, 170, 255])
    objs.append(b"<< /Type /XObject /Subtype /Image /Width 2 /Height 2 /ColorSpace /DeviceGray /BitsPerComponent 8 "
                b"/Length 4 >>\nstream\n" + pixels + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for k, body in enumerate(objs):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % (k + 1) + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)
