"""Read-only ambiguous-result reconciliation decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from aieos_app_release.errors import ReconciliationConflictError
from aieos_app_release.fingerprint import fingerprint_managed_spec


class ReconciliationClass(str, Enum):
    COMMITTED = "COMMITTED"
    NOT_COMMITTED = "NOT_COMMITTED"
    AMBIGUOUS = "AMBIGUOUS"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True, slots=True)
class ReconciliationInput:
    expected_app_name: str
    expected_app_id: str | None
    expected_managed_fingerprint: str
    expected_deployment_id: str | None
    current_apps: list[dict[str, Any]]
    current_app: dict[str, Any] | None
    deployments: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class ReconciliationDecision:
    classification: ReconciliationClass
    detail: str
    mutate_again: bool = False


def reconcile_mutation_result(inp: ReconciliationInput) -> ReconciliationDecision:
    """Classify provider observations. Never mutates. Never auto-retries mutation."""
    matches = [
        a
        for a in inp.current_apps
        if a.get("spec", {}).get("name") == inp.expected_app_name
        or a.get("name") == inp.expected_app_name
    ]

    if inp.expected_app_id is None:
        # CREATE reconciliation
        if len(matches) == 0:
            return ReconciliationDecision(
                ReconciliationClass.NOT_COMMITTED,
                "target App absent after CREATE ambiguity",
                mutate_again=False,
            )
        if len(matches) > 1:
            return ReconciliationDecision(
                ReconciliationClass.CONFLICT,
                "multiple Apps match semantic name",
                mutate_again=False,
            )
        app = matches[0]
        return ReconciliationDecision(
            ReconciliationClass.COMMITTED,
            f"create observed app_id={app.get('id')}",
            mutate_again=False,
        )

    # UPDATE / ROTATE path
    if inp.current_app is None:
        if len(matches) == 0:
            return ReconciliationDecision(
                ReconciliationClass.AMBIGUOUS,
                "authorized App missing during reconciliation",
                mutate_again=False,
            )
        return ReconciliationDecision(
            ReconciliationClass.AMBIGUOUS,
            "current App projection unavailable",
            mutate_again=False,
        )

    observed_id = str(inp.current_app.get("id", ""))
    if observed_id != inp.expected_app_id:
        return ReconciliationDecision(
            ReconciliationClass.CONFLICT,
            "App identity conflict during reconciliation",
            mutate_again=False,
        )

    managed = inp.current_app.get("managed_projection") or inp.current_app.get("spec") or {}
    if not isinstance(managed, dict):
        return ReconciliationDecision(
            ReconciliationClass.AMBIGUOUS,
            "managed projection unavailable",
            mutate_again=False,
        )
    fp = fingerprint_managed_spec(managed)
    if fp == inp.expected_managed_fingerprint:
        return ReconciliationDecision(
            ReconciliationClass.COMMITTED,
            "managed fingerprint matches expected release",
            mutate_again=False,
        )

    if inp.expected_deployment_id:
        dep_ids = {str(d.get("id")) for d in inp.deployments}
        if inp.expected_deployment_id in dep_ids:
            return ReconciliationDecision(
                ReconciliationClass.COMMITTED,
                "expected deployment id present",
                mutate_again=False,
            )

    # Fingerprint mismatch without confirming deployment evidence
    if not inp.deployments and fp != inp.expected_managed_fingerprint:
        return ReconciliationDecision(
            ReconciliationClass.NOT_COMMITTED,
            "expected managed state not observed",
            mutate_again=False,
        )

    return ReconciliationDecision(
        ReconciliationClass.AMBIGUOUS,
        "unable to determine commit status safely",
        mutate_again=False,
    )


def assert_no_auto_mutation(decision: ReconciliationDecision) -> None:
    if decision.mutate_again:
        raise ReconciliationConflictError("reconciliation must not auto-mutate")
