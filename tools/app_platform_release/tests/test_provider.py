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
from tests.conftest import DUMMY_APP_ID, DUMMY_DIGEST, DUMMY_PROJECT

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
        result = c.create_app({"name": "x"}, project_id=DUMMY_PROJECT)
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
    bodies: list[object] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        bodies.append(json.loads(request.content.decode()) if request.content else None)
        return httpx.Response(200, json={"app": {"id": DUMMY_APP_ID}})

    with _client(handler) as c:
        assert c.create_app({"name": "x"}, project_id=DUMMY_PROJECT).call_count == 1
        assert c.update_app(DUMMY_APP_ID, {"name": "x"}).call_count == 2
        assert c.rotate_secret(DUMMY_APP_ID, {"name": "x"}).call_count == 3
        assert calls == [
            ("POST", "/v2/apps"),
            ("PUT", f"/v2/apps/{DUMMY_APP_ID}"),
            ("PUT", f"/v2/apps/{DUMMY_APP_ID}"),
        ]
        assert bodies[0] == {"project_id": DUMMY_PROJECT, "spec": {"name": "x"}}
        assert c.mutation_call_count == 3


def test_create_app_requires_validated_project_uuid() -> None:
    """CREATE body is exactly {project_id, spec}; missing/malformed project rejects before HTTP."""
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        body = json.loads(request.content.decode())
        assert set(body.keys()) == {"project_id", "spec"}
        assert body == {"project_id": DUMMY_PROJECT, "spec": {"name": "x"}}
        return httpx.Response(201, json={"app": {"id": DUMMY_APP_ID}})

    with _client(handler) as c:
        with pytest.raises(TypeError):
            c.create_app({"name": "x"})  # type: ignore[call-arg]
        assert hits["n"] == 0
        with pytest.raises(AllowlistViolationError, match="project"):
            c.create_app({"name": "x"}, project_id="")
        assert hits["n"] == 0
        with pytest.raises(AllowlistViolationError, match="project"):
            c.create_app({"name": "x"}, project_id="not-a-uuid")
        assert hits["n"] == 0
        with pytest.raises(AllowlistViolationError, match="project"):
            c.create_app({"name": "x"}, project_id="latest")
        assert hits["n"] == 0
        result = c.create_app({"name": "x"}, project_id=DUMMY_PROJECT)
        assert result.outcome is MutationOutcome.SUCCESS
        assert result.call_count == 1
        assert hits["n"] == 1
        assert c.mutation_call_count == 1


def test_transport_exception_and_5xx_ambiguous_one_call() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with _client(boom) as c:
        r = c.create_app({"name": "x"}, project_id=DUMMY_PROJECT)
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
        result = c.create_app({"name": "x"}, project_id=DUMMY_PROJECT)
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
            "meta": {"total": 3},
            "links": {
                "pages": {
                    "next": (
                        "https://api.digitalocean.com/v2/apps"
                        "?page=2&per_page=200&with_projects=true"
                    )
                }
            },
        },
        2: {
            "apps": [
                {"id": "33333333-3333-4333-8333-333333333333", "spec": {"name": "aieos-prod-workflow-dispatcher"}},
            ],
            "meta": {"total": 3},
            "links": {"pages": {}},
        },
    }
    first_seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/apps"
        assert "name=" not in str(request.url)
        assert request.url.params.get("with_projects") == "true"
        if not first_seen:
            assert request.url.params.get("page") == "1"
            assert request.url.params.get("per_page") == "200"
            first_seen.append(str(request.url))
        page = int(request.url.params.get("page", "1"))
        return httpx.Response(200, json=pages[page])

    with _client(handler) as c:
        assert c.count_apps_by_semantic_name("aieos-prod-workflow-dispatcher") == 2
        assert c.count_apps_by_semantic_name("missing") == 0
    assert first_seen
    assert "page=1" in first_seen[0]
    assert "per_page=200" in first_seen[0]
    assert "with_projects=true" in first_seen[0]

