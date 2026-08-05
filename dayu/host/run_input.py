"""Host RunInputBuilder 与 no-tool provider 边界。

本模块实现 Phase 5 的内部 RunInputBuilder。它只从 durable EventLog /
Run / Attempt / dispatch record 与显式注入的 policy snapshot 构造 Engine
``AgentRunRequest``，不读取 UI / Service 临时状态，不实现 scheduler、
LocalProxy、ToolRuntime 执行、Memory projection 或 Context Governance。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, NoReturn, Protocol, cast

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionRequest, GeminiToolCallState
from dayu.contracts.tool_executor import ToolExecutor
from dayu.contracts.tool_outcome import (
    BatchToolExecutionOutcome,
    BatchToolExecutionRecord,
    TOOL_CANCELLED_REASON_HOST_CANCELLED,
    ToolCancelledOutcome,
)
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.engine.contracts.engine_events import (
    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION,
    runner_role_sequence_digest,
)
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.messages import (
    AgentMessage,
    AgentMessageRole,
    AssistantToolCall,
    AssistantMessage,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.host._runner_call_manifest import (
    RunnerCallHotAtoms,
    RunnerCallInputManifest,
    RunnerCallProjectorMetadata,
    RunnerCallSizingSnapshot,
    RunnerCallSizingStatus,
    RunnerCallSizingUnavailableReason,
    complete_runner_call_hot_diagnostic,
    complete_runner_call_sizing_snapshot,
    runner_call_hot_payload,
    runner_call_projector_metadata_descriptor,
    runner_call_sizing_snapshot_json,
    parse_runner_call_hot_payload,
    parse_runner_call_manifest,
    unavailable_runner_call_sizing_snapshot,
)
from dayu.host._execution_config_projection import (
    effective_execution_snapshot_from_json,
    provider_request_json,
    runner_options_json,
)
from dayu.host._event_payload import (
    payload_object as _payload_object,
)
from dayu.host._event_payload import (
    required_payload_text as _required_payload_text,
)
from dayu.host._terminal_answer import assistant_final_answer_continuity_text
from dayu.host.api import AttemptDispatchSnapshot
from dayu.host.api import AttemptStatus, RunStatus
from dayu.host.compact_payload import parse_context_compacted_semantic_payload
from dayu.host.context_event_payload import resolve_context_compacted_payload
from dayu.host.context_events import CONTEXT_COMPACTED, CONTEXT_COMPACTION_REQUESTED
from dayu.host.context_fallback import (
    ActiveRecentWindowFallback,
    EventLogContextFallbackProvider,
    fallback_window_digest,
    load_context_fallback_in_transaction,
)
from dayu.host.compact_material import (
    RunInputMaterialBlock,
    build_pre_dispatch_compact_material_view,
    is_turn_group_material_block,
    protected_recent_turn_group_ids_for_material_blocks,
    run_input_material_block,
    selected_material_view_digest,
)
from dayu.host.compact_pipeline import (
    CompactPipelineAttemptDispatchSnapshot,
    CompactPipelineCompactArtifactView,
    CompactPipelineCurrentRunFacts,
    CompactPipelineOrdinaryRawTailHandoff,
    CompactPipelineProtectedRawTailProvider,
    MemorySnapshotView as CompactPipelineMemorySnapshotView,
    compact_pipeline_source_snapshot_from_pre_dispatch_view,
    select_ordinary_protected_raw_tail,
)
from dayu.host.compaction import (
    CompactMaterialBlockKind,
    CompactMaterialSection,
)
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.context_budget import (
    CONTEXT_ESTIMATOR_CONTRACT,
    BudgetEstimate,
    BudgetEstimateInput,
    BudgetJsonFragment,
    BudgetTextFragment,
    ContextSizingStage,
    estimate_context_budget,
    estimate_context_input,
)
from dayu.host.context_anchor import (
    ContextAnchorQuery,
    ContextAnchorResolution,
    resolve_context_anchor,
)
from dayu.host.context_policy import ContextBudgetPolicy
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
    read_event_by_id,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.memory import (
    conversation_memory_projection_event_filter,
    read_latest_memory_snapshot_at_or_before,
)
from dayu.host.durable.payload import (
    BoundedJsonPayloadWriteRequest,
    PayloadDescriptor,
    PayloadStore,
    SQLitePayloadFormat,
    SQLitePayloadWriteRequest,
)
from dayu.host.durable.schema import (
    PayloadDescriptorKind,
    RUNNER_CALL_INPUT_MANIFEST_MEDIA_TYPE,
    RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION,
    RUNNER_CALL_INPUT_PROJECTION_MEDIA_TYPE,
    RUNNER_CALL_INPUT_PROJECTION_SCHEMA_VERSION,
    SELECTED_TOOL_SCHEMA_SNAPSHOT_MEDIA_TYPE,
    SELECTED_TOOL_SCHEMA_SNAPSHOT_SCHEMA_VERSION,
    TABLE_EVENT_LOG,
    payload_descriptor_metadata,
)
from dayu.host.durable.state import (
    AttemptRow,
    DispatchRecordRow,
    DispatchRecordStatus,
    RunRow,
    RunStartReason,
    decode_run_started_payload,
    read_attempt_by_id,
    read_dispatch_record_by_attempt_id,
    read_run_by_id,
)
from dayu.host.durable.transaction import HostRow, HostTransaction, HostTransactionRunner
from dayu.host.accepted_result_projection import (
    AcceptedToolResultProjection,
    AcceptedToolResultStatus,
    project_accepted_tool_result,
)
from dayu.host.evidence import render_accepted_tool_evidence_for_llm
from dayu.host.payload_resolution import (
    event_payload_object,
    sqlite_payload_object,
)
from dayu.host.projection import event_log_read_filter_from_projection_filter
from dayu.host.terminal_payload import (
    PayloadTextReadPolicy,
)
from dayu.host.memory import (
    CONVERSATION_MEMORY_CONSUMER_ID,
    ConversationMemorySnapshotVNext,
    MemoryDiagnostic,
    MemoryProjectionEvent,
    MemoryProjectionPolicy,
    MemoryRepairReason,
    MemoryRepairRequest,
    MemorySnapshotCursor,
    EvidenceBackedFactView,
    ReferenceContinuityItem,
    SelectedRecentWindowItem,
    SelectedRecentWindowRole,
    build_inline_delta_repair_diagnostic,
    digest_memory_projection_policy,
    memory_snapshot_with_cursor_and_diagnostics,
    project_conversation_memory_event,
)

if TYPE_CHECKING:
    from dayu.host.tool_runtime import ToolRuntimeHandle

_EVENT_TYPE_USER_INPUT_ACCEPTED = "USER_INPUT_ACCEPTED"
_EVENT_TYPE_RUN_ACCEPTED = "RUN_ACCEPTED"
_EVENT_TYPE_RUN_STARTED = "RUN_STARTED"
_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"
_EVENT_TYPE_TOOL_RESULT_ACCEPTED = "TOOL_RESULT_ACCEPTED"
_EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED = "RUNNER_CALL_INPUT_ASSEMBLED"
_PAYLOAD_FIELD_DISPLAY_TEXT = "display_text"
_PAYLOAD_FIELD_SYSTEM_PROMPT = "system_prompt"
_PAYLOAD_FIELD_OPERATION_KIND = "operation_kind"
_PAYLOAD_FIELD_EXECUTION_TARGET = "execution_target"
_PAYLOAD_FIELD_TOOL_RESULT_EVENT_REF = "tool_result_event_ref"
_PAYLOAD_FIELD_EVENT_ID = "event_id"
_PAYLOAD_FIELD_TOOL_CALL_ID = "tool_call_id"
_PAYLOAD_FIELD_TOOL_NAME = "tool_name"
_PAYLOAD_FIELD_ARGUMENTS = "arguments"
_PAYLOAD_FIELD_COMPACT_ARTIFACT_REF = "compact_artifact_ref"
_PAYLOAD_FIELD_COMPACT_ARTIFACT_DIGEST = "compact_artifact_digest"
_PAYLOAD_FIELD_OPERATION_ID = "operation_id"
_PAYLOAD_FIELD_TRIGGER_SOURCE = "trigger_source"
_NO_TOOL_CANCEL_MESSAGE = "tools are disabled for this attempt"
_PREPARED_CANDIDATE_SCHEMA_VERSION = "runner_call_prepared_candidate.v1"
_PREPARED_CANDIDATE_MEDIA_TYPE = "application/vnd.dayu.runner-call-prepared-candidate+json"
_PREPARED_CANDIDATE_FIELDS = frozenset(
    {
        "schema_version",
        "session_id",
        "host_run_id",
        "candidate_input_cursor",
        "messages",
        "tool_schemas",
        "disable_tools",
        "tool_execution_mode",
        "policy_snapshot_ref",
        "policy_snapshot_digest",
        "source_cursor_refs",
        "memory_snapshot_cursor_ref",
        "compact_artifact_refs",
        "context_fallback_decision_ref",
        "request_semantics_digest",
        "estimator_id",
        "estimator_version",
    }
)
_PREPARED_CANDIDATE_POLICY_INDEPENDENT_FIELDS = frozenset(
    {
        "schema_version",
        "session_id",
        "host_run_id",
        "candidate_input_cursor",
        "messages",
        "tool_schemas",
        "disable_tools",
        "tool_execution_mode",
        "source_cursor_refs",
        "memory_snapshot_cursor_ref",
        "compact_artifact_refs",
        "context_fallback_decision_ref",
    }
)
_SYSTEM_ENVELOPE_SEPARATOR = "\n\n"
_SYSTEM_ENVELOPE_HEADER_PREFIX = "## "
_SYSTEM_SECTION_TASK_INSTRUCTIONS = "Task Instructions"
_SYSTEM_SECTION_EXECUTION_GUIDANCE = "Execution Guidance"
_SYSTEM_SECTION_CONVERSATION_SUMMARY = "Conversation Summary"
_SYSTEM_SECTION_VERIFIED_EVIDENCE = "Verified Evidence and Facts"
_SYSTEM_SECTION_PRIOR_ANSWER_ANCHORS = "Prior Answer Anchors"
_SYSTEM_SECTION_OPEN_FOLLOWUP_CONTEXT = "Open Follow-up Context"
_SYSTEM_SECTION_REFERENCE_CONTINUITY = "Reference Continuity"
_SYSTEM_SECTION_RECENT_EVIDENCE = "Recent Evidence"
_SYSTEM_ENVELOPE_SECTION_ORDER = (
    _SYSTEM_SECTION_TASK_INSTRUCTIONS,
    _SYSTEM_SECTION_EXECUTION_GUIDANCE,
    _SYSTEM_SECTION_CONVERSATION_SUMMARY,
    _SYSTEM_SECTION_VERIFIED_EVIDENCE,
    _SYSTEM_SECTION_PRIOR_ANSWER_ANCHORS,
    _SYSTEM_SECTION_OPEN_FOLLOWUP_CONTEXT,
    _SYSTEM_SECTION_REFERENCE_CONTINUITY,
    _SYSTEM_SECTION_RECENT_EVIDENCE,
)
_EXECUTION_GUIDANCE_PREFIX = "Execution guidance:"
_RECENT_EVIDENCE_PREFIX = "Recent evidence:"
_ACCEPTED_TOOL_EVIDENCE_PREFIX = "Accepted tool evidence:"
_MEMORY_SESSION_SUMMARY_HEADER = "Session Summary Memory:"
_MEMORY_EVIDENCE_FACT_HEADER = "Evidence / Fact Memory:"
_MEMORY_ANSWER_ANCHOR_HEADER = "Answer Anchor Memory:"
_MEMORY_FORWARD_INTENT_HEADER = "Forward Intent Memory:"
_MEMORY_REFERENCE_CONTINUITY_HEADER = "Trace Memory reference continuity:"
_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS = (
    "policy_snapshot_ref=",
    "tool_call_id=",
    "tool_call_id",
    "event_id=",
    "event_sequence=",
    "payload_ref=",
    "artifact_ref=",
    "compact_artifact_ref=",
    "compact_artifact_digest=",
    "manifest_payload_ref=",
    "manifest_digest=",
    "projection_artifact_ref=",
    "projection_checkpoint",
    "projector_metadata",
    "attempt_id=",
    "execution_id=",
    "runner_call_index=",
    "checkpoint_event_id",
    "checkpoint_event_sequence",
    "CompactCandidateV3",
)
_RUNNER_CALL_MANIFEST_PAYLOAD_REF_PREFIX = "payload-runner-call-input-manifest"
_RUNNER_CALL_MANIFEST_SQLITE_PAYLOAD_ID_PREFIX = "sqlite-payload-runner-call-input-manifest"
_RUNNER_CALL_PROJECTION_PAYLOAD_REF_PREFIX = "payload-runner-call-input-projection"
_RUNNER_CALL_PROJECTION_SQLITE_PAYLOAD_ID_PREFIX = "sqlite-payload-runner-call-input-projection"
_SELECTED_TOOL_SCHEMA_PAYLOAD_REF_PREFIX = "payload-selected-tool-schema-snapshot"
_SELECTED_TOOL_SCHEMA_SQLITE_PAYLOAD_ID_PREFIX = "sqlite-payload-selected-tool-schema-snapshot"
_RUNNER_CALL_EVENT_ID_PREFIX = "event-runner-call-input-assembled"
_RUNNER_CALL_EVENT_ACTOR = "host.run_input"
_RUNNER_CALL_EVENT_SOURCE = "host.run_input.builder"
_PREPARED_CANDIDATE_PROJECTION_REF_PREFIX = "runner-call-candidate-projection"
_RUNNER_CALL_KIND_INITIAL_USER_DISPATCH = "initial_user_dispatch"
_RUNNER_CALL_KIND_FOLLOWUP_USER_DISPATCH = "followup_user_dispatch"
_RUNNER_CALL_KIND_POST_COMPACTION_DISPATCH = "post_compaction_dispatch"
_RUNNER_CALL_KIND_COMPACTOR_PROPOSAL = "compactor_proposal"
_PRE_START_RUNNER_CALL_KINDS = frozenset(
    {
        _RUNNER_CALL_KIND_INITIAL_USER_DISPATCH,
        _RUNNER_CALL_KIND_FOLLOWUP_USER_DISPATCH,
        _RUNNER_CALL_KIND_POST_COMPACTION_DISPATCH,
    }
)
_RUNNER_CALL_TRIGGER_INITIAL_USER_INPUT = "initial_user_input"
_RUNNER_CALL_TRIGGER_FOLLOWUP_USER_INPUT = "followup_user_input"
_RUNNER_CALL_TRIGGER_HOST_RESUME = "host_resume"
_RUNNER_CALL_TRIGGER_CONTEXT_GOVERNANCE_RESOLVED = "context_governance_resolved"
_RUNNER_CALL_VALIDATION_COMPLETE = "complete"
_PROJECTOR_ID_SYSTEM_CONTEXT = "run_input_system_context"
_PROJECTOR_ID_USER_INPUT = "user_input_message"
_PROJECTOR_ID_ASSISTANT_HISTORY = "assistant_history_message"
_PROJECTOR_ID_TOOL_RESULT = "tool_result_message"
_PROJECTOR_ID_MEMORY = "compact_memory_material"
_PROJECTOR_ID_RECENT_WINDOW = "recent_window_material"
_PROJECTOR_PURPOSE_ORDINARY = "ordinary_run_input"
_PROJECTOR_PURPOSE_POST_COMPACTION = "post_compaction_input"
_PROJECTOR_SCHEMA_VERSION = "run_input_projector.v1"


class ToolExecutionMode(StrEnum):
    """RunInputBuilder 的显式工具执行模式。

    - ``TOOL_ENABLED``：普通允许工具的 Attempt。
    - ``NO_TOOL_REPLAY``：replay Attempt，结构修复但不暴露工具。
    - ``NO_TOOL_DISABLED``：显式禁用工具的 Attempt。
    """

    TOOL_ENABLED = "tool_enabled"
    NO_TOOL_REPLAY = "no_tool_replay"
    NO_TOOL_DISABLED = "no_tool_disabled"


@dataclass(frozen=True, slots=True)
class CurrentRunFacts:
    """当前 RunInputBuilder 构造所需的 durable 当前 Run facts。

    :param run: 当前 Run row。
    :param attempt: 当前 Attempt row。
    :param dispatch_record: 当前 dispatch record row。
    :param user_input_event: 当前 ``USER_INPUT_ACCEPTED`` 事件。
    :param run_accepted_event: 当前 ``RUN_ACCEPTED`` 事件。
    :param run_started_event: 当前 ``RUN_STARTED`` 事件。
    :param user_prompt: 当前用户 prompt 文本。
    :param system_prompt: 当前 Run 显式 system prompt；无则为 ``None``。
    :param operation_kind: 当前 operation kind。
    """

    run: RunRow
    attempt: AttemptRow
    dispatch_record: DispatchRecordRow
    user_input_event: EventLogRow
    run_accepted_event: EventLogRow
    run_started_event: EventLogRow
    user_prompt: str
    system_prompt: str | None
    operation_kind: str


@dataclass(frozen=True, slots=True)
class SessionContinuityView:
    """Session continuity provider 输出。

    :param messages: 由历史 canonical facts 投影出的 messages。
    :param source_refs: continuity 对应的 canonical source refs。
    """

    messages: tuple[AgentMessage, ...]
    source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PreparedRunnerCallSource:
    """strict-load 后的 prepared runner-call source。

    :param manifest_event: source ``RUNNER_CALL_INPUT_ASSEMBLED`` event。
    :param manifest: digest-verified strict manifest。
    :param candidate: digest-verified complete candidate。
    """

    manifest_event: EventLogRow
    manifest: RunnerCallInputManifest
    candidate: PreparedRunnerCallCandidate


class PreparedRunnerCallSourceFailureCategory(StrEnum):
    """continuation source strict owner 的封闭失败类别。"""

    TOOL_SCHEMA = "tool_schema"
    POLICY = "policy"
    REQUEST_SEMANTICS = "request_semantics"


class PreparedRunnerCallSourceError(HostDurableError):
    """prepared runner-call source 无法供 continuation 使用。

    :param category: strict owner 判定的失败类别。
    :param message: 不参与下游分类的诊断文本。
    """

    category: PreparedRunnerCallSourceFailureCategory

    def __init__(
        self,
        category: PreparedRunnerCallSourceFailureCategory,
        message: str,
    ) -> None:
        """初始化 typed source failure。

        :param category: strict owner 判定的失败类别。
        :param message: 非空诊断文本。
        :returns: ``None``。
        :raises ValueError: ``message`` 为空时抛出。
        """

        if message.strip() == "":
            raise ValueError("PreparedRunnerCallSourceError.message must be non-empty")
        self.category = category
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class _PreparedSourceToolFacts:
    """prepared candidate 中不依赖 policy 的 strict tool facts。

    :param tool_schemas: candidate 冻结的 exact selected schemas。
    :param disable_tools: candidate 冻结的工具禁用标志。
    :param tool_execution_mode: candidate 冻结的工具执行模式。
    """

    tool_schemas: tuple[ToolSchema, ...]
    disable_tools: bool
    tool_execution_mode: ToolExecutionMode


@dataclass(frozen=True, slots=True)
class MemorySnapshotView:
    """Memory snapshot provider 输出。

    :param messages: memory stable layer messages。
    :param memory_snapshot_cursor: memory snapshot cursor；no-op provider 为 ``None``。
    :param policy_digest: memory policy digest；no-op provider 为 ``None``。
    :param diagnostics: memory provider 产生或透传的 diagnostics。
    :param represented_evidence_refs: 已被 stable evidence-backed fact 表示的
        accepted evidence refs。
    :param latest_compaction_event_ref: memory snapshot 已覆盖的最新 compact event id。
    :param selected_recent_source_refs: 已渲染 selected recent window 的内部来源
        refs，仅用于 provider 内部去重，不进入 LLM-facing messages。
    :param selected_recent_content_digests: 已渲染 selected recent window 的文本
        digest，仅用于 provider 内部去重，不进入 LLM-facing messages。
    """

    messages: tuple[AgentMessage, ...]
    memory_snapshot_cursor: str | None
    policy_digest: str | None
    diagnostics: tuple[MemoryDiagnostic, ...]
    represented_evidence_refs: tuple[str, ...] = ()
    latest_compaction_event_ref: str | None = None
    selected_recent_source_refs: tuple[str, ...] = ()
    selected_recent_content_digests: tuple[str, ...] = ()


class MemoryProjectionRepairRequired(HostDurableError):
    """RunInputBuilder 需要 memory projection repair 的结构化错误。

    :param repair_request: repair 请求。
    """

    repair_request: MemoryRepairRequest

    def __init__(self, repair_request: MemoryRepairRequest) -> None:
        """初始化 repair-required 错误。

        :param repair_request: repair 请求。
        :returns: ``None``。
        """

        self.repair_request = repair_request
        super().__init__(
            "memory projection repair required: "
            f"reason={repair_request.reason.value}, "
            f"session_id={repair_request.session_id}, "
            f"required_event_sequence={repair_request.required_event_sequence}"
        )


@dataclass(frozen=True, slots=True)
class _CurrentMemoryRenderScope:
    """本次 RunInputBuilder 渲染 memory 时需要排除的当前 Run facts。

    :param run_id: 当前 Run id。
    :param user_input_event_id: 当前 ``USER_INPUT_ACCEPTED`` event id。
    :param user_prompt: 当前用户 prompt。
    """

    run_id: str
    user_input_event_id: str
    user_prompt: str


@dataclass(frozen=True, slots=True)
class _MemoryStableBlock:
    """RunInputBuilder 渲染前的 stable memory block。

    :param block_id: 可诊断的稳定 block id。
    :param message: 待注入的 system message。
    """

    block_id: str
    message: SystemMessage


@dataclass(frozen=True, slots=True)
class _RenderedMemoryMessages:
    """Memory snapshot 渲染结果。

    :param messages: 可交给 Engine 的 messages。
    :param diagnostics: 渲染阶段产生的 transient diagnostics。
    """

    messages: tuple[AgentMessage, ...]
    diagnostics: tuple[MemoryDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class CompactArtifactView:
    """Compact artifact provider 输出。

    :param compaction_event_ref: latest accepted compact event id。
    :param compact_artifact_ref: compact artifact ref；Phase 5 noop 为 ``None``。
    :param compact_artifact_digest: compact artifact digest；Phase 5 noop 为 ``None``。
    :param represented_evidence_refs: 已被 accepted compact artifact 表示的
        canonical evidence refs。
    """

    compaction_event_ref: str | None
    compact_artifact_ref: str | None
    compact_artifact_digest: str | None
    represented_evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolSchemaSnapshot:
    """工具 schema snapshot provider 输出。

    :param tool_schemas: 暴露给 Engine 的工具 schema 元组。
    :param disable_tools: 是否禁用工具调用。
    :param tool_runtime_handle: tool-enabled 模式下的 ToolRuntime handle；
        no-tool / replay 模式下为 ``None``。
    """

    tool_schemas: tuple[ToolSchema, ...]
    disable_tools: bool
    tool_runtime_handle: ToolRuntimeHandle | None


@dataclass(frozen=True, slots=True)
class PolicySnapshot:
    """RunInputBuilder 使用的显式 policy snapshot。

    :param runner_spec: Engine Runner 规约。
    :param runner_options: Engine Runner 调用参数。
    :param agent_policy: Engine Agent policy。
    :param policy_snapshot_ref: Host policy snapshot ref。
    """

    runner_spec: RunnerSpec
    runner_options: RunnerCallOptions
    agent_policy: AgentPolicy
    policy_snapshot_ref: str

    def __post_init__(self) -> None:
        """校验 policy snapshot 的基础一致性。

        :returns: ``None``。
        :raises ValueError: policy ref 为空时抛出。
        """

        if self.policy_snapshot_ref.strip() == "":
            raise ValueError("policy_snapshot_ref must be non-empty")


@dataclass(frozen=True, slots=True)
class PreparedRunnerCallCandidate:
    """Attempt identity-free 的 complete runner-call candidate。

    :param session_id: Session id。
    :param run_id: Host Run id。
    :param candidate_input_cursor: 本次读取的最大 committed source watermark。
    :param candidate_input_projection_ref: identity-free projection logical ref。
    :param candidate_input_projection_digest: identity-free projection digest。
    :param input_snapshot_digest: messages/tools/policy/request semantics digest。
    :param messages: 完整 normalized Runner messages。
    :param tool_schemas: selected tool schemas。
    :param disable_tools: 是否禁用工具。
    :param tool_execution_mode: frozen 工具执行模式。
    :param policy_snapshot: admission-frozen Engine policy snapshot。
    :param source_cursor_refs: complete candidate source refs。
    :param memory_snapshot_cursor_ref: frozen memory cursor ref。
    :param compact_artifact_refs: frozen compact artifact refs。
    :param context_fallback_decision_ref: frozen fallback decision ref。
    :param request_semantics_digest: request serialization compatibility digest。
    """

    session_id: str
    run_id: str
    candidate_input_cursor: int
    candidate_input_projection_ref: str
    candidate_input_projection_digest: str
    input_snapshot_digest: str
    messages: tuple[AgentMessage, ...]
    tool_schemas: tuple[ToolSchema, ...]
    disable_tools: bool
    tool_execution_mode: ToolExecutionMode
    policy_snapshot: PolicySnapshot
    source_cursor_refs: tuple[str, ...]
    memory_snapshot_cursor_ref: str | None
    compact_artifact_refs: tuple[str, ...]
    context_fallback_decision_ref: str | None
    request_semantics_digest: str

    def __post_init__(self) -> None:
        """校验 complete candidate contract。

        :returns: ``None``。
        :raises TypeError: tuple、bool 或 policy 类型非法时抛出。
        :raises ValueError: identity/ref/digest/cursor 非法时抛出。
        """

        for field_name, value in (
            ("PreparedRunnerCallCandidate.session_id", self.session_id),
            ("PreparedRunnerCallCandidate.run_id", self.run_id),
            (
                "PreparedRunnerCallCandidate.candidate_input_projection_ref",
                self.candidate_input_projection_ref,
            ),
            (
                "PreparedRunnerCallCandidate.candidate_input_projection_digest",
                self.candidate_input_projection_digest,
            ),
            (
                "PreparedRunnerCallCandidate.input_snapshot_digest",
                self.input_snapshot_digest,
            ),
            (
                "PreparedRunnerCallCandidate.request_semantics_digest",
                self.request_semantics_digest,
            ),
        ):
            if not isinstance(value, str) or value.strip() == "":
                raise ValueError(f"{field_name} must be non-empty")
        if (
            isinstance(self.candidate_input_cursor, bool)
            or not isinstance(self.candidate_input_cursor, int)
            or self.candidate_input_cursor < 0
        ):
            raise ValueError("PreparedRunnerCallCandidate.candidate_input_cursor must be non-negative int")
        if not isinstance(self.messages, tuple):
            raise TypeError("PreparedRunnerCallCandidate.messages must be tuple")
        if not isinstance(self.tool_schemas, tuple):
            raise TypeError("PreparedRunnerCallCandidate.tool_schemas must be tuple")
        if not isinstance(self.disable_tools, bool):
            raise TypeError("PreparedRunnerCallCandidate.disable_tools must be bool")
        if not isinstance(self.tool_execution_mode, ToolExecutionMode):
            raise TypeError("PreparedRunnerCallCandidate.tool_execution_mode must be ToolExecutionMode")
        if not isinstance(self.policy_snapshot, PolicySnapshot):
            raise TypeError("PreparedRunnerCallCandidate.policy_snapshot must be PolicySnapshot")
        for field_name, values in (
            (
                "PreparedRunnerCallCandidate.source_cursor_refs",
                self.source_cursor_refs,
            ),
            (
                "PreparedRunnerCallCandidate.compact_artifact_refs",
                self.compact_artifact_refs,
            ),
        ):
            if not isinstance(values, tuple):
                raise TypeError(f"{field_name} must be tuple")
            for value in values:
                if not isinstance(value, str) or value.strip() == "":
                    raise ValueError(f"{field_name} items must be non-empty")


class CurrentRunFactProvider(Protocol):
    """当前 Run durable fact provider 协议。"""

    def load_current_run_facts(self, snapshot: AttemptDispatchSnapshot) -> CurrentRunFacts:
        """读取当前 RunInputBuilder 所需 durable facts。

        :param snapshot: Attempt dispatch snapshot。
        :returns: 当前 Run facts。
        :raises HostDurableError: durable facts 缺失或不匹配时抛出。
        """
        ...


class SessionContinuityProvider(Protocol):
    """Session continuity provider 协议。"""

    def load_session_continuity(
        self, snapshot: AttemptDispatchSnapshot, current_facts: CurrentRunFacts
    ) -> SessionContinuityView:
        """读取当前 Attempt 之前的 Session continuity messages。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: Session continuity view。
        :raises HostDurableError: durable facts 无法投影时抛出。
        """
        ...


class MemorySnapshotProvider(Protocol):
    """Memory snapshot provider 协议。"""

    def load_memory_snapshot(
        self, snapshot: AttemptDispatchSnapshot, current_facts: CurrentRunFacts
    ) -> MemorySnapshotView:
        """读取 memory stable layer。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: Memory snapshot view。
        """
        ...


class CompactArtifactProvider(Protocol):
    """Compact artifact provider 协议。"""

    def load_compact_artifact(
        self, snapshot: AttemptDispatchSnapshot, current_facts: CurrentRunFacts
    ) -> CompactArtifactView:
        """读取 compact artifact view。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: Compact artifact view。
        """
        ...


class AcceptedToolEvidenceMaterialProvider(Protocol):
    """Accepted tool evidence material provider 协议。"""

    def load_accepted_tool_evidence_materials(
        self,
        snapshot: AttemptDispatchSnapshot,
        current_facts: CurrentRunFacts,
        memory: MemorySnapshotView,
        compact: CompactArtifactView,
    ) -> tuple[RunInputMaterialBlock, ...]:
        """读取当前 Attempt 可用于 compact 的 accepted tool evidence material。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :param memory: 当前 memory provider view。
        :param compact: 当前 compact artifact provider view。
        :returns: evidence material blocks。
        :raises HostDurableError: evidence payload 损坏时抛出。
        """
        ...


class ContextFallbackProvider(Protocol):
    """RunInputBuilder 内部 fallback view provider 协议。"""

    def load_context_fallback(
        self,
        *,
        run_id: str,
        run_started_event_sequence: int,
        current_input_ref: str,
    ) -> ActiveRecentWindowFallback | None:
        """读取当前 dispatch 绑定的 fallback view。

        :param run_id: 当前 Run id。
        :param run_started_event_sequence: 当前 ``RUN_STARTED`` event sequence。
        :param current_input_ref: 当前用户输入 event id。
        :returns: active fallback view；不存在时返回 ``None``。
        """
        ...


class NoopContextFallbackProvider:
    """默认 no-op fallback provider。"""

    def load_context_fallback(
        self,
        *,
        run_id: str,
        run_started_event_sequence: int,
        current_input_ref: str,
    ) -> ActiveRecentWindowFallback | None:
        """返回空 fallback view。

        :param run_id: 当前 Run id。
        :param run_started_event_sequence: 当前 ``RUN_STARTED`` event sequence。
        :param current_input_ref: 当前用户输入 event id。
        :returns: 始终返回 ``None``。
        """

        del run_id, run_started_event_sequence, current_input_ref
        return None


class ToolSchemaSnapshotProvider(Protocol):
    """Tool schema snapshot provider 协议。"""

    def load_tool_schema_snapshot(
        self, snapshot: AttemptDispatchSnapshot, current_facts: CurrentRunFacts
    ) -> ToolSchemaSnapshot:
        """读取工具 schema snapshot。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: Tool schema snapshot。
        """
        ...


class ToolExecutorProvider(Protocol):
    """ToolExecutor provider 协议。"""

    def load_tool_executor(self, snapshot: AttemptDispatchSnapshot, current_facts: CurrentRunFacts) -> ToolExecutor:
        """读取 Engine ToolExecutor。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: ToolExecutor。
        """
        ...


class ToolRuntimeHandleProvider(Protocol):
    """ToolRuntime handle provider 协议。"""

    def load_tool_runtime_handle(
        self, snapshot: AttemptDispatchSnapshot, current_facts: CurrentRunFacts
    ) -> ToolRuntimeHandle:
        """读取 tool-enabled Attempt 使用的 ToolRuntime handle。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: ToolRuntimeHandle。
        """
        ...


class SceneParameterProvider(Protocol):
    """Scene parameter provider 协议。"""

    def build_scene_messages(
        self,
        snapshot: AttemptDispatchSnapshot,
        current_facts: CurrentRunFacts,
        policy_snapshot: PolicySnapshot,
        tool_execution_mode: ToolExecutionMode,
    ) -> tuple[SystemMessage, ...]:
        """构造 system scene / execution target / policy messages。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :param policy_snapshot: policy snapshot。
        :param tool_execution_mode: 显式工具执行模式。
        :returns: system message 元组。
        """
        ...


class PolicySnapshotProvider(Protocol):
    """Policy snapshot provider 协议。"""

    def load_policy_snapshot(self, snapshot: AttemptDispatchSnapshot, current_facts: CurrentRunFacts) -> PolicySnapshot:
        """读取显式 policy snapshot。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: policy snapshot。
        """
        ...


@dataclass(frozen=True, slots=True)
class RunnerCallManifestRecordInput:
    """记录 runner-call input assembly manifest 所需输入。

    :param attempt_snapshot: Attempt dispatch snapshot。
    :param current_facts: 当前 Run durable facts。
    :param policy_snapshot: policy snapshot。
    :param memory: memory snapshot provider view。
    :param compact: compact artifact provider view。
    :param continuity: session continuity provider view。
    :param tool_snapshot: tool schema snapshot provider view。
    :param messages: 实际传给 Engine / Runner 的 messages。
    :param fallback: 当前生效的 recent-window fallback；未生效时为 ``None``。
    """

    attempt_snapshot: AttemptDispatchSnapshot
    current_facts: CurrentRunFacts
    policy_snapshot: PolicySnapshot
    memory: MemorySnapshotView
    compact: CompactArtifactView
    continuity: SessionContinuityView
    tool_snapshot: ToolSchemaSnapshot
    messages: tuple[AgentMessage, ...]
    fallback: ActiveRecentWindowFallback | None


class RunnerCallManifestRecorder(Protocol):
    """runner-call input assembly manifest 记录器协议。"""

    def record_runner_call_manifest(self, record_input: RunnerCallManifestRecordInput) -> None:
        """记录一次 logical runner call input assembly manifest。

        :param record_input: manifest 构造输入。
        :returns: ``None``。
        :raises HostDurableError: manifest 无法写入或校验失败时抛出。
        """
        ...


class NoopRunnerCallManifestRecorder:
    """不写入 manifest 的测试 recorder。"""

    def record_runner_call_manifest(self, record_input: RunnerCallManifestRecordInput) -> None:
        """忽略 manifest 记录请求。

        :param record_input: manifest 构造输入。
        :returns: ``None``。
        """

        del record_input


class DurableRunnerCallManifestRecorder:
    """将 runner-call input assembly manifest 写入 Host EventLog。"""

    def __init__(self, transaction_runner: HostTransactionRunner) -> None:
        """初始化 durable manifest recorder。

        :param transaction_runner: Host durable transaction runner。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner
        self._event_log_store = EventLogStore()
        self._payload_store = PayloadStore()

    def record_runner_call_manifest(self, record_input: RunnerCallManifestRecordInput) -> None:
        """记录一次 logical runner call input assembly manifest。

        :param record_input: manifest 构造输入。
        :returns: ``None``。
        :raises HostDurableError: manifest 无法写入或校验失败时抛出。
        """

        self._transaction_runner.run_write(
            lambda transaction: self._record_in_transaction(
                transaction,
                record_input,
            )
        )

    def _record_in_transaction(
        self,
        transaction: HostTransaction,
        record_input: RunnerCallManifestRecordInput,
    ) -> None:
        """在单个 transaction 内写入 manifest descriptor 与 canonical event。

        :param transaction: 当前 Host transaction。
        :param record_input: manifest 构造输入。
        :returns: ``None``。
        :raises HostDurableError: manifest 无法写入或校验失败时抛出。
        """

        existing = _find_existing_runner_call_manifest_event(
            transaction,
            run=record_input.current_facts.run,
            attempt_id=record_input.current_facts.attempt.attempt_id,
            execution_id=record_input.current_facts.attempt.execution_id,
        )
        if existing is not None:
            return
        runner_call_index = _next_runner_call_index(transaction, run_id=record_input.current_facts.run.run_id)
        event_id = _runner_call_manifest_event_id(
            record_input.current_facts.run.run_id,
            record_input.current_facts.attempt.attempt_id,
            record_input.current_facts.attempt.execution_id,
            runner_call_index,
        )
        projection = _runner_call_projection_body(
            record_input,
            runner_call_index=runner_call_index,
            projection_id=_runner_call_projection_id(event_id),
        )
        projection_digest = sha256_digest_json(projection)
        projection_descriptor = _write_runner_call_projection_payload(
            transaction,
            self._payload_store,
            event_id=event_id,
            projection=projection,
            projection_digest=projection_digest,
        )
        tool_schema_descriptor = _write_selected_tool_schema_snapshot_payload(
            transaction,
            self._payload_store,
            event_id=event_id,
            record_input=record_input,
        )
        manifest = _runner_call_manifest_body(
            record_input,
            runner_call_index=runner_call_index,
            manifest_id=_runner_call_manifest_id(event_id),
            projection_descriptor=projection_descriptor,
            tool_schema_descriptor=tool_schema_descriptor,
        )
        manifest_digest = sha256_digest_json(manifest)
        descriptor = _write_runner_call_manifest_payload(
            transaction,
            self._payload_store,
            event_id=event_id,
            manifest=manifest,
            manifest_digest=manifest_digest,
        )
        hot_payload = _runner_call_manifest_hot_payload(
            manifest=manifest,
            manifest_payload_ref=descriptor.payload_ref,
            manifest_digest=manifest_digest,
        )
        self._event_log_store.append_event(
            transaction,
            EventLogAppendRequest(
                event_id=event_id,
                event_class=EventClass.CANONICAL_FACT,
                session_id=record_input.current_facts.run.session_id,
                run_id=record_input.current_facts.run.run_id,
                attempt_id=record_input.current_facts.attempt.attempt_id,
                execution_id=record_input.current_facts.attempt.execution_id,
                event_type=_EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED,
                occurred_at=datetime.now(UTC),
                actor=_RUNNER_CALL_EVENT_ACTOR,
                source=_RUNNER_CALL_EVENT_SOURCE,
                client_request_id=record_input.current_facts.run.client_request_id,
                idempotency_key=None,
                policy_decision=None,
                reason=None,
                payload_json=hot_payload,
                payload_ref=descriptor.payload_ref,
                payload_digest=descriptor.payload_digest,
            ),
        )


