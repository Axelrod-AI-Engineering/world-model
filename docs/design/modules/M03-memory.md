# M03 · Memory

**Layer** 2 · **Package** `memory/` · **Status** exists. Its logic moves out:
- `SuperInteractionBuilder` → M09;
- the frontier ABCs → M01;
- `open_world.py` → M14.

## Purpose

The two memories, as state only. **Working memory** is what the world is like now. **Long-term memory** is what generalizes across time and entities. Algorithms write to them only through a `MutationTxn` ([M04](M04-repo.md)). [cognition.md F1](../cognition.md#f1--two-memories-consolidated-daily) explains why there are two.

## Owns

```python
class WorkingMemory(BaseModel):
    clock; graph: CausalGraph
    deviations: DeviationHistory            # z per subentity per day
    channels: dict[str, ChannelState]       # kernel recursion state per interaction direction
    hypotheses: dict[str, Hypothesis]       # the hypothesis frontier
    pending_refinements: dict[str, PendingRefinement]   # hedges
    ripple_judgments: dict[str, RippleJudgment]
    forecast_layer: ForecastLayer           # outside the state hash
    activity_log; episode_buffer; late_queue; source_cursors; ids

class LongTermMemory(BaseModel):            # the UI's five tabs, in this order
    object_generalizations                  # kinds + superentity patterns
    interaction_generalizations
    entity_memories: dict[str, EntityMemory]   # decisions by context
    correlation_frontier                    # co-movements with no interaction
    prior_states                            # episodes, explanations

dump_state(wm, ltm) -> bytes; load_state(blob) -> (wm, ltm)
```

## Depends on

[M01](M01-foundation.md), [M02](M02-model.md).

## Diagram

```mermaid
%% style: begin (scripts/docs/style_mermaid.py)
%%{init: {"theme": "base", "themeVariables": {"fontSize": "14px", "primaryColor": "#FFFDF8", "primaryBorderColor": "#C9BFAF", "primaryTextColor": "#2F2A25", "lineColor": "#857C70", "textColor": "#2F2A25", "secondaryColor": "#F7F2EA", "tertiaryColor": "#FBF8F2", "edgeLabelBackground": "#F7F2EA", "clusterBkg": "#F7F2EA", "clusterBorder": "#E4DACB", "titleColor": "#665E54"}}}%%
%% style: end
flowchart LR
  EV["Vetted event"]:::start ==>|learn.working| WM["Working memory<br/>the world now"]:::wm
  EV ==>|learn.long_term| LTM["Long-term memory<br/>what generalizes"]:::ltm
  WM ==>|"day.distill: episodes, superentity support,<br/>Entity memories, frontier decay"| LTM
  LTM -->|priors · analogs · patterns to bind| WM
  WM -.->|day.record · day.close| WM
  %% style: classes and happy path
  classDef start fill:#DAD0F4,stroke:#7C64C4,stroke-width:1.5px,color:#2F2A25
  classDef wm fill:#E1ECDF,stroke:#A9C6A9,stroke-width:1.3px,color:#3E6A46
  classDef ltm fill:#DCE6F0,stroke:#A9BFD6,stroke-width:1.3px,color:#3B5B7C
  linkStyle 0,1,2 stroke:#7C64C4,stroke-width:2.6px,color:#5B4A99
  %% style: end
```

## Invariants

- **State, not logic.** No imports from layer 3 or above. Today `memory/` imports `dynamics.kernels` and `inference.records`.
- **The forecast layer is not state.** It never bumps the version and is excluded from the hash.
- **Exact past states are snapshots,** not long-term memory.
- **Learning writes memory; inference never does.**

## Planned

- Proposals, theses, forecasts, and decisions live in the controller's memory today. They move to ledger-backed stores ([M04](M04-repo.md)).

## Done when

- `dump_state`/`load_state` round-trips.
- The forecast layer stays out of the hash.
- The layer test passes.
