// A small Markdown renderer for the Literature tab (web/literature.md): headings (with ids for the contents),
// paragraphs, nested lists, tables, block quotes, rules, emphasis, inline code, and links. The document's first
// heading is its title; "# Part …" headings become h2, "##" h3, and "###" h4. Paragraphs after a "References"
// heading become a numbered reference list.
import { esc } from "./util.js";

const slug = (t) => t.toLowerCase().replace(/<[^>]+>/g, "").replace(/[^\w\s-]/g, "").trim().replace(/\s+/g, "-");

function inline(text) {
  let s = esc(text);
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
  s = s.replace(/(^|[^*\w])\*([^*\s][^*]*?)\*(?!\w)/g, "$1<i>$2</i>");
  s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (m, t, u) => (u.startsWith("#") ? `<a href="${u}">${t}</a>`
    : u.startsWith("http") ? `<a href="${u}" target="_blank" rel="noopener">${t}</a>` : t));
  s = s.replace(/(^|\s)(https?:\/\/[^\s<]+[^\s<.,;)])/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>');
  return s;
}

function list(lines) {
  // lines: [{indent, ordered, text}], nested by indentation
  let html = "";
  const stack = [];
  for (const l of lines) {
    while (stack.length && stack.at(-1).indent > l.indent) html += `</li></${stack.pop().tag}>`;
    const top = stack.at(-1);
    if (!top || l.indent > top.indent) {
      const tag = l.ordered ? "ol" : "ul";
      stack.push({ indent: l.indent, tag });
      html += `<${tag}><li>${inline(l.text)}`;
    } else {
      html += `</li><li>${inline(l.text)}`;
    }
  }
  while (stack.length) html += `</li></${stack.pop().tag}>`;
  return html;
}

export function renderMarkdown(src) {
  const lines = src.replace(/\r/g, "").split("\n");
  const out = [];
  let i = 0;
  let titled = false;
  let refs = false;
  let para = [];
  const flush = () => {
    if (!para.length) return;
    const text = para.join(" ");
    out.push(refs ? `<li>${inline(text)}</li>` : `<p>${inline(text)}</p>`);
    para = [];
  };
  const openRefs = () => { if (refs && !out.at(-1)?.startsWith("<li") && !out.at(-1)?.startsWith("<ol")) out.push('<ol class="refs">'); };
  while (i < lines.length) {
    const line = lines[i];
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      flush();
      if (refs) { out.push("</ol>"); refs = false; }
      const level = h[1].length;
      const text = h[2].trim();
      let tag = level === 1 && !titled ? "h1" : `h${Math.min(6, level + 1)}`;
      if (level === 1 && !titled) titled = true;
      if (level === 1 && tag !== "h1") tag = "h2";
      out.push(`<${tag} id="${slug(text)}"${level === 1 && tag === "h2" ? ' class="part"' : ""}>${inline(text)}</${tag}>`);
      refs = /^references$/i.test(text);
      if (refs) out.push('<ol class="refs">');
      i += 1;
      continue;
    }
    if (/^\s*$/.test(line)) { flush(); i += 1; continue; }
    if (/^---+\s*$/.test(line)) { flush(); out.push("<hr>"); i += 1; continue; }
    if (/^\|/.test(line)) {
      flush();
      const rows = [];
      while (i < lines.length && /^\|/.test(lines[i])) { rows.push(lines[i]); i += 1; }
      const cells = (r) => r.replace(/^\||\|\s*$/g, "").split("|").map((c) => c.trim());
      const head = cells(rows[0]);
      const body = rows.slice(2).map(cells);
      out.push(`<table><thead><tr>${head.map((c) => `<th>${inline(c)}</th>`).join("")}</tr></thead><tbody>${body.map((r) =>
        `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`);
      continue;
    }
    if (/^\s*([-*]|\d+\.)\s+/.test(line)) {
      flush();
      const items = [];
      while (i < lines.length && (/^\s*([-*]|\d+\.)\s+/.test(lines[i]) || (/^\s{2,}\S/.test(lines[i]) && items.length))) {
        const m = /^(\s*)([-*]|\d+\.)\s+(.*)$/.exec(lines[i]);
        if (m) items.push({ indent: m[1].length, ordered: /\d/.test(m[2]), text: m[3] });
        else items.at(-1).text += ` ${lines[i].trim()}`;
        i += 1;
      }
      out.push(list(items));
      continue;
    }
    if (/^>\s?/.test(line)) {
      flush();
      const q = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) { q.push(lines[i].replace(/^>\s?/, "")); i += 1; }
      out.push(`<blockquote>${inline(q.join(" "))}</blockquote>`);
      continue;
    }
    if (refs) { openRefs(); }
    para.push(line.trim());
    i += 1;
  }
  flush();
  if (refs) out.push("</ol>");
  return out.join("\n");
}