def record_prepared_runner_call_candidate_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    payload_store: PayloadStore,
    *,
    run: RunRow,
    attempt_id: str,
    execution_id: str,
    occurred_at: datetime,
    candidate: PreparedRunnerCallCandidate,
    sizing_snapshot: RunnerCallSizingSnapshot,
) -> EventLogRow:
    """在 allow transaction 内先于 start transition 记录 frozen candidate。

    manifest 与随后 durable start transition 必须消费调用方传入的同一个
    producer 直接提供的 Attempt identity；本函数不生成或替换任何 start input。

    :param transaction: 调用方 write transaction。
    :param event_log_store: EventLog primitive。
    :param payload_store: payload store primitive。
    :param run: 当前 startable Run。
    :param attempt_id: allow 后唯一生成的 Attempt id。
    :param execution_id: allow 后唯一生成的 execution id。
    :param occurred_at: manifest 与随后 start transition 共用的发生时间。
    :param candidate: pre-start frozen identity-free candidate。
    :param sizing_snapshot: complete 或 context-policy-unavailable snapshot。
    :returns: committed 前 transaction 内可见的 manifest event row。
    :raises HostDurableError: identity、descriptor、digest 或 manifest graph 非法时抛出。
    """

    if candidate.run_id != run.run_id or candidate.session_id != run.session_id:
        raise HostDurableError("prepared candidate Run identity mismatch")
    if attempt_id.strip() == "" or execution_id.strip() == "":
        raise HostDurableError("prepared manifest identity must be non-empty")
    runner_call_index = _next_runner_call_index(
        transaction,
        run_id=run.run_id,
    )
    event_id = _runner_call_manifest_event_id(
        run.run_id,
        attempt_id,
        execution_id,
        runner_call_index,
    )
    runner_call_kind, trigger_reason = _prepared_candidate_kind_and_trigger(
        candidate,
        sizing_snapshot=sizing_snapshot,
    )
    _write_prepared_candidate_payload(
        transaction,
        payload_store,
        candidate=candidate,
    )
    projection = _prepared_runner_call_projection_body(
        candidate=candidate,
        attempt_id=attempt_id,
        execution_id=execution_id,
        runner_call_index=runner_call_index,
        projection_id=_runner_call_projection_id(event_id),
        runner_call_kind=runner_call_kind,
        trigger_reason=trigger_reason,
    )
    projection_digest = sha256_digest_json(projection)
    projection_descriptor = _write_runner_call_projection_payload(
        transaction,
        payload_store,
        event_id=event_id,
        projection=projection,
        projection_digest=projection_digest,
    )
    tool_schema_descriptor = _write_prepared_tool_schema_snapshot_payload(
        transaction,
        payload_store,
        event_id=event_id,
        candidate=candidate,
        attempt_id=attempt_id,
        execution_id=execution_id,
    )
    manifest = _prepared_runner_call_manifest_body(
        candidate=candidate,
        attempt_id=attempt_id,
        execution_id=execution_id,
        runner_call_index=runner_call_index,
        manifest_id=_runner_call_manifest_id(event_id),
        projection_descriptor=projection_descriptor,
        tool_schema_descriptor=tool_schema_descriptor,
        runner_call_kind=runner_call_kind,
        trigger_reason=trigger_reason,
        sizing_snapshot=sizing_snapshot,
    )
    manifest_digest = sha256_digest_json(manifest)
    descriptor = _write_runner_call_manifest_payload(
        transaction,
        payload_store,
        event_id=event_id,
        manifest=manifest,
        manifest_digest=manifest_digest,
    )
    hot_payload = _runner_call_manifest_hot_payload(
        manifest=manifest,
        manifest_payload_ref=descriptor.payload_ref,
        manifest_digest=manifest_digest,
    )
    return event_log_store.append_event(
        transaction,
        EventLogAppendRequest(
            event_id=event_id,
            event_class=EventClass.CANONICAL_FACT,
            session_id=run.session_id,
            run_id=run.run_id,
            attempt_id=attempt_id,
            execution_id=execution_id,
            event_type=_EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED,
            occurred_at=occurred_at,
            actor=_RUNNER_CALL_EVENT_ACTOR,
            source=_RUNNER_CALL_EVENT_SOURCE,
            client_request_id=run.client_request_id,
            idempotency_key=None,
            policy_decision=None,
            reason=None,
            payload_json=hot_payload,
            payload_ref=descriptor.payload_ref,
            payload_digest=descriptor.payload_digest,
        ),
    ).row


class DurableCurrentRunFactProvider:
    """基于 Host durable store 的当前 Run fact provider。"""

    def __init__(self, transaction_runner: HostTransactionRunner) -> None:
        """初始化 provider。

        :param transaction_runner: Host durable transaction runner。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner
        self._event_log_store = EventLogStore()

    def load_current_run_facts(self, snapshot: AttemptDispatchSnapshot) -> CurrentRunFacts:
        """读取当前 RunInputBuilder 所需 durable facts。

        :param snapshot: Attempt dispatch snapshot。
        :returns: 当前 Run facts。
        :raises HostDurableError: durable facts 缺失或不匹配时抛出。
        """

        return self._transaction_runner.run_read(
            lambda transaction: self._load_current_run_facts_tx(transaction, snapshot)
        )

    def _load_current_run_facts_tx(
        self, transaction: HostTransaction, snapshot: AttemptDispatchSnapshot
    ) -> CurrentRunFacts:
        """在 read transaction 内读取当前 Run facts。

        :param transaction: Host durable transaction。
        :param snapshot: Attempt dispatch snapshot。
        :returns: 当前 Run facts。
        :raises HostDurableError: durable facts 缺失或不匹配时抛出。
        """

        run = read_run_by_id(transaction, snapshot.run_id)
        attempt = read_attempt_by_id(transaction, snapshot.attempt_id)
        dispatch_record = read_dispatch_record_by_attempt_id(transaction, snapshot.attempt_id)
        _validate_snapshot_rows(
            snapshot=snapshot,
            run=run,
            attempt=attempt,
            dispatch_record=dispatch_record,
        )
        if run is None or attempt is None or dispatch_record is None:
            raise HostDurableError("Attempt dispatch snapshot narrowing failed")
        if run.started_event_id is None:
            raise HostDurableError("RunInputBuilder requires RUN_STARTED event")
        user_input_event = _require_event(
            self._event_log_store.read_event_by_id(transaction, run.input_event_id),
            expected_type=_EVENT_TYPE_USER_INPUT_ACCEPTED,
        )
        run_accepted_event = _require_event(
            self._event_log_store.read_event_by_id(transaction, run.accepted_event_id),
            expected_type=_EVENT_TYPE_RUN_ACCEPTED,
        )
        run_started_event = _require_event(
            self._event_log_store.read_event_by_id(transaction, run.started_event_id),
            expected_type=_EVENT_TYPE_RUN_STARTED,
        )
        _validate_current_event_scope(snapshot, user_input_event)
        _validate_current_event_scope(snapshot, run_accepted_event)
        _validate_current_event_scope(snapshot, run_started_event)
        payload = event_payload_object(
            transaction,
            user_input_event,
            payload_label=_EVENT_TYPE_USER_INPUT_ACCEPTED,
        )
        return CurrentRunFacts(
            run=run,
            attempt=attempt,
            dispatch_record=dispatch_record,
            user_input_event=user_input_event,
            run_accepted_event=run_accepted_event,
            run_started_event=run_started_event,
            user_prompt=_required_payload_text(
                payload,
                field_name=_PAYLOAD_FIELD_DISPLAY_TEXT,
            ),
            system_prompt=_optional_payload_text(
                payload,
                field_name=_PAYLOAD_FIELD_SYSTEM_PROMPT,
            ),
            operation_kind=_required_payload_text(
                payload,
                field_name=_PAYLOAD_FIELD_OPERATION_KIND,
            ),
        )


class DurableSessionContinuityProvider:
    """基于 EventLog 的 resume-specific Session continuity provider。"""

    def __init__(self, transaction_runner: HostTransactionRunner) -> None:
        """初始化 provider。

        :param transaction_runner: Host durable transaction runner。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner

    def load_session_continuity(
        self, snapshot: AttemptDispatchSnapshot, current_facts: CurrentRunFacts
    ) -> SessionContinuityView:
        """读取当前 Attempt 之前的 Session continuity messages。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: Session continuity view。
        :raises HostDurableError: durable facts 无法投影时抛出。
        """

        return self._transaction_runner.run_read(
            lambda transaction: self._load_session_continuity_tx(transaction, snapshot, current_facts)
        )

    def _load_session_continuity_tx(
        self,
        transaction: HostTransaction,
        snapshot: AttemptDispatchSnapshot,
        current_facts: CurrentRunFacts,
    ) -> SessionContinuityView:
        """在 read transaction 内读取非历史 continuity facts。

        :param transaction: Host durable transaction。
        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: Session continuity view。
        """

        del snapshot
        return _resume_wait_continuity_from_current_start(
            transaction,
            current_facts,
        )


class NoopMemorySnapshotProvider:
    """Phase 5 no-op memory snapshot provider。"""

    def load_memory_snapshot(
        self, snapshot: AttemptDispatchSnapshot, current_facts: CurrentRunFacts
    ) -> MemorySnapshotView:
        """返回空 memory stable layer。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: 空 MemorySnapshotView。
        """

        del snapshot, current_facts
        return MemorySnapshotView(
            messages=(),
            memory_snapshot_cursor=None,
            policy_digest=None,
            diagnostics=(),
        )


class DurableMemorySnapshotProvider:
    """基于 durable memory projection 的 RunInputBuilder provider。

    本 provider 只读取 durable snapshot 和 EventLog delta；小滞后时返回临时
    inline repair 结果，不写 EventLog、不修改 Run / Attempt 状态，也不推进
    projection checkpoint。

    :param transaction_runner: Host durable transaction runner。
    :param policy: memory projection policy。
    :param consumer_id: memory projection consumer id。
    """

    def __init__(
        self,
        transaction_runner: HostTransactionRunner,
        policy: MemoryProjectionPolicy,
        *,
        consumer_id: str = CONVERSATION_MEMORY_CONSUMER_ID,
    ) -> None:
        """初始化 durable memory provider。

        :param transaction_runner: Host durable transaction runner。
        :param policy: memory projection policy。
        :param consumer_id: memory projection consumer id。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner
        self._policy = policy
        self._policy_digest = digest_memory_projection_policy(policy)
        self._consumer_id = consumer_id
        self._event_log_store = EventLogStore()

    def load_memory_snapshot(
        self, snapshot: AttemptDispatchSnapshot, current_facts: CurrentRunFacts
    ) -> MemorySnapshotView:
        """读取并校验 memory snapshot。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: Memory snapshot view。
        :raises MemoryProjectionRepairRequired: snapshot 缺失、损坏或滞后超过阈值时抛出。
        :raises HostDurableError: EventLog delta 无法读取或投影时抛出。
        """

        return self._transaction_runner.run_read(
            lambda transaction: self._load_memory_snapshot_tx(transaction, snapshot, current_facts)
        )

    def _load_memory_snapshot_tx(
        self,
        transaction: HostTransaction,
        snapshot: AttemptDispatchSnapshot,
        current_facts: CurrentRunFacts,
    ) -> MemorySnapshotView:
        """在 read transaction 内读取 memory snapshot。

        :param transaction: Host durable transaction。
        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: Memory snapshot view。
        :raises MemoryProjectionRepairRequired: 需要 projection repair 时抛出。
        """

        required_event_sequence = _required_memory_event_sequence(current_facts)
        memory_snapshot = self._read_latest_snapshot_or_repair(
            transaction,
            session_id=snapshot.session_id,
            required_event_sequence=required_event_sequence,
        )
        self._validate_snapshot_cursor(
            transaction,
            memory_snapshot=memory_snapshot,
            required_event_sequence=required_event_sequence,
        )
        lag_events = required_event_sequence - memory_snapshot.cursor.checkpoint_event_sequence
        if lag_events < 0:
            self._raise_repair_required(
                session_id=snapshot.session_id,
                reason=MemoryRepairReason.SNAPSHOT_AHEAD_OF_REQUIRED,
                required_event_sequence=required_event_sequence,
                observed_cursor=memory_snapshot.cursor,
            )
        if lag_events <= 0:
            return _memory_snapshot_view(memory_snapshot, current_facts, self._policy)
        if (
            lag_events > self._policy.max_lag_events_for_inline_delta
            or lag_events > self._policy.max_delta_repair_events
        ):
            self._raise_repair_required(
                session_id=snapshot.session_id,
                reason=MemoryRepairReason.SNAPSHOT_LAG_OVER_THRESHOLD,
                required_event_sequence=required_event_sequence,
                observed_cursor=memory_snapshot.cursor,
            )
        repaired = self._repair_inline_delta(
            transaction,
            snapshot=memory_snapshot,
            required_event_sequence=required_event_sequence,
            lag_events=lag_events,
        )
        return _memory_snapshot_view(repaired, current_facts, self._policy)

    def _read_latest_snapshot_or_repair(
        self,
        transaction: HostTransaction,
        *,
        session_id: str,
        required_event_sequence: int,
    ) -> ConversationMemorySnapshotVNext:
        """读取 latest snapshot，缺失或损坏时转成 repair-required。

        :param transaction: Host durable transaction。
        :param session_id: Session id。
        :param required_event_sequence: 本次需要覆盖的 EventLog cursor。
        :returns: durable memory snapshot。
        :raises MemoryProjectionRepairRequired: snapshot 缺失或损坏时抛出。
        """

        try:
            row = read_latest_memory_snapshot_at_or_before(
                transaction,
                session_id=session_id,
                consumer_id=self._consumer_id,
                policy_digest=self._policy_digest,
                max_checkpoint_event_sequence=required_event_sequence,
            )
        except HostDurableError as exc:
            repair_request = MemoryRepairRequest(
                session_id=session_id,
                reason=MemoryRepairReason.SNAPSHOT_DAMAGED,
                required_event_sequence=required_event_sequence,
                observed_cursor=None,
                policy_digest=self._policy_digest,
            )
            raise MemoryProjectionRepairRequired(repair_request) from exc
        if row is None:
            self._raise_repair_required(
                session_id=session_id,
                reason=MemoryRepairReason.SNAPSHOT_MISSING,
                required_event_sequence=required_event_sequence,
                observed_cursor=None,
            )
        return row.snapshot

    def _validate_snapshot_cursor(
        self,
        transaction: HostTransaction,
        *,
        memory_snapshot: ConversationMemorySnapshotVNext,
        required_event_sequence: int,
    ) -> None:
        """校验 snapshot cursor 指向真实 EventLog row。

        :param transaction: Host durable transaction。
        :param memory_snapshot: 已读取的 memory snapshot。
        :param required_event_sequence: 本次需要覆盖的 EventLog cursor。
        :returns: ``None``。
        :raises MemoryProjectionRepairRequired: cursor 损坏时抛出。
        """

        cursor = memory_snapshot.cursor
        if cursor.checkpoint_event_sequence == 0:
            return
        if cursor.checkpoint_event_id is None:
            self._raise_repair_required(
                session_id=memory_snapshot.session_id,
                reason=MemoryRepairReason.SNAPSHOT_DAMAGED,
                required_event_sequence=required_event_sequence,
                observed_cursor=cursor,
            )
        row = read_event_by_id(transaction, cursor.checkpoint_event_id)
        if (
            row is None
            or row.event_sequence != cursor.checkpoint_event_sequence
            or row.session_id != memory_snapshot.session_id
        ):
            self._raise_repair_required(
                session_id=memory_snapshot.session_id,
                reason=MemoryRepairReason.SNAPSHOT_DAMAGED,
                required_event_sequence=required_event_sequence,
                observed_cursor=cursor,
            )

    def _repair_inline_delta(
        self,
        transaction: HostTransaction,
        *,
        snapshot: ConversationMemorySnapshotVNext,
        required_event_sequence: int,
        lag_events: int,
    ) -> ConversationMemorySnapshotVNext:
        """用 EventLog delta 临时修复小滞后 snapshot。

        :param transaction: Host durable transaction。
        :param snapshot: 滞后的 memory snapshot。
        :param required_event_sequence: 需要覆盖到的 EventLog cursor。
        :param lag_events: 滞后事件数。
        :returns: 临时 repaired snapshot。
        :raises MemoryProjectionRepairRequired: delta 无法覆盖 required cursor 时抛出。
        """

        event_filter = event_log_read_filter_from_projection_filter(conversation_memory_projection_event_filter())
        page = self._event_log_store.read_events_after_matching(
            transaction,
            snapshot.cursor.checkpoint_event_sequence,
            event_filter=event_filter,
            limit=lag_events,
            max_event_sequence=required_event_sequence,
            session_id=snapshot.session_id,
        )
        if page.covered_event_sequence != required_event_sequence:
            self._raise_repair_required(
                session_id=snapshot.session_id,
                reason=MemoryRepairReason.SNAPSHOT_DAMAGED,
                required_event_sequence=required_event_sequence,
                observed_cursor=snapshot.cursor,
            )
        required_event_id = page.covered_event_id
        if required_event_id is None:
            self._raise_repair_required(
                session_id=snapshot.session_id,
                reason=MemoryRepairReason.SNAPSHOT_DAMAGED,
                required_event_sequence=required_event_sequence,
                observed_cursor=snapshot.cursor,
            )
        repaired = snapshot
        for row in page.rows:
            repaired = project_conversation_memory_event(
                previous_snapshot=repaired,
                event=_memory_projection_event_from_row(transaction, row),
                policy=self._policy,
                built_at=row.occurred_at,
                consumer_id=self._consumer_id,
            )
        diagnostic = build_inline_delta_repair_diagnostic(
            event_sequence=required_event_sequence,
            policy_digest=self._policy_digest,
        )
        return memory_snapshot_with_cursor_and_diagnostics(
            snapshot=repaired,
            cursor=MemorySnapshotCursor(
                consumer_id=self._consumer_id,
                checkpoint_event_sequence=required_event_sequence,
                checkpoint_event_id=required_event_id,
                session_id=snapshot.session_id,
            ),
            diagnostics=(diagnostic,),
        )

    def _raise_repair_required(
        self,
        *,
        session_id: str,
        reason: MemoryRepairReason,
        required_event_sequence: int,
        observed_cursor: MemorySnapshotCursor | None,
    ) -> NoReturn:
        """抛出结构化 repair-required 错误。

        :param session_id: Session id。
        :param reason: repair reason。
        :param required_event_sequence: 需要覆盖的 EventLog cursor。
        :param observed_cursor: 已观测 cursor。
        :raises MemoryProjectionRepairRequired: 始终抛出。
        """

        raise MemoryProjectionRepairRequired(
            MemoryRepairRequest(
                session_id=session_id,
                reason=reason,
                required_event_sequence=required_event_sequence,
                observed_cursor=observed_cursor,
                policy_digest=self._policy_digest,
            )
        )


class NoopCompactArtifactProvider:
    """Phase 5 no-op compact artifact provider。"""

    def load_compact_artifact(
        self, snapshot: AttemptDispatchSnapshot, current_facts: CurrentRunFacts
    ) -> CompactArtifactView:
        """返回空 compact artifact view。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: 空 CompactArtifactView。
        """

        del snapshot, current_facts
        return CompactArtifactView(
            compaction_event_ref=None,
            compact_artifact_ref=None,
            compact_artifact_digest=None,
        )


class NoopAcceptedToolEvidenceMaterialProvider:
    """不读取 accepted tool evidence 的 material provider。"""

    def load_accepted_tool_evidence_materials(
        self,
        snapshot: AttemptDispatchSnapshot,
        current_facts: CurrentRunFacts,
        memory: MemorySnapshotView,
        compact: CompactArtifactView,
    ) -> tuple[RunInputMaterialBlock, ...]:
        """返回空 evidence material。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :param memory: 当前 memory provider view。
        :param compact: 当前 compact artifact provider view。
        :returns: 空 material tuple。
        """

        del snapshot, current_facts, memory, compact
        return ()


class _NoopProtectedRecentRawTailProvider:
    """不读取 protected recent raw tail 的 provider。"""

    def load_ordinary_raw_tail(
        self,
        snapshot: CompactPipelineAttemptDispatchSnapshot,
        current_facts: CompactPipelineCurrentRunFacts,
        memory: CompactPipelineMemorySnapshotView,
        compact: CompactPipelineCompactArtifactView,
    ) -> CompactPipelineOrdinaryRawTailHandoff:
        """返回空 raw-tail view。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :param memory: 当前 memory provider view。
        :param compact: 当前 compact artifact provider view。
        :returns: 空 protected recent raw tail view。
        """

        del snapshot, current_facts, memory, compact
        return CompactPipelineOrdinaryRawTailHandoff(
            messages=(),
            material_blocks=(),
            source_refs=(),
            material_view_digest=selected_material_view_digest(()),
            selected_recent_window_turn_floor=0,
        )


class _DurableProtectedRecentRawTailProvider:
    """基于 EventLog 读取 post-compaction protected recent raw tail。

    Provider 自己管理 read transaction，并只从
    ``build_pre_dispatch_compact_material_view`` 的 EventLog-backed
    post-compact delta material 选择 raw tail。

    :param transaction_runner: Host durable transaction runner。
    :param policy: memory projection policy，提供 existing selected recent floor。
    """

    def __init__(
        self,
        transaction_runner: HostTransactionRunner,
        policy: MemoryProjectionPolicy,
    ) -> None:
        """初始化 provider。

        :param transaction_runner: Host durable transaction runner。
        :param policy: memory projection policy。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner
        self._event_log_store = EventLogStore()
        self._policy = policy

    def load_ordinary_raw_tail(
        self,
        snapshot: CompactPipelineAttemptDispatchSnapshot,
        current_facts: CompactPipelineCurrentRunFacts,
        memory: CompactPipelineMemorySnapshotView,
        compact: CompactPipelineCompactArtifactView,
    ) -> CompactPipelineOrdinaryRawTailHandoff:
        """读取当前 ordinary dispatch 可注入的 protected raw tail。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :param memory: 当前 memory provider view。
        :param compact: 当前 compact artifact provider view。
        :returns: protected recent raw tail view。
        :raises HostDurableError: compact provenance 或 EventLog material 损坏时抛出。
        """

        del snapshot
        if compact.compact_artifact_ref is None:
            return CompactPipelineOrdinaryRawTailHandoff(
                messages=(),
                material_blocks=(),
                source_refs=(),
                material_view_digest=selected_material_view_digest(()),
                selected_recent_window_turn_floor=0,
            )
        return self._transaction_runner.run_read(
            lambda transaction: self._load_protected_recent_raw_tail_tx(
                transaction,
                current_facts=current_facts,
                memory=memory,
                compact=compact,
            )
        )

    def _load_protected_recent_raw_tail_tx(
        self,
        transaction: HostTransaction,
        *,
        current_facts: CompactPipelineCurrentRunFacts,
        memory: CompactPipelineMemorySnapshotView,
        compact: CompactPipelineCompactArtifactView,
    ) -> CompactPipelineOrdinaryRawTailHandoff:
        """在 read transaction 内读取 protected recent raw tail。

        :param transaction: Host transaction。
        :param current_facts: 当前 Run facts。
        :param memory: 当前 memory provider view。
        :param compact: 当前 compact artifact provider view。
        :returns: protected recent raw tail view。
        :raises HostDurableError: compact artifact 与 current Run 不匹配时抛出。
        """

        compacted_event = _latest_compacted_event_before_attempt(transaction, current_facts)
        if compacted_event is None:
            return CompactPipelineOrdinaryRawTailHandoff(
                messages=(),
                material_blocks=(),
                source_refs=(),
                material_view_digest=selected_material_view_digest(()),
                selected_recent_window_turn_floor=0,
            )
        _validate_loaded_compact_view_matches_event(
            transaction,
            compact=compact,
            compacted_event=compacted_event,
        )
        material_view = build_pre_dispatch_compact_material_view(
            transaction,
            self._event_log_store,
            run=current_facts.run,
            current_display_text=current_facts.user_prompt,
        )
        source_snapshot = compact_pipeline_source_snapshot_from_pre_dispatch_view(
            trigger_source=_compaction_trigger_source_for_compacted_event(
                transaction,
                compacted_event=compacted_event,
            ),
            run=current_facts.run,
            material_view=material_view,
        )
        return select_ordinary_protected_raw_tail(
            source_snapshot=source_snapshot,
            selected_recent_window_turn_floor=(self._policy.selected_recent_window_turn_floor),
            memory=memory,
        )


class DurableAcceptedToolEvidenceMaterialProvider:
    """基于 EventLog 读取当前 Attempt 前 accepted tool evidence material。

    Provider 复用 pre-dispatch compact material view 的 EventLog-backed 语义，
    只做 accepted evidence kind 与已表示 evidence refs 的 whole-block 过滤。

    :param transaction_runner: Host durable transaction runner。
    """

    def __init__(
        self,
        transaction_runner: HostTransactionRunner,
    ) -> None:
        """初始化 provider。

        :param transaction_runner: Host durable transaction runner。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner
        self._event_log_store = EventLogStore()

    def load_accepted_tool_evidence_materials(
        self,
        snapshot: AttemptDispatchSnapshot,
        current_facts: CurrentRunFacts,
        memory: MemorySnapshotView,
        compact: CompactArtifactView,
    ) -> tuple[RunInputMaterialBlock, ...]:
        """读取 EventLog-backed accepted tool evidence material。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :param memory: 当前 memory provider view。
        :param compact: 当前 compact artifact provider view。
        :returns: evidence material blocks。
        :raises HostDurableError: EventLog 或 evidence payload 损坏时抛出。
        """

        return self._transaction_runner.run_read(
            lambda transaction: self._load_accepted_tool_evidence_materials_tx(
                transaction,
                current_facts=current_facts,
                represented_evidence_refs=_represented_evidence_refs(memory, compact),
            )
        )

    def _load_accepted_tool_evidence_materials_tx(
        self,
        transaction: HostTransaction,
        *,
        current_facts: CurrentRunFacts,
        represented_evidence_refs: tuple[str, ...],
    ) -> tuple[RunInputMaterialBlock, ...]:
        """在 read transaction 内读取 accepted evidence material。

        :param transaction: Host transaction。
        :param current_facts: 当前 Run facts。
        :param represented_evidence_refs: 已由 memory / compact 表示的 evidence refs。
        :returns: evidence material blocks。
        """

        material_view = build_pre_dispatch_compact_material_view(
            transaction,
            self._event_log_store,
            run=current_facts.run,
            current_display_text=current_facts.user_prompt,
        )
        represented = frozenset(represented_evidence_refs)
        return tuple(
            block
            for block in material_view.material_blocks
            if block.kind is CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE
            and block.accepted_evidence_id not in represented
        )


class DurableCompactArtifactProvider:
    """基于 EventLog 读取 accepted compact artifact 的 provider。

    :param transaction_runner: Host durable transaction runner。
    """

    def __init__(
        self,
        transaction_runner: HostTransactionRunner,
    ) -> None:
        """初始化 provider。

        :param transaction_runner: Host durable transaction runner。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner

    def load_compact_artifact(
        self, snapshot: AttemptDispatchSnapshot, current_facts: CurrentRunFacts
    ) -> CompactArtifactView:
        """读取当前 Attempt cursor 之前 accepted 的 compact artifact。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: Compact artifact view。
        :raises HostDurableError: compact payload 损坏时抛出。
        """

        return self._transaction_runner.run_read(
            lambda transaction: self._load_compact_artifact_tx(transaction, snapshot, current_facts)
        )

    def _load_compact_artifact_tx(
        self,
        transaction: HostTransaction,
        snapshot: AttemptDispatchSnapshot,
        current_facts: CurrentRunFacts,
    ) -> CompactArtifactView:
        """在 read transaction 内读取 compacted event。

        :param transaction: Host durable transaction。
        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: Compact artifact view。
        """

        del snapshot
        row = _latest_compacted_event_before_attempt(transaction, current_facts)
        if row is None:
            return CompactArtifactView(
                compaction_event_ref=None,
                compact_artifact_ref=None,
                compact_artifact_digest=None,
            )
        payload = resolve_context_compacted_payload(transaction, row)
        try:
            semantic_payload = parse_context_compacted_semantic_payload(payload)
        except (TypeError, ValueError) as exc:
            raise HostDurableError("compact semantic payload is invalid") from exc
        return CompactArtifactView(
            compaction_event_ref=row.event_id,
            compact_artifact_ref=semantic_payload.compact_artifact_ref,
            compact_artifact_digest=_required_text_field(
                payload,
                _PAYLOAD_FIELD_COMPACT_ARTIFACT_DIGEST,
            ),
            represented_evidence_refs=semantic_payload.accepted_evidence_mapping_refs,
        )


class NoopToolSchemaSnapshotProvider:
    """Phase 5 no-tool schema snapshot provider。"""

    def load_tool_schema_snapshot(
        self, snapshot: AttemptDispatchSnapshot, current_facts: CurrentRunFacts
    ) -> ToolSchemaSnapshot:
        """返回空工具 schema 并禁用工具。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: no-tool schema snapshot。
        """

        del snapshot, current_facts
        return ToolSchemaSnapshot(tool_schemas=(), disable_tools=True, tool_runtime_handle=None)


class NoToolExecutor:
    """Phase 5 no-tool 防线 executor。"""

    async def execute(self, request: BatchToolExecutionRequest) -> BatchToolExecutionOutcome:
        """把所有工具调用归一为 Host cancelled outcome。

        :param request: Engine 发起的批式工具执行请求。
        :returns: 与输入 calls 严格双射的 cancelled records。
        """

        return BatchToolExecutionOutcome(
            records=tuple(
                BatchToolExecutionRecord(
                    tool_call_id=call.tool_call_id,
                    outcome=ToolCancelledOutcome(
                        reason=TOOL_CANCELLED_REASON_HOST_CANCELLED,
                        message=_NO_TOOL_CANCEL_MESSAGE,
                        hint=None,
                        meta=None,
                    ),
                )
                for call in request.calls
            )
        )


