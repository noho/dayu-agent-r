"""interactive entrypoint runtime path 集成测试。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from dayu.host.api import (
    FollowupBehavior,
    FollowupSnapshot,
    Host,
    HostCallContext,
    HostEvent,
    HostEventClass,
    HostEventKind,
    HostFinalAnswerView,
    HostStreamCursor,
    HostTerminalStatus,
    OperationContext,
    OutboxProjectionStatus,
    OutboxTerminalCursor,
    OutboxTerminalItemsBatch,
    ReadOutboxTerminalItemsRequest,
    RunSnapshot,
    RunStatus,
    SubmitFollowupRequest,
)
from dayu.service.entrypoint_runtime import (
    EntrypointRuntimeRequest,
    EntrypointRuntimeResult,
    EntrypointTurnRequest,
    prepare_entrypoint_runtime,
    submit_entrypoint_turn_and_wait,
)
from dayu.service.host_assembly import ServiceAssemblyOverrides, ServiceRunOverrides

_PACKAGE_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "dayu" / "config"
_MODEL_ID = "deepseek-v4-flash"
_RUNNER_HINT_ID = "interactive"
_API_KEY = "test-provider-key"
_DEFAULT_INTERACTIVE_TOOL_NAME = "get_financial_statement"
_DEFAULT_TIME_TOOL_NAME = "get_current_time"
_DEFAULT_DOWNLOAD_TOOL_NAME = "start_fins_download"
_DEFAULT_PREPROCESS_TOOL_NAME = "start_fins_preprocess"
_EXCLUDED_UPLOAD_TOOL_NAME = "start_fins_upload"
_INTERACTIVE_CURRENT_TIME_TEXT = "# 当前时间\n现在是 2026年7月7日 17:20（Asia/Shanghai，星期二）。"


@dataclass(frozen=True, slots=True)
class _StopSignal:
    """测试 watcher 停止信号。"""


class _FakeHostEventIterator:
    """测试用 Host event iterator。"""

    closed_count: int
    _queue: asyncio.Queue[HostEvent | _StopSignal]

    def __init__(self) -> None:
        """初始化 fake watcher。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.closed_count = 0
        self._queue = asyncio.Queue()

    def __aiter__(self) -> AsyncIterator[HostEvent]:
        """返回自身作为 async iterator。

        :returns: HostEvent async iterator。
        :raises Exception: 不主动抛出异常。
        """

        return self

    async def __anext__(self) -> HostEvent:
        """读取下一条 Host event。

        :returns: HostEvent。
        :raises StopAsyncIteration: 收到停止信号时抛出。
        """

        item = await self._queue.get()
        if isinstance(item, _StopSignal):
            raise StopAsyncIteration
        return item

    async def push(self, event: HostEvent) -> None:
        """推入一条 Host event。

        :param event: 待推入事件。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        await self._queue.put(event)

    async def aclose(self) -> None:
        """关闭 watcher。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.closed_count += 1
        await self._queue.put(_StopSignal())


