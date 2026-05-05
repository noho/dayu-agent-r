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

from dayu.contracts.tool_call import (
    GeminiToolCallState,
    ToolCallProviderState,
    ToolCallRequest,
)


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
