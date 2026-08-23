# WPI-I01 — Temporal Cloud Provisioning Source

**Classification: INFRASTRUCTURE SOURCE / TESTS / CI / DOCUMENTATION ONLY**

```text
WPI-I01 source presence
!=
Temporal Cloud production provisioning authority
```

## 1. Exact governed source gate

| Repository | SHA |
| --- | --- |
| Architecture `origin/main` | `5dec3214ddf170ac7e07096b8eca1d2aad2b9109` |
| Infrastructure base | `84bd2e6d696af5849c84b9be5cd422b38f14d5ec` |
| Backend `origin/main` | `8f4dd172e6a0ba8b4ad944b0ae22060442356342` |

Binding authority: ADR-AIEOS-026 / 029 / 031 / 045 / **047**, Infrastructure
[`contracts/temporal/production-workflow-plane.yaml`](../contracts/temporal/production-workflow-plane.yaml),
Backend PED-I12 / PED-I12R1.

## 2. WPI-PF01 preflight basis

WPI-PF01 established:

- Provider pin candidate **1.7.0** and Cloud Ops endpoint `saas-api.tmprl.cloud:443`
- Namespace Endpoint + API-key auth + delete protection are provider-supported
- Built-in Account **READ** + Namespace **WRITE** is representable for two SAs
- Temporal Cloud account / control-plane access was **absent** on the operator host
- Existing Temporal Cloud resources are therefore **UNKNOWN / UNCONFIRMED**

WPI-I01 does **not** encode an assumption that the Namespace does not exist.

## 3. Provider

| Item | Value |
| --- | --- |
| OpenTofu | `= 1.12.5` |
| DigitalOcean provider | `= 2.99.1` (unchanged) |
| Temporal Cloud provider | `temporalio/temporalcloud` `= 1.7.0` |
| Cloud Ops endpoint | `saas-api.tmprl.cloud:443` |
| `allow_insecure` | `false` |
| `allowed_account_id` | `var.temporal_cloud_allowed_account_id` |
| `api_key` in source | **forbidden** — later use provider env `TEMPORAL_CLOUD_API_KEY` only |

## 4. Modeled resource topology

Module: [`modules/temporal_cloud_workflow_plane/`](../modules/temporal_cloud_workflow_plane/)

Required module files:

- `main.tf` — Namespace + two service accounts
- `variables.tf` — required inputs
- `outputs.tf` — non-secret identifiers
- `versions.tf` — `temporalio/temporalcloud = 1.7.0` (required for OpenTofu provider inheritance; same pattern as other modules)

| Resource | Purpose |
| --- | --- |
| `temporalcloud_namespace.production` | One production Namespace |
| `temporalcloud_service_account.workflow_dispatcher` | WORKFLOW_DISPATCHER |
| `temporalcloud_service_account.temporal_worker` | TEMPORAL_WORKER |

Namespace source invariants:

- `api_key_auth = true`
- `namespace_lifecycle.enable_delete_protection = true`
- `regions = [var.namespace_region]` — **structurally one region** (HA not authorized)

Each service account:

- `account_access = "read"`
- target Namespace `permission = "write"`
- **no** `namespace_scoped_access`
- **no** Custom Roles / admin / developer / owner

## 5. Independent activation guard

```hcl
enable_temporal_cloud_resources  # default false
```

Independent from DigitalOcean `enable_cloud_resources` (also default **false**).

`true` requires a later explicit Chief Architect production Temporal Cloud
provisioning gate. WPI-I01 does not authorize that gate.

## 6. Unresolved production inputs (no defaults)

| Variable | Status |
| --- | --- |
| `temporal_cloud_allowed_account_id` | unresolved |
| `temporal_namespace_name` | unresolved |
| `temporal_namespace_region` | unresolved |
| `temporal_namespace_retention_days` | unresolved |

Non-binding WPI-PF01 observations (documentation only — **not frozen**):

- Leading region candidate: `aws-ap-south-1`
- Alternative: `aws-ap-south-2`
- Temporal Essentials floor: USD 100/month or 5% of usage (whichever greater)
- Temporal Cloud cost is **separate** from the DigitalOcean USD 250 Bootstrap ceiling

## 7. API keys deliberately excluded

WPI-I01 creates **zero** `temporalcloud_apikey` resources.

Reason: the provider exposes the generated full token as a sensitive field that
would enter OpenTofu/Terraform state. Workload credential material in shared
tfstate requires a separate secret-state / credential-issuance governance
decision.

A later gate must govern: API-key creation, expiry, rotation, secret delivery,
App Platform encrypted-env injection, and revocation.

Static proof: `scripts/temporal/validate-provisioning-source.sh` fails if
`temporalcloud_apikey` appears.

## 8. Existing-resource / import safety

Before any production plan/apply, the operator **MUST** perform an authenticated
read-only Temporal Cloud inventory.

If matching Namespace or service accounts already exist: **STOP** before create.
Use a separately reviewed adoption/import plan.

Import is supported by the provider for:

- `temporalcloud_namespace`
- `temporalcloud_service_account`

WPI-I01 does **not** execute imports and does **not** add automatic import blocks.

## 9. Authority fence (this slice)

| Act | Occurred? |
| --- | --- |
| Live Temporal Cloud access | **NO** |
| Commercial enrollment | **NO** |
| Production plan | **NO** |
| Production apply | **NO** |
| Production remote-state access | **NO** |
| API-key issuance | **NO** |
| DigitalOcean / App Platform mutation | **NO** |
| Deployment | **NO** |

Static validators:

- [`scripts/temporal/validate-contract.sh`](../scripts/temporal/validate-contract.sh)
- [`scripts/temporal/validate-provisioning-source.sh`](../scripts/temporal/validate-provisioning-source.sh)
