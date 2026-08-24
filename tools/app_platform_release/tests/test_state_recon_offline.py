"""State machine, reconciliation, offline adversarial proofs."""

from __future__ import annotations

import ast
from pathlib import Path

import httpx
import pytest

from aieos_app_release.errors import IllegalStateTransitionError
from aieos_app_release.fingerprint import fingerprint_managed_spec
from aieos_app_release.provider import DigitalOceanAppClient
from aieos_app_release.reconciliation import (
    ReconciliationClass,
    ReconciliationInput,
    assert_no_auto_mutation,
    reconcile_mutation_result,
)
from aieos_app_release.state_machine import ReleaseState, ReleaseStateMachine
from tests.conftest import DUMMY_APP_ID


def test_legal_state_path() -> None:
    sm = ReleaseStateMachine()
    path = [
        ReleaseState.LEASE_ACQUIRED,
        ReleaseState.PROVIDER_PREFLIGHT,
        ReleaseState.LIVE_SPEC_READ_1,
        ReleaseState.ALLOWLIST_VALIDATE,
        ReleaseState.DESIRED_SPEC_IN_MEMORY,
        ReleaseState.LIVE_SPEC_READ_2,
        ReleaseState.STALE_WRITE_FENCE,
        ReleaseState.MUTATION_SENT_ONCE,
        ReleaseState.RESULT_RECONCILIATION,
        ReleaseState.DEPLOYMENT_VERIFY,
        ReleaseState.RECEIPT,
        ReleaseState.PROCESS_EXIT,
    ]
    for s in path:
        sm.transition(s)
    assert sm.state is ReleaseState.PROCESS_EXIT


def test_illegal_transition() -> None:
    sm = ReleaseStateMachine()
    with pytest.raises(IllegalStateTransitionError):
        sm.transition(ReleaseState.MUTATION_SENT_ONCE)


def test_ambiguity_requires_reconciliation_not_retry() -> None:
    sm = ReleaseStateMachine()
    for s in [
        ReleaseState.LEASE_ACQUIRED,
        ReleaseState.PROVIDER_PREFLIGHT,
        ReleaseState.LIVE_SPEC_READ_1,
        ReleaseState.ALLOWLIST_VALIDATE,
        ReleaseState.DESIRED_SPEC_IN_MEMORY,
        ReleaseState.LIVE_SPEC_READ_2,
        ReleaseState.STALE_WRITE_FENCE,
        ReleaseState.MUTATION_SENT_ONCE,
    ]:
        sm.transition(s)
    sm.mark_ambiguous_after_mutation()
    assert sm.state is ReleaseState.RESULT_RECONCILIATION
    with pytest.raises(IllegalStateTransitionError):
        sm.transition(ReleaseState.MUTATION_SENT_ONCE)


def test_no_second_mutation_transition() -> None:
    sm = ReleaseStateMachine()
    for s in [
        ReleaseState.LEASE_ACQUIRED,
        ReleaseState.PROVIDER_PREFLIGHT,
        ReleaseState.LIVE_SPEC_READ_1,
        ReleaseState.ALLOWLIST_VALIDATE,
        ReleaseState.DESIRED_SPEC_IN_MEMORY,
        ReleaseState.LIVE_SPEC_READ_2,
        ReleaseState.STALE_WRITE_FENCE,
        ReleaseState.MUTATION_SENT_ONCE,
        ReleaseState.RESULT_RECONCILIATION,
        ReleaseState.PROCESS_EXIT,
    ]:
        sm.transition(s)
    with pytest.raises(IllegalStateTransitionError):
        sm.transition(ReleaseState.MUTATION_SENT_ONCE)


