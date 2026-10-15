"""The README's picture (docs/flowchart.svg): learning, inference, and the architecture on one page.

Learning and inference are drawn from their flows' stages (flows/__init__.py, flows/inference.py), so the
picture follows the flowcharts; the architecture is the module map of docs/design. It uses the classes and
palette of render.py, so it reads like the demo's own flowcharts. The happy path is drawn thick and purple.
"""

from __future__ import annotations

from html import escape

from axelrod_wm.flows import INFERENCE, WORLD_MODEL
from axelrod_wm.flows.render import CAPTION, LINE, PAD_X, PAD_Y, STYLE, _arrow, _wrap

WIDTH = 1240
BAND_W = 556                 # each process band
LEFT = 24                    # learning band's left edge
RIGHT = WIDTH - 24 - BAND_W  # inference band's left edge
MAIN_W = 372                 # a stage box
SIDE_W = 128                 # a side exit
GAP = 30

OVERVIEW_STYLE = """
.ov-stage { font: 600 13.5px var(--font-ui, 'Instrument Sans', 'Helvetica Neue', sans-serif); fill: var(--ink, #2F2A25); }
.ov-chip { font: 500 12.5px var(--font-ui, 'Instrument Sans', 'Helvetica Neue', sans-serif); fill: var(--ink, #2F2A25); }
.ov-num { font: 600 10.5px var(--font-mono, 'IBM Plex Mono', ui-monospace, monospace); fill: var(--ink-3, #93897C); }
.fl-node.wm .fl-box { fill: var(--wm-fill, #E1ECDF); stroke: var(--wm-line, #A9C6A9); }
.fl-node.ltm .fl-box { fill: var(--ltm-fill, #DCE6F0); stroke: var(--ltm-line, #A9BFD6); }
.fl-node.inf .fl-box { fill: var(--front-fill, #F5E4E9); stroke: var(--front-line, #D9A9B8); }
.fl-node.ext .fl-box { fill: var(--paper, #FBF8F2); stroke: var(--real-line, #7C64C4); stroke-dasharray: 2 3; }
.fl-edge.happy { stroke: var(--real-line, #7C64C4); stroke-width: 2.6; }
.fl-arrow.happy { fill: var(--real-line, #7C64C4); }
.fl-edge.dashed { stroke-dasharray: 4 4; }
"""

# The module map (docs/design/README.md), foundation first, so imports point up: (number, name, look).
LAYERS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ("5 · Interfaces", [("M14", "Views · API · CLI", "step"), ("M15", "Context layer (MCP)", "step"),
                        ("M16", "Web: Learn · Predict", "step")]),
    ("4 · Runtime", [("M12", "Runtime · the day loop", "decision"), ("M13", "Services: review · update · thesis", "decision")]),
    ("3 · Engines", [("M05", "Intake", "step"), ("M06", "Shared read", "step"), ("M07", "Dynamics", "step"),
                     ("M08", "Learning · WM", "wm"), ("M09", "Learning · LTM", "ltm"), ("M10", "Inference", "inf"),
                     ("M11", "Evaluation", "step")]),
    ("2 · State", [("M03", "Memory: working · long-term", "store"), ("M04", "Repo: ledger · snapshots · branches", "store")]),
    ("1 · Domain", [("M02", "Model: entities · interactions · superentities", "step")]),
    ("0 · Foundation", [("M01", "Core · ports: every slot's contract", "start")]),
]
SIDE_MODULE = ("M17", "Demo (side)", "ext")


class _Out:
    def __init__(self) -> None:
        self.parts: list[str] = []

    def add(self, s: str) -> None:
        self.parts.append(s)


