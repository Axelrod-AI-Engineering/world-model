"""Draw a flow (flows/__init__.py) as a standalone SVG.

Layout: the main line runs down the middle column in the flow's order. A decision's answers leave it on
three sides: down to the next step on the main line, left along a lane to a step further down (the
bypass that skips an optional step), or right to a side node (an exit, or a detour that rejoins the main
line just below). Phases are bands behind the nodes; their names sit at the left.

Optional steps have dashed borders; a badge says which memory a step writes (WM, LTM). Every node
carries data-node, data-kind, and data-trace attributes, so a page can light the path one market event
took (class fl-hit) and dim the rest (fl-miss). Colors are CSS variables with the demo's palette as
fallbacks, so the file reads the same in the docs and inside the demo.
"""

from __future__ import annotations

from html import escape

from axelrod_wm.flows import Flow, FlowNode

W_MAIN = 340
W_SIDE = 236
PAD_X = 14
PAD_Y = 9
LINE = 16
CAPTION = 14
GAP = 28              # vertical gap between nodes on the main line
PHASE_GAP = 22        # extra gap where a phase changes
TITLE_COL = 118       # the phase names' column
LANE = 15             # spacing of the left lanes
SIDE_GAP = 74         # from the main column to the side column
FONT = 13.0
CHAR = 0.53           # average glyph width as a fraction of the font size (a safe overestimate)

MEMORY_BADGE = {"working": "WM", "long_term": "LTM", "both": "WM + LTM"}

STYLE = """
.fl-title { font: 700 18px var(--font-head, 'Bricolage Grotesque', 'Avenir Next', 'Segoe UI', sans-serif); fill: var(--ink, #2F2A25); }
.fl-sum { font: 400 12.5px var(--font-ui, 'Instrument Sans', 'Helvetica Neue', sans-serif); fill: var(--ink-2, #665E54); }
.fl-phase-band { fill: var(--fl-band, #F7F2EA); }
.fl-phase-band.alt { fill: var(--fl-band-alt, #FBF8F2); }
.fl-phase { font: 600 10.5px var(--font-mono, 'IBM Plex Mono', ui-monospace, monospace); letter-spacing: .07em; fill: var(--ink-3, #93897C); text-transform: uppercase; }
.fl-box { fill: var(--sheet, #FFFDF8); stroke: var(--rule-strong, #C9BFAF); stroke-width: 1.3; }
.fl-node.optional .fl-box { stroke-dasharray: 5 4; }
.fl-node.decision .fl-box { fill: var(--butter-fill, #F5EAC6); stroke: var(--butter-line, #D2BB72); }
.fl-node.start .fl-box { fill: var(--real-fill, #DAD0F4); stroke: var(--real-line, #7C64C4); }
.fl-node.end .fl-box { fill: var(--paper, #FBF8F2); stroke: var(--ink-3, #93897C); stroke-width: 1.6; }
.fl-node.store .fl-box { fill: var(--out-fill, #F7E1D3); stroke: var(--out-line, #E0B092); }
.fl-node.link .fl-box { fill: var(--paper, #FBF8F2); stroke: var(--real-line, #7C64C4); stroke-dasharray: 2 3; }
.fl-label { font: 500 13px var(--font-ui, 'Instrument Sans', 'Helvetica Neue', sans-serif); fill: var(--ink, #2F2A25); }
.fl-node.decision .fl-label { font-weight: 600; }
.fl-cap { font: 400 10.5px var(--font-mono, 'IBM Plex Mono', ui-monospace, monospace); fill: var(--ink-3, #93897C); }
.fl-badge rect { stroke-width: 1; }
.fl-badge text { font: 600 9.5px var(--font-mono, 'IBM Plex Mono', ui-monospace, monospace); }
.fl-badge.working rect { fill: var(--wm-fill, #E1ECDF); stroke: var(--wm-line, #A9C6A9); }
.fl-badge.working text { fill: var(--wm-ink, #3E6A46); }
.fl-badge.long_term rect { fill: var(--ltm-fill, #DCE6F0); stroke: var(--ltm-line, #A9BFD6); }
.fl-badge.long_term text { fill: var(--ltm-ink, #3B5B7C); }
.fl-badge.both rect { fill: var(--front-fill, #F5E4E9); stroke: var(--front-line, #D9A9B8); }
.fl-badge.both text { fill: var(--front-ink, #93465F); }
.fl-edge { fill: none; stroke: var(--edge, #857C70); stroke-width: 1.3; }
.fl-edge.side { stroke-dasharray: none; }
.fl-elabel { font: 500 10.5px var(--font-mono, 'IBM Plex Mono', ui-monospace, monospace); fill: var(--ink-2, #665E54);
  paint-order: stroke; stroke: var(--fl-band, #F7F2EA); stroke-width: 4px; stroke-linejoin: round; }
.fl-arrow { fill: var(--edge, #857C70); }
.fl-legend { font: 400 11px var(--font-ui, 'Instrument Sans', 'Helvetica Neue', sans-serif); fill: var(--ink-2, #665E54); }
.fl-node.fl-hit .fl-box { stroke: var(--real-line, #7C64C4); stroke-width: 2.4; }
.fl-node.fl-miss { opacity: .38; }
.fl-edge.fl-hit { stroke: var(--real-line, #7C64C4); stroke-width: 2.2; }
.fl-edge.fl-miss { opacity: .3; }
"""


