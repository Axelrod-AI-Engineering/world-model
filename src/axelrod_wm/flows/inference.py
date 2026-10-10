"""Inference, as data (Oct 8 restructure): how the model answers a question, apart from how it learns.

Learning (WORLD_MODEL) changes the model and stops at a person's review. Inference only reads it: a thesis runs
on a branch of a committed version that is never merged. The overview has six stages, each with an input and an
output, and each stage has its own flowchart below, drawn like the learning stages' (every condition a decision
with labeled answers, every loop drawn back, optional steps dashed).
"""

from __future__ import annotations

from axelrod_wm.flows import Flow, _flow

INFERENCE = _flow(
    "inference", "Inference",
    "How the model answers a what-if question. A thesis runs on a branch of a committed version and the branch is "
    "never merged, so asking never changes the model. The forecast is a mixture of rival scenarios, read out value "
    "by value with the order and path each move travels; once the horizon passes, the outcome scores it.",
    [
        dict(id="pose", title="Pose a thesis",
             input="A what-if question and the committed version it asks of",
             output="A hypothetical event with concrete ends, and the values to watch",
             detail="A thesis is a shock (oil up 20%) or a decision held for a window (the Fed holds). It is read "
                    "into the same operations an article is, and every end must name one value."),
        dict(id="isolate", title="Isolate the networks",
             input="The hypothetical event, applied on a branch",
             output="The networks the shock reaches: superentities and paths to the targets, rivals marked",
             detail="Only the part of the graph the shock can reach is simulated. A superentity the shock touches "
                    "is one network; two that explain the same moves differently are rivals."),
        dict(id="simulate", title="Simulate and couple",
             input="The networks, and the scenarios their rivals and open hypotheses make",
             output="For each scenario: simulated paths with and without the shock, on the same random draws",
             detail="Each network is simulated alone first, then the networks are coupled through the interactions "
                    "between them. The difference between the shocked and the baseline run is the thesis's effect."),
        dict(id="unify", title="Weigh and unify",
             input="The scenarios' simulated effects",
             output="One forecast: the scenarios mixed by weight, every value as a distribution",
             detail="A scenario's weight is its rivals' support, fit, and track record, times the probability of "
                    "each open hypothesis it assumes."),
        dict(id="read_out", title="Read out and explain",
             input="The forecast",
             output="Every value by order and transmission path, groups, binding constraints, and a brief",
             detail="Order is the fewest interactions between the shock and a value; the path is the most "
                    "significant one of that length. Ablating one interaction at a time says which ones matter."),
        dict(id="score", title="Score against outcomes",
             input="A decision taken on the forecast, once its horizon has passed",
             output="A score for the forecast, and the track records of the superentities it used",
             detail="The realized values score the forecast (CRPS). A superentity whose network called the move "
                    "gains track record, so the next forecast weighs its scenarios higher."),
    ],
    [
        dict(id="question", label="A what-if question, asked in Predict", kind="start", phase="pose",
             trace=["thesis.posed"]),
        dict(id="translate", label="Read it into a hypothetical event: a shock, or a decision held", phase="pose"),
        dict(id="concrete", label="Does every end name one value?", kind="decision", phase="pose"),
        dict(id="ask", label="Ask the asker to pick one (nothing runs)", kind="end", phase="pose", side=True),
        dict(id="branch", label="Branch a committed version and apply the event; the branch is never merged",
             phase="isolate"),
        dict(id="networks", label="Isolate the networks the shock reaches", phase="isolate", component="isolator",
             trace=["isolate.networks"]),
        dict(id="alone", label="Simulate each network alone", phase="simulate", component="network_predictor",
             trace=["predict.network"]),
        dict(id="couple", label="Couple the networks, per scenario, with and without the shock", phase="simulate",
             component="coupler", trace=["couple.done"]),
        dict(id="rivals", label="More than one scenario?", kind="decision", phase="unify"),
        dict(id="weigh", label="Weigh them: support × fit × track record × open hypotheses", phase="unify",
             mandatory=False, when="rival scenarios", component="scenario_weighter", trace=["unify.scenarios"]),
        dict(id="mix", label="Mix them into one forecast", phase="unify", component="unifier"),
        dict(id="paths", label="Each value's order, path, and timing; groups; binding constraints", phase="read_out",
             trace=["forecast.ready"]),
        dict(id="brief", label="Explain it and write the brief", phase="read_out", component="explainer",
             trace=["explain.stored"]),
        dict(id="decide", label="Does someone act on it?", kind="decision", phase="score"),
        dict(id="done", label="A forecast and its brief; nothing is learned", kind="end", phase="score", side=True),
        dict(id="record", label="Record the decision with the version it read", phase="score",
             mandatory=False, when="someone acts on it", trace=["decision.recorded"]),
        dict(id="outcome", label="After the horizon: score it against what happened; track records update",
             kind="end", phase="score", mandatory=False, when="someone acts on it", component="scorer",
             trace=["decision.resolved"]),
    ],
    [("question", "translate"), ("translate", "concrete"), ("concrete", "ask", "no"), ("concrete", "branch", "yes"),
     ("branch", "networks"), ("networks", "alone"), ("alone", "couple"), ("couple", "rivals"),
     ("rivals", "weigh", "yes"), ("rivals", "mix", "no"), ("weigh", "mix"), ("mix", "paths"), ("paths", "brief"),
     ("brief", "decide"), ("decide", "done", "no"), ("decide", "record", "yes"), ("record", "outcome")],
)

