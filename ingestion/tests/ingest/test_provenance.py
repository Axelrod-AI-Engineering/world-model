"""Attribution on every item (Oct 25): `document`, `publisher`, `basis`, `citation`, `coverage` and `plausible`, which the world
model's standards gate reads. Each rule is tested alone, then through the pipeline, a manifest, and the stored bundle."""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from axelrod_ingest import EXTRACTOR_VERSION
from axelrod_ingest.contract.bundle import ImportBundle
from axelrod_ingest.extract import (
    basis_of,
    citation_of,
    coverage_of,
    plausible_of,
    provenance_of,
    signal_plausible,
)
from axelrod_ingest.parse import parse
from axelrod_ingest.pipeline import bundle_id, publisher_of
from axelrod_ingest.sources import read_manifest
from tests.ingest.builders import pdf

T = "acme"
RATE = "central_bank.policy_rate"
CET1 = "acme_bank.cet1_ratio"
FILING = b"# Acme Bank Corp results\n\nPublished 2026-08-04.\n\nAcme Bank reported its CET1 ratio of 13.1%.\n"
NEWS = b"# Markets wrap\n\nPublished 2026-08-05.\n\nAcme Bank said its CET1 ratio was 13.4%.\n"
LINK = (b"# Rates note\n\nPublished 2026-08-05.\n\nThe central bank raised its policy rate by 25bp to 4.25%. "
        b"Higher government bond yields lift Acme Re.\n")


def observe(sid=CET1, value=13.1, **kw) -> dict:
    return {"type": "observe", "value_of": sid, "value": value, "quote": "q", **kw}


def move(delta=0.25, mode="absolute", sid=RATE) -> dict:
    return {"type": "move", "value_of": sid, "delta": delta, "mode": mode, "quote": "q"}


def link(quote="Higher yields lift Acme Re.") -> dict:
    return {"type": "link", "source": "gov_bonds.yield_10y", "target": "acme_re.domestic_pc_profit", "label": "lift",
            "effect": 0.3, "quote": quote}


# -- plausibility ---------------------------------------------------------------------------------------------------
def test_a_level_is_plausible_inside_the_band_and_not_outside(rules):
    assert signal_plausible(rules, observe(value=13.1)) is True
    assert signal_plausible(rules, observe(value=900.0)) is False


def test_a_sized_move_is_checked_by_its_size_and_a_direction_or_link_is_not(rules):
    assert signal_plausible(rules, move(0.25)) is True and signal_plausible(rules, move(0.4, "relative")) is True
    assert signal_plausible(rules, move(5.0)) is False and signal_plausible(rules, move(0.95, "relative")) is False
    assert signal_plausible(rules, move(0.0)) is False
    assert signal_plausible(rules, move(0.5, "standardized")) is None and signal_plausible(rules, link()) is None


def test_an_item_is_plausible_only_when_every_signal_was_checked_and_is_in_band(rules):
    assert plausible_of(rules, [observe(), move()]) is True
    assert plausible_of(rules, [observe(), observe(value=900.0)]) is False
    assert plausible_of(rules, [observe(), link()]) is None


# -- basis ----------------------------------------------------------------------------------------------------------
def test_an_issuers_own_filing_about_itself_is_direct(rules):
    assert basis_of(rules, [observe(CET1), move(0.1, "relative", "acme_bank.net_income")], "filing", "acme_bank") == "direct"


def test_a_filing_about_another_entity_or_with_a_link_is_not_decided(rules):
    assert basis_of(rules, [observe(CET1)], "filing", "acme_motors") is None
    assert basis_of(rules, [observe(CET1)], "filing", None) is None
    assert basis_of(rules, [observe(CET1), link()], "filing", "acme_bank") is None


def test_third_party_levels_and_sized_moves_are_a_proxy_and_links_context_only(rules):
    for source in ("broker_research", "expert_call", "news", "other"):
        assert basis_of(rules, [observe(), move()], source, "acme_bank") == "proxy"
    assert basis_of(rules, [link()], "news", None) == "context_only"
    assert basis_of(rules, [move(mode="standardized"), link()], "broker_research", None) == "context_only"
    assert basis_of(rules, [observe(), link()], "news", None) is None             # a mix: a person decides


@pytest.mark.parametrize("source", ["central_bank", "data", "client_model"])
def test_other_sources_leave_the_basis_open(rules, source):
    assert basis_of(rules, [observe()], source, "acme_bank") is None


