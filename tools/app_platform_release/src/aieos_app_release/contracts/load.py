"""Load and cross-validate governed App Platform contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from aieos_app_release.contracts.release_plane import ProductionReleasePlaneContract
from aieos_app_release.contracts.runtime import ProductionWorkflowRuntimeContract
from aieos_app_release.errors import ContractConfigurationError, SourceAuthorityMismatchError

SAFE_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def _repo_root_from_here() -> Path:
    # tools/app_platform_release/src/aieos_app_release/contracts/load.py → repo root
    return Path(__file__).resolve().parents[5]


def default_runtime_contract_path() -> Path:
    return _repo_root_from_here() / "contracts" / "app-platform" / "production-workflow-runtime.yaml"


def default_release_plane_contract_path() -> Path:
    return _repo_root_from_here() / "contracts" / "app-platform" / "production-release-plane.yaml"


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractConfigurationError(f"cannot read contract: {path}") from exc
    try:
        data = yaml.load(raw, Loader=SAFE_LOADER)
    except yaml.YAMLError as exc:
        raise ContractConfigurationError(f"invalid YAML: {path}") from exc
    if not isinstance(data, dict):
        raise ContractConfigurationError(f"contract root must be mapping: {path}")
    return data


def load_runtime_contract(path: Path | None = None) -> ProductionWorkflowRuntimeContract:
    p = path or default_runtime_contract_path()
    data = load_yaml_mapping(p)
    try:
        return ProductionWorkflowRuntimeContract.model_validate(data)
    except Exception as exc:
        raise ContractConfigurationError(f"runtime contract invalid: {exc}") from exc


def load_release_plane_contract(path: Path | None = None) -> ProductionReleasePlaneContract:
    p = path or default_release_plane_contract_path()
    data = load_yaml_mapping(p)
    try:
        return ProductionReleasePlaneContract.model_validate(data)
    except Exception as exc:
        raise ContractConfigurationError(f"release-plane contract invalid: {exc}") from exc


def cross_validate_contracts(
    runtime: ProductionWorkflowRuntimeContract,
    release: ProductionReleasePlaneContract,
) -> None:
    """Fail closed on disagreement between runtime and release-plane contracts."""
    mismatches: list[str] = []

    if runtime.environment != release.environment:
        mismatches.append("environment")
    if runtime.registry.logical_registry != release.registry.logical_registry:
        mismatches.append("registry.logical_registry")
    if runtime.registry.repository != release.registry.repository:
        mismatches.append("registry.repository")
    if runtime.registry.production_authority != release.registry.production_authority:
        mismatches.append("registry.production_authority")
    if (
        runtime.workloads.workflow_dispatcher.app_name
        != release.workloads.workflow_dispatcher.app_semantic_name
    ):
        mismatches.append("workflow_dispatcher.app_name")
    if (
        runtime.workloads.temporal_worker.app_name
        != release.workloads.temporal_worker.app_semantic_name
    ):
        mismatches.append("temporal_worker.app_name")
    if runtime.ownership.app_lifecycle != release.ownership.app_lifecycle:
        mismatches.append("ownership.app_lifecycle")
    if (
        runtime.ownership.opentofu_digitalocean_app
        != release.ownership.opentofu_digitalocean_app
    ):
        mismatches.append("ownership.opentofu_digitalocean_app")
    if runtime.production.deployment_authorized != release.production.deployment_authorized:
        mismatches.append("production.deployment_authorized")
    if release.provider.automatic_mutation_retries != 0:
        mismatches.append("provider.automatic_mutation_retries")
    if release.runtime.self_hosted_production_runner != "forbidden":
        mismatches.append("runtime.self_hosted_production_runner")
    if release.triggers.production_automatic != "forbidden":
        mismatches.append("triggers.production_automatic")

    if mismatches:
        raise SourceAuthorityMismatchError(
            "runtime/release-plane contract disagreement",
            detail=",".join(mismatches),
        )


def load_and_cross_validate(
    runtime_path: Path | None = None,
    release_path: Path | None = None,
) -> tuple[ProductionWorkflowRuntimeContract, ProductionReleasePlaneContract]:
    runtime = load_runtime_contract(runtime_path)
    release = load_release_plane_contract(release_path)
    cross_validate_contracts(runtime, release)
    return runtime, release
