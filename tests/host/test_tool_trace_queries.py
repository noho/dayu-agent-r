"""Host Tool Trace durable query helper 测试。"""

from __future__ import annotations

from dayu.engine.contracts.structured_output import StructuredOutputCapability

from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import pytest
import dayu.host.durable.tool_trace as tool_trace_module

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.engine_events import (
    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION,
    runner_role_sequence_digest,
)
from dayu.engine.contracts.messages import AgentMessageRole, UserMessage
from dayu.engine.contracts.runner_spec import (
    ClientCorrelationPolicy,
    RunnerCallOptions,
    RunnerSpec,
)
from dayu.engine.contracts.runner_identity import (
    ProviderRequestIdAvailability,
    SuccessfulRunnerResponseIdentity,
    build_runner_request_identity,
)
from dayu.host._runner_call_manifest import (
    RunnerCallHotAtoms,
    complete_runner_call_hot_diagnostic,
    parse_runner_call_hot_payload,
    runner_call_hot_diagnostic_from_json,
    runner_call_hot_payload,
)
from dayu.host.durable.artifact import LocalArtifactStore
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    append_event,
    read_run_events_by_types_page,
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
    CompactorResponseDisposition,
    ResolvedCompactorResponseIdentity,
    RunnerCallReconstructionConsumerBoundary,
    RunnerCallReconstructionDiagnosticReason,
    RunnerCallReconstructionMissingRefKind,
    RunnerCallReconstructionSignal,
    RunnerCallReconstructionStatus,
    find_tool_trace_by_diagnostic_ref,
    find_tool_trace_by_provider_request_id,
    find_tool_trace_by_tool_call_id,
    read_runner_call_reconstruction_signals_by_run,
    read_tool_trace_by_run,
    read_tool_trace_page,
    resolve_runner_call_projection_from_signal,
    resolve_tool_trace_hot_row_payloads,
)
from dayu.host.context_events import (
    CONTEXT_COMPACTED,
    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
    CompactorProposalManifestReference,
    build_context_compacted_payload,
    build_context_compaction_attempt_rejected_payload,
)
from dayu.host.compaction import (
    COMPACT_OUTPUT_SCHEMA_V2,
    CompactCandidateV2,
    CompactSessionSummaryV2,
)
from dayu.host.durable.state import (
    AttemptRow,
    DispatchRecordRow,
    DispatchRecordStatus,
    RunRow,
    WorkerKind,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.evidence import (
    AcceptedEvidenceEnvelope,
    AcceptedEvidenceResultRef,
    AcceptedEvidenceToolQuery,
    accepted_evidence_envelope_to_json_value,
)
from dayu.host.api import AttemptDispatchSnapshot, AttemptStatus, RunStatus
from dayu.host.queue_policy import RunQueuePolicy
from dayu.host.run_input import (
    CompactArtifactView,
    CurrentRunFacts,
    DurableRunnerCallManifestRecorder,
    MemorySnapshotView,
    PolicySnapshot,
    RunnerCallManifestRecordInput,
    SessionContinuityView,
    ToolSchemaSnapshot,
)
from dayu.host.tool_trace import (
    ToolTraceSinkOptions,
    catch_up_tool_trace_projection,
)
from dayu.host.tool_call_request import (
    AcceptedToolCallRequestAtomInput,
    ToolCallRequestEventOrigin,
    build_tool_call_requested_event_request,
)
from tests.host.fake_cancellation import ControllableCancellationToken
from tests.host.fake_compaction import accepted_truth_for_candidate

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


class _ManifestTamperKind(StrEnum):
    """Tool Trace full-manifest fail-closed 篡改分类。"""

    INCOMPLETE = "incomplete"
    DANGLING_METADATA_ID = "dangling_metadata_id"
    UNKNOWN_PROJECTOR_ID = "unknown_projector_id"
    UNKNOWN_PURPOSE = "unknown_purpose"
    UNKNOWN_SCHEMA_VERSION = "unknown_schema_version"
    HOT_IDENTITY_MISMATCH = "hot_identity_mismatch"


class _NonAdvancingTerminalPageReader:
    """始终返回同一 full page 的损坏 keyset reader。"""

    def __init__(self, row: EventLogRow) -> None:
        """保存将被重复返回的 canonical row。

        :param row: 第一次查询合法、后续查询不推进的 row。
        :returns: ``None``。
        :raises: 无。
        """

        self._row = row

    def __call__(
        self,
        transaction: HostTransaction,
        *,
        run_id: str,
        event_types: tuple[str, ...],
        after_event_sequence: int,
        limit: int,
    ) -> tuple[EventLogRow, ...]:
        """忽略 cursor 并重复返回同一 row。

        :param transaction: 未使用的 read transaction。
        :param run_id: 未使用的 parent Run id。
        :param event_types: 未使用的 terminal types。
        :param after_event_sequence: 未使用的 keyset cursor。
        :param limit: 未使用的 page size。
        :returns: 单 row full page。
        :raises: 无。
        """

        del transaction, run_id, event_types, after_event_sequence, limit
        return (self._row,)


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
    payload_ref: str | None = None,
    payload_digest: str | None = None,
) -> EventLogRow:
    """追加 Tool Trace query 测试 EventLog row。

    :param transaction_runner: Host durable transaction runner。
    :param event_id: EventLog id。
    :param event_type: EventLog type。
    :param payload: inline payload。
    :param run_id: Run id。
    :param event_class: EventLog class。
    :param payload_ref: 可选 source descriptor ref。
    :param payload_digest: 可选 source descriptor digest。
    :returns: 数据库返回的真实 EventLog row。
    """

    return transaction_runner.run_write(
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
                payload_ref=payload_ref,
                payload_digest=payload_digest,
            ),
        ).row
    )


def _canonical_request_atom(
    *,
    event_id: str,
    tool_call_id: str,
    tool_name: str,
    accepted_arguments: Mapping[str, JsonValue],
) -> AcceptedToolCallRequestAtomInput:
    """构造 identity/digest 同源的 canonical request atom 输入。

    :param event_id: request event id。
    :param tool_call_id: tool call id。
    :param tool_name: 工具名。
    :param accepted_arguments: Host 已接受的精确工具参数。
    :returns: 可交给共享 writer 的 accepted request atom。
    :raises ValueError: 构造的 request atom 字段违反基础约束时抛出。
    """

    return AcceptedToolCallRequestAtomInput(
        session_id="session-1",
        run_id="run-1",
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
        normalized_arguments_digest=sha256_digest_json(
            {"arguments": accepted_arguments}
        ),
        tool_fact_kind="completed",
        accept_idempotency_key=f"accept:{event_id}",
        semantic_input_digest=sha256_digest_json(
            {"semantic_input": f"query fixture {event_id}"}
        ),
        semantic_query_text=f"查询 query fixture {event_id}",
    )


def _append_canonical_tool_request(
    transaction_runner: HostTransactionRunner,
    *,
    event_id: str,
    atom: AcceptedToolCallRequestAtomInput,
) -> EventLogRow:
    """通过共享 writer 追加 canonical ``TOOL_CALL_REQUESTED``。

    :param transaction_runner: Host durable transaction runner。
    :param event_id: request event id。
    :param atom: 已接受的 request atom。
    :returns: 数据库返回的真实 request row。
    :raises ValueError: request atom 基础字段非法时抛出。
    :raises HostDurableError: request atom 或 EventLog 写入失败时抛出。
    """

    return transaction_runner.run_write(
        lambda transaction: append_event(
            transaction,
            build_tool_call_requested_event_request(
                transaction,
                atom=atom,
                event_id=event_id,
                occurred_at=_FIXED_NOW,
                origin=ToolCallRequestEventOrigin.ORDINARY_ACCEPT,
            ),
        ).row
    )


