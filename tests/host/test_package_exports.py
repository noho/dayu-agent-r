"""``dayu.host`` 包根导出白名单测试。"""

from __future__ import annotations

import inspect

import dayu.host as host
import dayu.host.api as api
import dayu.host.context_fallback as context_fallback
import dayu.host.memory as memory
import dayu.host.read_api as read_api
import dayu.host.wait_callback as wait_callback

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
        "HOST_TRANSIENT_DELTA_TYPE_TO_DATA",
        "HOST_EVENT_STREAM_DEFAULT_LIMIT",
        "HOST_EVENT_STREAM_MAX_LIMIT",
        "HOST_OUTBOX_TERMINAL_READ_MAX_LIMIT",
        "HOST_OUTBOX_TERMINAL_SEEN_IDS_MAX_COUNT",
        "TERMINAL_RUN_STATUSES",
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
        "HostAdmin",
        "HostActivityCounts",
        "HostActivityKind",
        "HostActivitySeverity",
        "HostActivityStatus",
        "HostActivityView",
        "HostContextUsageView",
        "ContextEstimateMethod",
        "ContextPressureLevel",
        "HostCallContext",
        "HostClosedError",
        "HostContentDelta",
        "HostEvent",
        "HostEventClass",
        "HostEventKind",
        "HostFinalAnswerView",
        "HostMetadataEntry",
        "HostPayloadRef",
        "HostReasoningDelta",
        "HostSessionEventAdmissionDetail",
        "HostSessionEventAdmissionReason",
        "HostSessionEvent",
        "HostSessionEventDeliveryDetail",
        "HostSessionEventDeliveryPolicy",
        "HostSessionEventDeliveryReason",
        "HostSessionEventIterator",
        "HostSessionAccessMode",
        "HostSessionAttachment",
        "HostSessionAttachmentConflictDetail",
        "HostSessionAttachmentConflictReason",
        "HostSessionMutationErrorDetail",
        "HostSessionMutationRejectionReason",
        "HostStreamCursor",
        "HostTerminalStatus",
        "HostToolCallDelta",
        "HostTransientDelta",
        "HostTransientDeltaData",
        "HostTransientDeltaType",
        "HostUnavailableDetail",
        "ListSessionsResult",
        "LocalEngineWorker",
        "LocalEngineWorkerFactory",
        "LocalWorkerHandle",
        "OpenHostOptions",
        "OpenHostAdminOptions",
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
        "SessionListItem",
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
        "is_terminal_run_status",
    }
)

EXPECTED_TOOLING_EXPORTS: frozenset[str] = frozenset(
    {
        "FrameworkToolName",
        "FrameworkToolPolicyView",
        "HostToolingOptions",
        "ProcessCapsuleInterruptPolicy",
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
        "list_sessions",
        "open_host",
        "open_host_admin",
        "purge_session",
        "replay_run",
        "report_storage_usage",
        "resolve_wait",
        "retry_run",
        "run_storage_maintenance",
        "submit_followup",
    }
)

EXPECTED_WAIT_CALLBACK_EXPORTS: frozenset[str] = frozenset(
    {
        "CallbackWaitResolvePort",
        "CallbackWaitResolveResult",
        "DefaultWaitCallbackAdapter",
        "WaitCallbackAdapterResult",
        "WaitCallbackAdapterStatus",
        "WaitCallbackAuthAccepted",
        "WaitCallbackAuthInput",
        "WaitCallbackAuthRejected",
        "WaitCallbackAuthResult",
        "WaitCallbackAuthenticator",
        "WaitCallbackCompletionEnvelope",
        "WaitCallbackStateReadPort",
        "WaitCallbackStoredWaitState",
        "WaitCallbackStoredWaitStatus",
        "callback_payload_digest",
    }
)

EXPECTED_STORAGE_MAINTENANCE_EXPORTS: frozenset[str] = frozenset(
    {
        "DEFAULT_ORPHAN_ARTIFACT_GRACE_SECONDS",
        "HostStorageMaintenanceFileError",
        "HostStorageMaintenanceRequest",
        "HostStorageMaintenanceResult",
        "HostStorageUsageReport",
        "HostWalCheckpointMode",
        "HostWalCheckpointResult",
        "MemorySnapshotIntegrityIssue",
        "report_storage_usage",
    }
)

EXPECTED_TOOL_TRACE_ANALYSIS_EXPORTS: frozenset[str] = frozenset(
    {
        "ToolTraceAnalysisPolicy",
        "ToolTraceAnalysisSource",
        "ToolTraceInputMode",
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
    | EXPECTED_WAIT_CALLBACK_EXPORTS
    | EXPECTED_STORAGE_MAINTENANCE_EXPORTS
    | EXPECTED_TOOL_TRACE_ANALYSIS_EXPORTS
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
        "PurgeReplayDecision",
        "PurgeReplayDecisionKind",
        "PurgeSessionAlreadyPurgedError",
        "PurgeSessionDeleteRequest",
        "PurgeSessionDeleteResult",
        "PurgeSessionInvalidStateError",
        "PurgeSessionNotFoundError",
        "PurgeTombstoneRow",
        "build_deleted_counts_digest",
        "build_purge_attempt_ref",
        "build_purge_semantic_digest",
        "build_purge_tombstone_digest",
        "build_purge_tombstone_id",
        "insert_purge_tombstone",
        "purge_session_durable",
        "read_purge_tombstone_by_id",
        "read_purge_tombstone_by_session_id",
        "record_or_read_purge_idempotency",
    }
)

