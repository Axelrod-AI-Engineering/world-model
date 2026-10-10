"""Footage for the 2-minute internal devlog, choreographed to the voiceover's word timings (docs/media/AxelrodDemo.m4a).

Takes (voiceover seconds):
  A [ 0.0,  53.8)  title, the objects, the five stages          (state: the nest example approved)
  B [53.8,  83.2)  one event through the five stages            (rewound to the ripple example, waiting)
  C [83.2,  97.5)  earned beliefs: frontier, Checks, the drawer  (the frontier example, waiting)
  D [97.5, 115.6)  the key idea, thanks for watching             (the nest example approved again)
"""
import json
import math
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8766"
OUT = Path(__file__).parent
S = float(sys.argv[1]) if len(sys.argv) > 1 else 4.0          # slow motion: every clock in the page runs S times slower
QC = len(sys.argv) > 2 and sys.argv[2] == "qc"                  # the quality check: log any visible translucent text
TAG = sys.argv[3] if len(sys.argv) > 3 else "4"
LOG = {"takes": [], "misses": [], "slow": S, "geom": []}
INJECT = (OUT / "annotate4.js").read_text()
SNAPDIR = OUT / "snaps"
# DECISION: slow motion capture. Playwright's recorder keeps only some frames under load (4 to 16 new ones a second
# measured), so the page runs S times slower (timers, animation frames, d3, CSS animations) and the edit speeds it back.
SLOWDOWN = """(() => { const S = %s; if (S === 1) return;
  const pn = performance.now.bind(performance); const t0 = pn();
  performance.now = () => t0 + (pn() - t0) / S;
  const dn = Date.now; const d0 = dn(); Date.now = () => d0 + (dn() - d0) / S;
  const st = window.setTimeout, si = window.setInterval;
  window.setTimeout = (f, d, ...a) => st(f, (d || 0) * S, ...a);
  window.setInterval = (f, d, ...a) => si(f, (d || 0) * S, ...a);
  const raf = window.requestAnimationFrame.bind(window);
  window.requestAnimationFrame = (cb) => raf((ts) => cb(t0 + (ts - t0) / S));
})();""" % S


