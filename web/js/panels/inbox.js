// Inbox (§13.6): one card per market event with time, source, headline, a "Synthetic" badge, and a
// status chip. Clicking a card shows its translation: highlighted spans and op chips with specificity badges.
import { api } from "../api.js";
import { on, store } from "../store.js";
import { esc, fmtTime, SPEC_BADGE } from "../util.js";

const STATUS_CLASS = { received: "init", translated: "real", "awaiting review": "out", applied: "wm",
                       rejected: "front", deferred: "", "no translation": "" };

function highlightSpans(text, spans) {
  if (!spans?.length) return esc(text);
  const sorted = [...spans].filter((s) => Array.isArray(s) || s.start != null)
    .map((s) => (Array.isArray(s) ? { start: s[0], end: s[1] } : s)).sort((a, b) => a.start - b.start);
  let out = "";
  let i = 0;
  for (const s of sorted) {
    if (s.start < i) continue;
    out += esc(text.slice(i, s.start));
    out += `<span class="span-hl">${esc(text.slice(s.start, s.end))}</span>`;
    i = s.end;
  }
  return out + esc(text.slice(i));
}

function opChips(translation) {
  const parts = [];
  for (const e of translation?.events ?? []) {
    for (const o of e.ops ?? []) {
      const ends = (o.ends ?? []).map((x) => `<span class="badge spec-${x.level}" title="${esc(x.end)}: ${esc(x.ref)}">
        ${esc(x.end)} · ${SPEC_BADGE[x.level] ?? x.level}</span>`).join(" ");
      parts.push(`<div style="margin:3px 0"><span class="chip op">${esc(o.op)}</span> <span class="small">${esc(o.summary)}</span>
        <div>${ends}</div></div>`);
    }
  }
  return parts.join("") || `<span class="muted small">no ops</span>`;
}

export function initInbox({ onSelectEvent } = {}) {
  const body = document.getElementById("inbox-body");
  const count = document.getElementById("inbox-count");
  let open = null;

  function render() {
    const cards = [...store.marketEvents.values()].sort((a, b) => String(b.published_at).localeCompare(String(a.published_at)));
    count.textContent = String(cards.filter((c) => !String(c.id).startsWith("ME-D-")).length);
    if (!cards.length) {
      body.innerHTML = `<p class="muted small">Market events appear here as the scenario runs.</p>`;
      return;
    }
    // data releases are bundled; news and filings get their own cards
    body.innerHTML = cards.slice(0, 80).map((c) => `
      <article class="card selectable ${open === c.id ? "selected" : ""}" data-me="${esc(c.id)}" tabindex="0">
        <div class="meta"><span class="mono">${esc(c.id)}</span><span>${fmtTime(c.published_at)}</span>
          <span>${esc(c.source ?? "")}</span>${c.synthetic ? `<span class="badge">Synthetic</span>` : ""}
          <span class="spacer"></span><span class="badge ${STATUS_CLASS[c.status] ?? ""}">${esc(c.status)}</span></div>
        <div class="title">${esc(c.headline)}</div>
        <div class="detail" ${open === c.id ? "" : "hidden"}></div>
      </article>`).join("");
    for (const card of body.querySelectorAll("[data-me]")) {
      const toggle = () => { open = open === card.dataset.me ? null : card.dataset.me; render(); if (open) loadDetail(open); };
      card.addEventListener("click", toggle);
      card.addEventListener("keydown", (ev) => { if (ev.key === "Enter") toggle(); });
    }
    if (open) loadDetail(open);
  }

  async function loadDetail(id) {
    const holder = body.querySelector(`[data-me="${CSS.escape(id)}"] .detail`);
    if (!holder) return;
    const cached = store.marketEvents.get(id);
    let translation = cached?.translation;
    let event = null;
    try {
      const r = await api.marketEvent(id);
      event = r.event;
      translation = r.translation ?? translation;
    } catch { /* keep what the trace gave us */ }
    // spans index into "headline body"
    const text = event ? `${event.headline} ${event.body ?? ""}`.trim() : cached?.headline ?? "";
    holder.innerHTML = `
      <div class="small" style="margin:4px 0">${highlightSpans(text, translation?.spans)}</div>
      ${translation?.rationale ? `<div class="small muted">${esc(translation.rationale)}</div>` : ""}
      <div>${opChips(translation)}</div>`;
    onSelectEvent?.(id);
  }

  on("inbox", render);
  on("flash-inbox", (id) => {
    const el = body.querySelector(`[data-me="${CSS.escape(String(id))}"]`);
    if (el) { el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash"); }
  });
  render();
}
