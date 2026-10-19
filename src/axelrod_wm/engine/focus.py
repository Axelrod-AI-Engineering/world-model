"""A focused world (Oct 18): a scenario's world narrowed to some of its covered companies and the players they connect to.

A scenario declares `focus: {base: <scenario>, companies: [...]}` in its scenario.yaml (sim/scenario.py). It inherits
the base scenario's world, groups, theses, expected paths, and watchlist, each narrowed here:

- **Covered companies** are the entities with a construction file (construction/<entity>.yaml). Those outside the
  focus are dropped with every value, link, path, composition, identity, stock-flow, and matrix that names them.
- **Players kept** are the focus companies and every entity upstream of a focus value (any chain of links into it,
  through sources, moderators, and state values), or one link downstream of it. Every value of a kept entity stays,
  except a value a dropped company's construction file added to a shared entity, which stays only if it is itself
  upstream or one link downstream of a focus value.
- **Links and objects kept** are those whose every value is kept (a path also needs each step; a matrix both views).
- **Groups** keep their kept members and links; a group that held companies and keeps none is dropped, as is one left
  with fewer than two members. **Theses** keep their kept targets and groups; one whose shock names a dropped value,
  or that keeps no focus target, is dropped. **Expected paths** keep the chains, channels, and missing links whose
  every value is kept. The **taxonomy** lists only what remains.
- **Text.** A group or thesis whose text names a removed company (name, short name, or an alias of three or more
  characters) is dropped unless `overrides` rewrites it: `overrides: {<id>: {field: text}}` replaces fields of any
  entity, value, link, group, or thesis with that id. Other kept text that names a removed company is listed under
  `mentions` in the report.
- **Imports.** `narrow_bundle` drops an import item about a removed company and every signal on a value the world
  no longer has (sim/imports.py applies it to every import into a focused scenario).

`focus_result(spec)` computes all of it once per spec and set of file versions; `report()` gives the kept and dropped
counts by category."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from axelrod_wm.engine.initialize import REPO_ROOT, ConstructionError, read_construction, resolve_path

SCENARIOS_DIR = REPO_ROOT / "data" / "scenarios"
TEXT_FIELDS = ("name", "short", "description", "question", "note", "label", "caption")
SECTIONS = ("interactions", "paths", "compositions", "identities", "stock_flows", "matrices")


class FocusSpec(BaseModel):
    """scenario.yaml's `focus`: the scenario it narrows, the covered companies it keeps, and rewritten text."""

    model_config = ConfigDict(extra="forbid")

    base: str
    companies: list[str]
    overrides: dict[str, dict[str, str]] = {}


def _entity(sid: str) -> str:
    return sid.split(".", 1)[0]


def _value_refs(x: dict, key: str) -> list[str]:
    """Every value id an item of a construction section names."""
    if key == "interactions":
        refs = [x["source"], x["target"], *(p["moderator"] for p in x.get("parameters") or [])]
        for part in (x.get("state") or {}).values():
            if isinstance(part, dict) and part.get("value"):
                refs.append(part["value"])
        return refs
    if key == "compositions":
        return [x["total"], *x.get("members", []), *([x["residual"]] if x.get("residual") else []),
                *([x["eliminations"]] if x.get("eliminations") else [])]
    if key == "identities":
        return [x["target"], *x.get("factors", []), *x.get("numerator", []), *x.get("denominator", []),
                *([x["of"]] if x.get("of") else []), *x.get("minus", []), *(x.get("weights") or {})]
    if key == "stock_flows":
        return [x["stock"], *x.get("inflows", []), *x.get("outflows", [])]
    return [v for row in (x.get("cells") or {}).values() for v in row.values()]     # a matrix's cells


def _strings(x: Any) -> list[str]:
    if isinstance(x, str):
        return [x]
    if isinstance(x, dict):
        return [s for v in x.values() for s in _strings(v)]
    if isinstance(x, list):
        return [s for v in x for s in _strings(v)]
    return []


