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
    pack = c.get("/v1/world-models/sally_demo/exports/v4.1.4").json()["data"]["domain_pack"]
print(json.dumps(sorted((p["path_id"], p["primary_company_id"]) for p in pack["transmission_paths"])))
"""


def _paths(seed: int) -> str:
    env = {**os.environ, "PYTHONHASHSEED": str(seed)}
    out = subprocess.run([sys.executable, "-c", SCRIPT], env=env, capture_output=True, text=True, check=True, timeout=300)
    return out.stdout.strip().splitlines()[-1]


def test_the_export_does_not_depend_on_the_process():
    runs = {_paths(seed) for seed in (1, 2, 3, 4)}
    assert len(runs) == 1 and "PATH_" in next(iter(runs))


READING = """
import hashlib, json, tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from axelrod_wm.api.app import create_app
from axelrod_wm.context.reading import build_reading_set
from axelrod_wm.repo.snapshots import MemoryBackend
app = create_app(scenario="sally_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
with TestClient(app) as c:
    ctx = c.get("/api/context/v4").json()
out = Path(tempfile.mkdtemp())
pack_file = next(f["file"] for f in ctx["manifest"]["load_order"] if f["source"] == "this export: domain_pack")
(out / pack_file).write_text("{}")
build_reading_set(out, ctx, ctx["manifest"])
print(json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((out / "reading").iterdir())}))
"""


def test_the_reading_set_does_not_depend_on_the_process():
    runs = []
    for seed in (1, 2):
        env = {**os.environ, "PYTHONHASHSEED": str(seed)}
        out = subprocess.run([sys.executable, "-c", READING], env=env, capture_output=True, text=True, check=True,
                             timeout=300)
        runs.append(out.stdout.strip().splitlines()[-1])
    assert runs[0] == runs[1] and "00_START_HERE.md" in runs[0]
