"""P10.5 Slice 4 session-level live HostEvent watch 测试。"""

from __future__ import annotations

import asyncio
import pathlib
import sqlite3
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import suppress
from datetime import UTC, datetime
from typing import cast

import pytest

from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import (
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    RunFailedData,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.host import (
    AttemptDispatchSnapshot,
    CancelMode,
    CancelRunRequest,
    CloseSessionRequest,
    EnsureSessionRequest,
    FollowupBehavior,
    Host,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostClosedError,
    HostEvent,
    HostEventKind,
    HostTerminalStatus,
    LocalEngineWorker,
    LocalWorkerHandle,
    OpenHostOptions,
    OperationContext,
    OrdinaryRunExecutionBaseline,
    RunSnapshot,
    RunStatus,
    SubmitFollowupRequest,
    open_host,
)
from dayu.host.api import AuthorizationClaim
from dayu.host.durable.schema import TABLE_EVENT_LOG
from dayu.host.memory import default_memory_projection_policy

_WORKER_MODE_FINAL = "final"
_WORKER_MODE_BLOCKING = "blocking"
_WORKER_MODE_FAILED = "failed"
_WORKER_MODE_EMPTY_FINAL = "empty_final"


class _ImmediateFinalAnswerHandle:
    """测试用立即产出 final answer 的 worker handle。"""

    def __init__(self, snapshot: AttemptDispatchSnapshot) -> None:
        """初始化 handle。

        :param snapshot: 当前 dispatch snapshot。
        :returns: ``None``。
        """

        self._snapshot = snapshot

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker id。

        :returns: 本地 worker id。
        """

        return "watch-final-answer-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """产出 final answer EngineEvent。

        :returns: EngineEvent 异步迭代器。
        """

        yield _final_answer_event(self._snapshot, f"answer:{self._snapshot.run_id}")

    async def close(self) -> None:
        """关闭 handle。

        :returns: ``None``。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """记录取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason


class _BlockingFinalAnswerHandle:
    """测试用受控释放 final answer 的 worker handle。"""

    def __init__(
        self, snapshot: AttemptDispatchSnapshot, release_event: asyncio.Event
    ) -> None:
        """初始化 handle。

        :param snapshot: 当前 dispatch snapshot。
        :param release_event: 控制 final answer 产出的事件。
        :returns: ``None``。
        """

        self._snapshot = snapshot
        self._release_event = release_event
        self.cancel_reasons: list[str] = []

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker id。

        :returns: 本地 worker id。
        """

        return "watch-blocking-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """等待测试释放后产出 final answer。

        :returns: EngineEvent 异步迭代器。
        """

        await self._release_event.wait()
        yield _final_answer_event(self._snapshot, f"released:{self._snapshot.run_id}")

    async def close(self) -> None:
        """关闭 handle。

        :returns: ``None``。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """记录取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        self.cancel_reasons.append(reason)


class _FailedHandle:
    """测试用产出 RUN_FAILED 的 worker handle。"""

    def __init__(self, snapshot: AttemptDispatchSnapshot) -> None:
        """初始化 handle。

        :param snapshot: 当前 dispatch snapshot。
        :returns: ``None``。
        """

        self._snapshot = snapshot

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker id。

        :returns: 本地 worker id。
        """

        return "watch-failed-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """产出 RUN_FAILED EngineEvent。

        :returns: EngineEvent 异步迭代器。
        """

        yield EngineEvent(
            occurred_at=datetime(2026, 5, 18, 1, 2, 4, tzinfo=UTC),
            session_id=self._snapshot.session_id,
            run_id=self._snapshot.run_id,
            type=EngineEventType.RUN_FAILED,
            data=RunFailedData(
                error_code="provider_failed",
                message="provider failed safely",
                provider_request_id=None,
                recoverable=False,
            ),
            metadata=None,
        )

    async def close(self) -> None:
        """关闭 handle。

        :returns: ``None``。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """忽略取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason


class _EmptyFinalAnswerHandle:
    """测试用产出空 final answer 的 worker handle。"""

    def __init__(self, snapshot: AttemptDispatchSnapshot) -> None:
        """初始化 handle。

        :param snapshot: 当前 dispatch snapshot。
        :returns: ``None``。
        """

        self._snapshot = snapshot

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker id。

        :returns: 本地 worker id。
        """

        return "watch-empty-final-answer-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """产出空 final answer EngineEvent。

        :returns: EngineEvent 异步迭代器。
        """

        yield EngineEvent(
            occurred_at=datetime(2026, 5, 18, 1, 2, 5, tzinfo=UTC),
            session_id=self._snapshot.session_id,
            run_id=self._snapshot.run_id,
            type=EngineEventType.FINAL_ANSWER,
            data=FinalAnswerData(
                content="",
                filtered=False,
                degraded=True,
                finish_reason=FinishReason.LENGTH,
            ),
            metadata=None,
        )

    async def close(self) -> None:
        """关闭 handle。

        :returns: ``None``。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """忽略取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason


class _HandleWorker:
    """返回预设 handle 的 worker。"""

    def __init__(self, handle: LocalWorkerHandle) -> None:
        """初始化 worker。

        :param handle: accept 后返回的 worker handle。
        :returns: ``None``。
        """

        self._handle = handle

    async def accept(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> LocalWorkerHandle:
        """接受 dispatch 并返回预设 handle。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: worker handle。
        """

        del snapshot, request
        return self._handle


class _Factory:
    """按 dispatch 顺序创建测试 worker 的 factory。"""

    def __init__(self, mode: str, release_event: asyncio.Event | None = None) -> None:
        """初始化 factory。

        :param mode: worker 行为模式。
        :param release_event: blocking 模式使用的释放事件。
        :returns: ``None``。
        """

        self._mode = mode
        self._release_event = release_event
        self.accepted_event = asyncio.Event()
        self.created_handles: list[LocalWorkerHandle] = []

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建测试 worker。

        :param snapshot: dispatch snapshot。
        :returns: 测试 worker。
        :raises RuntimeError: mode 非法或 blocking 模式未提供释放事件时抛出。
        """

        if self._mode == _WORKER_MODE_FINAL:
            handle: LocalWorkerHandle = _ImmediateFinalAnswerHandle(snapshot)
        elif self._mode == _WORKER_MODE_FAILED:
            handle = _FailedHandle(snapshot)
        elif self._mode == _WORKER_MODE_EMPTY_FINAL:
            handle = _EmptyFinalAnswerHandle(snapshot)
        elif self._mode == _WORKER_MODE_BLOCKING:
            if self._release_event is None:
                raise RuntimeError("blocking mode requires release_event")
            handle = _BlockingFinalAnswerHandle(snapshot, self._release_event)
        else:
            raise RuntimeError("unknown worker mode")
        self.created_handles.append(handle)
        self.accepted_event.set()
        return _HandleWorker(handle)


@pytest.mark.asyncio
async def test_two_watchers_observe_same_terminal_event_and_iterator_continues(
    tmp_path: pathlib.Path,
) -> None:
    """两个 watcher 观察同一 terminal，并且 terminal 不结束 iterator。"""

    factory = _Factory(_WORKER_MODE_FINAL)
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(_ensure_request("watch-two"))
        first_watcher = host.watch_session_events(session.session_id)
        second_watcher = host.watch_session_events(session.session_id)

        await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "followup-1"),
        )
        first_terminal, second_terminal = await asyncio.gather(
            _next_terminal(first_watcher),
            _next_terminal(second_watcher),
        )

        assert first_terminal.event_id == second_terminal.event_id
        assert first_terminal.event_sequence == second_terminal.event_sequence
        assert first_terminal.dedupe_key == second_terminal.dedupe_key
        assert first_terminal.kind is HostEventKind.SUCCEEDED
        assert first_terminal.final_answer is not None
        assert first_terminal.final_answer.content.startswith("answer:")

        await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "followup-2"),
        )
        next_terminal = await _next_terminal(first_watcher)
        assert next_terminal.kind is HostEventKind.SUCCEEDED
        assert next_terminal.event_id != first_terminal.event_id

        await _close_iterator(first_watcher)
        await _close_iterator(second_watcher)


