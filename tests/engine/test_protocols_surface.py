"""Engine 协议表面测试。

通过反射检查 :class:`AsyncRunner` 协议的用户定义可调用成员集合，确保
它恰好是 Phase 0 锁定的最小表面，不存在 OLD 残留方法。

:class:`ToolExecutor` / :class:`CancellationToken` 的协议表面归属
:mod:`dayu.contracts`，由 ``tests/contracts/test_protocols_surface.py``
覆盖；本文件不重复测试。
"""

from __future__ import annotations

import inspect

import dayu.engine.agent as agent_module
from dayu.engine.contracts.runner import AsyncRunner


def _user_defined_callables(proto: type) -> set[str]:
    """返回协议自身命名空间内的非下划线可调用成员名集合。

    :param proto: 协议类型。
    :returns: 成员名集合。
    """

    return {
        name
        for name, value in proto.__dict__.items()
        if not name.startswith("_") and callable(value)
    }


def test_async_runner_surface() -> None:
    """:class:`AsyncRunner` 仅暴露 ``call`` / ``is_supports_tool_calling``
    / ``close`` 方法。"""

    assert _user_defined_callables(AsyncRunner) == {
        "call",
        "is_supports_tool_calling",
        "close",
    }


def test_async_runner_structured_output_parameter_is_required() -> None:
    """Protocol 的 structured_output 必须是 required keyword-only 参数。"""

    parameter = inspect.signature(AsyncRunner.call).parameters[
        "structured_output"
    ]

    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty


def test_async_runner_does_not_expose_old_methods() -> None:
    """:class:`AsyncRunner` 不得暴露 OLD 时代的 ``set_tools`` /
    ``get_schemas`` / ``get_tool_display_info`` 等方法。"""

    surface = _user_defined_callables(AsyncRunner)
    assert "set_tools" not in surface
    assert "get_schemas" not in surface
    assert "get_tool_display_info" not in surface


def test_agent_module_does_not_import_concrete_openai_runner_symbol() -> None:
    """Agent 协调模块不得直接持有 OpenAI Runner 实现类符号。"""

    assert "AsyncOpenAIRunner" not in vars(agent_module)
