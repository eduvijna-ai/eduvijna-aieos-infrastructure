# App Platform first-production source (WPI-AP-I02)

## Authority

| ADR | Role |
|-----|------|
| ADR-AIEOS-048 | Base first-production App topology / delivery contract |
| ADR-AIEOS-048R1 | **CURRENT** provider-compliant naming authority |
| ADR-AIEOS-048R2 | **CURRENT** App Platform ownership / deployment authority |

## Current ownership (ADR-AIEOS-048R2)

Production OpenTofu **`digitalocean_app` ownership is REJECTED**.

Empirical basis: disposable provider validation **WPI-AP-SV01R1** against DigitalOcean provider **2.99.1** classified **`FAIL_OPEN_TOFU_SECRET_MATERIAL`** — a refresh-only plan materialized out-of-band encrypted `EV[...]` secret material into OpenTofu plan JSON while HCL contained zero env blocks. Encrypted DigitalOcean `EV[...]` values are treated as **secret material** and must not enter infrastructure plan/state or ordinary deployment evidence.

Production App Platform lifecycle owner:

**GOVERNED STATE-FREE DEPLOYMENT PLANE**

Persistent secret-bearing deployment state is **FORBIDDEN**.

Design/implementation of that deployment plane is **pending WPI-AP-DP01** and is **not** authorized by WPI-AP-I02.

## Historical / superseded OpenTofu App ownership

WPI-AP-I01 / WPI-AP-I01R1 previously modeled production App Platform workers as OpenTofu `digitalocean_app` resources via `modules/app_platform_worker` and independent activation guards `enable_workflow_dispatcher_app` / `enable_temporal_worker_app`.

That App ownership portion of Infrastructure `main` at `7a3b5070b138a5224de9594c9926d8cb36aa4507` is:

**ARCHITECTURALLY SUPERSEDED — MUST REMAIN INACTIVE**

WPI-AP-I02 removes those production OpenTofu App resources and the reusable App worker module. Git history remains the historical record.

## What OpenTofu still owns (DigitalOcean)

Independent, fail-closed guards (all default **false**):

- `enable_production_vpc`
- `enable_aistor_resources`

OpenTofu continues to model:

- dedicated production VPC `aieos-prod-blr1` / `blr1` / `10.130.0.0/20` (`default-blr1` reuse **FORBIDDEN**)
- AIStor Bootstrap resources (requires VPC)

App release desire **must not** instantiate `module.production_project` or any other OpenTofu object merely because an App deployment is wanted.

## Temporal Cloud

`enable_temporal_cloud_resources` remains an independent guard (default **false**).

`module "temporal_cloud_workflow_plane"` is unchanged by WPI-AP-I02 (`TEMPORAL_RESOURCE_ADDRESS_CHURN = NONE`).

## Preserved App topology (deployment contract — not OpenTofu desired-state)

Machine-readable contract:

[`contracts/app-platform/production-workflow-runtime.yaml`](../contracts/app-platform/production-workflow-runtime.yaml)

| Concern | Frozen value |
|---------|--------------|
| Region | `blr` |
| VPC | `aieos-prod-blr1` / `blr1` / `10.130.0.0/20` |
| WORKFLOW_DISPATCHER app | `aieos-prod-workflow-dispatcher` |
| TEMPORAL_WORKER app | `aieos-prod-temporal-worker` |
| Component | worker |
| Dispatcher run command | `python -m aieos.platform.runtime.entrypoints.workflow_dispatcher_main` |
| Worker run command | `python -m aieos.platform.runtime.entrypoints.temporal_worker_main` |
| Instance size | `apps-s-1vcpu-1gb-fixed` |
| Instance count | 1 each |
| Registry / repository | `eduvijna-registry` / `aieos-backend` |
| Image authority | immutable digest only |
| `deploy_on_push` | false |

Immutable Backend OCI digest authority remains binding under ADR-AIEOS-048 / 048R2 and the deployment contract. It is **not** expressed as a production OpenTofu variable after WPI-AP-I02.

## Commercial model (unchanged)

Ownership migration does **not** change the first-production commercial model:

| Slice | USD/month (list, pre-tax) |
|-------|---------------------------|
| AIStor source-modeled | 217.90 |
| WORKFLOW_DISPATCHER workload | 10.00 |
| TEMPORAL_WORKER workload | 10.00 |
| First-production modeled subtotal | **237.90** |
| Optional +USD 5 registry sensitivity | 242.90 |
| Operating target | 240 |
| Hard DigitalOcean service ceiling | 250 |

GST/statutory tax treatment remains unchanged and does not consume the USD 250 service ceiling.

## Authorization fence

WPI-AP-I02 is **source / CI / docs / PR only**.

**NOT AUTHORIZED:**

- production OpenTofu plan / apply / refresh / state access
- DigitalOcean mutation
- App Platform application create/update
- VPC / AIStor creation
- DOCR / OCI publication
- Temporal API-key issuance
- runtime secret injection
- deployment / restart
- WPI-AP-DP01 implementation

Production App Platform plan/apply/deployment remains **NOT AUTHORIZED**.