@pytest.mark.asyncio
async def test_consumer_early_cancel_does_not_cancel_run_or_write_eventlog(
    tmp_path: pathlib.Path,
) -> None:
    """consumer 提前取消只关闭订阅，不取消 Run、不写 EventLog。"""

    release_event = asyncio.Event()
    factory = _Factory(_WORKER_MODE_BLOCKING, release_event)
    options = _options(tmp_path, factory)
    async with open_host(options) as host:
        session = await host.ensure_session(_ensure_request("watch-cancel"))
        watcher = host.watch_session_events(session.session_id)
        consumer = asyncio.create_task(_consume_forever(watcher))

        followup = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "followup-blocking"),
        )
        await asyncio.wait_for(factory.accepted_event.wait(), timeout=2.0)
        await _wait_run_status(host, followup.accepted_run_id, RunStatus.RUNNING)
        before_cancel = await _stable_event_log_count(options.db_path)

        consumer.cancel()
        with suppress(asyncio.CancelledError):
            await consumer
        after_cancel = _event_log_count(options.db_path)

        assert after_cancel == before_cancel
        run = await host.get_run(followup.accepted_run_id)
        assert run.status is RunStatus.RUNNING
        blocking_handle = cast(_BlockingFinalAnswerHandle, factory.created_handles[0])
        assert blocking_handle.cancel_reasons == []

        release_event.set()
        terminal = await _wait_run_terminal(host, followup.accepted_run_id)
        assert terminal.status is RunStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_failed_and_cancelled_terminal_events_are_typed(
    tmp_path: pathlib.Path,
) -> None:
    """FAILED / CANCELLED terminal HostEvent 提供 typed status 与展示字段。"""

    failed_factory = _Factory(_WORKER_MODE_FAILED)
    async with open_host(_options(tmp_path / "failed", failed_factory)) as host:
        session = await host.ensure_session(_ensure_request("watch-failed"))
        watcher = host.watch_session_events(session.session_id)
        await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "followup-failed"),
        )
        failed = await _next_terminal(watcher)
        assert failed.kind is HostEventKind.FAILED
        assert failed.terminal_status is HostTerminalStatus.FAILED
        assert failed.error_message == "provider failed safely"
        assert failed.final_answer is None
        await _close_iterator(watcher)

    release_event = asyncio.Event()
    cancel_factory = _Factory(_WORKER_MODE_BLOCKING, release_event)
    async with open_host(_options(tmp_path / "cancelled", cancel_factory)) as host:
        session = await host.ensure_session(_ensure_request("watch-cancelled"))
        watcher = host.watch_session_events(session.session_id)
        await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "followup-active"),
        )
        await asyncio.wait_for(cancel_factory.accepted_event.wait(), timeout=2.0)
        queued = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "followup-queued"),
        )

        await host.cancel_run(
            queued.accepted_run_id,
            CancelRunRequest(
                context=_context("cancel-queued"),
                client_request_id="cancel-queued",
                reason="user_stop_queued",
                mode=CancelMode.GRACEFUL,
            ),
        )
        cancelled = await _next_terminal(watcher)

        assert cancelled.kind is HostEventKind.CANCELLED
        assert cancelled.terminal_status is HostTerminalStatus.CANCELLED
        assert cancelled.cancel_reason == "user_stop_queued"
        assert cancelled.final_answer is None

        release_event.set()
        await _close_iterator(watcher)