def _wrap(text: str, width_px: float, font: float = FONT) -> list[str]:
    per_line = max(8, int(width_px / (font * CHAR)))
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > per_line:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    if cur:
        lines.append(cur)
    return lines or [""]


def _caption(n: FlowNode) -> str:
    bits = [b for b in (f"if {n.when}" if n.when else "", n.cadence) if b]
    return " · ".join(bits)


class _Box:
    def __init__(self, node: FlowNode, x: float, y: float, w: float, lines: list[str], cap: str) -> None:
        self.node, self.x, self.y, self.w, self.lines = node, x, y, w, lines
        self.caps = _wrap(cap, w - 2 * PAD_X, 10.5) if cap else []
        self.h = 2 * PAD_Y + LINE * len(lines) + CAPTION * len(self.caps)
        if node.kind == "decision":
            self.h += 6

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def right(self) -> float:
        return self.x + self.w


def _badge_width(label: str) -> float:
    return 9 + 6.2 * len(label)


def _text_width(n: FlowNode, w: float) -> float:
    inset = 26 if n.kind == "decision" else PAD_X
    if n.kind in ("start", "end", "link"):
        inset = 20
    if n.writes:
        inset = max(inset, _badge_width(MEMORY_BADGE[n.writes]) + 14)
    return w - 2 * inset


def layout(flow: Flow, bare: bool = False) -> tuple[dict[str, _Box], dict, float, float]:
    main = [n for n in flow.nodes if not n.side]
    index = {n.id: i for i, n in enumerate(main)}
    side_parent: dict[str, str] = {}
    for e in flow.edges:
        tgt = flow.node(e.dst)
        if tgt.side and e.dst not in side_parent:
            side_parent[e.dst] = e.src

    # left lanes for edges that skip down the main line (interval coloring)
    skips = []
    for e in flow.edges:
        if e.src in index and e.dst in index and index[e.dst] != index[e.src] + 1:
            skips.append(e)
    lanes: dict[tuple[str, str], int] = {}
    taken: list[list[tuple[int, int]]] = []
    for e in sorted(skips, key=lambda e: (abs(index[e.dst] - index[e.src]), index[e.src])):
        lo, hi = sorted((index[e.src], index[e.dst]))
        for k, spans in enumerate(taken):
            if all(hi < a or lo > b for a, b in spans):
                spans.append((lo, hi))
                lanes[(e.src, e.dst)] = k
                break
        else:
            taken.append([(lo, hi)])
            lanes[(e.src, e.dst)] = len(taken) - 1
    n_lanes = max(1, len(taken))

    # a lane's answer is written between the lanes and the decision it leaves, clear of every lane line
    lane_labels = [e.label for e in skips if e.label]
    room = max([0] + [int(len(lab) * 10.5 * CHAR * 1.1) + 14 for lab in lane_labels])
    left = 16 + TITLE_COL + n_lanes * LANE + 12 + room
    # the gap to the side column fits the longest label on an edge into it
    side_labels = [e.label for e in flow.edges if flow.node(e.dst).side and e.label]
    gap = max([SIDE_GAP] + [int(len(lab) * 10.5 * CHAR * 1.15) + 46 for lab in side_labels])
    side_x = left + W_MAIN + gap
    top = 0.0
    title_lines = _wrap(flow.title, 900, 18)
    width = side_x + W_SIDE + 24
    sum_lines = _wrap(flow.summary, width - 32, 12.5)
    top = 30 + 22 * (len(title_lines) - 1) + 18 * len(sum_lines) + 18
    if bare:                       # a page that supplies its own title and summary
        top, title_lines, sum_lines = 4.0, [], []

    boxes: dict[str, _Box] = {}
    y = top + 14
    side_bottom = y
    prev_phase = None
    phase_spans: dict[str, list[float]] = {}
    for n in main:
        if prev_phase is not None and n.phase != prev_phase:
            y = max(y, side_bottom + GAP) + PHASE_GAP
        b = _Box(n, left, y, W_MAIN, _wrap(n.label, _text_width(n, W_MAIN)), _caption(n))
        boxes[n.id] = b
        span = phase_spans.setdefault(n.phase, [b.y, b.bottom])
        span[0], span[1] = min(span[0], b.y), max(span[1], b.bottom)
        y = b.bottom + GAP
        # this node's side nodes, stacked in the side column
        for s in [m for m in flow.nodes if m.side and side_parent.get(m.id) == n.id]:
            sb = _Box(s, side_x, 0, W_SIDE, _wrap(s.label, _text_width(s, W_SIDE)), _caption(s))
            sb.y = max(b.cy - sb.h / 2, b.y, side_bottom + 16 if side_bottom > top + 14 else b.y)
            boxes[s.id] = sb
            side_bottom = sb.bottom
            sp = phase_spans.setdefault(s.phase, [sb.y, sb.bottom])
            sp[0], sp[1] = min(sp[0], sb.y), max(sp[1], sb.bottom)
            y = max(y, sb.bottom + GAP)
        prev_phase = n.phase
    height = max(b.bottom for b in boxes.values()) + 18
    lane_out: dict[str, list[tuple[str, str]]] = {}
    lane_in: dict[str, list[tuple[str, str]]] = {}
    for key in sorted(lanes, key=lambda k: lanes[k]):
        lane_out.setdefault(key[0], []).append(key)
        lane_in.setdefault(key[1], []).append(key)
    return boxes, {"lanes": lanes, "index": index, "left": left, "room": room, "side_x": side_x, "phase_spans": phase_spans,
                   "title_lines": title_lines, "sum_lines": sum_lines, "top": top, "lane_out": lane_out,
                   "lane_in": lane_in}, width, height


