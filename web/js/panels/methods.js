// Methods (addition). DECISION: the user asked for a separate pane that describes, in an academic tone,
// how the functions this demo shows would be implemented and with which ML stack, rooted in the
// cognitive science of concept formation. The briefing lives in web/methods.html (one source, readable
// on its own too); this pane loads it, builds a contents list from its section headings, and keeps the
// reading position while it is open.
import { esc } from "../util.js";

export function initMethods() {
  const pane = document.createElement("section");
  pane.id = "methods";
  pane.className = "methods hidden";
  pane.setAttribute("role", "dialog");
  pane.setAttribute("aria-label", "Proposed implementation and ML stack");
  document.getElementById("stage").appendChild(pane);
  let loaded = false;

  async function load() {
    pane.innerHTML = `<header><div class="group-label">Methods · a technical briefing on the proposed implementation and ML stack</div><span class="spacer"></span>
        <a class="small" href="methods.html" target="_blank" rel="noopener">Open on its own ↗</a>
        <button class="close" aria-label="Close the briefing (Esc)">✕</button></header>
      <div class="mbody"><nav class="toc" aria-label="Contents"></nav><article class="doc"><p class="empty">Loading…</p></article></div>`;
    pane.querySelector(".close").addEventListener("click", close);
    try {
      const html = await (await fetch("methods.html")).text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      const art = pane.querySelector("article.doc");
      art.innerHTML = doc.querySelector("main")?.innerHTML ?? doc.body.innerHTML;
      const heads = [...art.querySelectorAll("h2[id], h3[id]")];
      pane.querySelector(".toc").innerHTML = heads.map((h) => `<a href="#${esc(h.id)}" class="${h.tagName === "H3" ? "sub" : ""}">${esc(h.textContent)}</a>`).join("");
      for (const a of pane.querySelectorAll(".toc a")) {
        a.addEventListener("click", (ev) => {
          ev.preventDefault();
          // scroll the article only (scrollIntoView would also scroll the page and shift the whole app)
          const target = art.querySelector(`#${CSS.escape(a.getAttribute("href").slice(1))}`);
          if (target) {
            const top = target.getBoundingClientRect().top - art.getBoundingClientRect().top + art.scrollTop - 8;
            art.scrollTo({ top, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
          }
        });
      }
      loaded = true;
    } catch (err) {
      pane.querySelector("article.doc").innerHTML = `<p class="error">Could not load the briefing: ${esc(err.message)}</p>`;
    }
  }

  function open() {
    pane.classList.remove("hidden");
    document.getElementById("btn-methods")?.setAttribute("aria-expanded", "true");
    if (!loaded) load();
  }
  function close() {
    pane.classList.add("hidden");
    document.getElementById("btn-methods")?.setAttribute("aria-expanded", "false");
  }
  return { open, close, toggle: () => (pane.classList.contains("hidden") ? open() : close()), isOpen: () => !pane.classList.contains("hidden") };
}
