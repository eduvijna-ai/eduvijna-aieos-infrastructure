"""Stale-write fence, targeting, OCI tests."""

from __future__ import annotations

import pytest

from aieos_app_release.errors import OciDigestError, StaleWriteError, TargetCardinalityError
from aieos_app_release.fence import (
    FenceResult,
    LiveAppSnapshot,
    assert_fence_eligible,
    evaluate_stale_write_fence,
    normalize_allowed_provider_defaults,
)
from aieos_app_release.oci import validate_oci_digest
from aieos_app_release.targeting import (
    SteadyStatePhysicalIds,
    assert_bootstrap_create_cardinality,
    assert_steady_state_identity,
)
from tests.conftest import DUMMY_APP_ID, DUMMY_DIGEST, DUMMY_PROJECT, DUMMY_VPC


def _snap(**kwargs) -> LiveAppSnapshot:
    base = dict(
        app_id=DUMMY_APP_ID,
        app_name="aieos-prod-workflow-dispatcher",
        project_uuid=DUMMY_PROJECT,
        vpc_uuid=DUMMY_VPC,
        updated_at="2026-08-24T00:00:00Z",
        managed_projection={"name": "aieos-prod-workflow-dispatcher", "region": "blr"},
        secret_key_set=frozenset({"AIEOS_TEMPORAL_API_KEY"}),
        allowed_provider_defaults=frozenset({"default_ingress_rule"}),
    )
    base.update(kwargs)
    return LiveAppSnapshot(**base)


def test_equal_double_read_eligible() -> None:
    a = _snap()
    b = _snap()
    assert evaluate_stale_write_fence(a, b) is FenceResult.ELIGIBLE
    assert_fence_eligible(a, b)


def test_allowed_provider_default_only_not_stale() -> None:
    a = _snap(managed_projection={"name": "x", "region": "blr"})
    b = _snap(
        managed_projection={"name": "x", "region": "blr", "default_ingress_rule": "provider-added"},
        updated_at="2026-08-24T01:00:00Z",
    )
    assert "default_ingress_rule" not in normalize_allowed_provider_defaults(
        b.managed_projection, b.allowed_provider_defaults
    )
    assert evaluate_stale_write_fence(a, b) is FenceResult.ELIGIBLE


def test_managed_non_secret_difference_blocks() -> None:
    a = _snap()
    b = _snap(managed_projection={"name": "aieos-prod-workflow-dispatcher", "region": "nyc"})
    assert evaluate_stale_write_fence(a, b) is FenceResult.STALE_WRITE
    with pytest.raises(StaleWriteError):
        assert_fence_eligible(a, b)


def test_secret_key_set_change_blocks() -> None:
    a = _snap()
    b = _snap(secret_key_set=frozenset({"AIEOS_TEMPORAL_API_KEY", "EXTRA"}))
    assert evaluate_stale_write_fence(a, b) is FenceResult.SECRET_KEY_SET_CHANGED


def test_secret_ciphertext_only_non_blocking() -> None:
    a = _snap(
        managed_projection={
            "name": "x",
            "env": {"AIEOS_TEMPORAL_API_KEY": "EV[AAAA]"},
        }
    )
    b = _snap(
        managed_projection={
            "name": "x",
            "env": {"AIEOS_TEMPORAL_API_KEY": "EV[BBBB]"},
        },
        updated_at="2026-08-24T02:00:00Z",
    )
    assert evaluate_stale_write_fence(a, b) is FenceResult.ELIGIBLE


def test_changed_app_identity_and_physical_ids() -> None:
    a = _snap()
    assert (
        evaluate_stale_write_fence(a, _snap(app_id="55555555-5555-4555-8555-555555555555"))
        is FenceResult.IDENTITY_CHANGED
    )
    assert (
        evaluate_stale_write_fence(a, _snap(vpc_uuid="66666666-6666-4666-8666-666666666666"))
        is FenceResult.PHYSICAL_ID_CHANGED
    )


def test_bootstrap_cardinality() -> None:
    assert_bootstrap_create_cardinality(0)
    with pytest.raises(TargetCardinalityError):
        assert_bootstrap_create_cardinality(1)
    with pytest.raises(TargetCardinalityError):
        assert_bootstrap_create_cardinality(2)


def test_steady_state_physical_ids() -> None:
    auth = SteadyStatePhysicalIds(
        app_semantic_name="aieos-prod-temporal-worker",
        app_uuid=DUMMY_APP_ID,
        project_uuid=DUMMY_PROJECT,
        vpc_uuid=DUMMY_VPC,
    )
    assert_steady_state_identity(auth, auth)
    bad = SteadyStatePhysicalIds(
        app_semantic_name="aieos-prod-temporal-worker",
        app_uuid="55555555-5555-4555-8555-555555555555",
        project_uuid=DUMMY_PROJECT,
        vpc_uuid=DUMMY_VPC,
    )
    with pytest.raises(TargetCardinalityError):
        assert_steady_state_identity(bad, auth)


def test_oci_digest_rules() -> None:
    assert validate_oci_digest(DUMMY_DIGEST) == DUMMY_DIGEST
    for bad in ("latest", "v1.2.3", "sha256:ABC", "sha256:abcd", "", "SHA256:" + "a" * 64):
        with pytest.raises(OciDigestError):
            validate_oci_digest(bad)
    with pytest.raises(OciDigestError):
        validate_oci_digest("sha256:" + ("A" * 64))
