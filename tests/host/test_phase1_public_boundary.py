"""Host public API 边界测试。"""

from __future__ import annotations

import inspect

import dayu.host as host

EXPECTED_EXPORTS: frozenset[str] = frozenset(
    {
        "HostRunFailedData",
        "RunCancelledResult",
        "RunEventData",
        "RunEvent",
        "RunEventCursor",
        "RunEventKind",
        "RunEventSource",
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
        "get_run_result",
        "start_run",
        "stream_run_events",
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
    """``dayu.host.__all__`` 只暴露当前最小 public surface。"""

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


def test_public_run_read_apis_have_expected_async_shape() -> None:
    """Run 级读取入口保持当前 public API 形态。"""

    assert not inspect.iscoroutinefunction(host.stream_run_events)
    assert inspect.iscoroutinefunction(host.get_run_result)
