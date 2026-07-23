"""真实 Host→Service→CLI delivery interruption 路径测试。"""

from __future__ import annotations

import asyncio
import io
import pathlib
import threading
from contextlib import AsyncExitStack
from dataclasses import replace
from typing import cast

import pytest

from dayu.cli.agent_entrypoint import package_config_root
from dayu.cli.exit_codes import EXIT_SUCCESS
from dayu.cli.output import render_prompt_terminal_result
from dayu.cli.runtime_display import RuntimeDisplayController
from dayu.cli.thinking import CliThinkingRenderer, CliThinkingRendererOptions
from dayu.host import (
    FollowupBehavior,
    FollowupSnapshot,
    Host,
    HostApiError,
    HostApiErrorCode,
    HostEvent,
    HostSessionEvent,
    HostSessionEventDeliveryDetail,
    HostSessionEventDeliveryPolicy,
    HostSessionEventDeliveryReason,
    HostSessionEventIterator,
    OutboxTerminalCursor,
    OutboxTerminalItemsBatch,
    ReadOutboxTerminalItemsRequest,
    RunSnapshot,
    RunStatus,
    SubmitFollowupRequest,
    open_host,
)
from dayu.service.entrypoint_runtime import (
    EntrypointActivity,
    EntrypointRuntimeRequest,
    EntrypointTerminalSource,
    EntrypointThinking,
    EntrypointTurnRequest,
    prepare_entrypoint_runtime,
    submit_entrypoint_turn_and_wait,
)
from dayu.service.host_assembly import ServiceAssemblyOverrides, ServiceRunOverrides
from tests.host.public_smoke_support import (
    close_attachment_shielded,
    ensure_request,
    followup_request,
    host_context,
)
from tests.host.transient_stream_support import (
    TransientStreamCounts,
    TransientStreamWorkerFactory,
    event_log_type_count,
    read_transient_durable_snapshot,
)

_DELTA_COUNT_PER_TYPE = 400
_HOST_MAILBOX_MAX_ITEMS = 32
_E2E_TIMEOUT_SECONDS = 30.0
_FINAL_ANSWER = "delivery-interruption-final"


class _ObservedHostSessionEventIterator:
    """只观测真实 Host iterator 交付与原异常 identity 的透明 wrapper。"""

    def __init__(
        self,
        *,
        inner: HostSessionEventIterator,
        owner: _SlowConsumerHostProbe,
    ) -> None:
        """初始化透明 iterator probe。

        :param inner: 真实 Host Session event iterator。
        :param owner: 汇总观测结果的 Host probe。
        :returns: 无返回值。
        :raises Exception: 本构造函数不主动抛出异常。
        """

        self._inner = inner
        self._owner = owner

    def __aiter__(self) -> _ObservedHostSessionEventIterator:
        """返回当前 iterator。

        :returns: 当前实例。
        :raises Exception: 本方法不主动抛出异常。
        """

        return self

    async def __anext__(self) -> HostSessionEvent:
        """转发真实 Host item，并记录 terminal 与原 typed error。

        :returns: 下一条真实 Host Session event。
        :raises HostApiError: 真实 Host iterator 的原异常原样透传。
        :raises StopAsyncIteration: 真实 Host iterator 正常结束时透传。
        """

        try:
            event = await anext(self._inner)
        except HostApiError as exc:
            self._owner.host_errors.append(exc)
            raise
        self._owner.yielded_count += 1
        if isinstance(event, HostEvent) and event.terminal_status is not None:
            self._owner.live_terminal_event_ids.append(event.event_id)
        return event

    async def aclose(self) -> None:
        """转发到真实 Host iterator cleanup。

        :returns: ``None``。
        :raises Exception: 真实 Host iterator cleanup 失败时透传。
        """

        await self._inner.aclose()


