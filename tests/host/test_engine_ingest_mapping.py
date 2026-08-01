"""Host Phase 5 EngineEvent ingest 映射测试。"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import NoReturn, cast

import pytest

import dayu.host.engine_ingest as engine_ingest_module
from tests.host.transient_delta_support import (
    FailingTransientDeltaPublisher,
    NOOP_TRANSIENT_DELTA_PUBLISHER,
    RecordingTransientDeltaPublisher,
)
from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionRequest
from dayu.contracts.tool_await import ToolAwaitKind, ToolAwaitSpec
from dayu.contracts.tool_call import ToolCallRequest
from dayu.contracts.tool_executor import ToolExecutor
from dayu.contracts.tool_outcome import BatchToolExecutionOutcome
from dayu.contracts.tool_outcome import ToolCompletedOutcome
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.error_codes import (
    EngineRunErrorCode,
    adapter_error_code,
    runner_protocol_error_code,
)
from dayu.engine.contracts.engine_events import (
    ContextCompactionRequestedData,
    ContentCompleteData,
    ContentDeltaData,
    EngineEvent,
    EngineEventData,
    EngineEventType,
    FinalAnswerData,
    IterationCompletedData,
    IterationStartedData,
    ProviderDiagnosticData,
    ProviderProtocolErrorData,
    ReasoningDeltaData,
    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION,
    RunnerInputMessageProjection,
    RunnerInputToolCallProjection,
    RunCancelledData,
    RunFailedData,
    RunSuspendedData,
    ToolAwaitingData,
    ToolCallBatchItemData,
    ToolCallDeltaData,
    ToolCallRequestedData,
    ToolCallsBatchDoneData,
    ToolCallsBatchReadyData,
    ToolResultAcceptedData,
    UsageReportedData,
    runner_role_sequence_digest,
)
from dayu.host.queue_policy import RunQueuePolicy
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.messages import AgentMessageRole, SystemMessage, UserMessage
from dayu.engine.contracts.partial_tool_call import PartialToolCallSummary
from dayu.engine.contracts.runner_spec import (
    ClientCorrelationPolicy,
    RunnerCallOptions,
    RunnerSpec,
)
from dayu.engine.contracts.runner_events import (
    RunnerDiagnosticSeverity,
    RunnerDiagnosticSource,
)
from dayu.engine.contracts.tool_records import (
    AcceptedToolExecutionRecord,
    AssistantToolCallBatchSnapshot,
    AwaitingToolExecutionRecord,
)
from dayu.host.admission import PendingDispatchRecord
from dayu.host.terminal_post_commit import TerminalPostCommitNotice
from dayu.host._runner_call_manifest import (
    RunnerCallHotAtoms,
    RunnerCallProjectorMetadata,
    RunnerCallSizingSnapshot,
    RunnerCallSizingUnavailableReason,
    complete_runner_call_sizing_snapshot,
    complete_runner_call_hot_diagnostic,
    parse_runner_call_hot_payload,
    parse_runner_call_manifest,
    runner_call_hot_payload,
    runner_call_projector_metadata_descriptor,
    unavailable_runner_call_sizing_snapshot,
)
from dayu.host._execution_config_projection import (
    effective_execution_config_json,
    effective_execution_snapshot_from_json,
)
from dayu.host.api import (
    AttemptStatus,
    CancelMode,
    EnsureSessionRequest,
    HostCallContext,
    HostContentDelta,
    HostReasoningDelta,
    HostToolCallDelta,
    HostTransientDeltaType,
    OperationContext,
    ResolveWaitCompletedOutcome,
    ResolveWaitRequest,
    RunStatus,
    WaitAdapterKey,
    WaitResolutionSource,
)
from dayu.host.context_events import (
    CONTEXT_BUDGET_EVALUATED,
    CONTEXT_COMPACTED,
    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
    CONTEXT_COMPACTION_FAILED,
    CONTEXT_COMPACTION_REQUESTED,
    append_context_budget_evaluated_in_transaction,
    build_context_compaction_failed_payload,
    parse_context_budget_evaluated_payload,
)
from dayu.host.compaction_terminal import (
    COMPACTION_TERMINAL_INVALID_MULTIPLE_ERROR,
)
from dayu.host.compact_payload import (
    COMPACT_ARTIFACT_MEDIA_TYPE_VNEXT,
    COMPACT_ARTIFACT_SCHEMA_VERSION_VNEXT,
    COMPACT_PROJECTION_SIGNAL_MEMORY_CATCHUP,
)
from dayu.host.compact_material import (
    conversation_compact_input_vnext_from_material_pack,
)
from dayu.host.compaction import (
    CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT,
    CompactQualityCheckResultVNext,
    CompactionRequest,
    ConversationCompactOutputVNext,
    ContextCompactor,
)
from dayu.host.compaction_operation import (
    CompactionOperationResult,
    CompactorProposalManifestRecorder,
    CompactorProposalRunInput,
)
from dayu.host.context_policy import (
    ContextBudgetPolicy,
    context_budget_policy_from_threshold_tokens,
)
from dayu.host.context_budget import (
    CONTEXT_ESTIMATOR_CONTRACT,
    BudgetEstimate,
    ContextBudgetDecision,
    ContextEstimateMethod,
    ContextEstimatorContract,
    ContextPressureLevel,
    ContextSizingFallbackReason,
    ContextSizingStage,
    build_conservative_context_sizing_result_from_atoms,
)
from dayu.host.context_anchor import (
    CompatibleContextAnchor,
    ContextAnchorQuery,
    ContextAnchorResolution,
)
from dayu.host.durable.codec import format_utc_timestamp, sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.idempotency import IdempotencyStore
from dayu.host.durable.liveness import (
    HostInstanceIdentity,
    register_current_instance,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.payload import (
    PayloadKind,
    PayloadStore,
    SQLitePayloadFormat,
    SQLitePayloadWriteRequest,
)
from dayu.host.durable.run_transition import (
    AcceptWorkerRunningInput,
    ActiveCancelWatchdogCloseoutInput,
    CancelActiveAttemptInput,
    CreateRunningRunInput,
    FailRecoveringRunInput,
    RunTransitionResult,
    StartRecoveryRunInput,
    StartGovernedRunInput,
    TerminalCloseoutInput,
    accept_worker_running_in_transaction,
    active_cancel_watchdog_closeout_in_transaction,
    create_running_run_with_starting_attempt_in_transaction,
    request_active_attempt_cancel_in_transaction,
)
from dayu.host.durable.tool_trace import read_tool_trace_json_payload
from dayu.host.payload_resolution import sqlite_payload_object
from dayu.host.durable.schema import (
    RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION,
    TABLE_EVENT_LOG,
    TABLE_HOST_ATTEMPTS,
    TABLE_HOST_RUNS,
    TABLE_PAYLOAD_DESCRIPTORS,
    TABLE_SQLITE_PAYLOADS,
)
from dayu.host.durable.session_lifecycle import ensure_session
from dayu.host.durable.state import (
    AttemptRow,
    DispatchRecordRow,
    DispatchRecordStatus,
    RunRow,
    RunStartReason,
    StateMutationStatus,
    WaitResumePolicy,
    WorkerKind,
    insert_attempt,
    insert_dispatch_record,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatching_after_lane_row,
    read_attempt_by_id,
    read_dispatch_record_by_attempt_id,
    read_run_by_id,
    steer_active_run_row,
    steer_running_attempt_row,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.lifecycle_events import (
    closeout_attempt_terminal_event_type_for_status,
    run_terminal_event_type_for_status,
)
from dayu.host.memory import (
    MemoryProjectionPolicy,
    default_memory_projection_policy,
)
from dayu.host.memory_repair import (
    ConversationMemoryProjectionRepairResult,
    catch_up_conversation_memory_projection,
)
from dayu.host.payload_resolution import event_payload_object
from dayu.host.run_input import (
    PolicySnapshot,
    PreparedRunnerCallCandidate,
    PreparedRunnerCallSourceError,
    PreparedRunnerCallSourceFailureCategory,
    SessionContinuityView,
    ToolExecutionMode,
    _prepared_candidate_payload_ref,
    load_prepared_runner_call_candidate_in_transaction,
    load_prepared_runner_call_source_in_transaction,
    prepare_runner_call_candidate_in_transaction,
    record_prepared_runner_call_candidate_in_transaction,
)
from tests.host._context_compaction_assertions import assert_failed_payload_no_fallback
from tests.host.fake_cancellation import ControllableCancellationToken
from tests.host.fake_compaction import FakeContextCompactor
from dayu.host.wait_adapter import WaitAdapterBinding, WaitExternalJobRefSource
from dayu.host.waiting import (
    DefaultHostResolveWaitService,
    DefaultHostToolAwaitingAcceptPort,
    ToolAwaitingAcceptCandidate,
    ToolAwaitingAcceptedAck,
)
from dayu.host.engine_ingest import (
    EngineEventCandidate,
    EngineEventIngestor,
    EngineIngestResult,
    EngineIngestStatus,
    LocalEngineEnvelope,
)

_NOW = datetime(2026, 5, 15, 1, 2, 3, tzinfo=UTC)
_CALL_CONTEXT_DIGEST = sha256_digest_json({"context": "engine-ingest-test"})
_REACTIVE_POLICY_REF = "test-reactive-policy"
_ORIGINAL_INGEST_VALIDATED_OPERATION_CALL = (
    engine_ingest_module._IngestValidatedOperation.__call__
)


class _ExpectedTransientRollback(RuntimeError):
    """测试专用的 transient ingest rollback sentinel。"""


def _force_rollback_after_validated_ingest(
    operation: engine_ingest_module._IngestValidatedOperation,
    transaction: HostTransaction,
) -> NoReturn:
    """在 validated ingest 完成后抛错，使 durable transaction 回滚。

    :param operation: 当前 ingest transaction operation。
    :param transaction: 当前 Host write transaction。
    :returns: 本函数不会返回。
    :raises _ExpectedTransientRollback: validated ingest 完成后始终抛出。
    """

    _ORIGINAL_INGEST_VALIDATED_OPERATION_CALL(operation, transaction)
    raise _ExpectedTransientRollback("forced transient ingest rollback")


class _EngineHotTamperKind(StrEnum):
    """Engine ingest shared hot parser 的篡改分类。"""

    MISSING_DIAGNOSTIC = "missing_diagnostic"
    NULL_DIAGNOSTIC = "null_diagnostic"
    MALFORMED_DIAGNOSTIC = "malformed_diagnostic"
    LEGACY_METADATA_ARRAY = "legacy_metadata_array"
    STATUS_MISMATCH = "status_mismatch"
    COUNT_MISMATCH = "count_mismatch"
    DIGEST_MISMATCH = "digest_mismatch"


class _ReactiveSourceTamperKind(StrEnum):
    """reactive source strict-load 的 durable 篡改分类。"""

    EFFECTIVE_CONFIG_MISSING = "effective_config_missing"
    MANIFEST_MISSING = "manifest_missing"
    CANDIDATE_DIGEST_MISMATCH = "candidate_digest_mismatch"
    TOOL_SNAPSHOT_MISSING = "tool_snapshot_missing"


@dataclass(frozen=True, slots=True)
class _SeededRun:
    """测试中创建的 active Engine run。"""

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str


class _AttemptFenceReadSpy:
    """把 validation transaction 读取的 Attempt fence 替换为唯一 sentinel。"""

    def __init__(self, *, started_event_sequence: int) -> None:
        """初始化 transaction read spy。

        :param started_event_sequence: 注入 current Attempt row 的正整数 fence。
        :returns: 无返回值。
        :raises ValueError: 本测试 helper 不主动校验 sentinel。
        """

        self._started_event_sequence = started_event_sequence
        self.call_count = 0

    def __call__(
        self,
        transaction: HostTransaction,
        attempt_id: str,
    ) -> AttemptRow | None:
        """读取真实 current Attempt，并只替换 transaction-local fence。

        :param transaction: 当前 validation write transaction。
        :param attempt_id: candidate Attempt 标识。
        :returns: 缺失时返回 ``None``；否则返回携带 sentinel fence 的 row。
        :raises HostDurableError: durable row 解码失败时抛出。
        """

        self.call_count += 1
        attempt = read_attempt_by_id(transaction, attempt_id)
        if attempt is None:
            return None
        return replace(
            attempt,
            started_event_sequence=self._started_event_sequence,
        )


def _cas_lost_terminal_closeout(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: TerminalCloseoutInput,
) -> RunTransitionResult:
    """模拟 terminal helper 在写 payload 后返回 CAS loser。

    :param transaction: 当前真实 Host transaction。
    :param event_log_store: 生产 EventLog store；本注入点不写事件。
    :param request: terminal closeout 输入。
    :returns: 携带真实 durable rows 的 ``CAS_LOST`` transition 结果。
    :raises AssertionError: seeded durable rows 缺失时抛出。
    """

    del event_log_store
    run = read_run_by_id(transaction, request.run_id)
    attempt = read_attempt_by_id(transaction, request.attempt_id)
    dispatch_record = read_dispatch_record_by_attempt_id(
        transaction, request.attempt_id
    )
    assert run is not None
    assert attempt is not None
    assert dispatch_record is not None
    return RunTransitionResult(
        status=StateMutationStatus.CAS_LOST,
        run=run,
        attempt=attempt,
        dispatch_record=dispatch_record,
        run_event=None,
    )


class _TransactionReadableCompactor(FakeContextCompactor):
    """测试 compactor 调用期可开启独立读事务。"""

    def __init__(self, transaction_runner: HostTransactionRunner) -> None:
        """初始化 compactor。

        :param transaction_runner: Host transaction runner。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner
        self.calls = 0

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> ConversationCompactOutputVNext:
        """执行 vNext compact 并验证当前不在外层 write transaction 内。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: fake vNext compaction candidate。
        """

        self.calls += 1
        row = self._transaction_runner.run_read(
            lambda transaction: read_run_by_id(transaction, request.run_id)
        )
        assert row is not None
        return await super().compact(request, cancellation_token)


