"""Closed DigitalOcean provider HTTP client (httpx)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable
from uuid import UUID

import httpx

from aieos_app_release.errors import (
    AllowlistViolationError,
    ProviderMutationAmbiguousError,
    ProviderReadError,
)
from aieos_app_release.oci import validate_oci_digest

API_BASE = "https://api.digitalocean.com"
APP_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


class MutationOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    AMBIGUOUS_RESULT = "AMBIGUOUS_RESULT"
    REJECTED = "REJECTED"


@dataclass
class MutationResult:
    outcome: MutationOutcome
    status_code: int | None = None
    body: dict[str, Any] | None = None
    call_count: int = 1
    request_id: str | None = None


@dataclass
class ReadRetryPolicy:
    max_attempts: int = 3
    # Deterministic testable backoff schedule (seconds); caller may ignore sleeps in tests
    backoff_seconds: tuple[float, ...] = (0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.max_attempts > 5:
            raise ValueError("max_attempts must be <= 5")


def _validate_app_id(app_id: str) -> str:
    if not APP_ID_RE.fullmatch(app_id):
        raise AllowlistViolationError("arbitrary/invalid App ID rejected", detail="app_id")
    UUID(app_id)
    return app_id


def _is_retryable_read(exc: BaseException | None, status: int | None) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)):
        return True
    if status in {429, 500, 502, 503, 504}:
        return True
    return False


def _is_ambiguous_mutation(exc: BaseException | None, status: int | None) -> bool:
    if isinstance(
        exc,
        (
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.RemoteProtocolError,
            httpx.TransportError,
        ),
    ):
        return True
    if status is not None and status >= 500:
        return True
    return False


@dataclass
class DigitalOceanAppClient:
    """Typed closed provider surface. No generic public request(method, url)."""

    token: str
    transport: httpx.BaseTransport | None = None
    read_retry: ReadRetryPolicy = field(default_factory=ReadRetryPolicy)
    _mutation_calls: int = field(default=0, init=False, repr=False)
    _client: httpx.Client = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = httpx.Client(
            base_url=API_BASE,
            transport=self.transport,
            verify=True,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(30.0),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> DigitalOceanAppClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @property
    def mutation_call_count(self) -> int:
        return self._mutation_calls

    def _read_once(self, method: str, path: str) -> httpx.Response:
        if method not in {"GET"}:
            raise AllowlistViolationError("read path allows GET only")
        if not path.startswith("/v2/"):
            raise AllowlistViolationError("path outside /v2/ rejected")
        return self._client.request(method, path)

    def _read_with_retry(self, method: str, path: str) -> dict[str, Any]:
        attempts = 0
        last_exc: BaseException | None = None
        last_status: int | None = None
        while attempts < self.read_retry.max_attempts:
            attempts += 1
            try:
                resp = self._read_once(method, path)
                last_status = resp.status_code
                if _is_retryable_read(None, resp.status_code) and attempts < self.read_retry.max_attempts:
                    continue
                if resp.status_code >= 400:
                    raise ProviderReadError(
                        "provider read failed",
                        detail=f"status={resp.status_code}",
                    )
                data = resp.json()
                if not isinstance(data, dict):
                    raise ProviderReadError("provider read returned non-object")
                return data
            except ProviderReadError:
                raise
            except Exception as exc:  # noqa: BLE001 — classified below
                last_exc = exc
                if _is_retryable_read(exc, None) and attempts < self.read_retry.max_attempts:
                    continue
                raise ProviderReadError("provider read transport failure") from exc
        raise ProviderReadError(
            "provider read exhausted retries",
            detail=str(type(last_exc).__name__ if last_exc else last_status),
        )

    def get_app(self, app_id: str) -> dict[str, Any]:
        app_id = _validate_app_id(app_id)
        return self._read_with_retry("GET", f"/v2/apps/{app_id}")

    def list_apps_by_name(self, name: str) -> list[dict[str, Any]]:
        if not name or not isinstance(name, str):
            raise AllowlistViolationError("App name required")
        data = self._read_with_retry("GET", f"/v2/apps?name={name}")
        apps = data.get("apps", [])
        if not isinstance(apps, list):
            raise ProviderReadError("apps list malformed")
        return apps

    def get_app_deployments(self, app_id: str) -> list[dict[str, Any]]:
        app_id = _validate_app_id(app_id)
        data = self._read_with_retry("GET", f"/v2/apps/{app_id}/deployments")
        deployments = data.get("deployments", [])
        if not isinstance(deployments, list):
            raise ProviderReadError("deployments list malformed")
        return deployments

    def prove_registry_digest_exists(
        self,
        *,
        registry: str,
        repository: str,
        digest: str,
    ) -> bool:
        digest = validate_oci_digest(digest)
        if registry != "eduvijna-registry" or repository != "aieos-backend":
            raise AllowlistViolationError("registry/repository not authorized")
        # DigitalOcean Container Registry manifest HEAD/GET abstraction (read-only)
        path = f"/v2/registry/{registry}/repositories/{repository}/digests/{digest}"
        data = self._read_with_retry("GET", path)
        return bool(data.get("exists", True))

    def _mutate_once(self, method: str, path: str, json_body: dict[str, Any] | None) -> MutationResult:
        """Transmit mutation exactly once. Never retries."""
        self._mutation_calls += 1
        call_count = self._mutation_calls
        try:
            resp = self._client.request(method, path, json=json_body)
        except Exception as exc:  # noqa: BLE001
            if _is_ambiguous_mutation(exc, None):
                return MutationResult(
                    outcome=MutationOutcome.AMBIGUOUS_RESULT,
                    call_count=call_count,
                )
            raise
        if _is_ambiguous_mutation(None, resp.status_code):
            return MutationResult(
                outcome=MutationOutcome.AMBIGUOUS_RESULT,
                status_code=resp.status_code,
                call_count=call_count,
                request_id=resp.headers.get("x-request-id"),
            )
        if resp.status_code >= 400:
            return MutationResult(
                outcome=MutationOutcome.REJECTED,
                status_code=resp.status_code,
                call_count=call_count,
                request_id=resp.headers.get("x-request-id"),
            )
        body: dict[str, Any] | None
        try:
            parsed = resp.json()
            body = parsed if isinstance(parsed, dict) else None
        except Exception:  # noqa: BLE001
            body = None
        return MutationResult(
            outcome=MutationOutcome.SUCCESS,
            status_code=resp.status_code,
            body=body,
            call_count=call_count,
            request_id=resp.headers.get("x-request-id"),
        )

    def create_app(self, app_spec: dict[str, Any]) -> MutationResult:
        if not isinstance(app_spec, dict):
            raise AllowlistViolationError("CREATE requires object AppSpec")
        return self._mutate_once("POST", "/v2/apps", {"spec": app_spec})

    def update_app(self, app_id: str, app_spec: dict[str, Any]) -> MutationResult:
        app_id = _validate_app_id(app_id)
        if not isinstance(app_spec, dict):
            raise AllowlistViolationError("UPDATE requires object AppSpec")
        return self._mutate_once("PUT", f"/v2/apps/{app_id}", {"spec": app_spec})

    def rotate_secret(self, app_id: str, app_spec: dict[str, Any]) -> MutationResult:
        # Same PUT full-spec path as UPDATE
        return self.update_app(app_id, app_spec)

    def rollback_deployment(
        self,
        app_id: str,
        deployment_id: str,
        *,
        phase: str,
    ) -> MutationResult:
        """Authorized rollback sequence steps only (validate/rollback/verify/commit)."""
        app_id = _validate_app_id(app_id)
        if phase not in {"validate", "rollback", "verify", "commit"}:
            raise AllowlistViolationError("unauthorized rollback phase")
        if not deployment_id or not isinstance(deployment_id, str):
            raise AllowlistViolationError("deployment_id required")
        path = f"/v2/apps/{app_id}/deployments/{deployment_id}/rollback/{phase}"
        return self._mutate_once("POST", path, None)

    def delete_app(self, app_id: str) -> None:  # noqa: ARG002
        raise AllowlistViolationError("DELETE is forbidden")

    def restart_app(self, app_id: str) -> None:  # noqa: ARG002
        raise AllowlistViolationError("restart is forbidden")

    def request(self, *args: Any, **kwargs: Any) -> None:  # noqa: ARG002
        raise AllowlistViolationError("generic request(method, url) is forbidden")


def require_ambiguous_raises(result: MutationResult) -> None:
    if result.outcome is MutationOutcome.AMBIGUOUS_RESULT:
        raise ProviderMutationAmbiguousError(
            "mutation result ambiguous; reconcile read-only only"
        )
