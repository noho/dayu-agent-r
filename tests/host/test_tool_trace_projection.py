"""Host Tool Trace hot / cold projection 测试。"""

from __future__ import annotations

import json
import hashlib
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    append_event,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.payload import (
    SQLitePayloadFormat,
    SQLitePayloadWriteRequest,
    write_sqlite_payload,
)
from dayu.host.durable.projection import (
    read_projection_checkpoint,
    read_projection_failure,
)
from dayu.host.durable.schema import (
    TABLE_EVENT_LOG,
    TABLE_HOST_ATTEMPTS,
    TABLE_HOST_RUNS,
    TABLE_HOST_TOOL_TRACE_HOT,
    TOOL_CALL_ARGUMENTS_DESCRIPTOR_KIND,
    TOOL_CALL_ARGUMENTS_STORAGE_PAYLOAD_DESCRIPTOR,
    TOOL_CALL_SEMANTIC_QUERY_STORAGE_PAYLOAD_DESCRIPTOR,
)
from dayu.host.durable.tool_trace import (
    read_tool_trace_by_run,
    read_tool_trace_hot_row,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.evidence import (
    AcceptedEvidenceEnvelope,
    AcceptedEvidenceResultRef,
    AcceptedEvidenceToolQuery,
    OpaqueEvidenceRef,
    accepted_evidence_envelope_to_json_value,
)
from dayu.host.open_host import _default_tool_trace_cold_jsonl_path
from dayu.host.projection import ProjectionRunner
from dayu.host.projection import projection_event_view_from_row
from dayu.host.tool_trace import (
    TOOL_TRACE_CONSUMER_ID,
    ToolTraceProjectionConsumer,
    ToolTraceSinkOptions,
    _LOCK_TIMEOUT_SECONDS,
    _tool_trace_cold_lock_path,
    catch_up_tool_trace_projection,
)
from dayu.host.tool_call_request import (
    AcceptedToolCallRequestAtomInput,
    ToolCallRequestEventOrigin,
    build_tool_call_requested_event_request,
)

_FIXED_NOW = datetime(2026, 5, 29, 2, 3, 4, tzinfo=UTC)
_FIELD_CONTEXT_PRESSURE = "context_pressure"
_FIELD_TOOL_TIMING = "tool_timing"
_FIELD_FAILURE_METADATA = "failure_metadata"
_FIELD_PARTIAL_TOOL_CALL_SIGNAL = "partial_tool_call_signal"
_SIGNAL_FIELD_NAMES: tuple[str, ...] = (
    _FIELD_CONTEXT_PRESSURE,
    _FIELD_TOOL_TIMING,
    _FIELD_FAILURE_METADATA,
    _FIELD_PARTIAL_TOOL_CALL_SIGNAL,
)
_CONFIGURED_SECRET_SENTINEL = "synthetic-local-trust-sentinel-6f2b9d8c"


class _AcceptedTraceCorruption(StrEnum):
    """accepted result canonical request material 损坏分类。"""

    MISSING_ENVELOPE = "missing_envelope"
    MISSING_REQUEST_ROW = "missing_request_row"
    REQUEST_IDENTITY_MISMATCH = "request_identity_mismatch"
    ARGUMENTS_DIGEST_MISMATCH = "arguments_digest_mismatch"
    ARGUMENTS_DESCRIPTOR_WITH_INLINE = "arguments_descriptor_with_inline"
    SEMANTIC_QUERY_DESCRIPTOR_WITH_INLINE = (
        "semantic_query_descriptor_with_inline"
    )
    RESULT_EXECUTION_MISSING = "result_execution_missing"
    RESULT_EXECUTION_MISMATCH = "result_execution_mismatch"


class _RequestedRowCorruption(StrEnum):
    """direct TOOL_CALL_REQUESTED canonical row 损坏分类。"""

    MISSING_ROW = "missing_row"
    WRONG_EVENT_TYPE = "wrong_event_type"
    STORAGE_CONFLICT = "storage_conflict"
    DIGEST_MISMATCH = "digest_mismatch"


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试用 Host durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "host" / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(),
    )


def _append_tool_event(
    transaction_runner: HostTransactionRunner,
    *,
    event_id: str,
    event_type: str,
    payload: JsonValue,
    event_class: EventClass = EventClass.CANONICAL_FACT,
    payload_ref: str | None = None,
    payload_digest: str | None = None,
) -> EventLogRow:
    """追加 Tool Trace 测试 EventLog row。

    :param transaction_runner: Host durable transaction runner。
    :param event_id: EventLog id。
    :param event_type: EventLog type。
    :param payload: inline payload。
    :param event_class: EventLog class。
    :param payload_ref: 可选 payload descriptor ref。
    :param payload_digest: 可选 payload digest。
    :returns: 已追加 EventLog row。
    """

    return transaction_runner.run_write(
        lambda transaction: _append_tool_event_in_transaction(
            transaction,
            event_id=event_id,
            event_type=event_type,
            payload=payload,
            event_class=event_class,
            payload_ref=payload_ref,
            payload_digest=payload_digest,
        )
    )


def _append_tool_event_in_transaction(
    transaction: HostTransaction,
    *,
    event_id: str,
    event_type: str,
    payload: JsonValue,
    event_class: EventClass,
    payload_ref: str | None,
    payload_digest: str | None,
    execution_id: str | None = "execution-1",
) -> EventLogRow:
    """在单个 transaction 内追加 Tool Trace 测试 EventLog row。

    :param transaction: Host durable transaction。
    :param event_id: EventLog id。
    :param event_type: EventLog type。
    :param payload: inline payload。
    :param event_class: EventLog class。
    :param payload_ref: 可选 payload descriptor ref。
    :param payload_digest: 可选 payload digest。
    :param execution_id: EventLog execution id。
    :returns: 已追加 EventLog row。
    :raises HostDurableError: payload 或 EventLog durable 写入失败时抛出。
    """

    actual_payload_ref = payload_ref
    actual_payload_digest = payload_digest
    if payload_ref is not None:
        descriptor = write_sqlite_payload(
            transaction,
            SQLitePayloadWriteRequest(
                payload_ref=payload_ref,
                payload_id=f"{event_id}-payload",
                payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                payload_json={"event_id": event_id, "source": "event-log-payload"},
                media_type="application/json",
                metadata={"kind": "test"},
                expected_digest=payload_digest,
            ),
        )
        actual_payload_ref = descriptor.payload_ref
        actual_payload_digest = descriptor.payload_digest
    return append_event(
        transaction,
        EventLogAppendRequest(
            event_id=event_id,
            event_class=event_class,
            session_id="session-1",
            run_id="run-1",
            attempt_id="attempt-1",
            execution_id=execution_id,
            event_type=event_type,
            occurred_at=_FIXED_NOW,
            actor="host",
            source="unit-test",
            client_request_id=None,
            idempotency_key=None,
            policy_decision={"decision": "accepted"},
            reason={"reason": "test"},
            payload_json=payload,
            payload_ref=actual_payload_ref,
            payload_digest=actual_payload_digest,
        ),
    ).row


def _accepted_request_atom(
    *,
    event_id: str,
    tool_call_id: str,
    tool_name: str,
    run_id: str = "run-1",
) -> AcceptedToolCallRequestAtomInput:
    """构造 identity/digest 同源的 canonical request atom 输入。

    :param event_id: request event id，用于生成稳定测试参数。
    :param tool_call_id: tool call id。
    :param tool_name: 工具名。
    :param run_id: request row Run id。
    :returns: 可交给共享 request writer 的 accepted atom。
    :raises ValueError: 构造的 request atom 字段违反基础约束时抛出。
    """

    accepted_arguments: Mapping[str, JsonValue] = {"fixture": event_id}
    arguments_digest = sha256_digest_json({"arguments": accepted_arguments})
    semantic_input_digest = sha256_digest_json(
        {"semantic_input": f"trace fixture {event_id}"}
    )
    return AcceptedToolCallRequestAtomInput(
        session_id="session-1",
        run_id=run_id,
        attempt_id="attempt-1",
        execution_id="execution-1",
        iteration_id="iteration-1",
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        tool_schema_digest=sha256_digest_json({"tool_schema": tool_name}),
        tool_identity_digest=sha256_digest_json(
            {"tool_name": tool_name, "tool_call_id": tool_call_id}
        ),
        accepted_arguments=accepted_arguments,
        normalized_arguments_digest=arguments_digest,
        tool_fact_kind="completed",
        accept_idempotency_key=f"accept:{event_id}",
        semantic_input_digest=semantic_input_digest,
        semantic_query_text=f"查询 trace fixture {event_id}",
    )


def _append_canonical_tool_request_event(
    transaction_runner: HostTransactionRunner,
    *,
    event_id: str,
    tool_call_id: str,
    tool_name: str,
) -> EventLogRow:
    """通过共享 writer 追加 canonical ``TOOL_CALL_REQUESTED``。

    :param transaction_runner: Host durable transaction runner。
    :param event_id: request event id。
    :param tool_call_id: tool call id。
    :param tool_name: 工具名。
    :returns: 数据库返回的真实 request row。
    :raises ValueError: request atom 基础字段非法时抛出。
    :raises HostDurableError: request atom 或 EventLog 写入失败时抛出。
    """

    return transaction_runner.run_write(
        lambda transaction: append_event(
            transaction,
            build_tool_call_requested_event_request(
                transaction,
                atom=_accepted_request_atom(
                    event_id=event_id,
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                ),
                event_id=event_id,
                occurred_at=_FIXED_NOW,
                origin=ToolCallRequestEventOrigin.ORDINARY_ACCEPT,
            ),
        ).row
    )


def _append_accepted_tool_result_event(
    transaction_runner: HostTransactionRunner,
    *,
    event_id: str,
    tool_call_id: str,
    tool_name: str,
    additional_payload: Mapping[str, JsonValue],
    include_raw_outcome: bool = True,
) -> EventLogRow:
    """原子追加 canonical request 与 accepted result 成功夹具。

    :param transaction_runner: Host durable transaction runner。
    :param event_id: result event id。
    :param tool_call_id: tool call id。
    :param tool_name: 工具名。
    :param additional_payload: signal 等 result-owned 附加字段。
    :param include_raw_outcome: 是否写入 canonical raw outcome。
    :returns: 数据库返回的真实 result row。
    :raises ValueError: request/envelope 基础字段非法时抛出。
    :raises HostDurableError: request、envelope 或 EventLog 写入失败时抛出。
    """

    return transaction_runner.run_write(
        lambda transaction: _append_accepted_tool_result_in_transaction(
            transaction,
            event_id=event_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            additional_payload=additional_payload,
            include_raw_outcome=include_raw_outcome,
        )
    )


def _append_accepted_tool_result_in_transaction(
    transaction: HostTransaction,
    *,
    event_id: str,
    tool_call_id: str,
    tool_name: str,
    additional_payload: Mapping[str, JsonValue],
    include_raw_outcome: bool = True,
) -> EventLogRow:
    """在同一 transaction 内追加 canonical request/result pair。

    :param transaction: Host durable transaction。
    :param event_id: result event id。
    :param tool_call_id: tool call id。
    :param tool_name: 工具名。
    :param additional_payload: signal 等 result-owned 附加字段。
    :param include_raw_outcome: 是否写入 canonical raw outcome。
    :returns: 数据库返回的真实 result row。
    :raises ValueError: request/envelope 基础字段非法时抛出。
    :raises HostDurableError: request、envelope 或 EventLog 写入失败时抛出。
    """

    request_event_id = f"{event_id}-request"
    atom = _accepted_request_atom(
        event_id=request_event_id,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
    )
    request = append_event(
        transaction,
        build_tool_call_requested_event_request(
            transaction,
            atom=atom,
            event_id=request_event_id,
            occurred_at=_FIXED_NOW,
            origin=ToolCallRequestEventOrigin.ORDINARY_ACCEPT,
        ),
    ).row
    raw_tool_outcome: JsonValue = {
        "kind": "completed",
        "result": {"content": f"trace result {event_id}"},
    }
    envelope = AcceptedEvidenceEnvelope(
        evidence_id=f"evidence:{event_id}",
        producer_event_ref=event_id,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        tool_query=AcceptedEvidenceToolQuery(
            tool_call_requested_event_ref=request.event_id,
            normalized_arguments_digest=atom.normalized_arguments_digest,
            semantic_input_digest=atom.semantic_input_digest,
        ),
        result_ref=AcceptedEvidenceResultRef(
            payload_ref=None,
            payload_digest=None,
            outcome_digest=sha256_digest_json(raw_tool_outcome),
            truncation_applied=False,
        ),
        source_refs=(),
        locator_refs=(),
    )
    result_payload: dict[str, JsonValue] = dict(additional_payload)
    result_payload.update(
        {
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "normalized_arguments_digest": atom.normalized_arguments_digest,
            "semantic_input_digest": atom.semantic_input_digest,
            "outcome_digest": sha256_digest_json(raw_tool_outcome),
            "accepted_evidence_envelope": (
                accepted_evidence_envelope_to_json_value(envelope)
            ),
        }
    )
    if include_raw_outcome:
        result_payload["raw_tool_outcome"] = raw_tool_outcome
    return _append_tool_event_in_transaction(
        transaction,
        event_id=event_id,
        event_type="TOOL_RESULT_ACCEPTED",
        payload=result_payload,
        event_class=EventClass.CANONICAL_FACT,
        payload_ref=None,
        payload_digest=None,
    )