class NoToolExecutorProvider:
    """Phase 5 no-tool executor provider。"""

    def __init__(self) -> None:
        """初始化 provider。

        :returns: ``None``。
        """

        self._executor = NoToolExecutor()

    def load_tool_executor(self, snapshot: AttemptDispatchSnapshot, current_facts: CurrentRunFacts) -> ToolExecutor:
        """返回 no-tool executor。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: NoToolExecutor。
        """

        del snapshot, current_facts
        return self._executor


class StaticToolRuntimeHandleProvider:
    """显式注入 ToolRuntimeHandle 的 provider。"""

    def __init__(self, tool_runtime_handle: ToolRuntimeHandle) -> None:
        """初始化 provider。

        :param tool_runtime_handle: tool-enabled Attempt 使用的 handle。
        :returns: ``None``。
        """

        self._tool_runtime_handle = tool_runtime_handle

    def load_tool_runtime_handle(
        self, snapshot: AttemptDispatchSnapshot, current_facts: CurrentRunFacts
    ) -> ToolRuntimeHandle:
        """返回构造时注入的 ToolRuntimeHandle。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: ToolRuntimeHandle。
        """

        del snapshot, current_facts
        return self._tool_runtime_handle


class ToolRuntimeSchemaSnapshotProvider:
    """从同一个 ToolRuntimeHandle 投影 tool schemas。"""

    def __init__(self, handle_provider: ToolRuntimeHandleProvider) -> None:
        """初始化 provider。

        :param handle_provider: ToolRuntimeHandle provider。
        :returns: ``None``。
        """

        self._handle_provider = handle_provider

    def load_tool_schema_snapshot(
        self, snapshot: AttemptDispatchSnapshot, current_facts: CurrentRunFacts
    ) -> ToolSchemaSnapshot:
        """读取 tool-enabled schema snapshot。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: 带 ToolRuntimeHandle 的 schema snapshot。
        """

        handle = self._handle_provider.load_tool_runtime_handle(snapshot, current_facts)
        return ToolSchemaSnapshot(
            tool_schemas=handle.tool_schemas,
            disable_tools=False,
            tool_runtime_handle=handle,
        )


class ToolRuntimeExecutorProvider:
    """从同一个 ToolRuntimeHandle 读取 ToolExecutor。"""

    def __init__(self, handle_provider: ToolRuntimeHandleProvider) -> None:
        """初始化 provider。

        :param handle_provider: ToolRuntimeHandle provider。
        :returns: ``None``。
        """

        self._handle_provider = handle_provider

    def load_tool_executor(self, snapshot: AttemptDispatchSnapshot, current_facts: CurrentRunFacts) -> ToolExecutor:
        """读取 tool-enabled ToolExecutor。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: ToolRuntimeHandle 暴露的 executor。
        """

        return self._handle_provider.load_tool_runtime_handle(snapshot, current_facts).tool_executor


class DefaultSceneParameterProvider:
    """默认 system scene / execution target provider。"""

    def build_scene_messages(
        self,
        snapshot: AttemptDispatchSnapshot,
        current_facts: CurrentRunFacts,
        policy_snapshot: PolicySnapshot,
        tool_execution_mode: ToolExecutionMode,
    ) -> tuple[SystemMessage, ...]:
        """构造确定性的 system scene message。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :param policy_snapshot: policy snapshot。
        :param tool_execution_mode: 显式工具执行模式。
        :returns: system message 元组。
        """

        del snapshot
        del current_facts, policy_snapshot
        return _default_scene_messages(tool_execution_mode)


def _default_scene_messages(
    tool_execution_mode: ToolExecutionMode,
) -> tuple[SystemMessage, ...]:
    """构造 ordinary candidate 与 actual request 共享的 scene messages。

    :param tool_execution_mode: frozen tool execution mode。
    :returns: 单条 execution guidance system message。
    :raises TypeError: tool mode 类型非法时抛出。
    """

    if not isinstance(tool_execution_mode, ToolExecutionMode):
        raise TypeError("tool_execution_mode must be ToolExecutionMode")
    content = "\n".join(
        (
            _EXECUTION_GUIDANCE_PREFIX,
            "Use the available context and tools under the current run limits.",
            _tools_scene_line(tool_execution_mode),
        )
    )
    return (SystemMessage(role=AgentMessageRole.SYSTEM, content=content),)


class StaticPolicySnapshotProvider:
    """显式注入 policy snapshot 的 provider。"""

    def __init__(self, policy_snapshot: PolicySnapshot) -> None:
        """初始化 provider。

        :param policy_snapshot: 显式 policy snapshot。
        :returns: ``None``。
        """

        self._policy_snapshot = policy_snapshot

    def load_policy_snapshot(self, snapshot: AttemptDispatchSnapshot, current_facts: CurrentRunFacts) -> PolicySnapshot:
        """返回构造时注入的 policy snapshot。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: policy snapshot。
        :raises HostDurableError: snapshot ref 与注入 policy ref 不一致时抛出。
        """

        del current_facts
        if snapshot.policy_snapshot_ref != self._policy_snapshot.policy_snapshot_ref:
            raise HostDurableError("policy snapshot ref does not match attempt snapshot")
        return self._policy_snapshot


@dataclass(frozen=True, slots=True)
class _PreStartCandidateFacts:
    """pre-start complete candidate 组装所需的 Attempt-free facts。

    :param run: 当前 startable Run row。
    :param user_input_event: 当前 USER_INPUT_ACCEPTED。
    :param run_accepted_event: 当前 RUN_ACCEPTED。
    :param user_prompt: 当前用户输入。
    :param system_prompt: admission system prompt。
    :param operation_kind: admission operation kind。
    """

    run: RunRow
    user_input_event: EventLogRow
    run_accepted_event: EventLogRow
    user_prompt: str
    system_prompt: str | None
    operation_kind: str


def prepare_runner_call_candidate_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    run: RunRow,
    current_input_event: EventLogRow,
    continuity: SessionContinuityView,
    policy_snapshot: PolicySnapshot,
    tool_schemas: tuple[ToolSchema, ...],
    disable_tools: bool,
    tool_execution_mode: ToolExecutionMode,
    memory_projection_policy: MemoryProjectionPolicy,
) -> PreparedRunnerCallCandidate:
    """在调用方 write transaction snapshot 内冻结 pre-start candidate。

    本函数不创建 Attempt/execution/dispatch identity，不写 manifest，也不
    创建 ToolRuntime handle。memory、compact、fallback、scene、selected tool
    schemas 与 actual request 都在这里收敛为一个 immutable candidate。

    :param transaction: 调用方 Host write transaction。
    :param event_log_store: stateless EventLog primitive。
    :param run: 当前 startable Run。
    :param current_input_event: 本次 candidate 唯一 current input fact。
    :param continuity: producer 已冻结的 typed continuation。
    :param policy_snapshot: admission-frozen Engine policy。
    :param tool_schemas: pre-start selected tool schemas。
    :param disable_tools: 是否禁用工具。
    :param tool_execution_mode: frozen tool execution mode。
    :param memory_projection_policy: memory projection policy。
    :returns: identity-free complete candidate。
    :raises MemoryProjectionRepairRequired: memory snapshot 未覆盖 candidate cursor 时抛出。
    :raises HostDurableError: durable input、compact、fallback 或 projection 非法时抛出。
    """

    user_input_event = _require_event(
        current_input_event,
        expected_type=_EVENT_TYPE_USER_INPUT_ACCEPTED,
    )
    if (
        user_input_event.session_id != run.session_id
        or user_input_event.run_id != run.run_id
        or user_input_event.attempt_id is not None
        or user_input_event.execution_id is not None
    ):
        raise HostDurableError("candidate current USER_INPUT_ACCEPTED identity mismatch")
    run_accepted_event = _require_event(
        event_log_store.read_event_by_id(transaction, run.accepted_event_id),
        expected_type=_EVENT_TYPE_RUN_ACCEPTED,
    )
    input_payload = event_payload_object(
        transaction,
        user_input_event,
        payload_label=_EVENT_TYPE_USER_INPUT_ACCEPTED,
    )
    facts = _PreStartCandidateFacts(
        run=run,
        user_input_event=user_input_event,
        run_accepted_event=run_accepted_event,
        user_prompt=_required_payload_text(
            input_payload,
            field_name=_PAYLOAD_FIELD_DISPLAY_TEXT,
        ),
        system_prompt=_optional_payload_text(
            input_payload,
            field_name=_PAYLOAD_FIELD_SYSTEM_PROMPT,
        ),
        operation_kind=_required_payload_text(
            input_payload,
            field_name=_PAYLOAD_FIELD_OPERATION_KIND,
        ),
    )
    candidate_cursor = _candidate_input_cursor(transaction, run.session_id)
    memory = _load_pre_start_memory_snapshot(
        transaction,
        event_log_store,
        facts=facts,
        required_event_sequence=candidate_cursor,
        policy=memory_projection_policy,
    )
    compact, compacted_event = _load_pre_start_compact_artifact(
        transaction,
        event_log_store,
        facts=facts,
        before_event_sequence=candidate_cursor + 1,
    )
    fallback = load_context_fallback_in_transaction(
        transaction,
        event_log_store,
        run_id=run.run_id,
        before_event_sequence=candidate_cursor + 1,
        current_input_ref=user_input_event.event_id,
    )
    if fallback is None:
        raw_tail = _pre_start_protected_recent_raw_tail(
            transaction,
            event_log_store,
            facts=facts,
            memory=memory,
            compact=compact,
            compacted_event=compacted_event,
            memory_projection_policy=memory_projection_policy,
        )
        bounded_context_messages = (
            *memory.messages,
            *raw_tail.messages,
            *continuity.messages,
        )
    else:
        material_blocks = (
            fallback.material_blocks
            if fallback.material_blocks is not None
            else _pre_start_fallback_material_blocks(
                transaction,
                event_log_store,
                facts=facts,
                memory=memory,
                continuity=continuity,
                compact=compact,
            )
        )
        bounded_context_messages = _fallback_context_messages(
            fallback=fallback,
            material_blocks=material_blocks,
        )
    candidate_messages = (
        *_system_prompt_message(facts.system_prompt),
        *_default_scene_messages(tool_execution_mode),
        *bounded_context_messages,
        *_pre_start_current_user_tail(facts, continuity),
    )
    messages = _normalize_ordinary_run_messages(candidate_messages)
    source_refs = _pre_start_candidate_source_refs(
        facts=facts,
        memory=memory,
        compact=compact,
        fallback=fallback,
        continuity=continuity,
    )
    return prepare_runner_call_candidate(
        session_id=run.session_id,
        run_id=run.run_id,
        candidate_input_cursor=candidate_cursor,
        messages=messages,
        tool_schemas=tool_schemas,
        disable_tools=disable_tools,
        tool_execution_mode=tool_execution_mode,
        policy_snapshot=policy_snapshot,
        source_cursor_refs=source_refs,
        memory_snapshot_cursor_ref=memory.memory_snapshot_cursor,
        compact_artifact_refs=_compact_artifact_refs(compact),
        context_fallback_decision_ref=_context_fallback_decision_ref(fallback),
    )


def prepare_runner_call_candidate(
    *,
    session_id: str,
    run_id: str,
    candidate_input_cursor: int,
    messages: tuple[AgentMessage, ...],
    tool_schemas: tuple[ToolSchema, ...],
    disable_tools: bool,
    tool_execution_mode: ToolExecutionMode,
    policy_snapshot: PolicySnapshot,
    source_cursor_refs: tuple[str, ...],
    memory_snapshot_cursor_ref: str | None,
    compact_artifact_refs: tuple[str, ...],
    context_fallback_decision_ref: str | None,
) -> PreparedRunnerCallCandidate:
    """冻结 identity-free complete runner-call candidate。

    本 helper 是 complete messages、selected tool schemas、Engine policy 与
    request serialization semantics 的唯一 digest owner；调用方不得再从
    display text 或 material subset 重建另一个 candidate。

    :param session_id: Session id。
    :param run_id: Host Run id。
    :param candidate_input_cursor: 最大 committed source watermark。
    :param messages: 完整 normalized messages。
    :param tool_schemas: selected tool schemas。
    :param disable_tools: 是否禁用工具。
    :param tool_execution_mode: frozen 工具执行模式。
    :param policy_snapshot: admission-frozen Engine policy。
    :param source_cursor_refs: complete candidate source refs。
    :param memory_snapshot_cursor_ref: memory cursor ref。
    :param compact_artifact_refs: compact artifact refs。
    :param context_fallback_decision_ref: fallback decision ref。
    :returns: identity-free prepared candidate。
    :raises TypeError: typed 参数非法时抛出。
    :raises ValueError: identity/ref/cursor 非法时抛出。
    """

    request_semantics_digest = runner_request_semantics_digest(policy_snapshot)
    projection_body = _prepared_candidate_projection_body(
        session_id=session_id,
        run_id=run_id,
        candidate_input_cursor=candidate_input_cursor,
        messages=messages,
        tool_schemas=tool_schemas,
        disable_tools=disable_tools,
        tool_execution_mode=tool_execution_mode,
        policy_snapshot=policy_snapshot,
        source_cursor_refs=source_cursor_refs,
        memory_snapshot_cursor_ref=memory_snapshot_cursor_ref,
        compact_artifact_refs=compact_artifact_refs,
        context_fallback_decision_ref=context_fallback_decision_ref,
        request_semantics_digest=request_semantics_digest,
    )
    projection_digest = sha256_digest_json(projection_body)
    input_snapshot_digest = sha256_digest_json(
        _prepared_candidate_input_snapshot_body(
            messages=messages,
            tool_schemas=tool_schemas,
            disable_tools=disable_tools,
            tool_execution_mode=tool_execution_mode,
            policy_snapshot=policy_snapshot,
            request_semantics_digest=request_semantics_digest,
        )
    )
    projection_ref = _prepared_candidate_payload_ref(projection_digest)
    return PreparedRunnerCallCandidate(
        session_id=session_id,
        run_id=run_id,
        candidate_input_cursor=candidate_input_cursor,
        candidate_input_projection_ref=projection_ref,
        candidate_input_projection_digest=projection_digest,
        input_snapshot_digest=input_snapshot_digest,
        messages=messages,
        tool_schemas=tool_schemas,
        disable_tools=disable_tools,
        tool_execution_mode=tool_execution_mode,
        policy_snapshot=policy_snapshot,
        source_cursor_refs=source_cursor_refs,
        memory_snapshot_cursor_ref=memory_snapshot_cursor_ref,
        compact_artifact_refs=compact_artifact_refs,
        context_fallback_decision_ref=context_fallback_decision_ref,
        request_semantics_digest=request_semantics_digest,
    )


def estimate_prepared_runner_call_candidate(
    candidate: PreparedRunnerCallCandidate,
    policy: ContextBudgetPolicy,
) -> BudgetEstimate:
    """对 complete candidate 调用唯一 conservative estimator。

    :param candidate: identity-free complete candidate。
    :param policy: Host context budget policy。
    :returns: complete candidate conservative estimate。
    :raises TypeError: candidate 或 policy 类型非法时抛出。
    :raises ValueError: estimator 输入无法 canonical encode 时抛出。
    """

    if not isinstance(candidate, PreparedRunnerCallCandidate):
        raise TypeError("candidate must be PreparedRunnerCallCandidate")
    return estimate_context_budget(
        policy,
        _budget_estimate_input_from_prepared_candidate(candidate),
    )


def resolve_prepared_runner_call_context_anchor_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    candidate: PreparedRunnerCallCandidate,
    context_window_size: int,
    candidate_input_cursor: int | None = None,
) -> ContextAnchorResolution:
    """为complete prepared candidate构造typed query并解析durable anchor。

    本helper只把RunInput owner已冻结的provider/model/request semantics/input digest
    映射成resolver query；它不计算prediction、threshold或action。

    :param transaction: 调用方现有Host transaction。
    :param event_log_store: stateless EventLog primitive。
    :param candidate: complete prepared candidate。
    :param context_window_size: frozen context window。
    :param candidate_input_cursor: 可选scan上界；省略时使用candidate source watermark。
    :returns: compatible anchor或closed fallback reason。
    :raises TypeError: candidate或cursor类型非法时抛出。
    :raises ValueError: query atom范围或digest非法时抛出。
    """

    if not isinstance(candidate, PreparedRunnerCallCandidate):
        raise TypeError("candidate must be PreparedRunnerCallCandidate")
    scan_cursor = candidate.candidate_input_cursor if candidate_input_cursor is None else candidate_input_cursor
    return resolve_context_anchor(
        transaction,
        event_log_store,
        ContextAnchorQuery(
            session_id=candidate.session_id,
            current_run_id=candidate.run_id,
            candidate_input_cursor=scan_cursor,
            candidate_input_digest=candidate.input_snapshot_digest,
            provider=candidate.policy_snapshot.runner_spec.provider,
            model=candidate.policy_snapshot.runner_spec.model,
            context_window_size=context_window_size,
            estimator_contract=CONTEXT_ESTIMATOR_CONTRACT,
            request_semantics_digest=candidate.request_semantics_digest,
        ),
    )


def continuation_runner_call_sizing_snapshot(
    candidate: PreparedRunnerCallCandidate,
    source_sizing: RunnerCallSizingSnapshot,
) -> RunnerCallSizingSnapshot:
    """按 source compatibility atoms冻结新 continuation candidate sizing。

    continuation 不读取当前 context policy；complete source只复用其
    window/policy/provider/model/estimator compatibility atoms，并对新 candidate
    执行同一无 policy conservative estimator。unavailable source保留原原因。

    :param candidate: 本次 continuation complete candidate。
    :param source_sizing: source pre-start manifest 的 strict sizing snapshot。
    :returns: stage 为 ``CONTINUATION`` 的 complete 或 unavailable snapshot。
    :raises HostDurableError: source atoms与candidate或当前estimator contract不一致时抛出。
    """

    if source_sizing.status is RunnerCallSizingStatus.UNAVAILABLE:
        if source_sizing.reason is None:
            raise HostDurableError("continuation source unavailable reason is missing")
        return unavailable_runner_call_sizing_snapshot(
            source_sizing.reason,
            sizing_stage=ContextSizingStage.CONTINUATION,
        )
    if source_sizing.status is not RunnerCallSizingStatus.COMPLETE:
        raise HostDurableError("continuation source sizing is not complete")
    estimator_id = source_sizing.estimator_id
    estimator_version = source_sizing.estimator_version
    provider = source_sizing.provider
    model = source_sizing.model
    if (
        estimator_id is None
        or estimator_id != CONTEXT_ESTIMATOR_CONTRACT.estimator_id
        or estimator_version is None
        or estimator_version != CONTEXT_ESTIMATOR_CONTRACT.estimator_version
        or source_sizing.context_window_size is None
        or provider is None
        or provider != candidate.policy_snapshot.runner_spec.provider
        or model is None
        or model != candidate.policy_snapshot.runner_spec.model
        or source_sizing.request_semantics_digest != candidate.request_semantics_digest
        or source_sizing.policy_ref is None
        or source_sizing.policy_snapshot_digest is None
    ):
        raise HostDurableError("continuation source sizing compatibility mismatch")
    tokens, estimator_digest = estimate_context_input(_budget_estimate_input_from_prepared_candidate(candidate))
    return complete_runner_call_sizing_snapshot(
        sizing_stage=ContextSizingStage.CONTINUATION,
        estimator_id=estimator_id,
        estimator_version=estimator_version,
        estimator_digest=estimator_digest,
        conservative_input_tokens=tokens,
        context_window_size=source_sizing.context_window_size,
        provider=provider,
        model=model,
        request_semantics_digest=candidate.request_semantics_digest,
        input_snapshot_digest=candidate.input_snapshot_digest,
        policy_ref=source_sizing.policy_ref,
        policy_snapshot_digest=source_sizing.policy_snapshot_digest,
    )


def _budget_estimate_input_from_prepared_candidate(
    candidate: PreparedRunnerCallCandidate,
) -> BudgetEstimateInput:
    """把 complete candidate 投影为层内中性的 conservative estimator 输入。

    每条实际 message 只产生一次 message overhead；message 正文作为文本
    fragment，assistant tool calls / reasoning 与 tool-call identity 作为独立
    canonical JSON atom，避免正文重复计数。Engine message 联合只在
    RunInput owner 内解释，context budget owner 只消费中性 fragments。

    :param candidate: identity-free complete candidate。
    :returns: 与 actual request 同源的 estimator input。
    :raises TypeError: candidate message 或 tool schema 类型非法时抛出。
    """

    message_fragments: list[BudgetTextFragment] = []
    json_fragments: list[BudgetJsonFragment] = []
    for index, message in enumerate(candidate.messages):
        message_fragments.append(
            BudgetTextFragment(
                fragment_ref=(f"candidate-message:{index}:{message.role.value}"),
                text=_candidate_budget_message_text(message),
            )
        )
        structured_atom = _candidate_budget_structured_atom(message)
        if structured_atom is not None:
            json_fragments.append(
                BudgetJsonFragment(
                    fragment_ref=(f"candidate-message-structured:{index}"),
                    value=structured_atom,
                )
            )
    tool_fragments = tuple(
        BudgetJsonFragment(
            fragment_ref=f"candidate-tool-schema:{index}",
            value=_tool_schema_json(schema),
        )
        for index, schema in enumerate(candidate.tool_schemas)
    )
    return BudgetEstimateInput(
        session_id=candidate.session_id,
        run_id=candidate.run_id,
        message_fragments=tuple(message_fragments),
        json_fragments=tuple(json_fragments),
        tool_schema_fragments=tool_fragments,
        compact_artifact_refs=candidate.compact_artifact_refs,
        memory_snapshot_cursor=None,
        current_prompt_ref=(candidate.source_cursor_refs[-1] if candidate.source_cursor_refs else None),
        input_snapshot_digest=candidate.input_snapshot_digest,
    )


def _candidate_budget_message_text(message: AgentMessage) -> str:
    """读取 complete candidate message 的业务文本。

    :param message: typed Agent message。
    :returns: message 正文；assistant 空正文返回空串。
    :raises TypeError: 遇到封闭联合外消息类型时抛出。
    """

    if isinstance(message, SystemMessage | UserMessage | ToolMessage):
        return message.content
    if isinstance(message, AssistantMessage):
        return "" if message.content is None else message.content
    raise TypeError("candidate message type is unsupported")


def _candidate_budget_structured_atom(
    message: AgentMessage,
) -> Mapping[str, JsonValue] | None:
    """投影 message 中未进入正文的 provider-neutral structured atoms。

    :param message: typed Agent message。
    :returns: canonical JSON atom；无 structured atom 时为 ``None``。
    :raises TypeError: 遇到封闭联合外消息类型时抛出。
    """

    if isinstance(message, SystemMessage | UserMessage):
        return None
    if isinstance(message, ToolMessage):
        return {
            "role": message.role.value,
            "tool_call_id": message.tool_call_id,
        }
    if isinstance(message, AssistantMessage):
        if message.reasoning_content is None and not message.tool_calls:
            return None
        return {
            "role": message.role.value,
            "reasoning_content": message.reasoning_content,
            "tool_calls": [
                {
                    "id": call.id,
                    "name": call.name,
                    "arguments": dict(call.arguments),
                }
                for call in message.tool_calls
            ],
        }
    raise TypeError("candidate message type is unsupported")


def runner_request_semantics_digest(policy_snapshot: PolicySnapshot) -> str:
    """计算 provider-neutral Runner request serialization semantics digest。

    endpoint、API key、headers、timeout 与 retry 不进入 digest；provider/model
    仍作为 manifest 显式 compatibility atoms。

    :param policy_snapshot: admission-frozen Engine policy snapshot。
    :returns: canonical sha256 digest。
    :raises TypeError: policy 或 provider extension 类型非法时抛出。
    """

    if not isinstance(policy_snapshot, PolicySnapshot):
        raise TypeError("policy_snapshot must be PolicySnapshot")
    spec = policy_snapshot.runner_spec
    return sha256_digest_json(
        {
            "runner_input_serializer_schema_version": (RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION),
            "runner_call_input_projection_schema_version": (RUNNER_CALL_INPUT_PROJECTION_SCHEMA_VERSION),
            "runner_options": runner_options_json(policy_snapshot.runner_options),
            "provider_request": provider_request_json(spec.provider_request),
            "supports_tool_calling": spec.supports_tool_calling,
            "supports_streaming": spec.supports_streaming,
            "supports_stream_usage": spec.supports_stream_usage,
            "client_correlation_policy": spec.client_correlation_policy.value,
        }
    )


def agent_run_request_from_prepared_candidate(
    *,
    candidate: PreparedRunnerCallCandidate,
    attempt_snapshot: AttemptDispatchSnapshot,
    tool_executor: ToolExecutor,
) -> AgentRunRequest:
    """从 frozen candidate 构造 actual AgentRunRequest。

    本 helper 不调用任何 durable/material provider，不重新 assemble messages
    或 tool schemas；它只复核 candidate/request identity 后绑定 Attempt runtime
    handles。

    :param candidate: pre-start frozen complete candidate。
    :param attempt_snapshot: allow 后创建的 Attempt dispatch snapshot。
    :param tool_executor: 与 frozen selected schema 同源的 runtime executor。
    :returns: actual Engine AgentRunRequest。
    :raises HostDurableError: Run/session/policy/request digest 不匹配时抛出。
    """

    if candidate.session_id != attempt_snapshot.session_id:
        raise HostDurableError("frozen candidate session identity mismatch")
    if candidate.run_id != attempt_snapshot.run_id:
        raise HostDurableError("frozen candidate Run identity mismatch")
    if candidate.policy_snapshot.policy_snapshot_ref != attempt_snapshot.policy_snapshot_ref:
        raise HostDurableError("frozen candidate policy identity mismatch")
    if runner_request_semantics_digest(candidate.policy_snapshot) != candidate.request_semantics_digest:
        raise HostDurableError("frozen candidate request semantics mismatch")
    rebuilt = prepare_runner_call_candidate(
        session_id=candidate.session_id,
        run_id=candidate.run_id,
        candidate_input_cursor=candidate.candidate_input_cursor,
        messages=candidate.messages,
        tool_schemas=candidate.tool_schemas,
        disable_tools=candidate.disable_tools,
        tool_execution_mode=candidate.tool_execution_mode,
        policy_snapshot=candidate.policy_snapshot,
        source_cursor_refs=candidate.source_cursor_refs,
        memory_snapshot_cursor_ref=candidate.memory_snapshot_cursor_ref,
        compact_artifact_refs=candidate.compact_artifact_refs,
        context_fallback_decision_ref=(candidate.context_fallback_decision_ref),
    )
    if rebuilt.input_snapshot_digest != candidate.input_snapshot_digest:
        raise HostDurableError("frozen candidate input snapshot digest mismatch")
    return AgentRunRequest(
        run_id=attempt_snapshot.run_id,
        session_id=attempt_snapshot.session_id,
        attempt_id=attempt_snapshot.attempt_id,
        execution_id=attempt_snapshot.execution_id,
        messages=candidate.messages,
        disable_tools=candidate.disable_tools,
        runner_spec=candidate.policy_snapshot.runner_spec,
        runner_options=candidate.policy_snapshot.runner_options,
        agent_policy=candidate.policy_snapshot.agent_policy,
        tool_schemas=candidate.tool_schemas,
        tool_executor=tool_executor,
        cancellation_token=attempt_snapshot.cancellation_token,
    )


def load_run_input_policy_snapshot_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    run: RunRow,
) -> PolicySnapshot:
    """从 source Run 的 exact input fact strict 重建 Engine policy。

    :param transaction: 调用方现有 Host transaction。
    :param event_log_store: EventLog primitive。
    :param run: source Run row。
    :returns: input fact 冻结的 typed policy snapshot。
    :raises HostDurableError: event type、Session/Run identity 或 execution config
        不完整、损坏时抛出。
    """

    event = event_log_store.read_event_by_id(
        transaction,
        run.input_event_id,
    )
    if (
        event is None
        or event.event_id != run.input_event_id
        or event.event_type != _EVENT_TYPE_USER_INPUT_ACCEPTED
        or event.session_id != run.session_id
        or event.run_id != run.run_id
        or event.attempt_id is not None
        or event.execution_id is not None
    ):
        raise HostDurableError("source Run exact USER_INPUT_ACCEPTED fact is invalid")
    payload = event_payload_object(
        transaction,
        event,
        payload_label=_EVENT_TYPE_USER_INPUT_ACCEPTED,
    )
    execution_config = payload.get("effective_execution_config")
    if execution_config is None:
        raise HostDurableError("source Run effective execution config is missing")
    snapshot = effective_execution_snapshot_from_json(execution_config)
    return PolicySnapshot(
        runner_spec=snapshot.runner_spec,
        runner_options=snapshot.runner_options,
        agent_policy=snapshot.agent_policy,
        policy_snapshot_ref=snapshot.policy_snapshot_ref,
    )


def load_prepared_runner_call_source_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    run_id: str,
    attempt_id: str,
    execution_id: str,
) -> PreparedRunnerCallSource:
    """在调用方 transaction 内 strict-load source manifest/candidate 超集。

    :param transaction: 调用方现有 Host transaction。
    :param event_log_store: EventLog primitive。
    :param run_id: source Host Run id。
    :param attempt_id: source Attempt id。
    :param execution_id: source execution id。
    :returns: digest-verified source manifest、event 与 candidate。
    :raises PreparedRunnerCallSourceError: strict source owner 以 typed category
        报告 tool schema、policy 或 request semantics 不可用。
    """

    run = read_run_by_id(transaction, run_id)
    if run is None:
        raise PreparedRunnerCallSourceError(
            PreparedRunnerCallSourceFailureCategory.TOOL_SCHEMA,
            "prepared runner-call source Run is missing",
        )
    try:
        event = _find_existing_runner_call_manifest_event(
            transaction,
            run=run,
            attempt_id=attempt_id,
            execution_id=execution_id,
        )
    except HostDurableError as exc:
        raise PreparedRunnerCallSourceError(
            PreparedRunnerCallSourceFailureCategory.TOOL_SCHEMA,
            "prepared runner-call manifest identity is invalid",
        ) from exc
    if event is None:
        raise PreparedRunnerCallSourceError(
            PreparedRunnerCallSourceFailureCategory.TOOL_SCHEMA,
            "prepared runner-call manifest is missing before dispatch",
        )
    try:
        hot = parse_runner_call_hot_payload(_payload_object(event))
        if hot.host_run_id != run_id or hot.attempt_id != attempt_id or hot.execution_id != execution_id:
            raise HostDurableError("prepared manifest hot identity mismatch")
        manifest_json = sqlite_payload_object(
            transaction,
            payload_ref=hot.manifest_payload_ref,
            payload_digest=hot.manifest_digest,
            payload_label="prepared runner-call manifest",
        )
        manifest = parse_runner_call_manifest(
            manifest_json,
            hot_payload=hot,
        )
        if (
            manifest.identity.iteration_id is not None
            or manifest.identity.iteration_index is not None
            or manifest.compactor_identity is not None
        ):
            raise HostDurableError("prepared runner-call source is not a pre-start manifest")
    except (HostDurableError, TypeError, ValueError) as exc:
        raise PreparedRunnerCallSourceError(
            PreparedRunnerCallSourceFailureCategory.TOOL_SCHEMA,
            "prepared runner-call manifest is invalid",
        ) from exc
    candidate_ref = _prepared_candidate_payload_ref(manifest.input_projection_digest)
    try:
        candidate_json = sqlite_payload_object(
            transaction,
            payload_ref=candidate_ref,
            payload_digest=manifest.input_projection_digest,
            payload_label="prepared runner-call candidate",
        )
    except HostDurableError as exc:
        raise PreparedRunnerCallSourceError(
            PreparedRunnerCallSourceFailureCategory.TOOL_SCHEMA,
            "prepared runner-call candidate payload is unavailable",
        ) from exc
    try:
        tool_facts = _prepared_source_tool_facts(
            candidate_json,
            run=run,
        )
        _validate_prepared_tool_snapshot(
            transaction,
            manifest.source_refs.tool_schema_snapshot_refs,
            tool_schemas=tool_facts.tool_schemas,
            disable_tools=tool_facts.disable_tools,
        )
    except (HostDurableError, TypeError, ValueError) as exc:
        raise PreparedRunnerCallSourceError(
            PreparedRunnerCallSourceFailureCategory.TOOL_SCHEMA,
            "prepared runner-call tool snapshot is invalid",
        ) from exc
    try:
        policy_snapshot = load_run_input_policy_snapshot_in_transaction(
            transaction,
            event_log_store,
            run=run,
        )
    except (HostDurableError, TypeError, ValueError) as exc:
        raise PreparedRunnerCallSourceError(
            PreparedRunnerCallSourceFailureCategory.POLICY,
            "prepared runner-call source policy is unavailable",
        ) from exc
    _validate_prepared_source_policy_fields(
        candidate_json,
        policy_snapshot=policy_snapshot,
    )
    _validate_prepared_source_request_fields(
        candidate_json,
        policy_snapshot=policy_snapshot,
    )
    try:
        candidate = _prepared_candidate_from_json(
            candidate_json,
            policy_snapshot=policy_snapshot,
        )
        if candidate.run_id != run_id:
            raise HostDurableError("prepared candidate Run identity mismatch")
        if (
            candidate.candidate_input_projection_ref != candidate_ref
            or candidate.candidate_input_projection_digest != manifest.input_projection_digest
        ):
            raise HostDurableError("prepared candidate manifest projection mismatch")
    except (HostDurableError, TypeError, ValueError) as exc:
        raise PreparedRunnerCallSourceError(
            PreparedRunnerCallSourceFailureCategory.TOOL_SCHEMA,
            "prepared runner-call candidate is invalid",
        ) from exc
    sizing = manifest.sizing_snapshot
    if sizing.status is RunnerCallSizingStatus.NOT_APPLICABLE:
        raise PreparedRunnerCallSourceError(
            PreparedRunnerCallSourceFailureCategory.POLICY,
            "prepared runner-call source sizing is not applicable",
        )
    if (
        (sizing.input_snapshot_digest is not None and sizing.input_snapshot_digest != candidate.input_snapshot_digest)
        or (
            sizing.request_semantics_digest is not None
            and sizing.request_semantics_digest != candidate.request_semantics_digest
        )
        or (sizing.provider is not None and sizing.provider != candidate.policy_snapshot.runner_spec.provider)
        or (sizing.model is not None and sizing.model != candidate.policy_snapshot.runner_spec.model)
    ):
        raise PreparedRunnerCallSourceError(
            PreparedRunnerCallSourceFailureCategory.REQUEST_SEMANTICS,
            "prepared runner-call source request semantics are inconsistent",
        )
    return PreparedRunnerCallSource(
        manifest_event=event,
        manifest=manifest,
        candidate=candidate,
    )


