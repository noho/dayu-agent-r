"""Host RunInputBuilder 与 no-tool provider 边界。

本模块实现 Phase 5 的内部 RunInputBuilder。它只从 durable EventLog /
Run / Attempt / dispatch record 与显式注入的 policy snapshot 构造 Engine
``AgentRunRequest``，不读取 UI / Service 临时状态，不实现 scheduler、
LocalProxy、ToolRuntime 执行、Memory projection 或 Context Governance。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

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
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.messages import (
    AgentMessage,
    AgentMessageRole,
    AssistantMessage,
    SystemMessage,
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
from dayu.host.durable.event_log import (
    EventClass,
    EventLogRow,
    EventLogStore,
    read_event_by_id,
    read_run_input_continuity_events,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.state import (
    AttemptRow,
    DispatchRecordRow,
    DispatchRecordStatus,
    RunRow,
    read_attempt_by_id,
    read_dispatch_record_by_attempt_id,
    read_run_by_id,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.tool_runtime import ToolRuntimeHandle

_EVENT_TYPE_USER_INPUT_ACCEPTED = "USER_INPUT_ACCEPTED"
_EVENT_TYPE_RUN_ACCEPTED = "RUN_ACCEPTED"
_EVENT_TYPE_RUN_STARTED = "RUN_STARTED"
_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"
_PAYLOAD_FIELD_DISPLAY_TEXT = "display_text"
_PAYLOAD_FIELD_OPERATION_KIND = "operation_kind"
_PAYLOAD_FIELD_EXECUTION_TARGET = "execution_target"
_PAYLOAD_FIELD_FINAL_ANSWER = "final_answer"
_PAYLOAD_FIELD_CONTENT = "content"
_PAYLOAD_FIELD_SUMMARY_TEXT = "summary_text"
_NO_TOOL_CANCEL_MESSAGE = "tools are disabled for this attempt"


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
    :param operation_kind: 当前 operation kind。
    """

    run: RunRow
    attempt: AttemptRow
    dispatch_record: DispatchRecordRow
    user_input_event: EventLogRow
    run_accepted_event: EventLogRow
    run_started_event: EventLogRow
    user_prompt: str
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

    :param messages: memory stable layer messages；Phase 5 noop 为空。
    :param memory_snapshot_cursor: memory snapshot cursor；Phase 5 noop 为 ``None``。
    """

    messages: tuple[AgentMessage, ...]
    memory_snapshot_cursor: str | None


@dataclass(frozen=True, slots=True)
class CompactArtifactView:
    """Compact artifact provider 输出。

    :param messages: compact artifact messages；Phase 5 noop 为空。
    :param compact_artifact_ref: compact artifact ref；Phase 5 noop 为 ``None``。
    :param compact_artifact_digest: compact artifact digest；Phase 5 noop 为 ``None``。
    """

    messages: tuple[AgentMessage, ...]
    compact_artifact_ref: str | None
    compact_artifact_digest: str | None


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
        payload = _payload_object(user_input_event)
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
            operation_kind=_required_payload_text(
                payload,
                field_name=_PAYLOAD_FIELD_OPERATION_KIND,
            ),
        )


class DurableSessionContinuityProvider:
    """基于 EventLog 的 Session continuity provider。"""

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
        """在 read transaction 内读取 continuity events。

        :param transaction: Host durable transaction。
        :param snapshot: Attempt dispatch snapshot。
        :param current_facts: 当前 Run facts。
        :returns: Session continuity view。
        """

        events = read_run_input_continuity_events(
            transaction,
            session_id=snapshot.session_id,
            before_event_sequence=current_facts.attempt.started_event_sequence,
        )
        return SessionContinuityView(
            messages=_successful_run_continuity_messages(
                events=events,
                current_run_id=snapshot.run_id,
            )
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
        return MemorySnapshotView(messages=(), memory_snapshot_cursor=None)


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
        tool_schema_snapshot_provider: ToolSchemaSnapshotProvider,
        tool_executor_provider: ToolExecutorProvider,
        scene_parameter_provider: SceneParameterProvider,
        policy_snapshot_provider: PolicySnapshotProvider,
        tool_execution_mode: ToolExecutionMode,
    ) -> None:
        """初始化 RunInputBuilder。

        :param current_run_provider: 当前 Run durable fact provider。
        :param session_continuity_provider: Session continuity provider。
        :param memory_snapshot_provider: Memory snapshot provider。
        :param compact_artifact_provider: Compact artifact provider。
        :param tool_schema_snapshot_provider: Tool schema snapshot provider。
        :param tool_executor_provider: ToolExecutor provider。
        :param scene_parameter_provider: Scene parameter provider。
        :param policy_snapshot_provider: Policy snapshot provider。
        :param tool_execution_mode: 显式工具执行模式。
        :returns: ``None``。
        """

        self._current_run_provider = current_run_provider
        self._session_continuity_provider = session_continuity_provider
        self._memory_snapshot_provider = memory_snapshot_provider
        self._compact_artifact_provider = compact_artifact_provider
        self._tool_schema_snapshot_provider = tool_schema_snapshot_provider
        self._tool_executor_provider = tool_executor_provider
        self._scene_parameter_provider = scene_parameter_provider
        self._policy_snapshot_provider = policy_snapshot_provider
        self._tool_execution_mode = tool_execution_mode

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
            *self._scene_parameter_provider.build_scene_messages(
                attempt_snapshot,
                current_facts,
                policy_snapshot,
                self._tool_execution_mode,
            ),
            *memory.messages,
            *compact.messages,
            *continuity.messages,
            UserMessage(
                role=AgentMessageRole.USER,
                content=current_facts.user_prompt,
            ),
        )
        return AgentRunRequest(
            run_id=attempt_snapshot.run_id,
            session_id=attempt_snapshot.session_id,
            messages=messages,
            disable_tools=tool_snapshot.disable_tools,
            runner_spec=policy_snapshot.runner_spec,
            runner_options=policy_snapshot.runner_options,
            agent_policy=policy_snapshot.agent_policy,
            tool_schemas=tool_snapshot.tool_schemas,
            tool_executor=tool_executor,
            cancellation_token=attempt_snapshot.cancellation_token,
        )


def create_no_tool_run_input_builder(
    *,
    transaction_runner: HostTransactionRunner,
    policy_snapshot: PolicySnapshot,
    tool_execution_mode: ToolExecutionMode = ToolExecutionMode.NO_TOOL_DISABLED,
) -> RunInputBuilder:
    """创建 Phase 5 默认 no-tool RunInputBuilder。

    :param transaction_runner: Host durable transaction runner。
    :param policy_snapshot: 显式 policy snapshot。
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
        memory_snapshot_provider=NoopMemorySnapshotProvider(),
        compact_artifact_provider=NoopCompactArtifactProvider(),
        tool_schema_snapshot_provider=NoopToolSchemaSnapshotProvider(),
        tool_executor_provider=NoToolExecutorProvider(),
        scene_parameter_provider=DefaultSceneParameterProvider(),
        policy_snapshot_provider=StaticPolicySnapshotProvider(policy_snapshot),
        tool_execution_mode=tool_execution_mode,
    )


