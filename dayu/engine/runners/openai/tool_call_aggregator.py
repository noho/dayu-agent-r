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
from typing import TypeGuard

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
from dayu.engine.contracts.error_codes import runner_protocol_error_code
from dayu.engine.contracts.runner_events import (
    RunnerDiagnosticSeverity,
    RunnerDiagnosticSource,
    RunnerProtocolErrorData,
    RunnerProviderDiagnosticData,
)
from dayu.engine.runners.openai._types import _OpenAIToolCallDelta

_GOOGLE_NAMESPACE: str = "google"
_GEMINI_THOUGHT_SIGNATURE_KEY: str = "thought_signature"
_GEMINI_THOUGHT_KEY: str = "thought"
_KNOWN_GEMINI_KEYS: frozenset[str] = frozenset({_GEMINI_THOUGHT_SIGNATURE_KEY, _GEMINI_THOUGHT_KEY})
PARTIAL_TOOL_CALL_SUMMARY_MAX_ITEMS: int = 16
PARTIAL_TOOL_CALL_NAME_FRAGMENT_MAX_CHARS: int = 128


def _is_tool_call_index(value: JsonValue | None) -> TypeGuard[int]:
    """判断值是否为合法 tool call index。

    :param value: provider 返回或内部 delta 携带的 index 值。
    :returns: 非 ``bool`` 的 ``int`` 返回 ``True``；其它返回 ``False``。
    :raises Exception: 不主动抛出异常。
    """

    return isinstance(value, int) and not isinstance(value, bool)


def _bounded_name_fragment(name: str) -> str | None:
    """生成用于协议错误诊断的工具名片段。

    :param name: 已累积的工具名。
    :returns: 空名称返回 ``None``；非空名称返回按字符数截断后的片段。
    :raises Exception: 不主动抛出异常。
    """

    if not name:
        return None
    return name[:PARTIAL_TOOL_CALL_NAME_FRAGMENT_MAX_CHARS]


