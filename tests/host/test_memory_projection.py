"""Host Conversation Memory vNext projection 与 durable primitive 测试。"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host.compact_payload import parse_context_compacted_semantic_payload
from dayu.host.compaction import (
    CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT,
    AnswerAnchorCandidateVNext,
    AnswerAnchorChildVNext,
    CompactQualityCheckResultVNext,
    ConversationCompactOutputVNext,
    EvidenceBackedFactCandidateVNext,
    FactEvidenceKindVNext,
    ForwardIntentCandidateVNext,
    ForwardIntentStatusVNext,
    ForwardIntentTypeVNext,
    ReferenceContinuityCandidateVNext,
    ReferenceContinuityReasonVNext,
    SessionSummaryCandidateVNext,
)
from dayu.host.context_events import (
    CONTEXT_COMPACTED,
    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
    CONTEXT_COMPACTION_FAILED,
    build_context_compacted_payload,
)
from dayu.host.durable import memory as durable_memory_module
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.connection import HostDurableStore
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    append_event,
)
from dayu.host.durable.memory import (
    ConversationMemoryProjectionConsumer,
    MemorySnapshotIntegrityFailureKind,
    conversation_memory_projection_event_filter,
    inspect_memory_snapshot_integrity,
    read_latest_memory_snapshot,
    read_memory_snapshot,
    write_memory_snapshot_with_checkpoint,
)
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
from dayu.host.durable.projection import read_projection_checkpoint
from dayu.host.durable.schema import (
    TABLE_HOST_MEMORY_ITEMS,
    TABLE_HOST_MEMORY_SNAPSHOTS,
    TOOL_CALL_ARGUMENTS_STORAGE_INLINE_JSON,
    TOOL_CALL_SEMANTIC_QUERY_STORAGE_ABSENT,
    TOOL_CALL_SEMANTIC_QUERY_STORAGE_INLINE_TEXT,
)
from dayu.host.durable.transaction import HostRow, HostTransaction
from dayu.host.evidence import (
    AcceptedEvidenceEnvelope,
    AcceptedEvidenceResultRef,
    AcceptedEvidenceToolQuery,
    accepted_evidence_envelope_to_json_value,
)
from dayu.host.evidence import (
    ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT,
    ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT,
    AcceptedToolEvidenceLLMMaterial,
    render_accepted_tool_evidence_for_llm,
)
from dayu.host.memory import (
    CONVERSATION_MEMORY_CONSUMER_ID,
    ConversationMemorySnapshotVNext,
    MemoryDiagnosticReason,
    MemoryIncludedReason,
    MemoryProjectionEvent,
    MemoryProjectionPolicy,
    SelectedRecentWindowRole,
    build_conversation_memory_snapshot_from_events,
    build_empty_conversation_memory_snapshot,
    calculate_memory_snapshot_digest,
    conversation_memory_snapshot_from_json_value,
    conversation_memory_snapshot_to_json_value,
    default_memory_projection_policy,
    digest_memory_projection_policy,
    project_conversation_memory_event,
    stable_memory_snapshot_id,
)
from dayu.host.projection import ProjectionRunner

_SESSION_ID = "session-1"
_RUN_ID = "run-1"
_ATTEMPT_ID = "attempt-1"
_EXECUTION_ID = "execution-1"
_NOW = "2026-05-16T00:00:00.000000Z"
_OCCURRED_AT = datetime(2026, 5, 16, tzinfo=UTC)
_REQUEST_PAYLOAD_KIND_VALID = "valid"
_REQUEST_PAYLOAD_KIND_INVALID = "invalid"
_FAIL_SAFE_QUERY_TEXT = "这个 request query 不应进入 memory"
_FAIL_SAFE_LIMITED_QUERY_TEXT = ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT
_COMPACT_ARTIFACT_DIGEST = (
    "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
)

_POLICY_FIELDS = (
    "context_window_size",
    "selected_recent_window_item_cap",
    "selected_recent_window_char_cap",
    "selected_recent_window_turn_floor",
    "fallback_selected_recent_window_item_cap",
    "fallback_selected_recent_window_char_cap",
    "evidence_fact_item_cap",
    "evidence_fact_char_cap",
    "evidence_fact_floor",
    "session_summary_char_cap",
    "answer_anchor_item_cap",
    "answer_anchor_char_cap",
    "forward_intent_item_cap",
    "forward_intent_char_cap",
    "reference_continuity_item_cap",
    "reference_continuity_char_cap",
    "reference_continuity_item_floor",
    "max_lag_events_for_inline_delta",
    "max_delta_repair_events",
    "policy_ref",
)

_SNAPSHOT_FIELDS = (
    "schema_version",
    "snapshot_id",
    "session_id",
    "cursor",
    "policy_digest",
    "latest_compaction_event_ref",
    "trace_memory",
    "evidence_fact_memory",
    "session_summary_memory",
    "answer_anchor_memory",
    "forward_intent_memory",
    "diagnostics",
    "built_at",
    "snapshot_digest",
)


@dataclass(frozen=True, slots=True)
class _ToolQueryFailSafeCase:
    """工具 evidence query fail-safe 分支测试参数。

    :param append_request: 是否写入 request row。
    :param request_session_id: request row session id。
    :param request_event_class: request row event class。
    :param request_event_type: request row event type。
    :param request_payload_kind: request payload 构造类型。
    :param request_tool_call_id: request atom 中的 tool call id。
    :param request_tool_name: request atom 中的工具名。
    :param envelope_tool_call_id: result envelope 中的 tool call id。
    :param envelope_tool_name: result envelope 中的工具名。
    :param envelope_arguments_digest: 可选 result envelope 参数 digest 覆写。
    """

    append_request: bool = True
    request_session_id: str = _SESSION_ID
    request_event_class: EventClass = EventClass.CANONICAL_FACT
    request_event_type: str = "TOOL_CALL_REQUESTED"
    request_payload_kind: str = _REQUEST_PAYLOAD_KIND_VALID
    request_tool_call_id: str = "tool-call-fail-safe-memory"
    request_tool_name: str = "list_documents"
    envelope_tool_call_id: str = "tool-call-fail-safe-memory"
    envelope_tool_name: str = "list_documents"
    envelope_arguments_digest: str | None = None


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试用 durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "host" / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(busy_timeout_seconds=0.25),
    )


def _policy() -> MemoryProjectionPolicy:
    """构造 vNext memory projection policy。

    :returns: memory projection policy。
    """

    return MemoryProjectionPolicy(
        context_window_size=8192,
        selected_recent_window_item_cap=8,
        selected_recent_window_char_cap=2048,
        selected_recent_window_turn_floor=2,
        fallback_selected_recent_window_item_cap=4,
        fallback_selected_recent_window_char_cap=1024,
        evidence_fact_item_cap=4,
        evidence_fact_char_cap=2048,
        evidence_fact_floor=1,
        session_summary_char_cap=1024,
        answer_anchor_item_cap=4,
        answer_anchor_char_cap=1024,
        forward_intent_item_cap=4,
        forward_intent_char_cap=1024,
        reference_continuity_item_cap=4,
        reference_continuity_char_cap=1024,
        reference_continuity_item_floor=0,
        max_lag_events_for_inline_delta=4,
        max_delta_repair_events=16,
        policy_ref="test-memory-vnext",
    )


def _event(
    sequence: int,
    event_id: str,
    event_type: str,
    payload: dict[str, JsonValue],
    *,
    run_id: str | None = _RUN_ID,
    assistant_final_answer_text: str | None = None,
    accepted_tool_evidence: AcceptedToolEvidenceLLMMaterial | None = None,
) -> MemoryProjectionEvent:
    """构造 memory projection event。

    :param sequence: EventLog sequence。
    :param event_id: event id。
    :param event_type: event type。
    :param payload: canonical payload。
    :param run_id: Host Run id。
    :param assistant_final_answer_text: 可选 typed assistant answer material。
    :param accepted_tool_evidence: accepted tool evidence typed material。
    :returns: memory projection event。
    """

    return MemoryProjectionEvent(
        event_sequence=sequence,
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT.value,
        event_type=event_type,
        session_id=_SESSION_ID,
        run_id=run_id,
        attempt_id=_ATTEMPT_ID,
        execution_id=_EXECUTION_ID,
        occurred_at=_NOW,
        payload_ref=None,
        payload_digest=None,
        payload=payload,
        compacted_semantics=(
            parse_context_compacted_semantic_payload(payload)
            if event_type == CONTEXT_COMPACTED
            else None
        ),
        assistant_final_answer_text=assistant_final_answer_text,
        accepted_tool_evidence=accepted_tool_evidence,
    )


def _llm_facing_memory_text_view(
    snapshot: ConversationMemorySnapshotVNext,
) -> tuple[
    tuple[tuple[SelectedRecentWindowRole, str], ...],
    tuple[tuple[SelectedRecentWindowRole, str], ...],
]:
    """提取 LLM-facing memory 的稳定 role/text 等价视图。

    :param snapshot: conversation memory snapshot。
    :returns: selected recent window 与 recent evidence 的 role/text 视图。
    """

    selected = tuple(
        (item.role, item.text)
        for item in snapshot.trace_memory.selected_recent_window
    )
    recent_evidence = tuple(
        (item.role, item.text)
        for item in snapshot.evidence_fact_memory.recent_evidence_items
    )
    return selected, recent_evidence


def _accepted_compact_payload(
    *,
    facts: list[EvidenceBackedFactCandidateVNext] | None = None,
    summary_text: str = "用户关注收入增速和毛利率变化。",
) -> dict[str, JsonValue]:
    """构造 accepted vNext compact payload。

    :param facts: 可选 evidence-backed fact candidates。
    :param summary_text: session summary 文本。
    :returns: CONTEXT_COMPACTED payload。
    """

    candidate = ConversationCompactOutputVNext(
        schema_version=CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT,
        session_summary=SessionSummaryCandidateVNext(
            summary_text=summary_text,
            source_labels=("u1",),
        ),
        evidence_backed_facts=() if facts is None else tuple(facts),
        answer_anchors=(
            AnswerAnchorCandidateVNext(
                anchor_title="收入口径",
                anchor_items=(
                    AnswerAnchorChildVNext(
                        display_text="同比收入增速来自已接受证据。",
                        ordinal=1,
                    ),
                    AnswerAnchorChildVNext(
                        display_text="毛利率口径保持一致。",
                        ordinal=2,
                    ),
                ),
                answer_source_labels=("e1",),
            ),
        ),
        forward_intents=(
            ForwardIntentCandidateVNext(
                intent_type=ForwardIntentTypeVNext.NEXT_STEP_NOTE,
                text="下一轮继续核对费用率。",
                status=ForwardIntentStatusVNext.OPEN,
                source_labels=("u1",),
            ),
        ),
        reference_continuity_items=(
            ReferenceContinuityCandidateVNext(
                text="“该公司”继续指向当前分析主体。",
                reason=ReferenceContinuityReasonVNext.LOCAL_REFERENCE,
                source_labels=("u1",),
            ),
        ),
        diagnostics=(),
    )
    return dict(
        build_context_compacted_payload(
            operation_id="event-context-compaction-requested-1",
            accepted_attempt_number=1,
            compact_artifact_ref="artifact:compact-1",
            compact_artifact_digest=_COMPACT_ARTIFACT_DIGEST,
            accepted_candidate=candidate,
            quality_check_result=CompactQualityCheckResultVNext(
                accepted=True,
                rejection_reasons=(),
            ),
            budget_after_compact=512,
            prompt_local_label_mapping_refs=("prompt-label:u1", "prompt-label:e1"),
            source_boundary_refs=("event:user-1",),
            accepted_evidence_mapping_refs=("event:tool-1",),
            projection_signal="conversation_memory_projection_catchup",
        )
    )


def _tool_call_requested_payload(
    *,
    tool_call_id: str,
    tool_name: str,
    arguments_json: Mapping[str, JsonValue],
    semantic_input_digest: str,
    semantic_query_text: str | None,
) -> dict[str, JsonValue]:
    """构造最小合法 ``TOOL_CALL_REQUESTED`` payload。

    :param tool_call_id: 工具调用 id。
    :param tool_name: 工具名。
    :param arguments_json: accepted arguments canonical JSON。
    :param semantic_input_digest: Host accept semantic input digest。
    :param semantic_query_text: 可选业务可读 semantic query 文本。
    :returns: EventLog payload JSON object。
    """

    arguments_digest = sha256_digest_json(arguments_json)
    payload: dict[str, JsonValue] = {
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "normalized_arguments_digest": arguments_digest,
        "arguments_payload_digest": arguments_digest,
        "arguments_storage_kind": TOOL_CALL_ARGUMENTS_STORAGE_INLINE_JSON,
        "arguments_inline_json": arguments_json,
        "arguments_payload_ref": None,
        "arguments_json_size_bytes": len(
            canonical_json_dumps(arguments_json).encode("utf-8")
        ),
        "semantic_input_digest": semantic_input_digest,
    }
    if semantic_query_text is None:
        payload.update(
            {
                "semantic_query_storage_kind": (
                    TOOL_CALL_SEMANTIC_QUERY_STORAGE_ABSENT
                ),
                "semantic_query_text": None,
                "semantic_query_payload_ref": None,
                "semantic_query_digest": None,
            }
        )
        return payload
    payload.update(
        {
            "semantic_query_storage_kind": TOOL_CALL_SEMANTIC_QUERY_STORAGE_INLINE_TEXT,
            "semantic_query_text": semantic_query_text,
            "semantic_query_payload_ref": None,
            "semantic_query_digest": sha256_digest_json(
                {"semantic_query_text": semantic_query_text}
            ),
        }
    )
    return payload


def _accepted_tool_result_payload(
    *,
    result_event_id: str,
    request_event_id: str | None,
    tool_call_id: str,
    tool_name: str,
    arguments_digest: str,
    semantic_input_digest: str,
    raw_tool_outcome: JsonValue,
) -> dict[str, JsonValue]:
    """构造带 accepted evidence envelope 的工具结果 payload。

    :param result_event_id: ``TOOL_RESULT_ACCEPTED`` event id。
    :param request_event_id: 对应 ``TOOL_CALL_REQUESTED`` event id；缺失时为
        ``None``。
    :param tool_call_id: 工具调用 id。
    :param tool_name: 工具名。
    :param arguments_digest: accepted arguments digest。
    :param semantic_input_digest: Host accept semantic input digest。
    :param raw_tool_outcome: 原始工具响应 JSON 值。
    :returns: EventLog payload JSON object。
    """

    envelope = AcceptedEvidenceEnvelope(
        evidence_id=f"evidence:{result_event_id}",
        producer_event_ref=result_event_id,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        tool_query=AcceptedEvidenceToolQuery(
            tool_call_requested_event_ref=request_event_id,
            normalized_arguments_digest=arguments_digest,
            semantic_input_digest=semantic_input_digest,
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
    return {
        "accepted_evidence_envelope": accepted_evidence_envelope_to_json_value(
            envelope
        ),
        "raw_tool_outcome": raw_tool_outcome,
    }


def _append_tool_request_and_result_events(
    transaction: HostTransaction,
    *,
    request_event_id: str,
    result_event_id: str,
    request_payload: dict[str, JsonValue],
    result_payload: dict[str, JsonValue],
    append_request: bool = True,
    request_session_id: str = _SESSION_ID,
    request_event_class: EventClass = EventClass.CANONICAL_FACT,
    request_event_type: str = "TOOL_CALL_REQUESTED",
    request_run_id: str | None = _RUN_ID,
    request_attempt_id: str | None = _ATTEMPT_ID,
    request_execution_id: str | None = _EXECUTION_ID,
    result_run_id: str | None = _RUN_ID,
    result_attempt_id: str | None = _ATTEMPT_ID,
    result_execution_id: str | None = _EXECUTION_ID,
) -> None:
    """追加一组 request/result canonical EventLog facts。

    :param transaction: Host transaction。
    :param request_event_id: ``TOOL_CALL_REQUESTED`` event id。
    :param result_event_id: ``TOOL_RESULT_ACCEPTED`` event id。
    :param request_payload: request payload。
    :param result_payload: result payload。
    :param append_request: 是否写入 request row。
    :param request_session_id: request row session id。
    :param request_event_class: request row event class。
    :param request_event_type: request row event type。
    :param request_run_id: request row run id。
    :param request_attempt_id: request row attempt id。
    :param request_execution_id: request row execution id。
    :param result_run_id: result row run id。
    :param result_attempt_id: result row attempt id。
    :param result_execution_id: result row execution id。
    :returns: ``None``。
    """

    if append_request:
        append_event(
            transaction,
            EventLogAppendRequest(
                event_id=request_event_id,
                event_class=request_event_class,
                session_id=request_session_id,
                run_id=request_run_id,
                attempt_id=request_attempt_id,
                execution_id=request_execution_id,
                event_type=request_event_type,
                occurred_at=_OCCURRED_AT,
                actor="pytest",
                source="pytest",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason=None,
                payload_json=request_payload,
                payload_ref=None,
                payload_digest=None,
            ),
        )
    append_event(
        transaction,
        EventLogAppendRequest(
            event_id=result_event_id,
            event_class=EventClass.CANONICAL_FACT,
            session_id=_SESSION_ID,
            run_id=result_run_id,
            attempt_id=result_attempt_id,
            execution_id=result_execution_id,
            event_type="TOOL_RESULT_ACCEPTED",
            occurred_at=_OCCURRED_AT,
            actor="pytest",
            source="pytest",
            client_request_id=None,
            idempotency_key=None,
            policy_decision=None,
            reason=None,
            payload_json=result_payload,
            payload_ref=None,
            payload_digest=None,
        ),
    )


def _fail_safe_request_payload(
    case: _ToolQueryFailSafeCase,
    *,
    arguments_json: Mapping[str, JsonValue],
    semantic_input_digest: str,
) -> dict[str, JsonValue]:
    """按 fail-safe case 构造 request payload。

    :param case: fail-safe case。
    :param arguments_json: accepted arguments canonical JSON。
    :param semantic_input_digest: Host accept semantic input digest。
    :returns: request payload。
    :raises ValueError: 未知 request payload 类型时抛出。
    """

    if case.request_payload_kind == _REQUEST_PAYLOAD_KIND_VALID:
        return _tool_call_requested_payload(
            tool_call_id=case.request_tool_call_id,
            tool_name=case.request_tool_name,
            arguments_json=arguments_json,
            semantic_input_digest=semantic_input_digest,
            semantic_query_text=_FAIL_SAFE_QUERY_TEXT,
        )
    if case.request_payload_kind == _REQUEST_PAYLOAD_KIND_INVALID:
        return {"tool_call_id": case.request_tool_call_id}
    raise ValueError("unknown fail-safe request payload kind")


def _project_tool_query_fail_safe_case(
    tmp_path: Path,
    case: _ToolQueryFailSafeCase,
) -> str:
    """运行单个工具 query fail-safe projection case 并返回 memory 文本。

    :param tmp_path: pytest 临时目录。
    :param case: fail-safe case。
    :returns: selected recent window 中的工具 evidence 文本。
    """

    policy = _policy()
    request_event_id = "event-tool-call-requested-query-fail-safe-memory"
    result_event_id = "event-tool-result-query-fail-safe-memory"
    arguments_json: Mapping[str, JsonValue] = {"arguments": {"ticker": "COIN"}}
    arguments_digest = sha256_digest_json(arguments_json)
    semantic_input_digest = sha256_digest_json({"semantic_input": "COIN"})
    envelope_arguments_digest = (
        arguments_digest
        if case.envelope_arguments_digest is None
        else case.envelope_arguments_digest
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: _append_tool_request_and_result_events(
                transaction,
                request_event_id=request_event_id,
                result_event_id=result_event_id,
                request_payload=_fail_safe_request_payload(
                    case,
                    arguments_json=arguments_json,
                    semantic_input_digest=semantic_input_digest,
                ),
                result_payload=_accepted_tool_result_payload(
                    result_event_id=result_event_id,
                    request_event_id=request_event_id,
                    tool_call_id=case.envelope_tool_call_id,
                    tool_name=case.envelope_tool_name,
                    arguments_digest=envelope_arguments_digest,
                    semantic_input_digest=semantic_input_digest,
                    raw_tool_outcome={"status": "raw outcome retained"},
                ),
                append_request=case.append_request,
                request_session_id=case.request_session_id,
                request_event_class=case.request_event_class,
                request_event_type=case.request_event_type,
            )
        )
        consumer = ConversationMemoryProjectionConsumer(policy)
        ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            consumer.consumer_id,
            limit=10,
        )
        latest = store.transaction_runner.run_read(
            lambda transaction: read_latest_memory_snapshot(
                transaction,
                session_id=_SESSION_ID,
                consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                policy_digest=digest_memory_projection_policy(policy),
            )
        )
        assert latest is not None
        return latest.snapshot.trace_memory.selected_recent_window[0].text
    raise AssertionError("tool query fail-safe projection did not return memory text")


def _fact(claim_text: str) -> EvidenceBackedFactCandidateVNext:
    """构造 fact candidate。

    :param claim_text: fact claim 文本。
    :returns: typed fact candidate。
    """

    return EvidenceBackedFactCandidateVNext(
        claim_text=claim_text,
        evidence_labels=("e1",),
        evidence_kind=FactEvidenceKindVNext.ACCEPTED_EVIDENCE_MATERIAL,
        source_labels=("e1",),
    )


def _memory_item_count(transaction: HostTransaction) -> int:
    """读取 memory item durable row 数。

    :param transaction: Host transaction。
    :returns: memory item row 数。
    """

    row = transaction.fetchone(
        f"SELECT COUNT(*) AS count FROM {TABLE_HOST_MEMORY_ITEMS}"
    )
    assert row is not None
    count = row.get("count")
    assert isinstance(count, int)
    return count


def test_memory_projection_policy_contract_uses_design_source_fields() -> None:
    """MemoryProjectionPolicy 字段集合只包含设计真源字段。"""

    assert tuple(field.name for field in fields(MemoryProjectionPolicy)) == _POLICY_FIELDS


def test_conversation_memory_snapshot_vnext_contract_fields_are_fixed() -> None:
    """ConversationMemorySnapshotVNext 字段集合固定为 vNext contract。"""

    assert (
        tuple(field.name for field in fields(ConversationMemorySnapshotVNext))
        == _SNAPSHOT_FIELDS
    )


def test_pre_compact_projection_only_builds_selected_recent_window() -> None:
    """compact 前 projection 只形成 selected recent window 可读材料。"""

    policy = _policy()
    snapshot = build_conversation_memory_snapshot_from_events(
        events=(
            _event(1, "user-1", "USER_INPUT_ACCEPTED", {"display_text": "请分析收入。"}),
            _event(2, "run-1", "RUN_SUCCEEDED", {"final_answer": "收入同比增长。"}),
            _event(
                3,
                "tool-1",
                "TOOL_RESULT_ACCEPTED",
                {"display_text": "10-K revenue table"},
            ),
        ),
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )

    assert tuple(
        item.role for item in snapshot.trace_memory.selected_recent_window
    ) == (
        SelectedRecentWindowRole.USER,
        SelectedRecentWindowRole.ASSISTANT,
        SelectedRecentWindowRole.EVIDENCE,
    )
    assistant_item = snapshot.trace_memory.selected_recent_window[1]
    assert assistant_item.included_reason is MemoryIncludedReason.SELECTED_RECENT_WINDOW
    assert snapshot.session_summary_memory.summary_text is None
    assert snapshot.evidence_fact_memory.evidence_backed_facts == ()
    assert snapshot.answer_anchor_memory.anchors == ()
    assert snapshot.forward_intent_memory.intents == ()


def test_tool_awaiting_does_not_project_llm_facing_memory() -> None:
    """TOOL_AWAITING 不应形成 awaiting 专属 LLM-facing memory。"""

    policy = _policy()
    arguments = {"ticker": "CRCL"}
    arguments_digest = sha256_digest_json({"arguments": arguments})
    snapshot = build_conversation_memory_snapshot_from_events(
        events=(
            _event(1, "user-1", "USER_INPUT_ACCEPTED", {"display_text": "下载Circle财报"}),
            _event(
                2,
                "awaiting-1",
                "TOOL_AWAITING",
                {
                    "tool_name": "start_fins_download",
                    "accepted_arguments": arguments,
                    "accepted_arguments_source_digest": arguments_digest,
                    "normalized_arguments_digest": arguments_digest,
                },
            ),
        ),
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )

    selected = snapshot.trace_memory.selected_recent_window
    evidence = snapshot.evidence_fact_memory.recent_evidence_items
    assert tuple(item.role for item in selected) == (SelectedRecentWindowRole.USER,)
    assert evidence == ()
    memory_text = "\n".join(
        item.text for item in snapshot.trace_memory.selected_recent_window
    )
    forbidden_fragments = (
        "等待",
        "awaiting",
        "外部工具",
        "任务",
        "启动",
        "取消",
        "abandoned",
        "poll",
        "已接受",
    )
    for fragment in forbidden_fragments:
        assert fragment not in memory_text
    assert "start_fins_download" not in memory_text
    assert "CRCL" not in memory_text


def test_tool_awaiting_presence_does_not_change_llm_facing_memory_semantics() -> None:
    """有无 TOOL_AWAITING 时，相同普通事实应生成相同 LLM-facing memory。"""

    policy = _policy()
    ordinary_events = (
        _event(1, "user-1", "USER_INPUT_ACCEPTED", {"display_text": "下载Circle财报"}),
        _event(
            3,
            "tool-result-1",
            "TOOL_RESULT_ACCEPTED",
            {"display_text": "下载工具返回：已保存 Circle 2024 10-K。"},
        ),
        _event(4, "run-1", "RUN_SUCCEEDED", {"final_answer": "Circle 财报已保存。"}),
    )
    arguments = {"ticker": "CRCL"}
    arguments_digest = sha256_digest_json({"arguments": arguments})
    with_awaiting_events = (
        ordinary_events[0],
        _event(
            2,
            "awaiting-1",
            "TOOL_AWAITING",
            {
                "tool_name": "start_fins_download",
                "accepted_arguments": arguments,
                "accepted_arguments_source_digest": arguments_digest,
                "normalized_arguments_digest": arguments_digest,
            },
        ),
        ordinary_events[1],
        ordinary_events[2],
    )

    ordinary_snapshot = build_conversation_memory_snapshot_from_events(
        events=ordinary_events,
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )
    with_awaiting_snapshot = build_conversation_memory_snapshot_from_events(
        events=with_awaiting_events,
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )

    assert (
        _llm_facing_memory_text_view(with_awaiting_snapshot)
        == _llm_facing_memory_text_view(ordinary_snapshot)
    )
    selected_view, evidence_view = _llm_facing_memory_text_view(with_awaiting_snapshot)
    memory_text = "\n".join(text for _, text in selected_view + evidence_view)
    assert "TOOL_AWAITING" not in memory_text
    assert "start_fins_download" not in memory_text
    assert "CRCL" not in memory_text


def test_selected_recent_window_floor_protects_recent_run_groups() -> None:
    """selected recent window floor 保护最近 Run group 的全部 eligible material。"""

    policy = MemoryProjectionPolicy(
        context_window_size=8192,
        selected_recent_window_item_cap=2,
        selected_recent_window_char_cap=4096,
        selected_recent_window_turn_floor=2,
        fallback_selected_recent_window_item_cap=2,
        fallback_selected_recent_window_char_cap=2048,
        evidence_fact_item_cap=4,
        evidence_fact_char_cap=2048,
        evidence_fact_floor=1,
        session_summary_char_cap=1024,
        answer_anchor_item_cap=4,
        answer_anchor_char_cap=1024,
        forward_intent_item_cap=4,
        forward_intent_char_cap=1024,
        reference_continuity_item_cap=4,
        reference_continuity_char_cap=1024,
        reference_continuity_item_floor=0,
        max_lag_events_for_inline_delta=4,
        max_delta_repair_events=16,
        policy_ref="test-memory-vnext",
    )
    snapshot = build_conversation_memory_snapshot_from_events(
        events=(
            _event(
                1,
                "user-old",
                "USER_INPUT_ACCEPTED",
                {"display_text": "old user"},
                run_id="run-old",
            ),
            _event(
                2,
                "answer-old",
                "RUN_SUCCEEDED",
                {"final_answer": "old answer"},
                run_id="run-old",
            ),
            _event(
                3,
                "user-mid",
                "USER_INPUT_ACCEPTED",
                {"display_text": "mid user"},
                run_id="run-mid",
            ),
            _event(
                4,
                "answer-mid",
                "RUN_SUCCEEDED",
                {"final_answer": "mid answer"},
                run_id="run-mid",
            ),
            _event(
                5,
                "tool-mid",
                "TOOL_RESULT_ACCEPTED",
                {"display_text": "mid evidence"},
                run_id="run-mid",
            ),
            _event(
                6,
                "user-new",
                "USER_INPUT_ACCEPTED",
                {"display_text": "new user"},
                run_id="run-new",
            ),
            _event(
                7,
                "answer-new",
                "RUN_SUCCEEDED",
                {"final_answer": "new answer"},
                run_id="run-new",
            ),
            _event(
                8,
                "tool-new",
                "TOOL_RESULT_ACCEPTED",
                {"display_text": "new evidence"},
                run_id="run-new",
            ),
        ),
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )

    selected = snapshot.trace_memory.selected_recent_window
    assert tuple(item.run_id for item in selected) == (
        "run-mid",
        "run-mid",
        "run-mid",
        "run-new",
        "run-new",
        "run-new",
    )
    fallback_text = render_accepted_tool_evidence_for_llm(None)
    assert tuple(item.text for item in selected) == (
        "mid user",
        "mid answer",
        fallback_text,
        "new user",
        "new answer",
        fallback_text,
    )


def test_selected_recent_window_floor_skips_missing_run_id_group() -> None:
    """缺 run_id 的 item 不参与 turn floor 保护，也不阻断 projection。"""

    policy = replace(
        _policy(),
        selected_recent_window_item_cap=1,
        selected_recent_window_turn_floor=1,
        fallback_selected_recent_window_item_cap=1,
    )
    snapshot = build_conversation_memory_snapshot_from_events(
        events=(
            _event(
                1,
                "user-missing-run",
                "USER_INPUT_ACCEPTED",
                {"display_text": "missing run"},
                run_id=None,
            ),
            _event(
                2,
                "user-with-run",
                "USER_INPUT_ACCEPTED",
                {"display_text": "with run"},
                run_id="run-with-id",
            ),
        ),
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )

    assert tuple(item.text for item in snapshot.trace_memory.selected_recent_window) == (
        "with run",
    )


def test_accepted_compact_materializes_vnext_memory_sections() -> None:
    """accepted CONTEXT_COMPACTED 物化 vNext memory sections。"""

    policy = _policy()
    snapshot = build_conversation_memory_snapshot_from_events(
        events=(
            _event(1, "user-1", "USER_INPUT_ACCEPTED", {"display_text": "请分析收入。"}),
            _event(
                2,
                "compact-1",
                CONTEXT_COMPACTED,
                _accepted_compact_payload(facts=[_fact("收入同比增长 12%。")]),
            ),
        ),
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )

    assert snapshot.latest_compaction_event_ref == "compact-1"
    assert snapshot.session_summary_memory.summary_text == "用户关注收入增速和毛利率变化。"
    assert snapshot.evidence_fact_memory.evidence_backed_facts[0].claim_text == (
        "收入同比增长 12%。"
    )
    assert snapshot.answer_anchor_memory.anchors[0].anchor_title == "收入口径"
    assert tuple(
        (child.display_text, child.ordinal)
        for child in snapshot.answer_anchor_memory.anchors[0].anchor_items
    ) == (
        ("同比收入增速来自已接受证据。", 1),
        ("毛利率口径保持一致。", 2),
    )
    assert (
        snapshot.forward_intent_memory.intents[0].intent_type
        is ForwardIntentTypeVNext.NEXT_STEP_NOTE
    )
    assert (
        snapshot.forward_intent_memory.intents[0].status
        is ForwardIntentStatusVNext.OPEN
    )
    assert snapshot.forward_intent_memory.intents[0].text == "下一轮继续核对费用率。"
    assert snapshot.trace_memory.reference_continuity_items[0].reason is (
        ReferenceContinuityReasonVNext.LOCAL_REFERENCE
    )


def test_run_succeeded_summary_only_does_not_materialize_assistant_window() -> None:
    """只有 summary_text 或 nested summary 时不生成 assistant selected recent item。"""

    policy = _policy()
    snapshot = build_conversation_memory_snapshot_from_events(
        events=(
            _event(
                1,
                "run-summary-only",
                "RUN_SUCCEEDED",
                {
                    "summary_text": "摘要不应进入 assistant final answer",
                    "summary": {"summary_text": "nested 摘要也不应进入"},
                },
            ),
        ),
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )

    assert snapshot.trace_memory.selected_recent_window == ()
    assert snapshot.session_summary_memory.summary_text is None


def test_run_succeeded_payload_refs_do_not_materialize_assistant_window() -> None:
    """缺失 final answer 时不把 ref / digest / event id 投影给 assistant window。"""

    policy = _policy()
    event = _event(1, "run-ref-only", "RUN_SUCCEEDED", {})
    event = replace(event, payload_ref="payload-run", payload_digest="sha256:digest")

    snapshot = build_conversation_memory_snapshot_from_events(
        events=(event,),
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )

    assert snapshot.trace_memory.selected_recent_window == ()


def test_user_input_missing_display_text_does_not_expose_refs() -> None:
    """USER_INPUT_ACCEPTED 缺 display_text 时不把内部 refs 投给 LLM。

    :returns: ``None``。
    :raises AssertionError: selected recent user text 泄漏内部治理标识时抛出。
    """

    policy = _policy()
    event = _event(1, "event-user-input-ref-only", "USER_INPUT_ACCEPTED", {})
    event = replace(
        event,
        payload_ref="payload-user-input-ref-only",
        payload_digest=sha256_digest_json({"display_text": "hidden"}),
    )

    snapshot = build_conversation_memory_snapshot_from_events(
        events=(event,),
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )

    selected = snapshot.trace_memory.selected_recent_window
    assert len(selected) == 1
    text = selected[0].text
    assert selected[0].role is SelectedRecentWindowRole.USER
    assert "event_ref=" not in text
    assert "payload_ref=" not in text
    assert "payload_digest=" not in text
    assert "sha256:" not in text
    assert "event-user-input-ref-only" not in text
    assert "payload-user-input-ref-only" not in text


def test_typed_terminal_answer_material_becomes_selected_recent_window() -> None:
    """typed assistant answer material 进入 selected recent window。

    :returns: ``None``。
    :raises AssertionError: typed material 没有被 memory consumer 消费时抛出。
    """

    policy = _policy()
    snapshot = build_conversation_memory_snapshot_from_events(
        events=(
            _event(
                1,
                "run-typed-answer",
                "RUN_SUCCEEDED",
                {
                    "terminal_summary_ref": "payload-terminal-final-answer",
                    "terminal_summary_digest": "sha256:terminal-final-answer",
                    "content": "裸 content 不应进入 assistant window",
                },
                assistant_final_answer_text="typed final answer",
            ),
        ),
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )

    selected = snapshot.trace_memory.selected_recent_window
    assert len(selected) == 1
    assert selected[0].text == "typed final answer"


def test_durable_projection_uses_typed_terminal_answer_material(
    tmp_path: Path,
) -> None:
    """durable projection 通过 typed terminal answer material 进入 continuity。"""

    policy = _policy()
    with open_host_durable_store(_options(tmp_path)) as store:

        def append_run_succeeded(transaction: HostTransaction) -> None:
            """写入 terminal artifact 与仅含 descriptor 的 RUN_SUCCEEDED。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            descriptor = PayloadStore().write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref="payload-terminal-final-answer",
                    payload_id="sqlite-terminal-final-answer",
                    payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                    payload_json={
                        "content": "artifact final answer",
                        "summary_text": "artifact summary",
                    },
                ),
            )
            append_event(
                transaction,
                EventLogAppendRequest(
                    event_id="run-terminal-content",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=_SESSION_ID,
                    run_id=_RUN_ID,
                    attempt_id=_ATTEMPT_ID,
                    execution_id=_EXECUTION_ID,
                    event_type="RUN_SUCCEEDED",
                    occurred_at=_OCCURRED_AT,
                    actor="pytest",
                    source="pytest",
                    client_request_id=None,
                    idempotency_key=None,
                    policy_decision=None,
                    reason=None,
                    payload_json={
                        "final_answer": " ",
                        "content": "裸 content 不应进入 assistant window",
                        "summary_text": "run summary 不应进入 assistant window",
                        "terminal_summary_ref": descriptor.payload_ref,
                        "terminal_summary_digest": descriptor.payload_digest,
                    },
                    payload_ref=None,
                    payload_digest=None,
                ),
            )

        store.transaction_runner.run_write(append_run_succeeded)
        consumer = ConversationMemoryProjectionConsumer(policy)
        ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            consumer.consumer_id,
            limit=10,
        )
        policy_digest = digest_memory_projection_policy(policy)
        latest = store.transaction_runner.run_read(
            lambda transaction: read_latest_memory_snapshot(
                transaction,
                session_id=_SESSION_ID,
                consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                policy_digest=policy_digest,
            )
        )

        assert latest is not None
        selected = latest.snapshot.trace_memory.selected_recent_window
        assert len(selected) == 1
        assert selected[0].text == "artifact final answer"
        assert selected[0].text != " "
        for fragment in (
            "terminal_summary_ref",
            "terminal_summary_digest",
            "payload_ref",
            "payload_digest",
            "artifact_ref",
            "event_id",
            "digest",
            "cursor",
            "payload-terminal-final-answer",
            "sha256:",
        ):
            assert fragment not in selected[0].text
        assert selected[0].included_reason is MemoryIncludedReason.SELECTED_RECENT_WINDOW
        assert latest.snapshot.evidence_fact_memory.evidence_backed_facts == ()


