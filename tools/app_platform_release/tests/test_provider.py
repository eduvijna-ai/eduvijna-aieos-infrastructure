"""Provider HTTP closed-surface and zero-mutation-retry tests."""

from __future__ import annotations

import json

import httpx
import pytest

from aieos_app_release.errors import AllowlistViolationError, ProviderReadError
from aieos_app_release.provider import (
    API_BASE,
    AUTHORIZED_PUBLIC_CALLABLES,
    DigitalOceanAppClient,
    MutationOutcome,
    MutationResult,
    ReadRetryPolicy,
    public_provider_methods,
    sanitize_provider_payload,
)
from aieos_app_release.secrets import REDACTED, SecretValue
from tests.conftest import DUMMY_APP_ID, DUMMY_DIGEST

DUMMY_PAT = "dop_v1_DUMMY_PAT_VALUE_NOT_REAL_ABCDEFGHIJKLMNOP"


def _client(handler, token: str | SecretValue = DUMMY_PAT) -> DigitalOceanAppClient:
    return DigitalOceanAppClient(token=token, transport=httpx.MockTransport(handler))


def test_client_posture_real() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"apps": [], "links": {}})

    with _client(handler) as c:
        posture = c.client_posture()
        assert posture["base_url"] == API_BASE
        assert posture["constructed_verify"] is True
        assert posture["constructed_trust_env"] is False
        assert posture["constructed_follow_redirects"] is False
        assert posture["live_trust_env"] is False
        assert posture["live_follow_redirects"] is False
        assert posture["has_retry_transport"] is False


def test_token_repr_str_errors_redacted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"apps": [], "links": {}})

    with _client(handler) as c:
        assert DUMMY_PAT not in repr(c)
        assert DUMMY_PAT not in str(c)
        assert REDACTED in repr(c)
        result = c.create_app({"name": "x"})
        assert DUMMY_PAT not in repr(result)
        assert getattr(result, "body", None) is None
        try:
            raise RuntimeError(f"client={c} result={result}")
        except RuntimeError as exc:
            assert DUMMY_PAT not in str(exc)


def test_mutation_result_has_no_raw_body() -> None:
    mr = MutationResult(outcome=MutationOutcome.SUCCESS, status_code=201, app_id=DUMMY_APP_ID)
    assert not hasattr(mr, "body") or getattr(mr, "body", None) is None
    assert "spec" not in repr(mr)


def test_public_surface_closed() -> None:
    public = public_provider_methods()
    forbidden = {"delete_app", "restart_app", "request", "rollback_deployment", "list_apps_by_name"}
    assert forbidden.isdisjoint(public)
    # all non-dunder public callables must be authorized
    for name in public:
        if name.startswith("__") and name.endswith("__"):
            continue
        assert name in AUTHORIZED_PUBLIC_CALLABLES, name
    assert not hasattr(DigitalOceanAppClient, "delete_app")
    assert not hasattr(DigitalOceanAppClient, "restart_app")
    assert not hasattr(DigitalOceanAppClient, "request")


def test_arbitrary_app_id_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"app": {}})

    with _client(handler) as c:
        with pytest.raises(AllowlistViolationError):
            c.get_app("not-a-uuid")
        with pytest.raises(AllowlistViolationError):
            c.update_app("latest", {"name": "x"})


def test_create_update_rotate_one_call() -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={"app": {"id": DUMMY_APP_ID}})

    with _client(handler) as c:
        assert c.create_app({"name": "x"}).call_count == 1
        assert c.update_app(DUMMY_APP_ID, {"name": "x"}).call_count == 2
        assert c.rotate_secret(DUMMY_APP_ID, {"name": "x"}).call_count == 3
        assert calls == [
            ("POST", "/v2/apps"),
            ("PUT", f"/v2/apps/{DUMMY_APP_ID}"),
            ("PUT", f"/v2/apps/{DUMMY_APP_ID}"),
        ]
        assert c.mutation_call_count == 3


