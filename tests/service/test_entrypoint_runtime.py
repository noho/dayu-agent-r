"""``dayu.service.entrypoint_runtime`` Service 边界测试。"""

from __future__ import annotations

import ast
import asyncio
import json
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

import dayu.service.entrypoint_runtime as entrypoint_runtime
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
    HostActivityCounts,
    HostActivityKind,
    HostActivitySeverity,
    HostActivityStatus,
    HostActivityView,
    HostCallContext,
    HostClosedError,
    HostContentDelta,
    HostEvent,
    HostEventClass,
    HostEventKind,
    HostFinalAnswerView,
    HostReasoningDelta,
    HostSessionEvent,
    HostSessionEventDeliveryDetail,
    HostSessionEventDeliveryReason,
    HostSessionEventIterator,
    HostStreamCursor,
    HostTerminalStatus,
    HostToolCallDelta,
    HostTransientDelta,
    HostTransientDeltaType,
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
    TerminalResultSummary,
    is_terminal_run_status,
)
from dayu.service.entrypoint_runtime import (
    EntrypointActivity,
    EntrypointActivityCallback,
    EntrypointActivityKind,
    EntrypointActivitySeverity,
    EntrypointActivityStatus,
    EntrypointThinking,
    EntrypointThinkingCallback,
    EntrypointCallbackExecutionPort,
    EntrypointCancelRequest,
    EntrypointRuntimeRequest,
    EntrypointRuntimeResult,
    EntrypointRuntimeError,
    EntrypointRunTerminalResult,
    EntrypointStartupReconnectRequest,
    EntrypointTerminalSource,
    EntrypointTurnRequest,
    cancel_entrypoint_run_and_wait,
    ensure_or_create_entrypoint_session,
    prepare_entrypoint_runtime,
    startup_reconnect_entrypoint_session,
    submit_entrypoint_turn_and_wait,
)
from dayu.service.host_assembly import ServiceAssemblyOverrides, ServiceRunOverrides
from dayu.service.scene_context import (
    CURRENT_TIME_SLOT,
    FINS_DEFAULT_SUBJECT_SLOT,
    EntrypointContextSlotRequest,
    build_entrypoint_context_slot_values,
    current_time,
    fins_default_subject,
)
import dayu.service.scene_context as scene_context
from dayu.fins.resolver import FmpCompanyInfo, FmpCompanyInfoResolutionError

_PACKAGE_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "dayu" / "config"
_NOW = datetime(2026, 6, 14, 8, 0, 0, tzinfo=UTC)
_MODEL_ID = "deepseek-v4-flash"
_RUNNER_HINT_ID = "interactive"
_API_KEY = "test-provider-key"


class _FakeSceneContextFmpResolver:
    """scene context 测试用 FMP resolver。"""

    api_key: str
    timeout_seconds: float

    def __init__(self, *, api_key: str, timeout_seconds: float) -> None:
        """初始化 fake resolver。

        :param api_key: 调用方传入的 FMP API key。
        :param timeout_seconds: 调用方传入的 FMP timeout。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def resolve_company_info(self, canonical_ticker: str) -> FmpCompanyInfo:
        """返回固定公司信息。

        :param canonical_ticker: canonical ticker。
        :returns: fake 公司信息。
        :raises Exception: 不主动抛出异常。
        """

        return FmpCompanyInfo(
            canonical_ticker=canonical_ticker,
            company_name="Visa Inc.",
            ticker_aliases=(canonical_ticker,),
        )


class _FailingSceneContextFmpResolver:
    """scene context 测试用失败 FMP resolver。"""

    def __init__(self, *, api_key: str, timeout_seconds: float) -> None:
        """初始化失败 resolver。

        :param api_key: 调用方传入的 FMP API key。
        :param timeout_seconds: 调用方传入的 FMP timeout。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        del api_key, timeout_seconds

    def resolve_company_info(self, canonical_ticker: str) -> FmpCompanyInfo:
        """模拟 FMP 解析失败。

        :param canonical_ticker: canonical ticker。
        :returns: 不返回；始终抛出异常。
        :raises FmpCompanyInfoResolutionError: 始终抛出。
        """

        del canonical_ticker
        raise FmpCompanyInfoResolutionError("boom")


def test_scene_context_formats_subject_and_current_time() -> None:
    """scene context helper 应生成自解释的 LLM-facing 中文 slot 文本。"""

    assert fins_default_subject(None) == ""
    assert fins_default_subject(" v ") == "# 当前分析对象\n你正在分析的是 V。"
    assert fins_default_subject("V", company_name="Visa Inc.") == "# 当前分析对象\n你正在分析的是 V（Visa Inc.）。"
    assert (
        current_time(datetime(2026, 7, 7, 15, 8, tzinfo=UTC)) == "# 当前时间\n"
        "现在是 2026年7月7日 23:08（Asia/Shanghai，星期二）。\n"
        "这是对话开始时的当前时间；回答“现在/今天/当前时间”默认使用它；该时间不会自动更新。"
    )
    assert (
        current_time(datetime(2026, 7, 7, 15, 8)) == "# 当前时间\n"
        "现在是 2026年7月7日 15:08（Asia/Shanghai，星期二）。\n"
        "这是对话开始时的当前时间；回答“现在/今天/当前时间”默认使用它；该时间不会自动更新。"
    )


def test_build_entrypoint_context_slot_values_resolves_fmp_company_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """有 FMP key 时 Service helper 应用公司名增强 subject 文本。"""

    monkeypatch.setattr(scene_context, "FmpCompanyInfoResolver", _FakeSceneContextFmpResolver)

    values = build_entrypoint_context_slot_values(
        EntrypointContextSlotRequest(
            ticker="V",
            now=datetime(2026, 7, 7, 15, 8),
            fmp_api_key="test-fmp-key",
            fmp_timeout_seconds=2.0,
        )
    )

    assert values[FINS_DEFAULT_SUBJECT_SLOT] == "# 当前分析对象\n你正在分析的是 V（Visa Inc.）。"
    assert (
        values[CURRENT_TIME_SLOT] == "# 当前时间\n"
        "现在是 2026年7月7日 15:08（Asia/Shanghai，星期二）。\n"
        "这是对话开始时的当前时间；回答“现在/今天/当前时间”默认使用它；该时间不会自动更新。"
    )


def test_build_entrypoint_context_slot_values_falls_back_without_fmp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """缺 key 或 FMP 失败时 subject 应回退到 ticker-only 且不暴露错误文本。"""

    no_key_values = build_entrypoint_context_slot_values(
        EntrypointContextSlotRequest(
            ticker=None,
            now=datetime(2026, 7, 7, 15, 8),
            fmp_api_key=None,
        )
    )
    assert no_key_values[FINS_DEFAULT_SUBJECT_SLOT] == ""
    assert "未指定具体公司" not in str(no_key_values[FINS_DEFAULT_SUBJECT_SLOT])

    no_key_bad_timeout_values = build_entrypoint_context_slot_values(
        EntrypointContextSlotRequest(
            ticker="V",
            now=datetime(2026, 7, 7, 15, 8),
            fmp_api_key=None,
            fmp_timeout_seconds=0,
        )
    )
    assert no_key_bad_timeout_values[FINS_DEFAULT_SUBJECT_SLOT] == "# 当前分析对象\n你正在分析的是 V。"

    monkeypatch.setattr(scene_context, "FmpCompanyInfoResolver", _FailingSceneContextFmpResolver)
    failed_values = build_entrypoint_context_slot_values(
        EntrypointContextSlotRequest(
            ticker="V",
            now=datetime(2026, 7, 7, 15, 8),
            fmp_api_key="test-fmp-key",
        )
    )

    assert failed_values[FINS_DEFAULT_SUBJECT_SLOT] == "# 当前分析对象\n你正在分析的是 V。"
    assert "boom" not in str(failed_values[FINS_DEFAULT_SUBJECT_SLOT])


@dataclass(frozen=True, slots=True)
class _RaiseSignal:
    """测试 watcher 抛错信号。"""

    error: Exception


