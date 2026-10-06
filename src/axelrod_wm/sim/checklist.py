"""The scenario checklist (§15.3), recorded while the oil_shock_demo runs."""

from __future__ import annotations

import math
from typing import Any

from axelrod_wm.control.review import ProposalKind
from axelrod_wm.memory.snapshots import load_state, state_hash

CPI, CONF = "inflation.headline_cpi", "confidence.consumer_confidence"
OIL, STANCE, RATE = "resources_energy.oil_price", "federal_reserve.policy_stance", "interest_rates.us_policy_rate"
CHIPS, CONTROLS, CAPEX = "cross_border_trade.chip_exports", "legal_regulatory.export_controls", "productivity_tech.tech_capex"
NVDA_CAPEX = "nvidia.capex"
HAWK, YIELDS = "fed_chair.hawkishness", "interest_rates.long_term_yields"
# S10 is the seeded composite (S2 + S1 + the Fed); S11-S17 group the real actors by sector and rivalry;
# HP1 and HP2 load unbound
BOUND_SEEDS = {f"S{i}" for i in range(1, 18)}
SEED_PATTERNS = BOUND_SEEDS | {"HP1", "HP2"}
# DECISION: NVIDIA (a real chipmaker) replaces the plan's fictional Northwind and sits in two superentities
LOOSE = {"market_concentration", "geography", "ecb", "fed_chair"}
N_ITEMS = 17


def _finite(*xs: float | None) -> bool:
    return all(x is not None and math.isfinite(x) for x in xs)