def _prepared_source_tool_facts(
    candidate_json: Mapping[str, JsonValue],
    *,
    run: RunRow,
) -> _PreparedSourceToolFacts:
    """先于 policy 读取验证 candidate 的 policy-independent tool facts。

    此 helper 只消费 candidate 自身及 source Run identity；它复用 complete
    parser 的字段解析 primitives，但不读取或推断 policy。这样 tool 与
    policy 同时损坏时，strict owner 仍稳定返回 ``TOOL_SCHEMA``。

    :param candidate_json: digest-verified durable prepared candidate JSON。
    :param run: source Run durable row。
    :returns: exact selected schemas、disable flag 与 tool mode。
    :raises HostDurableError: candidate shape、identity、source refs 或 tool
        facts 非法时抛出。
    """

    fields = frozenset(candidate_json)
    if not fields.issubset(_PREPARED_CANDIDATE_FIELDS) or not _PREPARED_CANDIDATE_POLICY_INDEPENDENT_FIELDS.issubset(
        fields
    ):
        raise HostDurableError("prepared candidate policy-independent fields are invalid")
    if (
        _candidate_required_text(candidate_json, "schema_version") != _PREPARED_CANDIDATE_SCHEMA_VERSION
        or _candidate_required_text(candidate_json, "session_id") != run.session_id
        or _candidate_required_text(candidate_json, "host_run_id") != run.run_id
    ):
        raise HostDurableError("prepared candidate policy-independent identity is invalid")
    cursor = candidate_json.get("candidate_input_cursor")
    if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0:
        raise HostDurableError("prepared candidate input cursor is invalid")
    _candidate_messages(candidate_json.get("messages"))
    tool_schemas = _candidate_tool_schemas(candidate_json.get("tool_schemas"))
    disable_tools = candidate_json.get("disable_tools")
    if not isinstance(disable_tools, bool):
        raise HostDurableError("prepared candidate disable_tools is invalid")
    try:
        tool_execution_mode = ToolExecutionMode(
            _candidate_required_text(
                candidate_json,
                "tool_execution_mode",
            )
        )
    except ValueError as exc:
        raise HostDurableError("prepared candidate tool_execution_mode is invalid") from exc
    if tool_execution_mode is ToolExecutionMode.TOOL_ENABLED:
        if disable_tools:
            raise HostDurableError("tool-enabled candidate must not disable tools")
    elif not disable_tools or tool_schemas:
        raise HostDurableError("no-tool candidate must disable tools and omit schemas")
    _candidate_text_tuple(
        candidate_json.get("source_cursor_refs"),
        field_name="source_cursor_refs",
    )
    _candidate_optional_text(
        candidate_json.get("memory_snapshot_cursor_ref"),
        field_name="memory_snapshot_cursor_ref",
    )
    _candidate_text_tuple(
        candidate_json.get("compact_artifact_refs"),
        field_name="compact_artifact_refs",
    )
    _candidate_optional_text(
        candidate_json.get("context_fallback_decision_ref"),
        field_name="context_fallback_decision_ref",
    )
    return _PreparedSourceToolFacts(
        tool_schemas=tool_schemas,
        disable_tools=disable_tools,
        tool_execution_mode=tool_execution_mode,
    )


def _validate_prepared_source_policy_fields(
    candidate_json: Mapping[str, JsonValue],
    *,
    policy_snapshot: PolicySnapshot,
) -> None:
    """在完整 candidate 解析前校验 policy-owned 字段。

    :param candidate_json: durable prepared candidate JSON。
    :param policy_snapshot: exact input fact 恢复的 typed policy。
    :returns: ``None``。
    :raises PreparedRunnerCallSourceError: policy ref/digest 缺失或漂移时抛出。
    """

    try:
        valid = _candidate_required_text(
            candidate_json, "policy_snapshot_ref"
        ) == policy_snapshot.policy_snapshot_ref and _candidate_required_text(
            candidate_json,
            "policy_snapshot_digest",
        ) == _engine_policy_snapshot_digest(policy_snapshot)
    except HostDurableError as exc:
        raise PreparedRunnerCallSourceError(
            PreparedRunnerCallSourceFailureCategory.POLICY,
            "prepared runner-call candidate policy fields are unavailable",
        ) from exc
    if not valid:
        raise PreparedRunnerCallSourceError(
            PreparedRunnerCallSourceFailureCategory.POLICY,
            "prepared runner-call candidate policy does not match exact input fact",
        )


def _validate_prepared_source_request_fields(
    candidate_json: Mapping[str, JsonValue],
    *,
    policy_snapshot: PolicySnapshot,
) -> None:
    """在完整 candidate 解析前校验 request-semantics-owned 字段。

    :param candidate_json: durable prepared candidate JSON。
    :param policy_snapshot: exact input fact 恢复的 typed policy。
    :returns: ``None``。
    :raises PreparedRunnerCallSourceError: request digest 或 estimator contract
        缺失、损坏或漂移时抛出。
    """

    try:
        valid = (
            _candidate_required_text(
                candidate_json,
                "request_semantics_digest",
            )
            == runner_request_semantics_digest(policy_snapshot)
            and _candidate_required_text(candidate_json, "estimator_id") == CONTEXT_ESTIMATOR_CONTRACT.estimator_id
            and _candidate_required_text(candidate_json, "estimator_version")
            == CONTEXT_ESTIMATOR_CONTRACT.estimator_version
        )
    except HostDurableError as exc:
        raise PreparedRunnerCallSourceError(
            PreparedRunnerCallSourceFailureCategory.REQUEST_SEMANTICS,
            "prepared runner-call request semantics fields are unavailable",
        ) from exc
    if not valid:
        raise PreparedRunnerCallSourceError(
            PreparedRunnerCallSourceFailureCategory.REQUEST_SEMANTICS,
            "prepared runner-call request semantics do not match current contract",
        )


def load_prepared_runner_call_candidate_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    run_id: str,
    attempt_id: str,
    execution_id: str,
    policy_snapshot: PolicySnapshot,
) -> PreparedRunnerCallCandidate:
    """strict-load frozen candidate 并核对 worker caller policy。

    :param transaction: 调用方现有 Host transaction。
    :param event_log_store: EventLog primitive。
    :param run_id: source Host Run id。
    :param attempt_id: source Attempt id。
    :param execution_id: source execution id。
    :param policy_snapshot: worker 从 exact input fact读取的 caller policy。
    :returns: digest-verified identity-free candidate。
    :raises HostDurableError: source 或 caller policy identity 不一致时抛出。
    """

    source = load_prepared_runner_call_source_in_transaction(
        transaction,
        event_log_store,
        run_id=run_id,
        attempt_id=attempt_id,
        execution_id=execution_id,
    )
    candidate = source.candidate
    if (
        candidate.policy_snapshot != policy_snapshot
        or candidate.policy_snapshot.policy_snapshot_ref != policy_snapshot.policy_snapshot_ref
        or _engine_policy_snapshot_digest(candidate.policy_snapshot) != _engine_policy_snapshot_digest(policy_snapshot)
        or candidate.request_semantics_digest != runner_request_semantics_digest(policy_snapshot)
    ):
        raise HostDurableError("prepared candidate caller policy identity mismatch")
    return candidate


def load_prepared_runner_call_candidate(
    transaction_runner: HostTransactionRunner,
    *,
    attempt_snapshot: AttemptDispatchSnapshot,
    policy_snapshot: PolicySnapshot,
) -> PreparedRunnerCallCandidate:
    """从 pre-start manifest 读取并验证 actual request 的 frozen candidate。

    :param transaction_runner: Host transaction runner。
    :param attempt_snapshot: 当前 Attempt dispatch snapshot。
    :param policy_snapshot: admission-frozen policy snapshot。
    :returns: digest-verified identity-free candidate。
    :raises HostDurableError: manifest、candidate、tool snapshot 或 policy 不一致时抛出。
    """

    return transaction_runner.run_read(
        lambda transaction: load_prepared_runner_call_candidate_in_transaction(
            transaction,
            EventLogStore(),
            run_id=attempt_snapshot.run_id,
            attempt_id=attempt_snapshot.attempt_id,
            execution_id=attempt_snapshot.execution_id,
            policy_snapshot=policy_snapshot,
        )
    )


def _prepared_candidate_from_json(
    value: Mapping[str, JsonValue],
    *,
    policy_snapshot: PolicySnapshot,
) -> PreparedRunnerCallCandidate:
    """从 strict Host-private JSON 重建 frozen candidate。

    :param value: candidate payload JSON。
    :param policy_snapshot: admission-frozen typed policy。
    :returns: 重建且重新摘要验证后的 candidate。
    :raises HostDurableError: schema、字段或 digest 语义非法时抛出。
    """

    if frozenset(value) != _PREPARED_CANDIDATE_FIELDS:
        raise HostDurableError("prepared candidate payload fields are invalid")
    if _candidate_required_text(value, "schema_version") != _PREPARED_CANDIDATE_SCHEMA_VERSION:
        raise HostDurableError("prepared candidate schema version is unsupported")
    if _candidate_required_text(
        value, "policy_snapshot_ref"
    ) != policy_snapshot.policy_snapshot_ref or _candidate_required_text(
        value, "policy_snapshot_digest"
    ) != _engine_policy_snapshot_digest(policy_snapshot):
        raise HostDurableError("prepared candidate policy snapshot mismatch")
    if _candidate_required_text(value, "request_semantics_digest") != runner_request_semantics_digest(policy_snapshot):
        raise HostDurableError("prepared candidate request semantics mismatch")
    if (
        _candidate_required_text(value, "estimator_id") != CONTEXT_ESTIMATOR_CONTRACT.estimator_id
        or _candidate_required_text(value, "estimator_version") != CONTEXT_ESTIMATOR_CONTRACT.estimator_version
    ):
        raise HostDurableError("prepared candidate estimator contract mismatch")
    cursor = value.get("candidate_input_cursor")
    if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0:
        raise HostDurableError("prepared candidate input cursor is invalid")
    disable_tools = value.get("disable_tools")
    if not isinstance(disable_tools, bool):
        raise HostDurableError("prepared candidate disable_tools is invalid")
    mode_value = _candidate_required_text(value, "tool_execution_mode")
    try:
        tool_execution_mode = ToolExecutionMode(mode_value)
    except ValueError as exc:
        raise HostDurableError("prepared candidate tool_execution_mode is invalid") from exc
    candidate = prepare_runner_call_candidate(
        session_id=_candidate_required_text(value, "session_id"),
        run_id=_candidate_required_text(value, "host_run_id"),
        candidate_input_cursor=cursor,
        messages=_candidate_messages(value.get("messages")),
        tool_schemas=_candidate_tool_schemas(value.get("tool_schemas")),
        disable_tools=disable_tools,
        tool_execution_mode=tool_execution_mode,
        policy_snapshot=policy_snapshot,
        source_cursor_refs=_candidate_text_tuple(
            value.get("source_cursor_refs"),
            field_name="source_cursor_refs",
        ),
        memory_snapshot_cursor_ref=_candidate_optional_text(
            value.get("memory_snapshot_cursor_ref"),
            field_name="memory_snapshot_cursor_ref",
        ),
        compact_artifact_refs=_candidate_text_tuple(
            value.get("compact_artifact_refs"),
            field_name="compact_artifact_refs",
        ),
        context_fallback_decision_ref=_candidate_optional_text(
            value.get("context_fallback_decision_ref"),
            field_name="context_fallback_decision_ref",
        ),
    )
    if sha256_digest_json(value) != candidate.candidate_input_projection_digest:
        raise HostDurableError("prepared candidate payload digest mismatch")
    return candidate


def _candidate_messages(value: JsonValue | None) -> tuple[AgentMessage, ...]:
    """解析 candidate 的 exact ordered messages。

    :param value: messages JSON。
    :returns: typed Agent messages。
    :raises HostDurableError: message shape 或 role 非法时抛出。
    """

    if not isinstance(value, list):
        raise HostDurableError("prepared candidate messages must be array")
    messages: list[AgentMessage] = []
    for expected_index, item in enumerate(value):
        mapping = _candidate_mapping(item, field_name="message")
        index = mapping.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or index != expected_index:
            raise HostDurableError("prepared candidate message index is invalid")
        role = _candidate_required_text(mapping, "role")
        if role == AgentMessageRole.SYSTEM.value:
            messages.append(
                SystemMessage(
                    role=AgentMessageRole.SYSTEM,
                    content=_candidate_required_text(mapping, "content"),
                )
            )
        elif role == AgentMessageRole.USER.value:
            messages.append(
                UserMessage(
                    role=AgentMessageRole.USER,
                    content=_candidate_required_text(mapping, "content"),
                )
            )
        elif role == AgentMessageRole.TOOL.value:
            messages.append(
                ToolMessage(
                    role=AgentMessageRole.TOOL,
                    tool_call_id=_candidate_required_text(
                        mapping,
                        "tool_call_id",
                    ),
                    content=_candidate_required_text(mapping, "content"),
                )
            )
        elif role == AgentMessageRole.ASSISTANT.value:
            messages.append(_candidate_assistant_message(mapping))
        else:
            raise HostDurableError("prepared candidate message role is unsupported")
    return tuple(messages)


def _candidate_assistant_message(
    value: Mapping[str, JsonValue],
) -> AssistantMessage:
    """解析 candidate assistant message。

    :param value: assistant message JSON。
    :returns: typed assistant message。
    :raises HostDurableError: content、reasoning 或 tool calls 非法时抛出。
    """

    content = _candidate_optional_text(
        value.get("content"),
        field_name="assistant.content",
        allow_empty=True,
    )
    reasoning = _candidate_optional_text(
        value.get("reasoning_content"),
        field_name="assistant.reasoning_content",
        allow_empty=True,
    )
    calls_value = value.get("tool_calls")
    if not isinstance(calls_value, list):
        raise HostDurableError("prepared candidate assistant tool_calls must be array")
    calls: list[AssistantToolCall] = []
    for item in calls_value:
        call = _candidate_mapping(item, field_name="assistant.tool_call")
        arguments = _candidate_mapping(
            call.get("arguments"),
            field_name="assistant.tool_call.arguments",
        )
        calls.append(
            AssistantToolCall(
                id=_candidate_required_text(call, "id"),
                name=_candidate_required_text(call, "name"),
                arguments=arguments,
                provider_state=_candidate_provider_state(call.get("provider_state")),
            )
        )
    return AssistantMessage(
        role=AgentMessageRole.ASSISTANT,
        content=content,
        reasoning_content=reasoning,
        tool_calls=tuple(calls),
    )


def _candidate_provider_state(
    value: JsonValue | None,
) -> GeminiToolCallState | None:
    """解析 candidate provider state closed union。

    :param value: provider state JSON。
    :returns: typed provider state；缺失时为 ``None``。
    :raises HostDurableError: provider 或字段非法时抛出。
    """

    if value is None:
        return None
    mapping = _candidate_mapping(value, field_name="provider_state")
    if set(mapping) != {"provider", "thought_signature"}:
        raise HostDurableError("prepared candidate provider state fields are invalid")
    if _candidate_required_text(mapping, "provider") != "gemini":
        raise HostDurableError("prepared candidate provider state is unsupported")
    return GeminiToolCallState(
        thought_signature=_candidate_required_text(
            mapping,
            "thought_signature",
        )
    )


def _candidate_tool_schemas(
    value: JsonValue | None,
) -> tuple[ToolSchema, ...]:
    """解析 candidate selected tool schemas。

    :param value: tool schema JSON array。
    :returns: typed tool schemas。
    :raises HostDurableError: schema shape 非法时抛出。
    """

    if not isinstance(value, list):
        raise HostDurableError("prepared candidate tool_schemas must be array")
    schemas: list[ToolSchema] = []
    for item in value:
        schema = _candidate_mapping(item, field_name="tool_schema")
        if set(schema) != {"type", "function"}:
            raise HostDurableError("prepared candidate tool schema fields are invalid")
        if _candidate_required_text(schema, "type") != "function":
            raise HostDurableError("prepared candidate tool schema type is unsupported")
        function = _candidate_mapping(
            schema.get("function"),
            field_name="tool_schema.function",
        )
        parameters = _candidate_mapping(
            function.get("parameters"),
            field_name="tool_schema.function.parameters",
        )
        properties = _candidate_mapping(
            parameters.get("properties"),
            field_name="tool_schema.function.parameters.properties",
        )
        required = _candidate_text_tuple(
            parameters.get("required"),
            field_name="tool_schema.function.parameters.required",
        )
        additional = parameters.get("additionalProperties")
        if additional is not None and not isinstance(additional, bool):
            raise HostDurableError("prepared candidate additionalProperties is invalid")
        schemas.append(
            ToolSchema(
                type="function",
                function=ToolFunctionSchema(
                    name=_candidate_required_text(function, "name"),
                    description=_candidate_required_text(
                        function,
                        "description",
                        allow_empty=True,
                    ),
                    parameters=ToolParametersSchema(
                        type="object",
                        properties=properties,
                        required=required,
                        additional_properties=additional,
                    ),
                ),
            )
        )
    return tuple(schemas)


def _validate_prepared_tool_snapshot(
    transaction: HostTransaction,
    refs: tuple[str, ...],
    *,
    tool_schemas: tuple[ToolSchema, ...],
    disable_tools: bool,
) -> None:
    """验证 selected-tool descriptor 与 candidate schemas 同源。

    :param transaction: 当前 read transaction。
    :param refs: manifest strict tool schema refs。
    :param tool_schemas: candidate raw fields 解析出的 exact selected schemas。
    :param disable_tools: candidate raw fields 解析出的工具禁用标志。
    :returns: ``None``。
    :raises HostDurableError: ref/digest/snapshot 与 candidate 不一致时抛出。
    """

    if not tool_schemas:
        if refs:
            raise HostDurableError("no-tool candidate must not reference tool schema snapshot")
        return
    ref = _candidate_prefixed_ref(
        refs,
        prefix="tool_schema_snapshot_ref:",
    )
    digest = _candidate_prefixed_ref(
        refs,
        prefix="tool_schema_snapshot_digest:",
    )
    snapshot = sqlite_payload_object(
        transaction,
        payload_ref=ref,
        payload_digest=digest,
        payload_label="prepared selected tool schema",
    )
    schemas = _candidate_tool_schemas(snapshot.get("tool_schemas"))
    snapshot_disable_tools = snapshot.get("disable_tools")
    if schemas != tool_schemas or snapshot_disable_tools is not disable_tools:
        raise HostDurableError("prepared selected tool schema snapshot mismatch")


def _candidate_prefixed_ref(
    refs: tuple[str, ...],
    *,
    prefix: str,
) -> str:
    """从 manifest ref 闭集中读取唯一指定前缀值。

    :param refs: manifest refs。
    :param prefix: required prefix。
    :returns: 去前缀后的非空值。
    :raises HostDurableError: 缺失、重复或空值时抛出。
    """

    values = tuple(ref.removeprefix(prefix) for ref in refs if ref.startswith(prefix))
    if len(values) != 1 or values[0].strip() == "":
        raise HostDurableError("prepared tool schema snapshot ref is incomplete")
    return values[0]


def _candidate_mapping(
    value: JsonValue | None,
    *,
    field_name: str,
) -> Mapping[str, JsonValue]:
    """收窄 candidate JSON object。

    :param value: 待收窄 JSON。
    :param field_name: 错误定位字段。
    :returns: typed JSON mapping。
    :raises HostDurableError: 值不是 object 时抛出。
    """

    if not isinstance(value, Mapping):
        raise HostDurableError(f"{field_name} must be object")
    return cast(Mapping[str, JsonValue], value)


def _candidate_required_text(
    value: Mapping[str, JsonValue],
    field_name: str,
    *,
    allow_empty: bool = False,
) -> str:
    """读取 candidate required text。

    :param value: source object。
    :param field_name: 字段名。
    :param allow_empty: 是否允许空字符串。
    :returns: text value。
    :raises HostDurableError: 字段不是文本或不允许的空文本时抛出。
    """

    item = value.get(field_name)
    if not isinstance(item, str) or (not allow_empty and item.strip() == ""):
        raise HostDurableError(f"prepared candidate {field_name} must be text")
    return item


def _candidate_optional_text(
    value: JsonValue | None,
    *,
    field_name: str,
    allow_empty: bool = False,
) -> str | None:
    """读取 candidate optional text。

    :param value: optional JSON value。
    :param field_name: 字段名。
    :param allow_empty: 是否允许空字符串。
    :returns: text 或 ``None``。
    :raises HostDurableError: 非空值不是合法文本时抛出。
    """

    if value is None:
        return None
    if not isinstance(value, str) or (not allow_empty and value.strip() == ""):
        raise HostDurableError(f"prepared candidate {field_name} must be optional text")
    return value


def _candidate_text_tuple(
    value: JsonValue | None,
    *,
    field_name: str,
) -> tuple[str, ...]:
    """读取 candidate text array。

    :param value: JSON array。
    :param field_name: 字段名。
    :returns: ordered text tuple。
    :raises HostDurableError: shape 或 item 非法时抛出。
    """

    if not isinstance(value, list):
        raise HostDurableError(f"prepared candidate {field_name} must be array")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or item.strip() == "":
            raise HostDurableError(f"prepared candidate {field_name} items must be text")
        items.append(item)
    return tuple(items)


class RunInputBuilder:
    """基于 typed providers 构造 deterministic no-tool AgentRunRequest。"""

    def __init__(
        self,
        *,
        current_run_provider: CurrentRunFactProvider,
        session_continuity_provider: SessionContinuityProvider,
        memory_snapshot_provider: MemorySnapshotProvider,
        compact_artifact_provider: CompactArtifactProvider,
        accepted_tool_evidence_material_provider: AcceptedToolEvidenceMaterialProvider,
        context_fallback_provider: ContextFallbackProvider,
        tool_schema_snapshot_provider: ToolSchemaSnapshotProvider,
        tool_executor_provider: ToolExecutorProvider,
        scene_parameter_provider: SceneParameterProvider,
        policy_snapshot_provider: PolicySnapshotProvider,
        tool_execution_mode: ToolExecutionMode,
        runner_call_manifest_recorder: RunnerCallManifestRecorder | None = None,
        protected_recent_raw_tail_provider: CompactPipelineProtectedRawTailProvider | None = None,
    ) -> None:
        """初始化 RunInputBuilder。

        :param current_run_provider: 当前 Run durable fact provider。
        :param session_continuity_provider: Session continuity provider。
        :param memory_snapshot_provider: Memory snapshot provider。
        :param compact_artifact_provider: Compact artifact provider。
        :param accepted_tool_evidence_material_provider: accepted tool
            evidence material provider。
        :param context_fallback_provider: context fallback view provider。
        :param tool_schema_snapshot_provider: Tool schema snapshot provider。
        :param tool_executor_provider: ToolExecutor provider。
        :param scene_parameter_provider: Scene parameter provider。
        :param policy_snapshot_provider: Policy snapshot provider。
        :param tool_execution_mode: 显式工具执行模式。
        :param runner_call_manifest_recorder: runner-call manifest 记录器；
            ``None`` 表示 no-op。
        :param protected_recent_raw_tail_provider: post-compaction raw-tail
            provider；``None`` 表示 no-op。
        :returns: ``None``。
        """

        self._current_run_provider = current_run_provider
        self._session_continuity_provider = session_continuity_provider
        self._memory_snapshot_provider = memory_snapshot_provider
        self._compact_artifact_provider = compact_artifact_provider
        self._accepted_tool_evidence_material_provider = accepted_tool_evidence_material_provider
        self._context_fallback_provider = context_fallback_provider
        self._tool_schema_snapshot_provider = tool_schema_snapshot_provider
        self._tool_executor_provider = tool_executor_provider
        self._scene_parameter_provider = scene_parameter_provider
        self._policy_snapshot_provider = policy_snapshot_provider
        self._tool_execution_mode = tool_execution_mode
        self._runner_call_manifest_recorder = (
            NoopRunnerCallManifestRecorder() if runner_call_manifest_recorder is None else runner_call_manifest_recorder
        )
        self._protected_recent_raw_tail_provider = (
            _NoopProtectedRecentRawTailProvider()
            if protected_recent_raw_tail_provider is None
            else protected_recent_raw_tail_provider
        )

    def build(self, attempt_snapshot: AttemptDispatchSnapshot) -> AgentRunRequest:
        """构造 AgentRunRequest。

        :param attempt_snapshot: Attempt dispatch snapshot。
        :returns: Engine AgentRunRequest。
        :raises HostDurableError: durable facts 缺失、不匹配或 provider 违反工具模式约束时抛出。
        """

        current_facts = self._current_run_provider.load_current_run_facts(attempt_snapshot)
        policy_snapshot = self._policy_snapshot_provider.load_policy_snapshot(attempt_snapshot, current_facts)
        continuity = self._session_continuity_provider.load_session_continuity(attempt_snapshot, current_facts)
        memory = self._memory_snapshot_provider.load_memory_snapshot(attempt_snapshot, current_facts)
        compact = self._compact_artifact_provider.load_compact_artifact(attempt_snapshot, current_facts)
        _require_compact_memory_event_ref_consistency(
            memory=memory,
            compact=compact,
            current_facts=current_facts,
        )
        fallback = self._context_fallback_provider.load_context_fallback(
            run_id=current_facts.run.run_id,
            run_started_event_sequence=(current_facts.run_started_event.event_sequence),
            current_input_ref=current_facts.user_input_event.event_id,
        )
        if fallback is None:
            protected_recent_raw_tail = (
                self._protected_recent_raw_tail_provider.load_ordinary_raw_tail(
                    attempt_snapshot,
                    current_facts,
                    memory,
                    compact,
                )
                if compact.compact_artifact_ref is not None
                else CompactPipelineOrdinaryRawTailHandoff(
                    messages=(),
                    material_blocks=(),
                    source_refs=(),
                    material_view_digest=selected_material_view_digest(()),
                    selected_recent_window_turn_floor=0,
                )
            )
            bounded_context_messages = (
                *memory.messages,
                *protected_recent_raw_tail.messages,
                *continuity.messages,
            )
        else:
            evidence = self._accepted_tool_evidence_material_provider.load_accepted_tool_evidence_materials(
                attempt_snapshot,
                current_facts,
                memory,
                compact,
            )
            fallback_material_blocks = (
                fallback.material_blocks
                if fallback.material_blocks is not None
                else build_run_input_material_blocks(
                    current_facts=current_facts,
                    memory=memory,
                    continuity=continuity,
                    accepted_tool_evidence=evidence,
                )
            )
            bounded_context_messages = _fallback_context_messages(
                fallback=fallback,
                material_blocks=fallback_material_blocks,
            )
        tool_snapshot = self._tool_schema_snapshot_provider.load_tool_schema_snapshot(attempt_snapshot, current_facts)
        tool_executor = self._tool_executor_provider.load_tool_executor(attempt_snapshot, current_facts)
        _validate_tool_mode_snapshot(
            self._tool_execution_mode,
            tool_snapshot,
            policy_snapshot,
            tool_executor,
        )
        candidate_messages = (
            *_system_prompt_message(current_facts.system_prompt),
            *self._scene_parameter_provider.build_scene_messages(
                attempt_snapshot,
                current_facts,
                policy_snapshot,
                self._tool_execution_mode,
            ),
            *bounded_context_messages,
            *_current_user_tail_messages(current_facts, continuity),
        )
        messages = _normalize_ordinary_run_messages(candidate_messages)
        self._runner_call_manifest_recorder.record_runner_call_manifest(
            RunnerCallManifestRecordInput(
                attempt_snapshot=attempt_snapshot,
                current_facts=current_facts,
                policy_snapshot=policy_snapshot,
                memory=memory,
                compact=compact,
                continuity=continuity,
                tool_snapshot=tool_snapshot,
                messages=messages,
                fallback=fallback,
            )
        )
        return AgentRunRequest(
            run_id=attempt_snapshot.run_id,
            session_id=attempt_snapshot.session_id,
            attempt_id=attempt_snapshot.attempt_id,
            execution_id=attempt_snapshot.execution_id,
            messages=messages,
            disable_tools=tool_snapshot.disable_tools,
            runner_spec=policy_snapshot.runner_spec,
            runner_options=policy_snapshot.runner_options,
            agent_policy=policy_snapshot.agent_policy,
            tool_schemas=tool_snapshot.tool_schemas,
            tool_executor=tool_executor,
            cancellation_token=attempt_snapshot.cancellation_token,
        )

    def build_material_blocks(self, attempt_snapshot: AttemptDispatchSnapshot) -> tuple[RunInputMaterialBlock, ...]:
        """构造与 ordinary Run input 同源的 compact material block view。

        本方法是 Host internal helper，供 Context Governance / compact builder
        复用 RunInputBuilder 的普通输入 material source；它不改变
        ``AgentRunRequest`` public shape。

        :param attempt_snapshot: Attempt dispatch snapshot。
        :returns: ordinary input material blocks。
        :raises HostDurableError: durable facts 缺失或 provider 读取失败时抛出。
        """

        current_facts = self._current_run_provider.load_current_run_facts(attempt_snapshot)
        continuity = self._session_continuity_provider.load_session_continuity(attempt_snapshot, current_facts)
        memory = self._memory_snapshot_provider.load_memory_snapshot(attempt_snapshot, current_facts)
        compact = self._compact_artifact_provider.load_compact_artifact(attempt_snapshot, current_facts)
        evidence = self._accepted_tool_evidence_material_provider.load_accepted_tool_evidence_materials(
            attempt_snapshot, current_facts, memory, compact
        )
        return build_run_input_material_blocks(
            current_facts=current_facts,
            memory=memory,
            continuity=continuity,
            accepted_tool_evidence=evidence,
        )


def create_no_tool_run_input_builder(
    *,
    transaction_runner: HostTransactionRunner,
    policy_snapshot: PolicySnapshot,
    memory_projection_policy: MemoryProjectionPolicy | None = None,
    memory_snapshot_provider: MemorySnapshotProvider | None = None,
    compact_artifact_provider: CompactArtifactProvider | None = None,
    context_fallback_provider: ContextFallbackProvider | None = None,
    tool_execution_mode: ToolExecutionMode = ToolExecutionMode.NO_TOOL_DISABLED,
) -> RunInputBuilder:
    """创建 Phase 5 默认 no-tool RunInputBuilder。

    :param transaction_runner: Host durable transaction runner。
    :param policy_snapshot: 显式 policy snapshot。
    :param memory_projection_policy: 可选 memory projection policy；提供
        post-compaction protected recent raw tail floor。
    :param memory_snapshot_provider: 可选 memory snapshot provider；默认 no-op。
    :param compact_artifact_provider: 可选 compact artifact provider；默认 no-op。
    :param context_fallback_provider: 可选 context fallback provider；默认 no-op。
    :param tool_execution_mode: no-tool 工具执行模式，只能是 replay 或 disabled。
    :returns: RunInputBuilder。
    :raises ValueError: 传入 ``TOOL_ENABLED`` 时抛出。
    """

    if tool_execution_mode == ToolExecutionMode.TOOL_ENABLED:
        raise ValueError("create_no_tool_run_input_builder requires no-tool mode")
    return RunInputBuilder(
        current_run_provider=DurableCurrentRunFactProvider(transaction_runner),
        session_continuity_provider=DurableSessionContinuityProvider(transaction_runner),
        memory_snapshot_provider=(
            NoopMemorySnapshotProvider() if memory_snapshot_provider is None else memory_snapshot_provider
        ),
        compact_artifact_provider=(
            NoopCompactArtifactProvider() if compact_artifact_provider is None else compact_artifact_provider
        ),
        accepted_tool_evidence_material_provider=(DurableAcceptedToolEvidenceMaterialProvider(transaction_runner)),
        context_fallback_provider=(
            NoopContextFallbackProvider() if context_fallback_provider is None else context_fallback_provider
        ),
        tool_schema_snapshot_provider=NoopToolSchemaSnapshotProvider(),
        tool_executor_provider=NoToolExecutorProvider(),
        scene_parameter_provider=DefaultSceneParameterProvider(),
        policy_snapshot_provider=StaticPolicySnapshotProvider(policy_snapshot),
        tool_execution_mode=tool_execution_mode,
        runner_call_manifest_recorder=DurableRunnerCallManifestRecorder(transaction_runner),
        protected_recent_raw_tail_provider=(
            None
            if memory_projection_policy is None
            else _DurableProtectedRecentRawTailProvider(
                transaction_runner,
                memory_projection_policy,
            )
        ),
    )


def create_tool_enabled_run_input_builder(
    *,
    transaction_runner: HostTransactionRunner,
    policy_snapshot: PolicySnapshot,
    tool_runtime_handle: ToolRuntimeHandle,
    memory_projection_policy: MemoryProjectionPolicy | None = None,
    memory_snapshot_provider: MemorySnapshotProvider | None = None,
    compact_artifact_provider: CompactArtifactProvider | None = None,
    context_fallback_provider: ContextFallbackProvider | None = None,
) -> RunInputBuilder:
    """创建 tool-enabled RunInputBuilder。

    :param transaction_runner: Host durable transaction runner。
    :param policy_snapshot: 显式 policy snapshot，必须允许工具调用。
    :param tool_runtime_handle: ToolRuntime handle。
    :param memory_projection_policy: 可选 memory projection policy；提供
        post-compaction protected recent raw tail floor。
    :param memory_snapshot_provider: 可选 memory snapshot provider；默认 no-op。
    :param compact_artifact_provider: 可选 compact artifact provider；默认 no-op。
    :param context_fallback_provider: 可选 context fallback provider；默认 no-op。
    :returns: RunInputBuilder。
    """

    handle_provider = StaticToolRuntimeHandleProvider(tool_runtime_handle)
    return RunInputBuilder(
        current_run_provider=DurableCurrentRunFactProvider(transaction_runner),
        session_continuity_provider=DurableSessionContinuityProvider(transaction_runner),
        memory_snapshot_provider=(
            NoopMemorySnapshotProvider() if memory_snapshot_provider is None else memory_snapshot_provider
        ),
        compact_artifact_provider=(
            NoopCompactArtifactProvider() if compact_artifact_provider is None else compact_artifact_provider
        ),
        accepted_tool_evidence_material_provider=(DurableAcceptedToolEvidenceMaterialProvider(transaction_runner)),
        context_fallback_provider=(
            NoopContextFallbackProvider() if context_fallback_provider is None else context_fallback_provider
        ),
        tool_schema_snapshot_provider=ToolRuntimeSchemaSnapshotProvider(handle_provider),
        tool_executor_provider=ToolRuntimeExecutorProvider(handle_provider),
        scene_parameter_provider=DefaultSceneParameterProvider(),
        policy_snapshot_provider=StaticPolicySnapshotProvider(policy_snapshot),
        tool_execution_mode=ToolExecutionMode.TOOL_ENABLED,
        runner_call_manifest_recorder=DurableRunnerCallManifestRecorder(transaction_runner),
        protected_recent_raw_tail_provider=(
            None
            if memory_projection_policy is None
            else _DurableProtectedRecentRawTailProvider(
                transaction_runner,
                memory_projection_policy,
            )
        ),
    )