class FocusResult:
    """A focused world: the narrowed construction, groups, theses, expected paths, and watchlist, and the report."""

    def __init__(self, spec: FocusSpec) -> None:
        self.spec = spec
        base_dir = SCENARIOS_DIR / spec.base
        raw = yaml.safe_load((base_dir / "scenario.yaml").read_text()) or {}
        if raw.get("focus"):
            raise ConstructionError(f"focus base {spec.base!r} is itself a focused scenario")
        ini = raw.get("initialization") or {}
        self.base_dir = base_dir
        self.world_dir = resolve_path(ini["construction_dir"])
        self.seeds_path = resolve_path(ini["seeds"]) if ini.get("seeds") else None
        data, origin = read_construction(self.world_dir)
        self._base = data
        files = sorted(p.stem for p in (self.world_dir / "construction").glob("*.yaml"))
        ent_ids = {e["id"] for e in data["entities"]}
        self.covered = [f for f in files if f in ent_ids]
        unknown = [c for c in spec.companies if c not in self.covered]
        if unknown or not spec.companies:
            raise ConstructionError(f"focus companies must be covered companies of {spec.base} ({', '.join(self.covered)}): "
                                    f"{', '.join(unknown) or 'none given'}")
        self.focus = list(spec.companies)
        self.dropped_companies = [c for c in self.covered if c not in self.focus]
        self._names = self._removed_names(data)
        self._narrow_construction(data, origin)
        self._narrow_seeds()
        self._narrow_theses()
        self._narrow_expected_paths()

    # -- the world ------------------------------------------------------------------------------------------------
    def _narrow_construction(self, data: dict, origin: dict[str, str]) -> None:
        gone_co = set(self.dropped_companies)
        gone_files = set(self.dropped_companies)
        # a removed company's construction goes whole: its links too, even those between shared values
        live = [i for i in data["interactions"] if origin.get(i["id"]) not in gone_files
                and not any(_entity(v) in gone_co for v in _value_refs(i, "interactions"))]
        parents: dict[str, set[str]] = {}
        for i in live:
            parents.setdefault(i["target"], set()).update(v for v in _value_refs(i, "interactions") if v != i["target"])
        focus_values = {s["id"] for e in data["entities"] if e["id"] in self.focus for s in e.get("subentities") or []}
        focus_values |= {v for i in live for v in _value_refs(i, "interactions") if _entity(v) in self.focus}
        upstream: set[str] = set()
        todo = list(focus_values)
        while todo:
            for p in parents.get(todo.pop(), ()):
                if p not in upstream and p not in focus_values:
                    upstream.add(p)
                    todo.append(p)
        downstream = {i["target"] for i in live if i["target"] not in focus_values
                      and any(v in focus_values for v in _value_refs(i, "interactions"))}
        relevant = upstream | downstream
        ents = {e["id"]: e for e in data["entities"]}
        keep_ents = set(self.focus) | {_entity(v) for v in relevant if _entity(v) in ents}
        keep_ents -= gone_co
        self.entities = keep_ents
        self.added_values_dropped: set[str] = set()

        def keeps(sid: str) -> bool:
            return (_entity(sid) in keep_ents and sid not in self.added_values_dropped)

        out = {k: v for k, v in data.items()}
        out["entities"] = []
        for e in data["entities"]:
            if e["id"] not in keep_ents:
                continue
            e = dict(e)
            subs = []
            for s in e.get("subentities") or []:
                if origin.get(s["id"]) in gone_files and e["id"] not in self.focus and s["id"] not in relevant:
                    self.added_values_dropped.add(s["id"])
                else:
                    subs.append(s)
            e["subentities"] = subs
            out["entities"].append(e)
        kept_links = [i for i in live if all(keeps(v) for v in _value_refs(i, "interactions"))]
        out["identities"] = [x for x in data["identities"] if _entity(x["target"]) in keep_ents
                             and all(keeps(v) for v in _value_refs(x, "identities"))]
        out["stock_flows"] = [x for x in data["stock_flows"] if x["entity_id"] in keep_ents
                              and all(keeps(v) for v in _value_refs(x, "stock_flows"))]
        # a link that is an identity's or a stock-flow's term goes with it
        identity_ids = {x["id"] for x in [*out["identities"], *out["stock_flows"]]}
        out["interactions"] = [i for i in kept_links if not i.get("identity") or i["identity"] in identity_ids]
        ids = {i["id"] for i in out["interactions"]}
        out["compositions"] = [x for x in data["compositions"] if x["entity_id"] in keep_ents
                               and all(keeps(v) for v in _value_refs(x, "compositions"))]
        comp_ids = {x["id"] for x in out["compositions"]}
        out["matrices"] = [x for x in data["matrices"] if x["entity_id"] in keep_ents and x["rows"] in comp_ids
                           and x["columns"] in comp_ids and all(keeps(v) for v in _value_refs(x, "matrices"))]
        out["paths"] = [x for x in data["paths"] if x["entity_id"] in keep_ents and keeps(x["endpoint"])
                        and all(st["interaction_id"] in ids for st in x.get("steps") or [])]
        out["decision_variables"] = [v for v in data["decision_variables"] if keeps(v)]
        out["entity_link_labels"] = {k: v for k, v in (data.get("entity_link_labels") or {}).items()
                                     if all(p in keep_ents for p in k.split("->"))}
        self._apply_overrides(out["entities"])
        self._apply_overrides([s for e in out["entities"] for s in e.get("subentities") or []])
        for key in SECTIONS:
            self._apply_overrides(out[key])
        self.keeps_value = keeps
        self.interaction_ids = ids
        self._data = out
        self._counts = {}
        for key in SECTIONS:
            self._counts[key] = (len(out[key]), len(data[key]) - len(out[key]))
        self._dropped_ids = ({e["id"] for e in data["entities"]} - keep_ents) | \
            ({i["id"] for i in data["interactions"]} - ids)

    def construction(self) -> dict:
        """The narrowed construction data (ConstructionSpec.load validates it), a fresh copy each call."""
        return copy.deepcopy(self._data)

    def dropped_ids(self) -> list[str]:
        """Entities, links, and groups the focused world dropped: the taxonomy leaves them out."""
        return sorted(self._dropped_ids | set(self.groups_dropped))

    # -- groups ---------------------------------------------------------------------------------------------------
    def _narrow_seeds(self) -> None:
        raw = (yaml.safe_load(self.seeds_path.read_text()) or {}) if self.seeds_path else {}
        companies = {e["id"] for e in self._base["entities"] if e.get("kind") == "company"}
        kept: list[dict] = []
        self.groups_dropped: dict[str, str] = {}
        for p in raw.get("patterns") or []:
            members = [m for m in p["members"] if m in self.entities]
            had = any(m in companies for m in p["members"])
            if had and not any(m in companies for m in members):
                self.groups_dropped[p["id"]] = "its companies were all removed"
                continue
            if len(members) < 2:
                self.groups_dropped[p["id"]] = "fewer than two members remain"
                continue
            q = dict(p, members=members,
                     interactions=[i for i in p.get("interactions") or [] if i in self.interaction_ids],
                     absent_interactions=[i for i in p.get("absent_interactions") or [] if i in self.interaction_ids])
            self._apply_overrides([q])
            named = self._mentions(q, ("name", "description"))
            if named:
                self.groups_dropped[p["id"]] = f"its text names {', '.join(named)} (give it an override)"
                continue
            kept.append(q)
        ids = {p["id"] for p in kept}
        for q in kept:
            q["sub_patterns"] = [c for c in q.get("sub_patterns") or [] if c in ids]
            q["rivals"] = [c for c in q.get("rivals") or [] if c in ids]
        out = dict(raw, patterns=kept)
        out["super_interaction_labels"] = [d for d in raw.get("super_interaction_labels") or []
                                           if d.get("source") in ids and d.get("target") in ids]
        out["frontier_seeds"] = [f for f in raw.get("frontier_seeds") or []
                                 if self.keeps_value(f["earlier"]) and self.keeps_value(f["later"])]
        self.groups = ids
        self._seeds = out
        self._counts["groups"] = (len(kept), len(raw.get("patterns") or []) - len(kept))

    def seeds(self) -> dict:
        return copy.deepcopy(self._seeds)

    # -- theses and expected paths --------------------------------------------------------------------------------
    def _narrow_theses(self) -> None:
        p = self.base_dir / "theses.yaml"
        raw = (yaml.safe_load(p.read_text()) or {}) if p.exists() else {}
        kept, self.theses_dropped = [], {}
        for t in raw.get("theses") or []:
            ops = (t.get("event") or {}).get("ops") or []
            shocks = [((o.get("target") or {}).get("subentity_id")) for o in ops]
            t = copy.deepcopy(t)
            t["targets"] = [x for x in t.get("targets") or [] if self.keeps_value(x)]
            t["target_groups"] = [g for g in t.get("target_groups") or []
                                  if (g.get("ref") in self.groups if g.get("kind") == "superentity"
                                      else g.get("ref") in self.entities)]
            self._apply_overrides([t])
            named = self._mentions(t, ("question",))
            if any(s and not self.keeps_value(s) for s in shocks):
                self.theses_dropped[t["id"]] = "its shock is on a removed value"
            elif not any(_entity(x) in self.focus for x in t["targets"]):
                self.theses_dropped[t["id"]] = "no focus company is among its targets"
            elif named:
                self.theses_dropped[t["id"]] = f"its question names {', '.join(named)} (give it an override)"
            else:
                kept.append(t)
        self._theses = dict(raw, theses=kept, hypotheses=[])
        self.thesis_ids = {t["id"] for t in kept}
        self._counts["theses"] = (len(kept), len(raw.get("theses") or []) - len(kept))

    def theses(self) -> dict:
        return copy.deepcopy(self._theses)

    def _narrow_expected_paths(self) -> None:
        p = self.base_dir / "expected_paths.yaml"
        raw = (yaml.safe_load(p.read_text()) or {}) if p.exists() else {}
        out: dict[str, dict] = {}
        n = {"chains": [0, 0], "channels": [0, 0], "missing_links": [0, 0]}
        for tid, spec in (raw.get("theses") or {}).items():
            if tid not in self.thesis_ids:
                for k in n:
                    n[k][1] += len(spec.get(k) or [])
                continue
            s = dict(spec)
            for k, refs in (("chains", lambda c: c), ("channels", lambda c: [c["source"], c["target"]]),
                            ("missing_links", lambda c: [c["source"], c["target"]])):
                items = spec.get(k) or []
                s[k] = [c for c in items if all(self.keeps_value(v) for v in refs(c))]
                n[k][0] += len(s[k])
                n[k][1] += len(items) - len(s[k])
            s["outputs"] = {v: d for v, d in (spec.get("outputs") or {}).items() if self.keeps_value(v)}
            out[tid] = s
        self._expected = {**raw, "theses": out}
        for k, (a, b) in n.items():
            self._counts[f"expected {k}"] = (a, b)

    def expected_paths(self) -> dict:
        return copy.deepcopy(self._expected)

    def watchlist(self) -> dict | None:
        p = self.base_dir / "watchlist.yaml"
        raw = yaml.safe_load(p.read_text()) if p.exists() else None
        if not raw:
            return None
        return dict(raw, entities=[e for e in raw.get("entities") or [] if e in self.entities],
                    **({k: v for k, v in self.spec.overrides.get("watchlist", {}).items()}))

    # -- imports --------------------------------------------------------------------------------------------------
    def narrow_bundle(self, bundle: dict) -> tuple[dict, dict]:
        """An import bundle with the items about removed companies dropped and every signal on a removed value left
        out; returns the bundle and {items_dropped: [ids], signals_dropped: n, items_kept: n}."""
        gone = set(self.dropped_companies)
        tickers = {a for e in self._base["entities"] if e["id"] in gone for a in e.get("aliases") or []}
        items, dropped, signals = [], [], 0
        for it in bundle.get("items") or []:
            sig = it.get("signals") or []
            refs = [r for s in sig for r in (s.get("value_of"), s.get("source"), s.get("target")) if r]
            if (any(e in gone for e in it.get("entities") or []) or any(_entity(r) in gone for r in refs)
                    or any(t in tickers for t in it.get("tickers") or [])
                    or self._mentions(it, ("headline", "summary"))):
                dropped.append(it.get("id"))
                continue
            kept = [s for s in sig if all(self.keeps_value(r) for r in (s.get("value_of"), s.get("source"),
                                                                        s.get("target")) if r)]
            signals += len(sig) - len(kept)
            if sig and not kept:
                dropped.append(it.get("id"))
                continue
            items.append(dict(it, signals=kept, entities=[e for e in it.get("entities") or [] if e in self.entities]))
        return dict(bundle, items=items), {"items_dropped": dropped, "signals_dropped": signals, "items_kept": len(items)}

    # -- text -----------------------------------------------------------------------------------------------------
    def _removed_names(self, data: dict) -> list[tuple[str, re.Pattern]]:
        out = []
        for e in data["entities"]:
            if e["id"] in self.dropped_companies:
                for name in sorted({e["name"], e.get("short") or e["name"], *(e.get("aliases") or [])}):
                    if len(name) >= 3:
                        out.append((name, re.compile(rf"(?<![\w&]){re.escape(name)}(?![\w&])")))
        return out

    def _mentions(self, x: Any, fields: tuple[str, ...] | None = None) -> list[str]:
        texts = [x.get(f) or "" for f in fields] if fields and isinstance(x, dict) else _strings(x)
        return sorted({n for n, rx in self._names for t in texts if isinstance(t, str) and rx.search(t)})

    def _apply_overrides(self, items: list[dict]) -> None:
        for x in items:
            for k, v in self.spec.overrides.get(x.get("id"), {}).items():
                x[k] = v

    def mentions(self) -> dict[str, list[str]]:
        """Kept entities, values, and links whose text still names a removed company (worth an override)."""
        out = {}
        for e in self._data["entities"]:
            for x in [e, *(e.get("subentities") or [])]:
                n = self._mentions({k: x.get(k) for k in TEXT_FIELDS})
                if n:
                    out[x["id"]] = n
        for i in [x for key in SECTIONS for x in self._data[key]]:
            n = self._mentions(i)
            if n:
                out[i["id"]] = n
        return out

    def report(self) -> dict:
        """Kept and dropped counts by category, with what was dropped and why."""
        base = self._base
        kinds: dict[str, list[int]] = {}
        for e in base["entities"]:
            k = "covered companies" if e["id"] in self.covered else f"other {e.get('kind')}"
            kinds.setdefault(k, [0, 0])[0 if e["id"] in self.entities else 1] += 1
        n_values = sum(len(e.get("subentities") or []) for e in base["entities"])
        kept_values = sum(len(e.get("subentities") or []) for e in self._data["entities"])
        counts = {f"entities: {k}": tuple(v) for k, v in sorted(kinds.items())}
        counts["values (declared)"] = (kept_values, n_values - kept_values)
        counts.update(self._counts)
        return {"base": self.spec.base, "focus": self.focus, "dropped_companies": self.dropped_companies,
                "counts": {k: {"kept": a, "dropped": b} for k, (a, b) in counts.items()},
                "entities_kept": sorted(self.entities),
                "entities_dropped": sorted({e["id"] for e in base["entities"]} - self.entities),
                "added_values_dropped": sorted(self.added_values_dropped),
                "groups_dropped": self.groups_dropped, "theses_dropped": self.theses_dropped,
                "mentions": self.mentions()}


_CACHE: dict[str, tuple[tuple, FocusResult]] = {}


def _versions(spec: FocusSpec) -> tuple:
    d = SCENARIOS_DIR / spec.base
    raw = yaml.safe_load((d / "scenario.yaml").read_text()) or {}
    ini = raw.get("initialization") or {}
    world = resolve_path(ini.get("construction_dir", ""))
    files = [d / "scenario.yaml", *sorted(d.glob("*.yaml")), *sorted(world.glob("*.yaml")),
             *sorted((world / "construction").glob("*.yaml"))]
    if ini.get("seeds"):
        files.append(resolve_path(ini["seeds"]))
    return tuple((str(f), f.stat().st_mtime_ns) for f in files if Path(f).exists())


def focus_result(spec: FocusSpec | dict) -> FocusResult:
    """The focused world for a spec, computed once per spec and set of file versions."""
    spec = spec if isinstance(spec, FocusSpec) else FocusSpec.model_validate(spec)
    key = json.dumps(spec.model_dump(), sort_keys=True)
    ver = _versions(spec)
    hit = _CACHE.get(key)
    if hit is None or hit[0] != ver:
        hit = (ver, FocusResult(spec))
        _CACHE[key] = hit
    return hit[1]