def test_app_cardinality_completeness() -> None:
    def complete_zero(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"apps": [], "meta": {"total": 0}, "links": {}})

    with _client(complete_zero) as c:
        assert c.count_apps_by_semantic_name("aieos-prod-workflow-dispatcher") == 0

    def incomplete_zero(request: httpx.Request) -> httpx.Response:
        # empty page but total=1 and no next → must NOT return cardinality 0
        return httpx.Response(200, json={"apps": [], "meta": {"total": 1}, "links": {}})

    with _client(incomplete_zero) as c:
        with pytest.raises(ProviderReadError, match="incomplete enumeration"):
            c.count_apps_by_semantic_name("aieos-prod-workflow-dispatcher")

    def incomplete_partial(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "apps": [{"id": "11111111-1111-4111-8111-111111111111", "spec": {"name": "other"}}],
                "meta": {"total": 2},
                "links": {},
            },
        )

    with _client(incomplete_partial) as c:
        with pytest.raises(ProviderReadError, match="incomplete enumeration"):
            c.count_apps_by_semantic_name("x")

    pages = {
        1: {
            "apps": [{"id": "11111111-1111-4111-8111-111111111111", "spec": {"name": "a"}}],
            "meta": {"total": 2},
            "links": {
                "pages": {
                    "next": (
                        "https://api.digitalocean.com/v2/apps"
                        "?page=2&per_page=200&with_projects=true"
                    )
                }
            },
        },
        2: {
            "apps": [{"id": "22222222-2222-4222-8222-222222222222", "spec": {"name": "b"}}],
            "meta": {"total": 2},
            "links": {"pages": {}},
        },
    }

    def complete_two(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        return httpx.Response(200, json=pages[page])

    with _client(complete_two) as c:
        assert c.count_apps_by_semantic_name("missing") == 0

    unstable = {
        1: {
            "apps": [{"id": "11111111-1111-4111-8111-111111111111", "spec": {"name": "a"}}],
            "meta": {"total": 2},
            "links": {
                "pages": {
                    "next": (
                        "https://api.digitalocean.com/v2/apps"
                        "?page=2&per_page=200&with_projects=true"
                    )
                }
            },
        },
        2: {
            "apps": [{"id": "22222222-2222-4222-8222-222222222222", "spec": {"name": "b"}}],
            "meta": {"total": 3},
            "links": {"pages": {}},
        },
    }

    def unstable_total(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        return httpx.Response(200, json=unstable[page])

    with _client(unstable_total) as c:
        with pytest.raises(ProviderReadError, match="meta.total changed"):
            c.list_apps()

    def exceeds(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "apps": [
                    {"id": "11111111-1111-4111-8111-111111111111", "spec": {"name": "a"}},
                    {"id": "22222222-2222-4222-8222-222222222222", "spec": {"name": "b"}},
                ],
                "meta": {"total": 1},
                "links": {},
            },
        )

    with _client(exceeds) as c:
        with pytest.raises(ProviderReadError, match="exceeds"):
            c.list_apps()

    def malformed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"apps": "nope", "meta": {"total": 0}})

    with _client(malformed) as c:
        with pytest.raises(ProviderReadError):
            c.count_apps_by_semantic_name("x")

    def evil_next(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "apps": [],
                "meta": {"total": 1},
                "links": {"pages": {"next": "https://evil.example/v2/apps?page=2"}},
            },
        )

    with _client(evil_next) as c:
        with pytest.raises(ProviderReadError):
            c.list_apps()


