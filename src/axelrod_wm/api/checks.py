"""Checks (Oct 9): when the model tests what it believes, how, and exactly what each test updates.

A check is one step that weighs evidence and moves a stored weight. The catalog says, for each kind, when it runs,
what it reads, which stored fields it writes, and the bound that turns enough evidence into a proposal for review
(with the configured values). The live view lists what is being checked now: each hedged fuzzy end, each held
co-movement, and each candidate superentity, with its progress toward its bound and when it can next be checked.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from axelrod_wm.control.controller import WorldModelController


def catalog(cfg: Any) -> list[dict]:
    rec = int(cfg.thresholds.recognition)
    ref = cfg.refinement
    fr = cfg.frontier
    ab = cfg.abduction
    return [
        {"id": "hedge", "name": "Hedge check", "memory": "working", "when": "each article, as working memory learns it",
         "how": "An article that names a candidate, or a move of a candidate's value in the direction the interaction "
                "says, adds pseudo-counts to that candidate; a move against it spreads them over the rivals and the "
                "open share. One article counts as one check, however many records it leaves.",
         "reads": "the article's mentions, its moves, and each candidate's unexplained move",
         "updates": "the hedge's Dirichlet counts (alpha, open_alpha), its support (+1 per article), and the existence "
                    "of its soft interactions, which follow the posterior",
         "bound": f"one candidate past {round(100 * float(ref.commit_posterior))}% after {rec} articles: a refinement "
                  "goes to review",
         "after_review": "approved: the winner is kept and its rivals retired; rejected: half the winner's weight "
                         "returns to the open share and its support restarts at 0"},
        {"id": "existence", "name": "Existence evidence", "memory": "working",
         "when": "each observed value, as the fold learns it",
         "how": "The fold compares how well the value's move is predicted with and without each incoming interaction; "
                "the better the interaction predicts it, the more the belief that it exists grows.",
         "reads": "the observed value and each incoming interaction's regressor that day",
         "updates": f"each incoming interaction's existence Beta (rate {cfg.learning.existence_learning_rate}) and its "
                    "effect",
         "bound": "none: it moves the belief continuously; a person retires a link", "after_review": ""},
        {"id": "frontier", "name": "Spaced verification", "memory": "long_term",
         "when": f"each article whose value moves without a cause in the graph; a pair at most once every "
                 f"{int(fr.evidence_spacing_days)} days",
         "how": "A value that moves unexplained is paired with an earlier move that could have caused it; each later "
                "check either passes (the same sign again, a large enough source move) or fails.",
         "reads": f"window innovations over {int(fr.window_days)} days at the pair's lag",
         "updates": "the co-movement's support (+1 if it passes, -1 if it fails), its correlation, and its hypothesis's "
                    "probability, support / (support + recognition + 1)",
         "bound": f"support above {rec}, correlation at least {fr.min_corr}, and {round(100 * float(fr.min_consistency))}% "
                  "of checks consistent: a learned interaction goes to review",
         "after_review": f"rejected: the pair is blocked for {int(fr.reject_cooldown_days)} days"},
        {"id": "superentity", "name": "Superentity count", "memory": "long_term",
         "when": f"each day, as the day is distilled; a group at most once every {int(ab.evidence_spacing_days)} days",
         "how": "Interactions that were active together, explaining the same moves, are matched against the known "
                "groups; a match counts once for that group. Support decays with a half-life of "
                f"{int(ab.support_half_life_days)} days.",
         "reads": f"the activity log over {int(ab.window_days)} days",
         "updates": "the group's support, and the support of every kind along its generalization path",
         "bound": f"a candidate above {rec}: an admission goes to review; an admitted group below "
                  f"{ab.dissolve_below}: a dissolution goes to review", "after_review": ""},
        {"id": "kinds", "name": "Generalization statistics", "memory": "long_term",
         "when": "each article, as long-term memory registers it",
         "how": "Every item the article touched is classified down its taxonomy; each kind on the path adds the item's "
                "statistics.",
         "reads": "the classified items and their values or effects",
         "updates": "support and pooled statistics of every kind on the path; a crowded kind may split",
         "bound": f"a kind supplies priors once its support passes {int(cfg.thresholds.recall)}", "after_review": ""},
    ]


def _days(ctl: WorldModelController, d: int | None) -> str | None:
    if d is None:
        return None
    return ctl.engine.wm.deviations.day_start(int(d)).date().isoformat()


def checks_view(ctl: WorldModelController) -> dict:
    from axelrod_wm.control.stage import hedge_view

    eng = ctl.engine
    cfg = eng.config
    wm, ltm = eng.wm, eng.ltm
    g = wm.graph
    rec = int(cfg.thresholds.recognition)
    today = int(wm.last_processed_day)
    name = lambda sid: g.subentities[sid].name if sid in g.subentities else sid  # noqa: E731
    live: list[dict] = []
    bound = float(cfg.refinement.commit_posterior)
    for pid, pend in sorted(wm.pending_refinements.items()):
        v = hedge_view(pend, g)
        top = max((c for c in v["candidates"] if c["id"] != "__open__"), key=lambda c: c["p"], default=None)
        last = pend.checks[-1] if pend.checks else None
        live.append({"kind": "hedge", "id": pid, "label": v["label"], "status": pend.status,
                     "progress": [{"what": f"{top['name'] if top else 'top candidate'} probability",
                                   "value": top["p"] if top else 0.0, "bound": bound, "unit": "pct"},
                                  {"what": "articles", "value": float(pend.support), "bound": float(rec), "unit": "n"}],
                     "candidates": v["candidates"], "last": last.at.date().isoformat() if last else None,
                     "next": "any article that names a candidate, or moves a candidate's value"})
    spacing = int(cfg.frontier.evidence_spacing_days)
    for cid, co in sorted(ltm.correlation_frontier.entries.items()):
        if str(co.status) != "holding":
            continue
        n = co.consistent + co.inconsistent
        nxt = (co.last_verified_day + spacing) if co.last_verified_day is not None else today
        live.append({"kind": "frontier", "id": cid, "label": f"{name(co.earlier_id)} → {name(co.later_id)}",
                     "status": str(co.status),
                     "progress": [{"what": "support", "value": round(float(co.support), 2), "bound": float(rec) + 0.01,
                                   "unit": "n"},
                                  {"what": "consistent checks", "value": round(co.consistent / n, 3) if n else 0.0,
                                   "bound": float(cfg.frontier.min_consistency), "unit": "pct"},
                                  {"what": "correlation", "value": round(abs(co.corr.corr()), 3),
                                   "bound": float(cfg.frontier.min_corr), "unit": "r"}],
                     "passed": co.consistent, "failed": co.inconsistent, "last": _days(ctl, co.last_verified_day),
                     "next": f"from {_days(ctl, max(nxt, today))}, when {name(co.later_id)} moves unexplained"})
    ab_spacing = int(cfg.abduction.evidence_spacing_days)
    for pid, p in sorted(ltm.object_generalizations.patterns.items()):
        st = str(p.status)
        if st == "candidate":
            nxt = (p.last_counted_day + ab_spacing) if p.last_counted_day is not None else today
            live.append({"kind": "superentity", "id": pid, "label": p.name,
                         "status": "proposed" if p.proposed_at is not None else st,
                         "progress": [{"what": "support", "value": round(float(p.support), 2),
                                       "bound": float(rec) + 0.01, "unit": "n"}],
                         "last": _days(ctl, p.last_counted_day),
                         "next": f"from {_days(ctl, max(nxt, today))}, when its interactions fire together"})
        elif st == "admitted" and float(p.support) < 2 * float(cfg.abduction.dissolve_below):
            live.append({"kind": "superentity", "id": pid, "label": p.name, "status": "fading",
                         "progress": [{"what": "support (dissolution below)", "value": round(float(p.support), 2),
                                       "bound": float(cfg.abduction.dissolve_below), "unit": "n", "below": True}],
                         "last": _days(ctl, p.last_counted_day), "next": "each day, as support decays"})
    return {"catalog": catalog(cfg), "live": live, "today": _days(ctl, today)}
