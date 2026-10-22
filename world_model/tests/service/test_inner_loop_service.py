"""The inner-loop runner's clean-world operations against the real v1 service (the synthetic acme world): the same source
imported twice adds no second document and no second bundle."""

from __future__ import annotations

from axelrod_wm.evaluation import inner_loop as il
from tests.service.helpers import NOTE, service
from tests.unit.evaluation.test_inner_loop import recipes, suite


def test_a_repeated_import_adds_no_document_and_no_bundle() -> None:
    with service() as client:
        s = suite()
        rec = {"TST-02-06": {"op": "ingest_repeat", "ingest_repeat": {
            "name": "note.md", "document": {"const": NOTE.decode()}}}}
        r = il.run_suite(s, rec | {k: v for k, v in recipes(s).items() if k == "TST-01-01"}, only=["TST-02-06"],
                         services=lambda: il.V1Service(client, "acme_demo"))
    a = r["results"][0]["actual_result"]
    assert r["results"][0]["status"] == il.ANSWERED
    assert a["documents_after_first_import"] == a["documents_after_second_import"] == 1
    assert a["bundles_after_first_import"] == a["bundles_after_second_import"] == 1
    assert a["unique_economic_records"] is True and a["same_document_id"] is True