class _InputSequenceAdvancingCompactor(FakeContextCompactor):
    """测试 compactor，在 proposal 期间推进 Run input sequence。"""

    def __init__(self, transaction_runner: HostTransactionRunner) -> None:
        """初始化 compactor。

        :param transaction_runner: Host transaction runner。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner
        self.calls = 0

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> ConversationCompactOutputVNext:
        """推进 durable input sequence 后返回旧 snapshot 的 vNext candidate。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: 基于旧 request 的 fake vNext compaction candidate。
        """

        self.calls += 1
        _advance_run_input_sequence(self._transaction_runner, run_id=request.run_id)
        return await super().compact(request, cancellation_token)


class _InvalidMultipleReactiveCompactor(FakeContextCompactor):
    """在 provider await 期间注入两个 reactive canonical terminal。"""

    def __init__(self, transaction_runner: HostTransactionRunner) -> None:
        """初始化损坏 terminal 注入 compactor。

        :param transaction_runner: Host transaction runner。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._transaction_runner = transaction_runner

    async def compact(
        self,
        request: CompactionRequest,
        cancellation_token: CancellationToken,
    ) -> ConversationCompactOutputVNext:
        """提交两个同 operation failed terminal 后返回 accepted candidate。

        :param request: reactive compaction request。
        :param cancellation_token: Host cancellation token。
        :returns: fake accepted candidate。
        :raises AssertionError: request canonical fact 不存在时抛出。
        """

        def _operation(transaction: HostTransaction) -> None:
            """在单笔事务内追加两个 canonical terminal。

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
            for ordinal in (1, 2):
                EventLogStore().append_event(
                    transaction,
                    EventLogAppendRequest(
                        event_id=f"event-reactive-invalid-multiple-{ordinal}",
                        event_class=EventClass.CANONICAL_FACT,
                        session_id=request.session_id,
                        run_id=request.run_id,
                        attempt_id=request.attempt_id,
                        execution_id=request.execution_id,
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

        self._transaction_runner.run_write(_operation)
        return await super().compact(request, cancellation_token)


class _RaisingCompactor(FakeContextCompactor):
    """测试用失败 compactor。"""

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> ConversationCompactOutputVNext:
        """抛出 vNext proposal 失败。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: 不返回。
        :raises RuntimeError: 始终抛出 proposal failure。
        """

        del cancellation_token
        raise RuntimeError(f"proposal failed for {request.run_id}")


class _RejectingToolExecutor(ToolExecutor):
    """测试用工具执行器，prepared compactor 路径不会实际调用。"""

    async def execute(
        self, request: BatchToolExecutionRequest
    ) -> BatchToolExecutionOutcome:
        """拒绝意外工具执行。

        :param request: 批式工具执行请求。
        :returns: 不会返回。
        :raises AssertionError: 一旦被调用即抛出。
        """

        del request
        raise AssertionError("prepared compactor test must not execute tools")


class _PreparedManifestReactiveCompactor(FakeContextCompactor):
    """支持 prepared proposal manifest 的 reactive 测试 compactor。"""

    def __init__(self, *, fail_run: bool = False) -> None:
        """初始化 prepared compactor。

        :param fail_run: 是否在 prepared proposal 执行阶段抛错。
        :returns: ``None``。
        """

        self.fail_run = fail_run
        self.calls = 0
        self._prepared_request: CompactionRequest | None = None

    def prepare_compactor_proposal_run_input(
        self,
        request: CompactionRequest,
        cancellation_token: CancellationToken,
        *,
        compaction_operation_id: str | None,
        compaction_attempt_number: int,
    ) -> CompactorProposalRunInput:
        """构造测试用 prepared compactor proposal input。

        :param request: Host compaction request。
        :param cancellation_token: Host cancellation token。
        :param compaction_operation_id: operation id。
        :param compaction_attempt_number: operation 内 attempt 序号。
        :returns: prepared proposal input。
        """

        del cancellation_token
        self._prepared_request = request
        compact_input = conversation_compact_input_vnext_from_material_pack(
            request.material_pack
        )
        agent_request = _proposal_agent_request(
            request,
            compaction_operation_id=compaction_operation_id,
            compaction_attempt_number=compaction_attempt_number,
        )
        projection = {
            "projection_kind": "reactive_compactor_input_projection",
            "compaction_request_digest": request.digest(),
        }
        roles = tuple(message.role.value for message in agent_request.messages)
        return CompactorProposalRunInput(
            compact_input=compact_input,
            agent_request=agent_request,
            compaction_request_digest=request.digest(),
            compactor_engine_run_id=agent_request.run_id,
            message_count=len(agent_request.messages),
            role_sequence_digest=runner_role_sequence_digest(roles),
            system_prompt_asset_digest=_CALL_CONTEXT_DIGEST,
            user_prompt_template_digest=_CALL_CONTEXT_DIGEST,
            user_prompt_digest=sha256_digest_json({"user_prompt": "reactive"}),
            compactor_input_projection=projection,
            compactor_input_projection_digest=sha256_digest_json(projection),
        )

    async def run_prepared_compactor_proposal(
        self,
        prepared_input: CompactorProposalRunInput,
    ) -> ConversationCompactOutputVNext:
        """执行 prepared proposal。

        :param prepared_input: prepared proposal input。
        :returns: fake compact candidate。
        :raises RuntimeError: ``fail_run`` 为真时抛出。
        """

        self.calls += 1
        if self.fail_run:
            raise RuntimeError("prepared reactive proposal failed")
        request = self._prepared_request
        if request is None:
            raise AssertionError("prepared request is missing")
        return await super().compact(
            request,
            prepared_input.agent_request.cancellation_token,
        )


class _WakeupSpy:
    """测试用 wakeup port。"""

    def __init__(self) -> None:
        """初始化 spy。

        :returns: ``None``。
        """

        self.promoted_session_ids: list[str] = []
        self.dispatches: list[PendingDispatchRecord] = []

    def wake_dispatch(self, record: PendingDispatchRecord) -> None:
        """记录 dispatch wakeup。

        :param record: pending dispatch record。
        :returns: ``None``。
        """

        self.dispatches.append(record)

    def wake_queue_promotion(self, session_id: str) -> None:
        """记录 queue promotion wakeup。

        :param session_id: Session id。
        :returns: ``None``。
        """

        self.promoted_session_ids.append(session_id)


@dataclass(slots=True)
class _RecordingTerminalPostCommitPort:
    """记录 Engine ingest commit 后的 exact terminal notices。"""

    notices: list[TerminalPostCommitNotice]

    def __init__(self) -> None:
        """初始化空记录器。

        :returns: ``None``。
        """

        self.notices = []

    def notify_terminal_post_commit(
        self,
        notice: TerminalPostCommitNotice,
    ) -> None:
        """记录一次已提交 terminal notice。

        :param notice: exact terminal notice。
        :returns: ``None``。
        """

        self.notices.append(notice)


@dataclass(frozen=True, slots=True)
class _CommittedTerminalObservation:
    """terminal port 回调内读取到的 committed Run 与 exact event。"""

    notice: TerminalPostCommitNotice
    run: RunRow
    run_event: EventLogRow


@dataclass(frozen=True, slots=True)
class _ReadCommittedTerminalObservation:
    """按预期 Run identity 读取已提交 terminal owner facts。"""

    expected_session_id: str
    expected_run_id: str

    def __call__(
        self,
        transaction: HostTransaction,
    ) -> tuple[RunRow, EventLogRow]:
        """读取 committed Run 与其 stable terminal event。

        :param transaction: callback 发起的独立 read transaction。
        :returns: identity 与 stable ref 完全一致的 Run/event 二元组。
        :raises AssertionError: Run、terminal ref、event 或 identity 缺失时抛出。
        """

        run = read_run_by_id(transaction, self.expected_run_id)
        assert run is not None
        assert run.session_id == self.expected_session_id
        assert run.terminal_event_id is not None
        assert run.terminal_event_sequence is not None
        run_event = EventLogStore().read_event_by_id(
            transaction,
            run.terminal_event_id,
        )
        assert run_event is not None
        assert run_event.event_sequence == run.terminal_event_sequence
        assert run_event.session_id == run.session_id
        assert run_event.run_id == run.run_id
        return run, run_event


@dataclass(slots=True)
class _CommittedTerminalPostCommitPort:
    """在 terminal port 回调中验证 commit 已返回且 exact row 可见。"""

    _db_path: Path
    _transaction_runner: HostTransactionRunner
    _reader: _ReadCommittedTerminalObservation
    observations: list[_CommittedTerminalObservation]

    def __init__(
        self,
        *,
        db_path: Path,
        transaction_runner: HostTransactionRunner,
        expected_session_id: str,
        expected_run_id: str,
    ) -> None:
        """初始化 committed terminal 观察端口。

        :param db_path: production ingest 使用的 durable DB路径。
        :param transaction_runner: production ingest 使用的 durable runner。
        :param expected_session_id: 预期 terminal Session id。
        :param expected_run_id: 预期 terminal Run id。
        :returns: ``None``。
        :raises: 无主动抛出。
        """

        self._db_path = db_path
        self._transaction_runner = transaction_runner
        self._reader = _ReadCommittedTerminalObservation(
            expected_session_id=expected_session_id,
            expected_run_id=expected_run_id,
        )
        self.observations = []

    def notify_terminal_post_commit(
        self,
        notice: TerminalPostCommitNotice,
    ) -> None:
        """验证 callback 位于 commit return 后并记录 exact owner facts。

        :param notice: production ``_finish_ingest`` 交付的 terminal notice。
        :returns: ``None``。
        :raises AssertionError: callback 仍在 transaction 中或 notice 与已提交
            stable Run/event ref 不一致时抛出。
        """

        assert not self._transaction_runner.has_active_transaction
        with sqlite3.connect(self._db_path) as connection:
            committed_row = connection.execute(
                f"""
                SELECT
                    runs.session_id,
                    runs.run_id,
                    runs.terminal_event_sequence,
                    events.event_sequence,
                    events.session_id,
                    events.run_id
                FROM {TABLE_HOST_RUNS} AS runs
                JOIN {TABLE_EVENT_LOG} AS events
                  ON events.event_id = runs.terminal_event_id
                WHERE runs.run_id = ?
                """,
                (self._reader.expected_run_id,),
            ).fetchone()
        assert committed_row is not None
        assert str(committed_row[0]) == notice.session_id
        assert str(committed_row[1]) == self._reader.expected_run_id
        assert int(committed_row[2]) == notice.terminal_event_sequence
        assert int(committed_row[3]) == notice.terminal_event_sequence
        assert str(committed_row[4]) == notice.session_id
        assert str(committed_row[5]) == self._reader.expected_run_id
        run, run_event = self._transaction_runner.run_read(self._reader)
        assert notice.session_id == run.session_id
        assert notice.terminal_event_sequence == run_event.event_sequence
        self.observations.append(
            _CommittedTerminalObservation(
                notice=notice,
                run=run,
                run_event=run_event,
            )
        )


def test_final_answer_closes_attempt_and_run_with_phase5_payload(
    tmp_path: Path,
) -> None:
    """final_answer 映射为 ATTEMPT_SUCCEEDED 与 RUN_SUCCEEDED。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        candidate = _candidate(
            seeded,
            worker_event_index=1,
            data=FinalAnswerData(
                content="完成答案",
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
            event_type=EngineEventType.FINAL_ANSWER,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED, result.reason
        assert result.terminal_closeout is True
        assert result.terminal_notice is not None
        assert result.terminal_notice.wake_queue_promotion is True
        assert [event.event_type for event in result.events] == [
            "ATTEMPT_SUCCEEDED",
            "RUN_SUCCEEDED",
        ]
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.SUCCEEDED
        assert attempt_status == AttemptStatus.SUCCEEDED
        payload = _payload(result.events[0])
        assert payload["dispatch_record_id"] == seeded.dispatch_record_id
        assert payload["finish_reason"] == "stop"
        assert isinstance(payload["terminal_summary_ref"], str)
        assert isinstance(payload["terminal_summary_digest"], str)

        terminal_payload = store.transaction_runner.run_read(
            lambda transaction: sqlite_payload_object(
                transaction,
                payload_ref=cast(str, payload["terminal_summary_ref"]),
                payload_digest=cast(str, payload["terminal_summary_digest"]),
                payload_label="terminal payload",
            )
        )
        assert terminal_payload["content"] == "完成答案"
        assert terminal_payload["finish_reason"] == "stop"
        assert terminal_payload["filtered"] is False
        assert terminal_payload["degraded"] is False
        assert terminal_payload["attempt_id"] == seeded.attempt_id
        assert terminal_payload["execution_id"] == seeded.execution_id
        assert "summary" not in terminal_payload
        assert "summary_text" not in terminal_payload


def test_terminal_plans_use_lifecycle_event_owner_helpers() -> None:
    """两类 terminal plan 类型分离并复用 lifecycle event owner helper。

    :returns: ``None``。
    :raises AssertionError: 类型边界或 owner helper 映射漂移时抛出。
    """

    succeeded = engine_ingest_module._final_answer_plan(
        FinalAnswerData(
            content="完成答案",
            filtered=False,
            degraded=False,
            finish_reason=FinishReason.STOP,
        )
    )
    failed = engine_ingest_module._run_failed_plan(
        RunFailedData(
            error_code=adapter_error_code("provider_error"),
            message="provider failed",
            provider_request_id=None,
            client_correlation_id=None,
            recoverable=False,
        )
    )
    lost = engine_ingest_module._lost_lifecycle_plan(
        worker_lifecycle_signal="worker_crashed",
        stream_error_code=None,
        last_observed_worker_event_index=3,
        last_accepted_event_id=None,
    )

    assert isinstance(succeeded, engine_ingest_module._EngineTerminalPlan)
    assert isinstance(failed, engine_ingest_module._EngineTerminalPlan)
    assert isinstance(lost, engine_ingest_module._HostLifecycleTerminalPlan)
    engine_plan_fields = {field.name for field in fields(succeeded)}
    host_plan_fields = {field.name for field in fields(lost)}
    assert engine_plan_fields == {
        "terminal",
        "finish_reason",
        "filtered",
        "degraded",
        "error_code",
        "message",
        "provider_request_id",
        "client_correlation_id",
        "recoverable",
        "unsupported_later_owner",
    }
    assert host_plan_fields == {
        "terminal",
        "error_code",
        "message",
        "recoverable",
        "worker_lifecycle_signal",
        "stream_error_code",
        "last_observed_worker_event_index",
        "last_accepted_event_id",
    }
    assert succeeded.terminal.attempt_event_type == (
        closeout_attempt_terminal_event_type_for_status(AttemptStatus.SUCCEEDED).value
    )
    assert succeeded.terminal.run_event_type == (
        run_terminal_event_type_for_status(RunStatus.SUCCEEDED).value
    )
    assert failed.terminal.attempt_event_type == (
        closeout_attempt_terminal_event_type_for_status(AttemptStatus.FAILED).value
    )
    assert failed.terminal.run_event_type == (
        run_terminal_event_type_for_status(RunStatus.FAILED).value
    )
    assert lost.terminal.attempt_event_type == (
        closeout_attempt_terminal_event_type_for_status(AttemptStatus.LOST).value
    )
    assert lost.terminal.run_event_type == (
        run_terminal_event_type_for_status(RunStatus.LOST).value
    )


def test_engine_owned_empty_final_failure_closes_failed(
    tmp_path: Path,
) -> None:
    """Engine-owned 空 final 失败事实映射为 Host FAILED。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _candidate(
            seeded,
            worker_event_index=2,
            data=RunFailedData(
                error_code=EngineRunErrorCode.RUNNER_EMPTY_FINAL_CONTENT,
                message="runner did not produce final content",
                provider_request_id=None,
                client_correlation_id=None,
                recoverable=False,
            ),
            event_type=EngineEventType.RUN_FAILED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        assert [event.event_type for event in result.events] == [
            "ATTEMPT_FAILED",
            "RUN_FAILED",
        ]
        assert _event_count(store.transaction_runner, "RUN_SUCCEEDED") == 0
        assert _event_count(store.transaction_runner, "RUN_FAILED") == 1
        payload = _payload(result.events[0])
        assert payload["error_code"] == "runner_empty_final_content"
        assert payload["recoverable"] is False
        assert "content" not in payload
        assert "final_answer" not in payload
        run_payload = _payload(result.events[1])
        assert run_payload["error_code"] == "runner_empty_final_content"
        assert "content" not in run_payload
        assert "final_answer" not in run_payload
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.FAILED
        assert attempt_status == AttemptStatus.FAILED


def test_run_failed_recoverable_false_closes_failed(tmp_path: Path) -> None:
    """不可恢复 run_failed 直接映射为 FAILED closeout。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _candidate(
            seeded,
            worker_event_index=2,
            data=RunFailedData(
                error_code=adapter_error_code("provider_error"),
                message="provider failed",
                provider_request_id="req-1",
                client_correlation_id="client-req-1",
                recoverable=False,
            ),
            event_type=EngineEventType.RUN_FAILED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert [event.event_type for event in result.events] == [
            "ATTEMPT_FAILED",
            "RUN_FAILED",
        ]
        payload = _payload(result.events[0])
        assert payload["error_code"] == "provider_error"
        assert payload["client_correlation_id"] == "client-req-1"
        assert payload["recoverable"] is False
        assert _payload(result.events[1])["client_correlation_id"] == "client-req-1"
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.FAILED
        assert attempt_status == AttemptStatus.FAILED


def test_run_failed_recoverable_true_is_diagnostic_then_failed(tmp_path: Path) -> None:
    """可恢复 run_failed 在 Phase 5 不进入 RECOVERING。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _candidate(
            seeded,
            worker_event_index=3,
            data=RunFailedData(
                error_code=adapter_error_code("context_recovery_needed"),
                message="recoverable",
                provider_request_id="req-2",
                client_correlation_id="client-req-2",
                recoverable=True,
            ),
            event_type=EngineEventType.RUN_FAILED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert [event.event_class for event in result.events] == [
            EventClass.DIAGNOSTIC,
            EventClass.CANONICAL_FACT,
            EventClass.CANONICAL_FACT,
        ]
        assert result.events[1].event_type == "ATTEMPT_FAILED"
        assert _payload(result.events[0])["client_correlation_id"] == "client-req-2"
        payload = _payload(result.events[1])
        assert payload["unsupported_later_owner"] == "phase10"
        assert payload["client_correlation_id"] == "client-req-2"
        run_status, _attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.FAILED


@pytest.mark.asyncio
async def test_context_compaction_requested_none_budget_uses_host_estimator_and_recovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """provider overflow budget_state=None 使用 Host estimator 并进入 recovery。"""

    original_run_compaction_operation = (
        engine_ingest_module.run_compaction_operation
    )
    observed_attempt_ranges: list[tuple[int, int, str | None]] = []

    async def observe_run_compaction_operation(
        *,
        request: CompactionRequest,
        compactor: ContextCompactor,
        first_attempt_number: int,
        max_attempt_number: int,
        cancellation_token: CancellationToken,
        pass_queue: tuple[CompactionRequest, ...] = (),
        compaction_operation_id: str | None = None,
        proposal_manifest_recorder: CompactorProposalManifestRecorder | None = None,
    ) -> CompactionOperationResult:
        """记录 Engine ingest 传给 operation owner 的冻结 attempt range。

        :param request: reactive root compaction request。
        :param compactor: reactive compactor。
        :param first_attempt_number: 首个全局 attempt number。
        :param max_attempt_number: 冻结的 operation attempt 上限。
        :param cancellation_token: Host cancellation token。
        :param pass_queue: reactive pass queue。
        :param compaction_operation_id: request event 同源 operation id。
        :param proposal_manifest_recorder: durable manifest recorder。
        :returns: 原 operation owner 的执行结果。
        :raises Exception: 原 operation owner 异常时透传。
        """

        observed_attempt_ranges.append(
            (
                first_attempt_number,
                max_attempt_number,
                compaction_operation_id,
            )
        )
        return await original_run_compaction_operation(
            request=request,
            compactor=compactor,
            first_attempt_number=first_attempt_number,
            max_attempt_number=max_attempt_number,
            cancellation_token=cancellation_token,
            pass_queue=pass_queue,
            compaction_operation_id=compaction_operation_id,
            proposal_manifest_recorder=proposal_manifest_recorder,
        )

    monkeypatch.setattr(
        engine_ingest_module,
        "run_compaction_operation",
        observe_run_compaction_operation,
    )

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        wakeup = _WakeupSpy()
        policy = replace(
            _reactive_policy(),
            max_compaction_attempts_per_operation=3,
        )
        candidate = _candidate(
            seeded,
            worker_event_index=4,
            data=ContextCompactionRequestedData(
                iteration_id="iter-1",
                budget_state=None,
                reason="provider_overflow",
                provider_request_id="req-overflow",
                client_correlation_id="client-overflow",
            ),
            event_type=EngineEventType.CONTEXT_COMPACTION_REQUESTED,
        )

        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            wakeup_port=wakeup,
            context_budget_policy=policy,
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        ).ingest_async(candidate)

        assert result.terminal_closeout is False
        assert result.stop_worker_stream is True
        assert wakeup.promoted_session_ids == []
        event_types = tuple(event.event_type for event in result.events)
        assert event_types[:4] == (
            CONTEXT_COMPACTION_REQUESTED,
            "ATTEMPT_FAILED",
            "RUN_RECOVERING",
            CONTEXT_COMPACTED,
        )
        assert event_types[-4:] == (
            "RUNNER_CALL_INPUT_ASSEMBLED",
            "CONTEXT_BUDGET_EVALUATED",
            "RUN_STARTED",
            "ATTEMPT_STARTED",
        )
        requested_payload = _payload(result.events[0])
        assert requested_payload["operation_id"] == result.events[0].event_id
        assert requested_payload["max_compaction_attempts_per_operation"] == (
            policy.max_compaction_attempts_per_operation
        )
        assert observed_attempt_ranges == [
            (
                1,
                policy.max_compaction_attempts_per_operation,
                result.events[0].event_id,
            )
        ]
        assert requested_payload["trigger_source"] == "reactive"
        assert requested_payload["provider_request_id"] == "req-overflow"
        assert requested_payload["client_correlation_id"] == "client-overflow"
        assert requested_payload["attempt_id"] == seeded.attempt_id
        assert requested_payload["execution_id"] == seeded.execution_id
        assert requested_payload["frozen_material_refs"] == ["event-input-ingest"]
        assert isinstance(requested_payload["frozen_material_list_digest"], str)
        assert isinstance(requested_payload["estimator_digest"], str)
        compacted_payload = _payload(result.events[3])
        assert compacted_payload["operation_id"] == result.events[0].event_id
        assert compacted_payload["accepted_attempt_number"] == 1
        assert compacted_payload["projection_signal"] == (
            COMPACT_PROJECTION_SIGNAL_MEMORY_CATCHUP
        )
        accepted_candidate = compacted_payload["accepted_candidate"]
        assert isinstance(accepted_candidate, Mapping)
        assert accepted_candidate["schema_version"] == (
            CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT
        )
        assert "preserved_fact_refs" not in compacted_payload
        artifact_ref = compacted_payload["compact_artifact_ref"]
        assert isinstance(artifact_ref, str)
        descriptor = store.transaction_runner.run_read(
            lambda transaction: PayloadStore().read_payload_descriptor(
                transaction, artifact_ref
            )
        )
        assert descriptor is not None
        assert descriptor.media_type == COMPACT_ARTIFACT_MEDIA_TYPE_VNEXT
        assert descriptor.payload_digest == compacted_payload["compact_artifact_digest"]
        assert descriptor.artifact_relative_path is not None
        artifact_path = tmp_path / "compact-artifacts" / descriptor.artifact_relative_path
        artifact_raw = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert isinstance(artifact_raw, Mapping)
        artifact_json = cast(Mapping[str, JsonValue], artifact_raw)
        assert artifact_json["schema_version"] == (
            COMPACT_ARTIFACT_SCHEMA_VERSION_VNEXT
        )
        assert artifact_json["accepted_candidate_digest"] == (
            compacted_payload["accepted_candidate_digest"]
        )
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.RUNNING
        assert attempt_status == AttemptStatus.FAILED
        assert len(wakeup.dispatches) == 1
        assert wakeup.dispatches[0].attempt_id != seeded.attempt_id
        assert wakeup.dispatches[0].execution_id != seeded.execution_id
        recovery_manifest_event = result.events[-4]
        hot = parse_runner_call_hot_payload(
            _payload(recovery_manifest_event)
        )
        manifest_json = store.transaction_runner.run_read(
            lambda transaction: sqlite_payload_object(
                transaction,
                payload_ref=hot.manifest_payload_ref,
                payload_digest=hot.manifest_digest,
                payload_label="recovery manifest",
            )
        )
        manifest = parse_runner_call_manifest(
            manifest_json,
            hot_payload=hot,
        )
        recovery_attempt_id = hot.attempt_id
        recovery_execution_id = hot.execution_id
        assert recovery_attempt_id is not None
        assert recovery_execution_id is not None
        policy_snapshot, _config = _source_policy_snapshot_and_config()
        loaded = store.transaction_runner.run_read(
            lambda transaction: (
                    load_prepared_runner_call_candidate_in_transaction(
                        transaction,
                        EventLogStore(),
                    run_id=seeded.run_id,
                    attempt_id=recovery_attempt_id,
                    execution_id=recovery_execution_id,
                    policy_snapshot=policy_snapshot,
                )
            )
        )
        assert manifest.sizing_snapshot.sizing_stage is (
            ContextSizingStage.REACTIVE_POST_COMPACT
        )
        assert manifest.sizing_snapshot.input_snapshot_digest == (
            loaded.input_snapshot_digest
        )
        assert loaded.tool_execution_mode is (
            ToolExecutionMode.NO_TOOL_DISABLED
        )
        assert wakeup.dispatches[0].attempt_id == hot.attempt_id
        assert wakeup.dispatches[0].execution_id == hot.execution_id


@pytest.mark.asyncio
async def test_reactive_reuses_source_frozen_tool_snapshot_and_mode(
    tmp_path: Path,
) -> None:
    """recovery candidate 精确复用 source tool schema 与 execution mode。

    :param tmp_path: pytest 临时目录。
    """

    source_schema = _reactive_source_tool_schema()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
            source_tool_schema=source_schema,
        )
        wakeup = _WakeupSpy()
        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            wakeup_port=wakeup,
            context_budget_policy=_reactive_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        ).ingest_async(
            _context_compaction_candidate(
                seeded,
                worker_event_index=151,
            )
        )

        hot = parse_runner_call_hot_payload(_payload(result.events[-4]))
        recovery_attempt_id = hot.attempt_id
        recovery_execution_id = hot.execution_id
        assert recovery_attempt_id is not None
        assert recovery_execution_id is not None
        policy_snapshot, _config = _source_policy_snapshot_and_config(
            allow_tool_calls=True,
        )
        loaded = store.transaction_runner.run_read(
            lambda transaction: (
                    load_prepared_runner_call_candidate_in_transaction(
                        transaction,
                        EventLogStore(),
                    run_id=seeded.run_id,
                    attempt_id=recovery_attempt_id,
                    execution_id=recovery_execution_id,
                    policy_snapshot=policy_snapshot,
                )
            )
        )

        assert loaded.tool_schemas == (source_schema,)
        assert loaded.disable_tools is False
        assert loaded.tool_execution_mode is ToolExecutionMode.TOOL_ENABLED
        assert len(wakeup.dispatches) == 1


@pytest.mark.asyncio
async def test_reactive_memory_catch_up_failure_blocks_recovery_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """accepted compact 后 memory catch-up 失败必须零 start、零 wake。"""

    def fail_memory_catch_up(
        transaction_runner: HostTransactionRunner,
        *,
        policy: MemoryProjectionPolicy,
        batch_size: int,
        max_event_sequence: int,
    ) -> NoReturn:
        """模拟事务外 memory catch-up 失败。

        :param transaction_runner: Host transaction runner。
        :param policy: memory projection policy。
        :param batch_size: catch-up batch size。
        :param max_event_sequence: catch-up 目标 event sequence。
        :returns: 不返回。
        :raises RuntimeError: 始终抛出。
        """

        del transaction_runner, policy, batch_size, max_event_sequence
        raise RuntimeError("catch up failed")

    monkeypatch.setattr(
        engine_ingest_module,
        "catch_up_conversation_memory_projection",
        fail_memory_catch_up,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        wakeup = _WakeupSpy()

        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            wakeup_port=wakeup,
            context_budget_policy=_reactive_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        ).ingest_async(_context_compaction_candidate(seeded, worker_event_index=52))

        assert result.status is EngineIngestStatus.ACCEPTED
        assert result.events[-1].event_type == CONTEXT_COMPACTED
        assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 1
        assert _event_count(store.transaction_runner, "RUN_STARTED") == 1
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status is RunStatus.RECOVERING
        assert attempt_status is AttemptStatus.FAILED
        assert wakeup.dispatches == []


@pytest.mark.asyncio
async def test_reactive_memory_catch_up_not_reached_blocks_recovery_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """memory 未达到 compact exact cursor 时零 start、零 wake。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    """

    original_catch_up = catch_up_conversation_memory_projection

    def report_target_not_reached(
        transaction_runner: HostTransactionRunner,
        *,
        policy: MemoryProjectionPolicy,
        batch_size: int,
        max_event_sequence: int,
    ) -> ConversationMemoryProjectionRepairResult:
        """完成真实 projection 后注入 target-not-reached 汇总。

        :param transaction_runner: Host transaction runner。
        :param policy: memory projection policy。
        :param batch_size: projection batch size。
        :param max_event_sequence: required compact cursor。
        :returns: target 未达的 typed repair result。
        """

        result = original_catch_up(
            transaction_runner,
            policy=policy,
            batch_size=batch_size,
            max_event_sequence=max_event_sequence,
        )
        return replace(result, target_reached=False)

    monkeypatch.setattr(
        engine_ingest_module,
        "catch_up_conversation_memory_projection",
        report_target_not_reached,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        wakeup = _WakeupSpy()
        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            wakeup_port=wakeup,
            context_budget_policy=_reactive_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        ).ingest_async(
            _context_compaction_candidate(
                seeded,
                worker_event_index=53,
            )
        )

        assert result.events[-1].event_type == CONTEXT_COMPACTED
        assert _event_count(store.transaction_runner, "RUN_STARTED") == 1
        assert _attempt_count(store.transaction_runner, seeded.run_id) == 1
        assert _statuses(store.transaction_runner, seeded) == (
            RunStatus.RECOVERING,
            AttemptStatus.FAILED,
        )
        assert wakeup.dispatches == []


@pytest.mark.asyncio
async def test_reactive_recovery_requires_terminal_source_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """source Attempt 非终态时不得选择 reactive post-compact stage。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    """

    original_catch_up = catch_up_conversation_memory_projection

    def make_source_nonterminal(
        transaction_runner: HostTransactionRunner,
        *,
        policy: MemoryProjectionPolicy,
        batch_size: int,
        max_event_sequence: int,
    ) -> ConversationMemoryProjectionRepairResult:
        """追平后把 source fixture 改成非终态以验证 conjunction gate。

        :param transaction_runner: Host transaction runner。
        :param policy: memory projection policy。
        :param batch_size: projection batch size。
        :param max_event_sequence: required compact cursor。
        :returns: 真实 catch-up 汇总。
        """

        result = original_catch_up(
            transaction_runner,
            policy=policy,
            batch_size=batch_size,
            max_event_sequence=max_event_sequence,
        )

        def _make_nonterminal(transaction: HostTransaction) -> None:
            """把 source Attempt 还原为非终态 fixture。

            :param transaction: Host write transaction。
            :returns: ``None``。
            """

            updated = transaction.execute(
                f"""
                UPDATE {TABLE_HOST_ATTEMPTS}
                SET status = ?,
                    terminal_event_id = NULL,
                    terminal_event_sequence = NULL,
                    terminal_at = NULL
                WHERE attempt_id = ?
                """,
                (AttemptStatus.RUNNING.value, "attempt-ingest"),
            )
            assert updated.rowcount == 1

        transaction_runner.run_write(_make_nonterminal)
        return result

    monkeypatch.setattr(
        engine_ingest_module,
        "catch_up_conversation_memory_projection",
        make_source_nonterminal,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        wakeup = _WakeupSpy()
        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            wakeup_port=wakeup,
            context_budget_policy=_reactive_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        ).ingest_async(
            _context_compaction_candidate(
                seeded,
                worker_event_index=54,
            )
        )

        assert result.events[-1].event_type == CONTEXT_COMPACTED
        assert _event_count(store.transaction_runner, "RUN_STARTED") == 1
        assert _attempt_count(store.transaction_runner, seeded.run_id) == 1
        assert wakeup.dispatches == []


@pytest.mark.asyncio
async def test_reactive_recovery_requires_matching_committed_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """matching compact outcome 不可读时 fail closed 且零 start/wake。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    """

    original_read = EventLogStore.read_event_by_id

    def hide_compacted_outcome(
        event_log_store: EventLogStore,
        transaction: HostTransaction,
        event_id: str,
    ) -> EventLogRow | None:
        """只隐藏已提交 compact outcome，模拟 startup orphan。

        :param event_log_store: EventLog primitive。
        :param transaction: Host transaction。
        :param event_id: 待读取 event id。
        :returns: compacted outcome 返回 ``None``，其它 row 原样返回。
        """

        row = original_read(event_log_store, transaction, event_id)
        if row is not None and row.event_type == CONTEXT_COMPACTED:
            return None
        return row

    monkeypatch.setattr(
        EventLogStore,
        "read_event_by_id",
        hide_compacted_outcome,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        wakeup = _WakeupSpy()
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            wakeup_port=wakeup,
            context_budget_policy=_reactive_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        )

        with pytest.raises(
            HostDurableError,
            match="reactive compacted outcome identity is invalid",
        ):
            await ingestor.ingest_async(
                _context_compaction_candidate(
                    seeded,
                    worker_event_index=55,
                )
            )

        assert _event_count(store.transaction_runner, "RUN_STARTED") == 1
        assert _attempt_count(store.transaction_runner, seeded.run_id) == 1
        assert wakeup.dispatches == []


@pytest.mark.asyncio
async def test_reactive_post_compact_hard_pressure_still_starts_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """reactive post-compact hard 保留真实压力但不伪造 lifecycle failure。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    """

    policy = _reactive_policy()
    hard_pressure_tokens = int(
        policy.context_window_size * policy.hard_threshold_context_ratio
    )
    original_estimator = (
        engine_ingest_module.estimate_prepared_runner_call_candidate
    )

    def estimate_post_compact_hard(
        candidate: PreparedRunnerCallCandidate,
        sizing_policy: ContextBudgetPolicy,
    ) -> BudgetEstimate:
        """仅把 complete post-compact candidate 的真实估算推到 hard。

        :param candidate: recovery complete candidate。
        :param sizing_policy: recovery sizing policy。
        :returns: 保留 estimator contract、仅调整 token 压力的估算。
        """

        estimate = original_estimator(candidate, sizing_policy)
        return replace(
            estimate,
            estimated_input_tokens=estimate.hard_threshold_tokens,
        )

    monkeypatch.setattr(
        engine_ingest_module,
        "estimate_prepared_runner_call_candidate",
        estimate_post_compact_hard,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        wakeup = _WakeupSpy()

        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            wakeup_port=wakeup,
            context_budget_policy=policy,
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        ).ingest_async(
            _context_compaction_candidate(seeded, worker_event_index=152)
        )

        assert tuple(event.event_type for event in result.events)[-4:] == (
            "RUNNER_CALL_INPUT_ASSEMBLED",
            "CONTEXT_BUDGET_EVALUATED",
            "RUN_STARTED",
            "ATTEMPT_STARTED",
        )
        hot = parse_runner_call_hot_payload(_payload(result.events[-4]))
        manifest_json = store.transaction_runner.run_read(
            lambda transaction: sqlite_payload_object(
                transaction,
                payload_ref=hot.manifest_payload_ref,
                payload_digest=hot.manifest_digest,
                payload_label="reactive hard manifest",
            )
        )
        manifest = parse_runner_call_manifest(
            manifest_json,
            hot_payload=hot,
        )
        assert manifest.sizing_snapshot.sizing_stage is (
            ContextSizingStage.REACTIVE_POST_COMPACT
        )
        assert manifest.sizing_snapshot.conservative_input_tokens is not None
        assert (
            manifest.sizing_snapshot.conservative_input_tokens
            >= hard_pressure_tokens
        )
        budget_payload = parse_context_budget_evaluated_payload(
            _payload(result.events[-3])
        )
        assert budget_payload.estimate_method is (
            ContextEstimateMethod.CONSERVATIVE_FALLBACK
        )
        assert budget_payload.fallback_reason is (
            ContextSizingFallbackReason.ACCEPTED_COMPACT_INVALIDATED
        )
        assert _event_count(
            store.transaction_runner,
            CONTEXT_COMPACTION_FAILED,
        ) == 0
        assert _event_count(store.transaction_runner, "RUN_FAILED") == 0
        assert _event_count(store.transaction_runner, "RUN_LOST") == 0
        assert len(wakeup.dispatches) == 1


@pytest.mark.parametrize(
    "tamper_kind",
    tuple(_ReactiveSourceTamperKind),
)
@pytest.mark.asyncio
async def test_reactive_source_strict_load_failure_has_zero_start_and_wake(
    tmp_path: Path,
    tamper_kind: _ReactiveSourceTamperKind,
) -> None:
    """source durable contract 缺失或 mismatch 时 fail closed。

    :param tmp_path: pytest 临时目录。
    :param tamper_kind: effective config、manifest 或 candidate digest 篡改。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
            source_tool_schema=(
                _reactive_source_tool_schema()
                if tamper_kind
                is _ReactiveSourceTamperKind.TOOL_SNAPSHOT_MISSING
                else None
            ),
        )
        _tamper_reactive_source(
            store.transaction_runner,
            seeded=seeded,
            tamper_kind=tamper_kind,
        )
        wakeup = _WakeupSpy()
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            wakeup_port=wakeup,
            context_budget_policy=_reactive_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        )

        with pytest.raises(HostDurableError):
            await ingestor.ingest_async(
                _context_compaction_candidate(
                    seeded,
                    worker_event_index=160,
                )
            )

        assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 1
        assert _event_count(store.transaction_runner, "RUN_STARTED") == 1
        assert _attempt_count(store.transaction_runner, seeded.run_id) == 1
        assert _statuses(store.transaction_runner, seeded) == (
            RunStatus.RECOVERING,
            AttemptStatus.FAILED,
        )
        assert wakeup.dispatches == []


@pytest.mark.asyncio
async def test_reactive_duplicate_after_recovery_winner_does_not_repeat_wake(
    tmp_path: Path,
) -> None:
    """matching committed winner 已 start 时 duplicate 不再创建或 wake。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        wakeup = _WakeupSpy()
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            wakeup_port=wakeup,
            context_budget_policy=_reactive_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        )
        candidate = _context_compaction_candidate(
            seeded,
            worker_event_index=161,
        )

        first = await ingestor.ingest_async(candidate)
        duplicate = await ingestor.ingest_async(candidate)

        assert first.status is EngineIngestStatus.ACCEPTED
        assert duplicate.status is EngineIngestStatus.DUPLICATE
        assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 1
        assert _event_count(store.transaction_runner, "RUN_STARTED") == 2
        assert _attempt_count(store.transaction_runner, seeded.run_id) == 2
        assert len(wakeup.dispatches) == 1


@pytest.mark.asyncio
async def test_reactive_start_precondition_miss_rolls_back_candidate_and_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """recovery start precondition miss 回滚同事务 candidate/manifest。"""

    def reject_start(
        transaction: HostTransaction,
        event_log_store: EventLogStore,
        request: StartRecoveryRunInput,
    ) -> RunTransitionResult:
        """模拟 recovery transition 的 owner precondition miss。

        :param transaction: Host write transaction。
        :param event_log_store: EventLog primitive。
        :param request: recovery start input。
        :returns: ``INVALID_STATE`` transition result。
        """

        del transaction, event_log_store, request
        return RunTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=None,
            attempt=None,
            dispatch_record=None,
            run_event=None,
        )

    monkeypatch.setattr(
        engine_ingest_module,
        "start_recovery_run_with_starting_attempt_in_transaction",
        reject_start,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        descriptor_count_before = store.transaction_runner.run_read(
            lambda transaction: _table_row_count(
                transaction,
                TABLE_PAYLOAD_DESCRIPTORS,
            )
        )
        wakeup = _WakeupSpy()

        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            wakeup_port=wakeup,
            context_budget_policy=_reactive_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        ).ingest_async(
            _context_compaction_candidate(seeded, worker_event_index=162)
        )

        assert result.status is EngineIngestStatus.ACCEPTED
        assert result.events[-1].event_type == CONTEXT_COMPACTED
        assert _attempt_count(store.transaction_runner, seeded.run_id) == 1
        assert _event_count(store.transaction_runner, "RUN_STARTED") == 1
        assert _event_count(
            store.transaction_runner,
            "RUNNER_CALL_INPUT_ASSEMBLED",
        ) == 1
        assert _event_count(
            store.transaction_runner,
            CONTEXT_BUDGET_EVALUATED,
        ) == 0
        descriptor_count_after = store.transaction_runner.run_read(
            lambda transaction: _table_row_count(
                transaction,
                TABLE_PAYLOAD_DESCRIPTORS,
            )
        )
        assert descriptor_count_after == descriptor_count_before + 1
        assert wakeup.dispatches == []


@pytest.mark.asyncio
async def test_reactive_prepared_compaction_records_accepted_proposal_manifest(
    tmp_path: Path,
) -> None:
    """reactive accepted compact payload 携带 prepared proposal manifest 引用。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            context_budget_policy=_reactive_policy(),
            context_compactor=_PreparedManifestReactiveCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        ).ingest_async(_context_compaction_candidate(seeded, worker_event_index=40))

        compacted_rows = tuple(
            event for event in result.events if event.event_type == CONTEXT_COMPACTED
        )
        assert len(compacted_rows) == 1
        compacted_payload = _payload(compacted_rows[0])
        assert isinstance(
            compacted_payload["accepted_proposal_manifest_ref"], str
        )
        assert compacted_payload["accepted_proposal_manifest_ref"].startswith(
            "runner-call-manifest:"
        )
        assert isinstance(
            compacted_payload["accepted_proposal_manifest_digest"], str
        )
        assert (
            _event_count(
                store.transaction_runner,
                "RUNNER_CALL_INPUT_ASSEMBLED",
            )
            == 3
        )


@pytest.mark.asyncio
async def test_reactive_freezes_overflow_material_list_before_compaction(
    tmp_path: Path,
) -> None:
    """reactive pending record 保存冻结 ordinary material digest 与 refs。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            context_budget_policy=_reactive_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        ).ingest_async(_context_compaction_candidate(seeded, worker_event_index=47))

        requested = result.events[0]
        payload = _payload(requested)
        assert requested.event_type == CONTEXT_COMPACTION_REQUESTED
        assert payload["frozen_material_refs"] == ["event-input-ingest"]
        assert payload["frozen_material_list_digest"] != payload["estimator_digest"]


@pytest.mark.asyncio
async def test_reactive_compaction_calls_llm_outside_write_transaction(
    tmp_path: Path,
) -> None:
    """reactive compactor 外部调用不持有 Host write transaction。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        compactor = _TransactionReadableCompactor(store.transaction_runner)
        candidate = _context_compaction_candidate(seeded, worker_event_index=41)

        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            context_budget_policy=_reactive_policy(),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
        ).ingest_async(candidate)

        assert result.status is EngineIngestStatus.ACCEPTED
        assert compactor.calls == 1
        assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 1


@pytest.mark.asyncio
async def test_reactive_invalid_multiple_terminals_fail_closed_without_third_or_start(
    tmp_path: Path,
) -> None:
    """reactive caller 对 INVALID_MULTIPLE 抛稳定错误且不追加 durable 副作用。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: caller 追加第三 terminal、artifact 或 recovery start 时抛出。
    """

    artifact_root = tmp_path / "compact-artifacts"
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        wakeup = _WakeupSpy()
        descriptor_count_before = store.transaction_runner.run_read(
            lambda transaction: _table_row_count(
                transaction,
                TABLE_PAYLOAD_DESCRIPTORS,
            )
        )
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            wakeup_port=wakeup,
            context_budget_policy=_reactive_policy(),
            context_compactor=_InvalidMultipleReactiveCompactor(
                store.transaction_runner
            ),
            compact_artifact_root=artifact_root,
        )

        with pytest.raises(
            HostDurableError,
            match=COMPACTION_TERMINAL_INVALID_MULTIPLE_ERROR,
        ):
            await ingestor.ingest_async(
                _context_compaction_candidate(
                    seeded,
                    worker_event_index=162,
                )
            )

        assert _event_count(store.transaction_runner, CONTEXT_COMPACTION_FAILED) == 2
        assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 0
        assert _event_count(
            store.transaction_runner,
            CONTEXT_COMPACTION_ATTEMPT_REJECTED,
        ) == 0
        assert _event_count(store.transaction_runner, "RUN_STARTED") == 1
        assert _attempt_count(store.transaction_runner, seeded.run_id) == 1
        assert _event_count(store.transaction_runner, "RUN_FAILED") == 0
        assert wakeup.dispatches == []
        assert _compact_artifact_files(artifact_root) == ()
        descriptor_count_after = store.transaction_runner.run_read(
            lambda transaction: _table_row_count(
                transaction,
                TABLE_PAYLOAD_DESCRIPTORS,
            )
        )
        assert descriptor_count_after == descriptor_count_before


