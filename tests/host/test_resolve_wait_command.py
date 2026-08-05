"""Host resolve_wait command 与 waiting resume 测试。"""

from __future__ import annotations

from dayu.engine.contracts.structured_output import StructuredOutputCapability

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.tool_await import ToolAwaitKind, ToolAwaitSpec
from dayu.contracts.tool_outcome import (
    TOOL_CANCELLED_REASON_TIMEOUT,
    ToolCancelledOutcome,
)
from dayu.contracts.tool_result import ToolResultFailure, ToolResultSuccess
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.messages import AssistantMessage, ToolMessage, UserMessage
from dayu.engine.contracts.runner_spec import ClientCorrelationPolicy, RunnerCallOptions, RunnerSpec
from dayu.host._execution_config_projection import (
    effective_execution_config_json,
    effective_execution_snapshot_from_json,
)
from dayu.host._runner_call_manifest import (
    RunnerCallSizingUnavailableReason,
    complete_runner_call_sizing_snapshot,
    unavailable_runner_call_sizing_snapshot,
)
from dayu.host.queue_policy import RunQueuePolicy
from dayu.host.admission import effective_tool_facts_json
from dayu.host import (
    AttemptDispatchSnapshot,
    AuthorizationClaim,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    OperationContext,
    ResolveWaitCancelledOutcome,
    ResolveWaitCompletedOutcome,
    ResolveWaitFailedOutcome,
    ResolveWaitLostOutcome,
    ResolveWaitRequest,
    RunStatus,
    WaitProviderStatusRef,
    WaitResolutionSource,
    get_run,
    resolve_wait,
)
from dayu.host.api import (
    EnsureSessionRequest,
    HostCommandHandleOptions,
    OrdinaryRunExecutionBaseline,
    WaitAdapterKey,
)
from dayu.host.command import HostCommandHandle
from dayu.host.tooling import HostToolingOptions
from dayu.host.context_budget import (
    CONTEXT_ESTIMATOR_CONTRACT,
    ContextBudgetDecision,
    ContextEstimatorContract,
    ContextPressureLevel,
    ContextSizingStage,
    build_conservative_context_sizing_result_from_atoms,
)
from dayu.host.context_events import (
    CONTEXT_BUDGET_EVALUATED,
    append_context_budget_evaluated_in_transaction,
    parse_context_budget_evaluated_payload,
)
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.payload import PayloadStore
from dayu.host.durable.memory import read_latest_memory_snapshot
from dayu.host.durable.liveness import HostInstanceIdentity, register_current_instance
from dayu.host.durable.idempotency import IdempotencyStore
from dayu.host.durable.run_transition import (
    AcceptWorkerRunningInput,
    CreateAcceptedRunInput,
    CreateRunningRunInput,
    ResumeRunFromWaitingInput,
    StartGovernedRunInput,
    WaitingRunTerminalInput,
    accept_worker_running_in_transaction,
    create_accepted_run_in_transaction,
    create_running_run_with_starting_attempt_in_transaction,
    fail_run_from_waiting_in_transaction,
    resume_run_from_waiting_in_transaction,
    start_governed_run_with_starting_attempt_in_transaction,
)
from dayu.host.durable.schema import (
    TABLE_EVENT_LOG,
    TABLE_HOST_ATTEMPTS,
    TABLE_HOST_ATTEMPT_DISPATCH_RECORDS,
    TABLE_HOST_RUNS,
    TABLE_HOST_WAIT_RECORDS,
)
from dayu.host.durable.session_lifecycle import ensure_session
from dayu.host.durable.state import (
    DispatchRecordStatus,
    DispatchRecordRow,
    RunStartReason,
    RunRow,
    StateMutationStatus,
    WaitRecordRow,
    WaitRecordStatus,
    WaitResumePolicy,
    WorkerKind,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatching_after_lane_row,
    read_dispatch_record_by_attempt_id,
    read_wait_record_by_id,
)
from dayu.host.durable.transaction import HostRow, HostTransaction, HostTransactionRunner
from dayu.host.admission import create_host_admission_service
from dayu.host.accepted_tool_outcome import (
    accepted_tool_outcome_digest,
    accepted_tool_outcome_json,
)
from dayu.host.memory import (
    CONVERSATION_MEMORY_CONSUMER_ID,
    default_memory_projection_policy,
    digest_memory_projection_policy,
)
from dayu.host.memory_repair import catch_up_conversation_memory_projection
from dayu.host.projection import ProjectionCatchupPort
from dayu.host.run_input import (
    PolicySnapshot,
    SessionContinuityView,
    ToolExecutionMode,
    create_no_tool_run_input_builder,
    prepare_runner_call_candidate_in_transaction,
    record_prepared_runner_call_candidate_in_transaction,
)
from dayu.host.wait_adapter import WaitAdapterBinding, WaitExternalJobRefSource
from dayu.host.waiting import (
    DefaultHostResolveWaitService,
    DefaultHostToolAwaitingAcceptPort,
    ToolAwaitingAcceptCandidate,
    ToolAwaitingAcceptedAck,
    ResolveWaitResult,
    _resolve_created_event_ref,
)
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL
from tests.host.execution_handle_support import create_execution_command_handle

_NOW = datetime(2026, 5, 16, 1, 2, 3, tzinfo=UTC)
_OBSERVED = datetime(2026, 5, 16, 1, 5, 7, tzinfo=UTC)
_OBSERVED_REPLAY = datetime(2026, 5, 16, 1, 6, 8, tzinfo=UTC)
_CALL_CONTEXT_DIGEST = sha256_digest_json({"context": "resolve-wait-test"})


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
        raise RuntimeError("forced resolve wait projection catch-up failure")


class _CountingEventLogStore(EventLogStore):
    """测试用 EventLog store，记录 read_event_by_id 调用。"""

    def __init__(self) -> None:
        """初始化调用记录。

        :returns: ``None``。
        """

        self.read_event_ids: list[str] = []

    def read_event_by_id(
        self, transaction: HostTransaction, event_id: str
    ) -> EventLogRow | None:
        """记录读取的 event id 并委托默认实现。

        :param transaction: 当前 Host transaction。
        :param event_id: EventLog event id。
        :returns: EventLog row；不存在时为 ``None``。
        """

        self.read_event_ids.append(event_id)
        return super().read_event_by_id(transaction, event_id)


@dataclass(frozen=True, slots=True)
class _ResolutionTables:
    """wait-resolution 写入边界涉及的 durable 全表快照。"""

    events: tuple[HostRow, ...]
    runs: tuple[HostRow, ...]
    attempts: tuple[HostRow, ...]
    wait_records: tuple[HostRow, ...]
    dispatch_records: tuple[HostRow, ...]


def test_resolve_wait_completed_resumes_run_and_wakes_dispatch(
    tmp_path: Path,
) -> None:
    """completed outcome 关闭 wait 并创建 resume Attempt / dispatch record。"""

    host = _create_execution_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        request = _completed_request("resolve-completed")

        snapshot = resolve_wait(host, seeded.wait_id, request)

        wait_record, dispatch_record, events = _read_resolution_state(
            host._transaction_runner(), seeded.wait_id, snapshot.current_attempt_id
        )
        assert snapshot.status is RunStatus.RUNNING
        assert snapshot.current_attempt_id is not None
        assert snapshot.current_attempt_id != seeded.attempt_id
        assert wait_record is not None
        assert wait_record.status is WaitRecordStatus.RESOLVED
        assert dispatch_record is not None
        assert [event.event_type for event in events[-4:]] == [
            "RESUME_REQUESTED",
            "TOOL_RESULT_ACCEPTED",
            "RUN_STARTED",
            "ATTEMPT_STARTED",
        ]
        tool_result = events[-3]
        assert tool_result.attempt_id == seeded.attempt_id
        assert tool_result.execution_id == seeded.execution_id
        assert dispatch_record.execution_id != seeded.execution_id
        assert events[-2].reason_json == '{"start_reason":"resume"}'
        request_for_resume = _build_resume_request(
            host._transaction_runner(), seeded.session_id, snapshot.current_attempt_id
        )
        assert len(request_for_resume.messages) == 4
        assert isinstance(request_for_resume.messages[1], UserMessage)
        assert request_for_resume.messages[1].content == "hello"
        assistant = request_for_resume.messages[2]
        assert isinstance(assistant, AssistantMessage)
        assert len(assistant.tool_calls) == 1
        assert assistant.tool_calls[0].id == "tool-call-resolve"
        assert assistant.tool_calls[0].name == "long_tool"
        assert assistant.tool_calls[0].arguments == {"name": "long_tool"}
        tool = request_for_resume.messages[3]
        assert isinstance(tool, ToolMessage)
        assert tool.tool_call_id == "tool-call-resolve"
        assert tool.content == '{"answer": 42}'
    finally:
        host.close()


