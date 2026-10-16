// Agent context (Oct 15): the world model as the context layer for a client's agents. A client's agents (a decision
// engine, a disruption-propagation agent, an execution and monetization agent) load a world model before they reason:
// a domain pack (companies, clusters, edges, transmission paths) and a dated baseline, in the client's v4.1.4 format.
// GET /api/context/v4 exports ours in that format, with a forecast's decision context when one is open. The dialog
// shows the card an agent fills from it (the Decision Engine's "Scenarios & conviction") beside the context itself, and
// which part of the context each of the agents' cards reads; Download saves the whole pack as one JSON file. Opened
// without a forecast (Learn, ☰ › Export the world model), it exports the world model as it stands: the pack and baseline.
// The context grounds the agent's judgment and never concludes it: no ratings, no sizing.
import { api } from "../api.js";
import { names as nameIndex } from "../names.js";
import { emit, on } from "../store.js";
import { errorText, esc, fmt } from "../util.js";

const BAND_TEXT = { Bull: "the best quarter of the draws for the book", Base: "the middle half", Bear: "the worst quarter" };

// a move in its own units: percent for prices and profits, a change for rates
export function moveText(m) {
  if (!m) return "";
  if (m.pct != null) return `${m.pct > 0 ? "+" : ""}${fmt(m.pct, Math.abs(m.pct) < 10 ? 1 : 0)}%`;
  if (m.change != null) {
    const pp = /%|pct|percent/i.test(m.unit ?? "");
    return `${m.change > 0 ? "+" : ""}${pp ? fmt(m.change * 100, 0) : fmt(m.change)}${pp ? " bp" : ` ${m.unit ?? ""}`}`;
  }
  return `${m.sd > 0 ? "+" : ""}${fmt(m.sd)} sd`;
}
const cls = (v) => (v > 0.005 ? "z-up" : v < -0.005 ? "z-down" : "faint");
const names = (list) => (list ?? []).map((x) => `${esc(x.name)} <span class="mono ${cls(x.sd)}">${esc(moveText(x))}</span>`).join(", ");

// the scenario table: bull, base, and bear bands of the forecast's draws, read for the book
export function scenarioTableHtml(t, { compact = false } = {}) {
  if (!t?.rows?.length) return "";
  const lean = t.p_book_up - t.p_book_down;
  const verdict = Math.abs(lean) < 0.1 ? "No clear lean for the book" : lean > 0 ? "The book leans up" : "The book leans down";
  const change = t.changes_the_read;
  return `<div class="scen-table">
    <div class="scen-verdict"><b>${verdict}.</b> <span class="muted">Up in ${fmt(t.p_book_up * 100, 0)}% of draws, down in
      ${fmt(t.p_book_down * 100, 0)}%, at day ${t.horizon_days}, across ${t.book.length} names.</span></div>
    <table class="scen small"><thead><tr><th>Scenario</th><th title="The band's share of the draws">Prob.</th>
      <th title="Median average move of the book in the band, in sd">Book</th><th>Favored</th><th>Hurt</th>
      ${compact ? "" : "<th>Primary driver (mechanism)</th>"}</tr></thead><tbody>
      ${t.rows.map((r) => `<tr class="band-${r.band.toLowerCase()}"><td title="${esc(BAND_TEXT[r.band] ?? "")}"><b>${esc(r.band)}</b></td>
        <td class="mono" data-label="Prob.">${fmt(r.probability * 100, 0)}%</td>
        <td class="mono nowrap ${cls(r.book_move ?? 0)}" data-label="Book">${r.book_move > 0 ? "+" : ""}${fmt(r.book_move ?? 0)} sd</td>
        <td data-label="Favored">${names(r.favored) || `<span class="faint">none</span>`}</td><td data-label="Hurt">${names(r.hurt) || `<span class="faint">none</span>`}</td>
        ${compact ? "" : `<td data-label="Mechanism">${(r.mechanism ?? []).map((m) => `${esc(m.name)} <span class="mono ${cls(m.sd)}">${esc(moveText(m))}</span>`).join("; ")}</td>`}</tr>`).join("")}
    </tbody></table>
    ${change ? `<div class="small"><b>What would change the read:</b> ${esc(change.text)}${change.kind === "hypothesis"
      ? ` <span class="faint">(${esc(change.id)}, ${fmt(change.probability * 100, 0)}% likely now)</span>` : ""}</div>` : ""}
    ${(t.rival_scenarios ?? []).length ? `<div class="small muted">Rival scenarios in memory: ${t.rival_scenarios.map((s) => `${esc(s.name)} ${fmt(s.weight * 100, 0)}%`).join(", ")}.</div>` : ""}
  </div>`;
}

