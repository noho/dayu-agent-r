"""Host wait expiry terminal owner 与 first-committer race 测试。"""

from __future__ import annotations

from functools import partial
import json
import multiprocessing
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from dayu.host import (
    CancelMode,
    CancelRunRequest,
    HostApiError,
    RunStatus,
    WaitResolutionSource,
    cancel_run,
    get_run,
)
from dayu.host.admission import PendingDispatchRecord, create_host_admission_service
from dayu.host.command import expire_wait, start_run
from dayu.host.durable.state import (
    StateMutationStatus,
    WaitRecordStatus,
    read_run_by_id,
)
from dayu.host.projection import ProjectionCatchupPort
from dayu.host.terminal_post_commit import TerminalPostCommitNotice
from dayu.host.waiting import ExpireWaitInput, _expire_wait_in_transaction
from dayu.host.memory import default_memory_projection_policy
from tests.host.execution_handle_support import (
    create_execution_command_handle,
    deterministic_ordinary_run_baseline,
)
from tests.host.test_command_handle import _start_request
from tests.host.test_resolve_wait_command import (
    _context,
    _events,
    _failed_request,
    _options,
    _read_wait,
    _seed_waiting_run,
    _set_wait_deadline_text,
)

_create_execution_handle = partial(
    create_execution_command_handle,
    ordinary_run_baseline=deterministic_ordinary_run_baseline(
        "wait-expiry-closeout"
    ),
    memory_projection_policy=default_memory_projection_policy(),
    tooling_options=None,
    context_budget_policy=None,
    enable_truncation_manager=False,
)

_EXPIRED_AT = datetime(2026, 5, 16, 2, 0, 0, tzinfo=UTC)


class _BarrierPort(Protocol):
    """multiprocess barrier 的最小类型端口。"""

    def wait(self, timeout: float | None = None) -> int:
        """等待全部参与者到达。

        :param timeout: 可选超时秒数。
        :returns: barrier arrival index。
        """

        ...


class _RecordingProjection(ProjectionCatchupPort):
    """记录 projection 与 wake 顺序的测试端口。"""

    def __init__(self, order: list[str]) -> None:
        """初始化共享顺序记录。

        :param order: 顺序记录列表。
        :returns: ``None``。
        """

        self._order = order

    def catch_up_projection(self) -> None:
        """记录 projection catch-up。

        :returns: ``None``。
        """

        self._order.append("projection")


class _RecordingWakeup:
    """记录 dispatch 与 queue promotion wake 的 admission port。"""

    def __init__(self, order: list[str]) -> None:
        """初始化 wake 记录。

        :param order: 顺序记录列表。
        :returns: ``None``。
        """

        self._order = order
        self.queue_sessions: list[str] = []

    def wake_dispatch(self, record: PendingDispatchRecord) -> None:
        """忽略本测试不关心的 dispatch wake。

        :param record: committed pending dispatch。
        :returns: ``None``。
        """

        del record

    def wake_queue_promotion(self, session_id: str) -> None:
        """记录 commit 后 queue promotion wake。

        :param session_id: 释放 active slot 的 Session id。
        :returns: ``None``。
        """

        self._order.append("wake")
        self.queue_sessions.append(session_id)


class _RecordingTerminalPort:
    """记录 wait expiry terminal notice 与调用顺序。"""

    def __init__(self, order: list[str]) -> None:
        """初始化记录端口。

        :param order: 顺序记录列表。
        :returns: ``None``。
        """

        self._order = order
        self.notices: list[TerminalPostCommitNotice] = []

    def notify_terminal_post_commit(
        self,
        notice: TerminalPostCommitNotice,
    ) -> None:
        """记录 exact terminal notice。

        :param notice: 已提交的精确通知。
        :returns: ``None``。
        """

        self._order.append("notice")
        self.notices.append(notice)


