"""Host Phase 3 admission 与 durable queue promotion 测试。"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.runner_spec import ClientCorrelationPolicy, RunnerCallOptions, RunnerSpec
from dayu.host.queue_policy import RunQueuePolicy
from dayu.host.admission import (
    AdmissionClock,
    AdmissionIdFactory,
    AdmissionWakeupPort,
    CloseoutAttemptTerminalInput,
    HostAdmissionService,
    PendingDispatchRecord,
    SubmitFollowupQueueAdmissionInput,
    create_host_admission_service,
)
from dayu.host import admission as admission_module
from dayu.host.api import (
    AttemptStatus,
    AuthorizationClaim,
    CancelMode,
    CancelRunRequest,
    CancelSessionRunsRequest,
    CloseSessionRequest,
    EnsureSessionRequest,
    FollowupBehavior,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostInput,
    HostMetadataEntry,
    OperationContext,
    OrdinaryRunExecutionBaseline,
    RunStatus,
    StartRunRequest,
    SubmitFollowupRequest,
)
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.liveness import HostInstanceIdentity, register_current_instance
from dayu.host.durable.memory import read_latest_memory_snapshot
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.run_transition import (
    AcceptWorkerRunningInput,
    CreateRunningRunInput,
    PromotionSkipReason,
    TerminalCloseoutInput,
    accept_worker_running_in_transaction,
    create_running_run_with_starting_attempt_in_transaction,
    terminal_closeout_in_transaction,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.session_lifecycle import close_session, ensure_session
from dayu.host.durable.state import (
    AttemptRow,
    DispatchRecordRow,
    DispatchRecordStatus,
    RunRow,
    RunStartReason,
    StateMutationStatus,
    read_attempt_by_id,
    read_dispatch_record_by_attempt_id,
    read_run_by_id,
    WorkerKind,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatching_after_lane_row,
)
from dayu.host.durable.transaction import HostRow, HostTransaction, HostTransactionRunner
from dayu.host.memory import (
    CONVERSATION_MEMORY_CONSUMER_ID,
    default_memory_projection_policy,
    digest_memory_projection_policy,
)
from dayu.host.memory_repair import catch_up_conversation_memory_projection
from dayu.host.payload_resolution import event_payload_object
from dayu.host.projection import ProjectionCatchupPort

_NOW = datetime(2026, 5, 14, 9, 30, 0, tzinfo=UTC)
_CALLER_DIGEST = sha256_digest_json({"caller": "admission-test"})
_LANE_NAME = "llm"


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


@dataclass(frozen=True, slots=True)
class _SeededActiveRun:
    """测试用已启动 active Run 摘要。"""

    run: RunRow
    attempt: AttemptRow
    dispatch_record: DispatchRecordRow


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


@dataclass(slots=True)
class _ToggleFailingWakeupSpy(_WakeupSpy):
    """可切换失败的 wakeup spy。"""

    fail_dispatch: bool = False
    fail_queue_promotion: bool = False

    def wake_dispatch(self, record: PendingDispatchRecord) -> None:
        """记录 dispatch wakeup，并按开关抛出运行时错误。

        :param record: pending dispatch 摘要。
        :returns: ``None``。
        :raises RuntimeError: ``fail_dispatch`` 为真时抛出。
        """

        self.dispatches.append(record)
        if self.fail_dispatch:
            raise RuntimeError("forced dispatch wakeup failure")

    def wake_queue_promotion(self, session_id: str) -> None:
        """记录 promotion wakeup，并按开关抛出运行时错误。

        :param session_id: 目标 Session id。
        :returns: ``None``。
        :raises RuntimeError: ``fail_queue_promotion`` 为真时抛出。
        """

        self.promotions.append(session_id)
        if self.fail_queue_promotion:
            raise RuntimeError("forced queue wakeup failure")


@dataclass(slots=True)
class _CountingEventLogStore(EventLogStore):
    """记录 read_event_by_id 调用次数的 EventLog primitive。"""

    read_event_by_id_count: int = 0

    def read_event_by_id(
        self, transaction: HostTransaction, event_id: str
    ) -> EventLogRow | None:
        """统计并委托读取 EventLog row。

        :param transaction: Host transaction。
        :param event_id: Event id。
        :returns: EventLog row；不存在时返回 ``None``。
        :raises HostDurableError: Event id 非法时由底层抛出。
        """

        self.read_event_by_id_count += 1
        return EventLogStore.read_event_by_id(self, transaction, event_id)


@dataclass(slots=True)
class _FailingProjectionCatchup(ProjectionCatchupPort):
    """测试用失败 projection catch-up port。"""

    calls: int = 0

    def catch_up_projection(self) -> None:
        """记录调用并模拟 projection catch-up 失败。

        :returns: ``None``。
        :raises RuntimeError: 始终抛出测试错误。
        """

        self.calls += 1
        raise RuntimeError("forced projection catch-up failure")


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


def _options_with_payload_inline_threshold(
    tmp_path: Path, payload_inline_threshold_bytes: int
) -> HostDurableStoreOptions:
    """构造覆盖 payload inline 阈值的测试 options。

    :param tmp_path: pytest 临时目录。
    :param payload_inline_threshold_bytes: payload inline 阈值字节数。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(
            artifact_root=tmp_path / "artifacts",
            payload_inline_threshold_bytes=payload_inline_threshold_bytes,
        ),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=0.5,
            write_busy_retry_count=8,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.02,
        ),
    )


