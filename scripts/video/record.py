"""Record the demo video's raw footage: one continuous session on the small demo, slow and methodical, with on-screen
text and a visible cursor. Waits (an example playing its predecessors) are cut later: segments to keep are logged with
their start and end times in the recording."""
import json
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8766"
OUT = Path(__file__).parent
SEGS = []

INJECT = r"""
(() => {
  if (window.__vid) return; window.__vid = true;
  const st = document.createElement('style');
  st.textContent = `
  #vcap{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);z-index:9999;pointer-events:none;padding:22px 34px 24px;border-radius:20px;
    background:rgba(47,42,37,.90);color:#FFFDF8;text-align:center;opacity:0;transition:opacity .8s ease;box-shadow:0 18px 50px rgba(0,0,0,.22);max-width:820px}
  #vcap.low{top:auto;bottom:70px;transform:translateX(-50%)}
  #vcap.on{opacity:1}
  #vcap .s{font:600 12.5px "IBM Plex Mono",monospace;letter-spacing:.16em;text-transform:uppercase;color:#C9B8F2;margin-bottom:8px}
  #vcap .t{font:600 34px "Bricolage Grotesque",system-ui;line-height:1.15}
  #vcap .u{font:400 16.5px "Instrument Sans",system-ui;color:#E8E1D6;margin-top:10px;line-height:1.4}
  #vtitle{position:fixed;inset:0;z-index:10001;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;
    background:#FBF8F2;opacity:0;transition:opacity 1s ease;pointer-events:none}
  #vtitle.on{opacity:1}
  #vtitle .b{font:700 64px "Bricolage Grotesque",system-ui;color:#2F2A25;letter-spacing:-.01em}
  #vtitle .b span{color:#7C64C4}
  #vtitle .l{font:400 22px "Instrument Sans",system-ui;color:#665E54}
  #vtitle .m{font:500 13px "IBM Plex Mono",monospace;color:#93897C;letter-spacing:.14em;text-transform:uppercase;margin-top:18px}
  #vcur{position:fixed;z-index:10000;width:18px;height:18px;margin:-2px 0 0 -2px;pointer-events:none;transition:transform .12s ease}
  #vcur.down{transform:scale(.82)}
  `;
  document.head.appendChild(st);
  const cur = document.createElement('div'); cur.id = 'vcur';
  cur.innerHTML = '<svg viewBox="0 0 18 18" width="18" height="18"><path d="M2 1.5L2 15L5.8 11.4L8.4 16.6L10.8 15.4L8.2 10.3L13.4 10.1Z" fill="#2F2A25" stroke="#FFFDF8" stroke-width="1.3" stroke-linejoin="round"/></svg>';
  document.body.appendChild(cur);
  document.addEventListener('mousemove', (e) => { cur.style.left = e.clientX + 'px'; cur.style.top = e.clientY + 'px'; }, true);
  document.addEventListener('mousedown', () => cur.classList.add('down'), true);
  document.addEventListener('mouseup', () => cur.classList.remove('down'), true);
  const cap = document.createElement('div'); cap.id = 'vcap'; document.body.appendChild(cap);
  const ttl = document.createElement('div'); ttl.id = 'vtitle'; document.body.appendChild(ttl);
  window.__cap = (s, t, u, low) => { cap.innerHTML = `<div class="s">${s}</div><div class="t">${t}</div>${u ? `<div class="u">${u}</div>` : ''}`; cap.classList.toggle('low', !!low); cap.classList.add('on'); };
  window.__capOff = () => cap.classList.remove('on');
  window.__title = (b, l, m) => { ttl.innerHTML = `<div class="b">${b}</div><div class="l">${l}</div>${m ? `<div class="m">${m}</div>` : ''}`; ttl.classList.add('on'); };
  window.__titleOff = () => ttl.classList.remove('on');
  // keep the hints and the shortcut toast out of the footage
  const hide = document.createElement('style'); hide.textContent = '#gesture-hint,.hint-toast,#toast{display:none!important}'; document.head.appendChild(hide);
})();
"""


def api(path, body=None):
    req = urllib.request.Request(BASE + path, method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read() or b"null")


def settle():
    for _ in range(1200):
        if api("/api/sim/status")["state"] != "running":
            return
        time.sleep(0.25)