def test_expiry_helper_owns_failed_terminal_and_stable_replay(
    tmp_path: Path,
) -> None:
    """helper 只消费 caller transaction，并以 durable boundary 稳定重放。"""

    host = _create_execution_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        _set_wait_deadline_text(
            host._transaction_runner(),
            seeded.wait_id,
            "2026-05-16T01:59:59.000000Z",
        )
        first = host._transaction_runner().run_write(
            lambda transaction: _expire_wait_in_transaction(
                transaction,
                ExpireWaitInput(
                    wait_id=seeded.wait_id,
                    observed_at=_EXPIRED_AT,
                    actor="expiry-owner-test",
                    source=WaitResolutionSource.POLL,
                ),
            )
        )
        events_after_first = _events(host._transaction_runner())
        replay = host._transaction_runner().run_write(
            lambda transaction: _expire_wait_in_transaction(
                transaction,
                ExpireWaitInput(
                    wait_id=seeded.wait_id,
                    observed_at=_EXPIRED_AT,
                    actor="different-actor",
                    source=WaitResolutionSource.CALLBACK,
                ),
            )
        )

        wait = _read_wait(host._transaction_runner(), seeded.wait_id)
        run = get_run(host, seeded.run_id)
        terminal_events = tuple(
            event
            for event in events_after_first
            if event.event_type in ("TOOL_RESULT_ACCEPTED", "RUN_FAILED")
        )
        tool_result = next(
            event
            for event in terminal_events
            if event.event_type == "TOOL_RESULT_ACCEPTED"
        )
        payload = json.loads(tool_result.payload_json)
        assert first.transition.status is StateMutationStatus.UPDATED
        assert first.terminal_notice is not None
        assert first.terminal_notice.wake_queue_promotion is True
        assert not first.idempotent_replay
        assert replay.transition.status is StateMutationStatus.CAS_LOST
        assert replay.idempotent_replay
        assert replay.terminal_notice is not None
        assert replay.terminal_notice.wake_queue_promotion is False
        assert (
            replay.terminal_notice.terminal_event_sequence
            == first.terminal_notice.terminal_event_sequence
        )
        assert _events(host._transaction_runner()) == events_after_first
        assert wait.status is WaitRecordStatus.FAILED
        assert run.status is RunStatus.FAILED
        assert len(terminal_events) == 2
        assert payload["result"]["result"]["error"] == "wait_deadline_expired"
        assert payload["result"]["result"]["hint"] is None
        assert payload["result"]["result"]["meta"] is None
        assert tool_result.payload_ref is None
    finally:
        host.close()


def test_expiry_wakes_queue_only_after_commit_and_projection(
    tmp_path: Path,
) -> None:
    """expiry terminal commit 后先交付 exact notice，再执行 projection。"""

    host = _create_execution_handle(_options(tmp_path))
    order: list[str] = []
    wakeup = _RecordingWakeup(order)
    projection = _RecordingProjection(order)
    terminal_port = _RecordingTerminalPort(order)
    host._terminal_post_commit_port = terminal_port
    previous = host._admission_service
    host._admission_service = create_host_admission_service(
        host._transaction_runner(),
        terminal_post_commit_port=terminal_port,
        payload_store=previous.payload_store,
        event_log_store=previous.event_log_store,
        idempotency_store=previous.idempotency_store,
        clock=previous.clock,
        id_factory=previous.id_factory,
        wakeup_port=wakeup,
        projection_catchup_port=projection,
        ordinary_run_baseline=previous.ordinary_run_baseline,
        tooling_options=previous.tooling_options,
        context_budget_policy=previous.context_budget_policy,
        memory_projection_policy=previous.memory_projection_policy,
        enable_truncation_manager=previous.enable_truncation_manager,
        owner_host_instance_id=previous.owner_host_instance_id,
    )
    try:
        seeded = _seed_waiting_run(host)
        queued = start_run(
            host,
            _start_request(seeded.session_id, "queued-after-wait"),
        )
        assert queued.status is RunStatus.QUEUED
        _set_wait_deadline_text(
            host._transaction_runner(),
            seeded.wait_id,
            "2026-05-16T01:59:59.000000Z",
        )
        order.clear()
        wakeup.queue_sessions.clear()

        result = expire_wait(
            host,
            ExpireWaitInput(
                wait_id=seeded.wait_id,
                observed_at=_EXPIRED_AT,
                actor="expiry-poller",
                source=WaitResolutionSource.POLL,
            ),
        )

        assert result.transition.status is StateMutationStatus.UPDATED
        assert order == ["notice", "projection"]
        assert wakeup.queue_sessions == []
        assert terminal_port.notices == [result.terminal_notice]
        assert _read_wait(host._transaction_runner(), seeded.wait_id).status is WaitRecordStatus.FAILED
    finally:
        host.close()