def _arrow(x: float, y: float, direction: str) -> str:
    s = 5.5
    if direction == "down":
        pts = f"{x - s * .75},{y - s} {x + s * .75},{y - s} {x},{y}"
    elif direction == "right":
        pts = f"{x - s},{y - s * .75} {x - s},{y + s * .75} {x},{y}"
    elif direction == "left":
        pts = f"{x + s},{y - s * .75} {x + s},{y + s * .75} {x},{y}"
    else:
        pts = f"{x - s * .75},{y + s} {x + s * .75},{y + s} {x},{y}"
    return f'<polygon class="fl-arrow" points="{pts}"/>'


def _shape(b: _Box) -> str:
    k = b.node.kind
    x, y, w, h = b.x, b.y, b.w, b.h
    if k == "decision":
        d = 16
        pts = f"{x + d},{y} {x + w - d},{y} {x + w},{y + h / 2} {x + w - d},{y + h} {x + d},{y + h} {x},{y + h / 2}"
        return f'<polygon class="fl-box" points="{pts}"/>'
    if k in ("start", "end", "link"):
        return f'<rect class="fl-box" x="{x}" y="{y}" width="{w}" height="{h}" rx="{min(h / 2, 18)}"/>'
    if k == "store":
        return (f'<rect class="fl-box" x="{x}" y="{y}" width="{w}" height="{h}" rx="5"/>'
                f'<line class="fl-box" x1="{x}" y1="{y + 5}" x2="{x + w}" y2="{y + 5}"/>')
    return f'<rect class="fl-box" x="{x}" y="{y}" width="{w}" height="{h}" rx="8"/>'


