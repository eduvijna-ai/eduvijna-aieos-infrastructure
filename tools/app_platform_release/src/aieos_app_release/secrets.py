"""Secret-bearing value wrappers with mandatory redaction."""

from __future__ import annotations

import re
from typing import Any, Iterator

REDACTED = "***REDACTED***"
SECRET_SENTINEL = "__AIEOS_SECRET_SENTINEL__"
_EV_PATTERN = re.compile(r"EV\[[A-Za-z0-9+/=_-]+\]")


class SecretValue:
    """Opaque holder for plaintext or DigitalOcean EV[...] secret material."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("SecretValue requires str")
        object.__setattr__(self, "_value", value)

    def reveal(self) -> str:
        return object.__getattribute__(self, "_value")

    def is_ev(self) -> bool:
        return object.__getattribute__(self, "_value").startswith("EV[")

    def __str__(self) -> str:
        return REDACTED

    def __repr__(self) -> str:
        return f"SecretValue({REDACTED!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SecretValue):
            return self.reveal() == other.reveal()
        return NotImplemented

    def __hash__(self) -> int:
        return hash(object.__getattribute__(self, "_value"))

    def __getstate__(self) -> None:
        raise TypeError("SecretValue must not be pickled/serialized")

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("SecretValue is immutable")


def is_secret_material(value: Any) -> bool:
    if isinstance(value, SecretValue):
        return True
    if isinstance(value, str) and (
        value.startswith("EV[") or _EV_PATTERN.fullmatch(value) is not None
    ):
        return True
    return False


def redact_text(text: str) -> str:
    return _EV_PATTERN.sub(REDACTED, text)


def walk_replace_secrets(obj: Any, *, replacement: Any = SECRET_SENTINEL) -> Any:
    """Deep-copy structure replacing secret VALUES with a structural sentinel."""
    if isinstance(obj, SecretValue):
        return replacement
    if isinstance(obj, str) and is_secret_material(obj):
        return replacement
    if isinstance(obj, dict):
        return {k: walk_replace_secrets(v, replacement=replacement) for k, v in obj.items()}
    if isinstance(obj, list):
        return [walk_replace_secrets(v, replacement=replacement) for v in obj]
    if isinstance(obj, tuple):
        return tuple(walk_replace_secrets(v, replacement=replacement) for v in obj)
    return obj


def assert_no_secret_leak(obj: Any, *, path: str = "$") -> None:
    """Recursively fail if secret material is present."""
    from .errors import ReceiptPolicyError

    if isinstance(obj, SecretValue):
        raise ReceiptPolicyError(f"secret material at {path}")
    if isinstance(obj, str):
        if obj.startswith("EV[") or "EV[" in obj:
            raise ReceiptPolicyError(f"EV material at {path}")
        lowered = obj.lower()
        if "authorization:" in lowered or "bearer " in lowered:
            raise ReceiptPolicyError(f"authorization material at {path}")
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert_no_secret_leak(v, path=f"{path}.{k}")
        return
    if isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            assert_no_secret_leak(v, path=f"{path}[{i}]")


def iter_strings(obj: Any) -> Iterator[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from iter_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from iter_strings(v)
