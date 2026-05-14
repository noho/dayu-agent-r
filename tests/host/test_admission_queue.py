"""Host Phase 3 admission 与 durable queue promotion 测试。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.host.admission import (
    AdmissionClock,
    AdmissionIdFactory,
    AdmissionWakeupPort,
    HostAdmissionService,
    PendingDispatchRecord,
    SubmitFollowupQueueAdmissionInput,
    create_host_admission_service,
)
from dayu.host.api import (
    AttemptStatus,
    AuthorizationClaim,
    CloseSessionRequest,
    EnsureSessionRequest,
    FollowupBehavior,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostInput,
    HostMetadataEntry,
    OperationContext,
    RunStatus,
    StartRunRequest,
    SubmitFollowupRequest,
)
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import EventLogStore
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.run_transition import (
    TerminalCloseoutInput,
    terminal_closeout_in_transaction,
)
from dayu.host.durable.session_lifecycle import close_session, ensure_session
from dayu.host.durable.state import (
    DispatchRecordStatus,
    RunRow,
    read_run_by_id,
)
from dayu.host.durable.transaction import HostRow, HostTransaction, HostTransactionRunner

_NOW = datetime(2026, 5, 14, 9, 30, 0, tzinfo=UTC)
_CALLER_DIGEST = sha256_digest_json({"caller": "admission-test"})


@dataclass(frozen=True, slots=True)
class _FixedClock(AdmissionClock):
    """测试用固定 UTC 时钟。"""

    value: datetime = _NOW

    def now(self) -> datetime:
        """返回固定时间。

        :returns: 固定 timezone-aware datetime。
        """

        return self.value


@dataclass(slots=True)
class _SequentialIdFactory(AdmissionIdFactory):
    """测试用确定性 id 工厂。"""

    label: str
    counters: dict[str, int] = field(default_factory=dict)

    def new_id(self, prefix: str) -> str:
        """生成带测试标签的递增 id。

        :param prefix: id 前缀。
        :returns: ``prefix-label-index`` 文本 id。
        """

        next_value = self.counters.get(prefix, 0) + 1
        self.counters[prefix] = next_value
        return f"{prefix}-{self.label}-{next_value}"


@dataclass(slots=True)
class _WakeupSpy(AdmissionWakeupPort):
    """测试用 wakeup spy。"""

    dispatches: list[PendingDispatchRecord] = field(default_factory=list)
    promotions: list[str] = field(default_factory=list)

    def wake_dispatch(self, record: PendingDispatchRecord) -> None:
        """记录 dispatch wakeup。

        :param record: pending dispatch 摘要。
        :returns: ``None``。
        """

        self.dispatches.append(record)

    def wake_queue_promotion(self, session_id: str) -> None:
        """记录 promotion wakeup。

        :param session_id: 目标 Session id。
        :returns: ``None``。
        """

        self.promotions.append(session_id)


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试用 Host durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    """

    return _options_for_path(tmp_path / "durable.sqlite3", tmp_path / "artifacts")


