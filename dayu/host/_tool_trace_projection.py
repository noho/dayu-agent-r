"""Host P7 ToolTraceObserver。

把 EventLog canonical fact 派生为 trace record，实时写入
:class:`ToolTraceJsonlSink`。``tx`` 不被使用（trace 完全走文件系统），
保留参数以满足 :class:`ObserverSink` 协议。

派发规则：

- ``TOOL_CALL_REQUESTED`` + ``TOOL_RESULT_ACCEPTED``（同 batch 内按
  ``(iteration_id, tool_call_id)`` 配对）-> 一条
  :class:`ToolCallRecord`。截断信息只来自普通 accepted outcome payload。
- ``RUNNER_USAGE_RECORDED`` -> :class:`IterationUsageRecord`。
- ``FINAL_ANSWER`` -> :class:`FinalResponseRecord`（``iteration_id`` 为
  空字符串，因为 ``FinalAnswerData`` 不携带 iteration 维度）。
- ``PROVIDER_PROTOCOL_ERROR`` -> :class:`ProviderProtocolErrorRecord`，
  raw payload 经 :func:`_scrub_provider_secret` 后写入；缺失 payload
  时写入 ``{"reason": "omitted_no_payload"}``。
- ``RUN_INPUT_CONTEXT_SNAPSHOT_BUILT`` -> 先写 raw_input / raw_tool_schemas
  两个 blob 文件，再写 :class:`IterationContextSnapshotRecord`。

错误处理：``TOOL_CALL_REQUESTED`` 在同 batch 内未配对 ``TOOL_RESULT_ACCEPTED``
时抛 :class:`ProjectionSchemaError`，由 :class:`ProjectionCoordinator`
按 ``BLOCKED_FAILED`` 记录。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from dayu.contracts import JsonValue
from dayu.contracts.tool_outcome import (
    ToolCompletedOutcome,
    ToolFailedOutcome,
)
from dayu.engine import (
    FinalAnswerData,
    ProviderProtocolErrorData,
    RunnerUsageData,
    ToolCallRequestedData,
    ToolResultAcceptedData,
)
from dayu.host._event_observer import (
    ObserverDescriptor,
    ObserverSink,
    ProjectionEventEnvelope,
)
from dayu.host._credential_scrub import (
    scrub_tool_arguments,
    scrub_tool_execution_outcome,
)
from dayu.host._host_storage_transaction import HostStorageTransaction
from dayu.host._tool_trace_jsonl_sink import (
    FinalResponseRecord,
    IterationContextSnapshotRecord,
    IterationUsageRecord,
    ProviderProtocolErrorRecord,
    ToolCallRecord,
    ToolTraceJsonlSink,
    ToolTraceRecordType,
    ToolTraceSchemaVersion,
    _scrub_provider_secret,
    compute_idempotency_key,
    now_iso,
)
from dayu.host.contracts import (
    RunEventKind,
    RunEventSource,
    RunEventType,
    RunInputContextSnapshotBuiltData,
)

_OBSERVER_ID: str = "tool_trace"
_PROJECTION_NAME: str = "tool_trace_v2_host"
_SCHEMA_VERSION_INT: int = 1
_RECORD_ROLE_PRIMARY: str = "primary"
_OUTCOME_COMPLETED: str = "completed"
_OUTCOME_FAILED: str = "failed"
_OMITTED_PAYLOAD_JSON: str = '{"reason": "omitted_no_payload"}'
_RAW_PAYLOADS_DIR: str = "raw_payloads"


class ProjectionSchemaError(Exception):
    """trace projection 命中 schema 不一致时抛出。

    例如 ``TOOL_CALL_REQUESTED`` 在 batch 内未配对 ``TOOL_RESULT_ACCEPTED``。
    被 :class:`ProjectionCoordinator` 记录为 ``BLOCKED_FAILED``，
    checkpoint 不前进，需人工干预。
    """


@dataclass(slots=True)
class _ToolCallGroup:
    """同 ``(iteration_id, tool_call_id)`` 内的事件聚合容器。

    :param requested: ``TOOL_CALL_REQUESTED`` envelope；缺失为 ``None``。
    :param accepted: ``TOOL_RESULT_ACCEPTED`` envelope；缺失为 ``None``。
    """

    requested: ProjectionEventEnvelope | None = None
    accepted: ProjectionEventEnvelope | None = None


@dataclass(slots=True)
class ToolTraceObserver(ObserverSink):
    """tool trace projection observer。

    :param jsonl_sink: 实际负责文件写入的 sink。
    """

    jsonl_sink: ToolTraceJsonlSink
    _schema_version_str: str = field(default=ToolTraceSchemaVersion.TOOL_TRACE_V2_HOST.value, init=False)

    @property
    def descriptor(self) -> ObserverDescriptor:
        """observer 元数据。

        :returns: :class:`ObserverDescriptor`。
        :raises Exception: 不主动抛出异常。
        """

        return ObserverDescriptor(
            observer_id=_OBSERVER_ID,
            projection_name=_PROJECTION_NAME,
            schema_version=_SCHEMA_VERSION_INT,
            required=False,
        )

    async def process(
        self,
        *,
        tx: HostStorageTransaction,
        batch: tuple[ProjectionEventEnvelope, ...],
    ) -> None:
        """处理 EventLog batch。

        ``tx`` 在 P7/P8 trace observer 中不被使用，保留参数以满足
        :class:`ObserverSink` 协议。协议为 async（P8 起 ObserverSink
        协议升级为 async）；当前实现内部仍只做同步 JSONL / 文件写入，
        不 ``await`` 任何下游，但保持 async 签名以匹配协议。

        :param tx: 当前事务（未使用）。
        :param batch: 事件 envelope 元组，按 position 升序。
        :returns: 无返回值。
        :raises ProjectionSchemaError: tool_call 未配对时抛出。
        :raises OSError: JSONL / blob 写入失败时透传。
        """

        _ = tx
        groups: dict[tuple[str, str], _ToolCallGroup] = {}
        for envelope in batch:
            event = envelope.event
            event_type = event.type
            if event_type is RunEventType.TOOL_CALL_REQUESTED:
                self._collect_tool_call(envelope=envelope, groups=groups)
                continue
            if event_type is RunEventType.TOOL_RESULT_ACCEPTED:
                self._collect_tool_call(envelope=envelope, groups=groups)
                continue
            if event_type is RunEventType.RUNNER_USAGE_RECORDED:
                self._emit_iteration_usage(envelope=envelope)
                continue
            if event_type is RunEventType.FINAL_ANSWER:
                self._emit_final_response(envelope=envelope)
                continue
            if event_type is RunEventType.PROVIDER_PROTOCOL_ERROR:
                self._emit_provider_protocol_error(envelope=envelope)
                continue
            if event_type is RunEventType.RUN_INPUT_CONTEXT_SNAPSHOT_BUILT:
                self._emit_iteration_context_snapshot(envelope=envelope)
                continue

        for key, group in groups.items():
            self._emit_tool_call(key=key, group=group)

    def _collect_tool_call(
        self,
        *,
        envelope: ProjectionEventEnvelope,
        groups: dict[tuple[str, str], _ToolCallGroup],
    ) -> None:
        """把单条 tool 维度事件归入对应 group。

        :param envelope: 事件 envelope。
        :param groups: 当前 batch 累积的 group dict。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        key = _tool_call_group_key(envelope=envelope)
        group = groups.get(key)
        if group is None:
            group = _ToolCallGroup()
            groups[key] = group
        event_type = envelope.event.type
        if event_type is RunEventType.TOOL_CALL_REQUESTED:
            group.requested = envelope
        elif event_type is RunEventType.TOOL_RESULT_ACCEPTED:
            group.accepted = envelope

    def _emit_tool_call(
        self,
        *,
        key: tuple[str, str],
        group: _ToolCallGroup,
    ) -> None:
        """发射 tool_call record。

        :param key: ``(iteration_id, tool_call_id)``。
        :param group: 同组事件聚合。
        :returns: 无返回值。
        :raises ProjectionSchemaError: 缺少 requested / accepted 时抛出。
        :raises OSError: JSONL 写入失败时透传。
        """

        if group.requested is None or group.accepted is None:
            raise ProjectionSchemaError(f"tool_call group missing requested/accepted pair: key={key}")
        requested_event = group.requested.event
        requested_data = requested_event.data
        if not isinstance(requested_data, ToolCallRequestedData):
            raise ProjectionSchemaError("TOOL_CALL_REQUESTED data type mismatch")
        accepted_data = group.accepted.event.data
        if not isinstance(accepted_data, ToolResultAcceptedData):
            raise ProjectionSchemaError("TOOL_RESULT_ACCEPTED data type mismatch")
        # trace projection 可被测试、repair 或 backfill 直接喂入未清洗数据；
        # 这里复用 EventLog 同一个幂等 helper 做防御性清洗，避免分叉规则。
        scrubbed_outcome = scrub_tool_execution_outcome(accepted_data.outcome)
        if not isinstance(scrubbed_outcome, (ToolCompletedOutcome, ToolFailedOutcome)):
            raise ProjectionSchemaError("TOOL_RESULT_ACCEPTED outcome type mismatch")
        outcome_kind, result_value_json, failure_error, failure_message = _summarize_outcome(outcome=scrubbed_outcome)
        (
            truncation_scope_token,
            truncation_cursor,
            truncation_has_more,
            truncation_limit,
        ) = _summarize_truncation(outcome=scrubbed_outcome)
        iteration_id, tool_call_id = key
        source_event_position = group.requested.position.value
        idempotency_key = compute_idempotency_key(
            schema_version=self._schema_version_str,
            trace_type=ToolTraceRecordType.TOOL_CALL.value,
            run_id=requested_event.run_id,
            iteration_id=iteration_id,
            tool_call_id=tool_call_id,
            source_event_position=source_event_position,
            record_role=_RECORD_ROLE_PRIMARY,
        )
        record = ToolCallRecord(
            schema_version=self._schema_version_str,
            trace_type=ToolTraceRecordType.TOOL_CALL.value,
            idempotency_key=idempotency_key,
            recorded_at=now_iso(),
            session_id=requested_event.session_id,
            run_id=requested_event.run_id,
            source_event_position=source_event_position,
            iteration_id=iteration_id,
            tool_call_id=tool_call_id,
            tool_name=requested_data.name,
            index_in_iteration=requested_data.index_in_iteration,
            arguments_json=json.dumps(
                dict(scrub_tool_arguments(requested_data.arguments)),
                ensure_ascii=False,
                sort_keys=True,
            ),
            outcome_kind=outcome_kind,
            result_value_json=result_value_json,
            failure_error=failure_error,
            failure_message=failure_message,
            truncation_scope_token=truncation_scope_token,
            truncation_cursor=truncation_cursor,
            truncation_has_more=truncation_has_more,
            truncation_limit=truncation_limit,
            fetch_more_consumed_cursor=None,
            fetch_more_next_cursor=None,
            fetch_more_chunk_size=None,
            fetch_more_has_more=None,
            cursor_denial_reason=None,
            cursor_expired_at_monotonic=None,
        )
        self.jsonl_sink.append_record_line(
            session_id=requested_event.session_id,
            record=record.to_json_record(),
        )

    def _emit_iteration_usage(self, *, envelope: ProjectionEventEnvelope) -> None:
        """发射 iteration_usage record。

        :param envelope: ``RUNNER_USAGE_RECORDED`` envelope。
        :returns: 无返回值。
        :raises ProjectionSchemaError: data 类型不匹配时抛出。
        :raises OSError: JSONL 写入失败时透传。
        """

        event = envelope.event
        data = event.data
        if not isinstance(data, RunnerUsageData):
            raise ProjectionSchemaError("RUNNER_USAGE_RECORDED data type mismatch")
        idempotency_key = compute_idempotency_key(
            schema_version=self._schema_version_str,
            trace_type=ToolTraceRecordType.ITERATION_USAGE.value,
            run_id=event.run_id,
            iteration_id=data.iteration_id,
            tool_call_id="",
            source_event_position=envelope.position.value,
            record_role=_RECORD_ROLE_PRIMARY,
        )
        record = IterationUsageRecord(
            schema_version=self._schema_version_str,
            trace_type=ToolTraceRecordType.ITERATION_USAGE.value,
            idempotency_key=idempotency_key,
            recorded_at=now_iso(),
            session_id=event.session_id,
            run_id=event.run_id,
            source_event_position=envelope.position.value,
            iteration_id=data.iteration_id,
            prompt_tokens=data.prompt_tokens,
            completion_tokens=data.completion_tokens,
            total_tokens=data.total_tokens,
        )
        self.jsonl_sink.append_record_line(
            session_id=event.session_id,
            record=record.to_json_record(),
        )

    def _emit_final_response(self, *, envelope: ProjectionEventEnvelope) -> None:
        """发射 final_response record。

        :param envelope: ``FINAL_ANSWER`` envelope。
        :returns: 无返回值。
        :raises ProjectionSchemaError: data 类型不匹配时抛出。
        :raises OSError: JSONL 写入失败时透传。
        """

        event = envelope.event
        data = event.data
        if not isinstance(data, FinalAnswerData):
            raise ProjectionSchemaError("FINAL_ANSWER data type mismatch")
        idempotency_key = compute_idempotency_key(
            schema_version=self._schema_version_str,
            trace_type=ToolTraceRecordType.FINAL_RESPONSE.value,
            run_id=event.run_id,
            iteration_id="",
            tool_call_id="",
            source_event_position=envelope.position.value,
            record_role=_RECORD_ROLE_PRIMARY,
        )
        record = FinalResponseRecord(
            schema_version=self._schema_version_str,
            trace_type=ToolTraceRecordType.FINAL_RESPONSE.value,
            idempotency_key=idempotency_key,
            recorded_at=now_iso(),
            session_id=event.session_id,
            run_id=event.run_id,
            source_event_position=envelope.position.value,
            iteration_id="",
            content=data.content,
            filtered=data.filtered,
            degraded=data.degraded,
            finish_reason=data.finish_reason.value,
        )
        self.jsonl_sink.append_record_line(
            session_id=event.session_id,
            record=record.to_json_record(),
        )

    def _emit_provider_protocol_error(self, *, envelope: ProjectionEventEnvelope) -> None:
        """发射 provider_protocol_error record。

        :param envelope: ``PROVIDER_PROTOCOL_ERROR`` envelope。
        :returns: 无返回值。
        :raises ProjectionSchemaError: data 类型不匹配时抛出。
        :raises OSError: JSONL 写入失败时透传。
        """

        event = envelope.event
        data = event.data
        if not isinstance(data, ProviderProtocolErrorData):
            raise ProjectionSchemaError("PROVIDER_PROTOCOL_ERROR data type mismatch")
        if data.raw_payload is None:
            raw_payload_json = _OMITTED_PAYLOAD_JSON
        else:
            scrubbed: JsonValue = _scrub_provider_secret(data.raw_payload)
            raw_payload_json = json.dumps(scrubbed, ensure_ascii=False, sort_keys=True)
        idempotency_key = compute_idempotency_key(
            schema_version=self._schema_version_str,
            trace_type=ToolTraceRecordType.PROVIDER_PROTOCOL_ERROR.value,
            run_id=event.run_id,
            iteration_id=data.iteration_id,
            tool_call_id="",
            source_event_position=envelope.position.value,
            record_role=_RECORD_ROLE_PRIMARY,
        )
        record = ProviderProtocolErrorRecord(
            schema_version=self._schema_version_str,
            trace_type=ToolTraceRecordType.PROVIDER_PROTOCOL_ERROR.value,
            idempotency_key=idempotency_key,
            recorded_at=now_iso(),
            session_id=event.session_id,
            run_id=event.run_id,
            source_event_position=envelope.position.value,
            iteration_id=data.iteration_id,
            error_code=data.error_code,
            message=data.message,
            provider_request_id=data.provider_request_id,
            raw_payload_json=raw_payload_json,
        )
        self.jsonl_sink.append_record_line(
            session_id=event.session_id,
            record=record.to_json_record(),
        )

    def _emit_iteration_context_snapshot(self, *, envelope: ProjectionEventEnvelope) -> None:
        """发射 iteration_context_snapshot record，并落 raw payload 文件。

        实现：先 ``write_raw_payload_blob`` 写两份 raw payload（input /
        tools），再 ``append_record_line`` 写 hot summary。两步若 crash，
        replay 后 ``os.replace`` 仍是原子覆盖，``idempotency_key`` 让
        analyzer 去重。

        :param envelope: ``RUN_INPUT_CONTEXT_SNAPSHOT_BUILT`` envelope。
        :returns: 无返回值。
        :raises ProjectionSchemaError: data 类型不匹配时抛出。
        :raises OSError: JSONL / blob 写入失败时透传。
        """

        event = envelope.event
        data = event.data
        if not isinstance(data, RunInputContextSnapshotBuiltData):
            raise ProjectionSchemaError("RUN_INPUT_CONTEXT_SNAPSHOT_BUILT data type mismatch")
        if event.kind is not RunEventKind.CANONICAL or event.source is not RunEventSource.HOST:
            raise ProjectionSchemaError("RUN_INPUT_CONTEXT_SNAPSHOT_BUILT must be canonical host fact")
        self.jsonl_sink.write_raw_payload_blob(
            run_id=event.run_id,
            iteration_id=data.iteration_id,
            blob_id=data.raw_input_blob_id,
            payload_text=data.raw_input_messages_json,
        )
        self.jsonl_sink.write_raw_payload_blob(
            run_id=event.run_id,
            iteration_id=data.iteration_id,
            blob_id=data.raw_tool_schemas_blob_id,
            payload_text=data.raw_tool_schemas_json,
        )
        raw_input_relpath = f"{_RAW_PAYLOADS_DIR}/{event.run_id}_{data.iteration_id}/" f"{data.raw_input_blob_id}.json"
        raw_tools_relpath = (
            f"{_RAW_PAYLOADS_DIR}/{event.run_id}_{data.iteration_id}/" f"{data.raw_tool_schemas_blob_id}.json"
        )
        message_summaries_payload: list[JsonValue] = [
            {
                "role": summary.role,
                "source_kind": summary.source_kind,
                "excerpt": summary.excerpt,
                "content_hash": summary.content_hash,
                "char_size": summary.char_size,
                "token_estimate": summary.token_estimate,
            }
            for summary in data.message_summaries
        ]
        tool_schema_summaries_payload: list[JsonValue] = [
            {
                "name": summary.name,
                "schema_hash": summary.schema_hash,
            }
            for summary in data.tool_schema_summaries
        ]
        context_meta_payload: Mapping[str, JsonValue] = {
            "message_count": data.context_meta.message_count,
            "role_sequence": list(data.context_meta.role_sequence),
            "total_char_size": data.context_meta.total_char_size,
            "total_token_estimate": data.context_meta.total_token_estimate,
            "memory_item_count": data.context_meta.memory_item_count,
            "current_user_run_id": data.context_meta.current_user_run_id,
        }
        idempotency_key = compute_idempotency_key(
            schema_version=self._schema_version_str,
            trace_type=ToolTraceRecordType.ITERATION_CONTEXT_SNAPSHOT.value,
            run_id=event.run_id,
            iteration_id=data.iteration_id,
            tool_call_id="",
            source_event_position=envelope.position.value,
            record_role=_RECORD_ROLE_PRIMARY,
        )
        record = IterationContextSnapshotRecord(
            schema_version=self._schema_version_str,
            trace_type=ToolTraceRecordType.ITERATION_CONTEXT_SNAPSHOT.value,
            idempotency_key=idempotency_key,
            recorded_at=now_iso(),
            session_id=event.session_id,
            run_id=event.run_id,
            source_event_position=envelope.position.value,
            iteration_id=data.iteration_id,
            iteration_index=data.iteration_index,
            attempt_index=data.attempt_index,
            current_user_excerpt=data.current_user_excerpt,
            current_user_content_hash=data.current_user_content_hash,
            current_user_source_cursor=data.current_user_source_cursor,
            message_summaries_json=json.dumps(
                message_summaries_payload,
                ensure_ascii=False,
                sort_keys=True,
            ),
            tool_schema_summaries_json=json.dumps(
                tool_schema_summaries_payload,
                ensure_ascii=False,
                sort_keys=True,
            ),
            context_meta_json=json.dumps(
                dict(context_meta_payload),
                ensure_ascii=False,
                sort_keys=True,
            ),
            raw_input_blob_relative_path=raw_input_relpath,
            raw_tool_schemas_blob_relative_path=raw_tools_relpath,
        )
        self.jsonl_sink.append_record_line(
            session_id=event.session_id,
            record=record.to_json_record(),
        )


