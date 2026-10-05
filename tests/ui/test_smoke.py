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
def test_the_demo_loads_steps_and_switches_levels(server):
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
        page.wait_for_selector("g.node-pill", timeout=60000)
        page.wait_for_timeout(1500)
        assert page.locator("g.node-pill").count() == 33
        assert page.locator("g.hull").count() >= 7
        page.keyboard.press("3")
        page.wait_for_timeout(1500)
        assert page.locator("g.node-sub").count() == 69
        page.keyboard.press("1")
        page.wait_for_timeout(1500)
        assert page.locator("g.node-super").count() >= 7
        page.keyboard.press("2")
        page.keyboard.press("ArrowRight")
        page.wait_for_function("() => document.querySelector('#step-label').textContent.startsWith('step 1/')",
                               timeout=120000)
        page.click("#btn-memory")
        page.wait_for_selector("#drawer .tnode", timeout=20000)
        browser.close()
    assert not errors, errors