def _append_broken_accepted_tool_result_event(
    transaction_runner: HostTransactionRunner,
    *,
    event_id: str,
    corruption: _AcceptedTraceCorruption,
) -> EventLogRow:
    """追加 canonical request material 损坏的 accepted result。

    :param transaction_runner: Host durable transaction runner。
    :param event_id: result event id。
    :param corruption: envelope、request row、identity 或 digest 损坏分类。
    :returns: 数据库返回的真实 result row。
    :raises ValueError: corruption 或 envelope 基础字段非法时抛出。
    :raises HostDurableError: request、envelope 或 EventLog 写入失败时抛出。
    """

    return transaction_runner.run_write(
        lambda transaction: _append_broken_accepted_tool_result_in_transaction(
            transaction,
            event_id=event_id,
            corruption=corruption,
        )
    )


def _append_broken_accepted_tool_result_in_transaction(
    transaction: HostTransaction,
    *,
    event_id: str,
    corruption: _AcceptedTraceCorruption,
) -> EventLogRow:
    """在单个 transaction 内追加损坏 request/result fixture。

    :param transaction: Host durable transaction。
    :param event_id: result event id。
    :param corruption: envelope、request row、identity 或 digest 损坏分类。
    :returns: 数据库返回的真实 result row。
    :raises ValueError: corruption 或 envelope 基础字段非法时抛出。
    :raises HostDurableError: request、envelope 或 EventLog 写入失败时抛出。
    """

    tool_call_id = f"tool-call-{corruption.value}"
    tool_name = "lookup_filing"
    request_event_id = f"{event_id}-request"
    atom = _accepted_request_atom(
        event_id=request_event_id,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        run_id=(
            "run-other"
            if corruption is _AcceptedTraceCorruption.REQUEST_IDENTITY_MISMATCH
            else "run-1"
        ),
    )
    if corruption is _AcceptedTraceCorruption.ARGUMENTS_DESCRIPTOR_WITH_INLINE:
        descriptor_arguments: Mapping[str, JsonValue] = {
            "fixture": "x" * 70_000
        }
        atom = replace(
            atom,
            accepted_arguments=descriptor_arguments,
            normalized_arguments_digest=sha256_digest_json(
                {"arguments": descriptor_arguments}
            ),
        )
    elif (
        corruption
        is _AcceptedTraceCorruption.SEMANTIC_QUERY_DESCRIPTOR_WITH_INLINE
    ):
        atom = replace(atom, semantic_query_text="query " + ("x" * 70_000))
    if corruption is not _AcceptedTraceCorruption.MISSING_REQUEST_ROW:
        request_append = build_tool_call_requested_event_request(
            transaction,
            atom=atom,
            event_id=request_event_id,
            occurred_at=_FIXED_NOW,
            origin=ToolCallRequestEventOrigin.ORDINARY_ACCEPT,
        )
        if corruption in {
            _AcceptedTraceCorruption.ARGUMENTS_DESCRIPTOR_WITH_INLINE,
            _AcceptedTraceCorruption.SEMANTIC_QUERY_DESCRIPTOR_WITH_INLINE,
        }:
            assert isinstance(request_append.payload_json, Mapping)
            request_payload = dict(
                cast(Mapping[str, JsonValue], request_append.payload_json)
            )
            if (
                corruption
                is _AcceptedTraceCorruption.ARGUMENTS_DESCRIPTOR_WITH_INLINE
            ):
                assert request_payload["arguments_storage_kind"] == (
                    TOOL_CALL_ARGUMENTS_STORAGE_PAYLOAD_DESCRIPTOR
                )
                request_payload["arguments_inline_json"] = {
                    "arguments": {"fixture": "stale"}
                }
            else:
                assert request_payload["semantic_query_storage_kind"] == (
                    TOOL_CALL_SEMANTIC_QUERY_STORAGE_PAYLOAD_DESCRIPTOR
                )
                request_payload["semantic_query_text"] = "stale inline query"
            request_append = replace(request_append, payload_json=request_payload)
        request = append_event(
            transaction,
            request_append,
        ).row
        request_event_ref = request.event_id
    else:
        request_event_ref = request_event_id
    raw_tool_outcome: JsonValue = {
        "kind": "completed",
        "result": {"content": "must not be traced"},
    }
    payload: dict[str, JsonValue] = {
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "raw_tool_outcome": raw_tool_outcome,
    }
    if corruption is not _AcceptedTraceCorruption.MISSING_ENVELOPE:
        normalized_arguments_digest = atom.normalized_arguments_digest
        if corruption is _AcceptedTraceCorruption.ARGUMENTS_DIGEST_MISMATCH:
            normalized_arguments_digest = sha256_digest_json(
                {"arguments": {"fixture": "wrong"}}
            )
        envelope = AcceptedEvidenceEnvelope(
            evidence_id=f"evidence:{event_id}",
            producer_event_ref=event_id,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            tool_query=AcceptedEvidenceToolQuery(
                tool_call_requested_event_ref=request_event_ref,
                normalized_arguments_digest=normalized_arguments_digest,
                semantic_input_digest=atom.semantic_input_digest,
            ),
            result_ref=AcceptedEvidenceResultRef(
                payload_ref=None,
                payload_digest=None,
                outcome_digest=sha256_digest_json(raw_tool_outcome),
                truncation_applied=False,
            ),
            source_refs=(),
            locator_refs=(),
        )
        payload["accepted_evidence_envelope"] = (
            accepted_evidence_envelope_to_json_value(envelope)
        )
    result_execution_id: str | None = "execution-1"
    if corruption is _AcceptedTraceCorruption.RESULT_EXECUTION_MISSING:
        result_execution_id = None
    elif corruption is _AcceptedTraceCorruption.RESULT_EXECUTION_MISMATCH:
        result_execution_id = "execution-other"
    return _append_tool_event_in_transaction(
        transaction,
        event_id=event_id,
        event_type="TOOL_RESULT_ACCEPTED",
        payload=payload,
        event_class=EventClass.CANONICAL_FACT,
        payload_ref=None,
        payload_digest=None,
        execution_id=result_execution_id,
    )


def _append_corrupt_tool_request_event(
    transaction_runner: HostTransactionRunner,
    *,
    corruption: _RequestedRowCorruption,
) -> EventLogRow:
    """追加 direct Tool Trace request corruption fixture。

    :param transaction_runner: Host durable transaction runner。
    :param corruption: request row 损坏分类。
    :returns: 已持久化的 request-like row。
    :raises HostDurableError: EventLog 写入失败时抛出。
    """

    event_id = f"event-request-direct-{corruption.value}"

    def operation(transaction: HostTransaction) -> EventLogRow:
        """在单 transaction 中写入 request-like row。

        :param transaction: Host transaction。
        :returns: 已持久化 row。
        """

        request = build_tool_call_requested_event_request(
            transaction,
            atom=_accepted_request_atom(
                event_id=event_id,
                tool_call_id=f"tool-call-direct-{corruption.value}",
                tool_name="lookup_filing",
            ),
            event_id=event_id,
            occurred_at=_FIXED_NOW,
            origin=ToolCallRequestEventOrigin.ORDINARY_ACCEPT,
        )
        if corruption is _RequestedRowCorruption.WRONG_EVENT_TYPE:
            request = replace(request, event_type="TOOL_CALL_GOVERNED")
        elif corruption in {
            _RequestedRowCorruption.STORAGE_CONFLICT,
            _RequestedRowCorruption.DIGEST_MISMATCH,
        }:
            assert isinstance(request.payload_json, Mapping)
            payload = dict(cast(Mapping[str, JsonValue], request.payload_json))
            if corruption is _RequestedRowCorruption.STORAGE_CONFLICT:
                payload["arguments_storage_kind"] = (
                    TOOL_CALL_ARGUMENTS_STORAGE_PAYLOAD_DESCRIPTOR
                )
            else:
                payload["normalized_arguments_digest"] = sha256_digest_json(
                    {"arguments": {"fixture": "corrupt"}}
                )
            request = replace(request, payload_json=payload)
        return append_event(transaction, request).row

    return transaction_runner.run_write(operation)


def _run_trace_once(
    transaction_runner: HostTransactionRunner,
    cold_jsonl_path: Path,
    *,
    limit: int = 10,
    lock_path: Path | None = None,
) -> None:
    """运行一次 Tool Trace projection。

    :param transaction_runner: Host durable transaction runner。
    :param cold_jsonl_path: cold JSONL 路径。
    :param limit: ProjectionRunner 单次扫描上限。
    :param lock_path: 显式 runtime file lock 路径；``None`` 时使用默认派生路径。
    :returns: ``None``。
    """

    ProjectionRunner(
        transaction_runner,
        (
            ToolTraceProjectionConsumer(
                ToolTraceSinkOptions(
                    cold_jsonl_path=cold_jsonl_path,
                    create_parent_dirs=True,
                    lock_path=lock_path,
                )
            ),
        ),
    ).run_once(TOOL_TRACE_CONSUMER_ID, limit=limit)


def _json_lines(path: Path) -> tuple[Mapping[str, JsonValue], ...]:
    """读取 JSONL 文件为 JSON object 元组。

    :param path: JSONL 文件路径。
    :returns: JSON object 元组。
    :raises AssertionError: 行不是 JSON object 时抛出。
    """

    if not path.exists():
        return ()
    rows: list[Mapping[str, JsonValue]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = cast(JsonValue, json.loads(line))
        assert isinstance(value, Mapping)
        rows.append(cast(Mapping[str, JsonValue], value))
    return tuple(rows)


def _table_count(
    transaction_runner: HostTransactionRunner, table_name: str
) -> int:
    """读取表 row 数。

    :param transaction_runner: Host durable transaction runner。
    :param table_name: 目标表名。
    :returns: row 数。
    :raises AssertionError: SQLite 返回值不是整数时抛出。
    """

    row = transaction_runner.run_read(
        lambda transaction: transaction.fetchone(
            f"SELECT count(*) AS n FROM {table_name}"
        )
    )
    assert row is not None
    value = row.get("n")
    assert isinstance(value, int)
    return value


def _reset_tool_trace_projection(transaction_runner: HostTransactionRunner) -> None:
    """清理 Tool Trace projection rows 与 checkpoint 以模拟 rebuild。

    :param transaction_runner: Host durable transaction runner。
    :returns: ``None``。
    """

    transaction_runner.run_write(
        lambda transaction: (
            transaction.execute(f"DELETE FROM {TABLE_HOST_TOOL_TRACE_HOT}"),
            transaction.execute(
                "DELETE FROM host_projection_checkpoints WHERE consumer_id = ?",
                (TOOL_TRACE_CONSUMER_ID.value,),
            ),
            transaction.execute(
                "DELETE FROM host_projection_failures WHERE consumer_id = ?",
                (TOOL_TRACE_CONSUMER_ID.value,),
            ),
        )
    )


def _cold_trace_summary(
    cold_lines: tuple[Mapping[str, JsonValue], ...], index: int
) -> Mapping[str, JsonValue]:
    """读取 cold JSONL 指定行的 trace_summary object。

    :param cold_lines: 已解析的 cold JSONL 行。
    :param index: 目标行序号。
    :returns: trace_summary JSON object。
    :raises AssertionError: 指定字段不是 JSON object 时抛出。
    """

    summary = cold_lines[index]["trace_summary"]
    assert isinstance(summary, Mapping)
    return cast(Mapping[str, JsonValue], summary)


def _cold_trace_summary_for_event(
    cold_lines: tuple[Mapping[str, JsonValue], ...],
    *,
    event_id: str,
) -> Mapping[str, JsonValue]:
    """按 event id 读取 cold JSONL 的 trace summary。

    :param cold_lines: 已解析的 cold JSONL 行。
    :param event_id: 目标 EventLog id。
    :returns: 对应 cold line 的 trace summary。
    :raises AssertionError: event 不存在或 summary 不是 JSON object 时抛出。
    """

    matching = tuple(line for line in cold_lines if line["event_id"] == event_id)
    assert len(matching) == 1
    summary = matching[0]["trace_summary"]
    assert isinstance(summary, Mapping)
    return cast(Mapping[str, JsonValue], summary)


def test_tool_trace_excludes_internal_effective_execution_value(
    tmp_path: Path,
) -> None:
    """Tool Trace filter、hot、cold 与 query 均不投影 Host 内部执行配置值。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: Tool Trace 任一投影面包含 synthetic sentinel 时抛出。
    """

    cold_path = tmp_path / "trace" / "internal-config.jsonl"
    with open_host_durable_store(_options(tmp_path)) as store:
        row = _append_tool_event(
            store.transaction_runner,
            event_id="event-user-input-internal-config",
            event_type="USER_INPUT_ACCEPTED",
            payload={
                "display_text": "分析本期经营情况",
                "effective_execution_config": {
                    "config": {
                        "runner_spec": {
                            "headers": {
                                "X-Synthetic-Execution-Value": (
                                    _CONFIGURED_SECRET_SENTINEL
                                )
                            }
                        }
                    }
                },
            },
        )
        run_id = row.run_id
        assert isinstance(run_id, str)
        consumer = ToolTraceProjectionConsumer(
            ToolTraceSinkOptions(
                cold_jsonl_path=cold_path,
                create_parent_dirs=True,
            )
        )

        assert not consumer.event_filter.matches(
            projection_event_view_from_row(row)
        )
        _run_trace_once(store.transaction_runner, cold_path)

        hot_row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(
                transaction, row.event_id
            )
        )
        query_page = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_by_run(
                transaction,
                run_id,
                after_event_sequence=0,
                limit=10,
            )
        )

        assert hot_row is None
        assert query_page.rows == ()
        assert _CONFIGURED_SECRET_SENTINEL not in repr(query_page)

    assert _json_lines(cold_path) == ()


