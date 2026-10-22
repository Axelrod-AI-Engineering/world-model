"""Footage for the external trailer (docs/media/EmilyVideo.m4a), one recording per shot, timed to the voiceover.

    uv run --with "playwright==1.58.0" python scripts/video/trailer/record.py OUT [SLOW] [shot ...]

The app shots drive Emily's demo on port 8777 (start it fresh: `uv run axelrod demo --scenario emily_demo --port 8777`);
the others are graphics.html and Emily's Oil-to-Portfolio Canvas (CANVAS, a local copy). Every shot opens with a
magenta flash that edit.py syncs on, and its actions are scheduled in voiceover seconds. Pages run SLOW times slower
(timers, animation frames, CSS animations) so the recorder keeps every frame; edit.py speeds them back up.
Emily's data is read from data/work/emily at record time and never written into the repository.
"""
import json
import math
import os
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from data import VO, scene_data  # noqa: E402

BASE = "http://127.0.0.1:8777"
OUT = Path(sys.argv[1]).resolve()
S = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
ONLY = set(sys.argv[3:])
CANVAS = Path(os.environ.get("EMILY_CANVAS", "")).resolve() if os.environ.get("EMILY_CANVAS") else None
GRAPHICS = (HERE / "graphics.html").as_uri()
W, H = 1600, 900
OUT.mkdir(parents=True, exist_ok=True)
LOG = {"slow": S, "shots": {}, "misses": []}

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

# the app, cleaned for the camera: no progress strip, captions, toasts, timeline, find, canvas controls, Admin, tooltips
CLEAN = """
#update-strip, #caption, #toast, #bottom, #search-box, #canvas-controls, #admin, #staged-banner, #gesture-hint, #empty-hint,
#isolate-banner, #predict-hint, #tooltip, .guide, #guide, .zoom-slider { display: none !important; }
#__cursor { position: fixed; z-index: 99999; width: 22px; height: 22px; pointer-events: none; left: -40px; top: -40px;
  transition: transform .12s; filter: drop-shadow(0 2px 3px rgba(0,0,0,.25)); }
#__cursor.down { transform: scale(.85); }
#__chip { position: fixed; z-index: 99990; left: 24px; bottom: 24px; font: 600 15px "IBM Plex Mono", monospace; letter-spacing: .14em;
  text-transform: uppercase; color: #4A3590; background: #DAD0F4; border: 1.5px solid #7C64C4; padding: 6px 14px; border-radius: 999px;
  opacity: 0; transition: opacity .4s; }
#__chip.in { opacity: 1; }
#__flash { position: fixed; inset: 0; z-index: 100000; background: #FF00FF; }
"""
CURSOR_SVG = ('<svg viewBox="0 0 22 22" width="22" height="22"><path d="M3 2 L3 18 L7.5 13.8 L10.6 20.4 L13.2 19.2 L10.2 12.8 L16.4 12.6 Z" '
              'fill="#2F2A25" stroke="#FFFDF8" stroke-width="1.4" stroke-linejoin="round"/></svg>')


def api(path, body=None, timeout=1800):
    req = urllib.request.Request(BASE + path, method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"null")


def settle():
    for _ in range(7200):
        if api("/api/sim/status")["state"] != "running":
            return
        time.sleep(0.25)


