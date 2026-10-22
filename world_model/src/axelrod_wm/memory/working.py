"""Working memory: the current state of the graph and the daily state of every subentity (§6.12)."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, time, timedelta

from pydantic import BaseModel, ConfigDict

from axelrod_wm.dynamics.kernels import KernelRecursion
from axelrod_wm.events.graph_update import GraphOp, Specificity
from axelrod_wm.inference.records import Forecast
from axelrod_wm.model.evidence import Evidence
from axelrod_wm.model.explanation import Explanation
from axelrod_wm.model.graph import CausalGraph
from axelrod_wm.model.hypothesis import Hypothesis
from axelrod_wm.model.ids import IdFactory
from axelrod_wm.model.serialization import StrSet


def point_key(subentity_id: str, day: int) -> str:
    return f"{subentity_id}|{day}"


def split_point_key(key: str) -> tuple[str, int]:
    sid, _, day = key.rpartition("|")
    return sid, int(day)


class DeviationPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    z: float                          # filtered if observed that day, predicted otherwise
    var: float                        # variance of z (standardized units squared)
    level: float                      # the local level a_j at the end of the day
    innovation: float | None = None   # standardized; None when not observed that day
    observed: bool = False


class DeviationSeries:
    """Read-only view of one subentity's z by day; returns 0.0 before the history starts."""

    __slots__ = ("hist", "sid", "_prefix")

    def __init__(self, hist: DeviationHistory, subentity_id: str) -> None:
        self.hist = hist
        self.sid = subentity_id
        self._prefix = subentity_id + "|"

    @property
    def first_day(self) -> int:
        return self.hist.first_kept_day

    def __getitem__(self, day: int) -> float:
        p = self.hist.points.get(self._prefix + str(day))
        return p.z if p is not None else 0.0

    def get(self, day: int) -> DeviationPoint | None:
        return self.hist.points.get(self._prefix + str(day))


class DeviationHistory(BaseModel):
    """The daily state of every subentity (D13). Every processed day has a point for every
    subentity, observed or predicted. Keyed "<subentity id>|<day>" so that a change set records only
    the points it adds; days older than history.keep_days are pruned at consolidation."""

    model_config = ConfigDict(extra="forbid")

    origin_date: date                 # day 0
    points: dict[str, DeviationPoint] = {}
    first_kept_day: int = 0           # the oldest day still kept after pruning

    # -- days ---------------------------------------------------------------------------------
    def day_of(self, t: datetime) -> int:
        """Day index of a UTC timestamp (day 0 is origin_date)."""
        if t.tzinfo is None:
            t = t.replace(tzinfo=UTC)
        return (t.astimezone(UTC).date() - self.origin_date).days

    def date_of(self, day: int) -> date:
        return self.origin_date + timedelta(days=int(day))

    def day_of_date(self, d: date) -> int:
        return (d - self.origin_date).days

    def day_start(self, day: int) -> datetime:
        return datetime.combine(self.date_of(day), time(0, 0, 0), tzinfo=UTC)

    def day_end(self, day: int) -> datetime:
        return datetime.combine(self.date_of(day), time(23, 59, 59), tzinfo=UTC)

    # -- points -------------------------------------------------------------------------------
    def point(self, subentity_id: str, day: int) -> DeviationPoint | None:
        return self.points.get(point_key(subentity_id, day))

    def z(self, subentity_id: str, day: int) -> float:
        p = self.points.get(point_key(subentity_id, day))
        return p.z if p is not None else 0.0

    def z_at(self, subentity_id: str, day: int) -> float | None:
        """z on that day, or None if there is no point (a day not processed, or pruned)."""
        p = self.points.get(point_key(subentity_id, day))
        return p.z if p is not None else None

    def series(self, subentity_id: str) -> DeviationSeries:
        return DeviationSeries(self, subentity_id)

    def window_change(self, subentity_id: str, day: int, width_days: int) -> float:
        """z(day) - z(day - width_days)."""
        return self.z(subentity_id, day) - self.z(subentity_id, day - width_days)

    def window_innovation(self, subentity_id: str, day: int, width_days: int) -> float:
        """Sum of the innovations observed in (day - width_days, day], divided by the square root
        of their count; 0 if there are none."""
        total, n = 0.0, 0
        for k in range(int(width_days)):
            p = self.points.get(point_key(subentity_id, day - k))
            if p is not None and p.observed and p.innovation is not None:
                total += p.innovation
                n += 1
        return total / math.sqrt(n) if n else 0.0

    def observed_days(self, subentity_id: str, start: int, end: int) -> list[int]:
        """Days in [start, end] on which the subentity was observed."""
        out = []
        for d in range(int(start), int(end) + 1):
            p = self.points.get(point_key(subentity_id, d))
            if p is not None and p.observed:
                out.append(d)
        return out

    def array(self, subentity_id: str, start: int, end: int) -> list[float]:
        """z for days start..end inclusive (0.0 where there is no point)."""
        pre = subentity_id + "|"
        pts = self.points
        out = []
        for d in range(int(start), int(end) + 1):
            p = pts.get(pre + str(d))
            out.append(p.z if p is not None else 0.0)
        return out


