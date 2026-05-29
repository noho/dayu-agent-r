"""``dayu.host`` 包根导出白名单测试。"""

from __future__ import annotations

import dayu.host as host
import dayu.host.api as api
import dayu.host.read_api as read_api


EXPECTED_API_EXPORTS: frozenset[str] = frozenset(
    {
        "AttemptDispatchSnapshot",
        "AttemptStatus",
        "AuthorizationClaim",
        "CancelMode",
        "CancelRunRequest",
        "CancelSessionRunsRequest",
        "CloseSessionRequest",
        "CreateSessionRequest",
        "DrainOutboxTerminalItemsRequest",
        "EnsureSessionRequest",
        "FollowupBehavior",
        "FollowupSnapshot",
        "HOST_EVENT_STREAM_DEFAULT_LIMIT",
        "HOST_EVENT_STREAM_MAX_LIMIT",
        "HOST_OUTBOX_TERMINAL_READ_MAX_LIMIT",
        "HOST_OUTBOX_TERMINAL_SEEN_IDS_MAX_COUNT",
        "HOST_WAIT_ADAPTER_KEY_MAX_LENGTH",
        "HOST_WAIT_EXTERNAL_JOB_ID_MAX_LENGTH",
        "HOST_WAIT_IDEMPOTENCY_KEY_MAX_LENGTH",
        "HOST_WAIT_ID_MAX_LENGTH",
        "HOST_WAIT_PROVIDER_STATUS_REF_MAX_LENGTH",
        "HOST_WAIT_RESUME_TOKEN_MAX_LENGTH",
        "HOST_WAIT_SNAPSHOT_ID_MAX_LENGTH",
        "HOST_WAIT_TOOL_CALL_ID_MAX_LENGTH",
        "HOST_WAIT_TOOL_NAME_MAX_LENGTH",
        "HostApiError",
        "HostApiErrorCode",
        "HostApiErrorDetail",
        "Host",
        "HostCallContext",
        "HostClosedError",
        "HostEvent",
        "HostEventClass",
        "HostEventKind",
        "HostFinalAnswerView",
        "HostMetadataEntry",
        "HostPayloadRef",
        "HostStreamCursor",
        "HostTerminalStatus",
        "LocalEngineWorker",
        "LocalEngineWorkerFactory",
        "LocalWorkerHandle",
        "OpenHostOptions",
        "OperationContext",
        "OrdinaryRunExecutionBaseline",
        "OutboxProjectionStatus",
        "OutboxSummary",
        "OutboxTerminalCursor",
        "OutboxTerminalItem",
        "OutboxTerminalItemsBatch",
        "OutboxTerminalItemState",
        "PurgeSessionRequest",
        "PurgeSessionResult",
        "CompactorRunnerBaseline",
        "ReadOutboxTerminalItemsRequest",
        "ReplayRunRequest",
        "ResolveWaitCancelledOutcome",
        "ResolveWaitCompletedOutcome",
        "ResolveWaitFailedOutcome",
        "ResolveWaitLostOutcome",
        "ResolveWaitOutcome",
        "ResolveWaitRequest",
        "RetryRunRequest",
        "RunSnapshot",
        "RunStatus",
        "SessionSlotRef",
        "SessionSnapshot",
        "SessionStatus",
        "SourceRunRelation",
        "SteerConflictDetail",
        "SubmitFollowupRequest",
        "TerminalResultSummary",
        "WaitAdapterKey",
        "WaitProviderStatusRef",
        "WaitResolutionSource",
    }
)

EXPECTED_TOOLING_EXPORTS: frozenset[str] = frozenset(
    {
        "FrameworkToolName",
        "FrameworkToolPolicyView",
        "HostToolingOptions",
        "default_framework_tool_policy_view",
    }
)

EXPECTED_COMMAND_EXPORTS: frozenset[str] = frozenset(
    {
        "cancel_run",
        "cancel_session_runs",
        "close_session",
        "create_session",
        "ensure_session",
        "get_run",
        "get_session",
        "open_host",
        "purge_session",
        "replay_run",
        "resolve_wait",
        "retry_run",
        "submit_followup",
    }
)

ROOT_INTERNAL_API_NAMES: frozenset[str] = frozenset(
    {
        "HostCommandFacet",
        "HostCommandHandleOptions",
        "HostEventStream",
        "HostEventView",
        "HostInput",
        "HostLocalExecutionOptions",
        "StartRunRequest",
    }
)

EXPECTED_HOST_EXPORTS: frozenset[str] = (
    (EXPECTED_API_EXPORTS - ROOT_INTERNAL_API_NAMES)
    | EXPECTED_TOOLING_EXPORTS
    | EXPECTED_COMMAND_EXPORTS
)

