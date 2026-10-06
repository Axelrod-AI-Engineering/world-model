// Review queue (§13.6): kind, reasons, ops with a before/after preview, refinement steps as a breadcrumb,
// and evidence. Approve; Edit (JSON editor plus quick fields); Reject (a note is required); Defer.
// A frontier promotion also shows the earlier move against the later innovation.
import { api } from "../api.js";
import { scatter } from "../charts/fan.js";
import { emit, on, refreshGraph, store } from "../store.js";
import { errorText, esc, fmt, SPEC_BADGE } from "../util.js";

const KIND_LABEL = {
  graph_update: "Graph update", refinement: "Refinement", frontier_promotion: "Frontier promotion",
  superentity_admission: "Superentity admission", superentity_dissolution: "Superentity dissolution",
  missing_relation: "Missing relation",
};

export function initReview({ openModal, toast }) {
  const body = document.getElementById("review-body");
  const counts = [document.getElementById("review-count"), document.getElementById("review-count-tab")];
  let focused = null;

  function render() {
    const ps = store.proposals ?? [];
    for (const c of counts) {
      c.textContent = String(ps.length);
      c.classList.toggle("hot", ps.length > 0);
    }
    if (!ps.length) {
      body.innerHTML = `<p class="empty">Nothing waits for review. Changes to the graph's structure (new entities, new links,
        promotions, new superentities) stop here for your approval.</p>`;
      focused = null;
      return;
    }
    if (!ps.some((p) => p.proposal.id === focused)) focused = ps[0].proposal.id;
    body.innerHTML = ps.map((pv) => card(pv)).join("");
    for (const el of body.querySelectorAll("[data-pr]")) {
      const id = el.dataset.pr;
      el.addEventListener("focusin", () => setFocus(id));
      el.addEventListener("click", () => setFocus(id));
      el.querySelector("[data-act=approve]")?.addEventListener("click", (ev) => { ev.stopPropagation(); approve(id); });
      el.querySelector("[data-act=reject]")?.addEventListener("click", (ev) => { ev.stopPropagation(); reject(id); });
      el.querySelector("[data-act=defer]")?.addEventListener("click", (ev) => { ev.stopPropagation(); defer(id); });
      el.querySelector("[data-act=edit]")?.addEventListener("click", (ev) => { ev.stopPropagation(); edit(id); });
    }
    for (const pv of ps) {
      if (pv.proposal.kind === "frontier_promotion" && pv.proposal.subject_id) loadSeries(pv);
    }
  }

  function setFocus(id) {
    focused = id;
    for (const el of body.querySelectorAll("[data-pr]")) el.classList.toggle("selected", el.dataset.pr === id);
  }

  function card(pv) {
    const p = pv.proposal;
    const ops = pv.ops.map((o) => `
      <div style="margin:3px 0"><span class="chip op">${esc(o.op)}</span> <span class="small">${esc(o.summary)}</span>
        <div>${(o.ends ?? []).map((e) => `<span class="badge spec-${e.level}" title="${esc(e.ref)}">${esc(e.end)} · ${SPEC_BADGE[e.level] ?? e.level}${e.level !== "subentity" && e.ref ? `: ${esc(e.ref)}` : ""}</span>`).join(" ")}</div>
      </div>`).join("");
    const preview = (pv.preview ?? []).map((x) => {
      if (x.kind === "change") {
        return `<div class="preview-row"><span class="mono">${esc(x.ref)}</span><span>${fmt(x.before)}</span><span class="arrow">→</span><b>${fmt(x.after)}</b><span class="muted">${esc(x.unit ?? "")}</span></div>`;
      }
      return `<div class="preview-row"><span class="badge ${x.kind === "remove" ? "front" : "wm"}">${esc(x.kind)}</span><span class="mono">${esc(x.ref)}</span><span>${esc(x.name ?? "")}</span></div>`;
    }).join("");
    const crumbs = groupCrumbs(pv.refinement_steps ?? []);
    const evidence = (p.event.evidence ?? []).slice(0, 3).map((e) => `<div class="small muted">“${esc(e.excerpt)}”</div>`).join("");
    const reasons = (p.review_reasons ?? []).join("; ");
    return `
      <article class="card ${focused === p.id ? "selected" : ""}" data-pr="${esc(p.id)}" tabindex="0" aria-label="${esc(KIND_LABEL[p.kind] ?? p.kind)} ${esc(p.id)}">
        <div class="meta"><span class="badge out">${esc(KIND_LABEL[p.kind] ?? p.kind)}</span><span class="mono">${esc(p.id)}</span>
          ${p.market_event_id ? `<span class="mono">${esc(p.market_event_id)}</span>` : ""}
          ${p.status === "deferred" ? `<span class="badge">deferred</span>` : ""}</div>
        ${reasons ? `<div class="reasons">Needs review: ${esc(reasons)}</div>` : ""}
        ${p.reason ? `<div class="small">${esc(p.reason)}</div>` : ""}
        ${crumbs ? `<div class="breadcrumb">${crumbs}</div>` : ""}
        ${ops}
        ${preview ? `<div style="margin-top:4px">${preview}</div>` : ""}
        ${evidence}
        <div class="series" data-series="${esc(p.subject_id ?? "")}"></div>
        <div class="row" style="margin-top:6px">
          <button class="primary" data-act="approve" title="Approve (A)">Approve</button>
          <button data-act="edit">Edit</button>
          <button class="danger" data-act="reject" title="Reject (R)">Reject</button>
          <button data-act="defer">Defer</button>
        </div>
      </article>`;
  }

  function groupCrumbs(steps) {
    const byOp = new Map();
    for (const s of steps) {
      const k = `${s.op_index}:${s.end}`;
      if (!byOp.has(k)) byOp.set(k, []);
      byOp.get(k).push(s);
    }
    return [...byOp.entries()].map(([k, ss]) => {
      const [op, end] = k.split(":");
      return `<div>op ${esc(op)} ${esc(end)}: ${ss.map((s) => `<b>${esc(s.name)}</b>${s.created ? " (new)" : ""}`).join(" → ")}</div>`;
    }).join("");
  }

  async function loadSeries(pv) {
    const holder = body.querySelector(`[data-pr="${CSS.escape(pv.proposal.id)}"] .series`);
    if (!holder) return;
    try {
      const s = await api.frontierSeries(pv.proposal.subject_id);
      holder.innerHTML = `<div class="small muted">${esc(s.earlier)} → ${esc(s.later)}, lag ${s.lag_days} days, corr ${fmt(s.corr)}</div>`;
      holder.appendChild(scatter(s.pairs, { xLabel: "earlier move", yLabel: "later innovation" }));
      const entry = store.view?.frontier?.find((f) => f.id === pv.proposal.subject_id);
      if (entry?.ambiguous_direction) {
        holder.insertAdjacentHTML("beforeend", `<div class="row small">Direction is ambiguous:
          <label><input type="radio" name="dir-${esc(pv.proposal.id)}" checked> ${esc(s.earlier)} → ${esc(s.later)}</label>
          <label><input type="radio" name="dir-${esc(pv.proposal.id)}" data-flip="1"> ${esc(s.later)} → ${esc(s.earlier)}</label></div>`);
      }
    } catch { /* the entry may have closed */ }
  }

  async function act(fn, ok) {
    try {
      await fn();
      toast(ok);
      await refreshGraph();
      emit("reviewed", null);
    } catch (err) {
      toast(errorText(err), "err");
    }
  }

  const approve = (id) => {
    const flip = body.querySelector(`[data-pr="${CSS.escape(id)}"] input[data-flip]:checked`);
    if (flip) {
      const pv = store.proposals.find((x) => x.proposal.id === id);
      const ev = structuredClone(pv.proposal.event);
      for (const op of ev.ops) if (op.op === "add_interaction") [op.source, op.target] = [op.target, op.source];
      return act(async () => { await api.edit(id, ev); await api.approve(id); }, `Approved ${id} (direction flipped).`);
    }
    return act(() => api.approve(id), `Approved ${id}.`);
  };

  const defer = (id) => act(() => api.defer(id), `Deferred ${id}.`);

  function reject(id) {
    openModal(`<h3>Reject ${esc(id)}</h3><label for="rj-note" class="small">A note is required.</label>
      <textarea id="rj-note" rows="3" placeholder="Why?"></textarea><div class="error" id="rj-err"></div>
      <div class="actions"><button data-close>Cancel</button><button class="danger" id="rj-go">Reject</button></div>`,
    (root, close) => {
      root.querySelector("#rj-note").focus();
      root.querySelector("#rj-go").addEventListener("click", async () => {
        const note = root.querySelector("#rj-note").value.trim();
        if (!note) { root.querySelector("#rj-err").textContent = "A rejection needs a note."; return; }
        close();
        await act(() => api.reject(id, note), `Rejected ${id}.`);
      });
    });
  }

  function edit(id) {
    const pv = store.proposals.find((x) => x.proposal.id === id);
    if (!pv) return;
    const ev = pv.proposal.event;
    const quick = ev.ops.map((op, i) => {
      if (op.op !== "add_interaction") return "";
      const cands = (pv.ops[i]?.ends ?? []).filter((e) => e.candidates?.length);
      return `<div class="card"><div class="small"><b>op ${i}</b> ${esc(op.label)}</div>
        <div class="form-grid">
          <label>Label</label><input type="text" data-q="label" data-op="${i}" value="${esc(op.label)}">
          <label>Polarity</label><button data-q="flip" data-op="${i}">flip (${op.polarity > 0 ? "+" : "−"})</button>
          ${cands.map((e) => `<label>Rebind ${esc(e.end)}</label><select data-q="rebind" data-op="${i}" data-end="${esc(e.end)}">
            <option value="">(keep)</option>${e.candidates.map(([c, s]) => `<option value="${esc(c)}">${esc(c)} (${fmt(s)})</option>`).join("")}</select>`).join("")}
        </div></div>`;
    }).join("");
    openModal(`<h3>Edit ${esc(id)}</h3>${quick}
      <label class="small" for="ed-json">GraphUpdateEvent (validated by the server against the schema)</label>
      <textarea id="ed-json" rows="14">${esc(JSON.stringify(ev, null, 2))}</textarea><div class="error" id="ed-err"></div>
      <div class="actions"><button data-close>Cancel</button><button class="primary" id="ed-go">Save edit</button></div>`,
    (root, close) => {
      const ta = root.querySelector("#ed-json");
      const mutate = (fn) => {
        try { const e = JSON.parse(ta.value); fn(e); ta.value = JSON.stringify(e, null, 2); } catch (err) {
          root.querySelector("#ed-err").textContent = `Invalid JSON: ${err.message}`;
        }
      };
      for (const inp of root.querySelectorAll("[data-q=label]")) {
        inp.addEventListener("change", () => mutate((e) => { e.ops[+inp.dataset.op].label = inp.value; }));
      }
      for (const b of root.querySelectorAll("[data-q=flip]")) {
        b.addEventListener("click", () => mutate((e) => {
          const op = e.ops[+b.dataset.op];
          op.polarity = -op.polarity;
          b.textContent = `flip (${op.polarity > 0 ? "+" : "−"})`;
        }));
      }
      for (const s of root.querySelectorAll("[data-q=rebind]")) {
        s.addEventListener("change", () => mutate((e) => {
          if (!s.value) return;
          const op = e.ops[+s.dataset.op];
          const end = s.dataset.end;
          const cur = op[end] ?? {};
          op[end] = s.value.includes(".") ? { kind: "concrete", subentity_id: s.value }
            : { ...cur, kind: "abstract", entity_id: s.value, candidate_entity_ids: [] };
        }));
      }
      root.querySelector("#ed-go").addEventListener("click", async () => {
        let parsed;
        try { parsed = JSON.parse(ta.value); } catch (err) { root.querySelector("#ed-err").textContent = `Invalid JSON: ${err.message}`; return; }
        try {
          await api.edit(id, parsed);
          close();
          toast(`Edited ${id}; it stays in the queue for approval.`);
          await refreshGraph();
        } catch (err) {
          root.querySelector("#ed-err").textContent = errorText(err);
        }
      });
    });
  }

  on("proposals", render);
  on("flash-review", (id) => {
    const el = body.querySelector(`[data-pr="${CSS.escape(String(id))}"]`);
    if (el) { el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash"); }
  });
  render();
  return {
    approveFocused: () => focused && approve(focused),
    rejectFocused: () => focused && reject(focused),
  };
}
