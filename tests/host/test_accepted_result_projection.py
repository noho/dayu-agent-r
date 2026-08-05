"""Host accepted result projection helper 测试。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_outcome import ToolCompletedOutcome
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.host.api import RunStatus
from dayu.host.accepted_tool_outcome import accepted_tool_outcome_json
from dayu.host.accepted_result_projection import (
    AcceptedToolResultProjection,
    AcceptedToolResultQueryState,
    AcceptedToolResultSourceState,
    AcceptedToolResultStatus,
    project_accepted_tool_result,
    project_planned_accepted_tool_result,
)
from dayu.host.compact_material import (
    CompactMaterialPack,
    PreDispatchCompactMaterialView,
    build_compact_material_pack,
    build_pre_dispatch_compact_material_view,
    initial_segment_selection,
    select_compact_segment,
)
from dayu.host.compaction import (
    CompactMaterialBlockKind,
    CompactSegmentTrigger,
    CompactSourceKindV3,
    CompactionRequest,
)
from dayu.host.context_budget import BudgetEstimate
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.queue_policy import RunQueuePolicy
from dayu.host.evidence import (
    ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT,
    AcceptedToolEvidenceLLMMaterial,
    render_accepted_tool_evidence_for_llm,
)
from dayu.host.context_governance import compact_output_caps_v3_from_memory_policy
from dayu.host.durable.memory import _memory_projection_event_from_view
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.payload import (
    PayloadDescriptor,
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
    AcceptedEvidenceProducerEventRefMismatchError,
    AcceptedEvidenceResultRef,
    AcceptedEvidenceToolQuery,
    OpaqueEvidenceRef,
    accepted_evidence_envelope_from_json_value,
    accepted_evidence_envelope_from_payload,
    accepted_evidence_envelope_to_json_value,
)
from dayu.host.memory import (
    CONVERSATION_MEMORY_CONSUMER_ID,
    ConversationMemorySnapshotVNext,
    build_conversation_memory_snapshot_from_events,
    default_memory_projection_policy,
)
from dayu.host.payload_resolution import event_payload_object
from dayu.host.projection import projection_event_view_from_row
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
_CITATION_OBJECT: dict[str, JsonValue] = {
    "document_id": "MSFT-10K-2025",
    "source_type": "sec_filing",
    "unknown_future_member": {"page": 42, "section": "Revenue"},
}
_OPAQUE_SENTINEL_REFS = (
    OpaqueEvidenceRef(
        ref_kind="fliing-typo",
        ref_id="opaque-should-never-reach-llm",
        digest=None,
    ),
    OpaqueEvidenceRef(
        ref_kind="eventlog",
        ref_id="event-internal-only",
        digest=None,
    ),
    OpaqueEvidenceRef(
        ref_kind="eventlogg",
        ref_id="event-typo-should-never-reach-llm",
        digest=None,
    ),
)


def _compaction_request_for_material_pack(
    material_pack: CompactMaterialPack,
) -> CompactionRequest:
    """把跨消费者 material pack 绑定到唯一 production input owner。

    :param material_pack: 已由 production builder 构造的 material pack。
    :returns: 可通过 ``CompactionRequest.compact_input`` 读取输入的请求。
    :raises ValueError: material pack 缺少 current source ref 时抛出。
    """

    current_refs = material_pack.current_input_anchor.canonical_source_refs
    if len(current_refs) == 0:
        raise ValueError("material pack current input source ref is required")
    current_ref = current_refs[0]
    return CompactionRequest(
        trigger_source=ContextCompactionTriggerSource.PROACTIVE,
        session_id=_SESSION_ID,
        run_id=_RUN_ID,
        attempt_id=None,
        execution_id=None,
        memory_snapshot_cursor=None,
        material_pack=material_pack,
        segment_selection=initial_segment_selection(
            trigger_source=CompactSegmentTrigger.PROACTIVE,
            input_cursor=1,
            material_pack=material_pack,
        ),
        evidence_backed_fact_refs=(),
        recent_raw_turn_refs=(current_ref,),
        older_raw_turn_refs=(),
        existing_episode_summary_refs=(),
        budget_before_compact=BudgetEstimate(
            estimated_input_tokens=100,
            input_budget_tokens=4096,
            soft_threshold_tokens=3200,
            hard_threshold_tokens=3900,
            safety_margin_tokens=200,
            estimator_digest=_DIGEST,
            overage_reason=None,
        ),
        output_caps=compact_output_caps_v3_from_memory_policy(
            default_memory_projection_policy()
        ),
    )


def test_planned_and_committed_projection_share_one_owner_contract(
    tmp_path: Path,
) -> None:
    """planned wait payload 与 committed canonical fact 产生完全相同的投影。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: planned/committed owner contract 漂移时抛出。
    """

    event_log = EventLogStore()
    projections: (
        tuple[
            AcceptedToolResultProjection | None,
            AcceptedToolResultProjection,
        ]
        | None
    ) = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:

        def operation(
            transaction: HostTransaction,
        ) -> tuple[
            AcceptedToolResultProjection | None,
            AcceptedToolResultProjection,
        ]:
            """在同一 transaction 中比较 committed 与 planned 投影。

            :param transaction: 当前 Host transaction。
            :returns: committed 与 planned 投影。
            :raises HostDurableError: canonical payload 无法严格投影时抛出。
            """

            row = _append_tool_result_with_request(
                transaction,
                event_log,
                event_id="event-planned-committed-equivalence",
                tool_call_id="tool-call-planned-committed-equivalence",
                tool_fact_kind="completed",
                raw_tool_outcome=_completed_outcome_json({"summary": "Equivalent projection"}),
                source_refs=_OPAQUE_SENTINEL_REFS,
            )
            payload = event_payload_object(
                transaction,
                row,
                payload_label="planned accepted tool result",
            )
            return (
                project_accepted_tool_result(transaction, row),
                project_planned_accepted_tool_result(
                    transaction,
                    event_id=row.event_id,
                    session_id=row.session_id,
                    run_id=_RUN_ID,
                    attempt_id=_ATTEMPT_ID,
                    execution_id=_EXECUTION_ID,
                    occurred_at=row.occurred_at,
                    payload=payload,
                ),
            )

        projections = store.transaction_runner.run_write(operation)

    assert projections is not None
    committed, planned = projections
    assert committed is not None
    assert planned == committed


class _ColdResultDescriptorFailure(StrEnum):
    """测试用 cold result descriptor 损坏分类。"""

    REF_MISMATCH = "ref_mismatch"
    DIGEST_MISMATCH = "digest_mismatch"
    REF_MISSING = "ref_missing"
    DIGEST_MISSING = "digest_missing"


def _completed_outcome_json(value: JsonValue) -> JsonValue:
    """通过 accepted outcome codec 构造真实 completed result shape。

    :param value: producer-owned success value。
    :returns: canonical accepted tool outcome JSON。
    :raises ValueError: value 不是合法 JSON 时由 typed contract 抛出。
    """

    return accepted_tool_outcome_json(ToolCompletedOutcome(result=ToolResultSuccess(ok=True, value=value, meta=None)))


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
                raw_tool_outcome=_completed_outcome_json(
                    {
                        "citation": _CITATION_OBJECT,
                        "summary": "Revenue found",
                    }
                ),
                source_refs=_OPAQUE_SENTINEL_REFS,
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
    assert projection.source.text == canonical_json_dumps(_CITATION_OBJECT)


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
    assert projection.query.text == (f"参数：{canonical_json_dumps({'arguments': {'ticker': 'AAPL'}})}")
    assert projection.status is AcceptedToolResultStatus.FAILED
    assert projection is not None
    assert projection.source.state is AcceptedToolResultSourceState.UNAVAILABLE
    assert projection.source.diagnostic_reason == "business_source_unavailable"
    assert projection.source.text == ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT


@pytest.mark.parametrize(
    "result_value",
    (
        {},
        {"citaiton": _CITATION_OBJECT},
        {"citation": "not-an-object"},
    ),
    ids=("missing", "misspelled", "wrong-type"),
)
def test_projection_uses_one_neutral_source_text_for_invalid_citation_shapes(
    tmp_path: Path,
    result_value: JsonValue,
) -> None:
    """无 citation、拼错或类型错误都使用唯一业务中性文案。

    :param tmp_path: pytest 临时目录。
    :param result_value: producer success value 反例。
    """

    event_log = EventLogStore()
    projection: AcceptedToolResultProjection | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        row = store.transaction_runner.run_write(
            lambda transaction: _append_tool_result_with_request(
                transaction,
                event_log,
                event_id="event-result-invalid-citation",
                tool_call_id="tool-call-invalid-citation",
                tool_fact_kind="completed",
                raw_tool_outcome=_completed_outcome_json(result_value),
                source_refs=_OPAQUE_SENTINEL_REFS,
            )
        )
        projection = store.transaction_runner.run_read(
            lambda transaction: project_accepted_tool_result(transaction, row)
        )

    assert projection is not None
    assert projection.source.state is AcceptedToolResultSourceState.UNAVAILABLE
    assert projection.source.text == "该工具结果未提供业务来源。"
    assert projection.source.diagnostic_reason == "business_source_unavailable"


def test_opaque_provenance_round_trips_but_stays_out_of_projection(
    tmp_path: Path,
) -> None:
    """opaque provenance 在 envelope round-trip 保留但不进入共享 projection。"""

    event_log = EventLogStore()
    envelope: AcceptedEvidenceEnvelope | None = None
    projection: AcceptedToolResultProjection | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        row = store.transaction_runner.run_write(
            lambda transaction: _append_tool_result_with_request(
                transaction,
                event_log,
                event_id="event-result-opaque-round-trip",
                tool_call_id="tool-call-opaque-round-trip",
                tool_fact_kind="completed",
                raw_tool_outcome=_completed_outcome_json({"citation": _CITATION_OBJECT}),
                source_refs=_OPAQUE_SENTINEL_REFS,
                locator_refs=tuple(reversed(_OPAQUE_SENTINEL_REFS)),
            )
        )
        payload = store.transaction_runner.run_read(
            lambda transaction: event_payload_object(
                transaction,
                row,
                payload_label="opaque round-trip accepted result",
            )
        )
        envelope = accepted_evidence_envelope_from_payload(payload, producer_event_ref=row.event_id)
        projection = store.transaction_runner.run_read(
            lambda transaction: project_accepted_tool_result(transaction, row)
        )

    assert envelope is not None
    assert projection is not None
    assert envelope.source_refs == _OPAQUE_SENTINEL_REFS
    assert envelope.locator_refs == tuple(reversed(_OPAQUE_SENTINEL_REFS))
    projection_text = repr(projection)
    for ref in _OPAQUE_SENTINEL_REFS:
        assert ref.ref_kind not in projection_text
        assert ref.ref_id not in projection_text


@pytest.mark.parametrize(
    ("invalid_case", "expected_message"),
    (
        ("non_object", "must be a JSON object"),
        ("unexpected_field", "unexpected JSON fields"),
        ("required_string", "tool_name must be a string"),
        ("optional_string", "must be a string or null"),
        ("required_boolean", "truncation_applied must be a boolean"),
        ("required_list", "source_refs must be a JSON array"),
    ),
)
def test_evidence_envelope_decoder_rejects_invalid_owner_shapes(
    invalid_case: str,
    expected_message: str,
) -> None:
    """evidence owner decoder 对各类非法 JSON shape fail closed。

    :param invalid_case: 要构造的非法 envelope shape。
    :param expected_message: 对应 owner validation 错误摘要。
    :returns: ``None``。
    :raises AssertionError: 非法 shape 未由 evidence owner 拒绝时抛出。
    """

    invalid_value = _invalid_accepted_evidence_envelope_json(invalid_case)
    with pytest.raises(ValueError, match=expected_message):
        accepted_evidence_envelope_from_json_value(invalid_value)


def test_projection_missing_request_atom_fails_closed(
    tmp_path: Path,
) -> None:
    """canonical request atom 缺失时共享 projection 抛 durable error。"""

    event_log = EventLogStore()
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
        with pytest.raises(HostDurableError, match="request atom is missing"):
            store.transaction_runner.run_read(lambda transaction: project_accepted_tool_result(transaction, row))


def test_projection_missing_envelope_fails_closed(
    tmp_path: Path,
) -> None:
    """accepted evidence envelope 缺失时共享 projection fail closed。"""

    event_log = EventLogStore()
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
        with pytest.raises(HostDurableError, match="evidence envelope is missing"):
            store.transaction_runner.run_read(lambda transaction: project_accepted_tool_result(transaction, row))


def test_renderer_rejects_missing_typed_material() -> None:
    """renderer 不接受缺失 material，禁止整体 fallback。"""

    with pytest.raises(TypeError, match="AcceptedToolEvidenceLLMMaterial"):
        render_accepted_tool_evidence_for_llm(cast(AcceptedToolEvidenceLLMMaterial, None))


def test_memory_consumer_rejects_canonical_result_without_llm_material(
    tmp_path: Path,
) -> None:
    """Memory owner 拒绝缺 typed material 的 canonical accepted result。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: Memory 跳过损坏 evidence 或构造 fallback 时抛出。
    """

    event_log = EventLogStore()
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        row = store.transaction_runner.run_write(
            lambda transaction: _append_tool_result_with_request(
                transaction,
                event_log,
                event_id="event-result-memory-no-material",
                tool_call_id="tool-call-memory-no-material",
                tool_fact_kind="completed",
                raw_tool_outcome=_completed_outcome_json({"summary": "result"}),
                source_refs=(),
                include_raw_outcome=False,
            )
        )

        with pytest.raises(
            HostDurableError,
            match="TOOL_RESULT_ACCEPTED memory LLM material is missing",
        ):
            store.transaction_runner.run_read(
                lambda transaction: _memory_projection_event_from_view(
                    transaction,
                    projection_event_view_from_row(transaction, row),
                )
            )


def test_projection_missing_envelope_and_blank_status_handling(
    tmp_path: Path,
) -> None:
    """缺 envelope fail closed；canonical request 完整时空状态映射 unknown。"""

    event_log = EventLogStore()
    blank_status_projection: AcceptedToolResultProjection | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        wrong_type_row = store.transaction_runner.run_write(
            lambda transaction: _append_event(
                transaction,
                event_log,
                event_id="event-result-wrong-tool-name",
                event_type="TOOL_RESULT_ACCEPTED",
                payload={
                    "tool_name": 123,
                    "raw_tool_outcome": {"kind": "completed"},
                },
            )
        )
        blank_status_row = store.transaction_runner.run_write(
            lambda transaction: _append_tool_result_with_request(
                transaction,
                event_log,
                event_id="event-result-blank-status",
                tool_call_id="tool-call-blank-status",
                tool_fact_kind=" ",
                raw_tool_outcome={"kind": "completed"},
                source_refs=(),
            )
        )

        with pytest.raises(HostDurableError):
            store.transaction_runner.run_read(
                lambda transaction: project_accepted_tool_result(
                    transaction,
                    wrong_type_row,
                )
            )
        blank_status_projection = store.transaction_runner.run_read(
            lambda transaction: project_accepted_tool_result(
                transaction,
                blank_status_row,
            )
        )

    assert blank_status_projection is not None
    assert blank_status_projection.status is AcceptedToolResultStatus.UNKNOWN
    assert "accepted_status_unavailable" in blank_status_projection.diagnostic_reasons


def test_accepted_evidence_producer_mismatch_is_typed_exception(
    tmp_path: Path,
) -> None:
    """producer event ref mismatch 使用专用异常并由 projection 包装 cause。"""

    event_log = EventLogStore()
    envelope = _accepted_envelope(
        event_id="event-result-observed",
        tool_call_id="tool-call-mismatch",
        request_event_ref=None,
        normalized_arguments_digest=_DIGEST,
        raw_tool_outcome={"kind": "completed"},
        source_refs=(),
    )
    payload: dict[str, JsonValue] = {
        "accepted_evidence_envelope": accepted_evidence_envelope_to_json_value(envelope),
        "raw_tool_outcome": {"kind": "completed"},
    }
    wrapped_cause: BaseException | None = None
    with pytest.raises(AcceptedEvidenceProducerEventRefMismatchError) as direct:
        accepted_evidence_envelope_from_payload(
            payload,
            producer_event_ref="event-result-expected",
        )
    assert direct.value.expected_event_ref == "event-result-expected"
    assert direct.value.observed_event_ref == "event-result-observed"

    with open_host_durable_store(_durable_options(tmp_path)) as store:
        row = store.transaction_runner.run_write(
            lambda transaction: _append_event(
                transaction,
                event_log,
                event_id="event-result-expected",
                event_type="TOOL_RESULT_ACCEPTED",
                payload=payload,
            )
        )
        with pytest.raises(HostDurableError) as wrapped:
            store.transaction_runner.run_read(lambda transaction: project_accepted_tool_result(transaction, row))
        wrapped_cause = wrapped.value.__cause__

    assert isinstance(wrapped_cause, AcceptedEvidenceProducerEventRefMismatchError)


def test_projection_maps_governed_error_and_unknown_status(tmp_path: Path) -> None:
    """projection 按封闭状态表映射 governed_error 与 unknown。"""

    event_log = EventLogStore()
    governed_projection: AcceptedToolResultProjection | None = None
    unknown_projection: AcceptedToolResultProjection | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        governed = store.transaction_runner.run_write(
            lambda transaction: _append_tool_result_with_request(
                transaction,
                event_log,
                event_id="event-result-governed",
                tool_call_id="tool-call-governed",
                tool_fact_kind="governed_error",
                raw_tool_outcome={"kind": "failed", "result": {"ok": False}},
                source_refs=(),
            )
        )
        unknown = store.transaction_runner.run_write(
            lambda transaction: _append_tool_result_with_request(
                transaction,
                event_log,
                event_id="event-result-unknown",
                tool_call_id="tool-call-unknown",
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
    assert "accepted_status_unavailable" in unknown_projection.diagnostic_reasons


def test_projection_identity_mismatch_fails_closed(tmp_path: Path) -> None:
    """request atom 与 envelope 工具身份不匹配时抛 durable error。"""

    event_log = EventLogStore()
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
        with pytest.raises(HostDurableError, match="envelope mismatch"):
            store.transaction_runner.run_read(lambda transaction: project_accepted_tool_result(transaction, row))


@pytest.mark.parametrize(
    "result_execution_id",
    (None, "execution-other"),
    ids=("missing", "mismatch"),
)
def test_projection_result_execution_identity_mismatch_fails_closed(
    tmp_path: Path,
    result_execution_id: str | None,
) -> None:
    """accepted result execution 缺失或漂移时严格身份校验 fail closed。

    :param tmp_path: pytest 临时目录。
    :param result_execution_id: 缺失或与 canonical request 不同的 execution id。
    :returns: ``None``。
    :raises AssertionError: 不同源 result 被接受或异常类型不正确时抛出。
    """

    event_log = EventLogStore()
    with open_host_durable_store(_durable_options(tmp_path)) as store:

        def seed(transaction: HostTransaction) -> EventLogRow:
            """写入 execution 不同源的 request / accepted result。

            :param transaction: Host transaction。
            :returns: accepted result row。
            :raises HostDurableError: durable append 失败时由 store 抛出。
            """

            arguments_json: JsonValue = {"arguments": {"ticker": "MSFT"}}
            arguments_digest = sha256_digest_json(arguments_json)
            request = _append_tool_call_requested(
                transaction,
                event_log,
                event_id=f"event-request-execution-{result_execution_id}",
                tool_call_id="tool-call-execution-mismatch",
                arguments_json=arguments_json,
                semantic_query_text=None,
            )
            return _append_tool_result(
                transaction,
                event_log,
                event_id=f"event-result-execution-{result_execution_id}",
                tool_call_id="tool-call-execution-mismatch",
                request_event_ref=request.event_id,
                normalized_arguments_digest=arguments_digest,
                tool_fact_kind="completed",
                raw_tool_outcome={"kind": "completed", "result": {"ok": True}},
                source_refs=(),
                execution_id=result_execution_id,
            )

        row = store.transaction_runner.run_write(seed)
        with pytest.raises(
            HostDurableError,
            match="accepted result request atom identity mismatch",
        ):
            store.transaction_runner.run_read(lambda transaction: project_accepted_tool_result(transaction, row))


def test_projection_wait_resolution_status_takes_priority(tmp_path: Path) -> None:
    """wait resolution kind 优先于普通 tool fact kind。"""

    event_log = EventLogStore()
    projection: AcceptedToolResultProjection | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        row = store.transaction_runner.run_write(
            lambda transaction: _append_tool_result_with_request(
                transaction,
                event_log,
                event_id="event-result-wait-resolution",
                tool_call_id="tool-call-wait-resolution",
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


def test_projection_never_guesses_business_source_from_opaque_refs(
    tmp_path: Path,
) -> None:
    """unknown、拼错和 internal opaque refs 都不成为业务 source。"""

    event_log = EventLogStore()
    projection: AcceptedToolResultProjection | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        row = store.transaction_runner.run_write(
            lambda transaction: _append_tool_result_with_request(
                transaction,
                event_log,
                event_id="event-result-source-filter",
                tool_call_id="tool-call-source-filter",
                tool_fact_kind="completed",
                raw_tool_outcome={"kind": "completed", "result": {"ok": True}},
                source_refs=_OPAQUE_SENTINEL_REFS,
            )
        )
        projection = store.transaction_runner.run_read(
            lambda transaction: project_accepted_tool_result(transaction, row)
        )

    assert projection is not None
    assert projection.source.state is AcceptedToolResultSourceState.UNAVAILABLE
    assert projection.source.text == ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT
    assert "source_locator_refs" not in {field.name for field in fields(AcceptedToolResultProjection)}
    assert "OpaqueEvidenceRef" not in repr(projection)
    for ref in _OPAQUE_SENTINEL_REFS:
        assert ref.ref_kind not in projection.source.text
        assert ref.ref_id not in projection.source.text


def test_projection_unavailable_source_uses_shared_llm_text_and_ignores_internal_refs(
    tmp_path: Path,
) -> None:
    """source 不可用时由 projection owner 给出共享 LLM-facing 文案。"""

    event_log = EventLogStore()
    projection: AcceptedToolResultProjection | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        row = store.transaction_runner.run_write(
            lambda transaction: _append_tool_result_with_request(
                transaction,
                event_log,
                event_id="event-result-source-unavailable",
                tool_call_id="tool-call-source-unavailable",
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


def test_projection_resolves_hot_payload_cold_result_and_keeps_inline_direct(
    tmp_path: Path,
) -> None:
    """projection 区分已含 raw outcome 的 inline 与仅含 ref 的 hot payload。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: inline payload 被误跟随 descriptor，或 hot payload
        未解析 cold result 时抛出。
    """

    event_log = EventLogStore()
    descriptor_payload: JsonValue = {
        "kind": "completed",
        "result": {"ok": True, "summary": "descriptor result"},
    }
    with open_host_durable_store(_durable_options(tmp_path)) as store:

        def seed(
            transaction: HostTransaction,
        ) -> tuple[
            EventLogRow,
            Mapping[str, JsonValue],
            EventLogRow,
            Mapping[str, JsonValue],
        ]:
            """写入 producer-shaped hot/cold result 与普通 inline result。

            :param transaction: Host transaction。
            :returns: descriptor row/hot payload 与 inline row/payload。
            :raises HostDurableError: durable payload 或 EventLog 写入失败时抛出。
            """

            arguments_json: JsonValue = {"arguments": {"ticker": "MSFT"}}
            arguments_digest = sha256_digest_json(arguments_json)
            descriptor_request = _append_tool_call_requested(
                transaction,
                event_log,
                event_id="event-request-descriptor",
                tool_call_id="tool-call-descriptor",
                arguments_json=arguments_json,
                semantic_query_text=None,
            )
            descriptor_row, descriptor_hot_payload, _ = _append_hot_cold_tool_result(
                transaction,
                event_log,
                event_id="event-result-descriptor",
                tool_call_id="tool-call-descriptor",
                request_event_ref=descriptor_request.event_id,
                normalized_arguments_digest=arguments_digest,
                raw_tool_outcome=descriptor_payload,
                source_refs=(),
            )
            inline_request = _append_tool_call_requested(
                transaction,
                event_log,
                event_id="event-request-inline-resolved",
                tool_call_id="tool-call-inline-resolved",
                arguments_json=arguments_json,
                semantic_query_text=None,
            )
            inline_row = _append_tool_result(
                transaction,
                event_log,
                event_id="event-result-inline-resolved",
                tool_call_id="tool-call-inline-resolved",
                request_event_ref=inline_request.event_id,
                normalized_arguments_digest=arguments_digest,
                tool_fact_kind="completed",
                raw_tool_outcome={
                    "kind": "completed",
                    "result": {"ok": True, "summary": "inline result"},
                },
                source_refs=(),
            )
            inline_payload = projection_event_view_from_row(
                transaction,
                inline_row,
            ).payload
            return (
                descriptor_row,
                descriptor_hot_payload,
                inline_row,
                inline_payload,
            )

        (
            descriptor_row,
            descriptor_hot_payload,
            inline_row,
            inline_payload,
        ) = store.transaction_runner.run_write(seed)
        descriptor_projection = store.transaction_runner.run_read(
            lambda transaction: project_accepted_tool_result(
                transaction,
                descriptor_row,
                resolved_payload=descriptor_hot_payload,
            )
        )
        inline_projection = store.transaction_runner.run_read(
            lambda transaction: project_accepted_tool_result(
                transaction,
                inline_row,
                resolved_payload=inline_payload,
            )
        )

        assert descriptor_projection.result_details_text == "descriptor result"
        assert descriptor_projection.status is AcceptedToolResultStatus.COMPLETED
        assert descriptor_projection.llm_material is not None
        assert descriptor_projection.llm_material.result_text == (canonical_json_dumps(descriptor_payload))
        assert inline_projection.result_details_text == "inline result"
        assert inline_projection.status is AcceptedToolResultStatus.COMPLETED
        assert inline_projection.llm_material is not None


@pytest.mark.parametrize("failure", tuple(_ColdResultDescriptorFailure))
def test_projection_hot_payload_cold_descriptor_corruption_fails_closed(
    tmp_path: Path,
    failure: _ColdResultDescriptorFailure,
) -> None:
    """hot payload 的 cold descriptor ref/digest 损坏或缺失时 fail closed。

    :param tmp_path: pytest 临时目录。
    :param failure: 单一 descriptor 损坏分类。
    :returns: ``None``。
    :raises AssertionError: shared projection 未拒绝损坏 descriptor 时抛出。
    """

    event_log = EventLogStore()
    with open_host_durable_store(_durable_options(tmp_path)) as store:

        def seed(
            transaction: HostTransaction,
        ) -> tuple[EventLogRow, Mapping[str, JsonValue], PayloadDescriptor]:
            """写入 producer-shaped hot/cold accepted result。

            :param transaction: Host transaction。
            :returns: result row、hot payload 与 cold descriptor。
            :raises HostDurableError: durable payload 或 EventLog 写入失败时抛出。
            """

            arguments_json: JsonValue = {"arguments": {"ticker": "MSFT"}}
            arguments_digest = sha256_digest_json(arguments_json)
            request = _append_tool_call_requested(
                transaction,
                event_log,
                event_id=f"event-request-cold-{failure.value}",
                tool_call_id=f"tool-call-cold-{failure.value}",
                arguments_json=arguments_json,
                semantic_query_text="Read descriptor result",
            )
            return _append_hot_cold_tool_result(
                transaction,
                event_log,
                event_id=f"event-result-cold-{failure.value}",
                tool_call_id=f"tool-call-cold-{failure.value}",
                request_event_ref=request.event_id,
                normalized_arguments_digest=arguments_digest,
                raw_tool_outcome=_completed_outcome_json({"summary": "strict cold result"}),
                source_refs=(),
            )

        row, hot_payload, _ = store.transaction_runner.run_write(seed)
        projected_row = row
        if failure is _ColdResultDescriptorFailure.REF_MISMATCH:
            projected_row = replace(row, payload_ref="payload-cold-ref-mismatch")
        elif failure is _ColdResultDescriptorFailure.DIGEST_MISMATCH:
            projected_row = replace(
                row,
                payload_digest=sha256_digest_json({"digest": "mismatch"}),
            )
        elif failure is _ColdResultDescriptorFailure.REF_MISSING:
            projected_row = replace(row, payload_ref=None, payload_digest=None)
        elif failure is _ColdResultDescriptorFailure.DIGEST_MISSING:
            projected_row = replace(row, payload_digest=None)
        projection = store.transaction_runner.run_read(
            lambda transaction: project_accepted_tool_result(
                transaction,
                projected_row,
                resolved_payload=hot_payload,
            )
        )

        assert projection.llm_material is None
        assert projection.result_text is None
        assert projection.status is AcceptedToolResultStatus.LOST
        assert "result_payload_unavailable" in projection.diagnostic_reasons


def test_projection_missing_event_payload_fails_closed(
    tmp_path: Path,
) -> None:
    """EventLog payload 不可读导致 canonical envelope 缺失时 fail closed。"""

    event_log = EventLogStore()
    with open_host_durable_store(_durable_options(tmp_path)) as store:

        def seed(transaction: HostTransaction) -> EventLogRow:
            """写入 payload JSON 非 object 的 accepted result event。

            :param transaction: Host transaction。
            :returns: accepted result row。
            """

            payload_ref = "payload-invalid-event-payload"
            payload_json: JsonValue = ["not-object"]
            payload_digest = sha256_digest_json(payload_json)
            PayloadStore().write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref=payload_ref,
                    payload_id="sqlite-invalid-event-payload",
                    payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                    payload_json=payload_json,
                    media_type="application/json",
                    metadata={"kind": "accepted_result_test"},
                    expected_digest=payload_digest,
                ),
            )
            return _append_event(
                transaction,
                event_log,
                event_id="event-result-missing-event-payload",
                event_type="TOOL_RESULT_ACCEPTED",
                payload={},
                payload_ref=payload_ref,
                payload_digest=payload_digest,
            )

        row = store.transaction_runner.run_write(seed)
        with pytest.raises(HostDurableError, match="evidence envelope is missing"):
            store.transaction_runner.run_read(lambda transaction: project_accepted_tool_result(transaction, row))


def test_projection_mechanically_displays_legal_business_argument_names(
    tmp_path: Path,
) -> None:
    """合法业务参数名不经字段名分类，直接投影 canonical JSON。"""

    event_log = EventLogStore()
    projection: AcceptedToolResultProjection | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:

        def seed(transaction: HostTransaction) -> EventLogRow:
            """写入含合法路径、引用标签与 password-like 业务名的结果。

            :param transaction: Host transaction。
            :returns: accepted result row。
            """

            arguments_json: JsonValue = {
                "arguments": {
                    "file_path": "reports/COIN/annual-report.pdf",
                    "password_policy_name": "research-read-policy",
                    "scope_token": "scope-visible-business-label",
                    "ticker": "COIN",
                }
            }
            arguments_digest = sha256_digest_json(arguments_json)
            request = _append_tool_call_requested(
                transaction,
                event_log,
                event_id="event-request-business-arguments",
                tool_call_id="tool-call-business-arguments",
                arguments_json=arguments_json,
                semantic_query_text=None,
            )
            return _append_tool_result(
                transaction,
                event_log,
                event_id="event-result-business-arguments",
                tool_call_id="tool-call-business-arguments",
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
    assert projection.query.state is AcceptedToolResultQueryState.ARGUMENTS_SUMMARY
    assert projection.query.diagnostic_reason == "semantic_query_missing"
    assert projection.query.text == (
        '参数：{"arguments":{"file_path":"reports/COIN/annual-report.pdf",'
        '"password_policy_name":"research-read-policy",'
        '"scope_token":"scope-visible-business-label","ticker":"COIN"}}'
    )


def test_projection_maps_raw_result_ok_false_and_extracts_details(
    tmp_path: Path,
) -> None:
    """raw outcome result.ok=false 不重建状态，但仍抽取结构化 details。"""

    event_log = EventLogStore()
    projection: AcceptedToolResultProjection | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        row = store.transaction_runner.run_write(
            lambda transaction: _append_tool_result_with_request(
                transaction,
                event_log,
                event_id="event-result-raw-ok-false",
                tool_call_id="tool-call-raw-ok-false",
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
    assert projection.status is AcceptedToolResultStatus.UNKNOWN
    assert "accepted_status_unavailable" in projection.diagnostic_reasons
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
    current_row: EventLogRow | None = None
    with open_host_durable_store(_durable_options(tmp_path)) as store:

        def seed(
            transaction: HostTransaction,
        ) -> tuple[EventLogRow, Mapping[str, JsonValue], EventLogRow]:
            """写入 hot/cold 跨消费者等价性测试 facts。

            :param transaction: Host transaction。
            :returns: accepted result row、hot payload 与 current input row。
            :raises HostDurableError: descriptor 或 EventLog 写入失败时抛出。
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
            result, hot_payload, _ = _append_hot_cold_tool_result(
                transaction,
                event_log,
                event_id="event-result-cross-consumer",
                tool_call_id="tool-call-cross-consumer",
                request_event_ref=request.event_id,
                normalized_arguments_digest=arguments_digest,
                raw_tool_outcome=_completed_outcome_json(
                    {
                        "citation": _CITATION_OBJECT,
                        "summary": "Revenue is 100",
                    }
                ),
                source_refs=_OPAQUE_SENTINEL_REFS,
            )
            current = _append_event(
                transaction,
                event_log,
                event_id="event-current-cross-consumer",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "current question"},
            )
            return result, hot_payload, current

        result_row, hot_payload, current_row = store.transaction_runner.run_write(seed)
        projection = store.transaction_runner.run_read(
            lambda transaction: project_accepted_tool_result(
                transaction,
                result_row,
                resolved_payload=hot_payload,
            )
        )
        consumer = ToolTraceProjectionConsumer(ToolTraceSinkOptions(cold_jsonl_path=tmp_path / "trace.jsonl"))
        store.transaction_runner.run_write(
            lambda transaction: consumer.apply_event(
                transaction,
                projection_event_view_from_row(transaction, result_row),
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
                projection_event_view_from_row(transaction, result_row),
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
    assert projection.source.state is AcceptedToolResultSourceState.AVAILABLE
    assert projection.source.text == canonical_json_dumps(_CITATION_OBJECT)
    assert tool_trace_row is not None
    assert memory_snapshot is not None
    assert compact_view is not None
    assert current_row is not None
    evidence_blocks = tuple(
        block for block in compact_view.material_blocks if block.kind is CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE
    )
    assert len(evidence_blocks) == 1
    evidence_block = evidence_blocks[0]
    compact_selection = select_compact_segment(
        trigger_source=CompactSegmentTrigger.PROACTIVE,
        input_cursor=current_row.event_sequence,
        memory_snapshot_cursor=None,
        policy_digest="policy-r03-cross-consumer",
        material_blocks=compact_view.material_blocks,
    )
    compact_pack = build_compact_material_pack(
        selected_segment=compact_selection,
        material_blocks=compact_view.material_blocks,
        memory_snapshot=None,
        inline_delta_repair_view=None,
        current_input_ref=current_row.event_id,
        current_input_text="current question",
    )
    compact_input = _compaction_request_for_material_pack(compact_pack).compact_input
    evidence_sources = tuple(
        source
        for source in compact_input.source_boundary
        if source.source_kind is CompactSourceKindV3.EVIDENCE_MATERIAL
    )
    assert len(evidence_sources) == 1
    compact_evidence = evidence_sources[0]
    assert projection.llm_material is not None
    material = projection.llm_material
    run_input_text = render_accepted_tool_evidence_for_llm(material)
    memory_text = memory_snapshot.trace_memory.selected_recent_window[0].text
    trace_request = tool_trace_row.trace_summary["tool_request"]
    trace_result = tool_trace_row.trace_summary["tool_result"]
    assert isinstance(trace_request, dict)
    assert isinstance(trace_result, dict)
    assert trace_request["query_text"] == projection.query.text
    assert trace_request["query_state"] == projection.query.state.value
    assert trace_result["result_status"] == projection.status.value
    assert trace_result["result_text"] == projection.result_text
    assert trace_result["business_source_text"] == projection.source.text
    assert trace_result["business_source_state"] == projection.source.state.value
    assert "diagnostic_reason" not in trace_result
    block_material = evidence_block.accepted_tool_evidence
    assert block_material is not None
    assert block_material == material
    assert block_material.query_text == projection.query.text
    assert block_material.source_text == projection.source.text
    assert block_material.result_text == projection.result_text
    assert f"查询：{projection.query.text}" in compact_evidence.readable_text
    assert f"结果：{projection.result_text}" in compact_evidence.readable_text
    assert f"来源：{projection.source.text}" in compact_evidence.readable_text
    assert evidence_block.text == render_accepted_tool_evidence_for_llm(material)
    assert f"查询语义：{projection.query.text}" in run_input_text
    assert f"业务来源：{projection.source.text}" in run_input_text
    assert f"工具结果：{projection.result_text}" in run_input_text
    assert projection.query.text in memory_text
    assert projection.result_text is not None
    assert projection.result_text in memory_text
    assert projection.source.text is not None
    assert projection.source.text in memory_text
    visible_texts = (
        run_input_text,
        memory_text,
        canonical_json_dumps(compact_input.to_json()),
        str(tool_trace_row.trace_summary),
    )
    for visible_text in visible_texts:
        for ref in _OPAQUE_SENTINEL_REFS:
            assert ref.ref_kind not in visible_text
            assert ref.ref_id not in visible_text


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


def _invalid_accepted_evidence_envelope_json(invalid_case: str) -> JsonValue:
    """构造 evidence envelope strict decoder 的单点 shape 反例。

    :param invalid_case: 非法 shape 分类。
    :returns: 只破坏一个 owner 字段的 JSON 值。
    :raises AssertionError: 测试传入未知分类时抛出。
    """

    if invalid_case == "non_object":
        return ["not-an-envelope-object"]
    envelope_json = accepted_evidence_envelope_to_json_value(
        _accepted_envelope(
            event_id="event-result-invalid-envelope",
            tool_call_id="tool-call-invalid-envelope",
            request_event_ref="event-request-invalid-envelope",
            normalized_arguments_digest=_DIGEST,
            raw_tool_outcome=_completed_outcome_json({"summary": "result"}),
            source_refs=(),
        )
    )
    envelope_mapping = cast(dict[str, JsonValue], envelope_json)
    if invalid_case == "unexpected_field":
        envelope_mapping["unexpected"] = True
    elif invalid_case == "required_string":
        envelope_mapping["tool_name"] = 7
    elif invalid_case == "optional_string":
        tool_query = cast(dict[str, JsonValue], envelope_mapping["tool_query"])
        tool_query["tool_call_requested_event_ref"] = 7
    elif invalid_case == "required_boolean":
        result_ref = cast(dict[str, JsonValue], envelope_mapping["result_ref"])
        result_ref["truncation_applied"] = "false"
    elif invalid_case == "required_list":
        envelope_mapping["source_refs"] = "not-a-list"
    else:
        raise AssertionError(f"unknown invalid evidence envelope case: {invalid_case}")
    return envelope_mapping


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
    :param arguments_json: exact canonical request arguments JSON。
    :param semantic_query_text: 可选 semantic query 文本。
    :returns: appended EventLog row。
    """

    arguments_digest = sha256_digest_json(arguments_json)
    semantic_query_digest = (
        sha256_digest_json({"semantic_query_text": semantic_query_text}) if semantic_query_text is not None else None
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
            "arguments_json_size_bytes": len(canonical_json_dumps(arguments_json).encode("utf-8")),
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


def _append_hot_cold_tool_result(
    transaction: HostTransaction,
    event_log: EventLogStore,
    *,
    event_id: str,
    tool_call_id: str,
    request_event_ref: str,
    normalized_arguments_digest: str,
    raw_tool_outcome: JsonValue,
    source_refs: tuple[OpaqueEvidenceRef, ...],
) -> tuple[EventLogRow, Mapping[str, JsonValue], PayloadDescriptor]:
    """按 ToolRuntime 大结果 shape 写入 hot EventLog 与 cold result payload。

    该 helper 复用生产 descriptor/EventLog primitive：cold payload 包含完整
    ``raw_tool_outcome``，hot payload 只包含同一 envelope 与 descriptor pair。

    :param transaction: Host transaction。
    :param event_log: EventLog store。
    :param event_id: accepted result event id。
    :param tool_call_id: 工具调用 id。
    :param request_event_ref: canonical request atom event ref。
    :param normalized_arguments_digest: request 参数 digest。
    :param raw_tool_outcome: 完整 raw outcome JSON。
    :param source_refs: accepted evidence source refs。
    :returns: result row、hot payload 与 cold payload descriptor。
    :raises HostDurableError: descriptor 或 EventLog 写入失败时抛出。
    """

    payload_ref = f"payload-{event_id}"
    envelope = _accepted_envelope(
        event_id=event_id,
        tool_call_id=tool_call_id,
        request_event_ref=request_event_ref,
        normalized_arguments_digest=normalized_arguments_digest,
        raw_tool_outcome=raw_tool_outcome,
        source_refs=source_refs,
        payload_ref=payload_ref,
        payload_digest=None,
    )
    envelope_json = accepted_evidence_envelope_to_json_value(envelope)
    cold_payload: Mapping[str, JsonValue] = {
        "tool_call_id": tool_call_id,
        "tool_name": _TOOL_NAME,
        "normalized_arguments_digest": normalized_arguments_digest,
        "tool_fact_kind": "completed",
        "accepted_evidence_envelope": envelope_json,
        "payload_ref": None,
        "raw_tool_outcome": raw_tool_outcome,
    }
    descriptor = PayloadStore().write_sqlite_payload(
        transaction,
        SQLitePayloadWriteRequest(
            payload_ref=payload_ref,
            payload_id=f"sqlite-{event_id}",
            payload_format=SQLitePayloadFormat.CANONICAL_JSON,
            payload_json=cold_payload,
            media_type="application/json",
            metadata={"kind": "accepted_result_test"},
            expected_digest=None,
        ),
    )
    hot_payload: Mapping[str, JsonValue] = {
        "tool_call_id": tool_call_id,
        "tool_name": _TOOL_NAME,
        "normalized_arguments_digest": normalized_arguments_digest,
        "tool_fact_kind": "completed",
        "accepted_evidence_envelope": envelope_json,
        "payload_ref": {
            "payload_ref": descriptor.payload_ref,
            "payload_digest": descriptor.payload_digest,
        },
    }
    row = _append_event(
        transaction,
        event_log,
        event_id=event_id,
        event_type="TOOL_RESULT_ACCEPTED",
        payload=hot_payload,
        payload_ref=descriptor.payload_ref,
        payload_digest=descriptor.payload_digest,
    )
    return (row, hot_payload, descriptor)


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
    locator_refs: tuple[OpaqueEvidenceRef, ...] = (),
    resolution_kind: str | None = None,
    payload_ref: str | None = None,
    payload_digest: str | None = None,
    execution_id: str | None = _EXECUTION_ID,
    include_raw_outcome: bool = True,
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
    :param locator_refs: locator refs。
    :param resolution_kind: 可选 wait resolution kind。
    :param payload_ref: 可选 raw result payload descriptor ref。
    :param payload_digest: 可选 raw result payload digest。
    :param execution_id: accepted result execution id。
    :param include_raw_outcome: 是否写入 canonical raw outcome。
    :returns: appended EventLog row。
    :raises HostDurableError: durable append 失败时由 store 抛出。
    """

    envelope = _accepted_envelope(
        event_id=event_id,
        tool_call_id=tool_call_id,
        request_event_ref=request_event_ref,
        normalized_arguments_digest=normalized_arguments_digest,
        raw_tool_outcome=raw_tool_outcome,
        source_refs=source_refs,
        locator_refs=locator_refs,
        payload_ref=payload_ref,
        payload_digest=payload_digest,
    )
    payload: dict[str, JsonValue] = {
        "tool_call_id": tool_call_id,
        "tool_name": _TOOL_NAME,
        "normalized_arguments_digest": normalized_arguments_digest,
        "accepted_evidence_envelope": accepted_evidence_envelope_to_json_value(envelope),
    }
    if include_raw_outcome:
        payload["raw_tool_outcome"] = raw_tool_outcome
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
        execution_id=execution_id,
    )


def _append_tool_result_with_request(
    transaction: HostTransaction,
    event_log: EventLogStore,
    *,
    event_id: str,
    tool_call_id: str,
    tool_fact_kind: str | None,
    raw_tool_outcome: JsonValue,
    source_refs: tuple[OpaqueEvidenceRef, ...],
    locator_refs: tuple[OpaqueEvidenceRef, ...] = (),
    resolution_kind: str | None = None,
    include_raw_outcome: bool = True,
) -> EventLogRow:
    """追加同源 canonical request atom 与 accepted result。

    :param transaction: Host transaction。
    :param event_log: EventLog store。
    :param event_id: accepted result event id。
    :param tool_call_id: tool call id。
    :param tool_fact_kind: 可选 durable tool fact kind。
    :param raw_tool_outcome: raw outcome JSON。
    :param source_refs: source refs。
    :param locator_refs: locator refs。
    :param resolution_kind: 可选 wait resolution kind。
    :param include_raw_outcome: 是否写入 canonical raw outcome。
    :returns: appended accepted result row。
    :raises HostDurableError: append durable fact 失败时由 store 抛出。
    """

    arguments_json: JsonValue = {"arguments": {"ticker": "MSFT"}}
    arguments_digest = sha256_digest_json(arguments_json)
    request = _append_tool_call_requested(
        transaction,
        event_log,
        event_id=f"event-request-for-{event_id}",
        tool_call_id=tool_call_id,
        arguments_json=arguments_json,
        semantic_query_text=None,
    )
    return _append_tool_result(
        transaction,
        event_log,
        event_id=event_id,
        tool_call_id=tool_call_id,
        request_event_ref=request.event_id,
        normalized_arguments_digest=arguments_digest,
        tool_fact_kind=tool_fact_kind,
        raw_tool_outcome=raw_tool_outcome,
        source_refs=source_refs,
        locator_refs=locator_refs,
        resolution_kind=resolution_kind,
        include_raw_outcome=include_raw_outcome,
    )


def _accepted_envelope(
    *,
    event_id: str,
    tool_call_id: str,
    request_event_ref: str | None,
    normalized_arguments_digest: str,
    raw_tool_outcome: JsonValue,
    source_refs: tuple[OpaqueEvidenceRef, ...],
    locator_refs: tuple[OpaqueEvidenceRef, ...] = (),
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
    :param locator_refs: locator refs。
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
        locator_refs=locator_refs,
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
    execution_id: str | None = _EXECUTION_ID,
) -> EventLogRow:
    """追加测试用 canonical EventLog row。

    :param transaction: Host transaction。
    :param event_log: EventLog store。
    :param event_id: event id。
    :param event_type: event type。
    :param payload: payload JSON。
    :param payload_ref: 可选 payload descriptor ref。
    :param payload_digest: 可选 payload descriptor digest。
    :param execution_id: EventLog execution id。
    :returns: appended EventLog row。
    :raises HostDurableError: durable append 失败时由 store 抛出。
    """

    return event_log.append_event(
        transaction,
        EventLogAppendRequest(
            event_id=event_id,
            event_class=EventClass.CANONICAL_FACT,
            session_id=_SESSION_ID,
            run_id=_RUN_ID,
            attempt_id=_ATTEMPT_ID,
            execution_id=execution_id,
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
        queue_policy=RunQueuePolicy.QUEUE,
        created_at="2026-07-09T00:00:00.000000Z",
        updated_at="2026-07-09T00:00:00.000000Z",
        terminal_at=None,
    )