def create_tool_enabled_run_input_builder(
    *,
    transaction_runner: HostTransactionRunner,
    policy_snapshot: PolicySnapshot,
    tool_runtime_handle: ToolRuntimeHandle,
) -> RunInputBuilder:
    """创建 tool-enabled RunInputBuilder。

    :param transaction_runner: Host durable transaction runner。
    :param policy_snapshot: 显式 policy snapshot，必须允许工具调用。
    :param tool_runtime_handle: ToolRuntime handle。
    :returns: RunInputBuilder。
    """

    handle_provider = StaticToolRuntimeHandleProvider(tool_runtime_handle)
    return RunInputBuilder(
        current_run_provider=DurableCurrentRunFactProvider(transaction_runner),
        session_continuity_provider=DurableSessionContinuityProvider(
            transaction_runner
        ),
        memory_snapshot_provider=NoopMemorySnapshotProvider(),
        compact_artifact_provider=NoopCompactArtifactProvider(),
        tool_schema_snapshot_provider=ToolRuntimeSchemaSnapshotProvider(
            handle_provider
        ),
        tool_executor_provider=ToolRuntimeExecutorProvider(handle_provider),
        scene_parameter_provider=DefaultSceneParameterProvider(),
        policy_snapshot_provider=StaticPolicySnapshotProvider(policy_snapshot),
        tool_execution_mode=ToolExecutionMode.TOOL_ENABLED,
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
        summary = _assistant_summary_from_payload(_payload_object(event))
        if summary is None:
            return None
        return AssistantMessage(
            role=AgentMessageRole.ASSISTANT,
            content=summary,
            reasoning_content=None,
            tool_calls=(),
        )
    return None


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


def _assistant_summary_from_payload(
    payload: Mapping[str, JsonValue]
) -> str | None:
    """从 RUN_SUCCEEDED payload 中读取可投影的 assistant 摘要。

    :param payload: RUN_SUCCEEDED payload 映射。
    :returns: assistant 摘要；缺失时返回 ``None``。
    :raises HostDurableError: 字段存在但类型非法时抛出。
    """

    for field_name in (
        _PAYLOAD_FIELD_FINAL_ANSWER,
        _PAYLOAD_FIELD_CONTENT,
        _PAYLOAD_FIELD_SUMMARY_TEXT,
    ):
        value = _optional_payload_text(payload, field_name=field_name)
        if value is not None:
            return value
    return None


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
    "CurrentRunFactProvider",
    "CurrentRunFacts",
    "DefaultSceneParameterProvider",
    "DurableCurrentRunFactProvider",
    "DurableSessionContinuityProvider",
    "MemorySnapshotProvider",
    "MemorySnapshotView",
    "NoToolExecutor",
    "NoToolExecutorProvider",
    "NoopCompactArtifactProvider",
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
    "create_no_tool_run_input_builder",
    "create_tool_enabled_run_input_builder",
]
