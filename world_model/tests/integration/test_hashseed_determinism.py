"""What the small demo learns and forecasts is the same whichever process runs it: Python orders a set differently in
each process (PYTHONHASHSEED), so nothing that reaches the model's state or an output may depend on that order. The
scenario runs the whole example chain (every example staged, reviewed and approved, a thesis posed) in two processes
with different hash seeds, and the taxonomy nodes, every item's assignment, and each forecast's transmission, path
source and isolated grids must match byte for byte. The transmission grids once listed their values and links in set
order, so a forecast's grids differed from one process to the next.

The state hash too (Oct 26): a state saved by one process must hash the same, and restore, in any other. Every set the
state holds is given several members first (a scenario rarely builds a set of two, and only those depend on order), then
the state is hashed, and saved and loaded back, under three more seeds. Dev failed to restart three times when a set
field's hash followed the process's set order."""

from __future__ import annotations

import json
import os
import pickle
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


FILL = """
import enum, pickle, sys
from pydantic import BaseModel
from axelrod_wm.sim.examples.session import run_examples

_, runner = run_examples("small_demo")
eng = runner.controller.engine
filled, seen = {}, set()

def walk(x):
    if id(x) in seen:
        return
    seen.add(id(x))
    if isinstance(x, BaseModel):
        for name in type(x).model_fields:
            v = getattr(x, name, None)
            if isinstance(v, set):
                one = next(iter(v), None)
                v.update(set(type(one)) if isinstance(one, enum.Enum) else {f"zz-{k}" for k in range(9)})
                key = type(x).__name__ + "." + name
                filled[key] = filled.get(key, 0) + 1
            else:
                walk(v)
    elif isinstance(x, dict):
        for v in x.values():
            walk(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            walk(v)

walk(eng.wm)
walk(eng.ltm)
pickle.dump((eng.wm, eng.ltm, filled), open(sys.argv[1], "wb"))
"""

HASH = """
import pickle, sys
from axelrod_wm.repo.snapshots import dump_state, load_state, state_hash

wm, ltm, _filled = pickle.load(open(sys.argv[1], "rb"))
print(state_hash(wm, ltm), state_hash(*load_state(dump_state(wm, ltm))))
"""


def _python(script: str, seed: int, *args: str) -> str:
    env = {**os.environ, "PYTHONHASHSEED": str(seed)}
    out = subprocess.run([sys.executable, "-c", script, *args], env=env, capture_output=True, text=True, check=True,
                         timeout=300)
    return out.stdout.strip()


def test_the_state_hash_and_a_restore_do_not_depend_on_the_process(tmp_path):
    state = tmp_path / "state.pkl"
    _python(FILL, 0, str(state))
    _wm, _ltm, filled = pickle.loads(state.read_bytes())
    assert {"SuperentityPattern.rival_ids", "Entity.category_tags", "Episode.signature"} <= set(filled)
    hashes = {_python(HASH, seed, str(state)) for seed in (1, 2, 3)}
    assert len(hashes) == 1
    stored, restored = hashes.pop().split()
    assert stored == restored
