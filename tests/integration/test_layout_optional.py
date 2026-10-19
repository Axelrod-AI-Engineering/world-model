"""A scenario without a drawn layout answers an empty one, not an error (the canvas then lays the graph out itself), so
the browser logs no failed request on opening Sally's or Emily's demo."""

from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.repo.snapshots import MemoryBackend


def test_a_scenario_without_a_layout_answers_an_empty_one():
    app = create_app(scenario="sally_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        r = c.get("/api/layouts/figure1")
        assert r.status_code == 200 and r.json() == {}