def test_pagination_query_allowlist() -> None:
    """List Apps allows page/per_page/with_projects=true; other endpoints keep R4 page/per_page only."""

    def page1_with_next(next_url: str):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.params.get("page") in (None, "1"):
                assert request.url.params.get("with_projects") == "true"
                return httpx.Response(
                    200,
                    json={
                        "apps": [{"id": "11111111-1111-4111-8111-111111111111", "spec": {"name": "a"}}],
                        "meta": {"total": 2},
                        "links": {"pages": {"next": next_url}},
                    },
                )
            assert request.url.params.get("with_projects") == "true"
            return httpx.Response(
                200,
                json={
                    "apps": [{"id": "22222222-2222-4222-8222-222222222222", "spec": {"name": "b"}}],
                    "meta": {"total": 2},
                    "links": {"pages": {}},
                },
            )

        return handler

    # Accepted List Apps next forms — with_projects=true required on every page URL
    for ok_next in (
        "https://api.digitalocean.com/v2/apps?page=2&with_projects=true",
        "https://api.digitalocean.com/v2/apps?page=2&per_page=200&with_projects=true",
        "https://api.digitalocean.com/v2/apps?with_projects=true&page=2&per_page=100",
    ):
        with _client(page1_with_next(ok_next)) as c:
            assert len(c.list_apps()) == 2

    # Missing / false / duplicate with_projects fail closed for List Apps
    for bad_next in (
        "https://api.digitalocean.com/v2/apps?page=2",
        "https://api.digitalocean.com/v2/apps?page=2&per_page=200",
        "https://api.digitalocean.com/v2/apps?page=2&per_page=200&with_projects=false",
        "https://api.digitalocean.com/v2/apps?page=2&with_projects=true&with_projects=true",
        "https://api.digitalocean.com/v2/apps?with_projects=1&page=2",
        "https://api.digitalocean.com/v2/apps?page=2&with_projects=",
    ):
        with _client(page1_with_next(bad_next)) as c:
            with pytest.raises(ProviderReadError):
                c.list_apps()

    # Documented singular DOCR legacy path with page/per_page (R4 — no with_projects)
    other = "sha256:" + ("b" * 64)
    target = DUMMY_DIGEST
    docr_pages = {
        "primary": {
            "manifests": [{"digest": other}],
            "meta": {"total": 2},
            "links": {
                "pages": {
                    "next": (
                        "https://api.digitalocean.com/v2/registry/eduvijna-registry"
                        "/repositories/aieos-backend/digests?page=2&per_page=200"
                    )
                }
            },
        },
        "legacy": {
            "manifests": [{"digest": target}],
            "meta": {"total": 2},
            "links": {"pages": {}},
        },
    }

    def docr_ok(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/v2/registries/"):
            return httpx.Response(200, json=docr_pages["primary"])
        return httpx.Response(200, json=docr_pages["legacy"])

    with _client(docr_ok) as c:
        assert c.prove_registry_digest_exists(
            registry="eduvijna-registry", repository="aieos-backend", digest=target
        )

    # with_projects remains rejected on DOCR pagination (R4)
    def docr_with_projects(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "manifests": [{"digest": other}],
                "meta": {"total": 2},
                "links": {
                    "pages": {
                        "next": (
                            "https://api.digitalocean.com/v2/registries/eduvijna-registry"
                            "/repositories/aieos-backend/digests"
                            "?page=2&per_page=200&with_projects=true"
                        )
                    }
                },
            },
        )

    with _client(docr_with_projects) as c:
        with pytest.raises(ProviderReadError):
            c.prove_registry_digest_exists(
                registry="eduvijna-registry", repository="aieos-backend", digest=target
            )

    # with_projects remains rejected on deployments pagination (R4)
    def deployments_with_projects(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "deployments": [{"id": "dep-1"}],
                "meta": {"total": 2},
                "links": {
                    "pages": {
                        "next": (
                            f"https://api.digitalocean.com/v2/apps/{DUMMY_APP_ID}/deployments"
                            "?page=2&per_page=200&with_projects=true"
                        )
                    }
                },
            },
        )

    with _client(deployments_with_projects) as c:
        with pytest.raises(ProviderReadError):
            c.get_app_deployments(DUMMY_APP_ID)

    # Accepted R4 forms for deployments (page/per_page only)
    dep_pages = {
        1: {
            "deployments": [{"id": "dep-1"}],
            "meta": {"total": 2},
            "links": {
                "pages": {
                    "next": (
                        f"https://api.digitalocean.com/v2/apps/{DUMMY_APP_ID}/deployments"
                        "?page=2&per_page=200"
                    )
                }
            },
        },
        2: {
            "deployments": [{"id": "dep-2"}],
            "meta": {"total": 2},
            "links": {"pages": {}},
        },
    }

    def deployments_ok(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        assert "with_projects" not in request.url.params
        return httpx.Response(200, json=dep_pages[page])

    with _client(deployments_ok) as c:
        assert len(c.get_app_deployments(DUMMY_APP_ID)) == 2

    reject_queries = (
        "foo=bar",
        "name=x",
        "deployment_types=MANUAL",
        "page=2&foo=bar&with_projects=true",
        "page=2&per_page=200&extra=x&with_projects=true",
        "page=2&page=3&with_projects=true",
        "per_page=20&per_page=200&with_projects=true",
        "page=0&with_projects=true",
        "page=-1&with_projects=true",
        "page=abc&with_projects=true",
        "page=2&per_page=0&with_projects=true",
        "page=2&per_page=201&with_projects=true",
        "page=2&per_page=abc&with_projects=true",
        "page=2&name=x&with_projects=true",
    )
    for q in reject_queries:
        next_url = f"https://api.digitalocean.com/v2/apps?{q}"
        with _client(page1_with_next(next_url)) as c:
            with pytest.raises(ProviderReadError):
                c.list_apps()

    with _client(
        page1_with_next(
            "https://api.digitalocean.com/v2/apps?page=2&with_projects=true#frag"
        )
    ) as c:
        with pytest.raises(ProviderReadError, match="fragment"):
            c.list_apps()

    with _client(
        page1_with_next(
            "https://user:pass@api.digitalocean.com/v2/apps?page=2&with_projects=true"
        )
    ) as c:
        with pytest.raises(ProviderReadError, match="userinfo"):
            c.list_apps()


def test_list_apps_first_request_with_projects() -> None:
    """Initial List Apps request must be page=1&per_page=200&with_projects=true."""
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json={"apps": [], "meta": {"total": 0}, "links": {}})

    with _client(handler) as c:
        assert c.list_apps() == []
    assert len(seen) == 1
    assert seen[0].path == "/v2/apps"
    assert seen[0].params.get("page") == "1"
    assert seen[0].params.get("per_page") == "200"
    assert seen[0].params.get("with_projects") == "true"
    assert list(seen[0].params.keys()) == ["page", "per_page", "with_projects"]


