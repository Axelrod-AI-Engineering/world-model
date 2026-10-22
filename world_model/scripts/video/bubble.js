    bubble({ id, text, at, side = "right", nth = 0 }) {
      const r = rectOf(at, nth);
      if (!r) throw new Error(`no target ${at}`);
      const bub = add("div", "vbub");
      bub.textContent = text;
      const bw = bub.offsetWidth;
      const bh = bub.offsetHeight;
      // the bubble covers nothing it can avoid; its arrow may pass into the container its target sits in, but should
      // cross as few of that container's words as it can
      const obs = obstacles([bub], r);
      const holder = elOf(at, nth)?.closest("#left-panel, #right-panel, .manual, #drawer.open, #console");
      const texts = holder ? textBoxes(holder).filter((t) => ov(t, { l: r.l - 2, t: r.t - 2, r: r.r + 2, b: r.b + 2 }) === 0) : [];
      const { x, y } = place(r, bw, bh, side, obs, at, texts);
      bub.style.left = `${x}px`;
      bub.style.top = `${y}px`;
      const bb = { l: x, t: y, r: x + bw, b: y + bh, cx: x + bw / 2, cy: y + bh / 2, w: bw, h: bh };
      let [x2, y2, n2x, n2y] = anchor(at, r, bb.cx, bb.cy);
      let [x1, y1, n1x, n1y] = startOf(bb, x2, y2);
      const route = [...obs.filter((o) => !inside(r, o) && !inside(o, r)), ...texts];
      // a ringed target can be met anywhere on its ring: take the point whose arrow crosses the least, then turns the least
      const ringC = circles.get(at);
      if (ringC) {
        let best = null;
        for (let i = 0; i < 64; i++) {
          const a = (i / 64) * Math.PI * 2;
          const [ax, ay, anx, any] = anchor(at, r, ringC.cx + Math.cos(a) * 4000, ringC.cy + Math.sin(a) * 4000);
          const [sx, sy, snx, sny] = startOf(bb, ax, ay);
          const L = Math.hypot(ax - sx, ay - sy) || 1;
          const ch = [(ax - sx) / L, (ay - sy) / L];
          const turn = Math.acos(clamp(snx * ch[0] + sny * ch[1], -1, 1)) + Math.acos(clamp(-anx * ch[0] - any * ch[1], -1, 1));
          const cost = hits(arrowPts(sx, sy, [snx, sny], ax, ay, [anx, any]), route) * 1000 + turn * 40 + L * 0.15;
          if (!best || cost < best.cost) best = { cost, a: [ax, ay, anx, any], s: [sx, sy, snx, sny] };
        }
        [x2, y2, n2x, n2y] = best.a;
        [x1, y1, n1x, n1y] = best.s;
      }
      const bend = bestBend(x1, y1, x2, y2, route);
      bub.style.transformOrigin = `${clamp(((x1 - x) / bw) * 100, 0, 100)}% ${clamp(((y1 - y) / bh) * 100, 0, 100)}%`;
      popIn(bub);
      keep(id, bub);
      drawCurve(id, x1, y1, x2, y2, { bend, delay: 200, dur: 520 });
    },
