"""``dayu.host`` 包根导出白名单测试。"""

from __future__ import annotations

import dayu.host as host
import dayu.host.api as api


EXPECTED_EXPORTS: frozenset[str] = frozenset(
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
        "HostApiError",
        "HostApiErrorCode",
        "HostCallContext",
        "HostCommandFacet",
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
        "SubmitFollowupRequest",
        "TerminalResultSummary",
        "WaitResolutionSource",
    }
)


def test_host_all_matches_slice1_public_contracts() -> None:
    """``dayu.host.__all__`` 只包含 Slice 1 承诺的公共类型。"""

    actual = frozenset(host.__all__)
    assert actual == EXPECTED_EXPORTS, (
        f"missing={EXPECTED_EXPORTS - actual}; extra={actual - EXPECTED_EXPORTS}"
    )


def test_api_all_matches_package_root_exports() -> None:
    """``dayu.host.api.__all__`` 与包根导出集合保持一致。"""

    assert frozenset(api.__all__) == EXPECTED_EXPORTS


def test_exported_symbols_are_same_objects_as_api_symbols() -> None:
    """包根导出的符号必须直接来自 ``dayu.host.api``。"""

    for name in EXPECTED_EXPORTS:
        assert vars(host)[name] is vars(api)[name]