def test_list_apps_documented_zero_with_empty_array() -> None:
    """Documented zero-App List Apps shape with explicit empty apps array."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/apps"
        assert request.url.params.get("with_projects") == "true"
        return httpx.Response(200, json={"apps": [], "meta": {"total": 0}})

    with _client(handler) as c:
        assert c.list_apps() == []


def test_list_apps_live_observed_zero_omitted_apps_key() -> None:
    """TV01 live evidence: DigitalOcean may omit apps when meta.total=0."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/apps"
        assert request.url.params.get("with_projects") == "true"
        return httpx.Response(200, json={"meta": {"total": 0}})

    with _client(handler) as c:
        assert c.list_apps() == []


def test_list_apps_omitted_apps_nonzero_total_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"meta": {"total": 1}})

    with _client(handler) as c:
        with pytest.raises(ProviderReadError, match="malformed apps"):
            c.list_apps()


def test_list_apps_omitted_apps_negative_total_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"meta": {"total": -1}})

    with _client(handler) as c:
        with pytest.raises(ProviderReadError):
            c.list_apps()


def test_list_apps_omitted_apps_missing_meta_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    with _client(handler) as c:
        with pytest.raises(ProviderReadError):
            c.list_apps()


def test_list_apps_omitted_apps_malformed_total_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"meta": {"total": "0"}})

    with _client(handler) as c:
        with pytest.raises(ProviderReadError):
            c.list_apps()


def test_list_apps_explicit_malformed_apps_fails_even_when_total_zero() -> None:
    """PRESENT but non-list apps must not be reinterpreted as empty."""

    def null_apps(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"apps": None, "meta": {"total": 0}})

    def string_apps(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"apps": "not-a-list", "meta": {"total": 0}})

    with _client(null_apps) as c:
        with pytest.raises(ProviderReadError, match="malformed apps"):
            c.list_apps()
    with _client(string_apps) as c:
        with pytest.raises(ProviderReadError, match="malformed apps"):
            c.list_apps()


