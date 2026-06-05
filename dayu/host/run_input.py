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
from dayu.host.api import AttemptDispatchSnapshot
from dayu.host.api import AttemptStatus, RunStatus
from dayu.host.context_events import CONTEXT_COMPACTED
from dayu.host.context_fallback import (
    ActiveRecentWindowFallback,
    EventLogContextFallbackProvider,
)
from dayu.host.compact_material import (
    RunInputMaterialBlock,
    run_input_material_block,
)
from dayu.host.compaction_evidence import (
    SelectedEvidenceBlockRef,
    collect_selected_compaction_request_evidence_inputs,
)
from dayu.host.compaction import (
    CompactMaterialBlockKind,
    CompactMaterialSection,
)
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
    read_event_by_id,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.memory import read_latest_memory_snapshot_at_or_before
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
from dayu.host.payload_resolution import (
    event_payload_object,
    sqlite_payload_object,
)
from dayu.host.terminal_summary_payload import (
    PayloadSummaryTextPolicy,
    assistant_summary_from_payload,
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
_PAYLOAD_FIELD_CONTENT = "content"
_PAYLOAD_FIELD_TERMINAL_SUMMARY_REF = "terminal_summary_ref"
_PAYLOAD_FIELD_TERMINAL_SUMMARY_DIGEST = "terminal_summary_digest"
_PAYLOAD_FIELD_START_REASON = "start_reason"
_PAYLOAD_FIELD_TOOL_RESULT_EVENT_REF = "tool_result_event_ref"
_PAYLOAD_FIELD_EVENT_ID = "event_id"
_PAYLOAD_FIELD_COMPACT_ARTIFACT_REF = "compact_artifact_ref"
_PAYLOAD_FIELD_COMPACT_ARTIFACT_DIGEST = "compact_artifact_digest"
_PAYLOAD_FIELD_ACCEPTED_CANDIDATE = "accepted_candidate"
_PAYLOAD_FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS = "accepted_evidence_mapping_refs"
_PAYLOAD_FIELD_SCHEMA_VERSION = "schema_version"
_PAYLOAD_FIELD_SESSION_SUMMARY = "session_summary"
_PAYLOAD_FIELD_SUMMARY_TEXT = "summary_text"
_PAYLOAD_FIELD_EVIDENCE_BACKED_FACTS = "evidence_backed_facts"
_PAYLOAD_FIELD_ANSWER_ANCHORS = "answer_anchors"
_PAYLOAD_FIELD_FORWARD_INTENTS = "forward_intents"
_PAYLOAD_FIELD_REFERENCE_CONTINUITY_ITEMS = "reference_continuity_items"
_NO_TOOL_CANCEL_MESSAGE = "tools are disabled for this attempt"
_COMPACT_SUMMARY_MAX_CHARS = 1200
_MEMORY_SESSION_SUMMARY_HEADER = "Session Summary Memory:"
_MEMORY_EVIDENCE_FACT_HEADER = "Evidence / Fact Memory:"
_MEMORY_ANSWER_ANCHOR_HEADER = "Answer Anchor Memory:"
_MEMORY_FORWARD_INTENT_HEADER = "Forward Intent Memory:"
_MEMORY_REFERENCE_CONTINUITY_HEADER = "Trace Memory reference continuity:"
_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT = 8
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
_MEMORY_EVENT_TYPES = frozenset(
    (
        _EVENT_TYPE_USER_INPUT_ACCEPTED,
        _EVENT_TYPE_RUN_SUCCEEDED,
        _EVENT_TYPE_TOOL_RESULT_ACCEPTED,
        CONTEXT_COMPACTED,
    )
)


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
    """

    messages: tuple[AgentMessage, ...]
    memory_snapshot_cursor: str | None
    policy_digest: str | None
    diagnostics: tuple[MemoryDiagnostic, ...]
    represented_evidence_refs: tuple[str, ...] = ()


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

        rows = self._event_log_store.read_events_after(
            transaction,
            snapshot.cursor.checkpoint_event_sequence,
            limit=lag_events,
        )
        if len(rows) != lag_events:
            self._raise_repair_required(
                session_id=snapshot.session_id,
                reason=MemoryRepairReason.SNAPSHOT_DAMAGED,
                required_event_sequence=required_event_sequence,
                observed_cursor=snapshot.cursor,
            )
        required_row = rows[-1]
        if (
            required_row.event_sequence != required_event_sequence
            or required_row.session_id != snapshot.session_id
        ):
            self._raise_repair_required(
                session_id=snapshot.session_id,
                reason=MemoryRepairReason.SNAPSHOT_DAMAGED,
                required_event_sequence=required_event_sequence,
                observed_cursor=snapshot.cursor,
            )
        repaired = snapshot
        for row in rows:
            if _is_memory_projection_row(row, session_id=snapshot.session_id):
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
                checkpoint_event_sequence=required_row.event_sequence,
                checkpoint_event_id=required_row.event_id,
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


class DurableAcceptedToolEvidenceMaterialProvider:
    """基于 EventLog 读取当前 Attempt 前 accepted tool evidence material。

    Provider 只读取当前 Session、当前 Attempt start cursor 之前的最近
    ``TOOL_RESULT_ACCEPTED`` 事件，并用固定上限约束读取规模。raw evidence
    payload 解析复用 ``compaction_evidence`` 的 accepted envelope 逻辑，避免
    在 RunInputBuilder 内重复解释工具结果结构。

    :param transaction_runner: Host durable transaction runner。
    :param max_evidence_blocks: 单次最多暴露给 compactor 的 accepted evidence 数。
    """

    def __init__(
        self,
        transaction_runner: HostTransactionRunner,
        *,
        max_evidence_blocks: int = _ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT,
    ) -> None:
        """初始化 provider。

        :param transaction_runner: Host durable transaction runner。
        :param max_evidence_blocks: accepted evidence material 上限。
        :returns: ``None``。
        :raises ValueError: 上限非正数时抛出。
        """

        if max_evidence_blocks <= 0:
            raise ValueError("max_evidence_blocks must be positive")
        self._transaction_runner = transaction_runner
        self._event_log_store = EventLogStore()
        self._max_evidence_blocks = max_evidence_blocks

    def load_accepted_tool_evidence_materials(
        self,
        snapshot: AttemptDispatchSnapshot,
        current_facts: CurrentRunFacts,
        memory: MemorySnapshotView,
        compact: CompactArtifactView,
    ) -> tuple[RunInputMaterialBlock, ...]:
        """读取 bounded accepted tool evidence material。

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
                snapshot=snapshot,
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
        snapshot: AttemptDispatchSnapshot,
        current_facts: CurrentRunFacts,
        represented_evidence_refs: tuple[str, ...],
    ) -> tuple[RunInputMaterialBlock, ...]:
        """在 read transaction 内读取 accepted evidence material。

        :param transaction: Host transaction。
        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :param represented_evidence_refs: 已由 memory / compact 表示的 evidence refs。
        :returns: evidence material blocks。
        """

        return build_accepted_tool_evidence_material_blocks(
            transaction,
            self._event_log_store,
            session_id=snapshot.session_id,
            before_event_sequence=current_facts.attempt.started_event_sequence,
            represented_evidence_refs=represented_evidence_refs,
            max_evidence_blocks=self._max_evidence_blocks,
        )


