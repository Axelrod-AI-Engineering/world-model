"""I5. Export and re-import: a bundle read out of one service (`GET .../bundles/{id}` and its items) and posted whole
into a fresh one (`POST .../bundles`) gives the same model as the original, once the same changes are approved: version
for version and hash for hash; the v4.1.4 export of the two models is the same file."""

from __future__ import annotations

import pytest

from tests.integration.service.conftest import (
    RATES_NOTE,
    SIGNER,
    WM,
    attribute,
    propose,
    review_all,
    upload,
    version,
)
from tests.service.helpers import data, service

pytestmark = pytest.mark.integration


def test_an_exported_bundle_reimported_elsewhere_gives_the_same_model():
    with service(SIGNER) as first:
        res = upload(first, RATES_NOTE, "2026-09-01_data.txt", source="Data desk")
        summary = data(first.get(f"{WM}/bundles/{res['bundle_id']}"))
        items = data(first.get(f"{WM}/bundles/{res['bundle_id']}/items", params={"limit": 200}))
        exported = {"format": "axelrod.import/v1", "title": summary["title"], "items": items}
        a = propose(first, res["bundle_id"])["result"]["detail"]
        decided_a = review_all(first)
        at_a, crude_a = version(first), attribute(first, "crude_oil", "price")["data"]
        pack_a = data(first.get(f"{WM}/exports/v4.1.4"))

    with service(SIGNER) as second:
        posted = data(second.post(f"{WM}/bundles", json=exported), 201)
        assert posted["item_count"] == len(items) and posted["signal_count"] == summary["signal_count"]
        doc = data(second.get(f"{WM}/documents/{posted['document_ids'][0]}"))
        assert doc["meta"]["format"] == "bundle"
        b = propose(second, posted["id"])["result"]["detail"]
        decided_b = review_all(second)
        assert b["imported_item_ids"] == a["imported_item_ids"] and len(decided_b) == len(decided_a)
        at_b = version(second)
        assert (at_b["number"], at_b["state_hash"]) == (at_a["number"], at_a["state_hash"])
        assert attribute(second, "crude_oil", "price")["data"] == crude_a
        pack_b = data(second.get(f"{WM}/exports/v4.1.4"))
        assert pack_b["domain_pack"] == pack_a["domain_pack"] and pack_b["registry_entry"] == pack_a["registry_entry"]
