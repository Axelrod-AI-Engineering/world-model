"""Optional browser smoke test (§15.4). Runs only with --runslow and when Playwright and Chromium are
installed locally; Playwright is not a project dependency."""

from __future__ import annotations

import socket
import threading
import time

import pytest

from axelrod_wm.memory.snapshots import MemoryBackend


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
        # the first view: Figure 1's entities inside their superentities, no subentities, panels closed
        assert page.locator("g.pill").count() == 48
        assert page.locator("g.hull[data-instance]").count() >= 8
        assert page.locator("g.row").count() == 0
        assert page.locator("#right-panel").is_hidden() and page.locator("#left-panel").is_hidden()
        # no categories widget on the canvas: they live in the Admin window, which starts minimized
        assert page.locator("#key").count() == 0
        assert "minimized" in (page.locator("#admin").get_attribute("class") or "")
        # entities shared by two superentities wear a stripe per owner; overlapping outlines draw a lens
        assert page.locator('g.pill[data-id="nvidia"] .owners rect').count() == 2
        assert page.locator("g.lens").count() >= 1
        # zoom is only zoom: zooming in opens nothing
        page.click("#zoom-in")
        page.click("#zoom-in")
        page.wait_for_timeout(600)
        assert page.locator("g.row").count() == 0 and page.locator("g.card-super").count() == 0
        # detail presets
        page.keyboard.press("3")
        page.wait_for_timeout(1200)
        assert page.locator("g.row").count() == 107
        page.keyboard.press("1")
        page.wait_for_timeout(1200)
        assert page.locator("g.card-super").count() >= 7 and page.locator("g.row").count() == 0
        # undo and redo a view change
        page.keyboard.press("Control+z")
        page.wait_for_timeout(1200)
        assert page.locator("g.row").count() == 107 and page.locator("g.card-super").count() == 0
        page.keyboard.press("Control+y")
        page.wait_for_timeout(1200)
        assert page.locator("g.card-super").count() >= 7
        # every shortcut on one sheet
        page.keyboard.press("?")
        page.wait_for_selector(".modal .keys")
        page.keyboard.press("Escape")
        page.keyboard.press("2")
        page.wait_for_timeout(1200)
        assert page.locator("g.pill").count() == 48 and page.locator("g.card-super").count() == 0
        # right-click opens one entity's subentities; right-click a superentity closes it into a card
        page.click('g.pill[data-id="inflation"]', button="right")
        page.wait_for_selector(".ctx-menu")
        page.click(".ctx-menu button:has-text('Show its subentities')")
        page.wait_for_timeout(800)
        assert page.locator('g.pill[data-id="inflation"] g.row').count() == 2
        page.click('g.hull-tab[data-instance="inst-S6"]', button="right")
        page.wait_for_selector(".ctx-menu")
        page.click(".ctx-menu button:has-text('Close it into one card')")
        page.wait_for_timeout(800)
        assert page.locator('g.card-super[data-instance="inst-S6"]').count() == 1
        # a closed superentity lists its members as chips; one shared with an open outline is tethered to it
        page.evaluate("() => window.axelrod.renderer.toggleGroup('inst-S12', true)")
        page.wait_for_timeout(900)
        assert page.locator('g.card-super[data-instance="inst-S12"] g.chip').count() == 2
        assert page.locator('g.card-super[data-instance="inst-S12"] g.chip.shared').count() == 1
        assert page.locator("g.tether").count() >= 1
        page.evaluate("() => window.axelrod.renderer.toggleGroup('inst-S12', false)")
        # the nested superentity: S10 holds S1 and S2
        page.click('g.hull-tab[data-instance="inst-S10"]', button="right")
        page.wait_for_selector(".ctx-menu")
        assert page.locator(".ctx-menu button:has-text('Open it with its parts closed')").count() == 1
        page.keyboard.press("Escape")
        # an actor's values, each with a small picture of its distribution
        page.click('g.pill[data-id="delta"]')
        page.wait_for_selector("#tab-inspector details.subrow svg.density", timeout=20000)
        # what to forecast: chips that wrap, at every granularity
        page.keyboard.press("q")
        page.wait_for_selector("#tab-thesis .pick.actor")
        assert page.locator("#tab-thesis .pick.sector").count() >= 1
        # asking: the Forecast tab shows progress at once, the guide (first time) narrates, and a brief
        # opens in the left sidebar when the forecast is in
        page.click("#th-ask")
        page.wait_for_selector("#tab-forecast .progress-card", timeout=20000)
        page.wait_for_selector("#guide:not(.hidden) .bubble", timeout=20000)
        page.wait_for_selector("#left-panel:not([hidden]) .brief h3", timeout=180000)
        assert "bottom line" in page.locator(".brief").inner_text().lower()
        # selecting text in the brief offers a chat, which is a labeled mock-up
        box = page.locator(".brief .lede").first.bounding_box()
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
        # the technical briefing
        page.click("#btn-methods")
        page.wait_for_selector("#methods .toc a", timeout=20000)
        assert page.locator("#methods .doc ol.refs li").count() >= 40
        page.keyboard.press("Escape")
        # two scripted steps (the second reads the Fed's decision), then walk through it
        page.locator("#canvas").focus()
        page.keyboard.press("ArrowRight")
        page.wait_for_function("() => document.querySelector('#step-label').textContent.startsWith('1 /')", timeout=120000)
        page.keyboard.press("ArrowRight")
        page.wait_for_function("() => document.querySelector('#step-label').textContent.startsWith('2 /')", timeout=180000)
        page.wait_for_selector("#caption .walks button", timeout=60000)
        page.click("#caption .walks button")
        page.wait_for_selector("#walkthrough .walk-body h4")
        first = page.locator("#walkthrough .walk-body h4").text_content()
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(500)
        assert page.locator("#walkthrough .walk-body h4").text_content() != first
        page.keyboard.press("Escape")
        assert page.locator("#walkthrough").is_hidden()
        # the memory drawer
        page.click("#btn-memory")
        page.wait_for_selector("#drawer .tnode", timeout=20000)
        browser.close()
    assert not errors, errors
