#!/usr/bin/env bash
# Static exactness + secret-marker guard for ADR-AIEOS-046 / EPI-SF01 contract.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONTRACT="${ROOT}/contracts/nats/production-event-plane.yaml"

fail() { echo "CONTRACT_FAIL: $*" >&2; exit 1; }
ok() { echo "CONTRACT_OK: $*"; }

[[ -f "$CONTRACT" ]] || fail "missing contract: $CONTRACT"

need() {
  local needle="$1"
  grep -F -- "$needle" "$CONTRACT" >/dev/null || fail "missing exact: $needle"
}

need 'environment: production'
need 'name: AIEOS_EVENTS_PROD'
need '- "io.eduvijna.aieos.>"'
need '- "io.eduvijna.aieos.content.>"'
need '- "_INBOX.>"'
need 'stream_admin: false'
need 'js_api_stream_admin: false'
need 'scheme: jwt_nkey_creds'
need 'secret_env: AIEOS_EVENT_DISPATCHER_NATS_CREDENTIALS'
need 'delivery: encrypted_environment'
need 'runtime_materialization: in_memory_callbacks'
need 'identity: streamadmin'
need 'separate_from_event_runtime: true'
need 'tls_required: true'
need 'private_endpoint_required: true'
need 'certificate_verification_required: true'
need '- AIEOS_EVENTS'
need '- "aieos.event.v1."'
need '- AIEOS_EVENT_DISPATCHER_NATS_CREDENTIALS_FILE'

# Ensure production stream name is not AIEOS_EVENTS as the authoritative name field.
if grep -E '^\s*name:\s*AIEOS_EVENTS\s*$' "$CONTRACT" >/dev/null; then
  fail "production stream name must not be AIEOS_EVENTS"
fi

# Reject committed NATS secret material anywhere in the repo.
# Guard/validate scripts may mention the marker strings as detection patterns only.
if grep -RInE --exclude-dir='.git' --exclude-dir='.terraform' \
  'BEGIN NATS USER JWT|BEGIN USER NKEY SEED' \
  --include='*.creds' --include='*.jwt' --include='*.nk' \
  --include='*.pem' --include='*.key' --include='*.seed' \
  --include='*.txt' --include='*.yml' --include='*.yaml' \
  --include='*.tf' --include='*.json' --include='*.sh' \
  --include='*.md' --include='*.py' \
  "$ROOT" 2>/dev/null \
  | grep -vE 'scripts/guard\.sh|scripts/nats/validate-contract\.sh|scripts/nats/ci-test-event-plane\.sh' \
  | grep -q .; then
  fail "possible committed NATS JWT/NKey seed material"
fi

# Reject committed .creds files under the repository.
if find "$ROOT" -type f -name '*.creds' ! -path '*/.git/*' | grep -q .; then
  fail "committed .creds files are forbidden"
fi

ok "production-event-plane.yaml exactness + secret markers"
