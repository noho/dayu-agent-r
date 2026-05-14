"""``dayu.host`` 包根导出白名单测试。"""

from __future__ import annotations

import dayu.host as host
import dayu.host.api as api


EXPECTED_API_EXPORTS: frozenset[str] = frozenset(
    {
        "AttemptStatus",
        "AuthorizationClaim",
        "CancelMode",
        "CancelRunRequest",
        "CancelSessionRunsRequest",
        "CloseSessionRequest",
        "CreateSessionRequest",
        "EnsureSessionRequest",
        "FollowupBehavior",
        "FollowupSnapshot",
        "HOST_EVENT_STREAM_DEFAULT_LIMIT",
        "HOST_EVENT_STREAM_MAX_LIMIT",
        "HostApiError",
        "HostApiErrorCode",
        "HostApiErrorDetail",
        "HostCallContext",
        "HostCommandFacet",
        "HostCommandHandleOptions",
        "HostEventStream",
        "HostEventView",
        "HostInput",
        "HostMetadataEntry",
        "HostStreamCursor",
        "OperationContext",
        "OutboxSummary",
        "PurgeSessionRequest",
        "PurgeSessionResult",
        "ReplayRunRequest",
        "ResolveWaitRequest",
        "RetryRunRequest",
        "RunSnapshot",
        "RunStatus",
        "SessionSlotRef",
        "SessionSnapshot",
        "SessionStatus",
        "SourceRunRelation",
        "StartRunRequest",
        "SteerConflictDetail",
        "SubmitFollowupRequest",
        "TerminalResultSummary",
        "WaitResolutionSource",
    }
)

EXPECTED_TOOLING_EXPORTS: frozenset[str] = frozenset(
    {
        "FrameworkToolName",
        "FrameworkToolPolicyView",
        "HostToolingOptions",
        "ToolBundleSourceKind",
        "ToolBundleSourceRef",
        "default_framework_tool_policy_view",
    }
)

EXPECTED_COMMAND_EXPORTS: frozenset[str] = frozenset(
    {
        "HostCommandHandle",
        "cancel_run",
        "cancel_session_runs",
        "close_session",
        "create_host_command_handle",
        "create_session",
        "ensure_session",
        "get_run",
        "get_session",
        "purge_session",
        "replay_run",
        "resolve_wait",
        "retry_run",
        "start_run",
        "stream_run_events",
        "submit_followup",
    }
)

EXPECTED_HOST_EXPORTS: frozenset[str] = (
    EXPECTED_API_EXPORTS | EXPECTED_TOOLING_EXPORTS | EXPECTED_COMMAND_EXPORTS
)


def test_host_all_matches_phase1_public_contracts() -> None:
    """``dayu.host.__all__`` 匹配当前 public contract。"""

    actual = frozenset(host.__all__)
    assert actual == EXPECTED_HOST_EXPORTS, (
        f"missing={EXPECTED_HOST_EXPORTS - actual}; extra={actual - EXPECTED_HOST_EXPORTS}"
    )


def test_api_all_stays_request_snapshot_boundary() -> None:
    """``dayu.host.api.__all__`` 仍只包含 request / snapshot / context 类型。"""

    assert frozenset(api.__all__) == EXPECTED_API_EXPORTS


def test_exported_symbols_are_same_objects_as_api_symbols() -> None:
    """api 类型在包根导出时必须直接来自 ``dayu.host.api``。"""

    for name in EXPECTED_API_EXPORTS:
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
