"""Hand-built graph pieces for the model coverage tests."""

from __future__ import annotations

from datetime import datetime, timezone

from axelrod_wm.model.distributions import Beta, Gaussian
from axelrod_wm.model.entity import Entity, EntityKind, Subentity
from axelrod_wm.model.evidence import Origin
from axelrod_wm.model.graph import CausalGraph
from axelrod_wm.model.interaction import Direction, EdgeDynamics, Interaction
from axelrod_wm.model.temporal import KernelSpec

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def entity(eid: str, kind: EntityKind = EntityKind.COMPANY, subs: list[str] | None = None, **kw) -> Entity:
    return Entity(id=eid, name=eid.upper(), kind=kind, category_tags=set(), subentity_ids=subs or [],
                  origin=Origin.CONSTRUCTION, created_at=T0, **kw)


def sub(sid: str, attribute_kind: str = "revenue", **kw) -> Subentity:
    g = Gaussian(mu=0.0, sigma=1.0)
    return Subentity(id=sid, entity_id=sid.split(".", 1)[0], name=sid, attribute_kind=attribute_kind, unit="usd",
                     scale=1.0, prior=g, posterior=g, anchor=0.0, origin=Origin.CONSTRUCTION, **kw)


def dyn(beta: float = 0.5, sigma: float = 0.0, delay: float = 7, lag: float = 14, duration: float | None = None):
    return EdgeDynamics(effect=Gaussian(mu=beta, sigma=sigma),
                        kernel=KernelSpec.model_validate({"delay_days": delay, "lag_days": lag,
                                                          "duration_days": duration}))


def inter(iid: str, s: str, t: str, beta: float = 0.5, existence: Beta | None = None, label: str = "raises",
          reverse: EdgeDynamics | None = None, **kw) -> Interaction:
    return Interaction(id=iid, source_id=s, target_id=t, label=label, origin=Origin.CONSTRUCTION,
                       existence=existence or Beta(alpha=9.0, beta=1.0), forward=dyn(beta),
                       direction=Direction.BIDIRECTIONAL if reverse is not None else Direction.UNIDIRECTIONAL,
                       reverse=reverse, created_at=T0, **kw)


def small_graph() -> CausalGraph:
    """a.x -> b.y (between), b.y <-> b.z (internal, bidirectional), c.w alone."""
    ents = {"a": entity("a", subs=["a.x"], features={"region": "US"}),
            "b": entity("b", subs=["b.y", "b.z"], generalization_id="gen:obj:firm"),
            "c": entity("c", kind=EntityKind.MARKET, subs=["c.w"])}
    subs = {"a.x": sub("a.x", "policy_rate"), "b.y": sub("b.y", "revenue", features={"product": "chips"}),
            "b.z": sub("b.z", "margin"), "c.w": sub("c.w", "price")}
    ints = {"int-1": inter("int-1", "a.x", "b.y", 0.8),
            "int-2": inter("int-2", "b.y", "b.z", -0.4, label="cuts margin", reverse=dyn(0.2))}
    return CausalGraph(entities=ents, subentities=subs, interactions=ints)
