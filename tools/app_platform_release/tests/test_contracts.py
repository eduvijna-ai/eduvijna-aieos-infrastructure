"""Contract parse / cross-validate adversarial tests."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from aieos_app_release.contracts.load import (
    cross_validate_contracts,
    load_and_cross_validate,
    load_release_plane_contract,
    load_runtime_contract,
)
from aieos_app_release.contracts.release_plane import ProductionReleasePlaneContract
from aieos_app_release.errors import ContractConfigurationError, SourceAuthorityMismatchError
from tests.conftest import RELEASE_CONTRACT, RUNTIME_CONTRACT

SAFE = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def _load_raw(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=SAFE)


def test_valid_frozen_contracts_parse_and_cross_validate() -> None:
    runtime, release = load_and_cross_validate(RUNTIME_CONTRACT, RELEASE_CONTRACT)
    assert runtime.environment == "production"
    assert release.provider.automatic_mutation_retries == 0
    assert release.provider.api_base_url == "https://api.digitalocean.com"


def test_unknown_field_rejected() -> None:
    data = _load_raw(RELEASE_CONTRACT)
    data["unexpected_field"] = True
    with pytest.raises(Exception):
        ProductionReleasePlaneContract.model_validate(data)


def test_wrong_environment_rejected() -> None:
    data = _load_raw(RELEASE_CONTRACT)
    data["environment"] = "staging"
    with pytest.raises(Exception):
        ProductionReleasePlaneContract.model_validate(data)


def test_wrong_app_name_rejected() -> None:
    data = _load_raw(RELEASE_CONTRACT)
    data["workloads"]["workflow_dispatcher"]["app_semantic_name"] = "wrong-name"
    with pytest.raises(Exception):
        ProductionReleasePlaneContract.model_validate(data)


def test_wrong_workflow_identity_rejected() -> None:
    data = _load_raw(RELEASE_CONTRACT)
    data["workloads"]["workflow_dispatcher"]["workflow_file"] = "other.yml"
    with pytest.raises(Exception):
        ProductionReleasePlaneContract.model_validate(data)


def test_wrong_github_environment_rejected() -> None:
    data = _load_raw(RELEASE_CONTRACT)
    data["workloads"]["temporal_worker"]["github_environment"] = "wrong-env"
    with pytest.raises(Exception):
        ProductionReleasePlaneContract.model_validate(data)


def test_wrong_concurrency_group_rejected() -> None:
    data = _load_raw(RELEASE_CONTRACT)
    data["workloads"]["temporal_worker"]["concurrency_group"] = "wrong-group"
    with pytest.raises(Exception):
        ProductionReleasePlaneContract.model_validate(data)


def test_wrong_registry_rejected() -> None:
    data = _load_raw(RELEASE_CONTRACT)
    data["registry"]["logical_registry"] = "other-registry"
    with pytest.raises(Exception):
        ProductionReleasePlaneContract.model_validate(data)


def test_nonzero_mutation_retry_rejected() -> None:
    data = _load_raw(RELEASE_CONTRACT)
    data["provider"]["automatic_mutation_retries"] = 1
    with pytest.raises(Exception):
        ProductionReleasePlaneContract.model_validate(data)


def test_unknown_mutation_operation_rejected() -> None:
    data = _load_raw(RELEASE_CONTRACT)
    data["operations"]["allowed"] = ["CREATE", "UPDATE", "ROTATE_SECRET", "ROLLBACK", "DELETE"]
    with pytest.raises(Exception):
        ProductionReleasePlaneContract.model_validate(data)


def test_unresolved_physical_ids_accepted() -> None:
    release = load_release_plane_contract(RELEASE_CONTRACT)
    assert release.physical_ids.status == "unresolved_pre_bootstrap"
    assert release.physical_ids.project_uuid is None


def test_malformed_physical_uuid_rejected() -> None:
    data = _load_raw(RELEASE_CONTRACT)
    data["physical_ids"] = {
        "status": "pinned",
        "project_uuid": "not-a-uuid",
        "vpc_uuid": "33333333-3333-4333-8333-333333333333",
        "workflow_dispatcher_app_uuid": "11111111-1111-4111-8111-111111111111",
        "temporal_worker_app_uuid": "44444444-4444-4444-8444-444444444444",
    }
    with pytest.raises(Exception):
        ProductionReleasePlaneContract.model_validate(data)


def test_nil_uuid_rejected() -> None:
    data = _load_raw(RELEASE_CONTRACT)
    data["physical_ids"] = {
        "status": "pinned",
        "project_uuid": "00000000-0000-0000-0000-000000000000",
        "vpc_uuid": "33333333-3333-4333-8333-333333333333",
        "workflow_dispatcher_app_uuid": "11111111-1111-4111-8111-111111111111",
        "temporal_worker_app_uuid": "44444444-4444-4444-8444-444444444444",
    }
    with pytest.raises(Exception):
        ProductionReleasePlaneContract.model_validate(data)


def test_runtime_release_plane_disagreement_rejected() -> None:
    runtime = load_runtime_contract(RUNTIME_CONTRACT)
    release = load_release_plane_contract(RELEASE_CONTRACT)
    # mutate a copy via model_copy
    bad = release.model_copy(
        update={
            "registry": release.registry.model_copy(update={"repository": "wrong-repo"})  # type: ignore[arg-type]
        }
    )
    # repository is Literal — construct via raw validate bypass using object.__setattr__ path
    data = release.model_dump()
    data["registry"]["repository"] = "aieos-backend"  # same — force mismatch via app name
    data["workloads"]["workflow_dispatcher"]["app_semantic_name"] = "aieos-prod-workflow-dispatcher"
    # Use cross_validate by temporarily patching runtime app name via dump/load
    rt = runtime.model_dump()
    rt["workloads"]["workflow_dispatcher"]["app_name"] = "mismatch-app"
    from aieos_app_release.contracts.runtime import ProductionWorkflowRuntimeContract

    # model won't allow mismatch-app — so call cross_validate with monkeypatched attributes
    class _R:
        environment = runtime.environment
        registry = runtime.registry
        ownership = runtime.ownership
        production = runtime.production

        class workloads:
            class workflow_dispatcher:
                app_name = "mismatch-app"

            class temporal_worker:
                app_name = runtime.workloads.temporal_worker.app_name

    with pytest.raises(SourceAuthorityMismatchError):
        cross_validate_contracts(_R(), release)  # type: ignore[arg-type]


def test_exact_scope_and_forbidden_sets() -> None:
    data = _load_raw(RELEASE_CONTRACT)
    # missing member
    missing = copy.deepcopy(data)
    missing["credentials"]["steady_state_scopes"] = [
        s for s in missing["credentials"]["steady_state_scopes"] if s != "vpc:read"
    ]
    with pytest.raises(Exception):
        ProductionReleasePlaneContract.model_validate(missing)
    # extra member
    extra = copy.deepcopy(data)
    extra["credentials"]["steady_state_scopes"] = list(extra["credentials"]["steady_state_scopes"]) + [
        "app:delete"
    ]
    with pytest.raises(Exception):
        ProductionReleasePlaneContract.model_validate(extra)
    # dangerous bootstrap authority
    danger = copy.deepcopy(data)
    danger["credentials"]["bootstrap_additional_scopes"] = ["app:create", "app:delete"]
    with pytest.raises(Exception):
        ProductionReleasePlaneContract.model_validate(danger)
    # forbidden ops exact
    bad_forbid = copy.deepcopy(data)
    bad_forbid["operations"]["forbidden"] = list(bad_forbid["operations"]["forbidden"]) + ["FORCE"]
    with pytest.raises(Exception):
        ProductionReleasePlaneContract.model_validate(bad_forbid)
    # missing forbidden member
    miss_forbid = copy.deepcopy(data)
    miss_forbid["operations"]["forbidden"] = [
        x for x in miss_forbid["operations"]["forbidden"] if x != "DELETE"
    ]
    with pytest.raises(Exception):
        ProductionReleasePlaneContract.model_validate(miss_forbid)


def test_self_hosted_forbidden_in_contract() -> None:
    release = load_release_plane_contract(RELEASE_CONTRACT)
    assert release.runtime.self_hosted_production_runner == "forbidden"
    assert release.triggers.production_automatic == "forbidden"


def test_load_missing_file_fails() -> None:
    with pytest.raises(ContractConfigurationError):
        load_release_plane_contract(Path("/no/such/release-plane.yaml"))
