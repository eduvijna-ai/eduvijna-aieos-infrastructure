# WPI-AP-DP-I01 — App Platform Release Controller Library / Contracts / Offline Validation

## Governed source SHAs (authorization gate)

| Repository | `origin/main` |
|------------|---------------|
| Architecture | `26f9fb02cc522779b5f75456c12bc84354634edd` |
| Infrastructure | `7e295f00fa5990d6368451626d31c76adf4c3a36` |
| Backend | `8f4dd172e6a0ba8b4ad944b0ae22060442356342` |

## Architecture authority

- [ADR-AIEOS-049](https://github.com/eduvijna-ai/eduvijna-architecture/blob/main/decisions/ADR-AIEOS-049-aieos-app-platform-state-free-deployment-plane.md) — state-free deployment-plane **behavior** (WPI-AP-DP01)
- [ADR-AIEOS-050](https://github.com/eduvijna-ai/eduvijna-architecture/blob/main/decisions/ADR-AIEOS-050-aieos-app-platform-release-controller-implementation-architecture.md) — release-controller **implementation architecture** (WPI-AP-DP02 design frozen)

## Source location

```text
tools/app_platform_release/
```

Isolated Infrastructure release tool. Not packaged into Backend. Not OpenTofu App ownership.

## Runtime versions

| Concern | Value |
|---------|-------|
| Python family | 3.14 |
| Exact pin | 3.14.7 |
| Dependency manager | `uv` |
| CI uv | 0.12.4 |
| Production runner (future) | GitHub-hosted `ubuntu-24.04` only |

Committed lockfile: `tools/app_platform_release/uv.lock`.

## Contract relationship

| Contract | Role |
|----------|------|
| `contracts/app-platform/production-workflow-runtime.yaml` | **INPUT AUTHORITY** — runtime topology (unchanged by I01) |
| `contracts/app-platform/production-release-plane.yaml` | Release-controller behavior / identities / allowlist / evidence / credential **scope posture** (non-secret) |

Both are strictly parsed (Pydantic v2) and cross-validated. Disagreement fails closed.

Physical production UUIDs remain `unresolved_pre_bootstrap` (null). No invented project/VPC/App UUIDs.

## Closed mutation surface

Typed operations only:

| Operation | Bound |
|-----------|-------|
| CREATE | `POST /v2/apps` body exactly `{"project_id": <UUID>, "spec": <AppSpec>}` — explicit project UUID required; no default-project fallback |
| UPDATE / ROTATE_SECRET | `PUT /v2/apps/{exact_authorized_app_id}` |
| ROLLBACK | native validate → rollback → verify → commit sequence |

Forbidden: DELETE, restart, console, arbitrary method/URL, generic `request()`, `doctl`, shell `curl`, OpenTofu App mutation.

Provider client posture:

- base `https://api.digitalocean.com`
- TLS verify required
- `trust_env=false`
- redirects disabled
- automatic mutation retries = **0**

## Read retry vs mutation retry

- **Read**: bounded, explicit, read-only, testable
- **Mutation**: transmit exactly once; never replayed by transport, decorator, or loop

Ambiguous mutation results (timeout / connection loss / uncertain 5xx) classify `AMBIGUOUS_RESULT` and enter **read-only reconciliation only**.

## Double-read stale-write fence

`LIVE_SPEC_READ_1` → desired projection → `LIVE_SPEC_READ_2` → fence → only if unchanged → `MUTATION_SENT_ONCE`.

Provider encrypted ciphertext equality is not semantic equality.

## Secret / EV handling

Plaintext secrets and DigitalOcean `EV[...]` are SECRET MATERIAL.

- `SecretValue` redacts `str` / `repr`
- Environment acquisition pops keys immediately into redacting holders
- Dispatcher / worker secret families are isolated
- No filesystem persistence of secret-bearing AppSpecs

## Fingerprint rules

Fingerprint only the managed App projection:

1. replace every secret VALUE with one structural sentinel
2. deterministic UTF-8 JSON, sorted keys, compact separators
3. SHA-256

## Receipt rules

Future sink: sanitized `release-receipt.json` (90-day first-production retention).

I01 implements the model/serializer only (no Actions artifact upload).

Receipt may contain non-secret audit fields and secret **KEY NAMES** only. Never raw AppSpec, secrets, `EV[...]`, auth headers, or raw HTTP bodies.

## Offline CI

Job name (exact): `app-release-controller-validate`

- GitHub-hosted `ubuntu-24.04`
- `persist-credentials: false`
- `uv` 0.12.4 + Python 3.14.7
- `uv lock --check`, compileall, full pytest
- no production secrets / Environments / live DigitalOcean calls

## What I01 implements

- Isolated Python controller library
- Committed `uv.lock`
- Strict release-plane contract + cross-validation
- Closed provider HTTP abstraction
- Zero mutation retry + ambiguous-result model
- Double-read fence, targeting/cardinality, OCI digest validators
- Secret redaction / env acquisition primitives
- Canonical fingerprint + sanitized receipt model
- Pure release state machine + reconciliation classifications
- Exhaustive offline / adversarial tests
- Credential-free CI job

## WPI-AP-DP-I01R1 corrective hardenings

Fail-closed repairs on the same library/contracts/tests surface:

- SecretValue-backed provider credential; client/result repr redacted
- MutationResult retains only sanitized non-secret identifiers (no raw bodies)
- Provider READ EV[...] sanitized to SecretValue before caller use
- Removed public `delete_app` / `restart_app` / `request` stubs
- Exact steady-state / bootstrap / forbidden scope and operations.forbidden sets
- Paginated `GET /v2/apps` + local semantic-name cardinality
- Paginated registry digests list with exact digest match (no default-true)
- Typed rollback validate / start / commit paths; verify is read-only only
- CREATE reconciliation requires project+VPC+fingerprint evidence (name alone insufficient)
- Allowed provider-default normalization integrated into stale-write fence

## WPI-AP-DP-I01R2 corrective hardenings

- DOCR manifest existence uses documented response collection `manifests` with field `digest` (`sha256:<64 lowercase hex>` only); invented `digests` collection / speculative aliases fail closed
- ADR-AIEOS-049 `updated_at` hard race fence restored: any `updated_at` change between READ_1 and READ_2 is STALE_WRITE; allowed-default / ciphertext normalization never bypasses that signal

## WPI-AP-DP-I01R3 corrective hardenings

- Paginated reads require `meta.total` completeness proof (`accumulated == meta.total`); absent next with shortfall fails closed
- DOCR pagination accepts documented same-origin legacy next path `/v2/registry/{reg}/repositories/{repo}/digests` in addition to primary `/v2/registries/.../digests` (exact registry/repository only)

## WPI-AP-DP-I01R4 corrective hardenings

- Pagination next URLs may carry only `page` / `per_page` (single decimal integers; `page >= 1`; `per_page` in 1..200); unknown keys, duplicates, fragments, and userinfo fail closed

## WPI-AP-DP-I01E1 CREATE project binding + project-aware enumeration

- `create_app` requires an explicit validated project UUID and transmits exactly `{"project_id": <uuid>, "spec": <AppSpec>}` — no default-project fallback, no arbitrary extra top-level CREATE properties
- List Apps initial request is `GET /v2/apps?page=1&per_page=200&with_projects=true`; every provider next URL for that enumeration must carry exactly one `with_projects=true`
- `with_projects` is **not** authorized on deployments or DOCR pagination (R4 `page`/`per_page` only remains)
- CREATE reconciliation evidence path unchanged: semantic name + exact project UUID + exact VPC UUID + managed fingerprint (name alone / wrong project / missing project remain AMBIGUOUS / fail closed)

## WPI-AP-DP-I01E2 empty List-Apps enumeration compatibility

Live TV01 provider evidence established that DigitalOcean `GET /v2/apps` may omit the `apps` collection key when `meta.total=0` (response shape `{"meta":{"total":0}}`). This is recorded as empirically validated provider compatibility — not as a DigitalOcean documentation guarantee.

The controller normalizes **only** that exact List-Apps zero-result shape to `[]` via `_paginate(..., allow_omitted_collection_when_total_zero=True)` opted in solely by `list_apps()`.

- Absent `apps` + validated integer `meta.total == 0` → `[]`
- Absent `apps` + `meta.total > 0` / missing / malformed total → provider failure
- Present but non-list `apps` (including `null`) → provider failure (not reinterpreted as empty)
- Deployments / DOCR digest enumeration and other `_paginate` callers remain strict (default `allow_omitted_collection_when_total_zero=False`)
- `with_projects=true` List-Apps contract and pagination completeness proofs are unchanged

## What I01 explicitly does NOT authorize

| Item | Status |
|------|--------|
| WPI-AP-DP-TV01 | **NOT AUTHORIZED** |
| production release workflows | **NOT AUTHORIZED** |
| GitHub Environments / secrets | **NOT AUTHORIZED** |
| DigitalOcean PAT creation | **NOT AUTHORIZED** |
| Temporal credential creation | **NOT AUTHORIZED** |
| live DigitalOcean validation | **NOT AUTHORIZED** |
| production App create/update/rollback | **NOT AUTHORIZED** |
| production deployment | **NOT AUTHORIZED** |
| OpenTofu apply / cloud mutation | **NOT AUTHORIZED** |
| merge | **NOT AUTHORIZED** without Chief Architect exact-source authorization |