def test_memory_direct_consumer_does_not_follow_terminal_descriptor() -> None:
    """直接 memory consumer 在无 typed material 时不跟随 descriptor。

    Durable projection / RunInputBuilder 负责提供 digest-checked typed answer
    material；纯 consumer 没有 typed material 时只读取 inline ``final_answer``。

    :returns: ``None``。
    :raises AssertionError: direct consumer 错误跟随 descriptor 时抛出。
    """

    policy = _policy()
    snapshot = build_conversation_memory_snapshot_from_events(
        events=(
            _event(
                1,
                "run-descriptor-only",
                "RUN_SUCCEEDED",
                {
                    "terminal_summary_ref": "payload-terminal-final-answer",
                    "terminal_summary_digest": "sha256:terminal-final-answer",
                    "content": "裸 content 不应进入 assistant window",
                    "summary_text": "summary 不应进入 assistant window",
                },
            ),
        ),
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )

    assert snapshot.trace_memory.selected_recent_window == ()
    assert snapshot.evidence_fact_memory.evidence_backed_facts == ()


def test_accepted_tool_evidence_includes_query_and_raw_outcome_without_refs() -> None:
    """accepted tool evidence 投影自解释 query 与原始工具响应。

    :returns: ``None``。
    :raises AssertionError: memory 错误读取 preview、内部 id 或 payload ref 时抛出。
    """

    policy = _policy()
    event_id = "event-tool-result-raw-memory"
    envelope = AcceptedEvidenceEnvelope(
        evidence_id="evidence:tool-result-raw-memory",
        producer_event_ref=event_id,
        tool_name="lookup_mock_fact",
        tool_call_id="tool-call-raw-memory",
        tool_query=AcceptedEvidenceToolQuery(
            tool_call_requested_event_ref="event-tool-call-raw-memory",
            normalized_arguments_digest=sha256_digest_json({"query": "DAYU"}),
            semantic_input_digest=sha256_digest_json("DAYU"),
        ),
        result_ref=AcceptedEvidenceResultRef(
            payload_ref="payload-tool-result-raw-memory",
            payload_digest=sha256_digest_json(
                {"status": "ok", "text": "tool fact accepted"}
            ),
            outcome_digest=sha256_digest_json(
                {"status": "ok", "text": "tool fact accepted"}
            ),
            truncation_applied=False,
        ),
        locator_refs=(),
        source_refs=(),
    )
    snapshot = build_conversation_memory_snapshot_from_events(
        events=(
            _event(
                1,
                event_id,
                "TOOL_RESULT_ACCEPTED",
                {
                    "accepted_evidence_envelope": (
                        accepted_evidence_envelope_to_json_value(envelope)
                    ),
                    "display_text": "preview display must not enter memory",
                    "content": "preview content must not enter memory",
                    "raw_tool_outcome": {
                        "status": "ok",
                        "text": "tool fact accepted",
                    },
                },
                accepted_tool_evidence=AcceptedToolEvidenceLLMMaterial(
                    tool_name="lookup_mock_fact",
                    query_text="查询 DAYU 的业务事实",
                    source_text=ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT,
                    result_text=canonical_json_dumps(
                        {"status": "ok", "text": "tool fact accepted"}
                    ),
                ),
            ),
        ),
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )

    selected = snapshot.trace_memory.selected_recent_window
    assert len(selected) == 1
    text = selected[0].text
    assert "lookup_mock_fact" in text
    assert "查询 DAYU 的业务事实" in text
    assert ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT in text
    assert "tool fact accepted" in text
    assert "preview display" not in text
    assert "preview content" not in text
    assert event_id not in text
    assert "event-tool-call-raw-memory" not in text
    assert "tool-call-raw-memory" not in text
    assert "payload-tool-result-raw-memory" not in text
    assert "sha256:" not in text