const PARTS = [["manifest", "Manifest"], ["domain_pack", "Domain pack"], ["baseline", "Baseline"], ["forecast", "Decision context"]];

function partSummary(key, v) {
  if (!v) return "";
  if (key === "manifest") {
    return `<ol class="small ctx-load">${v.load_order.map((f) => `<li><span class="mono">${esc(f.file)}</span> <span class="muted">${esc(f.source)}</span></li>`).join("")}</ol>`;
  }
  if (key === "domain_pack") {
    const counts = ["companies", "clusters", "cluster_memberships", "company_edge_relationships", "transmission_paths",
                    "cross_validation_assertions", "industry_caveat_definitions"].map((k) => `${(v[k] ?? []).length} ${k.replaceAll("_", " ")}`);
    const e = v.company_edge_relationships?.[0];
    return `<div class="small muted">${counts.join(" · ")}</div>
      ${e ? `<div class="small" style="margin-top:6px">An edge as the agents read it: <b>${esc(nameIndex().value?.(e.source_metric) ?? e.source_metric)}</b> ${esc(e.mechanism_label)}
        <b>${esc(nameIndex().value?.(e.affected_metrics[0]) ?? e.affected_metrics[0])}</b>: ${esc(e.direction)}, ${esc(e.confidence_prior)} confidence, ${esc(e.time_horizon)}.
        <span class="muted">Ours adds the size (${fmt(e.axelrod.effect_sd_per_sd)} sd per sd), the chance the link exists
        (${fmt(e.axelrod.existence_p * 100, 0)}%), and its evidence (${e.axelrod.evidence_count}).</span></div>` : ""}`;
  }
  if (key === "baseline") {
    return `<div class="small muted">As of ${esc(String(v.as_of).slice(0, 10))} · version ${v.state_version} · ${v.values.length} values ·
      ${v.unresolved_questions.length} open questions from the hypothesis frontier</div>`;
  }
  return `<div class="small muted">${esc(v.question)} · ${v.targets.length} targets · ${v.transmission.length} transmission steps ·
    ${v.key_interactions.length} key interactions · the scenario table · based on version ${v.based_on_version}</div>`;
}

// the world model on its own (Oct 15, the Learn side's export): what the agents receive, at a glance
function modelCardHtml(p) {
  const pack = p.domain_pack;
  const base = p.baseline;
  const nm = nameIndex();
  const label = (id) => nm.value?.(id) ?? id;
  const edges = [...pack.company_edge_relationships]
    .sort((a, b) => Math.abs(b.axelrod.effect_sd_per_sd) * b.axelrod.existence_p - Math.abs(a.axelrod.effect_sd_per_sd) * a.axelrod.existence_p)
    .slice(0, 6);
  const counts = [["companies", pack.companies.length], ["clusters", pack.clusters.length],
                  ["relationships", pack.company_edge_relationships.length], ["transmission paths", pack.transmission_paths.length],
                  ["values in the baseline", base.values.length], ["open questions", base.unresolved_questions.length]];
  return `<div class="group-label">The world model, as it stands</div>
    <div class="ctx-q">As of ${esc(String(base.as_of).slice(0, 10))} · version ${base.state_version}</div>
    <div class="small muted">State hash <span class="mono">${esc(String(base.state_hash ?? "").slice(0, 12))}</span>: an agent can tell which
      committed version its context came from, and the same version always exports the same pack.</div>
    <div class="ctx-counts small">${counts.map(([k, n]) => `<span><b>${n}</b> ${esc(k)}</span>`).join("")}</div>
    <div class="group-label" style="margin-top:10px">Strongest relationships</div>
    <ul class="small ctx-feeds">${edges.map((e) => `<li>${esc(label(e.source_metric))} <i class="via">${esc(e.mechanism_label)}</i>
      ${esc(label(e.affected_metrics[0]))} <span class="muted">· ${esc(e.direction)}, ${esc(e.confidence_prior)} confidence,
      ${e.axelrod.effect_sd_per_sd > 0 ? "+" : ""}${fmt(e.axelrod.effect_sd_per_sd)} sd per sd</span></li>`).join("")}</ul>
    ${base.unresolved_questions.length ? `<div class="group-label" style="margin-top:10px">Open questions it passes on</div>
      <ul class="small ctx-feeds">${base.unresolved_questions.slice(0, 3).map((q) => `<li>${esc(q.question)} <span class="faint">(${fmt(q.probability * 100, 0)}%)</span></li>`).join("")}</ul>` : ""}`;
}

