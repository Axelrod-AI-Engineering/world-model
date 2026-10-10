V="/private/tmp/claude-501/-Users-karthiksing05-Documents-Axelrod-AI-karthik-world-model/30c82e23-1d79-4de4-a5fa-fd924b15d7d1/scratchpad/video"
p=f"{V}/annotate3.js"
s=open(p).read()
def rep(a,b):
    global s
    assert a in s, a[:80]; s=s.replace(a,b,1)
rep('''  .vbadge { position: fixed; z-index: 9996; pointer-events: none; min-width: 34px; height: 34px; padding: 0 8px; box-sizing: border-box; border-radius: 17px;''',
    '''  .vbadge { position: fixed; z-index: 9996; pointer-events: none; min-width: 26px; height: 26px; padding: 0 6px; box-sizing: border-box; border-radius: 13px;''')
rep('''    font: 800 17px "Bricolage Grotesque", system-ui; color: ${INK}; transform: scale(0); transition: transform .5s ${SPRING}; }
  .vbadge.in''','''    font: 800 14px "Bricolage Grotesque", system-ui; color: ${INK}; transform: scale(0); transition: transform .5s ${SPRING}; }
  .vbadge.in''')
rep('''  function popIn(el) {''', open(f"{V}/engine.js").read() + '''
  function popIn(el) {''')
rep('''  function drawCurve(id, x1, y1, x2, y2, { bend = 0.18, head = true, dur = 650, delay = 0 } = {}) {''',
    '''  function drawCurve(id, x1, y1, x2, y2, { bend = 0.14, head = true, dur = 650, delay = 0 } = {}) {''')
a_start = s.index("    bubble({ id, text, at, side = \"right\", nth = 0, dx = 0, dy = 0, dist }) {")
a_end = s.index("    arrow({ id, from, to }) {")
s = s[:a_start] + open(f"{V}/bubble.js").read() + s[a_end:]
a_start = s.index("    arrow({ id, from, to }) {")
a_end = s.index("    circle({ id, at, nth = 0, pad = 10 }) {")
s = s[:a_start] + '''    arrow({ id, from, to, bend }) {
      const a = rectOf(from);
      const b = rectOf(to);
      if (!a || !b) throw new Error(`no arrow ends ${from} ${to}`);
      const [x2, y2, n2x, n2y] = anchor(to, b, a.cx, a.cy);
      // an arrow leaves its source from the side facing its target, never level like words
      const [x1, y1, n1x, n1y] = anchor(from, { ...a, text: false, badge: true }, x2, y2, 4);
      const obs = obstacles([]).filter((o) => !inside(a, o) && !inside(b, o) && !inside(o, a) && !inside(o, b));
      drawCurve(id, x1, y1, x2, y2, { bend: bend ?? bestBend(x1, y1, x2, y2, obs), dur: 560 });
    },
''' + s[a_end:]
rep('''    circle({ id, at, nth = 0, pad = 10 }) {
      const r = rectOf(at, nth);
      if (!r) throw new Error(`no target ${at}`);
      const rx = r.w / 2 + pad + 4;
      const ry = r.h / 2 + pad;''','''    circle({ id, at, nth = 0 }) {
      const r = rectOf(at, nth);
      if (!r) throw new Error(`no target ${at}`);
      // one rule: a ring that clears the box by a little. a line of words or a tab gets an ellipse; a tall or very wide
      // box gets a rounded rectangle a fixed 7px outside it, so the line never cuts through what it encloses
      const n = r.h < 44 && r.w / r.h < 7 ? 2 : 0;
      const rx = r.w / 2 + (n === 2 ? Math.min(14, 6 + r.w * 0.04) : 7);
      const ry = r.h / 2 + (n === 2 ? Math.min(9, 4 + r.h * 0.08) : 7);
      // the rounded rectangle, walked clockwise from its top-left corner: points with their outward normals
      let poly = null;
      if (!n) {
        poly = [];
        const R = Math.min(16, ry);
        const segs = [
          ["arc", -rx + R, -ry + R, Math.PI, Math.PI * 1.5], ["line", -rx + R, -ry, rx - R, -ry, 0, -1],
          ["arc", rx - R, -ry + R, Math.PI * 1.5, Math.PI * 2], ["line", rx, -ry + R, rx, ry - R, 1, 0],
          ["arc", rx - R, ry - R, 0, Math.PI * 0.5], ["line", rx - R, ry, -rx + R, ry, 0, 1],
          ["arc", -rx + R, ry - R, Math.PI * 0.5, Math.PI], ["line", -rx, ry - R, -rx, -ry + R, -1, 0],
        ];
        for (const sg of segs) {
          if (sg[0] === "arc") {
            const steps = 8;
            for (let k = 0; k < steps; k++) {
              const a = sg[3] + ((sg[4] - sg[3]) * k) / steps;
              poly.push([r.cx + sg[1] + Math.cos(a) * R, r.cy + sg[2] + Math.sin(a) * R, Math.cos(a), Math.sin(a)]);
            }
          } else {
            const L = Math.hypot(sg[3] - sg[1], sg[4] - sg[2]);
            const steps = Math.max(1, Math.round(L / 6));
            for (let k = 0; k < steps; k++) {
              poly.push([r.cx + sg[1] + ((sg[3] - sg[1]) * k) / steps, r.cy + sg[2] + ((sg[4] - sg[2]) * k) / steps, sg[5], sg[6]]);
            }
          }
        }
      }
      const ring = (a) => [Math.cos(a), Math.sin(a)];
      if (typeof at === "string") circles.set(at, n ? { cx: r.cx, cy: r.cy, rx: rx * 1.02, ry: ry * 1.02, n } : { cx: r.cx, cy: r.cy, rx, ry, n: 12, poly });''')