def test_start_run_on_open_session_creates_accepted_run_and_governance_wakeup(
    tmp_path: Path,
) -> None:
    """start_run 在无 active Run 时创建 accepted Run 并唤醒 governance。"""

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

        assert result.run.status == RunStatus.ACCEPTED
        assert result.run.execution_target == "target-initial"
        assert result.attempt is None
        assert result.dispatch_record is None
        assert result.pending_dispatch is None
        assert spy.dispatches == []
        assert spy.promotions == [session_id]
        assert _count_rows(store.transaction_runner, "host_attempts") == 0
        assert _event_types_for_run(store.transaction_runner, result.run.run_id) == (
            "USER_INPUT_ACCEPTED",
            "RUN_ACCEPTED",
        )


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
        assert _count_rows(store.transaction_runner, "host_attempts") == 0
        assert spy.dispatches == []
        assert spy.promotions == [session_id]
        skipped = service.promote_next_queued_run(session_id)
        assert skipped.skipped is True
        assert skipped.promoted_run is None
        assert _read_run(store.transaction_runner, queued.run.run_id).status == (
            RunStatus.QUEUED
        )


def test_followup_queue_without_active_creates_accepted_run(
    tmp_path: Path,
) -> None:
    """无 active Run 时 follow-up queue 创建 accepted Run 并等待 governance。"""

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

        assert result.run.status == RunStatus.ACCEPTED
        assert result.run.execution_target == "follow-target"
        assert result.attempt is None
        assert result.dispatch_record is None
        assert _event_types_for_run(store.transaction_runner, result.run.run_id) == (
            "USER_INPUT_ACCEPTED",
            "RUN_ACCEPTED",
        )


