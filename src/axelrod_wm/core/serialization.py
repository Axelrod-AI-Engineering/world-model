"""Canonical JSON, content digests, and set types that serialize deterministically.

Python randomizes string hashing per process, so set iteration order differs between runs.
Every set-valued field uses one of the annotated types below, which serialize as a sorted
list. Hashes use canonical JSON: sorted keys, compact separators, and floats rounded to 12
significant digits (§9).
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Annotated, Any

from pydantic import BaseModel, PlainSerializer


def _sorted_list(values: Any) -> list:
    return sorted(values, key=lambda v: str(v))


StrSet = Annotated[set[str], PlainSerializer(_sorted_list, return_type=list, when_used="json")]


def round12(x: float) -> float:
    if x == 0 or not math.isfinite(x):
        return 0.0 if x == 0 else x
    return float(f"{x:.12g}")


def _round_parse(s: str) -> float:
    return round12(float(s))


def _int_parse(s: str) -> float:
    # DECISION: ints and floats canonicalize alike, so a float field holding 0 and 0.0 hash equal.
    return round12(float(s))


def to_jsonable(obj: Any) -> Any:
    """JSON-compatible python structure for a model, list, or plain value."""
    if isinstance(obj, BaseModel):
        return json.loads(obj.model_dump_json())
    return json.loads(json.dumps(obj, default=_default))


def _default(o: Any) -> Any:
    if isinstance(o, BaseModel):
        return json.loads(o.model_dump_json())
    if isinstance(o, (set, frozenset)):
        return _sorted_list(o)
    if hasattr(o, "isoformat"):
        return o.isoformat()
    if hasattr(o, "tolist"):
        return o.tolist()
    raise TypeError(f"not JSON serializable: {type(o).__name__}")


def canonical_json(obj: Any) -> str:
    """Canonical JSON text: sorted keys, compact separators, floats rounded to 12 digits."""
    if isinstance(obj, BaseModel):
        raw = obj.model_dump_json()
    else:
        raw = json.dumps(obj, default=_default)
    data = json.loads(raw, parse_float=_round_parse, parse_int=_int_parse)
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