def test_transport_exception_and_5xx_ambiguous_one_call() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with _client(boom) as c:
        r = c.create_app({"name": "x"})
        assert r.outcome is MutationOutcome.AMBIGUOUS_RESULT
        assert c.mutation_call_count == 1

    def five(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    with _client(five) as c:
        r = c.update_app(DUMMY_APP_ID, {"name": "x"})
        assert r.outcome is MutationOutcome.AMBIGUOUS_RESULT
        assert c.mutation_call_count == 1


def test_read_retry_bounded_mutation_not_retried() -> None:
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        if request.method == "GET":
            if hits["n"] < 3:
                return httpx.Response(503, json={"error": "tmp"})
            return httpx.Response(200, json={"app": {"id": DUMMY_APP_ID}})
        return httpx.Response(503, json={"error": "tmp"})

    with DigitalOceanAppClient(
        token=DUMMY_PAT,
        transport=httpx.MockTransport(handler),
        read_retry=ReadRetryPolicy(max_attempts=3),
    ) as c:
        data = c.get_app(DUMMY_APP_ID)
        assert data["app"]["id"] == DUMMY_APP_ID
        before = hits["n"]
        result = c.create_app({"name": "x"})
        assert result.outcome is MutationOutcome.AMBIGUOUS_RESULT
        assert hits["n"] == before + 1


def test_sanitize_ev_on_read() -> None:
    payload = sanitize_provider_payload(
        {"spec": {"envs": [{"key": "AIEOS_TEMPORAL_API_KEY", "value": "EV[ABCDEFGH]"}]}}
    )
    val = payload["spec"]["envs"][0]["value"]
    assert isinstance(val, SecretValue)
    assert "EV[" not in str(val)
    assert "EV[" not in repr(val)


def test_app_cardinality_paginated_local_filter() -> None:
    pages = {
        1: {
            "apps": [
                {"id": "11111111-1111-4111-8111-111111111111", "spec": {"name": "other"}},
                {"id": "22222222-2222-4222-8222-222222222222", "spec": {"name": "aieos-prod-workflow-dispatcher"}},
            ],
            "links": {"pages": {"next": "https://api.digitalocean.com/v2/apps?page=2&per_page=200"}},
        },
        2: {
            "apps": [
                {"id": "33333333-3333-4333-8333-333333333333", "spec": {"name": "aieos-prod-workflow-dispatcher"}},
            ],
            "links": {"pages": {}},
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/apps"
        assert "name=" not in str(request.url)
        page = int(request.url.params.get("page", "1"))
        return httpx.Response(200, json=pages[page])

    with _client(handler) as c:
        assert c.count_apps_by_semantic_name("aieos-prod-workflow-dispatcher") == 2
        assert c.count_apps_by_semantic_name("missing") == 0


def test_app_cardinality_zero_and_malformed_and_external_next() -> None:
    def empty(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"apps": [], "links": {}})

    with _client(empty) as c:
        assert c.count_apps_by_semantic_name("aieos-prod-workflow-dispatcher") == 0

    def malformed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"apps": "nope"})

    with _client(malformed) as c:
        with pytest.raises(ProviderReadError):
            c.count_apps_by_semantic_name("x")

    def evil_next(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "apps": [],
                "links": {"pages": {"next": "https://evil.example/v2/apps?page=2"}},
            },
        )

    with _client(evil_next) as c:
        with pytest.raises(ProviderReadError):
            c.list_apps()