def _box(o: _Out, x: float, y: float, w: float, kind: str, title: str, cap: str = "", extra: str = "",
         title_cls: str = "ov-stage") -> float:
    """Draw a node; returns its height."""
    inset = 26 if kind == "decision" else PAD_X
    tl = _wrap(title, w - 2 * inset, 13.5)
    cl = _wrap(cap, w - 2 * inset - 8, 12.4) if cap else []   # monospace sets wider than the default estimate
    h = 2 * PAD_Y + LINE * len(tl) + CAPTION * len(cl) + (6 if kind == "decision" else 0)
    base = {"wm": "step", "ltm": "step", "inf": "step", "ext": "step"}.get(kind, kind)
    cls = f"fl-node {base} {kind} {extra}".strip()
    o.add(f'<g class="{cls}"><title>{escape(title + (": " + cap if cap else ""))}</title>')
    if kind == "decision":
        d = 16
        pts = f"{x + d},{y} {x + w - d},{y} {x + w},{y + h / 2} {x + w - d},{y + h} {x + d},{y + h} {x},{y + h / 2}"
        o.add(f'<polygon class="fl-box" points="{pts}"/>')
    elif kind in ("start", "end"):
        o.add(f'<rect class="fl-box" x="{x}" y="{y}" width="{w}" height="{h}" rx="{min(h / 2, 18)}"/>')
    elif kind == "store":
        o.add(f'<rect class="fl-box" x="{x}" y="{y}" width="{w}" height="{h}" rx="5"/>')
    else:
        o.add(f'<rect class="fl-box" x="{x}" y="{y}" width="{w}" height="{h}" rx="8"/>')
    ty = y + PAD_Y + LINE - 3.5 + (3 if kind == "decision" else 0)
    for i, line in enumerate(tl):
        o.add(f'<text class="{title_cls}" x="{x + w / 2}" y="{ty + i * LINE}" text-anchor="middle">{escape(line)}</text>')
    for i, line in enumerate(cl):
        o.add(f'<text class="fl-cap" x="{x + w / 2}" y="{ty + len(tl) * LINE - 1 + i * CAPTION}" '
              f'text-anchor="middle">{escape(line)}</text>')
    o.add("</g>")
    return h


def _down(o: _Out, x: float, y1: float, y2: float, happy: bool = True, label: str = "") -> None:
    cls = "happy" if happy else ""
    o.add(f'<path class="fl-edge {cls}" d="M{x},{y1} L{x},{y2 - 1}"/>' + _arrow(x, y2, "down").replace(
        'class="fl-arrow"', f'class="fl-arrow {cls}"'))
    if label:
        o.add(f'<text class="fl-elabel" x="{x + 8}" y="{(y1 + y2) / 2 + 4}">{escape(label)}</text>')


def _band(o: _Out, x: float, y: float, w: float, h: float, title: str, alt: bool = False) -> None:
    o.add(f'<rect class="fl-phase-band{" alt" if alt else ""}" x="{x}" y="{y}" width="{w}" height="{h}" rx="8"/>')
    o.add(f'<text class="fl-phase" x="{x + 16}" y="{y + 22}">{escape(title)}</text>')


def _process(o: _Out, x0: float, y0: float, start: str, stages: list[tuple[str, str, str]], end: str) -> dict:
    """A process column: a start, its stages (kind, title, caption), an end. Returns each box's geometry."""
    mx = x0 + 24
    cx = mx + MAIN_W / 2
    y = y0 + 40
    geo = {}
    h = _box(o, mx + 40, y, MAIN_W - 80, "start", start)
    geo["start"] = (mx + 40, y, MAIN_W - 80, h)
    y += h
    for i, (kind, title, cap) in enumerate(stages):
        _down(o, cx, y, y + GAP)
        y += GAP
        dashed = "optional" if kind == "optional" else ""
        h = _box(o, mx, y, MAIN_W, "step" if kind == "optional" else kind, title, cap, extra=dashed)
        geo[i] = (mx, y, MAIN_W, h)
        y += h
    _down(o, cx, y, y + GAP)
    y += GAP
    h = _box(o, mx + 40, y, MAIN_W - 80, "end", end)
    geo["end"] = (mx + 40, y, MAIN_W - 80, h)
    geo["bottom"] = y + h
    geo["side_x"] = mx + MAIN_W + 26
    return geo