@pytest.mark.asyncio
async def test_empty_final_answer_terminal_projects_as_failed_event(
    tmp_path: pathlib.Path,
) -> None:
    """空 final answer 不会写成 public watch 无法读取的 SUCCEEDED event。"""

    factory = _Factory(_WORKER_MODE_EMPTY_FINAL)
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(_ensure_request("watch-empty-final"))
        watcher = host.watch_session_events(session.session_id)
        await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "followup-empty-final"),
        )
        terminal = await _next_terminal(watcher)

    assert terminal.kind is HostEventKind.FAILED
    assert terminal.terminal_status is HostTerminalStatus.FAILED
    assert terminal.final_answer is None
    assert terminal.error_message is not None
    assert "no displayable content" in terminal.error_message


@pytest.mark.asyncio
async def test_watch_lifecycle_errors_and_closed_session_watch(
    tmp_path: pathlib.Path,
) -> None:
    """watch 校验 handle close、missing Session 与 Session CLOSED 语义。"""

    factory = _Factory(_WORKER_MODE_FINAL)
    manager = open_host(_options(tmp_path, factory))
    host = await manager.__aenter__()
    await host.close()
    with pytest.raises(HostClosedError):
        host.watch_session_events("missing-session")
    await manager.__aexit__(None, None, None)

    async with open_host(
        _options(tmp_path / "open", _Factory(_WORKER_MODE_FINAL))
    ) as host:
        with pytest.raises(HostApiError) as exc_info:
            host.watch_session_events("missing-session")
        assert exc_info.value.code is HostApiErrorCode.NOT_FOUND

        session = await host.ensure_session(_ensure_request("watch-closed"))
        await host.close_session(
            session.session_id,
            CloseSessionRequest(
                context=_context("close-session"),
                client_request_id="close-session",
                reason="user_closed_input",
            ),
        )
        watcher = host.watch_session_events(session.session_id)
        await _close_iterator(watcher)


