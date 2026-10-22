"""Inference, as data (Oct 8 restructure): how the model answers a question, apart from how it learns.

Learning (WORLD_MODEL) changes the model and stops at a person's review. Inference only reads it: a thesis runs
on a branch of a committed version that is never merged. The overview has seven stages, mutually exclusive and
together exhaustive: each answers one question with one output, so no step belongs to two stages. They use the
naming guide's terms: Pose a thesis, Isolate, Isolated prediction, Distributed prediction, Unify, Read out,
Evaluate. Each stage has its own flowchart below, drawn like the learning stages' (every condition a decision
with labeled answers, every loop drawn back, optional steps dashed).
"""

from __future__ import annotations

from axelrod_wm.flows import Flow, _flow

INFERENCE = _flow(
    "inference", "Inference",
    "How the model answers a what-if question. Seven stages, each answering one question with one output, so no "
    "step belongs to two stages. A thesis runs on a branch of a committed version that is never merged, so asking "
    "never changes the model. Only one thing flows back: once a decision's horizon passes, the outcome scores the "
    "forecast.",
    [
        dict(id="pose", title="Pose a thesis",
             input="A what-if question and the committed version it asks of",
             output="A hypothetical event with concrete ends, and the values to watch",
             detail="What is asked? A thesis is a shock (oil up 20%) or a decision held for a window (the Fed "
                    "holds). It is read into the same operations an article is, and every end must name one value."),
        dict(id="isolate", title="Isolate",
             input="The hypothetical event, applied on a branch",
             output="The networks the shock can reach: superentities, a residual network, a context network",
             detail="What can the shock reach? Only that part of the graph is simulated. A superentity the shock "
                    "touches is one network; paths outside them form a residual network; values the asker watches "
                    "form a context network."),
        dict(id="isolated", title="Isolated prediction",
             input="The networks",
             output="Each network's response on its own: its effect, shocked minus baseline",
             detail="How does each network respond alone? Each is simulated with the shocks that land in it, with "
                    "and without them, on the same random draws."),
        dict(id="distributed", title="Distributed prediction",
             input="The networks and their isolated responses",
             output="Weighted scenarios, each with the networks coupled: its effect, shocked minus baseline",
             detail="How do the networks move together? A scenario is one choice among each set of rival networks "
                    "and one answer to each open hypothesis worth branching on. Each is weighed (support, fit, "
                    "track record, hypothesis probability), the heaviest are kept, and each kept scenario couples "
                    "its networks through the interactions between them."),
        dict(id="unify", title="Unify",
             input="The weighted scenarios' effects",
             output="One forecast: every value as a distribution over the horizon",
             detail="One answer from rival stories. The forecast is the scenarios' mixture by weight, so where "
                    "they disagree it is wide or has two humps; nothing is averaged away."),
        dict(id="read_out", title="Read out",
             input="The forecast",
             output="Every value by order and transmission path, groups, binding constraints, and a brief",
             detail="What moves, when, and by which path? Order is the fewest interactions between the shock and "
                    "a value; the path is the most significant one of that length. Ablating one interaction at a "
                    "time says which ones carry the effect."),
        dict(id="evaluate", title="Evaluate",
             input="A decision recorded on the forecast, once its horizon has passed",
             output="A score for the forecast, and the track records of the superentities it used",
             detail="Did it come true? The realized values score the forecast (CRPS). A superentity whose network "
                    "called the move gains track record, which weighs the next forecast's scenarios."),
    ],
    [
        dict(id="question", label="A what-if question, asked in Predict", kind="start", phase="pose",
             trace=["thesis.posed"]),
        dict(id="translate", label="Read it into a hypothetical event: a shock, or a decision held", phase="pose"),
        dict(id="concrete", label="Does every end name one value?", kind="decision", phase="pose"),
        dict(id="ask", label="Ask the asker to pick one (nothing runs)", kind="end", phase="pose", side=True),
        dict(id="branch", label="Branch a committed version and apply the event; the branch is never merged",
             phase="isolate"),
        dict(id="networks", label="Find the networks the shock can reach", phase="isolate", component="isolator",
             trace=["isolate.networks"]),
        dict(id="alone", label="Simulate each network alone, ± the shock", phase="isolated",
             component="network_predictor", trace=["predict.network"]),
        dict(id="scenarios", label="Form scenarios from rival networks and open hypotheses; weigh them; keep the "
                                   "heaviest", phase="distributed", component="scenario_weighter",
             trace=["unify.scenarios"]),
        dict(id="couple", label="Couple each scenario's networks, ± the shock", phase="distributed",
             component="coupler", trace=["couple.done"]),
        dict(id="mix", label="Mix the scenarios by weight into one forecast", phase="unify", component="unifier"),
        dict(id="paths", label="Each value's order, path, and timing; groups; binding constraints", phase="read_out",
             trace=["forecast.ready"]),
        dict(id="brief", label="Explain it and write the brief", phase="read_out", component="explainer",
             trace=["explain.stored"]),
        dict(id="decide", label="Is a decision recorded on the forecast?", kind="decision", phase="evaluate"),
        dict(id="done", label="No: the forecast and its brief are the answer; nothing is learned", kind="end",
             phase="evaluate", side=True),
        dict(id="outcome", label="Once its horizon passes: score it; track records update",
             kind="end", phase="evaluate", mandatory=False, when="a decision cites the forecast",
             component="scorer", trace=["decision.resolved"]),
    ],
    [("question", "translate"), ("translate", "concrete"), ("concrete", "ask", "no"), ("concrete", "branch", "yes"),
     ("branch", "networks"), ("networks", "alone"), ("alone", "scenarios"), ("scenarios", "couple"),
     ("couple", "mix"), ("mix", "paths"), ("paths", "brief"), ("brief", "decide"), ("decide", "done", "no"),
     ("decide", "outcome", "yes")],
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
    "inf-isolate", "2 · Isolate: only what the shock can reach",
    "The event is applied to a branch, a copy of the committed version. The networks are the superentities the "
    "shock touches, a residual network for paths outside them, and a context network for the values the asker "
    "watches.",
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
        dict(id="out", label="The networks", kind="end", phase="find"),
    ],
    [("in", "copy"), ("copy", "apply"), ("apply", "supers"), ("supers", "residual"), ("residual", "rest", "yes"),
     ("residual", "watched", "no"), ("rest", "watched"), ("watched", "watch", "yes"),
     ("watched", "out", "no"), ("watch", "out")],
)

