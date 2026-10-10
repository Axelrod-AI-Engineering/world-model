#!/bin/sh
set -eu
mkdir -p /app/var
exec axelrod demo --host 0.0.0.0 --port "${PORT:-8080}"
