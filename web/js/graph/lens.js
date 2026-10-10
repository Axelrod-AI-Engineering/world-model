// The lens (Oct 9): whatever the cursor is on is drawn larger, as a small picture in its hover card, so a closed pill
// or a card shows what it holds without opening it. An entity shows its values as bars from normal (up green, down
// red) with each value's open node; a superentity shows its members and the interactions among them as a small
// graph; an interaction shows its effect and the belief that it exists.
import { esc } from "../util.js";

const W = 240;

export function entityLens(subs) {
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
        <text x="0" y="${rh / 2 + 3}" class="lens-name">${esc(trim(s.name, 22))}</text>
        <rect x="${b >= 0 ? mid : mid + b}" y="3" width="${Math.max(1, Math.abs(b))}" height="${rh - 7}" rx="2" class="${(s.z ?? 0) >= 0 ? "lens-up" : "lens-down"}"/>
        <circle cx="${W - 8}" cy="${rh / 2}" r="${r.toFixed(1)}" class="lens-open"><title>${Math.round(100 * (s.open ?? 1))}% not explained by the graph yet</title></circle>
      </g>`;
    }).join("")}</svg>${subs.length > rows.length ? `<div class="tt-f">+ ${subs.length - rows.length} more values</div>` : ""}`;
}

export function groupLens(memberIds, view) {
  const ents = (view?.entities ?? []).filter((e) => memberIds.includes(e.id));
  if (ents.length < 2) return "";
  const ent = new Map((view.subentities ?? []).map((s) => [s.id, s.entity_id]));
  const pairs = new Map();
  for (const l of view.links ?? []) {
    const a = ent.get(l.source);
    const b = ent.get(l.target);
    if (a && b && a !== b && memberIds.includes(a) && memberIds.includes(b)) pairs.set(`${a}|${b}`, l);
  }
  const h = 120;
  const cx = W / 2;
  const cy = h / 2;
  const R = Math.min(46, 18 + ents.length * 6);
  const pos = new Map(ents.map((e, i) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / ents.length;
    return [e.id, { x: cx + 1.9 * R * Math.cos(a), y: cy + R * Math.sin(a) }];
  }));
  return `<svg class="lens" viewBox="0 0 ${W} ${h}" width="${W}" height="${h}" role="img" aria-label="Its members and the interactions among them">
    <defs><marker id="lens-arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0 0L10 5L0 10z" class="lens-arrow"/></marker></defs>
    ${[...pairs.keys()].map((k) => {
      const [a, b] = k.split("|");
      const p = pos.get(a);
      const q = pos.get(b);
      const dx = q.x - p.x;
      const dy = q.y - p.y;
      const d = Math.hypot(dx, dy) || 1;
      return `<line x1="${(p.x + (dx / d) * 14).toFixed(1)}" y1="${(p.y + (dy / d) * 9).toFixed(1)}" x2="${(q.x - (dx / d) * 16).toFixed(1)}" y2="${(q.y - (dy / d) * 10).toFixed(1)}" class="lens-edge" marker-end="url(#lens-arr)"/>`;
    }).join("")}
    ${ents.map((e) => {
      const p = pos.get(e.id);
      const z = e.deviation?.z ?? 0;
      return `<g transform="translate(${p.x.toFixed(1)},${p.y.toFixed(1)})"><rect x="-30" y="-9" width="60" height="18" rx="6" class="lens-node${Math.abs(z) >= 0.5 ? (z > 0 ? " up" : " down") : ""}"/>
        <text y="3.5" class="lens-node-t">${esc(trim(e.name, 10))}</text></g>`;
    }).join("")}</svg>`;
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
