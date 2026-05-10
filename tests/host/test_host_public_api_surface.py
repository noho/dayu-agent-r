"""Host P8-S2 公开 API surface 反向断言测试。

S2 删除了 ``dayu.host`` 模块级 ``start_run`` / ``stream_run_events`` /
``get_run_result`` / ``get_tool_fetch_more_handle`` /
``fetch_more_tool_result`` 五个 helper, 以及对应的
:class:`LocalRunHarness` / :class:`HostToolRuntime` 公开方法。本测试
作为 surface 收紧的反向断言, 防止后续无意中再次暴露这些入口。
"""

from __future__ import annotations

import dayu.host as host
from dayu.host._run_harness import LocalRunHarness
from dayu.host._tool_runtime import HostToolRuntime


def test_host_module_does_not_export_legacy_helpers() -> None:
    """``dayu.host`` 包根不再导出 5 个 legacy helper。"""

    forbidden: frozenset[str] = frozenset(
        {
            "start_run",
            "stream_run_events",
            "get_run_result",
            "get_tool_fetch_more_handle",
            "fetch_more_tool_result",
        }
    )
    actual = frozenset(host.__all__)
    leaked = actual & forbidden
    assert leaked == frozenset(), f"forbidden symbols leaked: {leaked}"
    for name in forbidden:
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
