"""Double-read stale-write fence (ADR-AIEOS-049)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from aieos_app_release.errors import StaleWriteError
from aieos_app_release.fingerprint import fingerprint_managed_spec
from aieos_app_release.secrets import walk_replace_secrets


class FenceResult(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    STALE_WRITE = "STALE_WRITE"
    IDENTITY_CHANGED = "IDENTITY_CHANGED"
    PHYSICAL_ID_CHANGED = "PHYSICAL_ID_CHANGED"
    SECRET_KEY_SET_CHANGED = "SECRET_KEY_SET_CHANGED"


@dataclass(frozen=True, slots=True)
class LiveAppSnapshot:
    app_id: str
    app_name: str
    project_uuid: str
    vpc_uuid: str
    updated_at: str
    managed_projection: dict[str, Any]
    secret_key_set: frozenset[str]
    allowed_provider_defaults: frozenset[str] = frozenset()


def _nonsecret_fingerprint(snap: LiveAppSnapshot) -> str:
    return fingerprint_managed_spec(snap.managed_projection)


def evaluate_stale_write_fence(
    read1: LiveAppSnapshot,
    read2: LiveAppSnapshot,
) -> FenceResult:
    if read1.app_id != read2.app_id or read1.app_name != read2.app_name:
        return FenceResult.IDENTITY_CHANGED
    if read1.project_uuid != read2.project_uuid or read1.vpc_uuid != read2.vpc_uuid:
        return FenceResult.PHYSICAL_ID_CHANGED
    if read1.secret_key_set != read2.secret_key_set:
        return FenceResult.SECRET_KEY_SET_CHANGED
    if read1.updated_at != read2.updated_at:
        return FenceResult.STALE_WRITE
    if _nonsecret_fingerprint(read1) != _nonsecret_fingerprint(read2):
        # Ignore pure ciphertext / secret-value differences already handled by fingerprint
        return FenceResult.STALE_WRITE
    return FenceResult.ELIGIBLE


def assert_fence_eligible(read1: LiveAppSnapshot, read2: LiveAppSnapshot) -> None:
    result = evaluate_stale_write_fence(read1, read2)
    if result is not FenceResult.ELIGIBLE:
        raise StaleWriteError("double-read stale-write fence blocked mutation", detail=result.value)


def classify_provider_default_keys(
    observed_extra_keys: set[str],
    allowed_defaults: set[str],
) -> set[str]:
    """Return blocking unmanaged keys (provider defaults allowed are removed)."""
    return observed_extra_keys - allowed_defaults


def managed_projection_without_secrets(projection: dict[str, Any]) -> dict[str, Any]:
    return walk_replace_secrets(projection)
