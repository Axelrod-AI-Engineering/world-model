"""Engine configuration (§8.2). Mirrors configs/default.yaml, with those values as defaults."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from axelrod_wm.model.serialization import canonical_json, sha256_text
from axelrod_wm.paths import REPO_ROOT, WM_ROOT


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TimeConfig(_Section):
    step_days: float = 1          # everything runs on a daily grid (D13); every other time parameter is in days
    horizon_days: int = 182       # default forecast horizon; a thesis's horizon_days overrides it


class ThresholdsConfig(_Section):
    recognition: float = 3
    recall: float = 4


class PropagationConfig(_Section):
    samples: int = 400
    min_delay_days: int = 1
    moderator_clip: list[float] = [0.0, 3.0]
    include_level_noise: bool = True
    max_frames: int = 60          # propagation.frame trace events per run, evenly spaced over the horizon


class LearningConfig(_Section):
    effect_process_noise: float = 0.0075    # random-walk sd for effects, per day (about 0.02 per week)
    level_process_noise: float = 0.04       # random-walk sd for each subentity's local level, per day
    existence_learning_rate: float = 0.5
    min_regressor: float = 0.05
    min_change_noise: float = 0.05          # floor on the noise of a real change_value (standardized)


class HistoryConfig(_Section):
    keep_days: Union[int, str] = "auto"     # at least the longest delay + lag over all channels, plus 30; never below 760


class KernelUpdateConfig(_Section):
    every_days: int = 7
    min_observations: int = 8
    window_days: int = 182
    multipliers: list[float] = [0.5, 1.0, 2.0]
    step: float = 0.5
    cv_shrink: float = 0.9
    min_cv: float = 0.15
    min_log_lik_gain: float = 2.0   # DECISION: evidence a rescaled kernel needs over the current one


class PrefillConfig(_Section):
    trend_window_days: int = 28
    max_drift_per_day: float = 0.03
    drift_damping: float = 0.985    # drift on forecast day t is drift * damping**t (half-life about 46 days)


class EpisodesConfig(_Section):
    min_abs_z: float = 0.5          # a subentity enters an episode's deltas if it moved at least this much
    analog_span_days: int = 42      # a non-routine episode's response window, used by analog recall


class EntityMemoryConfig(_Section):
    entry_every_days: int = 7


class SnapshotsConfig(_Section):
    every_days: int = 30            # plus one at the end of every update run


class AttentionConfig(_Section):
    top_k_superentities: int = 6
    top_k_analogs: int = 5
    temperature: float = 0.5
    min_attention: float = 0.02


class IsolationConfig(_Section):
    max_networks: int = 6
    min_relevance: float = 0.05
    reach_hops: int = 2
    residual_hops: int = 2
    residual_min_significance: float = 0.05


class UnifyConfig(_Section):
    max_scenarios: int = 8
    branch_hypothesis_min_voi: float = 0.15
    branch_probability_range: list[float] = [0.15, 0.85]
    fit_window_days: int = 56


class FrontierConfig(_Section):
    window_days: int = 14
    lag_grid_days: list[int] = [0, 1, 2, 3, 5, 7, 10, 14, 21, 28]
    min_innovation: float = 1.5
    min_source_move: float = 0.5
    max_candidates_per_target: int = 5
    min_corr: float = 0.3
    min_consistency: float = 0.75
    evidence_spacing_days: int = 14     # a co-movement is verified at most once per this many days
    half_life_days: float = 30
    remove_below: float = 0.5
    reject_cooldown_days: float = 60
    backfill_days: int = 182


class AbductionConfig(_Section):
    window_days: int = 28               # activity window that components are built from
    evidence_spacing_days: int = 14     # a pattern's support grows at most once per this many days
    min_edge_contribution: float = 0.2
    match_jaccard: float = 0.75
    min_binding_coverage: float = 0.6
    mdl_lambda: float = 0.05
    support_half_life_days: float = 90
    dissolve_below: float = 1.0
    missing_relation_cooldown_days: float = 30


class RefinementConfig(_Section):
    min_generalization_score: float = 0.5
    bind_score: float = 0.6
    bind_margin: float = 0.15
    evidence_bonus: float = 0.2
    pending_ttl_days: float = 60
    # hedged fuzzy ends (Oct 8): a mention binds outright only when it names one candidate; otherwise it stays a
    # hedge, a Dirichlet posterior over its candidates plus an open-world reserve, until evidence settles it
    hedge_prior: float = 1.0            # Dirichlet pseudo-counts spread over the candidates by their resolver scores
    hedge_open_mass: float = 0.5        # pseudo-count kept for a candidate not in the graph yet
    hedge_max_candidates: int = 4
    commit_posterior: float = 0.75      # the bound a candidate must pass (with recognition-many checks) to resolve
    mention_weight: float = 1.5         # pseudo-count a later article adds to a candidate it names (times confidence)
    move_weight: float = 1.0            # pseudo-count a move consistent with the interaction adds (times confidence)
    soft_edge_concentration: float = 2.0   # existence Beta strength of a hedge's soft interactions at the start


class OpenWorldConfig(_Section):
    """The open node every node carries (Oct 9): the probability mass the graph does not account for yet."""
    concentration: float = 1.0          # a kind's or a superentity's pseudo-count for something not seen yet (CRP alpha)
    prior_sd2: float = 1.0              # sd^2 of movement a value is assumed to have, all of it open, before any data


class HypothesesConfig(_Section):
    half_life_days: float = 14
    reference_samples: int = 100
    watch_list: dict[str, float] = {
        "inflation.headline_cpi": 1.0,
        "interest_rates.us_policy_rate": 1.0,
        "credit_availability.credit_growth": 0.8,
        "business_investment.capex_growth": 0.8,
        "asset_prices.equity_index": 1.0,
        "confidence.consumer_confidence": 0.6,
        "productivity_tech.tfp_growth": 0.5,
    }


class EvaluationConfig(_Section):
    significant_effect: float = 0.5
    sign_probability: float = 0.7


class ReviewConfig(_Section):
    policy: str = "default"
    min_auto_confidence: float = 0.8
    auto_approve_human: bool = True


class UpdateConfig(_Section):
    sources: list[str] = ["mock_web_scraper"]   # names in the `source` registry (§8.16)
    pause_for_review: bool = True               # a world event awaiting review pauses the run at its day (D14)
    repose_pinned: bool = True                  # re-pose pinned theses after every update
    auto_daily: bool = False                    # when true, the server requests an update every day at daily_at
    daily_at: str = "18:00"
    timezone: str = "America/New_York"
    source_params: dict[str, dict[str, Any]] = {}   # per-source params (e.g. the mock scraper's latency)


class ComponentSpec(_Section):
    name: str
    params: dict[str, Any] = {}


ComponentRef = Union[str, ComponentSpec]

DEFAULT_COMPONENTS: dict[str, str] = {
    "parser": "default",
    "classifier": "taxonomy_descent",
    "taxonomy_grower": "shared_feature_split",
    "recaller": "overlap_attention",
    "attention": "softmax_top_k",
    "binder": "bfs_role_filling",
    "inducer": "co_activation",
    "prefiller": "analog_empirical_bayes",
    "propagator": "mc_impulse",
    "analyzer": "propagation",
    "daily_propagator": "kalman_predict",
    "posterior_updater": "link_kalman",
    "folder": "kalman_edge",
    "kernel_updater": "grid_rescale",
    "generalization_updater": "path_stats",
    "frontier": "residual_comovement",
    "promotion_test": "threshold",
    "explainer": "path_attribution",
    "isolator": "bound_superentity",
    "network_predictor": "mc_network",
    "coupler": "union_graph",
    "rival_detector": "pattern_and_sign",
    "scenario_weighter": "support_fit_track",
    "unifier": "channels_and_rivals",
    "hypothesis_scorer": "forecast_sensitivity_voi",
    "consolidator": "daily",
    "scorer": "omission_commission_calibration",
    "refiner": "taxonomy",
    "entity_resolver": "alias_fuzzy",
    "review_policy": "default",
}

DEFAULT_TRANSLATORS: dict[str, list[str]] = {
    "news": ["hand_drawn", "template"],
    "data": ["data_feed"],
    "filing": ["hand_drawn", "template"],
    "analyst": ["hand_drawn", "template"],
}


class StorageConfig(_Section):
    backend: str = "files"
    path: str = "var/axelrod"


class EngineConfig(_Section):
    seed: int = 7
    time: TimeConfig = TimeConfig()
    thresholds: ThresholdsConfig = ThresholdsConfig()
    propagation: PropagationConfig = PropagationConfig()
    learning: LearningConfig = LearningConfig()
    history: HistoryConfig = HistoryConfig()
    kernel_update: KernelUpdateConfig = KernelUpdateConfig()
    prefill: PrefillConfig = PrefillConfig()
    episodes: EpisodesConfig = EpisodesConfig()
    entity_memory: EntityMemoryConfig = EntityMemoryConfig()
    snapshots: SnapshotsConfig = SnapshotsConfig()
    attention: AttentionConfig = AttentionConfig()
    isolation: IsolationConfig = IsolationConfig()
    unify: UnifyConfig = UnifyConfig()
    frontier: FrontierConfig = FrontierConfig()
    abduction: AbductionConfig = AbductionConfig()
    refinement: RefinementConfig = RefinementConfig()
    open_world: OpenWorldConfig = OpenWorldConfig()
    hypotheses: HypothesesConfig = HypothesesConfig()
    evaluation: EvaluationConfig = EvaluationConfig()
    review: ReviewConfig = ReviewConfig()
    update: UpdateConfig = UpdateConfig()
    translators: dict[str, list[ComponentRef]] = Field(default_factory=lambda: {k: list(v) for k, v in DEFAULT_TRANSLATORS.items()})
    components: dict[str, ComponentRef] = Field(default_factory=lambda: dict(DEFAULT_COMPONENTS))
    storage: StorageConfig = StorageConfig()

    @field_validator("translators", mode="before")
    @classmethod
    def _translator_lists(cls, v: Any) -> Any:
        """A single translator name is a list of one."""
        if isinstance(v, dict):
            return {k: (x if isinstance(x, list) else [x]) for k, x in v.items()}
        return v

    def component(self, slot: str) -> tuple[str, dict[str, Any]]:
        """(name, params) for a slot."""
        ref = self.components.get(slot, DEFAULT_COMPONENTS.get(slot))
        if ref is None:
            raise KeyError(f"no component configured for slot {slot!r}")
        if isinstance(ref, ComponentSpec):
            return ref.name, dict(ref.params)
        return ref, {}

    def translator_chain(self, kind: str) -> list[tuple[str, dict[str, Any]]]:
        """The translators tried in order for a market event kind (§7.4)."""
        refs = self.translators.get(kind, DEFAULT_TRANSLATORS.get(kind, ["hand_drawn", "template"]))
        out = []
        for ref in refs:
            if isinstance(ref, ComponentSpec):
                out.append((ref.name, dict(ref.params)))
            else:
                out.append((ref, {}))
        return out

    def translator(self, kind: str) -> tuple[str, dict[str, Any]]:
        """The first translator for a kind."""
        return self.translator_chain(kind)[0]

    def keep_days(self, longest_span_days: float = 0.0) -> int:
        """history.keep_days, resolving "auto" (§8.2)."""
        kd = self.history.keep_days
        if isinstance(kd, str):
            return max(760, int(longest_span_days) + 30)
        return max(int(kd), 1)

    def config_hash(self) -> str:
        return sha256_text(canonical_json(self.model_dump(mode="json")))


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k not in ("watch_list",):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


DEFAULT_CONFIG_PATH = WM_ROOT / "configs" / "default.yaml"


def load_config(path: str | Path | None = None, overrides: list[str | Path | dict] | None = None,
                **updates: Any) -> EngineConfig:
    """Load a config file (default: configs/default.yaml), then apply override files or dicts."""
    p = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    data: dict = {}
    if p.exists():
        data = yaml.safe_load(p.read_text()) or {}
    for ov in overrides or []:
        if isinstance(ov, dict):
            data = deep_merge(data, ov)
        else:
            op = Path(ov)
            if not op.is_absolute() and not op.exists():
                op = REPO_ROOT / op
            data = deep_merge(data, yaml.safe_load(op.read_text()) or {})
    if updates:
        data = deep_merge(data, updates)
    return EngineConfig.model_validate(data)
