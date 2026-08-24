# Bootstrap Infrastructure Baseline

**NON_PRODUCTION FOUNDATION**

Governed architecture SHAs at foundation creation:

- Architecture `origin/main`: `5aa0bdfdba4f237f603b4c8456dfddceb6da24d2`
- Backend `origin/main`: `0040e1121f19f0b6177e87a736d32f8ccc926440` (PED-I10B8 corrective merge)

## Distinction table

| Layer | Status |
| --- | --- |
| Architecture frozen | Yes |
| Implementation modeled (OpenTofu) | Yes |
| Production state bucket bootstrap | **COMPLETE** (`eduvijna-aieos-tofu-state-prod-sfo3` / SFO3) |
| Production remote backend initialized | **Yes** (Stage 2) |
| Production remote state materialized | **Yes** (Stage 3B) |
| Authoritative state | **serial 1 / zero managed resources** |
| Production workload cloud resources created | **No** |
| Permanent production state credential | **ESTABLISHED** (bucket-scoped `readwrite`; outside Git) |
| Production workload credentials | **NOT ACTIVATED / NOT CREATED** |
| Production deployed | **No** |
| PED-I03 activated | **No** |
| Further OpenTofu apply | **NOT AUTHORIZED** |

## Frozen Bootstrap target (modeled)

- Cloud: DigitalOcean
- Region: BLR1
- AIStor: MinIO AIStor Free
- Topology: single dedicated node
- Compute: `s-2vcpu-4gb` named `aieos-prod-aistor-01`
- OS: Ubuntu 24.04 LTS
- Storage: six NEW ~190 GiB Volumes (XFS)
- Erasure geometry (install gate): N=6 / K=3 / M=3 / EC:3
- Network: PRIVATE-SERVICE-ONLY; no Bootstrap load balancer; no public S3
- Primary bucket (literal intended): `aieos-assets-prod`
- Versioning OFF; Object Lock OFF; lifecycle expiry NONE
- Existing DOKS worker reuse: **FORBIDDEN**
- Existing `default-blr1` reuse: **FORBIDDEN** (new VPC `aieos-prod-blr1`)
- Production project: existing DigitalOcean project **AIEOS** (do not create a second)

## App Platform network rule (binding)

- App Platform region: `blr`
- VPC datacenter: `blr1`
- VPC networking: **REQUIRED**
- Dedicated egress IP: **NOT** part of Bootstrap baseline

Reason: DigitalOcean does not permit App Platform VPC attachment and dedicated
egress IPs simultaneously; private AIStor connectivity is mandatory.

## Commercial guards

Historical foundation-slice planning values (list USD, pre-tax, 2026-08-21;
**not** current complete-estate commercial authority):

- Retained DO estate ≈ USD 79.90/mo
- AIStor node = USD 24/mo
- Six × 190 GiB = USD 114/mo
- AIStor-slice projected total ≈ USD 217.90/mo

Binding complete-estate planning evidence under ADR-AIEOS-044 is approximately
**USD 294.05/month pre-tax — RED**. Full production compute remains commercially
blocked. App Platform and Managed PostgreSQL remain required by architecture and
are not yet present as workload resources.

- Target ≤ USD 240/month (DigitalOcean service-charge operating target)
- Hard ceiling USD 250/month
- Statutory taxes including Indian GST: tracked separately; do **not** consume
  the USD 250 DigitalOcean service-charge ceiling (ADR-AIEOS-044)

No billable workload OpenTofu apply may be authorized until an exact pre-apply
commercial calculation includes every resource in that apply plus retained
estate.

## Hard OpenTofu guard

The production root now uses independent default-false mutation guards:

- `enable_production_vpc`
- `enable_aistor_resources`
- `enable_workflow_dispatcher_app`
- `enable_temporal_worker_app`
- `enable_temporal_cloud_resources`

No guard implicitly enables another production slice. `enable_aistor_resources`
requires the dedicated production VPC. App Platform workload guards require the
dedicated production VPC plus one common immutable Backend OCI digest.