def test_accepted_tool_evidence_disambiguates_raw_result_with_request_query() -> None:
    """raw tool outcome 含义不完整时，memory 文本必须带 request/query 语义。"""

    policy = _policy()
    event_id = "event-tool-result-ambiguous-memory"
    envelope = AcceptedEvidenceEnvelope(
        evidence_id="evidence:tool-result-ambiguous-memory",
        producer_event_ref=event_id,
        tool_name="list_documents",
        tool_call_id="tool-call-ambiguous-memory",
        tool_query=AcceptedEvidenceToolQuery(
            tool_call_requested_event_ref="event-tool-call-ambiguous-memory",
            normalized_arguments_digest=sha256_digest_json({"query": "COIN"}),
            semantic_input_digest=sha256_digest_json("COIN"),
        ),
        result_ref=AcceptedEvidenceResultRef(
            payload_ref="payload-tool-result-ambiguous-memory",
            payload_digest=sha256_digest_json({"total": 0, "documents": []}),
            outcome_digest=sha256_digest_json({"total": 0, "documents": []}),
            truncation_applied=False,
        ),
        locator_refs=(),
        source_refs=(),
    )
    snapshot = build_conversation_memory_snapshot_from_events(
        events=(
            _event(
                1,
                event_id,
                "TOOL_RESULT_ACCEPTED",
                {
                    "accepted_evidence_envelope": (
                        accepted_evidence_envelope_to_json_value(envelope)
                    ),
                    "raw_tool_outcome": {"total": 0, "documents": []},
                },
                accepted_tool_evidence=AcceptedToolEvidenceLLMMaterial(
                    tool_name="list_documents",
                    query_text="读取 ticker=COIN 的财报列表",
                    source_text=ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT,
                    result_text=canonical_json_dumps(
                        {"total": 0, "documents": []}
                    ),
                ),
            ),
        ),
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )

    text = snapshot.trace_memory.selected_recent_window[0].text
    assert "list_documents" in text
    assert "读取 ticker=COIN 的财报列表" in text
    assert '"total":0' in text
    forbidden_fragments = (
        "tool-call-ambiguous-memory",
        "event-tool-call-ambiguous-memory",
        event_id,
        "payload-tool-result-ambiguous-memory",
        "sha256:",
        "wait",
        "awaiting",
        "poll",
        "cancel",
        "EventLog",
        "payload ref",
        "artifact ref",
    )
    for fragment in forbidden_fragments:
        assert fragment not in text


