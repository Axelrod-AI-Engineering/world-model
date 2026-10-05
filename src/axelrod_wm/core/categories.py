"""The eight category tags (§6.2)."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import PlainSerializer


class CategoryTag(StrEnum):
    """One of the eight main categories. A label for people with no causal meaning.
    It is not a generalization and plays no part in forming superentities."""

    SD = "SD"  # spending and demand
    MF = "MF"  # money and finance
    SC = "SC"  # supply and capacity
    DI = "DI"  # distribution
    DF = "DF"  # deep foundations
    EN = "EN"  # environment
    EX = "EX"  # expectations
    SH = "SH"  # shocks


CATEGORY_NAMES: dict[str, str] = {
    "SD": "spending and demand",
    "MF": "money and finance",
    "SC": "supply and capacity",
    "DI": "distribution",
    "DF": "deep foundations",
    "EN": "environment",
    "EX": "expectations",
    "SH": "shocks",
}

TagSet = Annotated[set[CategoryTag],
                   PlainSerializer(lambda s: sorted(str(t) for t in s), return_type=list, when_used="json")]
