"""Sanitized release-receipt model/serializer."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aieos_app_release.errors import ReceiptPolicyError
from aieos_app_release.secrets import assert_no_secret_leak

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SECRET_KEY_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

FORBIDDEN_KEYS = frozenset(
    {
        "appspec",
        "raw_appspec",
        "spec",
        "authorization",
        "authorization_header",
        "raw_http_request",
        "raw_http_response",
        "secret_hash",
        "secret_fingerprint",
        "secret_value",
        "pat",
        "token",
        "password",
        "database_url",
        "temporal_api_key",
        "ev",
        "dop_v1",
        "bearer",
    }
)

_SECRET_VALUE_MARKERS = (
    "ev[",
    "bearer ",
    "authorization:",
    "postgres://",
    "postgresql://",
    "dop_v1_",
    "eyj",  # JWT-ish
)


ALLOWED_TOP_LEVEL_FIELDS = frozenset(
    {
        "app_semantic_name",
        "app_uuid",
        "deployment_id",
        "project_uuid",
        "vpc_uuid",
        "architecture_sha",
        "infrastructure_sha",
        "backend_sha",
        "oci_digest",
        "release_identity",
        "build_identity",
        "github_run_id",
        "github_run_attempt",
        "concurrency_group",
        "managed_spec_fingerprint",
        "secret_key_names",
        "generation_labels",
        "provider_request_ids",
        "drift_classification",
        "verification_result",
        "rollback_result",
        "receipt_sha256",
    }
)


def _looks_like_secret_value(text: str) -> bool:
    lowered = text.lower()
    if any(m in lowered for m in _SECRET_VALUE_MARKERS):
        return True
    if text.startswith("EV["):
        return True
    if _DIGEST_RE.fullmatch(text) or _SHA_RE.fullmatch(text):
        return False
    if re.fullmatch(r"dop_v1_[A-Za-z0-9_\-]{20,}", text):
        return True
    if re.fullmatch(r"[A-Za-z0-9_\-]{48,}", text) and not text.startswith("sha256:"):
        return True
    return False


def _scan_secret_material(obj: Any, path: str = "$", *, allow_schema_keys: bool = False) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k)
            key_l = key.lower()
            if allow_schema_keys and path == "$" and key in ALLOWED_TOP_LEVEL_FIELDS:
                _scan_secret_material(v, f"{path}.{key}", allow_schema_keys=False)
                continue
            if key_l in FORBIDDEN_KEYS or any(
                bad == key_l or key_l.endswith("_" + bad) for bad in ("password", "token", "pat", "bearer")
            ):
                raise ReceiptPolicyError(f"forbidden receipt key at {path}.{key}")
            if _looks_like_secret_value(key):
                raise ReceiptPolicyError(f"secret-like receipt key at {path}.{key}")
            _scan_secret_material(v, f"{path}.{key}", allow_schema_keys=False)
        return
    if isinstance(obj, list):
        for i, v in enumerate(obj):
            _scan_secret_material(v, f"{path}[{i}]", allow_schema_keys=False)
        return
    if isinstance(obj, str) and _looks_like_secret_value(obj):
        raise ReceiptPolicyError(f"forbidden secret-like value in field {path}")


class StrictReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    app_semantic_name: str
    app_uuid: str | None = None
    deployment_id: str | None = None
    project_uuid: str | None = None
    vpc_uuid: str | None = None
    architecture_sha: str
    infrastructure_sha: str
    backend_sha: str
    oci_digest: str
    release_identity: str
    build_identity: str | None = None
    github_run_id: str
    github_run_attempt: str
    concurrency_group: str
    managed_spec_fingerprint: str
    secret_key_names: list[str] = Field(default_factory=list)
    generation_labels: dict[str, str] = Field(default_factory=dict)
    provider_request_ids: list[str] = Field(default_factory=list)
    drift_classification: str | None = None
    verification_result: str | None = None
    rollback_result: str | None = None
    receipt_sha256: str | None = None

    @field_validator(
        "app_uuid",
        "project_uuid",
        "vpc_uuid",
        mode="before",
    )
    @classmethod
    def _uuid_ok(cls, v: object) -> object:
        if v is None:
            return None
        if not isinstance(v, str) or not _UUID_RE.fullmatch(v):
            raise ValueError("invalid UUID")
        return v

    @field_validator("architecture_sha", "infrastructure_sha", "backend_sha")
    @classmethod
    def _sha(cls, v: str) -> str:
        if not _SHA_RE.fullmatch(v):
            raise ValueError("governed SHA must be 40 lowercase hex")
        return v

    @field_validator("oci_digest", "managed_spec_fingerprint")
    @classmethod
    def _digest(cls, v: str) -> str:
        if not _DIGEST_RE.fullmatch(v):
            raise ValueError("digest must be sha256:<64 lowercase hex>")
        return v

    @field_validator("secret_key_names")
    @classmethod
    def _keys_only(cls, v: list[str]) -> list[str]:
        for item in v:
            if not _SECRET_KEY_NAME_RE.fullmatch(item):
                raise ValueError("secret key name must be UPPER_SNAKE_CASE")
            if "EV[" in item or "=" in item or " " in item:
                raise ValueError("secret values forbidden in key names")
        return v

    @field_validator("generation_labels")
    @classmethod
    def _labels(cls, v: dict[str, str]) -> dict[str, str]:
        for k, val in v.items():
            if not re.fullmatch(r"^[a-z][a-z0-9_]*$", k):
                raise ValueError("generation label keys must be lowercase_snake")
            if _looks_like_secret_value(val) or _looks_like_secret_value(k):
                raise ValueError("generation labels must not contain secret-like material")
        return v

    @model_validator(mode="before")
    @classmethod
    def _forbid_keys(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        _scan_secret_material(data, allow_schema_keys=True)
        return data


def serialize_receipt(receipt: StrictReceipt) -> bytes:
    payload = receipt.model_dump(exclude={"receipt_sha256"})
    assert_no_secret_leak(payload)
    _scan_secret_material(payload, allow_schema_keys=True)
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    payload["receipt_sha256"] = f"sha256:{digest}"
    assert_no_secret_leak(payload)
    _scan_secret_material(payload, allow_schema_keys=True)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def parse_receipt(data: dict[str, Any]) -> StrictReceipt:
    try:
        return StrictReceipt.model_validate(data)
    except ReceiptPolicyError:
        raise
    except Exception as exc:
        raise ReceiptPolicyError(f"receipt rejected: {exc}") from exc
