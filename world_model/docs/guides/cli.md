# The command line and configuration

Every command runs through uv: `uv run axelrod <command>`. `uv run axelrod --help` lists them all, and `--help` after a command lists its options.

<!-- toc -->
**Contents**

- [Demos](#demos)
- [The model without the browser](#the-model-without-the-browser)
- [Configuration](#configuration)
- [Environment variables](#environment-variables)
<!-- /toc -->

## Demos

```bash
uv run axelrod small_demo [example]    # the small demo at http://127.0.0.1:8765; --list, --headless, --port, --host
uv run axelrod prod_demo [example]     # the production demo, with the same options
uv run axelrod demo                    # the full oil-shock demo at http://127.0.0.1:8000; --scenario, --port, --host
```

[demos.md](demos.md) describes each one.

## The model without the browser

```bash
uv run axelrod flows --svg docs/flowchart.svg              # learning's and inference's stages and their flowcharts, as text; the overview (learning, inference, architecture) as a picture
uv run axelrod contracts                                   # every component's inputs, outputs, and writes
uv run axelrod init oil_shock_demo                         # build the init snapshot and start a session in var/axelrod
uv run axelrod update --until 2026-02-02 --auto-approve    # fold news and data through Feb 2 into that session
uv run axelrod log --limit 20                              # the session's commits, newest first
uv run axelrod show <version>                              # one commit
uv run axelrod diff <from> [<to>]                          # what changed between two versions
uv run axelrod run-scenario oil_shock_demo --headless --auto-approve   # all 18 steps and the 17-item checklist
uv run axelrod thesis ...                                  # pose a question as a thesis and print the forecast
uv run axelrod evaluate ...                                # freeze at a past date, pose what later happened, and score
uv run axelrod export-trace ...                            # copy a recorded trace to a file
```

`--help` after `thesis`, `evaluate`, or `export-trace` gives their arguments.

## Configuration

- `configs/default.yaml` picks one component per slot. To swap one in, copy the file, edit `components:`, and pass `--config`.
- `configs/demo.yaml` and `configs/small_demo.yaml` hold each scenario's overrides. Both demos review every change (`review_all`).
- `world_model/examples/worlds/<world>/` holds a world's construction files. `world_model/taxonomy/objects.yaml` gives each firm concept (Airline, Chipmaker, …) its default values and links.
- `world_model/examples/scenarios/<scenario>/` holds a script, seeds, a layout, market events and their reviewed translations, and the synthetic world's truth. The small demo is a blank canvas (`canvas: blank`). The production demo builds on `oil_shock_demo` (`base:`).

## Environment variables

| Variable | Effect |
|---|---|
| `WORLD_MODEL_BASIC_AUTH_USERNAME`, `WORLD_MODEL_BASIC_AUTH_PASSWORD` | The main login. When both are set, every page, API call, and WebSocket requires signing in (the variables keep their old name). Setting only one stops the server from starting. |
| `WORLD_MODEL_REQUIRE_BASIC_AUTH=1` | Refuse to start without both credentials. On Railway this is automatic. |

Without these variables, the local demos need no login. [deployment.md](deployment.md#sign-in) covers the hosted setup and the other logins (`WORLD_MODEL_LOGINS`); the API's variables (keys, trusted issuers, the lakehouse, the embedder, the LLM step) are in [the API reference](../api/README.md#configuration).
