#!/usr/bin/env bash
# WPI-I01R1 — disposable disabled-mode Temporal provider inertness plan proof.
# NON_PRODUCTION / SOURCE-CONFORMANCE ONLY.
# Uses an isolated fixture without backend.tf — no production remote state.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FIXTURE="${ROOT}/scripts/temporal/fixtures/disabled-provider-plan"
PROD_LOCK="${ROOT}/environments/production/.terraform.lock.hcl"

fail() { echo "DISABLED_PROVIDER_PLAN_FAIL: $*" >&2; exit 1; }
ok() { echo "DISABLED_PROVIDER_PLAN_OK: $*"; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

require_cmd tofu
require_cmd mktemp

WORKDIR=""
cleanup() {
  if [[ -n "$WORKDIR" && -d "$WORKDIR" ]]; then
    rm -rf "$WORKDIR"
  fi
}
trap cleanup EXIT

# Prove no Temporal credential channel is present
if [[ -n "${TEMPORAL_CLOUD_API_KEY:-}" ]]; then
  fail "TEMPORAL_CLOUD_API_KEY must be absent for disabled-mode proof"
fi
if [[ -n "${DIGITALOCEAN_TOKEN:-}" ]]; then
  fail "DIGITALOCEAN_TOKEN must be absent for disabled-mode proof"
fi

tofu version | grep -Fq 'OpenTofu v1.12.5' \
  || fail "expected OpenTofu 1.12.5"

[[ -f "$PROD_LOCK" ]] || fail "missing production lockfile: $PROD_LOCK"

WORKDIR="$(mktemp -d)"
cp "$FIXTURE/main.tf" "$FIXTURE/providers.tf" "$FIXTURE/variables.tf" "$WORKDIR/"
cp "$PROD_LOCK" "$WORKDIR/.terraform.lock.hcl"

# Resolve module source to repository-absolute path (temp dir is outside the tree).
module_src="${ROOT}/modules/temporal_cloud_workflow_plane"
if [[ "$(uname -s)" == MINGW* || "$(uname -s)" == MSYS* ]]; then
  module_src="$(cd "$module_src" && pwd -W | sed 's|\\|/|g')"
fi
sed "s|../../../../modules/temporal_cloud_workflow_plane|${module_src}|g" \
  "$FIXTURE/main.tf" >"$WORKDIR/main.tf"

cd "$WORKDIR"
tofu init -backend=false -input=false -reconfigure >/dev/null

lock_ver="$(grep -E 'version[[:space:]]*=[[:space:]]*"1\.7\.0"' .terraform.lock.hcl | head -1 || true)"
[[ -n "$lock_ver" ]] || fail "lockfile must pin temporalio/temporalcloud 1.7.0"

plan_out="$(mktemp)"
trap 'rm -f "$plan_out"; cleanup' EXIT

set +e
tofu plan -input=false -refresh=false >"$plan_out" 2>&1
plan_status=$?
set -e
[[ "$plan_status" -eq 0 ]] || {
  echo "--- plan output ---" >&2
  cat "$plan_out" >&2
  fail "disabled-mode plan must succeed without credentials (exit ${plan_status})"
}

if ! grep -Eiq 'No changes\.|Your infrastructure matches the configuration\.' "$plan_out"; then
  echo "--- plan output ---" >&2
  cat "$plan_out" >&2
  fail "expected successful no-op plan in disabled mode"
fi

if grep -Eiq 'temporalcloud_|module\.temporal_cloud_workflow_plane|temporal_cloud_workflow_plane' "$plan_out"; then
  echo "--- plan output ---" >&2
  cat "$plan_out" >&2
  fail "plan must not propose Temporal Cloud managed-resource changes"
fi

ok "disabled-mode plan: zero Temporal provider instances, zero Temporal resource changes, no credentials"
echo "NOTE: This is a disposable source-conformance test — NOT a production plan."
