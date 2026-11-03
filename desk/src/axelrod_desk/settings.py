"""Where the desk keeps its data and finds the world model it builds on (Nov 2).

Everything is read from one TOML file, `<home>/desk.toml`, where `home` is `DESK_HOME` (default `./data/desk`). The home holds
the desk's own state: the database, the stored files, their page text, the lake, and the builds. The other paths point at the
world model the builds start from, which the desk reads and never changes:

    repo            the karthik-world-model checkout whose export scripts run a build
    data            WORLD_MODEL_DATA_DIR for those scripts (the client data folder)
    clients         WORLD_MODEL_CLIENT_DIR (the client's worlds and scenarios)
    base_scenario   the scenario every build narrows (the unified model)
    construction    the base model's construction sources: <company>/sources.json, citations.json, repair.json
    world_view      the base scenario's world view (world_model/scripts/export_world_view.py): companies, values, links
    client_core     the client's v4.1.4 folder of 000, 010 and 020, copied beside each export (optional)
    remaps          OLD=NEW path prefixes that let the exporters find (and hash) the base construction's documents

Paths in the file may be relative to the file's folder. Client data stays in these folders, all of them outside the repository.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

HOME_ENV = "DESK_HOME"
PYTHON = ("uv", "run", "--no-sync", "--package", "axelrod-world-model", "python")


@dataclass(frozen=True)
class Settings:
    home: Path
    repo: Path
    data: Path
    clients: Path
    construction: Path
    world_view: Path
    base_scenario: str = "unified"
    client_core: Path | None = None
    remaps: tuple[str, ...] = ()
    tenant: str = "desk"
    python: tuple[str, ...] = PYTHON           # how a world-model script is run (from `repo`)
    pack_index: str = "050"                    # the v4.1.4 file index of a desk build's domain pack
    groups: dict[str, list[str]] = field(default_factory=dict)   # named sector groups, beside the scenarios' own

    @property
    def db(self) -> Path:
        return self.home / "desk.sqlite3"

    @property
    def files(self) -> Path:
        return self.home / "files"

    @property
    def text(self) -> Path:
        return self.home / "text"

    @property
    def lake(self) -> Path:
        return self.home / "lake"

    @property
    def builds(self) -> Path:
        return self.home / "builds"

    @property
    def scenarios(self) -> Path:
        """A client root of the desk's own, holding the scenario each build writes."""
        return self.home / "clients"


def home_of(env: dict[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    return Path(env.get(HOME_ENV) or "data/desk").expanduser().resolve()


def load(home: Path | None = None) -> Settings:
    """The settings in `<home>/desk.toml`."""
    home = home or home_of()
    raw = tomllib.loads((home / "desk.toml").read_text(encoding="utf-8"))

    def path(key: str) -> Path:
        return (home / raw[key]).expanduser().resolve()

    return Settings(home=home, repo=path("repo"), data=path("data"), clients=path("clients"),
                    construction=path("construction"), world_view=path("world_view"),
                    base_scenario=raw.get("base_scenario", "unified"),
                    client_core=path("client_core") if raw.get("client_core") else None,
                    remaps=tuple(raw.get("remaps", [])), tenant=raw.get("tenant", "desk"),
                    python=tuple(raw.get("python", PYTHON)), pack_index=str(raw.get("pack_index", "050")),
                    groups={k: list(v) for k, v in (raw.get("groups") or {}).items()})


__all__ = ["HOME_ENV", "PYTHON", "Settings", "home_of", "load"]