class ChecklistRecorder:
    def __init__(self) -> None:
        self.items: dict[int, tuple[str, bool, str]] = {}
        self.facts: dict[str, Any] = {}

    # -- wiring --------------------------------------------------------------------------------
    def attach(self, runner: Any) -> None:
        self.items = {}
        self.facts = {}
        runner.listeners = [fn for fn in runner.listeners if getattr(fn, "__self__", None) is not self]
        runner.listeners.append(self.on_runner)
        runner.controller.listeners.append(self.on_controller)
        self.runner = runner
        self._check_load(runner)

    def _set(self, n: int, label: str, ok: bool, detail: str = "") -> None:
        self.items[n] = (label, bool(ok), detail)

    # -- item 1 --------------------------------------------------------------------------------
    def _check_load(self, runner: Any) -> None:
        eng = runner.controller.engine
        g, ltm, wm = eng.wm.graph, eng.ltm, eng.wm
        ints = sorted(g.interactions)
        # DECISION: Figure 1's 33 entities with NVIDIA in Northwind's place, plus 15 more real actors
        ok_counts = (len(g.entities) == 48 and len(g.subentities) == 107 and ints == [f"e{i:02d}" for i in range(1, 91)]
                     and not any(str(i.edge_type) == "learned_causal" for i in g.interactions.values()))
        pats = ltm.object_generalizations.patterns
        admitted = {p for p, x in pats.items() if str(x.status) == "admitted"}
        others = {p for p, x in pats.items() if str(x.status) == "candidate"}
        with_inst = {i.pattern_id for i in g.instances.values()}
        ok_pats = admitted == SEED_PATTERNS and not others and with_inst == BOUND_SEEDS
        loose = {e for e in g.entities if not g.instances_of_entity(e)}
        fr = list(ltm.correlation_frontier.entries.values())
        ok_frontier = (len(fr) == 1 and fr[0].earlier_id == CPI and fr[0].later_id == CONF
                       and abs(fr[0].support - 1.0) < 1e-9)
        ok_tax = all(len(n.child_ids) == 0 or len(n.child_ids) >= 2
                     for tax in (ltm.object_generalizations.taxonomy, ltm.interaction_generalizations.taxonomy)
                     for n in tax.nodes.values())
        sup = {}
        for s in g.super_interactions.values():
            a, b = g.instances[s.source_instance_id].pattern_id, g.instances[s.target_instance_id].pattern_id
            sup[(a, b, str(s.kind))] = s
        ok_sup = (sup.get(("S2", "S1", "causal")) is not None and sup[("S2", "S1", "causal")].label == "raises costs"
                  and sup.get(("S1", "S3", "causal")) is not None and sup[("S1", "S3", "causal")].label == "sparks crises"
                  and sup.get(("S3", "S4", "causal")) is not None and sup[("S3", "S4", "causal")].label == "cuts trade finance"
                  and ("S2", "S4", "shares_members") in sup)
        dev = wm.deviations
        last = int(wm.last_processed_day)
        missing = sum(1 for d in range(dev.first_kept_day, last + 1) for s in g.subentities if dev.point(s, d) is None)
        ok_days = (missing == 0 and dev.date_of(last).isoformat() == "2026-01-25"
                   and wm.clock == dev.day_end(last))
        detail = (f"counts={ok_counts} patterns={ok_pats} loose={loose == LOOSE} frontier={ok_frontier} "
                  f"taxonomy={ok_tax} super={ok_sup} days={ok_days} (missing points {missing}, clock {wm.clock})")
        self._set(1, "Load: Figure 1's graph, seed patterns, loose entities, frontier, daily history, taxonomies, "
                     "super-interactions",
                  ok_counts and ok_pats and loose == LOOSE and ok_frontier and ok_tax and ok_sup and ok_days, detail)
        self.facts["tdiff_support_at_load"] = \
            ltm.interaction_generalizations.taxonomy.nodes["gen:int:technology_diffusion"].stats.support
        self.facts["nvda_capex_z_at_load"] = dev.z(NVDA_CAPEX, last)

    # -- controller events ---------------------------------------------------------------------
    def on_controller(self, kind: str, proposal: Any = None, result: Any = None) -> None:
        ctl = self.runner.controller
        eng = ctl.engine
        g = eng.wm.graph
        step = self.runner.step_index
        frontier = eng.ltm.correlation_frontier
        if kind == "proposed":
            if proposal.kind == ProposalKind.FRONTIER_PROMOTION:
                co = frontier.entries.get(proposal.subject_id)
                if co is not None and {co.earlier_id, co.later_id} == {CPI, CONF}:
                    self.facts.setdefault("promotion", {"step": step, "support": co.support, "proposal": proposal.id})
            elif proposal.kind == ProposalKind.SUPERENTITY_ADMISSION:
                pat = proposal.event.ops[0].pattern
                inst = next((i for i in g.instances.values() if i.pattern_id == pat.id), None)
                has = False
                if inst is not None:
                    for iid in inst.interaction_ids:
                        it = g.interactions.get(iid)
                        if it is not None and it.source_id == CONTROLS and it.target_id == CHIPS:
                            has = True
                if not has:
                    has = any(r.source_role == "legal_regulatory" and r.target_role == "cross_border_trade"
                              and r.target_attr == "trade_flow" for r in pat.relations)
                if has:
                    self.facts.setdefault("admission", {"step": step, "support": pat.support, "pattern": pat.id,
                                                        "proposal": proposal.id})
            elif proposal.kind == ProposalKind.REFINEMENT:
                for op in proposal.event.ops:
                    if op.op == "add_interaction" and getattr(op.target, "subentity_id", None) == CAPEX \
                            and getattr(op.source, "subentity_id", None) == CHIPS:
                        self.facts.setdefault("refinement", {"step": step, "proposal": proposal.id})
            return
        if kind != "applied":
            return
        me = proposal.market_event_id
        dev = eng.wm.deviations
        if me == "ME-01" and result is not None:
            sub = g.subentities[STANCE]
            released = ctl.market_events["ME-01"].data.get(STANCE)
            ops = [op.op for op in proposal.event.ops]
            top = [s.pattern_id for s in sorted(result.shared.recall.superentities,
                                                key=lambda s: (-s.attention, s.pattern_id))[:3]]
            ok = ("change_value" in ops and released is not None and abs(sub.posterior.mean() - released) <= 0.05
                  and ("S1" in top or "S8" in top))
            self._set(2, "ME-01: a change_value; the Fed stance posterior is within 0.05 of the released value; "
                         "recall ranks S1 or S8 in its top 3", ok,
                      f"ops={ops} mean={sub.posterior.mean():.3f} released={released} top3={top}")
        if me == "ME-02" and result is not None:
            before = result.shared.parsed.z_before.get(OIL)
            after = dev.z(OIL, result.fold.day)
            moves = result.shared.analysis.expected_moves
            ok = before is not None and after - before >= 1.5 and CPI in moves and moves[CPI].q50 > 0
            self._set(3, "ME-02: oil posterior rises >= 1.5 sd; the analysis expects headline CPI up", ok,
                      f"dz={after - (before or 0):.2f} cpi={moves.get(CPI).q50 if CPI in moves else None}")
        if me == "ME-06" and result is not None:
            episodes = eng.ltm.prior_states.episodes
            tags = [t for a in result.shared.recall.analogs for t in episodes[a.episode_id].tags]
            bound = {i.pattern_id for i in g.instances.values()} & {"HP1", "HP2"}
            self._set(9, "ME-06: a bank-run-like analog is recalled and HP1 or HP2 binds",
                      "bank-run-like" in tags and bool(bound), f"bound={sorted(bound)} tags={sorted(set(tags))}")
        if proposal.id == self.facts.get("promotion", {}).get("proposal"):
            ids = g.interaction_between(CPI, CONF)
            learned = [g.interactions[i] for i in ids if str(g.interactions[i].edge_type) == "learned_causal"]
            self.facts["promotion"]["applied_existence"] = learned[0].existence.mean() if learned else None
        if proposal.id == self.facts.get("admission", {}).get("proposal"):
            pid = self.facts["admission"]["pattern"]
            p = eng.ltm.object_generalizations.patterns.get(pid)
            tax = eng.ltm.object_generalizations.taxonomy
            path = tax.path_from_root(p.generalization_id) if p is not None and p.generalization_id in tax.nodes else []
            self.facts["admission"]["admitted"] = p is not None and str(p.status) == "admitted"
            self.facts["admission"]["classified"] = "gen:obj:configuration" in path
            self.facts["admission"]["bound"] = any(i.pattern_id == pid for i in g.instances.values())
        if proposal.id == self.facts.get("refinement", {}).get("proposal"):
            ids = g.interaction_between(CHIPS, CAPEX)
            self.facts["refinement"]["generalization"] = g.interactions[ids[0]].generalization_id if ids else None

    # -- runner events -------------------------------------------------------------------------
    def on_runner(self, kind: str, report: Any = None) -> None:
        runner = self.runner
        ctl = runner.controller
        eng = ctl.engine
        g, ltm = eng.wm.graph, eng.ltm
        idx = report.step_index
        if report.update_id:
            run = ctl.get_update(report.update_id)
            self.facts.setdefault("runs", []).append((idx, run.id, str(run.state), run.report is not None))
            if "ME-03-mirror" in run.duplicate_ids:
                self.facts["mirror_dropped"] = True
        if "ME-03" in report.market_event_ids:
            sub = g.subentities.get(CHIPS)
            ids = g.interaction_between(CONTROLS, CHIPS) if sub else []
            pend = [p for p in eng.wm.pending_refinements.values()
                    if int(p.reached) == 0 and p.node_id == "gen:obj:supply_factor"]
            tdiff = ltm.interaction_generalizations.taxonomy.nodes["gen:int:technology_diffusion"].stats.support
            ok = (sub is not None and str(sub.origin) == "event_parsing" and sub.features.get("product") == "semiconductors"
                  and bool(ids) and g.interactions[ids[0]].generalization_id == "gen:int:trade_restriction"
                  and len(pend) == 1 and tdiff > self.facts.get("tdiff_support_at_load", 0.0))
            self._set(4, "ME-03: chip_exports created; export_controls -> chip_exports under Trade restriction; "
                         "one pending refinement at Supply factor; Technology diffusion support grew", ok,
                      f"pending={len(pend)} tdiff={tdiff:.2f}")
        if "ME-04" in report.market_event_ids:
            me4 = ctl.market_events["ME-04"]
            rbi = g.entities.get("rbi")
            tax = ltm.object_generalizations.taxonomy
            path = tax.path_from_root(rbi.generalization_id) if rbi and rbi.generalization_id in tax.nodes else []
            ids = g.interaction_between("interest_rates.india_policy_rate", "credit_availability.india_bank_funding_cost")
            it = g.interactions[ids[0]] if ids else None
            ok = (str(me4.channel) == "user" and me4.update_id == report.update_id
                  and path == ["gen:obj:root", "gen:obj:actor", "gen:obj:monetary_authority", "gen:obj:central_bank"]
                  and g.subentities.get("rbi.policy_stance") is not None
                  and g.subentities["rbi.policy_stance"].prior_source_id == "gen:obj:central_bank"
                  and it is not None and it.generalization_id == "gen:int:policy_rate_to_bank_funding" == it.prior_source_id)
            self._set(5, "ME-04: a user event collected in step 4's update; the RBI classifies as a central bank and "
                         "inherits priors; the India funding edge classifies under Policy rate -> bank funding cost",
                      ok, f"channel={me4.channel} update={me4.update_id} path={path}")
        if idx == 6:
            ids = [i for i in g.interaction_between(HAWK, YIELDS)
                   if g.interactions[i].source_id == HAWK and str(g.interactions[i].origin) == "human"]
            self.facts["ug01"] = bool(ids)
        if idx == 12:
            self._check_by_step_12()
        if "T-01" in runner.forecasts_by_thesis and "t01" not in self.facts and idx == 13:
            self._check_t01(runner)
        if "T-02" in runner.forecasts_by_thesis and 12 not in self.items:
            self._check_t02(runner)
        if any(n.startswith("evaluation") for n in report.notes):
            rep = list(ctl.evaluations.values())[-1]
            ok = (_finite(rep.omission_rate, rep.commission_rate, rep.crps, *rep.coverage.values())
                  and set(rep.coverage) == {"50", "80", "90"} and bool(rep.pattern_hits))
            self._set(13, "Evaluation: finite omission, commission, coverage, and CRPS; pattern_hits not empty", ok,
                      f"om={rep.omission_rate:.2f} com={rep.commission_rate:.2f} crps={rep.crps:.3f} "
                      f"cov={rep.coverage} hits={rep.pattern_hits}")
        if any(n.startswith("decision") for n in report.notes):
            rec = list(ctl.decisions.values())[-1]
            v00 = ctl.forecast(runner.forecasts_by_thesis["T-00"]).based_on_version
            v01 = ctl.forecast(runner.forecasts_by_thesis["T-01"]).based_on_version
            tr = ctl.trace_decision(rec.id)
            self.facts["decision"] = {"recorded": rec.state_version == v00 == v01,
                                      "trace": tr.hash_verified and len(tr.forecasts) == 2}
        if any(n.startswith("outcome") for n in report.notes):
            rec = list(ctl.decisions.values())[-1]
            d = self.facts.get("decision", {})
            ok = d.get("recorded", False) and d.get("trace", False) and rec.outcome is not None and _finite(rec.outcome.crps)
            self._set(14, "D-01: records at the T-00/T-01 version; the trace verifies its hash; the outcome has a "
                          "finite CRPS", ok, f"{d} crps={rec.outcome.crps if rec.outcome else None}")
        if runner.step_index >= len(runner.script.steps):
            self._check_restore(runner)
            self._check_updates(runner)
            self._check_daily(runner)

    def _check_by_step_12(self) -> None:
        pr = self.facts.get("promotion")
        ok6 = (pr is not None and pr["step"] <= 12 and pr["support"] > 3 and pr.get("applied_existence") is not None
               and pr["applied_existence"] <= 0.3)
        self._set(6, "By step 12: Inflation -> Confidence proposed for promotion (support > 3); the learned edge's "
                     "existence <= 0.3", ok6, str(pr))
        ad = self.facts.get("admission")
        ok7 = (ad is not None and ad["step"] <= 12 and ad["support"] > 3 and ad.get("admitted")
               and ad.get("classified") and ad.get("bound"))
        self._set(7, "By step 12: the export-controls pattern (support > 3) is proposed, admitted under "
                     "Configuration, and bound", ok7, str(ad))
        rf = self.facts.get("refinement")
        ok8 = rf is not None and rf.get("generalization") == "gen:int:technology_diffusion"
        self._set(8, "After ME-09: the pending refinement binds tech_capex and the edge lands in Technology diffusion",
                  ok8, str(rf))

    def _check_t01(self, runner: Any) -> None:
        ctl = runner.controller
        eng = ctl.engine
        fc = ctl.forecast(runner.forecasts_by_thesis["T-01"])
        self.facts["t01"] = fc.id
        names = [s.name for s in fc.scenarios]
        s8 = next((s for s in fc.scenarios if "S8" in s.name), None)
        s9 = next((s for s in fc.scenarios if "S9" in s.name), None)
        differ = s8 is not None and s9 is not None and RATE in s8.effect_summary and RATE in s9.effect_summary and \
            s8.effect_summary[RATE][-1].q50 > s9.effect_summary[RATE][-1].q50
        pats = {n.pattern_id for n in fc.networks}
        residual = any(str(n.kind) == "residual" for n in fc.networks)
        top = max(fc.scenarios, key=lambda s: s.weight)
        dec_ok = all(set(v) - {"coupling"} == set(top.network_ids) and "coupling" in v for v in fc.decomposition.values())
        ex = ctl.explanation(fc.explanation_id)
        cpi = fc.effect_summary[CPI][-1].q50 if CPI in fc.effect_summary else None
        ok = (len(fc.scenarios) >= 2 and differ and abs(sum(s.weight for s in fc.scenarios) - 1.0) <= 1e-9
              and {"S1", "S2"} <= pats and residual and cpi is not None and cpi > 0 and dec_ok
              and ex is not None and len(ex.top_paths) >= 3 and fc.based_on_version == eng.version)
        rates = {s.name: round(s.effect_summary[RATE][-1].q50, 3) for s in fc.scenarios if RATE in s.effect_summary}
        self._set(10, "T-01: S8 and S9 scenarios differ; weights sum to 1; networks S2, S1, residual; CPI up; "
                      "decomposition; >= 3 top paths; version recorded", ok,
                  f"scenarios={names} weights={[round(s.weight, 3) for s in fc.scenarios]} rate={rates} "
                  f"pats={sorted(p for p in pats if p)} cpi={cpi} paths={len(ex.top_paths) if ex else None}")
        # item 11: pose T-01 again at the same version
        h = eng.full_state_hash()
        again = ctl.pose_thesis(ctl.theses["T-01"])
        same = again.summary == fc.summary and again.effect_summary == fc.effect_summary
        self._set(11, "Reproducibility: posing T-01 again gives identical summaries and leaves the state hash",
                  same and eng.full_state_hash() == h and again.based_on_version == fc.based_on_version,
                  f"{fc.id} vs {again.id}")
        runner.forecasts_by_thesis["T-01"] = fc.id

    def _check_t02(self, runner: Any) -> None:
        ctl = runner.controller
        t01 = ctl.forecast(runner.forecasts_by_thesis["T-01"])
        t02 = ctl.forecast(runner.forecasts_by_thesis["T-02"])
        a = t01.effect_summary[RATE][-1].q50 if RATE in t01.effect_summary else None
        b = t02.effect_summary[RATE][-1].q50 if RATE in t02.effect_summary else None
        self._set(12, "T-02: holding the Fed lowers the policy-rate effect below T-01's",
                  a is not None and b is not None and b < a, f"T-01={a} T-02={b}")

    def _check_restore(self, runner: Any) -> None:
        eng = runner.controller.engine
        from axelrod_wm.control.mutator import ChangeSet, apply_changeset
        from axelrod_wm.events.ledger import LedgerKind

        info = eng.version_info(runner.init_version)
        wm, ltm = load_state(eng.storage.load_snapshot(runner.init_version))
        for e in eng.ledger.read(info.seq if info else 0):
            if e.kind == LedgerKind.CHANGESET:
                apply_changeset(wm, ltm, ChangeSet.model_validate(e.payload))
        ok = state_hash(wm, ltm) == eng.full_state_hash() == eng.state_hash
        self._set(15, "Restore: the init snapshot plus the ledger's change sets reproduce the live state hash", ok)

    def _check_updates(self, runner: Any) -> None:
        from axelrod_wm.control.updates import UpdateRequest

        ctl = runner.controller
        steps_with_update = [i for i, st in enumerate(runner.script.steps) if st.update is not None]
        runs = {i: (rid, state, has) for i, rid, state, has in self.facts.get("runs", [])}
        all_done = all(i in runs and runs[i][1] == "done" and runs[i][2] for i in steps_with_update)
        # requesting step 17's update again collects nothing
        last = runner.script.steps[-1]
        again = ctl.request_update(UpdateRequest(requested_by="scenario", until=last.at.date(), requested_at=last.at))
        nothing = again.report is not None and sum(again.report.collected.values()) == 0 and again.report.days == 0
        # T-00 (pinned) re-posed at the end of step 17's update, at the new version
        rid = runs.get(len(runner.script.steps) - 1, (None,))[0]
        run17 = ctl.updates.get(rid) if rid else None
        t00 = [f for f in ctl.forecasts.values() if f.thesis_id == "T-00"]
        reposed = (run17 is not None and run17.report is not None and "T-00" in run17.report.reposed_theses
                   and bool(t00) and max(f.based_on_version for f in t00) == run17.report.version_after)
        ok = all_done and self.facts.get("mirror_dropped", False) and nothing and self.facts.get("ug01", False) and reposed
        self._set(16, "Update runs: every update step ran to DONE with a report; ME-03's duplicate dropped; a repeat "
                      "of step 17's update collects nothing; UG-01's edge exists (origin=human); T-00 re-posed",
                  ok, f"all_done={all_done} mirror={self.facts.get('mirror_dropped', False)} repeat_empty={nothing} "
                      f"ug01={self.facts.get('ug01')} reposed={reposed}")

    def _check_daily(self, runner: Any) -> None:
        eng = runner.controller.engine
        dev = eng.wm.deviations
        last = int(eng.wm.last_processed_day)
        observed = dev.observed_days(NVDA_CAPEX, dev.first_kept_day, last)
        moved = dev.z(NVDA_CAPEX, last) - self.facts.get("nvda_capex_z_at_load", 0.0)
        self._set(17, "Daily propagation: nvidia.capex was never observed, yet its z moved by >= 0.2",
                  not observed and abs(moved) >= 0.2, f"observed_days={len(observed)} moved={moved:+.3f}")

    # -- report --------------------------------------------------------------------------------
    def evaluate(self, runner: Any) -> list[tuple[str, bool]]:
        out = []
        for n in range(1, N_ITEMS + 1):
            if n in self.items:
                label, ok, _ = self.items[n]
            else:
                label, ok = f"item {n}: not reached", False
            out.append((f"{n:2d}. {label}", ok))
        return out

    def details(self) -> dict[int, str]:
        return {n: d for n, (_, _, d) in self.items.items()}
