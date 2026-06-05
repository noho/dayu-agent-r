"""Host Phase 5 EngineEvent ingest 映射测试。"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_await import ToolAwaitKind, ToolAwaitSpec
from dayu.contracts.tool_call import ToolCallRequest
from dayu.contracts.tool_outcome import ToolCompletedOutcome
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.engine.contracts.engine_events import (
    ContextCompactionRequestedData,
    ContentDeltaData,
    EngineEvent,
    EngineEventData,
    EngineEventType,
    FinalAnswerData,
    IterationCompletedData,
    IterationStartedData,
    ProviderProtocolErrorData,
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
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.tool_records import (
    AcceptedToolExecutionRecord,
    AssistantToolCallBatchSnapshot,
    AwaitingToolExecutionRecord,
)
from dayu.host.admission import PendingDispatchRecord
from dayu.host.api import (
    AttemptStatus,
    EnsureSessionRequest,
    HostCallContext,
    OperationContext,
    ResolveWaitCompletedOutcome,
    ResolveWaitRequest,
    RunStatus,
    WaitAdapterKey,
    WaitResolutionSource,
)
from dayu.host.context_events import (
    CONTEXT_COMPACTED,
    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
    CONTEXT_COMPACTION_FAILED,
    CONTEXT_COMPACTION_REQUESTED,
)
from dayu.host.compact_payload import (
    COMPACT_ARTIFACT_MEDIA_TYPE_VNEXT,
    COMPACT_ARTIFACT_SCHEMA_VERSION_VNEXT,
    COMPACT_PROJECTION_SIGNAL_MEMORY_CATCHUP,
)
from dayu.host.compaction import (
    CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT,
    CompactionRequest,
    ConversationCompactOutputVNext,
)
from dayu.host.context_policy import (
    ContextBudgetPolicy,
    context_budget_policy_from_threshold_tokens,
)
from dayu.host.durable.codec import format_utc_timestamp, sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.liveness import (
    HostInstanceIdentity,
    register_current_instance,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.payload import PayloadStore
from dayu.host.durable.run_transition import (
    AcceptWorkerRunningInput,
    CreateRunningRunInput,
    accept_worker_running_in_transaction,
    create_running_run_with_starting_attempt_in_transaction,
)
from dayu.host.durable.schema import TABLE_EVENT_LOG
from dayu.host.durable.session_lifecycle import ensure_session
from dayu.host.durable.state import (
    AttemptRow,
    DispatchRecordRow,
    DispatchRecordStatus,
    RunStartReason,
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
from tests.host._context_compaction_assertions import assert_failed_payload_no_fallback
from tests.host.fake_cancellation import StubCancellationToken
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
    EngineIngestStatus,
    LocalEngineEnvelope,
)

_NOW = datetime(2026, 5, 15, 1, 2, 3, tzinfo=UTC)
_CALL_CONTEXT_DIGEST = sha256_digest_json({"context": "engine-ingest-test"})
_REACTIVE_POLICY_REF = "test-reactive-policy"


@dataclass(frozen=True, slots=True)
class _SeededRun:
    """测试中创建的 active Engine run。"""

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str


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


def test_final_answer_closes_attempt_and_run_with_phase5_payload(
    tmp_path: Path,
) -> None:
    """final_answer 映射为 ATTEMPT_SUCCEEDED 与 RUN_SUCCEEDED。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
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
            transaction_runner=store.transaction_runner
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        assert result.terminal_closeout is True
        assert result.promotion_triggered is True
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


def test_empty_final_answer_closes_failed_without_run_succeeded(
    tmp_path: Path,
) -> None:
    """空 final_answer 不写入无法 public 投影的 RUN_SUCCEEDED。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _candidate(
            seeded,
            worker_event_index=2,
            data=FinalAnswerData(
                content="",
                filtered=False,
                degraded=True,
                finish_reason=FinishReason.LENGTH,
            ),
            event_type=EngineEventType.FINAL_ANSWER,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        assert [event.event_type for event in result.events] == [
            "ATTEMPT_FAILED",
            "RUN_FAILED",
        ]
        assert _event_count(store.transaction_runner, "RUN_SUCCEEDED") == 0
        assert _event_count(store.transaction_runner, "RUN_FAILED") == 1
        payload = _payload(result.events[0])
        assert payload["error_code"] == "empty_final_answer"
        assert payload["recoverable"] is False
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
                error_code="provider_error",
                message="provider failed",
                provider_request_id="req-1",
                client_correlation_id="client-req-1",
                recoverable=False,
            ),
            event_type=EngineEventType.RUN_FAILED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner
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
                error_code="context_recovery_needed",
                message="recoverable",
                provider_request_id="req-2",
                client_correlation_id="client-req-2",
                recoverable=True,
            ),
            event_type=EngineEventType.RUN_FAILED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner
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
) -> None:
    """provider overflow budget_state=None 使用 Host estimator 并进入 recovery。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        wakeup = _WakeupSpy()
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
            wakeup_port=wakeup,
            context_budget_policy=_reactive_policy(),
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
        requested_payload = _payload(result.events[0])
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