@pytest.mark.parametrize("outcome_kind", ("completed", "cancelled"))
def test_budgeted_wait_resume_orders_continuation_fact_before_start(
    tmp_path: Path,
    outcome_kind: str,
) -> None:
    """completed/cancelled wait以hard continuation fact恢复且仍allow。

    :param tmp_path: pytest临时目录。
    :param outcome_kind: completed或tool-level cancelled outcome。
    :returns: ``None``。
    :raises AssertionError: producer顺序、pressure或decision错误时抛出。
    """

    host = _create_execution_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host, budgeted_hard=True)
        before_events = _events(host._transaction_runner())
        request = (
            _completed_request("resolve-budgeted-completed")
            if outcome_kind == "completed"
            else _cancelled_request("resolve-budgeted-cancelled")
        )

        snapshot = resolve_wait(host, seeded.wait_id, request)

        after_events = _events(host._transaction_runner())
        new_events = after_events[len(before_events) :]
        new_event_types = tuple(event.event_type for event in new_events)
        manifest_index = new_event_types.index(
            "RUNNER_CALL_INPUT_ASSEMBLED"
        )
        fact_index = new_event_types.index(CONTEXT_BUDGET_EVALUATED)
        run_started_index = new_event_types.index("RUN_STARTED")
        attempt_started_index = new_event_types.index("ATTEMPT_STARTED")
        assert (
            manifest_index
            < fact_index
            < run_started_index
            < attempt_started_index
        )
        fact = parse_context_budget_evaluated_payload(
            cast(
                Mapping[str, JsonValue],
                json.loads(new_events[fact_index].payload_json),
            )
        )
        assert fact.sizing_stage is ContextSizingStage.CONTINUATION
        assert (
            fact.pressure_level
            is ContextPressureLevel.HARD_THRESHOLD_EXCEEDED
        )
        assert fact.budget_decision is ContextBudgetDecision.ALLOW_DISPATCH
        assert snapshot.status is RunStatus.RUNNING
        assert snapshot.current_attempt_id != seeded.attempt_id
        assert len(_events_by_type(after_events, CONTEXT_BUDGET_EVALUATED)) == 2
    finally:
        host.close()


@pytest.mark.parametrize("outcome_kind", ("failed", "lost"))
def test_failed_lost_wait_add_no_budget_fact_manifest_or_attempt(
    tmp_path: Path,
    outcome_kind: str,
) -> None:
    """failed/lost wait只执行terminal owner，不创建continuation artifacts。

    :param tmp_path: pytest临时目录。
    :param outcome_kind: failed或lost terminal outcome。
    :returns: ``None``。
    :raises AssertionError: terminal路径新增fact、manifest或Attempt时抛出。
    """

    host = _create_execution_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host, budgeted_hard=True)
        before = _read_resolution_tables(host._transaction_runner())
        before_event_rows = _events(host._transaction_runner())
        request = (
            _failed_request("resolve-budgeted-failed")
            if outcome_kind == "failed"
            else _lost_request("resolve-budgeted-lost")
        )

        snapshot = resolve_wait(host, seeded.wait_id, request)

        after = _read_resolution_tables(host._transaction_runner())
        after_event_rows = _events(host._transaction_runner())
        assert snapshot.status is (
            RunStatus.FAILED
            if outcome_kind == "failed"
            else RunStatus.LOST
        )
        assert len(after.attempts) == len(before.attempts)
        assert len(after.dispatch_records) == len(before.dispatch_records)
        assert len(
            _events_by_type(after_event_rows, CONTEXT_BUDGET_EVALUATED)
        ) == len(
            _events_by_type(before_event_rows, CONTEXT_BUDGET_EVALUATED)
        )
        assert len(
            _events_by_type(after_event_rows, "RUNNER_CALL_INPUT_ASSEMBLED")
        ) == len(
            _events_by_type(
                before_event_rows,
                "RUNNER_CALL_INPUT_ASSEMBLED",
            )
        )
    finally:
        host.close()


def test_resolve_created_event_ref_fails_closed_for_missing_resume_start() -> None:
    """resolve wait resume 结果缺 started_event_id 时 fail closed。"""

    result = ResolveWaitResult(
        run=_run_row(started_event_id=None, started_event_sequence=None),
        dispatch_record=_dispatch_record_row(),
        idempotent_replay=False,
    )

    with pytest.raises(HostApiError) as error_info:
        _resolve_created_event_ref(result)

    assert error_info.value.code is HostApiErrorCode.INTERNAL_ERROR


def test_resolve_wait_survives_projection_catchup_failure(
    tmp_path: Path,
) -> None:
    """resolve_wait commit 后 projection catch-up 失败不影响恢复结果。"""

    host = _create_execution_handle(_options(tmp_path))
    projection = _FailingProjectionCatchup()
    host._admission_service = create_host_admission_service(
        host._transaction_runner(),
        terminal_post_commit_port=host._terminal_post_commit_port,
        payload_store=PayloadStore(),
        event_log_store=None,
        idempotency_store=None,
        clock=None,
        id_factory=None,
        wakeup_port=None,
        projection_catchup_port=projection,
        ordinary_run_baseline=_ordinary_run_baseline(),
        tooling_options=None,
        context_budget_policy=None,
        memory_projection_policy=default_memory_projection_policy(),
        enable_truncation_manager=False,
        owner_host_instance_id=host.host_handle_id,
    )
    try:
        seeded = _seed_waiting_run(host)
        snapshot = resolve_wait(host, seeded.wait_id, _completed_request("resolve-catchup"))

        assert snapshot.status is RunStatus.RUNNING
        assert snapshot.current_attempt_id is not None
        assert projection.calls == 1
    finally:
        host.close()


def test_resolve_wait_rejects_expired_wait_from_common_owner(
    tmp_path: Path,
) -> None:
    """过期 wait 由 common owner 收为 FAILED 后拒绝迟到结果。"""

    host = _create_execution_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        _set_wait_deadline_text(
            host._transaction_runner(),
            seeded.wait_id,
            "2026-05-16T01:05:05.000000Z",
        )

        with pytest.raises(HostApiError) as error_info:
            resolve_wait(host, seeded.wait_id, _completed_request("expired-direct"))

        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)
        late_events = _events_by_type(
            _events(host._transaction_runner()), "WAIT_LATE_RESULT_REJECTED"
        )
        assert error_info.value.code is HostApiErrorCode.INVALID_STATE
        assert wait_record.status is WaitRecordStatus.FAILED
        assert get_run(host, seeded.run_id).status is RunStatus.FAILED
        assert len(late_events) == 1
    finally:
        host.close()


def test_resolve_wait_invalid_deadline_fails_closed_without_lost(
    tmp_path: Path,
) -> None:
    """非法持久化 deadline fail closed，不能被转换成业务 LOST。"""

    host = _create_execution_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        _set_wait_deadline_text(
            host._transaction_runner(), seeded.wait_id, "not-a-timestamp"
        )
        before_events = _events(host._transaction_runner())

        with pytest.raises(HostApiError) as error_info:
            resolve_wait(host, seeded.wait_id, _lost_request("invalid-direct"))

        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)
        assert error_info.value.code is HostApiErrorCode.INVALID_STATE
        assert wait_record.status is WaitRecordStatus.WAITING
        assert _events(host._transaction_runner()) == before_events
    finally:
        host.close()


def test_resolve_wait_committed_tool_result_direct_catchup_without_fact(
    tmp_path: Path,
) -> None:
    """resolve_wait 提交工具结果后直接 catch-up 可覆盖 accepted tool result cursor。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: resolve_wait committed 工具结果未被 memory 覆盖时抛出。
    """

    policy = default_memory_projection_policy()
    host = _create_execution_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)

        snapshot = resolve_wait(
            host, seeded.wait_id, _completed_request("resolve-memory-catchup")
        )
        tool_events = _events_by_type(
            _events(host._transaction_runner()), "TOOL_RESULT_ACCEPTED"
        )
        assert len(tool_events) > 0
        result_payload = json.loads(tool_events[-1].payload_json)
        assert "accepted_evidence_envelope" in result_payload
        assert "raw_tool_outcome" in result_payload
        catch_up_conversation_memory_projection(
            host._transaction_runner(),
            policy=policy,
            batch_size=8,
            max_event_sequence=tool_events[-1].event_sequence,
        )
        memory_snapshot = host._transaction_runner().run_read(
            lambda transaction: read_latest_memory_snapshot(
                transaction,
                session_id=seeded.session_id,
                consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                policy_digest=digest_memory_projection_policy(policy),
            )
        )

        assert snapshot.status is RunStatus.RUNNING
        assert memory_snapshot is not None
        assert memory_snapshot.snapshot.evidence_fact_memory.evidence_backed_facts == ()
        recent_evidence = memory_snapshot.snapshot.evidence_fact_memory.recent_evidence_items
        assert len(recent_evidence) == 1
        evidence_text = recent_evidence[0].text
        assert "工具名称：long_tool" in evidence_text
        assert '查询语义：参数：{"arguments":{"name":"long_tool"}}' in evidence_text
        assert '"answer":42' in evidence_text
        assert "原始工具响应不可用" not in evidence_text
        assert "TOOL_AWAITING" not in evidence_text
        assert "wait" not in evidence_text
        assert (
            memory_snapshot.snapshot.cursor.checkpoint_event_sequence
            >= tool_events[-1].event_sequence
        )
    finally:
        host.close()


