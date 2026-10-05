"""Long-term memory (§6.13).

Full prior states (snapshots) live in the SnapshotStore (§9), which the engine reaches; they are
not inside this model, so a snapshot never contains other snapshots.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from axelrod_wm.core.entity import EntityMemory
from axelrod_wm.core.taxonomy import AttributeVocabulary, Taxonomy
from axelrod_wm.evaluation.reliability import ReliabilityBook
from axelrod_wm.memory.episodes import Episode, EpisodeStore
from axelrod_wm.memory.explanations import ExplanationStore
from axelrod_wm.memory.frontier import CorrelationFrontier
from axelrod_wm.memory.patterns import PatternStore


class LongTermMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episodes: EpisodeStore                      # prior states, summarized; the source of analogs
    object_taxonomy: Taxonomy
    interaction_taxonomy: Taxonomy
    attributes: AttributeVocabulary
    patterns: PatternStore
    entity_memories: dict[str, EntityMemory] = {}
    explanations: ExplanationStore
    frontier: CorrelationFrontier              # §8.7
    reliability: ReliabilityBook               # §8.14

    def taxonomy(self, kind) -> Taxonomy:
        return self.object_taxonomy if str(kind) == "object" else self.interaction_taxonomy


__all__ = ["LongTermMemory", "Episode", "EpisodeStore", "PatternStore", "ExplanationStore"]