def _sorted_partial_indices(
    partials_by_index: Mapping[int, "_PartialToolCall"],
) -> list[int]:
    """按 provider 原生 index 与合成 index 分区排序 partial key。

    :param partials_by_index: 当前累积的 partial 映射。
    :returns: 原生非负 index 升序在前，合成负数 index 按分配顺序在后。
    :raises Exception: 不主动抛出异常。
    """

    return sorted(
        partials_by_index.keys(),
        key=lambda index: (index < 0, -index if index < 0 else index),
    )


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
    :param warnings: 非致命诊断（例如未知 provider namespace / 未知
        ``google.*`` 键 / 单条 delta 缺 ``index`` 与 ``id``）。调用方按
        顺序发出但不阻断成功收口。
    """

    tool_calls: tuple[ToolCallRequest, ...]
    fatal_errors: tuple[RunnerProtocolErrorData, ...] = field(default_factory=tuple)
    warnings: tuple[RunnerProviderDiagnosticData, ...] = field(default_factory=tuple)


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
        # 合成 index 使用负数 keyspace，避免先收到缺 index delta 后又
        # 收到 provider 原生 index=0 时把两条 tool call 错误合并。
        self._next_synthetic_index: int = -1
        self._index_by_position: dict[int, int] = {}
        self._fatal_errors: list[RunnerProtocolErrorData] = []
        self._warnings: list[RunnerProviderDiagnosticData] = []

    def _allocate_synthetic_index(self) -> int:
        """缺失 ``index`` 但有 ``id`` 时分配的合成顺序键。

        从 ``-1`` 开始向负方向分配，保证不会与 provider 合法原生
        ``index`` 冲突。
        """

        while self._next_synthetic_index in self._partials_by_index:
            self._next_synthetic_index -= 1
        index = self._next_synthetic_index
        self._next_synthetic_index -= 1
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
        if _is_tool_call_index(delta_index):
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
        if position is not None and position in self._index_by_position:
            return self._index_by_position[position]
        if position is not None and position in self._partials_by_index:
            return position
        return None

    def _remap_partial_index(self, *, source_index: int, target_index: int) -> None:
        """把旧 partial 合并到 provider 后续给出的真实 index。

        :param source_index: 先前由 id 归属到的旧 index。
        :param target_index: 后续 delta 携带的 provider 原生 index。
        :returns: ``None``。
        """

        if source_index == target_index:
            return
        source = self._partials_by_index.pop(source_index, None)
        if source is None:
            return
        target = self._partials_by_index.get(target_index)
        if target is None:
            self._partials_by_index[target_index] = source
        else:
            target.tool_call_id = target.tool_call_id or source.tool_call_id
            target.name = source.name + target.name
            target.arguments_buffer = source.arguments_buffer + target.arguments_buffer
            target.extra_content_seen = source.extra_content_seen or target.extra_content_seen
            if target.provider_state is None:
                target.provider_state = source.provider_state
        for item_id, mapped_index in tuple(self._index_by_id.items()):
            if mapped_index == source_index:
                self._index_by_id[item_id] = target_index
        for item_position, mapped_index in tuple(self._index_by_position.items()):
            if mapped_index == source_index:
                self._index_by_position[item_position] = target_index

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
                RunnerProviderDiagnosticData(
                    diagnostic_code="tool_call_missing_index_and_id",
                    severity=RunnerDiagnosticSeverity.WARNING,
                    message="tool call delta missing both index and id",
                    provider_request_id=self._provider_request_id,
                    raw_payload=None,
                    partial_tool_calls=self.partial_summaries(),
                    diagnostic_source=(
                        RunnerDiagnosticSource.TOOL_CALL_AGGREGATOR
                    ),
                )
            )
            return None
        delta_id = delta.get("id")
        if isinstance(delta_id, str) and delta_id:
            existing_index = self._index_by_id.get(delta_id)
            if existing_index is not None and existing_index != index:
                self._remap_partial_index(
                    source_index=existing_index,
                    target_index=index,
                )
            self._index_by_id[delta_id] = index
        partial = self._partials_by_index.setdefault(index, _PartialToolCall())
        if position is not None:
            self._index_by_position[position] = index
        if isinstance(delta_id, str) and delta_id:
            partial.tool_call_id = delta_id
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
                    RunnerProviderDiagnosticData(
                        diagnostic_code="tool_call_unknown_provider_namespace",
                        severity=RunnerDiagnosticSeverity.WARNING,
                        message=(f"unknown provider namespace in tool call " f"extra_content: {namespace}"),
                        provider_request_id=self._provider_request_id,
                        raw_payload=None,
                        partial_tool_calls=self.partial_summaries(),
                        diagnostic_source=(
                            RunnerDiagnosticSource.TOOL_CALL_AGGREGATOR
                        ),
                    )
                )
                continue
            for key in inner.keys():
                if key not in _KNOWN_GEMINI_KEYS:
                    self._warnings.append(
                        RunnerProviderDiagnosticData(
                            diagnostic_code="tool_call_unknown_gemini_key",
                            severity=RunnerDiagnosticSeverity.WARNING,
                            message=(f"unknown google.* key in tool call " f"extra_content: {key}"),
                            provider_request_id=self._provider_request_id,
                            raw_payload=None,
                            partial_tool_calls=self.partial_summaries(),
                            diagnostic_source=(
                                RunnerDiagnosticSource.TOOL_CALL_AGGREGATOR
                            ),
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
        sorted_indices = _sorted_partial_indices(self._partials_by_index)
        result_index = 0
        for index in sorted_indices:
            partial = self._partials_by_index[index]
            if partial.tool_call_id is None:
                self._fatal_errors.append(
                    RunnerProtocolErrorData(
                        error_code=runner_protocol_error_code(
                            "tool_call_missing_id"
                        ),
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
                        error_code=runner_protocol_error_code(
                            "tool_call_missing_name"
                        ),
                        message=(f"tool call {partial.tool_call_id} missing name"),
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
        for index in _sorted_partial_indices(self._partials_by_index)[:PARTIAL_TOOL_CALL_SUMMARY_MAX_ITEMS]:
            partial = self._partials_by_index[index]
            arguments_sha256 = (
                None
                if partial.arguments_buffer == ""
                else hashlib.sha256(partial.arguments_buffer.encode("utf-8")).hexdigest()
            )
            summaries.append(
                PartialToolCallSummary(
                    tool_call_index=index,
                    tool_call_id=_bounded_tool_call_id(partial.tool_call_id),
                    name_fragment=_bounded_name_fragment(partial.name),
                    arguments_byte_size=len(partial.arguments_buffer.encode("utf-8")),
                    arguments_sha256=arguments_sha256,
                )
            )
        return tuple(summaries)

    def _parse_arguments(self, buffer: str, *, tool_call_id: str) -> Mapping[str, JsonValue] | None:
        """解析累积的 arguments JSON。"""

        if not buffer:
            return {}
        try:
            parsed = json.loads(buffer)
        except json.JSONDecodeError as exc:
            self._fatal_errors.append(
                RunnerProtocolErrorData(
                    error_code=runner_protocol_error_code(
                        "tool_call_arguments_invalid_json"
                    ),
                    message=(f"tool call {tool_call_id} arguments invalid: {exc}"),
                    provider_request_id=self._provider_request_id,
                    raw_payload=None,
                    partial_tool_calls=self.partial_summaries(),
                )
            )
            return None
        if not isinstance(parsed, dict):
            self._fatal_errors.append(
                RunnerProtocolErrorData(
                    error_code=runner_protocol_error_code(
                        "tool_call_arguments_not_object"
                    ),
                    message=(f"tool call {tool_call_id} arguments is not an object"),
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