def build_accepted_tool_evidence_material_blocks(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    session_id: str,
    before_event_sequence: int,
    represented_evidence_refs: tuple[str, ...] = (),
    max_evidence_blocks: int = _ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT,
) -> tuple[RunInputMaterialBlock, ...]:
    """从 bounded EventLog window 构造 accepted tool evidence material。

    本 helper 只读取当前 Session 中 ``before_event_sequence`` 之前最近的
    ``TOOL_RESULT_ACCEPTED``，并复用 compaction evidence reader 解析 raw
    accepted evidence；canonical refs 只写入 material block 内部 provenance
    字段，不进入 LLM-facing material JSON。

    :param transaction: Host transaction。
    :param event_log_store: EventLog store。
    :param session_id: 当前 Session id。
    :param before_event_sequence: 当前输入 / Attempt cursor 的排他上界。
    :param represented_evidence_refs: 已由 stable facts 或 compact artifact 表示
        的 accepted evidence refs。
    :param max_evidence_blocks: 单次最多读取的 accepted evidence 数。
    :returns: evidence material blocks。
    :raises HostDurableError: EventLog 或 evidence payload 损坏时抛出。
    """

    rows = _recent_accepted_tool_result_rows(
        transaction,
        event_log_store,
        session_id=session_id,
        before_event_sequence=before_event_sequence,
        limit=max_evidence_blocks,
    )
    if len(rows) == 0:
        return ()
    selected_refs = tuple(
        SelectedEvidenceBlockRef(
            block_id=f"accepted-tool-evidence:{row.event_id}",
            tool_result_event_ref=row.event_id,
        )
        for row in rows
    )
    inputs = collect_selected_compaction_request_evidence_inputs(
        transaction,
        event_log_store,
        session_id=session_id,
        selected_evidence_block_refs=selected_refs,
    )
    sequence_by_event_id = {row.event_id: row.event_sequence for row in rows}
    represented = frozenset(represented_evidence_refs)
    blocks: list[RunInputMaterialBlock] = []
    for index, material in enumerate(inputs.evidence_materials):
        if material.accepted_evidence_id in represented:
            continue
        blocks.append(
            run_input_material_block(
                block_id=(
                    "accepted-tool-evidence:"
                    f"{material.tool_result_event_ref}:"
                    f"{material.accepted_evidence_id}"
                ),
                section=CompactMaterialSection.EVIDENCE_MATERIAL,
                kind=CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE,
                text=material.raw_result_text,
                canonical_source_refs=(material.canonical_source_ref,),
                event_sequence=sequence_by_event_id[material.tool_result_event_ref],
                event_sub_index=index,
                accepted_evidence_id=material.accepted_evidence_id,
                tool_result_event_ref=material.tool_result_event_ref,
                tool_call_event_ref=material.tool_call_event_ref,
                payload_refs=material.payload_refs,
                artifact_refs=material.artifact_refs,
                source_locator_refs=material.source_locator_refs,
                readable_tool_name=material.readable_tool_name,
                readable_query_text=material.readable_query_text,
                readable_source_text=material.readable_source_text,
            )
        )
    return tuple(blocks)


