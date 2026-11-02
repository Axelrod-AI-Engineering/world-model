"""The library: stored once, typed and dated, its company and class found, its copies linked."""

from __future__ import annotations

import pytest

from axelrod_ingest.sources import read_manifest
from tests.conftest import REPORT, pdf

FIGURES = "\n".join(f"Line {k} amount {100000 + 137 * k:,}" for k in range(60))


def test_a_file_is_stored_once_with_its_pages_and_what_it_is(desk, person):
    lib = desk.library
    data = pdf(REPORT)
    a = lib.add(data, "acme_q3.pdf", account=person, publisher="Acme Motors", published="2026-10-30")
    assert (a.outcome, a.status) == ("new", "new")
    d = lib.get(a.sha256)
    assert (d["company"], d["source_class"], d["pages"], d["published"], d["publisher"]) == (
        "acme", "company", 3, "2026-10-30", "Acme Motors")
    assert lib.pages(a.sha256)[1].startswith("Revenue for the quarter") and lib.path_of(a.sha256, ".pdf").read_bytes() == data
    again = lib.add(data, "copy.pdf", account=None)
    assert (again.outcome, again.status) == ("already stored", "new")
    assert [u["outcome"] for u in desk.db.all("select outcome from uploads order by id")] == ["new", "already stored"]
    assert lib.mime_of(d) == "application/pdf" and lib.mime_of({"filename": "x.unknownext"}) == "application/octet-stream"


def test_a_broker_note_is_sell_side_and_an_unknown_one_waits_for_a_company(desk, person):
    lib = desk.library
    note = lib.add(pdf(["Rival Batteries: buy", "target RMB 300"]), "20261020 - Macquarie - 300750_CH - Rival - 2 pages.pdf",
                   account=person)
    d = lib.get(note.sha256)
    assert (d["company"], d["source_class"], d["publisher"]) == ("rival", "sell_side", "Macquarie")
    loose = lib.add(b"some words about nothing in particular", "memo.txt", account=person)
    assert loose.status == "needs company" and lib.get(loose.sha256)["source_class"] == "other"
    assert lib.list(status="needs company")[0]["sha256"] == loose.sha256
    assert {x["sha256"] for x in lib.list(company="rival", source_class="sell_side")} == {note.sha256}
    assert len(lib.list()) == 2


def test_the_manifest_labels_a_folder_and_a_bad_file_is_reported(desk, person, tmp_path):
    folder = tmp_path / "pack"
    folder.mkdir()
    (folder / "acme_q3.pdf").write_bytes(pdf(REPORT))
    (folder / "broken.pdf").write_bytes(b"%PDF-1.4 not really")
    (folder / "skip.bin").write_bytes(b"\x00")
    (folder / "MANIFEST.md").write_text(
        "# Pack\n\n## Sell-side research\n\n| File | Publisher | Published | Source |\n|---|---|---|---|\n"
        "| acme_q3.pdf | Nomura | 2026-10-31 | [Source](https://example.com/a) |\n")
    added = desk.library.add_folder(folder, account=person, company="acme")
    assert [(x.filename, x.outcome) for x in added] == [("acme_q3.pdf", "new"), ("broken.pdf", "failed")]
    assert added[1].error and desk.library.get(added[1].sha256) is None
    d = desk.library.get(added[0].sha256)
    assert (d["source_class"], d["publisher"], d["published"], d["url"], d["section"]) == (
        "sell_side", "Nomura", "2026-10-31", "https://example.com/a", "Sell-side research")


def test_copies_of_one_disclosure_are_linked_and_only_the_primary_is_read(desk, person):
    lib = desk.library
    en = lib.add(pdf(["Acme Motors results for the three months ended 30 September 2026 (IFRS)", FIGURES]), "acme_en.pdf",
                 account=person, company="acme")
    zh = lib.add(pdf(["Acme Motors quarterly report, period ended 30 September 2026", FIGURES]), "acme_zh.pdf",
                 account=person, company="acme")
    other = lib.add(pdf(["Acme Motors unrelated"]), "other.pdf", account=person, company="acme")
    assert lib.link() == 1
    roles = {s: (lib.get(s)["origin_role"], lib.get(s)["status"]) for s in (en.sha256, zh.sha256, other.sha256)}
    primary = lib.get(en.sha256)["origin_primary"]
    assert sorted(r for r, _ in roles.values() if r) == ["duplicate", "primary"] and roles[other.sha256] == (None, "new")
    dup = next(s for s, (r, _) in roles.items() if r == "duplicate")
    assert roles[dup][1] == "duplicate" and primary != dup
    assert lib.link() == 1                                                         # idempotent


def test_editing_a_document(desk, person):
    lib = desk.library
    a = lib.add(b"words", "memo.txt", account=person)
    d = lib.edit(a.sha256, company="solo", source_class="other", published="2026-10-01", publisher="Solo")
    assert (d["company"], d["status"], d["published"]) == ("solo", "new", "2026-10-01")
    assert lib.edit(a.sha256, note="checked")["status"] == "new"
    for fields, err in (({"status": "read"}, ValueError), ({"company": "ghost"}, ValueError),
                        ({"source_class": "rumour"}, ValueError), ({"published": "soon"}, ValueError)):
        with pytest.raises(err):
            lib.edit(a.sha256, **fields)
    with pytest.raises(KeyError):
        lib.edit("0" * 64, company="acme")
    with pytest.raises(KeyError):
        lib.pages("0" * 64)


def test_adding_with_a_bad_company_or_class_is_refused(desk):
    with pytest.raises(ValueError):
        desk.library.add(b"x", "a.txt", company="ghost")
    with pytest.raises(ValueError):
        desk.library.add(b"y", "b.txt", source_class="rumour")


def test_a_manifest_row_without_a_date_and_a_filing(desk, person):
    m = read_manifest("# P\n\n## Filings\n\n| File | Note |\n|---|---|\n| f.txt | annual report |\n")
    a = desk.library.add(b"Solo Bank annual report 2025", "f.txt", account=person, entry=m.entry_for("f.txt"))
    d = desk.library.get(a.sha256)
    assert d["published"] is None and d["section"] == "Filings" and d["company"] == "solo"


def test_a_lake_document_the_desk_does_not_hold_is_left_alone(desk, person):
    lib = desk.library
    kept = lib.add(pdf(["Acme Motors results for the three months ended 30 September 2026 (IFRS)", FIGURES]), "en.pdf",
                   account=person, company="acme")
    lib.ingestor.ingest_file(lib.tenant, pdf(["Acme Motors report, period ended 30 September 2026", FIGURES]), "lake.pdf",
                             lib.graph)
    assert lib.link() == 1 and lib.get(kept.sha256)["origin_role"] == "primary" and len(lib.list()) == 1
