"""Host P7 ToolTraceJsonlSink。

本模块把 EventLog canonical fact 派生的 trace record 实时写入 JSONL 文件，
并把 ``RUN_INPUT_CONTEXT_SNAPSHOT_BUILT`` fact 内联的完整 raw payload 拆为
``raw_payloads/<run_id>_<iteration_id>/<blob_id>.json`` 文件。每行写入后
立即 ``flush + fsync``；raw payload 文件采用 ``os.replace`` 原子改名。

**设计约束**：
- schema 字面量为 ``tool_trace_v2_host``，**不向后兼容 OLD ``tool_trace_v2``**。
- 行内 ``idempotency_key`` 字段为 sha256 of source provenance；analyzer 用
  它去重崩溃 replay 产生的孤儿副本。
- provider secret 只在 ``PROVIDER_PROTOCOL_ERROR`` 的 raw payload 上 scrub；
  scope_token / cursor / prompt / tool result 不做过滤（按 OLD 热/冷分层
  保留，用于真实故障定位）。
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import TypeAlias

from dayu.contracts import JsonValue
from dayu.host._credential_scrub import scrub_explicit_credentials

_TRACE_SCHEMA_VERSION_HOST: str = "tool_trace_v2_host"
_FILE_BYTE_THRESHOLD: int = 10 * 1024 * 1024


class ToolTraceSchemaVersion(StrEnum):
    """Trace schema version 字面量。"""

    TOOL_TRACE_V2_HOST = _TRACE_SCHEMA_VERSION_HOST


class ToolTraceRecordType(StrEnum):
    """Trace record 类型。"""

    TOOL_CALL = "tool_call"
    ITERATION_CONTEXT_SNAPSHOT = "iteration_context_snapshot"
    ITERATION_USAGE = "iteration_usage"
    FINAL_RESPONSE = "final_response"
    PROVIDER_PROTOCOL_ERROR = "provider_protocol_error"


def compute_idempotency_key(
    *,
    schema_version: str,
    trace_type: str,
    run_id: str,
    iteration_id: str,
    tool_call_id: str,
    source_event_position: int,
    record_role: str,
) -> str:
    """计算行级幂等键。

    :param schema_version: trace schema 字面量，例如 ``tool_trace_v2_host``。
    :param trace_type: trace record 类型字面量。
    :param run_id: Run id。
    :param iteration_id: 迭代 id；无 iteration 维度时传空字符串。
    :param tool_call_id: 工具调用 id；无工具维度时传空字符串。
    :param source_event_position: 来源 EventLog global position。
    :param record_role: 同一 source event 内进一步区分子 record 的角色字面
        量（例如 ``"primary"``）。
    :returns: sha256 16-byte 前缀十六进制字符串。
    :raises Exception: 不主动抛出异常。
    """

    payload = "|".join(
        [
            schema_version,
            trace_type,
            run_id,
            iteration_id,
            tool_call_id,
            str(source_event_position),
            record_role,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _scrub_provider_secret(payload: JsonValue) -> JsonValue:
    """递归剔除 provider raw payload 中的显式凭证。

    :param payload: 任意 JSON value。
    :returns: scrub 后的 JSON value（保持原结构，只替换敏感值为 ``"***"``）。
    :raises Exception: 不主动抛出异常。
    """

    return scrub_explicit_credentials(payload)


JsonRecord: TypeAlias = Mapping[str, JsonValue]


@dataclass(slots=True)
class ToolTraceJsonlSink:
    """Trace JSONL 输出 sink。

    :param root_path: JSONL 输出根目录；不存在时由 sink 在首次写入时创建。
    """

    root_path: Path

    def __init__(self, *, root_path: Path) -> None:
        """初始化 sink。

        :param root_path: 根目录路径。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.root_path = root_path

    def append_record_line(
        self,
        *,
        session_id: str,
        record: JsonRecord,
    ) -> Path:
        """向当前 session 的 JSONL 文件追加一行 record。

        每行写完立即 ``flush`` + ``fsync``。文件大小达到 ~10MB 时滚动到下一
        个分片。

        :param session_id: 会话 id；用于路径分片。
        :param record: 已序列化为 ``Mapping[str, JsonValue]`` 的 trace record。
        :returns: 实际写入的 JSONL 文件路径。
        :raises OSError: 写入失败时抛出。
        """

        target_dir = self.root_path / "sessions" / session_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = self._select_jsonl_file(target_dir=target_dir)
        line = json.dumps(dict(record), ensure_ascii=False, sort_keys=True)
        with target_path.open("ab") as handle:
            handle.write(line.encode("utf-8"))
            handle.write(b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        return target_path

    def write_raw_payload_blob(
        self,
        *,
        run_id: str,
        iteration_id: str,
        blob_id: str,
        payload_text: str,
    ) -> Path:
        """原子写入 raw payload 文件。

        实现：先写入 ``<blob_id>.json.tmp`` 并 fsync，再 ``os.replace`` 改名
        到目标路径，避免半文件。

        :param run_id: Run id。
        :param iteration_id: 迭代 id；用于目录分片。
        :param blob_id: 文件名标识；调用方负责提供稳定值。
        :param payload_text: 完整 JSON 文本。
        :returns: 写入的最终文件路径。
        :raises OSError: 写入失败时抛出。
        """

        target_dir = self.root_path / "raw_payloads" / f"{run_id}_{iteration_id}"
        target_dir.mkdir(parents=True, exist_ok=True)
        final_path = target_dir / f"{blob_id}.json"
        tmp_path = target_dir / f"{blob_id}.json.tmp"
        with tmp_path.open("wb") as handle:
            handle.write(payload_text.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, final_path)
        return final_path

    def _select_jsonl_file(self, *, target_dir: Path) -> Path:
        """选择当前 session 下一个可写 JSONL 文件。

        :param target_dir: 会话目录。
        :returns: 文件路径。
        :raises Exception: 不主动抛出异常。
        """

        existing = sorted(target_dir.glob("tool_calls_*.jsonl"))
        if not existing:
            return target_dir / "tool_calls_000001.jsonl"
        latest = existing[-1]
        try:
            size = latest.stat().st_size
        except FileNotFoundError:
            return latest
        if size < _FILE_BYTE_THRESHOLD:
            return latest
        next_index = len(existing) + 1
        return target_dir / f"tool_calls_{next_index:06d}.jsonl"


def now_iso() -> str:
    """返回当前 UTC 时间戳（ISO 8601）。

    :returns: ISO 8601 时间字符串。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 5 个强类型 trace record dataclass。
# 每个 record 自带 ``to_json_record`` 方法，把强类型字段映射为
# ``Mapping[str, JsonValue]``，由 sink 调用 ``append_record_line`` 落 JSONL。
# *_json 字段已是序列化字符串，原样保留（便于 analyzer 直接读取）。
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ToolCallRecord:
    """工具调用 record（含 truncation / fetch_more / cursor 维度）。

    :param schema_version: trace schema 字面量。
    :param trace_type: ``tool_call``。
    :param idempotency_key: 行级幂等键。
    :param recorded_at: ISO 8601 写入时间。
    :param session_id: 会话 id。
    :param run_id: Run id。
    :param source_event_position: 来源 EventLog global position。
    :param iteration_id: 迭代 id。
    :param tool_call_id: 工具调用 id。
    :param tool_name: 工具名。
    :param index_in_iteration: 工具调用在迭代内的序号。
    :param arguments_json: 工具参数 JSON 字符串。
    :param outcome_kind: ``completed`` / ``failed``。
    :param result_value_json: 成功结果 value 的 JSON 字符串；非成功为
        ``None``。
    :param failure_error: 失败错误码；成功为 ``None``。
    :param failure_message: 失败消息；成功为 ``None``。
    :param truncation_scope_token: 截断 scope token；无截断为 ``None``。
    :param truncation_cursor: 截断 cursor 指纹；无截断为 ``None``。
    :param truncation_has_more: 截断 has_more；无截断为 ``None``。
    :param truncation_limit: 截断 limit；无截断为 ``None``。
    :param fetch_more_consumed_cursor: 已消费 cursor 指纹；无补读为 ``None``。
    :param fetch_more_next_cursor: 下一页 cursor 指纹；无补读为 ``None``。
    :param fetch_more_chunk_size: 补读返回元素数量；无补读为 ``None``。
    :param fetch_more_has_more: 补读 has_more；无补读为 ``None``。
    :param cursor_denial_reason: cursor 拒绝原因；非拒绝为 ``None``。
    :param cursor_expired_at_monotonic: cursor 过期单进程时间；非过期为
        ``None``。
    """

    schema_version: str
    trace_type: str
    idempotency_key: str
    recorded_at: str
    session_id: str
    run_id: str
    source_event_position: int
    iteration_id: str
    tool_call_id: str
    tool_name: str
    index_in_iteration: int
    arguments_json: str
    outcome_kind: str
    result_value_json: str | None
    failure_error: str | None
    failure_message: str | None
    truncation_scope_token: str | None
    truncation_cursor: str | None
    truncation_has_more: bool | None
    truncation_limit: int | None
    fetch_more_consumed_cursor: str | None
    fetch_more_next_cursor: str | None
    fetch_more_chunk_size: int | None
    fetch_more_has_more: bool | None
    cursor_denial_reason: str | None
    cursor_expired_at_monotonic: float | None

    def to_json_record(self) -> Mapping[str, JsonValue]:
        """编码为 JSON record。

        :returns: ``Mapping[str, JsonValue]``。
        :raises Exception: 不主动抛出异常。
        """

        record: dict[str, JsonValue] = {
            "schema_version": self.schema_version,
            "trace_type": self.trace_type,
            "idempotency_key": self.idempotency_key,
            "recorded_at": self.recorded_at,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "source_event_position": self.source_event_position,
            "iteration_id": self.iteration_id,
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "index_in_iteration": self.index_in_iteration,
            "arguments_json": self.arguments_json,
            "outcome_kind": self.outcome_kind,
            "result_value_json": self.result_value_json,
            "failure_error": self.failure_error,
            "failure_message": self.failure_message,
            "truncation_scope_token": self.truncation_scope_token,
            "truncation_cursor": self.truncation_cursor,
            "truncation_has_more": self.truncation_has_more,
            "truncation_limit": self.truncation_limit,
            "fetch_more_consumed_cursor": self.fetch_more_consumed_cursor,
            "fetch_more_next_cursor": self.fetch_more_next_cursor,
            "fetch_more_chunk_size": self.fetch_more_chunk_size,
            "fetch_more_has_more": self.fetch_more_has_more,
            "cursor_denial_reason": self.cursor_denial_reason,
            "cursor_expired_at_monotonic": self.cursor_expired_at_monotonic,
        }
        return record


@dataclass(frozen=True, slots=True)
class IterationContextSnapshotRecord:
    """RunInput context snapshot record。

    :param schema_version: trace schema 字面量。
    :param trace_type: ``iteration_context_snapshot``。
    :param idempotency_key: 行级幂等键。
    :param recorded_at: ISO 8601 写入时间。
    :param session_id: 会话 id。
    :param run_id: Run id。
    :param source_event_position: 来源 EventLog global position。
    :param iteration_id: 迭代 id。
    :param iteration_index: Engine iteration index。
    :param attempt_index: Host attempt index。
    :param current_user_excerpt: 当前用户输入截断预览。
    :param current_user_content_hash: 当前用户输入摘要。
    :param current_user_source_cursor: 当前用户输入 RunEvent cursor.sequence。
    :param message_summaries_json: hot summary 列表 JSON。
    :param tool_schema_summaries_json: tool schema summary 列表 JSON。
    :param context_meta_json: 上下文 meta JSON。
    :param raw_input_blob_relative_path: raw_input 文件相对路径。
    :param raw_tool_schemas_blob_relative_path: raw_tool_schemas 文件相对路径。
    """

    schema_version: str
    trace_type: str
    idempotency_key: str
    recorded_at: str
    session_id: str
    run_id: str
    source_event_position: int
    iteration_id: str
    iteration_index: int
    attempt_index: int
    current_user_excerpt: str
    current_user_content_hash: str
    current_user_source_cursor: int | None
    message_summaries_json: str
    tool_schema_summaries_json: str
    context_meta_json: str
    raw_input_blob_relative_path: str
    raw_tool_schemas_blob_relative_path: str

    def to_json_record(self) -> Mapping[str, JsonValue]:
        """编码为 JSON record。

        :returns: ``Mapping[str, JsonValue]``。
        :raises Exception: 不主动抛出异常。
        """

        return {
            "schema_version": self.schema_version,
            "trace_type": self.trace_type,
            "idempotency_key": self.idempotency_key,
            "recorded_at": self.recorded_at,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "source_event_position": self.source_event_position,
            "iteration_id": self.iteration_id,
            "iteration_index": self.iteration_index,
            "attempt_index": self.attempt_index,
            "current_user_excerpt": self.current_user_excerpt,
            "current_user_content_hash": self.current_user_content_hash,
            "current_user_source_cursor": self.current_user_source_cursor,
            "message_summaries_json": self.message_summaries_json,
            "tool_schema_summaries_json": self.tool_schema_summaries_json,
            "context_meta_json": self.context_meta_json,
            "raw_input_blob_relative_path": (self.raw_input_blob_relative_path),
            "raw_tool_schemas_blob_relative_path": (self.raw_tool_schemas_blob_relative_path),
        }


@dataclass(frozen=True, slots=True)
class IterationUsageRecord:
    """Runner usage record。

    :param schema_version: trace schema 字面量。
    :param trace_type: ``iteration_usage``。
    :param idempotency_key: 行级幂等键。
    :param recorded_at: ISO 8601 写入时间。
    :param session_id: 会话 id。
    :param run_id: Run id。
    :param source_event_position: 来源 EventLog global position。
    :param iteration_id: 迭代 id。
    :param prompt_tokens: 提示 token 数。
    :param completion_tokens: 完成 token 数。
    :param total_tokens: 总 token 数。
    """

    schema_version: str
    trace_type: str
    idempotency_key: str
    recorded_at: str
    session_id: str
    run_id: str
    source_event_position: int
    iteration_id: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    def to_json_record(self) -> Mapping[str, JsonValue]:
        """编码为 JSON record。

        :returns: ``Mapping[str, JsonValue]``。
        :raises Exception: 不主动抛出异常。
        """

        return {
            "schema_version": self.schema_version,
            "trace_type": self.trace_type,
            "idempotency_key": self.idempotency_key,
            "recorded_at": self.recorded_at,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "source_event_position": self.source_event_position,
            "iteration_id": self.iteration_id,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True, slots=True)
class FinalResponseRecord:
    """final answer record。

    :param schema_version: trace schema 字面量。
    :param trace_type: ``final_response``。
    :param idempotency_key: 行级幂等键。
    :param recorded_at: ISO 8601 写入时间。
    :param session_id: 会话 id。
    :param run_id: Run id。
    :param source_event_position: 来源 EventLog global position。
    :param iteration_id: 迭代 id；``FinalAnswerData`` 不携带 iteration_id 字
        段，因此 observer 派生时传空字符串。
    :param content: 最终回答正文。
    :param filtered: 是否经过过滤。
    :param degraded: 是否为降级回答。
    :param finish_reason: 完成原因字符串。
    """

    schema_version: str
    trace_type: str
    idempotency_key: str
    recorded_at: str
    session_id: str
    run_id: str
    source_event_position: int
    iteration_id: str
    content: str
    filtered: bool
    degraded: bool
    finish_reason: str

    def to_json_record(self) -> Mapping[str, JsonValue]:
        """编码为 JSON record。

        :returns: ``Mapping[str, JsonValue]``。
        :raises Exception: 不主动抛出异常。
        """

        return {
            "schema_version": self.schema_version,
            "trace_type": self.trace_type,
            "idempotency_key": self.idempotency_key,
            "recorded_at": self.recorded_at,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "source_event_position": self.source_event_position,
            "iteration_id": self.iteration_id,
            "content": self.content,
            "filtered": self.filtered,
            "degraded": self.degraded,
            "finish_reason": self.finish_reason,
        }


@dataclass(frozen=True, slots=True)
class ProviderProtocolErrorRecord:
    """provider 协议错误 record。

    :param schema_version: trace schema 字面量。
    :param trace_type: ``provider_protocol_error``。
    :param idempotency_key: 行级幂等键。
    :param recorded_at: ISO 8601 写入时间。
    :param session_id: 会话 id。
    :param run_id: Run id。
    :param source_event_position: 来源 EventLog global position。
    :param iteration_id: 迭代 id。
    :param error_code: 中性错误码。
    :param message: 人类可读错误描述。
    :param provider_request_id: provider 侧请求 id；缺失为 ``None``。
    :param raw_payload_json: scrub 后的 provider 原始报错 JSON 字符串；缺
        失时为 ``'{"reason":"omitted_no_payload"}'``。
    """

    schema_version: str
    trace_type: str
    idempotency_key: str
    recorded_at: str
    session_id: str
    run_id: str
    source_event_position: int
    iteration_id: str
    error_code: str
    message: str
    provider_request_id: str | None
    raw_payload_json: str

    def to_json_record(self) -> Mapping[str, JsonValue]:
        """编码为 JSON record。

        :returns: ``Mapping[str, JsonValue]``。
        :raises Exception: 不主动抛出异常。
        """

        return {
            "schema_version": self.schema_version,
            "trace_type": self.trace_type,
            "idempotency_key": self.idempotency_key,
            "recorded_at": self.recorded_at,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "source_event_position": self.source_event_position,
            "iteration_id": self.iteration_id,
            "error_code": self.error_code,
            "message": self.message,
            "provider_request_id": self.provider_request_id,
            "raw_payload_json": self.raw_payload_json,
        }


__all__ = [
    "FinalResponseRecord",
    "IterationContextSnapshotRecord",
    "IterationUsageRecord",
    "ProviderProtocolErrorRecord",
    "ToolCallRecord",
    "ToolTraceJsonlSink",
    "_scrub_provider_secret",
    "ToolTraceRecordType",
    "ToolTraceSchemaVersion",
    "compute_idempotency_key",
    "now_iso",
]
