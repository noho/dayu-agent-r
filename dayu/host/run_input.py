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
from typing import NoReturn, Protocol

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionRequest
from dayu.contracts.tool_executor import ToolExecutor
from dayu.contracts.tool_outcome import (
    BatchToolExecutionOutcome,
    BatchToolExecutionRecord,
    TOOL_CANCELLED_REASON_HOST_CANCELLED,
    ToolCancelledOutcome,
)
from dayu.contracts.tool_schema import ToolSchema
from dayu.engine.contracts.engine_events import (
    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION,
    runner_role_sequence_digest,
)
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.messages import (
    AgentMessage,
    AgentMessageRole,
    AssistantMessage,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.host._event_payload import (
    payload_object as _payload_object,
)
from dayu.host._event_payload import (
    required_payload_text as _required_payload_text,
)
from dayu.host._terminal_answer import assistant_final_answer_continuity_text
from dayu.host.api import AttemptDispatchSnapshot
from dayu.host.api import AttemptStatus, RunStatus
from dayu.host.context_events import CONTEXT_COMPACTED, CONTEXT_COMPACTION_REQUESTED
from dayu.host.context_fallback import (
    ActiveRecentWindowFallback,
    EventLogContextFallbackProvider,
    fallback_window_digest,
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
    PayloadDescriptor,
    PayloadStore,
    SQLitePayloadFormat,
    SQLitePayloadWriteRequest,
)
from dayu.host.durable.schema import (
    RUNNER_CALL_INPUT_MANIFEST_MEDIA_TYPE,
    RUNNER_CALL_INPUT_MANIFEST_DESCRIPTOR_KIND,
    RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION,
    TABLE_EVENT_LOG,
)
from dayu.host.durable.state import (
    AttemptRow,
    DispatchRecordRow,
    DispatchRecordStatus,
    RunRow,
    read_attempt_by_id,
    read_dispatch_record_by_attempt_id,
    read_run_by_id,
)
from dayu.host.durable.transaction import HostRow, HostTransaction, HostTransactionRunner
from dayu.host.evidence import ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH
from dayu.host.evidence import accepted_evidence_envelope_from_payload
from dayu.host.payload_resolution import (
    event_payload_object,
    event_payload_object_for_result_ref,
)
from dayu.host.projection import event_log_read_filter_from_projection_filter
from dayu.host.terminal_payload import (
    PayloadTextReadPolicy,
    assistant_final_answer_text_from_run_payload,
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
    build_memory_budget_diagnostic,
    digest_memory_projection_policy,
    estimate_memory_size_units,
    memory_snapshot_with_cursor_and_diagnostics,
    project_conversation_memory_event,
)
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
_PAYLOAD_FIELD_FINAL_ANSWER = "final_answer"
_PAYLOAD_FIELD_START_REASON = "start_reason"
_PAYLOAD_FIELD_TOOL_RESULT_EVENT_REF = "tool_result_event_ref"
_PAYLOAD_FIELD_EVENT_ID = "event_id"
_PAYLOAD_FIELD_COMPACT_ARTIFACT_REF = "compact_artifact_ref"
_PAYLOAD_FIELD_COMPACT_ARTIFACT_DIGEST = "compact_artifact_digest"
_PAYLOAD_FIELD_OPERATION_ID = "operation_id"
_PAYLOAD_FIELD_TRIGGER_SOURCE = "trigger_source"
_PAYLOAD_FIELD_ACCEPTED_CANDIDATE = "accepted_candidate"
_PAYLOAD_FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS = "accepted_evidence_mapping_refs"
_PAYLOAD_FIELD_SCHEMA_VERSION = "schema_version"
_PAYLOAD_FIELD_SESSION_SUMMARY = "session_summary"
_PAYLOAD_FIELD_SUMMARY_TEXT = "summary_text"
_PAYLOAD_FIELD_TEXT = "text"
_PAYLOAD_FIELD_CLAIM_TEXT = "claim_text"
_PAYLOAD_FIELD_EVIDENCE_LABELS = "evidence_labels"
_PAYLOAD_FIELD_SOURCE_LABELS = "source_labels"
_PAYLOAD_FIELD_EVIDENCE_KIND = "evidence_kind"
_PAYLOAD_FIELD_ANCHOR_TITLE = "anchor_title"
_PAYLOAD_FIELD_ANCHOR_ITEMS = "anchor_items"
_PAYLOAD_FIELD_ORDINAL = "ordinal"
_PAYLOAD_FIELD_INTENT_TYPE = "intent_type"
_PAYLOAD_FIELD_STATUS = "status"
_PAYLOAD_FIELD_REASON = "reason"
_PAYLOAD_FIELD_EVIDENCE_BACKED_FACTS = "evidence_backed_facts"
_PAYLOAD_FIELD_ANSWER_ANCHORS = "answer_anchors"
_PAYLOAD_FIELD_FORWARD_INTENTS = "forward_intents"
_PAYLOAD_FIELD_REFERENCE_CONTINUITY_ITEMS = "reference_continuity_items"
_NO_TOOL_CANCEL_MESSAGE = "tools are disabled for this attempt"
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
_SYSTEM_SECTION_RESUME_GUIDANCE = "Resume Guidance"
_SYSTEM_ENVELOPE_SECTION_ORDER = (
    _SYSTEM_SECTION_TASK_INSTRUCTIONS,
    _SYSTEM_SECTION_EXECUTION_GUIDANCE,
    _SYSTEM_SECTION_CONVERSATION_SUMMARY,
    _SYSTEM_SECTION_VERIFIED_EVIDENCE,
    _SYSTEM_SECTION_PRIOR_ANSWER_ANCHORS,
    _SYSTEM_SECTION_OPEN_FOLLOWUP_CONTEXT,
    _SYSTEM_SECTION_REFERENCE_CONTINUITY,
    _SYSTEM_SECTION_RECENT_EVIDENCE,
    _SYSTEM_SECTION_RESUME_GUIDANCE,
)
_EXECUTION_GUIDANCE_PREFIX = "Execution guidance:"
_ACCEPTED_COMPACTED_VIEW_PREFIX = "Accepted compacted conversation view:"
_RECENT_EVIDENCE_PREFIX = "Recent evidence:"
_ACCEPTED_TOOL_EVIDENCE_PREFIX = "Accepted tool evidence:"
_RESUME_GUIDANCE_PREFIX = "Resume guidance:"
_EVIDENCE_SOURCE_PART_SEPARATOR = ", "
_INTERNAL_EVIDENCE_SOURCE_PREFIXES = (
    "tool_call_event:",
    "tool_result_event:",
    "event:",
    "eventlog:",
    "payload:",
    "artifact:",
    "digest:",
)
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
    "ConversationCompactOutputVNext",
)
_RUNNER_CALL_MANIFEST_PAYLOAD_REF_PREFIX = "payload-runner-call-input-manifest"
_RUNNER_CALL_MANIFEST_SQLITE_PAYLOAD_ID_PREFIX = (
    "sqlite-payload-runner-call-input-manifest"
)
_RUNNER_CALL_EVENT_ID_PREFIX = "event-runner-call-input-assembled"
_RUNNER_CALL_EVENT_ACTOR = "host.run_input"
_RUNNER_CALL_EVENT_SOURCE = "host.run_input.builder"
_RUNNER_CALL_KIND_INITIAL_USER_DISPATCH = "initial_user_dispatch"
_RUNNER_CALL_KIND_FOLLOWUP_USER_DISPATCH = "followup_user_dispatch"
_RUNNER_CALL_KIND_POST_COMPACTION_DISPATCH = "post_compaction_dispatch"
_RUNNER_CALL_TRIGGER_INITIAL_USER_INPUT = "initial_user_input"
_RUNNER_CALL_TRIGGER_FOLLOWUP_USER_INPUT = "followup_user_input"
_RUNNER_CALL_TRIGGER_HOST_RESUME = "host_resume"
_RUNNER_CALL_TRIGGER_CONTEXT_COMPACTION_COMPLETED = "context_compaction_completed"
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
    """

    messages: tuple[AgentMessage, ...]


@dataclass(frozen=True, slots=True)
class MemorySnapshotView:
    """Memory snapshot provider 输出。

    :param messages: memory stable layer messages。
    :param memory_snapshot_cursor: memory snapshot cursor；no-op provider 为 ``None``。
    :param policy_digest: memory policy digest；no-op provider 为 ``None``。
    :param diagnostics: memory provider 产生或透传的 diagnostics。
    :param represented_evidence_refs: 已被 stable evidence-backed fact 表示的
        accepted evidence refs。
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

    :param messages: compact artifact messages；Phase 5 noop 为空。
    :param compact_artifact_ref: compact artifact ref；Phase 5 noop 为 ``None``。
    :param compact_artifact_digest: compact artifact digest；Phase 5 noop 为 ``None``。
    :param represented_evidence_refs: 已被 accepted compact artifact 表示的
        canonical evidence refs。
    """

    messages: tuple[AgentMessage, ...]
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


class CurrentRunFactProvider(Protocol):
    """当前 Run durable fact provider 协议。"""

    def load_current_run_facts(
        self, snapshot: AttemptDispatchSnapshot
    ) -> CurrentRunFacts:
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

    def load_tool_executor(
        self, snapshot: AttemptDispatchSnapshot, current_facts: CurrentRunFacts
    ) -> ToolExecutor:
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

    def load_policy_snapshot(
        self, snapshot: AttemptDispatchSnapshot, current_facts: CurrentRunFacts
    ) -> PolicySnapshot:
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

    def record_runner_call_manifest(
        self, record_input: RunnerCallManifestRecordInput
    ) -> None:
        """记录一次 logical runner call input assembly manifest。

        :param record_input: manifest 构造输入。
        :returns: ``None``。
        :raises HostDurableError: manifest 无法写入或校验失败时抛出。
        """
        ...


class NoopRunnerCallManifestRecorder:
    """不写入 manifest 的测试 recorder。"""

    def record_runner_call_manifest(
        self, record_input: RunnerCallManifestRecordInput
    ) -> None:
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

    def record_runner_call_manifest(
        self, record_input: RunnerCallManifestRecordInput
    ) -> None:
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
            run_id=record_input.current_facts.run.run_id,
            attempt_id=record_input.current_facts.attempt.attempt_id,
            execution_id=record_input.current_facts.attempt.execution_id,
        )
        if existing is not None:
            return
        runner_call_index = _next_runner_call_index(
            transaction, run_id=record_input.current_facts.run.run_id
        )
        event_id = _runner_call_manifest_event_id(
            record_input.current_facts.run.run_id,
            record_input.current_facts.attempt.attempt_id,
            record_input.current_facts.attempt.execution_id,
            runner_call_index,
        )
        manifest = _runner_call_manifest_body(
            record_input,
            runner_call_index=runner_call_index,
            manifest_id=_runner_call_manifest_id(event_id),
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


class DurableCurrentRunFactProvider:
    """基于 Host durable store 的当前 Run fact provider。"""

    def __init__(self, transaction_runner: HostTransactionRunner) -> None:
        """初始化 provider。

        :param transaction_runner: Host durable transaction runner。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner
        self._event_log_store = EventLogStore()

    def load_current_run_facts(
        self, snapshot: AttemptDispatchSnapshot
    ) -> CurrentRunFacts:
        """读取当前 RunInputBuilder 所需 durable facts。

        :param snapshot: Attempt dispatch snapshot。
        :returns: 当前 Run facts。
        :raises HostDurableError: durable facts 缺失或不匹配时抛出。
        """

        return self._transaction_runner.run_read(
            lambda transaction: self._load_current_run_facts_tx(
                transaction, snapshot
            )
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
        dispatch_record = read_dispatch_record_by_attempt_id(
            transaction, snapshot.attempt_id
        )
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
            self._event_log_store.read_event_by_id(
                transaction, run.input_event_id
            ),
            expected_type=_EVENT_TYPE_USER_INPUT_ACCEPTED,
        )
        run_accepted_event = _require_event(
            self._event_log_store.read_event_by_id(
                transaction, run.accepted_event_id
            ),
            expected_type=_EVENT_TYPE_RUN_ACCEPTED,
        )
        run_started_event = _require_event(
            self._event_log_store.read_event_by_id(
                transaction, run.started_event_id
            ),
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
            lambda transaction: self._load_session_continuity_tx(
                transaction, snapshot, current_facts
            )
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
        resume_message = _resume_wait_message_from_current_start(
            transaction, current_facts
        )
        if resume_message is None:
            return SessionContinuityView(messages=())
        return SessionContinuityView(messages=(resume_message,))


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
            lambda transaction: self._load_memory_snapshot_tx(
                transaction, snapshot, current_facts
            )
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
        lag_events = (
            required_event_sequence
            - memory_snapshot.cursor.checkpoint_event_sequence
        )
        if lag_events < 0:
            self._raise_repair_required(
                session_id=snapshot.session_id,
                reason=MemoryRepairReason.SNAPSHOT_AHEAD_OF_REQUIRED,
                required_event_sequence=required_event_sequence,
                observed_cursor=memory_snapshot.cursor,
            )
        if lag_events <= 0:
            return _memory_snapshot_view(
                memory_snapshot, current_facts, self._policy
            )
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

        event_filter = event_log_read_filter_from_projection_filter(
            conversation_memory_projection_event_filter()
        )
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
            messages=(),
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

        compacted_event = _latest_compacted_event_before_attempt(
            transaction, current_facts
        )
        if compacted_event is None:
            return CompactPipelineOrdinaryRawTailHandoff(
                messages=(),
                material_blocks=(),
                source_refs=(),
                material_view_digest=selected_material_view_digest(()),
                selected_recent_window_turn_floor=0,
            )
        _validate_loaded_compact_view_matches_event(
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
            selected_recent_window_turn_floor=(
                self._policy.selected_recent_window_turn_floor
            ),
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
                represented_evidence_refs=_represented_evidence_refs(
                    memory, compact
                ),
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
            lambda transaction: self._load_compact_artifact_tx(
                transaction, snapshot, current_facts
            )
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
                messages=(),
                compact_artifact_ref=None,
                compact_artifact_digest=None,
            )
        payload = _payload_object(row)
        artifact_ref = _required_text_field(
            payload, _PAYLOAD_FIELD_COMPACT_ARTIFACT_REF
        )
        artifact_digest = _required_text_field(
            payload, _PAYLOAD_FIELD_COMPACT_ARTIFACT_DIGEST
        )
        message_content = _compact_artifact_message_content(
            compacted_event=row,
            payload=payload,
        )
        messages: tuple[SystemMessage, ...] = (
            ()
            if message_content is None
            else (
                SystemMessage(
                    role=AgentMessageRole.SYSTEM,
                    content=message_content,
                ),
            )
        )
        return CompactArtifactView(
            messages=messages,
            compact_artifact_ref=artifact_ref,
            compact_artifact_digest=artifact_digest,
            represented_evidence_refs=_accepted_evidence_mapping_refs(payload),
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
        return ToolSchemaSnapshot(
            tool_schemas=(), disable_tools=True, tool_runtime_handle=None
        )


class NoToolExecutor:
    """Phase 5 no-tool 防线 executor。"""

    async def execute(
        self, request: BatchToolExecutionRequest
    ) -> BatchToolExecutionOutcome:
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

    def load_tool_executor(
        self, snapshot: AttemptDispatchSnapshot, current_facts: CurrentRunFacts
    ) -> ToolExecutor:
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

        handle = self._handle_provider.load_tool_runtime_handle(
            snapshot, current_facts
        )
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

    def load_tool_executor(
        self, snapshot: AttemptDispatchSnapshot, current_facts: CurrentRunFacts
    ) -> ToolExecutor:
        """读取 tool-enabled ToolExecutor。

        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: ToolRuntimeHandle 暴露的 executor。
        """

        return self._handle_provider.load_tool_runtime_handle(
            snapshot, current_facts
        ).tool_executor


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
        content = "\n".join(
            (
                _EXECUTION_GUIDANCE_PREFIX,
                "Use the available context and tools under the current run limits.",
                _tools_scene_line(tool_execution_mode),
            )
        )
        return (
            SystemMessage(role=AgentMessageRole.SYSTEM, content=content),
        )


class StaticPolicySnapshotProvider:
    """显式注入 policy snapshot 的 provider。"""

    def __init__(self, policy_snapshot: PolicySnapshot) -> None:
        """初始化 provider。

        :param policy_snapshot: 显式 policy snapshot。
        :returns: ``None``。
        """

        self._policy_snapshot = policy_snapshot

    def load_policy_snapshot(
        self, snapshot: AttemptDispatchSnapshot, current_facts: CurrentRunFacts
    ) -> PolicySnapshot:
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


class RunInputBuilder:
    """基于 typed providers 构造 deterministic no-tool AgentRunRequest。"""

    def __init__(
        self,
        *,
        current_run_provider: CurrentRunFactProvider,
        session_continuity_provider: SessionContinuityProvider,
        memory_snapshot_provider: MemorySnapshotProvider,
        compact_artifact_provider: CompactArtifactProvider,
        accepted_tool_evidence_material_provider: (
            AcceptedToolEvidenceMaterialProvider
        ),
        context_fallback_provider: ContextFallbackProvider,
        tool_schema_snapshot_provider: ToolSchemaSnapshotProvider,
        tool_executor_provider: ToolExecutorProvider,
        scene_parameter_provider: SceneParameterProvider,
        policy_snapshot_provider: PolicySnapshotProvider,
        tool_execution_mode: ToolExecutionMode,
        runner_call_manifest_recorder: RunnerCallManifestRecorder | None = None,
        protected_recent_raw_tail_provider: (
            CompactPipelineProtectedRawTailProvider | None
        ) = None,
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
        self._accepted_tool_evidence_material_provider = (
            accepted_tool_evidence_material_provider
        )
        self._context_fallback_provider = context_fallback_provider
        self._tool_schema_snapshot_provider = tool_schema_snapshot_provider
        self._tool_executor_provider = tool_executor_provider
        self._scene_parameter_provider = scene_parameter_provider
        self._policy_snapshot_provider = policy_snapshot_provider
        self._tool_execution_mode = tool_execution_mode
        self._runner_call_manifest_recorder = (
            NoopRunnerCallManifestRecorder()
            if runner_call_manifest_recorder is None
            else runner_call_manifest_recorder
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

        current_facts = self._current_run_provider.load_current_run_facts(
            attempt_snapshot
        )
        policy_snapshot = self._policy_snapshot_provider.load_policy_snapshot(
            attempt_snapshot, current_facts
        )
        continuity = self._session_continuity_provider.load_session_continuity(
            attempt_snapshot, current_facts
        )
        memory = self._memory_snapshot_provider.load_memory_snapshot(
            attempt_snapshot, current_facts
        )
        compact = self._compact_artifact_provider.load_compact_artifact(
            attempt_snapshot, current_facts
        )
        fallback = self._context_fallback_provider.load_context_fallback(
            run_id=current_facts.run.run_id,
            run_started_event_sequence=(
                current_facts.run_started_event.event_sequence
            ),
            current_input_ref=current_facts.user_input_event.event_id,
        )
        if fallback is None:
            protected_recent_raw_tail = (
                self._protected_recent_raw_tail_provider
                .load_ordinary_raw_tail(
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
                *compact.messages,
                *protected_recent_raw_tail.messages,
                *continuity.messages,
            )
        else:
            evidence = (
                self._accepted_tool_evidence_material_provider
                .load_accepted_tool_evidence_materials(
                    attempt_snapshot,
                    current_facts,
                    memory,
                    compact,
                )
            )
            fallback_material_blocks = (
                fallback.material_blocks
                if fallback.material_blocks is not None
                else build_run_input_material_blocks(
                    current_facts=current_facts,
                    memory=memory,
                    compact=compact,
                    continuity=continuity,
                    accepted_tool_evidence=evidence,
                )
            )
            bounded_context_messages = _fallback_context_messages(
                fallback=fallback,
                material_blocks=fallback_material_blocks,
            )
        tool_snapshot = self._tool_schema_snapshot_provider.load_tool_schema_snapshot(
            attempt_snapshot, current_facts
        )
        tool_executor = self._tool_executor_provider.load_tool_executor(
            attempt_snapshot, current_facts
        )
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
            UserMessage(
                role=AgentMessageRole.USER,
                content=current_facts.user_prompt,
            ),
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

    def build_material_blocks(
        self, attempt_snapshot: AttemptDispatchSnapshot
    ) -> tuple[RunInputMaterialBlock, ...]:
        """构造与 ordinary Run input 同源的 compact material block view。

        本方法是 Host internal helper，供 Context Governance / compact builder
        复用 RunInputBuilder 的普通输入 material source；它不改变
        ``AgentRunRequest`` public shape。

        :param attempt_snapshot: Attempt dispatch snapshot。
        :returns: ordinary input material blocks。
        :raises HostDurableError: durable facts 缺失或 provider 读取失败时抛出。
        """

        current_facts = self._current_run_provider.load_current_run_facts(
            attempt_snapshot
        )
        continuity = self._session_continuity_provider.load_session_continuity(
            attempt_snapshot, current_facts
        )
        memory = self._memory_snapshot_provider.load_memory_snapshot(
            attempt_snapshot, current_facts
        )
        compact = self._compact_artifact_provider.load_compact_artifact(
            attempt_snapshot, current_facts
        )
        evidence = (
            self._accepted_tool_evidence_material_provider
            .load_accepted_tool_evidence_materials(
                attempt_snapshot, current_facts, memory, compact
            )
        )
        return build_run_input_material_blocks(
            current_facts=current_facts,
            memory=memory,
            compact=compact,
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
        session_continuity_provider=DurableSessionContinuityProvider(
            transaction_runner
        ),
        memory_snapshot_provider=(
            NoopMemorySnapshotProvider()
            if memory_snapshot_provider is None
            else memory_snapshot_provider
        ),
        compact_artifact_provider=(
            NoopCompactArtifactProvider()
            if compact_artifact_provider is None
            else compact_artifact_provider
        ),
        accepted_tool_evidence_material_provider=(
            DurableAcceptedToolEvidenceMaterialProvider(transaction_runner)
        ),
        context_fallback_provider=(
            NoopContextFallbackProvider()
            if context_fallback_provider is None
            else context_fallback_provider
        ),
        tool_schema_snapshot_provider=NoopToolSchemaSnapshotProvider(),
        tool_executor_provider=NoToolExecutorProvider(),
        scene_parameter_provider=DefaultSceneParameterProvider(),
        policy_snapshot_provider=StaticPolicySnapshotProvider(policy_snapshot),
        tool_execution_mode=tool_execution_mode,
        runner_call_manifest_recorder=DurableRunnerCallManifestRecorder(
            transaction_runner
        ),
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
        session_continuity_provider=DurableSessionContinuityProvider(
            transaction_runner
        ),
        memory_snapshot_provider=(
            NoopMemorySnapshotProvider()
            if memory_snapshot_provider is None
            else memory_snapshot_provider
        ),
        compact_artifact_provider=(
            NoopCompactArtifactProvider()
            if compact_artifact_provider is None
            else compact_artifact_provider
        ),
        accepted_tool_evidence_material_provider=(
            DurableAcceptedToolEvidenceMaterialProvider(transaction_runner)
        ),
        context_fallback_provider=(
            NoopContextFallbackProvider()
            if context_fallback_provider is None
            else context_fallback_provider
        ),
        tool_schema_snapshot_provider=ToolRuntimeSchemaSnapshotProvider(
            handle_provider
        ),
        tool_executor_provider=ToolRuntimeExecutorProvider(handle_provider),
        scene_parameter_provider=DefaultSceneParameterProvider(),
        policy_snapshot_provider=StaticPolicySnapshotProvider(policy_snapshot),
        tool_execution_mode=ToolExecutionMode.TOOL_ENABLED,
        runner_call_manifest_recorder=DurableRunnerCallManifestRecorder(
            transaction_runner
        ),
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


def _validate_current_event_scope(
    snapshot: AttemptDispatchSnapshot, event: EventLogRow
) -> None:
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
    facts = _memory_evidence_fact_message(
        snapshot.evidence_fact_memory.evidence_backed_facts
    )
    if facts is not None:
        messages.append(facts)
    anchors = _memory_answer_anchor_message(snapshot)
    if anchors is not None:
        messages.append(anchors)
    intents = _memory_forward_intent_message(snapshot)
    if intents is not None:
        messages.append(intents)
    reference = _memory_reference_continuity_message(
        snapshot.trace_memory.reference_continuity_items
    )
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
        lines.append(
            f"Source F{index}: "
            f"claim_text={fact.claim_text}; "
            f"evidence_kind={fact.evidence_kind.value}"
        )
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
            (
                child.display_text
                if child.ordinal is None
                else f"{child.ordinal}. {child.display_text}"
            )
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
        lines.append(
            "forward_intent="
            f"type={intent.intent_type}; status={intent.status}; text={intent.text}"
        )
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
    compact: CompactArtifactView,
    continuity: SessionContinuityView,
    accepted_tool_evidence: tuple[RunInputMaterialBlock, ...] = (),
) -> tuple[RunInputMaterialBlock, ...]:
    """构造 ordinary Run input 的共享 material block list。

    :param current_facts: 当前 Run durable facts。
    :param memory: memory snapshot provider view。
    :param compact: compact artifact provider view。
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
    compact_source_ref = _compact_material_source_ref(compact)
    for index, message in enumerate(compact.messages):
        blocks.append(
            run_input_material_block(
                block_id=f"compact:{index}",
                section=CompactMaterialSection.TRACE_MATERIAL,
                kind=CompactMaterialBlockKind.SESSION_SUMMARY,
                text=_run_input_message_content(message),
                canonical_source_refs=(compact_source_ref,),
                event_sequence=None,
                event_sub_index=index,
                already_represented=True,
            )
        )
    for index, message in enumerate(continuity.messages):
        blocks.append(
            run_input_material_block(
                block_id=f"continuity:{index}",
                section=CompactMaterialSection.TRACE_MATERIAL,
                kind=_history_material_kind(message),
                text=_run_input_message_content(message),
                canonical_source_refs=(f"message:continuity:{index}",),
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

    sections: dict[str, list[str]] = {
        section: [] for section in _SYSTEM_ENVELOPE_SECTION_ORDER
    }
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
    if content.startswith(_ACCEPTED_COMPACTED_VIEW_PREFIX):
        return _stripped_prefixed_system_body(
            content,
            prefix=_ACCEPTED_COMPACTED_VIEW_PREFIX,
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
    if content.startswith(_RESUME_GUIDANCE_PREFIX):
        return _stripped_prefixed_system_body(
            content,
            prefix=_RESUME_GUIDANCE_PREFIX,
            section=_SYSTEM_SECTION_RESUME_GUIDANCE,
        )
    return (_SYSTEM_SECTION_TASK_INSTRUCTIONS, content)


def _stripped_prefixed_system_body(
    content: str, *, prefix: str, section: str
) -> tuple[str, str]:
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
        f"{_SYSTEM_ENVELOPE_HEADER_PREFIX}{section}\n{body}"
        for section, body, _item_count in section_blocks
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
            raise HostDurableError(
                "ordinary system envelope exposes internal governance material"
            )


def _system_envelope_overhead(section_blocks: tuple[tuple[str, str, int], ...]) -> int:
    """计算 envelope 固定 header 与 separator 开销。

    :param section_blocks: 非空 section blocks。
    :returns: 固定格式开销字符数。
    """

    if not section_blocks:
        return 0
    header_chars = sum(
        len(_SYSTEM_ENVELOPE_HEADER_PREFIX) + len(section) + 1
        for section, _body, _item_count in section_blocks
    )
    separator_chars = len(_SYSTEM_ENVELOPE_SEPARATOR) * (len(section_blocks) - 1)
    item_separator_chars = sum(
        item_count - 1 for _section, _body, item_count in section_blocks
    )
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
    selected_blocks = tuple(
        block for block in material_blocks if block.block_id in selected_ids
    )
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
        and fallback_window_digest(fallback.fallback_input_window)
        != fallback.fallback_input_digest
    ):
        raise HostDurableError("fallback input digest mismatch")
    view_digest = selected_material_view_digest(selected_blocks)
    if (
        fallback.selected_material_view_digest is not None
        and fallback.selected_material_view_digest != view_digest
    ):
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
        selected_raw_turn_count = sum(
            1 for block in selected_blocks if is_turn_group_material_block(block)
        )
        if selected_raw_turn_count != fallback.selected_raw_turn_count:
            raise HostDurableError("fallback selected raw turn count mismatch")
    if fallback.selected_recent_window_turn_floor is None:
        return
    if fallback.selected_recent_window_turn_floor == 0:
        return
    try:
        protected_group_ids = protected_recent_turn_group_ids_for_material_blocks(
            material_blocks,
            selected_recent_window_turn_floor=(
                fallback.selected_recent_window_turn_floor
            ),
        )
    except ValueError as exc:
        raise HostDurableError(
            "fallback protected turn_group_id consistency mismatch"
        ) from exc
    selected_ids = frozenset(block.block_id for block in selected_blocks)
    expected_protected_ids = frozenset(
        block.block_id
        for block in material_blocks
        if block.turn_group_id in protected_group_ids
        and is_turn_group_material_block(block)
    )
    if not expected_protected_ids.issubset(selected_ids):
        raise HostDurableError("fallback protected group consistency mismatch")


def _fallback_message_from_material_block(block: RunInputMaterialBlock) -> AgentMessage:
    """把 fallback material block 渲染为 Engine message。

    :param block: selected fallback material block。
    :returns: Agent message。
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
        return SystemMessage(
            role=AgentMessageRole.SYSTEM,
            content=_accepted_tool_evidence_content(block),
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


def _accepted_tool_evidence_content(block: RunInputMaterialBlock) -> str:
    """把 accepted tool evidence block 改写为业务可读 material。

    :param block: accepted tool evidence material block。
    :returns: 不含内部 ref / digest 的 evidence 文本。
    :raises HostDurableError: 可读工具名缺失时抛出。
    """

    if block.readable_tool_name is None:
        raise HostDurableError("accepted tool evidence requires readable tool name")
    query_text = (
        "The original tool query is not available in readable form."
        if block.readable_query_text is None
        else block.readable_query_text
    )
    lines = [
        _ACCEPTED_TOOL_EVIDENCE_PREFIX,
        f"tool_name={block.readable_tool_name}",
        f"query={query_text}",
    ]
    source_text = _llm_facing_evidence_source_text(block.readable_source_text)
    if source_text is not None:
        lines.append(f"source={source_text}")
    lines.append(f"result={block.text}")
    return "\n".join(lines)


def _llm_facing_evidence_source_text(source_text: str | None) -> str | None:
    """过滤 accepted evidence source note 中的内部 provenance。

    :param source_text: compact material provider 给出的 source note。
    :returns: 仅含业务可读 source locator 的文本；无可读项时返回 ``None``。
    """

    if source_text is None:
        return None
    parts = tuple(
        part.strip()
        for part in source_text.split(_EVIDENCE_SOURCE_PART_SEPARATOR)
        if part.strip() != ""
    )
    visible_parts = tuple(
        part for part in parts if not _is_internal_evidence_source_part(part)
    )
    if len(visible_parts) == 0:
        return None
    return _EVIDENCE_SOURCE_PART_SEPARATOR.join(visible_parts)


def _is_internal_evidence_source_part(source_part: str) -> bool:
    """判断 source note 片段是否属于内部 provenance。

    :param source_part: source note 片段。
    :returns: 内部 provenance 返回 ``True``。
    """

    return any(
        source_part.startswith(prefix)
        for prefix in _INTERNAL_EVIDENCE_SOURCE_PREFIXES
    )


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


def _compact_material_source_ref(compact: CompactArtifactView) -> str:
    """返回 compact artifact material canonical source ref。

    :param compact: compact artifact view。
    :returns: source ref。
    """

    if compact.compact_artifact_ref is not None:
        return f"compact:{compact.compact_artifact_ref}"
    if compact.compact_artifact_digest is not None:
        return f"compact:{compact.compact_artifact_digest}"
    return "compact:no-artifact"


def _represented_evidence_refs(
    memory: MemorySnapshotView, compact: CompactArtifactView
) -> tuple[str, ...]:
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


def _memory_projection_event_from_row(
    transaction: HostTransaction, row: EventLogRow
) -> MemoryProjectionEvent:
    """把 EventLog row 转换为 memory projection event。

    :param transaction: Host transaction。
    :param row: EventLog row。
    :returns: memory projection event。
    :raises HostDurableError: payload 不是 JSON object 时抛出。
    """

    payload = _payload_with_assistant_final_answer(transaction, row)
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
    )


def _payload_with_assistant_final_answer(
    transaction: HostTransaction, row: EventLogRow
) -> Mapping[str, JsonValue]:
    """必要时把 memory projection 需要的 transient payload 补齐。

    :param transaction: Host transaction。
    :param row: EventLog row。
    :returns: memory projection 消费的 payload。
    :raises HostDurableError: terminal artifact descriptor 或工具 payload 损坏时抛出。
    """

    payload = _payload_object(row)
    if row.event_type == _EVENT_TYPE_TOOL_RESULT_ACCEPTED:
        return _tool_result_memory_payload(transaction, row, payload)
    if row.event_type != _EVENT_TYPE_RUN_SUCCEEDED:
        return payload
    if (
        assistant_final_answer_text_from_run_payload(
            payload,
            text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
        )
        is not None
    ):
        return payload
    final_answer = assistant_final_answer_continuity_text(
        transaction,
        payload,
        text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
    )
    if final_answer is None:
        return payload
    merged: dict[str, JsonValue] = dict(payload)
    merged[_PAYLOAD_FIELD_FINAL_ANSWER] = final_answer
    return merged


def _tool_result_memory_payload(
    transaction: HostTransaction,
    row: EventLogRow,
    payload: Mapping[str, JsonValue],
) -> Mapping[str, JsonValue]:
    """读取 memory inline repair 使用的完整 accepted tool result payload。

    :param transaction: Host transaction。
    :param row: ``TOOL_RESULT_ACCEPTED`` EventLog row。
    :param payload: inline hot payload。
    :returns: digest-checked 工具结果 payload。
    :raises HostDurableError: envelope 或 payload descriptor 损坏时抛出。
    """

    try:
        envelope = accepted_evidence_envelope_from_payload(
            payload,
            producer_event_ref=row.event_id,
        )
    except ValueError as exc:
        if str(exc) == ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH:
            raise HostDurableError(str(exc)) from exc
        raise HostDurableError("canonical evidence envelope is invalid") from exc
    if envelope is None:
        return payload
    return event_payload_object_for_result_ref(
        transaction,
        row,
        expected_payload_ref=envelope.result_ref.payload_ref,
        expected_payload_digest=envelope.result_ref.payload_digest,
        payload_label=_EVENT_TYPE_TOOL_RESULT_ACCEPTED,
    )


def _latest_compacted_event_before_attempt(
    transaction: HostTransaction, current_facts: CompactPipelineCurrentRunFacts
) -> EventLogRow | None:
    """读取当前 Attempt start cursor 前最新 ``CONTEXT_COMPACTED``。

    :param transaction: Host durable transaction。
    :param current_facts: 当前 Run facts。
    :returns: 最新 compacted event；不存在时为 ``None``。
    """

    rows = transaction.fetchall(
        f"""
        SELECT event_id
        FROM {TABLE_EVENT_LOG}
        WHERE session_id = ?
          AND run_id = ?
          AND event_type = ?
          AND event_class = ?
          AND event_sequence < ?
        ORDER BY event_sequence DESC
        LIMIT 1
        """,
        (
            current_facts.run.session_id,
            current_facts.run.run_id,
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
    *, compact: CompactPipelineCompactArtifactView, compacted_event: EventLogRow
) -> None:
    """校验 compact provider view 来自同一个 current-run compact event。

    :param compact: compact provider view。
    :param compacted_event: current Run / current Attempt 前的 compacted event。
    :returns: ``None``。
    :raises HostDurableError: artifact ref 或 digest 不一致时抛出。
    """

    payload = _payload_object(compacted_event)
    artifact_ref = _required_text_field(payload, _PAYLOAD_FIELD_COMPACT_ARTIFACT_REF)
    artifact_digest = _required_text_field(
        payload, _PAYLOAD_FIELD_COMPACT_ARTIFACT_DIGEST
    )
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

    compacted_payload = _payload_object(compacted_event)
    operation_id = _required_text_field(
        compacted_payload,
        _PAYLOAD_FIELD_OPERATION_ID,
    )
    requested_event = EventLogStore().read_event_by_id(transaction, operation_id)
    if (
        requested_event is None
        or requested_event.event_type != CONTEXT_COMPACTION_REQUESTED
    ):
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


def _compact_artifact_message_content(
    *,
    compacted_event: EventLogRow,
    payload: Mapping[str, JsonValue],
) -> str | None:
    """构造 compact artifact SystemMessage 内容。

    :param compacted_event: ``CONTEXT_COMPACTED`` event row。
    :param payload: compacted payload。
    :returns: message 内容；没有可渲染语义项时返回 ``None``。
    """

    del compacted_event
    semantic_lines = _vnext_compact_candidate_semantic_lines(payload)
    if len(semantic_lines) == 0:
        return None
    lines = [
        _ACCEPTED_COMPACTED_VIEW_PREFIX,
        *semantic_lines,
    ]
    return "\n".join(lines)


def _accepted_evidence_mapping_refs(
    payload: Mapping[str, JsonValue],
) -> tuple[str, ...]:
    """读取 vNext compact payload 中已接受 evidence mapping refs。

    :param payload: ``CONTEXT_COMPACTED`` vNext payload。
    :returns: accepted evidence mapping refs。
    :raises HostDurableError: 字段缺失或包含非文本元素时抛出。
    """

    return _required_text_list_field(
        payload, _PAYLOAD_FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS
    )


def _vnext_compact_candidate_semantic_lines(
    payload: Mapping[str, JsonValue],
) -> tuple[str, ...]:
    """从 vNext accepted candidate 渲染完整语义条目。

    :param payload: ``CONTEXT_COMPACTED`` vNext payload。
    :returns: LLM-facing semantic lines。
    :raises HostDurableError: accepted candidate 结构损坏时抛出。
    """

    candidate = _required_mapping_field(payload, _PAYLOAD_FIELD_ACCEPTED_CANDIDATE)
    _required_text_field(candidate, _PAYLOAD_FIELD_SCHEMA_VERSION)
    facts = _required_mapping_list_field(
        candidate, _PAYLOAD_FIELD_EVIDENCE_BACKED_FACTS
    )
    anchors = _required_mapping_list_field(candidate, _PAYLOAD_FIELD_ANSWER_ANCHORS)
    intents = _required_mapping_list_field(candidate, _PAYLOAD_FIELD_FORWARD_INTENTS)
    references = _required_mapping_list_field(
        candidate, _PAYLOAD_FIELD_REFERENCE_CONTINUITY_ITEMS
    )
    lines: list[str] = []
    session_summary = _optional_session_summary_text(candidate)
    if session_summary is not None:
        lines.append(f"session_summary={session_summary}")
    lines.extend(_accepted_compact_fact_lines(facts))
    lines.extend(_accepted_compact_answer_anchor_lines(anchors))
    lines.extend(_accepted_compact_forward_intent_lines(intents))
    lines.extend(_accepted_compact_reference_lines(references))
    return tuple(lines)


def _accepted_compact_fact_lines(
    facts: tuple[Mapping[str, JsonValue], ...],
) -> tuple[str, ...]:
    """渲染 accepted compact fact 语义条目。

    :param facts: fact JSON objects。
    :returns: LLM-facing fact lines。
    :raises HostDurableError: fact 结构损坏时抛出。
    """

    lines: list[str] = []
    for index, fact in enumerate(facts, start=1):
        parts = [
            f"fact {index}: claim_text={_required_text_field(fact, _PAYLOAD_FIELD_CLAIM_TEXT)}"
        ]
        evidence_kind = _optional_semantic_text_field(
            fact,
            _PAYLOAD_FIELD_EVIDENCE_KIND,
        )
        if evidence_kind is not None:
            parts.append(f"evidence_kind={evidence_kind}")
        evidence_labels = _optional_text_list_field(
            fact,
            _PAYLOAD_FIELD_EVIDENCE_LABELS,
        )
        if len(evidence_labels) > 0:
            parts.append(f"evidence_labels={', '.join(evidence_labels)}")
        source_labels = _optional_text_list_field(fact, _PAYLOAD_FIELD_SOURCE_LABELS)
        if len(source_labels) > 0:
            parts.append(f"source_labels={', '.join(source_labels)}")
        lines.append("; ".join(parts))
    return tuple(lines)


def _accepted_compact_answer_anchor_lines(
    anchors: tuple[Mapping[str, JsonValue], ...],
) -> tuple[str, ...]:
    """渲染 accepted compact answer anchor 语义条目。

    :param anchors: answer anchor JSON objects。
    :returns: LLM-facing answer anchor lines。
    :raises HostDurableError: anchor 结构损坏时抛出。
    """

    lines: list[str] = []
    for index, anchor in enumerate(anchors, start=1):
        title = _required_text_field(anchor, _PAYLOAD_FIELD_ANCHOR_TITLE)
        item_text = _accepted_compact_anchor_item_text(anchor)
        line = f"answer_anchor {index}: title={title}"
        if item_text != "":
            line = f"{line}; items={item_text}"
        lines.append(line)
    return tuple(lines)


def _accepted_compact_anchor_item_text(anchor: Mapping[str, JsonValue]) -> str:
    """渲染 answer anchor 子项文本。

    :param anchor: answer anchor JSON object。
    :returns: 子项文本；没有子项时返回空字符串。
    :raises HostDurableError: 子项结构损坏时抛出。
    """

    value = anchor.get(_PAYLOAD_FIELD_ANCHOR_ITEMS)
    if value is None:
        return ""
    if not isinstance(value, list):
        raise HostDurableError("answer_anchor.anchor_items must be list")
    items: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise HostDurableError("answer_anchor.anchor_items item must be object")
        display_text = _required_text_field(item, _PAYLOAD_FIELD_DISPLAY_TEXT)
        ordinal = item.get(_PAYLOAD_FIELD_ORDINAL)
        if ordinal is None:
            items.append(display_text)
        elif isinstance(ordinal, int):
            items.append(f"{ordinal}. {display_text}")
        else:
            raise HostDurableError("answer_anchor.anchor_items ordinal must be int")
    return "; ".join(items)


def _accepted_compact_forward_intent_lines(
    intents: tuple[Mapping[str, JsonValue], ...],
) -> tuple[str, ...]:
    """渲染 accepted compact forward intent 语义条目。

    :param intents: forward intent JSON objects。
    :returns: LLM-facing forward intent lines。
    :raises HostDurableError: intent 结构损坏时抛出。
    """

    lines: list[str] = []
    for index, intent in enumerate(intents, start=1):
        lines.append(
            "forward_intent "
            f"{index}: type={_required_text_field(intent, _PAYLOAD_FIELD_INTENT_TYPE)}; "
            f"status={_required_text_field(intent, _PAYLOAD_FIELD_STATUS)}; "
            f"text={_required_text_field(intent, _PAYLOAD_FIELD_TEXT)}"
        )
    return tuple(lines)


def _accepted_compact_reference_lines(
    references: tuple[Mapping[str, JsonValue], ...],
) -> tuple[str, ...]:
    """渲染 accepted compact reference continuity 语义条目。

    :param references: reference continuity JSON objects。
    :returns: LLM-facing reference continuity lines。
    :raises HostDurableError: reference 结构损坏时抛出。
    """

    lines: list[str] = []
    for index, reference in enumerate(references, start=1):
        parts = [
            f"reference_continuity {index}: text={_required_text_field(reference, _PAYLOAD_FIELD_TEXT)}"
        ]
        reason = _optional_semantic_text_field(reference, _PAYLOAD_FIELD_REASON)
        if reason is not None:
            parts.append(f"reason={reason}")
        source_labels = _optional_text_list_field(
            reference,
            _PAYLOAD_FIELD_SOURCE_LABELS,
        )
        if len(source_labels) > 0:
            parts.append(f"source_labels={', '.join(source_labels)}")
        lines.append("; ".join(parts))
    return tuple(lines)


def _optional_session_summary_text(
    candidate: Mapping[str, JsonValue],
) -> str | None:
    """读取 vNext accepted candidate 的可选 session summary 文本。

    :param candidate: ``accepted_candidate`` JSON object。
    :returns: summary text；无 summary 时返回 ``None``。
    :raises HostDurableError: summary 字段存在但结构损坏时抛出。
    """

    value = candidate.get(_PAYLOAD_FIELD_SESSION_SUMMARY)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise HostDurableError("accepted_candidate.session_summary must be object")
    return _required_text_field(value, _PAYLOAD_FIELD_SUMMARY_TEXT)


def _required_mapping_field(
    payload: Mapping[str, JsonValue], field_name: str
) -> Mapping[str, JsonValue]:
    """读取必填 JSON object 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: JSON object。
    :raises HostDurableError: 字段缺失或非 object 时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        raise HostDurableError(f"payload field {field_name} must be object")
    return value


def _required_mapping_list_field(
    payload: Mapping[str, JsonValue], field_name: str
) -> tuple[Mapping[str, JsonValue], ...]:
    """读取必填 JSON object list 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: JSON object tuple。
    :raises HostDurableError: 字段缺失、非 list 或元素非 object 时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, list):
        raise HostDurableError(f"payload field {field_name} must be list")
    items: list[Mapping[str, JsonValue]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise HostDurableError(f"payload field {field_name} item must be object")
        items.append(item)
    return tuple(items)


def _required_text_list_field(
    payload: Mapping[str, JsonValue], field_name: str
) -> tuple[str, ...]:
    """读取必填文本 list 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: 文本 tuple。
    :raises HostDurableError: 字段缺失、非 list 或元素非文本时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, list):
        raise HostDurableError(f"payload field {field_name} must be list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or item.strip() == "":
            raise HostDurableError(f"payload field {field_name} item must be text")
        result.append(item)
    return tuple(result)


def _optional_text_list_field(
    payload: Mapping[str, JsonValue], field_name: str
) -> tuple[str, ...]:
    """读取可选文本 list 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: 文本 tuple；字段不存在时返回空 tuple。
    :raises HostDurableError: 字段存在但非 list 或元素非文本时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise HostDurableError(f"payload field {field_name} must be list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or item.strip() == "":
            raise HostDurableError(f"payload field {field_name} item must be text")
        result.append(item)
    return tuple(result)


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


def _optional_semantic_text_field(
    payload: Mapping[str, JsonValue], field_name: str
) -> str | None:
    """读取 accepted compact semantic renderer 的可选文本字段。

    字段不存在时表示该 semantic item 不提供该属性；字段一旦存在，必须是
    非空文本，避免把损坏 compact payload 静默渲染为缺省语义。

    :param payload: payload 映射。
    :param field_name: 字段名。
    :returns: 文本或 ``None``。
    :raises HostDurableError: 字段存在但不是非空文本时抛出。
    """

    if field_name not in payload:
        return None
    return _required_text_field(payload, field_name)


def _optional_mapping_text(
    payload: Mapping[str, JsonValue], field_name: str
) -> str | None:
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
    return (
        SystemMessage(role=AgentMessageRole.SYSTEM, content=system_prompt),
    )


def _optional_payload_text(
    payload: Mapping[str, JsonValue], *, field_name: str
) -> str | None:
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


def _execution_target_from_accepted_event(
    event: EventLogRow, *, fallback: str
) -> str:
    """从 RUN_ACCEPTED payload 读取 execution target。

    :param event: RUN_ACCEPTED event。
    :param fallback: payload 缺失时使用的 Run row execution target。
    :returns: execution target。
    :raises HostDurableError: payload 字段类型非法时抛出。
    """

    payload = _payload_object(event)
    value = _optional_payload_text(
        payload, field_name=_PAYLOAD_FIELD_EXECUTION_TARGET
    )
    if value is None:
        return fallback
    return value


def _resume_wait_message_from_current_start(
    transaction: HostTransaction, current_facts: CurrentRunFacts
) -> SystemMessage | None:
    """从当前 resume ``RUN_STARTED`` 重建 wait result fact message。

    :param transaction: Host durable transaction。
    :param current_facts: 当前 Run facts。
    :returns: resume wait fact system message；非 resume Attempt 返回 ``None``。
    :raises HostDurableError: resume payload 或引用事件无法投影时抛出。
    """

    start_payload = _payload_object(current_facts.run_started_event)
    start_reason = _optional_payload_text(
        start_payload, field_name=_PAYLOAD_FIELD_START_REASON
    )
    if start_reason != "resume":
        return None
    tool_result_event_id = _event_id_from_payload_ref(
        start_payload, field_name=_PAYLOAD_FIELD_TOOL_RESULT_EVENT_REF
    )
    tool_result_event = read_event_by_id(transaction, tool_result_event_id)
    if tool_result_event is None:
        raise HostDurableError("resume tool result event not found")
    _require_event(
        tool_result_event,
        expected_type=_EVENT_TYPE_TOOL_RESULT_ACCEPTED,
    )
    payload = _payload_object(tool_result_event)
    result_text = json.dumps(
        payload.get("result"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    content = "\n".join(
        (
            _RESUME_GUIDANCE_PREFIX,
            "A previous interrupted step has an accepted wait result.",
            f"tool_name={_required_payload_text(payload, field_name='tool_name')}",
            "resolution_kind="
            f"{_required_payload_text(payload, field_name='resolution_kind')}",
            "tool_fact_kind="
            f"{_required_payload_text(payload, field_name='tool_fact_kind')}",
            f"result={result_text}",
            (
                "This wait result is the accepted result for the interrupted "
                "tool request. If the interrupted step made duplicate requests "
                "for the same tool with the same arguments, treat this same "
                "result as covering those duplicate requests. Do not call the "
                "same tool again only to obtain the same result."
            ),
        )
    )
    return SystemMessage(role=AgentMessageRole.SYSTEM, content=content)


def _event_id_from_payload_ref(
    payload: Mapping[str, JsonValue], *, field_name: str
) -> str:
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
        _validate_tool_enabled_snapshot(
            tool_snapshot, policy_snapshot, tool_executor
        )
        return
    _validate_no_tool_snapshot(tool_snapshot, policy_snapshot)


def _validate_no_tool_snapshot(
    tool_snapshot: ToolSchemaSnapshot, policy_snapshot: PolicySnapshot
) -> None:
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
        raise HostDurableError(
            "RunInputBuilder tool schemas must come from ToolRuntimeHandle"
        )
    if tool_snapshot.tool_runtime_handle.tool_executor is not tool_executor:
        raise HostDurableError(
            "RunInputBuilder tool executor must come from same ToolRuntimeHandle"
        )


def _find_existing_runner_call_manifest_event(
    transaction: HostTransaction,
    *,
    run_id: str,
    attempt_id: str,
    execution_id: str,
) -> EventLogRow | None:
    """查找同一 attempt/execution 已写入的 runner-call manifest event。

    :param transaction: 当前 Host transaction。
    :param run_id: 当前 Run id。
    :param attempt_id: 当前 Attempt id。
    :param execution_id: 当前 execution id。
    :returns: 已存在的 manifest event；不存在时返回 ``None``。
    :raises HostDurableError: 既有 event hot payload 非法时抛出。
    """

    rows = transaction.fetchall(
        f"""
        SELECT event_id
        FROM {TABLE_EVENT_LOG}
        WHERE run_id = ?
          AND event_type = ?
        ORDER BY event_sequence ASC
        """,
        (run_id, _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED),
    )
    event_log_store = EventLogStore()
    for row in rows:
        event_id = row.get("event_id")
        if not isinstance(event_id, str):
            raise HostDurableError("runner-call manifest event_id is invalid")
        event = event_log_store.read_event_by_id(transaction, event_id)
        if event is None:
            raise HostDurableError("runner-call manifest event row is missing")
        payload = _payload_object(event)
        if (
            payload.get("attempt_id") == attempt_id
            and payload.get("execution_id") == execution_id
        ):
            return event
    return None


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


def _runner_call_manifest_body(
    record_input: RunnerCallManifestRecordInput,
    *,
    runner_call_index: int,
    manifest_id: str,
) -> Mapping[str, JsonValue]:
    """构造 runner-call input assembly manifest body。

    :param record_input: manifest 构造输入。
    :param runner_call_index: Host-owned runner call index。
    :param manifest_id: manifest logical id。
    :returns: manifest canonical JSON object。
    """

    roles = _message_role_values(record_input.messages)
    message_entries = _runner_call_message_entries(record_input)
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
        "runner_input_serializer_schema_version": (
            RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
        ),
        "input_projection_digest": input_projection_digest,
        "message_entries": list(message_entries),
        "source_cursor_refs": list(source_cursor_refs),
        "tool_schema_snapshot_refs": list(_tool_schema_snapshot_refs(record_input)),
        "memory_snapshot_cursor_ref": _memory_snapshot_cursor_ref(
            record_input.memory
        ),
        "compact_artifact_refs": list(_compact_artifact_refs(record_input.compact)),
        "context_fallback_decision_ref": _context_fallback_decision_ref(
            record_input.fallback
        ),
        "projector_metadata": list(projector_metadata),
        "compactor_identity": None,
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
            metadata={
                "descriptor_kind": RUNNER_CALL_INPUT_MANIFEST_DESCRIPTOR_KIND,
                "event_type": _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED,
                "event_id": event_id,
            },
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

    return {
        "session_id": _manifest_text(manifest, "session_id"),
        "host_run_id": _manifest_text(manifest, "host_run_id"),
        "attempt_id": _manifest_optional_text(manifest, "attempt_id"),
        "execution_id": _manifest_optional_text(manifest, "execution_id"),
        "runner_call_index": _manifest_int(manifest, "runner_call_index"),
        "runner_call_kind": _manifest_text(manifest, "runner_call_kind"),
        "runner_call_trigger_reason": _manifest_text(
            manifest, "runner_call_trigger_reason"
        ),
        "iteration_id": _manifest_optional_text(manifest, "iteration_id"),
        "iteration_index": manifest.get("iteration_index"),
        "manifest_payload_ref": manifest_payload_ref,
        "manifest_digest": manifest_digest,
        "manifest_schema_version": _manifest_text(manifest, "schema_version"),
        "validation_status": _RUNNER_CALL_VALIDATION_COMPLETE,
        "message_count": _manifest_int(manifest, "message_count"),
        "role_sequence_digest": _manifest_text(manifest, "role_sequence_digest"),
        "input_projection_digest": _manifest_text(
            manifest, "input_projection_digest"
        ),
        "projector_metadata_summary": list(_projector_metadata_summary(manifest)),
        "diagnostic": None,
    }


def _runner_call_manifest_payload_ref(event_id: str) -> str:
    """派生 runner-call manifest payload descriptor ref。

    :param event_id: manifest canonical event id。
    :returns: payload descriptor ref。
    """

    return f"{_RUNNER_CALL_MANIFEST_PAYLOAD_REF_PREFIX}-{event_id}"


def _runner_call_manifest_sqlite_payload_id(event_id: str) -> str:
    """派生 runner-call manifest SQLite payload id。

    :param event_id: manifest canonical event id。
    :returns: SQLite payload id。
    """

    return f"{_RUNNER_CALL_MANIFEST_SQLITE_PAYLOAD_ID_PREFIX}-{event_id}"


def _runner_call_message_entries(
    record_input: RunnerCallManifestRecordInput,
) -> tuple[Mapping[str, JsonValue], ...]:
    """构造 manifest message entries。

    :param record_input: manifest 构造输入。
    :returns: message entry 元组。
    """

    return tuple(
        _runner_call_message_entry(record_input, index=index, message=message)
        for index, message in enumerate(record_input.messages)
    )


def _runner_call_message_entry(
    record_input: RunnerCallManifestRecordInput,
    *,
    index: int,
    message: AgentMessage,
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
        "source_refs": list(
            _message_source_refs(record_input, index=index, message=message)
        ),
        "projection_artifact_ref": None,
        "projection_artifact_digest": None,
        "projector_metadata_id": _projector_metadata_id_for_message(
            record_input, index=index, message=message
        ),
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
        metadata_id = _projector_metadata_id_for_message(
            record_input, index=index, message=message
        )
        if metadata_id in metadata_by_id:
            continue
        metadata_by_id[metadata_id] = _projector_metadata(
            metadata_id=metadata_id,
            projector_id=_projector_id_for_message(record_input, index, message),
            purpose=_projector_purpose(record_input),
            source_contract_refs=_message_source_refs(
                record_input, index=index, message=message
            ),
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

    return {
        "projector_metadata_id": metadata_id,
        "projector_id": projector_id,
        "projector_schema_version": _PROJECTOR_SCHEMA_VERSION,
        "projector_digest": sha256_digest_json(
            {
                "projector_id": projector_id,
                "projector_schema_version": _PROJECTOR_SCHEMA_VERSION,
                "purpose": purpose,
                "source_contract_refs": list(source_contract_refs),
            }
        ),
        "purpose": purpose,
        "source_contract_refs": list(source_contract_refs),
    }


def _projector_metadata_summary(
    manifest: Mapping[str, JsonValue]
) -> tuple[Mapping[str, JsonValue], ...]:
    """从 manifest body 复制 Tool Trace 可缓存的 projector metadata summary。

    :param manifest: manifest body。
    :returns: projector metadata summary 元组。
    :raises HostDurableError: manifest projector metadata 结构非法时抛出。
    """

    value = manifest.get("projector_metadata")
    if not isinstance(value, list):
        raise HostDurableError("runner-call manifest projector_metadata is invalid")
    summaries: list[Mapping[str, JsonValue]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise HostDurableError("runner-call projector metadata must be object")
        summaries.append(
            {
                "projector_metadata_id": _manifest_text(
                    item, "projector_metadata_id"
                ),
                "projector_id": _manifest_text(item, "projector_id"),
                "projector_schema_version": _manifest_text(
                    item, "projector_schema_version"
                ),
                "projector_digest": _manifest_text(item, "projector_digest"),
                "purpose": _manifest_text(item, "purpose"),
            }
        )
    return tuple(summaries)


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
    record_input: RunnerCallManifestRecordInput,
) -> tuple[str, ...]:
    """返回工具 schema snapshot refs。

    :param record_input: manifest 构造输入。
    :returns: 工具 schema refs；无工具时为空。
    """

    if len(record_input.tool_snapshot.tool_schemas) == 0:
        return ()
    return (
        "tool_schema_snapshot:"
        + sha256_digest_json(
            {
                "tool_schema_count": len(record_input.tool_snapshot.tool_schemas),
                "disable_tools": record_input.tool_snapshot.disable_tools,
            }
        ),
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
    start_reason = start_payload.get(_PAYLOAD_FIELD_START_REASON)
    if start_reason == "recovery" or record_input.fallback is not None:
        return (
            _RUNNER_CALL_KIND_POST_COMPACTION_DISPATCH,
            _RUNNER_CALL_TRIGGER_CONTEXT_COMPACTION_COMPLETED,
        )
    if start_reason == "resume":
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


def _manifest_optional_text(
    payload: Mapping[str, JsonValue], field_name: str
) -> str | None:
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
    "create_no_tool_run_input_builder",
    "create_tool_enabled_run_input_builder",
]
