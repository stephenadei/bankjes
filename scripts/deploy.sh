#!/usr/bin/env bash
# Idempotent deploy script. Invoked by GHA over SSH on the VPS, or runnable manually.
#
#   scripts/deploy.sh acc   → pulls :acc tag, restarts bankjes-acc
#   scripts/deploy.sh prd   → pulls :prd tag, restarts bankjes
#   scripts/deploy.sh pre   → pulls :pre tag, restarts bankjes-pre (one-phase-ahead preview)
#
# Expects to run from a checkout in /home/stephen/projects/bankjes-<env>/
# with .env.<env> present.

set -euo pipefail

ENV="${1:?usage: deploy.sh <acc|prd|pre>}"
case "$ENV" in
  acc|prd|pre) ;;
  *) echo "env must be acc, prd, or pre, got: $ENV" >&2; exit 2 ;;
esac

COMPOSE_FILE="docker-compose.${ENV}.yml"
ENV_FILE=".env.${ENV}"

[[ -f "$COMPOSE_FILE" ]] || { echo "missing $COMPOSE_FILE" >&2; exit 1; }
[[ -f "$ENV_FILE" ]]     || { echo "missing $ENV_FILE — copy from ${ENV_FILE}.example and fill" >&2; exit 1; }

echo "[deploy:$ENV] pulling latest image"
docker compose -f "$COMPOSE_FILE" pull

echo "[deploy:$ENV] (re)starting container"
docker compose -f "$COMPOSE_FILE" up -d

echo "[deploy:$ENV] pruning dangling images"
docker image prune -f >/dev/null

echo "[deploy:$ENV] container status"
docker compose -f "$COMPOSE_FILE" ps