def api(path, body=None):
    req = urllib.request.Request(BASE + path, method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.loads(r.read() or b"null")


def settle():
    for _ in range(7200):
        if api("/api/sim/status")["state"] != "running":
            return
        time.sleep(0.25)


def approve_pending():
    for pv in api("/api/proposals?status=pending"):
        api(f"/api/proposals/{pv['proposal']['id']}/approve", {"by": "backend user"})
    settle()


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, record_video_dir=str(OUT / f"raw{TAG}"),
                        record_video_size={"width": 1440, "height": 900})
    ctx.add_init_script(SLOWDOWN)
    pg = ctx.new_page()
    cdp = ctx.new_cdp_session(pg)

    def css_slow():
        cdp.send("Animation.enable")
        cdp.send("Animation.setPlaybackRate", {"playbackRate": 1.0 / S})

    def sleep(sec):
        pg.wait_for_timeout(int(sec * S * 1000))
    T0 = time.time()
    wall = lambda: time.time() - T0  # noqa: E731
    pos = {"x": 1000.0, "y": 26.0}      # parked on the top bar's empty middle, where nothing shows a tooltip

    def js(code, arg=None):
        try:
            return pg.evaluate(code, arg)
        except Exception as exc:
            LOG["misses"].append(f"{code[:70]} {json.dumps(arg)[:80] if arg is not None else ''}: {str(exc).splitlines()[0][:120]}")
            return None

    def center(sel, nth=0):
        return js("""([s, n]) => { let els; if (s.includes('::')) { const [q, t] = s.split('::'); els = [...document.querySelectorAll(q)].filter((e) => (e.textContent || '').includes(t)); } else els = [...document.querySelectorAll(s)];
          const el = els[n]; if (!el) return null; const b = el.getBoundingClientRect(); return {x: b.left + b.width / 2, y: b.top + b.height / 2}; }""", [sel, nth])

    def glide(sel=None, x=None, y=None, dur=0.7, click=False, nth=0):
        if sel:
            c = center(sel, nth)
            if not c:
                LOG["misses"].append(f"glide {sel}")
                return
            x, y = c["x"], c["y"]
        x0, y0 = pos["x"], pos["y"]
        dur = dur * S
        n = max(8, int(dur * 50))
        bend = 0.12 * math.hypot(x - x0, y - y0)
        nx, ny = x - x0, y - y0
        ln = math.hypot(nx, ny) or 1
        px, py = -ny / ln, nx / ln
        for i in range(1, n + 1):
            t = i / n
            e = t * t * (3 - 2 * t)
            off = math.sin(math.pi * e) * bend * 0.25
            pg.mouse.move(x0 + nx * e + px * off, y0 + ny * e + py * off)
            pg.wait_for_timeout(int(dur * 1000 / n))
        pos["x"], pos["y"] = x, y
        if click:
            pg.mouse.down()
            pg.wait_for_timeout(int(110 * S))
            pg.mouse.up()

    def drag_to(sel, f0, f1, dur=1.0):
        r = js("(s) => { const el = document.querySelector(s); if (!el) return null; const b = el.getBoundingClientRect(); return {x: b.left, y: b.top, w: b.width, h: b.height}; }", sel)
        if not r:
            LOG["misses"].append(f"drag {sel}")
            return
        y = r["y"] + r["h"] / 2
        glide(x=r["x"] + r["w"] * f0, y=y, dur=0.4)
        pg.mouse.down()
        dur = dur * S
        n = int(dur * 40)
        for i in range(1, n + 1):
            t = i / n
            e = t * t * (3 - 2 * t)
            pg.mouse.move(r["x"] + r["w"] * (f0 + (f1 - f0) * e), y)
            pg.wait_for_timeout(int(dur * 1000 / n))
        pg.mouse.up()
        pos["x"], pos["y"] = r["x"] + r["w"] * f1, y

    def take(name, start, end, actions):
        w0 = wall()
        js(f"() => {{ window.__voStart = {start}; window.__voT0 = performance.now(); }}")
        LOG["takes"].append({"name": name, "vo_start": start, "vo_end": end, "wall_start": round(w0, 3)})
        for at, fn in actions:
            due = w0 + (at - start) * S
            lag = wall() - due
            if lag < 0:
                pg.wait_for_timeout(int(-lag * 1000))
            elif lag > 0.3 * S:
                LOG["misses"].append(f"{name} @{at}: late by {lag / S:.2f}s")
            fn()
        rest = w0 + (end - start) * S - wall()
        if rest > 0:
            pg.wait_for_timeout(int(rest * 1000))
        LOG["takes"][-1]["wall_end"] = round(wall(), 3)

    A = lambda code, arg=None: (lambda: js(code, arg))  # noqa: E731

    def bubble(id_, text, at, side="right", dist=110, dx=0, dy=0, nth=0):
        return A("(o) => window.__ann.bubble(o)", {"id": id_, "text": text, "at": at, "side": side, "dist": dist, "dx": dx, "dy": dy, "nth": nth})

    def circle(id_, at, pad=10, nth=0):
        return A("(o) => window.__ann.circle(o)", {"id": id_, "at": at, "pad": pad, "nth": nth})

    def badge(id_, n, at, side="right", dx=0, dy=0):
        return A("(o) => window.__ann.badge(o)", {"id": id_, "n": n, "at": at, "side": side, "dx": dx, "dy": dy})

    def arrow(id_, a, b_):
        return A("(o) => window.__ann.arrow(o)", {"id": id_, "from": a, "to": b_})

    def clear(*ids):
        return A("(ids) => window.__ann.clear(ids)", list(ids))

    def chapter(text):
        return A("(t) => window.__ann.chapter(t)", text)

    def key(k):
        return lambda: pg.keyboard.press(k)

    def snap(name):
        def go():
            if not QC:
                return
            SNAPDIR.mkdir(exist_ok=True)
            pg.screenshot(path=str(SNAPDIR / f"{name}.png"))
            res = js("() => window.__ann.verify()") or []
            LOG["geom"].append({"snap": name, "arrows": res})
            for i, tip in enumerate(js("() => window.__ann.liveTips()") or []):
                x, y = tip["tip"]
                clip = {"x": max(0, x - 130), "y": max(0, y - 80), "width": 260, "height": 160}
                pg.screenshot(path=str(SNAPDIR / f"{name}--{tip['id']}-{i}.png"), clip=clip)
            for i, c in enumerate(js("() => window.__ann.liveCircles()") or []):
                clip = {"x": max(0, c["cx"] - c["rx"] - 40), "y": max(0, c["cy"] - c["ry"] - 30),
                        "width": 2 * c["rx"] + 80, "height": 2 * c["ry"] + 60}
                pg.screenshot(path=str(SNAPDIR / f"{name}--circle-{i}.png"), clip=clip)
        return go

    def close_left():
        js("() => { const b = document.querySelector('[data-close-panel=\"left\"]'); if (b && b.offsetParent) b.click(); }")

    def unscroll():
        js("() => { document.scrollingElement.scrollTop = 0; for (const el of document.querySelectorAll('#stage, #canvas, main, body')) { el.scrollTop = 0; el.scrollLeft = 0; } }")

    def ready(chap=None):
        """Off camera, under the sheet: settle the view. The take itself slides the sheet away."""
        close_left()
        unscroll()
        sleep(0.8)
        js("() => window.axelrod.renderer.fit(0)")
        sleep(1.0)
        close_left()
        unscroll()
        if chap:
            js("(t) => window.__ann.chapter(t)", chap)
        sleep(0.8)

    def cover():
        js("() => window.__ann.clear()")

    away = A("() => window.__ann.sheetAway()")
    shut = A("() => window.__ann.sheet('', '')")

    # -- setup A: the nest example approved, Delta open ----------------------------------------------------------------
    pg.goto(BASE)
    pg.evaluate("() => { localStorage.setItem('axelrod.hinted', '1'); localStorage.setItem('axelrod.guide.mode', '\"off\"'); localStorage.setItem('axelrod.colorBy', 'change'); localStorage.setItem('axelrod.autoDetail', '0'); }")
    pg.reload()
    css_slow()
    sleep(2.5)
    pg.evaluate(INJECT)
    js("() => window.__ann.cinematic(window.axelrod.renderer)")
    js("() => window.__ann.sheet('', '', '', true)")
    if QC:
        js("() => window.__qc.start(() => (window.__voStart ?? -1) + (performance.now() - (window.__voT0 ?? performance.now())) / 1000)")
    pg.mouse.move(pos["x"], pos["y"])
    api("/api/examples/nest", {})
    settle()
    approve_pending()
    sleep(2.5)
    close_left()
    js("() => window.axelrod.renderer.setDetail('entity')")
    sleep(1.2)
    js("() => window.axelrod.renderer.toggleEntity('delta', true)")
    sleep(1.5)
    js("() => window.__ann.flash()")
    LOG["flash_wall"] = round(wall(), 3)
    sleep(0.7)
    close_left()
    unscroll()
    js("() => window.axelrod.renderer.fit(0)")
    sleep(1.0)

    oil = 'g.pill[data-id="resources_energy"]'
    delta = 'g.pill[data-id="delta"]'
    take("A", 0.0, 53.8, [
        (0.0, A("() => window.__ann.sheet('Axelrod <span>World Model</span>', 'A proposal: a causal world model of the economy', 'internal devlog · synthetic data', true)")),
        (4.5, away),
        (5.3, chapter("The objects")),
        (6.0, circle("ent", oil + " rect.body")),
        (6.2, bubble("entb", "Entity: an actor or an idea", oil + " rect.body", side="left")),
        (7.6, snap("A-entity")),
        (8.9, circle("ent2", delta + " rect.body")),
        (9.55, snap("A-delta")),
        (9.7, clear("ent", "entb", "ent2")),
        (9.8, circle("rows", f"union:{delta} g.row rect.bg")),
        (10.0, bubble("sub", "Subentities: the values each one holds", f"union:{delta} g.row rect.bg", side="right")),
        (11.6, snap("A-sub")),
        (13.5, clear("sub", "rows")),
        (13.9, A("(o) => window.__ann.underline(o)", {"id": "fuel", "at": f'{delta} g.row[data-id="delta.fuel_cost"] text.rname'})),
        (14.9, snap("A-fuel")),
        (15.5, clear("fuel")),
        (15.7, A("(o) => window.__ann.traceEdge(o)", {"id": "edge", "a": oil + " rect.body", "b": delta + " rect.body"})),
        (16.1, bubble("int", "Interaction: a causal link between two values", "point:edge", side="left")),
        (17.4, snap("A-interaction")),
        (20.2, clear("int", "edge")),
        (20.5, circle("sup", "g.hull-tab::Policy loop@")),
        (20.8, bubble("supb", "Superentity: entities that move as one", "g.hull-tab::Policy loop@", side="right")),
        (22.2, snap("A-superentity")),
        (25.6, clear("sup", "supb")),
        (26.1, A("(o) => window.__ann.headline(o)", {"id": "hd", "text": "Brent jumps 20% as producers tighten supply", "x": 1060, "y": 220})),
        (27.7, bubble("gue", "A graph update event: proposed edits to all of these", "#vh-hd", side="bottom")),
        (29.1, snap("A-gue")),
        (31.0, clear("hd", "gue")),
        (31.4, chapter("Five stages")),
        (31.6, A("() => window.__ann.stages(true)")),
        (33.8, A("() => window.__ann.stageOn(0)")),
        (36.9, A("() => window.__ann.stageOn(1)")),
        (40.0, A("() => window.__ann.stageOn(2)")),
        (44.8, A("() => window.__ann.stageOn(3)")),
        (49.5, A("() => window.__ann.stageOn(4)")),
        (52.9, shut),
    ])

    # -- setup B: rewind to the ripple example ---------------------------------------------------------------------------
    cover()
    js("() => window.__ann.stages(false, true)")      # under the sheet: gone at once, never seen leaving
    api("/api/examples/ripple", {})
    settle()
    sleep(2.5)
    ready("One event, five stages")

    rows = delta + ' g.row[data-id="delta.{}"]'
    take("B", 53.8, 83.2, [
        (53.8, away),
        (54.0, chapter("1 · Intake")),
        (54.1, lambda: glide("#btn-review", dur=0.6)),
        (54.8, lambda: glide("#btn-review", dur=0.05, click=True)),
        (56.0, A("(o) => window.__ann.underline(o)", {"id": "mark", "at": ".rv-article mark"})),
        (57.3, circle("oprow", ".rv-items .rv-item::Move Oil price@")),
        (57.6, bubble("op", "One phrase → one operation: move the oil price", ".rv-items .rv-item::Move Oil price@", side="right")),
        (59.0, snap("B-op")),
        (60.6, clear("mark", "oprow", "op")),
        (60.8, chapter("2 · Working memory")),
        (61.0, A("() => window.__ann.scrollTo('.rv-card .rv-scroll', '.rv-sec::The ripple')")),
        (62.2, A("(s) => window.__ann.rings(s)", oil)),
        (65.1, badge("o1", "1", rows.format("fuel_cost") + " rect.bg", side="left")),
        (65.15, arrow("a1", oil + " g.row rect.bg", "#vb-o1")),
        (66.2, badge("o2", "2", rows.format("operating_margin") + " rect.bg", side="left")),
        (67.1, badge("o3", "3", rows.format("share_price") + " rect.bg", side="left")),
        (68.2, snap("B-badges")),
        (69.0, clear("o1", "o2", "o3", "a1")),
        (69.1, chapter("3 · Long-term memory")),
        (69.2, A("() => window.__ann.scrollTo('.rv-card .rv-scroll', '.rv-sec::What recall brought back')")),
        (70.4, bubble("kinds", "Kinds update their statistics", "#rvg-long_term::Statistics update along$", side="right")),
        (71.3, bubble("rec", "An earlier oil shock, recalled", ".rv-sec h4 .small::from long-term memory$", side="right")),
        (72.6, snap("B-ltm")),
        (74.1, clear("kinds", "rec")),
        (74.2, chapter("4 · Review")),
        (74.3, A("() => window.__ann.scrollTo('.rv-card .rv-scroll', '.rv-sec::The ripple')")),
        (75.3, bubble("copy", "Staged on a copy: nothing has changed yet", "#rvg-review::Nothing has changed yet$", side="right")),
        (76.3, snap("B-copy")),
        (76.45, clear("copy")),
        (76.6, lambda: glide(".rv-rip [data-rip-conf]", dur=0.45, click=True)),
        (77.05, lambda: drag_to("[data-rip-p]", 0.97, 0.6, dur=0.6)),
        (78.2, bubble("leave", "Weigh each step, or leave it out", "[data-rip-reset]::as the analysis expects$", side="right")),
        (78.3, lambda: glide(".rv-rip input[data-rip]", dur=0.35, nth=2)),
        (79.85, snap("B-leave")),
        (79.95, clear("leave")),
        (80.0, chapter("5 · Commit")),
        (80.1, lambda: glide('.rv-actions [data-act="approve"]', dur=0.5)),
        (80.65, lambda: glide('.rv-actions [data-act="approve"]', dur=0.05, click=True)),
        (81.15, badge("ver", "+1", "#sim-version", side="right", dx=4)),
        (81.25, bubble("verb", "The next version", "#sim-version", side="bottom")),
        (82.25, snap("B-version")),
        (82.35, shut),
    ])

    # -- setup C: weeks later, the frontier example waiting -------------------------------------------------------------
    cover()
    approve_pending()
    api("/api/examples/frontier", {})
    settle()
    sleep(2.5)
    ready("Earned beliefs")

    take("C", 83.2, 97.5, [
        (83.2, away),
        (84.4, lambda: glide("#btn-review", dur=0.6)),
        (85.05, lambda: glide("#btn-review", dur=0.05, click=True)),
        # the graph settles into the lower part of the canvas, leaving the top clear for the notes
        # (after the app's own fit, which follows staging by 380 ms)
        (85.1, A("""() => { const t0 = performance.now(); const tick = () => {
            const b = document.querySelector('#staged-banner');
            if ((b && !b.classList.contains('hidden')) || performance.now() - t0 > 2500) {
              setTimeout(() => { const r = window.axelrod.renderer; r.zoom.fit(r.bounds(), 450, { pad: r.freePad({ top: 90, right: 30, bottom: 120, left: 420 }) }); window.__reframed = performance.now() - t0; }, 430);
            } else setTimeout(tick, 25); }; tick(); }""")),
        (86.55, lambda: print("reframed after", js("() => window.__reframed"), flush=True)),
        (86.6, bubble("pair", "Moves the graph couldn't explain, paired", ".rv-evidence h4::The articles behind it$", side="right")),
        (88.4, circle("checks", ".rv-evidence .ev-checks")),
        (88.6, bubble("spaced", "Re-checked, spaced apart", ".rv-evidence .ev-checks", side="right")),
        (90.2, circle("edgec", ".rv-head")),
        (90.4, bubble("edge", "…until it's proposed as an edge", ".rv-head", side="right")),
        (91.45, snap("C-frontier")),
        (91.6, clear("pair", "checks", "spaced", "edgec", "edge")),
        (91.7, close_left),
        (92.0, key("c")),
        (92.9, bubble("pane", "Every check, against its bound", ".checks .ck-row .ck-val::79%$", side="right")),
        (94.3, snap("C-checks")),
        (94.6, clear("pane")),
        (94.65, key("Escape")),
        (94.7, key("m")),
        (95.55, bubble("grow", "The kinds and groups, growing", "#drawer .tree .tnode::Airline@", side="right")),
        (96.6, snap("C-drawer")),
        (96.65, shut),
    ])

    # -- setup D: the nest example approved again ---------------------------------------------------------------------
    cover()
    js("() => { const d = document.querySelector('#drawer'); if (d?.classList.contains('open')) document.querySelector('#drawer-close')?.click(); }")
    approve_pending()
    api("/api/examples/nest", {})
    settle()
    approve_pending()
    sleep(2.5)
    js("() => window.axelrod.renderer.setDetail('entity')")
    sleep(1.2)
    ready("The key idea")

    take("D", 97.5, 115.6, [
        (97.5, away),
        (98.0, A("(o) => window.__ann.sticker(o.s, o.t, 1700)", {"s": "#canvas", "t": "The full tech stack: a separate video"})),
        (100.0, key("m")),
        (101.2, lambda: glide("#drawer .tree li .toggle", dur=0.5, nth=2)),
        (101.75, A("() => { const li = [...document.querySelectorAll('#drawer .tree li')].find((l) => l.querySelector(':scope > .tnode')?.textContent.trim().startsWith('Firm')); const t = li?.querySelector(':scope > .toggle'); if (t && t.textContent.trim() === '▸') t.click(); }")),
        (102.8, bubble("gen", "Generalizations: kinds, each with its own priors", "#drawer .tree .tnode::Airline@", side="right")),
        (104.2, snap("D-gen")),
        (104.4, clear("airline", "gen")),
        (104.45, A("() => document.querySelector('#drawer-close')?.click()")),
        (105.0, circle("comp", "g.hull-tab::Oil and rates@")),
        (105.2, bubble("compb", "Compositions: groups, and groups of groups", "g.hull-tab::Oil and rates@", side="right")),
        (106.6, snap("D-comp")),
        (107.3, clear("comp", "compb")),
        (107.5, A("(o) => window.__ann.headline(o)", {"id": "hd2", "text": "Brent jumps 12% on a new supply scare", "x": 1225, "y": 300})),
        (108.7, arrow("k1", "#vh-hd2", "g.hull-tab::Policy loop@")),
        (108.9, arrow("k2", "#vh-hd2", 'g.pill[data-id="alpenflug"] rect.body')),
        (109.4, bubble("both", "Read against kinds and groups, never from scratch", "#vh-hd2", side="bottom")),
        (110.9, snap("D-both")),
        (111.9, clear("hd2", "k1", "k2", "both")),
        (112.1, A("() => window.__ann.sheet('Thanks for watching', 'Axelrod World Model', 'internal devlog')")),
        (114.0, A("() => window.__ann.sheetText(true)")),
    ])
    if QC:
        LOG["qc"] = js("() => window.__qc.log") or []
    LOG["video"] = str(pg.video.path())
    ctx.close()
    b.close()
    (OUT / f"takes{TAG}.json").write_text(json.dumps(LOG, indent=1))
    print(json.dumps(LOG, indent=1))