class _SlowConsumerHostProbe:
    """透明观测 Service 使用的真实 Host public 调用。"""

    def __init__(self, host: Host) -> None:
        """初始化真实 Host public probe。

        :param host: ``open_host`` 返回的真实 public Host。
        :returns: 无返回值。
        :raises Exception: 本构造函数不主动抛出异常。
        """

        self._host = host
        self.submit_completed = asyncio.Event()
        self.accepted_run_id: str | None = None
        self.yielded_count = 0
        self.host_errors: list[HostApiError] = []
        self.live_terminal_event_ids: list[str] = []
        self.get_run_call_count = 0
        self.outbox_read_call_count = 0

    async def watch_session_events(
        self,
        session_id: str,
    ) -> HostSessionEventIterator:
        """异步 attach 真实 Host watcher，并返回透明观测 wrapper。

        :param session_id: 目标 Session 标识。
        :returns: 透明包装后的真实 Host iterator。
        :raises HostApiError: Host watch attach 失败时透传。
        """

        return _ObservedHostSessionEventIterator(
            inner=await self._host.watch_session_events(session_id),
            owner=self,
        )

    async def submit_followup(
        self,
        session_id: str,
        request: SubmitFollowupRequest,
    ) -> FollowupSnapshot:
        """转发真实 submit 并记录 accepted Run identity。

        :param session_id: 目标 Session 标识。
        :param request: Host public follow-up 请求。
        :returns: 真实 Host follow-up snapshot。
        :raises HostApiError: Host submit 失败时透传。
        """

        result = await self._host.submit_followup(session_id, request)
        self.accepted_run_id = result.accepted_run_id
        self.submit_completed.set()
        return result

    async def get_run(self, run_id: str) -> RunSnapshot:
        """转发 durable Run read 并记录 recovery 调用次数。

        :param run_id: 目标 Run 标识。
        :returns: 真实 Run snapshot。
        :raises HostApiError: Host read 失败时透传。
        :raises asyncio.CancelledError: Service task 被取消时透传。
        """

        self.get_run_call_count += 1
        return await self._host.get_run(run_id)

    async def read_outbox_terminal_items(
        self,
        session_id: str,
        request: ReadOutboxTerminalItemsRequest,
    ) -> OutboxTerminalItemsBatch:
        """转发 Service fallback 使用的真实 Outbox read。

        :param session_id: 目标 Session 标识。
        :param request: public Outbox read 请求。
        :returns: 真实 Outbox terminal batch。
        :raises HostApiError: Host Outbox read 失败时透传。
        """

        self.outbox_read_call_count += 1
        return await self._host.read_outbox_terminal_items(session_id, request)


class _BlockingThinkingRenderer:
    """在首个 thinking 增量建立可控阻塞 barrier 的 CLI renderer。"""

    def __init__(self, inner: CliThinkingRenderer) -> None:
        """初始化 renderer wrapper。

        :param inner: 真实 CLI thinking renderer。
        :returns: 无返回值。
        :raises Exception: 本构造函数不主动抛出异常。
        """

        self._inner = inner
        self._blocked = threading.Event()
        self._release = threading.Event()
        self.record_call_count = 0
        self.close_call_count = 0

    @property
    def blocked(self) -> bool:
        """返回 callback 是否已进入阻塞点。

        :returns: 已进入阻塞点时返回 ``True``。
        :raises Exception: 本属性不主动抛出异常。
        """

        return self._blocked.is_set()

    def record(self, thinking: EntrypointThinking) -> None:
        """阻塞首个 callback，恢复后交给真实 renderer。

        :param thinking: Service thinking DTO。
        :returns: ``None``。
        :raises AssertionError: barrier 超时未释放时抛出。
        """

        self.record_call_count += 1
        if self.record_call_count == 1:
            self._blocked.set()
            if not self._release.wait(timeout=_E2E_TIMEOUT_SECONDS):
                raise AssertionError("blocking renderer was not released")
        self._inner.record(thinking)

    def release(self) -> None:
        """释放首个 callback barrier。

        :returns: ``None``。
        :raises Exception: 本方法不主动抛出异常。
        """

        self._release.set()

    def finish_runtime_display(self) -> None:
        """结束真实 thinking 运行态行。

        :returns: ``None``。
        :raises OSError: 真实 renderer 输出失败时透传。
        """

        self._inner.finish_runtime_display()

    def close(self) -> None:
        """关闭真实 renderer 并记录 exact-once 调用。

        :returns: ``None``。
        :raises OSError: 真实 renderer 输出失败时透传。
        """

        self.close_call_count += 1
        self._inner.close()


