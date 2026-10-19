"""Check a world's business construction, and write each company's readable view (context/construction.py).

    uv run python scripts/construction/check.py sally_demo --entities toyota tokio_marine --out <folder>
        [--trace dollar_yen.usd_jpy:toyota ...] [--sources data/sally_data/construction]
        [--reconcile [--baselines <bundle.json> ...] [--statistic mean|median] [--suggest-residual] [--tolerance 0.005]]

Prints structural problems (model/construction.validate_construction) and exits 1 if there are any, and each total
with more than one driving additive view (the overlapping-views guard at import, intake/overlap.py). Per company: its inputs by
status (and every one not yet reviewed); with --sources, whether its cited source ids resolve to the local sources.json
and which material claims have no citation with a location (citations.json). With --reconcile, a table of each
additive composition (total against members + residual + eliminations, driving and reconciling views alike), each
identity (target against what its terms imply), and each matrix's cells, at the model's levels, or at the levels the
--baselines bundles observe (axelrod.import/v1), where each stock-flow's roll-forward is also checked between dated
stock levels; exit 1 on a flag; --suggest-residual prints the residual level that
would close each gap. Writes <entity>.md (the readable view) and <entity>.json (the objects) to --out, and each --trace
(start:entity) as a route list (--through-totals: routes go on through the totals they reach). Run it against the loaded scenario, so the view shows the model's current levels.

Client passages never print: the source report gives ids and counts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from axelrod_wm.context.construction import (
    company_citations,
    construction_view,
    inputs_by_status,
    keyword_risks,
    load_sources,
    to_markdown,
    trace,
)
from axelrod_wm.intake.overlap import overlapping_views
from axelrod_wm.model.construction import (
    TOLERANCE,
    bundle_levels,
    bundle_series,
    model_levels,
    reconcile,
    reconcile_identities,
    reconcile_matrices,
    reconcile_stock_flows,
    validate_construction,
)


def _num(x: float | None, pct: bool = False) -> str:
    if x is None:
        return "-"
    return f"{100 * x:+.2f}%" if pct else f"{x:,.4g}"


def print_reconciliation(rows: list[dict], label: str, suggest: bool) -> int:
    """The reconciliation table; returns the number of flags."""
    print(f"reconciliation at {label} ({len(rows)} additive composition(s)):")
    print(f"  {'composition':<32} {'total':>12} {'sum':>12} {'difference':>12} {'rel':>9}  status")
    for r in rows:
        print(f"  {r['composition_id']:<32} {_num(r['total_level']):>12} {_num(r['sum']):>12} {_num(r['difference']):>12} "
              f"{_num(r['relative_difference'], pct=True):>9}  {r['status'].upper()}")
        if r["unit_mismatches"]:
            print(f"    unit differs from the total's ({r['unit']}): {', '.join(r['unit_mismatches'])}")
        if r["missing_levels"]:
            print(f"    no level: {', '.join(r['missing_levels'])}")
        if suggest and r["status"] == "flag" and r["residual_to_close"] is not None:
            where = r["residual"] or "a new residual"
            print(f"    residual to close: {where} = {_num(r['residual_to_close'])}")
    flags = sum(1 for r in rows if r["status"] == "flag")
    blocked = sum(1 for r in rows if r["status"] == "blocked")
    print(f"  {flags} flag(s)" + (f", {blocked} blocked by missing levels (not a discrepancy)" if blocked else ""))
    return flags


def print_identities(rows: list[dict], label: str) -> int:
    """Identities (target against what its terms imply), matrix cells, or roll-forwards; returns the flags."""
    if not rows:
        return 0
    print(f"identities at {label} ({len(rows)}):")
    for r in rows:
        print(f"  {r['identity_id']:<32} {_num(r['target_level']):>12} {_num(r['implied']):>12} "
              f"{_num(r['relative_difference'], pct=True):>9}  {r['status'].upper()}  {r['formula']}")
        for k, what in (("missing_levels", "no level"), ("unit_mismatches", "unit differs from the target's")):
            if r[k]:
                print(f"    {what}: {', '.join(r[k])}")
    return sum(1 for r in rows if r["status"] == "flag")


def print_matrices(rows: list[dict], label: str) -> int:
    if not rows:
        return 0
    print(f"matrix cells at {label} ({len(rows)} matri{'x' if len(rows) == 1 else 'ces'}):")
    for r in rows:
        print(f"  {r['matrix_id']}: {r['status'].upper()}" + (f" (incomplete: {', '.join(r['incomplete'])})"
                                                             if r["incomplete"] else ""))
        for x in r["lines"]:
            print(f"    {x['axis']} {x['part']:<30} {_num(x['level']):>12} {_num(x['sum_of_cells']):>12} "
                  f"{_num(x['relative_difference'], pct=True):>9}  {x['status'].upper()}")
    return sum(1 for r in rows if r["status"] == "flag")


def print_stock_flows(rows: list[dict], label: str) -> int:
    if not rows:
        return 0
    print(f"roll-forwards at {label} ({len(rows)}):")
    for r in rows:
        print(f"  {r['stock_flow_id']:<28} {r['opening_at']} -> {r['closing_at']}  opening {_num(r['opening'])}, closing "
              f"{_num(r['closing'])}, implied {_num(r['implied_closing'])} ({_num(r['relative_difference'], pct=True)})"
              f"  {r['status'].upper()}" + (f"  no flow: {', '.join(r['missing_flows'])}" if r["missing_flows"] else ""))
    return sum(1 for r in rows if r["status"] == "flag")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("scenario")
    ap.add_argument("--entities", nargs="*", default=[])
    ap.add_argument("--trace", nargs="*", default=[], help="start:entity, e.g. dollar_yen.usd_jpy:toyota")
    ap.add_argument("--through-totals", action="store_true", help="traces go on through the totals they reach")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--sources", type=Path, help="the folder of <company>/sources.json and citations.json")
    ap.add_argument("--reconcile", action="store_true", help="check each additive composition's levels")
    ap.add_argument("--baselines", type=Path, nargs="*", default=[], help="axelrod.import/v1 bundles: their observes are the levels")
    ap.add_argument("--suggest-residual", action="store_true", help="print the residual level that closes each gap")
    ap.add_argument("--tolerance", type=float, default=TOLERANCE)
    ap.add_argument("--statistic", choices=["mean", "median"], default="mean",
                    help="the model's level: posterior mean (default) or median (a lognormal's construction level)")
    a = ap.parse_args(argv)

    from axelrod_wm.repo.snapshots import MemoryBackend
    from axelrod_wm.sim.runner import build_runner

    r = build_runner(a.scenario, interactive=True, storage=MemoryBackend(), record_checklist=False)
    r.load()
    g = r.controller.engine.wm.graph
    problems = validate_construction(g)
    for p in problems:
        print(f"PROBLEM {p}")
    for total, cids in overlapping_views(g).items():
        print(f"VIEWS {total} has {len(cids)} additive views ({', '.join(cids)}); an import folds one per item and "
              f"day (intake/overlap.py)")
    if a.out:
        a.out.mkdir(parents=True, exist_ok=True)
    sources = load_sources(a.sources) if a.sources else None
    for p in (sources or {}).get("problems", []):
        print(f"SOURCES {p}")
    for eid in a.entities:
        view = construction_view(g, eid)
        print(f"{eid}: {len(view['compositions'])} composition(s), {len(view['paths'])} path(s), links {view['links']}")
        ins = inputs_by_status(g, eid)
        print(f"  inputs by status: {ins['counts']}")
        for name in ins["not_yet_reviewed"]:
            print(f"  NOT YET REVIEWED {name}")
        for k in keyword_risks(g, eid):
            print(f"  KEYWORD {k['value_id']}: the extraction gazetteer would match the common word(s) "
                  f"{', '.join(k['keywords'])} anywhere; rename the value or give its id a specific last word")
        if sources is not None:
            cc = company_citations(g, eid, sources)
            print(f"  sources: {len(cc['resolved'])} id(s) resolve, {len(cc['unresolved'])} do not; "
                  f"{cc['cited_links']} link(s) and {cc['cited_values']} value(s) cited; "
                  f"{len(cc['claims_without_citation'])} material claim(s) without a citation")
            for u in cc["unresolved"]:
                print(f"  UNRESOLVED {u['source_id']} (cited by {', '.join(u['cited_by'])})")
            for c in cc["claims_without_citation"]:
                print(f"  UNCITED {c['interaction_id']}: {'; '.join(c['claims'])}")
            for k in cc["unknown_citation_keys"]:
                print(f"  UNKNOWN CITATION KEY {k}")
        if a.out:
            (a.out / f"{eid}.md").write_text(to_markdown(view))
            (a.out / f"{eid}.json").write_text(json.dumps(view, indent=1))
    for t in a.trace:
        start, eid = t.split(":")
        tr = trace(g, start, eid, through_totals=a.through_totals)
        print(f"trace {start} -> {eid}: {len(tr['routes'])} route(s), reaches an endpoint: {tr['reaches_endpoint']}, "
              f"stops at {tr['stops']}")
        if a.out:
            (a.out / f"trace_{start}_{eid}.json").write_text(json.dumps(tr, indent=1))
    flags = 0
    if a.reconcile:
        def mine(rows: list[dict]) -> list[dict]:
            return [x for x in rows if not a.entities or x["entity_id"] in a.entities]

        if a.baselines:
            for b in a.baselines:
                bundle = json.loads(b.read_text())
                lv, label = bundle_levels(bundle), f"the levels {b.name} observes"
                flags += print_reconciliation(mine(reconcile(g, lv, a.tolerance)), label, a.suggest_residual)
                flags += print_identities(mine(reconcile_identities(g, lv, a.tolerance)), label)
                flags += print_matrices(mine(reconcile_matrices(g, lv, a.tolerance)), label)
                flags += print_stock_flows(mine(reconcile_stock_flows(g, bundle_series(bundle), a.tolerance)), label)
        else:
            lv, label = model_levels(g, a.statistic), f"the model's levels (posterior {a.statistic}s)"
            flags += print_reconciliation(mine(reconcile(g, lv, a.tolerance)), label, a.suggest_residual)
            flags += print_identities(mine(reconcile_identities(g, lv, a.tolerance)), label)
            flags += print_matrices(mine(reconcile_matrices(g, lv, a.tolerance)), label)
    return 1 if problems or flags else 0


if __name__ == "__main__":
    sys.exit(main())
