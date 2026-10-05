"""The scenario checklist (§15.3), recorded while the oil_shock_demo runs."""

from __future__ import annotations

import math
from typing import Any

from axelrod_wm.control.review import ProposalKind
from axelrod_wm.memory.snapshots import load_state, state_hash

CPI, CONF = "inflation.headline_cpi", "confidence.consumer_confidence"
OIL, STANCE, RATE = "resources_energy.oil_price", "federal_reserve.policy_stance", "interest_rates.us_policy_rate"
CHIPS, CONTROLS, CAPEX = "cross_border_trade.chip_exports", "legal_regulatory.export_controls", "productivity_tech.tech_capex"
SEED_PATTERNS = {f"S{i}" for i in range(1, 10)} | {"HP1", "HP2"}
LOOSE = {"market_concentration", "geography", "ecb", "northwind_semis", "fed_chair"}


def _finite(*xs: float) -> bool:
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
        g, ltm = eng.wm.graph, eng.ltm
        ints = sorted(g.interactions)
        ok_counts = (len(g.entities) == 33 and len(g.subentities) == 69 and ints == [f"e{i:02d}" for i in range(1, 50)]
                     and not any(str(i.edge_type) == "learned_causal" for i in g.interactions.values()))
        pats = ltm.patterns.patterns
        admitted = {p for p, x in pats.items() if str(x.status) == "admitted"}
        others = {p for p, x in pats.items() if str(x.status) == "candidate"}
        with_inst = {i.pattern_id for i in g.instances.values()}
        ok_pats = admitted == SEED_PATTERNS and not others and with_inst == {f"S{i}" for i in range(1, 10)}
        loose = {e for e in g.entities if not g.instances_of_entity(e)}
        fr = list(ltm.frontier.entries.values())
        ok_frontier = (len(fr) == 1 and fr[0].earlier_id == CPI and fr[0].later_id == CONF and abs(fr[0].support - 1.0) < 1e-9)
        ok_tax = all(len(n.child_ids) in (0,) or len(n.child_ids) >= 2
                     for tax in (ltm.object_taxonomy, ltm.interaction_taxonomy) for n in tax.nodes.values())
        sup = {}
        for s in g.super_interactions.values():
            a, b = g.instances[s.source_instance_id].pattern_id, g.instances[s.target_instance_id].pattern_id
            sup[(a, b, str(s.kind))] = s
        ok_sup = (sup.get(("S2", "S1", "causal")) is not None and sup[("S2", "S1", "causal")].label == "raises costs"
                  and sup.get(("S1", "S3", "causal")) is not None and sup[("S1", "S3", "causal")].label == "sparks crises"
                  and sup.get(("S3", "S4", "causal")) is not None and sup[("S3", "S4", "causal")].label == "cuts trade finance"
                  and ("S2", "S4", "shares_members") in sup)
        detail = (f"counts={ok_counts} patterns={ok_pats} loose={loose == LOOSE} frontier={ok_frontier} "
                  f"taxonomy={ok_tax} super={ok_sup}")
        self._set(1, "Load: Figure 1's graph, seed patterns, loose entities, frontier, taxonomies, super-interactions",
                  ok_counts and ok_pats and loose == LOOSE and ok_frontier and ok_tax and ok_sup, detail)
        self.facts["tdiff_support_at_load"] = ltm.interaction_taxonomy.nodes["gen:int:technology_diffusion"].stats.support

    # -- controller events ---------------------------------------------------------------------
    def on_controller(self, kind: str, proposal: Any = None, result: Any = None) -> None:
        eng = self.runner.controller.engine
        g = eng.wm.graph
        step = self.runner.step_index
        if kind == "proposed":
            if proposal.kind == ProposalKind.FRONTIER_PROMOTION:
                co = eng.ltm.frontier.entries.get(proposal.subject_id)
                if co is not None and {co.earlier_id, co.later_id} == {CPI, CONF}:
                    self.facts.setdefault("promotion", {"step": step, "support": co.support, "proposal": proposal.id})
            elif proposal.kind == ProposalKind.SUPERENTITY_ADMISSION:
                op = proposal.event.ops[0]
                pat = op.pattern
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
        if me == "ME-01" and result is not None:
            sub = g.subentities[STANCE]
            top = [s.pattern_id for s in sorted(result.shared.recall.superentities, key=lambda s: (-s.attention, s.pattern_id))[:3]]
            ok = abs(sub.posterior.mean() - 4.75) <= 0.05 and ("S1" in top or "S8" in top)
            self._set(2, "ME-01: Fed stance posterior 4.75 +- 0.05; recall ranks S1 or S8 in its top 3", ok,
                      f"mean={sub.posterior.mean():.3f} top3={top}")
        if me == "ME-02" and result is not None:
            before = result.shared.parsed.z_before.get(OIL)
            after = eng.wm.deviations.current_z(OIL)
            moves = result.shared.analysis.expected_moves
            ok = before is not None and after - before >= 1.5 and CPI in moves and moves[CPI].q50 > 0
            self._set(3, "ME-02: oil posterior rises >= 1.5 sd; the analysis expects headline CPI up", ok,
                      f"dz={after - (before or 0):.2f} cpi={moves.get(CPI).q50 if CPI in moves else None}")
        if me == "ME-06" and result is not None:
            tags = [t for a in result.shared.recall.analogs for t in eng.ltm.episodes.episodes[a.episode_id].tags]
            bound = {i.pattern_id for i in g.instances.values()} & {"HP1", "HP2"}
            self._set(9, "ME-06: a bank-run-like analog is recalled and HP1 or HP2 binds",
                      "bank-run-like" in tags and bool(bound), f"bound={sorted(bound)}")
        if proposal.id == self.facts.get("promotion", {}).get("proposal"):
            ids = g.interaction_between(CPI, CONF)
            learned = [g.interactions[i] for i in ids if str(g.interactions[i].edge_type) == "learned_causal"]
            self.facts["promotion"]["applied_existence"] = learned[0].existence.mean() if learned else None
        if proposal.id == self.facts.get("admission", {}).get("proposal"):
            pid = self.facts["admission"]["pattern"]
            p = eng.ltm.patterns.patterns.get(pid)
            self.facts["admission"]["admitted"] = p is not None and str(p.status) == "admitted"
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
        if "ME-03" in report.market_event_ids:
            sub = g.subentities.get(CHIPS)
            ids = g.interaction_between(CONTROLS, CHIPS) if sub else []
            pend = [p for p in eng.wm.pending_refinements.values()
                    if int(p.reached) == 0 and p.node_id == "gen:obj:supply_factor"]
            tdiff = ltm.interaction_taxonomy.nodes["gen:int:technology_diffusion"].stats.support
            ok = (sub is not None and str(sub.origin) == "event_parsing" and sub.features.get("product") == "semiconductors"
                  and bool(ids) and g.interactions[ids[0]].generalization_id == "gen:int:trade_restriction"
                  and len(pend) == 1 and tdiff > self.facts.get("tdiff_support_at_load", 0.0))
            self._set(4, "ME-03: chip_exports created; export_controls -> chip_exports under Trade restriction; "
                         "one pending refinement at Supply factor; Technology diffusion support grew", ok,
                      f"pending={len(pend)} tdiff={tdiff:.2f}")
        if "ME-04" in report.market_event_ids:
            rbi = g.entities.get("rbi")
            tax = ltm.object_taxonomy
            path = tax.path_from_root(rbi.generalization_id) if rbi and rbi.generalization_id in tax.nodes else []
            ids = g.interaction_between("interest_rates.india_policy_rate", "credit_availability.india_bank_funding_cost")
            it = g.interactions[ids[0]] if ids else None
            ok = (path == ["gen:obj:root", "gen:obj:actor", "gen:obj:monetary_authority", "gen:obj:central_bank"]
                  and g.subentities.get("rbi.policy_stance") is not None
                  and g.subentities["rbi.policy_stance"].prior_source_id == "gen:obj:central_bank"
                  and it is not None and it.generalization_id == "gen:int:policy_rate_to_bank_funding" == it.prior_source_id)
            self._set(5, "ME-04: the RBI classifies as a central bank and inherits priors; the India funding edge "
                         "classifies under Policy rate -> bank funding cost", ok, f"path={path}")
        idx = report.step_index
        if idx == 11:
            self._check_by_step_11()
        if "T-01" in runner.forecasts_by_thesis and "t01" not in self.facts and idx == 12:
            self._check_t01(runner)
        if "T-02" in runner.forecasts_by_thesis and 12 not in self.items:
            self._check_t02(runner)
        if any(n.startswith("evaluation") for n in report.notes):
            rep = list(ctl.evaluations.values())[-1]
            ok = (_finite(rep.omission_rate, rep.commission_rate, rep.crps, *rep.coverage.values())
                  and set(rep.coverage) == {"50", "80", "90"} and bool(rep.pattern_hits))
            self._set(13, "Evaluation: finite omission, commission, coverage, and CRPS; pattern_hits not empty", ok,
                      f"om={rep.omission_rate:.2f} com={rep.commission_rate:.2f} crps={rep.crps:.3f} hits={rep.pattern_hits}")
        if any(n.startswith("decision") for n in report.notes):
            rec = list(ctl.decisions.values())[-1]
            v00 = ctl.forecast(runner.forecasts_by_thesis["T-00"]).based_on_version
            v01 = ctl.forecast(runner.forecasts_by_thesis["T-01"]).based_on_version
            tr = ctl.trace_decision(rec.id)
            self.facts["decision"] = {"recorded": rec.state_version == v00 == v01, "trace": tr.hash_verified and len(tr.forecasts) == 2}
        if any(n.startswith("outcome") for n in report.notes):
            rec = list(ctl.decisions.values())[-1]
            d = self.facts.get("decision", {})
            ok = d.get("recorded", False) and d.get("trace", False) and rec.outcome is not None and _finite(rec.outcome.crps)
            self._set(14, "D-01: records at the T-00/T-01 version; the trace verifies its hash; the outcome has a "
                          "finite CRPS", ok, f"{d} crps={rec.outcome.crps if rec.outcome else None}")
        if runner.step_index >= len(runner.script.steps):
            self._check_restore(runner)

    def _check_by_step_11(self) -> None:
        pr = self.facts.get("promotion")
        ok6 = (pr is not None and pr["step"] <= 11 and pr["support"] > 3 and pr.get("applied_existence") is not None
               and pr["applied_existence"] <= 0.3)
        self._set(6, "By step 11: Inflation -> Confidence promoted from the frontier (support > 3); the learned "
                     "edge's existence <= 0.3", ok6, str(pr))
        ad = self.facts.get("admission")
        ok7 = (ad is not None and ad["step"] <= 11 and ad["support"] > 3 and ad.get("admitted") and ad.get("bound"))
        self._set(7, "By step 11: the export-controls pattern (support > 3) is proposed, admitted, and bound", ok7, str(ad))
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
        differ = s8 is not None and s9 is not None and \
            s8.effect_summary[RATE][-1].q50 > s9.effect_summary[RATE][-1].q50
        pats = {n.pattern_id for n in fc.networks}
        residual = any(str(n.kind) == "residual" for n in fc.networks)
        top = max(fc.scenarios, key=lambda s: s.weight)
        dec_ok = all(set(v) - {"coupling"} == set(top.network_ids) and "coupling" in v for v in fc.decomposition.values())
        ex = ctl.explanation(fc.explanation_id)
        ok = (len(fc.scenarios) >= 2 and differ and abs(sum(s.weight for s in fc.scenarios) - 1.0) <= 1e-9
              and {"S1", "S2"} <= pats and residual and fc.effect_summary[CPI][-1].q50 > 0 and dec_ok
              and ex is not None and len(ex.top_paths) >= 3 and fc.based_on_version == eng.version)
        self._set(10, "T-01: S8 and S9 scenarios differ; weights sum to 1; networks S2, S1, residual; CPI up; "
                      "decomposition; >= 3 top paths; version recorded", ok,
                  f"scenarios={names} weights={[round(s.weight, 3) for s in fc.scenarios]} pats={sorted(p for p in pats if p)} "
                  f"cpi={fc.effect_summary[CPI][-1].q50:.3f}")
        # item 11: pose T-01 again at the same version
        h = eng.full_state_hash()
        thesis = ctl.theses["T-01"]
        again = ctl.pose_thesis(thesis)
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

    # -- report --------------------------------------------------------------------------------
    def evaluate(self, runner: Any) -> list[tuple[str, bool]]:
        out = []
        for n in range(1, 16):
            if n in self.items:
                label, ok, _ = self.items[n]
            else:
                label, ok = f"item {n}: not reached", False
            out.append((f"{n:2d}. {label}", ok))
        return out

    def details(self) -> dict[int, str]:
        return {n: d for n, (_, _, d) in self.items.items()}
