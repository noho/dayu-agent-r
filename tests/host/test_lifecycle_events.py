"""Host lifecycle event owner helper 测试。"""

from __future__ import annotations

import pytest

from dayu.host.api import AttemptStatus, RunStatus
from dayu.host.lifecycle_events import (
    CLOSEOUT_SUPPORTED_ATTEMPT_TERMINAL_EVENT_TYPES,
    HOST_ATTEMPT_TERMINAL_EVENT_TYPES,
    HOST_RUN_TERMINAL_EVENT_TYPES,
    HostAttemptEventType,
    HostRunEventType,
    attempt_event_type_values,
    attempt_terminal_event_type_for_status,
    closeout_attempt_terminal_event_type_for_status,
    event_type_values,
    run_terminal_event_type_for_status,
)


def test_run_terminal_event_type_for_status_covers_terminal_owner_set() -> None:
    """Run terminal status 到 Host Run terminal event type 的映射覆盖 owner 集合。"""

    expected = {
        RunStatus.SUCCEEDED: HostRunEventType.RUN_SUCCEEDED,
        RunStatus.FAILED: HostRunEventType.RUN_FAILED,
        RunStatus.CANCELLED: HostRunEventType.RUN_CANCELLED,
        RunStatus.LOST: HostRunEventType.RUN_LOST,
    }

    assert tuple(expected.values()) == HOST_RUN_TERMINAL_EVENT_TYPES
    assert event_type_values(HOST_RUN_TERMINAL_EVENT_TYPES) == (
        "RUN_SUCCEEDED",
        "RUN_FAILED",
        "RUN_CANCELLED",
        "RUN_LOST",
    )
    for status, event_type in expected.items():
        assert run_terminal_event_type_for_status(status) is event_type


@pytest.mark.parametrize(
    "status",
    (
        RunStatus.ACCEPTED,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
        RunStatus.WAITING,
        RunStatus.CANCELLING,
        RunStatus.RECOVERING,
    ),
)
def test_run_terminal_event_type_for_status_rejects_non_terminal_status(
    status: RunStatus,
) -> None:
    """Run terminal event helper 对非终态 Run status fail-fast。"""

    with pytest.raises(ValueError, match="unsupported Run terminal status"):
        run_terminal_event_type_for_status(status)


def test_attempt_terminal_event_type_for_status_covers_terminal_owner_set() -> None:
    """Attempt durable terminal status 到 Host terminal event type 的映射覆盖 owner 集合。"""

    expected = {
        AttemptStatus.SUCCEEDED: HostAttemptEventType.ATTEMPT_SUCCEEDED,
        AttemptStatus.FAILED: HostAttemptEventType.ATTEMPT_FAILED,
        AttemptStatus.CANCELLED: HostAttemptEventType.ATTEMPT_CANCELLED,
        AttemptStatus.SUSPENDED: HostAttemptEventType.ATTEMPT_SUSPENDED,
        AttemptStatus.STEERED: HostAttemptEventType.ATTEMPT_STEERED,
        AttemptStatus.LOST: HostAttemptEventType.ATTEMPT_LOST,
    }

    assert tuple(expected.values()) == HOST_ATTEMPT_TERMINAL_EVENT_TYPES
    assert attempt_event_type_values(HOST_ATTEMPT_TERMINAL_EVENT_TYPES) == (
        "ATTEMPT_SUCCEEDED",
        "ATTEMPT_FAILED",
        "ATTEMPT_CANCELLED",
        "ATTEMPT_SUSPENDED",
        "ATTEMPT_STEERED",
        "ATTEMPT_LOST",
    )
    for status, event_type in expected.items():
        assert attempt_terminal_event_type_for_status(status) is event_type


def test_closeout_attempt_terminal_event_type_for_status_covers_supported_subset() -> None:
    """Attempt closeout-supported terminal helper 只覆盖联合 closeout 支持的子集。"""

    expected = {
        AttemptStatus.SUCCEEDED: HostAttemptEventType.ATTEMPT_SUCCEEDED,
        AttemptStatus.FAILED: HostAttemptEventType.ATTEMPT_FAILED,
        AttemptStatus.CANCELLED: HostAttemptEventType.ATTEMPT_CANCELLED,
        AttemptStatus.LOST: HostAttemptEventType.ATTEMPT_LOST,
    }

    assert tuple(expected.values()) == CLOSEOUT_SUPPORTED_ATTEMPT_TERMINAL_EVENT_TYPES
    assert attempt_event_type_values(CLOSEOUT_SUPPORTED_ATTEMPT_TERMINAL_EVENT_TYPES) == (
        "ATTEMPT_SUCCEEDED",
        "ATTEMPT_FAILED",
        "ATTEMPT_CANCELLED",
        "ATTEMPT_LOST",
    )
    for status, event_type in expected.items():
        assert closeout_attempt_terminal_event_type_for_status(status) is event_type


@pytest.mark.parametrize(
    ("status", "event_type"),
    (
        (AttemptStatus.SUSPENDED, HostAttemptEventType.ATTEMPT_SUSPENDED),
        (AttemptStatus.STEERED, HostAttemptEventType.ATTEMPT_STEERED),
    ),
)
def test_closeout_attempt_terminal_event_type_for_status_rejects_durable_only_terminal(
    status: AttemptStatus,
    event_type: HostAttemptEventType,
) -> None:
    """SUSPENDED / STEERED 是 durable terminal，但不是 closeout-supported terminal。"""

    assert attempt_terminal_event_type_for_status(status) is event_type
    assert event_type not in CLOSEOUT_SUPPORTED_ATTEMPT_TERMINAL_EVENT_TYPES
    with pytest.raises(
        ValueError,
        match="unsupported closeout Attempt terminal status",
    ):
        closeout_attempt_terminal_event_type_for_status(status)


@pytest.mark.parametrize(
    "status",
    (
        AttemptStatus.STARTING,
        AttemptStatus.RUNNING,
    ),
)
def test_attempt_terminal_event_type_for_status_rejects_non_terminal_status(
    status: AttemptStatus,
) -> None:
    """Attempt terminal event helper 对非终态 Attempt status fail-fast。"""

    with pytest.raises(ValueError, match="unsupported Attempt terminal status"):
        attempt_terminal_event_type_for_status(status)
    with pytest.raises(
        ValueError,
        match="unsupported closeout Attempt terminal status",
    ):
        closeout_attempt_terminal_event_type_for_status(status)
