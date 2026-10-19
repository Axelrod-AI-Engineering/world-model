"""Engine config: component and translator references, and loading with overrides."""

from __future__ import annotations

import pytest
import yaml

from axelrod_wm.engine.config import DEFAULT_CONFIG_PATH, EngineConfig, load_config


def test_translators_pass_through_a_non_dict_for_validation_to_reject():
    assert EngineConfig._translator_lists(None) is None
    with pytest.raises(ValueError):
        EngineConfig(translators=["news"])


def test_component_with_params_and_unknown_slot():
    cfg = EngineConfig(components={"parser": {"name": "custom", "params": {"depth": 2}}})
    name, params = cfg.component("parser")
    assert (name, params) == ("custom", {"depth": 2})
    params["depth"] = 9                                     # a copy: the config is unchanged
    assert cfg.component("parser") == ("custom", {"depth": 2})
    assert cfg.component("classifier") == ("taxonomy_descent", {})
    with pytest.raises(KeyError, match="no component configured for slot 'nowhere'"):
        cfg.component("nowhere")


def test_translator_chain_mixes_names_and_specs():
    cfg = EngineConfig(translators={"news": [{"name": "llm", "params": {"model": "m"}}, "template"],
                                    "data": "data_feed"})
    assert cfg.translator_chain("news") == [("llm", {"model": "m"}), ("template", {})]
    assert cfg.translator("news") == ("llm", {"model": "m"})
    assert cfg.translator_chain("data") == [("data_feed", {})]           # a single name is a list of one
    assert cfg.translator("rumour") == ("hand_drawn", {})                # an unknown kind falls back


def test_load_config_from_a_missing_file_uses_the_defaults(tmp_path):
    cfg = load_config(tmp_path / "absent.yaml")
    assert cfg == EngineConfig()


def test_load_config_resolves_a_relative_override_against_the_repo(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)                          # the relative path does not exist here
    rel = DEFAULT_CONFIG_PATH.relative_to(DEFAULT_CONFIG_PATH.parents[1])   # configs/default.yaml
    base = load_config(tmp_path / "absent.yaml", overrides=[str(rel)])
    assert base == load_config(DEFAULT_CONFIG_PATH)
    (tmp_path / "seed.yaml").write_text(yaml.safe_dump({"seed": 11}))
    assert load_config(tmp_path / "absent.yaml", overrides=["seed.yaml"]).seed == 11   # exists locally


def test_load_config_applies_keyword_updates_last(tmp_path):
    cfg = load_config(tmp_path / "absent.yaml", overrides=[{"seed": 3, "time": {"horizon_days": 30}}],
                      seed=5, time={"step_days": 2})
    assert (cfg.seed, cfg.time.step_days, cfg.time.horizon_days) == (5, 2, 30)
