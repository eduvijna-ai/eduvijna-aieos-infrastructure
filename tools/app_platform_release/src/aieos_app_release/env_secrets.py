"""Environment secret acquisition with immediate process-env removal."""

from __future__ import annotations

import os
from enum import Enum
from typing import Mapping

from aieos_app_release.errors import SecretBoundaryError
from aieos_app_release.secrets import SecretValue

DISPATCHER_SECRET_KEYS = frozenset(
    {
        "AIEOS_DO_APP_RELEASE_TOKEN",
        "AIEOS_WORKFLOW_DISPATCHER_DATABASE_URL",
        "AIEOS_WORKFLOW_DISPATCHER_TEMPORAL_API_KEY",
    }
)
WORKER_SECRET_KEYS = frozenset(
    {
        "AIEOS_DO_APP_RELEASE_TOKEN",
        "AIEOS_TEMPORAL_API_KEY",
    }
)
DISPATCHER_ONLY = DISPATCHER_SECRET_KEYS - {"AIEOS_DO_APP_RELEASE_TOKEN"}
WORKER_ONLY = WORKER_SECRET_KEYS - {"AIEOS_DO_APP_RELEASE_TOKEN"}


class WorkloadSecretFamily(str, Enum):
    WORKFLOW_DISPATCHER = "workflow_dispatcher"
    TEMPORAL_WORKER = "temporal_worker"


def expected_keys(family: WorkloadSecretFamily) -> frozenset[str]:
    if family is WorkloadSecretFamily.WORKFLOW_DISPATCHER:
        return DISPATCHER_SECRET_KEYS
    return WORKER_SECRET_KEYS


def acquire_workload_secrets(
    family: WorkloadSecretFamily,
    environ: dict[str, str] | None = None,
) -> dict[str, SecretValue]:
    """Read exact secret family, wrap as SecretValue, pop from process environment."""
    env = environ if environ is not None else os.environ
    required = expected_keys(family)

    # Cross-workload contamination checks
    if family is WorkloadSecretFamily.WORKFLOW_DISPATCHER:
        for key in WORKER_ONLY:
            if key in env and env.get(key):
                raise SecretBoundaryError(
                    "dispatcher family contaminated by worker-only secret key",
                    detail=key,
                )
    else:
        for key in DISPATCHER_ONLY:
            if key in env and env.get(key):
                raise SecretBoundaryError(
                    "worker family contaminated by dispatcher-only secret key",
                    detail=key,
                )

    missing = [k for k in sorted(required) if not env.get(k)]
    if missing:
        raise SecretBoundaryError(
            "missing required secret keys",
            detail=",".join(missing),
        )

    acquired: dict[str, SecretValue] = {}
    for key in sorted(required):
        value = env[key]
        acquired[key] = SecretValue(value)
        # remove immediately from process environment
        try:
            del env[key]
        except KeyError:
            pass
        if environ is None:
            os.environ.pop(key, None)

    return acquired


def assert_env_cleared(keys: Mapping[str, object], environ: Mapping[str, str] | None = None) -> None:
    env = environ if environ is not None else os.environ
    for key in keys:
        if key in env:
            raise SecretBoundaryError("secret key still present in environment", detail=key)