EXPECTED_MEMORY_MODULE_EXPORTS: frozenset[str] = frozenset(
    {
        "CONVERSATION_MEMORY_CONSUMER_ID",
        "CONVERSATION_MEMORY_SNAPSHOT_SCHEMA_VERSION",
        "DEFAULT_ANSWER_ANCHOR_CHAR_CAP",
        "DEFAULT_ANSWER_ANCHOR_ITEM_CAP",
        "DEFAULT_EVIDENCE_FACT_CHAR_CAP",
        "DEFAULT_EVIDENCE_FACT_FLOOR",
        "DEFAULT_EVIDENCE_FACT_ITEM_CAP",
        "DEFAULT_FALLBACK_SELECTED_RECENT_WINDOW_CHAR_CAP",
        "DEFAULT_FALLBACK_SELECTED_RECENT_WINDOW_ITEM_CAP",
        "DEFAULT_FORWARD_INTENT_CHAR_CAP",
        "DEFAULT_FORWARD_INTENT_ITEM_CAP",
        "DEFAULT_MEMORY_CONTEXT_WINDOW_SIZE",
        "DEFAULT_MEMORY_MAX_DELTA_REPAIR_EVENTS",
        "DEFAULT_MEMORY_MAX_LAG_EVENTS_FOR_INLINE_DELTA",
        "DEFAULT_MEMORY_POLICY_REF",
        "DEFAULT_REFERENCE_CONTINUITY_CHAR_CAP",
        "DEFAULT_REFERENCE_CONTINUITY_ITEM_CAP",
        "DEFAULT_REFERENCE_CONTINUITY_ITEM_FLOOR",
        "DEFAULT_SELECTED_RECENT_WINDOW_CHAR_CAP",
        "DEFAULT_SELECTED_RECENT_WINDOW_ITEM_CAP",
        "DEFAULT_SELECTED_RECENT_WINDOW_TURN_FLOOR",
        "DEFAULT_SESSION_SUMMARY_CHAR_CAP",
        "AnswerAnchor",
        "AnswerAnchorChild",
        "AnswerAnchorMemoryView",
        "ConversationMemorySnapshotVNext",
        "EvidenceBackedFactView",
        "EvidenceFactMemoryView",
        "ForwardIntent",
        "ForwardIntentMemoryView",
        "HostEventRef",
        "HostNeutralRefKind",
        "HostPayloadRef",
        "MemoryClaimStatus",
        "MemoryDiagnostic",
        "MemoryDiagnosticReason",
        "MemoryDigestRef",
        "MemoryEvidenceBackedFactKind",
        "MemoryExcludedReason",
        "MemoryIncludedReason",
        "MemoryPolicyDigest",
        "MemoryProducerKind",
        "MemoryProjectionEvent",
        "MemoryProjectionPolicy",
        "MemoryProvenanceRef",
        "MemoryRepairReason",
        "MemoryRepairRequest",
        "MemorySizeUnits",
        "MemorySnapshotCursor",
        "OpaqueMemoryRef",
        "ReferenceContinuityItem",
        "SelectedRecentWindowItem",
        "SelectedRecentWindowRole",
        "SessionSummaryMemoryView",
        "TraceMemoryView",
        "build_conversation_memory_snapshot_from_events",
        "build_empty_conversation_memory_snapshot",
        "build_inline_delta_repair_diagnostic",
        "build_memory_budget_diagnostic",
        "calculate_memory_snapshot_digest",
        "conversation_memory_snapshot_from_json_value",
        "conversation_memory_snapshot_to_json_value",
        "default_memory_projection_policy",
        "digest_memory_projection_policy",
        "estimate_memory_size_units",
        "memory_diagnostic_from_json_value",
        "memory_diagnostic_to_json_value",
        "memory_projection_policy_to_json_value",
        "memory_snapshot_with_cursor_and_diagnostics",
        "project_conversation_memory_event",
        "stable_memory_snapshot_id",
    }
)

