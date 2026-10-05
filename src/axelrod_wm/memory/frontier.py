"""The correlation frontier: co-movements not yet admitted as causal (§8.7, Figure 3)."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from axelrod_wm.control.mutator import MutationTxn
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.engine.learning import FoldResult
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory


class CoMovementStatus(StrEnum):
    HOLDING = "holding"
    PROMOTION_PROPOSED = "promotion_proposed"
    PROMOTED = "promoted"
    DECAYED = "decayed"


class RunningCorr(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n: float = 0.0
    mean_x: float = 0.0
    mean_y: float = 0.0
    c_xy: float = 0.0
    m2_x: float = 0.0
    m2_y: float = 0.0
    pairs: list[tuple[float, float]] = []     # the points pushed, for the promotion chart (last 104)

    def push(self, x: float, y: float) -> None:
        if not (math.isfinite(x) and math.isfinite(y)):
            return
        n = self.n + 1.0
        dx = x - self.mean_x
        self.mean_x += dx / n
        dy = y - self.mean_y
        self.mean_y += dy / n
        self.c_xy += dx * (y - self.mean_y)
        self.m2_x += dx * (x - self.mean_x)
        self.m2_y += dy * (y - self.mean_y)
        self.n = n
        self.pairs = (self.pairs + [(float(x), float(y))])[-104:]

    def pushed(self, x: float, y: float) -> RunningCorr:
        out = self.model_copy(deep=True)
        out.push(x, y)
        return out

    def corr(self) -> float:
        if self.n < 2 or self.m2_x <= 1e-12 or self.m2_y <= 1e-12:
            return 0.0
        return float(self.c_xy / math.sqrt(self.m2_x * self.m2_y))

    def slope(self) -> tuple[float, float]:
        """OLS slope of y on x and its standard error."""
        if self.n < 2 or self.m2_x <= 1e-12:
            return 0.0, float("inf")
        b = self.c_xy / self.m2_x
        if self.n <= 2:
            return float(b), float("inf")
        resid = max(self.m2_y - b * self.c_xy, 0.0) / (self.n - 2.0)
        return float(b), float(math.sqrt(resid / self.m2_x))


class CoMovement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    earlier_id: str                    # subentity that moved first
    later_id: str                      # subentity with the unexplained move
    lag_steps: int
    sign: int                          # +1 same direction, -1 opposite
    support: float = 0.0               # decayed count of consistent episodes
    consistent: int = 0
    inconsistent: int = 0
    corr: RunningCorr = RunningCorr()        # (window change of a at s - lag, window innovation of b at s)
    response: RunningCorr = RunningCorr()    # (window change of a at s - lag, window change of b at s): effect units
    first_seen: datetime
    last_seen: datetime
    last_episode_day: date | None = None
    status: CoMovementStatus = CoMovementStatus.HOLDING
    ambiguous_direction: bool = False
    seeded: bool = False                     # from frontier_seeds; does not decay until first verified
    hypothesis_id: str | None = None
    proposal_id: str | None = None
    verified_days: list[date] = []


def pair_key(a: str, b: str) -> str:
    """Key for a pair regardless of direction, used for blocks after a rejection."""
    x, y = sorted((a, b))
    return f"{x}|{y}"


class CorrelationFrontier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: dict[str, CoMovement] = {}
    blocked_until: dict[str, datetime] = {}    # "a|b" -> date, after a rejection

    def get(self, earlier_id: str, later_id: str) -> CoMovement | None:
        for _, co in sorted(self.entries.items()):
            if co.earlier_id == earlier_id and co.later_id == later_id:
                return co
        return None

    def for_pair(self, a: str, b: str) -> list[CoMovement]:
        return [co for _, co in sorted(self.entries.items())
                if {co.earlier_id, co.later_id} == {a, b}]

    def is_blocked(self, a: str, b: str, now: datetime) -> bool:
        until = self.blocked_until.get(pair_key(a, b))
        return until is not None and now < until

    def live(self) -> list[CoMovement]:
        return [co for _, co in sorted(self.entries.items())
                if co.status in (CoMovementStatus.HOLDING, CoMovementStatus.PROMOTION_PROPOSED)]


class FrontierResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    logged: list[str] = []
    tested: list[str] = []
    proposals: list[str] = []
    decayed: list[str] = []
    proposal_events: list[dict] = []     # FRONTIER_PROMOTION proposals for the controller to queue


class FrontierTester(ABC):
    @abstractmethod
    def test(self, fold: FoldResult, wm: WorkingMemory, ltm: LongTermMemory,
             ctx: ProcessContext, txn: MutationTxn) -> FrontierResult: ...


class PromotionTest(ABC):
    @abstractmethod
    def passes(self, co: CoMovement, recognition: float, cfg: dict) -> bool: ...


def comovement_pair(dev, earlier: str, later: str, lag: int, step: int, width: int) -> tuple[float, float, float]:
    """(window change of the earlier subentity at step - lag, window innovation of the later one at
    step, window change of the later one at step)."""
    x = dev.window_change(earlier, step - lag, width)
    y = dev.window_innovation(later, step, width)
    r = dev.window_change(later, step, width)
    return x, y, r


def backfilled(co: CoMovement, dev, step: int, width: int, n: int) -> CoMovement:
    """A copy of `co` with corr and response filled from the last `n` steps up to `step`."""
    out = co.model_copy(deep=True)
    for s in range(step - n + 1, step + 1):
        x, y, r = comovement_pair(dev, co.earlier_id, co.later_id, co.lag_steps, s, width)
        if x == 0.0 and y == 0.0 and r == 0.0:
            continue
        out.corr.push(x, y)
        out.response.push(x, r)
    return out


def comovement_statement(graph, earlier: str, later: str, sign: int) -> str:
    def name(sid: str) -> str:
        sub = graph.subentities.get(sid)
        return sub.name if sub is not None else sid

    verb = "moves with" if sign > 0 else "moves against"
    return f"{name(later)} {verb} earlier moves in {name(earlier)} (co-movement on the frontier)"
