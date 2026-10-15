"""Render the design's diagrams to SVG, in the look of the app's flowcharts (docs/flowchart.svg).

Each diagram is a Mermaid source in docs/design/diagrams/*.mmd, and the docs show the rendered SVG beside it.
Write a source in plain Mermaid with three kinds of markup; this script adds the rest when it renders:

- Node classes, as `A["..."]:::step`:
  start (purple, where a flow begins) · step · opt (dashed, runs only sometimes) · check (butter, a yes/no
  question) · store (peach, a commit or stored data) · done (an end) · wm (green), ltm (blue), inf (pink):
  working memory, long-term memory, inference · ext (dotted, outside the system)
- The happy path, drawn `==>`, becomes thick and purple. Declare it first, so the layout keeps it straight.
- Edge labels go in pipes: `-->|yes|`.

    uv run --with playwright python scripts/docs/diagrams.py            # render every stale diagram
    uv run python scripts/docs/diagrams.py --check                      # exit 1 if an SVG is stale (no browser)
    uv run --with playwright python scripts/docs/diagrams.py --all      # render them all

Rendering needs a Chromium for Playwright (`playwright install chromium`, or set CHROMIUM to a binary) and
downloads Mermaid once into ~/.cache/axelrod. Labels are SVG text, not HTML, so the files display as images.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "docs" / "design" / "diagrams"
MERMAID = "11.4.1"
MERMAID_URL = f"https://cdn.jsdelivr.net/npm/mermaid@{MERMAID}/dist/mermaid.min.js"
CACHE = Path.home() / ".cache" / "axelrod" / f"mermaid-{MERMAID}.min.js"
STYLE_VERSION = "4"          # bump when the look below changes, so every SVG re-renders
BACKGROUND = "#FFFDF8"

HAPPY = "stroke:#7C64C4,stroke-width:2.6px,color:#5B4A99"
CYCLE = "stroke:#C0605A,stroke-width:1.8px"

# No fontFamily: a directive's font list is read as one family name and falls back to a serif, so Mermaid's
# default sans-serif stack is kept. Single quotes anywhere in a directive drop it entirely.
BASE = {"fontSize": "14px", "primaryColor": "#FFFDF8", "primaryBorderColor": "#C9BFAF",
        "primaryTextColor": "#2F2A25", "lineColor": "#857C70", "textColor": "#2F2A25",
        "secondaryColor": "#F7F2EA", "tertiaryColor": "#FBF8F2"}
BY_KIND = {
    "flowchart": {"edgeLabelBackground": "#F7F2EA", "clusterBkg": "#F7F2EA", "clusterBorder": "#E4DACB",
                  "titleColor": "#665E54"},
    "sequenceDiagram": {
        "actorBkg": "#DAD0F4", "actorBorder": "#7C64C4", "actorLineColor": "#C9BFAF", "signalColor": "#857C70",
        "labelBoxBkgColor": "#F5EAC6", "labelBoxBorderColor": "#D2BB72", "noteBkgColor": "#F5EAC6",
        "noteBorderColor": "#D2BB72", "activationBkgColor": "#E1ECDF", "sequenceNumberColor": "#FFFDF8"},
    "stateDiagram-v2": {"transitionColor": "#857C70", "transitionLabelColor": "#665E54",
                        "compositeBackground": "#F7F2EA"},
    "classDiagram": {},
}
CLASSES = {
    "start": "fill:#DAD0F4,stroke:#7C64C4,stroke-width:1.5px,color:#2F2A25",
    "step": "fill:#FFFDF8,stroke:#C9BFAF,stroke-width:1.3px,color:#2F2A25",
    "opt": "fill:#FFFDF8,stroke:#C9BFAF,stroke-width:1.3px,stroke-dasharray:5 4,color:#2F2A25",
    "check": "fill:#F5EAC6,stroke:#D2BB72,stroke-width:1.3px,color:#2F2A25,font-weight:600",
    "store": "fill:#F7E1D3,stroke:#E0B092,stroke-width:1.3px,color:#2F2A25",
    "done": "fill:#FBF8F2,stroke:#93897C,stroke-width:1.6px,color:#2F2A25",
    "wm": "fill:#E1ECDF,stroke:#A9C6A9,stroke-width:1.3px,color:#3E6A46",
    "ltm": "fill:#DCE6F0,stroke:#A9BFD6,stroke-width:1.3px,color:#3B5B7C",
    "inf": "fill:#F5E4E9,stroke:#D9A9B8,stroke-width:1.3px,color:#93465F",
    "ext": "fill:#FBF8F2,stroke:#7C64C4,stroke-width:1.3px,stroke-dasharray:2 3,color:#2F2A25",
}

SKIP = re.compile(r"^\s*(subgraph|end\b|direction|classDef|class\s|linkStyle|style\s|%%|flowchart|graph)")
OPS = re.compile(r"(<-->|==>|-->|-\.->|---)(\|[^|]*\|)?")


def kind_of(src: str) -> str:
    return next((ln.split()[0] for ln in src.splitlines() if ln.strip() and not ln.lstrip().startswith("%%")), "")


def edges(lines: list[str]) -> list[str]:
    """Each link's operator, in the order Mermaid numbers links (A --> B & C is two links)."""
    out: list[str] = []
    for line in lines:
        if SKIP.match(line):
            continue
        if re.search(r'--\s*"|==\s*"|--\s+\w+\s+-->', line):
            raise ValueError(f"write edge labels as -->|label|, not inline: {line.strip()}")
        parts = OPS.split(re.sub(r'"[^"]*"', '""', line))
        segs, ops = parts[0::3], parts[1::3]
        for i, op in enumerate(ops):
            out += [op] * (len(segs[i].split("&")) * len(segs[i + 1].split("&")))
    return out


