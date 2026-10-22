"""Optional browser smoke test (§15.4). Runs only with --runslow and when Playwright and Chromium are
installed locally; Playwright is not a project dependency."""

from __future__ import annotations

import socket
import threading
import time

import pytest

from axelrod_wm.repo.snapshots import MemoryBackend


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server():
    import uvicorn

    from axelrod_wm.api.app import create_app

    port = _free_port()
    app = create_app(scenario="oil_shock_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    t0 = time.time()
    while not srv.started and time.time() - t0 < 300:
        time.sleep(0.2)
    yield f"http://127.0.0.1:{port}/"
    srv.should_exit = True
    th.join(timeout=10)


def settled_box(page, locator, tries: int = 40):
    """The element's box once it has stopped moving (two reads 100 ms apart agree)."""
    prev = None
    for _ in range(tries):
        box = locator.bounding_box()
        if box and prev and abs(box["x"] - prev["x"]) < 0.5 and abs(box["y"] - prev["y"]) < 0.5:
            return box
        prev = box
        page.wait_for_timeout(100)
    return prev


def _zoom_to(page, target, pause=60, step=40):
    """Wheel the canvas toward a zoom, a notch at a time (as a person does); True once within 4% of it."""
    for _ in range(300):
        k = page.evaluate("() => window.axelrod.renderer.zoom.transform().k")
        if (k <= target * 1.04) if target < k else (k >= target / 1.04):
            return True
        page.mouse.wheel(0, step if target < k else -step)
        page.wait_for_timeout(pause)
    return False


@pytest.mark.slow
def test_a_large_model_reads_as_superentities_that_open_as_the_view_closes_in(server):
    """Semantic zoom (Oct 22): the oil world has 53 entities, enough to be grouped. In the gravity layout it opens as
    superentity boxes with their keywords, entities appear as the view comes in and fold away as it goes out, nothing
    toggles back and forth around one zoom, and a box opens by click."""
    sync_api = pytest.importorskip("playwright.sync_api")
    errors: list[str] = []
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # Chromium not installed
            pytest.skip(f"no Chromium: {exc}")
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(server)
        page.wait_for_selector("g.pill", timeout=60000)
        page.wait_for_timeout(1500)
        # Figure 1's hand-placed layout keeps every entity a pill; the gravity layout groups
        assert page.locator("g.pill").count() == 53 and page.locator("g.cnode").count() == 0
        page.evaluate("() => window.axelrod.renderer.setLayoutMode('gravity')")
        page.wait_for_selector("g.cnode", timeout=20000)
        page.wait_for_timeout(2500)
        boxes, pills = page.locator("g.cnode").count(), page.locator("g.pill").count()
        assert boxes >= 3 and boxes + pills <= 40                 # a few boxes and the entities near the middle, not all 53
        # every box is named by its keywords, and no two siblings share a name
        names = page.locator("g.cnode text.cname").all_text_contents()
        assert all(names) and len(set(names)) == len(names)
        assert page.locator("#lvl-super").is_visible()
        # zooming in reveals members, and zooming out folds them
        page.mouse.move(800, 520)
        assert _zoom_to(page, 2.2)
        page.wait_for_timeout(1200)
        zoomed = page.locator("g.pill").count()
        assert _zoom_to(page, 0.3)
        page.wait_for_timeout(1500)
        assert page.locator("g.cnode").count() >= boxes - 1 and page.locator("g.pill").count() < zoomed
        # hysteresis: swing the zoom a few percent each way at several zooms; the cut does not change on the swings
        page.evaluate("""() => {
          const r = window.axelrod.renderer, m = window.__changes = { n: 0, last: null };
          const read = () => JSON.stringify([...r.sem.clusters().keys()].filter((i) => r.sem.isOpen(i)).sort());
          m.last = read();
          window.__poll = setInterval(() => { const now = read(); if (now !== m.last) { m.n += 1; m.last = now; } }, 25);
        }""")
        for k0 in (0.45, 0.8, 1.4):
            assert _zoom_to(page, k0)
            page.wait_for_timeout(1500)
            page.evaluate("() => { window.__changes.n = 0; }")
            for _ in range(5):
                page.mouse.wheel(0, -20)
                page.wait_for_timeout(250)
                page.mouse.wheel(0, 20)
                page.wait_for_timeout(250)
            page.wait_for_timeout(800)
            assert page.evaluate("() => window.__changes.n") <= 1, k0
        # a slow zoom in only ever opens boxes (no box opens and closes in one run)
        assert _zoom_to(page, 0.25)
        page.wait_for_timeout(1500)
        page.evaluate("""() => { window.__changes.n = 0; const r = window.axelrod.renderer; window.__seen = new Map();
          clearInterval(window.__poll);
          window.__poll = setInterval(() => { for (const i of r.sem.clusters().keys()) {
            const was = window.__seen.get(i) ?? [r.sem.isOpen(i), 0], now = r.sem.isOpen(i);
            if (now !== was[0]) was[1] += 1; was[0] = now; window.__seen.set(i, was); } }, 25); }""")
        assert _zoom_to(page, 3.0, pause=90, step=30)
        page.wait_for_timeout(1500)
        flips = page.evaluate("() => [...window.__seen.values()].filter((v) => v[1] > 1).length")
        assert flips == 0
        page.evaluate("() => clearInterval(window.__poll)")
        # the three detail buttons: superentities (3), entities (1)
        page.keyboard.press("3")
        page.wait_for_timeout(1200)
        assert page.locator("g.pill").count() == 0 and page.locator("g.cnode").count() >= 3
        # a box opens by click (its parts show where its members sit); right-click offers its options
        box = page.locator("g.cnode").first
        box.click(button="right")
        page.wait_for_selector(".ctx-menu")
        assert page.locator(".ctx-menu button:has-text('Open it into its parts')").count() == 1
        assert page.locator(".ctx-menu button:has-text('Zoom to it')").count() == 1
        page.keyboard.press("Escape")
        before = page.locator("g.cnode").count()
        page.locator("g.cnode").first.click()
        page.wait_for_timeout(1500)
        assert page.locator("g.pill").count() >= 1 or page.locator("g.cnode").count() != before
        page.keyboard.press("1")
        page.wait_for_timeout(1200)
        assert page.locator("g.pill").count() == 53 and page.locator("g.cnode").count() == 0
        browser.close()
    assert not errors, errors


@pytest.mark.slow
def test_the_demo_loads_opens_nodes_and_steps(server):
    sync_api = pytest.importorskip("playwright.sync_api")
    errors: list[str] = []
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # Chromium not installed
            pytest.skip(f"no Chromium: {exc}")
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(server)
        page.wait_for_selector("g.pill", timeout=60000)
        page.wait_for_timeout(1500)
        # the guide is tested once, on the first forecast below; start from "first time" mode
        page.evaluate("() => { localStorage.removeItem('axelrod.guide.seen'); localStorage.removeItem('axelrod.guide.mode'); }")
        # the first view: Figure 1's entities, no subentities, panels closed. Superentities are not drawn (Oct 17): no
        # outlines, tabs, cards, ownership stripes, tethers, or lenses
        assert page.locator("g.pill").count() == 53
        for sel in ("g.hull", "g.hull-tab", "g.card-super", ".owners rect", "g.tether", "g.lens", "g.row .marks rect"):
            assert page.locator(sel).count() == 0, sel
        assert page.locator("g.row").count() == 0
        assert page.locator("#right-panel").is_hidden() and page.locator("#left-panel").is_hidden()
        # no categories widget on the canvas: they live in the Admin window, which starts minimized
        assert page.locator("#key").count() == 0
        assert "minimized" in (page.locator("#admin").get_attribute("class") or "")
        # the World path lists the taxonomy's top concepts, not superentities
        assert page.locator("#levels .lv-chip.concept").count() >= 2
        # the zoom slider: + moves the thumb; a little zoom opens nothing (values open past the learned threshold)
        before = int(page.locator("#zoom-range").input_value())
        page.click(".zs-step[data-step='1.25']")
        page.wait_for_timeout(600)
        assert int(page.locator("#zoom-range").input_value()) > before
        assert page.locator("g.row").count() == 0
        # one more step passes the threshold: the few entities in the middle of the view open, not all of them
        page.click(".zs-step[data-step='1.25']")
        page.wait_for_timeout(800)
        assert 0 < page.locator("g.row").count() < 40
        # detail presets (Oct 17: 1 entities, 2 subentities)
        page.keyboard.press("2")
        page.wait_for_timeout(1200)
        assert page.locator("g.row").count() == 159
        # each value shows its mean in its own unit, not a move in sd (that is in its hover card)
        assert not any(t.endswith(" sd") for t in page.locator("g.row text.rz").all_text_contents())
        # similar objects have similar subentities: hovering United's jet fuel cost lights Delta's (its kin)
        assert page.locator('g.pill[data-id="delta"] text.rname').all_text_contents() == \
            page.locator('g.pill[data-id="united_airlines"] text.rname').all_text_contents()
        # (mouseenter and mouseleave do not bubble in a browser; dispatch_event bubbles unless told not to)
        page.locator('g.row[data-id="united_airlines.fuel_cost"]').dispatch_event("mouseenter", {"bubbles": False})
        assert page.locator('g.row.kin[data-id="delta.fuel_cost"]').count() == 1
        page.locator('g.row[data-id="united_airlines.fuel_cost"]').dispatch_event("mouseleave", {"bubbles": False})
        assert page.locator(".kin").count() == 0
        page.keyboard.press("1")
        page.wait_for_timeout(1200)
        assert page.locator("g.row").count() == 0
        # undo and redo a view change
        page.keyboard.press("Control+z")
        page.wait_for_timeout(1200)
        assert page.locator("g.row").count() == 159
        page.keyboard.press("Control+y")
        page.wait_for_timeout(1200)
        assert page.locator("g.row").count() == 0
        # every shortcut on one sheet
        page.keyboard.press("?")
        page.wait_for_selector(".modal .keys")
        page.keyboard.press("Escape")
        page.keyboard.press("1")
        page.wait_for_timeout(1200)
        assert page.locator("g.pill").count() == 53 and page.locator("g.row").count() == 0
        # right-click opens one entity's subentities
        page.click('g.pill[data-id="inflation"]', button="right")
        page.wait_for_selector(".ctx-menu")
        page.click(".ctx-menu button:has-text('Show its subentities')")
        page.wait_for_timeout(800)
        assert page.locator('g.pill[data-id="inflation"] g.row').count() == 2
        # its superentities are listed in its menu, not drawn
        page.click('g.pill[data-id="nvidia"]', button="right")
        page.wait_for_selector(".ctx-menu")
        assert page.locator(".ctx-menu button:has-text('Close it into one card')").count() == 0
        page.keyboard.press("Escape")
        # an actor's values, each with a small picture of its distribution
        page.click('g.pill[data-id="delta"]')
        page.wait_for_selector("#tab-inspector details.subrow svg.density", timeout=20000)
        # what to forecast: chips that wrap, at every granularity
        page.keyboard.press("q")
        page.wait_for_selector("#tab-thesis .pick.actor")
        assert page.locator("#tab-thesis .pick.sector").count() >= 1
        # asking: the Forecast tab shows progress at once, and the guide (first time, in Learn) narrates. When the
        # forecast is in, the brief does not open by itself (Oct 14): one small prompt offers it
        page.click("#th-ask")
        page.wait_for_selector("#tab-forecast .progress-card", timeout=20000)
        page.wait_for_selector("#guide:not(.hidden) .bubble", timeout=20000)
        page.wait_for_selector(".brief-nudge:not(.hidden)", timeout=180000)
        assert page.locator("#left-panel").is_hidden() or page.locator("#left-panel").get_attribute("data-tab") != "briefs"
        page.click(".brief-nudge [data-bn-open]")
        page.wait_for_selector("#left-panel:not([hidden]) .brief h3", timeout=60000)
        text = page.locator(".brief").inner_text().lower()
        # its sections (renamed Oct 15: the bottom line reads "Summary", the timeline "Expected timing")
        assert "summary" in text and "transmission path" in text and "expected timing" in text
        # selecting text in the brief offers a chat, which is a labeled mock-up. Panels slide in and the brief settles its
        # layout after it opens (Oct 14), so the drag waits until the line stops moving
        box = settled_box(page, page.locator(".brief .lede").first)
        page.mouse.move(box["x"] + 3, box["y"] + 6)
        page.mouse.down()
        page.mouse.move(box["x"] + 200, box["y"] + 8)
        page.mouse.up()
        page.wait_for_selector(".ask-sel:not(.hidden)")
        page.click(".ask-sel")
        page.wait_for_selector("#chat:not(.hidden)")
        assert "not implemented yet" in page.locator("#chat").inner_text().lower()
        page.keyboard.press("Escape")
        page.keyboard.press("Escape")
        page.keyboard.press("Escape")
        # the Admin window: story, map (with the categories), view, settings (with the guide switch)
        page.locator("#canvas").focus()
        page.keyboard.press(",")
        page.click('#admin [data-tab="map"]')
        assert page.locator("#admin .cat").count() == 8
        page.click('#admin [data-tab="settings"]')
        page.click('#admin [data-guide="off"]')
        assert page.evaluate("() => window.axelrod.guide.mode") == "off"
        page.click('#admin [data-a="min"]')
        # how it works, from the top bar: learning (five stages), then inference (seven, MECE), then the literature
        page.click("#btn-methods")
        page.wait_for_selector("#methods .fc-stage", timeout=20000)
        assert page.locator("#methods .fc-stage").count() == 5
        page.wait_for_selector("#methods figure.stage-flow svg", timeout=20000)
        assert page.locator("#methods figure.stage-flow").count() == 5
        page.click('#methods [data-mtab="inference"]')
        page.wait_for_selector("#methods figure.stage-flow[data-flow='inf-pose'] svg", timeout=20000)
        assert page.locator("#methods .fc-stage.st-inference").count() == 7
        page.click('#methods [data-mtab="literature"]')
        page.wait_for_selector("#methods .doc ol.refs li", timeout=20000)
        assert page.locator("#methods .doc ol.refs li").count() >= 40
        page.keyboard.press("Escape")
        # two scripted steps (the second reads the Fed's decision), then walk through it. Asking moved the app to
        # Predict, where the step keys only say to switch back (they learn), so step from Learn
        page.click("#mode-learn")
        page.locator("#canvas").focus()
        # the label shows the step on screen (from its start); the Step button comes back when it has finished
        done = "(n) => document.querySelector('#step-label').textContent.startsWith(n + ' /') && !document.querySelector('#btn-step').disabled"
        page.keyboard.press("ArrowRight")
        page.wait_for_function(done, arg=1, timeout=120000)
        page.keyboard.press("ArrowRight")
        page.wait_for_function(done, arg=2, timeout=180000)
        page.wait_for_selector("#caption .walks button", timeout=60000)
        page.click("#caption .walks button")
        page.wait_for_selector("#walkthrough .walk-body h4")
        first = page.locator("#walkthrough .walk-body h4").text_content()
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(500)
        assert page.locator("#walkthrough .walk-body h4").text_content() != first
        page.keyboard.press("Escape")
        page.wait_for_selector("#walkthrough", state="hidden", timeout=5000)   # it slides out (Oct 14)
        # the memory drawer
        page.click("#btn-menu")
        page.click("#btn-memory")
        page.wait_for_selector("#drawer .tnode", timeout=20000)
        browser.close()
    assert not errors, errors


@pytest.fixture(scope="module")
def tutorial_server():
    import uvicorn

    from axelrod_wm.api.app import create_app

    port = _free_port()
    app = create_app(scenario="small_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    t0 = time.time()
    while not srv.started and time.time() - t0 < 60:
        time.sleep(0.2)
    yield f"http://127.0.0.1:{port}/"
    srv.should_exit = True
    th.join(timeout=10)


@pytest.mark.slow
def test_the_small_demo_builds_from_a_blank_canvas_with_a_staged_review(tutorial_server):
    sync_api = pytest.importorskip("playwright.sync_api")
    errors: list[str] = []
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # Chromium not installed
            pytest.skip(f"no Chromium: {exc}")
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(tutorial_server)
        page.evaluate("() => { localStorage.setItem('axelrod.hinted', '1'); localStorage.setItem('axelrod.guide.mode', '\"off\"'); }")
        page.reload()
        page.wait_for_selector("#empty-hint:not(.hidden)", timeout=30000)
        assert page.locator("g.pill").count() == 0
        assert page.locator("#btn-examples").is_visible() and not page.locator("#btn-step").is_visible()
        page.click("#btn-examples")
        page.wait_for_selector('#examples [data-run="select"]')
        assert page.locator("#examples .erow").count() == 24
        page.click('#examples [data-run="select"]')
        # the review opens on the staged event: seven changes, the flow strip, the staged graph
        page.wait_for_selector(".rv-items input[data-item]", timeout=60000)
        assert page.locator(".rv-items input[data-item]").count() == 7
        assert page.locator(".rv-stage.waiting").count() == 1
        for g in ("intake", "working", "long_term", "review"):              # one colored group per stage
            assert page.locator(f".rv-group.st-{g}").count() == 1, g
        assert page.locator(".rv-article mark").count() >= 3          # the phrases that asked for the items
        page.wait_for_selector("g.pill.staged-new", timeout=20000)
        # leave out the Fed: its value and links go with it, and the event is staged again
        page.click('.rv-items input[data-item="2"]')
        page.wait_for_function("() => document.querySelectorAll('.rv-items input:checked').length === 3")
        page.wait_for_function("() => document.querySelector('[data-act=approve]').textContent.includes('3 of 7')")
        page.click("[data-act=approve]")
        page.wait_for_function("() => (window.axelrod.store.graph?.entities ?? []).some((e) => e.id === 'inflation')",
                               timeout=60000)
        ids = page.evaluate("() => window.axelrod.store.graph.entities.map((e) => e.id)")
        assert "federal_reserve" not in ids
        # back on the live graph: the staged outlines go (pills that leave fade out first)
        page.wait_for_function("() => !window.axelrod.store.staged && !document.querySelector('g.pill.staged-new:not(.exiting)')",
                               timeout=10000)
        browser.close()
    assert not errors, errors
