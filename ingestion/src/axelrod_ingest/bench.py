"""Benchmarks for ingestion (Oct 17): how fast each stage runs, and how well extraction recovers a gold set.

**Gold.** A gold signal is a claim a careful reader took from one source document (an `axelrod.import/v1` signal
plus the file it came from and a verdict on whether the file states it). Only signals the file states and that live in
text a parser can read (a sentence or a table row) count toward recall. Claims found only in a chart, or inferred
across sentences, are reported separately, as out of reach for a rule-based reader.

**Matching.** A predicted signal *agrees* with a gold signal from the same file when:
- **observe:** the same value, at a level within tolerance (`REL_TOL` of the gold level, or `ABS_TOL`);
- **move:** the same value, in the same direction (sizes differ legitimately between modes and readers);
- **support, contradict, link:** the same two ends; a support and a new link both say "this channel holds", so they
  agree with each other, and a contradiction agrees only with a contradiction.

It is *located* when only the value (or the pair of ends) matches: the reader found the right place but read it
differently. Each gold signal is matched at most once.

**Precision.** A prediction that agrees with a gold signal is correct. Other predictions are judged through a labels
file (correct or incorrect, by `label_key`), because the gold set is a selection, not every claim in the corpus.
Unlabelled predictions are counted, not guessed.

**Timing.** Seconds per stage per document (`IngestResult.timings`), summarized as totals, means, and p50/p95, with
throughput in documents, pages, and megabytes per second.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

TEST_SHARE = 3          # one document in three (by the hash of its path) is held out as the test split
REL_TOL = 0.02          # an observed level within 2% of the gold level agrees
ABS_TOL = 0.051         # or within 0.05 in its unit (a rate quoted as 4.8 vs 4.85)
COUNTED = ("sentence", "table")
TYPES = ("observe", "move", "support", "contradict", "link")


@dataclass(frozen=True)
class GoldSignal:
    item_id: str
    index: int
    signal: Mapping[str, Any]
    files: tuple[str, ...]
    verdict: str = "supported"          # supported | partly | unsupported
    extractable: str = "sentence"       # sentence | table | chart_only | inference

    @property
    def counted(self) -> bool:
        """Whether this signal counts toward recall: stated by its file, in text a parser reads."""
        return self.verdict != "unsupported" and self.extractable in COUNTED and bool(self.files)


def ends(sig: Mapping[str, Any]) -> tuple[str, ...]:
    """What a signal is about: its value, or its two ends."""
    if sig["type"] in ("observe", "move"):
        return (sig["value_of"],)
    return (sig["source"], sig["target"])


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


def agrees(pred: Mapping[str, Any], gold: Mapping[str, Any]) -> bool:
    if ends(pred) != ends(gold):
        return False
    t, g = pred["type"], gold["type"]
    if g == "observe":
        return t == "observe" and abs(pred["value"] - gold["value"]) <= max(ABS_TOL, REL_TOL * abs(gold["value"]))
    if g == "move":
        return t == "move" and _sign(pred["delta"]) == _sign(gold["delta"]) != 0
    if g == "contradict":
        return t == "contradict"
    return t in ("support", "link")


def located(pred: Mapping[str, Any], gold: Mapping[str, Any]) -> bool:
    return ends(pred) == ends(gold)


def label_key(file: str, sig: Mapping[str, Any]) -> str:
    """A stable key for a predicted signal, to label it once and keep the label across runs."""
    body = json.dumps({"file": file, "type": sig["type"], "ends": ends(sig), "quote": sig.get("quote", "")},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def split_of(file: str) -> str:
    """"dev" or "test", fixed by the file's path: tune on dev, report on test, so rules are not fit to what they are
    judged on."""
    return "test" if int(hashlib.sha256(file.encode()).hexdigest(), 16) % TEST_SHARE == 0 else "dev"


def only_split(predictions: Mapping[str, list], gold: list[GoldSignal], split: str) -> tuple[dict, list[GoldSignal]]:
    """The predictions and gold signals of one split ("all" keeps everything); a gold signal belongs to its first
    file's split."""
    if split == "all":
        return dict(predictions), list(gold)
    return ({f: p for f, p in predictions.items() if split_of(f) == split},
            [g for g in gold if g.files and split_of(g.files[0]) == split])