def _append_accepted_tool_result(
    transaction_runner: HostTransactionRunner,
    *,
    event_id: str,
    request: EventLogRow,
    atom: AcceptedToolCallRequestAtomInput,
    additional_payload: Mapping[str, JsonValue],
    raw_tool_outcome: JsonValue,
    result_payload_ref: str | None = None,
    result_payload_digest: str | None = None,
) -> EventLogRow:
    """追加与 canonical request identity/digest 同源的 accepted result。

    :param transaction_runner: Host durable transaction runner。
    :param event_id: result event id。
    :param request: 对应的 canonical request row。
    :param atom: request row 使用的 accepted atom。
    :param additional_payload: signal、诊断或 payload ref 等 result 字段。
    :param raw_tool_outcome: accepted raw tool outcome。
    :param result_payload_ref: 可选 result payload descriptor ref。
    :param result_payload_digest: 可选 result payload descriptor digest。
    :returns: 数据库返回的真实 result row。
    :raises ValueError: envelope 基础字段非法时抛出。
    :raises HostDurableError: envelope 或 EventLog 写入失败时抛出。
    """

    envelope = AcceptedEvidenceEnvelope(
        evidence_id=f"evidence:{event_id}",
        producer_event_ref=event_id,
        tool_name=atom.tool_name,
        tool_call_id=atom.tool_call_id,
        tool_query=AcceptedEvidenceToolQuery(
            tool_call_requested_event_ref=request.event_id,
            normalized_arguments_digest=atom.normalized_arguments_digest,
            semantic_input_digest=atom.semantic_input_digest,
        ),
        result_ref=AcceptedEvidenceResultRef(
            payload_ref=result_payload_ref,
            payload_digest=result_payload_digest,
            outcome_digest=sha256_digest_json(raw_tool_outcome),
            truncation_applied=False,
        ),
        source_refs=(),
        locator_refs=(),
    )
    payload: dict[str, JsonValue] = dict(additional_payload)
    payload.update(
        {
            "tool_call_id": atom.tool_call_id,
            "tool_name": atom.tool_name,
            "normalized_arguments_digest": atom.normalized_arguments_digest,
            "semantic_input_digest": atom.semantic_input_digest,
            "outcome_digest": sha256_digest_json(raw_tool_outcome),
            "accepted_evidence_envelope": (
                accepted_evidence_envelope_to_json_value(envelope)
            ),
            "raw_tool_outcome": raw_tool_outcome,
        }
    )
    return _append_event(
        transaction_runner,
        event_id=event_id,
        event_type="TOOL_RESULT_ACCEPTED",
        payload=payload,
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


def _projector_metadata(
    *,
    metadata_id: str,
    projector_id: str,
    purpose: str,
) -> Mapping[str, JsonValue]:
    """构造 Tool Trace query 测试用六字段 projector metadata。

    :param metadata_id: projector metadata id。
    :param projector_id: projector id。
    :param purpose: projector purpose。
    :returns: 完整六字段 projector metadata JSON object。
    :raises TypeError: 无主动抛出。
    """

    source_contract_refs: list[JsonValue] = ["contract:test-runner-call"]
    schema_version = "run_input_projector.v1"
    return {
        "projector_metadata_id": metadata_id,
        "projector_id": projector_id,
        "projector_schema_version": schema_version,
        "projector_digest": sha256_digest_json(
            {
                "projector_id": projector_id,
                "projector_schema_version": schema_version,
                "purpose": purpose,
                "source_contract_refs": source_contract_refs,
            }
        ),
        "purpose": purpose,
        "source_contract_refs": source_contract_refs,
    }


def _full_runner_call_manifest(
    *,
    manifest_id: str,
    runner_call_index: int,
    runner_call_kind: str,
    runner_call_trigger_reason: str,
    roles: tuple[str, ...],
    message_count: int | None = None,
    role_sequence_digest: str | None = None,
    iteration_id: str | None = None,
    iteration_index: int | None = None,
    projection_ref: str | None = None,
    projection_digest: str | None = None,
    projection_size_bytes: int | None = None,
    diagnostic: Mapping[str, JsonValue] | None = None,
    compactor_identity: Mapping[str, JsonValue] | None = None,
) -> Mapping[str, JsonValue]:
    """构造覆盖完整字段与 metadata graph 的 runner-call manifest。

    :param manifest_id: manifest logical id。
    :param runner_call_index: runner-call 顺序。
    :param runner_call_kind: runner-call kind。
    :param runner_call_trigger_reason: runner-call trigger reason。
    :param roles: 实际 message entry roles。
    :param message_count: manifest message_count；省略时等于 ``roles`` 数量。
    :param role_sequence_digest: role digest；省略时从 ``roles`` 计算。
    :param iteration_id: 可选 iteration id。
    :param iteration_index: 可选 iteration index。
    :param projection_ref: 可选 input projection ref。
    :param projection_digest: 可选 input projection digest。
    :param projection_size_bytes: 可选 input projection size。
    :param diagnostic: 非 complete manifest diagnostic；complete 时为 ``None``。
    :param compactor_identity: compactor proposal 的完整 typed identity JSON。
    :returns: full runner-call manifest JSON object。
    :raises AssertionError: projection descriptor 只提供一部分时抛出。
    """

    projection_values = (projection_ref, projection_digest, projection_size_bytes)
    assert all(value is None for value in projection_values) or all(
        value is not None for value in projection_values
    )
    purpose = "ordinary_run_input"
    if runner_call_kind == "tool_result_continuation":
        purpose = "tool_continuation_input"
    elif runner_call_kind == "compactor_proposal":
        purpose = "compactor_proposal_input"
    projector_ids = {
        "system": "run_input_system_context",
        "user": "user_input_message",
        "assistant": "assistant_history_message",
        "tool": "tool_result_message",
    }
    if runner_call_kind == "compactor_proposal":
        projector_ids = {
            **projector_ids,
            "system": "compactor_system_prompt",
            "user": "compactor_user_prompt",
        }
    metadata: list[JsonValue] = []
    message_entries: list[JsonValue] = []
    for index, role in enumerate(roles):
        metadata_id = f"projector:{index}:{role}"
        metadata.append(
            _projector_metadata(
                metadata_id=metadata_id,
                projector_id=projector_ids[role],
                purpose=purpose,
            )
        )
        message_entries.append(
            {
                "index": index,
                "role": role,
                "content_digest": sha256_digest_json(
                    {"manifest_id": manifest_id, "message_index": index}
                ),
                "content_size_bytes": index + 1,
                "source_refs": [f"event:source:{manifest_id}:{index}"],
                "projection_artifact_ref": projection_ref,
                "projection_artifact_digest": projection_digest,
                "projector_metadata_id": metadata_id,
                "provider_tool_calls_digest": None,
                "reasoning_content_digest": None,
            }
        )
    actual_message_count = len(roles) if message_count is None else message_count
    actual_role_digest = (
        runner_role_sequence_digest(roles)
        if role_sequence_digest is None
        else role_sequence_digest
    )
    return {
        "schema_version": "runner_call_input_manifest.v2",
        "manifest_id": manifest_id,
        "session_id": "session-1",
        "host_run_id": "run-1",
        "attempt_id": "attempt-1",
        "execution_id": "execution-1",
        "runner_call_index": runner_call_index,
        "runner_call_kind": runner_call_kind,
        "runner_call_trigger_reason": runner_call_trigger_reason,
        "iteration_id": iteration_id,
        "iteration_index": iteration_index,
        "message_count": actual_message_count,
        "role_sequence_digest": actual_role_digest,
        "runner_input_serializer_schema_version": (
            RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
        ),
        "input_projection_digest": sha256_digest_json(
            {"manifest_id": manifest_id, "message_count": actual_message_count}
        ),
        "runner_call_projection_artifact_ref": projection_ref,
        "runner_call_projection_artifact_digest": projection_digest,
        "runner_call_projection_artifact_size_bytes": projection_size_bytes,
        "message_entries": message_entries,
        "source_cursor_refs": [f"event:{manifest_id}"],
        "tool_schema_snapshot_refs": [],
        "memory_snapshot_cursor_ref": None,
        "compact_artifact_refs": [],
        "context_fallback_decision_ref": None,
        "projector_metadata": metadata,
        "compactor_identity": compactor_identity,
        "sizing_snapshot": {
            "status": "unavailable",
            "reason": "context_policy_unavailable",
            "sizing_stage": "ordinary",
            "estimator_id": None,
            "estimator_version": None,
            "estimator_digest": None,
            "conservative_input_tokens": None,
            "context_window_size": None,
            "provider": None,
            "model": None,
            "request_semantics_digest": None,
            "input_snapshot_digest": None,
            "policy_ref": None,
            "policy_snapshot_digest": None,
        },
        "diagnostic": diagnostic,
    }


def _hot_payload_for_manifest(
    manifest: Mapping[str, JsonValue],
    *,
    manifest_ref: str,
) -> Mapping[str, JsonValue]:
    """通过 shared producer owner 构造同源 hot payload。

    :param manifest: full runner-call manifest。
    :param manifest_ref: manifest descriptor ref。
    :returns: exact fixed-shape hot payload。
    :raises AssertionError: 测试 manifest 字段类型不符合 fixture contract 时抛出。
    :raises HostDurableError: production owner 拒绝 manifest 时抛出。
    """

    diagnostic_value = manifest["diagnostic"]
    message_count = manifest["message_count"]
    role_digest = manifest["role_sequence_digest"]
    assert isinstance(message_count, int) and not isinstance(message_count, bool)
    assert isinstance(role_digest, str)
    if diagnostic_value is None:
        validation_status = "complete"
        diagnostic = complete_runner_call_hot_diagnostic(
            status=validation_status,
            message_count=message_count,
            role_sequence_digest=role_digest,
            consumer_boundary="test.tool_trace_query",
        )
    else:
        assert isinstance(diagnostic_value, Mapping)
        diagnostic = runner_call_hot_diagnostic_from_json(diagnostic_value)
        validation_status = diagnostic.status
    projection_ref = manifest["runner_call_projection_artifact_ref"]
    projection_digest = manifest["runner_call_projection_artifact_digest"]
    projection_size = manifest["runner_call_projection_artifact_size_bytes"]
    assert projection_ref is None or isinstance(projection_ref, str)
    assert projection_digest is None or isinstance(projection_digest, str)
    assert projection_size is None or (
        isinstance(projection_size, int) and not isinstance(projection_size, bool)
    )
    return runner_call_hot_payload(
        RunnerCallHotAtoms(
            session_id="session-1",
            host_run_id="run-1",
            attempt_id="attempt-1",
            execution_id="execution-1",
            runner_call_index=_manifest_test_int(manifest, "runner_call_index"),
            runner_call_kind=_manifest_test_text(manifest, "runner_call_kind"),
            runner_call_trigger_reason=_manifest_test_text(
                manifest,
                "runner_call_trigger_reason",
            ),
            iteration_id=_manifest_test_optional_text(manifest, "iteration_id"),
            iteration_index=_manifest_test_optional_int(
                manifest,
                "iteration_index",
            ),
            manifest_payload_ref=manifest_ref,
            manifest_digest=sha256_digest_json(manifest),
            manifest_schema_version=_manifest_test_text(
                manifest,
                "schema_version",
            ),
            validation_status=validation_status,
            message_count=message_count,
            role_sequence_digest=role_digest,
            input_projection_digest=_manifest_test_text(
                manifest,
                "input_projection_digest",
            ),
            runner_call_projection_artifact_ref=projection_ref,
            runner_call_projection_artifact_digest=projection_digest,
            runner_call_projection_artifact_size_bytes=projection_size,
            diagnostic=diagnostic,
        ),
        manifest=manifest,
    )


def _record_compactor_runner_call(
    transaction_runner: HostTransactionRunner,
    tmp_path: Path,
    *,
    operation_id: str = "operation-1",
    attempt_number: int = 1,
    compactor_engine_run_id: str = "compactor-engine-run-1",
) -> tuple[RunnerCallReconstructionSignal, str, str]:
    """写入可由 production resolver 解析的 compactor runner-call signal。

    :param transaction_runner: Host durable transaction runner。
    :param tmp_path: pytest 临时目录。
    :param operation_id: compaction operation id。
    :param attempt_number: proposal attempt 序号。
    :param compactor_engine_run_id: compactor Engine run id。
    :returns: ``(signal, manifest_ref, manifest_digest)``。
    :raises HostDurableError: production manifest/query owner 拒绝 fixture 时抛出。
    """

    projection_payload: Mapping[str, JsonValue] = {
        "schema_version": "runner_call_input_projection.v1",
        "messages": [],
    }
    projection_ref = f"payload-projection:{operation_id}:{attempt_number}"
    projection_digest = sha256_digest_json(projection_payload)
    manifest_ref = f"payload-manifest:{operation_id}:{attempt_number}"
    manifest_value = dict(
        _full_runner_call_manifest(
            manifest_id=f"manifest:{operation_id}:{attempt_number}",
            runner_call_index=attempt_number - 1,
            runner_call_kind="compactor_proposal",
            runner_call_trigger_reason="context_compaction_initial_proposal",
            roles=(),
            projection_ref=projection_ref,
            projection_digest=projection_digest,
            projection_size_bytes=len(
                canonical_json_dumps(projection_payload).encode("utf-8")
            ),
            compactor_identity={
                "parent_host_run_id": "run-1",
                "parent_session_id": "session-1",
                "compaction_operation_id": operation_id,
                "compactor_engine_run_id": compactor_engine_run_id,
                "compaction_attempt_number": attempt_number,
                "compaction_request_digest": sha256_digest_json(
                    {
                        "operation_id": operation_id,
                        "attempt_number": attempt_number,
                    }
                ),
                "compactor_input_projection_ref": projection_ref,
            },
        )
    )
    manifest_value["sizing_snapshot"] = {
        "status": "not_applicable",
        "reason": None,
        "sizing_stage": None,
        "estimator_id": None,
        "estimator_version": None,
        "estimator_digest": None,
        "conservative_input_tokens": None,
        "context_window_size": None,
        "provider": None,
        "model": None,
        "request_semantics_digest": None,
        "input_snapshot_digest": None,
        "policy_ref": None,
        "policy_snapshot_digest": None,
    }
    manifest: Mapping[str, JsonValue] = manifest_value
    manifest_digest = sha256_digest_json(manifest)
    transaction_runner.run_write(
        lambda transaction: (
            _write_json_payload(
                transaction,
                payload_ref=projection_ref,
                payload_id=f"sqlite-projection:{operation_id}:{attempt_number}",
                payload=projection_payload,
            ),
            _write_json_payload(
                transaction,
                payload_ref=manifest_ref,
                payload_id=f"sqlite-manifest:{operation_id}:{attempt_number}",
                payload=manifest,
            ),
        )
    )
    event_id = f"event-runner-call:{operation_id}:{attempt_number}"
    _append_event(
        transaction_runner,
        event_id=event_id,
        event_type="RUNNER_CALL_INPUT_ASSEMBLED",
        payload=_hot_payload_for_manifest(manifest, manifest_ref=manifest_ref),
        payload_ref=manifest_ref,
        payload_digest=manifest_digest,
    )
    _catch_up(transaction_runner, tmp_path)
    page = transaction_runner.run_read(
        lambda transaction: read_runner_call_reconstruction_signals_by_run(
            transaction,
            "run-1",
            after_event_sequence=0,
            limit=10,
        )
    )
    signal = next(item for item in page.signals if item.event_id == event_id)
    return signal, manifest_ref, manifest_digest


def _successful_compactor_response_identity(
    compactor_engine_run_id: str,
    *,
    provider_request_id: str | None = "provider-request-actual",
) -> SuccessfulRunnerResponseIdentity:
    """构造 actual provider/model/request identity 测试事实。

    :param compactor_engine_run_id: manifest 绑定的 compactor Engine run id。
    :param provider_request_id: provider-native request id；``None`` 表示不可用。
    :returns: strict successful response identity。
    :raises ValueError: typed identity 字段非法时抛出。
    """

    return SuccessfulRunnerResponseIdentity(
        effective_provider="provider-actual",
        effective_model="model-actual",
        runner_request_identity=build_runner_request_identity(
            run_id=compactor_engine_run_id,
            attempt_id=None,
            execution_id=None,
            iteration_id="iteration-final",
            iteration_index=1,
            runner_call_index=2,
        ),
        provider_request_id_availability=(
            ProviderRequestIdAvailability.UNAVAILABLE
            if provider_request_id is None
            else ProviderRequestIdAvailability.PRESENT
        ),
        provider_request_id=provider_request_id,
    )


def _proposal_manifest_reference(
    *,
    operation_id: str,
    attempt_number: int,
    compactor_engine_run_id: str,
    manifest_ref: str,
    manifest_digest: str,
) -> CompactorProposalManifestReference:
    """构造与 resolver fixture exact binding 的 manifest reference。

    :param operation_id: compaction operation id。
    :param attempt_number: proposal attempt 序号。
    :param compactor_engine_run_id: compactor Engine run id。
    :param manifest_ref: manifest descriptor ref。
    :param manifest_digest: manifest body digest。
    :returns: canonical event builder 所需 typed reference。
    :raises ValueError: typed reference 字段非法时抛出。
    """

    return CompactorProposalManifestReference(
        manifest_event_id=f"event-runner-call:{operation_id}:{attempt_number}",
        manifest_payload_ref=manifest_ref,
        manifest_digest=manifest_digest,
        compactor_input_projection_ref=(
            f"payload-projection:{operation_id}:{attempt_number}"
        ),
        compactor_input_projection_digest=sha256_digest_json(
            {"schema_version": "runner_call_input_projection.v1", "messages": []}
        ),
        compaction_operation_id=operation_id,
        compaction_attempt_number=attempt_number,
        compactor_engine_run_id=compactor_engine_run_id,
    )


def _accepted_compactor_payload(
    *,
    operation_id: str,
    attempt_number: int,
    compactor_engine_run_id: str,
    manifest_ref: str,
    manifest_digest: str,
) -> Mapping[str, JsonValue]:
    """通过 production owners 构造 accepted compact terminal payload。

    :param operation_id: compaction operation id。
    :param attempt_number: proposal attempt 序号。
    :param compactor_engine_run_id: compactor Engine run id。
    :param manifest_ref: proposal manifest ref。
    :param manifest_digest: proposal manifest digest。
    :returns: strict ``CONTEXT_COMPACTED`` payload。
    :raises RuntimeError: candidate 无法通过 production governance 时抛出。
    """

    candidate = CompactCandidateV2(
        schema=COMPACT_OUTPUT_SCHEMA_V2,
        session_summary=CompactSessionSummaryV2(
            text="Accepted compactor summary.",
            source_labels=("T1",),
        ),
        evidence_facts=(),
        answer_anchors=(),
        forward_intents=(),
        reference_continuity=(),
        diagnostics=(),
        explicitly_dropped_sources=(),
    )
    return build_context_compacted_payload(
        operation_id=operation_id,
        accepted_attempt_number=attempt_number,
        compact_artifact_ref=f"compact-artifact:{operation_id}",
        compact_artifact_digest=sha256_digest_json(
            {"compact_artifact": operation_id}
        ),
        accepted_truth=accepted_truth_for_candidate(
            candidate,
            current_input_ref="event-current-input",
            source_refs_by_label={"T1": ("event-trace-source",)},
        ),
        budget_after_compact=128,
        prompt_local_label_mapping_refs=("prompt-label:T1",),
        accepted_evidence_mapping_refs=(),
        projection_signal="conversation_memory_projection_catchup",
        successful_response_identity=_successful_compactor_response_identity(
            compactor_engine_run_id
        ),
        accepted_proposal_manifest_reference=_proposal_manifest_reference(
            operation_id=operation_id,
            attempt_number=attempt_number,
            compactor_engine_run_id=compactor_engine_run_id,
            manifest_ref=manifest_ref,
            manifest_digest=manifest_digest,
        ),
    )


def _manifest_test_text(
    manifest: Mapping[str, JsonValue],
    field_name: str,
) -> str:
    """读取测试 manifest 的必填文本。

    :param manifest: 测试 manifest。
    :param field_name: 字段名。
    :returns: 文本值。
    :raises AssertionError: 字段不是文本时抛出。
    """

    value = manifest[field_name]
    assert isinstance(value, str)
    return value


def _manifest_test_optional_text(
    manifest: Mapping[str, JsonValue],
    field_name: str,
) -> str | None:
    """读取测试 manifest 的可选文本。

    :param manifest: 测试 manifest。
    :param field_name: 字段名。
    :returns: 文本或 ``None``。
    :raises AssertionError: 非空值不是文本时抛出。
    """

    value = manifest[field_name]
    assert value is None or isinstance(value, str)
    return value


def _manifest_test_int(
    manifest: Mapping[str, JsonValue],
    field_name: str,
) -> int:
    """读取测试 manifest 的必填整数。

    :param manifest: 测试 manifest。
    :param field_name: 字段名。
    :returns: 整数值。
    :raises AssertionError: 字段不是严格整数时抛出。
    """

    value = manifest[field_name]
    assert isinstance(value, int) and not isinstance(value, bool)
    return value


def _manifest_test_optional_int(
    manifest: Mapping[str, JsonValue],
    field_name: str,
) -> int | None:
    """读取测试 manifest 的可选整数。

    :param manifest: 测试 manifest。
    :param field_name: 字段名。
    :returns: 整数或 ``None``。
    :raises AssertionError: 非空值不是严格整数时抛出。
    """

    value = manifest[field_name]
    assert value is None or (
        isinstance(value, int) and not isinstance(value, bool)
    )
    return value


def _record_real_ordinary_runner_call_manifest(
    transaction_runner: HostTransactionRunner,
    *,
    message_count: int,
) -> None:
    """通过 ordinary production recorder 写入真实 full manifest 与 hot event。

    :param transaction_runner: Host durable transaction runner。
    :param message_count: 实际交给 producer 的 message 数量。
    :returns: ``None``。
    :raises HostDurableError: production manifest owner 拒绝输入时抛出。
    """

    now = "2026-05-29T03:04:05.000000Z"
    run = RunRow(
        run_id="run-1",
        session_id="session-1",
        status=RunStatus.RUNNING,
        client_request_id="request-runner-call-real",
        input_event_id="event-input-real",
        input_event_sequence=1,
        accepted_event_id="event-run-accepted-real",
        accepted_event_sequence=2,
        queued_event_id=None,
        queued_event_sequence=None,
        started_event_id="event-run-started-real",
        started_event_sequence=3,
        terminal_event_id=None,
        terminal_event_sequence=None,
        cancel_request_event_id=None,
        current_attempt_id="attempt-1",
        source_run_id=None,
        source_run_relation=None,
        execution_target="local-default",
        queue_policy=RunQueuePolicy.QUEUE,
        created_at=now,
        updated_at=now,
        terminal_at=None,
    )
    attempt = AttemptRow(
        attempt_id="attempt-1",
        run_id=run.run_id,
        execution_id="execution-1",
        status=AttemptStatus.STARTING,
        started_event_id="event-attempt-started-real",
        started_event_sequence=4,
        terminal_event_id=None,
        terminal_event_sequence=None,
        created_at=now,
        updated_at=now,
        terminal_at=None,
    )
    dispatch_record = DispatchRecordRow(
        dispatch_record_id="dispatch-runner-call-real",
        run_id=run.run_id,
        attempt_id=attempt.attempt_id,
        execution_id=attempt.execution_id,
        status=DispatchRecordStatus.PENDING,
        worker_kind=WorkerKind.LOCAL,
        execution_target=run.execution_target,
        owner_host_instance_id=None,
        created_event_id="event-dispatch-created-real",
        created_event_sequence=5,
        waiting_for_lane_at=None,
        lane_name=None,
        lane_claim_id=None,
        lane_owner_id=None,
        lane_acquired_at=None,
        dispatching_at=None,
        worker_accepted_at=None,
        worker_accept_event_id=None,
        worker_accept_event_sequence=None,
        cancelled_event_id=None,
        cancelled_event_sequence=None,
        created_at=now,
        updated_at=now,
        cancelled_at=None,
    )
    current_facts = CurrentRunFacts(
        run=run,
        attempt=attempt,
        dispatch_record=dispatch_record,
        user_input_event=_runner_call_source_event(
            event_id=run.input_event_id,
            event_type="USER_INPUT_ACCEPTED",
            payload={"display_text": "real producer input"},
        ),
        run_accepted_event=_runner_call_source_event(
            event_id=run.accepted_event_id,
            event_type="RUN_ACCEPTED",
            payload={},
        ),
        run_started_event=_runner_call_source_event(
            event_id="event-run-started-real",
            event_type="RUN_STARTED",
            payload={"start_reason": "initial"},
        ),
        user_prompt="real producer input",
        system_prompt=None,
        operation_kind="prompt",
    )
    token = ControllableCancellationToken()
    attempt_snapshot = AttemptDispatchSnapshot(
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=attempt.attempt_id,
        execution_id=attempt.execution_id,
        dispatch_record_id=dispatch_record.dispatch_record_id,
        execution_target=run.execution_target,
        policy_snapshot_ref="policy:runner-call-real",
        cancellation_token=token,
    )
    policy_snapshot = PolicySnapshot(
        runner_spec=RunnerSpec(
            provider="test",
            model="test-model",
            endpoint="https://example.invalid/v1",
            api_key_ref="test-key",
            headers={},
            client_correlation_policy=ClientCorrelationPolicy.DISABLED,
            supports_tool_calling=False,
            supports_streaming=False,
            supports_stream_usage=False,
            structured_output_capability=StructuredOutputCapability.NONE,
            default_timeout_seconds=30.0,
            max_retries=0,
            provider_request=None,
        ),
        runner_options=RunnerCallOptions(
            temperature=None,
            max_tokens=None,
            top_p=None,
            stream=False,
        ),
        agent_policy=AgentPolicy(
            max_iterations=1,
            continuation_max_attempts=0,
            allow_tool_calls=False,
            tool_execution_timeout_seconds=1.0,
            fallback_prompt="test fallback prompt",
            continuation_prompt="test continuation prompt",
        ),
        policy_snapshot_ref="policy:runner-call-real",
    )
    messages = tuple(
        UserMessage(
            role=AgentMessageRole.USER,
            content=f"real producer message {index}",
        )
        for index in range(message_count)
    )
    DurableRunnerCallManifestRecorder(transaction_runner).record_runner_call_manifest(
        RunnerCallManifestRecordInput(
            attempt_snapshot=attempt_snapshot,
            current_facts=current_facts,
            policy_snapshot=policy_snapshot,
            memory=MemorySnapshotView(
                messages=(),
                memory_snapshot_cursor=None,
                policy_digest=None,
                diagnostics=(),
            ),
            compact=CompactArtifactView(
                compaction_event_ref=None,
                compact_artifact_ref=None,
                compact_artifact_digest=None,
            ),
        continuity=SessionContinuityView(
            messages=(),
            source_refs=(),
        ),
            tool_snapshot=ToolSchemaSnapshot(
                tool_schemas=(),
                disable_tools=True,
                tool_runtime_handle=None,
            ),
            messages=messages,
            fallback=None,
        )
    )


def _runner_call_source_event(
    *,
    event_id: str,
    event_type: str,
    payload: Mapping[str, JsonValue],
) -> EventLogRow:
    """构造 ordinary producer 只读 source fact。

    :param event_id: source event id。
    :param event_type: source event type。
    :param payload: source event payload。
    :returns: typed EventLog row。
    :raises: 无。
    """

    now = "2026-05-29T03:04:05.000000Z"
    return EventLogRow(
        event_sequence=1,
        event_id=event_id,
        event_body_digest=sha256_digest_json(
            {"event_id": event_id, "event_type": event_type}
        ),
        event_class=EventClass.CANONICAL_FACT,
        session_id="session-1",
        run_id="run-1",
        attempt_id="attempt-1",
        execution_id="execution-1",
        event_type=event_type,
        occurred_at=now,
        actor="test",
        source="test.tool_trace_queries",
        client_request_id=None,
        idempotency_key=None,
        policy_decision_json=None,
        reason_json=None,
        payload_json=canonical_json_dumps(payload),
        payload_ref=None,
        payload_digest=None,
        appended_at=now,
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
    """run/tool_call/provider/diagnostic 查询按 event_sequence ASC 分页。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: canonical request/result 未按真实 sequence 查询时抛出。
    """

    signal_objects = _query_signal_objects()
    with open_host_durable_store(_options(tmp_path)) as store:
        atom = _canonical_request_atom(
            event_id="event-1",
            tool_call_id="tool-call-1",
            tool_name="lookup_filing",
            accepted_arguments={"ticker": "AAPL"},
        )
        request = _append_canonical_tool_request(
            store.transaction_runner,
            event_id="event-1",
            atom=atom,
        )
        _append_accepted_tool_result(
            store.transaction_runner,
            event_id="event-2",
            request=request,
            atom=atom,
            additional_payload={
                "diagnostic_refs": [{"ref_id": "diag-shared"}],
                _FIELD_CONTEXT_PRESSURE: signal_objects[_FIELD_CONTEXT_PRESSURE],
                _FIELD_TOOL_TIMING: signal_objects[_FIELD_TOOL_TIMING],
                _FIELD_FAILURE_METADATA: signal_objects[_FIELD_FAILURE_METADATA],
            },
            raw_tool_outcome={"kind": "completed", "result": {"status": "ok"}},
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
                _FIELD_PARTIAL_TOOL_CALL_SIGNAL: (signal_objects[_FIELD_PARTIAL_TOOL_CALL_SIGNAL]),
            },
        )
        _catch_up(store.transaction_runner, tmp_path)

        by_run = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_by_run(transaction, "run-1", after_event_sequence=0, limit=2)
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
        unfiltered = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_page(
                transaction,
                after_event_sequence=0,
                limit=2,
            )
        )
        unfiltered_next = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_page(
                transaction,
                after_event_sequence=unfiltered.next_event_sequence,
                limit=2,
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
        assert by_provider.rows[0].trace_summary["client_correlation_id"] == "client-terminal"
        assert [row.event_id for row in by_diagnostic.rows] == ["event-2"]
        assert [row.event_id for row in unfiltered.rows] == [
            "event-1",
            "event-2",
        ]
        assert unfiltered.has_more is True
        assert [row.event_id for row in unfiltered_next.rows] == ["event-3"]
        assert unfiltered_next.has_more is False
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

    role_digest = runner_role_sequence_digest(("system", "user"))
    projection_digest = sha256_digest_json({"projection": "summary"})
    observed_digest = runner_role_sequence_digest(("system", "user", "tool"))
    expected_digest = role_digest
    complete_manifest = _full_runner_call_manifest(
        manifest_id="runner-call-manifest:complete",
        runner_call_index=0,
        runner_call_kind="initial_user_dispatch",
        runner_call_trigger_reason="initial_user_input",
        roles=("system", "user"),
        projection_ref="payload-runner-call-projection-complete",
        projection_digest=projection_digest,
        projection_size_bytes=128,
    )
    limited_diagnostic: Mapping[str, JsonValue] = {
        "status": "limited_signal",
        "reason": "missing_projection_artifact",
        "missing_atom_kind": None,
        "missing_ref_kind": "artifact_ref",
        "missing_ref": None,
        "observed_count": 3,
        "expected_count": None,
        "observed_digest": observed_digest,
        "expected_digest": None,
        "consumer_boundary": "host.engine_ingest",
    }
    limited_manifest = _full_runner_call_manifest(
        manifest_id="runner-call-manifest:limited",
        runner_call_index=1,
        runner_call_kind="tool_result_continuation",
        runner_call_trigger_reason="tool_results_available",
        roles=(),
        message_count=3,
        role_sequence_digest=observed_digest,
        iteration_id="iteration-2",
        iteration_index=1,
        diagnostic=limited_diagnostic,
    )
    mismatch_diagnostic: Mapping[str, JsonValue] = {
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
    }
    mismatch_manifest = _full_runner_call_manifest(
        manifest_id="runner-call-manifest:mismatch",
        runner_call_index=2,
        runner_call_kind="tool_result_continuation",
        runner_call_trigger_reason="tool_results_available",
        roles=("system", "user", "tool"),
        iteration_id="iteration-3",
        iteration_index=2,
        diagnostic=mismatch_diagnostic,
    )
    complete_hot = _hot_payload_for_manifest(
        complete_manifest,
        manifest_ref="payload-runner-call-complete",
    )
    limited_hot = _hot_payload_for_manifest(
        limited_manifest,
        manifest_ref="payload-runner-call-limited",
    )
    mismatch_hot = _hot_payload_for_manifest(
        mismatch_manifest,
        manifest_ref="payload-runner-call-mismatch",
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: (
                _write_json_payload(
                    transaction,
                    payload_ref="payload-runner-call-complete",
                    payload_id="sqlite-runner-call-complete",
                    payload=complete_manifest,
                ),
                _write_json_payload(
                    transaction,
                    payload_ref="payload-runner-call-limited",
                    payload_id="sqlite-runner-call-limited",
                    payload=limited_manifest,
                ),
                _write_json_payload(
                    transaction,
                    payload_ref="payload-runner-call-mismatch",
                    payload_id="sqlite-runner-call-mismatch",
                    payload=mismatch_manifest,
                ),
            )
        )
        _append_event(
            store.transaction_runner,
            event_id="event-runner-call-complete",
            event_type="RUNNER_CALL_INPUT_ASSEMBLED",
            payload=complete_hot,
            payload_ref="payload-runner-call-complete",
            payload_digest=sha256_digest_json(complete_manifest),
        )
        _append_event(
            store.transaction_runner,
            event_id="event-runner-call-limited",
            event_type="RUNNER_CALL_INPUT_ASSEMBLED",
            payload=limited_hot,
            payload_ref="payload-runner-call-limited",
            payload_digest=sha256_digest_json(limited_manifest),
        )
        _append_event(
            store.transaction_runner,
            event_id="event-runner-call-mismatch",
            event_type="RUNNER_CALL_INPUT_ASSEMBLED",
            payload=mismatch_hot,
            payload_ref="payload-runner-call-mismatch",
            payload_digest=sha256_digest_json(mismatch_manifest),
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


def test_runner_call_query_reconstructs_three_hundred_projector_summaries(
    tmp_path: Path,
) -> None:
    """Tool Trace 从 verified descriptor 恢复 300 条五字段 metadata summary。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: descriptor 无法解析、summary 丢失或字段错位时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        _record_real_ordinary_runner_call_manifest(
            store.transaction_runner,
            message_count=300,
        )
        _catch_up(store.transaction_runner, tmp_path)

        page = store.transaction_runner.run_read(
            lambda transaction: read_runner_call_reconstruction_signals_by_run(
                transaction,
                "run-1",
                after_event_sequence=0,
                limit=10,
            )
        )

        assert len(page.signals) == 1
        summaries = page.signals[0].projector_metadata_summary
        assert len(summaries) == 300
        assert summaries[0].projector_metadata_id == "projector:0:user"
        assert summaries[-1].projector_metadata_id == "projector:299:user"
        assert all(
            summary.projector_schema_version == "run_input_projector.v1"
            and summary.purpose == "ordinary_run_input"
            for summary in summaries
        )
        assert summaries[-1].projector_id == "user_input_message"


@pytest.mark.parametrize("tamper_kind", tuple(_ManifestTamperKind))
def test_runner_call_query_rejects_invalid_full_manifest_graph(
    tmp_path: Path,
    tamper_kind: _ManifestTamperKind,
) -> None:
    """Tool Trace 只从完整 typed manifest 图投影 metadata summary。

    :param tmp_path: pytest 临时目录。
    :param tamper_kind: schema、graph、enum 或 hot identity 篡改分类。
    :returns: ``None``。
    :raises AssertionError: 无效 manifest 被 Tool Trace 查询接受时抛出。
    """

    projection_digest = sha256_digest_json({"projection": "manifest-graph"})
    base_manifest = _full_runner_call_manifest(
        manifest_id="runner-call-manifest:graph-validation",
        runner_call_index=0,
        runner_call_kind="initial_user_dispatch",
        runner_call_trigger_reason="initial_user_input",
        roles=("system", "user"),
        projection_ref="payload-projection-graph-validation",
        projection_digest=projection_digest,
        projection_size_bytes=128,
    )
    manifest: dict[str, JsonValue] = dict(base_manifest)
    if tamper_kind is _ManifestTamperKind.INCOMPLETE:
        del manifest["message_entries"]
    elif tamper_kind is _ManifestTamperKind.DANGLING_METADATA_ID:
        entries = list(_json_object_sequence(manifest["message_entries"]))
        first_entry = dict(entries[0])
        first_entry["projector_metadata_id"] = "projector:missing"
        manifest["message_entries"] = [first_entry, *entries[1:]]
    elif tamper_kind in (
        _ManifestTamperKind.UNKNOWN_PROJECTOR_ID,
        _ManifestTamperKind.UNKNOWN_PURPOSE,
    ):
        metadata = list(_json_object_sequence(manifest["projector_metadata"]))
        first_metadata = dict(metadata[0])
        if tamper_kind is _ManifestTamperKind.UNKNOWN_PROJECTOR_ID:
            first_metadata["projector_id"] = "unknown_projector"
        else:
            first_metadata["purpose"] = "unknown_purpose"
        manifest["projector_metadata"] = [first_metadata, *metadata[1:]]
    elif tamper_kind is _ManifestTamperKind.UNKNOWN_SCHEMA_VERSION:
        manifest["schema_version"] = "runner_call_input_manifest.unknown"
    hot_payload: dict[str, JsonValue] = dict(
        _hot_payload_for_manifest(
            base_manifest,
            manifest_ref="payload-manifest-graph-validation",
        )
    )
    if tamper_kind is _ManifestTamperKind.HOT_IDENTITY_MISMATCH:
        hot_payload["runner_call_index"] = 1
    else:
        hot_payload["manifest_digest"] = sha256_digest_json(manifest)
    manifest_digest = sha256_digest_json(manifest)

    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: _write_json_payload(
                transaction,
                payload_ref="payload-manifest-graph-validation",
                payload_id="sqlite-manifest-graph-validation",
                payload=manifest,
            )
        )
        _append_event(
            store.transaction_runner,
            event_id=f"event-runner-call-graph-{tamper_kind.value}",
            event_type="RUNNER_CALL_INPUT_ASSEMBLED",
            payload=hot_payload,
            payload_ref="payload-manifest-graph-validation",
            payload_digest=manifest_digest,
        )
        _catch_up(store.transaction_runner, tmp_path)

        with pytest.raises(HostDurableError):
            store.transaction_runner.run_read(
                lambda transaction: read_runner_call_reconstruction_signals_by_run(
                    transaction,
                    "run-1",
                    after_event_sequence=0,
                    limit=10,
                )
            )


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
    manifest_value = dict(
        _full_runner_call_manifest(
            manifest_id="runner-call-manifest:resolvable",
            runner_call_index=0,
            runner_call_kind="initial_user_dispatch",
            runner_call_trigger_reason="initial_user_input",
            roles=("system", "user"),
            projection_ref="payload-projection",
            projection_digest=projection_digest,
            projection_size_bytes=len(
                canonical_json_dumps(projection_payload).encode("utf-8")
            ),
        )
    )
    manifest_value["tool_schema_snapshot_refs"] = [
        "tool_schema_snapshot_ref:payload-schema",
        "tool_schema_snapshot_digest:" + schema_digest,
    ]
    manifest_payload: Mapping[str, JsonValue] = manifest_value
    manifest_digest = sha256_digest_json(manifest_payload)
    hot_payload = _hot_payload_for_manifest(
        manifest_payload,
        manifest_ref="payload-manifest",
    )
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
            payload=hot_payload,
            payload_ref="payload-manifest",
            payload_digest=manifest_digest,
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
        assert resolved.compactor_response_identity is None
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
    manifest_payload = _full_runner_call_manifest(
        manifest_id="runner-call-manifest:artifact-projection",
        runner_call_index=0,
        runner_call_kind="initial_user_dispatch",
        runner_call_trigger_reason="initial_user_input",
        roles=("user",),
        projection_ref="payload-artifact-projection",
        projection_digest=projection_digest,
        projection_size_bytes=len(
            canonical_json_dumps(projection_payload).encode("utf-8")
        ),
    )
    manifest_digest = sha256_digest_json(manifest_payload)
    hot_payload = _hot_payload_for_manifest(
        manifest_payload,
        manifest_ref="payload-artifact-manifest",
    )
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
            payload=hot_payload,
            payload_ref="payload-artifact-manifest",
            payload_digest=manifest_digest,
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


def test_runner_call_query_rejects_event_row_and_hot_manifest_identity_mismatch(
    tmp_path: Path,
) -> None:
    """EventLog row descriptor 与 hot manifest identity 分裂时 fail closed。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: public Tool Trace 查询未拒绝 identity mismatch 时抛出。
    """

    manifest_ref = "payload-manifest-row-hot-mismatch"
    manifest = _full_runner_call_manifest(
        manifest_id="runner-call-manifest:row-hot-mismatch",
        runner_call_index=0,
        runner_call_kind="initial_user_dispatch",
        runner_call_trigger_reason="initial_user_input",
        roles=("system", "user"),
    )
    manifest_digest = sha256_digest_json(manifest)
    hot_payload = _hot_payload_for_manifest(
        manifest,
        manifest_ref=manifest_ref,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: (
                _write_json_payload(
                    transaction,
                    payload_ref=manifest_ref,
                    payload_id="sqlite-manifest-row-hot-mismatch",
                    payload=manifest,
                ),
                _write_json_payload(
                    transaction,
                    payload_ref="payload-row-descriptor-mismatch",
                    payload_id="sqlite-row-descriptor-mismatch",
                    payload=manifest,
                ),
            )
        )
        _append_event(
            store.transaction_runner,
            event_id="event-runner-call-row-hot-mismatch",
            event_type="RUNNER_CALL_INPUT_ASSEMBLED",
            payload=hot_payload,
            payload_ref="payload-row-descriptor-mismatch",
            payload_digest=manifest_digest,
        )
        _catch_up(store.transaction_runner, tmp_path)

        with pytest.raises(
            HostDurableError,
            match="tool trace row and runner-call hot identity mismatch",
        ):
            store.transaction_runner.run_read(
                lambda transaction: read_runner_call_reconstruction_signals_by_run(
                    transaction,
                    "run-1",
                    after_event_sequence=0,
                    limit=10,
                )
            )


def test_runner_call_hot_owner_fails_closed_for_missing_manifest_ref() -> None:
    """runner-call hot payload 缺 manifest ref 时在 shared owner fail closed。

    :returns: ``None``。
    :raises AssertionError: incomplete hot payload 被接受时抛出。
    """

    manifest = _full_runner_call_manifest(
        manifest_id="runner-call-manifest:missing-ref",
        runner_call_index=0,
        runner_call_kind="initial_user_dispatch",
        runner_call_trigger_reason="initial_user_input",
        roles=("user",),
    )
    payload = dict(
        _hot_payload_for_manifest(
            manifest,
            manifest_ref="payload-manifest-required",
        )
    )
    del payload["manifest_payload_ref"]

    with pytest.raises(HostDurableError, match="hot payload fields mismatch"):
        parse_runner_call_hot_payload(payload)


def test_runner_call_projection_resolver_fails_closed_for_digest_mismatch(
    tmp_path: Path,
) -> None:
    """projection descriptor digest 与 manifest 期望不一致时 resolver fail closed。"""

    projection_payload: Mapping[str, JsonValue] = {"messages": []}
    wrong_projection_digest = sha256_digest_json({"projection": "wrong"})
    manifest_payload = _full_runner_call_manifest(
        manifest_id="runner-call-manifest:projection-digest-mismatch",
        runner_call_index=0,
        runner_call_kind="initial_user_dispatch",
        runner_call_trigger_reason="initial_user_input",
        roles=(),
        projection_ref="payload-projection-mismatch",
        projection_digest=wrong_projection_digest,
        projection_size_bytes=len(
            canonical_json_dumps(projection_payload).encode("utf-8")
        ),
    )
    manifest_digest = sha256_digest_json(manifest_payload)
    hot_payload = _hot_payload_for_manifest(
        manifest_payload,
        manifest_ref="payload-manifest-mismatch",
    )
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
            payload=hot_payload,
            payload_ref="payload-manifest-mismatch",
            payload_digest=manifest_digest,
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
    manifest_payload = _full_runner_call_manifest(
        manifest_id="runner-call-manifest:projection-non-object",
        runner_call_index=0,
        runner_call_kind="initial_user_dispatch",
        runner_call_trigger_reason="initial_user_input",
        roles=(),
        projection_ref="payload-projection-list",
        projection_digest=projection_digest,
        projection_size_bytes=len(
            canonical_json_dumps(projection_payload).encode("utf-8")
        ),
    )
    manifest_digest = sha256_digest_json(manifest_payload)
    hot_payload = _hot_payload_for_manifest(
        manifest_payload,
        manifest_ref="payload-manifest-list",
    )
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
            payload=hot_payload,
            payload_ref="payload-manifest-list",
            payload_digest=manifest_digest,
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


def test_compactor_response_resolver_projects_accepted_actual_identity(
    tmp_path: Path,
) -> None:
    """accepted terminal 公开 actual provider/model/request identity。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: resolver 未投影 exact actual identity 时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        signal, manifest_ref, manifest_digest = _record_compactor_runner_call(
            store.transaction_runner,
            tmp_path,
        )
        _append_event(
            store.transaction_runner,
            event_id="event-context-compacted-1",
            event_type=CONTEXT_COMPACTED,
            payload=_accepted_compactor_payload(
                operation_id="operation-1",
                attempt_number=1,
                compactor_engine_run_id="compactor-engine-run-1",
                manifest_ref=manifest_ref,
                manifest_digest=manifest_digest,
            ),
        )

        resolved = store.transaction_runner.run_read(
            lambda transaction: resolve_runner_call_projection_from_signal(
                transaction,
                signal,
            )
        )

        response = resolved.compactor_response_identity
        assert response is not None
        assert response.disposition is CompactorResponseDisposition.ACCEPTED
        assert response.proposal_manifest_ref == manifest_ref
        assert response.proposal_manifest_digest == manifest_digest
        assert response.successful_response_identity is not None
        assert response.successful_response_identity.effective_provider == (
            "provider-actual"
        )
        assert response.successful_response_identity.effective_model == (
            "model-actual"
        )
        assert response.successful_response_identity.provider_request_id == (
            "provider-request-actual"
        )
        with pytest.raises(ValueError, match="accepted.*requires successful"):
            ResolvedCompactorResponseIdentity(
                disposition=CompactorResponseDisposition.ACCEPTED,
                terminal_event_id="event-invalid-accepted",
                terminal_event_sequence=999,
                compaction_operation_id="operation-invalid",
                compaction_attempt_number=1,
                proposal_manifest_ref="payload-invalid",
                proposal_manifest_digest="sha256:" + "f" * 64,
                successful_response_identity=None,
            )


@pytest.mark.parametrize(
    ("failure_category", "with_success"),
    (
        ("quality_check_rejected", True),
        ("cancellation_requested", False),
    ),
)
def test_compactor_response_resolver_projects_rejected_nullable_identity(
    tmp_path: Path,
    failure_category: str,
    with_success: bool,
) -> None:
    """post-success rejection 保留 actual identity，no-success 明确为 null。

    :param tmp_path: pytest 临时目录。
    :param failure_category: canonical rejection category。
    :param with_success: 是否提供实际 Engine success identity。
    :returns: ``None``。
    :raises AssertionError: rejection nullable identity 不符合 terminal 事实时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        signal, manifest_ref, manifest_digest = _record_compactor_runner_call(
            store.transaction_runner,
            tmp_path,
        )
        identity = (
            _successful_compactor_response_identity("compactor-engine-run-1")
            if with_success
            else None
        )
        payload = build_context_compaction_attempt_rejected_payload(
            operation_id="operation-1",
            attempt_number=1,
            failure_category=failure_category,
            repairable=False,
            runner_attempt_summary_refs=("runner-attempt-1",),
            diagnostic_refs=("diagnostic-1",),
            next_policy_decision="stop",
            budget_after_attempted_compact=None,
            successful_response_identity=identity,
            proposal_manifest_reference=_proposal_manifest_reference(
                operation_id="operation-1",
                attempt_number=1,
                compactor_engine_run_id="compactor-engine-run-1",
                manifest_ref=manifest_ref,
                manifest_digest=manifest_digest,
            ),
        )
        _append_event(
            store.transaction_runner,
            event_id=f"event-rejected-{failure_category}",
            event_type=CONTEXT_COMPACTION_ATTEMPT_REJECTED,
            payload=payload,
        )
        resolved = store.transaction_runner.run_read(
            lambda transaction: resolve_runner_call_projection_from_signal(
                transaction,
                signal,
            )
        )

        response = resolved.compactor_response_identity
        assert response is not None
        assert response.disposition is (
            CompactorResponseDisposition.ATTEMPT_REJECTED
        )
        assert (response.successful_response_identity is not None) is with_success


def test_compactor_response_resolver_exhausts_multiple_full_pages_without_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """目标 terminal 位于多个 full page 后仍解析，不产生 scan-cap limitation。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: resolver 未 exhaust 多个 full pages 时抛出。
    """

    monkeypatch.setattr(
        tool_trace_module,
        "_COMPACTOR_TERMINAL_SCAN_PAGE_SIZE",
        1,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        signal, manifest_ref, manifest_digest = _record_compactor_runner_call(
            store.transaction_runner,
            tmp_path,
        )
        for ordinal in range(3):
            unrelated_ref = CompactorProposalManifestReference(
                manifest_event_id=f"event-unrelated-manifest-{ordinal}",
                manifest_payload_ref=f"payload-unrelated-{ordinal}",
                manifest_digest=sha256_digest_json({"unrelated": ordinal}),
                compactor_input_projection_ref=f"projection-unrelated-{ordinal}",
                compactor_input_projection_digest=sha256_digest_json(
                    {"projection": ordinal}
                ),
                compaction_operation_id=f"unrelated-operation-{ordinal}",
                compaction_attempt_number=ordinal + 1,
                compactor_engine_run_id=f"unrelated-engine-run-{ordinal}",
            )
            _append_event(
                store.transaction_runner,
                event_id=f"event-unrelated-terminal-{ordinal}",
                event_type=CONTEXT_COMPACTION_ATTEMPT_REJECTED,
                payload=build_context_compaction_attempt_rejected_payload(
                    operation_id=f"unrelated-operation-{ordinal}",
                    attempt_number=ordinal + 1,
                    failure_category="cancellation_requested",
                    repairable=False,
                    runner_attempt_summary_refs=("runner-attempt",),
                    diagnostic_refs=("diagnostic",),
                    next_policy_decision="stop",
                    budget_after_attempted_compact=None,
                    successful_response_identity=None,
                    proposal_manifest_reference=unrelated_ref,
                ),
            )
        _append_event(
            store.transaction_runner,
            event_id="event-target-terminal",
            event_type=CONTEXT_COMPACTION_ATTEMPT_REJECTED,
            payload=build_context_compaction_attempt_rejected_payload(
                operation_id="operation-1",
                attempt_number=1,
                failure_category="cancellation_requested",
                repairable=False,
                runner_attempt_summary_refs=("runner-attempt",),
                diagnostic_refs=("diagnostic",),
                next_policy_decision="stop",
                budget_after_attempted_compact=None,
                successful_response_identity=None,
                proposal_manifest_reference=_proposal_manifest_reference(
                    operation_id="operation-1",
                    attempt_number=1,
                    compactor_engine_run_id="compactor-engine-run-1",
                    manifest_ref=manifest_ref,
                    manifest_digest=manifest_digest,
                ),
            ),
        )

        resolved = store.transaction_runner.run_read(
            lambda transaction: resolve_runner_call_projection_from_signal(
                transaction,
                signal,
            )
        )

        assert resolved.compactor_response_identity is not None
        assert resolved.compactor_response_identity.terminal_event_id == (
            "event-target-terminal"
        )


def test_compactor_response_resolver_returns_missing_only_after_exhaustion(
    tmp_path: Path,
) -> None:
    """完整 empty-page exhaustion 后无 terminal 才返回 typed unavailable。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: complete exhaustion 未返回 ``None`` 时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        signal, _, _ = _record_compactor_runner_call(
            store.transaction_runner,
            tmp_path,
        )
        resolved = store.transaction_runner.run_read(
            lambda transaction: resolve_runner_call_projection_from_signal(
                transaction,
                signal,
            )
        )

        assert resolved.compactor_response_identity is None


def test_compactor_response_resolver_rejects_non_advancing_cursor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """full page 后 reader 重复旧 row 时 resolver fail closed。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: non-advancing cursor 未被拒绝时抛出。
    """

    monkeypatch.setattr(
        tool_trace_module,
        "_COMPACTOR_TERMINAL_SCAN_PAGE_SIZE",
        1,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        signal, manifest_ref, manifest_digest = _record_compactor_runner_call(
            store.transaction_runner,
            tmp_path,
        )
        _append_event(
            store.transaction_runner,
            event_id="event-repeated-terminal",
            event_type=CONTEXT_COMPACTION_ATTEMPT_REJECTED,
            payload=build_context_compaction_attempt_rejected_payload(
                operation_id="operation-1",
                attempt_number=1,
                failure_category="cancellation_requested",
                repairable=False,
                runner_attempt_summary_refs=("runner-attempt",),
                diagnostic_refs=("diagnostic",),
                next_policy_decision="stop",
                budget_after_attempted_compact=None,
                successful_response_identity=None,
                proposal_manifest_reference=_proposal_manifest_reference(
                    operation_id="operation-1",
                    attempt_number=1,
                    compactor_engine_run_id="compactor-engine-run-1",
                    manifest_ref=manifest_ref,
                    manifest_digest=manifest_digest,
                ),
            ),
        )
        terminal_row = store.transaction_runner.run_read(
            lambda transaction: read_run_events_by_types_page(
                transaction,
                run_id="run-1",
                event_types=(CONTEXT_COMPACTION_ATTEMPT_REJECTED,),
                after_event_sequence=0,
                limit=1,
            )[0]
        )
        monkeypatch.setattr(
            tool_trace_module,
            "read_run_events_by_types_page",
            _NonAdvancingTerminalPageReader(terminal_row),
        )

        with pytest.raises(HostDurableError, match="cursor did not advance"):
            store.transaction_runner.run_read(
                lambda transaction: resolve_runner_call_projection_from_signal(
                    transaction,
                    signal,
                )
            )


@pytest.mark.parametrize(
    "tamper_field",
    (
        "manifest_ref",
        "manifest_digest",
        "operation_id",
        "attempt_number",
        "engine_run_id",
        "duplicate_terminal",
        "malformed_identity",
    ),
)
def test_compactor_response_resolver_fails_closed_for_binding_corruption(
    tmp_path: Path,
    tamper_field: str,
) -> None:
    """ref/digest/operation/attempt/Engine identity/duplicate/malformed 全部拒绝。

    :param tmp_path: pytest 临时目录。
    :param tamper_field: 本次注入的 corruption 类别。
    :returns: ``None``。
    :raises AssertionError: corruption 未触发 fail-closed 时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        signal, manifest_ref, manifest_digest = _record_compactor_runner_call(
            store.transaction_runner,
            tmp_path,
        )
        operation_id = "operation-1"
        attempt_number = 1
        terminal_engine_run_id = (
            "wrong-engine-run"
            if tamper_field == "engine_run_id"
            else "compactor-engine-run-1"
        )
        reference = _proposal_manifest_reference(
            operation_id=operation_id,
            attempt_number=attempt_number,
            compactor_engine_run_id=terminal_engine_run_id,
            manifest_ref=(
                "payload-wrong-manifest"
                if tamper_field == "manifest_ref"
                else manifest_ref
            ),
            manifest_digest=(
                sha256_digest_json({"wrong": "digest"})
                if tamper_field == "manifest_digest"
                else manifest_digest
            ),
        )
        identity = _successful_compactor_response_identity(
            terminal_engine_run_id
        )
        payload = dict(
            build_context_compaction_attempt_rejected_payload(
                operation_id=operation_id,
                attempt_number=attempt_number,
                failure_category="quality_check_rejected",
                repairable=False,
                runner_attempt_summary_refs=("runner-attempt",),
                diagnostic_refs=("diagnostic",),
                next_policy_decision="stop",
                budget_after_attempted_compact=None,
                successful_response_identity=identity,
                proposal_manifest_reference=reference,
            )
        )
        if tamper_field == "operation_id":
            payload["operation_id"] = "wrong-operation"
        if tamper_field == "attempt_number":
            payload["attempt_number"] = 2
        if tamper_field == "malformed_identity":
            response_identity = dict(
                _json_object(payload["successful_response_identity"])
            )
            response_identity["authorization"] = "Bearer must-not-leak"
            payload["successful_response_identity"] = response_identity
        _append_event(
            store.transaction_runner,
            event_id="event-corrupt-terminal-1",
            event_type=CONTEXT_COMPACTION_ATTEMPT_REJECTED,
            payload=payload,
        )
        if tamper_field == "duplicate_terminal":
            _append_event(
                store.transaction_runner,
                event_id="event-corrupt-terminal-2",
                event_type=CONTEXT_COMPACTION_ATTEMPT_REJECTED,
                payload=payload,
            )

        with pytest.raises(HostDurableError):
            store.transaction_runner.run_read(
                lambda transaction: resolve_runner_call_projection_from_signal(
                    transaction,
                    signal,
                )
            )


def test_tool_trace_row_resolver_reads_args_result_and_final_answer(
    tmp_path: Path,
) -> None:
    """row resolver 能读取工具参数、工具结果 payload 与 terminal final answer。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 任一 canonical descriptor payload 无法恢复时抛出。
    """

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
        accepted_arguments: Mapping[str, JsonValue] = {
            "timezone": "Asia/Shanghai"
        }
        atom = _canonical_request_atom(
            event_id="event-tool-call",
            tool_call_id="call-time",
            tool_name="get_current_time",
            accepted_arguments=accepted_arguments,
        )
        request = _append_canonical_tool_request(
            store.transaction_runner,
            event_id="event-tool-call",
            atom=atom,
        )
        _append_accepted_tool_result(
            store.transaction_runner,
            event_id="event-tool-result",
            request=request,
            atom=atom,
            additional_payload={
                "payload_ref": {
                    "payload_ref": "payload-tool-result",
                    "payload_digest": result_digest,
                },
                "payload_digest": result_digest,
            },
            raw_tool_outcome={"kind": "completed", "result": result_payload},
            result_payload_ref="payload-tool-result",
            result_payload_digest=result_digest,
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
            "arguments": {"timezone": "Asia/Shanghai"}
        }
        assert resolved_result.descriptor_payload is not None
        assert resolved_result.descriptor_payload.payload == result_payload
        assert resolved_final.descriptor_payload is not None
        assert resolved_final.descriptor_payload.payload == final_payload