class _FakeHostEventIterator:
    """测试用可关闭 HostEvent iterator。"""

    closed_count: int
    _close_error: BaseException | None
    _items: tuple[HostSessionEvent | _RaiseSignal, ...]
    _item_index: int
    _changed: asyncio.Event
    _closed: bool
    anext_active: bool
    close_observed_active_anext: bool

    def __init__(self, *, close_error: BaseException | None = None) -> None:
        """初始化测试 watcher。

        :param close_error: ``aclose`` 应抛出的测试异常；``None`` 表示正常关闭。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.closed_count = 0
        self._close_error = close_error
        self._items = ()
        self._item_index = 0
        self._changed = asyncio.Event()
        self._closed = False
        self.anext_active = False
        self.close_observed_active_anext = False

    def __aiter__(self) -> HostSessionEventIterator:
        """返回自身作为 async iterator。

        :returns: HostEvent async iterator。
        :raises Exception: 不主动抛出异常。
        """

        return self

    async def __anext__(self) -> HostSessionEvent:
        """读取下一条测试事件。

        :returns: 下一条 HostEvent。
        :raises StopAsyncIteration: 收到停止信号时抛出。
        """

        self.anext_active = True
        try:
            while self._item_index >= len(self._items):
                if self._closed:
                    raise StopAsyncIteration
                self._changed.clear()
                await self._changed.wait()
            item = self._items[self._item_index]
            self._item_index += 1
            if isinstance(item, _RaiseSignal):
                raise item.error
            return item
        finally:
            self.anext_active = False

    async def push(self, event: HostSessionEvent) -> None:
        """向 watcher 推入测试事件。

        :param event: 待推入事件。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._items = (*self._items, event)
        self._changed.set()

    async def fail(self, error: Exception) -> None:
        """向 watcher 推入测试异常。

        :param error: watcher drain 应观察到的异常。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._items = (*self._items, _RaiseSignal(error=error))
        self._changed.set()

    async def aclose(self) -> None:
        """关闭测试 watcher。

        :returns: ``None``。
        :raises BaseException: 配置了 ``close_error`` 时抛出该异常。
        """

        self.closed_count += 1
        self.close_observed_active_anext = self.anext_active
        self._closed = True
        self._changed.set()
        if self._close_error is not None:
            raise self._close_error


class _InlineCallbackExecutionPort(EntrypointCallbackExecutionPort):
    """测试用 typed callback port；在当前 event-loop task 内直接调用。"""

    async def invoke_activity(
        self,
        callback: EntrypointActivityCallback,
        activity: EntrypointActivity,
    ) -> None:
        """调用 activity callback。

        :param callback: 同步 activity callback。
        :param activity: Service activity DTO。
        :returns: ``None``。
        :raises Exception: callback 原始异常透传。
        """

        callback(activity)

    async def invoke_thinking(
        self,
        callback: EntrypointThinkingCallback,
        thinking: EntrypointThinking,
    ) -> None:
        """调用 thinking callback。

        :param callback: 同步 thinking callback。
        :param thinking: Service thinking DTO。
        :returns: ``None``。
        :raises Exception: callback 原始异常透传。
        """

        callback(thinking)


class _FailingCallbackExecutionPort(EntrypointCallbackExecutionPort):
    """以同一原异常模拟 callback execution-domain scheduling failure。"""

    def __init__(self, error: RuntimeError) -> None:
        """初始化失败端口。

        :param error: 每次 invocation 应原样抛出的异常。
        :returns: ``None``。
        :raises Exception: 本构造函数不主动抛出异常。
        """

        self._error = error

    async def invoke_activity(
        self,
        callback: EntrypointActivityCallback,
        activity: EntrypointActivity,
    ) -> None:
        """模拟 activity 调度失败。

        :param callback: 未调用的 activity callback。
        :param activity: 未交付的 activity DTO。
        :returns: 本方法不返回。
        :raises RuntimeError: 原样抛出配置的 scheduling failure。
        """

        del callback, activity
        raise self._error

    async def invoke_thinking(
        self,
        callback: EntrypointThinkingCallback,
        thinking: EntrypointThinking,
    ) -> None:
        """模拟 thinking 调度失败。

        :param callback: 未调用的 thinking callback。
        :param thinking: 未交付的 thinking DTO。
        :returns: 本方法不返回。
        :raises RuntimeError: 原样抛出配置的 scheduling failure。
        """

        del callback, thinking
        raise self._error


class _BlockingCallbackExecutionPort(EntrypointCallbackExecutionPort):
    """用 async barrier 证明 consumer 会等待当前 callback 真正完成。"""

    def __init__(self) -> None:
        """初始化 barrier。

        :returns: ``None``。
        :raises Exception: 本构造函数不主动抛出异常。
        """

        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.finished = asyncio.Event()

    async def invoke_activity(
        self,
        callback: EntrypointActivityCallback,
        activity: EntrypointActivity,
    ) -> None:
        """阻塞 activity callback，释放后同步调用并标记完成。

        :param callback: activity callback。
        :param activity: activity DTO。
        :returns: ``None``。
        :raises Exception: callback 原始异常透传。
        """

        self.started.set()
        await self.release.wait()
        callback(activity)
        self.finished.set()

    async def invoke_thinking(
        self,
        callback: EntrypointThinkingCallback,
        thinking: EntrypointThinking,
    ) -> None:
        """阻塞 thinking callback，释放后同步调用并标记完成。

        :param callback: thinking callback。
        :param thinking: thinking DTO。
        :returns: ``None``。
        :raises Exception: callback 原始异常透传。
        """

        self.started.set()
        await self.release.wait()
        callback(thinking)
        self.finished.set()


class _FailingActivityProjection:
    """以指定原异常模拟 Host activity 到 Service DTO 的投影失败。"""

    error: RuntimeError

    def __init__(self, error: RuntimeError) -> None:
        """初始化失败投影。

        :param error: 投影调用必须原样抛出的异常。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.error = error

    def __call__(self, event: HostEvent) -> EntrypointActivity:
        """确认收到目标 public event 后抛出配置异常。

        :param event: sole consumer 已读取的 Host activity event。
        :returns: 本方法不返回。
        :raises RuntimeError: 始终抛出配置的投影异常。
        """

        if event.run_id != "run-1":
            raise AssertionError("projection received unexpected target Run")
        raise self.error


class _FakeHost:
    """测试用 Host public API 替身。"""

    calls: list[str]
    watchers: list[_FakeHostEventIterator]
    submit_requests: list[SubmitFollowupRequest]
    cancel_requests: list[CancelRunRequest]
    ensure_requests: list[EnsureSessionRequest]
    create_requests: list[CreateSessionRequest]
    read_outbox_requests: list[ReadOutboxTerminalItemsRequest]
    _submit_events: tuple[HostSessionEvent, ...]
    _submit_watcher_errors: tuple[Exception, ...]
    _cancel_events: tuple[HostSessionEvent, ...]
    _cancel_error: HostApiError | None
    _run_statuses: tuple[RunStatus, ...]
    _outbox_batches: tuple[OutboxTerminalItemsBatch, ...]
    _session_snapshots: tuple[SessionSnapshot, ...]
    _session_get_watcher_errors: tuple[Exception, ...]
    _run_status_index: int
    _outbox_index: int
    _session_snapshot_index: int
    _session_get_watcher_error_index: int
    _watcher: _FakeHostEventIterator | None

    def __init__(
        self,
        *,
        submit_events: tuple[HostSessionEvent, ...] = (),
        submit_watcher_errors: tuple[Exception, ...] = (),
        cancel_events: tuple[HostSessionEvent, ...] = (),
        cancel_error: HostApiError | None = None,
        run_statuses: tuple[RunStatus, ...] = (RunStatus.SUCCEEDED,),
        outbox_batches: tuple[OutboxTerminalItemsBatch, ...] = (),
        session_snapshots: tuple[SessionSnapshot, ...] = (),
        session_get_watcher_errors: tuple[Exception, ...] = (),
        watcher: _FakeHostEventIterator | None = None,
    ) -> None:
        """初始化测试 Host。

        :param submit_events: submit_followup 时推入 watcher 的事件。
        :param submit_watcher_errors: submit_followup 时推入 watcher 的异常。
        :param cancel_events: cancel_run 时推入 watcher 的事件。
        :param cancel_error: cancel_run 应抛出的 Host API 错误。
        :param run_statuses: get_run 依次返回的 RunStatus。
        :param outbox_batches: read_outbox_terminal_items 依次返回的批次。
        :param session_snapshots: get_session 依次返回的 SessionSnapshot。
        :param session_get_watcher_errors: get_session 返回后推入 startup watcher 的异常。
        :param watcher: 可选预构造 public iterator。
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
        self._session_snapshots = session_snapshots
        self._session_get_watcher_errors = session_get_watcher_errors
        self._run_status_index = 0
        self._outbox_index = 0
        self._session_snapshot_index = 0
        self._session_get_watcher_error_index = 0
        self._watcher = watcher

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

    async def watch_session_events(
        self,
        session_id: str,
    ) -> HostSessionEventIterator:
        """记录 watcher attach 并返回测试 iterator。

        :param session_id: 目标 Session id。
        :returns: HostSessionEvent async iterator。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(f"watch:{session_id}")
        watcher = _FakeHostEventIterator() if self._watcher is None else self._watcher
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

    async def get_session(self, session_id: str) -> SessionSnapshot:
        """按预设返回 Session snapshot。

        :param session_id: 目标 Session id。
        :returns: SessionSnapshot。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(f"get_session:{session_id}")
        if not self._session_snapshots:
            return _session_snapshot(session_id=session_id, slot_key=None)
        snapshot_index = min(
            self._session_snapshot_index,
            len(self._session_snapshots) - 1,
        )
        self._session_snapshot_index += 1
        if self._session_get_watcher_error_index < len(self._session_get_watcher_errors):
            await self.watchers[-1].fail(self._session_get_watcher_errors[self._session_get_watcher_error_index])
            self._session_get_watcher_error_index += 1
            await asyncio.sleep(0)
        return self._session_snapshots[snapshot_index]

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


class _AttachFailingHost(_FakeHost):
    """在 public watcher factory 边界原样失败的 Host fake。"""

    def __init__(self, error: RuntimeError) -> None:
        """初始化 attach failure fake。

        :param error: watcher factory 应原样抛出的异常。
        :returns: ``None``。
        :raises Exception: 本构造函数不主动抛出异常。
        """

        super().__init__()
        self._attach_error = error

    async def watch_session_events(
        self,
        session_id: str,
    ) -> HostSessionEventIterator:
        """记录 attach 后原样抛出构造失败。

        :param session_id: 目标 Session id。
        :returns: 本方法不返回。
        :raises RuntimeError: 原样抛出配置的 attach failure。
        """

        self.calls.append(f"watch:{session_id}")
        raise self._attach_error


class _StartupReadProbeHost(_FakeHost):
    """记录每次 startup Session probe 前 consumer 已读取的 item 数。"""

    def __init__(
        self,
        *,
        watcher: _FakeHostEventIterator,
        session_snapshots: tuple[SessionSnapshot, ...],
        outbox_batches: tuple[OutboxTerminalItemsBatch, ...],
    ) -> None:
        """初始化 startup generation probe。

        :param watcher: 预装多 target terminal 的 public iterator fake。
        :param session_snapshots: 依次暴露的 active target snapshots。
        :param outbox_batches: startup 前后 durable backfill batches。
        :returns: ``None``。
        :raises Exception: 本构造函数不主动抛出异常。
        """

        super().__init__(
            watcher=watcher,
            session_snapshots=session_snapshots,
            outbox_batches=outbox_batches,
        )
        self.item_indices_before_session_read: list[int] = []

    async def get_session(self, session_id: str) -> SessionSnapshot:
        """记录 iterator progress 后转发 Session probe。

        :param session_id: 目标 Session id。
        :returns: 预设 Session snapshot。
        :raises Exception: 基类 fake 失败时透传。
        """

        self.item_indices_before_session_read.append(self.watchers[-1]._item_index)
        return await super().get_session(session_id)


class _SubmitFailingHost(_FakeHost):
    """watcher attach 成功后 submit 原样失败的 Host fake。"""

    def __init__(
        self,
        error: RuntimeError,
        *,
        watcher: _FakeHostEventIterator,
    ) -> None:
        """初始化 submit failure fake。

        :param error: submit 应原样抛出的异常。
        :param watcher: attach 返回的 public iterator fake。
        :returns: ``None``。
        :raises Exception: 本构造函数不主动抛出异常。
        """

        super().__init__(watcher=watcher)
        self._submit_error = error

    async def submit_followup(
        self,
        session_id: str,
        request: SubmitFollowupRequest,
    ) -> FollowupSnapshot:
        """记录 submit 后原样抛出失败。

        :param session_id: 目标 Session id。
        :param request: public follow-up 请求。
        :returns: 本方法不返回。
        :raises RuntimeError: 原样抛出配置的 submit failure。
        """

        self.calls.append(f"submit:{session_id}")
        self.submit_requests.append(request)
        raise self._submit_error


class _RecoveryFailingHost(_FakeHost):
    """typed delivery interruption 后 durable read 原样失败的 Host fake。"""

    def __init__(
        self,
        error: RuntimeError,
        *,
        watcher: _FakeHostEventIterator,
        delivery_error: HostApiError,
    ) -> None:
        """初始化 recovery failure fake。

        :param error: durable ``get_run`` 应原样抛出的异常。
        :param watcher: attach 返回的 public iterator fake。
        :param delivery_error: submit 期间推入的 typed delivery failure。
        :returns: ``None``。
        :raises Exception: 本构造函数不主动抛出异常。
        """

        super().__init__(
            watcher=watcher,
            submit_watcher_errors=(delivery_error,),
        )
        self._recovery_error = error

    async def get_run(self, run_id: str) -> RunSnapshot:
        """记录 durable read 后原样失败。

        :param run_id: 目标 Run id。
        :returns: 本方法不返回。
        :raises RuntimeError: 原样抛出配置的 recovery failure。
        """

        self.calls.append(f"get_run:{run_id}")
        raise self._recovery_error


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


class _SleepAndPushTerminal:
    """测试用 sleep coroutine，在第一次 sleep 时推送 live terminal。"""

    calls: list[float]
    _host: _FakeHost
    _event: HostEvent
    _pushed: bool

    def __init__(self, *, host: _FakeHost, event: HostEvent) -> None:
        """初始化 sleep 推送器。

        :param host: 接收 watcher 的 fake Host。
        :param event: 第一次 sleep 时推送的 terminal event。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.calls = []
        self._host = host
        self._event = event
        self._pushed = False

    async def __call__(self, seconds: float) -> None:
        """记录 sleep 秒数，并在首次调用时推送 terminal。

        :param seconds: sleep 秒数。
        :returns: ``None``。
        :raises AssertionError: watcher 尚未 attach 时抛出。
        """

        self.calls.append(seconds)
        if not self._pushed:
            self._pushed = True
            if len(self._host.watchers) == 0:
                raise AssertionError("watcher must be attached before sleep")
            await self._host.watchers[-1].push(self._event)
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_prepare_entrypoint_runtime_assembles_scene_tools_and_host(
    tmp_path: Path,
) -> None:
    """prepare helper 应完成 location、config、scene、tools 与 Host assembly。"""

    result = await _prepare_runtime(tmp_path)

    assert isinstance(result, EntrypointRuntimeResult)
    assert result.locations.config_overlay_dir == tmp_path / "config"
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
async def test_submit_callback_port_validation_precedes_host_attach(
    tmp_path: Path,
) -> None:
    """callback/port 组合非法时必须在 Host attach/submit 前失败。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises Exception: validation ordering 断言失败时由 pytest 抛出。
    """

    runtime = await _prepare_runtime(tmp_path)
    fake_host = _FakeHost()
    activities: list[EntrypointActivity] = []

    with pytest.raises(ValueError, match="callback_execution_port is required"):
        await submit_entrypoint_turn_and_wait(
            cast(Host, fake_host),
            request=_turn_request(),
            scene_inputs=runtime.scene_inputs,
            host_assembly=runtime.host_assembly,
            on_activity=activities.append,
        )

    assert fake_host.calls == []


