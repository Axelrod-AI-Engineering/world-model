// The hypothesis frontier (§13.6): hypotheses about the presence or absence of interactions and the proposed
// decisions of entities, sorted by current informational value, with a decay sparkline, a kind badge, and the
// probability. Decision hypotheses have "Pose as thesis"; all have "Mark supported" and "Mark refuted".
// DECISION (addition): the frontier filters by kind, and every hypothesis can show the data that bears on it:
// where its probability comes from, the subentity series it reads, the co-movement or the interaction's
// evidence behind it, an entity memory's decision record, and the news and data that touched it.
import { api } from "../api.js";
import { scatter } from "../charts/fan.js";
import { sparkline } from "../charts/sparkline.js";
import { names } from "../names.js";
import { emit, on } from "../store.js";
import { errorText, esc, fmt, signed } from "../util.js";

// DECISION (low friction without clutter): each hypothesis is one line (statement, p, informational value)
// that opens in place to its decay, its data, and its actions; the frontier shows the top 10 and grows 15 at a time.
const FIRST = 10;
const MORE = 15;
const KIND_NAME = { interaction_present: "interaction present", interaction_absent: "interaction absent",
                    entity_decision: "entity decision", comovement: "co-movement" };
const FILTERS = [["all", "All"], ["entity_decision", "Entity decisions"], ["interaction_present", "Interactions present"],
                 ["interaction_absent", "Interactions absent"], ["comovement", "Co-movements"]];
const BASIS = {
  "correlation frontier": "the correlation frontier's support for the co-movement",
  "interaction existence": "the interaction's existence belief",
  "entity memory": "the entity memory's record of the actor's past decisions in this context",
  prior: "its starting belief: no data has bound it yet",
};
const kindOf = (h) => (h.comovement_id ? "comovement" : h.kind);
const day = (iso) => (iso ? new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }) : "");

// "inflation.headline_cpi>+0.75&…" → "Headline CPI (% y/y) above +0.75 sd"
function contextText(bucket, nm) {
  if (!bucket || bucket === "neutral") return "neutral: no driver beyond ±0.75 sd";
  return bucket.split("&").map((part) => {
    const m = /^(.+)>([+-])([\d.]+)$/.exec(part);
    return m ? `${nm.value(m[1])} ${m[2] === "+" ? "above +" : "below −"}${m[3]} sd` : part;
  }).join(" and ");
}

