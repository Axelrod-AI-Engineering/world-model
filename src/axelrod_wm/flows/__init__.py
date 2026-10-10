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

    def node(self, node_id: str) -> FlowNode:
        return next(n for n in self.nodes if n.id == node_id)

    def phase(self, phase_id: str) -> FlowPhase:
        return next(p for p in self.phases if p.id == phase_id)


def _flow(fid: str, title: str, summary: str, phases: list[dict], nodes: list[dict], edges: list[tuple]) -> Flow:
    return Flow(id=fid, title=title, summary=summary, phases=[FlowPhase(**p) for p in phases],
                nodes=[FlowNode(**n) for n in nodes],
                edges=[FlowEdge(src=e[0], dst=e[1], label=e[2] if len(e) > 2 else "") for e in edges])


WORLD_MODEL = _flow(
    "world-model", "Learning",
    "Everything that can happen to an event. Learning stages it in two parts, working memory and then long-term "
    "memory; a person then checks every change to both, including the second- and third-order ripple, and only "
    "what they approve is committed. Inference reads committed versions and never writes.",
    [
        dict(id="intake", title="Intake",
             input="A market event (news, a data release, a filing) or a backend user's edit",
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
        # intake
        dict(id="event", label="A market event or a backend user's edit", kind="start", phase="intake",
             trace=["market_event.received"]),
        dict(id="translate", label="Translate it into operations", phase="intake", component="translator",
             trace=["translate.result"]),
        dict(id="refine", label="Refine fuzzy ends: generalization → entity → subentity, or hedge across the candidates",
             phase="intake", mandatory=False, when="an end names a generalization, not a subentity", component="refiner",
             trace=["refine.step", "refine.pending"]),
        # working memory
        dict(id="parse", label="Apply new or retired structure; collect the event's moves", phase="working",
             component="parser", writes="working", trace=["parse.created", "parse.retired"]),
        dict(id="classify", label="Classify new items; they inherit their kind's priors", phase="working",
             mandatory=False, when="the event adds structure", component="classifier", writes="working",
             trace=["classify.path"]),
        dict(id="recall", label="Recall similar superentities and past days", phase="working", component="recaller",
             trace=["recall.result"]),
        dict(id="ripple", label="Simulate the ripple: first, second, third order", phase="working", mandatory=False,
             when="the event moves a value", component="analyzer", trace=["analyze.done"]),
        dict(id="fold", label="Fold: update observed values and the effects that feed them", phase="working",
             mandatory=False, when="the event reports a value", component="folder", writes="working",
             trace=["fold.posterior", "fold.edge"]),
        dict(id="hedges", label="Weigh hedged fuzzy ends; propose a resolution once one passes the bound",
             phase="working", mandatory=False, when="fuzzy ends are hedged", component="refiner", writes="working",
             trace=["refine.weighed", "refine.resolution_proposed"]),
        # long-term memory
        dict(id="kinds", label="Kinds learn their new members and statistics", phase="long_term",
             component="generalization_updater", writes="long_term", trace=["generalize.updated", "generalize.split"]),
        dict(id="memory", label="Entity memory records an actor's decision", phase="long_term", mandatory=False,
             when="the event shows an actor deciding", component="consolidator", writes="long_term"),
        dict(id="frontier", label="Correlation frontier: pair unexplained moves; propose a link once a pair holds",
             phase="long_term", component="frontier", writes="long_term",
             trace=["frontier.logged", "frontier.promotion_proposed"]),
        dict(id="support", label="Superentity support: propose a collapse when a group recurs, an expansion when one "
                                 "fades", phase="long_term", component="inducer", writes="long_term", cadence="per day",
             trace=["abduce.admission_proposed", "abduce.dissolution_proposed"]),
        dict(id="explain", label="Explain what was learned", phase="long_term", component="explainer",
             writes="long_term", trace=["explain.stored"]),
        # human review
        dict(id="check", label="A person checks every staged change to both memories, through the third-order ripple, "
                                "at the confidence they set",
             phase="review", trace=["review.queued"]),
        dict(id="decide", label="Approve?", kind="decision", phase="review", trace=["review.decided"]),
        dict(id="rejected", label="Rejected: nothing changes (logged)", kind="end", phase="review", side=True),
        # commit
        dict(id="commit_wm", label="Commit to working memory", kind="store", phase="commit", writes="working",
             trace=["state.version"]),
        dict(id="commit_ltm", label="Commit to long-term memory: a new version", kind="store", phase="commit",
             writes="long_term", trace=["state.version"]),
        dict(id="version", label="A new version in the log; inference reads committed versions", kind="end",
             phase="commit"),
    ],
    [("event", "translate"), ("translate", "refine"), ("refine", "parse"), ("translate", "parse", "concrete"),
     ("parse", "classify"), ("classify", "recall"), ("parse", "recall", "no new items"),
     ("recall", "ripple"), ("ripple", "fold"), ("recall", "fold", "no move"), ("fold", "hedges"),
     ("hedges", "kinds"), ("fold", "kinds", "no fuzzy ends"),
     ("ripple", "hedges", "nothing observed"),
     ("kinds", "memory"), ("memory", "frontier"), ("kinds", "frontier", "no decision"), ("frontier", "support"),
     ("support", "explain"), ("explain", "check"), ("check", "decide"),
     ("decide", "rejected", "no (nothing changes)"), ("decide", "check", "some (re-stage)"),
     ("decide", "commit_wm", "yes (commit)"), ("commit_wm", "commit_ltm"), ("commit_ltm", "version")],
)

from axelrod_wm.flows.inference import INFERENCE, INFERENCE_FLOWS  # noqa: E402  (they use the models above)
from axelrod_wm.flows.stages import STAGE_FLOWS  # noqa: E402

for _p in WORLD_MODEL.phases:
    _p.flow = f"stage-{_p.id}"

FLOWS: dict[str, Flow] = {f.id: f for f in (WORLD_MODEL, *STAGE_FLOWS, INFERENCE, *INFERENCE_FLOWS)}


def flow_path(flow: Flow, trace_kinds: set[str]) -> list[str]:
    """The nodes of `flow` that a set of trace kinds shows ran (in flow order)."""
    return [n.id for n in flow.nodes if set(n.trace) & trace_kinds]


__all__ = ["FLOWS", "INFERENCE", "INFERENCE_FLOWS", "STAGE_FLOWS", "WORLD_MODEL", "Flow", "FlowEdge", "FlowNode", "FlowPhase", "flow_path"]
