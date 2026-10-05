// The caption banner above the canvas, and the read-only banner for earlier versions.
import { backToLive, on, store } from "../store.js";
import { esc } from "../util.js";

export function initCaption() {
  const el = document.getElementById("caption");
  const ro = document.getElementById("readonly-banner");
  const render = () => {
    const c = store.caption;
    const st = store.status;
    const total = st?.total_steps ?? "?";
    el.querySelector(".step").textContent = c.step != null ? `step ${c.step}/${total}` : "";
    let text = c.text || st?.caption || "";
    if (!text && st?.loaded) {
      const title = store.scenarios.find((x) => x.id === st.scenario_id)?.title ?? st.scenario_id;
      text = st.step_index === 0 ? `${title}: loaded from its init snapshot. Press Step (→) or Play (Space) to begin.` : title;
    }
    el.querySelector(".text").textContent = text;
    el.classList.toggle("hyp", !!c.hyp);
  };
  on("caption", render);
  on("status", render);
  on("readonly", (v) => {
    if (v == null) {
      ro.classList.add("hidden");
      ro.innerHTML = "";
      return;
    }
    ro.classList.remove("hidden");
    ro.innerHTML = `<b>Read-only:</b> state version <span class="mono">v${esc(v)}</span>
      <span class="muted small">(the live engine keeps running)</span><span class="spacer"></span>
      <button id="ro-live">Back to live</button>`;
    ro.querySelector("#ro-live").addEventListener("click", backToLive);
  });
}