@pytest.mark.parametrize(
    "corruption",
    tuple(_AcceptedTraceCorruption),
)
def test_tool_trace_request_corruption_records_failure_without_result_trace(
    tmp_path: Path,
    corruption: _AcceptedTraceCorruption,
) -> None:
    """canonical request material 损坏时记录 HostDurableError 且不发布结果 trace。

    :param tmp_path: pytest 临时目录。
    :param corruption: envelope、request row、identity、storage 或 digest 损坏分类。
    :returns: ``None``。
    :raises AssertionError: result trace 被发布或 failure 类型不是 HostDurableError 时抛出。
    """

    cold_path = tmp_path / "trace" / "request-corruption.jsonl"
    result_event_id = f"event-result-{corruption.value}"
    with open_host_durable_store(_options(tmp_path)) as store:
        result_event = _append_broken_accepted_tool_result_event(
            store.transaction_runner,
            event_id=result_event_id,
            corruption=corruption,
        )
        consumer = ToolTraceProjectionConsumer(
            ToolTraceSinkOptions(
                cold_jsonl_path=cold_path,
                create_parent_dirs=True,
            )
        )
        projection_result = ProjectionRunner(
            store.transaction_runner,
            (consumer,),
        ).run_once(TOOL_TRACE_CONSUMER_ID, limit=10)
        failure = store.transaction_runner.run_read(
            lambda transaction: read_projection_failure(
                transaction,
                TOOL_TRACE_CONSUMER_ID.value,
            )
        )
        hot_row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(
                transaction,
                result_event.event_id,
            )
        )
        checkpoint = store.transaction_runner.run_read(
            lambda transaction: read_projection_checkpoint(
                transaction,
                TOOL_TRACE_CONSUMER_ID.value,
            )
        )

        assert projection_result.failures == 1
        assert hot_row is None
        assert failure is not None
        expected_failed_event_id = (
            f"{result_event.event_id}-request"
            if corruption
            in {
                _AcceptedTraceCorruption.ARGUMENTS_DESCRIPTOR_WITH_INLINE,
                _AcceptedTraceCorruption.SEMANTIC_QUERY_DESCRIPTOR_WITH_INLINE,
            }
            else result_event.event_id
        )
        assert failure.failed_event_id == expected_failed_event_id
        assert failure.last_error_code == HostDurableError.__name__
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence < result_event.event_sequence
        cold_event_ids = (
            tuple(line["event_id"] for line in _json_lines(cold_path))
            if cold_path.exists()
            else ()
        )
        assert result_event.event_id not in cold_event_ids


@pytest.mark.parametrize("corruption", tuple(_RequestedRowCorruption))
def test_tool_trace_direct_request_row_corruption_fails_closed(
    tmp_path: Path,
    corruption: _RequestedRowCorruption,
) -> None:
    """direct request missing/type/storage/digest corruption 均 fail closed。

    :param tmp_path: pytest 临时目录。
    :param corruption: direct request row 损坏分类。
    :returns: ``None``。
    :raises AssertionError: Tool Trace 发布 limited/placeholder summary 时抛出。
    """

    cold_path = tmp_path / "trace" / "direct-request-corruption.jsonl"
    with open_host_durable_store(_options(tmp_path)) as store:
        row = _append_corrupt_tool_request_event(
            store.transaction_runner,
            corruption=corruption,
        )
        event = projection_event_view_from_row(row)
        if corruption is _RequestedRowCorruption.WRONG_EVENT_TYPE:
            event = replace(event, event_type="TOOL_CALL_REQUESTED")
        if corruption is _RequestedRowCorruption.MISSING_ROW:
            store.transaction_runner.run_write(
                lambda transaction: transaction.execute(
                    f"DELETE FROM {TABLE_EVENT_LOG} WHERE event_id = ?",
                    (row.event_id,),
                )
            )
        consumer = ToolTraceProjectionConsumer(
            ToolTraceSinkOptions(cold_jsonl_path=cold_path)
        )

        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(
                lambda transaction: consumer.apply_event(transaction, event)
            )
        hot_row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(
                transaction,
                row.event_id,
            )
        )
        assert hot_row is None

    assert _json_lines(cold_path) == ()


def test_tool_trace_canonical_result_without_llm_material_fails_closed(
    tmp_path: Path,
) -> None:
    """LLM-ready Tool Trace 拒绝缺 typed material 的 canonical result。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: Tool Trace 生成 fallback/limited result summary 时抛出。
    """

    cold_path = tmp_path / "trace" / "missing-llm-material.jsonl"
    with open_host_durable_store(_options(tmp_path)) as store:
        result = _append_accepted_tool_result_event(
            store.transaction_runner,
            event_id="event-result-missing-llm-material",
            tool_call_id="tool-call-missing-llm-material",
            tool_name="lookup_filing",
            additional_payload={},
            include_raw_outcome=False,
        )
        consumer = ToolTraceProjectionConsumer(
            ToolTraceSinkOptions(cold_jsonl_path=cold_path)
        )

        with pytest.raises(
            HostDurableError,
            match="TOOL_RESULT_ACCEPTED tool trace LLM material is missing",
        ):
            store.transaction_runner.run_write(
                lambda transaction: consumer.apply_event(
                    transaction,
                    projection_event_view_from_row(result),
                )
            )
        hot_row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(
                transaction,
                result.event_id,
            )
        )
        assert hot_row is None

    assert _json_lines(cold_path) == ()


def test_tool_call_chain_projects_hot_rows_and_cold_lines(tmp_path: Path) -> None:
    """TOOL_CALL_REQUESTED / GOVERNED / RESULT_ACCEPTED 投影关键字段。"""

    cold_path = tmp_path / "trace" / "cold.jsonl"
    lock_path = tmp_path / "locks" / "tool-trace-cold.jsonl.lock"
    request_event_id = "event-requested"
    result_event_id = "event-result"
    arguments_json: Mapping[str, JsonValue] = {
        "arguments": {
            "ticker": "AAPL",
            "filing_type": "10-K",
        }
    }
    arguments_digest = sha256_digest_json(arguments_json)
    semantic_query_text = '工具 lookup_filing 请求参数：{"ticker":"AAPL","filing_type":"10-K"}'
    semantic_query_digest = sha256_digest_json(
        {"semantic_query_text": semantic_query_text}
    )
    outcome_digest = sha256_digest_json({"result": "filing found"})
    envelope = AcceptedEvidenceEnvelope(
        evidence_id=f"evidence:{result_event_id}",
        producer_event_ref=result_event_id,
        tool_name="lookup_filing",
        tool_call_id="tool-call-1",
        tool_query=AcceptedEvidenceToolQuery(
            tool_call_requested_event_ref=request_event_id,
            normalized_arguments_digest=arguments_digest,
            semantic_input_digest=semantic_query_digest,
        ),
        result_ref=AcceptedEvidenceResultRef(
            payload_ref=None,
            payload_digest=None,
            outcome_digest=outcome_digest,
            truncation_applied=False,
        ),
        source_refs=(
            OpaqueEvidenceRef(
                ref_kind="payload",
                ref_id="payload-source-internal",
                digest=None,
            ),
        ),
        locator_refs=(),
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        requested = _append_tool_event(
            store.transaction_runner,
            event_id=request_event_id,
            event_type="TOOL_CALL_REQUESTED",
            payload={
                "tool_call_id": "tool-call-1",
                "tool_name": "lookup_filing",
                "tool_schema_digest": "sha256:schema",
                "tool_identity_digest": "sha256:identity",
                "normalized_arguments_digest": arguments_digest,
                "arguments_json_size_bytes": len(
                    canonical_json_dumps(arguments_json).encode("utf-8")
                ),
                "arguments_storage_kind": "inline_json",
                "arguments_inline_json": arguments_json,
                "arguments_payload_ref": None,
                "arguments_payload_digest": arguments_digest,
                "semantic_input_digest": semantic_query_digest,
                "semantic_query_storage_kind": "inline_text",
                "semantic_query_text": semantic_query_text,
                "semantic_query_payload_ref": None,
                "semantic_query_digest": semantic_query_digest,
            },
        )
        governed = _append_tool_event(
            store.transaction_runner,
            event_id="event-governed",
            event_type="TOOL_CALL_GOVERNED",
            payload={
                "tool_call_id": "tool-call-1",
                "tool_name": "lookup_filing",
                "duplicate_key": "dup-key",
                "duplicate_decision": "reuse",
                "duplicate_scope": {
                    "kind": "attempt",
                    "attempt_id": "attempt-trace",
                },
                "reuse_prior_event_refs": [
                    {"event_id": "event-old", "event_sequence": 1}
                ],
                "diagnostic_refs": [{"ref_id": "diag-duplicate"}],
            },
        )
        result = _append_tool_event(
            store.transaction_runner,
            event_id=result_event_id,
            event_type="TOOL_RESULT_ACCEPTED",
            payload={
                "tool_call_id": "tool-call-1",
                "tool_name": "lookup_filing",
                "normalized_arguments_digest": arguments_digest,
                "semantic_input_digest": semantic_query_digest,
                "resolution_kind": "completed",
                "tool_fact_kind": "completed",
                "outcome_digest": outcome_digest,
                "payload_ref": {
                    "payload_ref": "artifact://tool-result",
                    "payload_digest": (
                        "sha256:"
                        "1111111111111111111111111111111111111111111111111111111111111111"
                    ),
                },
                "diagnostic_refs": [{"ref_id": "diag-result"}],
                "operation_context": {
                    "operation_name": "analyze_filing",
                    "business_domain": "financial_report",
                    "business_object_id": "AAPL-10K-2025",
                },
                "accepted_evidence_envelope": (
                    accepted_evidence_envelope_to_json_value(envelope)
                ),
                "raw_tool_outcome": {
                    "kind": "completed",
                    "result": {
                        "ok": True,
                        "value": {
                            "details": [
                                {"label": "ticker", "value": "AAPL"},
                                {"label": "filing", "value": "10-K"},
                                {"label": "status", "value": "found"},
                            ],
                            "document_id": "aapl-10k-2025",
                        },
                    },
                },
                "raw_result": {
                    "unbounded_text": "raw payload must stay in EventLog only"
                },
            },
            payload_ref="artifact://event-log-payload",
        )

        _run_trace_once(store.transaction_runner, cold_path, lock_path=lock_path)
        requested_row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(
                transaction, requested.event_id
            )
        )
        governed_row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(
                transaction, governed.event_id
            )
        )
        result_row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(transaction, result.event_id)
        )
        checkpoint = store.transaction_runner.run_read(
            lambda transaction: read_projection_checkpoint(
                transaction, TOOL_TRACE_CONSUMER_ID.value
            )
        )

        assert requested_row is not None
        assert requested_row.tool_call_id == "tool-call-1"
        assert requested_row.tool_name == "lookup_filing"
        assert requested_row.normalized_arguments_digest == arguments_digest
        assert requested_row.semantic_input_digest == semantic_query_digest
        requested_summary = requested_row.trace_summary["tool_request"]
        assert isinstance(requested_summary, Mapping)
        assert requested_summary["query_text"] == semantic_query_text
        assert "ticker=AAPL" in str(requested_summary["arguments_summary_text"])
        assert governed_row is not None
        assert governed_row.diagnostic_ref == "diag-duplicate"
        assert governed_row.trace_summary["duplicate_decision"] == "reuse"
        assert governed_row.trace_summary["duplicate_scope"] == {
            "kind": "attempt",
            "attempt_id": "attempt-trace",
        }
        assert result_row is not None
        assert result_row.result_digest == outcome_digest
        assert result_row.diagnostic_ref == "diag-result"
        result_request = result_row.trace_summary["tool_request"]
        result_summary = result_row.trace_summary["tool_result"]
        assert isinstance(result_request, Mapping)
        assert isinstance(result_summary, Mapping)
        assert "ticker=AAPL" in str(result_request["arguments_summary_text"])
        assert result_summary["result_status"] == "completed"
        assert "ticker=AAPL" in str(result_summary["result_details"])
        assert "filing=10-K" in str(result_summary["result_details"])
        assert "ticker=AAPL" in str(result_summary["result_summary_text"])
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == result.event_sequence
        assert lock_path.exists()
        cold_lines = _json_lines(cold_path)
        assert [line["event_id"] for line in cold_lines] == [
            "event-requested",
            "event-governed",
            "event-result",
        ]
        result_line = cold_lines[2]
        assert "payload" not in result_line
        assert "raw_result" not in json.dumps(result_line, sort_keys=True)
        assert result_line["payload_ref"] == "artifact://tool-result"
        assert result_line["payload_digest"] == (
            "sha256:"
            "1111111111111111111111111111111111111111111111111111111111111111"
        )
        assert result_line["source_payload_ref"] == "artifact://event-log-payload"
        assert result_line["source_payload_digest"] == result.payload_digest
        assert result_line["diagnostic_refs"] == ["diag-result"]
        assert result_line["operation_context_refs"] == [
            "analyze_filing",
            "financial_report",
            "AAPL-10K-2025",
        ]
        assert isinstance(result_line["operation_context_digest"], str)
        assert result_line["trace_summary"] == result_row.trace_summary
        assert result_line["cold_trace_ref"] == "tool-trace-cold:event-result"
        assert result_line["cold_trace_digest"] == result_line["line_digest"]
        governed_line = cold_lines[1]
        governed_summary = governed_line["trace_summary"]
        assert isinstance(governed_summary, Mapping)
        assert governed_summary["duplicate_scope"] == {
            "kind": "attempt",
            "attempt_id": "attempt-trace",
        }


