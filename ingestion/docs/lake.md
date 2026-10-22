# The lakehouse and search

Where everything ingestion reads and produces is kept, and how it is searched. The steps that fill it are in
[pipeline.md](pipeline.md); the service routes over it are in [the API reference](../../world_model/docs/api/README.md).

<!-- toc -->
**Contents**

- [The lakehouse](#the-lakehouse)
- [Search](#search)
<!-- /toc -->

## The lakehouse

`WORLD_MODEL_LAKE_DIR` (default `var/lake`; on Railway, the volume) holds:

```
lake.sqlite3                SQLite (WAL): the catalog and the indexes
<org>/raw/<doc-id>.<ext>    the files as uploaded
```

| Table | Holds |
|---|---|
| `documents` | One row per file per organization: hash, name, type, source, the two times, status, and parse metadata |
| `texts` | The extracted text and the parser that produced it |
| `chunks`, `chunks_fts`, `chunks_prefix` | Chunks with their offsets and pages; the stemmed and unstemmed full-text indexes |
| `mentions` | Which entity and value each chunk names |
| `embeddings` | One float32 vector per chunk, with the embedder's name |
| `bundles` | Each bundle, whole, with its source documents and extractor version |
| `imports` | Each import of a bundle: when, by whom, the graph update it started, and which items |
| `llm_cache` | LLM answers by digest |

Organizations are tenants: a credential sees only its organization's documents. Storage sits behind an interface (`ingestion/src/axelrod_ingest/lake/store.py`,
`LakeStore`), so a warehouse such as Postgres, or Parquet on object storage, can replace SQLite without changing the
pipeline or the API.

## Search

Search runs over what has been ingested and over the model's own names. It has five modes: keyword (BM25), prefix,
semantic, graph (the nodes named and their neighbours, then the chunks that mention them), and hybrid
(reciprocal-rank fusion of keyword, semantic, and graph). This is the retrieval layer for the agents' RAG: each hit
gives its document, chunk, and text, and says why it matched. See [the API reference](../../world_model/docs/api/README.md#search).