class DurableCompactArtifactProvider:
    """基于 EventLog 读取 accepted compact artifact 的 provider。

    :param transaction_runner: Host durable transaction runner。
    :param max_summary_chars: compact candidate 摘要渲染字符上限。
    """

    def __init__(
        self,
        transaction_runner: HostTransactionRunner,
        *,
        max_summary_chars: int = _COMPACT_SUMMARY_MAX_CHARS,
    ) -> None:
        """初始化 provider。

        :param transaction_runner: Host durable transaction runner。
        :param max_summary_chars: compact candidate 摘要渲染字符上限。
        :returns: ``None``。
        :raises ValueError: 上限非正数时抛出。
        """

        if max_summary_chars <= 0:
            raise ValueError("max_summary_chars must be positive")
        self._transaction_runner = transaction_runner
        self._max_summary_chars = max_summary_chars

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
        message = SystemMessage(
            role=AgentMessageRole.SYSTEM,
            content=_compact_artifact_message_content(
                compacted_event=row,
                payload=payload,
                max_summary_chars=self._max_summary_chars,
            ),
        )
        return CompactArtifactView(
            messages=(message,),
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
        execution_target = _execution_target_from_accepted_event(
            current_facts.run_accepted_event,
            fallback=current_facts.run.execution_target,
        )
        content = "\n".join(
            (
                "Host execution context:",
                f"operation_kind={current_facts.operation_kind}",
                f"execution_target={execution_target}",
                f"queue_policy={current_facts.run.queue_policy}",
                f"policy_snapshot_ref={policy_snapshot.policy_snapshot_ref}",
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
            bounded_context_messages = (
                *memory.messages,
                *compact.messages,
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
            bounded_context_messages = _fallback_context_messages(
                fallback=fallback,
                material_blocks=build_run_input_material_blocks(
                    current_facts=current_facts,
                    memory=memory,
                    compact=compact,
                    continuity=continuity,
                    accepted_tool_evidence=evidence,
                ),
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
        messages = (
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
    memory_snapshot_provider: MemorySnapshotProvider | None = None,
    compact_artifact_provider: CompactArtifactProvider | None = None,
    context_fallback_provider: ContextFallbackProvider | None = None,
    tool_execution_mode: ToolExecutionMode = ToolExecutionMode.NO_TOOL_DISABLED,
) -> RunInputBuilder:
    """创建 Phase 5 默认 no-tool RunInputBuilder。

    :param transaction_runner: Host durable transaction runner。
    :param policy_snapshot: 显式 policy snapshot。
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
    )


def create_tool_enabled_run_input_builder(
    *,
    transaction_runner: HostTransactionRunner,
    policy_snapshot: PolicySnapshot,
    tool_runtime_handle: ToolRuntimeHandle,
    memory_snapshot_provider: MemorySnapshotProvider | None = None,
    compact_artifact_provider: CompactArtifactProvider | None = None,
    context_fallback_provider: ContextFallbackProvider | None = None,
) -> RunInputBuilder:
    """创建 tool-enabled RunInputBuilder。

    :param transaction_runner: Host durable transaction runner。
    :param policy_snapshot: 显式 policy snapshot，必须允许工具调用。
    :param tool_runtime_handle: ToolRuntime handle。
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
    for fact in facts:
        lines.append(
            "fact="
            f"claim_text={fact.claim_text}; "
            f"evidence_refs={','.join(fact.evidence_refs)}; "
            f"evidence_kind={fact.evidence_kind.value}; "
            f"extraction_operation_ref={fact.extraction_operation_ref}; "
            f"event_id={fact.provenance.event_id}; "
            f"event_sequence={fact.provenance.event_sequence}"
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
            messages.append(SystemMessage(role=AgentMessageRole.SYSTEM, content=item.text))
    return tuple(messages)


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
        )
    )
    return tuple(blocks)


def _fallback_context_messages(
    *,
    fallback: ActiveRecentWindowFallback,
    material_blocks: tuple[RunInputMaterialBlock, ...],
) -> tuple[AgentMessage, ...]:
    """按 fallback selected block ids 渲染 bounded context messages。

    :param fallback: active fallback view。
    :param material_blocks: ordinary material blocks。
    :returns: fallback bounded context messages，不包含当前 input anchor。
    :raises HostDurableError: fallback view 与 ordinary material 不一致时抛出。
    """

    selected_ids = frozenset(fallback.selected_block_ids)
    if len(selected_ids) != len(fallback.selected_block_ids):
        raise HostDurableError("fallback selected block ids must be unique")
    selected_blocks = tuple(
        block for block in material_blocks if block.block_id in selected_ids
    )
    if len(selected_blocks) != len(selected_ids):
        raise HostDurableError("fallback selected block id is missing from material view")
    current_blocks = tuple(
        block
        for block in selected_blocks
        if block.section is CompactMaterialSection.CURRENT_INPUT_ANCHOR
        and fallback.current_input_ref in block.canonical_source_refs
    )
    if len(current_blocks) != 1:
        raise HostDurableError("fallback view requires exactly one current input anchor")
    messages: list[AgentMessage] = []
    for block in selected_blocks:
        if block.block_id == current_blocks[0].block_id:
            continue
        messages.append(_fallback_message_from_material_block(block))
    return tuple(messages)


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
    return SystemMessage(role=AgentMessageRole.SYSTEM, content=block.text)


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


def _is_memory_projection_row(row: EventLogRow, *, session_id: str) -> bool:
    """判断 EventLog row 是否应进入 memory delta projection。

    :param row: EventLog row。
    :param session_id: 当前 Session id。
    :returns: 命中 memory projection 返回 ``True``。
    """

    return (
        row.session_id == session_id
        and row.event_class == EventClass.CANONICAL_FACT
        and row.event_type in _MEMORY_EVENT_TYPES
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

    payload = _payload_with_terminal_summary(transaction, row)
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


def _payload_with_terminal_summary(
    transaction: HostTransaction, row: EventLogRow
) -> Mapping[str, JsonValue]:
    """必要时把 terminal summary 摘要合并进 RUN_SUCCEEDED payload。

    :param transaction: Host transaction。
    :param row: EventLog row。
    :returns: memory projection 消费的 payload。
    :raises HostDurableError: terminal summary descriptor 损坏时抛出。
    """

    payload = _payload_object(row)
    if row.event_type != _EVENT_TYPE_RUN_SUCCEEDED:
        return payload
    if (
        assistant_summary_from_payload(
            payload,
            text_policy=PayloadSummaryTextPolicy.STRICT_NON_EMPTY,
        )
        is not None
    ):
        return payload
    terminal_summary_ref = _optional_payload_text(
        payload, field_name=_PAYLOAD_FIELD_TERMINAL_SUMMARY_REF
    )
    terminal_summary_digest = _optional_payload_text(
        payload, field_name=_PAYLOAD_FIELD_TERMINAL_SUMMARY_DIGEST
    )
    if terminal_summary_ref is None or terminal_summary_digest is None:
        return payload
    terminal_summary = sqlite_payload_object(
        transaction,
        payload_ref=terminal_summary_ref,
        payload_digest=terminal_summary_digest,
        payload_label="terminal summary",
    )
    summary = assistant_summary_from_payload(
        terminal_summary,
        text_policy=PayloadSummaryTextPolicy.STRICT_NON_EMPTY,
    )
    if summary is None:
        return payload
    merged: dict[str, JsonValue] = dict(payload)
    merged[_PAYLOAD_FIELD_CONTENT] = summary
    return merged


def _latest_compacted_event_before_attempt(
    transaction: HostTransaction, current_facts: CurrentRunFacts
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


def _recent_accepted_tool_result_rows(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    session_id: str,
    before_event_sequence: int,
    limit: int,
) -> tuple[EventLogRow, ...]:
    """读取当前 Attempt 前最近的 accepted tool result rows。

    查询先按倒序取固定上限，再恢复为 event_sequence 升序，保证读取有界且
    selection / prompt label 分配稳定。

    :param transaction: Host transaction。
    :param event_log_store: EventLog store。
    :param session_id: 当前 Session id。
    :param before_event_sequence: 当前 Attempt started event sequence。
    :param limit: 最大读取 row 数。
    :returns: 稳定升序的 EventLog rows。
    :raises HostDurableError: 参数非法或 row 消失时抛出。
    """

    if before_event_sequence <= 0:
        raise HostDurableError("before_event_sequence must be positive")
    if limit <= 0:
        raise HostDurableError("accepted tool evidence limit must be positive")
    rows = transaction.fetchall(
        f"""
        SELECT event_id
        FROM {TABLE_EVENT_LOG}
        WHERE session_id = ?
          AND event_type = ?
          AND event_class = ?
          AND event_sequence < ?
        ORDER BY event_sequence DESC
        LIMIT ?
        """,
        (
            session_id,
            _EVENT_TYPE_TOOL_RESULT_ACCEPTED,
            EventClass.CANONICAL_FACT.value,
            before_event_sequence,
            limit,
        ),
    )
    result: list[EventLogRow] = []
    for row in reversed(rows):
        event_id = _required_host_row_text(row, field_name="event_id")
        event = event_log_store.read_event_by_id(transaction, event_id)
        if event is None:
            raise HostDurableError("accepted tool evidence event disappeared")
        result.append(
            _require_event(
                event,
                expected_type=_EVENT_TYPE_TOOL_RESULT_ACCEPTED,
            )
        )
    return tuple(result)


def _compact_artifact_message_content(
    *,
    compacted_event: EventLogRow,
    payload: Mapping[str, JsonValue],
    max_summary_chars: int,
) -> str:
    """构造 bounded compact artifact SystemMessage 内容。

    :param compacted_event: ``CONTEXT_COMPACTED`` event row。
    :param payload: compacted payload。
    :param max_summary_chars: summary 字符上限。
    :returns: message 内容。
    """

    artifact_ref = _required_text_field(payload, _PAYLOAD_FIELD_COMPACT_ARTIFACT_REF)
    artifact_digest = _required_text_field(
        payload, _PAYLOAD_FIELD_COMPACT_ARTIFACT_DIGEST
    )
    accepted_evidence_mapping_refs = _accepted_evidence_mapping_refs(payload)
    candidate_summary = _vnext_compact_candidate_summary(
        payload, max_summary_chars=max_summary_chars
    )
    lines = [
        "Accepted vNext compact artifact is available for this run.",
        f"compact_artifact_ref={artifact_ref}",
        f"compact_artifact_digest={artifact_digest}",
        f"compacted_event_id={compacted_event.event_id}",
        f"compacted_event_sequence={compacted_event.event_sequence}",
        (
            "accepted_evidence_mapping_refs="
            f"{','.join(accepted_evidence_mapping_refs)}"
        ),
        f"accepted_candidate={candidate_summary}",
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


def _vnext_compact_candidate_summary(
    payload: Mapping[str, JsonValue], *, max_summary_chars: int
) -> str:
    """从 vNext accepted candidate 渲染 bounded compact 摘要。

    :param payload: ``CONTEXT_COMPACTED`` vNext payload。
    :param max_summary_chars: 最大字符数。
    :returns: accepted candidate 摘要。
    :raises HostDurableError: accepted candidate 结构损坏时抛出。
    """

    candidate = _required_mapping_field(payload, _PAYLOAD_FIELD_ACCEPTED_CANDIDATE)
    schema_version = _required_text_field(candidate, _PAYLOAD_FIELD_SCHEMA_VERSION)
    facts = _required_mapping_list_field(
        candidate, _PAYLOAD_FIELD_EVIDENCE_BACKED_FACTS
    )
    anchors = _required_mapping_list_field(candidate, _PAYLOAD_FIELD_ANSWER_ANCHORS)
    intents = _required_mapping_list_field(candidate, _PAYLOAD_FIELD_FORWARD_INTENTS)
    references = _required_mapping_list_field(
        candidate, _PAYLOAD_FIELD_REFERENCE_CONTINUITY_ITEMS
    )
    parts = [f"schema_version={schema_version}"]
    session_summary = _optional_session_summary_text(candidate)
    if session_summary is not None:
        parts.append(f"session_summary={session_summary}")
    parts.extend(
        (
            f"evidence_backed_facts={len(facts)}",
            f"answer_anchors={len(anchors)}",
            f"forward_intents={len(intents)}",
            f"reference_continuity_items={len(references)}",
        )
    )
    text = " | ".join(parts)
    if len(text) <= max_summary_chars:
        return text
    return text[:max_summary_chars]


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


def _continuity_message_from_event(event: EventLogRow) -> AgentMessage | None:
    """把 continuity canonical event 投影为 Engine message。

    :param event: EventLog row。
    :returns: AgentMessage；无需进入 messages 时返回 ``None``。
    :raises HostDurableError: payload 字段无法投影时抛出。
    """

    if event.event_type == _EVENT_TYPE_USER_INPUT_ACCEPTED:
        return UserMessage(
            role=AgentMessageRole.USER,
            content=_required_payload_text(
                _payload_object(event),
                field_name=_PAYLOAD_FIELD_DISPLAY_TEXT,
            ),
        )
    if event.event_type == _EVENT_TYPE_RUN_SUCCEEDED:
        summary = assistant_summary_from_payload(
            _payload_object(event),
            text_policy=PayloadSummaryTextPolicy.STRICT_NON_EMPTY,
        )
        if summary is None:
            return None
        return AssistantMessage(
            role=AgentMessageRole.ASSISTANT,
            content=summary,
            reasoning_content=None,
            tool_calls=(),
        )
    return None


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
    content = "\n".join(
        (
            "Accepted wait result fact:",
            f"wait_id={_required_payload_text(payload, field_name='wait_id')}",
            "tool_call_id="
            f"{_required_payload_text(payload, field_name='tool_call_id')}",
            f"tool_name={_required_payload_text(payload, field_name='tool_name')}",
            "resolution_kind="
            f"{_required_payload_text(payload, field_name='resolution_kind')}",
            "tool_fact_kind="
            f"{_required_payload_text(payload, field_name='tool_fact_kind')}",
            "result="
            f"{json.dumps(payload.get('result'), sort_keys=True, separators=(',', ':'))}",
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


def _successful_run_continuity_messages(
    *, events: tuple[EventLogRow, ...], current_run_id: str
) -> tuple[AgentMessage, ...]:
    """只把已成功收口的历史 Run 投影为完整 user/assistant 对。

    :param events: 按 EventLog sequence 排序的 continuity events。
    :param current_run_id: 当前 Run id；该 Run 的事件不进入历史 continuity。
    :returns: 可进入 Engine request 的历史消息。
    :raises HostDurableError: payload 字段无法投影时抛出。
    """

    ordered_run_ids: list[str] = []
    events_by_run_id: dict[str, list[EventLogRow]] = {}
    for event in events:
        run_id = event.run_id
        if run_id is None or run_id == current_run_id:
            continue
        if run_id not in events_by_run_id:
            events_by_run_id[run_id] = []
            ordered_run_ids.append(run_id)
        events_by_run_id[run_id].append(event)

    messages: list[AgentMessage] = []
    for run_id in ordered_run_ids:
        projected = _successful_run_message_pair(events_by_run_id[run_id])
        if projected is not None:
            messages.extend(projected)
    return tuple(messages)


def _successful_run_message_pair(
    events: list[EventLogRow],
) -> tuple[UserMessage, AssistantMessage] | None:
    """从单个成功历史 Run 中提取 user/assistant 对。

    :param events: 同一个 Run 的 continuity events。
    :returns: 两条完整消息；缺少任一端时返回 ``None``。
    :raises HostDurableError: payload 字段无法投影时抛出。
    """

    user_message: UserMessage | None = None
    assistant_message: AssistantMessage | None = None
    for event in events:
        message = _continuity_message_from_event(event)
        if isinstance(message, UserMessage):
            user_message = message
        elif isinstance(message, AssistantMessage):
            assistant_message = message
    if user_message is None or assistant_message is None:
        return None
    return (user_message, assistant_message)


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
    """返回 scene message 中的工具状态行。

    :param tool_execution_mode: 显式工具执行模式。
    :returns: 工具状态行。
    """

    if tool_execution_mode == ToolExecutionMode.TOOL_ENABLED:
        return "tools=enabled"
    return "tools=disabled"


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
    "build_accepted_tool_evidence_material_blocks",
    "build_run_input_material_blocks",
    "create_no_tool_run_input_builder",
    "create_tool_enabled_run_input_builder",
]
