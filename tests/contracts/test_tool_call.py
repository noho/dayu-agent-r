"""``ToolCallRequest`` 与 ``ToolCallProviderState`` 联合契约测试。

覆盖 Phase 1 contract 补丁（``docs/engine/phase1-plan.md`` §0.1）：

- ``ToolCallRequest.provider_state`` 字段构造与等值（``None`` 与
  Gemini 续航状态两路）。
- ``GeminiToolCallState`` / ``ToolCallProviderState`` 联合穷尽：
  使用 ``match`` 时若新增 provider state 必须扩 case，否则
  pyright 触发 ``assert_never``。
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Final

import pytest

from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    GeminiToolCallState,
    ToolCallProviderState,
    ToolCallRequest,
)


class _StaticCancellationToken:
    """轻量 :class:`CancellationToken` 实现，仅供契约测试。"""

    def __init__(self) -> None:
        """初始化为未取消状态。"""

        self._cancelled: bool = False

    def is_cancelled(self) -> bool:
        """返回是否已取消。"""

        return self._cancelled

    def cancel_reason(self) -> str | None:
        """返回取消原因。"""

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。"""

        return None


_VALID_RUN_ID: Final[str] = "run-1"
_VALID_SESSION_ID: Final[str] = "session-1"
_VALID_ITERATION_ID: Final[str] = "iter-1"
_VALID_CORRELATION_ID: Final[str] = "run-1:iter-1:tool_batch"


def _describe_provider_state(state: ToolCallProviderState | None) -> str:
    """以穷尽 ``match`` 守护 :data:`ToolCallProviderState` 联合。

    :param state: 待描述的 provider 续航状态；``None`` 表示无续航。
    :returns: 中性描述字符串。

    当前 :data:`ToolCallProviderState` 仅含
    :class:`GeminiToolCallState` 一个成员；未来扩展时本函数必须新增
    ``case`` 分支并恢复 ``case _: assert_never(state)`` 守护。
    """

    if state is None:
        return "none"
    match state:
        case GeminiToolCallState():
            return f"gemini:{state.thought_signature}"


def test_tool_call_request_field_set() -> None:
    """``ToolCallRequest`` 字段集合必须包含 ``provider_state``。"""

    fields = {f.name for f in dataclasses.fields(ToolCallRequest)}
    assert fields == {
        "tool_call_id",
        "name",
        "arguments",
        "index_in_iteration",
        "provider_state",
    }


def test_tool_call_request_provider_state_none_default_construction() -> None:
    """构造时 ``provider_state=None`` 合法且字段值正确。"""

    request = ToolCallRequest(
        tool_call_id="id-1",
        name="get_value",
        arguments={"k": "v"},
        index_in_iteration=0,
        provider_state=None,
    )
    assert request.provider_state is None
    assert _describe_provider_state(request.provider_state) == "none"


def test_tool_call_request_with_gemini_provider_state_equality() -> None:
    """构造时携带 Gemini 续航状态 → 等值与字段值正确。"""

    state = GeminiToolCallState(thought_signature="sig-x")
    a = ToolCallRequest(
        tool_call_id="id-1",
        name="get_value",
        arguments={"k": "v"},
        index_in_iteration=0,
        provider_state=state,
    )
    b = ToolCallRequest(
        tool_call_id="id-1",
        name="get_value",
        arguments={"k": "v"},
        index_in_iteration=0,
        provider_state=GeminiToolCallState(thought_signature="sig-x"),
    )
    assert a == b
    assert _describe_provider_state(a.provider_state) == "gemini:sig-x"


def test_gemini_tool_call_state_field_set() -> None:
    """``GeminiToolCallState`` 字段集合必须为 ``{thought_signature}``。"""

    fields = {f.name for f in dataclasses.fields(GeminiToolCallState)}
    assert fields == {"thought_signature"}


def test_provider_state_union_currently_only_gemini() -> None:
    """:data:`ToolCallProviderState` 当前仅含 Gemini 一个成员。

    若未来扩展，本测试断言会引导更新所有 ``match`` 守护。
    """

    state: ToolCallProviderState = GeminiToolCallState(thought_signature="s")
    assert isinstance(state, GeminiToolCallState)


def _make_valid_context(
    *, timeout_seconds: float | None = 5.0
) -> BatchToolExecutionContext:
    """构造合法的 :class:`BatchToolExecutionContext`。

    :param timeout_seconds: 透传给 context 的超时秒数。
    :returns: 合法 context 实例。
    """

    return BatchToolExecutionContext(
        run_id=_VALID_RUN_ID,
        session_id=_VALID_SESSION_ID,
        iteration_id=_VALID_ITERATION_ID,
        timeout_seconds=timeout_seconds,
        cancellation_token=_StaticCancellationToken(),
        correlation_id=_VALID_CORRELATION_ID,
    )


def test_batch_tool_execution_context_accepts_none_or_finite_positive() -> None:
    """``timeout_seconds`` 为 ``None`` 或有限正数时构造合法。"""

    none_ctx = _make_valid_context(timeout_seconds=None)
    assert none_ctx.timeout_seconds is None

    positive_ctx = _make_valid_context(timeout_seconds=1.5)
    assert positive_ctx.timeout_seconds == 1.5


def test_batch_tool_execution_context_rejects_non_positive_and_non_finite() -> None:
    """``timeout_seconds`` 不为 ``None`` 且非有限正数时必须在构造期被拒。"""

    import math

    for invalid_timeout in (0.0, -1.0, -0.0001, math.inf, math.nan):
        with pytest.raises(ValueError):
            _make_valid_context(timeout_seconds=invalid_timeout)


def test_batch_tool_execution_request_rejects_empty_calls() -> None:
    """``calls`` 为空必须在构造期被拒。"""

    with pytest.raises(ValueError):
        BatchToolExecutionRequest(
            calls=(),
            context=_make_valid_context(),
        )


def test_batch_tool_execution_request_accepts_non_empty_calls() -> None:
    """``calls`` 非空时构造合法。"""

    call = ToolCallRequest(
        tool_call_id="id-1",
        name="get_value",
        arguments={"k": "v"},
        index_in_iteration=0,
        provider_state=None,
    )
    request = BatchToolExecutionRequest(
        calls=(call,),
        context=_make_valid_context(),
    )
    assert request.calls == (call,)
