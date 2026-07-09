"""Host accepted result projection helper 测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from dayu.contracts.json_value import JsonValue
from dayu.host.api import RunStatus
from dayu.host.accepted_result_projection import (
    ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT,
    ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT,
    AcceptedToolResultProjection,
    AcceptedToolResultQueryState,
    AcceptedToolResultSourceState,
    AcceptedToolResultStatus,
    project_accepted_tool_result,
)
from dayu.host.compact_material import (
    PreDispatchCompactMaterialView,
    build_pre_dispatch_compact_material_view,
)
from dayu.host.compaction import CompactMaterialBlockKind
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.memory import _memory_projection_event_from_view
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.payload import (
    PayloadStore,
    SQLitePayloadFormat,
    SQLitePayloadWriteRequest,
)
from dayu.host.durable.schema import (
    TOOL_CALL_ARGUMENTS_STORAGE_INLINE_JSON,
    TOOL_CALL_SEMANTIC_QUERY_STORAGE_ABSENT,
    TOOL_CALL_SEMANTIC_QUERY_STORAGE_INLINE_TEXT,
)
from dayu.host.durable.state import RunRow
from dayu.host.durable.tool_trace import ToolTraceHotRow, read_tool_trace_hot_row
from dayu.host.durable.transaction import HostTransaction
from dayu.host.evidence import (
    AcceptedEvidenceEnvelope,
    AcceptedEvidenceResultRef,
    AcceptedEvidenceToolQuery,
    OpaqueEvidenceRef,
    accepted_evidence_envelope_to_json_value,
)
from dayu.host.memory import (
    CONVERSATION_MEMORY_CONSUMER_ID,
    ConversationMemorySnapshotVNext,
    build_conversation_memory_snapshot_from_events,
    default_memory_projection_policy,
)
from dayu.host.projection import projection_event_view_from_row
from dayu.host.run_input import _accepted_tool_evidence_content
from dayu.host.tool_trace import (
    ToolTraceProjectionConsumer,
    ToolTraceSinkOptions,
)

_SESSION_ID = "session-projection"
_RUN_ID = "run-projection"
_ATTEMPT_ID = "attempt-projection"
_EXECUTION_ID = "execution-projection"
_TOOL_NAME = "fins.search"
_DIGEST = sha256_digest_json({"test": "accepted-result-projection"})


def test_projection_uses_semantic_query_status_result_and_business_source(
    tmp_path: Path,
) -> None:
    """projection 使用 request semantic query、status、result 与业务 source。"""

    event_log = EventLogStore()
    projection: AcceptedToolResultProjection | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        def seed(transaction: HostTransaction) -> EventLogRow:
            """写入一组 request / accepted result facts。

            :param transaction: Host transaction。
            :returns: accepted result row。
            """

            arguments_json: JsonValue = {"arguments": {"ticker": "MSFT"}}
            arguments_digest = sha256_digest_json(arguments_json)
            request = _append_tool_call_requested(
                transaction,
                event_log,
                event_id="event-request-semantic",
                tool_call_id="tool-call-semantic",
                arguments_json=arguments_json,
                semantic_query_text="Search Microsoft FY2025 revenue",
            )
            return _append_tool_result(
                transaction,
                event_log,
                event_id="event-result-semantic",
                tool_call_id="tool-call-semantic",
                request_event_ref=request.event_id,
                normalized_arguments_digest=arguments_digest,
                tool_fact_kind="completed",
                raw_tool_outcome={
                    "kind": "completed",
                    "result": {"ok": True, "summary": "Revenue found"},
                },
                source_refs=(
                    OpaqueEvidenceRef(ref_kind="event", ref_id="internal", digest=None),
                    OpaqueEvidenceRef(ref_kind="filing", ref_id="MSFT-10K", digest=None),
                ),
            )

        row = store.transaction_runner.run_write(seed)
        projection = store.transaction_runner.run_read(
            lambda transaction: project_accepted_tool_result(transaction, row)
        )

    assert projection is not None
    assert projection.evidence_id == "evidence:event-result-semantic"
    assert projection.tool_name == _TOOL_NAME
    assert projection.query.state is AcceptedToolResultQueryState.SEMANTIC_QUERY
    assert projection.query.text == "Search Microsoft FY2025 revenue"
    assert projection.status is AcceptedToolResultStatus.COMPLETED
    assert projection.result_details_text == "Revenue found"
    assert projection.source.text == "filing:MSFT-10K"


def test_projection_falls_back_to_arguments_when_semantic_query_is_absent(
    tmp_path: Path,
) -> None:
    """semantic query 缺失时 projection 使用 helper 内统一参数摘要。"""

    event_log = EventLogStore()
    projection: AcceptedToolResultProjection | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        def seed(transaction: HostTransaction) -> EventLogRow:
            """写入无 semantic query 的 request / accepted result facts。

            :param transaction: Host transaction。
            :returns: accepted result row。
            """

            arguments_json: JsonValue = {"arguments": {"ticker": "AAPL"}}
            arguments_digest = sha256_digest_json(arguments_json)
            request = _append_tool_call_requested(
                transaction,
                event_log,
                event_id="event-request-arguments",
                tool_call_id="tool-call-arguments",
                arguments_json=arguments_json,
                semantic_query_text=None,
            )
            return _append_tool_result(
                transaction,
                event_log,
                event_id="event-result-arguments",
                tool_call_id="tool-call-arguments",
                request_event_ref=request.event_id,
                normalized_arguments_digest=arguments_digest,
                tool_fact_kind="failed",
                raw_tool_outcome={
                    "kind": "failed",
                    "result": {"ok": False, "error": "not found"},
                },
                source_refs=(),
            )

        row = store.transaction_runner.run_write(seed)
        projection = store.transaction_runner.run_read(
            lambda transaction: project_accepted_tool_result(transaction, row)
        )

    assert projection is not None
    assert projection.query.state is AcceptedToolResultQueryState.ARGUMENTS_SUMMARY
    assert projection.query.text == (
        f"参数：{canonical_json_dumps({'arguments': {'ticker': 'AAPL'}})}"
    )
    assert projection.status is AcceptedToolResultStatus.FAILED
    assert projection.source.state is AcceptedToolResultSourceState.UNAVAILABLE
    assert projection.source.diagnostic_reason == "business_source_unavailable"
    assert projection.source.text == ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT


def test_projection_missing_request_atom_returns_limited_signal(
    tmp_path: Path,
) -> None:
    """request atom 缺失时 query 降级由 projection owner 统一给出。"""

    event_log = EventLogStore()
    projection: AcceptedToolResultProjection | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        row = store.transaction_runner.run_write(
            lambda transaction: _append_tool_result(
                transaction,
                event_log,
                event_id="event-result-missing-request",
                tool_call_id="tool-call-missing-request",
                request_event_ref="event-request-missing",
                normalized_arguments_digest=_DIGEST,
                tool_fact_kind="cancelled",
                raw_tool_outcome={"kind": "cancelled", "result": {"ok": False}},
                source_refs=(),
            )
        )
        projection = store.transaction_runner.run_read(
            lambda transaction: project_accepted_tool_result(transaction, row)
        )

    assert projection is not None
    assert projection.query.state is AcceptedToolResultQueryState.LIMITED_SIGNAL
    assert projection.query.text == ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT
    assert projection.status is AcceptedToolResultStatus.CANCELLED
    assert "request_atom_unavailable" in projection.diagnostic_reasons


def test_projection_missing_envelope_returns_shared_unavailable_source_text(
    tmp_path: Path,
) -> None:
    """accepted evidence envelope 缺失时 source 文本仍由 projection owner 提供。"""

    event_log = EventLogStore()
    projection: AcceptedToolResultProjection | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        row = store.transaction_runner.run_write(
            lambda transaction: _append_event(
                transaction,
                event_log,
                event_id="event-result-no-envelope",
                event_type="TOOL_RESULT_ACCEPTED",
                payload={
                    "tool_call_id": "tool-call-no-envelope",
                    "tool_name": _TOOL_NAME,
                    "tool_fact_kind": "completed",
                    "raw_tool_outcome": {
                        "kind": "completed",
                        "result": {"ok": True},
                    },
                },
            )
        )
        projection = store.transaction_runner.run_read(
            lambda transaction: project_accepted_tool_result(transaction, row)
        )

    assert projection is not None
    assert projection.source.state is AcceptedToolResultSourceState.UNAVAILABLE
    assert projection.source.diagnostic_reason == "accepted_evidence_envelope_missing"
    assert projection.source.text == ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT


def test_projection_maps_governed_error_and_unknown_status(tmp_path: Path) -> None:
    """projection 按封闭状态表映射 governed_error 与 unknown。"""

    event_log = EventLogStore()
    governed_projection: AcceptedToolResultProjection | None = None
    unknown_projection: AcceptedToolResultProjection | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        governed = store.transaction_runner.run_write(
            lambda transaction: _append_tool_result(
                transaction,
                event_log,
                event_id="event-result-governed",
                tool_call_id="tool-call-governed",
                request_event_ref=None,
                normalized_arguments_digest=_DIGEST,
                tool_fact_kind="governed_error",
                raw_tool_outcome={"kind": "failed", "result": {"ok": False}},
                source_refs=(),
            )
        )
        unknown = store.transaction_runner.run_write(
            lambda transaction: _append_tool_result(
                transaction,
                event_log,
                event_id="event-result-unknown",
                tool_call_id="tool-call-unknown",
                request_event_ref=None,
                normalized_arguments_digest=_DIGEST,
                tool_fact_kind="unexpected-status",
                raw_tool_outcome={"kind": "completed", "result": {"ok": True}},
                source_refs=(),
            )
        )
        governed_projection = store.transaction_runner.run_read(
            lambda transaction: project_accepted_tool_result(transaction, governed)
        )
        unknown_projection = store.transaction_runner.run_read(
            lambda transaction: project_accepted_tool_result(transaction, unknown)
        )

    assert governed_projection is not None
    assert unknown_projection is not None
    assert governed_projection.status is AcceptedToolResultStatus.GOVERNED_ERROR
    assert unknown_projection.status is AcceptedToolResultStatus.UNKNOWN


def test_projection_identity_mismatch_returns_limited_signal(tmp_path: Path) -> None:
    """request atom 身份不匹配时 query fail closed 为 limited signal。"""

    event_log = EventLogStore()
    projection: AcceptedToolResultProjection | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        def seed(transaction: HostTransaction) -> EventLogRow:
            """写入 tool_call_id 不一致的 request / accepted result。

            :param transaction: Host transaction。
            :returns: accepted result row。
            """

            arguments_json: JsonValue = {"arguments": {"ticker": "MSFT"}}
            arguments_digest = sha256_digest_json(arguments_json)
            request = _append_tool_call_requested(
                transaction,
                event_log,
                event_id="event-request-identity-mismatch",
                tool_call_id="tool-call-request-side",
                arguments_json=arguments_json,
                semantic_query_text="request query must not leak",
            )
            return _append_tool_result(
                transaction,
                event_log,
                event_id="event-result-identity-mismatch",
                tool_call_id="tool-call-result-side",
                request_event_ref=request.event_id,
                normalized_arguments_digest=arguments_digest,
                tool_fact_kind="completed",
                raw_tool_outcome={"kind": "completed", "result": {"ok": True}},
                source_refs=(),
            )

        row = store.transaction_runner.run_write(seed)
        projection = store.transaction_runner.run_read(
            lambda transaction: project_accepted_tool_result(transaction, row)
        )

    assert projection is not None
    assert projection.query.state is AcceptedToolResultQueryState.LIMITED_SIGNAL
    assert projection.query.text == ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT
    assert projection.query.diagnostic_reason == "request_atom_identity_mismatch"
    assert "request query must not leak" not in projection.query.text


def test_projection_wait_resolution_status_takes_priority(tmp_path: Path) -> None:
    """wait resolution kind 优先于普通 tool fact kind。"""

    event_log = EventLogStore()
    projection: AcceptedToolResultProjection | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        row = store.transaction_runner.run_write(
            lambda transaction: _append_tool_result(
                transaction,
                event_log,
                event_id="event-result-wait-resolution",
                tool_call_id="tool-call-wait-resolution",
                request_event_ref=None,
                normalized_arguments_digest=_DIGEST,
                tool_fact_kind="completed",
                resolution_kind="cancelled",
                raw_tool_outcome={"kind": "completed", "result": {"ok": True}},
                source_refs=(),
            )
        )
        projection = store.transaction_runner.run_read(
            lambda transaction: project_accepted_tool_result(transaction, row)
        )

    assert projection is not None
    assert projection.status is AcceptedToolResultStatus.CANCELLED


def test_projection_filters_internal_source_refs(tmp_path: Path) -> None:
    """source projection 只保留业务 source refs。"""

    event_log = EventLogStore()
    projection: AcceptedToolResultProjection | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        row = store.transaction_runner.run_write(
            lambda transaction: _append_tool_result(
                transaction,
                event_log,
                event_id="event-result-source-filter",
                tool_call_id="tool-call-source-filter",
                request_event_ref=None,
                normalized_arguments_digest=_DIGEST,
                tool_fact_kind="completed",
                raw_tool_outcome={"kind": "completed", "result": {"ok": True}},
                source_refs=(
                    OpaqueEvidenceRef(ref_kind="payload", ref_id="payload-1", digest=None),
                    OpaqueEvidenceRef(ref_kind="event", ref_id="event-1", digest=None),
                    OpaqueEvidenceRef(ref_kind="filing", ref_id="MSFT-10K", digest=None),
                ),
            )
        )
        projection = store.transaction_runner.run_read(
            lambda transaction: project_accepted_tool_result(transaction, row)
        )

    assert projection is not None
    assert projection.source.state is AcceptedToolResultSourceState.AVAILABLE
    assert projection.source.text == "filing:MSFT-10K"


def test_projection_unavailable_source_uses_shared_llm_text_and_filters_internal_refs(
    tmp_path: Path,
) -> None:
    """source 不可用时由 projection owner 给出共享 LLM-facing 文案。"""

    event_log = EventLogStore()
    projection: AcceptedToolResultProjection | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        row = store.transaction_runner.run_write(
            lambda transaction: _append_tool_result(
                transaction,
                event_log,
                event_id="event-result-source-unavailable",
                tool_call_id="tool-call-source-unavailable",
                request_event_ref=None,
                normalized_arguments_digest=_DIGEST,
                tool_fact_kind="completed",
                raw_tool_outcome={"kind": "completed", "result": {"ok": True}},
                source_refs=(
                    OpaqueEvidenceRef(ref_kind="payload", ref_id="payload-1", digest=None),
                    OpaqueEvidenceRef(ref_kind="event", ref_id="event-1", digest=None),
                    OpaqueEvidenceRef(ref_kind="digest", ref_id="sha256:internal", digest=None),
                ),
            )
        )
        projection = store.transaction_runner.run_read(
            lambda transaction: project_accepted_tool_result(transaction, row)
        )

    assert projection is not None
    assert projection.source.state is AcceptedToolResultSourceState.UNAVAILABLE
    assert projection.source.diagnostic_reason == "business_source_unavailable"
    assert projection.source.text == ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT
    assert "business_source_unavailable" in projection.diagnostic_reasons
    assert "payload-1" not in projection.source.text
    assert "event-1" not in projection.source.text
    assert "sha256:internal" not in projection.source.text


def test_projection_reads_descriptor_payload_and_reports_missing_descriptor(
    tmp_path: Path,
) -> None:
    """projection 覆盖 descriptor raw payload 与 descriptor 缺失诊断。"""

    event_log = EventLogStore()
    descriptor_payload: JsonValue = {
        "kind": "completed",
        "result": {"ok": True, "summary": "descriptor result"},
    }
    descriptor_projection: AcceptedToolResultProjection | None = None
    missing_projection: AcceptedToolResultProjection | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        def seed_descriptor(transaction: HostTransaction) -> EventLogRow:
            """写入 descriptor-backed accepted result。

            :param transaction: Host transaction。
            :returns: accepted result row。
            """

            payload_ref = "payload-accepted-result-descriptor"
            envelope = _accepted_envelope(
                event_id="event-result-descriptor",
                tool_call_id="tool-call-descriptor",
                request_event_ref=None,
                normalized_arguments_digest=_DIGEST,
                raw_tool_outcome=descriptor_payload,
                source_refs=(),
                payload_ref=payload_ref,
                payload_digest=None,
            )
            payload: JsonValue = {
                "tool_call_id": "tool-call-descriptor",
                "tool_name": _TOOL_NAME,
                "normalized_arguments_digest": _DIGEST,
                "tool_fact_kind": "completed",
                "accepted_evidence_envelope": accepted_evidence_envelope_to_json_value(
                    envelope
                ),
                "raw_tool_outcome": descriptor_payload,
            }
            actual_digest = sha256_digest_json(payload)
            PayloadStore().write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref=payload_ref,
                    payload_id="sqlite-accepted-result-descriptor",
                    payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                    payload_json=payload,
                    media_type="application/json",
                    metadata={"kind": "accepted_result_test"},
                    expected_digest=actual_digest,
                ),
            )
            return _append_event(
                transaction,
                event_log,
                event_id="event-result-descriptor",
                event_type="TOOL_RESULT_ACCEPTED",
                payload={},
                payload_ref=payload_ref,
                payload_digest=actual_digest,
            )

        descriptor_row = store.transaction_runner.run_write(seed_descriptor)
        missing_row = store.transaction_runner.run_write(
            lambda transaction: _append_tool_result(
                transaction,
                event_log,
                event_id="event-result-missing-descriptor",
                tool_call_id="tool-call-missing-descriptor",
                request_event_ref=None,
                normalized_arguments_digest=_DIGEST,
                tool_fact_kind="completed",
                raw_tool_outcome={"kind": "completed", "result": {"ok": True}},
                source_refs=(),
                payload_ref="payload-missing-descriptor",
                payload_digest=sha256_digest_json({"missing": True}),
            )
        )
        descriptor_projection = store.transaction_runner.run_read(
            lambda transaction: project_accepted_tool_result(transaction, descriptor_row)
        )
        missing_projection = store.transaction_runner.run_read(
            lambda transaction: project_accepted_tool_result(transaction, missing_row)
        )

    assert descriptor_projection is not None
    assert missing_projection is not None
    assert descriptor_projection.result_details_text == "descriptor result"
    assert descriptor_projection.status is AcceptedToolResultStatus.COMPLETED
    assert missing_projection.result_text is None
    assert missing_projection.status is AcceptedToolResultStatus.LOST
    assert "result_payload_unavailable" in missing_projection.diagnostic_reasons


def test_projection_unsafe_argument_keys_return_limited_signal(tmp_path: Path) -> None:
    """敏感或本地路径参数 key 不进入 LLM-facing query 摘要。"""

    event_log = EventLogStore()
    projection: AcceptedToolResultProjection | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        def seed(transaction: HostTransaction) -> EventLogRow:
            """写入含敏感参数 key 的 accepted result。

            :param transaction: Host transaction。
            :returns: accepted result row。
            """

            arguments_json: JsonValue = {
                "arguments": {"ticker": "MSFT", "api_key": "secret-value"}
            }
            arguments_digest = sha256_digest_json(arguments_json)
            request = _append_tool_call_requested(
                transaction,
                event_log,
                event_id="event-request-unsafe-arguments",
                tool_call_id="tool-call-unsafe-arguments",
                arguments_json=arguments_json,
                semantic_query_text=None,
            )
            return _append_tool_result(
                transaction,
                event_log,
                event_id="event-result-unsafe-arguments",
                tool_call_id="tool-call-unsafe-arguments",
                request_event_ref=request.event_id,
                normalized_arguments_digest=arguments_digest,
                tool_fact_kind="completed",
                raw_tool_outcome={"kind": "completed", "result": {"ok": True}},
                source_refs=(),
            )

        row = store.transaction_runner.run_write(seed)
        projection = store.transaction_runner.run_read(
            lambda transaction: project_accepted_tool_result(transaction, row)
        )

    assert projection is not None
    assert projection.query.state is AcceptedToolResultQueryState.LIMITED_SIGNAL
    assert projection.query.diagnostic_reason == "arguments_summary_unsafe"
    assert "secret-value" not in projection.query.text


def test_projection_maps_raw_result_ok_false_and_extracts_details(
    tmp_path: Path,
) -> None:
    """raw outcome result.ok=false 映射 failed，并抽取结构化 details。"""

    event_log = EventLogStore()
    projection: AcceptedToolResultProjection | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        row = store.transaction_runner.run_write(
            lambda transaction: _append_tool_result(
                transaction,
                event_log,
                event_id="event-result-raw-ok-false",
                tool_call_id="tool-call-raw-ok-false",
                request_event_ref=None,
                normalized_arguments_digest=_DIGEST,
                tool_fact_kind=None,
                raw_tool_outcome={
                    "result": {"ok": False},
                    "details": [{"label": "reason", "value": "not found"}],
                },
                source_refs=(),
            )
        )
        projection = store.transaction_runner.run_read(
            lambda transaction: project_accepted_tool_result(transaction, row)
        )

    assert projection is not None
    assert projection.status is AcceptedToolResultStatus.FAILED
    assert projection.result_details_text == "reason=not found"


def test_same_accepted_result_has_equivalent_consumer_projection(
    tmp_path: Path,
) -> None:
    """同一 source-unavailable result 在各消费者中使用同一 projection 语义。"""

    event_log = EventLogStore()
    projection: AcceptedToolResultProjection | None = None
    tool_trace_row: ToolTraceHotRow | None = None
    memory_snapshot: ConversationMemorySnapshotVNext | None = None
    compact_view: PreDispatchCompactMaterialView | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        def seed(transaction: HostTransaction) -> tuple[EventLogRow, EventLogRow]:
            """写入跨消费者等价性测试 facts。

            :param transaction: Host transaction。
            :returns: accepted result row 与 current input row。
            """

            arguments_json: JsonValue = {"arguments": {"ticker": "MSFT"}}
            arguments_digest = sha256_digest_json(arguments_json)
            request = _append_tool_call_requested(
                transaction,
                event_log,
                event_id="event-request-cross-consumer",
                tool_call_id="tool-call-cross-consumer",
                arguments_json=arguments_json,
                semantic_query_text="Read MSFT FY2025 revenue",
            )
            result = _append_tool_result(
                transaction,
                event_log,
                event_id="event-result-cross-consumer",
                tool_call_id="tool-call-cross-consumer",
                request_event_ref=request.event_id,
                normalized_arguments_digest=arguments_digest,
                tool_fact_kind="completed",
                raw_tool_outcome={
                    "kind": "completed",
                    "result": {"ok": True, "summary": "Revenue is 100"},
                },
                source_refs=(
                    OpaqueEvidenceRef(ref_kind="payload", ref_id="payload-internal", digest=None),
                    OpaqueEvidenceRef(ref_kind="event", ref_id="event-internal", digest=None),
                ),
            )
            current = _append_event(
                transaction,
                event_log,
                event_id="event-current-cross-consumer",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "current question"},
            )
            return result, current

        result_row, current_row = store.transaction_runner.run_write(seed)
        projection = store.transaction_runner.run_read(
            lambda transaction: project_accepted_tool_result(transaction, result_row)
        )
        consumer = ToolTraceProjectionConsumer(
            ToolTraceSinkOptions(cold_jsonl_path=tmp_path / "trace.jsonl")
        )
        store.transaction_runner.run_write(
            lambda transaction: consumer.apply_event(
                transaction,
                projection_event_view_from_row(result_row),
            )
        )
        tool_trace_row = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_hot_row(
                transaction,
                result_row.event_id,
            )
        )
        memory_event = store.transaction_runner.run_read(
            lambda transaction: _memory_projection_event_from_view(
                transaction,
                projection_event_view_from_row(result_row),
            )
        )
        memory_snapshot = build_conversation_memory_snapshot_from_events(
            events=(memory_event,),
            session_id=_SESSION_ID,
            consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
            policy=default_memory_projection_policy(),
            built_at="2026-07-09T00:00:00.000000Z",
        )
        compact_view = store.transaction_runner.run_read(
            lambda transaction: build_pre_dispatch_compact_material_view(
                transaction,
                event_log,
                run=_run_row(current_row),
                current_display_text="current question",
            )
        )

    assert projection is not None
    assert projection.source.state is AcceptedToolResultSourceState.UNAVAILABLE
    assert projection.source.text == ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT
    assert tool_trace_row is not None
    assert memory_snapshot is not None
    assert compact_view is not None
    evidence_blocks = tuple(
        block
        for block in compact_view.material_blocks
        if block.kind is CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE
    )
    assert len(evidence_blocks) == 1
    evidence_block = evidence_blocks[0]
    run_input_text = _accepted_tool_evidence_content(evidence_block)
    memory_text = memory_snapshot.trace_memory.selected_recent_window[0].text
    trace_request = tool_trace_row.trace_summary["tool_request"]
    trace_result = tool_trace_row.trace_summary["tool_result"]
    assert isinstance(trace_request, dict)
    assert isinstance(trace_result, dict)
    assert trace_request["query_text"] == projection.query.text
    assert trace_request["query_state"] == projection.query.state.value
    assert trace_result["result_status"] == projection.status.value
    assert trace_result["result_text"] == projection.result_text
    assert evidence_block.readable_query_text == projection.query.text
    assert evidence_block.readable_source_text == projection.source.text
    assert evidence_block.text == projection.result_text
    assert f"query={projection.query.text}" in run_input_text
    assert f"source={projection.source.text}" in run_input_text
    assert f"result={projection.result_text}" in run_input_text
    assert projection.query.text in memory_text
    assert projection.result_text is not None
    assert projection.result_text in memory_text
    assert projection.source.text is not None
    assert projection.source.text in memory_text
    visible_texts = (
        run_input_text,
        memory_text,
        str(tool_trace_row.trace_summary),
    )
    for visible_text in visible_texts:
        assert "payload-internal" not in visible_text
        assert "event-internal" not in visible_text


def _durable_options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造 accepted result projection 测试 durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=0.25,
            write_busy_retry_count=3,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.01,
        ),
    )


def _append_tool_call_requested(
    transaction: HostTransaction,
    event_log: EventLogStore,
    *,
    event_id: str,
    tool_call_id: str,
    arguments_json: JsonValue,
    semantic_query_text: str | None,
) -> EventLogRow:
    """追加测试用 ``TOOL_CALL_REQUESTED`` canonical fact。

    :param transaction: Host transaction。
    :param event_log: EventLog store。
    :param event_id: event id。
    :param tool_call_id: tool call id。
    :param arguments_json: LLM-safe request arguments JSON。
    :param semantic_query_text: 可选 semantic query 文本。
    :returns: appended EventLog row。
    """

    arguments_digest = sha256_digest_json(arguments_json)
    semantic_query_digest = (
        sha256_digest_json({"semantic_query_text": semantic_query_text})
        if semantic_query_text is not None
        else None
    )
    return _append_event(
        transaction,
        event_log,
        event_id=event_id,
        event_type="TOOL_CALL_REQUESTED",
        payload={
            "tool_call_id": tool_call_id,
            "tool_name": _TOOL_NAME,
            "normalized_arguments_digest": arguments_digest,
            "arguments_payload_digest": arguments_digest,
            "arguments_storage_kind": TOOL_CALL_ARGUMENTS_STORAGE_INLINE_JSON,
            "arguments_payload_ref": None,
            "arguments_inline_json": arguments_json,
            "arguments_json_size_bytes": len(
                canonical_json_dumps(arguments_json).encode("utf-8")
            ),
            "semantic_input_digest": _DIGEST,
            "semantic_query_storage_kind": (
                TOOL_CALL_SEMANTIC_QUERY_STORAGE_INLINE_TEXT
                if semantic_query_text is not None
                else TOOL_CALL_SEMANTIC_QUERY_STORAGE_ABSENT
            ),
            "semantic_query_text": semantic_query_text,
            "semantic_query_payload_ref": None,
            "semantic_query_digest": semantic_query_digest,
        },
    )


def _append_tool_result(
    transaction: HostTransaction,
    event_log: EventLogStore,
    *,
    event_id: str,
    tool_call_id: str,
    request_event_ref: str | None,
    normalized_arguments_digest: str,
    tool_fact_kind: str | None,
    raw_tool_outcome: JsonValue,
    source_refs: tuple[OpaqueEvidenceRef, ...],
    resolution_kind: str | None = None,
    payload_ref: str | None = None,
    payload_digest: str | None = None,
) -> EventLogRow:
    """追加测试用 ``TOOL_RESULT_ACCEPTED`` canonical fact。

    :param transaction: Host transaction。
    :param event_log: EventLog store。
    :param event_id: event id。
    :param tool_call_id: tool call id。
    :param request_event_ref: request atom event ref。
    :param normalized_arguments_digest: envelope 参数 digest。
    :param tool_fact_kind: 可选 durable tool fact kind。
    :param raw_tool_outcome: raw outcome JSON。
    :param source_refs: source refs。
    :param resolution_kind: 可选 wait resolution kind。
    :param payload_ref: 可选 raw result payload descriptor ref。
    :param payload_digest: 可选 raw result payload digest。
    :returns: appended EventLog row。
    """

    envelope = _accepted_envelope(
        event_id=event_id,
        tool_call_id=tool_call_id,
        request_event_ref=request_event_ref,
        normalized_arguments_digest=normalized_arguments_digest,
        raw_tool_outcome=raw_tool_outcome,
        source_refs=source_refs,
        payload_ref=payload_ref,
        payload_digest=payload_digest,
    )
    payload: dict[str, JsonValue] = {
        "tool_call_id": tool_call_id,
        "tool_name": _TOOL_NAME,
        "normalized_arguments_digest": normalized_arguments_digest,
        "accepted_evidence_envelope": accepted_evidence_envelope_to_json_value(
            envelope
        ),
        "raw_tool_outcome": raw_tool_outcome,
    }
    if tool_fact_kind is not None:
        payload["tool_fact_kind"] = tool_fact_kind
    if resolution_kind is not None:
        payload["resolution_kind"] = resolution_kind
    return _append_event(
        transaction,
        event_log,
        event_id=event_id,
        event_type="TOOL_RESULT_ACCEPTED",
        payload=payload,
    )


def _accepted_envelope(
    *,
    event_id: str,
    tool_call_id: str,
    request_event_ref: str | None,
    normalized_arguments_digest: str,
    raw_tool_outcome: JsonValue,
    source_refs: tuple[OpaqueEvidenceRef, ...],
    payload_ref: str | None = None,
    payload_digest: str | None = None,
) -> AcceptedEvidenceEnvelope:
    """构造测试用 accepted evidence envelope。

    :param event_id: result event id。
    :param tool_call_id: tool call id。
    :param request_event_ref: request atom event ref。
    :param normalized_arguments_digest: request 参数 digest。
    :param raw_tool_outcome: raw outcome JSON。
    :param source_refs: source refs。
    :param payload_ref: 可选 result payload descriptor ref。
    :param payload_digest: 可选 result payload digest。
    :returns: accepted evidence envelope。
    """

    return AcceptedEvidenceEnvelope(
        evidence_id=f"evidence:{event_id}",
        producer_event_ref=event_id,
        tool_name=_TOOL_NAME,
        tool_call_id=tool_call_id,
        tool_query=AcceptedEvidenceToolQuery(
            tool_call_requested_event_ref=request_event_ref,
            normalized_arguments_digest=normalized_arguments_digest,
            semantic_input_digest=_DIGEST,
        ),
        result_ref=AcceptedEvidenceResultRef(
            payload_ref=payload_ref,
            payload_digest=payload_digest,
            outcome_digest=sha256_digest_json(raw_tool_outcome),
            truncation_applied=False,
        ),
        source_refs=source_refs,
        locator_refs=(),
    )


def _append_event(
    transaction: HostTransaction,
    event_log: EventLogStore,
    *,
    event_id: str,
    event_type: str,
    payload: JsonValue,
    payload_ref: str | None = None,
    payload_digest: str | None = None,
) -> EventLogRow:
    """追加测试用 canonical EventLog row。

    :param transaction: Host transaction。
    :param event_log: EventLog store。
    :param event_id: event id。
    :param event_type: event type。
    :param payload: payload JSON。
    :param payload_ref: 可选 payload descriptor ref。
    :param payload_digest: 可选 payload descriptor digest。
    :returns: appended EventLog row。
    """

    return event_log.append_event(
        transaction,
        EventLogAppendRequest(
            event_id=event_id,
            event_class=EventClass.CANONICAL_FACT,
            session_id=_SESSION_ID,
            run_id=_RUN_ID,
            attempt_id=_ATTEMPT_ID,
            execution_id=_EXECUTION_ID,
            event_type=event_type,
            occurred_at=datetime(2026, 7, 9, tzinfo=UTC),
            actor="test",
            source="test.accepted_result_projection",
            client_request_id=None,
            idempotency_key=event_id,
            policy_decision=None,
            reason=None,
            payload_json=payload,
            payload_ref=payload_ref,
            payload_digest=payload_digest,
        ),
    ).row


def _run_row(input_event: EventLogRow) -> RunRow:
    """构造 compact material 读取所需的最小 RunRow。

    :param input_event: 当前 USER_INPUT_ACCEPTED event。
    :returns: RunRow。
    """

    return RunRow(
        run_id=_RUN_ID,
        session_id=input_event.session_id,
        status=RunStatus.QUEUED,
        client_request_id="client-request-projection",
        input_event_id=input_event.event_id,
        input_event_sequence=input_event.event_sequence,
        accepted_event_id=input_event.event_id,
        accepted_event_sequence=input_event.event_sequence,
        queued_event_id=None,
        queued_event_sequence=None,
        started_event_id=None,
        started_event_sequence=None,
        terminal_event_id=None,
        terminal_event_sequence=None,
        cancel_request_event_id=None,
        current_attempt_id=None,
        source_run_id=None,
        source_run_relation=None,
        execution_target="local",
        queue_policy="fifo",
        created_at="2026-07-09T00:00:00.000000Z",
        updated_at="2026-07-09T00:00:00.000000Z",
        terminal_at=None,
    )