def test_wait_resolution_tool_trace_summarizes_request_and_result_details(
    tmp_path: Path,
) -> None:
    """wait-resolution tool trace 应自解释工具请求与结果 details。"""

    cold_path = tmp_path / "trace" / "wait-resolution.jsonl"
    arguments_json: Mapping[str, JsonValue] = {
        "arguments": {
            "file_path": "reports/ATAT/annual-report.pdf",
            "password_policy_name": "research-read-policy",
            "scope_token": "scope-atat-visible",
            "ticker": "ATAT",
            "source": "auto",
        }
    }
    arguments_digest = sha256_digest_json(arguments_json)
    semantic_query_text = '工具 start_fins_download 请求参数：{"ticker":"ATAT","source":"auto"}'
    semantic_query_digest = sha256_digest_json(
        {"semantic_query_text": semantic_query_text}
    )
    result_event_id = "event-tool-result-wait-resolution-atat"
    request_event_id = "event-tool-call-requested-atat"
    envelope = AcceptedEvidenceEnvelope(
        evidence_id=f"evidence:{result_event_id}",
        producer_event_ref=result_event_id,
        tool_name="start_fins_download",
        tool_call_id="tool-call-atat",
        tool_query=AcceptedEvidenceToolQuery(
            tool_call_requested_event_ref=request_event_id,
            normalized_arguments_digest=arguments_digest,
            semantic_input_digest=semantic_query_digest,
        ),
        result_ref=AcceptedEvidenceResultRef(
            payload_ref=None,
            payload_digest=None,
            outcome_digest=sha256_digest_json({"result": "atat"}),
            truncation_applied=False,
        ),
        source_refs=(
            OpaqueEvidenceRef(
                ref_kind="payload",
                ref_id="payload-source-internal",
                digest=None,
            ),
        ),
        locator_refs=(),
    )
    raw_outcome: JsonValue = {
        "kind": "completed",
        "result": {
            "ok": True,
            "value": {
                "details": [
                    {"label": "discovered", "value": "27"},
                    {"label": "downloaded", "value": "12"},
                    {"label": "skipped", "value": "0"},
                    {"label": "rejected", "value": "15"},
                    {"label": "failed", "value": "0"},
                    {"label": "written documents", "value": "12"},
                ],
                "written": 12,
            },
        },
    }
    with open_host_durable_store(_options(tmp_path)) as store:
        _append_tool_event(
            store.transaction_runner,
            event_id=request_event_id,
            event_type="TOOL_CALL_REQUESTED",
            payload={
                "tool_call_id": "tool-call-atat",
                "tool_name": "start_fins_download",
                "tool_schema_digest": "sha256:schema",
                "tool_identity_digest": "sha256:identity",
                "normalized_arguments_digest": arguments_digest,
                "arguments_json_size_bytes": len(
                    canonical_json_dumps(arguments_json).encode("utf-8")
                ),
                "arguments_storage_kind": "inline_json",
                "arguments_inline_json": arguments_json,
                "arguments_payload_ref": None,
                "arguments_payload_digest": arguments_digest,
                "semantic_input_digest": semantic_query_digest,
                "semantic_query_storage_kind": "inline_text",
                "semantic_query_text": semantic_query_text,
                "semantic_query_payload_ref": None,
                "semantic_query_digest": semantic_query_digest,
            },
        )
        _append_tool_event(
            store.transaction_runner,
            event_id=result_event_id,
            event_type="TOOL_RESULT_ACCEPTED",
            payload={
                "wait_id": "wait-atat-should-not-project",
                "tool_call_id": "tool-call-atat",
                "tool_name": "start_fins_download",
                "normalized_arguments_digest": arguments_digest,
                "semantic_input_digest": semantic_query_digest,
                "resolution_kind": "completed",
                "tool_fact_kind": "completed",
                "outcome_digest": sha256_digest_json({"result": "atat"}),
                "accepted_evidence_envelope": (
                    accepted_evidence_envelope_to_json_value(envelope)
                ),
                "raw_tool_outcome": raw_outcome,
            },
        )

        _run_trace_once(store.transaction_runner, cold_path)
        request_row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(transaction, request_event_id)
        )
        result_row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(transaction, result_event_id)
        )
        cold_lines = _json_lines(cold_path)

        assert request_row is not None
        request_summary = request_row.trace_summary["tool_request"]
        assert isinstance(request_summary, Mapping)
        assert request_summary["tool_name"] == "start_fins_download"
        assert request_summary["query_text"] == semantic_query_text
        assert "ticker=ATAT" in str(request_summary["arguments_summary_text"])
        assert request_summary["arguments"] == arguments_json["arguments"]
        assert "file_path=reports/ATAT/annual-report.pdf" in str(
            request_summary["arguments_summary_text"]
        )
        assert "password_policy_name=research-read-policy" in str(
            request_summary["arguments_summary_text"]
        )
        assert "scope_token=scope-atat-visible" in str(
            request_summary["arguments_summary_text"]
        )
        assert "<redacted>" not in json.dumps(request_summary, ensure_ascii=False)
        assert result_row is not None
        result_request = result_row.trace_summary["tool_request"]
        result_summary = result_row.trace_summary["tool_result"]
        assert isinstance(result_request, Mapping)
        assert isinstance(result_summary, Mapping)
        assert result_request["tool_name"] == "start_fins_download"
        assert "ticker=ATAT" in str(result_request["arguments_summary_text"])
        assert result_request["arguments"] == arguments_json["arguments"]
        assert result_summary["result_status"] == "completed"
        assert "discovered=27" in str(result_summary["result_details"])
        assert "downloaded=12" in str(result_summary["result_details"])
        assert "downloaded=12" in str(result_summary["result_summary_text"])
        cold_text = json.dumps(cold_lines, ensure_ascii=False, sort_keys=True)
        assert "ticker=ATAT" in cold_text
        assert "reports/ATAT/annual-report.pdf" in cold_text
        assert "research-read-policy" in cold_text
        assert "scope-atat-visible" in cold_text
        assert "discovered=27" in cold_text
        assert "wait-atat-should-not-project" not in cold_text
        assert "payload-source-internal" not in cold_text
        assert "observation handle" not in cold_text
        assert "runtime" not in cold_text


def test_tool_trace_copies_optional_summary_signal_objects(
    tmp_path: Path,
) -> None:
    """Tool Trace 将已存在的四类 signal object 复制进 hot/cold summary。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: canonical result 未投影 signal 或 hot/cold 不一致时抛出。
    """

    cold_path = tmp_path / "trace" / "signals.jsonl"
    context_pressure: Mapping[str, JsonValue] = {
        "schema_version": 1,
        "signal_source": "USAGE_REPORTED",
        "status": "observed",
    }
    tool_timing: Mapping[str, JsonValue] = {
        "schema_version": 1,
        "status": "available",
        "started_at": "2026-06-11T00:00:00+00:00",
        "finished_at": "2026-06-11T00:00:01.250000+00:00",
        "duration_ms": 1250,
        "duration_source": "tool_result_meta",
    }
    failure_metadata: Mapping[str, JsonValue] = {
        "schema_version": 1,
        "signal_source": "TOOL_RESULT_ACCEPTED",
        "failure_kind": "tool_failed",
        "error_code": "lookup_failed",
        "repair_hint": "retry lookup",
        "repair_hint_truncated": False,
        "repair_hint_sha256": _text_sha256("retry lookup"),
        "diagnostic_refs": ["diag-result"],
    }
    partial_tool_call_signal: Mapping[str, JsonValue] = {
        "schema_version": 1,
        "signal_source": "PROVIDER_PROTOCOL_ERROR",
        "partial_tool_call_count": 0,
        "summary_status": "none",
        "raw_payload_present": False,
        "partial_tool_calls": [],
    }
    with open_host_durable_store(_options(tmp_path)) as store:
        event = _append_accepted_tool_result_event(
            store.transaction_runner,
            event_id="event-signals",
            tool_call_id="tool-call-signals",
            tool_name="lookup_filing",
            additional_payload={
                _FIELD_CONTEXT_PRESSURE: context_pressure,
                _FIELD_TOOL_TIMING: tool_timing,
                _FIELD_FAILURE_METADATA: failure_metadata,
                _FIELD_PARTIAL_TOOL_CALL_SIGNAL: partial_tool_call_signal,
            },
        )

        _run_trace_once(store.transaction_runner, cold_path)
        row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(transaction, event.event_id)
        )
        cold_lines = _json_lines(cold_path)

        assert row is not None
        assert row.trace_summary[_FIELD_CONTEXT_PRESSURE] == context_pressure
        assert row.trace_summary[_FIELD_TOOL_TIMING] == tool_timing
        assert row.trace_summary[_FIELD_FAILURE_METADATA] == failure_metadata
        assert (
            row.trace_summary[_FIELD_PARTIAL_TOOL_CALL_SIGNAL]
            == partial_tool_call_signal
        )
        assert _cold_trace_summary_for_event(
            cold_lines,
            event_id=event.event_id,
        ) == row.trace_summary


def test_tool_trace_projects_tool_timing_available_and_missing_signals(
    tmp_path: Path,
) -> None:
    """TOOL_RESULT_ACCEPTED 的 tool_timing 同步进入 hot / cold summary。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: available/missing timing 未按原 object 投影时抛出。
    """

    cold_path = tmp_path / "trace" / "tool-timing.jsonl"
    available_timing: Mapping[str, JsonValue] = {
        "schema_version": 1,
        "status": "available",
        "started_at": "2026-06-11T00:00:00+00:00",
        "finished_at": "2026-06-11T00:00:01.250000+00:00",
        "duration_ms": 1250,
        "duration_source": "tool_result_meta",
    }
    missing_timing: Mapping[str, JsonValue] = {
        "schema_version": 1,
        "status": "missing_tool_result_meta",
        "started_at": None,
        "finished_at": None,
        "duration_ms": None,
        "duration_source": None,
    }
    with open_host_durable_store(_options(tmp_path)) as store:
        available = _append_accepted_tool_result_event(
            store.transaction_runner,
            event_id="event-tool-timing-available",
            tool_call_id="tool-call-duration",
            tool_name="lookup_filing",
            additional_payload={
                _FIELD_TOOL_TIMING: available_timing,
            },
        )
        missing = _append_accepted_tool_result_event(
            store.transaction_runner,
            event_id="event-tool-timing-missing",
            tool_call_id="tool-call-missing-meta",
            tool_name="lookup_filing",
            additional_payload={
                _FIELD_TOOL_TIMING: missing_timing,
            },
        )

        _run_trace_once(store.transaction_runner, cold_path)
        available_row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(
                transaction, available.event_id
            )
        )
        missing_row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(transaction, missing.event_id)
        )
        cold_lines = _json_lines(cold_path)

        assert available_row is not None
        assert missing_row is not None
        assert available_row.trace_summary[_FIELD_TOOL_TIMING] == available_timing
        assert missing_row.trace_summary[_FIELD_TOOL_TIMING] == missing_timing
        assert _cold_trace_summary_for_event(
            cold_lines,
            event_id=available.event_id,
        )[_FIELD_TOOL_TIMING] == available_timing
        assert _cold_trace_summary_for_event(
            cold_lines,
            event_id=missing.event_id,
        )[_FIELD_TOOL_TIMING] == missing_timing


