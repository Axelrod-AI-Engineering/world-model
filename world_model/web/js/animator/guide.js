// The guide (addition). DECISION: the user asked for a small animal, not a hijacked mouse, to show what
// the model does the first time it forecasts. A red panda hops to whatever the model is working on and
// says what it does in one short line, while a soft spotlight marks the thing it means on the canvas.
// It is paced by the trace (the player awaits it), it never takes input from the user, a click on its
// bubble skips ahead, and it can be switched off (Admin › Settings, or the bubble's "Turn off").
// Modes: "first" (the first forecast and the first news, once per browser), "always", or "off".
import { store } from "../store.js";

const KEY_MODE = "axelrod.guide.mode";
const KEY_SEEN = "axelrod.guide.seen";

// a red panda (review, Oct 14: the old raccoon read as a red panda in goggles, so it became a clear one): rust fur, white
// ear rims, white brows, cheeks, and muzzle, dark tear marks under dark eyes, a small dark nose. Flat, a few shapes, the
// canvas's inks; the eyes blink now and then (CSS)
const RED_PANDA = `<svg viewBox="0 0 52 48" width="46" height="42" aria-hidden="true">
  <path d="M9.5 47.5 Q26 35.2 42.5 47.5 Z" fill="#5A2A17"/>
  <path d="M6.4 21.4 Q3.6 8.2 13.6 5.8 Q19.4 7.6 20.8 13.2 Z" fill="#FBF6EE" stroke="#2F2A25" stroke-width="1.4" stroke-linejoin="round"/>
  <path d="M45.6 21.4 Q48.4 8.2 38.4 5.8 Q32.6 7.6 31.2 13.2 Z" fill="#FBF6EE" stroke="#2F2A25" stroke-width="1.4" stroke-linejoin="round"/>
  <path d="M9.2 18.6 Q8 10.6 13.8 9.2 Q17.2 10.4 18 13.8 Z" fill="#7A3418"/>
  <path d="M42.8 18.6 Q44 10.6 38.2 9.2 Q34.8 10.4 34 13.8 Z" fill="#7A3418"/>
  <path d="M26 10.4 C38.6 10.4 46.6 17.8 46.6 26.6 C46.6 35.6 37.6 41.9 26 41.9 C14.4 41.9 5.4 35.6 5.4 26.6 C5.4 17.8 13.4 10.4 26 10.4 Z" fill="#C4612F" stroke="#2F2A25" stroke-width="1.4"/>
  <path d="M26 12.6 Q18.6 13.4 16.6 18.6 Q26 15.8 35.4 18.6 Q33.4 13.4 26 12.6 Z" fill="#D47A42"/>
  <path d="M7 28.6 Q7.8 22.6 14 23.2 Q14.2 31.2 19.6 36.8 Q10.6 37 7 28.6 Z" fill="#FBF6EE"/>
  <path d="M45 28.6 Q44.2 22.6 38 23.2 Q37.8 31.2 32.4 36.8 Q41.4 37 45 28.6 Z" fill="#FBF6EE"/>
  <ellipse cx="26" cy="33.4" rx="7.4" ry="5.8" fill="#FBF6EE"/>
  <ellipse cx="18.6" cy="19.4" rx="2.7" ry="1.7" transform="rotate(-12 18.6 19.4)" fill="#FBF6EE"/>
  <ellipse cx="33.4" cy="19.4" rx="2.7" ry="1.7" transform="rotate(12 33.4 19.4)" fill="#FBF6EE"/>
  <path d="M17.6 26.2 Q16.4 30.6 19.6 34.4 M34.4 26.2 Q35.6 30.6 32.4 34.4" stroke="#6A2C14" stroke-width="2.6" fill="none" stroke-linecap="round"/>
  <g class="eyes">
    <circle cx="19" cy="24.4" r="2.5" fill="#2A2522"/>
    <circle cx="33" cy="24.4" r="2.5" fill="#2A2522"/>
    <circle cx="19.8" cy="23.6" r="0.8" fill="#FFFDF8"/>
    <circle cx="33.8" cy="23.6" r="0.8" fill="#FFFDF8"/>
  </g>
  <path d="M23.4 30 Q26 28.9 28.6 30 Q27.8 32.4 26 32.6 Q24.2 32.4 23.4 30 Z" fill="#2A2522"/>
  <path d="M26 32.6 Q25.2 35.2 23 34.8 M26 32.6 Q26.8 35.2 29 34.8" stroke="#2A2522" stroke-width="1.1" fill="none" stroke-linecap="round"/>
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
    this.el.innerHTML = `<div class="critter">${RED_PANDA}</div>
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
    // a passing line (wait: false) that follows another within a moment changes the words in place: no hop, no pop,
    // so a quick run of steps does not make the guide flicker across the canvas (Oct 11)
    const now = performance.now();
    if (!wait && now - (this.lastPop ?? 0) < 2200) {
      this.spot(target);
      this.txt.textContent = text;
      this.sub.textContent = "";
      return;
    }
    this.lastPop = now;
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