def test_oci_digest_paginated_exact_match_fail_closed() -> None:
    target = DUMMY_DIGEST
    other = "sha256:" + ("b" * 64)
    pages = {
        1: {
            "manifests": [{"digest": other}],
            "links": {
                "pages": {
                    "next": "https://api.digitalocean.com/v2/registries/eduvijna-registry/repositories/aieos-backend/digests?page=2&per_page=200"
                }
            },
        },
        2: {"manifests": [{"digest": target}], "links": {"pages": {}}},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert "/v2/registries/eduvijna-registry/repositories/aieos-backend/digests" == request.url.path
        assert request.method == "GET"
        page = int(request.url.params.get("page", "1"))
        return httpx.Response(200, json=pages[page])

    with _client(handler) as c:
        assert c.prove_registry_digest_exists(
            registry="eduvijna-registry", repository="aieos-backend", digest=target
        )

    def missing_target(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"manifests": [{"digest": other}], "links": {}})

    with _client(missing_target) as c:
        assert (
            c.prove_registry_digest_exists(
                registry="eduvijna-registry", repository="aieos-backend", digest=target
            )
            is False
        )

    def missing_key(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"links": {}})

    with _client(missing_key) as c:
        with pytest.raises(ProviderReadError):
            c.prove_registry_digest_exists(
                registry="eduvijna-registry", repository="aieos-backend", digest=target
            )

    def not_array(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"manifests": 123})

    with _client(not_array) as c:
        with pytest.raises(ProviderReadError):
            c.prove_registry_digest_exists(
                registry="eduvijna-registry", repository="aieos-backend", digest=target
            )

    def not_object(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"manifests": [target], "links": {}})

    with _client(not_object) as c:
        with pytest.raises(ProviderReadError):
            c.prove_registry_digest_exists(
                registry="eduvijna-registry", repository="aieos-backend", digest=target
            )

    def missing_digest_field(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"manifests": [{"tag": "latest"}], "links": {}})

    with _client(missing_digest_field) as c:
        with pytest.raises(ProviderReadError):
            c.prove_registry_digest_exists(
                registry="eduvijna-registry", repository="aieos-backend", digest=target
            )

    def malformed_digest(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"manifests": [{"digest": "latest"}], "links": {}})

    with _client(malformed_digest) as c:
        with pytest.raises(ProviderReadError):
            c.prove_registry_digest_exists(
                registry="eduvijna-registry", repository="aieos-backend", digest=target
            )

    def invent_digests_key(request: httpx.Request) -> httpx.Response:
        # invented collection key must fail closed (manifests required)
        return httpx.Response(200, json={"digests": [{"digest": target}], "links": {}})

    with _client(invent_digests_key) as c:
        with pytest.raises(ProviderReadError):
            c.prove_registry_digest_exists(
                registry="eduvijna-registry", repository="aieos-backend", digest=target
            )

    def evil_next(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "manifests": [{"digest": other}],
                "links": {
                    "pages": {
                        "next": "https://evil.example/v2/registries/eduvijna-registry/repositories/aieos-backend/digests?page=2"
                    }
                },
            },
        )

    with _client(evil_next) as c:
        with pytest.raises(ProviderReadError):
            c.prove_registry_digest_exists(
                registry="eduvijna-registry", repository="aieos-backend", digest=target
            )


def test_rollback_validate_start_commit_paths_and_one_call() -> None:
    recorded: list[tuple[str, str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else None
        recorded.append((request.method, request.url.path, body))
        return httpx.Response(200, json={"deployment": {"id": "dep-1"}})

    dep = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    with _client(handler) as c:
        assert c.validate_rollback(DUMMY_APP_ID, dep).call_count == 1
        assert c.start_rollback(DUMMY_APP_ID, dep).call_count == 2
        assert c.commit_rollback(DUMMY_APP_ID).call_count == 3
    assert recorded == [
        (
            "POST",
            f"/v2/apps/{DUMMY_APP_ID}/rollback/validate",
            {"deployment_id": dep, "skip_pin": False},
        ),
        (
            "POST",
            f"/v2/apps/{DUMMY_APP_ID}/rollback",
            {"deployment_id": dep, "skip_pin": False},
        ),
        ("POST", f"/v2/apps/{DUMMY_APP_ID}/rollback/commit", None),
    ]


def test_ambiguous_rollback_does_not_auto_commit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    with _client(handler) as c:
        r = c.start_rollback(DUMMY_APP_ID, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        assert r.outcome is MutationOutcome.AMBIGUOUS_RESULT
        assert c.mutation_call_count == 1
        # caller must not auto-commit; commit would be a separate explicit call
        assert not hasattr(c, "rollback_deployment")
