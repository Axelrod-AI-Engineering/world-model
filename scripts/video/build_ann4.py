"""annotate4.js: annotate3.js with exact text targets, tip-first arrows, traced edges, and a geometry verifier."""
from pathlib import Path

V = Path(__file__).parent
s = (V / "annotate3.js").read_text()


def rep(a, b):
    global s
    assert a in s, a[:90]
    s = s.replace(a, b, 1)


# -- targets: "sel::words" is the box of those words; "union:sel" is every match together; "point:id" a traced point --
start = s.index("  const rectOf = (sel, nth = 0) => {")
end = s.index("  function edgeBetween(aSel, bSel) {")
s = s[:start] + r'''  const points = {};               // named points (a traced edge's middle)
  const vis = (el) => {
    if (!el || !el.isConnected) return false;
    const b = el.getBoundingClientRect();
    if (!(b.width || b.height) || b.bottom < 0 || b.top > innerHeight || b.right < 0 || b.left > innerWidth) return false;
    const cx = (b.left + b.right) / 2;
    const cy = (b.top + b.bottom) / 2;
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.display === "none" || cs.visibility === "hidden" || e.hidden) return false;
      // a scrolling or clipping ancestor must show the element's middle
      if (e !== el && /(auto|scroll|hidden|clip)/.test(cs.overflowY + cs.overflowX)) {
        const a = e.getBoundingClientRect();
        if (cx < a.left || cx > a.right || cy < a.top || cy > a.bottom) return false;
      }
    }
    return true;
  };
  const box = (b) => ({ l: b.left, t: b.top, r: b.right, b: b.bottom, cx: (b.left + b.right) / 2, cy: (b.top + b.bottom) / 2, w: b.width, h: b.height });
  // the screen box of `txt` inside `el`: the first line it sits on (a phrase is pointed at where it starts)
  function wordsBox(el, txt, line = false) {
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const i = n.nodeValue.indexOf(txt);
      if (i < 0) continue;
      const r = document.createRange();
      r.setStart(n, i);
      r.setEnd(n, i + txt.length);
      const rs = [...r.getClientRects()].filter((b) => b.width > 2 && b.height > 2);
      if (!rs.length) continue;
      let out = box(rs[0]);
      if (line) {
        // every piece of text in the element on the same line
        const all = document.createRange();
        all.selectNodeContents(el);
        const same = [...all.getClientRects()].filter((b) => b.width > 1 && b.height > 2 && Math.abs((b.top + b.bottom) / 2 - out.cy) < out.h * 0.45);
        const l = Math.min(out.l, ...same.map((b) => b.left));
        const rr = Math.max(out.r, ...same.map((b) => b.right));
        out = { ...out, l, r: rr, cx: (l + rr) / 2, w: rr - l };
      }
      return { ...out, text: true };
    }
    return null;
  }
  const rectOf = (sel, nth = 0) => {
    if (sel && typeof sel === "object" && sel.pt) {
      const [x, y] = sel.pt;
      return { l: x - 6, t: y - 6, r: x + 6, b: y + 6, cx: x, cy: y, w: 12, h: 12 };
    }
    if (typeof sel !== "string") return null;
    if (sel.startsWith("point:")) {
      const p = points[sel.slice(6)];
      return p ? { l: p[0] - 3, t: p[1] - 3, r: p[0] + 3, b: p[1] + 3, cx: p[0], cy: p[1], w: 6, h: 6 } : null;
    }
    if (sel.startsWith("edge:")) return edgeBetween(...sel.slice(5).split("|"));
    if (sel.startsWith("union:")) {
      const bs = [...document.querySelectorAll(sel.slice(6))].filter(vis).map((e) => e.getBoundingClientRect());
      if (!bs.length) return null;
      const l = Math.min(...bs.map((b) => b.left)), t = Math.min(...bs.map((b) => b.top));
      const r = Math.max(...bs.map((b) => b.right)), b2 = Math.max(...bs.map((b) => b.bottom));
      return { l, t, r, b: b2, cx: (l + r) / 2, cy: (t + b2) / 2, w: r - l, h: b2 - t };
    }
    if (sel.includes("::")) {
      let [q, txt] = sel.split("::");
      const whole = txt.endsWith("@");
      const line = txt.endsWith("$");
      if (whole || line) txt = txt.slice(0, -1);
      const els = [...document.querySelectorAll(q)].filter((e) => (e.textContent || "").includes(txt) && vis(e));
      const el = els[nth] ?? els[0];
      if (!el) return null;
      if (whole) return box(el.getBoundingClientRect());
      return wordsBox(el, txt, line) ?? box(el.getBoundingClientRect());
    }
    const els = [...document.querySelectorAll(sel)].filter(vis);
    const el = els[nth] ?? els[0];
    if (el && el.classList.contains("vbadge")) {
      const l = parseFloat(el.style.left);
      const t = parseFloat(el.style.top);
      return { l, t, r: l + el.offsetWidth, b: t + el.offsetHeight, cx: l + el.offsetWidth / 2, cy: t + el.offsetHeight / 2, w: el.offsetWidth, h: el.offsetHeight, badge: true };
    }
    return el ? box(el.getBoundingClientRect()) : null;
  };
  const elOf = (sel, nth = 0) => {
    if (typeof sel !== "string" || sel.startsWith("point:") || sel.startsWith("edge:") || sel.startsWith("union:")) return null;
    const [q, t0] = sel.split("::");
    const txt = t0 ? t0.replace(/[@$]$/, "") : t0;
    const els = [...document.querySelectorAll(q)].filter((e) => (!txt || (e.textContent || "").includes(txt)) && vis(e));
    return els[nth] ?? els[0] ?? null;
  };
''' + s[end:]

