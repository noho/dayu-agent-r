"""Host P7 ToolTraceObserver。

把 EventLog canonical fact 派生为 trace record，实时写入
:class:`ToolTraceJsonlSink`。``tx`` 不被使用（trace 完全走文件系统）；
coordinator 会优先通过非事务协议把 JSONL / blob I/O 移出 SQLite
checkpoint transaction。

派发规则：

- ``TOOL_CALL_REQUESTED`` + ``TOOL_RESULT_ACCEPTED``（按
  ``(iteration_id, tool_call_id)`` 跨 checkpoint batch 配对）-> 一条
  :class:`ToolCallRecord`；record 在 accepted 到达后才完成写出，因此
  ``source_event_position`` 使用 accepted event position。截断信息只来自
  普通 accepted outcome payload。
- ``RUNNER_USAGE_RECORDED`` -> :class:`IterationUsageRecord`。
- ``FINAL_ANSWER`` -> :class:`FinalResponseRecord`（``iteration_id`` 为
  空字符串，因为 ``FinalAnswerData`` 不携带 iteration 维度）。
- ``PROVIDER_PROTOCOL_ERROR`` -> :class:`ProviderProtocolErrorRecord`，
  raw payload 经 :func:`_scrub_provider_secret` 后写入；缺失 payload
  时写入 ``{"reason": "omitted_no_payload"}``。
- ``RUN_INPUT_CONTEXT_SNAPSHOT_BUILT`` -> 先写 raw_input / raw_tool_schemas
  两个 blob 文件，再写 :class:`IterationContextSnapshotRecord`。

错误处理：同一 tool_call 的 request/result 不依赖 checkpoint batch 边界；
observer 会在内存中暂存未配对事件，直到对应事件到达后再发射 record。
"""

