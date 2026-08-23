# Temporal Production Workflow Plane — Source Contract

**Classification: INFRASTRUCTURE SOURCE CONTRACT / STATIC PROOF ONLY**

```text
Infrastructure source contract
!=
Temporal Cloud provisioning authorization
```

This document freezes the first-production AIEOS Temporal **workflow-plane source
contract** aligned to **ADR-AIEOS-047** (Architecture `origin/main`
`5dec3214ddf170ac7e07096b8eca1d2aad2b9109`).

It does **not** authorize Temporal Cloud access, Namespace creation/mutation,
service-account or API-key creation/revocation, Cloud Ops mutation, DigitalOcean
mutation, OpenTofu apply, App Platform mutation, Backend WORKFLOW dispatcher
implementation, Temporal worker deployment, production execution, or deployment.

Machine-readable contract:
[`contracts/temporal/production-workflow-plane.yaml`](../contracts/temporal/production-workflow-plane.yaml).

Static validation:
[`scripts/temporal/validate-contract.sh`](../scripts/temporal/validate-contract.sh).

---

## 1. Authority

| Layer | Role |
| --- | --- |
| ADR-AIEOS-026 | Temporal selection; capability task queues; deferred production hosting |
| ADR-AIEOS-029 | Production environment / deployment readiness baseline |
| ADR-AIEOS-031 | Authorization kernel — sensitive effects revalidate current authority |
| ADR-AIEOS-037 | Temporal Cloud as production Temporal service (infrastructure baseline) |
| ADR-AIEOS-045 | Committed intent deliverability; candidate discovery; identity separation |
| **ADR-AIEOS-047** | **Current production** workflow-plane hosting / identity / RBAC / operation fence |
| This repository | Deterministic source contract + static exactness CI — **not** live provider proof |

Architecture gap ≠ Infrastructure implementation freedom. Do not broaden ADR-AIEOS-047.

---

## 2. Temporal Cloud first-production baseline

```text
Temporal Cloud
=
first-production Temporal hosting baseline
```

This is a production specialization of ADR-AIEOS-026. ADR-AIEOS-026 remains valid and
is not rewritten by Infrastructure.

Production provisioning remains **NOT AUTHORIZED**.

---

## 3. Connection — Namespace Endpoint mode

Freeze endpoint **mode**:

```text
Temporal Cloud Namespace Endpoint
```

Exact provider-generated hostname is a **provisioning output**, not a source constant.
Runtime receives it as environment configuration under a separately authorized Backend /
deployment gate.

Required transport:

| Requirement | Value |
| --- | --- |
| TLS | required |
| Certificate verification | required |
| Plaintext fallback | **forbidden** |

Forbidden: `tls=False`, insecure channel, `verify=False`, certificate-verification bypass,
silent plaintext fallback. Connection failure → **FAIL CLOSED**.

---

## 4. Namespace topology

```text
environment-isolated Namespace topology
Production and staging do NOT share one Namespace
```

| Topology rule | Frozen |
| --- | --- |
| Per-tenant Namespace | **false** |
| Per-tenant task queue | **false** |
| Capability-oriented task queues | **preserved** (ADR-AIEOS-026) |

Exact production Namespace identifier = provisioning / operations data, not a source
constant.

---

## 5. Current Content Review workflow contract

| Item | Frozen value |
| --- | --- |
| Workflow type | `ContentReviewWorkflowV1` |
| Task queue | `aieos.content.review` |
| Signal | `review_decision_recorded` |

Do not invent additional production workflow types in this contract. Future types/queues
require governed source change/release.

---

## 6. Two separate workload identities

| Workload | Auth | Separate SA | Separate API key |
| --- | --- | --- | --- |
| `WORKFLOW_DISPATCHER` | Temporal Cloud Service Account + API key | yes (from worker) | yes (from worker) |
| `TEMPORAL_WORKER` | Temporal Cloud Service Account + API key | yes (from dispatcher) | yes (from dispatcher) |

Do not reuse API runtime, EVENT dispatcher, database, migrator, or human/operator
identities. Temporal Cloud identity ≠ AIEOS business Principal identity.

---

## 7. Provider RBAC floor

Minimum **stable built-in** Temporal Cloud RBAC for each runtime identity:

| Scope | Role |
| --- | --- |
| Account | **READ** |
| Target production Namespace | **WRITE** |

Forbidden runtime provider authority: Account Owner, Account Admin, Account Developer,
Namespace Admin.

### Custom Roles

**Custom Roles are not a first-production dependency.** ADR-AIEOS-047 records that
Temporal Cloud Custom Roles were **Pre-Release** at freeze time (2026-08-23). They may
be evaluated later after GA and AIEOS validation via a governed architecture revision.

Do not silently change production authority based on current provider marketing status.

### Provider coarseness vs AIEOS fence

Provider Namespace Write may be **broader** than the AIEOS application operation fence.
Broader provider RBAC does **not** broaden AIEOS source authority. First-production
boundary is defense in depth:

```text
stable provider Namespace Write
+
separate service accounts / API keys
+
Backend source operation fence
+
CI / static abuse tests
```

---

## 8. WORKFLOW_DISPATCHER operation fence

### Allowed (current governed behavior)

1. Start governed `ContentReviewWorkflowV1` on task queue `aieos.content.review`
2. Describe an identified governed Workflow Execution
3. Read/fetch Workflow history required for reconciliation
4. Signal `review_decision_recorded`
5. Wait/read result/history required for command-delivery reconciliation
6. Normal SDK metadata/protocol calls strictly necessary for the above

### Forbidden

