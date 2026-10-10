"""annotate4.js -> annotate5.js: a traced superentity outline, a highlighter for rows, gentler exits, and a calmer
five-stage diagram (boxes that never change size, straight arrows centered between them)."""
from pathlib import Path

V = Path(__file__).parent
s = (V / "annotate4.js").read_text()


def rep(a, b, count=1):
    global s
    assert a in s, a[:90]
    s = s.replace(a, b, count)


# -- exits: everything leaves at the pace it arrived, never snapped away --------------------------------------------
n = s.count("320ms cubic-bezier(.5,0,.75,0)")
assert n >= 3, n
s = s.replace("320ms cubic-bezier(.5,0,.75,0)", "560ms cubic-bezier(.45,0,.55,1)")
s = s.replace("later(380, () => g.remove());", "later(620, () => g.remove());")
rep(".vbub.out { transform: scale(0); transition: transform .35s cubic-bezier(.5,0,.75,0); }",
    ".vbub.out { transform: scale(0); transition: transform .5s cubic-bezier(.45,0,.55,1); }")
# the head shrinks back along its own line instead of vanishing
rep("if (hd) hd.setAttribute(\"transform\", `translate(${tx.toFixed(1)} ${ty.toFixed(1)}) scale(0)`);",
    """if (hd) {
        const t0 = performance.now();
        const step = () => {
          const q = Math.min(1, (performance.now() - t0) / 260);
          hd.setAttribute("transform", `translate(${tx.toFixed(1)} ${ty.toFixed(1)}) rotate(${ang.toFixed(1)}) scale(${(1 - q * q).toFixed(3)})`);
          if (q < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
      }""")

# -- the five stages: fixed boxes, straight arrows on the boxes' center line; the current stage lifts, nothing grows --
rep("""  #vstages .vstage { width: 188px; padding: 16px 14px 18px; border-radius: 18px; text-align: center; background: #EEE9E0; border: 3px solid #D9D1C4;
    transform: scale(.94); transition: transform .5s ${SPRING}, background-color .4s, border-color .4s, box-shadow .4s; }""",
    """  #vstages .vstage { box-sizing: border-box; width: 196px; height: 150px; padding: 14px 14px; border-radius: 18px; text-align: center;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    background: #EEE9E0; border: 3px solid #D9D1C4; box-shadow: 0 0 0 ${INK};
    transition: transform .45s ${EASE}, background-color .4s, border-color .4s, box-shadow .45s ${EASE}; }
  #vstages .varr { flex: none; width: 46px; height: 24px; display: block; }
  #vstages .varr path { stroke: #CFC6B8; transition: stroke .4s; }
  #vstages .varr.on path { stroke: ${INK}; }""")
rep("""  #vstages .vstage.cur { transform: scale(1.07); box-shadow: 5px 6px 0 ${INK}; border-color: ${INK}; }
  #vstages .vstage.on:not(.cur) { transform: scale(1); }""",
    """  #vstages .vstage.cur { transform: translateY(-6px); box-shadow: 4px 6px 0 ${INK}; border-color: ${INK}; }""")
rep("""${i ? `<svg width="44" height="24" viewBox="0 0 44 24"><path d="M3 12 C14 4 26 4 37 12" fill="none" stroke="${INK}" stroke-width="3.4" stroke-linecap="round"/><path d="M30 6 L39 12 L30 18" fill="none" stroke="${INK}" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/></svg>` : ""}""",
    """${i ? `<svg class="varr" data-i="${i}" viewBox="0 0 46 24"><path d="M6 12 H38" fill="none" stroke-width="3.2" stroke-linecap="round"/><path d="M31 5 L39 12 L31 19" fill="none" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/></svg>` : ""}""")
rep("""<div style="display:flex;align-items:center;gap:10px">""", """<div style="display:flex;align-items:center;gap:8px">""")
rep("""        el.style.borderColor = k === i ? INK : k < i ? el.dataset.l : "";
      }""", """        el.style.borderColor = k === i ? INK : k < i ? el.dataset.l : "";
      }
      // an arrow is drawn in ink once the stage it leads into has been reached
      for (const a of stageBox?.querySelectorAll(".varr") ?? []) a.classList.toggle("on", +a.dataset.i <= i);""")

# -- targets: "shape:name" is a traced outline ----------------------------------------------------------------------
rep("""    if (sel.startsWith("edge:")) return edgeBetween(...sel.slice(5).split("|"));""",
    """    if (sel.startsWith("edge:")) return edgeBetween(...sel.slice(5).split("|"));
    if (sel.startsWith("shape:")) return shapes[sel.slice(6)]?.box ?? null;""")
rep("""    if (typeof sel !== "string" || sel.startsWith("point:") || sel.startsWith("edge:") || sel.startsWith("union:")) return null;
    const [q, t0] = sel.split("::");""",
    """    if (typeof sel !== "string" || sel.startsWith("point:") || sel.startsWith("edge:") || sel.startsWith("union:") || sel.startsWith("shape:")) return null;
    const [q, t0] = sel.split("::");""")
rep("""  const rectOf = (sel, nth = 0) => {""", """  const shapes = {};                // traced outlines, by name: their box and their points with outward normals
  const rectOf = (sel, nth = 0) => {""")