def test_accepted_tool_evidence_missing_projection_fields_fail_closed() -> None:
    """accepted tool evidence 缺 projection 字段时不从 payload 重建。

    :returns: ``None``。
    :raises AssertionError: memory 从 payload 重建 accepted evidence 时抛出。
    """

    policy = _policy()
    event_id = "event-tool-result-preview-memory"
    envelope = AcceptedEvidenceEnvelope(
        evidence_id="evidence:tool-result-preview-memory",
        producer_event_ref=event_id,
        tool_name="lookup_mock_fact",
        tool_call_id="tool-call-preview-memory",
        tool_query=AcceptedEvidenceToolQuery(
            tool_call_requested_event_ref="event-tool-call-preview-memory",
            normalized_arguments_digest=sha256_digest_json({"query": "DAYU"}),
            semantic_input_digest=sha256_digest_json("DAYU"),
        ),
        result_ref=AcceptedEvidenceResultRef(
            payload_ref=None,
            payload_digest=None,
            outcome_digest=sha256_digest_json(
                {"status": "ok", "text": "tool fact accepted"}
            ),
            truncation_applied=False,
        ),
        locator_refs=(),
        source_refs=(),
    )

    snapshot = build_conversation_memory_snapshot_from_events(
        events=(
            _event(
                1,
                event_id,
                "TOOL_RESULT_ACCEPTED",
                {
                    "accepted_evidence_envelope": (
                        accepted_evidence_envelope_to_json_value(envelope)
                    ),
                    "raw_tool_outcome": {
                        "status": "ok",
                        "text": "tool fact accepted",
                    },
                    "result_preview": "preview must not be read by memory",
                },
                accepted_tool_evidence=None,
            ),
        ),
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )

    text = snapshot.trace_memory.selected_recent_window[0].text
    assert text == render_accepted_tool_evidence_for_llm(None)
    assert "lookup_mock_fact" not in text
    assert "tool fact accepted" not in text
    assert "preview must not be read" not in text


def test_accepted_tool_evidence_uses_projection_fields_without_payload_rebuild() -> None:
    """Conversation Memory 使用 projection 字段，缺字段时不重建工具证据。"""

    policy = _policy()
    payload: dict[str, JsonValue] = {
        "tool_name": "payload_tool_must_not_leak",
        "raw_tool_outcome": {"text": "payload result must not leak"},
    }
    projected_snapshot = build_conversation_memory_snapshot_from_events(
        events=(
            _event(
                1,
                "event-tool-result-projected-memory",
                "TOOL_RESULT_ACCEPTED",
                payload,
                accepted_tool_evidence=AcceptedToolEvidenceLLMMaterial(
                    tool_name="projection_tool",
                    query_text="projection query",
                    source_text="filing:projection",
                    result_text=canonical_json_dumps({"text": "projection result"}),
                ),
            ),
        ),
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )
    missing_fields_snapshot = build_conversation_memory_snapshot_from_events(
        events=(
            _event(
                1,
                "event-tool-result-missing-projection-memory",
                "TOOL_RESULT_ACCEPTED",
                payload,
                accepted_tool_evidence=None,
            ),
        ),
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )

    projected_text = projected_snapshot.trace_memory.selected_recent_window[0].text
    missing_fields_text = (
        missing_fields_snapshot.trace_memory.selected_recent_window[0].text
    )
    assert "projection_tool" in projected_text
    assert "projection query" in projected_text
    assert "projection result" in projected_text
    assert "filing:projection" in projected_text
    assert missing_fields_text == render_accepted_tool_evidence_for_llm(None)
    for forbidden in ("payload_tool_must_not_leak", "payload result must not leak"):
        assert forbidden not in projected_text
        assert forbidden not in missing_fields_text


def test_accepted_compact_limits_evidence_facts_and_records_budget_diagnostic() -> None:
    """Evidence facts 超过 section item cap 时整体丢弃并记录 budget diagnostic。"""

    policy = replace(_policy(), evidence_fact_item_cap=1, evidence_fact_floor=0)
    snapshot = build_conversation_memory_snapshot_from_events(
        events=(
            _event(
                1,
                "compact-1",
                CONTEXT_COMPACTED,
                _accepted_compact_payload(
                    facts=[
                        _fact("旧 fact 应被截断。"),
                        _fact("新 fact 应被保留。"),
                    ],
                ),
            ),
        ),
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )

    assert tuple(
        fact.claim_text
        for fact in snapshot.evidence_fact_memory.evidence_backed_facts
    ) == ("新 fact 应被保留。",)
    assert MemoryDiagnosticReason.BUDGET_LIMIT_REACHED in tuple(
        diagnostic.reason for diagnostic in snapshot.diagnostics
    )


