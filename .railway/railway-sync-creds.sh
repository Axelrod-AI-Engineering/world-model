#!/usr/bin/env bash
# Push a stage's secrets from the gitignored .creds.<stage> to the world-model service on Railway (core's
# `make sync-<stage>-env` convention). Values go through stdin, are never printed, and no deploy is triggered.
# Usage: scripts/railway-sync-creds.sh [stage] [creds file]   (stage defaults to dev, the only hosted stage)
set -euo pipefail

STAGE="${1:-dev}"
CREDS="${2:-.creds.${STAGE}}"
SERVICE="${RAILWAY_SERVICE_NAME:-world-model}"
command -v railway >/dev/null || { echo "railway CLI is required" >&2; exit 1; }
[[ -f "${CREDS}" ]] || { echo "credential file not found: ${CREDS}" >&2; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

while IFS= read -r -d '' key && IFS= read -r -d '' value; do
  printf '%s' "${value}" | railway variables set --service "${SERVICE}" --environment "${STAGE}" --skip-deploys --set-from-stdin "${key}" >/dev/null
  echo "synced ${key} to ${SERVICE}/${STAGE}"
done < <(PYTHONPATH="${ROOT}/src" CREDS="${CREDS}" python3 -I -c '
import os, sys
from pathlib import Path
from axelrod_wm.settings import read_creds
for k, v in read_creds(Path(os.environ["CREDS"])).items():
    sys.stdout.write(k + "\0" + v + "\0")
')
