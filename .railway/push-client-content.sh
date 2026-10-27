#!/bin/sh
# Copy client content onto the dev volume, after checking it (scripts/deploy/check_client_content.py): every YAML file
# decodes and parses, and the service boots on the folder with every scenario's login. Stops before copying on a failure.
# The copy leaves out a Mac's resource forks and .DS_Store files (`._*.yaml` took dev down on Oct 22). Redeploy afterwards.
#
#   .railway/push-client-content.sh [folder, default data/clients] [main scenario, default unified]
set -eu
root="${1:-data/clients}"
scenario="${2:-unified}"
uv run python -I scripts/deploy/check_client_content.py "$root" --scenario "$scenario"
COPYFILE_DISABLE=1 tar cz --exclude='._*' --exclude='.DS_Store' -C "$root" scenarios worlds configs docs \
  | npx -y -p node@22 -p @railway/cli@5.64.2 railway ssh -s world-model -e dev -- tar xz -C /app/var/clients
echo "copied; redeploy world-model to load it"
