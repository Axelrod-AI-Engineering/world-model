"""What the small demo learns and forecasts is the same whichever process runs it: Python orders a set differently in
each process (PYTHONHASHSEED), so nothing that reaches the model's state or an output may depend on that order. The
scenario runs the whole example chain (every example staged, reviewed and approved, a thesis posed) in two processes
with different hash seeds, and the taxonomy nodes, every item's assignment, and each forecast's transmission, path
source and isolated grids must match byte for byte. The transmission grids once listed their values and links in set
order, so a forecast's grids differed from one process to the next."""

from __future__ import annotations

import json
import os
import subprocess
import sys

SCRIPT = """
import json
from axelrod_wm.inference.paths import METHODS, isolate
from axelrod_wm.sim.examples.session import run_examples

_, runner = run_examples("small_demo")
ctl = runner.controller
eng = ctl.engine
out = {
    "taxonomies": {
        name: {k: json.loads(n.model_dump_json()) for k, n in g.taxonomy.nodes.items()}
        for name, g in (("objects", eng.ltm.object_generalizations), ("interactions", eng.ltm.interaction_generalizations))},
    "assignments": {
        "entities": {k: e.generalization_id for k, e in eng.wm.graph.entities.items()},
        "interactions": {k: i.generalization_id for k, i in eng.wm.graph.interactions.items()}},
    "forecasts": {},
}
for tid in ctl.theses:
    for fc in ctl.forecasts_of(tid):
        grids = {m: isolate(fc.paths, m) for m in METHODS} if fc.paths and fc.paths.get("values") else {}
        out["forecasts"][fc.id] = {"transmission": [t.model_dump(mode="json") for t in fc.transmission or []],
                                   "paths": fc.paths, "grids": grids}
print(json.dumps(out))     # dict order kept: the order of an output is part of the output
"""


def _run(seed: int) -> str:
    env = {**os.environ, "PYTHONHASHSEED": str(seed)}
    out = subprocess.run([sys.executable, "-c", SCRIPT], env=env, capture_output=True, text=True, check=True, timeout=300)
    return out.stdout.strip().splitlines()[-1]


def test_the_learned_taxonomy_and_the_forecasts_do_not_depend_on_the_process():
    first, second = _run(1), _run(2)
    assert first == second
    got = json.loads(first)
    assert got["taxonomies"]["interactions"] and got["assignments"]["interactions"]
    assert any(f["grids"] and f["transmission"] for f in got["forecasts"].values())
