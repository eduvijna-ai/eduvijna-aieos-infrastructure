"""Canonical managed-spec fingerprinting (ADR-AIEOS-050)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from aieos_app_release.secrets import SECRET_SENTINEL, walk_replace_secrets


def canonicalize_managed_projection(managed: dict[str, Any]) -> bytes:
    """Deterministic UTF-8 JSON with sorted keys and compact separators."""
    redacted = walk_replace_secrets(managed, replacement=SECRET_SENTINEL)
    return json.dumps(
        redacted,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def fingerprint_managed_spec(managed: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonicalize_managed_projection(managed)).hexdigest()
    return f"sha256:{digest}"
