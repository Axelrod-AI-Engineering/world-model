"""Determinism, the bar the ingestion is held to: the same file and the same world model always give byte-identical
text, chunks, mentions, embeddings, and bundles, whichever lake, order, process, or hash seed reads them."""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

from axelrod_wm.ingest.pipeline import Ingestor
from axelrod_wm.lake.embed import HashingEmbedder
from axelrod_wm.lake.sqlite import SQLiteLake
from axelrod_wm.lake.store import canonical_json, digest
from tests.ingest.builders import docx, para, pdf, pptx, xlsx
from tests.ingest.conftest import NOW, sally_graph, sally_inverted

T = "desk"
ROOT = Path(__file__).resolve().parents[2]

BOJ = ("The BoJ raised its policy rate by 25bp to 1.25%. JGB yields rose 10bp, and Bund yields rose 10bp. "
       "The yen strengthened 2%. Higher JGB yields lift Tokio Marine Japan P&C profit.")
BANKS = ("JPMorgan's net interest income rose 4% in Q3. Citi net interest income was $64 billion. "
         "The Fed rate weighs on JPMorgan net interest income.")


def documents() -> dict[str, bytes]:
    """The corpus, built once: several formats, each with claims of several kinds."""
    return {
        "boj_2026-10-05.md": f"# BoJ watch\n\n{BOJ}\n\n- Brent crude lifts Komatsu operating profit.\n".encode(),
        "banks.html": (f"<html><head><title>US banks</title><script>Brent fell 9%.</script></head><body>"
                       f"<p>{BANKS}</p><table><tr><td>Brent crude</td><td>rose 3%</td></tr></table></body></html>"
                       ).encode(),
        "memo.docx": docx(para("Desk memo, 5 Oct 2026") + para("A 25bp cut in the ECB deposit rate.", "\n",
                                                                  "Lower Bund yields lift European stocks.")),
        "rates.xlsx": xlsx({"Levels": [["Value", "Level"], ["BoJ policy rate at", "1.25%"],
                                       ["US core CPI rose", "0.3 percentage points"]],
                            "Notes": [["USD/JPY fell to ¥152."], [None], ["Brent crude hit $95."]]}),
        "wire.txt": "Toyota operating profit reached ¥3.5 trillion.\nThe yen weakened.\n".encode("utf-16"),
        "deck.pptx": pptx({2: ["UniCredit net interest income rose 3%."], 1: ["ECB held rates at 2.25%."]}),
        "scan.pdf": pdf(["October 9, 2026", "UST 2Y yields jumped 15bp."]),
        "table.csv": b"name,move\nBrent crude rose,2%\nTOPIX,fell 1%\n",
    }


def snapshot(lake: SQLiteLake, results) -> dict:
    """Everything the lake holds for each document, as JSON."""
    out = {}
    for r in results:
        d = r.document.id
        out[r.document.filename] = {
            "document": r.document.model_dump(mode="json"),
            "text": lake.get_text(T, d),
            "chunks": [c.model_dump(mode="json") for c in lake.get_chunks(T, d)],
            "mentions": [m.model_dump(mode="json") for m in lake.mentions_of(T, doc_id=d)],
            "embeddings": digest([e for e in lake.embeddings(T, "hashing-256") if e[0] == d]),
            "bundle_id": r.bundle.id,
            "bundle": canonical_json(r.bundle.bundle),
            "counts": [r.chunks, r.mentions, r.signals, r.llm_signals, r.warnings],
        }
    return out


def ingest_all(lake_dir: Path, files: list[tuple[bytes, str]], graph) -> tuple[dict, list[str]]:
    lake = SQLiteLake(lake_dir)
    try:
        ing = Ingestor(lake, HashingEmbedder(), clock=lambda: NOW, inverted=sally_inverted())
        results = ing.ingest_many(T, files, graph, source="Desk", source_type="broker_research")
        return snapshot(lake, results), [r.document.filename for r in results]
    finally:
        lake.close()


def run_dir(src: str, lake_dir: str) -> str:
    """For a fresh process: ingest every file in `src` (sorted) and print the snapshot as canonical JSON."""
    files = [(p.read_bytes(), p.name) for p in sorted(Path(src).iterdir())]
    snap, order = ingest_all(Path(lake_dir), files, sally_graph())
    return canonical_json({"snapshot": snap, "order": order})