@pytest.mark.parametrize("winner_compacted", (True, False))
@pytest.mark.asyncio
async def test_reactive_same_pending_terminal_race_preserves_first_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    winner_compacted: bool,
) -> None:
    """同一 reactive pending 的相反结果并发只提交 first truth。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :param winner_compacted: 首个获准结果是否为 compacted。
    :returns: ``None``。
    :raises AssertionError: late loser 写 artifact/event/fallback/start 时抛出。
    """

    artifact_root = tmp_path / "compact-artifacts"
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        wakeup = _WakeupSpy()
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            wakeup_port=wakeup,
            context_budget_policy=_reactive_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=artifact_root,
        )
        candidate = _context_compaction_candidate(
            seeded,
            worker_event_index=163 if winner_compacted else 164,
        )
        pending = ingestor._ingest_before_reactive_compaction(candidate)
        assert isinstance(pending, engine_ingest_module._ReactiveCompactPending)
        entered_count = 0
        both_entered = asyncio.Event()
        releases = (asyncio.Event(), asyncio.Event())

        async def _competing_operation(
            *,
            request: CompactionRequest,
            compactor: ContextCompactor,
            first_attempt_number: int,
            max_attempt_number: int,
            cancellation_token: CancellationToken,
            pass_queue: tuple[CompactionRequest, ...] = (),
            compaction_operation_id: str | None = None,
            proposal_manifest_recorder: CompactorProposalManifestRecorder | None = None,
        ) -> CompactionOperationResult:
            """以 barrier 控制同 pending 两个相反 provider result 的返回顺序。

            :param request: reactive root request。
            :param compactor: 当前 compactor。
            :param first_attempt_number: frozen first attempt。
            :param max_attempt_number: frozen max attempt。
            :param cancellation_token: Host cancellation token。
            :param pass_queue: frozen reactive pass queue。
            :param compaction_operation_id: request event 同源 operation id。
            :param proposal_manifest_recorder: durable manifest recorder。
            :returns: 当前 contender 对应 accepted 或 failed result。
            :raises AssertionError: operation frozen identity 漂移时抛出。
            """

            nonlocal entered_count
            del pass_queue, proposal_manifest_recorder
            assert compactor is not None
            assert first_attempt_number == 1
            assert max_attempt_number == pending.policy.max_compaction_attempts_per_operation
            assert compaction_operation_id == pending.operation_id
            contender_index = entered_count
            entered_count += 1
            if entered_count == 2:
                both_entered.set()
            await releases[contender_index].wait()
            contender_compacted = (
                winner_compacted
                if contender_index == 0
                else not winner_compacted
            )
            if contender_compacted:
                accepted_candidate = await FakeContextCompactor().compact(
                    request,
                    cancellation_token,
                )
                return CompactionOperationResult(
                    accepted_candidate=accepted_candidate,
                    quality_result=CompactQualityCheckResultVNext(
                        accepted=True,
                        rejection_reasons=(),
                    ),
                    rejected_attempts=(),
                    failure_reason=None,
                    budget_after_attempted_compact=(
                        pending.estimate.estimated_input_tokens
                    ),
                    accepted_attempt_number=1,
                )
            return CompactionOperationResult(
                accepted_candidate=None,
                quality_result=None,
                rejected_attempts=(),
                failure_reason="contending_provider_failure",
                budget_after_attempted_compact=None,
                accepted_attempt_number=None,
            )

        monkeypatch.setattr(
            engine_ingest_module,
            "run_compaction_operation",
            _competing_operation,
        )
        first = asyncio.create_task(ingestor._execute_reactive_compaction(pending))
        late = asyncio.create_task(ingestor._execute_reactive_compaction(pending))
        await asyncio.wait_for(both_entered.wait(), timeout=1)

        releases[0].set()
        winner = await first
        assert isinstance(winner, engine_ingest_module._ReactiveRecoveryAccepted)
        ingestor._complete_reactive_recovery(winner)
        first_terminal_type = (
            CONTEXT_COMPACTED
            if winner_compacted
            else CONTEXT_COMPACTION_FAILED
        )
        first_terminal = _latest_event(
            store.transaction_runner,
            first_terminal_type,
        )
        cursor_after_winner = _event_log_cursor(store.transaction_runner)
        descriptor_count_after_winner = store.transaction_runner.run_read(
            lambda transaction: _table_row_count(
                transaction,
                TABLE_PAYLOAD_DESCRIPTORS,
            )
        )
        artifact_files_after_winner = _compact_artifact_files(artifact_root)
        run_started_after_winner = _event_count(
            store.transaction_runner,
            "RUN_STARTED",
        )
        attempt_count_after_winner = _attempt_count(
            store.transaction_runner,
            seeded.run_id,
        )

        releases[1].set()
        loser = await late

        assert isinstance(loser, EngineIngestResult)
        assert _events_after_cursor(
            store.transaction_runner,
            cursor_after_winner,
        ) == ()
        assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == (
            1 if winner_compacted else 0
        )
        assert _event_count(
            store.transaction_runner,
            CONTEXT_COMPACTION_FAILED,
        ) == (0 if winner_compacted else 1)
        assert _event_count(
            store.transaction_runner,
            CONTEXT_COMPACTION_ATTEMPT_REJECTED,
        ) == 0
        assert _latest_event(
            store.transaction_runner,
            first_terminal_type,
        ).event_id == first_terminal.event_id
        assert _compact_artifact_files(artifact_root) == artifact_files_after_winner
        assert store.transaction_runner.run_read(
            lambda transaction: _table_row_count(
                transaction,
                TABLE_PAYLOAD_DESCRIPTORS,
            )
        ) == descriptor_count_after_winner
        assert _event_count(
            store.transaction_runner,
            "RUN_STARTED",
        ) == run_started_after_winner
        assert _attempt_count(
            store.transaction_runner,
            seeded.run_id,
        ) == attempt_count_after_winner
        assert run_started_after_winner == 2
        assert attempt_count_after_winner == 2
        assert len(wakeup.dispatches) == 1


@pytest.mark.asyncio
async def test_reactive_compaction_gate_consumes_terminal_attempt_status_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """reactive compact 返回后的 gate 直接消费 Attempt terminal status owner。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: reactive gate 未消费 terminal status owner 时抛出。
    """

    owner_predicate = engine_ingest_module.is_terminal_attempt_status
    observed_statuses: list[AttemptStatus] = []

    def status_gate(status: AttemptStatus) -> bool:
        """记录 gate 输入并让 FAILED status 明确阻止 compact commit。

        :param status: reactive gate 读取的 Attempt status。
        :returns: 非 FAILED status 使用真实 owner predicate；FAILED 返回 ``False``。
        :raises: 无主动抛出。
        """

        observed_statuses.append(status)
        if status is AttemptStatus.FAILED:
            return False
        return owner_predicate(status)

    monkeypatch.setattr(
        engine_ingest_module,
        "is_terminal_attempt_status",
        status_gate,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        compactor = _TransactionReadableCompactor(store.transaction_runner)

        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            context_budget_policy=_reactive_policy(),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
        ).ingest_async(
            _context_compaction_candidate(seeded, worker_event_index=141)
        )

        assert result.status is EngineIngestStatus.ACCEPTED
        assert compactor.calls == 1
        assert AttemptStatus.FAILED in observed_statuses
        assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 0
        assert _attempt_count(store.transaction_runner, seeded.run_id) == 1
        assert _statuses(store.transaction_runner, seeded) == (
            RunStatus.RECOVERING,
            AttemptStatus.FAILED,
        )


@pytest.mark.asyncio
async def test_reactive_compaction_rejects_stale_input_sequence(
    tmp_path: Path,
) -> None:
    """reactive compact 返回后 input sequence 变化时拒绝旧 snapshot 结果。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        compactor = _InputSequenceAdvancingCompactor(store.transaction_runner)
        candidate = _context_compaction_candidate(seeded, worker_event_index=43)

        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            context_budget_policy=_reactive_policy(),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
        ).ingest_async(candidate)

        assert result.status is EngineIngestStatus.ACCEPTED
        assert result.stop_worker_stream is True
        assert compactor.calls == 1
        assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 0
        assert _event_count(store.transaction_runner, CONTEXT_COMPACTION_FAILED) == 1
        assert _attempt_count(store.transaction_runner, seeded.run_id) == 1
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status is RunStatus.RECOVERING
        assert attempt_status is AttemptStatus.FAILED
        stale_failed = _latest_event(
            store.transaction_runner, CONTEXT_COMPACTION_FAILED
        )
        payload = _payload(stale_failed)
        assert payload["failure_reason"] == "stale_compaction_result"
        assert_failed_payload_no_fallback(
            payload,
            expected_operation_id=result.events[0].event_id,
            expected_attempt_count=0,
            expected_retry_repair_budget_exhausted=False,
        )


@pytest.mark.asyncio
async def test_reactive_compaction_attempt_rejected_uses_request_event_operation_id(
    tmp_path: Path,
) -> None:
    """reactive attempt rejected 使用 request fact event id 作为 operation anchor。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        candidate = _context_compaction_candidate(seeded, worker_event_index=42)

        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            context_budget_policy=context_budget_policy_from_threshold_tokens(
                context_window_size=100,
                soft_threshold_tokens=45,
                hard_threshold_tokens=80,
                max_compaction_attempts_per_operation=1,
                policy_ref=_REACTIVE_POLICY_REF,
            ),
            context_compactor=_RaisingCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        ).ingest_async(candidate)

        rejected_rows = tuple(
            event
            for event in result.events
            if event.event_type == CONTEXT_COMPACTION_ATTEMPT_REJECTED
        )
        assert len(rejected_rows) == 1
        rejected_payload = _payload(rejected_rows[0])
        requested_payload = _payload(result.events[0])
        assert result.events[0].event_type == CONTEXT_COMPACTION_REQUESTED
        assert rejected_payload["operation_id"] == result.events[0].event_id
        assert requested_payload["estimator_digest"] != rejected_payload["operation_id"]


@pytest.mark.asyncio
async def test_reactive_prepared_rejected_attempt_records_proposal_manifest(
    tmp_path: Path,
) -> None:
    """reactive rejected attempt payload 携带 prepared proposal manifest 引用。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            context_budget_policy=context_budget_policy_from_threshold_tokens(
                context_window_size=100,
                soft_threshold_tokens=45,
                hard_threshold_tokens=80,
                max_compaction_attempts_per_operation=1,
                policy_ref=_REACTIVE_POLICY_REF,
            ),
            context_compactor=_PreparedManifestReactiveCompactor(fail_run=True),
            compact_artifact_root=tmp_path / "compact-artifacts",
        ).ingest_async(_context_compaction_candidate(seeded, worker_event_index=39))

        rejected_rows = tuple(
            event
            for event in result.events
            if event.event_type == CONTEXT_COMPACTION_ATTEMPT_REJECTED
        )
        assert len(rejected_rows) == 1
        rejected_payload = _payload(rejected_rows[0])
        assert isinstance(rejected_payload["proposal_manifest_ref"], str)
        assert rejected_payload["proposal_manifest_ref"].startswith(
            "runner-call-manifest:"
        )
        assert isinstance(rejected_payload["proposal_manifest_digest"], str)
        assert (
            _event_count(
                store.transaction_runner,
                "RUNNER_CALL_INPUT_ASSEMBLED",
            )
            == 3
        )


def test_context_compaction_requested_stale_identity_is_rejected(
    tmp_path: Path,
) -> None:
    """attempt_id + execution_id 不匹配时拒绝 reactive compact。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        wrong_seeded = _SeededRun(
            session_id=seeded.session_id,
            run_id=seeded.run_id,
            attempt_id=seeded.attempt_id,
            execution_id="execution-other",
            dispatch_record_id=seeded.dispatch_record_id,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            context_budget_policy=_reactive_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        ).ingest(
            _candidate(
                wrong_seeded,
                worker_event_index=41,
                data=ContextCompactionRequestedData(
                    iteration_id="iter-1",
                    budget_state=None,
                    reason="provider_overflow",
                    provider_request_id="req-overflow",
                ),
                event_type=EngineEventType.CONTEXT_COMPACTION_REQUESTED,
            )
        )

        assert result.status == EngineIngestStatus.REJECTED
        assert _payload(result.events[0])["reason"] == "stale_execution_id"
        assert _event_count(store.transaction_runner, CONTEXT_COMPACTION_REQUESTED) == 0
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.RUNNING
        assert attempt_status == AttemptStatus.RUNNING


@pytest.mark.asyncio
async def test_reactive_compactor_missing_fallback_dispatches_recovery_attempt(
    tmp_path: Path,
) -> None:
    """reactive compact final failure 预算通过时 fallback 创建 recovery Attempt。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            context_budget_policy=_reactive_policy(),
        ).ingest_async(
            _context_compaction_candidate(seeded, worker_event_index=42)
        )

        assert tuple(event.event_type for event in result.events) == (
            CONTEXT_COMPACTION_REQUESTED,
            "ATTEMPT_FAILED",
                "RUN_RECOVERING",
                CONTEXT_COMPACTION_FAILED,
                "RUNNER_CALL_INPUT_ASSEMBLED",
                "CONTEXT_BUDGET_EVALUATED",
                "RUN_STARTED",
                "ATTEMPT_STARTED",
            )
        assert result.terminal_closeout is False
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.RUNNING
        assert attempt_status == AttemptStatus.FAILED
        assert _event_count(store.transaction_runner, "RUN_LOST") == 0
        assert _event_count(store.transaction_runner, "RUN_FAILED") == 0
        assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 0
        assert _attempt_count(store.transaction_runner, seeded.run_id) == 2
        assert _current_attempt_id(store.transaction_runner, seeded.run_id) != (
            seeded.attempt_id
        )
        failed_payload = _payload(result.events[3])
        assert failed_payload["operation_id"] == result.events[0].event_id
        assert failed_payload["fallback_action"] == "dispatch"
        assert failed_payload["fallback_policy_decision"] == (
            "deterministic_recent_window"
        )
        assert isinstance(failed_payload["fallback_input_window"], Mapping)
        assert failed_payload["fallback_input_window"]["current_input_ref"] == (
            "event-input-ingest"
        )
        assert isinstance(failed_payload["fallback_budget_result"], Mapping)
        assert failed_payload["fallback_budget_result"]["status"] == (
            "within_hard_budget"
        )


@pytest.mark.asyncio
async def test_reactive_fallback_over_budget_fails_closed_without_lost(
    tmp_path: Path,
) -> None:
    """recovery fail commit 后向 terminal port 交付 exact promotion notice。"""

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            display_text="overflow " * 80,
            record_source_candidate=True,
        )
        terminal_port = _CommittedTerminalPostCommitPort(
            db_path=options.db_path,
            transaction_runner=store.transaction_runner,
            expected_session_id=seeded.session_id,
            expected_run_id=seeded.run_id,
        )
        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=terminal_port,
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            context_budget_policy=_reactive_policy(),
        ).ingest_async(
            _context_compaction_candidate(seeded, worker_event_index=42)
        )

        assert tuple(event.event_type for event in result.events) == (
            CONTEXT_COMPACTION_REQUESTED,
            "ATTEMPT_FAILED",
            "RUN_RECOVERING",
            CONTEXT_COMPACTION_FAILED,
            "RUN_FAILED",
        )
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.FAILED
        assert attempt_status == AttemptStatus.FAILED
        assert _event_count(store.transaction_runner, "RUN_LOST") == 0
        assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 0
        assert _attempt_count(store.transaction_runner, seeded.run_id) == 1
        failed_payload = _payload(result.events[3])
        assert failed_payload["operation_id"] == result.events[0].event_id
        assert failed_payload["fallback_action"] == "fail_closed"
        assert failed_payload["fallback_policy_decision"] == (
            "deterministic_recent_window"
        )
        assert isinstance(failed_payload["fallback_budget_result"], Mapping)
        assert failed_payload["fallback_budget_result"]["status"] == "over_hard_budget"
        assert len(terminal_port.observations) == 1
        observation = terminal_port.observations[0]
        assert result.terminal_notice is observation.notice
        assert observation.notice.session_id == seeded.session_id
        assert observation.notice.wake_queue_promotion is True
        assert observation.run.status is RunStatus.FAILED
        assert observation.run.run_id == seeded.run_id
        assert observation.run_event == result.events[-1]
        assert (
            observation.notice.terminal_event_sequence
            == observation.run.terminal_event_sequence
            == observation.run_event.event_sequence
        )


@pytest.mark.parametrize(
    "mutation_status",
    (StateMutationStatus.CAS_LOST, StateMutationStatus.INVALID_STATE),
)
@pytest.mark.asyncio
async def test_reactive_fail_closed_propagates_recovering_fail_rejection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation_status: StateMutationStatus,
) -> None:
    """recovering Run fail CAS-lost/rejected 时不得伪造 terminal notice。"""

    def reject_fail_recovering_run(
        transaction: HostTransaction,
        event_log_store: EventLogStore,
        request: FailRecoveringRunInput,
    ) -> RunTransitionResult:
        """模拟 fail_recovering_run 的状态前置条件失败。

        :param transaction: Host transaction。
        :param event_log_store: EventLog store。
        :param request: fail recovering run 输入。
        :returns: 参数指定的非 UPDATED transition result。
        :raises: 无主动抛出。
        """

        del transaction, event_log_store, request
        return RunTransitionResult(
            status=mutation_status,
            run=None,
            attempt=None,
            dispatch_record=None,
            run_event=None,
        )

    monkeypatch.setattr(
        engine_ingest_module,
        "fail_recovering_run_in_transaction",
        reject_fail_recovering_run,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            display_text="overflow " * 80,
            record_source_candidate=True,
        )
        terminal_port = _RecordingTerminalPostCommitPort()

        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=terminal_port,
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            context_budget_policy=_reactive_policy(),
        ).ingest_async(
            _context_compaction_candidate(seeded, worker_event_index=53)
        )

        assert result.status is EngineIngestStatus.REJECTED
        assert result.terminal_closeout is False
        assert result.terminal_notice is None
        assert terminal_port.notices == []
        assert result.reason == "recovering_run_failed_precondition_failed"
        assert tuple(event.event_type for event in result.events) == (
            CONTEXT_COMPACTION_REQUESTED,
            "ATTEMPT_FAILED",
            "RUN_RECOVERING",
            CONTEXT_COMPACTION_FAILED,
        )
        assert _event_count(store.transaction_runner, "RUN_FAILED") == 0


@pytest.mark.asyncio
async def test_old_attempt_run_failed_after_recovery_is_stale_diagnostic(
    tmp_path: Path,
) -> None:
    """recovery start 后旧 Attempt 的 recoverable run_failed 不创建第二个 Attempt。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            context_budget_policy=_reactive_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        )
        first = await ingestor.ingest_async(
            _context_compaction_candidate(seeded, worker_event_index=43)
        )
        assert first.status == EngineIngestStatus.ACCEPTED

        stale = ingestor.ingest(
            _candidate(
                seeded,
                worker_event_index=44,
                data=RunFailedData(
                    error_code=EngineRunErrorCode.CONTEXT_COMPACTION_REQUIRED,
                    message="provider closed old attempt",
                    provider_request_id="req-overflow",
                    recoverable=True,
                ),
                event_type=EngineEventType.RUN_FAILED,
            )
        )

        assert stale.status == EngineIngestStatus.REJECTED
        assert _payload(stale.events[0])["reason"] == "stale_execution_id"
        assert _attempt_count(store.transaction_runner, seeded.run_id) == 2
        current_attempt = _current_attempt_id(store.transaction_runner, seeded.run_id)
        assert current_attempt != seeded.attempt_id
        assert _attempt_status(store.transaction_runner, current_attempt) == (
            AttemptStatus.STARTING
        )


def test_old_steered_attempt_event_is_rejected_and_current_attempt_accepts(
    tmp_path: Path,
) -> None:
    """steer 后旧 Attempt 的 EngineEvent 不得污染当前 Run EventLog。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        current = _steer_to_new_running_attempt(store.transaction_runner, seeded)
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        )

        stale = ingestor.ingest(
            _candidate(
                seeded,
                worker_event_index=51,
                data=ContentCompleteData(
                    iteration_id="iter-stale",
                    content="old",
                    reasoning_content=None,
                ),
                event_type=EngineEventType.CONTENT_COMPLETED,
            )
        )
        accepted = ingestor.ingest(
            _candidate(
                current,
                worker_event_index=1,
                data=ContentCompleteData(
                    iteration_id="iter-current",
                    content="new",
                    reasoning_content=None,
                ),
                event_type=EngineEventType.CONTENT_COMPLETED,
            )
        )

        assert stale.status == EngineIngestStatus.REJECTED
        assert _payload(stale.events[0])["reason"] == "stale_execution_id"
        assert accepted.status == EngineIngestStatus.ACCEPTED
        assert accepted.events[0].attempt_id == current.attempt_id
        assert _payload(accepted.events[0])["has_content"] is True


def test_stale_transient_delta_is_rejected_before_no_row_short_circuit(
    tmp_path: Path,
) -> None:
    """旧 Attempt 的 transient delta 仍先经过 durable identity governance。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        _steer_to_new_running_attempt(store.transaction_runner, seeded)
        publisher = RecordingTransientDeltaPublisher()
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=publisher,
        )

        result = ingestor.ingest(
            _candidate(
                seeded,
                worker_event_index=52,
                data=ContentDeltaData(iteration_id="iter-stale", delta="old"),
                event_type=EngineEventType.CONTENT_DELTA,
            )
        )

        assert result.status == EngineIngestStatus.REJECTED
        assert result.events[0].event_type == "ENGINE_EVENT_REJECTED"
        assert _payload(result.events[0])["reason"] == "stale_execution_id"
        assert _event_count(store.transaction_runner, "CONTENT_DELTA") == 0
        assert publisher.candidates == []


@pytest.mark.asyncio
async def test_reactive_compact_count_limit_fails_closed_without_second_attempt(
    tmp_path: Path,
) -> None:
    """配置为一次 reactive 时，已有 request 会触发失败收口。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        _append_reactive_requested_fact(
            store.transaction_runner,
            seeded=seeded,
            event_id="event-existing-reactive-request",
            corrupted=False,
        )

        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            context_budget_policy=_reactive_policy(max_reactive_compactions_per_run=1),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        ).ingest_async(_context_compaction_candidate(seeded, worker_event_index=45))

        assert CONTEXT_COMPACTION_REQUESTED not in (
            event.event_type for event in result.events
        )
        assert _attempt_count(store.transaction_runner, seeded.run_id) == 1
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.FAILED
        assert attempt_status == AttemptStatus.FAILED
        failed = _latest_event(store.transaction_runner, CONTEXT_COMPACTION_FAILED)
        payload = _payload(failed)
        assert payload["failure_reason"] == "reactive_compact_limit_reached"
        assert_failed_payload_no_fallback(
            payload,
            expected_operation_id=None,
            expected_attempt_count=0,
            expected_retry_repair_budget_exhausted=False,
        )


@pytest.mark.asyncio
async def test_reactive_repeated_overflow_respects_max_reactive_compactions_per_run(
    tmp_path: Path,
) -> None:
    """重复 overflow 达到 reactive 上限后 fail closed 且不无限 retry。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        _append_reactive_requested_fact(
            store.transaction_runner,
            seeded=seeded,
            event_id="event-existing-reactive-request-repeat",
            corrupted=False,
        )

        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            context_budget_policy=_reactive_policy(max_reactive_compactions_per_run=1),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        ).ingest_async(_context_compaction_candidate(seeded, worker_event_index=48))

        assert result.terminal_closeout is True
        assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 0
        assert _event_count(store.transaction_runner, "RUN_FAILED") == 1
        assert _event_count(store.transaction_runner, "RUN_LOST") == 0
        failed = _latest_event(store.transaction_runner, CONTEXT_COMPACTION_FAILED)
        assert_failed_payload_no_fallback(
            _payload(failed),
            expected_operation_id=None,
            expected_attempt_count=0,
            expected_retry_repair_budget_exhausted=False,
        )


@pytest.mark.asyncio
async def test_reactive_compact_count_allows_second_operation(
    tmp_path: Path,
) -> None:
    """默认两次 reactive 上限允许第二条 compact request。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 第二次 reactive compact 被错误阻断时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        _append_reactive_requested_fact(
            store.transaction_runner,
            seeded=seeded,
            event_id="event-existing-reactive-request",
            corrupted=False,
        )

        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            context_budget_policy=_reactive_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        ).ingest_async(_context_compaction_candidate(seeded, worker_event_index=45))

        assert result.status == EngineIngestStatus.ACCEPTED
        assert _attempt_count(store.transaction_runner, seeded.run_id) == 2
        assert _event_count(store.transaction_runner, CONTEXT_COMPACTION_REQUESTED) == 2
        assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 1
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.RUNNING
        assert attempt_status == AttemptStatus.FAILED


@pytest.mark.asyncio
async def test_reactive_compact_corrupt_count_fact_fails_closed(
    tmp_path: Path,
) -> None:
    """reactive compact count fact 损坏时 fail closed 且不创建第二个 Attempt。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        _append_reactive_requested_fact(
            store.transaction_runner,
            seeded=seeded,
            event_id="event-corrupt-reactive-request",
            corrupted=True,
        )

        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            context_budget_policy=_reactive_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        ).ingest_async(_context_compaction_candidate(seeded, worker_event_index=46))

        assert result.status == EngineIngestStatus.ACCEPTED
        assert _attempt_count(store.transaction_runner, seeded.run_id) == 1
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.FAILED
        assert attempt_status == AttemptStatus.FAILED
        failed = _latest_event(store.transaction_runner, CONTEXT_COMPACTION_FAILED)
        payload = _payload(failed)
        assert payload["failure_reason"] == "reactive_compact_count_unreadable"
        assert_failed_payload_no_fallback(
            payload,
            expected_operation_id=None,
            expected_attempt_count=0,
            expected_retry_repair_budget_exhausted=False,
        )


def test_run_suspended_only_writes_diagnostic_and_duplicate_is_idempotent(
    tmp_path: Path,
) -> None:
    """run_suspended 只写 diagnostic，不创建 wait state 或失败收口。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _candidate(
            seeded,
            worker_event_index=5,
            data=RunSuspendedData(
                reason="tool_awaiting",
                resume_hint=None,
                accepted_records=(_accepted_tool_record(),),
                awaiting_records=(_awaiting_tool_record(),),
            ),
            event_type=EngineEventType.RUN_SUSPENDED,
        )
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        )

        first = ingestor.ingest(candidate)
        second = ingestor.ingest(candidate)

        assert first.status == EngineIngestStatus.ACCEPTED
        assert second.status == EngineIngestStatus.DUPLICATE
        assert first.stop_worker_stream is False
        assert second.stop_worker_stream is False
        assert [event.event_type for event in first.events] == [
            "ENGINE_EVENT_DIAGNOSTIC",
        ]
        assert _payload(first.events[0])["run_status"] == "running"
        assert _event_count(store.transaction_runner, "RUN_FAILED") == 0
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.RUNNING
        assert attempt_status == AttemptStatus.RUNNING


def test_tool_awaiting_only_writes_diagnostic_and_duplicate_is_idempotent(
    tmp_path: Path,
) -> None:
    """tool_awaiting 只写 diagnostic，不创建 wait state 或失败收口。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _candidate(
            seeded,
            worker_event_index=6,
            data=ToolAwaitingData(
                iteration_id="iter-await",
                record=_awaiting_tool_record(),
            ),
            event_type=EngineEventType.TOOL_AWAITING,
        )
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        )

        first = ingestor.ingest(candidate)
        second = ingestor.ingest(candidate)

        assert first.status == EngineIngestStatus.ACCEPTED
        assert second.status == EngineIngestStatus.DUPLICATE
        assert [event.event_type for event in first.events] == [
            "ENGINE_EVENT_DIAGNOSTIC",
        ]
        assert _event_count(store.transaction_runner, "RUN_FAILED") == 0
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.RUNNING
        assert attempt_status == AttemptStatus.RUNNING


