"""Strict Pydantic models for production-release-plane.yaml."""

from __future__ import annotations

import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ArchitectureAuthorityRelease(StrictModel):
    deployment_plane: Literal["ADR-AIEOS-049"]
    implementation_architecture: Literal["ADR-AIEOS-050"]


class ControllerPlacement(StrictModel):
    placement: Literal["tools/app_platform_release"]
    packaging: Literal["infrastructure_isolated_release_tool"]
    backend_package_forbidden: Literal[True]
    opentofu_app_ownership_forbidden: Literal[True]


class RuntimePin(StrictModel):
    language: Literal["python"]
    python_family: Literal["3.14"]
    python_exact: Literal["3.14.7"]
    dependency_manager: Literal["uv"]
    production_runner: Literal["github-hosted-ubuntu-24.04"]
    self_hosted_production_runner: Literal["forbidden"]


class ReadRetry(StrictModel):
    enabled: Literal[True]
    mode: Literal["bounded_read_only"]


class ProviderContract(StrictModel):
    name: Literal["digitalocean"]
    api_base_url: Literal["https://api.digitalocean.com"]
    tls_verify: Literal[True]
    trust_env: Literal[False]
    follow_redirects: Literal[False]
    automatic_mutation_retries: Literal[0]
    read_retry: ReadRetry


class RegistryRelease(StrictModel):
    logical_registry: Literal["eduvijna-registry"]
    repository: Literal["aieos-backend"]
    production_authority: Literal["immutable_digest_only"]


class WorkloadRelease(StrictModel):
    app_semantic_name: str
    workflow_file: str
    github_environment: str
    concurrency_group: str
    secret_key_names: list[str]


class WorkloadsRelease(StrictModel):
    workflow_dispatcher: WorkloadRelease
    temporal_worker: WorkloadRelease

    @model_validator(mode="after")
    def _exact_identities(self) -> WorkloadsRelease:
        d = self.workflow_dispatcher
        w = self.temporal_worker
        if d.app_semantic_name != "aieos-prod-workflow-dispatcher":
            raise ValueError("dispatcher app_semantic_name mismatch")
        if d.workflow_file != "app-platform-release-workflow-dispatcher.yml":
            raise ValueError("dispatcher workflow_file mismatch")
        if d.github_environment != "aieos-prod-workflow-dispatcher":
            raise ValueError("dispatcher github_environment mismatch")
        if d.concurrency_group != "aieos-prod-app-release-workflow-dispatcher":
            raise ValueError("dispatcher concurrency_group mismatch")
        if set(d.secret_key_names) != {
            "AIEOS_DO_APP_RELEASE_TOKEN",
            "AIEOS_WORKFLOW_DISPATCHER_DATABASE_URL",
            "AIEOS_WORKFLOW_DISPATCHER_TEMPORAL_API_KEY",
        }:
            raise ValueError("dispatcher secret_key_names mismatch")
        if w.app_semantic_name != "aieos-prod-temporal-worker":
            raise ValueError("worker app_semantic_name mismatch")
        if w.workflow_file != "app-platform-release-temporal-worker.yml":
            raise ValueError("worker workflow_file mismatch")
        if w.github_environment != "aieos-prod-temporal-worker":
            raise ValueError("worker github_environment mismatch")
        if w.concurrency_group != "aieos-prod-app-release-temporal-worker":
            raise ValueError("worker concurrency_group mismatch")
        if set(w.secret_key_names) != {
            "AIEOS_DO_APP_RELEASE_TOKEN",
            "AIEOS_TEMPORAL_API_KEY",
        }:
            raise ValueError("worker secret_key_names mismatch")
        return self


class ConcurrencyContract(StrictModel):
    cancel_in_progress: Literal[False]
    queue: Literal["single"]
    timeout_minutes: Literal[60]


class MethodPathCreate(StrictModel):
    method: Literal["POST"]
    path: Literal["/v2/apps"]


class MethodPathUpdate(StrictModel):
    method: Literal["PUT"]
    path_template: Literal["/v2/apps/{exact_authorized_app_id}"]


class MethodPathRollback(StrictModel):
    method_sequence: list[Literal["validate", "rollback", "verify", "commit"]]
    notes: str

    @field_validator("method_sequence")
    @classmethod
    def _seq(cls, v: list[str]) -> list[str]:
        if v != ["validate", "rollback", "verify", "commit"]:
            raise ValueError("rollback method_sequence mismatch")
        return v


class MethodPathAuthority(StrictModel):
    CREATE: MethodPathCreate
    UPDATE: MethodPathUpdate
    ROTATE_SECRET: MethodPathUpdate
    ROLLBACK: MethodPathRollback


STEADY_STATE_SCOPES = (
    "app:update",
    "app:read",
    "regions:read",
    "sizes:read",
    "actions:read",
    "project:read",
    "vpc:read",
    "registry:read",
)
BOOTSTRAP_ADDITIONAL_SCOPES = (
    "app:create",
    "project:assign_resource",
)
FORBIDDEN_NORMAL_AUTHORITY = (
    "app:delete",
    "app:access_console",
    "broad_api_write",
    "registry_mutation",
    "vpc_mutation",
    "broad_project_mutation",
)
OPERATIONS_FORBIDDEN = (
    "DELETE",
    "restart",
    "console",
    "arbitrary_method",
    "arbitrary_endpoint",
)


