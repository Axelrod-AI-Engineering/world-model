"""Every set in the model's state is written sorted, however it is reached (Oct 26).

A set iterates in an order Python draws per process (PYTHONHASHSEED), so a set written in that order makes the state
hash differ from one process to the next, and a restart cannot restore what the last process stored: dev failed to boot
three times on Oct 26 for this. The state's set fields are typed `StrSet` or `TagSet`, which serialize sorted; the hash
reads them through `field_adapter`, which once dropped that serializer. These check, for every model reachable from
WorkingMemory and LongTermMemory, without needing a state that happens to hold a set of two: that no field holds a bare
set at any depth, and that each set field dumps sorted through the hash's own path."""

from __future__ import annotations

import enum
import types
import typing
from typing import Annotated, Any, get_args, get_origin

from pydantic import BaseModel

from axelrod_wm.memory.long_term import LongTermMemory
from axelrod_wm.memory.working import WorkingMemory
from axelrod_wm.repo.mutator import field_adapter

SETS = (set, frozenset)


def models() -> list[type[BaseModel]]:
    """Every pydantic model a state can hold, by walking the field annotations from the two roots."""
    seen: dict[type, None] = {}

    def visit(tp: Any) -> None:
        if isinstance(tp, type) and issubclass(tp, BaseModel):
            if tp not in seen:
                seen[tp] = None
                for f in tp.model_fields.values():
                    visit(f.annotation)
            return
        for arg in get_args(tp):
            visit(arg)

    visit(WorkingMemory)
    visit(LongTermMemory)
    return list(seen)


def bare_sets(tp: Any) -> bool:
    """Whether a set with no serializer of its own sits anywhere in the annotation (Annotated[set, ...] has one)."""
    if get_origin(tp) is Annotated:
        return False
    if get_origin(tp) in SETS or tp in SETS:
        return True
    return any(bare_sets(a) for a in get_args(tp))


def set_fields() -> list[tuple[type[BaseModel], str, Any]]:
    """(model, field, element type) for each field whose own type is a set."""
    out = []
    for cls in models():
        for name, f in cls.model_fields.items():
            tp = f.annotation
            if get_origin(tp) in (typing.Union, types.UnionType):
                tp = next(a for a in get_args(tp) if a is not type(None))
            if get_origin(tp) in SETS:
                out.append((cls, name, get_args(tp)[0]))
    return out


def sample(elem: Any) -> set:
    if isinstance(elem, type) and issubclass(elem, enum.Enum):
        return set(elem)
    return {f"z{k}" for k in range(9, 0, -1)}


def test_the_walk_reaches_the_state_models():
    names = {c.__name__ for c in models()}
    assert {"WorkingMemory", "LongTermMemory", "Entity", "SuperentityPattern", "Episode", "Explanation"} <= names


def test_no_field_holds_a_set_without_a_sorted_serializer():
    bare = [f"{cls.__name__}.{name}" for cls in models() for name, f in cls.model_fields.items()
            if bare_sets(f.annotation) and not f.metadata]
    assert bare == []


def test_every_set_field_dumps_sorted_through_the_hashs_own_path():
    fields = set_fields()
    assert {(c.__name__, n) for c, n, _e in fields} >= {("SuperentityPattern", "rival_ids"), ("Entity", "category_tags"),
                                                        ("Episode", "signature"), ("Explanation", "index_keys")}
    for cls, name, elem in fields:
        values = sample(elem)
        got = field_adapter(cls, name).dump_python(values, mode="json")
        assert got == sorted(got) and len(got) == len(values), f"{cls.__name__}.{name} dumps in set order"