class Shot:
    def __init__(self, p, name, start):
        self.name, self.start = name, start
        self.ctx = p.chromium.launch().new_context(viewport={"width": W, "height": H}, record_video_dir=str(OUT / name),
                                                   record_video_size={"width": W, "height": H})
        self.ctx.add_init_script(SLOWDOWN)
        self.pg = self.ctx.new_page()
        self.cdp = self.ctx.new_cdp_session(self.pg)
        self.cdp.send("Animation.enable")
        self.cdp.send("Animation.setPlaybackRate", {"playbackRate": 1.0 / S})
        self.pos = [W * 0.62, 26.0]
        self.t0 = None

    def js(self, code, arg=None):
        try:
            return self.pg.evaluate(code, arg)
        except Exception as exc:  # noqa: BLE001
            LOG["misses"].append(f"{self.name}: {code[:60]}: {str(exc).splitlines()[0][:120]}")
            return None

    def dress(self, chip=None, cursor=True):
        self.js("(css) => { const s = document.createElement('style'); s.textContent = css; document.head.appendChild(s); }", CLEAN)
        if cursor:
            self.js("""(svg) => { const c = document.createElement('div'); c.id = '__cursor'; c.innerHTML = svg; document.body.appendChild(c);
              addEventListener('mousemove', (e) => { c.style.left = (e.clientX - 3) + 'px'; c.style.top = (e.clientY - 2) + 'px'; }, true);
              addEventListener('mousedown', () => c.classList.add('down'), true); addEventListener('mouseup', () => c.classList.remove('down'), true); }""",
                    CURSOR_SVG)
            self.pg.mouse.move(*self.pos)
        if chip:
            self.js("(t) => { const c = document.createElement('div'); c.id = '__chip'; c.textContent = t; document.body.appendChild(c); }", chip)

    def chip(self, text):
        self.js("""(t) => { const c = document.getElementById('__chip'); if (!c) return; c.classList.remove('in');
          setTimeout(() => { c.textContent = t; c.classList.add('in'); }, 250); }""", text)

    def flash(self):
        """The sync mark: magenta for a moment; the shot's voiceover time starts when it goes."""
        self.js("() => { const f = document.createElement('div'); f.id = '__flash'; document.body.appendChild(f); }")
        self.pg.wait_for_timeout(int(350 * S))
        self.js("() => document.getElementById('__flash')?.remove()")
        self.t0 = time.time()
        LOG["shots"][self.name] = {"vo_start": self.start}

    def until(self, vo):
        """Wait until this voiceover second (real speed)."""
        due = self.t0 + (vo - self.start) * S
        lag = time.time() - due
        if lag > 0.25 * S:
            LOG["misses"].append(f"{self.name}: {lag / S:.2f}s late for {vo}")
        if due > time.time():
            self.pg.wait_for_timeout(int((due - time.time()) * 1000))

    def glide(self, sel=None, x=None, y=None, dur=0.6, click=False, nth=0):
        if sel:
            b = self.js("""([s, n]) => { const el = document.querySelectorAll(s)[n]; if (!el) return null;
              el.scrollIntoView({block: 'nearest'}); const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }""", [sel, nth])
            if not b:
                LOG["misses"].append(f"{self.name}: glide {sel}")
                return False
            x, y = b
        x0, y0 = self.pos
        n = max(10, int(dur * S * 50))
        for i in range(1, n + 1):
            e = (i / n) ** 2 * (3 - 2 * i / n)
            bend = math.sin(math.pi * e) * 0.06 * math.hypot(x - x0, y - y0)
            self.pg.mouse.move(x0 + (x - x0) * e, y0 + (y - y0) * e - bend)
            self.pg.wait_for_timeout(int(dur * S * 1000 / n))
        self.pos = [x, y]
        if click:
            self.pg.mouse.down()
            self.pg.wait_for_timeout(int(90 * S))
            self.pg.mouse.up()
        return True

    def drag(self, sel, f0, f1, dur=0.9):
        r = self.js("(s) => { const el = document.querySelector(s); if (!el) return null; const b = el.getBoundingClientRect(); return [b.left, b.top, b.width, b.height]; }", sel)
        if not r:
            LOG["misses"].append(f"{self.name}: drag {sel}")
            return
        x, y, w, h = r
        self.glide(x=x + w * f0, y=y + h / 2, dur=0.35)
        self.pg.mouse.down()
        n = int(dur * S * 40)
        for i in range(1, n + 1):
            e = (i / n) ** 2 * (3 - 2 * i / n)
            self.pg.mouse.move(x + w * (f0 + (f1 - f0) * e), y + h / 2)
            self.pg.wait_for_timeout(int(dur * S * 1000 / n))
        self.pg.mouse.up()
        self.pos = [x + w * f1, y + h / 2]

    def slide(self, sel, v0, v1, dur=0.9):
        """Move a range input from v0 to v1 (0-100): its value is set step by step with input events, and the cursor
        rides along its thumb. A real drag loses the thumb when the review re-renders mid-way."""
        r = self.js("(s) => { const el = document.querySelector(s); if (!el) return null; const b = el.getBoundingClientRect(); return [b.left, b.top, b.width, b.height]; }", sel)
        if not r:
            LOG["misses"].append(f"{self.name}: slide {sel}")
            return
        x, y, w, h = r
        self.glide(x=x + w * v0 / 100, y=y + h / 2, dur=0.35)
        self.pg.mouse.down()
        n = int(dur * S * 25)
        for i in range(1, n + 1):
            e = (i / n) ** 2 * (3 - 2 * i / n)
            v = v0 + (v1 - v0) * e
            self.js("""([s, v]) => { const el = document.querySelector(s); if (!el) return; el.value = String(Math.round(v / 5) * 5);
              el.dispatchEvent(new Event('input', {bubbles: true})); }""", [sel, v])
            self.pg.mouse.move(x + w * v / 100, y + h / 2)
            self.pg.wait_for_timeout(int(dur * S * 1000 / n))
        self.pg.mouse.up()
        self.js("(s) => document.querySelector(s)?.dispatchEvent(new Event('change', {bubbles: true}))", sel)
        self.pos = [x + w * v1 / 100, y + h / 2]

    def typed(self, sel, text, dur):
        self.glide(sel, dur=0.3, click=True)
        for ch in text:
            self.pg.keyboard.type(ch)
            self.pg.wait_for_timeout(int(dur * S * 1000 / len(text)))

    def end(self, vo):
        self.until(vo)
        self.pg.wait_for_timeout(int(300 * S))
        path = self.pg.video.path()
        self.ctx.close()
        self.ctx.browser.close()
        LOG["shots"][self.name].update({"video": str(path), "vo_end": vo})
        (OUT / "shots.json").write_text(json.dumps(LOG, indent=1))


