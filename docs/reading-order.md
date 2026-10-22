# Reading order

What to read first, and in what order, by what you are here to do. About an hour for the first list.

<!-- toc -->
**Contents**

- [Everyone](#everyone)
- [By what you are doing](#by-what-you-are-doing)
<!-- /toc -->

## Everyone

1. [README.md](README.md): the map.
2. [architecture.md](architecture.md): the two members, their contract, and the conventions. Ten minutes.
3. [../world_model/docs/design/README.md](../world_model/docs/design/README.md): what the world model is for, its principles, and the system at a glance.
4. [../world_model/docs/guides/demos.md](../world_model/docs/guides/demos.md): run `uv run axelrod small_demo` and follow the examples.
5. [../world_model/docs/vocab.md](../world_model/docs/vocab.md): the terms. Every page uses them; none renames them.

## By what you are doing

| You are… | Then read |
|---|---|
| Working on ingestion | [../ingestion/docs/README.md](../ingestion/docs/README.md), then [pipeline](../ingestion/docs/pipeline.md), [lake](../ingestion/docs/lake.md), [contract](../ingestion/docs/contract.md), [bench](../ingestion/docs/bench.md) |
| Working on the world model | [../world_model/docs/design/modules/README.md](../world_model/docs/design/modules/README.md) (each module's spec), [data-model.md](../world_model/docs/design/data-model.md), [interfaces.md](../world_model/docs/design/interfaces.md) |
| Calling the API or MCP | [../world_model/docs/api/README.md](../world_model/docs/api/README.md), then [design/api.md](../world_model/docs/design/api.md) for why, and [core-mcp-auth.md](../world_model/docs/design/core-mcp-auth.md) for who is calling |
| Reading the math | [ml-stack.md](ml-stack.md) (one page), then [../world_model/docs/ml/stack.md](../world_model/docs/ml/stack.md) (the math as built) and [roadmap.md](../world_model/docs/ml/roadmap.md) (what replaces it) |
| Building a company's construction | [../world_model/docs/construction/README.md](../world_model/docs/construction/README.md), then [specificity.md](../world_model/docs/design/specificity.md) |
| Releasing or operating | [deployment.md](deployment.md), then [development.md](development.md#continuous-integration) |
| Writing code or tests | [development.md](development.md), then [../world_model/tests/README.md](../world_model/tests/README.md) |
| Asking why | [decisions.md](decisions.md) |