# -- arrows: computed tip first; the head sits on the curve's own end tangent, its point exactly at the tip -----------
start = s.index("  function drawCurve(id, x1, y1, x2, y2,")
end = s.index("  // -- layout: one set of rules for every callout")
s = s[:start] + r'''  const geom = [];                 // every arrow drawn: where it starts, its tip, its direction, what it points at
  const HEAD = 17;
  function drawCurve(id, x1, y1, tx, ty, { bend = 0.14, head = true, dur = 650, delay = 0, target = null, sel = null, n1 = null, n2 = null } = {}) {
    const dx = tx - x1;
    const dy = ty - y1;
    const L = Math.hypot(dx, dy) || 1;
    // a short arrow bows less, so its end stays straight enough for the head
    const b = L < 90 ? bend * (L / 90) : bend;
    // it leaves its start square to the side it starts from, and arrives square to what it points at (level for words),
    // so the head always points straight in
    const [c1, c2] = n1 && n2 ? controls(x1, y1, n1, tx, ty, n2)
      : [[x1 + dx * 0.3 - dy * b, y1 + dy * 0.3 + dx * b], [x1 + dx * 0.7 - dy * b, y1 + dy * 0.7 + dx * b]];
    let ux = tx - c2[0];
    let uy = ty - c2[1];
    const un = Math.hypot(ux, uy) || 1;
    ux /= un; uy /= un;
    const hl = head ? Math.min(HEAD, Math.max(13, un * 0.75)) : 0;
    // the line ends where the head begins, on the segment from c2 to the tip, so it meets the head straight on
    const ex = tx - ux * hl;
    const ey = ty - uy * hl;
    const d = `M${x1.toFixed(1)} ${y1.toFixed(1)} C${c1[0].toFixed(1)} ${c1[1].toFixed(1)} ${c2[0].toFixed(1)} ${c2[1].toFixed(1)} ${ex.toFixed(1)} ${ey.toFixed(1)}`;
    const g = document.createElementNS(NS, "g");
    const halo = document.createElementNS(NS, "path");
    const line = document.createElementNS(NS, "path");
    halo.setAttribute("class", "halo");
    line.setAttribute("class", "line");
    halo.setAttribute("d", d);
    line.setAttribute("d", d);
    g.append(halo, line);
    svg.appendChild(g);
    const len = line.getTotalLength();
    for (const p of [halo, line]) {
      p.style.strokeDasharray = `${len} ${len + 20}`;
      p.style.strokeDashoffset = `${len}`;
    }
    later(delay, () => {
      for (const p of [halo, line]) {
        p.style.transition = `stroke-dashoffset ${dur}ms ${EASE}`;
        p.getBoundingClientRect();
        p.style.strokeDashoffset = "0";
      }
    });
    const ang = (Math.atan2(uy, ux) * 180) / Math.PI;
    let hd = null;
    if (head) {
      hd = document.createElementNS(NS, "path");
      hd.setAttribute("class", "head");
      // its point at the origin, pointing along +x
      const k = hl / HEAD;
      hd.setAttribute("d", `M0 0 L${(-17 * k).toFixed(1)} ${(-9 * k).toFixed(1)} Q${(-12.5 * k).toFixed(1)} 0 ${(-17 * k).toFixed(1)} ${(9 * k).toFixed(1)} Z`);
      hd.setAttribute("transform", `translate(${tx.toFixed(1)} ${ty.toFixed(1)}) rotate(${ang.toFixed(1)}) scale(0)`);
      g.appendChild(hd);
      later(delay + dur - 40, () => {
        const t0 = performance.now();
        const step = () => {
          const q = Math.min(1, (performance.now() - t0) / 240);
          const sc = 1 + 0.3 * Math.sin(Math.PI * q) * (1 - q) - (1 - q) * (1 - q);
          hd.setAttribute("transform", `translate(${tx.toFixed(1)} ${ty.toFixed(1)}) rotate(${ang.toFixed(1)}) scale(${Math.max(0, sc).toFixed(3)})`);
          if (q < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
      });
    }
    const rec = { id, from: [x1, y1], tip: [tx, ty], dir: [ux, uy], target, sel, d, bend: b };
    rec.curve = [x1, y1, c1[0], c1[1], c2[0], c2[1], ex, ey];
    geom.push(rec);
    g.__retract = () => {
      const i = geom.indexOf(rec);
      if (i >= 0) geom.splice(i, 1);
      if (hd) hd.setAttribute("transform", `translate(${tx.toFixed(1)} ${ty.toFixed(1)}) scale(0)`);
      for (const p of [halo, line]) {
        p.style.transition = `stroke-dashoffset 320ms cubic-bezier(.5,0,.75,0)`;
        p.style.strokeDashoffset = `${-len}`;
      }
      later(380, () => g.remove());
    };
    keep(id, g);
    return g;
  }

''' + s[end:]