def test_deployments_omitted_collection_remains_strict_when_total_zero() -> None:
    """Non-List-Apps collections must not accept omitted keys merely because total=0."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"meta": {"total": 0}})

    with _client(handler) as c:
        with pytest.raises(ProviderReadError, match="malformed deployments"):
            c.get_app_deployments(DUMMY_APP_ID)


def test_oci_digest_paginated_exact_match_fail_closed() -> None:
    target = DUMMY_DIGEST
    other = "sha256:" + ("b" * 64)

    # Documented: first request plural /registries; next uses legacy singular /registry
    pages: dict[str, dict] = {
        "primary": {
            "manifests": [{"digest": other}],
            "meta": {"total": 2},
            "links": {
                "pages": {
                    "next": "https://api.digitalocean.com/v2/registry/eduvijna-registry/repositories/aieos-backend/digests?page=2&per_page=200"
                }
            },
        },
        "legacy": {
            "manifests": [{"digest": target}],
            "meta": {"total": 2},
            "links": {"pages": {}},
        },
    }
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        assert request.method == "GET"
        if request.url.path == "/v2/registries/eduvijna-registry/repositories/aieos-backend/digests":
            return httpx.Response(200, json=pages["primary"])
        if request.url.path == "/v2/registry/eduvijna-registry/repositories/aieos-backend/digests":
            return httpx.Response(200, json=pages["legacy"])
        raise AssertionError(f"unexpected path {request.url.path}")

    with _client(handler) as c:
        assert c.prove_registry_digest_exists(
            registry="eduvijna-registry", repository="aieos-backend", digest=target
        )
    assert seen_paths == [
        "/v2/registries/eduvijna-registry/repositories/aieos-backend/digests",
        "/v2/registry/eduvijna-registry/repositories/aieos-backend/digests",
    ]

    def missing_target(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"manifests": [{"digest": other}], "meta": {"total": 1}, "links": {}}
        )

    with _client(missing_target) as c:
        assert (
            c.prove_registry_digest_exists(
                registry="eduvijna-registry", repository="aieos-backend", digest=target
            )
            is False
        )

    def incomplete(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"manifests": [{"digest": other}], "meta": {"total": 2}, "links": {}}
        )

    with _client(incomplete) as c:
        with pytest.raises(ProviderReadError, match="incomplete enumeration"):
            c.prove_registry_digest_exists(
                registry="eduvijna-registry", repository="aieos-backend", digest=target
            )

    def missing_key(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"meta": {"total": 0}, "links": {}})

    with _client(missing_key) as c:
        with pytest.raises(ProviderReadError):
            c.prove_registry_digest_exists(
                registry="eduvijna-registry", repository="aieos-backend", digest=target
            )

    def not_array(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"manifests": 123, "meta": {"total": 0}})

    with _client(not_array) as c:
        with pytest.raises(ProviderReadError):
            c.prove_registry_digest_exists(
                registry="eduvijna-registry", repository="aieos-backend", digest=target
            )

    def not_object(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"manifests": [target], "meta": {"total": 1}, "links": {}}
        )

    with _client(not_object) as c:
        with pytest.raises(ProviderReadError):
            c.prove_registry_digest_exists(
                registry="eduvijna-registry", repository="aieos-backend", digest=target
            )

    def missing_digest_field(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"manifests": [{"tag": "latest"}], "meta": {"total": 1}, "links": {}}
        )

    with _client(missing_digest_field) as c:
        with pytest.raises(ProviderReadError):
            c.prove_registry_digest_exists(
                registry="eduvijna-registry", repository="aieos-backend", digest=target
            )

    def malformed_digest(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"manifests": [{"digest": "latest"}], "meta": {"total": 1}, "links": {}}
        )

    with _client(malformed_digest) as c:
        with pytest.raises(ProviderReadError):
            c.prove_registry_digest_exists(
                registry="eduvijna-registry", repository="aieos-backend", digest=target
            )

    def invent_digests_key(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"digests": [{"digest": target}], "meta": {"total": 1}, "links": {}}
        )

    with _client(invent_digests_key) as c:
        with pytest.raises(ProviderReadError):
            c.prove_registry_digest_exists(
                registry="eduvijna-registry", repository="aieos-backend", digest=target
            )

    def missing_meta(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"manifests": [], "links": {}})

    with _client(missing_meta) as c:
        with pytest.raises(ProviderReadError, match="meta"):
            c.prove_registry_digest_exists(
                registry="eduvijna-registry", repository="aieos-backend", digest=target
            )

    for bad_total in (None, "2", True, -1, 1.5):
        payload = {"manifests": [], "meta": {"total": bad_total} if bad_total is not None else {}, "links": {}}
        if bad_total is None:
            payload["meta"] = {}

        def bad_meta(request: httpx.Request, p=payload) -> httpx.Response:
            return httpx.Response(200, json=p)

        with _client(bad_meta) as c:
            with pytest.raises(ProviderReadError):
                c.prove_registry_digest_exists(
                    registry="eduvijna-registry", repository="aieos-backend", digest=target
                )

    def evil_next(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "manifests": [{"digest": other}],
                "meta": {"total": 2},
                "links": {
                    "pages": {
                        "next": "https://evil.example/v2/registry/eduvijna-registry/repositories/aieos-backend/digests?page=2"
                    }
                },
            },
        )

    with _client(evil_next) as c:
        with pytest.raises(ProviderReadError):
            c.prove_registry_digest_exists(
                registry="eduvijna-registry", repository="aieos-backend", digest=target
            )

    def http_next(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "manifests": [{"digest": other}],
                "meta": {"total": 2},
                "links": {
                    "pages": {
                        "next": "http://api.digitalocean.com/v2/registry/eduvijna-registry/repositories/aieos-backend/digests?page=2"
                    }
                },
            },
        )

    with _client(http_next) as c:
        with pytest.raises(ProviderReadError, match="HTTPS"):
            c.prove_registry_digest_exists(
                registry="eduvijna-registry", repository="aieos-backend", digest=target
            )

    def wrong_registry_legacy(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "manifests": [{"digest": other}],
                "meta": {"total": 2},
                "links": {
                    "pages": {
                        "next": "https://api.digitalocean.com/v2/registry/other-registry/repositories/aieos-backend/digests?page=2"
                    }
                },
            },
        )

    with _client(wrong_registry_legacy) as c:
        with pytest.raises(ProviderReadError):
            c.prove_registry_digest_exists(
                registry="eduvijna-registry", repository="aieos-backend", digest=target
            )

    def wrong_repo_legacy(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "manifests": [{"digest": other}],
                "meta": {"total": 2},
                "links": {
                    "pages": {
                        "next": "https://api.digitalocean.com/v2/registry/eduvijna-registry/repositories/other-repo/digests?page=2"
                    }
                },
            },
        )

    with _client(wrong_repo_legacy) as c:
        with pytest.raises(ProviderReadError):
            c.prove_registry_digest_exists(
                registry="eduvijna-registry", repository="aieos-backend", digest=target
            )

    def digest_specific_path(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "manifests": [{"digest": other}],
                "meta": {"total": 2},
                "links": {
                    "pages": {
                        "next": f"https://api.digitalocean.com/v2/registry/eduvijna-registry/repositories/aieos-backend/digests/{target}"
                    }
                },
            },
        )

    with _client(digest_specific_path) as c:
        with pytest.raises(ProviderReadError):
            c.prove_registry_digest_exists(
                registry="eduvijna-registry", repository="aieos-backend", digest=target
            )

    loop_hits = {"n": 0}

    def pagination_loop(request: httpx.Request) -> httpx.Response:
        loop_hits["n"] += 1
        return httpx.Response(
            200,
            json={
                "manifests": [{"digest": other}],
                "meta": {"total": 2},
                "links": {
                    "pages": {
                        "next": "https://api.digitalocean.com/v2/registries/eduvijna-registry/repositories/aieos-backend/digests?page=1&per_page=200"
                    }
                },
            },
        )

    with _client(pagination_loop) as c:
        with pytest.raises(ProviderReadError, match="loop"):
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
