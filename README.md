# Axelrod World Model

The **Axelrod World Model**, v0. It is one causal world model of the economy, built like version control:

- **Backend users** teach it (the Learn view). Each event's learning runs on a staged copy, first working memory and then long-term memory. A person checks everything it would commit, down to the second- and third-order ripple. They keep what makes sense, and only that is committed.
- **Everyone else** only asks it (the Predict view). A thesis runs on a branch of a committed version that is never merged.

![The flowchart: learning and prediction](docs/flowchart.svg)

The repository has two parts:

- **`axelrod_wm`**, a Python package. It holds a causal graph of actors in an environment of actors:
  - **entities**: companies, agencies, and the economic ideas they act in;
  - **subentities**: each entity's values;
  - **interactions**: causal relations with uncertain effects and timing;
  - **superentities**: schemas such as sectors, rivalries, and shocks.
- **A browser demo** in `web/`. It runs locally, and a shared copy is hosted on Railway (see [Hosted demo](#hosted-demo)).

**All news, data, and numbers are synthetic.** Real company and agency names make the graph concrete. No headline reports a real event, and nothing in it is a claim about any company. The Fed chair is a role, not a person.

## Quick start

You need [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`). It installs Python 3.12, as pinned in `.python-version`.

```bash
uv sync
uv run axelrod small_demo          # a blank canvas, built one example at a time: http://127.0.0.1:8765
uv run axelrod prod_demo ripple    # the same examples in the oil-shock world
uv run axelrod demo --port 8765    # the full scripted oil-shock demo (the one the hosted demo runs)
uv run pytest                      # the tests
```

The production and full demos replay three years of synthetic history the first time they start (about two and a half minutes) and cache it in `var/`. Later starts take seconds.

## Hosted demo

The full demo runs on Railway's `dev` environment at **https://world-model-dev.up.railway.app**, behind Basic Auth. Ask the team for the credentials. Everyone who opens it shares one session, so a review approved there is approved for everyone. [docs/deployment.md](docs/deployment.md) covers the infrastructure, the release runbook, and the checks.

## Documentation

| Read | For |
|---|---|
| [docs/design/README.md](docs/design/README.md) | **The design**: the architecture, 17 modules with specs, diagrams, the cognitive framings, Cognee vs Semantica, decisions, and the migration plan |
| [docs/demos.md](docs/demos.md) | The four demos, the 24 examples, and how the review works |
| [docs/interface.md](docs/interface.md) | A tour of the interface: the top bar, the canvas, the panels, and every shortcut |
| [docs/cli.md](docs/cli.md) | The command line and configuration |
| [docs/ml-stack.md](docs/ml-stack.md) | The ML stack as built, stated formally, with its adversarial review |
| [docs/ml-roadmap.md](docs/ml-roadmap.md) | The plan to replace each heuristic with a method we can defend |
| [docs/deployment.md](docs/deployment.md) | The Railway dev deployment, sign-in, and running the container locally |
| [docs/development.md](docs/development.md) | Tests, the repository layout, conventions, and the demo videos |
| [docs/archive/plan.md](docs/archive/plan.md) | The original specification (historical), which the code's § references point to |

Inside the demo, **How it works** (`H`) explains the model itself: the five stages of learning and the six of inference, each with its flowchart; the literature review; and the implementation.

Videos (a two-minute devlog, a one-minute tour of learning, and the external trailer of Emily's demo) are kept out of the repository: ask the team for them. Locally they go in `docs/media/`, which is gitignored, and [scripts/video](scripts/video/README.md) records and cuts them.
