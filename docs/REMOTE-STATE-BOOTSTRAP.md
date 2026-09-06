# Remote State — Bootstrap

## Production remote-state authority (current)

| Setting | Value |
| --- | --- |
| Backend | OpenTofu `s3` |
| Object store | DigitalOcean Spaces **Standard** |
| Bucket | `eduvijna-aieos-tofu-state-prod-sfo3` |
| Bucket posture | **EXISTS / PRIVATE** |
| Region | **SFO3** |
| Endpoint | `https://sfo3.digitaloceanspaces.com` |
| Locking | native `use_lockfile = true` |
| Versioning | **ENABLED** |
| CDN | OFF / unused |
| Public access | **FORBIDDEN** |
| Permanent credential | **ESTABLISHED** / bucket-scoped `readwrite` / outside Git |
| Stage 1 | **PASS / FORMALLY CLOSED** |
| Stage 2 | **PASS / FORMALLY CLOSED** |
| Stage 3A | **PASS / FORMALLY CLOSED** |
| Stage 3B | **PASS / FORMALLY CLOSED** |
| Production backend | **INITIALIZED** |
| Remote tfstate object | **MATERIALIZED / AUTHORITATIVE** |
| State key | `environments/production/opentofu.tfstate` |
| Initial serial | **1** |
| Managed resources | **0** |
| `tofu state list` | **EMPTY** |
| Current persistent lock object | **ABSENT** |
| Native locking | **VALIDATED** |
| Stage 3A bounded refresh-only plan | **EXECUTED / CLOSED** |
| Normal workload plan | **NOT AUTHORIZED** |
| Stage 3B exact inspected refresh-only saved-plan apply | **EXECUTED / CLOSED** |
| Further production apply | **NOT AUTHORIZED** |

Stage 3A/3B: **`DIGITALOCEAN_TOKEN` not used**; no DigitalOcean workload
mutation occurred.

### Workload vs control-plane location

| Concern | Region |
| --- | --- |
| Production **workload** (VPC / AIStor / NATS / PostgreSQL / App Platform) | **BLR1** |
| Production **OpenTofu control-plane state** | **SFO3** |

This is a control-plane state location exception under
[ADR-AIEOS-044R2](https://github.com/eduvijna-ai/eduvijna-architecture/blob/main/decisions/ADR-AIEOS-044R2-aieos-production-state-region-availability-resolution.md).
SFO3 state co-location with backup Spaces does **not** imply shared bucket or
shared credentials.

Do **not** use:

- local state as production authority
- HCP / Terraform Cloud
- AWS DynamoDB
- AWS infrastructure
- self-managed lock database
- application or AIStor credentials for state access

## Partial backend configuration

`environments/production/backend.tf` is intentionally **PARTIAL / NON-SECRET**.
CI runs `tofu init -backend=false`.

Stage 2 initialized an authorized operator working directory using external
non-secret backend configuration plus process-local credential loading.
Credentials and executable backend parameters are **not** embedded in source.

A clean or future production operator workspace does **not** inherit Stage 2/3
authorization automatically; fresh production backend initialization still
requires an explicit Chief Architect execution gate.

## Namespace collision hold

`eduvijna-aieos-tofu-state-prod` is a pre-existing NYC3 Space in `first-project`
discovered during Stage 1.

**Classification:**

**UNATTRIBUTED / PRE-EXISTING / NON-AUTHORITATIVE / HOLD**

It is **not** AIEOS production state authority. Do **not** adopt, delete,
reassign, enable Versioning merely for AIEOS, or create AIEOS state credentials
against it. Any later disposition requires separate Chief Architect authority
([ADR-AIEOS-044R1](https://github.com/eduvijna-ai/eduvijna-architecture/blob/main/decisions/ADR-AIEOS-044R1-aieos-production-state-namespace-collision-resolution.md)).

## Superseded BLR1 planned target

`eduvijna-aieos-tofu-state-prod-blr1` =

**PLANNED / NEVER CREATED / SUPERSEDED BY ADR-AIEOS-044R2**

It was never successfully created. It is **not** current state authority. No
deletion is required.

## Stage 1 / Stage 2 / Stage 3A / Stage 3B status

- **Stage 1** production-state bucket bootstrap: **PASS / FORMALLY CLOSED**
- **Stage 2** production remote-backend initialization: **PASS / FORMALLY CLOSED**
- **Stage 3A** bounded refresh-only plan / live-lock validation: **PASS / FORMALLY CLOSED**
- **Stage 3B** first authoritative remote tfstate materialization (exact inspected refresh-only saved-plan apply; 0 added / 0 changed / 0 destroyed): **PASS / FORMALLY CLOSED**

Remote tfstate is **MATERIALIZED / AUTHORITATIVE** (serial **1**; zero managed
resources). Current persistent lock object remains **ABSENT**. Native S3 lock
lifecycle is **VALIDATED**. Bounded Stage 3A plan and Stage 3B saved-plan apply
are **EXECUTED / CLOSED**. Normal production workload plan and further production
apply remain **NOT AUTHORIZED**.

## Legacy bucket

`eduvijna-terraform-state` is:

**LEGACY / UNVERIFIED / NOT AUTHORITATIVE FOR NEW AIEOS PRODUCTION STATE**

Do not adopt it merely because the name exists. Do not conflate it with the
NYC3 collision hold or the superseded BLR1 planned target above. A later
read-only inspection may determine retirement vs historical preservation. Do
not inspect object contents in this foundation slice.
