"""Component contracts (restructure): every pluggable slot's inputs, outputs, and side effects.

Each slot in the registry (engine/registry.py) has one contract here: the process it belongs to, how
often it runs, what it takes and returns, which memories it reads and writes, whether it always runs
(and if not, the condition that sends work to it), and the flowchart steps it carries out
(flows/__init__.py). A test keeps the contracts, the registries, and the flowchart in step. The demo shows them
under Methods → Implementation; `axelrod contracts` prints them.

Processes:
    intake               market events in, graph update events out; writes nothing
    review               vetting; decides whether a person must approve
    shared               the read of an event or a thesis, used by learning and inference alike
    learning.working     learning of working memory: the current graph and its values
    learning.long_term   learning of long-term memory: kinds, patterns, entity memories, the frontier
    dynamics             the simulation both learning and inference run on
    inference            prediction for everyone; reads a branch and writes nothing
    evaluation           scores forecasts and decisions against outcomes (track records)
    repo                 storage of commits and snapshots
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Process = Literal["intake", "review", "shared", "learning.working", "learning.long_term", "dynamics", "inference",
                  "evaluation", "repo"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot: str
    does: str
    process: Process
    cadence: str
    inputs: list[str]
    outputs: list[str]
    reads: list[str] = []
    writes: list[str] = []
    mandatory: bool = True
    condition: str = ""                # when it runs, if not always
    flow_nodes: list[str] = []         # "flow-id:node-id"
    used_by: list[str] = []            # slots or processes that call it


def _c(**kw) -> Contract:
    return Contract(**kw)


CONTRACTS: dict[str, Contract] = {c.slot: c for c in [
    # -- intake ---------------------------------------------------------------------------------
    _c(slot="source", does="Poll one source for market events published in a window", process="intake",
       cadence="per update run, per source", inputs=["cursor (last poll time)", "until"],
       outputs=["market events, in publication order"], flow_nodes=["world-model:translate"]),
    _c(slot="translator", does="Turn a market event into graph update events (operations)", process="intake",
       cadence="per market event", inputs=["market event", "templates and series map of the world",
                                           "reviewed fixtures"],
       outputs=["graph update events, or none (logged as missing)"], reads=["wm.graph", "ltm vocabularies"],
       flow_nodes=["world-model:translate"]),
    _c(slot="refiner", does="Narrow each fuzzy end: generalization, then entity, then subentity", process="intake",
       cadence="per graph update event", inputs=["graph update event"],
       outputs=["refined event", "refinement steps", "pending refinements", "soft support"],
       reads=["wm.graph", "ltm.object_generalizations", "ltm.interaction_generalizations"], mandatory=False,
       condition="an end names a concept rather than a value", flow_nodes=["world-model:refine"]),
    _c(slot="entity_resolver", does="Rank the entities a mention could name", process="intake",
       cadence="per fuzzy end", inputs=["mention", "constraints", "candidate entities"],
       outputs=["(entity, score) pairs"], reads=["wm.graph"], mandatory=False,
       condition="the refiner asks", used_by=["refiner"]),
    # -- review ---------------------------------------------------------------------------------
    _c(slot="review_policy", does="Decide whether a proposal needs a person", process="review",
       cadence="per proposal", inputs=["proposal"], outputs=["needs review", "reasons"], reads=["wm.graph"],
       flow_nodes=["world-model:check"]),
    # -- shared: the read of an event or a thesis -------------------------------------------------
    _c(slot="parser", does="Apply new or retired structure; collect shocks and observations", process="shared",
       cadence="per event or thesis", inputs=["graph update event"],
       outputs=["parsed event: created and retired items, shocks, observations, signature"],
       reads=["wm.graph"], writes=["wm.graph (a branch, for a thesis)"], flow_nodes=["world-model:parse"]),
    _c(slot="classifier", does="Sort an item down its taxonomy; the item inherits the concept's priors; "
                              "incorporate() makes it a member of the concept",
       process="shared", cadence="per new or touched item",
       inputs=["item", "taxonomy (object or interaction)"], outputs=["classification path", "priors"],
       reads=["ltm.object_generalizations", "ltm.interaction_generalizations"],
       writes=["wm.graph (priors)", "ltm taxonomy members (incorporate, long-term learning only)"],
       mandatory=False, condition="the event creates or touches items",
       flow_nodes=["world-model:classify", "world-model:kinds"]),
    _c(slot="attention", does="Keep the top few recalled items, with weights", process="shared",
       cadence="per recall", inputs=["scores"], outputs=["top-k weights"], used_by=["recaller"]),
    _c(slot="recaller", does="Recall superentities and past episodes that resemble the event", process="shared",
       cadence="per event or thesis", inputs=["parsed event"], outputs=["scored superentities",
                                                                        "scored episodes (analogs)"],
       reads=["wm.graph", "ltm.object_generalizations.patterns", "ltm.prior_states.episodes"],
       flow_nodes=["world-model:recall"]),
    _c(slot="binder", does="Bind a superentity pattern's roles to entities", process="shared",
       cadence="per recalled pattern", inputs=["pattern", "seed entities", "graph"],
       outputs=["binding (role to entity)", "missing relations, proposed for review"],
       reads=["wm.graph", "ltm.object_generalizations.patterns"], writes=["wm.graph.instances"],
       mandatory=False, condition="a recalled pattern can bind", flow_nodes=["world-model:recall"],
       used_by=["inducer", "structural"]),
    _c(slot="prefiller", does="Build the working set of interactions with their dynamics, adjusted by analogs",
       process="shared", cadence="per event or thesis", inputs=["parsed event", "recall", "bindings"],
       outputs=["prefilled model"], reads=["wm.graph", "ltm.prior_states.episodes"],
       flow_nodes=["world-model:recall"]),
    _c(slot="analyzer", does="Simulate the event's shocks through the working set: the ripple, by order",
       process="shared", cadence="per event or thesis", inputs=["parsed event", "prefilled model"],
       outputs=["expected moves", "transmission: order, path, arrival, peak"], reads=["wm"], mandatory=False,
       condition="the event changes or reports values", flow_nodes=["world-model:ripple"]),
    _c(slot="explainer", does="Explain what was learned, or what a forecast says and why", process="shared",
       cadence="per event and per forecast", inputs=["the read, the fold, the frontier; or a forecast"],
       outputs=["explanation (text, key interactions, top paths)"], reads=["wm", "ltm"],
       writes=["ltm.prior_states.explanations (learning)"],
       flow_nodes=["world-model:explain", "inference:brief"]),
    # -- dynamics ---------------------------------------------------------------------------------
    _c(slot="propagator", does="Monte Carlo simulation of shocks through lag kernels, with and without the "
                                "shocks on common random numbers",
       process="dynamics", cadence="per analysis, per network, per scenario",
       inputs=["interactions and their kernels", "shocks", "number of samples"],
       outputs=["sample paths", "effects (with minus without)"],
       flow_nodes=["world-model:ripple"], used_by=["analyzer", "network_predictor", "coupler"]),
    _c(slot="daily_propagator", does="Predict each day's values before its events; record them after",
       process="learning.working", cadence="once per day (twice: open and record)",
       inputs=["yesterday's values", "interactions"], outputs=["the day's predicted and recorded points",
                                                               "the day's moves"],
       reads=["wm.graph", "wm.deviations"], writes=["wm.deviations", "wm.graph.subentities (posteriors)",
                                                     "wm.channels"],
       flow_nodes=["world-model:commit_wm"]),
    # -- learning of working memory -----------------------------------------------------------------
    _c(slot="folder", does="Update observed values and their incoming interactions (Kalman)",
       process="learning.working", cadence="per vetted event", inputs=["parsed event", "analysis"],
       outputs=["posteriors", "unexplained moves (innovations)", "observed decisions"],
       reads=["wm"], writes=["wm.graph.subentities", "wm.graph.interactions", "wm.deviations"],
       mandatory=False, condition="the event reports values", flow_nodes=["world-model:fold"]),
    _c(slot="posterior_updater", does="One conjugate update of a value's or an interaction's posterior",
       process="learning.working", cadence="per observation", inputs=["prior", "observation"],
       outputs=["posterior"], used_by=["folder"]),
    _c(slot="kernel_updater", does="Re-estimate interactions' timing (delay, lag) from recent days",
       process="learning.working", cadence="every few days, at the close of a day",
       inputs=["recent days' values"], outputs=["interactions whose kernels changed"],
       reads=["wm.deviations", "wm.graph.interactions"], writes=["wm.graph.interactions"],
       mandatory=False, condition="the kernel cadence is due", flow_nodes=["world-model:commit_wm"]),
    _c(slot="hypothesis_scorer", does="Score hypotheses by how much they would move forecasts (value of "
                                      "information)", process="learning.working",
       cadence="at the close of a day; when a hypothesis is added", inputs=["hypotheses", "touched entities"],
       outputs=["scores"], reads=["wm", "ltm"], writes=["wm.hypotheses"], mandatory=False,
       condition="the day touched a hypothesis's entities", flow_nodes=["world-model:commit_wm"]),
    # -- learning of long-term memory ---------------------------------------------------------------
    _c(slot="taxonomy_grower", does="Split a concept whose members share a feature it lacks",
       process="learning.long_term", cadence="per event; per day for the concepts touched",
       inputs=["taxonomy", "concept"], outputs=["new concepts"],
       writes=["ltm.object_generalizations.taxonomy", "ltm.interaction_generalizations.taxonomy"],
       mandatory=False, condition="a concept is crowded", flow_nodes=["world-model:kinds"]),
    _c(slot="generalization_updater", does="Update statistics along each classification path",
       process="learning.long_term", cadence="per vetted event", inputs=["classifications"],
       outputs=["updated concepts"], writes=["ltm taxonomy statistics (support, levels, effects, kernels)"],
       flow_nodes=["world-model:kinds"]),
    _c(slot="frontier", does="Pair unexplained moves with earlier moves elsewhere; verify at spaced checks",
       process="learning.long_term", cadence="per live vetted event", inputs=["fold result"],
       outputs=["frontier entries", "promotion proposals (for review)"],
       reads=["wm.deviations"], writes=["ltm.correlation_frontier", "wm.hypotheses (presence hypotheses)"],
       mandatory=False, condition="live (not the history replay)", flow_nodes=["world-model:frontier"]),
    _c(slot="promotion_test", does="Decide whether a frontier pair has held long enough to propose",
       process="learning.long_term", cadence="per frontier check", inputs=["co-movement"],
       outputs=["pass or fail"], used_by=["frontier"], flow_nodes=["world-model:frontier"]),
    _c(slot="inducer", does="Count superentity support; form candidates; propose admission or dissolution",
       process="learning.long_term", cadence="once per day (distillation)", inputs=["the day's activity"],
       outputs=["support counts", "candidates", "admission and dissolution proposals (for review)"],
       reads=["wm.graph", "wm.activity_log"], writes=["ltm.object_generalizations.patterns"],
       flow_nodes=["world-model:support"]),
    _c(slot="consolidator", does="Distill the day: episode, analogs, support, entity memories, frontier decay, "
                                 "growth", process="learning.long_term", cadence="once per day",
       inputs=["the day's episode buffer and values"], outputs=["consolidation report"],
       reads=["wm"], writes=["ltm.prior_states", "ltm.entity_memories", "ltm.correlation_frontier",
                             "ltm taxonomies"],
       flow_nodes=["world-model:support", "world-model:memory", "world-model:frontier"]),
    # -- inference --------------------------------------------------------------------------------
    _c(slot="isolator", does="Isolate the networks a thesis touches", process="inference", cadence="per thesis",
       inputs=["the thesis's read"], outputs=["networks: superentity instances, residual, context paths"],
       reads=["wm (branch)", "ltm"], flow_nodes=["inference:networks"]),
    _c(slot="network_predictor", does="Simulate each network alone", process="inference",
       cadence="per network", inputs=["network", "inputs", "prefilled model"], outputs=["network prediction"],
       reads=["wm (branch)"], flow_nodes=["inference:alone"]),
    _c(slot="rival_detector", does="Group networks that explain the same moves differently", process="inference",
       cadence="per thesis", inputs=["networks"], outputs=["rival groups"], reads=["ltm"], mandatory=False,
       flow_nodes=["inf-distributed:rival"], used_by=["unifier"]),
    _c(slot="coupler", does="Couple the networks across their interactions, per scenario", process="inference",
       cadence="per scenario", inputs=["networks", "forced existence"], outputs=["coupled samples"],
       flow_nodes=["inference:couple"]),
    _c(slot="scenario_weighter", does="Weigh scenarios by support, fit, and track record", process="inference",
       cadence="per thesis", inputs=["scenarios", "networks"], outputs=["weights"], reads=["wm", "ltm"],
       flow_nodes=["inference:scenarios"], used_by=["unifier"]),
    _c(slot="unifier", does="Plan the scenarios and unify them into one forecast", process="inference",
       cadence="per thesis", inputs=["thesis", "scenarios"], outputs=["forecast: densities, tail quantiles"],
       flow_nodes=["inference:mix"]),
    # -- evaluation -------------------------------------------------------------------------------
    _c(slot="scorer", does="Score a forecast against what happened: omission, commission, calibration",
       process="evaluation", cadence="per evaluation or resolved decision", inputs=["forecast", "outcomes"],
       outputs=["scores"], writes=["ltm.object_generalizations.patterns (track records)"], mandatory=False,
       condition="an outcome is known", flow_nodes=["inference:outcome"]),
    # -- repo -------------------------------------------------------------------------------------
    _c(slot="storage", does="Keep commits and snapshots so every version can be restored", process="repo",
       cadence="per commit", inputs=["changesets", "snapshots"], outputs=["restorable versions"]),
]}


def contracts_by_process() -> dict[str, list[Contract]]:
    out: dict[str, list[Contract]] = {}
    for c in CONTRACTS.values():
        out.setdefault(c.process, []).append(c)
    return out


def contracts_table() -> str:
    """The contracts as a Markdown table, for docs/components.md."""
    rows = ["| Slot | Process | Cadence | Inputs | Outputs | Writes | Runs |", "|---|---|---|---|---|---|---|"]
    order = ["intake", "review", "shared", "dynamics", "learning.working", "learning.long_term", "inference",
             "evaluation", "repo"]
    for proc in order:
        for c in sorted(contracts_by_process().get(proc, []), key=lambda c: c.slot):
            runs = "always" if c.mandatory else f"if {c.condition}" if c.condition else "when called"
            rows.append(f"| `{c.slot}` | {c.process} | {c.cadence} | {'; '.join(c.inputs)} | "
                        f"{'; '.join(c.outputs)} | {'; '.join(c.writes) or '—'} | {runs} |")
    return "\n".join(rows)


__all__ = ["CONTRACTS", "Contract", "contracts_by_process", "contracts_table"]
