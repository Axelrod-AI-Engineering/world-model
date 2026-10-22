(() => {
  if (window.__ann) return;
  // DECISIONS for the video: motion, never transparency. Every entrance and exit moves or scales; nothing with text
  // in it fades. Overlays are opaque. Lines are smooth curves with a soft halo; heads appear once a line is drawn.
  const INK = "#2F2A25";
  const PAPER = "#FBF8F2";
  const BUTTER = "#F6DA7A";
  const EASE = "cubic-bezier(.65,0,.35,1)";
  const SPRING = "cubic-bezier(.34,1.56,.64,1)";
  const st = document.createElement("style");
  st.textContent = `
  #caption, #toast, #gesture-hint, .hint-toast, #tooltip, #admin { display: none !important; }
  button:disabled { opacity: 1 !important; }
  /* the app's own fades, off: pills and cards grow in at full opacity; anything leaving goes at once */
  .pill .inner, .card-super .inner, g.hull-tabs, .hull-tab { opacity: 1 !important; }
  .pill.exiting, .card-super.exiting { display: none !important; }
  .dim, .pill.dim, .card-super.dim, .hull-tab.dim { opacity: 1 !important; }
  .sheet-panel.left:not([hidden]) { animation: vslideL .7s ${EASE}; }
  .sheet-panel.right:not([hidden]) { animation: vslideR .7s ${EASE}; }
  @keyframes vslideL { from { transform: translateX(-105%); } to { transform: none; } }
  @keyframes vslideR { from { transform: translateX(105%); } to { transform: none; } }
  .manual:not(.hidden), #console:not(.hidden) { animation: vrise .7s ${EASE}; }
  @keyframes vrise { from { transform: translateY(calc(100vh)); } to { transform: none; } }
  #drawer.open { transition: transform .8s ${EASE}, visibility 0s !important; }
  #vann-svg { position: fixed; inset: 0; width: 100vw; height: 100vh; z-index: 9990; pointer-events: none; overflow: visible; }
  #vann-svg .halo { fill: none; stroke: ${PAPER}; stroke-width: 9; stroke-linecap: round; stroke-linejoin: round; }
  #vann-svg .line { fill: none; stroke: ${INK}; stroke-width: 3.6; stroke-linecap: round; stroke-linejoin: round; }
  #vann-svg .head { fill: ${INK}; stroke: ${PAPER}; stroke-width: 2.4; stroke-linejoin: round; transform-box: fill-box; transform-origin: center; }
  .vbub { position: fixed; z-index: 9995; pointer-events: none; max-width: 300px; padding: 11px 16px 12px; background: #FFFDF8; color: ${INK};
    border: 3px solid ${INK}; border-radius: 18px; box-shadow: 5px 6px 0 ${INK}; font: 600 18px/1.25 "Bricolage Grotesque", system-ui;
    transform: scale(0); transition: transform .55s ${SPRING}; }
  .vbub.in { transform: scale(1); }
  .vbub.out { transform: scale(0); transition: transform .35s cubic-bezier(.5,0,.75,0); }
  .vbadge { position: fixed; z-index: 9996; pointer-events: none; min-width: 26px; height: 26px; padding: 0 6px; box-sizing: border-box; border-radius: 13px;
    background: ${BUTTER}; border: 3px solid ${INK}; box-shadow: 2px 3px 0 ${INK}; display: flex; align-items: center; justify-content: center;
    font: 800 14px "Bricolage Grotesque", system-ui; color: ${INK}; transform: scale(0); transition: transform .5s ${SPRING}; }
  .vbadge.in { transform: scale(1); }
  .vbadge.out { transform: scale(0); transition: transform .3s cubic-bezier(.5,0,.75,0); }
  .vsticker { position: fixed; z-index: 9995; pointer-events: none; padding: 9px 16px; background: ${BUTTER}; border: 3px solid ${INK}; border-radius: 12px;
    box-shadow: 4px 5px 0 ${INK}; font: 700 20px "Bricolage Grotesque", system-ui; color: ${INK}; transform: translate(-50%, -50%) rotate(-3deg) scale(0);
    transition: transform .55s ${SPRING}; }
  .vsticker.in { transform: translate(-50%, -50%) rotate(-3deg) scale(1); }
  .vsticker.out { transform: translate(-50%, -50%) rotate(-3deg) scale(0); transition: transform .35s cubic-bezier(.5,0,.75,0); }
  .vhead { position: fixed; z-index: 9994; width: 330px; padding: 12px 16px 14px; background: #FFFDF8; border: 3px solid ${INK}; border-radius: 6px;
    box-shadow: 6px 7px 0 ${INK}; pointer-events: none; transform: translate(-50%, calc(-50% - 110vh)) rotate(-14deg); transition: transform .9s cubic-bezier(.2,1.25,.4,1); }
  .vhead.in { transform: translate(-50%, -50%) rotate(-2.5deg); }
  .vhead.out { transform: translate(-50%, calc(-50% - 110vh)) rotate(8deg); transition: transform .6s cubic-bezier(.6,0,.8,.2); }
  #vchap { position: fixed; bottom: 60px; left: 50%; z-index: 9980; pointer-events: none; padding: 7px 16px 8px; background: ${INK}; color: #FFFDF8;
    border-radius: 999px; font: 600 13px "IBM Plex Mono", monospace; letter-spacing: .12em; text-transform: uppercase; box-shadow: 0 8px 24px rgba(0,0,0,.16);
    transform: translate(-50%, 240%); transition: transform .5s ${EASE}; }
  #vchap.on { transform: translate(-50%, 0); }
  #vsheet { position: fixed; inset: 0; z-index: 10001; background: ${PAPER}; display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 14px; text-align: center; pointer-events: none; transform: translateX(-104%); box-shadow: 24px 0 48px rgba(47,42,37,.18); transition: transform .8s ${EASE}; }
  #vsheet.on { transform: none; }
  #vsheet.away { transform: translateX(104%); box-shadow: -24px 0 48px rgba(47,42,37,.18); }
  #vsheet.instant { transition: none; }
  #vsheet .b { font: 700 64px/1.08 "Bricolage Grotesque", system-ui; color: ${INK}; letter-spacing: -.01em; transition: transform .4s cubic-bezier(.5,0,.75,0); }
  #vsheet .b span { color: #7C64C4; }
  #vsheet .l { font: 400 22px "Instrument Sans", system-ui; color: #665E54; transition: transform .4s cubic-bezier(.5,0,.75,0); }
  #vsheet .m { font: 500 13px "IBM Plex Mono", monospace; color: #93897C; letter-spacing: .14em; text-transform: uppercase; margin-top: 18px; transition: transform .4s cubic-bezier(.5,0,.75,0); }
  #vsheet.textout .b, #vsheet.textout .l, #vsheet.textout .m { transform: scale(0); }
  #vflash { position: fixed; inset: 0; z-index: 10003; background: #000; display: none; }
  #vcur { position: fixed; z-index: 10000; width: 20px; height: 20px; margin: -2px 0 0 -2px; pointer-events: none; transition: transform .12s ease; }
  #vcur.down { transform: scale(.8); }
  .vring { position: fixed; z-index: 9988; width: 40px; height: 40px; margin: -20px 0 0 -20px; border: 3px solid ${INK}; border-radius: 50%; pointer-events: none;
    transform: scale(.5); transition: transform 1.6s cubic-bezier(.2,.7,.3,1), border-width 1.6s ease; }
  #vstages { position: fixed; inset: 0; z-index: 9985; display: flex; align-items: center; justify-content: center; background: ${PAPER}; pointer-events: none;
    transform: translateY(104%); transition: transform .8s ${EASE}; }
  #vstages.on { transform: none; }
  #vstages .vstage { width: 188px; padding: 16px 14px 18px; border-radius: 18px; text-align: center; background: #EEE9E0; border: 3px solid #D9D1C4;
    transform: scale(.94); transition: transform .5s ${SPRING}, background-color .4s, border-color .4s, box-shadow .4s; }
  #vstages .vstage .k { font: 600 12px 'IBM Plex Mono', monospace; letter-spacing: .14em; color: #A79E91; }
  #vstages .vstage .n { font: 700 22px 'Bricolage Grotesque', system-ui; color: #A79E91; margin: 4px 0 6px; }
  #vstages .vstage .d { font: 500 14.5px 'Instrument Sans', system-ui; color: #A79E91; line-height: 1.3; }
  #vstages .vstage.on .k { color: #665E54; } #vstages .vstage.on .n { color: ${INK}; } #vstages .vstage.on .d { color: #3d362f; }
  #vstages .vstage.cur { transform: scale(1.07); box-shadow: 5px 6px 0 ${INK}; border-color: ${INK}; }
  #vstages .vstage.on:not(.cur) { transform: scale(1); }
  `;
  document.head.appendChild(st);
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.id = "vann-svg";
  document.body.appendChild(svg);
  const add = (tag, cls) => { const el = document.createElement(tag); if (cls) el.className = cls; document.body.appendChild(el); return el; };
  const cur = add("div"); cur.id = "vcur";
  cur.innerHTML = `<svg viewBox="0 0 18 18" width="20" height="20"><path d="M2 1.5L2 15L5.8 11.4L8.4 16.6L10.8 15.4L8.2 10.3L13.4 10.1Z" fill="${INK}" stroke="#FFFDF8" stroke-width="1.3" stroke-linejoin="round"/></svg>`;
  document.addEventListener("mousemove", (e) => { cur.style.left = `${e.clientX}px`; cur.style.top = `${e.clientY}px`; }, true);
  document.addEventListener("mousedown", () => cur.classList.add("down"), true);
  document.addEventListener("mouseup", () => cur.classList.remove("down"), true);
  const chap = add("div"); chap.id = "vchap";
  const sheet = add("div"); sheet.id = "vsheet";
  const flash = add("div"); flash.id = "vflash";
  const items = new Map();
  const later = (ms, fn) => setTimeout(fn, ms);
  const keep = (id, ...els) => { if (!items.has(id)) items.set(id, []); items.get(id).push(...els); };

  const rectOf = (sel, nth = 0) => {
    if (sel && typeof sel === "object" && sel.pt) {
      const [x, y] = sel.pt;
      return { l: x - 6, t: y - 6, r: x + 6, b: y + 6, cx: x, cy: y, w: 12, h: 12 };
    }
    if (typeof sel === "string" && sel.startsWith("edge:")) return edgeBetween(...sel.slice(5).split("|"));
    let els;
    if (typeof sel === "string" && sel.includes("::")) {
      const [q, txt] = sel.split("::");
      els = [...document.querySelectorAll(q)].filter((e) => (e.textContent || "").includes(txt));
    } else els = [...document.querySelectorAll(sel)];
    const el = els[nth] ?? els[0];
    if (!el) return null;
    const b = el.getBoundingClientRect();
    return b.width || b.height ? { l: b.left, t: b.top, r: b.right, b: b.bottom, cx: (b.left + b.right) / 2, cy: (b.top + b.bottom) / 2, w: b.width, h: b.height } : null;
  };
  function edgeBetween(aSel, bSel) {
    const a = rectOf(aSel);
    const b = rectOf(bSel);
    if (!a || !b) return null;
    let best = null;
    for (const p of document.querySelectorAll("g.edge path.line")) {
      const len = p.getTotalLength?.();
      if (!len) continue;
      const m = p.getScreenCTM();
      const at = (t) => { const q = p.getPointAtLength(t); return [q.x * m.a + q.y * m.c + m.e, q.x * m.b + q.y * m.d + m.f]; };
      const [x0, y0] = at(0);
      const [x1, y1] = at(len);
      const dist = (x, y, r) => Math.hypot(Math.max(r.l - x, 0, x - r.r), Math.max(r.t - y, 0, y - r.b));
      const score = dist(x0, y0, a) + dist(x1, y1, b);
      if (!best || score < best.score) { const [mx, my] = at(len / 2); best = { score, mx, my }; }
    }
    return best ? { l: best.mx - 6, t: best.my - 6, r: best.mx + 6, b: best.my + 6, cx: best.mx, cy: best.my, w: 12, h: 12 } : null;
  }
  const edgePoint = (r, x, y, gap = 6) => {
    const dx = r.cx - x;
    const dy = r.cy - y;
    const s = Math.min((r.w / 2 + gap) / Math.abs(dx || 1e-6), (r.h / 2 + gap) / Math.abs(dy || 1e-6));
    return [r.cx - dx * Math.min(s, 1), r.cy - dy * Math.min(s, 1)];
  };

  // a smooth cubic curve from (x1, y1) to (x2, y2), bowed to one side; its halo; and a head that pops in once drawn
  function drawCurve(id, x1, y1, x2, y2, { bend = 0.14, head = true, dur = 650, delay = 0 } = {}) {
    const dx = x2 - x1;
    const dy = y2 - y1;
    const c1 = [x1 + dx * 0.3 - dy * bend, y1 + dy * 0.3 + dx * bend];
    const c2 = [x1 + dx * 0.7 - dy * bend, y1 + dy * 0.7 + dx * bend];
    // stop short of the target so the head sits on it
    const ang = Math.atan2(y2 - c2[1], x2 - c2[0]);
    const ex = x2 - Math.cos(ang) * (head ? 15 : 0);
    const ey = y2 - Math.sin(ang) * (head ? 15 : 0);
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
    let hd = null;
    if (head) {
      hd = document.createElementNS(NS, "path");
      hd.setAttribute("class", "head");
      hd.setAttribute("d", "M-2 -9.5 L17 0 L-2 9.5 Q2 0 -2 -9.5 Z");
      hd.setAttribute("transform", `translate(${ex.toFixed(1)} ${ey.toFixed(1)}) rotate(${(ang * 180 / Math.PI).toFixed(1)}) scale(0)`);
      g.appendChild(hd);
      later(delay + dur - 60, () => {
        const t0 = performance.now();
        const step = () => {
          const k = Math.min(1, (performance.now() - t0) / 260);
          const s = 1 + 0.35 * Math.sin(Math.PI * k) * (1 - k) - (1 - k) * (1 - k);
          hd.setAttribute("transform", `translate(${ex.toFixed(1)} ${ey.toFixed(1)}) rotate(${(ang * 180 / Math.PI).toFixed(1)}) scale(${Math.max(0, s).toFixed(3)})`);
          if (k < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
      });
    }
    g.__retract = () => {
      if (hd) hd.setAttribute("transform", `translate(${ex.toFixed(1)} ${ey.toFixed(1)}) scale(0)`);
      for (const p of [halo, line]) {
        p.style.transition = `stroke-dashoffset 320ms cubic-bezier(.5,0,.75,0)`;
        p.style.strokeDashoffset = `${-len}`;
      }
      later(380, () => g.remove());
    };
    keep(id, g);
    return g;
  }

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
  function obstacles(skip = [], target = null) {
    const out = [];
    for (const q of OBST) {
      for (const el of document.querySelectorAll(q)) {
        if (skip.includes(el) || !shown(el)) continue;
        const box = { ...boxOf(el), el };
        // the container a target sits in: its words are obstacles, its empty space is not
        if (target && CONTAINERS.some((c) => el.matches(c)) && inside(target, box)) out.push(...textBoxes(el));
        else out.push(box);
      }
    }
    return out;
  }
  const circles = new Map();       // target selector -> the ellipse drawn around it
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
      const th = Math.atan2((y - c.cy) / c.ry, (x - c.cx) / c.rx);
      const ex = c.cx + Math.cos(th) * c.rx;
      const ey = c.cy + Math.sin(th) * c.ry;
      const n = Math.hypot(x - ex, y - ey) || 1;
      return [ex + ((x - ex) / n) * gap, ey + ((y - ey) / n) * gap];
    }
    const side = facing(r, x, y);
    if (side === "l" || side === "r") return [side === "l" ? r.l - gap : r.r + gap, clamp(y, r.t + r.h * 0.3, r.b - r.h * 0.3)];
    return [clamp(x, r.l + r.w * 0.3, r.r - r.w * 0.3), side === "t" ? r.t - gap : r.b + gap];
  }
  // where an arrow leaves a bubble: the middle part of its side facing the target
  function startOf(bb, tx, ty) {
    const side = facing(bb, tx, ty);
    if (side === "l" || side === "r") return [side === "l" ? bb.l - 3 : bb.r + 3, clamp(ty, bb.t + bb.h * 0.35, bb.b - bb.h * 0.35)];
    return [clamp(tx, bb.l + bb.w * 0.3, bb.r - bb.w * 0.3), side === "t" ? bb.t - 3 : bb.b + 3];
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
  function place(r, bw, bh, side, obs) {
    const sides = [side, ...["right", "left", "bottom", "top"].filter((x) => x !== side)];
    let best = null;
    for (const sd of sides) {
      for (const d of [56, 80, 110, 150, 200, 260, 330, 410]) {
        for (const off of [0, -0.35, 0.35, -0.7, 0.7]) {
          let x;
          let y;
          if (sd === "right") { x = r.r + d; y = r.cy - bh / 2 + off * bh; }
          else if (sd === "left") { x = r.l - d - bw; y = r.cy - bh / 2 + off * bh; }
          else if (sd === "top") { x = r.cx - bw / 2 + off * bw; y = r.t - d - bh; }
          else { x = r.cx - bw / 2 + off * bw; y = r.b + d; }
          if (x < 14 || y < 62 || x + bw > innerWidth - 14 || y + bh > innerHeight - 56) continue;
          const bb = { l: x - 10, t: y - 10, r: x + bw + 14, b: y + bh + 14 };
          const cover = obs.reduce((a, o) => a + ov(bb, o), 0) + ov(bb, { l: r.l - 6, t: r.t - 6, r: r.r + 6, b: r.b + 6 }) * 4;
          const cost = cover / 40 + d * 0.1 + Math.abs(off) * 14 + (sd === side ? 0 : 40);
          if (!best || cost < best.cost) best = { x, y, cost };
        }
      }
    }
    return best ?? { x: clamp(r.r + 60, 14, innerWidth - bw - 14), y: clamp(r.cy - bh / 2, 62, innerHeight - bh - 56) };
  }

  function popIn(el) { el.getBoundingClientRect(); requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add("in"))); }

  const STAGES = [["Intake", "reads the article into operations", "#F7E1D3", "#E0B092"],
    ["Working memory", "folds it into the current graph", "#E1ECDF", "#A9C6A9"],
    ["Long-term memory", "learns what generalizes", "#DCE6F0", "#A9BFD6"],
    ["Review", "a person keeps what makes sense", "#DAD0F4", "#7C64C4"],
    ["Commit", "a new version", "#E7E0F3", "#B9ACD8"]];
  let stageBox = null;

  window.__ann = {
    cinematic(r) {
      const z = r.zoom;
      const slow = (d) => (d === 0 ? 0 : Math.max(900, (d ?? 320) * 2.4));
      const f = z.fit.bind(z); z.fit = (b, d, o) => f(b, slow(d), o);
      const s = z.set.bind(z); z.set = (t, d) => s(t, slow(d));
      const c = z.centerOn.bind(z); z.centerOn = (x, y, k, d, dx) => c(x, y, k, slow(d), dx);
      const p = z.panBy.bind(z); z.panBy = (dx, dy, d) => p(dx, dy, slow(d));
      const fit = r.fit.bind(r); r.fit = (d) => fit(d === 0 ? 0 : slow(d));
      r.sim.velocityDecay(0.6);
    },
    // the paper sheet: the title cards and the cuts between takes. It slides in from the left and away to the right.
    sheet(b, l, m, instant = false) {
      sheet.classList.remove("away", "textout");
      sheet.classList.toggle("instant", !!instant);
      sheet.innerHTML = b || l ? `<div class="b">${b}</div><div class="l">${l}</div>${m ? `<div class="m">${m}</div>` : ""}` : "";
      sheet.getBoundingClientRect();
      sheet.classList.add("on");
      if (instant) later(30, () => sheet.classList.remove("instant"));
    },
    sheetAway() {
      sheet.classList.remove("instant");
      sheet.classList.add("away");
      sheet.classList.remove("on");
      later(900, () => { sheet.classList.add("instant"); sheet.classList.remove("away"); sheet.innerHTML = ""; later(30, () => sheet.classList.remove("instant")); });
    },
    sheetText(out) { sheet.classList.toggle("textout", !!out); },
    flash() { flash.style.display = "block"; later(240, () => { flash.style.display = "none"; }); },
    chapter(t) {
      const show = () => { chap.textContent = t; chap.getBoundingClientRect(); chap.classList.add("on"); };
      if (chap.classList.contains("on")) { chap.classList.remove("on"); later(520, show); } else show();
    },
    sticker(sel, text, dur = 1800) {
      const r = rectOf(sel);
      if (!r) return;
      const s = add("div", "vsticker");
      s.textContent = text;
      s.style.left = `${r.cx}px`;
      s.style.top = `${r.t + Math.min(r.h * 0.38, 300)}px`;
      popIn(s);
      later(dur, () => { s.classList.add("out"); later(420, () => s.remove()); });
    },
    stages(on, instant = false) {
      if (!on && instant) { stageBox?.remove(); stageBox = null; return; }
      if (!on) { if (stageBox) { stageBox.classList.remove("on"); const sb = stageBox; later(900, () => sb.remove()); stageBox = null; } return; }
      stageBox = add("div"); stageBox.id = "vstages";
      stageBox.innerHTML = `<div style="display:flex;align-items:center;gap:10px">${STAGES.map(([n, d, f, l], i) => `${i ? `<svg width="44" height="24" viewBox="0 0 44 24"><path d="M3 12 C14 4 26 4 37 12" fill="none" stroke="${INK}" stroke-width="3.4" stroke-linecap="round"/><path d="M30 6 L39 12 L30 18" fill="none" stroke="${INK}" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/></svg>` : ""}
        <div class="vstage" data-i="${i}" data-f="${f}" data-l="${l}"><div class="k">STAGE ${i + 1}</div><div class="n">${n}</div><div class="d">${d}</div></div>`).join("")}</div>`;
      stageBox.getBoundingClientRect();
      requestAnimationFrame(() => stageBox.classList.add("on"));
    },
    stageOn(i) {
      for (const el of stageBox?.querySelectorAll(".vstage") ?? []) {
        const k = +el.dataset.i;
        el.classList.toggle("on", k <= i);
        el.classList.toggle("cur", k === i);
        el.style.background = k <= i ? el.dataset.f : "";
        el.style.borderColor = k === i ? INK : k < i ? el.dataset.l : "";
      }
    },
    headline({ id, text, src = "Synthetic newswire", x, y }) {
      const h = add("div", "vhead");
      h.style.left = `${x}px`;
      h.style.top = `${y}px`;
      h.innerHTML = `<div style="font:600 11px 'IBM Plex Mono',monospace;letter-spacing:.12em;text-transform:uppercase;color:#93897C">${src}</div><div style="font:700 22px/1.2 'Bricolage Grotesque',system-ui;color:${INK};margin-top:4px">${text}</div>`;
      h.id = `vh-${id}`;
      popIn(h);
      keep(id, h);
    },
    rings(sel) {
      const r = rectOf(sel);
      if (!r) return;
      for (let k = 0; k < 3; k++) {
        later(k * 330, () => {
          const c = add("div", "vring");
          c.style.left = `${r.cx}px`;
          c.style.top = `${r.cy}px`;
          c.getBoundingClientRect();
          requestAnimationFrame(() => { c.style.transform = "scale(7)"; c.style.borderWidth = "0.5px"; });
          later(1650, () => c.remove());
        });
      }
    },
    scrollTo(_scroller, target, offset = 8) {
      const r = rectOf(target);
      let el = null;
      if (typeof target === "string") {
        const [q, txt] = target.split("::");
        el = [...document.querySelectorAll(q)].find((e) => !txt || (e.textContent || "").includes(txt));
      }
      let sc = el?.parentElement;
      while (sc && !(sc.scrollHeight > sc.clientHeight + 2 && /(auto|scroll)/.test(getComputedStyle(sc).overflowY))) sc = sc.parentElement;
      if (!sc || !r) return;
      // eased by hand, so it slows with the page's clock like everything else
      const from = sc.scrollTop;
      const to = from + r.t - sc.getBoundingClientRect().top - offset;
      const t0 = performance.now();
      const step = () => {
        const k = Math.min(1, (performance.now() - t0) / 900);
        const e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
        sc.scrollTop = from + (to - from) * e;
        if (k < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    },
    bubble({ id, text, at, side = "right", nth = 0 }) {
      const r = rectOf(at, nth);
      if (!r) throw new Error(`no target ${at}`);
      const bub = add("div", "vbub");
      bub.textContent = text;
      const bw = bub.offsetWidth;
      const bh = bub.offsetHeight;
      // the bubble covers nothing it can avoid; its arrow may pass into the container its target sits in
      const obs = obstacles([bub], r);
      const { x, y } = place(r, bw, bh, side, obs);
      bub.style.left = `${x}px`;
      bub.style.top = `${y}px`;
      const bb = { l: x, t: y, r: x + bw, b: y + bh, cx: x + bw / 2, cy: y + bh / 2, w: bw, h: bh };
      const [x2, y2] = anchor(at, r, bb.cx, bb.cy);
      const [x1, y1] = startOf(bb, x2, y2);
      const route = obs.filter((o) => !inside(r, o) && !inside(o, r));
      const bend = bestBend(x1, y1, x2, y2, route);
      bub.style.transformOrigin = `${clamp(((x1 - x) / bw) * 100, 0, 100)}% ${clamp(((y1 - y) / bh) * 100, 0, 100)}%`;
      popIn(bub);
      keep(id, bub);
      drawCurve(id, x1, y1, x2, y2, { bend, delay: 280, dur: 620 });
    },
    arrow({ id, from, to, bend }) {
      const a = rectOf(from);
      const b = rectOf(to);
      if (!a || !b) throw new Error(`no arrow ends ${from} ${to}`);
      const [x2, y2] = anchor(to, b, a.cx, a.cy);
      const [x1, y1] = anchor(from, a, x2, y2, 4);
      const obs = obstacles([]).filter((o) => !inside(a, o) && !inside(b, o) && !inside(o, a) && !inside(o, b));
      drawCurve(id, x1, y1, x2, y2, { bend: bend ?? bestBend(x1, y1, x2, y2, obs), dur: 560 });
    },
    circle({ id, at, nth = 0 }) {
      const r = rectOf(at, nth);
      if (!r) throw new Error(`no target ${at}`);
      // one rule: an ellipse that clears the box by a little, wider than tall
      const rx = r.w / 2 + Math.min(14, 6 + r.w * 0.04);
      const ry = r.h / 2 + Math.min(9, 4 + r.h * 0.08);
      if (typeof at === "string") circles.set(at, { cx: r.cx, cy: r.cy, rx: rx * 1.02, ry: ry * 1.02 });
      // a clean ellipse that overshoots its start a little, as a pen would
      const pts = [];
      for (let i = 0; i <= 72; i++) {
        const a = -2.3 + (i / 72) * (Math.PI * 2 + 0.5);
        const k = 1 + (i / 72) * 0.04;
        pts.push([r.cx + Math.cos(a) * rx * k, r.cy + Math.sin(a) * ry * k]);
      }
      let d = `M${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`;
      for (let i = 1; i < pts.length - 1; i++) {
        const mx = (pts[i][0] + pts[i + 1][0]) / 2;
        const my = (pts[i][1] + pts[i + 1][1]) / 2;
        d += ` Q${pts[i][0].toFixed(1)} ${pts[i][1].toFixed(1)} ${mx.toFixed(1)} ${my.toFixed(1)}`;
      }
      const g = document.createElementNS(NS, "g");
      const halo = document.createElementNS(NS, "path");
      const line = document.createElementNS(NS, "path");
      halo.setAttribute("class", "halo"); line.setAttribute("class", "line");
      halo.setAttribute("d", d); line.setAttribute("d", d);
      g.append(halo, line);
      svg.appendChild(g);
      const len = line.getTotalLength();
      for (const p of [halo, line]) { p.style.strokeDasharray = `${len} ${len + 20}`; p.style.strokeDashoffset = `${len}`; }
      requestAnimationFrame(() => {
        for (const p of [halo, line]) { p.style.transition = `stroke-dashoffset 700ms ${EASE}`; p.style.strokeDashoffset = "0"; }
      });
      g.__retract = () => {
        if (typeof at === "string") circles.delete(at);
        for (const p of [halo, line]) { p.style.transition = "stroke-dashoffset 320ms cubic-bezier(.5,0,.75,0)"; p.style.strokeDashoffset = `${-len}`; }
        later(380, () => g.remove());
      };
      keep(id, g);
    },
    badge({ id, n, at, nth = 0, dx = 0, dy = 0, side = "center" }) {
      const r = rectOf(at, nth);
      if (!r) throw new Error(`no target ${at}`);
      const bd = add("div", "vbadge");
      bd.id = `vb-${id}`;
      bd.textContent = n;
      const x = side === "left" ? r.l - 22 : side === "right" ? r.r + 22 : r.cx;
      bd.style.left = `${x + dx - 13}px`;
      bd.style.top = `${r.cy + dy - 13}px`;
      popIn(bd);
      keep(id, bd);
    },
    clear(ids) {
      const which = ids?.length ? ids : [...items.keys()];
      for (const id of which) {
        for (const el of items.get(id) ?? []) {
          if (el.__retract) el.__retract();
          else if (el.classList?.contains("vbub") || el.classList?.contains("vbadge") || el.classList?.contains("vhead")) {
            el.classList.remove("in");
            el.classList.add("out");
            later(700, () => el.remove());
          } else el.remove();
        }
        items.delete(id);
      }
    },
  };

  // the quality check: any visible text that is not fully opaque, with when it was seen (run in a check pass only)
  window.__qc = {
    log: [],
    start(clock) {
      const vis = (el) => {
        const cs = getComputedStyle(el);
        if (cs.visibility === "hidden" || cs.display === "none") return false;
        const b = el.getBoundingClientRect();
        return b.width > 0 && b.height > 0 && b.right > 0 && b.bottom > 0 && b.left < innerWidth && b.top < innerHeight;
      };
      const eff = (el) => {
        let o = 1;
        for (let e = el; e && e.nodeType === 1; e = e.parentNode) {
          const cs = getComputedStyle(e);
          o *= parseFloat(cs.opacity || "1");
          if (e.tagName === "text" || e.tagName === "tspan") o *= parseFloat(cs.fillOpacity || "1");
        }
        const c = getComputedStyle(el).color.match(/rgba?\(([^)]+)\)/);
        if (c) { const p = c[1].split(",").map((x) => parseFloat(x)); if (p.length === 4) o *= p[3]; }
        return o;
      };
      const sheetUp = () => sheet.classList.contains("on") && getComputedStyle(sheet).transform === "none";
      this.timer = setInterval(() => {
        if (sheetUp()) return;
        const seen = new Set();
        const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        for (let n = w.nextNode(); n; n = w.nextNode()) {
          if (!n.nodeValue.trim()) continue;
          const el = n.parentElement;
          if (!el || seen.has(el) || el.closest("#vsheet, #vflash, #vcur, script, style")) continue;
          seen.add(el);
          if (!vis(el)) continue;
          const o = eff(el);
          if (o < 0.97 && o > 0.03) {
            const tag = `${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""}.${(el.getAttribute("class") || "").split(" ").slice(0, 2).join(".")}`;
            this.log.push({ t: clock(), o: +o.toFixed(2), tag, text: n.nodeValue.trim().slice(0, 40) });
          }
        }
      }, 100);
    },
  };
})();
