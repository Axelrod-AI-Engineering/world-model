"""Ingestion (Oct 17): from a file someone uploads to the graph updates the world model reviews.

    file ──parse──▶ text ──chunk──▶ chunks ──recognize──▶ mentions ──extract──▶ signals ──▶ import bundle
     │                                  │                                                     │
     └─ lakehouse (raw, by hash)        └─ keyword / semantic indexes                         └─ the model's Import

Every step is deterministic: the same bytes and the same world model give byte-identical text, chunks, mentions, and
bundles (ingestion/tests/ingest/test_determinism.py). An optional LLM step proposes what the rules miss, through a replay cache
keyed by content, so a re-run reproduces it exactly; it is off unless a provider key is set.
"""

EXTRACTOR_VERSION = "ingest-1.2"