def app(p, name, start, chip=None, ready="() => window.axelrod?.store?.view?.entities?.length", cursor=True):
    s = Shot(p, name, start)
    s.pg.goto(BASE)
    s.pg.wait_for_function(ready, timeout=120000)
    s.pg.wait_for_timeout(int(2500 * S))
    # no guide over a forecast, and no transmission grid opening by itself (Predict's): the canvas shows the forecast
    s.js("() => { try { window.axelrod.guide?.setMode?.('off'); } catch (e) {} window.axelrod.store.settings.gridAuto = false; }")
    s.dress(chip, cursor=cursor)
    return s


def graphic(p, scene, start, end):
    s = Shot(p, scene, start)
    s.pg.add_init_script(f"window.__DATA = {json.dumps(scene_data(scene))};")
    s.pg.goto(f"{GRAPHICS}?scene={scene}")
    s.pg.wait_for_function("window.__ready")
    s.js("() => document.fonts.ready")
    s.pg.wait_for_timeout(int(600 * S))
    s.dress(cursor=False)
    s.flash()
    s.js("() => window.__go()")
    s.end(end)


# -- the shots ---------------------------------------------------------------------------------------------------
def shot_title(p):
    s = app(p, "title", VO["title"], cursor=False)
    s.js("""() => { const o = document.createElement('div'); o.id = '__title';
      o.innerHTML = '<div class="w">Axelrod <span>World Model</span></div><div class="s">A causal world model of the economy · the context layer for your agents</div>';
      o.style.cssText = 'position:fixed;inset:0;z-index:9000;display:grid;place-content:center;text-align:center;pointer-events:none;' +
        'background:radial-gradient(ellipse at center, rgba(251,248,242,.94) 0%, rgba(251,248,242,.80) 38%, rgba(251,248,242,0) 72%);opacity:0;transition:opacity .9s';
      const st = document.createElement('style'); st.textContent = `#__title .w{font:800 96px "Bricolage Grotesque";letter-spacing:-.03em;color:#2F2A25}
        #__title .w span{font-weight:500;color:#7C64C4}#__title .s{font:500 22px "Instrument Sans";color:#665E54;margin-top:10px;opacity:0;transition:opacity .9s}
        #__title.in .s{opacity:1}`; document.head.appendChild(st); document.body.appendChild(o); }""")
    s.js("() => window.axelrod.renderer.fit(0)")
    s.pg.wait_for_timeout(int(600 * S))
    s.flash()
    s.js("() => { const r = window.axelrod.renderer; const t = r.zoom.transform(); r.zoom.set({x: t.x - 60, y: t.y - 30, k: t.k * 1.07}, 6000); }")
    s.until(VO["title"] + 0.25)
    s.js("() => { const o = document.getElementById('__title'); o.style.opacity = 1; }")
    s.until(VO["title"] + 1.6)
    s.js("() => document.getElementById('__title').classList.add('in')")
    s.end(VO["old"])


def shot_old(p):
    """Emily's Oil-to-Portfolio Canvas: a slow scroll through its five layers."""
    s = Shot(p, "old", VO["old"])
    s.pg.goto(CANVAS.as_uri())
    s.pg.wait_for_timeout(int(3000 * S))
    s.dress(chip=None, cursor=False)
    s.js("""() => { const c = document.createElement('div'); c.id = '__chip'; c.textContent = 'Today, by hand'; document.body.appendChild(c); }""")
    s.flash()
    s.js("() => document.getElementById('__chip').classList.add('in')")
    dur = VO["import"] - VO["old"] - 0.8
    s.js("""(dur) => { const max = document.documentElement.scrollHeight - innerHeight; const t0 = performance.now();
      const ease = (t) => t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      const step = (now) => { const t = Math.min(1, (now - t0) / (dur * 1000)); scrollTo(0, max * ease(t)); if (t < 1) requestAnimationFrame(step); };
      requestAnimationFrame(step); }""", dur)
    s.end(VO["import"])