@pytest.mark.asyncio
async def test_submit_attach_failure_prevents_submit(
    tmp_path: Path,
) -> None:
    """public iterator factory 失败时不得执行 submit。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises Exception: attach ordering 断言失败时由 pytest 抛出。
    """

    runtime = await _prepare_runtime(tmp_path)
    attach_error = RuntimeError("attach failed")
    fake_host = _AttachFailingHost(attach_error)

    with pytest.raises(RuntimeError, match="attach failed") as exc_info:
        await submit_entrypoint_turn_and_wait(
            cast(Host, fake_host),
            request=_turn_request(),
            scene_inputs=runtime.scene_inputs,
            host_assembly=runtime.host_assembly,
        )

    assert exc_info.value is attach_error
    assert fake_host.calls == ["watch:session-1"]
    assert fake_host.submit_requests == []


@pytest.mark.asyncio
async def test_consumer_task_construction_failure_preserves_primary_and_closes_iterator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """consumer task 构造失败时仍应关闭 iterator，且 close 只能作为 cause。

    :param monkeypatch: pytest 属性替换夹具。
    :returns: ``None``。
    :raises Exception: owner contract 断言失败时由 pytest 抛出。
    """

    task_error = RuntimeError("consumer task construction failed")
    close_error = RuntimeError("consumer construction cleanup failed")
    watcher = _FakeHostEventIterator(close_error=close_error)
    fake_host = _FakeHost(watcher=watcher)

    def fail_create_task(
        _coroutine: Coroutine[None, None, None],
    ) -> asyncio.Task[None]:
        """模拟 event-loop task 构造失败。

        :param _coroutine: 尚未启动的 sole-consumer coroutine。
        :returns: 本函数不返回。
        :raises RuntimeError: 始终抛出固定 task 构造失败。
        """

        raise task_error

    monkeypatch.setattr(entrypoint_runtime.asyncio, "create_task", fail_create_task)

    with pytest.raises(RuntimeError, match="consumer task construction failed") as exc_info:
        await entrypoint_runtime._create_watch_and_wait_runtime(
            cast(Host, fake_host),
            "session-1",
            observation_state=entrypoint_runtime._new_terminal_observation_state(),
            on_activity=None,
            on_thinking=None,
            callback_execution_port=None,
        )

    assert exc_info.value is task_error
    assert task_error.__cause__ is close_error
    assert watcher.closed_count == 1
    assert fake_host.calls == ["watch:session-1"]


@pytest.mark.asyncio
async def test_submit_failure_is_primary_and_closes_unbound_iterator(
    tmp_path: Path,
) -> None:
    """submit 失败不得猜测 target，且 cleanup failure 只能作为 cause。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises Exception: submit cleanup 断言失败时由 pytest 抛出。
    """

    runtime = await _prepare_runtime(tmp_path)
    submit_error = RuntimeError("submit failed")
    close_error = RuntimeError("submit cleanup failed")
    watcher = _FakeHostEventIterator(close_error=close_error)
    fake_host = _SubmitFailingHost(submit_error, watcher=watcher)

    with pytest.raises(RuntimeError, match="submit failed") as exc_info:
        await submit_entrypoint_turn_and_wait(
            cast(Host, fake_host),
            request=_turn_request(),
            scene_inputs=runtime.scene_inputs,
            host_assembly=runtime.host_assembly,
        )

    assert exc_info.value is submit_error
    assert exc_info.value.__cause__ is close_error
    assert fake_host.calls == ["watch:session-1", "submit:session-1"]
    assert watcher.closed_count == 1
    assert watcher.close_observed_active_anext is False


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
async def test_submit_entrypoint_turn_emits_host_public_activity(
    tmp_path: Path,
) -> None:
    """submit helper 应把目标 Run 的 Host public activity 投影给 callback。"""

    runtime = await _prepare_runtime(tmp_path)
    activities: list[EntrypointActivity] = []
    fake_host = _FakeHost(
        submit_events=(
            _activity_event(
                event_sequence=2,
                run_id="run-1",
                dedupe_key="activity-tool-call",
            ),
            _terminal_event(event_sequence=3, run_id="run-1"),
        )
    )

    result = await submit_entrypoint_turn_and_wait(
        cast(Host, fake_host),
        request=_turn_request(),
        scene_inputs=runtime.scene_inputs,
        host_assembly=runtime.host_assembly,
        on_activity=activities.append,
        callback_execution_port=_InlineCallbackExecutionPort(),
    )

    assert result.source is EntrypointTerminalSource.LIVE_EVENT
    assert result.terminal_event_id == "terminal-run-1-3"
    assert len(activities) == 1
    activity = activities[0]
    assert activity.kind is EntrypointActivityKind.TOOL_BATCH
    assert activity.status is EntrypointActivityStatus.COMPLETED
    assert activity.run_id == "run-1"
    assert activity.event_sequence == 2
    assert activity.dedupe_key == "activity-tool-call"
    assert activity.title == "工具批次完成"
    assert activity.summary == "完成 2 个工具调用。"
    assert activity.severity is EntrypointActivitySeverity.INFO
    assert activity.tool_name == "record_smoke_fact"
    assert activity.tool_display_name == "记录烟测事实"
    assert activity.counts is not None
    assert activity.counts.total == 2
    assert activity.counts.completed == 2
    assert activity.counts.failed == 0
    assert activity.counts.cancelled == 0


@pytest.mark.asyncio
async def test_submit_entrypoint_turn_preserves_provider_protocol_error_activity(
    tmp_path: Path,
) -> None:
    """submit helper 保留 fatal provider protocol error activity kind。"""

    runtime = await _prepare_runtime(tmp_path)
    activities: list[EntrypointActivity] = []
    fake_host = _FakeHost(
        submit_events=(
            _activity_event(
                event_sequence=2,
                run_id="run-1",
                dedupe_key="activity-provider-protocol-error",
                activity_kind=HostActivityKind.PROVIDER_PROTOCOL_ERROR,
                activity_status=HostActivityStatus.FAILED,
            ),
            _terminal_event(event_sequence=3, run_id="run-1"),
        )
    )

    await submit_entrypoint_turn_and_wait(
        cast(Host, fake_host),
        request=_turn_request(),
        scene_inputs=runtime.scene_inputs,
        host_assembly=runtime.host_assembly,
        on_activity=activities.append,
        callback_execution_port=_InlineCallbackExecutionPort(),
    )

    assert len(activities) == 1
    activity = activities[0]
    assert activity.kind is EntrypointActivityKind.PROVIDER_PROTOCOL_ERROR
    assert activity.status is EntrypointActivityStatus.FAILED
    assert activity.dedupe_key == "activity-provider-protocol-error"


