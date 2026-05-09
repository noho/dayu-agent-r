"""Host P7 RunInputContextSnapshotBuilt fact 构造器。

本模块把 :class:`RunInputBuildResult` 与当前用户输入事件派生为
:class:`RunInputContextSnapshotBuiltData`，作为 EventLog canonical fact
追加。raw payload (model_input_messages / tool_schemas) 完整内联在
``raw_input_messages_json`` / ``raw_tool_schemas_json``；observer 阶段
负责把它们拆成 ``raw_payloads/`` 文件，hot 层只保留摘要。

设计要点：

- builder 是无状态 dataclass，不持有 LRU、事件流或 Engine 状态；
  调用方在每个 attempt 启动前显式构造材料后调用 ``build``。
- 序列化字段（``*_json``）使用 ``json.dumps(..., sort_keys=True,
  ensure_ascii=False)``，保证 replay / 重启后 blob_id 稳定。
- ``raw_input_blob_id`` / ``raw_tool_schemas_blob_id`` 由 ``run_id`` +
  ``iteration_id`` + 角色派生，与 EventLog 行内容解耦，确保 observer
  在 crash 重放后仍能写到同一文件名（``os.replace`` 原子覆盖）。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from dayu.contracts import JsonValue
from dayu.contracts.tool_schema import ToolSchema
from dayu.engine import (
    AgentMessage,
    AssistantMessage,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from dayu.host._run_input_builder import RunInputBuildTrace
from dayu.host._text import truncate_text
from dayu.host._token_estimator import estimate_text_tokens
from dayu.host.contracts import (
    RunEvent,
    RunEventKind,
    RunEventSource,
    RunEventType,
    RunInput,
    RunInputContextMeta,
    RunInputContextSnapshotBuiltData,
    RunInputMessageSummary,
    RunInputToolSchemaSummary,
    UserInputAcceptedData,
)

_BLOB_ID_HEX_PREFIX_LEN: int = 16
_CONTENT_HASH_HEX_PREFIX_LEN: int = 32
_DEFAULT_EXCERPT_CHAR_LIMIT: int = 256
_SOURCE_KIND_CALLER_SYSTEM: str = "caller_system"
_SOURCE_KIND_MEMORY_BLOCK: str = "memory_block"
_SOURCE_KIND_CURRENT_USER: str = "current_user"
_SOURCE_KIND_ASSISTANT: str = "assistant"
_SOURCE_KIND_TOOL_RESULT: str = "tool_result"
_SOURCE_KIND_UNKNOWN: str = "unknown"
_BLOB_ROLE_INPUT: str = "input"
_BLOB_ROLE_TOOLS: str = "tools"
_ERROR_CURRENT_USER_EVENT_KIND: str = (
    "current_user_event must be canonical Host USER_INPUT_ACCEPTED"
)


@dataclass(frozen=True, slots=True)
class RunInputContextFactBuilder:
    """从 RunInput / RunInputBuildTrace 派生 ``RunInputContextSnapshotBuiltData``。

    :param excerpt_char_limit: hot summary 文本截断上限。
    """

    excerpt_char_limit: int = _DEFAULT_EXCERPT_CHAR_LIMIT

    def build(
        self,
        *,
        run_input: RunInput,
        build_trace: RunInputBuildTrace,
        current_user_event: RunEvent,
        tool_schemas: tuple[ToolSchema, ...],
        attempt_index: int,
        iteration_index: int,
        iteration_id: str,
    ) -> RunInputContextSnapshotBuiltData:
        """派生 ``RunInputContextSnapshotBuiltData`` 事实。

        :param run_input: 已交给 Engine 的 RunInput。
        :param build_trace: ``RunInputBuilder`` 产出的 trace。
        :param current_user_event: 当前 Host-owned ``USER_INPUT_ACCEPTED``
            事件。
        :param tool_schemas: 暴露给 Engine 的工具 schema 元组。
        :param attempt_index: Host attempt 序号。
        :param iteration_index: Engine iteration index。
        :param iteration_id: Engine iteration id。
        :returns: ``RunInputContextSnapshotBuiltData``。
        :raises ValueError: ``current_user_event`` 不是 canonical Host
            ``USER_INPUT_ACCEPTED`` 时抛出。
        :raises TypeError: ``current_user_event.data`` 不是
            :class:`UserInputAcceptedData` 时抛出。
        """

        current_user_text = _current_user_text(current_user_event)
        message_summaries = _build_message_summaries(
            messages=run_input.messages,
            excerpt_char_limit=self.excerpt_char_limit,
        )
        tool_schema_summaries = tuple(
            _build_tool_schema_summary(schema) for schema in tool_schemas
        )
        run_id = current_user_event.run_id
        message_dicts = [_message_to_dict(message) for message in run_input.messages]
        schema_dicts = [_tool_schema_to_dict(schema) for schema in tool_schemas]
        raw_input_messages_json = json.dumps(
            message_dicts, ensure_ascii=False, sort_keys=True
        )
        raw_tool_schemas_json = json.dumps(
            schema_dicts, ensure_ascii=False, sort_keys=True
        )
        total_char_size = sum(
            len(_message_text(message)) for message in run_input.messages
        )
        context_meta = RunInputContextMeta(
            message_count=len(run_input.messages),
            role_sequence=tuple(
                _message_role_value(message) for message in run_input.messages
            ),
            total_char_size=total_char_size,
            total_token_estimate=build_trace.total_token_estimate,
            memory_item_count=len(build_trace.items),
            current_user_run_id=run_id,
        )
        raw_input_blob_id = _blob_id(
            run_id=run_id,
            iteration_id=iteration_id,
            role=_BLOB_ROLE_INPUT,
        )
        raw_tool_schemas_blob_id = _blob_id(
            run_id=run_id,
            iteration_id=iteration_id,
            role=_BLOB_ROLE_TOOLS,
        )
        return RunInputContextSnapshotBuiltData(
            iteration_id=iteration_id,
            iteration_index=iteration_index,
            attempt_index=attempt_index,
            current_user_excerpt=truncate_text(
                text=current_user_text, limit=self.excerpt_char_limit
            ),
            current_user_content_hash=_short_sha256(current_user_text),
            current_user_source_cursor=current_user_event.cursor.sequence,
            message_summaries=message_summaries,
            tool_schema_summaries=tool_schema_summaries,
            context_meta=context_meta,
            raw_input_messages_json=raw_input_messages_json,
            raw_tool_schemas_json=raw_tool_schemas_json,
            raw_input_blob_id=raw_input_blob_id,
            raw_tool_schemas_blob_id=raw_tool_schemas_blob_id,
        )


def _current_user_text(event: RunEvent) -> str:
    """从当前用户输入事件读取正文。

    :param event: 当前用户输入事件。
    :returns: 用户输入正文。
    :raises ValueError: 事件非 canonical Host ``USER_INPUT_ACCEPTED`` 时
        抛出。
    :raises TypeError: data 类型不匹配时抛出。
    """

    if (
        event.type is not RunEventType.USER_INPUT_ACCEPTED
        or event.kind is not RunEventKind.CANONICAL
        or event.source is not RunEventSource.HOST
    ):
        raise ValueError(_ERROR_CURRENT_USER_EVENT_KIND)
    data = event.data
    if not isinstance(data, UserInputAcceptedData):
        raise TypeError("USER_INPUT_ACCEPTED data must be UserInputAcceptedData")
    return data.content


def _build_message_summaries(
    *,
    messages: tuple[AgentMessage, ...],
    excerpt_char_limit: int,
) -> tuple[RunInputMessageSummary, ...]:
    """构造每条消息的 hot summary。

    :param messages: RunInput 消息。
    :param excerpt_char_limit: 截断上限。
    :returns: summary 元组。
    :raises Exception: 不主动抛出异常。
    """

    summaries: list[RunInputMessageSummary] = []
    seen_first_system = False
    for message in messages:
        text = _message_text(message)
        source_kind = _resolve_source_kind(
            message=message,
            seen_first_system=seen_first_system,
        )
        if isinstance(message, SystemMessage) and not seen_first_system:
            seen_first_system = True
        summaries.append(
            RunInputMessageSummary(
                role=_message_role_value(message),
                source_kind=source_kind,
                excerpt=truncate_text(text=text, limit=excerpt_char_limit),
                content_hash=_short_sha256(text),
                char_size=len(text),
                token_estimate=estimate_text_tokens(text),
            )
        )
    return tuple(summaries)


def _resolve_source_kind(
    *,
    message: AgentMessage,
    seen_first_system: bool,
) -> str:
    """判定消息来源类别。

    简化策略：所有处于消息序列前缀（在出现第一条 SystemMessage 之前
    或本身即为第一条 SystemMessage 的位置）的 SystemMessage 归入
    ``caller_system``，其余 SystemMessage 视作 ``memory_block``；
    UserMessage 归 ``current_user``，AssistantMessage 归 ``assistant``，
    ToolMessage 归 ``tool_result``。

    :param message: 当前消息。
    :param seen_first_system: 在当前位置之前是否已出现过 SystemMessage。
    :returns: source_kind 字面量。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(message, SystemMessage):
        # 第一条 SystemMessage 视作 caller_system；其余视为 memory_block。
        if not seen_first_system:
            return _SOURCE_KIND_CALLER_SYSTEM
        return _SOURCE_KIND_MEMORY_BLOCK
    if isinstance(message, UserMessage):
        return _SOURCE_KIND_CURRENT_USER
    if isinstance(message, AssistantMessage):
        return _SOURCE_KIND_ASSISTANT
    if isinstance(message, ToolMessage):
        return _SOURCE_KIND_TOOL_RESULT
    return _SOURCE_KIND_UNKNOWN