async def _next_terminal(iterator: AsyncIterator[HostEvent]) -> HostEvent:
    """读取下一条 terminal HostEvent。

    :param iterator: HostEvent async iterator。
    :returns: 下一条 terminal HostEvent。
    :raises AssertionError: 超时仍未读取到 terminal 时抛出。
    """

    return await asyncio.wait_for(_read_next_terminal(iterator), timeout=2.0)


async def _read_next_terminal(iterator: AsyncIterator[HostEvent]) -> HostEvent:
    """从 iterator 中顺序读取下一条 terminal 事件。

    :param iterator: HostEvent async iterator。
    :returns: 下一条 terminal HostEvent。
    """

    while True:
        event = await anext(iterator)
        if event.kind in {
            HostEventKind.SUCCEEDED,
            HostEventKind.FAILED,
            HostEventKind.CANCELLED,
        }:
            return event


async def _consume_forever(iterator: AsyncIterator[HostEvent]) -> None:
    """持续消费 watcher，直到调用方取消任务。

    :param iterator: HostEvent async iterator。
    :returns: ``None``。
    :raises asyncio.CancelledError: 调用方取消 consumer task 时抛出。
    """

    async for _event in iterator:
        await asyncio.sleep(0)


async def _close_iterator(iterator: AsyncIterator[HostEvent]) -> None:
    """关闭测试中持有的 async generator iterator。

    :param iterator: HostEvent async iterator。
    :returns: ``None``。
    """

    await cast(AsyncGenerator[HostEvent, None], iterator).aclose()


async def _wait_run_terminal(host: Host, run_id: str) -> RunSnapshot:
    """等待 Run 进入终态。

    :param host: public Host handle。
    :param run_id: 目标 Run id。
    :returns: terminal Run snapshot。
    :raises AssertionError: 超时仍未进入终态时抛出。
    """

    for _ in range(200):
        snapshot = await host.get_run(run_id)
        if snapshot.status in {
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }:
            return snapshot
        await asyncio.sleep(0.01)
    raise AssertionError(f"run {run_id} did not reach terminal status")


async def _wait_run_status(
    host: Host, run_id: str, expected_status: RunStatus
) -> RunSnapshot:
    """等待 Run 到达指定状态。

    :param host: public Host handle。
    :param run_id: 目标 Run id。
    :param expected_status: 期待状态。
    :returns: 匹配状态的 Run snapshot。
    :raises AssertionError: 超时仍未到达期待状态时抛出。
    """

    for _ in range(200):
        snapshot = await host.get_run(run_id)
        if snapshot.status is expected_status:
            return snapshot
        await asyncio.sleep(0.01)
    raise AssertionError(
        f"run {run_id} did not reach {expected_status.value} status"
    )