def _options_for_path(
    db_path: Path, artifact_root: Path
) -> HostDurableStoreOptions:
    """按显式路径构造 Host durable store options。

    :param db_path: SQLite db 路径。
    :param artifact_root: artifact 根目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=db_path,
        payload_policy=PayloadStoragePolicy(artifact_root=artifact_root),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=0.5,
            write_busy_retry_count=8,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.02,
        ),
    )


def test_start_run_on_open_session_creates_running_attempt_and_dispatch(
    tmp_path: Path,
) -> None:
    """start_run 在无 active Run 时创建 running Run 与 pending dispatch。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        spy = _WakeupSpy()
        service = _service(store.transaction_runner, spy=spy)

        result = service.start_run(
            _start_request(
                session_id=session_id,
                client_request_id="start-1",
                execution_target="target-initial",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )

        assert result.run.status == RunStatus.RUNNING
        assert result.run.execution_target == "target-initial"
        assert result.attempt is not None
        assert result.attempt.status == AttemptStatus.STARTING
        assert result.dispatch_record is not None
        assert result.dispatch_record.status == DispatchRecordStatus.PENDING
        assert len(spy.dispatches) == 1
        assert spy.dispatches[0].run_id == result.run.run_id


def test_followup_queue_with_active_creates_queued_run_with_supplied_target(
    tmp_path: Path,
) -> None:
    """active Run 存在时 follow-up queue 只创建 queued Run 并保存显式 target。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        spy = _WakeupSpy()
        service = _service(store.transaction_runner, spy=spy)
        active = service.start_run(
            _start_request(
                session_id=session_id,
                client_request_id="start-active",
                execution_target="active-target",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )

        queued = service.submit_followup_queue(
            SubmitFollowupQueueAdmissionInput(
                request=_followup_request(
                    session_id=session_id,
                    client_request_id="follow-queued",
                    display_text="queued input",
                ),
                resolved_execution_target="queued-target",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )

        assert active.run.execution_target == "active-target"
        assert queued.run.status == RunStatus.QUEUED
        assert queued.run.execution_target == "queued-target"
        assert queued.attempt is None
        assert queued.dispatch_record is None
        assert _count_rows(store.transaction_runner, "host_attempts") == 1
        assert len(spy.dispatches) == 1


def test_followup_queue_without_active_creates_running_run_with_four_facts(
    tmp_path: Path,
) -> None:
    """无 active Run 时 follow-up queue 直接启动并写四个 canonical facts。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        service = _service(store.transaction_runner)

        result = service.submit_followup_queue(
            SubmitFollowupQueueAdmissionInput(
                request=_followup_request(
                    session_id=session_id,
                    client_request_id="follow-direct",
                    display_text="direct follow-up",
                ),
                resolved_execution_target="follow-target",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )

        assert result.run.status == RunStatus.RUNNING
        assert result.run.execution_target == "follow-target"
        assert result.attempt is not None
        assert result.dispatch_record is not None
        assert _event_types_for_run(store.transaction_runner, result.run.run_id) == (
            "USER_INPUT_ACCEPTED",
            "RUN_ACCEPTED",
            "RUN_STARTED",
            "ATTEMPT_STARTED",
        )


def test_closed_session_rejects_start_and_followup_without_event_side_effects(
    tmp_path: Path,
) -> None:
    """closed Session 拒绝新 admission，且不追加 EventLog 或幂等记录。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        close_session(
            store.transaction_runner,
            session_id,
            _close_request("close-1"),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        before = _event_count(store.transaction_runner)
        before_idempotency = _count_rows(store.transaction_runner, "idempotency_records")
        service = _service(store.transaction_runner)

        with pytest.raises(HostApiError) as start_error:
            service.start_run(
                _start_request(session_id=session_id, client_request_id="start-closed"),
                caller_semantic_digest=_CALLER_DIGEST,
            )
        with pytest.raises(HostApiError) as followup_error:
            service.submit_followup_queue(
                SubmitFollowupQueueAdmissionInput(
                    request=_followup_request(
                        session_id=session_id,
                        client_request_id="follow-closed",
                    ),
                    resolved_execution_target="target-closed",
                ),
                caller_semantic_digest=_CALLER_DIGEST,
            )

        assert start_error.value.code == HostApiErrorCode.INVALID_STATE
        assert followup_error.value.code == HostApiErrorCode.INVALID_STATE
        assert _event_count(store.transaction_runner) == before
        assert _count_rows(store.transaction_runner, "idempotency_records") == (
            before_idempotency
        )


def test_duplicate_idempotency_returns_same_run_without_extra_events(
    tmp_path: Path,
) -> None:
    """queued 与 direct running 两条 admission 路径重复幂等不追加事件。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        service = _service(store.transaction_runner)
        active_session_id = _ensure_session_id(store.transaction_runner, slot_key="active")
        service.start_run(
            _start_request(
                session_id=active_session_id,
                client_request_id="start-active",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        queued_input = SubmitFollowupQueueAdmissionInput(
            request=_followup_request(
                session_id=active_session_id,
                client_request_id="follow-repeat",
                display_text="repeat queued",
            ),
            resolved_execution_target="queued-target",
        )
        queued_first = service.submit_followup_queue(
            queued_input,
            caller_semantic_digest=_CALLER_DIGEST,
        )
        before_queued_retry = _event_count(store.transaction_runner)
        queued_second = service.submit_followup_queue(
            queued_input,
            caller_semantic_digest=_CALLER_DIGEST,
        )
        assert _event_count(store.transaction_runner) == before_queued_retry

        direct_session_id = _ensure_session_id(store.transaction_runner, slot_key="direct")
        direct_input = SubmitFollowupQueueAdmissionInput(
            request=_followup_request(
                session_id=direct_session_id,
                client_request_id="follow-direct-repeat",
                display_text="repeat direct",
            ),
            resolved_execution_target="direct-target",
        )
        direct_first = service.submit_followup_queue(
            direct_input,
            caller_semantic_digest=_CALLER_DIGEST,
        )
        before_direct_retry = _event_count(store.transaction_runner)
        direct_second = service.submit_followup_queue(
            direct_input,
            caller_semantic_digest=_CALLER_DIGEST,
        )

        assert queued_first.run.run_id == queued_second.run.run_id
        assert queued_second.idempotent_replay is True
        assert _event_count(store.transaction_runner) == before_direct_retry
        assert before_direct_retry > before_queued_retry
        assert direct_first.run.run_id == direct_second.run.run_id
        assert direct_second.idempotent_replay is True


def test_followup_idempotency_excludes_later_resolved_execution_target(
    tmp_path: Path,
) -> None:
    """follow-up 同 key 重试不因新 target 改写首次持久化 target。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        service = _service(store.transaction_runner)
        service.start_run(
            _start_request(session_id=session_id, client_request_id="start-active"),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        request = _followup_request(
            session_id=session_id,
            client_request_id="follow-target-retry",
            display_text="same semantic input",
        )

        first = service.submit_followup_queue(
            SubmitFollowupQueueAdmissionInput(
                request=request,
                resolved_execution_target="first-target",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        second = service.submit_followup_queue(
            SubmitFollowupQueueAdmissionInput(
                request=request,
                resolved_execution_target="second-target",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        latest = _read_run(store.transaction_runner, first.run.run_id)

        assert second.run.run_id == first.run.run_id
        assert second.run.execution_target == "first-target"
        assert latest.execution_target == "first-target"


def test_same_idempotency_key_with_changed_input_digest_conflicts(
    tmp_path: Path,
) -> None:
    """同 key 改变输入 digest 返回 idempotency_conflict 且不追加事件。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        service = _service(store.transaction_runner)
        service.start_run(
            _start_request(session_id=session_id, client_request_id="start-active"),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        service.submit_followup_queue(
            SubmitFollowupQueueAdmissionInput(
                request=_followup_request(
                    session_id=session_id,
                    client_request_id="follow-conflict",
                    display_text="original",
                ),
                resolved_execution_target="target",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        before = _event_count(store.transaction_runner)

        with pytest.raises(HostApiError) as exc_info:
            service.submit_followup_queue(
                SubmitFollowupQueueAdmissionInput(
                    request=_followup_request(
                        session_id=session_id,
                        client_request_id="follow-conflict",
                        display_text="changed",
                    ),
                    resolved_execution_target="target",
                ),
                caller_semantic_digest=_CALLER_DIGEST,
            )

        assert exc_info.value.code == HostApiErrorCode.IDEMPOTENCY_CONFLICT
        assert _event_count(store.transaction_runner) == before


def test_reject_and_attach_active_have_expected_event_and_idempotency_effects(
    tmp_path: Path,
) -> None:
    """reject active 不写 side effect；attach active 只写 null event 幂等记录。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        service = _service(store.transaction_runner)
        active = service.start_run(
            _start_request(session_id=session_id, client_request_id="start-active"),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        before_events = _event_count(store.transaction_runner)
        before_idempotency = _count_rows(store.transaction_runner, "idempotency_records")

        with pytest.raises(HostApiError) as reject_error:
            service.start_run(
                _start_request(
                    session_id=session_id,
                    client_request_id="start-reject",
                    queue_policy="reject",
                ),
                caller_semantic_digest=_CALLER_DIGEST,
            )

        attached = service.start_run(
            _start_request(
                session_id=session_id,
                client_request_id="start-attach",
                queue_policy="attach_active",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        record = _idempotency_record(
            store.transaction_runner,
            scope_kind="start_run",
            scope_id=session_id,
            key="start-attach",
        )

        assert reject_error.value.code == HostApiErrorCode.CONFLICT
        assert _event_count(store.transaction_runner) == before_events
        assert attached.run.run_id == active.run.run_id
        assert attached.attached_active is True
        assert _count_rows(store.transaction_runner, "idempotency_records") == (
            before_idempotency + 1
        )
        assert _text(record, "created_event_id") is None
        assert record.get("created_event_sequence") is None


def test_unknown_queue_policy_raises_value_error_without_transaction(
    tmp_path: Path,
) -> None:
    """未知 queue_policy 在打开事务前抛出 ValueError。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        service = _service(store.transaction_runner)
        before = _event_count(store.transaction_runner)

        with pytest.raises(ValueError):
            service.start_run(
                _start_request(
                    session_id=session_id,
                    client_request_id="start-unknown",
                    queue_policy="unknown",
                ),
                caller_semantic_digest=_CALLER_DIGEST,
            )

        assert _event_count(store.transaction_runner) == before


def test_promotion_skips_with_active_then_promotes_earliest_queued_run(
    tmp_path: Path,
) -> None:
    """promotion active skip 不报错；释放 active 后按 accepted sequence FIFO。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        spy = _WakeupSpy()
        service = _service(store.transaction_runner, spy=spy)
        active = service.start_run(
            _start_request(session_id=session_id, client_request_id="start-active"),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        first_queued = service.submit_followup_queue(
            SubmitFollowupQueueAdmissionInput(
                request=_followup_request(
                    session_id=session_id,
                    client_request_id="follow-b",
                    display_text="first queued",
                ),
                resolved_execution_target="first-target",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        second_queued = service.submit_followup_queue(
            SubmitFollowupQueueAdmissionInput(
                request=_followup_request(
                    session_id=session_id,
                    client_request_id="follow-a",
                    display_text="second queued",
                ),
                resolved_execution_target="second-target",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        skipped = service.promote_next_queued_run(session_id)

        _closeout_active(store.transaction_runner, active.run.run_id)
        promoted = service.promote_next_queued_run(session_id)

        assert skipped.skipped is True
        assert skipped.skip_reason is not None
        assert skipped.skip_reason.value == "active_run_exists"
        assert promoted.promoted_run is not None
        assert promoted.promoted_run.run_id == first_queued.run.run_id
        assert promoted.promoted_run.execution_target == "first-target"
        assert _read_run(store.transaction_runner, second_queued.run.run_id).status == (
            RunStatus.QUEUED
        )
        assert len(spy.dispatches) == 2


def test_concurrent_promotion_attempts_promote_at_most_one_run(
    tmp_path: Path,
) -> None:
    """两个进程式连接竞争 promotion 时最多一个 queued Run 进入 running。"""

    db_path = tmp_path / "durable.sqlite3"
    artifact_root = tmp_path / "artifacts"
    options = _options_for_path(db_path, artifact_root)
    session_id = ""
    with open_host_durable_store(options) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        service = _service(store.transaction_runner, label="seed")
        active = service.start_run(
            _start_request(session_id=session_id, client_request_id="start-active"),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        service.submit_followup_queue(
            SubmitFollowupQueueAdmissionInput(
                request=_followup_request(
                    session_id=session_id,
                    client_request_id="follow-one",
                ),
                resolved_execution_target="target-one",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        _closeout_active(store.transaction_runner, active.run.run_id)

    def promote(label: str) -> tuple[bool, str | None]:
        """在独立连接中执行一次 promotion。

        :param label: 测试 id 标签。
        :returns: 是否 promotion 成功与 Run id。
        """

        with open_host_durable_store(options) as thread_store:
            result = _service(thread_store.transaction_runner, label=label).promote_next_queued_run(
                session_id
            )
            return (
                result.promoted_run is not None,
                result.promoted_run.run_id if result.promoted_run is not None else None,
            )
        raise AssertionError("promotion worker did not return")

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert session_id != ""
        results = tuple(executor.map(promote, ("worker-a", "worker-b")))

    assert sum(1 for promoted, _run_id in results if promoted) == 1
    with open_host_durable_store(options) as store:
        assert _count_running_runs(store.transaction_runner, session_id) == 1


def _service(
    transaction_runner: HostTransactionRunner,
    *,
    spy: _WakeupSpy | None = None,
    label: str = "main",
) -> HostAdmissionService:
    """构造测试 admission service。

    :param transaction_runner: Host transaction runner。
    :param spy: 可选 wakeup spy。
    :param label: id factory 标签。
    :returns: HostAdmissionService。
    """

    return create_host_admission_service(
        transaction_runner,
        clock=_FixedClock(),
        id_factory=_SequentialIdFactory(label),
        wakeup_port=spy if spy is not None else _WakeupSpy(),
    )


def _context() -> HostCallContext:
    """构造标准 Host call context。

    :returns: Host call context。
    """

    return HostCallContext(
        actor="analyst",
        source="pytest",
        request_id="request-trace",
        authorization_claims=(AuthorizationClaim(name="role", value="research"),),
        operation_context=OperationContext(
            operation_name="admission_test",
            operation_kind="unit_test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="phase3",
            correlation_id="corr-admission",
        ),
    )


def _ensure_session_id(
    transaction_runner: HostTransactionRunner, *, slot_key: str = "admission"
) -> str:
    """创建测试 Session 并返回 id。

    :param transaction_runner: Host transaction runner。
    :param slot_key: slot key。
    :returns: Session id。
    """

    result = ensure_session(
        transaction_runner,
        EnsureSessionRequest(
            scope="workspace",
            slot_key=slot_key,
            metadata=(HostMetadataEntry(key="case", value="admission"),),
        ),
    )
    return result.snapshot.session_id


def _start_request(
    *,
    session_id: str,
    client_request_id: str,
    display_text: str = "start input",
    execution_target: str = "target-default",
    queue_policy: str = "queue",
) -> StartRunRequest:
    """构造 start_run 请求。

    :param session_id: Session id。
    :param client_request_id: 幂等请求 id。
    :param display_text: 输入展示文本。
    :param execution_target: 执行目标。
    :param queue_policy: queue policy。
    :returns: StartRunRequest。
    """

    return StartRunRequest(
        context=_context(),
        session_id=session_id,
        client_request_id=client_request_id,
        input=HostInput(display_text=display_text, payload_ref=None, payload_digest=None),
        execution_target=execution_target,
        queue_policy=queue_policy,
    )


def _followup_request(
    *,
    session_id: str,
    client_request_id: str,
    display_text: str = "follow-up input",
) -> SubmitFollowupRequest:
    """构造 follow-up queue 请求。

    :param session_id: Session id。
    :param client_request_id: 幂等请求 id。
    :param display_text: 输入展示文本。
    :returns: SubmitFollowupRequest。
    """

    return SubmitFollowupRequest(
        context=_context(),
        session_id=session_id,
        client_request_id=client_request_id,
        input=HostInput(display_text=display_text, payload_ref=None, payload_digest=None),
        behavior=FollowupBehavior.QUEUE,
        target_run_id=None,
    )


def _close_request(client_request_id: str) -> CloseSessionRequest:
    """构造 close session 请求。

    :param client_request_id: 幂等请求 id。
    :returns: CloseSessionRequest。
    """

    return CloseSessionRequest(
        context=_context(),
        client_request_id=client_request_id,
        reason="test_close",
    )


def _closeout_active(
    transaction_runner: HostTransactionRunner, run_id: str
) -> None:
    """使用低层 terminal helper 释放 active slot。

    :param transaction_runner: Host transaction runner。
    :param run_id: active Run id。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """执行 terminal closeout。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        run = read_run_by_id(transaction, run_id)
        assert run is not None
        assert run.current_attempt_id is not None
        terminal_closeout_in_transaction(
            transaction,
            EventLogStore(),
            TerminalCloseoutInput(
                run_id=run_id,
                attempt_id=run.current_attempt_id,
                attempt_terminal_event_id=f"event-terminal-attempt-{run_id}",
                run_terminal_event_id=f"event-terminal-run-{run_id}",
                attempt_terminal_status=AttemptStatus.SUCCEEDED,
                run_terminal_status=RunStatus.SUCCEEDED,
                occurred_at=_NOW,
                actor="analyst",
                source="pytest",
                reason="test_closeout",
                terminal_summary_ref=None,
                terminal_summary_digest=None,
            ),
        )

    transaction_runner.run_write(operation)


def _read_run(transaction_runner: HostTransactionRunner, run_id: str) -> RunRow:
    """读取 Run row。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :returns: Run row。
    """

    def operation(transaction: HostTransaction) -> RunRow:
        """读取 Run row。

        :param transaction: Host transaction。
        :returns: Run row。
        """

        run = read_run_by_id(transaction, run_id)
        assert run is not None
        return run

    return transaction_runner.run_write(operation)


def _event_types_for_run(
    transaction_runner: HostTransactionRunner, run_id: str
) -> tuple[str, ...]:
    """读取某 Run 的 EventLog event type 序列。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :returns: event type 元组。
    """

    def operation(transaction: HostTransaction) -> tuple[str, ...]:
        """读取 event type。

        :param transaction: Host transaction。
        :returns: event type 元组。
        """

        rows = transaction.fetchall(
            "SELECT event_type FROM event_log WHERE run_id = ? ORDER BY event_sequence ASC",
            (run_id,),
        )
        return tuple(_required_text(row, "event_type") for row in rows)

    return transaction_runner.run_write(operation)


def _event_count(transaction_runner: HostTransactionRunner) -> int:
    """读取 EventLog row 数。

    :param transaction_runner: Host transaction runner。
    :returns: row count。
    """

    def operation(transaction: HostTransaction) -> int:
        """读取 EventLog row 数。

        :param transaction: Host transaction。
        :returns: row count。
        """

        row = transaction.fetchone("SELECT COUNT(*) AS total FROM event_log")
        assert row is not None
        return _int(row, "total")

    return transaction_runner.run_write(operation)


def _count_rows(transaction_runner: HostTransactionRunner, table_name: str) -> int:
    """读取指定测试表的 row 数。

    :param transaction_runner: Host transaction runner。
    :param table_name: 测试内固定表名。
    :returns: row count。
    """

    def operation(transaction: HostTransaction) -> int:
        """读取 row 数。

        :param transaction: Host transaction。
        :returns: row count。
        """

        row = transaction.fetchone(f"SELECT COUNT(*) AS total FROM {table_name}")
        assert row is not None
        return _int(row, "total")

    return transaction_runner.run_write(operation)


def _count_running_runs(
    transaction_runner: HostTransactionRunner, session_id: str
) -> int:
    """读取 Session 下 running Run 数。

    :param transaction_runner: Host transaction runner。
    :param session_id: Session id。
    :returns: running Run 数。
    """

    def operation(transaction: HostTransaction) -> int:
        """读取 running Run 数。

        :param transaction: Host transaction。
        :returns: running Run 数。
        """

        row = transaction.fetchone(
            "SELECT COUNT(*) AS total FROM host_runs WHERE session_id = ? AND status = ?",
            (session_id, RunStatus.RUNNING.value),
        )
        assert row is not None
        return _int(row, "total")

    return transaction_runner.run_write(operation)


def _idempotency_record(
    transaction_runner: HostTransactionRunner,
    *,
    scope_kind: str,
    scope_id: str,
    key: str,
) -> HostRow:
    """读取幂等记录 HostRow。

    :param transaction_runner: Host transaction runner。
    :param scope_kind: 幂等 scope kind。
    :param scope_id: 幂等 scope id。
    :param key: 幂等 key。
    :returns: HostRow。
    """

    def operation(transaction: HostTransaction) -> HostRow:
        """读取幂等记录。

        :param transaction: Host transaction。
        :returns: HostRow。
        """

        row = transaction.fetchone(
            """
            SELECT created_event_id, created_event_sequence
            FROM idempotency_records
            WHERE scope_kind = ? AND scope_id = ? AND idempotency_key = ?
            """,
            (scope_kind, scope_id, key),
        )
        assert row is not None
        return row

    return transaction_runner.run_write(operation)


def _text(row: HostRow, column: str) -> str | None:
    """读取可空文本列。

    :param row: Host row。
    :param column: 列名。
    :returns: 文本或 ``None``。
    """

    value = row.get(column)
    assert value is None or isinstance(value, str)
    return value


def _required_text(row: HostRow, column: str) -> str:
    """读取必填文本列。

    :param row: Host row。
    :param column: 列名。
    :returns: 文本值。
    """

    value = row.get(column)
    assert isinstance(value, str)
    return value


def _int(row: HostRow, column: str) -> int:
    """读取整数列。

    :param row: Host row。
    :param column: 列名。
    :returns: 整数值。
    """

    value = row.get(column)
    assert isinstance(value, int)
    return value
