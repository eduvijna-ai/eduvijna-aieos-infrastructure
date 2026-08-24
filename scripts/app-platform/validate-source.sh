#!/usr/bin/env bash
# WPI-AP-I01 — static first-production App Platform source proofs.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROD="${ROOT}/environments/production"
MAIN="${PROD}/main.tf"
VARS="${PROD}/variables.tf"
OUTS="${PROD}/outputs.tf"
EXAMPLE="${PROD}/production.auto.tfvars.example"
CI="${ROOT}/.github/workflows/ci.yml"
MODULE="${ROOT}/modules/app_platform_worker"
MODULE_MAIN="${MODULE}/main.tf"
MODULE_VARS="${MODULE}/variables.tf"
CONTRACT="${ROOT}/contracts/app-platform/production-workflow-runtime.yaml"
DOC="${ROOT}/docs/APP-PLATFORM-FIRST-PRODUCTION-SOURCE.md"
README="${ROOT}/README.md"
TEMPORAL_VALIDATE="${ROOT}/scripts/temporal/validate-provisioning-source.sh"

fail() { echo "APP_PLATFORM_SOURCE_FAIL: $*" >&2; exit 1; }
ok() { echo "APP_PLATFORM_SOURCE_OK: $*"; }

need_file() { [[ -f "$1" ]] || fail "missing file: $1"; }

for f in "$MAIN" "$VARS" "$OUTS" "$EXAMPLE" "$CI" "$MODULE_MAIN" "$MODULE_VARS" "$CONTRACT" "$DOC" "$README" "$TEMPORAL_VALIDATE"; do
  need_file "$f"
done

for v in enable_production_vpc enable_aistor_resources enable_workflow_dispatcher_app enable_temporal_worker_app; do
  awk "/variable \"${v}\"/,/^}/" "$VARS" \
    | grep -E '^[[:space:]]*default[[:space:]]*=[[:space:]]*false[[:space:]]*$' >/dev/null \
    || fail "${v} must default false"
done

if grep -RIn --include='*.tf' --include='*.example' --include='*.yml' --include='*.yaml' \
  --exclude-dir='.git' 'enable_cloud_resources' "$ROOT" | grep -q .; then
  fail "legacy enable_cloud_resources must be absent from active source and CI"
fi

grep -F 'default     = "aieos-prod-blr1"' "$VARS" >/dev/null \
  || fail "production VPC name must be aieos-prod-blr1"
grep -F 'default     = "blr1"' "$VARS" >/dev/null \
  || fail "production VPC region must be blr1"
grep -F 'default     = "10.130.0.0/20"' "$VARS" >/dev/null \
  || fail "production VPC CIDR must be 10.130.0.0/20"
grep -F 'production_vpc_name == "aieos-prod-blr1"' "$VARS" >/dev/null \
  || fail "production VPC name freeze validation missing"
grep -F 'production_vpc_region == "blr1"' "$VARS" >/dev/null \
  || fail "production VPC region freeze validation missing"
grep -F 'production_vpc_ip_range == "10.130.0.0/20"' "$VARS" >/dev/null \
  || fail "production VPC CIDR freeze validation missing"
grep -F 'default-blr1' "$DOC" >/dev/null \
  || fail "documentation must forbid default-blr1 reuse"

grep -F 'eduvijna-aieos-prod-workflow-dispatcher' "$MAIN" >/dev/null \
  || fail "workflow dispatcher app name missing"
grep -F 'eduvijna-aieos-prod-temporal-worker' "$MAIN" >/dev/null \
  || fail "temporal worker app name missing"
grep -F 'python -m aieos.platform.runtime.entrypoints.workflow_dispatcher_main' "$MAIN" >/dev/null \
  || fail "workflow dispatcher run command missing"
grep -F 'python -m aieos.platform.runtime.entrypoints.temporal_worker_main' "$MAIN" >/dev/null \
  || fail "temporal worker run command missing"
grep -F 'apps-s-1vcpu-1gb-fixed' "$MAIN" >/dev/null \
  || fail "app instance size slug missing"
grep -F 'app_platform_instance_count   = 1' "$MAIN" >/dev/null \
  || fail "app instance count must be 1"
grep -F 'app_registry_type             = "DOCR"' "$MAIN" >/dev/null \
  || fail "registry type must be DOCR"
grep -F 'app_image_repository          = "aieos-backend"' "$MAIN" >/dev/null \
  || fail "image repository must be aieos-backend"

grep -F 'resource "digitalocean_app" "this"' "$MODULE_MAIN" >/dev/null \
  || fail "app_platform_worker must manage digitalocean_app"
grep -F 'project_id = var.project_id' "$MODULE_MAIN" >/dev/null \
  || fail "digitalocean_app top-level project_id missing"
grep -F 'registry_type = var.image_registry_type' "$MODULE_MAIN" >/dev/null \
  || fail "image registry_type wiring missing"
grep -F 'repository    = var.image_repository' "$MODULE_MAIN" >/dev/null \
  || fail "image repository wiring missing"
grep -F 'digest        = var.image_digest' "$MODULE_MAIN" >/dev/null \
  || fail "image digest wiring missing"
grep -F 'enabled = false' "$MODULE_MAIN" >/dev/null \
  || fail "deploy_on_push must be false"
if grep -RIn 'tag[[:space:]]*=' "$MODULE" | grep -q .; then
  fail "production app module must not use image tag"
fi
if grep -RIn 'registry[[:space:]]*=' "$MODULE_MAIN" | grep -v 'registry_type' | grep -q .; then
  fail "DOCR registry field must be omitted"
fi

if grep -RInE '^[[:space:]]*(env|envs)[[:space:]]*\{' "$MODULE" | grep -q .; then
  fail "app_platform_worker must not contain env blocks"
fi
if grep -RInE 'AIEOS_(WORKFLOW_DISPATCHER_)?TEMPORAL_API_KEY|DB_PASSWORD|NATS_|secret|credential' \
  "$MODULE_VARS" "$MODULE_MAIN" | grep -q .; then
  fail "app_platform_worker must not accept secret-bearing runtime inputs"
fi

grep -F 'aieos_backend_image_digest' "$VARS" >/dev/null \
  || fail "common digest variable missing"
grep -F '^sha256:[0-9a-f]{64}$' "$VARS" >/dev/null \
  || fail "common digest regex missing"

grep -F 'module "temporal_cloud_workflow_plane"' "$MAIN" >/dev/null \
  || fail "Temporal module name must remain unchanged"
grep -F 'for_each = local.temporal_cloud_resource_instances' "$MAIN" >/dev/null \
  || fail "Temporal module for_each must remain unchanged"

grep -F 'plan_authorized: false' "$CONTRACT" >/dev/null \
  || fail "contract must keep production plan unauthorized"
grep -F 'apply_authorized: false' "$CONTRACT" >/dev/null \
  || fail "contract must keep production apply unauthorized"
grep -F 'deployment_authorized: false' "$CONTRACT" >/dev/null \
  || fail "contract must keep deployment unauthorized"

ok "WPI-AP-I01 static source proofs"
