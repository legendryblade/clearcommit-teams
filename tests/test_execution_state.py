"""The state machine must be exhaustive, not sampled.

These are the rules a person relies on when reading an execution, so each is
pinned individually rather than inferred from one happy path.
"""

from __future__ import annotations

import pytest

from server.execution_state import (
    BLOCKED,
    CANCELLED,
    FAILED,
    PARTIALLY_VERIFIED,
    RUNNING,
    STATES,
    SUCCEEDED,
    TERMINAL,
    UNKNOWN,
    VERIFYING,
    WAITING_APPROVAL,
    IllegalTransition,
    can_transition,
    derive_outcome,
    ensure_transition,
    ensure_verdict,
    is_terminal,
    legal_targets,
)


def test_state_set_is_closed():
    assert STATES == {
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


@pytest.mark.parametrize("state", sorted(STATES))
def test_every_state_has_a_transition_row(state):
    assert legal_targets(state) <= STATES


@pytest.mark.parametrize("state", sorted(TERMINAL))
def test_terminal_states_leave_nowhere(state):
    assert legal_targets(state) == frozenset()
    assert is_terminal(state)
    for target in STATES:
        assert not can_transition(state, target)


@pytest.mark.parametrize(
    "current,target",
    [
        (RUNNING, VERIFYING),
        (RUNNING, WAITING_APPROVAL),
        (RUNNING, BLOCKED),
        (RUNNING, CANCELLED),
        (WAITING_APPROVAL, RUNNING),
        (WAITING_APPROVAL, BLOCKED),
        (WAITING_APPROVAL, CANCELLED),
        (BLOCKED, RUNNING),
        (BLOCKED, CANCELLED),
        (VERIFYING, SUCCEEDED),
        (VERIFYING, PARTIALLY_VERIFIED),
        (VERIFYING, FAILED),
        (VERIFYING, UNKNOWN),
    ],
)
def test_legal_transitions(current, target):
    ensure_transition(current, target)


@pytest.mark.parametrize(
    "current,target",
    [
        (RUNNING, SUCCEEDED),
        (RUNNING, FAILED),
        (RUNNING, UNKNOWN),
        (RUNNING, PARTIALLY_VERIFIED),
        (BLOCKED, VERIFYING),
        (BLOCKED, SUCCEEDED),
        (WAITING_APPROVAL, VERIFYING),
        (WAITING_APPROVAL, SUCCEEDED),
        (VERIFYING, RUNNING),
        (VERIFYING, CANCELLED),
        (SUCCEEDED, RUNNING),
        (SUCCEEDED, CANCELLED),
        (FAILED, RUNNING),
        (CANCELLED, RUNNING),
        (UNKNOWN, VERIFYING),
    ],
)
def test_illegal_transitions_raise(current, target):
    with pytest.raises(IllegalTransition):
        ensure_transition(current, target)


def test_a_run_cannot_claim_success_without_verifying():
    with pytest.raises(IllegalTransition):
        ensure_transition(RUNNING, SUCCEEDED)
    with pytest.raises(IllegalTransition):
        ensure_transition(BLOCKED, SUCCEEDED)


def test_cancellation_is_terminal_and_is_not_rollback():
    ensure_transition(RUNNING, CANCELLED)
    assert is_terminal(CANCELLED)
    for target in STATES:
        with pytest.raises(IllegalTransition):
            ensure_transition(CANCELLED, target)


def test_unknown_state_is_rejected():
    with pytest.raises(IllegalTransition):
        ensure_transition("done", RUNNING)
    with pytest.raises(IllegalTransition):
        ensure_transition(RUNNING, "done")


def test_verdict_requires_verifying():
    ensure_verdict(VERIFYING, SUCCEEDED)
    with pytest.raises(IllegalTransition):
        ensure_verdict(RUNNING, SUCCEEDED)
    with pytest.raises(IllegalTransition):
        ensure_verdict(BLOCKED, FAILED)


def test_verdict_rejects_non_outcome():
    with pytest.raises(IllegalTransition):
        ensure_verdict(VERIFYING, RUNNING)
    with pytest.raises(IllegalTransition):
        ensure_verdict(VERIFYING, CANCELLED)


@pytest.mark.parametrize(
    "passed,failed,unknown,expected",
    [
        (3, 0, 0, SUCCEEDED),
        (1, 0, 0, SUCCEEDED),
        (3, 1, 0, FAILED),
        (0, 1, 0, FAILED),
        (3, 0, 1, PARTIALLY_VERIFIED),
        (3, 1, 2, FAILED),
        (0, 0, 1, UNKNOWN),
        (0, 0, 0, UNKNOWN),
    ],
)
def test_derive_outcome(passed, failed, unknown, expected):
    assert derive_outcome(passed=passed, failed=failed, unknown=unknown) == expected


def test_one_failure_beats_any_number_of_passes():
    assert derive_outcome(passed=99, failed=1, unknown=0) == FAILED


def test_empty_verification_never_succeeds():
    assert derive_outcome(passed=0, failed=0, unknown=0) == UNKNOWN


def test_negative_counts_are_rejected():
    with pytest.raises(ValueError):
        derive_outcome(passed=-1, failed=0, unknown=0)
