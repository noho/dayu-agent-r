"""P7 S1 durable harness config 测试。

确认 ``DurableHarnessConfig.tool_trace_path`` 装配开关：

- ``None`` -> 不装配 :class:`ToolTraceObserver`，bundle 字段为 ``None``，
  coordinator observer 元组不含 trace observer。
- 空字符串 -> 同上。
- 非空字符串 -> 装配，bundle 字段非 ``None``，并出现在 coordinator
  observer 元组中。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dayu.host._durable_harness import (
    DurableHarnessConfig,
    build_durable_harness,
)
from dayu.host._tool_trace_projection import ToolTraceObserver


def _close_bundle(bundle: object) -> None:
    """统一调用 bundle.close()。

    :param bundle: durable harness bundle。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    close = getattr(bundle, "close")
    close()


def test_durable_harness_config_default_tool_trace_path_none_skips_observer() -> None:
    """默认 ``tool_trace_path=None`` 不装配 trace observer。"""

    config = DurableHarnessConfig(database_path=":memory:")
    bundle = build_durable_harness(config=config)
    try:
        assert bundle.tool_trace_observer is None
        for observer in bundle.coordinator.observers:
            assert not isinstance(observer, ToolTraceObserver)
    finally:
        _close_bundle(bundle)


def test_durable_harness_config_empty_tool_trace_path_skips_observer() -> None:
    """空字符串等价于未配置 trace。"""

    config = DurableHarnessConfig(database_path=":memory:", tool_trace_path="")
    bundle = build_durable_harness(config=config)
    try:
        assert bundle.tool_trace_observer is None
        for observer in bundle.coordinator.observers:
            assert not isinstance(observer, ToolTraceObserver)
    finally:
        _close_bundle(bundle)


def test_durable_harness_config_tool_trace_path_set_registers_observer(
    tmp_path: Path,
) -> None:
    """非空 ``tool_trace_path`` 必须装配 trace observer。"""

    trace_dir = tmp_path / "trace"
    config = DurableHarnessConfig(
        database_path=":memory:",
        tool_trace_path=str(trace_dir),
    )
    bundle = build_durable_harness(config=config)
    try:
        assert bundle.tool_trace_observer is not None
        assert any(
            isinstance(o, ToolTraceObserver)
            for o in bundle.coordinator.observers
        )
    finally:
        _close_bundle(bundle)


def test_durable_harness_config_is_immutable() -> None:
    """``DurableHarnessConfig`` 必须 frozen。"""

    config = DurableHarnessConfig(database_path=":memory:")
    with pytest.raises(Exception):
        config.database_path = "/tmp/other.db"  # type: ignore[misc]
