// The demo menu (top bar, beside the name): Small demo, Production demo, Full demo, Emily's demo. Choosing one switches
// this login's engine on the server (POST /api/demos/{id}); a demo opened before comes back as it was left, and one
// opened for the first time is built while the current one keeps working, with its progress shown here. Once it swaps
// in, every page on this engine reloads (the stream's "switched" message), so nothing of the old demo carries over.
import { api } from "../api.js";
import { esc } from "../util.js";

const PHASES = {
  starting: "Starting",
  world: "Generating the synthetic world and its history",
  replay: "Replaying three years of synthetic history",
  session: "Copying the history into a new session",
  ready: "Opening it",
};
const AFTER = "axelrod.afterSwitch";      // what to open once the page has reloaded into the new demo (this tab only)

export function initDemos({ toast }) {
  const btn = document.querySelector("#btn-demo");
  const panel = document.querySelector("#demo-panel");
  const prog = document.querySelector("#demo-progress");
  let listing = null;
  let polling = null;

  const label = (id) => listing?.demos.find((d) => d.id === id)?.label ?? id;
  const setOpen = (open) => {
    panel.hidden = !open;
    btn.setAttribute("aria-expanded", String(open));
    if (open) panel.querySelector("[aria-current='true'], button")?.focus();
  };

  function render() {
    if (!listing) return;
    btn.querySelector(".lbl").textContent = label(listing.current);
    panel.innerHTML = listing.demos.map((d) => `
      <button class="tool demo-item" role="menuitemradio" aria-checked="${d.current}" data-demo="${esc(d.id)}" ${d.current ? 'aria-current="true"' : ""}>
        <span class="tick" aria-hidden="true">${d.current ? "✓" : ""}</span>
        <span class="txt"><b>${esc(d.label)}</b><span class="small muted">${esc(d.note)}</span>
          ${d.cold ? '<span class="small cold">First open replays its history: a few minutes</span>' : ""}</span>
      </button>`).join("");
    for (const b of panel.querySelectorAll("[data-demo]")) b.addEventListener("click", () => choose(b.dataset.demo));
  }

  async function refresh() {
    try { listing = await api.demos(); } catch { return null; }
    render();
    return listing;
  }

  function showProgress(sw) {
    if (!sw) { prog.classList.add("hidden"); return; }
    prog.classList.remove("hidden");
    const name = label(sw.demo);
    if (sw.phase === "error") {
      prog.innerHTML = `<div class="hd"><b>Could not open ${esc(name)}</b>
        <button class="ghost small" data-x aria-label="Close">✕</button></div><p class="small">${esc(sw.error ?? "")}</p>`;
      prog.querySelector("[data-x]").addEventListener("click", () => prog.classList.add("hidden"));
      return;
    }
    const frac = sw.fraction ?? (sw.phase === "session" ? 1 : sw.phase === "ready" ? 1 : null);
    const days = sw.days ? ` (day ${sw.days[0].toLocaleString()} of ${sw.days[1].toLocaleString()})` : "";
    const slow = sw.phase === "replay" || (sw.phase === "world" && sw.elapsed_s > 4);
    prog.innerHTML = `<div class="hd"><b>Opening ${esc(name)}</b><span class="mono small muted">${Math.round(sw.elapsed_s ?? 0)}s</span></div>
      <div class="small">${esc(PHASES[sw.phase] ?? sw.phase)}${esc(days)}</div>
      <div class="bar ${frac == null ? "indet" : ""}"><i style="width:${frac == null ? 30 : Math.round(frac * 100)}%"></i></div>
      ${slow ? '<p class="small muted">The first open builds its history once and caches it; later opens take seconds. The current demo keeps working meanwhile.</p>' : ""}`;
  }

  // poll the switch until the engine serves the chosen demo, then reload into it
  function follow(id) {
    clearInterval(polling);
    polling = setInterval(async () => {
      const out = await refresh();
      if (!out) return;
      if (out.current === id && !out.switching) { clearInterval(polling); reload(); return; }
      showProgress(out.switching);
      if (out.switching?.phase === "error") clearInterval(polling);
    }, 500);
  }

  let reloading = false;
  function reload() {
    if (reloading) return;
    reloading = true;
    document.body.classList.add("switching-out");
    setTimeout(() => location.reload(), 180);
  }

  // switch to a demo; `after` ("examples") is opened once the new demo's page has loaded
  async function choose(id, { after = null } = {}) {
    setOpen(false);
    if (listing && id === listing.current && !after) return;
    try { if (after) sessionStorage.setItem(AFTER, after); } catch { /* still switches */ }
    try {
      const out = await api.switchDemo(id);
      listing = out;
      render();
      if (out.current === id && !out.switching) { reload(); return; }
      showProgress(out.switching);
      follow(id);
    } catch (err) {
      toast(`Could not switch demos: ${err.message}`, "err");
    }
  }

  btn.addEventListener("click", (ev) => { ev.stopPropagation(); if (panel.hidden) refresh(); setOpen(panel.hidden); });
  document.addEventListener("click", (ev) => { if (!panel.hidden && !ev.target.closest(".demo-wrap")) setOpen(false); });
  panel.addEventListener("keydown", (ev) => {
    const items = [...panel.querySelectorAll("button")];
    const i = items.indexOf(document.activeElement);
    if (ev.key === "ArrowDown") { ev.preventDefault(); items[(i + 1) % items.length]?.focus(); }
    else if (ev.key === "ArrowUp") { ev.preventDefault(); items[(i - 1 + items.length) % items.length]?.focus(); }
    else if (ev.key === "Escape") { ev.stopPropagation(); setOpen(false); btn.focus(); }
  });

  // a switch already under way (another tab started it, or this page reloaded mid-way) is followed too
  refresh().then((out) => { if (out?.switching && out.switching.phase !== "error") { showProgress(out.switching); follow(out.switching.demo); } });

  const takeAfter = () => {
    try { const a = sessionStorage.getItem(AFTER); sessionStorage.removeItem(AFTER); return a; } catch { return null; }
  };
  return {
    choose,
    reload,
    takeAfter,
    isOpen: () => !panel.hidden,
    close: () => setOpen(false),
    current: () => listing?.current,
  };
}