def _event_log_count(db_path: pathlib.Path) -> int:
    """读取 EventLog row 数量。

    :param db_path: Host durable SQLite 路径。
    :returns: EventLog row 数量。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            f"SELECT COUNT(*) FROM {TABLE_EVENT_LOG}"
        ).fetchone()
    if row is None:
        raise AssertionError("EventLog count query returned no row")
    value = row[0]
    if not isinstance(value, int):
        raise AssertionError("EventLog count is not int")
    return value


async def _stable_event_log_count(db_path: pathlib.Path) -> int:
    """等待 EventLog 计数在短窗口内稳定。

    :param db_path: Host durable SQLite 路径。
    :returns: 稳定后的 EventLog row 数量。
    :raises AssertionError: 计数持续变化时抛出。
    """

    previous = _event_log_count(db_path)
    for _ in range(20):
        await asyncio.sleep(0.02)
        current = _event_log_count(db_path)
        if current == previous:
            return current
        previous = current
    raise AssertionError("EventLog count did not become stable")


def _final_answer_event(snapshot: AttemptDispatchSnapshot, content: str) -> EngineEvent:
    """构造 final answer EngineEvent。

    :param snapshot: 当前 dispatch snapshot。
    :param content: final answer 内容。
    :returns: EngineEvent。
    """

    return EngineEvent(
        occurred_at=datetime(2026, 5, 18, 1, 2, 3, tzinfo=UTC),
        session_id=snapshot.session_id,
        run_id=snapshot.run_id,
        type=EngineEventType.FINAL_ANSWER,
        data=FinalAnswerData(
            content=content,
            filtered=False,
            degraded=False,
            finish_reason=FinishReason.STOP,
        ),
        metadata=None,
    )


def _options(tmp_path: pathlib.Path, worker_factory: _Factory) -> OpenHostOptions:
    """构造测试用 OpenHostOptions。

    :param tmp_path: pytest 临时目录。
    :param worker_factory: 测试 worker factory。
    :returns: OpenHostOptions。
    """

    return OpenHostOptions(
        db_path=tmp_path / "host.sqlite3",
        artifact_root=tmp_path / "artifacts",
        create_parent_dirs=True,
        sqlite_busy_timeout_seconds=1.0,
        sqlite_write_busy_retry_count=8,
        sqlite_write_retry_initial_delay_seconds=0.001,
        sqlite_write_retry_backoff_multiplier=1.2,
        sqlite_write_retry_max_delay_seconds=0.02,
        payload_inline_threshold_bytes=4096,
        lane_db_path=tmp_path / "lane.sqlite3",
        lane_name="llm",
        lane_capacity=1,
        lane_default_timeout_seconds=0.2,
        lane_claim_ttl_seconds=1.0,
        lane_heartbeat_interval_seconds=0.1,
        worker_startup_timeout_seconds=1.0,
        dispatch_poll_interval_seconds=0.01,
        ordinary_run_baseline=OrdinaryRunExecutionBaseline(
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
            ),
        ),
        worker_factory=worker_factory,
        tooling_options=None,
        context_budget_policy=None,
        compactor_runner_baseline=None,
        memory_projection_policy=default_memory_projection_policy(),
        memory_projection_catchup_batch_size=128,
        enable_truncation_manager=True,
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
        supports_tool_calling=False,
        supports_streaming=False,
        supports_stream_usage=False,
        default_timeout_seconds=1.0,
        max_retries=0,
        provider_request=None,
    )


def _ensure_request(slot_key: str) -> EnsureSessionRequest:
    """构造 ensure session 请求。

    :param slot_key: session slot key。
    :returns: EnsureSessionRequest。
    """

    return EnsureSessionRequest(
        scope="workspace",
        slot_key=slot_key,
        metadata=(),
    )


def _followup_request(
    session_id: str,
    client_request_id: str,
) -> SubmitFollowupRequest:
    """构造 follow-up queue 请求。

    :param session_id: 目标 Session id。
    :param client_request_id: 幂等请求 id。
    :returns: SubmitFollowupRequest。
    """

    return SubmitFollowupRequest(
        context=_context(client_request_id),
        session_id=session_id,
        client_request_id=client_request_id,
        system_prompt=None,
        user_prompt="请给出 deterministic answer",
        tool_names=None,
        runner_spec=None,
        runner_options=None,
        agent_policy=None,
        behavior=FollowupBehavior.QUEUE,
        target_run_id=None,
    )


def _context(request_id: str) -> HostCallContext:
    """构造 Host 调用上下文。

    :param request_id: 请求 id。
    :returns: HostCallContext。
    """

    return HostCallContext(
        actor="analyst",
        source="pytest",
        request_id=request_id,
        authorization_claims=(AuthorizationClaim(name="role", value="research"),),
        operation_context=OperationContext(
            operation_name="watch_session_events",
            operation_kind="unit_test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="p10_5_slice4",
            correlation_id="corr-watch-session-events",
        ),
    )
