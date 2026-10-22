"""Find (Oct 9): semantic search and filtering over the graph, nodes and edges alike.

A query is free words and filters. Each word matches what an item is called and what it is: its name and aliases, its
kind and every kind above it in long-term memory ("airline" finds every airline; "firm" finds them too), its
categories, unit, and description; an interaction matches its label and the names of the values it joins. Words are
stemmed and a few economic synonyms are expanded ("rates" finds the policy rate, "prices" finds CPI). Filters narrow
the result:

    moved           a value at least 1 sd from normal (up / down for one direction)
    open>0.5        an open node above the share (what the graph does not explain yet)
    learned         an interaction the model learned (not given by construction)
    hedged          a soft interaction of a fuzzy end
    kind:airline    items of that kind (or any kind below it)

Every hit carries why it matched. Neighborhoods (one and two hops through interactions) are drawn by the client from
the hits' entities.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from axelrod_wm.control.controller import WorldModelController

CATEGORY_NAMES = {"SD": "spending demand", "MF": "money finance", "SC": "supply capacity energy commodities",
                  "DI": "distribution inequality", "DF": "foundations institutions regulation", "EN": "environment climate",
                  "EX": "expectations confidence", "SH": "shocks crises"}
SYNONYMS = {"rate": ["policy", "interest", "yield"], "interest": ["rate"], "price": ["cpi", "inflation", "cost"],
            "inflation": ["cpi", "price"], "cpi": ["inflation"], "oil": ["brent", "crude", "energy"], "crude": ["oil", "brent"],
            "energy": ["oil", "fuel"], "fuel": ["jet", "oil"], "fed": ["federal", "reserve", "central"],
            "central": ["fed", "reserve"], "bank": ["central", "reserve"], "profit": ["margin"], "margin": ["profit"],
            "stock": ["share", "equity"], "share": ["stock", "equity"], "demand": ["passenger", "spending", "travel"],
            "airline": ["air", "carrier"], "carrier": ["airline"], "fare": ["ticket", "price"]}
STOP = {"the", "a", "an", "of", "and", "or", "in", "on", "to", "for", "with", "what", "which", "show", "me", "find"}


def stem(w: str) -> str:
    w = w.lower()
    for suf in ("ations", "ation", "ings", "ing", "ies", "es", "s"):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


def words(text: str) -> set[str]:
    return {stem(w) for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in STOP}


def _filters(q: str) -> tuple[list[str], dict[str, Any]]:
    f: dict[str, Any] = {}
    free: list[str] = []
    for tok in q.split():
        t = tok.lower()
        if t in ("moved", "up", "down", "learned", "hedged"):
            f[t] = True
        elif m := re.fullmatch(r"open([<>])=?([0-9.]+)%?", t):
            v = float(m.group(2))
            f["open"] = (m.group(1), v / 100 if v > 1 else v)
        elif t.startswith("kind:"):
            f["kind"] = stem(t[5:])
        else:
            free.append(tok)
    return free, f


def find(ctl: WorldModelController, q: str, limit: int = 40) -> dict:
    from axelrod_wm.api.views import build_graph_view

    eng = ctl.engine
    g = eng.wm.graph
    view = build_graph_view(eng.wm, eng.ltm, ctl, eng.version)
    otax = eng.ltm.object_generalizations.taxonomy
    itax = eng.ltm.interaction_generalizations.taxonomy

    def path_names(tax: Any, gid: str | None) -> list[str]:
        out = []
        while gid and gid in tax.nodes:
            out.append(tax.nodes[gid].name)
            gid = tax.nodes[gid].parent_id
        return out

    free, flt = _filters(q)
    query = set()
    for w in free:
        sw = stem(w)
        if sw and sw not in STOP:
            query.add(sw)
    expanded = {w: {w, *(stem(x) for x in SYNONYMS.get(w, []))} for w in query}

    def score(fields: list[tuple[str, str, float]]) -> tuple[float, list[str]]:
        """fields: (label, text, weight). Every query word must match some field (a synonym counts for less)."""
        total = 0.0
        why: list[str] = []
        for w, alts in expanded.items():
            best = 0.0
            hit = None
            for label, text, weight in fields:
                ws = words(text)
                if w in ws:
                    s = weight
                elif alts & ws:
                    s = weight * 0.6
                elif any(x.startswith(w) for x in ws) and len(w) >= 3:
                    s = weight * 0.5
                else:
                    continue
                if s > best:
                    best, hit = s, label
            if best == 0.0:
                return 0.0, []
            total += best
            if hit and hit not in why:
                why.append(hit)
        return total, why

    ent_by = {e.id: e for e in view.entities}
    sub_by = {s.id: s for s in view.subentities}
    hits: list[dict] = []

    def kind_ok(names: list[str], extra: str = "") -> bool:
        if "kind" not in flt:
            return True
        return flt["kind"] in words(" ".join(names) + " " + extra)

    def open_ok(share: float) -> bool:
        if "open" not in flt:
            return True
        op, v = flt["open"]
        return share > v if op == ">" else share < v

    want_edges_only = flt.get("learned") or flt.get("hedged")
    for e in view.entities:
        ent = g.entities.get(e.id)
        kinds = path_names(otax, e.generalization_id)
        if not kind_ok(kinds, e.kind) or not open_ok(e.open) or want_edges_only:
            continue
        subs = [sub_by[s] for s in e.subentity_ids if s in sub_by]
        if flt.get("moved") or flt.get("up") or flt.get("down"):
            zs = [s.z for s in subs]
            if not any(_moved(z, flt) for z in zs):
                continue
        fields = [("name", e.name, 3.0), ("also called", " ".join(e.aliases), 2.5), ("concept", " ".join(kinds) + " " + e.kind, 2.0),
                  ("category", " ".join(CATEGORY_NAMES.get(t, t) for t in e.category_tags), 1.2),
                  ("description", (ent.description if ent else "") or "", 1.0)]
        s, why = score(fields) if query else (1.0, [])
        if s > 0:
            hits.append({"kind": "entity", "id": e.id, "name": e.name, "entity": e.id, "score": round(s, 3), "why": why,
                         "detail": e.kind_name or e.kind})
    for s in view.subentities:
        e = ent_by.get(s.entity_id)
        if e is None or want_edges_only:
            continue
        kinds = path_names(otax, e.generalization_id)
        if not kind_ok(kinds, e.kind) or not open_ok(s.open) or ((flt.get("moved") or flt.get("up") or flt.get("down")) and not _moved(s.z, flt)):
            continue
        fields = [("name", s.name, 3.0), ("entity", e.name + " " + " ".join(e.aliases), 2.0),
                  ("concept", f"{s.attribute_kind.replace('_', ' ')} {' '.join(kinds)}", 1.5), ("unit", s.unit, 0.8)]
        sc, why = score(fields) if query else (1.0, [])
        if sc > 0:
            # the screen names it with its entity ("Delta Air Lines · share price", world_model/web/js/names.js)
            hits.append({"kind": "subentity", "id": s.id, "name": s.name, "entity": s.entity_id, "entity_name": e.name,
                         "score": round(sc, 3), "why": why, "detail": f"{s.z:+.1f} sd"})
    for link in view.links:
        a, b = sub_by.get(link.source), sub_by.get(link.target)
        if a is None or b is None:
            continue
        if flt.get("learned") and link.origin == "construction":
            continue
        if flt.get("hedged") and not link.hedge:
            continue
        if (flt.get("moved") or flt.get("up") or flt.get("down")) and not (_moved(a.z, flt) or _moved(b.z, flt)):
            continue
        if "open" in flt or ("kind" in flt and flt["kind"] not in words(" ".join(path_names(itax, link.generalization_id)) + " " + link.label)):
            continue
        ea, eb = ent_by.get(a.entity_id), ent_by.get(b.entity_id)
        fields = [("label", link.label, 2.5), ("from", f"{a.name} {ea.name if ea else ''}", 1.5),
                  ("to", f"{b.name} {eb.name if eb else ''}", 1.5),
                  ("concept", " ".join(path_names(itax, link.generalization_id)), 1.0)]
        sc, why = score(fields) if query else (0.5, [])
        if sc > 0:
            hits.append({"kind": "interaction", "id": link.id, "name": f"{a.name} → {b.name}", "label": link.label,
                         "entities": [a.entity_id, b.entity_id], "score": round(sc, 3), "why": why,
                         "detail": f"{link.label} · effect {link.effect:+.2f}"})
    seen_patterns: set[str] = set()
    for h in view.hulls:
        if h.pattern_id in seen_patterns:
            continue
        seen_patterns.add(h.pattern_id)
        if h.transient or h.status == "dissolved" or want_edges_only or (flt.get("moved") or flt.get("up") or flt.get("down")):
            continue
        if "kind" in flt or not open_ok(h.open):
            continue
        member_names = " ".join(ent_by[m].name for m in h.members if m in ent_by)
        fields = [("name", h.label, 1.8), ("members", member_names, 1.5), ("description", h.description, 1.0)]
        sc, why = score(fields) if query else (0.8, [])
        if sc > 0:
            hits.append({"kind": "superentity", "id": h.id, "pattern_id": h.pattern_id, "name": h.label,
                         "entities": list(h.members), "score": round(sc, 3), "why": why,
                         "detail": f"{len(h.members)} entities · {h.status}"})
    order = {"entity": 0, "superentity": 1, "subentity": 2, "interaction": 3}
    hits.sort(key=lambda x: (-x["score"], order[x["kind"]], x["name"]))
    return {"query": q, "filters": {k: v for k, v in flt.items()}, "words": sorted(query), "hits": hits[:limit],
            "total": len(hits)}


def _moved(z: float, flt: dict) -> bool:
    if flt.get("up"):
        return z >= 1.0
    if flt.get("down"):
        return z <= -1.0
    return abs(z) >= 1.0
