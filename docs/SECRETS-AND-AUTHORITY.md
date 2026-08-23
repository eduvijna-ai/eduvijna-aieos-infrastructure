# Secrets and Authority

No secret values may appear in Git, `.tfvars`, OpenTofu source, CI logs, plans
committed to Git, or documentation.

## Distinct authorities

| Authority | Purpose | Must not be |
| --- | --- | --- |
| DigitalOcean production token | Deployment / OpenTofu apply | Committed; held by foundation CI |
| Spaces state key | Remote state only | Shared with app/AIStor |
| AIStor ordinary runtime | PutObject + GetObject + GetBucketLocation | Admin / break-glass / ListBucket |
| AIStor provisioning/admin | Governed bootstrap/configuration | Injected into App Platform runtime |
| AIStor break-glass delete | Auditable physical delete only | Normal admin convenience |
| TLS root/CA private key | AIEOS-controlled CA | In Git or OpenTofu state |
| AIStor server private key | TLS for AIStor | In Git, `.tfvars`, cloud-init in Git, or state |
| Runtime CA trust bundle | Future encrypted App Platform config | Public plaintext repo content |
| Database administration credential | PostgreSQL deployment identity bootstrap / JIT membership / role verification | API runtime, migrator routine use, dispatcher, Temporal, App Platform workload |
| NATS EVENT publisher `.creds` | Production EVENT dispatcher broker auth (JWT+NKey) | Committed; streamadmin; unrelated workloads; disk file as production authority |
| NATS `streamadmin` | Governed stream create/verify/maintenance only | EVENT/API/WORKFLOW runtime injection |
| Temporal WORKFLOW_DISPATCHER API key | Production WORKFLOW dispatcher Temporal Cloud data-plane auth | Worker key; Cloud Ops / Namespace Admin; EVENT/API/DB identities; committed values |
| Temporal TEMPORAL_WORKER API key | Production Temporal worker Temporal Cloud data-plane auth | Dispatcher key; Cloud Ops / Namespace Admin; EVENT/API/DB identities; committed values |
| Temporal provisioning / control-plane authority | Namespace / service-account / API-key / Cloud Ops administration | Injected into App Platform / WORKFLOW_DISPATCHER / TEMPORAL_WORKER runtime |

## Database administration credential (ADR-AIEOS-045)

Distinct from migrator, API runtime, event dispatcher, workflow dispatcher, and Temporal worker credentials.

| Property | Requirement |
| --- | --- |
| Purpose | Create/verify NOLOGIN candidate-reader roles; grant/revoke temporary migrator `SET` membership |
| Typical conceptual name | `aieos_db_deployment_admin` (deployment-configurable) |
| Provider break-glass | DigitalOcean `doadmin` is **initial/break-glass only** — not routine bootstrap identity |
| Must not be used for | Alembic migration sessions, API requests, dispatcher loops, application SQL |

Delivery: authorized deployment secret channel only. Never commit passwords, connection URIs, hostnames, or tokens to Git, OpenTofu state, or documentation.

### Candidate-reader roles

Event and workflow candidate-readers are **NOLOGIN** and have **NO CREDENTIAL**. No password, API key, or application secret is provisioned for them in the Infrastructure bootstrap phase.

## NATS EVENT credential (ADR-AIEOS-046 / EPI-SF01)

Production secret environment variable (App Platform encrypted env only):

```text
AIEOS_EVENT_DISPATCHER_NATS_CREDENTIALS
```

Contains JWT + NKey `.creds` material. Future runtime consumes it **in memory** via
`user_jwt_cb` + `signature_cb`. `AIEOS_EVENT_DISPATCHER_NATS_CREDENTIALS_FILE` is **not**
production authority.

`streamadmin` is a separate identity and must never be injected into the EVENT dispatcher.

Source repositories and CI must contain **zero** production seeds, user JWTs, or `.creds`
files. CI may generate ephemeral disposable credentials outside the repository tree only.

See [NATS-PRODUCTION-EVENT-PLANE.md](NATS-PRODUCTION-EVENT-PLANE.md).

## Temporal workflow-plane credentials (ADR-AIEOS-047 / WPI-SF01-B)

Two distinct production Temporal Cloud Service Account + API key identities:

| Workload | Secret env name | Must not be |
| --- | --- | --- |
| WORKFLOW_DISPATCHER | `AIEOS_WORKFLOW_DISPATCHER_TEMPORAL_API_KEY` | Worker key; Cloud Ops / Namespace Admin credential; committed value |
| TEMPORAL_WORKER | `AIEOS_TEMPORAL_API_KEY` | Dispatcher key; Cloud Ops / Namespace Admin credential; committed value |

Dispatcher key **must not** be the worker key. Worker key **must not** be the dispatcher key.
Neither runtime receives Temporal Cloud account / Namespace administration credentials.
Provisioning / control-plane authority must **never** be injected into application runtime.

Non-secret configuration env names (exact production values are provisioning outputs, not
source constants):

```text
AIEOS_WORKFLOW_DISPATCHER_TEMPORAL_TARGET_HOST
AIEOS_WORKFLOW_DISPATCHER_TEMPORAL_NAMESPACE
AIEOS_TEMPORAL_TARGET_HOST
AIEOS_TEMPORAL_NAMESPACE
```

No Temporal production secret values may appear in Git, OpenTofu, documentation, CI logs,
`.tfvars`, committed plans, or `.env` files. Environment-variable **names**, documentation
placeholders, contract property names, and validation detection patterns are allowed.

See [TEMPORAL-PRODUCTION-WORKFLOW-PLANE.md](TEMPORAL-PRODUCTION-WORKFLOW-PLANE.md).

## Ordinary runtime IAM (documentation)

Object:

- `s3:PutObject`
- `s3:GetObject`

Bucket:

- `s3:GetBucketLocation`

Forbidden for ordinary runtime:

- `s3:ListBucket`
- `s3:ListAllMyBuckets`
- `s3:DeleteObject`
- administrative authority

## TLS invariants

- AIEOS-controlled private CA
- Server certificate must cover the eventual stable logical AIStor hostname
- No `verify=false`
- No plaintext fallback
- Certificate issuance is a later authorized operational step

## Stable service identity (unresolved EDR)

Requirement frozen: application configuration MUST use a stable hostname, not
an ephemeral Droplet IP.

DNS/product mechanism is **unresolved** and requires one final provider/DNS
authority probe before provisioning. Do not invent a public exposure path.
