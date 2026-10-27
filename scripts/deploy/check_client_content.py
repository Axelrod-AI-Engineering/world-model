"""Check client content before it goes onto the dev volume (Oct 26).

Client content (scenarios, worlds, configs) never passes through CI: it is copied onto the volume by hand, and the service
reads it only when it boots. On Oct 22 a Mac copy brought `._entities.yaml` resource forks with it, the loader read one as
YAML, and dev did not start. Run this on the folder you are about to copy (`.railway/push-client-content.sh` does, and
stops on a failure):

1. The files: every `.yaml`/`.yml` under scenarios/, worlds/ and configs/ decodes as UTF-8 and parses as YAML. The junk a
   Mac copy brings (`._*`, `.DS_Store`) is listed: the push leaves it out.
2. The boot: the service starts on the folder as dev runs it, with the main scenario (default `unified`, as
   `.railway/railway.ts` sets WORLD_MODEL_SCENARIO) and a login for every other scenario, each focus a compartment of the
   main engine. `/api/health` must answer within the budget, and every login must read its state.

    uv run python scripts/deploy/check_client_content.py data/clients [--scenario unified] [--budget 300]

Nothing is written outside a temporary folder; the model is held in memory. Exit 0 when the folder is safe to push.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
import tempfile
import time
from pathlib import Path

import yaml

FOLDERS = ("scenarios", "worlds", "configs")


def is_junk(path: Path) -> bool:
    return path.name.startswith("._") or path.name == ".DS_Store"


def check_files(root: Path) -> tuple[list[str], list[str]]:
    """(problems, junk): files that do not decode or parse, and the files a push leaves out."""
    problems, junk = [], []
    for folder in FOLDERS:
        for path in sorted((root / folder).rglob("*")) if (root / folder).is_dir() else []:
            rel = path.relative_to(root).as_posix()
            if is_junk(path):
                junk.append(rel)
            elif path.is_file() and path.suffix in (".yaml", ".yml") and not any(is_junk(p) for p in path.parents):
                try:
                    yaml.safe_load(path.read_bytes().decode("utf-8"))
                except UnicodeDecodeError as err:
                    problems.append(f"{rel}: not UTF-8 (byte {err.object[err.start]:#04x} at {err.start})")
                except yaml.YAMLError as err:
                    problems.append(f"{rel}: not YAML ({str(err).splitlines()[0]})")
    return problems, junk


def check_boot(root: Path, scenario: str, budget: float) -> list[str]:
    """Boot the service on the folder in process; the rows of what it did, or SystemExit-worthy problems raised."""
    from fastapi.testclient import TestClient

    from axelrod_wm.api.app import create_app
    from axelrod_wm.repo.snapshots import MemoryBackend

    others = sorted(p.name for p in (root / "scenarios").iterdir() if p.is_dir() and p.name != scenario)
    password = secrets.token_urlsafe(12)
    logins = {f"check-{name}": name for name in others}
    os.environ.update({
        "WORLD_MODEL_CLIENT_DIR": str(root), "WORLD_MODEL_PROFILE": "dev", "WORLD_MODEL_EMBEDDER": "hashing",
        "WORLD_MODEL_REQUIRE_BASIC_AUTH": "1", "WORLD_MODEL_BASIC_AUTH_USERNAME": "check",
        "WORLD_MODEL_BASIC_AUTH_PASSWORD": password, "WORLD_MODEL_API_KEYS": "",
        "WORLD_MODEL_LOGINS": ",".join(f"{user}:{password}:{name}" for user, name in logins.items())})
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        t0 = time.monotonic()
        app = create_app(scenario=scenario, storage=MemoryBackend(), trace_dir=None, play_delay=0.0,
                         lake_dir=Path(tmp) / "lake", lake_sync=False)
        with TestClient(app) as c:
            secs = time.monotonic() - t0
            r = c.get("/api/health")
            if r.status_code != 200:
                raise RuntimeError(f"/api/health answered {r.status_code}")
            if secs > budget:
                raise RuntimeError(f"the boot took {secs:.0f} s, over the {budget:.0f} s budget")
            rows.append(f"boot of {scenario}: healthy in {secs:.0f} s (budget {budget:.0f} s)")
            for user, name in logins.items():
                c.cookies.clear()
                c.post("/login", data={"username": user, "password": password, "next": "/"}, follow_redirects=False)
                r = c.get("/api/state")
                if r.status_code != 200 or not r.json().get("entities"):
                    raise RuntimeError(f"a login on {name} could not read its state ({r.status_code})")
                rows.append(f"login on {name}: {len(r.json()['entities'])} entities")
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("root", type=Path, help="the client folder to check (scenarios/, worlds/, configs/)")
    ap.add_argument("--scenario", default="unified", help="the main engine's scenario (WORLD_MODEL_SCENARIO on dev)")
    ap.add_argument("--budget", type=float, default=300.0, help="seconds the boot may take")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    if not (root / "scenarios" / args.scenario / "scenario.yaml").is_file():
        print(f"no scenario {args.scenario!r} under {root}/scenarios", file=sys.stderr)
        return 1
    problems, junk = check_files(root)
    for rel in junk:
        print(f"left out of the push: {rel}")
    if problems:
        print("\n".join(["files that would stop the boot:", *problems]), file=sys.stderr)
        return 1
    try:
        rows = check_boot(root, args.scenario, args.budget)
    except Exception as err:            # anything the boot raises is a reason not to push
        print(f"the service does not boot on this folder: {type(err).__name__}: {err}", file=sys.stderr)
        return 1
    print("\n".join(rows))
    print("safe to push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
