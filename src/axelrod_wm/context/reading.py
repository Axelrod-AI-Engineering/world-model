"""The reading set: a v4.1.4 export an answering agent can open (Oct 18).

The domain pack is the machine-import file and stays whole (the client's contract, named by their 020). It can run to
megabytes, which a reading tool refuses ("file too large to extract"). So the export also carries `reading/`: files of
at most `cap_kb` kilobytes, each holding whole objects of the pack unchanged, with their ids:

    00_START_HERE.md            what the model is, what it covers, every file with its size and when to open it
    01_overview_<company>.md    business composition, paths (one line each), relationships, calculation coverage
    10_pack_core_NN.json        the pack header, companies, clusters, sector packs, caveats, metric families
    20_relationships_<company>_NN.json   company_edge_relationships, grouped by edge, never cut mid-relationship
    30_paths_<company>_NN.json  transmission_paths
    40_semantic_fields_NN.json  financial_model_semantic_fields
    50_financial_<company>_NN.json   the financial bridge and identities of the company
    60_support_NN.json          the other domain_specific_support_objects
    90_index_ids_NN.json        every relationship, path, and support-object id -> its file (sorted, in as many files as it needs)

Each object lands in exactly one shard; `verify_coverage` reads the written files back and checks that their union is
the pack's objects, nothing lost or duplicated, and the manifest lists each file with its sha256 and size.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

FOLDER = "reading"
BIG = ("company_edge_relationships", "transmission_paths", "financial_model_semantic_fields",
       "domain_specific_support_objects")
SUP = "domain_specific_support_objects."
PER_COMPANY = (SUP + "financial_bridge", SUP + "financial_identities", SUP + "financial_matrices")
ID_KEY = {"company_edge_relationships": "relationship_id", "transmission_paths": "path_id",
          "financial_model_semantic_fields": "field_spec_id", "clusters": "cluster_id",
          SUP + "macro_transmission_links": "link_id", SUP + "macro_factor_nodes": "node_id",
          SUP + "financial_bridge": "composition_id", SUP + "financial_identities": "identity_id",
          SUP + "axelrod_edge_vocabulary": "edge_id"}
WHEN_ORDER = {10: "The pack's frame: companies, clusters, sector packs, caveats, metric families",
              20: "Mechanisms from a driver to a company metric: effect size, delay, validator, invalidator",
              30: "The ordered chain from a trigger to the companies it reaches",
              40: "Definitions of the financial-model fields",
              50: "How a company's total splits into parts, and the identities that compute its metrics",
              60: "Macro nodes and links, edge vocabulary, schema gaps, model state, citation gaps",
              90: "To find the file holding a relationship, path, composition, identity, node, or link id"}
WHEN = {
    "yours": ("The client's contract, schema, or registry",
              "Open for the meaning of a field or a rule."),
    "this export: domain_pack": ("The full domain pack (machine import)",
                                 "Do not open: {size}, too large to read. Every object in it is in the files above, unchanged."),
    "this export: evidence": ("Evidence pack: each metric's current value and the open questions",
                              "For numbers at the as-of date."),
    "this export: sources": ("Source catalogue", "To resolve an `evidence_refs` source id to its document."),
    "this export: forecast": ("Forecast evidence pack, thesis {thesis}", "{question}"),
}


def line(o: Any) -> str:
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def canon(o: Any) -> str:
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def size_of(o: Any) -> int:
    return len(line(o).encode()) + 2


def kb(n: int) -> str:
    return f"{n / 1024:.1f} KB"


def flatten(pack: dict) -> tuple[dict, list[tuple[str, Any]]]:
    """The pack as (header scalars, [(section, object)]): lists give their elements, a dict one object, and the
    support objects each of their parts, under `domain_specific_support_objects.<part>`."""
    header, items = {}, []

    def add(section: str, v: Any) -> None:
        items.extend((section, o) for o in (v if isinstance(v, list) else [v]))

    for k, v in pack.items():
        if k == "domain_specific_support_objects":
            for part, pv in v.items():
                add(SUP + part, pv)
        elif isinstance(v, (list, dict)):
            add(k, v)
        else:
            header[k] = v
    return header, items


def pack_groups(items: list[tuple[str, Any, str]], budget: int) -> list[list[tuple[str, Any]]]:
    """Fill files in order up to `budget` bytes. A group (items sharing a key) stays in one file when it fits;
    one larger than the budget is split between objects. An object is never cut."""
    groups: dict[str, list[tuple[str, Any]]] = {}
    for s, o, g in items:
        if size_of(o) > budget:
            raise ValueError(f"one object in {s} is larger than the {budget}-byte budget")
        groups.setdefault(g, []).append((s, o))
    shards: list[list[tuple[str, Any]]] = []
    cur: list[tuple[str, Any]] = []
    used = 0
    for its in groups.values():
        total = sum(size_of(o) for _s, o in its)
        if total <= budget:
            if used + total > budget:
                shards.append(cur)
                cur, used = [], 0
            cur += its
            used += total
        else:
            if cur:
                shards.append(cur)
            cur, used = [], 0
            for it in its:
                n = size_of(it[1])
                if used + n > budget:
                    shards.append(cur)
                    cur, used = [], 0
                cur.append(it)
                used += n
    return [*shards, *([cur] if cur else [])]


def render(meta: dict, its: list[tuple[str, Any]]) -> str:
    secs: dict[str, list[Any]] = {}
    for s, o in its:
        secs.setdefault(s, []).append(o)
    body = ",\n".join(f"{json.dumps(s)}: [\n" + ",\n".join(line(o) for o in objs) + "\n]" for s, objs in secs.items())
    return '{\n"reading_shard": ' + line(meta) + ',\n"sections": {\n' + body + "\n}\n}\n"


def route(pack: dict, slug_of: dict[str, str]) -> list[tuple[str, int, str, Any, str]]:
    """(family, order, section, object, group) for every object: which family of files holds it."""
    header, items = flatten(pack)
    out = []
    for s, o in items:
        if s == "company_edge_relationships":
            slug = slug_of.get(o["company_id"], o["company_id"].lower())
            out.append((f"relationships_{slug}", 20, s, o, f"{o['edge_id']}|{o['axelrod']['target_metric']}"))
        elif s == "transmission_paths":
            slug = slug_of.get(o["primary_company_id"], o["primary_company_id"].lower())
            out.append((f"paths_{slug}", 30, s, o, o["path_id"]))
        elif s == "financial_model_semantic_fields":
            out.append(("semantic_fields", 40, s, o, s))
        elif s in PER_COMPANY:
            slug = slug_of.get(o["company_id"], o["company_id"].lower())
            out.append((f"financial_{slug}", 50, s, o, s))
        elif s.startswith(SUP):
            out.append(("support", 60, s, o, s))
        else:
            out.append(("pack_core", 10, s, o, s))
    return out


def oid(section: str, o: Any) -> str | None:
    key = ID_KEY.get(section)
    return o[key] if key and isinstance(o, dict) and key in o else None


def describe(its: list[tuple[str, Any]]) -> tuple[dict, dict]:
    """Counts per section, and for relationships the edges and the range of target metrics the file holds."""
    counts = Counter(s for s, _o in its)
    rels = [o for s, o in its if s == "company_edge_relationships"]
    targets = sorted(o["axelrod"]["target_metric"] for o in rels)
    scope = {"edge_ids": sorted({o["edge_id"] for o in rels}), "target_metrics_from": targets[0],
             "target_metrics_to": targets[-1]} if rels else {}
    return dict(counts), scope


def scope_text(scope: dict) -> str:
    e = scope["edge_ids"]
    return f"edges {', '.join(e)}; targets {scope['target_metrics_from']} to {scope['target_metrics_to']}"


def verify_coverage(pack: dict, docs: list[dict]) -> dict:
    """Does the union of the shards equal the pack's objects? Compared by canonical content, with multiplicity."""
    header, items = flatten(pack)
    want = Counter((s, canon(o)) for s, o in items)
    got: Counter = Counter()
    got_header: dict = {}
    for d in docs:
        got_header.update(d["reading_shard"].get("pack_header", {}))
        for s, objs in d["sections"].items():
            got.update((s, canon(o)) for o in objs)
    missing, extra = want - got, got - want
    ids = Counter((s, i) for s, c in got.elements() if (i := oid(s, json.loads(c))) is not None)
    in_pack = Counter((s, i) for s, o in items if (i := oid(s, o)) is not None)
    dup_ids = sorted(f"{s}:{i}" for (s, i), n in ids.items() if n > in_pack[(s, i)])
    pack_dups = sorted(f"{s}:{i}" for (s, i), n in in_pack.items() if n > 1)
    ok = not missing and not extra and not dup_ids and got_header == header
    return {"objects": len(items), "shard_objects": sum(got.values()), "missing": sum(missing.values()),
            "unexpected_or_duplicated": sum(extra.values()), "duplicate_ids": dup_ids,
            "ids_repeated_in_the_pack_itself": pack_dups, "ok": ok}