def _node_svg(b: _Box) -> str:
    n = b.node
    cls = ["fl-node", n.kind, "mandatory" if n.mandatory else "optional"]
    title = n.label + (f" — {n.detail}" if n.detail else "")
    if not n.mandatory:
        title += f" (optional: runs only if {n.when})" if n.when else " (optional)"
    attrs = (f'data-node="{escape(n.id)}" data-kind="{n.kind}" data-phase="{escape(n.phase)}" '
             f'data-trace="{escape(" ".join(n.trace))}" data-component="{escape(n.component)}" '
             f'data-writes="{n.writes}" data-mandatory="{str(n.mandatory).lower()}"')
    if n.link:
        attrs += f' data-link="{escape(n.link)}"'
    out = [f'<g class="{" ".join(cls)}" {attrs}><title>{escape(title)}</title>', _shape(b)]
    ty = b.y + PAD_Y + LINE - 3.5 + (3 if n.kind == "decision" else 0)
    label_lines = list(b.lines)
    if n.kind == "link":
        label_lines[-1] = label_lines[-1] + " →"
    for i, line in enumerate(label_lines):
        out.append(f'<text class="fl-label" x="{b.cx}" y="{ty + i * LINE}" text-anchor="middle">{escape(line)}</text>')
    for i, cap in enumerate(b.caps):
        out.append(f'<text class="fl-cap" x="{b.cx}" y="{ty + len(label_lines) * LINE - 1 + i * CAPTION}" '
                   f'text-anchor="middle">{escape(cap)}</text>')
    if n.writes:
        label = MEMORY_BADGE[n.writes]
        bw = _badge_width(label)
        bx, by = b.right - bw - 8, b.y + (b.h - 16) / 2
        said = label.replace("WM", "working memory").replace("LTM", "long-term memory")
        out.append(f'<g class="fl-badge {n.writes}"><title>Writes {said}</title><rect x="{bx}" y="{by}" '
                   f'width="{bw}" height="16" rx="8"/><text x="{bx + bw / 2}" y="{by + 11.5}" '
                   f'text-anchor="middle">{label}</text></g>')
    out.append("</g>")
    return "".join(out)


def _edge_svg(flow: Flow, e, boxes: dict[str, _Box], meta: dict) -> str:
    a, b = boxes[e.src], boxes[e.dst]
    index, lanes, left = meta["index"], meta["lanes"], meta["left"]
    label = escape(e.label)
    parts: list[str] = []
    attrs = f'data-src="{escape(e.src)}" data-dst="{escape(e.dst)}"'
    if not a.node.side and not b.node.side:
        if index[e.dst] == index[e.src] + 1:                      # straight down the main line
            parts.append(f'<path class="fl-edge" {attrs} d="M{a.cx},{a.bottom} V{b.y - 1}"/>')
            parts.append(_arrow(a.cx, b.y - 1, "down"))
            if label:
                parts.append(f'<text class="fl-elabel" x="{a.cx + 9}" y="{(a.bottom + b.y) / 2 + 4}">{label}</text>')
        else:                                                      # a lane on the left
            key = (e.src, e.dst)
            lane_x = left - meta["room"] - 12 - LANE * lanes[key]
            outs = meta["lane_out"][e.src]
            k = outs.index(key)
            dy = (k - (len(outs) - 1) / 2) * 20                    # each answer leaves at its own height
            y0 = a.cy + dy
            x0 = a.x + (16 * abs(dy) / (a.h / 2) if a.node.kind == "decision" else 0)
            ins = meta["lane_in"][e.dst]
            j = ins.index(key)
            ex, ey = b.x + 26 + 12 * j, b.y - 9 - 5 * j            # and enters its target from the top
            parts.append(f'<path class="fl-edge" {attrs} d="M{x0:.1f},{y0:.1f} H{lane_x} V{ey} H{ex} V{b.y - 1}"/>')
            parts.append(_arrow(ex, b.y - 1, "down"))
            if label:                                              # just left of the decision, above its own line
                parts.append(f'<text class="fl-elabel" x="{x0 - 6:.1f}" y="{y0 - 4:.1f}" text-anchor="end">'
                             f'{label}</text>')
    elif b.node.side:                                              # out to a side node
        mid = a.right + 30
        if abs(b.cy - a.cy) < 1:
            d = f"M{a.right},{a.cy} H{b.x - 1}"
        else:
            d = f"M{a.right},{a.cy} H{mid} V{b.cy} H{b.x - 1}"
        parts.append(f'<path class="fl-edge side" {attrs} d="{d}"/>')
        parts.append(_arrow(b.x - 1, b.cy, "right"))
        if label:
            parts.append(f'<text class="fl-elabel" x="{b.x - 10}" y="{b.cy - 7}" text-anchor="end">{label}</text>')
    else:                                                          # a side node rejoins the main line
        ex = b.right - 40
        ym = b.y - 12
        parts.append(f'<path class="fl-edge side" {attrs} d="M{a.cx},{a.bottom} V{ym} H{ex} V{b.y - 1}"/>')
        parts.append(_arrow(ex, b.y - 1, "down"))
        if label:
            parts.append(f'<text class="fl-elabel" x="{a.cx + 8}" y="{a.bottom + 14}">{label}</text>')
    return f'<g class="fl-edge-g" {attrs}>' + "".join(parts) + "</g>"