def _validate_snapshot_rows(
    *,
    snapshot: AttemptDispatchSnapshot,
    run: RunRow | None,
    attempt: AttemptRow | None,
    dispatch_record: DispatchRecordRow | None,
) -> None:
    """校验 durable rows 与 attempt snapshot 一致。

    :param snapshot: Attempt dispatch snapshot。
    :param run: durable Run row。
    :param attempt: durable Attempt row。
    :param dispatch_record: durable dispatch record row。
    :returns: ``None``。
    :raises HostDurableError: 任一 row 缺失或 identity 不匹配时抛出。
    """

    if run is None:
        raise HostDurableError("RunInputBuilder run row not found")
    if attempt is None:
        raise HostDurableError("RunInputBuilder attempt row not found")
    if dispatch_record is None:
        raise HostDurableError("RunInputBuilder dispatch record row not found")
    if run.session_id != snapshot.session_id:
        raise HostDurableError("RunInputBuilder session_id mismatch")
    if run.current_attempt_id != snapshot.attempt_id:
        raise HostDurableError("RunInputBuilder current_attempt_id mismatch")
    if attempt.run_id != snapshot.run_id or attempt.execution_id != snapshot.execution_id:
        raise HostDurableError("RunInputBuilder attempt identity mismatch")
    if (
        dispatch_record.dispatch_record_id != snapshot.dispatch_record_id
        or dispatch_record.execution_id != snapshot.execution_id
        or dispatch_record.run_id != snapshot.run_id
    ):
        raise HostDurableError("RunInputBuilder dispatch identity mismatch")
    if run.execution_target != snapshot.execution_target:
        raise HostDurableError("RunInputBuilder execution_target mismatch")
    if run.status != RunStatus.RUNNING:
        raise HostDurableError("RunInputBuilder requires RUNNING Run")
    if attempt.status != AttemptStatus.STARTING:
        raise HostDurableError("RunInputBuilder requires STARTING Attempt")
    if dispatch_record.status != DispatchRecordStatus.DISPATCHING:
        raise HostDurableError("RunInputBuilder requires DISPATCHING dispatch record")


def _require_event(row: EventLogRow | None, *, expected_type: str) -> EventLogRow:
    """校验并返回指定类型的 canonical EventLog row。

    :param row: EventLog row 或 ``None``。
    :param expected_type: 期望 event type。
    :returns: EventLog row。
    :raises HostDurableError: row 缺失或类型不匹配时抛出。
    """

    if row is None:
        raise HostDurableError(f"{expected_type} event not found")
    if row.event_class != EventClass.CANONICAL_FACT:
        raise HostDurableError(f"{expected_type} event must be canonical")
    if row.event_type != expected_type:
        raise HostDurableError(f"expected {expected_type} event")
    return row


def _validate_current_event_scope(snapshot: AttemptDispatchSnapshot, event: EventLogRow) -> None:
    """校验当前 Run 事件归属。

    :param snapshot: Attempt dispatch snapshot。
    :param event: EventLog row。
    :returns: ``None``。
    :raises HostDurableError: 事件归属不匹配时抛出。
    """

    if event.session_id != snapshot.session_id or event.run_id != snapshot.run_id:
        raise HostDurableError("RunInputBuilder current event scope mismatch")


def _required_memory_event_sequence(current_facts: CurrentRunFacts) -> int:
    """计算本次 memory snapshot 需要覆盖的 EventLog cursor。

    :param current_facts: 当前 Run facts。
    :returns: 当前 Attempt start 之前的最大 EventLog sequence。
    :raises HostDurableError: Attempt started sequence 非法时抛出。
    """

    required_event_sequence = current_facts.attempt.started_event_sequence - 1
    if required_event_sequence < 0:
        raise HostDurableError("memory required event sequence is invalid")
    return required_event_sequence


def _candidate_input_cursor(
    transaction: HostTransaction,
    session_id: str,
) -> int:
    """读取当前 transaction snapshot 的 Session source watermark。

    :param transaction: Host transaction。
    :param session_id: Session id。
    :returns: 最大 EventLog sequence；无事件时返回 ``0``。
    :raises HostDurableError: SQLite 返回类型非法时抛出。
    """

    row = transaction.fetchone(
        f"""
        SELECT MAX(event_sequence) AS max_event_sequence
        FROM {TABLE_EVENT_LOG}
        WHERE session_id = ?
        """,
        (session_id,),
    )
    if row is None:
        raise HostDurableError("candidate cursor query returned no row")
    value = row.get("max_event_sequence")
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HostDurableError("candidate cursor is invalid")
    return value


def _load_pre_start_memory_snapshot(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    facts: _PreStartCandidateFacts,
    required_event_sequence: int,
    policy: MemoryProjectionPolicy,
) -> MemorySnapshotView:
    """读取并渲染 candidate cursor 对应的 memory snapshot。

    :param transaction: Host transaction。
    :param event_log_store: EventLog primitive。
    :param facts: Attempt-free current Run facts。
    :param required_event_sequence: candidate source watermark。
    :param policy: memory projection policy。
    :returns: 与 actual request 同源的 memory view。
    :raises MemoryProjectionRepairRequired: snapshot 缺失、损坏或滞后过大时抛出。
    """

    policy_digest = digest_memory_projection_policy(policy)
    row = read_latest_memory_snapshot_at_or_before(
        transaction,
        session_id=facts.run.session_id,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy_digest=policy_digest,
        max_checkpoint_event_sequence=required_event_sequence,
    )
    if row is None:
        event_filter = event_log_read_filter_from_projection_filter(conversation_memory_projection_event_filter())
        page = event_log_store.read_events_after_matching(
            transaction,
            0,
            event_filter=event_filter,
            limit=policy.max_delta_repair_events,
            max_event_sequence=required_event_sequence,
            session_id=facts.run.session_id,
        )
        repaired_from_empty: ConversationMemorySnapshotVNext | None = None
        for event in page.rows:
            repaired_from_empty = project_conversation_memory_event(
                previous_snapshot=repaired_from_empty,
                event=_memory_projection_event_from_row(transaction, event),
                policy=policy,
                built_at=event.occurred_at,
                consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
            )
        if (
            repaired_from_empty is None
            or page.covered_event_sequence != required_event_sequence
            or page.covered_event_id is None
        ):
            raise MemoryProjectionRepairRequired(
                MemoryRepairRequest(
                    session_id=facts.run.session_id,
                    reason=MemoryRepairReason.SNAPSHOT_MISSING,
                    required_event_sequence=required_event_sequence,
                    observed_cursor=None,
                    policy_digest=policy_digest,
                )
            )
        snapshot = memory_snapshot_with_cursor_and_diagnostics(
            snapshot=repaired_from_empty,
            cursor=MemorySnapshotCursor(
                consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                checkpoint_event_sequence=required_event_sequence,
                checkpoint_event_id=page.covered_event_id,
                session_id=facts.run.session_id,
            ),
            diagnostics=(
                build_inline_delta_repair_diagnostic(
                    event_sequence=required_event_sequence,
                    policy_digest=policy_digest,
                ),
            ),
        )
    else:
        snapshot = row.snapshot
    cursor = snapshot.cursor
    if cursor.checkpoint_event_sequence > 0:
        cursor_event = (
            None if cursor.checkpoint_event_id is None else read_event_by_id(transaction, cursor.checkpoint_event_id)
        )
        if (
            cursor_event is None
            or cursor_event.event_sequence != cursor.checkpoint_event_sequence
            or cursor_event.session_id != facts.run.session_id
        ):
            raise MemoryProjectionRepairRequired(
                MemoryRepairRequest(
                    session_id=facts.run.session_id,
                    reason=MemoryRepairReason.SNAPSHOT_DAMAGED,
                    required_event_sequence=required_event_sequence,
                    observed_cursor=cursor,
                    policy_digest=policy_digest,
                )
            )
    lag_events = required_event_sequence - cursor.checkpoint_event_sequence
    if lag_events < 0:
        raise MemoryProjectionRepairRequired(
            MemoryRepairRequest(
                session_id=facts.run.session_id,
                reason=MemoryRepairReason.SNAPSHOT_AHEAD_OF_REQUIRED,
                required_event_sequence=required_event_sequence,
                observed_cursor=cursor,
                policy_digest=policy_digest,
            )
        )
    repaired = snapshot
    if lag_events > 0:
        inline_event_limit = min(
            policy.max_lag_events_for_inline_delta,
            policy.max_delta_repair_events,
        )
        event_filter = event_log_read_filter_from_projection_filter(conversation_memory_projection_event_filter())
        page = event_log_store.read_events_after_matching(
            transaction,
            cursor.checkpoint_event_sequence,
            event_filter=event_filter,
            limit=inline_event_limit + 1,
            max_event_sequence=required_event_sequence,
            session_id=facts.run.session_id,
        )
        if len(page.rows) > inline_event_limit:
            raise MemoryProjectionRepairRequired(
                MemoryRepairRequest(
                    session_id=facts.run.session_id,
                    reason=MemoryRepairReason.SNAPSHOT_LAG_OVER_THRESHOLD,
                    required_event_sequence=required_event_sequence,
                    observed_cursor=cursor,
                    policy_digest=policy_digest,
                )
            )
        if page.covered_event_sequence != required_event_sequence:
            raise MemoryProjectionRepairRequired(
                MemoryRepairRequest(
                    session_id=facts.run.session_id,
                    reason=MemoryRepairReason.SNAPSHOT_DAMAGED,
                    required_event_sequence=required_event_sequence,
                    observed_cursor=cursor,
                    policy_digest=policy_digest,
                )
            )
        for event in page.rows:
            repaired = project_conversation_memory_event(
                previous_snapshot=repaired,
                event=_memory_projection_event_from_row(transaction, event),
                policy=policy,
                built_at=event.occurred_at,
                consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
            )
        covered_event_id = page.covered_event_id
        if covered_event_id is None:
            raise HostDurableError("candidate memory delta covered event id is missing")
        repaired = memory_snapshot_with_cursor_and_diagnostics(
            snapshot=repaired,
            cursor=MemorySnapshotCursor(
                consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                checkpoint_event_sequence=required_event_sequence,
                checkpoint_event_id=covered_event_id,
                session_id=facts.run.session_id,
            ),
            diagnostics=(
                build_inline_delta_repair_diagnostic(
                    event_sequence=required_event_sequence,
                    policy_digest=policy_digest,
                ),
            ),
        )
    render_scope = _CurrentMemoryRenderScope(
        run_id=facts.run.run_id,
        user_input_event_id=facts.user_input_event.event_id,
        user_prompt=facts.user_prompt,
    )
    rendered = _memory_messages(repaired, render_scope, policy)
    return MemorySnapshotView(
        messages=rendered.messages,
        memory_snapshot_cursor=_memory_cursor_ref(repaired.cursor),
        policy_digest=repaired.policy_digest,
        diagnostics=repaired.diagnostics + rendered.diagnostics,
        represented_evidence_refs=_memory_represented_evidence_refs(repaired),
        latest_compaction_event_ref=repaired.latest_compaction_event_ref,
        selected_recent_source_refs=_memory_selected_recent_source_refs(
            repaired.trace_memory.selected_recent_window,
            render_scope,
        ),
        selected_recent_content_digests=_memory_selected_recent_content_digests(
            repaired.trace_memory.selected_recent_window,
            render_scope,
        ),
    )


def _load_pre_start_compact_artifact(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    facts: _PreStartCandidateFacts,
    before_event_sequence: int,
) -> tuple[CompactArtifactView, EventLogRow | None]:
    """读取 candidate cursor 前 latest accepted compact artifact。

    :param transaction: Host transaction。
    :param event_log_store: EventLog primitive。
    :param facts: Attempt-free current Run facts。
    :param before_event_sequence: exclusive EventLog cursor。
    :returns: ``(compact view, compacted event)``。
    :raises HostDurableError: compact payload 或 descriptor identity 非法时抛出。
    """

    compacted_event = _latest_compacted_event_before_cursor(
        transaction,
        event_log_store,
        session_id=facts.run.session_id,
        before_event_sequence=before_event_sequence,
    )
    if compacted_event is None:
        return (
            CompactArtifactView(
                compaction_event_ref=None,
                compact_artifact_ref=None,
                compact_artifact_digest=None,
            ),
            None,
        )
    payload = resolve_context_compacted_payload(transaction, compacted_event)
    try:
        semantic_payload = parse_context_compacted_semantic_payload(payload)
    except (TypeError, ValueError) as exc:
        raise HostDurableError("compact semantic payload is invalid") from exc
    return (
        CompactArtifactView(
            compaction_event_ref=compacted_event.event_id,
            compact_artifact_ref=semantic_payload.compact_artifact_ref,
            compact_artifact_digest=_required_text_field(
                payload,
                _PAYLOAD_FIELD_COMPACT_ARTIFACT_DIGEST,
            ),
            represented_evidence_refs=(semantic_payload.accepted_evidence_mapping_refs),
        ),
        compacted_event,
    )


def _latest_compacted_event_before_cursor(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    session_id: str,
    before_event_sequence: int,
) -> EventLogRow | None:
    """读取指定 Session/cursor 前 latest accepted compact event。

    :param transaction: Host transaction。
    :param event_log_store: EventLog primitive。
    :param session_id: Session id。
    :param before_event_sequence: exclusive EventLog cursor。
    :returns: latest compacted event；不存在时为 ``None``。
    :raises HostDurableError: event id 或 row 缺失时抛出。
    """

    rows = transaction.fetchall(
        f"""
        SELECT event_id
        FROM {TABLE_EVENT_LOG}
        WHERE session_id = ?
          AND event_type = ?
          AND event_class = ?
          AND event_sequence < ?
        ORDER BY event_sequence DESC
        LIMIT 1
        """,
        (
            session_id,
            CONTEXT_COMPACTED,
            EventClass.CANONICAL_FACT.value,
            before_event_sequence,
        ),
    )
    if not rows:
        return None
    event_id = _required_host_row_text(rows[0], field_name="event_id")
    event = event_log_store.read_event_by_id(transaction, event_id)
    if event is None:
        raise HostDurableError("CONTEXT_COMPACTED event disappeared during read")
    return event


def _pre_start_protected_recent_raw_tail(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    facts: _PreStartCandidateFacts,
    memory: MemorySnapshotView,
    compact: CompactArtifactView,
    compacted_event: EventLogRow | None,
    memory_projection_policy: MemoryProjectionPolicy,
) -> CompactPipelineOrdinaryRawTailHandoff:
    """构造 pre-start candidate 的 post-compact protected raw tail。

    :param transaction: Host transaction。
    :param event_log_store: EventLog primitive。
    :param facts: Attempt-free current Run facts。
    :param memory: frozen memory view。
    :param compact: frozen compact view。
    :param compacted_event: compact view 的 source event。
    :param memory_projection_policy: raw-tail floor policy。
    :returns: ordinary protected raw-tail handoff。
    :raises HostDurableError: compact provenance 或 material source 非法时抛出。
    """

    if compact.compact_artifact_ref is None:
        return CompactPipelineOrdinaryRawTailHandoff(
            messages=(),
            material_blocks=(),
            source_refs=(),
            material_view_digest=selected_material_view_digest(()),
            selected_recent_window_turn_floor=0,
        )
    if compacted_event is None:
        raise HostDurableError("compact view source event is missing")
    _validate_loaded_compact_view_matches_event(
        transaction,
        compact=compact,
        compacted_event=compacted_event,
    )
    material_view = build_pre_dispatch_compact_material_view(
        transaction,
        event_log_store,
        run=facts.run,
        current_display_text=facts.user_prompt,
    )
    source_snapshot = compact_pipeline_source_snapshot_from_pre_dispatch_view(
        trigger_source=_compaction_trigger_source_for_compacted_event(
            transaction,
            compacted_event=compacted_event,
        ),
        run=facts.run,
        material_view=material_view,
    )
    return select_ordinary_protected_raw_tail(
        source_snapshot=source_snapshot,
        selected_recent_window_turn_floor=(memory_projection_policy.selected_recent_window_turn_floor),
        memory=memory,
    )


def _pre_start_fallback_material_blocks(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    facts: _PreStartCandidateFacts,
    memory: MemorySnapshotView,
    continuity: SessionContinuityView,
    compact: CompactArtifactView,
) -> tuple[RunInputMaterialBlock, ...]:
    """构造 reactive fallback 所需的 complete material blocks。

    :param transaction: Host transaction。
    :param event_log_store: EventLog primitive。
    :param facts: Attempt-free current Run facts。
    :param memory: frozen memory view。
    :param continuity: frozen continuity view。
    :param compact: frozen compact view。
    :returns: fallback material blocks。
    :raises HostDurableError: material source 非法时抛出。
    """

    material_view = build_pre_dispatch_compact_material_view(
        transaction,
        event_log_store,
        run=facts.run,
        current_display_text=facts.user_prompt,
    )
    represented = frozenset(_represented_evidence_refs(memory, compact))
    accepted_evidence = tuple(
        block
        for block in material_view.material_blocks
        if block.kind is CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE
        and block.accepted_evidence_id not in represented
    )
    return _pre_start_material_blocks(
        facts=facts,
        memory=memory,
        continuity=continuity,
        accepted_tool_evidence=accepted_evidence,
    )


def _pre_start_material_blocks(
    *,
    facts: _PreStartCandidateFacts,
    memory: MemorySnapshotView,
    continuity: SessionContinuityView,
    accepted_tool_evidence: tuple[RunInputMaterialBlock, ...],
) -> tuple[RunInputMaterialBlock, ...]:
    """构造 Attempt-free candidate 的 shared material block list。

    :param facts: Attempt-free current Run facts。
    :param memory: frozen memory view。
    :param continuity: frozen continuity view。
    :param accepted_tool_evidence: accepted evidence blocks。
    :returns: ordered material blocks。
    :raises Exception: 不主动抛出异常。
    """

    blocks: list[RunInputMaterialBlock] = []
    for index, message in enumerate(memory.messages):
        blocks.append(
            run_input_material_block(
                block_id=f"memory:{index}",
                section=_material_section_for_message(message),
                kind=_memory_material_kind(message),
                text=_run_input_message_content(message),
                canonical_source_refs=(_memory_material_source_ref(memory),),
                event_sequence=None,
                event_sub_index=index,
            )
        )
    for index, message in enumerate(continuity.messages):
        blocks.append(
            run_input_material_block(
                block_id=f"continuity:{index}",
                section=CompactMaterialSection.TRACE_MATERIAL,
                kind=_history_material_kind(message),
                text=_run_input_message_content(message),
                canonical_source_refs=continuity.source_refs,
                event_sequence=None,
                event_sub_index=index,
            )
        )
    blocks.extend(accepted_tool_evidence)
    blocks.append(
        run_input_material_block(
            block_id=f"current:{facts.user_input_event.event_id}",
            section=CompactMaterialSection.CURRENT_INPUT_ANCHOR,
            kind=CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR,
            text=facts.user_prompt,
            canonical_source_refs=(facts.user_input_event.event_id,),
            event_sequence=facts.user_input_event.event_sequence,
            turn_group_id=facts.run.run_id,
        )
    )
    return tuple(blocks)


def _pre_start_candidate_source_refs(
    *,
    facts: _PreStartCandidateFacts,
    memory: MemorySnapshotView,
    compact: CompactArtifactView,
    fallback: ActiveRecentWindowFallback | None,
    continuity: SessionContinuityView,
) -> tuple[str, ...]:
    """构造 identity-free candidate 的 complete source refs。

    :param facts: Attempt-free current Run facts。
    :param memory: frozen memory view。
    :param compact: frozen compact view。
    :param fallback: frozen fallback view。
    :param continuity: producer 冻结的 continuation source refs。
    :returns: 去重 source refs。
    :raises Exception: 不主动抛出异常。
    """

    refs = [
        f"event:{facts.user_input_event.event_id}",
        f"event:{facts.run_accepted_event.event_id}",
        facts.run.execution_target,
    ]
    if memory.memory_snapshot_cursor is not None:
        refs.append(f"memory:{memory.memory_snapshot_cursor}")
    refs.extend(_compact_artifact_refs(compact))
    refs.extend(continuity.source_refs)
    fallback_ref = _context_fallback_decision_ref(fallback)
    if fallback_ref is not None:
        refs.append(fallback_ref)
    return tuple(dict.fromkeys(refs))


def _pre_start_current_user_tail(
    facts: _PreStartCandidateFacts,
    continuity: SessionContinuityView,
) -> tuple[UserMessage, ...]:
    """为 pre-start candidate 追加且只追加一次 current user input。

    :param facts: 本次 candidate 的 exact input fact。
    :param continuity: producer 冻结的 continuation messages。
    :returns: continuity 已包含 current user 时为空，否则为单条 user message。
    :raises Exception: 不主动抛出异常。
    """

    for message in continuity.messages:
        if isinstance(message, UserMessage) and message.content == facts.user_prompt:
            return ()
    return (
        UserMessage(
            role=AgentMessageRole.USER,
            content=facts.user_prompt,
        ),
    )


def _memory_snapshot_view(
    snapshot: ConversationMemorySnapshotVNext,
    current_facts: CurrentRunFacts,
    policy: MemoryProjectionPolicy,
) -> MemorySnapshotView:
    """把 typed memory snapshot 渲染为 provider view。

    :param snapshot: memory snapshot。
    :param current_facts: 当前 Run facts。
    :param policy: memory projection policy。
    :returns: RunInputBuilder memory view。
    """

    render_scope = _CurrentMemoryRenderScope(
        run_id=current_facts.run.run_id,
        user_input_event_id=current_facts.user_input_event.event_id,
        user_prompt=current_facts.user_prompt,
    )
    rendered = _memory_messages(snapshot, render_scope, policy)
    return MemorySnapshotView(
        messages=rendered.messages,
        memory_snapshot_cursor=_memory_cursor_ref(snapshot.cursor),
        policy_digest=snapshot.policy_digest,
        diagnostics=snapshot.diagnostics + rendered.diagnostics,
        represented_evidence_refs=_memory_represented_evidence_refs(snapshot),
        latest_compaction_event_ref=snapshot.latest_compaction_event_ref,
        selected_recent_source_refs=_memory_selected_recent_source_refs(
            snapshot.trace_memory.selected_recent_window,
            render_scope,
        ),
        selected_recent_content_digests=_memory_selected_recent_content_digests(
            snapshot.trace_memory.selected_recent_window,
            render_scope,
        ),
    )


def _memory_messages(
    snapshot: ConversationMemorySnapshotVNext,
    render_scope: _CurrentMemoryRenderScope,
    policy: MemoryProjectionPolicy,
) -> _RenderedMemoryMessages:
    """按设计固定顺序渲染 vNext memory messages。

    :param snapshot: memory snapshot。
    :param render_scope: 当前 Run memory 渲染排除范围。
    :param policy: memory projection policy。
    :returns: memory provider messages 与 transient diagnostics。
    """

    del policy
    messages: list[AgentMessage] = []
    summary = _memory_session_summary_message(snapshot)
    if summary is not None:
        messages.append(summary)
    facts = _memory_evidence_fact_message(snapshot.evidence_fact_memory.evidence_backed_facts)
    if facts is not None:
        messages.append(facts)
    anchors = _memory_answer_anchor_message(snapshot)
    if anchors is not None:
        messages.append(anchors)
    intents = _memory_forward_intent_message(snapshot)
    if intents is not None:
        messages.append(intents)
    reference = _memory_reference_continuity_message(snapshot.trace_memory.reference_continuity_items)
    if reference is not None:
        messages.append(reference)
    messages.extend(
        _memory_selected_recent_window_messages(
            snapshot.trace_memory.selected_recent_window,
            render_scope,
        )
    )
    return _RenderedMemoryMessages(
        messages=tuple(messages),
        diagnostics=(),
    )


def _memory_session_summary_message(
    snapshot: ConversationMemorySnapshotVNext,
) -> SystemMessage | None:
    """渲染 Session Summary Memory section。

    :param snapshot: memory snapshot。
    :returns: system message；无 summary 时返回 ``None``。
    """

    summary = snapshot.session_summary_memory
    if summary.summary_text is None:
        return None
    lines = [_MEMORY_SESSION_SUMMARY_HEADER, f"summary={summary.summary_text}"]
    return SystemMessage(role=AgentMessageRole.SYSTEM, content="\n".join(lines))


def _memory_evidence_fact_message(
    facts: tuple[EvidenceBackedFactView, ...],
) -> SystemMessage | None:
    """渲染 Evidence / Fact Memory section。

    :param facts: evidence-backed fact 元组。
    :returns: system message；无内容时返回 ``None``。
    """

    if not facts:
        return None
    lines = [_MEMORY_EVIDENCE_FACT_HEADER]
    for index, fact in enumerate(facts, start=1):
        lines.append(f"Source F{index}: claim_text={fact.claim_text}")
    return SystemMessage(
        role=AgentMessageRole.SYSTEM,
        content="\n".join(lines),
    )


def _memory_answer_anchor_message(
    snapshot: ConversationMemorySnapshotVNext,
) -> SystemMessage | None:
    """渲染 Answer Anchor Memory section。

    :param snapshot: memory snapshot。
    :returns: system message；无内容时返回 ``None``。
    """

    anchors = snapshot.answer_anchor_memory.anchors
    if not anchors:
        return None
    lines = [_MEMORY_ANSWER_ANCHOR_HEADER]
    for anchor in anchors:
        child_text = "; ".join(
            (child.display_text if child.ordinal is None else f"{child.ordinal}. {child.display_text}")
            for child in anchor.anchor_items
        )
        lines.append(f"answer_anchor=title={anchor.anchor_title}; items={child_text}")
    return SystemMessage(role=AgentMessageRole.SYSTEM, content="\n".join(lines))


def _memory_forward_intent_message(
    snapshot: ConversationMemorySnapshotVNext,
) -> SystemMessage | None:
    """渲染 Forward Intent Memory section。

    :param snapshot: memory snapshot。
    :returns: system message；无内容时返回 ``None``。
    """

    intents = snapshot.forward_intent_memory.intents
    if not intents:
        return None
    lines = [_MEMORY_FORWARD_INTENT_HEADER]
    for intent in intents:
        lines.append(f"forward_intent=type={intent.intent_type}; status={intent.status.value}; text={intent.text}")
    return SystemMessage(role=AgentMessageRole.SYSTEM, content="\n".join(lines))


def _memory_reference_continuity_message(
    items: tuple[ReferenceContinuityItem, ...],
) -> SystemMessage | None:
    """渲染 Trace Memory reference continuity section。

    :param items: reference continuity items。
    :returns: system message；无内容时返回 ``None``。
    """

    if not items:
        return None
    lines = [_MEMORY_REFERENCE_CONTINUITY_HEADER]
    for item in items:
        lines.append(f"reference_continuity=reason={item.reason}; text={item.text}")
    return SystemMessage(role=AgentMessageRole.SYSTEM, content="\n".join(lines))


def _memory_selected_recent_window_messages(
    items: tuple[SelectedRecentWindowItem, ...],
    render_scope: _CurrentMemoryRenderScope,
) -> tuple[AgentMessage, ...]:
    """渲染 selected recent window messages。

    :param items: selected recent window items。
    :param render_scope: 当前 Run memory 渲染排除范围。
    :returns: Engine messages。
    """

    messages: list[AgentMessage] = []
    for item in items:
        if item.event_id == render_scope.user_input_event_id:
            continue
        if item.role is SelectedRecentWindowRole.USER:
            messages.append(UserMessage(role=AgentMessageRole.USER, content=item.text))
        elif item.role is SelectedRecentWindowRole.ASSISTANT:
            messages.append(
                AssistantMessage(
                    role=AgentMessageRole.ASSISTANT,
                    content=item.text,
                    reasoning_content=None,
                    tool_calls=(),
                )
            )
        else:
            messages.append(
                SystemMessage(
                    role=AgentMessageRole.SYSTEM,
                    content=_recent_evidence_content(item.text),
                )
            )
    return tuple(messages)


def _memory_selected_recent_source_refs(
    items: tuple[SelectedRecentWindowItem, ...],
    render_scope: _CurrentMemoryRenderScope,
) -> tuple[str, ...]:
    """返回已渲染 selected recent window 的内部来源 refs。

    :param items: selected recent window items。
    :param render_scope: 当前 Run memory 渲染排除范围。
    :returns: 去重后的来源 refs。
    """

    refs: list[str] = []
    for item in items:
        if item.event_id == render_scope.user_input_event_id:
            continue
        refs.append(item.event_id)
        refs.extend(item.source_refs)
    return tuple(dict.fromkeys(refs))


def _memory_selected_recent_content_digests(
    items: tuple[SelectedRecentWindowItem, ...],
    render_scope: _CurrentMemoryRenderScope,
) -> tuple[str, ...]:
    """返回已渲染 selected recent window 的文本 digest。

    :param items: selected recent window items。
    :param render_scope: 当前 Run memory 渲染排除范围。
    :returns: 去重后的文本 digest。
    """

    digests: list[str] = []
    for item in items:
        if item.event_id == render_scope.user_input_event_id:
            continue
        digests.append(_text_content_digest(item.text))
    return tuple(dict.fromkeys(digests))


def build_run_input_material_blocks(
    *,
    current_facts: CurrentRunFacts,
    memory: MemorySnapshotView,
    continuity: SessionContinuityView,
    accepted_tool_evidence: tuple[RunInputMaterialBlock, ...] = (),
) -> tuple[RunInputMaterialBlock, ...]:
    """构造 ordinary Run input 的共享 material block list。

    :param current_facts: 当前 Run durable facts。
    :param memory: memory snapshot provider view。
    :param continuity: session continuity provider view。
    :param accepted_tool_evidence: 当前 Attempt 前可用于 compact 的 accepted
        tool evidence material blocks。
    :returns: RunInputBuilder 与 compact builder 共用的 material blocks。
    """

    blocks: list[RunInputMaterialBlock] = []
    for index, message in enumerate(memory.messages):
        content = _run_input_message_content(message)
        blocks.append(
            run_input_material_block(
                block_id=f"memory:{index}",
                section=_material_section_for_message(message),
                kind=_memory_material_kind(message),
                text=content,
                canonical_source_refs=(_memory_material_source_ref(memory),),
                event_sequence=None,
                event_sub_index=index,
            )
        )
    for index, message in enumerate(continuity.messages):
        blocks.append(
            run_input_material_block(
                block_id=f"continuity:{index}",
                section=CompactMaterialSection.TRACE_MATERIAL,
                kind=_history_material_kind(message),
                text=_run_input_message_content(message),
                canonical_source_refs=continuity.source_refs,
                event_sequence=None,
                event_sub_index=index,
            )
        )
    blocks.extend(accepted_tool_evidence)
    blocks.append(
        run_input_material_block(
            block_id=f"current:{current_facts.user_input_event.event_id}",
            section=CompactMaterialSection.CURRENT_INPUT_ANCHOR,
            kind=CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR,
            text=current_facts.user_prompt,
            canonical_source_refs=(current_facts.user_input_event.event_id,),
            event_sequence=current_facts.user_input_event.event_sequence,
            turn_group_id=current_facts.run.run_id,
        )
    )
    return tuple(blocks)


def _normalize_ordinary_run_messages(
    messages: tuple[AgentMessage, ...],
) -> tuple[AgentMessage, ...]:
    """把 ordinary RunInput 候选 messages 归一为至多一条 system envelope。

    :param messages: RunInputBuilder 已完成预算治理的候选 messages。
    :returns: 归一化后的最终 Engine messages。
    :raises HostDurableError: system material 为空、未知 message 类型或 envelope
        含内部治理标识时抛出。
    """

    sections: dict[str, list[str]] = {section: [] for section in _SYSTEM_ENVELOPE_SECTION_ORDER}
    non_system_messages: list[AgentMessage] = []
    source_system_chars = 0
    for message in messages:
        if isinstance(message, SystemMessage):
            content = message.content.strip()
            if content == "":
                raise HostDurableError("ordinary system material must be non-empty")
            source_system_chars += len(content)
            section, body = _system_envelope_section_and_body(content)
            sections[section].append(body)
        elif isinstance(message, UserMessage):
            non_system_messages.append(message)
        elif isinstance(message, AssistantMessage):
            non_system_messages.append(message)
        elif isinstance(message, ToolMessage):
            non_system_messages.append(message)
        else:
            _raise_unsupported_agent_message(message)
    section_blocks = _non_empty_system_section_blocks(sections)
    if not section_blocks:
        return tuple(non_system_messages)
    envelope_content = _render_system_envelope(section_blocks)
    _validate_system_envelope_content(
        envelope_content,
        source_system_chars=source_system_chars,
        section_blocks=section_blocks,
    )
    return (
        SystemMessage(role=AgentMessageRole.SYSTEM, content=envelope_content),
        *tuple(non_system_messages),
    )