def test_result_cancel_expiry_multiprocess_first_committer_wins(
    tmp_path: Path,
) -> None:
    """result、cancel、expiry 同 barrier 竞争时只有一个 terminal fact 获胜。"""

    host = _create_execution_handle(_options(tmp_path))
    seeded = _seed_waiting_run(host)
    _set_wait_deadline_text(
        host._transaction_runner(),
        seeded.wait_id,
        "2026-05-16T03:00:00.000000Z",
    )
    host.close()

    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(4)
    processes = (
        context.Process(
            target=_resolve_failed_worker,
            args=(str(tmp_path), seeded.wait_id, barrier),
        ),
        context.Process(
            target=_cancel_worker,
            args=(str(tmp_path), seeded.run_id, barrier),
        ),
        context.Process(
            target=_expire_worker,
            args=(str(tmp_path), seeded.wait_id, barrier),
        ),
    )
    for process in processes:
        process.start()
    barrier.wait(timeout=5.0)
    for process in processes:
        process.join(10.0)
        assert process.exitcode == 0

    reader = _create_execution_handle(_options(tmp_path))
    try:
        events = _events(reader._transaction_runner())
        terminal = tuple(
            event
            for event in events
            if event.event_type in ("RUN_FAILED", "RUN_CANCELLED")
            and event.run_id == seeded.run_id
        )
        run = get_run(reader, seeded.run_id)
        wait = _read_wait(reader._transaction_runner(), seeded.wait_id)
        assert len(terminal) == 1
        run_row = reader._transaction_runner().run_read(
            lambda transaction: read_run_by_id(transaction, seeded.run_id)
        )
        assert run_row is not None
        assert run_row.terminal_event_id == terminal[0].event_id
        if run.status is RunStatus.FAILED:
            assert wait.status is WaitRecordStatus.FAILED
        else:
            assert run.status is RunStatus.CANCELLED
            assert wait.status is WaitRecordStatus.CANCELLED
    finally:
        reader.close()


def _resolve_failed_worker(
    root: str,
    wait_id: str,
    barrier: _BarrierPort,
) -> None:
    """barrier 后提交 deadline 前 failed result。

    :param root: 测试 durable root。
    :param wait_id: wait id。
    :param barrier: 三方 start barrier。
    :returns: ``None``。
    """

    from dayu.host import resolve_wait

    host = _create_execution_handle(_options(Path(root)))
    try:
        barrier.wait(timeout=5.0)
        try:
            resolve_wait(host, wait_id, _failed_request("race-result"))
        except HostApiError:
            return
    finally:
        host.close()


def _cancel_worker(root: str, run_id: str, barrier: _BarrierPort) -> None:
    """barrier 后提交 waiting cancel。

    :param root: 测试 durable root。
    :param run_id: Run id。
    :param barrier: 三方 start barrier。
    :returns: ``None``。
    """

    host = _create_execution_handle(_options(Path(root)))
    try:
        barrier.wait(timeout=5.0)
        try:
            cancel_run(
                host,
                run_id,
                CancelRunRequest(
                    context=_context("race-cancel"),
                    client_request_id="race-cancel",
                    reason="race_cancel",
                    mode=CancelMode.GRACEFUL,
                ),
            )
        except HostApiError:
            return
    finally:
        host.close()


def _expire_worker(root: str, wait_id: str, barrier: _BarrierPort) -> None:
    """barrier 后提交 deadline 后 expiry。

    :param root: 测试 durable root。
    :param wait_id: wait id。
    :param barrier: 三方 start barrier。
    :returns: ``None``。
    """

    host = _create_execution_handle(_options(Path(root)))
    try:
        barrier.wait(timeout=5.0)
        try:
            expire_wait(
                host,
                ExpireWaitInput(
                    wait_id=wait_id,
                    observed_at=datetime(2026, 5, 16, 4, 0, 0, tzinfo=UTC),
                    actor="race-expiry",
                    source=WaitResolutionSource.POLL,
                ),
            )
        except HostApiError:
            return
    finally:
        host.close()
