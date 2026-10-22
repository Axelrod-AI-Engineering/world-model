"""The graph update a document would make (Oct 17): what the Import dialog draws before anything changes.

A document goes through the ingestion pipeline (ingest/pipeline.py, the service's own path) into an import bundle;
each of its items becomes one GraphUpdateEvent when imported (intake/bundle.py). This module reads that event without
importing it: every operation, tied to the signal it came from (its type, its quoted sentence or table row, the chunk
and page of the document), the values and links it touches (with their current level, for direction and size), and
the signals that could not be mapped onto the model. It is a pure function of the bundle, the stored chunks, and the
graph, so the same document against the same model always draws the same update.
"""

from __future__ import annotations

import re
from typing import Any

from axelrod_wm.ingest.chunk import CELL, tabular
from axelrod_wm.intake.bundle import ImportBundle, market_event_of, signal_ops, translate_item

ORD = re.compile(r"-(\d{4})$")          # an extracted item's id ends in its chunk's position (ingest/extract.py)


def _level(s: Any) -> tuple[float, float]:
    d = s.posterior
    return float(d.mean()), float(d.sd())


def _size(op: Any, s: Any) -> float:
    """The op's move in standard deviations of the value (its direction and size on the canvas)."""
    mean, sd = _level(s)
    sd = sd or 1.0
    if op.op == "observe_value":
        return (op.value - mean) / sd
    if op.mode == "standardized":
        return op.delta
    if op.mode == "relative":
        return op.delta * mean / sd
    return op.delta / sd


def _value(graph: Any, sid: str) -> dict:
    s = graph.subentities[sid]
    owner = graph.entities.get(s.entity_id)
    mean, sd = _level(s)
    return {"id": sid, "name": s.name, "entity_id": s.entity_id, "entity": owner.name if owner else s.entity_id,
            "unit": s.unit, "mean": round(mean, 6), "sd": round(sd, 6)}


def _op(k: int, op: Any, sig: Any, graph: Any) -> dict:
    out: dict[str, Any] = {"index": k, "op": op.op, "signal": sig.type, "quote": sig.quote, "note": sig.note,
                           "table_row": CELL in sig.quote or tabular(sig.quote)}
    if op.op in ("observe_value", "change_value"):
        sid = op.target.subentity_id
        s = graph.subentities[sid]
        out |= {"values": [sid], "z": round(_size(op, s), 4)}
        out |= {"value": op.value} if op.op == "observe_value" else {"delta": op.delta, "mode": str(op.mode)}
        return out
    if op.op == "add_interaction":
        src, dst = op.source.subentity_id, op.target.subentity_id
        return out | {"values": [src, dst], "source": src, "target": dst, "label": op.label, "polarity": op.polarity,
                      "effect": round(float(op.dynamics.effect.mean()), 4)}
    link = graph.interactions[op.interaction_id]
    return out | {"values": [link.source_id, link.target_id], "source": link.source_id, "target": link.target_id,
                  "interaction_id": link.id, "label": link.label, "supports": op.supports, "strength": op.strength}


def update_view(bundle: dict, graph: Any, runner: Any, chunks: list[Any] = ()) -> dict:
    """Each item's GraphUpdateEvent, op by op, with its evidence; the values it touches; the chunks it quotes."""
    b = ImportBundle.model_validate(bundle)
    by_ord = {c.ord: c for c in chunks}
    items, values, quoted = [], {}, {}
    for item in sorted(b.items, key=lambda x: (x.published_at, x.id)):
        me = market_event_of(item, runner.event_id(item), b.synthetic)
        res, _ = translate_item(item, me, graph)
        event = res.events[0] if res.events else None
        m = ORD.search(item.id)
        chunk = by_ord.get(int(m.group(1))) if m else None
        ops, dropped, k = [], [], 0
        for sig in item.signals:
            got, why = signal_ops(sig, graph, me.published_at)
            if why:
                dropped.append({"signal": sig.type, "quote": sig.quote, "reason": why})
            for _ in got:
                row = _op(k, event.ops[k], sig, graph)
                ops.append(row)
                for sid in row["values"]:
                    values.setdefault(sid, _value(graph, sid))
                k += 1
        if chunk is not None:
            quoted[chunk.ord] = {"ord": chunk.ord, "page": chunk.page, "section": chunk.section, "text": chunk.text}
        items.append({"id": item.id, "headline": item.headline, "published_at": item.published_at.isoformat(),
                      "category": item.category, "chunk": chunk.ord if chunk is not None else None,
                      "page": chunk.page if chunk is not None else None, "summary": item.summary,
                      "event_id": event.id if event is not None else None, "ops": ops, "dropped": dropped,
                      "imported": me.id in runner.imported})
    return {"items": items, "values": values, "chunks": [quoted[o] for o in sorted(quoted)]}


def document_view(result: Any, graph: Any, runner: Any, chunks: list[Any]) -> dict:
    """An ingested document: what the pipeline read (the trace), its bundle, and the update the bundle would make."""
    d = result.document
    rec = result.bundle
    view = update_view(rec.bundle, graph, runner, chunks) if rec is not None else {"items": [], "values": {}, "chunks": []}
    return {"document": {"id": d.id, "filename": d.filename, "title": d.title, "source": d.source,
                         "source_type": d.source_type, "event_time": d.event_time.isoformat(), "status": d.status,
                         "error": d.error},
            "trace": {"new": result.new, "chunks": result.chunks, "mentions": result.mentions,
                      "signals": result.signals, "llm_signals": result.llm_signals, "warnings": list(result.warnings)},
            "bundle_id": rec.id if rec is not None else None, "bundle": rec.bundle if rec is not None else None,
            **view}


__all__ = ["document_view", "update_view"]
