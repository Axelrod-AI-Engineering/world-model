"""The flowcharts, as data (Oct 8 restructure): learning, which changes the model, and inference, which only reads it.

Learning (WORLD_MODEL) runs in two parts, working memory and then long-term memory, on a staged copy of the
model; a person checks everything it would change, including the second- and third-order ripple, and only what
they approve is committed. Inference (flows/inference.py) answers a thesis on a branch of a committed version
and never writes.

Each stage (a lane) states its input and its output. A step is mandatory (it always runs) or optional (it
runs only when its `when` holds), and optional steps are drawn dashed. A step names the component that does
it (a registry slot, see engine/contracts.py), the memory it writes, and the trace kinds that show it ran.
The demo draws the flows from this data (How it works, and the strip in Review); `axelrod flows`
renders it as an SVG.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

NodeKind = Literal["start", "step", "decision", "store", "end", "link"]


class FlowNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    kind: NodeKind = "step"
    phase: str = ""
    detail: str = ""
    mandatory: bool = True
    when: str = ""                    # for an optional step: when it runs
    side: bool = False
    writes: str = ""                  # "working", "long_term", "both", or ""
    component: str = ""               # a registry slot (engine/contracts.py)
    trace: list[str] = []             # trace kinds that show this node ran
    cadence: str = ""                 # e.g. "per day"
    link: str = ""                    # for kind "link": the flow it continues in


class FlowEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    src: str
    dst: str
    label: str = ""
    drawn: bool = True                # False: a way around an optional step that its "if" caption already says


class FlowTerm(BaseModel):
    """A word the flowchart uses, with what it means here (the glossary under the chart)."""

    model_config = ConfigDict(extra="forbid")

    term: str
    meaning: str


class FlowPhase(BaseModel):
    """A stage of the flow: what it takes in and what it hands on."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    input: str = ""
    output: str = ""
    detail: str = ""
    examples: list[str] = []          # examples that isolate this stage (sim/examples/small.py)
    flow: str = ""                    # the stage's own flowchart (flows/stages.py), from input to output


class Flow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    summary: str
    phases: list[FlowPhase]
    nodes: list[FlowNode]
    edges: list[FlowEdge]
    terms: list[FlowTerm] = []

    def node(self, node_id: str) -> FlowNode:
        return next(n for n in self.nodes if n.id == node_id)

    def phase(self, phase_id: str) -> FlowPhase:
        return next(p for p in self.phases if p.id == phase_id)


def _flow(fid: str, title: str, summary: str, phases: list[dict], nodes: list[dict], edges: list[tuple],
          terms: list[tuple[str, str]] | None = None) -> Flow:
    """An edge is (src, dst), (src, dst, label), or (src, dst, label, drawn)."""
    return Flow(id=fid, title=title, summary=summary, phases=[FlowPhase(**p) for p in phases],
                nodes=[FlowNode(**n) for n in nodes],
                edges=[FlowEdge(src=e[0], dst=e[1], label=e[2] if len(e) > 2 else "", drawn=e[3] if len(e) > 3 else True)
                       for e in edges],
                terms=[FlowTerm(term=t, meaning=m) for t, m in terms or []])


