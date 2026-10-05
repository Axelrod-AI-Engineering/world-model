"""The explanation store: explanations kept in long-term memory (§8.10)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from axelrod_wm.engine.explain_records import Explanation


class ExplanationStore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explanations: dict[str, Explanation] = {}

    def add(self, explanation: Explanation) -> None:
        self.explanations[explanation.id] = explanation

    def by_index_key(self, key: str) -> list[str]:
        return [eid for eid, ex in sorted(self.explanations.items()) if key in ex.index_keys]

    def index_keys_of(self, explanation_ids: list[str]) -> set[str]:
        out: set[str] = set()
        for eid in explanation_ids:
            ex = self.explanations.get(eid)
            if ex is not None:
                out |= set(ex.index_keys)
        return out
