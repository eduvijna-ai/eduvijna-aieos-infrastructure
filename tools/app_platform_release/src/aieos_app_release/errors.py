"""Typed sanitized errors for the App Platform release controller."""

from __future__ import annotations

from typing import Any


class ReleaseControllerError(Exception):
    """Base sanitized controller error."""

    code: str = "RELEASE_CONTROLLER_ERROR"

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        self.message = message
        self.detail = detail
        super().__init__(message)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"


class ContractConfigurationError(ReleaseControllerError):
    code = "CONTRACT_CONFIGURATION_FAILURE"


class SourceAuthorityMismatchError(ReleaseControllerError):
    code = "SOURCE_AUTHORITY_MISMATCH"


class TargetCardinalityError(ReleaseControllerError):
    code = "TARGET_CARDINALITY_MISMATCH"


class ProviderReadError(ReleaseControllerError):
    code = "PROVIDER_READ_FAILURE"


class ProviderMutationAmbiguousError(ReleaseControllerError):
    code = "PROVIDER_MUTATION_AMBIGUOUS_RESULT"


class StaleWriteError(ReleaseControllerError):
    code = "STALE_WRITE_DETECTION"


class DriftViolationError(ReleaseControllerError):
    code = "DRIFT_VIOLATION"


class SecretBoundaryError(ReleaseControllerError):
    code = "SECRET_BOUNDARY_VIOLATION"


class ReceiptPolicyError(ReleaseControllerError):
    code = "RECEIPT_POLICY_VIOLATION"


class ReconciliationConflictError(ReleaseControllerError):
    code = "RECONCILIATION_CONFLICT"


class AllowlistViolationError(ReleaseControllerError):
    code = "ALLOWLIST_VIOLATION"


class IllegalStateTransitionError(ReleaseControllerError):
    code = "ILLEGAL_STATE_TRANSITION"


class OciDigestError(ReleaseControllerError):
    code = "OCI_DIGEST_INVALID"


def sanitize_for_error(value: Any) -> str:
    """Return a safe non-secret description for error context."""
    text = str(value)
    lowered = text.lower()
    if "ev[" in lowered or "authorization" in lowered or "bearer " in lowered:
        return "<redacted>"
    if len(text) > 200:
        return text[:200] + "…"
    return text
