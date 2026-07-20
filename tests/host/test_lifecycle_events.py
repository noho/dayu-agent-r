"""Host lifecycle event owner helper 测试。"""

from __future__ import annotations

import pytest

from dayu.host.api import AttemptStatus, RunStatus
from dayu.host.lifecycle_events import (
    CLOSEOUT_SUPPORTED_ATTEMPT_TERMINAL_EVENT_TYPES,
    HOST_ADMISSION_COMMAND_EVENT_TYPES,
    HOST_ATTEMPT_TERMINAL_EVENT_TYPES,
    HOST_CONTEXT_GOVERNANCE_EVENT_TYPES,
    HOST_ENGINE_DIAGNOSTIC_EVENT_TYPES,
    HOST_EVENT_TYPE_CATEGORIES,
    HOST_PREVIEW_EVENT_TYPES,
    HOST_RUNNER_INPUT_EVENT_TYPES,
    HOST_RUN_TERMINAL_EVENT_TYPES,
    HOST_SESSION_LIFECYCLE_EVENT_TYPES,
    HOST_TOOL_WAIT_EVENT_TYPES,
    HostAdmissionCommandEventType,
    HostAttemptEventType,
    HostContextGovernanceEventType,
    HostEngineDiagnosticEventType,
    HostPreviewEventType,
    HostRunnerInputEventType,
    HostRunEventType,
    HostSessionEventType,
    HostToolWaitEventType,
    all_host_event_type_values,
    attempt_event_type_values,
    attempt_terminal_event_type_for_status,
    closeout_attempt_terminal_event_type_for_status,
    event_type_values,
    host_event_type_values,
    parse_host_event_type,
    run_terminal_event_type_for_status,
    serialize_host_event_type,
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


def test_all_host_event_type_values_preserves_owner_categories() -> None:
    """完整 EventLog event type owner 保留各语义分类。"""

    expected_categories = (
        HOST_SESSION_LIFECYCLE_EVENT_TYPES,
        (
            HostRunEventType.RUN_ACCEPTED,
            HostRunEventType.RUN_QUEUED,
            HostRunEventType.RUN_STARTED,
            HostRunEventType.RUN_WAITING,
            HostRunEventType.RUN_CANCELLING,
            HostRunEventType.RUN_RECOVERING,
            HostRunEventType.RUN_SUCCEEDED,
            HostRunEventType.RUN_FAILED,
            HostRunEventType.RUN_CANCELLED,
            HostRunEventType.RUN_LOST,
        ),
        (
            HostAttemptEventType.ATTEMPT_STARTED,
            HostAttemptEventType.ATTEMPT_RUNNING,
            HostAttemptEventType.ATTEMPT_SUCCEEDED,
            HostAttemptEventType.ATTEMPT_FAILED,
            HostAttemptEventType.ATTEMPT_CANCELLED,
            HostAttemptEventType.ATTEMPT_SUSPENDED,
            HostAttemptEventType.ATTEMPT_STEERED,
            HostAttemptEventType.ATTEMPT_LOST,
        ),
        HOST_ADMISSION_COMMAND_EVENT_TYPES,
        HOST_TOOL_WAIT_EVENT_TYPES,
        HOST_CONTEXT_GOVERNANCE_EVENT_TYPES,
        HOST_RUNNER_INPUT_EVENT_TYPES,
        HOST_ENGINE_DIAGNOSTIC_EVENT_TYPES,
        HOST_PREVIEW_EVENT_TYPES,
    )

    assert HOST_EVENT_TYPE_CATEGORIES == expected_categories
    assert HOST_SESSION_LIFECYCLE_EVENT_TYPES == (
        HostSessionEventType.SESSION_CREATED,
        HostSessionEventType.SESSION_CLOSED,
    )
    assert HOST_ADMISSION_COMMAND_EVENT_TYPES == (
        HostAdmissionCommandEventType.USER_INPUT_ACCEPTED,
        HostAdmissionCommandEventType.STEER_REQUESTED,
        HostAdmissionCommandEventType.RETRY_REQUESTED,
        HostAdmissionCommandEventType.REPLAY_REQUESTED,
        HostAdmissionCommandEventType.CANCEL_REQUESTED,
        HostAdmissionCommandEventType.RESUME_REQUESTED,
    )
    assert HOST_TOOL_WAIT_EVENT_TYPES == (
        HostToolWaitEventType.TOOL_CALL_REQUESTED,
        HostToolWaitEventType.TOOL_CALL_GOVERNED,
        HostToolWaitEventType.TOOL_RESULT_ACCEPTED,
        HostToolWaitEventType.TOOL_AWAITING,
        HostToolWaitEventType.TOOL_CALLS_BATCH_READY,
        HostToolWaitEventType.TOOL_CALLS_BATCH_DONE,
        HostToolWaitEventType.WAIT_LATE_RESULT_REJECTED,
    )
    assert HOST_CONTEXT_GOVERNANCE_EVENT_TYPES == (
        HostContextGovernanceEventType.CONTEXT_COMPACTION_REQUESTED,
        HostContextGovernanceEventType.CONTEXT_COMPACTED,
        HostContextGovernanceEventType.CONTEXT_COMPACTION_FAILED,
        HostContextGovernanceEventType.CONTEXT_COMPACTION_ATTEMPT_REJECTED,
    )
    assert HOST_RUNNER_INPUT_EVENT_TYPES == (
        HostRunnerInputEventType.RUNNER_CALL_INPUT_ASSEMBLED,
        HostRunnerInputEventType.RUNNER_CALL_INPUT_ITERATION_LINKED,
        HostRunnerInputEventType.USAGE_REPORTED,
    )
    assert HOST_ENGINE_DIAGNOSTIC_EVENT_TYPES == (
        HostEngineDiagnosticEventType.ENGINE_EVENT_REJECTED,
        HostEngineDiagnosticEventType.ENGINE_EVENT_DIAGNOSTIC,
        HostEngineDiagnosticEventType.HOST_LIFECYCLE_DIAGNOSTIC,
        HostEngineDiagnosticEventType.PROVIDER_DIAGNOSTIC,
        HostEngineDiagnosticEventType.PROVIDER_PROTOCOL_ERROR,
    )
    assert HOST_PREVIEW_EVENT_TYPES == (
        HostPreviewEventType.ITERATION_STARTED,
        HostPreviewEventType.CONTENT_COMPLETED,
        HostPreviewEventType.ITERATION_COMPLETED,
        HostPreviewEventType.REASONING_DELTA,
    )
    assert all_host_event_type_values() == tuple(
        event_type.value
        for category in expected_categories
        for event_type in category
    )
    assert len(all_host_event_type_values()) == len(set(all_host_event_type_values()))


def test_parse_and_serialize_host_event_type_round_trip_full_legal_set() -> None:
    """EventLog event type parser / serializer 覆盖完整 owner 合法集合。"""

    for event_type_text in all_host_event_type_values():
        parsed = parse_host_event_type(event_type_text)
        assert parsed is not None
        assert serialize_host_event_type(parsed) == event_type_text

    assert parse_host_event_type("INVALID_TEST_EVENT_TYPE") is None
    assert host_event_type_values(HOST_PREVIEW_EVENT_TYPES) == (
        "ITERATION_STARTED",
        "CONTENT_COMPLETED",
        "ITERATION_COMPLETED",
        "REASONING_DELTA",
    )


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
