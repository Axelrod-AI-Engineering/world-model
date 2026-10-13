"""Give every Mermaid diagram in docs/ the look of the app's flowcharts (docs/flowchart.svg).

Write a flowchart with plain Mermaid and mark it up in three ways; this script adds the rest.

- Node classes, as `A["..."]:::step`:
  - start (purple): where a flow begins
  - step: a concrete step
  - opt (dashed): a step that runs only sometimes
  - check (butter): a yes/no question
  - store (peach): a commit or stored data
  - done: an end
  - wm (green), ltm (blue), both (pink): which memory a step belongs to
  - ext: something outside the system
- The happy path, drawn with `==>`, becomes thick and purple. Side paths keep `-->`, and optional ones `-.->`.
- Edge labels go in pipes: `-->|yes|`.

The script prepends a theme block and the class definitions to each diagram, and appends a
`linkStyle` for every `==>` edge. It replaces what it added before, so it is safe to rerun.

    uv run python scripts/docs/style_mermaid.py            # restyle docs/ in place
    uv run python scripts/docs/style_mermaid.py --check    # exit 1 if any diagram is stale
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BEGIN, TAIL, END = "%% style: begin (scripts/docs/style_mermaid.py)", "%% style: classes and happy path", "%% style: end"
HAPPY = "stroke:#7C64C4,stroke-width:2.6px,color:#5B4A99"
CYCLE = "stroke:#C0605A,stroke-width:1.8px"

BASE = {
    "fontSize": "14px", "primaryColor": "#FFFDF8", "primaryBorderColor": "#C9BFAF",
    "primaryTextColor": "#2F2A25", "lineColor": "#857C70", "textColor": "#2F2A25",
}
# No fontFamily: a directive's font list is read as one family name and falls back to a serif,
# so Mermaid's default (sans-serif) stack is kept. Single quotes anywhere drop the whole directive.
BY_KIND = {
    "flowchart": {"secondaryColor": "#F7F2EA", "tertiaryColor": "#FBF8F2", "edgeLabelBackground": "#F7F2EA", "clusterBkg": "#F7F2EA", "clusterBorder": "#E4DACB",
                  "titleColor": "#665E54"},
    "sequenceDiagram": {
        "actorBkg": "#DAD0F4", "actorBorder": "#7C64C4", "actorLineColor": "#C9BFAF", "signalColor": "#857C70",
        "labelBoxBkgColor": "#F5EAC6", "labelBoxBorderColor": "#D2BB72", "noteBkgColor": "#F5EAC6",
        "noteBorderColor": "#D2BB72", "activationBkgColor": "#E1ECDF", "sequenceNumberColor": "#FFFDF8"},
    "stateDiagram-v2": {"secondaryColor": "#F7F2EA", "tertiaryColor": "#FBF8F2", "transitionColor": "#857C70",
                        "transitionLabelColor": "#665E54", "compositeBackground": "#F7F2EA"},
    "classDiagram": {"secondaryColor": "#F7F2EA", "tertiaryColor": "#FBF8F2"},
}


def init(kind: str) -> str:
    theme = {**BASE, **BY_KIND.get("flowchart" if kind == "graph" else kind, {})}
    return "%%{init: " + json.dumps({"theme": "base", "themeVariables": theme}) + "}%%"


CLASSES = {
    "start": "fill:#DAD0F4,stroke:#7C64C4,stroke-width:1.5px,color:#2F2A25",
    "step": "fill:#FFFDF8,stroke:#C9BFAF,stroke-width:1.3px,color:#2F2A25",
    "opt": "fill:#FFFDF8,stroke:#C9BFAF,stroke-width:1.3px,stroke-dasharray:5 4,color:#2F2A25",
    "check": "fill:#F5EAC6,stroke:#D2BB72,stroke-width:1.3px,color:#2F2A25,font-weight:600",
    "store": "fill:#F7E1D3,stroke:#E0B092,stroke-width:1.3px,color:#2F2A25",
    "done": "fill:#FBF8F2,stroke:#93897C,stroke-width:1.6px,color:#2F2A25",
    "wm": "fill:#E1ECDF,stroke:#A9C6A9,stroke-width:1.3px,color:#3E6A46",
    "ltm": "fill:#DCE6F0,stroke:#A9BFD6,stroke-width:1.3px,color:#3B5B7C",
    "both": "fill:#F5E4E9,stroke:#D9A9B8,stroke-width:1.3px,color:#93465F",
    "ext": "fill:#FBF8F2,stroke:#7C64C4,stroke-width:1.3px,stroke-dasharray:2 3,color:#2F2A25",
}

SKIP = re.compile(r"^\s*(subgraph|end\b|direction|classDef|class\s|linkStyle|style\s|%%|flowchart|graph)")
OPS = re.compile(r"(<-->|==>|-->|-\.->|---)(\|[^|]*\|)?")


def edges(body: list[str]) -> list[str]:
    """Each link's operator, in the order Mermaid numbers links (A --> B & C is two links)."""
    out: list[str] = []
    for line in body:
        if SKIP.match(line):
            continue
        s = re.sub(r'"[^"]*"', '""', line)
        if re.search(r'--\s*"|==\s*"|--\s+\w+\s+-->', line):
            raise ValueError(f"write edge labels as -->|label|, not inline: {line.strip()}")
        parts = OPS.split(s)
        # parts: seg, op, label, seg, op, label, seg ...
        segs = parts[0::3]
        ops = parts[1::3]
        for i, op in enumerate(ops):
            n = len(segs[i].split("&")) * len(segs[i + 1].split("&"))
            out += [op] * n
    return out


