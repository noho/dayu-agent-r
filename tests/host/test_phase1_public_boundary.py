"""Host P1 public API 边界测试。"""

from __future__ import annotations

import inspect

import dayu.host as host

EXPECTED_EXPORTS: frozenset[str] = frozenset(
    {
        "RunCancelledResult",
        "RunEvent",
        "RunEventCursor",
        "RunEventType",
        "RunFailedResult",
        "RunHandle",
        "RunInput",
        "RunOptions",
        "RunResult",
        "RunState",
        "RunStream",
        "RunSucceededResult",
        "RunSuspendedResult",
        "StartRunRequest",
        "start_run",
    }
)

FORBIDDEN_EXPORTS: frozenset[str] = frozenset(
    {
        "EngineWorker",
        "LocalProxy",
        "ToolExecutor",
        "run_agent_messages",
    }
)


def test_host_all_matches_expected_p1_surface() -> None:
    """``dayu.host.__all__`` 只暴露 P1 最小 public surface。"""

    actual = frozenset(host.__all__)
    assert actual == EXPECTED_EXPORTS, (
        f"missing={EXPECTED_EXPORTS - actual}; extra={actual - EXPECTED_EXPORTS}"
    )


def test_internal_symbols_not_exported_or_attribute_accessible() -> None:
    """EngineWorker / ToolExecutor 等内部符号不得从包根访问。"""

    actual = frozenset(host.__all__)
    assert actual.isdisjoint(FORBIDDEN_EXPORTS), (
        f"forbidden symbols leaked: {actual & FORBIDDEN_EXPORTS}"
    )
    for name in FORBIDDEN_EXPORTS:
        assert not hasattr(host, name), f"{name} unexpectedly accessible"


def test_public_start_run_is_async_entrypoint() -> None:
    """public start_run 必须保持 async 入口语义。"""

    assert inspect.iscoroutinefunction(host.start_run)