def styled(src: str) -> str:
    """The source with the theme, the classes it uses, and the happy path's link styles."""
    kind = kind_of(src)
    theme = {**BASE, **BY_KIND.get("flowchart" if kind == "graph" else kind, {})}
    lines = src.rstrip().splitlines()
    out = ["%%{init: " + json.dumps({"theme": "base", "themeVariables": theme}) + "}%%", *lines]
    if kind in ("flowchart", "graph"):
        used = set(re.findall(r":::(\w+)", src))
        out += [f"  classDef {k} {v}" for k, v in CLASSES.items() if k in used]
        ops = edges(lines)
        for op, look in (("==>", HAPPY), ("<-->", CYCLE)):
            idx = [i for i, o in enumerate(ops) if o == op]
            if idx:
                out.append(f"  linkStyle {','.join(map(str, idx))} {look}")
    return "\n".join(out) + "\n"


def digest(src: str) -> str:
    return hashlib.sha256(f"{MERMAID}|{STYLE_VERSION}|{src}".encode()).hexdigest()[:16]


def stamp_of(svg_path: Path) -> str | None:
    if not svg_path.exists():
        return None
    m = re.search(r"<!-- source sha: (\w+) -->", svg_path.read_text()[:600])
    return m.group(1) if m else None


def finish(svg: str, name: str, sha: str) -> str:
    """Give the SVG an explicit size and an opaque background, and stamp its source."""
    m = re.search(r'viewBox="([^"]+)"', svg)
    x, y, w, h = (float(v) for v in m.group(1).replace(",", " ").split())
    svg = re.sub(r'<svg ([^>]*?)width="100%"', rf'<svg \1width="{w:.0f}" height="{h:.0f}"', svg, count=1)
    svg = re.sub(r' style="max-width: [\d.]+px;"', "", svg, count=1)
    # the background goes first, right after <svg ...>: a sequence diagram draws its actors and lifelines before its
    # <style>, so a background placed after the style covered them
    head_end = svg.index(">", svg.index("<svg")) + 1
    bg = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{BACKGROUND}"/>'
    svg = svg[:head_end] + bg + svg[head_end:]
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<!-- source sha: {sha} -->\n'
            f'<!-- generated from {name}.mmd by scripts/docs/diagrams.py; edit the source, not this file -->\n'
            + svg + "\n")


def mermaid_js() -> str:
    if not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(MERMAID_URL, timeout=60) as r:   # pinned version, read once
            CACHE.write_bytes(r.read())
    return CACHE.read_text()


def render(todo: list[Path]) -> None:
    import asyncio

    from playwright.async_api import async_playwright

    async def go() -> None:
        async with async_playwright() as p:
            exe = os.environ.get("CHROMIUM")
            browser = await p.chromium.launch(executable_path=exe) if exe else await p.chromium.launch()
            page = await browser.new_page()
            await page.set_content("<div id=o></div>")
            await page.add_script_tag(content=mermaid_js())
            await page.evaluate("mermaid.initialize({startOnLoad:false, htmlLabels:false, flowchart:{htmlLabels:false}})")
            for src_path in todo:
                src = src_path.read_text()
                svg = await page.evaluate("async ([id, s]) => (await mermaid.render(id, s)).svg",
                                          [f"dg-{src_path.stem}", styled(src)])
                src_path.with_suffix(".svg").write_text(finish(svg, src_path.stem, digest(src)))
                print(f"rendered {src_path.relative_to(ROOT).with_suffix('.svg')}")
            await browser.close()

    asyncio.run(go())


def main() -> int:
    sources = sorted(SOURCES.glob("*.mmd"))
    stale = [s for s in sources if stamp_of(s.with_suffix(".svg")) != digest(s.read_text())]
    if "--check" in sys.argv:
        for s in stale:
            print(f"stale: {s.relative_to(ROOT).with_suffix('.svg')} (run scripts/docs/diagrams.py)")
        return 1 if stale else 0
    todo = sources if "--all" in sys.argv else stale
    if todo:
        for s in todo:
            styled(s.read_text())            # fail fast on a malformed source before starting a browser
        render(todo)
    orphans = [p for p in SOURCES.glob("*.svg") if not p.with_suffix(".mmd").exists()]
    for p in orphans:
        print(f"orphan (no source): {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
