"""Strict Pydantic models for production-workflow-runtime.yaml."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ArchitectureAuthorityRuntime(StrictModel):
    base: Literal["ADR-AIEOS-048"]
    naming: Literal["ADR-AIEOS-048R1"]
    ownership: Literal["ADR-AIEOS-048R2"]


class VpcContract(StrictModel):
    name: Literal["aieos-prod-blr1"]
    datacenter: Literal["blr1"]
    cidr: Literal["10.130.0.0/20"]
    default_vpc_reuse: Literal[False]


class RegistryContract(StrictModel):
    logical_registry: Literal["eduvijna-registry"]
    provider_registry_type: Literal["DOCR"]
    repository: Literal["aieos-backend"]
    production_authority: Literal["immutable_digest_only"]
    deploy_on_push: Literal[False]


class WorkloadRuntime(StrictModel):
    app_name: str
    component: Literal["worker"]
    run_command: str
    instance_size: Literal["apps-s-1vcpu-1gb-fixed"]
    instance_count: Literal[1]


class WorkloadsRuntime(StrictModel):
    workflow_dispatcher: WorkloadRuntime
    temporal_worker: WorkloadRuntime

    @field_validator("workflow_dispatcher")
    @classmethod
    def _dispatch_name(cls, v: WorkloadRuntime) -> WorkloadRuntime:
        if v.app_name != "aieos-prod-workflow-dispatcher":
            raise ValueError("workflow_dispatcher.app_name must be aieos-prod-workflow-dispatcher")
        return v

    @field_validator("temporal_worker")
    @classmethod
    def _worker_name(cls, v: WorkloadRuntime) -> WorkloadRuntime:
        if v.app_name != "aieos-prod-temporal-worker":
            raise ValueError("temporal_worker.app_name must be aieos-prod-temporal-worker")
        return v


class OwnershipRuntime(StrictModel):
    app_lifecycle: Literal["governed_state_free_deployment_plane"]
    opentofu_digitalocean_app: Literal["rejected"]
    persistent_secret_bearing_state_allowed: Literal[False]


class ProviderValidation(StrictModel):
    work_item: str
    provider_version: str
    classification: Literal["FAIL_OPEN_TOFU_SECRET_MATERIAL"]
    encrypted_ev_is_secret_material: Literal[True]


class RuntimeEnvironment(StrictModel):
    opentofu_owned: Literal[False]
    provider_behavior_validation_required: Literal[True]


class ProductionAuthRuntime(StrictModel):
    plan_authorized: Literal[False]
    apply_authorized: Literal[False]
    deployment_authorized: Literal[False]


class ProductionWorkflowRuntimeContract(StrictModel):
    schema_version: Literal["1"]
    architecture_authority: ArchitectureAuthorityRuntime
    environment: Literal["production"]
    region: Literal["blr"]
    vpc: VpcContract
    registry: RegistryContract
    workloads: WorkloadsRuntime
    ownership: OwnershipRuntime
    provider_validation: ProviderValidation
    runtime_environment: RuntimeEnvironment
    production: ProductionAuthRuntime