@pytest.mark.asyncio
async def test_reactive_freezes_overflow_material_list_before_compaction(
    tmp_path: Path,
) -> None:
    """reactive pending record 保存冻结 ordinary material digest 与 refs。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
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
        seeded = _seed_active_run(store.transaction_runner)
        compactor = _TransactionReadableCompactor(store.transaction_runner)
        candidate = _context_compaction_candidate(seeded, worker_event_index=41)

        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            context_budget_policy=_reactive_policy(),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
        ).ingest_async(candidate)

        assert result.status is EngineIngestStatus.ACCEPTED
        assert compactor.calls == 1
        assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 1


@pytest.mark.asyncio
async def test_reactive_compaction_rejects_stale_input_sequence(
    tmp_path: Path,
) -> None:
    """reactive compact 返回后 input sequence 变化时拒绝旧 snapshot 结果。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        compactor = _InputSequenceAdvancingCompactor(store.transaction_runner)
        candidate = _context_compaction_candidate(seeded, worker_event_index=43)

        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
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
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _context_compaction_candidate(seeded, worker_event_index=42)

        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
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


def test_context_compaction_requested_stale_identity_is_rejected(
    tmp_path: Path,
) -> None:
    """attempt_id + execution_id 不匹配时拒绝 reactive compact。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        wrong_seeded = _SeededRun(
            session_id=seeded.session_id,
            run_id=seeded.run_id,
            attempt_id=seeded.attempt_id,
            execution_id="execution-other",
            dispatch_record_id=seeded.dispatch_record_id,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
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
        seeded = _seed_active_run(store.transaction_runner)
        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            context_budget_policy=_reactive_policy(),
        ).ingest_async(
            _context_compaction_candidate(seeded, worker_event_index=42)
        )

        assert tuple(event.event_type for event in result.events) == (
            CONTEXT_COMPACTION_REQUESTED,
            "ATTEMPT_FAILED",
            "RUN_RECOVERING",
            CONTEXT_COMPACTION_FAILED,
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
    """reactive fallback view 仍超 hard budget 时 FAILED 收口且不 LOST。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(
            store.transaction_runner,
            display_text="overflow " * 80,
        )
        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
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


