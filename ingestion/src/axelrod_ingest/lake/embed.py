"""Embedders for semantic search (Oct 17).

`fastembed` runs a small sentence embedder on the CPU, inside the service: no text leaves the deploy. The model is IBM's
granite-embedding-small-english-r2 (Oct 25): open (Apache-2.0) and from a US developer, 384 dimensions, ONNX, and it
needs no query or passage prefix, so a query and a passage embed the same way. It replaced BAAI/bge-small-en-v1.5. It runs
single-threaded, and its vectors are L2-normalized (granite's are not, as they come) and rounded to 6 decimals, so the
same text always embeds to the same unit vector. `hashing` needs no model: words and word pairs hashed into 256 signed buckets,
L2-normalized. It is exact and instant, so the tests use it, and it is the fallback when fastembed is not installed.

WORLD_MODEL_EMBEDDER selects one: fastembed, hashing, or auto (the default: fastembed when installed).
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from typing import Protocol

WORD = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    def __init__(self, dim: int = 256) -> None:
        self.dim = dim
        self.name = f"hashing-{dim}"

    def _bucket(self, feature: str) -> tuple[int, float]:
        h = hashlib.blake2b(feature.encode(), digest_size=8).digest()
        return int.from_bytes(h[:4], "big") % self.dim, (1.0 if h[4] & 1 else -1.0)

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            words = WORD.findall(t.lower())
            v = [0.0] * self.dim
            for f in [*words, *(f"{a} {b}" for a, b in zip(words, words[1:]))]:
                k, s = self._bucket(f)
                v[k] += s
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([round(x / n, 6) for x in v])
        return out


class FastEmbedder:
    MODEL = "ibm-granite/granite-embedding-small-english-r2"

    def __init__(self, cache_dir: str | None = None) -> None:
        from fastembed import TextEmbedding

        self.model = TextEmbedding(self.MODEL, threads=1, cache_dir=cache_dir)
        self.name = f"fastembed:{self.MODEL}"
        self.dim = 384

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for v in self.model.embed(texts, batch_size=32):
            n = math.sqrt(sum(float(x) * float(x) for x in v)) or 1.0
            out.append([round(float(x) / n, 6) for x in v])
        return out


def embedder_from_env(env: dict[str, str] | None = None) -> Embedder:
    env = dict(os.environ) if env is None else env
    which = env.get("WORLD_MODEL_EMBEDDER", "auto").strip().lower()
    if which == "hashing":
        return HashingEmbedder()
    try:
        return FastEmbedder(cache_dir=env.get("WORLD_MODEL_EMBED_CACHE") or None)
    except ImportError:
        if which == "fastembed":
            raise
        return HashingEmbedder()


class LazyEmbedder:
    """The configured embedder, loaded on first use (a model download should not slow the server's start)."""

    def __init__(self, env: dict[str, str] | None = None) -> None:
        self.env = env
        self._inner: Embedder | None = None

    @property
    def inner(self) -> Embedder:
        if self._inner is None:
            self._inner = embedder_from_env(self.env)
        return self._inner

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def dim(self) -> int:
        return self.inner.dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.inner.embed(texts)


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
