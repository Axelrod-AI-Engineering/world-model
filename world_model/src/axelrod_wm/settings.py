"""Where the service's settings come from (Oct 20), following core's convention.

- Non-secret settings are checked in: `configs/world_model.toml`, overlaid by `configs/world_model.<stage>.toml`. They
  say which core stages' tokens are trusted, which organizations own which logins and compartments, and which
  organizations are internal.
- Secrets live in one place per stage: the gitignored `.creds.<stage>` file (dotenv), read only when running locally.
  On Railway the same names arrive as process variables, pushed from that file by `.railway/railway-sync-creds.sh`.
- A process variable always wins, then the creds file, then the checked-in profile. The readers (`api/auth.py`,
  `api/keys.py`, `api/tokens.py`, `api/v1/compartments.py`) keep reading the process environment.

The stage is `WORLD_MODEL_PROFILE`, else Railway's environment name, else `local`. `WORLD_MODEL_PROFILE=none` turns
the loading off (the tests do this).
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import MutableMapping
from pathlib import Path

from axelrod_wm.paths import REPO_ROOT as ROOT

CONFIGS = ROOT / "configs"
STAGES = ("local", "dev", "staging", "production")
ALIASES = {"development": "dev", "prod": "production"}
# only these names may be in a creds file, and none of them may be in a checked-in profile
SECRETS = frozenset({"WORLD_MODEL_BASIC_AUTH_USERNAME", "WORLD_MODEL_BASIC_AUTH_PASSWORD", "WORLD_MODEL_LOGINS",
                     "WORLD_MODEL_API_KEYS", "WORLD_MODEL_SESSION_SECRET", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"})
PROFILE_KEYS = {"auth": {"trusted_issuers", "internal_orgs", "main_login_org", "deny", "owners"}, "compartments": None}


def stage(env: MutableMapping[str, str] | None = None) -> str | None:
    """The stage whose settings load, or None when loading is off."""
    env = os.environ if env is None else env
    raw = (env.get("WORLD_MODEL_PROFILE") or env.get("RAILWAY_ENVIRONMENT_NAME") or "local").strip().lower()
    if raw == "none":
        return None
    name = ALIASES.get(raw, raw)
    if name not in STAGES:
        raise RuntimeError(f"unknown stage {raw!r}: one of {', '.join(STAGES)}, or none")
    return name


def read_creds(path: Path) -> dict[str, str]:
    """A dotenv file: KEY=VALUE lines, `#` comments, an optional `export `, values optionally quoted. Only secret
    names are allowed: everything else belongs in the checked-in profile."""
    out: dict[str, str] = {}
    for n, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.removeprefix("export ").partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not key:
            raise RuntimeError(f"{path.name} line {n}: expected KEY=VALUE")
        if key not in SECRETS:
            raise RuntimeError(f"{path.name} line {n}: {key} is not a secret; put it in configs/world_model.<stage>.toml")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key] = value
    return out


def read_profile(name: str, configs: Path = CONFIGS) -> dict:
    """The base profile overlaid by the stage's, table by table."""
    merged: dict = {}
    for f in (configs / "world_model.toml", configs / f"world_model.{name}.toml"):
        if not f.exists():
            continue
        data = tomllib.loads(f.read_text())
        for table, body in data.items():
            if table not in PROFILE_KEYS:
                raise RuntimeError(f"{f.name}: unknown table [{table}]")
            allowed = PROFILE_KEYS[table]
            extra = sorted(set(body) - allowed) if allowed is not None else []
            if extra:
                raise RuntimeError(f"{f.name}: unknown keys in [{table}]: {', '.join(extra)}")
            merged.setdefault(table, {}).update(body)
    return merged


def profile_env(profile: dict, main_login: str = "") -> dict[str, str]:
    """The checked-in profile as the variables the readers take."""
    auth, comps = profile.get("auth", {}), profile.get("compartments", {})
    out: dict[str, str] = {}
    issuers = auth.get("trusted_issuers", [])
    if issuers:
        out["WORLD_MODEL_TRUSTED_ISSUERS"] = ",".join(f"{i['issuer']};{i['jwks_url']};{i['audience']}" for i in issuers)
    owners = dict(auth.get("owners", {}))
    if main_login and auth.get("main_login_org"):
        owners.setdefault(main_login, auth["main_login_org"])
    if owners:
        out["WORLD_MODEL_OWNERS"] = ",".join(f"{k}={v}" for k, v in owners.items())
    if auth.get("internal_orgs"):
        out["WORLD_MODEL_INTERNAL_ORGS"] = ",".join(auth["internal_orgs"])
    if auth.get("deny"):
        out["WORLD_MODEL_DENY"] = ",".join(auth["deny"])
    if comps:
        out["WORLD_MODEL_COMPARTMENTS"] = ",".join(f"{k}={v}" for k, v in comps.items())
    return out


def load(env: MutableMapping[str, str] | None = None, root: Path = ROOT) -> str | None:
    """Fill the environment from the creds file (locally) and the checked-in profile, never overriding a variable
    already set. Returns the stage loaded, or None when loading is off."""
    env = os.environ if env is None else env
    name = stage(env)
    if name is None:
        return None
    creds = root / f".creds.{name}"
    if creds.exists() and not env.get("RAILWAY_ENVIRONMENT_ID"):
        for k, v in read_creds(creds).items():
            env.setdefault(k, v)
    for k, v in profile_env(read_profile(name, root / "configs"), env.get("WORLD_MODEL_BASIC_AUTH_USERNAME", "")).items():
        env.setdefault(k, v)
    return name
