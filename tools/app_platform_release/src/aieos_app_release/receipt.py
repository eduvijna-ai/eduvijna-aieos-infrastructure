"""Sanitized release-receipt model/serializer."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aieos_app_release.errors import ReceiptPolicyError
from aieos_app_release.secrets import assert_no_secret_leak

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

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
    }
)


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
            if not item.isupper() and not all(c.isalnum() or c == "_" for c in item):
                raise ValueError("secret key name invalid")
            if "EV[" in item or "=" in item:
                raise ValueError("secret values forbidden in key names")
        return v

    @model_validator(mode="before")
    @classmethod
    def _forbid_keys(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        lowered = {str(k).lower(): k for k in data}
        for bad in FORBIDDEN_KEYS:
            if bad in lowered:
                raise ReceiptPolicyError(f"forbidden receipt field: {lowered[bad]}")

        def _scan(obj: Any, path: str) -> None:
            if isinstance(obj, str):
                if obj.startswith("EV[") or "EV[" in obj:
                    raise ReceiptPolicyError(f"forbidden secret-like value in field {path}")
                lowered_v = obj.lower()
                if (
                    "bearer " in lowered_v
                    or "authorization:" in lowered_v
                    or "postgres://" in lowered_v
                    or "postgresql://" in lowered_v
                ):
                    raise ReceiptPolicyError(f"forbidden secret-like value in field {path}")
                return
            if isinstance(obj, dict):
                for k, v in obj.items():
                    _scan(v, f"{path}.{k}")
                return
            if isinstance(obj, list):
                for i, v in enumerate(obj):
                    _scan(v, f"{path}[{i}]")

        for k, v in data.items():
            _scan(v, str(k))
        return data


def serialize_receipt(receipt: StrictReceipt) -> bytes:
    payload = receipt.model_dump(exclude={"receipt_sha256"})
    assert_no_secret_leak(payload)
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    payload["receipt_sha256"] = f"sha256:{digest}"
    assert_no_secret_leak(payload)
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
