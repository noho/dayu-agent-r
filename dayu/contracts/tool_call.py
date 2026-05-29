"""工具调用请求与批式执行上下文契约。

本模块定义工具调用闭环中的强类型输入：

- :class:`ToolCallRequest`：单次工具调用请求载荷（含
  :data:`ToolCallProviderState` provider 续航状态）。
- :class:`BatchToolExecutionContext`：批式握手共享的运行期上下文
  （run/session/iteration id、超时预算、取消 token、批级 correlation_id）。
- :class:`BatchToolExecutionRequest`：把 ``calls`` 与共享 context 打包，
  作为 :meth:`ToolExecutor.execute` 的唯一入参。
- :class:`GeminiToolCallState` 与 :data:`ToolCallProviderState`：承载 provider
  私有的 tool call 续航状态（如 Gemini ``thought_signature``）；以**封闭联合**
  形式暴露，禁止使用 ``dict[str, Any]`` 或 metadata 万能袋承载。

批式 ``correlation_id`` 形如 ``f"{run_id}:{iteration_id}:tool_batch"``，
仅用于跨 Host observer / ToolRuntime 的中性关联；Engine 不会基于它做
任何治理决策。批内单次工具调用的关联信息由 ``tool_call_id`` 提供。
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeAlias

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue


@dataclass(frozen=True, slots=True)
class GeminiToolCallState:
    """Gemini provider 的 tool call 续航状态。

    用于在多轮工具调用 roundtrip 中回写 Gemini ``thought_signature``，
    使下一轮 assistant message 能向 provider 回传之前思考链对应的
    签名。该字段从 SSE / non-stream 响应中 ``extra_content.google.thought_signature``
    透传而来；outbound 序列化时再写回 provider namespace 形态
    ``{"google": {"thought_signature": ...}}``。

    :param thought_signature: provider 返回的 thought 签名字符串。
    """

    thought_signature: str


ToolCallProviderState: TypeAlias = GeminiToolCallState
"""tool call 续航状态封闭联合。

