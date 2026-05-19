"""Host 公共 API 类型与校验规则测试。"""

from __future__ import annotations

import pathlib
from dataclasses import MISSING, fields, is_dataclass, replace
from datetime import UTC, datetime, timedelta, timezone
from enum import StrEnum
from typing import Protocol, cast

import pytest

from dayu.contracts.tool_outcome import (
    TOOL_CANCELLED_REASON_TIMEOUT,
    ToolCancelledOutcome,
)
from dayu.contracts.tool_result import ToolResultFailure, ToolResultSuccess
from dayu.contracts.cancellation import CancellationToken
from dayu.host import (
    AttemptDispatchSnapshot,
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
    HOST_EVENT_STREAM_DEFAULT_LIMIT,
    HOST_EVENT_STREAM_MAX_LIMIT,
    HOST_WAIT_IDEMPOTENCY_KEY_MAX_LENGTH,
    HOST_WAIT_PROVIDER_STATUS_REF_MAX_LENGTH,
    HostApiError,
    HostApiErrorCode,
    HostApiErrorDetail,
    HostCallContext,
    HostPayloadRef,
    LocalEngineWorkerFactory,
    HostMetadataEntry,
    HostStreamCursor,
    OperationContext,
    OutboxSummary,
    PurgeSessionRequest,
    PurgeSessionResult,
    ReplayRunRequest,
    ResolveWaitCancelledOutcome,
    ResolveWaitCompletedOutcome,
    ResolveWaitFailedOutcome,
    ResolveWaitLostOutcome,
    ResolveWaitRequest,
    RetryRunRequest,
    RunSnapshot,
    RunStatus,
    SessionSlotRef,
    SessionSnapshot,
    SessionStatus,
    SourceRunRelation,
    SteerConflictDetail,
    SubmitFollowupRequest,
    TerminalResultSummary,
    WaitAdapterKey,
    WaitProviderStatusRef,
    WaitResolutionSource,
)
from dayu.host.api import (
    HostCommandHandleOptions,
    HostEventStream,
    HostEventView,
    HostInput,
    HostLocalExecutionOptions,
    StartRunRequest,
)
from dayu.host.command import compose_host_local_execution_options
from dayu.host.tool_runtime import ToolFactKind
from dayu.host.context_policy import ContextBudgetPolicy, default_context_budget_policy
from dayu.host.memory import MemoryProjectionPolicy
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec


class _DataclassParams(Protocol):
    """测试中读取 dataclass 参数所需的最小协议。"""

    frozen: bool


class _FrozenSlotsDataclassClass(Protocol):
    """测试中读取 public dataclass 类属性所需的最小协议。"""

    __dataclass_params__: _DataclassParams
    __slots__: tuple[str, ...]


class _WorkerFactoryToken:
    """测试用 worker factory token。

    HostLocalExecutionOptions 当前只在构造期拒绝 ``None``；结构协议由
    pyright 与真实装配点保障。
    """


