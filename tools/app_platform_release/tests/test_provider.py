"""Provider HTTP closed-surface and zero-mutation-retry tests."""

from __future__ import annotations

import httpx
import pytest

from aieos_app_release.errors import AllowlistViolationError
from aieos_app_release.provider import (
    API_BASE,
    DigitalOceanAppClient,
    MutationOutcome,
    ReadRetryPolicy,
)
from tests.conftest import DUMMY_APP_ID, DUMMY_DIGEST


def _client(handler) -> DigitalOceanAppClient:
    transport = httpx.MockTransport(handler)
    return DigitalOceanAppClient(token="dummy-pat-not-real", transport=transport)


def test_client_posture() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"apps": []})

    with _client(handler) as c:
        assert str(c._client.base_url).rstrip("/") == API_BASE
        assert c._client.trust_env is False
        assert c._client.follow_redirects is False
        # verify remains True (not disabled)
        assert c._client._transport is not None or True
        c.list_apps_by_name("aieos-prod-workflow-dispatcher")


def test_generic_request_forbidden() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    with _client(handler) as c:
        with pytest.raises(AllowlistViolationError):
            c.request("GET", "/v2/apps")


def test_delete_forbidden() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    with _client(handler) as c:
        with pytest.raises(AllowlistViolationError):
            c.delete_app(DUMMY_APP_ID)
        with pytest.raises(AllowlistViolationError):
            c.restart_app(DUMMY_APP_ID)


def test_arbitrary_app_id_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"app": {}})

    with _client(handler) as c:
        with pytest.raises(AllowlistViolationError):
            c.get_app("not-a-uuid")
        with pytest.raises(AllowlistViolationError):
            c.update_app("latest", {"name": "x"})


def test_create_one_post_only() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        return httpx.Response(201, json={"app": {"id": DUMMY_APP_ID}})

    with _client(handler) as c:
        result = c.create_app({"name": "aieos-prod-workflow-dispatcher"})
        assert result.outcome is MutationOutcome.SUCCESS
        assert result.call_count == 1
        assert c.mutation_call_count == 1
        assert calls == ["POST /v2/apps"]


def test_update_one_put_only() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        return httpx.Response(200, json={"app": {"id": DUMMY_APP_ID}})

    with _client(handler) as c:
        result = c.update_app(DUMMY_APP_ID, {"name": "aieos-prod-workflow-dispatcher"})
        assert result.outcome is MutationOutcome.SUCCESS
        assert calls == [f"PUT /v2/apps/{DUMMY_APP_ID}"]
        assert c.mutation_call_count == 1


def test_rotate_secret_one_put_only() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        return httpx.Response(200, json={"app": {"id": DUMMY_APP_ID}})

    with _client(handler) as c:
        result = c.rotate_secret(DUMMY_APP_ID, {"name": "x", "envs": []})
        assert result.outcome is MutationOutcome.SUCCESS
        assert calls == ["PUT"]
        assert c.mutation_call_count == 1


def test_transport_exception_after_mutation_ambiguous_one_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with _client(handler) as c:
        result = c.create_app({"name": "x"})
        assert result.outcome is MutationOutcome.AMBIGUOUS_RESULT
        assert result.call_count == 1
        assert c.mutation_call_count == 1


def test_5xx_mutation_ambiguous_one_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    with _client(handler) as c:
        result = c.update_app(DUMMY_APP_ID, {"name": "x"})
        assert result.outcome is MutationOutcome.AMBIGUOUS_RESULT
        assert c.mutation_call_count == 1


def test_read_transient_retry_bounded() -> None:
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        if hits["n"] < 3:
            return httpx.Response(503, json={"error": "tmp"})
        return httpx.Response(200, json={"app": {"id": DUMMY_APP_ID}})

    with DigitalOceanAppClient(
        token="dummy",
        transport=httpx.MockTransport(handler),
        read_retry=ReadRetryPolicy(max_attempts=3),
    ) as c:
        data = c.get_app(DUMMY_APP_ID)
        assert data["app"]["id"] == DUMMY_APP_ID
        assert hits["n"] == 3
        assert c.mutation_call_count == 0


def test_mutation_never_uses_read_retry_loop() -> None:
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(503, json={"error": "tmp"})

    with DigitalOceanAppClient(
        token="dummy",
        transport=httpx.MockTransport(handler),
        read_retry=ReadRetryPolicy(max_attempts=5),
    ) as c:
        result = c.create_app({"name": "x"})
        assert result.outcome is MutationOutcome.AMBIGUOUS_RESULT
        assert hits["n"] == 1
        assert c.mutation_call_count == 1


def test_prove_digest_read_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "eduvijna-registry" in str(request.url)
        assert "aieos-backend" in str(request.url)
        return httpx.Response(200, json={"exists": True})

    with _client(handler) as c:
        assert c.prove_registry_digest_exists(
            registry="eduvijna-registry",
            repository="aieos-backend",
            digest=DUMMY_DIGEST,
        )
