#!/usr/bin/env bash
# WPI-I01 — static Temporal Cloud provisioning-source proofs.
# SOURCE MODELING / STATIC PROOF ONLY.
# Does NOT authenticate to Temporal Cloud. Does NOT plan or apply.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROD="${ROOT}/environments/production"
MODULE="${ROOT}/modules/temporal_cloud_workflow_plane"
PROVIDERS="${PROD}/providers.tf"
MAIN="${PROD}/main.tf"
VARS="${PROD}/variables.tf"
LOCK="${PROD}/.terraform.lock.hcl"
MOD_MAIN="${MODULE}/main.tf"

fail() { echo "PROVISIONING_SOURCE_FAIL: $*" >&2; exit 1; }
ok() { echo "PROVISIONING_SOURCE_OK: $*"; }

need_file() { [[ -f "$1" ]] || fail "missing file: $1"; }

need_file "$PROVIDERS"
need_file "$MAIN"
need_file "$VARS"
need_file "$LOCK"
need_file "$MOD_MAIN"
need_file "${MODULE}/variables.tf"
need_file "${MODULE}/outputs.tf"

# Provider pins / safety
grep -F 'source  = "temporalio/temporalcloud"' "$PROVIDERS" >/dev/null \
  || fail "temporalcloud provider source missing"
grep -E 'version[[:space:]]*=[[:space:]]*"= 1\.7\.0"' "$PROVIDERS" >/dev/null \
  || fail "temporalcloud provider must be pinned = 1.7.0"
grep -E 'required_version[[:space:]]*=[[:space:]]*"= 1\.12\.5"' "$PROVIDERS" >/dev/null \
  || fail "OpenTofu required_version must remain = 1.12.5"
grep -E 'version[[:space:]]*=[[:space:]]*"= 2\.99\.1"' "$PROVIDERS" >/dev/null \
  || fail "digitalocean provider pin must remain = 2.99.1"
grep -F 'endpoint           = "saas-api.tmprl.cloud:443"' "$PROVIDERS" >/dev/null \
  || grep -F 'endpoint = "saas-api.tmprl.cloud:443"' "$PROVIDERS" >/dev/null \
  || fail "Cloud Ops endpoint must be saas-api.tmprl.cloud:443"
grep -E 'allow_insecure[[:space:]]*=[[:space:]]*false' "$PROVIDERS" >/dev/null \
  || fail "allow_insecure must be false"
grep -F 'allowed_account_id = var.temporal_cloud_allowed_account_id' "$PROVIDERS" >/dev/null \
  || fail "allowed_account_id must bind to var.temporal_cloud_allowed_account_id"
if grep -E 'api_key[[:space:]]*=' "$PROVIDERS" >/dev/null; then
  fail "api_key must not appear in provider source (use TEMPORAL_CLOUD_API_KEY env only)"
fi

# Lockfile pins
grep -q 'version.*=.*"2.99.1"' "$LOCK" || fail "lockfile must pin digitalocean 2.99.1"
grep -q 'version.*=.*"1.7.0"' "$LOCK" || fail "lockfile must pin temporalcloud 1.7.0"
grep -q 'registry.opentofu.org/temporalio/temporalcloud' "$LOCK" \
  || grep -q 'registry.terraform.io/temporalio/temporalcloud' "$LOCK" \
  || fail "lockfile must contain temporalcloud provider entry"

# Independent activation guard
awk '/variable "enable_cloud_resources"/,/^}/' "$VARS" \
  | grep -E '^\s*default\s*=\s*false\s*$' >/dev/null \
  || fail "enable_cloud_resources default must be false"
awk '/variable "enable_temporal_cloud_resources"/,/^}/' "$VARS" \
  | grep -E '^\s*default\s*=\s*false\s*$' >/dev/null \
  || fail "enable_temporal_cloud_resources default must be false"
grep -F 'count  = var.enable_temporal_cloud_resources ? 1 : 0' "$MAIN" >/dev/null \
  || grep -F 'count = var.enable_temporal_cloud_resources ? 1 : 0' "$MAIN" >/dev/null \
  || fail "temporal module must use enable_temporal_cloud_resources count guard"

# Required inputs — no production defaults for unresolved decisions
for v in temporal_cloud_allowed_account_id temporal_namespace_name temporal_namespace_region temporal_namespace_retention_days; do
  block="$(awk "/variable \"${v}\"/,/^}/" "$VARS")"
  echo "$block" | grep -E '^\s*default\s*=' >/dev/null \
    && fail "${v} must not have a default"
done

# No hard-coded production decisions in .tf (descriptions must not embed candidates either)
if grep -RInE --include='*.tf' --exclude-dir='.git' --exclude-dir='.terraform' \
  'aws-ap-south-1|aws-ap-south-2' \
  "$PROD" "$MODULE" 2>/dev/null | grep -q .; then
  fail "production region must not be hard-coded in .tf source"
fi
if grep -RInE --include='*.tf' --exclude-dir='.git' --exclude-dir='.terraform' \
  'retention_days[[:space:]]*=[[:space:]]*[0-9]+' \
  "$PROD" "$MODULE" 2>/dev/null | grep -v 'var\.' | grep -q .; then
  fail "retention_days must not be hard-coded as a numeric literal"
fi

# Namespace invariants in module
grep -E 'api_key_auth[[:space:]]*=[[:space:]]*true' "$MOD_MAIN" >/dev/null \
  || fail "api_key_auth must be true"
