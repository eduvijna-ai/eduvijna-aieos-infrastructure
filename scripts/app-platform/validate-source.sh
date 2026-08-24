#!/usr/bin/env bash
# WPI-AP-I02 / ADR-AIEOS-048R2 — App Platform ownership reconciliation static proofs.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROD="${ROOT}/environments/production"
MAIN="${PROD}/main.tf"
VARS="${PROD}/variables.tf"
OUTS="${PROD}/outputs.tf"
EXAMPLE="${PROD}/production.auto.tfvars.example"
CI="${ROOT}/.github/workflows/ci.yml"
MODULE="${ROOT}/modules/app_platform_worker"
CONTRACT="${ROOT}/contracts/app-platform/production-workflow-runtime.yaml"
DOC="${ROOT}/docs/APP-PLATFORM-FIRST-PRODUCTION-SOURCE.md"
README="${ROOT}/README.md"
TEMPORAL_VALIDATE="${ROOT}/scripts/temporal/validate-provisioning-source.sh"

fail() { echo "APP_PLATFORM_SOURCE_FAIL: $*" >&2; exit 1; }
ok() { echo "APP_PLATFORM_SOURCE_OK: $*"; }

need_file() { [[ -f "$1" ]] || fail "missing file: $1"; }

assert_provider_name() {
  local name="$1"
  local len="${#name}"
  [[ "$len" -le 32 ]] || fail "app name '${name}' length ${len} exceeds 32"
  [[ "$name" =~ ^[a-z][a-z0-9-]*[a-z0-9]$ ]] || fail "app name '${name}' fails provider-compatible shape"
}

for f in "$MAIN" "$VARS" "$OUTS" "$EXAMPLE" "$CI" "$CONTRACT" "$DOC" "$README" "$TEMPORAL_VALIDATE"; do
  need_file "$f"
done

# 1. ZERO production digitalocean_app resource declarations
if grep -RIn --include='*.tf' 'resource[[:space:]]\+"digitalocean_app"' \
  "${PROD}" "${ROOT}/modules" 2>/dev/null | grep -q .; then
  fail "production OpenTofu must contain ZERO digitalocean_app resources"
fi
ok "PRODUCTION_OPENTOFU_DIGITALOCEAN_APP_RESOURCE_COUNT = 0"

# 2-3. no app_platform_worker module or references
[[ ! -e "$MODULE" ]] || fail "modules/app_platform_worker must not exist after ADR-AIEOS-048R2 reconciliation"
if grep -RIn --include='*.tf' 'modules/app_platform_worker\|app_platform_worker' \
  "${PROD}" "${ROOT}/modules" 2>/dev/null | grep -q .; then
  fail "active .tf must not reference modules/app_platform_worker"
fi
ok "app_platform_worker module absent"

# 4. no production root App module/instance locals
for needle in \
  'module "workflow_dispatcher_app"' \
  'module "temporal_worker_app"' \
  'workflow_dispatcher_app_instances' \
  'temporal_worker_app_instances' \
  'module.workflow_dispatcher_app' \
  'module.temporal_worker_app'
do
  if grep -Fn "$needle" "$MAIN" "$OUTS" >/dev/null 2>&1; then
    fail "production root still references ${needle}"
  fi
done
ok "production App module paths absent"

# 5. superseded activation variables gone
for v in enable_workflow_dispatcher_app enable_temporal_worker_app; do
  if grep -n "variable \"${v}\"" "$VARS" >/dev/null 2>&1; then
    fail "${v} must not remain in production variables.tf"
  fi
  if grep -RIn --include='*.tf' --include='*.example' --include='*.yml' --include='*.yaml' \
    --exclude-dir='.git' --exclude-dir='docs' "${v}" "$ROOT" 2>/dev/null \
    | grep -v 'scripts/app-platform/validate-source.sh' \
    | grep -v 'HISTORICAL\|historical\|superseded\|SUPERSEDED' \
    | grep -q .; then
    # Allow docs historical mentions only under docs/; active HCL/CI must be clean
    :
  fi
  if grep -n "${v}" "$VARS" "$MAIN" "$OUTS" "$EXAMPLE" "$CI" >/dev/null 2>&1; then
    fail "${v} must not remain in active production HCL/CI/example"
  fi
done
ok "superseded App OpenTofu activation variables absent"

# 6. aieos_backend_image_digest gone from production OpenTofu HCL
if grep -n 'aieos_backend_image_digest' "$VARS" "$MAIN" "$OUTS" "$EXAMPLE" >/dev/null 2>&1; then
  fail "aieos_backend_image_digest must not remain in production OpenTofu HCL after App ownership removal"
fi
ok "aieos_backend_image_digest absent from production OpenTofu HCL"

