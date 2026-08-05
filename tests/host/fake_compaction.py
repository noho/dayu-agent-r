"""Host 测试专用 deterministic vNext context compactor。

本模块位于 tests 包下，只允许测试显式注入一个稳定 compactor。生产代码
不得导入 tests helper；真实生产装配必须显式提供 ``ContextCompactor``。
"""

from __future__ import annotations

from dayu.engine.contracts.structured_output import StructuredOutputCapability

import json
from collections.abc import Mapping

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import runner_role_sequence_digest
from dayu.engine.contracts.messages import (
    AgentMessageRole,
    SystemMessage,
    UserMessage,
)
from dayu.engine.contracts.runner_identity import (
    ProviderRequestIdAvailability,
    SuccessfulRunnerResponseIdentity,
    build_runner_request_identity,
)
from dayu.engine.contracts.runner_spec import (
    ClientCorrelationPolicy,
    RunnerCallOptions,
    RunnerSpec,
)
from dayu.host.compaction import (
    CompactAnswerAnchorV2,
    COMPACT_OUTPUT_SCHEMA_V2,
    CompactCandidateDiagnosticV2,
    CompactorProposal,
    CompactionRequest,
    CompactInputV2,
    CompactCandidateV2,
    ContextCompactor,
    CompactEvidenceFactV2,
    CompactForwardIntentV2,
    CompactRepairFeedbackV2,
    CompactReferenceContinuityV2,
    CompactSessionSummaryV2,
    CompactSourceKindV2,
    CompactCurrentInputV2,
    CompactSourceBoundaryEntryV2,
    CompactAcceptedTruthV2,
    CompactValidationReportV2,
    COMPACT_INPUT_SCHEMA_V2,
)
from dayu.host.compaction_operation import CompactorProposalRunInput
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.context_governance import accept_compact_candidate_v2
from dayu.host.memory import MemoryProjectionPolicy
from dayu.host.run_input import NoToolExecutor

_FAKE_COMPACTION_SYSTEM_PROMPT = "Deterministic fake context compactor."
_FAKE_COMPACTION_PROVIDER = "test-fake-compactor"
_FAKE_COMPACTION_MODEL = "test-fake-compactor-model"


def accepted_truth_for_candidate(
    candidate: CompactCandidateV2,
    *,
    current_input_ref: str,
    source_refs_by_label: Mapping[str, tuple[str, ...]] | None = None,
) -> CompactAcceptedTruthV2:
    """通过 production governance owner 构造测试用 accepted truth。

    :param candidate: strict v2 candidate。
    :param current_input_ref: 不进入 coverage 的 current input ref。
    :param source_refs_by_label: 可选 label→canonical refs 映射。
    :returns: production owner 验收后的 final truth。
    :raises RuntimeError: candidate 未满足 production acceptance contract 时抛出。
    """

    compact_input = compact_input_for_candidate(
        candidate,
        current_input_ref=current_input_ref,
        source_refs_by_label=source_refs_by_label,
    )
    result = accept_compact_candidate_v2(
        compact_input,
        candidate,
        _fake_memory_policy(),
    )
    if isinstance(result, CompactValidationReportV2):
        raise RuntimeError(f"test candidate is not acceptable: {result.to_json()}")
    return result


