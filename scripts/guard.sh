#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() { echo "GUARD_FAIL: $*" >&2; exit 1; }

# Forbidden production local-state authority
if find . -type f \( -name '*.tfstate' -o -name '*.tfstate.*' \) \
  ! -path './.git/*' | grep -q .; then
  fail "tfstate files must not exist in the repository tree"
fi

# Hard-coded credential-ish assignments in .tf (allow comments/docs)
if grep -RInE \
  --include='*.tf' --include='*.tfvars' --include='*.hcl' \
  --exclude-dir='.git' --exclude-dir='.terraform' \
  '(token\s*=\s*"[^$]|access_key\s*=\s*"[^$]|secret_key\s*=\s*"[^$]|DIGITALOCEAN_TOKEN\s*=\s*"[^$]|private_key\s*=\s*"-----BEGIN)' \
  .; then
  fail "possible plaintext credential assignment in OpenTofu files"
fi

# Disallow committed auto.tfvars (except examples)
if find . -type f -name '*.auto.tfvars' ! -name '*.example' ! -path './.git/*' | grep -q .; then
  fail "committed *.auto.tfvars is forbidden"
fi

# Disallow apply/destroy in CI scripts/workflows
if grep -RInE --include='*.yml' --include='*.yaml' --include='*.sh' \
  --exclude-dir='.git' \
  'tofu[[:space:]]+(apply|destroy)|terraform[[:space:]]+(apply|destroy)' .; then
  fail "apply/destroy commands are forbidden in CI/scripts"
fi

# Disallow committed NATS JWT / NKey seed material and .creds files
if find . -type f -name '*.creds' ! -path './.git/*' | grep -q .; then
  fail "committed .creds files are forbidden"
fi
if grep -RInE --exclude-dir='.git' --exclude-dir='.terraform' \
  --exclude='guard.sh' --exclude='validate-contract.sh' --exclude='ci-test-event-plane.sh' \
  'BEGIN NATS USER JWT|BEGIN USER NKEY SEED' .; then
  fail "possible committed NATS JWT or NKey seed material"
fi

# Disallow committed Temporal API key value assignments (env NAMES alone are allowed)
if grep -RInE --exclude-dir='.git' --exclude-dir='.terraform' \
  --exclude='guard.sh' --exclude='validate-contract.sh' \
  'AIEOS_(WORKFLOW_DISPATCHER_)?TEMPORAL_API_KEY[[:space:]]*=[[:space:]]*["'\'']?[A-Za-z0-9+/=._-]{20,}' \
  --include='*.yml' --include='*.yaml' --include='*.tf' --include='*.tfvars' \
  --include='*.env' --include='*.json' --include='*.txt' --include='*.properties' \
  .; then
  fail "possible committed Temporal API key value assignment"
fi

# Disallow committed Temporal credential dump filenames
if find . -type f \( \
  -name '*.temporal.key' -o -name 'temporal-api-key*' -o -name '*temporal*creds*' \
  \) ! -path './.git/*' | grep -q .; then
  fail "committed Temporal credential dump files are forbidden"
fi

# Disallow production remote init without -backend=false in CI
if grep -RIn --include='*.yml' --include='*.yaml' --exclude-dir='.git' 'tofu init' .github \
  | grep -v '\-backend=false' | grep -q .; then
  fail "CI tofu init must use -backend=false"
fi

echo "GUARD_OK"
