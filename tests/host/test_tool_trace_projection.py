"""Host Tool Trace hot / cold projection 测试。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.codec import sha256_digest_json
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
    TABLE_HOST_ATTEMPTS,
    TABLE_HOST_RUNS,
    TABLE_HOST_TOOL_TRACE_HOT,
    TOOL_CALL_ARGUMENTS_DESCRIPTOR_KIND,
)
from dayu.host.durable.tool_trace import read_tool_trace_hot_row
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.open_host import _default_tool_trace_cold_jsonl_path
from dayu.host.projection import ProjectionRunner
from dayu.host.projection import projection_event_view_from_row
from dayu.host.tool_trace import (
    TOOL_TRACE_CONSUMER_ID,
    ToolTraceProjectionConsumer,
    ToolTraceSinkOptions,
    catch_up_tool_trace_projection,
)

_FIXED_NOW = datetime(2026, 5, 29, 2, 3, 4, tzinfo=UTC)


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
) -> EventLogRow:
    """在单个 transaction 内追加 Tool Trace 测试 EventLog row。

    :param transaction: Host durable transaction。
    :param event_id: EventLog id。
    :param event_type: EventLog type。
    :param payload: inline payload。
    :param event_class: EventLog class。
    :param payload_ref: 可选 payload descriptor ref。
    :param payload_digest: 可选 payload digest。
    :returns: 已追加 EventLog row。
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
            execution_id="execution-1",
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


def test_tool_call_chain_projects_hot_rows_and_cold_lines(tmp_path: Path) -> None:
    """TOOL_CALL_REQUESTED / GOVERNED / RESULT_ACCEPTED 投影关键字段。"""

    cold_path = tmp_path / "trace" / "cold.jsonl"
    lock_path = tmp_path / "locks" / "tool-trace-cold.jsonl.lock"
    with open_host_durable_store(_options(tmp_path)) as store:
        requested = _append_tool_event(
            store.transaction_runner,
            event_id="event-requested",
            event_type="TOOL_CALL_REQUESTED",
            payload={
                "tool_call_id": "tool-call-1",
                "tool_name": "lookup_filing",
                "tool_schema_digest": "sha256:schema",
                "tool_identity_digest": "sha256:identity",
                "normalized_arguments_digest": "sha256:args",
                "semantic_input_digest": "sha256:semantic",
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
            event_id="event-result",
            event_type="TOOL_RESULT_ACCEPTED",
            payload={
                "tool_call_id": "tool-call-1",
                "tool_name": "lookup_filing",
                "normalized_arguments_digest": "sha256:args",
                "semantic_input_digest": "sha256:semantic",
                "outcome_digest": "sha256:outcome",
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
        assert requested_row.normalized_arguments_digest == "sha256:args"
        assert requested_row.semantic_input_digest == "sha256:semantic"
        assert governed_row is not None
        assert governed_row.diagnostic_ref == "diag-duplicate"
        assert governed_row.trace_summary["duplicate_decision"] == "reuse"
        assert governed_row.trace_summary["duplicate_scope"] == {
            "kind": "attempt",
            "attempt_id": "attempt-trace",
        }
        assert result_row is not None
        assert result_row.result_digest == "sha256:outcome"
        assert result_row.diagnostic_ref == "diag-result"
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


def test_tool_trace_does_not_inline_large_tool_call_arguments(
    tmp_path: Path,
) -> None:
    """Tool Trace 投影 TOOL_CALL_REQUESTED 时不展开大参数 descriptor。"""

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
        _append_tool_event(
            store.transaction_runner,
            event_id="event-requested-large-arguments",
            event_type="TOOL_CALL_REQUESTED",
            payload={
                "tool_call_id": "tool-call-large-arguments",
                "tool_name": "lookup_filing",
                "tool_schema_digest": "sha256:schema",
                "tool_identity_digest": "sha256:identity",
                "normalized_arguments_digest": arguments_digest,
                "arguments_json_size_bytes": 2048,
                "arguments_storage_kind": "payload_descriptor",
                "arguments_inline_json": None,
                "arguments_payload_ref": "payload-tool-call-arguments-large",
                "arguments_payload_digest": arguments_digest,
                "semantic_input_digest": "sha256:semantic",
                "semantic_query_storage_kind": "absent",
                "semantic_query_text": None,
                "semantic_query_payload_ref": None,
                "semantic_query_digest": None,
            },
        )

        _run_trace_once(store.transaction_runner, cold_path)
        cold_lines = _json_lines(cold_path)

        assert len(cold_lines) == 1
        line_text = json.dumps(cold_lines[0], sort_keys=True)
        assert arguments_digest in line_text
        assert "x" * 128 not in line_text


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
        _append_tool_event(
            store.transaction_runner,
            event_id="event-requested",
            event_type="TOOL_CALL_REQUESTED",
            payload={
                "tool_call_id": "tool-call-1",
                "tool_name": "lookup_filing",
                "normalized_arguments_digest": "sha256:args",
            },
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
        event = _append_tool_event(
            store.transaction_runner,
            event_id="event-requested",
            event_type="TOOL_CALL_REQUESTED",
            payload={
                "tool_call_id": "tool-call-1",
                "tool_name": "lookup_filing",
                "normalized_arguments_digest": "sha256:args",
            },
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
