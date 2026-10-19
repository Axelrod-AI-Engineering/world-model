"""Optional browser check of a document's graph update (Oct 17): read a synthetic note in the Import dialog, see its
update drawn on the canvas beside its operations, focus one, open its evidence, and leave the model unchanged. Runs
only with --runslow and when Playwright and Chromium are installed locally (tests/ui/test_smoke.py's pattern)."""

from __future__ import annotations

import threading
import time

import pytest

from axelrod_wm.repo.snapshots import MemoryBackend
from tests.ui.test_smoke import _free_port

# synthetic text, written for this test
NOTE = (b"Desk rates note, October 5, 2026.\n\n"
        b"The BoJ raised its policy rate by 25bp to 1.25%. USD/JPY fell to 152 as the yen strengthened.\n\n"
        b"Brent crude lifts Komatsu operating profit. Higher oil prices lift Japan's core inflation.\n\n"
        b"Toyota's operating profit rose 4% y/y.")


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import uvicorn

    from axelrod_wm.api.app import create_app

    port = _free_port()
    app = create_app(scenario="emily_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0,
                     lake_dir=tmp_path_factory.mktemp("lake"))
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
def test_a_document_update_is_drawn_and_changes_nothing(server, tmp_path):
    sync_api = pytest.importorskip("playwright.sync_api")
    note = tmp_path / "2026-10-05_desk_note.md"
    note.write_bytes(NOTE)
    errors: list[str] = []
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # Chromium not installed
            pytest.skip(f"no Chromium: {exc}")
        page = browser.new_page(viewport={"width": 1500, "height": 950})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(server)
        page.wait_for_selector("g.pill", timeout=60000)
        version = page.evaluate("fetch('/api/sim/status').then((r) => r.json()).then((s) => s.version)")
        page.click("#btn-import")
        page.set_input_files("#import input[data-doc]", str(note))
        page.wait_for_selector("#import .imp-doc-head button[data-gu]", timeout=30000)
        page.click("#import .imp-doc-head button[data-gu]")
        page.wait_for_selector(".layer-gupdate g.gu-chip")
        # the values it observes or moves, a dashed new link, a marked link it is evidence for; the model is hidden
        assert page.locator(".layer-gupdate g.gu-chip").count() == 6
        assert page.locator(".layer-gupdate g.gu-link.new").count() == 1
        assert page.locator(".layer-gupdate g.gu-link.supports").count() == 1
        assert page.locator(".layer-gupdate g.gu-chip.up").count() >= 2
        assert page.locator(".layer-gupdate g.gu-chip.down").count() == 1
        assert not page.locator("g.pill").first.is_visible()
        assert page.locator("#import li.gu-op").count() == 6
        # an op lights its ends; its quote opens the passage it came from
        page.locator("#import li.gu-op", has_text="New link").locator("button.gu-opline").click()
        page.wait_for_timeout(300)
        assert page.locator(".layer-gupdate g.gu-chip.hot").count() == 2
        page.click("#import button.gu-quote")
        assert page.locator("#import .gu-chunk mark").inner_text() == "Brent crude lifts Komatsu operating profit."
        # back to the items: the canvas shows the model again, which nothing changed
        page.click("#import [data-gu-back]")
        assert page.locator(".layer-gupdate g.gu-chip").count() == 0 and page.locator("g.pill").first.is_visible()
        assert page.evaluate("fetch('/api/sim/status').then((r) => r.json()).then((s) => s.version)") == version
        browser.close()
    assert errors == []