def test_tool_awaiting_confirms_only_matching_host_accepted_wait_refs(
    tmp_path: Path,
) -> None:
    """tool_awaiting 只有匹配 Host accepted wait refs 时才记为确认。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        accept_result = DefaultHostToolAwaitingAcceptPort(
            transaction_runner=store.transaction_runner
        ).accept_tool_awaiting(_awaiting_accept_candidate(seeded))
        assert isinstance(accept_result, ToolAwaitingAcceptedAck)
        candidate = _candidate(
            seeded,
            worker_event_index=20,
            data=ToolAwaitingData(
                iteration_id="iter-tool",
                record=_awaiting_tool_record(),
            ),
            event_type=EngineEventType.TOOL_AWAITING,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        assert result.reason == "waiting_event_confirmation"
        assert result.stop_worker_stream is True
        payload = _payload(result.events[0])
        assert payload["waiting_confirmation_accepted"] is True
        assert payload["waiting_confirmation_mismatch_reason"] is None
        assert payload["wait_id"] == accept_result.wait_id
        assert _canonical_tool_event_count(store.transaction_runner) == 2
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.WAITING
        assert attempt_status == AttemptStatus.SUSPENDED


def test_run_suspended_confirms_only_matching_host_accepted_wait_refs(
    tmp_path: Path,
) -> None:
    """run_suspended 只有匹配 Host accepted wait refs 时才记为确认。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        accept_result = DefaultHostToolAwaitingAcceptPort(
            transaction_runner=store.transaction_runner
        ).accept_tool_awaiting(_awaiting_accept_candidate(seeded))
        assert isinstance(accept_result, ToolAwaitingAcceptedAck)
        candidate = _candidate(
            seeded,
            worker_event_index=21,
            data=RunSuspendedData(
                reason="tool_awaiting",
                resume_hint=None,
                accepted_records=(),
                awaiting_records=(_awaiting_tool_record(),),
            ),
            event_type=EngineEventType.RUN_SUSPENDED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        assert result.reason == "waiting_event_confirmation"
        payload = _payload(result.events[0])
        assert payload["waiting_confirmation_accepted"] is True
        assert payload["wait_id"] == accept_result.wait_id
        assert _event_count(store.transaction_runner, "ATTEMPT_SUSPENDED") == 1
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.WAITING
        assert attempt_status == AttemptStatus.SUSPENDED


def test_tool_awaiting_rejects_mismatched_engine_record_without_state_change(
    tmp_path: Path,
) -> None:
    """Engine awaiting record 不匹配 wait record 时只能写未确认 diagnostic。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        accept_result = DefaultHostToolAwaitingAcceptPort(
            transaction_runner=store.transaction_runner
        ).accept_tool_awaiting(_awaiting_accept_candidate(seeded))
        assert isinstance(accept_result, ToolAwaitingAcceptedAck)
        candidate = _candidate(
            seeded,
            worker_event_index=22,
            data=ToolAwaitingData(
                iteration_id="iter-tool",
                record=_awaiting_tool_record(
                    await_spec=ToolAwaitSpec(
                        await_kind=ToolAwaitKind.EXTERNAL_JOB,
                        deadline=None,
                        resume_token="wrong-resume-token",
                    )
                ),
            ),
            event_type=EngineEventType.TOOL_AWAITING,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        assert result.reason == "waiting_event_without_host_accepted_refs"
        payload = _payload(result.events[0])
        assert payload["waiting_confirmation_accepted"] is False
        assert payload["waiting_confirmation_mismatch_reason"] == "awaiting_spec_mismatch"
        assert payload["wait_id"] == accept_result.wait_id
        assert _canonical_tool_event_count(store.transaction_runner) == 2
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.WAITING
        assert attempt_status == AttemptStatus.SUSPENDED


def test_waiting_confirmation_wrong_attempt_identity_is_rejected(
    tmp_path: Path,
) -> None:
    """错 Attempt identity 的 waiting confirmation 不读取其它 Attempt 的 wait refs。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        accept_result = DefaultHostToolAwaitingAcceptPort(
            transaction_runner=store.transaction_runner
        ).accept_tool_awaiting(_awaiting_accept_candidate(seeded))
        assert isinstance(accept_result, ToolAwaitingAcceptedAck)
        wrong_attempt = _SeededRun(
            session_id=seeded.session_id,
            run_id=seeded.run_id,
            attempt_id="attempt-wrong",
            execution_id=seeded.execution_id,
            dispatch_record_id=seeded.dispatch_record_id,
        )
        candidate = _candidate(
            wrong_attempt,
            worker_event_index=23,
            data=ToolAwaitingData(
                iteration_id="iter-tool",
                record=_awaiting_tool_record(),
            ),
            event_type=EngineEventType.TOOL_AWAITING,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.REJECTED
        assert result.reason == "stale_execution_id"
        assert _payload(result.events[0])["reason"] == "stale_execution_id"
        assert _canonical_tool_event_count(store.transaction_runner) == 2
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.WAITING
        assert attempt_status == AttemptStatus.SUSPENDED


def test_waiting_confirmation_wrong_execution_identity_is_rejected(
    tmp_path: Path,
) -> None:
    """错 execution identity 的 waiting confirmation 不确认 Host wait refs。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        accept_result = DefaultHostToolAwaitingAcceptPort(
            transaction_runner=store.transaction_runner
        ).accept_tool_awaiting(_awaiting_accept_candidate(seeded))
        assert isinstance(accept_result, ToolAwaitingAcceptedAck)
        wrong_execution = _SeededRun(
            session_id=seeded.session_id,
            run_id=seeded.run_id,
            attempt_id=seeded.attempt_id,
            execution_id="execution-wrong",
            dispatch_record_id=seeded.dispatch_record_id,
        )
        candidate = _candidate(
            wrong_execution,
            worker_event_index=24,
            data=ToolAwaitingData(
                iteration_id="iter-tool",
                record=_awaiting_tool_record(),
            ),
            event_type=EngineEventType.TOOL_AWAITING,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.REJECTED
        assert result.reason == "stale_execution_id"
        assert _event_count(store.transaction_runner, "ENGINE_EVENT_REJECTED") == 1
        assert _canonical_tool_event_count(store.transaction_runner) == 2
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.WAITING
        assert attempt_status == AttemptStatus.SUSPENDED


def test_old_attempt_late_waiting_confirmation_is_rejected_after_resolve(
    tmp_path: Path,
) -> None:
    """旧 Attempt 在 wait resolved 后的 late waiting confirmation 只能被拒绝。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
        )
        accept_result = DefaultHostToolAwaitingAcceptPort(
            transaction_runner=store.transaction_runner
        ).accept_tool_awaiting(_awaiting_accept_candidate(seeded))
        assert isinstance(accept_result, ToolAwaitingAcceptedAck)
        resolved = DefaultHostResolveWaitService(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            event_log_store=EventLogStore(),
            idempotency_store=IdempotencyStore(),
            payload_store=PayloadStore(),
            memory_projection_policy=default_memory_projection_policy(),
        ).resolve_wait(
            accept_result.wait_id,
            _resolve_wait_completed_request("resolve-old-attempt"),
        )
        assert resolved.run.status == RunStatus.RUNNING
        candidate = _candidate(
            seeded,
            worker_event_index=25,
            data=ToolAwaitingData(
                iteration_id="iter-tool",
                record=_awaiting_tool_record(),
            ),
            event_type=EngineEventType.TOOL_AWAITING,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.REJECTED
        assert result.reason == "stale_execution_id"
        assert _payload(result.events[0])["reason"] == "stale_execution_id"
        assert _canonical_tool_event_count(store.transaction_runner) == 3


def test_usage_reported_is_projection_signal_without_state_change(
    tmp_path: Path,
) -> None:
    """usage_reported 只写 projection_signal，不改 Run / Attempt 状态。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        role_digest = runner_role_sequence_digest(("system", "user"))
        _append_prepared_runner_call_manifest(
            store.transaction_runner,
            seeded,
            event_id="event-prepared-runner-call-usage",
            runner_call_index=0,
            runner_call_kind="initial_user_dispatch",
            runner_call_trigger_reason="initial_user_input",
            message_count=2,
            role_sequence_digest=role_digest,
        )
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            context_budget_policy=_reactive_policy(),
        )
        link_result = ingestor.ingest(
            _candidate(
                seeded,
                worker_event_index=7,
                data=IterationStartedData(
                    iteration_id="iter-usage",
                    iteration_index=0,
                    message_count=2,
                    role_sequence_digest=role_digest,
                    runner_input_serializer_schema_version=(
                        RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
                    ),
                ),
                event_type=EngineEventType.ITERATION_STARTED,
            )
        )
        assert link_result.status == EngineIngestStatus.ACCEPTED
        candidate = _candidate(
            seeded,
            worker_event_index=8,
            data=UsageReportedData(
                iteration_id="iter-usage",
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
                provider_request_id="req-usage",
            ),
            event_type=EngineEventType.USAGE_REPORTED,
        )

        result = ingestor.ingest(candidate)

        assert result.events[0].event_class == EventClass.PROJECTION_SIGNAL
        assert result.events[0].event_type == "USAGE_REPORTED"
        payload = _payload(result.events[0])
        assert payload["session_id"] == seeded.session_id
        assert payload["run_id"] == seeded.run_id
        assert payload["attempt_id"] == seeded.attempt_id
        assert payload["execution_id"] == seeded.execution_id
        assert payload["iteration_id"] == "iter-usage"
        assert payload["prompt_tokens"] == 10
        assert payload["completion_tokens"] == 20
        assert payload["total_tokens"] == 30
        assert payload["provider_request_id"] == "req-usage"
        assert payload["policy_ref"] == "policy-test"
        assert isinstance(payload["estimator_digest"], str)
        assert payload["estimated_input_tokens"] == 128
        assert payload["usage_observation_status"] == "observed"
        assert isinstance(payload["usage_observation_digest"], str)
        assert payload["prompt_token_delta"] == -118
        pairing = payload["runner_call_pairing"]
        assert isinstance(pairing, Mapping)
        assert pairing["status"] == "complete"
        assert pairing["reason"] is None
        assert pairing["manifest_event_id"] == (
            "event-prepared-runner-call-usage"
        )
        assert isinstance(pairing["observation_digest"], str)
        context_pressure = payload["context_pressure"]
        assert isinstance(context_pressure, Mapping)
        pressure = cast(Mapping[str, JsonValue], context_pressure)
        assert pressure["schema_version"] == 1
        assert pressure["signal_source"] == "USAGE_REPORTED"
        assert pressure["status"] == "observed"
        assert pressure["policy_ref"] == "policy-test"
        assert pressure["estimator_digest"] == payload["estimator_digest"]
        assert pressure["estimated_input_tokens"] == 128
        assert pressure["input_budget_tokens"] is None
        assert pressure["soft_threshold_tokens"] is None
        assert pressure["hard_threshold_tokens"] is None
        assert pressure["soft_threshold_exceeded"] is None
        assert pressure["hard_threshold_exceeded"] is None
        assert pressure["budget_decision"] == "unknown"
        assert pressure["overage_reason"] is None
        assert pressure["prompt_tokens"] == 10
        assert pressure["completion_tokens"] == 20
        assert pressure["total_tokens"] == 30
        assert pressure["prompt_token_delta"] == -118
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.RUNNING
        assert attempt_status == AttemptStatus.RUNNING


def test_usage_reported_without_policy_keeps_projection_non_failing(
    tmp_path: Path,
) -> None:
    """未配置 context budget policy 时 usage projection 仍成功。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _candidate(
            seeded,
            worker_event_index=7,
            data=UsageReportedData(
                iteration_id="iter-usage",
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
                provider_request_id=None,
            ),
            event_type=EngineEventType.USAGE_REPORTED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        payload = _payload(result.events[0])
        assert payload["policy_ref"] == "none"
        assert payload["estimator_digest"] is None
        assert payload["estimated_input_tokens"] is None
        assert payload["usage_observation_status"] == "estimate_unavailable"
        assert payload["provider_request_id"] is None
        context_pressure = payload["context_pressure"]
        assert isinstance(context_pressure, Mapping)
        pressure = cast(Mapping[str, JsonValue], context_pressure)
        assert pressure["status"] == "estimate_unavailable"
        assert pressure["policy_ref"] == "none"
        assert pressure["estimator_digest"] is None
        assert pressure["estimated_input_tokens"] is None
        assert pressure["input_budget_tokens"] is None
        assert pressure["soft_threshold_tokens"] is None
        assert pressure["hard_threshold_tokens"] is None
        assert pressure["soft_threshold_exceeded"] is None
        assert pressure["hard_threshold_exceeded"] is None
        assert pressure["budget_decision"] == "unknown"
        assert pressure["prompt_token_delta"] is None
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.RUNNING
        assert attempt_status == AttemptStatus.RUNNING


def test_usage_reported_missing_input_event_keeps_projection_non_failing(
    tmp_path: Path,
) -> None:
    """input event 缺失时 usage projection 降级为 estimate_unavailable。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        connection = store.connect()
        try:
            _delete_input_event(connection, event_id="event-input-ingest")
        finally:
            connection.close()
        candidate = _candidate(
            seeded,
            worker_event_index=7,
            data=UsageReportedData(
                iteration_id="iter-usage",
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
                provider_request_id=None,
            ),
            event_type=EngineEventType.USAGE_REPORTED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            context_budget_policy=_reactive_policy(),
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        payload = _payload(result.events[0])
        assert payload["policy_ref"] == "none"
        assert payload["estimator_digest"] is None
        assert payload["estimated_input_tokens"] is None
        assert payload["usage_observation_status"] == "estimate_unavailable"
        context_pressure = payload["context_pressure"]
        assert isinstance(context_pressure, Mapping)
        assert context_pressure["status"] == "estimate_unavailable"
        assert context_pressure["budget_decision"] == "unknown"
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.RUNNING
        assert attempt_status == AttemptStatus.RUNNING


def test_usage_reported_unreadable_input_event_keeps_projection_non_failing(
    tmp_path: Path,
) -> None:
    """input event payload 不可读时 usage projection 降级为 estimate_unavailable。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        _replace_inline_payload_json(
            store.transaction_runner,
            event_id="event-input-ingest",
            payload_json='{"display_text":7}',
        )
        candidate = _candidate(
            seeded,
            worker_event_index=7,
            data=UsageReportedData(
                iteration_id="iter-usage",
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
                provider_request_id="req-unreadable-input",
            ),
            event_type=EngineEventType.USAGE_REPORTED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            context_budget_policy=_reactive_policy(),
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        payload = _payload(result.events[0])
        assert payload["policy_ref"] == "none"
        assert payload["estimator_digest"] is None
        assert payload["estimated_input_tokens"] is None
        assert payload["usage_observation_status"] == "estimate_unavailable"
        assert payload["provider_request_id"] == "req-unreadable-input"
        context_pressure = payload["context_pressure"]
        assert isinstance(context_pressure, Mapping)
        assert context_pressure["status"] == "estimate_unavailable"
        assert context_pressure["budget_decision"] == "unknown"
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.RUNNING
        assert attempt_status == AttemptStatus.RUNNING


def test_usage_reported_invalid_tokens_keeps_projection_non_failing(
    tmp_path: Path,
) -> None:
    """usage token 异常时 projection 仍提交且不改变 Run / Attempt 状态。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _candidate(
            seeded,
            worker_event_index=7,
            data=UsageReportedData(
                iteration_id="iter-usage",
                prompt_tokens=-1,
                completion_tokens=20,
                total_tokens=19,
                provider_request_id="req-invalid-usage",
            ),
            event_type=EngineEventType.USAGE_REPORTED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            context_budget_policy=_reactive_policy(),
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        payload = _payload(result.events[0])
        assert payload["prompt_tokens"] == -1
        assert payload["provider_request_id"] == "req-invalid-usage"
        assert payload["policy_ref"] == "none"
        assert payload["estimator_digest"] is None
        assert payload["estimated_input_tokens"] is None
        assert payload["usage_observation_status"] == "usage_invalid"
        assert isinstance(payload["usage_observation_digest"], str)
        assert payload["prompt_token_delta"] is None
        context_pressure = payload["context_pressure"]
        assert isinstance(context_pressure, Mapping)
        pressure = cast(Mapping[str, JsonValue], context_pressure)
        assert pressure["status"] == "usage_invalid"
        assert pressure["estimated_input_tokens"] is None
        assert pressure["budget_decision"] == "unknown"
        assert pressure["prompt_tokens"] == -1
        assert pressure["prompt_token_delta"] is None
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.RUNNING
        assert attempt_status == AttemptStatus.RUNNING


def test_duplicate_candidate_returns_existing_result(tmp_path: Path) -> None:
    """同一 terminal candidate 重放 exact sequence，且 replay flag 为 false。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        wakeup = _WakeupSpy()
        terminal_port = _RecordingTerminalPostCommitPort()
        candidate = _candidate(
            seeded,
            worker_event_index=8,
            data=FinalAnswerData(
                content="重复",
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
            event_type=EngineEventType.FINAL_ANSWER,
        )
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=terminal_port,
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
            wakeup_port=wakeup,
        )

        first = ingestor.ingest(candidate)
        second = ingestor.ingest(candidate)

        assert first.status == EngineIngestStatus.ACCEPTED
        assert first.terminal_notice is not None
        assert first.terminal_notice.wake_queue_promotion is True
        assert second.status == EngineIngestStatus.DUPLICATE
        assert second.terminal_notice is not None
        assert second.terminal_notice.wake_queue_promotion is False
        assert terminal_port.notices == [
            first.terminal_notice,
            second.terminal_notice,
        ]
        assert (
            first.terminal_notice.terminal_event_sequence
            == second.terminal_notice.terminal_event_sequence
        )
        assert [event.event_id for event in first.events] == [
            event.event_id for event in second.events
        ]
        assert _event_count(store.transaction_runner, "ATTEMPT_SUCCEEDED") == 1
        assert _event_count(store.transaction_runner, "RUN_SUCCEEDED") == 1
        assert wakeup.promoted_session_ids == []


def test_stale_execution_id_is_rejected_diagnostic(tmp_path: Path) -> None:
    """stale execution_id 不污染 canonical facts。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        stale = _SeededRun(
            session_id=seeded.session_id,
            run_id=seeded.run_id,
            attempt_id=seeded.attempt_id,
            execution_id="execution-stale",
            dispatch_record_id=seeded.dispatch_record_id,
        )
        candidate = _candidate(
            stale,
            worker_event_index=9,
            data=FinalAnswerData(
                content="过期",
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
            event_type=EngineEventType.FINAL_ANSWER,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.REJECTED
        assert result.events[0].event_class == EventClass.DIAGNOSTIC
        assert result.events[0].event_type == "ENGINE_EVENT_REJECTED"
        assert _event_count(store.transaction_runner, "ATTEMPT_SUCCEEDED") == 0
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.RUNNING
        assert attempt_status == AttemptStatus.RUNNING


def test_provider_protocol_error_is_diagnostic_without_state_change(
    tmp_path: Path,
) -> None:
    """provider_protocol_error 写 diagnostic，不改变 active Run 状态。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _candidate(
            seeded,
            worker_event_index=10,
            data=ProviderProtocolErrorData(
                iteration_id="iter-protocol",
                error_code=runner_protocol_error_code("invalid_stream"),
                message="bad stream",
                provider_request_id="req-protocol",
                client_correlation_id="client-protocol",
                raw_payload={
                    "version": 1,
                    "source": "provider_protocol_error",
                    "kind": "provider_error",
                    "canonical_byte_size": 128,
                    "sha256_digest": ("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"),
                    "provider_error": {
                        "code": "raw_payload_code_must_not_win",
                        "type": "protocol_error",
                    },
                },
                partial_tool_calls=(),
            ),
            event_type=EngineEventType.PROVIDER_PROTOCOL_ERROR,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.events[0].event_class == EventClass.DIAGNOSTIC
        assert result.events[0].event_type == "PROVIDER_PROTOCOL_ERROR"
        payload = _payload(result.events[0])
        assert payload["client_correlation_id"] == "client-protocol"
        assert payload["raw_payload_ref"] is not None
        assert payload["partial_tool_call_count"] == 0
        assert payload["partial_tool_call_signal"] == {
            "schema_version": 1,
            "signal_source": "PROVIDER_PROTOCOL_ERROR",
            "partial_tool_call_count": 0,
            "summary_status": "none",
            "raw_payload_present": True,
            "partial_tool_calls": [],
        }
        assert payload["failure_metadata"] == {
            "schema_version": 1,
            "signal_source": "PROVIDER_PROTOCOL_ERROR",
            "failure_kind": "provider_protocol_error",
            "provider_error_code": "invalid_stream",
            "diagnostic_refs": [payload["raw_payload_ref"], "req-protocol"],
        }
        assert "RunnerSpecificErrorCode" not in json.dumps(payload)
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.RUNNING
        assert attempt_status == AttemptStatus.RUNNING


def test_provider_diagnostic_is_nonfatal_diagnostic_without_failure_metadata(
    tmp_path: Path,
) -> None:
    """provider diagnostic 持久化为非致命诊断，不改变 active Run 状态。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _candidate(
            seeded,
            worker_event_index=11,
            data=ProviderDiagnosticData(
                iteration_id="iter-diagnostic",
                diagnostic_code="usage_field_malformed",
                severity=RunnerDiagnosticSeverity.WARNING,
                message="usage ignored",
                provider_request_id="req-diagnostic",
                raw_payload={"prompt_tokens_type": "str"},
                partial_tool_calls=(),
                diagnostic_source=RunnerDiagnosticSource.SSE_PARSER,
                client_correlation_id="client-diagnostic",
            ),
            event_type=EngineEventType.PROVIDER_DIAGNOSTIC,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.terminal_closeout is False
        assert result.events[0].event_class == EventClass.DIAGNOSTIC
        assert result.events[0].event_type == "PROVIDER_DIAGNOSTIC"
        payload = _payload(result.events[0])
        assert payload["diagnostic_code"] == "usage_field_malformed"
        assert payload["severity"] == "warning"
        assert payload["message"] == "usage ignored"
        assert payload["provider_request_id"] == "req-diagnostic"
        assert payload["client_correlation_id"] == "client-diagnostic"
        assert payload["diagnostic_source"] == "sse_parser"
        assert payload["payload_ref"] is not None
        assert payload["payload_digest"] is not None
        assert payload["partial_tool_call_count"] == 0
        assert "failure_metadata" not in payload
        assert "provider_error_code" not in payload
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.RUNNING
        assert attempt_status == AttemptStatus.RUNNING


def test_provider_protocol_error_serializes_partial_tool_call_signal(
    tmp_path: Path,
) -> None:
    """provider_protocol_error 写入 Engine bounded partial tool-call signal。"""

    arguments_sha256 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _candidate(
            seeded,
            worker_event_index=11,
            data=ProviderProtocolErrorData(
                iteration_id="iter-protocol-partial",
                error_code=runner_protocol_error_code("invalid_stream"),
                message="bad stream",
                provider_request_id="req-protocol-partial",
                client_correlation_id="client-protocol-partial",
                raw_payload=None,
                partial_tool_calls=(
                    PartialToolCallSummary(
                        tool_call_index=0,
                        tool_call_id="call-bounded",
                        name_fragment="lookup_filing",
                        arguments_byte_size=42,
                        arguments_sha256=arguments_sha256,
                    ),
                    PartialToolCallSummary(
                        tool_call_index=1,
                        tool_call_id=None,
                        name_fragment=None,
                        arguments_byte_size=0,
                        arguments_sha256=None,
                    ),
                ),
            ),
            event_type=EngineEventType.PROVIDER_PROTOCOL_ERROR,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        payload = _payload(result.events[0])
        assert payload["raw_payload_ref"] is None
        assert payload["raw_payload_digest"] is None
        assert payload["partial_tool_call_count"] == 2
        assert payload["partial_tool_call_signal"] == {
            "schema_version": 1,
            "signal_source": "PROVIDER_PROTOCOL_ERROR",
            "partial_tool_call_count": 2,
            "summary_status": "present",
            "raw_payload_present": False,
            "partial_tool_calls": [
                {
                    "tool_call_index": 0,
                    "tool_call_id": "call-bounded",
                    "name_fragment": "lookup_filing",
                    "arguments_byte_size": 42,
                    "arguments_sha256": arguments_sha256,
                    "arguments_present": True,
                },
                {
                    "tool_call_index": 1,
                    "tool_call_id": None,
                    "name_fragment": None,
                    "arguments_byte_size": 0,
                    "arguments_sha256": None,
                    "arguments_present": False,
                },
            ],
        }
        assert _legacy_provider_protocol_diagnostic_view(payload) == {
            "error_code": "invalid_stream",
            "provider_request_id": "req-protocol-partial",
            "client_correlation_id": "client-protocol-partial",
            "raw_payload_ref": None,
            "partial_tool_call_count": 2,
        }


def test_tool_call_requested_and_result_accepted_are_preview(
    tmp_path: Path,
) -> None:
    """Engine 工具请求与结果只能作为 preview，不能写 canonical 工具事实。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        requested = _candidate(
            seeded,
            worker_event_index=11,
            data=ToolCallRequestedData(
                iteration_id="iter-tool",
                tool_call_id="tool-call-1",
                name="lookup",
                arguments={"ticker": "MSFT"},
                index_in_iteration=0,
                provider_state=None,
            ),
            event_type=EngineEventType.TOOL_CALL_REQUESTED,
        )
        accepted = _candidate(
            seeded,
            worker_event_index=12,
            data=ToolResultAcceptedData(
                iteration_id="iter-tool",
                record=_accepted_tool_record(),
            ),
            event_type=EngineEventType.TOOL_RESULT_ACCEPTED,
        )
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        )

        first = ingestor.ingest(requested)
        second = ingestor.ingest(accepted)

        assert first.events[0].event_class == EventClass.PREVIEW
        assert first.events[0].event_type == "TOOL_CALL_REQUESTED"
        assert _payload(first.events[0])["argument_key_count"] == 1
        assert _payload(first.events[0])["normalized_arguments_digest"] == (
            sha256_digest_json({"arguments": {"ticker": "MSFT"}})
        )
        assert second.events[0].event_class == EventClass.PREVIEW
        assert second.events[0].event_type == "TOOL_RESULT_ACCEPTED"
        assert _payload(second.events[0])["outcome_kind"] == "completed"
        assert _canonical_tool_event_count(store.transaction_runner) == 0
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.RUNNING
        assert attempt_status == AttemptStatus.RUNNING


def test_all_transient_deltas_publish_once_without_event_log_rows(
    tmp_path: Path,
) -> None:
    """三类 Engine delta 共享 post-validation publish 与 zero-row contract。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        publisher = RecordingTransientDeltaPublisher()
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=publisher,
        )
        candidates = (
            _candidate(
                seeded,
                worker_event_index=11,
                data=ContentDeltaData(iteration_id="iter-delta", delta="content"),
                event_type=EngineEventType.CONTENT_DELTA,
            ),
            _candidate(
                seeded,
                worker_event_index=12,
                data=ReasoningDeltaData(
                    iteration_id="iter-delta",
                    delta="reasoning",
                ),
                event_type=EngineEventType.REASONING_DELTA,
            ),
            _candidate(
                seeded,
                worker_event_index=13,
                data=ToolCallDeltaData(
                    iteration_id="iter-tool",
                    tool_call_index=0,
                    tool_call_id="tool-call-1",
                    name_delta="lookup",
                    arguments_delta='{"ticker":"MSFT"}',
                ),
                event_type=EngineEventType.TOOL_CALL_DELTA,
            ),
        )

        results = tuple(ingestor.ingest(candidate) for candidate in candidates)

        assert [result.status for result in results] == [
            EngineIngestStatus.ACCEPTED,
            EngineIngestStatus.ACCEPTED,
            EngineIngestStatus.ACCEPTED,
        ]
        assert [result.events for result in results] == [(), (), ()]
        assert len(publisher.candidates) == 3
        assert [candidate.type for candidate in publisher.candidates] == [
            HostTransientDeltaType.CONTENT_DELTA,
            HostTransientDeltaType.REASONING_DELTA,
            HostTransientDeltaType.TOOL_CALL_DELTA,
        ]
        assert isinstance(publisher.candidates[0].data, HostContentDelta)
        assert publisher.candidates[0].data.text_delta == "content"
        assert isinstance(publisher.candidates[1].data, HostReasoningDelta)
        assert publisher.candidates[1].data.text_delta == "reasoning"
        assert isinstance(publisher.candidates[2].data, HostToolCallDelta)
        assert publisher.candidates[2].data.arguments_delta == '{"ticker":"MSFT"}'
        assert _event_count(store.transaction_runner, "CONTENT_DELTA") == 0
        assert _event_count(store.transaction_runner, "REASONING_DELTA") == 0
        assert _event_count(store.transaction_runner, "TOOL_CALL_DELTA") == 0


def test_transient_fence_comes_from_same_validation_transaction_attempt_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """candidate fence 必须原样来自 validation transaction 的 current Attempt。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: transaction read owner 注入工具。
    :returns: ``None``。
    :raises AssertionError: ingest 另行回读或重算 fence 时抛出。
    """

    sentinel_fence = 987_654_321
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        publisher = RecordingTransientDeltaPublisher()
        attempt_read_spy = _AttemptFenceReadSpy(
            started_event_sequence=sentinel_fence,
        )
        monkeypatch.setattr(
            engine_ingest_module,
            "read_attempt_by_id",
            attempt_read_spy,
        )
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=publisher,
        )

        result = ingestor.ingest(
            _candidate(
                seeded,
                worker_event_index=14,
                data=ReasoningDeltaData(
                    iteration_id="iter-fence",
                    delta="fenced",
                ),
                event_type=EngineEventType.REASONING_DELTA,
            )
        )

        assert result.status is EngineIngestStatus.ACCEPTED
        assert result.events == ()
        assert attempt_read_spy.call_count == 1
        assert len(publisher.candidates) == 1
        assert (
            publisher.candidates[0].durable_causal_fence_event_sequence
            == sentinel_fence
        )


def test_transient_publisher_failure_is_sanitized_and_does_not_change_acceptance(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """发布端口意外不得回滚 accepted ingest 或记录 delta/异常敏感正文。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=FailingTransientDeltaPublisher(),
        )
        with caplog.at_level("ERROR"):
            result = ingestor.ingest(
                _candidate(
                    seeded,
                    worker_event_index=14,
                    data=ReasoningDeltaData(
                        iteration_id="iter-sensitive",
                        delta="sensitive-reasoning-text",
                    ),
                    event_type=EngineEventType.REASONING_DELTA,
                )
            )

        assert result.status is EngineIngestStatus.ACCEPTED
        assert result.events == ()
        assert _event_count(store.transaction_runner, "REASONING_DELTA") == 0
        assert "transient_publish_failed" in caplog.text
        assert "sensitive-reasoning-text" not in caplog.text
        assert "sensitive-delta-publisher-message" not in caplog.text


def test_transient_transaction_rollback_does_not_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """validation transaction 回滚时不产生瞬态发布或 durable delta row。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: rollback 后仍发布或写入 delta row 时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        publisher = RecordingTransientDeltaPublisher()
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=publisher,
        )
        monkeypatch.setattr(
            engine_ingest_module._IngestValidatedOperation,
            "__call__",
            _force_rollback_after_validated_ingest,
        )

        with pytest.raises(
            _ExpectedTransientRollback,
            match="forced transient ingest rollback",
        ):
            ingestor.ingest(
                _candidate(
                    seeded,
                    worker_event_index=15,
                    data=ReasoningDeltaData(
                        iteration_id="iter-rollback",
                        delta="rollback-reasoning",
                    ),
                    event_type=EngineEventType.REASONING_DELTA,
                )
            )

        assert publisher.candidates == []
        assert _event_count(store.transaction_runner, "REASONING_DELTA") == 0


def test_tool_batch_events_stay_preview_not_canonical(
    tmp_path: Path,
) -> None:
    """Engine batch-ready 与 batch-done 不能绕过 accept path。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        )
        ready = _candidate(
            seeded,
            worker_event_index=14,
            data=ToolCallsBatchReadyData(
                iteration_id="iter-tool",
                tool_calls=(
                    ToolCallBatchItemData(
                        tool_call_id="tool-call-1",
                        name="lookup",
                        index_in_iteration=0,
                        provider_state=None,
                    ),
                ),
            ),
            event_type=EngineEventType.TOOL_CALLS_BATCH_READY,
        )
        done = _candidate(
            seeded,
            worker_event_index=15,
            data=ToolCallsBatchDoneData(
                iteration_id="iter-tool",
                tool_call_ids=("tool-call-1",),
                completed_count=1,
                failed_count=0,
                cancelled_count=0,
            ),
            event_type=EngineEventType.TOOL_CALLS_BATCH_DONE,
        )

        results = tuple(ingestor.ingest(item) for item in (ready, done))

        assert [result.events[0].event_class for result in results] == [
            EventClass.PREVIEW,
            EventClass.PREVIEW,
        ]
        assert [result.events[0].event_type for result in results] == [
            "TOOL_CALLS_BATCH_READY",
            "TOOL_CALLS_BATCH_DONE",
        ]
        assert _canonical_tool_event_count(store.transaction_runner) == 0


def test_late_terminal_event_is_rejected_after_closeout(tmp_path: Path) -> None:
    """Run terminal 后迟到 terminal candidate 写 rejected diagnostic。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        )
        first = _candidate(
            seeded,
            worker_event_index=13,
            data=FinalAnswerData(
                content="done",
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
            event_type=EngineEventType.FINAL_ANSWER,
        )
        late = _candidate(
            seeded,
            worker_event_index=14,
                data=RunFailedData(
                    error_code=adapter_error_code("late"),
                message="late",
                provider_request_id=None,
                recoverable=False,
            ),
            event_type=EngineEventType.RUN_FAILED,
        )

        ingestor.ingest(first)
        result = ingestor.ingest(late)

        assert result.status == EngineIngestStatus.REJECTED
        assert result.events[0].event_type == "ENGINE_EVENT_REJECTED"
        assert _payload(result.events[0])["reason"] == "terminal_already_closed"


def test_late_reasoning_delta_is_rejected_before_transient_publish(
    tmp_path: Path,
) -> None:
    """终态后的 reasoning delta 仍先经过 late-event governance。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        publisher = RecordingTransientDeltaPublisher()
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=publisher,
        )
        first = _candidate(
            seeded,
            worker_event_index=13,
            data=FinalAnswerData(
                content="done",
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
            event_type=EngineEventType.FINAL_ANSWER,
        )
        late = _candidate(
            seeded,
            worker_event_index=14,
            data=ReasoningDeltaData(
                iteration_id="iter-late",
                delta="late reasoning",
            ),
            event_type=EngineEventType.REASONING_DELTA,
        )

        ingestor.ingest(first)
        result = ingestor.ingest(late)

        assert result.status == EngineIngestStatus.REJECTED
        assert result.events[0].event_type == "ENGINE_EVENT_REJECTED"
        assert _payload(result.events[0])["reason"] == "terminal_already_closed"
        assert _event_count(store.transaction_runner, "REASONING_DELTA") == 0
        assert publisher.candidates == []


def test_run_cancelled_without_active_cancel_is_rejected(tmp_path: Path) -> None:
    """缺少 Host active cancel fact 的 run_cancelled 不关闭 Run。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _candidate(
            seeded,
            worker_event_index=15,
            data=RunCancelledData(
                reason="user_stop",
                requested_at=_NOW,
                accepted_at=_NOW,
                finished_at=_NOW,
            ),
            event_type=EngineEventType.RUN_CANCELLED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.REJECTED
        assert _payload(result.events[0])["reason"] == (
            "run_cancelled_invalid_active_cancel_link"
        )
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.RUNNING
        assert attempt_status == AttemptStatus.RUNNING


def test_run_cancelled_with_malformed_active_cancel_payload_uses_typed_link(
    tmp_path: Path,
) -> None:
    """RUN_CANCELLING payload 缺少 request id 时仍使用 typed row link。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        store.transaction_runner.run_write(_RequestActiveCancelOperation(seeded))
        store.transaction_runner.run_write(
            _AppendMalformedRunCancellingOperation(seeded)
        )
        candidate = _candidate(
            seeded,
            worker_event_index=16,
            data=RunCancelledData(
                reason="user_stop",
                requested_at=_NOW,
                accepted_at=_NOW,
                finished_at=_NOW,
            ),
            event_type=EngineEventType.RUN_CANCELLED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        assert result.terminal_closeout is True
        assert _event_count(store.transaction_runner, "RUN_CANCELLED") == 1
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.CANCELLED
        assert attempt_status == AttemptStatus.CANCELLED


def test_run_cancelled_requested_at_uses_cancel_requested_event_time(
    tmp_path: Path,
) -> None:
    """cancel terminal requested_at 来自 committed CANCEL_REQUESTED fact。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        store.transaction_runner.run_write(_RequestActiveCancelOperation(seeded))
        engine_requested_at = _NOW.replace(second=33)
        candidate = _candidate(
            seeded,
            worker_event_index=17,
            data=RunCancelledData(
                reason="user_stop",
                requested_at=engine_requested_at,
                accepted_at=_NOW.replace(second=34),
                finished_at=_NOW.replace(second=35),
            ),
            event_type=EngineEventType.RUN_CANCELLED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        run_cancelled = _latest_event(store.transaction_runner, "RUN_CANCELLED")
        payload = _payload(run_cancelled)
        assert payload["requested_at"] == "2026-05-15T01:02:03.000000Z"
        assert payload["requested_at"] != engine_requested_at.isoformat()


def test_late_worker_terminal_after_timeout_is_rejected_as_terminal_closed(
    tmp_path: Path,
) -> None:
    """watchdog terminal 后迟到 worker terminal 只写 terminal closed diagnostic。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        store.transaction_runner.run_write(_CloseActiveCancelWatchdogOperation(seeded))
        candidate = _candidate(
            seeded,
            worker_event_index=17,
                data=RunFailedData(
                    error_code=adapter_error_code("late_after_timeout"),
                message="late after timeout",
                provider_request_id=None,
                recoverable=False,
            ),
            event_type=EngineEventType.RUN_FAILED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.REJECTED
        assert _payload(result.events[0])["reason"] == "terminal_already_closed"
        assert _event_count(store.transaction_runner, "RUN_FAILED") == 0
        assert _event_count(store.transaction_runner, "ATTEMPT_FAILED") == 0
        assert _event_count(store.transaction_runner, "RUN_CANCELLED") == 1
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.CANCELLED
        assert attempt_status == AttemptStatus.CANCELLED


def test_late_final_answer_after_run_cancelling_is_rejected_with_diagnostic(
    tmp_path: Path,
) -> None:
    """RUN_CANCELLING 后迟到 final_answer 不写 success terminal。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        store.transaction_runner.run_write(_RequestActiveCancelOperation(seeded))
        candidate = _candidate(
            seeded,
            worker_event_index=18,
            data=FinalAnswerData(
                content="late answer",
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
            event_type=EngineEventType.FINAL_ANSWER,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.REJECTED
        assert _payload(result.events[0])["reason"] == (
            "late_terminal_after_active_cancel"
        )
        assert _event_count(store.transaction_runner, "RUN_SUCCEEDED") == 0
        assert _event_count(store.transaction_runner, "ATTEMPT_SUCCEEDED") == 0
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.CANCELLING
        assert attempt_status == AttemptStatus.RUNNING


def test_late_run_failed_after_run_cancelling_is_rejected_with_diagnostic(
    tmp_path: Path,
) -> None:
    """RUN_CANCELLING 后迟到 run_failed 不写 failure terminal。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        store.transaction_runner.run_write(_RequestActiveCancelOperation(seeded))
        candidate = _candidate(
            seeded,
            worker_event_index=19,
                data=RunFailedData(
                    error_code=adapter_error_code("late_failure"),
                message="late failure",
                provider_request_id=None,
                recoverable=False,
            ),
            event_type=EngineEventType.RUN_FAILED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.REJECTED
        assert _payload(result.events[0])["reason"] == (
            "late_terminal_after_active_cancel"
        )
        assert _event_count(store.transaction_runner, "RUN_FAILED") == 0
        assert _event_count(store.transaction_runner, "ATTEMPT_FAILED") == 0
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.CANCELLING
        assert attempt_status == AttemptStatus.RUNNING


@pytest.mark.parametrize(
    "lifecycle_source",
    ("worker_clean_eof", "worker_lost"),
)
def test_host_lifecycle_after_run_cancelling_is_diagnostic_only(
    tmp_path: Path,
    lifecycle_source: str,
) -> None:
    """active cancel 后 Host lifecycle signal 不写失败或 lost terminal。

    :param tmp_path: pytest 临时目录。
    :param lifecycle_source: 待验证的 Host lifecycle 来源。
    :returns: ``None``。
    :raises AssertionError: lifecycle decision table 不满足时由 pytest 报告。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        store.transaction_runner.run_write(_RequestActiveCancelOperation(seeded))
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        )
        if lifecycle_source == "worker_clean_eof":
            result = ingestor.close_clean_eof(
                _envelope(seeded),
                observed_at=_NOW,
                last_observed_worker_event_index=0,
            )
        else:
            result = ingestor.close_worker_lost(
                _envelope(seeded),
                observed_at=_NOW,
                worker_lifecycle_signal="worker_crash",
                stream_error_code="RuntimeError",
                last_observed_worker_event_index=0,
            )

        assert result.status == EngineIngestStatus.REJECTED
        assert result.terminal_closeout is False
        assert len(result.events) == 1
        diagnostic = result.events[0]
        assert diagnostic.event_type == "HOST_LIFECYCLE_DIAGNOSTIC"
        assert diagnostic.event_id.startswith("event-host-lifecycle-")
        assert diagnostic.source == "host.worker_lifecycle"
        diagnostic_payload = _payload(diagnostic)
        assert diagnostic_payload["reason"] == (
            "host_lifecycle_after_active_cancel"
        )
        assert diagnostic_payload["lifecycle_source"] == lifecycle_source
        assert "engine_event_type" not in diagnostic_payload
        assert "engine_event_ref" not in diagnostic_payload
        assert _event_count(store.transaction_runner, "RUN_FAILED") == 0
        assert _event_count(store.transaction_runner, "ATTEMPT_FAILED") == 0
        assert _event_count(store.transaction_runner, "RUN_LOST") == 0
        assert _event_count(store.transaction_runner, "ATTEMPT_LOST") == 0
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.CANCELLING
        assert attempt_status == AttemptStatus.RUNNING


def test_late_awaiting_after_cancel_does_not_move_to_waiting(
    tmp_path: Path,
) -> None:
    """RUN_CANCELLING 后迟到 suspended/awaiting 不能把 Run 推入 WAITING。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        store.transaction_runner.run_write(_RequestActiveCancelOperation(seeded))
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        )
        suspended = _candidate(
            seeded,
            worker_event_index=20,
            data=RunSuspendedData(
                reason="tool_awaiting",
                resume_hint=None,
                accepted_records=(_accepted_tool_record(),),
                awaiting_records=(_awaiting_tool_record(),),
            ),
            event_type=EngineEventType.RUN_SUSPENDED,
        )
        awaiting = _candidate(
            seeded,
            worker_event_index=21,
            data=ToolAwaitingData(
                iteration_id="iter-late-await",
                record=_awaiting_tool_record(),
            ),
            event_type=EngineEventType.TOOL_AWAITING,
        )

        suspended_result = ingestor.ingest(suspended)
        awaiting_result = ingestor.ingest(awaiting)

        assert suspended_result.status == EngineIngestStatus.ACCEPTED
        assert awaiting_result.status == EngineIngestStatus.ACCEPTED
        assert _payload(suspended_result.events[0])["reason"] == (
            "tool_awaiting"
        )
        assert _payload(suspended_result.events[0])["run_status"] == "cancelling"
        assert _payload(suspended_result.events[0])[
            "waiting_confirmation_accepted"
        ] is False
        assert _payload(awaiting_result.events[0])["run_status"] == "cancelling"
        assert _event_count(store.transaction_runner, "RUN_WAITING") == 0
        assert _event_count(store.transaction_runner, "ATTEMPT_SUSPENDED") == 0
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.CANCELLING
        assert attempt_status == AttemptStatus.RUNNING


@dataclass(frozen=True, slots=True)
class _AppendMalformedRunCancellingOperation:
    """写入缺少 ``cancel_request_event_id`` 的 RUN_CANCELLING fact。

    :param seeded: 已创建的 active run 测试数据。
    """

    seeded: _SeededRun

    def __call__(self, transaction: HostTransaction) -> None:
        """执行测试数据写入。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        EventLogStore().append_event(
            transaction,
            EventLogAppendRequest(
                event_id="event-run-cancelling-malformed",
                event_class=EventClass.CANONICAL_FACT,
                session_id=self.seeded.session_id,
                run_id=self.seeded.run_id,
                attempt_id=self.seeded.attempt_id,
                execution_id=self.seeded.execution_id,
                event_type="RUN_CANCELLING",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason="malformed",
                payload_json={"reason": "malformed"},
                payload_ref=None,
                payload_digest=None,
            ),
        )


@dataclass(frozen=True, slots=True)
class _RequestActiveCancelOperation:
    """把 seeded active Run 推进到 ``RUN_CANCELLING``。

    :param seeded: 已创建的 active run 测试数据。
    """

    seeded: _SeededRun

    def __call__(self, transaction: HostTransaction) -> None:
        """执行 active cancel request。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        result = request_active_attempt_cancel_in_transaction(
            transaction,
            EventLogStore(),
            CancelActiveAttemptInput(
                run_id=self.seeded.run_id,
                cancel_request_event_id="event-active-cancel-requested-ingest",
                run_cancelling_event_id="event-run-cancelling-ingest",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id="client-active-cancel-ingest",
                idempotency_key="idem-active-cancel-ingest",
                reason="user_cancel",
                mode=CancelMode.GRACEFUL,
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )
        assert result.status == StateMutationStatus.UPDATED


@dataclass(frozen=True, slots=True)
class _CloseActiveCancelWatchdogOperation:
    """把 seeded active Run 经 accepted cancel watchdog 收口为 cancelled。

    :param seeded: 已创建的 active run 测试数据。
    """

    seeded: _SeededRun

    def __call__(self, transaction: HostTransaction) -> None:
        """执行 active cancel request 与 watchdog closeout。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        _RequestActiveCancelOperation(self.seeded)(transaction)
        result = active_cancel_watchdog_closeout_in_transaction(
            transaction,
            EventLogStore(),
            ActiveCancelWatchdogCloseoutInput(
                run_id=self.seeded.run_id,
                attempt_id=self.seeded.attempt_id,
                attempt_cancelled_event_id=(
                    "event-active-watchdog-attempt-cancelled-ingest"
                ),
                run_cancelled_event_id="event-active-watchdog-run-cancelled-ingest",
                occurred_at=_NOW,
                actor="host.active_cancel_watchdog",
                source="pytest",
                cancel_requested_at="2026-05-14T01:02:03.000000Z",
                closed_out_at=_NOW,
                watchdog_owner="host.active_cancel_watchdog",
                worker_lifecycle_signal="active_cancel_watchdog_closeout",
                last_observed_worker_event_index=None,
                last_accepted_event_id=None,
            ),
        )
        assert result.status == StateMutationStatus.UPDATED


def test_worker_clean_eof_closeout_uses_host_lifecycle_identity_and_source(
    tmp_path: Path,
) -> None:
    """worker clean EOF 使用 Host lifecycle identity，不伪造 Engine fact。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: lifecycle identity、source 或 payload 不满足时报告。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).close_clean_eof(
            _envelope(seeded),
            observed_at=_NOW,
            last_observed_worker_event_index=0,
        )

        assert result.status == EngineIngestStatus.ACCEPTED
        assert [event.event_type for event in result.events] == [
            "ATTEMPT_FAILED",
            "RUN_FAILED",
        ]
        assert all(
            event.event_id.startswith("event-host-lifecycle-")
            for event in result.events
        )
        assert all(event.source == "host.worker_lifecycle" for event in result.events)
        attempt_payload = _payload(result.events[0])
        assert "engine_event_ref" not in attempt_payload
        assert "engine_event_type" not in attempt_payload
        terminal_payload = store.transaction_runner.run_read(
            lambda transaction: sqlite_payload_object(
                transaction,
                payload_ref=cast(str, attempt_payload["terminal_summary_ref"]),
                payload_digest=cast(
                    str, attempt_payload["terminal_summary_digest"]
                ),
                payload_label="host lifecycle terminal payload",
            )
        )
        assert terminal_payload["lifecycle_source"] == "worker_clean_eof"
        assert terminal_payload["host_lifecycle_ref"] == (
            f"host-lifecycle:{seeded.execution_id}:1:worker_clean_eof:stream_ended_without_terminal"
        )
        assert "engine_event_type" not in terminal_payload


def test_host_lifecycle_ingress_rejects_mismatched_run_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Host lifecycle ingress 显式拒绝 repository 返回的错 run identity。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: ingress 接受错 Run identity 时抛出。
    """

    durable_read_run = engine_ingest_module.read_run_by_id

    def mismatched_read_run(
        transaction: HostTransaction, run_id: str
    ) -> RunRow | None:
        """返回 key 查询命中但 row identity 漂移的测试 double。

        :param transaction: 当前 Host transaction。
        :param run_id: envelope 请求的 Run id。
        :returns: identity 被替换的 Run row；不存在时返回 ``None``。
        :raises HostDurableError: durable Run row 读取失败时抛出。
        """

        run = durable_read_run(transaction, run_id)
        if run is None:
            return None
        return replace(run, run_id=f"{run_id}-mismatched")

    monkeypatch.setattr(
        engine_ingest_module,
        "read_run_by_id",
        mismatched_read_run,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).close_clean_eof(
            _envelope(seeded),
            observed_at=_NOW,
            last_observed_worker_event_index=0,
        )

        assert result.status is EngineIngestStatus.REJECTED
        assert result.reason == "stale_execution_id"
        assert result.terminal_closeout is False
        assert [event.event_type for event in result.events] == [
            "HOST_LIFECYCLE_DIAGNOSTIC"
        ]
        assert _event_count(store.transaction_runner, "RUN_FAILED") == 0
        assert _statuses(store.transaction_runner, seeded) == (
            RunStatus.RUNNING,
            AttemptStatus.RUNNING,
        )


def test_worker_lost_closeout_uses_lost_event_ids_and_duplicate(
    tmp_path: Path,
) -> None:
    """worker lost 使用 Host lifecycle LOST facts，重复 closeout 幂等。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: LOST closeout 或幂等 identity 不满足时报告。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        )
        envelope = _envelope(seeded)

        first = ingestor.close_worker_lost(
            envelope,
            observed_at=_NOW,
            worker_lifecycle_signal="worker_stream_error",
            stream_error_code="RuntimeError",
            last_observed_worker_event_index=0,
            last_accepted_event_id=None,
        )
        second = ingestor.close_worker_lost(
            envelope,
            observed_at=_NOW,
            worker_lifecycle_signal="worker_stream_error",
            stream_error_code="RuntimeError",
            last_observed_worker_event_index=0,
            last_accepted_event_id=None,
        )

        assert first.status == EngineIngestStatus.ACCEPTED
        assert second.status == EngineIngestStatus.DUPLICATE
        assert [event.event_type for event in first.events] == [
            "ATTEMPT_LOST",
            "RUN_LOST",
        ]
        assert all(
            event.event_id.startswith("event-host-lifecycle-")
            for event in first.events
        )
        assert all(event.source == "host.worker_lifecycle" for event in first.events)
        payload = _payload(first.events[1])
        assert "engine_event_ref" not in payload
        attempt_payload = _payload(first.events[0])
        terminal_payload = store.transaction_runner.run_read(
            lambda transaction: sqlite_payload_object(
                transaction,
                payload_ref=cast(str, attempt_payload["terminal_summary_ref"]),
                payload_digest=cast(
                    str, attempt_payload["terminal_summary_digest"]
                ),
                payload_label="host lifecycle terminal payload",
            )
        )
        assert terminal_payload["lifecycle_source"] == "worker_lost"
        assert terminal_payload["host_lifecycle_ref"] == (
            f"host-lifecycle:{seeded.execution_id}:1:worker_lost:worker_lost_before_terminal"
        )
        assert "engine_event_type" not in terminal_payload
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.LOST
        assert attempt_status == AttemptStatus.LOST


def test_engine_terminal_invalid_state_rolls_back_payload_and_events(
    tmp_path: Path,
) -> None:
    """Engine terminal 遇 WAITING/RUNNING invalid-state 时原子回滚。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: payload、EventLog 或状态未原子回滚时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        _force_run_status_for_invalid_terminal_precondition(
            store.transaction_runner,
            seeded,
            status=RunStatus.WAITING,
        )
        before = _terminal_storage_snapshot(store.transaction_runner, seeded)

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(
            _candidate(
                seeded,
                worker_event_index=61,
                data=FinalAnswerData(
                    content="late answer",
                    filtered=False,
                    degraded=False,
                    finish_reason=FinishReason.STOP,
                ),
                event_type=EngineEventType.FINAL_ANSWER,
            )
        )

        assert result.status is EngineIngestStatus.REJECTED
        assert result.reason == "terminal_closeout_precondition_failed"
        assert result.events == ()
        assert _terminal_storage_snapshot(store.transaction_runner, seeded) == before


def test_host_lifecycle_invalid_state_rolls_back_payload_and_events(
    tmp_path: Path,
) -> None:
    """Host lifecycle terminal 遇 WAITING/RUNNING invalid-state 时原子回滚。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: payload、EventLog 或状态未原子回滚时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        _force_run_status_for_invalid_terminal_precondition(
            store.transaction_runner,
            seeded,
            status=RunStatus.WAITING,
        )
        before = _terminal_storage_snapshot(store.transaction_runner, seeded)

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).close_worker_lost(
            _envelope(seeded),
            observed_at=_NOW,
            worker_lifecycle_signal="worker_stream_error",
            stream_error_code="RuntimeError",
            last_observed_worker_event_index=0,
        )

        assert result.status is EngineIngestStatus.REJECTED
        assert result.reason == "terminal_closeout_precondition_failed"
        assert result.events == ()
        assert _terminal_storage_snapshot(store.transaction_runner, seeded) == before


def test_engine_terminal_cas_lost_rolls_back_real_payload_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Engine terminal CAS loser 经真实 transaction 与 payload repository 回滚。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: CAS loser 未原子回滚时抛出。
    """

    monkeypatch.setattr(
        engine_ingest_module,
        "terminal_closeout_in_transaction",
        _cas_lost_terminal_closeout,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        before = _terminal_storage_snapshot(store.transaction_runner, seeded)

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(
            _candidate(
                seeded,
                worker_event_index=62,
                data=FinalAnswerData(
                    content="answer",
                    filtered=False,
                    degraded=False,
                    finish_reason=FinishReason.STOP,
                ),
                event_type=EngineEventType.FINAL_ANSWER,
            )
        )

        assert result.status is EngineIngestStatus.REJECTED
        assert result.reason == "terminal_closeout_precondition_failed"
        assert result.events == ()
        assert _terminal_storage_snapshot(store.transaction_runner, seeded) == before


def test_host_lifecycle_cas_lost_rolls_back_real_payload_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Host lifecycle CAS loser 经真实 transaction 与 payload repository 回滚。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: CAS loser 未原子回滚时抛出。
    """

    monkeypatch.setattr(
        engine_ingest_module,
        "terminal_closeout_in_transaction",
        _cas_lost_terminal_closeout,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        before = _terminal_storage_snapshot(store.transaction_runner, seeded)

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).close_clean_eof(
            _envelope(seeded),
            observed_at=_NOW,
            last_observed_worker_event_index=0,
        )

        assert result.status is EngineIngestStatus.REJECTED
        assert result.reason == "terminal_closeout_precondition_failed"
        assert result.events == ()
        assert _terminal_storage_snapshot(store.transaction_runner, seeded) == before


def test_engine_run_failed_with_worker_lifecycle_reason_remains_engine_failed(
    tmp_path: Path,
) -> None:
    """真实 Engine run_failed 不因 Host lifecycle reason 文本被重解释为 LOST。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: Engine-origin closeout 被错误重解释时报告。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _candidate(
            seeded,
            worker_event_index=1,
            data=RunFailedData(
                error_code=adapter_error_code("worker_lost_before_terminal"),
                message="Engine reported its own failure",
                provider_request_id=None,
                recoverable=False,
            ),
            event_type=EngineEventType.RUN_FAILED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert [event.event_type for event in result.events] == [
            "ATTEMPT_FAILED",
            "RUN_FAILED",
        ]
        assert all(event.event_id.startswith("event-engine-") for event in result.events)
        payload = _payload(result.events[0])
        assert payload["engine_event_ref"] == (
            f"engine:{seeded.execution_id}:1:run_failed"
        )
        assert _statuses(store.transaction_runner, seeded) == (
            RunStatus.FAILED,
            AttemptStatus.FAILED,
        )


def test_late_rejection_uses_status_even_when_terminal_refs_are_missing(
    tmp_path: Path,
) -> None:
    """late rejection 直接消费 Run / Attempt status，而不依赖 nullable refs。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: status truth 未优先于 nullable refs 时报告。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _candidate(
            seeded,
            worker_event_index=1,
            data=ReasoningDeltaData(
                iteration_id="iter-status-truth",
                delta="late",
            ),
            event_type=EngineEventType.REASONING_DELTA,
        )

        def _context(
            transaction: HostTransaction,
        ) -> engine_ingest_module._ValidatedCandidate:
            """构造只用于 predicate 单测的异常 nullable-ref 上下文。

            :param transaction: Host read transaction。
            :returns: status 已终态但 terminal refs 为空的校验上下文。
            :raises AssertionError: seeded durable rows 缺失时抛出。
            """

            run = read_run_by_id(transaction, seeded.run_id)
            attempt = read_attempt_by_id(transaction, seeded.attempt_id)
            dispatch = read_dispatch_record_by_attempt_id(
                transaction, seeded.attempt_id
            )
            assert run is not None
            assert attempt is not None
            assert dispatch is not None
            return engine_ingest_module._ValidatedCandidate(
                candidate=candidate,
                run=replace(
                    run,
                    status=RunStatus.FAILED,
                    terminal_event_id=None,
                    terminal_event_sequence=None,
                    terminal_at=None,
                ),
                attempt=attempt,
                dispatch_record=dispatch,
            )

        run_terminal_context = store.transaction_runner.run_read(_context)
        attempt_terminal_context = replace(
            run_terminal_context,
            run=replace(run_terminal_context.run, status=RunStatus.RUNNING),
            attempt=replace(
                run_terminal_context.attempt,
                status=AttemptStatus.FAILED,
                terminal_event_id=None,
                terminal_event_sequence=None,
                terminal_at=None,
            ),
        )

        assert (
            engine_ingest_module._late_engine_event_rejection_reason(run_terminal_context) == "terminal_already_closed"
        )
        assert (
            engine_ingest_module._late_engine_event_rejection_reason(attempt_terminal_context)
            == "terminal_already_closed"
        )


def test_unsupported_engine_event_shape_is_rejected(tmp_path: Path) -> None:
    """EngineEvent owner 在 Host ingest 前拒绝 type/data mismatch。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        with pytest.raises(ValueError, match="type/data mismatch"):
            _candidate(
                seeded,
                worker_event_index=16,
                data=FinalAnswerData(
                    content="wrong shape",
                    filtered=False,
                    degraded=False,
                    finish_reason=FinishReason.STOP,
                ),
                event_type=EngineEventType.RUN_FAILED,
            )


@pytest.mark.parametrize(
    ("worker_event_index", "data", "expected_error", "expected_message"),
    (
        (
            17,
            cast(EngineEventData, None),
            TypeError,
            "unsupported type",
        ),
        (
            18,
            IterationStartedData(
                iteration_id="iter-wrong",
                iteration_index=0,
                message_count=1,
                role_sequence_digest=runner_role_sequence_digest(("user",)),
                runner_input_serializer_schema_version=(
                    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
                ),
            ),
            ValueError,
            "type/data mismatch",
        ),
    ),
)
def test_transient_delta_event_rejects_missing_or_wrong_data(
    tmp_path: Path,
    worker_event_index: int,
    data: EngineEventData,
    expected_error: type[TypeError] | type[ValueError],
    expected_message: str,
) -> None:
    """非法 transient delta 在构造 owner 处失败，不进入 Host repair。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        with pytest.raises(expected_error, match=expected_message):
            _candidate(
                seeded,
                worker_event_index=worker_event_index,
                data=data,
                event_type=EngineEventType.CONTENT_DELTA,
            )


def test_transient_delta_event_accepts_matching_type_without_row(
    tmp_path: Path,
) -> None:
    """匹配 data 类型的 transient delta event 返回 accepted 但不写 row。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _candidate(
            seeded,
            worker_event_index=19,
            data=ContentDeltaData(iteration_id="iter-ok", delta="hello"),
            event_type=EngineEventType.CONTENT_DELTA,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        assert result.events == ()
        assert _event_count(store.transaction_runner, "CONTENT_DELTA") == 0


def test_iteration_started_links_prepared_runner_call_manifest(
    tmp_path: Path,
) -> None:
    """ordinary prepared manifest 会显式 link 到 Engine iteration。"""

    role_digest = runner_role_sequence_digest(("system", "user"))
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        manifest_event = _append_prepared_runner_call_manifest(
            store.transaction_runner,
            seeded,
            event_id="event-prepared-runner-call-initial",
            runner_call_index=0,
            runner_call_kind="initial_user_dispatch",
            runner_call_trigger_reason="initial_user_input",
            message_count=2,
            role_sequence_digest=role_digest,
        )
        candidate = _candidate(
            seeded,
            worker_event_index=20,
            data=IterationStartedData(
                iteration_id="iter-linked",
                iteration_index=0,
                message_count=2,
                role_sequence_digest=role_digest,
                runner_input_serializer_schema_version=(
                    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
                ),
            ),
            event_type=EngineEventType.ITERATION_STARTED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        assert [event.event_type for event in result.events] == [
            "RUNNER_CALL_INPUT_ITERATION_LINKED",
            "ITERATION_STARTED",
        ]
        link_payload = _payload(result.events[0])
        preview_payload = _payload(result.events[1])
        validation = preview_payload["runner_call_manifest_validation"]
        assert isinstance(validation, Mapping)

        assert link_payload["manifest_event_id"] == manifest_event.event_id
        assert link_payload["iteration_id"] == "iter-linked"
        assert link_payload["iteration_index"] == 0
        assert link_payload["validation_status"] == "complete"
        assert link_payload["diagnostic"] is None
        assert link_payload["engine_message_count"] == 2
        assert link_payload["expected_message_count"] == 2
        assert link_payload["engine_role_sequence_digest"] == role_digest
        assert link_payload["expected_role_sequence_digest"] == role_digest
        assert preview_payload["runner_call_iteration_link_event_id"] == (
            result.events[0].event_id
        )
        assert preview_payload["runner_call_manifest_event_id"] == (
            manifest_event.event_id
        )
        assert validation["status"] == "complete"
        assert validation["runner_call_iteration_link_event_id"] == (
            result.events[0].event_id
        )
        assert validation["manifest_event_id"] == manifest_event.event_id
        assert validation["continuation_limited_signal"] is False


@pytest.mark.parametrize(
    ("message_count", "role_digest", "expected_reason"),
    (
        (
            3,
            runner_role_sequence_digest(("system", "user")),
            "message_count_mismatch",
        ),
        (
            2,
            runner_role_sequence_digest(("user", "system")),
            "role_sequence_digest_mismatch",
        ),
    ),
)
def test_iteration_started_mismatch_fails_closed_after_link(
    tmp_path: Path,
    message_count: int,
    role_digest: str,
    expected_reason: str,
) -> None:
    """prepared manifest 与 Engine observed input 不一致时 fail closed。"""

    expected_digest = runner_role_sequence_digest(("system", "user"))
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        manifest_event = _append_prepared_runner_call_manifest(
            store.transaction_runner,
            seeded,
            event_id=f"event-prepared-runner-call-{expected_reason}",
            runner_call_index=0,
            runner_call_kind="initial_user_dispatch",
            runner_call_trigger_reason="initial_user_input",
            message_count=2,
            role_sequence_digest=expected_digest,
        )
        candidate = _candidate(
            seeded,
            worker_event_index=21,
            data=IterationStartedData(
                iteration_id=f"iter-{expected_reason}",
                iteration_index=0,
                message_count=message_count,
                role_sequence_digest=role_digest,
                runner_input_serializer_schema_version=(
                    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
                ),
            ),
            event_type=EngineEventType.ITERATION_STARTED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)
        replay = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.REJECTED
        assert result.stop_worker_stream is True
        assert [event.event_type for event in result.events] == [
            "RUNNER_CALL_INPUT_ITERATION_LINKED",
            "ENGINE_EVENT_REJECTED",
        ]
        link_payload = _payload(result.events[0])
        rejected_payload = _payload(result.events[1])
        diagnostic = link_payload["diagnostic"]
        assert isinstance(diagnostic, Mapping)

        assert link_payload["manifest_event_id"] == manifest_event.event_id
        assert link_payload["validation_status"] == "mismatch"
        assert diagnostic["reason"] == expected_reason
        assert diagnostic["observed_count"] == message_count
        assert diagnostic["expected_count"] == 2
        assert diagnostic["observed_digest"] == role_digest
        assert diagnostic["expected_digest"] == expected_digest
        assert rejected_payload["reason"] == "runner_call_manifest_mismatch"
        assert rejected_payload["stop_worker_stream"] is True
        assert rejected_payload["runner_call_iteration_link_event_id"] == (
            result.events[0].event_id
        )
        assert rejected_payload["runner_call_manifest_event_id"] == (
            manifest_event.event_id
        )
        assert replay.status == EngineIngestStatus.REJECTED
        assert replay.stop_worker_stream is True
        assert [event.event_type for event in replay.events] == [
            "ENGINE_EVENT_REJECTED",
        ]
        replay_payload = _payload(replay.events[0])
        assert replay_payload["reason"] == "runner_call_manifest_mismatch"
        assert replay_payload["runner_call_iteration_link_event_id"] == (result.events[0].event_id)
        assert replay_payload["runner_call_manifest_event_id"] == (manifest_event.event_id)
        assert (
            _event_count(
                store.transaction_runner,
                "RUNNER_CALL_INPUT_ITERATION_LINKED",
            )
            == 1
        )
        assert _event_count(store.transaction_runner, "ENGINE_EVENT_REJECTED") == 1
        assert _event_count(store.transaction_runner, "ITERATION_STARTED") == 0


def test_iteration_started_missing_initial_manifest_fails_closed(
    tmp_path: Path,
) -> None:
    """首个 iteration 缺少 prepared manifest 时不得降级为 limited signal。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _candidate(
            seeded,
            worker_event_index=22,
            data=IterationStartedData(
                iteration_id="iter-missing-manifest",
                iteration_index=0,
                message_count=1,
                role_sequence_digest=runner_role_sequence_digest(("user",)),
                runner_input_serializer_schema_version=(
                    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
                ),
            ),
            event_type=EngineEventType.ITERATION_STARTED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.REJECTED
        assert result.stop_worker_stream is True
        assert result.events[0].event_type == "ENGINE_EVENT_REJECTED"
        assert _payload(result.events[0])["reason"] == "missing_runner_call_manifest"
        assert _payload(result.events[0])["stop_worker_stream"] is True
        assert _event_count(store.transaction_runner, "RUNNER_CALL_INPUT_ASSEMBLED") == 0
        assert _event_count(store.transaction_runner, "ITERATION_STARTED") == 0


def test_iteration_started_mismatch_link_does_not_seed_continuation(
    tmp_path: Path,
) -> None:
    """mismatch link 属于 rejected path，不能作为 continuation prior observation。"""

    expected_digest = runner_role_sequence_digest(("system", "user"))
    observed_digest = runner_role_sequence_digest(("system", "assistant"))
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        _append_prepared_runner_call_manifest(
            store.transaction_runner,
            seeded,
            event_id="event-prepared-runner-call-mismatch-prior",
            runner_call_index=0,
            runner_call_kind="initial_user_dispatch",
            runner_call_trigger_reason="initial_user_input",
            message_count=2,
            role_sequence_digest=expected_digest,
        )
        mismatch = _candidate(
            seeded,
            worker_event_index=23,
            data=IterationStartedData(
                iteration_id="iter-mismatch-prior",
                iteration_index=0,
                message_count=2,
                role_sequence_digest=observed_digest,
                runner_input_serializer_schema_version=(
                    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
                ),
            ),
            event_type=EngineEventType.ITERATION_STARTED,
        )
        next_iteration = _candidate(
            seeded,
            worker_event_index=24,
            data=IterationStartedData(
                iteration_id="iter-after-mismatch-prior",
                iteration_index=1,
                message_count=4,
                role_sequence_digest=runner_role_sequence_digest(
                    ("system", "user", "assistant", "tool")
                ),
                runner_input_serializer_schema_version=(
                    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
                ),
            ),
            event_type=EngineEventType.ITERATION_STARTED,
        )

        mismatch_result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(mismatch)
        next_result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(next_iteration)

        assert mismatch_result.status == EngineIngestStatus.REJECTED
        assert next_result.status == EngineIngestStatus.REJECTED
        assert next_result.stop_worker_stream is True
        assert [event.event_type for event in next_result.events] == [
            "ENGINE_EVENT_REJECTED",
        ]
        assert _payload(next_result.events[0])["reason"] == (
            "missing_runner_call_manifest"
        )
        assert _event_count(store.transaction_runner, "RUNNER_CALL_INPUT_ASSEMBLED") == 1
        assert (
            _event_count(
                store.transaction_runner,
                "RUNNER_CALL_INPUT_ITERATION_LINKED",
            )
            == 1
        )
        assert _event_count(store.transaction_runner, "ITERATION_STARTED") == 0


def test_iteration_started_rejected_event_does_not_seed_continuation(
    tmp_path: Path,
) -> None:
    """ENGINE_EVENT_REJECTED 不能被 prior observation helper 当作 continuation。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        first = _candidate(
            seeded,
            worker_event_index=23,
            data=IterationStartedData(
                iteration_id="iter-missing-first",
                iteration_index=0,
                message_count=1,
                role_sequence_digest=runner_role_sequence_digest(("user",)),
                runner_input_serializer_schema_version=(
                    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
                ),
            ),
            event_type=EngineEventType.ITERATION_STARTED,
        )
        second = _candidate(
            seeded,
            worker_event_index=24,
            data=IterationStartedData(
                iteration_id="iter-missing-second",
                iteration_index=0,
                message_count=1,
                role_sequence_digest=runner_role_sequence_digest(("user",)),
                runner_input_serializer_schema_version=(
                    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
                ),
            ),
            event_type=EngineEventType.ITERATION_STARTED,
        )

        first_result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(first)
        second_result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(second)

        assert first_result.status == EngineIngestStatus.REJECTED
        assert second_result.status == EngineIngestStatus.REJECTED
        assert _payload(second_result.events[0])["reason"] == (
            "missing_runner_call_manifest"
        )
        assert _event_count(store.transaction_runner, "RUNNER_CALL_INPUT_ASSEMBLED") == 0


def test_iteration_started_ambiguous_prepared_manifest_fails_closed(
    tmp_path: Path,
) -> None:
    """多个 unlinked prepared manifest 无法唯一关联时 fail closed。"""

    role_digest = runner_role_sequence_digest(("system", "user"))
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        _append_prepared_runner_call_manifest(
            store.transaction_runner,
            seeded,
            event_id="event-prepared-runner-call-ambiguous-a",
            runner_call_index=0,
            runner_call_kind="initial_user_dispatch",
            runner_call_trigger_reason="initial_user_input",
            message_count=2,
            role_sequence_digest=role_digest,
        )
        _append_prepared_runner_call_manifest(
            store.transaction_runner,
            seeded,
            event_id="event-prepared-runner-call-ambiguous-b",
            runner_call_index=1,
            runner_call_kind="followup_user_dispatch",
            runner_call_trigger_reason="followup_user_input",
            message_count=2,
            role_sequence_digest=role_digest,
        )
        candidate = _candidate(
            seeded,
            worker_event_index=25,
            data=IterationStartedData(
                iteration_id="iter-ambiguous",
                iteration_index=0,
                message_count=2,
                role_sequence_digest=role_digest,
                runner_input_serializer_schema_version=(
                    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
                ),
            ),
            event_type=EngineEventType.ITERATION_STARTED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.REJECTED
        assert result.stop_worker_stream is True
        assert result.events[0].event_type == "ENGINE_EVENT_REJECTED"
        assert _payload(result.events[0])["reason"] == "ambiguous_runner_call_manifest"
        assert _event_count(store.transaction_runner, "RUNNER_CALL_INPUT_ITERATION_LINKED") == 0
        assert _event_count(store.transaction_runner, "ITERATION_STARTED") == 0


def test_iteration_started_link_conflict_fails_closed(tmp_path: Path) -> None:
    """同一 iteration 的既有 link 与新 observation 冲突时 fail closed。"""

    role_digest = runner_role_sequence_digest(("system", "user"))
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        _append_prepared_runner_call_manifest(
            store.transaction_runner,
            seeded,
            event_id="event-prepared-runner-call-conflict",
            runner_call_index=0,
            runner_call_kind="initial_user_dispatch",
            runner_call_trigger_reason="initial_user_input",
            message_count=2,
            role_sequence_digest=role_digest,
        )
        first = _candidate(
            seeded,
            worker_event_index=26,
            data=IterationStartedData(
                iteration_id="iter-conflict",
                iteration_index=0,
                message_count=2,
                role_sequence_digest=role_digest,
                runner_input_serializer_schema_version=(
                    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
                ),
            ),
            event_type=EngineEventType.ITERATION_STARTED,
        )
        second = _candidate(
            seeded,
            worker_event_index=27,
            data=IterationStartedData(
                iteration_id="iter-conflict",
                iteration_index=0,
                message_count=3,
                role_sequence_digest=role_digest,
                runner_input_serializer_schema_version=(
                    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
                ),
            ),
            event_type=EngineEventType.ITERATION_STARTED,
        )

        accepted = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(first)
        rejected = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(second)

        assert accepted.status == EngineIngestStatus.ACCEPTED
        assert rejected.status == EngineIngestStatus.REJECTED
        assert rejected.stop_worker_stream is True
        assert _payload(rejected.events[0])["reason"] == (
            "runner_call_iteration_link_conflict"
        )
        assert _event_count(store.transaction_runner, "RUNNER_CALL_INPUT_ITERATION_LINKED") == 1


@pytest.mark.parametrize(
    ("runner_call_kind", "trigger_reason"),
    (
        ("followup_user_dispatch", "followup_user_input"),
        ("post_compaction_dispatch", "context_compaction_completed"),
    ),
)
def test_iteration_started_links_all_ordinary_dispatch_kinds(
    tmp_path: Path,
    runner_call_kind: str,
    trigger_reason: str,
) -> None:
    """ordinary dispatch kind 闭集覆盖 followup 与 post-compaction。"""

    role_digest = runner_role_sequence_digest(("system", "user"))
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        manifest_event = _append_prepared_runner_call_manifest(
            store.transaction_runner,
            seeded,
            event_id=f"event-prepared-runner-call-{runner_call_kind}",
            runner_call_index=0,
            runner_call_kind=runner_call_kind,
            runner_call_trigger_reason=trigger_reason,
            message_count=2,
            role_sequence_digest=role_digest,
        )
        candidate = _candidate(
            seeded,
            worker_event_index=28,
            data=IterationStartedData(
                iteration_id=f"iter-{runner_call_kind}",
                iteration_index=0,
                message_count=2,
                role_sequence_digest=role_digest,
                runner_input_serializer_schema_version=(
                    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
                ),
            ),
            event_type=EngineEventType.ITERATION_STARTED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        assert result.events[0].event_type == "RUNNER_CALL_INPUT_ITERATION_LINKED"
        assert _payload(result.events[0])["manifest_event_id"] == (
            manifest_event.event_id
        )
        assert _payload(result.events[0])["runner_call_kind"] == runner_call_kind


def test_iteration_started_does_not_link_compactor_manifest(tmp_path: Path) -> None:
    """compactor proposal manifest 不会被 ordinary link resolution 选中。"""

    role_digest = runner_role_sequence_digest(("system", "user"))
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        _append_prepared_runner_call_manifest(
            store.transaction_runner,
            seeded,
            event_id="event-prepared-runner-call-compactor",
            runner_call_index=0,
            runner_call_kind="compactor_proposal",
            runner_call_trigger_reason="context_compaction_repair_attempt",
            message_count=2,
            role_sequence_digest=role_digest,
            compactor_identity={"compaction_operation_id": "operation-test"},
        )
        candidate = _candidate(
            seeded,
            worker_event_index=29,
            data=IterationStartedData(
                iteration_id="iter-compactor-not-ordinary",
                iteration_index=0,
                message_count=2,
                role_sequence_digest=role_digest,
                runner_input_serializer_schema_version=(
                    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
                ),
            ),
            event_type=EngineEventType.ITERATION_STARTED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.REJECTED
        assert _payload(result.events[0])["reason"] == "missing_runner_call_manifest"
        assert _event_count(store.transaction_runner, "RUNNER_CALL_INPUT_ITERATION_LINKED") == 0


def test_iteration_started_continuation_reset_uses_limited_signal_after_link(
    tmp_path: Path,
) -> None:
    """iteration_index reset 为 0 时不能误匹配已 linked ordinary manifest。"""

    initial_digest = runner_role_sequence_digest(("system", "user"))
    continuation_digest = runner_role_sequence_digest(
        ("system", "user", "assistant", "tool")
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        _append_prepared_runner_call_manifest(
            store.transaction_runner,
            seeded,
            event_id="event-prepared-runner-call-reset",
            runner_call_index=0,
            runner_call_kind="initial_user_dispatch",
            runner_call_trigger_reason="initial_user_input",
            message_count=2,
            role_sequence_digest=initial_digest,
        )
        initial = _candidate(
            seeded,
            worker_event_index=30,
            data=IterationStartedData(
                iteration_id="iter-reset-initial",
                iteration_index=0,
                message_count=2,
                role_sequence_digest=initial_digest,
                runner_input_serializer_schema_version=(
                    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
                ),
            ),
            event_type=EngineEventType.ITERATION_STARTED,
        )
        continuation = _candidate(
            seeded,
            worker_event_index=31,
            data=IterationStartedData(
                iteration_id="iter-reset-continuation",
                iteration_index=0,
                message_count=4,
                role_sequence_digest=continuation_digest,
                runner_input_serializer_schema_version=(
                    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
                ),
            ),
            event_type=EngineEventType.ITERATION_STARTED,
        )

        accepted = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(initial)
        continued = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(continuation)

        assert accepted.status == EngineIngestStatus.ACCEPTED
        assert continued.status == EngineIngestStatus.ACCEPTED
        assert [event.event_type for event in continued.events] == [
            "RUNNER_CALL_INPUT_ASSEMBLED",
            "ITERATION_STARTED",
        ]
        manifest_hot = _payload(continued.events[0])
        preview_payload = _payload(continued.events[1])
        validation = preview_payload["runner_call_manifest_validation"]
        assert isinstance(validation, Mapping)
        assert manifest_hot["runner_call_kind"] == "tool_result_continuation"
        assert manifest_hot["iteration_id"] == "iter-reset-continuation"
        assert manifest_hot["runner_call_index"] == 1
        assert validation["status"] == "limited_signal"
        assert validation["continuation_limited_signal"] is True
        assert validation["manifest_event_id"] == continued.events[0].event_id


def test_iteration_started_writes_limited_runner_call_manifest_for_continuation(
    tmp_path: Path,
) -> None:
    """tool-loop continuation iteration 会写 canonical limited manifest signal。"""

    role_digest = runner_role_sequence_digest(
        ("system", "user", "assistant", "tool")
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        _append_prior_iteration_started_preview(
            store.transaction_runner,
            seeded,
            event_id="event-prior-iteration-preview",
            iteration_id="iter-prior",
            iteration_index=0,
        )
        candidate = _candidate(
            seeded,
            worker_event_index=21,
            data=IterationStartedData(
                iteration_id="iter-continuation",
                iteration_index=1,
                message_count=4,
                role_sequence_digest=role_digest,
                runner_input_serializer_schema_version=(
                    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
                ),
            ),
            event_type=EngineEventType.ITERATION_STARTED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        assert [event.event_type for event in result.events] == [
            "RUNNER_CALL_INPUT_ASSEMBLED",
            "ITERATION_STARTED",
        ]
        assert _event_count(
            store.transaction_runner,
            CONTEXT_BUDGET_EVALUATED,
        ) == 0
        manifest_event = result.events[0]
        preview_event = result.events[1]
        manifest_hot = _payload(manifest_event)
        manifest_body = store.transaction_runner.run_read(
            lambda transaction: event_payload_object(
                transaction,
                manifest_event,
                payload_label="runner-call manifest",
            )
        )
        preview_payload = _payload(preview_event)
        validation = preview_payload["runner_call_manifest_validation"]
        assert isinstance(validation, Mapping)

        assert manifest_event.event_class == EventClass.CANONICAL_FACT
        assert manifest_hot["runner_call_index"] == 0
        assert manifest_hot["runner_call_kind"] == "tool_result_continuation"
        assert manifest_hot["runner_call_trigger_reason"] == "tool_results_available"
        assert manifest_hot["iteration_id"] == "iter-continuation"
        assert manifest_hot["message_count"] == 4
        assert manifest_hot["role_sequence_digest"] == role_digest
        assert manifest_hot["validation_status"] == "limited_signal"
        assert manifest_hot["diagnostic"] == {
            "status": "limited_signal",
            "reason": "missing_projection_artifact",
            "missing_atom_kind": None,
            "missing_ref_kind": "artifact_ref",
            "missing_ref": None,
            "observed_count": 4,
            "expected_count": None,
            "observed_digest": role_digest,
            "expected_digest": None,
            "consumer_boundary": "host.engine_ingest",
        }
        assert manifest_body["manifest_id"] == (
            f"runner-call-manifest:{manifest_event.event_id}"
        )
        assert manifest_body["message_entries"] == []
        assert manifest_body["message_count"] == 4
        assert manifest_event.payload_ref == manifest_hot["manifest_payload_ref"]
        assert manifest_event.payload_digest == manifest_hot["manifest_digest"]
        assert validation["status"] == "limited_signal"
        assert validation["reason"] == "missing_projection_artifact"
        assert validation["observed_count"] == 4
        assert validation["observed_digest"] == role_digest


def test_iteration_started_continuation_with_projection_writes_complete_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """complete tool-loop continuation在同事务消费typed anchor。

    :param tmp_path: pytest临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    """

    observed_queries: list[ContextAnchorQuery] = []

    def resolve_anchor(
        transaction: HostTransaction,
        event_log_store: EventLogStore,
        query: ContextAnchorQuery,
    ) -> ContextAnchorResolution:
        """注入compatible continuation anchor。

        :param transaction: 当前ingest transaction。
        :param event_log_store: EventLog primitive。
        :param query: complete continuation query。
        :returns: compatible anchor。
        """

        del transaction, event_log_store
        observed_queries.append(query)
        return ContextAnchorResolution(
            anchor=CompatibleContextAnchor(
                manifest_event_id="event-anchor",
                manifest_payload_ref="payload-anchor",
                manifest_digest=sha256_digest_json({"anchor": "manifest"}),
                iteration_link_event_id="event-anchor-link",
                usage_event_id="event-anchor-usage",
                usage_observation_digest=sha256_digest_json(
                    {"anchor": "usage"}
                ),
                iteration_completed_event_id="event-anchor-completed",
                usage_anchor_tokens=100,
                conservative_anchor_tokens=100,
            ),
            fallback_reason=None,
        )

    monkeypatch.setattr(
        engine_ingest_module,
        "resolve_context_anchor",
        resolve_anchor,
    )

    role_digest = runner_role_sequence_digest(
        ("system", "user", "assistant", "tool")
    )
    input_projection = (
        RunnerInputMessageProjection(
            index=0,
            role="system",
            content="# 当前时间\n2026-07-07\n# 当前分析对象\nV（Visa Inc.）",
            tool_call_id=None,
            tool_calls=(),
        ),
        RunnerInputMessageProjection(
            index=1,
            role="user",
            content="分析 Visa",
            tool_call_id=None,
            tool_calls=(),
        ),
        RunnerInputMessageProjection(
            index=2,
            role="assistant",
            content=None,
            tool_call_id=None,
            tool_calls=(
                RunnerInputToolCallProjection(
                    tool_call_id="call-time",
                    name="get_current_time",
                    arguments={"timezone": "Asia/Shanghai"},
                ),
            ),
        ),
        RunnerInputMessageProjection(
            index=3,
            role="tool",
            content='{"current_time":"2026-07-07 19:18:11","payload":"'
            + ("y" * 5000)
            + '"}',
            tool_call_id="call-time",
            tool_calls=(),
        ),
    )
    with open_host_durable_store(
        _options(tmp_path, payload_inline_threshold_bytes=4096)
    ) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
            source_complete_sizing=True,
        )
        _link_pre_start_runner_call_manifest(
            store.transaction_runner,
            seeded,
            iteration_id="iter-prior-complete",
            worker_event_index=1,
        )
        candidate = _candidate(
            seeded,
            worker_event_index=25,
            data=IterationStartedData(
                iteration_id="iter-continuation-complete",
                iteration_index=1,
                message_count=4,
                role_sequence_digest=role_digest,
                runner_input_serializer_schema_version=(
                    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
                ),
                input_projection=input_projection,
            ),
            event_type=EngineEventType.ITERATION_STARTED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED, result.reason
        assert tuple(event.event_type for event in result.events) == (
            "RUNNER_CALL_INPUT_ASSEMBLED",
            CONTEXT_BUDGET_EVALUATED,
            "ITERATION_STARTED",
        )
        manifest_hot = _payload(result.events[0])
        budget_payload = parse_context_budget_evaluated_payload(
            _payload(result.events[1])
        )
        preview_payload = _payload(result.events[2])
        validation = preview_payload["runner_call_manifest_validation"]
        assert isinstance(validation, Mapping)
        assert manifest_hot["validation_status"] == "complete"
        assert (
            budget_payload.sizing_stage
            is ContextSizingStage.CONTINUATION
        )
        assert (
            budget_payload.budget_decision
            is ContextBudgetDecision.ALLOW_DISPATCH
        )
        assert budget_payload.estimate_method is (
            ContextEstimateMethod.USAGE_ANCHORED
        )
        assert budget_payload.anchor_diagnostic is not None
        assert len(observed_queries) == 1
        assert observed_queries[0].candidate_input_cursor == (
            result.events[0].event_sequence - 1
        )
        hot_diagnostic = _json_object(manifest_hot["diagnostic"])
        assert hot_diagnostic["status"] == "complete"
        assert hot_diagnostic["reason"] is None
        assert manifest_hot["runner_call_projection_artifact_ref"] is not None
        assert validation["status"] == "complete"
        assert validation["continuation_limited_signal"] is False
        manifest_body = store.transaction_runner.run_read(
            lambda transaction: event_payload_object(
                transaction,
                result.events[0],
                payload_label="runner-call manifest",
            )
        )
        message_entries = _json_object_sequence(manifest_body["message_entries"])
        projector_metadata = _json_object_sequence(
            manifest_body["projector_metadata"]
        )
        assert len(message_entries) == 4
        assert len(projector_metadata) == 1
        projector_metadata_ids: set[str] = set()
        for item in projector_metadata:
            metadata_id = item["projector_metadata_id"]
            assert isinstance(metadata_id, str)
            projector_metadata_ids.add(metadata_id)
        assert all(
            entry["projector_metadata_id"] in projector_metadata_ids
            for entry in message_entries
        )
        assert frozenset(projector_metadata[0]) == frozenset(
            {
                "projector_metadata_id",
                "projector_id",
                "projector_schema_version",
                "projector_digest",
                "purpose",
                "source_contract_refs",
            }
        )
        assert "projector_metadata_summary" not in manifest_hot
        projection_ref = manifest_hot["runner_call_projection_artifact_ref"]
        projection_digest = manifest_hot["runner_call_projection_artifact_digest"]
        assert isinstance(projection_ref, str)
        assert isinstance(projection_digest, str)
        projection_descriptor = store.transaction_runner.run_read(
            lambda transaction: PayloadStore().read_payload_descriptor(
                transaction,
                projection_ref,
            )
        )
        assert projection_descriptor is not None
        assert projection_descriptor.payload_kind is PayloadKind.ARTIFACT_REF
        projection_payload = store.transaction_runner.run_read(
            lambda transaction: read_tool_trace_json_payload(
                transaction,
                projection_ref,
                expected_digest=projection_digest,
            )
        )
        projection_messages = _json_object_sequence(
            projection_payload.payload["messages"]
        )
        assert len(projection_messages) == len(message_entries)
        for message, entry in zip(projection_messages, message_entries, strict=True):
            assert message["index"] == entry["index"]
            assert message["role"] == entry["role"]
            assert message["content_digest"] == entry["content_digest"]
            assert entry["projection_artifact_ref"] == projection_ref
            assert entry["projection_artifact_digest"] == projection_digest


@pytest.mark.parametrize(
    ("failure_kind", "expected_reason"),
    (
        (
            "projection",
            "continuation_projection_unavailable",
        ),
        (
            "tool",
            "continuation_tool_schema_unavailable",
        ),
        (
            "policy",
            "continuation_policy_unavailable",
        ),
        (
            "request",
            "continuation_request_semantics_unavailable",
        ),
    ),
)
def test_continuation_source_failure_projects_typed_closed_reason(
    tmp_path: Path,
    failure_kind: str,
    expected_reason: str,
) -> None:
    """continuation 按 projection→tool→policy→request 投影 typed closed reason。

    :param tmp_path: pytest 临时目录。
    :param failure_kind: 单一 source failure 类别。
    :param expected_reason: manifest sizing 应记录的 closed reason。
    """

    input_projection = (
        RunnerInputMessageProjection(
            index=0,
            role="system",
            content="system",
            tool_call_id=None,
            tool_calls=(),
        ),
        RunnerInputMessageProjection(
            index=1,
            role="user",
            content="user",
            tool_call_id=None,
            tool_calls=(),
        ),
    )
    role_digest = runner_role_sequence_digest(("system", "user"))
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
            source_tool_schema=(
                _reactive_source_tool_schema()
                if failure_kind == "tool"
                else None
            ),
            source_complete_sizing=True,
            source_request_semantics_digest_override=(
                sha256_digest_json({"request": "corrupt"})
                if failure_kind == "request"
                else None
            ),
        )
        _link_pre_start_runner_call_manifest(
            store.transaction_runner,
            seeded,
            worker_event_index=69,
            iteration_id=f"iter-prior-{failure_kind}",
        )
        if failure_kind in {"projection", "policy"}:
            _tamper_reactive_source(
                store.transaction_runner,
                seeded=seeded,
                tamper_kind=_ReactiveSourceTamperKind.EFFECTIVE_CONFIG_MISSING,
            )
        elif failure_kind == "tool":
            _tamper_reactive_source(
                store.transaction_runner,
                seeded=seeded,
                tamper_kind=_ReactiveSourceTamperKind.TOOL_SNAPSHOT_MISSING,
            )
        candidate = _candidate(
            seeded,
            worker_event_index=70,
            data=IterationStartedData(
                iteration_id=f"iter-continuation-{failure_kind}",
                iteration_index=1,
                message_count=2,
                role_sequence_digest=role_digest,
                runner_input_serializer_schema_version=(
                    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
                ),
                input_projection=(
                    () if failure_kind == "projection" else input_projection
                ),
            ),
            event_type=EngineEventType.ITERATION_STARTED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status is EngineIngestStatus.ACCEPTED
        assert result.events[0].event_type == "RUNNER_CALL_INPUT_ASSEMBLED"
        hot = parse_runner_call_hot_payload(_payload(result.events[0]))
        manifest_body = store.transaction_runner.run_read(
            lambda transaction: sqlite_payload_object(
                transaction,
                payload_ref=hot.manifest_payload_ref,
                payload_digest=hot.manifest_digest,
                payload_label="continuation source failure manifest",
            )
        )
        sizing = manifest_body["sizing_snapshot"]
        assert isinstance(sizing, Mapping)
        assert sizing["status"] == "unavailable"
        assert sizing["reason"] == expected_reason


def test_source_loader_ignores_valid_continuation_manifest(
    tmp_path: Path,
) -> None:
    """同 Attempt 的 continuation manifest 不参与 pre-start duplicate 判定。"""

    projection = (
        RunnerInputMessageProjection(
            index=0,
            role="system",
            content="system",
            tool_call_id=None,
            tool_calls=(),
        ),
        RunnerInputMessageProjection(
            index=1,
            role="user",
            content="user",
            tool_call_id=None,
            tool_calls=(),
        ),
    )
    role_digest = runner_role_sequence_digest(("system", "user"))
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
            source_complete_sizing=True,
        )
        _link_pre_start_runner_call_manifest(
            store.transaction_runner,
            seeded,
            iteration_id="iter-prior-source-loader",
            worker_event_index=70,
        )
        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(
            _candidate(
                seeded,
                worker_event_index=71,
                data=IterationStartedData(
                    iteration_id="iter-source-loader-continuation",
                    iteration_index=1,
                    message_count=2,
                    role_sequence_digest=role_digest,
                    runner_input_serializer_schema_version=(
                        RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
                    ),
                    input_projection=projection,
                ),
                event_type=EngineEventType.ITERATION_STARTED,
            )
        )

        assert result.status is EngineIngestStatus.ACCEPTED
        source = store.transaction_runner.run_read(
            lambda transaction: load_prepared_runner_call_source_in_transaction(
                transaction,
                EventLogStore(),
                run_id=seeded.run_id,
                attempt_id=seeded.attempt_id,
                execution_id=seeded.execution_id,
            )
        )
        assert source.manifest.identity.iteration_id is None
        assert source.manifest.identity.iteration_index is None


def test_source_loader_rejects_two_pre_start_manifests(
    tmp_path: Path,
) -> None:
    """同 Attempt/execution 两个 pre-start manifest 必须 fail duplicate。"""

    role_digest = runner_role_sequence_digest(("system", "user"))
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
            source_complete_sizing=True,
        )
        _append_prepared_runner_call_manifest(
            store.transaction_runner,
            seeded,
            event_id="event-second-pre-start-manifest",
            runner_call_index=1,
            runner_call_kind="followup_user_dispatch",
            runner_call_trigger_reason="followup_user_input",
            message_count=2,
            role_sequence_digest=role_digest,
        )

        with pytest.raises(PreparedRunnerCallSourceError) as exc_info:
            store.transaction_runner.run_read(
                lambda transaction: load_prepared_runner_call_source_in_transaction(
                    transaction,
                    EventLogStore(),
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    execution_id=seeded.execution_id,
                )
            )

        assert (
            exc_info.value.category
            is PreparedRunnerCallSourceFailureCategory.TOOL_SCHEMA
        )


def test_source_loader_rejects_eventlog_hot_identity_mismatch(
    tmp_path: Path,
) -> None:
    """manifest EventLog row 与 hot attempt identity 错配时 fail closed。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
            source_complete_sizing=True,
        )

        def _corrupt_row(transaction: HostTransaction) -> None:
            """只篡改 canonical EventLog row identity。

            :param transaction: Host write transaction。
            :returns: ``None``。
            """

            result = transaction.execute(
                f"""
                UPDATE {TABLE_EVENT_LOG}
                SET attempt_id = ?
                WHERE event_type = ?
                  AND attempt_id = ?
                  AND execution_id = ?
                """,
                (
                    "attempt-corrupt",
                    "RUNNER_CALL_INPUT_ASSEMBLED",
                    seeded.attempt_id,
                    seeded.execution_id,
                ),
            )
            assert result.rowcount == 1

        store.transaction_runner.run_write(_corrupt_row)
        with pytest.raises(PreparedRunnerCallSourceError) as exc_info:
            store.transaction_runner.run_read(
                lambda transaction: load_prepared_runner_call_source_in_transaction(
                    transaction,
                    EventLogStore(),
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    execution_id=seeded.execution_id,
                )
            )

        assert (
            exc_info.value.category
            is PreparedRunnerCallSourceFailureCategory.TOOL_SCHEMA
        )


def test_source_loader_prioritizes_tool_failure_over_policy_failure(
    tmp_path: Path,
) -> None:
    """同一 source 的 tool 与 policy 同时损坏时稳定归属 TOOL_SCHEMA。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
            source_tool_schema=_reactive_source_tool_schema(),
            source_complete_sizing=True,
        )
        _tamper_reactive_source(
            store.transaction_runner,
            seeded=seeded,
            tamper_kind=_ReactiveSourceTamperKind.TOOL_SNAPSHOT_MISSING,
        )
        _tamper_reactive_source(
            store.transaction_runner,
            seeded=seeded,
            tamper_kind=_ReactiveSourceTamperKind.EFFECTIVE_CONFIG_MISSING,
        )

        with pytest.raises(PreparedRunnerCallSourceError) as exc_info:
            store.transaction_runner.run_read(
                lambda transaction: load_prepared_runner_call_source_in_transaction(
                    transaction,
                    EventLogStore(),
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    execution_id=seeded.execution_id,
                )
            )

        assert (
            exc_info.value.category
            is PreparedRunnerCallSourceFailureCategory.TOOL_SCHEMA
        )


def test_source_loader_reports_policy_after_valid_tool_source(
    tmp_path: Path,
) -> None:
    """tool-owned source 完整而 exact policy 损坏时返回 POLICY。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            record_source_candidate=True,
            source_tool_schema=_reactive_source_tool_schema(),
            source_complete_sizing=True,
        )
        _tamper_reactive_source(
            store.transaction_runner,
            seeded=seeded,
            tamper_kind=_ReactiveSourceTamperKind.EFFECTIVE_CONFIG_MISSING,
        )

        with pytest.raises(PreparedRunnerCallSourceError) as exc_info:
            store.transaction_runner.run_read(
                lambda transaction: load_prepared_runner_call_source_in_transaction(
                    transaction,
                    EventLogStore(),
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    execution_id=seeded.execution_id,
                )
            )

        assert (
            exc_info.value.category
            is PreparedRunnerCallSourceFailureCategory.POLICY
        )


@pytest.mark.parametrize("tamper_kind", tuple(_EngineHotTamperKind))
def test_engine_ingest_rejects_invalid_runner_call_hot_payload(
    tmp_path: Path,
    tamper_kind: _EngineHotTamperKind,
) -> None:
    """Engine ingest 不得为损坏 hot row 合成 complete diagnostic。

    :param tmp_path: pytest 临时目录。
    :param tamper_kind: diagnostic、旧数组或跨字段冲突分类。
    :returns: ``None``。
    :raises AssertionError: Engine consumer 接受损坏 hot payload 时抛出。
    """

    role_digest = runner_role_sequence_digest(("system", "user"))
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        event = _append_prepared_runner_call_manifest(
            store.transaction_runner,
            seeded,
            event_id=f"event-engine-hot-{tamper_kind.value}",
            runner_call_index=0,
            runner_call_kind="initial_user_dispatch",
            runner_call_trigger_reason="initial_user_input",
            message_count=2,
            role_sequence_digest=role_digest,
        )
        payload: dict[str, JsonValue] = dict(_payload(event))
        diagnostic_value = payload["diagnostic"]
        assert isinstance(diagnostic_value, Mapping)
        diagnostic: dict[str, JsonValue] = dict(diagnostic_value)
        if tamper_kind is _EngineHotTamperKind.MISSING_DIAGNOSTIC:
            del payload["diagnostic"]
        elif tamper_kind is _EngineHotTamperKind.NULL_DIAGNOSTIC:
            payload["diagnostic"] = None
        elif tamper_kind is _EngineHotTamperKind.MALFORMED_DIAGNOSTIC:
            payload["diagnostic"] = []
        elif tamper_kind is _EngineHotTamperKind.LEGACY_METADATA_ARRAY:
            payload["projector_metadata_summary"] = []
        elif tamper_kind is _EngineHotTamperKind.STATUS_MISMATCH:
            payload["validation_status"] = "limited_signal"
        elif tamper_kind is _EngineHotTamperKind.COUNT_MISMATCH:
            diagnostic["observed_count"] = 3
            payload["diagnostic"] = diagnostic
        else:
            diagnostic["expected_digest"] = sha256_digest_json(
                {"roles": ["tampered"]}
            )
            payload["diagnostic"] = diagnostic

        with pytest.raises(HostDurableError):
            engine_ingest_module._runner_call_payload_diagnostic(
                payload,
                consumer_boundary="engine_ingest_test",
            )


def test_iteration_completed_preview_includes_client_correlation_id(
    tmp_path: Path,
) -> None:
    """iteration completed preview 同步暴露 provider 与 client correlation。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _candidate(
            seeded,
            worker_event_index=20,
            data=IterationCompletedData(
                iteration_id="iter-completed",
                finish_reason=FinishReason.STOP,
                provider_request_id="req-iteration",
                client_correlation_id="client-iteration",
            ),
            event_type=EngineEventType.ITERATION_COMPLETED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
            transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        assert result.events[0].event_class == EventClass.PREVIEW
        payload = _payload(result.events[0])
        assert payload["provider_request_id"] == "req-iteration"
        assert payload["client_correlation_id"] == "client-iteration"


def _options(
    tmp_path: Path, *, payload_inline_threshold_bytes: int = 65536
) -> HostDurableStoreOptions:
    """构造测试 durable store options。

    :param tmp_path: pytest 临时目录。
    :param payload_inline_threshold_bytes: payload inline 阈值。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(
            artifact_root=tmp_path / "artifacts",
            payload_inline_threshold_bytes=payload_inline_threshold_bytes,
        ),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=0.25,
            write_busy_retry_count=3,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.01,
        ),
    )


