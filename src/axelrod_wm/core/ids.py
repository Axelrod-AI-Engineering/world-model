"""Deterministic id generation (§6.1).

Runtime ids are ``<prefix>-<6-digit counter>``. The counters live in working memory and are
saved in every ChangeSet, so a repeated run produces identical ids. Never use uuids.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

PREFIXES = {
    "int": "interaction",
    "pat": "pattern",
    "inst": "instance",
    "sup": "super-interaction",
    "GUE": "graph update event",
    "PR": "proposal",
    "H": "hypothesis",
    "EP": "episode",
    "CM": "co-movement",
    "EX": "explanation",
    "EV": "evidence",
    "CS": "change set",
    "PEND": "pending refinement",
}

TEMP_PREFIX = "new:"


class IdFactory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    counters: dict[str, int] = {}

    def next(self, prefix: str) -> str:
        n = self.counters.get(prefix, 0) + 1
        self.counters[prefix] = n
        return f"{prefix}-{n:06d}"

    def peek(self, prefix: str) -> str:
        """The id that next() would return, without consuming it."""
        return f"{prefix}-{self.counters.get(prefix, 0) + 1:06d}"


def is_temp_id(ref: str | None) -> bool:
    return bool(ref) and ref.startswith(TEMP_PREFIX)


def strip_temp(ref: str) -> str:
    """``new:rbi.policy_stance`` -> ``rbi.policy_stance``."""
    return ref[len(TEMP_PREFIX):] if ref.startswith(TEMP_PREFIX) else ref


_slug_re = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Lower-case snake_case slug: ``"Chip exports"`` -> ``"chip_exports"``."""
    s = _slug_re.sub("_", text.lower()).strip("_")
    return s or "item"


def entity_of(subentity_id: str) -> str:
    """Subentity ids are ``<entity_id>.<slug>``."""
    return subentity_id.split(".", 1)[0]