def test_tool_trace_projects_failure_metadata_variants(tmp_path: Path) -> None:
    """Tool Trace 投影 tool failure / cancel / policy block 失败元数据。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 任一 accepted result 的 failure metadata 丢失时抛出。
    """

    cold_path = tmp_path / "trace" / "failure-metadata.jsonl"
    failed_metadata: Mapping[str, JsonValue] = {
        "schema_version": 1,
        "signal_source": "TOOL_RESULT_ACCEPTED",
        "failure_kind": "tool_failed",
        "error_code": "lookup_failed",
        "repair_hint": None,
        "repair_hint_truncated": False,
        "repair_hint_sha256": None,
        "diagnostic_refs": ["diag-failed"],
    }
    cancelled_metadata: Mapping[str, JsonValue] = {
        "schema_version": 1,
        "signal_source": "TOOL_RESULT_ACCEPTED",
        "failure_kind": "tool_cancelled",
        "cancel_reason": "host_cancelled",
        "cancel_message": None,
        "cancel_message_truncated": False,
        "cancel_message_sha256": None,
        "cancel_hint": "retry later",
        "cancel_hint_truncated": False,
        "cancel_hint_sha256": _text_sha256("retry later"),
        "diagnostic_refs": ["diag-cancelled"],
    }
    policy_metadata: Mapping[str, JsonValue] = {
        "schema_version": 1,
        "signal_source": "TOOL_RESULT_ACCEPTED",
        "failure_kind": "policy_blocked",
        "policy_decision_kind": "governed_error",
        "policy_block_reason": "tool_idempotency_key_required",
        "diagnostic_refs": ["diag-policy"],
    }
    with open_host_durable_store(_options(tmp_path)) as store:
        failed = _append_accepted_tool_result_event(
            store.transaction_runner,
            event_id="event-tool-failed-metadata",
            tool_call_id="tool-call-failed",
            tool_name="lookup_filing",
            additional_payload={
                _FIELD_FAILURE_METADATA: failed_metadata,
            },
        )
        cancelled = _append_accepted_tool_result_event(
            store.transaction_runner,
            event_id="event-tool-cancelled-metadata",
            tool_call_id="tool-call-cancelled",
            tool_name="lookup_filing",
            additional_payload={
                _FIELD_FAILURE_METADATA: cancelled_metadata,
            },
        )
        policy = _append_accepted_tool_result_event(
            store.transaction_runner,
            event_id="event-tool-policy-metadata",
            tool_call_id="tool-call-policy",
            tool_name="lookup_filing",
            additional_payload={
                _FIELD_FAILURE_METADATA: policy_metadata,
            },
        )

        _run_trace_once(store.transaction_runner, cold_path)
        failed_row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(transaction, failed.event_id)
        )
        cancelled_row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(
                transaction, cancelled.event_id
            )
        )
        policy_row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(transaction, policy.event_id)
        )
        cold_lines = _json_lines(cold_path)

        assert failed_row is not None
        assert cancelled_row is not None
        assert policy_row is not None
        assert failed_row.trace_summary[_FIELD_FAILURE_METADATA] == failed_metadata
        assert (
            cancelled_row.trace_summary[_FIELD_FAILURE_METADATA]
            == cancelled_metadata
        )
        cancelled_summary = cancelled_row.trace_summary[_FIELD_FAILURE_METADATA]
        assert isinstance(cancelled_summary, Mapping)
        assert cancelled_summary["failure_kind"] != "tool_failed"
        assert policy_row.trace_summary[_FIELD_FAILURE_METADATA] == policy_metadata
        assert _cold_trace_summary_for_event(
            cold_lines,
            event_id=failed.event_id,
        ) == failed_row.trace_summary
        assert _cold_trace_summary_for_event(
            cold_lines,
            event_id=cancelled.event_id,
        ) == cancelled_row.trace_summary
        assert _cold_trace_summary_for_event(
            cold_lines,
            event_id=policy.event_id,
        ) == policy_row.trace_summary


def test_tool_trace_projects_provider_protocol_failure_metadata(
    tmp_path: Path,
) -> None:
    """PROVIDER_PROTOCOL_ERROR 的 failure_metadata 同步进入 hot / cold。"""

    cold_path = tmp_path / "trace" / "provider-failure-metadata.jsonl"
    metadata: Mapping[str, JsonValue] = {
        "schema_version": 1,
        "signal_source": "PROVIDER_PROTOCOL_ERROR",
        "failure_kind": "provider_protocol_error",
        "provider_error_code": "invalid_tool_arguments",
        "diagnostic_refs": ["provider-req-1"],
    }
    with open_host_durable_store(_options(tmp_path)) as store:
        event = _append_tool_event(
            store.transaction_runner,
            event_id="event-provider-protocol-failure",
            event_type="PROVIDER_PROTOCOL_ERROR",
            event_class=EventClass.DIAGNOSTIC,
            payload={
                "provider_request_id": "provider-req-1",
                "error_code": "invalid_tool_arguments",
                _FIELD_FAILURE_METADATA: metadata,
            },
        )

        _run_trace_once(store.transaction_runner, cold_path)
        row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(transaction, event.event_id)
        )
        cold_lines = _json_lines(cold_path)

        assert row is not None
        assert row.trace_summary[_FIELD_FAILURE_METADATA] == metadata
        assert _cold_trace_summary(cold_lines, 0) == row.trace_summary


def test_tool_trace_projects_provider_diagnostic_without_failure_metadata(
    tmp_path: Path,
) -> None:
    """PROVIDER_DIAGNOSTIC 只作为诊断展示，不生成失败元数据。"""

    cold_path = tmp_path / "trace" / "provider-diagnostic.jsonl"
    with open_host_durable_store(_options(tmp_path)) as store:
        event = _append_tool_event(
            store.transaction_runner,
            event_id="event-provider-diagnostic",
            event_type="PROVIDER_DIAGNOSTIC",
            event_class=EventClass.DIAGNOSTIC,
            payload={
                "provider_request_id": "provider-req-diagnostic",
                "client_correlation_id": "client-diagnostic",
                "diagnostic_code": "usage_field_malformed",
                "severity": "warning",
                "message": "usage ignored",
                "diagnostic_source": "sse_parser",
                "payload_ref": "payload-provider-diagnostic",
                "payload_digest": (
                    "sha256:"
                    "2222222222222222222222222222222222222222222222222222222222222222"
                ),
            },
        )

        _run_trace_once(store.transaction_runner, cold_path)
        row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(transaction, event.event_id)
        )
        cold_lines = _json_lines(cold_path)

        assert row is not None
        assert row.provider_request_id == "provider-req-diagnostic"
        assert row.diagnostic_ref == "payload-provider-diagnostic"
        assert _FIELD_FAILURE_METADATA not in row.trace_summary
        assert row.trace_summary["client_correlation_id"] == "client-diagnostic"
        assert row.trace_summary["provider_error_ref"] is None
        assert row.trace_summary["diagnostic_refs"] == [
            "payload-provider-diagnostic",
            "provider-req-diagnostic",
        ]
        assert "provider_error_code" not in row.trace_summary
        assert len(cold_lines) == 1
        assert cold_lines[0]["diagnostic_refs"] == [
            "payload-provider-diagnostic",
            "provider-req-diagnostic",
        ]
        assert cold_lines[0]["client_correlation_id"] == "client-diagnostic"
        assert _cold_trace_summary(cold_lines, 0) == row.trace_summary


def test_tool_trace_projects_provider_protocol_partial_tool_call_signal_states(
    tmp_path: Path,
) -> None:
    """PROVIDER_PROTOCOL_ERROR 区分 absent、none 与 present partial signal。"""

    cold_path = tmp_path / "trace" / "provider-partial-tool-call.jsonl"
    arguments_sha256 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    none_signal: Mapping[str, JsonValue] = {
        "schema_version": 1,
        "signal_source": "PROVIDER_PROTOCOL_ERROR",
        "partial_tool_call_count": 0,
        "summary_status": "none",
        "raw_payload_present": True,
        "partial_tool_calls": [],
    }
    present_signal: Mapping[str, JsonValue] = {
        "schema_version": 1,
        "signal_source": "PROVIDER_PROTOCOL_ERROR",
        "partial_tool_call_count": 1,
        "summary_status": "present",
        "raw_payload_present": False,
        "partial_tool_calls": [
            {
                "tool_call_index": 0,
                "tool_call_id": "call-bounded",
                "name_fragment": "lookup_filing",
                "arguments_byte_size": 42,
                "arguments_sha256": arguments_sha256,
                "arguments_present": True,
            }
        ],
    }
    with open_host_durable_store(_options(tmp_path)) as store:
        absent = _append_tool_event(
            store.transaction_runner,
            event_id="event-provider-partial-absent",
            event_type="PROVIDER_PROTOCOL_ERROR",
            event_class=EventClass.DIAGNOSTIC,
            payload={
                "provider_request_id": "provider-req-absent",
                "error_code": "invalid_stream",
            },
        )
        none = _append_tool_event(
            store.transaction_runner,
            event_id="event-provider-partial-none",
            event_type="PROVIDER_PROTOCOL_ERROR",
            event_class=EventClass.DIAGNOSTIC,
            payload={
                "provider_request_id": "provider-req-none",
                "error_code": "invalid_stream",
                _FIELD_PARTIAL_TOOL_CALL_SIGNAL: none_signal,
            },
        )
        present = _append_tool_event(
            store.transaction_runner,
            event_id="event-provider-partial-present",
            event_type="PROVIDER_PROTOCOL_ERROR",
            event_class=EventClass.DIAGNOSTIC,
            payload={
                "provider_request_id": "provider-req-present",
                "error_code": "invalid_stream",
                _FIELD_PARTIAL_TOOL_CALL_SIGNAL: present_signal,
            },
        )

        _run_trace_once(store.transaction_runner, cold_path)
        absent_row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(transaction, absent.event_id)
        )
        none_row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(transaction, none.event_id)
        )
        present_row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(transaction, present.event_id)
        )
        cold_lines = _json_lines(cold_path)

        assert absent_row is not None
        assert none_row is not None
        assert present_row is not None
        assert _FIELD_PARTIAL_TOOL_CALL_SIGNAL not in absent_row.trace_summary
        assert none_row.trace_summary[_FIELD_PARTIAL_TOOL_CALL_SIGNAL] == none_signal
        assert (
            present_row.trace_summary[_FIELD_PARTIAL_TOOL_CALL_SIGNAL]
            == present_signal
        )
        assert _FIELD_PARTIAL_TOOL_CALL_SIGNAL not in _cold_trace_summary(
            cold_lines, 0
        )
        assert _cold_trace_summary(cold_lines, 1)[
            _FIELD_PARTIAL_TOOL_CALL_SIGNAL
        ] == none_signal
        assert _cold_trace_summary(cold_lines, 2)[
            _FIELD_PARTIAL_TOOL_CALL_SIGNAL
        ] == present_signal


