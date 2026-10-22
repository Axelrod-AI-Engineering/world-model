// The lens (Oct 9): whatever the cursor is on is drawn larger, as a small picture in its hover card, so a closed pill
// shows what it holds without opening it. An entity shows its values as bars from normal (up green, down red) with
// each value's open node; an interaction shows its effect and the belief that it exists.
import { ownPart } from "../names.js";
import { esc } from "../util.js";

const W = 240;

// The card is headed by the entity, so each value reads by its own part ("share price", not "Delta share price").
export function entityLens(subs, entName = null, kind = null) {
  if (!subs?.length) return "";
  const rows = subs.slice(0, 8);
  const rh = 17;
  const h = rows.length * rh + 4;
  const mid = 150;
  const span = 62;
  const bar = (z) => Math.max(-1, Math.min(1, z / 3)) * span;
  return `<svg class="lens" viewBox="0 0 ${W} ${h}" width="${W}" height="${h}" role="img" aria-label="Its values, from normal">
    <line x1="${mid}" x2="${mid}" y1="0" y2="${h}" class="lens-axis"/>
    ${rows.map((s, i) => {
      const y = 2 + i * rh;
      const b = bar(s.z ?? 0);
      const r = 1.8 + 3 * Math.max(0, Math.min(1, s.open ?? 1));
      return `<g transform="translate(0,${y})">
        <text x="0" y="${rh / 2 + 3}" class="lens-name">${esc(trim(entName ? ownPart(s.name, entName, kind) : s.name, 22))}</text>
        <rect x="${b >= 0 ? mid : mid + b}" y="3" width="${Math.max(1, Math.abs(b))}" height="${rh - 7}" rx="2" class="${(s.z ?? 0) >= 0 ? "lens-up" : "lens-down"}"/>
        <circle cx="${W - 8}" cy="${rh / 2}" r="${r.toFixed(1)}" class="lens-open"><title>${Math.round(100 * (s.open ?? 1))}% not explained by the graph yet</title></circle>
      </g>`;
    }).join("")}</svg>${subs.length > rows.length ? `<div class="tt-f">+ ${subs.length - rows.length} more values</div>` : ""}`;
}

export function linkLens(l) {
  if (!l) return "";
  const eff = Math.max(-1, Math.min(1, l.effect ?? 0));
  const mid = W / 2;
  return `<svg class="lens" viewBox="0 0 ${W} 38" width="${W}" height="38" role="img" aria-label="Its effect and existence">
    <text x="0" y="12" class="lens-name">effect</text>
    <line x1="${mid}" x2="${mid}" y1="2" y2="16" class="lens-axis"/>
    <rect x="${eff >= 0 ? mid : mid + eff * 70}" y="4" width="${Math.max(1, Math.abs(eff) * 70)}" height="10" rx="2" class="${eff >= 0 ? "lens-up" : "lens-down"}"/>
    <text x="0" y="31" class="lens-name">exists</text>
    <rect x="60" y="23" width="140" height="10" rx="2" class="lens-track"/>
    <rect x="60" y="23" width="${(140 * Math.max(0, Math.min(1, l.existence ?? 0))).toFixed(1)}" height="10" rx="2" class="lens-exist"/>
  </svg>`;
}

function trim(s, n) {
  const t = String(s ?? "");
  return t.length > n ? `${t.slice(0, n - 1)}…` : t;
}