def _system_envelope_section_and_body(content: str) -> tuple[str, str]:
    """返回候选 system material 对应的 envelope section 与正文。

    :param content: 单条候选 system message 内容。
    :returns: ``(section title, body)``。
    :raises HostDurableError: 正文为空时抛出。
    """

    if content.startswith(_EXECUTION_GUIDANCE_PREFIX):
        return _stripped_prefixed_system_body(
            content,
            prefix=_EXECUTION_GUIDANCE_PREFIX,
            section=_SYSTEM_SECTION_EXECUTION_GUIDANCE,
        )
    if content.startswith(_MEMORY_SESSION_SUMMARY_HEADER):
        return _stripped_prefixed_system_body(
            content,
            prefix=_MEMORY_SESSION_SUMMARY_HEADER,
            section=_SYSTEM_SECTION_CONVERSATION_SUMMARY,
        )
    if content.startswith(_MEMORY_EVIDENCE_FACT_HEADER):
        return _stripped_prefixed_system_body(
            content,
            prefix=_MEMORY_EVIDENCE_FACT_HEADER,
            section=_SYSTEM_SECTION_VERIFIED_EVIDENCE,
        )
    if content.startswith(_MEMORY_ANSWER_ANCHOR_HEADER):
        return _stripped_prefixed_system_body(
            content,
            prefix=_MEMORY_ANSWER_ANCHOR_HEADER,
            section=_SYSTEM_SECTION_PRIOR_ANSWER_ANCHORS,
        )
    if content.startswith(_MEMORY_FORWARD_INTENT_HEADER):
        return _stripped_prefixed_system_body(
            content,
            prefix=_MEMORY_FORWARD_INTENT_HEADER,
            section=_SYSTEM_SECTION_OPEN_FOLLOWUP_CONTEXT,
        )
    if content.startswith(_MEMORY_REFERENCE_CONTINUITY_HEADER):
        return _stripped_prefixed_system_body(
            content,
            prefix=_MEMORY_REFERENCE_CONTINUITY_HEADER,
            section=_SYSTEM_SECTION_REFERENCE_CONTINUITY,
        )
    if content.startswith(_RECENT_EVIDENCE_PREFIX):
        return _stripped_prefixed_system_body(
            content,
            prefix=_RECENT_EVIDENCE_PREFIX,
            section=_SYSTEM_SECTION_RECENT_EVIDENCE,
        )
    if content.startswith(_ACCEPTED_TOOL_EVIDENCE_PREFIX):
        return _stripped_prefixed_system_body(
            content,
            prefix=_ACCEPTED_TOOL_EVIDENCE_PREFIX,
            section=_SYSTEM_SECTION_RECENT_EVIDENCE,
        )
    return (_SYSTEM_SECTION_TASK_INSTRUCTIONS, content)


def _stripped_prefixed_system_body(content: str, *, prefix: str, section: str) -> tuple[str, str]:
    """移除候选 material 内部分类前缀并返回指定 section。

    :param content: 候选 system message 内容。
    :param prefix: 需要移除的固定前缀。
    :param section: envelope section title。
    :returns: ``(section, body)``。
    :raises HostDurableError: 移除前缀后正文为空时抛出。
    """

    body = content.removeprefix(prefix).strip()
    if body == "":
        raise HostDurableError("ordinary system section body must be non-empty")
    return (section, body)


def _non_empty_system_section_blocks(
    sections: Mapping[str, list[str]],
) -> tuple[tuple[str, str, int], ...]:
    """把 section item 映射转为固定顺序的非空 section blocks。

    :param sections: section title 到正文 item 的映射。
    :returns: 固定顺序的 ``(section title, body, item count)`` 元组。
    """

    blocks: list[tuple[str, str, int]] = []
    for section in _SYSTEM_ENVELOPE_SECTION_ORDER:
        items = tuple(item.strip() for item in sections[section] if item.strip() != "")
        if not items:
            continue
        blocks.append((section, "\n".join(items), len(items)))
    return tuple(blocks)


def _render_system_envelope(section_blocks: tuple[tuple[str, str, int], ...]) -> str:
    """按设计固定标题与分隔符渲染 system envelope。

    :param section_blocks: 非空 section blocks。
    :returns: system envelope content。
    """

    rendered_sections = tuple(
        f"{_SYSTEM_ENVELOPE_HEADER_PREFIX}{section}\n{body}" for section, body, _item_count in section_blocks
    )
    return _SYSTEM_ENVELOPE_SEPARATOR.join(rendered_sections)


def _validate_system_envelope_content(
    content: str,
    *,
    source_system_chars: int,
    section_blocks: tuple[tuple[str, str, int], ...],
) -> None:
    """校验 system envelope 的 boundedness 与 LLM-facing 内部字段边界。

    :param content: 合并后的 system envelope。
    :param source_system_chars: 候选 system material 字符数总和。
    :param section_blocks: 非空 section blocks。
    :returns: ``None``。
    :raises HostDurableError: envelope 膨胀异常或包含内部治理标识时抛出。
    """

    overhead = _system_envelope_overhead(section_blocks)
    if len(content) > source_system_chars + overhead:
        raise HostDurableError("ordinary system envelope exceeded deterministic overhead")
    for fragment in _SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS:
        if fragment in content:
            raise HostDurableError("ordinary system envelope exposes internal governance material")


def _system_envelope_overhead(section_blocks: tuple[tuple[str, str, int], ...]) -> int:
    """计算 envelope 固定 header 与 separator 开销。

    :param section_blocks: 非空 section blocks。
    :returns: 固定格式开销字符数。
    """

    if not section_blocks:
        return 0
    header_chars = sum(
        len(_SYSTEM_ENVELOPE_HEADER_PREFIX) + len(section) + 1 for section, _body, _item_count in section_blocks
    )
    separator_chars = len(_SYSTEM_ENVELOPE_SEPARATOR) * (len(section_blocks) - 1)
    item_separator_chars = sum(item_count - 1 for _section, _body, item_count in section_blocks)
    return header_chars + separator_chars + item_separator_chars


def _raise_unsupported_agent_message(message: NoReturn) -> NoReturn:
    """对 AgentMessage 封闭联合做穷尽性防线。

    :param message: 静态类型上不可达的 message。
    :returns: 永不返回。
    :raises HostDurableError: 始终抛出。
    """

    raise HostDurableError(f"unsupported AgentMessage type: {type(message).__name__}")


@dataclass(frozen=True, slots=True)
class _SelectedMaterialRenderView:
    """已选 material 的渲染视图。

    :param selected_blocks: 已选 blocks，保持原 material view 顺序。
    :param current_input_block: 已选 current input anchor。
    :param source_refs: 已选 blocks 的 canonical source refs。
    :param material_view_digest: 已选 material view digest。
    """

    selected_blocks: tuple[RunInputMaterialBlock, ...]
    current_input_block: RunInputMaterialBlock
    source_refs: tuple[str, ...]
    material_view_digest: str


def _fallback_context_messages(
    *,
    fallback: ActiveRecentWindowFallback,
    material_blocks: tuple[RunInputMaterialBlock, ...],
) -> tuple[AgentMessage, ...]:
    """按 fallback selected block ids 渲染 bounded context messages。

    :param fallback: active fallback view。
    :param material_blocks: fallback 使用的 frozen material blocks。
    :returns: fallback bounded context messages，不包含当前 input anchor。
    :raises HostDurableError: fallback view 与 material view 不一致时抛出。
    """

    render_view = _selected_material_render_view(
        fallback=fallback,
        material_blocks=material_blocks,
    )
    messages: list[AgentMessage] = []
    for block in render_view.selected_blocks:
        if block.block_id == render_view.current_input_block.block_id:
            continue
        messages.append(_fallback_message_from_material_block(block))
    return tuple(messages)


def _selected_material_render_view(
    *,
    fallback: ActiveRecentWindowFallback,
    material_blocks: tuple[RunInputMaterialBlock, ...],
) -> _SelectedMaterialRenderView:
    """从 frozen material view 取回 selected blocks 并校验 provenance。

    :param fallback: active fallback view。
    :param material_blocks: fallback 使用的 frozen material blocks。
    :returns: 可渲染的 selected material view。
    :raises HostDurableError: selected id、source refs、digest 或 protected group
        与 material view 不一致时抛出。
    """

    _validate_material_block_ids_unique(material_blocks)
    selected_ids = frozenset(fallback.selected_block_ids)
    if len(selected_ids) != len(fallback.selected_block_ids):
        raise HostDurableError("fallback selected block ids must be unique")
    selected_blocks = tuple(block for block in material_blocks if block.block_id in selected_ids)
    if len(selected_blocks) != len(selected_ids):
        raise HostDurableError("fallback selected block id is missing from material view")
    current_block = _selected_current_input_block(
        selected_blocks,
        current_input_ref=fallback.current_input_ref,
    )
    source_refs = _material_source_refs(selected_blocks)
    if source_refs != fallback.source_refs:
        raise HostDurableError("fallback selected source refs mismatch")
    if (
        fallback.fallback_input_window is not None
        and fallback_window_digest(fallback.fallback_input_window) != fallback.fallback_input_digest
    ):
        raise HostDurableError("fallback input digest mismatch")
    view_digest = selected_material_view_digest(selected_blocks)
    if fallback.selected_material_view_digest is not None and fallback.selected_material_view_digest != view_digest:
        raise HostDurableError("fallback selected material view digest mismatch")
    _validate_fallback_protected_groups(
        fallback=fallback,
        material_blocks=material_blocks,
        selected_blocks=selected_blocks,
    )
    return _SelectedMaterialRenderView(
        selected_blocks=selected_blocks,
        current_input_block=current_block,
        source_refs=source_refs,
        material_view_digest=view_digest,
    )


def _validate_material_block_ids_unique(
    material_blocks: tuple[RunInputMaterialBlock, ...],
) -> None:
    """校验 material view block ids 唯一。

    :param material_blocks: fallback 使用的 frozen material blocks。
    :returns: ``None``。
    :raises HostDurableError: block id 重复时抛出。
    """

    block_ids = tuple(block.block_id for block in material_blocks)
    if len(frozenset(block_ids)) != len(block_ids):
        raise HostDurableError("material view block ids must be unique")


def _selected_current_input_block(
    selected_blocks: tuple[RunInputMaterialBlock, ...],
    *,
    current_input_ref: str,
) -> RunInputMaterialBlock:
    """读取 selected view 中唯一 current input anchor。

    :param selected_blocks: 已选 blocks。
    :param current_input_ref: fallback 绑定的当前输入 ref。
    :returns: current input anchor block。
    :raises HostDurableError: current input ref 不匹配时抛出。
    """

    current_blocks = tuple(
        block
        for block in selected_blocks
        if block.section is CompactMaterialSection.CURRENT_INPUT_ANCHOR
        and current_input_ref in block.canonical_source_refs
    )
    if len(current_blocks) != 1:
        raise HostDurableError("fallback current_input_ref mismatch")
    return current_blocks[0]


def _material_source_refs(
    blocks: tuple[RunInputMaterialBlock, ...],
) -> tuple[str, ...]:
    """收集 material blocks 的 canonical source refs。

    :param blocks: material blocks。
    :returns: 去重后的 canonical source refs。
    """

    refs: list[str] = []
    for block in blocks:
        refs.extend(block.canonical_source_refs)
    return tuple(dict.fromkeys(refs))


def _validate_fallback_protected_groups(
    *,
    fallback: ActiveRecentWindowFallback,
    material_blocks: tuple[RunInputMaterialBlock, ...],
    selected_blocks: tuple[RunInputMaterialBlock, ...],
) -> None:
    """校验 fallback protected turn-group floor 没有漂移。

    :param fallback: active fallback view。
    :param material_blocks: fallback 使用的 frozen material blocks。
    :param selected_blocks: 已选 material blocks。
    :returns: ``None``。
    :raises HostDurableError: protected group 或 raw turn 计数不一致时抛出。
    """

    if fallback.selected_raw_turn_count is not None:
        selected_raw_turn_count = sum(1 for block in selected_blocks if is_turn_group_material_block(block))
        if selected_raw_turn_count != fallback.selected_raw_turn_count:
            raise HostDurableError("fallback selected raw turn count mismatch")
    if fallback.selected_recent_window_turn_floor is None:
        return
    if fallback.selected_recent_window_turn_floor == 0:
        return
    try:
        protected_group_ids = protected_recent_turn_group_ids_for_material_blocks(
            material_blocks,
            selected_recent_window_turn_floor=(fallback.selected_recent_window_turn_floor),
        )
    except ValueError as exc:
        raise HostDurableError("fallback protected turn_group_id consistency mismatch") from exc
    selected_ids = frozenset(block.block_id for block in selected_blocks)
    expected_protected_ids = frozenset(
        block.block_id
        for block in material_blocks
        if block.turn_group_id in protected_group_ids and is_turn_group_material_block(block)
    )
    if not expected_protected_ids.issubset(selected_ids):
        raise HostDurableError("fallback protected group consistency mismatch")


def _fallback_message_from_material_block(block: RunInputMaterialBlock) -> AgentMessage:
    """把 fallback material block 渲染为 Engine message。

    :param block: selected fallback material block。
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
    if block.kind is CompactMaterialBlockKind.EVIDENCE_BACKED_FACT:
        return SystemMessage(role=AgentMessageRole.SYSTEM, content=block.text)
    if block.section is CompactMaterialSection.EVIDENCE_MATERIAL:
        return SystemMessage(
            role=AgentMessageRole.SYSTEM,
            content=_recent_evidence_content(block.text),
        )
    return SystemMessage(role=AgentMessageRole.SYSTEM, content=block.text)


def _recent_evidence_content(text: str) -> str:
    """构造 recent evidence 的 LLM-facing 有界正文。

    :param text: 已由上游预算治理的 evidence 文本。
    :returns: 带 recent evidence 前缀的 system material。
    """

    return f"{_RECENT_EVIDENCE_PREFIX}\n{text}"


def _run_input_message_content(message: AgentMessage) -> str:
    """读取 AgentMessage 文本内容。

    :param message: Agent message。
    :returns: message content。
    :raises TypeError: message 类型非法时抛出。
    """

    if isinstance(message, SystemMessage):
        return message.content
    if isinstance(message, UserMessage):
        return message.content
    if isinstance(message, AssistantMessage):
        if message.content is None:
            raise TypeError("assistant material message content must be non-empty")
        return message.content
    raise TypeError("unsupported AgentMessage type for material block")


def _material_section_for_message(message: AgentMessage) -> CompactMaterialSection:
    """根据 message role 判断 material section。

    :param message: Agent message。
    :returns: material section。
    """

    if isinstance(message, SystemMessage):
        return CompactMaterialSection.PREVIOUS_COMPACTED_VIEW
    if isinstance(message, AssistantMessage):
        return CompactMaterialSection.ANSWER_MATERIAL
    return CompactMaterialSection.TRACE_MATERIAL


def _memory_material_kind(message: AgentMessage) -> CompactMaterialBlockKind:
    """根据 memory message 内容选择 material kind。

    :param message: memory message。
    :returns: material block kind。
    """

    content = _run_input_message_content(message)
    if content.startswith(_MEMORY_EVIDENCE_FACT_HEADER):
        return CompactMaterialBlockKind.EVIDENCE_BACKED_FACT
    if content.startswith(_MEMORY_FORWARD_INTENT_HEADER):
        return CompactMaterialBlockKind.FORWARD_INTENT
    if content.startswith(_MEMORY_ANSWER_ANCHOR_HEADER):
        return CompactMaterialBlockKind.ANSWER_ANCHOR
    if content.startswith(_MEMORY_REFERENCE_CONTINUITY_HEADER):
        return CompactMaterialBlockKind.REFERENCE_CONTINUITY
    if content.startswith(_MEMORY_SESSION_SUMMARY_HEADER):
        return CompactMaterialBlockKind.SESSION_SUMMARY
    if isinstance(message, UserMessage):
        return CompactMaterialBlockKind.USER_INPUT
    if isinstance(message, AssistantMessage):
        return CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER
    return CompactMaterialBlockKind.SESSION_SUMMARY


def _history_material_kind(message: AgentMessage) -> CompactMaterialBlockKind:
    """根据 continuity message role 选择 history material kind。

    :param message: continuity message。
    :returns: material block kind。
    """

    if isinstance(message, UserMessage):
        return CompactMaterialBlockKind.USER_INPUT
    if isinstance(message, AssistantMessage):
        return CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER
    return CompactMaterialBlockKind.SESSION_SUMMARY


def _memory_material_source_ref(memory: MemorySnapshotView) -> str:
    """返回 memory material canonical source ref。

    :param memory: memory snapshot view。
    :returns: source ref。
    """

    if memory.memory_snapshot_cursor is not None:
        return f"memory:{memory.memory_snapshot_cursor}"
    return "memory:no-snapshot"


def _memory_represented_evidence_refs(
    snapshot: ConversationMemorySnapshotVNext,
) -> tuple[str, ...]:
    """返回 stable memory facts 已表示的 accepted evidence refs。

    :param snapshot: memory snapshot。
    :returns: 去重后的 accepted evidence refs。
    """

    refs: list[str] = []
    for fact in snapshot.evidence_fact_memory.evidence_backed_facts:
        refs.extend(fact.evidence_refs)
    return tuple(dict.fromkeys(refs))


def _require_compact_memory_event_ref_consistency(
    *,
    memory: MemorySnapshotView,
    compact: CompactArtifactView,
    current_facts: CurrentRunFacts,
) -> None:
    """校验 compact artifact 与 memory snapshot 的 latest compact event id 一致。

    :param memory: memory provider view。
    :param compact: compact artifact provider view。
    :param current_facts: 当前 Run facts。
    :returns: ``None``。
    :raises MemoryProjectionRepairRequired: memory 需要 catch-up / rebuild 时抛出。
    :raises HostDurableError: repair request 所需 metadata 缺失时抛出。
    """

    compact_ref = compact.compaction_event_ref
    memory_ref = memory.latest_compaction_event_ref
    if compact_ref is None and memory_ref is None:
        return
    if compact_ref is not None and memory_ref == compact_ref:
        return
    if memory.policy_digest is None:
        raise HostDurableError("memory policy digest is required for compaction repair")
    raise MemoryProjectionRepairRequired(
        MemoryRepairRequest(
            session_id=current_facts.run.session_id,
            reason=MemoryRepairReason.SNAPSHOT_DAMAGED,
            required_event_sequence=_required_memory_event_sequence(current_facts),
            observed_cursor=None,
            policy_digest=memory.policy_digest,
        )
    )


def _represented_evidence_refs(memory: MemorySnapshotView, compact: CompactArtifactView) -> tuple[str, ...]:
    """合并 memory 与 compact artifact 已表示的 evidence refs。

    :param memory: memory provider view。
    :param compact: compact artifact provider view。
    :returns: 去重后的 accepted evidence refs。
    """

    return tuple(
        dict.fromkeys(
            (
                *memory.represented_evidence_refs,
                *compact.represented_evidence_refs,
            )
        )
    )


def _memory_cursor_ref(cursor: MemorySnapshotCursor) -> str:
    """渲染 memory snapshot cursor ref。

    :param cursor: memory snapshot cursor。
    :returns: 稳定 cursor ref。
    """

    event_id = "" if cursor.checkpoint_event_id is None else cursor.checkpoint_event_id
    return (
        f"consumer_id={cursor.consumer_id};"
        f"session_id={cursor.session_id};"
        f"checkpoint_event_sequence={cursor.checkpoint_event_sequence};"
        f"checkpoint_event_id={event_id}"
    )


def _memory_projection_event_from_row(transaction: HostTransaction, row: EventLogRow) -> MemoryProjectionEvent:
    """把 EventLog row 转换为 memory projection event。

    :param transaction: Host transaction。
    :param row: EventLog row。
    :returns: memory projection event。
    :raises HostDurableError: payload 不是 JSON object 时抛出。
    :raises ValueError: persisted compact semantic payload 非法时抛出。
    """

    payload = _memory_projection_payload(transaction, row)
    accepted_tool_projection = (
        project_accepted_tool_result(
            transaction,
            row,
            resolved_payload=payload,
        )
        if row.event_type == _EVENT_TYPE_TOOL_RESULT_ACCEPTED
        else None
    )
    if accepted_tool_projection is not None and accepted_tool_projection.llm_material is None:
        raise HostDurableError("TOOL_RESULT_ACCEPTED typed LLM material is missing")
    return MemoryProjectionEvent(
        event_sequence=row.event_sequence,
        event_id=row.event_id,
        event_class=row.event_class.value,
        event_type=row.event_type,
        session_id=row.session_id,
        run_id=row.run_id,
        attempt_id=row.attempt_id,
        execution_id=row.execution_id,
        occurred_at=row.occurred_at,
        payload_ref=row.payload_ref,
        payload_digest=row.payload_digest,
        payload=payload,
        compacted_semantics=(
            parse_context_compacted_semantic_payload(payload) if row.event_type == CONTEXT_COMPACTED else None
        ),
        assistant_final_answer_text=_assistant_final_answer_text(
            transaction,
            row,
            payload,
        ),
        accepted_tool_evidence=(None if accepted_tool_projection is None else accepted_tool_projection.llm_material),
    )


def _memory_projection_payload(
    transaction: HostTransaction,
    row: EventLogRow,
) -> Mapping[str, JsonValue]:
    """读取 memory inline repair 使用的 payload。

    :param transaction: Host transaction。
    :param row: EventLog row。
    :returns: memory projection 消费的 payload。
    :raises HostDurableError: terminal artifact descriptor 或工具 payload 损坏时抛出。
    """

    if row.event_type == CONTEXT_COMPACTED:
        return resolve_context_compacted_payload(transaction, row)
    return _payload_object(row)


def _assistant_final_answer_text(
    transaction: HostTransaction,
    row: EventLogRow,
    payload: Mapping[str, JsonValue],
) -> str | None:
    """读取 RUN_SUCCEEDED 的 typed assistant final-answer continuity 文本。

    :param transaction: Host transaction。
    :param row: EventLog row。
    :param payload: 已解析 canonical payload。
    :returns: LLM-facing assistant answer 文本；非成功终态或缺失时返回 ``None``。
    :raises HostDurableError: terminal artifact descriptor 损坏时抛出。
    """

    if row.event_type != _EVENT_TYPE_RUN_SUCCEEDED:
        return None
    return assistant_final_answer_continuity_text(
        transaction,
        payload,
        text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
    )


def _latest_compacted_event_before_attempt(
    transaction: HostTransaction, current_facts: CompactPipelineCurrentRunFacts
) -> EventLogRow | None:
    """读取当前 Session 在 Attempt start cursor 前最新 ``CONTEXT_COMPACTED``。

    :param transaction: Host durable transaction。
    :param current_facts: 当前 Run facts。
    :returns: 最新 compacted event；不存在时为 ``None``。
    """

    rows = transaction.fetchall(
        f"""
        SELECT event_id
        FROM {TABLE_EVENT_LOG}
        WHERE session_id = ?
          AND event_type = ?
          AND event_class = ?
          AND event_sequence < ?
        ORDER BY event_sequence DESC
        LIMIT 1
        """,
        (
            current_facts.run.session_id,
            CONTEXT_COMPACTED,
            EventClass.CANONICAL_FACT.value,
            current_facts.attempt.started_event_sequence,
        ),
    )
    if len(rows) == 0:
        return None
    event_id = _required_host_row_text(rows[0], field_name="event_id")
    event = EventLogStore().read_event_by_id(transaction, event_id)
    if event is None:
        raise HostDurableError("CONTEXT_COMPACTED event disappeared during read")
    return event


def _validate_loaded_compact_view_matches_event(
    transaction: HostTransaction,
    *,
    compact: CompactPipelineCompactArtifactView,
    compacted_event: EventLogRow,
) -> None:
    """校验 compact provider view 来自同一个 session latest compact event。

    :param transaction: 当前 Host transaction。
    :param compact: compact provider view。
    :param compacted_event: current Run / current Attempt 前的 compacted event。
    :returns: ``None``。
    :raises HostDurableError: artifact ref 或 digest 不一致时抛出。
    """

    payload = resolve_context_compacted_payload(transaction, compacted_event)
    artifact_ref = _required_text_field(payload, _PAYLOAD_FIELD_COMPACT_ARTIFACT_REF)
    artifact_digest = _required_text_field(payload, _PAYLOAD_FIELD_COMPACT_ARTIFACT_DIGEST)
    if compact.compact_artifact_ref != artifact_ref:
        raise HostDurableError("compact artifact ref does not match current run")
    if compact.compact_artifact_digest != artifact_digest:
        raise HostDurableError("compact artifact digest does not match current run")


def _compaction_trigger_source_for_compacted_event(
    transaction: HostTransaction,
    *,
    compacted_event: EventLogRow,
) -> ContextCompactionTriggerSource:
    """读取 compacted event 对应 requested fact 的 trigger source。

    :param transaction: Host transaction。
    :param compacted_event: current Run / current Attempt 前的 compacted event。
    :returns: compaction trigger source。
    :raises HostDurableError: requested fact 缺失或 trigger source 非法时抛出。
    """

    compacted_payload = resolve_context_compacted_payload(
        transaction,
        compacted_event,
    )
    operation_id = _required_text_field(
        compacted_payload,
        _PAYLOAD_FIELD_OPERATION_ID,
    )
    requested_event = EventLogStore().read_event_by_id(transaction, operation_id)
    if requested_event is None or requested_event.event_type != CONTEXT_COMPACTION_REQUESTED:
        raise HostDurableError("compaction requested event is missing")
    requested_payload = _payload_object(requested_event)
    trigger_value = _required_text_field(
        requested_payload,
        _PAYLOAD_FIELD_TRIGGER_SOURCE,
    )
    try:
        return ContextCompactionTriggerSource(trigger_value)
    except ValueError as exc:
        raise HostDurableError("compaction trigger source is invalid") from exc


def _text_content_digest(text: str) -> str:
    """计算 LLM-readable 文本 digest。

    :param text: LLM-readable 文本。
    :returns: sha256 digest。
    """

    return sha256_digest_json({"text": text})


def _required_text_field(payload: Mapping[str, JsonValue], field_name: str) -> str:
    """读取必填文本字段。

    :param payload: payload 映射。
    :param field_name: 字段名。
    :returns: 文本字段值。
    :raises HostDurableError: 字段缺失或非文本时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, str) or value.strip() == "":
        raise HostDurableError(f"payload field {field_name} must be text")
    return value


def _optional_mapping_text(payload: Mapping[str, JsonValue], field_name: str) -> str | None:
    """从 mapping 读取可选文本字段。

    :param payload: payload 映射。
    :param field_name: 字段名。
    :returns: 文本或 ``None``。
    """

    value = payload.get(field_name)
    if isinstance(value, str) and value.strip() != "":
        return value
    return None


def _required_host_row_text(row: HostRow, *, field_name: str) -> str:
    """读取 HostRow 中必填文本字段。

    :param row: Host row。
    :param field_name: 字段名。
    :returns: 文本字段。
    :raises HostDurableError: 字段缺失或非文本时抛出。
    """

    value = row.get(field_name)
    if not isinstance(value, str) or value.strip() == "":
        raise HostDurableError(f"Host row field {field_name} must be text")
    return value


def _system_prompt_message(system_prompt: str | None) -> tuple[SystemMessage, ...]:
    """把可选 public system prompt 转为 Engine system message。

    :param system_prompt: admission 冻结的 system prompt。
    :returns: 空元组或单条 system message。
    """

    if system_prompt is None:
        return ()
    return (SystemMessage(role=AgentMessageRole.SYSTEM, content=system_prompt),)


def _current_user_tail_messages(
    current_facts: CurrentRunFacts,
    continuity: SessionContinuityView,
) -> tuple[UserMessage, ...]:
    """返回普通 dispatch 需要追加的当前用户消息。

    resume continuity 若已经重建 ``user -> assistant(tool_call) -> tool``
    闭环，则当前用户消息已在 continuity 中，不能再次追加到末尾。

    :param current_facts: 当前 Run facts。
    :param continuity: session continuity view。
    :returns: 需要追加的当前用户消息；resume 工具闭环已包含时为空。
    """

    if _continuity_contains_current_user(current_facts, continuity):
        return ()
    return (
        UserMessage(
            role=AgentMessageRole.USER,
            content=current_facts.user_prompt,
        ),
    )


def _continuity_contains_current_user(
    current_facts: CurrentRunFacts,
    continuity: SessionContinuityView,
) -> bool:
    """判断 continuity 是否已包含当前用户输入。

    ``DurableSessionContinuityProvider`` 当前只返回 resume 专用的
    ``user -> assistant(tool_call) -> tool`` 消息，不拼接 memory 或 snapshot 前缀。
    这里仍遍历完整 continuity，避免未来 provider 组合调整后因前缀消息导致当前
    用户输入被重复追加。

    :param current_facts: 当前 Run facts。
    :param continuity: session continuity view。
    :returns: 任一 continuity 用户消息等于当前用户输入时返回 ``True``。
    """

    for message in continuity.messages:
        if isinstance(message, UserMessage) and message.content == current_facts.user_prompt:
            return True
    return False


def _optional_payload_text(payload: Mapping[str, JsonValue], *, field_name: str) -> str | None:
    """读取 payload 中的可选文本字段。

    :param payload: payload 映射。
    :param field_name: 字段名。
    :returns: 文本值或 ``None``。
    :raises HostDurableError: 字段存在但不是文本时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise HostDurableError(f"payload field {field_name} must be text")
    if value.strip() == "":
        return None
    return value


def _execution_target_from_accepted_event(event: EventLogRow, *, fallback: str) -> str:
    """从 RUN_ACCEPTED payload 读取 execution target。

    :param event: RUN_ACCEPTED event。
    :param fallback: payload 缺失时使用的 Run row execution target。
    :returns: execution target。
    :raises HostDurableError: payload 字段类型非法时抛出。
    """

    payload = _payload_object(event)
    value = _optional_payload_text(payload, field_name=_PAYLOAD_FIELD_EXECUTION_TARGET)
    if value is None:
        return fallback
    return value


def _resume_wait_continuity_from_current_start(
    transaction: HostTransaction, current_facts: CurrentRunFacts
) -> SessionContinuityView:
    """从当前 resume ``RUN_STARTED`` 重建 wait result continuation。

    :param transaction: Host durable transaction。
    :param current_facts: 当前 Run facts。
    :returns: resume continuation；非 resume Attempt 返回显式空 view。
    :raises HostDurableError: resume payload 或引用事件无法投影时抛出。
    """

    start_payload = _payload_object(current_facts.run_started_event)
    started_payload = decode_run_started_payload(start_payload)
    if started_payload.start_reason is not RunStartReason.RESUME:
        return SessionContinuityView(messages=(), source_refs=())
    tool_result_event_id = _event_id_from_payload_ref(start_payload, field_name=_PAYLOAD_FIELD_TOOL_RESULT_EVENT_REF)
    tool_result_event = read_event_by_id(transaction, tool_result_event_id)
    if tool_result_event is None:
        raise HostDurableError("resume tool result event not found")
    _require_event(
        tool_result_event,
        expected_type=_EVENT_TYPE_TOOL_RESULT_ACCEPTED,
    )
    projection = project_accepted_tool_result(transaction, tool_result_event)
    request_event_ref = projection.tool_call_requested_event_ref
    if request_event_ref is None:
        raise HostDurableError("resume wait tool-call requested event ref is missing")
    return project_wait_resume_continuity(
        user_prompt=current_facts.user_prompt,
        accepted_result=projection,
        source_refs=(request_event_ref, tool_result_event.event_id),
    )


def project_wait_resume_continuity(
    *,
    user_prompt: str,
    accepted_result: AcceptedToolResultProjection,
    source_refs: tuple[str, ...],
) -> SessionContinuityView:
    """把 typed completed/cancelled accepted result 投影为唯一 resume continuity。

    :param user_prompt: source Run 当前用户输入。
    :param accepted_result: accepted-result owner 产出的 strict typed projection。
    :param source_refs: exact request/result canonical event refs。
    :returns: ``user -> assistant(tool_call) -> tool(result)`` continuity。
    :raises HostDurableError: status、工具 identity、request arguments、raw outcome
        或 source refs 不完整时抛出。
    """

    if user_prompt.strip() == "":
        raise HostDurableError("resume wait user prompt must be non-empty")
    if accepted_result.status not in (
        AcceptedToolResultStatus.COMPLETED,
        AcceptedToolResultStatus.CANCELLED,
    ):
        raise HostDurableError("resume wait accepted result is not resumable")
    if (
        accepted_result.tool_call_id is None
        or accepted_result.tool_call_id.strip() == ""
        or accepted_result.tool_name is None
        or accepted_result.tool_name.strip() == ""
    ):
        raise HostDurableError("resume wait tool identity is incomplete")
    if (
        len(source_refs) == 0
        or len(set(source_refs)) != len(source_refs)
        or any(ref.strip() == "" for ref in source_refs)
    ):
        raise HostDurableError("resume wait source refs are invalid")
    if accepted_result.raw_outcome is None:
        raise HostDurableError("resume wait raw outcome is missing")
    accepted_arguments = _resume_wait_accepted_arguments(
        projection=accepted_result,
    )
    tool_call_id = accepted_result.tool_call_id
    tool_name = accepted_result.tool_name
    return SessionContinuityView(
        messages=(
            UserMessage(role=AgentMessageRole.USER, content=user_prompt),
            AssistantMessage(
                role=AgentMessageRole.ASSISTANT,
                content=None,
                reasoning_content=None,
                tool_calls=(
                    AssistantToolCall(
                        id=tool_call_id,
                        name=tool_name,
                        arguments=accepted_arguments,
                        provider_state=None,
                    ),
                ),
            ),
            ToolMessage(
                role=AgentMessageRole.TOOL,
                tool_call_id=tool_call_id,
                content=_resume_wait_tool_message_content({"raw_tool_outcome": accepted_result.raw_outcome}),
            ),
        ),
        source_refs=source_refs,
    )


def _resume_wait_accepted_arguments(
    *,
    projection: AcceptedToolResultProjection,
) -> Mapping[str, JsonValue]:
    """读取 resume 等待工具调用的 exact canonical request atom 参数。

    :param projection: accepted result 共享投影。
    :returns: Host 已接受的精确工具参数。
    :raises HostDurableError: canonical request arguments 缺失或结构非法时抛出。
    """

    if projection.request_arguments_json is None:
        raise HostDurableError("resume wait request arguments are missing")
    value = projection.request_arguments_json.get(_PAYLOAD_FIELD_ARGUMENTS)
    if not isinstance(value, Mapping):
        raise HostDurableError("resume wait request arguments must be object")
    accepted_arguments = dict(value)
    return accepted_arguments


def _resume_wait_tool_message_content(
    tool_result_payload: Mapping[str, JsonValue],
) -> str:
    """把 wait resolution result 投影为 LLM-facing tool message content。

    :param tool_result_payload: ``TOOL_RESULT_ACCEPTED`` payload。
    :returns: 与 Engine 普通工具注入一致的扁平 JSON 字符串。
    :raises HostDurableError: result 结构缺失或非法时抛出。
    """

    result = tool_result_payload.get("raw_tool_outcome")
    if not isinstance(result, Mapping):
        raise HostDurableError("resume wait raw_tool_outcome must be object")
    kind = _required_payload_text(result, field_name="kind")
    if kind == "completed":
        body = _required_resume_tool_result_body(result)
        projected = _resume_wait_completed_tool_content(body)
    elif kind == "failed":
        body = _required_resume_tool_result_body(result)
        projected = _resume_wait_failed_tool_content(body)
    elif kind == "cancelled":
        projected = _resume_wait_cancelled_tool_content(result)
    else:
        raise HostDurableError("resume wait result kind is not resumable")
    return json.dumps(projected, ensure_ascii=False, sort_keys=True)


def _required_resume_tool_result_body(
    raw_tool_outcome: Mapping[str, JsonValue],
) -> Mapping[str, JsonValue]:
    """读取 canonical completed / failed outcome 的 result body。

    :param raw_tool_outcome: accepted tool outcome canonical atom。
    :returns: ``result`` 字段中的 JSON object。
    :raises HostDurableError: ``result`` 缺失或非 object 时抛出。
    """

    body = raw_tool_outcome.get("result")
    if not isinstance(body, Mapping):
        raise HostDurableError("resume wait raw_tool_outcome.result must be object")
    return body


def _resume_wait_completed_tool_content(
    result_body: Mapping[str, JsonValue],
) -> Mapping[str, JsonValue]:
    """投影 completed wait result 的 tool message JSON。

    :param result_body: completed result body。
    :returns: LLM-facing JSON object。
    """

    value = result_body.get("value")
    if isinstance(value, Mapping):
        return dict(value)
    return {"content": value}


def _resume_wait_failed_tool_content(
    result_body: Mapping[str, JsonValue],
) -> Mapping[str, JsonValue]:
    """投影 failed wait result 的 tool message JSON。

    :param result_body: failed result body。
    :returns: LLM-facing JSON object。
    :raises HostDurableError: 必填错误字段缺失时抛出。
    """

    projected: dict[str, JsonValue] = {
        "error": _required_payload_text(result_body, field_name="error"),
        "message": _required_payload_text(result_body, field_name="message"),
    }
    hint = _optional_payload_text(result_body, field_name="hint")
    if hint is not None:
        projected["hint"] = hint
    return projected


def _resume_wait_cancelled_tool_content(
    result_body: Mapping[str, JsonValue],
) -> Mapping[str, JsonValue]:
    """投影 cancelled wait result 的 tool message JSON。

    :param result_body: cancelled result body。
    :returns: LLM-facing JSON object。
    :raises HostDurableError: 必填取消字段缺失时抛出。
    """

    projected: dict[str, JsonValue] = {
        "cancelled": True,
        "reason": _required_payload_text(result_body, field_name="reason"),
        "message": _required_payload_text(result_body, field_name="message"),
    }
    hint = _optional_payload_text(result_body, field_name="hint")
    if hint is not None:
        projected["hint"] = hint
    return projected


def _event_id_from_payload_ref(payload: Mapping[str, JsonValue], *, field_name: str) -> str:
    """从 payload 中读取嵌套 event ref 的 event_id。

    :param payload: payload 映射。
    :param field_name: event ref 字段名。
    :returns: event_id 文本。
    :raises HostDurableError: 字段缺失或类型非法时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        raise HostDurableError(f"payload field {field_name} must be event ref")
    event_id = value.get(_PAYLOAD_FIELD_EVENT_ID)
    if not isinstance(event_id, str) or event_id.strip() == "":
        raise HostDurableError(f"payload field {field_name}.event_id is invalid")
    return event_id


