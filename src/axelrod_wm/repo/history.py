"""The world model's history, read as version control (§9; restructure).

Every change to the world model is a commit (a ChangeSet). A commit names the process that made it, the
memory it touched, a one-line message, and, for a vetted change, the proposal and who approved it:

    repository     the state (working and long-term memory) plus the ledger of commits
    commit         one ChangeSet; it bumps the state version by one
    pull request   a proposal: a translated market event, or a structural change, waiting for review
    review         vetting by a backend user (approve, reject, edit, defer); nothing unvetted that needs
                   review is ever committed
    log            the ledger's commits, newest first (`log`)
    show           one commit, grouped by the kind of thing it changed (`show`)
    diff           what changed between two versions (`diff`)
    checkout       an earlier version, read-only (snapshots plus replay; the timeline in the UI)
    branch         a thesis's scratch overlay: the forecast reads it and it is never merged

This module only reads. Writes go through repo/mutator.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from axelrod_wm.repo.ledger import LedgerKind
from axelrod_wm.repo.mutator import PROCESSES, ChangeSet

if TYPE_CHECKING:
    from axelrod_wm.engine.engine import Engine

# what a collection holds, in the words of the naming guide; collections not listed are "other state"
KINDS: dict[str, str] = {
    "wm.graph.entities": "entities",
    "wm.graph.subentities": "subentities",
    "wm.graph.interactions": "interactions",
    "wm.graph.instances": "superentity instances",
    "wm.graph.super_interactions": "super-interactions",
    "wm.hypotheses": "hypotheses",
    "wm.pending_refinements": "pending refinements",
    "wm.ripple_judgments": "ripple judgments",
    "wm.deviations.points": "daily values",
    "wm.channels": "channel states",
    "wm.activity_log": "activity records",
    "ltm.object_generalizations.taxonomy.nodes": "object generalizations",
    "ltm.interaction_generalizations.taxonomy.nodes": "interaction generalizations",
    "ltm.object_generalizations.patterns": "superentity patterns",
    "ltm.entity_memories": "entity memories",
    "ltm.correlation_frontier.entries": "correlation frontier",
    "ltm.prior_states.episodes": "episodes",
    "ltm.prior_states.explanations": "explanations",
}
# kinds whose individual ids are worth listing (structure, not bookkeeping)
STRUCTURAL = {"entities", "subentities", "interactions", "superentity instances", "superentity patterns",
              "object generalizations", "interaction generalizations", "hypotheses", "correlation frontier",
              "pending refinements"}
VERB = {"add": "added", "update": "updated", "remove": "removed", "put": "set", "append": "appended",
        "truncate": "trimmed", "clear": "cleared"}


class CommitSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    id: str
    cause: str
    process: str
    process_text: str
    memory: str
    message: str
    proposal_id: str | None = None
    vetted_by: str | None = None
    recorded_at: datetime
    counts: dict[str, dict[str, int]]          # kind -> verb -> how many
    touched: dict[str, dict[str, list[str]]]   # structural kind -> verb -> ids (at most 12 each)
    total_changes: int


def kind_of(collection: str) -> str:
    return KINDS.get(collection, "other state")


def summarize(cs: ChangeSet) -> CommitSummary:
    counts: dict[str, dict[str, int]] = {}
    touched: dict[str, dict[str, list[str]]] = {}
    for c in cs.changes:
        k = kind_of(c.collection)
        v = VERB.get(c.action, c.action)
        counts.setdefault(k, {}).setdefault(v, 0)
        counts[k][v] += 1
        if k in STRUCTURAL:
            ids = touched.setdefault(k, {}).setdefault(v, [])
            if c.id not in ids and len(ids) < 12:
                ids.append(c.id)
    process = cs.process or "other"
    return CommitSummary(version=cs.version_after, id=cs.id, cause=cs.cause, process=process,
                         process_text=PROCESSES.get(process, process), memory=cs.memory, message=cs.message or cs.cause,
                         proposal_id=cs.proposal_id, vetted_by=cs.vetted_by, recorded_at=cs.recorded_at,
                         counts=counts, touched=touched, total_changes=len(cs.changes))


def _commits_between(engine: Engine, after_version: int, upto_version: int) -> list[ChangeSet]:
    """The commits that produced versions after_version + 1 .. upto_version, oldest first."""
    if upto_version <= after_version:
        return []
    first = engine.snapshots.version_info(after_version + 1)
    last = engine.snapshots.version_info(upto_version)
    since = (first.seq - 1) if first is not None else 0
    stop = last.seq if last is not None else None
    out: list[ChangeSet] = []
    for e in engine.ledger.read(since):
        if stop is not None and e.seq > stop:
            break
        if e.kind != LedgerKind.CHANGESET:
            continue
        cs = ChangeSet.model_validate(e.payload)
        if after_version < cs.version_after <= upto_version and cs.version_after != cs.version_before:
            out.append(cs)
    return out


def log(engine: Engine, *, limit: int = 50, before_version: int | None = None,
        processes: set[str] | None = None, memory: str | None = None) -> list[CommitSummary]:
    """The newest commits first, at most `limit`, optionally only those of some processes or one memory.
    Walks back from `before_version` (exclusive; the current version + 1 by default)."""
    top = (engine.version if before_version is None else before_version - 1)
    out: list[CommitSummary] = []
    window = max(limit * 4, 64)
    hi = top
    while hi > 0 and len(out) < limit:
        lo = max(0, hi - window)
        batch = _commits_between(engine, lo, hi)
        if not batch and engine.snapshots.version_info(hi) is None:
            break                           # the ledger here starts after a cached history
        for cs in reversed(batch):
            if processes and (cs.process or "other") not in processes:
                continue
            if memory and cs.memory != memory:
                continue
            out.append(summarize(cs))
            if len(out) >= limit:
                break
        hi = lo
    return out


def show(engine: Engine, version: int) -> dict[str, Any] | None:
    """One commit in full: its summary and its structural changes with names."""
    commits = _commits_between(engine, version - 1, version)
    if not commits:
        return None
    cs = commits[-1]
    return {"commit": summarize(cs).model_dump(mode="json"), "changes": structural_changes(engine, [cs])}


def structural_changes(engine: Engine, commits: list[ChangeSet]) -> list[dict[str, Any]]:
    """The changes to structure (entities, values' definitions, interactions, superentities, kinds,
    hypotheses, the frontier), one row per (kind, id), net over the commits: an item added and then
    removed drops out, and an item updated many times is one row with every field that changed."""
    g = engine.wm.graph
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for cs in commits:
        for c in cs.changes:
            k = kind_of(c.collection)
            if k not in STRUCTURAL:
                continue
            key = (k, c.id)
            row = rows.get(key)
            if row is None:
                row = rows[key] = {"kind": k, "id": c.id, "action": None, "fields": [], "version": cs.version_after,
                                   "commit": cs.id, "cause": cs.cause}
            if c.action == "add":
                row["action"] = "added" if row["action"] != "removed" else "updated"
            elif c.action == "remove":
                row["action"] = None if row["action"] == "added" else "removed"
                if c.before:
                    row["was"] = c.before
            elif c.action == "update" and c.after and c.after.get("retired_at"):
                row["action"] = "retired"
            elif row["action"] is None:
                row["action"] = "updated"
            if c.action == "update" and c.after:
                for f in c.after:
                    if f not in row["fields"]:
                        row["fields"].append(f)
            if c.field and c.field not in row["fields"]:
                row["fields"].append(c.field)
            row["version"] = cs.version_after
    # names of records the commits removed, so links that ended with them still read in words
    gone = {i: row["was"]["name"] for (k, i), row in rows.items()
            if k == "subentities" and isinstance(row.get("was"), dict) and row["was"].get("name")}

    def sub_name(sid: str) -> str:
        sub = g.subentities.get(sid)
        return sub.name if sub is not None else gone.get(sid, sid)

    out = []
    for (k, i), row in sorted(rows.items(), key=lambda kv: (kv[1]["version"], kv[0])):
        if row["action"] is None:
            continue
        name = None
        if k == "entities" and i in g.entities:
            name = g.entities[i].name
        elif k == "subentities" and i in g.subentities:
            name = g.subentities[i].name
        elif k == "interactions" and i in g.interactions:
            inter = g.interactions[i]
            name = f"{sub_name(inter.source_id)} → {sub_name(inter.target_id)} ({inter.label})"
        elif k == "superentity patterns" and i in engine.ltm.object_generalizations.patterns:
            name = engine.ltm.object_generalizations.patterns[i].name
        elif k in ("object generalizations", "interaction generalizations"):
            tax = (engine.ltm.object_generalizations if k.startswith("object") else
                   engine.ltm.interaction_generalizations).taxonomy
            name = tax.nodes[i].name if i in tax.nodes else None
        was = row.pop("was", None) or {}
        if name is None and was:
            name = was.get("name") or (f"{was.get('source_id')} → {was.get('target_id')} ({was.get('label')})"
                                       if was.get("source_id") else None)
        row["name"] = name or i
        out.append(row)
    return out


def diff(engine: Engine, from_version: int, to_version: int | None = None) -> dict[str, Any]:
    """What changed between two versions: the commits in between, counted by process and memory, and
    the net structural changes."""
    to_version = engine.version if to_version is None else to_version
    commits = _commits_between(engine, from_version, to_version)
    by_process: dict[str, int] = {}
    by_memory: dict[str, int] = {}
    for cs in commits:
        by_process[cs.process or "other"] = by_process.get(cs.process or "other", 0) + 1
        by_memory[cs.memory or "none"] = by_memory.get(cs.memory or "none", 0) + 1
    return {"from_version": from_version, "to_version": to_version, "commits": len(commits),
            "by_process": by_process, "by_memory": by_memory,
            "changes": structural_changes(engine, commits)}
