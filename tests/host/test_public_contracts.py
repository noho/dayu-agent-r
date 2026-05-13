"""Host 公共 API 类型与校验规则测试。"""

from __future__ import annotations

from dataclasses import is_dataclass
from enum import StrEnum
from typing import Protocol, cast

import pytest

from dayu.host import (
    AttemptStatus,
    AuthorizationClaim,
    CancelMode,
    CancelRunRequest,
    CancelSessionRunsRequest,
    CloseSessionRequest,
    CreateSessionRequest,
    EnsureSessionRequest,
    FollowupBehavior,
    FollowupSnapshot,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostEventStream,
    HostEventView,
    HostInput,
    HostMetadataEntry,
    HostStreamCursor,
    OperationContext,
    OutboxSummary,
    PurgeSessionRequest,
    PurgeSessionResult,
    ReplayRunRequest,
    ResolveWaitRequest,
    RetryRunRequest,
    RunSnapshot,
    RunStatus,
    SessionSlotRef,
    SessionSnapshot,
    SessionStatus,
    SourceRunRelation,
    StartRunRequest,
    SubmitFollowupRequest,
    TerminalResultSummary,
    WaitResolutionSource,
)


class _DataclassParams(Protocol):
    """测试中读取 dataclass 参数所需的最小协议。"""

    frozen: bool


class _FrozenSlotsDataclassClass(Protocol):
    """测试中读取 public dataclass 类属性所需的最小协议。"""

    __dataclass_params__: _DataclassParams
    __slots__: tuple[str, ...]


PUBLIC_HOST_DATACLASS_TYPES: tuple[_FrozenSlotsDataclassClass, ...] = (
    cast(_FrozenSlotsDataclassClass, OperationContext),
    cast(_FrozenSlotsDataclassClass, AuthorizationClaim),
    cast(_FrozenSlotsDataclassClass, HostCallContext),
    cast(_FrozenSlotsDataclassClass, HostMetadataEntry),
    cast(_FrozenSlotsDataclassClass, HostInput),
    cast(_FrozenSlotsDataclassClass, SessionSlotRef),
    cast(_FrozenSlotsDataclassClass, HostStreamCursor),
    cast(_FrozenSlotsDataclassClass, EnsureSessionRequest),
    cast(_FrozenSlotsDataclassClass, CreateSessionRequest),
    cast(_FrozenSlotsDataclassClass, CloseSessionRequest),
    cast(_FrozenSlotsDataclassClass, PurgeSessionRequest),
    cast(_FrozenSlotsDataclassClass, StartRunRequest),
    cast(_FrozenSlotsDataclassClass, CancelRunRequest),
    cast(_FrozenSlotsDataclassClass, CancelSessionRunsRequest),
    cast(_FrozenSlotsDataclassClass, SubmitFollowupRequest),
    cast(_FrozenSlotsDataclassClass, RetryRunRequest),
    cast(_FrozenSlotsDataclassClass, ReplayRunRequest),
    cast(_FrozenSlotsDataclassClass, ResolveWaitRequest),
    cast(_FrozenSlotsDataclassClass, TerminalResultSummary),
    cast(_FrozenSlotsDataclassClass, OutboxSummary),
    cast(_FrozenSlotsDataclassClass, SessionSnapshot),
    cast(_FrozenSlotsDataclassClass, RunSnapshot),
    cast(_FrozenSlotsDataclassClass, FollowupSnapshot),
    cast(_FrozenSlotsDataclassClass, PurgeSessionResult),
    cast(_FrozenSlotsDataclassClass, HostEventView),
    cast(_FrozenSlotsDataclassClass, HostEventStream),
)


def _operation_context() -> OperationContext:
    """构造测试用操作上下文。

    :returns: 可复用的 ``OperationContext``。
    :raises ValueError: 构造参数不满足公共契约时抛出。
    """

    return OperationContext(
        operation_name="analyze_earnings",
        operation_kind="interactive",
        business_domain="fins",
        business_object_type="filing",
        business_object_id="filing-1",
        scenario="qa",
        correlation_id="corr-1",
    )


def _call_context() -> HostCallContext:
    """构造测试用 Host 调用上下文。

    :returns: 可复用的 ``HostCallContext``。
    :raises ValueError: 构造参数不满足公共契约时抛出。
    """

    return HostCallContext(
        actor="user-1",
        source="cli",
        request_id="request-1",
        authorization_claims=(
            AuthorizationClaim(name="role", value="analyst"),
        ),
        operation_context=_operation_context(),
    )


def _host_input() -> HostInput:
    """构造测试用 Host 输入 envelope。

    :returns: 可复用的 ``HostInput``。
    :raises ValueError: 构造参数不满足公共契约时抛出。
    """

    return HostInput(
        display_text="请分析财报",
        payload_ref=None,
        payload_digest=None,
    )


