"""The world view: what ingestion reads of a world model, and nothing more.

Extraction recognizes the model's own names in a document and reads each value's unit, scale, and current level, so it
needs the entities, their values, and the model's links, not the model itself. A `WorldView` is that, as frozen records
sorted by id, with a deterministic JSON form (`to_json` / `from_json`): the world model builds one from its graph
(`axelrod_wm.intake.world_view.world_view_of`), and a separate ingestion service can be sent one over HTTP.

Standard library only: this module is part of the contract (ingestion/tests/test_boundary.py enforces it).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class EntityView:
    id: str
    name: str
    kind: str                           # "company", "market", "agency", ...
    aliases: tuple[str, ...] = ()
    region: str | None = None           # the entity's feature of that name, when it has one
    sector: str | None = None
    subentity_ids: tuple[str, ...] = ()  # its values, in the model's order


@dataclass(frozen=True)
class ValueView:
    id: str
    entity_id: str
    name: str
    attribute_kind: str
    unit: str = ""
    scale: float = 1.0
    family: str = "gaussian"            # the posterior's family: "gaussian", "lognormal", "gamma", ...
    mean: float = 0.0                   # the posterior's mean and sd, in the value's own units
    sd: float = 1.0
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class LinkView:
    id: str
    source_id: str                      # value ids
    target_id: str
    label: str = ""
    fixed: bool = False                 # an accounting, identity, or stock-flow weight that learning never refits
    effect_mean: float = 0.0            # the forward effect's mean (target sd per source sd)
    polarity: int = 1                   # +1 or -1: the effect's sign, or for an uncalibrated link the sign its mechanism states


@dataclass(frozen=True)
class WorldView:
    entities: dict[str, EntityView] = field(default_factory=dict)
    values: dict[str, ValueView] = field(default_factory=dict)
    links: tuple[LinkView, ...] = ()

    def to_json(self) -> str:
        """Canonical JSON: records sorted by id, keys sorted, no whitespace. Equal views give equal strings."""
        body = {"entities": [asdict(e) for _, e in sorted(self.entities.items())],
                "values": [asdict(v) for _, v in sorted(self.values.items())],
                "links": [asdict(i) for i in sorted(self.links, key=lambda x: x.id)]}
        return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> WorldView:
        body: dict[str, Any] = json.loads(text)
        entities = [EntityView(**{**e, "aliases": tuple(e["aliases"]), "subentity_ids": tuple(e["subentity_ids"])})
                    for e in body["entities"]]
        values = [ValueView(**{**v, "aliases": tuple(v["aliases"])}) for v in body["values"]]
        return cls(entities={e.id: e for e in entities}, values={v.id: v for v in values},
                   links=tuple(LinkView(**i) for i in body["links"]))


__all__ = ["EntityView", "LinkView", "ValueView", "WorldView"]