def compact_input_for_candidate(
    candidate: CompactCandidateV2,
    *,
    current_input_ref: str,
    source_refs_by_label: Mapping[str, tuple[str, ...]] | None = None,
) -> CompactInputV2:
    """从 candidate 业务引用构造严格测试 input boundary。

    :param candidate: strict v2 candidate。
    :param current_input_ref: current input canonical ref。
    :param source_refs_by_label: 可选 label→canonical refs 映射。
    :returns: 与 candidate source-kind contract 一致的 v2 input。
    :raises ValueError: 同一 label 被用于不兼容 source kind 时抛出。
    """

    kinds: dict[str, CompactSourceKindV2] = {}
    order: list[str] = []
    for fact in candidate.evidence_facts:
        _record_candidate_labels(
            kinds,
            order,
            fact.support_labels,
            CompactSourceKindV2.EVIDENCE_MATERIAL,
        )
        _record_candidate_labels(
            kinds,
            order,
            fact.context_labels,
            CompactSourceKindV2.TRACE_MATERIAL,
        )
    for anchor in candidate.answer_anchors:
        _record_candidate_labels(
            kinds,
            order,
            anchor.source_labels,
            CompactSourceKindV2.ANSWER_MATERIAL,
        )
    for intent in candidate.forward_intents:
        _record_flexible_candidate_labels(
            kinds,
            order,
            intent.source_labels,
            default_kind=CompactSourceKindV2.TRACE_MATERIAL,
        )
    for item in candidate.reference_continuity:
        _record_flexible_candidate_labels(
            kinds,
            order,
            item.source_labels,
            default_kind=CompactSourceKindV2.TRACE_MATERIAL,
        )
    if candidate.session_summary is not None:
        _record_flexible_candidate_labels(
            kinds,
            order,
            candidate.session_summary.source_labels,
            default_kind=CompactSourceKindV2.TRACE_MATERIAL,
        )
    for drop in candidate.explicitly_dropped_sources:
        _record_flexible_candidate_labels(
            kinds,
            order,
            (drop.source_label,),
            default_kind=CompactSourceKindV2.TRACE_MATERIAL,
        )
    refs = {} if source_refs_by_label is None else source_refs_by_label
    return CompactInputV2(
        schema=COMPACT_INPUT_SCHEMA_V2,
        current_input=CompactCurrentInputV2(
            source_ref=current_input_ref,
            readable_text="测试当前输入",
        ),
        source_boundary=tuple(
            CompactSourceBoundaryEntryV2(
                source_label=label,
                source_kind=kinds[label],
                source_refs=refs.get(label, (f"source:{label}",)),
                readable_text=f"{label} 的测试业务内容",
            )
            for label in order
        ),
    )


def _record_candidate_labels(
    kinds: dict[str, CompactSourceKindV2],
    order: list[str],
    labels: tuple[str, ...],
    kind: CompactSourceKindV2,
) -> None:
    """记录必须使用单一 kind 的 candidate labels。

    :param kinds: label→kind accumulator。
    :param order: 首次出现顺序 accumulator。
    :param labels: 待记录 labels。
    :param kind: required source kind。
    :returns: ``None``。
    :raises ValueError: label 已绑定不兼容 kind 时抛出。
    """

    for label in labels:
        existing = kinds.get(label)
        if existing is not None and existing is not kind:
            raise ValueError(f"candidate label {label} has incompatible source kinds")
        if existing is None:
            kinds[label] = kind
            order.append(label)


def _record_flexible_candidate_labels(
    kinds: dict[str, CompactSourceKindV2],
    order: list[str],
    labels: tuple[str, ...],
    *,
    default_kind: CompactSourceKindV2,
) -> None:
    """记录允许沿用已确定 kind 的 candidate labels。

    :param kinds: label→kind accumulator。
    :param order: 首次出现顺序 accumulator。
    :param labels: 待记录 labels。
    :param default_kind: label 首次出现时的 kind。
    :returns: ``None``。
    """

    for label in labels:
        if label not in kinds:
            kinds[label] = default_kind
            order.append(label)


def _fake_memory_policy() -> MemoryProjectionPolicy:
    """构造测试 candidate acceptance 的宽松共享 policy。

    :returns: deterministic Memory policy。
    """

    return MemoryProjectionPolicy(
        context_window_size=65536,
        selected_recent_window_item_cap=128,
        selected_recent_window_char_cap=65536,
        selected_recent_window_turn_floor=0,
        fallback_selected_recent_window_item_cap=128,
        fallback_selected_recent_window_char_cap=65536,
        evidence_fact_item_cap=128,
        evidence_fact_char_cap=65536,
        evidence_fact_floor=0,
        session_summary_char_cap=65536,
        answer_anchor_item_cap=128,
        answer_anchor_char_cap=65536,
        forward_intent_item_cap=128,
        forward_intent_char_cap=65536,
        reference_continuity_item_cap=128,
        reference_continuity_char_cap=65536,
        reference_continuity_item_floor=0,
        max_lag_events_for_inline_delta=128,
        max_delta_repair_events=128,
        policy_ref="test-fake-compaction-v2",
    )


