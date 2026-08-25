"""Pure release state machine (provider-I/O independent)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from aieos_app_release.errors import IllegalStateTransitionError


class ReleaseState(str, Enum):
    SOURCE_GATE = "SOURCE_GATE"
    LEASE_ACQUIRED = "LEASE_ACQUIRED"
    PROVIDER_PREFLIGHT = "PROVIDER_PREFLIGHT"
    LIVE_SPEC_READ_1 = "LIVE_SPEC_READ_1"
    ALLOWLIST_VALIDATE = "ALLOWLIST_VALIDATE"
    DESIRED_SPEC_IN_MEMORY = "DESIRED_SPEC_IN_MEMORY"
    LIVE_SPEC_READ_2 = "LIVE_SPEC_READ_2"
    STALE_WRITE_FENCE = "STALE_WRITE_FENCE"
    MUTATION_SENT_ONCE = "MUTATION_SENT_ONCE"
    RESULT_RECONCILIATION = "RESULT_RECONCILIATION"
    DEPLOYMENT_VERIFY = "DEPLOYMENT_VERIFY"
    RECEIPT = "RECEIPT"
    PROCESS_EXIT = "PROCESS_EXIT"


LEGAL_TRANSITIONS: dict[ReleaseState, frozenset[ReleaseState]] = {
    ReleaseState.SOURCE_GATE: frozenset({ReleaseState.LEASE_ACQUIRED, ReleaseState.PROCESS_EXIT}),
    ReleaseState.LEASE_ACQUIRED: frozenset(
        {ReleaseState.PROVIDER_PREFLIGHT, ReleaseState.PROCESS_EXIT}
    ),
    ReleaseState.PROVIDER_PREFLIGHT: frozenset(
        {ReleaseState.LIVE_SPEC_READ_1, ReleaseState.PROCESS_EXIT}
    ),
    ReleaseState.LIVE_SPEC_READ_1: frozenset(
        {ReleaseState.ALLOWLIST_VALIDATE, ReleaseState.PROCESS_EXIT}
    ),
    ReleaseState.ALLOWLIST_VALIDATE: frozenset(
        {ReleaseState.DESIRED_SPEC_IN_MEMORY, ReleaseState.PROCESS_EXIT}
    ),
    ReleaseState.DESIRED_SPEC_IN_MEMORY: frozenset(
        {ReleaseState.LIVE_SPEC_READ_2, ReleaseState.PROCESS_EXIT}
    ),
    ReleaseState.LIVE_SPEC_READ_2: frozenset(
        {ReleaseState.STALE_WRITE_FENCE, ReleaseState.PROCESS_EXIT}
    ),
    ReleaseState.STALE_WRITE_FENCE: frozenset(
        {ReleaseState.MUTATION_SENT_ONCE, ReleaseState.PROCESS_EXIT}
    ),
    ReleaseState.MUTATION_SENT_ONCE: frozenset({ReleaseState.RESULT_RECONCILIATION}),
    ReleaseState.RESULT_RECONCILIATION: frozenset(
        {ReleaseState.DEPLOYMENT_VERIFY, ReleaseState.RECEIPT, ReleaseState.PROCESS_EXIT}
    ),
    ReleaseState.DEPLOYMENT_VERIFY: frozenset(
        {ReleaseState.RECEIPT, ReleaseState.PROCESS_EXIT}
    ),
    ReleaseState.RECEIPT: frozenset({ReleaseState.PROCESS_EXIT}),
    ReleaseState.PROCESS_EXIT: frozenset(),
}


@dataclass
class ReleaseStateMachine:
    state: ReleaseState = ReleaseState.SOURCE_GATE
    history: list[ReleaseState] = field(default_factory=list)
    mutation_transmitted: bool = False

    def __post_init__(self) -> None:
        self.history.append(self.state)

    def transition(self, new_state: ReleaseState) -> None:
        allowed = LEGAL_TRANSITIONS[self.state]
        if new_state not in allowed:
            raise IllegalStateTransitionError(
                f"illegal transition {self.state.value} -> {new_state.value}"
            )
        if (
            self.state is ReleaseState.MUTATION_SENT_ONCE
            and new_state is not ReleaseState.RESULT_RECONCILIATION
        ):
            raise IllegalStateTransitionError(
                "uncertainty after MUTATION_SENT_ONCE must enter RESULT_RECONCILIATION only"
            )
        if new_state is ReleaseState.MUTATION_SENT_ONCE:
            if self.mutation_transmitted:
                raise IllegalStateTransitionError("mutation already transmitted once")
            self.mutation_transmitted = True
        # Forbid jumping back to mutation from reconciliation
        if (
            self.state is ReleaseState.RESULT_RECONCILIATION
            and new_state is ReleaseState.MUTATION_SENT_ONCE
        ):
            raise IllegalStateTransitionError("blind mutation retry from reconciliation forbidden")
        self.state = new_state
        self.history.append(new_state)

    def mark_ambiguous_after_mutation(self) -> None:
        if self.state is not ReleaseState.MUTATION_SENT_ONCE:
            # allow if already about to reconcile
            if self.state is ReleaseState.RESULT_RECONCILIATION:
                return
            raise IllegalStateTransitionError(
                "ambiguous mutation classification requires MUTATION_SENT_ONCE"
            )
        self.transition(ReleaseState.RESULT_RECONCILIATION)
