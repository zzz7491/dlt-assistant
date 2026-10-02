#!/usr/bin/env bash
# DLT production deployment wrapper with Cloudflare Account Guard (fail-closed).
#
# Usage:
#   scripts/deploy_production.sh            # live wrangler whoami check + deploy
#   scripts/deploy_production.sh --offline  # check from local .wrangler cache
#   scripts/deploy_production.sh --ci       # check from CLOUDFLARE_ACCOUNT_ID env
#
# The guard runs BEFORE `wrangler pages deploy`.  If the active Cloudflare
# account is not the DLT production account, deployment is refused (exit 1).
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"
WRANGLER_ARGS=""
GUARD_FLAGS=""

# Parse local flags
while [[ $# -gt 0 ]]; do
  case "$1" in
    --offline) GUARD_FLAGS="--offline"; shift ;;
    --ci)      GUARD_FLAGS="--ci"; shift ;;
    -h|--help)
      echo "Usage: scripts/deploy_production.sh [--offline|--ci]"
      exit 0 ;;
    *)
      echo "Unknown option: $1 (passed to wrangler)"
      WRANGLER_ARGS="$WRANGLER_ARGS $1"
      shift ;;
  esac
done

echo "═══ DLT CLOUDFLARE DEPLOYMENT GUARD ═══"

# STEP 1: run the account guard (fail-closed)
if ! $PYTHON scripts/check_cloudflare_account.py $GUARD_FLAGS; then
  echo "Deployment aborted: Cloudflare account guard failed."
  exit 1
fi

echo "✓ Account guard passed. Proceeding with deployment."

# STEP 2: deploy via wrangler (npx in CI, local binary if available)
if command -v wrangler >/dev/null 2>&1; then
  echo "Running: wrangler pages deploy public $WRANGLER_ARGS"
  exec wrangler pages deploy public --project-name dlt-assistant --branch master --commit-dirty=true $WRANGLER_ARGS
elif command -v npx >/dev/null 2>&1; then
  echo "Running: npx --yes wrangler@latest pages deploy public $WRANGLER_ARGS"
  exec npx --yes wrangler@latest pages deploy public --project-name dlt-assistant --branch master --commit-dirty=true $WRANGLER_ARGS
else
  echo "ERROR: neither 'wrangler' nor 'npx' found in PATH."
  echo "Install node/npx or run wrangler manually after verifying the account."
  exit 1
fi