grep -E 'enable_delete_protection[[:space:]]*=[[:space:]]*true' "$MOD_MAIN" >/dev/null \
  || fail "enable_delete_protection must be true"
grep -F 'regions        = [var.namespace_region]' "$MOD_MAIN" >/dev/null \
  || grep -F 'regions = [var.namespace_region]' "$MOD_MAIN" >/dev/null \
  || fail "regions must be a one-element list [var.namespace_region]"
if grep -E 'regions[[:space:]]*=[[:space:]]*\[[^]]*,[^]]*\]' "$MOD_MAIN" >/dev/null; then
  fail "HA/two-region regions list is forbidden"
fi

# Exactly two distinct service accounts with frozen RBAC
sa_count="$(grep -c 'resource "temporalcloud_service_account"' "$MOD_MAIN" || true)"
[[ "$sa_count" == "2" ]] || fail "expected exactly two temporalcloud_service_account resources, got ${sa_count}"
grep -F 'resource "temporalcloud_service_account" "workflow_dispatcher"' "$MOD_MAIN" >/dev/null \
  || fail "WORKFLOW_DISPATCHER service account resource missing"
grep -F 'resource "temporalcloud_service_account" "temporal_worker"' "$MOD_MAIN" >/dev/null \
  || fail "TEMPORAL_WORKER service account resource missing"
dispatcher_reads="$(awk '/resource "temporalcloud_service_account" "workflow_dispatcher"/,/^}/' "$MOD_MAIN" | grep -c 'account_access[[:space:]]*=[[:space:]]*"read"' || true)"
worker_reads="$(awk '/resource "temporalcloud_service_account" "temporal_worker"/,/^}/' "$MOD_MAIN" | grep -c 'account_access[[:space:]]*=[[:space:]]*"read"' || true)"
[[ "$dispatcher_reads" -ge 1 ]] || fail "WORKFLOW_DISPATCHER must use account_access = \"read\""
[[ "$worker_reads" -ge 1 ]] || fail "TEMPORAL_WORKER must use account_access = \"read\""
grep -E 'permission[[:space:]]*=[[:space:]]*"write"' "$MOD_MAIN" >/dev/null \
  || fail "target Namespace permission must be write"
write_count="$(grep -c 'permission[[:space:]]*=[[:space:]]*"write"' "$MOD_MAIN" || true)"
[[ "$write_count" == "2" ]] || fail "expected exactly two Namespace write grants, got ${write_count}"

# Forbidden constructs
if grep -RIn --include='*.tf' --exclude-dir='.git' --exclude-dir='.terraform' \
  'namespace_scoped_access' "$PROD" "$MODULE" 2>/dev/null | grep -q .; then
  fail "namespace_scoped_access is not authorized for WPI-I01"
fi
if grep -RIn --include='*.tf' --exclude-dir='.git' --exclude-dir='.terraform' \
  'temporalcloud_apikey\|temporalcloud_custom_role\|temporalcloud_connectivity_rule' \
  "$ROOT" 2>/dev/null | grep -q .; then
  fail "apikey / custom_role / connectivity_rule resources are forbidden in WPI-I01"
fi
if grep -RInE --include='*.tf' --exclude-dir='.git' --exclude-dir='.terraform' \
  'account_access[[:space:]]*=[[:space:]]*"(admin|developer|owner)"' \
  "$PROD" "$MODULE" 2>/dev/null | grep -q .; then
  fail "admin/developer/owner account_access is forbidden for workload SAs"
fi

# No production endpoint hostnames other than Cloud Ops provider endpoint
if grep -RInE --include='*.tf' --exclude-dir='.git' --exclude-dir='.terraform' \
  '\.tmprl\.cloud' "$PROD" "$MODULE" 2>/dev/null \
  | grep -v 'saas-api.tmprl.cloud:443' | grep -q .; then
  fail "no production Namespace endpoint hostname may be hard-coded"
fi

# No credential / token literals in Temporal provisioning source
if grep -RInE --include='*.tf' --include='*.tfvars' --include='*.example' \
  --exclude-dir='.git' --exclude-dir='.terraform' \
  'TEMPORAL_CLOUD_API_KEY[[:space:]]*=[[:space:]]*["'\''][^"'\'']+|api_key[[:space:]]*=[[:space:]]*["'\''][^$"'\'']|"eyJ[A-Za-z0-9_-]{20,}' \
  "$PROD" "$MODULE" 2>/dev/null | grep -q .; then
  fail "Temporal credential/token literals are forbidden"
fi

# CI must not inject Temporal Cloud credentials (bash absence-checks are allowed)
if grep -RInE --include='*.yml' --include='*.yaml' \
  '^[[:space:]]*TEMPORAL_CLOUD_API_KEY:[[:space:]]*' \
  "${ROOT}/.github" 2>/dev/null | grep -q .; then
  fail "CI must not define TEMPORAL_CLOUD_API_KEY as a workflow env/secret"
fi
if grep -RInE --include='*.yml' --include='*.yaml' \
  'TEMPORAL_CLOUD_API_KEY[[:space:]]*=[[:space:]]*[^$]' \
  "${ROOT}/.github" 2>/dev/null | grep -q .; then
  fail "CI must not assign TEMPORAL_CLOUD_API_KEY"
fi

ok "WPI-I01 Temporal Cloud provisioning-source static proofs"
echo "NOTE: This result does NOT authorize Temporal Cloud access, plan, apply, or commercial enrollment."