ISOLATED = _flow(
    "inf-isolated", "3 · Isolated prediction: each network on its own",
    "Each network is simulated with only the shocks that land in it, twice on the same random draws: with the "
    "shock and without it. The difference is that network's own response, before any network affects another.",
    [dict(id="alone", title="Alone")],
    [
        dict(id="in", label="The networks", kind="start", phase="alone"),
        dict(id="next", label="Take the next network", phase="alone"),
        dict(id="each", label="Simulate it with the shocks that land in it, and without them, on the same draws",
             phase="alone", component="network_predictor", trace=["predict.network"]),
        dict(id="more", label="More networks?", kind="decision", phase="alone"),
        dict(id="out", label="Each network's effect: shocked minus baseline", kind="end", phase="alone"),
    ],
    [("in", "next"), ("next", "each"), ("each", "more"), ("more", "next", "yes: loop"), ("more", "out", "no")],
)

DISTRIBUTED = _flow(
    "inf-distributed", "4 · Distributed prediction: the networks together, per scenario",
    "Rival networks explain the same moves differently, and some open hypotheses are worth branching on, so there "
    "is more than one way the networks can fit together. Each way is a scenario. Scenarios are weighed once, here; "
    "the heaviest are kept, and each couples its networks through the interactions between them.",
    [dict(id="scenarios", title="Scenarios"), dict(id="couple", title="Couple")],
    [
        dict(id="in", label="The networks and their isolated responses", kind="start", phase="scenarios"),
        dict(id="rival", label="Mark rivals: networks that explain the same moves with a different pattern or sign",
             phase="scenarios", component="rival_detector"),
        dict(id="open", label="An open hypothesis inside the networks, valuable and undecided?", kind="decision",
             phase="scenarios"),
        dict(id="branch", label="Branch on it: once with the interaction, once without",
             phase="scenarios", mandatory=False, when="such a hypothesis", component="hypothesis_scorer"),
        dict(id="form", label="One scenario per combination of rival choices and branched hypotheses",
             phase="scenarios"),
        dict(id="weigh", label="Weigh each: support × fit × track record × each branched hypothesis's probability; "
                               "keep the heaviest", phase="scenarios", component="scenario_weighter",
             trace=["unify.scenarios"]),
        dict(id="next", label="Take the next scenario", phase="couple"),
        dict(id="shocked", label="Couple its networks through the interactions between them, with the shock",
             phase="couple", component="coupler"),
        dict(id="baseline", label="Again without the shock, on the same random draws", phase="couple",
             component="coupler", trace=["couple.done"]),
        dict(id="more", label="More scenarios?", kind="decision", phase="couple"),
        dict(id="out", label="Weighted scenarios, each with its effect: shocked minus baseline", kind="end",
             phase="couple"),
    ],
    [("in", "rival"), ("rival", "open"), ("open", "branch", "yes"), ("open", "form", "no"),
     ("branch", "open", "another?"), ("form", "weigh"), ("weigh", "next"), ("next", "shocked"),
     ("shocked", "baseline"), ("baseline", "more"), ("more", "next", "yes: loop"), ("more", "out", "no")],
)