def test_accepted_compact_drops_oversized_fact_without_prefix_text() -> None:
    """超出 fact char cap 的 compact fact 整体丢弃，不返回前缀文本。"""

    policy = replace(_policy(), evidence_fact_char_cap=8, evidence_fact_floor=0)
    long_claim = "这是一条超过上限且不能被前缀截断的完整事实。"
    snapshot = build_conversation_memory_snapshot_from_events(
        events=(
            _event(
                1,
                "compact-oversized-fact",
                CONTEXT_COMPACTED,
                _accepted_compact_payload(facts=[_fact(long_claim)]),
            ),
        ),
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )

    assert snapshot.evidence_fact_memory.evidence_backed_facts == ()
    assert long_claim[: policy.evidence_fact_char_cap] not in tuple(
        fact.claim_text for fact in snapshot.evidence_fact_memory.evidence_backed_facts
    )
    assert MemoryDiagnosticReason.BUDGET_LIMIT_REACHED in tuple(
        diagnostic.reason for diagnostic in snapshot.diagnostics
    )


def test_accepted_compact_drops_oversized_summary_without_prefix_text() -> None:
    """超出 summary char cap 的 compact summary 整体丢弃，不返回前缀文本。"""

    policy = replace(_policy(), session_summary_char_cap=8)
    long_summary = "用户需要完整保留的长 summary，不能静默截断。"
    payload = _accepted_compact_payload(summary_text=long_summary)
    snapshot = build_conversation_memory_snapshot_from_events(
        events=(
            _event(
                1,
                "compact-oversized-summary",
                CONTEXT_COMPACTED,
                payload,
            ),
        ),
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy=policy,
        built_at=_NOW,
    )

    assert snapshot.session_summary_memory.summary_text is None
    assert MemoryDiagnosticReason.BUDGET_LIMIT_REACHED in tuple(
        diagnostic.reason for diagnostic in snapshot.diagnostics
    )


def test_accepted_evidence_without_fact_candidate_records_diagnostic_only() -> None:
    """accepted evidence 存在但无 fact candidate 时不合成 fallback fact。"""

    policy = _policy()
    snapshot = project_conversation_memory_event(
        previous_snapshot=None,
        event=_event(1, "compact-1", CONTEXT_COMPACTED, _accepted_compact_payload()),
        policy=policy,
        built_at=_NOW,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
    )

    assert snapshot.evidence_fact_memory.evidence_backed_facts == ()
    assert tuple(diagnostic.reason for diagnostic in snapshot.diagnostics) == (
        MemoryDiagnosticReason.ACCEPTED_EVIDENCE_WITHOUT_FACT_CANDIDATE,
    )


def test_failed_compaction_event_does_not_materialize_memory_sections() -> None:
    """failed compaction event 不物化 summary、fact、anchor 或 intent。"""

    policy = _policy()
    snapshot = project_conversation_memory_event(
        previous_snapshot=None,
        event=_event(1, "failed-1", "CONTEXT_COMPACTION_FAILED", {"reason": "over"}),
        policy=policy,
        built_at=_NOW,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
    )

    assert snapshot.session_summary_memory.summary_text is None
    assert snapshot.evidence_fact_memory.evidence_backed_facts == ()
    assert snapshot.answer_anchor_memory.anchors == ()
    assert snapshot.forward_intent_memory.intents == ()
    assert snapshot.trace_memory.reference_continuity_items == ()
    assert snapshot.diagnostics[0].reason is MemoryDiagnosticReason.UNSUPPORTED_EVENT_TYPE


def test_snapshot_json_roundtrip_preserves_vnext_sections() -> None:
    """snapshot JSON codec 保留 vNext sections 与 digest。"""

    policy = _policy()
    snapshot = project_conversation_memory_event(
        previous_snapshot=None,
        event=_event(
            1,
            "compact-1",
            CONTEXT_COMPACTED,
            _accepted_compact_payload(facts=[_fact("毛利率提升。")]),
        ),
        policy=policy,
        built_at=_NOW,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
    )

    value = conversation_memory_snapshot_to_json_value(snapshot)
    restored = conversation_memory_snapshot_from_json_value(value)

    assert restored == snapshot
    assert restored.snapshot_digest == calculate_memory_snapshot_digest(restored)
    mapping = cast(dict[str, JsonValue], value)
    forward_memory = cast(dict[str, JsonValue], mapping["forward_intent_memory"])
    intents = cast(list[JsonValue], forward_memory["intents"])
    intent = cast(dict[str, JsonValue], intents[0])
    trace_memory = cast(dict[str, JsonValue], mapping["trace_memory"])
    references = cast(list[JsonValue], trace_memory["reference_continuity_items"])
    reference = cast(dict[str, JsonValue], references[0])
    assert intent["intent_type"] == ForwardIntentTypeVNext.NEXT_STEP_NOTE.value
    assert intent["status"] == ForwardIntentStatusVNext.OPEN.value
    assert reference["reason"] == ReferenceContinuityReasonVNext.LOCAL_REFERENCE.value


@pytest.mark.parametrize(
    ("section", "field_name", "invalid_value"),
    (
        ("forward_intent_memory", "intent_type", "unknown_intent"),
        ("forward_intent_memory", "status", "unknown_status"),
        ("trace_memory", "reason", "unknown_reason"),
    ),
)
def test_snapshot_json_rejects_invalid_compact_enum(
    section: str,
    field_name: str,
    invalid_value: str,
) -> None:
    """snapshot codec 严格恢复 compact enum，不写 unknown fallback。

    :param section: 被破坏的 snapshot section。
    :param field_name: 被破坏的 enum 字段。
    :param invalid_value: 非法 enum value。
    """

    snapshot = project_conversation_memory_event(
        previous_snapshot=None,
        event=_event(
            1,
            "compact-invalid-snapshot-enum",
            CONTEXT_COMPACTED,
            _accepted_compact_payload(),
        ),
        policy=_policy(),
        built_at=_NOW,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
    )
    mapping = cast(
        dict[str, JsonValue],
        conversation_memory_snapshot_to_json_value(snapshot),
    )
    section_mapping = cast(dict[str, JsonValue], mapping[section])
    items_field = (
        "reference_continuity_items" if section == "trace_memory" else "intents"
    )
    items = cast(list[JsonValue], section_mapping[items_field])
    item = cast(dict[str, JsonValue], items[0])
    item[field_name] = invalid_value

    with pytest.raises(ValueError):
        conversation_memory_snapshot_from_json_value(mapping)


def test_snapshot_json_rejects_bool_for_integer_fields() -> None:
    """snapshot JSON 的 integer 字段拒绝 bool，避免 true 被当成 1。"""

    policy = _policy()
    snapshot = project_conversation_memory_event(
        previous_snapshot=None,
        event=_event(1, "user-1", "USER_INPUT_ACCEPTED", {"display_text": "hello"}),
        policy=policy,
        built_at=_NOW,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
    )
    value = conversation_memory_snapshot_to_json_value(snapshot)
    mapping = cast(dict[str, JsonValue], value)
    trace_memory = cast(dict[str, JsonValue], mapping["trace_memory"])
    selected = cast(list[JsonValue], trace_memory["selected_recent_window"])
    selected_item = cast(dict[str, JsonValue], selected[0])
    selected_item["event_sequence"] = True

    with pytest.raises(ValueError, match="event_sequence must be integer"):
        conversation_memory_snapshot_from_json_value(mapping)


def test_write_snapshot_with_checkpoint_commits_snapshot_before_checkpoint(
    tmp_path: Path,
) -> None:
    """snapshot 与 projection checkpoint 在同一 durable transaction 提交。"""

    policy = _policy()
    snapshot = project_conversation_memory_event(
        previous_snapshot=None,
        event=_event(
            1,
            "compact-1",
            CONTEXT_COMPACTED,
            _accepted_compact_payload(facts=[_fact("收入增长。")]),
        ),
        policy=policy,
        built_at=_NOW,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
    )

    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: append_event(
                transaction,
                EventLogAppendRequest(
                    event_id="compact-1",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=_SESSION_ID,
                    run_id=_RUN_ID,
                    attempt_id=_ATTEMPT_ID,
                    execution_id=_EXECUTION_ID,
                    event_type=CONTEXT_COMPACTED,
                    occurred_at=_OCCURRED_AT,
                    actor="pytest",
                    source="pytest",
                    client_request_id=None,
                    idempotency_key=None,
                    policy_decision=None,
                    reason=None,
                    payload_json=_accepted_compact_payload(facts=[_fact("收入增长。")]),
                    payload_ref=None,
                    payload_digest=None,
                ),
            ).row
        )
        written = store.transaction_runner.run_write(
            lambda transaction: write_memory_snapshot_with_checkpoint(
                transaction,
                snapshot,
                now=_NOW,
            )
        )
        read_back = store.transaction_runner.run_read(
            lambda transaction: read_memory_snapshot(transaction, snapshot.snapshot_id)
        )
        checkpoint = store.transaction_runner.run_read(
            lambda transaction: read_projection_checkpoint(
                transaction,
                CONVERSATION_MEMORY_CONSUMER_ID,
            )
        )

        assert read_back is not None
        assert written.snapshot.snapshot_id == read_back.snapshot.snapshot_id
        assert checkpoint is not None
        assert (
            checkpoint.checkpoint_event_sequence
            == snapshot.cursor.checkpoint_event_sequence
        )
        assert checkpoint.checkpoint_event_id == snapshot.cursor.checkpoint_event_id


def test_projection_consumer_applies_event_and_writes_durable_vnext_snapshot(
    tmp_path: Path,
) -> None:
    """accepted compact 经 ProjectionRunner 物化五类 memory section 与 checkpoint。"""

    policy = _policy()
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: append_event(
                transaction,
                EventLogAppendRequest(
                    event_id="compact-1",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=_SESSION_ID,
                    run_id=_RUN_ID,
                    attempt_id=_ATTEMPT_ID,
                    execution_id=_EXECUTION_ID,
                    event_type=CONTEXT_COMPACTED,
                    occurred_at=_OCCURRED_AT,
                    actor="pytest",
                    source="pytest",
                    client_request_id=None,
                    idempotency_key=None,
                    policy_decision=None,
                    reason=None,
                    payload_json=_accepted_compact_payload(facts=[_fact("收入增长。")]),
                    payload_ref=None,
                    payload_digest=None,
                ),
            ).row
        )
        consumer = ConversationMemoryProjectionConsumer(policy)
        ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            consumer.consumer_id,
            limit=10,
        )
        policy_digest = digest_memory_projection_policy(policy)
        latest = store.transaction_runner.run_read(
            lambda transaction: read_latest_memory_snapshot(
                transaction,
                session_id=_SESSION_ID,
                consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                policy_digest=policy_digest,
            )
        )
        item_kinds = store.transaction_runner.run_read(
            lambda transaction: tuple(
                cast(
                    str,
                    row.get("item_kind"),
                )
                for row in transaction.fetchall(
                    f"""
                    SELECT item_kind
                    FROM {TABLE_HOST_MEMORY_ITEMS}
                    ORDER BY item_kind
                    """
                )
            )
        )
        checkpoint = store.transaction_runner.run_read(
            lambda transaction: read_projection_checkpoint(
                transaction,
                CONVERSATION_MEMORY_CONSUMER_ID,
            )
        )

        assert latest is not None
        assert latest.snapshot.latest_compaction_event_ref == "compact-1"
        assert latest.snapshot.session_summary_memory.summary_text == (
            "用户关注收入增速和毛利率变化。"
        )
        assert (
            latest.snapshot.evidence_fact_memory.evidence_backed_facts[0].claim_text
            == "收入增长。"
        )
        assert latest.snapshot.answer_anchor_memory.anchors[0].anchor_title == (
            "收入口径"
        )
        assert latest.snapshot.forward_intent_memory.intents[0].text == (
            "下一轮继续核对费用率。"
        )
        assert latest.snapshot.trace_memory.reference_continuity_items[0].text == (
            "“该公司”继续指向当前分析主体。"
        )
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == 1
        assert checkpoint.checkpoint_event_id == "compact-1"
        assert (
            latest.snapshot.cursor.checkpoint_event_sequence
            == checkpoint.checkpoint_event_sequence
        )
        assert latest.snapshot.cursor.checkpoint_event_id == checkpoint.checkpoint_event_id
        assert set(item_kinds) == {
            "answer_anchor",
            "evidence_backed_fact",
            "forward_intent",
            "reference_continuity",
            "session_summary",
        }