class CredentialsContract(StrictModel):
    pat_logical_classes: list[
        Literal[
            "dispatcher_bootstrap",
            "dispatcher_steady_state",
            "worker_bootstrap",
            "worker_steady_state",
        ]
    ]
    steady_state_scopes: list[str]
    bootstrap_additional_scopes: list[str]
    forbidden_normal_authority: list[str]
    lifetime_days_max: Literal[90]
    rotation_target_begins_days_before_expiry: Literal[30]

    @field_validator("pat_logical_classes")
    @classmethod
    def _pats(cls, v: list[str]) -> list[str]:
        expected = {
            "dispatcher_bootstrap",
            "dispatcher_steady_state",
            "worker_bootstrap",
            "worker_steady_state",
        }
        if set(v) != expected:
            raise ValueError("pat_logical_classes mismatch")
        return v

    @field_validator("steady_state_scopes")
    @classmethod
    def _steady(cls, v: list[str]) -> list[str]:
        if list(v) != list(STEADY_STATE_SCOPES):
            raise ValueError("steady_state_scopes must match exact ADR-050 set")
        return v

    @field_validator("bootstrap_additional_scopes")
    @classmethod
    def _bootstrap(cls, v: list[str]) -> list[str]:
        if list(v) != list(BOOTSTRAP_ADDITIONAL_SCOPES):
            raise ValueError("bootstrap_additional_scopes must match exact ADR-050 set")
        return v

    @field_validator("forbidden_normal_authority")
    @classmethod
    def _forbidden_auth(cls, v: list[str]) -> list[str]:
        if list(v) != list(FORBIDDEN_NORMAL_AUTHORITY):
            raise ValueError("forbidden_normal_authority must match exact ADR-050 set")
        return v


class OperationsContract(StrictModel):
    allowed: list[Literal["CREATE", "UPDATE", "ROTATE_SECRET", "ROLLBACK"]]
    method_path_authority: MethodPathAuthority
    forbidden: list[str]

    @field_validator("allowed")
    @classmethod
    def _allowed(cls, v: list[str]) -> list[str]:
        if set(v) != {"CREATE", "UPDATE", "ROTATE_SECRET", "ROLLBACK"}:
            raise ValueError("allowed operations mismatch")
        return v

    @field_validator("forbidden")
    @classmethod
    def _forbidden_ops(cls, v: list[str]) -> list[str]:
        if list(v) != list(OPERATIONS_FORBIDDEN):
            raise ValueError("operations.forbidden must match exact ADR-050 set")
        return v


def _optional_uuid(v: str | None) -> str | None:
    if v is None:
        return None
    if not UUID_RE.fullmatch(v):
        raise ValueError(f"malformed UUID: {v}")
    # reject nil UUID as fake production id
    if v == "00000000-0000-0000-0000-000000000000":
        raise ValueError("nil UUID is not a valid production physical id")
    UUID(v)
    return v


class PhysicalIds(StrictModel):
    status: Literal["unresolved_pre_bootstrap", "pinned"]
    project_uuid: str | None
    vpc_uuid: str | None
    workflow_dispatcher_app_uuid: str | None
    temporal_worker_app_uuid: str | None

    @field_validator(
        "project_uuid",
        "vpc_uuid",
        "workflow_dispatcher_app_uuid",
        "temporal_worker_app_uuid",
        mode="before",
    )
    @classmethod
    def _uuid(cls, v: object) -> object:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("UUID must be string or null")
        return _optional_uuid(v)

    @model_validator(mode="after")
    def _prebootstrap(self) -> PhysicalIds:
        ids = [
            self.project_uuid,
            self.vpc_uuid,
            self.workflow_dispatcher_app_uuid,
            self.temporal_worker_app_uuid,
        ]
        present = [x for x in ids if x is not None]
        if self.status == "unresolved_pre_bootstrap":
            if present:
                raise ValueError(
                    "unresolved_pre_bootstrap forbids frozen physical UUIDs"
                )
            return self
        # pinned requires all
        if any(x is None for x in ids):
            raise ValueError("pinned physical_ids requires all UUIDs")
        return self


class EvidenceContract(StrictModel):
    artifact_name: Literal["release-receipt.json"]
    retention_days: Literal[90]
    permanent_audit_sor: Literal[False]


class TriggersContract(StrictModel):
    production_automatic: Literal["forbidden"]
    allowed_trigger: Literal["workflow_dispatch_only"]


class OwnershipRelease(StrictModel):
    app_lifecycle: Literal["governed_state_free_deployment_plane"]
    opentofu_digitalocean_app: Literal["rejected"]


class ProductionAuthRelease(StrictModel):
    deployment_authorized: Literal[False]
    live_validation_authorized: Literal[False]
    credential_creation_authorized: Literal[False]
    tv01_authorized: Literal[False]


class ProductionReleasePlaneContract(StrictModel):
    schema_version: Literal["1"]
    architecture_authority: ArchitectureAuthorityRelease
    environment: Literal["production"]
    controller: ControllerPlacement
    runtime: RuntimePin
    provider: ProviderContract
    registry: RegistryRelease
    workloads: WorkloadsRelease
    concurrency: ConcurrencyContract
    operations: OperationsContract
    credentials: CredentialsContract
    physical_ids: PhysicalIds
    evidence: EvidenceContract
    triggers: TriggersContract
    ownership: OwnershipRelease
    production: ProductionAuthRelease
