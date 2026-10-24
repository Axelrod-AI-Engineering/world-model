# Ingestion

Documents in, import bundles out. Ingestion parses a file, splits it into passages, finds the model's own names in
them, extracts signals with their exact quotes, and keeps everything in a data lakehouse that it searches by keyword,
prefix, meaning, and graph. It is the workspace member `ingestion/` (distribution `axelrod-ingest`, import
`axelrod_ingest`), and it does not import the world model.

<!-- toc -->
**Contents**

- [Pages](#pages)
- [The package](#the-package)
- [Running it](#running-it)
- [As services](#as-services)
<!-- /toc -->

## Pages

| I want to… | Go to |
|---|---|
| Follow a file from upload to bundle: the steps, the two times, typing, OCR, Chinese and Korean text, the yen sign, duplicates, packs, the rules, determinism | [pipeline.md](pipeline.md) |
| See how each stage is implemented: the method (rules, learned model, workflow), its parameters, its module, and why it repeats | [implementation.md](implementation.md) |
| Know where everything is kept, and how search works | [lake.md](lake.md) |
| Know what ingestion exchanges with the world model: the bundle format and the world view | [contract.md](contract.md) |
| Measure speed and extraction against a gold set | [bench.md](bench.md) |
| Pick up the work: what is built downstream (search), what is not (grounded answering), and the next steps in order | [next_steps.md](next_steps.md) |
| See how the whole repository fits together | [../../docs/architecture.md](../../docs/architecture.md) |

## The package

```text
ingestion/
  src/axelrod_ingest/
    __init__.py       EXTRACTOR_VERSION (import-light)
    contract/         bundle.py (axelrod.import/v1), world_view.py: standard library and pydantic only
    parse.py chunk.py tables.py     bytes to text, text to passages, table rows to cells
    encoding.py ocr.py              a file's charset; the text of a scanned page (tesseract, cached by content)
    cjk.py units.py                 Chinese, Japanese, and Korean text; currencies, scales, and the yen sign
    dates.py sources.py             published date and period; document type and the manifest reader
    dedupe.py                       one disclosure across language and basis
    gazetteer.py extract.py llm.py  recognition, rules-first extraction, the optional cached LLM step
    pipeline.py       the Ingestor: store, parse, type, index, recognize, extract, bundle
    service.py        the ingestion service (axelrod-ingest): the Ingestor behind HTTP, and /v1/embed
    ingest_client.py  RemoteIngestor and RemoteEmbedder: the world model's side of that service
    pack.py           a folder with a manifest into a lake, a report on each file, the determinism digest
    bench.py text.py  scoring, and how words are cut and compared
    lake/             store.py (the interface), sqlite.py, search.py, embed.py,
                      server.py (the data service, axelrod-lake), remote.py (RemoteLake, lake_from_env)
    testing.py        a pytest plugin: an isolated lake per test, the hashing embedder, no LLM step
  tests/              contract/ ingest/ lake/ test_boundary.py fixtures/
  scripts/            ingest_bench.py, ingest_pack.py
  docs/               this folder
```

## Running it

```bash
uv sync --frozen --package axelrod-ingest         # only this member: the world model is not installed
cd ingestion && uv run pytest                      # its own tests
cd ingestion && uv run pytest --cov                # coverage of its own source; CI requires 100% lines and branches
uv run python ingestion/scripts/ingest_pack.py <pack> --world-view <file> --lake-dir <dir>   # a pack into an isolated lake
```

The tests run with no client data and no model download: each gets a lake of its own, the exact `hashing` embedder,
and no LLM step. Every document and sentence in them is invented.

## As services

Two console scripts run the member as services (they need `--extra service`; the tests have it in the dev group). The base
package stays importable without FastAPI: only `lake/server.py` and `service.py` need it.

| Script | Entry point | Needs | Does |
|---|---|---|---|
| `axelrod-lake` | `axelrod_ingest.lake.server:main` | `LAKE_TOKEN`; `LAKE_DIR`, `PORT` | The lake behind HTTP: the only process that opens the SQLite file ([lake.md](lake.md#as-a-service)) |
| `axelrod-ingest` | `axelrod_ingest.service:main` | `INGEST_TOKEN`; `WORLD_MODEL_LAKE_URL` and `_TOKEN` (else a local lake), `PORT` | `POST /v1/ingest` (files and a world view), `POST /v1/process`, `POST /v1/embed`, `GET /health`. Stateless: it writes no file bytes to disk, keeps its OCR cache in temporary storage, and is the only embedder |

The world model reaches them with `RemoteIngestor` (`ingest_client.py`), whose `embedder` is a `RemoteEmbedder`, and
`RemoteLake` (`lake/remote.py`). Results are equal to the in-process path's: the same bundle ids and the same lake digest
(`pack.lake_digest`). Images are `ingestion/Dockerfile` (with tesseract and the embedding model) and `ingestion/Dockerfile.lake`
(neither); see [deployment.md](../../docs/deployment.md#three-services).
