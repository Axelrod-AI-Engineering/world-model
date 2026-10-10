  // -- layout: one set of rules for every callout ------------------------------------------------------------------
  // obstacles: what a bubble must not cover and an arrow should not cross
  const OBST = ["g.pill", "g.card-super", "g.hull-tab", "#levels", "#vchap", "#search-box", "#canvas-controls", "#staged-banner",
    "#topbar", "#bottom", ".vbub", ".vhead", ".vbadge", "#left-panel", "#right-panel", ".manual", "#drawer.open", "#console"];
  const boxOf = (el) => { const b = el.getBoundingClientRect(); return { l: b.left, t: b.top, r: b.right, b: b.bottom }; };
  const shown = (el) => {
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden" || el.hidden || el.classList.contains("hidden")) return false;
    const b = el.getBoundingClientRect();
    return b.width > 2 && b.height > 2 && b.right > 0 && b.bottom > 0 && b.left < innerWidth && b.top < innerHeight;
  };
  const ov = (a, b) => Math.max(0, Math.min(a.r, b.r) - Math.max(a.l, b.l)) * Math.max(0, Math.min(a.b, b.b) - Math.max(a.t, b.t));
  const inside = (a, b) => a.l >= b.l - 1 && a.r <= b.r + 1 && a.t >= b.t - 1 && a.b <= b.b + 1;
  // the text inside a container, line by line: a panel or the drawer blocks only where it has words
  function textBoxes(container) {
    const out = [];
    const w = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    const range = document.createRange();
    for (let n = w.nextNode(); n && out.length < 500; n = w.nextNode()) {
      if (!n.nodeValue.trim()) continue;
      range.selectNodeContents(n);
      for (const b of range.getClientRects()) {
        if (b.width < 2 || b.height < 2 || b.bottom < 0 || b.top > innerHeight) continue;
        out.push({ l: b.left - 2, t: b.top - 1, r: b.right + 2, b: b.bottom + 1, el: n.parentElement });
      }
    }
    return out;
  }
  // the sparse containers (the memory drawer, the Checks pane) block word by word; the dense side panels stay whole,
  // so a bubble about something in them always sits outside them, on the canvas
  const CONTAINERS = [".manual", "#drawer.open"];
  // the drawn things in a sparse container that are not words (bars, swatches, chips): a bubble must not cover them either
  function marks(container) {
    const out = [];
    for (const el of container.querySelectorAll("*")) {
      if (el.childElementCount || out.length > 400) continue;
      const cs = getComputedStyle(el);
      const painted = (cs.backgroundColor && cs.backgroundColor !== "rgba(0, 0, 0, 0)" && cs.backgroundColor !== "transparent") || parseFloat(cs.borderTopWidth) > 0;
      if (!painted) continue;
      const b = el.getBoundingClientRect();
      if (b.width < 6 || b.height < 2 || b.height > 40 || b.bottom < 0 || b.top > innerHeight) continue;
      out.push({ l: b.left - 2, t: b.top - 2, r: b.right + 2, b: b.bottom + 2, el });
    }
    return out;
  }
  function obstacles(skip = [], target = null) {
    const out = [];
    for (const q of OBST) {
      for (const el of document.querySelectorAll(q)) {
        if (skip.includes(el) || !shown(el)) continue;
        const box = { ...boxOf(el), el };
        // the container a target sits in: its words are obstacles, its empty space is not
        if (target && CONTAINERS.some((c) => el.matches(c)) && inside(target, box)) out.push(...textBoxes(el), ...marks(el));
        else out.push(box);
      }
    }
    return out;
  }
  const circles = new Map();       // target selector -> the ellipse drawn around it
  // words, short labels, tabs, and pills are reached level, from the side; round badges and big boxes from any side
  const isLevel = (r) => !!r && (r.text || r.h < 40) && !r.badge;
  // the points of the arrow drawCurve will draw from (x1, y1) to the tip (tx, ty)
  function controls(x1, y1, n1, tx, ty, n2) {
    const L = Math.hypot(tx - x1, ty - y1) || 1;
    const k = Math.max(Math.min(26, L * 0.3), Math.min(120, L * 0.42));
    return [[x1 + n1[0] * k, y1 + n1[1] * k], [tx + n2[0] * k, ty + n2[1] * k]];
  }
  function arrowPts(x1, y1, n1, tx, ty, n2) {
    const [c1, c2] = controls(x1, y1, n1, tx, ty, n2);
    const pts = [];
    for (let i = 1; i < 30; i++) {
      const t = i / 30;
      const u = 1 - t;
      pts.push([u * u * u * x1 + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t * t * t * tx,
                u * u * u * y1 + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t * t * t * ty]);
    }
    return pts;
  }
  const hits = (pts, boxes, m = 5) => boxes.filter((o) => pts.some(([x, y]) => x > o.l - m && x < o.r + m && y > o.t - m && y < o.b + m)).length;
  // which side of r faces the point (x, y)
  function facing(r, x, y) {
    const dx = (x - r.cx) / Math.max(1, r.w / 2);
    const dy = (y - r.cy) / Math.max(1, r.h / 2);
    return Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "r" : "l") : (dy > 0 ? "b" : "t");
  }
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  // where an arrow meets a target, coming from (x, y): the ellipse around it if it is circled, else the middle part
  // of its facing edge, a fixed gap away
  function anchor(sel, r, x, y, gap = 8) {
    const c = typeof sel === "string" ? circles.get(sel) : null;
    if (c) {
      // the ring's point in the direction of (x, y), and the ring's own normal there
      // the point of the ring nearest (x, y), so the arrow comes straight at it instead of hooking around to the middle
      const n = c.n || 2;
      let ex = c.cx;
      let ey = c.cy;
      let bd = Infinity;
      let pn = null;
      if (c.poly) for (const [px, py, qx, qy] of c.poly) {
        const dd = Math.hypot(px - x, py - y);
        if (dd < bd) { bd = dd; ex = px; ey = py; pn = [qx, qy]; }
      }
      if (!c.poly) for (let i = 0; i < 240; i++) {
        const a = (i / 240) * Math.PI * 2;
        const ca = Math.cos(a);
        const sa = Math.sin(a);
        const px = c.cx + Math.sign(ca) * Math.abs(ca) ** (2 / n) * c.rx;
        const py = c.cy + Math.sign(sa) * Math.abs(sa) ** (2 / n) * c.ry;
        const dd = Math.hypot(px - x, py - y);
        if (dd < bd) { bd = dd; ex = px; ey = py; }
      }
      let nx = Math.sign(ex - c.cx) * Math.abs((ex - c.cx) / c.rx) ** (n - 1) / c.rx;
      let ny = Math.sign(ey - c.cy) * Math.abs((ey - c.cy) / c.ry) ** (n - 1) / c.ry;
      if (pn) [nx, ny] = pn;
      const nn = Math.hypot(nx, ny) || 1;
      nx /= nn; ny /= nn;
      return [ex + nx * gap, ey + ny * gap, nx, ny];
    }
    // words are pointed at from the side, level with them: never from above or below, where other lines sit
    if (isLevel(r)) return x < r.cx ? [r.l - (r.text ? 8 : gap), r.cy, -1, 0] : [r.r + (r.text ? 8 : gap), r.cy, 1, 0];
    const side = facing(r, x, y);
    if (side === "l") return [r.l - gap, clamp(y, r.t + r.h * 0.3, r.b - r.h * 0.3), -1, 0];
    if (side === "r") return [r.r + gap, clamp(y, r.t + r.h * 0.3, r.b - r.h * 0.3), 1, 0];
    if (side === "t") return [clamp(x, r.l + r.w * 0.3, r.r - r.w * 0.3), r.t - gap, 0, -1];
    return [clamp(x, r.l + r.w * 0.3, r.r - r.w * 0.3), r.b + gap, 0, 1];
  }
  // how many obstacles a straight line crosses (sampled)
  function crossings(x1, y1, x2, y2, boxes) {
    let n = 0;
    for (const o of boxes) {
      for (let i = 1; i < 16; i++) {
        const x = x1 + ((x2 - x1) * i) / 16;
        const y = y1 + ((y2 - y1) * i) / 16;
        if (x > o.l && x < o.r && y > o.t && y < o.b) { n += 1; break; }
      }
    }
    return n;
  }
  // where an arrow leaves a bubble: the middle part of its side facing the target
  function startOf(bb, tx, ty) {
    const side = facing(bb, tx, ty);
    if (side === "l") return [bb.l - 3, clamp(ty, bb.t + bb.h * 0.25, bb.b - bb.h * 0.25), -1, 0];
    if (side === "r") return [bb.r + 3, clamp(ty, bb.t + bb.h * 0.25, bb.b - bb.h * 0.25), 1, 0];
    if (side === "t") return [clamp(tx, bb.l + Math.min(48, bb.w * 0.3), bb.r - Math.min(48, bb.w * 0.3)), bb.t - 3, 0, -1];
    return [clamp(tx, bb.l + Math.min(48, bb.w * 0.3), bb.r - Math.min(48, bb.w * 0.3)), bb.b + 3, 0, 1];
  }
  const curvePts = (x1, y1, x2, y2, bend) => {
    const dx = x2 - x1;
    const dy = y2 - y1;
    const c1 = [x1 + dx * 0.3 - dy * bend, y1 + dy * 0.3 + dx * bend];
    const c2 = [x1 + dx * 0.7 - dy * bend, y1 + dy * 0.7 + dx * bend];
    const pts = [];
    for (let i = 1; i < 24; i++) {
      const t = i / 24;
      const u = 1 - t;
      pts.push([u * u * u * x1 + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t * t * t * x2,
                u * u * u * y1 + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t * t * t * y2]);
    }
    return pts;
  };
  // the bend that crosses the fewest obstacles, preferring one gentle bow in the same direction every time
  function bestBend(x1, y1, x2, y2, obs) {
    let best = null;
    for (const bend of [0.14, 0.08, 0.2, 0, 0.28, -0.08, -0.14, -0.2, 0.36, -0.28]) {
      const hits = curvePts(x1, y1, x2, y2, bend).filter(([x, y]) => obs.some((o) => x > o.l - 4 && x < o.r + 4 && y > o.t - 4 && y < o.b + 4)).length;
      const cost = hits * 10 + Math.abs(bend - 0.14) * 6;
      if (!best || cost < best.cost) best = { bend, cost };
    }
    return best.bend;
  }
  // a bubble's place: the spot on the preferred side (then the others) that covers the least, close to its target
  function place(r, bw, bh, side, obs, sel = null, texts = []) {
    // words take a bubble only to their side
    const horiz = side === "left" || side === "right" ? side : "right";
    const sides = isLevel(r) ? [horiz, horiz === "right" ? "left" : "right", side === "bottom" || side === "top" ? side : "bottom"]
      : [side, ...["right", "left", "bottom", "top"].filter((x) => x !== side)];
    let best = null;
    for (const sd of sides) {
      for (const d of [56, 80, 110, 150, 200, 260, 330, 410, 500, 600, 700]) {
        for (const off of [0, -0.15, 0.15, -0.25, 0.25, -0.35, 0.35, -0.7, 0.7]) {
          let x;
          let y;
          if (sd === "right") { x = r.r + d; y = r.cy - bh / 2 + off * bh; }
          else if (sd === "left") { x = r.l - d - bw; y = r.cy - bh / 2 + off * bh; }
          else if (sd === "top") { x = r.cx - bw / 2 + off * bw; y = r.t - d - bh; }
          else { x = r.cx - bw / 2 + off * bw; y = r.b + d; }
          if (x < 14 || y < 62 || x + bw > innerWidth - 14 || y + bh > innerHeight - 56) continue;
          const bb = { l: x - 10, t: y - 10, r: x + bw + 14, b: y + bh + 14 };
          // covering a group's empty inside is a small cost; covering anything with words on it is a large one
          let cover = ov(bb, { l: r.l - 6, t: r.t - 6, r: r.r + 6, b: r.b + 6 }) * 4;
          let solid = 0;
          for (const o of obs) {
            const v = ov(bb, o);
            if (!v) continue;
            if (o.el?.matches?.("g.card-super")) cover += v * 0.15;
            else { cover += v; solid += 1; }
          }
          // and its arrow should cross as little as possible on the way
          const cand = { l: x, t: y, r: x + bw, b: y + bh, cx: x + bw / 2, cy: y + bh / 2, w: bw, h: bh };
          const [ax, ay, anx, any] = anchor(sel, r, cand.cx, cand.cy);
          const [sx, sy, snx, sny] = startOf(cand, ax, ay);
          // the arrow as it will be drawn, not a straight stand-in
          const pts = arrowPts(sx, sy, [snx, sny], ax, ay, [anx, any]);
          const cross = hits(pts, texts) + hits(pts, obs.filter((o) => !inside(r, o)));
          const L = Math.hypot(ax - sx, ay - sy);
          // how far the arrow has to turn: from the way it leaves, to the chord, to the way it arrives
          const ch = [(ax - sx) / (L || 1), (ay - sy) / (L || 1)];
          const turn = Math.acos(clamp(snx * ch[0] + sny * ch[1], -1, 1)) + Math.acos(clamp(-anx * ch[0] - any * ch[1], -1, 1));
          const cost = cover / 10 + solid * 220 + d * 0.1 + Math.abs(off) * 14 + (sd === (isLevel(r) ? horiz : side) ? 0 : 40) + cross * 70
            + Math.max(0, 70 - L) * 3 + turn * 25;
          if (!best || cost < best.cost) best = { x, y, cost };
        }
      }
    }
    return best ?? { x: clamp(r.r + 60, 14, innerWidth - bw - 14), y: clamp(r.cy - bh / 2, 62, innerHeight - bh - 56) };
  }
