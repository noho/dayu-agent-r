"""``dayu.service.entrypoint_runtime`` Service 边界测试。"""

from __future__ import annotations

import ast
import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from dayu.host.api import (
    CancelMode,
    CancelRunRequest,
    CreateSessionRequest,
    EnsureSessionRequest,
    FollowupBehavior,
    FollowupSnapshot,
    Host,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostEvent,
    HostEventKind,
    HostFinalAnswerView,
    HostStreamCursor,
    HostTerminalStatus,
    OperationContext,
    OutboxProjectionStatus,
    OutboxTerminalCursor,
    OutboxTerminalItem,
    OutboxTerminalItemsBatch,
    OutboxTerminalItemState,
    ReadOutboxTerminalItemsRequest,
    RunSnapshot,
    RunStatus,
    SessionSlotRef,
    SessionSnapshot,
    SessionStatus,
    SubmitFollowupRequest,
)
from dayu.service.entrypoint_runtime import (
    EntrypointCancelRequest,
    EntrypointRuntimeRequest,
    EntrypointRuntimeResult,
    EntrypointRuntimeError,
    EntrypointTerminalSource,
    EntrypointTurnRequest,
    cancel_entrypoint_run_and_wait,
    ensure_or_create_entrypoint_session,
    prepare_entrypoint_runtime,
    submit_entrypoint_turn_and_wait,
    _close_watcher,
)
from dayu.service.host_assembly import ServiceAssemblyOverrides, ServiceRunOverrides

_PACKAGE_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "dayu" / "config"
_NOW = datetime(2026, 6, 14, 8, 0, 0, tzinfo=UTC)
_MODEL_ID = "deepseek-v4-flash"
_RUNNER_HINT_ID = "interactive"
_API_KEY = "test-provider-key"


@dataclass(frozen=True, slots=True)
class _StopSignal:
    """测试 watcher 停止信号。"""


@dataclass(frozen=True, slots=True)
class _RaiseSignal:
    """测试 watcher 抛错信号。"""

    error: Exception


