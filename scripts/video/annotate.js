(() => {
  if (window.__ann) return;
  const INK = "#2F2A25";
  const PAPER = "#FBF8F2";
  const BUTTER = "#F6DA7A";
  const st = document.createElement("style");
  st.textContent = `
  #caption, #toast, #gesture-hint, .hint-toast { display: none !important; }
  .sheet-panel.left:not([hidden]) { animation: vslideL .55s cubic-bezier(.2,.8,.2,1); }
  .sheet-panel.right:not([hidden]) { animation: vslideR .55s cubic-bezier(.2,.8,.2,1); }
  @keyframes vslideL { from { opacity: 0; transform: translateX(-36px); } to { opacity: 1; transform: none; } }
  @keyframes vslideR { from { opacity: 0; transform: translateX(36px); } to { opacity: 1; transform: none; } }
  .manual:not(.hidden), #console:not(.hidden), .color-pop:not(.hidden) { animation: vrise .5s cubic-bezier(.2,.8,.2,1); }
  @keyframes vrise { from { opacity: 0; transform: translateY(14px) scale(.98); } to { opacity: 1; transform: none; } }
  #drawer.open { transition: transform .7s cubic-bezier(.2,.8,.2,1), visibility 0s !important; }
  #vann-svg { position: fixed; inset: 0; width: 100vw; height: 100vh; z-index: 9990; pointer-events: none; overflow: visible; }
  #vann-svg path.draw { fill: none; stroke: ${INK}; stroke-width: 3.2; stroke-linecap: round; stroke-linejoin: round; filter: url(#vwob); }
  #vann-svg path.vcirc { fill: none; stroke: ${INK}; stroke-width: 3; stroke-linecap: round; filter: url(#vwob); }
  #vann-svg .fade { transition: opacity .35s ease; }
  .vbub { position: fixed; z-index: 9995; pointer-events: none; max-width: 300px; padding: 11px 16px 12px; background: #FFFDF8; color: ${INK};
    border: 3px solid ${INK}; border-radius: 18px; box-shadow: 5px 6px 0 ${INK}; font: 600 18px/1.25 "Bricolage Grotesque", system-ui;
    animation: vpop .55s cubic-bezier(.3,1.6,.5,1) both; transition: opacity .3s, transform .3s; }
  .vbub.out { opacity: 0; transform: scale(.85); }
  @keyframes vpop { 0% { opacity: 0; transform: scale(.35) rotate(-4deg); } 60% { opacity: 1; transform: scale(1.07) rotate(1deg); } 100% { transform: scale(1) rotate(0); } }
  .vbadge { position: fixed; z-index: 9996; pointer-events: none; min-width: 34px; height: 34px; padding: 0 8px; box-sizing: border-box; border-radius: 17px;
    background: ${BUTTER}; border: 3px solid ${INK}; box-shadow: 3px 4px 0 ${INK}; display: flex; align-items: center; justify-content: center;
    font: 800 17px "Bricolage Grotesque", system-ui; color: ${INK}; animation: vpop .5s cubic-bezier(.3,1.7,.5,1) both; transition: opacity .3s, transform .3s; }
  .vbadge.out { opacity: 0; transform: scale(.6); }
  #vchap { position: fixed; bottom: 60px; left: 50%; transform: translateX(-50%); z-index: 9980; pointer-events: none; padding: 7px 16px 8px;
    background: ${INK}; color: #FFFDF8; border-radius: 999px; font: 600 13px "IBM Plex Mono", monospace; letter-spacing: .12em; text-transform: uppercase;
    box-shadow: 0 8px 24px rgba(0,0,0,.16); opacity: 0; transition: opacity .5s ease; }
  #vchap.on { opacity: 1; }
  #vtitle { position: fixed; inset: 0; z-index: 10001; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px;
    background: ${PAPER}; opacity: 0; transition: opacity .9s ease; pointer-events: none; text-align: center; }
  #vtitle.on { opacity: 1; }
  #vtitle.instant { transition: none; }
  #vtitle .b { font: 700 64px/1.08 "Bricolage Grotesque", system-ui; color: ${INK}; letter-spacing: -.01em; }
  #vtitle .b span { color: #7C64C4; }
  #vtitle .l { font: 400 22px "Instrument Sans", system-ui; color: #665E54; }
  #vtitle .m { font: 500 13px "IBM Plex Mono", monospace; color: #93897C; letter-spacing: .14em; text-transform: uppercase; margin-top: 18px; }
  #vcover { position: fixed; inset: 0; z-index: 10002; background: ${PAPER}; display: none; }
  #vflash { position: fixed; inset: 0; z-index: 10003; background: #000; display: none; }
  #vcur { position: fixed; z-index: 10000; width: 20px; height: 20px; margin: -2px 0 0 -2px; pointer-events: none; transition: transform .12s ease; }
  #vcur.down { transform: scale(.8); }
  .vsticker { position: fixed; z-index: 9995; pointer-events: none; transform: translate(-50%, -50%) rotate(-3deg); padding: 9px 16px; background: ${BUTTER};
    border: 3px solid ${INK}; border-radius: 12px; box-shadow: 4px 5px 0 ${INK}; font: 700 20px "Bricolage Grotesque", system-ui; color: ${INK};
    animation: vpop .5s cubic-bezier(.3,1.6,.5,1) both; transition: opacity .35s; }
  .vsweep { position: fixed; z-index: 9989; pointer-events: none; background: linear-gradient(90deg, transparent, rgba(246,218,122,.55), transparent);
    animation: vsweep 1.4s ease-in-out both; }
  @keyframes vfly { from { opacity: 0; transform: translate(-50%, -160%) rotate(-12deg) scale(.8); } to { opacity: 1; transform: translate(-50%, -50%) rotate(-2.5deg) scale(1); } }
  @keyframes vring { from { opacity: .7; transform: scale(.6); } to { opacity: 0; transform: scale(9); } }
  @keyframes vsweep { from { transform: translateX(-30%); opacity: 0; } 20% { opacity: 1; } to { transform: translateX(110%); opacity: 0; } }
  `;
  document.head.appendChild(st);
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.id = "vann-svg";
  svg.innerHTML = `<defs><filter id="vwob" filterUnits="userSpaceOnUse" x="0" y="0" width="4000" height="3000"><feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves="2" seed="4"/>
    <feDisplacementMap in="SourceGraphic" scale="3.2"/></filter>
    <marker id="vhead" viewBox="0 0 12 12" refX="9" refY="6" markerWidth="11" markerHeight="11" orient="auto-start-reverse" markerUnits="userSpaceOnUse">
      <path d="M1 1.5 L10 6 L1 10.5" fill="none" stroke="${INK}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>`;
  document.body.appendChild(svg);
  const add = (tag, cls) => { const el = document.createElement(tag); if (cls) el.className = cls; document.body.appendChild(el); return el; };
  const cur = add("div"); cur.id = "vcur";
  cur.innerHTML = `<svg viewBox="0 0 18 18" width="20" height="20"><path d="M2 1.5L2 15L5.8 11.4L8.4 16.6L10.8 15.4L8.2 10.3L13.4 10.1Z" fill="${INK}" stroke="#FFFDF8" stroke-width="1.3" stroke-linejoin="round"/></svg>`;
  document.addEventListener("mousemove", (e) => { cur.style.left = `${e.clientX}px`; cur.style.top = `${e.clientY}px`; }, true);
  document.addEventListener("mousedown", () => cur.classList.add("down"), true);
  document.addEventListener("mouseup", () => cur.classList.remove("down"), true);
  const chap = add("div"); chap.id = "vchap";
  const ttl = add("div"); ttl.id = "vtitle";
  const cover = add("div"); cover.id = "vcover";
  const flash = add("div"); flash.id = "vflash";
  const items = new Map();       // id -> [elements]

  const edgeBetween = (aSel, bSel) => {
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
  };
  const rectOf = (sel, nth = 0) => {
    if (sel && typeof sel === "object" && sel.pt) {
      const [x, y] = sel.pt;
      return { l: x - 6, t: y - 6, r: x + 6, b: y + 6, cx: x, cy: y, w: 12, h: 12 };
    }
    if (typeof sel === "string" && sel.startsWith("edge:")) return edgeBetween(...sel.slice(5).split("|"));
    let els = [];
    if (typeof sel === "string" && sel.includes("::")) {
      const [q, txt] = sel.split("::");
      els = [...document.querySelectorAll(q)].filter((e) => (e.textContent || "").includes(txt));
    } else els = [...document.querySelectorAll(sel)];
    const el = els[nth] ?? els[0];
    if (!el) return null;
    const b = el.getBoundingClientRect();
    return b.width || b.height ? { l: b.left, t: b.top, r: b.right, b: b.bottom, cx: (b.left + b.right) / 2, cy: (b.top + b.bottom) / 2, w: b.width, h: b.height } : null;
  };
  const keep = (id, ...els) => { if (!items.has(id)) items.set(id, []); items.get(id).push(...els); };
  const drawOn = (path, ms = 480) => {
    const len = path.getTotalLength();
    path.style.strokeDasharray = `${len}`;
    path.style.strokeDashoffset = `${len}`;
    path.getBoundingClientRect();
    path.style.transition = `stroke-dashoffset ${ms}ms cubic-bezier(.5,0,.2,1)`;
    requestAnimationFrame(() => { path.style.strokeDashoffset = "0"; });
  };
  const edgePoint = (r, x, y, gap = 6) => {
    // where a line from (x, y) to the rect's center meets the rect, backed off by `gap`
    const dx = r.cx - x;
    const dy = r.cy - y;
    const s = Math.min((r.w / 2 + gap) / Math.abs(dx || 1e-6), (r.h / 2 + gap) / Math.abs(dy || 1e-6));
    return [r.cx - dx * Math.min(s, 1), r.cy - dy * Math.min(s, 1)];
  };
  const curve = (x1, y1, x2, y2, bend = 0.22) => {
    const mx = (x1 + x2) / 2;
    const my = (y1 + y2) / 2;
    const dx = x2 - x1;
    const dy = y2 - y1;
    return `M${x1.toFixed(1)} ${y1.toFixed(1)} Q${(mx - dy * bend).toFixed(1)} ${(my + dx * bend).toFixed(1)} ${x2.toFixed(1)} ${y2.toFixed(1)}`;
  };
  const pathEl = (d, cls = "draw", head = true) => {
    const p = document.createElementNS(NS, "path");
    p.setAttribute("d", d);
    p.setAttribute("class", `${cls} fade`);
    if (head) p.setAttribute("marker-end", "url(#vhead)");
    svg.appendChild(p);
    return p;
  };

  const STAGES = [["Intake", "reads the article into operations", "#F7E1D3", "#E0B092"],
    ["Working memory", "folds it into the current graph", "#E1ECDF", "#A9C6A9"],
    ["Long-term memory", "learns what generalizes", "#DCE6F0", "#A9BFD6"],
    ["Review", "a person keeps what makes sense", "#DAD0F4", "#7C64C4"],
    ["Commit", "a new version", "#E7E0F3", "#B9ACD8"]];
  let stageBox = null;
  window.__ann = {
    stages(on) {
      if (!on) { if (stageBox) { stageBox.style.opacity = "0"; const sb = stageBox; setTimeout(() => sb.remove(), 500); stageBox = null; } return; }
      stageBox = add("div");
      stageBox.style.cssText = "position:fixed;inset:0;z-index:9985;display:flex;align-items:center;justify-content:center;background:rgba(251,248,242,.88);opacity:0;transition:opacity .6s ease;pointer-events:none";
      stageBox.innerHTML = `<div style="display:flex;align-items:center;gap:10px">${STAGES.map(([n, d, f, l], i) => `${i ? `<svg width="44" height="24" viewBox="0 0 44 24"><path d="M3 12 Q22 4 38 12" fill="none" stroke="${INK}" stroke-width="3" stroke-linecap="round" filter="url(#vwob)"/><path d="M31 6 L39 12 L31 18" fill="none" stroke="${INK}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>` : ""}
        <div class="vstage" data-i="${i}" style="width:188px;padding:16px 14px 18px;border-radius:18px;background:${f};border:3px solid ${l};text-align:center;opacity:.35;transform:scale(.94);transition:all .5s cubic-bezier(.3,1.5,.5,1)">
          <div style="font:600 12px 'IBM Plex Mono',monospace;letter-spacing:.14em;color:#665E54">STAGE ${i + 1}</div>
          <div style="font:700 22px 'Bricolage Grotesque',system-ui;color:${INK};margin:4px 0 6px">${n}</div>
          <div style="font:500 14.5px 'Instrument Sans',system-ui;color:#3d362f;line-height:1.3">${d}</div></div>`).join("")}</div>`;
      requestAnimationFrame(() => { stageBox.style.opacity = "1"; });
    },
    stageOn(i) {
      for (const el of stageBox?.querySelectorAll(".vstage") ?? []) {
        const on = +el.dataset.i <= i;
        const cur = +el.dataset.i === i;
        el.style.opacity = on ? "1" : ".35";
        el.style.transform = cur ? "scale(1.07)" : on ? "scale(1)" : "scale(.94)";
        el.style.boxShadow = cur ? `5px 6px 0 ${INK}` : "none";
        el.style.borderColor = cur ? INK : "";
      }
    },
    headline({ id, text, src = "Synthetic newswire", x, y }) {
      const h = add("div");
      h.style.cssText = `position:fixed;z-index:9994;left:${x}px;top:${y}px;width:330px;padding:12px 16px 14px;background:#FFFDF8;border:3px solid ${INK};border-radius:6px;box-shadow:6px 7px 0 ${INK};pointer-events:none;transform:translate(-50%,-50%) rotate(-2.5deg);animation:vfly .8s cubic-bezier(.2,1.2,.4,1) both`;
      h.innerHTML = `<div style="font:600 11px 'IBM Plex Mono',monospace;letter-spacing:.12em;text-transform:uppercase;color:#93897C">${src}</div><div style="font:700 22px/1.2 'Bricolage Grotesque',system-ui;color:${INK};margin-top:4px">${text}</div>`;
      h.className = "vhead";
      h.id = `vh-${id}`;
      keep(id, h);
    },
    rings(sel) {
      const r = rectOf(sel);
      if (!r) return;
      for (let k = 0; k < 3; k++) {
        const c = add("div");
        c.style.cssText = `position:fixed;z-index:9988;left:${r.cx}px;top:${r.cy}px;width:40px;height:40px;margin:-20px 0 0 -20px;border:3px solid ${INK};border-radius:50%;pointer-events:none;opacity:0;animation:vring 1.6s ease-out ${k * 0.35}s both`;
        setTimeout(() => c.remove(), 2600);
      }
    },
    scrollTo(_scroller, target, offset = 8) {
      // the target's own scrolling ancestor
      const r = rectOf(target);
      let el = null;
      if (typeof target === "string") {
        const [q, txt] = target.split("::");
        el = [...document.querySelectorAll(q)].find((e) => !txt || (e.textContent || "").includes(txt));
      }
      let sc = el?.parentElement;
      while (sc && !(sc.scrollHeight > sc.clientHeight + 2 && /(auto|scroll)/.test(getComputedStyle(sc).overflowY))) sc = sc.parentElement;
      if (!sc || !r) return;
      sc.scrollTo({ top: sc.scrollTop + r.t - sc.getBoundingClientRect().top - offset, behavior: "smooth" });
    },
    cinematic(r) {
      // slower, eased camera moves (0 stays instant, for off-camera setup)
      const z = r.zoom;
      const slow = (d) => (d === 0 ? 0 : Math.max(850, (d ?? 320) * 2.6));
      const f = z.fit.bind(z); z.fit = (b, d, o) => f(b, slow(d), o);
      const s = z.set.bind(z); z.set = (t, d) => s(t, slow(d));
      const c = z.centerOn.bind(z); z.centerOn = (x, y, k, d, dx) => c(x, y, k, slow(d), dx);
      const p = z.panBy.bind(z); z.panBy = (dx, dy, d) => p(dx, dy, slow(d));
      const fit = r.fit.bind(r); r.fit = (d) => fit(d === 0 ? 0 : slow(d));
      r.sim.velocityDecay(0.6);
    },
    title(b, l, m, instant = false) {
      ttl.classList.toggle("instant", !!instant);
      ttl.innerHTML = `<div class="b">${b}</div><div class="l">${l}</div>${m ? `<div class="m">${m}</div>` : ""}`;
      ttl.classList.add("on");
    },
    titleOff() { ttl.classList.remove("instant"); ttl.classList.remove("on"); },
    cover(on) { cover.style.display = on ? "block" : "none"; },
    flash() { flash.style.display = "block"; setTimeout(() => { flash.style.display = "none"; }, 240); },
    chapter(t) {
      chap.classList.remove("on");
      setTimeout(() => { chap.textContent = t; chap.classList.add("on"); }, chap.textContent ? 350 : 0);
    },
    pulse(sel, nth, text) {
      const r = rectOf(sel, nth);
      if (!r) return;
      const s = add("div", "vsticker");
      s.textContent = text;
      s.style.left = `${r.cx}px`;
      s.style.top = `${r.t + Math.min(r.h * 0.42, 360)}px`;
      setTimeout(() => { s.style.opacity = "0"; setTimeout(() => s.remove(), 400); }, 1500);
    },
    sweep(sel) {
      const r = rectOf(sel);
      if (!r) return;
      const s = add("div", "vsweep");
      Object.assign(s.style, { left: `${r.l}px`, top: `${r.t}px`, width: `${r.w}px`, height: `${r.h}px` });
      setTimeout(() => s.remove(), 1500);
    },
    bubble({ id, text, at, side = "right", nth = 0, dx = 0, dy = 0, dist }) {
      const r = rectOf(at, nth);
      if (!r) throw new Error(`no target ${at}`);
      const bub = add("div", "vbub");
      bub.textContent = text;
      const bw = bub.offsetWidth;
      const bh = bub.offsetHeight;
      const d = dist ?? 110;
      let x;
      let y;
      if (side === "right") { x = r.r + d; y = r.cy - bh / 2; }
      else if (side === "left") { x = r.l - d - bw; y = r.cy - bh / 2; }
      else if (side === "top") { x = r.cx - bw / 2; y = r.t - d - bh; }
      else { x = r.cx - bw / 2; y = r.b + d; }
      x = Math.max(16, Math.min(innerWidth - bw - 24, x + dx));
      y = Math.max(16, Math.min(innerHeight - bh - 60, y + dy));
      bub.style.left = `${x}px`;
      bub.style.top = `${y}px`;
      const bb = { l: x, t: y, r: x + bw, b: y + bh, cx: x + bw / 2, cy: y + bh / 2, w: bw, h: bh };
      const [x1, y1] = edgePoint(bb, r.cx, r.cy, 4);
      const [x2, y2] = edgePoint(r, bb.cx, bb.cy, 7);
      const p = pathEl(curve(x1, y1, x2, y2));
      p.style.opacity = "0";
      setTimeout(() => { p.style.opacity = "1"; drawOn(p, 520); }, 260);
      bub.style.transformOrigin = `${Math.max(0, Math.min(100, ((x2 - x) / bw) * 100))}% ${Math.max(0, Math.min(100, ((y2 - y) / bh) * 100))}%`;
      keep(id, bub, p);
    },
    arrow({ id, from, to }) {
      const a = rectOf(from);
      const b = rectOf(to);
      if (!a || !b) throw new Error(`no arrow ends ${from} ${to}`);
      const [x1, y1] = edgePoint(a, b.cx, b.cy, 6);
      const [x2, y2] = edgePoint(b, a.cx, a.cy, 8);
      const p = pathEl(curve(x1, y1, x2, y2, 0.3));
      drawOn(p, 520);
      keep(id, p);
    },
    circle({ id, at, nth = 0, pad = 10 }) {
      const r = rectOf(at, nth);
      if (!r) throw new Error(`no target ${at}`);
      const rx = r.w / 2 + pad + 4;
      const ry = r.h / 2 + pad;
      const pts = [];
      for (let i = 0; i <= 64; i++) {
        const a = -2.2 + (i / 64) * (Math.PI * 2 + 0.55);
        const k = 1 + 0.045 * Math.sin(i * 0.9) + (i / 64) * 0.06;
        pts.push([r.cx + Math.cos(a) * rx * k, r.cy + Math.sin(a) * ry * k]);
      }
      const p = pathEl(`M${pts.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join(" L")}`, "vcirc", false);
      drawOn(p, 650);
      keep(id, p);
    },
    badge({ id, n, at, nth = 0, dx = 0, dy = 0, side = "center" }) {
      const r = rectOf(at, nth);
      if (!r) throw new Error(`no target ${at}`);
      const bd = add("div", "vbadge");
      bd.id = `vb-${id}`;
      bd.textContent = n;
      const x = side === "left" ? r.l - 26 : side === "right" ? r.r + 26 : r.cx;
      bd.style.left = `${x + dx - 17}px`;
      bd.style.top = `${r.cy + dy - 17}px`;
      keep(id, bd);
    },
    clear(ids) {
      const which = ids?.length ? ids : [...items.keys()];
      for (const id of which) {
        for (const el of items.get(id) ?? []) {
          if (el.classList?.contains("vbub")) el.classList.add("out");
          else if (el.classList?.contains("vbadge")) el.classList.add("out");
          else if (el.classList?.contains("vhead")) { el.style.transition = "opacity .35s"; el.style.opacity = "0"; }
          else el.style.opacity = "0";
          setTimeout(() => el.remove(), 380);
        }
        items.delete(id);
      }
    },
  };
})();