POSE = _flow(
    "inf-pose", "1 · Pose a thesis: from a question to a hypothetical event",
    "A thesis is read like an article, into operations on the graph, but it is never learned from. A held decision "
    "is a value pinned for a window, so whatever usually drives it is ignored.",
    [dict(id="ask", title="Ask"), dict(id="read", title="Read")],
    [
        dict(id="in", label="A what-if question, typed or picked in Predict", kind="start", phase="ask",
             trace=["thesis.posed"]),
        dict(id="version", label="Which version? The latest committed one, unless the asker picks an older one",
             phase="ask"),
        dict(id="kind", label="Is it a decision held for a window?", kind="decision", phase="read"),
        dict(id="hold", label="Pin the decision variable for the window; its incoming interactions are ignored",
             phase="read", mandatory=False, when="a held decision"),
        dict(id="shock", label="A shock: a change of value, in standard units", phase="read", mandatory=False,
             when="a shock"),
        dict(id="ends", label="Does every end name one value?", kind="decision", phase="read"),
        dict(id="pick", label="Show the candidates and ask the asker to pick (nothing runs)", kind="end",
             phase="read", side=True),
        dict(id="targets", label="Add the values to watch: the asker's targets, at any granularity", phase="read"),
        dict(id="out", label="A hypothetical event and its targets, on a version", kind="end", phase="read"),
    ],
    [("in", "version"), ("version", "kind"), ("kind", "hold", "yes"), ("kind", "shock", "no"), ("hold", "ends"),
     ("shock", "ends"), ("ends", "pick", "no"), ("ends", "targets", "yes"), ("targets", "out")],
)

