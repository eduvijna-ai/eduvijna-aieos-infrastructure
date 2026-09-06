# PostgreSQL Identity Bootstrap (ADR-AIEOS-045)

**Status:** source-defined / **NOT RELEASED** for production execution  
**Authority:** [ADR-AIEOS-045](https://github.com/eduvijna-ai/eduvijna-architecture/blob/main/decisions/ADR-AIEOS-045-aieos-dispatcher-tenant-candidate-discovery-authority.md) (Frozen / Approved)

This repository owns **PostgreSQL deployment identity administration** for ADR-AIEOS-045 candidate-reader roles. It does **not** own application schema DDL, RLS policies, queue grants, indexes, or candidate SECURITY DEFINER functions. Those belong to the Backend Alembic migration phase.

## Purpose

Provision and verify two NOLOGIN candidate-reader identities:

| Conceptual role | Purpose |
| --- | --- |
| Event candidate-reader | Cross-tenant outbox candidate discovery authority (role only in this phase) |
| Workflow candidate-reader | Cross-tenant workflow intent candidate discovery authority (role only in this phase) |

Both roles are:

- **NOLOGIN** / **NOBYPASSRLS**
- **not** schema owners or table owners
- **without** application credentials or passwords
- **without** queue table SELECT / schema CREATE / function EXECUTE in this Infrastructure phase

## Deployment administration identity

Bootstrap scripts run as an **already-established** deployment administration LOGIN role (deployment-configurable; conceptual name `aieos_db_deployment_admin`).

Required attributes:

```text
LOGIN CREATEROLE NOSUPERUSER NOCREATEDB NOREPLICATION NOBYPASSRLS
```

This Infrastructure phase **does not create** the deployment-admin role. One-time establishment from provider administrative authority (for example DigitalOcean `doadmin`) is a **separate, explicitly authorized** deployment operation documented below.

Provider `doadmin` is **break-glass / initial administration only** and must not be embedded in scripts or used as runtime/migrator/dispatcher credentials.

### One-time deployment-admin bootstrap (document only — not executed here)

Under separate Chief Architect authorization, a privileged provider administration identity may execute:

```sql
CREATE ROLE aieos_db_deployment_admin LOGIN
  CREATEROLE NOCREATEDB NOBYPASSRLS NOSUPERUSER NOREPLICATION;
-- password supplied only through authorized secret channel; never stored in Git
```

After the narrower administration role is verified, remove the provider administrative credential from routine execution environments.

## Persistent administrative relationship

When the deployment admin creates a candidate-reader (`CREATEROLE`), PostgreSQL records an administrative membership edge:

```text
member          = deployment admin
granted role    = candidate-reader
admin_option    = true
inherit_option  = false
set_option      = false
```

This is **role-management authority only**. It is **not** execution privilege inheritance. The deployment admin **cannot** `SET ROLE` to the candidate-reader under this baseline edge.

## Alembic boundary

**Alembic must never `CREATE ROLE`.** Backend migrations consume externally provisioned role names through validated environment inputs. Application function DDL (`integration.list_outbox_dispatch_candidates`, workflow candidate functions), RLS replacement, column grants, and queue indexes remain **Backend-owned**.

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/postgresql/bootstrap-candidate-readers.sh` | Idempotent candidate-reader create / safe verify |
| `scripts/postgresql/verify-candidate-readers.sh` | Read-only verification (`baseline` or `jit` mode) |
| `scripts/postgresql/grant-candidate-migration-access.sh` | Temporary migrator `SET` membership (`ADMIN false`, `INHERIT false`, `SET true`) |
| `scripts/postgresql/revoke-candidate-migration-access.sh` | Revoke temporary migrator membership |
| `scripts/postgresql/cleanup-candidate-migration-access.sh` | Safe interrupted-deployment cleanup (revoke only) |

### Required environment inputs

| Variable | Purpose |
| --- | --- |
| `AIEOS_DB_DEPLOYMENT_ADMIN_ROLE` | Deployment admin role name (connection identity for bootstrap scripts) |
| `AIEOS_EVENT_CANDIDATE_READER_ROLE` | Event candidate-reader role name |
| `AIEOS_WORKFLOW_CANDIDATE_READER_ROLE` | Workflow candidate-reader role name |
| `AIEOS_MIGRATOR_ROLE` | Migrator role (JIT grant/revoke scripts only) |

Optional verifier inputs (recommended in production verification):

- `AIEOS_RUNTIME_ROLE`
- `AIEOS_EVENT_DISPATCHER_ROLE`
- `AIEOS_WORKFLOW_DISPATCHER_ROLE`
- `AIEOS_CONTENT_MIGRATION_RUNTIME_ROLE`

All role names must match `^[a-z_][a-z0-9_]*$`. Missing or invalid values fail closed.

### libpq connection contract

Scripts use standard `psql` libpq inputs only. **`DATABASE_URL` is not accepted.**

Accepted modes:

| Mode | Requirement |
| --- | --- |
| **A. Service file** | `PGSERVICE` is set (`PGUSER` / password may come from the service definition) |
| **B. Explicit host/database** | both `PGHOST` and `PGDATABASE` are set (`PGPORT` optional; `PGUSER` / `PGPASSWORD` supplied externally) |

Scripts never echo secrets. Role identity is **never** inferred from environment variable names alone; after connection each operational script executes `SELECT current_user` and proves the session equals `AIEOS_DB_DEPLOYMENT_ADMIN_ROLE` where required.

### Candidate-reader outbound membership

Candidate-readers must **not** themselves be members of any other PostgreSQL role (`pg_auth_members.member = candidate_reader`). This is distinct from the accepted administrative edge where deployment admin is a member **of** the candidate-reader for role management (`ADMIN true`, `INHERIT false`, `SET false`).

Outbound membership would allow inherited authority during SECURITY DEFINER execution and is forbidden.

### Verifier modes

- `AIEOS_VERIFY_MODE=baseline` (default): migrator must **not** have candidate-reader membership.
- `AIEOS_VERIFY_MODE=jit`: migrator must have **exact** temporary membership (`ADMIN false`, `INHERIT false`, `SET true`).

### Fail-closed idempotency

| State | Bootstrap behavior |
| --- | --- |
| Role absent | Create exact desired attributes |
| Role present with exact safe attributes | Pass |
| Role present with LOGIN / BYPASSRLS / SUPERUSER / CREATEROLE / CREATEDB / REPLICATION | **Fail closed** (no silent normalization) |

### CONNECT / credential semantics

Candidate-readers are **NOLOGIN** and carry **no application credential**. Effective database connectivity for ordinary sessions is not the security boundary; **NOLOGIN + no credential** is. This slice does not alter `PUBLIC` database `CONNECT`.

## JIT migration membership choreography

For a separately authorized Backend Alembic migration window:

1. `grant-candidate-migration-access.sh` (deployment admin)
2. Backend migration creates SECURITY DEFINER functions owned by candidate-readers (Backend phase)
3. `revoke-candidate-migration-access.sh` (deployment admin)
4. `verify-candidate-readers.sh` in `baseline` mode

`grant-candidate-migration-access.sh` performs preflight verification, grants **both** candidate-reader memberships inside **one** PostgreSQL transaction (`BEGIN` / `COMMIT`, `ON_ERROR_STOP`), verifies exact membership triples after commit, and runs best-effort JIT cleanup if post-commit verification fails.

Final persistent state: **no migrator → candidate-reader membership**.

`cleanup-candidate-migration-access.sh` revokes temporary migrator membership only. It does **not** drop candidate-reader roles, application functions, schemas, or RLS objects. Use cleanup after interrupted deployment or failed post-commit verification recovery.

## Production execution

Production bootstrap, JIT grant/revoke, and Backend migration require **separate Chief Architect authorization**. Commercial workload provisioning remains blocked.

Dispatcher daemon enablement remains **out of scope**.

## CI

Disposable PostgreSQL 18 proof: `scripts/postgresql/ci-test-bootstrap.sh` (see `.github/workflows/ci.yml` job `postgresql-identity-bootstrap`).