@pytest.mark.parametrize(
    ("tool_timing", "message"),
    (
        (
            {
                "schema_version": 1,
                "status": "available",
                "started_at": "2026-06-11T00:00:01+00:00",
                "finished_at": "2026-06-11T00:00:00+00:00",
                "duration_ms": -1,
                "duration_source": "tool_result_meta",
            },
            "duration_ms",
        ),
        (
            {
                "schema_version": 1,
                "status": "available",
                "started_at": "2026-06-11T00:00:00+00:00",
                "finished_at": "2026-06-11T00:00:01+00:00",
                "duration_ms": "1000",
                "duration_source": "tool_result_meta",
            },
            "duration_ms",
        ),
        (
            {
                "schema_version": 1,
                "status": "missing_tool_result_meta",
                "started_at": "2026-06-11T00:00:00+00:00",
                "finished_at": None,
                "duration_ms": None,
                "duration_source": None,
            },
            "started_at",
        ),
    ),
)
def test_tool_trace_rejects_malformed_tool_timing_signal(
    tmp_path: Path, tool_timing: Mapping[str, JsonValue], message: str
) -> None:
    """malformed tool_timing 以 HostDurableError fail closed。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        event = _append_tool_event(
            store.transaction_runner,
            event_id=f"event-malformed-tool-timing-{message}",
            event_type="TOOL_RESULT_ACCEPTED",
            payload={
                "tool_call_id": "tool-call-malformed-timing",
                "tool_name": "lookup_filing",
                "outcome_digest": "sha256:outcome-malformed-timing",
                _FIELD_TOOL_TIMING: tool_timing,
            },
        )
        consumer = ToolTraceProjectionConsumer(
            ToolTraceSinkOptions(cold_jsonl_path=tmp_path / "trace.jsonl")
        )

        with pytest.raises(HostDurableError, match=message):
            store.transaction_runner.run_write(
                lambda transaction: consumer.apply_event(
                    transaction,
                    projection_event_view_from_row(event),
                )
            )


@pytest.mark.parametrize(
    ("failure_metadata", "message"),
    (
        (
            {
                "schema_version": 1,
                "signal_source": "TOOL_RESULT_ACCEPTED",
                "failure_kind": "unknown_failure",
                "diagnostic_refs": [],
            },
            "failure_kind",
        ),
        (
            {
                "schema_version": 1,
                "signal_source": "PROVIDER_PROTOCOL_ERROR",
                "failure_kind": "tool_failed",
                "error_code": "lookup_failed",
                "repair_hint": None,
                "repair_hint_truncated": False,
                "repair_hint_sha256": None,
                "diagnostic_refs": [],
            },
            "signal_source",
        ),
        (
            {
                "schema_version": 1,
                "signal_source": "TOOL_RESULT_ACCEPTED",
                "failure_kind": "tool_failed",
                "error_code": "lookup_failed",
                "repair_hint": "x" * 513,
                "repair_hint_truncated": False,
                "repair_hint_sha256": ("sha256:" + hashlib.sha256(("x" * 513).encode("utf-8")).hexdigest()),
                "diagnostic_refs": [],
            },
            "repair_hint",
        ),
    ),
)
def test_tool_trace_rejects_malformed_failure_metadata_signal(
    tmp_path: Path, failure_metadata: Mapping[str, JsonValue], message: str
) -> None:
    """malformed failure_metadata 以 HostDurableError fail closed。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        event = _append_tool_event(
            store.transaction_runner,
            event_id=f"event-malformed-failure-metadata-{message}",
            event_type="TOOL_RESULT_ACCEPTED",
            payload={
                "tool_call_id": "tool-call-malformed-failure",
                "tool_name": "lookup_filing",
                _FIELD_FAILURE_METADATA: failure_metadata,
            },
        )
        consumer = ToolTraceProjectionConsumer(
            ToolTraceSinkOptions(cold_jsonl_path=tmp_path / "trace.jsonl")
        )

        with pytest.raises(HostDurableError, match=message):
            store.transaction_runner.run_write(
                lambda transaction: consumer.apply_event(
                    transaction,
                    projection_event_view_from_row(event),
                )
            )


@pytest.mark.parametrize(
    ("partial_tool_call_signal", "message"),
    (
        (
            {
                "schema_version": 1,
                "signal_source": "PROVIDER_PROTOCOL_ERROR",
                "partial_tool_call_count": 0,
                "summary_status": "present",
                "raw_payload_present": False,
                "partial_tool_calls": [],
            },
            "present status",
        ),
        (
            {
                "schema_version": 1,
                "signal_source": "PROVIDER_PROTOCOL_ERROR",
                "partial_tool_call_count": 2,
                "summary_status": "present",
                "raw_payload_present": False,
                "partial_tool_calls": [
                    {
                        "tool_call_index": 0,
                        "tool_call_id": "call-bounded",
                        "name_fragment": "lookup_filing",
                        "arguments_byte_size": 42,
                        "arguments_sha256": ("0123456789abcdef0123456789abcdef" "0123456789abcdef0123456789abcdef"),
                        "arguments_present": True,
                    }
                ],
            },
            "count mismatch",
        ),
        (
            {
                "schema_version": 1,
                "signal_source": "PROVIDER_PROTOCOL_ERROR",
                "partial_tool_call_count": 1,
                "summary_status": "present",
                "raw_payload_present": False,
                "partial_tool_calls": [
                    {
                        "tool_call_index": 0,
                        "tool_call_id": "call-bounded",
                        "name_fragment": "lookup_filing",
                        "arguments_byte_size": 42,
                        "arguments_sha256": "sha256:not-engine-format",
                        "arguments_present": True,
                    }
                ],
            },
            "arguments_sha256",
        ),
    ),
)
def test_tool_trace_rejects_malformed_partial_tool_call_signal(
    tmp_path: Path,
    partial_tool_call_signal: Mapping[str, JsonValue],
    message: str,
) -> None:
    """malformed partial_tool_call_signal 以 HostDurableError fail closed。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        event = _append_tool_event(
            store.transaction_runner,
            event_id=f"event-malformed-partial-tool-call-{message}",
            event_type="PROVIDER_PROTOCOL_ERROR",
            event_class=EventClass.DIAGNOSTIC,
            payload={
                "provider_request_id": "provider-req-malformed-partial",
                "error_code": "invalid_stream",
                _FIELD_PARTIAL_TOOL_CALL_SIGNAL: partial_tool_call_signal,
            },
        )
        consumer = ToolTraceProjectionConsumer(
            ToolTraceSinkOptions(cold_jsonl_path=tmp_path / "trace.jsonl")
        )

        with pytest.raises(HostDurableError, match=message):
            store.transaction_runner.run_write(
                lambda transaction: consumer.apply_event(
                    transaction,
                    projection_event_view_from_row(event),
                )
            )


def test_tool_trace_derives_context_pressure_from_compaction_failed_payload(
    tmp_path: Path,
) -> None:
    """failed compact fact 从现有 request/result payload 派生 context pressure。"""

    cold_path = tmp_path / "trace" / "compact-failed.jsonl"
    with open_host_durable_store(_options(tmp_path)) as store:
        _append_tool_event(
            store.transaction_runner,
            event_id="event-context-requested",
            event_type="CONTEXT_COMPACTION_REQUESTED",
            payload={
                "trigger_source": "reactive",
                "budget_reason": "provider_overflow",
                "budget_snapshot_ref": "sha256:" + "a" * 64,
                "input_snapshot_cursor": 12,
                "estimator_digest": "sha256:" + "b" * 64,
                "policy_ref": "policy-ref",
                "provider_request_id": "provider-1",
                "provider_error_ref": "engine-event-ref",
                "attempt_id": "attempt-1",
                "execution_id": "execution-1",
            },
        )
        failed = _append_tool_event(
            store.transaction_runner,
            event_id="event-context-failed",
            event_type="CONTEXT_COMPACTION_FAILED",
            payload={
                "operation_id": "event-context-requested",
                "failure_reason": "quality_check_failed",
                "policy_decision": "reactive_compact_failed",
                "retryable": False,
                "attempt_count": 1,
                "retry_repair_budget_exhausted": True,
                "diagnostic_refs": ["diagnostic:compact"],
                "budget_after_attempted_compact": 180,
                "fallback_policy_decision": "recent_window_budget_passed",
                "fallback_input_window": {"selected_block_ids": ["block-current"]},
                "fallback_input_digest": "sha256:" + "c" * 64,
                "fallback_budget_result": {
                    "estimated_input_tokens": 42,
                    "decision": "allow_dispatch",
                },
                "fallback_action": "dispatch",
            },
        )

        _run_trace_once(store.transaction_runner, cold_path)
        row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(
                transaction, failed.event_id
            )
        )
        cold_lines = _json_lines(cold_path)

        assert row is not None
        pressure = row.trace_summary[_FIELD_CONTEXT_PRESSURE]
        assert isinstance(pressure, Mapping)
        assert pressure == {
            "schema_version": 1,
            "signal_source": "CONTEXT_COMPACTION_FAILED",
            "status": "compaction_failed",
            "policy_ref": "policy-ref",
            "estimator_digest": "sha256:" + "b" * 64,
            "operation_id": "event-context-requested",
            "trigger_source": "reactive",
            "budget_reason": "provider_overflow",
            "budget_after_compact": None,
            "budget_after_attempted_compact": 180,
            "fallback_action": "dispatch",
            "fallback_policy_decision": "recent_window_budget_passed",
            "retry_repair_budget_exhausted": True,
        }
        assert row.trace_summary[_FIELD_FAILURE_METADATA] == {
            "schema_version": 1,
            "signal_source": "CONTEXT_COMPACTION_FAILED",
            "failure_kind": "context_compaction_failed",
            "failure_reason": "quality_check_failed",
            "policy_decision": "reactive_compact_failed",
            "retryable": False,
            "attempt_count": 1,
            "retry_repair_budget_exhausted": True,
            "fallback_action": "dispatch",
            "fallback_policy_decision": "recent_window_budget_passed",
            "diagnostic_refs": ["diagnostic:compact"],
        }
        assert _cold_trace_summary(cold_lines, 1) == row.trace_summary


def test_tool_trace_derives_context_pressure_from_compaction_rejected_payload(
    tmp_path: Path,
) -> None:
    """attempt rejected compact fact 从现有 payload 派生最小 context pressure。"""

    cold_path = tmp_path / "trace" / "compact-rejected.jsonl"
    with open_host_durable_store(_options(tmp_path)) as store:
        rejected = _append_tool_event(
            store.transaction_runner,
            event_id="event-context-rejected",
            event_type="CONTEXT_COMPACTION_ATTEMPT_REJECTED",
            payload={
                "operation_id": "event-context-requested",
                "attempt_number": 1,
                "failure_category": "quality_check_failed",
                "repairable": True,
                "runner_attempt_summary_refs": ["runner-attempt:1"],
                "diagnostic_refs": ["diagnostic:reject"],
                "next_policy_decision": "retry_or_fallback",
                "budget_after_attempted_compact": 180,
            },
        )

        _run_trace_once(store.transaction_runner, cold_path)
        row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(
                transaction, rejected.event_id
            )
        )
        cold_lines = _json_lines(cold_path)

        assert row is not None
        pressure = row.trace_summary[_FIELD_CONTEXT_PRESSURE]
        assert isinstance(pressure, Mapping)
        assert pressure == {
            "schema_version": 1,
            "signal_source": "CONTEXT_COMPACTION_ATTEMPT_REJECTED",
            "status": "compaction_attempt_rejected",
            "operation_id": "event-context-requested",
            "budget_after_attempted_compact": 180,
            "next_policy_decision": "retry_or_fallback",
            "failure_category": "quality_check_failed",
            "repairable": True,
        }
        assert row.trace_summary[_FIELD_FAILURE_METADATA] == {
            "schema_version": 1,
            "signal_source": "CONTEXT_COMPACTION_ATTEMPT_REJECTED",
            "failure_kind": "context_compaction_attempt_rejected",
            "failure_category": "quality_check_failed",
            "repairable": True,
            "next_policy_decision": "retry_or_fallback",
            "budget_after_attempted_compact": 180,
            "diagnostic_refs": ["diagnostic:reject"],
        }
        assert _cold_trace_summary(cold_lines, 0) == row.trace_summary


def test_tool_trace_omits_missing_or_null_summary_signal_objects(
    tmp_path: Path,
) -> None:
    """缺失或 null 的 signal 不写入 summary，避免表达不存在的事实。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: hot/cold summary 错误保留空 signal 时抛出。
    """

    cold_path = tmp_path / "trace" / "signals-null.jsonl"
    with open_host_durable_store(_options(tmp_path)) as store:
        missing_event = _append_canonical_tool_request_event(
            store.transaction_runner,
            event_id="event-signals-missing",
            tool_call_id="tool-call-missing",
            tool_name="lookup_filing",
        )
        null_event = _append_accepted_tool_result_event(
            store.transaction_runner,
            event_id="event-signals-null",
            tool_call_id="tool-call-null",
            tool_name="lookup_filing",
            additional_payload={
                _FIELD_CONTEXT_PRESSURE: None,
                _FIELD_TOOL_TIMING: None,
                _FIELD_FAILURE_METADATA: None,
                _FIELD_PARTIAL_TOOL_CALL_SIGNAL: None,
            },
        )

        _run_trace_once(store.transaction_runner, cold_path)
        missing_row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(
                transaction, missing_event.event_id
            )
        )
        null_row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(transaction, null_event.event_id)
        )
        cold_lines = _json_lines(cold_path)

        assert missing_row is not None
        assert null_row is not None
        missing_summary = _cold_trace_summary_for_event(
            cold_lines,
            event_id=missing_event.event_id,
        )
        null_summary = _cold_trace_summary_for_event(
            cold_lines,
            event_id=null_event.event_id,
        )
        for field_name in _SIGNAL_FIELD_NAMES:
            assert field_name not in missing_row.trace_summary
            assert field_name not in null_row.trace_summary
            assert field_name not in missing_summary
            assert field_name not in null_summary


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    (
        (_FIELD_CONTEXT_PRESSURE, "invalid-context-pressure"),
        (_FIELD_TOOL_TIMING, 123),
        (_FIELD_FAILURE_METADATA, ["invalid-failure-metadata"]),
        (_FIELD_PARTIAL_TOOL_CALL_SIGNAL, False),
    ),
)
def test_tool_trace_rejects_non_object_summary_signal_fields(
    tmp_path: Path, field_name: str, invalid_value: JsonValue
) -> None:
    """signal 字段存在但不是 object/null 时以 durable error fail closed。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        event = _append_tool_event(
            store.transaction_runner,
            event_id=f"event-invalid-{field_name}",
            event_type="TOOL_RESULT_ACCEPTED",
            payload={
                "tool_call_id": "tool-call-invalid-signal",
                "tool_name": "lookup_filing",
                field_name: invalid_value,
            },
        )
        consumer = ToolTraceProjectionConsumer(
            ToolTraceSinkOptions(cold_jsonl_path=tmp_path / "trace.jsonl")
        )

        with pytest.raises(HostDurableError, match=field_name):
            store.transaction_runner.run_write(
                lambda transaction: consumer.apply_event(
                    transaction,
                    projection_event_view_from_row(event),
                )
            )