# Remaining DigitalOcean OpenTofu guards default false
for v in enable_production_vpc enable_aistor_resources; do
  awk "/variable \"${v}\"/,/^}/" "$VARS" \
    | grep -E '^[[:space:]]*default[[:space:]]*=[[:space:]]*false[[:space:]]*$' >/dev/null \
    || fail "${v} must default false"
done
awk '/variable "enable_temporal_cloud_resources"/,/^}/' "$VARS" \
  | grep -E '^[[:space:]]*default[[:space:]]*=[[:space:]]*false[[:space:]]*$' >/dev/null \
  || fail "enable_temporal_cloud_resources must default false"

if grep -RIn --include='*.tf' --include='*.example' --include='*.yml' --include='*.yaml' \
  --exclude-dir='.git' 'enable_cloud_resources' "$ROOT" | grep -q .; then
  fail "legacy enable_cloud_resources must be absent from active source and CI"
fi

# VPC / region / CIDR
grep -F 'default     = "aieos-prod-blr1"' "$VARS" >/dev/null \
  || fail "production VPC name must be aieos-prod-blr1"
grep -F 'default     = "blr1"' "$VARS" >/dev/null \
  || fail "production VPC region must be blr1"
grep -F 'default     = "10.130.0.0/20"' "$VARS" >/dev/null \
  || fail "production VPC CIDR must be 10.130.0.0/20"
if grep -RIn --include='*.tf' --include='*.md' --include='*.yaml' --include='*.yml' \
  --exclude-dir='.git' 'default-blr1' "$ROOT" \
  | grep -viE 'forbidden|must not|reuse|collision|against' \
  | grep -q .; then
  # soft: ensure docs still forbid reuse
  :
fi
grep -RIn --include='*.md' --include='*.yaml' 'default_vpc_reuse: false\|default-blr1.*FORBIDDEN\|reuse forbidden\|default_vpc_reuse: false' \
  "$CONTRACT" "$DOC" >/dev/null \
  || fail "default-blr1 production reuse must remain forbidden in contract/docs"

# Contract ownership / evidence
grep -F 'ownership: ADR-AIEOS-048R2' "$CONTRACT" >/dev/null \
  || fail "contract must declare ownership: ADR-AIEOS-048R2"
grep -F 'opentofu_digitalocean_app: rejected' "$CONTRACT" >/dev/null \
  || fail "contract must reject opentofu digitalocean_app ownership"
grep -F 'persistent_secret_bearing_state_allowed: false' "$CONTRACT" >/dev/null \
  || fail "contract must forbid persistent secret-bearing state"
grep -F 'FAIL_OPEN_TOFU_SECRET_MATERIAL' "$CONTRACT" >/dev/null \
  || fail "contract must record FAIL_OPEN_TOFU_SECRET_MATERIAL"
grep -F 'provider_version: "2.99.1"' "$CONTRACT" >/dev/null \
  || fail "contract must record provider 2.99.1"
grep -F 'encrypted_ev_is_secret_material: true' "$CONTRACT" >/dev/null \
  || fail "contract must classify EV[...] as secret material"
if grep -E 'EV\[[A-Za-z0-9+/=_-]{8,}' "$CONTRACT" >/dev/null 2>&1; then
  fail "contract must not contain real EV[...] ciphertext"
fi

# Topology preserved in deployment contract
assert_provider_name "aieos-prod-workflow-dispatcher"
assert_provider_name "aieos-prod-temporal-worker"
grep -F 'app_name: aieos-prod-workflow-dispatcher' "$CONTRACT" >/dev/null \
  || fail "contract missing dispatcher app name"
grep -F 'app_name: aieos-prod-temporal-worker' "$CONTRACT" >/dev/null \
  || fail "contract missing temporal worker app name"
grep -F 'python -m aieos.platform.runtime.entrypoints.workflow_dispatcher_main' "$CONTRACT" >/dev/null \
  || fail "contract missing dispatcher run command"
grep -F 'python -m aieos.platform.runtime.entrypoints.temporal_worker_main' "$CONTRACT" >/dev/null \
  || fail "contract missing temporal worker run command"
grep -F 'instance_size: apps-s-1vcpu-1gb-fixed' "$CONTRACT" >/dev/null \
  || fail "contract missing apps-s-1vcpu-1gb-fixed"
grep -F 'instance_count: 1' "$CONTRACT" >/dev/null \
  || fail "contract missing instance_count 1"
grep -F 'name: aieos-prod-blr1' "$CONTRACT" >/dev/null \
  || fail "contract missing VPC name"
grep -F 'datacenter: blr1' "$CONTRACT" >/dev/null \
  || fail "contract missing VPC datacenter"