class _FakeHost:
    """interactive path 测试用 Host public API 替身。"""

    calls: list[str]
    submit_requests: list[SubmitFollowupRequest]
    watchers: list[_FakeHostEventIterator]
    read_outbox_requests: list[ReadOutboxTerminalItemsRequest]
    _submit_index: int

    def __init__(self) -> None:
        """初始化 fake Host。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.calls = []
        self.submit_requests = []
        self.watchers = []
        self.read_outbox_requests = []
        self._submit_index = 0

    def watch_session_events(self, session_id: str) -> AsyncIterator[HostEvent]:
        """记录 watcher attach。

        :param session_id: 目标 Session id。
        :returns: Host event iterator。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(f"watch:{session_id}")
        watcher = _FakeHostEventIterator()
        self.watchers.append(watcher)
        return watcher

    async def submit_followup(self, session_id: str, request: SubmitFollowupRequest) -> FollowupSnapshot:
        """记录 submit 请求并推入成功终态。

        :param session_id: 目标 Session id。
        :param request: SubmitFollowupRequest。
        :returns: FollowupSnapshot。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(f"submit:{session_id}")
        self.submit_requests.append(request)
        self._submit_index += 1
        run_id = f"run-{self._submit_index}"
        await self.watchers[-1].push(_terminal_event(run_id=run_id, event_sequence=self._submit_index + 1))
        await asyncio.sleep(0)
        return FollowupSnapshot(
            accepted_input_ref=f"input-{self._submit_index}",
            behavior=FollowupBehavior.QUEUE,
            accepted_run_id=run_id,
            accepted_run_status=RunStatus.RUNNING,
            command_watermark=HostStreamCursor(event_sequence=self._submit_index),
            queued_run_id=None,
            target_run_id=None,
        )

    async def get_run(self, run_id: str) -> RunSnapshot:
        """返回测试 RunSnapshot。

        :param run_id: 目标 Run id。
        :returns: RunSnapshot。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(f"get_run:{run_id}")
        return RunSnapshot(
            run_id=run_id,
            session_id="session-1",
            status=RunStatus.SUCCEEDED,
            current_attempt_id=None,
            terminal_result_summary=None,
            event_cursor=HostStreamCursor(event_sequence=2),
            source_run_id=None,
            source_run_relation=None,
            outbox_summary=None,
        )

    async def read_outbox_terminal_items(
        self,
        session_id: str,
        request: ReadOutboxTerminalItemsRequest,
    ) -> OutboxTerminalItemsBatch:
        """返回空 outbox 批次。

        :param session_id: 目标 Session id。
        :param request: outbox read 请求。
        :returns: 空 outbox terminal batch。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(f"read_outbox:{session_id}")
        self.read_outbox_requests.append(request)
        return OutboxTerminalItemsBatch(
            items=(),
            next_cursor=OutboxTerminalCursor(event_sequence=0),
            scanned_watermark=OutboxTerminalCursor(event_sequence=0),
            projection_checkpoint=OutboxTerminalCursor(event_sequence=0),
            projection_status=OutboxProjectionStatus.CAUGHT_UP,
            projection_error_code=None,
            projection_error_message=None,
            has_more=False,
        )


@pytest.mark.asyncio
async def test_interactive_runtime_uses_real_manifest_required_slots(
    tmp_path: Path,
) -> None:
    """真实 interactive scene 应只要求并消费当前 manifest 所需 slots。"""

    result = await _prepare_interactive_runtime(tmp_path)

    assert result.scene_inputs.tool_selection.tool_names is not None
    assert _DEFAULT_INTERACTIVE_TOOL_NAME in result.scene_inputs.tool_selection.tool_names
    assert _DEFAULT_TIME_TOOL_NAME in result.scene_inputs.tool_selection.tool_names
    assert _DEFAULT_DOWNLOAD_TOOL_NAME in result.scene_inputs.tool_selection.tool_names
    assert _DEFAULT_PREPROCESS_TOOL_NAME in result.scene_inputs.tool_selection.tool_names
    assert _EXCLUDED_UPLOAD_TOOL_NAME not in result.scene_inputs.tool_selection.tool_names
    assert "财报工具指引" in result.scene_inputs.system_prompt
    assert _DEFAULT_TIME_TOOL_NAME in result.scene_inputs.system_prompt
    assert _DEFAULT_DOWNLOAD_TOOL_NAME in result.scene_inputs.system_prompt
    assert _DEFAULT_PREPROCESS_TOOL_NAME in result.scene_inputs.system_prompt
    assert _EXCLUDED_UPLOAD_TOOL_NAME not in result.scene_inputs.system_prompt
    assert "<when_tag" not in result.scene_inputs.system_prompt
    assert "</when_tag>" not in result.scene_inputs.system_prompt
    assert "<when_tool" not in result.scene_inputs.system_prompt
    assert "</when_tool>" not in result.scene_inputs.system_prompt
    assert result.host_assembly.diagnostics.model_id == _MODEL_ID
    assert result.host_assembly.diagnostics.runner_option_hint_id == _RUNNER_HINT_ID


@pytest.mark.asyncio
async def test_interactive_runtime_requires_current_time_context_slot(
    tmp_path: Path,
) -> None:
    """真实 interactive scene 只要求当前时间，不要求入口身份类 context slot。"""

    runtime = await prepare_entrypoint_runtime(
        EntrypointRuntimeRequest(
            workspace_root=tmp_path,
            package_config_root=_PACKAGE_CONFIG_ROOT,
            explicit_config_dir=None,
            scene_id="interactive",
            context_slot_values={"current_time": _INTERACTIVE_CURRENT_TIME_TEXT},
            assembly_overrides=ServiceAssemblyOverrides(
                model_id=_MODEL_ID,
                runner_option_hint_id=_RUNNER_HINT_ID,
            ),
            env={"DEEPSEEK_API_KEY": _API_KEY},
        )
    )

    assert runtime.scene_inputs.tool_selection.tool_names is not None
    assert _DEFAULT_INTERACTIVE_TOOL_NAME in runtime.scene_inputs.tool_selection.tool_names


@pytest.mark.asyncio
async def test_interactive_two_turns_have_independent_terminal_wait_state(
    tmp_path: Path,
) -> None:
    """interactive 两轮应各自 attach/close watcher 且不复用 wait state。"""

    runtime = await _prepare_interactive_runtime(tmp_path)
    fake_host = _FakeHost()

    first = await submit_entrypoint_turn_and_wait(
        cast(Host, fake_host),
        request=_turn_request(turn_index=1, user_prompt="第一轮"),
        scene_inputs=runtime.scene_inputs,
        host_assembly=runtime.host_assembly,
    )
    second = await submit_entrypoint_turn_and_wait(
        cast(Host, fake_host),
        request=_turn_request(turn_index=2, user_prompt="第二轮"),
        scene_inputs=runtime.scene_inputs,
        host_assembly=runtime.host_assembly,
    )

    assert first.run_id == "run-1"
    assert second.run_id == "run-2"
    assert fake_host.calls == [
        "watch:session-1",
        "submit:session-1",
        "watch:session-1",
        "submit:session-1",
    ]
    assert [watcher.closed_count for watcher in fake_host.watchers] == [1, 1]
    assert fake_host.submit_requests[0].client_request_id == "submit-turn-1"
    assert fake_host.submit_requests[1].client_request_id == "submit-turn-2"


async def _prepare_interactive_runtime(
    tmp_path: Path,
) -> EntrypointRuntimeResult:
    """构造真实 interactive runtime assembly 测试结果。

    :param tmp_path: pytest 临时 workspace root。
    :returns: entrypoint runtime result。
    :raises Exception: runtime assembly 失败时向上抛出。
    """

    return await prepare_entrypoint_runtime(
        EntrypointRuntimeRequest(
            workspace_root=tmp_path,
            package_config_root=_PACKAGE_CONFIG_ROOT,
            explicit_config_dir=None,
            scene_id="interactive",
            context_slot_values={"current_time": _INTERACTIVE_CURRENT_TIME_TEXT},
            assembly_overrides=ServiceAssemblyOverrides(
                model_id=_MODEL_ID,
                runner_option_hint_id=_RUNNER_HINT_ID,
            ),
            env={"DEEPSEEK_API_KEY": _API_KEY},
        )
    )


def _turn_request(*, turn_index: int, user_prompt: str) -> EntrypointTurnRequest:
    """构造默认 entrypoint turn request。

    :param turn_index: 测试轮次序号。
    :param user_prompt: 用户输入。
    :returns: entrypoint turn request。
    :raises Exception: 不主动抛出异常。
    """

    return EntrypointTurnRequest(
        context=_host_context(f"submit-context-{turn_index}"),
        session_id="session-1",
        client_request_id=f"submit-turn-{turn_index}",
        user_prompt=user_prompt,
        tool_names=frozenset({"get_financial_statement"}),
        behavior=FollowupBehavior.QUEUE,
        target_run_id=None,
        run_overrides=ServiceRunOverrides(temperature=0.2),
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
            operation_name="service_entrypoint.interactive_test",
            operation_kind="service_entrypoint_test",
            business_domain="fins",
            business_object_type=None,
            business_object_id=None,
            scenario="interactive",
            correlation_id="correlation-1",
        ),
    )


def _terminal_event(*, run_id: str, event_sequence: int) -> HostEvent:
    """构造测试 terminal HostEvent。

    :param run_id: Run id。
    :param event_sequence: event sequence。
    :returns: HostEvent。
    :raises Exception: 不主动抛出异常。
    """

    return HostEvent(
        event_id=f"terminal-{run_id}-{event_sequence}",
        event_sequence=event_sequence,
        session_id="session-1",
        run_id=run_id,
        event_class=HostEventClass.CANONICAL_FACT,
        event_type="RUN_SUCCEEDED",
        kind=HostEventKind.SUCCEEDED,
        activity=None,
        dedupe_key=f"terminal-{run_id}-{event_sequence}",
        terminal_status=HostTerminalStatus.SUCCEEDED,
        final_answer=HostFinalAnswerView(
            content=f"answer for {run_id}",
            filtered=False,
            degraded=False,
            finish_reason="stop",
            terminal_status=HostTerminalStatus.SUCCEEDED,
        ),
        error_message=None,
        cancel_reason=None,
    )