def test_tool_trace_resolves_large_tool_call_arguments_without_internal_refs(
    tmp_path: Path,
) -> None:
    """Tool Trace 严格解析 descriptor 并只展示 bounded exact 参数。"""

    cold_path = tmp_path / "trace" / "cold.jsonl"
    large_arguments: Mapping[str, JsonValue] = {
        "ticker": "MSFT",
        "query": "x" * 1024,
    }
    arguments_json: Mapping[str, JsonValue] = {"arguments": large_arguments}
    arguments_digest = sha256_digest_json(arguments_json)
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref="payload-tool-call-arguments-large",
                    payload_id="sqlite-payload-tool-call-arguments-large",
                    payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                    payload_json=arguments_json,
                    media_type="application/json",
                    metadata={
                        "descriptor_kind": TOOL_CALL_ARGUMENTS_DESCRIPTOR_KIND,
                    },
                    expected_digest=arguments_digest,
                ),
            )
        )
        request_payload: Mapping[str, JsonValue] = {
            "tool_call_id": "tool-call-large-arguments",
            "tool_name": "lookup_filing",
            "tool_schema_digest": "sha256:schema",
            "tool_identity_digest": "sha256:identity",
            "normalized_arguments_digest": arguments_digest,
            "arguments_json_size_bytes": len(
                canonical_json_dumps(arguments_json).encode("utf-8")
            ),
            "arguments_storage_kind": "payload_descriptor",
            "arguments_inline_json": None,
            "arguments_payload_ref": "payload-tool-call-arguments-large",
            "arguments_payload_digest": arguments_digest,
            "semantic_input_digest": "sha256:semantic",
            "semantic_query_storage_kind": "absent",
            "semantic_query_text": None,
            "semantic_query_payload_ref": None,
            "semantic_query_digest": None,
        }
        _append_tool_event(
            store.transaction_runner,
            event_id="event-requested-large-arguments",
            event_type="TOOL_CALL_REQUESTED",
            payload=cast(JsonValue, request_payload),
        )

        _run_trace_once(store.transaction_runner, cold_path)
        hot_row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(
                transaction, "event-requested-large-arguments"
            )
        )
        cold_lines = _json_lines(cold_path)

        assert request_payload["arguments_payload_ref"] == (
            "payload-tool-call-arguments-large"
        )
        assert request_payload["arguments_payload_digest"] == arguments_digest
        assert hot_row is not None
        assert hot_row.normalized_arguments_digest == arguments_digest
        assert len(cold_lines) == 1
        line_text = json.dumps(cold_lines[0], sort_keys=True)
        readable_text = json.dumps(
            cold_lines[0]["trace_summary"], sort_keys=True
        )
        assert arguments_digest in line_text
        assert "payload-tool-call-arguments-large" not in readable_text
        assert arguments_digest not in readable_text
        assert "x" * 128 in readable_text
        assert "arguments payload" not in readable_text


def test_tool_trace_projects_runner_call_manifest_signal(tmp_path: Path) -> None:
    """Tool Trace hot row 只复制 shared owner 校验后的 fixed scalars。"""

    cold_path = tmp_path / "trace" / "runner-call.jsonl"
    manifest_digest = sha256_digest_json({"manifest": "runner-call"})
    role_digest = sha256_digest_json({"roles": ["system", "user"]})
    projection_digest = sha256_digest_json({"projection": "summary"})
    with open_host_durable_store(_options(tmp_path)) as store:
        event = _append_tool_event(
            store.transaction_runner,
            event_id="event-runner-call-input",
            event_type="RUNNER_CALL_INPUT_ASSEMBLED",
            payload={
                "session_id": "session-1",
                "host_run_id": "run-1",
                "attempt_id": "attempt-1",
                "execution_id": "execution-1",
                "runner_call_index": 0,
                "runner_call_kind": "initial_user_dispatch",
                "runner_call_trigger_reason": "initial_user_input",
                "iteration_id": "iteration-1",
                "iteration_index": 0,
                "manifest_payload_ref": "payload-runner-call-manifest",
                "manifest_digest": manifest_digest,
                "manifest_schema_version": "runner_call_input_manifest.v2",
                "validation_status": "complete",
                "message_count": 2,
                "role_sequence_digest": role_digest,
                "input_projection_digest": projection_digest,
                "runner_call_projection_artifact_ref": None,
                "runner_call_projection_artifact_digest": None,
                "runner_call_projection_artifact_size_bytes": None,
                "diagnostic": {
                    "status": "complete",
                    "reason": None,
                    "missing_atom_kind": None,
                    "missing_ref_kind": None,
                    "missing_ref": None,
                    "observed_count": 2,
                    "expected_count": 2,
                    "observed_digest": role_digest,
                    "expected_digest": role_digest,
                    "consumer_boundary": "host.run_input.builder",
                },
            },
        )

        _run_trace_once(store.transaction_runner, cold_path)
        row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(transaction, event.event_id)
        )
        cold_lines = _json_lines(cold_path)

        assert row is not None
        assert row.result_digest == manifest_digest
        assert row.trace_summary["runner_call_index"] == 0
        assert row.trace_summary["manifest_ref"] == "payload-runner-call-manifest"
        assert row.trace_summary["manifest_digest"] == manifest_digest
        assert row.trace_summary["message_count"] == 2
        assert row.trace_summary["role_sequence_digest"] == role_digest
        assert row.trace_summary["input_projection_digest"] == projection_digest
        assert "projector_metadata_summary" not in row.trace_summary
        assert row.trace_summary["diagnostic"] == {
            "status": "complete",
            "reason": None,
            "missing_atom_kind": None,
            "missing_ref_kind": None,
            "missing_ref": None,
            "observed_count": 2,
            "expected_count": 2,
            "observed_digest": role_digest,
            "expected_digest": role_digest,
            "consumer_boundary": "tool_trace_query",
        }
        assert cold_lines[0]["trace_summary"] == row.trace_summary


def test_tool_trace_projects_limited_runner_call_manifest_diagnostic(
    tmp_path: Path,
) -> None:
    """Tool Trace 从 canonical payload 复制 non-complete typed diagnostic。"""

    cold_path = tmp_path / "trace" / "runner-call-limited.jsonl"
    manifest_digest = sha256_digest_json({"manifest": "runner-call-limited"})
    role_digest = sha256_digest_json({"roles": ["system", "user", "tool"]})
    projection_digest = sha256_digest_json({"projection": "limited"})
    diagnostic = {
        "status": "limited_signal",
        "reason": "missing_projection_artifact",
        "missing_atom_kind": None,
        "missing_ref_kind": "artifact_ref",
        "missing_ref": None,
        "observed_count": 3,
        "expected_count": None,
        "observed_digest": role_digest,
        "expected_digest": None,
        "consumer_boundary": "host.engine_ingest",
    }
    with open_host_durable_store(_options(tmp_path)) as store:
        event = _append_tool_event(
            store.transaction_runner,
            event_id="event-runner-call-input-limited",
            event_type="RUNNER_CALL_INPUT_ASSEMBLED",
            payload={
                "session_id": "session-1",
                "host_run_id": "run-1",
                "attempt_id": "attempt-1",
                "execution_id": "execution-1",
                "runner_call_index": 1,
                "runner_call_kind": "tool_result_continuation",
                "runner_call_trigger_reason": "tool_results_available",
                "iteration_id": "iteration-2",
                "iteration_index": 1,
                "manifest_payload_ref": "payload-runner-call-manifest-limited",
                "manifest_digest": manifest_digest,
                "manifest_schema_version": "runner_call_input_manifest.v2",
                "validation_status": "limited_signal",
                "message_count": 3,
                "role_sequence_digest": role_digest,
                "input_projection_digest": projection_digest,
                "runner_call_projection_artifact_ref": None,
                "runner_call_projection_artifact_digest": None,
                "runner_call_projection_artifact_size_bytes": None,
                "diagnostic": diagnostic,
            },
        )

        _run_trace_once(store.transaction_runner, cold_path)
        row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(transaction, event.event_id)
        )
        cold_lines = _json_lines(cold_path)

        assert row is not None
        assert row.trace_summary["runner_call_index"] == 1
        assert row.trace_summary["manifest_ref"] == (
            "payload-runner-call-manifest-limited"
        )
        assert row.trace_summary["diagnostic"] == {
            "status": "limited_signal",
            "reason": "missing_projection_artifact",
            "missing_atom_kind": None,
            "missing_ref_kind": "artifact_ref",
            "missing_ref": None,
            "observed_count": 3,
            "expected_count": None,
            "observed_digest": role_digest,
            "expected_digest": None,
            "consumer_boundary": "tool_trace_query",
        }
        assert cold_lines[0]["trace_summary"] == row.trace_summary


