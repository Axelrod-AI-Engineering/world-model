"""Corporate actions (Oct 17): a stock split changes every per-share figure without changing the business.

An entity lists its splits (`corporate_actions: [{type: split, ratio: 15, effective: 2026-04-01}]`, in entities.yaml
or a construction file). A ratio of 15 is a 15-for-1 split (one old share becomes 15); a reverse split has a ratio
below 1 (1-for-10 is 0.1).

**The model's basis.** The model holds every per-share value on the basis *before* every split its entity lists, so
the levels in the construction files (and all history) stay as they were set. A reported per-share level or absolute
change dated on or after a split's effective day is converted to that basis by multiplying it by the ratio of every
split in force on its date (a post-split price of 400 after a 15-for-1 split is 6,000 on the model's basis). List a
split only if the value's construction level predates it. A relative or standardized change has no unit and is never
converted.

**Per share.** A value is per share when its features say `per_share: "true"`, or its unit says so ("per share",
"/share"). Nothing else counts: the criterion is explicit, so a price that is not per share (oil, a yield) is never
touched.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_PER_SHARE_UNIT = re.compile(r"per\s+share|/\s*share", re.IGNORECASE)


class CorporateAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["split"]
    ratio: float = Field(gt=0)           # new shares per old share: 15 is a 15-for-1 split, 0.1 a 1-for-10 reverse
    effective: date                      # the first day the shares trade on the new basis
    note: str = ""

    @field_validator("ratio")
    @classmethod
    def _not_one(cls, v: float) -> float:
        if v == 1:
            raise ValueError("a split ratio of 1 changes nothing")
        return v


def is_per_share(value: Any) -> bool:
    """Whether a value (a subentity or its spec) is a per-share figure (see the module docstring)."""
    features = getattr(value, "features", None) or {}
    return str(features.get("per_share", "")).lower() == "true" or bool(
        _PER_SHARE_UNIT.search(getattr(value, "unit", None) or ""))


def splits_in_force(actions: list[CorporateAction], on: date) -> list[CorporateAction]:
    """The splits effective on or before `on`, oldest first."""
    return sorted((a for a in actions if a.effective <= on), key=lambda a: a.effective)


def to_model_basis(graph: Any, value_id: str, amount: float, on: date) -> tuple[float, dict | None]:
    """`amount` (a level or an absolute change, in the value's native unit, dated `on`) on the model's pre-split
    basis, and a record of the conversion (None when nothing converts)."""
    sub = graph.subentities[value_id]
    if not is_per_share(sub):
        return amount, None
    splits = splits_in_force(graph.entities[sub.entity_id].corporate_actions, on)
    if not splits:
        return amount, None
    factor = 1.0
    for a in splits:
        factor *= a.ratio
    return amount * factor, {"value_of": value_id, "reported": amount, "model_basis": amount * factor,
                             "factor": factor, "dated": on.isoformat(),
                             "splits": [{"ratio": a.ratio, "effective": a.effective.isoformat()} for a in splits]}


__all__ = ["CorporateAction", "is_per_share", "splits_in_force", "to_model_basis"]
