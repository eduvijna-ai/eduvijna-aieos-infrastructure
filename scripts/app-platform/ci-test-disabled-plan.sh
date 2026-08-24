#!/usr/bin/env bash
# WPI-AP-I02 — backendless production-root inert-plan proof (VPC/AIStor/Temporal guards false).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROD="${ROOT}/environments/production"
LOCK="${PROD}/.terraform.lock.hcl"

fail() { echo "APP_PLATFORM_DISABLED_PLAN_FAIL: $*" >&2; exit 1; }
ok() { echo "APP_PLATFORM_DISABLED_PLAN_OK: $*"; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

require_cmd tofu
require_cmd mktemp
if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=(python3)
elif command -v py >/dev/null 2>&1; then
  PYTHON_BIN=(py -3)
else
  fail "missing required command: python3 or py"
fi

if [[ -n "${DIGITALOCEAN_TOKEN:-}" ]]; then
  fail "DIGITALOCEAN_TOKEN must be absent for disabled-plan proof"
fi
if [[ -n "${TEMPORAL_CLOUD_API_KEY:-}" ]]; then
  fail "TEMPORAL_CLOUD_API_KEY must be absent for disabled-plan proof"
fi

tofu version | grep -Fq 'OpenTofu v1.12.5' || fail "expected OpenTofu 1.12.5"
[[ -f "$LOCK" ]] || fail "missing production lockfile"
[[ ! -e "$ROOT/modules/app_platform_worker" ]] || fail "app_platform_worker module must not exist"

WORKDIR="$(mktemp -d)"
cleanup() {
  rm -rf "$WORKDIR"
}
trap cleanup EXIT

mkdir -p "$WORKDIR/environments/production" "$WORKDIR/modules"
cp "$PROD/main.tf" "$PROD/variables.tf" "$PROD/outputs.tf" "$PROD/providers.tf" "$PROD/.terraform.lock.hcl" "$WORKDIR/environments/production/"
cp -r "$ROOT/modules/production_project" "$ROOT/modules/production_vpc" "$ROOT/modules/aistor_bootstrap" \
  "$ROOT/modules/aistor_network" "$ROOT/modules/temporal_cloud_workflow_plane" \
  "$WORKDIR/modules/"

cd "$WORKDIR/environments/production"
tofu init -backend=false -input=false -reconfigure >/dev/null

PLANFILE="$WORKDIR/disabled.tfplan"
JSONFILE="$WORKDIR/disabled-plan.json"
tofu plan \
  -input=false \
  -refresh=false \
  -out="$PLANFILE" \
  -var='do_project_id=DISABLED-PLAN-DUMMY-PROJECT-ID' \
  -var='enable_production_vpc=false' \
  -var='enable_aistor_resources=false' \
  -var='enable_temporal_cloud_resources=false' \
  >/dev/null

tofu show -json "$PLANFILE" >"$JSONFILE"

"${PYTHON_BIN[@]}" - "$JSONFILE" <<'PY'
import json
import sys
from pathlib import Path

plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
resource_changes = plan.get("resource_changes", [])
if resource_changes:
    raise SystemExit(f"expected zero resource_changes, got {len(resource_changes)}")

planned = plan.get("planned_values", {}).get("root_module", {})
resources = planned.get("resources", [])
child_modules = planned.get("child_modules", [])
if resources or child_modules:
    raise SystemExit("expected zero planned root resources/modules in disabled mode")

# Fail closed if any digitalocean_app resource instance appears in plan evidence
def walk_module(mod):
    for r in mod.get("resources", []) or []:
        yield r
    for child in mod.get("child_modules", []) or []:
        yield from walk_module(child)

for r in walk_module(planned):
    if r.get("type") == "digitalocean_app":
        raise SystemExit("disabled plan must contain ZERO digitalocean_app planned resources")

for rc in resource_changes:
    if rc.get("type") == "digitalocean_app":
        raise SystemExit("disabled plan must contain ZERO digitalocean_app resource_changes")

cfg_root = (plan.get("configuration") or {}).get("root_module") or {}
for r in walk_module(cfg_root):
    if r.get("type") == "digitalocean_app":
        raise SystemExit("disabled plan must contain ZERO digitalocean_app configuration resources")

checks = plan.get("checks", [])
failed = [
    c for c in checks
    if c.get("status") not in (None, "pass", "unknown")
]
if failed:
    raise SystemExit(f"unexpected failing checks: {failed}")
PY

ok "inert plan: zero managed/data changes, zero digitalocean_app, zero provider credentials, zero backend access"
