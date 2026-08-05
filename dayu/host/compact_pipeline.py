"""Host compact pipeline 的薄 helper contract。

本模块只收敛 compact source snapshot、request plan、recovery plan、
fallback decision input 与 ordinary raw-tail selection 的纯组合逻辑。
它不读取 EventLog、不写 artifact、不写 EventLog、不创建 Attempt，也不推进
Run / Attempt lifecycle。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Protocol

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.runner_identity import SuccessfulRunnerResponseIdentity
from dayu.engine.contracts.messages import (
    AgentMessage,
    AgentMessageRole,
    AssistantMessage,
    SystemMessage,
    UserMessage,
)
from dayu.host.compact_material import (
    CompactMaterialSourceBoundary,
    PreDispatchCompactMaterialView,
    RunInputMaterialBlock,
    build_compact_material_pack,
    is_turn_group_material_block,
    protected_recent_turn_group_ids_for_material_blocks,
    retained_previous_compacted_view_labels_for_recovery,
    run_input_material_block,
    select_compact_segment,
    selected_material_source_refs,
    selected_material_view_digest,
    selected_block_provenance_for_material_blocks,
    transform_previous_compacted_view_pair_for_recovery,
    turn_group_memberships_for_material_blocks,
)
from dayu.host.evidence import render_accepted_tool_evidence_for_llm
from dayu.host.compact_payload import (
    accepted_evidence_mapping_refs_for_candidate,
    prompt_local_label_mapping_refs,
)
from dayu.host.compaction import (
    CompactMaterialBlock,
    CompactMaterialBlockKind,
    CompactMaterialPack,
    CompactMaterialSection,
    CompactOutputCapsV3,
    PreviousCompactReadableView,
    CompactAcceptedTruthV3,
    CompactSegmentSelection,
    CompactSegmentSelectionScope,
    CompactSegmentTrigger,
    CompactionRequest,
    CompactInputV3,
    validate_previous_compacted_view_pair,
)
from dayu.host.context_budget import BudgetEstimate
from dayu.host.context_fallback import (
    FALLBACK_ACTION_DISPATCH,
    FALLBACK_ACTION_FAIL_CLOSED,
    FALLBACK_POLICY_DECISION_RECENT_WINDOW,
    FALLBACK_POLICY_DECISION_SELECTION_FAILED,
    RecentWindowFallbackBudgetResult,
    RecentWindowFallbackSelection,
    build_recent_window_fallback_selection,
    build_selection_failure_budget_payload,
    build_selection_failure_window_payload,
    estimate_recent_window_fallback_budget,
    fallback_window_digest,
)
from dayu.host.context_policy import ContextBudgetPolicy, ContextCompactionTriggerSource
from dayu.host.context_governance import compact_output_caps_v3_from_memory_policy
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.state import AttemptRow, RunRow
from dayu.host.memory import MemoryProjectionPolicy

_REACTIVE_SINGLE_PASS_REASON = "reactive_single_pass_block"
_REACTIVE_NOT_IN_PASS_REASON = "not_in_pass"
_RECENT_EVIDENCE_PREFIX = "Recent accepted tool evidence:"
_ACCEPTED_TOOL_EVIDENCE_PREFIX = "Accepted tool evidence:"


class MemorySnapshotView(Protocol):
    """ordinary raw-tail selection 所需的 memory view 结构协议。

    :param messages: memory stable layer messages。
    :param selected_recent_source_refs: 已由 memory recent window 表示的 source refs。
    :param selected_recent_content_digests: 已由 memory recent window 表示的内容 digest。
    """

    @property
    def messages(self) -> tuple[AgentMessage, ...]:
        """返回 memory stable layer messages。

        :returns: Agent messages。
        """

        ...

    @property
    def selected_recent_source_refs(self) -> tuple[str, ...]:
        """返回 memory selected recent source refs。

        :returns: source refs。
        """

        ...

    @property
    def selected_recent_content_digests(self) -> tuple[str, ...]:
        """返回 memory selected recent content digests。

        :returns: content digests。
        """

        ...


class CompactPipelineCurrentRunFacts(Protocol):
    """pipeline-owned second-read provider hook 所需的 current facts 协议。"""

    @property
    def run(self) -> RunRow:
        """返回当前 Run row。

        :returns: Run row。
        """

        ...

    @property
    def attempt(self) -> AttemptRow:
        """返回当前 Attempt row。

        :returns: Attempt row。
        """

        ...

    @property
    def user_prompt(self) -> str:
        """返回当前用户输入文本。

        :returns: 用户输入文本。
        """

        ...


class CompactPipelineCompactArtifactView(Protocol):
    """pipeline-owned second-read provider hook 所需的 compact artifact 协议。"""

    @property
    def compact_artifact_ref(self) -> str | None:
        """返回 compact artifact ref。

        :returns: artifact ref；不存在时为 ``None``。
        """

        ...

    @property
    def compact_artifact_digest(self) -> str | None:
        """返回 compact artifact digest。

        :returns: artifact digest；不存在时为 ``None``。
        """

        ...


class CompactPipelineAttemptDispatchSnapshot(Protocol):
    """pipeline-owned second-read provider hook 的 attempt snapshot 协议。"""


@dataclass(frozen=True, slots=True)
class CompactPipelineSourceSnapshot:
    """compact helper 的冻结 source snapshot。

    :param session_id: Session id。
    :param run_id: Run id。
    :param trigger_source: compact 触发来源。
    :param current_input_ref: 当前 USER_INPUT_ACCEPTED event id。
    :param current_input_text: 当前用户输入文本。
    :param input_event_sequence: 当前输入 EventLog sequence。
    :param material_blocks: compact / fallback 候选 material blocks。
    :param previous_compacted_view: latest accepted compacted view。
    :param previous_compacted_readable_view: 与 previous blocks 同源的 typed view。
    :param source_boundary: material source boundary。
    :param material_view_digest: 完整 material view digest。
    :param material_source_refs: 完整 material view 覆盖的 canonical source refs。
    """

    session_id: str
    run_id: str
    trigger_source: ContextCompactionTriggerSource
    current_input_ref: str
    current_input_text: str
    input_event_sequence: int
    material_blocks: tuple[RunInputMaterialBlock, ...]
    previous_compacted_view: tuple[CompactMaterialBlock, ...]
    source_boundary: CompactMaterialSourceBoundary
    material_view_digest: str
    material_source_refs: tuple[str, ...]
    previous_compacted_readable_view: PreviousCompactReadableView | None = None

    def __post_init__(self) -> None:
        """校验 source snapshot 中 previous blocks 与 typed view 的同源 pair。

        :returns: ``None``。
        :raises ValueError: previous pair invariant 不成立时抛出。
        """

        validate_previous_compacted_view_pair(
            self.previous_compacted_view,
            self.previous_compacted_readable_view,
        )


@dataclass(frozen=True, slots=True)
class CompactPipelineRequestPlan:
    """单个 compact request 的纯构造结果。

    :param request: compaction request。
    :param selected_segment: selected segment。
    :param selected_evidence_refs: selected evidence canonical refs。
    :param selected_raw_turn_refs: selected raw user / assistant refs。
    :param selected_source_refs: selected material source refs。
    :param source_snapshot: request 同源 snapshot。
    """

    request: CompactionRequest
    selected_segment: CompactSegmentSelection
    selected_evidence_refs: tuple[str, ...]
    selected_raw_turn_refs: tuple[str, ...]
    selected_source_refs: tuple[str, ...]
    source_snapshot: CompactPipelineSourceSnapshot


@dataclass(frozen=True, slots=True)
class CompactPipelineRecoveryRequestPlan:
    """tier 1/2/3 compact recovery request plan。

    :param tier_name: recovery tier 名称。
    :param request_plan: tier 对应 request plan。
    """

    tier_name: str
    request_plan: CompactPipelineRequestPlan


@dataclass(frozen=True, slots=True)
class CompactPipelinePassQueuePlan:
    """reactive multi-pass request queue 的纯构造结果。

    :param root_request_plan: root request plan。
    :param pass_requests: operation loop 可消费的 pass requests。
    """

    root_request_plan: CompactPipelineRequestPlan
    pass_requests: tuple[CompactionRequest, ...]


@dataclass(frozen=True, slots=True)
class CompactPipelineAcceptedPayloadInput:
    """构造 ``CONTEXT_COMPACTED`` payload 所需的 semantic input。

    :param request: accepted compaction request。
    :param accepted_truth: Context Governance final accepted truth。
    :param budget_after_compact: compact 后预算估算。
    :param accepted_attempt_number: accepted proposal attempt number。
    :param accepted_proposal_manifest_ref: accepted proposal manifest ref。
    :param accepted_proposal_manifest_digest: accepted proposal manifest digest。
    :param successful_response_identity: accepted candidate 对应的实际成功
        Runner call 身份。
    :param prompt_local_label_mapping_refs: prompt-local label mapping refs。
    :param accepted_evidence_mapping_refs: candidate 绑定的 accepted evidence refs。
    """

    request: CompactionRequest
    accepted_truth: CompactAcceptedTruthV3
    budget_after_compact: int
    accepted_attempt_number: int
    accepted_proposal_manifest_ref: str | None
    accepted_proposal_manifest_digest: str | None
    successful_response_identity: SuccessfulRunnerResponseIdentity
    prompt_local_label_mapping_refs: tuple[str, ...]
    accepted_evidence_mapping_refs: tuple[str, ...]

    @property
    def source_boundary_refs(self) -> tuple[str, ...]:
        """从 accepted truth 派生 current+covered canonical refs。

        :returns: 与 artifact/event 相同的 source boundary refs。
        """

        return (
            self.accepted_truth.current_input_ref,
            *self.accepted_truth.covered_source_refs,
        )


@dataclass(frozen=True, slots=True)
class CompactPipelineFailedPayloadInput:
    """构造 ``CONTEXT_COMPACTION_FAILED`` payload 所需的 semantic input。

    :param operation_id: compaction operation id。
    :param failure_reason: failure reason。
    :param attempt_count: operation attempt count。
    :param retry_repair_budget_exhausted: repair budget 是否耗尽。
    :param budget_after_attempted_compact: attempted compact 后预算；未知时为 ``None``。
    :param fallback_policy_decision: fallback policy decision。
    :param fallback_input_window: fallback window payload。
    :param fallback_input_digest: fallback window digest。
    :param fallback_budget_result: fallback budget payload。
    :param fallback_action: fallback action。
    """

    operation_id: str
    failure_reason: str
    attempt_count: int
    retry_repair_budget_exhausted: bool
    budget_after_attempted_compact: int | None
    fallback_policy_decision: str | None
    fallback_input_window: Mapping[str, JsonValue] | None
    fallback_input_digest: str | None
    fallback_budget_result: Mapping[str, JsonValue] | None
    fallback_action: str


@dataclass(frozen=True, slots=True)
class CompactPipelineFallbackSelectedMaterialHandoff:
    """fallback branch 的 selected material handoff。

    :param selected_block_ids: selected material block ids。
    :param material_blocks: selected material blocks。
    :param source_refs: selected source refs。
    :param fallback_input_digest: fallback window digest。
    :param selected_material_view_digest: selected material view digest。
    :param selected_recent_window_turn_floor: selected recent turn floor。
    :param selected_raw_turn_count: selected raw turn block count。
    """

    selected_block_ids: tuple[str, ...]
    material_blocks: tuple[RunInputMaterialBlock, ...]
    source_refs: tuple[str, ...]
    fallback_input_digest: str
    selected_material_view_digest: str
    selected_recent_window_turn_floor: int
    selected_raw_turn_count: int


@dataclass(frozen=True, slots=True)
class CompactPipelineFallbackDecisionInput:
    """shared fallback decision input。

    :param selection: recent-window fallback selection；selection 失败时为 ``None``。
    :param budget_result: fallback budget；selection 失败时为 ``None``。
    :param failed_payload_input: failed payload semantic input。
    :param fallback_handoff: selected material handoff；selection 失败时为 ``None``。
    :param action_hint: caller 后续动作提示。
    """

    selection: RecentWindowFallbackSelection | None
    budget_result: RecentWindowFallbackBudgetResult | None
    failed_payload_input: CompactPipelineFailedPayloadInput
    fallback_handoff: CompactPipelineFallbackSelectedMaterialHandoff | None
    action_hint: str


@dataclass(frozen=True, slots=True)
class CompactPipelineOrdinaryRawTailHandoff:
    """ordinary post-compaction raw-tail provider 的 handoff。

    :param messages: 可注入 ordinary RunInput 的 raw-tail messages。
    :param material_blocks: selected raw-tail material blocks。
    :param source_refs: selected source refs。
    :param material_view_digest: selected material view digest。
    :param selected_recent_window_turn_floor: selected recent turn floor。
    """

    messages: tuple[AgentMessage, ...]
    material_blocks: tuple[RunInputMaterialBlock, ...]
    source_refs: tuple[str, ...]
    material_view_digest: str
    selected_recent_window_turn_floor: int


class CompactPipelineProtectedRawTailProvider(Protocol):
    """pipeline-owned audited second-read raw-tail provider hook。"""

    def load_ordinary_raw_tail(
        self,
        snapshot: CompactPipelineAttemptDispatchSnapshot,
        current_facts: CompactPipelineCurrentRunFacts,
        memory: MemorySnapshotView,
        compact: CompactPipelineCompactArtifactView,
    ) -> CompactPipelineOrdinaryRawTailHandoff:
        """读取 ordinary raw-tail handoff。

        :param snapshot: Attempt dispatch snapshot；具体类型由 RunInput adapter 拥有。
        :param current_facts: 当前 Run facts。
        :param memory: memory snapshot view。
        :param compact: compact artifact view。
        :returns: ordinary raw-tail handoff。
        """

        ...


def compact_pipeline_source_snapshot_from_pre_dispatch_view(
    *,
    trigger_source: ContextCompactionTriggerSource,
    run: RunRow,
    material_view: PreDispatchCompactMaterialView,
) -> CompactPipelineSourceSnapshot:
    """从 frozen run facts 与 material view 构造 source snapshot。

    :param trigger_source: compact 触发来源。
    :param run: caller 已冻结的 Run durable row。
    :param material_view: 同源 pre-dispatch material view。
    :returns: compact pipeline source snapshot。
    :raises TypeError: 参数类型非法时抛出。
    :raises ValueError: input cursor 与 material boundary 不一致时抛出。
    """

    if not isinstance(trigger_source, ContextCompactionTriggerSource):
        raise TypeError("trigger_source must be ContextCompactionTriggerSource")
    if not isinstance(run, RunRow):
        raise TypeError("run must be RunRow")
    if not isinstance(material_view, PreDispatchCompactMaterialView):
        raise TypeError("material_view must be PreDispatchCompactMaterialView")
    if run.input_event_sequence != material_view.source_boundary.current_input_event_sequence:
        raise ValueError("run input event sequence does not match material boundary")
    block_ids = tuple(block.block_id for block in material_view.material_blocks)
    return CompactPipelineSourceSnapshot(
        session_id=run.session_id,
        run_id=run.run_id,
        trigger_source=trigger_source,
        current_input_ref=run.input_event_id,
        current_input_text=material_view.current_input_text,
        input_event_sequence=run.input_event_sequence,
        material_blocks=material_view.material_blocks,
        previous_compacted_view=material_view.previous_compacted_view,
        previous_compacted_readable_view=material_view.previous_compacted_readable_view,
        source_boundary=material_view.source_boundary,
        material_view_digest=selected_material_view_digest(material_view.material_blocks),
        material_source_refs=selected_material_source_refs(
            material_blocks=material_view.material_blocks,
            selected_block_ids=block_ids,
        ),
    )


def build_normal_compact_request_plan(
    *,
    source_snapshot: CompactPipelineSourceSnapshot,
    selection_policy_digest: str,
    memory_policy: MemoryProjectionPolicy,
    budget_before_compact: BudgetEstimate,
    selected_recent_window_turn_floor: int,
    attempt_id: str | None = None,
    execution_id: str | None = None,
) -> CompactPipelineRequestPlan:
    """构造 normal compact request plan。

    :param source_snapshot: compact source snapshot。
    :param selection_policy_digest: memory selection policy digest。
    :param memory_policy: 产生 v3 output caps 的同一 Memory policy。
    :param budget_before_compact: compact 前预算估算。
    :param selected_recent_window_turn_floor: protected recent turn floor。
    :param attempt_id: reactive attempt id；proactive 为 ``None``。
    :param execution_id: reactive execution id；proactive 为 ``None``。
    :returns: compact request plan。
    """

    segment = select_compact_segment(
        trigger_source=_segment_trigger(source_snapshot.trigger_source),
        input_cursor=source_snapshot.input_event_sequence,
        memory_snapshot_cursor=None,
        policy_digest=selection_policy_digest,
        material_blocks=source_snapshot.material_blocks,
        selected_recent_window_turn_floor=selected_recent_window_turn_floor,
    )
    return _request_plan_from_segment(
        source_snapshot=source_snapshot,
        selected_segment=segment,
        previous_compacted_view=source_snapshot.previous_compacted_view,
        previous_compacted_readable_view=source_snapshot.previous_compacted_readable_view,
        budget_before_compact=budget_before_compact,
        attempt_id=attempt_id,
        execution_id=execution_id,
        output_caps=compact_output_caps_v3_from_memory_policy(memory_policy),
    )


def build_tier_recovery_request_plans(
    *,
    source_snapshot: CompactPipelineSourceSnapshot,
    root_request_plan: CompactPipelineRequestPlan,
    memory_policy: MemoryProjectionPolicy,
) -> tuple[CompactPipelineRecoveryRequestPlan, ...]:
    """构造 tier 1/2/3 compact recovery request plans。

    :param source_snapshot: compact source snapshot。
    :param root_request_plan: root request plan。
    :param memory_policy: memory projection policy。
    :returns: recovery request plans。
    :raises TypeError: memory policy 类型非法时抛出。
    """

    if not isinstance(memory_policy, MemoryProjectionPolicy):
        raise TypeError("memory_policy must be MemoryProjectionPolicy")
    bounded_selection = select_compact_segment(
        trigger_source=_segment_trigger(source_snapshot.trigger_source),
        input_cursor=source_snapshot.input_event_sequence,
        memory_snapshot_cursor=None,
        policy_digest=root_request_plan.selected_segment.policy_digest,
        material_blocks=source_snapshot.material_blocks,
        selected_recent_window_turn_floor=(memory_policy.selected_recent_window_turn_floor),
        max_selected_size_units=memory_policy.fallback_selected_recent_window_char_cap,
        max_selected_item_count=memory_policy.fallback_selected_recent_window_item_cap,
    )
    plans: list[CompactPipelineRecoveryRequestPlan] = [
        CompactPipelineRecoveryRequestPlan(
            tier_name="tier_1_fallback_caps",
            request_plan=_request_plan_from_segment(
                source_snapshot=source_snapshot,
                selected_segment=bounded_selection,
                previous_compacted_view=source_snapshot.previous_compacted_view,
                previous_compacted_readable_view=source_snapshot.previous_compacted_readable_view,
                budget_before_compact=root_request_plan.request.budget_before_compact,
                attempt_id=root_request_plan.request.attempt_id,
                execution_id=root_request_plan.request.execution_id,
                output_caps=root_request_plan.request.output_caps,
            ),
        )
    ]
    retained_labels = retained_previous_compacted_view_labels_for_recovery(source_snapshot.previous_compacted_view)
    degraded_blocks, degraded_readable_view = transform_previous_compacted_view_pair_for_recovery(
        blocks=source_snapshot.previous_compacted_view,
        readable_view=source_snapshot.previous_compacted_readable_view,
        retained_block_labels=retained_labels,
    )
    if len(degraded_blocks) > 0 and degraded_blocks != source_snapshot.previous_compacted_view:
        plans.append(
            CompactPipelineRecoveryRequestPlan(
                tier_name="tier_2_section_degrade",
                request_plan=_request_plan_from_segment(
                    source_snapshot=source_snapshot,
                    selected_segment=bounded_selection,
                    previous_compacted_view=degraded_blocks,
                    previous_compacted_readable_view=degraded_readable_view,
                    budget_before_compact=(root_request_plan.request.budget_before_compact),
                    attempt_id=root_request_plan.request.attempt_id,
                    execution_id=root_request_plan.request.execution_id,
                    output_caps=root_request_plan.request.output_caps,
                ),
            )
        )
    empty_previous_blocks, empty_previous_readable_view = transform_previous_compacted_view_pair_for_recovery(
        blocks=source_snapshot.previous_compacted_view,
        readable_view=source_snapshot.previous_compacted_readable_view,
        retained_block_labels=frozenset(),
    )
    plans.append(
        CompactPipelineRecoveryRequestPlan(
            tier_name="tier_3_delta_only",
            request_plan=_request_plan_from_segment(
                source_snapshot=source_snapshot,
                selected_segment=bounded_selection,
                previous_compacted_view=empty_previous_blocks,
                previous_compacted_readable_view=empty_previous_readable_view,
                budget_before_compact=root_request_plan.request.budget_before_compact,
                attempt_id=root_request_plan.request.attempt_id,
                execution_id=root_request_plan.request.execution_id,
                output_caps=root_request_plan.request.output_caps,
            ),
        )
    )
    return tuple(plans)


def build_reactive_pass_queue_plan(
    *,
    source_snapshot: CompactPipelineSourceSnapshot,
    root_request_plan: CompactPipelineRequestPlan,
) -> CompactPipelinePassQueuePlan:
    """构造 reactive multi-pass request queue plan。

    :param source_snapshot: compact source snapshot。
    :param root_request_plan: root request plan。
    :returns: pass queue plan；selected block 不超过一个时 queue 为空。
    """

    selected = root_request_plan.selected_segment.selected_block_ids
    if len(selected) <= 1:
        return CompactPipelinePassQueuePlan(
            root_request_plan=root_request_plan,
            pass_requests=(),
        )
    empty_previous_blocks, empty_previous_readable_view = transform_previous_compacted_view_pair_for_recovery(
        blocks=source_snapshot.previous_compacted_view,
        readable_view=source_snapshot.previous_compacted_readable_view,
        retained_block_labels=frozenset(),
    )
    requests: list[CompactionRequest] = []
    for index, block_id in enumerate(selected):
        segment = _single_block_segment_selection(
            root_request=root_request_plan.request,
            block_id=block_id,
            material_blocks=source_snapshot.material_blocks,
        )
        pass_request = _request_plan_from_segment(
            source_snapshot=source_snapshot,
            selected_segment=segment,
            previous_compacted_view=(source_snapshot.previous_compacted_view if index == 0 else empty_previous_blocks),
            previous_compacted_readable_view=(
                source_snapshot.previous_compacted_readable_view if index == 0 else empty_previous_readable_view
            ),
            budget_before_compact=(root_request_plan.request.budget_before_compact),
            attempt_id=root_request_plan.request.attempt_id,
            execution_id=root_request_plan.request.execution_id,
            output_caps=root_request_plan.request.output_caps,
        ).request
        requests.append(
            _bind_reactive_pass_to_root_labels(
                request=pass_request,
                root_input=root_request_plan.request.compact_input,
            )
        )
    return CompactPipelinePassQueuePlan(
        root_request_plan=root_request_plan,
        pass_requests=tuple(requests),
    )


def _bind_reactive_pass_to_root_labels(
    *,
    request: CompactionRequest,
    root_input: CompactInputV3,
) -> CompactionRequest:
    """把单 pass 的局部编号重绑定到 immutable root labels。

    :param request: 单 block pass request。
    :param root_input: operation root strict input。
    :returns: source identity 不变、labels 与 root 一致的 pass request。
    :raises ValueError: pass source 无法唯一绑定到 root 时抛出。
    """

    pass_input = request.compact_input
    root_by_identity = {
        (entry.source_kind, entry.source_refs, entry.readable_text): entry for entry in root_input.source_boundary
    }
    label_mapping: dict[str, str] = {}
    for entry in pass_input.source_boundary:
        root_entry = root_by_identity.get((entry.source_kind, entry.source_refs, entry.readable_text))
        if root_entry is None:
            raise ValueError("reactive pass source is not present in root boundary")
        label_mapping[entry.source_label] = root_entry.source_label
    material_pack = request.material_pack
    rebound_pack = replace(
        material_pack,
        previous_compacted_view=tuple(
            replace(
                block,
                block_label=label_mapping[block.block_label],
            )
            for block in material_pack.previous_compacted_view
        ),
        trace_material=tuple(
            replace(
                block,
                block_label=label_mapping[block.block_label],
            )
            for block in material_pack.trace_material
        ),
        evidence_material=tuple(
            replace(
                block,
                evidence_label=label_mapping[block.evidence_label],
            )
            for block in material_pack.evidence_material
        ),
        answer_material=tuple(
            replace(
                block,
                block_label=label_mapping[block.block_label],
            )
            for block in material_pack.answer_material
        ),
        provenance_map={
            label_mapping.get(label, label): replace(
                provenance,
                label=label_mapping.get(label, label),
            )
            for label, provenance in material_pack.provenance_map.items()
        },
    )
    rebound_request = replace(request, material_pack=rebound_pack)
    rebound_input = rebound_request.compact_input
    expected_entries = tuple(
        root_by_identity[(entry.source_kind, entry.source_refs, entry.readable_text)]
        for entry in pass_input.source_boundary
    )
    if rebound_input.source_boundary != expected_entries:
        raise ValueError("reactive pass root label binding is inconsistent")
    return rebound_request


def build_compacted_payload_input(
    *,
    request: CompactionRequest,
    accepted_truth: CompactAcceptedTruthV3,
    budget_after_compact: int,
    accepted_attempt_number: int,
    accepted_proposal_manifest_ref: str | None,
    accepted_proposal_manifest_digest: str | None,
    successful_response_identity: SuccessfulRunnerResponseIdentity,
) -> CompactPipelineAcceptedPayloadInput:
    """构造 accepted compact payload semantic input。

    :param request: accepted compaction request。
    :param accepted_truth: Context Governance final accepted truth。
    :param budget_after_compact: compact 后预算估算。
    :param accepted_attempt_number: accepted proposal attempt number。
    :param accepted_proposal_manifest_ref: accepted proposal manifest ref。
    :param accepted_proposal_manifest_digest: accepted proposal manifest digest。
    :param successful_response_identity: accepted candidate 对应的实际成功
        Runner call 身份。
    :returns: accepted payload input。
    """

    accepted_truth.validate_input_binding(request.compact_input)
    return CompactPipelineAcceptedPayloadInput(
        request=request,
        accepted_truth=accepted_truth,
        budget_after_compact=budget_after_compact,
        accepted_attempt_number=accepted_attempt_number,
        accepted_proposal_manifest_ref=accepted_proposal_manifest_ref,
        accepted_proposal_manifest_digest=accepted_proposal_manifest_digest,
        successful_response_identity=successful_response_identity,
        prompt_local_label_mapping_refs=prompt_local_label_mapping_refs(request),
        accepted_evidence_mapping_refs=accepted_evidence_mapping_refs_for_candidate(
            request,
            accepted_truth.candidate,
        ),
    )


def build_fallback_decision_input(
    *,
    source_snapshot: CompactPipelineSourceSnapshot,
    context_policy: ContextBudgetPolicy,
    memory_policy: MemoryProjectionPolicy,
    operation_id: str,
    failure_reason: str,
    attempt_count: int,
    retry_repair_budget_exhausted: bool,
    budget_after_attempted_compact: int | None,
) -> CompactPipelineFallbackDecisionInput:
    """构造 fallback selection、budget 与 failed payload input。

    :param source_snapshot: compact source snapshot。
    :param context_policy: context budget policy。
    :param memory_policy: memory projection policy。
    :param operation_id: compaction operation id。
    :param failure_reason: compact failure reason。
    :param attempt_count: operation attempt count。
    :param retry_repair_budget_exhausted: repair budget 是否耗尽。
    :param budget_after_attempted_compact: attempted compact 后预算。
    :returns: fallback decision input。
    """

    try:
        selection = build_recent_window_fallback_selection(
            policy=context_policy,
            memory_policy=memory_policy,
            session_id=source_snapshot.session_id,
            run_id=source_snapshot.run_id,
            material_blocks=_fallback_material_blocks(source_snapshot),
            current_input_ref=source_snapshot.current_input_ref,
            input_cursor=source_snapshot.input_event_sequence,
            selected_recent_window_turn_floor=(memory_policy.selected_recent_window_turn_floor),
            trigger_source=source_snapshot.trigger_source,
        )
        budget = estimate_recent_window_fallback_budget(
            policy=context_policy,
            session_id=source_snapshot.session_id,
            run_id=source_snapshot.run_id,
            selection_blocks=selection.selected_blocks,
            current_input_ref=source_snapshot.current_input_ref,
        )
    except Exception as error:
        window = build_selection_failure_window_payload(
            current_input_ref=source_snapshot.current_input_ref,
            trigger_source=source_snapshot.trigger_source,
            policy_ref=context_policy.policy_ref,
            input_cursor=source_snapshot.input_event_sequence,
            failure_reason=_fallback_selection_failure_reason(
                error,
                compact_failure_reason=failure_reason,
            ),
        )
        failed = CompactPipelineFailedPayloadInput(
            operation_id=operation_id,
            failure_reason=failure_reason,
            attempt_count=attempt_count,
            retry_repair_budget_exhausted=retry_repair_budget_exhausted,
            budget_after_attempted_compact=budget_after_attempted_compact,
            fallback_policy_decision=FALLBACK_POLICY_DECISION_SELECTION_FAILED,
            fallback_input_window=window,
            fallback_input_digest=fallback_window_digest(window),
            fallback_budget_result=build_selection_failure_budget_payload(policy_ref=context_policy.policy_ref),
            fallback_action=FALLBACK_ACTION_FAIL_CLOSED,
        )
        return CompactPipelineFallbackDecisionInput(
            selection=None,
            budget_result=None,
            failed_payload_input=failed,
            fallback_handoff=None,
            action_hint=FALLBACK_ACTION_FAIL_CLOSED,
        )
    action = FALLBACK_ACTION_DISPATCH if budget.hard_budget_passed else FALLBACK_ACTION_FAIL_CLOSED
    window = selection.to_window_payload()
    failed = CompactPipelineFailedPayloadInput(
        operation_id=operation_id,
        failure_reason=failure_reason,
        attempt_count=attempt_count,
        retry_repair_budget_exhausted=retry_repair_budget_exhausted,
        budget_after_attempted_compact=budget_after_attempted_compact,
        fallback_policy_decision=FALLBACK_POLICY_DECISION_RECENT_WINDOW,
        fallback_input_window=window,
        fallback_input_digest=selection.digest,
        fallback_budget_result=budget.to_payload(),
        fallback_action=action,
    )
    return CompactPipelineFallbackDecisionInput(
        selection=selection,
        budget_result=budget,
        failed_payload_input=failed,
        fallback_handoff=CompactPipelineFallbackSelectedMaterialHandoff(
            selected_block_ids=selection.selected_block_ids,
            material_blocks=selection.selected_blocks,
            source_refs=selection.source_refs,
            fallback_input_digest=selection.digest,
            selected_material_view_digest=selected_material_view_digest(selection.selected_blocks),
            selected_recent_window_turn_floor=(selection.selected_recent_window_turn_floor),
            selected_raw_turn_count=_raw_turn_count(selection.selected_blocks),
        ),
        action_hint=action,
    )


def select_ordinary_protected_raw_tail(
    *,
    source_snapshot: CompactPipelineSourceSnapshot,
    selected_recent_window_turn_floor: int,
    memory: MemorySnapshotView,
) -> CompactPipelineOrdinaryRawTailHandoff:
    """选择 ordinary post-compaction protected raw tail。

    :param source_snapshot: compact source snapshot。
    :param selected_recent_window_turn_floor: selected recent turn floor。
    :param memory: memory provider view，用于 selected recent 去重。
    :returns: ordinary raw-tail handoff。
    :raises HostDurableError: protected group selection 失败时抛出。
    """

    if selected_recent_window_turn_floor == 0:
        return CompactPipelineOrdinaryRawTailHandoff(
            messages=(),
            material_blocks=(),
            source_refs=(),
            material_view_digest=selected_material_view_digest(()),
            selected_recent_window_turn_floor=0,
        )
    try:
        protected_group_ids = protected_recent_turn_group_ids_for_material_blocks(
            source_snapshot.material_blocks,
            selected_recent_window_turn_floor=selected_recent_window_turn_floor,
        )
    except ValueError as exc:
        raise HostDurableError("protected recent raw tail group selection failed") from exc
    selected = tuple(
        block
        for block in source_snapshot.material_blocks
        if block.turn_group_id in protected_group_ids
        and is_turn_group_material_block(block)
        and not _raw_tail_block_represented_by_memory(block, memory)
    )
    return CompactPipelineOrdinaryRawTailHandoff(
        messages=tuple(_message_from_material_block(block) for block in selected),
        material_blocks=selected,
        source_refs=_source_refs_for_blocks(selected),
        material_view_digest=selected_material_view_digest(selected),
        selected_recent_window_turn_floor=selected_recent_window_turn_floor,
    )


def _request_plan_from_segment(
    *,
    source_snapshot: CompactPipelineSourceSnapshot,
    selected_segment: CompactSegmentSelection,
    previous_compacted_view: tuple[CompactMaterialBlock, ...],
    previous_compacted_readable_view: PreviousCompactReadableView | None,
    budget_before_compact: BudgetEstimate,
    attempt_id: str | None,
    execution_id: str | None,
    output_caps: CompactOutputCapsV3,
) -> CompactPipelineRequestPlan:
    """按指定 segment 构造 request plan。

    :param source_snapshot: compact source snapshot。
    :param selected_segment: selected segment。
    :param previous_compacted_view: request 使用的 previous compacted view。
    :param previous_compacted_readable_view: 与 previous blocks 同源的 typed view。
    :param budget_before_compact: compact 前预算。
    :param attempt_id: reactive attempt id。
    :param execution_id: reactive execution id。
    :param output_caps: 同一 Memory policy 的 immutable output caps DTO。
    :returns: request plan。
    """

    _validate_segment_against_source_snapshot(
        source_snapshot=source_snapshot,
        selected_segment=selected_segment,
    )
    material_pack = build_compact_material_pack(
        selected_segment=selected_segment,
        material_blocks=source_snapshot.material_blocks,
        memory_snapshot=None,
        inline_delta_repair_view=None,
        current_input_ref=source_snapshot.current_input_ref,
        current_input_text=source_snapshot.current_input_text,
        previous_compacted_view=previous_compacted_view,
        previous_compacted_readable_view=previous_compacted_readable_view,
    )
    _validate_selected_pack_current_input_separation(material_pack)
    selected_evidence_refs = _selected_evidence_refs(
        material_blocks=source_snapshot.material_blocks,
        selected_block_ids=selected_segment.selected_block_ids,
    )
    selected_raw_turn_refs = _selected_raw_turn_refs(
        material_blocks=source_snapshot.material_blocks,
        selected_block_ids=selected_segment.selected_block_ids,
    )
    selected_source_refs = selected_material_source_refs(
        material_blocks=source_snapshot.material_blocks,
        selected_block_ids=selected_segment.selected_block_ids,
    )
    request = CompactionRequest(
        trigger_source=source_snapshot.trigger_source,
        session_id=source_snapshot.session_id,
        run_id=source_snapshot.run_id,
        attempt_id=attempt_id,
        execution_id=execution_id,
        memory_snapshot_cursor=None,
        output_caps=output_caps,
        material_pack=material_pack,
        segment_selection=selected_segment,
        evidence_backed_fact_refs=selected_evidence_refs,
        recent_raw_turn_refs=_dedupe_texts((source_snapshot.current_input_ref, *selected_raw_turn_refs)),
        older_raw_turn_refs=selected_source_refs,
        existing_episode_summary_refs=(),
        budget_before_compact=budget_before_compact,
    )
    return CompactPipelineRequestPlan(
        request=request,
        selected_segment=selected_segment,
        selected_evidence_refs=selected_evidence_refs,
        selected_raw_turn_refs=selected_raw_turn_refs,
        selected_source_refs=selected_source_refs,
        source_snapshot=source_snapshot,
    )


def _validate_segment_against_source_snapshot(
    *,
    source_snapshot: CompactPipelineSourceSnapshot,
    selected_segment: CompactSegmentSelection,
) -> None:
    """验证 selection 与同一 frozen source snapshot 的 block/group truth 同源。

    :param source_snapshot: immutable compact source snapshot。
    :param selected_segment: 待构造 request 的 root 或 transient selection。
    :returns: ``None``。
    :raises ValueError: block partition、group proof 或 transient root binding 不一致时抛出。
    """

    snapshot_block_ids = tuple(block.block_id for block in source_snapshot.material_blocks)
    known_ids = set(snapshot_block_ids)
    selected_ids = set(selected_segment.selected_block_ids)
    excluded_ids = set(selected_segment.excluded_reason_codes)
    if not selected_ids.issubset(known_ids) or not excluded_ids.issubset(known_ids):
        raise ValueError("segment selection contains block outside source snapshot")
    expected_memberships = turn_group_memberships_for_material_blocks(
        source_snapshot.material_blocks,
        memory_snapshot_cursor=selected_segment.memory_snapshot_cursor,
    )
    if selected_segment.turn_group_memberships != expected_memberships:
        raise ValueError("segment turn-group membership does not match source snapshot")
    expected_provenance = selected_block_provenance_for_material_blocks(
        source_snapshot.material_blocks,
        selected_block_ids=selected_segment.selected_block_ids,
    )
    if selected_segment.selected_block_provenance != expected_provenance:
        raise ValueError("segment selected block provenance does not match source snapshot")
    if selected_segment.scope is CompactSegmentSelectionScope.ROOT:
        if selected_ids.union(excluded_ids) != known_ids:
            raise ValueError("root segment must exactly partition source snapshot blocks")
        return
    if selected_segment.root_selection_digest is None:
        raise ValueError("transient segment must bind root selection digest")


def _validate_selected_pack_current_input_separation(
    material_pack: CompactMaterialPack,
) -> None:
    """拒绝 selected history/evidence 与 current anchor 共享 canonical ref。

    :param material_pack: 已由 selected source blocks 构造的最终 pack。
    :returns: ``None``。
    :raises ValueError: selected pack 与 current input canonical ref 重叠时抛出。
    """

    current_refs = set(material_pack.current_input_anchor.canonical_source_refs)
    selected_refs = (
        *(block.canonical_source_refs for block in material_pack.trace_material),
        *(block.canonical_source_refs for block in material_pack.evidence_material),
        *(block.canonical_source_refs for block in material_pack.answer_material),
    )
    if any(current_refs.intersection(refs) for refs in selected_refs):
        raise ValueError("selected compact material overlaps current input canonical ref")


def _segment_trigger(
    trigger_source: ContextCompactionTriggerSource,
) -> CompactSegmentTrigger:
    """把 context trigger 映射为 compact segment trigger。

    :param trigger_source: context compact trigger。
    :returns: compact segment trigger。
    """

    if trigger_source is ContextCompactionTriggerSource.REACTIVE:
        return CompactSegmentTrigger.REACTIVE
    return CompactSegmentTrigger.PROACTIVE


def _single_block_segment_selection(
    *,
    root_request: CompactionRequest,
    block_id: str,
    material_blocks: tuple[RunInputMaterialBlock, ...],
) -> CompactSegmentSelection:
    """构造 reactive single-block pass selection。

    :param root_request: root compaction request。
    :param block_id: pass 选中的 block id。
    :param material_blocks: 同源 material blocks。
    :returns: single-block selection。
    :raises ValueError: block id 不存在时抛出。
    """

    known = {block.block_id for block in material_blocks}
    if block_id not in known:
        raise ValueError("reactive pass block_id is not in material list")
    root_provenance = tuple(
        provenance
        for provenance in root_request.segment_selection.selected_block_provenance
        if provenance.block_id == block_id
    )
    if len(root_provenance) != 1:
        raise ValueError("reactive pass block provenance is not present exactly once in root")
    excluded = {block.block_id: _REACTIVE_NOT_IN_PASS_REASON for block in material_blocks if block.block_id != block_id}
    digest_input = {
        "scope": CompactSegmentSelectionScope.TRANSIENT.value,
        "turn_group_memberships": [
            membership.to_json() for membership in root_request.segment_selection.turn_group_memberships
        ],
        "selected_block_provenance": [root_provenance[0].to_json()],
        "root_selection_digest": root_request.segment_selection.selection_digest,
        "selected_block_ids": [block_id],
        "excluded_protected_ids": [],
        "trigger_source": CompactSegmentTrigger.REACTIVE.value,
        "input_cursor": root_request.segment_selection.input_cursor,
        "memory_snapshot_cursor": root_request.segment_selection.memory_snapshot_cursor,
        "policy_digest": root_request.segment_selection.policy_digest,
        "deterministic_reason_codes": [_REACTIVE_SINGLE_PASS_REASON],
        "excluded_reason_codes": excluded,
    }
    return CompactSegmentSelection(
        scope=CompactSegmentSelectionScope.TRANSIENT,
        turn_group_memberships=(root_request.segment_selection.turn_group_memberships),
        selected_block_provenance=root_provenance,
        root_selection_digest=root_request.segment_selection.selection_digest,
        selected_block_ids=(block_id,),
        excluded_protected_ids=(),
        trigger_source=CompactSegmentTrigger.REACTIVE,
        input_cursor=root_request.segment_selection.input_cursor,
        memory_snapshot_cursor=root_request.segment_selection.memory_snapshot_cursor,
        policy_digest=root_request.segment_selection.policy_digest,
        deterministic_reason_codes=(_REACTIVE_SINGLE_PASS_REASON,),
        selection_digest=sha256_digest_json(digest_input),
        excluded_reason_codes=excluded,
    )


def _fallback_material_blocks(
    source_snapshot: CompactPipelineSourceSnapshot,
) -> tuple[RunInputMaterialBlock, ...]:
    """构造 fallback selection 可消费的 material list。

    :param source_snapshot: compact source snapshot。
    :returns: material blocks，包含 current input anchor block。
    """

    current = run_input_material_block(
        block_id=f"current:{source_snapshot.current_input_ref}",
        section=CompactMaterialSection.CURRENT_INPUT_ANCHOR,
        kind=CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR,
        text=source_snapshot.current_input_text,
        canonical_source_refs=(source_snapshot.current_input_ref,),
        event_sequence=source_snapshot.input_event_sequence,
    )
    return (*source_snapshot.material_blocks, current)


def _selected_evidence_refs(
    *,
    material_blocks: tuple[RunInputMaterialBlock, ...],
    selected_block_ids: tuple[str, ...],
) -> tuple[str, ...]:
    """从 selected evidence material 派生 accepted evidence refs。

    :param material_blocks: 同源 material blocks。
    :param selected_block_ids: selected block ids。
    :returns: 去重后的 accepted evidence refs。
    """

    selected = frozenset(selected_block_ids)
    refs: list[str] = []
    for block in material_blocks:
        if block.block_id in selected and block.accepted_evidence_id is not None:
            refs.append(block.accepted_evidence_id)
    return _dedupe_texts(tuple(refs))


def _selected_raw_turn_refs(
    *,
    material_blocks: tuple[RunInputMaterialBlock, ...],
    selected_block_ids: tuple[str, ...],
) -> tuple[str, ...]:
    """从 selected raw turn material 派生 canonical refs。

    :param material_blocks: 同源 material blocks。
    :param selected_block_ids: selected block ids。
    :returns: 去重后的 raw turn refs。
    """

    selected = frozenset(selected_block_ids)
    refs: list[str] = []
    for block in material_blocks:
        if block.block_id not in selected:
            continue
        if block.kind not in (
            CompactMaterialBlockKind.USER_INPUT,
            CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER,
        ):
            continue
        refs.extend(block.canonical_source_refs)
    return _dedupe_texts(tuple(refs))


def _source_refs_for_blocks(blocks: tuple[RunInputMaterialBlock, ...]) -> tuple[str, ...]:
    """返回 material blocks 覆盖的 source refs。

    :param blocks: material blocks。
    :returns: 去重后的 source refs。
    """

    refs: list[str] = []
    for block in blocks:
        refs.extend(block.canonical_source_refs)
    return _dedupe_texts(tuple(refs))


def _raw_turn_count(blocks: tuple[RunInputMaterialBlock, ...]) -> int:
    """统计 selected raw turn material block 数。

    :param blocks: selected material blocks。
    :returns: raw turn block 数。
    """

    return sum(1 for block in blocks if is_turn_group_material_block(block))


def _dedupe_texts(values: tuple[str, ...]) -> tuple[str, ...]:
    """按原顺序去重文本元组。

    :param values: 输入文本元组。
    :returns: 去重后的文本元组。
    """

    return tuple(dict.fromkeys(values))


def _fallback_selection_failure_reason(error: Exception, *, compact_failure_reason: str) -> str:
    """构造 fallback selection failure reason。

    :param error: 捕获的 selection / budget 异常。
    :param compact_failure_reason: 原始 compact failure reason。
    :returns: 结构化 reason 文本。
    """

    return f"compact_pipeline_fallback_selection_failed:{compact_failure_reason}:{type(error).__name__}"


def _raw_tail_block_represented_by_memory(block: RunInputMaterialBlock, memory: MemorySnapshotView) -> bool:
    """判断 raw-tail block 是否已由 memory selected recent window 表示。

    :param block: raw-tail material block。
    :param memory: memory view。
    :returns: 已表示时返回 ``True``。
    """

    source_refs = frozenset(memory.selected_recent_source_refs)
    content_digests = frozenset(memory.selected_recent_content_digests)
    if block.content_digest in content_digests:
        return True
    for ref in block.canonical_source_refs:
        if ref in source_refs:
            return True
    evidence_refs = (
        block.accepted_evidence_id,
        block.tool_result_event_ref,
        block.tool_call_event_ref,
    )
    return any(ref is not None and ref in source_refs for ref in evidence_refs)


def _message_from_material_block(block: RunInputMaterialBlock) -> AgentMessage:
    """把 raw-tail material block 渲染为 Agent message。

    :param block: selected raw-tail block。
    :returns: Agent message。
    :raises HostDurableError: accepted evidence 缺 typed LLM material 时抛出。
    """

    if block.kind is CompactMaterialBlockKind.USER_INPUT:
        return UserMessage(role=AgentMessageRole.USER, content=block.text)
    if block.kind is CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER:
        return AssistantMessage(
            role=AgentMessageRole.ASSISTANT,
            content=block.text,
            reasoning_content=None,
            tool_calls=(),
        )
    if block.kind is CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE:
        if block.accepted_tool_evidence is None:
            raise HostDurableError("accepted tool evidence LLM material is missing")
        return SystemMessage(
            role=AgentMessageRole.SYSTEM,
            content=(
                f"{_ACCEPTED_TOOL_EVIDENCE_PREFIX}\n"
                f"{render_accepted_tool_evidence_for_llm(block.accepted_tool_evidence)}"
            ),
        )
    if block.section is CompactMaterialSection.EVIDENCE_MATERIAL:
        return SystemMessage(
            role=AgentMessageRole.SYSTEM,
            content=f"{_RECENT_EVIDENCE_PREFIX}\n{block.text}",
        )
    return SystemMessage(role=AgentMessageRole.SYSTEM, content=block.text)


__all__ = [
    "CompactPipelineAcceptedPayloadInput",
    "CompactPipelineAttemptDispatchSnapshot",
    "CompactPipelineCompactArtifactView",
    "CompactPipelineCurrentRunFacts",
    "CompactPipelineFailedPayloadInput",
    "CompactPipelineFallbackDecisionInput",
    "CompactPipelineFallbackSelectedMaterialHandoff",
    "CompactPipelineOrdinaryRawTailHandoff",
    "CompactPipelinePassQueuePlan",
    "CompactPipelineProtectedRawTailProvider",
    "CompactPipelineRecoveryRequestPlan",
    "CompactPipelineRequestPlan",
    "CompactPipelineSourceSnapshot",
    "MemorySnapshotView",
    "build_compacted_payload_input",
    "build_fallback_decision_input",
    "build_normal_compact_request_plan",
    "build_reactive_pass_queue_plan",
    "build_tier_recovery_request_plans",
    "compact_pipeline_source_snapshot_from_pre_dispatch_view",
    "select_ordinary_protected_raw_tail",
]