def shot_import(p):
    s = app(p, "import", VO["import"], chip="Import")
    s.flash()
    s.chip("Import")
    s.until(VO["import"] + 0.4)
    s.glide("#btn-import", dur=0.7, click=True)
    s.pg.wait_for_selector("[data-local]", timeout=30000)
    s.until(VO["import"] + 1.9)
    s.glide("[data-local]", dur=0.6, click=True)
    s.pg.wait_for_selector(".imp-row", timeout=60000)
    s.pg.wait_for_timeout(int(250 * S))
    s.glide("#import [data-max], .imp [data-max], [aria-label='Import'] [data-max]", dur=0.45, click=True) or \
        s.js("() => document.querySelector('.imp-list')?.closest('section, .manual, [role=dialog]')?.classList.add('win-max')")
    s.until(38.3)                                   # "Every item is dated"
    s.js("""() => { const l = document.querySelector('.imp-list'); const t0 = performance.now(); const go = (now) => {
      const t = Math.min(1, (now - t0) / 2600); l.scrollTop = 520 * t * t * (3 - 2 * t); if (t < 1) requestAnimationFrame(go); }; requestAnimationFrame(go); }""")
    s.until(40.2)                                   # "tied to the sentence that it came from"
    i = s.js("""() => { const rows = [...document.querySelectorAll('.imp-row [data-toggle]')]; const l = document.querySelector('.imp-list').getBoundingClientRect();
      return Math.max(0, rows.findIndex((b) => b.getBoundingClientRect().top > l.top + 120)); }""") or 0
    s.glide(".imp-row [data-toggle]", dur=0.5, click=True, nth=i)
    s.until(42.3)
    s.glide("[data-go]", dur=0.5)
    s.end(VO["trans"])


def go_to_ms_note():
    """Import Emily's bundle and approve, oldest first, up to Morgan Stanley's hawkish note."""
    if not api("/api/proposals?status=pending"):
        api("/api/import", {"bundle": api("/api/import/local/emily_import.json")})
        settle()
    for _ in range(80):
        pend = api("/api/proposals?status=pending")
        if not pend:
            raise SystemExit("ran out of proposals before the MS note")
        pid = pend[0]["proposal"]["id"]
        if "MS turns hawkish" in api(f"/api/proposals/{pid}/stage")["headline"]:
            return pid
        api(f"/api/proposals/{pid}/approve", {"by": "backend user"})
        settle()


LANE_COL = "(k) => { const r = window.axelrod.renderer; const c = r.lane?.cols?.[k]; if (c) r.frame(c.ids, {maxK: 1.0, duration: 900}); }"
LANE_ALL = "() => { const r = window.axelrod.renderer; if (r.lane) r.frame(r.lane.cols.flatMap((c) => c.ids), {maxK: 0.9, duration: 1000}); }"


