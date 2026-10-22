"""Tools for building import bundles (axelrod.import/v1) for a scenario fed by imports (Emily's, Sally's).

A research agent reads sources and writes bundle *parts*: JSON files of dated, categorized items whose signals name
the model's ids. These tools give the agents the ids to use, check a part against the model, and assemble the parts
into one bundle per day, which the Import dialog lists in date order.

    uv run python world_model/scripts/imports/bundles.py ids sally_demo > <parts>/model_ids.txt
    uv run python world_model/scripts/imports/bundles.py check sally_demo <parts>/<group>.json
    uv run python world_model/scripts/imports/bundles.py days sally_demo <parts> <out_dir> --title "Sally's research"

Client research never enters the repository: point <parts> and <out_dir> at a gitignored folder (data/<client>_data).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from axelrod_ingest.contract.bundle import ImportBundle
from axelrod_wm.intake.overlap import overlapping_views, views_by_part
from axelrod_wm.repo.snapshots import MemoryBackend
from axelrod_wm.sim.runner import build_runner


def _runner(scenario: str):
    runner = build_runner(scenario, interactive=True, storage=MemoryBackend())
    runner.load()
    return runner


def cmd_ids(scenario: str) -> int:
    """Every value (id, name, unit) and every existing link, one per line, for agents writing signals."""
    g = _runner(scenario).controller.engine.wm.graph
    for sid in sorted(g.subentities):
        s = g.subentities[sid]
        print(f"{sid}\t{s.name}\tunit={s.unit}")
    for iid in sorted(g.interactions):
        i = g.interactions[iid]
        if i.retired_at is None:
            print(f"LINK\t{i.source_id} -> {i.target_id}\t{i.label}")
    return 0


def problems_of(runner, items: list[dict]) -> list[str]:
    """Schema, ids, quotes, and that every item maps onto the model."""
    bundle = ImportBundle.model_validate({"title": "check", "items": items})
    graph = runner.controller.engine.wm.graph
    out = []
    for it in bundle.items:
        text = f"{it.headline}\n{it.summary}"
        out += [f"{it.id}: unknown entity {e}" for e in it.entities if e not in graph.entities]
        for s in it.signals:
            if not s.quote:
                out.append(f"{it.id}: a {s.type} signal has no quote")
            elif s.quote not in text:
                out.append(f"{it.id}: quote not in headline/summary: {s.quote!r}")
    for row in runner.preview(bundle)["items"]:
        if row["dropped"]:
            out.append(f"{row['id']}: dropped {row['dropped']}")
        if row["changes"] == 0:
            out.append(f"{row['id']}: maps to nothing")
    ids = [i.id for i in bundle.items]
    out += [f"duplicate id {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    return out + driving_view_problems(graph, bundle.items)


def driving_view_problems(graph, items) -> list[str]:
    """Totals the bundle observes parts of that have two driving views (Oct 18): one view drives a total, the others
    are marked `drives: false` (or held in a matrix) so a results day imports whole."""
    parts = views_by_part(graph)
    touched = {s.value_of for it in items for s in it.signals if s.value_of in parts}
    return [f"{total} has {len(cids)} driving views ({', '.join(cids)}) and the bundle observes their parts; mark all "
            f"but one `drives: false` so it imports whole" for total, cids in overlapping_views(graph).items()
            if any(t == total for sid in touched for t, _ in parts[sid])]


def _items(path: Path) -> list[dict]:
    raw = json.loads(path.read_text())
    return raw["items"] if isinstance(raw, dict) else raw


def cmd_check(scenario: str, part: str) -> int:
    items = _items(Path(part))
    problems = problems_of(_runner(scenario), items)
    print("\n".join(problems) if problems else f"OK: {len(items)} items")
    return 1 if problems else 0


def cmd_days(scenario: str, parts: str, out_dir: str, title: str, collected_by: str) -> int:
    """Merge every part, check the lot, and write one bundle per publication day (YYYY-MM-DD.json)."""
    items: list[dict] = []
    for p in sorted(Path(parts).glob("*.json")):
        items += _items(p)
    problems = problems_of(_runner(scenario), items)
    if problems:
        print("\n".join(problems))
        return 1
    by_day: dict[str, list[dict]] = defaultdict(list)
    for it in sorted(items, key=lambda i: (i["published_at"], i["id"])):
        by_day[it["published_at"][:10]].append(it)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()
    for day, day_items in sorted(by_day.items()):
        bundle = {"format": "axelrod.import/v1", "title": f"{title}, {day}", "collected_by": collected_by,
                  "collected_at": f"{day}T23:00:00Z", "description": f"{len(day_items)} item(s) published on {day}.",
                  "synthetic": False, "items": day_items}
        ImportBundle.model_validate(bundle)
        (out / f"{day}.json").write_text(json.dumps(bundle, indent=1, ensure_ascii=False) + "\n")
    print(f"OK: {len(items)} items in {len(by_day)} daily bundles -> {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ids")
    a.add_argument("scenario")
    b = sub.add_parser("check")
    b.add_argument("scenario")
    b.add_argument("part")
    c = sub.add_parser("days")
    c.add_argument("scenario")
    c.add_argument("parts")
    c.add_argument("out_dir")
    c.add_argument("--title", default="Research")
    c.add_argument("--collected-by", default="research agent")
    args = ap.parse_args()
    if args.cmd == "ids":
        return cmd_ids(args.scenario)
    if args.cmd == "check":
        return cmd_check(args.scenario, args.part)
    return cmd_days(args.scenario, args.parts, args.out_dir, args.title, args.collected_by)


if __name__ == "__main__":
    sys.exit(main())