@pytest.mark.asyncio
async def test_real_delivery_interruption_recovers_once_and_renders_terminal_once(
    tmp_path: pathlib.Path,
) -> None:
    """真实跨层慢消费者应 overflow、Outbox 收口且 CLI 只展示一次 final。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: Host mailbox、typed recovery 或输出去重失效时抛出。
    """

    runtime = await prepare_entrypoint_runtime(
        EntrypointRuntimeRequest(
            workspace_root=tmp_path,
            package_config_root=package_config_root(),
            explicit_config_dir=None,
            scene_id="prompt",
            context_slot_values={
                "fins_default_subject": "# 当前分析对象\n你正在分析的是 AAPL。",
                "current_time": "# 当前时间\n现在是 2026年7月21日。",
            },
            assembly_overrides=ServiceAssemblyOverrides(model_id="deepseek-v4-flash"),
            env={"DEEPSEEK_API_KEY": "test-provider-key"},
        )
    )
    worker_release = asyncio.Event()
    factory = TransientStreamWorkerFactory(
        counts=TransientStreamCounts(
            content=_DELTA_COUNT_PER_TYPE,
            reasoning=_DELTA_COUNT_PER_TYPE,
            tool_call=_DELTA_COUNT_PER_TYPE,
        ),
        final_answer=_FINAL_ANSWER,
        release_event=worker_release,
        terminal_release_event=asyncio.Event(),
    )
    options = replace(
        runtime.host_assembly.options,
        db_path=tmp_path / "host" / "host.sqlite3",
        artifact_root=tmp_path / "host" / "artifacts",
        create_parent_dirs=True,
        lane_db_path=tmp_path / "host" / "lane.sqlite3",
        worker_factory=factory,
        session_event_delivery_policy=HostSessionEventDeliveryPolicy(
            transient_mailbox_max_items=_HOST_MAILBOX_MAX_ITEMS,
            max_subscriptions_per_session=4,
        ),
    )
    thinking_stderr = io.StringIO()
    blocking_renderer = _BlockingThinkingRenderer(
        CliThinkingRenderer(
            stderr=thinking_stderr,
            options=CliThinkingRendererOptions(
                enabled=True,
                terminal_control=False,
            ),
        ),
    )
    display_controller = RuntimeDisplayController(
        activity_display=None,
        thinking_display=blocking_renderer,
    )
    activities: list[EntrypointActivity] = []

    async with (
        open_host(options) as real_host,
        AsyncExitStack() as attachment_stack,
    ):
        session = await real_host.ensure_session(ensure_request("delivery-interruption-e2e"))
        attachment = await real_host.attach_session(session.session_id)
        attachment_stack.push_async_callback(
            close_attachment_shielded, attachment
        )
        independent_watcher = await real_host.watch_session_events(session.session_id)
        independent_consumer = asyncio.create_task(_collect_terminal_event_ids(independent_watcher, expected_count=2))
        probe = _SlowConsumerHostProbe(real_host)
        service_task = asyncio.create_task(
            submit_entrypoint_turn_and_wait(
                cast(Host, probe),
                request=EntrypointTurnRequest(
                    context=host_context("delivery-interruption-e2e-submit"),
                    session_id=session.session_id,
                    client_request_id="delivery-interruption-e2e-followup",
                    user_prompt="exercise real delivery interruption path",
                    tool_names=runtime.scene_inputs.tool_selection.tool_names,
                    behavior=FollowupBehavior.QUEUE,
                    target_run_id=None,
                    run_overrides=ServiceRunOverrides(),
                ),
                scene_inputs=runtime.scene_inputs,
                host_assembly=runtime.host_assembly,
                on_activity=activities.append,
                on_thinking=blocking_renderer.record,
                callback_execution_port=display_controller,
                poll_interval_seconds=0.01,
            )
        )
        await asyncio.wait_for(probe.submit_completed.wait(), timeout=2.0)
        run_id = probe.accepted_run_id
        if run_id is None:
            raise AssertionError("Service did not expose accepted Run identity")

        worker_release.set()
        await _wait_for_renderer_block(blocking_renderer)
        yielded_at_block = probe.yielded_count
        queued = await real_host.submit_followup(
            session.session_id,
            followup_request(
                session.session_id,
                "delivery-interruption-e2e-queued",
                "prove queue promotion survives a blocked CLI renderer",
                tool_names=runtime.scene_inputs.tool_selection.tool_names,
            ),
        )
        queued_run_id = queued.accepted_run_id
        queued_snapshot = await real_host.get_run(queued_run_id)
        assert queued_snapshot.status is RunStatus.QUEUED
        await asyncio.wait_for(factory.deltas_finished_event.wait(), timeout=15.0)
        terminal_release = factory.terminal_release_event
        if terminal_release is None:
            raise AssertionError("terminal barrier is missing")
        terminal_release.set()
        run = await _wait_for_run_succeeded(real_host, run_id)
        promoted_run = await _wait_for_run_succeeded(real_host, queued_run_id)
        independent_terminal_ids = await asyncio.wait_for(
            independent_consumer,
            timeout=_E2E_TIMEOUT_SECONDS,
        )
        await asyncio.sleep(0.05)

        assert probe.yielded_count == yielded_at_block
        assert not service_task.done()
        assert run.status is RunStatus.SUCCEEDED
        assert promoted_run.status is RunStatus.SUCCEEDED
        assert len(independent_terminal_ids) == 2
        assert factory.cancel_reasons == []
        assert event_log_type_count(options.db_path, "RUN_SUCCEEDED") == 2

        blocking_renderer.release()
        terminal = await asyncio.wait_for(service_task, timeout=_E2E_TIMEOUT_SECONDS)
        await display_controller.finish_runtime_display()
        await display_controller.aclose()
        await independent_watcher.aclose()

        outbox = await real_host.read_outbox_terminal_items(
            session.session_id,
            ReadOutboxTerminalItemsRequest(
                after=OutboxTerminalCursor(event_sequence=0),
                seen_terminal_event_ids=(),
                limit=50,
            ),
        )

    assert terminal.source is EntrypointTerminalSource.OUTBOX_READ
    assert terminal.run_id == run_id
    assert terminal.final_answer is not None
    assert terminal.final_answer.content == _FINAL_ANSWER
    assert terminal.watcher_failure_message is None
    assert probe.live_terminal_event_ids == []
    assert len(probe.host_errors) == 1
    overflow = probe.host_errors[0]
    assert overflow.code is HostApiErrorCode.DELIVERY_INTERRUPTED
    assert overflow.retryable is False
    assert overflow.detail == HostSessionEventDeliveryDetail(
        reason=HostSessionEventDeliveryReason.TRANSIENT_MAILBOX_OVERFLOW,
    )
    assert probe.get_run_call_count == 1
    assert probe.outbox_read_call_count == 1
    assert terminal.terminal_event_id in independent_terminal_ids
    assert blocking_renderer.close_call_count == 1
    assert activities

    matching_outbox = tuple(item for item in outbox.items if item.run_id == run_id)
    assert len(matching_outbox) == 1
    assert matching_outbox[0].terminal_event_id == terminal.terminal_event_id
    assert matching_outbox[0].dedupe_key == terminal.dedupe_key
    durable = read_transient_durable_snapshot(options.db_path, run_id=run_id)
    assert durable.run_terminal_event_id == terminal.terminal_event_id
    assert durable.run_terminal_event_sequence == terminal.event_sequence
    assert durable.run_status == "succeeded"
    assert durable.attempt_status == "succeeded"

    stdout = io.StringIO()
    terminal_stderr = io.StringIO()
    exit_code = render_prompt_terminal_result(
        terminal,
        stdout=stdout,
        stderr=terminal_stderr,
    )
    assert exit_code == EXIT_SUCCESS
    assert stdout.getvalue() == f"{_FINAL_ANSWER}\n"
    assert stdout.getvalue().count(_FINAL_ANSWER) == 1
    assert terminal_stderr.getvalue() == ""
    assert thinking_stderr.getvalue().count("Thinking:") == 1
    assert "slow-consumer-thinking" in thinking_stderr.getvalue()


