"""流式 tool call delta 聚合。

本模块把 SSE 流中的 :class:`_OpenAIToolCallDelta` 增量按 ``index``（或
``id`` 兜底）聚合为最终 :class:`ToolCallRequest` 元组，并解析
``extra_content`` namespace 字段为 :class:`ToolCallProviderState`。

OLD 已验证的兼容点（见 phase1-plan.md §5.3）：

- 同一 tool call 的 ``name`` / ``arguments`` 在多 chunk 上累积。
- 缺失 ``index`` 的 delta 按 ``id`` 归属（OLD ``sse_parser.py:738``）。
- ``function.arguments == None`` 视为 noop，不报错。
- ``extra_content["google"]["thought_signature"]: str`` →
  :class:`GeminiToolCallState`；仅含 ``thought: True`` → ``None``；
  未知 namespace / ``google`` 下未知键 → 触发协议错误（不阻断聚合）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import (
    GeminiToolCallState,
    ToolCallProviderState,
    ToolCallRequest,
)
from dayu.engine.contracts.partial_tool_call import (
    PARTIAL_TOOL_CALL_ID_MAX_CHARS,
    PartialToolCallSummary,
)
from dayu.engine.contracts.runner_events import RunnerProtocolErrorData
from dayu.engine.runners.openai._types import _OpenAIToolCallDelta

_GOOGLE_NAMESPACE: str = "google"
_GEMINI_THOUGHT_SIGNATURE_KEY: str = "thought_signature"
_GEMINI_THOUGHT_KEY: str = "thought"
_KNOWN_GEMINI_KEYS: frozenset[str] = frozenset(
    {_GEMINI_THOUGHT_SIGNATURE_KEY, _GEMINI_THOUGHT_KEY}
)
PARTIAL_TOOL_CALL_SUMMARY_MAX_ITEMS: int = 16
PARTIAL_TOOL_CALL_NAME_FRAGMENT_MAX_CHARS: int = 128


def _bounded_name_fragment(name: str) -> str | None:
    """生成用于协议错误诊断的工具名片段。

    :param name: 已累积的工具名。
    :returns: 空名称返回 ``None``；非空名称返回按字符数截断后的片段。
    :raises Exception: 不主动抛出异常。
    """

    if not name:
        return None
    return name[:PARTIAL_TOOL_CALL_NAME_FRAGMENT_MAX_CHARS]


@dataclass(slots=True)
class _PartialToolCall:
    """累积中的 tool call 状态。"""

    tool_call_id: str | None = None
    name: str = ""
    arguments_buffer: str = ""
    provider_state: ToolCallProviderState | None = None
    extra_content_seen: bool = False


@dataclass(slots=True)
class ToolCallAggregateResult:
    """:meth:`ToolCallAggregator.finalize` 的结果。

    :param tool_calls: 解析成功的 :class:`ToolCallRequest` 元组。
    :param fatal_errors: 校验失败的致命协议错误（例如 ``tool_call_missing_id``、
        ``tool_call_arguments_not_object``、``tool_call_arguments_invalid_json``、
        ``tool_call_missing_name``）。出现任一致命错误时调用方必须收口为
        :class:`RunnerDoneData(FinishReason.ERROR)`，**不得**再产出
        :class:`RunnerToolCallsCompletedData`。
    :param warnings: 非致命警告（例如未知 provider namespace / 未知
        ``google.*`` 键 / 单条 delta 缺 ``index`` 与 ``id``）。调用方按
        顺序发出但不阻断成功收口。
    """

    tool_calls: tuple[ToolCallRequest, ...]
    fatal_errors: tuple[RunnerProtocolErrorData, ...] = field(
        default_factory=tuple
    )
    warnings: tuple[RunnerProtocolErrorData, ...] = field(
        default_factory=tuple
    )


class ToolCallAggregator:
    """流式 tool call 聚合器。

    内部按 fatal / warning 两路累积协议错误：

    - ``fatal``：违反 OpenAI tool_call schema 的硬错误（如 ``tool_call_id``
      缺失、``arguments`` 非合法 JSON 对象 / 非 object）。出现 fatal
      意味着本次 tool calls 不可被下游消费，调用方必须以
      :class:`RunnerDoneData(FinishReason.ERROR)` 收口。
    - ``warning``：解析过程中遇到的非阻断性问题（如 delta 缺
      ``index`` 与 ``id``、未知 provider namespace、未知 ``google.*``
      键）。调用方按顺序发出，**不**影响成功收口。
    """

    def __init__(self, *, provider_request_id: str | None) -> None:
        """初始化聚合器。

        :param provider_request_id: 当前 response header 提供的 request id。
        :raises Exception: 不主动抛出异常。
        """

        self._provider_request_id: str | None = provider_request_id
        self._partials_by_index: dict[int, _PartialToolCall] = {}
        self._index_by_id: dict[str, int] = {}
        # 合成 index 与真实 index 共用一个稠密命名空间，从 0 开始。
        # 既能避免与 provider 提供的真实 ``index`` 冲突，也使 finalize
        # 阶段按 sorted-key 顺序生成的 ``index_in_iteration`` 与本 index
        # 在「单一来源」场景下保持一致，让 SSE delta 与 completed 事件
        # 中的 tool_call_index 可稳定对照。
        self._next_synthetic_index: int = 0
        self._fatal_errors: list[RunnerProtocolErrorData] = []
        self._warnings: list[RunnerProtocolErrorData] = []

    def _allocate_synthetic_index(self) -> int:
        """缺失 ``index`` 但有 ``id`` 时分配的合成顺序键。

        从下一个未被占用（既不在 ``_partials_by_index`` 也未被合成过）
        的整数开始，保证不会与 provider 真实 ``index`` 冲突。
        """

        while self._next_synthetic_index in self._partials_by_index:
            self._next_synthetic_index += 1
        index = self._next_synthetic_index
        self._next_synthetic_index += 1
        return index

    def _resolve_index(
        self,
        delta: _OpenAIToolCallDelta,
        *,
        position: int | None,
    ) -> int | None:
        """把 delta 归属到现有 partial 的 index。

        :param delta: 增量。
        :param position: 当前 delta 在 ``choice.delta.tool_calls`` 数组
            中的位置；用于 OLD 兼容的 “pos fallback continuation” 路径
            （首帧带 ``id``/``name``，后续 arguments 帧既无 ``id`` 又无
            ``index`` 时按数组位置归位）。
        :returns: 命中或新建后的 index；无法归属时返回 ``None``。
        """

        delta_index = delta.get("index")
        if isinstance(delta_index, int):
            return delta_index
        delta_id = delta.get("id")
        if isinstance(delta_id, str) and delta_id:
            existing_index = self._index_by_id.get(delta_id)
            if existing_index is not None:
                return existing_index
            new_index = self._allocate_synthetic_index()
            self._index_by_id[delta_id] = new_index
            return new_index
        # 无 ``id`` 也无 ``index``：若调用方提供了 ``pos``，且该位置已
        # 有 partial，则归到该 partial（OLD ``sse_parser.py`` 的 pos
        # fallback 行为）。
        if (
            position is not None
            and position in self._partials_by_index
        ):
            return position
        return None

    def feed(
        self,
        delta: _OpenAIToolCallDelta,
        *,
        position: int | None = None,
    ) -> int | None:
        """累积一个 tool call delta。

        :param delta: 流式增量。
        :param position: ``choice.delta.tool_calls`` 数组中的位置；用于
            OLD pos fallback continuation 归位。
        :returns: 该 delta 归属的 resolved index；若 delta 既缺
            ``index`` 又缺 ``id``，且无法用 ``position`` 归位，返回
            ``None``（同时累积一条 ``tool_call_missing_index_and_id``
            warning）。

        OLD 兼容点：SSE parser 在 emit ``RunnerToolCallDeltaData`` 之前
        必须使用本返回值作为 ``tool_call_index``；缺 ``index`` 但有 ``id``
        的并行 tool call 才能在 delta 流中稳定区分归属。
        """

        index = self._resolve_index(delta, position=position)
        if index is None:
            self._warnings.append(
                RunnerProtocolErrorData(
                    error_code="tool_call_missing_index_and_id",
                    message="tool call delta missing both index and id",
                    provider_request_id=self._provider_request_id,
                    raw_payload=None,
                    partial_tool_calls=self.partial_summaries(),
                )
            )
            return None
        partial = self._partials_by_index.setdefault(
            index, _PartialToolCall()
        )
        delta_id = delta.get("id")
        if isinstance(delta_id, str) and delta_id:
            partial.tool_call_id = delta_id
            self._index_by_id.setdefault(delta_id, index)
        function = delta.get("function")
        if function is not None:
            name = function.get("name")
            if isinstance(name, str) and name:
                partial.name += name
            arguments = function.get("arguments")
            if isinstance(arguments, str):
                partial.arguments_buffer += arguments
        extra_content = delta.get("extra_content")
        if extra_content is not None:
            partial.extra_content_seen = True
            new_state = self._parse_provider_state(extra_content)
            if new_state is not None:
                partial.provider_state = new_state
        return index

    def _parse_provider_state(
        self, extra_content: Mapping[str, Mapping[str, JsonValue]]
    ) -> ToolCallProviderState | None:
        """解析 ``extra_content`` namespace 字段。

        :param extra_content: tool call delta 上的 ``extra_content``
            字段。
        :returns: 解析得到的 provider state；无法解析时返回 ``None``，
            并在内部累积协议错误事件。
        """

        if not extra_content:
            return None
        for namespace, inner in extra_content.items():
            if namespace != _GOOGLE_NAMESPACE:
                self._warnings.append(
                    RunnerProtocolErrorData(
                        error_code="tool_call_unknown_provider_namespace",
                        message=(
                            f"unknown provider namespace in tool call "
                            f"extra_content: {namespace}"
                        ),
                        provider_request_id=self._provider_request_id,
                        raw_payload=None,
                        partial_tool_calls=self.partial_summaries(),
                    )
                )
                continue
            for key in inner.keys():
                if key not in _KNOWN_GEMINI_KEYS:
                    self._warnings.append(
                        RunnerProtocolErrorData(
                            error_code="tool_call_unknown_gemini_key",
                            message=(
                                f"unknown google.* key in tool call "
                                f"extra_content: {key}"
                            ),
                            provider_request_id=self._provider_request_id,
                            raw_payload=None,
                            partial_tool_calls=self.partial_summaries(),
                        )
                    )
            signature = inner.get(_GEMINI_THOUGHT_SIGNATURE_KEY)
            if isinstance(signature, str):
                return GeminiToolCallState(thought_signature=signature)
        return None

    def finalize(self) -> ToolCallAggregateResult:
        """收口聚合，产出最终 :class:`ToolCallRequest` 元组。

        :returns: :class:`ToolCallAggregateResult`。

        校验规则：

        - ``tool_call_id`` 缺失 → 触发协议错误，跳过该 partial。
        - ``name`` 为空 → 触发协议错误，跳过该 partial。
        - ``arguments_buffer`` 为空字符串 → 视为空对象 ``{}``。
        - ``arguments_buffer`` 非合法 JSON 对象 → 触发协议错误。
        """

        tool_calls: list[ToolCallRequest] = []
        sorted_indices = sorted(self._partials_by_index.keys())
        result_index = 0
        for index in sorted_indices:
            partial = self._partials_by_index[index]
            if partial.tool_call_id is None:
                self._fatal_errors.append(
                    RunnerProtocolErrorData(
                        error_code="tool_call_missing_id",
                        message="tool call missing id at finalize",
                        provider_request_id=self._provider_request_id,
                        raw_payload=None,
                        partial_tool_calls=self.partial_summaries(),
                    )
                )
                continue
            if not partial.name:
                self._fatal_errors.append(
                    RunnerProtocolErrorData(
                        error_code="tool_call_missing_name",
                        message=(
                            f"tool call {partial.tool_call_id} missing name"
                        ),
                        provider_request_id=self._provider_request_id,
                        raw_payload=None,
                        partial_tool_calls=self.partial_summaries(),
                    )
                )
                continue
            arguments = self._parse_arguments(
                partial.arguments_buffer,
                tool_call_id=partial.tool_call_id,
            )
            if arguments is None:
                continue
            tool_calls.append(
                ToolCallRequest(
                    tool_call_id=partial.tool_call_id,
                    name=partial.name,
                    arguments=arguments,
                    index_in_iteration=result_index,
                    provider_state=partial.provider_state,
                )
            )
            result_index += 1
        return ToolCallAggregateResult(
            tool_calls=tuple(tool_calls),
            fatal_errors=tuple(self._fatal_errors),
            warnings=tuple(self._warnings),
        )

    def partial_summaries(self) -> tuple[PartialToolCallSummary, ...]:
        """生成当前 partial tool call 有界摘要。

        :returns: 按 provider index 排序的 partial summary 元组。
        :raises Exception: 不主动抛出异常。
        """

        summaries: list[PartialToolCallSummary] = []
        for index in sorted(self._partials_by_index.keys())[
            :PARTIAL_TOOL_CALL_SUMMARY_MAX_ITEMS
        ]:
            partial = self._partials_by_index[index]
            arguments_sha256 = (
                None
                if partial.arguments_buffer == ""
                else hashlib.sha256(
                    partial.arguments_buffer.encode("utf-8")
                ).hexdigest()
            )
            summaries.append(
                PartialToolCallSummary(
                    tool_call_index=index,
                    tool_call_id=_bounded_tool_call_id(partial.tool_call_id),
                    name_fragment=_bounded_name_fragment(partial.name),
                    arguments_byte_size=len(
                        partial.arguments_buffer.encode("utf-8")
                    ),
                    arguments_sha256=arguments_sha256,
                )
            )
        return tuple(summaries)

    def _parse_arguments(
        self, buffer: str, *, tool_call_id: str
    ) -> Mapping[str, JsonValue] | None:
        """解析累积的 arguments JSON。"""

        if not buffer:
            return {}
        try:
            parsed = json.loads(buffer)
        except json.JSONDecodeError as exc:
            self._fatal_errors.append(
                RunnerProtocolErrorData(
                    error_code="tool_call_arguments_invalid_json",
                    message=(
                        f"tool call {tool_call_id} arguments invalid: {exc}"
                    ),
                    provider_request_id=self._provider_request_id,
                    raw_payload=None,
                    partial_tool_calls=self.partial_summaries(),
                )
            )
            return None
        if not isinstance(parsed, dict):
            self._fatal_errors.append(
                RunnerProtocolErrorData(
                    error_code="tool_call_arguments_not_object",
                    message=(
                        f"tool call {tool_call_id} arguments is not an object"
                    ),
                    provider_request_id=self._provider_request_id,
                    raw_payload=None,
                    partial_tool_calls=self.partial_summaries(),
                )
            )
            return None
        return parsed


def _bounded_tool_call_id(value: str | None) -> str | None:
    """返回有界 provider tool call id 片段。

    :param value: provider 已给出的 tool call id；未知为 ``None``。
    :returns: 不超过 :data:`PARTIAL_TOOL_CALL_ID_MAX_CHARS` 的 id 片段。
    :raises Exception: 不主动抛出异常。
    """

    if value is None:
        return None
    return value[:PARTIAL_TOOL_CALL_ID_MAX_CHARS]


__all__ = [
    "PARTIAL_TOOL_CALL_NAME_FRAGMENT_MAX_CHARS",
    "PARTIAL_TOOL_CALL_SUMMARY_MAX_ITEMS",
    "ToolCallAggregator",
    "ToolCallAggregateResult",
]