def render_svg(flow: Flow, bare: bool = False) -> str:
    boxes, meta, width, height = layout(flow, bare)
    legend_y = height + 8
    height = legend_y + 40
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" width="{width:.0f}" '
           f'height="{height:.0f}" role="img" aria-labelledby="fl-{flow.id}-t fl-{flow.id}-d" class="fl-flow" '
           f'data-flow="{flow.id}">',
           f'<title id="fl-{flow.id}-t">{escape(flow.title)}</title><desc id="fl-{flow.id}-d">{escape(flow.summary)}</desc>',
           f"<style>{STYLE}</style>",
           f'<rect width="{width:.0f}" height="{height:.0f}" fill="var(--sheet, #FFFDF8)"/>']
    for i, line in enumerate(meta["title_lines"]):
        out.append(f'<text class="fl-title" x="16" y="{30 + 22 * i}">{escape(line)}</text>')
    y0 = 30 + 22 * (len(meta["title_lines"]) - 1) + 22
    for i, line in enumerate(meta["sum_lines"]):
        out.append(f'<text class="fl-sum" x="16" y="{y0 + 18 * i}">{escape(line)}</text>')
    # phase bands, then their names
    spans = meta["phase_spans"]
    ordered = [(p.id, p.title) for p in flow.phases if p.id in spans]
    for k, (pid, title) in enumerate(ordered):
        lo, hi = spans[pid]
        nxt = spans[ordered[k + 1][0]][0] if k + 1 < len(ordered) else hi + 24
        top_y = lo - 12
        bot_y = (hi + nxt) / 2 if k + 1 < len(ordered) else hi + 12
        if k > 0:
            prev_hi = spans[ordered[k - 1][0]][1]
            top_y = (prev_hi + lo) / 2
        alt = " alt" if k % 2 else ""
        out.append(f'<rect class="fl-phase-band{alt}" x="8" y="{top_y:.1f}" width="{width - 16:.0f}" '
                   f'height="{bot_y - top_y:.1f}" rx="6" data-phase="{escape(pid)}"/>')
        for j, line in enumerate(_wrap(title, TITLE_COL - 18, 10.5)):
            out.append(f'<text class="fl-phase" x="20" y="{top_y + 20 + 14 * j:.1f}">{escape(line)}</text>')
    for e in flow.edges:
        out.append(_edge_svg(flow, e, boxes, meta))
    for b in boxes.values():
        out.append(_node_svg(b))
    # legend
    lx, ly = 20, legend_y + 14
    out.append(f'<g class="fl-legend-g" transform="translate({lx},{ly})">'
               '<rect x="0" y="-11" width="26" height="15" rx="4" class="fl-box"/>'
               '<text class="fl-legend" x="32" y="0">step (always runs)</text>'
               '<rect x="150" y="-11" width="26" height="15" rx="4" class="fl-box" stroke-dasharray="4 3"/>'
               '<text class="fl-legend" x="182" y="0">optional step</text>'
               '<polygon points="282,-3.5 288,-11 302,-11 308,-3.5 302,4 288,4" class="fl-box" '
               'style="fill: var(--butter-fill, #F5EAC6); stroke: var(--butter-line, #D2BB72)"/>'
               '<text class="fl-legend" x="314" y="0">decision</text>'
               '<rect x="380" y="-11" width="26" height="15" rx="3" class="fl-box" '
               'style="fill: var(--out-fill, #F7E1D3); stroke: var(--out-line, #E0B092)"/>'
               '<text class="fl-legend" x="412" y="0">commit</text>'
               '<text class="fl-legend" x="470" y="0">WM / LTM: writes working / long-term memory</text>'
               '</g>')
    out.append("</svg>")
    return "\n".join(out)



def flow_markdown(flow: Flow) -> str:
    """The flow as text: each stage with its input and output, then its steps (for `axelrod flows`)."""
    lines = [f"# {flow.title}", "", flow.summary, ""]
    for ph in flow.phases:
        lines += [f"## {ph.title}", ""]
        if ph.input or ph.output:
            lines += [f"- **Input:** {ph.input}", f"- **Output:** {ph.output}", ""]
        for n in flow.nodes:
            if n.phase != ph.id:
                continue
            tags = [t for t in (f"if {n.when}" if n.when else "", n.cadence, f"`{n.component}`" if n.component else "",
                                MEMORY_BADGE.get(n.writes, "")) if t]
            mark = {"decision": "◆ ", "store": "▣ ", "start": "▶ ", "end": "■ "}.get(n.kind, "")
            lines.append(f"1. {mark}{n.label}" + (f" ({'; '.join(tags)})" if tags else ""))
        lines.append("")
    return "\n".join(lines)


__all__ = ["flow_markdown", "layout", "render_svg"]
