// Import (Oct 11): how new information reaches a client's world model. A bundle is research a collection agent has
// already read and categorized (intake/bundle.py): dated items, each with its source, summary, the entities it is
// about, a category, and the changes it claims. The dialog shows the bundle as a dated timeline, says what each item
// would change (and what it cannot map), and imports the chosen items: each is folded in on its own date and waits
// for review, in date order. Bundles come from a file on the person's computer, or from the server's imports folder
// when it has one (a local checkout).
import { api } from "../api.js";
import { store } from "../store.js";
import { errorText, esc } from "../util.js";

const SOURCE = { broker_research: "Broker research", expert_call: "Expert call", news: "News", central_bank: "Central bank",
                 data: "Data", filing: "Filing", client_model: "Client model", other: "Other" };
const CHANGE = { observe_value: "level", change_value: "move", add_interaction: "new link", reweight_interaction: "evidence" };

export function initImport({ toast, onProposal }) {
  const pane = document.createElement("section");
  pane.id = "import";
  pane.className = "examples import hidden";
  pane.setAttribute("role", "dialog");
  pane.setAttribute("aria-label", "Import research");
  document.getElementById("stage").appendChild(pane);
  const st = { bundle: null, preview: null, local: [], picked: new Set(), open: null, busy: false, filter: "all", error: null };

  const day = (iso) => new Date(iso).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
  const clock = (iso) => new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });

  async function use(bundle) {
    st.error = null;
    try {
      st.preview = await api.importPreview(bundle);
      st.bundle = bundle;
      st.picked = new Set(st.preview.items.filter((x) => x.status !== "imported" && x.changes > 0).map((x) => x.id));
      st.open = null;
    } catch (err) { st.error = errorText(err); }
    render();
  }

  async function readFile(file) {
    try { await use(JSON.parse(await file.text())); } catch (err) { st.error = `${file.name}: ${errorText(err)}`; render(); }
  }

  function chooser() {
    return `<div class="imp-src">
      <label class="primary small imp-file">Choose a bundle…<input type="file" accept=".json,application/json" hidden></label>
      ${st.local.map((b) => `<button class="small" data-local="${esc(b.name)}" title="${esc(b.collected_by)}">${esc(b.title)} <span class="muted">· ${b.items}</span></button>`).join("")}
      <span class="muted small">${st.local.length ? "or one from this server's imports folder" : "a JSON bundle from your research agent"}</span>
    </div>`;
  }

  function row(x) {
    const off = x.status === "imported" || x.changes === 0;
    const kinds = x.change_kinds.map((k) => CHANGE[k] ?? k).join(", ");
    return `<li class="imp-row ${esc(x.status)}${st.open === x.id ? " open" : ""}" data-id="${esc(x.id)}">
      <div class="imp-line">
        <input type="checkbox" data-pick="${esc(x.id)}" ${st.picked.has(x.id) ? "checked" : ""} ${off || st.busy ? "disabled" : ""}
          aria-label="Import ${esc(x.headline)}">
        <span class="imp-time mono muted">${clock(x.published_at)}</span>
        <button class="et linkish" data-toggle="${esc(x.id)}" aria-expanded="${st.open === x.id}">${esc(x.headline)}</button>
        ${x.category ? `<span class="imp-cat">${esc(x.category)}</span>` : ""}
        <span class="imp-n small" title="${esc(kinds)}">${x.changes ? `${x.changes} change${x.changes === 1 ? "" : "s"}` : "nothing to map"}</span>
        ${x.status === "imported" ? `<span class="edone" title="Already imported">✓</span>` : x.status === "late" ? `<span class="imp-late small" title="Older than the model's last processed day: folded in late">late</span>` : ""}
      </div>
      <div class="imp-meta small muted">${esc(SOURCE[x.source_type] ?? x.source_type)} · ${esc(x.source)}${x.stance ? ` · ${esc(x.stance)}` : ""}
        <span class="imp-rel" title="Relevance to the book, as the agent judged it"><i style="width:${Math.round(100 * x.relevance)}%"></i></span></div>
      ${st.open === x.id ? `<div class="emore small">
        ${x.summary ? `<blockquote class="earticle"><div>${esc(x.summary)}</div><div class="esrc muted">${esc(x.source)} · ${day(x.published_at)} ${clock(x.published_at)} UTC</div></blockquote>` : ""}
        <div class="imp-tags">${x.entities.map((e) => `<span class="cchip">${esc(e)}</span>`).join("")}${x.tickers.map((t) => `<span class="cchip mono">${esc(t)}</span>`).join("")}</div>
        <p>${x.changes ? `Would propose ${esc(kinds)} (${x.changes}) for your review.` : "Nothing in it maps onto this model."}
          The agent's confidence in its reading: ${Math.round(100 * x.confidence)}%.</p>
        ${x.dropped.length ? `<p class="muted">Not mapped: ${x.dropped.map(esc).join("; ")}.</p>` : ""}
      </div>` : ""}
    </li>`;
  }

  function render() {
    const p = st.preview;
    const cats = p ? [...new Set(p.items.map((x) => x.category).filter(Boolean))] : [];
    const shown = p ? p.items.filter((x) => st.filter === "all" || x.category === st.filter) : [];
    const days = [];
    for (const x of shown) {
      const d = x.published_at.slice(0, 10);
      if (!days.length || days[days.length - 1].d !== d) days.push({ d, items: [] });
      days[days.length - 1].items.push(x);
    }
    const n = st.picked.size;
    pane.innerHTML = `
      <header><div class="etitle">Import</div><span class="spacer"></span>
        <button class="ghost win-max-btn" data-max type="button" aria-label="Full screen" title="Full screen (or back)">⤢</button><button class="close" aria-label="Close (Esc)">✕</button></header>
      <p class="small muted elede">Research your agent has collected and categorized. Each item is folded in on its own date, and nothing changes
        your model until you approve it.</p>
      ${chooser()}
      ${st.error ? `<p class="error small">${esc(st.error)}</p>` : ""}
      ${p ? `<div class="imp-head small">
          <b>${esc(p.title)}</b> · ${esc(p.collected_by)}${p.collected_at ? ` · collected ${day(p.collected_at)}` : ""} · ${p.items.length} items
          <span class="muted">· your model is at ${day(p.model_date)}</span>
          ${p.description ? `<div class="muted">${esc(p.description)}</div>` : ""}</div>
        <div class="chips efilter" role="group" aria-label="Show">${[["all", "All"], ...cats.map((c) => [c, c])].map(([k, l]) =>
          `<button class="cchip" data-filter="${esc(k)}" aria-pressed="${st.filter === k}">${esc(l)}</button>`).join("")}
          <span class="spacer"></span><button class="ghost small" data-all>Select all</button><button class="ghost small" data-none>None</button></div>
        <div class="imp-list">${days.map((g) => `<h4 class="imp-day">${day(g.d + "T12:00:00Z")}</h4><ol class="elist">${g.items.map(row).join("")}</ol>`).join("")}</div>
        <footer class="imp-foot"><span class="muted small">${n ? `${n} item${n === 1 ? "" : "s"}, reviewed one by one in date order` : "Pick the items to import"}</span>
          <span class="spacer"></span><button class="primary" data-go ${n && !st.busy ? "" : "disabled"}>${st.busy ? "Importing…" : `Import ${n || ""}`}</button></footer>` : ""}`;
  }

  pane.addEventListener("change", (ev) => {
    const f = ev.target.closest?.(".imp-file input");
    if (f?.files?.[0]) { readFile(f.files[0]); return; }
    const box = ev.target.closest?.("[data-pick]");
    if (box) { box.checked ? st.picked.add(box.dataset.pick) : st.picked.delete(box.dataset.pick); render(); }
  });
  pane.addEventListener("click", async (ev) => {
    const t = ev.target.closest?.("button");
    if (!t) return;
    if (t.classList.contains("close")) return close();
    if (t.dataset.max != null) { pane.classList.toggle("win-max"); return; }
    if (t.dataset.toggle) { st.open = st.open === t.dataset.toggle ? null : t.dataset.toggle; render(); return; }
    if (t.dataset.filter) { st.filter = t.dataset.filter; render(); return; }
    if (t.dataset.local) {
      try { await use(await api.importLocal(t.dataset.local)); } catch (err) { st.error = errorText(err); render(); }
      return;
    }
    const usable = (st.preview?.items ?? []).filter((x) => x.status !== "imported" && x.changes > 0
      && (st.filter === "all" || x.category === st.filter));
    if (t.dataset.all != null) { usable.forEach((x) => st.picked.add(x.id)); render(); return; }
    if (t.dataset.none != null) { st.picked.clear(); render(); return; }
    if (t.dataset.go != null) {
      st.busy = true; render();
      try {
        const res = await api.importRun(st.bundle, [...st.picked]);
        toast(`Imported ${res.imported.length} item${res.imported.length === 1 ? "" : "s"}: each waits for your review, oldest first.`);
        close();
        if (res.waiting_on) onProposal?.(res.waiting_on);
      } catch (err) { st.error = errorText(err); }
      st.busy = false;
      if (!pane.classList.contains("hidden")) render();
    }
  });

  async function open() {
    pane.classList.remove("hidden");
    document.getElementById("btn-import")?.setAttribute("aria-expanded", "true");
    try { st.local = await api.importLocalList(); } catch { st.local = []; }
    if (st.bundle) await use(st.bundle);       // what is already imported may have changed
    else render();
  }
  function close() {
    pane.classList.add("hidden");
    document.getElementById("btn-import")?.setAttribute("aria-expanded", "false");
  }
  const isOpen = () => !pane.classList.contains("hidden");
  return { open, close, isOpen, toggle: () => (isOpen() ? close() : open()), ready: () => !!store.status?.imports };
}
