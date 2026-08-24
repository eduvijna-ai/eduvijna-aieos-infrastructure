# App Platform First-Production Source

**NON_PRODUCTION FOUNDATION**

This document records the infrastructure-source contract authorized by
ADR-AIEOS-048 and implemented by WPI-AP-I01. It does **not** authorize any
DigitalOcean mutation, production backend plan, production apply, runtime secret
injection, OCI publication, or deployment.

## Architecture authority

- Architecture ADR: `ADR-AIEOS-048`
- Source-design classification: `SOURCE_DESIGN_READY_SPLIT_SECRET_OWNERSHIP`
- Temporal workflow-plane source remains separate under `ADR-AIEOS-047`

## Activation model

Legacy `enable_cloud_resources` is removed.

The production root now uses four independent DigitalOcean slice guards, all
defaulting to `false`:

- `enable_production_vpc`
- `enable_aistor_resources`
- `enable_workflow_dispatcher_app`
- `enable_temporal_worker_app`

Temporal Cloud remains an independent plane:

- `enable_temporal_cloud_resources`

No guard implicitly enables another guard.

Fail-closed dependencies:

- `enable_aistor_resources` requires `enable_production_vpc = true`
- `enable_workflow_dispatcher_app` requires `enable_production_vpc = true`
- `enable_temporal_worker_app` requires `enable_production_vpc = true`
- both app workload guards require a non-null immutable
  `aieos_backend_image_digest`

## Frozen dedicated VPC

The production App Platform path is bound to the dedicated VPC contract frozen by
ADR-AIEOS-048:

- name: `aieos-prod-blr1`
- region/datacenter: `blr1`
- CIDR: `10.130.0.0/20`
- App Platform region: `blr`
- VPC required: `true`
- dedicated egress: `false`

`default-blr1` reuse is forbidden.

The root variable validations intentionally fail closed if a later local override
tries to change the name, region, or CIDR without a governed source revision.

## App topology

OpenTofu models two distinct App Platform applications:

1. `eduvijna-aieos-prod-workflow-dispatcher`
2. `eduvijna-aieos-prod-temporal-worker`

Each app owns exactly one worker component with:

- size `apps-s-1vcpu-1gb-fixed`
- instance count `1`
- one common immutable Backend OCI digest
- independent lifecycle boundary

The exact run commands are:

- `python -m aieos.platform.runtime.entrypoints.workflow_dispatcher_main`
- `python -m aieos.platform.runtime.entrypoints.temporal_worker_main`

## OCI / DOCR mapping

The provider schema for DigitalOcean provider `2.99.1` supports the required
shape using:

- `registry_type = DOCR`
- `repository = aieos-backend`
- `digest = sha256:...`
- `deploy_on_push.enabled = false`

The module intentionally omits:

- `registry`
- `tag`

Architecture still treats `eduvijna-registry` as the logical existing registry,
but the provider schema says the `registry` field must be left empty for DOCR.

## Runtime environment ownership fence

OpenTofu owns **NON-SECRET APP TOPOLOGY ONLY** in this slice.

OpenTofu currently owns **ZERO** runtime environment variables for App Platform.

The reusable `modules/app_platform_worker` module contains no:

- `spec.env`
- `worker.env`
- secret inputs
- Temporal API-key inputs
- generic environment maps

This is deliberate. Provider schema proves only that `value` can be omitted
syntactically; it does **not** yet prove safe out-of-band secret survival,
safe drift coexistence, or no plaintext re-materialization in state on later
refresh/update operations.

Runtime environment ownership remains blocked pending a later provider-behavior
gate.

## Commercial source posture

Modeled DigitalOcean first-production subtotal:

- retained + AIStor slice base: USD 217.90/month
- workflow dispatcher app worker: USD 10/month
- temporal worker app worker: USD 10/month
- modeled subtotal: USD 237.90/month
- operating target: USD 240/month
- hard ceiling: USD 250/month

Optional `+USD 5` registry sensitivity remains sensitivity only, not base bill:

- USD 242.90/month

Registry incremental cost is `UNPROVEN / DO NOT DOUBLE COUNT`.

## Production execution fence

This source slice does **not** authorize:

- production backend access beyond `tofu init -backend=false`
- production state reads or mutation
- DigitalOcean API mutation
- App Platform app creation/update
- VPC creation
- DOCR publication
- Temporal API-key creation
- runtime secret injection
- production deployment

Future real-state production planning must keep the existing Temporal workflow
plane safe: default/false placeholder inputs are not authority to destroy or
reconcile already-provisioned Temporal resources.