def _tool_call_group_key(*, envelope: ProjectionEventEnvelope) -> tuple[str, str]:
    """从 envelope 提取 ``(iteration_id, tool_call_id)`` 用作 group key。

    :param envelope: 工具维度事件 envelope。
    :returns: ``(iteration_id, tool_call_id)``。
    :raises ProjectionSchemaError: data 类型不匹配时抛出。
    """

    event = envelope.event
    data = event.data
    if isinstance(data, ToolCallRequestedData):
        return (data.iteration_id, data.tool_call_id)
    if isinstance(data, ToolResultAcceptedData):
        return (data.iteration_id, data.tool_call_id)
    raise ProjectionSchemaError(f"unexpected tool-dimension event data type: " f"{type(data).__name__}")


def _summarize_outcome(
    *, outcome: ToolCompletedOutcome | ToolFailedOutcome
) -> tuple[str, str | None, str | None, str | None]:
    """将 outcome 编码为 ``(outcome_kind, result_value_json, error, message)``。

    :param outcome: tool result outcome。
    :returns: 四元组。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(outcome, ToolCompletedOutcome):
        result_value_json = json.dumps(outcome.result.value, ensure_ascii=False, sort_keys=True)
        return (_OUTCOME_COMPLETED, result_value_json, None, None)
    return (
        _OUTCOME_FAILED,
        None,
        outcome.result.error,
        outcome.result.message,
    )


def _summarize_truncation(
    *, outcome: ToolCompletedOutcome | ToolFailedOutcome
) -> tuple[str | None, str | None, bool | None, int | None]:
    """提取 truncation 维度字段。

    :param outcome: accepted tool outcome。
    :returns: ``(scope_token, cursor, has_more, limit)``；无 truncation 时
        全部为 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if not isinstance(outcome, ToolCompletedOutcome):
        return (None, None, None, None)
    truncation = outcome.result.truncation
    if truncation is None:
        return (None, None, None, None)
    return (
        truncation.scope_token,
        truncation.cursor,
        truncation.has_more,
        truncation.limit,
    )


__all__ = ["ProjectionSchemaError", "ToolTraceObserver"]
