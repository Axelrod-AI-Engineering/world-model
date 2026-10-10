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
  @keyframes vslideL { from { clip-path: inset(0 100% 0 0 round 14px); } to { clip-path: inset(0 0 0 0 round 14px); } }
  @keyframes vslideR { from { clip-path: inset(0 0 0 100% round 14px); } to { clip-path: inset(0 0 0 0 round 14px); } }
  .manual:not(.hidden), #console:not(.hidden) { animation: vrise .7s ${EASE}; }
  @keyframes vrise { from { clip-path: inset(100% 0 0 0 round 14px); } to { clip-path: inset(0 0 0 0 round 14px); } }
  #drawer.open { transition: transform .8s ${EASE}, visibility 0s !important; }
  #vann-svg { position: fixed; inset: 0; width: 100vw; height: 100vh; z-index: 9990; pointer-events: none; overflow: visible; }
  #vann-svg .halo { fill: none; stroke: ${PAPER}; stroke-width: 9; stroke-linecap: round; stroke-linejoin: round; }
  #vann-svg .line { fill: none; stroke: ${INK}; stroke-width: 3.6; stroke-linecap: round; stroke-linejoin: round; }
  #vann-svg .head { fill: ${INK}; stroke: ${PAPER}; stroke-width: 2.4; stroke-linejoin: round; transform-box: view-box; transform-origin: 0 0; }
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

  const points = {};               // named points (a traced edge's middle)
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
  const geom = [];                 // every arrow drawn: where it starts, its tip, its direction, what it points at
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
  function anchor(sel, r, x, y, gap = 6) {
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
    // an interaction, traced in ink over its own line; its middle is named for a bubble to point at
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
    underline({ id, at, nth = 0 }) {
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
    liveTips() { return geom.map((g) => ({ id: g.id, tip: g.tip, from: g.from })); },
    liveCircles() { return [...circles.entries()].map(([k, e]) => ({ sel: k, ...e })); },
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
      // the bubble covers nothing it can avoid; its arrow may pass into the container its target sits in, but should
      // cross as few of that container's words as it can
      const obs = obstacles([bub], r);
      const holder = elOf(at, nth)?.closest("#left-panel, #right-panel, .manual, #drawer.open, #console");
      const texts = holder ? textBoxes(holder).filter((t) => ov(t, { l: r.l - 2, t: r.t - 2, r: r.r + 2, b: r.b + 2 }) === 0) : [];
      const { x, y } = place(r, bw, bh, side, obs, at, texts);
      bub.style.left = `${x}px`;
      bub.style.top = `${y}px`;
      const bb = { l: x, t: y, r: x + bw, b: y + bh, cx: x + bw / 2, cy: y + bh / 2, w: bw, h: bh };
      let [x2, y2, n2x, n2y] = anchor(at, r, bb.cx, bb.cy);
      let [x1, y1, n1x, n1y] = startOf(bb, x2, y2);
      const route = [...obs.filter((o) => !inside(r, o) && !inside(o, r)), ...texts];
      // a ringed target can be met anywhere on its ring: take the point whose arrow crosses the least, then turns the least
      const ringC = circles.get(at);
      if (ringC) {
        let best = null;
        for (let i = 0; i < 64; i++) {
          const a = (i / 64) * Math.PI * 2;
          const [ax, ay, anx, any] = anchor(at, r, ringC.cx + Math.cos(a) * 4000, ringC.cy + Math.sin(a) * 4000);
          const [sx, sy, snx, sny] = startOf(bb, ax, ay);
          const L = Math.hypot(ax - sx, ay - sy) || 1;
          const ch = [(ax - sx) / L, (ay - sy) / L];
          const turn = Math.acos(clamp(snx * ch[0] + sny * ch[1], -1, 1)) + Math.acos(clamp(-anx * ch[0] - any * ch[1], -1, 1));
          const cost = hits(arrowPts(sx, sy, [snx, sny], ax, ay, [anx, any]), route) * 1000 + turn * 40 + L * 0.15;
          if (!best || cost < best.cost) best = { cost, a: [ax, ay, anx, any], s: [sx, sy, snx, sny] };
        }
        [x2, y2, n2x, n2y] = best.a;
        [x1, y1, n1x, n1y] = best.s;
      }
      const bend = bestBend(x1, y1, x2, y2, route);
      bub.style.transformOrigin = `${clamp(((x1 - x) / bw) * 100, 0, 100)}% ${clamp(((y1 - y) / bh) * 100, 0, 100)}%`;
      popIn(bub);
      keep(id, bub);
      drawCurve(id, x1, y1, x2, y2, { bend, delay: 200, dur: 520, target: circles.get(at) ? { ellipse: circles.get(at) } : r, sel: at, n1: [n1x, n1y], n2: [n2x, n2y] });
    },
    arrow({ id, from, to, bend }) {
      const a = rectOf(from);
      const b = rectOf(to);
      if (!a || !b) throw new Error(`no arrow ends ${from} ${to}`);
      const [x2, y2, n2x, n2y] = anchor(to, b, a.cx, a.cy);
      // an arrow leaves its source from the side facing its target, never level like words
      const [x1, y1, n1x, n1y] = anchor(from, { ...a, text: false, badge: true }, x2, y2, 4);
      const obs = obstacles([]).filter((o) => !inside(a, o) && !inside(b, o) && !inside(o, a) && !inside(o, b));
      drawCurve(id, x1, y1, x2, y2, { bend: bend ?? bestBend(x1, y1, x2, y2, obs), dur: 560, target: circles.get(to) ? { ellipse: circles.get(to) } : b, sel: to, n1: [n1x, n1y], n2: [n2x, n2y] });
    },
    circle({ id, at, nth = 0 }) {
      const r = rectOf(at, nth);
      if (!r) throw new Error(`no target ${at}`);
      // one rule: a ring that clears the box by a little. a line of words or a tab gets an ellipse; a tall or very wide
      // box gets a rounded rectangle a fixed 7px outside it, so the line never cuts through what it encloses
      const n = r.h < 44 && r.w / r.h < 7 ? 2 : 0;
      const rx = r.w / 2 + (n === 2 ? Math.min(14, 6 + r.w * 0.04) : 7);
      const ry = r.h / 2 + (n === 2 ? Math.min(9, 4 + r.h * 0.08) : 7);
      // the rounded rectangle, walked clockwise from its top-left corner: points with their outward normals
      let poly = null;
      if (!n) {
        poly = [];
        const R = Math.min(16, ry);
        const segs = [
          ["arc", -rx + R, -ry + R, Math.PI, Math.PI * 1.5], ["line", -rx + R, -ry, rx - R, -ry, 0, -1],
          ["arc", rx - R, -ry + R, Math.PI * 1.5, Math.PI * 2], ["line", rx, -ry + R, rx, ry - R, 1, 0],
          ["arc", rx - R, ry - R, 0, Math.PI * 0.5], ["line", rx - R, ry, -rx + R, ry, 0, 1],
          ["arc", -rx + R, ry - R, Math.PI * 0.5, Math.PI], ["line", -rx, ry - R, -rx, -ry + R, -1, 0],
        ];
        for (const sg of segs) {
          if (sg[0] === "arc") {
            const steps = 8;
            for (let k = 0; k < steps; k++) {
              const a = sg[3] + ((sg[4] - sg[3]) * k) / steps;
              poly.push([r.cx + sg[1] + Math.cos(a) * R, r.cy + sg[2] + Math.sin(a) * R, Math.cos(a), Math.sin(a)]);
            }
          } else {
            const L = Math.hypot(sg[3] - sg[1], sg[4] - sg[2]);
            const steps = Math.max(1, Math.round(L / 6));
            for (let k = 0; k < steps; k++) {
              poly.push([r.cx + sg[1] + ((sg[3] - sg[1]) * k) / steps, r.cy + sg[2] + ((sg[4] - sg[2]) * k) / steps, sg[5], sg[6]]);
            }
          }
        }
      }
      const ring = (a) => [Math.cos(a), Math.sin(a)];
      if (typeof at === "string") circles.set(at, n ? { cx: r.cx, cy: r.cy, rx: rx * 1.02, ry: ry * 1.02, n } : { cx: r.cx, cy: r.cy, rx, ry, n: 12, poly });
      // a clean ellipse that overshoots its start a little, as a pen would
      const pts = [];
      for (let i = 0; i <= 72; i++) {
        const a = -2.3 + (i / 72) * (Math.PI * 2 + 0.5);
        const k = 1 + (i / 72) * 0.04;
        const [ux, uy] = ring(a);
        pts.push([r.cx + ux * rx * k, r.cy + uy * ry * k]);
      }
      if (poly) {
        pts.length = 0;
        const N = poly.length;
        const start = Math.round(N * 0.94);
        const total = Math.round(N * 1.08);
        for (let i = 0; i <= total; i++) {
          const [px, py, nx, ny] = poly[(start + i) % N];
          const o = (i / total) * 3;
          pts.push([px + nx * o, py + ny * o]);
        }
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
