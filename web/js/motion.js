// Motion for lists (demo polish, Oct 14). Panels rebuild their lists often (a status, a checkbox, a new trace event),
// so a CSS entrance would replay on every rebuild. This watches a few lists and animates only the items that are new
// since the last rebuild, one after another (30 ms apart, 240 ms each). Reduced motion (the system's or Admin's) skips it.

const reduced = () => document.body.classList.contains("reduced-motion")
  || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

// an item's identity across rebuilds: its id attribute if it has one, else the start of its text
const keyOf = (el) => el.dataset.id ?? el.dataset.me ?? el.dataset.pid ?? el.dataset.key ?? el.id
  ?? `${el.className}|${(el.textContent || "").trim().slice(0, 80)}`;

function watch(container, selector) {
  if (!container) return;
  let seen = new Set([...container.querySelectorAll(selector)].map(keyOf));
  let queued = false;
  const pass = () => {
    queued = false;
    const items = [...container.querySelectorAll(selector)];
    const now = new Set();
    let n = 0;
    for (const el of items) {
      const k = keyOf(el);
      now.add(k);
      if (seen.has(k) || reduced() || !el.animate || el.offsetParent === null) continue;
      el.animate([{ opacity: 0, translate: "0 5px" }, { opacity: 1, translate: "0 0" }],
        { duration: 240, delay: Math.min(n, 6) * 30, easing: "cubic-bezier(.2,.7,.2,1)", fill: "backwards" });
      n += 1;
    }
    seen = now;
  };
  new MutationObserver(() => { if (!queued) { queued = true; requestAnimationFrame(pass); } })
    .observe(container, { childList: true, subtree: true });
}

export function installListMotion() {
  const q = (s) => document.querySelector(s);
  watch(q("#review-body"), ".rv-sec, .rv-group, .rv-item, .rv-empty");
  watch(q("#inbox-body"), "article.card");
  watch(q(".examples:not(.import)"), "li.erow");
  watch(q("#find-results"), ".fr-hit");
  watch(q(".manual.checks"), ".ck-item");
}