def test_resolve_wait_uses_injected_event_log_store_for_request_atom(
    tmp_path: Path,
) -> None:
    """resolve wait request atom 校验使用注入 EventLogStore，而非临时实例。"""

    host = _create_execution_handle(_options(tmp_path))
    event_log_store = _CountingEventLogStore()
    service = DefaultHostResolveWaitService(
        transaction_runner=host._transaction_runner(),
        terminal_post_commit_port=host._terminal_post_commit_port,
        event_log_store=event_log_store,
        idempotency_store=IdempotencyStore(),
        payload_store=PayloadStore(),
        memory_projection_policy=default_memory_projection_policy(),
    )
    try:
        seeded = _seed_waiting_run(host)

        result = service.resolve_wait(
            seeded.wait_id, _completed_request("resolve-di-event-log")
        )

        assert result.run.status is RunStatus.RUNNING
        assert (
            f"event-tool-call-requested-awaiting-{seeded.wait_id.removeprefix('wait-')}"
            in event_log_store.read_event_ids
        )
        assert (
            f"event-tool-awaiting-{seeded.wait_id.removeprefix('wait-')}"
            in event_log_store.read_event_ids
        )
    finally:
        host.close()


def test_resolve_wait_rejects_request_atom_arguments_digest_mismatch(
    tmp_path: Path,
) -> None:
    """wait-resolution request atom 参数 digest 拼错时必须 fail fast。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: digest mismatch 未被拒绝时抛出。
    """

    host = _create_execution_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        _rewrite_wait_request_atom_digest(host._transaction_runner(), seeded.wait_id)
        before_events = _events(host._transaction_runner())

        with pytest.raises(HostApiError) as exc_info:
            resolve_wait(
                host,
                seeded.wait_id,
                _completed_request("resolve-request-digest-mismatch"),
            )
        assert isinstance(exc_info.value.__cause__, HostDurableError)
        assert "payload digest must match normalized digest" in str(
            exc_info.value.__cause__
        )
        assert _events(host._transaction_runner()) == before_events
        assert get_run(host, seeded.run_id).status is RunStatus.WAITING
        assert _read_wait(host._transaction_runner(), seeded.wait_id).status is (
            WaitRecordStatus.WAITING
        )
    finally:
        host.close()


@pytest.mark.parametrize(
    "link_case",
    ("missing", "wrong_shape", "missing_row", "wrong_type", "sequence_mismatch"),
)
def test_resolve_wait_rejects_broken_awaiting_request_link_without_mutation(
    tmp_path: Path,
    link_case: str,
) -> None:
    """awaiting 显式 request ref 缺失或损坏时不写 resolution/resume facts。"""

    host = _create_execution_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        _rewrite_wait_awaiting_request_link(
            host._transaction_runner(),
            seeded.wait_id,
            link_case=link_case,
        )
        before_events = _events(host._transaction_runner())

        with pytest.raises(HostApiError) as exc_info:
            resolve_wait(
                host,
                seeded.wait_id,
                _completed_request(f"resolve-broken-link-{link_case}"),
            )

        assert isinstance(exc_info.value.__cause__, HostDurableError)
        assert _events(host._transaction_runner()) == before_events
        assert get_run(host, seeded.run_id).status is RunStatus.WAITING
        assert _read_wait(host._transaction_runner(), seeded.wait_id).status is (
            WaitRecordStatus.WAITING
        )
    finally:
        host.close()


def test_resolve_wait_logs_ids_without_result_payload(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """resolve_wait 日志记录 wait / run ids，不记录 result payload。

    :param tmp_path: pytest 临时目录。
    :param caplog: pytest 日志捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 日志缺少字段或泄漏 result payload 时抛出。
    """

    host = _create_execution_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)

        with caplog.at_level(VERBOSE_LOG_LEVEL, logger="dayu.host.waiting"):
            snapshot = resolve_wait(
                host, seeded.wait_id, _completed_request("resolve-logging")
            )

        assert snapshot.status is RunStatus.RUNNING
        assert "host.waiting.resolve_wait.accepted" in caplog.text
        assert "host.waiting.resolve_wait.committed" in caplog.text
        assert seeded.wait_id in caplog.text
        assert seeded.run_id in caplog.text
        assert '"answer": 42' not in caplog.text
        assert "result" not in caplog.text
    finally:
        host.close()


def test_resolve_wait_same_key_same_outcome_replays_with_different_observed_at(
    tmp_path: Path,
) -> None:
    """同 wait_id + idempotency_key + outcome 不因 observed_at 变化而冲突。"""

    host = _create_execution_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        request = _completed_request("resolve-replay")
        replay_request = replace(request, observed_at=_OBSERVED_REPLAY)

        first = resolve_wait(host, seeded.wait_id, request)
        before_events = _events(host._transaction_runner())
        before_tool_results = _events_by_type(before_events, "TOOL_RESULT_ACCEPTED")
        second = resolve_wait(host, seeded.wait_id, replay_request)
        after_events = _events(host._transaction_runner())

        assert second.current_attempt_id == first.current_attempt_id
        assert after_events == before_events
        assert _events_by_type(after_events, "TOOL_RESULT_ACCEPTED") == (
            before_tool_results
        )
    finally:
        host.close()


def test_resolve_wait_same_key_different_outcome_conflicts(
    tmp_path: Path,
) -> None:
    """同 key 不同 outcome 返回 idempotency_conflict 且不追加事实。"""

    host = _create_execution_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        request = _completed_request("resolve-conflict")
        conflict = replace(
            request,
            outcome=ResolveWaitCompletedOutcome(
                result=ToolResultSuccess(
                    ok=True,
                    value={"answer": "changed"},
                    meta=None,
                ),
                payload_ref=None,
            ),
        )

        resolve_wait(host, seeded.wait_id, request)
        before_events = _events(host._transaction_runner())
        with pytest.raises(HostApiError) as exc_info:
            resolve_wait(host, seeded.wait_id, conflict)

        assert exc_info.value.code is HostApiErrorCode.IDEMPOTENCY_CONFLICT
        assert _events(host._transaction_runner()) == before_events
    finally:
        host.close()


def test_resolve_wait_failed_and_lost_close_run_without_resume_attempt(
    tmp_path: Path,
) -> None:
    """failed / lost outcome 收口 Run 且不创建 resume dispatch。"""

    failed_host = _create_execution_handle(_options(tmp_path / "failed"))
    lost_host = _create_execution_handle(_options(tmp_path / "lost"))
    try:
        failed_seeded = _seed_waiting_run(failed_host)
        failed_before = _read_resolution_tables(failed_host._transaction_runner())
        failed = resolve_wait(
            failed_host,
            failed_seeded.wait_id,
            _failed_request("resolve-failed", hint="retry after provider recovery"),
        )
        lost_seeded = _seed_waiting_run(lost_host)
        lost_before = _read_resolution_tables(lost_host._transaction_runner())
        lost = resolve_wait(
            lost_host,
            lost_seeded.wait_id,
            _lost_request("resolve-lost"),
        )

        failed_wait = _read_wait(failed_host._transaction_runner(), failed_seeded.wait_id)
        lost_wait = _read_wait(lost_host._transaction_runner(), lost_seeded.wait_id)
        failed_after = _read_resolution_tables(failed_host._transaction_runner())
        lost_after = _read_resolution_tables(lost_host._transaction_runner())
        assert failed.status is RunStatus.FAILED
        assert failed.current_attempt_id == failed_seeded.attempt_id
        assert failed_wait.status is WaitRecordStatus.FAILED
        assert lost.status is RunStatus.LOST
        assert lost.current_attempt_id == lost_seeded.attempt_id
        assert lost_wait.status is WaitRecordStatus.LOST
        failed_run_failed = _single_event(
            _events(failed_host._transaction_runner()), "RUN_FAILED"
        )
        lost_run_lost = _single_event(_events(lost_host._transaction_runner()), "RUN_LOST")
        failed_tool_result = _single_event(
            _events(failed_host._transaction_runner()), "TOOL_RESULT_ACCEPTED"
        )
        lost_tool_result = _single_event(
            _events(lost_host._transaction_runner()), "TOOL_RESULT_ACCEPTED"
        )
        assert failed_tool_result.attempt_id == failed_seeded.attempt_id
        assert failed_tool_result.execution_id == failed_seeded.execution_id
        assert lost_tool_result.attempt_id == lost_seeded.attempt_id
        assert lost_tool_result.execution_id == lost_seeded.execution_id
        assert len(failed_after.attempts) == len(failed_before.attempts)
        assert len(failed_after.dispatch_records) == len(
            failed_before.dispatch_records
        )
        assert len(lost_after.attempts) == len(lost_before.attempts)
        assert len(lost_after.dispatch_records) == len(lost_before.dispatch_records)
        assert all(
            event.get("event_type") != "RESUME_REQUESTED"
            for event in failed_after.events
        )
        assert all(
            event.get("event_type") != "RESUME_REQUESTED"
            for event in lost_after.events
        )
        failed_payload = cast(
            Mapping[str, JsonValue], json.loads(failed_run_failed.payload_json)
        )
        lost_payload = cast(
            Mapping[str, JsonValue], json.loads(lost_run_lost.payload_json)
        )
        assert failed_payload["message"] == (
            "provider failed retry after provider recovery"
        )
        assert lost_payload["message"] == "adapter cannot confirm external job"
    finally:
        failed_host.close()
        lost_host.close()


