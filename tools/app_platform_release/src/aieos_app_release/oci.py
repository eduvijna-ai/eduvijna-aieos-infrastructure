"""OCI digest validation (offline)."""

from __future__ import annotations

import re

from aieos_app_release.errors import OciDigestError

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def validate_oci_digest(digest: str) -> str:
    if not isinstance(digest, str) or not digest:
        raise OciDigestError("OCI digest must be non-empty string")
    if digest == "latest" or ":" not in digest and "/" not in digest and digest.isalnum():
        # bare tag-like
        if digest == "latest" or not digest.startswith("sha256:"):
            raise OciDigestError("mutable tags are forbidden; require sha256 digest")
    if digest.startswith("sha256:") and any(c.isupper() for c in digest):
        raise OciDigestError("OCI digest must be lowercase sha256 hex")
    if not _DIGEST_RE.fullmatch(digest):
        if digest.startswith("sha256:") and len(digest) != len("sha256:") + 64:
            raise OciDigestError("OCI digest length invalid")
        if not digest.startswith("sha256:"):
            raise OciDigestError("OCI digest must use sha256 algorithm")
        raise OciDigestError("OCI digest format invalid")
    return digest