Worker Workflow/Activity task polling and task completion/failure; Namespace
create/update/delete; Temporal account / service-account / API-key administration;
Cloud Ops API; arbitrary Workflow types / task queues / Signals; terminate; cancel;
reset; batch operations; Schedule / Search Attribute / Nexus / connectivity-rule /
HA-failover / retention administration; Namespace configuration mutation.

The dispatcher is **not** a general Temporal operator.

---

## 9. TEMPORAL_WORKER boundary

Purpose: poll/execute/respond for registered workflow/activity code on governed
capability task queues. Current governed queue: `aieos.content.review`.

Worker is not granted Cloud Ops administration merely because it executes tasks.
Worker API key must not be reused by WORKFLOW_DISPATCHER.

---

## 10. Secret environment names

### WORKFLOW_DISPATCHER (future)

```text
AIEOS_WORKFLOW_DISPATCHER_TEMPORAL_TARGET_HOST
AIEOS_WORKFLOW_DISPATCHER_TEMPORAL_NAMESPACE
AIEOS_WORKFLOW_DISPATCHER_TEMPORAL_API_KEY
AIEOS_WORKFLOW_DISPATCHER_TEMPORAL_CONNECT_TIMEOUT_SECONDS
```

`AIEOS_WORKFLOW_DISPATCHER_TEMPORAL_API_KEY` is secret. Target host and Namespace are
configuration; exact production values are **not** stored in this repository.

### TEMPORAL_WORKER (existing — do not rename)

```text
AIEOS_TEMPORAL_TARGET_HOST
AIEOS_TEMPORAL_NAMESPACE
AIEOS_TEMPORAL_API_KEY
AIEOS_TEMPORAL_CONNECT_TIMEOUT_SECONDS
AIEOS_TEMPORAL_SHUTDOWN_GRACE_SECONDS
```

No values for these variables are deposited here. No App Platform config is created in
this slice.

### Secret delivery

Future production secret delivery = authorized encrypted runtime environment secret
channel (DigitalOcean App Platform encrypted env when that deployment is separately
authorized).

Exact service-account IDs, API-key values, generated Namespace Endpoint, and production
Namespace identifier = **PROVISIONING OUTPUT / OPERATIONS DATA**, not source constants.

---

## 11. Credential / identity separation

Temporal identities are separate from:

- PostgreSQL WORKFLOW dispatcher login
- `aieos_workflow_candidate_reader` (NOLOGIN; no application credential)
- EVENT dispatcher
- API runtime
- migrator
- database deployment administrator
- human/operator credentials
- AIEOS business Principal identity

```text
Temporal Service Account ≠ PostgreSQL role
Temporal Service Account ≠ AIEOS Principal
Temporal API key ≠ business authorization
```

---

## 12. Fail-closed semantics

Missing Temporal target / Namespace / API-key secret, TLS verification failure,
connection establishment failure, or incompatible governed runtime configuration must
**not** result in plaintext fallback, anonymous connection, alternate workflow engine,
local Temporal fallback, worker credential reuse, or Cloud Ops credential reuse.

Future Backend runtime startup fails closed under a separately authorized Backend
implementation gate. This Infrastructure slice only records the contract.

---

## 13. Rotation model (source-level only)

```text
create/authorize replacement key
        ↓
inject replacement through authorized encrypted secret channel
        ↓
restart/redeploy affected workload
        ↓
verify healthy authenticated operation
        ↓
revoke old key
```

Dispatcher and worker rotate independently. This repository/CI does **not** execute any
step of that production sequence in WPI-SF01-B.

---

## 14. Observability boundary

**Allowed** non-secret operational evidence: workload kind; release/git SHA; non-secret
Temporal client identity; non-secret Namespace identifier; Workflow ID; Workflow type;
task queue; workflow intent ID; command ID where appropriate; delivery/reconciliation
result; retry/quarantine category; startup/shutdown category.

**Forbidden** log material: workflow input/command payloads; Temporal API key; DB
password/URL; authorization token; secret values.

Temporal provider audit/attribution is supplemental operational evidence. It is **not**
`security.audit_records` authority, approval truth, or business authorization truth.

---

## 15. Production provisioning stop gate

All of the following remain **NOT AUTHORIZED** (encoded `false` in the machine contract):

```text
temporal_cloud_access
namespace_create / namespace_update / namespace_delete
service_account_create / update / delete
api_key_create / api_key_revoke
cloud_ops_mutation
production_temporal_connectivity_test
production_db_access
database_migration
workflow_dispatcher_backend_implementation
temporal_worker_deployment
workflow_dispatcher_deployment
digitalocean_mutation
opentofu_apply
app_platform_mutation
production_execution
production_deployment
```

---

## 16. Why WPI-SF01-B does not fake Temporal Cloud RBAC proof

EPI-SF01 could use a disposable local NATS server for ACL exactness. A local Temporal
server **cannot** establish Temporal Cloud provider properties:

- Account Read / Namespace Write built-in RBAC
- Service Account isolation
- Cloud Ops denial
- Custom Roles behavior

Therefore WPI-SF01-B evidence is:

```text
machine-readable exact contract
+
documentation
+
static invariant validation
+
secret / residue guards
+
CI enforcement
```

**NOT:**

```text
fake live-provider evidence
local-server proof presented as Temporal Cloud RBAC proof
production Temporal connectivity test
```

Validation success means:

```text
SOURCE CONTRACT EXACTNESS / STATIC PROOF
```

It does **not** mean:

```text
PRODUCTION CONNECTIVITY PASS
PRODUCTION RBAC PASS
```