def test_projection_consumer_invalid_persisted_enum_does_not_advance_checkpoint(
    tmp_path: Path,
) -> None:
    """非法 persisted enum 记录 failure，不写 snapshot 或推进 checkpoint。

    :param tmp_path: pytest 临时目录。
    """

    policy = _policy()
    payload = _accepted_compact_payload(facts=[_fact("收入增长。")])
    candidate = cast(dict[str, JsonValue], payload["accepted_candidate"])
    intents = cast(list[JsonValue], candidate["forward_intents"])
    intent = cast(dict[str, JsonValue], intents[0])
    intent["intent_type"] = "unknown_intent"
    payload["accepted_candidate_digest"] = sha256_digest_json(candidate)
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: append_event(
                transaction,
                EventLogAppendRequest(
                    event_id="compact-invalid-enum",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=_SESSION_ID,
                    run_id=_RUN_ID,
                    attempt_id=_ATTEMPT_ID,
                    execution_id=_EXECUTION_ID,
                    event_type=CONTEXT_COMPACTED,
                    occurred_at=_OCCURRED_AT,
                    actor="pytest",
                    source="pytest",
                    client_request_id=None,
                    idempotency_key=None,
                    policy_decision=None,
                    reason=None,
                    payload_json=payload,
                    payload_ref=None,
                    payload_digest=None,
                ),
            ).row
        )
        consumer = ConversationMemoryProjectionConsumer(policy)
        result = ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            consumer.consumer_id,
            limit=10,
        )
        latest = store.transaction_runner.run_read(
            lambda transaction: read_latest_memory_snapshot(
                transaction,
                session_id=_SESSION_ID,
                consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                policy_digest=digest_memory_projection_policy(policy),
            )
        )
        checkpoint = store.transaction_runner.run_read(
            lambda transaction: read_projection_checkpoint(
                transaction,
                CONVERSATION_MEMORY_CONSUMER_ID,
            )
        )

        assert result.failures == 1
        assert result.events_applied == 0
        assert latest is None
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == 0
        assert checkpoint.checkpoint_event_id is None


def test_projection_consumer_pairs_tool_result_with_requested_query(
    tmp_path: Path,
) -> None:
    """工具结果 memory 从对应 request row 回读 query 语义。"""

    policy = _policy()
    tool_call_id = "tool-call-query-memory"
    request_event_id = "event-tool-call-requested-query-memory"
    result_event_id = "event-tool-result-query-memory"
    arguments_json: Mapping[str, JsonValue] = {"arguments": {"ticker": "COIN"}}
    arguments_digest = sha256_digest_json(arguments_json)
    semantic_input_digest = sha256_digest_json({"semantic_input": "COIN"})
    query_text = "读取 ticker=COIN 的财报列表"
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: _append_tool_request_and_result_events(
                transaction,
                request_event_id=request_event_id,
                result_event_id=result_event_id,
                request_payload=_tool_call_requested_payload(
                    tool_call_id=tool_call_id,
                    tool_name="list_documents",
                    arguments_json=arguments_json,
                    semantic_input_digest=semantic_input_digest,
                    semantic_query_text=query_text,
                ),
                result_payload=_accepted_tool_result_payload(
                    result_event_id=result_event_id,
                    request_event_id=request_event_id,
                    tool_call_id=tool_call_id,
                    tool_name="list_documents",
                    arguments_digest=arguments_digest,
                    semantic_input_digest=semantic_input_digest,
                    raw_tool_outcome={"total": 0, "documents": []},
                ),
            )
        )
        consumer = ConversationMemoryProjectionConsumer(policy)
        ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            consumer.consumer_id,
            limit=10,
        )
        latest = store.transaction_runner.run_read(
            lambda transaction: read_latest_memory_snapshot(
                transaction,
                session_id=_SESSION_ID,
                consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                policy_digest=digest_memory_projection_policy(policy),
            )
        )

        assert latest is not None
        text = latest.snapshot.trace_memory.selected_recent_window[0].text
        assert "list_documents" in text
        assert query_text in text
        assert '"documents":[]' in text
        forbidden_fragments = (
            tool_call_id,
            request_event_id,
            result_event_id,
            "sha256:",
            "payload",
            "artifact",
            "wait",
            "awaiting",
            "abandoned",
            "poll",
            "cancel",
        )
        for fragment in forbidden_fragments:
            assert fragment not in text


def test_projection_consumer_uses_limited_query_without_semantic_query(
    tmp_path: Path,
) -> None:
    """缺少 semantic query 时，不从 arguments 合成 query 文本。"""

    policy = _policy()
    tool_call_id = "tool-call-argument-summary-memory"
    request_event_id = "event-tool-call-requested-argument-summary-memory"
    result_event_id = "event-tool-result-argument-summary-memory"
    arguments_json: Mapping[str, JsonValue] = {"arguments": {"ticker": "MSFT"}}
    arguments_digest = sha256_digest_json(arguments_json)
    semantic_input_digest = sha256_digest_json({"semantic_input": "MSFT"})
    latest = None
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: _append_tool_request_and_result_events(
                transaction,
                request_event_id=request_event_id,
                result_event_id=result_event_id,
                request_payload=_tool_call_requested_payload(
                    tool_call_id=tool_call_id,
                    tool_name="list_documents",
                    arguments_json=arguments_json,
                    semantic_input_digest=semantic_input_digest,
                    semantic_query_text=None,
                ),
                result_payload=_accepted_tool_result_payload(
                    result_event_id=result_event_id,
                    request_event_id=request_event_id,
                    tool_call_id=tool_call_id,
                    tool_name="list_documents",
                    arguments_digest=arguments_digest,
                    semantic_input_digest=semantic_input_digest,
                    raw_tool_outcome={"total": 1},
                ),
            )
        )
        consumer = ConversationMemoryProjectionConsumer(policy)
        ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            consumer.consumer_id,
            limit=10,
        )
        latest = store.transaction_runner.run_read(
            lambda transaction: read_latest_memory_snapshot(
                transaction,
                session_id=_SESSION_ID,
                consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                policy_digest=digest_memory_projection_policy(policy),
            )
        )

    assert latest is not None
    text = latest.snapshot.trace_memory.selected_recent_window[0].text
    assert '参数：{"arguments":{"ticker":"MSFT"}}' in text
    assert '"total":1' in text
    assert request_event_id not in text
    assert result_event_id not in text
    assert tool_call_id not in text
    assert "sha256:" not in text


@pytest.mark.parametrize(
    ("request_run_id", "request_attempt_id", "request_execution_id"),
    (
        ("run-other", _ATTEMPT_ID, _EXECUTION_ID),
        (_RUN_ID, "attempt-other", _EXECUTION_ID),
        (_RUN_ID, _ATTEMPT_ID, "execution-other"),
    ),
)
def test_projection_consumer_fails_safe_on_request_result_execution_mismatch(
    tmp_path: Path,
    request_run_id: str,
    request_attempt_id: str,
    request_execution_id: str,
) -> None:
    """request/result 执行上下文错配时不回读 request query。"""

    policy = _policy()
    tool_call_id = "tool-call-execution-mismatch-memory"
    request_event_id = "event-tool-call-requested-execution-mismatch-memory"
    result_event_id = "event-tool-result-execution-mismatch-memory"
    arguments_json: Mapping[str, JsonValue] = {"arguments": {"ticker": "COIN"}}
    arguments_digest = sha256_digest_json(arguments_json)
    semantic_input_digest = sha256_digest_json({"semantic_input": "COIN"})
    query_text = "这个 request query 不应进入 memory"
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: _append_tool_request_and_result_events(
                transaction,
                request_event_id=request_event_id,
                result_event_id=result_event_id,
                request_payload=_tool_call_requested_payload(
                    tool_call_id=tool_call_id,
                    tool_name="list_documents",
                    arguments_json=arguments_json,
                    semantic_input_digest=semantic_input_digest,
                    semantic_query_text=query_text,
                ),
                result_payload=_accepted_tool_result_payload(
                    result_event_id=result_event_id,
                    request_event_id=request_event_id,
                    tool_call_id=tool_call_id,
                    tool_name="list_documents",
                    arguments_digest=arguments_digest,
                    semantic_input_digest=semantic_input_digest,
                    raw_tool_outcome={"total": 0},
                ),
                request_run_id=request_run_id,
                request_attempt_id=request_attempt_id,
                request_execution_id=request_execution_id,
            )
        )
        consumer = ConversationMemoryProjectionConsumer(policy)
        ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            consumer.consumer_id,
            limit=10,
        )
        latest = store.transaction_runner.run_read(
            lambda transaction: read_latest_memory_snapshot(
                transaction,
                session_id=_SESSION_ID,
                consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                policy_digest=digest_memory_projection_policy(policy),
            )
        )

        assert latest is not None
        text = latest.snapshot.trace_memory.selected_recent_window[0].text
        assert _FAIL_SAFE_LIMITED_QUERY_TEXT in text
        assert '"total":0' in text
        assert query_text not in text
        assert request_event_id not in text
        assert result_event_id not in text
        assert tool_call_id not in text
        assert "run-other" not in text
        assert "attempt-other" not in text
        assert "execution-other" not in text


def test_projection_consumer_fails_safe_when_requested_event_ref_missing(
    tmp_path: Path,
) -> None:
    """result envelope 缺少 request ref 时不合成内部引用文本。"""

    policy = _policy()
    tool_call_id = "tool-call-missing-request-ref-memory"
    request_event_id = "event-tool-call-requested-missing-ref-memory"
    result_event_id = "event-tool-result-missing-request-ref-memory"
    arguments_json: Mapping[str, JsonValue] = {"arguments": {"ticker": "COIN"}}
    arguments_digest = sha256_digest_json(arguments_json)
    semantic_input_digest = sha256_digest_json({"semantic_input": "COIN"})
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: _append_tool_request_and_result_events(
                transaction,
                request_event_id=request_event_id,
                result_event_id=result_event_id,
                request_payload=_tool_call_requested_payload(
                    tool_call_id=tool_call_id,
                    tool_name="list_documents",
                    arguments_json=arguments_json,
                    semantic_input_digest=semantic_input_digest,
                    semantic_query_text="缺失 ref 时不应读取这个 query",
                ),
                result_payload=_accepted_tool_result_payload(
                    result_event_id=result_event_id,
                    request_event_id=None,
                    tool_call_id=tool_call_id,
                    tool_name="list_documents",
                    arguments_digest=arguments_digest,
                    semantic_input_digest=semantic_input_digest,
                    raw_tool_outcome={"total": 0},
                ),
            )
        )
        consumer = ConversationMemoryProjectionConsumer(policy)
        ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            consumer.consumer_id,
            limit=10,
        )
        latest = store.transaction_runner.run_read(
            lambda transaction: read_latest_memory_snapshot(
                transaction,
                session_id=_SESSION_ID,
                consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                policy_digest=digest_memory_projection_policy(policy),
            )
        )

        assert latest is not None
        text = latest.snapshot.trace_memory.selected_recent_window[0].text
        assert _FAIL_SAFE_LIMITED_QUERY_TEXT in text
        assert "缺失 ref 时不应读取这个 query" not in text
        assert request_event_id not in text
        assert result_event_id not in text
        assert tool_call_id not in text


