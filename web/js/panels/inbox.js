// Inbox (§13.6): market events grouped by update run and then by day. Each card shows its time, source,
// a channel badge (Scraped, Data, or User), a "Synthetic" badge where it applies, the headline, and a
// status chip. Clicking a card shows its translation: highlighted spans and op chips with specificity
// badges. DECISION: a day's data releases fold into one line, so the news reads first.
import { api } from "../api.js";
import { on, store } from "../store.js";
import { esc, fmtTime, SPEC_BADGE } from "../util.js";

const STATUS_CLASS = { queued: "", received: "init", translated: "real", refined: "real", "awaiting review": "out",
                       applied: "wm", rejected: "front", deferred: "", "no translation": "" };
const CHANNEL = { scraper: ["Scraped", "ltm"], data_feed: ["Data", "butter"], user: ["User", "init"] };

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

// one wrapping line: what the translator read, as operations (the walkthrough shows each one in full)
function opChips(translation) {
  const ops = (translation?.events ?? []).flatMap((e) => e.ops ?? []);
  if (!ops.length) return `<span class="muted small">no operations</span>`;
  return `<div class="chips small"><span class="faint">${ops.length} operation${ops.length === 1 ? "" : "s"}:</span>${ops.map((o) => {
    const ends = (o.ends ?? []).map((x) => `${x.end}: ${SPEC_BADGE[x.level] ?? x.level}`).join(", ");
    return `<span class="chip op" title="${esc([o.summary, ends].filter(Boolean).join(" · "))}">${esc(String(o.op).replace(/_/g, " "))}</span>`;
  }).join("")}</div>`;
}

// routine daily releases fold; a release with its own headline (a rate decision) reads as news
const isData = (c) => String(c.id).startsWith("ME-D-");

export function initInbox({ onSelectEvent, onWalk } = {}) {
  const body = document.getElementById("inbox-body");
  const count = document.getElementById("inbox-count");
  let open = null;
  const userOpen = new Set();   // update runs the user unfolded
  const userShut = new Set();   // update runs the user folded (the newest starts unfolded)
  const dataOpen = new Set();   // days whose data releases are unfolded

  function card(c) {
    const [chan, cls] = CHANNEL[c.channel] ?? [c.source ?? "", ""];
    return `<article class="card selectable ${open === c.id ? "selected" : ""}" data-me="${esc(c.id)}" tabindex="0">
      <div class="meta"><span class="badge ${cls}">${esc(chan)}</span>${c.synthetic ? `<span class="badge">Synthetic</span>` : ""}
        <span>${c.published_at ? esc(fmtTime(c.published_at).slice(11)) : ""}</span><span class="faint">${esc(c.source ?? "")}</span>
        <span class="spacer"></span><span class="badge ${STATUS_CLASS[c.status] ?? ""}">${esc(c.status ?? "")}</span></div>
      <div class="title">${esc(c.headline)}</div>
      <div class="detail" ${open === c.id ? "" : "hidden"}></div>
    </article>`;
  }

  function render() {
    const cards = [...store.marketEvents.values()];
    count.textContent = String(cards.filter((c) => !isData(c)).length);
    if (!cards.length) {
      body.innerHTML = `<p class="empty">News and data appear here as updates collect them.<br>Press <b>Update</b> or <b>Step</b> to begin.</p>`;
      return;
    }
    const runs = new Map();
    for (const c of cards) {
      const k = c.update_id ?? "earlier";
      if (!runs.has(k)) runs.set(k, new Map());
      const day = c.day ?? String(c.published_at ?? "").slice(0, 10) ?? "";
      const days = runs.get(k);
      if (!days.has(day)) days.set(day, []);
      days.get(day).push(c);
    }
    const runKeys = [...runs.keys()].sort((a, b) => b.localeCompare(a, undefined, { numeric: true }));
    body.innerHTML = runKeys.map((rk, ri) => {
      const days = [...runs.get(rk).entries()].sort((a, b) => b[0].localeCompare(a[0]));
      const n = days.reduce((a, [, cs]) => a + cs.filter((c) => !isData(c)).length, 0);
      const u = store.updates.get(rk);
      const isOpen = userOpen.has(rk) || (ri === 0 && !userShut.has(rk));
      return `<details class="run-group" data-run="${esc(rk)}" ${isOpen ? "open" : ""}>
        <summary>${rk === "earlier" ? "Before this session" : esc(rk)}<span class="muted small" style="font-weight:400">${n} news
          ${u?.first ? ` · ${esc(u.first)}${u.last && u.last !== u.first ? ` to ${esc(u.last)}` : ""}` : ""}</span></summary>
        ${days.map(([day, cs]) => {
          const news = cs.filter((c) => !isData(c)).sort((a, b) => String(b.published_at).localeCompare(String(a.published_at)));
          const data = cs.filter(isData);
          const key = `${rk}|${day}`;
          return `<div class="day-group"><div class="day">${esc(day)}</div>
            ${news.map(card).join("")}
            ${data.length ? `<button class="ghost small" data-data="${esc(key)}">${dataOpen.has(key) ? "▾" : "▸"} ${data.length} data release${data.length === 1 ? "" : "s"}</button>
              ${dataOpen.has(key) ? data.map(card).join("") : ""}` : ""}</div>`;
        }).join("")}
      </details>`;
    }).join("");
    for (const d of body.querySelectorAll("details[data-run]")) {
      d.addEventListener("toggle", () => {
        if (d.open) { userOpen.add(d.dataset.run); userShut.delete(d.dataset.run); }
        else { userShut.add(d.dataset.run); userOpen.delete(d.dataset.run); }
      });
    }
    for (const b of body.querySelectorAll("[data-data]")) {
      b.addEventListener("click", () => {
        const k = b.dataset.data;
        if (dataOpen.has(k)) dataOpen.delete(k); else dataOpen.add(k);
        render();
      });
    }
    for (const el of body.querySelectorAll("[data-me]")) {
      const toggle = () => { open = open === el.dataset.me ? null : el.dataset.me; render(); };
      el.addEventListener("click", toggle);
      el.addEventListener("keydown", (ev) => { if (ev.key === "Enter") toggle(); });
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
      <div class="small" style="margin:6px 0">${highlightSpans(text, translation?.spans)}</div>
      <div>${opChips(translation)}</div>
      ${translation?.rationale ? `<details class="more"><summary>how it was read</summary><div class="small muted">${esc(translation.rationale)}</div></details>` : ""}
      ${event?.url ? `<div class="small faint mono" style="margin-top:4px;overflow-wrap:anywhere">${esc(event.url)}</div>` : ""}
      ${onWalk && store.traces.some((e) => e.scope === id) ? `<div class="ask-row" style="margin-top:6px">
        <button class="primary small" data-walk="${esc(id)}" title="Step through what the model did with this news (W)">Walk through ▸</button>
        <span class="small faint">news → fuzzy ops → real edges → the graph</span></div>` : ""}`;
    holder.querySelector("[data-walk]")?.addEventListener("click", (ev) => { ev.stopPropagation(); onWalk(id); });
    holder.addEventListener("click", (ev) => ev.stopPropagation());
    onSelectEvent?.(id);
  }

  let timer = null;
  const later = () => { clearTimeout(timer); timer = setTimeout(render, 120); };
  on("inbox", later);
  on("flash-inbox", (id) => {
    const el = body.querySelector(`[data-me="${CSS.escape(String(id))}"]`);
    if (el) { el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash"); }
  });
  render();
  return { render };
}