PUBLIC_HOST_DATACLASS_TYPES: tuple[_FrozenSlotsDataclassClass, ...] = (
    cast(_FrozenSlotsDataclassClass, OperationContext),
    cast(_FrozenSlotsDataclassClass, AuthorizationClaim),
    cast(_FrozenSlotsDataclassClass, HostCallContext),
    cast(_FrozenSlotsDataclassClass, HostMetadataEntry),
    cast(_FrozenSlotsDataclassClass, HostPayloadRef),
    cast(_FrozenSlotsDataclassClass, WaitAdapterKey),
    cast(_FrozenSlotsDataclassClass, WaitProviderStatusRef),
    cast(_FrozenSlotsDataclassClass, ResolveWaitCompletedOutcome),
    cast(_FrozenSlotsDataclassClass, ResolveWaitFailedOutcome),
    cast(_FrozenSlotsDataclassClass, ResolveWaitCancelledOutcome),
    cast(_FrozenSlotsDataclassClass, ResolveWaitLostOutcome),
    cast(_FrozenSlotsDataclassClass, HostInput),
    cast(_FrozenSlotsDataclassClass, SessionSlotRef),
    cast(_FrozenSlotsDataclassClass, HostStreamCursor),
    cast(_FrozenSlotsDataclassClass, SteerConflictDetail),
    cast(_FrozenSlotsDataclassClass, HostCommandHandleOptions),
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


def _success_result() -> ToolResultSuccess:
    """构造测试用工具成功结果。

    :returns: ``ToolResultSuccess``。
    """

    return ToolResultSuccess(ok=True, value={"accepted": True}, meta=None)


def _failure_result() -> ToolResultFailure:
    """构造测试用工具失败结果。

    :returns: ``ToolResultFailure``。
    """

    return ToolResultFailure(
        ok=False,
        error="provider_failed",
        message="provider failed",
        hint=None,
        meta=None,
    )


def _cancelled_result() -> ToolCancelledOutcome:
    """构造测试用工具级取消结果。

    :returns: ``ToolCancelledOutcome``。
    """

    return ToolCancelledOutcome(
        reason=TOOL_CANCELLED_REASON_TIMEOUT,
        message="tool timed out",
        hint=None,
        meta=None,
    )


def _resolve_wait_request() -> ResolveWaitRequest:
    """构造测试用 resolve wait 请求。

    :returns: ``ResolveWaitRequest``。
    """

    return ResolveWaitRequest(
        context=_call_context(),
        idempotency_key="resolve-1",
        outcome=ResolveWaitCompletedOutcome(
            result=_success_result(),
            payload_ref=None,
        ),
        source=WaitResolutionSource.MANUAL,
        observed_at=datetime(2026, 5, 16, tzinfo=UTC),
    )


def _host_command_handle_options() -> HostCommandHandleOptions:
    """构造测试用 Host command handle 选项。

    :returns: 可复用的 ``HostCommandHandleOptions``。
    :raises ValueError: 构造参数不满足公共契约时抛出。
    :raises TypeError: 路径字段不满足公共契约时抛出。
    """

    return HostCommandHandleOptions(
        host_handle_id="host-1",
        db_path=pathlib.Path("workspace/host.sqlite3"),
        artifact_root=pathlib.Path("workspace/artifacts"),
        create_parent_dirs=True,
        sqlite_busy_timeout_seconds=5.0,
        sqlite_write_busy_retry_count=3,
        sqlite_write_retry_initial_delay_seconds=0.01,
        sqlite_write_retry_backoff_multiplier=2.0,
        sqlite_write_retry_max_delay_seconds=1.0,
        payload_inline_threshold_bytes=4096,
        context_window_size=8192,
        reserved_output_tokens=1024,
    )


def _runner_spec() -> RunnerSpec:
    """构造测试用 RunnerSpec。

    :returns: RunnerSpec。
    """

    return RunnerSpec(
        provider="test",
        model="test-model",
        endpoint="https://example.invalid",
        api_key_ref="secret:test",
        headers={},
        supports_tool_calling=False,
        supports_streaming=False,
        supports_stream_usage=False,
        default_timeout_seconds=1.0,
        max_retries=0,
        provider_request=None,
    )


def _runner_options() -> RunnerCallOptions:
    """构造测试用 RunnerCallOptions。

    :returns: RunnerCallOptions。
    """

    return RunnerCallOptions(
        temperature=None,
        max_tokens=None,
        top_p=None,
        stream=False,
    )


def _agent_policy() -> AgentPolicy:
    """构造测试用 AgentPolicy。

    :returns: AgentPolicy。
    """

    return AgentPolicy(
        max_iterations=1,
        continuation_max_attempts=0,
        allow_tool_calls=False,
        tool_execution_timeout_seconds=1.0,
    )


def _local_execution_options() -> HostLocalExecutionOptions:
    """构造测试用 HostLocalExecutionOptions。

    :returns: HostLocalExecutionOptions。
    """

    return HostLocalExecutionOptions(
        lane_db_path=pathlib.Path("workspace/lane.sqlite3"),
        lane_name="llm",
        lane_capacity=1,
        lane_default_timeout_seconds=0.1,
        lane_claim_ttl_seconds=1.0,
        lane_heartbeat_interval_seconds=0.1,
        worker_startup_timeout_seconds=1.0,
        dispatch_poll_interval_seconds=0.01,
        runner_spec=_runner_spec(),
        runner_options=_runner_options(),
        agent_policy=_agent_policy(),
        worker_factory=cast(LocalEngineWorkerFactory, _WorkerFactoryToken()),
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
        "ACCEPTED": "accepted",
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
        "UNSUPPORTED_OPERATION": "unsupported_operation",
        "INTERNAL_ERROR": "internal_error",
    }


def test_dataclasses_are_frozen_and_slots() -> None:
    """所有 Host public dataclass 必须 frozen 且 slots 化。"""

    for dataclass_type in PUBLIC_HOST_DATACLASS_TYPES:
        assert is_dataclass(dataclass_type)
        assert dataclass_type.__dataclass_params__.frozen is True
        assert dataclass_type.__slots__ != ()


def test_host_api_error_carries_structured_fields() -> None:
    """HostApiError 携带结构化错误码、消息、可重试标记与 typed detail。"""

    error = HostApiError(
        code=HostApiErrorCode.CONFLICT,
        message="active run changed",
        retryable=True,
    )

    assert error.code == HostApiErrorCode.CONFLICT
    assert error.message == "active run changed"
    assert error.retryable is True
    assert error.detail is None
    assert str(error) == "active run changed"

    detail: HostApiErrorDetail = SteerConflictDetail(
        target_run_id="run-1",
        target_run_status=RunStatus.RUNNING,
        current_active_run_id="run-2",
        current_active_run_status=RunStatus.RUNNING,
    )
    detail_error = HostApiError(
        code=HostApiErrorCode.CONFLICT,
        message="steer target is not active",
        retryable=False,
        detail=detail,
    )

    assert detail_error.detail == detail
    assert vars(detail_error) == {
        "code": HostApiErrorCode.CONFLICT,
        "message": "steer target is not active",
        "retryable": False,
        "detail": detail,
    }


def test_event_stream_limit_constants_are_stable() -> None:
    """Host event stream limit 常量必须公开且默认值不超过最大值。"""

    assert HOST_EVENT_STREAM_DEFAULT_LIMIT == 100
    assert HOST_EVENT_STREAM_MAX_LIMIT == 1000
    assert HOST_EVENT_STREAM_DEFAULT_LIMIT <= HOST_EVENT_STREAM_MAX_LIMIT


def test_resolve_wait_request_uses_typed_outcome_envelope() -> None:
    """ResolveWaitRequest 必须使用 typed outcome envelope 而不是 outcome_ref。"""

    request = _resolve_wait_request()

    field_names = {field.name for field in fields(ResolveWaitRequest)}
    assert "outcome" in field_names
    assert "outcome_ref" not in field_names
    assert request.context == _call_context()
    assert isinstance(request.outcome, ResolveWaitCompletedOutcome)
    assert request.outcome.result == _success_result()
    assert request.observed_at.tzinfo is UTC


def test_resolve_wait_request_rejects_invalid_idempotency_and_time() -> None:
    """ResolveWaitRequest 拒绝空幂等键、超长幂等键和非 UTC 观测时间。"""

    with pytest.raises(ValueError, match="idempotency_key"):
        replace(_resolve_wait_request(), idempotency_key=" ")
    with pytest.raises(ValueError, match="idempotency_key"):
        replace(
            _resolve_wait_request(),
            idempotency_key="x" * (HOST_WAIT_IDEMPOTENCY_KEY_MAX_LENGTH + 1),
        )
    with pytest.raises(ValueError, match="observed_at"):
        replace(
            _resolve_wait_request(),
            observed_at=datetime(2026, 5, 16),
        )
    with pytest.raises(ValueError, match="observed_at"):
        replace(
            _resolve_wait_request(),
            observed_at=datetime(
                2026,
                5,
                16,
                tzinfo=timezone(timedelta(hours=8)),
            ),
        )


def test_resolve_wait_outcome_envelope_shapes_are_closed() -> None:
    """等待结果 envelope 必须把 payload ref 与 provider status ref 分流。"""

    payload_ref = HostPayloadRef(
        payload_ref="payload-1",
        payload_digest="sha256:" + "0" * 64,
    )
    adapter_key = WaitAdapterKey("poll.primary")
    provider_ref = WaitProviderStatusRef(
        adapter_key=adapter_key,
        status_ref="provider-status-1",
        status_digest="sha256:" + "1" * 64,
    )

    completed = ResolveWaitCompletedOutcome(
        result=_success_result(),
        payload_ref=payload_ref,
    )
    failed = ResolveWaitFailedOutcome(
        result=_failure_result(),
        payload_ref=payload_ref,
    )
    cancelled = ResolveWaitCancelledOutcome(
        result=_cancelled_result(),
        payload_ref=payload_ref,
    )
    lost = ResolveWaitLostOutcome(
        reason_code="provider_status_lost",
        message="provider status is not readable",
        provider_status_ref=provider_ref,
    )

    assert completed.payload_ref == payload_ref
    assert failed.payload_ref == payload_ref
    assert cancelled.payload_ref == payload_ref
    assert lost.provider_status_ref == provider_ref
    assert "provider_status_ref" not in {
        field.name for field in fields(ResolveWaitCompletedOutcome)
    }
    assert "payload_ref" not in {field.name for field in fields(ResolveWaitLostOutcome)}


def test_tool_fact_kind_includes_lost_for_wait_resolution() -> None:
    """ToolRuntime 工具事实类别预留 lost 等待结果终态。"""

    assert ToolFactKind.LOST.value == "lost"


def test_wait_ref_validation_rejects_invalid_lengths_and_digest() -> None:
    """等待相关 public refs 拒绝非法字符、超长文本与非法 digest。"""

    with pytest.raises(ValueError, match="invalid characters"):
        WaitAdapterKey("bad key")
    with pytest.raises(ValueError, match="status_ref"):
        WaitProviderStatusRef(
            adapter_key=WaitAdapterKey("manual"),
            status_ref="x" * (HOST_WAIT_PROVIDER_STATUS_REF_MAX_LENGTH + 1),
            status_digest=None,
        )
    with pytest.raises(ValueError, match="status_digest"):
        WaitProviderStatusRef(
            adapter_key=WaitAdapterKey("manual"),
            status_ref="provider-status",
            status_digest="not-a-digest",
        )
    with pytest.raises(ValueError, match="payload_digest"):
        HostPayloadRef(payload_ref="payload-1", payload_digest="not-a-digest")


def test_host_command_handle_options_accept_valid_shape() -> None:
    """HostCommandHandleOptions 接受显式 typed 构造选项。"""

    options = _host_command_handle_options()

    assert options.host_handle_id == "host-1"
    assert options.db_path == pathlib.Path("workspace/host.sqlite3")
    assert options.artifact_root == pathlib.Path("workspace/artifacts")
    assert options.create_parent_dirs is True
    assert options.context_window_size > options.reserved_output_tokens
    assert options.context_budget_hard_threshold_tokens is None
    assert options.context_budget_minimum_protection_tokens is None


def test_host_command_handle_options_require_explicit_budget_inputs() -> None:
    """HostCommandHandleOptions 不为 window / reserved budget 提供默认值。"""

    field_map = {
        field.name: field for field in fields(HostCommandHandleOptions)
    }

    assert field_map["context_window_size"].default is MISSING
    assert field_map["reserved_output_tokens"].default is MISSING


def test_host_command_handle_options_accept_explicit_context_budget() -> None:
    """HostCommandHandleOptions 接受显式 context budget typed 输入。"""

    options = replace(
        _host_command_handle_options(),
        context_window_size=4096,
        reserved_output_tokens=512,
        context_budget_hard_threshold_tokens=3000,
        context_budget_minimum_protection_tokens=128,
    )

    assert options.context_window_size == 4096
    assert options.reserved_output_tokens == 512
    assert options.context_budget_hard_threshold_tokens == 3000
    assert options.context_budget_minimum_protection_tokens == 128


def test_compose_host_local_execution_options_wires_context_policy() -> None:
    """command composition 从 public options 构造 Host context policy。"""

    local_execution = _local_execution_options()
    options = replace(
        _host_command_handle_options(),
        local_execution=local_execution,
        artifact_root=pathlib.Path("workspace/compact-artifacts"),
        context_window_size=4096,
        reserved_output_tokens=512,
        context_budget_hard_threshold_tokens=3000,
        context_budget_minimum_protection_tokens=128,
    )

    composed = compose_host_local_execution_options(options)

    assert composed is not None
    assert composed.context_budget_policy is not None
    assert composed.context_budget_policy.context_window_size == 4096
    assert composed.context_budget_policy.reserved_output_tokens == 512
    assert composed.context_budget_policy.hard_threshold_tokens == 3000
    assert composed.context_budget_policy.minimum_protection_tokens == 128
    assert composed.memory_projection_policy is local_execution.memory_projection_policy
    assert composed.compact_artifact_root == pathlib.Path(
        "workspace/compact-artifacts"
    )


def test_compose_host_local_execution_options_without_local_execution_is_none() -> None:
    """command composition 未配置 local execution 时不构造 scheduler 配置。"""

    assert compose_host_local_execution_options(_host_command_handle_options()) is None


def test_host_command_handle_options_rejects_empty_handle_id() -> None:
    """HostCommandHandleOptions 可选 handle id 存在时必须非空。"""

    with pytest.raises(ValueError, match="host_handle_id"):
        replace(_host_command_handle_options(), host_handle_id=" ")


def test_host_command_handle_options_rejects_invalid_paths() -> None:
    """HostCommandHandleOptions 路径字段必须是 pathlib.Path。"""

    with pytest.raises(TypeError, match="db_path"):
        replace(
            _host_command_handle_options(),
            db_path=cast(pathlib.Path, "workspace/host.sqlite3"),
        )
    with pytest.raises(TypeError, match="artifact_root"):
        replace(
            _host_command_handle_options(),
            artifact_root=cast(pathlib.Path, "workspace/artifacts"),
        )


def test_host_command_handle_options_rejects_invalid_bool() -> None:
    """HostCommandHandleOptions 布尔字段必须是 bool。"""

    with pytest.raises(TypeError, match="create_parent_dirs"):
        replace(
            _host_command_handle_options(),
            create_parent_dirs=cast(bool, 1),
        )


def test_host_command_handle_options_rejects_invalid_numeric_values() -> None:
    """HostCommandHandleOptions 拒绝非正数配置和负数重试次数。"""

    with pytest.raises(ValueError, match="sqlite_busy_timeout_seconds"):
        replace(_host_command_handle_options(), sqlite_busy_timeout_seconds=0.0)
    with pytest.raises(TypeError, match="sqlite_busy_timeout_seconds"):
        replace(
            _host_command_handle_options(),
            sqlite_busy_timeout_seconds=cast(float, True),
        )
    with pytest.raises(ValueError, match="sqlite_write_busy_retry_count"):
        replace(_host_command_handle_options(), sqlite_write_busy_retry_count=-1)
    with pytest.raises(TypeError, match="sqlite_write_busy_retry_count"):
        replace(
            _host_command_handle_options(),
            sqlite_write_busy_retry_count=cast(int, True),
        )
    with pytest.raises(
        ValueError, match="sqlite_write_retry_initial_delay_seconds"
    ):
        replace(
            _host_command_handle_options(),
            sqlite_write_retry_initial_delay_seconds=0.0,
        )
    with pytest.raises(
        ValueError, match="sqlite_write_retry_backoff_multiplier"
    ):
        replace(
            _host_command_handle_options(),
            sqlite_write_retry_backoff_multiplier=0.0,
        )
    with pytest.raises(ValueError, match="sqlite_write_retry_max_delay_seconds"):
        replace(
            _host_command_handle_options(),
            sqlite_write_retry_max_delay_seconds=0.0,
        )
    with pytest.raises(ValueError, match="payload_inline_threshold_bytes"):
        replace(_host_command_handle_options(), payload_inline_threshold_bytes=0)
    with pytest.raises(TypeError, match="payload_inline_threshold_bytes"):
        replace(
            _host_command_handle_options(),
            payload_inline_threshold_bytes=cast(int, True),
        )
    with pytest.raises(ValueError, match="context_window_size"):
        replace(_host_command_handle_options(), context_window_size=0)
    with pytest.raises(TypeError, match="context_window_size"):
        replace(
            _host_command_handle_options(),
            context_window_size=cast(int, True),
        )
    with pytest.raises(ValueError, match="reserved_output_tokens"):
        replace(_host_command_handle_options(), reserved_output_tokens=0)
    with pytest.raises(TypeError, match="reserved_output_tokens"):
        replace(
            _host_command_handle_options(),
            reserved_output_tokens=cast(int, True),
        )
    with pytest.raises(ValueError, match="reserved_output_tokens"):
        replace(
            _host_command_handle_options(),
            context_window_size=1000,
            reserved_output_tokens=1000,
            context_budget_minimum_protection_tokens=1,
        )
    with pytest.raises(ValueError, match="hard_threshold_tokens"):
        replace(
            _host_command_handle_options(),
            context_window_size=1000,
            reserved_output_tokens=100,
            context_budget_hard_threshold_tokens=901,
            context_budget_minimum_protection_tokens=1,
        )
    with pytest.raises(ValueError, match="minimum_protection_tokens"):
        replace(
            _host_command_handle_options(),
            context_window_size=1000,
            reserved_output_tokens=100,
            context_budget_minimum_protection_tokens=900,
        )


def test_host_local_execution_options_accept_valid_shape() -> None:
    """HostLocalExecutionOptions 接受当前 scheduler typed 装配边界。"""

    options = _local_execution_options()

    assert options.lane_name == "llm"
    assert options.runner_spec.provider == "test"
    assert options.runner_options.stream is False
    assert options.agent_policy.allow_tool_calls is False
    assert options.context_budget_policy is None
    assert options.memory_projection_policy.max_verified_facts > 0
    assert options.memory_projection_catchup_batch_size > 0

    with_budget = replace(
        options,
        context_budget_policy=default_context_budget_policy(
            context_window_size=2048,
            reserved_output_tokens=512,
        ),
    )
    assert with_budget.context_budget_policy is not None
    assert with_budget.context_budget_policy.context_window_size == 2048


def test_host_local_execution_options_rejects_invalid_typed_fields() -> None:
    """HostLocalExecutionOptions 拒绝错误 typed field 与 None worker factory。"""

    with pytest.raises(TypeError, match="runner_spec"):
        replace(
            _local_execution_options(),
            runner_spec=cast(RunnerSpec, _runner_options()),
        )
    with pytest.raises(TypeError, match="runner_options"):
        replace(
            _local_execution_options(),
            runner_options=cast(RunnerCallOptions, _runner_spec()),
        )
    with pytest.raises(TypeError, match="agent_policy"):
        replace(
            _local_execution_options(),
            agent_policy=cast(AgentPolicy, _runner_spec()),
        )
    with pytest.raises(TypeError, match="worker_factory"):
        replace(
            _local_execution_options(),
            worker_factory=cast(LocalEngineWorkerFactory, None),
        )
    with pytest.raises(TypeError, match="context_budget_policy"):
        replace(
            _local_execution_options(),
            context_budget_policy=cast(
                ContextBudgetPolicy,
                _runner_spec(),
            ),
        )
    with pytest.raises(TypeError, match="memory_projection_policy"):
        replace(
            _local_execution_options(),
            memory_projection_policy=cast(MemoryProjectionPolicy, _runner_spec()),
        )
    with pytest.raises(ValueError, match="memory_projection_catchup_batch_size"):
        replace(_local_execution_options(), memory_projection_catchup_batch_size=0)


def test_context_budget_inputs_are_not_per_run_fields() -> None:
    """context budget 输入只存在于 composition options，不在 per-run request。"""

    start_fields = {field.name for field in fields(StartRunRequest)}
    followup_fields = {field.name for field in fields(SubmitFollowupRequest)}
    metadata_fields = {field.name for field in fields(HostMetadataEntry)}
    forbidden = {
        "context_window_size",
        "reserved_output_tokens",
        "context_budget_hard_threshold_tokens",
        "context_budget_minimum_protection_tokens",
    }

    assert forbidden.isdisjoint(start_fields)
    assert forbidden.isdisjoint(followup_fields)
    assert forbidden.isdisjoint(metadata_fields)


def test_operation_context_rejects_empty_optional_text_fields() -> None:
    """OperationContext 可选字符串存在时必须非空。"""

    with pytest.raises(ValueError, match="business_object_type"):
        replace(_operation_context(), business_object_type="")
    with pytest.raises(ValueError, match="scenario"):
        replace(_operation_context(), scenario=" ")


def test_attempt_dispatch_snapshot_rejects_none_cancellation_token() -> None:
    """Attempt dispatch snapshot 必须拒绝空取消观察 token。"""

    with pytest.raises(TypeError, match="cancellation_token"):
        AttemptDispatchSnapshot(
            session_id="session-1",
            run_id="run-1",
            attempt_id="attempt-1",
            execution_id="execution-1",
            dispatch_record_id="dispatch-1",
            execution_target="local-default",
            policy_snapshot_ref="policy-1",
            cancellation_token=cast(CancellationToken, None),
        )


def test_empty_id_validation_failure_path() -> None:
    """request 中的 id 字段必须拒绝空字符串或纯空白。"""

    with pytest.raises(ValueError, match="session_id"):
        SubmitFollowupRequest(
            context=_call_context(),
            session_id=" ",
            client_request_id="client-1",
            system_prompt=None,
            user_prompt="prompt",
            tool_names=None,
            runner_spec=None,
            runner_options=None,
            agent_policy=None,
            behavior=FollowupBehavior.QUEUE,
            target_run_id=None,
        )


def test_invalid_cursor_validation_failure_path() -> None:
    """HostStreamCursor.event_sequence 必须非负。"""

    with pytest.raises(ValueError, match="event_sequence"):
        HostStreamCursor(event_sequence=-1)


def test_run_snapshot_rejects_relation_without_source_run_id() -> None:
    """RunSnapshot.source_run_relation 不能脱离 source_run_id 单独存在。"""

    with pytest.raises(ValueError, match="source_run_relation"):
        RunSnapshot(
            run_id="run-1",
            session_id="session-1",
            status=RunStatus.QUEUED,
            current_attempt_id=None,
            terminal_result_summary=None,
            event_cursor=HostStreamCursor(event_sequence=0),
            source_run_id=None,
            source_run_relation=SourceRunRelation.RETRY,
            outbox_summary=None,
        )


def test_run_snapshot_rejects_source_run_id_without_relation() -> None:
    """RunSnapshot.source_run_id 必须同时声明 source_run_relation。"""

    with pytest.raises(ValueError, match="source_run_id"):
        RunSnapshot(
            run_id="run-1",
            session_id="session-1",
            status=RunStatus.QUEUED,
            current_attempt_id=None,
            terminal_result_summary=None,
            event_cursor=HostStreamCursor(event_sequence=0),
            source_run_id="source-run-1",
            source_run_relation=None,
            outbox_summary=None,
        )


def test_followup_snapshot_queue_accepts_queued_run_shape() -> None:
    """queue follow-up snapshot 支持已接受 Run 仍处于 queued 的形状。"""

    snapshot = FollowupSnapshot(
        accepted_input_ref="input-1",
        behavior=FollowupBehavior.QUEUE,
        accepted_run_id="run-1",
        accepted_run_status=RunStatus.QUEUED,
        command_watermark=HostStreamCursor(event_sequence=1),
        queued_run_id="run-1",
        target_run_id=None,
    )

    assert snapshot.accepted_run_id == "run-1"
    assert snapshot.accepted_run_status == RunStatus.QUEUED
    assert snapshot.queued_run_id == "run-1"


def test_followup_snapshot_queue_accepts_running_run_shape() -> None:
    """queue follow-up snapshot 支持无 active Run 时直接启动的 running 形状。"""

    snapshot = FollowupSnapshot(
        accepted_input_ref="input-1",
        behavior=FollowupBehavior.QUEUE,
        accepted_run_id="run-1",
        accepted_run_status=RunStatus.RUNNING,
        command_watermark=HostStreamCursor(event_sequence=1),
        queued_run_id=None,
        target_run_id=None,
    )

    assert snapshot.accepted_run_id == "run-1"
    assert snapshot.accepted_run_status == RunStatus.RUNNING
    assert snapshot.queued_run_id is None


def test_followup_snapshot_steer_does_not_require_queued_run_id() -> None:
    """steer follow-up snapshot 不要求携带 queued_run_id。"""

    snapshot = FollowupSnapshot(
        accepted_input_ref="input-1",
        behavior=FollowupBehavior.STEER,
        accepted_run_id="run-1",
        accepted_run_status=RunStatus.RUNNING,
        command_watermark=HostStreamCursor(event_sequence=1),
        queued_run_id=None,
        target_run_id="run-1",
    )

    assert snapshot.target_run_id == "run-1"
    assert snapshot.queued_run_id is None


def test_followup_snapshot_queue_rejects_target_run_id() -> None:
    """queue follow-up snapshot 不得携带 target_run_id。"""

    with pytest.raises(ValueError, match="target_run_id"):
        FollowupSnapshot(
            accepted_input_ref="input-1",
            behavior=FollowupBehavior.QUEUE,
            accepted_run_id="run-1",
            accepted_run_status=RunStatus.QUEUED,
            command_watermark=HostStreamCursor(event_sequence=0),
            queued_run_id="run-1",
            target_run_id="run-1",
        )


def test_followup_snapshot_queue_rejects_missing_queued_run_id() -> None:
    """queue + QUEUED follow-up snapshot 要求 queued_run_id 等于 accepted_run_id。"""

    with pytest.raises(ValueError, match="queued_run_id"):
        FollowupSnapshot(
            accepted_input_ref="input-1",
            behavior=FollowupBehavior.QUEUE,
            accepted_run_id="run-1",
            accepted_run_status=RunStatus.QUEUED,
            command_watermark=HostStreamCursor(event_sequence=0),
            queued_run_id=None,
            target_run_id=None,
        )


def test_followup_snapshot_queue_rejects_running_queued_run_id() -> None:
    """queue + RUNNING follow-up snapshot 不得把 running Run id 放入 queued_run_id。"""

    with pytest.raises(ValueError, match="queued_run_id"):
        FollowupSnapshot(
            accepted_input_ref="input-1",
            behavior=FollowupBehavior.QUEUE,
            accepted_run_id="run-1",
            accepted_run_status=RunStatus.RUNNING,
            command_watermark=HostStreamCursor(event_sequence=0),
            queued_run_id="run-1",
            target_run_id=None,
        )


def test_followup_snapshot_queue_rejects_recovering_status() -> None:
    """queue follow-up snapshot 不把 Slice 3 外 recovery 状态作为接受结果。"""

    with pytest.raises(ValueError, match="accepted_run_status"):
        FollowupSnapshot(
            accepted_input_ref="input-1",
            behavior=FollowupBehavior.QUEUE,
            accepted_run_id="run-1",
            accepted_run_status=RunStatus.RECOVERING,
            command_watermark=HostStreamCursor(event_sequence=0),
            queued_run_id=None,
            target_run_id=None,
        )


def test_steer_requires_target_run_id() -> None:
    """steer follow-up 必须携带 target_run_id。"""

    with pytest.raises(ValueError, match="target_run_id"):
        SubmitFollowupRequest(
            context=_call_context(),
            session_id="session-1",
            client_request_id="client-1",
            system_prompt=None,
            user_prompt="prompt",
            tool_names=None,
            runner_spec=None,
            runner_options=None,
            agent_policy=None,
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
            system_prompt=None,
            user_prompt="prompt",
            tool_names=None,
            runner_spec=None,
            runner_options=None,
            agent_policy=None,
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
