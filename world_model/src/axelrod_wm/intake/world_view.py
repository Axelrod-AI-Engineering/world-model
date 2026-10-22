"""The world model's graph, as the view ingestion reads (axelrod_ingest.contract.world_view).

A pure adapter: it reads the graph and nothing else, and sorts everything by id, so the same graph always gives the
same view (and the same JSON).
"""

from __future__ import annotations

from typing import Any

from axelrod_ingest.contract.world_view import EntityView, LinkView, ValueView, WorldView


def world_view_of(graph: Any) -> WorldView:
    entities = {eid: EntityView(id=eid, name=e.name, kind=str(e.kind), aliases=tuple(e.aliases),
                                region=e.features.get("region"), sector=e.features.get("sector"),
                                subentity_ids=tuple(e.subentity_ids))
                for eid, e in sorted(graph.entities.items())}
    values = {sid: ValueView(id=sid, entity_id=s.entity_id, name=s.name, attribute_kind=s.attribute_kind, unit=s.unit,
                             scale=float(s.scale), family=str(getattr(s.posterior, "family", "gaussian")),
                             mean=float(s.posterior.mean()), sd=float(s.posterior.sd()), aliases=tuple(s.aliases))
              for sid, s in sorted(graph.subentities.items())}
    links = tuple(LinkView(id=i.id, source_id=i.source_id, target_id=i.target_id, label=i.label, fixed=bool(i.fixed),
                           effect_mean=float(i.forward.effect.mean()), polarity=i.polarity())
                  for i in graph.active_interactions())
    return WorldView(entities=entities, values=values, links=links)