def negatives(predictions: Mapping[str, list], annotations: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Predictions from negative controls: files an annotator found no claim in (`"negative_control": true`), so
    whatever is read from them is a false positive."""
    files = {f for a in annotations if a.get("negative_control") for f in a.get("files", [])}
    return {f: len(predictions.get(f, [])) for f in sorted(files)}


def load_gold(items: Iterable[Mapping[str, Any]], annotations: Iterable[Mapping[str, Any]]) -> list[GoldSignal]:
    """Gold signals from bundle items and their annotations ({item_id, files, signals: [{index, verdict, extractable}]}).
    An item with no annotation keeps no file, so it does not count toward recall."""
    notes = {a["item_id"]: a for a in annotations}
    out = []
    for item in sorted(items, key=lambda i: i["id"]):
        note = notes.get(item["id"], {})
        per = {s["index"]: s for s in note.get("signals", [])}
        for k, sig in enumerate(item["signals"]):
            s = per.get(k, {})
            out.append(GoldSignal(item["id"], k, sig, tuple(note.get("files", [])),
                                  s.get("verdict", "supported"), s.get("extractable", "sentence")))
    return out


@dataclass
class Score:
    counted: int = 0
    found: int = 0
    located: int = 0
    by_type: dict[str, list[int]] = field(default_factory=dict)       # type -> [counted, found]
    by_verdict: dict[str, list[int]] = field(default_factory=dict)    # supported | partly -> [counted, found]
    out_of_reach: Counter = field(default_factory=Counter)             # why gold signals were not counted
    predicted: int = 0
    correct: int = 0
    incorrect: int = 0
    unlabelled: int = 0
    misses: list[dict] = field(default_factory=list)                   # counted gold signals not found
    errors: list[dict] = field(default_factory=list)                   # predictions labelled incorrect

    @property
    def recall(self) -> float:
        return self.found / self.counted if self.counted else 1.0

    @property
    def location_recall(self) -> float:
        return self.located / self.counted if self.counted else 1.0

    @property
    def precision(self) -> float:
        judged = self.correct + self.incorrect
        return self.correct / judged if judged else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


def score(predictions: Mapping[str, list[Mapping[str, Any]]], gold: list[GoldSignal],
          labels: Mapping[str, str] | None = None) -> Score:
    """`predictions`: the signals extracted from each file (by the same relative path the gold uses)."""
    labels = labels or {}
    sc = Score()
    used: set[tuple[str, int]] = set()
    for g in gold:
        if not g.counted:
            reason = "unsupported" if g.verdict == "unsupported" else "no file" if not g.files else g.extractable
            sc.out_of_reach[reason] += 1
            continue
        t = g.signal["type"]
        sc.counted += 1
        sc.by_type.setdefault(t, [0, 0])[0] += 1
        sc.by_verdict.setdefault(g.verdict, [0, 0])[0] += 1
        cands = [(f, k, p) for f in g.files for k, p in enumerate(predictions.get(f, []))]
        hit = next(((f, k) for f, k, p in cands if (f, k) not in used and agrees(p, g.signal)), None)
        if hit is not None:
            used.add(hit)
            sc.found += 1
            sc.located += 1
            sc.by_type[t][1] += 1
            sc.by_verdict[g.verdict][1] += 1
            continue
        if any(located(p, g.signal) for _, _, p in cands):
            sc.located += 1
        sc.misses.append({"item_id": g.item_id, "index": g.index, "signal": dict(g.signal), "files": list(g.files),
                          "near": [dict(p) for _, _, p in cands if located(p, g.signal)]})
    for f in sorted(predictions):
        for k, p in enumerate(predictions[f]):
            sc.predicted += 1
            if (f, k) in used:
                sc.correct += 1
                continue
            verdict = labels.get(label_key(f, p))
            if verdict == "correct":
                sc.correct += 1
            elif verdict == "incorrect":
                sc.incorrect += 1
                sc.errors.append({"file": f, "signal": dict(p)})
            else:
                sc.unlabelled += 1
    return sc


# -- timing --------------------------------------------------------------------------------------------------------------
def _pct(xs: list[float], q: float) -> float:
    """The q-quantile by nearest rank (exact on small samples, no interpolation)."""
    s = sorted(xs)
    return s[min(len(s) - 1, max(0, math.ceil(q * len(s)) - 1))]


def timing(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    """rows: {"bytes": int, "pages": int, "timings": {stage: seconds}} per document."""
    stages: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        for k, v in r["timings"].items():
            stages[k].append(v)
    per_doc = [sum(r["timings"].values()) for r in rows]
    total = sum(per_doc)
    out = {"documents": len(rows), "seconds": round(total, 3),
           "pages": sum(r.get("pages", 0) for r in rows), "megabytes": round(sum(r["bytes"] for r in rows) / 1e6, 3),
           "stages": {k: {"total": round(sum(v), 3), "mean": round(sum(v) / len(v), 4), "p50": round(_pct(v, 0.5), 4),
                          "p95": round(_pct(v, 0.95), 4), "share": round(sum(v) / total, 3) if total else 0.0}
                      for k, v in sorted(stages.items())}}
    out["per_document"] = {"p50": round(_pct(per_doc, 0.5), 4), "p95": round(_pct(per_doc, 0.95), 4),
                           "max": round(max(per_doc), 4)} if rows else {}
    out["throughput"] = ({"documents_per_s": round(len(rows) / total, 3), "pages_per_s": round(out["pages"] / total, 2),
                          "mb_per_s": round(out["megabytes"] / total, 3)} if total else {})
    return out


# -- the report ----------------------------------------------------------------------------------------------------------
def _fmt(sig: Mapping[str, Any]) -> str:
    t = sig["type"]
    if t == "observe":
        return f"observe {sig['value_of']} = {sig['value']:g}"
    if t == "move":
        return f"move {sig['value_of']} {sig['delta']:+g} ({sig.get('mode', 'absolute')})"
    return f"{t} {sig['source']} → {sig['target']}"


def report(sc: Score, tm: dict[str, Any], *, title: str = "Ingestion benchmark", misses: int = 25,
           controls: Mapping[str, int] | None = None) -> str:
    lines = [f"# {title}", "", "## Extraction", "",
             f"- **Recall** {sc.recall:.1%} ({sc.found} of {sc.counted} gold signals the files state in readable text)",
             f"- **Located** {sc.location_recall:.1%} (the right value or link, however it was read)",
             f"- **Precision** {sc.precision:.1%} ({sc.correct} correct, {sc.incorrect} incorrect, "
             f"{sc.unlabelled} unlabelled of {sc.predicted} predicted)",
             f"- **F1** {sc.f1:.3f}"]
    for v, (n, f) in sorted(sc.by_verdict.items(), reverse=True):
        lines.append(f"- Recall on gold the file states {'fully' if v == 'supported' else v}: {f / n:.1%} ({f} of {n})")
    if controls:
        lines.append(f"- Negative controls: {sum(controls.values())} signal(s) read from {len(controls)} file(s) that state no "
                     f"claim ({sum(1 for n in controls.values() if n)} with any)")
    lines.append("")
    if sc.by_type:
        lines += ["| Type | Gold | Found | Recall |", "|---|---:|---:|---:|"]
        for t in [x for x in TYPES if x in sc.by_type]:
            n, f = sc.by_type[t]
            lines.append(f"| {t} | {n} | {f} | {f / n:.0%} |")
        lines.append("")
    if sc.out_of_reach:
        lines.append("Not counted: " + ", ".join(f"{k} {v}" for k, v in sorted(sc.out_of_reach.items())) + ".")
        lines.append("")
    if tm.get("documents"):
        th = tm["throughput"]
        lines += ["## Speed", "",
                  f"{tm['documents']} documents, {tm['pages']} pages, {tm['megabytes']} MB in {tm['seconds']} s: "
                  f"{th.get('documents_per_s', 0)} documents/s, {th.get('pages_per_s', 0)} pages/s, "
                  f"{th.get('mb_per_s', 0)} MB/s. Per document p50 {tm['per_document']['p50']} s, "
                  f"p95 {tm['per_document']['p95']} s, max {tm['per_document']['max']} s.", "",
                  "| Stage | Total s | Share | Mean s | p50 s | p95 s |", "|---|---:|---:|---:|---:|---:|"]
        for k, v in sorted(tm["stages"].items(), key=lambda kv: -kv[1]["total"]):
            lines.append(f"| {k} | {v['total']} | {v['share']:.0%} | {v['mean']} | {v['p50']} | {v['p95']} |")
        lines.append("")
    if sc.misses:
        lines += [f"## Misses (first {min(misses, len(sc.misses))} of {len(sc.misses)})", ""]
        for m in sc.misses[:misses]:
            near = "; read as " + ", ".join(_fmt(n) for n in m["near"]) if m["near"] else ""
            lines.append(f"- {m['item_id']}#{m['index']}: {_fmt(m['signal'])}{near}")
        lines.append("")
    if sc.errors:
        lines += [f"## Incorrect predictions ({len(sc.errors)})", ""]
        lines += [f"- {e['file']}: {_fmt(e['signal'])}" for e in sc.errors]
        lines.append("")
    return "\n".join(lines)