@pytest.mark.parametrize("transition_kind", ("completed", "failed"))
def test_waiting_resolution_transition_rejects_execution_identity_mismatch(
    tmp_path: Path,
    transition_kind: Literal["completed", "failed"],
) -> None:
    """WaitRecord 与源 Attempt execution 不同源时 transition 不产生任何写入。

    :param tmp_path: pytest 临时目录。
    :param transition_kind: direct resume 或 terminal transition 分支。
    :returns: ``None``。
    :raises AssertionError: transition 未 fail closed 或 durable 表发生变化时抛出。
    """

    host = _create_execution_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        auxiliary_execution_id = _seed_auxiliary_starting_attempt(
            host._transaction_runner()
        )
        _rewrite_wait_execution_id(
            host._transaction_runner(),
            wait_id=seeded.wait_id,
            execution_id=auxiliary_execution_id,
        )
        before = _read_resolution_tables(host._transaction_runner())

        if transition_kind == "completed":
            result = host._transaction_runner().run_write(
                lambda transaction: resume_run_from_waiting_in_transaction(
                    transaction,
                    EventLogStore(),
                    _direct_resume_transition_input(seeded),
                )
            )
        else:
            result = host._transaction_runner().run_write(
                lambda transaction: fail_run_from_waiting_in_transaction(
                    transaction,
                    EventLogStore(),
                    _direct_failed_transition_input(seeded),
                )
            )

        after = _read_resolution_tables(host._transaction_runner())
        assert result.status is StateMutationStatus.INVALID_STATE
        assert result.resume_requested_event is None
        assert result.tool_result_event is None
        assert result.run_event is None
        assert result.attempt_started_event is None
        assert result.dispatch_record is None
        assert after == before
    finally:
        host.close()


@pytest.mark.parametrize("precondition_kind", ("missing_run", "missing_wait"))
def test_waiting_resolution_transition_returns_not_found_without_mutation(
    tmp_path: Path,
    precondition_kind: Literal["missing_run", "missing_wait"],
) -> None:
    """waiting-resolution owner 缺少 durable 主体时不产生任何写入。

    :param tmp_path: pytest 临时目录。
    :param precondition_kind: 缺失目标 Run 或 WaitRecord 的 direct transition 分支。
    :returns: ``None``。
    :raises AssertionError: transition 未返回 NOT_FOUND 或 durable 表发生变化时抛出。
    """

    host = _create_execution_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        before = _read_resolution_tables(host._transaction_runner())

        if precondition_kind == "missing_run":
            resume_request = replace(
                _direct_resume_transition_input(seeded),
                run_id="run-resolve-missing",
            )
            result = host._transaction_runner().run_write(
                lambda transaction: resume_run_from_waiting_in_transaction(
                    transaction,
                    EventLogStore(),
                    resume_request,
                )
            )
            assert result.run is None
            assert result.attempt is not None
            assert result.wait_record is not None
        else:
            terminal_request = replace(
                _direct_failed_transition_input(seeded),
                wait_id="wait-resolve-missing",
            )
            result = host._transaction_runner().run_write(
                lambda transaction: fail_run_from_waiting_in_transaction(
                    transaction,
                    EventLogStore(),
                    terminal_request,
                )
            )
            assert result.run is not None
            assert result.attempt is not None
            assert result.wait_record is None

        after = _read_resolution_tables(host._transaction_runner())
        assert result.status is StateMutationStatus.NOT_FOUND
        assert result.resume_requested_event is None
        assert result.tool_result_event is None
        assert result.run_event is None
        assert result.attempt_started_event is None
        assert result.dispatch_record is None
        assert after == before
    finally:
        host.close()


def test_resolve_wait_lost_same_key_replays_terminal_snapshot(
    tmp_path: Path,
) -> None:
    """lost outcome 同 key 重放返回终态 snapshot 且不追加事实。"""

    host = _create_execution_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        request = _lost_request("resolve-lost-replay")

        first = resolve_wait(host, seeded.wait_id, request)
        before_events = _events(host._transaction_runner())
        second = resolve_wait(host, seeded.wait_id, request)
        after_events = _events(host._transaction_runner())

        assert first.status is RunStatus.LOST
        assert second.status is RunStatus.LOST
        assert second.current_attempt_id == first.current_attempt_id
        assert after_events == before_events
    finally:
        host.close()


def test_resolve_wait_tool_cancelled_resumes_as_resolved_wait(
    tmp_path: Path,
) -> None:
    """工具级 cancelled outcome 按 resolved wait 恢复，而不是取消 wait record。"""

    host = _create_execution_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)

        snapshot = resolve_wait(
            host,
            seeded.wait_id,
            _cancelled_request("resolve-cancelled-tool"),
        )

        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)
        tool_events = _events_by_type(
            _events(host._transaction_runner()), "TOOL_RESULT_ACCEPTED"
        )
        result_payload = cast(
            Mapping[str, JsonValue], json.loads(tool_events[-1].payload_json)
        )
        request = _cancelled_request("resolve-cancelled-tool")
        assert isinstance(request.outcome, ResolveWaitCancelledOutcome)
        expected_atom = accepted_tool_outcome_json(request.outcome.result)
        assert result_payload["raw_tool_outcome"] == expected_atom
        assert result_payload["result"] == expected_atom
        assert result_payload["outcome_digest"] == accepted_tool_outcome_digest(
            request.outcome.result
        )
        assert snapshot.current_attempt_id is not None
        request_for_resume = _build_resume_request(
            host._transaction_runner(), seeded.session_id, snapshot.current_attempt_id
        )
        tool_message = request_for_resume.messages[3]
        assert isinstance(tool_message, ToolMessage)
        assert tool_message.content == (
            '{"cancelled": true, "message": "tool timed out", "reason": "timeout"}'
        )
        assert snapshot.status is RunStatus.RUNNING
        assert snapshot.current_attempt_id != seeded.attempt_id
        assert wait_record.status is WaitRecordStatus.RESOLVED
    finally:
        host.close()


class _SeededWaitingRun:
    """测试中创建的 waiting Run 引用。"""

    def __init__(
        self,
        *,
        session_id: str,
        run_id: str,
        attempt_id: str,
        execution_id: str,
        dispatch_record_id: str,
        wait_id: str,
    ) -> None:
        """初始化 seeded waiting run 引用。

        :param session_id: Session id。
        :param run_id: Run id。
        :param attempt_id: Attempt id。
        :param execution_id: execution id。
        :param dispatch_record_id: dispatch record id。
        :param wait_id: wait record id。
        :returns: ``None``。
        """

        self.session_id = session_id
        self.run_id = run_id
        self.attempt_id = attempt_id
        self.execution_id = execution_id
        self.dispatch_record_id = dispatch_record_id
        self.wait_id = wait_id