@pytest.mark.asyncio
async def test_submit_entrypoint_turn_emits_host_public_thinking(
    tmp_path: Path,
) -> None:
    """submit helper 应把目标 Run 的 Host public thinking 投影给 callback。"""

    runtime = await _prepare_runtime(tmp_path)
    thinking_events: list[EntrypointThinking] = []
    fake_host = _FakeHost(
        submit_events=(
            _transient_delta(
                runtime_sequence=1,
                run_id="run-1",
                dedupe_key="content-run-1",
                transient_type=HostTransientDeltaType.CONTENT_DELTA,
                data=HostContentDelta(
                    iteration_id="iteration-1",
                    text_delta="content",
                ),
            ),
            _transient_delta(
                runtime_sequence=2,
                run_id="run-1",
                dedupe_key="thinking-run-1",
                transient_type=HostTransientDeltaType.REASONING_DELTA,
                data=HostReasoningDelta(
                    iteration_id="iteration-1",
                    text_delta="正在分析收入变化",
                ),
            ),
            _transient_delta(
                runtime_sequence=3,
                run_id="run-1",
                dedupe_key="tool-run-1",
                transient_type=HostTransientDeltaType.TOOL_CALL_DELTA,
                data=HostToolCallDelta(
                    iteration_id="iteration-1",
                    tool_call_index=0,
                    tool_call_id="tool-call-1",
                    name_delta="lookup",
                    arguments_delta=None,
                ),
            ),
            _terminal_event(event_sequence=4, run_id="run-1"),
        )
    )

    result = await submit_entrypoint_turn_and_wait(
        cast(Host, fake_host),
        request=_turn_request(),
        scene_inputs=runtime.scene_inputs,
        host_assembly=runtime.host_assembly,
        on_thinking=thinking_events.append,
        callback_execution_port=_InlineCallbackExecutionPort(),
    )

    assert result.source is EntrypointTerminalSource.LIVE_EVENT
    assert result.terminal_event_id == "terminal-run-1-4"
    assert len(thinking_events) == 1
    thinking = thinking_events[0]
    assert thinking.run_id == "run-1"
    assert thinking.runtime_id == "runtime-1"
    assert thinking.runtime_sequence == 2
    assert thinking.dedupe_key == "thinking-run-1"
    assert thinking.text_delta == "正在分析收入变化"


@pytest.mark.asyncio
async def test_submit_entrypoint_turn_deduplicates_activity_by_dedupe_key(
    tmp_path: Path,
) -> None:
    """重复 dedupe key 的 progress activity 不得重复 callback。"""

    runtime = await _prepare_runtime(tmp_path)
    activities: list[EntrypointActivity] = []
    fake_host = _FakeHost(
        submit_events=(
            _activity_event(
                event_sequence=2,
                run_id="run-1",
                dedupe_key="activity-duplicate",
            ),
            _activity_event(
                event_sequence=3,
                run_id="run-1",
                dedupe_key="activity-duplicate",
            ),
            _terminal_event(event_sequence=4, run_id="run-1"),
        )
    )

    result = await submit_entrypoint_turn_and_wait(
        cast(Host, fake_host),
        request=_turn_request(),
        scene_inputs=runtime.scene_inputs,
        host_assembly=runtime.host_assembly,
        on_activity=activities.append,
        callback_execution_port=_InlineCallbackExecutionPort(),
    )

    assert result.run_id == "run-1"
    assert [activity.dedupe_key for activity in activities] == ["activity-duplicate"]


@pytest.mark.asyncio
async def test_submit_entrypoint_turn_non_terminal_dedupe_key_does_not_hide_terminal(
    tmp_path: Path,
) -> None:
    """非终态事件与 terminal 共用 dedupe key 时仍必须返回 terminal。"""

    runtime = await _prepare_runtime(tmp_path)
    shared_dedupe_key = "shared-progress-terminal-dedupe"
    fake_host = _FakeHost(
        submit_events=(
            _activity_event(
                event_sequence=2,
                run_id="run-1",
                dedupe_key=shared_dedupe_key,
            ),
            _terminal_event(
                event_sequence=3,
                run_id="run-1",
                dedupe_key=shared_dedupe_key,
            ),
        )
    )

    result = await submit_entrypoint_turn_and_wait(
        cast(Host, fake_host),
        request=_turn_request(),
        scene_inputs=runtime.scene_inputs,
        host_assembly=runtime.host_assembly,
    )

    assert result.source is EntrypointTerminalSource.LIVE_EVENT
    assert result.run_id == "run-1"
    assert result.terminal_event_id == "terminal-run-1-3"
    assert result.dedupe_key == shared_dedupe_key


@pytest.mark.asyncio
async def test_submit_entrypoint_turn_activity_callback_exception_propagates(
    tmp_path: Path,
) -> None:
    """on_activity callback 抛错时应向调用方传播，不被 watcher wait 吞掉。"""

    runtime = await _prepare_runtime(tmp_path)
    fake_host = _FakeHost(
        submit_events=(
            _activity_event(
                event_sequence=2,
                run_id="run-1",
                dedupe_key="activity-callback-error",
            ),
            _terminal_event(event_sequence=3, run_id="run-1"),
        )
    )

    def raise_from_activity(activity: EntrypointActivity) -> None:
        """测试 activity callback 异常传播。

        :param activity: Service activity。
        :returns: ``None``。
        :raises RuntimeError: 始终抛出测试异常。
        """

        raise RuntimeError(f"activity callback failed: {activity.dedupe_key}")

    with pytest.raises(RuntimeError, match="activity callback failed: activity-callback-error"):
        await submit_entrypoint_turn_and_wait(
            cast(Host, fake_host),
            request=_turn_request(),
            scene_inputs=runtime.scene_inputs,
            host_assembly=runtime.host_assembly,
            on_activity=raise_from_activity,
            callback_execution_port=_InlineCallbackExecutionPort(),
        )

    assert fake_host.watchers[0].closed_count == 1


@pytest.mark.asyncio
async def test_submit_callback_failure_preserves_close_as_direct_cause(
    tmp_path: Path,
) -> None:
    """callback + close 应保持 callback 原异常为 top-level。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises Exception: exception chain 断言失败时由 pytest 抛出。
    """

    runtime = await _prepare_runtime(tmp_path)
    callback_error = RuntimeError("callback failed")
    close_error = RuntimeError("callback cleanup failed")
    watcher = _FakeHostEventIterator(close_error=close_error)
    fake_host = _FakeHost(
        watcher=watcher,
        submit_events=(
            _activity_event(
                event_sequence=2,
                run_id="run-1",
                dedupe_key="callback-close",
            ),
        ),
    )

    def fail_callback(_activity: EntrypointActivity) -> None:
        """原样抛出 callback failure。

        :param _activity: Service activity DTO。
        :returns: 本函数不返回。
        :raises RuntimeError: 始终抛出固定 callback failure。
        """

        raise callback_error

    with pytest.raises(RuntimeError, match="callback failed") as exc_info:
        await submit_entrypoint_turn_and_wait(
            cast(Host, fake_host),
            request=_turn_request(),
            scene_inputs=runtime.scene_inputs,
            host_assembly=runtime.host_assembly,
            on_activity=fail_callback,
            callback_execution_port=_InlineCallbackExecutionPort(),
        )

    assert exc_info.value is callback_error
    assert exc_info.value.__cause__ is close_error
    assert watcher.closed_count == 1
    assert watcher.close_observed_active_anext is False


@pytest.mark.asyncio
async def test_submit_execution_port_failure_uses_callback_failed_member(
    tmp_path: Path,
) -> None:
    """execution-domain scheduling failure 应保持原 identity，不新增 outcome。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises Exception: callback outcome 断言失败时由 pytest 抛出。
    """

    runtime = await _prepare_runtime(tmp_path)
    scheduling_error = RuntimeError("display scheduling failed")
    callback_values: list[EntrypointActivity] = []
    fake_host = _FakeHost(
        submit_events=(
            _activity_event(
                event_sequence=2,
                run_id="run-1",
                dedupe_key="scheduling-failure",
            ),
        )
    )

    with pytest.raises(RuntimeError, match="display scheduling failed") as exc_info:
        await submit_entrypoint_turn_and_wait(
            cast(Host, fake_host),
            request=_turn_request(),
            scene_inputs=runtime.scene_inputs,
            host_assembly=runtime.host_assembly,
            on_activity=callback_values.append,
            callback_execution_port=_FailingCallbackExecutionPort(scheduling_error),
        )

    assert exc_info.value is scheduling_error
    assert callback_values == []
    assert fake_host.watchers[0].closed_count == 1


@pytest.mark.asyncio
async def test_submit_consumer_does_not_anext_until_current_callback_finishes(
    tmp_path: Path,
) -> None:
    """当前 callback 完成前 sole consumer 不得读取后续 terminal。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises Exception: callback/anext ordering 断言失败时由 pytest 抛出。
    """

    runtime = await _prepare_runtime(tmp_path)
    port = _BlockingCallbackExecutionPort()
    activities: list[EntrypointActivity] = []
    watcher = _FakeHostEventIterator()
    fake_host = _FakeHost(
        watcher=watcher,
        submit_events=(
            _activity_event(
                event_sequence=2,
                run_id="run-1",
                dedupe_key="blocking-callback",
            ),
            _terminal_event(event_sequence=3, run_id="run-1"),
        ),
    )

    submit_task = asyncio.create_task(
        submit_entrypoint_turn_and_wait(
            cast(Host, fake_host),
            request=_turn_request(),
            scene_inputs=runtime.scene_inputs,
            host_assembly=runtime.host_assembly,
            on_activity=activities.append,
            callback_execution_port=port,
        )
    )
    await port.started.wait()
    await asyncio.sleep(0)
    assert watcher._item_index == 1
    assert submit_task.done() is False

    port.release.set()
    result = await submit_task

    assert port.finished.is_set()
    assert result.terminal_event_id == "terminal-run-1-3"
    assert watcher._item_index == 2
    assert watcher.closed_count == 1


@pytest.mark.asyncio
async def test_submit_entrypoint_turn_suppresses_progress_without_activity(
    tmp_path: Path,
) -> None:
    """无 Host public activity 的 progress 不得生成伪工具展示。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises Exception: activity projection 断言失败时由 pytest 抛出。
    """

    runtime = await _prepare_runtime(tmp_path)
    activities: list[EntrypointActivity] = []
    fake_host = _FakeHost(
        submit_events=(
            _progress_without_activity(event_sequence=2, run_id="run-1"),
            _terminal_event(event_sequence=3, run_id="run-1"),
        )
    )

    result = await submit_entrypoint_turn_and_wait(
        cast(Host, fake_host),
        request=_turn_request(),
        scene_inputs=runtime.scene_inputs,
        host_assembly=runtime.host_assembly,
        on_activity=activities.append,
        callback_execution_port=_InlineCallbackExecutionPort(),
    )

    assert result.run_id == "run-1"
    assert activities == []


