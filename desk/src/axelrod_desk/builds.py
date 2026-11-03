"""A build: a person's selection turned into world-model files (Nov 2).

A world model on the desk is a saved selection: companies and sector groups (expanded to companies), the source classes
whose documents go in (`company`, `sell_side`, `other`), and the switch that says whether approved figures are applied to
the model. A build of it:

1. **Facts.** The accepted figures of the selected companies' read documents in the chosen classes, resolved with the
   base model's own figures into facts (facts.py). A fact a person rejected stays out.
2. **Construction.** The base model's construction for those companies, copied, with each new fact added beside the
   baseline as an observation (never the selected baseline), its document as a source, and its other documents as further
   citations; a new document that repeats a base figure becomes another citation of that figure. Kinds are written in the
   wording the evaluation exporter reads (`wm_export.epistemic_of_observation`); a broker figure's view names its role in
   the note, so a note's own estimate, the consensus it quotes and the actual it restates stay apart. A rating, or a figure
   with no value, stays in the write-up and out of the files. A company with no construction yet (no repair.json) has no
   baseline, and its new figures are held out of the construction: they reach the model only through the switch.
3. **Bundles.** One import bundle per included document, dated by its publication, so folding them runs the model's clock
   to the newest one. With the switch on, each approved company-reported fact on a metric, in the metric's own unit, is an
   observation in its document's item, and the fold applies it; with the switch off the items carry no signals, so the
   fold moves the clock and nothing else.
4. **Exports.** A scenario focused on the companies, over the base scenario, and the world model's own export scripts:
   the v4.1.4 upload set (export_context.py) and the evaluation export (export_wm.py snapshot), each folding the bundles.
5. **Package.** The evaluation corpus (every page of every cited document), a summary, and one zip.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import zipfile
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from axelrod_desk.catalog import Catalog
from axelrod_desk.db import Db
from axelrod_desk.facts import Fact, resolve
from axelrod_desk.library import Library
from axelrod_desk.settings import Settings

EXPORT_KIND = {"company-reported actual": "reported actual", "company operating data": "reported actual (operating data)",
               "company capital action": "reported actual (capital action)",
               "company management statement": "reported actual (management statement)",
               "company guidance": "company guidance"}
SOURCE_TYPE = {"company": ("filing", "filing"), "sell_side": ("broker_research", "analyst"), "other": ("news", "news")}
PROOF = {"company": "company disclosure", "sell_side": "broker view, not a company disclosure",
         "other": "third-party material, not a company disclosure"}
DOCUMENT_WORD = {"company": "company disclosure", "sell_side": "broker note", "other": "third-party document"}
CONSTRUCTION_FILES = ("sources.json", "citations.json", "repair.json")
NOISE = re.compile(r"HTTP Request|testserver|HTTP/1\.1|StreamableHTTP|session manager|shutting down")


class BuildError(RuntimeError):
    pass


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "build"


def view_of(o: dict[str, Any], claim: str) -> str:
    kind = o.get("kind", "")
    if kind.startswith("company"):
        return "company"
    if kind.startswith("broker"):
        return "broker estimate before results" if claim == "estimate before results" else \
            {"broker estimate revision": "broker estimate"}.get(kind, kind)
    return "third party"


def unit_matches(a: str, b: str) -> bool:
    def n(u: str) -> str:
        return re.sub(r"\s+", "", u.lower().replace("per", "/"))
    return bool(a) and n(a) == n(b)


class Builder:
    def __init__(self, settings: Settings, db: Db, catalog: Catalog, library: Library, *,
                 run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> None:
        self.s, self.db, self.catalog, self.library, self.run_cmd = settings, db, catalog, library, run

    # -- the parts ------------------------------------------------------------------------------------------------------
    def records(self, companies: list[str], classes: list[str]) -> list[dict[str, Any]]:
        marks = lambda xs: ", ".join("?" for _ in xs)   # noqa: E731
        rows = self.db.all(
            f"select r.id, r.sha256, r.company, r.data, d.publisher, d.published, d.doc_type, d.filename, d.source_class "
            f"from records r join documents d on d.sha256 = r.sha256 where r.ok = 1 and d.status = 'read' "
            f"and r.company in ({marks(companies)}) and d.source_class in ({marks(classes)}) "
            f"and r.reading_id = (select max(id) from readings x where x.sha256 = r.sha256 and x.status = 'done')",
            [*companies, *classes])
        return [{**r, "observation": r.pop("data")} for r in rows]

    def baseline(self, companies: list[str]) -> list[dict[str, Any]]:
        out = []
        for co in companies:
            path = self.s.construction / co / "repair.json"
            rep = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}     # no construction yet: no baseline
            out += [{"company": co, "observation": o} for o in rep.get("observations", [])]
        return out

    def facts(self, companies: list[str], classes: list[str]) -> tuple[list[Fact], dict[str, str]]:
        reviews = {r["fact_key"]: r["decision"] for r in self.db.all("select fact_key, decision from reviews")}
        return resolve(self.records(companies, classes), self.baseline(companies)), reviews

    def _source(self, sha: str) -> tuple[str, dict[str, Any]]:
        d = self.library.get(sha)
        sid = f"desk.{sha[:12]}"
        return sid, {"file": str(self.library.path_of(sha, d["ext"])),
                     "kind": f"{DOCUMENT_WORD[d['source_class']]} ({d.get('publisher') or 'publisher not stated'}): "
                             f"{d.get('title') or d['filename']}",
                     "publisher": d.get("publisher"), "publication_date": d.get("published"), "period": d.get("period"),
                     "accounting_basis": None, "read_state": "read by the desk reader, every figure checked on its page",
                     "proof_limits": PROOF[d["source_class"]]}

    def _cite(self, c: dict[str, Any]) -> dict[str, Any]:
        d = self.library.get(c["sha256"])
        return {"source_id": f"desk.{c['sha256'][:12]}", "document": str(self.library.path_of(c["sha256"], d["ext"])),
                "location": f"PDF page {c['page']}", "page": c["page"], "quote": c["quote"]}

    def construction(self, out: Path, companies: list[str], facts: list[Fact], rejected: set[str],
                     records: dict[str, dict[str, Any]]) -> Counter:
        counts: Counter = Counter()
        for co in companies:                             # the three files the exporters read, not the folder's working files
            (out / co).mkdir(parents=True)
            for name in CONSTRUCTION_FILES:
                if (self.s.construction / co / name).exists():
                    shutil.copy2(self.s.construction / co / name, out / co / name)
        by_co: dict[str, list[Fact]] = {}
        for f in facts:
            by_co.setdefault(f.company, []).append(f)
        for co, fs in by_co.items():
            src_path, rep_path = out / co / "sources.json", out / co / "repair.json"
            if not rep_path.exists():
                # no construction for the company: the exporters have no node to put its figures beside, so they reach
                # the model only through the apply switch
                counts["held out (no construction for the company)"] += sum(
                    f.key not in rejected and any(not c.get("baseline") for c in f.citations) for f in fs)
                continue
            src, rep = json.loads(src_path.read_text()), json.loads(rep_path.read_text())
            inner = src["sources"] if isinstance(src.get("sources"), dict) else src
            obs = {o.get("observation_id"): o for o in rep["observations"]}
            for f in fs:
                new = [c for c in f.citations if not c.get("baseline")]
                if f.key in rejected:
                    counts["rejected"] += 1
                    continue
                if not new:
                    continue
                for c in new:
                    sid, s = self._source(c["sha256"])
                    inner.setdefault(sid, s)
                if f.baseline:
                    base = next(c for c in f.citations if c.get("baseline"))
                    o = obs[base["observation_id"]]
                    o["citations"] = [*o.get("citations", []), *(self._cite(c) for c in new)]
                    counts["citations added to base figures"] += len(new)
                    continue
                lead = records[new[0]["record_id"]]["observation"]
                if f.value is None:
                    counts["held out (no value)"] += 1
                    continue
                p = dict(f.period)
                rep["observations"].append({
                    "observation_id": "DESK_" + f.key[2:].upper(), "metric_id": f.metric_id, "label": f.label,
                    "period": {k: p.get(k) for k in ("label", "type", "start", "end")}, "value": f.value, "unit": f.unit,
                    "scope": {**(lead.get("scope") or {}), "view": view_of(lead, f.claim)},
                    "kind": EXPORT_KIND.get(lead["kind"], lead["kind"]), "available_at": new[0].get("published"),
                    "source": self._cite(new[0]), "citations": [self._cite(c) for c in new[1:]],
                    "raw": lead.get("raw"), "selected_baseline": False, "conflict": f.conflict,
                    **({"previous": lead["previous"]} if lead.get("previous") else {}),
                    **({"note": lead["note"]} if lead.get("note") else {})})
                counts["new figures"] += 1
                counts["conflicting figures"] += int(f.conflict)
            src_path.write_text(json.dumps(src, ensure_ascii=False, indent=1))
            rep_path.write_text(json.dumps(rep, ensure_ascii=False, indent=1))
        return counts

    def bundles(self, out: Path, docs: list[dict[str, Any]], facts: list[Fact], apply: bool,
                approved: set[str]) -> Counter:
        counts: Counter = Counter()
        signals: dict[str, list[dict[str, Any]]] = {}
        if apply:
            for f in facts:
                if f.key not in approved:
                    continue
                lead = next((c for c in f.citations if not c.get("baseline")), None)
                why = ("no new document" if lead is None else "not a company-reported figure"
                       if (f.speaker, f.claim) != ("company", "reported") else "no metric" if not f.metric_id
                       else "unit is not the metric's" if not unit_matches(f.unit, self.catalog.unit_of(f.metric_id))
                       else "")
                if why:
                    counts[f"approved, not applied: {why}"] += 1
                    continue
                signals.setdefault(lead["sha256"], []).append(
                    {"type": "observe", "value_of": f.metric_id, "value": f.value, "quote": lead["quote"],
                     "note": f"{f.label}, {f.period.get('label') or f.period.get('end')} (desk fact {f.key})"})
                counts["applied"] += 1
        out.mkdir(parents=True, exist_ok=True)
        for d in docs:
            st, kind = SOURCE_TYPE[d["source_class"]]
            day = d.get("published") or d["added_at"][:10]
            item = {"id": f"desk-{d['sha256'][:12]}", "published_at": f"{day}T00:00:00Z", "source": d.get("publisher") or "",
                    "source_type": st, "kind": kind, "headline": d.get("title") or d["filename"], "entities": [d["company"]],
                    "document": d["filename"], "publisher": d.get("publisher") or "",
                    "signals": signals.get(d["sha256"], [])}
            bundle = {"format": "axelrod.import/v1", "title": f"Desk: {d['filename']}", "collected_by": "axelrod desk",
                      "items": [item]}
            (out / f"{day}_{d['sha256'][:12]}.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=1))
        return counts

    def scenario(self, build_id: int, name: str, companies: list[str]) -> str:
        sid = f"desk_{build_id:04d}"
        folder = self.s.scenarios / "scenarios" / sid
        folder.mkdir(parents=True, exist_ok=True)
        spec = {"id": sid, "title": f"Desk build {build_id}: {name}",
                "focus": {"base": self.s.base_scenario, "companies": companies},
                "context_pack": {"domain_pack_id": f"PACK_DESK_{build_id:04d}", "name": f"Desk: {name}",
                                 "slug": f"desk_{slug(name)}", "file_index": self.s.pack_index, "edge_id_start": 60}}
        (folder / "scenario.yaml").write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
        return sid

    def corpus(self, path: Path, docs: list[dict[str, Any]], name: str) -> int:
        documents = []
        for i, d in enumerate(docs, 1):
            texts = self.library.pages(d["sha256"])
            documents.append({"document_id": f"D{i:03d}", "name": d["filename"], "sha256": d["sha256"],
                              "available_at": d.get("published"),
                              "pages": [{"page": k, "label": f"D{i:03d}-p{k}", "text": t} for k, t in enumerate(texts, 1)]})
        body = {"label": f"Desk: {name}", "company": ", ".join(sorted({d['company'] for d in docs})),
                "version": datetime.now(UTC).date().isoformat(), "documents": documents}
        path.write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n")
        return sum(len(d["pages"]) for d in documents)

    def export(self, label: str, cmd: list[str], log: Path) -> None:
        env = {**os.environ, "WORLD_MODEL_DATA_DIR": str(self.s.data),
               "WORLD_MODEL_CLIENT_DIR": os.pathsep.join([str(self.s.clients), str(self.s.scenarios)])}
        proc = self.run_cmd(cmd, cwd=self.s.repo, env=env, capture_output=True, text=True)
        text = "\n".join(ln for ln in f"{proc.stdout}\n{proc.stderr}".splitlines() if not NOISE.search(ln))
        log.write_text(text + "\n", encoding="utf-8")
        if proc.returncode:
            raise BuildError(f"the {label} failed (exit {proc.returncode}): {text[-1500:]}")

    # -- the whole build ------------------------------------------------------------------------------------------------
    def build(self, build_id: int, wm: dict[str, Any]) -> dict[str, Any]:
        companies = self.catalog.expand(wm["companies"], wm["groups"])
        if not companies:
            raise BuildError("the selection names no company")
        out = self.s.builds / f"{build_id:04d}"
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        facts, reviews = self.facts(companies, wm["classes"])
        rejected = {k for k, v in reviews.items() if v == "reject"}
        approved = {k for k, v in reviews.items() if v == "approve"}
        recs = {r["id"]: r for r in self.records(companies, wm["classes"])}
        counts = self.construction(out / "construction", companies, facts, rejected, recs)
        cited = sorted({c["sha256"] for f in facts if f.key not in rejected for c in f.citations if not c.get("baseline")})
        docs = sorted((self.library.get(s) for s in cited), key=lambda d: (d.get("published") or "", d["sha256"]))
        counts += self.bundles(out / "bundles", docs, facts, bool(wm["apply"]), approved - rejected)
        sid = self.scenario(build_id, wm["name"], companies)
        stamp = datetime.now(UTC).date().isoformat()
        folder = out / f"world_model_v4_1_4_axelrod_{self.s.pack_index}_desk_{slug(wm['name'])}_{stamp}"
        common = ["--days", str(out / "bundles"), "--construction-sources", str(out / "construction")]
        v4 = [*self.s.python, "world_model/scripts/imports/export_context.py", sid, str(folder), *common]
        if self.s.client_core:
            v4 += ["--client-core", str(self.s.client_core)]
        self.export("v4.1.4 export", v4, out / "export_v4.log")
        ev = [*self.s.python, "world_model/scripts/imports/export_wm.py", "snapshot", sid, str(out / "wm-export.json"),
              *common, "--world-model-id", f"desk-{build_id:04d}", "--label", wm["name"]]
        # the construction's data/ paths are the data folder's, whichever checkout the scripts run in (a worktree has none)
        for r in [*self.s.remaps, f"data/={self.s.data}/"]:
            ev += ["--remap", r]
        self.export("evaluation export", ev, out / "export_wm.log")
        pages = self.corpus(out / "corpus.json", docs, wm["name"])
        summary = {"world_model": wm["name"], "companies": companies, "classes": wm["classes"], "apply": bool(wm["apply"]),
                   "documents": len(docs), "corpus_pages": pages, "facts": len(facts),
                   "conflicts": sum(f.conflict for f in facts), "counts": dict(sorted(counts.items())),
                   "built_at": datetime.now(UTC).replace(microsecond=0).isoformat()}
        (out / "summary.json").write_text(json.dumps(summary, indent=1))
        zpath = out / f"{folder.name}.zip"
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(folder.rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(out))
            for name in ("wm-export.json", "corpus.json", "summary.json"):
                z.write(out / name, name)
        return {**summary, "zip": str(zpath), "out_dir": str(out)}


__all__ = ["EXPORT_KIND", "BuildError", "Builder", "slug", "unit_matches", "view_of"]