class _OpenCancellationToken:
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回当前是否已取消。

        :returns: 始终返回 ``False``。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终返回 ``None``。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终返回 ``None``。
        """

        return None


def _run_row(
    *, started_event_id: str | None, started_event_sequence: int | None
) -> RunRow:
    """构造 resolve wait helper 测试用 RunRow。

    :param started_event_id: run started event id。
    :param started_event_sequence: run started event sequence。
    :returns: RunRow。
    """

    return RunRow(
        run_id="run-resolve-helper",
        session_id="session-resolve-helper",
        status=RunStatus.RUNNING,
        client_request_id="client-resolve-helper",
        input_event_id="event-input-resolve-helper",
        input_event_sequence=1,
        accepted_event_id="event-run-accepted-resolve-helper",
        accepted_event_sequence=2,
        queued_event_id=None,
        queued_event_sequence=None,
        started_event_id=started_event_id,
        started_event_sequence=started_event_sequence,
        terminal_event_id=None,
        terminal_event_sequence=None,
        cancel_request_event_id=None,
        current_attempt_id="attempt-resolve-helper",
        source_run_id=None,
        source_run_relation=None,
        execution_target="target-resolve-helper",
        queue_policy=RunQueuePolicy.QUEUE,
        created_at="2026-05-16T01:02:03.000000Z",
        updated_at="2026-05-16T01:02:03.000000Z",
        terminal_at=None,
    )


def _dispatch_record_row() -> DispatchRecordRow:
    """构造 resolve wait helper 测试用 DispatchRecordRow。

    :returns: DispatchRecordRow。
    """

    return DispatchRecordRow(
        dispatch_record_id="dispatch-resolve-helper",
        run_id="run-resolve-helper",
        attempt_id="attempt-resolve-helper",
        execution_id="execution-resolve-helper",
        status=DispatchRecordStatus.PENDING,
        worker_kind=WorkerKind.LOCAL,
        execution_target="target-resolve-helper",
        owner_host_instance_id=None,
        created_event_id="event-dispatch-created-resolve-helper",
        created_event_sequence=3,
        waiting_for_lane_at=None,
        lane_name=None,
        lane_claim_id=None,
        lane_owner_id=None,
        lane_acquired_at=None,
        dispatching_at=None,
        worker_accepted_at=None,
        worker_accept_event_id=None,
        worker_accept_event_sequence=None,
        cancelled_event_id=None,
        cancelled_event_sequence=None,
        created_at="2026-05-16T01:02:03.000000Z",
        updated_at="2026-05-16T01:02:03.000000Z",
        cancelled_at=None,
    )


def _options(tmp_path: Path) -> HostCommandHandleOptions:
    """构造测试用 Host command handle options。

    :param tmp_path: pytest 临时目录。
    :returns: Host command handle options。
    """

    return HostCommandHandleOptions(
        host_handle_id="host-resolve-wait-test",
        db_path=tmp_path / "host.sqlite3",
        artifact_root=tmp_path / "artifacts",
        create_parent_dirs=True,
        sqlite_busy_timeout_seconds=1.0,
        sqlite_write_busy_retry_count=8,
        sqlite_write_retry_initial_delay_seconds=0.001,
        sqlite_write_retry_backoff_multiplier=1.2,
        sqlite_write_retry_max_delay_seconds=0.02,
        payload_inline_threshold_bytes=4096,
        context_window_size=8192,
        reserved_output_tokens=1024,
    )


def _context(request_id: str = "trace-resolve") -> HostCallContext:
    """构造 Host call context。

    :param request_id: request id。
    :returns: Host call context。
    """

    return HostCallContext(
        actor="analyst",
        source="pytest",
        request_id=request_id,
        authorization_claims=(AuthorizationClaim(name="role", value="tester"),),
        operation_context=OperationContext(
            operation_name="resolve_wait",
            operation_kind="test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="phase7",
            correlation_id=None,
        ),
    )


def _completed_request(idempotency_key: str) -> ResolveWaitRequest:
    """构造 completed resolve wait request。

    :param idempotency_key: resolve wait 幂等键。
    :returns: resolve wait request。
    """

    return ResolveWaitRequest(
        context=_context(idempotency_key),
        idempotency_key=idempotency_key,
        outcome=ResolveWaitCompletedOutcome(
            result=ToolResultSuccess(ok=True, value={"answer": 42}, meta=None),
            payload_ref=None,
        ),
        source=WaitResolutionSource.MANUAL,
        observed_at=_OBSERVED,
    )


def _failed_request(idempotency_key: str, *, hint: str | None = None) -> ResolveWaitRequest:
    """构造 failed resolve wait request。

    :param idempotency_key: resolve wait 幂等键。
    :param hint: 可选恢复提示文本。
    :returns: resolve wait request。
    """

    return ResolveWaitRequest(
        context=_context(idempotency_key),
        idempotency_key=idempotency_key,
        outcome=ResolveWaitFailedOutcome(
            result=ToolResultFailure(
                ok=False,
                error="provider_failed",
                message="provider failed",
                hint=hint,
                meta=None,
            ),
            payload_ref=None,
        ),
        source=WaitResolutionSource.MANUAL,
        observed_at=_OBSERVED,
    )


def _lost_request(idempotency_key: str) -> ResolveWaitRequest:
    """构造 lost resolve wait request。

    :param idempotency_key: resolve wait 幂等键。
    :returns: resolve wait request。
    """

    return ResolveWaitRequest(
        context=_context(idempotency_key),
        idempotency_key=idempotency_key,
        outcome=ResolveWaitLostOutcome(
            reason_code="adapter_lost",
            message="adapter cannot confirm external job",
            provider_status_ref=WaitProviderStatusRef(
                adapter_key=WaitAdapterKey("poll:long-tool"),
                status_ref="provider-status-1",
                status_digest=sha256_digest_json({"status": "lost"}),
            ),
        ),
        source=WaitResolutionSource.POLL,
        observed_at=_OBSERVED,
    )


def _direct_resume_transition_input(
    seeded: _SeededWaitingRun,
) -> ResumeRunFromWaitingInput:
    """构造 direct owner contract 测试使用的完整 resume transition 输入。

    :param seeded: 目标 waiting Run 引用。
    :returns: typed resume transition 输入。
    """

    resolution_digest = sha256_digest_json(
        {"resolution": "direct-resume-execution-mismatch"}
    )
    return ResumeRunFromWaitingInput(
        wait_id=seeded.wait_id,
        run_id=seeded.run_id,
        suspended_attempt_id=seeded.attempt_id,
        resume_attempt_id="attempt-resolve-direct-resume",
        resume_execution_id="execution-resolve-direct-resume",
        resume_dispatch_record_id="dispatch-resolve-direct-resume",
        resume_requested_event_id="event-resume-requested-direct-mismatch",
        tool_result_event_id="event-tool-result-direct-resume-mismatch",
        run_started_event_id="event-run-started-direct-resume-mismatch",
        attempt_started_event_id="event-attempt-started-direct-resume-mismatch",
        occurred_at=_OBSERVED,
        actor="tester",
        source="pytest",
        resolution_idempotency_key="resolve-direct-resume-mismatch",
        resolution_digest=resolution_digest,
        resume_requested_payload={"reason": "wait_resolved"},
        tool_result_payload={"result": "completed"},
        tool_result_payload_ref=None,
        tool_result_payload_digest=None,
        worker_kind=WorkerKind.LOCAL,
        owner_host_instance_id=None,
    )


def _direct_failed_transition_input(
    seeded: _SeededWaitingRun,
) -> WaitingRunTerminalInput:
    """构造 direct owner contract 测试使用的完整 failed transition 输入。

    :param seeded: 目标 waiting Run 引用。
    :returns: typed terminal transition 输入。
    """

    resolution_digest = sha256_digest_json(
        {"resolution": "direct-failed-execution-mismatch"}
    )
    return WaitingRunTerminalInput(
        wait_id=seeded.wait_id,
        run_id=seeded.run_id,
        suspended_attempt_id=seeded.attempt_id,
        tool_result_event_id="event-tool-result-direct-failed-mismatch",
        run_terminal_event_id="event-run-failed-direct-mismatch",
        run_terminal_status=RunStatus.FAILED,
        wait_terminal_status=WaitRecordStatus.FAILED,
        occurred_at=_OBSERVED,
        actor="tester",
        source="pytest",
        reason="wait_failed",
        message="provider failed",
        resolution_idempotency_key="resolve-direct-failed-mismatch",
        resolution_digest=resolution_digest,
        tool_result_payload={"result": "failed"},
        tool_result_payload_ref=None,
        tool_result_payload_digest=None,
    )


def _cancelled_request(idempotency_key: str) -> ResolveWaitRequest:
    """构造工具级 cancelled resolve wait request。

    :param idempotency_key: resolve wait 幂等键。
    :returns: resolve wait request。
    """

    return ResolveWaitRequest(
        context=_context(idempotency_key),
        idempotency_key=idempotency_key,
        outcome=ResolveWaitCancelledOutcome(
            result=ToolCancelledOutcome(
                reason=TOOL_CANCELLED_REASON_TIMEOUT,
                message="tool timed out",
                hint=None,
                meta=None,
            ),
            payload_ref=None,
        ),
        source=WaitResolutionSource.MANUAL,
        observed_at=_OBSERVED,
    )


def _rewrite_wait_request_atom_digest(
    transaction_runner: HostTransactionRunner, wait_id: str
) -> None:
    """把 waiting request atom 的参数 digest 改成错误值。

    :param transaction_runner: Host transaction runner。
    :param wait_id: wait id。
    :returns: ``None``。
    """

    event_id = f"event-tool-call-requested-awaiting-{wait_id.removeprefix('wait-')}"

    def _operation(transaction: HostTransaction) -> None:
        """更新 request atom payload。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        row = EventLogStore().read_event_by_id(transaction, event_id)
        assert row is not None
        payload = json.loads(row.payload_json)
        assert isinstance(payload, dict)
        payload["normalized_arguments_digest"] = sha256_digest_json(
            {"arguments": {"ticker": "WRONG"}}
        )
        transaction.execute(
            f"""
            UPDATE {TABLE_EVENT_LOG}
            SET payload_json = ?
            WHERE event_id = ?
            """,
            (canonical_json_dumps(payload), event_id),
        )

    transaction_runner.run_write(_operation)


