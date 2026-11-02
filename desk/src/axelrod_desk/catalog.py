"""What a build can choose from, read from the base model's world view (Nov 2): its companies, each company's metric
catalog, and named groups of companies.

A company's catalog is its own values, those of the rates, agencies and other non-company players its values link to
directly, and every market's, so a reader can tie "China NEV sales" in a BYD note to the market's own value. A figure joins a metric only
when it is exactly that metric; anything else keeps a label of its own.

Groups are the world view's sectors (every company with that sector), the focused scenarios over the base (each focus of
two or more covered companies), and any named in the settings.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

CODE = re.compile(r"\b(\d{4,6})\b")


class Catalog:
    def __init__(self, world_view: dict[str, Any], *, scenario_dirs: list[Path] = (), base: str = "unified",
                 groups: dict[str, list[str]] | None = None) -> None:
        wv = world_view.get("world_view", world_view)
        self.entities = {e["id"]: e for e in wv["entities"]}
        self.values = {v["id"]: v for v in wv["values"]}
        self.links = wv.get("links", [])
        self.companies = {k: e for k, e in sorted(self.entities.items()) if e.get("kind") == "company"}
        self.groups = self._groups(scenario_dirs, base, groups or {})

    @classmethod
    def load(cls, path: Path, **kw: Any) -> Catalog:
        return cls(json.loads(path.read_text(encoding="utf-8")), **kw)

    def company_list(self) -> list[dict[str, Any]]:
        return [{"id": k, "name": e.get("name", k), "sector": e.get("sector", ""), "region": e.get("region", ""),
                 "aliases": e.get("aliases", [])} for k, e in self.companies.items()]

    def related(self, company: str) -> list[str]:
        """The non-company entities whose values link directly to the company's, in id order."""
        own = set(self.entities[company].get("subentity_ids", []))
        owner = {sid: e["id"] for e in self.entities.values() for sid in e.get("subentity_ids", [])}
        out = set()
        for ln in self.links:
            for a, b in ((ln["source_id"], ln["target_id"]), (ln["target_id"], ln["source_id"])):
                if a in own and b in owner and self.entities[owner[b]].get("kind") != "company":
                    out.add(owner[b])
        return sorted(out)

    def metrics(self, company: str) -> list[dict[str, Any]]:
        """The company's values, then those of the players its values link to, then every market's (72 values in the
        unified model: a broker's market figures name markets the company's own values need not link to)."""
        rows = []
        markets = [k for k, e in sorted(self.entities.items()) if e.get("kind") == "market"]
        for eid in dict.fromkeys([company, *self.related(company), *markets]):
            for sid in self.entities[eid].get("subentity_ids", []):
                v = self.values.get(sid, {})
                rows.append({"metric_id": sid, "name": v.get("name", sid), "model_unit": v.get("unit", ""), "entity": eid})
        return rows

    def unit_of(self, metric_id: str) -> str:
        return (self.values.get(metric_id) or {}).get("unit", "")

    def _groups(self, dirs: list[Path], base: str, named: dict[str, list[str]]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        sectors: dict[str, list[str]] = {}
        for k, e in self.companies.items():
            if e.get("sector"):
                sectors.setdefault(e["sector"], []).append(k)
        for s, members in sorted(sectors.items()):
            out[f"sector:{s}"] = {"name": f"Sector: {s}", "companies": members}
        for d in dirs:
            for f in sorted(Path(d).glob("*/scenario.yaml")):
                spec = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
                focus = spec.get("focus") or {}
                members = [c for c in focus.get("companies", []) if c in self.companies]
                if focus.get("base") == base and len(members) >= 2:
                    name = (spec.get("context_pack") or {}).get("name") or spec.get("title") or spec["id"]
                    out[f"focus:{spec['id']}"] = {"name": name, "companies": members}
        for k, members in named.items():
            out[f"group:{k}"] = {"name": k, "companies": [c for c in members if c in self.companies]}
        return out

    def expand(self, companies: list[str], groups: list[str]) -> list[str]:
        """The covered companies a selection names, directly or through its groups, in id order."""
        unknown = [g for g in groups if g not in self.groups] + [c for c in companies if c not in self.companies]
        if unknown:
            raise ValueError(f"not in the catalog: {', '.join(unknown)}")
        return sorted(set(companies) | {c for g in groups for c in self.groups[g]["companies"]})

    def detect(self, *texts: str) -> str | None:
        """The company a document is about: the one whose names, aliases and codes it mentions most, when one leads."""
        scores = {}
        for k, e in self.companies.items():
            names = {n for n in [e.get("name", ""), *e.get("aliases", [])] if len(n) >= 3}
            codes = {m for n in e.get("aliases", []) for m in CODE.findall(n)}
            score = 0
            for weight, t in zip((5, *([1] * (len(texts) - 1))), texts):
                score += weight * sum(len(re.findall(rf"(?<![A-Za-z]){re.escape(n)}(?![A-Za-z])", t, re.I)) for n in names)
                score += weight * sum(len(re.findall(rf"(?<!\d){c}(?!\d)", t)) for c in codes)
            if score:
                scores[k] = score
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        if not ranked or (len(ranked) > 1 and ranked[1][1] * 2 > ranked[0][1]):
            return None
        return ranked[0][0]


__all__ = ["Catalog"]
