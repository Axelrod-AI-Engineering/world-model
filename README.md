# Axelrod

[![Tests](https://github.com/Axelrod-AI-Engineering/world-model/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/Axelrod-AI-Engineering/world-model/actions/workflows/tests.yml)

<!-- toc -->
<!-- /toc -->

One causal world model of the economy, built like version control, and the machinery that keeps it current: documents in, reviewed changes, what-if answers out. A uv workspace of two members:

| Member | Is | Docs |
|---|---|---|
| [`ingestion/`](ingestion/) | `axelrod-ingest`: parse, extract, and search documents; the lakehouse | [ingestion/docs](ingestion/docs/README.md) |
| [`world_model/`](world_model/) | `axelrod-world-model`: the causal graph, learning, inference, the demo, and the API | [world_model/docs](world_model/docs/README.md) |

**All news, data, and numbers are synthetic.** Real company and agency names make the graph concrete. No headline reports a real event, and nothing in it is a claim about any company.

## Start here

```bash
uv sync
uv run axelrod small_demo          # a blank canvas, built one example at a time: http://127.0.0.1:8765
uv run axelrod demo --port 8765    # the full scripted oil-shock demo (the one the hosted demo runs)
```

You need [uv](https://docs.astral.sh/uv/). Then read [docs/README.md](docs/README.md), the front door: [the architecture](docs/architecture.md), [the reading order](docs/reading-order.md), [the decisions](docs/decisions.md), [the ML stack](docs/ml-stack.md), [development](docs/development.md) (tests, coverage, CI), and [deployment](docs/deployment.md).

The full demo is hosted on Railway's `dev` environment at https://world-model-dev.up.railway.app, behind a sign-in page; ask the team for the credentials.