ISOLATE = _flow(
    "inf-isolate", "2 · Isolate the networks: only what the shock can reach",
    "The event is applied to a branch, a copy of the committed version. The networks are the superentities the "
    "shock touches and the paths from the shock to each target; superentities that explain the same moves "
    "differently are marked as rivals.",
    [dict(id="branch", title="Branch"), dict(id="find", title="Find networks")],
    [
        dict(id="in", label="The hypothetical event and a committed version", kind="start", phase="branch"),
        dict(id="copy", label="Copy the version into a branch; nothing written here is merged", phase="branch"),
        dict(id="apply", label="Apply the event on the branch", phase="branch"),
        dict(id="supers", label="Collect the superentities whose members the shock reaches", phase="find",
             component="isolator", trace=["isolate.networks"]),
        dict(id="residual", label="Is there a path to a target outside them?", kind="decision", phase="find"),
        dict(id="rest", label="Add a residual network for those paths", phase="find", mandatory=False,
             when="a path lies outside them"),
        dict(id="watched", label="Does the asker watch values outside them?", kind="decision", phase="find"),
        dict(id="watch", label="Add a context network for the watched values", phase="find",
             mandatory=False, when="the asker watches more values"),
        dict(id="rival", label="Mark rivals: networks that explain the same moves with a different pattern or sign",
             phase="find", component="rival_detector"),
        dict(id="out", label="The networks, rivals marked", kind="end", phase="find"),
    ],
    [("in", "copy"), ("copy", "apply"), ("apply", "supers"), ("supers", "residual"), ("residual", "rest", "yes"),
     ("residual", "watched", "no"), ("rest", "watched"), ("watched", "watch", "yes"),
     ("watched", "rival", "no"), ("watch", "rival"), ("rival", "out")],
)

SIMULATE = _flow(
    "inf-simulate", "3 · Simulate and couple: each network, then all of them",
    "A scenario is one choice among each set of rivals, and one answer to each open hypothesis worth branching on. "
    "Each scenario is simulated twice on the same random draws, with and without the shock; the difference is the "
    "thesis's effect.",
    [dict(id="alone", title="Alone"), dict(id="scenarios", title="Scenarios"), dict(id="couple", title="Couple")],
    [
        dict(id="in", label="The networks, rivals marked", kind="start", phase="alone"),
        dict(id="each", label="Simulate each network alone, with the shocks that land in it", phase="alone",
             component="network_predictor", trace=["predict.network"]),
        dict(id="rivals", label="One scenario per choice among rivals", phase="scenarios"),
        dict(id="open", label="An open hypothesis inside the networks, valuable and undecided?", kind="decision",
             phase="scenarios"),
        dict(id="branch", label="Branch every scenario on it: once with the interaction, once without",
             phase="scenarios", mandatory=False, when="such a hypothesis", component="hypothesis_scorer"),
        dict(id="next", label="Take the next scenario", phase="couple"),
        dict(id="shocked", label="Couple its networks through the interactions between them, with the shock",
             phase="couple", component="coupler"),
        dict(id="baseline", label="Again without the shock, on the same random draws", phase="couple",
             component="coupler", trace=["couple.done"]),
        dict(id="more", label="More scenarios?", kind="decision", phase="couple"),
        dict(id="out", label="Each scenario's effect: shocked minus baseline", kind="end", phase="couple"),
    ],
    [("in", "each"), ("each", "rivals"), ("rivals", "open"), ("open", "branch", "yes"), ("open", "next", "no"),
     ("branch", "open", "another?"), ("next", "shocked"), ("shocked", "baseline"), ("baseline", "more"),
     ("more", "next", "yes: loop"), ("more", "out", "no")],
)

UNIFY = _flow(
    "inf-unify", "4 · Weigh and unify: one forecast from rival scenarios",
    "Rival scenarios are not averaged away: the forecast is their mixture, so where they disagree the forecast is "
    "wide or has two humps. A scenario's weight comes from the evidence for each choice it makes.",
    [dict(id="weigh", title="Weigh"), dict(id="mix", title="Mix")],
    [
        dict(id="in", label="The scenarios' effects", kind="start", phase="weigh"),
        dict(id="one", label="More than one scenario?", kind="decision", phase="weigh"),
        dict(id="terms", label="For each rival chosen: support (how often it held) × fit (to recent days) × "
                               "track record (how its forecasts scored)", phase="weigh", mandatory=False,
             when="rival scenarios", component="scenario_weighter"),
        dict(id="hyp", label="For each branched hypothesis: its probability, or one minus it", phase="weigh",
             mandatory=False, when="rival scenarios"),
        dict(id="keep", label="Keep the heaviest scenarios; report the weight dropped", phase="weigh",
             mandatory=False, when="rival scenarios", trace=["unify.scenarios"]),
        dict(id="draws", label="Give each scenario draws in proportion to its weight", phase="mix",
             component="unifier"),
        dict(id="out", label="One forecast: every value as a distribution over the horizon", kind="end",
             phase="mix"),
    ],
    [("in", "one"), ("one", "terms", "yes"), ("one", "draws", "no"), ("terms", "hyp"), ("hyp", "keep"),
     ("keep", "draws"), ("draws", "out")],
)