def test_followup_queue_spills_large_user_input_payload(
    tmp_path: Path,
) -> None:
    """大 ``USER_INPUT_ACCEPTED`` payload 写入 descriptor 并可按真源读取。"""

    display_text = "long prompt " * 600
    with open_host_durable_store(
        _options_with_payload_inline_threshold(
            tmp_path, payload_inline_threshold_bytes=4096
        )
    ) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        service = _service(store.transaction_runner)

        result = service.submit_followup_queue(
            SubmitFollowupQueueAdmissionInput(
                request=_followup_request(
                    session_id=session_id,
                    client_request_id="follow-large-payload",
                    display_text=display_text,
                ),
                resolved_execution_target="follow-target",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )

        input_event = _read_user_input_event(
            store.transaction_runner, result.run.input_event_id
        )
        payload = _event_payload_object(store.transaction_runner, input_event)

        assert input_event.payload_ref is not None
        assert input_event.payload_digest is not None
        assert "long prompt" not in input_event.payload_json
        assert payload["display_text"] == display_text
        assert payload["user_prompt"] == display_text
        inline_payload = _payload_mapping(input_event)
        assert "display_text" not in inline_payload
        assert "user_prompt" not in inline_payload
        assert "system_prompt" not in inline_payload
        assert "effective_execution_config" not in inline_payload
        assert "effective_tool_set" not in inline_payload


def test_followup_queue_payload_inline_threshold_boundary(
    tmp_path: Path,
) -> None:
    """payload canonical UTF-8 len 等于阈值时 inline，阈值少一时 descriptor。"""

    display_text = "boundary prompt"
    baseline_dir = tmp_path / "baseline"
    inline_dir = tmp_path / "inline"
    descriptor_dir = tmp_path / "descriptor"
    baseline_dir.mkdir()
    inline_dir.mkdir()
    descriptor_dir.mkdir()
    payload_size = _accepted_input_payload_size(
        baseline_dir,
        client_request_id="follow-boundary",
        display_text=display_text,
        payload_inline_threshold_bytes=4096,
    )

    inline_event = _accepted_input_event(
        inline_dir,
        client_request_id="follow-boundary-inline",
        display_text=display_text,
        payload_inline_threshold_bytes=payload_size,
    )
    descriptor_event = _accepted_input_event(
        descriptor_dir,
        client_request_id="follow-boundary-descriptor",
        display_text=display_text,
        payload_inline_threshold_bytes=payload_size - 1,
    )

    assert inline_event.payload_ref is None
    assert descriptor_event.payload_ref is not None


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


def test_reject_conflicts_and_attach_active_returns_accepted_active(
    tmp_path: Path,
) -> None:
    """accepted active 上 reject conflict，attach_active 返回现有 Run。"""

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

        assert reject_error.value.code == HostApiErrorCode.CONFLICT
        assert attached.run.run_id == active.run.run_id
        assert attached.run.status == RunStatus.ACCEPTED
        assert attached.attempt is None
        assert attached.dispatch_record is None
        assert attached.attached_active is True
        replay = service.start_run(
            _start_request(
                session_id=session_id,
                client_request_id="start-attach",
                queue_policy="attach_active",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        assert replay.run.run_id == active.run.run_id
        assert replay.idempotent_replay is True
        assert _event_count(store.transaction_runner) == before_events
        assert active.run.status == RunStatus.ACCEPTED
        assert _count_rows(store.transaction_runner, "idempotency_records") == (
            before_idempotency + 1
        )


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
        active = _seed_active_run(store.transaction_runner, session_id=session_id)
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
        assert len(spy.dispatches) == 1


def test_cancel_queued_run_is_idempotent_and_creates_no_attempt(
    tmp_path: Path,
) -> None:
    """queued cancel 写 cancel facts，不创建 Attempt，重复请求不追加事件。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        service = _service(store.transaction_runner)
        service.start_run(
            _start_request(session_id=session_id, client_request_id="start-active"),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        queued = service.submit_followup_queue(
            SubmitFollowupQueueAdmissionInput(
                request=_followup_request(
                    session_id=session_id,
                    client_request_id="follow-cancel-queued",
                ),
                resolved_execution_target="queued-target",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        before_retry = 0

        first = service.cancel_run(
            queued.run.run_id,
            _cancel_request("cancel-queued"),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        before_retry = _event_count(store.transaction_runner)
        second = service.cancel_run(
            queued.run.run_id,
            _cancel_request("cancel-queued"),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        record = _idempotency_record(
            store.transaction_runner,
            scope_kind="cancel_run",
            scope_id=queued.run.run_id,
            key="cancel-queued",
        )

        assert first.run.status == RunStatus.CANCELLED
        assert first.attempt is None
        assert first.dispatch_record is None
        assert first.promotion is None
        assert second.idempotent_replay is True
        assert second.run.run_id == queued.run.run_id
        assert _event_count(store.transaction_runner) == before_retry
        assert _count_rows(store.transaction_runner, "host_attempts") == 0
        assert _event_types_for_run(store.transaction_runner, queued.run.run_id) == (
            "USER_INPUT_ACCEPTED",
            "RUN_ACCEPTED",
            "RUN_QUEUED",
            "CANCEL_REQUESTED",
            "RUN_CANCELLED",
        )
        assert _text(record, "created_event_id") is not None


def test_cancel_predispatch_starting_promotes_exactly_one_queued_run(
    tmp_path: Path,
) -> None:
    """active pre-dispatch cancel 取消 dispatch/Attempt/Run 后新事务 promotion 一条队列。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        spy = _WakeupSpy()
        service = _service(store.transaction_runner, spy=spy)
        active = _seed_active_run(store.transaction_runner, session_id=session_id)
        first_queued = service.submit_followup_queue(
            SubmitFollowupQueueAdmissionInput(
                request=_followup_request(
                    session_id=session_id,
                    client_request_id="follow-first",
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
                    client_request_id="follow-second",
                    display_text="second queued",
                ),
                resolved_execution_target="second-target",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        assert active.attempt is not None
        assert active.dispatch_record is not None

        result = service.cancel_run(
            active.run.run_id,
            _cancel_request("cancel-active"),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        active_attempt = _read_attempt(
            store.transaction_runner, active.attempt.attempt_id
        )
        active_dispatch = _read_dispatch_record(
            store.transaction_runner,
            active.dispatch_record.attempt_id,
        )

        assert result.run.status == RunStatus.CANCELLED
        assert result.attempt is not None
        assert result.attempt.status == AttemptStatus.CANCELLED
        assert result.dispatch_record is not None
        assert result.dispatch_record.status == DispatchRecordStatus.CANCELLED
        assert active_attempt.status == AttemptStatus.CANCELLED
        assert active_dispatch.status == DispatchRecordStatus.CANCELLED
        assert result.promotion is not None
        assert result.promotion.skipped is True
        assert result.promotion.promoted_run is None
        assert _read_run(store.transaction_runner, first_queued.run.run_id).status == (
            RunStatus.QUEUED
        )
        assert _read_run(store.transaction_runner, second_queued.run.run_id).status == (
            RunStatus.QUEUED
        )
        assert spy.promotions == [session_id]
        assert spy.dispatches == []


def test_cancel_predispatch_starting_promotion_survives_queue_wakeup_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """active cancel 后 queue wakeup 失败不掩盖已完成 promotion。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        spy = _ToggleFailingWakeupSpy()
        service = _service(store.transaction_runner, spy=spy)
        active = _seed_active_run(store.transaction_runner, session_id=session_id)
        queued = service.submit_followup_queue(
            SubmitFollowupQueueAdmissionInput(
                request=_followup_request(
                    session_id=session_id,
                    client_request_id="follow-wakeup-fails",
                ),
                resolved_execution_target="queued-target",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        spy.fail_queue_promotion = True

        with caplog.at_level(logging.WARNING, logger="dayu.host.admission"):
            result = service.cancel_run(
                active.run.run_id,
                _cancel_request("cancel-active-wakeup-fails"),
                caller_semantic_digest=_CALLER_DIGEST,
            )

        assert result.run.status == RunStatus.CANCELLED
        assert result.promotion is not None
        assert result.promotion.skipped is True
        assert result.promotion.promoted_run is None
        assert _read_run(store.transaction_runner, queued.run.run_id).status == (
            RunStatus.QUEUED
        )
        assert spy.promotions == [session_id]
        assert "host.admission.queue_promotion_wakeup_failed" in caplog.text
        assert session_id in caplog.text


def test_promote_after_release_reports_delegated_to_governance(
    tmp_path: Path,
) -> None:
    """active slot 释放后的 wakeup 结果不谎称 active Run 仍存在。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        spy = _WakeupSpy()
        service = _service(store.transaction_runner, spy=spy)

        result = admission_module._promote_after_release(
            service=service,
            session_id=session_id,
        )

        assert result.skipped is True
        assert result.skip_reason is PromotionSkipReason.DELEGATED_TO_GOVERNANCE
        assert spy.promotions == [session_id]


def test_promote_next_queued_run_returns_result_when_dispatch_wakeup_fails(
    tmp_path: Path,
) -> None:
    """promotion 提交后 dispatch wakeup 失败不掩盖 promotion 结果。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        spy = _ToggleFailingWakeupSpy()
        service = _service(store.transaction_runner, spy=spy)
        active = _seed_active_run(store.transaction_runner, session_id=session_id)
        queued = service.submit_followup_queue(
            SubmitFollowupQueueAdmissionInput(
                request=_followup_request(
                    session_id=session_id,
                    client_request_id="follow-dispatch-wakeup-fails",
                ),
                resolved_execution_target="queued-target",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        _closeout_active(store.transaction_runner, active.run.run_id)
        spy.fail_dispatch = True

        result = service.promote_next_queued_run(session_id)

        assert result.promoted_run is not None
        assert result.promoted_run.run_id == queued.run.run_id
        assert _read_run(store.transaction_runner, queued.run.run_id).status == (
            RunStatus.RUNNING
        )
        assert len(spy.dispatches) == 1


def test_start_run_survives_after_commit_projection_catchup_failure(
    tmp_path: Path,
) -> None:
    """start_run commit 后 projection catch-up 失败不掩盖命令结果。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        projection = _FailingProjectionCatchup()
        service = _service(
            store.transaction_runner,
            projection_catchup=projection,
        )

        result = service.start_run(
            _start_request(
                session_id=session_id,
                client_request_id="start-projection-catchup-fails",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )

        assert result.run.status == RunStatus.ACCEPTED
        assert result.pending_dispatch is None
        assert projection.calls == 1


def test_start_run_then_direct_memory_catchup_projects_user_input(
    tmp_path: Path,
) -> None:
    """start_run 提交用户输入后直接 catch-up 会投影用户输入 memory。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: committed 用户输入未被 memory catch-up 投影时抛出。
    """

    policy = default_memory_projection_policy()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        service = _service(store.transaction_runner)

        result = service.start_run(
            _start_request(
                session_id=session_id,
                client_request_id="start-memory-catch-up",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        catch_up_conversation_memory_projection(
            store.transaction_runner,
            policy=policy,
            batch_size=8,
            max_event_sequence=result.run.input_event_sequence,
        )
        snapshot = store.transaction_runner.run_read(
            lambda transaction: read_latest_memory_snapshot(
                transaction,
                session_id=session_id,
                consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                policy_digest=digest_memory_projection_policy(policy),
            )
        )

        assert result.run.status == RunStatus.ACCEPTED
        assert snapshot is not None
        assert tuple(
            item.text for item in snapshot.snapshot.trace_memory.selected_recent_window
        ) == ("start input",)


def test_terminal_closeout_promotes_exactly_one_queued_run_after_commit(
    tmp_path: Path,
) -> None:
    """terminal closeout 释放 active slot 后在新事务中 promotion 一条 queued Run。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        spy = _WakeupSpy()
        service = _service(store.transaction_runner, spy=spy)
        active = _seed_active_run(store.transaction_runner, session_id=session_id)
        assert active.attempt is not None
        first_queued = service.submit_followup_queue(
            SubmitFollowupQueueAdmissionInput(
                request=_followup_request(
                    session_id=session_id,
                    client_request_id="follow-terminal-first",
                ),
                resolved_execution_target="first-target",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        second_queued = service.submit_followup_queue(
            SubmitFollowupQueueAdmissionInput(
                request=_followup_request(
                    session_id=session_id,
                    client_request_id="follow-terminal-second",
                ),
                resolved_execution_target="second-target",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )

        result = service.closeout_attempt_terminal(
            CloseoutAttemptTerminalInput(
                run_id=active.run.run_id,
                attempt_id=active.attempt.attempt_id,
                attempt_terminal_status=AttemptStatus.SUCCEEDED,
                run_terminal_status=RunStatus.SUCCEEDED,
                terminal_summary_ref=None,
                terminal_summary_digest=None,
            )
        )

        assert result.run.status == RunStatus.SUCCEEDED
        assert result.attempt.status == AttemptStatus.SUCCEEDED
        assert result.promotion.skipped is True
        assert result.promotion.promoted_run is None
        assert _read_run(store.transaction_runner, first_queued.run.run_id).status == (
            RunStatus.QUEUED
        )
        assert _read_run(store.transaction_runner, second_queued.run.run_id).status == (
            RunStatus.QUEUED
        )
        assert spy.promotions == [session_id]
        assert spy.dispatches == []


def test_terminal_closeout_survives_after_commit_projection_catchup_failure(
    tmp_path: Path,
) -> None:
    """terminal closeout 后 projection catch-up 失败不影响 closeout / promotion。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        projection = _FailingProjectionCatchup()
        service = _service(
            store.transaction_runner,
            projection_catchup=projection,
        )
        active = _seed_active_run(store.transaction_runner, session_id=session_id)
        assert active.attempt is not None
        queued = service.submit_followup_queue(
            SubmitFollowupQueueAdmissionInput(
                request=_followup_request(
                    session_id=session_id,
                    client_request_id="follow-after-catchup-fails",
                ),
                resolved_execution_target="queued-target",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )

        result = service.closeout_attempt_terminal(
            CloseoutAttemptTerminalInput(
                run_id=active.run.run_id,
                attempt_id=active.attempt.attempt_id,
                attempt_terminal_status=AttemptStatus.SUCCEEDED,
                run_terminal_status=RunStatus.SUCCEEDED,
                terminal_summary_ref=None,
                terminal_summary_digest=None,
            )
        )

        assert result.run.status == RunStatus.SUCCEEDED
        assert result.promotion.skipped is True
        assert result.promotion.promoted_run is None
        assert _read_run(store.transaction_runner, queued.run.run_id).status == (
            RunStatus.QUEUED
        )
        assert projection.calls == 2


def test_terminal_closeout_promotion_survives_queue_wakeup_failure(
    tmp_path: Path,
) -> None:
    """terminal closeout 后 queue wakeup 失败不掩盖已完成 promotion。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        spy = _ToggleFailingWakeupSpy()
        service = _service(store.transaction_runner, spy=spy)
        active = _seed_active_run(store.transaction_runner, session_id=session_id)
        assert active.attempt is not None
        queued = service.submit_followup_queue(
            SubmitFollowupQueueAdmissionInput(
                request=_followup_request(
                    session_id=session_id,
                    client_request_id="follow-terminal-wakeup-fails",
                ),
                resolved_execution_target="queued-target",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        spy.fail_queue_promotion = True

        result = service.closeout_attempt_terminal(
            CloseoutAttemptTerminalInput(
                run_id=active.run.run_id,
                attempt_id=active.attempt.attempt_id,
                attempt_terminal_status=AttemptStatus.SUCCEEDED,
                run_terminal_status=RunStatus.SUCCEEDED,
                terminal_summary_ref=None,
                terminal_summary_digest=None,
            )
        )

        assert result.run.status == RunStatus.SUCCEEDED
        assert result.promotion.skipped is True
        assert result.promotion.promoted_run is None
        assert _read_run(store.transaction_runner, queued.run.run_id).status == (
            RunStatus.QUEUED
        )
        assert spy.promotions == [session_id]


def test_cancel_terminal_run_returns_current_terminal_without_new_facts(
    tmp_path: Path,
) -> None:
    """terminal Run 的后续 cancel 返回当前终态且不追加 canonical facts。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        service = _service(store.transaction_runner)
        active = _seed_active_run(store.transaction_runner, session_id=session_id)
        assert active.attempt is not None
        service.closeout_attempt_terminal(
            CloseoutAttemptTerminalInput(
                run_id=active.run.run_id,
                attempt_id=active.attempt.attempt_id,
                attempt_terminal_status=AttemptStatus.SUCCEEDED,
                run_terminal_status=RunStatus.SUCCEEDED,
                terminal_summary_ref=None,
                terminal_summary_digest=None,
            )
        )
        before = _event_count(store.transaction_runner)

        result = service.cancel_run(
            active.run.run_id,
            _cancel_request("cancel-terminal"),
            caller_semantic_digest=_CALLER_DIGEST,
        )

        assert result.run.status == RunStatus.SUCCEEDED
        assert result.attempt is not None
        assert result.attempt.status == AttemptStatus.SUCCEEDED
        assert result.dispatch_record is not None
        assert result.promotion is None
        assert result.active_cancel_target is None
        assert _event_count(store.transaction_runner) == before
        assert _read_run(store.transaction_runner, active.run.run_id).status == (
            RunStatus.SUCCEEDED
        )


def test_cancel_attempt_running_enters_cancelling_with_cancel_facts(
    tmp_path: Path,
) -> None:
    """Attempt RUNNING active cancel 进入 CANCELLING 并追加 cancel facts。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        service = _service(store.transaction_runner)
        active = _seed_active_run(store.transaction_runner, session_id=session_id)
        assert active.attempt is not None
        _force_attempt_status(
            store.transaction_runner,
            attempt_id=active.attempt.attempt_id,
            status=AttemptStatus.RUNNING,
        )
        before = _event_count(store.transaction_runner)

        result = service.cancel_run(
            active.run.run_id,
            _cancel_request("cancel-running-attempt"),
            caller_semantic_digest=_CALLER_DIGEST,
        )

        assert result.run.status == RunStatus.CANCELLING
        assert result.attempt is not None
        assert result.attempt.status == AttemptStatus.RUNNING
        assert result.active_cancel_target is not None
        assert result.active_cancel_target.run_id == active.run.run_id
        assert _event_count(store.transaction_runner) == before + 2
        assert _event_types_for_run(store.transaction_runner, active.run.run_id)[-2:] == (
            "CANCEL_REQUESTED",
            "RUN_CANCELLING",
        )
        assert _read_run(store.transaction_runner, active.run.run_id).status == (
            RunStatus.CANCELLING
        )


def test_cancel_session_replay_uses_injected_event_log_store(
    tmp_path: Path,
) -> None:
    """session cancel replay 通过注入的 EventLogStore 恢复 active cancel 目标。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    """

    event_log_store = _CountingEventLogStore()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        service = _service(store.transaction_runner, event_log_store=event_log_store)
        active = _seed_active_run(store.transaction_runner, session_id=session_id)
        _accept_active_worker(
            store.transaction_runner,
            run_id=active.run.run_id,
            attempt_id=active.attempt.attempt_id,
        )
        request = _cancel_session_request("cancel-session-active-replay")

        first = service.cancel_session_runs(
            session_id, request, caller_semantic_digest=_CALLER_DIGEST
        )
        replay = service.cancel_session_runs(
            session_id, request, caller_semantic_digest=_CALLER_DIGEST
        )

        assert first.active_cancel_targets == replay.active_cancel_targets
        assert replay.idempotent_replay is True
        assert len(replay.active_cancel_targets) == 1
        assert replay.active_cancel_targets[0].run_id == active.run.run_id
        assert event_log_store.read_event_by_id_count >= 1


def test_rollback_before_cancel_commit_does_not_wake_or_promote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cancel transaction rollback 时不执行 wakeup，也不在新事务 promotion。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        spy = _WakeupSpy()
        service = _service(store.transaction_runner, spy=spy)
        active = _seed_active_run(store.transaction_runner, session_id=session_id)
        queued = service.submit_followup_queue(
            SubmitFollowupQueueAdmissionInput(
                request=_followup_request(
                    session_id=session_id,
                    client_request_id="follow-rollback",
                ),
                resolved_execution_target="queued-target",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        original_cancel = admission_module.cancel_predispatch_starting_in_transaction

        def fail_after_transition(
            transaction: HostTransaction,
            event_log_store: EventLogStore,
            request: admission_module.CancelPredispatchStartingInput,
        ) -> admission_module.DurableRunTransitionResult:
            """执行真实 cancel 后抛错，模拟 commit 前失败。

            :param transaction: Host transaction。
            :param event_log_store: EventLog store。
            :param request: cancel pre-dispatch 输入。
            :returns: 不返回，签名保持与被替换函数一致。
            :raises HostDurableError: 总是抛出以触发 rollback。
            """

            original_cancel(transaction, event_log_store, request)
            raise HostDurableError("forced rollback")

        monkeypatch.setattr(
            admission_module,
            "cancel_predispatch_starting_in_transaction",
            fail_after_transition,
        )

        with pytest.raises(HostDurableError):
            service.cancel_run(
                active.run.run_id,
                _cancel_request("cancel-rollback"),
                caller_semantic_digest=_CALLER_DIGEST,
            )

        assert spy.promotions == []
        assert spy.dispatches == []
        assert _read_run(store.transaction_runner, active.run.run_id).status == (
            RunStatus.RUNNING
        )
        assert _read_run(store.transaction_runner, queued.run.run_id).status == (
            RunStatus.QUEUED
        )
        assert "CANCEL_REQUESTED" not in _event_types_for_run(
            store.transaction_runner, active.run.run_id
        )


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
        active = _seed_active_run(store.transaction_runner, session_id=session_id)
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
    projection_catchup: ProjectionCatchupPort | None = None,
    event_log_store: EventLogStore | None = None,
    label: str = "main",
) -> HostAdmissionService:
    """构造测试 admission service。

    :param transaction_runner: Host transaction runner。
    :param spy: 可选 wakeup spy。
    :param projection_catchup: 可选 projection catch-up port。
    :param event_log_store: 可选 EventLog primitive。
    :param label: id factory 标签。
    :returns: HostAdmissionService。
    """

    return create_host_admission_service(
        transaction_runner,
        clock=_FixedClock(),
        id_factory=_SequentialIdFactory(label),
        wakeup_port=spy if spy is not None else _WakeupSpy(),
        projection_catchup_port=projection_catchup,
        event_log_store=event_log_store,
        ordinary_run_baseline=_ordinary_run_baseline(),
        tooling_options=None,
    )


def _ordinary_run_baseline() -> OrdinaryRunExecutionBaseline:
    """构造测试用 ordinary Run 执行基线。

    :returns: OrdinaryRunExecutionBaseline。
    :raises TypeError: baseline typed 字段类型非法时抛出。
    :raises ValueError: baseline 字段语义非法时抛出。
    """

    return OrdinaryRunExecutionBaseline(
        runner_spec=RunnerSpec(
            provider="test",
            model="admission-baseline-model",
            endpoint="https://example.invalid",
            api_key_ref="secret:admission-baseline",
            headers={},
            client_correlation_policy=ClientCorrelationPolicy.DISABLED,
            supports_tool_calling=False,
            supports_streaming=False,
            supports_stream_usage=False,
            default_timeout_seconds=1.0,
            max_retries=0,
            provider_request=None,
        ),
        runner_options=RunnerCallOptions(
            temperature=None, max_tokens=None, top_p=None, stream=False
        ),
        agent_policy=AgentPolicy(
            max_iterations=1,
            continuation_max_attempts=0,
            allow_tool_calls=False,
            tool_execution_timeout_seconds=1.0,
            fallback_prompt="test fallback prompt",
            continuation_prompt="test continuation prompt",
        ),
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


def _seed_active_run(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    run_id: str = "run-seeded-active",
    attempt_id: str = "attempt-seeded-active",
    execution_id: str = "execution-seeded-active",
    dispatch_record_id: str = "dispatch-seeded-active",
    input_event_id: str = "event-seeded-input",
) -> _SeededActiveRun:
    """用低层 transition 创建 RUNNING + STARTING active Run。

    :param transaction_runner: Host transaction runner。
    :param session_id: Session id。
    :param run_id: Run id。
    :param attempt_id: Attempt id。
    :param execution_id: execution id。
    :param dispatch_record_id: dispatch record id。
    :param input_event_id: input event id。
    :returns: active Run 摘要。
    """

    input_sequence = _append_seed_user_input(
        transaction_runner,
        session_id=session_id,
        run_id=run_id,
        event_id=input_event_id,
    )

    def operation(transaction: HostTransaction) -> _SeededActiveRun:
        """写入 active Run。

        :param transaction: Host transaction。
        :returns: active Run 摘要。
        """

        transition = create_running_run_with_starting_attempt_in_transaction(
            transaction,
            EventLogStore(),
            CreateRunningRunInput(
                session_id=session_id,
                run_id=run_id,
                client_request_id=f"client-{run_id}",
                input_event_id=input_event_id,
                input_event_sequence=input_sequence,
                run_accepted_event_id=f"event-run-accepted-{run_id}",
                run_started_event_id=f"event-run-started-{run_id}",
                attempt_started_event_id=f"event-attempt-started-{run_id}",
                attempt_id=attempt_id,
                execution_id=execution_id,
                dispatch_record_id=dispatch_record_id,
                occurred_at=_NOW,
                actor="analyst",
                source="pytest",
                idempotency_key=f"idem-{run_id}",
                execution_target="target-seeded-active",
                queue_policy=RunQueuePolicy.QUEUE,
                start_reason=RunStartReason.INITIAL,
                worker_kind=WorkerKind.LOCAL,
                owner_host_instance_id=None,
                call_context_digest=_CALLER_DIGEST,
            ),
        )
        assert transition.run is not None
        assert transition.attempt is not None
        assert transition.dispatch_record is not None
        return _SeededActiveRun(
            run=transition.run,
            attempt=transition.attempt,
            dispatch_record=transition.dispatch_record,
        )

    return transaction_runner.run_write(operation)


def _append_seed_user_input(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    run_id: str,
    event_id: str,
    display_text: str = "seeded active input",
) -> int:
    """追加测试 active Run 的 USER_INPUT_ACCEPTED。

    :param transaction_runner: Host transaction runner。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_id: event id。
    :param display_text: 输入文本。
    :returns: event sequence。
    """

    def operation(transaction: HostTransaction) -> int:
        """追加输入事件。

        :param transaction: Host transaction。
        :returns: event sequence。
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
                event_type="USER_INPUT_ACCEPTED",
                occurred_at=_NOW,
                actor="analyst",
                source="pytest",
                client_request_id=f"client-{run_id}",
                idempotency_key=f"input-{run_id}",
                policy_decision=None,
                reason=None,
                payload_json={
                    "input_ref": None,
                    "input_digest": None,
                    "display_text": display_text,
                    "payload_ref": None,
                    "payload_digest": None,
                    "operation_kind": "start_run",
                    "call_context_digest": _CALLER_DIGEST,
                },
                payload_ref=None,
                payload_digest=None,
            ),
        ).row
        return event.event_sequence

    return transaction_runner.run_write(operation)


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
        system_prompt=None,
        user_prompt=display_text,
        tool_names=None,
        runner_spec=None,
        runner_options=None,
        agent_policy=None,
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


def _cancel_request(client_request_id: str) -> CancelRunRequest:
    """构造 cancel run 请求。

    :param client_request_id: 幂等请求 id。
    :returns: CancelRunRequest。
    """

    return CancelRunRequest(
        context=_context(),
        client_request_id=client_request_id,
        reason="user_cancel",
        mode=CancelMode.GRACEFUL,
    )


def _cancel_session_request(client_request_id: str) -> CancelSessionRunsRequest:
    """构造 cancel session runs 请求。

    :param client_request_id: 幂等请求 id。
    :returns: CancelSessionRunsRequest。
    """

    return CancelSessionRunsRequest(
        context=_context(),
        client_request_id=client_request_id,
        reason="user_cancel_all",
        mode=CancelMode.GRACEFUL,
    )


def _accept_active_worker(
    transaction_runner: HostTransactionRunner, *, run_id: str, attempt_id: str
) -> None:
    """用 durable transition helper 构造 active worker accepted 状态。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :param attempt_id: Attempt id。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """写入 worker accepted 状态。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        register_current_instance(
            transaction,
            HostInstanceIdentity(
                host_instance_id="host-admission-test",
                pid=os.getpid(),
                process_start_token="admission-test",
                boot_id=None,
            ),
        )
        waiting = mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id=attempt_id,
            owner_host_instance_id="host-admission-test",
            lane_name=_LANE_NAME,
            waiting_for_lane_at="2026-05-14T09:30:00.000000Z",
        )
        assert waiting.status == StateMutationStatus.UPDATED
        dispatching = mark_dispatching_after_lane_row(
            transaction,
            attempt_id=attempt_id,
            owner_host_instance_id="host-admission-test",
            lane_name=_LANE_NAME,
            lane_claim_id=f"claim-{attempt_id}",
            lane_owner_id="owner-admission-test",
            lane_acquired_at="2026-05-14T09:30:00.000000Z",
            dispatching_at="2026-05-14T09:30:00.000000Z",
        )
        assert dispatching.status == StateMutationStatus.UPDATED
        accepted = accept_worker_running_in_transaction(
            transaction,
            EventLogStore(),
            AcceptWorkerRunningInput(
                run_id=run_id,
                attempt_id=attempt_id,
                attempt_running_event_id=f"event-attempt-running-{attempt_id}",
                occurred_at=_NOW,
                actor="host.dispatch",
                source="host.dispatch",
                worker_accept_reason="local_worker_accepted",
                local_worker_id=f"worker-{attempt_id}",
            ),
        )
        assert accepted.status == StateMutationStatus.UPDATED

    transaction_runner.run_write(operation)


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


def _read_attempt(
    transaction_runner: HostTransactionRunner, attempt_id: str
) -> AttemptRow:
    """读取 Attempt row。

    :param transaction_runner: Host transaction runner。
    :param attempt_id: Attempt id。
    :returns: Attempt row。
    """

    def operation(transaction: HostTransaction) -> AttemptRow:
        """读取 Attempt row。

        :param transaction: Host transaction。
        :returns: Attempt row。
        """

        attempt = read_attempt_by_id(transaction, attempt_id)
        assert attempt is not None
        return attempt

    return transaction_runner.run_write(operation)


def _read_dispatch_record(
    transaction_runner: HostTransactionRunner, attempt_id: str
) -> DispatchRecordRow:
    """读取 Attempt dispatch record。

    :param transaction_runner: Host transaction runner。
    :param attempt_id: Attempt id。
    :returns: DispatchRecordRow。
    """

    def operation(transaction: HostTransaction) -> DispatchRecordRow:
        """读取 dispatch record。

        :param transaction: Host transaction。
        :returns: dispatch record。
        """

        dispatch_record = read_dispatch_record_by_attempt_id(transaction, attempt_id)
        assert dispatch_record is not None
        return dispatch_record

    return transaction_runner.run_write(operation)


def _force_attempt_status(
    transaction_runner: HostTransactionRunner,
    *,
    attempt_id: str,
    status: AttemptStatus,
) -> None:
    """测试内强制修改 Attempt 状态以构造 Phase 3 unsupported state。

    :param transaction_runner: Host transaction runner。
    :param attempt_id: Attempt id。
    :param status: 目标 Attempt 状态。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """写入 Attempt 状态。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        transaction.execute(
            "UPDATE host_attempts SET status = ? WHERE attempt_id = ?",
            (status.value, attempt_id),
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


def _read_user_input_event(
    transaction_runner: HostTransactionRunner, event_id: str
) -> EventLogRow:
    """按 event id 读取 ``USER_INPUT_ACCEPTED`` 事件。

    :param transaction_runner: Host transaction runner。
    :param event_id: event id。
    :returns: EventLog row。
    """

    def operation(transaction: HostTransaction) -> EventLogRow:
        """读取 EventLog row。

        :param transaction: Host transaction。
        :returns: EventLog row。
        """

        row = EventLogStore().read_event_by_id(transaction, event_id)
        assert row is not None
        assert row.event_type == "USER_INPUT_ACCEPTED"
        return row

    return transaction_runner.run_read(operation)


def _event_payload_object(
    transaction_runner: HostTransactionRunner, event: EventLogRow
) -> Mapping[str, JsonValue]:
    """读取 EventLog payload object。

    :param transaction_runner: Host transaction runner。
    :param event: EventLog row。
    :returns: payload JSON object。
    """

    def operation(transaction: HostTransaction) -> Mapping[str, JsonValue]:
        """读取 payload object。

        :param transaction: Host transaction。
        :returns: payload JSON object。
        """

        return event_payload_object(
            transaction, event, payload_label="USER_INPUT_ACCEPTED"
        )

    return transaction_runner.run_read(operation)


def _payload_mapping(event: EventLogRow) -> Mapping[str, JsonValue]:
    """解析 EventLog inline payload。

    :param event: EventLog row。
    :returns: inline payload mapping。
    :raises AssertionError: inline payload 不是 object 时抛出。
    """

    value = json.loads(event.payload_json)
    assert isinstance(value, Mapping)
    return value


def _accepted_input_payload_size(
    tmp_path: Path,
    *,
    client_request_id: str,
    display_text: str,
    payload_inline_threshold_bytes: int,
) -> int:
    """创建 followup 并返回 USER_INPUT_ACCEPTED inline payload UTF-8 长度。

    :param tmp_path: pytest 临时目录。
    :param client_request_id: 幂等请求 id。
    :param display_text: 用户输入展示文本。
    :param payload_inline_threshold_bytes: payload inline 阈值。
    :returns: canonical inline payload UTF-8 字节长度。
    """

    event = _accepted_input_event(
        tmp_path,
        client_request_id=client_request_id,
        display_text=display_text,
        payload_inline_threshold_bytes=payload_inline_threshold_bytes,
    )
    assert event.payload_ref is None
    return len(event.payload_json.encode("utf-8"))


def _accepted_input_event(
    tmp_path: Path,
    *,
    client_request_id: str,
    display_text: str,
    payload_inline_threshold_bytes: int,
) -> EventLogRow:
    """创建 followup 并返回 USER_INPUT_ACCEPTED event。

    :param tmp_path: pytest 临时目录。
    :param client_request_id: 幂等请求 id。
    :param display_text: 用户输入展示文本。
    :param payload_inline_threshold_bytes: payload inline 阈值。
    :returns: USER_INPUT_ACCEPTED EventLog row。
    """

    input_event: EventLogRow | None = None
    with open_host_durable_store(
        _options_with_payload_inline_threshold(
            tmp_path, payload_inline_threshold_bytes
        )
    ) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        service = _service(store.transaction_runner)
        result = service.submit_followup_queue(
            SubmitFollowupQueueAdmissionInput(
                request=_followup_request(
                    session_id=session_id,
                    client_request_id=client_request_id,
                    display_text=display_text,
                ),
                resolved_execution_target="follow-target",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        input_event = _read_user_input_event(
            store.transaction_runner, result.run.input_event_id
        )
    if input_event is None:
        raise AssertionError("input event must exist")
    return input_event


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
