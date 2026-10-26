"""A better read lets a pending change pass (world_model/docs/design/unified-model.md): a bundle read again from the same
document has the same item ids, and proposing it assesses the changes still waiting for a person on the new attribution.
One that now passes is applied by `policy:standards` and named in the answer's `regated_change_ids`; one that still fails
keeps waiting with its reasons updated; a change a person decided is not touched. All of it survives a restart."""

from __future__ import annotations

from tests.service.helpers import WM, data, etag_now, propose, service
from tests.service.test_v1_nonblocking_imports import (
    SIGNER,
    bare,
    by_event,
    changes,
    decide,
    item,
    post_bundle,
)


def test_a_re_read_applies_the_pending_change_it_now_passes_and_leaves_the_rest(tmp_path):
    with service(SIGNER, tmp_path, review=None) as c:
        for it in (bare("A", 4, 0.5), bare("B", 5, 0.75), bare("C", 6, 1.0)):
            propose(c, post_bundle(c, it))
        pend = by_event(c, "pending")
        assert sorted(pend) == ["IM-A", "IM-B", "IM-C"]
        assert data(decide(c, pend["IM-C"]["id"], False), 201)["status"] == "rejected"

        job = propose(c, post_bundle(c, item("A", 4, 0.5), item("B", 5, 0.75, plausible=False), item("C", 6, 1.0)))
        detail = job["result"]["detail"]
        assert sorted(detail["regated_change_ids"]) == sorted([pend["IM-A"]["id"], pend["IM-B"]["id"]])
        assert detail["imported_item_ids"] == [] and job["result"]["ids"] == []

        auto = by_event(c, "auto_applied")
        assert sorted(auto) == ["IM-A"] and auto["IM-A"]["decided_by"]["sub"] == "policy:standards"
        assert auto["IM-A"]["review_reasons"] == []
        (left,) = changes(c)
        assert left["event_id"] == "IM-B" and any("plausibility" in r for r in left["review_reasons"])
        assert not any("source document" in r for r in left["review_reasons"])
        assert sorted(by_event(c, "rejected")) == ["IM-C"]
        etag = etag_now(c)

        again = propose(c, post_bundle(c, item("A", 4, 0.5), item("B", 5, 0.75, plausible=False)))
        assert again["result"]["detail"]["regated_change_ids"] == []     # nothing new, and nothing to assess: not an error
        assert etag_now(c) == etag

    with service(SIGNER, tmp_path, review=None) as c:                   # a restart: the same state
        assert sorted(by_event(c, "auto_applied")) == ["IM-A"]
        (left,) = changes(c)
        assert left["event_id"] == "IM-B" and any("plausibility" in r for r in left["review_reasons"])
        assert data(c.get(f"{WM}/changes/{left['id']}"))["status"] == "pending"