@pytest.mark.asyncio
async def test_submit_entrypoint_turn_filters_unrelated_activity(
    tmp_path: Path,
) -> None:
    """同 Session 其它 Run 的 activity 不得进入当前 turn callback。"""

    runtime = await _prepare_runtime(tmp_path)
    activities: list[EntrypointActivity] = []
    fake_host = _FakeHost(
        submit_events=(
            _activity_event(
                event_sequence=2,
                run_id="other-run",
                dedupe_key="activity-other-run",
            ),
            _activity_event(
                event_sequence=3,
                run_id="run-1",
                dedupe_key="activity-current-run",
            ),
            _terminal_event(event_sequence=4, run_id="run-1"),
        )
    )

    result = await submit_entrypoint_turn_and_wait(
        cast(Host, fake_host),
        request=_turn_request(),
        scene_inputs=runtime.scene_inputs,
        host_assembly=runtime.host_assembly,
        on_activity=activities.append,
        callback_execution_port=_InlineCallbackExecutionPort(),
    )

    assert result.run_id == "run-1"
    assert [activity.dedupe_key for activity in activities] == ["activity-current-run"]


@pytest.mark.asyncio
async def test_submit_entrypoint_turn_waits_live_terminal_when_run_snapshot_is_terminal(
    tmp_path: Path,
) -> None:
    """submit 已 attach 时，get_run 先见终态也必须等待 live terminal。"""

    runtime = await _prepare_runtime(tmp_path)
    outbox_item = _outbox_item(event_sequence=5, run_id="run-1")
    terminal_event = _terminal_event(event_sequence=6, run_id="run-1")
    fake_host = _FakeHost(
        submit_events=(terminal_event,),
        run_statuses=(RunStatus.SUCCEEDED, RunStatus.SUCCEEDED),
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

    assert result.source is EntrypointTerminalSource.LIVE_EVENT
    assert result.terminal_event_id == "terminal-run-1-6"
    assert fake_host.read_outbox_requests == []


@pytest.mark.asyncio
async def test_startup_reconnect_attaches_watcher_before_session_outbox_backfill() -> None:
    """interactive startup 必须 watcher-first 后读取 session-scoped outbox。"""

    fake_host = _FakeHost(
        outbox_batches=(
            _outbox_batch(
                items=(
                    _outbox_item(event_sequence=2, run_id="run-1"),
                    _outbox_item(event_sequence=3, run_id="run-2"),
                ),
                next_sequence=3,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
        )
    )

    result = await startup_reconnect_entrypoint_session(
        cast(Host, fake_host),
        request=_startup_request(),
    )

    assert [terminal.run_id for terminal in result.terminal_results] == [
        "run-1",
        "run-2",
    ]
    assert result.next_terminal_cursor == OutboxTerminalCursor(event_sequence=3)
    assert fake_host.calls[:2] == ["watch:session-1", "read_outbox:session-1"]
    assert fake_host.read_outbox_requests[0].after == OutboxTerminalCursor(event_sequence=0)


@pytest.mark.asyncio
async def test_startup_reconnect_treats_caught_up_empty_backfill_as_idle_success() -> None:
    """startup session backfill 追平且无新 terminal 时应正常进入 idle success。"""

    fake_host = _FakeHost()

    result = await startup_reconnect_entrypoint_session(
        cast(Host, fake_host),
        request=_startup_request(),
    )

    assert result.terminal_results == ()
    assert fake_host.calls == [
        "watch:session-1",
        "read_outbox:session-1",
        "get_session:session-1",
        "read_outbox:session-1",
    ]


@pytest.mark.asyncio
async def test_startup_reconnect_reads_idle_tail_outbox_before_returning() -> None:
    """idle snapshot 后必须补读 tail outbox，避免 terminal 在输入态前丢失。"""

    fake_host = _FakeHost(
        session_snapshots=(_session_snapshot(session_id="session-1", slot_key=None),),
        outbox_batches=(
            _outbox_batch(
                items=(),
                next_sequence=0,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
            _outbox_batch(
                items=(_outbox_item(event_sequence=7, run_id="run-tail"),),
                next_sequence=7,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
            _outbox_batch(
                items=(),
                next_sequence=7,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
        ),
    )

    result = await startup_reconnect_entrypoint_session(
        cast(Host, fake_host),
        request=_startup_request(),
    )

    assert [terminal.run_id for terminal in result.terminal_results] == ["run-tail"]
    assert result.next_terminal_cursor == OutboxTerminalCursor(event_sequence=7)
    assert [request.after for request in fake_host.read_outbox_requests] == [
        OutboxTerminalCursor(event_sequence=0),
        OutboxTerminalCursor(event_sequence=0),
        OutboxTerminalCursor(event_sequence=7),
    ]
    assert fake_host.calls == [
        "watch:session-1",
        "read_outbox:session-1",
        "get_session:session-1",
        "read_outbox:session-1",
        "get_session:session-1",
        "read_outbox:session-1",
    ]


@pytest.mark.asyncio
async def test_startup_reconnect_idle_does_not_read_unbound_iterator() -> None:
    """startup 无 target 时不得预读 iterator 或建立 live cache。

    :returns: ``None``。
    :raises Exception: unbound iterator 断言失败时由 pytest 抛出。
    """

    fake_host = _FakeHost(
        session_snapshots=(_session_snapshot(session_id="session-1", slot_key=None),),
        session_get_watcher_errors=(RuntimeError("startup watcher stopped"),),
        outbox_batches=(
            _outbox_batch(
                items=(),
                next_sequence=0,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
            _outbox_batch(
                items=(),
                next_sequence=0,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
            _outbox_batch(
                items=(_outbox_item(event_sequence=11, run_id="run-after-failure"),),
                next_sequence=11,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
            _outbox_batch(
                items=(),
                next_sequence=11,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
        ),
    )

    result = await startup_reconnect_entrypoint_session(
        cast(Host, fake_host),
        request=_startup_request(),
    )

    assert result.terminal_results == ()
    assert fake_host.watchers[0]._item_index == 0
    assert fake_host.watchers[0].closed_count == 1
    assert [request.after for request in fake_host.read_outbox_requests] == [
        OutboxTerminalCursor(event_sequence=0),
        OutboxTerminalCursor(event_sequence=0),
    ]


@pytest.mark.asyncio
async def test_startup_reconnect_deduplicates_seen_terminal_ids() -> None:
    """startup backfill 必须按 CLI seen terminal ids 去重。"""

    fake_host = _FakeHost(
        outbox_batches=(
            _outbox_batch(
                items=(_outbox_item(event_sequence=2, run_id="run-1"),),
                next_sequence=2,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
        )
    )

    result = await startup_reconnect_entrypoint_session(
        cast(Host, fake_host),
        request=_startup_request(
            seen_terminal_event_ids=frozenset({"terminal-run-1-2"}),
        ),
    )

    assert result.terminal_results == ()
    assert fake_host.read_outbox_requests[0].seen_terminal_event_ids == ("terminal-run-1-2",)


@pytest.mark.asyncio
async def test_startup_reconnect_retries_lagged_by_parameter() -> None:
    """startup backfill 的 LAGGED 重试次数必须由请求参数控制。"""

    sleep = _SleepRecorder()
    fake_host = _FakeHost(
        outbox_batches=(
            _outbox_batch(
                items=(),
                next_sequence=0,
                projection_status=OutboxProjectionStatus.LAGGED,
            ),
            _outbox_batch(
                items=(_outbox_item(event_sequence=4, run_id="run-1"),),
                next_sequence=4,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
        )
    )

    result = await startup_reconnect_entrypoint_session(
        cast(Host, fake_host),
        request=_startup_request(outbox_lagged_max_attempts=1),
        sleep=sleep,
    )

    assert [terminal.run_id for terminal in result.terminal_results] == ["run-1"]
    assert sleep.calls == [0.05]


@pytest.mark.asyncio
async def test_startup_reconnect_lagged_retry_exhaustion_fails() -> None:
    """startup backfill 的 LAGGED 重试耗尽必须结构化失败。"""

    fake_host = _FakeHost(
        outbox_batches=(
            _outbox_batch(
                items=(),
                next_sequence=0,
                projection_status=OutboxProjectionStatus.LAGGED,
            ),
        )
    )

    with pytest.raises(EntrypointRuntimeError, match="projection lagged"):
        await startup_reconnect_entrypoint_session(
            cast(Host, fake_host),
            request=_startup_request(outbox_lagged_max_attempts=0),
        )


@pytest.mark.asyncio
async def test_startup_reconnect_projection_failed_fails() -> None:
    """startup backfill 遇到 projection FAILED 必须失败而不是进入 REPL。"""

    fake_host = _FakeHost(
        outbox_batches=(
            _outbox_batch(
                items=(),
                next_sequence=0,
                projection_status=OutboxProjectionStatus.FAILED,
                projection_error_code="projection_failed",
                projection_error_message="projection stopped",
            ),
        )
    )

    with pytest.raises(EntrypointRuntimeError, match="projection_failed"):
        await startup_reconnect_entrypoint_session(
            cast(Host, fake_host),
            request=_startup_request(),
        )


@pytest.mark.asyncio
async def test_startup_reconnect_observes_existing_active_run_terminal() -> None:
    """startup 发现 active Run 时必须先观察 terminal 再进入 idle。"""

    watcher = _FakeHostEventIterator()
    await watcher.push(_terminal_event(event_sequence=8, run_id="run-active"))
    fake_host = _FakeHost(
        watcher=watcher,
        session_snapshots=(
            _session_snapshot(
                session_id="session-1",
                slot_key=None,
                active_run_id="run-active",
            ),
            _session_snapshot(session_id="session-1", slot_key=None),
        ),
        outbox_batches=(
            _outbox_batch(
                items=(),
                next_sequence=0,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
            _outbox_batch(
                items=(_outbox_item(event_sequence=8, run_id="run-active"),),
                next_sequence=8,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
        ),
    )

    result = await startup_reconnect_entrypoint_session(
        cast(Host, fake_host),
        request=_startup_request(),
    )

    assert [terminal.run_id for terminal in result.terminal_results] == ["run-active"]
    assert "get_run:run-active" not in fake_host.calls


@pytest.mark.asyncio
async def test_startup_reconnect_does_not_read_next_target_before_ack_and_rebind() -> None:
    """A terminal ack/rebind B 之前 sole consumer 不得预读 B。

    :returns: ``None``。
    :raises Exception: generation handshake 断言失败时由 pytest 抛出。
    """

    watcher = _FakeHostEventIterator()
    await watcher.push(_terminal_event(event_sequence=8, run_id="run-a"))
    await watcher.push(_terminal_event(event_sequence=9, run_id="run-b"))
    fake_host = _StartupReadProbeHost(
        watcher=watcher,
        session_snapshots=(
            _session_snapshot(
                session_id="session-1",
                slot_key=None,
                active_run_id="run-a",
            ),
            _session_snapshot(
                session_id="session-1",
                slot_key=None,
                active_run_id="run-b",
            ),
            _session_snapshot(session_id="session-1", slot_key=None),
        ),
        outbox_batches=(
            _outbox_batch(
                items=(),
                next_sequence=0,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
            _outbox_batch(
                items=(),
                next_sequence=9,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
        ),
    )

    result = await startup_reconnect_entrypoint_session(
        cast(Host, fake_host),
        request=_startup_request(),
    )

    assert [terminal.run_id for terminal in result.terminal_results] == [
        "run-a",
        "run-b",
    ]
    assert fake_host.item_indices_before_session_read == [0, 1, 2]
    assert watcher.closed_count == 1
    assert watcher.close_observed_active_anext is False


@pytest.mark.asyncio
async def test_startup_reconnect_waits_for_queued_promotion_then_observes_terminal() -> None:
    """queued-only startup 应等待 promotion，promoted 后观察 terminal。"""

    sleep = _SleepRecorder()
    watcher = _FakeHostEventIterator()
    await watcher.push(_terminal_event(event_sequence=9, run_id="run-queued"))
    fake_host = _FakeHost(
        watcher=watcher,
        session_snapshots=(
            _session_snapshot(
                session_id="session-1",
                slot_key=None,
                queued_run_ids=("run-queued",),
            ),
            _session_snapshot(
                session_id="session-1",
                slot_key=None,
                queued_run_ids=("run-queued",),
            ),
            _session_snapshot(
                session_id="session-1",
                slot_key=None,
                active_run_id="run-queued",
            ),
            _session_snapshot(session_id="session-1", slot_key=None),
        ),
        outbox_batches=(
            _outbox_batch(
                items=(),
                next_sequence=0,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
            _outbox_batch(
                items=(_outbox_item(event_sequence=9, run_id="run-queued"),),
                next_sequence=9,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
        ),
    )

    result = await startup_reconnect_entrypoint_session(
        cast(Host, fake_host),
        request=_startup_request(promotion_max_attempts=2),
        sleep=sleep,
    )

    assert [terminal.run_id for terminal in result.terminal_results] == ["run-queued"]
    assert sleep.calls == [0.05]


@pytest.mark.asyncio
async def test_startup_reconnect_queued_only_exhaustion_fails_before_input() -> None:
    """queued-only bounded wait 耗尽时必须失败，不允许静默进入输入态。"""

    sleep = _SleepRecorder()
    fake_host = _FakeHost(
        session_snapshots=(
            _session_snapshot(
                session_id="session-1",
                slot_key=None,
                queued_run_ids=("run-queued",),
            ),
        )
    )

    with pytest.raises(EntrypointRuntimeError, match="queued Run"):
        await startup_reconnect_entrypoint_session(
            cast(Host, fake_host),
            request=_startup_request(promotion_max_attempts=1),
            sleep=sleep,
        )

    assert sleep.calls == [0.05]


@pytest.mark.asyncio
async def test_submit_non_delivery_iterator_failure_uses_stable_wrapper(
    tmp_path: Path,
) -> None:
    """非 delivery iterator failure 不得误入 durable recovery。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises Exception: iterator disposition 断言失败时由 pytest 抛出。
    """

    runtime = await _prepare_runtime(tmp_path)
    activities: list[EntrypointActivity] = []
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

    with pytest.raises(
        EntrypointRuntimeError,
        match="session_event_iterator_failed_before_terminal",
    ) as exc_info:
        await submit_entrypoint_turn_and_wait(
            cast(Host, fake_host),
            request=_turn_request(),
            scene_inputs=runtime.scene_inputs,
            host_assembly=runtime.host_assembly,
            on_activity=activities.append,
            callback_execution_port=_InlineCallbackExecutionPort(),
        )

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert str(exc_info.value.__cause__) == "watch stream disconnected"
    assert fake_host.read_outbox_requests == []
    assert activities == []


@pytest.mark.asyncio
async def test_submit_event_projection_failure_first_commits_iterator_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """event projection failure 应 fail fast 并按 ITERATOR_FAILED 精确关闭。

    :param tmp_path: pytest 临时 workspace root。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises Exception: exact-five disposition 或 cleanup 断言失败时由 pytest 抛出。
    """

    runtime = await _prepare_runtime(tmp_path)
    projection_error = RuntimeError("activity projection failed")
    projection = _FailingActivityProjection(projection_error)
    monkeypatch.setattr(
        entrypoint_runtime,
        "_entrypoint_activity_from_host_event",
        projection,
    )
    watcher = _FakeHostEventIterator()
    fake_host = _FakeHost(
        watcher=watcher,
        submit_events=(
            _activity_event(
                event_sequence=2,
                run_id="run-1",
                dedupe_key="projection-failure",
            ),
        ),
    )
    activities: list[EntrypointActivity] = []

    with pytest.raises(EntrypointRuntimeError) as exc_info:
        await asyncio.wait_for(
            submit_entrypoint_turn_and_wait(
                cast(Host, fake_host),
                request=_turn_request(),
                scene_inputs=runtime.scene_inputs,
                host_assembly=runtime.host_assembly,
                on_activity=activities.append,
                callback_execution_port=_InlineCallbackExecutionPort(),
            ),
            timeout=1.0,
        )

    assert str(exc_info.value) == "session_event_iterator_failed_before_terminal"
    assert exc_info.value.__cause__ is projection_error
    assert fake_host.read_outbox_requests == []
    assert activities == []
    assert watcher.closed_count == 1
    assert watcher.close_observed_active_anext is False


@pytest.mark.asyncio
async def test_cancel_entrypoint_run_reads_outbox_pages_until_target() -> None:
    """未 attach 补读路径必须按 has_more 分页推进直到命中目标 Run。"""

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

    result = await cancel_entrypoint_run_and_wait(
        cast(Host, fake_host),
        request=_cancel_request(),
    )

    assert result.run_id == "run-1"
    assert fake_host.read_outbox_requests[0].after == OutboxTerminalCursor(event_sequence=0)
    assert fake_host.read_outbox_requests[1].after == OutboxTerminalCursor(event_sequence=4)


@pytest.mark.asyncio
async def test_cancel_entrypoint_run_retries_when_outbox_lagged() -> None:
    """补读路径下 outbox LAGGED 且未命中时必须继续轮询。"""

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

    result = await cancel_entrypoint_run_and_wait(
        cast(Host, fake_host),
        request=_cancel_request(),
        sleep=sleep,
    )

    assert result.run_id == "run-1"
    assert sleep.calls == [0.05]


@pytest.mark.asyncio
async def test_cancel_entrypoint_run_raises_on_outbox_projection_failed() -> None:
    """补读路径下 outbox projection FAILED 必须转为 Service error。"""

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
        await cancel_entrypoint_run_and_wait(
            cast(Host, fake_host),
            request=_cancel_request(),
        )


@pytest.mark.asyncio
async def test_cancel_entrypoint_run_raises_when_caught_up_without_match() -> None:
    """补读路径已追平仍无目标 terminal 时必须报 contract error。"""

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
        await cancel_entrypoint_run_and_wait(
            cast(Host, fake_host),
            request=_cancel_request(),
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
async def test_submit_delivery_interruption_recovers_once_and_closes_iterator(
    tmp_path: Path,
) -> None:
    """typed delivery interruption 应只做一次 durable recovery 并精确关闭。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises Exception: recovery/cleanup 断言失败时由 pytest 抛出。
    """

    delivery_error = HostApiError(
        code=HostApiErrorCode.DELIVERY_INTERRUPTED,
        message="delivery interrupted",
        retryable=False,
        detail=HostSessionEventDeliveryDetail(
            reason=HostSessionEventDeliveryReason.TRANSIENT_MAILBOX_OVERFLOW,
        ),
    )
    fake_host = _FakeHost(
        submit_watcher_errors=(delivery_error,),
        run_statuses=(RunStatus.SUCCEEDED,),
        outbox_batches=(
            _outbox_batch(
                items=(_outbox_item(event_sequence=9, run_id="run-1"),),
                next_sequence=9,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
        ),
    )

    runtime = await _prepare_runtime(tmp_path)
    result = await submit_entrypoint_turn_and_wait(
        cast(Host, fake_host),
        request=_turn_request(),
        scene_inputs=runtime.scene_inputs,
        host_assembly=runtime.host_assembly,
    )

    assert result.source is EntrypointTerminalSource.OUTBOX_READ
    assert fake_host.watchers[0].closed_count == 1
    assert fake_host.calls.count("read_outbox:session-1") == 1


@pytest.mark.asyncio
async def test_submit_eof_and_close_failure_preserves_stable_primary_chain(
    tmp_path: Path,
) -> None:
    """EOF + close failure 应保持 stable wrapper 为 top-level。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises Exception: exception chain 断言失败时由 pytest 抛出。
    """

    close_error = RuntimeError("close failed")
    watcher = _FakeHostEventIterator(close_error=close_error)
    watcher._closed = True
    fake_host = _FakeHost(watcher=watcher)

    with pytest.raises(
        EntrypointRuntimeError,
        match="session_event_iterator_ended_before_terminal",
    ) as exc_info:
        runtime = await _prepare_runtime(tmp_path)
        await submit_entrypoint_turn_and_wait(
            cast(Host, fake_host),
            request=_turn_request(),
            scene_inputs=runtime.scene_inputs,
            host_assembly=runtime.host_assembly,
        )

    assert exc_info.value.__cause__ is close_error
    assert watcher.closed_count == 1


@pytest.mark.asyncio
async def test_submit_public_iterator_and_close_failures_preserve_identity(
    tmp_path: Path,
) -> None:
    """public iterator + close 应保持 public failure 为 top-level identity。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises Exception: public failure identity 断言失败时由 pytest 抛出。
    """

    runtime = await _prepare_runtime(tmp_path)
    iterator_error = HostClosedError("public iterator failed")
    close_error = RuntimeError("public iterator cleanup failed")
    watcher = _FakeHostEventIterator(close_error=close_error)
    fake_host = _FakeHost(
        watcher=watcher,
        submit_watcher_errors=(iterator_error,),
    )

    with pytest.raises(HostClosedError, match="public iterator failed") as exc_info:
        await submit_entrypoint_turn_and_wait(
            cast(Host, fake_host),
            request=_turn_request(),
            scene_inputs=runtime.scene_inputs,
            host_assembly=runtime.host_assembly,
        )

    assert exc_info.value is iterator_error
    assert exc_info.value.__cause__ is close_error
    assert watcher.closed_count == 1


@pytest.mark.asyncio
async def test_submit_nonpublic_iterator_and_close_failures_keep_three_level_chain(
    tmp_path: Path,
) -> None:
    """non-public iterator + close 应形成 wrapper→original→close 固定链。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises Exception: 三层异常链断言失败时由 pytest 抛出。
    """

    runtime = await _prepare_runtime(tmp_path)
    iterator_error = RuntimeError("nonpublic iterator failed")
    close_error = RuntimeError("nonpublic iterator cleanup failed")
    watcher = _FakeHostEventIterator(close_error=close_error)
    fake_host = _FakeHost(
        watcher=watcher,
        submit_watcher_errors=(iterator_error,),
    )

    with pytest.raises(
        EntrypointRuntimeError,
        match="session_event_iterator_failed_before_terminal",
    ) as exc_info:
        await submit_entrypoint_turn_and_wait(
            cast(Host, fake_host),
            request=_turn_request(),
            scene_inputs=runtime.scene_inputs,
            host_assembly=runtime.host_assembly,
        )

    assert exc_info.value.__cause__ is iterator_error
    assert iterator_error.__cause__ is close_error
    assert watcher.closed_count == 1


@pytest.mark.asyncio
async def test_submit_terminal_close_failure_returns_terminal_and_swallows_diagnostic_failure(
    tmp_path: Path,
) -> None:
    """terminal + close 应返回终态并最多输出一次固定去敏诊断。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises Exception: terminal/diagnostic 断言失败时由 pytest 抛出。
    """

    runtime = await _prepare_runtime(tmp_path)
    close_error = RuntimeError("terminal cleanup secret")
    watcher = _FakeHostEventIterator(close_error=close_error)
    diagnostics: list[EntrypointActivity] = []
    fake_host = _FakeHost(
        watcher=watcher,
        submit_events=(_terminal_event(event_sequence=3, run_id="run-1"),),
    )

    def fail_after_record(activity: EntrypointActivity) -> None:
        """记录去敏诊断后模拟 diagnostic callback failure。

        :param activity: Service cleanup diagnostic。
        :returns: 本函数不返回。
        :raises RuntimeError: 始终抛出测试异常。
        """

        diagnostics.append(activity)
        raise RuntimeError("diagnostic callback failed")

    result = await submit_entrypoint_turn_and_wait(
        cast(Host, fake_host),
        request=_turn_request(),
        scene_inputs=runtime.scene_inputs,
        host_assembly=runtime.host_assembly,
        on_activity=fail_after_record,
        callback_execution_port=_InlineCallbackExecutionPort(),
    )

    assert result.terminal_event_id == "terminal-run-1-3"
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.kind is EntrypointActivityKind.WATCHER_DIAGNOSTIC
    assert diagnostic.dedupe_key == "entrypoint_watcher_cleanup_failed"
    assert diagnostic.title == "运行事件流清理失败"
    assert diagnostic.summary == "已保留终态结果，但运行事件观察器清理失败。"
    assert "secret" not in f"{diagnostic.title}{diagnostic.summary}"
    assert watcher.closed_count == 1


@pytest.mark.asyncio
async def test_submit_delivery_recovery_success_ignores_close_failure(
    tmp_path: Path,
) -> None:
    """delivery recovery 成功后 close failure 不得覆盖同一 durable terminal。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises Exception: terminal identity 断言失败时由 pytest 抛出。
    """

    delivery_error = HostApiError(
        code=HostApiErrorCode.DELIVERY_INTERRUPTED,
        message="delivery interrupted",
        retryable=False,
        detail=HostSessionEventDeliveryDetail(
            reason=HostSessionEventDeliveryReason.TRANSIENT_MAILBOX_OVERFLOW,
        ),
    )
    close_error = RuntimeError("delivery cleanup failed")
    watcher = _FakeHostEventIterator(close_error=close_error)
    fake_host = _FakeHost(
        watcher=watcher,
        submit_watcher_errors=(delivery_error,),
        run_statuses=(RunStatus.SUCCEEDED,),
        outbox_batches=(
            _outbox_batch(
                items=(_outbox_item(event_sequence=9, run_id="run-1"),),
                next_sequence=9,
                projection_status=OutboxProjectionStatus.CAUGHT_UP,
            ),
        ),
    )
    runtime = await _prepare_runtime(tmp_path)

    result = await submit_entrypoint_turn_and_wait(
        cast(Host, fake_host),
        request=_turn_request(),
        scene_inputs=runtime.scene_inputs,
        host_assembly=runtime.host_assembly,
    )

    assert result.source is EntrypointTerminalSource.OUTBOX_READ
    assert result.terminal_event_id == "terminal-run-1-9"
    assert watcher.closed_count == 1


@pytest.mark.asyncio
async def test_submit_delivery_recovery_failure_keeps_delivery_and_close_chain(
    tmp_path: Path,
) -> None:
    """delivery recovery + close 应形成 recovery→delivery→close 固定链。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises Exception: recovery 异常链断言失败时由 pytest 抛出。
    """

    delivery_error = HostApiError(
        code=HostApiErrorCode.DELIVERY_INTERRUPTED,
        message="delivery interrupted",
        retryable=False,
        detail=HostSessionEventDeliveryDetail(
            reason=HostSessionEventDeliveryReason.TRANSIENT_MAILBOX_OVERFLOW,
        ),
    )
    recovery_error = RuntimeError("durable recovery failed")
    close_error = RuntimeError("delivery cleanup failed")
    watcher = _FakeHostEventIterator(close_error=close_error)
    fake_host = _RecoveryFailingHost(
        recovery_error,
        watcher=watcher,
        delivery_error=delivery_error,
    )
    runtime = await _prepare_runtime(tmp_path)

    with pytest.raises(RuntimeError, match="durable recovery failed") as exc_info:
        await submit_entrypoint_turn_and_wait(
            cast(Host, fake_host),
            request=_turn_request(),
            scene_inputs=runtime.scene_inputs,
            host_assembly=runtime.host_assembly,
        )

    assert exc_info.value is recovery_error
    assert exc_info.value.__cause__ is delivery_error
    assert delivery_error.__cause__ is close_error
    assert watcher.closed_count == 1


@pytest.mark.asyncio
async def test_startup_slot_empty_close_failure_uses_stable_cleanup_disposition() -> None:
    """startup 空 slot + close 应使用唯一 cleanup stable wrapper。

    :returns: ``None``。
    :raises Exception: slot-empty cleanup 断言失败时由 pytest 抛出。
    """

    close_error = RuntimeError("idle cleanup failed")
    watcher = _FakeHostEventIterator(close_error=close_error)
    fake_host = _FakeHost(watcher=watcher)

    with pytest.raises(
        EntrypointRuntimeError,
        match="session_event_iterator_cleanup_failed",
    ) as exc_info:
        await startup_reconnect_entrypoint_session(
            cast(Host, fake_host),
            request=_startup_request(),
        )

    assert exc_info.value.__cause__ is close_error
    assert watcher.closed_count == 1
    assert watcher.close_observed_active_anext is False


@pytest.mark.asyncio
async def test_submit_caller_cancellation_waits_callback_then_chains_close_failure(
    tmp_path: Path,
) -> None:
    """caller cancellation + close 应等待当前 callback 并保留 cancellation primary。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises Exception: cancellation/cleanup 断言失败时由 pytest 抛出。
    """

    runtime = await _prepare_runtime(tmp_path)
    close_error = RuntimeError("cancel cleanup failed")
    watcher = _FakeHostEventIterator(close_error=close_error)
    port = _BlockingCallbackExecutionPort()
    activities: list[EntrypointActivity] = []
    fake_host = _FakeHost(
        watcher=watcher,
        submit_events=(
            _activity_event(
                event_sequence=2,
                run_id="run-1",
                dedupe_key="cancel-blocking-callback",
            ),
        ),
    )
    submit_task = asyncio.create_task(
        submit_entrypoint_turn_and_wait(
            cast(Host, fake_host),
            request=_turn_request(),
            scene_inputs=runtime.scene_inputs,
            host_assembly=runtime.host_assembly,
            on_activity=activities.append,
            callback_execution_port=port,
        )
    )
    await port.started.wait()

    submit_task.cancel()
    await asyncio.sleep(0)
    assert submit_task.done() is False
    assert watcher.closed_count == 0
    port.release.set()
    with pytest.raises(asyncio.CancelledError) as exc_info:
        await submit_task

    assert exc_info.value.__cause__ is close_error
    assert port.finished.is_set()
    assert watcher.closed_count == 1
    assert watcher.close_observed_active_anext is False


def test_observation_state_rejects_old_generation_and_stop_late_commits() -> None:
    """capacity-one slot 应拒绝旧 generation 五类结果及 stop 后 late commit。

    :returns: ``None``。
    :raises Exception: generation/stop 仲裁断言失败时由 pytest 抛出。
    """

    state = entrypoint_runtime._ServiceObservationState()
    first_generation = state.bind("run-1")
    assert first_generation == 1
    first_terminal = entrypoint_runtime._TargetTerminal(
        target_generation=first_generation,
        result=_service_terminal_result(run_id="run-1", event_sequence=1),
    )
    assert state.try_commit(first_terminal, target_run_id="run-1") is True
    assert (
        state.try_commit(
            entrypoint_runtime._IteratorEnded(
                target_generation=first_generation,
            ),
            target_run_id="run-1",
        )
        is False
    )
    assert state.ack_target_terminal(first_generation) is first_terminal
    second_generation = state.bind("run-2")
    delivery_error = HostApiError(
        code=HostApiErrorCode.DELIVERY_INTERRUPTED,
        message="old generation delivery",
        retryable=False,
        detail=HostSessionEventDeliveryDetail(
            reason=HostSessionEventDeliveryReason.TRANSIENT_MAILBOX_OVERFLOW,
        ),
    )
    stale_results: tuple[entrypoint_runtime._ServiceObservationResult, ...] = (
        entrypoint_runtime._TargetTerminal(
            target_generation=first_generation,
            result=_service_terminal_result(run_id="run-1", event_sequence=1),
        ),
        entrypoint_runtime._DeliveryInterrupted(
            target_generation=first_generation,
            error=delivery_error,
        ),
        entrypoint_runtime._IteratorEnded(target_generation=first_generation),
        entrypoint_runtime._CallbackFailed(
            target_generation=first_generation,
            callback_kind=entrypoint_runtime._CallbackKind.ACTIVITY,
            error=RuntimeError("old callback"),
        ),
        entrypoint_runtime._IteratorFailed(
            target_generation=first_generation,
            error=RuntimeError("old iterator"),
        ),
    )
    for stale_result in stale_results:
        assert state.try_commit(stale_result, target_run_id="run-1") is False
        assert state.result is None

    state.request_stop()
    assert (
        state.try_commit(
            entrypoint_runtime._IteratorEnded(
                target_generation=second_generation,
            ),
            target_run_id="run-2",
        )
        is False
    )


def test_observation_state_fatal_result_is_sticky_and_not_acknowledgeable() -> None:
    """非 terminal fatal result 必须粘滞，且不能 ack/reuse generation。

    :returns: ``None``。
    :raises Exception: fatal sticky 断言失败时由 pytest 抛出。
    """

    state = entrypoint_runtime._ServiceObservationState()
    generation = state.bind("run-1")
    fatal = entrypoint_runtime._IteratorEnded(target_generation=generation)

    assert state.try_commit(fatal, target_run_id="run-1") is True
    assert state.result is fatal
    with pytest.raises(RuntimeError, match="only target terminal"):
        state.ack_target_terminal(generation)
    with pytest.raises(RuntimeError, match="only bind while unbound"):
        state.bind("run-2")


def test_terminal_identity_dedupe_uses_seen_terminal_event_ids_for_both_sources() -> None:
    """live 与 Outbox 都必须按同一 seen terminal event id 真源去重。

    :returns: ``None``。
    :raises Exception: owner contract 断言失败时由 pytest 抛出。
    """

    terminal_event_id = "terminal-run-1-2"
    live_state = entrypoint_runtime._new_terminal_observation_state(
        seen_terminal_event_ids=frozenset({terminal_event_id})
    )
    live_terminal = entrypoint_runtime._terminal_result_from_live_event(
        _terminal_event(
            event_sequence=2,
            run_id="run-1",
            dedupe_key="changed-live-dedupe-key",
        ),
        run_id="run-1",
        state=live_state,
    )

    outbox_state = entrypoint_runtime._new_terminal_observation_state(
        seen_terminal_event_ids=frozenset({terminal_event_id})
    )
    outbox_terminal = entrypoint_runtime._scan_outbox_terminal_items(
        items=(_outbox_item(event_sequence=2, run_id="run-1"),),
        run_id="run-1",
        state=outbox_state,
    )

    assert live_terminal is None
    assert outbox_terminal is None
    assert live_state.last_observed_event_sequence == 2
    assert outbox_state.last_observed_event_sequence == 2


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
                CURRENT_TIME_SLOT: current_time(_NOW),
                "fins_default_subject": "测试财报主体",
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

    target_path = workspace_root / "config" / "tool_discovery.json"
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


def _service_terminal_result(
    *,
    run_id: str,
    event_sequence: int,
) -> EntrypointRunTerminalResult:
    """构造 observation state 测试使用的 Service terminal DTO。

    :param run_id: 目标 Run id。
    :param event_sequence: terminal event sequence。
    :returns: 固定成功 terminal result。
    :raises Exception: DTO contract 非法时由构造函数抛出。
    """

    terminal_event_id = f"terminal-{run_id}-{event_sequence}"
    return EntrypointRunTerminalResult(
        source=EntrypointTerminalSource.LIVE_EVENT,
        session_id="session-1",
        run_id=run_id,
        terminal_event_id=terminal_event_id,
        event_sequence=event_sequence,
        terminal_status=HostTerminalStatus.SUCCEEDED,
        dedupe_key=terminal_event_id,
        final_answer=_final_answer(run_id=run_id),
        error_message=None,
        cancel_reason=None,
        watcher_failure_message=None,
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


def _startup_request(
    *,
    seen_terminal_event_ids: frozenset[str] = frozenset(),
    outbox_lagged_max_attempts: int = 3,
    promotion_max_attempts: int = 3,
) -> EntrypointStartupReconnectRequest:
    """构造默认 startup reconnect request。

    :param seen_terminal_event_ids: 已展示 terminal id 集合。
    :param outbox_lagged_max_attempts: outbox LAGGED 最大重试次数。
    :param promotion_max_attempts: queued promotion 最大轮询次数。
    :returns: startup reconnect request。
    :raises Exception: 不主动抛出异常。
    """

    return EntrypointStartupReconnectRequest(
        context=_host_context("startup-context"),
        session_id="session-1",
        terminal_cursor=OutboxTerminalCursor(event_sequence=0),
        seen_terminal_event_ids=seen_terminal_event_ids,
        poll_interval_seconds=0.05,
        outbox_lagged_max_attempts=outbox_lagged_max_attempts,
        promotion_poll_interval_seconds=0.05,
        promotion_max_attempts=promotion_max_attempts,
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


def _session_snapshot(
    *,
    session_id: str,
    slot_key: str | None,
    active_run_id: str | None = None,
    queued_run_ids: tuple[str, ...] = (),
) -> SessionSnapshot:
    """构造测试 SessionSnapshot。

    :param session_id: Session id。
    :param slot_key: slot key。
    :param active_run_id: 当前 active Run id。
    :param queued_run_ids: 当前 queued Run ids。
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
        active_run_id=active_run_id,
        queued_run_ids=queued_run_ids,
        timeline_cursor=HostStreamCursor(event_sequence=0),
    )


def _run_snapshot(*, run_id: str, status: RunStatus) -> RunSnapshot:
    """构造测试 RunSnapshot。

    :param run_id: Run id。
    :param status: Run status。
    :returns: RunSnapshot。
    :raises Exception: 不主动抛出异常。
    """

    terminal_summary = None
    if is_terminal_run_status(status):
        terminal_summary = TerminalResultSummary(
            status=status,
            summary_ref=None,
            summary_digest=None,
        )
    return RunSnapshot(
        run_id=run_id,
        session_id="session-1",
        status=status,
        current_attempt_id=None,
        terminal_result_summary=terminal_summary,
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
    dedupe_key: str | None = None,
) -> HostEvent:
    """构造测试 terminal HostEvent。

    :param event_sequence: event sequence。
    :param run_id: Run id。
    :param terminal_status: terminal 状态。
    :param dedupe_key: Host public dedupe key；``None`` 表示使用默认 terminal key。
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
        event_class=HostEventClass.CANONICAL_FACT,
        event_type=_event_type_for_terminal_status(terminal_status),
        kind=kind,
        activity=None,
        dedupe_key=dedupe_key if dedupe_key is not None else f"terminal-{run_id}-{event_sequence}",
        terminal_status=terminal_status,
        final_answer=final_answer,
        error_message=("run failed" if terminal_status is HostTerminalStatus.FAILED else None),
        cancel_reason=("cli_sigint" if terminal_status is HostTerminalStatus.CANCELLED else None),
    )


def _activity_event(
    *,
    event_sequence: int,
    run_id: str,
    dedupe_key: str,
    activity_kind: HostActivityKind = HostActivityKind.TOOL_BATCH,
    activity_status: HostActivityStatus = HostActivityStatus.COMPLETED,
) -> HostEvent:
    """构造带 Host public activity 的 progress HostEvent。

    :param event_sequence: event sequence。
    :param run_id: Run id。
    :param dedupe_key: Host public dedupe key。
    :param activity_kind: Host public activity kind。
    :param activity_status: Host public activity status。
    :returns: HostEvent。
    :raises Exception: 不主动抛出异常。
    """

    return HostEvent(
        event_id=f"activity-{run_id}-{event_sequence}",
        event_sequence=event_sequence,
        session_id="session-1",
        run_id=run_id,
        event_class=HostEventClass.DIAGNOSTIC,
        event_type="IGNORED_BY_SERVICE_UI_BRANCHING",
        kind=HostEventKind.PROGRESS,
        activity=HostActivityView(
            kind=activity_kind,
            status=activity_status,
            title="工具批次完成",
            summary="完成 2 个工具调用。",
            severity=HostActivitySeverity.INFO,
            tool_name="record_smoke_fact",
            tool_display_name="记录烟测事实",
            counts=HostActivityCounts(
                total=2,
                completed=2,
                failed=0,
                cancelled=0,
            ),
        ),
        dedupe_key=dedupe_key,
        terminal_status=None,
        final_answer=None,
        error_message=None,
        cancel_reason=None,
    )


def _transient_delta(
    *,
    runtime_sequence: int,
    run_id: str,
    dedupe_key: str,
    transient_type: HostTransientDeltaType,
    data: HostContentDelta | HostReasoningDelta | HostToolCallDelta,
) -> HostTransientDelta:
    """构造 Host public transient delta。

    :param runtime_sequence: 当前 Host runtime 瞬态序列。
    :param run_id: Run id。
    :param dedupe_key: Host public dedupe key。
    :param transient_type: Host public delta discriminator。
    :param data: 与 discriminator 对应的 public payload。
    :returns: HostTransientDelta。
    :raises ValueError: public envelope contract 校验失败时抛出。
    """

    return HostTransientDelta(
        runtime_id="runtime-1",
        runtime_sequence=runtime_sequence,
        session_id="session-1",
        run_id=run_id,
        attempt_id="attempt-1",
        execution_id="execution-1",
        worker_event_index=runtime_sequence,
        observed_at=_NOW,
        type=transient_type,
        data=data,
        dedupe_key=dedupe_key,
    )


def _progress_without_activity(*, event_sequence: int, run_id: str) -> HostEvent:
    """构造没有 public activity 的 progress HostEvent。

    :param event_sequence: event sequence。
    :param run_id: Run id。
    :returns: HostEvent。
    :raises Exception: 不主动抛出异常。
    """

    return HostEvent(
        event_id=f"progress-{run_id}-{event_sequence}",
        event_sequence=event_sequence,
        session_id="session-1",
        run_id=run_id,
        event_class=HostEventClass.PREVIEW,
        event_type="CONTENT_DELTA",
        kind=HostEventKind.PROGRESS,
        activity=None,
        dedupe_key=f"progress-{run_id}-{event_sequence}",
        terminal_status=None,
        final_answer=None,
        error_message=None,
        cancel_reason=None,
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


def _event_type_for_terminal_status(
    terminal_status: HostTerminalStatus,
) -> str:
    """把 terminal status 映射为测试 EventLog event_type。

    :param terminal_status: terminal status。
    :returns: EventLog event_type。
    :raises AssertionError: 未覆盖的 terminal status 时抛出。
    """

    if terminal_status is HostTerminalStatus.SUCCEEDED:
        return "RUN_SUCCEEDED"
    if terminal_status is HostTerminalStatus.FAILED:
        return "RUN_FAILED"
    if terminal_status is HostTerminalStatus.CANCELLED:
        return "RUN_CANCELLED"
    if terminal_status is HostTerminalStatus.LOST:
        return "RUN_LOST"
    raise AssertionError(f"unexpected terminal status: {terminal_status}")