class ChannelState(BaseModel):
    """A channel's regressor at its mean kernel, kept current day by day (§6.4). Every interaction
    has one per direction from the moment it is created: construction, an add_interaction op, a
    promotion, or a refinement builds it with KernelRecursion.warm_start() at the current day.
    After record(day), the recursion is at day + 1."""

    model_config = ConfigDict(extra="forbid")

    channel_id: str                   # interaction id, or "<interaction id>:rev" for a reverse channel
    recursion: KernelRecursion
    day: int = 0                      # the day the recursion's phi refers to


class HedgeCheck(BaseModel):
    """One piece of evidence a hedge weighed (Oct 8): which candidate it favored, how much, and the posterior after."""

    model_config = ConfigDict(extra="forbid")

    at: datetime
    event_id: str
    market_event_id: str | None = None
    headline: str | None = None
    kind: str                           # "mention", "move", "against", or "intake"
    candidate: str | None = None
    weight: float = 0.0                 # pseudo-count added (already times the reviewer's confidence)
    confidence: float = 1.0             # the reviewer's confidence in the evidence
    posterior: dict[str, float] = {}    # after this check (candidates and "__open__")


class PendingRefinement(BaseModel):
    """A graph update op that could not yet be made concrete (§7.5).

    DECISION (Oct 8): a fuzzy end is a hedge, not a guess. Its candidates carry a Dirichlet posterior (`alpha`, plus
    `open_alpha` for a candidate not in the graph yet); `candidates` is that posterior, normalized. Evidence from later
    articles updates it inside each event's staged learning, and once one candidate passes the commit bound with
    enough checks a refinement proposal goes to review. When the candidates are values, the hedge is also drawn as
    soft interactions (tagged `hedge:<key>`), one per candidate, whose existence follows the posterior: forecasts hedge
    across them as probabilistic data association does (Bar-Shalom, Daum, and Huang, 2009)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    op: GraphOp                         # as specific as it got
    end: str                            # "source", "target", or "subject"
    reached: Specificity
    node_id: str                        # generalization or entity id reached
    candidates: dict[str, float]        # candidate id -> score
    evidence: list[Evidence]
    source_event_id: str
    created_at: datetime
    expires_at: datetime
    relation_node_id: str | None = None         # the interaction generalization the op asserts
    attribute_filter: list[str] = []            # attribute kinds the fuzzy end may take
    explicit_attribute: bool = False            # True if the op itself named the attribute kind
    label: str | None = None
    polarity: int | None = None
    market_event_id: str | None = None
    key: str | None = None                      # stable across approval: "pending:<event>:<op>"; soft edges carry it
    ends: list[str] = []                        # the hedged ends; a joint hedge's candidates are "a|b" for these ends
    alpha: dict[str, float] = {}                # Dirichlet pseudo-counts per candidate
    open_alpha: float = 0.0                     # pseudo-count for a candidate not in the graph yet
    support: float = 0.0                        # checks that moved the posterior
    checks: list[HedgeCheck] = []               # the newest 20
    status: str = "holding"                     # holding, resolution_proposed
    soft: bool = False                          # drawn as soft interactions (candidates are values)
    user_confidence: float = 1.0                # the reviewer's confidence when it was stored

    def posterior(self) -> dict[str, float]:
        """The candidates' probabilities, with "__open__" for one not in the graph yet."""
        if not self.alpha:
            tot = sum(self.candidates.values()) or 1.0
            return {c: v / tot for c, v in self.candidates.items()}
        tot = sum(self.alpha.values()) + self.open_alpha
        out = {c: a / tot for c, a in self.alpha.items()}
        if self.open_alpha > 0:
            out["__open__"] = self.open_alpha / tot
        return out


