"""The overlapping-views guard (Oct 17): one change must not reach a total twice through two views of it.

Two additive compositions of the same total (say reporting segments and regions, both summing to operating profit)
are different views of one business (model/construction.py). Each part has an accounting link to the total, so if an
import observes or moves parts of both views, both sets of links carry the change into the total and it is counted
twice.

**The rule.** Within one item, and separately within one day (the items published on the same date, including any
already imported), when observations or moves touch parts of two or more additive compositions of the same total,
only the parts of one composition are folded in:

1. a composition already folded in that day keeps its place (an approved change cannot be unfolded);
2. otherwise the composition with the most distinct parts observed;
3. ties go to the composition with the larger share of its parts observed, then to the first by id.

The other compositions' part signals are not folded: the preview lists them under `dropped`, with the compositions'
ids, and the review's rationale says so. Everything else in the item (rates, prices, links, the total itself) is folded
as usual.

**Reconciling views (Oct 18).** A composition marked `drives: false`, or the passive view of a matrix (rows x columns),
is observed and reconciled against its total but has no propagating link into it. Its parts never compete with the
driving view, so a results day that reports both views folds both whole.

**Why fold one view rather than refuse the item.** Refusing would also hold back every unrelated signal in the item
(a results release reports segments, regions, guidance and the share price together) and push the reviewer to edit the
bundle by hand. Folding one view never double counts, keeps the dropped observations visible, and leaves the choice
open: a reviewer who prefers the other view imports an item without these parts.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from axelrod_wm.model.construction import reconciling_views

RULE = ("When one item, or one day, observes parts of two additive views of the same total, only the parts of one view "
        "are folded: a view already folded that day, else the view with the most parts observed (ties: the larger share "
        "of its parts, then the first by id). The other views' parts are listed as dropped, so no change reaches the "
        "total twice.")


def views_by_part(graph: Any) -> dict[str, list[tuple[str, str]]]:
    """part id -> [(total id, composition id)] over the graph's additive compositions that drive their total. A
    reconciling view (`drives: false`, or a matrix's passive view; model/construction.reconciling_views) is left out:
    its parts have no propagating link into the total, so observing them with the driving view's parts counts nothing
    twice and they are never dropped."""
    passive = reconciling_views(graph)
    out: dict[str, list[tuple[str, str]]] = {}
    for cid, c in sorted(graph.compositions.items()):
        if not c.additive or cid in passive:
            continue
        for sid in [*c.members, *([c.residual] if c.residual else []), *([c.eliminations] if c.eliminations else [])]:
            out.setdefault(sid, []).append((c.total, cid))
    return out


def overlapping_views(graph: Any) -> dict[str, list[str]]:
    """total id -> the ids of its additive compositions, for totals with more than one (the views that overlap)."""
    by_total: dict[str, set[str]] = {}
    for views in views_by_part(graph).values():
        for total, cid in views:
            by_total.setdefault(total, set()).add(cid)
    return {t: sorted(cids) for t, cids in sorted(by_total.items()) if len(cids) > 1}


def _touched(item: Any, parts: dict[str, list[tuple[str, str]]]) -> list[tuple[int, str]]:
    """(signal index, value id) of the item's observes and moves of a composition part."""
    return [(k, s.value_of) for k, s in enumerate(item.signals)
            if s.type in ("observe", "move") and s.value_of in parts]


def _pick(graph: Any, counts: dict[str, set[str]], fixed: set[str]) -> str:
    def key(cid: str) -> tuple:
        c = graph.compositions[cid]
        n = len([*c.members, *([c.residual] if c.residual else []), *([c.eliminations] if c.eliminations else [])])
        return (cid not in fixed, -len(counts[cid]), -len(counts[cid]) / n, cid)

    return min(counts, key=key)


def overlap_guard(graph: Any, items: Iterable[Any], folded: Iterable[Any] = (),
                  held: dict[str, dict[int, str]] | None = None) -> tuple[dict[str, dict[int, str]], list[dict]]:
    """For the items about to be folded (and those already folded, which are never changed; `held` names the signals
    of theirs that were not folded): the signals not to fold, {item id: {signal index: reason}}, and one warning per
    overlap found (scope "item" or "day")."""
    parts = views_by_part(graph)
    items, folded, held = list(items), list(folded), held or {}
    skip: dict[str, dict[int, str]] = {}
    warnings: list[dict] = []

    def resolve(scope: str, where: str, touched: list[tuple[str, int, str]], fixed: dict[str, set[str]]) -> None:
        # touched: (item id, signal index, value id) for the signals still to fold, plus the folded ones
        per_total: dict[str, dict[str, set[str]]] = {}
        for _, _, sid in touched:
            for total, cid in parts[sid]:
                per_total.setdefault(total, {}).setdefault(cid, set()).add(sid)
        for total, counts in sorted(per_total.items()):
            if len(counts) < 2:
                continue
            keep = _pick(graph, counts, fixed.get(total, set()))
            # only this total's other views lose their parts; a part of the kept view, or of another total, stays
            others = {sid for sid, views in parts.items()
                      if (total, keep) not in views and any(t == total for t, _ in views)}
            dropped = []
            for iid, k, sid in touched:
                if sid not in others or iid in done or k in skip.get(iid, {}):
                    continue
                skip.setdefault(iid, {})[k] = (f"overlapping view: {', '.join(sorted(counts))} are views of {total}; "
                                               f"{keep} is folded ({scope} rule), so {sid} is not")
                dropped.append({"item": iid, "signal": k, "value_of": sid})
            warnings.append({"scope": scope, "where": where, "total": total, "compositions": sorted(counts),
                             "kept": keep, "observed": {c: sorted(v) for c, v in sorted(counts.items())},
                             "dropped": dropped})

    done = {i.id for i in folded}
    for it in items:
        resolve("item", it.id, [(it.id, k, sid) for k, sid in _touched(it, parts)], {})
    by_day: dict[str, list[Any]] = {}
    for it in [*folded, *items]:
        by_day.setdefault(it.published_at.date().isoformat(), []).append(it)
    for day, day_items in sorted(by_day.items()):
        touched = [(it.id, k, sid) for it in day_items for k, sid in _touched(it, parts)
                   if k not in skip.get(it.id, held.get(it.id, {}))]
        fixed: dict[str, set[str]] = {}
        for iid, _, sid in touched:
            if iid in done:
                for total, cid in parts[sid]:
                    fixed.setdefault(total, set()).add(cid)
        if len({iid for iid, _, _ in touched}) > 1:
            resolve("day", day, touched, fixed)
    return skip, warnings


__all__ = ["RULE", "overlap_guard", "overlapping_views", "views_by_part"]