rep('''        const k = 1 + (i / 72) * 0.07;''', '''        const k = 1 + (i / 72) * 0.04;''')
rep('''      g.__retract = () => {
        for (const p of [halo, line]) { p.style.transition = "stroke-dashoffset 320ms cubic-bezier(.5,0,.75,0)"; p.style.strokeDashoffset = `${-len}`; }
        later(380, () => g.remove());
      };
      keep(id, g);
    },''','''      g.__retract = () => {
        if (typeof at === "string") circles.delete(at);
        for (const p of [halo, line]) { p.style.transition = "stroke-dashoffset 320ms cubic-bezier(.5,0,.75,0)"; p.style.strokeDashoffset = `${-len}`; }
        later(380, () => g.remove());
      };
      keep(id, g);
    },''')
rep('''      const x = side === "left" ? r.l - 26 : side === "right" ? r.r + 26 : r.cx;
      bd.style.left = `${x + dx - 17}px`;
      bd.style.top = `${r.cy + dy - 17}px`;''','''      const x = side === "left" ? r.l - 22 : side === "right" ? r.r + 22 : r.cx;
      bd.style.left = `${x + dx - 13}px`;
      bd.style.top = `${r.cy + dy - 13}px`;''')

rep('''        pts.push([r.cx + Math.cos(a) * rx * k, r.cy + Math.sin(a) * ry * k]);''', '''        const [ux, uy] = ring(a);
        pts.push([r.cx + ux * rx * k, r.cy + uy * ry * k]);''')
rep('''      let d = `M${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`;''', '''      if (poly) {
        pts.length = 0;
        const N = poly.length;
        const start = Math.round(N * 0.94);
        const total = Math.round(N * 1.08);
        for (let i = 0; i <= total; i++) {
          const [px, py, nx, ny] = poly[(start + i) % N];
          const o = (i / total) * 3;
          pts.push([px + nx * o, py + ny * o]);
        }
      }
      let d = `M${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`;''')
open(p,'w').write(s)
print("ok")