FORBIDDEN_HOST_ROOT_EXPORTS: frozenset[str] = frozenset(
    {
        "ActiveWorkerRegistry",
        "DefaultToolRuntimeFactory",
        "HostAdmissionService",
        "HostDispatchScheduler",
        "HostDurableStore",
        "HostDurableStoreOptions",
        "HostEventStream",
        "HostEventView",
        "HostCommandFacet",
        "HostCommandHandle",
        "HostCommandHandleOptions",
        "HostLocalExecutionOptions",
        "StartRunRequest",
        "ToolRuntimeBuildRequest",
        "ToolRuntimeExecutionScope",
        "ToolRuntimeFactory",
        "ToolRuntimeHandle",
        "create_host_command_handle",
        "open_host_durable_store",
        "start_run",
        "stream_run_events",
    }
)

REMOVED_SERVICE_FACING_ALL_EXPORTS: frozenset[str] = frozenset(
    {
        "CompactorExecutionBaseline",
        "HostCommandHandle",
        "HostCommandFacet",
        "HostCommandHandleOptions",
        "HostEventStream",
        "HostEventView",
        "HostHandle",
        "HostInput",
        "HostLocalExecutionOptions",
        "StartRunRequest",
        "create_host_command_handle",
        "start_run",
        "stream_run_events",
    }
)

INTERNAL_PURGE_DURABLE_EXPORTS: frozenset[str] = frozenset(
    {
        "PURGE_IDEMPOTENCY_RESULT_KIND",
        "PURGE_IDEMPOTENCY_SCOPE_KIND",
        "PurgeCommitCleanupRefs",
        "PurgeDeleteCounts",
        "PurgePreconditionSnapshot",
        "PurgeReplayDecision",
        "PurgeReplayDecisionKind",
        "PurgeSessionAlreadyPurgedError",
        "PurgeSessionDeleteRequest",
        "PurgeSessionDeleteResult",
        "PurgeSessionInvalidStateError",
        "PurgeSessionNotFoundError",
        "PurgeTombstoneAuditRecordRequest",
        "PurgeTombstoneAuditRecordResult",
        "PurgeTombstoneAuditRecorder",
        "PurgeTombstoneRow",
        "build_deleted_counts_digest",
        "build_purge_semantic_digest",
        "insert_purge_tombstone",
        "purge_session_durable",
        "read_purge_tombstone_by_id",
        "read_purge_tombstone_by_session_id",
        "record_or_read_purge_idempotency",
    }
)


def test_host_all_matches_current_public_contracts() -> None:
    """``dayu.host.__all__`` 匹配当前 public contract。"""

    actual = frozenset(host.__all__)
    assert actual == EXPECTED_HOST_EXPORTS, (
        f"missing={EXPECTED_HOST_EXPORTS - actual}; extra={actual - EXPECTED_HOST_EXPORTS}"
    )


def test_host_root_does_not_export_internal_services() -> None:
    """Service/UI 从包根不能取得 Host 内部 service 或 runtime 边界。"""

    package_symbols = vars(host)
    assert not (FORBIDDEN_HOST_ROOT_EXPORTS & frozenset(package_symbols))
    assert "CompactorExecutionBaseline" not in package_symbols


def test_api_all_stays_request_snapshot_boundary() -> None:
    """``dayu.host.api.__all__`` 只包含 API 与本地执行配置类型。"""

    assert frozenset(api.__all__) == EXPECTED_API_EXPORTS


def test_read_api_all_keeps_service_facing_read_boundary() -> None:
    """``dayu.host.read_api.__all__`` 不重新公开 run-level stream。"""

    assert frozenset(read_api.__all__) == frozenset({"get_run", "get_session"})


def test_exported_symbols_are_same_objects_as_api_symbols() -> None:
    """api 类型在包根导出时必须直接来自 ``dayu.host.api``。"""

    for name in EXPECTED_API_EXPORTS - ROOT_INTERNAL_API_NAMES:
        assert vars(host)[name] is vars(api)[name]


def test_tooling_symbols_are_exported_from_package_root() -> None:
    """tooling 类型从包根导出，但不进入 ``dayu.host.api``。"""

    for name in EXPECTED_TOOLING_EXPORTS:
        assert name in vars(host)
        assert name not in vars(api)


def test_command_symbols_are_exported_from_package_root_only() -> None:
    """command facade 从包根导出，但不进入 ``dayu.host.api``。"""

    for name in EXPECTED_COMMAND_EXPORTS:
        assert name in vars(host)
        assert name not in vars(api)


def test_removed_low_level_symbols_are_not_service_facing_all_exports() -> None:
    """低层历史入口不再进入 ``dayu.host.__all__`` 的 Service-facing 边界。"""

    assert not (REMOVED_SERVICE_FACING_ALL_EXPORTS & frozenset(host.__all__))


def test_removed_low_level_symbols_are_not_package_root_attributes() -> None:
    """低层历史入口不再作为 ``dayu.host`` 模块属性暴露。"""

    assert not (REMOVED_SERVICE_FACING_ALL_EXPORTS & frozenset(vars(host)))


def test_purge_durable_symbols_are_not_package_root_exports() -> None:
    """purge durable helper 不进入 ``dayu.host`` Service-facing 根命名空间。"""

    assert not (INTERNAL_PURGE_DURABLE_EXPORTS & frozenset(host.__all__))
    assert not (INTERNAL_PURGE_DURABLE_EXPORTS & frozenset(vars(host)))
