"""The initializer's last step (§8.13 step 5): a cursor per live source at the end of the history."""

from __future__ import annotations

from datetime import timedelta

from axelrod_wm.engine.initialize import Initializer
from tests.conftest import START, constructed_engine


def test_set_cursors_puts_one_cursor_per_source_at_the_end_of_history():
    eng = constructed_engine()
    end = START + timedelta(days=400)
    Initializer(eng).set_cursors(["mock_web_scraper", "fred"], end)
    assert dict(eng.wm.source_cursors) == {"mock_web_scraper": end, "fred": end}
