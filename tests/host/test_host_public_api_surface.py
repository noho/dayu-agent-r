"""Host P8 公开 API surface 正向 / 反向断言测试。

P8 阶段 ``dayu.host`` 包根只导出 contracts 强类型契约，不把 durable
harness / runtime 内部装配入口提前固定为 public API。S2 删除了
``dayu.host`` 模块级 ``start_run`` / ``stream_run_events`` /
``get_run_result`` / ``get_tool_fetch_more_handle`` /
``fetch_more_tool_result`` 五个 helper, 以及对应的
:class:`LocalRunHarness` / :class:`HostToolRuntime` 公开方法。本测试
同时锁定当前应导出的 contracts 符号与不应泄漏的 legacy / internal 符号。
"""

from __future__ import annotations

import dayu.host as host
from dayu.host._run_harness import LocalRunHarness
from dayu.host._tool_runtime import HostToolRuntime


_EXPECTED_HOST_CONTRACT_EXPORTS: frozenset[str] = frozenset(
    {
        "ContextCompactFailureReason",
        "HostContextAttemptRetryData",
        "HostContextCompactCompletedData",
        "HostContextCompactEventData",
        "HostContextCompactFailedData",
        "HostContextCompactRequestedData",
        "HostContextOverflowObservedData",
        "HostRunFailedData",
        "RunCancelledResult",
        "RunEvent",
        "RunEventCursor",
        "RunEventData",
        "RunEventKind",
        "RunEventSource",
        "RunEventType",
        "RunFailedResult",
        "RunHandle",
        "RunInput",
        "RunInputContextMeta",
        "RunInputContextSnapshotBuiltData",
        "RunInputMessageSummary",
        "RunInputToolSchemaSummary",
        "RunOptions",
        "RunResult",
        "RunState",
        "RunStream",
        "RunSucceededResult",
        "RunSuspendedResult",
        "StartRunRequest",
        "ToolCursorDeniedData",
        "ToolCursorExpiredData",
        "ToolCursorIssuedData",
        "ToolFetchMoreCompletedData",
        "ToolFetchMoreFailedData",
        "ToolFetchMoreFailedResult",
        "ToolFetchMoreRequest",
        "ToolFetchMoreRequestedData",
        "ToolFetchMoreResult",
        "ToolFetchMoreSucceededResult",
        "ToolResultTruncatedData",
        "ToolRuntimeCursor",
        "ToolRuntimeEventData",
        "ToolValueSizeSummary",
        "UserInputAcceptedData",
        "UserInputScope",
    }
)
"""当前 ``dayu.host`` 包根允许导出的 contracts 符号集合。"""


_FORBIDDEN_HOST_ROOT_EXPORTS: frozenset[str] = frozenset(
    {
        "start_run",
        "stream_run_events",
        "get_run_result",
        "get_tool_fetch_more_handle",
        "fetch_more_tool_result",
        "LocalRunHarness",
        "build_durable_harness",
        "HostToolRuntime",
    }
)
"""当前 ``dayu.host`` 包根禁止导出的 legacy / internal 符号集合。"""


def test_host_module_exports_exact_contract_surface() -> None:
    """``dayu.host.__all__`` 精确等于当前 contracts 导出集合。"""

    actual = frozenset(host.__all__)
    assert actual == _EXPECTED_HOST_CONTRACT_EXPORTS
    assert len(host.__all__) == len(_EXPECTED_HOST_CONTRACT_EXPORTS)
    for name in _EXPECTED_HOST_CONTRACT_EXPORTS:
        assert hasattr(host, name), f"{name} missing from dayu.host"


def test_host_module_does_not_export_legacy_helpers() -> None:
    """``dayu.host`` 包根不再导出 legacy helper 与 internal 装配入口。"""

    actual = frozenset(host.__all__)
    leaked = actual & _FORBIDDEN_HOST_ROOT_EXPORTS
    assert leaked == frozenset(), f"forbidden symbols leaked: {leaked}"
    for name in _FORBIDDEN_HOST_ROOT_EXPORTS:
        assert not hasattr(host, name), f"{name} unexpectedly accessible"


def test_local_run_harness_no_longer_exposes_fetch_more_methods() -> None:
    """``LocalRunHarness`` 不再提供公开 fetch_more 方法。"""

    assert getattr(LocalRunHarness, "fetch_more_tool_result", None) is None
    assert getattr(LocalRunHarness, "get_tool_fetch_more_handle", None) is None


def test_in_memory_tool_runtime_no_longer_exposes_fetch_more_methods() -> None:
    """``HostToolRuntime`` 不再提供公开 fetch_more 入口；只保留
    ``execute_tool_call`` 路径承载 framework fetch_more 工具调用。"""

    assert getattr(HostToolRuntime, "get_tool_fetch_more_handle", None) is None
    assert getattr(HostToolRuntime, "fetch_more", None) is None
    assert callable(getattr(HostToolRuntime, "execute_tool_call", None))


def test_host_run_harness_module_does_not_provide_default_harness_helper() -> None:
    """模块级 ``_default_harness_for_running_loop`` / ``_build_default_harness`` 已删除。"""

    import dayu.host._run_harness as run_harness_module

    assert not hasattr(run_harness_module, "_default_harness_for_running_loop")
    assert not hasattr(run_harness_module, "_build_default_harness")
    assert not hasattr(run_harness_module, "start_run")
    assert not hasattr(run_harness_module, "stream_run_events")
    assert not hasattr(run_harness_module, "get_run_result")
    assert not hasattr(run_harness_module, "get_tool_fetch_more_handle")
    assert not hasattr(run_harness_module, "fetch_more_tool_result")
