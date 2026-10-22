"""Deterministic random streams (§8.3, §9).

Every stream is a ``numpy.random.Generator`` seeded from a ``SeedSequence`` whose spawn key is
built from stable names. String keys are hashed with SHA-256.
"""

from __future__ import annotations

import hashlib

import numpy as np


def stable_key(key: int | str) -> int:
    if isinstance(key, bool):
        return int(key)
    if isinstance(key, int):
        return key & 0xFFFFFFFFFFFFFFFF
    h = hashlib.sha256(str(key).encode("utf-8")).hexdigest()
    return int(h[:16], 16)


def make_rng(seed: int, *keys: int | str) -> np.random.Generator:
    ss = np.random.SeedSequence(entropy=int(seed), spawn_key=tuple(stable_key(k) for k in keys))
    return np.random.default_rng(ss)


def seed_sequence_of(rng: np.random.Generator) -> np.random.SeedSequence:
    ss = getattr(rng.bit_generator, "seed_seq", None)
    if ss is None:  # pragma: no cover - numpy always keeps it for default_rng
        ss = rng.bit_generator._seed_seq  # noqa: SLF001
    return ss


def substream(rng: np.random.Generator, *keys: int | str) -> np.random.Generator:
    """A generator derived from `rng`'s seed and stable keys, without consuming `rng`.
    Two calls with the same base and keys give identical streams (common random numbers)."""
    base = seed_sequence_of(rng)
    ss = np.random.SeedSequence(entropy=base.entropy,
                                spawn_key=tuple(base.spawn_key) + tuple(stable_key(k) for k in keys))
    return np.random.default_rng(ss)
