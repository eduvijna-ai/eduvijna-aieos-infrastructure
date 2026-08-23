# NATS Production Event Plane — Source Contract

**Classification: INFRASTRUCTURE SOURCE / DISPOSABLE PROOF ONLY**

```text
Infrastructure source
≠ production provisioning authorization
```

This document freezes the production NATS event-plane **source contract** aligned to
**ADR-AIEOS-046** (Chief-approved alignment; Architecture PR may be awaiting merge).
It does **not** authorize production broker mutation, credential issuance, stream
creation, DigitalOcean mutation, OpenTofu apply, App Platform deployment, or Backend
EVENT dispatcher implementation.

Machine-readable contract: [`contracts/nats/production-event-plane.yaml`](../contracts/nats/production-event-plane.yaml).

---

## 1. Authority / ADR relationship

| Layer | Role |
| --- | --- |
| ADR-AIEOS-025 | CloudEvents, JetStream, outbox, least-privilege baseline; historical modular-first examples |
| ADR-AIEOS-046 | **Current production** stream / subject / identity / credential / transport specialization |
| This repository | Deterministic source contract + disposable ACL proof + CI exactness |

ADR-046 has production precedence over ADR-025 modular-first examples
(`AIEOS_EVENTS`, `aieos.event.v1.>`).

---

## 2. Stream contract

| Item | Frozen value |
| --- | --- |
| Stream name | `AIEOS_EVENTS_PROD` |
| Subjects | `io.eduvijna.aieos.>` |

The stream is infrastructure-owned, production-environment-specific, created/verified
**before** EVENT runtime activation, and never created or repaired by the EVENT dispatcher.

If stream configuration is absent or incompatible: EVENT publishing **fails closed** into
existing outbox retry/quarantine semantics. No silent alternate stream. No Core NATS fallback.
Do not create `AIEOS_EVENTS` as production authority.

---

## 3. Subject contract

Canonical namespace:

```text
io.eduvijna.aieos.*
```

CloudEvent type is the JetStream publish subject. Content events use:

```text
io.eduvijna.aieos.content.<aggregate>.<fact>.v1
```

Do not translate into `aieos.event.v1.*`. Do not introduce a second broker-routing scheme.

---

## 4. EVENT publisher ACL

| Direction | Frozen value |
| --- | --- |
| PUB | `io.eduvijna.aieos.content.>` |
| SUB | `_INBOX.>` (+ publish-acknowledgement response semantics only) |
| Stream admin | **false** |
| `$JS.API` stream-admin | **FORBIDDEN** |

Stream coverage ≠ EVENT publisher authority. Subjects under `io.eduvijna.aieos.>` outside
`io.eduvijna.aieos.content.>` remain denied to the EVENT publisher.

---

## 5. streamadmin separation

Separate NATS identity: `streamadmin`.

Purpose: governed stream create / configure / verify / authorized maintenance.

```text
NOT EVENT runtime identity
NOT API runtime identity
NOT WORKFLOW runtime identity
NOT application business identity
```

`streamadmin` credentials must never be injected into the EVENT dispatcher. EVENT runtime
must not assume or switch to `streamadmin`.

---

## 6. JWT + NKey credential model

Production EVENT authentication:

```text
NATS JWT + NKey + .creds material
```

Not production baseline: username/password, static bearer, unauthenticated NATS, seed in URL,
credential committed to repository.

---

## 7. Encrypted-env delivery

Single production secret environment variable:

```text
AIEOS_EVENT_DISPATCHER_NATS_CREDENTIALS
```

Delivery channel: DigitalOcean App Platform encrypted environment secret.

`AIEOS_EVENT_DISPATCHER_NATS_CREDENTIALS_FILE` is **not** production authority (superseded).

---

## 8. In-memory Backend consumption

Future Backend EVENT runtime (not authorized by this gate) must:

```text
encrypted env
    ↓
AIEOS_EVENT_DISPATCHER_NATS_CREDENTIALS
    ↓
parse .creds in memory
    ↓
user_jwt_cb + signature_cb
    ↓
nats.connect(...)
```

Do not require a production on-disk credential file merely because `nats-py` supports
`user_credentials=<path>`.

Never log or emit credential contents.

---

## 9. TLS / private endpoint

```text
private broker endpoint + TLS required + certificate verification required
```

Forbidden: `tls=false`, `verify=false`, plaintext production connection, public
unauthenticated broker endpoint. Exact DNS remains environment configuration; do not freeze
ephemeral IPs in source.

---

## 10. Fail-closed behavior

Absent or incompatible `AIEOS_EVENTS_PROD` → publish fails closed → outbox retry/quarantine.
No automatic stream create/repair by EVENT runtime. No Core NATS fallback.

---

## 11. Credential rotation model

Future issuance boundary (not performed by this repository or CI):

```text
authorized NATS operator/account authority
        ↓
issue EVENT user JWT + NKey credential
        ↓
produce .creds material
        ↓
authorized secret channel only
        ↓
App Platform encrypted env
AIEOS_EVENT_DISPATCHER_NATS_CREDENTIALS
        ↓
EVENT runtime
```

Source repositories contain **zero** production seeds, user JWTs, or `.creds` files.
Credential issuance is **not** automatic CI. CI may generate **ephemeral disposable**
credentials only, outside the repository tree, then destroy them.

---

## 12. Production provisioning stop gate

This source contract does **not** authorize:

- production NATS access or mutation
- production JWT / NKey / `.creds` issuance
- production `AIEOS_EVENTS_PROD` creation on a real broker
- DigitalOcean / App Platform / Temporal / DB mutation
- OpenTofu apply
- Backend EVENT dispatcher daemon implementation
- commercial purchase
- deployment

---

## 13. Disposable proof procedure

CI / local proof (`scripts/nats/ci-test-event-plane.sh`):

1. Create a temporary directory **outside** the governed repository tree.
2. Pin and use NATS JWT/NKey tooling (`nsc`) for disposable operator/account/user authority only.
3. Start disposable `nats-server` **v2.14.3** (Backend-compatible 2.14.x family) with
   memory resolver + JetStream (no production endpoint; no cloud).
4. Prove P1–P12 (authorized Content publish, denial of non-Content / outside / admin,
   streamadmin success, stream subject exactness, no repo credential residue, cleanup).
5. Destroy all disposable operator/account/user seeds, creds, server/container, and temp dir
   on success **and** failure.
6. Never print seeds, JWTs, or `.creds` to logs.

Static companion: `scripts/nats/validate-contract.sh` proves YAML exactness and rejects
committed NATS secret markers.