READ_OUT = _flow(
    "inf-read_out", "5 · Read out and explain: how each value moves, and why",
    "The forecast is read value by value: how far it moves, when, and by which path. A coarser target (an entity, "
    "a sector) is the average of its values, draw by draw, so its uncertainty is honest.",
    [dict(id="values", title="Values"), dict(id="why", title="Why")],
    [
        dict(id="in", label="The forecast", kind="start", phase="values"),
        dict(id="order", label="Each value: order (fewest interactions from the shock), main path, arrival, peak",
             phase="values"),
        dict(id="groups", label="Does the thesis ask about an entity, a sector, or a category?", kind="decision",
             phase="values"),
        dict(id="avg", label="Average its values draw by draw", phase="values", mandatory=False,
             when="a coarser target"),
        dict(id="bounds", label="Note where a soft bound bent a value, beyond the baseline", phase="values"),
        dict(id="ablate", label="Ablate the main interactions one at a time: which ones carry the effect?",
             phase="why"),
        dict(id="explain", label="Write the explanation and the brief", phase="why", component="explainer",
             trace=["explain.stored", "forecast.ready"]),
        dict(id="out", label="A forecast and its brief; nothing is learned", kind="end", phase="why"),
    ],
    [("in", "order"), ("order", "groups"), ("groups", "avg", "yes"), ("groups", "bounds", "no"), ("avg", "bounds"),
     ("bounds", "ablate"), ("ablate", "explain"), ("explain", "out")],
)

SCORE = _flow(
    "inf-score", "6 · Score against outcomes: how inference earns trust",
    "A forecast that someone acts on is recorded with the version it read, so it can be traced later. Once its "
    "horizon passes, what happened scores it; superentities whose networks called the move gain track record.",
    [dict(id="record", title="Record"), dict(id="score", title="Score")],
    [
        dict(id="in", label="A forecast and its brief", kind="start", phase="record"),
        dict(id="act", label="Does someone act on it?", kind="decision", phase="record"),
        dict(id="none", label="Nothing more happens; the forecast stays in its layer", kind="end", phase="record",
             side=True),
        dict(id="record", label="Record the decision: the forecasts, the version, and when to check",
             phase="record", mandatory=False, when="someone acts on it", trace=["decision.recorded"]),
        dict(id="due", label="Has the horizon passed?", kind="decision", phase="score"),
        dict(id="wait", label="Wait a day; learning goes on meanwhile", phase="score", mandatory=False,
             when="the horizon has not passed"),
        dict(id="crps", label="Score the forecast against the realized values (CRPS)", phase="score",
             component="scorer", trace=["decision.resolved"]),
        dict(id="track", label="Each superentity used: did its network call the move? Its track record updates",
             phase="score"),
        dict(id="out", label="A score, and track records that weigh the next forecast's scenarios", kind="end",
             phase="score"),
    ],
    [("in", "act"), ("act", "none", "no"), ("act", "record", "yes"), ("record", "due"), ("due", "wait", "not yet"),
     ("wait", "due", "check again"), ("due", "crps", "yes"), ("crps", "track"), ("track", "out")],
)

INFERENCE_FLOWS: tuple[Flow, ...] = (POSE, ISOLATE, SIMULATE, UNIFY, READ_OUT, SCORE)

for _p, _f in zip(INFERENCE.phases, INFERENCE_FLOWS):
    _p.flow = _f.id

__all__ = ["INFERENCE", "INFERENCE_FLOWS"]
