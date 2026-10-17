"""The lakehouse's records (Oct 17): content-derived ids and digests are deterministic, canonical JSON ignores key
order, and records are frozen."""

from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from axelrod_wm.lake.store import DEFAULT_TENANT, Hit, Mention, canonical_json, content_id, digest
from tests.lake.conftest import make_doc


def test_content_id_is_the_sha256_prefix_and_stable():
    data = b"Toyota raised its forecast."
    assert content_id(data) == content_id(data) == hashlib.sha256(data).hexdigest()[:24]
    assert len(content_id(data)) == 24
    assert content_id(data) != content_id(data + b" ")


def test_canonical_json_ignores_key_order_and_whitespace():
    a = {"b": 1, "a": {"y": [1, 2], "x": "é"}}
    b = {"a": {"x": "é", "y": [1, 2]}, "b": 1}
    assert canonical_json(a) == canonical_json(b) == '{"a":{"x":"é","y":[1,2]},"b":1}'


def test_canonical_json_serializes_unknown_types_as_strings():
    assert canonical_json({"t": make_doc(b"x").event_time}) == '{"t":"2026-03-01 00:00:00+00:00"}'


def test_digest_is_the_sha256_of_canonical_json():
    a, b = {"x": 1, "y": 2}, {"y": 2, "x": 1}
    assert digest(a) == digest(b) == hashlib.sha256(canonical_json(a).encode()).hexdigest()
    assert digest(a) != digest({"x": 1, "y": 3})


def test_records_are_frozen_and_forbid_extra_fields():
    doc = make_doc(b"x")
    with pytest.raises(ValidationError):
        doc.title = "changed"
    with pytest.raises(ValidationError):
        Mention(tenant="t", doc_id="d", ord=0, entity_id="e", surface="E", extra=1)


def test_record_defaults():
    doc = make_doc(b"x")
    assert (doc.status, doc.source_type, doc.meta, doc.published_at) == ("stored", "other", {}, None)
    hit = Hit(kind="entity", score=1.0, text="Toyota")
    assert (hit.doc_id, hit.why, hit.event_time) == (None, [], None)
    assert DEFAULT_TENANT == "default"