@pytest.mark.parametrize(
    "case",
    (
        pytest.param(
            _ToolQueryFailSafeCase(append_request=False),
            id="requested-event-row-missing",
        ),
        pytest.param(
            _ToolQueryFailSafeCase(request_session_id="session-other"),
            id="request-session-mismatch",
        ),
        pytest.param(
            _ToolQueryFailSafeCase(request_event_class=EventClass.DIAGNOSTIC),
            id="request-event-class-not-canonical",
        ),
        pytest.param(
            _ToolQueryFailSafeCase(request_event_type="TOOL_CALL_GOVERNED"),
            id="request-event-type-mismatch",
        ),
        pytest.param(
            _ToolQueryFailSafeCase(
                request_payload_kind=_REQUEST_PAYLOAD_KIND_INVALID,
            ),
            id="request-atoms-unreadable",
        ),
        pytest.param(
            _ToolQueryFailSafeCase(
                envelope_tool_call_id="tool-call-envelope-mismatch-memory",
            ),
            id="tool-call-id-mismatch",
        ),
        pytest.param(
            _ToolQueryFailSafeCase(envelope_tool_name="lookup_documents"),
            id="tool-name-mismatch",
        ),
        pytest.param(
            _ToolQueryFailSafeCase(
                envelope_arguments_digest=sha256_digest_json(
                    {"arguments": {"ticker": "MSFT"}}
                ),
            ),
            id="arguments-digest-mismatch",
        ),
    ),
)
def test_projection_consumer_fails_safe_for_request_query_source_mismatch(
    tmp_path: Path,
    case: _ToolQueryFailSafeCase,
) -> None:
    """request query 来源不可校验时统一降级且保留 raw outcome。"""

    text = _project_tool_query_fail_safe_case(tmp_path, case)

    assert _FAIL_SAFE_LIMITED_QUERY_TEXT in text
    assert "raw outcome retained" in text
    assert _FAIL_SAFE_QUERY_TEXT not in text
    forbidden_fragments = (
        "event-tool-call-requested-query-fail-safe-memory",
        "event-tool-result-query-fail-safe-memory",
        case.request_tool_call_id,
        case.envelope_tool_call_id,
        "sha256:",
        "payload",
        "artifact",
        "wait",
        "awaiting",
        "abandoned",
        "poll",
        "cancel",
    )
    for fragment in forbidden_fragments:
        assert fragment not in text


def test_projection_consumer_uses_limited_query_for_unsafe_argument_fallback(
    tmp_path: Path,
) -> None:
    """缺少 semantic query 时，unsafe 参数不裸露进入 memory。"""

    policy = _policy()
    tool_call_id = "tool-call-unsafe-argument-memory"
    request_event_id = "event-tool-call-requested-unsafe-memory"
    result_event_id = "event-tool-result-unsafe-memory"
    secret = "sk-live-secret"
    local_path = "/Users/leo/private/report.pdf"
    arguments_json: Mapping[str, JsonValue] = {
        "arguments": {
            "api_key": secret,
            "input_path": local_path,
            "ticker": "COIN",
        }
    }
    arguments_digest = sha256_digest_json(arguments_json)
    semantic_input_digest = sha256_digest_json({"semantic_input": "unsafe"})
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: _append_tool_request_and_result_events(
                transaction,
                request_event_id=request_event_id,
                result_event_id=result_event_id,
                request_payload=_tool_call_requested_payload(
                    tool_call_id=tool_call_id,
                    tool_name="lookup_private_file",
                    arguments_json=arguments_json,
                    semantic_input_digest=semantic_input_digest,
                    semantic_query_text=None,
                ),
                result_payload=_accepted_tool_result_payload(
                    result_event_id=result_event_id,
                    request_event_id=request_event_id,
                    tool_call_id=tool_call_id,
                    tool_name="lookup_private_file",
                    arguments_digest=arguments_digest,
                    semantic_input_digest=semantic_input_digest,
                    raw_tool_outcome={"status": "ok"},
                ),
            )
        )
        consumer = ConversationMemoryProjectionConsumer(policy)
        ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            consumer.consumer_id,
            limit=10,
        )
        latest = store.transaction_runner.run_read(
            lambda transaction: read_latest_memory_snapshot(
                transaction,
                session_id=_SESSION_ID,
                consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                policy_digest=digest_memory_projection_policy(policy),
            )
        )

        assert latest is not None
        text = latest.snapshot.trace_memory.selected_recent_window[0].text
        assert _FAIL_SAFE_LIMITED_QUERY_TEXT in text
        assert '"status":"ok"' in text
        assert secret not in text
        assert local_path not in text
        assert "arguments" not in text
        assert "api_key" not in text
        assert "input_path" not in text
        assert "ticker" not in text
        assert "COIN" not in text
        assert request_event_id not in text
        assert result_event_id not in text
        assert tool_call_id not in text


def test_conversation_memory_consumer_uses_shared_projection_event_filter() -> None:
    """Conversation Memory consumer 直接使用模块级 projection filter 真源。"""

    policy = _policy()
    consumer = ConversationMemoryProjectionConsumer(policy)

    assert consumer.event_filter == conversation_memory_projection_event_filter()
    event_types = consumer.event_filter.class_filters[0].event_types
    assert event_types is not None
    assert "TOOL_AWAITING" not in event_types


def test_projection_consumer_skips_failed_compact_without_memory_snapshot(
    tmp_path: Path,
) -> None:
    """failed compact 不进入 Conversation Memory snapshot 或 compact sections。"""

    policy = _policy()
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: append_event(
                transaction,
                EventLogAppendRequest(
                    event_id="compact-failed-1",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=_SESSION_ID,
                    run_id=_RUN_ID,
                    attempt_id=_ATTEMPT_ID,
                    execution_id=_EXECUTION_ID,
                    event_type=CONTEXT_COMPACTION_FAILED,
                    occurred_at=_OCCURRED_AT,
                    actor="pytest",
                    source="pytest",
                    client_request_id=None,
                    idempotency_key=None,
                    policy_decision=None,
                    reason=None,
                    payload_json={"failure_reason": "compactor_unavailable"},
                    payload_ref=None,
                    payload_digest=None,
                ),
            ).row
        )
        consumer = ConversationMemoryProjectionConsumer(policy)
        result = ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            consumer.consumer_id,
            limit=10,
        )
        policy_digest = digest_memory_projection_policy(policy)
        latest = store.transaction_runner.run_read(
            lambda transaction: read_latest_memory_snapshot(
                transaction,
                session_id=_SESSION_ID,
                consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                policy_digest=policy_digest,
            )
        )
        item_count = store.transaction_runner.run_read(_memory_item_count)
        checkpoint = store.transaction_runner.run_read(
            lambda transaction: read_projection_checkpoint(
                transaction,
                CONVERSATION_MEMORY_CONSUMER_ID,
            )
        )

        assert result.events_scanned == 1
        assert result.events_matched == 0
        assert result.events_applied == 0
        assert latest is None
        assert item_count == 0
        assert checkpoint is not None
        assert checkpoint.checkpoint_event_sequence == 1
        assert checkpoint.checkpoint_event_id == "compact-failed-1"


def test_projection_consumer_skips_compaction_attempt_rejected(
    tmp_path: Path,
) -> None:
    """attempt rejected 诊断事件不进入 Conversation Memory snapshot。"""

    policy = _policy()
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            lambda transaction: append_event(
                transaction,
                EventLogAppendRequest(
                    event_id="compact-attempt-rejected-1",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=_SESSION_ID,
                    run_id=_RUN_ID,
                    attempt_id=_ATTEMPT_ID,
                    execution_id=_EXECUTION_ID,
                    event_type=CONTEXT_COMPACTION_ATTEMPT_REJECTED,
                    occurred_at=_OCCURRED_AT,
                    actor="pytest",
                    source="pytest",
                    client_request_id=None,
                    idempotency_key=None,
                    policy_decision=None,
                    reason=None,
                    payload_json={"failure_category": "proposal_failed"},
                    payload_ref=None,
                    payload_digest=None,
                ),
            ).row
        )
        consumer = ConversationMemoryProjectionConsumer(policy)
        result = ProjectionRunner(store.transaction_runner, (consumer,)).run_once(
            consumer.consumer_id,
            limit=10,
        )
        policy_digest = digest_memory_projection_policy(policy)
        latest = store.transaction_runner.run_read(
            lambda transaction: read_latest_memory_snapshot(
                transaction,
                session_id=_SESSION_ID,
                consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                policy_digest=policy_digest,
            )
        )

        assert result.events_scanned == 1
        assert result.events_matched == 0
        assert result.events_applied == 0
        assert latest is None


def test_policy_digest_changes_when_design_field_changes() -> None:
    """policy digest 覆盖 vNext 字段变化。"""

    policy = _policy()
    changed = replace(policy, forward_intent_item_cap=policy.forward_intent_item_cap + 1)

    assert digest_memory_projection_policy(policy) != digest_memory_projection_policy(changed)


def test_empty_snapshot_uses_stable_id_and_vnext_empty_views() -> None:
    """空 snapshot 使用稳定 id 并初始化 vNext 空 view。"""

    policy = default_memory_projection_policy()
    policy_digest = digest_memory_projection_policy(policy)
    snapshot_id = stable_memory_snapshot_id(
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy_digest=policy_digest,
    )

    snapshot = build_empty_conversation_memory_snapshot(
        snapshot_id=snapshot_id,
        session_id=_SESSION_ID,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy_digest=policy_digest,
        built_at=_NOW,
    )

    assert snapshot.snapshot_id == snapshot_id
    assert snapshot.trace_memory.selected_recent_window == ()
    assert snapshot.evidence_fact_memory.evidence_backed_facts == ()
    assert snapshot.snapshot_digest == calculate_memory_snapshot_digest(snapshot)


def test_memory_snapshot_integrity_empty_and_valid_rows_return_no_issues(
    tmp_path: Path,
) -> None:
    """Memory snapshot integrity classifier 对空库和有效 row 返回空诊断。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        empty_issues = store.transaction_runner.run_read(
            inspect_memory_snapshot_integrity
        )
        snapshot = _write_integrity_compact_snapshot(store)
        valid_issues = store.transaction_runner.run_read(
            inspect_memory_snapshot_integrity
        )
        read_back = store.transaction_runner.run_read(
            lambda transaction: read_memory_snapshot(
                transaction,
                snapshot.snapshot_id,
            )
        )

        assert empty_issues == ()
        assert valid_issues == ()
        assert read_back is not None


def test_memory_snapshot_integrity_classifies_invalid_json(tmp_path: Path) -> None:
    """Memory snapshot integrity classifier 识别非法 JSON。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        snapshot = _write_integrity_compact_snapshot(store)
        _replace_snapshot_json(store, snapshot.snapshot_id, "{not-json")

        issues = store.transaction_runner.run_read(inspect_memory_snapshot_integrity)

        assert len(issues) == 1
        assert issues[0].failure_kind is MemorySnapshotIntegrityFailureKind.INVALID_JSON
        assert issues[0].snapshot_id == snapshot.snapshot_id


def test_memory_snapshot_integrity_classifies_schema_mismatch(tmp_path: Path) -> None:
    """Memory snapshot integrity classifier 识别 schema-mismatched JSON。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        snapshot = _write_integrity_compact_snapshot(store)
        _replace_snapshot_json(
            store,
            snapshot.snapshot_id,
            canonical_json_dumps({"schema_version": "conversation_memory_snapshot_v1"}),
        )

        issues = store.transaction_runner.run_read(inspect_memory_snapshot_integrity)

        assert len(issues) == 1
        assert (
            issues[0].failure_kind
            is MemorySnapshotIntegrityFailureKind.SCHEMA_MISMATCH
        )
        assert issues[0].snapshot_id == snapshot.snapshot_id


def test_memory_snapshot_integrity_classifies_manual_digest_mismatch(
    tmp_path: Path,
) -> None:
    """手动 SQL 篡改合法 JSON 内容时归类为 digest mismatch。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        snapshot = _write_integrity_compact_snapshot(store)
        corrupted_json = _snapshot_json_with_changed_built_at(snapshot)
        _replace_snapshot_json(store, snapshot.snapshot_id, corrupted_json)

        issues = store.transaction_runner.run_read(inspect_memory_snapshot_integrity)

        assert len(issues) == 1
        assert (
            issues[0].failure_kind
            is MemorySnapshotIntegrityFailureKind.DIGEST_MISMATCH
        )
        assert issues[0].snapshot_id == snapshot.snapshot_id