def company_overview(c: dict, pack: dict, where: dict[tuple[str, str], list[str]], meta: dict) -> str:
    cid, name = c["company_id"], c["company_name"]
    sup = pack["domain_specific_support_objects"]
    rels = [r for r in pack["company_edge_relationships"] if r["company_id"] == cid]
    paths = [p for p in pack["transmission_paths"] if cid == p["primary_company_id"] or cid in p["company_ids"]]
    bridge = [b for b in sup["financial_bridge"] if b["company_id"] == cid]
    idents = [i for i in sup["financial_identities"] if i["company_id"] == cid]
    fields = [f for f in pack["financial_model_semantic_fields"] if name in f["applies_to"]]
    tax = c["taxonomy"]
    L = [f"# {name} ({c['ticker']}): overview", "",
         f"Pack {meta['domain_pack_id']}, {meta['schema_version']}, as of {meta['as_of'][:10]} "
         f"(state version {meta['state_version']}). Company id `{cid}`.", "",
         f"{c['description']}", "",
         f"Sector {tax['sector']} ({', '.join(tax['subsectors'])}); geography {tax['geographic_scope']}; "
         f"aliases: {', '.join(c['aliases'])}; role tags: {', '.join(c['role_tags'])}; "
         f"primary sector pack `{c['primary_sector_pack_id']}`.", "",
         "## Business composition, segments, and regions", "",
         "Each view splits one total into members. Metric ids are those used in the relationships.", ""]
    for b in bridge:
        extra = [f"residual `{b['residual_metric']}`"] if b["residual_metric"] else []
        extra += [f"eliminations `{b['eliminations_metric']}`"] if b["eliminations_metric"] else []
        L += [f"- **{b['view']}** (`{b['composition_id']}`; {b['basis']}; {b['unit']}, {b['period']}): "
              f"total `{b['total_metric']}` = {', '.join('`' + m + '`' for m in b['member_metrics'])}"
              + (f"; {'; '.join(extra)}" if extra else "")]
    L += ["", f"## Transmission paths ({len(paths)})", "",
          "One line each: id, trigger, steps, edges, and the file that holds it.", ""]
    L += [f"- `{p['path_id']}`: {p['trigger']} ({len(p['ordered_steps'])} steps; edges {', '.join(p['edge_ids'])}); "
          f"in `{where[('transmission_paths', p['path_id'])][0]}`" for p in paths]
    dirs = Counter(r["direction"] for r in rels)
    L += ["", f"## Relationships ({len(rels)})", "",
          f"By direction: {', '.join(f'{k} {v}' for k, v in sorted(dirs.items()))}. Files, in order of edge and then of the metric each link points at:", ""]
    files: dict[str, list[str]] = {}
    for r in rels:
        files.setdefault(where[("company_edge_relationships", r["relationship_id"])][0], []).append(r)
    L += [f"- `{f}`: {len(rs)} relationships; "
          + scope_text(describe([("company_edge_relationships", r) for r in rs])[1]) for f, rs in sorted(files.items())]
    forms = Counter(i["form"] for i in idents)
    L += ["", "## Calculation coverage", "",
          f"{len(bridge)} compositions (above), {len(idents)} identities ({', '.join(f'{k} {v}' for k, v in sorted(forms.items()))}), "
          f"{len(fields)} financial-model fields. Identities, by target metric:", ""]
    L += [f"- `{i['identity_id']}` -> `{i['target_metric']}` ({i['form']})" for i in idents]
    L += ["", f"Identities and compositions are in the `financial_{c['slug']}` files; fields are in "
          "`semantic_fields`. Open the id index to find any of them.", ""]
    return "\n".join(L)


