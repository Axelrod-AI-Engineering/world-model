"""The v4.1.4 export is the same file whichever process writes it: nothing in it may depend on the order of a set,
which Python varies by process (PYTHONHASHSEED). A path whose chain reached two companies equally once named a
different primary company from one run to the next."""

from __future__ import annotations

import os
import subprocess
import sys

SCRIPT = """
import json
from fastapi.testclient import TestClient
from axelrod_wm.api.app import create_app
from axelrod_wm.repo.snapshots import MemoryBackend
app = create_app(scenario="sally_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
with TestClient(app) as c:
    pack = c.get("/api/world-model/context/v4").json()["domain_pack"]
print(json.dumps(sorted((p["path_id"], p["primary_company_id"]) for p in pack["transmission_paths"])))
"""


def _paths(seed: int) -> str:
    env = {**os.environ, "PYTHONHASHSEED": str(seed)}
    out = subprocess.run([sys.executable, "-c", SCRIPT], env=env, capture_output=True, text=True, check=True, timeout=300)
    return out.stdout.strip().splitlines()[-1]


def test_the_export_does_not_depend_on_the_process():
    runs = {_paths(seed) for seed in (1, 2, 3, 4)}
    assert len(runs) == 1 and "PATH_" in next(iter(runs))
