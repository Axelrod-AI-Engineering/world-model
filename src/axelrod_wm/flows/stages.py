"""The learning stages' own flowcharts (Oct 8 restructure): how each stage turns its input into its output.

The overview (flows/__init__.py, WORLD_MODEL) is five stages, each with an input and an output. Each stage here is
drawn step by step, with every condition as a decision whose answers label its arrows, and every loop drawn back
to where it repeats. Optional steps are dashed and say when they run. The demo draws them under How it works →
Learning, below the overview; `axelrod flows` prints them.
"""

from __future__ import annotations

from axelrod_wm.flows import Flow, _flow

INTAKE = _flow(
    "stage-intake", "1 · Intake: from an article to operations",
    "A translator reads the article into operations on the graph. An end that names a generalization is narrowed level "
    "by level. It binds only when the article names one candidate outright; otherwise it is hedged: every candidate "
    "keeps a probability, with a share for one not in the graph yet, until later evidence settles it.",
    [dict(id="collect", title="Collect"), dict(id="translate", title="Translate"), dict(id="refine", title="Refine each end")],
    [
        dict(id="arrive", label="An article arrives from a source (or a backend user types one)", kind="start",
             phase="collect", trace=["market_event.received"]),
        dict(id="seen", label="Seen before (same address, or same site and title)?", kind="decision", phase="collect"),
        dict(id="dup", label="Drop the duplicate (logged)", kind="end", phase="collect", side=True),
        dict(id="fixture", label="A reviewed translation exists for it?", kind="decision", phase="translate"),
        dict(id="templates", label="Translate it: templates, or a language model held to the operation schema",
             phase="translate", mandatory=False, when="no reviewed translation", component="translator"),
        dict(id="ops", label="Any operations?", kind="decision", phase="translate", trace=["translate.result"]),
        dict(id="nothing", label="Nothing to learn (logged as untranslated)", kind="end", phase="translate", side=True),
        dict(id="next_op", label="Take the next operation", phase="refine"),
        dict(id="fuzzy", label="Does an end name a kind (\"an airline\") rather than a value?", kind="decision",
             phase="refine"),
        dict(id="narrow", label="Narrow it one level: kind → entity → value, by names, aliases, and the taxonomy",
             phase="refine", mandatory=False, when="an end names a kind", component="refiner", trace=["refine.step"]),
        dict(id="one", label="Does the article name one candidate outright?", kind="decision", phase="refine"),
        dict(id="pending", label="Hedge the end: each candidate gets a probability, with a share for one not in the "
                                 "graph yet; candidate values get soft interactions, as strong as they are probable",
             phase="refine", side=True, mandatory=False, when="the article names none outright",
             component="refiner", trace=["refine.pending"]),
        dict(id="value", label="Is the end a value now?", kind="decision", phase="refine"),
        dict(id="more", label="More operations?", kind="decision", phase="refine"),
        dict(id="out", label="A graph update event: operations whose ends name values (and any hedged ends)",
             kind="end", phase="refine"),
    ],
    [("arrive", "seen"), ("seen", "dup", "yes"), ("seen", "fixture", "no"),
     ("fixture", "ops", "yes: use it"), ("fixture", "templates", "no"), ("templates", "ops"),
     ("ops", "nothing", "no"), ("ops", "next_op", "yes"),
     ("next_op", "fuzzy"), ("fuzzy", "more", "no"), ("fuzzy", "narrow", "yes"), ("narrow", "one"),
     ("one", "pending", "no: hedge it"), ("one", "value", "yes"), ("pending", "more"),
     ("value", "narrow", "no: down a level"), ("value", "more", "yes"),
     ("more", "next_op", "yes: loop"), ("more", "out", "no")],
)

