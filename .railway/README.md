# Railway dev deployment

This repo owns `service.world-model` and `volume.world-model-volume` through the
named `world-model` IaC partial in the shared Axelrod project. The configuration
refuses environments other than `dev`. Existing services and secrets remain
outside this partial. See [Railway multi-repo ownership](https://docs.railway.com/infrastructure-as-code#multi-repo-projects).

Following Axelrod/core: frozen Python dependencies, Dockerfile builds, one replica
in `us-west2`, durable storage, ON_FAILURE with two retries, App Sleep off,
plan-before-apply, and strict post-deployment drift and hosted health checks.
The demo needs a 600-second initial health timeout because it replays synthetic
history before startup completes. All demo sessions share one engine. Runtime
state, traces, and initialization caches persist under `/app/var` (5 GB volume).
No model-provider credentials or database are required for the synthetic demo.

## Toolchain and deployment

IaC SDK `railway@3.13.1` is pinned in package-lock.json. CLI `5.64.2` and Node 22
are pinned here because named partials and native TypeScript evaluation require
newer tooling than Core's CLI 5.33.0 / Node 20 pair.

```bash
npm ci
npx --yes -p node@22 -p @railway/cli@5.64.2 railway link \
  --project ee19a1df-2ce5-4193-932a-6139f034bbce --environment dev --service world-model
npx --yes -p node@22 -p @railway/cli@5.64.2 railway config plan
# Review: only resources owned by world-model may change; no destructive changes.
npx --yes -p node@22 -p @railway/cli@5.64.2 railway config apply --yes
npx --yes -p node@22 -p @railway/cli@5.64.2 railway up \
  --project ee19a1df-2ce5-4193-932a-6139f034bbce --environment dev --service world-model --detach
bash scripts/persist-railway-fields.sh
npx --yes -p node@22 -p @railway/cli@5.64.2 railway config plan --json > /tmp/world-model-drift.json
python3 scripts/verify-railway-drift.py /tmp/world-model-drift.json
```

Like Core, Railway currently leaves source.type after CLI uploads and does not
store restartPolicyType / sleepApplication in EnvironmentConfig. Deployment
metadata must independently confirm ON_FAILURE, retry limit 2, App Sleep false,
healthcheck /api/health, and the /app/var mount. The verifier admits only those
exact known leftovers. Do not apply the post-upload source.type leftover.

Verify the exact deployment is SUCCESS, then use Railway SSH to check
`http://127.0.0.1:8080/api/health`, `/`, and `/api/state`. Never report an upload
or a successful build alone as a healthy deployment.

## Shared-project integration

Railway requires every IaC repo targeting an environment with named partials to
export a partial. Core currently uses whole-project IaC. Before its next dev
IaC plan/apply, migrate Core to a stable named partial with a CLI supporting
partials and claim only its resources. This repository does not edit Core.
Core's older whole-project planner must not be applied against the expanded dev
environment: it can propose deleting services owned by other repositories.

## Basic Auth

The hosted demo requires `WORLD_MODEL_REQUIRE_BASIC_AUTH=1` and both
`WORLD_MODEL_BASIC_AUTH_USERNAME` / `WORLD_MODEL_BASIC_AUTH_PASSWORD`. Credentials
are generated securely and kept in Railway; IaC preserves them. A private,
gitignored operator copy is in `var/railway/dev-basic-auth.txt` (mode 0600).
Missing credentials prevent server startup when auth is required. Local use
without these variables remains unchanged.

All HTTP content and mutations, including static assets and API documentation,
and the WebSocket stream require Basic Auth. GET/HEAD `/api/health` is the sole
readiness exception. Browser credentials cached after the initial login also
authenticate the same-origin WebSocket handshake. Public access uses Railway
HTTPS. This remains a shared demo session, rather than separate per-user state.
