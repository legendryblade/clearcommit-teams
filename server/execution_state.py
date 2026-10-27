"""Execution state machine: the closed set of legal transitions.

The states are deliberately many. ``Succeeded``, ``PartiallyVerified``,
``Failed`` and ``Unknown`` are distinct because they mean different things to a
person reading the result, and collapsing them into a single "done" flag is the
failure mode the product exists to avoid.

    Running ──▶ Verifying ──▶ Succeeded
       │            ├───────▶ PartiallyVerified
       │            ├───────▶ Failed
       │            └───────▶ Unknown
       ├──▶ WaitingApproval ──▶ Running | Cancelled
       ├──▶ Blocked ──▶ Running | Cancelled
       └──▶ Cancelled

``Cancelled`` and the four terminal outcomes are final. Nothing leaves them.

Cancellation is not rollback: it stops eligible *future* work. An email already
sent or a payment already made is not undone by this state, and no caller may
infer that it was.
"""

from __future__ import annotations

from typing import Final

RUNNING: Final = "running"
WAITING_APPROVAL: Final = "waiting_approval"
BLOCKED: Final = "blocked"
VERIFYING: Final = "verifying"
SUCCEEDED: Final = "succeeded"
PARTIALLY_VERIFIED: Final = "partially_verified"
FAILED: Final = "failed"
UNKNOWN: Final = "unknown"
CANCELLED: Final = "cancelled"

STATES: Final[frozenset[str]] = frozenset(
    {
        RUNNING,
        WAITING_APPROVAL,
        BLOCKED,
        VERIFYING,
        SUCCEEDED,
        PARTIALLY_VERIFIED,
        FAILED,
        UNKNOWN,
        CANCELLED,
    }
)

TERMINAL: Final[frozenset[str]] = frozenset(
    {SUCCEEDED, PARTIALLY_VERIFIED, FAILED, UNKNOWN, CANCELLED}
)

# Outcomes a verifier may produce. ``Unknown`` is a real answer: it means the
# check could not establish the postcondition, which is not the same as failure.
VERIFIED_OUTCOMES: Final[frozenset[str]] = frozenset(
    {SUCCEEDED, PARTIALLY_VERIFIED, FAILED, UNKNOWN}
)

_LEGAL: Final[dict[str, frozenset[str]]] = {
    RUNNING: frozenset({WAITING_APPROVAL, BLOCKED, VERIFYING, CANCELLED}),
    WAITING_APPROVAL: frozenset({RUNNING, BLOCKED, CANCELLED}),
    BLOCKED: frozenset({RUNNING, CANCELLED}),
    VERIFYING: frozenset({SUCCEEDED, PARTIALLY_VERIFIED, FAILED, UNKNOWN}),
    SUCCEEDED: frozenset(),
    PARTIALLY_VERIFIED: frozenset(),
    FAILED: frozenset(),
    UNKNOWN: frozenset(),
    CANCELLED: frozenset(),
}


class IllegalTransition(ValueError):
    """A requested state change that the machine does not permit."""

    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"Cannot move an execution from {current!r} to {target!r}.")
        self.current = current
        self.target = target


def is_terminal(state: str) -> bool:
    return state in TERMINAL


def can_transition(current: str, target: str) -> bool:
    return target in _LEGAL.get(current, frozenset())


def legal_targets(current: str) -> frozenset[str]:
    return _LEGAL.get(current, frozenset())


def ensure_transition(current: str, target: str) -> None:
    """Raise :class:`IllegalTransition` unless the move is permitted."""
    if current not in STATES:
        raise IllegalTransition(current, target)
    if target not in STATES:
        raise IllegalTransition(current, target)
    if not can_transition(current, target):
        raise IllegalTransition(current, target)


def derive_outcome(passed: int, failed: int, unknown: int) -> str:
    """Turn verification results into an outcome.

    The ordering is a product rule, not a convenience: any failed check means
    the outcome is ``failed`` even when other checks passed, because a single
    unmet postcondition is enough to make the claim untrue. A mix of passes and
    unknowns is ``partially_verified`` — real work happened, but it is not
    proven. An empty run is ``unknown``, never ``succeeded``.
    """
    if passed < 0 or failed < 0 or unknown < 0:
        raise ValueError("Verification counts cannot be negative.")
    if failed > 0:
        return FAILED
    if passed > 0 and unknown == 0:
        return SUCCEEDED
    if passed > 0 and unknown > 0:
        return PARTIALLY_VERIFIED
    return UNKNOWN


def ensure_verdict(current: str, outcome: str) -> None:
    """A verdict may only be applied from ``Verifying``."""
    if current != VERIFYING:
        raise IllegalTransition(current, outcome)
    if outcome not in VERIFIED_OUTCOMES:
        raise IllegalTransition(current, outcome)