@pytest.mark.asyncio
async def test_old_attempt_run_failed_after_recovery_is_stale_diagnostic(
    tmp_path: Path,
) -> None:
    """recovery start 后旧 Attempt 的 recoverable run_failed 不创建第二个 Attempt。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
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
                    error_code="context_compaction_required",
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
        ingestor = EngineEventIngestor(transaction_runner=store.transaction_runner)

        stale = ingestor.ingest(
            _candidate(
                seeded,
                worker_event_index=51,
                data=ContentDeltaData(iteration_id="iter-stale", delta="old"),
                event_type=EngineEventType.CONTENT_DELTA,
            )
        )
        accepted = ingestor.ingest(
            _candidate(
                current,
                worker_event_index=1,
                data=ContentDeltaData(iteration_id="iter-current", delta="new"),
                event_type=EngineEventType.CONTENT_DELTA,
            )
        )

        assert stale.status == EngineIngestStatus.REJECTED
        assert _payload(stale.events[0])["reason"] == "stale_execution_id"
        assert accepted.status == EngineIngestStatus.ACCEPTED
        assert accepted.events[0].attempt_id == current.attempt_id
        assert _payload(accepted.events[0])["delta"] == "new"


@pytest.mark.asyncio
async def test_reactive_compact_count_limit_fails_closed_without_second_attempt(
    tmp_path: Path,
) -> None:
    """配置为一次 reactive 时，已有 request 会触发失败收口。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        _append_reactive_requested_fact(
            store.transaction_runner,
            seeded=seeded,
            event_id="event-existing-reactive-request",
            corrupted=False,
        )

        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            context_budget_policy=_reactive_policy(
                max_reactive_compactions_per_run=1
            ),
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
        seeded = _seed_active_run(store.transaction_runner)
        _append_reactive_requested_fact(
            store.transaction_runner,
            seeded=seeded,
            event_id="event-existing-reactive-request-repeat",
            corrupted=False,
        )

        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            context_budget_policy=_reactive_policy(
                max_reactive_compactions_per_run=1
            ),
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
        seeded = _seed_active_run(store.transaction_runner)
        _append_reactive_requested_fact(
            store.transaction_runner,
            seeded=seeded,
            event_id="event-existing-reactive-request",
            corrupted=False,
        )

        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            context_budget_policy=_reactive_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        ).ingest_async(_context_compaction_candidate(seeded, worker_event_index=45))

        assert result.status == EngineIngestStatus.ACCEPTED
        assert _attempt_count(store.transaction_runner, seeded.run_id) == 2
        assert (
            _event_count(store.transaction_runner, CONTEXT_COMPACTION_REQUESTED)
            == 2
        )
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
        seeded = _seed_active_run(store.transaction_runner)
        _append_reactive_requested_fact(
            store.transaction_runner,
            seeded=seeded,
            event_id="event-corrupt-reactive-request",
            corrupted=True,
        )

        result = await EngineEventIngestor(
            transaction_runner=store.transaction_runner,
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
        ingestor = EngineEventIngestor(transaction_runner=store.transaction_runner)

        first = ingestor.ingest(candidate)
        second = ingestor.ingest(candidate)

        assert first.status == EngineIngestStatus.ACCEPTED
        assert second.status == EngineIngestStatus.DUPLICATE
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
        ingestor = EngineEventIngestor(transaction_runner=store.transaction_runner)

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
            transaction_runner=store.transaction_runner
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        assert result.reason == "waiting_event_confirmation"
        payload = _payload(result.events[0])
        assert payload["waiting_confirmation_accepted"] is True
        assert payload["waiting_confirmation_mismatch_reason"] is None
        assert payload["wait_id"] == accept_result.wait_id
        assert _canonical_tool_event_count(store.transaction_runner) == 1
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
            transaction_runner=store.transaction_runner
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
            transaction_runner=store.transaction_runner
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        assert result.reason == "waiting_event_without_host_accepted_refs"
        payload = _payload(result.events[0])
        assert payload["waiting_confirmation_accepted"] is False
        assert payload["waiting_confirmation_mismatch_reason"] == "awaiting_spec_mismatch"
        assert payload["wait_id"] == accept_result.wait_id
        assert _canonical_tool_event_count(store.transaction_runner) == 1
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
            transaction_runner=store.transaction_runner
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.REJECTED
        assert result.reason == "stale_execution_id"
        assert _payload(result.events[0])["reason"] == "stale_execution_id"
        assert _canonical_tool_event_count(store.transaction_runner) == 1
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
            transaction_runner=store.transaction_runner
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.REJECTED
        assert result.reason == "stale_execution_id"
        assert _event_count(store.transaction_runner, "ENGINE_EVENT_REJECTED") == 1
        assert _canonical_tool_event_count(store.transaction_runner) == 1
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.WAITING
        assert attempt_status == AttemptStatus.SUSPENDED


def test_old_attempt_late_waiting_confirmation_is_rejected_after_resolve(
    tmp_path: Path,
) -> None:
    """旧 Attempt 在 wait resolved 后的 late waiting confirmation 只能被拒绝。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        accept_result = DefaultHostToolAwaitingAcceptPort(
            transaction_runner=store.transaction_runner
        ).accept_tool_awaiting(_awaiting_accept_candidate(seeded))
        assert isinstance(accept_result, ToolAwaitingAcceptedAck)
        resolved = DefaultHostResolveWaitService(
            transaction_runner=store.transaction_runner
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
            transaction_runner=store.transaction_runner
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.REJECTED
        assert result.reason == "stale_execution_id"
        assert _payload(result.events[0])["reason"] == "stale_execution_id"
        assert _canonical_tool_event_count(store.transaction_runner) == 2


def test_usage_reported_is_projection_signal_without_state_change(
    tmp_path: Path,
) -> None:
    """usage_reported 只写 projection_signal，不改 Run / Attempt 状态。"""

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
            ),
            event_type=EngineEventType.USAGE_REPORTED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            context_budget_policy=_reactive_policy(),
        ).ingest(candidate)

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
        assert payload["provider_request_id"] is None
        assert payload["policy_ref"] == _REACTIVE_POLICY_REF
        assert isinstance(payload["estimator_digest"], str)
        assert payload["estimated_input_tokens"] == 14
        assert payload["usage_observation_status"] == "observed"
        assert isinstance(payload["usage_observation_digest"], str)
        assert payload["prompt_token_delta"] == -4
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
            ),
            event_type=EngineEventType.USAGE_REPORTED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        payload = _payload(result.events[0])
        assert payload["policy_ref"] == "none"
        assert payload["estimator_digest"] is None
        assert payload["estimated_input_tokens"] is None
        assert payload["usage_observation_status"] == "estimate_unavailable"
        assert payload["provider_request_id"] is None
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
            ),
            event_type=EngineEventType.USAGE_REPORTED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            context_budget_policy=_reactive_policy(),
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        payload = _payload(result.events[0])
        assert payload["policy_ref"] == _REACTIVE_POLICY_REF
        assert payload["estimator_digest"] is None
        assert payload["estimated_input_tokens"] is None
        assert payload["usage_observation_status"] == "estimate_unavailable"
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
            ),
            event_type=EngineEventType.USAGE_REPORTED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            context_budget_policy=_reactive_policy(),
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        payload = _payload(result.events[0])
        assert payload["policy_ref"] == _REACTIVE_POLICY_REF
        assert payload["estimator_digest"] is None
        assert payload["estimated_input_tokens"] is None
        assert payload["usage_observation_status"] == "estimate_unavailable"
        assert payload["provider_request_id"] is None
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
            ),
            event_type=EngineEventType.USAGE_REPORTED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            context_budget_policy=_reactive_policy(),
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        payload = _payload(result.events[0])
        assert payload["prompt_tokens"] == -1
        assert payload["policy_ref"] == _REACTIVE_POLICY_REF
        assert isinstance(payload["estimator_digest"], str)
        assert payload["estimated_input_tokens"] == 14
        assert payload["usage_observation_status"] == "usage_invalid"
        assert isinstance(payload["usage_observation_digest"], str)
        assert payload["prompt_token_delta"] is None
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.RUNNING
        assert attempt_status == AttemptStatus.RUNNING


def test_duplicate_candidate_returns_existing_result(tmp_path: Path) -> None:
    """同一 terminal candidate 重放不追加 canonical event 但会重试 promotion wakeup。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        wakeup = _WakeupSpy()
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
            wakeup_port=wakeup,
        )

        first = ingestor.ingest(candidate)
        second = ingestor.ingest(candidate)

        assert first.status == EngineIngestStatus.ACCEPTED
        assert first.promotion_triggered is True
        assert second.status == EngineIngestStatus.DUPLICATE
        assert second.promotion_triggered is True
        assert [event.event_id for event in first.events] == [
            event.event_id for event in second.events
        ]
        assert _event_count(store.transaction_runner, "ATTEMPT_SUCCEEDED") == 1
        assert _event_count(store.transaction_runner, "RUN_SUCCEEDED") == 1
        assert wakeup.promoted_session_ids == [
            seeded.session_id,
            seeded.session_id,
        ]


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
            transaction_runner=store.transaction_runner
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
                error_code="invalid_stream",
                message="bad stream",
                provider_request_id="req-protocol",
                client_correlation_id="client-protocol",
                raw_payload={
                    "version": 1,
                    "source": "provider_protocol_error",
                    "kind": "provider_error",
                    "canonical_byte_size": 128,
                    "sha256_digest": (
                        "0123456789abcdef0123456789abcdef"
                        "0123456789abcdef0123456789abcdef"
                    ),
                    "provider_error": {
                        "code": "invalid_stream",
                        "type": "protocol_error",
                    },
                },
                partial_tool_calls=(),
            ),
            event_type=EngineEventType.PROVIDER_PROTOCOL_ERROR,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner
        ).ingest(candidate)

        assert result.events[0].event_class == EventClass.DIAGNOSTIC
        assert result.events[0].event_type == "PROVIDER_PROTOCOL_ERROR"
        assert _payload(result.events[0])["client_correlation_id"] == "client-protocol"
        assert _payload(result.events[0])["raw_payload_ref"] is not None
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.RUNNING
        assert attempt_status == AttemptStatus.RUNNING


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
        ingestor = EngineEventIngestor(transaction_runner=store.transaction_runner)

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