class RippleJudgment(BaseModel):
    """A reviewer's judgment of one value's ripple from one event (Oct 9): the probability that the ripple reaches
    it. The ripple is not an op of the event (it follows from the interactions), but it moves the state day by day,
    so the reviewer may weigh it: with probability `weight` it arrives as the analysis expects, else not at all.
    The daily prediction adds (weight - 1) times `path` (the expected ripple, by day from `start_day`, already
    scaled by what the reviewer said of the values upstream) to the value's predicted deviation, until the path ends.
    Keyed "<event id>|<subentity id>"."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    subentity_id: str
    weight: float                     # 0: the ripple does not reach it; 1: as the analysis expects
    start_day: int                    # the event's processing day; path[0] is this day
    path: list[float]                 # the expected ripple in sd, by day
    order: int = 1
    via: list[str] = []               # the interactions along its main path


def ripple_key(event_id: str, subentity_id: str) -> str:
    return f"{event_id}|{subentity_id}"


def ripple_correction(wm: WorkingMemory, subentity_id: str, day: int) -> float:
    """What the reviewers' ripple judgments add to one value's predicted deviation on `day`."""
    out = 0.0
    for j in wm.ripple_judgments.values():
        if j.subentity_id == subentity_id and 0 <= day - j.start_day < len(j.path):
            out += (j.weight - 1.0) * j.path[day - j.start_day]
    return out


class ForecastStateView(BaseModel):
    """What the forecast layer holds for one thesis: the state updated into a forecast."""

    model_config = ConfigDict(extra="forbid")

    thesis_id: str
    forecast: Forecast                     # the full record (§8.9); read_out() returns it
    explanation: Explanation               # moves into long-term memory at the next consolidation
    thesis: dict | None = None             # the posed thesis (JSON), for "Compare with..." and VOI references


class ForecastLayer(BaseModel):
    """Forecasts written by the inference task, keyed by thesis id (D5). It never touches
    posteriors, it is not part of the state hash, and writing it never bumps the version.
    Unpinned entries are cleared at consolidation, after their explanations are stored."""

    model_config = ConfigDict(extra="forbid")

    by_thesis: dict[str, ForecastStateView] = {}
    pinned: StrSet = set()
    pose_counts: dict[str, int] = {}         # thesis id -> times posed, for FC-<thesis>-<n> ids
    order: list[str] = []                    # thesis ids, most recently posed last


class ActivityRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: int
    channel_id: str
    contribution_change: float        # change in mu * m * phi over the last abduction.window_days
    target_move: float                # the target's window change over the same days (observed or predicted)
    target_id: str | None = None


def activity_key(day: int, channel_id: str) -> str:
    return f"{day}|{channel_id}"


class EpisodeEntry(BaseModel):
    """What consolidation needs from each applied real event (§8.12)."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    at: datetime
    event_type: str | None
    tags: list[str]
    signature: StrSet                 # from signature_of(), including tag: and etype: keys
    routine: bool                     # True for event_type "data_release" with no move of 1 standard unit or more
    touched_entity_ids: list[str] = []
    explanation_id: str | None = None


class WorkingMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clock: datetime                   # the end of the last processed day
    last_processed_day: int = -1      # day index of the clock
    graph: CausalGraph
    deviations: DeviationHistory
    channels: dict[str, ChannelState] = {}       # channel id -> regressor state
    channel_phi: dict[str, float] = {}           # "<channel id>|<day>" -> phi; pruned with the activity log
    hypotheses: dict[str, Hypothesis] = {}
    pending_refinements: dict[str, PendingRefinement] = {}
    ripple_judgments: dict[str, RippleJudgment] = {}  # "<event id>|<subentity id>" -> a reviewer's weight (Oct 9)
    forecast_layer: ForecastLayer = ForecastLayer()
    activity_log: dict[str, ActivityRecord] = {}   # "<day>|<channel id>" -> record; rolling window (§8.8)
    fold_accumulators: dict[str, tuple[float, float]] = {}   # interaction id -> (sum phi*y, sum phi^2) today
    episode_buffer: list[EpisodeEntry] = []      # applied real events today
    source_cursors: dict[str, datetime] = {}     # source name -> end of the last window already collected
    late_queue: dict[str, int] = {}              # proposal id -> day it was due; folded first on the next processed day
    ids: IdFactory = IdFactory()
    decision_variables: list[str] = []           # from construction (§14.1)
    pending_episode_tags: list[str] = []         # tags for the next episode, e.g. "decision-outcome"
    missing_relation_log: dict[str, datetime] = {}   # "<pattern>#<relation index>" -> last proposed

    def processing_day(self) -> int:
        """The next day an update run will process."""
        return self.last_processed_day + 1

    def phi(self, channel_id: str) -> float:
        cs = self.channels.get(channel_id)
        return cs.recursion.phi() if cs is not None else 0.0
