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

from axelrod_wm.ingest.pipeline import Ingestor, bundle_id
from axelrod_wm.lake.embed import HashingEmbedder
from axelrod_wm.lake.sqlite import SQLiteLake
from axelrod_wm.lake.store import canonical_json, digest
from tests.ingest.builders import docx, para, pdf, pptx, xlsx
from tests.ingest.conftest import NOW, acme_graph, acme_inverted

T = "desk"
ROOT = Path(__file__).resolve().parents[2]

POLICY = ("The central bank raised its policy rate by 25bp to 4.25%. Government bonds 10Y yield rose 10bp, and the dollar "
          "index rose 2%. Higher government bonds 10Y yield lifts Acme Re domestic P&C profit.")
BANKS = ("Acme Bank's net interest income rose 4% in Q3. Delta net interest income was $64 billion. "
         "The central bank policy rate weighs on Acme Bank net interest income.")


def documents() -> dict[str, bytes]:
    """The corpus, built once: several formats, each with claims of several kinds."""
    return {
        "policy_2026-10-05.md": f"# Policy watch\n\n{POLICY}\n\n- Crude oil price lifts Ridge Energy operating profit.\n".encode(),
        "banks.html": (f"<html><head><title>Banks</title><script>Crude oil price fell 9%.</script></head><body>"
                       f"<p>{BANKS}</p><table><tr><td>Crude oil price</td><td>rose 3%</td></tr></table></body></html>"
                       ).encode(),
        "memo.docx": docx(para("Desk memo, 5 Oct 2026") + para("A 25bp cut in the central bank policy rate.", "\n",
                                                                  "Higher freight rates lift credit spreads.")),
        "rates.xlsx": xlsx({"Levels": [["Value", "Level"], ["Central bank policy rate at", "4.25%"],
                                       ["Core inflation rose", "0.3 percentage points"]],
                            "Notes": [["Dollar index fell to 104."], [None], ["Crude oil price hit $95."]]}),
        "wire.txt": "Ridge Energy operating profit reached $6.5 billion.\nThe dollar weakened.\n".encode("utf-16"),
        "deck.pptx": pptx({2: ["Delta net interest income rose 3%."], 1: ["The central bank held rates at 4.25%."]}),
        "scan.pdf": pdf(["October 9, 2026", "Two-year yields jumped 15bp."]),
        "table.csv": b"series,unit,2026-09-30,2026-10-01\nCrude oil price,$/bbl,94,95\nDollar index,index,104,105\n",
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
        ing = Ingestor(lake, HashingEmbedder(), clock=lambda: NOW, inverted=acme_inverted())
        results = ing.ingest_many(T, files, graph, source="Desk", source_type="broker_research")
        return snapshot(lake, results), [r.document.filename for r in results]
    finally:
        lake.close()


def run_dir(src: str, lake_dir: str) -> str:
    """For a fresh process: ingest every file in `src` (sorted) and print the snapshot as canonical JSON."""
    files = [(p.read_bytes(), p.name) for p in sorted(Path(src).iterdir())]
    snap, order = ingest_all(Path(lake_dir), files, acme_graph())
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
        assert a[name]["bundle_id"] == bundle_id(json.loads(a[name]["bundle"]))


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


def test_a_bundle_id_does_not_depend_on_when_it_was_read(corpus, graph, tmp_path, inverted):
    """Two lakes reading the same file a year apart: a dated file's bundles differ only in `collected_at`, and share an
    id. (An undated file is dated when it was read, so its items, and its id, differ.)"""
    ids = []
    for k, now in enumerate((NOW, NOW.replace(year=2027))):
        lake = SQLiteLake(tmp_path / f"lake{k}")
        try:
            ing = Ingestor(lake, HashingEmbedder(), clock=lambda now=now: now, inverted=inverted)
            ids.append({name: ing.ingest_file(T, data, name, graph).bundle for name, data in corpus.items()})
        finally:
            lake.close()
    same = 0
    for name in corpus:
        a, b = ids[0][name], ids[1][name]
        assert a.bundle["collected_at"] != b.bundle["collected_at"]
        content = {**a.bundle, "collected_at": None} == {**b.bundle, "collected_at": None}
        assert (a.id == b.id) is content, name
        same += content
    assert same >= 3                                    # the dated files: policy_2026-10-05.md, memo.docx, scan.pdf, ...


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
    # Sep 30 (the table's first column), then Oct 5 (by id), then Oct 9
    assert order[0] == "table.csv" and set(order[1:3]) == {"policy_2026-10-05.md", "memo.docx"} and order[3] == "scan.pdf"


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