def _build_tool_schema_summary(schema: ToolSchema) -> RunInputToolSchemaSummary:
    """构造 tool schema 的 hot summary。

    :param schema: 工具 schema。
    :returns: summary。
    :raises Exception: 不主动抛出异常。
    """

    schema_dict = _tool_schema_to_dict(schema)
    schema_text = json.dumps(schema_dict, ensure_ascii=False, sort_keys=True)
    return RunInputToolSchemaSummary(
        name=schema.function.name,
        schema_hash=_short_sha256(schema_text),
    )


def _message_text(message: AgentMessage) -> str:
    """读取消息正文。

    :param message: AgentMessage。
    :returns: 正文文本。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(message, AssistantMessage):
        return "" if message.content is None else message.content
    return message.content


def _message_role_value(message: AgentMessage) -> str:
    """读取消息 role 字面量。

    :param message: AgentMessage。
    :returns: role 字面量。
    :raises Exception: 不主动抛出异常。
    """

    return message.role.value


def _message_to_dict(message: AgentMessage) -> dict[str, JsonValue]:
    """把 AgentMessage 扁平化为 raw JSON dict。

    :param message: AgentMessage。
    :returns: raw JSON dict。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(message, SystemMessage):
        return {"role": message.role.value, "content": message.content}
    if isinstance(message, UserMessage):
        return {"role": message.role.value, "content": message.content}
    if isinstance(message, AssistantMessage):
        tool_calls: list[JsonValue] = []
        for call in message.tool_calls:
            tool_calls.append(
                {
                    "id": call.id,
                    "name": call.name,
                    "arguments": dict(call.arguments),
                }
            )
        return {
            "role": message.role.value,
            "content": message.content,
            "reasoning_content": message.reasoning_content,
            "tool_calls": tool_calls,
        }
    if isinstance(message, ToolMessage):
        return {
            "role": message.role.value,
            "tool_call_id": message.tool_call_id,
            "content": message.content,
        }
    return {"role": "unknown", "content": ""}


