"""Closed DigitalOcean provider HTTP client (httpx)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib.parse import parse_qsl, urlparse
from uuid import UUID

import httpx

from aieos_app_release.errors import (
    AllowlistViolationError,
    ProviderMutationAmbiguousError,
    ProviderReadError,
)
from aieos_app_release.oci import validate_oci_digest
from aieos_app_release.secrets import REDACTED, SecretValue

API_BASE = "https://api.digitalocean.com"
API_HOST = "api.digitalocean.com"
APP_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_DECIMAL_INT_RE = re.compile(r"^[0-9]+$")
_PAGINATION_QUERY_KEYS = frozenset({"page", "per_page"})
_LIST_APPS_QUERY_KEYS = frozenset({"page", "per_page", "with_projects"})
MAX_PAGES = 100


class MutationOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    AMBIGUOUS_RESULT = "AMBIGUOUS_RESULT"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class MutationResult:
    """Sanitized mutation outcome — never retains raw provider bodies/AppSpecs."""

    outcome: MutationOutcome
    status_code: int | None = None
    call_count: int = 1
    request_id: str | None = None
    app_id: str | None = None
    deployment_id: str | None = None

    def __repr__(self) -> str:
        return (
            f"MutationResult(outcome={self.outcome!r}, status_code={self.status_code!r}, "
            f"call_count={self.call_count!r}, request_id={self.request_id!r}, "
            f"app_id={self.app_id!r}, deployment_id={self.deployment_id!r})"
        )


@dataclass
class ReadRetryPolicy:
    max_attempts: int = 3
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


def _validate_project_id(project_id: str) -> str:
    """Explicit CREATE project UUID — no default-project fallback."""
    if not isinstance(project_id, str) or not project_id:
        raise AllowlistViolationError("CREATE requires explicit project UUID", detail="project_id")
    if not APP_ID_RE.fullmatch(project_id):
        raise AllowlistViolationError("arbitrary/invalid project UUID rejected", detail="project_id")
    UUID(project_id)
    return project_id


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


def sanitize_provider_payload(obj: Any) -> Any:
    """Replace EV[...] / secret-like strings with SecretValue before caller use."""
    if isinstance(obj, SecretValue):
        return obj
    if isinstance(obj, str):
        if obj.startswith("EV[") or "EV[" in obj:
            return SecretValue(obj)
        return obj
    if isinstance(obj, dict):
        return {k: sanitize_provider_payload(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_provider_payload(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(sanitize_provider_payload(v) for v in obj)
    return obj


def _extract_safe_ids(parsed: dict[str, Any] | None) -> tuple[str | None, str | None]:
    if not isinstance(parsed, dict):
        return None, None
    app_id = None
    deployment_id = None
    app = parsed.get("app")
    if isinstance(app, dict) and isinstance(app.get("id"), str):
        app_id = app["id"]
    elif isinstance(parsed.get("id"), str) and APP_ID_RE.fullmatch(parsed["id"]):
        app_id = parsed["id"]
    dep = parsed.get("deployment")
    if isinstance(dep, dict) and isinstance(dep.get("id"), str):
        deployment_id = dep["id"]
    elif isinstance(parsed.get("deployment_id"), str):
        deployment_id = parsed["deployment_id"]
    return app_id, deployment_id


def _parse_meta_total(data: dict[str, Any]) -> int:
    meta = data.get("meta")
    if meta is None:
        raise ProviderReadError("pagination meta missing")
    if not isinstance(meta, dict):
        raise ProviderReadError("pagination meta must be object")
    if "total" not in meta:
        raise ProviderReadError("pagination meta.total missing")
    total = meta.get("total")
    # Reject bool explicitly (bool is a subclass of int in Python)
    if isinstance(total, bool) or not isinstance(total, int):
        raise ProviderReadError("pagination meta.total must be non-negative integer")
    if total < 0:
        raise ProviderReadError("pagination meta.total must be non-negative integer")
    return total


def _assert_pagination_query(
    query: str,
    *,
    allowed_keys: frozenset[str] = _PAGINATION_QUERY_KEYS,
    require_with_projects_true: bool = False,
) -> None:
    """Allow listed pagination keys with strict single decimal-integer page/per_page.

    List Apps may additionally require exactly one ``with_projects=true``.
    All other paginated endpoints keep R4: only ``page`` / ``per_page``.
    """
    pairs = parse_qsl(query, keep_blank_values=True) if query else []
    keys = [key for key, _ in pairs]
    for key in keys:
        if key not in allowed_keys:
            raise ProviderReadError("pagination query parameter rejected")
    if keys.count("page") > 1:
        raise ProviderReadError("duplicate pagination page parameter")
    if keys.count("per_page") > 1:
        raise ProviderReadError("duplicate pagination per_page parameter")
    if require_with_projects_true:
        wp_count = keys.count("with_projects")
        if wp_count == 0:
            raise ProviderReadError("with_projects required on list apps pagination")
        if wp_count > 1:
            raise ProviderReadError("duplicate with_projects parameter")
        wp_value = next(v for k, v in pairs if k == "with_projects")
        if wp_value != "true":
            raise ProviderReadError("with_projects must be true")
    elif "with_projects" in keys:
        # Defense: with_projects must never pass default R4 allowlist.
        raise ProviderReadError("pagination query parameter rejected")
    values = dict(pairs)
    if "page" in values:
        raw_page = values["page"]
        if not _DECIMAL_INT_RE.fullmatch(raw_page):
            raise ProviderReadError("pagination page must be decimal integer")
        if int(raw_page) < 1:
            raise ProviderReadError("pagination page must be >= 1")
    if "per_page" in values:
        raw_per_page = values["per_page"]
        if not _DECIMAL_INT_RE.fullmatch(raw_per_page):
            raise ProviderReadError("pagination per_page must be decimal integer")
        per_page = int(raw_per_page)
        if per_page < 1 or per_page > 200:
            raise ProviderReadError("pagination per_page out of range")


def _assert_same_origin_next(
    next_url: str,
    *,
    allowed_exact_paths: tuple[str, ...],
    allowed_query_keys: frozenset[str] = _PAGINATION_QUERY_KEYS,
    require_with_projects_true: bool = False,
) -> str:
    """Return path+query for next page; fail closed on external/malicious URLs."""
    parsed = urlparse(next_url)
    if parsed.username is not None or parsed.password is not None:
        raise ProviderReadError("pagination next URL userinfo rejected")
    if parsed.fragment:
        raise ProviderReadError("pagination next URL fragment rejected")
    if parsed.scheme == "http":
        raise ProviderReadError("pagination next URL must be HTTPS")
    if parsed.scheme not in {"https", ""}:
        raise ProviderReadError("pagination next URL scheme rejected")
    if parsed.scheme == "https" and parsed.hostname != API_HOST:
        raise ProviderReadError("pagination next URL host rejected")
    if parsed.netloc and parsed.hostname != API_HOST:
        raise ProviderReadError("pagination next URL host rejected")
    path = (parsed.path or "").rstrip("/")
    allowed = {p.rstrip("/") for p in allowed_exact_paths}
    if path not in allowed:
        raise ProviderReadError("pagination next path outside allowlist")
    _assert_pagination_query(
        parsed.query,
        allowed_keys=allowed_query_keys,
        require_with_projects_true=require_with_projects_true,
    )
    if parsed.query:
        return f"{path}?{parsed.query}"
    return path


def _docr_digest_allowed_paths(registry: str, repository: str) -> tuple[str, ...]:
    """Primary + documented legacy same-origin next path for DOCR digests listing."""
    return (
        f"/v2/registries/{registry}/repositories/{repository}/digests",
        f"/v2/registry/{registry}/repositories/{repository}/digests",
    )


class DigitalOceanAppClient:
    """Typed closed provider surface. No generic public request(method, url)."""

    def __init__(
        self,
        token: str | SecretValue,
        *,
        transport: httpx.BaseTransport | None = None,
        read_retry: ReadRetryPolicy | None = None,
    ) -> None:
        if isinstance(token, SecretValue):
            self._token = token
        elif isinstance(token, str):
            self._token = SecretValue(token)
        else:
            raise TypeError("token must be SecretValue or str")
        self.transport = transport
        self.read_retry = read_retry or ReadRetryPolicy()
        self._mutation_calls = 0
        self._verify = True
        self._trust_env = False
        self._follow_redirects = False
        # Reveal token only at this narrow Authorization-header construction boundary.
        self._client = httpx.Client(
            base_url=API_BASE,
            transport=self.transport,
            verify=self._verify,
            trust_env=self._trust_env,
            follow_redirects=self._follow_redirects,
            timeout=httpx.Timeout(30.0),
            headers={
                "Authorization": f"Bearer {self._token.reveal()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    def __repr__(self) -> str:
        return (
            f"DigitalOceanAppClient(token={REDACTED!r}, base_url={API_BASE!r}, "
            f"trust_env=False, follow_redirects=False, verify=True)"
        )

    def __str__(self) -> str:
        return self.__repr__()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> DigitalOceanAppClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @property
    def mutation_call_count(self) -> int:
        return self._mutation_calls

    def client_posture(self) -> dict[str, Any]:
        """Non-secret construction posture for tests/CI proofs."""
        transport = getattr(self._client, "_transport", None)
        return {
            "base_url": str(self._client.base_url).rstrip("/"),
            "constructed_verify": self._verify,
            "constructed_trust_env": self._trust_env,
            "constructed_follow_redirects": self._follow_redirects,
            "live_trust_env": self._client.trust_env,
            "live_follow_redirects": bool(self._client.follow_redirects),
            "has_retry_transport": type(transport).__name__ in {"RetryTransport", "TransportWithRetry"},
            "transport_type": type(transport).__name__ if transport is not None else None,
        }

    def _read_once(self, method: str, path: str) -> httpx.Response:
        if method not in {"GET"}:
            raise AllowlistViolationError("read path allows GET only")
        if not path.startswith("/v2/"):
            raise AllowlistViolationError("path outside /v2/ rejected")
        # Use relative path against base_url; never accept absolute foreign URLs here.
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
                return sanitize_provider_payload(data)
            except ProviderReadError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if _is_retryable_read(exc, None) and attempts < self.read_retry.max_attempts:
                    continue
                raise ProviderReadError("provider read transport failure") from exc
        raise ProviderReadError(
            "provider read exhausted retries",
            detail=str(type(last_exc).__name__ if last_exc else last_status),
        )

    def _paginate(
        self,
        *,
        first_path: str,
        collection_key: str,
        allowed_exact_paths: tuple[str, ...],
        allowed_query_keys: frozenset[str] = _PAGINATION_QUERY_KEYS,
        require_with_projects_true: bool = False,
    ) -> list[Any]:
        """Paginated GET with meta.total completeness proof. Never infers completion from absent links."""
        items: list[Any] = []
        path = first_path
        seen: set[str] = set()
        expected_total: int | None = None
        for _ in range(MAX_PAGES):
            if path in seen:
                raise ProviderReadError("pagination loop detected")
            seen.add(path)
            data = self._read_with_retry("GET", path)
            page_items = data.get(collection_key)
            if not isinstance(page_items, list):
                raise ProviderReadError(f"malformed {collection_key} response")
            total = _parse_meta_total(data)
            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                raise ProviderReadError("pagination meta.total changed between pages")
            items.extend(page_items)
            if len(items) > expected_total:
                raise ProviderReadError("pagination accumulated count exceeds meta.total")

            links = data.get("links")
            if links is None:
                nxt = None
            elif not isinstance(links, dict):
                raise ProviderReadError("malformed pagination links")
            else:
                pages = links.get("pages")
                if pages is None:
                    nxt = None
                elif not isinstance(pages, dict):
                    raise ProviderReadError("malformed pagination pages")
                else:
                    nxt = pages.get("next")
                    if nxt is not None and not isinstance(nxt, str):
                        raise ProviderReadError("malformed pagination next")
                    if isinstance(nxt, str) and not nxt:
                        nxt = None

            if nxt:
                path = _assert_same_origin_next(
                    nxt,
                    allowed_exact_paths=allowed_exact_paths,
                    allowed_query_keys=allowed_query_keys,
                    require_with_projects_true=require_with_projects_true,
                )
                continue

            # No next: completeness requires exact total match
            if len(items) != expected_total:
                raise ProviderReadError("incomplete enumeration")
            return items

        raise ProviderReadError("pagination exceeded max pages")

    def get_app(self, app_id: str) -> dict[str, Any]:
        app_id = _validate_app_id(app_id)
        return self._read_with_retry("GET", f"/v2/apps/{app_id}")

    def list_apps(self) -> list[dict[str, Any]]:
        """Complete paginated GET /v2/apps with explicit project evidence (with_projects=true)."""
        apps = self._paginate(
            first_path="/v2/apps?page=1&per_page=200&with_projects=true",
            collection_key="apps",
            allowed_exact_paths=("/v2/apps",),
            allowed_query_keys=_LIST_APPS_QUERY_KEYS,
            require_with_projects_true=True,
        )
        if not all(isinstance(a, dict) for a in apps):
            raise ProviderReadError("malformed apps entries")
        return apps  # type: ignore[return-value]

    def count_apps_by_semantic_name(self, semantic_name: str) -> int:
        """Bootstrap cardinality via full enumeration + local exact-name filter."""
        if not semantic_name or not isinstance(semantic_name, str):
            raise AllowlistViolationError("App semantic name required")
        apps = self.list_apps()
        count = 0
        for app in apps:
            name = None
            spec = app.get("spec")
            if isinstance(spec, dict):
                name = spec.get("name")
            if name is None:
                name = app.get("name")
            if name == semantic_name:
                count += 1
        return count

    def get_app_deployments(self, app_id: str) -> list[dict[str, Any]]:
        app_id = _validate_app_id(app_id)
        deployments = self._paginate(
            first_path=f"/v2/apps/{app_id}/deployments?page=1&per_page=200",
            collection_key="deployments",
            allowed_exact_paths=(f"/v2/apps/{app_id}/deployments",),
        )
        if not all(isinstance(d, dict) for d in deployments):
            raise ProviderReadError("malformed deployments entries")
        return deployments  # type: ignore[return-value]

    def prove_registry_digest_exists(
        self,
        *,
        registry: str,
        repository: str,
        digest: str,
    ) -> bool:
        """Paginated read-only manifests list; exact sha256 digest match. Never DELETE."""
        digest = validate_oci_digest(digest)
        if registry != "eduvijna-registry" or repository != "aieos-backend":
            raise AllowlistViolationError("registry/repository not authorized")
        # Documented DOCR endpoint path remains .../digests; 200 collection key is "manifests".
        primary = f"/v2/registries/{registry}/repositories/{repository}/digests"
        first = f"{primary}?page=1&per_page=200"
        manifests = self._paginate(
            first_path=first,
            collection_key="manifests",
            allowed_exact_paths=_docr_digest_allowed_paths(registry, repository),
        )
        for entry in manifests:
            if not isinstance(entry, dict):
                raise ProviderReadError("manifest entry must be an object")
            if "digest" not in entry:
                raise ProviderReadError("manifest missing digest")
            observed = entry.get("digest")
            if not isinstance(observed, str):
                raise ProviderReadError("manifest digest must be string")
            try:
                validate_oci_digest(observed)
            except Exception as exc:
                raise ProviderReadError("manifest malformed digest") from exc
            if observed == digest:
                return True
        return False

    def _mutate_once(self, method: str, path: str, json_body: dict[str, Any] | None) -> MutationResult:
        """Transmit mutation exactly once. Never retries. Never retains raw body."""
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
        request_id = resp.headers.get("x-request-id")
        if _is_ambiguous_mutation(None, resp.status_code):
            return MutationResult(
                outcome=MutationOutcome.AMBIGUOUS_RESULT,
                status_code=resp.status_code,
                call_count=call_count,
                request_id=request_id,
            )
        if resp.status_code >= 400:
            return MutationResult(
                outcome=MutationOutcome.REJECTED,
                status_code=resp.status_code,
                call_count=call_count,
                request_id=request_id,
            )
        app_id = None
        deployment_id = None
        try:
            parsed = resp.json()
            if isinstance(parsed, dict):
                app_id, deployment_id = _extract_safe_ids(parsed)
        except Exception:  # noqa: BLE001
            pass
        return MutationResult(
            outcome=MutationOutcome.SUCCESS,
            status_code=resp.status_code,
            call_count=call_count,
            request_id=request_id,
            app_id=app_id,
            deployment_id=deployment_id,
        )

    def create_app(self, app_spec: dict[str, Any], *, project_id: str) -> MutationResult:
        """CREATE with explicit project binding — no default-project fallback."""
        if not isinstance(app_spec, dict):
            raise AllowlistViolationError("CREATE requires object AppSpec")
        authorized_project_uuid = _validate_project_id(project_id)
        # Exact body: project_id + spec only. AppSpec remains caller-owned in-memory.
        return self._mutate_once(
            "POST",
            "/v2/apps",
            {"project_id": authorized_project_uuid, "spec": app_spec},
        )

    def update_app(self, app_id: str, app_spec: dict[str, Any]) -> MutationResult:
        app_id = _validate_app_id(app_id)
        if not isinstance(app_spec, dict):
            raise AllowlistViolationError("UPDATE requires object AppSpec")
        return self._mutate_once("PUT", f"/v2/apps/{app_id}", {"spec": app_spec})

    def rotate_secret(self, app_id: str, app_spec: dict[str, Any]) -> MutationResult:
        return self.update_app(app_id, app_spec)

    def validate_rollback(self, app_id: str, deployment_id: str) -> MutationResult:
        app_id = _validate_app_id(app_id)
        if not deployment_id or not isinstance(deployment_id, str):
            raise AllowlistViolationError("deployment_id required")
        return self._mutate_once(
            "POST",
            f"/v2/apps/{app_id}/rollback/validate",
            {"deployment_id": deployment_id, "skip_pin": False},
        )

    def start_rollback(self, app_id: str, deployment_id: str) -> MutationResult:
        app_id = _validate_app_id(app_id)
        if not deployment_id or not isinstance(deployment_id, str):
            raise AllowlistViolationError("deployment_id required")
        return self._mutate_once(
            "POST",
            f"/v2/apps/{app_id}/rollback",
            {"deployment_id": deployment_id, "skip_pin": False},
        )

    def commit_rollback(self, app_id: str) -> MutationResult:
        app_id = _validate_app_id(app_id)
        return self._mutate_once("POST", f"/v2/apps/{app_id}/rollback/commit", None)


def public_provider_methods() -> frozenset[str]:
    """Public callable surface excluding dunders/private names."""
    names: set[str] = set()
    for name in dir(DigitalOceanAppClient):
        if name.startswith("_"):
            continue
        attr = getattr(DigitalOceanAppClient, name)
        if callable(attr) or isinstance(attr, property):
            names.add(name)
    return frozenset(names)


AUTHORIZED_PUBLIC_CALLABLES = frozenset(
    {
        "get_app",
        "list_apps",
        "count_apps_by_semantic_name",
        "get_app_deployments",
        "prove_registry_digest_exists",
        "create_app",
        "update_app",
        "rotate_secret",
        "validate_rollback",
        "start_rollback",
        "commit_rollback",
        "close",
        "client_posture",
        "mutation_call_count",
        "__enter__",
        "__exit__",
        "__repr__",
        "__str__",
        "__init__",
    }
)


def require_ambiguous_raises(result: MutationResult) -> None:
    if result.outcome is MutationOutcome.AMBIGUOUS_RESULT:
        raise ProviderMutationAmbiguousError(
            "mutation result ambiguous; reconcile read-only only"
        )
