"""prompt entrypoint runtime path 集成测试。"""

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
from dayu.runtime.scene_prepare import ScenePrepareError
from dayu.service.entrypoint_runtime import (
    EntrypointRuntimeRequest,
    EntrypointRuntimeResult,
    EntrypointTurnRequest,
    prepare_entrypoint_runtime,
    submit_entrypoint_turn_and_wait,
)
from dayu.service.host_assembly import ServiceAssemblyOverrides, ServiceRunOverrides

DEFAULT_PROMPT_TOOL_NAME: str = "get_financial_statement"
DEFAULT_TIME_TOOL_NAME: str = "get_current_time"
DEFAULT_DOWNLOAD_TOOL_NAME: str = "start_fins_download"
DEFAULT_PREPROCESS_TOOL_NAME: str = "start_fins_preprocess"
EXCLUDED_UPLOAD_TOOL_NAME: str = "start_fins_upload"
_PACKAGE_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "dayu" / "config"
_MODEL_ID = "deepseek-v4-flash"
_RUNNER_HINT_ID = "prompt"
_API_KEY = "test-provider-key"


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
    """prompt path 测试用 Host public API 替身。"""

    calls: list[str]
    submit_requests: list[SubmitFollowupRequest]
    watchers: list[_FakeHostEventIterator]

    def __init__(self) -> None:
        """初始化 fake Host。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.calls = []
        self.submit_requests = []
        self.watchers = []

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
        await self.watchers[-1].push(_terminal_event())
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
async def test_prompt_runtime_uses_real_prompt_manifest_required_slots(
    tmp_path: Path,
) -> None:
    """真实 prompt scene 应要求并消费 fins_default_subject/base_user slots。"""

    result = await _prepare_prompt_runtime(
        tmp_path,
        fins_default_subject="测试公司",
        base_user="本地 CLI 用户",
    )
    changed_subject_result = await _prepare_prompt_runtime(
        tmp_path,
        fins_default_subject="另一家公司",
        base_user="本地 CLI 用户",
    )

    assert result.scene_inputs.tool_selection.tool_names is not None
    assert DEFAULT_PROMPT_TOOL_NAME in result.scene_inputs.tool_selection.tool_names
    assert DEFAULT_TIME_TOOL_NAME in result.scene_inputs.tool_selection.tool_names
    assert DEFAULT_DOWNLOAD_TOOL_NAME not in result.scene_inputs.tool_selection.tool_names
    assert DEFAULT_PREPROCESS_TOOL_NAME not in result.scene_inputs.tool_selection.tool_names
    assert EXCLUDED_UPLOAD_TOOL_NAME not in result.scene_inputs.tool_selection.tool_names
    assert "财报工具指引" in result.scene_inputs.system_prompt
    assert DEFAULT_TIME_TOOL_NAME in result.scene_inputs.system_prompt
    assert DEFAULT_DOWNLOAD_TOOL_NAME not in result.scene_inputs.system_prompt
    assert DEFAULT_PREPROCESS_TOOL_NAME not in result.scene_inputs.system_prompt
    assert EXCLUDED_UPLOAD_TOOL_NAME not in result.scene_inputs.system_prompt
    assert "<when_tag" not in result.scene_inputs.system_prompt
    assert "</when_tag>" not in result.scene_inputs.system_prompt
    assert "<when_tool" not in result.scene_inputs.system_prompt
    assert "</when_tool>" not in result.scene_inputs.system_prompt
    assert result.scene_inputs.content_digest != (changed_subject_result.scene_inputs.content_digest)
    assert result.host_assembly.diagnostics.model_id == _MODEL_ID
    assert result.host_assembly.diagnostics.runner_option_hint_id == _RUNNER_HINT_ID


@pytest.mark.asyncio
async def test_prompt_runtime_rejects_missing_required_context_slot(
    tmp_path: Path,
) -> None:
    """真实 prompt scene 缺 required slot 时必须 fail closed。"""

    with pytest.raises(ScenePrepareError, match="fins_default_subject"):
        await prepare_entrypoint_runtime(
            EntrypointRuntimeRequest(
                workspace_root=tmp_path,
                package_config_root=_PACKAGE_CONFIG_ROOT,
                explicit_config_dir=None,
                scene_id="prompt",
                context_slot_values={"base_user": "本地 CLI 用户"},
                assembly_overrides=ServiceAssemblyOverrides(
                    model_id=_MODEL_ID,
                    runner_option_hint_id=_RUNNER_HINT_ID,
                ),
                env={"DEEPSEEK_API_KEY": _API_KEY},
            )
        )


@pytest.mark.asyncio
async def test_submit_entrypoint_turn_reports_accepted_run_id(
    tmp_path: Path,
) -> None:
    """submit helper 应在 Host 接受 Run 后通知 accepted_run_id。"""

    runtime = await _prepare_prompt_runtime(
        tmp_path,
        fins_default_subject="测试公司",
        base_user="本地 CLI 用户",
    )
    accepted_run_ids: list[str] = []
    fake_host = _FakeHost()

    result = await submit_entrypoint_turn_and_wait(
        cast(Host, fake_host),
        request=EntrypointTurnRequest(
            context=_host_context("submit-context"),
            session_id="session-1",
            client_request_id="submit-request-1",
            user_prompt="请总结收入变化。",
            tool_names=runtime.scene_inputs.tool_selection.tool_names,
            behavior=FollowupBehavior.QUEUE,
            target_run_id=None,
            run_overrides=ServiceRunOverrides(temperature=0.2),
        ),
        scene_inputs=runtime.scene_inputs,
        host_assembly=runtime.host_assembly,
        on_run_accepted=accepted_run_ids.append,
    )

    assert accepted_run_ids == ["run-1"]
    assert result.final_answer is not None
    assert result.final_answer.content == "prompt answer"
    assert fake_host.calls == ["watch:session-1", "submit:session-1"]


async def _prepare_prompt_runtime(
    tmp_path: Path,
    *,
    fins_default_subject: str,
    base_user: str,
) -> EntrypointRuntimeResult:
    """准备真实 prompt scene 的 entrypoint runtime。

    :param tmp_path: pytest 临时 workspace root。
    :param fins_default_subject: prompt scene 财报主体 slot 值。
    :param base_user: prompt scene base_user slot 值。
    :returns: entrypoint runtime result。
    :raises Exception: runtime assembly 失败时向上抛出。
    """

    return await prepare_entrypoint_runtime(
        EntrypointRuntimeRequest(
            workspace_root=tmp_path,
            package_config_root=_PACKAGE_CONFIG_ROOT,
            explicit_config_dir=None,
            scene_id="prompt",
            context_slot_values={
                "fins_default_subject": fins_default_subject,
                "base_user": base_user,
            },
            assembly_overrides=ServiceAssemblyOverrides(
                model_id=_MODEL_ID,
                runner_option_hint_id=_RUNNER_HINT_ID,
            ),
            env={"DEEPSEEK_API_KEY": _API_KEY},
        )
    )


def _terminal_event() -> HostEvent:
    """构造 prompt path 测试 terminal event。

    :returns: HostEvent。
    :raises Exception: 不主动抛出异常。
    """

    return HostEvent(
        event_id="terminal-run-1-2",
        event_sequence=2,
        session_id="session-1",
        run_id="run-1",
        event_class=HostEventClass.CANONICAL_FACT,
        event_type="RUN_SUCCEEDED",
        kind=HostEventKind.SUCCEEDED,
        activity=None,
        dedupe_key="terminal-run-1-2",
        terminal_status=HostTerminalStatus.SUCCEEDED,
        final_answer=HostFinalAnswerView(
            content="prompt answer",
            filtered=False,
            degraded=False,
            finish_reason="stop",
            terminal_status=HostTerminalStatus.SUCCEEDED,
        ),
        error_message=None,
        cancel_reason=None,
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
            operation_name="service_entrypoint.prompt_test",
            operation_kind="service_entrypoint_prompt_test",
            business_domain="fins",
            business_object_type=None,
            business_object_id=None,
            scenario="prompt",
            correlation_id="correlation-1",
        ),
    )