function evidenceHtml(ev, nm) {
  const unit = (sid) => nm.subs.get(sid)?.unit ?? "";
  const co = ev.comovement;
  const it = ev.interaction;
  const d = ev.decision;
  const parts = [`<div class="small"><b>p comes from</b> ${esc(BASIS[ev.basis] ?? ev.basis)}.</div>`];
  if (co) {
    parts.push(`<div class="small muted">${(nm.valueHtml(co.earlier))} → ${(nm.valueHtml(co.later))}, ${co.lag_days} days later,
      ${co.sign > 0 ? "same" : "opposite"} direction · support ${fmt(co.support)} · ${co.consistent + co.inconsistent
      ? `${co.consistent} of ${co.consistent + co.inconsistent} spaced checks consistent` : "no spaced checks yet"} · correlation ${fmt(co.corr)} · ${esc(String(co.status).replace(/_/g, " "))}</div><div class="ev-scatter"></div>`);
  }
  if (it) {
    parts.push(`<div class="small muted">${esc(nm.link(it.id) ?? it.id)} (${esc(it.label)}): effect ${signed(it.effect)} sd per sd
      (± ${fmt(it.effect_sd)} sd per sd) · existence ${fmt(it.existence)}</div>
      ${it.evidence.length ? `<div class="ev-list">${it.evidence.map((e) => `<div class="small"><span class="faint mono">${esc(day(e.observed_at))}</span>
        <span class="badge">${esc(e.source_type)}</span> ${esc(e.excerpt ?? "")} <span class="faint">· strength ${fmt(e.strength)}</span></div>`).join("")}</div>` : ""}`);
  }
  if (d) {
    const rows = Object.entries(d.profile ?? {});
    parts.push(`<div class="small">The hypothesis: <b>${(nm.valueHtml(d.subentity))}</b> ${Math.abs(d.change ?? 0) < 1e-9 ? "stays unchanged"
      : `changes by ${signed(d.change)} ${esc(unit(d.subentity))}`} within ${d.window_days ?? "?"} days.</div>
      <div class="small muted">Its context now: ${esc(contextText(d.context, nm))}</div>
      ${rows.length ? `<table class="list small ev-profile"><thead><tr><th>Context</th><th>Raised</th><th>Cut</th><th>Held</th></tr></thead>
        <tbody>${rows.map(([c, n]) => `<tr class="${c === d.context ? "hl" : ""}"><td>${esc(contextText(c, nm))}</td><td>${n[0]}</td><td>${n[1]}</td><td>${n[2]}</td></tr>`).join("")}</tbody></table>`
        : `<div class="small faint">No decisions recorded yet: its entity memory has no profile for it.</div>`}
      ${d.drivers.length ? `<div class="small">Driven by ${d.drivers.map((x) => `${(nm.valueHtml(x.source))} <span class="mono">${signed(x.z)} sd</span> <span class="faint">(${esc(x.label)})</span>`).join("; ")}</div>` : ""}`);
  }
  if (ev.series.length) {
    parts.push(`<div class="small muted" style="margin-top:6px">The data it reads: daily deviation from normal (sd), the last ${ev.series[0].points.length} days;
      dots are observed days</div>${ev.series.map((s, i) => `<div class="ev-series"><span class="nm">${esc(s.name)} <span class="faint">(${esc(s.unit)})</span></span>
        <span class="ev-spark" data-i="${i}"></span><span class="mono small">${signed(s.points.at(-1)?.z ?? 0)} sd</span></div>`).join("")}`);
  }
  if (ev.news.length || ev.data_releases.count) {
    parts.push(`<div class="small muted" style="margin-top:6px">News and data that touched it</div>
      ${ev.news.map((n) => `<div class="small"><span class="faint mono">${esc(day(n.published_at))}</span> ${esc(n.headline)}
        ${n.status ? `<span class="badge">${esc(String(n.status).replace(/_/g, " "))}</span>` : ""}</div>`).join("")}
      ${ev.data_releases.count ? `<div class="small faint">${ev.data_releases.count} scheduled data release${ev.data_releases.count === 1 ? "" : "s"} observed these subentities, the latest on ${esc(day(ev.data_releases.last))}</div>` : ""}`);
  }
  if (ev.watched.length) {
    parts.push(`<div class="small faint" style="margin-top:6px">Informational value is measured against ${ev.watched.map((w) =>
      `${esc(w.thesis_id)}${w.question ? ` “${esc(w.question)}”` : ""}`).join(", ")}.</div>`);
  }
  return parts.join("");
}

