"""Shared fixtures: network denial + contract paths."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_CONTRACT = REPO_ROOT / "contracts" / "app-platform" / "production-workflow-runtime.yaml"
RELEASE_CONTRACT = REPO_ROOT / "contracts" / "app-platform" / "production-release-plane.yaml"

DUMMY_APP_ID = "11111111-1111-4111-8111-111111111111"
DUMMY_PROJECT = "22222222-2222-4222-8222-222222222222"
DUMMY_VPC = "33333333-3333-4333-8333-333333333333"
DUMMY_DIGEST = "sha256:" + ("a" * 64)
DUMMY_SHA = "a" * 40


@pytest.fixture(autouse=True)
def deny_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Adversarial: no test may open a real external socket."""

    real_create = socket.socket

    class GuardedSocket(real_create):  # type: ignore[valid-type,misc]
        def connect(self, address):  # noqa: ANN001
            host = address[0] if isinstance(address, tuple) else address
            if host not in {"127.0.0.1", "::1", "localhost"}:
                raise RuntimeError(f"network denied for host={host!r}")
            return super().connect(address)

        def connect_ex(self, address):  # noqa: ANN001
            host = address[0] if isinstance(address, tuple) else address
            if host not in {"127.0.0.1", "::1", "localhost"}:
                raise RuntimeError(f"network denied for host={host!r}")
            return super().connect_ex(address)

    monkeypatch.setattr(socket, "socket", GuardedSocket)
