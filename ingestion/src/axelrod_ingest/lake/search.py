"""Search and retrieval over the lakehouse and the world model (Oct 17).

    keyword   words in the documents' text (FTS5, ranked by BM25); every word first, any word when that finds nothing
    prefix    the same with the last word as a prefix, plus the world model's entities and attributes whose names start so
    semantic  the query's embedding against every chunk's, by cosine similarity
    graph     the entities and attributes the query names, their neighbours through the model's interactions, and the
              chunks that mention them
    hybrid    keyword, semantic, and graph, fused by reciprocal rank

`retrieve` is the public retrieval (Oct 26, `GET /v1/world-models/{id}/chunks`): passages only, filtered by document,
fused in the store in one call, and paged.

Every list is ordered by score, then by document and position, so the same query over the same data always returns the
same results in the same order.
"""

from __future__ import annotations

from collections.abc import Sequence

from axelrod_ingest.contract.world_view import WorldView
from axelrod_ingest.gazetteer import Gazetteer
from axelrod_ingest.lake.embed import Embedder
from axelrod_ingest.lake.store import (
    CHANNELS,
    RRF_K,
    Hit,
    LakeStore,
    Retrieval,
    RetrievalFilter,
    RetrievalSpec,
)
from axelrod_ingest.text import norm, tokens

MODES = ("keyword", "prefix", "semantic", "graph", "hybrid")


