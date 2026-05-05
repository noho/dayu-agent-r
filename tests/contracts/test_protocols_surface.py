"""``dayu.contracts`` 协议表面测试。

通过反射检查 :class:`ToolExecutor` 与 :class:`CancellationToken` 协议的
用户定义可调用成员集合，确保它们恰好是 Phase 0 锁定的最小表面，不存在
OLD 残留方法。
"""

from __future__ import annotations

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.tool_executor import ToolExecutor


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


def test_tool_executor_surface() -> None:
    """:class:`ToolExecutor` 仅暴露 ``execute`` 方法。"""

    assert _user_defined_callables(ToolExecutor) == {"execute"}


def test_cancellation_token_surface() -> None:
    """:class:`CancellationToken` 仅暴露 ``is_cancelled`` /
    ``cancel_reason`` / ``requested_at`` 方法。"""

    assert _user_defined_callables(CancellationToken) == {
        "is_cancelled",
        "cancel_reason",
        "requested_at",
    }