WORKING = _flow(
    "stage-working", "2 · Learning of working memory: what the world is like now",
    "The operations are applied to a staged copy of the current graph. New items take their kind's priors; a moved "
    "value is carried through the interactions order by order; a reported value corrects the model where it was "
    "wrong.",
    [dict(id="day", title="The day"), dict(id="read", title="Read the event"), dict(id="ripple", title="The ripple"),
     dict(id="fold", title="The fold"), dict(id="hedges", title="Fuzzy ends")],
    [
        dict(id="event", label="The graph update event, on its day", kind="start", phase="day"),
        dict(id="open", label="The day opens: yesterday's moves ripple forward, so every value has a prediction",
             phase="day", component="daily_propagator", cadence="once per day"),
        dict(id="apply", label="Apply each operation: add or retire structure; a change becomes a shock; a report "
                               "becomes an observation", phase="read", component="parser", writes="working",
             trace=["parse.created", "parse.retired"]),
        dict(id="new", label="New entities, values, or interactions?", kind="decision", phase="read"),
        dict(id="classify", label="Sort each down its taxonomy; it inherits its kind's priors unless the article "
                                  "gave its own", phase="read", mandatory=False, when="new items",
             component="classifier", writes="working", trace=["classify.path"]),
        dict(id="recall", label="Recall superentities and past days whose signature matches the event's",
             phase="read", component="recaller", trace=["recall.result"]),
        dict(id="fits", label="Does a recalled superentity fit these entities?", kind="decision", phase="read"),
        dict(id="bind", label="Bind it as an instance; a relation it predicts but the graph lacks becomes a proposal",
             phase="read", mandatory=False, when="a superentity fits", component="binder"),
        dict(id="prefill", label="Build the working set: interactions near the event, adjusted by what followed "
                                 "similar past days", phase="read", component="prefiller", trace=["prefill.adjusted"]),
        dict(id="moves", label="Does the event move a value?", kind="decision", phase="ripple"),
        dict(id="simulate", label="Simulate with and without the move, on the same random draws; the difference is "
                                  "the event's effect", phase="ripple", mandatory=False, when="a value moves",
             component="analyzer", trace=["analyze.done"]),
        dict(id="orders", label="For each value it reaches: order = fewest interactions from the move; keep the "
                                "most significant path and when it peaks", phase="ripple", mandatory=False,
             when="a value moves"),
        dict(id="reports", label="Does the event report a value?", kind="decision", phase="fold"),
        dict(id="innovation", label="Compare the report with the day's prediction: the surprise (innovation)",
             phase="fold", mandatory=False, when="a value is reported"),
        dict(id="kalman", label="Update the value's level, and the effect and existence of each interaction into it "
                                "in proportion to how much it explains", phase="fold", mandatory=False,
             when="a value is reported", component="folder", writes="working",
             trace=["fold.posterior", "fold.edge"]),
        dict(id="held", label="Are fuzzy ends hedged, waiting for evidence?", kind="decision", phase="hedges"),
        dict(id="weigh", label="Weigh the event for each candidate: one it names, or one that moved as the interaction "
                               "predicts, gains weight, times your confidence", phase="hedges", mandatory=False,
             when="hedges are held", component="refiner", writes="working", trace=["refine.weighed"]),
        dict(id="bound", label="Has one candidate passed the bound, with enough checks?", kind="decision", phase="hedges"),
        dict(id="resolve", label="Propose the resolution: keep it, retire its rivals' soft interactions (it waits "
                                 "for review)", phase="hedges", side=True, mandatory=False,
             when="a candidate passes the bound", trace=["refine.resolution_proposed"]),
        dict(id="out", label="Staged working memory: structure, the event's moves, the ripple by order, updated "
                             "values and effects, and the hedges' new odds", kind="end", phase="hedges"),
    ],
    [("event", "open"), ("open", "apply"), ("apply", "new"), ("new", "classify", "yes"), ("new", "recall", "no"),
     ("classify", "recall"), ("recall", "fits"), ("fits", "bind", "yes"), ("fits", "prefill", "no"),
     ("bind", "prefill"), ("prefill", "moves"), ("moves", "simulate", "yes"), ("moves", "reports", "no"),
     ("simulate", "orders"), ("orders", "reports"), ("reports", "innovation", "yes"), ("reports", "held", "no"),
     ("innovation", "kalman"), ("kalman", "held"), ("held", "weigh", "yes"), ("held", "out", "no"),
     ("weigh", "bound"), ("bound", "resolve", "yes"), ("bound", "out", "not yet"), ("resolve", "out")],
)