def _rewrite_wait_awaiting_request_link(
    transaction_runner: HostTransactionRunner,
    wait_id: str,
    *,
    link_case: str,
) -> None:
    """把 ``TOOL_AWAITING`` 的显式 request ref 改成指定损坏形态。

    :param transaction_runner: Host transaction runner。
    :param wait_id: wait id。
    :param link_case: missing/wrong_shape/missing_row/wrong_type/sequence_mismatch。
    :returns: ``None``。
    :raises ValueError: link_case 不受支持时抛出。
    """

    def _operation(transaction: HostTransaction) -> None:
        """更新 awaiting canonical payload。

        :param transaction: Host transaction。
        :returns: ``None``。
        :raises ValueError: link_case 不受支持时抛出。
        """

        wait_record = read_wait_record_by_id(transaction, wait_id)
        assert wait_record is not None
        awaiting = EventLogStore().read_event_by_id(
            transaction, wait_record.created_event_id
        )
        assert awaiting is not None
        payload = json.loads(awaiting.payload_json)
        assert isinstance(payload, dict)
        current_ref = payload.get("tool_call_requested_event_ref")
        assert isinstance(current_ref, dict)
        current_event_id = current_ref.get("event_id")
        current_sequence = current_ref.get("event_sequence")
        assert isinstance(current_event_id, str)
        assert isinstance(current_sequence, int)
        if link_case == "missing":
            payload.pop("tool_call_requested_event_ref")
        elif link_case == "wrong_shape":
            payload["tool_call_requested_event_ref"] = {
                "event_id": current_event_id
            }
        elif link_case == "missing_row":
            payload["tool_call_requested_event_ref"] = {
                "event_id": "event-request-missing",
                "event_sequence": 999,
            }
        elif link_case == "wrong_type":
            payload["tool_call_requested_event_ref"] = {
                "event_id": awaiting.event_id,
                "event_sequence": awaiting.event_sequence,
            }
        elif link_case == "sequence_mismatch":
            payload["tool_call_requested_event_ref"] = {
                "event_id": current_event_id,
                "event_sequence": current_sequence + 100,
            }
        else:
            raise ValueError("unsupported link_case")
        transaction.execute(
            f"UPDATE {TABLE_EVENT_LOG} SET payload_json = ? WHERE event_id = ?",
            (canonical_json_dumps(payload), awaiting.event_id),
        )

    transaction_runner.run_write(_operation)


def _rewrite_wait_execution_id(
    transaction_runner: HostTransactionRunner,
    *,
    wait_id: str,
    execution_id: str,
) -> None:
    """把目标 WaitRecord execution 改为另一条 FK-valid Attempt execution。

    :param transaction_runner: Host transaction runner。
    :param wait_id: 目标 wait id。
    :param execution_id: 辅助 Attempt 的 execution id。
    :returns: ``None``。
    :raises AssertionError: 目标 wait row 不唯一时抛出。
    """

    def _operation(transaction: HostTransaction) -> None:
        """执行 WaitRecord execution 腐化。

        :param transaction: 当前 Host transaction。
        :returns: ``None``。
        :raises AssertionError: 目标 wait row 不唯一时抛出。
        """

        result = transaction.execute(
            f"UPDATE {TABLE_HOST_WAIT_RECORDS} SET execution_id = ? WHERE wait_id = ?",
            (execution_id, wait_id),
        )
        assert result.rowcount == 1

    transaction_runner.run_write(_operation)