def start_here(pack: dict, meta: dict, rows: list[dict], linked: list[dict], cap_kb: int) -> str:
    cos = ", ".join(f"{c['company_name']} ({c['ticker']})" for c in pack["companies"])
    L = [f"# START HERE: {pack['domain_pack_name']}", "",
         "## What this is", "",
         "A causal world model of the companies below: how drivers (rates, the yen, policy, demand) reach their "
         "profits and prices, with effect sizes, delays, and how sure the model is. It states drivers, exposures, "
         "transmission, and timing. It does not rate, size, or decide.", "",
         f"Covers: {cos}.", "",
         f"Version {meta['schema_version']}; pack `{meta['domain_pack_id']}` (file index {pack['file_index']}); "
         f"model state version {meta['state_version']}, as of {meta['as_of'][:10]}.", "",
         "## If any file fails to load", "",
         "Say so, and name the file. Never answer as if you had read a file that did not load or came back "
         "truncated, empty, or as an error. Every file below is at most "
         f"{cap_kb} KB, so a failure is a real fault to report, not a size limit. The full domain pack "
         "(`../" + meta["pack_file"] + "`) is the machine-import copy and is too large to read: do not use it.", "",
         "## Files", "",
         "| File | Holds | Size | Open it when |", "|---|---|---|---|"]
    L += [f"| `{r['file']}` | {r['holds']} | {kb(r['bytes'])} | {r['when']} |" for r in rows]
    L += [f"| `{r['file']}` | {r['holds']} | {kb(r['bytes'])} | {r['when']} |" for r in linked]
    L += ["", "## Follow an id to its file", "",
          "- A relationship id is `REL_<COMPANY>__<EDGE>_<NAME>`; a path id is `PATH_...`. Open "
          "the `90_index_ids_NN.json` files: `ids` maps every relationship, path, financial composition and "
          "identity, support node and link, and field id (as `section:id`, sorted) to a file code, and `files` "
          "maps the code to the file name. Each index file's header gives its first and last key.",
          "- Without the index: a relationship is in its company's `20_relationships_...` files, ordered by edge, then by the metric it points at: "
          "the header (`reading_shard` line) gives `target_metrics_from` and `target_metrics_to`; a path is in its primary company's `30_paths_...` "
          "files, and the company overview lists each path with its file.",
          "- Every object is in exactly one file, unchanged from the pack, so an id found in one place is the same "
          "object everywhere.", ""]
    return "\n".join(L)


