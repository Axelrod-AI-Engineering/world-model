// The right-click menu: every per-node choice lives here, so the canvas itself carries no buttons.
// Arrow keys move, Enter picks, Esc closes.
import { esc } from "../util.js";

let current = null;

export function closeMenu() {
  if (!current) return;
  current.el.remove();
  window.removeEventListener("pointerdown", current.outside, true);
  window.removeEventListener("keydown", current.keys, true);
  window.removeEventListener("blur", closeMenu);
  window.removeEventListener("resize", closeMenu);
  const back = current.restoreFocus;
  current = null;
  back?.focus?.({ preventScroll: true });
}

export function menuOpen() {
  return !!current;
}

// items: {label, hint?, kbd?, action, disabled?, swatch?: {fill, line}} | {sep: true} | {group: "label"}
export function openMenu(at, { title = null, subtitle = null, items = [] }) {
  closeMenu();
  const el = document.createElement("div");
  el.className = "ctx-menu";
  el.setAttribute("role", "menu");
  const parts = [];
  if (title) parts.push(`<div class="hd">${esc(title)}${subtitle ? `<small>${esc(subtitle)}</small>` : ""}</div><div class="sep"></div>`);
  items.forEach((it, i) => {
    if (it.sep) parts.push(`<div class="sep"></div>`);
    else if (it.group) parts.push(`<div class="label">${esc(it.group)}</div>`);
    else {
      const sw = it.swatch ? `<span class="sw" style="background:${esc(it.swatch.fill)};border-color:${esc(it.swatch.line)}"></span>` : "";
      parts.push(`<button role="menuitem" data-i="${i}" ${it.disabled ? "disabled" : ""} title="${esc(it.hint ?? "")}">${sw}
        <span>${esc(it.label)}</span>${it.kbd ? `<span class="kbd">${esc(it.kbd)}</span>` : ""}</button>`);
    }
  });
  el.innerHTML = parts.join("");
  document.getElementById("menu-root").appendChild(el);
  const { innerWidth: W, innerHeight: H } = window;
  const r = el.getBoundingClientRect();
  el.style.left = `${Math.max(6, Math.min(at.x, W - r.width - 6))}px`;
  el.style.top = `${Math.max(6, Math.min(at.y, H - r.height - 6))}px`;
  const buttons = [...el.querySelectorAll("button:not([disabled])")];
  for (const b of el.querySelectorAll("button[data-i]")) {
    b.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const it = items[+b.dataset.i];
      closeMenu();
      it.action?.();
    });
  }
  const outside = (ev) => { if (!el.contains(ev.target)) closeMenu(); };
  const keys = (ev) => {
    const i = buttons.indexOf(document.activeElement);
    if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); closeMenu(); }
    else if (ev.key === "ArrowDown") { ev.preventDefault(); buttons[(i + 1) % buttons.length]?.focus(); }
    else if (ev.key === "ArrowUp") { ev.preventDefault(); buttons[(i - 1 + buttons.length) % buttons.length]?.focus(); }
    else if (ev.key === "Tab") { ev.preventDefault(); }
  };
  current = { el, outside, keys, restoreFocus: document.activeElement };
  setTimeout(() => {
    window.addEventListener("pointerdown", outside, true);
    window.addEventListener("blur", closeMenu);
    window.addEventListener("resize", closeMenu);
  }, 0);
  window.addEventListener("keydown", keys, true);
  if (at.keyboard) buttons[0]?.focus({ preventScroll: true });
}