def _set_wait_deadline_text(
    transaction_runner: HostTransactionRunner, wait_id: str, deadline_text: str
) -> None:
    """更新测试 wait record deadline 原始文本。

    :param transaction_runner: Host transaction runner。
    :param wait_id: wait id。
    :param deadline_text: deadline 原始文本。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        """执行 deadline 文本更新。

        :param transaction: 当前 Host transaction。
        :returns: ``None``。
        """

        transaction.execute(
            f"UPDATE {TABLE_HOST_WAIT_RECORDS} SET deadline_at = ? WHERE wait_id = ?",
            (deadline_text, wait_id),
        )

    transaction_runner.run_write(_operation)


def _seed_waiting_run(
    host: HostCommandHandle,
    *,
    tooling_options: HostToolingOptions | None = None,
    budgeted_hard: bool = False,
) -> _SeededWaitingRun:
    """创建已进入 WAITING/SUSPENDED 的 Run。

    :param host: Host command handle。
    :param tooling_options: admission 时的 construction-time 工具真源。
    :param budgeted_hard: source Attempt是否携带hard continuation budget fact。
    :returns: seeded waiting run。
    :raises Exception: durable seed或budget contract失败时透传。
    """

    transaction_runner = host._transaction_runner()
    session_id = ensure_session(
        transaction_runner,
        EnsureSessionRequest(scope="workspace", slot_key="resolve", metadata=()),
    ).snapshot.session_id
    base = _SeededWaitingRun(
        session_id=session_id,
        run_id="run-resolve",
        attempt_id="attempt-resolve",
        execution_id="execution-resolve",
        dispatch_record_id="dispatch-resolve",
        wait_id="wait-pending",
    )
    _seed_active_run(
        transaction_runner,
        base,
        tooling_options=tooling_options,
        budgeted_hard=budgeted_hard,
    )
    candidate = _awaiting_candidate(base)
    result = DefaultHostToolAwaitingAcceptPort(
        transaction_runner=transaction_runner
    ).accept_tool_awaiting(candidate)
    assert isinstance(result, ToolAwaitingAcceptedAck)
    return _SeededWaitingRun(
        session_id=base.session_id,
        run_id=base.run_id,
        attempt_id=base.attempt_id,
        execution_id=base.execution_id,
        dispatch_record_id=base.dispatch_record_id,
        wait_id=candidate.wait_id,
    )


def _seed_auxiliary_starting_attempt(
    transaction_runner: HostTransactionRunner,
) -> str:
    """在独立 Run 中创建供 FK-valid mismatch 使用的辅助 Attempt。

    :param transaction_runner: Host transaction runner。
    :returns: 辅助 Attempt 的 execution id。
    :raises AssertionError: 辅助 Run/Attempt 未创建成功时抛出。
    """

    session_id = ensure_session(
        transaction_runner,
        EnsureSessionRequest(
            scope="workspace",
            slot_key="resolve-auxiliary",
            metadata=(),
        ),
    ).snapshot.session_id
    execution_id = "execution-resolve-auxiliary"

    def _operation(transaction: HostTransaction) -> None:
        """创建辅助 Run、Attempt 与 dispatch record。

        :param transaction: 当前 Host transaction。
        :returns: ``None``。
        :raises AssertionError: durable transition 未成功时抛出。
        """

        input_event = EventLogStore().append_event(
            transaction,
            EventLogAppendRequest(
                event_id="event-input-resolve-auxiliary",
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id="run-resolve-auxiliary",
                attempt_id=None,
                execution_id=None,
                event_type="USER_INPUT_ACCEPTED",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id="client-resolve-auxiliary",
                idempotency_key="idem-resolve-auxiliary-input",
                policy_decision=None,
                reason=None,
                payload_json={"display_text": "auxiliary"},
                payload_ref=None,
                payload_digest=None,
            ),
        ).row
        result = create_running_run_with_starting_attempt_in_transaction(
            transaction,
            EventLogStore(),
            CreateRunningRunInput(
                session_id=session_id,
                run_id="run-resolve-auxiliary",
                client_request_id="client-resolve-auxiliary",
                input_event_id=input_event.event_id,
                input_event_sequence=input_event.event_sequence,
                run_accepted_event_id="event-run-accepted-resolve-auxiliary",
                run_started_event_id="event-run-started-resolve-auxiliary",
                attempt_started_event_id="event-attempt-started-resolve-auxiliary",
                attempt_id="attempt-resolve-auxiliary",
                execution_id=execution_id,
                dispatch_record_id="dispatch-resolve-auxiliary",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                idempotency_key="idem-resolve-auxiliary",
                execution_target="target-resolve-auxiliary",
                queue_policy=RunQueuePolicy.QUEUE,
                start_reason=RunStartReason.INITIAL,
                worker_kind=WorkerKind.LOCAL,
                owner_host_instance_id=None,
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )
        assert result.status is StateMutationStatus.UPDATED

    transaction_runner.run_write(_operation)
    return execution_id


def _seed_active_run(
    transaction_runner: HostTransactionRunner,
    seeded: _SeededWaitingRun,
    *,
    tooling_options: HostToolingOptions | None = None,
    budgeted_hard: bool = False,
) -> None:
    """创建已 worker accepted 的 active Run。

    :param transaction_runner: Host transaction runner。
    :param seeded: seeded run 引用。
    :param tooling_options: admission 时的 construction-time 工具真源。
    :param budgeted_hard: 是否记录hard continuation source fact。
    :returns: ``None``。
    :raises Exception: durable seed或budget contract失败时透传。
    """

    def _operation(transaction: HostTransaction) -> None:
        """写入 active Run 所需 durable rows。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        register_current_instance(
            transaction,
            HostInstanceIdentity(
                host_instance_id="host-resolve-test",
                pid=1,
                process_start_token="test-process",
                boot_id=None,
            ),
        )
        execution_config = _execution_config()
        input_event = EventLogStore().append_event(
            transaction,
            EventLogAppendRequest(
                event_id="event-input-resolve",
                event_class=EventClass.CANONICAL_FACT,
                session_id=seeded.session_id,
                run_id=seeded.run_id,
                attempt_id=None,
                execution_id=None,
                event_type="USER_INPUT_ACCEPTED",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id="client-resolve",
                idempotency_key="idem-resolve-input",
                policy_decision=None,
                reason=None,
                payload_json={
                    "display_text": "hello",
                    "operation_kind": "test",
                    "effective_execution_config": execution_config,
                    "effective_tool_set": effective_tool_facts_json(
                        frozenset(),
                        tooling_options=tooling_options,
                    ),
                },
                payload_ref=None,
                payload_digest=None,
            ),
        ).row
        accepted = create_accepted_run_in_transaction(
            transaction,
            EventLogStore(),
            CreateAcceptedRunInput(
                session_id=seeded.session_id,
                run_id=seeded.run_id,
                client_request_id="client-resolve",
                input_event_id=input_event.event_id,
                input_event_sequence=input_event.event_sequence,
                run_accepted_event_id="event-run-accepted-resolve",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                idempotency_key="idem-resolve",
                execution_target="target-resolve",
                queue_policy=RunQueuePolicy.QUEUE,
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )
        assert accepted.run is not None
        candidate = prepare_runner_call_candidate_in_transaction(
            transaction,
            EventLogStore(),
            run=accepted.run,
            current_input_event=input_event,
            continuity=SessionContinuityView(messages=(), source_refs=()),
            policy_snapshot=_policy_snapshot(),
            tool_schemas=(),
            disable_tools=True,
            tool_execution_mode=ToolExecutionMode.NO_TOOL_DISABLED,
            memory_projection_policy=default_memory_projection_policy(),
        )
        start_input = StartGovernedRunInput(
            run_id=seeded.run_id,
            expected_status=RunStatus.ACCEPTED,
            run_started_event_id="event-run-started-resolve",
            attempt_started_event_id="event-attempt-started-resolve",
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
        estimator_digest = sha256_digest_json(
            {"estimate": "wait-hard-source"}
        )
        policy_digest = sha256_digest_json(
            {"context_policy": "wait-hard-source"}
        )
        sizing_snapshot = (
            complete_runner_call_sizing_snapshot(
                sizing_stage=ContextSizingStage.CONTINUATION,
                estimator_id=CONTEXT_ESTIMATOR_CONTRACT.estimator_id,
                estimator_version=(
                    CONTEXT_ESTIMATOR_CONTRACT.estimator_version
                ),
                estimator_digest=estimator_digest,
                conservative_input_tokens=950,
                context_window_size=1_000,
                provider=candidate.policy_snapshot.runner_spec.provider,
                model=candidate.policy_snapshot.runner_spec.model,
                request_semantics_digest=candidate.request_semantics_digest,
                input_snapshot_digest=candidate.input_snapshot_digest,
                policy_ref="context-policy:wait-hard-source",
                policy_snapshot_digest=policy_digest,
            )
            if budgeted_hard
            else unavailable_runner_call_sizing_snapshot(
                RunnerCallSizingUnavailableReason.CONTEXT_POLICY_UNAVAILABLE,
                sizing_stage=ContextSizingStage.ORDINARY,
            )
        )
        manifest_event = record_prepared_runner_call_candidate_in_transaction(
            transaction,
            EventLogStore(),
            PayloadStore(),
            run=accepted.run,
            attempt_id=start_input.attempt_id,
            execution_id=start_input.execution_id,
            occurred_at=start_input.occurred_at,
            candidate=candidate,
            sizing_snapshot=sizing_snapshot,
        )
        if budgeted_hard:
            append_context_budget_evaluated_in_transaction(
                transaction,
                EventLogStore(),
                session_id=seeded.session_id,
                run_id=seeded.run_id,
                attempt_id=seeded.attempt_id,
                execution_id=seeded.execution_id,
                occurred_at=_NOW,
                result=(
                    build_conservative_context_sizing_result_from_atoms(
                        stage=ContextSizingStage.CONTINUATION,
                        candidate_input_cursor=manifest_event.event_sequence,
                        candidate_input_projection_ref=(
                            candidate.candidate_input_projection_ref
                        ),
                        candidate_input_digest=(
                            candidate.input_snapshot_digest
                        ),
                        estimator_contract=ContextEstimatorContract(
                            estimator_id=(
                                CONTEXT_ESTIMATOR_CONTRACT.estimator_id
                            ),
                            estimator_version=(
                                CONTEXT_ESTIMATOR_CONTRACT.estimator_version
                            ),
                        ),
                        estimator_digest=estimator_digest,
                        conservative_input_tokens=950,
                        context_window_size=1_000,
                        soft_threshold_tokens=1,
                        hard_threshold_tokens=2,
                        policy_ref="context-policy:wait-hard-source",
                        policy_snapshot_digest=policy_digest,
                    )
                ),
            )
        started = start_governed_run_with_starting_attempt_in_transaction(
            transaction,
            EventLogStore(),
            start_input,
        )
        assert started.status is StateMutationStatus.UPDATED
        mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id=seeded.attempt_id,
            owner_host_instance_id="host-resolve-test",
            lane_name="llm",
            waiting_for_lane_at="2026-05-16T01:02:03.000000Z",
        )
        mark_dispatching_after_lane_row(
            transaction,
            attempt_id=seeded.attempt_id,
            owner_host_instance_id="host-resolve-test",
            lane_name="llm",
            lane_claim_id="claim-resolve",
            lane_owner_id="owner-resolve",
            lane_acquired_at="2026-05-16T01:02:03.000000Z",
            dispatching_at="2026-05-16T01:02:03.000000Z",
        )
        accept_worker_running_in_transaction(
            transaction,
            EventLogStore(),
            AcceptWorkerRunningInput(
                run_id=seeded.run_id,
                attempt_id=seeded.attempt_id,
                attempt_running_event_id="event-attempt-running-resolve",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                worker_accept_reason="accepted",
                local_worker_id="local-worker-resolve",
            ),
        )

    transaction_runner.run_write(_operation)


def _awaiting_candidate(seeded: _SeededWaitingRun) -> ToolAwaitingAcceptCandidate:
    """构造 awaiting accept candidate。

    :param seeded: seeded run。
    :returns: awaiting accept candidate。
    """

    digest = sha256_digest_json({"awaiting": seeded.run_id})
    binding = WaitAdapterBinding(
        tool_name="long_tool",
        await_kind=ToolAwaitKind.EXTERNAL_JOB,
        adapter_key=WaitAdapterKey("poll:long-tool"),
        resume_policy=WaitResumePolicy.POLL,
        external_job_ref_source=WaitExternalJobRefSource.RESUME_TOKEN,
    )
    await_spec = ToolAwaitSpec(
        await_kind=ToolAwaitKind.EXTERNAL_JOB,
        deadline=None,
        resume_token="external-job-1",
    )
    return ToolAwaitingAcceptCandidate(
        session_id=seeded.session_id,
        run_id=seeded.run_id,
        attempt_id=seeded.attempt_id,
        execution_id=seeded.execution_id,
        iteration_id="iteration-resolve",
        tool_call_id="tool-call-resolve",
        tool_name="long_tool",
        tool_schema_digest=sha256_digest_json({"schema": "long_tool"}),
        tool_identity_digest=sha256_digest_json({"identity": "long_tool"}),
        normalized_arguments_digest=sha256_digest_json(
            {"arguments": {"name": "long_tool"}}
        ),
        accepted_arguments={"name": "long_tool"},
        await_spec=await_spec,
        snapshot_ref=None,
        binding=binding,
        external_job_ref=binding.external_job_ref(await_spec),
        wait_id=f"wait-{digest.removeprefix('sha256:')}",
        accept_idempotency_key=f"tool-await-{digest.removeprefix('sha256:')}",
        semantic_input_digest=digest,
    )


def _read_resolution_state(
    transaction_runner: HostTransactionRunner,
    wait_id: str,
    attempt_id: str | None,
) -> tuple[WaitRecordRow | None, DispatchRecordRow | None, tuple[EventLogRow, ...]]:
    """读取 resolve 后 wait、dispatch 与事件。

    :param transaction_runner: Host transaction runner。
    :param wait_id: wait record id。
    :param attempt_id: 当前 Attempt id。
    :returns: wait record、dispatch record 与全部事件。
    """

    def _operation(
        transaction: HostTransaction,
    ) -> tuple[WaitRecordRow | None, DispatchRecordRow | None, tuple[EventLogRow, ...]]:
        """执行读取。

        :param transaction: Host transaction。
        :returns: wait record、dispatch record 与全部事件。
        """

        dispatch_record = (
            read_dispatch_record_by_attempt_id(transaction, attempt_id)
            if attempt_id is not None
            else None
        )
        return (
            read_wait_record_by_id(transaction, wait_id),
            dispatch_record,
            EventLogStore().read_events_after(transaction, 0, limit=100),
        )

    return transaction_runner.run_read(_operation)


def _read_resolution_tables(
    transaction_runner: HostTransactionRunner,
) -> _ResolutionTables:
    """读取 wait-resolution owner 涉及的五张 durable 全表。

    :param transaction_runner: Host transaction runner。
    :returns: 按稳定主键排序的 durable 全表快照。
    """

    return transaction_runner.run_read(_read_resolution_tables_in_transaction)


def _read_resolution_tables_in_transaction(
    transaction: HostTransaction,
) -> _ResolutionTables:
    """在当前 transaction 内读取 wait-resolution durable 全表。

    :param transaction: 当前 Host transaction。
    :returns: 按稳定主键排序的 durable 全表快照。
    """

    return _ResolutionTables(
        events=transaction.fetchall(
            f"SELECT * FROM {TABLE_EVENT_LOG} ORDER BY event_sequence"
        ),
        runs=transaction.fetchall(f"SELECT * FROM {TABLE_HOST_RUNS} ORDER BY run_id"),
        attempts=transaction.fetchall(
            f"SELECT * FROM {TABLE_HOST_ATTEMPTS} ORDER BY attempt_id"
        ),
        wait_records=transaction.fetchall(
            f"SELECT * FROM {TABLE_HOST_WAIT_RECORDS} ORDER BY wait_id"
        ),
        dispatch_records=transaction.fetchall(
            "SELECT * "
            f"FROM {TABLE_HOST_ATTEMPT_DISPATCH_RECORDS} "
            "ORDER BY dispatch_record_id"
        ),
    )


def _read_wait(
    transaction_runner: HostTransactionRunner, wait_id: str
) -> WaitRecordRow:
    """读取 wait record 并断言存在。

    :param transaction_runner: Host transaction runner。
    :param wait_id: wait record id。
    :returns: wait record row。
    """

    row = transaction_runner.run_read(
        lambda transaction: read_wait_record_by_id(transaction, wait_id)
    )
    assert row is not None
    return row


def _build_resume_request(
    transaction_runner: HostTransactionRunner,
    session_id: str,
    attempt_id: str | None,
) -> AgentRunRequest:
    """把 resume dispatch 推进到 dispatching 并构造 Engine request。

    :param transaction_runner: Host transaction runner。
    :param session_id: Session id。
    :param attempt_id: resume Attempt id。
    :returns: AgentRunRequest；测试只检查 messages。
    """

    assert attempt_id is not None

    def _mark_dispatching(transaction: HostTransaction) -> DispatchRecordRow:
        """标记 resume dispatch 为 dispatching 并返回 row。

        :param transaction: Host transaction。
        :returns: dispatch record row。
        """

        mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id=attempt_id,
            owner_host_instance_id="host-resolve-test",
            lane_name="llm",
            waiting_for_lane_at="2026-05-16T01:05:07.000000Z",
        )
        mark_dispatching_after_lane_row(
            transaction,
            attempt_id=attempt_id,
            owner_host_instance_id="host-resolve-test",
            lane_name="llm",
            lane_claim_id="claim-resume",
            lane_owner_id="owner-resume",
            lane_acquired_at="2026-05-16T01:05:07.000000Z",
            dispatching_at="2026-05-16T01:05:07.000000Z",
        )
        dispatch = read_dispatch_record_by_attempt_id(transaction, attempt_id)
        assert dispatch is not None
        return dispatch

    dispatch = transaction_runner.run_write(_mark_dispatching)
    builder = create_no_tool_run_input_builder(
        transaction_runner=transaction_runner,
        policy_snapshot=_policy_snapshot(),
    )
    return builder.build(
        AttemptDispatchSnapshot(
            session_id=session_id,
            run_id=dispatch.run_id,
            attempt_id=dispatch.attempt_id,
            execution_id=dispatch.execution_id,
            dispatch_record_id=dispatch.dispatch_record_id,
            execution_target=dispatch.execution_target,
            policy_snapshot_ref=_policy_snapshot().policy_snapshot_ref,
            cancellation_token=_token(),
        )
    )


