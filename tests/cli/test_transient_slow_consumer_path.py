"""真实 Host→Service→CLI transient slow-consumer 路径测试。"""

from __future__ import annotations

import asyncio
import io
import pathlib
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Protocol, cast

import pytest

from dayu.cli.agent_entrypoint import package_config_root
from dayu.cli.exit_codes import EXIT_SUCCESS
from dayu.cli.output import render_prompt_terminal_result
from dayu.cli.thinking import CliThinkingRenderer, CliThinkingRendererOptions
from dayu.host import (
    FollowupBehavior,
    FollowupSnapshot,
    Host,
    HostApiError,
    HostApiErrorCode,
    HostEvent,
    HostSessionEvent,
    HostUnavailableDetail,
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
    EntrypointTurnRequest,
    prepare_entrypoint_runtime,
    submit_entrypoint_turn_and_wait,
)
from dayu.service.host_assembly import ServiceAssemblyOverrides, ServiceRunOverrides
from tests.host.public_smoke_support import ensure_request, host_context
from tests.host.transient_stream_support import (
    TransientStreamCounts,
    TransientStreamWorkerFactory,
    event_log_type_count,
    read_transient_durable_snapshot,
)

_DELTA_COUNT_PER_TYPE = 400
_SERVICE_RELAY_CAPACITY = 256
_PENDING_RELAY_ITEM_COUNT = 1
_E2E_TIMEOUT_SECONDS = 30.0
_FINAL_ANSWER = "slow-consumer-final"


class _ClosableSessionEventIterator(Protocol):
    """E2E probe 使用的可关闭 Session event iterator 窄协议。"""

    async def aclose(self) -> None:
        """关闭 iterator。

        :returns: ``None``。
        :raises Exception: Host iterator cleanup 失败时透传。
        """

        ...