LONG_TERM = _flow(
    "stage-long_term", "3 · Learning of long-term memory: what the event teaches",
    "What generalizes across time and entities. Kinds learn their members and pass priors to newcomers; actors' "
    "decisions are remembered by context; moves the graph did not explain are paired and, once a pair keeps "
    "holding, proposed as interactions; groups that keep firing together are proposed as superentities.",
    [dict(id="event", title="Per event"), dict(id="day", title="Per day")],
    [
        dict(id="in", label="What working memory learned: new or retired items, surprises, decisions",
             kind="start", phase="event"),
        dict(id="retired", label="Did the event retire anything?", kind="decision", phase="event"),
        dict(id="leave", label="Retired items leave their kinds; frontier entries about them decay", phase="event",
             mandatory=False, when="something was retired"),
        dict(id="join", label="New items join their kinds; statistics update along each classification path",
             phase="event", component="generalization_updater", writes="long_term",
             trace=["generalize.updated"]),
        dict(id="crowded", label="Do enough members of a kind share a feature its other children lack?",
             kind="decision", phase="event"),
        dict(id="split", label="Split: a new child kind for them, which they now inherit from", phase="event",
             mandatory=False, when="a kind is crowded", component="taxonomy_grower", trace=["generalize.split"]),
        dict(id="decided", label="Did an actor's decision show (a decision variable moved or held)?",
             kind="decision", phase="event"),
        dict(id="memory", label="Record it in the actor's entity memory, by context (what it did when inflation "
                                "ran hot, ...)", phase="event", mandatory=False, when="a decision showed",
             writes="long_term"),
        dict(id="surprise", label="A move the graph did not explain?", kind="decision", phase="event"),
        dict(id="pair", label="Pair it with earlier unexplained moves elsewhere, after removing known drivers",
             phase="event", mandatory=False, when="an unexplained move", component="frontier",
             trace=["frontier.logged"]),
        dict(id="held", label="Has a pair held at enough spaced checks?", kind="decision", phase="event"),
        dict(id="promote", label="Propose the pair as an interaction (it waits for review)", phase="event",
             side=True, mandatory=False, when="a pair keeps holding", component="promotion_test",
             trace=["frontier.promotion_proposed"]),
        dict(id="explain", label="Explain what was learned; keep it with the prior states", phase="event",
             component="explainer", writes="long_term", trace=["explain.stored"]),
        dict(id="episode", label="After the day's events: summarize the day as an episode, for recall later",
             phase="day", component="consolidator", cadence="once per day"),
        dict(id="support", label="Count support: which interactions were active together today",
             phase="day", component="inducer", cadence="once per day"),
        dict(id="known", label="Does the group match a known superentity?", kind="decision", phase="day"),
        dict(id="gain", label="It gains support", phase="day", mandatory=False, when="it matches"),
        dict(id="candidate", label="Record it as a candidate", phase="day", mandatory=False, when="it is new",
             trace=["abduce.candidate"]),
        dict(id="admit", label="Is a candidate's support above the admission threshold?", kind="decision",
             phase="day"),
        dict(id="collapse", label="Propose a collapse into a superentity (it waits for review)", phase="day",
             side=True, mandatory=False, when="support crosses the threshold",
             trace=["abduce.admission_proposed"]),
        dict(id="fade", label="Has an admitted superentity's support decayed below its floor?", kind="decision",
             phase="day"),
        dict(id="expand", label="Propose an expansion back into its members (it waits for review)", phase="day",
             side=True, mandatory=False, when="support fades", trace=["abduce.dissolution_proposed"]),
        dict(id="out", label="Staged lessons, and the proposals they raise", kind="end", phase="day"),
    ],
    [("in", "retired"), ("retired", "leave", "yes"), ("retired", "join", "no"), ("leave", "join"),
     ("join", "crowded"), ("crowded", "split", "yes"), ("crowded", "decided", "no"), ("split", "decided"),
     ("decided", "memory", "yes"), ("decided", "surprise", "no"), ("memory", "surprise"),
     ("surprise", "pair", "yes"), ("surprise", "explain", "no"), ("pair", "held"),
     ("held", "promote", "yes"), ("held", "explain", "not yet"), ("promote", "explain"),
     ("explain", "episode", "the day ends"), ("episode", "support"), ("support", "known"),
     ("known", "gain", "yes"), ("known", "candidate", "no"), ("gain", "admit"), ("candidate", "admit"),
     ("admit", "collapse", "yes"), ("admit", "fade", "no"), ("collapse", "fade"),
     ("fade", "expand", "yes"), ("fade", "out", "no"), ("expand", "out")],
)

