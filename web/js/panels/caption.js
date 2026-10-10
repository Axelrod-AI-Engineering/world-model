// The caption above the canvas: one line of story for each scripted step, and the read-only banner for
// earlier versions. After a step, "How it learned" and "How it inferred" buttons replay what the model did with its news and its
// questions, one step at a time.
import { backToLive, on, store } from "../store.js";
import { esc } from "../util.js";

export function initCaption({ onWalk } = {}) {
  const el = document.getElementById("caption");
  const ro = document.getElementById("readonly-banner");
  const walks = el.querySelector(".walks");
  let since = 0;          // the seq where the current caption's step began
  let shown = "";
  let cleared = null;     // the caption the user cleared (its seq); the next step's caption shows again
  const clear = document.createElement("button");
  clear.className = "cap-x";
  clear.type = "button";
  clear.textContent = "✕";
  clear.setAttribute("aria-label", "Clear the caption");
  clear.title = "Clear the caption (the next step brings its own; Admin › Settings turns captions off)";
  el.appendChild(clear);
  clear.addEventListener("click", () => { cleared = since; el.classList.add("hidden"); });
  const scopes = () => {
    const out = [];
    for (const e of store.traces) {
      if (e.seq <= since || !e.scope || out.some((o) => o.scope === e.scope)) continue;
      if (/^T-/.test(e.scope) && e.kind === "thesis.posed") out.push({ scope: e.scope, label: "How it inferred", title: `Step through how the model answered “${e.payload.question}”` });
      else if (e.kind === "market_event.received" && !/^ME-D-/.test(e.scope)) {
        out.push({ scope: e.scope, label: "How it learned", title: `Step through what the model did with “${e.payload.headline}”` });
      }
    }
    return out;
  };
  const renderWalks = () => {
    if (!onWalk) return;
    const list = scopes();
    // DECISION: at most two buttons in the caption (the newest question, and the newest news: the one the caption
    // is about); the rest are one click away in the News panel, so the caption stays one line
    const pick = [...list.filter((o) => /^T-/.test(o.scope)).slice(-1), ...list.filter((o) => !/^T-/.test(o.scope)).slice(-1)].slice(0, 2);
    const key = pick.map((o) => o.scope).join("|");
    if (key === shown) return;
    shown = key;
    walks.innerHTML = pick.map((o) => `<button class="walk-btn" data-scope="${esc(o.scope)}" title="${esc(o.title ?? "")}">${esc(o.label)} ▸</button>`).join("");
    for (const b of walks.querySelectorAll("[data-scope]")) b.addEventListener("click", () => onWalk(b.dataset.scope));
  };
  const render = () => {
    const c = store.caption;
    const st = store.status;
    const total = st?.total_steps ?? "?";
    // the trace numbers steps from 0; the top bar counts them from 1, so the caption does too
    el.querySelector(".step").textContent = c.step != null ? `${c.step + 1} / ${total}` : "";
    // DECISION: the user asked that the opening sentence go; before the first step the caption is empty and
    // hidden, and any caption can be cleared (✕) until the next step brings its own
    let text = c.text || st?.caption || "";
    const loading = !st?.loaded && !text;
    if (loading) text = "Loading the world model…";
    el.querySelector(".text").textContent = text;
    el.title = text;
    el.classList.toggle("hyp", !!c.hyp);
    el.classList.toggle("hidden", !loading && (!text || store.settings.captions === false || cleared === since));
    clear.hidden = loading;
    renderWalks();
  };
  on("caption", (c) => { if (c?.seq != null) since = c.seq; render(); });
  on("status", render);
  on("captions-setting", render);
  let timer = null;
  on("inbox", () => { clearTimeout(timer); timer = setTimeout(renderWalks, 300); });
  on("forecast-ready", () => setTimeout(renderWalks, 100));
  on("readonly", (v) => {
    if (v == null) {
      ro.classList.add("hidden");
      ro.innerHTML = "";
      return;
    }
    ro.classList.remove("hidden");
    ro.innerHTML = `<b>Viewing version v${esc(v)}</b><span class="small">read-only; the live model keeps running</span>
      <button id="ro-live">Back to live</button>`;
    ro.querySelector("#ro-live").addEventListener("click", backToLive);
  });
}
