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
    expected_project_uuid: str | None
    expected_vpc_uuid: str | None
    current_apps: list[dict[str, Any]]
    current_app: dict[str, Any] | None
    deployments: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class ReconciliationDecision:
    classification: ReconciliationClass
    detail: str
    mutate_again: bool = False


def _app_name(app: dict[str, Any]) -> str | None:
    spec = app.get("spec")
    if isinstance(spec, dict) and isinstance(spec.get("name"), str):
        return spec["name"]
    name = app.get("name")
    return name if isinstance(name, str) else None


def _app_project(app: dict[str, Any]) -> str | None:
    for key in ("project_id", "project_uuid"):
        val = app.get(key)
        if isinstance(val, str):
            return val
    return None


def _app_vpc(app: dict[str, Any]) -> str | None:
    for key in ("vpc_uuid", "vpc_id"):
        val = app.get(key)
        if isinstance(val, str):
            return val
    spec = app.get("spec")
    if isinstance(spec, dict):
        ingress = spec.get("ingress") or spec.get("vpc")
        if isinstance(ingress, dict) and isinstance(ingress.get("id"), str):
            return ingress["id"]
        if isinstance(spec.get("vpc_uuid"), str):
            return spec["vpc_uuid"]
    return None


def _managed_from_app(app: dict[str, Any]) -> dict[str, Any] | None:
    managed = app.get("managed_projection")
    if isinstance(managed, dict):
        return managed
    spec = app.get("spec")
    if isinstance(spec, dict):
        return spec
    return None


def reconcile_mutation_result(inp: ReconciliationInput) -> ReconciliationDecision:
    """Classify provider observations. Never mutates. Never auto-retries mutation."""
    matches = [a for a in inp.current_apps if _app_name(a) == inp.expected_app_name]

    if inp.expected_app_id is None:
        # CREATE reconciliation — name alone is insufficient for COMMITTED
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
        managed = _managed_from_app(app)
        if managed is None:
            return ReconciliationDecision(
                ReconciliationClass.AMBIGUOUS,
                "CREATE observed name but managed projection unavailable",
                mutate_again=False,
            )
        if inp.expected_project_uuid is None or inp.expected_vpc_uuid is None:
            return ReconciliationDecision(
                ReconciliationClass.AMBIGUOUS,
                "CREATE reconciliation missing authorized project/VPC evidence",
                mutate_again=False,
            )
        if _app_project(app) != inp.expected_project_uuid:
            return ReconciliationDecision(
                ReconciliationClass.AMBIGUOUS,
                "CREATE observed App project evidence insufficient/mismatch",
                mutate_again=False,
            )
        if _app_vpc(app) != inp.expected_vpc_uuid:
            return ReconciliationDecision(
                ReconciliationClass.AMBIGUOUS,
                "CREATE observed App VPC evidence insufficient/mismatch",
                mutate_again=False,
            )
        fp = fingerprint_managed_spec(managed)
        if fp != inp.expected_managed_fingerprint:
            return ReconciliationDecision(
                ReconciliationClass.AMBIGUOUS,
                "CREATE observed App managed fingerprint mismatch",
                mutate_again=False,
            )
        if inp.expected_deployment_id:
            dep_ids = {str(d.get("id")) for d in inp.deployments}
            if inp.expected_deployment_id not in dep_ids:
                return ReconciliationDecision(
                    ReconciliationClass.AMBIGUOUS,
                    "CREATE missing expected deployment identity",
                    mutate_again=False,
                )
        return ReconciliationDecision(
            ReconciliationClass.COMMITTED,
            "CREATE bound by name+project+VPC+managed fingerprint",
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

    managed = _managed_from_app(inp.current_app)
    if managed is None:
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
        if inp.expected_deployment_id in dep_ids and fp == inp.expected_managed_fingerprint:
            return ReconciliationDecision(
                ReconciliationClass.COMMITTED,
                "expected deployment id present with matching fingerprint",
                mutate_again=False,
            )

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