def _validate_tool_mode_snapshot(
    tool_execution_mode: ToolExecutionMode,
    tool_snapshot: ToolSchemaSnapshot,
    policy_snapshot: PolicySnapshot,
    tool_executor: ToolExecutor,
) -> None:
    """按显式工具模式校验 request 约束。

    :param tool_execution_mode: 显式工具执行模式。
    :param tool_snapshot: tool schema snapshot。
    :param policy_snapshot: policy snapshot。
    :param tool_executor: ToolExecutor provider 输出。
    :returns: ``None``。
    :raises HostDurableError: provider 违反对应工具模式约束时抛出。
    """

    if tool_execution_mode == ToolExecutionMode.TOOL_ENABLED:
        _validate_tool_enabled_snapshot(tool_snapshot, policy_snapshot, tool_executor)
        return
    _validate_no_tool_snapshot(tool_snapshot, policy_snapshot)


def _validate_no_tool_snapshot(tool_snapshot: ToolSchemaSnapshot, policy_snapshot: PolicySnapshot) -> None:
    """校验 no-tool request 约束。

    :param tool_snapshot: tool schema snapshot。
    :param policy_snapshot: policy snapshot。
    :returns: ``None``。
    :raises HostDurableError: provider 违反 no-tool 约束时抛出。
    """

    if not tool_snapshot.disable_tools:
        raise HostDurableError("RunInputBuilder requires disable_tools=True")
    if tool_snapshot.tool_schemas:
        raise HostDurableError("RunInputBuilder no-tool schema snapshot must be empty")
    if policy_snapshot.agent_policy.allow_tool_calls:
        raise HostDurableError("RunInputBuilder requires allow_tool_calls=False")
    if tool_snapshot.tool_runtime_handle is not None:
        raise HostDurableError("RunInputBuilder no-tool mode must not carry handle")


def _validate_tool_enabled_snapshot(
    tool_snapshot: ToolSchemaSnapshot,
    policy_snapshot: PolicySnapshot,
    tool_executor: ToolExecutor,
) -> None:
    """校验 tool-enabled request 约束。

    :param tool_snapshot: tool schema snapshot。
    :param policy_snapshot: policy snapshot。
    :param tool_executor: ToolExecutor provider 输出。
    :returns: ``None``。
    :raises HostDurableError: provider 违反 tool-enabled 约束时抛出。
    """

    if tool_snapshot.disable_tools:
        raise HostDurableError("RunInputBuilder requires disable_tools=False")
    if not policy_snapshot.agent_policy.allow_tool_calls:
        raise HostDurableError("RunInputBuilder requires allow_tool_calls=True")
    if tool_snapshot.tool_runtime_handle is None:
        raise HostDurableError("RunInputBuilder tool-enabled mode requires handle")
    if tool_snapshot.tool_runtime_handle.tool_schemas != tool_snapshot.tool_schemas:
        raise HostDurableError("RunInputBuilder tool schemas must come from ToolRuntimeHandle")
    if tool_snapshot.tool_runtime_handle.tool_executor is not tool_executor:
        raise HostDurableError("RunInputBuilder tool executor must come from same ToolRuntimeHandle")


def _find_existing_runner_call_manifest_event(
    transaction: HostTransaction,
    *,
    run: RunRow,
    attempt_id: str,
    execution_id: str,
) -> EventLogRow | None:
    """查找同一 attempt/execution 已写入的 runner-call manifest event。

    :param transaction: 当前 Host transaction。
    :param run: 当前 source Run row。
    :param attempt_id: 当前 Attempt id。
    :param execution_id: 当前 execution id。
    :returns: 已存在的 manifest event；不存在时返回 ``None``。
    :raises HostDurableError: EventLog row、hot payload、caller 或 source
        identity 不同源，或同一 identity 出现重复 manifest 时抛出。
    """

    rows = transaction.fetchall(
        f"""
        SELECT event_id
        FROM {TABLE_EVENT_LOG}
        WHERE run_id = ?
          AND event_type = ?
        ORDER BY event_sequence ASC
        """,
        (run.run_id, _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED),
    )
    event_log_store = EventLogStore()
    matched: EventLogRow | None = None
    for row in rows:
        event_id = row.get("event_id")
        if not isinstance(event_id, str):
            raise HostDurableError("runner-call manifest event_id is invalid")
        event = event_log_store.read_event_by_id(transaction, event_id)
        if event is None:
            raise HostDurableError("runner-call manifest event row is missing")
        if (
            event.event_class is not EventClass.CANONICAL_FACT
            or event.event_type != _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED
            or event.session_id != run.session_id
            or event.run_id != run.run_id
        ):
            raise HostDurableError("runner-call manifest EventLog identity is invalid")
        try:
            hot = parse_runner_call_hot_payload(_payload_object(event))
        except (HostDurableError, TypeError, ValueError) as exc:
            raise HostDurableError("runner-call manifest hot payload is invalid") from exc
        if (
            hot.session_id != run.session_id
            or hot.host_run_id != run.run_id
            or hot.attempt_id != event.attempt_id
            or hot.execution_id != event.execution_id
        ):
            raise HostDurableError("runner-call manifest EventLog and hot identity mismatch")
        if hot.runner_call_kind == _RUNNER_CALL_KIND_COMPACTOR_PROPOSAL:
            continue
        if event.attempt_id is None or event.execution_id is None:
            raise HostDurableError("runner-call dispatch manifest EventLog identity is incomplete")
        if hot.attempt_id != attempt_id or hot.execution_id != execution_id:
            continue
        if hot.iteration_id is not None or hot.iteration_index is not None:
            continue
        if hot.runner_call_kind not in _PRE_START_RUNNER_CALL_KINDS:
            raise HostDurableError("runner-call manifest pre-start kind is unsupported")
        if matched is not None:
            raise HostDurableError("runner-call manifest identity has duplicate canonical events")
        matched = event
    return matched


def _next_runner_call_index(transaction: HostTransaction, *, run_id: str) -> int:
    """返回当前 Run 下下一个 Host-owned runner_call_index。

    :param transaction: 当前 Host transaction。
    :param run_id: 当前 Run id。
    :returns: 从 0 起的下一个 runner call index。
    :raises HostDurableError: SQLite 返回值非法时抛出。
    """

    row = transaction.fetchone(
        f"""
        SELECT count(*) AS n
        FROM {TABLE_EVENT_LOG}
        WHERE run_id = ?
          AND event_type = ?
        """,
        (run_id, _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED),
    )
    if row is None:
        raise HostDurableError("runner-call manifest count query returned no row")
    value = row.get("n")
    if not isinstance(value, int) or value < 0:
        raise HostDurableError("runner-call manifest count is invalid")
    return value


def _runner_call_manifest_event_id(
    run_id: str,
    attempt_id: str,
    execution_id: str,
    runner_call_index: int,
) -> str:
    """派生 runner-call manifest canonical event id。

    :param run_id: 当前 Run id。
    :param attempt_id: 当前 Attempt id。
    :param execution_id: 当前 execution id。
    :param runner_call_index: Host-owned runner call index。
    :returns: 稳定 event id。
    """

    digest = sha256_digest_json(
        {
            "run_id": run_id,
            "attempt_id": attempt_id,
            "execution_id": execution_id,
            "runner_call_index": runner_call_index,
        }
    )
    return f"{_RUNNER_CALL_EVENT_ID_PREFIX}-{digest.removeprefix('sha256:')}"


def _runner_call_manifest_id(event_id: str) -> str:
    """派生 runner-call manifest logical id。

    :param event_id: manifest canonical event id。
    :returns: manifest id。
    """

    return f"runner-call-manifest:{event_id}"


def _prepared_candidate_payload_ref(candidate_digest: str) -> str:
    """从 candidate digest 派生 Host-private payload ref。

    :param candidate_digest: candidate projection sha256 digest。
    :returns: deterministic payload ref。
    :raises Exception: 不主动抛出异常。
    """

    return f"{_PREPARED_CANDIDATE_PROJECTION_REF_PREFIX}:{candidate_digest.removeprefix('sha256:')}"


def _prepared_candidate_sqlite_payload_id(candidate_digest: str) -> str:
    """从 candidate digest 派生 SQLite payload id。

    :param candidate_digest: candidate projection sha256 digest。
    :returns: deterministic SQLite payload id。
    :raises Exception: 不主动抛出异常。
    """

    return f"sqlite-runner-call-prepared-candidate:{candidate_digest.removeprefix('sha256:')}"


def _runner_call_projection_id(event_id: str) -> str:
    """派生 runner-call projection logical id。

    :param event_id: manifest canonical event id。
    :returns: projection id。
    """

    return f"runner-call-projection:{event_id}"


def _prepared_candidate_projection_body(
    *,
    session_id: str,
    run_id: str,
    candidate_input_cursor: int,
    messages: tuple[AgentMessage, ...],
    tool_schemas: tuple[ToolSchema, ...],
    disable_tools: bool,
    tool_execution_mode: ToolExecutionMode,
    policy_snapshot: PolicySnapshot,
    source_cursor_refs: tuple[str, ...],
    memory_snapshot_cursor_ref: str | None,
    compact_artifact_refs: tuple[str, ...],
    context_fallback_decision_ref: str | None,
    request_semantics_digest: str,
) -> Mapping[str, JsonValue]:
    """构造 identity-free complete candidate digest preimage。

    :param session_id: Session id。
    :param run_id: Run id。
    :param candidate_input_cursor: committed source watermark。
    :param messages: complete normalized messages。
    :param tool_schemas: selected tool schemas。
    :param disable_tools: 是否禁用工具。
    :param tool_execution_mode: frozen 工具执行模式。
    :param policy_snapshot: admission-frozen Engine policy。
    :param source_cursor_refs: source refs。
    :param memory_snapshot_cursor_ref: memory cursor ref。
    :param compact_artifact_refs: compact refs。
    :param context_fallback_decision_ref: fallback ref。
    :param request_semantics_digest: request semantics digest。
    :returns: canonical JSON digest preimage。
    """

    return {
        "schema_version": _PREPARED_CANDIDATE_SCHEMA_VERSION,
        "session_id": session_id,
        "host_run_id": run_id,
        "candidate_input_cursor": candidate_input_cursor,
        "messages": [_prepared_candidate_message_body(index, message) for index, message in enumerate(messages)],
        "tool_schemas": [_tool_schema_json(schema) for schema in tool_schemas],
        "disable_tools": disable_tools,
        "tool_execution_mode": tool_execution_mode.value,
        "policy_snapshot_ref": policy_snapshot.policy_snapshot_ref,
        "policy_snapshot_digest": _engine_policy_snapshot_digest(policy_snapshot),
        "source_cursor_refs": list(source_cursor_refs),
        "memory_snapshot_cursor_ref": memory_snapshot_cursor_ref,
        "compact_artifact_refs": list(compact_artifact_refs),
        "context_fallback_decision_ref": context_fallback_decision_ref,
        "request_semantics_digest": request_semantics_digest,
        "estimator_id": CONTEXT_ESTIMATOR_CONTRACT.estimator_id,
        "estimator_version": CONTEXT_ESTIMATOR_CONTRACT.estimator_version,
    }


def _prepared_candidate_input_snapshot_body(
    *,
    messages: tuple[AgentMessage, ...],
    tool_schemas: tuple[ToolSchema, ...],
    disable_tools: bool,
    tool_execution_mode: ToolExecutionMode,
    policy_snapshot: PolicySnapshot,
    request_semantics_digest: str,
) -> Mapping[str, JsonValue]:
    """构造 actual runner logical input 的稳定 digest preimage。

    source cursor、payload ref 与 governance event sequence 只属于 projection
    lineage，不得让同一 messages/tools/policy snapshot 变成另一份 logical input。

    :param messages: complete normalized messages。
    :param tool_schemas: selected tool schemas。
    :param disable_tools: 是否禁用工具。
    :param tool_execution_mode: frozen 工具执行模式。
    :param policy_snapshot: admission-frozen Engine policy。
    :param request_semantics_digest: request serialization compatibility digest。
    :returns: messages、tools、policy与request semantics的canonical JSON。
    :raises TypeError: message closed union 出现非法成员时抛出。
    """

    return {
        "runner_input_serializer_schema_version": (RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION),
        "messages": [_prepared_candidate_message_body(index, message) for index, message in enumerate(messages)],
        "tool_schemas": [_tool_schema_json(schema) for schema in tool_schemas],
        "disable_tools": disable_tools,
        "tool_execution_mode": tool_execution_mode.value,
        "policy_snapshot_ref": policy_snapshot.policy_snapshot_ref,
        "policy_snapshot_digest": _engine_policy_snapshot_digest(policy_snapshot),
        "request_semantics_digest": request_semantics_digest,
    }


def _prepared_candidate_message_body(
    index: int,
    message: AgentMessage,
) -> Mapping[str, JsonValue]:
    """构造 candidate digest 使用的 exact message atom。

    :param index: message 顺序。
    :param message: typed Agent message。
    :returns: canonical message object。
    :raises TypeError: 遇到封闭联合外消息类型时抛出。
    """

    base: dict[str, JsonValue] = {
        "index": index,
        "role": message.role.value,
        "content": _message_content_text(message),
    }
    if isinstance(message, ToolMessage):
        base["tool_call_id"] = message.tool_call_id
        return base
    if isinstance(message, AssistantMessage):
        base["content"] = message.content
        base["reasoning_content"] = message.reasoning_content
        base["tool_calls"] = [
            {
                "id": call.id,
                "name": call.name,
                "arguments": dict(call.arguments),
                "provider_state": _prepared_candidate_provider_state(call.provider_state),
            }
            for call in message.tool_calls
        ]
        return base
    if isinstance(message, SystemMessage | UserMessage):
        return base
    raise TypeError("prepared candidate message type is unsupported")


def _prepared_candidate_provider_state(
    provider_state: GeminiToolCallState | None,
) -> Mapping[str, JsonValue] | None:
    """把 provider tool-call state 无损写入 Host-private candidate。

    :param provider_state: typed provider state。
    :returns: 可逆的 Host-private JSON；缺失时返回 ``None``。
    :raises TypeError: 遇到封闭联合外状态时抛出。
    """

    if provider_state is None:
        return None
    if isinstance(provider_state, GeminiToolCallState):
        return {
            "provider": "gemini",
            "thought_signature": provider_state.thought_signature,
        }
    raise TypeError("prepared candidate provider state is unsupported")


def _engine_policy_snapshot_digest(policy_snapshot: PolicySnapshot) -> str:
    """计算 complete candidate 的 Engine policy digest。

    :param policy_snapshot: admission-frozen Engine policy。
    :returns: canonical sha256 digest。
    :raises Exception: provider request extension 非法时由 typed projector 抛出。
    """

    policy = policy_snapshot.agent_policy
    return sha256_digest_json(
        {
            "policy_snapshot_ref": policy_snapshot.policy_snapshot_ref,
            "request_semantics_digest": runner_request_semantics_digest(policy_snapshot),
            "agent_policy": {
                "max_iterations": policy.max_iterations,
                "continuation_max_attempts": policy.continuation_max_attempts,
                "allow_tool_calls": policy.allow_tool_calls,
                "tool_execution_timeout_seconds": (policy.tool_execution_timeout_seconds),
                "fallback_mode": policy.fallback_mode.value,
                "fallback_prompt": policy.fallback_prompt,
                "continuation_prompt": policy.continuation_prompt,
                "max_consecutive_failed_tool_batches": (policy.max_consecutive_failed_tool_batches),
            },
        }
    )


def _prepared_candidate_kind_and_trigger(
    candidate: PreparedRunnerCallCandidate,
    *,
    sizing_snapshot: RunnerCallSizingSnapshot,
) -> tuple[str, str]:
    """从 frozen candidate provenance 判定 ordinary manifest kind。

    :param candidate: frozen complete candidate。
    :param sizing_snapshot: producer 显式给出的 sizing stage。
    :returns: ``(runner_call_kind, trigger_reason)``。
    :raises Exception: 不主动抛出异常。
    """

    if sizing_snapshot.sizing_stage is ContextSizingStage.CONTINUATION:
        return (
            _RUNNER_CALL_KIND_FOLLOWUP_USER_DISPATCH,
            _RUNNER_CALL_TRIGGER_HOST_RESUME,
        )
    if candidate.context_fallback_decision_ref is not None or candidate.compact_artifact_refs:
        return (
            _RUNNER_CALL_KIND_POST_COMPACTION_DISPATCH,
            _RUNNER_CALL_TRIGGER_CONTEXT_GOVERNANCE_RESOLVED,
        )
    return (
        _RUNNER_CALL_KIND_INITIAL_USER_DISPATCH,
        _RUNNER_CALL_TRIGGER_INITIAL_USER_INPUT,
    )


def _prepared_runner_call_projection_body(
    *,
    candidate: PreparedRunnerCallCandidate,
    attempt_id: str,
    execution_id: str,
    runner_call_index: int,
    projection_id: str,
    runner_call_kind: str,
    trigger_reason: str,
) -> Mapping[str, JsonValue]:
    """构造 allow transaction 内 persisted runner input projection。

    :param candidate: frozen complete candidate。
    :param attempt_id: 同一 allow Attempt id。
    :param execution_id: 同一 allow execution id。
    :param runner_call_index: Host-owned call index。
    :param projection_id: projection logical id。
    :param runner_call_kind: runner call kind。
    :param trigger_reason: runner call trigger。
    :returns: LLM-readable complete projection body。
    :raises Exception: 不主动抛出异常。
    """

    return {
        "schema_version": RUNNER_CALL_INPUT_PROJECTION_SCHEMA_VERSION,
        "projection_id": projection_id,
        "session_id": candidate.session_id,
        "host_run_id": candidate.run_id,
        "attempt_id": attempt_id,
        "execution_id": execution_id,
        "runner_call_index": runner_call_index,
        "runner_call_kind": runner_call_kind,
        "runner_call_trigger_reason": trigger_reason,
        "iteration_id": None,
        "iteration_index": None,
        "runner_input_serializer_schema_version": (RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION),
        "message_count": len(candidate.messages),
        "role_sequence_digest": runner_role_sequence_digest(_message_role_values(candidate.messages)),
        "messages": [
            _prepared_runner_call_projection_message(
                candidate,
                index=index,
                message=message,
            )
            for index, message in enumerate(candidate.messages)
        ],
    }


def _prepared_runner_call_projection_message(
    candidate: PreparedRunnerCallCandidate,
    *,
    index: int,
    message: AgentMessage,
) -> Mapping[str, JsonValue]:
    """构造 persisted projection 的单条 frozen message。

    :param candidate: frozen complete candidate。
    :param index: message 顺序。
    :param message: exact message。
    :returns: projection message JSON。
    :raises Exception: 不主动抛出异常。
    """

    base = dict(_prepared_candidate_message_body(index, message))
    base["content_digest"] = _message_content_digest(message)
    base["content_size_bytes"] = _message_content_size_bytes(message)
    base["source_refs"] = list(candidate.source_cursor_refs)
    base["projector_metadata_id"] = _prepared_projector_metadata_id(
        index,
        message,
    )
    return base


def _write_prepared_tool_schema_snapshot_payload(
    transaction: HostTransaction,
    payload_store: PayloadStore,
    *,
    event_id: str,
    candidate: PreparedRunnerCallCandidate,
    attempt_id: str,
    execution_id: str,
) -> PayloadDescriptor | None:
    """写入 frozen candidate 的 selected tool schema snapshot。

    :param transaction: Host transaction。
    :param payload_store: payload store primitive。
    :param event_id: manifest event id。
    :param candidate: frozen complete candidate。
    :param attempt_id: same start Attempt id。
    :param execution_id: same start execution id。
    :returns: 有 selected tools 时返回 descriptor，否则返回 ``None``。
    :raises HostDurableError: descriptor digest 冲突时抛出。
    """

    if not candidate.tool_schemas:
        return None
    snapshot: Mapping[str, JsonValue] = {
        "schema_version": SELECTED_TOOL_SCHEMA_SNAPSHOT_SCHEMA_VERSION,
        "session_id": candidate.session_id,
        "host_run_id": candidate.run_id,
        "attempt_id": attempt_id,
        "execution_id": execution_id,
        "disable_tools": candidate.disable_tools,
        "tool_schema_count": len(candidate.tool_schemas),
        "tool_schemas": [_tool_schema_json(schema) for schema in candidate.tool_schemas],
    }
    snapshot_digest = sha256_digest_json(snapshot)
    payload_ref = _selected_tool_schema_payload_ref(event_id)
    existing = payload_store.read_payload_descriptor(transaction, payload_ref)
    if existing is not None:
        if existing.payload_digest != snapshot_digest:
            raise HostDurableError("selected tool schema snapshot digest mismatch")
        return existing
    return payload_store.write_sqlite_payload(
        transaction,
        SQLitePayloadWriteRequest(
            payload_ref=payload_ref,
            payload_id=_selected_tool_schema_sqlite_payload_id(event_id),
            payload_format=SQLitePayloadFormat.CANONICAL_JSON,
            payload_json=snapshot,
            media_type=SELECTED_TOOL_SCHEMA_SNAPSHOT_MEDIA_TYPE,
            metadata=payload_descriptor_metadata(
                PayloadDescriptorKind.SELECTED_TOOL_SCHEMA_SNAPSHOT,
                {
                    "schema_version": (SELECTED_TOOL_SCHEMA_SNAPSHOT_SCHEMA_VERSION),
                    "event_type": _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED,
                    "event_id": event_id,
                },
            ),
            expected_digest=snapshot_digest,
        ),
    )


def _write_prepared_candidate_payload(
    transaction: HostTransaction,
    payload_store: PayloadStore,
    *,
    candidate: PreparedRunnerCallCandidate,
) -> PayloadDescriptor:
    """持久化 actual request 唯一可消费的 Host-private frozen candidate。

    :param transaction: allow write transaction。
    :param payload_store: payload store primitive。
    :param candidate: identity-free complete candidate。
    :returns: candidate payload descriptor。
    :raises HostDurableError: body、ref 或 digest 与 frozen candidate 不一致时抛出。
    """

    body = _prepared_candidate_projection_body(
        session_id=candidate.session_id,
        run_id=candidate.run_id,
        candidate_input_cursor=candidate.candidate_input_cursor,
        messages=candidate.messages,
        tool_schemas=candidate.tool_schemas,
        disable_tools=candidate.disable_tools,
        tool_execution_mode=candidate.tool_execution_mode,
        policy_snapshot=candidate.policy_snapshot,
        source_cursor_refs=candidate.source_cursor_refs,
        memory_snapshot_cursor_ref=candidate.memory_snapshot_cursor_ref,
        compact_artifact_refs=candidate.compact_artifact_refs,
        context_fallback_decision_ref=(candidate.context_fallback_decision_ref),
        request_semantics_digest=candidate.request_semantics_digest,
    )
    digest = sha256_digest_json(body)
    if digest != candidate.candidate_input_projection_digest:
        raise HostDurableError("prepared candidate payload digest mismatch")
    if _prepared_candidate_payload_ref(digest) != candidate.candidate_input_projection_ref:
        raise HostDurableError("prepared candidate payload ref mismatch")
    existing = payload_store.read_payload_descriptor(
        transaction,
        candidate.candidate_input_projection_ref,
    )
    if existing is not None:
        if existing.payload_digest != digest:
            raise HostDurableError("prepared candidate descriptor digest mismatch")
        return existing
    return payload_store.write_sqlite_payload(
        transaction,
        SQLitePayloadWriteRequest(
            payload_ref=candidate.candidate_input_projection_ref,
            payload_id=_prepared_candidate_sqlite_payload_id(digest),
            payload_format=SQLitePayloadFormat.CANONICAL_JSON,
            payload_json=body,
            media_type=_PREPARED_CANDIDATE_MEDIA_TYPE,
            metadata=payload_descriptor_metadata(
                PayloadDescriptorKind.RUNNER_CALL_PREPARED_CANDIDATE,
                {
                    "schema_version": _PREPARED_CANDIDATE_SCHEMA_VERSION,
                    "host_run_id": candidate.run_id,
                },
            ),
            expected_digest=digest,
        ),
    )


def _prepared_runner_call_manifest_body(
    *,
    candidate: PreparedRunnerCallCandidate,
    attempt_id: str,
    execution_id: str,
    runner_call_index: int,
    manifest_id: str,
    projection_descriptor: PayloadDescriptor,
    tool_schema_descriptor: PayloadDescriptor | None,
    runner_call_kind: str,
    trigger_reason: str,
    sizing_snapshot: RunnerCallSizingSnapshot,
) -> Mapping[str, JsonValue]:
    """构造 pre-start ordinary manifest v2 body。

    :param candidate: frozen complete candidate。
    :param attempt_id: same start Attempt id。
    :param execution_id: same start execution id。
    :param runner_call_index: Host-owned call index。
    :param manifest_id: manifest logical id。
    :param projection_descriptor: persisted complete projection descriptor。
    :param tool_schema_descriptor: selected tool schema descriptor。
    :param runner_call_kind: runner call kind。
    :param trigger_reason: runner call trigger。
    :param sizing_snapshot: strict sizing snapshot。
    :returns: manifest v2 canonical JSON。
    :raises HostDurableError: sizing snapshot 或 graph 非法时由 shared parser 抛出。
    """

    message_entries = tuple(
        _prepared_manifest_message_entry(
            candidate,
            index=index,
            message=message,
            projection_descriptor=projection_descriptor,
        )
        for index, message in enumerate(candidate.messages)
    )
    projector_metadata = _prepared_projector_metadata(candidate)
    return {
        "schema_version": RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION,
        "manifest_id": manifest_id,
        "session_id": candidate.session_id,
        "host_run_id": candidate.run_id,
        "attempt_id": attempt_id,
        "execution_id": execution_id,
        "runner_call_index": runner_call_index,
        "runner_call_kind": runner_call_kind,
        "runner_call_trigger_reason": trigger_reason,
        "iteration_id": None,
        "iteration_index": None,
        "message_count": len(candidate.messages),
        "role_sequence_digest": runner_role_sequence_digest(_message_role_values(candidate.messages)),
        "runner_input_serializer_schema_version": (RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION),
        "input_projection_digest": (candidate.candidate_input_projection_digest),
        "runner_call_projection_artifact_ref": (projection_descriptor.payload_ref),
        "runner_call_projection_artifact_digest": (projection_descriptor.payload_digest),
        "runner_call_projection_artifact_size_bytes": (projection_descriptor.payload_size_bytes),
        "message_entries": list(message_entries),
        "source_cursor_refs": list(candidate.source_cursor_refs),
        "tool_schema_snapshot_refs": list(_tool_schema_snapshot_refs(tool_schema_descriptor)),
        "memory_snapshot_cursor_ref": candidate.memory_snapshot_cursor_ref,
        "compact_artifact_refs": list(candidate.compact_artifact_refs),
        "context_fallback_decision_ref": (candidate.context_fallback_decision_ref),
        "projector_metadata": list(projector_metadata),
        "compactor_identity": None,
        "sizing_snapshot": runner_call_sizing_snapshot_json(sizing_snapshot),
        "diagnostic": None,
    }


def _prepared_manifest_message_entry(
    candidate: PreparedRunnerCallCandidate,
    *,
    index: int,
    message: AgentMessage,
    projection_descriptor: PayloadDescriptor,
) -> Mapping[str, JsonValue]:
    """构造 prepared manifest 的单条 message provenance。

    :param candidate: frozen candidate。
    :param index: message 顺序。
    :param message: exact message。
    :param projection_descriptor: complete projection descriptor。
    :returns: manifest message entry。
    :raises Exception: 不主动抛出异常。
    """

    return {
        "index": index,
        "role": message.role.value,
        "content_digest": _message_content_digest(message),
        "content_size_bytes": _message_content_size_bytes(message),
        "source_refs": list(candidate.source_cursor_refs),
        "projection_artifact_ref": projection_descriptor.payload_ref,
        "projection_artifact_digest": projection_descriptor.payload_digest,
        "projector_metadata_id": _prepared_projector_metadata_id(
            index,
            message,
        ),
        "provider_tool_calls_digest": _assistant_tool_calls_digest(message),
        "reasoning_content_digest": _assistant_reasoning_content_digest(message),
    }


def _prepared_projector_metadata(
    candidate: PreparedRunnerCallCandidate,
) -> tuple[Mapping[str, JsonValue], ...]:
    """构造 prepared candidate 的 per-message projector metadata。

    :param candidate: frozen complete candidate。
    :returns: ordered projector metadata descriptors。
    :raises HostDurableError: shared descriptor contract 非法时抛出。
    """

    purpose = (
        _PROJECTOR_PURPOSE_POST_COMPACTION
        if candidate.compact_artifact_refs or candidate.context_fallback_decision_ref is not None
        else _PROJECTOR_PURPOSE_ORDINARY
    )
    return tuple(
        runner_call_projector_metadata_descriptor(
            RunnerCallProjectorMetadata(
                projector_metadata_id=_prepared_projector_metadata_id(
                    index,
                    message,
                ),
                projector_id=_prepared_projector_id(message),
                projector_schema_version=_PROJECTOR_SCHEMA_VERSION,
                projector_digest=sha256_digest_json(
                    {
                        "message_index": index,
                        "message_digest": _message_content_digest(message),
                        "source_refs": list(candidate.source_cursor_refs),
                        "purpose": purpose,
                    }
                ),
                purpose=purpose,
                source_contract_refs=candidate.source_cursor_refs,
            )
        )
        for index, message in enumerate(candidate.messages)
    )


def _prepared_projector_metadata_id(
    index: int,
    message: AgentMessage,
) -> str:
    """派生 prepared message 的 projector metadata id。

    :param index: message 顺序。
    :param message: exact message。
    :returns: manifest-local metadata id。
    :raises Exception: 不主动抛出异常。
    """

    return f"projector:{index}:{message.role.value}"


def _prepared_projector_id(message: AgentMessage) -> str:
    """把 AgentMessage role 映射到 shared projector id closed set。

    :param message: exact message。
    :returns: shared projector id。
    :raises TypeError: 遇到封闭联合外消息类型时抛出。
    """

    if isinstance(message, SystemMessage):
        return _PROJECTOR_ID_SYSTEM_CONTEXT
    if isinstance(message, UserMessage):
        return _PROJECTOR_ID_USER_INPUT
    if isinstance(message, AssistantMessage):
        return _PROJECTOR_ID_ASSISTANT_HISTORY
    if isinstance(message, ToolMessage):
        return _PROJECTOR_ID_TOOL_RESULT
    raise TypeError("prepared projector message type is unsupported")


