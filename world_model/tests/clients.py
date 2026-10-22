"""Client content in the tests (Oct 21).

Client scenarios, worlds, and construction files are never tracked: they live in a client root (`WORLD_MODEL_CLIENT_DIR`,
default <data>/clients, data/ being local and gitignored; src/axelrod_wm/clients.py). CI has none. The suite therefore runs in two ways:

- Against `tests/fixtures/clients`, a small synthetic client (the invented "acme" names: scenarios `acme_demo` and
  `acme_focus`, world `acme_demo`). tests/conftest.py puts it first on the client roots, so every test can use it.
- Against the real client content, when it is present: a test module that reads it starts with
  `skip_without_client("sally_demo")`, and is skipped, with the reason, when it is absent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from axelrod_wm.clients import DATA_DIR, client_roots, find_scenario

SALLY_WORK = DATA_DIR / "work" / "sally"      # the client's local working data (construction pages, days, bundles)


def client_present(*scenario_ids: str) -> bool:
    return all(find_scenario(s) is not None for s in scenario_ids)


def skip_without_client(*scenario_ids: str) -> None:
    """Skip the rest of a test module (at import, before it reads client files) when a client scenario is absent."""
    missing = ", ".join(s for s in scenario_ids if find_scenario(s) is None)
    if missing:
        pytest.skip(f"client content is absent: {missing} (WORLD_MODEL_CLIENT_DIR; data/ is gitignored)",
                    allow_module_level=True)


def client_path(relative: str) -> Path:
    """A file of client content, by its path under a client root (`worlds/<name>/...`, `scenarios/<id>/...`)."""
    for root in client_roots():
        if (root / relative).exists():
            return root / relative
    return client_roots()[-1] / relative