def _token() -> CancellationToken:
    """构造测试用 cancellation token。

    :returns: 未取消 token。
    """

    return _OpenCancellationToken()


def _policy_snapshot() -> PolicySnapshot:
    """构造测试用 policy snapshot。

    :returns: PolicySnapshot。
    """

    execution = effective_execution_snapshot_from_json(_execution_config())
    return PolicySnapshot(
        runner_spec=execution.runner_spec,
        runner_options=execution.runner_options,
        agent_policy=execution.agent_policy,
        policy_snapshot_ref=execution.policy_snapshot_ref,
    )


def _execution_config() -> JsonValue:
    """构造 waiting source input 使用的 exact execution config。

    :returns: 可由共享 strict parser 重建的 execution config JSON。
    :raises TypeError: typed execution contract 非法时抛出。
    :raises ValueError: typed execution contract 字段非法时抛出。
    """

    return effective_execution_config_json(
        runner_spec=RunnerSpec(
            provider="test",
            model="test-model",
            endpoint="https://example.invalid/v1",
            api_key_ref="test-key",
            headers={},
            client_correlation_policy=ClientCorrelationPolicy.DISABLED,
            supports_tool_calling=False,
            supports_streaming=False,
            supports_stream_usage=False,
            structured_output_capability=StructuredOutputCapability.NONE,
            default_timeout_seconds=30.0,
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
            fallback_prompt="test fallback prompt",
            continuation_prompt="test continuation prompt",
        ),
        runner_spec_source="test",
        runner_options_source="test",
        agent_policy_source="test",
    )


def _ordinary_run_baseline() -> OrdinaryRunExecutionBaseline:
    """构造 resolve-wait 测试的显式 execution baseline。

    :returns: ordinary Run baseline。
    :raises TypeError: typed execution contract 非法时抛出。
    :raises ValueError: typed execution contract 字段非法时抛出。
    """

    policy = _policy_snapshot()
    return OrdinaryRunExecutionBaseline(
        runner_spec=policy.runner_spec,
        runner_options=policy.runner_options,
        agent_policy=policy.agent_policy,
    )


def _create_execution_handle(options: HostCommandHandleOptions) -> HostCommandHandle:
    """创建 resolve-wait 测试使用的 execution command handle。

    :param options: durable command options。
    :returns: 显式装配 execution admission 的 command handle。
    :raises HostApiError: durable store 或 admission 装配失败时抛出。
    """

    return create_execution_command_handle(
        options,
        ordinary_run_baseline=_ordinary_run_baseline(),
        memory_projection_policy=default_memory_projection_policy(),
    )


def _events(transaction_runner: HostTransactionRunner) -> tuple[EventLogRow, ...]:
    """读取全部 EventLog rows。

    :param transaction_runner: Host transaction runner。
    :returns: EventLog rows。
    """

    return transaction_runner.run_read(
        lambda transaction: EventLogStore().read_events_after(
            transaction, 0, limit=100
        )
    )


def _events_by_type(
    events: tuple[EventLogRow, ...], event_type: str
) -> tuple[EventLogRow, ...]:
    """按 event type 过滤 EventLog rows。

    :param events: EventLog rows。
    :param event_type: 目标 event type。
    :returns: 匹配事件元组。
    """

    return tuple(event for event in events if event.event_type == event_type)


def _single_event(events: tuple[EventLogRow, ...], event_type: str) -> EventLogRow:
    """读取唯一匹配类型的 EventLog row。

    :param events: EventLog rows。
    :param event_type: 目标 event type。
    :returns: 唯一匹配的 EventLog row。
    :raises AssertionError: 匹配数量不是 1 时由断言抛出。
    """

    matched = _events_by_type(events, event_type)
    assert len(matched) == 1
    return matched[0]