def test_tool_batch_and_delta_events_stay_preview_not_canonical(
    tmp_path: Path,
) -> None:
    """Engine batch-ready、batch-done 与 tool delta 不能绕过 accept path。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        ingestor = EngineEventIngestor(transaction_runner=store.transaction_runner)
        delta = _candidate(
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

        results = tuple(ingestor.ingest(item) for item in (delta, ready, done))

        assert [result.events[0].event_class for result in results] == [
            EventClass.PREVIEW,
            EventClass.PREVIEW,
            EventClass.PREVIEW,
        ]
        assert [result.events[0].event_type for result in results] == [
            "TOOL_CALL_DELTA",
            "TOOL_CALLS_BATCH_READY",
            "TOOL_CALLS_BATCH_DONE",
        ]
        assert _canonical_tool_event_count(store.transaction_runner) == 0


def test_late_terminal_event_is_rejected_after_closeout(tmp_path: Path) -> None:
    """Run terminal 后迟到 terminal candidate 写 rejected diagnostic。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        ingestor = EngineEventIngestor(transaction_runner=store.transaction_runner)
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
                error_code="late",
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
            transaction_runner=store.transaction_runner
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.REJECTED
        assert _payload(result.events[0])["reason"] == (
            "run_cancelled_without_active_cancel"
        )
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.RUNNING
        assert attempt_status == AttemptStatus.RUNNING


