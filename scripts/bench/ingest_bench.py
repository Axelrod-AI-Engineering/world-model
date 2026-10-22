"""Benchmark ingestion on a corpus: speed per stage, and extraction against a gold set (axelrod_wm.ingest.bench).

Each file is ingested the way an upload is: its bytes and its file name, nothing else, against the scenario's model.
The report, the scores, and every prediction (for labelling) are written to --out, which for a client's corpus must
stay inside that client's gitignored folder.

    uv run python scripts/bench/ingest_bench.py --corpus data/sources/sally --scenario sally_demo \
        --items data/work/sally/_bundle_parts --gold data/work/sally/bench/gold.json \
        --labels data/work/sally/bench/labels.json --out data/work/sally/bench

Files are found under --corpus (recursively, or only under --dirs; zips and the bench folder itself are skipped)
unless --files lists them. For Sally's corpus: --dirs unpacked/sell_side spreadsheets.
Gold paths are relative to --corpus.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

from axelrod_wm.ingest.bench import label_key, load_gold, negatives, only_split, report, score, timing
from axelrod_wm.ingest.parse import supported

SKIP_DIRS = {"bench", "_bundle_parts", "days", "exports", "agentic_walkthroughs_emily"}


def corpus_files(root: Path, dirs: list[str] | None = None) -> list[Path]:
    out = []
    found = [p for d in (dirs or ["."]) for p in (root / d).rglob("*")]
    for p in sorted(set(found)):
        rel = p.relative_to(root)
        if p.is_file() and not (set(rel.parts[:-1]) & SKIP_DIRS) and not p.name.startswith(".") \
                and supported(p.name):
            out.append(p)
    return out


def load_world(scenario: str):
    import yaml

    from axelrod_wm.repo.snapshots import MemoryBackend
    from axelrod_wm.sim.runner import build_runner

    r = build_runner(scenario, interactive=True, storage=MemoryBackend(), record_checklist=False)
    r.load()
    wd = r.controller.world_dir()
    templates = Path(wd) / "templates.yaml" if wd is not None else None
    inverted: frozenset[str] = frozenset()
    if templates is not None and templates.exists():
        subjects = (yaml.safe_load(templates.read_text()) or {}).get("subjects", [])
        inverted = frozenset(s["pattern"] for s in subjects if s.get("invert"))
    return r.controller.engine.wm.graph, inverted


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--corpus", type=Path, required=True)
    ap.add_argument("--scenario", default="sally_demo")
    ap.add_argument("--items", type=Path, help="folder of bundle-part JSON files ({items: [...]}) holding the gold items")
    ap.add_argument("--gold", type=Path, help="gold annotations (item_id, files, per-signal verdicts)")
    ap.add_argument("--labels", type=Path, help="labels for predictions: {label_key: correct|incorrect}")
    ap.add_argument("--files", nargs="*", type=Path, help="only these files (paths under --corpus)")
    ap.add_argument("--dirs", nargs="*", help="only files under these folders of --corpus")
    ap.add_argument("--embedder", default="hashing", choices=["hashing", "fastembed"])
    ap.add_argument("--split", default="dev", choices=["dev", "test", "all"],
                    help="score on this split of the documents (tune on dev; report test only at the end)")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)

    from axelrod_wm.ingest.pipeline import Ingestor
    from axelrod_wm.lake.embed import embedder_from_env
    from axelrod_wm.lake.sqlite import SQLiteLake

    graph, inverted = load_world(a.scenario)
    files = [a.corpus / f.relative_to(a.corpus) if f.is_absolute() else f for f in a.files] if a.files \
        else corpus_files(a.corpus, a.dirs)
    lake = SQLiteLake(Path(tempfile.mkdtemp(prefix="ingest-bench-")))
    ing = Ingestor(lake, embedder_from_env({"WORLD_MODEL_EMBEDDER": a.embedder}), inverted=inverted)
    predictions: dict[str, list[dict]] = {}
    rows, failures = [], []
    t0 = time.perf_counter()
    for k, path in enumerate(files, 1):
        rel = str(path.relative_to(a.corpus))
        data = path.read_bytes()
        res = ing.ingest_file("bench", data, path.name, graph)
        sigs = [s for item in (res.bundle.bundle["items"] if res.bundle else []) for s in item["signals"]]
        predictions[rel] = sigs
        rows.append({"file": rel, "bytes": len(data), "pages": int(res.document.meta.get("pages", 0) or 0),
                     "timings": res.timings, "status": res.document.status, "chunks": res.chunks,
                     "signals": len(sigs)})
        if res.document.status == "failed":
            failures.append({"file": rel, "error": res.document.error})
        print(f"[{k}/{len(files)}] {sum(res.timings.values()):6.2f}s {len(sigs):3d} signals  {rel[:100]}",
              file=sys.stderr, flush=True)
    wall = time.perf_counter() - t0

    gold, controls = [], {}
    if a.items and a.gold:
        items = [i for p in sorted(a.items.glob("*.json")) for i in json.loads(p.read_text())["items"]]
        notes = json.loads(a.gold.read_text())
        gold = load_gold(items, notes)
        controls = negatives(predictions, notes)
    labels = json.loads(a.labels.read_text()) if a.labels and a.labels.exists() else {}
    sc = score(*only_split(predictions, gold, a.split), labels)
    tm = timing(rows)
    tm["wall_seconds"] = round(wall, 2)
    a.out.mkdir(parents=True, exist_ok=True)
    text = report(sc, tm, title=f"Ingestion benchmark: {a.corpus.name} on {a.scenario}, {a.split} split",
                  controls=controls)
    if failures:
        text += "\n## Failed documents\n\n" + "\n".join(f"- {f['file']}: {f['error']}" for f in failures) + "\n"
    (a.out / "report.md").write_text(text)
    (a.out / "results.json").write_text(json.dumps({
        "recall": sc.recall, "location_recall": sc.location_recall, "precision": sc.precision, "f1": sc.f1,
        "counted": sc.counted, "found": sc.found, "predicted": sc.predicted, "correct": sc.correct,
        "incorrect": sc.incorrect, "unlabelled": sc.unlabelled, "by_type": sc.by_type,
        "out_of_reach": dict(sc.out_of_reach), "negative_controls": controls, "timing": tm, "documents": rows, "misses": sc.misses}, indent=1))
    (a.out / "predictions.json").write_text(json.dumps(
        [{"key": label_key(f, s), "file": f, "signal": s, "label": labels.get(label_key(f, s))}
         for f in sorted(predictions) for s in predictions[f]], indent=1, ensure_ascii=False))
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
