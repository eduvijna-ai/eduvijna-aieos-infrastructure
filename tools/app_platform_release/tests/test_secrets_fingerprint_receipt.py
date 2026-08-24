"""Secret, fingerprint, receipt tests."""

from __future__ import annotations

import json

import pytest

from aieos_app_release.env_secrets import WorkloadSecretFamily, acquire_workload_secrets
from aieos_app_release.errors import ReceiptPolicyError, SecretBoundaryError
from aieos_app_release.fingerprint import canonicalize_managed_projection, fingerprint_managed_spec
from aieos_app_release.receipt import StrictReceipt, parse_receipt, serialize_receipt
from aieos_app_release.secrets import REDACTED, SECRET_SENTINEL, SecretValue
from tests.conftest import DUMMY_APP_ID, DUMMY_DIGEST, DUMMY_PROJECT, DUMMY_SHA, DUMMY_VPC


def test_secret_str_repr_redacted() -> None:
    s = SecretValue("super-secret-value")
    assert str(s) == REDACTED
    assert REDACTED in repr(s)
    assert "super-secret-value" not in str(s)
    assert "super-secret-value" not in repr(s)


def test_secret_in_exception_redacted() -> None:
    s = SecretValue("EV[CIPHERTEXT]")
    try:
        raise RuntimeError(f"failed with {s}")
    except RuntimeError as exc:
        assert "EV[" not in str(exc)
        assert REDACTED in str(exc)


def test_env_pop_and_cross_workload_isolation() -> None:
    env = {
        "AIEOS_DO_APP_RELEASE_TOKEN": "pat-dummy",
        "AIEOS_WORKFLOW_DISPATCHER_DATABASE_URL": "postgresql://u:p@h/db",
        "AIEOS_WORKFLOW_DISPATCHER_TEMPORAL_API_KEY": "tok-dummy",
        "AIEOS_TEMPORAL_API_KEY": "worker-should-contaminate",
    }
    with pytest.raises(SecretBoundaryError):
        acquire_workload_secrets(WorkloadSecretFamily.WORKFLOW_DISPATCHER, env)

    env2 = {
        "AIEOS_DO_APP_RELEASE_TOKEN": "pat-dummy",
        "AIEOS_WORKFLOW_DISPATCHER_DATABASE_URL": "postgresql://u:p@h/db",
        "AIEOS_WORKFLOW_DISPATCHER_TEMPORAL_API_KEY": "tok-dummy",
    }
    got = acquire_workload_secrets(WorkloadSecretFamily.WORKFLOW_DISPATCHER, env2)
    assert set(got) == {
        "AIEOS_DO_APP_RELEASE_TOKEN",
        "AIEOS_WORKFLOW_DISPATCHER_DATABASE_URL",
        "AIEOS_WORKFLOW_DISPATCHER_TEMPORAL_API_KEY",
    }
    for k in got:
        assert k not in env2
        assert str(got[k]) == REDACTED

    env3 = {
        "AIEOS_DO_APP_RELEASE_TOKEN": "pat-dummy",
        "AIEOS_TEMPORAL_API_KEY": "worker-key",
        "AIEOS_WORKFLOW_DISPATCHER_DATABASE_URL": "should-contaminate-worker",
    }
    with pytest.raises(SecretBoundaryError):
        acquire_workload_secrets(WorkloadSecretFamily.TEMPORAL_WORKER, env3)


def test_fingerprint_deterministic_and_secret_insensitive() -> None:
    a = {
        "name": "app",
        "region": "blr",
        "env": {"AIEOS_TEMPORAL_API_KEY": SecretValue("plain-1"), "LABEL": "x"},
    }
    b = {
        "region": "blr",
        "name": "app",
        "env": {"LABEL": "x", "AIEOS_TEMPORAL_API_KEY": SecretValue("plain-2")},
    }
    c = {
        "name": "app",
        "region": "blr",
        "env": {"AIEOS_TEMPORAL_API_KEY": "EV[AAAA]", "LABEL": "x"},
    }
    fa = fingerprint_managed_spec(a)
    fb = fingerprint_managed_spec(b)
    fc = fingerprint_managed_spec(c)
    assert fa == fb == fc
    canon = canonicalize_managed_projection(a)
    assert b"plain-1" not in canon
    assert b"EV[" not in canon
    assert SECRET_SENTINEL.encode() in canon

    different_value = fingerprint_managed_spec(
        {"name": "app", "region": "nyc", "env": {"AIEOS_TEMPORAL_API_KEY": SecretValue("x"), "LABEL": "x"}}
    )
    assert different_value != fa

    different_keys = fingerprint_managed_spec(
        {
            "name": "app",
            "region": "blr",
            "env": {
                "AIEOS_TEMPORAL_API_KEY": SecretValue("x"),
                "EXTRA_SECRET": SecretValue("y"),
                "LABEL": "x",
            },
        }
    )
    assert different_keys != fa


def _receipt_kwargs(**overrides):
    base = dict(
        app_semantic_name="aieos-prod-workflow-dispatcher",
        app_uuid=DUMMY_APP_ID,
        project_uuid=DUMMY_PROJECT,
        vpc_uuid=DUMMY_VPC,
        architecture_sha=DUMMY_SHA,
        infrastructure_sha=DUMMY_SHA,
        backend_sha=DUMMY_SHA,
        oci_digest=DUMMY_DIGEST,
        release_identity="rel-1",
        github_run_id="123",
        github_run_attempt="1",
        concurrency_group="aieos-prod-app-release-workflow-dispatcher",
        managed_spec_fingerprint=DUMMY_DIGEST,
        secret_key_names=["AIEOS_DO_APP_RELEASE_TOKEN"],
    )
    base.update(overrides)
    return base


def test_receipt_approved_fields_deterministic() -> None:
    r1 = StrictReceipt(**_receipt_kwargs())
    r2 = StrictReceipt(**_receipt_kwargs())
    b1 = serialize_receipt(r1)
    b2 = serialize_receipt(r2)
    assert b1 == b2
    payload = json.loads(b1)
    assert payload["receipt_sha256"].startswith("sha256:")
    assert "EV[" not in b1.decode()


def test_receipt_rejects_secrets_and_forbidden() -> None:
    with pytest.raises(ReceiptPolicyError):
        parse_receipt({**_receipt_kwargs(), "raw_appspec": {"name": "x"}})
    with pytest.raises(ReceiptPolicyError):
        parse_receipt({**_receipt_kwargs(), "authorization_header": "Bearer abc"})
    with pytest.raises(ReceiptPolicyError):
        parse_receipt({**_receipt_kwargs(), "secret_hash": "abc"})
    with pytest.raises((ReceiptPolicyError, Exception)):
        StrictReceipt(**_receipt_kwargs(generation_labels={"x": "EV[ABCDEFGH]"}))
    with pytest.raises((ReceiptPolicyError, Exception)):
        StrictReceipt(
            **_receipt_kwargs(
                generation_labels={"db": "postgresql://u:p@host/db"},
            )
        )