REVIEW = _flow(
    "stage-review", "4 · Human review: does every change make sense?",
    "The person sees what the event would actually change, not only what the article says: each item, the event's "
    "own move, and the ripple at first, second, and third order. Deselecting re-stages the event, so the ripple of "
    "what is left can be checked again.",
    [dict(id="show", title="Show"), dict(id="check", title="Check"), dict(id="decide", title="Decide")],
    [
        dict(id="in", label="Every staged change: items, the event's moves, the ripple by order, lessons",
             kind="start", phase="show", trace=["review.queued"]),
        dict(id="items", label="Show each change as an item; an item that needs another goes with it", phase="show"),
        dict(id="article", label="Read the article beside them: which phrase asked for which item", phase="show"),
        dict(id="confidence", label="Set your confidence: the article's, and any change's own; it is staged again with "
                                    "it, and goes into the data it writes", phase="check"),
        dict(id="first", label="Check the event's own move: the right value, sign, and size?", phase="check"),
        dict(id="orders", label="Check each further order: does the sign follow from the path, and is the size "
                                "and timing plausible?", phase="check"),
        dict(id="sense", label="Does every change make sense?", kind="decision", phase="decide"),
        dict(id="deselect", label="Deselect the items behind what does not (and what needs them)", phase="decide",
             mandatory=False, when="some changes do not"),
        dict(id="restage", label="Re-stage without them: learning runs again on a fresh copy", phase="decide",
             mandatory=False, when="some changes do not"),
        dict(id="evidence", label="Is more evidence needed first?", kind="decision", phase="decide"),
        dict(id="defer", label="Defer: decide later; approved later, it folds in late", kind="end", phase="decide",
             side=True),
        dict(id="reject", label="Reject with a note: nothing changes (logged)", kind="end", phase="decide",
             side=True),
        dict(id="approve", label="Approve the selection; deselected operations are edited out (logged)",
             phase="decide", trace=["review.decided"]),
        dict(id="out", label="The approved selection, and who vetted it", kind="end", phase="decide"),
    ],
    [("in", "items"), ("items", "article"), ("article", "confidence"), ("confidence", "first"), ("first", "orders"), ("orders", "sense"),
     ("sense", "approve", "yes"), ("sense", "deselect", "some do not"), ("sense", "evidence", "none do"),
     ("deselect", "restage"), ("restage", "first", "check again"),
     ("evidence", "defer", "yes"), ("evidence", "reject", "no"), ("approve", "out")],
)

COMMIT = _flow(
    "stage-commit", "5 · Commit: version control for the world model",
    "Only the approved selection is written, through the same learning that was staged. Every commit names its "
    "process, its memory, and who vetted it; any version can be reopened or compared.",
    [dict(id="write", title="Write"), dict(id="day", title="Close the day")],
    [
        dict(id="in", label="The approved selection", kind="start", phase="write"),
        dict(id="effects", label="Does approval itself store anything (pending ends, soft support)?",
             kind="decision", phase="write"),
        dict(id="review", label="Commit the review's effects", kind="store", phase="write", mandatory=False,
             when="approval stores something"),
        dict(id="edit", label="A backend user's edit (collapse, expand, retire)?", kind="decision", phase="write"),
        dict(id="structural", label="One structural commit", kind="store", phase="write", side=True,
             writes="working"),
        dict(id="wm", label="Commit to working memory: the event's structure, values, and effects", kind="store",
             phase="write", writes="working", trace=["state.version"]),
        dict(id="ltm", label="Commit to long-term memory: its lessons", kind="store", phase="write",
             writes="long_term"),
        dict(id="last", label="Was it the day's last event?", kind="decision", phase="day"),
        dict(id="close", label="Record the day, distill it into long-term memory, close it (three commits)",
             kind="store", phase="day", mandatory=False, when="the day's last event", cadence="once per day"),
        dict(id="raised", label="Any proposals raised (a promoted pair, a collapse, a resolved end)?",
             kind="decision", phase="day"),
        dict(id="queue", label="They join the review queue, and go through the same review", phase="day",
             side=True, mandatory=False, when="proposals were raised"),
        dict(id="out", label="A new version in the log", kind="end", phase="day"),
    ],
    [("in", "effects"), ("effects", "review", "yes"), ("effects", "edit", "no"), ("review", "edit"),
     ("edit", "structural", "yes"), ("edit", "wm", "no: an event"), ("structural", "last"),
     ("wm", "ltm"), ("ltm", "last"), ("last", "close", "yes"), ("last", "raised", "no"), ("close", "raised"),
     ("raised", "queue", "yes"), ("raised", "out", "no"), ("queue", "out")],
)

STAGE_FLOWS: tuple[Flow, ...] = (INTAKE, WORKING, LONG_TERM, REVIEW, COMMIT)

__all__ = ["STAGE_FLOWS"]
