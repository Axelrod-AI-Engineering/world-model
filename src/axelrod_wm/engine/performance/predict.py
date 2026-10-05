"""Predict inside one network (goal 2, isolated; §8.9.2)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from axelrod_wm.core.distributions import summarize_samples
from axelrod_wm.engine.performance.records import NetworkInputs, NetworkPrediction
from axelrod_wm.engine.performance.task import NetworkPredictor
from axelrod_wm.engine.propagation import Propagator
from axelrod_wm.engine.registry import register
from axelrod_wm.engine.regressors import build_system, emit_frames, horizon_for
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.engine.interfaces import PrefilledModel
    from axelrod_wm.engine.performance.records import Network


@register("network_predictor", "mc_network")
class McNetworkPredictor(NetworkPredictor):
    def __init__(self, config: Any = None, propagator: Propagator | None = None) -> None:
        self.config = config
        self.propagator = propagator

    def predict(self, network: Network, inputs: NetworkInputs, model: PrefilledModel,
                ctx: ProcessContext) -> NetworkPrediction:
        H = horizon_for(ctx)
        absent = set(network.forced_absent)
        chans = [c.model_copy(update={"forced": False}) if c.interaction_id in absent else c for c in network.channels]
        system = build_system(chans, ctx.wm, ctx, H, extra_subentities=[s.subentity_id for s in inputs.shocks],
                              drifts=model.drifts)
        n = int(ctx.config.propagation.samples)
        key = ("predict", ctx.scope, network.pattern_id or "residual")
        exo = inputs.boundary or None
        shocked = self.propagator.propagate(system, inputs.shocks, n, ctx.child_rng(*key), record_contributions=True,
                                            exogenous=exo)
        base = self.propagator.propagate(system, [], n, ctx.child_rng(*key), record_contributions=True, exogenous=exo)
        effect = shocked.minus(base)
        at_h = {}
        for sid, i in sorted(effect.subentity_index.items()):
            col = effect.z[:, i, H]
            if abs(float(np.median(col))) >= 0.05:
                at_h[sid] = summarize_samples(col).q50
        ctx.tracer.emit(Phase.PREDICT, "predict.network", refs=[network.id] + sorted(at_h), network_id=network.id,
                        name=network.name, summaries={k: round(v, 4) for k, v in at_h.items()})
        emit_frames(ctx, Phase.PREDICT, f"predict:{network.id}", effect, refs=[network.id])
        return NetworkPrediction(network_id=network.id, result=effect)