import _thread
import asyncio
import json
import threading
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
    NonTransactionalObserverSink,
    ObserverDescriptor,
    ObserverSink,
    ProjectionEventEnvelope,
)
from dayu.host._durable_event_store import DurableRunEventStore
from dayu.host._credential_scrub import (
    _scrub_text_credential_assignments,
    scrub_tool_arguments,
    scrub_tool_execution_outcome,
)
from dayu.host._host_storage_transaction import HostStorageTransaction
from dayu.host._host_storage_transaction import HostStorage
from dayu.host._run_input_raw_payload_store import (
    RunInputRawPayloadKind,
    RunInputRawPayloadReadError,
    RunInputRawPayloadRef,
    get_run_input_raw_payload,
)
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
from dayu.host._tool_result_truncation import extract_truncation_hint
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
class ToolTraceObserver(ObserverSink, NonTransactionalObserverSink):
    """tool trace projection observer。

    :param jsonl_sink: 实际负责文件写入的 sink。
    :param raw_payload_storage: RunInput raw payload side-store 读连接；为
        ``None`` 时 snapshot fact 读取会失败。
    :param event_store: durable EventLog 读连接；用于进程重启后回查已
        checkpoint 的 tool request 事件。
    """

    jsonl_sink: ToolTraceJsonlSink
    raw_payload_storage: HostStorage | None = None
    event_store: DurableRunEventStore | None = None
    _schema_version_str: str = field(default=ToolTraceSchemaVersion.TOOL_TRACE_V2_HOST.value, init=False)
    _pending_tool_call_groups: dict[tuple[str, str], _ToolCallGroup] = field(
        default_factory=dict,
        init=False,
    )
    _pending_lock: _thread.RLock = field(
        default_factory=threading.RLock,
        init=False,
    )

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
        :class:`ObserverSink` 协议。coordinator 正常会调用
        :meth:`process_non_transactional`，让 JSONL / blob I/O 发生在
        checkpoint transaction 外；本方法用于直接测试或旧调用点。

        :param tx: 当前事务（未使用）。
        :param batch: 事件 envelope 元组，按 position 升序。
        :returns: 无返回值。
        :raises ProjectionSchemaError: 事件 data 类型不匹配时抛出。
        :raises OSError: JSONL / blob 写入失败时透传。
        """

        _ = tx
        await self.process_non_transactional(batch=batch)

    async def process_non_transactional(
        self,
        *,
        batch: tuple[ProjectionEventEnvelope, ...],
    ) -> None:
        """在 checkpoint transaction 外处理 EventLog batch。

        同步 JSONL / blob 写入通过 ``asyncio.to_thread`` 放入线程执行，
        避免阻塞 event loop。写入成功后由 coordinator 另启短事务推进
        checkpoint；若 checkpoint 推进失败，后续重放会产生相同
        ``idempotency_key`` 的重复行，由 reader / analyzer 去重。

        :param batch: 事件 envelope 元组，按 position 升序。
        :returns: 无返回值。
        :raises ProjectionSchemaError: 事件 data 类型不匹配时抛出。
        :raises OSError: JSONL / blob 写入失败时透传。
        """

        await asyncio.to_thread(self._process_sync, batch=batch)

    def _process_sync(
        self,
        *,
        batch: tuple[ProjectionEventEnvelope, ...],
    ) -> None:
        """同步处理 EventLog batch 并写入 JSONL / blob sink。

        :param batch: 事件 envelope 元组，按 position 升序。
        :returns: 无返回值。
        :raises ProjectionSchemaError: 事件 data 类型不匹配时抛出。
        :raises OSError: JSONL / blob 写入失败时透传。
        """

        with self._pending_lock:
            for envelope in batch:
                event = envelope.event
                event_type = event.type
                if event_type is RunEventType.TOOL_CALL_REQUESTED:
                    self._collect_tool_call(envelope=envelope)
                    continue
                if event_type is RunEventType.TOOL_RESULT_ACCEPTED:
                    self._collect_tool_call(envelope=envelope)
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

    def _collect_tool_call(
        self,
        *,
        envelope: ProjectionEventEnvelope,
    ) -> None:
        """把单条 tool 维度事件归入对应 group。

        :param envelope: 事件 envelope。
        :returns: 无返回值。
        :raises ProjectionSchemaError: 事件 data 类型不匹配时抛出。
        """

        key = _tool_call_group_key(envelope=envelope)
        group = self._pending_tool_call_groups.get(key)
        if group is None:
            group = _ToolCallGroup()
            self._pending_tool_call_groups[key] = group
        event_type = envelope.event.type
        if event_type is RunEventType.TOOL_CALL_REQUESTED:
            group.requested = envelope
        elif event_type is RunEventType.TOOL_RESULT_ACCEPTED:
            group.accepted = envelope
            if group.requested is None:
                group.requested = self._load_requested_from_eventlog(accepted=envelope)
        if group.requested is not None and group.accepted is not None:
            self._pending_tool_call_groups.pop(key, None)
            self._emit_tool_call(key=key, group=group)

    def _load_requested_from_eventlog(
        self,
        *,
        accepted: ProjectionEventEnvelope,
    ) -> ProjectionEventEnvelope | None:
        """从 durable EventLog 回查 accepted 对应的 requested 事件。

        :param accepted: 当前 ``TOOL_RESULT_ACCEPTED`` envelope。
        :returns: 找到时返回 requested envelope；未配置 durable store 或未命中
            时返回 ``None``。
        :raises ProjectionSchemaError: accepted/requested data 类型不匹配。
        :raises Exception: EventLog 读取失败时透传。
        """

        event_store = self.event_store
        if event_store is None:
            return None
        accepted_key = _tool_call_group_key(envelope=accepted)
        rows = event_store.fetch_run_events_by_type_before_position(
            run_id=accepted.event.run_id,
            event_type=RunEventType.TOOL_CALL_REQUESTED,
            before=accepted.position,
        )
        for position, event in rows:
            candidate = ProjectionEventEnvelope(position=position, event=event)
            if _tool_call_group_key(envelope=candidate) == accepted_key:
                return candidate
        return None

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
        # tool_call record 是 request/result 配对完成后的投影事实；
        # request 可能早于 usage 在旧 batch 到达，使用 accepted position
        # 才能表达该 JSONL record 的完成来源并保持写出序单调。
        source_event_position = group.accepted.position.value
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
            message=_scrub_text_credential_assignments(data.message),
            provider_request_id=data.provider_request_id,
            raw_payload_json=raw_payload_json,
            partial_tool_calls_json=json.dumps(
                [
                    {
                        "tool_call_index": item.tool_call_index,
                        "tool_call_id": item.tool_call_id,
                        "name_fragment": item.name_fragment,
                        "arguments_byte_size": item.arguments_byte_size,
                        "arguments_sha256": item.arguments_sha256,
                    }
                    for item in data.partial_tool_calls
                ],
                ensure_ascii=False,
                sort_keys=True,
            ),
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
        storage = self.raw_payload_storage
        if storage is None:
            raise ProjectionSchemaError("RUN_INPUT_CONTEXT_SNAPSHOT_BUILT raw payload storage missing")
        try:
            raw_input_payload = get_run_input_raw_payload(
                storage=storage,
                ref=RunInputRawPayloadRef(
                    blob_id=data.raw_input_messages_blob_id,
                    content_sha256=data.raw_input_messages_sha256,
                    byte_size=data.raw_input_messages_byte_size,
                ),
                expected_kind=RunInputRawPayloadKind.INPUT_MESSAGES,
            )
            raw_tool_schemas_payload = get_run_input_raw_payload(
                storage=storage,
                ref=RunInputRawPayloadRef(
                    blob_id=data.raw_tool_schemas_blob_id,
                    content_sha256=data.raw_tool_schemas_sha256,
                    byte_size=data.raw_tool_schemas_byte_size,
                ),
                expected_kind=RunInputRawPayloadKind.TOOL_SCHEMAS,
            )
        except RunInputRawPayloadReadError as exc:
            raise ProjectionSchemaError(str(exc)) from exc
        raw_input_path = self.jsonl_sink.write_raw_payload_blob(
            run_id=event.run_id,
            iteration_id=data.iteration_id,
            blob_id=data.raw_input_messages_blob_id,
            payload_text=raw_input_payload.payload_json,
        )
        raw_tool_schemas_path = self.jsonl_sink.write_raw_payload_blob(
            run_id=event.run_id,
            iteration_id=data.iteration_id,
            blob_id=data.raw_tool_schemas_blob_id,
            payload_text=raw_tool_schemas_payload.payload_json,
        )
        root_path = self.jsonl_sink.root_path.resolve()
        raw_input_relpath = raw_input_path.resolve().relative_to(root_path).as_posix()
        raw_tools_relpath = (
            raw_tool_schemas_path.resolve().relative_to(root_path).as_posix()
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
    truncation = extract_truncation_hint(outcome.result.value)
    if truncation is None:
        return (None, None, None, None)
    return (
        truncation.scope_token,
        truncation.cursor,
        truncation.has_more,
        truncation.limit,
    )


__all__ = ["ProjectionSchemaError", "ToolTraceObserver"]