def test_status_and_error_enum_values_are_stable() -> None:
    """status / error 枚举值必须保持稳定的 snake_case 字符串。"""

    assert issubclass(SessionStatus, StrEnum)
    assert issubclass(RunStatus, StrEnum)
    assert issubclass(AttemptStatus, StrEnum)
    assert issubclass(FollowupBehavior, StrEnum)
    assert issubclass(CancelMode, StrEnum)
    assert issubclass(WaitResolutionSource, StrEnum)
    assert issubclass(SourceRunRelation, StrEnum)
    assert issubclass(HostApiErrorCode, StrEnum)

    assert {item.name: item.value for item in SessionStatus} == {
        "OPEN": "open",
        "CLOSED": "closed",
    }
    assert {item.name: item.value for item in RunStatus} == {
        "QUEUED": "queued",
        "RUNNING": "running",
        "WAITING": "waiting",
        "CANCELLING": "cancelling",
        "RECOVERING": "recovering",
        "SUCCEEDED": "succeeded",
        "FAILED": "failed",
        "CANCELLED": "cancelled",
        "LOST": "lost",
    }
    assert {item.name: item.value for item in AttemptStatus} == {
        "STARTING": "starting",
        "RUNNING": "running",
        "SUCCEEDED": "succeeded",
        "FAILED": "failed",
        "CANCELLED": "cancelled",
        "SUSPENDED": "suspended",
        "STEERED": "steered",
        "LOST": "lost",
    }
    assert {item.name: item.value for item in FollowupBehavior} == {
        "QUEUE": "queue",
        "STEER": "steer",
    }
    assert {item.name: item.value for item in CancelMode} == {
        "GRACEFUL": "graceful",
    }
    assert {item.name: item.value for item in WaitResolutionSource} == {
        "POLL": "poll",
        "CALLBACK": "callback",
        "MANUAL": "manual",
    }
    assert {item.name: item.value for item in SourceRunRelation} == {
        "RETRY": "retry",
        "REPLAY": "replay",
    }
    assert {item.name: item.value for item in HostApiErrorCode} == {
        "NOT_FOUND": "not_found",
        "INVALID_STATE": "invalid_state",
        "CONFLICT": "conflict",
        "IDEMPOTENCY_CONFLICT": "idempotency_conflict",
        "PERMISSION_DENIED": "permission_denied",
        "INTERNAL_ERROR": "internal_error",
    }


def test_dataclasses_are_frozen_and_slots() -> None:
    """所有 Host public dataclass 必须 frozen 且 slots 化。"""

    for dataclass_type in PUBLIC_HOST_DATACLASS_TYPES:
        assert is_dataclass(dataclass_type)
        assert dataclass_type.__dataclass_params__.frozen is True
        assert dataclass_type.__slots__ != ()


def test_host_api_error_carries_structured_fields() -> None:
    """HostApiError 携带结构化错误码、消息与可重试标记。"""

    error = HostApiError(
        code=HostApiErrorCode.CONFLICT,
        message="active run changed",
        retryable=True,
    )

    assert error.code == HostApiErrorCode.CONFLICT
    assert error.message == "active run changed"
    assert error.retryable is True
    assert str(error) == "active run changed"


def test_empty_id_validation_failure_path() -> None:
    """request 中的 id 字段必须拒绝空字符串或纯空白。"""

    with pytest.raises(ValueError, match="session_id"):
        SubmitFollowupRequest(
            context=_call_context(),
            session_id=" ",
            client_request_id="client-1",
            input=_host_input(),
            behavior=FollowupBehavior.QUEUE,
            target_run_id=None,
        )


def test_invalid_cursor_validation_failure_path() -> None:
    """HostStreamCursor.event_sequence 必须非负。"""

    with pytest.raises(ValueError, match="event_sequence"):
        HostStreamCursor(event_sequence=-1)


def test_steer_requires_target_run_id() -> None:
    """steer follow-up 必须携带 target_run_id。"""

    with pytest.raises(ValueError, match="target_run_id"):
        SubmitFollowupRequest(
            context=_call_context(),
            session_id="session-1",
            client_request_id="client-1",
            input=_host_input(),
            behavior=FollowupBehavior.STEER,
            target_run_id=None,
        )


def test_queue_rejects_target_run_id() -> None:
    """queue follow-up 不得携带 target_run_id。"""

    with pytest.raises(ValueError, match="target_run_id"):
        SubmitFollowupRequest(
            context=_call_context(),
            session_id="session-1",
            client_request_id="client-1",
            input=_host_input(),
            behavior=FollowupBehavior.QUEUE,
            target_run_id="run-1",
        )


def test_bind_slot_requires_scope_and_slot_key() -> None:
    """CreateSessionRequest.bind_slot=True 时必须同时提供 scope 和 slot_key。"""

    with pytest.raises(ValueError, match="scope"):
        CreateSessionRequest(
            context=_call_context(),
            client_request_id="client-1",
            bind_slot=True,
            scope=None,
            slot_key="slot-1",
            metadata=(),
        )
    with pytest.raises(ValueError, match="slot_key"):
        CreateSessionRequest(
            context=_call_context(),
            client_request_id="client-1",
            bind_slot=True,
            scope="cli",
            slot_key=None,
            metadata=(),
        )


def test_metadata_key_validation_failure_path() -> None:
    """metadata key 作为 name-like 字段必须拒绝空白值。"""

    with pytest.raises(ValueError, match="HostMetadataEntry.key"):
        CreateSessionRequest(
            context=_call_context(),
            client_request_id="client-1",
            bind_slot=False,
            scope=None,
            slot_key=None,
            metadata=(HostMetadataEntry(key=" ", value="diagnostic"),),
        )


def test_cancel_run_rejects_non_graceful_runtime_mode() -> None:
    """CancelRunRequest 必须拒绝非 graceful 的运行时 mode 值。"""

    with pytest.raises(ValueError, match="mode"):
        CancelRunRequest(
            context=_call_context(),
            client_request_id="client-1",
            reason="user_cancelled",
            mode=cast(CancelMode, "force"),
        )


def test_cancel_session_runs_rejects_non_graceful_runtime_mode() -> None:
    """CancelSessionRunsRequest 必须拒绝非 graceful 的运行时 mode 值。"""

    with pytest.raises(ValueError, match="mode"):
        CancelSessionRunsRequest(
            context=_call_context(),
            client_request_id="client-1",
            reason="shutdown",
            mode=cast(CancelMode, "force"),
        )