def test_run_cancelled_with_malformed_active_cancel_payload_is_rejected(
    tmp_path: Path,
) -> None:
    """RUN_CANCELLING payload 缺少 request id 时返回 rejected diagnostic。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
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
            transaction_runner=store.transaction_runner
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.REJECTED
        assert _payload(result.events[0])["reason"] == (
            "run_cancelled_invalid_active_cancel_payload"
        )
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.RUNNING
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


def test_worker_lost_closeout_uses_lost_event_ids_and_duplicate(
    tmp_path: Path,
) -> None:
    """worker lost synthetic lifecycle 使用 LOST facts，重复 closeout 幂等。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        ingestor = EngineEventIngestor(transaction_runner=store.transaction_runner)
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
        payload = _payload(first.events[1])
        assert payload["engine_event_ref"] == (
            f"engine:{seeded.execution_id}:1:worker_lost_before_terminal"
        )
        run_status, attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.LOST
        assert attempt_status == AttemptStatus.LOST


def test_unsupported_engine_event_shape_is_rejected(tmp_path: Path) -> None:
    """EngineEvent type/data 不匹配时写 rejected diagnostic。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _candidate(
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

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.REJECTED
        assert _payload(result.events[0])["reason"] == "unsupported_engine_event_type"
        assert result.stop_worker_stream is True


@pytest.mark.parametrize(
    ("worker_event_index", "data"),
    (
        (17, cast(EngineEventData, None)),
        (
            18,
            IterationStartedData(
                iteration_id="iter-wrong",
                iteration_index=0,
                message_count=1,
            ),
        ),
    ),
)
def test_preview_event_rejects_missing_or_wrong_data(
    tmp_path: Path,
    worker_event_index: int,
    data: EngineEventData,
) -> None:
    """preview event 必须同时匹配 event type 与 data 类型。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _candidate(
            seeded,
            worker_event_index=worker_event_index,
            data=data,
            event_type=EngineEventType.CONTENT_DELTA,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.REJECTED
        assert result.events[0].event_class == EventClass.DIAGNOSTIC
        assert _payload(result.events[0])["reason"] == "unsupported_engine_event_type"
        assert result.stop_worker_stream is True
        assert _event_count(store.transaction_runner, "CONTENT_DELTA") == 0


def test_preview_event_accepts_matching_type_and_data(tmp_path: Path) -> None:
    """匹配 data 类型的 preview event 仍正常写入 preview payload。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _candidate(
            seeded,
            worker_event_index=19,
            data=ContentDeltaData(iteration_id="iter-ok", delta="hello"),
            event_type=EngineEventType.CONTENT_DELTA,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        assert result.events[0].event_class == EventClass.PREVIEW
        assert _payload(result.events[0])["delta"] == "hello"


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
            transaction_runner=store.transaction_runner
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        assert result.events[0].event_class == EventClass.PREVIEW
        payload = _payload(result.events[0])
        assert payload["provider_request_id"] == "req-iteration"
        assert payload["client_correlation_id"] == "client-iteration"


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试 durable store options。

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


def _seed_active_run(
    transaction_runner: HostTransactionRunner, *, display_text: str = "hello"
) -> _SeededRun:
    """创建已 worker accepted 的 active Run。

    :param transaction_runner: Host transaction runner。
    :param display_text: 当前用户输入展示文本。
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
                    payload_json={"display_text": display_text},
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
                queue_policy="queue",
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
    return seeded


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

        return EventLogStore().append_event(
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
        ).row

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
            cancellation_token=StubCancellationToken(),
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
        cancellation_token=StubCancellationToken(),
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
        normalized_arguments_digest=sha256_digest_json({"arguments": "lookup"}),
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
        input_event = EventLogStore().append_event(
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
        ).row
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
