"""The engine's wiring: storage choice, component lookup, dependency injection, snapshots."""

from __future__ import annotations

import pytest

from axelrod_wm.engine import engine as engine_mod
from axelrod_wm.engine.config import ComponentSpec, EngineConfig
from axelrod_wm.engine.engine import Engine, _create, make_storage, registered_components
from axelrod_wm.engine.registry import REGISTRIES, registry
from axelrod_wm.repo.snapshots import FilesBackend, MemoryBackend
from axelrod_wm.trace import NullTracer
from tests.conftest import make_config


@pytest.fixture
def scratch_slots():
    """Slots registered by a test are removed afterwards (every real slot has a contract)."""
    before = set(REGISTRIES)
    yield
    for slot in set(REGISTRIES) - before:
        del REGISTRIES[slot]


def test_make_storage_picks_the_backend(tmp_path):
    assert isinstance(make_storage(EngineConfig(storage={"backend": "memory", "path": str(tmp_path)})), MemoryBackend)
    assert isinstance(make_storage(EngineConfig(storage={"backend": "files", "path": str(tmp_path)})), FilesBackend)
    with pytest.raises(KeyError, match="unknown storage backend 'tape'"):
        make_storage(EngineConfig(storage={"backend": "tape", "path": str(tmp_path)}))


def test_component_returns_the_wired_component():
    eng = Engine(make_config(), MemoryBackend(), NullTracer())
    marker = object()
    eng.components["parser"] = marker
    assert eng.component("parser") is marker
    with pytest.raises(KeyError):
        eng.component("nothing")


def test_save_snapshot_without_a_version_saves_nothing():
    eng = Engine(make_config(), MemoryBackend(), NullTracer())
    assert eng.version == 0 and eng.save_snapshot() is None
    assert eng.storage.snapshot_versions() == []


def test_registered_components_lists_every_slot():
    comps = registered_components()
    assert list(comps) == sorted(comps)
    assert "link_kalman" in comps["posterior_updater"] and comps["storage"] == ["files", "memory"]


def _config(**components):
    return EngineConfig(storage={"backend": "memory", "path": "var/test"}, components=components)


def test_create_injects_params_config_engine_and_other_slots(scratch_slots):
    @registry("_cov_dep").register("plain")
    class Dep:
        def __init__(self) -> None:
            pass

    @registry("_cov_main").register("main")
    class Main:
        def __init__(self, width: int, config, engine, _cov_dep, unused=3, *args) -> None:
            self.width, self.config, self.engine, self.dep, self.unused = width, config, engine, _cov_dep, unused

    cfg = _config(_cov_main=ComponentSpec(name="main", params={"width": 4}), _cov_dep="plain")
    made: dict = {}
    eng = object()
    obj = _create("_cov_main", cfg, eng, made, [])
    assert (obj.width, obj.config, obj.engine, obj.unused) == (4, cfg, eng, 3)
    assert isinstance(obj.dep, Dep) and made["_cov_dep"] is obj.dep
    assert _create("_cov_main", cfg, eng, made, []) is obj          # made once


def test_create_passes_extra_params_through_kwargs(scratch_slots):
    @registry("_cov_kw").register("kw")
    class Kw:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    obj = _create("_cov_kw", _config(_cov_kw=ComponentSpec(name="kw", params={"a": 1})), None, {}, [])
    assert obj.kwargs == {"a": 1}


def test_create_rejects_params_the_component_does_not_take(scratch_slots):
    @registry("_cov_strict").register("strict")
    class Strict:
        def __init__(self) -> None:
            pass

    cfg = _config(_cov_strict=ComponentSpec(name="strict", params={"b": 2, "a": 1}))
    with pytest.raises(TypeError, match=r"Strict \(_cov_strict\) does not accept params \['a', 'b'\]"):
        _create("_cov_strict", cfg, None, {}, [])


def test_create_detects_a_dependency_cycle(scratch_slots):
    @registry("_cov_x").register("x")
    class X:
        def __init__(self, _cov_y) -> None:
            pass

    @registry("_cov_y").register("y")
    class Y:
        def __init__(self, _cov_x) -> None:
            pass

    with pytest.raises(RuntimeError, match="component dependency cycle: _cov_x -> _cov_y -> _cov_x"):
        _create("_cov_x", _config(_cov_x="x", _cov_y="y"), None, {}, [])


def test_storage_backends_table_matches_the_registry():
    registered_components()
    assert {k: registry("storage").get(k) for k in engine_mod.STORAGE_BACKENDS} == engine_mod.STORAGE_BACKENDS