def index_files(where: dict[tuple[str, str], list[str]], budget: int) -> list[tuple[str, str, int]]:
    """The id index as (file name, text, id count): `section:id` -> file code (a list when the pack repeats the id),
    in sorted order, in as many files as the budget needs; each file names its first and last key and maps the codes."""
    names = sorted({n for ns in where.values() for n in ns})
    codes = {n: f"F{k:02d}" for k, n in enumerate(names, 1)}
    entries = [(f"{s}:{i}", line([codes[n] for n in ns] if len(ns) > 1 else codes[ns[0]]), ns)
               for (s, i), ns in sorted(where.items())]
    chunks: list[list[tuple[str, str, list[str]]]] = []
    used, seen = 0, set()
    for k, v, ns in entries:
        n = len(k.encode()) + len(v.encode()) + 6 + sum(len(x) + 12 for x in ns if x not in seen)
        if not chunks or used + n > budget - 800:
            chunks.append([])
            used, seen = 0, set()
            n = len(k.encode()) + len(v.encode()) + 6 + sum(len(x) + 12 for x in ns)
        chunks[-1].append((k, v, ns))
        seen.update(ns)
        used += n
    out = []
    for n, ch in enumerate(chunks, 1):
        files_line = line({codes[x]: x for x in sorted({x for _k, _v, ns in ch for x in ns})})
        head = line({"part": f"{n} of {len(chunks)}", "keys_from": ch[0][0], "keys_to": ch[-1][0],
                     "note": "`section:id` -> file code, or a list of codes when the pack itself repeats the id. "
                             "`files` maps the codes used in this file to file names in the reading folder."})
        body = ",\n".join(f"{json.dumps(k, ensure_ascii=False)}: {v}" for k, v, _ns in ch)
        out.append((f"90_index_ids_{n:02d}.json",
                    f'{{\n"index_shard": {head},\n"files": {files_line},\n"ids": {{\n{body}\n}}\n}}\n', len(ch)))
    return out


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_reading_set(out: Path, ctx: dict, manifest: dict, *, cap_kb: int = 100) -> dict:
    """Write `out/reading/` for this export (after its other files are in `out`), check that the shards cover the
    pack exactly, and record the reading files, with sha256 and size, in `manifest`. Returns the coverage check."""
    pack, ev = ctx["domain_pack"], ctx["evidence"]
    cap = cap_kb * 1024
    pack_file = next(f["file"] for f in manifest["load_order"] if f["source"] == "this export: domain_pack")
    meta = {"domain_pack_id": pack["domain_pack_id"], "schema_version": pack["schema_version"],
            "as_of": ev["as_of"], "state_version": ev["state_version"], "pack_file": pack_file}
    cos = [{**c, "slug": c.get("axelrod_entity_id") or c["company_id"].lower()} for c in pack["companies"]]
    slug_of = {c["company_id"]: c["slug"] for c in cos}
    header, _ = flatten(pack)
    folder = out / FOLDER
    folder.mkdir(parents=True, exist_ok=True)

    fam: dict[tuple[int, str], list[tuple[str, Any, str]]] = {}
    for family, order, s, o, g in route(pack, slug_of):
        fam.setdefault((order, family), []).append((s, o, g))
    entries = [{"file": "00_START_HERE.md", "holds": "This guide", "when": "First, always"}]
    for c in cos:
        entries.append({"file": f"01_overview_{c['slug']}.md",
                        "holds": f"{c['company_name']}: business composition, segments and regions, paths, "
                                 "relationships, calculation coverage",
                        "when": f"Any question about {c['company_name']}; then follow it to the shards"})
    where: dict[tuple[str, str], list[str]] = {}
    docs = []
    for (order, family), its in sorted(fam.items()):
        its.sort(key=lambda t: t[2] if order == 20 else "")
        shards = pack_groups(its, int(cap * 0.88))
        for n, sh in enumerate(shards, 1):
            name = f"{order}_{family}_{n:02d}.json"
            counts, scope = describe(sh)
            info = {**{k: meta[k] for k in ("domain_pack_id", "schema_version", "as_of", "state_version")},
                    "file": name, "part": f"{n} of {len(shards)}", "objects": counts,
                    **scope,
                    **({"pack_header": header} if order == 10 and n == 1 else {}),
                    "note": "Whole objects of the full domain pack, unchanged; each object is in exactly one file."}
            text = render(info, sh)
            (folder / name).write_text(text)
            docs.append(json.loads(text))
            for s, o in sh:
                if (i := oid(s, o)) is not None:
                    where.setdefault((s.removeprefix(SUP), i), []).append(name)
            holds = ", ".join(f"{k} {s.removeprefix(SUP)}" for s, k in counts.items())
            entries.append({"file": name, "holds": f"{family.replace('_', ' ')} {n} of {len(shards)}: {holds}"
                            + (f"; {scope_text(scope)}" if scope else ""), "when": WHEN_ORDER[order]})
    check = verify_coverage(pack, docs)
    if not check["ok"]:
        raise ValueError(f"the shards do not cover the pack: {check}")
    for c in cos:
        (folder / f"01_overview_{c['slug']}.md").write_text(company_overview(c, pack, where, meta))
    for name, text, n_ids in index_files(where, int(cap * 0.88)):
        (folder / name).write_text(text)
        entries.append({"file": name, "holds": f"{n_ids} ids -> file code", "when": WHEN_ORDER[90]})

    linked = []
    for f in manifest["load_order"]:
        if (out / f["file"]).exists():
            holds, when = WHEN[f["source"].split(",")[0]]
            n = (out / f["file"]).stat().st_size
            fmt = {"size": kb(n), "thesis": f.get("thesis_id", ""), "question": f.get("question", "")}
            linked.append({"file": "../" + f["file"], "bytes": n, "holds": holds.format(**fmt), "when": when.format(**fmt)})
    rows = [{**e, "bytes": 0} for e in entries]
    for _ in range(3):  # the guide lists its own size, which its text moves by a digit at most
        (folder / "00_START_HERE.md").write_text(start_here(pack, meta, rows, linked, cap_kb))
        rows = [{**e, "bytes": (folder / e["file"]).stat().st_size} for e in entries]
    manifest["read_first"] = f"{FOLDER}/00_START_HERE.md"
    for f in manifest["load_order"]:
        if f["source"] == "this export: domain_pack":
            f["role"] = "machine_import"
            f["note"] = f"Complete v4.1.4 domain pack for machine import; too large to read. Read {FOLDER}/ instead."
    manifest["reading_set"] = {
        "folder": FOLDER, "start_here": f"{FOLDER}/00_START_HERE.md", "max_file_kb": cap_kb,
        "role": "reading", "coverage_check": check,
        "files": [{"file": f"{FOLDER}/{r['file']}", "bytes": r["bytes"], "sha256": sha256(folder / r["file"])}
                  for r in rows]}
    return check