# -- coverage -------------------------------------------------------------------------------------------------------
def test_coverage_is_partial_for_a_part_of_a_total_or_a_years_flow_from_a_part_year(rules):
    assert coverage_of(rules, [observe(CET1)], False) == "full"
    assert coverage_of(rules, [observe("acme_bank.ib_fees", 1.0)], False) == "partial"             # a part of net revenue
    flow = observe("acme_bank.net_income", 4.0)
    assert rules.graph.values["acme_bank.net_income"].unit.endswith("/yr")
    assert coverage_of(rules, [flow], True) == "partial"
    assert coverage_of(rules, [observe(RATE, 4.25)], True) == "full"                               # a rate is no flow


def test_a_link_has_no_coverage(rules):
    assert coverage_of(rules, [link()], False) is None


# -- citation -------------------------------------------------------------------------------------------------------
def test_a_citation_names_the_document_page_and_span_of_the_sentence():
    chunk = NS(text="Intro. Higher yields lift Acme Re. End.", start=100, page=3, ord=7)
    assert citation_of("Dabc", chunk, [observe(), link()]) == "Dabc p.3 chars 107-134"


def test_a_citation_without_a_page_or_a_found_sentence_falls_back():
    chunk = NS(text="Intro. Higher yields lift Acme Re.", start=0, page=None, ord=7)
    assert citation_of("Dabc", chunk, [link()]) == "Dabc chars 7-34"
    assert citation_of("Dabc", chunk, [link("not in the chunk")]) == "Dabc chunk 7"
    assert citation_of("Dabc", chunk, [link("")]) == "Dabc chunk 7"
    assert citation_of("Dabc", NS(text="x", start=0, page=2, ord=1), [link("zz")]) == "Dabc p.2 chunk 1"


def test_an_item_with_no_link_has_no_citation():
    assert citation_of("Dabc", NS(text="x", start=0, page=None, ord=0), [observe()]) == ""


def test_provenance_of_gathers_the_fields(rules):
    item = {"signals": [observe()], "source_type": "news"}
    got = provenance_of(rules, item, doc_id="Dabc", chunk=NS(text="", start=0, page=None, ord=0), subject="acme_bank",
                        partial=False, publisher="Wire", url="https://x.example/a")
    assert got == {"document": "Dabc", "publisher": "Wire", "url": "https://x.example/a", "basis": "proxy", "citation": "",
                   "coverage": "full", "plausible": True}
    assert provenance_of(rules, item, doc_id="Dabc", chunk=NS(text="", start=0, page=None, ord=0), subject=None,
                         partial=False, publisher="", url="")["url"] is None


# -- publisher ------------------------------------------------------------------------------------------------------
def doc(**meta):
    return NS(meta=meta)


def test_the_publisher_is_the_manifests_then_the_callers_then_the_documents_then_the_urls_host():
    manifest = {"publisher": "Pack Publisher", "url": "https://www.wire.example/a/b"}
    both = {"manifest": manifest, "hints": {"publisher": "Hint"}, "publisher": "Meta Author"}
    assert publisher_of(doc(**both)) == ("Pack Publisher", "https://www.wire.example/a/b")
    both["manifest"] = {**manifest, "publisher": ""}
    assert publisher_of(doc(**both))[0] == "Hint"
    del both["hints"]
    assert publisher_of(doc(**both))[0] == "Meta Author"
    del both["publisher"]
    assert publisher_of(doc(**both)) == ("wire.example", "https://www.wire.example/a/b")
    assert publisher_of(doc()) == ("", None)


def test_an_html_page_names_its_publisher_in_a_meta_tag():
    page = (b"<html><head><title>T</title><meta name='author' content='A Writer'>"
            b"<meta property='og:site_name' content='  Synthetic Wire '><meta name='x' content='y'>"
            b"<meta name='publisher' content=''><meta charset='utf-8'></head><body><p>"
            + b"The central bank raised its policy rate. " * 3 + b"</p></body></html>")
    assert parse(page, "a.html").meta["publisher"] == "Synthetic Wire"          # og:site_name before the author
    assert "publisher" not in parse(b"<html><body><p>No tags here at all.</p></body></html>", "b.html").meta


