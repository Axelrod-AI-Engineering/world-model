"""An import that needs a person never blocks the next one (world_model/docs/design/unified-model.md): under the
`standards` policy a bulk import of bundles goes to the end, the items that need a person stay pending with the gate's
reasons visible on the change, and each is decided later (approve: applied on the model as it is then; reject: closed),
also after a restart. Under `review_all` the old rule stays: one run waits and the next import is refused."""

from __future__ import annotations

import threading
import time

from tests.service.helpers import WM, Signer, data, etag_now, problem, propose, service

SIGNER = Signer()


def item(iid: str, day: int, rate: float, **kw) -> dict:
    """A well-attributed item (the gate applies it); `kw` overrides or adds fields."""
    return {"id": iid, "published_at": f"2026-08-{day:02d}T09:00:00Z", "source": "Synthetic central bank",
            "source_type": "central_bank", "document": f"Statement {iid}", "coverage": "full", "plausible": True,
            "confidence": 0.8, "headline": f"The central bank sets its policy rate at {rate}%",
            "entities": ["central_bank"],
            "signals": [{"type": "observe", "value_of": "central_bank.policy_rate", "value": rate}], **kw}


def news(iid: str, day: int, rate: float) -> dict:
    """News without its publisher: the gate sends it to a person."""
    return item(iid, day, rate, source_type="news", source="Synthetic wire", basis="direct")


def bare(iid: str, day: int, rate: float) -> dict:
    """The same item without its attribution."""
    return {k: v for k, v in item(iid, day, rate).items() if k not in ("document", "coverage", "plausible")}


def post_bundle(c, *items: dict) -> str:
    body = {"format": "axelrod.import/v1", "title": f"Research {items[0]['id']}", "collected_by": "a test",
            "synthetic": True, "items": list(items)}
    return data(c.post(f"{WM}/bundles", json=body), 201)["id"]


def decide(c, change_id: str, approve: bool, **kw):
    h = {**SIGNER.bearer(), "If-Match": etag_now(c)}
    if approve:
        return c.post(f"{WM}/changes/{change_id}/approvals", json={"note": "checked"}, headers=h)
    return c.post(f"{WM}/changes/{change_id}/rejections", json={"reason": "not for the model"}, headers=h)


def changes(c, status: str = "pending") -> list[dict]:
    return data(c.get(f"{WM}/changes", params={"status": status, "limit": 200}))


def by_event(c, status: str) -> dict[str, dict]:
    return {x["event_id"]: x for x in changes(c, status)}


PLAN = [("A", item("A", 4, 0.5)), ("B", news("B", 5, 0.75)), ("C", item("C", 6, 1.0)), ("D", bare("D", 7, 1.25)),
        ("E", item("E", 8, 1.5)), ("F", news("F", 9, 1.75)), ("G", item("G", 10, 2.0))]


def test_a_bulk_import_goes_past_the_items_that_need_a_person_and_each_is_decided_later(tmp_path):
    with service(SIGNER, tmp_path, review=None) as c:
        for name, it in PLAN:                                   # in order, one bundle each: none is refused
            propose(c, post_bundle(c, it))
        pend = by_event(c, "pending")
        assert sorted(pend) == ["IM-B", "IM-D", "IM-F"]
        assert any("publisher" in r for r in pend["IM-B"]["review_reasons"])
        assert any("source document" in r for r in pend["IM-D"]["review_reasons"])
        assert any("coverage is not labelled" in r for r in pend["IM-D"]["review_reasons"])
        auto = by_event(c, "auto_applied")
        assert sorted(auto) == ["IM-A", "IM-C", "IM-E", "IM-G"]
        assert all(x["decided_by"]["sub"] == "policy:standards" and x["review_reasons"] == [] for x in auto.values())
        one = data(c.get(f"{WM}/changes/{pend['IM-B']['id']}"))
        assert one["review_reasons"] == pend["IM-B"]["review_reasons"]

        before = c.get(WM).headers["etag"]
        ok = data(decide(c, pend["IM-B"]["id"], True), 201)         # applied now, on the model as it is
        assert ok["status"] == "approved" and c.get(WM).headers["etag"] != before
        assert data(c.get(f"{WM}/changes/{pend['IM-B']['id']}"))["version_after"] > 0
        gone = data(decide(c, pend["IM-D"]["id"], False), 201)
        assert gone["status"] == "rejected"
        problem(decide(c, pend["IM-D"]["id"], True), 409, "already_decided")
        assert sorted(by_event(c, "pending")) == ["IM-F"]
        propose(c, post_bundle(c, item("H", 11, 2.25)))             # and the next import still goes through
        left = by_event(c, "pending")["IM-F"]["id"]

    with service(SIGNER, tmp_path, review=None) as c:               # a restart: still pending, and decidable
        assert [x["id"] for x in changes(c)] == [left]
        assert changes(c)[0]["review_reasons"]
        assert data(decide(c, left, True), 201)["status"] == "approved" and changes(c) == []
        assert sorted(by_event(c, "approved")) == ["IM-B", "IM-F"] and sorted(by_event(c, "rejected")) == ["IM-D"]


def test_a_pending_change_the_model_has_moved_past_is_refused_and_stays_pending(tmp_path):
    support = {"id": "S", "published_at": "2026-08-10T00:00:00Z", "source": "agent", "headline": "Spreads and a bank",
               "signals": [{"type": "support", "source": "dollar.index", "target": "acme_motors.operating_profit",
                            "strength": 0.6, "quote": "A stronger dollar trims Acme Motors"}]}
    with service(SIGNER, tmp_path, review=None) as c:
        propose(c, post_bundle(c, support))
        (change,) = changes(c)
        ctl = c.app.state.world_models["acme_demo"].st.controller
        op = ctl.proposals[change["id"]].event.ops[0]
        retire = ctl.propose_retire(interaction_id=op.interaction_id, reason="no longer true")
        ctl.approve(retire.id, "a person")                          # the link is gone
        body = problem(decide(c, change["id"], True), 409, "conflict")
        assert "no longer" in body["detail"]
        assert [x["id"] for x in changes(c)] == [change["id"]]      # nothing changed: it stays pending, and can be rejected
        assert data(decide(c, change["id"], False), 201)["status"] == "rejected"


def test_two_imports_at_once_take_turns_under_standards_and_are_refused_under_review_all(tmp_path):
    with service(SIGNER, tmp_path, review=None) as c:
        a, b = post_bundle(c, item("A", 4, 0.5)), post_bundle(c, item("B", 5, 0.75))
        claims = c.app.state.proposing
        claims.add("acme_demo")                                     # an import is in flight ...
        threading.Timer(0.3, claims.discard, ("acme_demo",)).start()       # ... and ends a moment later
        t0 = time.time()
        propose(c, a)                                               # this one waits its turn, and then runs
        assert time.time() - t0 >= 0.25
        propose(c, b)
    (tmp_path / "ra").mkdir()
    with service(SIGNER, tmp_path / "ra") as c:                     # review_all: the first leaves a run waiting
        propose(c, post_bundle(c, item("A", 4, 0.5)))
        problem(c.post(f"{WM}/changes", json={"bundle_id": post_bundle(c, item("B", 5, 0.75))}), 409,
                "update_in_progress")
        claims = c.app.state.proposing
        claims.add("acme_demo")
        try:
            problem(c.post(f"{WM}/changes", json={"bundle_id": post_bundle(c, item("C", 6, 1.0))}), 409,
                    "update_in_progress")
        finally:
            claims.discard("acme_demo")
