"""Running examples (Oct 8 restructure): one chain per demo, with rewind, and a library of further events.

- Running example n first plays examples 1 to n - 1 (vetted by the tutorial setup), then plays example n up to its
  focus, which waits for the person's review.
- Running an example at or before the last one played rewinds: the demo reloads and replays the earlier examples,
  with the decisions the person made on them (a selection, a rejection), then plays the chosen one.
- A library event ("more like this") runs on the current state, after the example it needs, and stops at review.
- An example with several articles runs them in order; only its focus stops for review. When the focus is a
  proposal the model raises on its own (a superentity, a learned link, a resolved end), the earlier articles are
  vetted by the setup, days are processed until the proposal appears, and other proposals raised on the way are
  set aside (deferred).

Two runners use it: SmallDemoRunner (a blank canvas, data/scenarios/small_demo) and ProdDemoRunner (the oil-shock
world after its history replay, data/scenarios/prod_demo). Every change still waits for a person (review_all).
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Any

from axelrod_wm.control.controller import ControllerError, WorldModelController
from axelrod_wm.control.updates import UpdateRequest, UpdateState
from axelrod_wm.engine.engine import build_engine, make_storage
from axelrod_wm.engine.initialize import ConstructionSpec, Initializer, load_vocabulary
from axelrod_wm.engine.registry import register
from axelrod_wm.events.graph_update import GraphUpdateEvent
from axelrod_wm.events.market import MarketEvent, MarketEventChannel, MarketEventKind
from axelrod_wm.intake.translators import (
    MarketEventTranslator,
    TranslationContext,
    TranslationResult,
    fill_event,
)
from axelrod_wm.repo.review import ProposalStatus
from axelrod_wm.sim.examples.catalog import Catalog, Example, LibraryEvent, Step, full_text_of, manual_event
from axelrod_wm.sim.runner import RunnerStatus, ScenarioRunner
from axelrod_wm.trace import Phase

REVIEWER = "backend economist"
SETUP = "demo setup"
WAIT_DAYS = 7          # how far to advance at a time while waiting for a raised proposal
WAIT_LIMIT = 84        # and for how long, at most


def feasible(ops: list[dict], graph: Any) -> list[dict]:
    """The operations whose ends exist: those that need something an earlier decision left out (a value that was
    deselected, a link that was retired) are dropped, with anything that needs them."""
    defined: set[str] = set()
    keep: list[dict] = []
    for op in ops:
        refs = []
        for end in ("source", "target"):
            t = op.get(end)
            if isinstance(t, dict) and t.get("kind") == "concrete":
                refs.append(t["subentity_id"])
            elif isinstance(t, dict) and t.get("candidate_entity_ids"):
                t["candidate_entity_ids"] = [c for c in t["candidate_entity_ids"] if c in graph.entities]
                if not t["candidate_entity_ids"]:
                    refs.append("missing")
        if op["op"] == "add_subentity":
            refs.append(op["entity"])
        ok = all(r in defined or (not r.startswith("new:") and (r in graph.subentities or r in graph.entities))
                 for r in refs)
        if op["op"] in ("reweight_interaction", "retire_interaction"):
            ok = ok and op.get("interaction_id") in graph.interactions
        if ok:
            keep.append(op)
            if op.get("temp_id"):
                defined.add(op["temp_id"])
    return keep


def article_text(headline: str, body: str) -> str:
    """The text an article's spans index into."""
    return f"{headline}\n{body}" if body else headline


@register("translator", "example")
class ExampleTranslator(MarketEventTranslator):
    """The examples' reviewed translations: the operations each sample article stands for."""

    def __init__(self, config: Any = None, runner: Any = None) -> None:
        self.config = config
        self.runner = runner

    def translate(self, event: MarketEvent, ctx: TranslationContext) -> TranslationResult:
        spec = getattr(self.runner, "event_specs", {}).get(event.id)
        if spec is None:
            return TranslationResult(market_event_id=event.id, events=[], rationale="not an example's article")
        step, override = spec
        ops = override if override is not None else self.runner.catalog.ops[step.ops](self.runner.controller,
                                                                                      event.published_at)
        ops = feasible(ops, self.runner.controller.engine.wm.graph)
        if not ops:
            return TranslationResult(market_event_id=event.id, events=[], rationale="nothing to change")
        art = step.article
        raw = {"kind": "real", "event_type": art.event_type, "confidence": 0.9, "ops": ops,
               "evidence": [{"id": f"EV-{event.id}", "source_type": "data" if art.kind == "data" else "news",
                             "excerpt": event.headline, "observed_at": event.published_at.isoformat(),
                             "strength": 0.6, "market_event_id": event.id}]}
        ev = GraphUpdateEvent.model_validate(fill_event(raw, event, "hand_drawn"))
        text = article_text(event.headline, event.body)
        spans = []
        for phrase, idx in art.quotes:
            at = text.find(phrase)
            if at >= 0:
                spans += [(at, at + len(phrase), i) for i in idx if i < len(ops)]
        return TranslationResult(market_event_id=event.id, events=[ev], rationale=art.rationale, spans=spans)


