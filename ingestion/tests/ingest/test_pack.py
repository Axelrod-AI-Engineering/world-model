"""A pack of files with a manifest, ingested into a lake: a row for every file, duplicates linked, and two runs of the same
pack giving byte-identical lakes. The pack is built here from invented files."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from axelrod_ingest import pack as pack_module
from axelrod_ingest.lake.embed import HashingEmbedder
from axelrod_ingest.lake.sqlite import SQLiteLake
from axelrod_ingest.ocr import Ocr, find_tesseract
from axelrod_ingest.pack import (
    find_manifest,
    ingest_pack,
    lake_digest,
    main,
    pack_files,
    run,
    world_from_file,
)
from axelrod_ingest.pipeline import Ingestor
from tests.ingest.builders import pdf, scanned_pdf
from tests.ingest.multilingual import world
from tests.ingest.test_ocr import engine

NOW = datetime(2026, 10, 22, tzinfo=UTC)
FIGURES = [f"{100000 + k * 37:,}" for k in range(80)]
PRC = "Acme EV Co., Ltd. (A joint stock company incorporated in the People's Republic of China)"


OCR_BODY = ('cat >/dev/null; echo "Acme EV net profit: CNY 7.5bn. ' + "The slide goes on to describe the plan in some detail. " * 6 + '"')


def en_pdf() -> bytes:
    lines = [f"{PRC}", "Interim Report 2026", "For the six months ended 30 June 2026 under IFRS.",
             "Acme EV net profit: CNY 8.5bn.", *[f"Item {k}: {f}" for k, f in enumerate(FIGURES)]]
    return pdf(["\n".join(lines[i:i + 25]) for i in range(0, len(lines), 25)])


def zh_html() -> bytes:
    body = "".join(f"<p>第{k}项的金额为{f}元，同比有所变化，管理层认为业务保持稳定。</p>" for k, f in enumerate(FIGURES[:70]))
    page = ("<html><head><meta http-equiv=\"Content-Type\" content=\"text/html; charset=gb2312\"><title>艾克米电动2026年半年度报告</title>"
            f"</head><body><p>艾克米电动股份有限公司 2026 年半年度报告。艾克米电动净利润为人民币85亿元，营业收入为人民币1,200亿元。</p>{body}</body></html>")
    return page.encode("gb18030")


FILES = {
    "Business/001_1_28-Aug-2026_Interim-Report-English.pdf": en_pdf(),
    "Business/001_1_2026-08-29_Interim-Report-Chinese.html": zh_html(),
    "Business/001_INDEX_ONLY_Archive.html": b"<html><body>" + b"<p>Archive of filings, see the list below for the filings.</p>" * 40 + b"</body></html>",
    "Risk/001_3_undated_scanned-deck.pdf": scanned_pdf([None]),
    "Risk/001_3_notes.txt": b"Acme EV net profit: CNY 9.5bn. Note of 2026-09-01.",
    "Risk/files.zip": b"PK\x03\x04",
}


def manifest(files: dict[str, bytes]) -> str:
    def row(name: str, data: bytes, url: str, sha: str | None = None) -> str:
        return f"| [{Path(name).name}](https://drive.example/{name}) | [Original source](https://www.hkexnews.hk/{name}) | `{sha or hashlib.sha256(data).hexdigest()}` |"
    listed = [n for n in files if not n.endswith(("notes.txt", ".zip"))]
    return "\n".join([
        "# Acme EV - source pack", "", "Updated: 20 October 2026.", "", "## Business", "",
        "| Saved file | Source URL | SHA-256 |", "|---|---|---|",
        *[row(n, files[n], "", "00" * 32 if n.endswith("Chinese.html") else None) for n in listed if n.startswith("Business")],
        "", "## Risk", "", "| Saved file | Source URL | SHA-256 |", "|---|---|---|",
        *[row(n, files[n], "") for n in listed if n.startswith("Risk")], "| [missing.pdf](https://drive.example/m) | x | `ab` |",
        "", "## Outstanding or unavailable items", "", "- Q3 report not retrieved.", ""])


@pytest.fixture
def pack(tmp_path) -> Path:
    root = tmp_path / "pack"
    for name, data in FILES.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)
    (root / "MANIFEST.md").write_text(manifest(FILES), encoding="utf-8")
    (root / ".hidden").write_bytes(b"x")
    return root


@pytest.fixture
def fake_ocr(tmp_path) -> Ocr:
    exe = find_tesseract({"AXELROD_TESSERACT": str(engine(tmp_path, body=OCR_BODY))})
    return Ocr(exe, tmp_path / "cache")


def run_pack(root: Path, lake_dir: Path, ocr: Ocr | None):
    lake = SQLiteLake(lake_dir)
    try:
        ing = Ingestor(lake, HashingEmbedder(), clock=lambda: NOW, ocr=ocr, screen=True)
        report = ingest_pack(root, ing, world(), tenant="acme")
        return report, lake_digest(lake, "acme")
    finally:
        lake.close()


def test_pack_files_are_sorted_and_leave_out_the_manifest_and_hidden_files(pack):
    names = [p.relative_to(pack).as_posix() for p in pack_files(pack)]
    assert names == sorted(FILES) and "MANIFEST.md" not in names and ".hidden" not in names


def test_the_manifest_is_found_anywhere_under_the_pack_or_is_empty(pack, tmp_path):
    assert len(find_manifest(pack).entries) == 5
    nested = tmp_path / "nested"
    (nested / "Acme 001").mkdir(parents=True)
    (nested / "Acme 001" / "MANIFEST.md").write_text(manifest(FILES))
    assert find_manifest(nested).title == "Acme EV - source pack"
    assert find_manifest(tmp_path / "pack").title == "Acme EV - source pack" and find_manifest(tmp_path / "empty-nowhere").entries == ()


def test_a_row_for_every_file(pack, tmp_path, fake_ocr):
    report, _ = run_pack(pack, tmp_path / "lake", fake_ocr)
    rows = {r.path.split("/")[-1]: r for r in report.rows}
    assert list(rows) == [p.name for p in pack_files(pack)] and report.manifest_title == "Acme EV - source pack"
    en, zh = rows["001_1_28-Aug-2026_Interim-Report-English.pdf"], rows["001_1_2026-08-29_Interim-Report-Chinese.html"]
    assert (en.status, en.doc_type, en.language, en.pages, en.format) == ("extracted", "report", "en", 4, "pdf")
    assert (en.published_source, en.published_at[:10], en.period, en.in_manifest, en.sha256_matches) == (
        "manifest", "2026-08-28", "2026-H1", True, True)
    assert (zh.status, zh.language, zh.format, zh.sha256_matches, zh.yen, zh.yen_signs) == ("extracted", "zh", "html", False, "CNY", 0)
    assert en.signals >= 1 and zh.signals == 2 and en.bundle_id and en.chunks > 0 and en.mentions > 0
    idx = rows["001_INDEX_ONLY_Archive.html"]
    assert (idx.status, idx.doc_type, idx.chunks, idx.bundle_id) == ("excluded", "index_page", 0, "") and "named an index" in idx.error
    scan = rows["001_3_undated_scanned-deck.pdf"]
    assert (scan.status, scan.ocr_pages, scan.needs_ocr, scan.published_source) == ("extracted", 1, [], "ingested_at")
    notes = rows["001_3_notes.txt"]
    assert (notes.in_manifest, notes.sha256_matches, notes.status) == (False, None, "extracted")
    zipped = rows["files.zip"]
    assert (zipped.status, zipped.error, zipped.doc_id) == ("skipped", "unsupported file type", "")
    assert report.missing == ["missing.pdf"]


def test_the_summary_counts_what_happened(pack, tmp_path, fake_ocr):
    report, _ = run_pack(pack, tmp_path / "lake", fake_ocr)
    s = report.summary()
    assert (s["files"], s["documents"], s["extracted"], s["excluded"], s["skipped"], s["failed"]) == (6 - 0, 5, 4, 1, 1, 0)
    assert (s["needs_ocr"], s["ocr_pages"], s["hash_mismatches"], s["not_in_manifest"], s["manifest_missing"]) == (0, 1, 1, 1, 1)
    assert s["types"] == {"filing": 1, "index_page": 1, "other": 1, "report": 2} and s["languages"] == {"en": 4, "zh": 1}
    assert s["duplicate_groups"] == 1 and s["duplicate_copies"] == 1 and s["chunks"] == sum(r.chunks for r in report.rows)
    assert s["signals"] == sum(r.signals for r in report.rows) and s["mentions"] > 0 and s["yen"] == {}
    assert report.stats["documents"] == 5


def test_the_english_and_chinese_reports_are_one_disclosure_with_the_english_copy_primary(pack, tmp_path, fake_ocr):
    report, _ = run_pack(pack, tmp_path / "lake", fake_ocr)
    (g,) = report.groups
    rows = {r.path.split("/")[-1]: r for r in report.rows}
    assert set(g.members) == {rows["001_1_28-Aug-2026_Interim-Report-English.pdf"].doc_id,
                              rows["001_1_2026-08-29_Interim-Report-Chinese.html"].doc_id}
    assert g.primary == rows["001_1_28-Aug-2026_Interim-Report-English.pdf"].doc_id


def test_without_an_engine_the_scan_is_reported_not_lost(pack, tmp_path):
    report, _ = run_pack(pack, tmp_path / "lake", None)
    scan = next(r for r in report.rows if r.path.endswith("scanned-deck.pdf"))
    assert (scan.status, scan.needs_ocr, scan.chunks) == ("needs_ocr", [1], 0)
    assert report.summary()["needs_ocr"] == 1 and "needs_ocr" in scan.error


def test_two_runs_of_the_same_pack_give_identical_lakes_and_bundle_ids(pack, tmp_path, fake_ocr):
    (a, da), (b, db) = run_pack(pack, tmp_path / "one", fake_ocr), run_pack(pack, tmp_path / "two", fake_ocr)
    assert da == db and [r.bundle_id for r in a.rows] == [r.bundle_id for r in b.rows] and len(da["all"]) == 64
    assert set(da) == {"documents", "texts", "chunks", "mentions", "embeddings", "bundles", "all"}
    (pack / "Risk" / "001_3_notes.txt").write_bytes(b"Acme EV net profit: CNY 9.6bn. Note of 2026-09-01.")
    _c, dc = run_pack(pack, tmp_path / "three", fake_ocr)
    assert dc["all"] != da["all"] and dc["texts"] != da["texts"] and dc["documents"] != da["documents"]


def test_the_digest_sees_every_kind_of_record(pack, tmp_path, fake_ocr):
    _r, base = run_pack(pack, tmp_path / "one", fake_ocr)
    lake = SQLiteLake(tmp_path / "one")
    try:
        doc = lake.list_documents("acme", limit=1, order="ingested_at")[0]
        lake.put_mentions("acme", doc.id, [])
        assert lake_digest(lake, "acme")["mentions"] != base["mentions"]
    finally:
        lake.close()


def test_world_from_file_reads_what_the_exporter_writes(tmp_path):
    f = tmp_path / "wv.json"
    f.write_text(json.dumps({"inverted": ["(?:the )?yen"], "world_view": json.loads(world().to_json())}))
    graph, inverted = world_from_file(f)
    assert graph == world() and inverted == frozenset({"(?:the )?yen"})
    f.write_text(json.dumps({"world_view": json.loads(world().to_json())}))
    assert world_from_file(f)[1] == frozenset()


@pytest.fixture
def wv(tmp_path) -> Path:
    f = tmp_path / "wv.json"
    f.write_text(json.dumps({"inverted": [], "world_view": json.loads(world().to_json())}))
    return f


def test_run_uses_the_environment_for_ocr_and_never_the_llm(pack, wv, tmp_path, monkeypatch):
    exe = engine(tmp_path, body=OCR_BODY)
    monkeypatch.setenv("AXELROD_TESSERACT", str(exe))
    report, digest = run(pack, wv, tmp_path / "lake", tenant="acme", clock=NOW)
    scan = next(r for r in report.rows if r.path.endswith("scanned-deck.pdf"))
    assert scan.status == "extracted" and (tmp_path / "lake" / "ocr").is_dir() and len(digest["all"]) == 64
    monkeypatch.setenv("AXELROD_OCR", "off")
    off, _ = run(pack, wv, tmp_path / "lake2", tenant="acme", clock=NOW)
    assert next(r for r in off.rows if r.path.endswith("scanned-deck.pdf")).status == "needs_ocr"


def test_main_runs_a_pack_twice_and_says_the_lakes_are_identical(pack, wv, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AXELROD_TESSERACT", str(engine(tmp_path, body=OCR_BODY)))
    out = tmp_path / "report.json"
    code = main([str(pack), "--world-view", str(wv), "--lake-dir", str(tmp_path / "a"), "--twice", str(tmp_path / "b"),
                 "--report", str(out), "--tenant", "acme"])
    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["determinism"] == {"identical": True, "bundle_ids_equal": True, "differing": []}
    saved = json.loads(out.read_text())
    assert saved["summary"] == printed["summary"] and len(saved["report"]["rows"]) == 6 and saved["digest"] == printed["digest"]


def test_main_without_twice_or_a_report_and_with_the_default_tenant(pack, wv, tmp_path, capsys):
    assert main([str(pack), "--world-view", str(wv), "--lake-dir", str(tmp_path / "a")]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert "determinism" not in printed and printed["summary"]["files"] == 6
    assert (tmp_path / "a").is_dir()


def test_main_fails_when_two_runs_differ(pack, wv, tmp_path, monkeypatch, capsys):
    real = pack_module.run
    n = []

    def drift(*a, **k):
        report, digest = real(*a, **k)
        n.append(1)
        return report, {**digest, "texts": digest["texts"] + ("x" if len(n) == 2 else ""), "all": digest["all"] + ("x" if len(n) == 2 else "")}

    monkeypatch.setattr(pack_module, "run", drift)
    assert main([str(pack), "--world-view", str(wv), "--lake-dir", str(tmp_path / "a"), "--twice", str(tmp_path / "b")]) == 1
    assert json.loads(capsys.readouterr().out)["determinism"]["differing"] == ["all", "texts"]