async def _wait_for_run_succeeded(host: Host, run_id: str) -> RunSnapshot:
    """等待真实 Host Run 成功，证明 terminal/promotion 未受 renderer 阻塞。

    :param host: 真实 public Host。
    :param run_id: 目标 Run 标识。
    :returns: 成功 Run snapshot。
    :raises AssertionError: timeout 内未成功时抛出。
    """

    for _attempt in range(1_500):
        snapshot = await host.get_run(run_id)
        if snapshot.status is RunStatus.SUCCEEDED:
            return snapshot
        if snapshot.status in {
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.LOST,
        }:
            raise AssertionError(f"Run reached unexpected status: {snapshot.status}")
        await asyncio.sleep(0.01)
    raise AssertionError("Run did not succeed while CLI renderer was blocked")


async def _wait_for_renderer_block(renderer: _BlockingThinkingRenderer) -> None:
    """等待 CLI renderer callback 进入阻塞点。

    :param renderer: 带可控 barrier 的 renderer。
    :returns: ``None``。
    :raises AssertionError: timeout 内 callback 未进入阻塞点时抛出。
    """

    for _attempt in range(1_000):
        if renderer.blocked:
            return
        await asyncio.sleep(0.005)
    raise AssertionError("CLI renderer callback did not reach its blocking point")


async def _collect_terminal_event_ids(
    watcher: HostSessionEventIterator,
    *,
    expected_count: int,
) -> tuple[str, ...]:
    """持续消费独立 watcher，收集指定数量的 terminal identity。

    :param watcher: 真实 Host public Session event iterator。
    :param expected_count: 预期 terminal 数量。
    :returns: 按交付顺序收集的 terminal event id。
    :raises HostApiError: 独立 watcher 交付失败时透传。
    :raises AssertionError: HostEvent 缺少 terminal identity 时抛出。
    """

    terminal_event_ids: list[str] = []
    while len(terminal_event_ids) < expected_count:
        event = await anext(watcher)
        if not isinstance(event, HostEvent) or event.terminal_status is None:
            continue
        if event.event_id is None:
            raise AssertionError("terminal HostEvent did not contain event_id")
        terminal_event_ids.append(event.event_id)
    return tuple(terminal_event_ids)
