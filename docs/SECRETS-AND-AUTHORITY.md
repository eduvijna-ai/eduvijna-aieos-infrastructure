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