UNIFY = _flow(
    "inf-unify", "5 · Unify: one forecast from rival scenarios",
    "Rival scenarios are not averaged away: the forecast is their mixture by the weights distributed prediction "
    "gave them, so where they disagree the forecast is wide or has two humps.",
    [dict(id="mix", title="Mix")],
    [
        dict(id="in", label="The weighted scenarios' effects", kind="start", phase="mix"),
        dict(id="one", label="More than one scenario?", kind="decision", phase="mix"),
        dict(id="draws", label="Give each scenario draws in proportion to its weight", phase="mix",
             mandatory=False, when="rival scenarios", component="unifier"),
        dict(id="out", label="One forecast: every value as a distribution over the horizon", kind="end",
             phase="mix"),
    ],
    [("in", "one"), ("one", "draws", "yes"), ("one", "out", "no"), ("draws", "out")],
)

READ_OUT = _flow(
    "inf-read_out", "6 · Read out: what moves, when, by which path, and why",
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

EVALUATE = _flow(
    "inf-evaluate", "7 · Evaluate: how inference earns trust",
    "A forecast that someone acts on is recorded with the version it read, so it can be traced later. Once its "
    "horizon passes, what happened scores it; superentities whose networks called the move gain track record.",
    [dict(id="record", title="Record"), dict(id="score", title="Score")],
    [
        dict(id="in", label="A decision recorded on the forecast, with the version it read", kind="start",
             phase="record", trace=["decision.recorded"]),
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
    [("in", "due"), ("due", "wait", "not yet"), ("wait", "due", "check again"), ("due", "crps", "yes"),
     ("crps", "track"), ("track", "out")],
)

INFERENCE_FLOWS: tuple[Flow, ...] = (POSE, ISOLATE, ISOLATED, DISTRIBUTED, UNIFY, READ_OUT, EVALUATE)

for _p, _f in zip(INFERENCE.phases, INFERENCE_FLOWS):
    _p.flow = _f.id

__all__ = ["INFERENCE", "INFERENCE_FLOWS"]