def _seed_active_run(
    transaction_runner: HostTransactionRunner,
    *,
    display_text: str = "hello",
    record_source_candidate: bool = False,
    source_tool_schema: ToolSchema | None = None,
    source_complete_sizing: bool = False,
    source_request_semantics_digest_override: str | None = None,
) -> _SeededRun:
    """创建已 worker accepted 的 active Run。

    :param transaction_runner: Host transaction runner。
    :param display_text: 当前用户输入展示文本。
    :param record_source_candidate: 是否记录 reactive recovery 所需的
        strict source candidate/manifest。
    :param source_tool_schema: 可选 source frozen tool schema。
    :param source_complete_sizing: 是否记录 continuation 可消费的完整 sizing。
    :param source_request_semantics_digest_override: 可选 source sizing request
        semantics 摘要覆盖值，用于反例。
    :returns: seeded run。
    """

    session_id = ensure_session(
        transaction_runner,
        EnsureSessionRequest(scope="workspace", slot_key="engine-ingest", metadata=()),
    ).snapshot.session_id
    seeded = _SeededRun(
        session_id=session_id,
        run_id="run-ingest",
        attempt_id="attempt-ingest",
        execution_id="execution-ingest",
        dispatch_record_id="dispatch-ingest",
    )
    policy_snapshot, effective_execution_config = (
        _source_policy_snapshot_and_config(
            allow_tool_calls=source_tool_schema is not None,
        )
    )

    def _operation(transaction: HostTransaction) -> None:
        register_current_instance(
            transaction,
            HostInstanceIdentity(
                host_instance_id="host-test",
                pid=1,
                process_start_token="test-process",
                boot_id=None,
            ),
        )
        input_event = (
            EventLogStore()
            .append_event(
                transaction,
                EventLogAppendRequest(
                    event_id="event-input-ingest",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=session_id,
                    run_id=seeded.run_id,
                    attempt_id=None,
                    execution_id=None,
                    event_type="USER_INPUT_ACCEPTED",
                    occurred_at=_NOW,
                    actor="tester",
                    source="pytest",
                    client_request_id="client-ingest",
                    idempotency_key="idem-ingest-input",
                    policy_decision=None,
                    reason=None,
                    payload_json={
                        "display_text": display_text,
                        "operation_kind": "analysis",
                        "effective_execution_config": (
                            effective_execution_config
                        ),
                    },
                    payload_ref=None,
                    payload_digest=None,
                ),
            )
            .row
        )
        create_running_run_with_starting_attempt_in_transaction(
            transaction,
            EventLogStore(),
            CreateRunningRunInput(
                session_id=session_id,
                run_id=seeded.run_id,
                client_request_id="client-ingest",
                input_event_id=input_event.event_id,
                input_event_sequence=input_event.event_sequence,
                run_accepted_event_id="event-run-accepted-ingest",
                run_started_event_id="event-run-started-ingest",
                attempt_started_event_id="event-attempt-started-ingest",
                attempt_id=seeded.attempt_id,
                execution_id=seeded.execution_id,
                dispatch_record_id=seeded.dispatch_record_id,
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                idempotency_key="idem-ingest",
                execution_target="target-ingest",
                queue_policy=RunQueuePolicy.QUEUE,
                start_reason=RunStartReason.INITIAL,
                worker_kind=WorkerKind.LOCAL,
                owner_host_instance_id=None,
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )
        mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id=seeded.attempt_id,
            owner_host_instance_id="host-test",
            lane_name="llm",
            waiting_for_lane_at="2026-05-15T01:02:03.000000Z",
        )
        mark_dispatching_after_lane_row(
            transaction,
            attempt_id=seeded.attempt_id,
            owner_host_instance_id="host-test",
            lane_name="llm",
            lane_claim_id="claim-test",
            lane_owner_id="owner-test",
            lane_acquired_at="2026-05-15T01:02:03.000000Z",
            dispatching_at="2026-05-15T01:02:03.000000Z",
        )
        accept_worker_running_in_transaction(
            transaction,
            EventLogStore(),
            AcceptWorkerRunningInput(
                run_id=seeded.run_id,
                attempt_id=seeded.attempt_id,
                attempt_running_event_id="event-attempt-running-ingest",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                worker_accept_reason="accepted",
            ),
        )

    transaction_runner.run_write(_operation)
    if not record_source_candidate:
        return seeded
    required_cursor = transaction_runner.run_read(
        lambda transaction: EventLogStore()
        .read_events_after(transaction, 0, limit=100)[-1]
        .event_sequence
    )
    catch_up = catch_up_conversation_memory_projection(
        transaction_runner,
        policy=default_memory_projection_policy(),
        batch_size=100,
        max_event_sequence=required_cursor,
    )
    assert catch_up.target_reached is True

    def _record_source_candidate(transaction: HostTransaction) -> None:
        """记录与 source Attempt 严格配对的 frozen candidate。

        :param transaction: Host write transaction。
        :returns: ``None``。
        :raises AssertionError: source Run 缺失时抛出。
        :raises HostDurableError: candidate 或 manifest contract 非法时抛出。
        """

        run = read_run_by_id(transaction, seeded.run_id)
        assert run is not None
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
            tool_schemas=(
                ()
                if source_tool_schema is None
                else (source_tool_schema,)
            ),
            disable_tools=source_tool_schema is None,
            tool_execution_mode=(
                ToolExecutionMode.NO_TOOL_DISABLED
                if source_tool_schema is None
                else ToolExecutionMode.TOOL_ENABLED
            ),
            memory_projection_policy=default_memory_projection_policy(),
        )
        start_input = StartGovernedRunInput(
            run_id=seeded.run_id,
            expected_status=RunStatus.ACCEPTED,
            run_started_event_id="event-run-started-ingest",
            attempt_started_event_id="event-attempt-started-ingest",
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
        sizing_snapshot: RunnerCallSizingSnapshot
        source_estimator_digest = sha256_digest_json(
            {"estimate": "source"}
        )
        source_policy_digest = sha256_digest_json(
            {"context_policy": "source"}
        )
        if source_complete_sizing:
            sizing_snapshot = complete_runner_call_sizing_snapshot(
                sizing_stage=ContextSizingStage.ORDINARY,
                estimator_id=CONTEXT_ESTIMATOR_CONTRACT.estimator_id,
                estimator_version=CONTEXT_ESTIMATOR_CONTRACT.estimator_version,
                estimator_digest=source_estimator_digest,
                conservative_input_tokens=128,
                context_window_size=32768,
                provider=candidate.policy_snapshot.runner_spec.provider,
                model=candidate.policy_snapshot.runner_spec.model,
                request_semantics_digest=(
                    source_request_semantics_digest_override
                    if source_request_semantics_digest_override is not None
                    else candidate.request_semantics_digest
                ),
                input_snapshot_digest=candidate.input_snapshot_digest,
                policy_ref="context-policy:source",
                policy_snapshot_digest=source_policy_digest,
            )
        else:
            sizing_snapshot = unavailable_runner_call_sizing_snapshot(
                RunnerCallSizingUnavailableReason.CONTEXT_POLICY_UNAVAILABLE,
                sizing_stage=ContextSizingStage.ORDINARY,
            )
        manifest_event = record_prepared_runner_call_candidate_in_transaction(
            transaction,
            EventLogStore(),
            PayloadStore(),
            run=run,
            attempt_id=start_input.attempt_id,
            execution_id=start_input.execution_id,
            occurred_at=start_input.occurred_at,
            candidate=candidate,
            sizing_snapshot=sizing_snapshot,
        )
        if source_complete_sizing:
            append_context_budget_evaluated_in_transaction(
                transaction,
                EventLogStore(),
                session_id=seeded.session_id,
                run_id=seeded.run_id,
                attempt_id=seeded.attempt_id,
                execution_id=seeded.execution_id,
                occurred_at=_NOW,
                result=build_conservative_context_sizing_result_from_atoms(
                    stage=ContextSizingStage.ORDINARY,
                    candidate_input_cursor=candidate.candidate_input_cursor,
                    candidate_input_projection_ref=(
                        candidate.candidate_input_projection_ref
                    ),
                    candidate_input_digest=candidate.input_snapshot_digest,
                    estimator_contract=ContextEstimatorContract(
                        estimator_id=(
                            CONTEXT_ESTIMATOR_CONTRACT.estimator_id
                        ),
                        estimator_version=(
                            CONTEXT_ESTIMATOR_CONTRACT.estimator_version
                        ),
                    ),
                    estimator_digest=source_estimator_digest,
                    conservative_input_tokens=128,
                    context_window_size=32_768,
                    soft_threshold_tokens=20_000,
                    hard_threshold_tokens=30_000,
                    policy_ref="context-policy:source",
                    policy_snapshot_digest=source_policy_digest,
                ),
            )
            assert manifest_event.event_sequence > (
                candidate.candidate_input_cursor
            )

    transaction_runner.run_write(_record_source_candidate)
    return seeded


def _source_policy_snapshot_and_config(
    *,
    allow_tool_calls: bool = False,
) -> tuple[PolicySnapshot, JsonValue]:
    """构造 reactive source 共用的冻结 policy 与 durable JSON。

    :param allow_tool_calls: frozen Agent policy 是否允许工具。
    :returns: typed policy snapshot 与 ``effective_execution_config`` JSON。
    :raises HostDurableError: 生产投影 helper 无法还原刚构造的 JSON 时抛出。
    """

    runner_spec = _runner_spec()
    runner_options = RunnerCallOptions(
        temperature=None,
        max_tokens=None,
        top_p=None,
        stream=False,
    )
    agent_policy = AgentPolicy(
        max_iterations=3,
        continuation_max_attempts=1,
        allow_tool_calls=allow_tool_calls,
        tool_execution_timeout_seconds=1.0,
        fallback_prompt="test fallback prompt",
        continuation_prompt="test continuation prompt",
    )
    config = effective_execution_config_json(
        runner_spec=runner_spec,
        runner_options=runner_options,
        agent_policy=agent_policy,
        runner_spec_source="test",
        runner_options_source="test",
        agent_policy_source="test",
    )
    snapshot = effective_execution_snapshot_from_json(config)
    return (
        PolicySnapshot(
            runner_spec=snapshot.runner_spec,
            runner_options=snapshot.runner_options,
            agent_policy=snapshot.agent_policy,
            policy_snapshot_ref=snapshot.policy_snapshot_ref,
        ),
        config,
    )


def _reactive_source_tool_schema() -> ToolSchema:
    """构造用于验证 source frozen tool snapshot 的业务 schema。

    :returns: 单参数测试工具 schema。
    """

    properties: dict[str, JsonValue] = {
        "ticker": {"type": "string"},
    }
    return ToolSchema(
        type="function",
        function=ToolFunctionSchema(
            name="lookup_filing",
            description="按股票代码查询财报。",
            parameters=ToolParametersSchema(
                type="object",
                properties=properties,
                required=("ticker",),
                additional_properties=False,
            ),
        ),
    )


def _steer_to_new_running_attempt(
    transaction_runner: HostTransactionRunner, seeded: _SeededRun
) -> _SeededRun:
    """把 seeded active Run 切换为 steer 后的新 running Attempt。

    :param transaction_runner: Host transaction runner。
    :param seeded: 原 active Run 摘要。
    :returns: steer 后的新 current Attempt 摘要。
    """

    current = _SeededRun(
        session_id=seeded.session_id,
        run_id=seeded.run_id,
        attempt_id="attempt-ingest-steered-current",
        execution_id="execution-ingest-steered-current",
        dispatch_record_id="dispatch-ingest-steered-current",
    )

    def _event(
        transaction: HostTransaction,
        *,
        event_id: str,
        event_type: str,
        attempt_id: str | None,
        execution_id: str | None,
        payload_json: JsonValue,
    ) -> EventLogRow:
        """追加 steer 测试 setup 事件。

        :param transaction: Host transaction。
        :param event_id: 事件 id。
        :param event_type: 事件类型。
        :param attempt_id: Attempt id。
        :param execution_id: execution id。
        :param payload_json: JSON payload。
        :returns: 新写入的 EventLog row。
        """

        return (
            EventLogStore()
            .append_event(
                transaction,
                EventLogAppendRequest(
                    event_id=event_id,
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    attempt_id=attempt_id,
                    execution_id=execution_id,
                    event_type=event_type,
                    occurred_at=_NOW,
                    actor="tester",
                    source="pytest",
                    client_request_id="client-ingest-steer",
                    idempotency_key=f"idem-{event_id}",
                    policy_decision=None,
                    reason=None,
                    payload_json=payload_json,
                    payload_ref=None,
                    payload_digest=None,
                ),
            )
            .row
        )

    def _operation(transaction: HostTransaction) -> None:
        timestamp = format_utc_timestamp(_NOW)
        input_event = _event(
            transaction,
            event_id="event-input-ingest-steer",
            event_type="USER_INPUT_ACCEPTED",
            attempt_id=None,
            execution_id=None,
            payload_json={"display_text": "steer"},
        )
        steered_event = _event(
            transaction,
            event_id="event-attempt-steered-ingest",
            event_type="ATTEMPT_STEERED",
            attempt_id=seeded.attempt_id,
            execution_id=seeded.execution_id,
            payload_json={"reason": "steered"},
        )
        run_started_event = _event(
            transaction,
            event_id="event-run-started-ingest-steer",
            event_type="RUN_STARTED",
            attempt_id=None,
            execution_id=None,
            payload_json={"reason": "steer"},
        )
        attempt_started_event = _event(
            transaction,
            event_id="event-attempt-started-ingest-steer",
            event_type="ATTEMPT_STARTED",
            attempt_id=current.attempt_id,
            execution_id=current.execution_id,
            payload_json={"reason": "steer"},
        )
        steer_running_attempt_row(
            transaction,
            attempt_id=seeded.attempt_id,
            terminal_event_id=steered_event.event_id,
            terminal_event_sequence=steered_event.event_sequence,
            terminal_at=timestamp,
        )
        insert_attempt(
            transaction,
            AttemptRow(
                attempt_id=current.attempt_id,
                run_id=current.run_id,
                execution_id=current.execution_id,
                status=AttemptStatus.STARTING,
                started_event_id=attempt_started_event.event_id,
                started_event_sequence=attempt_started_event.event_sequence,
                terminal_event_id=None,
                terminal_event_sequence=None,
                created_at=timestamp,
                updated_at=timestamp,
                terminal_at=None,
            ),
        )
        insert_dispatch_record(
            transaction,
            DispatchRecordRow(
                dispatch_record_id=current.dispatch_record_id,
                run_id=current.run_id,
                attempt_id=current.attempt_id,
                execution_id=current.execution_id,
                status=DispatchRecordStatus.DISPATCHING,
                worker_kind=WorkerKind.LOCAL,
                execution_target="target-ingest",
                owner_host_instance_id="host-test",
                created_event_id=attempt_started_event.event_id,
                created_event_sequence=attempt_started_event.event_sequence,
                waiting_for_lane_at=timestamp,
                lane_name="llm",
                lane_claim_id="claim-test-steer",
                lane_owner_id="owner-test-steer",
                lane_acquired_at=timestamp,
                dispatching_at=timestamp,
                worker_accepted_at=None,
                worker_accept_event_id=None,
                worker_accept_event_sequence=None,
                cancelled_event_id=None,
                cancelled_event_sequence=None,
                created_at=timestamp,
                updated_at=timestamp,
                cancelled_at=None,
            ),
        )
        steer_active_run_row(
            transaction,
            session_id=seeded.session_id,
            run_id=seeded.run_id,
            previous_attempt_id=seeded.attempt_id,
            next_attempt_id=current.attempt_id,
            input_event_id=input_event.event_id,
            input_event_sequence=input_event.event_sequence,
            started_event_id=run_started_event.event_id,
            started_event_sequence=run_started_event.event_sequence,
            updated_at=timestamp,
        )
        accept_worker_running_in_transaction(
            transaction,
            EventLogStore(),
            AcceptWorkerRunningInput(
                run_id=current.run_id,
                attempt_id=current.attempt_id,
                attempt_running_event_id="event-attempt-running-ingest-steer",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                worker_accept_reason="accepted",
            ),
        )

    transaction_runner.run_write(_operation)
    return current


def _candidate(
    seeded: _SeededRun,
    *,
    worker_event_index: int,
    data: EngineEventData,
    event_type: EngineEventType,
) -> EngineEventCandidate:
    """构造 EngineEvent candidate。

    :param seeded: seeded run。
    :param worker_event_index: worker event index。
    :param data: Engine event data。
    :param event_type: Engine event type。
    :returns: EngineEvent candidate。
    """

    return EngineEventCandidate(
        envelope=LocalEngineEnvelope(
            session_id=seeded.session_id,
            run_id=seeded.run_id,
            attempt_id=seeded.attempt_id,
            execution_id=seeded.execution_id,
            dispatch_record_id=seeded.dispatch_record_id,
            worker_kind=WorkerKind.LOCAL,
            execution_target="target-ingest",
            local_worker_id="local-worker-ingest",
            cancellation_token=ControllableCancellationToken(),
        ),
        worker_event_index=worker_event_index,
        engine_event=EngineEvent(
            occurred_at=_NOW,
            session_id=seeded.session_id,
            run_id=seeded.run_id,
            type=event_type,
            data=data,
            metadata=None,
        ),
        observed_at=_NOW,
    )


def _context_compaction_candidate(
    seeded: _SeededRun, *, worker_event_index: int
) -> EngineEventCandidate:
    """构造 reactive context compaction EngineEvent candidate。

    :param seeded: seeded run。
    :param worker_event_index: worker event index。
    :returns: EngineEvent candidate。
    """

    return _candidate(
        seeded,
        worker_event_index=worker_event_index,
        data=ContextCompactionRequestedData(
            iteration_id="iter-1",
            budget_state=None,
            reason="provider_overflow",
            provider_request_id="req-overflow",
        ),
        event_type=EngineEventType.CONTEXT_COMPACTION_REQUESTED,
    )


def _proposal_agent_request(
    request: CompactionRequest,
    *,
    compaction_operation_id: str | None,
    compaction_attempt_number: int,
) -> AgentRunRequest:
    """构造测试用 compactor proposal AgentRunRequest。

    :param request: compaction request。
    :param compaction_operation_id: operation id。
    :param compaction_attempt_number: operation 内 attempt 序号。
    :returns: AgentRunRequest。
    """

    return AgentRunRequest(
        run_id=(f"compactor-run:{request.run_id}:{compaction_operation_id}:{compaction_attempt_number}"),
        session_id="context-compactor:test",
        attempt_id=None,
        execution_id=None,
        messages=(
            SystemMessage(role=AgentMessageRole.SYSTEM, content="system"),
            UserMessage(role=AgentMessageRole.USER, content="reactive user"),
        ),
        disable_tools=True,
        runner_spec=_runner_spec(),
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
            fallback_prompt="test fallback prompt",
            continuation_prompt="test continuation prompt",
        ),
        tool_schemas=(),
        tool_executor=_RejectingToolExecutor(),
        cancellation_token=ControllableCancellationToken(),
    )


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