EXPECTED_CONTEXT_FALLBACK_MODULE_EXPORTS: frozenset[str] = frozenset(
    {
        "FALLBACK_ACTION_DISPATCH",
        "FALLBACK_ACTION_FAIL_CLOSED",
        "FALLBACK_ACTION_NOT_APPLICABLE",
        "FALLBACK_BUDGET_STATUS_OVER_BUDGET",
        "FALLBACK_BUDGET_STATUS_SELECTION_FAILED",
        "FALLBACK_BUDGET_STATUS_WITHIN_BUDGET",
        "FALLBACK_POLICY_DECISION_RECENT_WINDOW",
        "FALLBACK_POLICY_DECISION_SELECTION_FAILED",
        "ActiveRecentWindowFallback",
        "EventLogContextFallbackProvider",
        "RecentWindowFallbackAction",
        "RecentWindowFallbackBudgetResult",
        "RecentWindowFallbackSelection",
        "build_recent_window_fallback_selection",
        "build_selection_failure_budget_payload",
        "build_selection_failure_window_payload",
        "estimate_recent_window_fallback_budget",
        "fallback_window_digest",
    }
)


def test_host_all_matches_current_public_contracts() -> None:
    """``dayu.host.__all__`` 匹配当前 public contract。"""

    actual = frozenset(host.__all__)
    assert actual == EXPECTED_HOST_EXPORTS, (
        f"missing={EXPECTED_HOST_EXPORTS - actual}; extra={actual - EXPECTED_HOST_EXPORTS}"
    )


def test_memory_module_all_matches_typed_contract_boundary() -> None:
    """``dayu.host.memory.__all__`` 只导出稳定 typed contracts。"""

    actual = frozenset(memory.__all__)
    assert actual == EXPECTED_MEMORY_MODULE_EXPORTS
    assert "_MemoryItemWithId" not in actual
    assert not any(name.startswith("_") for name in actual)


def test_context_fallback_module_all_matches_helper_boundary() -> None:
    """``dayu.host.context_fallback.__all__`` 只导出 fallback contract。"""

    actual = frozenset(context_fallback.__all__)
    assert actual == EXPECTED_CONTEXT_FALLBACK_MODULE_EXPORTS
    assert not any(name.startswith("_") for name in actual)


def test_host_root_does_not_export_internal_services() -> None:
    """Service/UI 从包根不能取得 Host 内部 service 或 runtime 边界。"""

    package_symbols = vars(host)
    assert not (FORBIDDEN_HOST_ROOT_EXPORTS & frozenset(package_symbols))
    assert "CompactorExecutionBaseline" not in package_symbols


def test_api_all_stays_request_snapshot_boundary() -> None:
    """``dayu.host.api.__all__`` 只包含 API 与本地执行配置类型。"""

    assert frozenset(api.__all__) == EXPECTED_API_EXPORTS


def test_host_protocol_exposes_public_handle_methods() -> None:
    """``Host`` Protocol 必须包含 opener public handle 的完整方法面。"""

    expected_async_methods = frozenset(
        {
            "attach_session",
            "cancel_run",
            "cancel_session_runs",
            "close",
            "close_session",
            "create_session",
            "drain_outbox_terminal_items",
            "ensure_session",
            "get_run",
            "get_session",
            "read_outbox_terminal_items",
            "replay_run",
            "resolve_wait",
            "retry_run",
            "submit_followup",
            "watch_session_events",
        }
    )
    actual_async_methods = frozenset(
        name
        for name in expected_async_methods
        if inspect.iscoroutinefunction(getattr(api.Host, name, None))
    )

    assert actual_async_methods == expected_async_methods


def test_host_admin_protocol_is_independent_capability_boundary() -> None:
    """HostAdmin 与 execution Host 必须是无继承关系的独立协议。"""

    admin_methods = frozenset(
        {
            "close",
            "get_session",
            "list_sessions",
            "purge_session",
            "report_storage_usage",
            "run_storage_maintenance",
        }
    )
    assert all(
        inspect.iscoroutinefunction(getattr(api.HostAdmin, name, None))
        for name in admin_methods
    )
    assert inspect.getsource(api.Host).startswith("class Host(Protocol):")
    assert inspect.getsource(api.HostAdmin).startswith("class HostAdmin(Protocol):")
    assert not hasattr(api.Host, "list_sessions")
    assert not hasattr(api.Host, "purge_session")
    assert not hasattr(api.Host, "report_storage_usage")
    assert not hasattr(api.Host, "run_storage_maintenance")
    assert not hasattr(api.HostAdmin, "submit_followup")
    assert not hasattr(api.HostAdmin, "cancel_run")
    assert not hasattr(api.HostAdmin, "watch_session_events")


def test_read_api_all_keeps_service_facing_read_boundary() -> None:
    """``dayu.host.read_api.__all__`` 不重新公开 run-level stream。"""

    assert frozenset(read_api.__all__) == frozenset(
        {"get_run", "get_session", "list_sessions"}
    )


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


def test_wait_callback_symbols_are_exported_from_package_root_only() -> None:
    """callback contract 从包根导出，但不进入 ``dayu.host.api``。"""

    for name in EXPECTED_WAIT_CALLBACK_EXPORTS:
        assert vars(host)[name] is vars(wait_callback)[name]
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