@pytest.fixture(scope="module")
def corpus() -> dict[str, bytes]:
    return documents()


def test_every_document_yields_claims(corpus, graph, tmp_path):
    snap, _ = ingest_all(tmp_path / "a", [(b, n) for n, b in corpus.items()], graph)
    for name, s in snap.items():
        bundle = json.loads(s["bundle"])
        assert bundle["items"], name
        assert s["document"]["status"] == "extracted" and s["chunks"] and s["mentions"], name
    types = {sig["type"] for s in snap.values() for i in json.loads(s["bundle"])["items"] for sig in i["signals"]}
    assert types == {"observe", "move", "support", "contradict", "link"}


def test_two_fresh_lakes_give_byte_identical_results(corpus, graph, tmp_path):
    files = [(b, n) for n, b in corpus.items()]
    a, order_a = ingest_all(tmp_path / "a", files, graph)
    b, order_b = ingest_all(tmp_path / "b", files, graph)
    assert canonical_json(a) == canonical_json(b) and order_a == order_b
    for name in corpus:
        assert a[name]["bundle_id"] == digest(json.loads(a[name]["bundle"]))[:24]


def test_reingesting_the_same_bytes_is_not_new_and_gives_the_same_bundle(corpus, graph, tmp_path, inverted):
    lake = SQLiteLake(tmp_path / "lake")
    try:
        first = Ingestor(lake, HashingEmbedder(), clock=lambda: NOW, inverted=inverted)
        later = Ingestor(lake, HashingEmbedder(), clock=lambda: NOW.replace(year=2027), inverted=inverted)
        for name, data in corpus.items():
            a = first.ingest_file(T, data, name, graph)
            b = later.ingest_file(T, data, f"copy-of-{name}", graph)
            assert a.new and not b.new
            assert b.document == a.document and b.bundle == a.bundle
            assert canonical_json(b.bundle.bundle) == canonical_json(a.bundle.bundle)
        assert len(lake.list_documents(T)) == len(corpus)
    finally:
        lake.close()


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_shuffled_batches_give_the_same_bundles_and_order(corpus, graph, tmp_path, seed):
    files = [(b, n) for n, b in corpus.items()]
    base, order = ingest_all(tmp_path / "base", files, graph)
    shuffled = files[:]
    random.Random(seed).shuffle(shuffled)
    assert shuffled != files
    snap, order2 = ingest_all(tmp_path / f"s{seed}", shuffled, graph)
    assert order2 == order
    assert canonical_json(snap) == canonical_json(base)


def test_event_time_order_is_by_date_then_id(corpus, graph, tmp_path):
    snap, order = ingest_all(tmp_path / "a", [(b, n) for n, b in corpus.items()], graph)
    keys = [(snap[n]["document"]["event_time"], snap[n]["document"]["id"]) for n in order]
    assert keys == sorted(keys)
    assert set(order[:2]) == {"boj_2026-10-05.md", "memo.docx"} and order[2] == "scan.pdf"    # Oct 5 (by id), Oct 9


def test_same_bundle_in_fresh_processes_with_different_hash_seeds(corpus, graph, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    for name, data in corpus.items():
        (src / name).write_bytes(data)
    inproc = run_dir(str(src), str(tmp_path / "inproc"))
    outs = []
    for k, seed in enumerate(("0", "4242")):
        env = {**os.environ, "PYTHONHASHSEED": seed, "WORLD_MODEL_EMBEDDER": "hashing"}
        env.pop("WORLD_MODEL_LLM_PROVIDER", None)
        code = ("import sys; from tests.ingest.test_determinism import run_dir; "
                "sys.stdout.write(run_dir(sys.argv[1], sys.argv[2]))")
        proc = subprocess.run([sys.executable, "-c", code, str(src), str(tmp_path / f"proc{k}")], cwd=ROOT, env=env,
                              capture_output=True, text=True, timeout=300, check=True)
        outs.append(proc.stdout)
    assert outs[0] == outs[1] == inproc
    ids = {n: s["bundle_id"] for n, s in json.loads(inproc)["snapshot"].items()}
    assert len(set(ids.values())) == len(corpus)