def _envelope(seeded: _SeededRun) -> LocalEngineEnvelope:
    """构造测试用 LocalEngineEnvelope。

    :param seeded: seeded run。
    :returns: LocalEngineEnvelope。
    """

    return LocalEngineEnvelope(
        session_id=seeded.session_id,
        run_id=seeded.run_id,
        attempt_id=seeded.attempt_id,
        execution_id=seeded.execution_id,
        dispatch_record_id=seeded.dispatch_record_id,
        worker_kind=WorkerKind.LOCAL,
        execution_target="target-ingest",
        local_worker_id="local-worker-ingest",
        cancellation_token=ControllableCancellationToken(),
    )


def _reactive_policy(
    *, max_reactive_compactions_per_run: int = 2
) -> ContextBudgetPolicy:
    """构造测试 reactive context budget policy。

    :param max_reactive_compactions_per_run: 单个 Run reactive compact 上限。
    :returns: Context budget policy。
    """

    return context_budget_policy_from_threshold_tokens(
        context_window_size=100,
        soft_threshold_tokens=45,
        hard_threshold_tokens=80,
        max_reactive_compactions_per_run=max_reactive_compactions_per_run,
        policy_ref=_REACTIVE_POLICY_REF,
    )


def _accepted_tool_record() -> AcceptedToolExecutionRecord:
    """构造测试用 accepted tool execution record。

    :returns: accepted tool record。
    """

    call = _tool_call()
    return AcceptedToolExecutionRecord(
        batch_snapshot=_tool_batch_snapshot(call),
        call=call,
        outcome=ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value={"answer": "ok"},
                meta=None,
            ),
        ),
    )