def render_overview_svg() -> str:
    o = _Out()
    title = "Axelrod World Model"
    summary = ("One causal world model of the economy, built like version control. Backend users teach it: each "
               "event's learning is staged, a person checks every change down to the third-order ripple, and only "
               "what they approve is committed. Everyone else asks it: a thesis runs on a branch that is never merged.")
    o.add(f'<text class="fl-title" x="{LEFT}" y="38">{title}</text>')
    sum_lines = _wrap(summary, WIDTH - 2 * LEFT, 12.5)
    for i, line in enumerate(sum_lines):
        o.add(f'<text class="fl-sum" x="{LEFT}" y="{62 + 18 * i}">{escape(line)}</text>')
    y = 62 + 18 * len(sum_lines) + 8

    # key
    key = [("start", "start"), ("decision", "a check"), ("store", "a commit"), ("wm", "working memory"),
           ("ltm", "long-term memory"), ("inf", "inference"), ("optional", "only sometimes")]
    kx = LEFT
    for kind, label in key:
        base = "step" if kind in ("wm", "ltm", "inf", "optional") else kind
        dash = ' style="stroke-dasharray: 5 4"' if kind == "optional" else ""
        o.add(f'<g class="fl-node {base} {kind}"><rect class="fl-box" x="{kx}" y="{y}" width="22" height="14" rx="4"{dash}/></g>'
              f'<text class="fl-legend" x="{kx + 28}" y="{y + 11}">{label}</text>')
        kx += 28 + 6.2 * len(label) + 22
    o.add(f'<path class="fl-edge happy" d="M{kx},{y + 7} L{kx + 26},{y + 7}"/>'
          f'<text class="fl-legend" x="{kx + 34}" y="{y + 11}">the happy path</text>')
    y += 34

    # learning and inference, side by side
    learn_stages = []
    for p in WORLD_MODEL.phases:
        kind = {"working": "wm", "long_term": "ltm", "review": "decision", "commit": "store"}.get(p.id, "step")
        learn_stages.append((kind, p.title, p.output))
    inf_stages = [("optional" if p.id == "score" else "inf" if p.id != "pose" else "step", p.title, p.output)
                  for p in INFERENCE.phases]
    top = y
    body = _Out()
    lg = _process(body, LEFT, top, "A market event, or a backend user's edit", learn_stages, "A new version")
    ig = _process(body, RIGHT, top, "A what-if question, asked in Predict", inf_stages[:-1], "A forecast and its brief")

    # inference: the optional score after the end
    ex, ey, ew, eh = ig["end"]
    sx, sw = RIGHT + 24, MAIN_W
    _down(body, ex + ew / 2, ey + eh, ey + eh + GAP, happy=False, label="if someone acts on it")
    s_kind, s_title, s_cap = inf_stages[-1]
    sh = _box(body, sx, ey + eh + GAP, sw, "step", s_title, s_cap, extra="optional")
    ig["bottom"] = ey + eh + GAP + sh

    # learning: the review's side exits fork right of it: up to re-stage, down to reject
    rx, ry, rw, rh = lg[3]
    cx_, cy_, cw_, ch_ = lg[4]
    ry_mid = ry + rh / 2
    fork_x = lg["side_x"] + 22
    wx, wy, ww, wh = lg[1]
    body.add(f'<path class="fl-edge" d="M{rx + rw},{ry_mid} L{fork_x},{ry_mid} L{fork_x},{wy + wh / 2} L{wx + ww + 1},{wy + wh / 2}"/>'
             + _arrow(wx + ww, wy + wh / 2, "left"))
    body.add(f'<text class="fl-elabel" x="{fork_x + 8}" y="{(ry_mid + wy + wh / 2) / 2}">deselect some:</text>'
             f'<text class="fl-elabel" x="{fork_x + 8}" y="{(ry_mid + wy + wh / 2) / 2 + 14}">re-stage</text>')
    rej_y = cy_ + ch_ / 2 - 20
    _box(body, lg["side_x"], rej_y, SIDE_W, "end", "Rejected: nothing changes", title_cls="ov-chip")
    body.add(f'<path class="fl-edge" d="M{fork_x},{ry_mid} L{fork_x},{rej_y - 1}"/>' + _arrow(fork_x, rej_y, "down"))
    body.add(f'<text class="fl-elabel" x="{fork_x + 8}" y="{(ry_mid + rej_y) / 2 + 4}">reject</text>')

    # the bridge: inference reads a branch of a committed version
    nx, ny, nw, nh = lg["end"]
    ix, iy, iw, ih = ig[1]
    gx = (LEFT + BAND_W + RIGHT) / 2
    body.add(f'<path class="fl-edge happy" d="M{nx + nw},{ny + nh / 2} L{gx},{ny + nh / 2} L{gx},{iy + ih / 2} '
             f'L{ix - 1},{iy + ih / 2}"/>' + _arrow(ix, iy + ih / 2, "right").replace('class="fl-arrow"', 'class="fl-arrow happy"'))
    for j, line in enumerate(["inference reads a branch of", "a committed version; never merged"]):
        body.add(f'<text class="fl-elabel" x="{nx + nw + 12}" y="{ny + nh / 2 + 20 + 14 * j}">{line}</text>')

    bottom = max(lg["bottom"], ig["bottom"]) + 24
    _band(o, LEFT, top, BAND_W, bottom - top, "Learning · backend users teach it")
    _band(o, RIGHT, top, BAND_W, bottom - top, "Inference · everyone else asks it")
    o.parts += body.parts

    # architecture
    y = bottom + 24
    row_h, label_w = 46, 130
    arch_h = 40 + row_h * len(LAYERS) + 16
    _band(o, LEFT, y, WIDTH - 2 * LEFT, arch_h, "Architecture · 17 modules in six layers (docs/design)")
    ry = y + 40
    for k, (layer, mods) in enumerate(reversed(LAYERS)):
        o.add(f'<rect class="fl-phase-band{" alt" if k % 2 else ""}" x="{LEFT + 8}" y="{ry}" width="{WIDTH - 2 * LEFT - 16}" '
              f'height="{row_h - 6}" rx="6"/>')
        o.add(f'<text class="fl-phase" x="{LEFT + 22}" y="{ry + 25}">{escape(layer)}</text>')
        cx = LEFT + 16 + label_w
        items = mods + ([SIDE_MODULE] if layer.startswith("4") else [])
        for num, name, kind in items:
            w = max(96, 6.6 * len(name) + 48)
            base = "step" if kind in ("wm", "ltm", "inf", "ext") else kind
            if kind == "ext":
                cx = WIDTH - LEFT - 16 - w - 56
            o.add(f'<g class="fl-node {base} {kind}"><title>{num} {escape(name)}</title>'
                  f'<rect class="fl-box" x="{cx}" y="{ry + 6}" width="{w}" height="28" rx="7"/>'
                  f'<text class="ov-num" x="{cx + 10}" y="{ry + 24}">{num}</text>'
                  f'<text class="ov-chip" x="{cx + 38}" y="{ry + 24.5}">{escape(name)}</text></g>')
            cx += w + 12
        ry += row_h
    ax = WIDTH - LEFT - 34
    o.add(f'<path class="fl-edge happy" d="M{ax},{ry - 18} L{ax},{y + 52}"/>'
          + _arrow(ax, y + 50, "up").replace('class="fl-arrow"', 'class="fl-arrow happy"'))
    o.add(f'<text class="fl-elabel" x="{ax - 8}" y="{y + 34}" text-anchor="end">imports point up only</text>')
    height = y + arch_h + 20

    head = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height:.0f}" width="{WIDTH}" '
            f'height="{height:.0f}" role="img" aria-labelledby="fl-overview-t fl-overview-d" class="fl-flow" data-flow="overview">',
            f'<title id="fl-overview-t">{title}: learning, inference, and the architecture</title>'
            f'<desc id="fl-overview-d">{escape(summary)}</desc>',
            f"<style>{STYLE}{OVERVIEW_STYLE}</style>",
            f'<rect width="{WIDTH}" height="{height:.0f}" fill="var(--sheet, #FFFDF8)"/>']
    return "\n".join(head + o.parts + ["</svg>"]) + "\n"


__all__ = ["render_overview_svg"]