class Searcher:
    def __init__(self, store: LakeStore, embedder: Embedder, graph: WorldView | None = None) -> None:
        self.store = store
        self.embedder = embedder
        self.graph = graph
        self._gz: tuple[int, Gazetteer] | None = None

    def gazetteer(self) -> Gazetteer | None:
        if self.graph is None:
            return None
        key = id(self.graph)
        if self._gz is None or self._gz[0] != key:
            self._gz = (key, Gazetteer(self.graph))
        return self._gz[1]

    # -- the modes ------------------------------------------------------------------------------------------------
    def keyword(self, tenant: str, q: str, limit: int = 20) -> list[Hit]:
        return self.store.keyword_search(tenant, q, prefix=False, limit=limit)

    def prefix(self, tenant: str, q: str, limit: int = 20) -> list[Hit]:
        hits = self.names(q, limit) + self.store.keyword_search(tenant, q, prefix=True, limit=limit)
        return hits[:limit]

    def names(self, q: str, limit: int = 20) -> list[Hit]:
        """The model's entities and attributes whose name (or an alias) starts with the query."""
        if self.graph is None or not q.strip():
            return []
        p = q.strip().lower()
        out = []
        for eid, e in sorted(self.graph.entities.items()):
            names = [e.name, *e.aliases]
            if any(n.lower().startswith(p) for n in names):
                out.append(Hit(kind="entity", ref=eid, entity_id=eid, score=1.0, text=e.name, why=["name prefix"]))
        for sid, s in sorted(self.graph.values.items()):
            if any(n.lower().startswith(p) for n in (s.name, *s.aliases)):
                out.append(Hit(kind="attribute", ref=sid, entity_id=s.entity_id, score=0.9, text=s.name,
                               why=["name prefix"]))
        return out[:limit]

    def semantic(self, tenant: str, q: str, limit: int = 20) -> list[Hit]:
        if not q.strip():
            return []
        qv = self.embedder.embed([q])[0]
        scored = self.store.nearest(tenant, self.embedder.name, qv, limit)
        return [self._chunk_hit(tenant, d, o, s, ["semantic"]) for s, d, o in scored]

    def graph_search(self, tenant: str, q: str, limit: int = 20) -> list[Hit]:
        gz = self.gazetteer()
        if gz is None:
            return []
        named = [(m.entity_id, m.subentity_id) for m in gz.find(q)]
        if not named:
            # no full name: the entities whose names share a word with the query
            words = {norm(t) for t, _a, _b in tokens(q)}
            named = [(eid, None) for eid, e in sorted(self.graph.entities.items())
                     if words & {norm(t) for n in (e.name, *e.aliases) for t, _a, _b in tokens(n)}]
        ents = sorted({e for e, _s in named})
        vals = sorted({s for _e, s in named if s})
        out: list[Hit] = []
        for eid in ents:
            out.append(Hit(kind="entity", ref=eid, entity_id=eid, score=1.0, text=self.graph.entities[eid].name,
                           why=["named"]))
        subs = self.graph.values
        for sid in vals:
            out.append(Hit(kind="attribute", ref=sid, entity_id=subs[sid].entity_id, score=1.0, text=subs[sid].name,
                           why=["named"]))
        # neighbours: attributes one interaction away from what was named
        seeds = set(vals) or {s for e in ents for s in self.graph.entities[e].subentity_ids}
        near: dict[str, str] = {}
        for i in sorted(self.graph.links, key=lambda x: x.id):
            if i.source_id in seeds and i.target_id not in seeds:
                near.setdefault(i.target_id, f"{self.graph.values[i.source_id].name} {i.label}")
            if i.target_id in seeds and i.source_id not in seeds:
                near.setdefault(i.source_id, f"drives {self.graph.values[i.target_id].name}")
        for sid, why in sorted(near.items()):
            out.append(Hit(kind="attribute", ref=sid, entity_id=subs[sid].entity_id, score=0.5, text=subs[sid].name,
                           why=["neighbour", why]))
        # the chunks that mention what was named, most mentions first
        counts: dict[tuple[str, int], int] = {}
        for eid in ents:
            for m in self.store.mentions_of(tenant, entity_id=eid):
                if not vals or m.subentity_id in vals or m.subentity_id is None:
                    counts[(m.doc_id, m.ord)] = counts.get((m.doc_id, m.ord), 0) + 1
        for (d, o), c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            out.append(self._chunk_hit(tenant, d, o, round(c / max(counts.values()), 6), ["mentions"]))
        return out[:limit]

    def hybrid(self, tenant: str, q: str, limit: int = 20) -> list[Hit]:
        lists = [self.keyword(tenant, q, 50), self.semantic(tenant, q, 50),
                 [h for h in self.graph_search(tenant, q, 50) if h.kind == "chunk"]]
        fused: dict[tuple[str, int], float] = {}
        why: dict[tuple[str, int], list[str]] = {}
        best: dict[tuple[str, int], Hit] = {}
        for hits in lists:
            for rank, h in enumerate(hits):
                key = (h.doc_id, h.ord)
                fused[key] = fused.get(key, 0.0) + 1.0 / (RRF_K + rank + 1)
                why.setdefault(key, []).extend(w for w in h.why if w not in why.get(key, []))
                best.setdefault(key, h)
        order = sorted(fused.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
        return [best[k].model_copy(update={"score": round(s, 6), "why": why[k]}) for k, s in order]

    def retrieve(self, tenant: str, q: str, *, channels: Sequence[str] = CHANNELS,
                 filter: RetrievalFilter | None = None, offset: int = 0, limit: int = 10, context: int = 0,
                 per_document: int = 0) -> Retrieval:
        """Ranked passages for `q` (store.retrieve): the query is embedded and its names resolved here, and the rest is
        one call to the store."""
        ents: set[str] = set()
        vals: set[str] = set()
        gz = self.gazetteer() if "graph" in channels else None
        for m in gz.find(q) if gz is not None else []:
            ents.add(m.entity_id)
            if m.subentity_id:
                vals.add(m.subentity_id)
        vector = self.embedder.embed([q])[0] if "semantic" in channels and q.strip() else None
        spec = RetrievalSpec(query=q, channels=list(channels), vector=vector, model=self.embedder.name,
                             entity_ids=sorted(ents), attribute_ids=sorted(vals), filter=filter or RetrievalFilter(),
                             offset=offset, limit=limit, context=context, per_document=per_document)
        return self.store.retrieve(tenant, spec)

    def search(self, tenant: str, q: str, mode: str = "hybrid", limit: int = 20) -> list[Hit]:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {', '.join(MODES)}")
        fn = {"keyword": self.keyword, "prefix": self.prefix, "semantic": self.semantic, "graph": self.graph_search,
              "hybrid": self.hybrid}[mode]
        return fn(tenant, q, limit)

    # -- helpers --------------------------------------------------------------------------------------------------
    def _chunk_hit(self, tenant: str, doc_id: str, ord_: int, score: float, why: list[str]) -> Hit:
        doc = self.store.get_document(tenant, doc_id)
        chunk = next((c for c in self.store.get_chunks(tenant, doc_id) if c.ord == ord_), None)
        return Hit(kind="chunk", doc_id=doc_id, ord=ord_, score=score, text=chunk.text if chunk else "",
                   title=doc.title if doc else "", filename=doc.filename if doc else "",
                   event_time=doc.event_time if doc else None, why=why)