def test_tool_trace_rejects_non_complete_runner_call_without_diagnostic(
    tmp_path: Path,
) -> None:
    """非 complete runner-call signal 缺少 typed diagnostic 时 fail closed。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        event = _append_tool_event(
            store.transaction_runner,
            event_id="event-runner-call-input-missing-diagnostic",
            event_type="RUNNER_CALL_INPUT_ASSEMBLED",
            payload={
                "session_id": "session-1",
                "host_run_id": "run-1",
                "attempt_id": "attempt-1",
                "execution_id": "execution-1",
                "runner_call_index": 2,
                "runner_call_kind": "tool_result_continuation",
                "runner_call_trigger_reason": "tool_results_available",
                "iteration_id": None,
                "iteration_index": None,
                "manifest_payload_ref": "payload-runner-call-manifest-missing",
                "manifest_digest": sha256_digest_json(
                    {"manifest": "runner-call-missing-diagnostic"}
                ),
                "manifest_schema_version": "runner_call_input_manifest.v2",
                "validation_status": "limited_signal",
                "message_count": 1,
                "role_sequence_digest": sha256_digest_json({"roles": ["user"]}),
                "input_projection_digest": sha256_digest_json(
                    {"projection": "missing-diagnostic"}
                ),
                "runner_call_projection_artifact_ref": None,
                "runner_call_projection_artifact_digest": None,
                "runner_call_projection_artifact_size_bytes": None,
                "diagnostic": None,
            },
        )
        consumer = ToolTraceProjectionConsumer(
            ToolTraceSinkOptions(cold_jsonl_path=tmp_path / "trace.jsonl")
        )

        with pytest.raises(HostDurableError, match="hot diagnostic"):
            store.transaction_runner.run_write(
                lambda transaction: consumer.apply_event(
                    transaction,
                    projection_event_view_from_row(event),
                )
            )


def test_tool_trace_projects_mismatch_runner_call_diagnostic(
    tmp_path: Path,
) -> None:
    """Tool Trace 复制 runner-call mismatch diagnostic 的 count / digest 证据。"""

    cold_path = tmp_path / "trace" / "runner-call-mismatch.jsonl"
    observed_digest = sha256_digest_json({"roles": ["system", "user", "tool"]})
    expected_digest = sha256_digest_json({"roles": ["system", "user"]})
    with open_host_durable_store(_options(tmp_path)) as store:
        event = _append_tool_event(
            store.transaction_runner,
            event_id="event-runner-call-input-mismatch",
            event_type="RUNNER_CALL_INPUT_ASSEMBLED",
            payload={
                "session_id": "session-1",
                "host_run_id": "run-1",
                "attempt_id": "attempt-1",
                "execution_id": "execution-1",
                "runner_call_index": 3,
                "runner_call_kind": "tool_result_continuation",
                "runner_call_trigger_reason": "tool_results_available",
                "iteration_id": "iteration-3",
                "iteration_index": 2,
                "manifest_payload_ref": "payload-runner-call-manifest-mismatch",
                "manifest_digest": sha256_digest_json(
                    {"manifest": "runner-call-mismatch"}
                ),
                "manifest_schema_version": "runner_call_input_manifest.v2",
                "validation_status": "mismatch",
                "message_count": 3,
                "role_sequence_digest": observed_digest,
                "input_projection_digest": sha256_digest_json(
                    {"projection": "mismatch"}
                ),
                "runner_call_projection_artifact_ref": None,
                "runner_call_projection_artifact_digest": None,
                "runner_call_projection_artifact_size_bytes": None,
                "diagnostic": {
                    "status": "mismatch",
                    "reason": "role_sequence_digest_mismatch",
                    "missing_atom_kind": None,
                    "missing_ref_kind": None,
                    "missing_ref": None,
                    "observed_count": 3,
                    "expected_count": 2,
                    "observed_digest": observed_digest,
                    "expected_digest": expected_digest,
                    "consumer_boundary": "host.engine_ingest",
                },
            },
        )

        _run_trace_once(store.transaction_runner, cold_path)
        row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(transaction, event.event_id)
        )

        assert row is not None
        assert row.trace_summary["diagnostic"] == {
            "status": "mismatch",
            "reason": "role_sequence_digest_mismatch",
            "missing_atom_kind": None,
            "missing_ref_kind": None,
            "missing_ref": None,
            "observed_count": 3,
            "expected_count": 2,
            "observed_digest": observed_digest,
            "expected_digest": expected_digest,
            "consumer_boundary": "tool_trace_query",
        }


def test_tool_trace_projection_includes_client_correlation_id(
    tmp_path: Path,
) -> None:
    """Tool Trace summary / cold JSONL trace_summary 暴露 client correlation。"""

    cold_path = tmp_path / "trace" / "tool-trace.jsonl"
    with open_host_durable_store(_options(tmp_path)) as store:
        event = _append_tool_event(
            store.transaction_runner,
            event_id="event-terminal-correlation",
            event_type="RUN_FAILED",
            payload={
                "provider_request_id": "req-terminal",
                "client_correlation_id": "client-terminal",
                "engine_event_ref": "event-engine-terminal",
                "terminal_summary_ref": "summary-ref",
                "terminal_summary_digest": "sha256:summary",
            },
        )

        _run_trace_once(store.transaction_runner, cold_path)
        row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(
                transaction, event.event_id
            )
        )

        assert row is not None
        assert row.trace_summary["client_correlation_id"] == "client-terminal"
        cold_lines = _json_lines(cold_path)
        assert len(cold_lines) == 1
        trace_summary = cold_lines[0]["trace_summary"]
        assert isinstance(trace_summary, Mapping)
        assert (
            trace_summary["client_correlation_id"] == "client-terminal"
        )


def test_diagnostic_trace_preserves_client_correlation_without_provider_id(
    tmp_path: Path,
) -> None:
    """diagnostic 无 provider_request_id 时仍保留客户端 fallback id。"""

    cold_path = tmp_path / "trace" / "diagnostic-client-fallback.jsonl"
    with open_host_durable_store(_options(tmp_path)) as store:
        event = _append_tool_event(
            store.transaction_runner,
            event_id="event-diagnostic-client-fallback",
            event_type="ENGINE_EVENT_DIAGNOSTIC",
            event_class=EventClass.DIAGNOSTIC,
            payload={
                "provider_request_id": None,
                "client_correlation_id": "client-fallback",
                "error_code": "provider_protocol_error",
            },
        )

        _run_trace_once(store.transaction_runner, cold_path)
        row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(
                transaction, event.event_id
            )
        )
        cold_lines = _json_lines(cold_path)

        assert row is not None
        assert row.provider_request_id is None
        assert row.diagnostic_ref is None
        assert row.trace_summary["client_correlation_id"] == "client-fallback"
        assert len(cold_lines) == 1
        assert cold_lines[0]["provider_request_id"] is None
        assert cold_lines[0]["client_correlation_id"] == "client-fallback"
        trace_summary = cold_lines[0]["trace_summary"]
        assert isinstance(trace_summary, Mapping)
        assert trace_summary["client_correlation_id"] == "client-fallback"


def test_diagnostic_trace_uses_raw_payload_ref_without_provider_id(
    tmp_path: Path,
) -> None:
    """diagnostic 无 provider id 时仍以 raw_payload_ref 作为诊断 ref。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: Tool Trace 投影不符合预期时抛出。
    """

    cold_path = tmp_path / "trace" / "diagnostic-raw-ref-fallback.jsonl"
    with open_host_durable_store(_options(tmp_path)) as store:
        event = _append_tool_event(
            store.transaction_runner,
            event_id="event-diagnostic-raw-ref-fallback",
            event_type="ENGINE_EVENT_DIAGNOSTIC",
            event_class=EventClass.DIAGNOSTIC,
            payload={
                "provider_request_id": None,
                "client_correlation_id": "client-fallback",
                "raw_payload_ref": "raw-ref-fallback",
                "raw_payload_digest": "sha256:raw-fallback",
                "error_code": "provider_protocol_error",
            },
        )

        _run_trace_once(store.transaction_runner, cold_path)
        row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(
                transaction, event.event_id
            )
        )
        cold_lines = _json_lines(cold_path)

        assert row is not None
        assert row.provider_request_id is None
        assert row.diagnostic_ref == "raw-ref-fallback"
        assert row.trace_summary["client_correlation_id"] == "client-fallback"
        assert len(cold_lines) == 1
        assert cold_lines[0]["diagnostic_refs"] == ["raw-ref-fallback"]
        assert cold_lines[0]["client_correlation_id"] == "client-fallback"
        trace_summary = cold_lines[0]["trace_summary"]
        assert isinstance(trace_summary, Mapping)
        assert trace_summary["client_correlation_id"] == "client-fallback"


def test_tool_trace_projection_rejects_non_text_client_correlation_id(
    tmp_path: Path,
) -> None:
    """payload 中非文本 client_correlation_id 按字段校验抛 durable error。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        event = _append_tool_event(
            store.transaction_runner,
            event_id="event-invalid-correlation",
            event_type="RUN_FAILED",
            payload={
                "provider_request_id": "req-terminal",
                "client_correlation_id": 123,
            },
        )
        consumer = ToolTraceProjectionConsumer(
            ToolTraceSinkOptions(cold_jsonl_path=tmp_path / "trace.jsonl")
        )

        with pytest.raises(HostDurableError, match="client_correlation_id"):
            store.transaction_runner.run_write(
                lambda transaction: consumer.apply_event(
                    transaction,
                    projection_event_view_from_row(event),
                )
            )


def test_cold_writer_failure_records_projection_failure_without_checkpoint(
    tmp_path: Path,
) -> None:
    """cold JSONL 写失败只记录 projection failure，不推进 checkpoint。"""

    cold_path = tmp_path / "trace-dir"
    cold_path.mkdir()
    with open_host_durable_store(_options(tmp_path)) as store:
        event = _append_tool_event(
            store.transaction_runner,
            event_id="event-result",
            event_type="TOOL_RESULT_ACCEPTED",
            payload={
                "tool_call_id": "tool-call-1",
                "tool_name": "lookup_filing",
                "outcome_digest": "sha256:outcome",
                "payload_digest": "sha256:payload",
            },
        )
        runner = ProjectionRunner(
            store.transaction_runner,
            (
                ToolTraceProjectionConsumer(
                    ToolTraceSinkOptions(
                        cold_jsonl_path=cold_path,
                        create_parent_dirs=False,
                        lock_path=None,
                    )
                ),
            ),
        )
        result = runner.run_once(TOOL_TRACE_CONSUMER_ID, limit=1)
        checkpoint = store.transaction_runner.run_read(
            lambda transaction: read_projection_checkpoint(
                transaction, TOOL_TRACE_CONSUMER_ID.value
            )
        )
        failure = store.transaction_runner.run_read(
            lambda transaction: read_projection_failure(
                transaction, TOOL_TRACE_CONSUMER_ID.value
            )
        )
        hot_row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(transaction, event.event_id)
        )

        assert result.failures == 1
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == 0
        assert failure is not None
        assert failure.failed_event_id == event.event_id
        assert hot_row is None


def test_projection_rebuild_from_event_log_restores_hot_rows(
    tmp_path: Path,
) -> None:
    """清空 Tool Trace projection 后可从 EventLog replay 恢复 hot rows。"""

    cold_path = tmp_path / "trace" / "cold.jsonl"
    with open_host_durable_store(_options(tmp_path)) as store:
        _append_canonical_tool_request_event(
            store.transaction_runner,
            event_id="event-requested",
            tool_call_id="tool-call-1",
            tool_name="lookup_filing",
        )
        catch_up_tool_trace_projection(
            store.transaction_runner,
            options=ToolTraceSinkOptions(cold_jsonl_path=cold_path),
        )
        assert _table_count(store.transaction_runner, TABLE_HOST_TOOL_TRACE_HOT) == 1

        _reset_tool_trace_projection(store.transaction_runner)
        assert _table_count(store.transaction_runner, TABLE_HOST_TOOL_TRACE_HOT) == 0

        catch_up_tool_trace_projection(
            store.transaction_runner,
            options=ToolTraceSinkOptions(cold_jsonl_path=cold_path),
        )
        rebuilt = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(
                transaction, "event-requested"
            )
        )
        event_count_after = _table_count(store.transaction_runner, "event_log")
        run_count_after = _table_count(store.transaction_runner, TABLE_HOST_RUNS)
        attempt_count_after = _table_count(
            store.transaction_runner, TABLE_HOST_ATTEMPTS
        )

        assert rebuilt is not None
        assert rebuilt.tool_call_id == "tool-call-1"
        assert [line["event_id"] for line in _json_lines(cold_path)] == [
            "event-requested"
        ]
        assert event_count_after == 1
        assert run_count_after == 0
        assert attempt_count_after == 0


def test_cold_jsonl_source_key_digest_conflict_records_failure_without_hot_row(
    tmp_path: Path,
) -> None:
    """cold JSONL 同 source key 但 digest 不同时记录 failure，且不补 hot row。"""

    cold_path = tmp_path / "trace" / "cold.jsonl"
    with open_host_durable_store(_options(tmp_path)) as store:
        event = _append_canonical_tool_request_event(
            store.transaction_runner,
            event_id="event-requested",
            tool_call_id="tool-call-1",
            tool_name="lookup_filing",
        )
        catch_up_tool_trace_projection(
            store.transaction_runner,
            options=ToolTraceSinkOptions(cold_jsonl_path=cold_path),
        )
        lines = _json_lines(cold_path)
        assert len(lines) == 1
        conflict_line = dict(lines[0])
        conflict_line["line_digest"] = "sha256:conflicting"
        conflict_line["cold_trace_digest"] = "sha256:conflicting"
        cold_path.write_text(
            json.dumps(conflict_line, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        _reset_tool_trace_projection(store.transaction_runner)
        result = catch_up_tool_trace_projection(
            store.transaction_runner,
            options=ToolTraceSinkOptions(cold_jsonl_path=cold_path),
        )
        hot_row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(transaction, event.event_id)
        )
        failure = store.transaction_runner.run_read(
            lambda transaction: read_projection_failure(
                transaction, TOOL_TRACE_CONSUMER_ID.value
            )
        )

        assert result.failures == 1
        assert hot_row is None
        assert failure is not None
        assert failure.failed_event_id == event.event_id
        assert _json_lines(cold_path)[0]["line_digest"] == "sha256:conflicting"


def test_default_tool_trace_path_is_derived_from_artifact_root(
    tmp_path: Path,
) -> None:
    """open_host 默认 Tool Trace cold JSONL 路径从 artifact_root 派生。"""

    assert _default_tool_trace_cold_jsonl_path(tmp_path / "artifacts") == (
        tmp_path / "artifacts" / "tool-trace" / "tool-trace-cold.jsonl"
    )


def test_tool_trace_producer_and_reader_share_adjacent_lock_owner(
    tmp_path: Path,
) -> None:
    """producer/reader 必须复用 Tool Trace owner 的相邻锁路径与既有 timeout。"""

    cold_path = tmp_path / "artifacts" / "tool-trace" / "trace.jsonl"
    lock_path = _tool_trace_cold_lock_path(cold_path)
    options = ToolTraceSinkOptions(
        cold_jsonl_path=cold_path,
        lock_path=lock_path,
    )

    assert lock_path == cold_path.with_name("trace.jsonl.lock")
    assert options.lock_path == lock_path
    assert _LOCK_TIMEOUT_SECONDS == 5.0


def _text_sha256(value: str) -> str:
    """计算文本 UTF-8 sha256 digest。

    :param value: 原始文本。
    :returns: ``sha256:`` 前缀 digest。
    """

    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"
