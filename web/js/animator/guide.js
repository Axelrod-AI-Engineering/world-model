// The guide (addition). DECISION: the user asked for a small animal, not a hijacked mouse, to show what
// the model does the first time it forecasts. A raccoon hops to whatever the model is working on and
// says what it does in one short line, while a soft spotlight marks the thing it means on the canvas.
// It is paced by the trace (the player awaits it), it never takes input from the user, a click on its
// bubble skips ahead, and it can be switched off (Admin › Settings, or the bubble's "Turn off").
// Modes: "first" (the first forecast and the first news, once per browser), "always", or "off".
import { store } from "../store.js";

const KEY_MODE = "axelrod.guide.mode";
const KEY_SEEN = "axelrod.guide.seen";

// a raccoon in sunglasses, after the team's sticker: flat, a few shapes, the canvas's inks
const RACCOON = `<svg viewBox="0 0 52 48" width="46" height="42" aria-hidden="true">
  <path d="M9.5 47.5 Q26 35.5 42.5 47.5 Z" fill="#37312D"/>
  <path d="M12 16.5 L8.6 4.6 Q15 6.4 20.4 11.4 Z" fill="#8E8780" stroke="#2F2A25" stroke-width="1.4" stroke-linejoin="round"/>
  <path d="M40 16.5 L43.4 4.6 Q37 6.4 31.6 11.4 Z" fill="#8E8780" stroke="#2F2A25" stroke-width="1.4" stroke-linejoin="round"/>
  <path d="M12.6 13.2 L11.1 7.9 L16.4 10.8 Z" fill="#EFE3D7"/>
  <path d="M39.4 13.2 L40.9 7.9 L35.6 10.8 Z" fill="#EFE3D7"/>
  <path d="M26 9.2 C37.2 9.2 45.2 16.3 45.6 25.2 C46 33.6 38.8 41.4 26 41.9 C13.2 41.4 6 33.6 6.4 25.2 C6.8 16.3 14.8 9.2 26 9.2 Z" fill="#A49D95" stroke="#2F2A25" stroke-width="1.4"/>
  <path d="M26 11.2 Q24.4 15.6 25.1 18.8 Q26 19.8 26.9 18.8 Q27.6 15.6 26 11.2 Z" fill="#857D76"/>
  <path d="M9.4 26.4 Q26 15.6 42.6 26.4 Q40.6 38.6 26 40.8 Q11.4 38.6 9.4 26.4 Z" fill="#F4F0E8"/>
  <path d="M7.6 25.2 Q15.2 18.6 26 23.2 Q36.8 18.6 44.4 25.2 Q41 31.2 33 30.4 Q26 28.2 19 30.4 Q11 31.2 7.6 25.2 Z" fill="#2F2A25"/>
  <g class="shades">
    <rect x="11.6" y="21.4" width="11.8" height="7.2" rx="3.2" fill="#E8643B" stroke="#2F2A25" stroke-width="1.2"/>
    <rect x="28.6" y="21.4" width="11.8" height="7.2" rx="3.2" fill="#E8643B" stroke="#2F2A25" stroke-width="1.2"/>
    <path d="M23.4 24 Q26 22.4 28.6 24" stroke="#2F2A25" stroke-width="1.3" fill="none"/>
    <path class="glint" d="M13.8 23.4 L17.4 23.4 M30.8 23.4 L34.4 23.4" stroke="#FFE0D2" stroke-width="1.1" stroke-linecap="round"/>
  </g>
  <ellipse cx="26" cy="33.8" rx="2.7" ry="1.9" fill="#2A2522"/>
  <path d="M26 35.6 Q24.4 37.6 22.6 36.8 M26 35.6 Q27.6 37.6 29.4 36.8" stroke="#2A2522" stroke-width="1.1" fill="none" stroke-linecap="round"/>
</svg>`;

function load(key, fallback) {
  try { const v = localStorage.getItem(key); return v == null ? fallback : JSON.parse(v); } catch { return fallback; }
}
function save(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode: per session only */ }
}

export class Guide {
  constructor({ renderer, stage, onModeChange }) {
    this.renderer = renderer;
    this.stage = stage;
    this.onModeChange = onModeChange;
    this.mode = load(KEY_MODE, "first");
    this.seen = load(KEY_SEEN, {});
    this.run = null;
    this.skip = null;
    this.el = document.createElement("div");
    this.el.id = "guide";
    this.el.className = "guide hidden";
    this.el.setAttribute("role", "status");
    this.el.setAttribute("aria-live", "polite");
    this.el.innerHTML = `<div class="critter">${RACCOON}</div>
      <div class="bubble"><span class="txt"></span><span class="sub"></span>
        <span class="ctl"><button class="next" title="Next (or click the bubble)">▸</button><button class="off" title="Turn the guide off">Turn off</button>
          <button class="x" aria-label="Stop the guide">✕</button></span></div>`;
    stage.appendChild(this.el);
    this.critter = this.el.querySelector(".critter");
    this.bubble = this.el.querySelector(".bubble");
    this.txt = this.el.querySelector(".txt");
    this.sub = this.el.querySelector(".sub");
    this.pos = null;
    this.bubble.addEventListener("click", (ev) => {
      if (ev.target.closest(".x")) { this.stop(); return; }
      if (ev.target.closest(".off")) { this.setMode("off"); this.stop(); return; }
      this.skip?.();
    });
  }

  setMode(mode) {
    this.mode = mode;
    save(KEY_MODE, mode);
    this.onModeChange?.(mode);
  }