class ExampleSession:
    """The chain of examples and the library, on a loaded runner (a mixin for ScenarioRunner subclasses)."""

    catalog: Catalog

    def reset_examples(self) -> None:
        self.done: list[dict] = []           # the chain so far: {"id", "pid"} per example, in order
        self.decisions: dict[str, dict] = {}  # what the person decided on each example, replayed after a rewind
        self.manual_specs: dict[str, dict] = {}  # a manual example's form, as the person last submitted it
        self.event_specs: dict[str, tuple[Step, list[dict] | None]] = {}
        self.library_runs: list[dict] = []
        self.focus: dict | None = None       # the example or library event waiting for review
        self.n_events = 0
        self.last_event: str | None = None   # the latest article published

    def install_translator(self) -> None:
        tr = ExampleTranslator(self.controller.config, runner=self)
        for kind in MarketEventKind:
            self.controller._translators[str(kind)] = [tr]

    # -- views -----------------------------------------------------------------------------------
    def status_of(self, entry: dict | None) -> str:
        if entry is None:
            return "ready"
        if entry.get("pid") is None:
            return "skipped" if entry.get("note") else "done"
        p = self.controller.proposals.get(entry["pid"])
        if p is None:
            return "done"
        if p.status == ProposalStatus.PENDING:
            return "waiting"
        if p.status in (ProposalStatus.APPROVED, ProposalStatus.AUTO_APPLIED):
            return "waiting" if p.world_event and p.folded_day is None else "done"
        return "skipped"                     # rejected or deferred: the chain moves on without it

    def examples(self) -> list[dict]:
        out = []
        last = len(self.done)
        for i, ex in enumerate(self.catalog.examples):
            entry = self.done[i] if i < last else None
            more = [e.model_dump(mode="json") | {"status": self._library_status(e)}
                    for e in self.catalog.library if e.feature == ex.feature]
            out.append({**ex.model_dump(mode="json"), "status": self.status_of(entry), "note": entry and entry.get("note"),
                        "plays_first": max(0, i - last), "rewinds": i < last, "proposal_id": entry and entry.get("pid"),
                        "more": more})
        return out

    def _library_status(self, ev: LibraryEvent) -> str:
        runs = [r for r in self.library_runs if r["id"] == ev.id]
        return self.status_of(runs[-1]) if runs else "ready"

    # -- running ---------------------------------------------------------------------------------
    def run_example(self, key: str, manual: dict | None = None) -> dict:
        """Run example `key` (playing the ones before it, or rewinding to it). For a manual addition, `manual` is the
        form as the person left it (the example's own prefill when absent)."""
        with self.lock:
            ex = self.catalog.example(key)
            if manual is not None and ex.kind == "manual":
                self.manual_specs[ex.id] = manual
            i = self.catalog.index(key)
            self._settle()
            self._set_aside(keep_kind=None, keep=self.focus["pid"] if self.focus else None)
            waiting = self.controller.pending_proposals()
            if waiting and not (i < len(self.done) or (self.focus and self.focus["id"] == ex.id)):
                raise ControllerError(f"{waiting[0].id} still waits for review: approve or reject it first, or pick an "
                                      "earlier example to rewind")
            if self.focus and self.focus["id"] == ex.id and self.focus.get("pid") in {p.id for p in waiting}:
                return self._answer(ex, self.focus["pid"], [], rewound=False)
            rewound, played = self._reach(i)
            pid = self._play(ex, auto=False, record=None)
            return self._answer(ex, pid, played, rewound)

    def _reach(self, i: int) -> tuple[bool, list[str]]:
        """Bring the model to the state just before example i: rewind if it is already past it, then play the examples
        before it with the person's earlier decisions."""
        rewound = i < len(self.done)
        if rewound:
            self._rewind(i)
        self._remember()
        played = []
        for j in range(len(self.done), i):
            nxt = self.catalog.examples[j]
            self._play(nxt, auto=True, record=self.decisions.get(nxt.id))
            played.append(nxt.id)
        return rewound, played

    def prepare_example(self, key: str) -> dict:
        """Bring the canvas to just before example `key` without running it (Oct 9): a manual example's form then
        opens over everything the earlier examples built, so the person sees what they are adding to."""
        with self.lock:
            ex = self.catalog.example(key)
            i = self.catalog.index(key)
            self._settle()
            self._set_aside(keep_kind=None, keep=self.focus["pid"] if self.focus else None)
            waiting = self.controller.pending_proposals()
            if waiting and not i < len(self.done):
                raise ControllerError(f"{waiting[0].id} still waits for review: approve or reject it first, or pick an "
                                      "earlier example to rewind")
            rewound, played = self._reach(i)
            self.focus = None
            self.caption = f"Example {ex.n}: {ex.title}. Fill in the form (it is prefilled), then stage it for review."
            self._broadcast()
            return {"example": ex.id, "played": played, "rewound": rewound}

    def _remember(self) -> None:
        """Keep the person's decisions on the examples played so far."""
        for e in self.done:
            if e.get("pid") and e.get("by_person"):
                p = self.controller.proposals.get(e["pid"])
                if p is not None and p.status != ProposalStatus.PENDING:
                    self.decisions[e["id"]] = self._record(e)

    def run_library(self, key: str) -> dict:
        with self.lock:
            ev = self.catalog.event(key)
            self._settle()
            self._set_aside(keep_kind=None, keep=self.focus["pid"] if self.focus else None)
            waiting = self.controller.pending_proposals()
            if waiting:
                raise ControllerError(f"{waiting[0].id} still waits for review: approve or reject it first")
            need = self.catalog.index(ev.after)
            self._remember()
            played = []
            for j in range(len(self.done), need + 1):
                nxt = self.catalog.examples[j]
                self._play(nxt, auto=True, record=self.decisions.get(nxt.id))
                played.append(nxt.id)
            pid = None
            if ev.step is not None:
                pid = self._run_steps([ev.step], auto=False, raises=None)
            elif ev.edit is not None:
                pid = self.catalog.edits[ev.edit](self.controller, "backend user").id
            self.library_runs.append({"id": ev.id, "pid": pid})
            self.focus = {"id": ev.id, "pid": pid} if pid else None
            self.caption = f"More like this: {ev.title}. Check the review, then approve all, some, or none."
            self._broadcast()
            return {"event": ev.id, "proposal_id": pid, "question": ev.question, "played": played}

    def _answer(self, ex: Example, pid: str | None, played: list[str], rewound: bool) -> dict:
        note = self.done[-1].get("note") if self.done and self.done[-1]["id"] == ex.id else None
        self.caption = (f"Example {ex.n}: {ex.title}. {ex.isolates}." +
                        (" Check the review, then approve all, some, or none." if pid else f" Skipped: {note}." if note else ""))
        self._broadcast()
        return {"example": ex.id, "proposal_id": pid, "question": ex.question, "played": played, "rewound": rewound,
                "note": note}

    def _rewind(self, i: int) -> None:
        """Reload and replay the first i examples with the decisions made on them. Decisions on later examples are
        kept too, so playing past them again repeats them."""
        kept = dict(self.decisions)
        for e in self.done:
            if e.get("pid") and e.get("by_person"):
                kept[e["id"]] = self._record(e)
        self.load()
        self.decisions = kept
        for j in range(i):
            ex = self.catalog.examples[j]
            self._play(ex, auto=True, record=kept.get(ex.id))

    def _record(self, entry: dict) -> dict:
        p = self.controller.proposals.get(entry.get("pid") or "")
        if p is None:
            return {"status": "approved", "ops": None}
        status = str(p.status)
        ops = [op.model_dump(mode="json") for op in p.event.ops] if p.edited_from is not None else None
        return {"status": "rejected" if status in ("rejected", "deferred", "pending") else "approved", "ops": ops,
                "manual": entry.get("manual")}

    def _play(self, ex: Example, *, auto: bool, record: dict | None) -> str | None:
        ctl = self.controller
        by = SETUP if auto else "backend user"
        pid = None
        note = None
        manual_spec = None
        if ex.kind == "edit":
            try:
                pid = self.catalog.edits[ex.edit](ctl, by).id
            except ControllerError as exc:  # what it edits was left out by an earlier decision
                note = f"nothing to change: {exc}"
        elif ex.kind == "event":
            pid = self._run_steps(ex.steps, auto=False, raises=ex.raises if ex.focus == "raised" else None,
                                  override=(record or {}).get("ops"))
        elif ex.kind == "manual":
            # a backend user's own knowledge: no article, the form as they filled it (or the example's prefill)
            spec = (record or {}).get("manual") or self.manual_specs.get(ex.id) or ex.manual
            manual_spec = spec
            # an interaction to a value an earlier decision left out cannot be added; the rest still can
            subs = ctl.engine.wm.graph.subentities
            ok = lambda x: x.startswith("new:") or x in subs  # noqa: E731
            kept = {**spec, "interactions": [i for i in spec.get("interactions", []) if ok(i["source"]) and ok(i["target"])]}
            if not kept.get("entity") and not kept.get("values") and not kept["interactions"]:
                note = "nothing to change: what it connects to was left out earlier"
            else:
                self.n_events += 1
                try:
                    event = manual_event(kept, ctl.now, f"GUE-MAN-{self.n_events:03d}")
                    pid = ctl.submit_graph_update(event, by=by).id
                except (ControllerError, ValueError) as exc:
                    note = f"nothing to change: {exc}"
        self.done.append({"id": ex.id, "pid": pid, "by_person": not auto, "manual": manual_spec,
                          "note": note or ("nothing to change: what it needs was left out earlier"
                                           if pid is None and ex.kind == "event" else None)})
        if pid is None:
            self.focus = None
            return None
        if auto:
            if (record or {}).get("status") == "rejected":
                self._decide(pid, "reject")
            else:
                self._decide(pid, "approve")
            self.focus = None
        else:
            self.focus = {"id": ex.id, "pid": pid}
        return pid

    def _decide(self, pid: str, action: str) -> None:
        ctl = self.controller
        p = ctl.proposals[pid]
        if p.status != ProposalStatus.PENDING:
            return
        if action == "approve":
            ctl.approve(pid, by=SETUP, note="played for a later example")
        else:
            ctl.reject(pid, by=SETUP, note="rejected when it was shown")
        self._settle()

    def _settle(self) -> None:
        """Finish the active update run if nothing waits for review (approval leaves it to run on)."""
        ctl = self.controller
        run = ctl.updates.get(ctl.active_update) if ctl.active_update else None
        if run is None:
            return
        if run.state == UpdateState.AWAITING_REVIEW:
            p = ctl.proposals.get(run.waiting_on or "")
            if p is not None and p.status == ProposalStatus.PENDING:
                return
            ctl.cycle.resume(run)
        elif run.state == UpdateState.RUNNING:
            ctl.cycle.run_days(run)

    def _run_steps(self, steps: list[Step], *, auto: bool, raises: str | None,
                   override: list[dict] | None = None) -> str | None:
        """Run the articles in order. Every article but the focus is vetted by the setup. Returns the focus: the
        last article's proposal, or (with `raises`) the first proposal of that kind the model raises."""
        ctl = self.controller
        focus = None
        about = self._about(steps) if raises else set()
        for k, step in enumerate(steps):
            last = k == len(steps) - 1
            pid = self._publish(step, override if (last and raises is None) else None)
            if pid is None:
                continue
            if last and raises is None and not auto:
                focus = pid
            else:
                self._decide(pid, "approve")
            self._set_aside(keep_kind=raises)
            # the focus is picked once every article has run, so its review is grounded in the last of them
            if raises and last and (hit := self._raised(raises, preferred_only=True, about=about)):
                focus = hit
                break
        if raises and focus is None:
            # process days until the model raises it; prefer one in the examples' story, else take what came
            waited = 0
            while waited < WAIT_LIMIT and focus is None:
                self._advance(WAIT_DAYS)
                waited += WAIT_DAYS
                self._set_aside(keep_kind=raises)
                focus = self._raised(raises, preferred_only=waited < WAIT_LIMIT // 2, about=about, settle=True)
            if focus is None:
                raise ControllerError(f"the model did not raise a {raises} proposal in {WAIT_LIMIT} days")
        if raises and focus is not None:
            for p in ctl.pending_proposals():
                if p.id != focus:
                    ctl.defer(p.id, by=SETUP)
            # a proposal the model raised on its own is grounded in the article that tipped it
            raised = ctl.proposals[focus]
            if raised.market_event_id is None and self.last_event is not None:
                raised.market_event_id = self.last_event
        return focus

    PREFER = "resources_energy"          # the examples' story runs through oil

    def _entities_in(self, payload: Any) -> set[str]:
        """The entities a payload (op dicts, or an event dump) touches: named outright, through one of their values,
        or through an interaction between their values."""
        g = self.controller.engine.wm.graph
        out: set[str] = set()

        def walk(x: Any) -> None:
            if isinstance(x, dict):
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
            elif isinstance(x, str):
                ref = x.removeprefix("new:")
                if ref in g.interactions:
                    it = g.interactions[ref]
                    out.update({it.source_id.split(".")[0], it.target_id.split(".")[0]})
                elif ref.split(".")[0] in g.entities:
                    out.add(ref.split(".")[0])
        walk(payload)
        return out

    def _about(self, steps: list[Step]) -> set[str]:
        """The entities an example's articles touch (from their operations), so the proposal it focuses on is about
        what the articles say: an article about Delta's fuel cost focuses on a superentity with Delta in it."""
        out: set[str] = set()
        now = self.controller.now
        for st in steps:
            try:
                out |= self._entities_in(self.catalog.ops[st.ops](self.controller, now))
            except Exception:  # noqa: BLE001 (a builder that needs later state says nothing here)
                continue
        return out

    def _raised(self, kind: str, preferred_only: bool = False, about: set[str] | None = None,
                settle: bool = False) -> str | None:
        """The raised proposal of `kind` to focus on. DECISION (Oct 9): the one about what the example's articles
        touch: before the articles have all run, only a proposal involving every entity they touch; while waiting,
        the one involving the most of them (then oil, the examples' story); late, whatever came."""
        ctl = self.controller
        pending = [p for p in ctl.pending_proposals() if str(p.kind) == kind]
        # proposals set aside by earlier examples count too: the one about these articles may have come early
        deferred = [p for p in ctl.proposals.values() if str(p.kind) == kind and str(p.status) == "deferred"
                    and p.decided_by == SETUP] if about else []
        hits = pending + deferred
        if not hits:
            return None
        about = about or set()

        def chosen(p: Any) -> str:
            if str(p.status) == "deferred":
                from axelrod_wm.repo.review import ProposalStatus

                p.status = ProposalStatus.PENDING          # back in the queue: this example is about it
            return p.id

        def overlap(p: Any) -> int:
            return len(about & self._entities_in(p.event.model_dump(mode="json")))
        if about:
            full = [p for p in hits if overlap(p) == len(about)]
            if full:
                return chosen(full[0])
            if not settle:
                return None
            best = max(hits, key=lambda p: (overlap(p), self.PREFER in p.event.model_dump_json()))
            if overlap(best) > 0:
                return chosen(best)
        best = next((p for p in pending if self.PREFER in p.event.model_dump_json()), None)
        if best is not None:
            return best.id
        return None if preferred_only or not pending else pending[0].id

    def _set_aside(self, keep_kind: str | None, keep: str | None = None) -> None:
        """Defer proposals the model raised on its own that are not the focus (they stay in the log, deferred)."""
        ctl = self.controller
        for p in ctl.pending_proposals():
            if p.id == keep:
                continue
            if p.market_event_id and p.market_event_id in self.event_specs and str(p.kind) == "graph_update":
                continue                     # an article's own proposal
            if keep_kind is not None and str(p.kind) == keep_kind:
                continue
            ctl.defer(p.id, by=SETUP)

    def _publish(self, step: Step, override: list[dict] | None) -> str | None:
        """Publish one article on its day and run the update up to its review."""
        ctl = self.controller
        eng = ctl.engine
        dev = eng.wm.deviations
        day = int(eng.wm.last_processed_day) + max(1, step.days)
        at = datetime.combine(dev.date_of(day), time(15, 0), tzinfo=UTC)
        art = step.article
        self.n_events += 1
        kind = {"data": MarketEventKind.DATA, "filing": MarketEventKind.FILING,
                "analyst": MarketEventKind.ANALYST}.get(art.kind, MarketEventKind.NEWS)
        me = MarketEvent(id=f"EX-{self.n_events:03d}", kind=kind,
                         channel=MarketEventChannel.DATA_FEED if art.kind == "data" else MarketEventChannel.SCRAPER,
                         source=art.source, headline=art.headline, body=art.body, published_at=at, occurred_at=at,
                         mentions=list(art.mentions), event_type=art.event_type, synthetic=True,
                         full_text=full_text_of(art.headline))
        self.event_specs[me.id] = (step, override)
        self.last_event = me.id
        run = ctl.request_update(UpdateRequest(requested_by="demo", until=dev.date_of(day), requested_at=at,
                                               user_market_events=[me], sources=[]), run_to_end=True)
        self.update_ids.append(run.id)
        return run.waiting_on or next((p for ids in run.proposals.values() for p in ids), None)

    def _advance(self, days: int) -> None:
        ctl = self.controller
        dev = ctl.engine.wm.deviations
        day = int(ctl.engine.wm.last_processed_day) + days
        at = datetime.combine(dev.date_of(day), time(23, 0), tzinfo=UTC)
        ctl.request_update(UpdateRequest(requested_by="demo", until=dev.date_of(day), requested_at=at, sources=[]),
                           run_to_end=True)

    def example_status_line(self) -> RunnerStatus:
        ctl = self.controller
        run = ctl.updates.get(ctl.active_update) if ctl.active_update else None
        state = "awaiting_review" if ctl.pending_proposals() else (
            "running" if run is not None and run.state == UpdateState.RUNNING else "idle")
        return RunnerStatus(scenario_id=self.demo_id, step_index=len(self.done), total_steps=0, sim_time=ctl.now,
                            state=state, update_id=ctl.active_update, pending_proposals=len(ctl.pending_proposals()),
                            caption=self.caption, version=ctl.engine.version, loaded=self.loaded, error=self.error,
                            canvas=self.canvas_kind, examples=self.catalog.name)


class SmallDemoRunner(ExampleSession, ScenarioRunner):
    """A blank canvas: construction with no entities, no history, and the small catalog."""

    canvas_kind = "blank"

    @property
    def demo_id(self) -> str:
        return self.script.id

    def load(self) -> RunnerStatus:
        from axelrod_wm.sim.examples.small import SMALL

        with self.lock:
            self.catalog = SMALL
            cfg = self.effective_config()
            ini = self.script.initialization
            storage = self.storage if self.storage is not None else make_storage(cfg)
            storage.reset()
            vocab = load_vocabulary(ini.taxonomy_dir)
            eng = build_engine(cfg, storage, self.tracer, vocab=vocab)
            Initializer(eng).construct(ConstructionSpec.load(ini.construction_dir, ini.taxonomy_dir), ini.taxonomy_dir,
                                       start=self.script.start, vocab=vocab)
            eng.save_snapshot()
            ctl = WorldModelController(eng, scenario_dir=self.scenario_dir)
            ctl.set_review_policy("review_all")
            self._loaded(ctl, eng.version, eng.ledger.next_seq - 1)
            ctl.advance_now(datetime.combine(self.script.start, time(0), tzinfo=UTC))
            self.caption = "A blank canvas. Pick an example from Examples to start building the world model."
            self.tracer.emit(Phase.INIT, "scenario.loaded", refs=[self.script.id], scenario_id=self.script.id,
                             version=eng.version, steps=0)
            self._broadcast()
            return self.status()

    def _loaded(self, ctl: WorldModelController, version: int, seq: int) -> None:
        self.controller = ctl
        self.world = None
        self.market_source = None
        self.user_events = {}
        self.theses_spec, self.hypotheses_spec, self.decisions_spec = {}, {}, {}
        self.init_version = version
        self.init_seq = seq
        self.init_info = {"history_events": 0, "version": version, "days": 0}
        self.step_index = 0
        self.state = "idle"
        self.forecasts_by_thesis, self.thesis_aliases, self.reports = {}, {}, []
        self.pending_step = None
        self.update_ids = []
        self.loaded = True
        self.error = None
        self.reset_examples()
        self.install_translator()

    def resume(self, session: dict) -> RunnerStatus:
        raise ControllerError("the demos do not keep sessions; load them again")

    def status(self) -> RunnerStatus:
        if self.controller is None:
            return super().status()
        return self.example_status_line()


class ProdDemoRunner(ExampleSession, ScenarioRunner):
    """The oil-shock world after its history replay, with the production catalog. It shares the oil demo's init
    cache, so it starts in seconds once that cache is built."""

    canvas_kind = "scripted"
    demo_id = "prod_demo"

    def load(self) -> RunnerStatus:
        from axelrod_wm.sim.examples.prod import PROD

        with self.lock:
            self.catalog = PROD
            self.reset_examples()
            self.caption = ("The oil-shock world after three years of synthetic history. Pick an example to see each "
                            "feature in a busier system.")
            super().load()                    # the oil world: construction, seeds, history (cached), hypotheses
            ctl = self.controller
            ctl.set_review_policy("review_all")
            self.install_translator()
            self._broadcast()
            return self.status()

    def resume(self, session: dict) -> RunnerStatus:
        raise ControllerError("the demos do not keep sessions; load them again")

    def status(self) -> RunnerStatus:
        if self.controller is None or not hasattr(self, "catalog"):
            return super().status()
        return self.example_status_line()


# ---------------------------------------------------------------------------------------------------
# headless: every example in order, each staged and approved by the backend economist
# ---------------------------------------------------------------------------------------------------
def run_examples(demo: str = "small_demo", only: list[str] | None = None, *, tracer: Any = None,
                 upto: str | None = None) -> tuple[list[dict], Any]:
    """Run the examples in order (or up to `upto`, or `only` these, playing what they need first). Each is staged,
    reviewed in full, and approved; a thesis is posed. Returns one record per example shown."""
    from axelrod_wm.control.stage import stage
    from axelrod_wm.repo.snapshots import MemoryBackend
    from axelrod_wm.sim.runner import build_runner
    from axelrod_wm.trace import RecordingTracer

    tracer = tracer or RecordingTracer(run_id=f"{demo}-{datetime.now(UTC):%Y%m%d-%H%M%S}")
    runner = build_runner(demo, interactive=True, tracer=tracer, storage=MemoryBackend(), record_checklist=False)
    runner.load()
    ctl = runner.controller
    stop = runner.catalog.example(upto).id if upto else None
    out = []
    for ex in runner.catalog.examples:
        if only is not None and ex.id not in only:
            continue
        before = ctl.engine.version
        res = runner.run_example(ex.id)
        review = forecast = None
        if res["proposal_id"]:
            review = stage(ctl, res["proposal_id"], with_graph=False)
            ctl.approve(res["proposal_id"], by=REVIEWER, note="checked each staged change; approved")
            runner._settle()
        elif res["question"]:
            fc = ctl.pose_thesis(res["question"])
            forecast = {"id": fc.id, "based_on_version": fc.based_on_version,
                        "transmission": [{"value": t.subentity_id, "order": t.order, "peak": round(t.peak, 3)}
                                         for t in (fc.transmission or [])[:8]]}
        out.append({"example": ex, "review": review, "forecast": forecast, "version_before": before,
                    "version_after": ctl.engine.version, "played": res["played"]})
        if stop is not None and ex.id == stop:
            break
    return out, runner


def examples_text(records: list[dict]) -> str:
    from axelrod_wm.control.stage import format_review

    out = []
    for r in records:
        ex = r["example"]
        out += [f"{ex.n}. {ex.title}  [{ex.memory}]", f"   isolates: {ex.isolates}", ""]
        for st in ex.steps:
            out.append(f"   “{st.article.headline}” ({st.article.source})")
        if r["review"] is not None:
            out += ["   " + line for line in format_review(r["review"]).splitlines()]
        if r["forecast"] is not None:
            out.append(f"   forecast {r['forecast']['id']} on version {r['forecast']['based_on_version']} (nothing learned)")
            for t in r["forecast"]["transmission"]:
                out.append(f"     order {t['order']}: {t['value']} peak {t['peak']:+.2f} sd")
        out += [f"   version {r['version_before']} → {r['version_after']}", ""]
    return "\n".join(out)


__all__ = ["ExampleSession", "ProdDemoRunner", "SmallDemoRunner", "examples_text", "run_examples"]