export function initHypotheses({ toast }) {
  const el = document.getElementById("tab-hypotheses");
  let timer = null;
  let shown = FIRST;
  let filter = "all";
  const opened = new Set();
  const showing = new Set();          // hypotheses whose data is open

  async function render() {
    let hs = [];
    let fcs = [];
    try { [hs, fcs] = await Promise.all([api.hypotheses(), api.forecasts()]); } catch { return; }
    const theses = [...new Map(fcs.map((f) => [f.thesis_id, f])).values()];
    const counts = { all: hs.length };
    for (const v of hs) counts[kindOf(v.hypothesis)] = (counts[kindOf(v.hypothesis)] ?? 0) + 1;
    const pool = filter === "all" ? hs : hs.filter((v) => kindOf(v.hypothesis) === filter);
    const list = pool.slice(0, shown);
    el.innerHTML = `<div class="group-label">Hypotheses</div><h3>Hypothesis frontier</h3>
      <p class="small muted">Hypotheses about the presence or absence of interactions and the proposed decisions of entities.
        Each has a probability p and an informational value: how much the forecasts you watch would move if it held (sd),
        times how unsure the model is. The value decays over time and is rescored as updates arrive.</p>
      <div class="chips hy-filters">${FILTERS.map(([k, label]) => `<button class="pick ${filter === k ? "on" : ""}" data-f="${k}" aria-pressed="${filter === k}">
        ${esc(label)} <span class="faint">${counts[k] ?? 0}</span></button>`).join("")}</div>
      ${list.length ? "" : "<p class='muted small'>No open hypotheses of this kind.</p>"}
      ${list.map((v) => {
        const h = v.hypothesis;
        const k = kindOf(h);
        return `<details class="hrow" data-h="${esc(h.id)}" ${opened.has(h.id) ? "open" : ""}>
          <summary><span class="badge ${k === "entity_decision" ? "init" : k === "interaction_absent" ? "hyp" : "front"}" title="${esc(h.kind)}">${esc(KIND_NAME[k])}</span>
            <span class="st">${names().namedHtml(String(h.statement).replace(/ \(co-movement on the frontier\)$/, ""))}</span>
            <span class="small muted" title="p: the probability that it holds · informational value (sd): how much your forecasts would move if it held, times how unsure the model is">p ${fmt(h.probability)} · informational value ${fmt(v.current_value, 2)} sd</span></summary>
          <div class="hbody"><div class="small faint mono">${esc(h.id)} · ${esc(h.status)} · half-life ${fmt(h.half_life_days, 0)} days</div>
            <div class="spark"></div>
            <div class="row">
              <button class="ghost" data-act="data" aria-expanded="${showing.has(h.id)}">${showing.has(h.id) ? "Hide the data" : "Show the data ▸"}</button>
              ${h.kind === "entity_decision" ? `<select data-base aria-label="Base thesis"><option value="">(no base thesis)</option>
                ${theses.filter((t) => !String(t.thesis_id).includes("+")).map((t) => `<option value="${esc(t.thesis_id)}">${esc(t.thesis_id)}</option>`).join("")}</select>
                <button class="hyp" data-act="pose">Pose as thesis</button>` : ""}
              <button data-act="supported">Mark supported</button><button data-act="refuted">Mark refuted</button>
            </div>
            <div class="ev-box" ${showing.has(h.id) ? "" : "hidden"}></div></div></details>`;
      }).join("")}
      ${pool.length > shown ? `<button class="ghost small" id="hy-more">+ ${Math.min(MORE, pool.length - shown)} more of ${pool.length - shown}</button>` : ""}`;
    el.querySelector("#hy-more")?.addEventListener("click", () => { shown += MORE; render(); });
    for (const b of el.querySelectorAll("[data-f]")) b.addEventListener("click", () => { filter = b.dataset.f; shown = FIRST; render(); });
    for (const v of list) {
      const id = v.hypothesis.id;
      const row = el.querySelector(`[data-h="${CSS.escape(id)}"]`);
      const fill = () => {
        const sp = row.querySelector(".spark");
        if (sp.childElementCount) return;
        sp.appendChild(sparkline(v.decay_points, { value: (p) => p.value, width: 300, height: 34,
                                                   label: "informational value (sd) over the next 8 weeks, as it decays" }));
      };
      const box = row.querySelector(".ev-box");
      const loadData = async () => {
        box.innerHTML = `<p class="small faint"><span class="spinner" aria-hidden="true"></span> Gathering the data…</p>`;
        try {
          const ev = await api.hypothesisEvidence(id);
          const nm = names();
          box.innerHTML = evidenceHtml(ev, nm);
          if (ev.comovement?.pairs?.length) {
            box.querySelector(".ev-scatter")?.appendChild(scatter(ev.comovement.pairs, { xLabel: "earlier move (sd)", yLabel: "later innovation (sd)" }));
          }
          for (const s of box.querySelectorAll(".ev-spark")) {
            const ser = ev.series[+s.dataset.i];
            s.appendChild(sparkline(ser.points, { value: (p) => p.z, width: 180, height: 26, zero: true, dot: (p) => p.observed,
                                                  label: `${ser.name}: deviation from normal (sd)` }));
          }
        } catch (err) { box.innerHTML = `<p class="small error">${esc(errorText(err))}</p>`; }
      };
      if (row.open) fill();
      if (showing.has(id) && row.open) loadData();
      row.addEventListener("toggle", () => {
        if (row.open) { opened.add(id); fill(); if (showing.has(id) && !box.childElementCount) loadData(); } else opened.delete(id);
      });
      row.querySelector("[data-act=data]").addEventListener("click", (ev) => {
        const b = ev.currentTarget;
        if (showing.has(id)) { showing.delete(id); box.hidden = true; b.textContent = "Show the data ▸"; b.setAttribute("aria-expanded", "false"); return; }
        showing.add(id); box.hidden = false; b.textContent = "Hide the data"; b.setAttribute("aria-expanded", "true");
        loadData();
      });
      row.querySelector("[data-act=pose]")?.addEventListener("click", async () => {
        const base = row.querySelector("[data-base]")?.value || null;
        try {
          const fv = await api.poseHypothesis(id, base);
          emit("show-forecast", fv);
        } catch (err) { toast(errorText(err), "err"); }
      });
      for (const st of ["supported", "refuted"]) {
        row.querySelector(`[data-act=${st}]`).addEventListener("click", async () => {
          try { await api.setHypothesisStatus(id, st); render(); } catch (err) { toast(errorText(err), "err"); }
        });
      }
    }
  }

  const later = () => { clearTimeout(timer); timer = setTimeout(render, 1200); };
  on("hypotheses", later);
  on("graph", later);
  return { render };
}
