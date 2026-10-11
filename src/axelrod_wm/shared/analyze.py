"""Analyze the event with the prefilled model (§8.4.5)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from axelrod_wm.dynamics.propagation import Propagator
from axelrod_wm.dynamics.regressors import build_system, emit_frames, horizon_for
from axelrod_wm.engine.interfaces import Analysis, Analyzer
from axelrod_wm.engine.registry import register
from axelrod_wm.model.distributions import summarize_samples
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.engine.interfaces import PrefilledModel
    from axelrod_wm.memory.working import WorkingMemory
    from axelrod_wm.shared.process import ParsedEvent


@register("analyzer", "propagation")
class PropagationAnalyzer(Analyzer):
    """Run the working set twice with common random numbers, with and without the parsed shocks.
    The difference is the event's effect."""

    def __init__(self, config: Any = None, propagator: Propagator | None = None) -> None:
        self.config = config
        self.propagator = propagator

    def analyze(self, parsed: ParsedEvent, model: PrefilledModel, wm: WorkingMemory, ctx: ProcessContext) -> Analysis:
        H = horizon_for(ctx)
        if not parsed.shocks or not model.channels:
            return Analysis(event_id=parsed.event_id, result=None, expected_moves={}, horizon_days=H)
        episodes = set(model.recalled_episode_ids)
        channels = [model.channel_with(k, episodes) for k in sorted(model.channels)]
        system = build_system(channels, wm, ctx, H, extra_subentities=[s.subentity_id for s in parsed.shocks],
                              drifts=model.drifts)
        n = int(ctx.config.propagation.samples)
        key = ("analyze", ctx.scope or parsed.event_id)
        shocked = self.propagator.propagate(system, parsed.shocks, n, ctx.child_rng(*key), record_contributions=True)
        base = self.propagator.propagate(system, [], n, ctx.child_rng(*key), record_contributions=True)
        effect = shocked.minus(base)
        expected = {}
        for sid, i in sorted(effect.subentity_index.items()):
            col = effect.z[:, i, H]
            if abs(float(np.median(col))) >= 0.1:
                expected[sid] = summarize_samples(col)
        emit_frames(ctx, Phase.ANALYZE, f"analyze:{parsed.event_id}", effect, refs=[parsed.event_id])
        # the ripple by order (addition): which values the news reaches directly, and which at second or third hand
        from axelrod_wm.inference.transmission import transmission_map

        trans = transmission_map(sorted({s.subentity_id for s in parsed.shocks}), channels, effect.z_of, H,
                                 int(ctx.config.propagation.min_delay_days))
        return Analysis(event_id=parsed.event_id, result=effect, expected_moves=expected, levels=shocked,
                        horizon_days=H, transmission=[e for e in trans if e.material][:24],
                        channels=channels, transmission_all=trans,
                        shocked=sorted({s.subentity_id for s in parsed.shocks}))
