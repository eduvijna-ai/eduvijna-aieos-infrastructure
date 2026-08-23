#!/usr/bin/env bash
# Static exactness + secret-marker guard for ADR-AIEOS-047 / WPI-SF01-B contract.
# SOURCE CONTRACT EXACTNESS / STATIC PROOF ONLY.
# Does NOT prove live Temporal Cloud connectivity or provider RBAC.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONTRACT="${ROOT}/contracts/temporal/production-workflow-plane.yaml"

fail() { echo "CONTRACT_FAIL: $*" >&2; exit 1; }
ok() { echo "CONTRACT_OK: $*"; }

[[ -f "$CONTRACT" ]] || fail "missing contract: $CONTRACT"

need() {
  local needle="$1"
  grep -F -- "$needle" "$CONTRACT" >/dev/null || fail "missing exact: $needle"
}

need_false() {
  local key="$1"
  grep -E "^[[:space:]]*${key}:[[:space:]]*false[[:space:]]*$" "$CONTRACT" >/dev/null \
    || fail "expected ${key}: false"
}

# Core authority / hosting
need 'schema_version: "1"'
need 'authority: ADR-AIEOS-047'
need 'environment: production'
need 'provider: temporal_cloud'
need 'first_production: true'

# Connection / TLS
need 'endpoint_mode: namespace_endpoint'
need 'exact_endpoint_from_provisioning: true'
need 'tls_required: true'
need 'certificate_verification_required: true'
need 'plaintext_fallback_allowed: false'

# Namespace topology
need 'environment_isolated: true'
need 'per_tenant_namespace: false'
need 'per_tenant_task_queue: false'

# Governed Content Review
need 'workflow_type: ContentReviewWorkflowV1'
need 'task_queue: aieos.content.review'
need 'signal: review_decision_recorded'

# Provider RBAC floor
need 'account_role: READ'
need 'target_namespace_role: WRITE'
need 'custom_roles_required: false'
need 'custom_roles_pre_release_at_adr047_freeze: true'
need 'namespace_admin: false'
need 'account_admin: false'
need 'account_owner: false'
need 'account_developer: false'

# Identities
need 'WORKFLOW_DISPATCHER:'
need 'TEMPORAL_WORKER:'
need 'authentication: service_account_api_key'
need 'separate_service_account_from_worker: true'
need 'separate_api_key_from_worker: true'
need 'separate_service_account_from_dispatcher: true'
need 'separate_api_key_from_dispatcher: true'
need 'cloud_ops_admin: false'
need 'worker_task_polling: false'
need 'namespace_role: WRITE'

# Dispatcher env names
need 'target_host_env: AIEOS_WORKFLOW_DISPATCHER_TEMPORAL_TARGET_HOST'
need 'namespace_env: AIEOS_WORKFLOW_DISPATCHER_TEMPORAL_NAMESPACE'
need 'api_key_env: AIEOS_WORKFLOW_DISPATCHER_TEMPORAL_API_KEY'
need 'connect_timeout_env: AIEOS_WORKFLOW_DISPATCHER_TEMPORAL_CONNECT_TIMEOUT_SECONDS'

# Worker env family preserved
need '- AIEOS_TEMPORAL_TARGET_HOST'
need '- AIEOS_TEMPORAL_NAMESPACE'
need '- AIEOS_TEMPORAL_API_KEY'
need '- AIEOS_TEMPORAL_CONNECT_TIMEOUT_SECONDS'
need '- AIEOS_TEMPORAL_SHUTDOWN_GRACE_SECONDS'

# Operation fence markers
need '- start_governed_ContentReviewWorkflowV1_on_aieos.content.review'
need '- signal_review_decision_recorded'
need '- worker_workflow_task_polling'
need '- cloud_ops_api'
need '- namespace_configuration_mutation'
need 'provider_namespace_write_broader_than_application_fence: true'
need 'application_operation_fence_controls_source_authority: true'

# Production authority fence — all false
need_false 'temporal_cloud_access'
need_false 'namespace_create'
need_false 'namespace_update'
need_false 'namespace_delete'
need_false 'service_account_create'
need_false 'service_account_update'
need_false 'service_account_delete'
need_false 'api_key_create'
need_false 'api_key_revoke'
need_false 'cloud_ops_mutation'
need_false 'production_temporal_connectivity_test'
need_false 'production_db_access'
need_false 'database_migration'
need_false 'workflow_dispatcher_backend_implementation'
need_false 'temporal_worker_deployment'
need_false 'workflow_dispatcher_deployment'
need_false 'digitalocean_mutation'
need_false 'opentofu_apply'
need_false 'app_platform_mutation'
need_false 'production_execution'
need_false 'production_deployment'

# Static proof class — must not claim live provider RBAC
need 'live_provider_rbac_claimed: false'
need 'local_temporal_server_not_temporal_cloud_rbac_proof: true'
need 'evidence_class: source_contract_exactness_static_proof'

# Reject prohibited Temporal production secret assignments (names alone are OK).
# Detection markers below are patterns only — never real secret material.
if grep -RInE --exclude-dir='.git' --exclude-dir='.terraform' \
  --exclude='guard.sh' --exclude='validate-contract.sh' \
  'AIEOS_(WORKFLOW_DISPATCHER_)?TEMPORAL_API_KEY[[:space:]]*=[[:space:]]*["'\'']?[A-Za-z0-9+/=._-]{20,}' \
  --include='*.yml' --include='*.yaml' --include='*.tf' --include='*.tfvars' \
  --include='*.env' --include='*.json' --include='*.md' --include='*.sh' \
  --include='*.txt' --include='*.properties' \
  "$ROOT" 2>/dev/null \
  | grep -q .; then
  fail "possible committed Temporal API key value assignment"
fi

# Reject obvious Temporal Cloud Ops / account bearer dump markers outside allowlisted scripts.
if grep -RInE --exclude-dir='.git' --exclude-dir='.terraform' \
  --exclude='guard.sh' --exclude='validate-contract.sh' \
  'TEMPORAL_CLOUD_API_KEY[[:space:]]*=[[:space:]]*["'\'']?[A-Za-z0-9+/=._-]{20,}|Authorization:[[:space:]]*Bearer[[:space:]]+[A-Za-z0-9._-]{32,}' \
  --include='*.yml' --include='*.yaml' --include='*.tf' --include='*.tfvars' \
  --include='*.env' --include='*.json' --include='*.txt' --include='*.sh' \
  "$ROOT" 2>/dev/null \
  | grep -q .; then
  fail "possible committed Temporal Cloud / bearer credential material"
fi

# Reject committed Temporal credential dump filenames.
if find "$ROOT" -type f \( \
  -name '*.temporal.key' -o -name 'temporal-api-key*' -o -name '*temporal*creds*' \
  \) ! -path '*/.git/*' | grep -q .; then
  fail "committed Temporal credential dump files are forbidden"
fi

ok "SOURCE CONTRACT EXACTNESS / STATIC PROOF — production-workflow-plane.yaml"
echo "NOTE: This result does NOT mean PRODUCTION CONNECTIVITY PASS or PRODUCTION RBAC PASS."
