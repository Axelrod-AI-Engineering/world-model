// Small DOM and formatting helpers shared by the panels.

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export function fmt(x, digits = 2) {
  if (x == null || !Number.isFinite(+x)) return "—";
  const v = +x;
  if (Math.abs(v) >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return v.toFixed(digits);
}

export function signed(x, digits = 2) {
  if (x == null || !Number.isFinite(+x)) return "—";
  return `${+x >= 0 ? "+" : ""}${(+x).toFixed(digits)}`;
}

export function fmtTime(t) {
  if (!t) return "—";
  const d = new Date(t);
  return `${d.toISOString().slice(0, 10)} ${d.toISOString().slice(11, 16)}`;
}

export function fmtDate(t) {
  return t ? new Date(t).toISOString().slice(0, 10) : "—";
}

export function html(strings, ...vals) {
  return strings.reduce((acc, s, i) => acc + s + (i < vals.length ? vals[i] : ""), "");
}

export function fragment(markup) {
  const t = document.createElement("template");
  t.innerHTML = markup.trim();
  return t.content;
}

export function errorText(err) {
  if (!err) return "";
  const d = err.body?.detail;
  if (err.body?.unbound) return `Unbound ends: ${JSON.stringify(err.body.unbound)}`;
  if (Array.isArray(d)) return d.map((x) => `${(x.loc ?? []).join(".")}: ${x.msg}`).join("\n");
  return err.message ?? String(err);
}