class _FakeHostEventIterator:
    """测试用可关闭 HostEvent iterator。"""

    closed_count: int
    _close_error: BaseException | None
    _queue: asyncio.Queue[HostEvent | _StopSignal | _RaiseSignal]

    def __init__(self, *, close_error: BaseException | None = None) -> None:
        """初始化测试 watcher。

        :param close_error: ``aclose`` 应抛出的测试异常；``None`` 表示正常关闭。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.closed_count = 0
        self._close_error = close_error
        self._queue = asyncio.Queue()

    def __aiter__(self) -> AsyncIterator[HostEvent]:
        """返回自身作为 async iterator。

        :returns: HostEvent async iterator。
        :raises Exception: 不主动抛出异常。
        """

        return self

    async def __anext__(self) -> HostEvent:
        """读取下一条测试事件。

        :returns: 下一条 HostEvent。
        :raises StopAsyncIteration: 收到停止信号时抛出。
        """

        item = await self._queue.get()
        if isinstance(item, _StopSignal):
            raise StopAsyncIteration
        if isinstance(item, _RaiseSignal):
            raise item.error
        return item

    async def push(self, event: HostEvent) -> None:
        """向 watcher 推入测试事件。

        :param event: 待推入事件。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        await self._queue.put(event)

    async def fail(self, error: Exception) -> None:
        """向 watcher 推入测试异常。

        :param error: watcher drain 应观察到的异常。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        await self._queue.put(_RaiseSignal(error=error))

    async def aclose(self) -> None:
        """关闭测试 watcher。

        :returns: ``None``。
        :raises BaseException: 配置了 ``close_error`` 时抛出该异常。
        """

        self.closed_count += 1
        if self._close_error is not None:
            raise self._close_error
        await self._queue.put(_StopSignal())


class _FakeHost:
    """测试用 Host public API 替身。"""

    calls: list[str]
    watchers: list[_FakeHostEventIterator]
    submit_requests: list[SubmitFollowupRequest]
    cancel_requests: list[CancelRunRequest]
    ensure_requests: list[EnsureSessionRequest]
    create_requests: list[CreateSessionRequest]
    read_outbox_requests: list[ReadOutboxTerminalItemsRequest]
    _submit_events: tuple[HostEvent, ...]
    _submit_watcher_errors: tuple[Exception, ...]
    _cancel_events: tuple[HostEvent, ...]
    _cancel_error: HostApiError | None
    _run_statuses: tuple[RunStatus, ...]
    _outbox_batches: tuple[OutboxTerminalItemsBatch, ...]
    _run_status_index: int
    _outbox_index: int

    def __init__(
        self,
        *,
        submit_events: tuple[HostEvent, ...] = (),
        submit_watcher_errors: tuple[Exception, ...] = (),
        cancel_events: tuple[HostEvent, ...] = (),
        cancel_error: HostApiError | None = None,
        run_statuses: tuple[RunStatus, ...] = (RunStatus.SUCCEEDED,),
        outbox_batches: tuple[OutboxTerminalItemsBatch, ...] = (),
    ) -> None:
        """初始化测试 Host。

        :param submit_events: submit_followup 时推入 watcher 的事件。
        :param submit_watcher_errors: submit_followup 时推入 watcher 的异常。
        :param cancel_events: cancel_run 时推入 watcher 的事件。
        :param cancel_error: cancel_run 应抛出的 Host API 错误。
        :param run_statuses: get_run 依次返回的 RunStatus。
        :param outbox_batches: read_outbox_terminal_items 依次返回的批次。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.calls = []
        self.watchers = []
        self.submit_requests = []
        self.cancel_requests = []
        self.ensure_requests = []
        self.create_requests = []
        self.read_outbox_requests = []
        self._submit_events = submit_events
        self._submit_watcher_errors = submit_watcher_errors
        self._cancel_events = cancel_events
        self._cancel_error = cancel_error
        self._run_statuses = run_statuses
        self._outbox_batches = outbox_batches
        self._run_status_index = 0
        self._outbox_index = 0

    async def ensure_session(self, request: EnsureSessionRequest) -> SessionSnapshot:
        """记录 ensure_session 调用并返回测试 Session。

        :param request: ensure session 请求。
        :returns: Session snapshot。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append("ensure_session")
        self.ensure_requests.append(request)
        return _session_snapshot(session_id="session-1", slot_key=request.slot_key)

    async def create_session(self, request: CreateSessionRequest) -> SessionSnapshot:
        """记录 create_session 调用并返回测试 Session。

        :param request: create session 请求。
        :returns: Session snapshot。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append("create_session")
        self.create_requests.append(request)
        return _session_snapshot(session_id="session-created", slot_key=request.slot_key)

    def watch_session_events(self, session_id: str) -> AsyncIterator[HostEvent]:
        """记录 watcher attach 并返回测试 iterator。

        :param session_id: 目标 Session id。
        :returns: HostEvent async iterator。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(f"watch:{session_id}")
        watcher = _FakeHostEventIterator()
        self.watchers.append(watcher)
        return watcher

    async def submit_followup(self, session_id: str, request: SubmitFollowupRequest) -> FollowupSnapshot:
        """记录 submit_followup，并在返回前推入预设事件。

        :param session_id: 目标 Session id。
        :param request: submit follow-up 请求。
        :returns: follow-up snapshot。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(f"submit:{session_id}")
        self.submit_requests.append(request)
        for event in self._submit_events:
            await self.watchers[-1].push(event)
        for error in self._submit_watcher_errors:
            await self.watchers[-1].fail(error)
        if self._submit_events or self._submit_watcher_errors:
            await asyncio.sleep(0)
        return FollowupSnapshot(
            accepted_input_ref="input-1",
            behavior=FollowupBehavior.QUEUE,
            accepted_run_id="run-1",
            accepted_run_status=RunStatus.RUNNING,
            command_watermark=HostStreamCursor(event_sequence=1),
            queued_run_id=None,
            target_run_id=None,
        )

    async def get_run(self, run_id: str) -> RunSnapshot:
        """按预设状态返回 Run snapshot。

        :param run_id: 目标 Run id。
        :returns: Run snapshot。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(f"get_run:{run_id}")
        status_index = min(self._run_status_index, len(self._run_statuses) - 1)
        status = self._run_statuses[status_index]
        self._run_status_index += 1
        return _run_snapshot(run_id=run_id, status=status)

    async def read_outbox_terminal_items(
        self,
        session_id: str,
        request: ReadOutboxTerminalItemsRequest,
    ) -> OutboxTerminalItemsBatch:
        """按预设批次返回 outbox terminal items。

        :param session_id: 目标 Session id。
        :param request: outbox read 请求。
        :returns: outbox terminal batch。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(f"read_outbox:{session_id}")
        self.read_outbox_requests.append(request)
        if not self._outbox_batches:
            return _outbox_batch(
                items=(),
                next_sequence=request.after.event_sequence,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            )
        batch_index = min(self._outbox_index, len(self._outbox_batches) - 1)
        self._outbox_index += 1
        return self._outbox_batches[batch_index]

    async def cancel_run(self, run_id: str, request: CancelRunRequest) -> RunSnapshot:
        """记录 cancel_run，并在返回前推入预设事件。

        :param run_id: 目标 Run id。
        :param request: cancel run 请求。
        :returns: Run snapshot。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(f"cancel:{run_id}")
        self.cancel_requests.append(request)
        if self._cancel_error is not None:
            raise self._cancel_error
        for event in self._cancel_events:
            await self.watchers[-1].push(event)
        if self._cancel_events:
            await asyncio.sleep(0)
        return _run_snapshot(run_id=run_id, status=RunStatus.CANCELLING)


class _SleepRecorder:
    """测试用 sleep coroutine 记录器。"""

    calls: list[float]

    def __init__(self) -> None:
        """初始化 sleep 调用记录。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.calls = []

    async def __call__(self, seconds: float) -> None:
        """记录 sleep 秒数并让出事件循环。

        :param seconds: sleep 秒数。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(seconds)
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_prepare_entrypoint_runtime_assembles_scene_tools_and_host(
    tmp_path: Path,
) -> None:
    """prepare helper 应完成 location、config、scene、tools 与 Host assembly。"""

    result = await _prepare_runtime(tmp_path)

    assert isinstance(result, EntrypointRuntimeResult)
    assert result.locations.config_overlay_dir == tmp_path / "workspace" / "config"
    assert result.scene_inputs.tool_selection.tool_names == frozenset({"record_smoke_fact"})
    assert result.host_assembly.options.ordinary_run_baseline.runner_options.stream is True


@pytest.mark.asyncio
async def test_ensure_or_create_entrypoint_session_uses_host_public_requests() -> None:
    """session helper 必须只构造 Host public ensure/create request。"""

    fake_host = _FakeHost()
    host = cast(Host, fake_host)

    ensured = await ensure_or_create_entrypoint_session(
        host,
        create_new=False,
        bind_slot=True,
        scope="cli.prompt",
        slot_key="label-1",
        metadata=(),
    )
    created = await ensure_or_create_entrypoint_session(
        host,
        create_new=True,
        bind_slot=True,
        scope="cli.prompt",
        slot_key="label-1",
        metadata=(),
        create_context=_host_context("create-context"),
        create_client_request_id="create-request-1",
    )

    assert ensured.session_id == "session-1"
    assert created.session_id == "session-created"
    assert fake_host.ensure_requests[0].scope == "cli.prompt"
    assert fake_host.create_requests[0].client_request_id == "create-request-1"
    assert fake_host.calls == ["ensure_session", "create_session"]


@pytest.mark.asyncio
async def test_ensure_or_create_entrypoint_session_rejects_create_without_context() -> None:
    """create session 路径缺 create_context 时必须抛 ValueError。"""

    fake_host = _FakeHost()

    with pytest.raises(ValueError, match="create_context"):
        await ensure_or_create_entrypoint_session(
            cast(Host, fake_host),
            create_new=True,
            bind_slot=True,
            scope="cli.prompt",
            slot_key="label-1",
            metadata=(),
            create_context=None,
            create_client_request_id="create-request-1",
        )

    assert fake_host.calls == []


@pytest.mark.asyncio
async def test_ensure_or_create_entrypoint_session_rejects_create_without_request_id() -> None:
    """create session 路径缺 create_client_request_id 时必须抛 ValueError。"""

    fake_host = _FakeHost()

    with pytest.raises(ValueError, match="create_client_request_id"):
        await ensure_or_create_entrypoint_session(
            cast(Host, fake_host),
            create_new=True,
            bind_slot=True,
            scope="cli.prompt",
            slot_key="label-1",
            metadata=(),
            create_context=_host_context("create-context"),
            create_client_request_id=None,
        )

    assert fake_host.calls == []


@pytest.mark.asyncio
async def test_ensure_or_create_entrypoint_session_rejects_ensure_without_scope() -> None:
    """ensure session 路径缺 scope 时必须抛 ValueError。"""

    fake_host = _FakeHost()

    with pytest.raises(ValueError, match="scope"):
        await ensure_or_create_entrypoint_session(
            cast(Host, fake_host),
            create_new=False,
            bind_slot=True,
            scope=None,
            slot_key="label-1",
            metadata=(),
        )

    assert fake_host.calls == []


@pytest.mark.asyncio
async def test_ensure_or_create_entrypoint_session_rejects_ensure_without_slot_key() -> None:
    """ensure session 路径缺 slot_key 时必须抛 ValueError。"""

    fake_host = _FakeHost()

    with pytest.raises(ValueError, match="slot_key"):
        await ensure_or_create_entrypoint_session(
            cast(Host, fake_host),
            create_new=False,
            bind_slot=True,
            scope="cli.prompt",
            slot_key=None,
            metadata=(),
        )

    assert fake_host.calls == []


@pytest.mark.asyncio
async def test_submit_entrypoint_turn_attaches_watcher_before_submit_and_returns_live_terminal(
    tmp_path: Path,
) -> None:
    """submit helper 必须先 attach watcher，再提交并返回 live terminal。"""

    runtime = await _prepare_runtime(tmp_path)
    terminal_event = _terminal_event(event_sequence=2, run_id="run-1")
    fake_host = _FakeHost(submit_events=(terminal_event,))

    result = await submit_entrypoint_turn_and_wait(
        cast(Host, fake_host),
        request=_turn_request(),
        scene_inputs=runtime.scene_inputs,
        host_assembly=runtime.host_assembly,
    )

    assert result.source is EntrypointTerminalSource.LIVE_EVENT
    assert result.final_answer is not None
    assert result.final_answer.content == "answer for run-1"
    assert fake_host.calls == ["watch:session-1", "submit:session-1"]
    assert fake_host.watchers[0].closed_count == 1
    assert fake_host.submit_requests[0].runner_options is not None
    assert fake_host.submit_requests[0].agent_policy is not None


@pytest.mark.asyncio
async def test_submit_entrypoint_turn_filters_unrelated_terminal(
    tmp_path: Path,
) -> None:
    """同一 Session 中其它 Run 的 terminal 不得结束当前 turn。"""

    runtime = await _prepare_runtime(tmp_path)
    fake_host = _FakeHost(
        submit_events=(
            _terminal_event(event_sequence=2, run_id="other-run"),
            _terminal_event(event_sequence=3, run_id="run-1"),
        )
    )

    result = await submit_entrypoint_turn_and_wait(
        cast(Host, fake_host),
        request=_turn_request(),
        scene_inputs=runtime.scene_inputs,
        host_assembly=runtime.host_assembly,
    )

    assert result.run_id == "run-1"
    assert result.event_sequence == 3


@pytest.mark.asyncio
async def test_submit_entrypoint_turn_uses_outbox_when_live_terminal_missing(
    tmp_path: Path,
) -> None:
    """get_run 已终态但 watcher 未给 terminal 时必须用 public outbox 补读。"""

    runtime = await _prepare_runtime(tmp_path)
    outbox_item = _outbox_item(event_sequence=5, run_id="run-1")
    fake_host = _FakeHost(
        run_statuses=(RunStatus.SUCCEEDED,),
        outbox_batches=(
            _outbox_batch(
                items=(outbox_item,),
                next_sequence=5,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
        ),
    )

    result = await submit_entrypoint_turn_and_wait(
        cast(Host, fake_host),
        request=_turn_request(),
        scene_inputs=runtime.scene_inputs,
        host_assembly=runtime.host_assembly,
    )

    assert result.source is EntrypointTerminalSource.OUTBOX_READ
    assert result.terminal_event_id == "terminal-run-1-5"
    read_request = fake_host.read_outbox_requests[0]
    assert read_request.after == OutboxTerminalCursor(event_sequence=0)
    assert read_request.seen_terminal_event_ids == ()
    assert read_request.limit == 50


@pytest.mark.asyncio
async def test_submit_entrypoint_turn_records_watcher_failure_and_uses_outbox(
    tmp_path: Path,
) -> None:
    """watcher 失败后必须带诊断并仍可通过 public outbox 返回终态。"""

    runtime = await _prepare_runtime(tmp_path)
    outbox_item = _outbox_item(event_sequence=9, run_id="run-1")
    fake_host = _FakeHost(
        submit_watcher_errors=(RuntimeError("watch stream disconnected"),),
        run_statuses=(RunStatus.SUCCEEDED,),
        outbox_batches=(
            _outbox_batch(
                items=(outbox_item,),
                next_sequence=9,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
        ),
    )

    result = await submit_entrypoint_turn_and_wait(
        cast(Host, fake_host),
        request=_turn_request(),
        scene_inputs=runtime.scene_inputs,
        host_assembly=runtime.host_assembly,
    )

    assert result.source is EntrypointTerminalSource.OUTBOX_READ
    assert result.terminal_event_id == "terminal-run-1-9"
    assert result.watcher_failure_message is not None
    assert "RuntimeError" in result.watcher_failure_message
    assert "watch stream disconnected" in result.watcher_failure_message
    assert fake_host.read_outbox_requests[0].after == OutboxTerminalCursor(event_sequence=0)


@pytest.mark.asyncio
async def test_submit_entrypoint_turn_reads_outbox_pages_until_target(
    tmp_path: Path,
) -> None:
    """outbox fallback 必须按 has_more 分页推进直到命中目标 Run。"""

    runtime = await _prepare_runtime(tmp_path)
    fake_host = _FakeHost(
        run_statuses=(RunStatus.SUCCEEDED,),
        outbox_batches=(
            _outbox_batch(
                items=(_outbox_item(event_sequence=4, run_id="other-run"),),
                next_sequence=4,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
                has_more=True,
            ),
            _outbox_batch(
                items=(_outbox_item(event_sequence=8, run_id="run-1"),),
                next_sequence=8,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
        ),
    )

    result = await submit_entrypoint_turn_and_wait(
        cast(Host, fake_host),
        request=_turn_request(),
        scene_inputs=runtime.scene_inputs,
        host_assembly=runtime.host_assembly,
    )

    assert result.run_id == "run-1"
    assert fake_host.read_outbox_requests[0].after == OutboxTerminalCursor(event_sequence=0)
    assert fake_host.read_outbox_requests[1].after == OutboxTerminalCursor(event_sequence=4)


@pytest.mark.asyncio
async def test_submit_entrypoint_turn_retries_when_outbox_lagged(
    tmp_path: Path,
) -> None:
    """outbox LAGGED 且未命中时不能视为完整，必须继续轮询。"""

    runtime = await _prepare_runtime(tmp_path)
    sleep = _SleepRecorder()
    fake_host = _FakeHost(
        run_statuses=(RunStatus.SUCCEEDED, RunStatus.SUCCEEDED),
        outbox_batches=(
            _outbox_batch(
                items=(),
                next_sequence=0,
                projection_status=OutboxProjectionStatus.LAGGED,
            ),
            _outbox_batch(
                items=(_outbox_item(event_sequence=6, run_id="run-1"),),
                next_sequence=6,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
        ),
    )

    result = await submit_entrypoint_turn_and_wait(
        cast(Host, fake_host),
        request=_turn_request(),
        scene_inputs=runtime.scene_inputs,
        host_assembly=runtime.host_assembly,
        sleep=sleep,
    )

    assert result.run_id == "run-1"
    assert sleep.calls == [0.05]


@pytest.mark.asyncio
async def test_submit_entrypoint_turn_raises_on_outbox_projection_failed(
    tmp_path: Path,
) -> None:
    """outbox projection FAILED 必须转为 Service error。"""

    runtime = await _prepare_runtime(tmp_path)
    fake_host = _FakeHost(
        run_statuses=(RunStatus.SUCCEEDED,),
        outbox_batches=(
            _outbox_batch(
                items=(),
                next_sequence=0,
                projection_status=OutboxProjectionStatus.FAILED,
                projection_error_code="projection_failed",
                projection_error_message="projection stopped",
            ),
        ),
    )

    with pytest.raises(EntrypointRuntimeError, match="projection_failed"):
        await submit_entrypoint_turn_and_wait(
            cast(Host, fake_host),
            request=_turn_request(),
            scene_inputs=runtime.scene_inputs,
            host_assembly=runtime.host_assembly,
        )


@pytest.mark.asyncio
async def test_submit_entrypoint_turn_raises_when_caught_up_without_match(
    tmp_path: Path,
) -> None:
    """Run 已终态且 outbox 追平仍无目标 terminal 时必须报 contract error。"""

    runtime = await _prepare_runtime(tmp_path)
    fake_host = _FakeHost(
        run_statuses=(RunStatus.SUCCEEDED,),
        outbox_batches=(
            _outbox_batch(
                items=(),
                next_sequence=0,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
        ),
    )

    with pytest.raises(EntrypointRuntimeError, match="caught up without"):
        await submit_entrypoint_turn_and_wait(
            cast(Host, fake_host),
            request=_turn_request(),
            scene_inputs=runtime.scene_inputs,
            host_assembly=runtime.host_assembly,
        )


@pytest.mark.asyncio
async def test_cancel_entrypoint_run_attaches_watcher_before_cancel_and_waits_terminal() -> None:
    """cancel helper 必须 attach watcher 后构造 public CancelRunRequest。"""

    cancel_terminal = _terminal_event(
        event_sequence=7,
        run_id="run-1",
        terminal_status=HostTerminalStatus.CANCELLED,
    )
    fake_host = _FakeHost(
        cancel_events=(cancel_terminal,),
        run_statuses=(RunStatus.RUNNING,),
    )
    cancel_request = EntrypointCancelRequest(
        context=_host_context("cancel-context"),
        run_id="run-1",
        client_request_id="cancel-request-1",
        reason="cli_sigint",
        mode=CancelMode.GRACEFUL,
    )

    result = await cancel_entrypoint_run_and_wait(
        cast(Host, fake_host),
        request=cancel_request,
    )

    assert result.terminal_status is HostTerminalStatus.CANCELLED
    assert fake_host.calls == [
        "get_run:run-1",
        "watch:session-1",
        "cancel:run-1",
    ]
    host_cancel_request = fake_host.cancel_requests[0]
    assert host_cancel_request.client_request_id == "cancel-request-1"
    assert host_cancel_request.reason == "cli_sigint"
    assert host_cancel_request.mode is CancelMode.GRACEFUL
    assert host_cancel_request.context == cancel_request.context
    assert fake_host.watchers[0].closed_count == 1


@pytest.mark.asyncio
async def test_cancel_entrypoint_run_skips_cancel_when_initial_snapshot_is_terminal() -> None:
    """初始 get_run 已终态时应跳过 cancel_run 并通过 public outbox 返回终态。"""

    fake_host = _FakeHost(
        run_statuses=(RunStatus.SUCCEEDED,),
        outbox_batches=(
            _outbox_batch(
                items=(_outbox_item(event_sequence=10, run_id="run-1"),),
                next_sequence=10,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
        ),
    )

    result = await cancel_entrypoint_run_and_wait(
        cast(Host, fake_host),
        request=_cancel_request(),
    )

    assert result.source is EntrypointTerminalSource.OUTBOX_READ
    assert result.event_sequence == 10
    assert fake_host.cancel_requests == []
    assert fake_host.watchers == []
    assert fake_host.calls == ["get_run:run-1", "get_run:run-1", "read_outbox:session-1"]


@pytest.mark.asyncio
async def test_cancel_entrypoint_run_continues_wait_when_cancel_loses_terminal_race() -> None:
    """cancel_run 与终态竞争失败时应保留 watcher 并继续用 public outbox 补读。"""

    fake_host = _FakeHost(
        cancel_error=HostApiError(
            code=HostApiErrorCode.INVALID_STATE,
            message="run already terminal",
            retryable=False,
        ),
        run_statuses=(RunStatus.RUNNING, RunStatus.SUCCEEDED),
        outbox_batches=(
            _outbox_batch(
                items=(_outbox_item(event_sequence=11, run_id="run-1"),),
                next_sequence=11,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
        ),
    )

    result = await cancel_entrypoint_run_and_wait(
        cast(Host, fake_host),
        request=_cancel_request(),
    )

    assert result.source is EntrypointTerminalSource.OUTBOX_READ
    assert result.event_sequence == 11
    assert len(fake_host.cancel_requests) == 1
    assert fake_host.watchers[0].closed_count == 1
    assert fake_host.calls == [
        "get_run:run-1",
        "watch:session-1",
        "cancel:run-1",
        "get_run:run-1",
        "get_run:run-1",
        "read_outbox:session-1",
    ]


@pytest.mark.asyncio
async def test_close_watcher_cancels_and_awaits_drain_when_aclose_is_cancelled() -> None:
    """watcher aclose 被取消时仍必须 cancel 并回收 drain task。"""

    watcher = _FakeHostEventIterator(close_error=asyncio.CancelledError())
    drain_cancel_observed = asyncio.Event()
    drain_task = asyncio.create_task(_wait_until_cancelled(drain_cancel_observed))
    await asyncio.sleep(0)

    with pytest.raises(asyncio.CancelledError):
        await _close_watcher(watcher=watcher, drain_task=drain_task)

    assert watcher.closed_count == 1
    assert drain_cancel_observed.is_set()
    assert drain_task.done()
    assert drain_task.cancelled()


@pytest.mark.asyncio
async def test_close_watcher_cancels_and_awaits_drain_when_aclose_fails() -> None:
    """watcher aclose 普通异常应透传，且 drain task 仍被回收。"""

    close_error = RuntimeError("watcher close failed")
    watcher = _FakeHostEventIterator(close_error=close_error)
    drain_cancel_observed = asyncio.Event()
    drain_task = asyncio.create_task(_wait_until_cancelled(drain_cancel_observed))
    await asyncio.sleep(0)

    with pytest.raises(RuntimeError, match="watcher close failed") as exc_info:
        await _close_watcher(watcher=watcher, drain_task=drain_task)

    assert exc_info.value is close_error
    assert watcher.closed_count == 1
    assert drain_cancel_observed.is_set()
    assert drain_task.done()
    assert drain_task.cancelled()


def test_entrypoint_runtime_does_not_import_engine_internals() -> None:
    """entrypoint runtime 不应导入 Engine 内部或 CLI-only 模块。"""

    source_path = Path(__file__).resolve().parents[2] / "dayu" / "service" / "entrypoint_runtime.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.append(node.module)

    assert "dayu.engine" not in imported_modules
    assert "dayu.cli" not in imported_modules


async def _wait_until_cancelled(cancel_observed: asyncio.Event) -> None:
    """等待 task 被取消，并记录取消已被 drain task 观察到。

    :param cancel_observed: 记录取消观察结果的事件。
    :returns: ``None``。
    :raises asyncio.CancelledError: 当前 task 被取消时透传。
    """

    blocker = asyncio.Event()
    try:
        await blocker.wait()
    except asyncio.CancelledError:
        cancel_observed.set()
        raise


async def _prepare_runtime(tmp_path: Path) -> EntrypointRuntimeResult:
    """构造真实 entrypoint runtime assembly 测试结果。

    :param tmp_path: pytest 临时 workspace root。
    :returns: entrypoint runtime result。
    :raises Exception: runtime assembly 失败时向上抛出。
    """

    _write_tool_discovery_overlay(tmp_path)
    return await prepare_entrypoint_runtime(
        EntrypointRuntimeRequest(
            workspace_root=tmp_path,
            package_config_root=_PACKAGE_CONFIG_ROOT,
            explicit_config_dir=None,
            scene_id="smoke_host_public_multiturn",
            context_slot_values={
                "fins_default_subject": "测试财报主体",
                "base_user": "service-entrypoint-test",
            },
            assembly_overrides=ServiceAssemblyOverrides(
                host_runtime_id="local",
                execution_profile_id="standard-256k",
                model_id=_MODEL_ID,
                runner_option_hint_id=_RUNNER_HINT_ID,
            ),
            env={"DEEPSEEK_API_KEY": _API_KEY},
        )
    )


def _write_tool_discovery_overlay(workspace_root: Path) -> None:
    """写入启用 smoke provider 的 workspace tool discovery overlay。

    :param workspace_root: pytest 临时 workspace root。
    :returns: ``None``。
    :raises OSError: 目录或文件写入失败时抛出。
    """

    target_path = workspace_root / "workspace" / "config" / "tool_discovery.json"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        json.dumps(
            {
                "providers": {
                    "financial-tools": {
                        "import_path": ("utils.smoke_host_public_multiturn:discover_smoke_tools"),
                        "entry_point": None,
                        "source_kind": "config_binding",
                        "source_id": "utils.smoke_host_public_multiturn",
                        "enabled": True,
                        "allow_empty": False,
                        "config": {},
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _turn_request() -> EntrypointTurnRequest:
    """构造默认 entrypoint turn request。

    :returns: entrypoint turn request。
    :raises Exception: 不主动抛出异常。
    """

    return EntrypointTurnRequest(
        context=_host_context("submit-context"),
        session_id="session-1",
        client_request_id="submit-request-1",
        user_prompt="请总结。",
        tool_names=frozenset({"record_smoke_fact"}),
        behavior=FollowupBehavior.QUEUE,
        target_run_id=None,
        run_overrides=ServiceRunOverrides(temperature=0.2),
    )


def _cancel_request() -> EntrypointCancelRequest:
    """构造默认 entrypoint cancel request。

    :returns: entrypoint cancel request。
    :raises Exception: 不主动抛出异常。
    """

    return EntrypointCancelRequest(
        context=_host_context("cancel-context"),
        run_id="run-1",
        client_request_id="cancel-request-1",
        reason="cli_sigint",
        mode=CancelMode.GRACEFUL,
    )


def _host_context(request_id: str) -> HostCallContext:
    """构造测试 HostCallContext。

    :param request_id: request id。
    :returns: HostCallContext。
    :raises Exception: 不主动抛出异常。
    """

    return HostCallContext(
        actor="service-test",
        source="service-entrypoint-test",
        request_id=request_id,
        authorization_claims=(),
        operation_context=OperationContext(
            operation_name="service_entrypoint.test",
            operation_kind="service_entrypoint_test",
            business_domain="fins",
            business_object_type=None,
            business_object_id=None,
            scenario="smoke_host_public_multiturn",
            correlation_id="correlation-1",
        ),
    )


def _session_snapshot(*, session_id: str, slot_key: str | None) -> SessionSnapshot:
    """构造测试 SessionSnapshot。

    :param session_id: Session id。
    :param slot_key: slot key。
    :returns: SessionSnapshot。
    :raises Exception: 不主动抛出异常。
    """

    slot = None
    if slot_key is not None:
        slot = SessionSlotRef(scope="cli.prompt", slot_key=slot_key)
    return SessionSnapshot(
        session_id=session_id,
        status=SessionStatus.OPEN,
        slot=slot,
        active_run_id=None,
        queued_run_ids=(),
        timeline_cursor=HostStreamCursor(event_sequence=0),
    )


def _run_snapshot(*, run_id: str, status: RunStatus) -> RunSnapshot:
    """构造测试 RunSnapshot。

    :param run_id: Run id。
    :param status: Run status。
    :returns: RunSnapshot。
    :raises Exception: 不主动抛出异常。
    """

    return RunSnapshot(
        run_id=run_id,
        session_id="session-1",
        status=status,
        current_attempt_id=None,
        terminal_result_summary=None,
        event_cursor=HostStreamCursor(event_sequence=0),
        source_run_id=None,
        source_run_relation=None,
        outbox_summary=None,
    )


def _terminal_event(
    *,
    event_sequence: int,
    run_id: str,
    terminal_status: HostTerminalStatus = HostTerminalStatus.SUCCEEDED,
) -> HostEvent:
    """构造测试 terminal HostEvent。

    :param event_sequence: event sequence。
    :param run_id: Run id。
    :param terminal_status: terminal 状态。
    :returns: HostEvent。
    :raises Exception: 不主动抛出异常。
    """

    kind = _event_kind_for_terminal_status(terminal_status)
    final_answer = None
    if terminal_status is HostTerminalStatus.SUCCEEDED:
        final_answer = _final_answer(run_id=run_id)
    return HostEvent(
        event_id=f"terminal-{run_id}-{event_sequence}",
        event_sequence=event_sequence,
        session_id="session-1",
        run_id=run_id,
        kind=kind,
        dedupe_key=f"terminal-{run_id}-{event_sequence}",
        terminal_status=terminal_status,
        final_answer=final_answer,
        error_message=("run failed" if terminal_status is HostTerminalStatus.FAILED else None),
        cancel_reason=("cli_sigint" if terminal_status is HostTerminalStatus.CANCELLED else None),
    )


def _outbox_item(*, event_sequence: int, run_id: str) -> OutboxTerminalItem:
    """构造测试 outbox terminal item。

    :param event_sequence: terminal event sequence。
    :param run_id: Run id。
    :returns: OutboxTerminalItem。
    :raises Exception: 不主动抛出异常。
    """

    terminal_event_id = f"terminal-{run_id}-{event_sequence}"
    return OutboxTerminalItem(
        item_id=f"item-{run_id}-{event_sequence}",
        idempotency_key=f"idem-{run_id}-{event_sequence}",
        terminal_event_id=terminal_event_id,
        event_sequence=event_sequence,
        session_id="session-1",
        run_id=run_id,
        terminal_status=HostTerminalStatus.SUCCEEDED,
        dedupe_key=terminal_event_id,
        final_answer=_final_answer(run_id=run_id),
        error_message=None,
        cancel_reason=None,
        result_ref=None,
        result_digest=None,
        terminal_summary_ref=None,
        terminal_summary_digest=None,
        projected_at=_NOW,
        item_state=OutboxTerminalItemState.PENDING,
    )


def _outbox_batch(
    *,
    items: tuple[OutboxTerminalItem, ...],
    next_sequence: int,
    projection_status: OutboxProjectionStatus,
    has_more: bool = False,
    projection_error_code: str | None = None,
    projection_error_message: str | None = None,
) -> OutboxTerminalItemsBatch:
    """构造测试 outbox terminal batch。

    :param items: terminal items。
    :param next_sequence: next cursor sequence。
    :param projection_status: projection status。
    :param has_more: 是否还有后续页。
    :param projection_error_code: projection 错误码。
    :param projection_error_message: projection 错误消息。
    :returns: OutboxTerminalItemsBatch。
    :raises Exception: 不主动抛出异常。
    """

    cursor = OutboxTerminalCursor(event_sequence=next_sequence)
    return OutboxTerminalItemsBatch(
        items=items,
        next_cursor=cursor,
        scanned_watermark=cursor,
        projection_checkpoint=cursor,
        projection_status=projection_status,
        projection_error_code=projection_error_code,
        projection_error_message=projection_error_message,
        has_more=has_more,
    )


def _final_answer(*, run_id: str) -> HostFinalAnswerView:
    """构造测试 final answer view。

    :param run_id: Run id。
    :returns: HostFinalAnswerView。
    :raises Exception: 不主动抛出异常。
    """

    return HostFinalAnswerView(
        content=f"answer for {run_id}",
        filtered=False,
        degraded=False,
        finish_reason="stop",
        terminal_status=HostTerminalStatus.SUCCEEDED,
    )


def _event_kind_for_terminal_status(
    terminal_status: HostTerminalStatus,
) -> HostEventKind:
    """把 terminal status 映射为测试 HostEventKind。

    :param terminal_status: terminal status。
    :returns: HostEventKind。
    :raises AssertionError: 未覆盖的 terminal status 时抛出。
    """

    if terminal_status is HostTerminalStatus.SUCCEEDED:
        return HostEventKind.SUCCEEDED
    if terminal_status is HostTerminalStatus.FAILED:
        return HostEventKind.FAILED
    if terminal_status is HostTerminalStatus.CANCELLED:
        return HostEventKind.CANCELLED
    if terminal_status is HostTerminalStatus.LOST:
        return HostEventKind.LOST
    raise AssertionError(f"unexpected terminal status: {terminal_status}")