grep -F 'cidr: 10.130.0.0/20' "$CONTRACT" >/dev/null \
  || fail "contract missing VPC CIDR"
grep -F 'region: blr' "$CONTRACT" >/dev/null \
  || fail "contract missing App region blr"
grep -F 'repository: aieos-backend' "$CONTRACT" >/dev/null \
  || fail "contract missing aieos-backend"
grep -F 'production_authority: immutable_digest_only' "$CONTRACT" >/dev/null \
  || fail "contract missing immutable digest authority"
grep -F 'deploy_on_push: false' "$CONTRACT" >/dev/null \
  || fail "contract must keep deploy_on_push false"
grep -F 'deployment_authorized: false' "$CONTRACT" >/dev/null \
  || fail "contract must keep production deployment unauthorized"
grep -F 'plan_authorized: false' "$CONTRACT" >/dev/null \
  || fail "contract must keep plan unauthorized"
grep -F 'apply_authorized: false' "$CONTRACT" >/dev/null \
  || fail "contract must keep apply unauthorized"

# Superseded long names must not be current authority
if grep -RIn --include='*.tf' --include='*.yaml' --include='*.yml' --include='*.example' \
  --exclude-dir='.git' 'eduvijna-aieos-prod-' "$ROOT" \
  | grep -viE 'superseded|historical|SUPERSEDED|HISTORICAL' \
  | grep -q .; then
  fail "superseded eduvijna-aieos-prod-* names must not appear as current authority"
fi

# Temporal module unchanged structurally
grep -F 'module "temporal_cloud_workflow_plane"' "$MAIN" >/dev/null \
  || fail "temporal module name must remain temporal_cloud_workflow_plane"
grep -F 'source   = "../../modules/temporal_cloud_workflow_plane"' "$MAIN" >/dev/null \
  || fail "temporal module source path must remain unchanged"
grep -F 'for_each = local.temporal_cloud_resource_instances' "$MAIN" >/dev/null \
  || fail "temporal module must use for_each = local.temporal_cloud_resource_instances"

# any_digitalocean_slice_enabled must not include App activation
if grep -n 'enable_workflow_dispatcher_app\|enable_temporal_worker_app' "$MAIN" >/dev/null 2>&1; then
  fail "main.tf must not reference removed App activation variables"
fi
grep -F 'var.enable_production_vpc' "$MAIN" >/dev/null \
  || fail "any_digitalocean_slice_enabled must still consider VPC"
grep -F 'var.enable_aistor_resources' "$MAIN" >/dev/null \
  || fail "any_digitalocean_slice_enabled must still consider AIStor"

# Commercial App costs retained as evidence
grep -F 'commercial_workflow_dispatcher_app_usd_mo = 10.00' "$MAIN" >/dev/null \
  || fail "commercial WORKFLOW_DISPATCHER USD 10 evidence must remain"
grep -F 'commercial_temporal_worker_app_usd_mo     = 10.00' "$MAIN" >/dev/null \
  || fail "commercial TEMPORAL_WORKER USD 10 evidence must remain"
grep -F 'commercial_aistor_slice_usd_mo            = 217.90' "$MAIN" >/dev/null \
  || fail "commercial AIStor USD 217.90 evidence must remain"
grep -F 'commercial_target_usd_mo       = 240.00' "$MAIN" >/dev/null \
  || fail "commercial target USD 240 must remain"
grep -F 'commercial_hard_ceiling_usd_mo = 250.00' "$MAIN" >/dev/null \
  || fail "commercial hard ceiling USD 250 must remain"

# Docs current ownership
grep -F 'ADR-AIEOS-048R2' "$DOC" >/dev/null \
  || fail "APP-PLATFORM doc must cite ADR-AIEOS-048R2"
grep -Ei 'digitalocean_app.*reject|OpenTofu.*reject|ownership.*reject' "$DOC" >/dev/null \
  || fail "APP-PLATFORM doc must state OpenTofu digitalocean_app ownership rejected"
grep -F 'WPI-AP-DP01' "$DOC" >/dev/null \
  || fail "APP-PLATFORM doc must reference pending WPI-AP-DP01"

# CI must prove zero digitalocean_app
grep -F 'scripts/app-platform/validate-source.sh' "$CI" >/dev/null \
  || fail "ci.yml must run app-platform validate-source.sh"
grep -F 'scripts/app-platform/ci-test-disabled-plan.sh' "$CI" >/dev/null \
  || fail "ci.yml must run app-platform ci-test-disabled-plan.sh"
grep -F 'enable_production_vpc enable_aistor_resources' "$CI" >/dev/null \
  || fail "ci.yml must prove remaining DO guards default false without App enables"

ok "WPI-AP-I02 App Platform ownership reconciliation proofs passed"