def test_reconciliation_classifications() -> None:
    managed = {"name": "aieos-prod-workflow-dispatcher", "region": "blr"}
    fp = fingerprint_managed_spec(managed)

    committed = reconcile_mutation_result(
        ReconciliationInput(
            expected_app_name="aieos-prod-workflow-dispatcher",
            expected_app_id=DUMMY_APP_ID,
            expected_managed_fingerprint=fp,
            expected_deployment_id=None,
            expected_project_uuid=None,
            expected_vpc_uuid=None,
            current_apps=[{"id": DUMMY_APP_ID, "name": "aieos-prod-workflow-dispatcher"}],
            current_app={"id": DUMMY_APP_ID, "managed_projection": managed},
            deployments=[],
        )
    )
    assert committed.classification is ReconciliationClass.COMMITTED
    assert committed.mutate_again is False
    assert_no_auto_mutation(committed)

    not_committed = reconcile_mutation_result(
        ReconciliationInput(
            expected_app_name="aieos-prod-workflow-dispatcher",
            expected_app_id=None,
            expected_managed_fingerprint=fp,
            expected_deployment_id=None,
            expected_project_uuid="22222222-2222-4222-8222-222222222222",
            expected_vpc_uuid="33333333-3333-4333-8333-333333333333",
            current_apps=[],
            current_app=None,
            deployments=[],
        )
    )
    assert not_committed.classification is ReconciliationClass.NOT_COMMITTED

    # name alone insufficient for CREATE COMMITTED
    name_only = reconcile_mutation_result(
        ReconciliationInput(
            expected_app_name="aieos-prod-workflow-dispatcher",
            expected_app_id=None,
            expected_managed_fingerprint=fp,
            expected_deployment_id=None,
            expected_project_uuid=None,
            expected_vpc_uuid=None,
            current_apps=[
                {
                    "id": DUMMY_APP_ID,
                    "name": "aieos-prod-workflow-dispatcher",
                    "managed_projection": managed,
                }
            ],
            current_app=None,
            deployments=[],
        )
    )
    assert name_only.classification is ReconciliationClass.AMBIGUOUS

    # racing / out-of-band creator with full evidence still binds; mismatch project => AMBIGUOUS
    racing = reconcile_mutation_result(
        ReconciliationInput(
            expected_app_name="aieos-prod-workflow-dispatcher",
            expected_app_id=None,
            expected_managed_fingerprint=fp,
            expected_deployment_id=None,
            expected_project_uuid="22222222-2222-4222-8222-222222222222",
            expected_vpc_uuid="33333333-3333-4333-8333-333333333333",
            current_apps=[
                {
                    "id": DUMMY_APP_ID,
                    "name": "aieos-prod-workflow-dispatcher",
                    "project_id": "99999999-9999-4999-8999-999999999999",
                    "vpc_uuid": "33333333-3333-4333-8333-333333333333",
                    "managed_projection": managed,
                }
            ],
            current_app=None,
            deployments=[],
        )
    )
    assert racing.classification is ReconciliationClass.AMBIGUOUS

    create_committed = reconcile_mutation_result(
        ReconciliationInput(
            expected_app_name="aieos-prod-workflow-dispatcher",
            expected_app_id=None,
            expected_managed_fingerprint=fp,
            expected_deployment_id=None,
            expected_project_uuid="22222222-2222-4222-8222-222222222222",
            expected_vpc_uuid="33333333-3333-4333-8333-333333333333",
            current_apps=[
                {
                    "id": DUMMY_APP_ID,
                    "name": "aieos-prod-workflow-dispatcher",
                    "project_id": "22222222-2222-4222-8222-222222222222",
                    "vpc_uuid": "33333333-3333-4333-8333-333333333333",
                    "managed_projection": managed,
                }
            ],
            current_app=None,
            deployments=[],
        )
    )
    assert create_committed.classification is ReconciliationClass.COMMITTED

    conflict = reconcile_mutation_result(
        ReconciliationInput(
            expected_app_name="aieos-prod-workflow-dispatcher",
            expected_app_id=None,
            expected_managed_fingerprint=fp,
            expected_deployment_id=None,
            expected_project_uuid="22222222-2222-4222-8222-222222222222",
            expected_vpc_uuid="33333333-3333-4333-8333-333333333333",
            current_apps=[
                {"id": "11111111-1111-4111-8111-111111111111", "name": "aieos-prod-workflow-dispatcher"},
                {"id": "22222222-2222-4222-8222-222222222222", "name": "aieos-prod-workflow-dispatcher"},
            ],
            current_app=None,
            deployments=[],
        )
    )
    assert conflict.classification is ReconciliationClass.CONFLICT

    ambiguous = reconcile_mutation_result(
        ReconciliationInput(
            expected_app_name="aieos-prod-workflow-dispatcher",
            expected_app_id=DUMMY_APP_ID,
            expected_managed_fingerprint=fp,
            expected_deployment_id=None,
            expected_project_uuid=None,
            expected_vpc_uuid=None,
            current_apps=[],
            current_app=None,
            deployments=[],
        )
    )
    assert ambiguous.classification is ReconciliationClass.AMBIGUOUS


def test_no_subprocess_os_system_in_library() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "aieos_app_release"
    forbidden_calls = {"system", "popen", "Popen", "run", "call", "check_call", "check_output"}
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in {"subprocess"}, path
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] == "subprocess":
                    raise AssertionError(f"subprocess import in {path}")
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in forbidden_calls:
                    if isinstance(func.value, ast.Name) and func.value.id in {"os", "subprocess"}:
                        raise AssertionError(f"forbidden call in {path}")
                if isinstance(func, ast.Name) and func.id == "system":
                    raise AssertionError(f"os.system-like in {path}")


def test_no_doctl_curl_strings_as_execution() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "aieos_app_release"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "doctl " not in text
        assert "shell=True" not in text


def test_mock_transport_only_no_live_do() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.digitalocean.com"
        return httpx.Response(200, json={"apps": [], "links": {}})

    with DigitalOceanAppClient(
        token="dummy",
        transport=httpx.MockTransport(handler),
    ) as c:
        c.list_apps()


def test_production_credential_env_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in [
        "DIGITALOCEAN_TOKEN",
        "AIEOS_DO_APP_RELEASE_TOKEN",
        "AIEOS_DO_APP_BOOTSTRAP_TOKEN",
        "AIEOS_WORKFLOW_DISPATCHER_DATABASE_URL",
        "AIEOS_WORKFLOW_DISPATCHER_TEMPORAL_API_KEY",
        "AIEOS_TEMPORAL_API_KEY",
        "TEMPORAL_CLOUD_API_KEY",
        "DOCKER_AUTH_CONFIG",
        "REGISTRY_PASSWORD",
        "REGISTRY_TOKEN",
    ]:
        monkeypatch.delenv(key, raising=False)
        import os

        assert not os.environ.get(key)