  // Start a guided run (a forecast or a piece of news) if the mode allows it; returns whether it did.
  begin(kind, scope) {
    if (this.run) return this.run.scope === scope;
    if (this.mode === "off" || store.walkthrough) return false;
    if (this.mode === "first" && this.seen[kind]) return false;
    this.seen[kind] = true;
    save(KEY_SEEN, this.seen);
    const t = this.renderer.zoom?.transform();
    this.run = { kind, scope, camera: t ? { x: t.x, y: t.y, k: t.k } : null };
    document.body.classList.add("guided");
    this.el.classList.remove("hidden", "leaving");
    return true;
  }

  active(scope = null) {
    return !!this.run && (scope == null || this.run.scope === scope || this.run.kind === "forecast" && /^T-/.test(scope ?? ""));
  }

  // Frame the things a step is about, inside what the side panels leave visible.
  frame(ids) {
    if (!this.run || !ids?.length) return;
    const canvas = document.getElementById("canvas").getBoundingClientRect();
    const lp = document.getElementById("left-panel");
    const rp = document.getElementById("right-panel");
    const left = lp && !lp.hidden ? lp.getBoundingClientRect().right - canvas.left : 0;
    const right = rp && !rp.hidden ? canvas.right - rp.getBoundingClientRect().left : 0;
    this.renderer.frame(ids, { top: 80, left: Math.max(0, left), right: Math.max(0, right), maxK: 1.05 });
  }

  // Hop next to a target and say one line. `target`: an id or ids on the canvas, {el} for a DOM element.
  async say(text, target, { wait = true, ms = null } = {}) {
    if (!this.run) return;
    const rect = this.rectOf(target);
    this.spot(target);
    this.moveTo(rect);
    this.txt.textContent = text;
    this.sub.textContent = "";
    this.bubble.classList.remove("pop");
    void this.bubble.offsetWidth;
    this.bubble.classList.add("pop");
    if (!wait) return;
    const speed = store.settings.speed || 1;
    const read = ms ?? Math.max(900, Math.min(2600, 450 + 17 * text.length)) / speed;
    await new Promise((resolve) => {
      const timer = setTimeout(resolve, store.settings.reducedMotion ? Math.min(read, 1200) : read);
      this.skip = () => { clearTimeout(timer); resolve(); };
    });
    this.skip = null;
  }

  // a small second line that changes without moving the guide (the day being simulated)
  note(text) {
    if (this.run) this.sub.textContent = text;
  }

  async end(text = null, target = null) {
    if (!this.run) return;
    if (text) await this.say(text, target);
    const cam = this.run.camera;
    this.stop();
    if (cam) this.renderer.zoom?.set(cam, store.settings.reducedMotion ? 0 : 320);
  }

  stop() {
    this.skip?.();
    this.run = null;
    this.spot(null);
    document.body.classList.remove("guided");
    this.el.classList.add("leaving");
    setTimeout(() => { if (!this.run) this.el.classList.add("hidden"); }, 220);
  }

  // -- placement ----------------------------------------------------------------------------------------
  rectOf(target) {
    if (!target) return null;
    if (target.el) return target.el.getBoundingClientRect();
    const ids = Array.isArray(target) ? target : [target];
    let r = null;
    for (const id of ids) {
      const s = this.renderer.screenOf(id);
      if (!s) continue;
      r = r ? { left: Math.min(r.left, s.left), top: Math.min(r.top, s.top), right: Math.max(r.right, s.right), bottom: Math.max(r.bottom, s.bottom) } : s;
    }
    return r;
  }

  spot(target) {
    for (const el of document.querySelectorAll(".guide-spot")) el.classList.remove("guide-spot");
    if (target?.el) { target.el.classList.add("guide-spot"); this.renderer.spotlight([]); return; }
    const ids = target == null ? [] : Array.isArray(target) ? target : [target];
    this.renderer.spotlight(ids.slice(0, 8));
  }

  moveTo(rect) {
    const stage = this.stage.getBoundingClientRect();
    const W = 46;
    let x;
    let y;
    if (rect) {
      // sit just above the target's top-left corner, as if pointing at it
      x = rect.left - stage.left - W + 8;
      y = rect.top - stage.top - 44;
      if (rect.width != null && rect.left > stage.right - 120) x = rect.left - stage.left - W - 6;
    } else {
      x = this.pos?.x ?? stage.width / 2;
      y = this.pos?.y ?? 120;
    }
    x = Math.max(6, Math.min(stage.width - 60, x));
    y = Math.max(6, Math.min(stage.height - 60, y));
    const flip = x > stage.width - 380;
    this.el.classList.toggle("flip", flip);
    const from = this.pos;
    this.pos = { x, y };
    const to = `translate(${x}px, ${y}px)`;
    if (!from || store.settings.reducedMotion) {
      this.el.style.transform = to;
      return;
    }
    // a hop: up and over, landing with a small bounce
    const mx = (from.x + x) / 2;
    const my = Math.min(from.y, y) - Math.min(70, 20 + Math.hypot(x - from.x, y - from.y) * 0.15);
    this.el.animate([{ transform: `translate(${from.x}px, ${from.y}px)` }, { transform: `translate(${mx}px, ${my}px)`, offset: 0.45 },
                     { transform: to }], { duration: 360, easing: "cubic-bezier(.35,.1,.25,1)" });
    this.el.style.transform = to;
    this.critter.classList.remove("land");
    void this.critter.offsetWidth;
    this.critter.classList.add("land");
  }
}