def _runner_call_projection_body(
    record_input: RunnerCallManifestRecordInput,
    *,
    runner_call_index: int,
    projection_id: str,
) -> Mapping[str, JsonValue]:
    """构造 runner-call LLM-facing input projection body。

    :param record_input: manifest 构造输入。
    :param runner_call_index: Host-owned runner call index。
    :param projection_id: projection logical id。
    :returns: projection canonical JSON object。
    """

    runner_call_kind, trigger_reason = _runner_call_kind_and_trigger(record_input)
    messages = tuple(
        _runner_call_projection_message(record_input, index=index, message=message)
        for index, message in enumerate(record_input.messages)
    )
    return {
        "schema_version": RUNNER_CALL_INPUT_PROJECTION_SCHEMA_VERSION,
        "projection_id": projection_id,
        "session_id": record_input.current_facts.run.session_id,
        "host_run_id": record_input.current_facts.run.run_id,
        "attempt_id": record_input.current_facts.attempt.attempt_id,
        "execution_id": record_input.current_facts.attempt.execution_id,
        "runner_call_index": runner_call_index,
        "runner_call_kind": runner_call_kind,
        "runner_call_trigger_reason": trigger_reason,
        "iteration_id": None,
        "iteration_index": None,
        "runner_input_serializer_schema_version": (RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION),
        "message_count": len(messages),
        "role_sequence_digest": runner_role_sequence_digest(_message_role_values(record_input.messages)),
        "messages": list(messages),
    }


def _runner_call_projection_message(
    record_input: RunnerCallManifestRecordInput,
    *,
    index: int,
    message: AgentMessage,
) -> Mapping[str, JsonValue]:
    """构造 runner-call projection 的单条 message。

    :param record_input: manifest 构造输入。
    :param index: message 顺序。
    :param message: 实际 runner input message。
    :returns: message projection JSON object。
    """

    base: dict[str, JsonValue] = {
        "index": index,
        "role": message.role.value,
        "content": _message_content_text(message),
        "content_digest": _message_content_digest(message),
        "content_size_bytes": _message_content_size_bytes(message),
        "source_refs": list(_message_source_refs(record_input, index=index, message=message)),
        "projector_metadata_id": _projector_metadata_id_for_message(record_input, index=index, message=message),
    }
    if isinstance(message, ToolMessage):
        base["tool_call_id"] = message.tool_call_id
    if isinstance(message, AssistantMessage):
        base["tool_calls"] = [
            {
                "tool_call_id": call.id,
                "name": call.name,
                "arguments": dict(call.arguments),
                "provider_state": _provider_state_projection(call.provider_state),
            }
            for call in message.tool_calls
        ]
    return base


def _provider_state_projection(
    provider_state: GeminiToolCallState | None,
) -> Mapping[str, JsonValue] | None:
    """构造 provider tool-call 续航状态的非 secret 结构化投影。

    :param provider_state: Engine tool call provider state。
    :returns: provider state projection；缺失时返回 ``None``。
    """

    if provider_state is None:
        return None
    return {
        "provider": "gemini",
        "state_digest": sha256_digest_json({"thought_signature": provider_state.thought_signature}),
    }


def _write_runner_call_projection_payload(
    transaction: HostTransaction,
    payload_store: PayloadStore,
    *,
    event_id: str,
    projection: Mapping[str, JsonValue],
    projection_digest: str,
) -> PayloadDescriptor:
    """写入 runner-call input projection payload descriptor。

    :param transaction: 当前 Host transaction。
    :param payload_store: payload store primitive。
    :param event_id: manifest canonical event id。
    :param projection: projection body。
    :param projection_digest: projection body digest。
    :returns: payload descriptor。
    :raises HostDurableError: descriptor 缺失或 digest 不一致时抛出。
    """

    return payload_store.write_bounded_json_payload(
        transaction,
        BoundedJsonPayloadWriteRequest(
            payload_ref=_runner_call_projection_payload_ref(event_id),
            sqlite_payload_id=_runner_call_projection_sqlite_payload_id(event_id),
            payload_json=projection,
            media_type=RUNNER_CALL_INPUT_PROJECTION_MEDIA_TYPE,
            metadata=payload_descriptor_metadata(
                PayloadDescriptorKind.RUNNER_CALL_INPUT_PROJECTION,
                {
                    "schema_version": RUNNER_CALL_INPUT_PROJECTION_SCHEMA_VERSION,
                    "event_type": _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED,
                    "event_id": event_id,
                },
            ),
            expected_digest=projection_digest,
        ),
    )


def _write_selected_tool_schema_snapshot_payload(
    transaction: HostTransaction,
    payload_store: PayloadStore,
    *,
    event_id: str,
    record_input: RunnerCallManifestRecordInput,
) -> PayloadDescriptor | None:
    """写入 selected tool schema full JSON snapshot payload descriptor。

    :param transaction: 当前 Host transaction。
    :param payload_store: payload store primitive。
    :param event_id: manifest canonical event id。
    :param record_input: manifest 构造输入。
    :returns: 有工具 schema 时返回 payload descriptor，否则返回 ``None``。
    :raises HostDurableError: descriptor 缺失或 digest 不一致时抛出。
    """

    if len(record_input.tool_snapshot.tool_schemas) == 0:
        return None
    snapshot = _selected_tool_schema_snapshot_body(record_input)
    snapshot_digest = sha256_digest_json(snapshot)
    payload_ref = _selected_tool_schema_payload_ref(event_id)
    existing = payload_store.read_payload_descriptor(transaction, payload_ref)
    if existing is not None:
        if existing.payload_digest != snapshot_digest:
            raise HostDurableError("selected tool schema snapshot digest mismatch")
        return existing
    return payload_store.write_sqlite_payload(
        transaction,
        SQLitePayloadWriteRequest(
            payload_ref=payload_ref,
            payload_id=_selected_tool_schema_sqlite_payload_id(event_id),
            payload_format=SQLitePayloadFormat.CANONICAL_JSON,
            payload_json=snapshot,
            media_type=SELECTED_TOOL_SCHEMA_SNAPSHOT_MEDIA_TYPE,
            metadata=payload_descriptor_metadata(
                PayloadDescriptorKind.SELECTED_TOOL_SCHEMA_SNAPSHOT,
                {
                    "schema_version": SELECTED_TOOL_SCHEMA_SNAPSHOT_SCHEMA_VERSION,
                    "event_type": _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED,
                    "event_id": event_id,
                },
            ),
            expected_digest=snapshot_digest,
        ),
    )


def _selected_tool_schema_snapshot_body(
    record_input: RunnerCallManifestRecordInput,
) -> Mapping[str, JsonValue]:
    """构造 selected tool schema full JSON snapshot body。

    :param record_input: manifest 构造输入。
    :returns: selected tool schema snapshot canonical JSON object。
    """

    return {
        "schema_version": SELECTED_TOOL_SCHEMA_SNAPSHOT_SCHEMA_VERSION,
        "session_id": record_input.current_facts.run.session_id,
        "host_run_id": record_input.current_facts.run.run_id,
        "attempt_id": record_input.current_facts.attempt.attempt_id,
        "execution_id": record_input.current_facts.attempt.execution_id,
        "disable_tools": record_input.tool_snapshot.disable_tools,
        "tool_schema_count": len(record_input.tool_snapshot.tool_schemas),
        "tool_schemas": [_tool_schema_json(schema) for schema in record_input.tool_snapshot.tool_schemas],
    }


def _tool_schema_json(schema: ToolSchema) -> Mapping[str, JsonValue]:
    """把 ToolSchema 转为 LLM-facing JSON snapshot。

    :param schema: Engine tool schema。
    :returns: OpenAI function-call 风格 JSON object。
    """

    parameters: dict[str, JsonValue] = {
        "type": schema.function.parameters.type,
        "properties": dict(schema.function.parameters.properties),
        "required": list(schema.function.parameters.required),
    }
    if schema.function.parameters.additional_properties is not None:
        parameters["additionalProperties"] = schema.function.parameters.additional_properties
    return {
        "type": schema.type,
        "function": {
            "name": schema.function.name,
            "description": schema.function.description,
            "parameters": parameters,
        },
    }


def _runner_call_manifest_body(
    record_input: RunnerCallManifestRecordInput,
    *,
    runner_call_index: int,
    manifest_id: str,
    projection_descriptor: PayloadDescriptor,
    tool_schema_descriptor: PayloadDescriptor | None,
) -> Mapping[str, JsonValue]:
    """构造 runner-call input assembly manifest body。

    :param record_input: manifest 构造输入。
    :param runner_call_index: Host-owned runner call index。
    :param manifest_id: manifest logical id。
    :returns: manifest canonical JSON object。
    """

    roles = _message_role_values(record_input.messages)
    message_entries = _runner_call_message_entries(record_input, projection_descriptor=projection_descriptor)
    projector_metadata = _runner_call_projector_metadata(record_input)
    source_cursor_refs = _source_cursor_refs(record_input)
    input_projection_digest = _input_projection_digest(
        message_entries=message_entries,
        projector_metadata=projector_metadata,
        source_cursor_refs=source_cursor_refs,
    )
    runner_call_kind, trigger_reason = _runner_call_kind_and_trigger(record_input)
    return {
        "schema_version": RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION,
        "manifest_id": manifest_id,
        "session_id": record_input.current_facts.run.session_id,
        "host_run_id": record_input.current_facts.run.run_id,
        "attempt_id": record_input.current_facts.attempt.attempt_id,
        "execution_id": record_input.current_facts.attempt.execution_id,
        "runner_call_index": runner_call_index,
        "runner_call_kind": runner_call_kind,
        "runner_call_trigger_reason": trigger_reason,
        "iteration_id": None,
        "iteration_index": None,
        "message_count": len(record_input.messages),
        "role_sequence_digest": runner_role_sequence_digest(roles),
        "runner_input_serializer_schema_version": (RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION),
        "input_projection_digest": input_projection_digest,
        "runner_call_projection_artifact_ref": projection_descriptor.payload_ref,
        "runner_call_projection_artifact_digest": (projection_descriptor.payload_digest),
        "runner_call_projection_artifact_size_bytes": (projection_descriptor.payload_size_bytes),
        "message_entries": list(message_entries),
        "source_cursor_refs": list(source_cursor_refs),
        "tool_schema_snapshot_refs": list(_tool_schema_snapshot_refs(tool_schema_descriptor)),
        "memory_snapshot_cursor_ref": _memory_snapshot_cursor_ref(record_input.memory),
        "compact_artifact_refs": list(_compact_artifact_refs(record_input.compact)),
        "context_fallback_decision_ref": _context_fallback_decision_ref(record_input.fallback),
        "projector_metadata": list(projector_metadata),
        "compactor_identity": None,
        "sizing_snapshot": runner_call_sizing_snapshot_json(
            unavailable_runner_call_sizing_snapshot(
                RunnerCallSizingUnavailableReason.CONTEXT_POLICY_UNAVAILABLE,
                sizing_stage=ContextSizingStage.ORDINARY,
            )
        ),
        "diagnostic": None,
    }


def _write_runner_call_manifest_payload(
    transaction: HostTransaction,
    payload_store: PayloadStore,
    *,
    event_id: str,
    manifest: Mapping[str, JsonValue],
    manifest_digest: str,
) -> PayloadDescriptor:
    """写入 runner-call manifest payload descriptor。

    :param transaction: 当前 Host transaction。
    :param payload_store: payload store primitive。
    :param event_id: manifest canonical event id。
    :param manifest: manifest body。
    :param manifest_digest: manifest body digest。
    :returns: payload descriptor。
    :raises HostDurableError: descriptor 缺失或 digest 不一致时抛出。
    """

    payload_ref = _runner_call_manifest_payload_ref(event_id)
    existing = payload_store.read_payload_descriptor(transaction, payload_ref)
    if existing is not None:
        if existing.payload_digest != manifest_digest:
            raise HostDurableError("runner-call manifest payload digest mismatch")
        return existing
    return payload_store.write_sqlite_payload(
        transaction,
        SQLitePayloadWriteRequest(
            payload_ref=payload_ref,
            payload_id=_runner_call_manifest_sqlite_payload_id(event_id),
            payload_format=SQLitePayloadFormat.CANONICAL_JSON,
            payload_json=manifest,
            media_type=RUNNER_CALL_INPUT_MANIFEST_MEDIA_TYPE,
            metadata=payload_descriptor_metadata(
                PayloadDescriptorKind.RUNNER_CALL_INPUT_MANIFEST,
                {
                    "event_type": _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED,
                    "event_id": event_id,
                },
            ),
            expected_digest=manifest_digest,
        ),
    )


def _runner_call_manifest_hot_payload(
    *,
    manifest: Mapping[str, JsonValue],
    manifest_payload_ref: str,
    manifest_digest: str,
) -> Mapping[str, JsonValue]:
    """构造 RUNNER_CALL_INPUT_ASSEMBLED hot payload。

    :param manifest: manifest body。
    :param manifest_payload_ref: manifest payload descriptor ref。
    :param manifest_digest: manifest body digest。
    :returns: EventLog hot payload。
    :raises HostDurableError: manifest identity 字段类型非法时抛出。
    """

    message_count = _manifest_int(manifest, "message_count")
    role_sequence_digest = _manifest_text(manifest, "role_sequence_digest")
    return runner_call_hot_payload(
        RunnerCallHotAtoms(
            session_id=_manifest_text(manifest, "session_id"),
            host_run_id=_manifest_text(manifest, "host_run_id"),
            attempt_id=_manifest_optional_text(manifest, "attempt_id"),
            execution_id=_manifest_optional_text(manifest, "execution_id"),
            runner_call_index=_manifest_int(manifest, "runner_call_index"),
            runner_call_kind=_manifest_text(manifest, "runner_call_kind"),
            runner_call_trigger_reason=_manifest_text(manifest, "runner_call_trigger_reason"),
            iteration_id=_manifest_optional_text(manifest, "iteration_id"),
            iteration_index=None,
            manifest_payload_ref=manifest_payload_ref,
            manifest_digest=manifest_digest,
            manifest_schema_version=_manifest_text(manifest, "schema_version"),
            validation_status=_RUNNER_CALL_VALIDATION_COMPLETE,
            message_count=message_count,
            role_sequence_digest=role_sequence_digest,
            input_projection_digest=_manifest_text(manifest, "input_projection_digest"),
            runner_call_projection_artifact_ref=_manifest_text(manifest, "runner_call_projection_artifact_ref"),
            runner_call_projection_artifact_digest=_manifest_text(manifest, "runner_call_projection_artifact_digest"),
            runner_call_projection_artifact_size_bytes=_manifest_int(
                manifest, "runner_call_projection_artifact_size_bytes"
            ),
            diagnostic=complete_runner_call_hot_diagnostic(
                status=_RUNNER_CALL_VALIDATION_COMPLETE,
                message_count=message_count,
                role_sequence_digest=role_sequence_digest,
                consumer_boundary=_RUNNER_CALL_EVENT_SOURCE,
            ),
        ),
        manifest=manifest,
    )


def _runner_call_manifest_payload_ref(event_id: str) -> str:
    """派生 runner-call manifest payload descriptor ref。

    :param event_id: manifest canonical event id。
    :returns: payload descriptor ref。
    """

    return f"{_RUNNER_CALL_MANIFEST_PAYLOAD_REF_PREFIX}-{event_id}"


def _runner_call_projection_payload_ref(event_id: str) -> str:
    """派生 runner-call projection payload descriptor ref。

    :param event_id: manifest canonical event id。
    :returns: payload descriptor ref。
    """

    return f"{_RUNNER_CALL_PROJECTION_PAYLOAD_REF_PREFIX}-{event_id}"


def _selected_tool_schema_payload_ref(event_id: str) -> str:
    """派生 selected tool schema snapshot payload descriptor ref。

    :param event_id: manifest canonical event id。
    :returns: payload descriptor ref。
    """

    return f"{_SELECTED_TOOL_SCHEMA_PAYLOAD_REF_PREFIX}-{event_id}"


def _runner_call_manifest_sqlite_payload_id(event_id: str) -> str:
    """派生 runner-call manifest SQLite payload id。

    :param event_id: manifest canonical event id。
    :returns: SQLite payload id。
    """

    return f"{_RUNNER_CALL_MANIFEST_SQLITE_PAYLOAD_ID_PREFIX}-{event_id}"


def _runner_call_projection_sqlite_payload_id(event_id: str) -> str:
    """派生 runner-call projection SQLite payload id。

    :param event_id: manifest canonical event id。
    :returns: SQLite payload id。
    """

    return f"{_RUNNER_CALL_PROJECTION_SQLITE_PAYLOAD_ID_PREFIX}-{event_id}"


def _selected_tool_schema_sqlite_payload_id(event_id: str) -> str:
    """派生 selected tool schema snapshot SQLite payload id。

    :param event_id: manifest canonical event id。
    :returns: SQLite payload id。
    """

    return f"{_SELECTED_TOOL_SCHEMA_SQLITE_PAYLOAD_ID_PREFIX}-{event_id}"


def _runner_call_message_entries(
    record_input: RunnerCallManifestRecordInput,
    *,
    projection_descriptor: PayloadDescriptor,
) -> tuple[Mapping[str, JsonValue], ...]:
    """构造 manifest message entries。

    :param record_input: manifest 构造输入。
    :returns: message entry 元组。
    """

    return tuple(
        _runner_call_message_entry(
            record_input,
            index=index,
            message=message,
            projection_descriptor=projection_descriptor,
        )
        for index, message in enumerate(record_input.messages)
    )


def _runner_call_message_entry(
    record_input: RunnerCallManifestRecordInput,
    *,
    index: int,
    message: AgentMessage,
    projection_descriptor: PayloadDescriptor,
) -> Mapping[str, JsonValue]:
    """构造单条 manifest message entry。

    :param record_input: manifest 构造输入。
    :param index: message 顺序。
    :param message: 实际 runner input message。
    :returns: message entry JSON object。
    """

    return {
        "index": index,
        "role": message.role.value,
        "content_digest": _message_content_digest(message),
        "content_size_bytes": _message_content_size_bytes(message),
        "source_refs": list(_message_source_refs(record_input, index=index, message=message)),
        "projection_artifact_ref": projection_descriptor.payload_ref,
        "projection_artifact_digest": projection_descriptor.payload_digest,
        "projector_metadata_id": _projector_metadata_id_for_message(record_input, index=index, message=message),
        "provider_tool_calls_digest": _assistant_tool_calls_digest(message),
        "reasoning_content_digest": _assistant_reasoning_content_digest(message),
    }


def _runner_call_projector_metadata(
    record_input: RunnerCallManifestRecordInput,
) -> tuple[Mapping[str, JsonValue], ...]:
    """构造 manifest projector metadata。

    :param record_input: manifest 构造输入。
    :returns: projector metadata 元组。
    """

    metadata_by_id: dict[str, Mapping[str, JsonValue]] = {}
    for index, message in enumerate(record_input.messages):
        metadata_id = _projector_metadata_id_for_message(record_input, index=index, message=message)
        if metadata_id in metadata_by_id:
            continue
        metadata_by_id[metadata_id] = _projector_metadata(
            metadata_id=metadata_id,
            projector_id=_projector_id_for_message(record_input, index, message),
            purpose=_projector_purpose(record_input),
            source_contract_refs=_message_source_refs(record_input, index=index, message=message),
        )
    return tuple(metadata_by_id.values())


def _projector_metadata(
    *,
    metadata_id: str,
    projector_id: str,
    purpose: str,
    source_contract_refs: tuple[str, ...],
) -> Mapping[str, JsonValue]:
    """构造单条 projector metadata。

    :param metadata_id: projector metadata id。
    :param projector_id: projector 语义 id。
    :param purpose: projector 目的。
    :param source_contract_refs: source contract refs。
    :returns: projector metadata JSON object。
    """

    projector_digest = sha256_digest_json(
        {
            "projector_id": projector_id,
            "projector_schema_version": _PROJECTOR_SCHEMA_VERSION,
            "purpose": purpose,
            "source_contract_refs": list(source_contract_refs),
        }
    )
    return runner_call_projector_metadata_descriptor(
        RunnerCallProjectorMetadata(
            projector_metadata_id=metadata_id,
            projector_id=projector_id,
            projector_schema_version=_PROJECTOR_SCHEMA_VERSION,
            projector_digest=projector_digest,
            purpose=purpose,
            source_contract_refs=source_contract_refs,
        )
    )


def _projector_metadata_id_for_message(
    record_input: RunnerCallManifestRecordInput,
    *,
    index: int,
    message: AgentMessage,
) -> str:
    """返回 message 对应的 projector metadata id。

    :param record_input: manifest 构造输入。
    :param index: message 顺序。
    :param message: 实际 runner input message。
    :returns: projector metadata id。
    """

    del record_input
    return f"projector:{index}:{message.role.value}"


def _projector_id_for_message(
    record_input: RunnerCallManifestRecordInput,
    index: int,
    message: AgentMessage,
) -> str:
    """返回 message 对应的 projector id。

    :param record_input: manifest 构造输入。
    :param index: message 顺序。
    :param message: 实际 runner input message。
    :returns: projector id。
    """

    if record_input.fallback is not None and index < len(record_input.messages) - 1:
        return _PROJECTOR_ID_RECENT_WINDOW
    if index == len(record_input.messages) - 1 and isinstance(message, UserMessage):
        return _PROJECTOR_ID_USER_INPUT
    if isinstance(message, AssistantMessage):
        return _PROJECTOR_ID_ASSISTANT_HISTORY
    if isinstance(message, ToolMessage):
        return _PROJECTOR_ID_TOOL_RESULT
    if _message_content_text(message).startswith(_MEMORY_SESSION_SUMMARY_HEADER):
        return _PROJECTOR_ID_MEMORY
    return _PROJECTOR_ID_SYSTEM_CONTEXT


def _projector_purpose(record_input: RunnerCallManifestRecordInput) -> str:
    """返回当前 manifest 的 projector purpose。

    :param record_input: manifest 构造输入。
    :returns: projector purpose。
    """

    if record_input.fallback is not None:
        return _PROJECTOR_PURPOSE_POST_COMPACTION
    return _PROJECTOR_PURPOSE_ORDINARY


def _message_role_values(messages: tuple[AgentMessage, ...]) -> tuple[str, ...]:
    """返回 messages 的 role wire value 序列。

    :param messages: 实际 runner input messages。
    :returns: role 文本元组。
    """

    return tuple(message.role.value for message in messages)


def _message_content_digest(message: AgentMessage) -> str:
    """计算单条 message rendered content digest。

    :param message: 实际 runner input message。
    :returns: ``sha256:`` digest。
    """

    return sha256_digest_json(_message_content_digest_preimage(message))


def _message_content_digest_preimage(message: AgentMessage) -> Mapping[str, JsonValue]:
    """构造 message content digest preimage。

    :param message: 实际 runner input message。
    :returns: digest preimage JSON object。
    """

    if isinstance(message, AssistantMessage):
        return {
            "serializer_schema_version": RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION,
            "role": message.role.value,
            "content": message.content,
            "reasoning_content_digest": _assistant_reasoning_content_digest(message),
            "tool_calls_digest": _assistant_tool_calls_digest(message),
        }
    return {
        "serializer_schema_version": RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION,
        "role": message.role.value,
        "content": _message_content_text(message),
    }


def _message_content_size_bytes(message: AgentMessage) -> int:
    """计算 message content 的 UTF-8 字节数。

    :param message: 实际 runner input message。
    :returns: content 字节数。
    """

    return len(_message_content_text(message).encode("utf-8"))


def _message_content_text(message: AgentMessage) -> str:
    """读取 message 文本内容。

    :param message: 实际 runner input message。
    :returns: message 文本；assistant content 缺失时返回空串。
    """

    if isinstance(message, SystemMessage):
        return message.content
    if isinstance(message, UserMessage):
        return message.content
    if isinstance(message, ToolMessage):
        return message.content
    if isinstance(message, AssistantMessage) and message.content is not None:
        return message.content
    return ""


def _assistant_tool_calls_digest(message: AgentMessage) -> str | None:
    """计算 assistant typed tool calls digest。

    :param message: 实际 runner input message。
    :returns: tool calls digest；非 assistant 或无 tool calls 时返回 ``None``。
    """

    if not isinstance(message, AssistantMessage) or len(message.tool_calls) == 0:
        return None
    return sha256_digest_json(
        {
            "tool_calls": [
                {
                    "id": call.id,
                    "name": call.name,
                    "arguments": dict(call.arguments),
                }
                for call in message.tool_calls
            ]
        }
    )


def _assistant_reasoning_content_digest(message: AgentMessage) -> str | None:
    """计算 assistant reasoning content digest。

    :param message: 实际 runner input message。
    :returns: reasoning content digest；缺失时返回 ``None``。
    """

    if not isinstance(message, AssistantMessage):
        return None
    if message.reasoning_content is None:
        return None
    return sha256_digest_json({"reasoning_content": message.reasoning_content})


def _message_source_refs(
    record_input: RunnerCallManifestRecordInput,
    *,
    index: int,
    message: AgentMessage,
) -> tuple[str, ...]:
    """返回 message 的 durable source refs。

    :param record_input: manifest 构造输入。
    :param index: message 顺序。
    :param message: 实际 runner input message。
    :returns: source refs 元组。
    """

    if index == len(record_input.messages) - 1 and isinstance(message, UserMessage):
        return (record_input.current_facts.user_input_event.event_id,)
    refs: list[str] = [
        record_input.current_facts.run_accepted_event.event_id,
        record_input.current_facts.run_started_event.event_id,
        record_input.policy_snapshot.policy_snapshot_ref,
    ]
    if record_input.memory.memory_snapshot_cursor is not None:
        refs.append(f"memory:{record_input.memory.memory_snapshot_cursor}")
    if record_input.compact.compact_artifact_ref is not None:
        refs.append(f"compact:{record_input.compact.compact_artifact_ref}")
    if record_input.fallback is not None:
        refs.append(f"context_fallback:{record_input.fallback.fallback_input_digest}")
    return tuple(dict.fromkeys(refs))


def _source_cursor_refs(
    record_input: RunnerCallManifestRecordInput,
) -> tuple[str, ...]:
    """返回 manifest source cursor refs。

    :param record_input: manifest 构造输入。
    :returns: source cursor refs 元组。
    """

    refs = [
        f"event:{record_input.current_facts.user_input_event.event_id}",
        f"event:{record_input.current_facts.run_started_event.event_id}",
    ]
    if record_input.memory.memory_snapshot_cursor is not None:
        refs.append(f"memory:{record_input.memory.memory_snapshot_cursor}")
    if record_input.compact.compact_artifact_ref is not None:
        refs.append(f"compact:{record_input.compact.compact_artifact_ref}")
    return tuple(dict.fromkeys(refs))


def _tool_schema_snapshot_refs(
    tool_schema_descriptor: PayloadDescriptor | None,
) -> tuple[str, ...]:
    """返回工具 schema snapshot refs。

    :param tool_schema_descriptor: selected schema snapshot descriptor。
    :returns: 工具 schema refs；无工具时为空。
    """

    if tool_schema_descriptor is None:
        return ()
    return (
        "tool_schema_snapshot_ref:" + tool_schema_descriptor.payload_ref,
        "tool_schema_snapshot_digest:" + tool_schema_descriptor.payload_digest,
        "tool_schema_snapshot_size_bytes:" + str(tool_schema_descriptor.payload_size_bytes),
    )


def _memory_snapshot_cursor_ref(memory: MemorySnapshotView) -> str | None:
    """返回 manifest memory snapshot cursor ref。

    :param memory: memory view。
    :returns: cursor ref；缺失时返回 ``None``。
    """

    if memory.memory_snapshot_cursor is None:
        return None
    return f"memory:{memory.memory_snapshot_cursor}"


def _compact_artifact_refs(compact: CompactArtifactView) -> tuple[str, ...]:
    """返回 manifest compact artifact refs。

    :param compact: compact artifact view。
    :returns: compact artifact refs 元组。
    """

    refs: list[str] = []
    if compact.compact_artifact_ref is not None:
        refs.append(f"compact:{compact.compact_artifact_ref}")
    if compact.compact_artifact_digest is not None:
        refs.append(f"compact_digest:{compact.compact_artifact_digest}")
    return tuple(refs)


def _context_fallback_decision_ref(
    fallback: ActiveRecentWindowFallback | None,
) -> str | None:
    """返回 context fallback decision ref。

    :param fallback: active fallback view。
    :returns: fallback ref；未生效时返回 ``None``。
    """

    if fallback is None:
        return None
    return f"context_fallback:{fallback.fallback_input_digest}"


def _input_projection_digest(
    *,
    message_entries: tuple[Mapping[str, JsonValue], ...],
    projector_metadata: tuple[Mapping[str, JsonValue], ...],
    source_cursor_refs: tuple[str, ...],
) -> str:
    """计算 manifest input projection digest。

    :param message_entries: message entry 摘要。
    :param projector_metadata: projector metadata 摘要。
    :param source_cursor_refs: source cursor refs。
    :returns: input projection digest。
    """

    return sha256_digest_json(
        {
            "message_entries": [
                {
                    "index": entry["index"],
                    "role": entry["role"],
                    "content_digest": entry["content_digest"],
                    "source_refs": entry["source_refs"],
                    "projector_metadata_id": entry["projector_metadata_id"],
                }
                for entry in message_entries
            ],
            "projector_metadata": list(projector_metadata),
            "source_cursor_refs": list(source_cursor_refs),
        }
    )


def _runner_call_kind_and_trigger(
    record_input: RunnerCallManifestRecordInput,
) -> tuple[str, str]:
    """返回 runner call kind 与 trigger reason。

    :param record_input: manifest 构造输入。
    :returns: ``(runner_call_kind, runner_call_trigger_reason)``。
    """

    start_payload = _payload_object(record_input.current_facts.run_started_event)
    started_payload = decode_run_started_payload(start_payload)
    if started_payload.start_reason is RunStartReason.RECOVERY or record_input.fallback is not None:
        return (
            _RUNNER_CALL_KIND_POST_COMPACTION_DISPATCH,
            _RUNNER_CALL_TRIGGER_CONTEXT_GOVERNANCE_RESOLVED,
        )
    if started_payload.start_reason is RunStartReason.RESUME:
        return (
            _RUNNER_CALL_KIND_FOLLOWUP_USER_DISPATCH,
            _RUNNER_CALL_TRIGGER_HOST_RESUME,
        )
    if len(record_input.continuity.messages) > 0:
        return (
            _RUNNER_CALL_KIND_FOLLOWUP_USER_DISPATCH,
            _RUNNER_CALL_TRIGGER_FOLLOWUP_USER_INPUT,
        )
    return (
        _RUNNER_CALL_KIND_INITIAL_USER_DISPATCH,
        _RUNNER_CALL_TRIGGER_INITIAL_USER_INPUT,
    )


def _manifest_text(payload: Mapping[str, JsonValue], field_name: str) -> str:
    """读取 manifest 中的必填文本字段。

    :param payload: manifest JSON object。
    :param field_name: 字段名。
    :returns: 文本值。
    :raises HostDurableError: 字段缺失或类型非法时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, str) or value.strip() == "":
        raise HostDurableError(f"runner-call manifest {field_name} must be text")
    return value


def _manifest_optional_text(payload: Mapping[str, JsonValue], field_name: str) -> str | None:
    """读取 manifest 中的可选文本字段。

    :param payload: manifest JSON object。
    :param field_name: 字段名。
    :returns: 文本值或 ``None``。
    :raises HostDurableError: 字段类型非法时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str) or value.strip() == "":
        raise HostDurableError(f"runner-call manifest {field_name} must be text")
    return value


def _manifest_int(payload: Mapping[str, JsonValue], field_name: str) -> int:
    """读取 manifest 中的必填非负整数字段。

    :param payload: manifest JSON object。
    :param field_name: 字段名。
    :returns: 整数值。
    :raises HostDurableError: 字段缺失或类型非法时抛出。
    """

    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HostDurableError(f"runner-call manifest {field_name} must be int")
    return value


def _tools_scene_line(tool_execution_mode: ToolExecutionMode) -> str:
    """返回 scene message 中的工具可用性说明。

    :param tool_execution_mode: 显式工具执行模式。
    :returns: 工具可用性说明。
    """

    if tool_execution_mode == ToolExecutionMode.TOOL_ENABLED:
        return "Tools are available for this runner call."
    return "Tools are disabled for this runner call."


__all__ = [
    "CompactArtifactProvider",
    "CompactArtifactView",
    "AcceptedToolEvidenceMaterialProvider",
    "ContextFallbackProvider",
    "CurrentRunFactProvider",
    "CurrentRunFacts",
    "DefaultSceneParameterProvider",
    "DurableCompactArtifactProvider",
    "DurableAcceptedToolEvidenceMaterialProvider",
    "DurableCurrentRunFactProvider",
    "DurableMemorySnapshotProvider",
    "DurableSessionContinuityProvider",
    "EventLogContextFallbackProvider",
    "MemoryProjectionRepairRequired",
    "MemorySnapshotProvider",
    "MemorySnapshotView",
    "NoToolExecutor",
    "NoToolExecutorProvider",
    "NoopCompactArtifactProvider",
    "NoopContextFallbackProvider",
    "NoopAcceptedToolEvidenceMaterialProvider",
    "NoopMemorySnapshotProvider",
    "NoopToolSchemaSnapshotProvider",
    "PolicySnapshot",
    "PolicySnapshotProvider",
    "PreparedRunnerCallCandidate",
    "PreparedRunnerCallSource",
    "PreparedRunnerCallSourceError",
    "PreparedRunnerCallSourceFailureCategory",
    "RunInputBuilder",
    "SceneParameterProvider",
    "SessionContinuityProvider",
    "SessionContinuityView",
    "StaticPolicySnapshotProvider",
    "StaticToolRuntimeHandleProvider",
    "ToolExecutionMode",
    "ToolExecutorProvider",
    "ToolRuntimeExecutorProvider",
    "ToolRuntimeHandleProvider",
    "ToolRuntimeSchemaSnapshotProvider",
    "ToolSchemaSnapshot",
    "ToolSchemaSnapshotProvider",
    "build_run_input_material_blocks",
    "agent_run_request_from_prepared_candidate",
    "create_no_tool_run_input_builder",
    "create_tool_enabled_run_input_builder",
    "estimate_prepared_runner_call_candidate",
    "resolve_prepared_runner_call_context_anchor_in_transaction",
    "load_prepared_runner_call_candidate",
    "load_prepared_runner_call_candidate_in_transaction",
    "prepare_runner_call_candidate",
    "prepare_runner_call_candidate_in_transaction",
    "record_prepared_runner_call_candidate_in_transaction",
    "runner_request_semantics_digest",
]
