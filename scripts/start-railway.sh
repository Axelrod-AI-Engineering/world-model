#!/bin/sh
set -eu
mkdir -p /app/var
# WORLD_MODEL_SCENARIO picks the scenario the main login opens on (default: the oil-shock demo); WORLD_MODEL_LOGINS
# adds logins with scenarios of their own (api/auth.py). Admin › Settings can still load any scenario, for everyone
# on that login.
exec axelrod demo --scenario "${WORLD_MODEL_SCENARIO:-oil_shock_demo}" --host 0.0.0.0 --port "${PORT:-8080}"