def _awaiting_tool_record(
    *, await_spec: ToolAwaitSpec | None = None
) -> AwaitingToolExecutionRecord:
    """构造测试用 awaiting tool execution record。

    :param await_spec: 可选等待规约；无则使用默认规约。
    :returns: awaiting tool record。
    """

    call = _tool_call()
    return AwaitingToolExecutionRecord(
        batch_snapshot=_tool_batch_snapshot(call),
        call=call,
        await_spec=(
            await_spec
            if await_spec is not None
            else ToolAwaitSpec(
                await_kind=ToolAwaitKind.EXTERNAL_JOB,
                deadline=None,
                resume_token="resume-token",
            )
        ),
        snapshot=None,
    )


def _awaiting_accept_candidate(seeded: _SeededRun) -> ToolAwaitingAcceptCandidate:
    """构造与 ``_awaiting_tool_record`` 匹配的 Host awaiting accept candidate。

    :param seeded: seeded run。
    :returns: awaiting accept candidate。
    """

    await_spec = ToolAwaitSpec(
        await_kind=ToolAwaitKind.EXTERNAL_JOB,
        deadline=None,
        resume_token="resume-token",
    )
    binding = WaitAdapterBinding(
        tool_name="lookup",
        await_kind=ToolAwaitKind.EXTERNAL_JOB,
        adapter_key=WaitAdapterKey("poll:lookup"),
        resume_policy=WaitResumePolicy.POLL,
        external_job_ref_source=WaitExternalJobRefSource.RESUME_TOKEN,
    )
    digest = sha256_digest_json({"awaiting": "engine-ingest"})
    return ToolAwaitingAcceptCandidate(
        session_id=seeded.session_id,
        run_id=seeded.run_id,
        attempt_id=seeded.attempt_id,
        execution_id=seeded.execution_id,
        iteration_id="iter-tool",
        tool_call_id="tool-call-1",
        tool_name="lookup",
        tool_schema_digest=sha256_digest_json({"schema": "lookup"}),
        tool_identity_digest=sha256_digest_json({"identity": "lookup"}),
        normalized_arguments_digest=sha256_digest_json(
            {"arguments": {"query": "lookup"}}
        ),
        accepted_arguments={"query": "lookup"},
        await_spec=await_spec,
        snapshot_ref=None,
        binding=binding,
        external_job_ref=binding.external_job_ref(await_spec),
        wait_id=f"wait-{digest.removeprefix('sha256:')}",
        accept_idempotency_key=f"tool-await-{digest.removeprefix('sha256:')}",
        semantic_input_digest=digest,
    )


def _resolve_wait_completed_request(idempotency_key: str) -> ResolveWaitRequest:
    """构造 completed resolve wait 请求。

    :param idempotency_key: resolve wait 幂等键。
    :returns: resolve wait request。
    """

    return ResolveWaitRequest(
        context=_host_call_context(idempotency_key),
        idempotency_key=idempotency_key,
        outcome=ResolveWaitCompletedOutcome(
            result=ToolResultSuccess(ok=True, value={"answer": "resolved"}, meta=None),
            payload_ref=None,
        ),
        source=WaitResolutionSource.MANUAL,
        observed_at=_NOW,
    )


def _host_call_context(request_id: str) -> HostCallContext:
    """构造测试用 Host call context。

    :param request_id: request id。
    :returns: Host call context。
    """

    return HostCallContext(
        actor="tester",
        source="pytest",
        request_id=request_id,
        authorization_claims=(),
        operation_context=OperationContext(
            operation_name="resolve_wait",
            operation_kind="test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="engine-ingest",
            correlation_id=None,
        ),
    )


def _tool_batch_snapshot(
    call: ToolCallRequest,
) -> AssistantToolCallBatchSnapshot:
    """构造测试用 assistant tool call batch snapshot。

    :param call: 工具调用请求。
    :returns: batch snapshot。
    """

    return AssistantToolCallBatchSnapshot(
        iteration_id="iter-tool",
        tool_calls=(call,),
        content=None,
        reasoning_content=None,
        provider_request_id="provider-tool",
    )


