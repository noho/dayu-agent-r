"""Host Tool Trace durable query helper 测试。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.artifact import LocalArtifactStore
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    append_event,
)
from dayu.host.durable.payload import (
    PayloadStore,
    SQLitePayloadFormat,
    SQLitePayloadWriteRequest,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.tool_trace import (
    RunnerCallReconstructionConsumerBoundary,
    RunnerCallReconstructionDiagnosticReason,
    RunnerCallReconstructionMissingRefKind,
    RunnerCallReconstructionStatus,
    find_tool_trace_by_diagnostic_ref,
    find_tool_trace_by_provider_request_id,
    find_tool_trace_by_tool_call_id,
    read_runner_call_reconstruction_signals_by_run,
    read_tool_trace_by_run,
    resolve_runner_call_projection_from_signal,
    resolve_tool_trace_hot_row_payloads,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.tool_trace import (
    ToolTraceSinkOptions,
    catch_up_tool_trace_projection,
)

_FIXED_NOW = datetime(2026, 5, 29, 3, 4, 5, tzinfo=UTC)
_FIELD_CONTEXT_PRESSURE = "context_pressure"
_FIELD_TOOL_TIMING = "tool_timing"
_FIELD_FAILURE_METADATA = "failure_metadata"
_FIELD_PARTIAL_TOOL_CALL_SIGNAL = "partial_tool_call_signal"
_ALL_SIGNAL_FIELDS: tuple[str, ...] = (
    _FIELD_CONTEXT_PRESSURE,
    _FIELD_TOOL_TIMING,
    _FIELD_FAILURE_METADATA,
    _FIELD_PARTIAL_TOOL_CALL_SIGNAL,
)


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


def _append_event(
    transaction_runner: HostTransactionRunner,
    *,
    event_id: str,
    event_type: str,
    payload: JsonValue,
    run_id: str = "run-1",
    event_class: EventClass = EventClass.CANONICAL_FACT,
) -> None:
    """追加 Tool Trace query 测试 EventLog row。

    :param transaction_runner: Host durable transaction runner。
    :param event_id: EventLog id。
    :param event_type: EventLog type。
    :param payload: inline payload。
    :param run_id: Run id。
    :param event_class: EventLog class。
    :returns: ``None``。
    """

    transaction_runner.run_write(
        lambda transaction: append_event(
            transaction,
            EventLogAppendRequest(
                event_id=event_id,
                event_class=event_class,
                session_id="session-1",
                run_id=run_id,
                attempt_id="attempt-1",
                execution_id="execution-1",
                event_type=event_type,
                occurred_at=_FIXED_NOW,
                actor="host",
                source="unit-test",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason=None,
                payload_json=payload,
                payload_ref=None,
                payload_digest=None,
            ),
        )
    )


def _catch_up(
    transaction_runner: HostTransactionRunner, tmp_path: Path
) -> None:
    """追平测试用 Tool Trace projection。

    :param transaction_runner: Host durable transaction runner。
    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    """

    catch_up_tool_trace_projection(
        transaction_runner,
        options=ToolTraceSinkOptions(
            cold_jsonl_path=tmp_path / "trace" / "cold.jsonl"
        ),
    )


def _write_json_payload(
    transaction: HostTransaction,
    *,
    payload_ref: str,
    payload_id: str,
    payload: Mapping[str, JsonValue],
) -> None:
    """写入测试用 JSON payload descriptor。

    :param transaction: Host transaction。
    :param payload_ref: payload descriptor ref。
    :param payload_id: SQLite payload id。
    :param payload: payload JSON object。
    :returns: ``None``。
    """

    PayloadStore().write_sqlite_payload(
        transaction,
        SQLitePayloadWriteRequest(
            payload_ref=payload_ref,
            payload_id=payload_id,
            payload_format=SQLitePayloadFormat.CANONICAL_JSON,
            payload_json=payload,
            media_type="application/json",
            metadata={},
            expected_digest=sha256_digest_json(payload),
        ),
    )


def _write_json_value_payload(
    transaction: HostTransaction,
    *,
    payload_ref: str,
    payload_id: str,
    payload: JsonValue,
) -> None:
    """写入测试用任意 JSON payload descriptor。

    :param transaction: Host transaction。
    :param payload_ref: payload descriptor ref。
    :param payload_id: SQLite payload id。
    :param payload: payload JSON 值。
    :returns: ``None``。
    """

    PayloadStore().write_sqlite_payload(
        transaction,
        SQLitePayloadWriteRequest(
            payload_ref=payload_ref,
            payload_id=payload_id,
            payload_format=SQLitePayloadFormat.CANONICAL_JSON,
            payload_json=payload,
            media_type="application/json",
            metadata={},
            expected_digest=sha256_digest_json(payload),
        ),
    )


def _write_artifact_json_payload(
    transaction: HostTransaction,
    *,
    payload_ref: str,
    payload: Mapping[str, JsonValue],
) -> None:
    """写入测试用 artifact JSON payload descriptor。

    :param transaction: Host transaction。
    :param payload_ref: payload descriptor ref。
    :param payload: payload JSON object。
    :returns: ``None``。
    """

    payload_bytes = canonical_json_dumps(payload).encode("utf-8")
    artifact_ref = LocalArtifactStore(
        transaction.artifact_root,
        create_artifact_root=transaction.create_artifact_root,
    ).write_artifact_bytes(
        payload_bytes,
        expected_digest=sha256_digest_json(payload),
    )
    PayloadStore().write_payload_descriptor_for_artifact(
        transaction,
        payload_ref,
        artifact_ref,
        "application/json",
        {},
    )


def _json_object(value: JsonValue) -> Mapping[str, JsonValue]:
    """断言 JSON 值是 object。

    :param value: JSON 值。
    :returns: JSON object。
    :raises AssertionError: value 不是 object 时抛出。
    """

    assert isinstance(value, Mapping)
    return value


def _json_object_sequence(value: JsonValue) -> tuple[Mapping[str, JsonValue], ...]:
    """断言 JSON 值是 object 列表。

    :param value: JSON 值。
    :returns: JSON object 元组。
    :raises AssertionError: value 不是 object 列表时抛出。
    """

    assert isinstance(value, list)
    objects: list[Mapping[str, JsonValue]] = []
    for item in value:
        assert isinstance(item, Mapping)
        objects.append(item)
    return tuple(objects)


def _query_signal_objects() -> Mapping[str, JsonValue]:
    """构造 query helper 闭环测试使用的四类 signal object。

    :returns: 以 signal 字段名索引的 JSON object。
    """

    return {
        _FIELD_CONTEXT_PRESSURE: {
            "schema_version": 1,
            "signal_source": "USAGE_REPORTED",
            "status": "observed",
            "input_budget_tokens": 100,
            "soft_threshold_tokens": 45,
            "hard_threshold_tokens": 80,
            "budget_decision": "allow_dispatch",
        },
        _FIELD_TOOL_TIMING: {
            "schema_version": 1,
            "status": "available",
            "started_at": "2026-06-11T00:00:00+00:00",
            "finished_at": "2026-06-11T00:00:01.250000+00:00",
            "duration_ms": 1250,
            "duration_source": "tool_result_meta",
        },
        _FIELD_FAILURE_METADATA: {
            "schema_version": 1,
            "signal_source": "TOOL_RESULT_ACCEPTED",
            "failure_kind": "tool_failed",
            "error_code": "lookup_failed",
            "repair_hint": None,
            "repair_hint_truncated": False,
            "repair_hint_sha256": None,
            "diagnostic_refs": ["diag-signal"],
        },
        _FIELD_PARTIAL_TOOL_CALL_SIGNAL: {
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
                    "arguments_sha256": (
                        "0123456789abcdef0123456789abcdef"
                        "0123456789abcdef0123456789abcdef"
                    ),
                    "arguments_present": True,
                }
            ],
        },
    }


def _assert_trace_summary_signals(
    trace_summary: Mapping[str, JsonValue],
    expected: Mapping[str, JsonValue],
    fields: tuple[str, ...],
) -> None:
    """断言 query helper 返回的 trace_summary 保留指定 signal。

    :param trace_summary: query helper 返回的 hot trace summary。
    :param expected: 期望 signal object 索引。
    :param fields: 需要验证的 signal 字段名。
    :returns: ``None``。
    """

    for field_name in fields:
        assert trace_summary[field_name] == expected[field_name]


def test_query_helpers_return_rows_ordered_by_event_sequence(
    tmp_path: Path,
) -> None:
    """run/tool_call/provider/diagnostic 查询按 event_sequence ASC 分页。"""

    signal_objects = _query_signal_objects()
    with open_host_durable_store(_options(tmp_path)) as store:
        _append_event(
            store.transaction_runner,
            event_id="event-1",
            event_type="TOOL_CALL_REQUESTED",
            payload={
                "tool_call_id": "tool-call-1",
                "tool_name": "lookup_filing",
                "normalized_arguments_digest": "sha256:args-1",
            },
        )
        _append_event(
            store.transaction_runner,
            event_id="event-2",
            event_type="TOOL_RESULT_ACCEPTED",
            payload={
                "tool_call_id": "tool-call-1",
                "tool_name": "lookup_filing",
                "outcome_digest": "sha256:outcome",
                "diagnostic_refs": [{"ref_id": "diag-shared"}],
                _FIELD_CONTEXT_PRESSURE: signal_objects[_FIELD_CONTEXT_PRESSURE],
                _FIELD_TOOL_TIMING: signal_objects[_FIELD_TOOL_TIMING],
                _FIELD_FAILURE_METADATA: signal_objects[_FIELD_FAILURE_METADATA],
            },
        )
        _append_event(
            store.transaction_runner,
            event_id="event-3",
            event_type="RUN_FAILED",
            payload={
                "provider_request_id": "req-terminal",
                "client_correlation_id": "client-terminal",
                "engine_event_ref": "event-engine-terminal",
                "terminal_summary_ref": "summary-ref",
                "terminal_summary_digest": "sha256:summary",
                _FIELD_PARTIAL_TOOL_CALL_SIGNAL: (
                    signal_objects[_FIELD_PARTIAL_TOOL_CALL_SIGNAL]
                ),
            },
        )
        _catch_up(store.transaction_runner, tmp_path)

        by_run = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_by_run(
                transaction, "run-1", after_event_sequence=0, limit=2
            )
        )
        by_run_next = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_by_run(
                transaction,
                "run-1",
                after_event_sequence=by_run.next_event_sequence,
                limit=2,
            )
        )
        by_tool_call = store.transaction_runner.run_read(
            lambda transaction: find_tool_trace_by_tool_call_id(
                transaction, "tool-call-1", after_event_sequence=0, limit=10
            )
        )
        by_provider = store.transaction_runner.run_read(
            lambda transaction: find_tool_trace_by_provider_request_id(
                transaction, "req-terminal", after_event_sequence=0, limit=10
            )
        )
        by_diagnostic = store.transaction_runner.run_read(
            lambda transaction: find_tool_trace_by_diagnostic_ref(
                transaction, "diag-shared", after_event_sequence=0, limit=10
            )
        )

        assert [row.event_id for row in by_run.rows] == ["event-1", "event-2"]
        assert by_run.has_more is True
        assert [row.event_id for row in by_run_next.rows] == ["event-3"]
        assert by_run_next.has_more is False
        assert [row.event_id for row in by_tool_call.rows] == [
            "event-1",
            "event-2",
        ]
        assert [row.event_id for row in by_provider.rows] == ["event-3"]
        assert by_provider.rows[0].provider_request_id == "req-terminal"
        assert (
            by_provider.rows[0].trace_summary["client_correlation_id"]
            == "client-terminal"
        )
        assert [row.event_id for row in by_diagnostic.rows] == ["event-2"]
        _assert_trace_summary_signals(
            by_run.rows[1].trace_summary,
            signal_objects,
            (
                _FIELD_CONTEXT_PRESSURE,
                _FIELD_TOOL_TIMING,
                _FIELD_FAILURE_METADATA,
            ),
        )
        _assert_trace_summary_signals(
            by_tool_call.rows[1].trace_summary,
            signal_objects,
            (
                _FIELD_CONTEXT_PRESSURE,
                _FIELD_TOOL_TIMING,
                _FIELD_FAILURE_METADATA,
            ),
        )
        _assert_trace_summary_signals(
            by_diagnostic.rows[0].trace_summary,
            signal_objects,
            (
                _FIELD_CONTEXT_PRESSURE,
                _FIELD_TOOL_TIMING,
                _FIELD_FAILURE_METADATA,
            ),
        )
        _assert_trace_summary_signals(
            by_run_next.rows[0].trace_summary,
            signal_objects,
            (_FIELD_PARTIAL_TOOL_CALL_SIGNAL,),
        )
        _assert_trace_summary_signals(
            by_provider.rows[0].trace_summary,
            signal_objects,
            (_FIELD_PARTIAL_TOOL_CALL_SIGNAL,),
        )
        assert set(_ALL_SIGNAL_FIELDS) == set(signal_objects)


def test_provider_request_id_terminal_diagnostic_query(
    tmp_path: Path,
) -> None:
    """provider_request_id 可查询 terminal diagnostic chain。"""

    partial_tool_call_signal: JsonValue = {
        "schema_version": 1,
        "signal_source": "PROVIDER_PROTOCOL_ERROR",
        "partial_tool_call_count": 1,
        "summary_status": "present",
        "raw_payload_present": True,
        "partial_tool_calls": [
            {
                "tool_call_index": 0,
                "tool_call_id": "call-bounded",
                "name_fragment": "lookup_filing",
                "arguments_byte_size": 42,
                "arguments_sha256": (
                    "0123456789abcdef0123456789abcdef"
                    "0123456789abcdef0123456789abcdef"
                ),
                "arguments_present": True,
            }
        ],
    }
    with open_host_durable_store(_options(tmp_path)) as store:
        _append_event(
            store.transaction_runner,
            event_id="event-terminal",
            event_type="RUN_FAILED",
            payload={
                "provider_request_id": "req-terminal",
                "client_correlation_id": "client-terminal",
                "engine_event_ref": "event-engine-terminal",
                "error_code": "provider_error",
                "message": "provider failed",
                "terminal_summary_ref": "summary-ref",
                "terminal_summary_digest": "sha256:summary",
            },
        )
        _append_event(
            store.transaction_runner,
            event_id="event-protocol",
            event_type="PROVIDER_PROTOCOL_ERROR",
            event_class=EventClass.DIAGNOSTIC,
            payload={
                "provider_request_id": "req-terminal",
                "client_correlation_id": "client-protocol",
                "raw_payload_ref": "raw-ref",
                "raw_payload_digest": "sha256:raw",
                "error_code": "invalid_stream",
                "partial_tool_call_signal": partial_tool_call_signal,
            },
        )
        _catch_up(store.transaction_runner, tmp_path)

        page = store.transaction_runner.run_read(
            lambda transaction: find_tool_trace_by_provider_request_id(
                transaction, "req-terminal", after_event_sequence=0, limit=10
            )
        )

        assert [row.event_id for row in page.rows] == [
            "event-terminal",
            "event-protocol",
        ]
        assert (
            page.rows[0].trace_summary["engine_event_ref"]
            == "event-engine-terminal"
        )
        assert (
            page.rows[0].trace_summary["client_correlation_id"]
            == "client-terminal"
        )
        assert (
            page.rows[1].trace_summary["client_correlation_id"]
            == "client-protocol"
        )
        assert (
            page.rows[1].trace_summary["partial_tool_call_signal"]
            == partial_tool_call_signal
        )
        assert page.rows[1].diagnostic_ref == "raw-ref"


def test_provider_request_id_query_ignores_client_correlation_fallback(
    tmp_path: Path,
) -> None:
    """provider id 查询不得把 client_correlation_id 当成 provider_request_id。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        _append_event(
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
        _catch_up(store.transaction_runner, tmp_path)

        by_client_id_as_provider = store.transaction_runner.run_read(
            lambda transaction: find_tool_trace_by_provider_request_id(
                transaction,
                "client-fallback",
                after_event_sequence=0,
                limit=10,
            )
        )

        assert by_client_id_as_provider.rows == ()
        assert by_client_id_as_provider.has_more is False


def test_runner_call_reconstruction_signal_query_classifies_statuses(
    tmp_path: Path,
) -> None:
    """runner-call 查询 helper 返回 complete / limited_signal / mismatch typed signal。"""

    manifest_digest = sha256_digest_json({"manifest": "runner-call"})
    role_digest = sha256_digest_json({"roles": ["system", "user"]})
    projection_digest = sha256_digest_json({"projection": "summary"})
    observed_digest = sha256_digest_json({"roles": ["system", "user", "tool"]})
    expected_digest = sha256_digest_json({"roles": ["system", "user"]})
    with open_host_durable_store(_options(tmp_path)) as store:
        _append_event(
            store.transaction_runner,
            event_id="event-runner-call-complete",
            event_type="RUNNER_CALL_INPUT_ASSEMBLED",
            payload={
                "runner_call_index": 0,
                "runner_call_kind": "initial_user_dispatch",
                "runner_call_trigger_reason": "initial_user_input",
                "iteration_id": "iteration-1",
                "manifest_payload_ref": "payload-runner-call-complete",
                "manifest_digest": manifest_digest,
                "validation_status": "complete",
                "message_count": 2,
                "role_sequence_digest": role_digest,
                "input_projection_digest": projection_digest,
                "projector_metadata_summary": [
                    {
                        "projector_metadata_id": "projector:0",
                        "projector_id": "run_input_system_context",
                        "projector_schema_version": "run_input_projector.v1",
                        "projector_digest": sha256_digest_json(
                            {"projector": "system"}
                        ),
                        "purpose": "ordinary_run_input",
                    }
                ],
                "diagnostic": None,
            },
        )
        _append_event(
            store.transaction_runner,
            event_id="event-runner-call-limited",
            event_type="RUNNER_CALL_INPUT_ASSEMBLED",
            payload={
                "runner_call_index": 1,
                "runner_call_kind": "tool_result_continuation",
                "runner_call_trigger_reason": "tool_results_available",
                "manifest_payload_ref": "payload-runner-call-limited",
                "manifest_digest": sha256_digest_json({"manifest": "limited"}),
                "validation_status": "limited_signal",
                "message_count": 3,
                "role_sequence_digest": observed_digest,
                "input_projection_digest": sha256_digest_json(
                    {"projection": "limited"}
                ),
                "projector_metadata_summary": [],
                "diagnostic": {
                    "status": "limited_signal",
                    "reason": "missing_projection_artifact",
                    "missing_atom_kind": None,
                    "missing_ref_kind": "runner_call_projection_artifact",
                    "missing_ref": None,
                    "observed_count": 3,
                    "expected_count": None,
                    "observed_digest": observed_digest,
                    "expected_digest": None,
                    "consumer_boundary": "host.engine_ingest",
                },
            },
        )
        _append_event(
            store.transaction_runner,
            event_id="event-runner-call-mismatch",
            event_type="RUNNER_CALL_INPUT_ASSEMBLED",
            payload={
                "runner_call_index": 2,
                "runner_call_kind": "tool_result_continuation",
                "runner_call_trigger_reason": "tool_results_available",
                "manifest_payload_ref": "payload-runner-call-mismatch",
                "manifest_digest": sha256_digest_json({"manifest": "mismatch"}),
                "validation_status": "mismatch",
                "message_count": 3,
                "role_sequence_digest": observed_digest,
                "input_projection_digest": sha256_digest_json(
                    {"projection": "mismatch"}
                ),
                "projector_metadata_summary": [],
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
        _catch_up(store.transaction_runner, tmp_path)

        page = store.transaction_runner.run_read(
            lambda transaction: read_runner_call_reconstruction_signals_by_run(
                transaction, "run-1", after_event_sequence=0, limit=10
            )
        )

        assert [signal.event_id for signal in page.signals] == [
            "event-runner-call-complete",
            "event-runner-call-limited",
            "event-runner-call-mismatch",
        ]
        assert page.has_more is False
        complete = page.signals[0]
        limited = page.signals[1]
        mismatch = page.signals[2]
        assert complete.diagnostic.status is RunnerCallReconstructionStatus.COMPLETE
        assert complete.manifest_ref == "payload-runner-call-complete"
        assert complete.message_count == 2
        assert complete.projector_metadata_summary[0].projector_id == (
            "run_input_system_context"
        )
        assert limited.diagnostic.status is (
            RunnerCallReconstructionStatus.LIMITED_SIGNAL
        )
        assert limited.diagnostic.reason is (
            RunnerCallReconstructionDiagnosticReason.MISSING_PROJECTION_ARTIFACT
        )
        assert limited.diagnostic.missing_ref_kind is (
            RunnerCallReconstructionMissingRefKind.ARTIFACT_REF
        )
        assert limited.diagnostic.consumer_boundary is (
            RunnerCallReconstructionConsumerBoundary.TOOL_TRACE_QUERY
        )
        assert mismatch.diagnostic.status is RunnerCallReconstructionStatus.MISMATCH
        assert mismatch.diagnostic.reason is (
            RunnerCallReconstructionDiagnosticReason.ROLE_SEQUENCE_DIGEST_MISMATCH
        )
        assert mismatch.diagnostic.observed_digest == observed_digest
        assert mismatch.diagnostic.expected_digest == expected_digest


def test_runner_call_projection_resolver_reads_manifest_projection_and_schema(
    tmp_path: Path,
) -> None:
    """resolver 能从 Tool Trace runner-call signal 恢复明文 input 与 schema。"""

    projection_payload: Mapping[str, JsonValue] = {
        "schema_version": "runner_call_input_projection.v1",
        "messages": [
            {
                "index": 0,
                "role": "system",
                "content": "# 当前时间\n2026-07-07\n# 当前分析对象\nV（Visa Inc.）",
                "content_digest": sha256_digest_json({"content": "system"}),
                "content_size_bytes": 75,
                "source_refs": ["event-input"],
                "projector_metadata_id": "projector:0:system",
            },
            {
                "index": 1,
                "role": "user",
                "content": "分析 Visa",
                "content_digest": sha256_digest_json({"content": "user"}),
                "content_size_bytes": 12,
                "source_refs": ["event-input"],
                "projector_metadata_id": "projector:1:user",
            },
        ],
    }
    schema_payload: Mapping[str, JsonValue] = {
        "schema_version": "selected_tool_schema_snapshot.v1",
        "tool_schemas": [
            {
                "type": "function",
                "function": {
                    "name": "get_current_time",
                    "description": "读取当前时间",
                    "parameters": {
                        "type": "object",
                        "properties": {"timezone": {"type": "string"}},
                        "required": ["timezone"],
                    },
                },
            }
        ],
    }
    projection_digest = sha256_digest_json(projection_payload)
    schema_digest = sha256_digest_json(schema_payload)
    manifest_payload: Mapping[str, JsonValue] = {
        "schema_version": "runner_call_input_manifest.v1",
        "runner_call_projection_artifact_ref": "payload-projection",
        "runner_call_projection_artifact_digest": projection_digest,
        "tool_schema_snapshot_refs": [
            "tool_schema_snapshot_ref:payload-schema",
            "tool_schema_snapshot_digest:" + schema_digest,
        ],
    }
    manifest_digest = sha256_digest_json(manifest_payload)
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: (
                _write_json_payload(
                    transaction,
                    payload_ref="payload-projection",
                    payload_id="sqlite-projection",
                    payload=projection_payload,
                ),
                _write_json_payload(
                    transaction,
                    payload_ref="payload-schema",
                    payload_id="sqlite-schema",
                    payload=schema_payload,
                ),
                _write_json_payload(
                    transaction,
                    payload_ref="payload-manifest",
                    payload_id="sqlite-manifest",
                    payload=manifest_payload,
                ),
            )
        )
        _append_event(
            store.transaction_runner,
            event_id="event-runner-call-resolvable",
            event_type="RUNNER_CALL_INPUT_ASSEMBLED",
            payload={
                "runner_call_index": 0,
                "runner_call_kind": "initial_user_dispatch",
                "runner_call_trigger_reason": "initial_user_input",
                "manifest_payload_ref": "payload-manifest",
                "manifest_digest": manifest_digest,
                "validation_status": "complete",
                "message_count": 2,
                "role_sequence_digest": sha256_digest_json(
                    {"roles": ["system", "user"]}
                ),
                "input_projection_digest": sha256_digest_json(
                    {"projection": "summary"}
                ),
                "projector_metadata_summary": [],
                "runner_call_projection_artifact_ref": "payload-projection",
                "runner_call_projection_artifact_digest": projection_digest,
                "diagnostic": None,
            },
        )
        _catch_up(store.transaction_runner, tmp_path)

        page = store.transaction_runner.run_read(
            lambda transaction: read_runner_call_reconstruction_signals_by_run(
                transaction, "run-1", after_event_sequence=0, limit=10
            )
        )
        resolved = store.transaction_runner.run_read(
            lambda transaction: resolve_runner_call_projection_from_signal(
                transaction, page.signals[0]
            )
        )

        messages = _json_object_sequence(
            resolved.runner_input_projection.payload["messages"]
        )
        assert "# 当前时间" in str(messages[0]["content"])
        assert "V（Visa Inc.）" in str(messages[0]["content"])
        assert resolved.selected_tool_schema_snapshot is not None
        tool_schemas = _json_object_sequence(
            resolved.selected_tool_schema_snapshot.payload["tool_schemas"]
        )
        function = _json_object(tool_schemas[0]["function"])
        assert function["name"] == "get_current_time"


def test_runner_call_projection_resolver_reads_artifact_projection_payload(
    tmp_path: Path,
) -> None:
    """resolver 能读取 artifact_ref 形式的 projection JSON payload。"""

    projection_payload: Mapping[str, JsonValue] = {
        "schema_version": "runner_call_input_projection.v1",
        "messages": [
            {
                "index": 0,
                "role": "user",
                "content": "artifact projection 明文",
                "content_digest": sha256_digest_json({"content": "artifact"}),
            }
        ],
    }
    projection_digest = sha256_digest_json(projection_payload)
    manifest_payload: Mapping[str, JsonValue] = {
        "schema_version": "runner_call_input_manifest.v1",
        "runner_call_projection_artifact_ref": "payload-artifact-projection",
        "runner_call_projection_artifact_digest": projection_digest,
        "tool_schema_snapshot_refs": [],
    }
    manifest_digest = sha256_digest_json(manifest_payload)
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: (
                _write_artifact_json_payload(
                    transaction,
                    payload_ref="payload-artifact-projection",
                    payload=projection_payload,
                ),
                _write_json_payload(
                    transaction,
                    payload_ref="payload-artifact-manifest",
                    payload_id="sqlite-artifact-manifest",
                    payload=manifest_payload,
                ),
            )
        )
        _append_event(
            store.transaction_runner,
            event_id="event-runner-call-artifact-projection",
            event_type="RUNNER_CALL_INPUT_ASSEMBLED",
            payload={
                "runner_call_index": 0,
                "runner_call_kind": "initial_user_dispatch",
                "runner_call_trigger_reason": "initial_user_input",
                "manifest_payload_ref": "payload-artifact-manifest",
                "manifest_digest": manifest_digest,
                "validation_status": "complete",
                "message_count": 1,
                "role_sequence_digest": sha256_digest_json({"roles": ["user"]}),
                "input_projection_digest": sha256_digest_json(
                    {"projection": "artifact"}
                ),
                "projector_metadata_summary": [],
                "runner_call_projection_artifact_ref": (
                    "payload-artifact-projection"
                ),
                "runner_call_projection_artifact_digest": projection_digest,
                "diagnostic": {"status": "complete"},
            },
        )
        _catch_up(store.transaction_runner, tmp_path)

        page = store.transaction_runner.run_read(
            lambda transaction: read_runner_call_reconstruction_signals_by_run(
                transaction, "run-1", after_event_sequence=0, limit=10
            )
        )
        resolved = store.transaction_runner.run_read(
            lambda transaction: resolve_runner_call_projection_from_signal(
                transaction, page.signals[0]
            )
        )

        messages = _json_object_sequence(
            resolved.runner_input_projection.payload["messages"]
        )
        assert messages[0]["content"] == "artifact projection 明文"
        assert resolved.runner_input_projection.payload_ref == (
            "payload-artifact-projection"
        )


def test_runner_call_projection_resolver_fails_closed_for_missing_manifest_ref(
    tmp_path: Path,
) -> None:
    """runner-call signal 缺 manifest ref 时 resolver fail closed。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        _append_event(
            store.transaction_runner,
            event_id="event-runner-call-no-manifest",
            event_type="RUNNER_CALL_INPUT_ASSEMBLED",
            payload={
                "runner_call_index": 0,
                "runner_call_kind": "initial_user_dispatch",
                "runner_call_trigger_reason": "initial_user_input",
                "validation_status": "complete",
                "message_count": 1,
                "role_sequence_digest": sha256_digest_json({"roles": ["user"]}),
                "input_projection_digest": sha256_digest_json(
                    {"projection": "missing-manifest"}
                ),
                "projector_metadata_summary": [],
                "diagnostic": {"status": "complete"},
            },
        )
        _catch_up(store.transaction_runner, tmp_path)

        page = store.transaction_runner.run_read(
            lambda transaction: read_runner_call_reconstruction_signals_by_run(
                transaction, "run-1", after_event_sequence=0, limit=10
            )
        )

        with pytest.raises(HostDurableError, match="no manifest_ref"):
            store.transaction_runner.run_read(
                lambda transaction: resolve_runner_call_projection_from_signal(
                    transaction, page.signals[0]
                )
            )


def test_runner_call_projection_resolver_fails_closed_for_digest_mismatch(
    tmp_path: Path,
) -> None:
    """projection descriptor digest 与 manifest 期望不一致时 resolver fail closed。"""

    projection_payload: Mapping[str, JsonValue] = {"messages": []}
    projection_digest = sha256_digest_json(projection_payload)
    manifest_payload: Mapping[str, JsonValue] = {
        "runner_call_projection_artifact_ref": "payload-projection-mismatch",
        "runner_call_projection_artifact_digest": sha256_digest_json(
            {"projection": "wrong"}
        ),
        "tool_schema_snapshot_refs": [],
    }
    manifest_digest = sha256_digest_json(manifest_payload)
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: (
                _write_json_payload(
                    transaction,
                    payload_ref="payload-projection-mismatch",
                    payload_id="sqlite-projection-mismatch",
                    payload=projection_payload,
                ),
                _write_json_payload(
                    transaction,
                    payload_ref="payload-manifest-mismatch",
                    payload_id="sqlite-manifest-mismatch",
                    payload=manifest_payload,
                ),
            )
        )
        _append_event(
            store.transaction_runner,
            event_id="event-runner-call-digest-mismatch",
            event_type="RUNNER_CALL_INPUT_ASSEMBLED",
            payload={
                "manifest_payload_ref": "payload-manifest-mismatch",
                "manifest_digest": manifest_digest,
                "validation_status": "complete",
                "message_count": 0,
                "role_sequence_digest": sha256_digest_json({"roles": []}),
                "input_projection_digest": sha256_digest_json(
                    {"projection": "digest-mismatch"}
                ),
                "projector_metadata_summary": [],
                "diagnostic": {"status": "complete"},
            },
        )
        _catch_up(store.transaction_runner, tmp_path)
        page = store.transaction_runner.run_read(
            lambda transaction: read_runner_call_reconstruction_signals_by_run(
                transaction, "run-1", after_event_sequence=0, limit=10
            )
        )

        with pytest.raises(HostDurableError, match="descriptor digest mismatch"):
            store.transaction_runner.run_read(
                lambda transaction: resolve_runner_call_projection_from_signal(
                    transaction, page.signals[0]
                )
            )


def test_runner_call_projection_resolver_fails_closed_for_non_object_payload(
    tmp_path: Path,
) -> None:
    """projection payload 不是 JSON object 时 resolver fail closed。"""

    projection_payload: JsonValue = ["not", "object"]
    projection_digest = sha256_digest_json(projection_payload)
    manifest_payload: Mapping[str, JsonValue] = {
        "runner_call_projection_artifact_ref": "payload-projection-list",
        "runner_call_projection_artifact_digest": projection_digest,
        "tool_schema_snapshot_refs": [],
    }
    manifest_digest = sha256_digest_json(manifest_payload)
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: (
                _write_json_value_payload(
                    transaction,
                    payload_ref="payload-projection-list",
                    payload_id="sqlite-projection-list",
                    payload=projection_payload,
                ),
                _write_json_payload(
                    transaction,
                    payload_ref="payload-manifest-list",
                    payload_id="sqlite-manifest-list",
                    payload=manifest_payload,
                ),
            )
        )
        _append_event(
            store.transaction_runner,
            event_id="event-runner-call-non-object",
            event_type="RUNNER_CALL_INPUT_ASSEMBLED",
            payload={
                "manifest_payload_ref": "payload-manifest-list",
                "manifest_digest": manifest_digest,
                "validation_status": "complete",
                "message_count": 0,
                "role_sequence_digest": sha256_digest_json({"roles": []}),
                "input_projection_digest": sha256_digest_json(
                    {"projection": "non-object"}
                ),
                "projector_metadata_summary": [],
                "diagnostic": {"status": "complete"},
            },
        )
        _catch_up(store.transaction_runner, tmp_path)
        page = store.transaction_runner.run_read(
            lambda transaction: read_runner_call_reconstruction_signals_by_run(
                transaction, "run-1", after_event_sequence=0, limit=10
            )
        )

        with pytest.raises(HostDurableError, match="must be object"):
            store.transaction_runner.run_read(
                lambda transaction: resolve_runner_call_projection_from_signal(
                    transaction, page.signals[0]
                )
            )


def test_tool_trace_row_resolver_reads_args_result_and_final_answer(
    tmp_path: Path,
) -> None:
    """row resolver 能读取工具参数、工具结果 payload 与 terminal final answer。"""

    result_payload: Mapping[str, JsonValue] = {
        "llm_facing_payload": {"current_time": "2026-07-07 19:18:11"}
    }
    final_payload: Mapping[str, JsonValue] = {
        "final_answer": "当前时间是 2026年7月7日 19:18:11。"
    }
    result_digest = sha256_digest_json(result_payload)
    final_digest = sha256_digest_json(final_payload)
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: (
                _write_json_payload(
                    transaction,
                    payload_ref="payload-tool-result",
                    payload_id="sqlite-tool-result",
                    payload=result_payload,
                ),
                _write_json_payload(
                    transaction,
                    payload_ref="payload-final",
                    payload_id="sqlite-final",
                    payload=final_payload,
                ),
            )
        )
        _append_event(
            store.transaction_runner,
            event_id="event-tool-call",
            event_type="TOOL_CALL_REQUESTED",
            payload={
                "tool_call_id": "call-time",
                "tool_name": "get_current_time",
                "arguments_inline_json": {"timezone": "Asia/Shanghai"},
                "normalized_arguments_digest": sha256_digest_json(
                    {"arguments": {"timezone": "Asia/Shanghai"}}
                ),
            },
        )
        _append_event(
            store.transaction_runner,
            event_id="event-tool-result",
            event_type="TOOL_RESULT_ACCEPTED",
            payload={
                "tool_call_id": "call-time",
                "tool_name": "get_current_time",
                "payload_ref": {
                    "payload_ref": "payload-tool-result",
                    "payload_digest": result_digest,
                },
                "payload_digest": result_digest,
            },
        )
        _append_event(
            store.transaction_runner,
            event_id="event-run-succeeded",
            event_type="RUN_SUCCEEDED",
            payload={
                "terminal_summary_ref": "payload-final",
                "terminal_summary_digest": final_digest,
            },
        )
        _catch_up(store.transaction_runner, tmp_path)

        page = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_by_run(
                transaction, "run-1", after_event_sequence=0, limit=10
            )
        )
        by_event = {row.event_id: row for row in page.rows}
        resolved_args = store.transaction_runner.run_read(
            lambda transaction: resolve_tool_trace_hot_row_payloads(
                transaction, by_event["event-tool-call"]
            )
        )
        resolved_result = store.transaction_runner.run_read(
            lambda transaction: resolve_tool_trace_hot_row_payloads(
                transaction, by_event["event-tool-result"]
            )
        )
        resolved_final = store.transaction_runner.run_read(
            lambda transaction: resolve_tool_trace_hot_row_payloads(
                transaction, by_event["event-run-succeeded"]
            )
        )

        assert resolved_args.source_event_payload["arguments_inline_json"] == {
            "timezone": "Asia/Shanghai"
        }
        assert resolved_result.descriptor_payload is not None
        assert resolved_result.descriptor_payload.payload == result_payload
        assert resolved_final.descriptor_payload is not None
        assert resolved_final.descriptor_payload.payload == final_payload
