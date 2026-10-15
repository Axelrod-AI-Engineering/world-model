"""The one writer: GraphMutator, transactions, and change sets (§7.7, D8).

Every change to working or long-term memory goes through a MutationTxn. Changes apply
immediately (later stages of the same event read them), are logged, and are rolled back if the
transaction raises. On exit the transaction commits one ChangeSet to the ledger and bumps the
state version, unless it touched only the forecast layer.

A change's `collection` is the dotted path of a field in WorkingMemory (`wm.`) or LongTermMemory
(`ltm.`). Daily data lives in keyed collections, and growing lists inside records change only
through `append` and `truncate`, so a day's change sets record only that day's new points and
entries and the ledger grows linearly with time.

# DECISION: change sets record new values only (`after`); the old values live in the in-memory undo
# log until commit. `before` stays in the model for callers that want to record an audit value.
# DECISION: an `update` may name a nested field with a dot ("forward.effect"), so the daily effect
# variance bump records the effect alone rather than the whole edge dynamics.
"""

from __future__ import annotations

import typing
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, TypeAdapter

from axelrod_wm.memory.entity_memory import EntityMemory
from axelrod_wm.memory.frontier import CoMovement
from axelrod_wm.memory.long_term import Episode
from axelrod_wm.memory.working import (
    ActivityRecord,
    ChannelState,
    DeviationPoint,
    ForecastStateView,
    PendingRefinement,
    RippleJudgment,
)
from axelrod_wm.model.entity import Entity, Subentity
from axelrod_wm.model.explanation import Explanation
from axelrod_wm.model.hypothesis import Hypothesis
from axelrod_wm.model.ids import entity_of
from axelrod_wm.model.interaction import Interaction
from axelrod_wm.model.superentity import SuperentityInstance, SuperentityPattern, SuperInteraction
from axelrod_wm.model.taxonomy import Generalization

if TYPE_CHECKING:
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory

Action = Literal["add", "update", "remove", "put", "append", "truncate", "clear"]