# anchor: the tip a fixed 6px from the words, edge, or circle
rep('''  function anchor(sel, r, x, y, gap = 8) {''', '''  function anchor(sel, r, x, y, gap = 6) {''')

# bubble: record its target for the verifier
rep('''      drawCurve(id, x1, y1, x2, y2, { bend, delay: 200, dur: 520 });
    },''', '''      drawCurve(id, x1, y1, x2, y2, { bend, delay: 200, dur: 520, target: circles.get(at) ? { ellipse: circles.get(at) } : r, sel: at, n1: [n1x, n1y], n2: [n2x, n2y] });
    },''')
rep('''      drawCurve(id, x1, y1, x2, y2, { bend: bend ?? bestBend(x1, y1, x2, y2, obs), dur: 560 });''',
    '''      drawCurve(id, x1, y1, x2, y2, { bend: bend ?? bestBend(x1, y1, x2, y2, obs), dur: 560, target: circles.get(to) ? { ellipse: circles.get(to) } : b, sel: to, n1: [n1x, n1y], n2: [n2x, n2y] });''')

# the traced edge, and the verifier
rep('''    sheet(b, l, m, instant = false) {''', r'''    // an interaction, traced in ink over its own line; its middle is named for a bubble to point at
    traceEdge({ id, a, b: bSel }) {
      const ra = rectOf(a);
      const rb = rectOf(bSel);
      if (!ra || !rb) throw new Error(`no edge ends ${a} ${bSel}`);
      let best = null;
      for (const p of document.querySelectorAll("g.edge path.line")) {
        const len = p.getTotalLength?.();
        if (!len) continue;
        const m = p.getScreenCTM();
        const at = (t) => { const q = p.getPointAtLength(t); return [q.x * m.a + q.y * m.c + m.e, q.x * m.b + q.y * m.d + m.f]; };
        const dist = (x, y, r) => Math.hypot(Math.max(r.l - x, 0, x - r.r), Math.max(r.t - y, 0, y - r.b));
        const [x0, y0] = at(0);
        const [x1, y1] = at(len);
        const score = dist(x0, y0, ra) + dist(x1, y1, rb);
        if (!best || score < best.score) best = { score, at, len };
      }
      if (!best) throw new Error("no edge");
      const pts = [];
      for (let i = 0; i <= 40; i++) pts.push(best.at((best.len * i) / 40));
      const d = `M${pts.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join(" L")}`;
      const g = document.createElementNS(NS, "g");
      const halo = document.createElementNS(NS, "path");
      const line = document.createElementNS(NS, "path");
      halo.setAttribute("class", "halo"); line.setAttribute("class", "line");
      halo.setAttribute("d", d); line.setAttribute("d", d);
      line.style.strokeWidth = "4.2";
      g.append(halo, line);
      svg.appendChild(g);
      const L = line.getTotalLength();
      for (const p of [halo, line]) { p.style.strokeDasharray = `${L} ${L + 20}`; p.style.strokeDashoffset = `${L}`; }
      requestAnimationFrame(() => { for (const p of [halo, line]) { p.style.transition = `stroke-dashoffset 700ms ${EASE}`; p.style.strokeDashoffset = "0"; } });
      points[id] = pts[20];
      g.__retract = () => {
        for (const p of [halo, line]) { p.style.transition = "stroke-dashoffset 320ms cubic-bezier(.5,0,.75,0)"; p.style.strokeDashoffset = `${-L}`; }
        later(380, () => g.remove());
      };
      keep(id, g);
    },
    // every arrow on screen, measured: the tip's distance from what it points at, whether the head points into it, whether
    // the target is on screen and uncovered, and how much text the line crosses
    verify() {
      const textRects = [];
      const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      const rg = document.createRange();
      for (let n = w.nextNode(); n; n = w.nextNode()) {
        if (!n.nodeValue.trim()) continue;
        const pe = n.parentElement;
        if (!pe || pe.closest(".vbub, .vbadge, .vhead, #vsheet, #vcur, #vchap, script, style") || !vis(pe)) continue;
        rg.selectNodeContents(n);
        for (const b of rg.getClientRects()) if (b.width > 2 && b.height > 4) textRects.push({ l: b.left, t: b.top + b.height * 0.22, r: b.right, b: b.bottom - b.height * 0.22, text: n.nodeValue.trim().slice(0, 24) });
      }
      return geom.map((g) => {
        const [tx, ty] = g.tip;
        const [ux, uy] = g.dir;
        const t = g.target;
        let dist;
        let into = false;
        if (t?.ellipse) {
          const e = t.ellipse;
          const f = (x, y) => Math.pow(Math.abs((x - e.cx) / e.rx) ** (e.n || 2) + Math.abs((y - e.cy) / e.ry) ** (e.n || 2), 1 / (e.n || 2));
          dist = Math.abs(f(tx, ty) - 1) * Math.min(e.rx, e.ry);
          for (let k = 2; k <= 30; k += 2) if (f(tx + ux * k, ty + uy * k) <= 1.02) { into = true; break; }
        } else if (t) {
          dist = Math.hypot(Math.max(t.l - tx, 0, tx - t.r), Math.max(t.t - ty, 0, ty - t.b));
          for (let k = 2; k <= 30; k += 2) {
            const x = tx + ux * k;
            const y = ty + uy * k;
            if (x >= t.l - 1 && x <= t.r + 1 && y >= t.t - 1 && y <= t.b + 1) { into = true; break; }
          }
        }
        const onScreen = t && (t.ellipse ? true : t.r > 0 && t.b > 0 && t.l < innerWidth && t.t < innerHeight);
        // what is drawn at the target's middle (a bubble or the sheet over it would be a covered target)
        let covered = null;
        if (t && !t.ellipse) {
          const top = document.elementFromPoint((t.l + t.r) / 2, (t.t + t.b) / 2);
          if (top?.closest(".vbub, .vbadge, .vhead, #vsheet, #vstages")) covered = top.className || top.id;
        }
        // text the line crosses (other than its own target's)
        const [x1, y1, c1x, c1y, c2x, c2y, ex, ey] = g.curve;
        const crossed = new Set();
        for (let i = 1; i < 40; i++) {
          const q = i / 40;
          const v = 1 - q;
          const x = v * v * v * x1 + 3 * v * v * q * c1x + 3 * v * q * q * c2x + q * q * q * ex;
          const y = v * v * v * y1 + 3 * v * v * q * c1y + 3 * v * q * q * c2y + q * q * q * ey;
          for (const r of textRects) {
            if (x >= r.l && x <= r.r && y >= r.t && y <= r.b && !(t && !t.ellipse && x >= t.l - 2 && x <= t.r + 2 && y >= t.t - 2 && y <= t.b + 2)) crossed.add(r.text);
          }
        }
        let moved = 0;
        if (t && !t.ellipse && typeof g.sel === "string") {
          const now = rectOf(g.sel);
          moved = now ? Math.round(Math.max(Math.abs(now.l - t.l), Math.abs(now.t - t.t), Math.abs(now.r - t.r), Math.abs(now.b - t.b))) : 999;
        }
        return { id: g.id, moved, sel: typeof g.sel === "string" ? g.sel : JSON.stringify(g.sel), tip: [Math.round(tx), Math.round(ty)],
                 dist: Math.round((dist ?? 999) * 10) / 10, into, onScreen: !!onScreen, covered, crossed: [...crossed] };
      });
    },
    liveTips() { return geom.map((g) => ({ id: g.id, tip: g.tip, from: g.from })); },
    liveCircles() { return [...circles.entries()].map(([k, e]) => ({ sel: k, ...e })); },
    sheet(b, l, m, instant = false) {''')