def shot_learn(p):
    """Transmission, review, and memory, as one take on the MS note."""
    go_to_ms_note()
    s = app(p, "learn", VO["trans"], chip="Transmission",
            ready="() => window.axelrod?.store?.view?.entities?.length && document.body.classList.contains('laned')")
    s.js("() => window.axelrod.renderer.fit(0)")
    s.pg.wait_for_timeout(int(800 * S))
    s.flash()
    s.chip("Transmission")
    s.until(44.0)                                   # "Morgan Stanley turns hawkish on the Fed"
    s.glide(".rv-article mark", dur=0.7)
    s.until(46.4)
    s.glide(".rv-title", dur=0.5)
    s.until(47.1)                                   # "Axelrod traces this through its model"
    s.js(LANE_COL, 0)
    s.until(49.6)                                   # "Treasury yields and the dollar"
    s.js(LANE_COL, 1)
    s.until(54.2)                                   # "then Tokio Marine, Toyota, and Zurich"
    s.js(LANE_COL, 2)
    s.until(56.8)                                   # "First, second, and third order effects on just one screen"
    s.js(LANE_ALL)
    s.until(60.5)                                   # "Nothing changes without you"
    s.chip("Review")
    s.js("""() => { const b = document.getElementById('review-body'); const h = [...b.querySelectorAll('.rv-sec h4')].find((x) => x.textContent.includes('ripple'));
      if (h) b.scrollTo({top: h.getBoundingClientRect().top - b.getBoundingClientRect().top + b.scrollTop - 10, behavior: 'smooth'}); }""")
    s.until(64.4)                                   # "keep what makes sense and drop what doesn't"
    s.glide(".rv-rip input[data-rip]", dur=0.6, click=True, nth=6)
    s.until(67.6)                                   # "even adjusting the confidence"
    s.glide(".rv-rip [data-rip-conf]", dur=0.5, click=True, nth=2)
    s.pg.wait_for_selector("[data-rip-p]", timeout=10000)
    s.slide("[data-rip-p]", 100, 55, dur=0.9)
    s.until(69.6)
    s.glide('[data-act="approve"]', dur=0.5, click=True)
    s.until(70.6)                                   # "And using this, Axelrod's able to learn"
    s.chip("Memory")
    s.pg.keyboard.press("m")
    s.until(72.0)                                   # "which companies move together"
    s.glide('[data-mtab="object"]', dur=0.5, click=True)
    s.until(74.6)                                   # "how each central bank has acted before"
    s.glide('[data-mtab="entity_memories"]', dur=0.5, click=True)
    s.pg.wait_for_timeout(int(500 * S))
    s.glide('[data-em="boj"]', dur=0.5, click=True) or s.glide('[data-em]', dur=0.5, click=True)
    s.until(77.4)                                   # "which events and co-movements looked like what's happened today"
    s.glide('[data-mtab="prior"]', dur=0.5, click=True)
    s.until(78.7)
    s.glide('[data-mtab="frontier"]', dur=0.4, click=True)
    s.until(79.8)                                   # "Every new article is read in that context"
    s.glide("#drawer-close", dur=0.5, click=True)
    s.js("""() => { const b = document.getElementById('review-body'); const g = b.querySelector('#rvg-long_term');
      if (g) b.scrollTo({top: g.getBoundingClientRect().top - b.getBoundingClientRect().top + b.scrollTop - 10, behavior: 'smooth'}); }""")
    s.end(VO["ask"])


def shot_ask(p):
    s = app(p, "ask", VO["ask"], chip="Ask")
    s.flash()
    s.chip("Ask")
    s.until(84.2)                                   # "Then you're able to ask Axelrod anything"
    s.glide("#mode-predict", dur=0.6, click=True)
    s.pg.wait_for_timeout(int(500 * S))
    if not s.js("() => !!document.querySelector('#th-q') && document.querySelector('#th-q').offsetParent !== null"):
        s.glide("#btn-ask", dur=0.4, click=True)
    s.js("() => { const q = document.querySelector('#th-q'); if (q) q.value = ''; }")
    s.until(86.7)                                   # "What if the yen carry trade unwinds?"
    s.typed("#th-q", "What if the yen carry trade unwinds?", 1.4)
    s.until(88.4)
    s.glide("#th-ask", dur=0.35, click=True)
    s.end(VO["meta"])


def shot_end(p):
    s = Shot(p, "end", VO["end"])
    s.pg.add_init_script("window.__DATA = {};")
    s.pg.goto(f"{GRAPHICS}?scene=end")
    s.pg.wait_for_function("window.__ready")
    s.js("() => document.fonts.ready")
    s.pg.wait_for_timeout(int(500 * S))
    s.dress(cursor=False)
    s.flash()
    s.js("() => window.__go()")
    s.end(VO["total"])


SHOTS = [("open", lambda p: graphic(p, "open", VO["open"], VO["title"])), ("title", shot_title), ("old", shot_old),
         ("import", shot_import), ("learn", shot_learn), ("ask", shot_ask),
         ("meta", lambda p: graphic(p, "meta", VO["meta"], VO["stack"])),
         ("stack", lambda p: graphic(p, "stack", VO["stack"], VO["end"])), ("end", shot_end)]

if __name__ == "__main__":
    prev = OUT / "shots.json"
    if prev.exists():
        LOG["shots"] = json.loads(prev.read_text()).get("shots", {})
    with sync_playwright() as p:
        for name, fn in SHOTS:
            if ONLY and name not in ONLY:
                continue
            t = time.time()
            fn(p)
            print(f"{name}: {time.time() - t:.0f}s", flush=True)
    (OUT / "shots.json").write_text(json.dumps(LOG, indent=1))
    print("misses:", *LOG["misses"], sep="\n  ")
