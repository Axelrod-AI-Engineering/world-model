"""Ingestion's attribution fields reach the standards gate: a synthetic document is ingested against the acme model's own
view, its bundle is imported under `standards`, and the gate reads `document`, `publisher`, `basis`, `coverage` and
`plausible` as ingestion wrote them. A well-attributed figure applies as `policy:standards`; a news item with no
publisher waits with the reason."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from axelrod_ingest.lake.embed import HashingEmbedder
from axelrod_ingest.lake.sqlite import SQLiteLake
from axelrod_ingest.pipeline import Ingestor
from axelrod_wm.intake.world_view import world_view_of
from axelrod_wm.repo.snapshots import MemoryBackend
from tests.unit.sim.test_import_persistence import decisions_by, runner

NOW = datetime(2026, 10, 25, tzinfo=UTC)
FILING = b"# Acme Bank Corp results\n\nPublished 2026-08-04.\n\nAcme Bank reported its CET1 ratio of 13.1%.\n"
NEWS = b"# Markets wrap\n\nPublished 2026-08-05.\n\nAcme Bank said its CET1 ratio was 13.4%.\n"


@pytest.fixture
def lake(tmp_path):
    store = SQLiteLake(tmp_path / "lake")
    yield store
    store.close()


def ingest(lake, r, data: bytes, name: str, **meta) -> dict:
    ing = Ingestor(lake, HashingEmbedder(), clock=lambda: NOW)
    res = ing.ingest_file("acme", data, name, world_view_of(r.controller.engine.wm.graph), **meta)
    assert res.bundle is not None
    return res.bundle.bundle


def test_a_well_attributed_figure_applies_and_a_news_item_without_a_publisher_waits(tmp_path, lake):
    r = runner(MemoryBackend())
    filing = ingest(lake, r, FILING, "results.md", source="Synthetic IR", source_type="filing")
    (fi,) = filing["items"]
    assert (fi["basis"], fi["coverage"], fi["plausible"]) == ("direct", "full", True) and fi["document"]
    news = ingest(lake, r, NEWS, "wrap.md", source="Synthetic wire", source_type="news")
    (ni,) = news["items"]
    assert ni["publisher"] == "" and ni["basis"] == "proxy"

    r.import_items(filing)
    assert not r.controller.pending_proposals() and decisions_by(r) == ["policy:standards"]
    assert r.imported[f"IM-{fi['id']}"].document == fi["document"]            # the item reached the gate whole

    r.import_items(news)
    (waiting,) = r.controller.pending_proposals()
    assert "third-party material without its publisher (R21)" in waiting.review_reasons
    assert decisions_by(r) == ["policy:standards"]                            # only the filing was applied by the gate


def test_the_same_news_with_a_publisher_applies(tmp_path, lake):
    r = runner(MemoryBackend())
    news = ingest(lake, r, NEWS, "wrap.md", source="Synthetic wire", source_type="news",
                  meta={"hints": {"publisher": "Synthetic Wire Service"}})
    (item,) = news["items"]
    assert item["publisher"] == "Synthetic Wire Service" and item["basis"] == "proxy"
    r.import_items(news)
    assert not r.controller.pending_proposals() and decisions_by(r) == ["policy:standards"]