def test_memory_snapshot_integrity_classifies_row_digest_column_mismatch(
    tmp_path: Path,
) -> None:
    """手动 SQL 篡改 snapshot_digest 列时归类为 digest mismatch。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        snapshot = _write_integrity_compact_snapshot(store)
        _replace_snapshot_digest(store, snapshot.snapshot_id, "sha256:manual-corrupt")

        issues = store.transaction_runner.run_read(inspect_memory_snapshot_integrity)

        assert len(issues) == 1
        assert (
            issues[0].failure_kind
            is MemorySnapshotIntegrityFailureKind.DIGEST_MISMATCH
        )
        assert issues[0].snapshot_id == snapshot.snapshot_id


def test_memory_snapshot_integrity_classifies_unsupported_old_item_kind(
    tmp_path: Path,
) -> None:
    """旧 durable verified_fact item kind 被分类并继续使普通读路径 fail closed。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        snapshot = _write_integrity_compact_snapshot(store)
        _insert_old_verified_fact_item(store, snapshot)

        issues = store.transaction_runner.run_read(inspect_memory_snapshot_integrity)

        with pytest.raises(HostDurableError, match="verified_fact"):
            store.transaction_runner.run_read(
                lambda transaction: read_memory_snapshot(
                    transaction,
                    snapshot.snapshot_id,
                )
            )

        assert len(issues) == 1
        assert (
            issues[0].failure_kind
            is MemorySnapshotIntegrityFailureKind.UNSUPPORTED_ITEM_KIND
        )
        assert issues[0].snapshot_id == snapshot.snapshot_id


def test_memory_snapshot_integrity_classifies_unknown_item_kind(tmp_path: Path) -> None:
    """未知 durable memory item kind 被分类为 unsupported item kind。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        snapshot = _write_integrity_compact_snapshot(store)
        _insert_unsupported_memory_item_kind(store, snapshot, "mystery_memory_kind")

        issues = store.transaction_runner.run_read(inspect_memory_snapshot_integrity)

        assert len(issues) == 1
        assert (
            issues[0].failure_kind
            is MemorySnapshotIntegrityFailureKind.UNSUPPORTED_ITEM_KIND
        )
        assert issues[0].snapshot_id == snapshot.snapshot_id


def test_memory_snapshot_integrity_reports_mixed_damaged_rows(
    tmp_path: Path,
) -> None:
    """Memory snapshot integrity classifier 对多个 damaged rows 返回全部诊断。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        first_snapshot = _write_integrity_compact_snapshot(
            store,
            event_id="compact-1",
            claim_text="收入增长。",
        )
        second_snapshot = _write_integrity_compact_snapshot(
            store,
            event_id="compact-2",
            claim_text="利润提升。",
            session_id="session-2",
            event_sequence=2,
        )
        _replace_snapshot_json(store, first_snapshot.snapshot_id, "{not-json")
        _replace_snapshot_json(
            store,
            second_snapshot.snapshot_id,
            _snapshot_json_with_changed_built_at(second_snapshot),
        )

        issues = store.transaction_runner.run_read(inspect_memory_snapshot_integrity)

        assert {issue.failure_kind for issue in issues} == {
            MemorySnapshotIntegrityFailureKind.INVALID_JSON,
            MemorySnapshotIntegrityFailureKind.DIGEST_MISMATCH,
        }


def test_memory_snapshot_integrity_classifies_storage_read_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Memory snapshot integrity scan 读取失败时返回 storage_read_failed。"""

    def _raise_storage_read_failed(
        transaction: HostTransaction,
    ) -> tuple[HostRow, ...]:
        """模拟 SQLite scan failure。

        :param transaction: Host durable transaction。
        :returns: 不返回；始终抛出 SQLite 错误。
        :raises sqlite3.OperationalError: 始终抛出。
        """

        del transaction
        raise sqlite3.OperationalError("forced snapshot scan failure")

    monkeypatch.setattr(
        durable_memory_module,
        "_memory_snapshot_integrity_rows",
        _raise_storage_read_failed,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        issues = store.transaction_runner.run_read(inspect_memory_snapshot_integrity)

        assert len(issues) == 1
        assert (
            issues[0].failure_kind
            is MemorySnapshotIntegrityFailureKind.STORAGE_READ_FAILED
        )
        assert issues[0].snapshot_id is None


def test_memory_snapshot_integrity_classifies_row_identity_read_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Memory snapshot integrity scan 识别单行 identity 字段读取失败。"""

    def _rows_with_missing_identity(
        transaction: HostTransaction,
    ) -> tuple[HostRow, ...]:
        """模拟 scan 返回缺少 identity 字段的畸形 row。

        :param transaction: Host durable transaction。
        :returns: 缺少 ``session_id`` 的 snapshot row。
        """

        del transaction
        return (
            HostRow(
                columns=(
                    "snapshot_id",
                    "consumer_id",
                    "checkpoint_event_sequence",
                    "policy_digest",
                    "snapshot_digest",
                    "snapshot_json",
                ),
                values=(
                    "snapshot-identity-corrupt",
                    CONVERSATION_MEMORY_CONSUMER_ID,
                    1,
                    "sha256:policy",
                    "sha256:snapshot",
                    "{}",
                ),
            ),
        )

    monkeypatch.setattr(
        durable_memory_module,
        "_memory_snapshot_integrity_rows",
        _rows_with_missing_identity,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        issues = store.transaction_runner.run_read(inspect_memory_snapshot_integrity)

        assert len(issues) == 1
        assert (
            issues[0].failure_kind
            is MemorySnapshotIntegrityFailureKind.STORAGE_READ_FAILED
        )
        assert issues[0].message.startswith(
            "memory snapshot row identity read failed:"
        )
        assert issues[0].snapshot_id is None


def _write_integrity_compact_snapshot(
    store: HostDurableStore,
    *,
    event_id: str = "compact-1",
    claim_text: str = "收入增长。",
    session_id: str = _SESSION_ID,
    event_sequence: int = 1,
) -> ConversationMemorySnapshotVNext:
    """写入测试用 compact event 与 memory snapshot。

    :param store: Host durable store。
    :param event_id: compact event id。
    :param claim_text: compact fact claim 文本。
    :param session_id: snapshot 所属 session id。
    :param event_sequence: compact event sequence。
    :returns: 已写入的 memory snapshot。
    """

    payload = _accepted_compact_payload(facts=[_fact(claim_text)])
    store.transaction_runner.run_write(
        lambda transaction: append_event(
            transaction,
            EventLogAppendRequest(
                event_id=event_id,
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id=_RUN_ID,
                attempt_id=_ATTEMPT_ID,
                execution_id=_EXECUTION_ID,
                event_type=CONTEXT_COMPACTED,
                occurred_at=_OCCURRED_AT,
                actor="pytest",
                source="pytest",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason=None,
                payload_json=payload,
                payload_ref=None,
                payload_digest=None,
            ),
        ).row
    )
    projection_event = MemoryProjectionEvent(
        event_sequence=event_sequence,
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT.value,
        event_type=CONTEXT_COMPACTED,
        session_id=session_id,
        run_id=_RUN_ID,
        attempt_id=_ATTEMPT_ID,
        execution_id=_EXECUTION_ID,
        occurred_at=_NOW,
        payload_ref=None,
        payload_digest=None,
        payload=payload,
        compacted_semantics=parse_context_compacted_semantic_payload(payload),
    )
    snapshot = project_conversation_memory_event(
        previous_snapshot=None,
        event=projection_event,
        policy=_policy(),
        built_at=_NOW,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
    )
    store.transaction_runner.run_write(
        lambda transaction: write_memory_snapshot_with_checkpoint(
            transaction,
            snapshot,
            now=_NOW,
        )
    )
    return snapshot


def _replace_snapshot_json(
    store: HostDurableStore,
    snapshot_id: str,
    snapshot_json: str,
) -> None:
    """直接替换 snapshot JSON 以模拟手动 durable corruption。

    :param store: Host durable store。
    :param snapshot_id: snapshot id。
    :param snapshot_json: 替换后的 JSON 文本。
    :returns: ``None``。
    """

    store.transaction_runner.run_write(
        lambda transaction: transaction.execute(
            f"""
            UPDATE {TABLE_HOST_MEMORY_SNAPSHOTS}
            SET snapshot_json = ?
            WHERE snapshot_id = ?
            """,
            (snapshot_json, snapshot_id),
        )
    )


def _replace_snapshot_digest(
    store: HostDurableStore,
    snapshot_id: str,
    snapshot_digest: str,
) -> None:
    """直接替换 snapshot digest 列以模拟手动 durable corruption。

    :param store: Host durable store。
    :param snapshot_id: snapshot id。
    :param snapshot_digest: 替换后的 digest 文本。
    :returns: ``None``。
    """

    store.transaction_runner.run_write(
        lambda transaction: transaction.execute(
            f"""
            UPDATE {TABLE_HOST_MEMORY_SNAPSHOTS}
            SET snapshot_digest = ?
            WHERE snapshot_id = ?
            """,
            (snapshot_digest, snapshot_id),
        )
    )


def _snapshot_json_with_changed_built_at(
    snapshot: ConversationMemorySnapshotVNext,
) -> str:
    """返回保留旧 digest 但内容已变更的 snapshot JSON。

    :param snapshot: 原始 snapshot。
    :returns: digest mismatch JSON 文本。
    """

    snapshot_value = conversation_memory_snapshot_to_json_value(snapshot)
    if not isinstance(snapshot_value, Mapping):
        raise AssertionError("snapshot JSON value must be an object")
    corrupted_value: dict[str, JsonValue] = dict(snapshot_value)
    corrupted_value["built_at"] = "2026-05-17T00:00:00.000000Z"
    return canonical_json_dumps(corrupted_value)


def _insert_old_verified_fact_item(
    store: HostDurableStore,
    snapshot: ConversationMemorySnapshotVNext,
) -> None:
    """插入旧 verified_fact item kind 以模拟旧库或手工损坏。

    :param store: Host durable store。
    :param snapshot: 已存在的 memory snapshot。
    :returns: ``None``。
    """

    _insert_unsupported_memory_item_kind(store, snapshot, "verified_fact")


def _insert_unsupported_memory_item_kind(
    store: HostDurableStore,
    snapshot: ConversationMemorySnapshotVNext,
    item_kind: str,
) -> None:
    """插入不受支持的 item kind 以模拟旧库或手工损坏。

    :param store: Host durable store。
    :param snapshot: 已存在的 memory snapshot。
    :param item_kind: 待插入的 item kind。
    :returns: ``None``。
    """

    store.transaction_runner.run_write(
        lambda transaction: _insert_unsupported_memory_item_kind_in_transaction(
            transaction,
            snapshot,
            item_kind,
        )
    )


def _insert_unsupported_memory_item_kind_in_transaction(
    transaction: HostTransaction,
    snapshot: ConversationMemorySnapshotVNext,
    item_kind: str,
) -> None:
    """在当前 transaction 中插入不受支持的 item kind。

    :param transaction: Host durable transaction。
    :param snapshot: 已存在的 memory snapshot。
    :param item_kind: 待插入的 item kind。
    :returns: ``None``。
    """

    transaction.execute("PRAGMA ignore_check_constraints = ON")
    try:
        transaction.execute(
            f"""
            INSERT INTO {TABLE_HOST_MEMORY_ITEMS} (
              item_id,
              snapshot_id,
              session_id,
              item_kind,
              claim_status,
              event_id,
              event_sequence,
              producer_kind,
              producer_name,
              payload_ref,
              payload_digest,
              item_json,
              included_reason,
              excluded_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "old-verified-fact-item",
                snapshot.snapshot_id,
                snapshot.session_id,
                item_kind,
                "evidence_backed",
                snapshot.cursor.checkpoint_event_id,
                snapshot.cursor.checkpoint_event_sequence,
                "tool",
                "pytest",
                None,
                None,
                "{}",
                None,
                None,
            ),
        )
    finally:
        transaction.execute("PRAGMA ignore_check_constraints = OFF")