当前仅含 :class:`GeminiToolCallState` 一个成员；后续若新增 provider
（如 Anthropic ``signature``），按 PEP 604 形如
``GeminiToolCallState | OtherProviderState`` 追加成员，并在所有
``match`` 消费侧补 ``case`` 分支。
"""


@dataclass(frozen=True, slots=True)
class ToolCallRequest:
    """单次工具调用请求。

    :param tool_call_id: 工具调用唯一 id，与 LLM 输出一致。
    :param name: 工具名称。
    :param arguments: 调用参数，强类型 JSON 映射。
    :param index_in_iteration: 本工具调用在当前迭代内的序号（从 0 起）。
    :param provider_state: provider 私有续航状态；为 ``None`` 表示当前
        provider 不需要在 tool call roundtrip 中携带额外签名 / 上下文。
    """

    tool_call_id: str
    name: str
    arguments: Mapping[str, JsonValue]
    index_in_iteration: int
    provider_state: ToolCallProviderState | None

    def __post_init__(self) -> None:
        """校验工具调用请求的最小完整性。

        :returns: ``None``。
        :raises ValueError: ``tool_call_id`` 或 ``name`` 为空 / 纯空白，
            ``arguments`` 含空白 key / 非 JSON 兼容值，或
            ``index_in_iteration`` 为负数时抛出。
        """

        if self.tool_call_id.strip() == "":
            raise ValueError("ToolCallRequest.tool_call_id must be non-empty")
        if self.name.strip() == "":
            raise ValueError("ToolCallRequest.name must be non-empty")
        for key, value in self.arguments.items():
            if key.strip() == "":
                raise ValueError("ToolCallRequest.arguments keys must be non-empty")
            _validate_json_value(value, field_path=f"arguments.{key}")
        if self.index_in_iteration < 0:
            raise ValueError(
                "ToolCallRequest.index_in_iteration must be non-negative"
            )


@dataclass(frozen=True, slots=True)
class BatchToolExecutionContext:
    """批式工具执行共享运行期上下文。

    本上下文在一次 ``ToolExecutor.execute`` 握手内对所有 ``calls`` 共享：

    - 不再包含 ``tool_call_id`` / ``index_in_iteration`` 等单次字段；
      批内每个工具调用自身的 id / index 由 :class:`ToolCallRequest` 承载。
    - ``correlation_id`` 是批级中性关联标识，约定形如
      ``f"{run_id}:{iteration_id}:tool_batch"``；不得用作 trace recorder
      私有入口。

    :param run_id: Agent run 唯一 id。
    :param session_id: 会话 id。
    :param iteration_id: 当前 LLM 迭代 id。
    :param timeout_seconds: Engine 从 AgentPolicy 真源投影到本次批
        握手的整体超时预算，供 ToolExecutor / ToolRuntime 协作设置内部
        超时；``None`` 表示调用方未提供该预算。
    :param cancellation_token: 取消观察 token。
    :param correlation_id: 批级中性跨组件关联标识。
    """

    run_id: str
    session_id: str
    iteration_id: str
    timeout_seconds: float | None
    cancellation_token: CancellationToken
    correlation_id: str | None

    def __post_init__(self) -> None:
        """校验批级运行期上下文。

        :returns: 无返回值。
        :raises ValueError: ``run_id``、``session_id``、``iteration_id`` 为空 /
            纯空白，或 ``timeout_seconds`` 不为 ``None`` 且不是有限正数时抛出。
        """

        if self.run_id.strip() == "":
            raise ValueError("BatchToolExecutionContext.run_id must be non-empty")
        if self.session_id.strip() == "":
            raise ValueError("BatchToolExecutionContext.session_id must be non-empty")
        if self.iteration_id.strip() == "":
            raise ValueError(
                "BatchToolExecutionContext.iteration_id must be non-empty"
            )
        if self.timeout_seconds is not None and (
            not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0
        ):
            raise ValueError(
                "BatchToolExecutionContext.timeout_seconds must be None or"
                " a finite positive number"
            )


def _validate_json_value(value: JsonValue, *, field_path: str) -> None:
    """递归校验工具调用参数值满足 JSON 运行时边界。

    :param value: 待校验 JSON 值。
    :param field_path: 错误消息中的字段路径。
    :returns: ``None``。
    :raises ValueError: 浮点数非有限、对象 key 为空白或值不是 JSON
        兼容结构时抛出。
    """

    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field_path} must be finite JSON number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, field_path=f"{field_path}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            if key.strip() == "":
                raise ValueError(f"{field_path} object keys must be non-empty")
            _validate_json_value(
                nested_value,
                field_path=f"{field_path}.{key}",
            )
        return
    raise ValueError(f"{field_path} must be JSON-compatible")


@dataclass(frozen=True, slots=True)
class BatchToolExecutionRequest:
    """批式工具执行入参。

    :param calls: 本次批内所有工具调用，按 LLM 输出顺序排列；元组语义
        意味着不可变快照。非空：批式执行至少包含一次调用。
    :param context: 共享的批级执行上下文。
    """

    calls: tuple[ToolCallRequest, ...]
    context: BatchToolExecutionContext

    def __post_init__(self) -> None:
        """校验批式入参最小完整性。

        :returns: 无返回值。
        :raises ValueError: ``calls`` 为空或含重复 ``tool_call_id`` 时抛出。
        """

        if not self.calls:
            raise ValueError(
                "BatchToolExecutionRequest.calls must be non-empty"
            )
        seen_tool_call_ids: set[str] = set()
        for call in self.calls:
            if call.tool_call_id in seen_tool_call_ids:
                raise ValueError(
                    "BatchToolExecutionRequest.calls must have unique "
                    f"tool_call_id values; duplicated {call.tool_call_id!r}"
                )
            seen_tool_call_ids.add(call.tool_call_id)


__all__ = [
    "BatchToolExecutionContext",
    "BatchToolExecutionRequest",
    "GeminiToolCallState",
    "ToolCallProviderState",
    "ToolCallRequest",
]
