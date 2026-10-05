"""The one writer: GraphMutator, transactions, and change sets (§7.7, D8).

Every change to working or long-term memory goes through a MutationTxn. Changes apply
immediately (later stages of the same event read them), are logged with before/after values,
and are rolled back if the transaction raises. On exit the transaction commits one ChangeSet
to the ledger and bumps the state version, unless it touched only the forecast layer.

# DECISION: besides whole-field "set" updates, a Change may carry mode "append" (extend a list
# field) or "merge" (deep-merge a dict field). This keeps the ledger compact for growing fields
# such as time states and the deviation history. Replay (§9) understands all three modes.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, TypeAdapter

from axelrod_wm.core.entity import Entity, EntityMemory, Subentity
from axelrod_wm.core.hypothesis import Hypothesis
from axelrod_wm.core.ids import entity_of
from axelrod_wm.core.interaction import Interaction
from axelrod_wm.core.superentity import SuperentityInstance, SuperentityPattern, SuperInteraction
from axelrod_wm.core.taxonomy import Generalization
from axelrod_wm.engine.explain_records import Explanation
from axelrod_wm.memory.episodes import Episode
from axelrod_wm.memory.frontier import CoMovement
from axelrod_wm.memory.working import ForecastStateView, PendingRefinement

if TYPE_CHECKING:
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory


class Change(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["add", "update", "remove"]
    collection: str          # see the list below
    id: str
    before: dict | None = None
    after: dict | None = None
    mode: Literal["set", "append", "merge"] = "set"


class ChangeSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    cause: str               # event id, proposal id, "construction", "consolidation:<date>", ...
    version_before: int
    version_after: int
    changes: list[Change]
    id_counters_after: dict[str, int]
    recorded_at: datetime


# collection -> (root, dotted path to the dict, model class)
KEYED: dict[str, tuple[str, str, type[BaseModel]]] = {
    "entities": ("wm", "graph.entities", Entity),
    "subentities": ("wm", "graph.subentities", Subentity),
    "interactions": ("wm", "graph.interactions", Interaction),
    "instances": ("wm", "graph.instances", SuperentityInstance),
    "super_interactions": ("wm", "graph.super_interactions", SuperInteraction),
    "hypotheses": ("wm", "hypotheses", Hypothesis),
    "pending_refinements": ("wm", "pending_refinements", PendingRefinement),
    "patterns": ("ltm", "patterns.patterns", SuperentityPattern),
    "generalizations.object": ("ltm", "object_taxonomy.nodes", Generalization),
    "generalizations.interaction": ("ltm", "interaction_taxonomy.nodes", Generalization),
    "frontier": ("ltm", "frontier.entries", CoMovement),
    "episodes": ("ltm", "episodes.episodes", Episode),
    "entity_memories": ("ltm", "entity_memories", EntityMemory),
    "explanations": ("ltm", "explanations.explanations", Explanation),
    "forecast_layer": ("wm", "forecast_layer.by_thesis", ForecastStateView),
}

KEY_FIELD = {"entity_memories": "entity_id", "forecast_layer": "thesis_id"}

# singleton path -> (root, dotted owner path, attribute)
SINGLETONS: dict[str, tuple[str, str, str]] = {
    "wm.clock": ("wm", "", "clock"),
    "wm.deviations": ("wm", "", "deviations"),
    "wm.activity_log": ("wm", "", "activity_log"),
    "wm.fold_accumulators": ("wm", "", "fold_accumulators"),
    "wm.episode_buffer": ("wm", "", "episode_buffer"),
    "wm.ids": ("wm", "", "ids"),
    "wm.decision_variables": ("wm", "", "decision_variables"),
    "wm.pending_episode_tags": ("wm", "", "pending_episode_tags"),
    "wm.last_consolidated": ("wm", "", "last_consolidated"),
    "wm.missing_relation_log": ("wm", "", "missing_relation_log"),
    "wm.graph.entity_link_labels": ("wm", "graph", "entity_link_labels"),
    "ltm.reliability": ("ltm", "", "reliability"),
    "ltm.frontier.blocked_until": ("ltm", "frontier", "blocked_until"),
    "ltm.attributes": ("ltm", "", "attributes"),
    "ltm.patterns.super_interaction_labels": ("ltm", "patterns", "super_interaction_labels"),
    "ltm.patterns.palettes": ("ltm", "patterns", "palettes"),
    "ltm.object_taxonomy.root_id": ("ltm", "object_taxonomy", "root_id"),
    "ltm.interaction_taxonomy.root_id": ("ltm", "interaction_taxonomy", "root_id"),
    "forecast_layer.pinned": ("wm", "forecast_layer", "pinned"),
    "forecast_layer.pose_counts": ("wm", "forecast_layer", "pose_counts"),
    "forecast_layer.order": ("wm", "forecast_layer", "order"),
}

_ADAPTERS: dict[tuple[type, str], TypeAdapter] = {}


def field_adapter(cls: type[BaseModel], name: str) -> TypeAdapter:
    key = (cls, name)
    ad = _ADAPTERS.get(key)
    if ad is None:
        ad = _ADAPTERS[key] = TypeAdapter(cls.model_fields[name].annotation)
    return ad


def _list_item_adapter(cls: type[BaseModel], name: str) -> TypeAdapter:
    return field_adapter(cls, name)


def dump_value(cls: type[BaseModel], name: str, value: Any) -> Any:
    return field_adapter(cls, name).dump_python(value, mode="json")


def _resolve(root: Any, dotted: str) -> Any:
    cur = root
    if dotted:
        for part in dotted.split("."):
            cur = getattr(cur, part)
    return cur


class _Roots:
    """Resolves collection and singleton paths against a (wm, ltm) pair."""

    def __init__(self, wm: WorkingMemory, ltm: LongTermMemory) -> None:
        self.wm = wm
        self.ltm = ltm

    def root(self, name: str) -> Any:
        return self.wm if name == "wm" else self.ltm

    def mapping(self, collection: str) -> dict[str, Any]:
        root, path, _ = KEYED[collection]
        return _resolve(self.root(root), path)

    def owner(self, path: str) -> tuple[Any, str]:
        root, owner_path, attr = SINGLETONS[path]
        return _resolve(self.root(root), owner_path), attr


def _deep_merge(target: dict, patch: dict, undo: dict | None) -> None:
    """Merge `patch` into `target` in place. A None value deletes the key. If `undo` is given it
    receives the previous values (None for keys that did not exist)."""
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(target.get(k), dict):
            sub_undo: dict | None = {} if undo is not None else None
            _deep_merge(target[k], v, sub_undo)
            if undo is not None:
                undo[k] = sub_undo
        else:
            if undo is not None:
                undo[k] = copy.deepcopy(target[k]) if k in target else None
            if v is None:
                target.pop(k, None)
            else:
                target[k] = copy.deepcopy(v) if isinstance(v, (dict, list)) else v


def _jsonify(obj: Any) -> Any:
    return json.loads(json.dumps(obj, default=_json_default))


def _json_default(o: Any) -> Any:
    if isinstance(o, BaseModel):
        return o.model_dump(mode="json")
    if isinstance(o, (set, frozenset)):
        return sorted(o, key=str)
    if hasattr(o, "isoformat"):
        return o.isoformat()
    if isinstance(o, tuple):
        return list(o)
    raise TypeError(type(o).__name__)


class MutationTxn:
    """Collects changes. On exit, commits one ChangeSet to the ledger and bumps the version;
    on an exception, rolls back."""

    def __init__(self, mutator: GraphMutator, cause: str, now: datetime) -> None:
        self.mutator = mutator
        self.cause = cause
        self.now = now
        self.changes: list[Change] = []
        self._undo: list[Any] = []
        self._touched: set[str] = set()
        self._ids_before = dict(mutator.state.wm.ids.counters)
        self._ids_dirty = False
        self.dirty: set[tuple[str, str]] = set()
        self.result: ChangeSet | None = None

    # -- helpers ---------------------------------------------------------------------------
    @property
    def roots(self) -> _Roots:
        return _Roots(self.mutator.state.wm, self.mutator.state.ltm)

    def new_id(self, prefix: str) -> str:
        self._ids_dirty = True
        return self.mutator.state.wm.ids.next(prefix)

    def touch_entities(self, entity_ids: set[str] | list[str]) -> None:
        self._touched.update(e for e in entity_ids if e)

    def touched_entities(self) -> set[str]:
        return set(self._touched)

    def _note_touch(self, collection: str, obj_id: str, obj: Any) -> None:
        if collection in ("entities", "entity_memories"):
            self._touched.add(obj_id)
        elif collection == "subentities":
            self._touched.add(entity_of(obj_id))
        elif collection == "interactions" and obj is not None:
            self._touched.add(entity_of(obj.source_id))
            self._touched.add(entity_of(obj.target_id))

    # -- keyed collections ----------------------------------------------------------------
    def get(self, collection: str, obj_id: str) -> Any:
        return self.roots.mapping(collection).get(obj_id)

    def add(self, collection: str, obj: BaseModel) -> None:
        mapping = self.roots.mapping(collection)
        obj_id = getattr(obj, KEY_FIELD.get(collection, "id"))
        if obj_id in mapping:
            raise KeyError(f"{collection}: {obj_id} already exists")
        mapping[obj_id] = obj
        self._undo.append(lambda m=mapping, k=obj_id: m.pop(k, None))
        self.changes.append(Change(action="add", collection=collection, id=obj_id,
                                   after=obj.model_dump(mode="json")))
        self.dirty.add((collection, obj_id))
        self._note_touch(collection, obj_id, obj)

    def update(self, collection: str, obj_id: str, **fields: Any) -> None:
        mapping = self.roots.mapping(collection)
        obj = mapping[obj_id]
        cls = type(obj)
        before, after = {}, {}
        old_vals = {}
        for name, value in fields.items():
            old = getattr(obj, name)
            old_vals[name] = old
            before[name] = dump_value(cls, name, old)
            after[name] = dump_value(cls, name, value)
            setattr(obj, name, value)

        def undo(o=obj, vals=old_vals) -> None:
            for n, v in vals.items():
                setattr(o, n, v)

        self._undo.append(undo)
        self.changes.append(Change(action="update", collection=collection, id=obj_id,
                                   before=before, after=after))
        self.dirty.add((collection, obj_id))
        self._note_touch(collection, obj_id, obj)

    def append_to(self, collection: str, obj_id: str, field: str, *items: Any, keep_last: int | None = None) -> None:
        """Extend a list field of a keyed object. With keep_last, older items are trimmed
        (recorded as a set of the field instead)."""
        mapping = self.roots.mapping(collection)
        obj = mapping[obj_id]
        cls = type(obj)
        cur = getattr(obj, field)
        if keep_last is not None and len(cur) + len(items) > keep_last:
            new_val = (list(cur) + list(items))[-keep_last:]
            self.update(collection, obj_id, **{field: new_val})
            return
        old_len = len(cur)
        cur.extend(items)
        self._undo.append(lambda c=cur, n=old_len: c.__delitem__(slice(n, None)))
        self.changes.append(Change(action="update", collection=collection, id=obj_id, mode="append",
                                   before={field: old_len},
                                   after={field: dump_value(cls, field, list(items))}))
        self.dirty.add((collection, obj_id))
        self._note_touch(collection, obj_id, obj)

    def remove(self, collection: str, obj_id: str) -> None:
        mapping = self.roots.mapping(collection)
        if obj_id not in mapping:
            return
        obj = mapping.pop(obj_id)
        self._undo.append(lambda m=mapping, k=obj_id, o=obj: m.__setitem__(k, o))
        self.changes.append(Change(action="remove", collection=collection, id=obj_id,
                                   before=obj.model_dump(mode="json")))
        self.dirty.add((collection, obj_id))
        self._note_touch(collection, obj_id, obj)

    # -- singletons ------------------------------------------------------------------------
    def set(self, path: str, value: Any) -> None:
        owner, attr = self.roots.owner(path)
        cls = type(owner)
        old = getattr(owner, attr)
        before = {"value": dump_value(cls, attr, old)}
        setattr(owner, attr, value)
        self._undo.append(lambda o=owner, a=attr, v=old: setattr(o, a, v))
        self.changes.append(Change(action="update", collection=path, id="_", before=before,
                                   after={"value": dump_value(cls, attr, value)}))
        self._mark_singleton(path, None)

    def append(self, path: str, item: Any) -> None:
        """For list singletons, e.g. "wm.episode_buffer"."""
        owner, attr = self.roots.owner(path)
        cls = type(owner)
        cur = getattr(owner, attr)
        old_len = len(cur)
        cur.append(item)
        self._undo.append(lambda c=cur, n=old_len: c.__delitem__(slice(n, None)))
        self.changes.append(Change(action="update", collection=path, id="_", mode="append",
                                   before={"value": old_len},
                                   after={"value": dump_value(cls, attr, [item])}))
        self._mark_singleton(path, None)

    def merge(self, path: str, patch: dict) -> None:
        """Deep-merge a patch into a dict-valued singleton (or a model's dict fields).
        A None value deletes a key."""
        owner, attr = self.roots.owner(path)
        cur = getattr(owner, attr)
        undo: dict = {}
        if isinstance(cur, BaseModel):
            for k, v in patch.items():
                sub_undo: dict = {}
                field_val = getattr(cur, k)
                if isinstance(field_val, dict) and isinstance(v, dict):
                    _deep_merge(field_val, v, sub_undo)
                    undo[k] = sub_undo
                else:
                    undo[k] = field_val
                    setattr(cur, k, v)
        else:
            _deep_merge(cur, patch, undo)

        def do_undo(c=cur, u=undo) -> None:
            if isinstance(c, BaseModel):
                for k, v in u.items():
                    fv = getattr(c, k)
                    if isinstance(fv, dict) and isinstance(v, dict):
                        _deep_merge(fv, v, None)
                    else:
                        setattr(c, k, v)
            else:
                _deep_merge(c, u, None)

        self._undo.append(do_undo)
        self.changes.append(Change(action="update", collection=path, id="_", mode="merge",
                                   before={"value": _jsonify(undo)}, after={"value": _jsonify(patch)}))
        self._mark_singleton(path, patch)

    def _mark_singleton(self, path: str, patch: dict | None) -> None:
        if path == "wm.deviations" and patch is not None:
            for k, v in patch.items():
                if k in ("z", "innovation") and isinstance(v, dict):
                    for sid in v:
                        self.dirty.add((f"wm.deviations.{k}", sid))
                else:
                    self.dirty.add(("wm.deviations.meta", "_"))
        elif path == "wm.deviations":
            self.dirty.add(("wm.deviations.meta", "_"))
            self.dirty.add(("wm.deviations.z", "*"))
            self.dirty.add(("wm.deviations.innovation", "*"))
        else:
            self.dirty.add((path, "_"))

    # -- lifecycle -------------------------------------------------------------------------
    def rollback(self) -> None:
        for undo in reversed(self._undo):
            undo()
        self.mutator.state.wm.ids.counters = dict(self._ids_before)
        self._undo.clear()
        self.changes.clear()

    def ids_changed(self) -> bool:
        return self._ids_dirty and self.mutator.state.wm.ids.counters != self._ids_before


class _TxnContext:
    def __init__(self, mutator: GraphMutator, txn: MutationTxn, outer: bool) -> None:
        self.mutator = mutator
        self.txn = txn
        self.outer = outer

    def __enter__(self) -> MutationTxn:
        return self.txn

    def __exit__(self, exc_type, exc, tb) -> bool:
        if not self.outer:
            return False
        try:
            if exc_type is not None:
                self.txn.rollback()
                return False
            self.txn.result = self.mutator.commit(self.txn)
            return False
        finally:
            self.mutator._active = None


class GraphMutator:
    """The single writer. `state` is the engine (anything with wm, ltm, version, ledger, ...)."""

    def __init__(self, state: Any) -> None:
        self.state = state
        self._active: MutationTxn | None = None
        self.last_changeset: ChangeSet | None = None

    @property
    def active(self) -> MutationTxn | None:
        return self._active

    def begin(self, cause: str, now: datetime | None = None) -> _TxnContext:
        """Use as a context manager. Nested calls join the open transaction."""
        if self._active is not None:
            return _TxnContext(self, self._active, outer=False)
        txn = MutationTxn(self, cause, now or self.state.wm.clock)
        self._active = txn
        return _TxnContext(self, txn, outer=True)

    def commit(self, txn: MutationTxn) -> ChangeSet | None:
        st = self.state
        if not txn.changes and not txn.ids_changed():
            return None
        forecast_only = bool(txn.changes) and all(c.collection.startswith("forecast_layer")
                                                  for c in txn.changes) and not txn.ids_changed()
        version_before = st.version
        if forecast_only:
            cs_id = f"CS-FL-{st.ledger.next_seq:06d}"
            version_after = version_before
        else:
            cs_id = st.wm.ids.next("CS")
            txn._ids_dirty = True
            version_after = version_before + 1
        if txn.ids_changed() or not forecast_only:
            txn.dirty.add(("wm.ids", "_"))
        cs = ChangeSet(id=cs_id, cause=txn.cause, version_before=version_before, version_after=version_after,
                       changes=txn.changes, id_counters_after=dict(st.wm.ids.counters), recorded_at=txn.now)
        st.on_commit(cs, txn, bumped=not forecast_only)
        self.last_changeset = cs
        return cs


# ---------------------------------------------------------------------------------------------
# Replay (§9): apply a JSON change to a (wm, ltm) pair
# ---------------------------------------------------------------------------------------------

def _validate_merge_target(cls: type[BaseModel], attr: str, current: Any, patch_json: Any) -> Any:
    cur_json = dump_value(cls, attr, current)
    if isinstance(current, BaseModel):
        for k, v in patch_json.items():
            if isinstance(v, dict) and isinstance(cur_json.get(k), dict):
                _deep_merge(cur_json[k], v, None)
            else:
                cur_json[k] = v
    else:
        _deep_merge(cur_json, patch_json, None)
    return field_adapter(cls, attr).validate_python(cur_json)


def apply_change(wm: WorkingMemory, ltm: LongTermMemory, change: Change) -> None:
    roots = _Roots(wm, ltm)
    if change.collection in KEYED:
        _, _, model = KEYED[change.collection]
        mapping = roots.mapping(change.collection)
        if change.action == "add":
            mapping[change.id] = model.model_validate(change.after)
        elif change.action == "remove":
            mapping.pop(change.id, None)
        else:
            obj = mapping[change.id]
            cls = type(obj)
            for name, val in (change.after or {}).items():
                if change.mode == "append":
                    items = field_adapter(cls, name).validate_python(val)
                    getattr(obj, name).extend(items)
                elif change.mode == "merge":
                    setattr(obj, name, _validate_merge_target(cls, name, getattr(obj, name), val))
                else:
                    setattr(obj, name, field_adapter(cls, name).validate_python(val))
        return
    if change.collection in SINGLETONS:
        owner, attr = roots.owner(change.collection)
        cls = type(owner)
        val = (change.after or {}).get("value")
        if change.mode == "append":
            items = field_adapter(cls, attr).validate_python(val)
            getattr(owner, attr).extend(items)
        elif change.mode == "merge":
            setattr(owner, attr, _validate_merge_target(cls, attr, getattr(owner, attr), val))
        else:
            setattr(owner, attr, field_adapter(cls, attr).validate_python(val))
        return
    raise KeyError(f"unknown collection {change.collection!r}")


def apply_changeset(wm: WorkingMemory, ltm: LongTermMemory, cs: ChangeSet) -> None:
    for ch in cs.changes:
        apply_change(wm, ltm, ch)
    wm.ids.counters = dict(cs.id_counters_after)
