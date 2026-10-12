#!/bin/sh
set -eu
mkdir -p /app/var
# WORLD_MODEL_SCENARIO picks the scenario the hosted demo opens on (default: the oil-shock demo); any scenario can
# still be loaded from Admin › Settings, for everyone at once.
exec axelrod demo --scenario "${WORLD_MODEL_SCENARIO:-oil_shock_demo}" --host 0.0.0.0 --port "${PORT:-8080}"
