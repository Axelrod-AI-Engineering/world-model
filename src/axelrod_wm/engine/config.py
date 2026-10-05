"""Engine configuration (§8.2). Mirrors configs/default.yaml, with those values as defaults."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field

from axelrod_wm.core.serialization import canonical_json, sha256_text


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TimeConfig(_Section):
    state_step_days: float = 1
    propagation_step_days: float = 7
    horizon_steps: int = 26


class ThresholdsConfig(_Section):
    recognition: float = 3
    recall: float = 4


class PropagationConfig(_Section):
    samples: int = 400
    min_delay_steps: float = 1
    moderator_clip: list[float] = [0.0, 3.0]
    kernel_window_steps: int = 104
    include_level_noise: bool = True


class LearningConfig(_Section):
    effect_process_noise: float = 0.02
    level_process_noise: float = 0.10
    existence_learning_rate: float = 0.5
    min_regressor: float = 0.05
    min_change_noise: float = 0.05


class KernelUpdateConfig(_Section):
    min_observations: int = 8
    window_steps: int = 26
    multipliers: list[float] = [0.5, 1.0, 2.0]
    step: float = 0.5
    cv_shrink: float = 0.9
    min_cv: float = 0.15
    min_log_lik_gain: float = 2.0   # evidence a rescaled kernel needs over the current one


class PrefillConfig(_Section):
    drift_damping: float = 0.9


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
    fit_window_steps: int = 8


class FrontierConfig(_Section):
    window_steps: int = 4
    max_lag_steps: int = 4
    min_innovation: float = 1.5
    min_source_move: float = 0.5
    max_candidates_per_target: int = 5
    min_corr: float = 0.3
    min_consistency: float = 0.75
    half_life_days: float = 30
    remove_below: float = 0.5
    reject_cooldown_days: float = 60
    backfill_steps: int = 26


class AbductionConfig(_Section):
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


class ConsolidationConfig(_Section):
    episode_min_abs_z: float = 0.5


class EvaluationConfig(_Section):
    significant_effect: float = 0.5
    sign_probability: float = 0.7


class ReviewConfig(_Section):
    policy: str = "default"
    min_auto_confidence: float = 0.8
    auto_approve_human: bool = True


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
    "scenario_weighter": "support_fit_reliability",
    "unifier": "channels_and_rivals",
    "hypothesis_scorer": "forecast_sensitivity_voi",
    "consolidator": "daily",
    "scorer": "omission_commission_calibration",
    "refiner": "taxonomy",
    "entity_resolver": "alias_fuzzy",
    "review_policy": "default",
}

DEFAULT_TRANSLATORS: dict[str, str] = {"news": "hand_drawn", "data": "data_feed",
                                       "filing": "hand_drawn", "analyst": "hand_drawn"}


class StorageConfig(_Section):
    backend: str = "files"
    path: str = "var/axelrod"


class EngineConfig(_Section):
    seed: int = 7
    time: TimeConfig = TimeConfig()
    thresholds: ThresholdsConfig = ThresholdsConfig()
    propagation: PropagationConfig = PropagationConfig()
    learning: LearningConfig = LearningConfig()
    kernel_update: KernelUpdateConfig = KernelUpdateConfig()
    prefill: PrefillConfig = PrefillConfig()
    attention: AttentionConfig = AttentionConfig()
    isolation: IsolationConfig = IsolationConfig()
    unify: UnifyConfig = UnifyConfig()
    frontier: FrontierConfig = FrontierConfig()
    abduction: AbductionConfig = AbductionConfig()
    refinement: RefinementConfig = RefinementConfig()
    hypotheses: HypothesesConfig = HypothesesConfig()
    consolidation: ConsolidationConfig = ConsolidationConfig()
    evaluation: EvaluationConfig = EvaluationConfig()
    review: ReviewConfig = ReviewConfig()
    translators: dict[str, ComponentRef] = Field(default_factory=lambda: dict(DEFAULT_TRANSLATORS))
    components: dict[str, ComponentRef] = Field(default_factory=lambda: dict(DEFAULT_COMPONENTS))
    storage: StorageConfig = StorageConfig()

    def component(self, slot: str) -> tuple[str, dict[str, Any]]:
        """(name, params) for a slot."""
        ref = self.components.get(slot, DEFAULT_COMPONENTS.get(slot))
        if ref is None:
            raise KeyError(f"no component configured for slot {slot!r}")
        if isinstance(ref, ComponentSpec):
            return ref.name, dict(ref.params)
        return ref, {}

    def translator(self, kind: str) -> tuple[str, dict[str, Any]]:
        ref = self.translators.get(kind, DEFAULT_TRANSLATORS.get(kind, "hand_drawn"))
        if isinstance(ref, ComponentSpec):
            return ref.name, dict(ref.params)
        return ref, {}

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


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = REPO_ROOT / "configs" / "default.yaml"


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
