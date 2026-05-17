"""Host Phase 5 EngineEvent ingest 映射测试。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

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
from dayu.host.durable.codec import sha256_digest_json
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
from dayu.host.durable.run_transition import (
    AcceptWorkerRunningInput,
    CreateRunningRunInput,
    accept_worker_running_in_transaction,
    create_running_run_with_starting_attempt_in_transaction,
)
from dayu.host.durable.session_lifecycle import ensure_session
from dayu.host.durable.state import (
    DispatchRecordStatus,
    RunStartReason,
    WaitResumePolicy,
    WorkerKind,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatching_after_lane_row,
    read_attempt_by_id,
    read_dispatch_record_by_attempt_id,
    read_run_by_id,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
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


@dataclass(frozen=True, slots=True)
class _SeededRun:
    """测试中创建的 active Engine run。"""

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str


class _NeverCancelledToken:
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回取消状态。

        :returns: 始终为 ``False``。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终为 ``None``。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终为 ``None``。
        """

        return None


class _WakeupSpy:
    """测试用 wakeup port。"""

    def __init__(self) -> None:
        """初始化 spy。

        :returns: ``None``。
        """

        self.promoted_session_ids: list[str] = []

    def wake_dispatch(self, record: PendingDispatchRecord) -> None:
        """忽略 dispatch wakeup。

        :param record: pending dispatch record。
        :returns: ``None``。
        """

        del record

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
        assert payload["recoverable"] is False
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
        payload = _payload(result.events[1])
        assert payload["unsupported_later_owner"] == "phase10"
        run_status, _attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.FAILED


def test_context_compaction_requested_accepts_none_budget_and_fails(
    tmp_path: Path,
) -> None:
    """context_compaction_requested 允许 budget_state=None 并按 unsupported recovery 失败收口。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        candidate = _candidate(
            seeded,
            worker_event_index=4,
            data=ContextCompactionRequestedData(
                iteration_id="iter-1",
                budget_state=None,
                reason="provider_overflow",
                provider_request_id=None,
            ),
            event_type=EngineEventType.CONTEXT_COMPACTION_REQUESTED,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner
        ).ingest(candidate)

        assert result.events[0].event_class == EventClass.DIAGNOSTIC
        assert result.events[1].event_type == "ATTEMPT_FAILED"
        assert _payload(result.events[0])["budget_state_present"] is False
        run_status, _attempt_status = _statuses(store.transaction_runner, seeded)
        assert run_status == RunStatus.FAILED


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
        assert result.reason == "terminal_already_closed"
        assert _payload(result.events[0])["reason"] == "terminal_already_closed"
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
            transaction_runner=store.transaction_runner
        ).ingest(candidate)

        assert result.events[0].event_class == EventClass.PROJECTION_SIGNAL
        assert result.events[0].event_type == "USAGE_REPORTED"
        assert _payload(result.events[0])["total_tokens"] == 30
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
                raw_payload={"raw": "payload"},
                partial_tool_calls=(),
            ),
            event_type=EngineEventType.PROVIDER_PROTOCOL_ERROR,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner
        ).ingest(candidate)

        assert result.events[0].event_class == EventClass.DIAGNOSTIC
        assert result.events[0].event_type == "PROVIDER_PROTOCOL_ERROR"
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


def _seed_active_run(transaction_runner: HostTransactionRunner) -> _SeededRun:
    """创建已 worker accepted 的 active Run。

    :param transaction_runner: Host transaction runner。
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
                    payload_json={"display_text": "hello"},
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
            cancellation_token=_NeverCancelledToken(),
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
        cancellation_token=_NeverCancelledToken(),
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
