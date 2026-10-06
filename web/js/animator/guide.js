// The guide (addition). DECISION: the user asked for a small animal, not a hijacked mouse, to show what
// the model does the first time it forecasts. A raccoon hops to whatever the model is working on and
// says what it does in one short line, while a soft spotlight marks the thing it means on the canvas.
// It is paced by the trace (the player awaits it), it never takes input from the user, a click on its
// bubble skips ahead, and it can be switched off (Admin › Settings, or the bubble's "Turn off").
// Modes: "first" (the first forecast and the first news, once per browser), "always", or "off".
import { store } from "../store.js";

const KEY_MODE = "axelrod.guide.mode";
const KEY_SEEN = "axelrod.guide.seen";

const RACCOON = `<svg viewBox="0 0 52 46" width="46" height="41" aria-hidden="true">
  <g class="ears">
    <path d="M9 17 L5.5 4.5 L19 10.5 Z" fill="#8F8983" stroke="#3E3833" stroke-width="1.6" stroke-linejoin="round"/>
    <path d="M43 17 L46.5 4.5 L33 10.5 Z" fill="#8F8983" stroke="#3E3833" stroke-width="1.6" stroke-linejoin="round"/>
    <path d="M9.6 13.6 L8 7.2 L15 10.4 Z" fill="#E6C6BC"/>
    <path d="M42.4 13.6 L44 7.2 L37 10.4 Z" fill="#E6C6BC"/>
  </g>
  <ellipse cx="26" cy="27" rx="19.5" ry="16" fill="#A8A29B" stroke="#3E3833" stroke-width="1.6"/>
  <path d="M10.5 26 Q26 14.5 41.5 26 Q39.5 40.5 26 43 Q12.5 40.5 10.5 26 Z" fill="#F5F1EA"/>
  <path d="M7.5 24 Q16.5 16 26 22.5 Q35.5 16 44.5 24 Q41 31.5 33 30.5 Q26 27 19 30.5 Q11 31.5 7.5 24 Z" fill="#37322E"/>
  <g class="eyes">
    <circle cx="18" cy="24.5" r="2.9" fill="#fff"/><circle cx="18.6" cy="24.8" r="1.7" fill="#1E1A17"/>
    <circle cx="34" cy="24.5" r="2.9" fill="#fff"/><circle cx="33.4" cy="24.8" r="1.7" fill="#1E1A17"/>
    <circle cx="19.2" cy="24" r="0.55" fill="#fff"/><circle cx="34" cy="24" r="0.55" fill="#fff"/>
  </g>
  <ellipse cx="26" cy="33.5" rx="2.9" ry="2.1" fill="#2A2522"/>
  <path d="M26 35.6 Q23.8 38.4 21.6 37.2 M26 35.6 Q28.2 38.4 30.4 37.2" stroke="#2A2522" stroke-width="1.2" fill="none" stroke-linecap="round"/>
  <ellipse cx="14.5" cy="33" rx="2.4" ry="1.3" fill="#EBB7AE" opacity="0.7"/><ellipse cx="37.5" cy="33" rx="2.4" ry="1.3" fill="#EBB7AE" opacity="0.7"/>
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
    const read = ms ?? Math.max(1400, Math.min(4000, 800 + 27 * text.length)) / speed;
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
    if (cam) this.renderer.zoom?.set(cam, store.settings.reducedMotion ? 0 : 600);
  }

  stop() {
    this.skip?.();
    this.run = null;
    this.spot(null);
    document.body.classList.remove("guided");
    this.el.classList.add("leaving");
    setTimeout(() => { if (!this.run) this.el.classList.add("hidden"); }, 380);
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
                     { transform: to }], { duration: 620, easing: "cubic-bezier(.35,.1,.25,1)" });
    this.el.style.transform = to;
    this.critter.classList.remove("land");
    void this.critter.offsetWidth;
    this.critter.classList.add("land");
  }
}