def close_left(pg):
    btn = pg.locator('[data-close-panel="left"]')
    if btn.is_visible():
        btn.click()
        pg.wait_for_timeout(500)


def pending():
    return [p["proposal"]["id"] for p in api("/api/proposals?status=pending")]


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, record_video_dir=str(OUT / "raw"),
                        record_video_size={"width": 1440, "height": 900}, device_scale_factor=1)
    pg = ctx.new_page()
    T0 = time.time()
    now = lambda: time.time() - T0  # noqa: E731
    seg = {}

    def keep(name):
        seg["name"], seg["t"] = name, now()

    def done():
        SEGS.append({"name": seg["name"], "start": round(seg["t"], 2), "end": round(now(), 2)})

    def cap(s, t, u="", low=False, hold=0.0):
        pg.evaluate("([s,t,u,l]) => window.__cap(s,t,u,l)", [s, t, u, low])
        if hold:
            pg.wait_for_timeout(int(hold * 1000))

    def cap_off(hold=0.8):
        pg.evaluate("() => window.__capOff()")
        pg.wait_for_timeout(int(hold * 1000))

    def glide(sel=None, x=None, y=None, click=False, steps=30, pause=350, nth=0):
        if sel:
            box = pg.locator(sel).nth(nth).bounding_box()
            x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        pg.mouse.move(x, y, steps=steps)
        pg.wait_for_timeout(pause)
        if click:
            pg.mouse.down(); pg.wait_for_timeout(90); pg.mouse.up()
            pg.wait_for_timeout(250)

    pg.goto(BASE)
    pg.evaluate("() => { localStorage.setItem('axelrod.hinted', '1'); localStorage.setItem('axelrod.guide.mode', '\"off\"'); localStorage.setItem('axelrod.colorBy', 'change'); localStorage.setItem('axelrod.autoDetail', '1'); }")
    pg.reload(); pg.wait_for_timeout(3000)
    pg.evaluate(INJECT)
    pg.mouse.move(720, 640)

    # -- 0. title -----------------------------------------------------------------------------------------------
    keep("title")
    pg.evaluate("() => window.__title('Axelrod <span>World Model</span>', 'A model of the economy that learns from the news, one reviewed step at a time', 'synthetic data · a demo')")
    pg.wait_for_timeout(4200)
    pg.evaluate("() => window.__titleOff()")
    pg.wait_for_timeout(1100)
    done()

    # -- 1. an article arrives ------------------------------------------------------------------------------------
    keep("article")
    cap("1 · Intake", "It starts from nothing", "An empty graph. Each example is one article.", hold=2.6)
    cap_off(0.5)
    glide("#btn-examples", click=True)
    pg.wait_for_timeout(900)
    glide('#examples [data-run="create"]', click=False, pause=500)
    done()
    pg.locator('#examples [data-run="create"]').click()
    pg.wait_for_selector(".rv-card .rv-article", timeout=240000)
    settle()
    pg.wait_for_timeout(1500)
    keep("review")
    glide(".rv-article mark", pause=900)
    cap("1 · Intake", "An article becomes changes to the graph", "Each marked phrase asks for one change.", low=True, hold=3.4)
    cap_off(0.4)
    cap("2 · Learning", "Learning runs on a copy first", "Working memory, then long-term memory. Nothing is committed yet.", low=True, hold=3.6)
    cap_off(0.4)
    cap("3 · Review", "A person approves", "Every change waits for review.", low=True, hold=2.0)
    glide('.rv-actions [data-act="approve"]', click=True, pause=500)
    pg.wait_for_timeout(2600)
    cap_off(0.6)
    done()

    # -- 2. a shock ripples ---------------------------------------------------------------------------------------
    pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
    pg.locator("#btn-examples").click(); pg.wait_for_timeout(600)
    pg.locator('#examples [data-run="ripple"]').click()
    pg.wait_for_selector(".rv-rip", timeout=600000)
    settle()
    pg.wait_for_timeout(2500)
    keep("ripple")
    cap("4 · The ripple", "A shock travels through the graph", "Oil moves Delta's fuel cost, then its margin, then its shares: first, second, third order.", low=True, hold=4.2)
    cap_off(0.4)
    pg.locator(".rv-sec:has(.rv-rip)").first.scroll_into_view_if_needed()
    pg.wait_for_timeout(800)
    glide(".rv-rip [data-rip-conf]", click=True, pause=500)
    sl = pg.locator("[data-rip-p]").first
    bb = sl.bounding_box()
    pg.mouse.move(bb["x"] + bb["width"] * 0.98, bb["y"] + bb["height"] / 2, steps=12)
    pg.mouse.down()
    pg.mouse.move(bb["x"] + bb["width"] * 0.6, bb["y"] + bb["height"] / 2, steps=40)
    pg.mouse.up()
    cap("4 · The ripple", "Even the ripple can be weighed", "A reviewer gives the probability it arrives.", low=True, hold=3.6)
    glide('.rv-actions [data-act="approve"]', click=True, pause=400)
    pg.wait_for_timeout(1800)
    cap_off(0.5)
    done()

    # -- 3. evidence, check by check ------------------------------------------------------------------------------
    pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
    api("/api/examples/frontier", {})
    settle()
    for pid in pending():
        api(f"/api/proposals/{pid}/approve", {"by": "backend user"})
    settle()
    pg.keyboard.press("Escape"); pg.keyboard.press("Escape")
    pg.wait_for_timeout(3000)
    close_left(pg)
    pg.locator("#btn-fit").click(); pg.wait_for_timeout(1200)
    keep("checks")
    cap("5 · Checks", "Belief is earned, check by check", "Weeks of articles later: fuzzy ends, co-movements, and recurring groups, each tested again and again.", low=True, hold=3.8)
    cap_off(0.3)
    pg.keyboard.press("c")
    pg.wait_for_timeout(2600)
    glide(".ck-item", pause=900)
    pg.mouse.wheel(0, 260); pg.wait_for_timeout(1400)
    cap("5 · Checks", "Past its bound, a check raises a proposal", "Nothing changes the structure until a person reviews it.", low=True, hold=3.2)
    cap_off(0.4)
    pg.keyboard.press("Escape"); pg.wait_for_timeout(600)
    done()

    # -- 4. structure: superentities within superentities ---------------------------------------------------------
    api("/api/examples/nest", {})
    settle()
    for pid in pending():
        api(f"/api/proposals/{pid}/approve", {"by": "backend user"})
    settle()
    pg.keyboard.press("Escape"); pg.keyboard.press("Escape")
    pg.wait_for_timeout(2500)
    close_left(pg)
    pg.locator("#btn-fit").click(); pg.wait_for_timeout(1200)
    keep("structure")
    cap("6 · Long-term memory", "It finds structure", "Groups that act as one become superentities, and superentities nest.", low=True, hold=3.6)
    cap_off(0.3)
    glide("#levels .lv-step", click=True, pause=600)      # World: everything closes into cards
    pg.wait_for_timeout(1800)
    glide("#levels .lv-chip", click=True, pause=600)      # Oil and rates: its parts
    pg.wait_for_timeout(2200)
    glide("#levels .lv-chip", click=True, pause=600, nth=0)   # a part
    pg.wait_for_timeout(2000)
    cap("6 · Long-term memory", "One level at a time", "World › Oil and rates › Policy loop", low=True, hold=2.6)
    cap_off(0.4)
    done()

    # -- 5. what it does not know --------------------------------------------------------------------------------
    pg.locator("#lvl-entity").click(); pg.wait_for_timeout(1500)
    pg.locator("#btn-fit").click(); pg.wait_for_timeout(1200)
    keep("open")
    glide("#btn-color", click=True, pause=500)
    glide('input[value="open"]', click=True, pause=700)
    glide("#btn-color", click=True, pause=300)
    pg.wait_for_timeout(600)
    glide('g.pill[data-id="federal_reserve"]', pause=1400)
    cap("7 · Open nodes", "It shows what it cannot explain yet", "Every node keeps a share for causes not in the graph. Amber marks the blind spots.", low=True, hold=3.8)
    cap_off(0.4)
    done()

    # -- end ------------------------------------------------------------------------------------------------------
    keep("end")
    pg.evaluate("() => window.__title('Every change reviewed.<br>Every version kept.', 'Axelrod World Model', 'small demo · synthetic data')")
    pg.wait_for_timeout(4200)
    done()
    video = pg.video.path()
    ctx.close()
    b.close()
    (OUT / "segments.json").write_text(json.dumps({"video": str(video), "segments": SEGS}, indent=1))
    print(json.dumps(SEGS, indent=1))
