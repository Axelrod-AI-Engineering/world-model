"""The import bundle (axelrod_ingest/contract/bundle.py): the schema, and that the format is stable."""

import json

import pytest
from pydantic import ValidationError
from tests.where import IMPORT_BUNDLE_SAMPLE

from axelrod_ingest.contract.bundle import FORMAT, ImportBundle


def test_sample_bundle_parses():
    b = ImportBundle.model_validate(json.loads(IMPORT_BUNDLE_SAMPLE.read_text()))
    assert b.format == FORMAT == "axelrod.import/v1"
    assert [i.id for i in b.items] == ["T-002", "T-001", "T-003"]
    assert {type(s).__name__ for i in b.items for s in i.signals} == {"Observe", "Support", "Link"}


def test_unknown_signal_type_and_extra_fields_fail():
    with pytest.raises(ValidationError):
        ImportBundle.model_validate({"items": [{"id": "x", "published_at": "2026-09-01T00:00:00Z", "source": "s",
                                                "headline": "h", "signals": [{"type": "guess", "value_of": "a"}]}]})
    with pytest.raises(ValidationError):
        ImportBundle.model_validate({"items": [], "surprise": 1})