class Change(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Action
    collection: str          # dotted path, see the tables below
    id: str                  # key in a keyed collection; "_" for a singleton or a top-level list
    field: str | None = None # for append/truncate on a list field of a keyed record
    before: dict | None = None
    after: dict | None = None   # "put": {"value": ...}; "append": the appended item only;
                                # "truncate": {"keep_last": n}


class ChangeSet(BaseModel):
    """One commit to the world model: the changes of one transaction, and the version they produce.

    # DECISION (restructure): a commit says which process made it and which memory it touched, with a
    # one-line message and, for a vetted change, the proposal and the person who approved it. Older
    # ledgers without these fields still load (they default to empty).
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    cause: str               # event id, "ltm:<event id>", proposal id, "construction", "predict:<date>",
                             # "record:<date>", "distill:<date>", "close:<date>", ...
    version_before: int
    version_after: int
    changes: list[Change]
    id_counters_after: dict[str, int]
    recorded_at: datetime
    process: str = ""        # see PROCESSES
    memory: str = ""         # "working", "long_term", "both", or "forecast" (derived from the changes)
    message: str = ""        # one line for the log
    proposal_id: str | None = None
    vetted_by: str | None = None


# The processes that commit, by name (the commit log and the flowcharts use these).
PROCESSES: dict[str, str] = {
    "construction": "Construction: the world model is created from the construction files",
    "history": "History replay: the model reads three years of synthetic history (one long update run)",
    "day.predict": "Working memory: the day opens; yesterday's moves ripple through the interactions",
    "learn.working": "Working memory: one vetted event is read and folded into the current state",
    "learn.long_term": "Long-term memory: the event's lessons are registered (concepts, frontier, decisions)",
    "day.record": "Working memory: the day is recorded (every value's deviation and posterior)",
    "day.distill": "Long-term memory: the day is distilled (episodes, schemas, entity memories)",
    "day.close": "Working memory: the day closes (timing, hypotheses, pruning, the clock)",
    "structural": "Structure: a vetted structural change (collapse, expand, retire, a drawn edit)",
    "review": "Review: a decision on a proposal records its side effects",
    "intake": "Intake: an update run collects market events and moves the sources' cursors",
    "hypothesis": "Hypothesis frontier: a user adds a hypothesis or changes its status",
    "forecast": "Forecast layer: a thesis was posed or pinned",
    "evaluation": "Evaluation: outcomes score forecasts and decisions (track records)",
    "other": "Other",
}


def _brief(obj: Any) -> dict | None:
    """What the log keeps of a removed record: enough to name it (restructure)."""
    out = {k: getattr(obj, k) for k in ("name", "label", "source_id", "target_id", "pattern_id")
           if isinstance(getattr(obj, k, None), str)}
    return out or None


def memory_of(changes: list[Change]) -> str:
    """Which memory a commit touched, from its changes' collections."""
    roots = set()
    for c in changes:
        if c.collection.startswith("wm.forecast_layer"):
            roots.add("forecast")
        elif c.collection.startswith("wm."):
            roots.add("working")
        elif c.collection.startswith("ltm."):
            roots.add("long_term")
    if len(roots) > 1:
        roots.discard("forecast")
    if not roots:
        return ""
    if len(roots) == 1:
        return roots.pop()
    return "both"


def process_of_cause(cause: str) -> str:
    """The process behind a commit, for callers that did not name one."""
    for prefix, name in (("predict:", "day.predict"), ("record:", "day.record"), ("distill:", "day.distill"),
                         ("consolidation:", "day.distill"), ("close:", "day.close"), ("ltm:", "learn.long_term"),
                         ("construction", "construction"), ("seeds", "construction"), ("frontier_seeds", "construction"),
                         ("pose:", "forecast"), ("pin:", "forecast"), ("collect:", "intake"), ("cursors", "intake"),
                         ("cancel:", "intake"), ("late:", "review"), ("approve:", "review"),
                         ("hypothesis:", "hypothesis"), ("outcome:", "evaluation"), ("evaluation:", "evaluation")):
        if cause.startswith(prefix):
            return name
    return "other"


# Keyed records: path -> (model, key field or None when the caller supplies the key)
RECORDS: dict[str, tuple[type[BaseModel], str | None]] = {
    "wm.graph.entities": (Entity, "id"),
    "wm.graph.subentities": (Subentity, "id"),
    "wm.graph.interactions": (Interaction, "id"),
    "wm.graph.instances": (SuperentityInstance, "id"),
    "wm.graph.super_interactions": (SuperInteraction, "id"),
    "wm.deviations.points": (DeviationPoint, None),        # key "<subentity id>|<day>"
    "wm.channels": (ChannelState, "channel_id"),
    "wm.hypotheses": (Hypothesis, "id"),
    "wm.pending_refinements": (PendingRefinement, "id"),
    "wm.ripple_judgments": (RippleJudgment, None),          # key "<event id>|<subentity id>"
    "wm.activity_log": (ActivityRecord, None),              # key "<day>|<channel id>"
    "wm.forecast_layer.by_thesis": (ForecastStateView, "thesis_id"),
    "ltm.object_generalizations.taxonomy.nodes": (Generalization, "id"),
    "ltm.object_generalizations.patterns": (SuperentityPattern, "id"),
    "ltm.interaction_generalizations.taxonomy.nodes": (Generalization, "id"),
    "ltm.entity_memories": (EntityMemory, "entity_id"),
    "ltm.correlation_frontier.entries": (CoMovement, "id"),
    "ltm.prior_states.episodes": (Episode, "id"),
    "ltm.prior_states.explanations": (Explanation, "id"),
}

# Keyed values (put, remove)
VALUES: set[str] = {
    "wm.channel_phi",                  # key "<channel id>|<day>"
    "wm.fold_accumulators",
    "wm.source_cursors",
    "wm.late_queue",
    "wm.missing_relation_log",
    "ltm.correlation_frontier.blocked_until",
}

# Lists (append, clear)
LISTS: set[str] = {"wm.episode_buffer", "wm.pending_episode_tags"}

# Singletons (update with id "_")
SINGLETONS: set[str] = {
    "wm.clock",
    "wm.last_processed_day",
    "wm.ids",
    "wm.decision_variables",
    "wm.deviations.origin_date",
    "wm.deviations.first_kept_day",
    "wm.graph.entity_link_labels",
    "wm.forecast_layer.pose_counts",
    "wm.forecast_layer.pinned",
    "wm.forecast_layer.order",
    "ltm.object_generalizations.taxonomy.root_id",
    "ltm.object_generalizations.taxonomy.kind",
    "ltm.object_generalizations.super_interaction_labels",
    "ltm.object_generalizations.palettes",
    "ltm.interaction_generalizations.taxonomy.root_id",
    "ltm.interaction_generalizations.taxonomy.kind",
}

# Short names some engine code still uses; changes always record the dotted path.
ALIASES: dict[str, str] = {
    "entities": "wm.graph.entities",
    "subentities": "wm.graph.subentities",
    "interactions": "wm.graph.interactions",
    "instances": "wm.graph.instances",
    "super_interactions": "wm.graph.super_interactions",
    "hypotheses": "wm.hypotheses",
    "pending_refinements": "wm.pending_refinements",
    "patterns": "ltm.object_generalizations.patterns",
    "generalizations.object": "ltm.object_generalizations.taxonomy.nodes",
    "generalizations.interaction": "ltm.interaction_generalizations.taxonomy.nodes",
    "frontier": "ltm.correlation_frontier.entries",
    "episodes": "ltm.prior_states.episodes",
    "entity_memories": "ltm.entity_memories",
    "explanations": "ltm.prior_states.explanations",
    "forecast_layer": "wm.forecast_layer.by_thesis",
    "forecast_layer.pinned": "wm.forecast_layer.pinned",
    "forecast_layer.pose_counts": "wm.forecast_layer.pose_counts",
    "forecast_layer.order": "wm.forecast_layer.order",
    "ltm.frontier.blocked_until": "ltm.correlation_frontier.blocked_until",
}


def canonical(collection: str) -> str:
    return ALIASES.get(collection, collection)


_ADAPTERS: dict[tuple[type, str], TypeAdapter] = {}
_ITEM_ADAPTERS: dict[tuple[type, str], TypeAdapter] = {}


def field_adapter(cls: type[BaseModel], name: str) -> TypeAdapter:
    key = (cls, name)
    ad = _ADAPTERS.get(key)
    if ad is None:
        ad = _ADAPTERS[key] = TypeAdapter(cls.model_fields[name].annotation)
    return ad


def item_adapter(cls: type[BaseModel], name: str) -> TypeAdapter:
    """Adapter for the items of a list field, or the values of a dict field."""
    key = (cls, name)
    ad = _ITEM_ADAPTERS.get(key)
    if ad is None:
        ann = cls.model_fields[name].annotation
        args = typing.get_args(ann)
        origin = typing.get_origin(ann)
        if origin is dict or (args and len(args) == 2):
            inner = args[1]
        elif args:
            inner = args[0]
        else:
            inner = Any
        ad = _ITEM_ADAPTERS[key] = TypeAdapter(inner)
    return ad


def dump_value(cls: type[BaseModel], name: str, value: Any) -> Any:
    return field_adapter(cls, name).dump_python(value, mode="json")


def _resolve(root: Any, dotted: str) -> Any:
    cur = root
    if dotted:
        for part in dotted.split("."):
            cur = getattr(cur, part)
    return cur


class _Roots:
    """Resolves dotted paths against a (wm, ltm) pair."""

    def __init__(self, wm: WorkingMemory, ltm: LongTermMemory) -> None:
        self.wm = wm
        self.ltm = ltm

    def owner(self, path: str) -> tuple[Any, str]:
        root, _, rest = path.partition(".")
        base = self.wm if root == "wm" else self.ltm
        owner_path, _, attr = rest.rpartition(".")
        return _resolve(base, owner_path), attr

    def target(self, path: str) -> Any:
        owner, attr = self.owner(path)
        return getattr(owner, attr)


def _nested(obj: Any, field: str) -> tuple[Any, str]:
    """(object that owns the last part, attribute name) for a possibly dotted field."""
    if "." not in field:
        return obj, field
    head, _, last = field.rpartition(".")
    return _resolve(obj, head), last


def _note_touch(touched: set[str], collection: str, obj_id: str, obj: Any) -> None:
    if collection in ("wm.graph.entities", "ltm.entity_memories"):
        touched.add(obj_id)
    elif collection == "wm.graph.subentities":
        touched.add(entity_of(obj_id))
    elif collection == "wm.graph.interactions" and obj is not None:
        touched.add(entity_of(obj.source_id))
        touched.add(entity_of(obj.target_id))


class MutationTxn:
    """Collects changes. On exit, commits one ChangeSet to the ledger and bumps the version;
    on an exception, rolls back."""

    def __init__(self, mutator: GraphMutator, cause: str, now: datetime, meta: dict[str, Any] | None = None) -> None:
        self.mutator = mutator
        self.cause = cause
        self.now = now
        self.meta: dict[str, Any] = dict(meta or {})   # process, message, proposal_id, vetted_by
        self.changes: list[Change] = []
        self._undo: list[Any] = []
        self._touched: set[str] = set()
        self._ids_before = dict(mutator.state.wm.ids.counters)
        self._ids_dirty = False
        self.dirty: set[tuple[str, str, str | None]] = set()
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

    def _mark(self, collection: str, key: str, field: str | None = None) -> None:
        self.dirty.add((collection, key, field))

    # -- keyed records ---------------------------------------------------------------------
    def get(self, collection: str, obj_id: str) -> Any:
        return self.roots.target(canonical(collection)).get(obj_id)

    def add(self, collection: str, obj: BaseModel, key: str | None = None) -> None:
        collection = canonical(collection)
        model, key_field = RECORDS[collection]
        mapping = self.roots.target(collection)
        obj_id = key if key is not None else getattr(obj, key_field or "id")
        if obj_id in mapping:
            raise KeyError(f"{collection}: {obj_id} already exists")
        mapping[obj_id] = obj
        self._undo.append(lambda m=mapping, k=obj_id: m.pop(k, None))
        self.changes.append(Change(action="add", collection=collection, id=obj_id, after=obj.model_dump(mode="json")))
        self._mark(collection, obj_id)
        _note_touch(self._touched, collection, obj_id, obj)

    def replace(self, collection: str, obj: BaseModel, key: str | None = None) -> None:
        """Add, or replace a record whole (recorded as a remove and an add)."""
        collection = canonical(collection)
        _, key_field = RECORDS[collection]
        obj_id = key if key is not None else getattr(obj, key_field or "id")
        if obj_id in self.roots.target(collection):
            self.remove(collection, obj_id)
        self.add(collection, obj, key=obj_id)

    def update(self, collection: str, obj_id: str, **fields: Any) -> None:
        collection = canonical(collection)
        if collection in SINGLETONS:
            if set(fields) != {"value"}:
                raise TypeError(f"singleton {collection} takes update(..., value=...)")
            self.set(collection, fields["value"])
            return
        mapping = self.roots.target(collection)
        obj = mapping[obj_id]
        after = {}
        old_vals = []
        for name, value in fields.items():
            owner, attr = _nested(obj, name)
            old = getattr(owner, attr)
            old_vals.append((owner, attr, old))
            after[name] = dump_value(type(owner), attr, value)
            setattr(owner, attr, value)

        def undo(vals=old_vals) -> None:
            for o, a, v in reversed(vals):
                setattr(o, a, v)

        self._undo.append(undo)
        self.changes.append(Change(action="update", collection=collection, id=obj_id, after=after))
        if collection in FIELD_HASHED:
            for name in fields:
                self._mark(collection, obj_id, name.split(".")[0])
        else:
            self._mark(collection, obj_id)
        _note_touch(self._touched, collection, obj_id, obj)

    def remove(self, collection: str, obj_id: str) -> None:
        collection = canonical(collection)
        mapping = self.roots.target(collection)
        if obj_id not in mapping:
            return
        obj = mapping.pop(obj_id)
        self._undo.append(lambda m=mapping, k=obj_id, o=obj: m.__setitem__(k, o))
        self.changes.append(Change(action="remove", collection=collection, id=obj_id, before=_brief(obj)))
        self._mark(collection, obj_id)
        _note_touch(self._touched, collection, obj_id, obj if collection in RECORDS else None)

    # -- keyed values ----------------------------------------------------------------------
    def put(self, collection: str, key: str, value: Any) -> None:
        collection = canonical(collection)
        owner, attr = self.roots.owner(collection)
        mapping = getattr(owner, attr)
        had = key in mapping
        old = mapping.get(key)
        mapping[key] = value
        if had:
            self._undo.append(lambda m=mapping, k=key, v=old: m.__setitem__(k, v))
        else:
            self._undo.append(lambda m=mapping, k=key: m.pop(k, None))
        js = item_adapter(type(owner), attr).dump_python(value, mode="json")
        self.changes.append(Change(action="put", collection=collection, id=key, after={"value": js}))
        self._mark(collection, key)

    # -- lists -----------------------------------------------------------------------------
    def append(self, collection: str, item: Any, *, key: str | None = None, field: str | None = None) -> None:
        """Append to a top-level list (`key` None) or to a list field of a keyed record."""
        collection = canonical(collection)
        if key is None:
            owner, attr = self.roots.owner(collection)
            lst = getattr(owner, attr)
            js = item_adapter(type(owner), attr).dump_python(item, mode="json")
            obj_id = "_"
        else:
            if field is None:
                raise TypeError("append to a record needs a field")
            obj = self.roots.target(collection)[key]
            owner, attr = _nested(obj, field)
            lst = getattr(owner, attr)
            js = item_adapter(type(owner), attr).dump_python(item, mode="json")
            obj_id = key
        n = len(lst)
        lst.append(item)
        self._undo.append(lambda c=lst, k=n: c.__delitem__(slice(k, None)))
        if not isinstance(js, dict):
            js = {"value": js}
        self.changes.append(Change(action="append", collection=collection, id=obj_id, field=field, after=js))
        if key is not None and collection in FIELD_HASHED:
            self._mark(collection, obj_id, field.split(".")[0] if field else None)
        else:
            self._mark(collection, obj_id)
        if key is not None:
            _note_touch(self._touched, collection, key, self.roots.target(collection).get(key))

    def truncate(self, collection: str, key: str, field: str, keep_last: int) -> None:
        collection = canonical(collection)
        obj = self.roots.target(collection)[key]
        owner, attr = _nested(obj, field)
        lst = getattr(owner, attr)
        if len(lst) <= keep_last:
            return
        cut = len(lst) - keep_last
        removed = lst[:cut]
        del lst[:cut]
        self._undo.append(lambda c=lst, r=removed: c.__setitem__(slice(0, 0), r))
        self.changes.append(Change(action="truncate", collection=collection, id=key, field=field,
                                   after={"keep_last": int(keep_last)}))
        if collection in FIELD_HASHED:
            self._mark(collection, key, field.split(".")[0])
        else:
            self._mark(collection, key)

    def append_to(self, collection: str, obj_id: str, field: str, *items: Any, keep_last: int | None = None) -> None:
        """Append items to a record's list field, then keep at most `keep_last` of them."""
        for item in items:
            self.append(collection, item, key=obj_id, field=field)
        if keep_last is not None:
            self.truncate(collection, obj_id, field, keep_last)

    def clear(self, collection: str) -> None:
        collection = canonical(collection)
        owner, attr = self.roots.owner(collection)
        cur = getattr(owner, attr)
        if not cur:
            return
        saved = list(cur) if isinstance(cur, list) else dict(cur)
        cur.clear()
        if isinstance(cur, list):
            self._undo.append(lambda c=cur, s=saved: c.extend(s))
        else:
            self._undo.append(lambda c=cur, s=saved: c.update(s))
        self.changes.append(Change(action="clear", collection=collection, id="_"))
        if collection in VALUES:
            for k in saved:
                self._mark(collection, k)
        else:
            self._mark(collection, "_")

    # -- singletons ------------------------------------------------------------------------
    def set(self, path: str, value: Any) -> None:
        path = canonical(path)
        owner, attr = self.roots.owner(path)
        cls = type(owner)
        old = getattr(owner, attr)
        setattr(owner, attr, value)
        self._undo.append(lambda o=owner, a=attr, v=old: setattr(o, a, v))
        self.changes.append(Change(action="update", collection=path, id="_",
                                   after={"value": dump_value(cls, attr, value)}))
        self._mark(path, "_")

    # -- lifecycle -------------------------------------------------------------------------
    def rollback(self) -> None:
        for undo in reversed(self._undo):
            undo()
        self.mutator.state.wm.ids.counters = dict(self._ids_before)
        self._undo.clear()
        self.changes.clear()

    def ids_changed(self) -> bool:
        return self._ids_dirty and self.mutator.state.wm.ids.counters != self._ids_before


# Records large enough that the hasher keeps one digest per field (§9).
FIELD_HASHED: set[str] = {
    "wm.graph.entities",
    "wm.graph.subentities",
    "wm.graph.interactions",
    "wm.graph.instances",
    "ltm.object_generalizations.taxonomy.nodes",
    "ltm.object_generalizations.patterns",
    "ltm.interaction_generalizations.taxonomy.nodes",
    "ltm.entity_memories",
    "ltm.correlation_frontier.entries",
}


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

    def begin(self, cause: str, at: datetime | None = None, *, now: datetime | None = None,
              process: str | None = None, message: str | None = None, proposal_id: str | None = None,
              vetted_by: str | None = None) -> _TxnContext:
        """Use as a context manager. Nested calls join the open transaction. `at` is the simulated
        time the change set is stamped with (§7.8); `now` is an older name for it. `process`, `message`,
        `proposal_id`, and `vetted_by` describe the commit for the log."""
        if self._active is not None:
            return _TxnContext(self, self._active, outer=False)
        stamp = at or now or self.state.wm.clock
        meta = {k: v for k, v in (("process", process), ("message", message), ("proposal_id", proposal_id),
                                  ("vetted_by", vetted_by)) if v}
        txn = MutationTxn(self, cause, stamp, meta)
        self._active = txn
        return _TxnContext(self, txn, outer=True)

    def commit(self, txn: MutationTxn) -> ChangeSet | None:
        st = self.state
        if not txn.changes and not txn.ids_changed():
            return None
        forecast_only = bool(txn.changes) and all(c.collection.startswith("wm.forecast_layer")
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
            txn.dirty.add(("wm.ids", "_", None))
        cs = ChangeSet(id=cs_id, cause=txn.cause, version_before=version_before, version_after=version_after,
                       changes=txn.changes, id_counters_after=dict(st.wm.ids.counters), recorded_at=txn.now,
                       process=txn.meta.get("process") or process_of_cause(txn.cause),
                       memory="forecast" if forecast_only else memory_of(txn.changes),
                       message=txn.meta.get("message", ""), proposal_id=txn.meta.get("proposal_id"),
                       vetted_by=txn.meta.get("vetted_by"))
        st.on_commit(cs, txn, bumped=not forecast_only)
        self.last_changeset = cs
        return cs


# ---------------------------------------------------------------------------------------------
# Replay (§9): apply a JSON change to a (wm, ltm) pair
# ---------------------------------------------------------------------------------------------

def apply_change(wm: WorkingMemory, ltm: LongTermMemory, change: Change) -> None:
    roots = _Roots(wm, ltm)
    col = change.collection
    act = change.action
    if col in RECORDS:
        model, _ = RECORDS[col]
        mapping = roots.target(col)
        if act == "add":
            mapping[change.id] = model.model_validate(change.after)
        elif act == "remove":
            mapping.pop(change.id, None)
        elif act == "update":
            obj = mapping[change.id]
            for name, val in (change.after or {}).items():
                owner, attr = _nested(obj, name)
                setattr(owner, attr, field_adapter(type(owner), attr).validate_python(val))
        elif act == "append":
            obj = mapping[change.id]
            owner, attr = _nested(obj, change.field or "")
            val = change.after
            ad = item_adapter(type(owner), attr)
            try:
                item = ad.validate_python(val)
            except Exception:
                item = ad.validate_python((val or {}).get("value"))
            getattr(owner, attr).append(item)
        elif act == "truncate":
            obj = mapping[change.id]
            owner, attr = _nested(obj, change.field or "")
            lst = getattr(owner, attr)
            keep = int((change.after or {})["keep_last"])
            if len(lst) > keep:
                del lst[: len(lst) - keep]
        else:
            raise ValueError(f"{act} is not valid on records ({col})")
        return
    if col in VALUES:
        owner, attr = roots.owner(col)
        mapping = getattr(owner, attr)
        if act == "put":
            mapping[change.id] = item_adapter(type(owner), attr).validate_python((change.after or {}).get("value"))
        elif act == "remove":
            mapping.pop(change.id, None)
        elif act == "clear":
            mapping.clear()
        else:
            raise ValueError(f"{act} is not valid on keyed values ({col})")
        return
    if col in LISTS:
        owner, attr = roots.owner(col)
        lst = getattr(owner, attr)
        if act == "append":
            val = change.after
            ad = item_adapter(type(owner), attr)
            try:
                item = ad.validate_python(val)
            except Exception:
                item = ad.validate_python((val or {}).get("value"))
            lst.append(item)
        elif act == "clear":
            lst.clear()
        else:
            raise ValueError(f"{act} is not valid on lists ({col})")
        return
    if col in SINGLETONS:
        owner, attr = roots.owner(col)
        val = (change.after or {}).get("value")
        setattr(owner, attr, field_adapter(type(owner), attr).validate_python(val))
        return
    raise KeyError(f"unknown collection {col!r}")


def apply_changeset(wm: WorkingMemory, ltm: LongTermMemory, cs: ChangeSet) -> None:
    for ch in cs.changes:
        apply_change(wm, ltm, ch)
    wm.ids.counters = dict(cs.id_counters_after)
