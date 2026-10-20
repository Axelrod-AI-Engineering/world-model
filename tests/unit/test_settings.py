"""Where the service's settings come from: the checked-in stage profile and the local .creds file (settings.py)."""

from __future__ import annotations

import pytest

from axelrod_wm import settings


def test_stage_comes_from_the_profile_railway_or_local():
    assert settings.stage({}) == "local"
    assert settings.stage({"RAILWAY_ENVIRONMENT_NAME": "dev"}) == "dev"
    assert settings.stage({"WORLD_MODEL_PROFILE": "prod", "RAILWAY_ENVIRONMENT_NAME": "dev"}) == "production"
    assert settings.stage({"WORLD_MODEL_PROFILE": " None "}) is None
    with pytest.raises(RuntimeError, match="unknown stage"):
        settings.stage({"WORLD_MODEL_PROFILE": "qa"})


def test_creds_hold_only_secrets(tmp_path):
    f = tmp_path / ".creds.dev"
    f.write_text("# a comment\n\nexport WORLD_MODEL_BASIC_AUTH_USERNAME=main\nWORLD_MODEL_BASIC_AUTH_PASSWORD='p w'\n"
                 'WORLD_MODEL_API_KEYS="a:b:c"\nWORLD_MODEL_SESSION_SECRET=x\n')
    assert settings.read_creds(f) == {"WORLD_MODEL_BASIC_AUTH_USERNAME": "main", "WORLD_MODEL_BASIC_AUTH_PASSWORD": "p w",
                                      "WORLD_MODEL_API_KEYS": "a:b:c", "WORLD_MODEL_SESSION_SECRET": "x"}
    f.write_text("WORLD_MODEL_OWNERS=a=b\n")
    with pytest.raises(RuntimeError, match="not a secret"):
        settings.read_creds(f)
    f.write_text("no equals sign\n")
    with pytest.raises(RuntimeError, match="KEY=VALUE"):
        settings.read_creds(f)


def test_the_profile_overlays_the_base_and_refuses_unknown_tables_and_keys(tmp_path):
    (tmp_path / "world_model.toml").write_text('[auth]\ninternal_orgs = ["base"]\ntrusted_issuers = []\n')
    (tmp_path / "world_model.dev.toml").write_text(
        '[auth]\ninternal_orgs = ["ours"]\nmain_login_org = "ours"\ndeny = ["kid:old"]\n'
        'trusted_issuers = [{issuer = "https://c", jwks_url = "https://c/jwks", audience = "wm"}]\n'
        '[auth.owners]\nsally = "s-org"\n[compartments]\nfocus = "s-org"\n')
    p = settings.read_profile("dev", tmp_path)
    assert p["auth"]["internal_orgs"] == ["ours"]
    assert settings.profile_env(p, "main") == {
        "WORLD_MODEL_TRUSTED_ISSUERS": "https://c;https://c/jwks;wm", "WORLD_MODEL_OWNERS": "sally=s-org,main=ours",
        "WORLD_MODEL_INTERNAL_ORGS": "ours", "WORLD_MODEL_DENY": "kid:old", "WORLD_MODEL_COMPARTMENTS": "focus=s-org"}
    assert settings.profile_env(settings.read_profile("staging", tmp_path)) == {"WORLD_MODEL_INTERNAL_ORGS": "base"}
    assert settings.profile_env({}) == {}
    (tmp_path / "world_model.local.toml").write_text("[runtime]\nx = 1\n")
    with pytest.raises(RuntimeError, match="unknown table"):
        settings.read_profile("local", tmp_path)
    (tmp_path / "world_model.local.toml").write_text('[auth]\npassword = "x"\n')
    with pytest.raises(RuntimeError, match="unknown keys"):
        settings.read_profile("local", tmp_path)


def test_load_fills_only_what_is_unset_and_reads_creds_only_off_railway(tmp_path):
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "world_model.dev.toml").write_text('[auth]\nmain_login_org = "ours"\ninternal_orgs = ["ours"]\n')
    (tmp_path / ".creds.dev").write_text("WORLD_MODEL_BASIC_AUTH_USERNAME=main\nWORLD_MODEL_BASIC_AUTH_PASSWORD=pw\n")
    env = {"WORLD_MODEL_PROFILE": "dev", "WORLD_MODEL_BASIC_AUTH_PASSWORD": "from-process"}
    assert settings.load(env, tmp_path) == "dev"
    assert env["WORLD_MODEL_BASIC_AUTH_PASSWORD"] == "from-process" and env["WORLD_MODEL_OWNERS"] == "main=ours"
    railway = {"RAILWAY_ENVIRONMENT_NAME": "dev", "RAILWAY_ENVIRONMENT_ID": "x"}
    settings.load(railway, tmp_path)
    assert "WORLD_MODEL_BASIC_AUTH_USERNAME" not in railway and "WORLD_MODEL_OWNERS" not in railway
    assert railway["WORLD_MODEL_INTERNAL_ORGS"] == "ours"
    assert settings.load({"WORLD_MODEL_PROFILE": "none"}, tmp_path) is None
    assert settings.load({}, tmp_path) == "local"


def test_the_checked_in_profiles_are_valid_and_hold_no_secrets():
    for name in settings.STAGES:
        env = settings.profile_env(settings.read_profile(name), "main")
        assert not set(env) & settings.SECRETS
    dev = settings.profile_env(settings.read_profile("dev"), "main")
    assert dev["WORLD_MODEL_COMPARTMENTS"] == "sally_focus=sally-demo-org" and "main=axelrod-internal" in dev["WORLD_MODEL_OWNERS"]
    assert dev["WORLD_MODEL_TRUSTED_ISSUERS"].count("/.well-known/jwks.json") == 3