export function initContext() {
  const pane = document.createElement("section");
  pane.id = "context";
  pane.className = "examples context hidden";
  pane.setAttribute("role", "dialog");
  pane.setAttribute("aria-label", "Agent context");
  document.getElementById("stage").appendChild(pane);
  const st = { forecast: null, pack: null, part: "domain_pack", error: null, busy: false };

  function render() {
    const p = st.pack;
    const fc = p?.forecast;
    pane.innerHTML = `
      <header><div class="etitle">${st.forecast ? "Agent context" : "World model export"}</div><span class="spacer"></span>
        <button class="small ghost" data-files ${p ? "" : "disabled"} title="Each part as its own file, named as the agents' load order expects">As files</button>
        <button class="small" data-download ${p ? "" : "disabled"} title="The whole context pack as one JSON file">Download</button>
        <button class="ghost win-max-btn" data-max type="button" aria-label="Full screen" title="Full screen (or back)">⤢</button><button class="close" aria-label="Close (Esc)">✕</button></header>
      <p class="small muted elede">${st.forecast ? `The world model is the context layer for the agents. This is it in the agents' own world-model format
        (v4.1.4): a domain pack and a dated baseline, and the forecast's decision context.` : `The world model as it stands now on the learning
        side, in the agents' own world-model format (v4.1.4): the domain pack and the dated baseline, at the latest committed version.
        Export it again after new research is approved, and the agents read the updated model.`} The agents read it before they reason;
        it grounds their judgment and never concludes it.</p>
      ${st.error ? `<p class="error small">${esc(st.error)}</p>` : ""}
      ${st.busy ? `<p class="small muted elede">Building the context…</p>` : ""}
      ${p ? `<div class="ctx-cols">
        <div class="ctx-card">
          ${fc ? `<div class="group-label">Decision Engine · 5 · Scenarios &amp; conviction</div><div class="ctx-q">${esc(fc.question)}</div>${scenarioTableHtml(fc.scenario_table)}
            <p class="small muted">What the agent writes beside it (its judgment, not the model's): the conviction, and what the stock is pricing.</p>`
            : modelCardHtml(p)}
          <div class="group-label" style="margin-top:12px">Which part each card reads</div>
          <ul class="small ctx-feeds">${p.manifest.feeds.filter((f) => fc || f.reads.some((r) => !r.startsWith("forecast."))).map((f) => `<li><b>${esc(f.agent)}</b> · ${esc(f.card)}: <span class="mono muted">${f.reads.map(esc).join(", ")}</span></li>`).join("")}</ul>
        </div>
        <div class="ctx-pack">
          <div class="seg" role="tablist" aria-label="Context part">${PARTS.filter(([k]) => p[k]).map(([k, l]) =>
            `<button role="tab" data-part="${k}" aria-pressed="${st.part === k}">${l}</button>`).join("")}</div>
          ${partSummary(st.part, p[st.part])}
          <details class="ctx-json"><summary class="small faint">The JSON</summary><pre class="mono small">${esc(JSON.stringify(p[st.part], null, 1))}</pre></details>
        </div></div>` : ""}`;
  }

  pane.addEventListener("click", (ev) => {
    const t = ev.target.closest?.("button");
    if (!t) return;
    if (t.classList.contains("close")) return close();
    if (t.dataset.max != null) { pane.classList.toggle("win-max"); return; }
    if (t.dataset.part) { st.part = t.dataset.part; render(); return; }
    if (t.dataset.download != null && st.pack) {
      const b = st.pack.baseline;
      save(`${st.pack.domain_pack.domain_pack_id}_${String(b.as_of).slice(0, 10)}_v${b.state_version}${st.forecast ? `_${st.forecast}` : ""}.context.json`, st.pack);
    }
    // each part under the file name the manifest's load order gives it, so the files drop into the agents' folder as is
    if (t.dataset.files != null && st.pack) {
      const files = st.pack.manifest.load_order.filter((f) => f.source.startsWith("this export"));
      const partOf = (f) => (f.source.includes("domain_pack") ? "domain_pack" : f.source.includes("baseline") ? "baseline" : "forecast");
      files.forEach((f, i) => setTimeout(() => save(f.file.endsWith(".json") ? f.file : `${f.file}.json`, st.pack[partOf(f)]), 250 * i));
      setTimeout(() => save("axelrod_manifest.json", st.pack.manifest), 250 * files.length);
    }
  });

  function save(name, obj) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(obj, null, 1)], { type: "application/json" }));
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  async function open(forecastId = null) {
    st.forecast = forecastId;
    st.error = null;
    st.busy = true;
    st.pack = null;
    st.part = forecastId ? "forecast" : "domain_pack";
    pane.classList.remove("hidden");
    render();
    try { st.pack = await api.contextV4(forecastId); } catch (err) { st.error = errorText(err); }
    st.busy = false;
    render();
  }
  function close() { pane.classList.add("hidden"); emit("context-closed"); }
  const isOpen = () => !pane.classList.contains("hidden");
  on("open-context", (id) => open(id));
  return { open, close, isOpen };
}
