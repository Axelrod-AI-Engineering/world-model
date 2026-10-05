"""Episodes: stored stretches of past events and the states they produced (§6.13)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from axelrod_wm.core.serialization import StrSet


class Episode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    start: datetime
    end: datetime
    trigger_event_ids: list[str]
    event_types: list[str] = []
    signature: StrSet                           # generalization ids involved (objects and interactions)
    key_signature: StrSet                       # the same, from non-routine events only (all events if none)
    deltas: dict[str, tuple[float, float]]      # subentity -> (z at start, z at end)
    active_interaction_ids: list[str]
    edge_effects: dict[str, tuple[float, float]]   # interaction id -> (implied effect, weight) in this episode
    active_pattern_ids: list[str]
    explanation_ids: list[str] = []
    tags: list[str] = []                        # e.g. ["energy-shock-like"]
    step: int | None = None                     # propagation-grid step of the episode


class EpisodeStore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episodes: dict[str, Episode] = {}

    def add(self, episode: Episode) -> None:
        self.episodes[episode.id] = episode

    def by_generalization(self, gen_id: str) -> list[str]:
        return [eid for eid, ep in sorted(self.episodes.items()) if gen_id in ep.signature]

    def by_tag(self, tag: str) -> list[str]:
        return [eid for eid, ep in sorted(self.episodes.items()) if tag in ep.tags]
