"""What an imported model keeps between sessions (Oct 25), read back from its storage.

An import runner's storage (a files backend on the volume) holds the model's ledger, versions and snapshots. The ledger
also records what the runner itself would otherwise forget: the construction inputs the model was built from
(`import_loaded`), each import batch with its items (`import_batch`), every change of review policy (REVIEW_POLICY),
every proposal and the decisions on it, and the state of a run that paused for review (`awaiting_review`). These
functions turn those entries back into the runner's memory; nothing here writes.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from axelrod_wm.events.graph_update import GraphUpdateEvent
from axelrod_wm.repo.ledger import LedgerEntry, LedgerKind
from axelrod_wm.repo.review import Proposal, ProposalStatus

_ID = re.compile(r"^(PR|UPD|SE|TQ|D|ME-U)-(\d+)$")        # the ids the controller issues (model/ids.IdFactory)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def construction_files(dirs: list[Path], extra_files: list[Path], settings: dict[str, Any]) -> dict[str, str]:
    """Label -> SHA-256 of every input the base model is built from: the files under each construction and taxonomy
    folder (hidden files left out), the seed files, and the scenario's own settings (id, start, seed, focus)."""
    out = {"settings": _sha(json.dumps(settings, sort_keys=True, default=str).encode())}
    for d in dirs:
        for f in sorted(d.rglob("*")) if d.is_dir() else []:
            if f.is_file() and not any(part.startswith(".") for part in f.relative_to(d).parts):
                out[f"{d.name}/{f.relative_to(d).as_posix()}"] = _sha(f.read_bytes())
    for f in extra_files:
        out[f.name] = _sha(f.read_bytes())
    return out


def construction_digest(files: dict[str, str]) -> str:
    return _sha(json.dumps(files, sort_keys=True).encode())


def changed_files(old: dict[str, str], new: dict[str, str]) -> list[str]:
    """The labels that differ between two sets of construction inputs, sorted."""
    return sorted(k for k in {*old, *new} if old.get(k) != new.get(k))


def loaded_record(entries: list[LedgerEntry]) -> dict | None:
    """The newest `import_loaded` record: the inputs the stored model was built from."""
    for e in reversed(entries):
        if e.kind == LedgerKind.UPDATE and e.payload.get("state") == "import_loaded":
            return e.payload
    return None


def batch_entries(entries: list[LedgerEntry]) -> list[LedgerEntry]:
    return [e for e in entries if e.kind == LedgerKind.UPDATE and e.payload.get("state") == "import_batch"]


def regate_entries(entries: list[LedgerEntry]) -> list[LedgerEntry]:
    """The re-reads: items imported again whose pending changes were assessed again (`import_regate`)."""
    return [e for e in entries if e.kind == LedgerKind.UPDATE and e.payload.get("state") == "import_regate"]


def policy_at(entries: list[LedgerEntry], seq: int | None = None) -> str | None:
    """The review policy in force after the entries up to `seq` (all of them when None): the newest REVIEW_POLICY."""
    name = None
    for e in entries:
        if seq is not None and e.seq > seq:
            break
        if e.kind == LedgerKind.REVIEW_POLICY:
            name = e.payload["policy"]
    return name


def counters_from(entries: list[LedgerEntry]) -> dict[str, int]:
    """The controller's id counters (PR, UPD, SE, ...), from the ids the ledger holds, so a resumed controller never
    issues an id again."""
    out: dict[str, int] = {}
    for e in entries:
        for key in ("id", "update_id", "proposal_id"):
            m = _ID.match(str(e.payload.get(key) or ""))
            if m:
                out[m.group(1)] = max(out.get(m.group(1), 0), int(m.group(2)))
    return out


def decisions(entries: list[LedgerEntry]) -> dict[str, list[LedgerEntry]]:
    out: dict[str, list[LedgerEntry]] = {}
    for e in entries:
        if e.kind == LedgerKind.REVIEW_DECISION:
            out.setdefault(e.payload["proposal_id"], []).append(e)
    return out


def restore_proposals(entries: list[LedgerEntry]) -> dict[str, Proposal]:
    """Every proposal the ledger holds, as it stood at the end: created as logged, then each decision applied in
    order (an edit or a confidence change rewrites its event; a decision sets its status)."""
    from axelrod_wm.control.stage import with_confidence

    status = {"approved": ProposalStatus.APPROVED, "auto_applied": ProposalStatus.AUTO_APPLIED,
              "rejected": ProposalStatus.REJECTED, "deferred": ProposalStatus.DEFERRED}
    props = {e.payload["id"]: Proposal.model_validate(e.payload)
             for e in entries if e.kind == LedgerKind.PROPOSAL}
    for pid, decided in decisions(entries).items():
        p = props[pid]
        for e in decided:
            act, pl = e.payload["action"], e.payload
            if act in status:
                p.status, p.decided_by, p.note = status[act], pl["by"], pl.get("note")
                p.decided_at = e.recorded_at
                p.changeset_id = pl.get("changeset_id") or p.changeset_id
                if pl.get("day") is not None:
                    p.folded_day = pl["day"]
            elif act == "edited":
                p.edited_from = p.edited_from or p.event
                p.event = GraphUpdateEvent.model_validate(pl["diff"]["after"])
            elif act == "confidence":
                after = pl["diff"]["after"]
                p.event = with_confidence(p.event, after["confidence"],
                                          {int(i): v for i, v in after["ops"].items()}, after["ripple"])
            elif act == "regated":                  # assessed again after a better read of its document
                p.review_reasons, p.needs_review = pl["reasons"], bool(pl["reasons"])
            elif act == "queued":                   # left pending by a run that did not pause
                p.queued, p.due_day, p.update_id = True, pl["day"], pl["update_id"]
            else:                                   # "folded"
                p.folded_day, p.late_from = pl["day"], pl.get("late_from")
                p.changeset_id = pl.get("changeset_id") or p.changeset_id
    return props
