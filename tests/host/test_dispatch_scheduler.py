"""Host Phase 5 dispatch scheduler 测试。"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar, cast

import pytest

import dayu.host.admission as host_admission
import dayu.host.dispatch as host_dispatch
import dayu.host.engine_ingest as host_engine_ingest
from tests.host.transient_delta_support import NOOP_TRANSIENT_DELTA_PUBLISHER
from tests.host.fake_session_access import ExplicitFakeSessionAccess
from dayu.contracts.cancellation import CancellationToken
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.error_codes import adapter_error_code
from dayu.engine.contracts.engine_events import (
    ContextCompactionRequestedData,
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    RunFailedData,
    runner_role_sequence_digest,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.messages import AgentMessage, AgentMessageRole, SystemMessage, UserMessage
from dayu.engine.contracts.runner_identity import (
    ProviderRequestIdAvailability,
    SuccessfulRunnerResponseIdentity,
    build_runner_request_identity,
)
from dayu.engine.contracts.runner_spec import ClientCorrelationPolicy, RunnerCallOptions, RunnerSpec
from dayu.host.queue_policy import RunQueuePolicy
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_execution import AsyncDirectToolExecutionCapability
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolExecutionOutcome
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.host.admission import (
    AdmissionWakeupPort,
    EffectiveBusinessToolSelector,
    EffectiveToolFacts,
    PendingDispatchRecord,
    effective_tool_facts_json,
    parse_effective_tool_facts,
    validate_effective_tool_facts_runtime,
)
from dayu.host._execution_health import HostExecutionHealthState
from dayu.host._execution_config_projection import (
    effective_execution_config_json,
    effective_execution_snapshot_from_json,
)
from dayu.host.api import (
    AttemptDispatchSnapshot,
    AttemptStatus,
    CancelMode,
    EnsureSessionRequest,
    HostApiError,
    HostApiErrorCode,
    HostActivityKind,
    HostUnavailableDetail,
    HostLocalExecutionOptions,
    LocalEngineWorker,
    LocalEngineWorkerFactory,
    LocalWorkerHandle,
    RunStatus,
)
from dayu.host.compaction import (
    CompactAnswerAnchorV2,
    CompactMaterialBlockKind,
    CompactMaterialSection,
    COMPACT_OUTPUT_SCHEMA_V2,
    CompactCandidateDiagnosticV2,
    CompactRepairFeedbackV2,
    CompactionRequest,
    CompactorProposal,
    ContextCompactor,
    CompactCandidateV2,
    CompactEvidenceFactV2,
    CompactForwardIntentV2,
    CompactForwardIntentStatusV2,
    CompactReferenceContinuityV2,
    CompactSessionSummaryV2,
)
from dayu.host.compact_material import (
    CompactMaterialSourceBoundary,
    PreDispatchCompactMaterialView,
    build_pre_dispatch_compact_material_view,
    run_input_material_block,
)
from dayu.host.compact_pipeline import (
    CompactPipelineSourceSnapshot,
    build_fallback_decision_input,
)
from dayu.host.compaction_operation import (
    CompactionOperationResult,
    CompactorProposalRunInput,
    DurableCompactorProposalManifestRecorder,
)
from dayu.host.context_events import CompactorProposalManifestReference
from dayu.host.context_budget import (
    ContextBudgetDecision,
    ContextEstimateMethod,
    ContextPressureLevel,
    ContextSizingFallbackReason,
    ContextSizingStage,
)
from dayu.host.context_anchor import (
    CompatibleContextAnchor,
    ContextAnchorResolution,
)
from dayu.host.context_events import (
    CONTEXT_BUDGET_EVALUATED,
    CONTEXT_COMPACTED,
    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
    CONTEXT_COMPACTION_FAILED,
    CONTEXT_COMPACTION_REQUESTED,
    build_context_compaction_attempt_rejected_payload,
    build_context_compacted_payload,
    build_context_compaction_failed_payload,
    build_context_compaction_requested_payload,
    parse_context_budget_evaluated_payload,
)
from dayu.host.compaction_terminal import (
    COMPACTION_TERMINAL_INVALID_MULTIPLE_ERROR,
)
from dayu.host.context_policy import (
    ContextBudgetPolicy,
    ContextCompactionTriggerSource,
    DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN,
    context_budget_policy_from_threshold_tokens,
)
from tests.host._context_compaction_assertions import assert_failed_payload_no_fallback
from tests.host.fake_compaction import FakeContextCompactor
from dayu.host.tooling import (
    HostToolingOptions,
)
from dayu.host.terminal_post_commit import (
    TerminalPostCommitNotice,
    TerminalPostCommitPort,
)
from dayu.host.session_attachment import SessionWorkLease
from dayu.host.tool_duplicate_governance import (
    DuplicateDecisionKind,
    DuplicateGovernancePolicy,
)
from dayu.contracts.tool_source import ToolBundleSourceKind, ToolBundleSourceRef
from dayu.host.dispatch import (
    ActiveCancelMessage,
    ActiveWorkerRegistry,
    DispatchDrainResult,
    HostDispatchScheduler,
    _DurableRunCancellationToken,
    _HostCancellationToken,
    _safe_close_worker_handle,
    _safe_release_lane_token,
)
from dayu.host.engine_ingest import (
    EngineIngestResult,
    EngineEventIngestor,
    LocalEngineEnvelope,
)
from dayu.host.evidence import (
    AcceptedEvidenceEnvelope,
    AcceptedEvidenceResultRef,
    AcceptedEvidenceToolQuery,
    OpaqueEvidenceRef,
    accepted_evidence_envelope_to_json_value,
)
from dayu.host.memory import (
    CONVERSATION_MEMORY_CONSUMER_ID,
    MemoryProjectionPolicy,
    MemoryRepairReason,
    MemoryRepairRequest,
    MemorySnapshotCursor,
    default_memory_projection_policy,
    digest_memory_projection_policy,
)
from tests.host.fake_compaction import accepted_truth_for_candidate
from dayu.host.memory_repair import (
    ConversationMemoryProjectionRepairResult,
    catch_up_conversation_memory_projection,
)
from dayu.host.run_input import (
    MemoryProjectionRepairRequired,
    NoToolExecutor,
    PolicySnapshot,
    SessionContinuityView,
    ToolExecutionMode,
    load_prepared_runner_call_source_in_transaction,
    prepare_runner_call_candidate_in_transaction,
    record_prepared_runner_call_candidate_in_transaction,
)
from dayu.host._runner_call_manifest import (
    RunnerCallSizingUnavailableReason,
    unavailable_runner_call_sizing_snapshot,
)
from dayu.host.proactive_compaction import (
    ProactiveCompactionAttemptStage,
    ProactiveCompactionDecision,
    ProactiveCompactionPhase,
    ProactiveCompactionProjection,
    read_proactive_compaction_projection,
)
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
from dayu.host.durable.connection import HostDurableStore, open_host_durable_store
from dayu.host.durable.errors import (
    HostDurableError,
    HostTransactionRetryExhaustedError,
)
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.payload import PayloadStore
from dayu.host.durable.projection import read_projection_checkpoint
from dayu.host.durable.schema import (
    TABLE_EVENT_LOG,
    TABLE_HOST_ATTEMPT_DISPATCH_RECORDS,
    TABLE_PAYLOAD_DESCRIPTORS,
    TOOL_CALL_ARGUMENTS_STORAGE_INLINE_JSON,
    TOOL_CALL_SEMANTIC_QUERY_STORAGE_INLINE_TEXT,
)
from dayu.host.durable.run_transition import (
    CancelPredispatchStartingInput,
    CreateAcceptedRunInput,
    _attempt_terminal_event_type,
    _run_terminal_event_type,
    cancel_predispatch_starting_in_transaction,
    create_accepted_run_in_transaction,
    FailUnstartedRunInput,
    RunTransitionResult,
    fail_unstarted_run_in_transaction,
    StartGovernedRunInput,
    start_governed_run_with_starting_attempt_in_transaction,
)
from dayu.host.durable.liveness import (
    HostInstanceIdentity,
    HostInstanceStatus,
    read_host_instance,
    register_current_instance,
)
from dayu.host.durable.session_lifecycle import ensure_session
from dayu.host.durable.state import (
    AttemptRow,
    DispatchRecordRow,
    DispatchRecordStatus,
    RunRow,
    RunStartReason,
    StateMutationStatus,
    WorkerKind,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatching_after_lane_row,
    read_attempt_by_id,
    read_dispatch_record_by_attempt_id,
    read_run_by_id,
)
from dayu.host.durable.transaction import (
    HostReadTransactionOperation,
    HostTransaction,
    HostTransactionRunner,
)
from dayu.host.durable.tool_trace import (
    read_runner_call_reconstruction_signals_by_run,
    resolve_runner_call_projection_from_signal,
)
from dayu.host.local_proxy import DefaultLocalEngineWorkerFactory
from dayu.host.projection import ProjectionCatchupPort
from dayu.host.read_api import _host_event_from_row
from dayu.host.run_input import PreparedRunnerCallCandidate
from dayu.host.tool_trace import (
    ToolTraceSinkOptions,
    catch_up_tool_trace_projection,
)
from dayu.runtime.lane import (
    LaneAcquired,
    LaneAcquireOutcome,
    LaneClaimToken,
    LaneConfig,
    LaneController,
    LaneOwner,
    RuntimeLaneClosedError,
    SQLiteLaneCoordinatorConfig,
)

_NOW = datetime(2026, 5, 15, 1, 2, 3, tzinfo=UTC)
_CALL_CONTEXT_DIGEST = sha256_digest_json({"context": "dispatch-test"})
_COMPACTOR_PROPOSAL_DESCRIPTOR_COUNT = 2
_COMPACTOR_RUNNER_CALL_KIND = "compactor_proposal"
_ACCEPTED_ATTEMPT_NUMBER_FIELD = "accepted_attempt_number"
_ATTEMPT_NUMBER_FIELD = "attempt_number"
_ACCEPTED_MANIFEST_REF_FIELD = "accepted_proposal_manifest_ref"
_ACCEPTED_MANIFEST_DIGEST_FIELD = "accepted_proposal_manifest_digest"
_REJECTED_MANIFEST_REF_FIELD = "proposal_manifest_ref"
_REJECTED_MANIFEST_DIGEST_FIELD = "proposal_manifest_digest"


def _successful_response_identity_for_agent_request(
    request: AgentRunRequest,
) -> SuccessfulRunnerResponseIdentity:
    """构造与 dispatch fixture 的 Engine request 同源的成功响应身份。

    :param request: 当前 worker/compactor 实际收到的 Engine request。
    :returns: provider request id 明确不可用的成功响应身份。
    :raises ValueError: request identity 字段非法时抛出。
    """

    return SuccessfulRunnerResponseIdentity(
        effective_provider=request.runner_spec.provider,
        effective_model=request.runner_spec.model,
        runner_request_identity=build_runner_request_identity(
            run_id=request.run_id,
            attempt_id=request.attempt_id,
            execution_id=request.execution_id,
            iteration_id=f"{request.run_id}:dispatch-final",
            iteration_index=0,
            runner_call_index=1,
        ),
        provider_request_id_availability=ProviderRequestIdAvailability.UNAVAILABLE,
        provider_request_id=None,
    )


def _proposal_manifest_reference(
    *,
    operation_id: str,
    attempt_number: int,
    compactor_engine_run_id: str,
) -> CompactorProposalManifestReference:
    """构造 dispatch durable fixture 的 typed manifest reference。

    :param operation_id: 当前 compaction operation id。
    :param attempt_number: 当前 proposal attempt number。
    :param compactor_engine_run_id: 当前 manifest 显式绑定的 Engine run id。
    :returns: 与 operation/attempt/run 同源的 manifest reference。
    :raises ValueError: manifest binding 字段非法时抛出。
    """

    return CompactorProposalManifestReference(
        manifest_event_id=f"manifest-event:{operation_id}:{attempt_number}",
        manifest_payload_ref=f"runner-call-manifest:{operation_id}:{attempt_number}",
        manifest_digest=_CALL_CONTEXT_DIGEST,
        compactor_input_projection_ref=f"projection:{operation_id}:{attempt_number}",
        compactor_input_projection_digest=_CALL_CONTEXT_DIGEST,
        compaction_operation_id=operation_id,
        compaction_attempt_number=attempt_number,
        compactor_engine_run_id=compactor_engine_run_id,
    )


_LANE_NAME = "llm"


class _RecordingTerminalPort(TerminalPostCommitPort):
    """记录 scheduler producer 的 exact terminal notices。"""

    def __init__(self) -> None:
        """初始化空记录器。

        :returns: ``None``。
        """

        self.notices: list[TerminalPostCommitNotice] = []

    def notify_terminal_post_commit(
        self,
        notice: TerminalPostCommitNotice,
    ) -> None:
        """记录一次 terminal notice。

        :param notice: exact terminal notice。
        :returns: ``None``。
        """

        self.notices.append(notice)


class _RecordingTerminalPortFactory:
    """记录 scheduler construction/bind 使用的 terminal port factory。"""

    def __init__(self, port: _RecordingTerminalPort | None = None) -> None:
        """初始化 factory。

        :param port: 可选预建 recording port。
        :returns: ``None``。
        """

        self.port = port if port is not None else _RecordingTerminalPort()
        self.create_calls = 0
        self.close_calls = 0
        self.promotion_port: AdmissionWakeupPort | None = None

    def create_terminal_post_commit_port(
        self,
        *,
        promotion_port: AdmissionWakeupPort,
    ) -> TerminalPostCommitPort:
        """记录稳定 promotion capability 并返回最终 port。

        :param promotion_port: 不可运行 scheduler promotion capability。
        :returns: recording terminal port。
        """

        self.create_calls += 1
        self.promotion_port = promotion_port
        return self.port

    async def close_after_failed_scheduler_open(self) -> None:
        """记录 construction failure cleanup 调用。

        :returns: ``None``。
        """

        self.close_calls += 1


class _FailingTerminalPortFactory(_RecordingTerminalPortFactory):
    """可在 coordinator construction 阶段失败的 recording factory。"""

    def __init__(self, *, fail_create: bool) -> None:
        """初始化失败模式。

        :param fail_create: ``True`` 时在 create 调用内失败。
        :returns: ``None``。
        """

        super().__init__()
        self._fail_create = fail_create
        self.scheduler: HostDispatchScheduler | None = None

    def create_terminal_post_commit_port(
        self,
        *,
        promotion_port: AdmissionWakeupPort,
    ) -> TerminalPostCommitPort:
        """记录未启动 scheduler，并按配置注入 construction failure。

        :param promotion_port: 不可运行 scheduler promotion capability。
        :returns: recording terminal port。
        :raises RuntimeError: ``fail_create=True`` 时固定抛出。
        """

        if not isinstance(promotion_port, HostDispatchScheduler):
            raise AssertionError("promotion capability must be scheduler")
        self.scheduler = promotion_port
        self.create_calls += 1
        self.promotion_port = promotion_port
        if self._fail_create:
            raise RuntimeError("injected terminal coordinator construction failure")
        return self.port


_SOFT_THRESHOLD_PROMPT_CHAR_COUNT = 120
_HARD_THRESHOLD_PROMPT_CHAR_COUNT = 240
_SOFT_CONTEXT_WINDOW_SIZE = 200
_SOFT_RESERVED_OUTPUT_TOKENS = 20
_SOFT_HARD_THRESHOLD_TOKENS = 180
_SOFT_SAFETY_MARGIN_RATIO = 0.5
_REPEATED_OVERFLOW_SYNC_TIMEOUT_SECONDS = 2.0
_SCHEDULER_CLOSE_REASON = "scheduler_close"
_EVENT_LOG_TEST_READ_LIMIT = 200
_RUNNER_CALL_MANIFEST_REF_PREFIX = "runner-call-manifest:"
_ATTEMPT_TERMINAL_STATUSES = (
    AttemptStatus.SUCCEEDED,
    AttemptStatus.FAILED,
    AttemptStatus.CANCELLED,
    AttemptStatus.LOST,
)
_RUN_TERMINAL_STATUSES = (
    RunStatus.SUCCEEDED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
    RunStatus.LOST,
)
_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class _SchedulerCloseLifecycleCase:
    """scheduler close lifecycle proof matrix 的单行场景。"""

    scenario_id: str
    window: str
    expected_close_action: str
    expected_durable_mutation: str
    expected_resource_cleanup: str
    coverage_classification: str


_SCHEDULER_CLOSE_LIFECYCLE_MATRIX = (
    _SchedulerCloseLifecycleCase(
        scenario_id="close-active-worker",
        window="active worker event stream",
        expected_close_action="cancel active token with scheduler_close and await active task cleanup",
        expected_durable_mutation="no scheduler-close-created terminal canonical fact",
        expected_resource_cleanup="handle close once, registry unregister, lane token release",
        coverage_classification="existing",
    ),
    _SchedulerCloseLifecycleCase(
        scenario_id="cancel-all-after-register",
        window="ActiveWorkerRegistry.cancel_all snapshot propagation",
        expected_close_action="cancel only entries captured before lock release",
        expected_durable_mutation="none",
        expected_resource_cleanup="later registered entries require a later cancel_all call",
        coverage_classification="new",
    ),
    _SchedulerCloseLifecycleCase(
        scenario_id="dispatch-queue-non-empty-close",
        window="pending dispatch queue before drain",
        expected_close_action="fail closed without drain-until-empty",
        expected_durable_mutation="run attempt and dispatch row remain recoverable by next open",
        expected_resource_cleanup="wakeup and drain APIs reject after close",
        coverage_classification="new",
    ),
    _SchedulerCloseLifecycleCase(
        scenario_id="promotion-queue-non-empty-close",
        window="promotion task running with queued session behind it",
        expected_close_action="cancel tracked promotion task without draining queued sessions",
        expected_durable_mutation="no terminal canonical fact",
        expected_resource_cleanup="promotion task done and pending promotion queue remains local-only",
        coverage_classification="new",
    ),
    _SchedulerCloseLifecycleCase(
        scenario_id="lane-wait-pre-worker-close",
        window="dispatch has entered lane wait before worker accept",
        expected_close_action="cancel drain path or receive lane close cancellation",
        expected_durable_mutation="no worker_startup_timeout terminal fact",
        expected_resource_cleanup="drain task done and lane controller closed",
        coverage_classification="new",
    ),
    _SchedulerCloseLifecycleCase(
        scenario_id="worker-accepted-before-consumer-start-close",
        window="worker accepted and active task registered before event consume body starts",
        expected_close_action="cancel active token and close residual active handle",
        expected_durable_mutation="no scheduler-close-created terminal canonical fact",
        expected_resource_cleanup="handle close once, registry clear, active task done",
        coverage_classification="new",
    ),
    _SchedulerCloseLifecycleCase(
        scenario_id="close-cancelled-mid-cleanup-retry",
        window="outer task cancellation during scheduler close cleanup",
        expected_close_action="propagate CancelledError and allow later close retry to finish cleanup",
        expected_durable_mutation="no scheduler-close-created terminal canonical fact",
        expected_resource_cleanup="active registry empty, active tasks done, lane closed",
        coverage_classification="new",
    ),
    _SchedulerCloseLifecycleCase(
        scenario_id="close-drain-until-empty",
        window="graceful completion of all pending local work",
        expected_close_action="not a scheduler close contract",
        expected_durable_mutation="none",
        expected_resource_cleanup="none",
        coverage_classification="non-goal",
    ),
)


class _RetryExhaustedReadRunner(HostTransactionRunner):
    """测试用 read transaction runner，始终模拟 durable 不可读。"""

    def __init__(self) -> None:
        """跳过真实 SQLite runner 初始化。

        :returns: ``None``。
        """

    def run_read(self, operation: HostReadTransactionOperation[_T]) -> _T:
        """模拟 read transaction busy 重试耗尽。

        :param operation: Host read transaction operation。
        :returns: 不会返回。
        :raises HostTransactionRetryExhaustedError: 始终抛出。
        """

        del operation
        raise HostTransactionRetryExhaustedError(
            "Host durable read transaction busy retry exhausted",
            attempts=3,
        )


@dataclass(frozen=True, slots=True)
class _SeededRun:
    """测试中创建的 running Run。"""

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str


@dataclass(frozen=True, slots=True)
class _AcceptedSeededRun:
    """测试中创建的 pre-start accepted Run。"""

    session_id: str
    run_id: str


@dataclass(slots=True)
class _FailingProjectionCatchup(ProjectionCatchupPort):
    """测试用失败 projection catch-up port。"""

    calls: int = 0

    def catch_up_projection(self) -> None:
        """记录调用并模拟 catch-up 失败。

        :returns: ``None``。
        :raises RuntimeError: 始终抛出测试错误。
        """

        self.calls += 1
        raise RuntimeError("forced scheduler projection catch-up failure")


class _FakeHandle:
    """测试用 worker handle。"""

    def __init__(self, local_worker_id: str = "local-worker-test") -> None:
        """初始化 fake handle。

        :param local_worker_id: 本地 worker id。
        :returns: ``None``。
        """

        self._local_worker_id = local_worker_id
        self.closed = False

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker id。

        :returns: 本地 worker id。
        """

        return self._local_worker_id

    async def events(self) -> AsyncIterator[EngineEvent]:
        """返回空事件流。

        :returns: 空异步迭代器。
        """

        if False:
            yield _unreachable_engine_event()

    def on_cancel(self, reason: str) -> None:
        """记录取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason

    async def close(self) -> None:
        """关闭 fake handle。

        :returns: ``None``。
        """

        self.closed = True


class _CrashingHandle(_FakeHandle):
    """事件流抛异常的 fake handle。"""

    async def events(self) -> AsyncIterator[EngineEvent]:
        """抛出 worker stream 异常。

        :returns: 不会正常返回事件。
        :raises RuntimeError: 始终模拟 worker stream crash。
        """

        raise RuntimeError("worker stream crashed")
        if False:
            yield _unreachable_engine_event()


class _PreparedManifestProactiveCompactor(FakeContextCompactor):
    """支持 prepared proposal manifest 的 proactive 测试 compactor。"""

    def __init__(self, *, fail_run: bool = False) -> None:
        """初始化 prepared compactor。

        :param fail_run: 是否在 proposal run 阶段抛出测试异常。
        :returns: ``None``。
        """

        super().__init__()
        self.fail_run = fail_run
        self.calls = 0
        self.prepared_requests: list[CompactionRequest] = []
        self.prepared_inputs: list[CompactorProposalRunInput] = []
        self._prepared_request: CompactionRequest | None = None

    def prepare_compactor_proposal_run_input(
        self,
        request: CompactionRequest,
        cancellation_token: CancellationToken,
        *,
        compaction_operation_id: str | None,
        compaction_attempt_number: int,
        repair_feedback: CompactRepairFeedbackV2 | None,
    ) -> CompactorProposalRunInput:
        """构造可持久化 manifest 的 deterministic proposal runner input。

        :param request: Host 构造的 compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :param compaction_operation_id: Host compaction operation id。
        :param compaction_attempt_number: operation 内 proposal attempt 序号。
        :param repair_feedback: 前次 semantic validation feedback。
        :returns: prepared proposal runner input。
        """

        self.prepared_requests.append(request)
        self._prepared_request = request
        compact_input = request.compact_input
        agent_request = _proposal_compactor_agent_request(
            request,
            cancellation_token=cancellation_token,
            compaction_operation_id=compaction_operation_id,
            compaction_attempt_number=compaction_attempt_number,
        )
        roles = tuple(message.role.value for message in agent_request.messages)
        projection: Mapping[str, JsonValue] = {
            "projection_kind": "proactive_compactor_input_projection",
            "compaction_request_digest": request.digest(),
            "repair_feedback": (None if repair_feedback is None else repair_feedback.to_json()),
        }
        prepared_input = CompactorProposalRunInput(
            compact_input=compact_input,
            agent_request=agent_request,
            compaction_request_digest=request.digest(),
            compactor_engine_run_id=agent_request.run_id,
            message_count=len(agent_request.messages),
            role_sequence_digest=runner_role_sequence_digest(roles),
            system_prompt_asset_digest=_CALL_CONTEXT_DIGEST,
            user_prompt_template_digest=_CALL_CONTEXT_DIGEST,
            user_prompt_digest=sha256_digest_json({"user_prompt": "proactive"}),
            compactor_input_projection=projection,
            compactor_input_projection_digest=sha256_digest_json(projection),
            repair_feedback=repair_feedback,
        )
        self.prepared_inputs.append(prepared_input)
        return prepared_input

    async def run_prepared_compactor_proposal(
        self,
        prepared_input: CompactorProposalRunInput,
    ) -> CompactorProposal:
        """执行 prepared proposal。

        :param prepared_input: 已准备且可记录 manifest 的 proposal input。
        :returns: fake compact candidate。
        :raises RuntimeError: ``fail_run`` 为真时抛出。
        :raises AssertionError: prepared request 缺失时抛出。
        """

        self.calls += 1
        if self.fail_run:
            raise RuntimeError("prepared proposal failed")
        proposal = await super().compact(
            self._latest_prepared_request(),
            prepared_input.agent_request.cancellation_token,
            repair_feedback=prepared_input.repair_feedback,
        )
        return CompactorProposal(
            candidate=proposal.candidate,
            successful_response_identity=(
                _successful_response_identity_for_agent_request(prepared_input.agent_request)
            ),
        )

    def _latest_prepared_request(self) -> CompactionRequest:
        """读取最近一次 frozen compaction request。

        :returns: 最近一次 prepared request。
        :raises AssertionError: request 尚未准备时抛出。
        """

        request = self._prepared_request
        if request is None:
            raise AssertionError("prepared request is missing")
        return request


class _TransactionReadableCompactor(_PreparedManifestProactiveCompactor):
    """测试 compactor 调用期可开启独立读事务。"""

    def __init__(self, transaction_runner: HostTransactionRunner) -> None:
        """初始化 compactor。

        :param transaction_runner: Host transaction runner。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__()
        self._transaction_runner = transaction_runner

    async def run_prepared_compactor_proposal(
        self,
        prepared_input: CompactorProposalRunInput,
    ) -> CompactorProposal:
        """执行 prepared proposal 并验证当前不在外层 write transaction 内。

        :param prepared_input: 已准备且可记录 manifest 的 proposal input。
        :returns: fake compaction candidate。
        """

        request = self._latest_prepared_request()
        row = self._transaction_runner.run_read(lambda transaction: read_run_by_id(transaction, request.run_id))
        assert row is not None
        return await super().run_prepared_compactor_proposal(prepared_input)


class _StaleMutatingCompactor(FakeContextCompactor):
    """测试 compactor 返回前让源 Run 状态变化。"""

    def __init__(self, transaction_runner: HostTransactionRunner) -> None:
        """初始化 compactor。

        :param transaction_runner: Host transaction runner。
        :returns: ``None``。
        """

        super().__init__()
        self._transaction_runner = transaction_runner
        self._fake = FakeContextCompactor()

    async def compact(
        self,
        request: CompactionRequest,
        cancellation_token: CancellationToken,
        *,
        repair_feedback: CompactRepairFeedbackV2 | None,
    ) -> CompactorProposal:
        """先把源 Run 失败收口，再返回 candidate。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: fake compaction candidate。
        """

        def _operation(transaction: HostTransaction) -> None:
            run = read_run_by_id(transaction, request.run_id)
            assert run is not None
            fail_unstarted_run_in_transaction(
                transaction,
                EventLogStore(),
                FailUnstartedRunInput(
                    run_id=request.run_id,
                    expected_status=run.status,
                    run_failed_event_id=f"event-stale-run-failed-{request.run_id}",
                    occurred_at=datetime.now(UTC),
                    actor="pytest",
                    source="pytest",
                    reason="stale-test",
                    error_code="stale_test",
                    message="stale test",
                ),
            )

        self._transaction_runner.run_write(_operation)
        return await self._fake.compact(
            request,
            cancellation_token,
            repair_feedback=repair_feedback,
        )


class _TerminalWinningProactiveCompactor(FakeContextCompactor):
    """在 proactive provider await 内先提交同 operation failed terminal。"""

    def __init__(self, transaction_runner: HostTransactionRunner) -> None:
        """初始化 first-terminal winner compactor。

        :param transaction_runner: Host transaction runner。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__()
        self._transaction_runner = transaction_runner

    async def compact(
        self,
        request: CompactionRequest,
        cancellation_token: CancellationToken,
        *,
        repair_feedback: CompactRepairFeedbackV2 | None,
    ) -> CompactorProposal:
        """先提交 failed first truth，再返回 late accepted candidate。

        :param request: proactive compaction request。
        :param cancellation_token: Host cancellation token。
        :returns: late accepted fake candidate。
        :raises AssertionError: request canonical fact 不存在时抛出。
        """

        def _operation(transaction: HostTransaction) -> None:
            """在独立 write transaction 内提交 first terminal truth。

            :param transaction: 当前 Host write transaction。
            :returns: ``None``。
            :raises AssertionError: request canonical fact 不存在时抛出。
            """

            requested = EventLogStore().read_latest_run_event_by_type(
                transaction,
                run_id=request.run_id,
                event_type=CONTEXT_COMPACTION_REQUESTED,
            )
            assert requested is not None
            EventLogStore().append_event(
                transaction,
                EventLogAppendRequest(
                    event_id="event-proactive-first-terminal-failed",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=request.session_id,
                    run_id=request.run_id,
                    attempt_id=None,
                    execution_id=None,
                    event_type=CONTEXT_COMPACTION_FAILED,
                    occurred_at=_NOW,
                    actor="tester",
                    source="pytest",
                    client_request_id=None,
                    idempotency_key=None,
                    policy_decision=None,
                    reason=None,
                    payload_json=build_context_compaction_failed_payload(
                        operation_id=requested.event_id,
                        failure_reason="concurrent_governance_winner",
                        policy_decision="fail_closed",
                        retryable=False,
                        attempt_count=0,
                        retry_repair_budget_exhausted=False,
                        diagnostic_refs=("diagnostic:first-winner",),
                        budget_after_attempted_compact=None,
                    ),
                    payload_ref=None,
                    payload_digest=None,
                ),
            )

        self._transaction_runner.run_write(_operation)
        return await super().compact(
            request,
            cancellation_token,
            repair_feedback=repair_feedback,
        )


class _RaisingCompactor(_PreparedManifestProactiveCompactor):
    """测试用 prepared proposal run 始终失败 compactor。"""

    def __init__(self) -> None:
        """初始化 prepared failure compactor。

        :returns: ``None``。
        """

        super().__init__(fail_run=True)


class _QualityRejectOnceCompactor(_PreparedManifestProactiveCompactor):
    """首次返回 quality rejection，第二次返回 accepted candidate。"""

    def __init__(self) -> None:
        """初始化 fake compactor 与调用计数。

        :returns: ``None``。
        """

        super().__init__()

    async def run_prepared_compactor_proposal(
        self,
        prepared_input: CompactorProposalRunInput,
    ) -> CompactorProposal:
        """构造一次可修复 quality rejection。

        :param prepared_input: 已准备且可记录 manifest 的 proposal input。
        :returns: compaction candidate。
        """

        proposal = await super().run_prepared_compactor_proposal(prepared_input)
        if self.calls == 1:
            return CompactorProposal(
                candidate=replace(
                    proposal.candidate,
                    diagnostics=(
                        CompactCandidateDiagnosticV2(
                            code="invalid-current-anchor",
                            message="invalid current anchor citation",
                            source_labels=("C1",),
                        ),
                    ),
                ),
                successful_response_identity=(proposal.successful_response_identity),
            )
        return proposal


class _AlwaysQualityRejectingCompactor(_PreparedManifestProactiveCompactor):
    """每次 runner call 成功但 candidate 都被 quality contract 拒绝的 compactor。"""

    async def run_prepared_compactor_proposal(
        self,
        prepared_input: CompactorProposalRunInput,
    ) -> CompactorProposal:
        """返回携带同源成功响应身份的无效 candidate。

        :param prepared_input: 已准备且可记录 manifest 的 proposal input。
        :returns: 必然触发 quality rejection 的 compaction proposal。
        :raises Exception: 基类 fake proposal 执行失败时透传。
        """

        proposal = await super().run_prepared_compactor_proposal(prepared_input)
        return CompactorProposal(
            candidate=replace(
                proposal.candidate,
                diagnostics=(
                    CompactCandidateDiagnosticV2(
                        code="invalid-current-anchor",
                        message="invalid current anchor citation",
                        source_labels=("C1",),
                    ),
                ),
            ),
            successful_response_identity=proposal.successful_response_identity,
        )


def _retain_feedback_without_binding_for_defensive_test(
    feedback: CompactRepairFeedbackV2 | None,
    request: CompactionRequest,
) -> CompactRepairFeedbackV2 | None:
    """绕过 dispatcher 正常清理，仅用于验证 operation defensive guard。

    :param feedback: 前一 attempt feedback。
    :param request: 当前 attempt request；测试 seam 故意不校验。
    :returns: 原 feedback。
    """

    del request
    return feedback


class _BlockingAfterManifestCompactor(_PreparedManifestProactiveCompactor):
    """manifest 提交后阻塞 provider result 的 proactive compactor。"""

    def __init__(self) -> None:
        """初始化 provider 进入 barrier。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__()
        self.provider_entered = asyncio.Event()
        self.provider_release = asyncio.Event()
        self.provider_calls = 0

    async def run_prepared_compactor_proposal(
        self,
        prepared_input: CompactorProposalRunInput,
    ) -> CompactorProposal:
        """进入 provider 后等待测试释放。

        :param prepared_input: 已提交 manifest 的 proposal input。
        :returns: fake accepted candidate。
        :raises asyncio.CancelledError: caller 模拟 crash 时透传。
        """

        self.provider_calls += 1
        self.provider_entered.set()
        await self.provider_release.wait()
        return await super().run_prepared_compactor_proposal(prepared_input)


class _SimulatedProactiveCrash(BaseException):
    """模拟 manifest 已提交、provider 结果未持久化时的进程终止。"""


class _CrashAtPreparedAttemptCompactor(_PreparedManifestProactiveCompactor):
    """在指定 global attempt 的 manifest 提交后阻塞并模拟 crash。"""

    def __init__(self, crash_attempt_number: int) -> None:
        """初始化 crash attempt 与 provider barrier。

        :param crash_attempt_number: manifest 后阻塞的 global attempt number。
        :returns: ``None``。
        :raises ValueError: crash attempt 不是正整数时抛出。
        """

        super().__init__()
        if crash_attempt_number <= 0:
            raise ValueError("crash_attempt_number must be positive")
        self._crash_attempt_number = crash_attempt_number
        self.provider_entered = asyncio.Event()

    async def run_prepared_compactor_proposal(
        self,
        prepared_input: CompactorProposalRunInput,
    ) -> CompactorProposal:
        """前序 attempts 模拟 proposal failure，目标 attempt 触发进程级 crash。

        :param prepared_input: 已提交 manifest 的 proposal input。
        :returns: 不返回 accepted candidate。
        :raises RuntimeError: 目标前的 attempts 模拟 proposal failure。
        :raises _SimulatedProactiveCrash: 目标 attempt 的 manifest 提交后抛出。
        """

        self.calls += 1
        if self.calls == self._crash_attempt_number:
            self.provider_entered.set()
            raise _SimulatedProactiveCrash
        if self.calls > self._crash_attempt_number:
            raise AssertionError("compactor advanced beyond crash attempt")
        raise RuntimeError("proposal failed before prepared crash attempt")


class _RequestCapturingCompactor(_PreparedManifestProactiveCompactor):
    """记录 proactive compaction request 的测试 compactor。"""


class _MinimalSummaryCompactor(_RequestCapturingCompactor):
    """返回最短 accepted summary 的 proactive 测试 compactor。"""

    async def run_prepared_compactor_proposal(
        self,
        prepared_input: CompactorProposalRunInput,
    ) -> CompactorProposal:
        """构造短 summary，避免测试 fixture 触发 compact 后预算拒绝。

        :param prepared_input: 已准备且可记录 manifest 的 proposal input。
        :returns: 最小 vNext compaction candidate。
        :raises AssertionError: 测试输入缺少 trace material 时抛出。
        """

        source_labels = prepared_input.compact_input.source_labels
        if len(source_labels) == 0:
            raise AssertionError("compact input has no citable label")
        return CompactorProposal(
            candidate=CompactCandidateV2(
                schema=COMPACT_OUTPUT_SCHEMA_V2,
                session_summary=CompactSessionSummaryV2(
                    text="rolled",
                    source_labels=source_labels,
                ),
                evidence_facts=(),
                answer_anchors=(),
                forward_intents=(),
                reference_continuity=(),
                diagnostics=(),
                explicitly_dropped_sources=(),
            ),
            successful_response_identity=(
                _successful_response_identity_for_agent_request(prepared_input.agent_request)
            ),
        )


class _RecoveryScenarioCompactor(_PreparedManifestProactiveCompactor):
    """按调用序号控制 S4 recovery 成败的 proactive 测试 compactor。"""

    def __init__(
        self,
        *,
        accept_call: int,
        transaction_runner: HostTransactionRunner | None = None,
        stale_after_call: int | None = None,
    ) -> None:
        """初始化 recovery 场景 compactor。

        :param accept_call: 第几次 compactor call 返回 accepted candidate。
        :param transaction_runner: 可选 durable runner；提供后可在指定 call 后制造 stale。
        :param stale_after_call: 指定 call 返回前把源 Run 置为 stale。
        :returns: ``None``。
        """

        super().__init__()
        self._accept_call = accept_call
        self._transaction_runner = transaction_runner
        self._stale_after_call = stale_after_call

    async def run_prepared_compactor_proposal(
        self,
        prepared_input: CompactorProposalRunInput,
    ) -> CompactorProposal:
        """按调用序号失败或返回最小 accepted summary。

        :param prepared_input: 已准备且可记录 manifest 的 proposal input。
        :returns: accepted compact candidate。
        :raises RuntimeError: 当前 call 不应 accepted 时抛出。
        """

        self.calls += 1
        if self._stale_after_call == self.calls:
            _fail_unstarted_for_stale_test(
                self._transaction_runner,
                self._latest_prepared_request(),
            )
        if self.calls != self._accept_call:
            raise RuntimeError("recovery scenario proposal failed")
        source_labels = prepared_input.compact_input.source_labels
        if len(source_labels) == 0:
            raise AssertionError("compact input has no citable label")
        return CompactorProposal(
            candidate=CompactCandidateV2(
                schema=COMPACT_OUTPUT_SCHEMA_V2,
                session_summary=CompactSessionSummaryV2(
                    text=f"recovery summary {self.calls}",
                    source_labels=source_labels,
                ),
                evidence_facts=(),
                answer_anchors=(),
                forward_intents=(),
                reference_continuity=(),
                diagnostics=(),
                explicitly_dropped_sources=(),
            ),
            successful_response_identity=(
                _successful_response_identity_for_agent_request(prepared_input.agent_request)
            ),
        )


def _first_citable_compact_input_label(
    prepared_input: CompactorProposalRunInput,
) -> str:
    """读取测试 compact input 中第一个可引用 source label。

    :param prepared_input: prepared compactor input。
    :returns: 第一个可引用 source label。
    :raises AssertionError: compact input 没有可引用材料时抛出。
    """

    compact_input = prepared_input.compact_input
    if compact_input.source_boundary:
        return compact_input.source_boundary[0].source_label
    raise AssertionError("compact input has no citable label")


def _fail_unstarted_for_stale_test(
    transaction_runner: HostTransactionRunner | None,
    request: CompactionRequest,
) -> None:
    """把测试 Run 置为 failed，制造 compaction stale state。

    :param transaction_runner: Host transaction runner。
    :param request: 当前 compaction request。
    :returns: ``None``。
    :raises AssertionError: transaction runner 缺失或 Run 缺失时抛出。
    """

    if transaction_runner is None:
        raise AssertionError("transaction runner is required")

    def _operation(transaction: HostTransaction) -> None:
        run = read_run_by_id(transaction, request.run_id)
        assert run is not None
        fail_unstarted_run_in_transaction(
            transaction,
            EventLogStore(),
            FailUnstartedRunInput(
                run_id=request.run_id,
                expected_status=run.status,
                run_failed_event_id=(f"event-stale-run-failed-{request.run_id}-{request.digest()}"),
                occurred_at=datetime.now(UTC),
                actor="pytest",
                source="pytest",
                reason="stale-test",
                error_code="stale_test",
                message="stale test",
            ),
        )

    transaction_runner.run_write(_operation)


class _CloseFailingHandle(_FakeHandle):
    """关闭时抛异常的 fake handle。"""

    async def events(self) -> AsyncIterator[EngineEvent]:
        """保持事件流未结束直到 scheduler close。

        :returns: 不会正常返回事件。
        """

        await asyncio.sleep(10.0)
        if False:
            yield _unreachable_engine_event()

    def on_cancel(self, reason: str) -> None:
        """模拟 handle cancel 异常。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises RuntimeError: 始终抛出取消异常。
        """

        del reason
        raise RuntimeError("cancel failed")

    async def close(self) -> None:
        """模拟 handle close 异常。

        :returns: ``None``。
        :raises RuntimeError: 始终抛出关闭异常。
        """

        raise RuntimeError("close failed")


class _CloseCountingHandle(_FakeHandle):
    """记录 cancel / close 次数且事件流长期挂起的 fake handle。"""

    def __init__(self) -> None:
        """初始化计数 handle。

        :returns: ``None``。
        """

        super().__init__()
        self.cancel_count = 0
        self.close_count = 0

    async def events(self) -> AsyncIterator[EngineEvent]:
        """保持事件流未结束直到 scheduler close。

        :returns: 不会正常返回事件。
        """

        await asyncio.sleep(10.0)
        if False:
            yield _unreachable_engine_event()

    def on_cancel(self, reason: str) -> None:
        """记录取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason
        self.cancel_count += 1

    async def close(self) -> None:
        """记录关闭次数。

        :returns: ``None``。
        """

        self.close_count += 1
        await super().close()


class _CancelHookFailingHandle(_CloseCountingHandle):
    """on_cancel 失败但 mandatory close 可成功的 fake handle。"""

    def on_cancel(self, reason: str) -> None:
        """记录 hook 调用后模拟 best-effort 失败。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises RuntimeError: 始终模拟 hook 失败。
        """

        super().on_cancel(reason)
        raise RuntimeError("cancel hook failed")


class _FailOnceCloseHandle(_FakeHandle):
    """首次 mandatory close 失败、重试成功的 fake handle。"""

    def __init__(self) -> None:
        """初始化 close 计数。

        :returns: ``None``。
        """

        super().__init__()
        self.close_count = 0

    async def close(self) -> None:
        """首次抛错，后续完成真实 fake close。

        :returns: ``None``。
        :raises RuntimeError: 首次调用模拟 mandatory close 失败。
        """

        self.close_count += 1
        if self.close_count == 1:
            raise RuntimeError("mandatory handle close failed")
        await super().close()


class _ControlledBlockingHandle(_FakeHandle):
    """用 asyncio.Event 控制事件流生命周期的 fake handle。"""

    def __init__(self) -> None:
        """初始化受控 handle。

        :returns: ``None``。
        """

        super().__init__()
        self.cancel_count = 0
        self.close_count = 0
        self.events_started = asyncio.Event()
        self.events_finalized = asyncio.Event()
        self.release_events = asyncio.Event()

    async def events(self) -> AsyncIterator[EngineEvent]:
        """阻塞事件流直到测试释放或 task 被取消。

        :returns: 不会自然返回事件，除非测试显式释放。
        """

        self.events_started.set()
        try:
            await self.release_events.wait()
        finally:
            self.events_finalized.set()
        if False:
            yield _unreachable_engine_event()

    def on_cancel(self, reason: str) -> None:
        """记录取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason
        self.cancel_count += 1

    async def close(self) -> None:
        """记录关闭请求。

        :returns: ``None``。
        """

        self.close_count += 1
        await super().close()


class _RegisteringCancelHandle(_FakeHandle):
    """取消回调中注册第二个 active entry 的测试 handle。"""

    def __init__(
        self,
        *,
        registry: ActiveWorkerRegistry,
        second_token: _HostCancellationToken,
        second_handle: _FakeHandle,
    ) -> None:
        """初始化测试 handle。

        :param registry: 待测试 active worker registry。
        :param second_token: 后注册 entry 的 cancellation token。
        :param second_handle: 后注册 entry 的 worker handle。
        :returns: ``None``。
        """

        super().__init__()
        self._registry = registry
        self._second_token = second_token
        self._second_handle = second_handle
        self.cancel_reasons: list[str] = []

    def on_cancel(self, reason: str) -> None:
        """记录取消原因并在传播过程中注册第二个 entry。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        self.cancel_reasons.append(reason)
        self._registry.register(
            session_id="session-second",
            run_id="run-second",
            attempt_id="attempt-second",
            execution_id="execution-second",
            handle=self._second_handle,
            cancellation_token=self._second_token,
        )


class _BlockedLaneAcquire:
    """阻塞 lane acquire 的确定性测试替身。"""

    def __init__(self) -> None:
        """初始化阻塞 acquire 替身。

        :returns: ``None``。
        """

        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def __call__(
        self,
        name: str,
        *,
        token: CancellationToken | None = None,
        timeout_seconds: float | None = None,
    ) -> LaneAcquireOutcome:
        """阻塞 acquire，直到外层 drain task 被取消。

        :param name: lane 名称。
        :param token: 可选取消 token。
        :param timeout_seconds: acquire timeout。
        :returns: 正常路径不会返回。
        :raises AssertionError: 若测试错误释放阻塞点则抛出。
        """

        del name, token, timeout_seconds
        self.started.set()
        await self.release.wait()
        raise AssertionError("blocked lane acquire must be cancelled by scheduler close")


class _CloseOnceBlockedLaneClose:
    """第一次 lane close 阻塞，后续调用转发到真实 close。"""

    def __init__(
        self,
        original_close: Callable[[str | None], Awaitable[None]],
    ) -> None:
        """初始化阻塞 close 替身。

        :param original_close: 真实 lane controller close 方法。
        :returns: ``None``。
        """

        self._original_close = original_close
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def __call__(self, reason: str | None = None) -> None:
        """第一次调用阻塞以便测试取消 close，第二次执行真实 close。

        :param reason: close reason。
        :returns: ``None``。
        :raises asyncio.CancelledError: 第一次调用被外层取消时透传。
        """

        self.calls += 1
        if self.calls == 1:
            self.started.set()
            await self.release.wait()
        await self._original_close(reason)


class _FailingLaneClose:
    """始终抛出 close 异常的 lane close 替身。"""

    def __init__(self) -> None:
        """初始化调用计数。

        :returns: ``None``。
        """

        self.calls = 0

    async def __call__(self, reason: str | None = None) -> None:
        """模拟 lane close 失败。

        :param reason: close 原因。
        :returns: 不会正常返回。
        :raises RuntimeError: 始终抛出测试异常。
        """

        del reason
        self.calls += 1
        raise RuntimeError("lane close failed")


async def _unstarted_active_consumer_probe(started: asyncio.Event) -> None:
    """模拟尚未进入 worker event consume body 的 active task。

    :param started: 若 task body 被调度执行则置位的事件。
    :returns: ``None``。
    """

    started.set()
    await asyncio.sleep(1)


class _FlakyLocalWorkerIdHandle(_FakeHandle):
    """第二次读取 ``local_worker_id`` 时抛错的 fake handle。"""

    def __init__(self) -> None:
        """初始化 fake handle。

        :returns: ``None``。
        """

        super().__init__("local-worker-first-read")
        self.local_worker_id_reads = 0
        self.close_count = 0

    @property
    def local_worker_id(self) -> str:
        """第一次返回 worker id，后续模拟 pre-event envelope 构造失败。

        :returns: 本地 worker id。
        :raises RuntimeError: 第二次及后续读取时抛出。
        """

        self.local_worker_id_reads += 1
        if self.local_worker_id_reads == 1:
            return "local-worker-first-read"
        raise RuntimeError("local worker id unavailable")

    async def events(self) -> AsyncIterator[EngineEvent]:
        """该测试路径不应进入事件流。

        :returns: 不会正常返回事件。
        :raises AssertionError: 若被调用则抛出。
        """

        raise AssertionError("events must not be consumed")
        if False:
            yield _unreachable_engine_event()

    async def close(self) -> None:
        """记录关闭次数。

        :returns: ``None``。
        """

        self.close_count += 1
        await super().close()


class _AcceptingWorker:
    """测试用立即 accept worker。"""

    def __init__(self, factory: "_FakeWorkerFactory") -> None:
        """初始化 worker。

        :param factory: 所属 factory。
        :returns: ``None``。
        """

        self._factory = factory

    async def accept(self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest) -> LocalWorkerHandle:
        """接受 worker 请求。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: fake handle。
        """

        self._factory.accepted_snapshots.append(snapshot)
        self._factory.accepted_requests.append(request)
        if self._factory.accepted_handle is not None:
            return self._factory.accepted_handle
        return _FakeHandle()


class _HandleWorker:
    """返回指定 handle 的 fake worker。"""

    def __init__(self, handle: LocalWorkerHandle) -> None:
        """初始化 worker。

        :param handle: accept 返回的 handle。
        :returns: ``None``。
        """

        self._handle = handle

    async def accept(self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest) -> LocalWorkerHandle:
        """返回预置 handle。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: 预置 handle。
        """

        del snapshot, request
        return self._handle


class _FailingAcceptWorker:
    """accept 时抛异常的 fake worker。"""

    async def accept(self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest) -> LocalWorkerHandle:
        """模拟非 timeout accept 异常。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: 不会返回。
        :raises RuntimeError: 始终抛出 accept 异常。
        """

        del snapshot, request
        raise RuntimeError("accept failed")


class _SlowWorker:
    """测试用超时 worker。"""

    async def accept(self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest) -> LocalWorkerHandle:
        """阻塞直到 scheduler startup timeout。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: 不会返回的 fake handle。
        """

        del snapshot, request
        await asyncio.sleep(1.0)
        return _FakeHandle()


class _FakeWorkerFactory:
    """测试用 worker factory。"""

    def __init__(
        self,
        *,
        slow: bool = False,
        worker: LocalEngineWorker | None = None,
        accepted_handle: LocalWorkerHandle | None = None,
    ) -> None:
        """初始化 factory。

        :param slow: 是否返回超时 worker。
        :param worker: 指定 worker；不传时按 ``slow`` 构造。
        :param accepted_handle: 默认 accepting worker 返回的指定 handle。
        :returns: ``None``。
        """

        self.created = 0
        self.accepted_snapshots: list[AttemptDispatchSnapshot] = []
        self.accepted_requests: list[AgentRunRequest] = []
        self._slow = slow
        self._worker = worker
        self.accepted_handle = accepted_handle

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建 fake worker。

        :param snapshot: dispatch snapshot。
        :returns: fake worker。
        """

        del snapshot
        self.created += 1
        if self._worker is not None:
            return self._worker
        if self._slow:
            return _SlowWorker()
        return _AcceptingWorker(self)


class _LagRepairRunInputBuilder:
    """首次 build 抛出大滞后 repair，第二次返回最小 Engine request。"""

    def __init__(self) -> None:
        """初始化调用计数。

        :returns: ``None``。
        """

        self.calls = 0

    def build(self, snapshot: AttemptDispatchSnapshot) -> AgentRunRequest:
        """构造测试 Engine request，首次模拟 snapshot 大滞后。

        :param snapshot: dispatch snapshot。
        :returns: 最小 no-tool Engine request。
        :raises MemoryProjectionRepairRequired: 首次调用时抛出 lag repair。
        """

        self.calls += 1
        if self.calls == 1:
            policy = default_memory_projection_policy()
            raise MemoryProjectionRepairRequired(
                MemoryRepairRequest(
                    session_id=snapshot.session_id,
                    reason=MemoryRepairReason.SNAPSHOT_LAG_OVER_THRESHOLD,
                    required_event_sequence=20,
                    observed_cursor=MemorySnapshotCursor(
                        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                        checkpoint_event_sequence=0,
                        checkpoint_event_id=None,
                        session_id=snapshot.session_id,
                    ),
                    policy_digest=digest_memory_projection_policy(policy),
                )
            )
        return AgentRunRequest(
            run_id=snapshot.run_id,
            session_id=snapshot.session_id,
            messages=(UserMessage(role=AgentMessageRole.USER, content="dispatch after lag"),),
            disable_tools=True,
            runner_spec=_runner_spec(),
            runner_options=RunnerCallOptions(
                temperature=None,
                max_tokens=None,
                top_p=None,
                stream=False,
            ),
            agent_policy=_agent_policy(False),
            tool_schemas=(),
            tool_executor=NoToolExecutor(),
            cancellation_token=snapshot.cancellation_token,
        )


class _PersistentLagRepairRunInputBuilder:
    """每次 build 都抛出大滞后 repair。"""

    def __init__(self) -> None:
        """初始化调用计数。

        :returns: ``None``。
        """

        self.calls = 0

    def build(self, snapshot: AttemptDispatchSnapshot) -> AgentRunRequest:
        """构造测试 Engine request，始终模拟 snapshot 大滞后。

        :param snapshot: dispatch snapshot。
        :returns: 不会返回。
        :raises MemoryProjectionRepairRequired: 始终抛出 lag repair。
        """

        self.calls += 1
        policy = default_memory_projection_policy()
        raise MemoryProjectionRepairRequired(
            MemoryRepairRequest(
                session_id=snapshot.session_id,
                reason=MemoryRepairReason.SNAPSHOT_LAG_OVER_THRESHOLD,
                required_event_sequence=20,
                observed_cursor=MemorySnapshotCursor(
                    consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                    checkpoint_event_sequence=0,
                    checkpoint_event_id=None,
                    session_id=snapshot.session_id,
                ),
                policy_digest=digest_memory_projection_policy(policy),
            )
        )


class _InlineRepairViewMissingRunInputBuilder:
    """build 时抛出 inline repair view 缺失 repair。"""

    def __init__(self) -> None:
        """初始化调用计数。

        :returns: ``None``。
        """

        self.calls = 0

    def build(self, snapshot: AttemptDispatchSnapshot) -> AgentRunRequest:
        """构造测试 Engine request，模拟 compact inline repair view 缺失。

        :param snapshot: dispatch snapshot。
        :returns: 不会返回。
        :raises MemoryProjectionRepairRequired: 始终抛出 view 缺失 repair。
        """

        self.calls += 1
        policy = default_memory_projection_policy()
        raise MemoryProjectionRepairRequired(
            MemoryRepairRequest(
                session_id=snapshot.session_id,
                reason=MemoryRepairReason.INLINE_DELTA_REPAIR_VIEW_MISSING,
                required_event_sequence=20,
                observed_cursor=MemorySnapshotCursor(
                    consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                    checkpoint_event_sequence=18,
                    checkpoint_event_id="event-18",
                    session_id=snapshot.session_id,
                ),
                policy_digest=digest_memory_projection_policy(policy),
            )
        )


class _SnapshotEventHandle(_FakeHandle):
    """按 dispatch snapshot 生成单个 EngineEvent 的 handle。"""

    def __init__(self, snapshot: AttemptDispatchSnapshot, event: EngineEvent) -> None:
        """初始化 handle。

        :param snapshot: dispatch snapshot。
        :param event: 要产出的 EngineEvent。
        :returns: ``None``。
        """

        super().__init__(local_worker_id=f"worker-{snapshot.attempt_id}")
        self._event = event

    async def events(self) -> AsyncIterator[EngineEvent]:
        """产出单个事件后结束。

        :returns: EngineEvent 异步迭代器。
        """

        yield self._event


class _GatedSnapshotEventHandle(_FakeHandle):
    """等待测试同步门后再产出单个 EngineEvent 的 handle。"""

    def __init__(
        self,
        snapshot: AttemptDispatchSnapshot,
        event: EngineEvent,
        gate: asyncio.Event,
    ) -> None:
        """初始化 gated handle。

        :param snapshot: dispatch snapshot。
        :param event: 要产出的 EngineEvent。
        :param gate: 控制事件产出时机的同步门。
        :returns: ``None``。
        """

        super().__init__(local_worker_id=f"worker-{snapshot.attempt_id}")
        self._event = event
        self._gate = gate

    async def events(self) -> AsyncIterator[EngineEvent]:
        """等待同步门打开后产出单个事件。

        :returns: EngineEvent 异步迭代器。
        """

        await self._gate.wait()
        yield self._event


class _ReactiveRecoveryWorker:
    """第一轮产出 reactive overflow，第二轮产出 final answer。"""

    def __init__(self, factory: "_ReactiveRecoveryWorkerFactory") -> None:
        """初始化 worker。

        :param factory: 所属 factory。
        :returns: ``None``。
        """

        self._factory = factory

    async def accept(self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest) -> LocalWorkerHandle:
        """按创建顺序返回 reactive 或 final handle。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: scripted handle。
        """

        self._factory.accepted_snapshots.append(snapshot)
        self._factory.accepted_requests.append(request)
        if len(self._factory.accepted_snapshots) == 1:
            event = EngineEvent(
                occurred_at=_NOW,
                session_id=snapshot.session_id,
                run_id=snapshot.run_id,
                type=EngineEventType.CONTEXT_COMPACTION_REQUESTED,
                data=ContextCompactionRequestedData(
                    iteration_id="iter-reactive",
                    budget_state=None,
                    reason="provider_overflow",
                    provider_request_id="req-reactive",
                ),
                metadata=None,
            )
            if self._factory.first_event_gate is not None:
                return _GatedSnapshotEventHandle(
                    snapshot,
                    event,
                    self._factory.first_event_gate,
                )
        elif self._factory.final_blocks:
            return _ControlledBlockingHandle()
        else:
            event = EngineEvent(
                occurred_at=_NOW,
                session_id=snapshot.session_id,
                run_id=snapshot.run_id,
                type=EngineEventType.FINAL_ANSWER,
                data=FinalAnswerData(
                    content="recovered",
                    filtered=False,
                    degraded=False,
                    finish_reason=FinishReason.STOP,
                    response_identity=(_successful_response_identity_for_agent_request(request)),
                ),
                metadata=None,
            )
        return _SnapshotEventHandle(snapshot, event)


class _ReactiveRecoveryWorkerFactory:
    """测试 reactive recovery dispatch 的 worker factory。"""

    def __init__(
        self,
        *,
        final_blocks: bool = False,
        first_event_gate: asyncio.Event | None = None,
    ) -> None:
        """初始化 factory。

        :param final_blocks: recovery Attempt 是否阻塞不产出 terminal。
        :param first_event_gate: 第一轮 reactive 事件产出前等待的同步门。
        :returns: ``None``。
        """

        self.final_blocks = final_blocks
        self.first_event_gate = first_event_gate
        self.created = 0
        self.accepted_snapshots: list[AttemptDispatchSnapshot] = []
        self.accepted_requests: list[AgentRunRequest] = []

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建 scripted worker。

        :param snapshot: dispatch snapshot。
        :returns: scripted worker。
        """

        del snapshot
        self.created += 1
        return _ReactiveRecoveryWorker(self)


class _RepeatedReactiveOverflowHandle(_FakeHandle):
    """每次 dispatch 后立即产出 reactive overflow 的 fake handle。"""

    def __init__(
        self,
        snapshot: AttemptDispatchSnapshot,
        overflow_index: int,
        factory: "_RepeatedReactiveOverflowWorkerFactory",
    ) -> None:
        """初始化 repeated-overflow handle。

        :param snapshot: 当前 dispatch snapshot。
        :param overflow_index: 当前 factory accept 序号，从 1 开始。
        :param factory: 所属 factory，用于记录 close 同步点。
        :returns: ``None``。
        """

        super().__init__(local_worker_id=f"worker-overflow-{overflow_index}")
        self._snapshot = snapshot
        self._overflow_index = overflow_index
        self._factory = factory

    async def events(self) -> AsyncIterator[EngineEvent]:
        """立即产出单个 reactive overflow EngineEvent。

        :returns: 只包含一个 ``CONTEXT_COMPACTION_REQUESTED`` 的异步迭代器。
        """

        yield EngineEvent(
            occurred_at=_NOW,
            session_id=self._snapshot.session_id,
            run_id=self._snapshot.run_id,
            type=EngineEventType.CONTEXT_COMPACTION_REQUESTED,
            data=ContextCompactionRequestedData(
                iteration_id=f"iter-reactive-{self._overflow_index}",
                budget_state=None,
                reason="provider_overflow",
                provider_request_id=f"req-reactive-{self._overflow_index}",
            ),
            metadata=None,
        )

    async def close(self) -> None:
        """记录 handle close，作为该次 overflow 已被 scheduler 收口的同步点。

        :returns: ``None``。
        """

        await super().close()
        await self._factory.record_closed()


class _RepeatedReactiveOverflowWorker:
    """每次 accept 都返回 repeated-overflow handle 的 fake worker。"""

    def __init__(self, factory: "_RepeatedReactiveOverflowWorkerFactory") -> None:
        """初始化 fake worker。

        :param factory: 所属 factory。
        :returns: ``None``。
        """

        self._factory = factory

    async def accept(self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest) -> LocalWorkerHandle:
        """记录 dispatch accept，并返回立即 overflow 的 handle。

        :param snapshot: 当前 dispatch snapshot。
        :param request: 当前 Engine request。
        :returns: repeated-overflow handle。
        """

        accepted_index = await self._factory.record_accept(snapshot, request)
        return _RepeatedReactiveOverflowHandle(snapshot, accepted_index, self._factory)


class _RepeatedReactiveOverflowWorkerFactory:
    """连续 reactive overflow dispatch-loop 的确定性 fake factory。"""

    def __init__(self) -> None:
        """初始化 fake factory。

        :returns: ``None``。
        """

        self.created = 0
        self.accepted_snapshots: list[AttemptDispatchSnapshot] = []
        self.accepted_requests: list[AgentRunRequest] = []
        self.closed_count = 0
        self._accepted_condition = asyncio.Condition()
        self._closed_condition = asyncio.Condition()

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建 repeated-overflow worker。

        :param snapshot: 当前 dispatch snapshot。
        :returns: repeated-overflow worker。
        """

        del snapshot
        self.created += 1
        return _RepeatedReactiveOverflowWorker(self)

    async def record_accept(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> int:
        """记录一次 worker accept 并唤醒测试同步点。

        :param snapshot: 当前 dispatch snapshot。
        :param request: 当前 Engine request。
        :returns: 本次 accept 序号，从 1 开始。
        """

        async with self._accepted_condition:
            self.accepted_snapshots.append(snapshot)
            self.accepted_requests.append(request)
            accepted_index = len(self.accepted_snapshots)
            self._accepted_condition.notify_all()
            return accepted_index

    async def record_closed(self) -> None:
        """记录一次 handle close 并唤醒测试同步点。

        :returns: ``None``。
        """

        async with self._closed_condition:
            self.closed_count += 1
            self._closed_condition.notify_all()

    async def wait_for_accepted_count(self, expected_count: int) -> None:
        """等待 factory 观察到指定 accept 次数。

        :param expected_count: 期望 accept 次数。
        :returns: ``None``。
        :raises TimeoutError: 超时仍未达到期望次数时抛出。
        """

        await asyncio.wait_for(
            self._wait_for_accepted_count(expected_count),
            timeout=_REPEATED_OVERFLOW_SYNC_TIMEOUT_SECONDS,
        )

    async def wait_for_closed_count(self, expected_count: int) -> None:
        """等待 factory 观察到指定 handle close 次数。

        :param expected_count: 期望 close 次数。
        :returns: ``None``。
        :raises TimeoutError: 超时仍未达到期望次数时抛出。
        """

        await asyncio.wait_for(
            self._wait_for_closed_count(expected_count),
            timeout=_REPEATED_OVERFLOW_SYNC_TIMEOUT_SECONDS,
        )

    async def _wait_for_accepted_count(self, expected_count: int) -> None:
        """在 condition 上等待 accept 次数达标。

        :param expected_count: 期望 accept 次数。
        :returns: ``None``。
        """

        async with self._accepted_condition:
            await self._accepted_condition.wait_for(lambda: len(self.accepted_snapshots) >= expected_count)

    async def _wait_for_closed_count(self, expected_count: int) -> None:
        """在 condition 上等待 handle close 次数达标。

        :param expected_count: 期望 close 次数。
        :returns: ``None``。
        """

        async with self._closed_condition:
            await self._closed_condition.wait_for(lambda: self.closed_count >= expected_count)


class _FinalAnswerWorker:
    """接受请求后立即返回 final_answer 的 fake worker。"""

    def __init__(self, factory: "_FinalAnswerWorkerFactory") -> None:
        """初始化 worker。

        :param factory: 所属 factory。
        :returns: ``None``。
        """

        self._factory = factory

    async def accept(self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest) -> LocalWorkerHandle:
        """记录请求并返回 final_answer handle。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: scripted final answer handle。
        """

        self._factory.accepted_snapshots.append(snapshot)
        self._factory.accepted_requests.append(request)
        return _SnapshotEventHandle(
            snapshot,
            EngineEvent(
                occurred_at=_NOW,
                session_id=snapshot.session_id,
                run_id=snapshot.run_id,
                type=EngineEventType.FINAL_ANSWER,
                data=FinalAnswerData(
                    content=f"final:{snapshot.run_id}",
                    filtered=False,
                    degraded=False,
                    finish_reason=FinishReason.STOP,
                    response_identity=(_successful_response_identity_for_agent_request(request)),
                ),
                metadata=None,
            ),
        )


class _FinalAnswerWorkerFactory:
    """按真实 dispatch 接受顺序记录 Engine request 的 fake factory。"""

    def __init__(self) -> None:
        """初始化 factory。

        :returns: ``None``。
        """

        self.created = 0
        self.accepted_snapshots: list[AttemptDispatchSnapshot] = []
        self.accepted_requests: list[AgentRunRequest] = []

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建 final answer worker。

        :param snapshot: dispatch snapshot。
        :returns: fake worker。
        """

        del snapshot
        self.created += 1
        return _FinalAnswerWorker(self)


class _CountingTool:
    """测试用业务工具 callable。"""

    def __init__(self) -> None:
        """初始化测试工具。

        :returns: ``None``。
        """

        self.call_count = 0

    async def __call__(self, call: ToolCallRequest, context: BatchToolExecutionContext) -> ToolExecutionOutcome:
        """返回当前调用参数并记录调用次数。

        :param call: 工具调用请求。
        :param context: 批式工具执行上下文。
        :returns: 工具成功 outcome。
        """

        del context
        self.call_count += 1
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value={"arguments": call.arguments},
                meta=None,
            )
        )


class _EnqueueOnSecondEmptyQueue(asyncio.Queue[PendingDispatchRecord]):
    """在第二次 empty 检查后注入一条 dispatch，用于复现 wakeup 窗口。"""

    def __init__(self, injected_record: PendingDispatchRecord) -> None:
        """初始化测试队列。

        :param injected_record: 第二次 empty 检查时注入的 dispatch 摘要。
        :returns: ``None``。
        """

        super().__init__()
        self._injected_record = injected_record
        self._empty_calls = 0

    def empty(self) -> bool:
        """第二次 empty 仍返回 True，但在返回前模拟并发入队。

        :returns: 当前测试队列是否报告为空。
        """

        self._empty_calls += 1
        if self._empty_calls == 2:
            self.put_nowait(self._injected_record)
            return True
        return super().empty()


class _ObservedEmptyQueue(asyncio.Queue[PendingDispatchRecord]):
    """记录 empty 检查的测试队列。"""

    def __init__(self, *, target_empty_checks: int = 1) -> None:
        """初始化测试队列。

        :param target_empty_checks: 触发 ``empty_checked`` 的 empty 检查次数。
        :returns: ``None``。
        """

        super().__init__()
        self.empty_checked = asyncio.Event()
        self.empty_call_count = 0
        self._target_empty_checks = target_empty_checks

    def empty(self) -> bool:
        """记录 empty 检查并返回真实队列状态。

        :returns: 当前队列是否为空。
        """

        self.empty_call_count += 1
        if self.empty_call_count >= self._target_empty_checks:
            self.empty_checked.set()
        return super().empty()


class _CancelBeforePreAcceptRecheck:
    """在 scheduler pre-accept recheck 前注入 durable cancel 的测试 callable。"""

    def __init__(
        self,
        *,
        transaction_runner: HostTransactionRunner,
        seeded: _SeededRun,
        original_recheck: Callable[[DispatchRecordRow], bool],
    ) -> None:
        """初始化 cancel race 注入器。

        :param transaction_runner: Host transaction runner。
        :param seeded: seeded run。
        :param original_recheck: scheduler 原始 pre-accept recheck。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner
        self._seeded = seeded
        self._original_recheck = original_recheck

    def __call__(self, dispatch_record: DispatchRecordRow) -> bool:
        """注入 cancel race 后执行原始 pre-accept recheck。

        :param dispatch_record: 当前 dispatching row。
        :returns: 原始 pre-accept recheck 结果。
        """

        _cancel_predispatch_dispatching(self._transaction_runner, self._seeded)
        return self._original_recheck(dispatch_record)


class _FailingDrainLoopScheduler(HostDispatchScheduler):
    """测试用 drain_once 崩溃 scheduler。"""

    async def drain_once(self) -> DispatchDrainResult:
        """模拟 drain_once 未预期异常。

        :returns: 不会返回。
        :raises RuntimeError: 始终抛出测试异常。
        """

        raise RuntimeError("drain failure")


class _RetryOnceDrainLoopScheduler(HostDispatchScheduler):
    """测试用首次 retry exhausted、随后成功 reconcile 的 scheduler。"""

    _drain_call_count: int
    _retry_seen: asyncio.Event
    _reconciled: asyncio.Event
    _reconcile_hold: asyncio.Event

    def configure_retry_probe(
        self,
        *,
        retry_seen: asyncio.Event,
        reconciled: asyncio.Event,
    ) -> None:
        """配置 deterministic retry 观测事件。

        :param retry_seen: 首次 retry exhausted 时置位。
        :param reconciled: 下一次 drain 成功时置位。
        :returns: ``None``。
        """

        self._drain_call_count = 0
        self._retry_seen = retry_seen
        self._reconciled = reconciled
        self._reconcile_hold = asyncio.Event()

    async def drain_once(self) -> DispatchDrainResult:
        """首次抛 retry exhausted，下一轮记录 reconcile 成功。

        :returns: retry 后的空 drain 结果。
        :raises HostTransactionRetryExhaustedError: 首次调用固定抛出。
        """

        self._drain_call_count += 1
        if self._drain_call_count == 1:
            self._retry_seen.set()
            raise HostTransactionRetryExhaustedError(
                "drain retry exhausted",
                attempts=3,
            )
        self._reconciled.set()
        await self._reconcile_hold.wait()
        return DispatchDrainResult(
            processed=0,
            dispatched=0,
            skipped=0,
            timed_out=0,
        )


class _LevelTriggeredActiveCancelWatchdogScheduler(HostDispatchScheduler):
    """记录 Event clear/set 与 tick 次数的 watchdog scheduler。"""

    _tick_count: int
    _first_tick_seen: asyncio.Event
    _second_tick_seen: asyncio.Event
    _wake_during_first_tick: bool
    _event_states_before_tick: list[bool]
    _event_state_after_nested_wake: bool | None

    def configure_level_trigger_probe(
        self,
        *,
        first_tick_seen: asyncio.Event,
        second_tick_seen: asyncio.Event,
        wake_during_first_tick: bool,
    ) -> None:
        """配置 deterministic level-triggered 观测点。

        :param first_tick_seen: 第一轮 tick 观测事件。
        :param second_tick_seen: 第二轮 tick 观测事件。
        :param wake_during_first_tick: 是否在第一轮 tick barrier 内再次 wake。
        :returns: ``None``。
        """

        self._tick_count = 0
        self._first_tick_seen = first_tick_seen
        self._second_tick_seen = second_tick_seen
        self._wake_during_first_tick = wake_during_first_tick
        self._event_states_before_tick = []
        self._event_state_after_nested_wake = None

    def tick_active_cancel_watchdog_for_session(
        self,
        session_id: str,
        now: datetime,
    ) -> host_dispatch.ActiveCancelWatchdogTickResult:
        """记录 tick 前 event 已 clear，并可在第一轮内注入第二次 wake。

        :param session_id: target watchdog 的 Session id。
        :param now: watchdog tick 的当前时间。
        :returns: 空扫描 tick 结果。
        :raises Exception: 不主动抛出异常。
        """

        assert session_id == "session-watchdog-probe"
        _ = now
        self._tick_count += 1
        self._event_states_before_tick.append(self._active_cancel_watchdog_event.is_set())
        if self._tick_count == 1:
            self._first_tick_seen.set()
            if self._wake_during_first_tick:
                self.wake_active_cancel_watchdog(session_id)
                self._event_state_after_nested_wake = self._active_cancel_watchdog_event.is_set()
        elif self._tick_count == 2:
            self._second_tick_seen.set()
        return host_dispatch.ActiveCancelWatchdogTickResult(
            scanned=0,
            eligible=0,
            closed=0,
            ignored=0,
        )


class _FailingActiveCancelWatchdogScheduler(HostDispatchScheduler):
    """测试用 active cancel watchdog fatal tick scheduler。"""

    def tick_active_cancel_watchdog_for_session(
        self,
        session_id: str,
        now: datetime,
    ) -> host_dispatch.ActiveCancelWatchdogTickResult:
        """固定抛出 watchdog unexpected failure。

        :param session_id: target watchdog 的 Session id。
        :param now: watchdog tick 的当前时间。
        :returns: 不会返回。
        :raises RuntimeError: 始终抛出测试异常。
        """

        assert session_id == "session-watchdog-probe"
        _ = now
        raise RuntimeError("active cancel watchdog private failure")


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ("factory", "bind"))
async def test_scheduler_terminal_port_failure_closes_each_owner_once_without_tasks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    """factory/bind failure 在零 critical task 状态各清理 coordinator 与 lane 一次。"""

    terminal_factory = _FailingTerminalPortFactory(fail_create=failure_stage == "factory")
    lane_close_calls = 0
    original_lane_close = LaneController.close

    async def record_lane_close(
        self: LaneController,
        reason: str | None = None,
    ) -> None:
        """记录 lane owner cleanup。

        :param self: lane controller。
        :param reason: close reason。
        :returns: ``None``。
        :raises Exception: 原始 lane close 失败时透传。
        """

        nonlocal lane_close_calls
        lane_close_calls += 1
        await original_lane_close(self, reason=reason)

    if failure_stage == "bind":

        def fail_bind(
            self: HostDispatchScheduler,
            terminal_post_commit_port: TerminalPostCommitPort,
        ) -> None:
            """在 construction-only bind 阶段注入失败。

            :param self: 尚未启动 scheduler。
            :param terminal_post_commit_port: factory 已创建的最终 port。
            :returns: 不会返回。
            :raises RuntimeError: 始终抛出。
            """

            del self, terminal_post_commit_port
            raise RuntimeError("injected terminal port bind failure")

        monkeypatch.setattr(
            HostDispatchScheduler,
            "_bind_terminal_post_commit_port",
            fail_bind,
        )
    monkeypatch.setattr(LaneController, "close", record_lane_close)

    with open_host_durable_store(_options(tmp_path)) as store:
        with pytest.raises(RuntimeError, match="terminal"):
            await _open_scheduler(
                tmp_path,
                store,
                _FakeWorkerFactory(),
                terminal_port_factory=terminal_factory,
            )

    scheduler = terminal_factory.scheduler
    assert scheduler is not None
    assert terminal_factory.create_calls == 1
    assert terminal_factory.close_calls == 1
    assert lane_close_calls == 1
    assert scheduler._heartbeat_task is None
    assert scheduler._active_cancel_watchdog_task is None
    assert scheduler._drain_task is None
    assert scheduler._promotion_drain_task is None
    assert scheduler._active_tasks == set()
    assert scheduler._active_handles == set()
    assert scheduler._closed is True
    assert scheduler._close_cleanup_done is True


async def _open_watchdog_probe_scheduler(
    tmp_path: Path,
    store: HostDurableStore,
    scheduler_type: type[HostDispatchScheduler],
    *,
    suffix: str,
) -> HostDispatchScheduler:
    """打开不受 periodic timeout 干扰的 watchdog probe scheduler。

    :param tmp_path: pytest 临时目录。
    :param store: scheduler durable store。
    :param scheduler_type: 待实例化 scheduler 类型。
    :param suffix: lane/handle 隔离后缀。
    :returns: 已构造但仅按显式 wake 启动 watchdog 的 scheduler。
    :raises Exception: lane controller 打开失败时透传。
    """

    lane_db_path = tmp_path / f"lane-active-cancel-{suffix}.sqlite3"
    lane_controller = await LaneController.open(
        [
            LaneConfig(
                name=_LANE_NAME,
                capacity=1,
                default_timeout_seconds=0.1,
                claim_ttl_seconds=1.0,
                heartbeat_interval_seconds=0.1,
            )
        ],
        coordinator=SQLiteLaneCoordinatorConfig(db_path=lane_db_path),
    )
    return scheduler_type(
        transaction_runner=store.transaction_runner,
        transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        terminal_post_commit_port=_RecordingTerminalPort(),
        event_log_store=EventLogStore(),
        local_execution=HostLocalExecutionOptions(
            lane_db_path=lane_db_path,
            lane_name=_LANE_NAME,
            lane_capacity=1,
            lane_default_timeout_seconds=0.1,
            lane_claim_ttl_seconds=1.0,
            lane_heartbeat_interval_seconds=0.1,
            worker_startup_timeout_seconds=1.0,
            dispatch_poll_interval_seconds=60.0,
            runner_spec=_runner_spec(),
            runner_options=RunnerCallOptions(
                temperature=None,
                max_tokens=None,
                top_p=None,
                stream=False,
            ),
            agent_policy=_agent_policy(False),
            worker_factory=_FakeWorkerFactory(),
        ),
        lane_controller=lane_controller,
        host_handle_id=f"host-active-cancel-{suffix}",
        session_new_work_access=ExplicitFakeSessionAccess(
            allowed_session_ids=None,
        ),
    )


class _CloseWorkerLostFailingIngestor:
    """测试用 close_worker_lost 失败 ingestor。"""

    def close_worker_lost(
        self,
        envelope: LocalEngineEnvelope,
        *,
        observed_at: datetime,
        worker_lifecycle_signal: str,
        stream_error_code: str,
        last_observed_worker_event_index: int,
        last_accepted_event_id: str | None,
    ) -> EngineIngestResult:
        """模拟 lost closeout 写入失败。

        :param envelope: worker envelope。
        :param observed_at: Host 观察时间。
        :param worker_lifecycle_signal: worker lifecycle signal。
        :param stream_error_code: 原始异常类型名。
        :param last_observed_worker_event_index: 最后观测到的 worker event index。
        :param last_accepted_event_id: 最后已接受 EventLog id。
        :returns: 不会返回。
        :raises RuntimeError: 始终抛出 closeout 失败。
        """

        del (
            envelope,
            observed_at,
            worker_lifecycle_signal,
            stream_error_code,
            last_observed_worker_event_index,
            last_accepted_event_id,
        )
        raise RuntimeError("close worker lost failed")


class _FailingCloseWorkerHandle:
    """关闭时抛错的 worker handle fake。"""

    @property
    def local_worker_id(self) -> str:
        """返回 fake worker id。

        :returns: fake worker id。
        """

        return "worker-close-fails"

    def events(self) -> AsyncIterator[EngineEvent]:
        """返回空事件流。

        :returns: 空异步迭代器。
        """

        return _empty_engine_events()

    async def close(self) -> None:
        """模拟 worker handle close 失败。

        :returns: 不返回。
        :raises RuntimeError: 始终抛出 close 失败。
        """

        raise RuntimeError("worker close failed")

    def on_cancel(self, reason: str) -> None:
        """忽略取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason


class _FailingLaneToken:
    """释放时抛错的 lane token fake。"""

    name = _LANE_NAME
    claim_id = "claim-release-fails"

    async def release(self) -> None:
        """模拟 lane token release 失败。

        :returns: 不返回。
        :raises RuntimeError: 始终抛出 release 失败。
        """

        raise RuntimeError("lane release failed")


async def _empty_engine_events() -> AsyncIterator[EngineEvent]:
    """返回空 EngineEvent 异步流。

    :returns: 空异步迭代器。
    """

    if False:
        yield _unreachable_engine_event()


def test_scheduler_close_lifecycle_matrix_covers_slice_b_windows() -> None:
    """close lifecycle matrix 必须覆盖 Slice B 要求的窗口。

    :returns: ``None``。
    :raises AssertionError: matrix 缺失必要场景或字段为空时抛出。
    """

    required_ids = {
        "cancel-all-after-register",
        "dispatch-queue-non-empty-close",
        "promotion-queue-non-empty-close",
        "lane-wait-pre-worker-close",
        "worker-accepted-before-consumer-start-close",
        "close-cancelled-mid-cleanup-retry",
    }
    actual_ids = {item.scenario_id for item in _SCHEDULER_CLOSE_LIFECYCLE_MATRIX}

    assert required_ids <= actual_ids
    assert {item.coverage_classification for item in _SCHEDULER_CLOSE_LIFECYCLE_MATRIX} == {
        "existing",
        "new",
        "non-goal",
    }
    for item in _SCHEDULER_CLOSE_LIFECYCLE_MATRIX:
        assert item.window.strip() != ""
        assert item.expected_close_action.strip() != ""
        assert item.expected_durable_mutation.strip() != ""
        assert item.expected_resource_cleanup.strip() != ""


def test_active_worker_registry_cancel_all_uses_snapshot_when_entry_registers_after_cancel() -> None:
    """``cancel_all`` 只取消调用开始时的 active entry 快照。

    :returns: ``None``。
    """

    registry = ActiveWorkerRegistry()
    first_token = _HostCancellationToken()
    second_token = _HostCancellationToken()
    second_handle = _FakeHandle()
    first_handle = _RegisteringCancelHandle(
        registry=registry,
        second_token=second_token,
        second_handle=second_handle,
    )
    registry.register(
        session_id="session-first",
        run_id="run-first",
        attempt_id="attempt-first",
        execution_id="execution-first",
        handle=first_handle,
        cancellation_token=first_token,
    )

    first_count = registry.cancel_all(_SCHEDULER_CLOSE_REASON)

    assert first_count == 1
    assert first_token.is_cancelled() is True
    assert first_token.cancel_reason() == _SCHEDULER_CLOSE_REASON
    assert first_handle.cancel_reasons == [_SCHEDULER_CLOSE_REASON]
    assert second_token.is_cancelled() is False

    second_count = registry.cancel_all(_SCHEDULER_CLOSE_REASON)

    assert second_count == 2
    assert second_token.is_cancelled() is True
    assert second_token.cancel_reason() == _SCHEDULER_CLOSE_REASON


@pytest.mark.asyncio
async def test_pending_waiting_dispatching_worker_accept_marks_running(
    tmp_path: Path,
) -> None:
    """pending dispatch 可推进到 worker accepted，Attempt 进入 RUNNING。"""

    factory = _FakeWorkerFactory(accepted_handle=_CloseCountingHandle())
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()

            run, attempt, dispatch_record = _read_rows(store.transaction_runner, seeded)
            event = _read_event_by_type(store.transaction_runner, "ATTEMPT_RUNNING")
            assert result.processed == 1
            assert result.dispatched == 1
            assert run.status == RunStatus.RUNNING
            assert attempt.status == AttemptStatus.RUNNING
            assert dispatch_record.status == DispatchRecordStatus.DISPATCHING
            assert dispatch_record.worker_accept_event_id == event.event_id
            payload = json.loads(event.payload_json)
            assert payload["local_worker_id"] == "local-worker-test"
            assert payload["worker_accepted_at"] == dispatch_record.worker_accepted_at
            assert payload["lane_name"] == _LANE_NAME
            assert payload["lane_claim_id"] == dispatch_record.lane_claim_id
            assert factory.accepted_snapshots[0].dispatch_record_id == seeded.dispatch_record_id
            assert factory.accepted_requests[0].disable_tools is True
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_dispatch_checkpoint_covered_catchup_accepts_ordinary_run_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """checkpoint 已覆盖 required cursor 时 dispatch 继续接受 ordinary worker。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: dispatch 走到 lag fail-closed、recovery 或未构造
        ordinary RunInput 时抛出。
    """

    policy = default_memory_projection_policy()
    observed_catchups: list[ConversationMemoryProjectionRepairResult] = []
    factory = _FakeWorkerFactory(accepted_handle=_CloseCountingHandle())
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        _, seeded_attempt, _ = _read_rows(store.transaction_runner, seeded)
        required_event_sequence = seeded_attempt.started_event_sequence - 1
        prewarmed = catch_up_conversation_memory_projection(
            store.transaction_runner,
            policy=policy,
            batch_size=32,
            max_event_sequence=required_event_sequence,
        )
        checkpoint_before_dispatch = _read_memory_checkpoint_sequence(store.transaction_runner)

        def _observed_catch_up(
            transaction_runner: HostTransactionRunner,
            *,
            policy: MemoryProjectionPolicy,
            batch_size: int,
            consumer_id: str = CONVERSATION_MEMORY_CONSUMER_ID,
            max_event_sequence: int | None = None,
        ) -> ConversationMemoryProjectionRepairResult:
            """调用真实 catch-up 并记录 dispatch 内部返回值。

            :param transaction_runner: Host transaction runner。
            :param policy: memory projection policy。
            :param batch_size: 每批扫描事件数。
            :param consumer_id: projection consumer id。
            :param max_event_sequence: 本次最多追到的 EventLog sequence。
            :returns: 真实 catch-up 返回值。
            """

            result = catch_up_conversation_memory_projection(
                transaction_runner,
                policy=policy,
                batch_size=batch_size,
                consumer_id=consumer_id,
                max_event_sequence=max_event_sequence,
            )
            observed_catchups.append(result)
            return result

        assert prewarmed.target_reached is True
        assert prewarmed.finished_cursor == required_event_sequence
        assert checkpoint_before_dispatch == required_event_sequence

        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            lane_default_timeout_seconds=1.0,
        )
        monkeypatch.setattr(
            host_dispatch,
            "catch_up_conversation_memory_projection",
            _observed_catch_up,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()

            run, attempt, dispatch_record = _read_rows(store.transaction_runner, seeded)
            checkpoint_after_dispatch = _read_memory_checkpoint_sequence(store.transaction_runner)
            assert len(observed_catchups) == 1
            assert len(factory.accepted_snapshots) == 1
            assert len(factory.accepted_requests) == 1
            dispatch_catchup = observed_catchups[0]
            accepted_contents = tuple(
                content
                for content in (_message_text(message) for message in factory.accepted_requests[0].messages)
                if content is not None
            )
            assert result.dispatched == 1
            assert dispatch_catchup.started_cursor == required_event_sequence
            assert dispatch_catchup.finished_cursor == required_event_sequence
            assert dispatch_catchup.events_scanned == 0
            assert dispatch_catchup.target_reached is True
            assert checkpoint_after_dispatch == checkpoint_before_dispatch
            assert run.status == RunStatus.RUNNING
            assert attempt.status == AttemptStatus.RUNNING
            assert dispatch_record.status == DispatchRecordStatus.DISPATCHING
            assert factory.accepted_requests[0].disable_tools is True
            assert accepted_contents[-1] == "dispatch prompt"
            assert _event_count(store.transaction_runner, "RUN_FAILED") == 0
            assert _event_count(store.transaction_runner, "RUN_RECOVERING") == 0
            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 1
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_dispatch_lag_repair_rebuild_not_reached_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """验证 rebuild 未达 required cursor 时 dispatch fail-closed。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :param caplog: pytest 日志捕获 fixture。
    :returns: ``None``。
    :raises AssertionError: scheduler 未按 fail-closed 语义收口时抛出。
    """

    caplog.set_level(logging.WARNING, logger="dayu.host.dispatch")
    factory = _FakeWorkerFactory(accepted_handle=_ControlledBlockingHandle())
    builder = _LagRepairRunInputBuilder()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            lane_default_timeout_seconds=1.0,
        )

        def _noop_catch_up(record: PendingDispatchRecord) -> None:
            """跳过 dispatch 预构建 catch-up，让 builder 暴露 lag repair。

            :param record: pending dispatch 摘要。
            :returns: ``None``。
            """

            del record

        def _fake_builder_for_dispatch(
            *,
            snapshot: AttemptDispatchSnapshot,
            policy_snapshot: PolicySnapshot,
            effective_tool_facts: EffectiveToolFacts,
        ) -> AgentRunRequest:
            """返回会先抛 lag repair 的测试 builder。

            :param snapshot: dispatch snapshot。
            :param policy_snapshot: 冻结 policy snapshot。
            :param effective_tool_facts: 冻结 effective tool facts。
            :returns: 测试 builder。
            """

            del policy_snapshot, effective_tool_facts
            return builder.build(snapshot)

        monkeypatch.setattr(
            scheduler,
            "_catch_up_memory_projection_before_worker",
            _noop_catch_up,
        )
        monkeypatch.setattr(
            scheduler,
            "_build_frozen_run_input",
            _fake_builder_for_dispatch,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()

            run, attempt, dispatch_record = _read_rows(store.transaction_runner, seeded)
            assert result.dispatched == 0
            assert result.timed_out == 1
            assert builder.calls == 1
            assert factory.created == 0
            assert run.status == RunStatus.FAILED
            assert attempt.status == AttemptStatus.FAILED
            assert dispatch_record.status == DispatchRecordStatus.CANCELLED
            assert _event_count(store.transaction_runner, "RUN_FAILED") == 1
            assert _event_count(store.transaction_runner, "RUN_RECOVERING") == 0
            assert "dispatch.worker_accept.failed" in caplog.text
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_inline_repair_view_missing_does_not_rebuild_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """inline repair view 缺失不得触发大滞后 rebuild retry。"""

    factory = _FakeWorkerFactory(accepted_handle=_ControlledBlockingHandle())
    builder = _InlineRepairViewMissingRunInputBuilder()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            lane_default_timeout_seconds=1.0,
        )

        def _noop_catch_up(record: PendingDispatchRecord) -> None:
            """跳过 dispatch 预构建 catch-up，让 builder 暴露 repair reason。

            :param record: pending dispatch 摘要。
            :returns: ``None``。
            """

            del record

        def _fake_builder_for_dispatch(
            *,
            snapshot: AttemptDispatchSnapshot,
            policy_snapshot: PolicySnapshot,
            effective_tool_facts: EffectiveToolFacts,
        ) -> AgentRunRequest:
            """返回会抛 view 缺失 repair 的测试 builder。

            :param snapshot: dispatch snapshot。
            :param policy_snapshot: 冻结 policy snapshot。
            :param effective_tool_facts: 冻结 effective tool facts。
            :returns: 测试 builder。
            """

            del policy_snapshot, effective_tool_facts
            return builder.build(snapshot)

        monkeypatch.setattr(
            scheduler,
            "_catch_up_memory_projection_before_worker",
            _noop_catch_up,
        )
        monkeypatch.setattr(
            scheduler,
            "_build_frozen_run_input",
            _fake_builder_for_dispatch,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()

            assert result.timed_out == 1
            assert builder.calls == 1
            assert factory.created == 0
            assert _event_count(store.transaction_runner, "RUN_FAILED") == 1
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_memory_lag_pre_dispatch_failure_does_not_enter_recovering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """验证 pre-dispatch memory lag repair 失败不进入 RECOVERING。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: Run 进入 recovery 或未 fail-closed 时抛出。
    """

    factory = _FakeWorkerFactory(accepted_handle=_ControlledBlockingHandle())
    builder = _LagRepairRunInputBuilder()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)

        def _noop_catch_up(record: PendingDispatchRecord) -> None:
            """跳过 catch-up 以触发 builder lag repair 分支。

            :param record: pending dispatch 摘要。
            :returns: ``None``。
            """

            del record

        def _fake_builder_for_dispatch(
            *,
            snapshot: AttemptDispatchSnapshot,
            policy_snapshot: PolicySnapshot,
            effective_tool_facts: EffectiveToolFacts,
        ) -> AgentRunRequest:
            """返回测试 builder。

            :param snapshot: dispatch snapshot。
            :param policy_snapshot: policy snapshot。
            :param effective_tool_facts: 冻结 effective tool facts。
            :returns: 测试 builder。
            """

            del policy_snapshot, effective_tool_facts
            return builder.build(snapshot)

        monkeypatch.setattr(
            scheduler,
            "_catch_up_memory_projection_before_worker",
            _noop_catch_up,
        )
        monkeypatch.setattr(
            scheduler,
            "_build_frozen_run_input",
            _fake_builder_for_dispatch,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            await scheduler.drain_once()

            assert _event_count(store.transaction_runner, "RUN_RECOVERING") == 0
            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 1
            assert _run_status(store.transaction_runner, seeded.run_id) == RunStatus.FAILED
            assert _event_count(store.transaction_runner, "RUN_FAILED") == 1
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_persistent_memory_lag_repair_failure_closes_starting_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """验证持续 memory lag repair failure 关闭 STARTING Run。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: Run / Attempt / dispatch record 未正确收口时抛出。
    """

    factory = _FakeWorkerFactory(accepted_handle=_ControlledBlockingHandle())
    builder = _PersistentLagRepairRunInputBuilder()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            lane_default_timeout_seconds=1.0,
        )

        def _noop_catch_up(record: PendingDispatchRecord) -> None:
            """跳过 catch-up 以触发 builder lag repair 分支。

            :param record: pending dispatch 摘要。
            :returns: ``None``。
            """

            del record

        def _fake_builder_for_dispatch(
            *,
            snapshot: AttemptDispatchSnapshot,
            policy_snapshot: PolicySnapshot,
            effective_tool_facts: EffectiveToolFacts,
        ) -> AgentRunRequest:
            """返回持续 lag repair 的测试 builder。

            :param snapshot: dispatch snapshot。
            :param policy_snapshot: policy snapshot。
            :param effective_tool_facts: 冻结 effective tool facts。
            :returns: 测试 builder。
            """

            del policy_snapshot, effective_tool_facts
            return builder.build(snapshot)

        monkeypatch.setattr(
            scheduler,
            "_catch_up_memory_projection_before_worker",
            _noop_catch_up,
        )
        monkeypatch.setattr(
            scheduler,
            "_build_frozen_run_input",
            _fake_builder_for_dispatch,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()

            run, attempt, dispatch_record = _read_rows(store.transaction_runner, seeded)
            assert result.timed_out == 1
            assert builder.calls == 1
            assert factory.created == 0
            assert run.status == RunStatus.FAILED
            assert attempt.status == AttemptStatus.FAILED
            assert dispatch_record.status == DispatchRecordStatus.CANCELLED
            assert dispatch_record.cancelled_event_id is not None
            assert _event_count(store.transaction_runner, "RUN_RECOVERING") == 0
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_drain_loop_unexpected_exception_reports_fatal(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """drain loop 未预期异常退出并向 shared health 报告 fatal。

    :param tmp_path: pytest 临时目录。
    :param caplog: pytest 日志捕获 fixture。
    :returns: ``None``。
    """

    caplog.set_level(logging.WARNING, logger="dayu.host.dispatch")
    with open_host_durable_store(_options(tmp_path)) as store:
        lane_controller = await LaneController.open(
            [
                LaneConfig(
                    name=_LANE_NAME,
                    capacity=1,
                    default_timeout_seconds=0.1,
                    claim_ttl_seconds=1.0,
                    heartbeat_interval_seconds=0.1,
                )
            ],
            coordinator=SQLiteLaneCoordinatorConfig(db_path=tmp_path / "lane-drain-loop.sqlite3"),
        )
        scheduler = _FailingDrainLoopScheduler(
            transaction_runner=store.transaction_runner,
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            terminal_post_commit_port=_RecordingTerminalPort(),
            event_log_store=EventLogStore(),
            local_execution=HostLocalExecutionOptions(
                lane_db_path=tmp_path / "lane-drain-loop.sqlite3",
                lane_name=_LANE_NAME,
                lane_capacity=1,
                lane_default_timeout_seconds=0.1,
                lane_claim_ttl_seconds=1.0,
                lane_heartbeat_interval_seconds=0.1,
                worker_startup_timeout_seconds=1.0,
                dispatch_poll_interval_seconds=0.01,
                runner_spec=_runner_spec(),
                runner_options=RunnerCallOptions(temperature=None, max_tokens=None, top_p=None, stream=False),
                agent_policy=_agent_policy(False),
                worker_factory=_FakeWorkerFactory(),
            ),
            lane_controller=lane_controller,
            host_handle_id="host-drain-loop-log",
            session_new_work_access=ExplicitFakeSessionAccess(
                allowed_session_ids=None,
            ),
        )
        try:
            scheduler._drain_task = scheduler._start_critical_task(
                scheduler._drain_loop,
                component="dispatch",
            )
            await asyncio.wait_for(
                asyncio.shield(scheduler._drain_task),
                timeout=0.5,
            )
            assert scheduler._drain_task.done() is True
            assert scheduler._health_gate.state is HostExecutionHealthState.UNAVAILABLE
        finally:
            await scheduler.close()

    assert any("dispatch drain loop stopped unexpectedly" in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_drain_loop_retries_durable_retry_exhausted_without_self_close(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """drain retry exhausted 按 poll interval 重试且不关闭或取消 worker。

    :param tmp_path: pytest 临时目录。
    :param caplog: pytest 日志捕获 fixture。
    :returns: ``None``。
    """

    caplog.set_level(logging.WARNING, logger="dayu.host.dispatch")
    with open_host_durable_store(_options(tmp_path)) as store:
        lane_controller = await LaneController.open(
            [
                LaneConfig(
                    name=_LANE_NAME,
                    capacity=1,
                    default_timeout_seconds=0.1,
                    claim_ttl_seconds=1.0,
                    heartbeat_interval_seconds=0.1,
                )
            ],
            coordinator=SQLiteLaneCoordinatorConfig(db_path=tmp_path / "lane-drain-loop-retry-exhausted.sqlite3"),
        )
        registry = ActiveWorkerRegistry()
        active_token = _HostCancellationToken()
        registry.register(
            session_id="session-active",
            run_id="run-active",
            attempt_id="attempt-active",
            execution_id="execution-active",
            handle=_FakeHandle(),
            cancellation_token=active_token,
        )
        scheduler = _RetryOnceDrainLoopScheduler(
            transaction_runner=store.transaction_runner,
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            terminal_post_commit_port=_RecordingTerminalPort(),
            event_log_store=EventLogStore(),
            local_execution=HostLocalExecutionOptions(
                lane_db_path=tmp_path / "lane-drain-loop-retry-exhausted.sqlite3",
                lane_name=_LANE_NAME,
                lane_capacity=1,
                lane_default_timeout_seconds=0.1,
                lane_claim_ttl_seconds=1.0,
                lane_heartbeat_interval_seconds=0.1,
                worker_startup_timeout_seconds=1.0,
                dispatch_poll_interval_seconds=0.01,
                runner_spec=_runner_spec(),
                runner_options=RunnerCallOptions(temperature=None, max_tokens=None, top_p=None, stream=False),
                agent_policy=_agent_policy(False),
                worker_factory=_FakeWorkerFactory(),
            ),
            lane_controller=lane_controller,
            host_handle_id="host-drain-loop-retry-exhausted",
            active_registry=registry,
            session_new_work_access=ExplicitFakeSessionAccess(
                allowed_session_ids=None,
            ),
        )
        retry_seen = asyncio.Event()
        reconciled = asyncio.Event()
        scheduler.configure_retry_probe(
            retry_seen=retry_seen,
            reconciled=reconciled,
        )
        scheduler._drain_task = scheduler._start_critical_task(
            scheduler._drain_loop,
            component="dispatch",
        )
        await asyncio.wait_for(retry_seen.wait(), timeout=0.5)
        await asyncio.wait_for(reconciled.wait(), timeout=0.5)
        assert scheduler._drain_task.done() is False
        assert scheduler._closed is False
        assert active_token.is_cancelled() is False
        scheduler.wake_dispatch(
            PendingDispatchRecord(
                dispatch_record_id="dispatch-open",
                run_id="run-open",
                attempt_id="attempt-open",
                execution_id="execution-open",
                execution_target="target-dispatch",
                worker_kind=WorkerKind.LOCAL,
            )
        )
        await scheduler.close()

    assert any("dispatch drain loop durable retry exhausted" in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_active_cancel_watchdog_wake_during_tick_drives_second_tick(
    tmp_path: Path,
) -> None:
    """tick barrier 内第二次 wake 在 clear 后保持 set 并驱动第二轮。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        scheduler = cast(
            _LevelTriggeredActiveCancelWatchdogScheduler,
            await _open_watchdog_probe_scheduler(
                tmp_path,
                store,
                _LevelTriggeredActiveCancelWatchdogScheduler,
                suffix="second-wake",
            ),
        )
        first_tick_seen = asyncio.Event()
        second_tick_seen = asyncio.Event()
        scheduler.configure_level_trigger_probe(
            first_tick_seen=first_tick_seen,
            second_tick_seen=second_tick_seen,
            wake_during_first_tick=True,
        )
        try:
            scheduler.wake_active_cancel_watchdog("session-watchdog-probe")
            await asyncio.wait_for(second_tick_seen.wait(), timeout=0.5)

            assert first_tick_seen.is_set()
            assert scheduler._tick_count == 2
            assert scheduler._event_states_before_tick == [False, False]
            assert scheduler._event_state_after_nested_wake is True
            assert scheduler._health_gate.state is HostExecutionHealthState.READY
        finally:
            await scheduler.close()

        assert scheduler._health_gate.state is HostExecutionHealthState.READY


@pytest.mark.asyncio
async def test_active_cancel_watchdog_concurrent_wakes_coalesce_to_level_signal(
    tmp_path: Path,
) -> None:
    """多个并发 wake 可合并为一次 level signal，不制造额外 tick。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        scheduler = cast(
            _LevelTriggeredActiveCancelWatchdogScheduler,
            await _open_watchdog_probe_scheduler(
                tmp_path,
                store,
                _LevelTriggeredActiveCancelWatchdogScheduler,
                suffix="coalesced-wakes",
            ),
        )
        first_tick_seen = asyncio.Event()
        second_tick_seen = asyncio.Event()
        scheduler.configure_level_trigger_probe(
            first_tick_seen=first_tick_seen,
            second_tick_seen=second_tick_seen,
            wake_during_first_tick=False,
        )
        try:
            scheduler.wake_active_cancel_watchdog("session-watchdog-probe")
            scheduler.wake_active_cancel_watchdog("session-watchdog-probe")
            scheduler.wake_active_cancel_watchdog("session-watchdog-probe")
            await asyncio.wait_for(first_tick_seen.wait(), timeout=0.5)

            assert scheduler._tick_count == 1
            assert scheduler._event_states_before_tick == [False]
            assert scheduler._active_cancel_watchdog_event.is_set() is False
            assert second_tick_seen.is_set() is False
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_active_cancel_watchdog_unexpected_failure_reports_typed_fatal(
    tmp_path: Path,
) -> None:
    """watchdog 普通异常必须由 S3 critical supervisor 提交 typed fatal。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        scheduler = cast(
            _FailingActiveCancelWatchdogScheduler,
            await _open_watchdog_probe_scheduler(
                tmp_path,
                store,
                _FailingActiveCancelWatchdogScheduler,
                suffix="fatal",
            ),
        )
        try:
            scheduler.wake_active_cancel_watchdog("session-watchdog-probe")
            task = scheduler._active_cancel_watchdog_task
            assert task is not None
            await task

            assert scheduler._health_gate.state is HostExecutionHealthState.UNAVAILABLE
            with pytest.raises(HostApiError) as exc_info:
                scheduler.wake_active_cancel_watchdog("session-watchdog-probe")
            assert exc_info.value.code is HostApiErrorCode.UNAVAILABLE
            assert isinstance(exc_info.value.detail, HostUnavailableDetail)
            assert exc_info.value.detail.component == "active_cancel_watchdog"
            assert exc_info.value.detail.reason_code == "critical_task_unexpected_exit"
            assert "private failure" not in str(exc_info.value.detail)
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_drain_loop_retry_exhausted_preserves_pending_durable_truth(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """drain retry exhausted 不把 pending durable work 改写成 terminal。

    :param tmp_path: pytest 临时目录。
    :param caplog: pytest 日志捕获 fixture。
    :returns: ``None``。
    """

    caplog.set_level(logging.WARNING, logger="dayu.host.dispatch")
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        lane_controller = await LaneController.open(
            [
                LaneConfig(
                    name=_LANE_NAME,
                    capacity=1,
                    default_timeout_seconds=0.1,
                    claim_ttl_seconds=1.0,
                    heartbeat_interval_seconds=0.1,
                )
            ],
            coordinator=SQLiteLaneCoordinatorConfig(db_path=tmp_path / "lane-drain-loop-queue-closeout.sqlite3"),
        )
        scheduler = _RetryOnceDrainLoopScheduler(
            transaction_runner=store.transaction_runner,
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            terminal_post_commit_port=_RecordingTerminalPort(),
            event_log_store=EventLogStore(),
            local_execution=HostLocalExecutionOptions(
                lane_db_path=tmp_path / "lane-drain-loop-queue-closeout.sqlite3",
                lane_name=_LANE_NAME,
                lane_capacity=1,
                lane_default_timeout_seconds=0.1,
                lane_claim_ttl_seconds=1.0,
                lane_heartbeat_interval_seconds=0.1,
                worker_startup_timeout_seconds=1.0,
                dispatch_poll_interval_seconds=0.01,
                runner_spec=_runner_spec(),
                runner_options=RunnerCallOptions(temperature=None, max_tokens=None, top_p=None, stream=False),
                agent_policy=_agent_policy(False),
                worker_factory=_FakeWorkerFactory(),
            ),
            lane_controller=lane_controller,
            host_handle_id="host-drain-loop-queue-closeout",
            session_new_work_access=ExplicitFakeSessionAccess(
                allowed_session_ids=None,
            ),
        )
        scheduler._queue.put_nowait(_pending_dispatch(seeded))
        retry_seen = asyncio.Event()
        reconciled = asyncio.Event()
        scheduler.configure_retry_probe(
            retry_seen=retry_seen,
            reconciled=reconciled,
        )
        scheduler._drain_task = scheduler._start_critical_task(
            scheduler._drain_loop,
            component="dispatch",
        )
        await asyncio.wait_for(retry_seen.wait(), timeout=0.5)
        await asyncio.wait_for(reconciled.wait(), timeout=0.5)
        await scheduler.close()

        run, attempt, dispatch_record = _read_rows(store.transaction_runner, seeded)
        assert scheduler._queue.qsize() == 1
        assert run.status is RunStatus.RUNNING
        assert attempt.status is AttemptStatus.STARTING
        assert dispatch_record.status is DispatchRecordStatus.PENDING

    assert "dispatch.drain_loop.queue_closeout" not in caplog.text


@pytest.mark.asyncio
async def test_close_worker_lost_failure_logs_context_without_raising(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """lost closeout 自身失败时记录结构化上下文且不传播异常。"""

    caplog.set_level(logging.ERROR, logger="dayu.host.dispatch")
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, _FakeWorkerFactory())
        try:
            token = _HostCancellationToken()
            envelope = LocalEngineEnvelope(
                session_id=seeded.session_id,
                run_id=seeded.run_id,
                attempt_id=seeded.attempt_id,
                execution_id=seeded.execution_id,
                dispatch_record_id=seeded.dispatch_record_id,
                worker_kind=WorkerKind.LOCAL,
                execution_target="target-dispatch",
                local_worker_id="worker-lost-closeout-fails",
                cancellation_token=token,
            )
            closed = scheduler._safe_close_worker_lost(
                ingestor=cast(
                    EngineEventIngestor,
                    _CloseWorkerLostFailingIngestor(),
                ),
                envelope=envelope,
                record=_pending_dispatch(seeded),
                local_worker_id="worker-lost-closeout-fails",
                worker_lifecycle_signal="ingest_exception",
                stream_error_code="RuntimeError",
                last_observed_worker_event_index=3,
                last_accepted_event_id=None,
                original_error=RuntimeError("original ingest failure"),
            )
            assert closed is False
        finally:
            await scheduler.close()

    assert "dispatch.worker_events.close_worker_lost_failed" in caplog.text
    assert "run_id=run-dispatch" in caplog.text
    assert "closeout_error_type=RuntimeError" in caplog.text
    assert "original_error_type=RuntimeError" in caplog.text


@pytest.mark.asyncio
async def test_safe_cleanup_helpers_log_failures(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """best-effort cleanup 失败时必须写入 warning 诊断。

    :param caplog: pytest 日志捕获 fixture。
    :returns: ``None``。
    """

    caplog.set_level(logging.WARNING, logger="dayu.host.dispatch")
    await _safe_close_worker_handle(_FailingCloseWorkerHandle())
    await _safe_release_lane_token(cast(LaneClaimToken, _FailingLaneToken()))

    messages = [record.getMessage() for record in caplog.records]
    assert any("dispatch.worker_handle.close_failed" in item for item in messages)
    assert any("dispatch.lane_token.release_failed" in item for item in messages)


@pytest.mark.asyncio
async def test_drain_loop_logs_idle_once_per_idle_streak_and_close(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """drain loop 空闲态和 close 取消路径写入有界 debug 诊断。

    :param tmp_path: pytest 临时目录。
    :param caplog: pytest 日志捕获 fixture。
    :returns: ``None``。
    """

    caplog.set_level(logging.DEBUG, logger="dayu.host.dispatch")
    factory = _FakeWorkerFactory()
    observed_queue = _ObservedEmptyQueue(target_empty_checks=3)
    with open_host_durable_store(_options(tmp_path)) as store:
        scheduler = await _open_scheduler(tmp_path, store, factory)
        scheduler._queue = observed_queue
        scheduler._drain_task = asyncio.create_task(scheduler._drain_loop())
        try:
            await observed_queue.empty_checked.wait()
        finally:
            await scheduler.close()

    idle_messages = [
        record.getMessage() for record in caplog.records if "dispatch.drain_loop.idle" in record.getMessage()
    ]
    assert idle_messages == ["dispatch.drain_loop.idle host_handle_id=host-test interval_seconds=0.01"]
    assert observed_queue.empty_call_count >= 3
    assert any("dispatch drain loop cancelled during close" in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_scheduler_injects_durable_memory_for_no_tool_dispatch(
    tmp_path: Path,
) -> None:
    """no-tool dispatch 默认接入 durable memory provider。"""

    factory = _FakeWorkerFactory(accepted_handle=_CloseCountingHandle())
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-memory-previous",
            event_id="event-input-memory-previous",
            display_text="previous memory prompt",
            client_request_id="client-memory-previous",
            idempotency_key="idem-memory-previous",
        )
        seeded = _seed_current_run(store, session_id=session_id)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()

            request = factory.accepted_requests[0]
            contents = tuple(_message_text(message) for message in request.messages)
            assert result.dispatched == 1
            assert "previous memory prompt" in contents
            assert contents[-1] == "dispatch prompt"
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_scheduler_uses_toolruntime_when_tooling_is_configured(
    tmp_path: Path,
) -> None:
    """真实 dispatch scheduler 在 tool-enabled 配置下接入 ToolRuntime。"""

    factory = _FakeWorkerFactory(accepted_handle=_CloseCountingHandle())
    tool = _CountingTool()
    tooling = _tooling_options(tool)
    tool_policy = _agent_policy(True)
    projection = _FailingProjectionCatchup()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-tool-memory-previous",
            event_id="event-input-tool-memory-previous",
            display_text="tool-enabled previous memory prompt",
            client_request_id="client-tool-memory-previous",
            idempotency_key="idem-tool-memory-previous",
        )
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            agent_policy=tool_policy,
            tool_schemas=tuple(definition.to_tool_schema() for definition in tooling.business_tool_bundle.definitions),
            tooling_options=tooling,
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            agent_policy=tool_policy,
            tooling_options=tooling,
            projection_catchup=projection,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()

            request = factory.accepted_requests[0]
            contents = tuple(_message_text(message) for message in request.messages)
            assert result.dispatched == 1
            assert request.disable_tools is False
            assert request.agent_policy.allow_tool_calls is True
            assert "tool-enabled previous memory prompt" in contents
            assert [schema.function.name for schema in request.tool_schemas] == ["fake_dispatch_tool"]

            tool_outcome = await request.tool_executor.execute(
                _tool_execution_request(
                    seeded,
                    request,
                    ToolCallRequest(
                        tool_call_id="tool-call-dispatch",
                        name="fake_dispatch_tool",
                        arguments={"ticker": "DAYU"},
                        index_in_iteration=0,
                        provider_state=None,
                    ),
                )
            )

            assert tool.call_count == 1
            assert isinstance(tool_outcome.records[0].outcome, ToolCompletedOutcome)
            assert _read_event_by_type(store.transaction_runner, "TOOL_CALL_REQUESTED").run_id == seeded.run_id
            assert _read_event_by_type(store.transaction_runner, "TOOL_RESULT_ACCEPTED").run_id == seeded.run_id
            assert projection.calls == 1
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_drain_loop_continues_when_dispatch_arrives_during_empty_window(
    tmp_path: Path,
) -> None:
    """empty / sleep / return 窗口内入队的 dispatch 不应被遗留在队列中。"""

    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            lane_default_timeout_seconds=1.0,
        )
        scheduler._queue = _EnqueueOnSecondEmptyQueue(_pending_dispatch(seeded))
        scheduler._drain_task = asyncio.create_task(scheduler._drain_loop())
        try:
            for _ in range(50):
                if factory.created == 1:
                    break
                await asyncio.sleep(0.01)
            assert factory.created == 1
            assert scheduler._queue.empty() is True
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_cancelled_dispatch_is_skipped_before_worker_call(
    tmp_path: Path,
) -> None:
    """worker accept 前被 direct cancel 的 dispatch 不会调用 worker。"""

    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        try:
            _mark_dispatching_and_cancel(store.transaction_runner, seeded)
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()
            assert result.processed == 1
            assert result.skipped == 1
            assert factory.created == 0
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_cancel_race_after_lane_acquire_releases_lane_without_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """lane acquire 后 durable cancel race 会释放 lane 且不调用 worker。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    """

    factory = _FakeWorkerFactory()
    lane_db_path = tmp_path / "lane-cancel-race.sqlite3"
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            lane_db_path=lane_db_path,
        )
        original_recheck = scheduler._dispatch_record_still_pre_accept
        monkeypatch.setattr(
            scheduler,
            "_dispatch_record_still_pre_accept",
            _CancelBeforePreAcceptRecheck(
                transaction_runner=store.transaction_runner,
                seeded=seeded,
                original_recheck=original_recheck,
            ),
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()
            run, attempt, dispatch_record = _read_rows(store.transaction_runner, seeded)

            assert result.processed == 1
            assert result.skipped == 1
            assert factory.created == 0
            assert run.status is RunStatus.CANCELLED
            assert attempt.status is AttemptStatus.CANCELLED
            assert dispatch_record.status is DispatchRecordStatus.CANCELLED
            verifier = await LaneController.open(
                [
                    LaneConfig(
                        name=_LANE_NAME,
                        capacity=1,
                        default_timeout_seconds=0,
                        claim_ttl_seconds=1.0,
                        heartbeat_interval_seconds=0.1,
                    )
                ],
                coordinator=SQLiteLaneCoordinatorConfig(db_path=lane_db_path),
                owner=LaneOwner(
                    owner_id="lane-cancel-race-verifier",
                    pid=1,
                    process_start_token=None,
                ),
            )
            try:
                reopened = await verifier.acquire(_LANE_NAME, timeout_seconds=0)
                assert isinstance(reopened, LaneAcquired)
                await reopened.token.release()
            finally:
                await verifier.close()
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_dispatching_after_recheck_requires_waiting_for_lane(
    tmp_path: Path,
) -> None:
    """scheduler durable recheck 只接受已进入 waiting_for_lane 的 dispatch。"""

    factory = _FakeWorkerFactory()
    host_identity = HostInstanceIdentity(
        host_instance_id="host-instance-dispatch-recheck",
        pid=1,
        process_start_token="process-token-dispatch-recheck",
        boot_id=None,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            host_handle_id="host-handle-dispatch-recheck",
            host_instance_identity=host_identity,
        )
        claim = await scheduler._lane_controller.acquire(
            _LANE_NAME,
            timeout_seconds=0,
        )
        assert isinstance(claim, LaneAcquired)
        try:
            wait_row = scheduler._mark_waiting_for_lane(_pending_dispatch(seeded))
            assert wait_row is not None
            assert wait_row.status == DispatchRecordStatus.WAITING_FOR_LANE
            assert wait_row.owner_host_instance_id == scheduler.host_instance_id
            assert wait_row.owner_host_instance_id != "host-handle-dispatch-recheck"
            dispatch_record = scheduler._mark_dispatching_after_recheck(
                _pending_dispatch(seeded),
                claim.token,
            )

            assert dispatch_record is not None
            assert dispatch_record.status == DispatchRecordStatus.DISPATCHING
            assert dispatch_record.waiting_for_lane_at is not None
            assert dispatch_record.lane_name == _LANE_NAME
            assert dispatch_record.lane_claim_id == claim.token.claim_id
            assert dispatch_record.owner_host_instance_id == scheduler.host_instance_id
            assert dispatch_record.owner_host_instance_id != "host-handle-dispatch-recheck"
        finally:
            await claim.token.release()
            await scheduler.close()


@pytest.mark.asyncio
async def test_pending_dispatch_recheck_without_waiting_is_skipped(
    tmp_path: Path,
) -> None:
    """scheduler durable recheck 不允许绕过 waiting_for_lane。"""

    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        claim = await scheduler._lane_controller.acquire(
            _LANE_NAME,
            timeout_seconds=0,
        )
        assert isinstance(claim, LaneAcquired)
        try:
            dispatch_record = scheduler._mark_dispatching_after_recheck(
                _pending_dispatch(seeded),
                claim.token,
            )

            assert dispatch_record is None
        finally:
            await claim.token.release()
            await scheduler.close()


@pytest.mark.asyncio
async def test_worker_startup_timeout_closes_starting_attempt_failed(
    tmp_path: Path,
) -> None:
    """worker accept timeout 会把 STARTING Attempt 和 Run 关闭为 FAILED。"""

    factory = _FakeWorkerFactory(slow=True)
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            worker_startup_timeout_seconds=0.001,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()

            run, attempt, dispatch_record = _read_rows(store.transaction_runner, seeded)
            event = _read_event_by_type(store.transaction_runner, "RUN_FAILED")
            assert result.timed_out == 1
            assert run.status == RunStatus.FAILED
            assert attempt.status == AttemptStatus.FAILED
            assert dispatch_record.status == DispatchRecordStatus.CANCELLED
            assert json.loads(_require_text(event.reason_json))["reason"] == ("worker_startup_timeout")
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_dispatch_first_durable_retry_exhausted_requeues_current_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """首次 durable 写 retry exhausted 时当前 dispatch record 不会丢失。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, _FakeWorkerFactory())

        def _raise_retry_exhausted(
            record: PendingDispatchRecord,
        ) -> DispatchRecordRow | None:
            """模拟首次 durable waiting-for-lane 写入 retry exhausted。

            :param record: pending dispatch record。
            :returns: 不会返回。
            :raises HostTransactionRetryExhaustedError: 始终抛出。
            """

            del record
            raise HostTransactionRetryExhaustedError(
                "waiting_for_lane busy",
                attempts=3,
            )

        monkeypatch.setattr(
            scheduler,
            "_mark_waiting_for_lane",
            _raise_retry_exhausted,
        )
        try:
            scheduler._queue.put_nowait(_pending_dispatch(seeded))

            with pytest.raises(HostTransactionRetryExhaustedError):
                await scheduler.drain_once()

            assert scheduler._queue.qsize() == 1
            queued = scheduler._queue.get_nowait()
            assert queued.dispatch_record_id == seeded.dispatch_record_id
            assert queued.attempt_id == seeded.attempt_id
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_scheduler_queue_promotion_survives_projection_catchup_failure(
    tmp_path: Path,
) -> None:
    """scheduler promotion wakeup 中 projection catch-up 失败不阻断 promotion。"""

    factory = _FakeWorkerFactory()
    projection = _FailingProjectionCatchup()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            projection_catchup=projection,
        )
        try:
            await scheduler.run_queue_promotion(session_id)

            assert projection.calls == 1
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_worker_accept_exception_closes_failed_and_cancels_dispatch(
    tmp_path: Path,
) -> None:
    """worker accept 非 timeout 异常按 startup failure 收口并取消 dispatch row。"""

    factory = _FakeWorkerFactory(worker=_FailingAcceptWorker())
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()

            run, attempt, dispatch_record = _read_rows(store.transaction_runner, seeded)
            assert result.timed_out == 1
            assert run.status == RunStatus.FAILED
            assert attempt.status == AttemptStatus.FAILED
            assert dispatch_record.status == DispatchRecordStatus.CANCELLED
            assert dispatch_record.cancelled_event_id is not None
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_worker_startup_closeout_error_still_releases_lane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """startup closeout 抛错时仍返回 timed_out 并释放 lane token。"""

    factory = _FakeWorkerFactory(worker=_FailingAcceptWorker())
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)

        def raise_closeout(record: PendingDispatchRecord) -> None:
            """模拟 durable closeout 失败。

            :param record: pending dispatch record。
            :returns: ``None``。
            :raises RuntimeError: 始终抛出 closeout 失败。
            """

            del record
            raise RuntimeError("closeout failed")

        monkeypatch.setattr(
            scheduler,
            "_closeout_worker_startup_timeout",
            raise_closeout,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            with caplog.at_level(logging.WARNING, logger="dayu.host.dispatch"):
                result = await scheduler.drain_once()

            assert result.timed_out == 1
            claim = await scheduler._lane_controller.acquire(
                _LANE_NAME,
                timeout_seconds=0,
            )
            assert isinstance(claim, LaneAcquired)
            await claim.token.release()
            assert "worker startup closeout failed; continuing" in caplog.text
            assert "error_type=RuntimeError" in caplog.text
            assert "original_error_type=RuntimeError" in caplog.text
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_durable_run_cancellation_token_fails_closed_on_retry_exhausted() -> None:
    """durable read 重试耗尽时，compaction 取消 token 必须 fail closed。"""

    token = _DurableRunCancellationToken(
        transaction_runner=_RetryExhaustedReadRunner(),
        run_id="run-durable-unavailable",
        session_id="session-durable-unavailable",
        expected_status=RunStatus.ACCEPTED,
        expected_input_event_sequence=1,
    )

    assert token.is_cancelled() is True
    assert token.cancel_reason() == "durable_unavailable"


@pytest.mark.asyncio
async def test_dispatch_retry_exhausted_requeues_without_terminal_closeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """dispatch durable 重试耗尽只释放 lane 并重排，不按 startup timeout 收口。"""

    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)

        def raise_retry_exhausted(record: PendingDispatchRecord, token: LaneClaimToken) -> DispatchRecordRow | None:
            """模拟 dispatching recheck 写事务 busy 重试耗尽。

            :param record: pending dispatch record。
            :param token: 已获取的 lane token。
            :returns: 不会返回。
            :raises HostTransactionRetryExhaustedError: 始终抛出以模拟 busy。
            """

            del record, token
            raise HostTransactionRetryExhaustedError("dispatch recheck busy", attempts=3)

        monkeypatch.setattr(
            scheduler,
            "_mark_dispatching_after_recheck",
            raise_retry_exhausted,
        )
        try:
            scheduler._queue.put_nowait(_pending_dispatch(seeded))
            with caplog.at_level(logging.WARNING, logger="dayu.host.dispatch"):
                result = await scheduler.drain_once()
            await asyncio.sleep(0)

            run, attempt, dispatch_record = _read_rows(store.transaction_runner, seeded)
            assert result.processed == 1
            assert result.skipped == 1
            assert result.timed_out == 0
            assert run.status is RunStatus.RUNNING
            assert attempt.status is AttemptStatus.STARTING
            assert dispatch_record.status is DispatchRecordStatus.WAITING_FOR_LANE
            assert dispatch_record.cancelled_event_id is None
            assert scheduler._queue.qsize() == 1

            claim = await scheduler._lane_controller.acquire(
                _LANE_NAME,
                timeout_seconds=0,
            )
            assert isinstance(claim, LaneAcquired)
            await claim.token.release()
            assert "dispatch durable retry exhausted; requeueing" in caplog.text
            assert seeded.run_id in caplog.text
            assert seeded.attempt_id in caplog.text
            assert seeded.dispatch_record_id in caplog.text
            assert "error_type=HostTransactionRetryExhaustedError" in caplog.text
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_lane_acquire_timeout_closes_starting_attempt_failed(
    tmp_path: Path,
) -> None:
    """lane acquire timeout 会把 worker accept 前 Attempt 与 Run 关闭为 FAILED。"""

    factory = _FakeWorkerFactory()
    lane_db_path = tmp_path / "lane.sqlite3"
    lane_holder = await LaneController.open(
        [
            LaneConfig(
                name=_LANE_NAME,
                capacity=1,
                default_timeout_seconds=0.001,
                claim_ttl_seconds=1.0,
                heartbeat_interval_seconds=0.1,
            )
        ],
        coordinator=SQLiteLaneCoordinatorConfig(db_path=lane_db_path),
    )
    claim = await lane_holder.acquire(_LANE_NAME, timeout_seconds=0)
    assert isinstance(claim, LaneAcquired)
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            lane_db_path=lane_db_path,
            lane_default_timeout_seconds=0.001,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()

            run, attempt, dispatch_record = _read_rows(store.transaction_runner, seeded)
            event = _read_event_by_type(store.transaction_runner, "RUN_FAILED")
            assert result.timed_out == 1
            assert result.dispatched == 0
            assert factory.created == 0
            assert run.status == RunStatus.FAILED
            assert attempt.status == AttemptStatus.FAILED
            assert dispatch_record.status == DispatchRecordStatus.CANCELLED
            assert json.loads(_require_text(event.reason_json))["reason"] == ("worker_startup_timeout")
        finally:
            await scheduler.close()
            await claim.token.release()
            await lane_holder.close()


@pytest.mark.asyncio
async def test_worker_clean_eof_closes_run_failed_from_scheduler(
    tmp_path: Path,
) -> None:
    """accepted worker clean EOF 由 scheduler 映射为 FAILED closeout。"""

    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()
            run, attempt, _dispatch_record = await _wait_for_statuses(
                store.transaction_runner,
                seeded,
                expected_run=RunStatus.FAILED,
                expected_attempt=AttemptStatus.FAILED,
            )

            assert result.dispatched == 1
            assert run.status == RunStatus.FAILED
            assert attempt.status == AttemptStatus.FAILED
            event = _read_event_by_type(store.transaction_runner, "RUN_FAILED")
            assert json.loads(_require_text(event.reason_json))["reason"] == ("stream_ended_without_terminal")
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_worker_stream_exception_closes_run_lost_from_scheduler(
    tmp_path: Path,
) -> None:
    """accepted worker stream 异常由 scheduler 映射为 LOST closeout。"""

    handle = _CrashingHandle()
    registry = ActiveWorkerRegistry()
    factory = _FakeWorkerFactory(worker=_HandleWorker(handle))
    lane_db_path = tmp_path / "lane-stream-exception.sqlite3"
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            lane_db_path=lane_db_path,
            lane_default_timeout_seconds=1.0,
            active_registry=registry,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()
            run, attempt, _dispatch_record = await _wait_for_statuses(
                store.transaction_runner,
                seeded,
                expected_run=RunStatus.LOST,
                expected_attempt=AttemptStatus.LOST,
            )
            await _wait_for_active_tasks_to_finish(scheduler)

            assert result.dispatched == 1
            assert run.status == RunStatus.LOST
            assert attempt.status == AttemptStatus.LOST
            event = _read_event_by_type(store.transaction_runner, "RUN_LOST")
            assert json.loads(_require_text(event.reason_json))["reason"] == ("worker_lost_before_terminal")
            assert handle.closed is True
            assert (
                registry.cancel(
                    ActiveCancelMessage(
                        session_id=seeded.session_id,
                        run_id=seeded.run_id,
                        attempt_id=seeded.attempt_id,
                        execution_id=seeded.execution_id,
                        reason="after_stream_exception",
                    )
                )
                is False
            )
            verifier = await LaneController.open(
                [
                    LaneConfig(
                        name=_LANE_NAME,
                        capacity=1,
                        default_timeout_seconds=0,
                        claim_ttl_seconds=1.0,
                        heartbeat_interval_seconds=0.1,
                    )
                ],
                coordinator=SQLiteLaneCoordinatorConfig(db_path=lane_db_path),
                owner=LaneOwner(
                    owner_id="lane-stream-exception-verifier",
                    pid=1,
                    process_start_token=None,
                ),
            )
            try:
                reopened = await verifier.acquire(_LANE_NAME, timeout_seconds=0)
                assert isinstance(reopened, LaneAcquired)
                await reopened.token.release()
            finally:
                await verifier.close()
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_scheduler_close_continues_after_best_effort_cancel_hook_failure(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """on_cancel 抛错不阻断 token、mandatory cleanup 与 STOPPED。

    :param tmp_path: pytest 临时目录。
    :param caplog: pytest 日志捕获 fixture。
    :returns: ``None``。
    :raises AssertionError: hook 失败阻断 owner cleanup 时抛出。
    """

    handle = _CancelHookFailingHandle()
    factory = _FakeWorkerFactory(accepted_handle=handle)
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        scheduler.wake_dispatch(_pending_dispatch(seeded))
        result = await scheduler.drain_once()

        assert result.dispatched == 1
        with caplog.at_level("WARNING", logger="dayu.host.dispatch"):
            await scheduler.close()
        assert "active worker cancel hook failed; continuing" in caplog.text
        assert factory.accepted_requests[0].cancellation_token.is_cancelled()
        assert handle.cancel_count == 1
        assert handle.close_count == 1
        assert handle.closed is True
        assert scheduler._close_cleanup_done is True
        host_instance = store.transaction_runner.run_read(
            lambda transaction: read_host_instance(
                transaction,
                scheduler.host_instance_id,
            )
        )
        assert host_instance is not None
        assert host_instance.status is HostInstanceStatus.STOPPED


@pytest.mark.asyncio
async def test_scheduler_close_lets_active_task_own_handle_close(
    tmp_path: Path,
) -> None:
    """scheduler close 只发 cancel，handle close 由 active task finally 执行一次。"""

    handle = _CloseCountingHandle()
    factory = _FakeWorkerFactory(accepted_handle=handle)
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        scheduler.wake_dispatch(_pending_dispatch(seeded))
        result = await scheduler.drain_once()

        assert result.dispatched == 1
        await scheduler.close()
        assert handle.cancel_count == 1
        assert handle.close_count == 1


@pytest.mark.asyncio
async def test_scheduler_close_cleans_active_handle_when_consumer_task_never_started(
    tmp_path: Path,
) -> None:
    """close 必须清理尚未进入 events consume body 的 active handle。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: close 后仍残留 active handle、registry entry 或未关闭
        worker handle 时抛出。
    """

    handle = _ControlledBlockingHandle()
    registry = ActiveWorkerRegistry()
    cancellation_token = _HostCancellationToken()
    started = asyncio.Event()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            active_registry=registry,
        )
        heartbeat_task = scheduler._heartbeat_task
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            scheduler._heartbeat_task = None
        watchdog_task = scheduler._active_cancel_watchdog_task
        if watchdog_task is not None:
            watchdog_task.cancel()
            try:
                await watchdog_task
            except asyncio.CancelledError:
                pass
            scheduler._active_cancel_watchdog_task = None
        registry.register(
            session_id=seeded.session_id,
            run_id=seeded.run_id,
            attempt_id=seeded.attempt_id,
            execution_id=seeded.execution_id,
            handle=handle,
            cancellation_token=cancellation_token,
        )
        active_task = asyncio.create_task(_unstarted_active_consumer_probe(started))
        scheduler._active_handles.add(handle)
        scheduler._active_tasks.add(active_task)
        active_task.add_done_callback(scheduler._active_tasks.discard)

        await scheduler.close()

        assert not started.is_set()
        assert cancellation_token.is_cancelled()
        assert cancellation_token.cancel_reason() == "scheduler_close"
        assert handle.cancel_count == 1
        assert handle.close_count == 1
        assert not scheduler._active_tasks
        assert not scheduler._active_handles
        assert (
            registry.cancel(
                ActiveCancelMessage(
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    execution_id=seeded.execution_id,
                    reason="after_scheduler_close",
                )
            )
            is False
        )


@pytest.mark.asyncio
async def test_scheduler_close_retries_mandatory_residual_handle_before_stopped(
    tmp_path: Path,
) -> None:
    """残余 handle close 失败时保持 STOPPING，重试成功后才 STOPPED。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: mandatory handle 异常被吞或阶段提前完成时抛出。
    """

    handle = _FailOnceCloseHandle()
    with open_host_durable_store(_options(tmp_path)) as store:
        scheduler = await _open_scheduler(tmp_path, store, _FakeWorkerFactory())
        scheduler._active_handles.add(handle)

        with pytest.raises(RuntimeError, match="mandatory handle close failed"):
            await scheduler.close()

        failed_instance = store.transaction_runner.run_read(
            lambda transaction: read_host_instance(
                transaction,
                scheduler.host_instance_id,
            )
        )
        assert failed_instance is not None
        assert failed_instance.status is HostInstanceStatus.STOPPING
        assert scheduler._closed is True
        assert scheduler._close_cleanup_done is False
        assert scheduler._lane_close_done is False
        assert scheduler._host_instance_stopped_marked is False
        assert handle in scheduler._active_handles
        assert handle.close_count == 1
        assert handle.closed is False

        await scheduler.close()

        stopped_instance = store.transaction_runner.run_read(
            lambda transaction: read_host_instance(
                transaction,
                scheduler.host_instance_id,
            )
        )
        assert stopped_instance is not None
        assert stopped_instance.status is HostInstanceStatus.STOPPED
        assert scheduler._close_cleanup_done is True
        assert scheduler._lane_close_done is True
        assert scheduler._host_instance_stopped_marked is True
        assert handle not in scheduler._active_handles
        assert handle.close_count == 2
        assert handle.closed is True


@pytest.mark.asyncio
async def test_scheduler_close_during_active_events_releases_all_resources(
    tmp_path: Path,
) -> None:
    """scheduler close 期间活跃事件消费被取消后会释放 lane 与 registry。"""

    handle = _ControlledBlockingHandle()
    registry = ActiveWorkerRegistry()
    factory = _FakeWorkerFactory(accepted_handle=handle)
    lane_db_path = tmp_path / "lane-close-active.sqlite3"
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            lane_db_path=lane_db_path,
            active_registry=registry,
        )
        scheduler.wake_dispatch(_pending_dispatch(seeded))
        result = await scheduler.drain_once()
        await handle.events_started.wait()

        assert result.dispatched == 1
        assert len(factory.accepted_requests) == 1
        await scheduler.close()

        assert factory.accepted_requests[0].cancellation_token.is_cancelled()
        assert factory.accepted_requests[0].cancellation_token.cancel_reason() == "scheduler_close"
        assert handle.cancel_count == 1
        assert handle.close_count == 1
        assert handle.events_finalized.is_set()
        assert (
            registry.cancel(
                ActiveCancelMessage(
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    execution_id=seeded.execution_id,
                    reason="after_scheduler_close",
                )
            )
            is False
        )
        verifier = await LaneController.open(
            [
                LaneConfig(
                    name=_LANE_NAME,
                    capacity=1,
                    default_timeout_seconds=0,
                    claim_ttl_seconds=1.0,
                    heartbeat_interval_seconds=0.1,
                )
            ],
            coordinator=SQLiteLaneCoordinatorConfig(db_path=lane_db_path),
            owner=LaneOwner(
                owner_id="lane-verifier",
                pid=1,
                process_start_token=None,
            ),
        )
        try:
            reopened = await verifier.acquire(_LANE_NAME, timeout_seconds=0)
            assert isinstance(reopened, LaneAcquired)
            await reopened.token.release()
        finally:
            await verifier.close()


@pytest.mark.asyncio
async def test_scheduler_close_with_non_empty_dispatch_queue_does_not_drain_or_write_terminal(
    tmp_path: Path,
) -> None:
    """dispatch queue 非空 close 不处理 pending work，也不写 terminal fact。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    """

    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)

        scheduler.wake_dispatch(_pending_dispatch(seeded))
        event_log_cursor = _event_log_cursor(store.transaction_runner)
        await scheduler.close()

        run, attempt, dispatch_record = _read_rows(store.transaction_runner, seeded)
        assert scheduler._queue.qsize() == 1
        assert factory.created == 0
        assert run.status is RunStatus.RUNNING
        assert attempt.status is AttemptStatus.STARTING
        assert dispatch_record.status is DispatchRecordStatus.PENDING
        assert dispatch_record.worker_accept_event_id is None
        _assert_scheduler_close_did_not_append_terminal_facts(
            store.transaction_runner,
            after_cursor=event_log_cursor,
        )
        with pytest.raises(HostApiError) as wake_error:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
        assert wake_error.value.code is HostApiErrorCode.UNAVAILABLE
        assert wake_error.value.retryable is True
        with pytest.raises(RuntimeError, match="HostDispatchScheduler is closed"):
            await scheduler.drain_once()


@pytest.mark.asyncio
async def test_scheduler_close_during_lane_wait_skips_worker_startup_timeout_terminal_fact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pre-worker lane wait 窗口 close 取消 drain path，不写 startup timeout。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    """

    factory = _FakeWorkerFactory()
    blocked_acquire = _BlockedLaneAcquire()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        original_acquire = scheduler._lane_controller.acquire
        monkeypatch.setattr(scheduler._lane_controller, "acquire", blocked_acquire)
        scheduler.wake_dispatch(_pending_dispatch(seeded))
        scheduler._drain_task = asyncio.create_task(_run_scheduler_drain_once(scheduler))

        await blocked_acquire.started.wait()
        run, attempt, dispatch_record = _read_rows(store.transaction_runner, seeded)
        assert run.status is RunStatus.RUNNING
        assert attempt.status is AttemptStatus.STARTING
        assert dispatch_record.status is DispatchRecordStatus.WAITING_FOR_LANE
        event_log_cursor = _event_log_cursor(store.transaction_runner)

        await scheduler.close()
        monkeypatch.setattr(scheduler._lane_controller, "acquire", original_acquire)

        assert scheduler._drain_task is not None
        assert scheduler._drain_task.done() is True
        assert factory.created == 0
        run, attempt, dispatch_record = _read_rows(store.transaction_runner, seeded)
        assert run.status is RunStatus.RUNNING
        assert attempt.status is AttemptStatus.STARTING
        assert dispatch_record.status is DispatchRecordStatus.WAITING_FOR_LANE
        assert dispatch_record.cancelled_event_id is None
        _assert_scheduler_close_did_not_append_terminal_facts(
            store.transaction_runner,
            after_cursor=event_log_cursor,
        )
        with pytest.raises(RuntimeLaneClosedError):
            await scheduler._lane_controller.acquire(_LANE_NAME, timeout_seconds=0)


@pytest.mark.asyncio
async def test_scheduler_close_cancelled_mid_cleanup_can_retry_and_finish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """close cleanup 中途被取消后，再次 close 必须补完资源清理。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    """

    handle = _ControlledBlockingHandle()
    registry = ActiveWorkerRegistry()
    factory = _FakeWorkerFactory(accepted_handle=handle)
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            active_registry=registry,
        )
        scheduler.wake_dispatch(_pending_dispatch(seeded))
        assert (await scheduler.drain_once()).dispatched == 1
        await handle.events_started.wait()
        blocked_close = _CloseOnceBlockedLaneClose(scheduler._lane_controller.close)
        monkeypatch.setattr(scheduler._lane_controller, "close", blocked_close)
        event_log_cursor = _event_log_cursor(store.transaction_runner)

        close_task = asyncio.create_task(scheduler.close())
        await blocked_close.started.wait()
        close_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await close_task

        assert scheduler._closed is True
        assert scheduler._close_cleanup_done is False

        await scheduler.close()

        assert blocked_close.calls == 2
        assert scheduler._close_cleanup_done is True
        assert not scheduler._active_tasks
        assert not scheduler._active_handles
        assert handle.cancel_count == 1
        assert handle.close_count == 1
        assert (
            registry.cancel(
                ActiveCancelMessage(
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    execution_id=seeded.execution_id,
                    reason="after_close_retry",
                )
            )
            is False
        )
        _assert_scheduler_close_did_not_append_terminal_facts(
            store.transaction_runner,
            after_cursor=event_log_cursor,
        )
        with pytest.raises(RuntimeLaneClosedError):
            await scheduler._lane_controller.acquire(_LANE_NAME, timeout_seconds=0)


@pytest.mark.asyncio
async def test_scheduler_close_keeps_cleanup_incomplete_when_cleanup_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """close mandatory cleanup 抛异常时保持未完成并允许重试。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    """

    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        scheduler = await _open_scheduler(tmp_path, store, factory)
        original_close = scheduler._lane_controller.close
        failing_close = _FailingLaneClose()
        monkeypatch.setattr(scheduler._lane_controller, "close", failing_close)

        with pytest.raises(RuntimeError, match="lane close failed"):
            await scheduler.close()

        assert scheduler._closed is True
        assert scheduler._close_cleanup_done is False
        assert failing_close.calls == 1
        monkeypatch.setattr(scheduler._lane_controller, "close", original_close)

        await scheduler.close()

        assert scheduler._close_cleanup_done is True


@pytest.mark.asyncio
async def test_scheduler_close_retries_stopped_write_without_reclosing_lane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """STOPPED 写入失败时保持 STOPPING，重试只补完 durable 阶段。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: STOPPED 失败后错误宣称 cleanup 完成时抛出。
    """

    stopped_calls = 0
    original_mark_stopped = HostDispatchScheduler._mark_host_instance_stopped

    def fail_stopped_once(scheduler: HostDispatchScheduler) -> None:
        """首次模拟 STOPPED transaction 失败，后续委托 production owner。

        :param scheduler: 当前 scheduler owner。
        :returns: ``None``。
        :raises RuntimeError: 首次调用模拟 durable 写失败。
        """

        nonlocal stopped_calls
        stopped_calls += 1
        if stopped_calls == 1:
            raise RuntimeError("host instance STOPPED write failed")
        original_mark_stopped(scheduler)

    with open_host_durable_store(_options(tmp_path)) as store:
        scheduler = await _open_scheduler(tmp_path, store, _FakeWorkerFactory())
        monkeypatch.setattr(
            HostDispatchScheduler,
            "_mark_host_instance_stopped",
            fail_stopped_once,
        )

        with pytest.raises(RuntimeError, match="STOPPED write failed"):
            await scheduler.close()

        failed_instance = store.transaction_runner.run_read(
            lambda transaction: read_host_instance(
                transaction,
                scheduler.host_instance_id,
            )
        )
        assert failed_instance is not None
        assert failed_instance.status is HostInstanceStatus.STOPPING
        assert scheduler._lane_close_done is True
        assert scheduler._host_instance_stopped_marked is False
        assert scheduler._close_cleanup_done is False

        await scheduler.close()

        stopped_instance = store.transaction_runner.run_read(
            lambda transaction: read_host_instance(
                transaction,
                scheduler.host_instance_id,
            )
        )
        assert stopped_instance is not None
        assert stopped_instance.status is HostInstanceStatus.STOPPED
        assert stopped_calls == 2
        assert scheduler._lane_close_done is True
        assert scheduler._host_instance_stopped_marked is True
        assert scheduler._close_cleanup_done is True


@pytest.mark.asyncio
async def test_default_active_registry_is_scheduler_local(tmp_path: Path) -> None:
    """未显式注入 registry 时，不同 host scheduler 不共享默认 registry。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        first = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            lane_db_path=tmp_path / "lane-first.sqlite3",
        )
        second = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            lane_db_path=tmp_path / "lane-second.sqlite3",
            host_handle_id="host-test-second",
        )
        try:
            assert first._active_registry is not second._active_registry
        finally:
            await first.close()
            await second.close()


@pytest.mark.asyncio
async def test_consume_pre_event_exception_releases_lane_and_unregisters(
    tmp_path: Path,
) -> None:
    """consume task 在 pre-event 构造失败时仍释放 lane 并注销 active worker。"""

    handle = _FlakyLocalWorkerIdHandle()
    registry = ActiveWorkerRegistry()
    factory = _FakeWorkerFactory(worker=_HandleWorker(handle))
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            active_registry=registry,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()
            await _wait_for_active_tasks_to_finish(scheduler)

            assert result.dispatched == 1
            assert handle.close_count == 1
            assert (
                registry.cancel(
                    ActiveCancelMessage(
                        session_id=seeded.session_id,
                        run_id=seeded.run_id,
                        attempt_id=seeded.attempt_id,
                        execution_id=seeded.execution_id,
                        reason="test_cancel_after_failure",
                    )
                )
                is False
            )
            claim = await scheduler._lane_controller.acquire(
                _LANE_NAME,
                timeout_seconds=0,
            )
            assert isinstance(claim, LaneAcquired)
            await claim.token.release()
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_scheduler_with_default_local_proxy_stream_error_closes_lost(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实 DefaultLocalProxy 的 Engine stream 异常经 scheduler 映射为 LOST。"""

    async def raising_run_agent_messages(
        request: AgentRunRequest,
    ) -> AsyncIterator[EngineEvent]:
        """模拟 Engine public entry 在 stream 迭代时抛错。

        :param request: Engine request。
        :returns: 不会正常返回事件。
        :raises RuntimeError: 始终抛出 stream 异常。
        """

        del request
        raise RuntimeError("engine stream failed")
        if False:
            yield _unreachable_engine_event()

    monkeypatch.setattr(
        "dayu.host.local_proxy.run_agent_messages",
        raising_run_agent_messages,
    )

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            DefaultLocalEngineWorkerFactory(),
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()
            run, attempt, _dispatch_record = await _wait_for_statuses(
                store.transaction_runner,
                seeded,
                expected_run=RunStatus.LOST,
                expected_attempt=AttemptStatus.LOST,
            )

            assert result.dispatched == 1
            assert run.status == RunStatus.LOST
            assert attempt.status == AttemptStatus.LOST
            event = _read_event_by_type(store.transaction_runner, "RUN_LOST")
            assert json.loads(_require_text(event.reason_json))["reason"] == ("worker_lost_before_terminal")
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_scheduler_closes_default_local_proxy_after_terminal_before_late_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """terminal accepted 后 scheduler 关闭 worker stream，不继续读取 late event。"""

    stream_finalized = asyncio.Event()
    late_event_reached = asyncio.Event()

    async def terminal_then_late_run_agent_messages(
        request: AgentRunRequest,
    ) -> AsyncIterator[EngineEvent]:
        """先产出 terminal，再暴露一个不应被读取的 late event。

        :param request: Engine request。
        :returns: 受控 EngineEvent stream。
        """

        try:
            yield EngineEvent(
                occurred_at=_NOW,
                session_id=request.session_id,
                run_id=request.run_id,
                type=EngineEventType.FINAL_ANSWER,
                data=FinalAnswerData(
                    content="done",
                    filtered=False,
                    degraded=False,
                    finish_reason=FinishReason.STOP,
                    response_identity=(_successful_response_identity_for_agent_request(request)),
                ),
                metadata=None,
            )
            late_event_reached.set()
            yield EngineEvent(
                occurred_at=_NOW,
                session_id=request.session_id,
                run_id=request.run_id,
                type=EngineEventType.RUN_FAILED,
                data=RunFailedData(
                    error_code=adapter_error_code("late"),
                    message="late event must not be consumed",
                    provider_request_id=None,
                    recoverable=False,
                ),
                metadata=None,
            )
        finally:
            stream_finalized.set()

    monkeypatch.setattr(
        "dayu.host.local_proxy.run_agent_messages",
        terminal_then_late_run_agent_messages,
    )

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            DefaultLocalEngineWorkerFactory(),
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()
            run, attempt, _dispatch_record = await _wait_for_statuses(
                store.transaction_runner,
                seeded,
                expected_run=RunStatus.SUCCEEDED,
                expected_attempt=AttemptStatus.SUCCEEDED,
            )
            await _wait_for_active_tasks_to_finish(scheduler)

            assert result.dispatched == 1
            assert run.status == RunStatus.SUCCEEDED
            assert attempt.status == AttemptStatus.SUCCEEDED
            assert stream_finalized.is_set()
            assert not late_event_reached.is_set()
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_pre_start_governance_soft_threshold_compacts_before_attempt(
    tmp_path: Path,
) -> None:
    """soft threshold 在 Attempt 创建前触发一次 proactive compact。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-soft-compact-history",
            event_id="event-soft-compact-history",
            display_text="older compactable material",
            client_request_id="client-soft-compact-history",
            idempotency_key="idem-soft-compact-history",
        )
        seeded = _seed_accepted_run(
            store,
            run_id="run-soft-compact",
            display_text=_soft_threshold_prompt(),
            session_id=session_id,
        )
        assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 0
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(),
            context_compactor=_PreparedManifestProactiveCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)
            event_types = _event_types_for_run(store.transaction_runner, seeded.run_id)
            compacted_payload = _event_payload(
                _latest_event_for_run(
                    store.transaction_runner,
                    seeded.run_id,
                    CONTEXT_COMPACTED,
                )
            )

            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 1
            budget_indexes = tuple(
                index for index, event_type in enumerate(event_types) if event_type == CONTEXT_BUDGET_EVALUATED
            )
            assert len(budget_indexes) == 2
            assert budget_indexes[0] < event_types.index(CONTEXT_COMPACTION_REQUESTED)
            assert event_types.index(CONTEXT_COMPACTION_REQUESTED) < event_types.index(CONTEXT_COMPACTED)
            assert event_types.index(CONTEXT_COMPACTED) < budget_indexes[1]
            assert budget_indexes[1] < event_types.index("RUN_STARTED")
            assert event_types.index("RUN_STARTED") < event_types.index("ATTEMPT_STARTED")
            budget_payloads = tuple(
                parse_context_budget_evaluated_payload(_event_payload(event))
                for event in _events_for_run_by_type(
                    store.transaction_runner,
                    seeded.run_id,
                    CONTEXT_BUDGET_EVALUATED,
                )
            )
            assert tuple(payload.sizing_stage for payload in budget_payloads) == (
                ContextSizingStage.ORDINARY,
                ContextSizingStage.POST_COMPACT,
            )
            assert _run_status(store.transaction_runner, seeded.run_id) == (RunStatus.RUNNING)
            _assert_accepted_payload_has_proposal_manifest(compacted_payload)
        finally:
            await scheduler.close()


@pytest.mark.parametrize(
    "stage",
    (
        ContextSizingStage.ORDINARY,
        ContextSizingStage.POST_COMPACT,
        ContextSizingStage.DISPATCH_FALLBACK,
    ),
)
@pytest.mark.asyncio
async def test_budgeted_allow_stage_orders_manifest_fact_before_start(
    tmp_path: Path,
    stage: ContextSizingStage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """budgeted allow 对三个dispatch stage提交manifest、fact、start。

    :param tmp_path: pytest 临时目录。
    :param stage: 本次dispatch candidate的真实stage。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: stage或EventLog顺序错误时抛出。
    """

    resolver_calls: list[ContextSizingStage] = []

    def resolve_anchor(
        transaction: HostTransaction,
        event_log_store: EventLogStore,
        *,
        candidate: PreparedRunnerCallCandidate,
        context_window_size: int,
        candidate_input_cursor: int | None = None,
    ) -> ContextAnchorResolution:
        """为eligible dispatch stage注入compatible anchor。

        :param transaction: 当前Host transaction。
        :param event_log_store: EventLog primitive。
        :param candidate: complete candidate。
        :param context_window_size: frozen context window。
        :param candidate_input_cursor: 可选scan cursor。
        :returns: compatible anchor。
        """

        del transaction, event_log_store, candidate_input_cursor
        assert context_window_size == 32_768
        resolver_calls.append(stage)
        return ContextAnchorResolution(
            anchor=CompatibleContextAnchor(
                manifest_event_id="event-anchor",
                manifest_payload_ref="payload-anchor",
                manifest_digest=sha256_digest_json({"anchor": "manifest"}),
                iteration_link_event_id="event-anchor-link",
                usage_event_id="event-anchor-usage",
                usage_observation_digest=sha256_digest_json({"anchor": "usage"}),
                iteration_completed_event_id="event-anchor-completed",
                usage_anchor_tokens=100,
                conservative_anchor_tokens=100,
            ),
            fallback_reason=None,
        )

    monkeypatch.setattr(
        host_dispatch,
        "resolve_prepared_runner_call_context_anchor_in_transaction",
        resolve_anchor,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id=f"run-budgeted-allow-{stage.value}",
            display_text="short budgeted input",
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(
                context_window_size=32_768,
                soft_threshold_tokens=30_000,
                hard_threshold_tokens=31_000,
            ),
        )
        try:
            run = _read_run(store.transaction_runner, seeded.run_id)
            scheduler._catch_up_memory_projection_before_candidate(run.session_id)
            outcome = store.transaction_runner.run_write(
                lambda transaction: scheduler._prepare_and_commit_start_in_transaction(
                    transaction,
                    run,
                    stage=stage,
                )
            )

            assert outcome.pending_dispatch is not None
            event_types = _event_types_for_run(
                store.transaction_runner,
                seeded.run_id,
            )
            assert event_types[-4:] == (
                "RUNNER_CALL_INPUT_ASSEMBLED",
                CONTEXT_BUDGET_EVALUATED,
                "RUN_STARTED",
                "ATTEMPT_STARTED",
            )
            fact = parse_context_budget_evaluated_payload(
                _event_payload(
                    _latest_event_for_run(
                        store.transaction_runner,
                        seeded.run_id,
                        CONTEXT_BUDGET_EVALUATED,
                    )
                )
            )
            assert fact.sizing_stage is stage
            if stage is ContextSizingStage.POST_COMPACT:
                assert resolver_calls == []
                assert fact.estimate_method is (ContextEstimateMethod.CONSERVATIVE_FALLBACK)
                assert fact.fallback_reason is (ContextSizingFallbackReason.ACCEPTED_COMPACT_INVALIDATED)
            else:
                assert resolver_calls == [stage]
                assert fact.estimate_method is (ContextEstimateMethod.USAGE_ANCHORED)
                assert fact.anchor_diagnostic is not None
        finally:
            await scheduler.close()


@pytest.mark.parametrize(
    "stage",
    (
        ContextSizingStage.ORDINARY,
        ContextSizingStage.POST_COMPACT,
        ContextSizingStage.DISPATCH_FALLBACK,
    ),
)
@pytest.mark.asyncio
async def test_budgeted_hard_stage_records_fact_before_terminal(
    tmp_path: Path,
    stage: ContextSizingStage,
) -> None:
    """ordinary/post-compact/fallback hard均先写fact再收口。

    :param tmp_path: pytest 临时目录。
    :param stage: 本次hard candidate的真实stage。
    :returns: ``None``。
    :raises AssertionError: fact stage、pressure或terminal顺序错误时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id=f"run-budgeted-hard-{stage.value}",
            display_text=_hard_threshold_prompt(),
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(
                context_window_size=200,
                soft_threshold_tokens=70,
                hard_threshold_tokens=120,
            ),
        )
        try:
            run = _read_run(store.transaction_runner, seeded.run_id)
            scheduler._catch_up_memory_projection_before_candidate(run.session_id)
            outcome = store.transaction_runner.run_write(
                lambda transaction: scheduler._prepare_and_commit_start_in_transaction(
                    transaction,
                    run,
                    stage=stage,
                )
            )

            assert outcome.pending_dispatch is None
            assert outcome.terminal_notice is not None
            event_types = _event_types_for_run(
                store.transaction_runner,
                seeded.run_id,
            )
            fact_index = event_types.index(CONTEXT_BUDGET_EVALUATED)
            assert fact_index < event_types.index("RUN_FAILED")
            fact = parse_context_budget_evaluated_payload(
                _event_payload(
                    _latest_event_for_run(
                        store.transaction_runner,
                        seeded.run_id,
                        CONTEXT_BUDGET_EVALUATED,
                    )
                )
            )
            assert fact.sizing_stage is stage
            assert fact.pressure_level is ContextPressureLevel.HARD_THRESHOLD_EXCEEDED
            assert (
                _attempt_count_for_run(
                    store.transaction_runner,
                    seeded.run_id,
                )
                == 0
            )
        finally:
            await scheduler.close()


@pytest.mark.parametrize("failure_kind", ("precondition", "cas_lost"))
@pytest.mark.asyncio
async def test_budgeted_start_failure_rolls_back_candidate_fact_and_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
) -> None:
    """start precondition miss与CAS lost均回滚candidate/fact/state。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :param failure_kind: 注入owner precondition miss或low-level CAS lost。
    :returns: ``None``。
    :raises AssertionError: transaction留下孤立写入时抛出。
    """

    def reject_start(
        transaction: HostTransaction,
        event_log_store: EventLogStore,
        request: StartGovernedRunInput,
    ) -> RunTransitionResult:
        """在manifest/fact之后注入transition失败。

        :param transaction: Host write transaction。
        :param event_log_store: EventLog primitive。
        :param request: governed start input。
        :returns: precondition场景的``INVALID_STATE``结果。
        :raises HostDurableError: CAS lost场景固定抛出。
        """

        del transaction, event_log_store, request
        if failure_kind == "cas_lost":
            raise HostDurableError("injected governed start CAS lost")
        return RunTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=None,
            attempt=None,
            dispatch_record=None,
            run_event=None,
        )

    monkeypatch.setattr(
        host_dispatch,
        "start_governed_run_with_starting_attempt_in_transaction",
        reject_start,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id=f"run-budgeted-rollback-{failure_kind}",
            display_text="short rollback input",
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(
                context_window_size=32_768,
                soft_threshold_tokens=30_000,
                hard_threshold_tokens=31_000,
            ),
        )
        try:
            run = _read_run(store.transaction_runner, seeded.run_id)
            scheduler._catch_up_memory_projection_before_candidate(run.session_id)
            descriptor_count_before = _table_count(
                store.transaction_runner,
                TABLE_PAYLOAD_DESCRIPTORS,
            )
            expected_error = (
                HostDurableError if failure_kind == "cas_lost" else host_dispatch._StartCandidateCasMissRollback
            )
            with pytest.raises(expected_error):
                store.transaction_runner.run_write(
                    lambda transaction: scheduler._prepare_and_commit_start_in_transaction(
                        transaction,
                        run,
                        stage=ContextSizingStage.ORDINARY,
                    )
                )

            event_types = _event_types_for_run(
                store.transaction_runner,
                seeded.run_id,
            )
            assert "RUNNER_CALL_INPUT_ASSEMBLED" not in event_types
            assert CONTEXT_BUDGET_EVALUATED not in event_types
            assert "RUN_STARTED" not in event_types
            assert "ATTEMPT_STARTED" not in event_types
            assert (
                _attempt_count_for_run(
                    store.transaction_runner,
                    seeded.run_id,
                )
                == 0
            )
            assert (
                _table_count(
                    store.transaction_runner,
                    TABLE_HOST_ATTEMPT_DISPATCH_RECORDS,
                )
                == 0
            )
            assert (
                _table_count(
                    store.transaction_runner,
                    TABLE_PAYLOAD_DESCRIPTORS,
                )
                == descriptor_count_before
            )
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_compact_accepted_hot_path_runs_bounded_memory_catchup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """compact accepted 后在 freeze candidate 前执行有界 memory catch-up。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    """

    original_catch_up = host_dispatch.catch_up_conversation_memory_projection
    observed_max_event_sequences: list[int | None] = []

    def observed_catch_up(
        transaction_runner: HostTransactionRunner,
        *,
        policy: MemoryProjectionPolicy,
        batch_size: int,
        consumer_id: str = CONVERSATION_MEMORY_CONSUMER_ID,
        max_event_sequence: int | None = None,
    ) -> ConversationMemoryProjectionRepairResult:
        """记录 compact accepted 热路径的有界 memory repair。

        :param transaction_runner: Host transaction runner。
        :param policy: memory projection policy。
        :param batch_size: projection page size。
        :param consumer_id: projection consumer id。
        :param max_event_sequence: 目标 EventLog sequence。
        :returns: memory projection repair result。
        :raises Exception: owner catch-up 异常原样透传。
        """

        observed_max_event_sequences.append(max_event_sequence)
        return original_catch_up(
            transaction_runner,
            policy=policy,
            batch_size=batch_size,
            consumer_id=consumer_id,
            max_event_sequence=max_event_sequence,
        )

    monkeypatch.setattr(
        host_dispatch,
        "catch_up_conversation_memory_projection",
        observed_catch_up,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-compact-catchup-history",
            event_id="event-compact-catchup-history",
            display_text="older compactable material",
            client_request_id="client-compact-catchup-history",
            idempotency_key="idem-compact-catchup-history",
        )
        seeded = _seed_accepted_run(
            store,
            run_id="run-compact-no-memory-catchup",
            display_text=_soft_threshold_prompt(),
            session_id=session_id,
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(),
            context_compactor=_PreparedManifestProactiveCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)

            assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 1
            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 1
            assert len(observed_max_event_sequences) == 2
            assert all(sequence is not None for sequence in observed_max_event_sequences)
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_governed_start_sets_dispatch_owner_immediately(
    tmp_path: Path,
) -> None:
    """标准 governed start 在创建 dispatch record 时立即写入 owner。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: dispatch record owner 未立即写入 scheduler
        instance id 时抛出。
    """

    host_identity = HostInstanceIdentity(
        host_instance_id="host-instance-governed-start",
        pid=1,
        process_start_token="process-token-governed-start",
        boot_id=None,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id="run-governed-owner",
            display_text="需要分析当前季度收入。",
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            host_handle_id="host-handle-governed-start",
            host_instance_identity=host_identity,
        )
        try:
            run = _read_run(store.transaction_runner, seeded.run_id)
            pending = _start_governed_for_test(store.transaction_runner, scheduler, run)
            dispatch_record = _read_dispatch_record_by_attempt_id(store.transaction_runner, pending.attempt_id)

            assert dispatch_record.owner_host_instance_id == scheduler.host_instance_id
            assert dispatch_record.owner_host_instance_id is not None
            assert dispatch_record.owner_host_instance_id != "host-handle-governed-start"
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_proactive_compaction_skips_empty_citable_selection(
    tmp_path: Path,
) -> None:
    """selection 无 citable boundary 时走 no-op start，不调用 compactor。"""

    compactor = _RequestCapturingCompactor()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id="run-proactive-selected-material",
            display_text=_soft_threshold_prompt(),
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)

            assert compactor.prepared_requests == []
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 0
            assert (
                _event_count(
                    store.transaction_runner,
                    CONTEXT_COMPACTION_REQUESTED,
                )
                == 0
            )
            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 1
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_proactive_compact_selection_passes_protected_recent_floor(
    tmp_path: Path,
) -> None:
    """normal proactive compact selection 传入 selected recent floor。"""

    compactor = _MinimalSummaryCompactor()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-proactive-floor-old",
            event_id="event-proactive-floor-old-input",
            display_text="older compactable material",
            client_request_id="client-proactive-floor-old",
            idempotency_key="idem-proactive-floor-old",
        )
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-proactive-floor-recent",
            event_id="event-proactive-floor-recent-input",
            display_text="recent protected material",
            client_request_id="client-proactive-floor-recent",
            idempotency_key="idem-proactive-floor-recent",
        )
        seeded = _seed_accepted_run(
            store,
            run_id="run-proactive-floor-current",
            display_text=_soft_threshold_prompt(),
            session_id=session_id,
        )
        memory_policy = _compact_floor_one_memory_policy()
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(
                context_window_size=300,
                soft_threshold_tokens=50,
                hard_threshold_tokens=200,
            ),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=memory_policy,
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)

            request = compactor.prepared_requests[0]
            assert request.segment_selection.policy_digest == (digest_memory_projection_policy(memory_policy))
            assert "eventlog:user:event-proactive-floor-old-input" in request.segment_selection.selected_block_ids
            assert (
                request.segment_selection.excluded_reason_codes["eventlog:user:event-proactive-floor-recent-input"]
                == "protected_recent_raw_floor"
            )
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_proactive_budget_uses_pre_dispatch_material_view(
    tmp_path: Path,
) -> None:
    """proactive budget 使用同源 material view，而不是只估当前输入。"""

    compactor = _MinimalSummaryCompactor()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-proactive-budget-old",
            event_id="event-proactive-budget-old-input",
            display_text=_soft_threshold_prompt(),
            client_request_id="client-proactive-budget-old",
            idempotency_key="idem-proactive-budget-old",
        )
        seeded = _seed_accepted_run(
            store,
            run_id="run-proactive-budget-current",
            display_text="short current question",
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)

            assert len(compactor.prepared_requests) == 1
            request = compactor.prepared_requests[0]
            assert "event-proactive-budget-old-input" in request.material_source_refs
            assert f"event-input-{seeded.run_id}" in request.material_source_refs
            assert request.budget_before_compact.estimated_input_tokens > 20
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_proactive_fallback_payload_appends_current_input_once(
    tmp_path: Path,
) -> None:
    """proactive fallback payload 只追加一次 current input anchor。"""

    current_display_text = "current question needing fallback"
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-proactive-fallback-old",
            event_id="event-proactive-fallback-old-input",
            display_text="old delta input",
            client_request_id="client-proactive-fallback-old",
            idempotency_key="idem-proactive-fallback-old",
        )
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-proactive-fallback-recent",
            event_id="event-proactive-fallback-recent-input",
            display_text="recent protected delta input",
            client_request_id="client-proactive-fallback-recent",
            idempotency_key="idem-proactive-fallback-recent",
        )
        seeded = _seed_accepted_run(
            store,
            run_id="run-proactive-fallback-current",
            display_text=current_display_text,
            session_id=session_id,
        )
        memory_policy = replace(
            _fallback_cap_memory_policy(),
            selected_recent_window_turn_floor=1,
            fallback_selected_recent_window_item_cap=2,
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(
                context_window_size=200,
                soft_threshold_tokens=40,
                hard_threshold_tokens=120,
            ),
            memory_projection_policy=memory_policy,
            compact_artifact_root=tmp_path / "compact-artifacts",
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)

            failed = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_FAILED,
            )
            payload = _event_payload(failed)
            window = payload["fallback_input_window"]
            assert isinstance(window, Mapping)
            selected_block_ids = _required_json_text_tuple(window["selected_block_ids"])
            current_block_id = f"current:event-input-{seeded.run_id}"
            assert selected_block_ids.count(current_block_id) == 1
            assert "eventlog:user:event-proactive-fallback-recent-input" in (selected_block_ids)
            assert window["current_input_ref"] == f"event-input-{seeded.run_id}"
            assert payload["fallback_action"] == "dispatch"
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_second_proactive_compact_uses_previous_view_without_old_raw_replay(
    tmp_path: Path,
) -> None:
    """第二次 proactive compact 使用 previous view，不重展旧 raw material。"""

    compactor = _MinimalSummaryCompactor()
    with open_host_durable_store(_options(tmp_path)) as store:
        factory = _FinalAnswerWorkerFactory()
        session_id = _ensure_session_id(store.transaction_runner)
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-proactive-rolling-old",
            event_id="event-proactive-rolling-old-input",
            display_text="old",
            client_request_id="client-proactive-rolling-old",
            idempotency_key="idem-proactive-rolling-old",
        )
        first = _seed_accepted_run(
            store,
            run_id="run-proactive-rolling-first",
            display_text=_soft_threshold_prompt(),
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            context_budget_policy=_soft_compact_policy(
                context_window_size=400,
                soft_threshold_tokens=50,
                hard_threshold_tokens=300,
            ),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        try:
            await scheduler.run_queue_promotion(first.session_id)
            assert len(compactor.prepared_requests) == 1
            assert compactor.prepared_requests[0].material_pack.trace_material != ()
            await _wait_for_final_request_count(factory, 1)
            await _wait_for_run_status(
                store.transaction_runner,
                first.run_id,
                expected_run=RunStatus.SUCCEEDED,
            )

            second = _seed_accepted_run(
                store,
                run_id="run-proactive-rolling-second",
                display_text=_soft_threshold_prompt(),
            )
            await scheduler.run_queue_promotion(second.session_id)

            assert len(compactor.prepared_requests) == 2
            second_request = compactor.prepared_requests[1]
            assert second_request.material_pack.previous_compacted_view != ()
            assert all(block.text != "old" for block in second_request.material_pack.trace_material)
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_proactive_material_pack_not_larger_than_ordinary_material_for_same_view(
    tmp_path: Path,
) -> None:
    """proactive material pack 与 ordinary material 使用同一去重视图。"""

    compactor = _RequestCapturingCompactor()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-proactive-material-size-history",
            event_id="event-proactive-material-size-history",
            display_text="older compactable material",
            client_request_id="client-proactive-material-size-history",
            idempotency_key="idem-proactive-material-size-history",
        )
        seeded = _seed_accepted_run(
            store,
            run_id="run-proactive-material-size",
            display_text=_soft_threshold_prompt(),
            session_id=session_id,
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)

            request = compactor.prepared_requests[0]
            ordinary_chars = len(_soft_threshold_prompt())
            pack_chars = len(str(request.llm_material_json()))
            assert pack_chars <= ordinary_chars + 512
            _assert_accepted_payload_has_proposal_manifest(
                _event_payload(
                    _latest_event_for_run(
                        store.transaction_runner,
                        seeded.run_id,
                        CONTEXT_COMPACTED,
                    )
                )
            )
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_wake_queue_promotion_uses_tracked_async_promotion_task(
    tmp_path: Path,
) -> None:
    """sync wakeup 入队后由 scheduler 管理的 promotion task 完成 compact。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-wake-soft-compact-history",
            event_id="event-wake-soft-compact-history",
            display_text="older compactable material",
            client_request_id="client-wake-soft-compact-history",
            idempotency_key="idem-wake-soft-compact-history",
        )
        seeded = _seed_accepted_run(
            store,
            run_id="run-wake-soft-compact",
            display_text=_soft_threshold_prompt(),
            session_id=session_id,
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(),
            context_compactor=_PreparedManifestProactiveCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        try:
            scheduler.wake_queue_promotion(seeded.session_id)
            await _wait_for_event_count(
                store.transaction_runner,
                CONTEXT_COMPACTED,
                expected_count=1,
            )

            assert scheduler._promotion_drain_task is not None
            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 1
            assert CONTEXT_COMPACTED in _event_types_for_run(store.transaction_runner, seeded.run_id)
            _assert_accepted_payload_has_proposal_manifest(
                _event_payload(
                    _latest_event_for_run(
                        store.transaction_runner,
                        seeded.run_id,
                        CONTEXT_COMPACTED,
                    )
                )
            )
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_wake_queue_promotion_logs_promotion_task_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """promotion drain task 捕获并记录异常，避免 silent task exception。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        scheduler = await _open_scheduler(tmp_path, store, _FakeWorkerFactory())

        async def _raising_promotion(session_id: str) -> bool:
            """模拟 promotion 内部异常。

            :param session_id: promotion session id。
            :returns: 不返回。
            :raises RuntimeError: 始终抛出测试异常。
            """

            del session_id
            raise RuntimeError("promotion failed")

        monkeypatch.setattr(
            scheduler,
            "_signal_pre_start_governance",
            _raising_promotion,
        )
        try:
            with caplog.at_level(logging.WARNING):
                scheduler.wake_queue_promotion("session-promotion-error")
                await _wait_for_log_message(
                    caplog,
                    "dispatch.queue_promotion.runtime_error",
                )

            assert scheduler._promotion_drain_task is not None
            assert scheduler._promotion_drain_task.done() is False
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_wake_queue_promotion_requeues_after_transient_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """promotion transient exception 后同一 session wakeup 会被重投。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: retry 次数不是精确两次时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        scheduler = await _open_scheduler(tmp_path, store, _FakeWorkerFactory())
        reconciliation_task = scheduler._owned_session_reconciliation_task
        assert reconciliation_task is not None
        reconciliation_task.cancel()
        await host_dispatch._suppress_task_cancel(reconciliation_task)
        attempts = 0
        recovered = asyncio.Event()

        async def _flaky_promotion(session_id: str) -> bool:
            """第一次失败，第二次记录恢复。

            :param session_id: promotion session id。
            :returns: 第二次及后续调用返回未 dispatch。
            :raises RuntimeError: 第一次调用时模拟 transient failure。
            """

            nonlocal attempts
            assert session_id == "session-promotion-retry"
            attempts += 1
            if attempts == 1:
                raise RuntimeError("promotion transient")
            recovered.set()
            return False

        monkeypatch.setattr(
            scheduler,
            "_signal_pre_start_governance",
            _flaky_promotion,
        )
        try:
            scheduler.wake_queue_promotion("session-promotion-retry")
            await asyncio.wait_for(recovered.wait(), timeout=1)

            assert attempts == 2
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_pre_start_flight_coalesces_wake_periodic_and_direct_signals(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同 Session 多 signal 只形成 sole flight 与一个 fresh no-op pass。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: signal 未合并、pass 未 fresh 重读或 flight 泄漏时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            dispatch_poll_interval_seconds=60.0,
        )
        first_pass_entered = asyncio.Event()
        release_first_pass = asyncio.Event()
        pass_count = 0

        async def _barrier_pass(
            session_id: str,
            *,
            work_lease: SessionWorkLease,
        ) -> bool:
            """阻塞首个 pass，并让 coalesced pass 执行 fresh no-op。

            :param session_id: 当前 Session id。
            :param work_lease: 当前 pass 独占生命周期的 fresh lease。
            :returns: 始终返回未创建 dispatch。
            :raises AssertionError: Session 或 lease 类型漂移时抛出。
            """

            nonlocal pass_count
            assert session_id == "session-flight-coalesced"
            assert isinstance(work_lease, SessionWorkLease)
            pass_count += 1
            if pass_count == 1:
                first_pass_entered.set()
                await release_first_pass.wait()
            return False

        monkeypatch.setattr(
            scheduler,
            "_run_queue_promotion_with_lease",
            _barrier_pass,
        )
        first_signal = asyncio.create_task(scheduler.run_queue_promotion("session-flight-coalesced"))
        try:
            await asyncio.wait_for(first_pass_entered.wait(), timeout=1)
            scheduler.wake_queue_promotion("session-flight-coalesced")
            scheduler.wake_queue_promotion("session-flight-coalesced")
            periodic_signal = asyncio.create_task(scheduler.reconcile_owned_sessions_once(fixed_now=_NOW))
            direct_signal = asyncio.create_task(scheduler.run_queue_promotion("session-flight-coalesced"))
            await asyncio.sleep(0)

            assert len(scheduler._pre_start_flights) == 1
            assert scheduler._pre_start_flights["session-flight-coalesced"].rerun_requested is True

            release_first_pass.set()
            await asyncio.gather(first_signal, periodic_signal, direct_signal)

            assert pass_count == 2
            assert scheduler._pre_start_flights == {}
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_live_compactor_flight_coalesces_wake_and_periodic_without_recovery(
    tmp_path: Path,
) -> None:
    """实际 compactor await 期间的多 signal 只要求 fresh no-op pass。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: live provider 被误恢复、attempt 重复或 flight 泄漏时抛出。
    """

    blocker = _BlockingAfterManifestCompactor()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-live-compactor-history",
            event_id="event-live-compactor-history",
            display_text="older compactable material",
            client_request_id="client-live-compactor-history",
            idempotency_key="idem-live-compactor-history",
        )
        seeded = _seed_accepted_run(
            store,
            run_id="run-live-compactor-coalesced-flight",
            display_text=_soft_threshold_prompt(),
            session_id=session_id,
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(accepted_handle=_CloseCountingHandle()),
            context_budget_policy=_soft_compact_policy(
                max_compaction_attempts_per_operation=2,
            ),
            context_compactor=blocker,
            compact_artifact_root=tmp_path / "compact-artifacts",
            dispatch_poll_interval_seconds=60.0,
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        promotion = asyncio.create_task(scheduler.run_queue_promotion(seeded.session_id))
        try:
            await asyncio.wait_for(blocker.provider_entered.wait(), timeout=2.0)
            flight = scheduler._pre_start_flights[seeded.session_id]
            projection_at_barrier = _read_proactive_projection(
                store.transaction_runner,
                session_id=seeded.session_id,
                run_id=seeded.run_id,
            )

            assert len(scheduler._pre_start_flights) == 1
            assert flight.task.done() is False
            assert flight.rerun_requested is False
            assert blocker.provider_calls == 1
            assert len(blocker.prepared_requests) == 1
            assert projection_at_barrier.state.prepared_attempt_numbers == (1,)
            assert (
                _event_types_for_run(
                    store.transaction_runner,
                    seeded.run_id,
                ).count(CONTEXT_COMPACTION_REQUESTED)
                == 1
            )
            assert (
                _events_for_run_by_type(
                    store.transaction_runner,
                    seeded.run_id,
                    CONTEXT_COMPACTED,
                )
                == ()
            )
            assert (
                _events_for_run_by_type(
                    store.transaction_runner,
                    seeded.run_id,
                    CONTEXT_COMPACTION_FAILED,
                )
                == ()
            )

            periodic_signal = asyncio.create_task(scheduler.reconcile_owned_sessions_once(fixed_now=_NOW))
            await asyncio.sleep(0)
            assert periodic_signal.done() is False
            assert scheduler._pre_start_flights[seeded.session_id] is flight
            assert flight.rerun_requested is True

            scheduler.wake_queue_promotion(seeded.session_id)
            scheduler.wake_queue_promotion(seeded.session_id)
            assert len(scheduler._pre_start_flights) == 1
            assert scheduler._pre_start_flights[seeded.session_id] is flight
            assert blocker.provider_calls == 1
            assert len(blocker.prepared_requests) == 1
            assert _read_proactive_projection(
                store.transaction_runner,
                session_id=seeded.session_id,
                run_id=seeded.run_id,
            ).state.prepared_attempt_numbers == (1,)

            blocker.provider_release.set()
            await asyncio.gather(promotion, periodic_signal)

            completed = _read_proactive_projection(
                store.transaction_runner,
                session_id=seeded.session_id,
                run_id=seeded.run_id,
            )
            event_types = _event_types_for_run(
                store.transaction_runner,
                seeded.run_id,
            )
            terminal_count = event_types.count(CONTEXT_COMPACTED) + (event_types.count(CONTEXT_COMPACTION_FAILED))
            assert scheduler._pre_start_flights == {}
            assert blocker.provider_calls == 1
            assert blocker.calls == 1
            assert len(blocker.prepared_requests) == 1
            assert event_types.count(CONTEXT_COMPACTION_REQUESTED) == 1
            assert terminal_count == 1
            assert event_types.count(CONTEXT_COMPACTED) == 1
            assert completed.state.phase is ProactiveCompactionPhase.COMPACTED
            assert completed.state.prepared_attempt_numbers == (1,)
            assert _run_status(store.transaction_runner, seeded.run_id) == (RunStatus.RUNNING)
        finally:
            blocker.provider_release.set()
            await scheduler.close()


@pytest.mark.asyncio
async def test_pre_start_flight_exit_boundary_signal_starts_fresh_flight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """flight 无 await 删除后的 signal 必须启动新的 fresh flight。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: exit-boundary signal 丢失或复用旧 flight 时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            dispatch_poll_interval_seconds=60.0,
        )
        second_flight_entered = asyncio.Event()
        pass_count = 0

        async def _exit_boundary_pass(
            session_id: str,
            *,
            work_lease: SessionWorkLease,
        ) -> bool:
            """首个 pass 返回前排队 signal，第二个 fresh flight 留下证据。

            :param session_id: 当前 Session id。
            :param work_lease: 当前 pass 的 fresh lease。
            :returns: 始终返回未创建 dispatch。
            :raises AssertionError: Session 或 lease 类型漂移时抛出。
            """

            nonlocal pass_count
            assert session_id == "session-flight-exit-boundary"
            assert isinstance(work_lease, SessionWorkLease)
            pass_count += 1
            if pass_count == 1:
                asyncio.get_running_loop().call_soon(
                    scheduler.wake_queue_promotion,
                    session_id,
                )
            else:
                second_flight_entered.set()
            return False

        monkeypatch.setattr(
            scheduler,
            "_run_queue_promotion_with_lease",
            _exit_boundary_pass,
        )
        try:
            await scheduler.run_queue_promotion("session-flight-exit-boundary")
            await asyncio.wait_for(second_flight_entered.wait(), timeout=1)

            assert pass_count == 2
            assert scheduler._pre_start_flights == {}
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_pre_start_flight_is_parallel_per_session_and_close_owned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不同 Session 可并行，awaiter 取消不取消 flight，close 统一收口。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: flight 被 caller 取消、跨 Session 串行或 close 泄漏时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            dispatch_poll_interval_seconds=60.0,
        )
        entered = {
            "session-flight-a": asyncio.Event(),
            "session-flight-b": asyncio.Event(),
        }
        blocker = asyncio.Event()

        async def _parallel_pass(
            session_id: str,
            *,
            work_lease: SessionWorkLease,
        ) -> bool:
            """记录两个 Session 并行进入并等待 scheduler close。

            :param session_id: 当前 Session id。
            :param work_lease: 当前 pass 的 fresh lease。
            :returns: blocker 被释放后返回未创建 dispatch。
            :raises AssertionError: Session 或 lease 类型漂移时抛出。
            """

            assert isinstance(work_lease, SessionWorkLease)
            entered[session_id].set()
            await blocker.wait()
            return False

        monkeypatch.setattr(
            scheduler,
            "_run_queue_promotion_with_lease",
            _parallel_pass,
        )
        first = asyncio.create_task(scheduler.run_queue_promotion("session-flight-a"))
        second = asyncio.create_task(scheduler.run_queue_promotion("session-flight-b"))
        await asyncio.wait_for(entered["session-flight-a"].wait(), timeout=1)
        await asyncio.wait_for(entered["session-flight-b"].wait(), timeout=1)

        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert scheduler._pre_start_flights["session-flight-a"].task.done() is False
        assert scheduler._pre_start_flights["session-flight-b"].task.done() is False

        await scheduler.close()

        with pytest.raises(asyncio.CancelledError):
            await second
        assert scheduler._pre_start_flights == {}


@pytest.mark.asyncio
async def test_scheduler_close_cancels_tracked_promotion_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """scheduler close 会取消 promotion task，但不无限 drain 本地 promotion queue。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        scheduler = await _open_scheduler(tmp_path, store, _FakeWorkerFactory())
        blocker = asyncio.Event()
        promotion_started = asyncio.Event()

        async def _blocked_promotion(session_id: str) -> bool:
            """模拟长期运行的 promotion。

            :param session_id: promotion session id。
            :returns: blocker 被释放后返回未 dispatch。
            :raises asyncio.CancelledError: scheduler close 取消时透传。
            """

            del session_id
            promotion_started.set()
            await blocker.wait()
            return False

        monkeypatch.setattr(
            scheduler,
            "_signal_pre_start_governance",
            _blocked_promotion,
        )
        scheduler.wake_queue_promotion("session-promotion-close")
        await _wait_for_promotion_task_started(scheduler)
        await promotion_started.wait()
        promotion_task = scheduler._promotion_drain_task
        assert promotion_task is not None
        scheduler._promotion_queue.put_nowait("session-promotion-pending")
        event_log_cursor = _event_log_cursor(store.transaction_runner)

        await scheduler.close()

        assert promotion_task.done() is True
        assert scheduler._promotion_queue.qsize() == 1
        _assert_scheduler_close_did_not_append_terminal_facts(
            store.transaction_runner,
            after_cursor=event_log_cursor,
        )


@pytest.mark.asyncio
async def test_scheduler_wake_methods_fail_after_close_and_close_is_idempotent(
    tmp_path: Path,
) -> None:
    """scheduler close 后 wake 方法稳定失败，重复 close 保持幂等。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, _FakeWorkerFactory())

        await scheduler.close()
        await scheduler.close()

        with pytest.raises(HostApiError) as dispatch_error:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
        assert dispatch_error.value.code is HostApiErrorCode.UNAVAILABLE
        with pytest.raises(HostApiError) as promotion_error:
            scheduler.wake_queue_promotion(seeded.session_id)
        assert promotion_error.value.code is HostApiErrorCode.UNAVAILABLE
        with pytest.raises(HostApiError) as watchdog_error:
            scheduler.wake_active_cancel_watchdog(seeded.session_id)
        assert watchdog_error.value.code is HostApiErrorCode.UNAVAILABLE
        assert scheduler._promotion_queue.qsize() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("component", ("heartbeat", "dispatch", "promotion"))
async def test_critical_task_exception_reports_typed_fatal_to_shared_health(
    tmp_path: Path,
    component: str,
) -> None:
    """critical task 非预期异常只向 shared health 提交稳定 typed fatal。

    :param tmp_path: pytest 临时目录。
    :param component: 预期写入 typed detail 的 critical component。
    :returns: ``None``。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
        )

        async def fail_critical_task() -> None:
            """抛出不会进入 public detail 的固定测试异常。

            :returns: 不会返回。
            :raises RuntimeError: 始终抛出。
            """

            raise RuntimeError("private provider diagnostic must not leak")

        try:
            await scheduler._supervise_critical_task(
                fail_critical_task,
                component=component,
            )
            assert scheduler._health_gate.state is HostExecutionHealthState.UNAVAILABLE
            with pytest.raises(HostApiError) as exc_info:
                scheduler.wake_dispatch(
                    PendingDispatchRecord(
                        dispatch_record_id="dispatch-fatal",
                        run_id="run-fatal",
                        attempt_id="attempt-fatal",
                        execution_id="execution-fatal",
                        execution_target="target-fatal",
                        worker_kind=WorkerKind.LOCAL,
                    )
                )
            assert exc_info.value.code is HostApiErrorCode.UNAVAILABLE
            assert exc_info.value.retryable is True
            assert isinstance(exc_info.value.detail, HostUnavailableDetail)
            assert exc_info.value.detail.component == component
            assert exc_info.value.detail.reason_code == "critical_task_unexpected_exit"
            assert "private provider diagnostic" not in str(exc_info.value.detail)
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_proactive_compaction_calls_llm_outside_write_transaction(
    tmp_path: Path,
) -> None:
    """proactive compactor 外部调用不持有 Host write transaction。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-proactive-outside-history",
            event_id="event-proactive-outside-history",
            display_text="older compactable material",
            client_request_id="client-proactive-outside-history",
            idempotency_key="idem-proactive-outside-history",
        )
        seeded = _seed_accepted_run(
            store,
            run_id="run-proactive-outside-transaction",
            display_text=_soft_threshold_prompt(),
            session_id=session_id,
        )
        compactor = _TransactionReadableCompactor(store.transaction_runner)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)

            assert compactor.calls == 1
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 1
            _assert_accepted_payload_has_proposal_manifest(
                _event_payload(
                    _latest_event_for_run(
                        store.transaction_runner,
                        seeded.run_id,
                        CONTEXT_COMPACTED,
                    )
                )
            )
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_proactive_compaction_rechecks_durable_state_after_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """manifest commit 后 Run 失效时，durable token 阻止 provider 调用。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-stale-manifest-history",
            event_id="event-stale-manifest-history",
            display_text="older compactable material",
            client_request_id="client-stale-manifest-history",
            idempotency_key="idem-stale-manifest-history",
        )
        seeded = _seed_accepted_run(
            store,
            run_id="run-proactive-stale-after-manifest",
            display_text=_soft_threshold_prompt(),
            session_id=session_id,
        )
        compactor = _PreparedManifestProactiveCompactor()
        original_record = DurableCompactorProposalManifestRecorder.record_compactor_proposal_manifest

        def record_then_fail_run(
            recorder: DurableCompactorProposalManifestRecorder,
            *,
            request: CompactionRequest,
            prepared_input: CompactorProposalRunInput,
            compaction_operation_id: str,
            compaction_attempt_number: int,
        ) -> CompactorProposalManifestReference:
            """提交真实 manifest 后在独立事务中让 Run 失效。

            :param recorder: durable manifest recorder。
            :param request: frozen compaction request。
            :param prepared_input: 已准备的 provider input。
            :param compaction_operation_id: compaction operation id。
            :param compaction_attempt_number: attempt 序号。
            :returns: 已提交的 manifest reference。
            """

            reference = original_record(
                recorder,
                request=request,
                prepared_input=prepared_input,
                compaction_operation_id=compaction_operation_id,
                compaction_attempt_number=compaction_attempt_number,
            )
            _fail_unstarted_for_stale_test(store.transaction_runner, request)
            return reference

        monkeypatch.setattr(
            DurableCompactorProposalManifestRecorder,
            "record_compactor_proposal_manifest",
            record_then_fail_run,
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)

            assert compactor.calls == 0
            assert _run_status(store.transaction_runner, seeded.run_id) is RunStatus.FAILED
            assert (
                _event_count(
                    store.transaction_runner,
                    "RUNNER_CALL_INPUT_ASSEMBLED",
                )
                == 1
            )
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 0
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_compaction_stale_result_does_not_write_compacted_event(
    tmp_path: Path,
) -> None:
    """proactive compact 返回后状态已变化时不写 ``CONTEXT_COMPACTED``。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-stale-result-history",
            event_id="event-stale-result-history",
            display_text="older compactable material",
            client_request_id="client-stale-result-history",
            idempotency_key="idem-stale-result-history",
        )
        seeded = _seed_accepted_run(
            store,
            run_id="run-proactive-stale-result",
            display_text=_soft_threshold_prompt(),
            session_id=session_id,
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(),
            context_compactor=_StaleMutatingCompactor(store.transaction_runner),
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)

            assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 0
            assert _run_status(store.transaction_runner, seeded.run_id) == (RunStatus.FAILED)
            failed = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_FAILED,
            )
            requested = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_REQUESTED,
            )
            payload = _event_payload(failed)
            assert payload["failure_reason"] == "stale_compaction_result"
            assert_failed_payload_no_fallback(
                payload,
                expected_operation_id=requested.event_id,
                expected_attempt_count=1,
                expected_retry_repair_budget_exhausted=False,
            )
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_proactive_late_accepted_result_preserves_first_failed_truth(
    tmp_path: Path,
) -> None:
    """I0543 late accepted result 只保留 provider 前已提交的 manifest evidence。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: late loser 改写 first truth 或产生副作用时抛出。
    """

    artifact_root = tmp_path / "compact-artifacts"
    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run_with_compactable_history(
            store,
            run_id="run-proactive-first-terminal-wins",
            display_text=_soft_threshold_prompt(),
        )
        descriptor_count_before = _payload_descriptor_count(store.transaction_runner)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            context_budget_policy=_soft_compact_policy(),
            context_compactor=_TerminalWinningProactiveCompactor(store.transaction_runner),
            compact_artifact_root=artifact_root,
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)

            failed = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_FAILED,
            )
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTION_FAILED) == 1
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 0
            assert (
                _event_count(
                    store.transaction_runner,
                    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
                )
                == 0
            )
            assert (
                _event_count(
                    store.transaction_runner,
                    "RUNNER_CALL_INPUT_ASSEMBLED",
                )
                == 1
            )
            assert _event_payload(failed)["failure_reason"] == ("concurrent_governance_winner")
            assert _event_count(store.transaction_runner, "RUN_STARTED") == 0
            assert (
                _attempt_count_for_run(
                    store.transaction_runner,
                    seeded.run_id,
                )
                == 0
            )
            assert factory.created == 0
            assert _compact_artifact_files(artifact_root) == ()
            descriptor_count_after = _payload_descriptor_count(store.transaction_runner)
            assert descriptor_count_after == (descriptor_count_before + _COMPACTOR_PROPOSAL_DESCRIPTOR_COUNT)
        finally:
            await scheduler.close()


@pytest.mark.parametrize("winner_compacted", (True, False))
@pytest.mark.asyncio
async def test_proactive_same_operation_terminal_contenders_preserve_first_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    winner_compacted: bool,
) -> None:
    """两个 proactive outcome contender 的相反顺序只提交 first truth。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :param winner_compacted: 首个获准 outcome 是否为 compacted。
    :returns: ``None``。
    :raises AssertionError: late loser 写 artifact/event/fallback/start 时抛出。
    """

    artifact_root = tmp_path / "compact-artifacts"
    compactor = _PreparedManifestProactiveCompactor()
    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run_with_compactable_history(
            store,
            run_id=("run-proactive-contender-compacted" if winner_compacted else "run-proactive-contender-failed"),
            display_text=_soft_threshold_prompt(),
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            context_budget_policy=_soft_compact_policy(
                max_compaction_attempts_per_operation=1,
            ),
            context_compactor=compactor,
            compact_artifact_root=artifact_root,
            dispatch_poll_interval_seconds=60.0,
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        captured: list[host_dispatch._GovernanceCompactPending] = []
        original_execute = scheduler._execute_proactive_compaction

        async def _capture_pending(
            pending: host_dispatch._GovernanceCompactPending,
        ) -> host_dispatch._ProactiveCompactionExecutionResult:
            """只捕获 request-owned pending，不提交 outcome。

            :param pending: 已持久化 proactive request 的 pending 摘要。
            :returns: 不含 durable 后续动作的执行结果。
            :raises Exception: 不主动抛出异常。
            """

            captured.append(pending)
            return host_dispatch._ProactiveCompactionExecutionResult(
                compacted_event_sequence=None,
                pending_dispatch=None,
            )

        monkeypatch.setattr(
            scheduler,
            "_execute_proactive_compaction",
            _capture_pending,
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)
            assert len(captured) == 1
            pending = captured[0]
            monkeypatch.setattr(
                scheduler,
                "_execute_proactive_compaction",
                original_execute,
            )
            original_attempt = host_dispatch.run_compaction_attempt
            entered_count = 0
            both_entered = asyncio.Event()
            releases = (asyncio.Event(), asyncio.Event())

            async def _contending_attempt(
                *,
                request: CompactionRequest,
                compactor: ContextCompactor,
                attempt_number: int,
                max_attempt_number: int,
                cancellation_token: CancellationToken,
                compaction_operation_id: str | None = None,
                proposal_manifest_recorder: (DurableCompactorProposalManifestRecorder | None) = None,
                memory_policy: MemoryProjectionPolicy,
                repair_feedback: CompactRepairFeedbackV2 | None,
            ) -> CompactionOperationResult:
                """在 provider/manifest 完成后 barrier 两个相反 outcome。

                :param request: 当前 frozen attempt request。
                :param compactor: proactive compactor。
                :param attempt_number: 当前全局 attempt number。
                :param max_attempt_number: frozen max attempt number。
                :param cancellation_token: durable Run cancellation token。
                :param compaction_operation_id: request 同源 operation id。
                :param proposal_manifest_recorder: durable manifest recorder。
                    :param memory_policy: Context Governance 使用的 Memory policy。
                    :param repair_feedback: 前次 semantic validation feedback。
                :returns: 当前 contender 的 accepted 或 failed outcome。
                :raises Exception: 真实 proposal attempt 或 barrier 失败时透传。
                """

                nonlocal entered_count
                accepted = await original_attempt(
                    request=request,
                    compactor=compactor,
                    attempt_number=attempt_number,
                    max_attempt_number=max_attempt_number,
                    cancellation_token=cancellation_token,
                    compaction_operation_id=compaction_operation_id,
                    proposal_manifest_recorder=proposal_manifest_recorder,
                    memory_policy=memory_policy,
                    repair_feedback=repair_feedback,
                )
                contender_index = entered_count
                entered_count += 1
                if entered_count == 2:
                    both_entered.set()
                await releases[contender_index].wait()
                contender_compacted = winner_compacted if contender_index == 0 else not winner_compacted
                if contender_compacted:
                    return accepted
                return CompactionOperationResult(
                    accepted_truth=None,
                    rejected_attempts=(),
                    failure_reason="contending_provider_failure",
                    budget_after_attempted_compact=None,
                    accepted_attempt_number=None,
                    accepted_successful_response_identity=None,
                    accepted_proposal_manifest_reference=None,
                )

            monkeypatch.setattr(
                host_dispatch,
                "run_compaction_attempt",
                _contending_attempt,
            )
            first = asyncio.create_task(original_execute(pending))
            late = asyncio.create_task(original_execute(pending))
            await asyncio.wait_for(both_entered.wait(), timeout=1)

            releases[0].set()
            winner = await first
            first_terminal_type = CONTEXT_COMPACTED if winner_compacted else CONTEXT_COMPACTION_FAILED
            first_terminal = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                first_terminal_type,
            )
            cursor_after_winner = _event_log_cursor(store.transaction_runner)
            descriptor_count_after_winner = _payload_descriptor_count(store.transaction_runner)
            artifacts_after_winner = _compact_artifact_files(artifact_root)
            run_started_after_winner = _event_count(
                store.transaction_runner,
                "RUN_STARTED",
            )
            attempt_count_after_winner = _attempt_count_for_run(
                store.transaction_runner,
                seeded.run_id,
            )
            if winner_compacted:
                assert winner.compacted_event_sequence == (first_terminal.event_sequence)
                assert winner.pending_dispatch is None
            else:
                assert winner.compacted_event_sequence is None
                assert winner.pending_dispatch is not None

            releases[1].set()
            loser = await late

            assert loser.compacted_event_sequence is None
            assert loser.pending_dispatch is None
            assert (
                _event_log_types_after_cursor(
                    store.transaction_runner,
                    cursor_after_winner,
                )
                == ()
            )
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == (1 if winner_compacted else 0)
            assert _event_count(
                store.transaction_runner,
                CONTEXT_COMPACTION_FAILED,
            ) == (0 if winner_compacted else 1)
            assert (
                _event_count(
                    store.transaction_runner,
                    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
                )
                == 0
            )
            assert (
                _latest_event_for_run(
                    store.transaction_runner,
                    seeded.run_id,
                    first_terminal_type,
                ).event_id
                == first_terminal.event_id
            )
            if not winner_compacted:
                assert _event_payload(first_terminal)["failure_reason"] == ("contending_provider_failure")
            assert _compact_artifact_files(artifact_root) == artifacts_after_winner
            assert len(artifacts_after_winner) == (1 if winner_compacted else 0)
            assert _payload_descriptor_count(store.transaction_runner) == descriptor_count_after_winner
            assert (
                _event_count(
                    store.transaction_runner,
                    "RUN_STARTED",
                )
                == run_started_after_winner
            )
            assert (
                _attempt_count_for_run(
                    store.transaction_runner,
                    seeded.run_id,
                )
                == attempt_count_after_winner
            )
            assert run_started_after_winner == (0 if winner_compacted else 1)
            assert attempt_count_after_winner == (0 if winner_compacted else 1)
            assert factory.created == 0
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_proactive_invalid_multiple_terminals_fail_closed_without_third_or_start(
    tmp_path: Path,
) -> None:
    """proactive caller 对 INVALID_MULTIPLE 抛稳定错误且不改写 first truth。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: caller 追加第三 terminal、artifact 或 start 时抛出。
    """

    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id="run-proactive-invalid-multiple",
            display_text=_soft_threshold_prompt(),
        )
        operation_id = "operation-proactive-invalid-multiple"
        _append_proactive_compaction_requested(
            store.transaction_runner,
            seeded=seeded,
            event_id=operation_id,
        )
        _append_duplicate_proactive_failed_terminals(
            store.transaction_runner,
            seeded=seeded,
            operation_id=operation_id,
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            context_budget_policy=_soft_compact_policy(),
            context_compactor=_PreparedManifestProactiveCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        )
        try:
            with pytest.raises(
                HostDurableError,
                match=COMPACTION_TERMINAL_INVALID_MULTIPLE_ERROR,
            ):
                await scheduler.run_queue_promotion(seeded.session_id)

            assert (
                _event_count(
                    store.transaction_runner,
                    CONTEXT_COMPACTION_FAILED,
                )
                == 2
            )
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 0
            assert _event_count(store.transaction_runner, "RUN_STARTED") == 0
            assert (
                _attempt_count_for_run(
                    store.transaction_runner,
                    seeded.run_id,
                )
                == 0
            )
            assert factory.created == 0
            assert _compact_artifact_files(tmp_path / "compact-artifacts") == ()
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_proactive_compaction_retries_quality_rejection_before_accept(
    tmp_path: Path,
) -> None:
    """proactive compact 首次 quality rejection 后 retry 并写入 accepted fact。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: repair attempt 或 formal trace identity 不同源时抛出。
    """

    compactor = _QualityRejectOnceCompactor()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run_with_compactable_history(
            store,
            run_id="run-proactive-quality-retry",
            display_text=_soft_threshold_prompt(),
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(
                max_compaction_attempts_per_operation=2,
            ),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)
            event_types = _event_types_for_run(store.transaction_runner, seeded.run_id)

            assert compactor.calls == 2
            assert compactor.prepared_inputs[0].repair_feedback is None
            repair_feedback = compactor.prepared_inputs[1].repair_feedback
            assert repair_feedback is not None
            assert repair_feedback.previous_attempt_number == 1
            assert repair_feedback.issues[0].json_path.startswith('$["diagnostics"][0]')
            assert compactor.prepared_inputs[1].compact_input == compactor.prepared_inputs[0].compact_input
            assert (
                _event_count(
                    store.transaction_runner,
                    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
                )
                == 1
            )
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 1
            assert event_types.index(CONTEXT_COMPACTION_ATTEMPT_REJECTED) < (event_types.index(CONTEXT_COMPACTED))
            assert event_types.index(CONTEXT_COMPACTED) < event_types.index("RUN_STARTED")
            assert _run_status(store.transaction_runner, seeded.run_id) == (RunStatus.RUNNING)
            rejected = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_ATTEMPT_REJECTED,
            )
            rejected_payload = _event_payload(rejected)
            compacted_payload = _event_payload(
                _latest_event_for_run(
                    store.transaction_runner,
                    seeded.run_id,
                    CONTEXT_COMPACTED,
                )
            )
            assert rejected_payload["failure_category"] == ("quality_check_rejected")
            _assert_rejected_payload_has_proposal_manifest(rejected_payload)
            _assert_accepted_payload_has_proposal_manifest(compacted_payload)
            _resolve_and_assert_compactor_calls(
                store.transaction_runner,
                tmp_path=tmp_path,
                run_id=seeded.run_id,
                prepared_inputs=tuple(compactor.prepared_inputs),
                attempt_payloads=(rejected_payload, compacted_payload),
                accepted_attempt_number=2,
            )
        finally:
            await scheduler.close()


@pytest.mark.parametrize(
    ("crash_attempt_number", "expected_resume_stage"),
    (
        (1, ProactiveCompactionAttemptStage.ROOT_REPAIR),
        (2, ProactiveCompactionAttemptStage.TIER_1_FALLBACK_CAPS),
        (3, ProactiveCompactionAttemptStage.TIER_2_SECTION_DEGRADE),
        (4, ProactiveCompactionAttemptStage.TIER_3_DELTA_ONLY),
        (5, None),
    ),
)
@pytest.mark.asyncio
async def test_proactive_manifest_crash_resumes_deterministic_next_stage(
    tmp_path: Path,
    crash_attempt_number: int,
    expected_resume_stage: ProactiveCompactionAttemptStage | None,
) -> None:
    """每个 prepared stage crash 后只按 frozen attempt schedule 恢复下一阶段。

    :param tmp_path: pytest 临时目录。
    :param crash_attempt_number: provider result 前 crash 的 global attempt。
    :param expected_resume_stage: fresh scheduler 应执行的下一 stage；预算耗尽为
        ``None``。
    :returns: ``None``。
    :raises AssertionError: operation、attempt、digest 或 stage 映射漂移时抛出。
    """

    blocker = _CrashAtPreparedAttemptCompactor(crash_attempt_number)
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_previous_compacted_event(
            store.transaction_runner,
            session_id=session_id,
            run_id=f"run-crash-previous-{crash_attempt_number}",
            event_id=f"event-crash-previous-{crash_attempt_number}",
        )
        for ordinal in (1, 2, 3):
            _append_user_input(
                store.transaction_runner,
                session_id=session_id,
                run_id=f"run-crash-delta-{crash_attempt_number}-{ordinal}",
                event_id=f"event-crash-delta-{crash_attempt_number}-{ordinal}",
                display_text=(f"crash resume material {crash_attempt_number}-{ordinal}"),
            )
        seeded = _seed_accepted_run(
            store,
            run_id=f"run-proactive-crash-{crash_attempt_number}",
            display_text=_soft_threshold_prompt(),
            session_id=session_id,
        )
        policy = _soft_compact_policy(
            max_compaction_attempts_per_operation=5,
            context_window_size=2000,
            soft_threshold_tokens=50,
            hard_threshold_tokens=1000,
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=policy,
            context_compactor=blocker,
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_fallback_cap_memory_policy(),
        )
        promotion = asyncio.create_task(scheduler.run_queue_promotion(seeded.session_id))
        try:
            await asyncio.wait_for(blocker.provider_entered.wait(), timeout=2.0)
            with pytest.raises(_SimulatedProactiveCrash):
                await promotion
        finally:
            await scheduler.close()

        incomplete = _read_proactive_projection(
            store.transaction_runner,
            session_id=seeded.session_id,
            run_id=seeded.run_id,
        )
        prepared_attempts = tuple(range(1, crash_attempt_number + 1))
        assert incomplete.state.phase is ProactiveCompactionPhase.INCOMPLETE
        assert incomplete.state.prepared_attempt_numbers == prepared_attempts
        assert incomplete.state.rejected_attempt_numbers == ()
        assert incomplete.state.next_attempt_number == crash_attempt_number + 1
        assert incomplete.state.max_attempt_number == 5
        assert incomplete.state.prepared_request_digests == tuple(
            (attempt_number, request.digest())
            for attempt_number, request in enumerate(
                blocker.prepared_requests,
                start=1,
            )
        )
        operation_id = incomplete.state.operation_id

        resumed_compactor = _PreparedManifestProactiveCompactor()
        resumed_scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=policy,
            context_compactor=resumed_compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_fallback_cap_memory_policy(),
            host_handle_id=f"host-test-crash-resumed-{crash_attempt_number}",
        )
        try:
            await resumed_scheduler.run_queue_promotion(seeded.session_id)
        finally:
            await resumed_scheduler.close()

        completed = _read_proactive_projection(
            store.transaction_runner,
            session_id=seeded.session_id,
            run_id=seeded.run_id,
        )
        assert completed.state.operation_id == operation_id
        assert _event_types_for_run(store.transaction_runner, seeded.run_id).count(CONTEXT_COMPACTION_REQUESTED) == 1
        if expected_resume_stage is None:
            assert resumed_compactor.calls == 0
            assert resumed_compactor.prepared_requests == []
            assert completed.state.phase is ProactiveCompactionPhase.FAILED
            assert completed.state.prepared_attempt_numbers == prepared_attempts
            failed = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_FAILED,
            )
            assert _event_payload(failed)["attempt_count"] == 5
            return

        assert resumed_compactor.calls == 1
        assert len(resumed_compactor.prepared_requests) == 1
        resumed_request = resumed_compactor.prepared_requests[0]
        _assert_resumed_proactive_request_stage(
            expected_resume_stage,
            root_request=blocker.prepared_requests[0],
            resumed_request=resumed_request,
        )
        assert completed.state.phase is ProactiveCompactionPhase.COMPACTED
        assert completed.state.prepared_attempt_numbers == (
            *prepared_attempts,
            crash_attempt_number + 1,
        )
        compacted = _latest_event_for_run(
            store.transaction_runner,
            seeded.run_id,
            CONTEXT_COMPACTED,
        )
        assert _event_payload(compacted)["accepted_attempt_number"] == (crash_attempt_number + 1)


@pytest.mark.asyncio
async def test_orphan_compactor_manifest_without_request_is_invalid(
    tmp_path: Path,
) -> None:
    """已提交 manifest 失去 request owner 后必须投影为无安全 id 的 INVALID。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: orphan manifest 被投影为 ABSENT 或获得 operation id 时抛出。
    """

    blocker = _CrashAtPreparedAttemptCompactor(1)
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run_with_compactable_history(
            store,
            run_id="run-orphan-proactive-manifest",
            display_text=_soft_threshold_prompt(),
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(
                max_compaction_attempts_per_operation=2,
            ),
            context_compactor=blocker,
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        promotion = asyncio.create_task(scheduler.run_queue_promotion(seeded.session_id))
        try:
            await asyncio.wait_for(blocker.provider_entered.wait(), timeout=2.0)
            with pytest.raises(_SimulatedProactiveCrash):
                await promotion
        finally:
            await scheduler.close()

        _delete_compaction_requested_events(
            store.transaction_runner,
            run_id=seeded.run_id,
        )
        projection = _read_proactive_projection(
            store.transaction_runner,
            session_id=seeded.session_id,
            run_id=seeded.run_id,
        )

        assert projection.state.phase is ProactiveCompactionPhase.INVALID
        assert projection.state.operation_id is None
        assert projection.state.invalid_reason == "HostDurableError"
        assert projection.decision is (ProactiveCompactionDecision.FAIL_EXISTING_OPERATION)


def _assert_resumed_proactive_request_stage(
    stage: ProactiveCompactionAttemptStage,
    *,
    root_request: CompactionRequest,
    resumed_request: CompactionRequest,
) -> None:
    """断言 crash resume request 使用目标 stage 的 material contract。

    :param stage: production typed schedule 给出的下一 stage。
    :param root_request: 同 operation 首次 immutable root request。
    :param resumed_request: fresh scheduler 实际准备的 request。
    :returns: ``None``。
    :raises AssertionError: request 未体现目标 stage 的降级语义时抛出。
    """

    if stage is ProactiveCompactionAttemptStage.ROOT_REPAIR:
        assert resumed_request == root_request
        return
    assert len(resumed_request.segment_selection.selected_block_ids) < len(
        root_request.segment_selection.selected_block_ids
    )
    if stage is ProactiveCompactionAttemptStage.TIER_1_FALLBACK_CAPS:
        assert resumed_request.material_pack.previous_compacted_view == (
            root_request.material_pack.previous_compacted_view
        )
        return
    if stage is ProactiveCompactionAttemptStage.TIER_2_SECTION_DEGRADE:
        assert (
            0
            < len(resumed_request.material_pack.previous_compacted_view)
            < len(root_request.material_pack.previous_compacted_view)
        )
        assert resumed_request.material_pack.previous_compacted_readable_view != (
            root_request.material_pack.previous_compacted_readable_view
        )
        return
    if stage is ProactiveCompactionAttemptStage.TIER_3_DELTA_ONLY:
        assert resumed_request.material_pack.previous_compacted_view == ()
        assert resumed_request.material_pack.previous_compacted_readable_view is None
        return
    raise AssertionError(f"unexpected proactive resume stage: {stage.value}")


@pytest.mark.parametrize(
    "mismatch_kind",
    ("attempt_number", "manifest_ref", "manifest_digest"),
)
@pytest.mark.asyncio
async def test_proactive_projection_rejects_compacted_manifest_mismatch(
    tmp_path: Path,
    mismatch_kind: str,
) -> None:
    """accepted terminal 必须精确反向关联同 attempt proposal manifest。

    :param tmp_path: pytest 临时目录。
    :param mismatch_kind: 注入 attempt、manifest ref 或 digest 错配。
    :returns: ``None``。
    :raises AssertionError: durable terminal mismatch 未投影为 INVALID 时抛出。
    """

    compactor = _PreparedManifestProactiveCompactor()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run_with_compactable_history(
            store,
            run_id=f"run-terminal-manifest-{mismatch_kind}",
            display_text=_soft_threshold_prompt(),
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(
                max_compaction_attempts_per_operation=1,
            ),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)
        finally:
            await scheduler.close()

        valid = _read_proactive_projection(
            store.transaction_runner,
            session_id=seeded.session_id,
            run_id=seeded.run_id,
        )
        assert valid.state.phase is ProactiveCompactionPhase.COMPACTED
        compacted = _latest_event_for_run(
            store.transaction_runner,
            seeded.run_id,
            CONTEXT_COMPACTED,
        )
        corrupted_payload = dict(_event_payload(compacted))
        if mismatch_kind == "attempt_number":
            corrupted_payload["accepted_attempt_number"] = 2
        elif mismatch_kind == "manifest_ref":
            corrupted_payload["accepted_proposal_manifest_ref"] = "runner-call-manifest:wrong-attempt"
        else:
            assert mismatch_kind == "manifest_digest"
            assert corrupted_payload["accepted_proposal_manifest_digest"] != (_CALL_CONTEXT_DIGEST)
            corrupted_payload["accepted_proposal_manifest_digest"] = _CALL_CONTEXT_DIGEST
        _overwrite_event_payload(
            store.transaction_runner,
            event_id=compacted.event_id,
            payload=corrupted_payload,
        )

        invalid = _read_proactive_projection(
            store.transaction_runner,
            session_id=seeded.session_id,
            run_id=seeded.run_id,
        )

        assert invalid.state.phase is ProactiveCompactionPhase.INVALID
        assert invalid.state.operation_id == valid.state.operation_id
        assert invalid.state.compacted_event_sequence == compacted.event_sequence
        assert invalid.decision is (ProactiveCompactionDecision.FAIL_EXISTING_OPERATION)


@pytest.mark.asyncio
async def test_proactive_projection_rejects_already_rejected_accepted_attempt(
    tmp_path: Path,
) -> None:
    """同一 attempt 不能先 rejected 又被 terminal 标为 accepted。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: mutually exclusive outcome 被错误归并时抛出。
    """

    compactor = _QualityRejectOnceCompactor()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run_with_compactable_history(
            store,
            run_id="run-rejected-then-accepted-corrupt",
            display_text=_soft_threshold_prompt(),
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(
                max_compaction_attempts_per_operation=2,
            ),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)
        finally:
            await scheduler.close()

        rejected = _latest_event_for_run(
            store.transaction_runner,
            seeded.run_id,
            CONTEXT_COMPACTION_ATTEMPT_REJECTED,
        )
        rejected_payload = _event_payload(rejected)
        compacted = _latest_event_for_run(
            store.transaction_runner,
            seeded.run_id,
            CONTEXT_COMPACTED,
        )
        corrupted_payload = dict(_event_payload(compacted))
        corrupted_payload["accepted_attempt_number"] = 1
        corrupted_payload["accepted_proposal_manifest_ref"] = rejected_payload["proposal_manifest_ref"]
        corrupted_payload["accepted_proposal_manifest_digest"] = rejected_payload["proposal_manifest_digest"]
        _overwrite_event_payload(
            store.transaction_runner,
            event_id=compacted.event_id,
            payload=corrupted_payload,
        )

        invalid = _read_proactive_projection(
            store.transaction_runner,
            session_id=seeded.session_id,
            run_id=seeded.run_id,
        )

        assert invalid.state.phase is ProactiveCompactionPhase.INVALID
        assert invalid.state.compacted_event_sequence == compacted.event_sequence


@pytest.mark.asyncio
async def test_proactive_projection_rejects_operation_row_after_terminal(
    tmp_path: Path,
) -> None:
    """proactive terminal 后追加同 operation rejection 必须 fail closed。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: terminal 后 operation row 被错误接受时抛出。
    """

    compactor = _PreparedManifestProactiveCompactor()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run_with_compactable_history(
            store,
            run_id="run-row-after-proactive-terminal",
            display_text=_soft_threshold_prompt(),
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(
                max_compaction_attempts_per_operation=2,
            ),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)
        finally:
            await scheduler.close()
        valid = _read_proactive_projection(
            store.transaction_runner,
            session_id=seeded.session_id,
            run_id=seeded.run_id,
        )
        operation_id = valid.state.operation_id
        assert operation_id is not None
        _append_proactive_rejection_after_terminal(
            store.transaction_runner,
            seeded=seeded,
            operation_id=operation_id,
        )

        invalid = _read_proactive_projection(
            store.transaction_runner,
            session_id=seeded.session_id,
            run_id=seeded.run_id,
        )

        assert invalid.state.phase is ProactiveCompactionPhase.INVALID
        assert invalid.state.operation_id == operation_id


@pytest.mark.asyncio
async def test_proactive_projection_requires_exact_failed_attempt_count(
    tmp_path: Path,
) -> None:
    """FAILED terminal count 必须等于 prepared/rejected attempt 并集。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 合法 count 或 corruption projection 漂移时抛出。
    """

    compactor = _RaisingCompactor()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run_with_compactable_history(
            store,
            run_id="run-failed-attempt-count",
            display_text=_soft_threshold_prompt(),
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(
                max_compaction_attempts_per_operation=2,
            ),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)
        finally:
            await scheduler.close()

        valid = _read_proactive_projection(
            store.transaction_runner,
            session_id=seeded.session_id,
            run_id=seeded.run_id,
        )
        assert valid.state.phase is ProactiveCompactionPhase.FAILED
        assert valid.state.prepared_attempt_numbers == (1, 2)
        assert valid.state.rejected_attempt_numbers == (1, 2)
        failed = _latest_event_for_run(
            store.transaction_runner,
            seeded.run_id,
            CONTEXT_COMPACTION_FAILED,
        )
        corrupted_payload = dict(_event_payload(failed))
        assert corrupted_payload["attempt_count"] == 2
        corrupted_payload["attempt_count"] = 1
        _overwrite_event_payload(
            store.transaction_runner,
            event_id=failed.event_id,
            payload=corrupted_payload,
        )

        invalid = _read_proactive_projection(
            store.transaction_runner,
            session_id=seeded.session_id,
            run_id=seeded.run_id,
        )

        assert invalid.state.phase is ProactiveCompactionPhase.INVALID
        assert invalid.state.failed_event_sequence == failed.event_sequence


@pytest.mark.asyncio
async def test_proactive_exhausted_manifest_fails_same_operation_without_provider(
    tmp_path: Path,
) -> None:
    """唯一预算已被 manifest 占用时，同 operation 失败且不再调用 provider。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: exhaustion、新 request 或 provider 次数漂移时抛出。
    """

    blocker = _BlockingAfterManifestCompactor()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run_with_compactable_history(
            store,
            run_id="run-proactive-manifest-exhausted",
            display_text=_soft_threshold_prompt(),
        )
        policy = _soft_compact_policy(
            max_compaction_attempts_per_operation=1,
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=policy,
            context_compactor=blocker,
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        promotion = asyncio.create_task(scheduler.run_queue_promotion(seeded.session_id))
        try:
            await asyncio.wait_for(blocker.provider_entered.wait(), timeout=2.0)
            promotion.cancel()
            with pytest.raises(asyncio.CancelledError):
                await promotion
        finally:
            await scheduler.close()

        exhausted = _read_proactive_projection(
            store.transaction_runner,
            session_id=seeded.session_id,
            run_id=seeded.run_id,
        )
        assert exhausted.state.operation_id is not None
        assert exhausted.state.prepared_attempt_numbers == (1,)
        assert exhausted.state.next_attempt_number == 2
        assert exhausted.decision is (ProactiveCompactionDecision.FAIL_EXISTING_OPERATION)
        operation_id = exhausted.state.operation_id

        forbidden_provider = _PreparedManifestProactiveCompactor()
        resumed_scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=policy,
            context_compactor=forbidden_provider,
            compact_artifact_root=tmp_path / "compact-artifacts",
            host_handle_id="host-test-exhausted-resumed",
        )
        try:
            await resumed_scheduler.run_queue_promotion(seeded.session_id)
        finally:
            await resumed_scheduler.close()

        assert forbidden_provider.calls == 0
        assert forbidden_provider.prepared_requests == []
        assert _event_types_for_run(store.transaction_runner, seeded.run_id).count(CONTEXT_COMPACTION_REQUESTED) == 1
        failed = _latest_event_for_run(
            store.transaction_runner,
            seeded.run_id,
            CONTEXT_COMPACTION_FAILED,
        )
        failed_payload = _event_payload(failed)
        assert failed_payload["operation_id"] == operation_id
        assert failed_payload["attempt_count"] == 1
        assert failed_payload["retry_repair_budget_exhausted"] is True


@pytest.mark.asyncio
async def test_proactive_default_budget_executes_root_repair_and_three_tiers(
    tmp_path: Path,
) -> None:
    """默认 budget=5 依次执行 root repair 与三种真实降级 material/renderer。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: attempt、request material 或 rendered input 漂移时抛出。
    """

    compactor = _RecoveryScenarioCompactor(accept_call=5)
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_previous_compacted_event(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-default-schedule-previous",
            event_id="event-default-schedule-previous-compact",
        )
        for ordinal in (1, 2, 3):
            _append_user_input(
                store.transaction_runner,
                session_id=session_id,
                run_id=f"run-default-schedule-delta-{ordinal}",
                event_id=f"event-default-schedule-delta-{ordinal}",
                display_text=f"default schedule delta material {ordinal}",
            )
        seeded = _seed_accepted_run(
            store,
            run_id="run-default-proactive-schedule",
            display_text=_soft_threshold_prompt(),
            session_id=session_id,
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(
                max_compaction_attempts_per_operation=5,
                context_window_size=2000,
                soft_threshold_tokens=50,
                hard_threshold_tokens=1000,
            ),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_fallback_cap_memory_policy(),
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)

            assert compactor.calls == 5
            assert (
                len(
                    _events_for_run_by_type(
                        store.transaction_runner,
                        seeded.run_id,
                        CONTEXT_COMPACTED,
                    )
                )
                == 1
            )
            assert (
                _events_for_run_by_type(
                    store.transaction_runner,
                    seeded.run_id,
                    CONTEXT_COMPACTION_FAILED,
                )
                == ()
            )
            assert (
                len(
                    _events_for_run_by_type(
                        store.transaction_runner,
                        seeded.run_id,
                        CONTEXT_COMPACTION_ATTEMPT_REJECTED,
                    )
                )
                == 4
            )
            compacted_payload = _event_payload(
                _latest_event_for_run(
                    store.transaction_runner,
                    seeded.run_id,
                    CONTEXT_COMPACTED,
                )
            )
            assert compacted_payload["accepted_attempt_number"] == 5
            assert len(compactor.prepared_requests) == 5
            assert len(compactor.prepared_inputs) == 5

            root, root_repair, tier_1, tier_2, tier_3 = compactor.prepared_requests
            assert root_repair == root
            assert tier_1.material_pack.previous_compacted_view == (root.material_pack.previous_compacted_view)
            assert len(tier_1.segment_selection.selected_block_ids) < len(root.segment_selection.selected_block_ids)
            assert tier_2.segment_selection == tier_1.segment_selection
            assert (
                0 < len(tier_2.material_pack.previous_compacted_view) < len(root.material_pack.previous_compacted_view)
            )
            assert tier_2.material_pack.previous_compacted_readable_view != (
                root.material_pack.previous_compacted_readable_view
            )
            assert tier_3.segment_selection == tier_1.segment_selection
            assert tier_3.material_pack.previous_compacted_view == ()
            assert tier_3.material_pack.previous_compacted_readable_view is None
            assert len({request.digest() for request in (root, tier_1, tier_2, tier_3)}) == 4

            root_input, root_repair_input, tier_1_input, tier_2_input, tier_3_input = (
                prepared.compact_input for prepared in compactor.prepared_inputs
            )
            assert root_repair_input == root_input
            assert len(tier_1_input.source_boundary) < len(root_input.source_boundary)
            assert tier_2_input.source_boundary not in (
                root_input.source_boundary,
                tier_1_input.source_boundary,
            )
            assert all(not entry.source_kind.value.startswith("previous_") for entry in tier_3_input.source_boundary)
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_proactive_compaction_recovery_stale_before_tier_attempt_discards(
    tmp_path: Path,
) -> None:
    """normal 失败后 state 已 stale 时不进入 recovery compact commit。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        compactor = _RecoveryScenarioCompactor(
            accept_call=2,
            transaction_runner=store.transaction_runner,
            stale_after_call=1,
        )
        seeded = _seed_accepted_run_with_compactable_history(
            store,
            run_id="run-recovery-stale-before",
            display_text=_soft_threshold_prompt(),
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(
                max_compaction_attempts_per_operation=4,
                context_window_size=2000,
                soft_threshold_tokens=50,
                hard_threshold_tokens=1000,
            ),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)

            assert compactor.calls == 1
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 0
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTION_FAILED) == 1
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_proactive_compaction_recovery_stale_during_tier_proposal_discards(
    tmp_path: Path,
) -> None:
    """tier proposal 执行期间 state stale 时不写 CONTEXT_COMPACTED。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        compactor = _RecoveryScenarioCompactor(
            accept_call=2,
            transaction_runner=store.transaction_runner,
            stale_after_call=2,
        )
        seeded = _seed_accepted_run_with_compactable_history(
            store,
            run_id="run-recovery-stale-after",
            display_text=_soft_threshold_prompt(),
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(
                max_compaction_attempts_per_operation=4,
                context_window_size=2000,
                soft_threshold_tokens=50,
                hard_threshold_tokens=1000,
            ),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)

            assert compactor.calls == 2
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 0
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTION_FAILED) == 1
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_proactive_compaction_recovery_all_tiers_fail_uses_dispatch_fallback(
    tmp_path: Path,
) -> None:
    """normal 与 tier 1-3 全失败后只写一次 failed 并进入 tier 4 dispatch。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: invalid attempts、formal traces 或 fallback 不闭合时抛出。
    """

    factory = _FakeWorkerFactory()
    compactor = _AlwaysQualityRejectingCompactor()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_previous_compacted_event(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-all-fail-previous",
            event_id="event-all-fail-previous-compact",
        )
        seeded = _seed_accepted_run(
            store,
            run_id="run-recovery-all-fail",
            display_text=_soft_threshold_prompt(),
            session_id=session_id,
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            context_budget_policy=_soft_compact_policy(
                max_compaction_attempts_per_operation=4,
                context_window_size=2000,
                soft_threshold_tokens=50,
                hard_threshold_tokens=1000,
            ),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)
            await _wait_for_event_count(
                store.transaction_runner,
                "ATTEMPT_RUNNING",
                expected_count=1,
            )

            assert compactor.calls == 4
            root, root_repair, tier_1, tier_2 = compactor.prepared_requests
            assert root_repair == root
            assert compactor.prepared_inputs[0].repair_feedback is None
            root_feedback = compactor.prepared_inputs[1].repair_feedback
            assert root_feedback is not None
            assert root_feedback.request_digest == root.digest()
            assert root_feedback.source_boundary_digest == root.source_boundary_digest()
            assert compactor.prepared_inputs[2].repair_feedback is None
            assert compactor.prepared_inputs[3].repair_feedback is None
            assert tier_1.digest() != root.digest()
            assert tier_2.source_boundary_digest() != tier_1.source_boundary_digest()
            assert (
                len(
                    _events_for_run_by_type(
                        store.transaction_runner,
                        seeded.run_id,
                        CONTEXT_COMPACTED,
                    )
                )
                == 0
            )
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTION_FAILED) == 1
            rejected_events = _events_for_run_by_type(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_ATTEMPT_REJECTED,
            )
            assert len(rejected_events) == 4
            rejected_payloads = tuple(_event_payload(row) for row in rejected_events)
            assert tuple(payload["attempt_number"] for payload in rejected_payloads) == (
                1,
                2,
                3,
                4,
            )
            assert all(payload["failure_category"] == "quality_check_rejected" for payload in rejected_payloads)
            for payload in rejected_payloads:
                _assert_rejected_payload_has_proposal_manifest(payload)
            failed_payload = _event_payload(
                _latest_event_for_run(
                    store.transaction_runner,
                    seeded.run_id,
                    CONTEXT_COMPACTION_FAILED,
                )
            )
            assert failed_payload["attempt_count"] == len(rejected_events)
            assert failed_payload["retry_repair_budget_exhausted"] is True
            assert len(factory.accepted_requests) == 1
            _resolve_and_assert_compactor_calls(
                store.transaction_runner,
                tmp_path=tmp_path,
                run_id=seeded.run_id,
                prepared_inputs=tuple(compactor.prepared_inputs),
                attempt_payloads=rejected_payloads,
                accepted_attempt_number=None,
            )
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_defensive_feedback_mismatch_stops_schedule_with_single_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """绕过 dispatcher 清理时 operation 拒绝跨 tier feedback 且只收口一次。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: 仅用于让 mismatch feedback 到达 operation 的测试 seam。
    :returns: ``None``。
    """

    monkeypatch.setattr(
        "dayu.host.dispatch._repair_feedback_for_request",
        _retain_feedback_without_binding_for_defensive_test,
    )
    factory = _FakeWorkerFactory()
    compactor = _AlwaysQualityRejectingCompactor()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_previous_compacted_event(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-defensive-feedback-previous",
            event_id="event-defensive-feedback-previous-compact",
        )
        seeded = _seed_accepted_run(
            store,
            run_id="run-defensive-feedback-mismatch",
            display_text=_soft_threshold_prompt(),
            session_id=session_id,
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            context_budget_policy=_soft_compact_policy(
                max_compaction_attempts_per_operation=3,
                context_window_size=2000,
                soft_threshold_tokens=50,
                hard_threshold_tokens=1000,
            ),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)
            await _wait_for_event_count(
                store.transaction_runner,
                "ATTEMPT_RUNNING",
                expected_count=1,
            )

            assert compactor.calls == 2
            assert len(compactor.prepared_inputs) == 2
            assert (
                _events_for_run_by_type(
                    store.transaction_runner,
                    seeded.run_id,
                    CONTEXT_COMPACTED,
                )
                == ()
            )
            assert (
                len(
                    _events_for_run_by_type(
                        store.transaction_runner,
                        seeded.run_id,
                        CONTEXT_COMPACTION_FAILED,
                    )
                )
                == 1
            )
            rejected_events = _events_for_run_by_type(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_ATTEMPT_REJECTED,
            )
            assert len(rejected_events) == 3
            assert _event_payload(rejected_events[-1])["failure_category"] == ("proposal_failed")
            assert len(factory.accepted_requests) == 1
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_compaction_repair_attempt_rejection_is_recorded_in_eventlog(
    tmp_path: Path,
) -> None:
    """semantic proposal failure 写 rejected facts 后通过 fallback dispatch。"""

    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run_with_compactable_history(
            store,
            run_id="run-proactive-attempt-rejected",
            display_text=_soft_threshold_prompt(),
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            context_budget_policy=_soft_compact_policy(
                max_compaction_attempts_per_operation=2,
            ),
            context_compactor=_RaisingCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)
            await _wait_for_event_count(
                store.transaction_runner,
                "ATTEMPT_RUNNING",
                expected_count=1,
            )

            assert (
                _event_count(
                    store.transaction_runner,
                    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
                )
                == 2
            )
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTION_FAILED) == 1
            requested = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_REQUESTED,
            )
            rejected = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_ATTEMPT_REJECTED,
            )
            rejected_rows = _events_for_run_by_type(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_ATTEMPT_REJECTED,
            )
            failed = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_FAILED,
            )
            assert _event_payload(rejected)["operation_id"] == requested.event_id
            assert len(rejected_rows) == 2
            assert tuple(_event_payload(rejected_row)["attempt_number"] for rejected_row in rejected_rows) == (
                1,
                2,
            )
            for rejected_row in rejected_rows:
                _assert_rejected_payload_has_proposal_manifest(_event_payload(rejected_row))
            payload = _event_payload(failed)
            assert payload["operation_id"] == requested.event_id
            assert payload["attempt_count"] == 2
            assert payload["retry_repair_budget_exhausted"] is True
            assert payload["fallback_action"] == "dispatch"
            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 1
            assert len(factory.accepted_requests) == 1
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_pre_start_governance_compact_failure_is_attempt_free(
    tmp_path: Path,
) -> None:
    """proactive compact 缺 compactor 后 fallback 预算通过会创建 Attempt。"""

    factory = _FakeWorkerFactory(accepted_handle=_CloseCountingHandle())
    compact_artifact_root = tmp_path / "compact-artifacts"
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-compact-failure-old",
            event_id="event-input-run-compact-failure-old",
            display_text="older fallback floor material that must render",
            client_request_id="client-run-compact-failure-old",
            idempotency_key="idem-run-compact-failure-old",
        )
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-compact-failure-recent",
            event_id="event-input-run-compact-failure-recent",
            display_text="recent protected fallback floor material",
            client_request_id="client-run-compact-failure-recent",
            idempotency_key="idem-run-compact-failure-recent",
        )
        seeded = _seed_accepted_run(
            store,
            run_id="run-compact-failure",
            display_text=_soft_threshold_prompt(),
            session_id=session_id,
        )
        memory_policy = replace(
            _fallback_cap_memory_policy(),
            selected_recent_window_turn_floor=1,
            fallback_selected_recent_window_item_cap=2,
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            context_budget_policy=_soft_compact_policy(
                context_window_size=200,
                soft_threshold_tokens=70,
                hard_threshold_tokens=200,
            ),
            memory_projection_policy=memory_policy,
            compact_artifact_root=compact_artifact_root,
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)
            await _wait_for_event_count(
                store.transaction_runner,
                "ATTEMPT_RUNNING",
                expected_count=1,
            )

            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 1
            assert _run_status(store.transaction_runner, seeded.run_id) is (RunStatus.RUNNING)
            event_types = _event_types_for_run(store.transaction_runner, seeded.run_id)
            assert event_types.index(CONTEXT_COMPACTION_FAILED) < event_types.index("RUN_STARTED")
            assert event_types.index("RUN_STARTED") < event_types.index("ATTEMPT_STARTED")
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 0
            assert len(factory.accepted_requests) == 1
            requested = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_REQUESTED,
            )
            failed = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_FAILED,
            )
            payload = _event_payload(failed)
            assert payload["operation_id"] == requested.event_id
            assert payload["fallback_action"] == "dispatch"
            assert isinstance(payload["fallback_input_window"], Mapping)
            assert payload["fallback_input_window"]["current_input_ref"] == (f"event-input-{seeded.run_id}")
            assert payload["fallback_input_window"]["selected_block_ids"] == [
                "eventlog:user:event-input-run-compact-failure-recent",
                f"current:event-input-{seeded.run_id}",
            ]
            assert "eventlog:user:event-input-run-compact-failure-old" in (
                _required_json_text_tuple(payload["fallback_input_window"]["dropped_block_ids"])
            )
            assert isinstance(payload["fallback_budget_result"], Mapping)
            assert payload["fallback_budget_result"]["status"] == "within_hard_budget"
            assert _compact_artifact_files(compact_artifact_root) == ()
            rendered = "\n".join(
                content
                for content in (_message_text(message) for message in factory.accepted_requests[0].messages)
                if content is not None
            )
            assert "recent protected fallback floor material" in rendered
            assert "older fallback floor material that must render" not in rendered
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_pre_start_governance_fallback_budget_fail_closes_run(
    tmp_path: Path,
) -> None:
    """hard-threshold precondition 不进入 fallback 且不创建 Attempt。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id="run-fallback-over-budget",
            display_text=_hard_threshold_prompt(),
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(
                context_window_size=200,
                soft_threshold_tokens=70,
                hard_threshold_tokens=120,
            ),
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)

            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 0
            assert _run_status(store.transaction_runner, seeded.run_id) == RunStatus.FAILED
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 0
            failed = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_FAILED,
            )
            payload = _event_payload(failed)
            assert payload["failure_reason"] == "hard_threshold_before_dispatch"
            assert_failed_payload_no_fallback(
                payload,
                expected_operation_id=None,
                expected_attempt_count=0,
                expected_retry_repair_budget_exhausted=False,
            )
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_pre_start_governance_material_source_failure_fails_closed(
    tmp_path: Path,
) -> None:
    """required memory catch-up 失败时零 start、零 fallback。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_corrupted_tool_result_material(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-material-source-corrupted-tool",
            event_id="event-material-source-corrupted-tool",
        )
        seeded = _seed_accepted_run(
            store,
            run_id="run-material-source-failure",
            display_text=_soft_threshold_prompt(),
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        )
        try:
            with pytest.raises(
                HostDurableError,
                match="candidate memory projection did not reach required cursor",
            ):
                await scheduler.run_queue_promotion(seeded.session_id)

            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 0
            assert _run_status(store.transaction_runner, seeded.run_id) == RunStatus.ACCEPTED
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTION_REQUESTED) == 0
            assert (
                _event_count(
                    store.transaction_runner,
                    CONTEXT_COMPACTION_FAILED,
                )
                == 0
            )
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_pre_start_governance_invalid_incomplete_snapshot_fails_same_operation(
    tmp_path: Path,
) -> None:
    """既有 incomplete request 的冻结 snapshot 不匹配时按原 operation 收口。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id="run-compact-limit",
            display_text=_soft_threshold_prompt(),
        )
        _append_proactive_compaction_requested(
            store.transaction_runner,
            seeded=seeded,
            event_id="event-existing-proactive-request",
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)

            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 1
            assert _run_status(store.transaction_runner, seeded.run_id) == (RunStatus.RUNNING)
            assert (
                _event_types_for_run(store.transaction_runner, seeded.run_id).count(CONTEXT_COMPACTION_REQUESTED) == 1
            )
            failed = _read_event_by_type(store.transaction_runner, CONTEXT_COMPACTION_FAILED)
            payload = _event_payload(failed)
            assert payload["failure_reason"] == ("proactive_operation_invalid_or_exhausted")
            assert payload["operation_id"] == "event-existing-proactive-request"
            assert payload["attempt_count"] == 0
            assert payload["retry_repair_budget_exhausted"] is True
            assert payload["fallback_action"] == "dispatch"
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_pre_start_governance_without_safe_operation_id_fails_run(
    tmp_path: Path,
) -> None:
    """损坏 request 无安全 proactive id 时只用 governance failure 收口 Run。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: dispatcher 追加 request/compaction terminal、调用
        provider 或创建 Attempt 时抛出。
    """

    compactor = _PreparedManifestProactiveCompactor()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id="run-corrupted-compact-count",
            display_text=_soft_threshold_prompt(),
        )
        _append_corrupted_compaction_requested(
            store.transaction_runner,
            seeded=seeded,
            event_id="event-corrupted-proactive-request",
        )
        event_types_before = _event_types_for_run(
            store.transaction_runner,
            seeded.run_id,
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)

            event_types_after = _event_types_for_run(
                store.transaction_runner,
                seeded.run_id,
            )
            assert (
                _attempt_count_for_run(
                    store.transaction_runner,
                    seeded.run_id,
                )
                == 0
            )
            assert (
                _run_status(
                    store.transaction_runner,
                    seeded.run_id,
                )
                is RunStatus.FAILED
            )
            assert compactor.calls == 0
            assert compactor.prepared_requests == []
            for event_type in (
                CONTEXT_COMPACTION_REQUESTED,
                CONTEXT_COMPACTION_FAILED,
                CONTEXT_COMPACTED,
            ):
                assert event_types_after.count(event_type) == (event_types_before.count(event_type))
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_multi_turn_proactive_compact_feeds_subsequent_run_input(
    tmp_path: Path,
) -> None:
    """多轮 Run 经 proactive compact 后写入 accepted closeout。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: accepted compactor trace 或 subsequent input 不可重构时抛出。
    """

    factory = _FinalAnswerWorkerFactory()
    compactor = _PreparedManifestProactiveCompactor()
    with open_host_durable_store(_options(tmp_path)) as store:
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            context_budget_policy=_soft_compact_policy(
                # 同源 material view 估算包含 previous view、delta 与 current input；
                # 这里需超过 soft threshold 且低于 hard threshold，目标仍是 proactive lifecycle。
                context_window_size=320,
                soft_threshold_tokens=60,
                hard_threshold_tokens=260,
            ),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_floor_one_memory_policy(),
        )
        try:
            first = await _dispatch_accepted_final_run(
                scheduler=scheduler,
                store=store,
                factory=factory,
                run_id="run-multi-turn-1",
                display_text="first raw turn for memory",
                expected_request_count=1,
            )
            assert first.session_id != ""

            await _dispatch_accepted_final_run(
                scheduler=scheduler,
                store=store,
                factory=factory,
                run_id="run-multi-turn-2",
                display_text="follow-up under budget",
                expected_request_count=2,
            )
            second_contents = tuple(_message_text(message) for message in factory.accepted_requests[1].messages)
            assert "first raw turn for memory" in second_contents
            assert second_contents[-1] == "follow-up under budget"

            compacted = _seed_accepted_run(
                store,
                run_id="run-multi-turn-3",
                display_text=_soft_threshold_prompt(),
            )
            await scheduler.run_queue_promotion(compacted.session_id)
            await _wait_for_event_count(
                store.transaction_runner,
                CONTEXT_COMPACTED,
                expected_count=1,
            )
            event_types = _event_types_for_run(store.transaction_runner, compacted.run_id)
            compacted_payload = _event_payload(
                _latest_event_for_run(
                    store.transaction_runner,
                    compacted.run_id,
                    CONTEXT_COMPACTED,
                )
            )
            _resolve_and_assert_compactor_calls(
                store.transaction_runner,
                tmp_path=tmp_path,
                run_id=compacted.run_id,
                prepared_inputs=tuple(compactor.prepared_inputs),
                attempt_payloads=(compacted_payload,),
                accepted_attempt_number=1,
            )
            runner_call_page = store.transaction_runner.run_read(
                lambda transaction: read_runner_call_reconstruction_signals_by_run(
                    transaction,
                    compacted.run_id,
                    after_event_sequence=0,
                    limit=100,
                )
            )
            ordinary_signals = tuple(
                signal for signal in runner_call_page.signals if signal.runner_call_kind != _COMPACTOR_RUNNER_CALL_KIND
            )
            assert len(ordinary_signals) == 1
            ordinary_call = store.transaction_runner.run_read(
                lambda transaction: resolve_runner_call_projection_from_signal(
                    transaction,
                    ordinary_signals[0],
                )
            )

            assert event_types.index(CONTEXT_COMPACTION_REQUESTED) < (event_types.index(CONTEXT_COMPACTED))
            assert event_types.index(CONTEXT_COMPACTED) < event_types.index("RUN_STARTED")
            sizing_snapshot = _required_json_mapping(ordinary_call.manifest.payload["sizing_snapshot"])
            assert sizing_snapshot["sizing_stage"] == ContextSizingStage.POST_COMPACT.value
            assert compacted_payload["operation_id"] != ""
            assert compacted_payload["accepted_attempt_number"] == 1
            assert compacted_payload["compact_artifact_ref"] != ""
            assert compacted_payload["accepted_candidate_digest"] != ""
            _assert_accepted_payload_has_proposal_manifest(compacted_payload)
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_reactive_overflow_recovers_and_dispatches_new_attempt(
    tmp_path: Path,
) -> None:
    """worker reactive overflow 经 compact 后创建新 Attempt closeout。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-reactive-history",
            event_id="event-reactive-history",
            display_text="older compactable material",
            client_request_id="client-reactive-history",
            idempotency_key="idem-reactive-history",
        )
        seeded = _seed_current_run(store, session_id=session_id)
        factory = _ReactiveRecoveryWorkerFactory()
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            context_budget_policy=_soft_compact_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            assert (await scheduler.drain_once()).dispatched == 1
            await _wait_for_event_count(
                store.transaction_runner,
                CONTEXT_COMPACTED,
                expected_count=1,
            )

            assert len(factory.accepted_snapshots) >= 1
            assert factory.accepted_snapshots[0].attempt_id == seeded.attempt_id
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 1
            assert _event_count(store.transaction_runner, "RUN_RECOVERING") == 1
            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 2
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_reactive_compact_request_uses_latest_previous_view(
    tmp_path: Path,
) -> None:
    """reactive compact request 复用 latest accepted compact previous view。"""

    proactive_compactor = _MinimalSummaryCompactor()
    reactive_compactor = _RequestCapturingCompactor()
    with open_host_durable_store(_options(tmp_path)) as store:
        final_factory = _FinalAnswerWorkerFactory()
        session_id = _ensure_session_id(store.transaction_runner)
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-reactive-previous-old",
            event_id="event-reactive-previous-old-input",
            display_text="old",
            client_request_id="client-reactive-previous-old",
            idempotency_key="idem-reactive-previous-old",
        )
        proactive = _seed_accepted_run(
            store,
            run_id="run-reactive-previous-proactive",
            display_text=_soft_threshold_prompt(),
        )
        proactive_scheduler = await _open_scheduler(
            tmp_path,
            store,
            final_factory,
            context_budget_policy=_soft_compact_policy(),
            context_compactor=proactive_compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        try:
            await proactive_scheduler.run_queue_promotion(proactive.session_id)
            assert len(proactive_compactor.prepared_requests) == 1
            await _wait_for_final_request_count(final_factory, 1)
            await _wait_for_run_status(
                store.transaction_runner,
                proactive.run_id,
                expected_run=RunStatus.SUCCEEDED,
            )
        finally:
            await proactive_scheduler.close()

        reactive_seed = _seed_current_run(store, session_id=session_id)
        reactive_factory = _ReactiveRecoveryWorkerFactory()
        reactive_scheduler = await _open_scheduler(
            tmp_path,
            store,
            reactive_factory,
            host_instance_identity=HostInstanceIdentity(
                host_instance_id="host-reactive-previous",
                pid=2,
                process_start_token="process-reactive-previous",
                boot_id=None,
            ),
            context_budget_policy=_soft_compact_policy(),
            context_compactor=reactive_compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        try:
            reactive_scheduler.wake_dispatch(_pending_dispatch(reactive_seed))
            assert (await reactive_scheduler.drain_once()).dispatched == 1
            await _wait_for_compactor_request_count(reactive_compactor, 1)

            assert len(reactive_compactor.prepared_requests) == 1
            request = reactive_compactor.prepared_requests[0]
            assert request.trigger_source is ContextCompactionTriggerSource.REACTIVE
            assert request.material_pack.previous_compacted_view != ()
            assert request.material_pack.previous_compacted_view[0].text == "rolled"
        finally:
            await reactive_scheduler.close()


@pytest.mark.asyncio
async def test_reactive_root_compact_selection_passes_protected_recent_floor(
    tmp_path: Path,
) -> None:
    """reactive root compact selection 传入 selected recent floor。"""

    reactive_compactor = _RequestCapturingCompactor()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-reactive-floor-old",
            event_id="event-reactive-floor-old-input",
            display_text="older reactive compactable material",
            client_request_id="client-reactive-floor-old",
            idempotency_key="idem-reactive-floor-old",
        )
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-reactive-floor-recent",
            event_id="event-reactive-floor-recent-input",
            display_text="recent reactive protected material",
            client_request_id="client-reactive-floor-recent",
            idempotency_key="idem-reactive-floor-recent",
        )
        _append_run_success(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-reactive-floor-recent",
            event_id="event-reactive-floor-recent-success",
            final_answer="recent reactive protected final answer",
        )
        _append_accepted_tool_evidence(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-reactive-floor-recent",
            event_prefix="event-reactive-floor-recent",
            query_text="读取 reactive protected evidence",
            raw_result_text="recent reactive protected evidence",
        )
        reactive_seed = _seed_current_run(store, session_id=session_id)
        run, attempt, dispatch_record = _read_rows(
            store.transaction_runner,
            reactive_seed,
        )
        context = host_engine_ingest._ValidatedCandidate(
            candidate=_reactive_compaction_candidate(
                run=run,
                attempt=attempt,
                dispatch_record=dispatch_record,
            ),
            run=run,
            attempt=attempt,
            dispatch_record=dispatch_record,
        )
        frozen_blocks = store.transaction_runner.run_read(
            lambda transaction: host_engine_ingest._frozen_reactive_material_blocks(
                context=context,
                display_text="dispatch prompt",
                material_view=build_pre_dispatch_compact_material_view(
                    transaction,
                    EventLogStore(),
                    run=run,
                    current_display_text="dispatch prompt",
                ),
            )
        )
        current_blocks = tuple(
            block for block in frozen_blocks if block.section is CompactMaterialSection.CURRENT_INPUT_ANCHOR
        )
        protected_blocks = tuple(block for block in frozen_blocks if block.turn_group_id == "run-reactive-floor-recent")
        protected_kinds = frozenset(block.kind for block in protected_blocks)

        assert len(current_blocks) == 1
        assert current_blocks[0].canonical_source_refs == ("event-input-dispatch",)
        assert all(block.section is not CompactMaterialSection.CURRENT_INPUT_ANCHOR for block in protected_blocks)
        assert CompactMaterialBlockKind.USER_INPUT in protected_kinds
        assert CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER in protected_kinds
        assert CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE in protected_kinds
        assert any(block.text == "recent reactive protected material" for block in protected_blocks)
        assert any(block.text == "recent reactive protected final answer" for block in protected_blocks)
        assert any("recent reactive protected evidence" in block.text for block in protected_blocks)
        reactive_scheduler = await _open_scheduler(
            tmp_path,
            store,
            _ReactiveRecoveryWorkerFactory(),
            context_budget_policy=_soft_compact_policy(),
            context_compactor=reactive_compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_floor_one_memory_policy(),
        )
        try:
            reactive_scheduler.wake_dispatch(_pending_dispatch(reactive_seed))
            assert (await reactive_scheduler.drain_once()).dispatched == 1
            await _wait_for_compactor_request_count(reactive_compactor, 1)

            request = reactive_compactor.prepared_requests[0]
            assert request.trigger_source is ContextCompactionTriggerSource.REACTIVE
            assert "eventlog:user:event-reactive-floor-old-input" in request.segment_selection.selected_block_ids
            for block in protected_blocks:
                assert request.segment_selection.excluded_reason_codes[block.block_id] == "protected_recent_raw_floor"
        finally:
            await reactive_scheduler.close()


@pytest.mark.asyncio
async def test_reactive_compact_failure_fallback_dispatch_uses_failed_view(
    tmp_path: Path,
) -> None:
    """reactive compact failure fallback 创建新 Attempt 且不依赖 compact artifact。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        factory = _ReactiveRecoveryWorkerFactory()
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            context_budget_policy=_soft_compact_policy(),
            lane_default_timeout_seconds=1.0,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            assert (await scheduler.drain_once()).dispatched == 1
            await _wait_for_run_status(
                store.transaction_runner,
                seeded.run_id,
                expected_run=RunStatus.SUCCEEDED,
            )
            await _wait_for_active_tasks_to_finish(scheduler)

            assert len(factory.accepted_snapshots) == 2
            assert factory.accepted_snapshots[1].attempt_id != seeded.attempt_id
            assert factory.accepted_snapshots[1].execution_id != seeded.execution_id
            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 2
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 0
            assert _event_count(store.transaction_runner, "RUN_LOST") == 0
            failed = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_FAILED,
            )
            payload = _event_payload(failed)
            assert payload["fallback_action"] == "dispatch"
            assert payload["fallback_policy_decision"] == ("deterministic_recent_window")
            second_contents = tuple(
                content
                for content in (_message_text(message) for message in factory.accepted_requests[1].messages)
                if content is not None
            )
            assert "Accepted compact artifact is available for this run." not in ("\n".join(second_contents))
            assert second_contents[-1] == "dispatch prompt"
        finally:
            await scheduler.close()


def test_reactive_fallback_pipeline_uses_memory_policy_caps(tmp_path: Path) -> None:
    """reactive fallback pipeline helper 使用 MemoryProjectionPolicy fallback caps。"""

    run, attempt, dispatch_record = _seed_current_run_rows(tmp_path)
    policy = _soft_compact_policy(
        context_window_size=500,
        soft_threshold_tokens=300,
        hard_threshold_tokens=420,
    )
    memory_policy = _fallback_cap_memory_policy()
    source_snapshot = CompactPipelineSourceSnapshot(
        session_id=run.session_id,
        run_id=run.run_id,
        trigger_source=ContextCompactionTriggerSource.REACTIVE,
        current_input_ref=run.input_event_id,
        current_input_text="dispatch prompt",
        input_event_sequence=run.input_event_sequence,
        material_blocks=(
            run_input_material_block(
                block_id="eventlog:user:event-input-run-dispatch-old",
                section=CompactMaterialSection.TRACE_MATERIAL,
                kind=CompactMaterialBlockKind.USER_INPUT,
                text="older reactive fallback material that cap must drop",
                canonical_source_refs=("event-input-run-dispatch-old",),
                event_sequence=1,
                turn_group_id="run-dispatch-old",
            ),
        ),
        previous_compacted_view=(),
        source_boundary=CompactMaterialSourceBoundary(
            latest_compacted_event_id=None,
            latest_compacted_event_sequence=None,
            post_compact_delta_start_sequence=1,
            post_compact_delta_end_sequence=run.input_event_sequence,
            current_input_event_sequence=run.input_event_sequence,
        ),
        material_view_digest="digest:reactive-fallback-test-view",
        material_source_refs=("event-input-run-dispatch-old",),
    )

    decision = build_fallback_decision_input(
        source_snapshot=source_snapshot,
        context_policy=policy,
        memory_policy=memory_policy,
        operation_id="event-reactive-request",
        failure_reason="test_failure",
        attempt_count=1,
        retry_repair_budget_exhausted=True,
        budget_after_attempted_compact=None,
    )
    failed_input = decision.failed_payload_input

    assert decision.action_hint == "dispatch"
    assert failed_input.fallback_input_window is not None
    assert failed_input.fallback_input_window["selected_block_ids"] == ["current:event-input-dispatch"]
    assert "eventlog:user:event-input-run-dispatch-old" in (
        _required_json_text_tuple(failed_input.fallback_input_window["dropped_block_ids"])
    )
    assert "fallback_tier" not in failed_input.fallback_input_window


@pytest.mark.asyncio
async def test_reactive_repeated_overflow_dispatch_loop_fails_closed_at_limit(
    tmp_path: Path,
) -> None:
    """reactive overflow accepted closeout 不依赖后续 RunInputBuilder 消费。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-repeated-reactive-history",
            event_id="event-repeated-reactive-history",
            display_text="older compactable material",
            client_request_id="client-repeated-reactive-history",
            idempotency_key="idem-repeated-reactive-history",
        )
        seeded = _seed_current_run(store, session_id=session_id)
        factory = _RepeatedReactiveOverflowWorkerFactory()
        max_reactive_compactions_per_run = 2
        policy = _soft_compact_policy(max_reactive_compactions_per_run=max_reactive_compactions_per_run)
        expected_attempt_count = max_reactive_compactions_per_run + 1
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            context_budget_policy=policy,
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            assert (await scheduler.drain_once()).dispatched == 1

            await _wait_for_event_count(
                store.transaction_runner,
                CONTEXT_COMPACTION_FAILED,
                expected_count=1,
            )

            run = _read_run(store.transaction_runner, seeded.run_id)
            event_types = _event_types_for_run(store.transaction_runner, seeded.run_id)
            actual_attempt_count = _attempt_count_for_run(
                store.transaction_runner,
                seeded.run_id,
            )

            failed = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_FAILED,
            )
            payload = _event_payload(failed)

            assert run.status == RunStatus.FAILED
            assert factory.created == expected_attempt_count
            assert len(factory.accepted_snapshots) == expected_attempt_count
            assert actual_attempt_count == expected_attempt_count
            assert event_types.count(CONTEXT_COMPACTION_REQUESTED) == (max_reactive_compactions_per_run)
            assert event_types.count(CONTEXT_COMPACTED) == (max_reactive_compactions_per_run)
            assert event_types.count(CONTEXT_COMPACTION_FAILED) == 1
            assert payload["failure_reason"] == "reactive_compact_limit_reached"
            assert_failed_payload_no_fallback(
                payload,
                expected_operation_id=None,
                expected_attempt_count=0,
                expected_retry_repair_budget_exhausted=False,
            )
            assert event_types.count("RUN_LOST") == 0
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_reactive_recovery_uses_fresh_duplicate_governance_attempt(
    tmp_path: Path,
) -> None:
    """reactive recovery 新 Attempt 对相同工具参数执行 fresh request。"""

    first_event_gate = asyncio.Event()
    tool = _CountingTool()
    duplicate_policy = DuplicateGovernancePolicy(default_duplicate_decision=DuplicateDecisionKind.REUSE)
    tool_policy = _agent_policy(True)
    tooling = _tooling_options(
        tool,
        duplicate_governance_policy=duplicate_policy,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-duplicate-reactive-history",
            event_id="event-duplicate-reactive-history",
            display_text="older compactable material",
            client_request_id="client-duplicate-reactive-history",
            idempotency_key="idem-duplicate-reactive-history",
        )
        seeded = _seed_current_run(
            store,
            session_id=session_id,
            agent_policy=tool_policy,
            tool_schemas=tuple(definition.to_tool_schema() for definition in tooling.business_tool_bundle.definitions),
            tooling_options=tooling,
        )
        factory = _ReactiveRecoveryWorkerFactory(
            final_blocks=True,
            first_event_gate=first_event_gate,
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            agent_policy=tool_policy,
            tooling_options=tooling,
            context_budget_policy=_soft_compact_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
            memory_projection_policy=_compact_no_floor_memory_policy(),
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            assert (await scheduler.drain_once()).dispatched == 1
            first_request = factory.accepted_requests[0]
            first_tool_outcome = await first_request.tool_executor.execute(
                _tool_execution_request(
                    seeded,
                    first_request,
                    ToolCallRequest(
                        tool_call_id="tool-call-first-attempt",
                        name="fake_dispatch_tool",
                        arguments={"ticker": "DAYU"},
                        index_in_iteration=0,
                        provider_state=None,
                    ),
                )
            )
            first_duplicate_outcome = await first_request.tool_executor.execute(
                _tool_execution_request(
                    seeded,
                    first_request,
                    ToolCallRequest(
                        tool_call_id="tool-call-first-attempt-duplicate",
                        name="fake_dispatch_tool",
                        arguments={"ticker": "DAYU"},
                        index_in_iteration=0,
                        provider_state=None,
                    ),
                )
            )

            assert isinstance(
                first_tool_outcome.records[0].outcome,
                ToolCompletedOutcome,
            )
            assert isinstance(
                first_duplicate_outcome.records[0].outcome,
                ToolCompletedOutcome,
            )
            assert tool.call_count == 1

            first_event_gate.set()
            await _wait_for_event_count(
                store.transaction_runner,
                CONTEXT_COMPACTED,
                expected_count=1,
            )

            assert factory.accepted_snapshots[0].attempt_id == seeded.attempt_id
            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 2
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 1
            assert _event_count(store.transaction_runner, "RUN_LOST") == 0
            assert tool.call_count == 1
            assert _run_status(store.transaction_runner, seeded.run_id) in (
                RunStatus.RECOVERING,
                RunStatus.RUNNING,
                RunStatus.FAILED,
            )
        finally:
            await scheduler.close()


@pytest.mark.parametrize(
    ("requested_names", "expected_names"),
    (
        (None, ("tool_a", "tool_b")),
        (frozenset({"tool_b"}), ("tool_b",)),
        (frozenset(), ()),
    ),
)
@pytest.mark.asyncio
async def test_dispatch_consumes_exact_admission_tool_names(
    tmp_path: Path,
    requested_names: frozenset[str] | None,
    expected_names: tuple[str, ...],
) -> None:
    """all/subset/none 均消费 admission 冻结的 exact names。

    :param tmp_path: pytest 临时目录。
    :param requested_names: admission selector 输入。
    :param expected_names: frozen candidate 应暴露的业务工具名。
    """

    tooling = _tooling_options_for_names(("tool_a", "tool_b"))
    frozen_facts = effective_tool_facts_json(
        requested_names,
        tooling_options=tooling,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id="run-exact-tool-selection",
            display_text="exact tool selection",
            agent_policy=_agent_policy(True),
            effective_tool_set=frozen_facts,
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            agent_policy=_agent_policy(True),
            tooling_options=tooling,
        )
        try:
            run = store.transaction_runner.run_read(lambda transaction: read_run_by_id(transaction, seeded.run_id))
            assert run is not None
            pending = _start_governed_for_test(
                store.transaction_runner,
                scheduler,
                run,
            )
            source = store.transaction_runner.run_read(
                lambda transaction: load_prepared_runner_call_source_in_transaction(
                    transaction,
                    EventLogStore(),
                    run_id=seeded.run_id,
                    attempt_id=pending.attempt_id,
                    execution_id=pending.execution_id,
                )
            )
            assert tuple(schema.function.name for schema in source.candidate.tool_schemas) == expected_names
        finally:
            await scheduler.close()


def test_replay_no_tool_facts_are_independent_of_current_tooling() -> None:
    """repair replay 的 empty tool truth 不读取当前业务 bundle/source。"""

    current_tooling = _tooling_options_for_names(("tool_a",))
    facts = parse_effective_tool_facts(
        effective_tool_facts_json(
            frozenset(),
            tooling_options=None,
        )
    )

    assert facts.selector is EffectiveBusinessToolSelector.NONE
    assert facts.effective_business_tool_names == frozenset()
    assert facts.source_refs == ()
    assert (
        validate_effective_tool_facts_runtime(
            facts,
            tooling_options=None,
        )
        == frozenset()
    )
    with pytest.raises(
        HostDurableError,
        match="current business tool bundle",
    ):
        validate_effective_tool_facts_runtime(
            facts,
            tooling_options=current_tooling,
        )


def test_steer_explicit_subset_fails_when_frozen_policy_disables_tools(
    tmp_path: Path,
) -> None:
    """steer 显式非空 subset 在 policy 禁用工具时保留 caller-intent fail closed。

    :param tmp_path: pytest 临时目录。
    """

    tooling = _tooling_options_for_names(("tool_a", "tool_b"))
    execution_config = effective_execution_config_json(
        runner_spec=_runner_spec(),
        runner_options=RunnerCallOptions(
            temperature=None,
            max_tokens=None,
            top_p=None,
            stream=False,
        ),
        agent_policy=_agent_policy(False),
        runner_spec_source="test",
        runner_options_source="test",
        agent_policy_source="test",
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-steer-subset-policy-disabled",
            event_id="event-steer-subset-policy-disabled",
            effective_execution_config=execution_config,
            effective_tool_set=effective_tool_facts_json(
                frozenset({"tool_a"}),
                tooling_options=tooling,
            ),
        )

        with pytest.raises(
            HostDurableError,
            match="explicit subset tools are unavailable",
        ):
            store.transaction_runner.run_read(
                lambda transaction: host_admission._strict_steer_candidate_inputs(
                    transaction=transaction,
                    input_event=cast(
                        EventLogRow,
                        EventLogStore().read_event_by_id(
                            transaction,
                            "event-steer-subset-policy-disabled",
                        ),
                    ),
                    tooling_options=tooling,
                    enable_truncation_manager=False,
                    replay=False,
                )
            )


@pytest.mark.parametrize(
    "drift_kind",
    ("added_tool", "same_name_schema", "bundle_digest", "schema_digest", "source_ref"),
)
@pytest.mark.asyncio
async def test_dispatch_tool_drift_fails_before_start_without_artifacts(
    tmp_path: Path,
    drift_kind: str,
) -> None:
    """bundle/schema/source drift 与冻结摘要损坏均在 start 前 fail closed。

    :param tmp_path: pytest 临时目录。
    :param drift_kind: 单一工具事实漂移类别。
    """

    frozen_tooling = _tooling_options_for_names(("tool_a",))
    runtime_tooling = frozen_tooling
    frozen_facts = effective_tool_facts_json(
        None,
        tooling_options=frozen_tooling,
    )
    assert isinstance(frozen_facts, Mapping)
    tampered_facts: dict[str, JsonValue] = dict(frozen_facts)
    if drift_kind == "added_tool":
        runtime_tooling = _tooling_options_for_names(("tool_a", "tool_b"))
    elif drift_kind == "same_name_schema":
        runtime_tooling = _tooling_options_for_names(
            ("tool_a",),
            description="schema drift",
        )
    elif drift_kind == "bundle_digest":
        tampered_facts["business_bundle_digest"] = sha256_digest_json({"corrupt": "bundle"})
    elif drift_kind == "schema_digest":
        corrupt_digest = sha256_digest_json({"corrupt": "schema"})
        tampered_facts["effective_schema_digest"] = corrupt_digest
        tampered_facts["tool_snapshot_ref"] = f"tools:{corrupt_digest}"
    else:
        source_refs = tampered_facts["source_refs"]
        assert isinstance(source_refs, list)
        source_ref = source_refs[0]
        assert isinstance(source_ref, Mapping)
        corrupt_source_ref: dict[str, JsonValue] = dict(source_ref)
        corrupt_source_ref["source_id"] = "corrupt-source"
        tampered_facts["source_refs"] = [corrupt_source_ref]
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id=f"run-tool-drift-{drift_kind}",
            display_text="tool drift",
            agent_policy=_agent_policy(True),
            effective_tool_set=tampered_facts,
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            agent_policy=_agent_policy(True),
            tooling_options=runtime_tooling,
        )
        try:
            run = store.transaction_runner.run_read(lambda transaction: read_run_by_id(transaction, seeded.run_id))
            assert run is not None
            with pytest.raises(HostDurableError):
                _start_governed_for_test(
                    store.transaction_runner,
                    scheduler,
                    run,
                )
            unchanged = store.transaction_runner.run_read(
                lambda transaction: read_run_by_id(transaction, seeded.run_id)
            )
            assert unchanged is not None
            assert unchanged.current_attempt_id is None
            assert "RUN_STARTED" not in _event_types_for_run(
                store.transaction_runner,
                seeded.run_id,
            )
            assert "RUNNER_CALL_INPUT_ASSEMBLED" not in _event_types_for_run(
                store.transaction_runner,
                seeded.run_id,
            )
        finally:
            await scheduler.close()


@pytest.mark.parametrize(
    "stage",
    (
        ContextSizingStage.ORDINARY,
        ContextSizingStage.POST_COMPACT,
        ContextSizingStage.DISPATCH_FALLBACK,
    ),
)
@pytest.mark.asyncio
async def test_no_budget_manifest_preserves_actual_dispatch_stage(
    tmp_path: Path,
    stage: ContextSizingStage,
) -> None:
    """无 context policy 时 ordinary/post-compact/fallback 均记录实际 stage。

    :param tmp_path: pytest 临时目录。
    :param stage: 本次 no-budget candidate 的真实阶段。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id=f"run-no-budget-{stage.value}",
            display_text="no budget stage",
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
        )
        try:
            run = store.transaction_runner.run_read(lambda transaction: read_run_by_id(transaction, seeded.run_id))
            assert run is not None
            scheduler._catch_up_memory_projection_before_candidate(run.session_id)
            outcome = store.transaction_runner.run_write(
                lambda transaction: scheduler._prepare_and_commit_start_in_transaction(
                    transaction,
                    run,
                    stage=stage,
                )
            )
            assert outcome.pending_dispatch is not None
            pending = outcome.pending_dispatch
            source = store.transaction_runner.run_read(
                lambda transaction: load_prepared_runner_call_source_in_transaction(
                    transaction,
                    EventLogStore(),
                    run_id=seeded.run_id,
                    attempt_id=pending.attempt_id,
                    execution_id=pending.execution_id,
                )
            )
            assert source.manifest.sizing_snapshot.sizing_stage is stage
            event_types = _event_types_for_run(
                store.transaction_runner,
                seeded.run_id,
            )
            assert CONTEXT_BUDGET_EVALUATED not in event_types
            assert (
                _has_context_usage_activity(
                    store.transaction_runner,
                    seeded.run_id,
                )
                is False
            )
        finally:
            await scheduler.close()


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造 Host durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "host.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=0.25,
            write_busy_retry_count=3,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.01,
        ),
    )


async def _open_scheduler(
    tmp_path: Path,
    store: HostDurableStore,
    factory: LocalEngineWorkerFactory,
    *,
    worker_startup_timeout_seconds: float = 1.0,
    lane_db_path: Path | None = None,
    lane_default_timeout_seconds: float = 0.01,
    active_registry: ActiveWorkerRegistry | None = None,
    agent_policy: AgentPolicy | None = None,
    tooling_options: HostToolingOptions | None = None,
    projection_catchup: ProjectionCatchupPort | None = None,
    context_budget_policy: ContextBudgetPolicy | None = None,
    context_compactor: ContextCompactor | None = None,
    compact_artifact_root: Path | None = None,
    memory_projection_policy: MemoryProjectionPolicy | None = None,
    host_handle_id: str = "host-test",
    host_instance_identity: HostInstanceIdentity | None = None,
    terminal_port_factory: _RecordingTerminalPortFactory | None = None,
    dispatch_poll_interval_seconds: float = 0.01,
) -> HostDispatchScheduler:
    """打开测试 scheduler。

    :param tmp_path: pytest 临时目录。
    :param store: durable store。
    :param factory: worker factory。
    :param worker_startup_timeout_seconds: worker startup timeout。
    :param lane_db_path: runtime lane DB 路径。
    :param lane_default_timeout_seconds: lane acquire 默认 timeout。
    :param active_registry: active worker registry。
    :param agent_policy: 可选 AgentPolicy；无则使用 no-tool policy。
    :param tooling_options: 可选 Host 工具装配选项。
    :param projection_catchup: 可选 projection catch-up port。
    :param context_budget_policy: 可选 pre-start context budget policy。
    :param context_compactor: 可选 context compactor。
    :param compact_artifact_root: 可选 compact artifact 根目录。
    :param memory_projection_policy: 可选 memory projection policy。
    :param host_handle_id: scheduler 使用的 Host handle id。
    :param host_instance_identity: 可选 Host instance 身份；用于测试 handle
        与 instance id 不同的 owner 写入路径。
    :param terminal_port_factory: 可选 construction/bind recording factory。
    :param dispatch_poll_interval_seconds: scheduler 后台 polling interval。
    :returns: scheduler。
    :raises Exception: lane controller 或 durable host instance 注册失败时透传。
    """

    local_execution = HostLocalExecutionOptions(
        lane_db_path=(lane_db_path if lane_db_path is not None else tmp_path / "lane.sqlite3"),
        lane_name=_LANE_NAME,
        lane_capacity=1,
        lane_default_timeout_seconds=lane_default_timeout_seconds,
        lane_claim_ttl_seconds=1.0,
        lane_heartbeat_interval_seconds=0.1,
        worker_startup_timeout_seconds=worker_startup_timeout_seconds,
        dispatch_poll_interval_seconds=dispatch_poll_interval_seconds,
        runner_spec=_runner_spec(),
        runner_options=RunnerCallOptions(temperature=None, max_tokens=None, top_p=None, stream=False),
        agent_policy=agent_policy if agent_policy is not None else _agent_policy(False),
        worker_factory=factory,
        tooling_options=tooling_options,
        context_budget_policy=context_budget_policy,
        context_compactor=context_compactor,
        compact_artifact_root=compact_artifact_root,
        memory_projection_policy=(
            memory_projection_policy if memory_projection_policy is not None else default_memory_projection_policy()
        ),
    )
    if host_instance_identity is None:
        return await HostDispatchScheduler.open(
            transaction_runner=store.transaction_runner,
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            terminal_post_commit_port_factory=(
                terminal_port_factory if terminal_port_factory is not None else _RecordingTerminalPortFactory()
            ),
            local_execution=local_execution,
            host_handle_id=host_handle_id,
            active_registry=active_registry,
            projection_catchup_port=projection_catchup,
            session_new_work_access=ExplicitFakeSessionAccess(allowed_session_ids=None),
        )
    _register_host_instance(store.transaction_runner, host_instance_identity)
    lane_controller = await LaneController.open(
        [
            LaneConfig(
                name=local_execution.lane_name,
                capacity=local_execution.lane_capacity,
                default_timeout_seconds=local_execution.lane_default_timeout_seconds,
                claim_ttl_seconds=local_execution.lane_claim_ttl_seconds,
                heartbeat_interval_seconds=(local_execution.lane_heartbeat_interval_seconds),
            )
        ],
        coordinator=SQLiteLaneCoordinatorConfig(db_path=local_execution.lane_db_path),
        owner=LaneOwner(
            owner_id=f"lane-owner-{host_handle_id}",
            pid=host_instance_identity.pid,
            process_start_token=host_instance_identity.process_start_token,
        ),
    )
    return HostDispatchScheduler(
        transaction_runner=store.transaction_runner,
        transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        terminal_post_commit_port=_RecordingTerminalPort(),
        event_log_store=EventLogStore(),
        local_execution=local_execution,
        lane_controller=lane_controller,
        host_handle_id=host_handle_id,
        host_instance_identity=host_instance_identity,
        active_registry=active_registry,
        projection_catchup_port=projection_catchup,
        session_new_work_access=ExplicitFakeSessionAccess(allowed_session_ids=None),
    )


def _register_host_instance(transaction_runner: HostTransactionRunner, identity: HostInstanceIdentity) -> None:
    """注册测试 scheduler 的 Host instance row。

    :param transaction_runner: Host transaction runner。
    :param identity: 待注册的 Host instance 身份。
    :returns: ``None``。
    :raises Exception: durable host instance 注册失败时透传。
    """

    def _operation(transaction: HostTransaction) -> None:
        register_current_instance(transaction, identity)

    transaction_runner.run_write(_operation)


def _runner_spec() -> RunnerSpec:
    """构造测试 RunnerSpec。

    :returns: RunnerSpec。
    """

    return RunnerSpec(
        provider="test",
        model="test-model",
        endpoint="https://example.invalid",
        api_key_ref="secret:test",
        headers={},
        client_correlation_policy=ClientCorrelationPolicy.DISABLED,
        supports_tool_calling=False,
        supports_streaming=False,
        supports_stream_usage=False,
        default_timeout_seconds=1.0,
        max_retries=0,
        provider_request=None,
    )


def _proposal_compactor_agent_request(
    request: CompactionRequest,
    *,
    cancellation_token: CancellationToken,
    compaction_operation_id: str | None,
    compaction_attempt_number: int,
) -> AgentRunRequest:
    """构造 proactive compactor proposal 的 deterministic AgentRunRequest。

    :param request: Host 构造的 compaction request。
    :param cancellation_token: Host 注入 compactor 的真实取消 token。
    :param compaction_operation_id: Host compaction operation id。
    :param compaction_attempt_number: operation 内 proposal attempt 序号。
    :returns: proposal runner request。
    """

    return AgentRunRequest(
        run_id=(f"compactor-run:{request.run_id}:{compaction_operation_id}:{compaction_attempt_number}"),
        session_id="context-compactor:test",
        attempt_id=None,
        execution_id=None,
        messages=(
            SystemMessage(role=AgentMessageRole.SYSTEM, content="system"),
            UserMessage(role=AgentMessageRole.USER, content="proactive user"),
        ),
        disable_tools=True,
        runner_spec=_runner_spec(),
        runner_options=RunnerCallOptions(
            temperature=None,
            max_tokens=None,
            top_p=None,
            stream=False,
        ),
        agent_policy=_agent_policy(False),
        tool_schemas=(),
        tool_executor=NoToolExecutor(),
        cancellation_token=cancellation_token,
    )


def _tooling_options(
    tool: _CountingTool,
    *,
    duplicate_governance_policy: DuplicateGovernancePolicy | None = None,
) -> HostToolingOptions:
    """构造 tool-enabled dispatch 测试用工具装配选项。

    :param tool: 测试业务工具 callable。
    :param duplicate_governance_policy: 可选 duplicate governance 策略。
    :returns: HostToolingOptions。
    """

    return HostToolingOptions(
        business_tool_bundle=ToolBundle(definitions=(_tool_definition("fake_dispatch_tool", tool),)),
        source_refs=(
            ToolBundleSourceRef(
                source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
                source_id="dispatch-tool-test",
            ),
        ),
        duplicate_governance_policy=(
            duplicate_governance_policy if duplicate_governance_policy is not None else DuplicateGovernancePolicy()
        ),
    )


def _tooling_options_for_names(
    names: tuple[str, ...],
    *,
    description: str = "dispatch fake tool",
) -> HostToolingOptions:
    """构造 exact-name/tool-schema contract 测试用工具装配。

    :param names: 按 bundle 顺序给出的业务工具名。
    :param description: 所有测试工具共用的 schema description。
    :returns: 带稳定 source ref 的 Host 工具选项。
    """

    tool = _CountingTool()
    return HostToolingOptions(
        business_tool_bundle=ToolBundle(
            definitions=tuple(_tool_definition(name, tool, description=description) for name in names)
        ),
        source_refs=(
            ToolBundleSourceRef(
                source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
                source_id="dispatch-tool-contract-test",
            ),
        ),
    )


def _tool_definition(
    name: str,
    tool: _CountingTool,
    *,
    description: str = "dispatch fake tool",
) -> ToolDefinition:
    """构造测试工具声明。

    :param name: 工具名。
    :param tool: 测试工具 callable。
    :param description: LLM-facing schema description。
    :returns: ToolDefinition。
    """

    return ToolDefinition(
        name=name,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=name,
                description=description,
                parameters=_tool_parameters(),
            ),
        ),
        callable=tool,
        execution=AsyncDirectToolExecutionCapability(),
        truncate=None,
        display=None,
        tags=("dispatch",),
    )


def _tool_parameters() -> ToolParametersSchema:
    """构造测试工具参数 schema。

    :returns: ToolParametersSchema。
    """

    properties: dict[str, JsonValue] = {"ticker": {"type": "string"}}
    return ToolParametersSchema(
        type="object",
        properties=properties,
        required=("ticker",),
        additional_properties=False,
    )


def _tool_execution_request(
    seeded: _SeededRun, request: AgentRunRequest, call: ToolCallRequest
) -> BatchToolExecutionRequest:
    """构造 ToolRuntime 批式执行请求。

    :param seeded: seeded Run refs。
    :param request: scheduler 传给 worker 的 AgentRunRequest。
    :param call: 工具调用请求。
    :returns: BatchToolExecutionRequest。
    """

    return BatchToolExecutionRequest(
        calls=(call,),
        context=BatchToolExecutionContext(
            run_id=seeded.run_id,
            session_id=seeded.session_id,
            iteration_id="iteration-dispatch-tool",
            timeout_seconds=1.0,
            cancellation_token=request.cancellation_token,
            correlation_id="correlation-dispatch-tool",
        ),
    )


def _message_text(message: AgentMessage) -> str | None:
    """读取 Agent message 的文本内容。

    :param message: Agent message。
    :returns: 文本内容；assistant 空内容时返回 ``None``。
    """

    return message.content


def _agent_policy(allow_tool_calls: bool) -> AgentPolicy:
    """构造测试 AgentPolicy。

    :param allow_tool_calls: 是否允许工具调用。
    :returns: AgentPolicy。
    """

    return AgentPolicy(
        max_iterations=1,
        continuation_max_attempts=0,
        allow_tool_calls=allow_tool_calls,
        tool_execution_timeout_seconds=1.0,
        fallback_prompt="test fallback prompt",
        continuation_prompt="test continuation prompt",
    )


def _seed_current_run(
    store: HostDurableStore,
    *,
    session_id: str | None = None,
    agent_policy: AgentPolicy | None = None,
    tool_schemas: tuple[ToolSchema, ...] = (),
    tooling_options: HostToolingOptions | None = None,
) -> _SeededRun:
    """创建 running Run、STARTING Attempt 和 pending dispatch。

    :param store: durable store。
    :param session_id: 可选已有 Session id；不传则创建默认测试 Session。
    :param agent_policy: frozen Agent policy；缺失时使用默认no-tool policy。
    :param tool_schemas: frozen selected tool schemas。
    :param tooling_options: admission 与 dispatch 共用的 construction-time 工具真源。
    :returns: seeded run 摘要。
    """

    actual_session_id = _ensure_session_id(store.transaction_runner) if session_id is None else session_id
    seeded = _SeededRun(
        session_id=actual_session_id,
        run_id="run-dispatch",
        attempt_id="attempt-dispatch",
        execution_id="execution-dispatch",
        dispatch_record_id="dispatch-dispatch",
    )
    policy = agent_policy if agent_policy is not None else _agent_policy(False)
    runner_options = RunnerCallOptions(
        temperature=None,
        max_tokens=None,
        top_p=None,
        stream=False,
    )
    effective_execution_config = effective_execution_config_json(
        runner_spec=_runner_spec(),
        runner_options=runner_options,
        agent_policy=policy,
        runner_spec_source="test",
        runner_options_source="test",
        agent_policy_source="test",
    )
    effective_snapshot = effective_execution_snapshot_from_json(effective_execution_config)
    input_event_sequence = _append_user_input(
        store.transaction_runner,
        session_id=actual_session_id,
        run_id=seeded.run_id,
        event_id="event-input-dispatch",
        effective_execution_config=effective_execution_config,
        effective_tool_set=effective_tool_facts_json(
            None,
            tooling_options=tooling_options,
        ),
    )

    def _accept_operation(transaction: HostTransaction) -> None:
        accepted = create_accepted_run_in_transaction(
            transaction,
            EventLogStore(),
            CreateAcceptedRunInput(
                session_id=actual_session_id,
                run_id=seeded.run_id,
                client_request_id="client-dispatch",
                input_event_id="event-input-dispatch",
                input_event_sequence=input_event_sequence,
                run_accepted_event_id="event-run-accepted-dispatch",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                idempotency_key="idem-dispatch",
                execution_target="target-dispatch",
                queue_policy=RunQueuePolicy.QUEUE,
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )
        assert accepted.run is not None

    store.transaction_runner.run_write(_accept_operation)
    required_cursor = store.transaction_runner.run_read(
        lambda transaction: EventLogStore().read_events_after(transaction, 0, limit=100)[-1].event_sequence
    )
    catch_up = catch_up_conversation_memory_projection(
        store.transaction_runner,
        policy=default_memory_projection_policy(),
        batch_size=100,
        max_event_sequence=required_cursor,
    )
    assert catch_up.target_reached is True

    def _start_operation(transaction: HostTransaction) -> None:
        run = read_run_by_id(transaction, seeded.run_id)
        assert run is not None
        policy_snapshot = PolicySnapshot(
            runner_spec=effective_snapshot.runner_spec,
            runner_options=effective_snapshot.runner_options,
            agent_policy=effective_snapshot.agent_policy,
            policy_snapshot_ref=effective_snapshot.policy_snapshot_ref,
        )
        candidate = prepare_runner_call_candidate_in_transaction(
            transaction,
            EventLogStore(),
            run=run,
            current_input_event=cast(
                EventLogRow,
                EventLogStore().read_event_by_id(
                    transaction,
                    run.input_event_id,
                ),
            ),
            continuity=SessionContinuityView(
                messages=(),
                source_refs=(),
            ),
            policy_snapshot=policy_snapshot,
            tool_schemas=tool_schemas,
            disable_tools=not tool_schemas,
            tool_execution_mode=(
                ToolExecutionMode.TOOL_ENABLED if tool_schemas else ToolExecutionMode.NO_TOOL_DISABLED
            ),
            memory_projection_policy=default_memory_projection_policy(),
        )
        start_input = StartGovernedRunInput(
            run_id=run.run_id,
            expected_status=RunStatus.ACCEPTED,
            run_started_event_id="event-run-started-dispatch",
            attempt_started_event_id="event-attempt-started-dispatch",
            attempt_id=seeded.attempt_id,
            execution_id=seeded.execution_id,
            dispatch_record_id=seeded.dispatch_record_id,
            occurred_at=_NOW,
            actor="tester",
            source="pytest",
            start_reason=RunStartReason.INITIAL,
            worker_kind=WorkerKind.LOCAL,
            owner_host_instance_id=None,
        )
        record_prepared_runner_call_candidate_in_transaction(
            transaction,
            EventLogStore(),
            PayloadStore(),
            run=run,
            attempt_id=start_input.attempt_id,
            execution_id=start_input.execution_id,
            occurred_at=start_input.occurred_at,
            candidate=candidate,
            sizing_snapshot=unavailable_runner_call_sizing_snapshot(
                RunnerCallSizingUnavailableReason.CONTEXT_POLICY_UNAVAILABLE,
                sizing_stage=ContextSizingStage.ORDINARY,
            ),
        )
        started = start_governed_run_with_starting_attempt_in_transaction(
            transaction,
            EventLogStore(),
            start_input,
        )
        assert started.run is not None
        assert started.attempt is not None
        assert started.dispatch_record is not None

    store.transaction_runner.run_write(_start_operation)
    return seeded


def _seed_accepted_run(
    store: HostDurableStore,
    *,
    run_id: str,
    display_text: str,
    session_id: str | None = None,
    agent_policy: AgentPolicy | None = None,
    effective_tool_set: JsonValue | None = None,
) -> _AcceptedSeededRun:
    """创建 pre-start accepted Run，不创建 Attempt 或 dispatch。

    :param store: durable store。
    :param run_id: Run id。
    :param display_text: 当前用户输入文本。
    :param session_id: 可选已有 Session id。
    :param agent_policy: admission 冻结的 Agent policy。
    :param effective_tool_set: admission 冻结的完整 effective tool facts。
    :returns: accepted Run 摘要。
    """

    actual_session_id = _ensure_session_id(store.transaction_runner) if session_id is None else session_id
    effective_execution_config = effective_execution_config_json(
        runner_spec=_runner_spec(),
        runner_options=RunnerCallOptions(
            temperature=None,
            max_tokens=None,
            top_p=None,
            stream=False,
        ),
        agent_policy=(agent_policy if agent_policy is not None else _agent_policy(False)),
        runner_spec_source="test",
        runner_options_source="test",
        agent_policy_source="test",
    )
    input_event_id = f"event-input-{run_id}"
    input_event_sequence = _append_user_input(
        store.transaction_runner,
        session_id=actual_session_id,
        run_id=run_id,
        event_id=input_event_id,
        display_text=display_text,
        client_request_id=f"client-{run_id}",
        idempotency_key=f"idem-input-{run_id}",
        effective_execution_config=effective_execution_config,
        effective_tool_set=effective_tool_set,
    )

    def _operation(transaction: HostTransaction) -> None:
        result = create_accepted_run_in_transaction(
            transaction,
            EventLogStore(),
            CreateAcceptedRunInput(
                session_id=actual_session_id,
                run_id=run_id,
                client_request_id=f"client-{run_id}",
                input_event_id=input_event_id,
                input_event_sequence=input_event_sequence,
                run_accepted_event_id=f"event-run-accepted-{run_id}",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                idempotency_key=f"idem-run-{run_id}",
                execution_target="target-dispatch",
                queue_policy=RunQueuePolicy.QUEUE,
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )
        assert result.run is not None
        assert result.run.status == RunStatus.ACCEPTED

    store.transaction_runner.run_write(_operation)
    return _AcceptedSeededRun(session_id=actual_session_id, run_id=run_id)


def _seed_accepted_run_with_compactable_history(
    store: HostDurableStore,
    *,
    run_id: str,
    display_text: str,
) -> _AcceptedSeededRun:
    """在同一 Session 先写入一条可 compact 历史，再创建 accepted Run。

    :param store: durable store。
    :param run_id: 当前 Run id。
    :param display_text: 当前用户输入。
    :returns: 带可引用 source boundary 的 accepted Run 摘要。
    """

    session_id = _ensure_session_id(store.transaction_runner)
    history_run_id = f"{run_id}-history"
    _append_user_input(
        store.transaction_runner,
        session_id=session_id,
        run_id=history_run_id,
        event_id=f"event-input-{history_run_id}",
        display_text="older compactable material",
        client_request_id=f"client-{history_run_id}",
        idempotency_key=f"idem-{history_run_id}",
    )
    return _seed_accepted_run(
        store,
        run_id=run_id,
        display_text=display_text,
        session_id=session_id,
    )


def _soft_compact_policy(
    *,
    max_compaction_attempts_per_operation: int = 1,
    max_reactive_compactions_per_run: int = DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN,
    context_window_size: int = _SOFT_CONTEXT_WINDOW_SIZE,
    soft_threshold_tokens: int | None = None,
    hard_threshold_tokens: int = _SOFT_HARD_THRESHOLD_TOKENS,
) -> ContextBudgetPolicy:
    """构造会对测试 prompt 触发 soft compact 的预算策略。

    :param max_compaction_attempts_per_operation: 单个 compaction operation 的 proposal attempt 上限。
    :param max_reactive_compactions_per_run: 单个 Run 允许的 reactive compact 次数。
    :param context_window_size: context window token 数。
    :param soft_threshold_tokens: 可选 soft threshold token 数。
    :param hard_threshold_tokens: hard threshold token 数。
    :returns: context budget policy。
    """

    actual_soft_threshold_tokens = (
        int((context_window_size - _SOFT_RESERVED_OUTPUT_TOKENS) * (1 - _SOFT_SAFETY_MARGIN_RATIO))
        if soft_threshold_tokens is None
        else soft_threshold_tokens
    )
    return context_budget_policy_from_threshold_tokens(
        context_window_size=context_window_size,
        soft_threshold_tokens=actual_soft_threshold_tokens,
        hard_threshold_tokens=hard_threshold_tokens,
        max_reactive_compactions_per_run=max_reactive_compactions_per_run,
        max_compaction_attempts_per_operation=(max_compaction_attempts_per_operation),
        policy_ref="test-soft-compact-policy",
    )


def _fallback_cap_memory_policy() -> MemoryProjectionPolicy:
    """构造验证 production fallback caps 接线的 memory policy。

    :returns: fallback item cap 收紧到 current-only 的 memory policy。
    """

    return MemoryProjectionPolicy(
        context_window_size=8192,
        selected_recent_window_item_cap=8,
        selected_recent_window_char_cap=4096,
        selected_recent_window_turn_floor=0,
        fallback_selected_recent_window_item_cap=1,
        fallback_selected_recent_window_char_cap=4096,
        evidence_fact_item_cap=16,
        evidence_fact_char_cap=4096,
        evidence_fact_floor=1,
        session_summary_char_cap=1024,
        answer_anchor_item_cap=8,
        answer_anchor_char_cap=2048,
        forward_intent_item_cap=8,
        forward_intent_char_cap=2048,
        reference_continuity_item_cap=8,
        reference_continuity_char_cap=2048,
        reference_continuity_item_floor=0,
        max_lag_events_for_inline_delta=100,
        max_delta_repair_events=16,
        policy_ref="test-fallback-cap-memory-policy",
    )


def _compact_no_floor_memory_policy() -> MemoryProjectionPolicy:
    """构造不保护 recent floor 的 legacy compact 测试 policy。

    仅用于非 floor 语义测试，避免旧测试把 protected recent floor 行为误判为
    compactor 输入缺失。

    :returns: selected recent turn floor 为 0 的 memory policy。
    """

    return replace(
        default_memory_projection_policy(),
        selected_recent_window_turn_floor=0,
    )


def _compact_floor_one_memory_policy() -> MemoryProjectionPolicy:
    """构造保护最近一个 turn group 的 compact 测试 policy。

    :returns: selected recent turn floor 为 1 的 memory policy。
    """

    return replace(
        default_memory_projection_policy(),
        selected_recent_window_turn_floor=1,
    )


def _soft_threshold_prompt() -> str:
    """返回触发 soft threshold 且未达 hard threshold 的测试 prompt。

    :returns: 测试 prompt。
    """

    return "x" * _SOFT_THRESHOLD_PROMPT_CHAR_COUNT


def _hard_threshold_prompt() -> str:
    """返回触发 hard threshold 的测试 prompt。

    :returns: 测试 prompt。
    """

    return "x" * _HARD_THRESHOLD_PROMPT_CHAR_COUNT


def _append_proactive_compaction_requested(
    transaction_runner: HostTransactionRunner,
    *,
    seeded: _AcceptedSeededRun,
    event_id: str,
) -> None:
    """追加一条合法 proactive compaction requested fact。

    :param transaction_runner: transaction runner。
    :param seeded: accepted Run 摘要。
    :param event_id: 事件 id。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        EventLogStore().append_event(
            transaction,
            EventLogAppendRequest(
                event_id=event_id,
                event_class=EventClass.CANONICAL_FACT,
                session_id=seeded.session_id,
                run_id=seeded.run_id,
                attempt_id=None,
                execution_id=None,
                event_type=CONTEXT_COMPACTION_REQUESTED,
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason=None,
                payload_json=build_context_compaction_requested_payload(
                    operation_id=event_id,
                    max_compaction_attempts_per_operation=5,
                    trigger_source=ContextCompactionTriggerSource.PROACTIVE,
                    budget_reason=ContextBudgetDecision.COMPACT_SOFT_THRESHOLD.value,
                    budget_snapshot_ref=_CALL_CONTEXT_DIGEST,
                    input_snapshot_cursor=1,
                    estimator_digest=_CALL_CONTEXT_DIGEST,
                    policy_ref="test-soft-compact-policy",
                    provider_request_id=None,
                    provider_error_ref=None,
                    attempt_id=None,
                    execution_id=None,
                    client_correlation_id=None,
                    frozen_material_list_digest=_CALL_CONTEXT_DIGEST,
                    frozen_material_refs=(f"event-input-{seeded.run_id}",),
                ),
                payload_ref=None,
                payload_digest=None,
            ),
        )

    transaction_runner.run_write(_operation)


def _append_duplicate_proactive_failed_terminals(
    transaction_runner: HostTransactionRunner,
    *,
    seeded: _AcceptedSeededRun,
    operation_id: str,
) -> None:
    """为同一 proactive operation 注入两个 canonical failed terminal。

    :param transaction_runner: Host transaction runner。
    :param seeded: accepted Run 摘要。
    :param operation_id: 已提交 proactive request id。
    :returns: ``None``。
    :raises Exception: EventLog append 失败时透传。
    """

    def _operation(transaction: HostTransaction) -> None:
        """在单笔事务中追加两个损坏 terminal facts。

        :param transaction: 当前 Host write transaction。
        :returns: ``None``。
        :raises Exception: EventLog append 失败时透传。
        """

        for ordinal in (1, 2):
            EventLogStore().append_event(
                transaction,
                EventLogAppendRequest(
                    event_id=f"event-invalid-multiple-failed-{ordinal}",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    attempt_id=None,
                    execution_id=None,
                    event_type=CONTEXT_COMPACTION_FAILED,
                    occurred_at=_NOW,
                    actor="tester",
                    source="pytest",
                    client_request_id=None,
                    idempotency_key=None,
                    policy_decision=None,
                    reason=None,
                    payload_json=build_context_compaction_failed_payload(
                        operation_id=operation_id,
                        failure_reason=f"invalid_multiple_{ordinal}",
                        policy_decision="fail_closed",
                        retryable=False,
                        attempt_count=0,
                        retry_repair_budget_exhausted=False,
                        diagnostic_refs=(f"diagnostic:{ordinal}",),
                        budget_after_attempted_compact=None,
                    ),
                    payload_ref=None,
                    payload_digest=None,
                ),
            )

    transaction_runner.run_write(_operation)


def _append_corrupted_compaction_requested(
    transaction_runner: HostTransactionRunner,
    *,
    seeded: _AcceptedSeededRun,
    event_id: str,
) -> None:
    """追加一条损坏的 compaction requested fact。

    :param transaction_runner: transaction runner。
    :param seeded: accepted Run 摘要。
    :param event_id: 事件 id。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        EventLogStore().append_event(
            transaction,
            EventLogAppendRequest(
                event_id=event_id,
                event_class=EventClass.CANONICAL_FACT,
                session_id=seeded.session_id,
                run_id=seeded.run_id,
                attempt_id=None,
                execution_id=None,
                event_type=CONTEXT_COMPACTION_REQUESTED,
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason=None,
                payload_json={"trigger_source": 7},
                payload_ref=None,
                payload_digest=None,
            ),
        )

    transaction_runner.run_write(_operation)


def _ensure_session_id(transaction_runner: HostTransactionRunner) -> str:
    """确保测试 Session 存在。

    :param transaction_runner: transaction runner。
    :returns: session id。
    """

    return ensure_session(
        transaction_runner,
        EnsureSessionRequest(scope="workspace", slot_key="slot", metadata=()),
    ).snapshot.session_id


def _append_user_input(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    run_id: str,
    event_id: str,
    display_text: str = "dispatch prompt",
    client_request_id: str = "client-dispatch",
    idempotency_key: str = "idem-input",
    effective_execution_config: JsonValue | None = None,
    effective_tool_set: JsonValue | None = None,
) -> int:
    """追加 USER_INPUT_ACCEPTED。

    :param transaction_runner: transaction runner。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_id: event id。
    :param display_text: 用户输入展示文本。
    :param client_request_id: EventLog client request id。
    :param idempotency_key: EventLog idempotency key。
    :param effective_execution_config: 可选的 durable frozen execution config。
    :param effective_tool_set: 可选的完整 durable effective tool facts。
    :returns: 追加后的 EventLog sequence。
    """

    def _operation(transaction: HostTransaction) -> int:
        frozen_execution = (
            effective_execution_config
            if effective_execution_config is not None
            else effective_execution_config_json(
                runner_spec=_runner_spec(),
                runner_options=RunnerCallOptions(
                    temperature=None,
                    max_tokens=None,
                    top_p=None,
                    stream=False,
                ),
                agent_policy=_agent_policy(False),
                runner_spec_source="test",
                runner_options_source="test",
                agent_policy_source="test",
            )
        )
        payload: dict[str, JsonValue] = {
            "display_text": display_text,
            "operation_kind": "unit_test",
            "execution_target": "target-dispatch",
            "effective_tool_set": (
                effective_tool_set
                if effective_tool_set is not None
                else effective_tool_facts_json(
                    None,
                    tooling_options=None,
                )
            ),
            "effective_execution_config": frozen_execution,
        }
        event = EventLogStore().append_event(
            transaction,
            EventLogAppendRequest(
                event_id=event_id,
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id=run_id,
                attempt_id=None,
                execution_id=None,
                event_type="USER_INPUT_ACCEPTED",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id=client_request_id,
                idempotency_key=idempotency_key,
                policy_decision=None,
                reason=None,
                payload_json=payload,
                payload_ref=None,
                payload_digest=None,
            ),
        )
        return event.row.event_sequence

    return transaction_runner.run_write(_operation)


def _append_run_success(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    run_id: str,
    event_id: str,
    final_answer: str,
) -> int:
    """追加测试用 RUN_SUCCEEDED canonical fact。

    :param transaction_runner: transaction runner。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_id: event id。
    :param final_answer: final answer 文本。
    :returns: 追加后的 EventLog sequence。
    """

    def _operation(transaction: HostTransaction) -> int:
        """追加 RUN_SUCCEEDED event。

        :param transaction: Host transaction。
        :returns: EventLog sequence。
        """

        event = EventLogStore().append_event(
            transaction,
            EventLogAppendRequest(
                event_id=event_id,
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id=run_id,
                attempt_id=None,
                execution_id=None,
                event_type="RUN_SUCCEEDED",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason=None,
                payload_json={"final_answer": final_answer},
                payload_ref=None,
                payload_digest=None,
            ),
        )
        return event.row.event_sequence

    return transaction_runner.run_write(_operation)


def _append_accepted_tool_evidence(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    run_id: str,
    event_prefix: str,
    query_text: str,
    raw_result_text: str,
) -> None:
    """追加测试用 TOOL_CALL_REQUESTED 与 TOOL_RESULT_ACCEPTED facts。

    :param transaction_runner: transaction runner。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_prefix: event id 前缀。
    :param query_text: 可读查询文本。
    :param raw_result_text: raw outcome 文本。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        """追加 accepted evidence 相关 facts。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        tool_call_event_id = f"{event_prefix}-tool-call"
        tool_result_event_id = f"{event_prefix}-tool-result"
        tool_call_id = f"{event_prefix}-tool-call-id"
        arguments_json: dict[str, JsonValue] = {"arguments": {"ticker": "MSFT", "topic": "risk"}}
        arguments_digest = sha256_digest_json(arguments_json)
        semantic_query_digest = sha256_digest_json({"semantic_query_text": query_text})
        EventLogStore().append_event(
            transaction,
            EventLogAppendRequest(
                event_id=tool_call_event_id,
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id=run_id,
                attempt_id=None,
                execution_id=None,
                event_type="TOOL_CALL_REQUESTED",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason=None,
                payload_json={
                    "tool_call_id": tool_call_id,
                    "tool_name": "fins.search",
                    "normalized_arguments_digest": arguments_digest,
                    "arguments_payload_digest": arguments_digest,
                    "arguments_storage_kind": TOOL_CALL_ARGUMENTS_STORAGE_INLINE_JSON,
                    "arguments_inline_json": arguments_json,
                    "arguments_payload_ref": None,
                    "arguments_json_size_bytes": len(canonical_json_dumps(arguments_json).encode("utf-8")),
                    "semantic_input_digest": semantic_query_digest,
                    "semantic_query_storage_kind": (TOOL_CALL_SEMANTIC_QUERY_STORAGE_INLINE_TEXT),
                    "semantic_query_text": query_text,
                    "semantic_query_payload_ref": None,
                    "semantic_query_digest": semantic_query_digest,
                },
                payload_ref=None,
                payload_digest=None,
            ),
        )
        evidence_id = f"evidence:{tool_result_event_id}"
        envelope = AcceptedEvidenceEnvelope(
            evidence_id=evidence_id,
            producer_event_ref=tool_result_event_id,
            tool_name="fins.search",
            tool_call_id=tool_call_id,
            tool_query=AcceptedEvidenceToolQuery(
                tool_call_requested_event_ref=tool_call_event_id,
                normalized_arguments_digest=arguments_digest,
                semantic_input_digest=semantic_query_digest,
            ),
            result_ref=AcceptedEvidenceResultRef(
                payload_ref=None,
                payload_digest=None,
                outcome_digest=sha256_digest_json({"raw_result_text": raw_result_text}),
                truncation_applied=False,
            ),
            source_refs=(
                OpaqueEvidenceRef(
                    ref_kind="tool_call_event",
                    ref_id=tool_call_event_id,
                    digest=None,
                ),
            ),
            locator_refs=(OpaqueEvidenceRef(ref_kind="filing", ref_id="msft-10k", digest=None),),
        )
        EventLogStore().append_event(
            transaction,
            EventLogAppendRequest(
                event_id=tool_result_event_id,
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id=run_id,
                attempt_id=None,
                execution_id=None,
                event_type="TOOL_RESULT_ACCEPTED",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason=None,
                payload_json={
                    "accepted_evidence_envelope": (accepted_evidence_envelope_to_json_value(envelope)),
                    "raw_tool_outcome": {
                        "kind": "completed",
                        "result": {"text": raw_result_text},
                    },
                },
                payload_ref=None,
                payload_digest=None,
            ),
        )

    transaction_runner.run_write(_operation)


def _append_previous_compacted_event(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    run_id: str,
    event_id: str,
) -> None:
    """追加测试用 latest accepted ``CONTEXT_COMPACTED`` fact。

    :param transaction_runner: transaction runner。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_id: compacted event id。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        operation_id = f"operation-{event_id}"
        compactor_agent_request = AgentRunRequest(
            run_id=f"compactor-run:{operation_id}:1",
            session_id=f"context-compactor:{session_id}",
            attempt_id=None,
            execution_id=None,
            messages=(
                SystemMessage(
                    role=AgentMessageRole.SYSTEM,
                    content="system",
                ),
                UserMessage(
                    role=AgentMessageRole.USER,
                    content="previous compact fixture",
                ),
            ),
            disable_tools=True,
            runner_spec=_runner_spec(),
            runner_options=RunnerCallOptions(
                temperature=None,
                max_tokens=None,
                top_p=None,
                stream=False,
            ),
            agent_policy=_agent_policy(False),
            tool_schemas=(),
            tool_executor=NoToolExecutor(),
            cancellation_token=_HostCancellationToken(),
        )
        EventLogStore().append_event(
            transaction,
            EventLogAppendRequest(
                event_id=operation_id,
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id=run_id,
                attempt_id=None,
                execution_id=None,
                event_type=CONTEXT_COMPACTION_REQUESTED,
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason=None,
                payload_json=build_context_compaction_requested_payload(
                    operation_id=operation_id,
                    max_compaction_attempts_per_operation=1,
                    trigger_source=ContextCompactionTriggerSource.PROACTIVE,
                    budget_reason=(ContextBudgetDecision.COMPACT_SOFT_THRESHOLD.value),
                    budget_snapshot_ref=_CALL_CONTEXT_DIGEST,
                    input_snapshot_cursor=1,
                    estimator_digest=_CALL_CONTEXT_DIGEST,
                    policy_ref="test-soft-compact-policy",
                    provider_request_id=None,
                    provider_error_ref=None,
                    attempt_id=None,
                    execution_id=None,
                    client_correlation_id=None,
                    frozen_material_list_digest=_CALL_CONTEXT_DIGEST,
                    frozen_material_refs=(),
                ),
                payload_ref=None,
                payload_digest=None,
            ),
        )
        EventLogStore().append_event(
            transaction,
            EventLogAppendRequest(
                event_id=event_id,
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id=run_id,
                attempt_id=None,
                execution_id=None,
                event_type=CONTEXT_COMPACTED,
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason=None,
                payload_json=build_context_compacted_payload(
                    operation_id=operation_id,
                    accepted_attempt_number=1,
                    compact_artifact_ref="artifact:previous-compact",
                    compact_artifact_digest=_CALL_CONTEXT_DIGEST,
                    accepted_truth=accepted_truth_for_candidate(
                        _previous_compacted_candidate(),
                        current_input_ref="current:previous-compact",
                        source_refs_by_label={
                            "T1": ("source-boundary:previous",),
                            "E1": ("evidence:previous",),
                            "A1": ("answer:previous",),
                        },
                    ),
                    budget_after_compact=16,
                    prompt_local_label_mapping_refs=("label-map:previous",),
                    accepted_evidence_mapping_refs=("evidence:previous",),
                    projection_signal="project_memory",
                    successful_response_identity=(
                        _successful_response_identity_for_agent_request(compactor_agent_request)
                    ),
                    accepted_proposal_manifest_reference=(
                        _proposal_manifest_reference(
                            operation_id=operation_id,
                            attempt_number=1,
                            compactor_engine_run_id=(compactor_agent_request.run_id),
                        )
                    ),
                ),
                payload_ref=None,
                payload_digest=None,
            ),
        )

    transaction_runner.run_write(_operation)


def _previous_compacted_candidate() -> CompactCandidateV2:
    """构造含全 section 的 latest accepted compact candidate。

    :returns: CompactCandidateV2。
    """

    return CompactCandidateV2(
        schema=COMPACT_OUTPUT_SCHEMA_V2,
        session_summary=CompactSessionSummaryV2(
            text="previous session summary must drop whole",
            source_labels=("T1",),
        ),
        evidence_facts=(
            CompactEvidenceFactV2(
                claim="previous evidence fact must stay exact",
                support_labels=("E1",),
            ),
        ),
        answer_anchors=(
            CompactAnswerAnchorV2(
                title="previous answer anchor must drop whole",
                detail="previous answer item",
                source_labels=("A1",),
            ),
        ),
        forward_intents=(
            CompactForwardIntentV2(
                intent_type="next_step_note",
                text="previous forward intent must drop whole",
                status=CompactForwardIntentStatusV2.OPEN,
                source_labels=("T1",),
            ),
        ),
        reference_continuity=(
            CompactReferenceContinuityV2(
                text="previous reference must drop whole",
                reason="local_reference",
                source_labels=("T1",),
            ),
        ),
        diagnostics=(),
        explicitly_dropped_sources=(),
    )


def _append_corrupted_tool_result_material(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    run_id: str,
    event_id: str,
) -> None:
    """追加损坏的 accepted tool-result material fact。

    :param transaction_runner: transaction runner。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_id: event id。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        EventLogStore().append_event(
            transaction,
            EventLogAppendRequest(
                event_id=event_id,
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id=run_id,
                attempt_id=None,
                execution_id=None,
                event_type="TOOL_RESULT_ACCEPTED",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason=None,
                payload_json={"accepted_evidence_envelope": "corrupted-envelope"},
                payload_ref=None,
                payload_digest=None,
            ),
        )

    transaction_runner.run_write(_operation)


def _pending_dispatch(seeded: _SeededRun) -> PendingDispatchRecord:
    """构造 pending dispatch wakeup 摘要。

    :param seeded: seeded run。
    :returns: pending dispatch record。
    """

    return PendingDispatchRecord(
        dispatch_record_id=seeded.dispatch_record_id,
        run_id=seeded.run_id,
        attempt_id=seeded.attempt_id,
        execution_id=seeded.execution_id,
        execution_target="target-dispatch",
        worker_kind=WorkerKind.LOCAL,
    )


def _seed_current_run_rows(tmp_path: Path) -> tuple[RunRow, AttemptRow, DispatchRecordRow]:
    """在临时 store 中创建 current Run 并返回 durable rows。

    :param tmp_path: pytest 临时目录。
    :returns: Run、Attempt 与 DispatchRecord rows。
    """

    result: tuple[RunRow, AttemptRow, DispatchRecordRow] | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        result = _read_rows(store.transaction_runner, seeded)
    assert result is not None
    return result


def _read_rows(
    transaction_runner: HostTransactionRunner, seeded: _SeededRun
) -> tuple[RunRow, AttemptRow, DispatchRecordRow]:
    """读取 Run、Attempt 与 dispatch row。

    :param transaction_runner: transaction runner。
    :param seeded: seeded run。
    :returns: 三个 durable row。
    """

    def _operation(
        transaction: HostTransaction,
    ) -> tuple[RunRow, AttemptRow, DispatchRecordRow]:
        run = read_run_by_id(transaction, seeded.run_id)
        attempt = read_attempt_by_id(transaction, seeded.attempt_id)
        dispatch_record = read_dispatch_record_by_attempt_id(transaction, seeded.attempt_id)
        assert run is not None
        assert attempt is not None
        assert dispatch_record is not None
        return run, attempt, dispatch_record

    return transaction_runner.run_read(_operation)


def _reactive_compaction_candidate(
    *,
    run: RunRow,
    attempt: AttemptRow,
    dispatch_record: DispatchRecordRow,
) -> host_engine_ingest.EngineEventCandidate:
    """构造测试用 reactive compaction EngineEvent candidate。

    :param run: Run row。
    :param attempt: Attempt row。
    :param dispatch_record: DispatchRecord row。
    :returns: EngineEventCandidate。
    """

    return host_engine_ingest.EngineEventCandidate(
        envelope=LocalEngineEnvelope(
            session_id=run.session_id,
            run_id=run.run_id,
            attempt_id=attempt.attempt_id,
            execution_id=attempt.execution_id,
            dispatch_record_id=dispatch_record.dispatch_record_id,
            worker_kind=WorkerKind.LOCAL,
            execution_target=dispatch_record.execution_target,
            local_worker_id="local-worker-test",
            cancellation_token=_HostCancellationToken(),
        ),
        worker_event_index=1,
        engine_event=EngineEvent(
            occurred_at=_NOW,
            session_id=run.session_id,
            run_id=run.run_id,
            type=EngineEventType.CONTEXT_COMPACTION_REQUESTED,
            data=ContextCompactionRequestedData(
                iteration_id="iter-reactive",
                budget_state=None,
                reason="provider_overflow",
                provider_request_id="req-reactive",
            ),
            metadata=None,
        ),
        observed_at=_NOW,
    )


def _read_run(transaction_runner: HostTransactionRunner, run_id: str) -> RunRow:
    """读取指定 Run row。

    :param transaction_runner: transaction runner。
    :param run_id: Run id。
    :returns: Run row。
    :raises AssertionError: Run 缺失时抛出。
    """

    def _operation(transaction: HostTransaction) -> RunRow:
        row = read_run_by_id(transaction, run_id)
        assert row is not None
        return row

    return transaction_runner.run_read(_operation)


def _pre_dispatch_material_view_for_run(
    transaction_runner: HostTransactionRunner,
    *,
    run_id: str,
    current_display_text: str,
) -> tuple[RunRow, PreDispatchCompactMaterialView]:
    """读取 Run 并构造 pre-dispatch compact material view。

    :param transaction_runner: transaction runner。
    :param run_id: Run id。
    :param current_display_text: 当前输入展示文本。
    :returns: Run row 与同源 pre-dispatch material view。
    """

    def _operation(
        transaction: HostTransaction,
    ) -> tuple[RunRow, PreDispatchCompactMaterialView]:
        run = read_run_by_id(transaction, run_id)
        assert run is not None
        material_view = build_pre_dispatch_compact_material_view(
            transaction,
            EventLogStore(),
            run=run,
            current_display_text=current_display_text,
        )
        return run, material_view

    return transaction_runner.run_read(_operation)


def _read_dispatch_record_by_attempt_id(
    transaction_runner: HostTransactionRunner, attempt_id: str
) -> DispatchRecordRow:
    """读取指定 Attempt 对应的 dispatch record。

    :param transaction_runner: transaction runner。
    :param attempt_id: Attempt id。
    :returns: Dispatch record row。
    :raises AssertionError: dispatch record 缺失时抛出。
    """

    def _operation(transaction: HostTransaction) -> DispatchRecordRow:
        row = read_dispatch_record_by_attempt_id(transaction, attempt_id)
        assert row is not None
        return row

    return transaction_runner.run_read(_operation)


def _start_governed_for_test(
    transaction_runner: HostTransactionRunner,
    scheduler: HostDispatchScheduler,
    run: RunRow,
) -> PendingDispatchRecord:
    """在测试事务内执行标准 governed start。

    :param transaction_runner: transaction runner。
    :param scheduler: 待测试的 scheduler。
    :param run: 待启动 Run row。
    :returns: 新创建的 pending dispatch 摘要。
    :raises AssertionError: governed start CAS 未创建 dispatch 时抛出。
    """

    scheduler._catch_up_memory_projection_before_candidate(run.session_id)

    def _operation(transaction: HostTransaction) -> PendingDispatchRecord:
        outcome = scheduler._prepare_and_commit_start_in_transaction(
            transaction,
            run,
            stage=ContextSizingStage.ORDINARY,
        )
        assert outcome.pending_dispatch is not None
        assert outcome.terminal_notice is None
        return outcome.pending_dispatch

    pending = transaction_runner.run_write(_operation)
    return pending


def _read_proactive_projection(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    run_id: str,
) -> ProactiveCompactionProjection:
    """读取目标 Run 的 proactive typed projection。

    :param transaction_runner: Host transaction runner。
    :param session_id: 目标 Session id。
    :param run_id: 目标 Run id。
    :returns: proactive typed projection。
    :raises Exception: durable 读取异常透传。
    """

    def _operation(transaction: HostTransaction) -> ProactiveCompactionProjection:
        """在单个 read transaction 中投影状态。

        :param transaction: Host read transaction。
        :returns: proactive typed projection。
        :raises Exception: owner reader 异常透传。
        """

        return read_proactive_compaction_projection(
            transaction,
            EventLogStore(),
            session_id=session_id,
            run_id=run_id,
        )

    return transaction_runner.run_read(_operation)


def _run_status(transaction_runner: HostTransactionRunner, run_id: str) -> RunStatus:
    """读取 Run 状态。

    :param transaction_runner: transaction runner。
    :param run_id: Run id。
    :returns: Run 状态。
    :raises AssertionError: Run 缺失时抛出。
    """

    def _operation(transaction: HostTransaction) -> RunStatus:
        row = read_run_by_id(transaction, run_id)
        assert row is not None
        return row.status

    return transaction_runner.run_read(_operation)


def _run_input_sequence(transaction_runner: HostTransactionRunner, run_id: str) -> int:
    """读取 Run input event sequence。

    :param transaction_runner: transaction runner。
    :param run_id: Run id。
    :returns: Run input event sequence。
    :raises AssertionError: Run 缺失时抛出。
    """

    def _operation(transaction: HostTransaction) -> int:
        row = read_run_by_id(transaction, run_id)
        assert row is not None
        return row.input_event_sequence

    return transaction_runner.run_read(_operation)


def _attempt_count_for_run(transaction_runner: HostTransactionRunner, run_id: str) -> int:
    """统计指定 Run 的 Attempt row 数。

    :param transaction_runner: transaction runner。
    :param run_id: Run id。
    :returns: Attempt row 数。
    """

    def _operation(transaction: HostTransaction) -> int:
        row = transaction.fetchone(
            "SELECT COUNT(*) AS count FROM host_attempts WHERE run_id = ?",
            (run_id,),
        )
        assert row is not None
        value = row.get("count")
        assert isinstance(value, int)
        return value

    return transaction_runner.run_read(_operation)


def _table_count(
    transaction_runner: HostTransactionRunner,
    table_name: str,
) -> int:
    """读取测试白名单表的总行数。

    :param transaction_runner: transaction runner。
    :param table_name: 由调用测试传入的schema常量。
    :returns: table row count。
    :raises AssertionError: table不在白名单或count类型非法时抛出。
    """

    assert table_name in frozenset(
        (
            TABLE_HOST_ATTEMPT_DISPATCH_RECORDS,
            TABLE_PAYLOAD_DESCRIPTORS,
        )
    )

    def _operation(transaction: HostTransaction) -> int:
        """执行固定白名单table count。

        :param transaction: Host read transaction。
        :returns: row count。
        :raises AssertionError: SQLite未返回int count时抛出。
        """

        row = transaction.fetchone(f"SELECT COUNT(*) AS count FROM {table_name}")
        assert row is not None
        count = row.get("count")
        assert isinstance(count, int)
        return count

    return transaction_runner.run_read(_operation)


def _event_types_for_run(transaction_runner: HostTransactionRunner, run_id: str) -> tuple[str, ...]:
    """按 sequence 读取指定 Run 的 EventLog 类型。

    :param transaction_runner: transaction runner。
    :param run_id: Run id。
    :returns: event type 元组。
    """

    def _operation(transaction: HostTransaction) -> tuple[str, ...]:
        rows = EventLogStore().read_events_after(
            transaction,
            0,
            limit=_EVENT_LOG_TEST_READ_LIMIT,
        )
        return tuple(row.event_type for row in rows if row.run_id == run_id)

    return transaction_runner.run_read(_operation)


def _has_context_usage_activity(
    transaction_runner: HostTransactionRunner,
    run_id: str,
) -> bool:
    """检查指定Run是否投影出context usage activity。

    :param transaction_runner: transaction runner。
    :param run_id: Run id。
    :returns: 任一durable row投影为context usage时返回``True``。
    :raises Exception: durable读取或strict public投影失败时透传。
    """

    def _operation(transaction: HostTransaction) -> bool:
        """在同一read transaction检查public activity。

        :param transaction: Host read transaction。
        :returns: 是否存在context usage activity。
        :raises Exception: strict public投影失败时透传。
        """

        rows = EventLogStore().read_events_after(
            transaction,
            0,
            limit=_EVENT_LOG_TEST_READ_LIMIT,
        )
        for row in rows:
            if row.run_id != run_id:
                continue
            activity = _host_event_from_row(transaction, row).activity
            if activity is not None and activity.kind is HostActivityKind.CONTEXT_USAGE:
                return True
        return False

    return transaction_runner.run_read(_operation)


def _event_log_cursor(transaction_runner: HostTransactionRunner) -> int:
    """读取测试库中当前 EventLog 最大游标。

    :param transaction_runner: transaction runner。
    :returns: 当前最大 ``event_sequence``；没有事件时返回 ``0``。
    """

    def _operation(transaction: HostTransaction) -> int:
        rows = EventLogStore().read_events_after(
            transaction,
            0,
            limit=_EVENT_LOG_TEST_READ_LIMIT,
        )
        if not rows:
            return 0
        return max(row.event_sequence for row in rows)

    return transaction_runner.run_read(_operation)


def _event_count(transaction_runner: HostTransactionRunner, event_type: str) -> int:
    """统计指定 event type 数量。

    :param transaction_runner: transaction runner。
    :param event_type: event type。
    :returns: 事件数量。
    """

    def _operation(transaction: HostTransaction) -> int:
        return sum(
            1
            for row in EventLogStore().read_events_after(
                transaction,
                0,
                limit=_EVENT_LOG_TEST_READ_LIMIT,
            )
            if row.event_type == event_type
        )

    return transaction_runner.run_read(_operation)


def _read_memory_checkpoint_sequence(transaction_runner: HostTransactionRunner) -> int:
    """读取 conversation memory projection checkpoint sequence。

    :param transaction_runner: transaction runner。
    :returns: memory projection checkpoint sequence。
    :raises AssertionError: checkpoint 尚未存在时抛出。
    """

    def _operation(transaction: HostTransaction) -> int:
        """读取 checkpoint row。

        :param transaction: Host transaction。
        :returns: checkpoint sequence。
        :raises AssertionError: checkpoint 尚未存在时抛出。
        """

        checkpoint = read_projection_checkpoint(
            transaction,
            CONVERSATION_MEMORY_CONSUMER_ID,
        )
        assert checkpoint is not None
        return checkpoint.checkpoint_event_sequence

    return transaction_runner.run_read(_operation)


def _compact_artifact_files(root: Path) -> tuple[Path, ...]:
    """返回 compact artifact 根目录下的文件。

    :param root: compact artifact 根目录。
    :returns: 已存在文件路径，按路径排序。
    """

    if not root.exists():
        return ()
    return tuple(sorted(path for path in root.rglob("*") if path.is_file()))


def _payload_descriptor_count(
    transaction_runner: HostTransactionRunner,
) -> int:
    """统计 durable payload descriptor rows。

    :param transaction_runner: Host transaction runner。
    :returns: descriptor row 数量。
    :raises AssertionError: SQLite 未返回整数 count 时抛出。
    """

    def _operation(transaction: HostTransaction) -> int:
        """在当前 read transaction 内统计 descriptor rows。

        :param transaction: 当前 Host read transaction。
        :returns: descriptor row 数量。
        :raises AssertionError: SQLite 未返回整数 count 时抛出。
        """

        row = transaction.fetchone(f"SELECT COUNT(*) AS total FROM {TABLE_PAYLOAD_DESCRIPTORS}")
        assert row is not None
        total = row.get("total")
        assert isinstance(total, int)
        return total

    return transaction_runner.run_read(_operation)


def _event_log_types_after_cursor(
    transaction_runner: HostTransactionRunner,
    after_cursor: int,
) -> tuple[str, ...]:
    """读取指定游标之后新增的 EventLog type。

    :param transaction_runner: transaction runner。
    :param after_cursor: 只读取该 EventLog cursor 之后的事件。
    :returns: 新增 EventLog type 序列。
    """

    def _operation(transaction: HostTransaction) -> tuple[str, ...]:
        rows = EventLogStore().read_events_after(
            transaction,
            after_cursor,
            limit=_EVENT_LOG_TEST_READ_LIMIT,
        )
        return tuple(row.event_type for row in rows)

    return transaction_runner.run_read(_operation)


def _scheduler_close_terminal_event_types() -> frozenset[str]:
    """读取 close 不得自行追加的当前 terminal EventLog type 集合。

    :returns: Attempt / Run 终态映射对应的 EventLog type 集合。
    """

    return frozenset(
        (
            *(_attempt_terminal_event_type(status) for status in _ATTEMPT_TERMINAL_STATUSES),
            *(_run_terminal_event_type(status) for status in _RUN_TERMINAL_STATUSES),
        )
    )


def _terminal_event_log_types_after_cursor(
    transaction_runner: HostTransactionRunner,
    after_cursor: int,
) -> tuple[str, ...]:
    """读取指定游标之后新增的 terminal EventLog type。

    :param transaction_runner: transaction runner。
    :param after_cursor: 只读取该 EventLog cursor 之后的事件。
    :returns: 新增 terminal EventLog type 序列。
    """

    terminal_event_types = _scheduler_close_terminal_event_types()
    return tuple(
        event_type
        for event_type in _event_log_types_after_cursor(transaction_runner, after_cursor)
        if event_type in terminal_event_types
    )


def _assert_scheduler_close_did_not_append_terminal_facts(
    transaction_runner: HostTransactionRunner,
    *,
    after_cursor: int,
) -> None:
    """断言 scheduler close 未追加 terminal canonical facts。

    :param transaction_runner: transaction runner。
    :param after_cursor: close 前记录的 EventLog cursor。
    :returns: ``None``。
    :raises AssertionError: close 后出现新增 terminal EventLog row 时抛出。
    """

    assert _terminal_event_log_types_after_cursor(transaction_runner, after_cursor) == ()


async def _wait_for_event_count(
    transaction_runner: HostTransactionRunner,
    event_type: str,
    *,
    expected_count: int,
) -> None:
    """等待指定 event type 达到期望数量。

    :param transaction_runner: transaction runner。
    :param event_type: event type。
    :param expected_count: 期望数量。
    :returns: ``None``。
    :raises AssertionError: 超时未达到数量时抛出。
    """

    for _index in range(200):
        if _event_count(transaction_runner, event_type) >= expected_count:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"event count did not converge: {event_type}")


def _latest_event_for_run(transaction_runner: HostTransactionRunner, run_id: str, event_type: str) -> EventLogRow:
    """按 Run 读取最近一条指定 EventLog row。

    :param transaction_runner: transaction runner。
    :param run_id: Run id。
    :param event_type: event type。
    :returns: EventLog row。
    """

    def _operation(transaction: HostTransaction) -> EventLogRow:
        rows = EventLogStore().read_events_after(
            transaction,
            0,
            limit=_EVENT_LOG_TEST_READ_LIMIT,
        )
        for row in reversed(rows):
            if row.run_id == run_id and row.event_type == event_type:
                return row
        raise AssertionError(f"missing event type {event_type}")

    return transaction_runner.run_read(_operation)


def _events_for_run_by_type(
    transaction_runner: HostTransactionRunner,
    run_id: str,
    event_type: str,
) -> tuple[EventLogRow, ...]:
    """按 Run 读取指定类型的全部 EventLog row。

    :param transaction_runner: transaction runner。
    :param run_id: Run id。
    :param event_type: event type。
    :returns: 匹配的 EventLog row 元组。
    """

    def _operation(transaction: HostTransaction) -> tuple[EventLogRow, ...]:
        rows = EventLogStore().read_events_after(
            transaction,
            0,
            limit=_EVENT_LOG_TEST_READ_LIMIT,
        )
        return tuple(row for row in rows if row.run_id == run_id and row.event_type == event_type)

    return transaction_runner.run_read(_operation)


def _event_payload(row: EventLogRow) -> Mapping[str, JsonValue]:
    """解析 EventLog row payload。

    :param row: EventLog row。
    :returns: payload mapping。
    """

    value = cast(JsonValue, json.loads(row.payload_json))
    assert isinstance(value, Mapping)
    return cast(Mapping[str, JsonValue], value)


def _overwrite_event_payload(
    transaction_runner: HostTransactionRunner,
    *,
    event_id: str,
    payload: Mapping[str, JsonValue],
) -> None:
    """破坏注入测试中覆盖指定 inline EventLog payload。

    :param transaction_runner: Host transaction runner。
    :param event_id: 待覆盖 event id。
    :param payload: replacement JSON object。
    :returns: ``None``。
    :raises AssertionError: 指定 event 不存在时抛出。
    """

    def _operation(transaction: HostTransaction) -> None:
        """在单个 write transaction 中覆盖 payload。

        :param transaction: Host write transaction。
        :returns: ``None``。
        :raises AssertionError: update 未命中时抛出。
        """

        result = transaction.execute(
            f"UPDATE {TABLE_EVENT_LOG} SET payload_json = ? WHERE event_id = ?",
            (canonical_json_dumps(payload), event_id),
        )
        assert result.rowcount == 1

    transaction_runner.run_write(_operation)


def _delete_compaction_requested_events(
    transaction_runner: HostTransactionRunner,
    *,
    run_id: str,
) -> None:
    """删除目标 Run 唯一 request row，构造 orphan manifest corruption。

    :param transaction_runner: Host transaction runner。
    :param run_id: 目标 Run id。
    :returns: ``None``。
    :raises AssertionError: 删除未精确命中一条 request row 时抛出。
    """

    def _operation(transaction: HostTransaction) -> None:
        """在单个 write transaction 中删除 request row。

        :param transaction: Host write transaction。
        :returns: ``None``。
        :raises AssertionError: 删除未精确命中一条 row 时抛出。
        """

        result = transaction.execute(
            f"DELETE FROM {TABLE_EVENT_LOG} WHERE run_id = ? AND event_type = ?",
            (run_id, CONTEXT_COMPACTION_REQUESTED),
        )
        assert result.rowcount == 1

    transaction_runner.run_write(_operation)


def _append_proactive_rejection_after_terminal(
    transaction_runner: HostTransactionRunner,
    *,
    seeded: _AcceptedSeededRun,
    operation_id: str,
) -> None:
    """追加同 proactive operation terminal 之后的非法 rejection row。

    :param transaction_runner: Host transaction runner。
    :param seeded: 目标 accepted Run identity。
    :param operation_id: 已完成 proactive operation id。
    :returns: ``None``。
    :raises Exception: EventLog append 失败时透传。
    """

    def _operation(transaction: HostTransaction) -> None:
        """在单个 write transaction 中追加 rejection。

        :param transaction: Host write transaction。
        :returns: ``None``。
        :raises Exception: EventLog append 失败时透传。
        """

        EventLogStore().append_event(
            transaction,
            EventLogAppendRequest(
                event_id="event-rejection-after-proactive-terminal",
                event_class=EventClass.CANONICAL_FACT,
                session_id=seeded.session_id,
                run_id=seeded.run_id,
                attempt_id=None,
                execution_id=None,
                event_type=CONTEXT_COMPACTION_ATTEMPT_REJECTED,
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason=None,
                payload_json=build_context_compaction_attempt_rejected_payload(
                    operation_id=operation_id,
                    attempt_number=2,
                    failure_category="proposal_failed",
                    repairable=False,
                    runner_attempt_summary_refs=("runner-attempt:after-terminal",),
                    diagnostic_refs=("diagnostic:after-terminal",),
                    next_policy_decision="fail_operation",
                    budget_after_attempted_compact=None,
                    successful_response_identity=None,
                    proposal_manifest_reference=None,
                ),
                payload_ref=None,
                payload_digest=None,
            ),
        )

    transaction_runner.run_write(_operation)


def _resolve_and_assert_compactor_calls(
    transaction_runner: HostTransactionRunner,
    *,
    tmp_path: Path,
    run_id: str,
    prepared_inputs: tuple[CompactorProposalRunInput, ...],
    attempt_payloads: tuple[Mapping[str, JsonValue], ...],
    accepted_attempt_number: int | None,
) -> None:
    """通过 public Tool Trace contract 重构并核对全部 compactor calls。

    :param transaction_runner: 当前 Host durable transaction runner。
    :param tmp_path: 当前 pytest 临时目录。
    :param run_id: compaction 所属 Host Run id。
    :param prepared_inputs: recorder 实际消费的逐 attempt prepared inputs。
    :param attempt_payloads: 与 attempts 对齐的 rejected/accepted canonical payloads。
    :param accepted_attempt_number: accepted attempt 序号；全部失败时为 ``None``。
    :returns: ``None``。
    :raises AssertionError: manifest、projection、attempt 或 response identity
        任一无法同源重构时抛出。
    :raises HostDurableError: Tool Trace catch-up 或 formal resolver fail closed 时透传。
    """

    assert len(prepared_inputs) == len(attempt_payloads)
    catch_up_tool_trace_projection(
        transaction_runner,
        options=ToolTraceSinkOptions(cold_jsonl_path=tmp_path / "tool-trace" / "cold.jsonl"),
    )
    page = transaction_runner.run_read(
        lambda transaction: read_runner_call_reconstruction_signals_by_run(
            transaction,
            run_id,
            after_event_sequence=0,
            limit=100,
        )
    )
    signals = tuple(signal for signal in page.signals if signal.runner_call_kind == _COMPACTOR_RUNNER_CALL_KIND)
    assert len(signals) == len(prepared_inputs)
    resolved_calls = transaction_runner.run_read(
        lambda transaction: tuple(resolve_runner_call_projection_from_signal(transaction, signal) for signal in signals)
    )
    source_events = {
        row.event_id: row
        for row in _events_for_run_by_type(
            transaction_runner,
            run_id,
            "RUNNER_CALL_INPUT_ASSEMBLED",
        )
    }

    for attempt_number, (prepared_input, attempt_payload, resolved) in enumerate(
        zip(prepared_inputs, attempt_payloads, resolved_calls, strict=True),
        start=1,
    ):
        is_accepted = attempt_number == accepted_attempt_number
        attempt_field = _ACCEPTED_ATTEMPT_NUMBER_FIELD if is_accepted else _ATTEMPT_NUMBER_FIELD
        manifest_ref_field = _ACCEPTED_MANIFEST_REF_FIELD if is_accepted else _REJECTED_MANIFEST_REF_FIELD
        manifest_digest_field = _ACCEPTED_MANIFEST_DIGEST_FIELD if is_accepted else _REJECTED_MANIFEST_DIGEST_FIELD
        signal = resolved.signal
        source_event = source_events[signal.event_id]
        hot_payload = _event_payload(source_event)
        assert signal.runner_call_index == attempt_number - 1
        assert _required_json_int(attempt_payload[attempt_field]) == attempt_number
        assert source_event.payload_ref == signal.manifest_ref
        assert source_event.payload_digest == signal.manifest_digest
        assert _required_json_text(hot_payload["manifest_payload_ref"]) == signal.manifest_ref
        assert _required_json_text(hot_payload["manifest_digest"]) == signal.manifest_digest
        assert resolved.manifest.payload_ref == signal.manifest_ref
        assert resolved.manifest.payload_digest == signal.manifest_digest
        assert resolved.manifest.payload_ref == _required_json_text(attempt_payload[manifest_ref_field])
        assert resolved.manifest.payload_digest == _required_json_text(attempt_payload[manifest_digest_field])

        compactor_identity = _required_json_mapping(resolved.manifest.payload["compactor_identity"])
        assert _required_json_int(compactor_identity["compaction_attempt_number"]) == attempt_number
        assert (
            _required_json_text(compactor_identity["compactor_engine_run_id"]) == prepared_input.compactor_engine_run_id
        )
        assert _required_json_text(compactor_identity["compaction_operation_id"]) == _required_json_text(
            attempt_payload["operation_id"]
        )
        assert resolved.runner_input_projection.payload_ref == _required_json_text(
            compactor_identity["compactor_input_projection_ref"]
        )
        assert _required_json_text(hot_payload["runner_call_projection_artifact_ref"]) == (
            resolved.runner_input_projection.payload_ref
        )
        assert _required_json_text(hot_payload["runner_call_projection_artifact_digest"]) == (
            resolved.runner_input_projection.payload_digest
        )
        assert resolved.runner_input_projection.payload_digest == (prepared_input.compactor_input_projection_digest)
        assert resolved.runner_input_projection.payload == (prepared_input.compactor_input_projection)

        response_identity = _required_json_mapping(attempt_payload["successful_response_identity"])
        assert _required_json_text(response_identity["effective_provider"]) == (
            prepared_input.agent_request.runner_spec.provider
        )
        assert _required_json_text(response_identity["effective_model"]) == (
            prepared_input.agent_request.runner_spec.model
        )
        runner_request_identity = _required_json_mapping(response_identity["runner_request_identity"])
        assert _required_json_text(runner_request_identity["run_id"]) == (prepared_input.compactor_engine_run_id)


def _assert_accepted_payload_has_proposal_manifest(
    payload: Mapping[str, JsonValue],
) -> None:
    """断言 accepted compact payload 携带 proposal manifest 引用。

    :param payload: ``CONTEXT_COMPACTED`` payload。
    :returns: ``None``。
    :raises AssertionError: manifest ref 或 digest 缺失时抛出。
    """

    manifest_ref = payload["accepted_proposal_manifest_ref"]
    manifest_digest = payload["accepted_proposal_manifest_digest"]
    assert isinstance(manifest_ref, str)
    assert manifest_ref.startswith(_RUNNER_CALL_MANIFEST_REF_PREFIX)
    assert isinstance(manifest_digest, str)
    assert manifest_digest != ""


def _assert_rejected_payload_has_proposal_manifest(
    payload: Mapping[str, JsonValue],
) -> None:
    """断言 rejected compact attempt payload 携带 proposal manifest 引用。

    :param payload: ``CONTEXT_COMPACTION_ATTEMPT_REJECTED`` payload。
    :returns: ``None``。
    :raises AssertionError: manifest ref 或 digest 缺失时抛出。
    """

    manifest_ref = payload["proposal_manifest_ref"]
    manifest_digest = payload["proposal_manifest_digest"]
    assert isinstance(manifest_ref, str)
    assert manifest_ref.startswith(_RUNNER_CALL_MANIFEST_REF_PREFIX)
    assert isinstance(manifest_digest, str)
    assert manifest_digest != ""


async def _wait_for_run_status(
    transaction_runner: HostTransactionRunner,
    run_id: str,
    *,
    expected_run: RunStatus,
) -> RunRow:
    """等待 Run 到达指定状态。

    :param transaction_runner: transaction runner。
    :param run_id: Run id。
    :param expected_run: 期望 Run 状态。
    :returns: Run row。
    :raises AssertionError: 超时未达到目标状态时抛出。
    """

    for _index in range(200):
        row = transaction_runner.run_read(lambda transaction: read_run_by_id(transaction, run_id))
        assert row is not None
        if row.status == expected_run:
            return row
        await asyncio.sleep(0.01)
    row = transaction_runner.run_read(lambda transaction: read_run_by_id(transaction, run_id))
    assert row is not None
    raise AssertionError(f"run status did not converge: {row.status.value}")


async def _wait_for_log_message(caplog: pytest.LogCaptureFixture, expected_fragment: str) -> None:
    """等待 caplog 捕获包含指定片段的日志。

    :param caplog: pytest log capture fixture。
    :param expected_fragment: 期望日志片段。
    :returns: ``None``。
    :raises AssertionError: 超时未捕获日志时抛出。
    """

    for _index in range(200):
        if any(expected_fragment in record.message for record in caplog.records):
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"log message did not converge: {expected_fragment}")


async def _wait_for_promotion_task_started(
    scheduler: HostDispatchScheduler,
) -> None:
    """等待 scheduler promotion task 进入运行态。

    :param scheduler: dispatch scheduler。
    :returns: ``None``。
    :raises AssertionError: 超时未启动时抛出。
    """

    for _index in range(200):
        task = scheduler._promotion_drain_task
        if task is not None and not task.done():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("promotion task did not start")


async def _run_scheduler_drain_once(scheduler: HostDispatchScheduler) -> None:
    """以 ``Task[None]`` 形态运行一次 scheduler drain。

    :param scheduler: dispatch scheduler。
    :returns: ``None``。
    :raises RuntimeError: scheduler 已关闭时透传。
    """

    await scheduler.drain_once()


async def _dispatch_accepted_final_run(
    *,
    scheduler: HostDispatchScheduler,
    store: HostDurableStore,
    factory: _FinalAnswerWorkerFactory,
    run_id: str,
    display_text: str,
    expected_request_count: int,
) -> _AcceptedSeededRun:
    """创建 accepted Run，经 scheduler gate dispatch，并等待 final_answer 收口。

    :param scheduler: Host dispatch scheduler。
    :param store: durable store。
    :param factory: 记录 Engine request 的 final-answer worker factory。
    :param run_id: 新 Run id。
    :param display_text: 当前用户输入文本。
    :param expected_request_count: 期望累计 accept 次数。
    :returns: accepted Run 摘要。
    :raises AssertionError: dispatch 或状态收口未在测试时间内完成时抛出。
    """

    seeded = _seed_accepted_run(
        store,
        run_id=run_id,
        display_text=display_text,
    )
    await scheduler.run_queue_promotion(seeded.session_id)
    await _wait_for_final_request_count(factory, expected_request_count)
    await _wait_for_run_status(
        store.transaction_runner,
        seeded.run_id,
        expected_run=RunStatus.SUCCEEDED,
    )
    return seeded


async def _wait_for_final_request_count(factory: _FinalAnswerWorkerFactory, expected_count: int) -> None:
    """等待 final-answer worker factory 接受指定次数。

    :param factory: final-answer worker factory。
    :param expected_count: 期望累计 accept 次数。
    :returns: ``None``。
    :raises AssertionError: 超时未达到次数时抛出。
    """

    for _index in range(200):
        if len(factory.accepted_requests) >= expected_count:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"worker request count did not converge: {len(factory.accepted_requests)}")


async def _wait_for_compactor_request_count(
    compactor: _RequestCapturingCompactor,
    expected_count: int,
) -> None:
    """等待测试 compactor 捕获指定次数的 request。

    :param compactor: request capturing compactor。
    :param expected_count: 期望 request 数。
    :returns: ``None``。
    :raises AssertionError: 超时未达到次数时抛出。
    """

    for _index in range(200):
        if len(compactor.prepared_requests) >= expected_count:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"compactor request count did not converge: {len(compactor.prepared_requests)}")


def _content_index(contents: tuple[str, ...], expected_fragment: str) -> int:
    """返回包含指定片段的 message index。

    :param contents: Engine request message 文本。
    :param expected_fragment: 需要查找的文本片段。
    :returns: 第一个匹配 index。
    :raises AssertionError: 找不到片段时抛出。
    """

    for index, content in enumerate(contents):
        if expected_fragment in content:
            return index
    raise AssertionError(f"message fragment not found: {expected_fragment}")


async def _wait_for_accepted_snapshot_count(factory: _ReactiveRecoveryWorkerFactory, expected_count: int) -> None:
    """等待 reactive worker factory 接受指定次数。

    :param factory: reactive worker factory。
    :param expected_count: 期望 accept 次数。
    :returns: ``None``。
    :raises AssertionError: 超时未达到次数时抛出。
    """

    for _index in range(200):
        if len(factory.accepted_snapshots) >= expected_count:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"accepted snapshot count did not converge: {len(factory.accepted_snapshots)}")


async def _wait_for_statuses(
    transaction_runner: HostTransactionRunner,
    seeded: _SeededRun,
    *,
    expected_run: RunStatus,
    expected_attempt: AttemptStatus,
) -> tuple[RunRow, AttemptRow, DispatchRecordRow]:
    """等待异步 worker consume task 写入目标 Run / Attempt 状态。

    :param transaction_runner: transaction runner。
    :param seeded: seeded run。
    :param expected_run: 期望 Run 状态。
    :param expected_attempt: 期望 Attempt 状态。
    :returns: 目标状态下的 durable rows。
    :raises AssertionError: 超时未达到目标状态时抛出。
    """

    for _index in range(100):
        rows = _read_rows(transaction_runner, seeded)
        run, attempt, _dispatch_record = rows
        if run.status == expected_run and attempt.status == expected_attempt:
            return rows
        await asyncio.sleep(0.01)
    run, attempt, _dispatch_record = _read_rows(transaction_runner, seeded)
    raise AssertionError(f"status did not converge: run={run.status.value} attempt={attempt.status.value}")


async def _wait_for_active_tasks_to_finish(
    scheduler: HostDispatchScheduler,
) -> None:
    """等待 scheduler active consume tasks 全部结束。

    :param scheduler: 目标 scheduler。
    :returns: ``None``。
    :raises AssertionError: 超时仍有 active task 时抛出。
    """

    for _index in range(100):
        if not scheduler._active_tasks:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("active tasks did not finish")


def _read_event_by_type(transaction_runner: HostTransactionRunner, event_type: str) -> EventLogRow:
    """按事件类型读取单条事件。

    :param transaction_runner: transaction runner。
    :param event_type: 事件类型。
    :returns: event row。
    """

    def _operation(transaction: HostTransaction) -> EventLogRow:
        rows = EventLogStore().read_events_after(transaction, 0, limit=100)
        for row in rows:
            if row.event_type == event_type:
                return row
        raise AssertionError(f"missing event type {event_type}")

    return transaction_runner.run_read(_operation)


def _mark_dispatching_and_cancel(transaction_runner: HostTransactionRunner, seeded: _SeededRun) -> None:
    """把 dispatch 推进到 pre-accept dispatching 后 direct cancel。

    :param transaction_runner: transaction runner。
    :param seeded: seeded run。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id=seeded.attempt_id,
            owner_host_instance_id="host-test",
            lane_name=_LANE_NAME,
            waiting_for_lane_at="2026-05-15T01:02:03.000000Z",
        )
        mark_dispatching_after_lane_row(
            transaction,
            attempt_id=seeded.attempt_id,
            owner_host_instance_id="host-test",
            lane_name=_LANE_NAME,
            lane_claim_id="claim-before-cancel",
            lane_owner_id="owner-before-cancel",
            lane_acquired_at="2026-05-15T01:02:03.000000Z",
            dispatching_at="2026-05-15T01:02:03.000000Z",
        )
        cancel_predispatch_starting_in_transaction(
            transaction,
            EventLogStore(),
            CancelPredispatchStartingInput(
                run_id=seeded.run_id,
                cancel_request_event_id="event-cancel-requested",
                attempt_cancelled_event_id="event-attempt-cancelled",
                run_cancelled_event_id="event-run-cancelled",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id="client-cancel",
                idempotency_key="idem-cancel",
                reason="user_stop",
                mode=CancelMode.GRACEFUL,
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )

    transaction_runner.run_write(_operation)


def _cancel_predispatch_dispatching(transaction_runner: HostTransactionRunner, seeded: _SeededRun) -> None:
    """取消已进入 pre-accept dispatching 的 seeded Run。

    :param transaction_runner: transaction runner。
    :param seeded: seeded run。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        """执行 durable cancel。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        cancel_predispatch_starting_in_transaction(
            transaction,
            EventLogStore(),
            CancelPredispatchStartingInput(
                run_id=seeded.run_id,
                cancel_request_event_id="event-cancel-race-requested",
                attempt_cancelled_event_id="event-cancel-race-attempt",
                run_cancelled_event_id="event-cancel-race-run",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id="client-cancel-race",
                idempotency_key="idem-cancel-race",
                reason="user_stop",
                mode=CancelMode.GRACEFUL,
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )

    transaction_runner.run_write(_operation)


def _unreachable_engine_event() -> EngineEvent:
    """构造不可达 EngineEvent 占位。

    :returns: 当前函数不会被执行。
    :raises AssertionError: 若测试错误执行到该分支则抛出。
    """

    raise AssertionError("unreachable")


def _require_text(value: str | None) -> str:
    """断言可选文本非空。

    :param value: 可选文本。
    :returns: 非空文本。
    :raises AssertionError: 文本缺失时抛出。
    """

    assert value is not None
    return value


def _required_json_mapping(value: JsonValue) -> Mapping[str, JsonValue]:
    """读取测试 canonical payload 中的 JSON object。

    :param value: 待校验 JSON 值。
    :returns: 严格字符串 key 的 JSON mapping。
    :raises AssertionError: 值不是 JSON object 时抛出。
    """

    assert isinstance(value, Mapping)
    return cast(Mapping[str, JsonValue], value)


def _required_json_text(value: JsonValue) -> str:
    """读取测试 canonical payload 中的非空文本。

    :param value: 待校验 JSON 值。
    :returns: 非空文本。
    :raises AssertionError: 值不是非空文本时抛出。
    """

    assert isinstance(value, str)
    assert value != ""
    return value


def _required_json_int(value: JsonValue) -> int:
    """读取测试 canonical payload 中的严格整数。

    :param value: 待校验 JSON 值。
    :returns: 严格整数。
    :raises AssertionError: 值不是严格整数时抛出。
    """

    assert isinstance(value, int)
    assert not isinstance(value, bool)
    return value


def _required_json_text_tuple(value: JsonValue) -> tuple[str, ...]:
    """从 JSON 值中读取字符串 tuple。

    :param value: JSON 值。
    :returns: 字符串 tuple。
    :raises AssertionError: 值不是字符串数组时抛出。
    """

    assert isinstance(value, list)
    result: list[str] = []
    for item in value:
        assert isinstance(item, str)
        result.append(item)
    return tuple(result)
