"""Where things are: the one source for the repository's roots.

- `REPO_ROOT` is the workspace root. It holds `data/` (local, gitignored), `var/` (caches, the lakehouse) and
  `configs/` (the stage settings, `world_model*.toml`). A deployment that installs the package without the source tree
  (the Docker image) sets `AXELROD_ROOT` to where it copied them.
- `WM_ROOT` is the world model member, `<root>/world_model`: `examples/`, `taxonomy/`, `configs/` (engine settings,
  `*.yaml`) and `web/`.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT_ENV = "AXELROD_ROOT"
# world_model/src/axelrod_wm/paths.py -> the workspace root is three levels up from the package folder
REPO_ROOT = Path(os.environ.get(ROOT_ENV) or Path(__file__).resolve().parents[3])
WM_ROOT = REPO_ROOT / "world_model"
