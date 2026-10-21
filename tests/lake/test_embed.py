"""Embedders (Oct 17): the hashing embedder is exact, unit-norm, and deterministic; fastembed is selected by the
environment and falls back to hashing in auto mode; its vectors are rounded; the lazy embedder loads once; cosine
handles zero vectors. No model is downloaded: fastembed is replaced with a fake module."""

from __future__ import annotations

import math
import sys
import types

import pytest

from axelrod_wm.lake import embed
from axelrod_wm.lake.embed import FastEmbedder, HashingEmbedder, LazyEmbedder, cosine, embedder_from_env


class FakeTextEmbedding:
    calls: list[dict] = []

    def __init__(self, model, threads=None, cache_dir=None):
        FakeTextEmbedding.calls.append({"model": model, "threads": threads, "cache_dir": cache_dir})

    def embed(self, texts, batch_size=None):
        assert batch_size == 32
        for t in texts:
            yield [len(t) + 0.12345678, 1 / 3]


@pytest.fixture
def fake_fastembed(monkeypatch):
    FakeTextEmbedding.calls = []
    monkeypatch.setitem(sys.modules, "fastembed", types.SimpleNamespace(TextEmbedding=FakeTextEmbedding))
    return FakeTextEmbedding


@pytest.fixture
def no_fastembed(monkeypatch):
    monkeypatch.setitem(sys.modules, "fastembed", None)       # makes `from fastembed import ...` raise ImportError


def norm2(v):
    return math.sqrt(sum(x * x for x in v))


def test_hashing_is_deterministic_and_unit_norm():
    e = HashingEmbedder()
    a, b = e.embed(["Acme Motors raised its operating profit forecast", "Acme Motors raised its operating profit forecast"])
    assert a == b == HashingEmbedder().embed(["Acme Motors raised its operating profit forecast"])[0]
    assert len(a) == 256 and e.name == "hashing-256" and e.dim == 256
    assert norm2(a) == pytest.approx(1.0, abs=1e-5)
    assert all(round(x, 6) == x for x in a)


def test_hashing_ignores_case_and_punctuation_but_not_words():
    e = HashingEmbedder(dim=64)
    a, b, c = e.embed(["The BoJ hiked.", "the boj HIKED", "the ecb cut"])
    assert a == b and a != c and len(a) == 64 and e.name == "hashing-64"
    assert cosine(a, c) < 1.0


def test_hashing_embeds_empty_text_as_the_zero_vector():
    assert HashingEmbedder(dim=8).embed(["", "!!"]) == [[0.0] * 8, [0.0] * 8]


def test_env_selects_hashing():
    assert isinstance(embedder_from_env({"WORLD_MODEL_EMBEDDER": " Hashing "}), HashingEmbedder)


def test_env_reads_the_process_environment_by_default():
    assert isinstance(embedder_from_env(), HashingEmbedder)            # the suite's conftest sets hashing


def test_fastembed_required_raises_when_not_installed(no_fastembed):
    with pytest.raises(ImportError):
        embedder_from_env({"WORLD_MODEL_EMBEDDER": "fastembed"})


def test_auto_falls_back_to_hashing_when_fastembed_is_missing(no_fastembed):
    assert isinstance(embedder_from_env({}), HashingEmbedder)
    assert isinstance(embedder_from_env({"WORLD_MODEL_EMBEDDER": "auto"}), HashingEmbedder)


def test_auto_falls_back_when_the_embedder_class_raises_import_error(monkeypatch):
    def boom(cache_dir=None):
        raise ImportError("no onnxruntime")

    monkeypatch.setattr(embed, "FastEmbedder", boom)
    assert isinstance(embedder_from_env({"WORLD_MODEL_EMBEDDER": "auto"}), HashingEmbedder)


def test_fastembed_is_selected_single_threaded_with_its_cache_dir(fake_fastembed):
    e = embedder_from_env({"WORLD_MODEL_EMBEDDER": "fastembed", "WORLD_MODEL_EMBED_CACHE": "/models"})
    assert isinstance(e, FastEmbedder)
    assert (e.name, e.dim) == ("fastembed:BAAI/bge-small-en-v1.5", 384)
    assert fake_fastembed.calls == [{"model": "BAAI/bge-small-en-v1.5", "threads": 1, "cache_dir": "/models"}]


def test_auto_selects_fastembed_without_a_cache_dir_when_installed(fake_fastembed):
    assert isinstance(embedder_from_env({"WORLD_MODEL_EMBED_CACHE": ""}), FastEmbedder)
    assert fake_fastembed.calls[-1]["cache_dir"] is None


def test_fastembed_vectors_are_rounded_to_six_decimals(fake_fastembed):
    e = FastEmbedder()
    assert e.embed(["ab", "abcd"]) == [[2.123457, 0.333333], [4.123457, 0.333333]]
    assert e.embed(["ab"]) == e.embed(["ab"])


def test_lazy_embedder_loads_once_and_proxies(monkeypatch):
    built = []

    def factory(env):
        built.append(env)
        return HashingEmbedder(dim=16)

    monkeypatch.setattr(embed, "embedder_from_env", factory)
    lazy = LazyEmbedder({"WORLD_MODEL_EMBEDDER": "hashing"})
    assert built == []                                               # nothing loads at construction
    assert (lazy.name, lazy.dim) == ("hashing-16", 16)
    assert lazy.embed(["oil"]) == HashingEmbedder(dim=16).embed(["oil"])
    assert lazy.inner is lazy.inner
    assert built == [{"WORLD_MODEL_EMBEDDER": "hashing"}]


def test_cosine():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine([1.0, 0.0], [0.0, 2.0]) == pytest.approx(0.0)
    assert cosine([3.0, 4.0], [-3.0, -4.0]) == pytest.approx(-1.0)
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert cosine([0.0, 0.0], [0.0, 0.0]) == 0.0
