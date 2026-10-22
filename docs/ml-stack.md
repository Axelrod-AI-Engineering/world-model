# The ML stack on one page

Every model and update the system runs, in the order a document travels, with where it lives and where its math is.
This is the map; the math as built (including what is wrong with it) is
[world_model/docs/ml/stack.md](../world_model/docs/ml/stack.md), and the plan to replace each heuristic is
[roadmap.md](../world_model/docs/ml/roadmap.md). Everything runs on synthetic data: no number here has been fit to, or
validated on, real market data.

<!-- toc -->
**Contents**

- [Ingestion: from a document to signals](#ingestion-from-a-document-to-signals)
- [The world model: reading, learning, asking](#the-world-model-reading-learning-asking)
- [What is planned](#what-is-planned)
<!-- /toc -->

## Ingestion: from a document to signals

Small and deterministic first; a language model only where the rules are silent, and off by default. Detail:
[pipeline.md](../ingestion/docs/pipeline.md), [lake.md](../ingestion/docs/lake.md).

| Step | Model or update | Where |
|---|---|---|
| Parse | PDFium for PDF, the XML of DOCX and PPTX, openpyxl values for XLSX; no OCR | `ingestion/src/axelrod_ingest/parse.py` |
| Chunk | Sentence splitting aware of abbreviations, bullets, and decimals; chunks of up to 700 characters that never cross a paragraph or page | `chunk.py` |
| Recognize | A gazetteer over the model's own names (a trie of word tokens, longest match first, slots resolved to the nearest owner), built from the world view | `gazetteer.py` |
| Extract | **Rules first**: sentence patterns for levels, moves, directions, causal claims, with exact quotes, and rules against forecasts, history, other actors' figures, and wrong periods | `extract.py`, `tables.py` |
| Extract, optional | **A cached LLM step** on chunks that name values where the rules found nothing: the same signal schema, every answer checked (ids exist, the quote appears verbatim), confidence 0.5, replayed from a cache keyed by content so a re-run is byte-identical | `llm.py` |
| Embed | A hashing embedder (exact, no model; the tests and the fallback), or bge-small (BAAI/bge-small-en-v1.5, 384 dimensions, ONNX on CPU) through fastembed | `lake/embed.py` |
| Search | BM25 over a stemmed full-text index, an unstemmed prefix index, cosine over embeddings, graph expansion from the names a query holds, and **reciprocal-rank fusion** (k = 60) of keyword, semantic, and graph for the hybrid mode | `lake/search.py`, `lake/sqlite.py` |
| Measure | Recall against a gold set with dev and test splits, precision from labels, speed per stage | `bench.py`, [bench.md](../ingestion/docs/bench.md) |

## The world model: reading, learning, asking

Paths are under `world_model/src/axelrod_wm/`. Section numbers are those of [stack.md](../world_model/docs/ml/stack.md).

| Part | Model or update | Where | Math |
|---|---|---|---|
| Intake | Translators: reviewed fixtures, regex templates at confidence 0.6, an imported bundle's own signals; the LLM translator is a stub | `intake/` | [§5](../world_model/docs/ml/stack.md#5-intake-from-article-to-operations) |
| Resolution | `alias_fuzzy` (sequence ratio, word overlap, constraints); a mention binds only when named, otherwise it is hedged over up to four candidates | `intake/resolver.py`, `intake/refiner.py` | [§5](../world_model/docs/ml/stack.md#5-intake-from-article-to-operations) |
| An interaction | Existence (a Beta), effect (a Gaussian), and a delay, lag, and duration kernel (Gamma) | `model/` | [§2](../world_model/docs/ml/stack.md#2-an-interaction) |
| Working memory | A local-level state-space model per value; a daily Kalman filter over its effects | `dynamics/daily.py` | [§3](../world_model/docs/ml/stack.md#3-the-state-space-model-of-working-memory) |
| Learn from one reviewed event | A joint Kalman update (the fold); existence by a likelihood-ratio pseudo-count; kernels by a three-point grid with a likelihood gate; level noise from entity memory | `learning/` | [§4](../world_model/docs/ml/stack.md#4-learning-in-working-memory-one-vetted-event) |
| Long-term memory | Taxonomies by signature descent (Cobweb is planned); the correlation frontier, a residual co-movement test; superentities by co-activation induction; recall by overlap attention | `memory/`, `learning/`, `shared/recall.py` | [§8](../world_model/docs/ml/stack.md#8-learning-in-long-term-memory) |
| Propagation | A Monte Carlo impulse model over the active channels | `dynamics/propagation.py` | [§6](../world_model/docs/ml/stack.md#6-propagation-the-monte-carlo-impulse-model-dynamicspropagationpy219-464) |
| Transmission | Orders and paths of a shock, and the reviewers' ripple judgments | `inference/transmission.py` | [§7](../world_model/docs/ml/stack.md#7-transmission-orders-and-ripple-judgments-inferencetransmissionpy53-114) |
| Inference | Isolate the networks a shock reaches, predict each, weigh rival scenarios (prior, fit, track record), couple, unify; hypotheses ranked by a value-of-information proxy | `inference/` | [§9](../world_model/docs/ml/stack.md#9-inference-answering-a-what-if-inferencetaskpy95-192) |
| Evaluation | Omission, commission, interval coverage, and CRPS against what the synthetic world then did; circular today | `evaluation/` | [§10](../world_model/docs/ml/stack.md#10-evaluation-evaluation) |

## What is planned

[Small models first](../world_model/docs/ml/stack.md#small-models-first): rules, then classical models, small
embedders, small finetuned classifiers, decision models, and a large language model last, each rung behind a slot and
audited for calibration. [Fine-tuning to own the structure](../world_model/docs/ml/stack.md#14-fine-tuning-to-own-the-structure)
(§14) is the data and the models that would follow. The review of what is unsound today is
[§13](../world_model/docs/ml/stack.md#13-adversarial-review).