def _tool_call() -> ToolCallRequest:
    """构造测试用 tool call。

    :returns: tool call request。
    """

    return ToolCallRequest(
        tool_call_id="tool-call-1",
        name="lookup",
        arguments={"ticker": "MSFT"},
        index_in_iteration=0,
        provider_state=None,
    )


def _statuses(
    transaction_runner: HostTransactionRunner, seeded: _SeededRun
) -> tuple[RunStatus, AttemptStatus]:
    """读取 Run / Attempt 状态。

    :param transaction_runner: Host transaction runner。
    :param seeded: seeded run。
    :returns: Run 与 Attempt 状态。
    """

    def _operation(transaction: HostTransaction) -> tuple[RunStatus, AttemptStatus]:
        run = read_run_by_id(transaction, seeded.run_id)
        attempt = read_attempt_by_id(transaction, seeded.attempt_id)
        dispatch = read_dispatch_record_by_attempt_id(transaction, seeded.attempt_id)
        assert run is not None
        assert attempt is not None
        assert dispatch is not None
        assert dispatch.status == DispatchRecordStatus.DISPATCHING
        return run.status, attempt.status

    return transaction_runner.run_read(_operation)


def _terminal_storage_snapshot(
    transaction_runner: HostTransactionRunner,
    seeded: _SeededRun,
) -> tuple[int, int, int, RunStatus, AttemptStatus]:
    """读取 terminal 原子性断言所需的真实 durable snapshot。

    :param transaction_runner: Host transaction runner。
    :param seeded: seeded run。
    :returns: payload row、descriptor、EventLog row 数与 Run/Attempt status。
    :raises AssertionError: durable count 或 Run/Attempt row 缺失时抛出。
    """

    def _operation(
        transaction: HostTransaction,
    ) -> tuple[int, int, int, RunStatus, AttemptStatus]:
        """在同一 read transaction 内读取原子性快照。

        :param transaction: Host read transaction。
        :returns: payload row、descriptor、EventLog row 数与 Run/Attempt status。
        :raises AssertionError: durable count 或 Run/Attempt row 缺失时抛出。
        """

        run = read_run_by_id(transaction, seeded.run_id)
        attempt = read_attempt_by_id(transaction, seeded.attempt_id)
        assert run is not None
        assert attempt is not None
        return (
            _table_row_count(transaction, TABLE_SQLITE_PAYLOADS),
            _table_row_count(transaction, TABLE_PAYLOAD_DESCRIPTORS),
            _table_row_count(transaction, TABLE_EVENT_LOG),
            run.status,
            attempt.status,
        )

    return transaction_runner.run_read(_operation)


def _force_run_status_for_invalid_terminal_precondition(
    transaction_runner: HostTransactionRunner,
    seeded: _SeededRun,
    *,
    status: RunStatus,
) -> None:
    """构造 row 可解码但不满足 terminal closeout 的跨对象状态组合。

    :param transaction_runner: Host transaction runner。
    :param seeded: seeded run。
    :param status: 写入 Run row 的非终态 status。
    :returns: ``None``。
    :raises AssertionError: 状态更新未命中唯一 Run row 时抛出。
    """

    def _operation(transaction: HostTransaction) -> None:
        """更新测试 Run status，不改变 Attempt 与 terminal refs。

        :param transaction: Host write transaction。
        :returns: ``None``。
        :raises AssertionError: 状态更新未命中唯一 Run row 时抛出。
        """

        changed = transaction.execute(
            f"UPDATE {TABLE_HOST_RUNS} SET status = ? WHERE run_id = ?",
            (status.value, seeded.run_id),
        )
        assert changed.rowcount == 1

    transaction_runner.run_write(_operation)


def _table_row_count(transaction: HostTransaction, table_name: str) -> int:
    """读取测试白名单 durable table 的 row count。

    :param transaction: Host transaction。
    :param table_name: schema 常量提供的 durable table 名称。
    :returns: row count。
    :raises AssertionError: SQLite 未返回整数 count 时抛出。
    """

    row = transaction.fetchone(f"SELECT COUNT(*) AS total FROM {table_name}")
    assert row is not None
    total = row.get("total")
    assert isinstance(total, int)
    return total


def _event_count(transaction_runner: HostTransactionRunner, event_type: str) -> int:
    """统计指定 event type 数量。

    :param transaction_runner: Host transaction runner。
    :param event_type: event type。
    :returns: 事件数量。
    """

    def _operation(transaction: HostTransaction) -> int:
        return sum(
            1
            for row in EventLogStore().read_events_after(transaction, 0, limit=100)
            if row.event_type == event_type
        )

    return transaction_runner.run_read(_operation)


def _event_log_cursor(transaction_runner: HostTransactionRunner) -> int:
    """读取当前 EventLog 最大 sequence。

    :param transaction_runner: Host transaction runner。
    :returns: 空日志返回零，否则返回最大 event sequence。
    :raises Exception: durable read 失败时透传。
    """

    def _operation(transaction: HostTransaction) -> int:
        """在同一 read transaction 内读取当前尾游标。

        :param transaction: 当前 Host read transaction。
        :returns: 空日志返回零，否则返回最大 event sequence。
        :raises Exception: EventLog read 失败时透传。
        """

        rows = EventLogStore().read_events_after(transaction, 0, limit=1000)
        if not rows:
            return 0
        return rows[-1].event_sequence

    return transaction_runner.run_read(_operation)


def _events_after_cursor(
    transaction_runner: HostTransactionRunner,
    after_cursor: int,
) -> tuple[EventLogRow, ...]:
    """读取游标后新增的 EventLog rows。

    :param transaction_runner: Host transaction runner。
    :param after_cursor: 已提交 winner 后的 EventLog cursor。
    :returns: 游标后的 rows。
    :raises Exception: durable read 失败时透传。
    """

    return transaction_runner.run_read(
        lambda transaction: EventLogStore().read_events_after(
            transaction,
            after_cursor,
            limit=1000,
        )
    )


def _compact_artifact_files(root: Path) -> tuple[Path, ...]:
    """返回 compact artifact 根目录下的全部文件。

    :param root: compact artifact 根目录。
    :returns: 已存在文件路径，按路径排序。
    :raises OSError: 文件系统枚举失败时透传。
    """

    if not root.exists():
        return ()
    return tuple(sorted(path for path in root.rglob("*") if path.is_file()))


def _append_prepared_runner_call_manifest(
    transaction_runner: HostTransactionRunner,
    seeded: _SeededRun,
    *,
    event_id: str,
    runner_call_index: int,
    runner_call_kind: str,
    runner_call_trigger_reason: str,
    message_count: int,
    role_sequence_digest: str,
    compactor_identity: Mapping[str, JsonValue] | None = None,
) -> EventLogRow:
    """追加测试用 prepared runner-call manifest event。

    :param transaction_runner: Host transaction runner。
    :param seeded: seeded run。
    :param event_id: manifest event id。
    :param runner_call_index: Host runner call index。
    :param runner_call_kind: runner-call kind。
    :param runner_call_trigger_reason: runner-call trigger reason。
    :param message_count: manifest message count。
    :param role_sequence_digest: manifest role digest。
    :param compactor_identity: 可选 compactor identity。
    :returns: 写入的 EventLog row。
    """

    roles = ("system", "user")
    if message_count != len(roles):
        raise AssertionError("prepared manifest fixture message_count must be two")
    if role_sequence_digest != runner_role_sequence_digest(roles):
        raise AssertionError("prepared manifest fixture role digest mismatch")
    is_compactor = compactor_identity is not None
    projection_ref = f"payload-runner-call-projection:{event_id}"
    projection_digest = sha256_digest_json({"projection": event_id})
    metadata_items: list[JsonValue] = []
    message_entries: list[JsonValue] = []
    for index, role in enumerate(roles):
        metadata_id = f"compactor-projector:{role}" if is_compactor else f"projector:{index}:{role}"
        projector_id = (
            f"compactor_{role}_prompt"
            if is_compactor
            else (
                "run_input_system_context"
                if role == "system"
                else "user_input_message"
            )
        )
        purpose = (
            "compactor_proposal_input"
            if is_compactor
            else (
                "post_compaction_input"
                if runner_call_kind == "post_compaction_dispatch"
                else "ordinary_run_input"
            )
        )
        source_contract_refs = (f"event:source:{event_id}:{index}",)
        projector_schema_version = "compactor_projector.v1" if is_compactor else "run_input_projector.v1"
        projector_digest = sha256_digest_json(
            {
                "projector_id": projector_id,
                "projector_schema_version": projector_schema_version,
                "purpose": purpose,
                "source_contract_refs": list(source_contract_refs),
            }
        )
        metadata_items.append(
            runner_call_projector_metadata_descriptor(
                RunnerCallProjectorMetadata(
                    projector_metadata_id=metadata_id,
                    projector_id=projector_id,
                    projector_schema_version=projector_schema_version,
                    projector_digest=projector_digest,
                    purpose=purpose,
                    source_contract_refs=source_contract_refs,
                )
            )
        )
        message_entries.append(
            {
                "index": index,
                "role": role,
                "content_digest": sha256_digest_json(
                    {"event_id": event_id, "message_index": index}
                ),
                "content_size_bytes": index + 1,
                "source_refs": list(source_contract_refs),
                "projection_artifact_ref": (
                    None if is_compactor and index == 0 else projection_ref
                ),
                "projection_artifact_digest": (
                    None if is_compactor and index == 0 else projection_digest
                ),
                "projector_metadata_id": metadata_id,
                "provider_tool_calls_digest": None,
                "reasoning_content_digest": None,
            }
        )
    valid_compactor_identity: Mapping[str, JsonValue] | None = None
    if is_compactor:
        operation_id = compactor_identity.get("compaction_operation_id")
        if not isinstance(operation_id, str):
            raise AssertionError("compactor operation id must be text")
        valid_compactor_identity = {
            "parent_host_run_id": seeded.run_id,
            "parent_session_id": seeded.session_id,
            "compaction_operation_id": operation_id,
            "compactor_engine_run_id": "compactor-engine-run-test",
            "compaction_attempt_number": runner_call_index + 1,
            "compaction_request_digest": sha256_digest_json(
                {"compaction_operation_id": operation_id}
            ),
            "compactor_input_projection_ref": projection_ref,
        }
    manifest: dict[str, JsonValue] = {
        "schema_version": RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION,
        "manifest_id": f"runner-call-manifest:{event_id}",
        "session_id": seeded.session_id,
        "host_run_id": seeded.run_id,
        "attempt_id": seeded.attempt_id,
        "execution_id": seeded.execution_id,
        "runner_call_index": runner_call_index,
        "runner_call_kind": runner_call_kind,
        "runner_call_trigger_reason": runner_call_trigger_reason,
        "iteration_id": None,
        "iteration_index": None,
        "message_count": message_count,
        "role_sequence_digest": role_sequence_digest,
        "runner_input_serializer_schema_version": (
            RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
        ),
        "input_projection_digest": sha256_digest_json(
            {"projection": event_id}
        ),
        "message_entries": message_entries,
        "source_cursor_refs": [f"event:{event_id}"],
        "tool_schema_snapshot_refs": [],
        "memory_snapshot_cursor_ref": None,
        "compact_artifact_refs": [],
        "context_fallback_decision_ref": None,
        "projector_metadata": metadata_items,
        "diagnostic": None,
        "compactor_identity": valid_compactor_identity,
        "sizing_snapshot": (
            {
                "status": "not_applicable",
                "reason": None,
                "sizing_stage": None,
                "estimator_id": None,
                "estimator_version": None,
                "estimator_digest": None,
                "conservative_input_tokens": None,
                "context_window_size": None,
                "provider": None,
                "model": None,
                "request_semantics_digest": None,
                "input_snapshot_digest": None,
                "policy_ref": None,
                "policy_snapshot_digest": None,
            }
            if is_compactor
            else {
                "status": "complete",
                "reason": None,
                "sizing_stage": "ordinary",
                "estimator_id": "dayu.host.conservative_context_budget",
                "estimator_version": "1",
                "estimator_digest": sha256_digest_json(
                    {"estimate": event_id}
                ),
                "conservative_input_tokens": 128,
                "context_window_size": 32768,
                "provider": "openai",
                "model": "test-model",
                "request_semantics_digest": sha256_digest_json(
                    {"request": event_id}
                ),
                "input_snapshot_digest": sha256_digest_json(
                    {"input": event_id}
                ),
                "policy_ref": "policy-test",
                "policy_snapshot_digest": sha256_digest_json(
                    {"policy": event_id}
                ),
            }
        ),
    }
    if not is_compactor:
        manifest.update(
            {
                "runner_call_projection_artifact_ref": projection_ref,
                "runner_call_projection_artifact_digest": projection_digest,
                "runner_call_projection_artifact_size_bytes": 128,
            }
        )
    manifest_digest = sha256_digest_json(manifest)
    manifest_payload_ref = f"payload-runner-call-manifest:{event_id}"
    hot_payload = runner_call_hot_payload(
        RunnerCallHotAtoms(
            session_id=seeded.session_id,
            host_run_id=seeded.run_id,
            attempt_id=seeded.attempt_id,
            execution_id=seeded.execution_id,
            runner_call_index=runner_call_index,
            runner_call_kind=runner_call_kind,
            runner_call_trigger_reason=runner_call_trigger_reason,
            iteration_id=None,
            iteration_index=None,
            manifest_payload_ref=manifest_payload_ref,
            manifest_digest=manifest_digest,
            manifest_schema_version=RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION,
            validation_status="complete",
            message_count=message_count,
            role_sequence_digest=role_sequence_digest,
            input_projection_digest=sha256_digest_json(
                {"projection": event_id}
            ),
            runner_call_projection_artifact_ref=(
                None if is_compactor else projection_ref
            ),
            runner_call_projection_artifact_digest=(
                None if is_compactor else projection_digest
            ),
            runner_call_projection_artifact_size_bytes=(
                None if is_compactor else 128
            ),
            diagnostic=complete_runner_call_hot_diagnostic(
                status="complete",
                message_count=message_count,
                role_sequence_digest=role_sequence_digest,
                consumer_boundary="test.engine_ingest",
            ),
        ),
        manifest=manifest,
    )

    def _operation(transaction: HostTransaction) -> EventLogRow:
        descriptor = PayloadStore().write_sqlite_payload(
            transaction,
            SQLitePayloadWriteRequest(
                payload_ref=manifest_payload_ref,
                payload_id=f"sqlite-runner-call-manifest:{event_id}",
                payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                payload_json=manifest,
                media_type="application/json",
                metadata={},
                expected_digest=manifest_digest,
            ),
        )
        return (
            EventLogStore()
            .append_event(
                transaction,
                EventLogAppendRequest(
                    event_id=event_id,
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    execution_id=seeded.execution_id,
                    event_type="RUNNER_CALL_INPUT_ASSEMBLED",
                    occurred_at=_NOW,
                    actor="tester",
                    source="pytest",
                    client_request_id=None,
                    idempotency_key=None,
                    policy_decision=None,
                    reason=None,
                    payload_json=hot_payload,
                    payload_ref=descriptor.payload_ref,
                    payload_digest=descriptor.payload_digest,
                ),
            )
            .row
        )

    return transaction_runner.run_write(_operation)


def _link_pre_start_runner_call_manifest(
    transaction_runner: HostTransactionRunner,
    seeded: _SeededRun,
    *,
    worker_event_index: int,
    iteration_id: str,
) -> None:
    """把 strict source pre-start manifest 链接到首个 Engine iteration。

    :param transaction_runner: transaction runner。
    :param seeded: active Run identity。
    :param worker_event_index: Engine worker event 顺序。
    :param iteration_id: 首个 iteration id。
    :returns: ``None``。
    :raises AssertionError: pre-start manifest 不唯一或 link 未被接受时抛出。
    """

    events = transaction_runner.run_read(
        lambda transaction: tuple(
            event
            for event in EventLogStore().read_events_after(
                transaction,
                0,
                limit=200,
            )
            if event.event_type == "RUNNER_CALL_INPUT_ASSEMBLED"
            and event.attempt_id == seeded.attempt_id
            and event.execution_id == seeded.execution_id
        )
    )
    pre_start_events = tuple(
        event
        for event in events
        if parse_runner_call_hot_payload(_payload(event)).iteration_id is None
    )
    assert len(pre_start_events) == 1
    hot = parse_runner_call_hot_payload(_payload(pre_start_events[0]))
    result = EngineEventIngestor(
        transaction_runner=transaction_runner,
        terminal_post_commit_port=_RecordingTerminalPostCommitPort(),
        transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
    ).ingest(
        _candidate(
            seeded,
            worker_event_index=worker_event_index,
            data=IterationStartedData(
                iteration_id=iteration_id,
                iteration_index=0,
                message_count=hot.message_count,
                role_sequence_digest=hot.role_sequence_digest,
                runner_input_serializer_schema_version=(
                    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
                ),
            ),
            event_type=EngineEventType.ITERATION_STARTED,
        )
    )
    assert result.status is EngineIngestStatus.ACCEPTED
    assert result.events[0].event_type == "RUNNER_CALL_INPUT_ITERATION_LINKED"


def _append_prior_iteration_started_preview(
    transaction_runner: HostTransactionRunner,
    seeded: _SeededRun,
    *,
    event_id: str,
    iteration_id: str,
    iteration_index: int,
) -> EventLogRow:
    """追加测试用 prior accepted ITERATION_STARTED preview。

    :param transaction_runner: Host transaction runner。
    :param seeded: seeded run。
    :param event_id: preview event id。
    :param iteration_id: Engine iteration id。
    :param iteration_index: Engine iteration index。
    :returns: 写入的 EventLog row。
    """

    def _operation(transaction: HostTransaction) -> EventLogRow:
        return (
            EventLogStore()
            .append_event(
                transaction,
                EventLogAppendRequest(
                    event_id=event_id,
                    event_class=EventClass.PREVIEW,
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    execution_id=seeded.execution_id,
                    event_type="ITERATION_STARTED",
                    occurred_at=_NOW,
                    actor="tester",
                    source="pytest",
                    client_request_id=None,
                    idempotency_key=None,
                    policy_decision=None,
                    reason=None,
                    payload_json={
                        "attempt_id": seeded.attempt_id,
                        "execution_id": seeded.execution_id,
                        "worker_event_index": 1,
                        "engine_event_type": "iteration_started",
                        "iteration_id": iteration_id,
                        "iteration_index": iteration_index,
                        "message_count": 1,
                        "role_sequence_digest": runner_role_sequence_digest(("user",)),
                        "runner_input_serializer_schema_version": (RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION),
                        "runner_call_manifest_validation": {
                            "status": "complete",
                            "reason": None,
                            "runner_call_iteration_link_event_id": None,
                            "manifest_event_id": None,
                            "manifest_payload_ref": None,
                            "manifest_digest": None,
                            "observed_count": 1,
                            "expected_count": 1,
                            "observed_digest": runner_role_sequence_digest(("user",)),
                            "expected_digest": runner_role_sequence_digest(("user",)),
                            "continuation_limited_signal": False,
                        },
                    },
                    payload_ref=None,
                    payload_digest=None,
                ),
            )
            .row
        )

    return transaction_runner.run_write(_operation)


def _attempt_count(transaction_runner: HostTransactionRunner, run_id: str) -> int:
    """统计 Run 下 Attempt row 数。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :returns: Attempt 数量。
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


def _current_attempt_id(
    transaction_runner: HostTransactionRunner, run_id: str
) -> str:
    """读取 Run 当前 Attempt id。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :returns: current Attempt id。
    """

    def _operation(transaction: HostTransaction) -> str:
        run = read_run_by_id(transaction, run_id)
        assert run is not None
        assert run.current_attempt_id is not None
        return run.current_attempt_id

    return transaction_runner.run_read(_operation)


def _attempt_status(
    transaction_runner: HostTransactionRunner, attempt_id: str
) -> AttemptStatus:
    """读取 Attempt 状态。

    :param transaction_runner: Host transaction runner。
    :param attempt_id: Attempt id。
    :returns: Attempt 状态。
    """

    def _operation(transaction: HostTransaction) -> AttemptStatus:
        attempt = read_attempt_by_id(transaction, attempt_id)
        assert attempt is not None
        return attempt.status

    return transaction_runner.run_read(_operation)


def _latest_event(
    transaction_runner: HostTransactionRunner, event_type: str
) -> EventLogRow:
    """读取最近一条指定类型事件。

    :param transaction_runner: Host transaction runner。
    :param event_type: event type。
    :returns: EventLog row。
    """

    def _operation(transaction: HostTransaction) -> EventLogRow:
        rows = EventLogStore().read_events_after(transaction, 0, limit=200)
        for row in reversed(rows):
            if row.event_type == event_type:
                return row
        raise AssertionError(f"missing event type {event_type}")

    return transaction_runner.run_read(_operation)


def _append_reactive_requested_fact(
    transaction_runner: HostTransactionRunner,
    *,
    seeded: _SeededRun,
    event_id: str,
    corrupted: bool,
) -> None:
    """追加测试用 reactive compact request fact。

    :param transaction_runner: Host transaction runner。
    :param seeded: seeded run。
    :param event_id: event id。
    :param corrupted: 是否写入损坏 payload。
    :returns: ``None``。
    """

    payload: Mapping[str, JsonValue]
    if corrupted:
        payload = {"trigger_source": 7}
    else:
        payload = {
            "trigger_source": "reactive",
            "budget_reason": "provider_overflow",
            "budget_snapshot_ref": _CALL_CONTEXT_DIGEST,
            "input_snapshot_cursor": 1,
            "estimator_digest": _CALL_CONTEXT_DIGEST,
            "policy_ref": _REACTIVE_POLICY_REF,
            "provider_request_id": "req-existing",
            "provider_error_ref": "engine:existing",
            "attempt_id": seeded.attempt_id,
            "execution_id": seeded.execution_id,
        }

    def _operation(transaction: HostTransaction) -> None:
        EventLogStore().append_event(
            transaction,
            EventLogAppendRequest(
                event_id=event_id,
                event_class=EventClass.CANONICAL_FACT,
                session_id=seeded.session_id,
                run_id=seeded.run_id,
                attempt_id=seeded.attempt_id,
                execution_id=seeded.execution_id,
                event_type=CONTEXT_COMPACTION_REQUESTED,
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason=None,
                payload_json=payload,
                payload_ref=None,
                payload_digest=None,
            ),
        )

    transaction_runner.run_write(_operation)


def _delete_input_event(connection: sqlite3.Connection, *, event_id: str) -> None:
    """删除测试 input event，模拟 durable run 指向缺失输入事件。

    :param connection: 独立 SQLite connection。
    :param event_id: input event id。
    :returns: ``None``。
    """

    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute(f"DELETE FROM {TABLE_EVENT_LOG} WHERE event_id = ?", (event_id,))
    connection.commit()


def _replace_inline_payload_json(
    transaction_runner: HostTransactionRunner,
    *,
    event_id: str,
    payload_json: str,
) -> None:
    """替换测试事件 inline payload，模拟 payload 不可读。

    :param transaction_runner: Host transaction runner。
    :param event_id: event id。
    :param payload_json: 新 payload JSON 文本。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        transaction.execute(
            f"""
            UPDATE {TABLE_EVENT_LOG}
            SET payload_json = ?
            WHERE event_id = ?
            """,
            (payload_json, event_id),
        )

    transaction_runner.run_write(_operation)


def _tamper_reactive_source(
    transaction_runner: HostTransactionRunner,
    *,
    seeded: _SeededRun,
    tamper_kind: _ReactiveSourceTamperKind,
) -> None:
    """篡改 reactive source durable truth 以验证 strict fail-closed。

    :param transaction_runner: Host transaction runner。
    :param seeded: source active Run identity。
    :param tamper_kind: 待模拟的 durable contract 缺口。
    :returns: ``None``。
    :raises AssertionError: source manifest 或 descriptor fixture 缺失时抛出。
    :raises HostDurableError: strict payload helper无法读取原始fixture时抛出。
    """

    if tamper_kind is _ReactiveSourceTamperKind.EFFECTIVE_CONFIG_MISSING:
        _replace_inline_payload_json(
            transaction_runner,
            event_id="event-input-ingest",
            payload_json=json.dumps(
                {
                    "display_text": "hello",
                    "operation_kind": "analysis",
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        return

    def _operation(transaction: HostTransaction) -> None:
        """删除 source manifest 或破坏 candidate descriptor digest。

        :param transaction: Host write transaction。
        :returns: ``None``。
        :raises AssertionError: source manifest 或 descriptor 缺失时抛出。
        :raises HostDurableError: manifest payload 不可读时抛出。
        """

        rows = tuple(
            row
            for row in EventLogStore().read_events_after(
                transaction,
                0,
                limit=200,
            )
            if row.event_type == "RUNNER_CALL_INPUT_ASSEMBLED"
            and row.attempt_id == seeded.attempt_id
            and row.execution_id == seeded.execution_id
        )
        assert len(rows) == 1
        manifest_event = rows[0]
        if tamper_kind is _ReactiveSourceTamperKind.MANIFEST_MISSING:
            result = transaction.execute(
                f"DELETE FROM {TABLE_EVENT_LOG} WHERE event_id = ?",
                (manifest_event.event_id,),
            )
            assert result.rowcount == 1
            return
        hot = parse_runner_call_hot_payload(_payload(manifest_event))
        manifest_json = sqlite_payload_object(
            transaction,
            payload_ref=hot.manifest_payload_ref,
            payload_digest=hot.manifest_digest,
            payload_label="source manifest",
        )
        manifest = parse_runner_call_manifest(
            manifest_json,
            hot_payload=hot,
        )
        if (
            tamper_kind
            is _ReactiveSourceTamperKind.TOOL_SNAPSHOT_MISSING
        ):
            tool_refs = tuple(
                ref.removeprefix("tool_schema_snapshot_ref:")
                for ref in manifest.source_refs.tool_schema_snapshot_refs
                if ref.startswith("tool_schema_snapshot_ref:")
            )
            assert len(tool_refs) == 1
            result = transaction.execute(
                f"""
                DELETE FROM {TABLE_PAYLOAD_DESCRIPTORS}
                WHERE payload_ref = ?
                """,
                (tool_refs[0],),
            )
            assert result.rowcount == 1
            return
        candidate_ref = _prepared_candidate_payload_ref(
            manifest.input_projection_digest
        )
        result = transaction.execute(
            f"""
            UPDATE {TABLE_PAYLOAD_DESCRIPTORS}
            SET payload_digest = ?
            WHERE payload_ref = ?
            """,
            (_CALL_CONTEXT_DIGEST, candidate_ref),
        )
        assert result.rowcount == 1

    transaction_runner.run_write(_operation)


def _advance_run_input_sequence(
    transaction_runner: HostTransactionRunner, *, run_id: str
) -> None:
    """追加新输入事件并推进 Run input sequence。

    :param transaction_runner: Host transaction runner。
    :param run_id: 目标 Run id。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        run = read_run_by_id(transaction, run_id)
        assert run is not None
        input_event = (
            EventLogStore()
            .append_event(
                transaction,
                EventLogAppendRequest(
                    event_id=f"event-stale-input-{run_id}",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=run.session_id,
                    run_id=run.run_id,
                    attempt_id=None,
                    execution_id=None,
                    event_type="USER_INPUT_ACCEPTED",
                    occurred_at=_NOW,
                    actor="tester",
                    source="pytest",
                    client_request_id="client-stale-input",
                    idempotency_key=f"idem-stale-input-{run_id}",
                    policy_decision=None,
                    reason=None,
                    payload_json={"display_text": "new input while compacting"},
                    payload_ref=None,
                    payload_digest=None,
                ),
            )
            .row
        )
        result = transaction.execute(
            """
            UPDATE host_runs
            SET
              input_event_id = ?,
              input_event_sequence = ?,
              updated_at = ?
            WHERE run_id = ?
            """,
            (
                input_event.event_id,
                input_event.event_sequence,
                "2026-05-15T01:02:04.000000Z",
                run_id,
            ),
        )
        assert result.rowcount == 1

    transaction_runner.run_write(_operation)


def _canonical_tool_event_count(transaction_runner: HostTransactionRunner) -> int:
    """统计 canonical 工具事件数量。

    :param transaction_runner: Host transaction runner。
    :returns: canonical ``TOOL_*`` 事件数量。
    """

    def _operation(transaction: HostTransaction) -> int:
        """读取并统计 canonical 工具事件。

        :param transaction: Host transaction。
        :returns: canonical 工具事件数量。
        """

        return sum(
            1
            for row in EventLogStore().read_events_after(transaction, 0, limit=100)
            if row.event_class is EventClass.CANONICAL_FACT
            and row.event_type.startswith("TOOL_")
        )

    return transaction_runner.run_read(_operation)


def _payload(row: EventLogRow) -> Mapping[str, JsonValue]:
    """解析 EventLog payload。

    :param row: EventLog row。
    :returns: payload mapping。
    """

    value = cast(JsonValue, json.loads(row.payload_json))
    assert isinstance(value, Mapping)
    return cast(Mapping[str, JsonValue], value)


def _json_object_sequence(value: JsonValue) -> tuple[Mapping[str, JsonValue], ...]:
    """断言 JSON 值是 object 列表。

    :param value: JSON 值。
    :returns: JSON object 元组。
    :raises AssertionError: value 不是 object 列表时抛出。
    """

    assert isinstance(value, list)
    objects: list[Mapping[str, JsonValue]] = []
    for item in value:
        assert isinstance(item, Mapping)
        objects.append(item)
    return tuple(objects)


def _json_object(value: JsonValue) -> Mapping[str, JsonValue]:
    """断言 JSON 值是 object。

    :param value: JSON 值。
    :returns: JSON object。
    :raises AssertionError: value 不是 object 时抛出。
    """

    assert isinstance(value, Mapping)
    return value


def _legacy_provider_protocol_diagnostic_view(
    payload: Mapping[str, JsonValue],
) -> Mapping[str, JsonValue]:
    """模拟只读取旧 provider protocol diagnostic 字段的消费者。

    :param payload: provider protocol diagnostic payload。
    :returns: 旧消费者关心的字段视图。
    """

    return {
        "error_code": payload["error_code"],
        "provider_request_id": payload["provider_request_id"],
        "client_correlation_id": payload["client_correlation_id"],
        "raw_payload_ref": payload["raw_payload_ref"],
        "partial_tool_call_count": payload["partial_tool_call_count"],
    }