WORLD_MODEL = _flow(
    "world-model", "Learning",
    "Everything that can happen to a market event. The main line runs straight down through concrete steps and yes/no "
    "checks; a step that runs only sometimes sits to the right of its check and rejoins the line. Learning stages the "
    "event in two parts, working memory and then long-term memory; a person "
    "then checks every change to both, including the second- and third-order ripple, and only what they approve "
    "is committed. Inference reads committed versions and never writes.",
    [
        dict(id="intake", title="Intake",
             input="A market event (news, a data release, a filing, an imported item) or a backend user's edit",
             output="A graph update event: operations with concrete ends",
             detail="A translator turns the event into operations: add or retire an entity, subentity, or "
                    "interaction; change or observe a value; group or dissolve a superentity. An end that names a "
                    "kind rather than a value is refined, step by step, until it names one.",
             examples=["refine", "pending"]),
        dict(id="working", title="Learning · working memory",
             input="The graph update event",
             output="The staged current state: new or retired structure, the event's moves, the ripple by order, "
                    "and updated values and effects",
             detail="What the world is like now. New items are classified and inherit their kind's priors; the "
                    "ripple is simulated order by order; observed values update themselves and the interactions "
                    "that feed them.",
             examples=["create", "links", "ripple", "fold", "analog", "weaken"]),
        dict(id="long_term", title="Learning · long-term memory",
             input="What working memory learned: classified items, unexplained moves, observed decisions",
             output="Staged lessons: kinds and their statistics, entity memories, the frontier, superentity "
                    "support, and any proposals they raise",
             detail="What the event teaches across time and entities. Kinds learn their members; a pairing that "
                    "keeps holding becomes a proposed interaction; a recurring group of entities becomes a proposed "
                    "superentity, and a faded one is proposed for dissolution.",
             examples=["inherit", "memory", "resolve", "superentity", "frontier", "split", "collapse", "expand"]),
        dict(id="review", title="Human review",
             input="Every staged change: structure, first-order moves, second- and third-order ripple, lessons",
             output="An approved selection of the changes, or a rejection",
             detail="A backend user checks that each change makes sense, not only the first-order moves but what "
                    "they set off downstream. Deselecting an item re-stages the event without it, so its ripple "
                    "disappears too. Deleting structure always waits here.",
             examples=["select", "delete"]),
        dict(id="commit", title="Commit",
             input="The approved selection",
             output="A new version: one commit to working memory, one to long-term memory",
             detail="Version control for the world model: every commit names its process, its memory, and who "
                    "vetted it, and any version can be reopened read-only or compared with another."),
    ],
    [
        # DECISION (Oct 11, revised): the main line holds only concrete steps and the checks between them. Every step
        # that runs only sometimes sits on the side, behind a check (a decision) that asks whether it applies: "yes"
        # goes out to the step, which rejoins the main line; "no" carries straight on.
        # intake
        dict(id="event", label="A market event: news, a data release, a filing, an imported item, or a backend user's "
                                "edit", kind="start", phase="intake", trace=["market_event.received"]),
        dict(id="translate", label="Translate it into operations: one graph update event", phase="intake",
             component="translator", trace=["translate.result"]),
        dict(id="q_fuzzy", label="Does an end name a kind, not a value?", kind="decision", phase="intake"),
        dict(id="refine", label="Refine the fuzzy end: kind → entity → subentity, or hedge across the candidates",
             phase="intake", component="refiner", side=True, trace=["refine.step", "refine.pending"]),
        # working memory
        dict(id="parse", label="Apply the operations: add or retire items; collect the event's moves", phase="working",
             component="parser", writes="working", trace=["parse.created", "parse.retired"]),
        dict(id="q_new", label="Does it add items?", kind="decision", phase="working"),
        dict(id="classify", label="Classify each new item into a kind; it inherits the kind's priors", phase="working",
             component="classifier", writes="working", side=True, trace=["classify.path"]),
        dict(id="recall", label="Recall similar superentities and past days", phase="working", component="recaller",
             trace=["recall.result"]),
        dict(id="q_move", label="Does it move a value?", kind="decision", phase="working"),
        dict(id="ripple", label="Simulate the ripple: first-, second-, and third-order moves", phase="working",
             component="analyzer", side=True, trace=["analyze.done"]),
        dict(id="q_report", label="Does it report a value?", kind="decision", phase="working"),
        dict(id="fold", label="Fold: update observed values and the interactions that feed them", phase="working",
             component="folder", writes="working", side=True, trace=["fold.posterior", "fold.edge"]),
        dict(id="q_hedged", label="Are fuzzy ends hedged?", kind="decision", phase="working"),
        dict(id="hedges", label="Weigh the hedges; propose a resolution once one passes the bound", phase="working",
             component="refiner", writes="working", side=True, trace=["refine.weighed", "refine.resolution_proposed"]),
        # long-term memory
        dict(id="kinds", label="Kinds learn their new members and statistics", phase="long_term",
             component="generalization_updater", writes="long_term", trace=["generalize.updated", "generalize.split"]),
        dict(id="q_actor", label="Does an actor decide?", kind="decision", phase="long_term"),
        dict(id="memory", label="Entity memory records the actor's decision", phase="long_term",
             component="consolidator", writes="long_term", side=True),
        dict(id="frontier", label="Correlation frontier: pair unexplained moves; propose an interaction once a pair "
                                  "holds", phase="long_term", component="frontier", writes="long_term",
             trace=["frontier.logged", "frontier.promotion_proposed"]),
        dict(id="support", label="Superentity support: propose a collapse when a group recurs, an expansion when one "
                                 "fades", phase="long_term", component="inducer", writes="long_term", cadence="per day",
             trace=["abduce.admission_proposed", "abduce.dissolution_proposed"]),
        dict(id="explain", label="Explain what was learned", phase="long_term", component="explainer",
             writes="long_term", trace=["explain.stored"]),
        # human review
        dict(id="check", label="The staged changes form a proposal: a person checks each one, through the "
                               "third-order ripple, at the confidence they set", phase="review", trace=["review.queued"]),
        dict(id="decide", label="Approve?", kind="decision", phase="review", trace=["review.decided"]),
        dict(id="restage", label="Re-stage without what was deselected", phase="review", side=True),
        dict(id="rejected", label="Rejected: nothing changes (logged)", kind="end", phase="review", side=True),
        # commit
        dict(id="commit_wm", label="Commit to working memory", kind="store", phase="commit", writes="working",
             trace=["state.version"]),
        dict(id="commit_ltm", label="Commit to long-term memory", kind="store", phase="commit",
             writes="long_term", trace=["state.version"]),
        dict(id="version", label="A new version in the log; inference reads committed versions only", kind="end",
             phase="commit"),
    ],
    [  # the main line, straight down
     ("event", "translate"), ("translate", "q_fuzzy"), ("q_fuzzy", "parse", "no"), ("parse", "q_new"),
     ("q_new", "recall", "no"), ("recall", "q_move"), ("q_move", "q_report", "no"), ("q_report", "q_hedged", "no"),
     ("q_hedged", "kinds", "no"), ("kinds", "q_actor"), ("q_actor", "frontier", "no"), ("frontier", "support"),
     ("support", "explain"), ("explain", "check"), ("check", "decide"), ("decide", "commit_wm", "yes"),
     ("commit_wm", "commit_ltm"), ("commit_ltm", "version"),
     # each check's "yes": the step on the side, which rejoins the main line
     ("q_fuzzy", "refine", "yes"), ("refine", "parse"),
     ("q_new", "classify", "yes"), ("classify", "recall"),
     ("q_move", "ripple", "yes"), ("ripple", "q_report"),
     ("q_report", "fold", "yes"), ("fold", "q_hedged"),
     ("q_hedged", "hedges", "yes"), ("hedges", "kinds"),
     ("q_actor", "memory", "yes"), ("memory", "frontier"),
     ("decide", "restage", "some"), ("restage", "check", "check again"),
     ("decide", "rejected", "no")],
    [
        ("Market event", "Something that happened and was published: news, a data release, a filing, or an imported "
                         "item. Its publication time decides the day it is folded in."),
        ("Imported item", "One dated piece of research in an import bundle, already read and categorized by a research "
                          "agent. Importing makes it a market event."),
        ("Operation", "One change: add or retire an item, change or observe a value, group or dissolve a superentity."),
        ("Graph update event", "The operations one market event stands for, with the evidence behind them."),
        ("Item", "Anything in the graph: an entity (an actor or an idea), a subentity (one of its values), an "
                 "interaction (a causal link), or a superentity (a recurring group)."),
        ("Kind", "A node of the taxonomy. Every item is classified into one and inherits its priors; kinds learn "
                 "from their members."),
        ("Ripple", "The moves a change sets off downstream, order by order."),
        ("Proposal", "The staged changes from one event, waiting for a person's review."),
        ("Version", "One commit. Any version can be reopened read-only or compared with another."),
    ],
)

from axelrod_wm.flows.inference import INFERENCE, INFERENCE_FLOWS  # noqa: E402  (they use the models above)
from axelrod_wm.flows.stages import STAGE_FLOWS  # noqa: E402

for _p in WORLD_MODEL.phases:
    _p.flow = f"stage-{_p.id}"

FLOWS: dict[str, Flow] = {f.id: f for f in (WORLD_MODEL, *STAGE_FLOWS, INFERENCE, *INFERENCE_FLOWS)}


def flow_path(flow: Flow, trace_kinds: set[str]) -> list[str]:
    """The nodes of `flow` that a set of trace kinds shows ran (in flow order)."""
    return [n.id for n in flow.nodes if set(n.trace) & trace_kinds]


__all__ = ["FLOWS", "INFERENCE", "INFERENCE_FLOWS", "STAGE_FLOWS", "WORLD_MODEL", "Flow", "FlowEdge", "FlowNode", "FlowPhase",
           "FlowTerm", "flow_path"]
