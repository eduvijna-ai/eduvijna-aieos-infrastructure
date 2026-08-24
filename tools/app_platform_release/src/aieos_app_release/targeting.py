"""App targeting and bootstrap cardinality validators."""

from __future__ import annotations

from dataclasses import dataclass

from aieos_app_release.errors import TargetCardinalityError
from aieos_app_release.oci import validate_oci_digest


@dataclass(frozen=True, slots=True)
class SteadyStatePhysicalIds:
    app_semantic_name: str
    app_uuid: str
    project_uuid: str
    vpc_uuid: str


def assert_bootstrap_create_cardinality(target_app_count: int) -> None:
    if target_app_count != 0:
        raise TargetCardinalityError(
            "bootstrap CREATE requires target App cardinality exactly zero",
            detail=str(target_app_count),
        )


def assert_steady_state_identity(
    observed: SteadyStatePhysicalIds,
    authorized: SteadyStatePhysicalIds,
) -> None:
    if observed.app_semantic_name != authorized.app_semantic_name:
        raise TargetCardinalityError("App semantic name mismatch")
    if observed.app_uuid != authorized.app_uuid:
        raise TargetCardinalityError("App UUID mismatch")
    if observed.project_uuid != authorized.project_uuid:
        raise TargetCardinalityError("project UUID mismatch")
    if observed.vpc_uuid != authorized.vpc_uuid:
        raise TargetCardinalityError("VPC UUID mismatch")


def assert_release_digest(digest: str) -> str:
    return validate_oci_digest(digest)