class FakeContextCompactor(ContextCompactor):
    """Deterministic vNext context compactor。

    该实现只根据 typed request 构造稳定 vNext candidate，不调用 LLM，不访问
    外部状态，不应作为生产默认 compactor。
    """

    def __init__(self) -> None:
        """初始化单实例内的 synthetic invocation owner。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self._invocation_index = 0
        self._prepared_requests: dict[str, CompactionRequest] = {}

    def prepare_compactor_proposal_run_input(
        self,
        request: CompactionRequest,
        cancellation_token: CancellationToken,
        *,
        compaction_operation_id: str | None,
        compaction_attempt_number: int,
        repair_feedback: CompactRepairFeedbackV2 | None,
    ) -> CompactorProposalRunInput:
        """构造 synthetic compactor invocation 的同源 Engine request。

        :param request: Host 构造的 compaction 请求。
        :param cancellation_token: Host 注入的真实取消 token。
        :param compaction_operation_id: Host compaction operation id。
        :param compaction_attempt_number: operation 内 proposal attempt 序号。
        :param repair_feedback: 前次 semantic validation feedback。
        :returns: 可由 durable manifest recorder 观测的 prepared input。
        :raises ValueError: attempt number 非正数时抛出。
        """

        if compaction_attempt_number <= 0:
            raise ValueError("compaction_attempt_number must be positive")
        operation_identity = "unbound" if compaction_operation_id is None else compaction_operation_id
        compact_input = request.compact_input
        agent_request = _fake_compactor_agent_request(
            request=request,
            cancellation_token=cancellation_token,
            compaction_operation_id=operation_identity,
            compaction_attempt_number=compaction_attempt_number,
        )
        projection: Mapping[str, JsonValue] = {
            "projection_kind": "test_fake_compactor_input",
            "compaction_request_digest": request.digest(),
            "repair_feedback": (None if repair_feedback is None else repair_feedback.to_json()),
        }
        projection_digest = sha256_digest_json(projection)
        self._prepared_requests[agent_request.run_id] = request
        roles = tuple(message.role.value for message in agent_request.messages)
        return CompactorProposalRunInput(
            compact_input=compact_input,
            agent_request=agent_request,
            compaction_request_digest=request.digest(),
            compactor_engine_run_id=agent_request.run_id,
            message_count=len(agent_request.messages),
            role_sequence_digest=runner_role_sequence_digest(roles),
            system_prompt_asset_digest=sha256_digest_json({"prompt": _FAKE_COMPACTION_SYSTEM_PROMPT}),
            user_prompt_template_digest=sha256_digest_json({"prompt": "Synthetic compaction input."}),
            user_prompt_digest=sha256_digest_json(
                {
                    "compaction_request_digest": request.digest(),
                    "repair_feedback": (None if repair_feedback is None else repair_feedback.to_json()),
                }
            ),
            compactor_input_projection=projection,
            compactor_input_projection_digest=projection_digest,
            repair_feedback=repair_feedback,
        )

    async def run_prepared_compactor_proposal(
        self,
        prepared_input: CompactorProposalRunInput,
    ) -> CompactorProposal:
        """执行 prepared synthetic invocation 并绑定同一 AgentRunRequest。

        :param prepared_input: 已由本实例准备的 proposal input。
        :returns: candidate 与 prepared Engine request 同源的 proposal。
        :raises ValueError: prepared input 不属于本实例时抛出。
        :raises RuntimeError: synthetic compact 执行失败时原样抛出。
        """

        request = self._prepared_requests.get(prepared_input.compactor_engine_run_id)
        if request is None:
            raise ValueError("prepared compactor request is unknown")
        proposal = await self.compact(
            request,
            prepared_input.agent_request.cancellation_token,
            repair_feedback=prepared_input.repair_feedback,
        )
        return CompactorProposal(
            candidate=proposal.candidate,
            successful_response_identity=_fake_prepared_response_identity(prepared_input.agent_request),
        )

    async def compact(
        self,
        request: CompactionRequest,
        cancellation_token: CancellationToken,
        *,
        repair_feedback: CompactRepairFeedbackV2 | None,
    ) -> CompactorProposal:
        """生成 deterministic vNext compaction output。

        :param request: Host 构造的 compaction 请求。
        :param cancellation_token: Host 注入的取消 token。
        :param repair_feedback: 前次 validation feedback；fake 不改变 frozen input。
        :returns: 与本次 synthetic invocation 身份配对的 deterministic
            vNext proposal。
        :raises TypeError: ``request`` 类型非法时抛出。
        :raises RuntimeError: token 已取消时抛出。
        """

        if not isinstance(request, CompactionRequest):
            raise TypeError("request must be CompactionRequest")
        del repair_feedback
        compact_input = request.compact_input
        candidate = await FakeConversationCompactorVNext().compact(
            compact_input,
            cancellation_token,
            repair_feedback=None,
        )
        self._invocation_index += 1
        return CompactorProposal(
            candidate=candidate,
            successful_response_identity=_fake_successful_response_identity(
                request=request,
                invocation_index=self._invocation_index,
            ),
        )


def _fake_successful_response_identity(
    *,
    request: CompactionRequest,
    invocation_index: int,
) -> SuccessfulRunnerResponseIdentity:
    """构造当前 fake compactor invocation 的安全成功身份。

    :param request: 当前 synthetic compactor invocation 的 Host request。
    :param invocation_index: 当前 fake 实例内从 1 起的调用序号。
    :returns: 与本次 invocation 唯一绑定的 typed identity。
    :raises ValueError: invocation index 非正数或请求字段非法时抛出。
    """

    if invocation_index <= 0:
        raise ValueError("invocation_index must be positive")
    compactor_run_id = f"test-fake-compactor-{request.digest()}-{invocation_index}"
    return SuccessfulRunnerResponseIdentity(
        effective_provider=_FAKE_COMPACTION_PROVIDER,
        effective_model=_FAKE_COMPACTION_MODEL,
        runner_request_identity=build_runner_request_identity(
            run_id=compactor_run_id,
            attempt_id=None,
            execution_id=None,
            iteration_id=f"{compactor_run_id}-iteration-1",
            iteration_index=0,
            runner_call_index=1,
        ),
        provider_request_id_availability=(ProviderRequestIdAvailability.UNAVAILABLE),
        provider_request_id=None,
    )


def _fake_compactor_agent_request(
    *,
    request: CompactionRequest,
    cancellation_token: CancellationToken,
    compaction_operation_id: str,
    compaction_attempt_number: int,
) -> AgentRunRequest:
    """构造 test fake compactor 的 deterministic AgentRunRequest。

    :param request: 当前 Host compaction request。
    :param cancellation_token: Host 注入的真实取消 token。
    :param compaction_operation_id: 当前 operation id。
    :param compaction_attempt_number: 当前 proposal attempt number。
    :returns: 与 manifest 和 response identity 共用的 Engine request。
    :raises ValueError: AgentRunRequest 字段非法时抛出。
    """

    return AgentRunRequest(
        run_id=(f"test-fake-compactor:{request.run_id}:{compaction_operation_id}:{compaction_attempt_number}"),
        session_id=f"context-compactor:{request.session_id}",
        attempt_id=None,
        execution_id=None,
        messages=(
            SystemMessage(
                role=AgentMessageRole.SYSTEM,
                content=_FAKE_COMPACTION_SYSTEM_PROMPT,
            ),
            UserMessage(
                role=AgentMessageRole.USER,
                content="Synthetic compaction input.",
            ),
        ),
        disable_tools=True,
        runner_spec=RunnerSpec(
            provider=_FAKE_COMPACTION_PROVIDER,
            model=_FAKE_COMPACTION_MODEL,
            endpoint="https://example.invalid",
            api_key_ref="env:TEST_FAKE_COMPACTOR_API_KEY",
            headers={},
            client_correlation_policy=ClientCorrelationPolicy.DISABLED,
            supports_tool_calling=False,
            supports_streaming=False,
            supports_stream_usage=False,
            structured_output_capability=StructuredOutputCapability.NONE,
            default_timeout_seconds=1.0,
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
            fallback_prompt="Synthetic fallback.",
            continuation_prompt="Synthetic continuation.",
        ),
        tool_schemas=(),
        tool_executor=NoToolExecutor(),
        cancellation_token=cancellation_token,
    )


def _fake_prepared_response_identity(
    request: AgentRunRequest,
) -> SuccessfulRunnerResponseIdentity:
    """从同一个 prepared AgentRunRequest 构造成功响应身份。

    :param request: 当前 synthetic provider invocation 的真实 request object。
    :returns: provider request id 明确不可用的 typed identity。
    :raises ValueError: request identity 字段非法时抛出。
    """

    return SuccessfulRunnerResponseIdentity(
        effective_provider=request.runner_spec.provider,
        effective_model=request.runner_spec.model,
        runner_request_identity=build_runner_request_identity(
            run_id=request.run_id,
            attempt_id=request.attempt_id,
            execution_id=request.execution_id,
            iteration_id=f"{request.run_id}:iteration:1",
            iteration_index=0,
            runner_call_index=1,
        ),
        provider_request_id_availability=(ProviderRequestIdAvailability.UNAVAILABLE),
        provider_request_id=None,
    )


class FakeConversationCompactorVNext:
    """测试专用 deterministic vNext context compactor。"""

    async def compact(
        self,
        request: CompactInputV2,
        cancellation_token: CancellationToken,
        *,
        repair_feedback: CompactRepairFeedbackV2 | None,
    ) -> CompactCandidateV2:
        """生成 deterministic vNext compact output。

        :param request: vNext compactor input。
        :param cancellation_token: Host 注入的取消 token。
        :param repair_feedback: 前次 validation feedback；fake 只验证 typed boundary。
        :returns: deterministic vNext compact output。
        :raises TypeError: request 类型非法时抛出。
        :raises RuntimeError: token 已取消时抛出。
        """

        if not isinstance(request, CompactInputV2):
            raise TypeError("request must be CompactInputV2")
        if cancellation_token.is_cancelled():
            raise RuntimeError("compaction cancelled")
        del repair_feedback
        return CompactCandidateV2(
            schema=COMPACT_OUTPUT_SCHEMA_V2,
            session_summary=_fake_session_summary_vnext(request),
            evidence_facts=_fake_fact_candidates_vnext(request),
            answer_anchors=_fake_answer_anchors_vnext(request),
            forward_intents=_fake_forward_intents_vnext(request),
            reference_continuity=_fake_reference_items_vnext(request),
            diagnostics=_fake_diagnostics_vnext(request),
            explicitly_dropped_sources=(),
        )


def fake_compaction_proposal_from_material_json(material_json: Mapping[str, JsonValue]) -> str:
    """从 vNext material JSON 生成 deterministic LLM strict JSON proposal。

    :param material_json: vNext compact input JSON。
    :returns: vNext compact output strict JSON 文本。
    :raises TypeError: material_json 结构非法时抛出。
    """

    boundary = _boundary_items(material_json)
    summary_labels = tuple(item.source_label for item in boundary)
    if len(summary_labels) == 0:
        summary_json: JsonValue = None
    else:
        summary_json = {
            "text": "Deterministic compact summary.",
            "source_labels": list(summary_labels),
        }
    proposal = {
        "schema": COMPACT_OUTPUT_SCHEMA_V2,
        "session_summary": summary_json,
        "evidence_facts": [
            {
                "claim": f"Canonical evidence material: {item.readable_text}",
                "support_labels": [item.source_label],
                "context_labels": [],
            }
            for item in boundary
            if item.source_kind
            in (
                CompactSourceKindV2.EVIDENCE_MATERIAL,
                CompactSourceKindV2.PREVIOUS_EVIDENCE_FACT,
            )
        ],
        "answer_anchors": [
            {
                "title": "Previous answer",
                "detail": item.readable_text,
                "source_labels": [item.source_label],
            }
            for item in boundary
            if item.source_kind
            in (
                CompactSourceKindV2.ANSWER_MATERIAL,
                CompactSourceKindV2.PREVIOUS_ANSWER_ANCHOR,
            )
        ],
        "forward_intents": [],
        "reference_continuity": [],
        "diagnostics": [],
        "explicitly_dropped_sources": [],
    }
    return json.dumps(proposal, ensure_ascii=False, sort_keys=True)


def _fake_session_summary_vnext(request: CompactInputV2) -> CompactSessionSummaryV2 | None:
    """构造 fake vNext session summary。

    :param request: vNext compactor input。
    :returns: session summary；无可引用 material 时返回 ``None``。
    """

    labels = _summary_labels_vnext(request)
    if len(labels) == 0:
        return None
    return CompactSessionSummaryV2(
        text=f"Deterministic compact summary for {request.current_input.readable_text}",
        source_labels=labels,
    )


def _fake_fact_candidates_vnext(
    request: CompactInputV2,
) -> tuple[CompactEvidenceFactV2, ...]:
    """构造 fake vNext fact candidates。

    :param request: vNext compactor input。
    :returns: fact candidate tuple。
    """

    candidates: list[CompactEvidenceFactV2] = []
    for item in request.source_boundary:
        if item.source_kind not in (
            CompactSourceKindV2.EVIDENCE_MATERIAL,
            CompactSourceKindV2.PREVIOUS_EVIDENCE_FACT,
        ):
            continue
        candidates.append(
            CompactEvidenceFactV2(
                claim=f"Canonical evidence material: {item.readable_text}",
                support_labels=(item.source_label,),
                context_labels=(),
            )
        )
    return tuple(candidates)


def _fake_answer_anchors_vnext(
    request: CompactInputV2,
) -> tuple[CompactAnswerAnchorV2, ...]:
    """构造 fake vNext answer anchors。

    :param request: vNext compactor input。
    :returns: answer anchor tuple。
    """

    anchors: list[CompactAnswerAnchorV2] = []
    for item in request.source_boundary:
        if item.source_kind not in (
            CompactSourceKindV2.ANSWER_MATERIAL,
            CompactSourceKindV2.PREVIOUS_ANSWER_ANCHOR,
        ):
            continue
        anchors.append(
            CompactAnswerAnchorV2(
                title="Previous answer",
                detail=item.readable_text,
                source_labels=(item.source_label,),
            )
        )
    return tuple(anchors)


def _fake_forward_intents_vnext(
    request: CompactInputV2,
) -> tuple[CompactForwardIntentV2, ...]:
    """构造 fake vNext forward intents。

    :param request: vNext compactor input。
    :returns: forward intent tuple。
    """

    del request
    return ()


def _fake_reference_items_vnext(
    request: CompactInputV2,
) -> tuple[CompactReferenceContinuityV2, ...]:
    """构造 fake vNext reference continuity items。

    :param request: vNext compactor input。
    :returns: reference continuity tuple。
    """

    del request
    return ()


def _fake_diagnostics_vnext(
    request: CompactInputV2,
) -> tuple[CompactCandidateDiagnosticV2, ...]:
    """构造 fake vNext diagnostics。

    :param request: vNext compactor input。
    :returns: diagnostics tuple。
    """

    del request
    return ()


def _summary_labels_vnext(request: CompactInputV2) -> tuple[str, ...]:
    """返回 fake vNext 可用于 summary 的 labels。

    :param request: vNext compactor input。
    :returns: 本次新材料的 prompt-local labels。
    """

    return request.source_labels


def _continuity_labels_vnext(request: CompactInputV2) -> tuple[str, ...]:
    """返回 fake vNext 可用于 forward / reference continuity 的 labels。

    :param request: vNext compactor input。
    :returns: prompt-local labels。
    """

    return tuple(
        item.source_label
        for item in request.source_boundary
        if item.source_kind
        in (
            CompactSourceKindV2.PREVIOUS_FORWARD_INTENT,
            CompactSourceKindV2.TRACE_MATERIAL,
            CompactSourceKindV2.ANSWER_MATERIAL,
        )
    )


class _BoundaryProposalItem:
    """fake JSON proposal 使用的 typed boundary item。"""

    def __init__(self, *, source_label: str, source_kind: CompactSourceKindV2, readable_text: str) -> None:
        """初始化 boundary item。

        :param source_label: prompt-local source label。
        :param source_kind: source kind。
        :param readable_text: 业务可读文本。
        :returns: ``None``。
        """

        self.source_label = source_label
        self.source_kind = source_kind
        self.readable_text = readable_text


def _boundary_items(material_json: Mapping[str, JsonValue]) -> tuple[_BoundaryProposalItem, ...]:
    """严格读取 v2 source boundary。

    :param material_json: strict v2 compact input JSON。
    :returns: typed boundary items。
    :raises TypeError: 字段结构非法时抛出。
    :raises ValueError: source kind 非闭集值时抛出。
    """

    items: list[_BoundaryProposalItem] = []
    for index, value in enumerate(_json_list(material_json, "source_boundary")):
        data = _json_object(value, field_name=f"source_boundary[{index}]")
        items.append(
            _BoundaryProposalItem(
                source_label=_json_string(data, "source_label"),
                source_kind=CompactSourceKindV2(_json_string(data, "source_kind")),
                readable_text=_json_string(data, "readable_text"),
            )
        )
    return tuple(items)


def _json_list(source: Mapping[str, JsonValue], field_name: str) -> list[JsonValue]:
    """读取 JSON array 字段。

    :param source: JSON object。
    :param field_name: 字段名。
    :returns: JSON array。
    :raises TypeError: 字段不是 array 时抛出。
    """

    value = source.get(field_name)
    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be list")
    return value


def _json_object(value: JsonValue, *, field_name: str) -> Mapping[str, JsonValue]:
    """校验 JSON object。

    :param value: JSON value。
    :param field_name: 字段名。
    :returns: 已完成 key / value 校验的 JSON object。
    :raises TypeError: value 不是 object，或 object 内存在非 JSON 值时抛出。
    """

    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be object")
    return _validated_json_object(value, field_name=field_name)


def _validated_json_object(value: Mapping[str, JsonValue], *, field_name: str) -> Mapping[str, JsonValue]:
    """递归校验 JSON object 的 key 与 value。

    :param value: JSON object。
    :param field_name: 字段名。
    :returns: 复制后的 JSON object。
    :raises TypeError: key 不是字符串，或 value 不是 JSON 值时抛出。
    """

    validated: dict[str, JsonValue] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError(f"{field_name} key must be string")
        validated[key] = _validated_json_value(item, field_name=f"{field_name}.{key}")
    return validated


def _validated_json_value(value: JsonValue, *, field_name: str) -> JsonValue:
    """递归校验 JSON value。

    :param value: JSON value。
    :param field_name: 字段名。
    :returns: 已校验的 JSON value。
    :raises TypeError: value 不是 JSON 标量、数组或对象时抛出。
    """

    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list):
        return [_validated_json_value(item, field_name=f"{field_name}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, Mapping):
        return _validated_json_object(value, field_name=field_name)
    raise TypeError(f"{field_name} must be JSON value")


def _json_string(source: Mapping[str, JsonValue], field_name: str) -> str:
    """读取非空 JSON string 字段。

    :param source: JSON object。
    :param field_name: 字段名。
    :returns: 字符串。
    :raises TypeError: 字段不是 string 时抛出。
    """

    value = source.get(field_name)
    if not isinstance(value, str) or value.strip() == "":
        raise TypeError(f"{field_name} must be non-empty string")
    return value


__all__ = ["FakeContextCompactor", "FakeConversationCompactorVNext", "fake_compaction_proposal_from_material_json"]
