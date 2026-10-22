"""Search the supplied material for each input a company's transitions still need, before declaring it missing.

    uv run python scripts/construction/inputs.py sally_demo --entities toyota --corpus data/sally_data \\
        [--files <file> ... | --dirs <folder> ...] [--extra-terms "eligible import volume=import units,CBU imports"] \\
        [--exclude construction bench] [--top 5]

Reads the world's files (never edits them), collects the inputs of every link that touches the company's values
(`transition.unresolved`), parses the files (axelrod_wm.ingest.parse) and scores each line of each page, sheet, or slide
against the input's name, its words, and any extra terms (context/construction.search_inputs: plain, deterministic
keyword scoring). Writes <corpus>/construction/<company>/input_search.json and .md (the candidate passages per input, with
file and location) and prints a suggested status per input: candidates found -> found_not_connected (confirm and bind
it); nothing found -> not_disclosed_in_reviewed_sources, with the files and queries searched.

Files are --files, else every supported file under --dirs, else under --corpus; relative paths are read against
--corpus. Folders named in --exclude (default: construction, bench) are skipped. The report holds client text: it is
written only under the corpus folder and refused inside a tracked part of the repository.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from axelrod_wm.clients import find_world
from axelrod_wm.context.construction import input_needs, search_inputs, search_markdown
from axelrod_wm.engine.initialize import ConstructionSpec, resolve_path, world_taxonomy_dir
from axelrod_wm.ingest.parse import ParseError, parse, supported


def world_dir(world: str) -> Path:
    p = resolve_path(world)
    return p if p.is_dir() else find_world(world) or resolve_path(f"data/worlds/{world}")


def extra_terms(pairs: list[str]) -> dict[str, list[str]]:
    """"input=term1,term2" -> {input: [term1, term2]} (an input's name may hold spaces; the first "=" splits)."""
    out: dict[str, list[str]] = {}
    for p in pairs:
        name, _, terms = p.partition("=")
        out.setdefault(name.strip(), []).extend(t.strip() for t in terms.split(",") if t.strip())
    return out


def corpus_files(corpus: Path, files: list[str], dirs: list[str], exclude: list[str]) -> list[Path]:
    def at(p: str) -> Path:
        q = Path(p)
        return q if q.is_absolute() else corpus / q

    if files:
        return [at(f) for f in files]
    roots = [at(d) for d in dirs] or [corpus]
    out = []
    for root in roots:
        for f in sorted(root.rglob("*")):
            rel = f.relative_to(root).parts
            if f.is_file() and supported(f.name) and not any(x in exclude for x in rel[:-1]):
                out.append(f)
    return out


def tracked(path: Path) -> bool:
    """Whether `path` lies in the repository and git would track it (it is not ignored)."""
    r = subprocess.run(["git", "-C", str(path.parent), "check-ignore", "-q", str(path)], capture_output=True)
    inside = subprocess.run(["git", "-C", str(path.parent), "rev-parse", "--is-inside-work-tree"], capture_output=True)
    return inside.returncode == 0 and r.returncode == 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("world", help="a world name (data/worlds/<name>) or folder")
    ap.add_argument("--entities", nargs="+", required=True)
    ap.add_argument("--corpus", type=Path, required=True, help="the client's material; the report is written under it")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--files", nargs="+", default=[])
    src.add_argument("--dirs", nargs="+", default=[])
    ap.add_argument("--extra-terms", nargs="*", default=[], help='"input name=term1,term2"')
    ap.add_argument("--exclude", nargs="*", default=["construction", "bench"], help="folder names to skip")
    ap.add_argument("--top", type=int, default=5)
    a = ap.parse_args(argv)

    world = world_dir(a.world)
    spec = ConstructionSpec.load(world, world_taxonomy_dir(world))
    paths = corpus_files(a.corpus, a.files, a.dirs, a.exclude)
    docs = []
    for f in paths:
        try:
            docs.append((str(f.relative_to(a.corpus)) if f.is_relative_to(a.corpus) else str(f),
                         parse(f.read_bytes(), f.name)))
        except (ParseError, OSError) as exc:
            print(f"  skipped {f.name}: {exc}")
    print(f"parsed {len(docs)} of {len(paths)} file(s)")
    extra = extra_terms(a.extra_terms)
    for eid in a.entities:
        ent = next((e for e in spec.entities if e.id == eid), None)
        if ent is None:
            print(f"{eid}: no such entity in {world}")
            return 1
        own = {s.id for s in ent.subentities}
        needs = input_needs([(x.id, x.transition) for x in sorted(spec.interactions, key=lambda x: x.id)
                             if x.source in own or x.target in own])
        rows = search_inputs(needs, docs, extra, a.top)
        out = a.corpus / "construction" / eid
        out.mkdir(parents=True, exist_ok=True)
        if tracked(out / "input_search.json"):
            print(f"REFUSED {out} is tracked by git; the report holds client text")
            return 1
        (out / "input_search.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
        (out / "input_search.md").write_text(search_markdown(eid, rows))
        print(f"{eid}: {len(needs)} input(s), {len(rows)} searched; report in {out}")
        for r in rows:
            found = f"{len(r['candidates'])} candidate(s) in {', '.join(r['suggested_found_in'])}" if r["candidates"] \
                else f"nothing in {len(r['searched_files'])} file(s)"
            print(f"  {r['input']}: now {r['status']}; suggested {r['suggested_status']} ({found})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
