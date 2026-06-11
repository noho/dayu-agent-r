"""Host Tool Trace durable query helper 测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    append_event,
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
)
from dayu.host.durable.transaction import HostTransactionRunner
from dayu.host.tool_trace import (
    ToolTraceSinkOptions,
    catch_up_tool_trace_projection,
)

_FIXED_NOW = datetime(2026, 5, 29, 3, 4, 5, tzinfo=UTC)


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


def test_query_helpers_return_rows_ordered_by_event_sequence(
    tmp_path: Path,
) -> None:
    """run/tool_call/provider/diagnostic 查询按 event_sequence ASC 分页。"""

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