def test_a_pdf_names_its_author_as_publisher():
    assert parse(pdf(["Crude rose."], title="T", author="Synthetic Research"), "x.pdf").meta["publisher"] == "Synthetic Research"
    assert "publisher" not in parse(pdf(["Crude rose."], title="T"), "x.pdf").meta
    assert parse(pdf(["Crude rose."], author="Only Author"), "y.pdf").meta["publisher"] == "Only Author"


def test_a_manifest_publisher_column_is_read():
    m = read_manifest("# P\n\n## News\n\n| File | URL | Publisher |\n|---|---|---|\n"
                      "| a.html | [x](https://w.example/a) | Synthetic Wire |\n| b.html | [y](https://w.example/b) |  |\n")
    assert [e.publisher for e in m.entries] == ["Synthetic Wire", ""]


# -- the pipeline ---------------------------------------------------------------------------------------------------
def items_of(res) -> list[dict]:
    return res.bundle.bundle["items"]


def test_a_filing_about_itself_is_attributed_and_direct(ingestor, graph):
    res = ingestor.ingest_file(T, FILING, "results.md", graph, source="Synthetic IR", source_type="filing")
    (item,) = items_of(res)
    assert item["document"] == res.document.id and item["publisher"] == "" and item["url"] is None
    assert (item["basis"], item["coverage"], item["plausible"], item["citation"]) == ("direct", "full", True, "")


def test_news_with_a_hint_or_a_manifest_url_has_a_publisher_and_is_a_proxy(ingestor, graph):
    res = ingestor.ingest_file(T, NEWS, "wrap.md", graph, source_type="news",
                               meta={"hints": {"publisher": "Synthetic Wire"}})
    (item,) = items_of(res)
    assert item["publisher"] == "Synthetic Wire" and item["basis"] == "proxy" and item["plausible"] is True
    manifest = {"file": "wrap2.md", "url": "https://www.wire.example/wrap", "section": "", "rank": 1, "sha256": "",
                "publisher": ""}
    res = ingestor.ingest_file(T, NEWS + b"\n", "wrap2.md", graph, source_type="news", meta={"manifest": manifest})
    (item,) = items_of(res)
    assert item["publisher"] == "wire.example" and item["url"] == "https://www.wire.example/wrap"


def test_news_with_no_publisher_leaves_it_empty(ingestor, graph):
    (item,) = items_of(ingestor.ingest_file(T, NEWS, "wrap.md", graph, source_type="news"))
    assert item["publisher"] == "" and item["basis"] == "proxy"


def test_a_link_is_cited_by_document_and_character_span(ingestor, graph):
    res = ingestor.ingest_file(T, LINK, "rates.md", graph, source_type="broker_research")
    (item,) = items_of(res)
    quote = next(s["quote"] for s in item["signals"] if s["type"] == "support")
    text, _ = ingestor.store.get_text(T, res.document.id)
    start = text.index(quote)
    assert item["citation"] == f"{res.document.id} chars {start}-{start + len(quote)}"
    assert item["basis"] is None and item["plausible"] is None                  # a level, a move and a support: a mix


def test_a_page_of_a_pdf_is_in_the_citation(ingestor, graph):
    data = pdf(["Intro.", "Higher government bond yields lift Acme Re. More text follows here."], author="Desk")
    res = ingestor.ingest_file(T, data, "note.pdf", graph, source_type="broker_research")
    (item,) = items_of(res)
    assert item["publisher"] == "Desk" and item["basis"] == "context_only"
    assert item["citation"].startswith(f"{res.document.id} p.2 chars ")


def test_the_same_file_gives_the_same_bundle_and_the_version_moved(ingestor, graph, lake, inverted):
    first = ingestor.ingest_file(T, NEWS, "wrap.md", graph, source_type="news")
    again = ingestor.process(T, first.document.id, graph)
    assert first.bundle.id == again.bundle.id == bundle_id(first.bundle.bundle)
    assert first.bundle.bundle == again.bundle.bundle and EXTRACTOR_VERSION == "ingest-1.2"
    ImportBundle.model_validate(first.bundle.bundle)


def test_an_uploaded_bundle_passes_through_without_attribution_added(ingestor, graph):
    raw = (b'{"format": "axelrod.import/v1", "items": [{"id": "A", "published_at": "2026-08-05T00:00:00Z", '
           b'"source": "S", "headline": "h", "signals": []}]}')
    res = ingestor.ingest_file(T, raw, "b.json", graph)
    (item,) = items_of(res)
    assert item["document"] == "" and item["publisher"] == "" and item["basis"] is None and item["plausible"] is None