# -- the highlighter, and the traced superentity --------------------------------------------------------------------
rep("""  .vbub.out {""", """  .vmark { position: fixed; z-index: 9984; pointer-events: none; border-radius: 5px; mix-blend-mode: multiply;
    transform: scaleX(0); transform-origin: 0 50%; transition: transform .42s ${EASE}, opacity .5s ease; }
  .vmark.in { transform: scaleX(1); }
  .vmark.out { opacity: 0; }
  .vbub.out {""")
rep("""    liveTips() {""", r"""    // a highlighter stroke across a row: the words stay as they are, the row takes the color
    marker({ id, at, color = "#C9BCF5", nth = 0, pad = 2 }) {
      const r = rectOf(at, nth);
      if (!r) throw new Error(`no target ${at}`);
      const m = add("div", "vmark");
      m.style.left = `${r.l - pad}px`;
      m.style.top = `${r.t - pad}px`;
      m.style.width = `${r.w + 2 * pad}px`;
      m.style.height = `${r.h + 2 * pad}px`;
      m.style.background = color;
      m.getBoundingClientRect();
      requestAnimationFrame(() => m.classList.add("in"));
      m.__retract = () => { m.classList.add("out"); later(560, () => m.remove()); };
      keep(id, m);
    },
    // a superentity, traced in ink along its own outline; the outline is named for a bubble to point at
    traceHull({ id, tab }) {
      const t = [...document.querySelectorAll("g.hull-tab")].find((e) => (e.textContent || "").includes(tab) && vis(e));
      if (!t) throw new Error(`no hull tab ${tab}`);
      const key = t.getAttribute("data-instance");
      const path = [...document.querySelectorAll("g.hull")].find((g) => g.getAttribute("data-instance") === key && !g.classList.contains("hull-tab"))?.querySelector("path.shape");
      if (!path) throw new Error(`no hull ${tab}`);
      // the outer outline: the longest of the path's pieces
      const m = path.getScreenCTM();
      const parts = (path.getAttribute("d") || "").split(/(?=M)/).filter((p) => p.trim());
      let best = null;
      for (const d of parts) {
        const p = document.createElementNS(NS, "path");
        p.setAttribute("d", d);
        path.parentNode.appendChild(p);
        const L = p.getTotalLength();
        if (!best || L > best.L) best = { p, L };
        else p.remove();
      }
      for (const p of path.parentNode.querySelectorAll("path:not(.shape)")) if (p !== best.p) p.remove();
      const N = 180;
      const pts = [];
      for (let i = 0; i < N; i++) {
        const q = best.p.getPointAtLength((best.L * i) / N);
        pts.push([q.x * m.a + q.y * m.c + m.e, q.x * m.b + q.y * m.d + m.f]);
      }
      best.p.remove();
      const cx = pts.reduce((a, p) => a + p[0], 0) / N;
      const cy = pts.reduce((a, p) => a + p[1], 0) / N;
      const poly = pts.map(([x, y], i) => {
        const [ax, ay] = pts[(i - 1 + N) % N];
        const [bx, by] = pts[(i + 1) % N];
        let nx = by - ay;
        let ny = -(bx - ax);
        const nn = Math.hypot(nx, ny) || 1;
        nx /= nn; ny /= nn;
        if (nx * (x - cx) + ny * (y - cy) < 0) { nx = -nx; ny = -ny; }
        return [x + nx * 3, y + ny * 3, nx, ny];
      });
      const xs = poly.map((p) => p[0]);
      const ys = poly.map((p) => p[1]);
      const box = { l: Math.min(...xs), t: Math.min(...ys), r: Math.max(...xs), b: Math.max(...ys) };
      Object.assign(box, { cx: (box.l + box.r) / 2, cy: (box.t + box.b) / 2, w: box.r - box.l, h: box.b - box.t });
      shapes[id] = { box, poly };
      circles.set(`shape:${id}`, { cx: box.cx, cy: box.cy, rx: box.w / 2, ry: box.h / 2, n: 12, poly });
      // start at the top-left and go once around, a little past where it began
      let s0 = 0;
      for (let i = 1; i < N; i++) if (poly[i][0] + poly[i][1] < poly[s0][0] + poly[s0][1]) s0 = i;
      const seq = [];
      for (let i = 0; i <= N + 6; i++) seq.push(poly[(s0 + i) % N]);
      const d = `M${seq.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join(" L")}`;
      const g = document.createElementNS(NS, "g");
      const halo = document.createElementNS(NS, "path");
      const line = document.createElementNS(NS, "path");
      halo.setAttribute("class", "halo"); line.setAttribute("class", "line");
      halo.setAttribute("d", d); line.setAttribute("d", d);
      line.style.strokeWidth = "3.6";
      line.style.strokeLinejoin = halo.style.strokeLinejoin = "round";
      g.append(halo, line);
      svg.appendChild(g);
      const L = line.getTotalLength();
      for (const p of [halo, line]) { p.style.strokeDasharray = `${L} ${L + 20}`; p.style.strokeDashoffset = `${L}`; }
      requestAnimationFrame(() => { for (const p of [halo, line]) { p.style.transition = `stroke-dashoffset 900ms ${EASE}`; p.style.strokeDashoffset = "0"; } });
      g.__retract = () => {
        circles.delete(`shape:${id}`);
        delete shapes[id];
        for (const p of [halo, line]) { p.style.transition = "stroke-dashoffset 560ms cubic-bezier(.45,0,.55,1)"; p.style.strokeDashoffset = `${-L}`; }
        later(620, () => g.remove());
      };
      keep(id, g);
    },
    liveTips() {""")

(V / "annotate5.js").write_text(s)
print("ok")