def _tool_schema_to_dict(schema: ToolSchema) -> dict[str, JsonValue]:
    """把 ToolSchema 扁平化为 OpenAI 兼容 JSON dict。

    :param schema: 工具 schema。
    :returns: dict。
    :raises Exception: 不主动抛出异常。
    """

    parameters = schema.function.parameters
    parameter_dict: dict[str, JsonValue] = {
        "type": parameters.type,
        "properties": dict(parameters.properties),
        "required": list(parameters.required),
    }
    if parameters.additional_properties is not None:
        parameter_dict["additionalProperties"] = parameters.additional_properties
    return {
        "type": schema.type,
        "function": {
            "name": schema.function.name,
            "description": schema.function.description,
            "parameters": parameter_dict,
        },
    }


def _short_sha256(text: str) -> str:
    """返回 sha256 16-byte 前缀十六进制。

    :param text: 输入文本。
    :returns: 32 个十六进制字符。
    :raises Exception: 不主动抛出异常。
    """

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[
        :_CONTENT_HASH_HEX_PREFIX_LEN
    ]


def _blob_id(*, run_id: str, iteration_id: str, role: str) -> str:
    """计算 raw_payload blob id。

    :param run_id: Run id。
    :param iteration_id: 迭代 id。
    :param role: 角色字面量（``input`` / ``tools``）。
    :returns: blob id（hex 16 字符）。
    :raises Exception: 不主动抛出异常。
    """

    payload = f"{run_id}|{iteration_id}|{role}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[
        :_BLOB_ID_HEX_PREFIX_LEN
    ]


__all__ = ["RunInputContextFactBuilder"]