# words inside a sentence are underlined, not ringed: a ring would cut the words beside them
rep('''    liveTips() {''', r'''    underline({ id, at, nth = 0 }) {
      const r = rectOf(at, nth);
      if (!r) throw new Error(`no target ${at}`);
      const y = r.b + 3;
      const d = `M${(r.l - 4).toFixed(1)} ${(y + 1.5).toFixed(1)} C${(r.l + r.w * 0.3).toFixed(1)} ${(y - 0.5).toFixed(1)} ${(r.l + r.w * 0.7).toFixed(1)} ${(y + 0.5).toFixed(1)} ${(r.r + 5).toFixed(1)} ${(y - 1.5).toFixed(1)}`;
      const g = document.createElementNS(NS, "g");
      const halo = document.createElementNS(NS, "path");
      const line = document.createElementNS(NS, "path");
      halo.setAttribute("class", "halo"); line.setAttribute("class", "line");
      halo.setAttribute("d", d); line.setAttribute("d", d);
      line.style.strokeWidth = "3.4";
      g.append(halo, line);
      svg.appendChild(g);
      const L = line.getTotalLength();
      for (const p of [halo, line]) { p.style.strokeDasharray = `${L} ${L + 20}`; p.style.strokeDashoffset = `${L}`; }
      requestAnimationFrame(() => { for (const p of [halo, line]) { p.style.transition = `stroke-dashoffset 450ms ${EASE}`; p.style.strokeDashoffset = "0"; } });
      g.__retract = () => {
        for (const p of [halo, line]) { p.style.transition = "stroke-dashoffset 320ms cubic-bezier(.5,0,.75,0)"; p.style.strokeDashoffset = `${-L}`; }
        later(380, () => g.remove());
      };
      keep(id, g);
    },
    liveTips() {''')
(V / "annotate4.js").write_text(s)
print("ok")