def style(block: str) -> str:
    lines = block.split("\n")
    for begin in (BEGIN, TAIL):                         # drop what we added last time
        marks = [ln.strip() for ln in lines]
        if begin in marks:
            i = marks.index(begin)
            j = marks.index(END, i)
            lines = lines[:i] + lines[j + 1:]
    lines = [ln for ln in lines if not (ln.strip().startswith("linkStyle") and (HAPPY in ln or CYCLE in ln))]
    while lines and not lines[-1].strip():
        lines.pop()
    kind = next((ln.split()[0] for ln in lines if ln.strip() and not ln.lstrip().startswith("%%")), "")
    out = [BEGIN, init(kind), END] + lines
    if kind in ("flowchart", "graph"):
        used = set(re.findall(r":::(\w+)", "\n".join(lines)))
        tail = [f"  classDef {k} {v}" for k, v in CLASSES.items() if k in used]
        ops = edges(lines)
        happy = [i for i, op in enumerate(ops) if op == "==>"]
        cycles = [i for i, op in enumerate(ops) if op == "<-->"]
        if happy:
            tail.append(f"  linkStyle {','.join(map(str, happy))} {HAPPY}")
        if cycles:
            tail.append(f"  linkStyle {','.join(map(str, cycles))} {CYCLE}")
        if tail:
            out += ["  " + TAIL] + tail + ["  " + END]
    return "\n".join(out) + "\n"


def restyle(text: str) -> str:
    return re.sub(r"```mermaid\n(.*?)```", lambda m: "```mermaid\n" + style(m.group(1)) + "```", text, flags=re.S)


def main() -> int:
    check = "--check" in sys.argv
    stale = []
    for path in sorted((ROOT / "docs").rglob("*.md")):
        if "archive" in path.parts:
            continue
        text = path.read_text()
        if "```mermaid" not in text:
            continue
        new = restyle(text)
        if new != text:
            stale.append(path.relative_to(ROOT))
            if not check:
                path.write_text(new)
    for p in stale:
        print(("stale: " if check else "styled: ") + str(p))
    return 1 if (check and stale) else 0


if __name__ == "__main__":
    sys.exit(main())