class _ObservedHostSessionEventIterator:
    """只观测真实 Host iterator 交付与原异常 identity 的透明 wrapper。"""

    def __init__(
        self,
        *,
        inner: AsyncIterator[HostSessionEvent],
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

        await cast(_ClosableSessionEventIterator, self._inner).aclose()


class _SlowConsumerHostProbe:
    """阻塞 Service 首次 ``get_run``，透明转发其余真实 Host public 调用。

    阻塞点位于 Service 已排空 relay、即将等待 durable 状态的位置。此后真实
    watcher drain task 会先填满 capacity-256 relay，再停在第 257 个 item 的
    ``await queue.put``；测试只记录该事实，不替换 Host/Service 实现。
    """

    def __init__(self, host: Host) -> None:
        """初始化真实 Host public probe。

        :param host: ``open_host`` 返回的真实 public Host。
        :returns: 无返回值。
        :raises Exception: 本构造函数不主动抛出异常。
        """

        self._host = host
        self._release_first_get_run = asyncio.Event()
        self.first_get_run_blocked = asyncio.Event()
        self.submit_completed = asyncio.Event()
        self.accepted_run_id: str | None = None
        self.block_start_yielded_count: int | None = None
        self.yielded_count = 0
        self.host_errors: list[HostApiError] = []
        self.live_terminal_event_ids: list[str] = []

    def watch_session_events(
        self,
        session_id: str,
    ) -> AsyncIterator[HostSessionEvent]:
        """同步 attach 真实 Host watcher，并返回透明观测 wrapper。

        :param session_id: 目标 Session 标识。
        :returns: 透明包装后的真实 Host iterator。
        :raises HostApiError: Host watch attach 失败时透传。
        """

        return _ObservedHostSessionEventIterator(
            inner=self._host.watch_session_events(session_id),
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
        """只阻塞 Service 的首次 get_run，恢复后转发真实读取。

        :param run_id: 目标 Run 标识。
        :returns: 真实 Run snapshot。
        :raises HostApiError: Host read 失败时透传。
        :raises asyncio.CancelledError: Service task 被取消时透传。
        """

        if not self.first_get_run_blocked.is_set():
            self.block_start_yielded_count = self.yielded_count
            self.first_get_run_blocked.set()
            await self._release_first_get_run.wait()
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

        return await self._host.read_outbox_terminal_items(session_id, request)

    def release_first_get_run(self) -> None:
        """恢复 Service terminal observation 消费。

        :returns: ``None``。
        :raises Exception: 本方法不主动抛出异常。
        """

        self._release_first_get_run.set()


@pytest.mark.asyncio
async def test_real_transient_slow_consumer_falls_back_once_with_original_typed_error(
    tmp_path: pathlib.Path,
) -> None:
    """真实跨层慢消费者应 overflow、Outbox 收口且 CLI 只展示一次 final。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: bounded relay、typed error、fallback 或输出去重失效时抛出。
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
            assembly_overrides=ServiceAssemblyOverrides(
                model_id="deepseek-v4-flash"
            ),
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
    )
    options = replace(
        runtime.host_assembly.options,
        db_path=tmp_path / "host" / "host.sqlite3",
        artifact_root=tmp_path / "host" / "artifacts",
        create_parent_dirs=True,
        lane_db_path=tmp_path / "host" / "lane.sqlite3",
        worker_factory=factory,
    )
    thinking_stderr = io.StringIO()
    renderer = CliThinkingRenderer(
        stderr=thinking_stderr,
        options=CliThinkingRendererOptions(
            enabled=True,
            terminal_control=False,
        ),
    )
    activities: list[EntrypointActivity] = []

    async with open_host(options) as real_host:
        session = await real_host.ensure_session(ensure_request("slow-consumer-e2e"))
        probe = _SlowConsumerHostProbe(real_host)
        service_task = asyncio.create_task(
            submit_entrypoint_turn_and_wait(
                cast(Host, probe),
                request=EntrypointTurnRequest(
                    context=host_context("slow-consumer-e2e-submit"),
                    session_id=session.session_id,
                    client_request_id="slow-consumer-e2e-followup",
                    user_prompt="exercise real slow consumer path",
                    tool_names=runtime.scene_inputs.tool_selection.tool_names,
                    behavior=FollowupBehavior.QUEUE,
                    target_run_id=None,
                    run_overrides=ServiceRunOverrides(),
                ),
                scene_inputs=runtime.scene_inputs,
                host_assembly=runtime.host_assembly,
                on_activity=activities.append,
                on_thinking=renderer.record,
                poll_interval_seconds=0.01,
            )
        )
        await asyncio.wait_for(probe.submit_completed.wait(), timeout=2.0)
        await asyncio.wait_for(probe.first_get_run_blocked.wait(), timeout=2.0)
        run_id = probe.accepted_run_id
        block_start = probe.block_start_yielded_count
        if run_id is None or block_start is None:
            raise AssertionError("Service did not expose accepted/block identities")

        worker_release.set()
        await asyncio.wait_for(factory.deltas_finished_event.wait(), timeout=15.0)
        run = await _wait_for_run_succeeded(real_host, run_id)
        blocked_yield_count = (
            block_start + _SERVICE_RELAY_CAPACITY + _PENDING_RELAY_ITEM_COUNT
        )
        await _wait_for_yielded_count(probe, blocked_yield_count)
        yielded_before_probe = probe.yielded_count
        await asyncio.sleep(0.05)

        assert yielded_before_probe == blocked_yield_count
        assert probe.yielded_count == yielded_before_probe
        assert not service_task.done()
        assert run.status is RunStatus.SUCCEEDED
        assert factory.cancel_reasons == []
        assert event_log_type_count(options.db_path, "RUN_SUCCEEDED") == 1

        probe.release_first_get_run()
        terminal = await asyncio.wait_for(service_task, timeout=_E2E_TIMEOUT_SECONDS)
        renderer.finish_runtime_display()
        renderer.close()

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
    assert terminal.watcher_failure_message is not None
    assert "HostApiError" in terminal.watcher_failure_message
    assert "too slow" in terminal.watcher_failure_message
    assert probe.live_terminal_event_ids == []
    assert len(probe.host_errors) == 1
    overflow = probe.host_errors[0]
    assert overflow.code is HostApiErrorCode.UNAVAILABLE
    assert overflow.retryable is True
    assert overflow.detail == HostUnavailableDetail(
        component="session_live_stream",
        reason_code="slow_consumer",
    )
    assert any(
        activity.summary is not None and "HostApiError" in activity.summary
        for activity in activities
    )

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
    """等待真实 Host Run 成功，证明 terminal append 未受 relay 反压阻塞。

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
    raise AssertionError("Run did not succeed while Service relay was blocked")


async def _wait_for_yielded_count(
    probe: _SlowConsumerHostProbe,
    expected_count: int,
) -> None:
    """等待透明 iterator 到达 Service relay 的确定性阻塞计数。

    :param probe: 真实 Host iterator 观测 probe。
    :param expected_count: relay capacity 加一个 pending put 后的精确计数。
    :returns: ``None``。
    :raises AssertionError: timeout 内未到达精确计数或越界时抛出。
    """

    for _attempt in range(1_000):
        if probe.yielded_count == expected_count:
            return
        if probe.yielded_count > expected_count:
            raise AssertionError("Service relay accepted more than its bounded capacity")
        await asyncio.sleep(0.005)
    raise AssertionError("Service relay did not reach its bounded blocking point")
