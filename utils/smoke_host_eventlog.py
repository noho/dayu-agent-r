"""人工验证 Host P1.5 EventLog 路径的 smoke 脚本。

本脚本不发起 provider 网络请求，只使用 fake ``WorkerProxy`` 产出少量
``EngineEvent``，用于观察当前 run harness 中的 EventLog 语义：

- ``start_run`` 启动后台任务。
- ``EngineEvent`` 翻译为 ``RunEventDraft``。
- ``RunEventStore.append`` 先落事实并分配 Host cursor。
- ``RunStream.events`` / ``stream_run_events`` 从 store 订阅或补读。
- ``get_run_result`` 从已 append 的 terminal RunEvent 推导结果。

建议使用 ``--log-level DEBUG`` 运行，通过 ``dayu.host`` 日志观察
append-before-stream、exclusive replay 与 Host-owned failure 行为。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

_REPO_ROOT_PARENT_INDEX: int = 1


def _ensure_repo_root_on_path() -> None:
    """确保按文件路径运行脚本时也能导入仓库顶层包。

    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    if __package__ not in (None, ""):
        return
    repo_root = Path(__file__).resolve().parents[_REPO_ROOT_PARENT_INDEX]
    repo_root_text = str(repo_root)
    if repo_root_text not in sys.path:
        sys.path.insert(0, repo_root_text)


_ensure_repo_root_on_path()

from dayu.contracts import CancellationToken
from dayu.engine import (
    AgentMessageRole,
    AgentPolicy,
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    FinishReason,
    RunnerCallOptions,
    RunnerSpec,
    UserMessage,
)
from dayu.host._event_store import InMemoryRunEventStore
from dayu.host._run_harness import LocalRunHarness
from utils._smoke_memory_store import SmokeInMemoryConversationMemoryStore
from dayu.host.contracts import (
    RunEvent,
    RunEventCursor,
    RunEventType,
    RunInput,
    RunOptions,
    StartRunRequest,
)
from dayu.runtime.log import LogLevel, configure

_DEFAULT_TIMEOUT_SECONDS: float = 30.0
_DEFAULT_MAX_RETRIES: int = 0
_DEFAULT_MAX_ITERATIONS: int = 2
_RUN_ID_PREFIX: str = "smoke_host_eventlog"
_SESSION_ID: str = "smoke_host_eventlog_session"
_PROMPT: str = "请用一句话回答：EventLog smoke。"
_SMOKE_PREFIX: str = "SMOKE"

SmokeCaseName = Literal["success", "worker-failure"]
"""smoke case 名称。"""


@dataclass(frozen=True, slots=True)
class SmokeArgs:
    """解析后的 smoke 参数。

    :param case_name: smoke case 名称。
    :param log_level: 日志级别名称。
    """

    case_name: SmokeCaseName
    log_level: LogLevel


@dataclass(frozen=True, slots=True)
class _ScriptedProxy:
    """按脚本产出 EngineEvent 的 fake WorkerProxy。

    :param events: 待产出的 EngineEvent 元组。
    """

    events: tuple[EngineEvent, ...]

    def stream_engine_events(
        self,
        request: StartRunRequest,
        cancellation_token: CancellationToken,
    ) -> AsyncIterator[EngineEvent]:
        """返回脚本化 EngineEvent 流。

        :param request: Host start_run 请求。
        :param cancellation_token: Host 注入的取消 token。
        :returns: EngineEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        return self._iter_events()

    async def _iter_events(self) -> AsyncIterator[EngineEvent]:
        """产出脚本事件。

        :returns: EngineEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        for event in self.events:
            await asyncio.sleep(0)
            yield event


@dataclass(frozen=True, slots=True)
class _FailingProxy:
    """取事件时抛出异常的 fake WorkerProxy。"""

    def stream_engine_events(
        self,
        request: StartRunRequest,
        cancellation_token: CancellationToken,
    ) -> AsyncIterator[EngineEvent]:
        """返回会在迭代时失败的 EngineEvent 流。

        :param request: Host start_run 请求。
        :param cancellation_token: Host 注入的取消 token。
        :returns: EngineEvent 异步流。
        :raises Exception: 不主动抛出异常；异常在迭代时抛出。
        """

        return self._fail()

    async def _fail(self) -> AsyncIterator[EngineEvent]:
        """抛出 worker / proxy 异常。

        :returns: EngineEvent 异步流。
        :raises RuntimeError: 始终抛出以模拟 worker / proxy 异常。
        """

        empty_events: tuple[EngineEvent, ...] = ()
        for event in empty_events:
            yield event
        raise RuntimeError("smoke worker failure")


def parse_args(argv: Sequence[str]) -> SmokeArgs:
    """解析命令行参数。

    :param argv: 不含程序名的参数序列。
    :returns: 解析后的 smoke 参数。
    :raises SystemExit: 参数非法时由 argparse 抛出。
    """

    parser = argparse.ArgumentParser(
        description="Run manual Host P1.5 EventLog smoke checks."
    )
    parser.add_argument(
        "--case",
        choices=("success", "worker-failure"),
        default="success",
    )
    parser.add_argument(
        "--log-level",
        choices=tuple(level.name for level in LogLevel),
        default=LogLevel.DEBUG.name,
    )
    namespace = parser.parse_args(list(argv))
    case_name: SmokeCaseName = namespace.case
    log_level_name: str = namespace.log_level
    return SmokeArgs(
        case_name=case_name,
        log_level=LogLevel[log_level_name],
    )


def _utc_now() -> datetime:
    """返回当前 UTC 时间。

    :returns: 当前 UTC 时间。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


def _request(case_name: SmokeCaseName) -> StartRunRequest:
    """构造 Host StartRunRequest。

    :param case_name: smoke case 名称。
    :returns: StartRunRequest。
    :raises Exception: 不主动抛出异常。
    """

    return StartRunRequest(
        session_id=_SESSION_ID,
        run_id=f"{_RUN_ID_PREFIX}_{case_name}",
        input=RunInput(
            messages=(UserMessage(role=AgentMessageRole.USER, content=_PROMPT),)
        ),
        options=RunOptions(
            runner_spec=RunnerSpec(
                provider="smoke",
                model="fake",
                endpoint="https://example.invalid/v1/chat/completions",
                api_key_ref="SMOKE_ONLY",
                headers={},
                supports_tool_calling=False,
                supports_streaming=True,
                supports_stream_usage=False,
                default_timeout_seconds=_DEFAULT_TIMEOUT_SECONDS,
                max_retries=_DEFAULT_MAX_RETRIES,
                provider_request=None,
            ),
            runner_options=RunnerCallOptions(
                temperature=None,
                max_tokens=None,
                top_p=None,
                stream=True,
            ),
            agent_policy=AgentPolicy(
                max_iterations=_DEFAULT_MAX_ITERATIONS,
                continuation_max_attempts=0,
                allow_tool_calls=False,
            ),
            stream=True,
            disable_tools=True,
            tool_schemas=(),
        ),
    )


def _success_events(request: StartRunRequest) -> tuple[EngineEvent, ...]:
    """构造成功路径 EngineEvent 脚本。

    :param request: Host StartRunRequest。
    :returns: EngineEvent 元组。
    :raises Exception: 不主动抛出异常。
    """

    return (
        EngineEvent(
            event_id=f"{request.run_id}_engine_final",
            sequence=101,
            occurred_at=_utc_now(),
            session_id=request.session_id,
            run_id=request.run_id,
            type=EngineEventType.FINAL_ANSWER,
            data=FinalAnswerData(
                content="EventLog smoke done.",
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
            metadata=None,
        ),
    )


def _build_harness(
    *,
    case_name: SmokeCaseName,
    request: StartRunRequest,
) -> LocalRunHarness:
    """构造 smoke 使用的 LocalRunHarness。

    :param case_name: smoke case 名称。
    :param request: Host StartRunRequest。
    :returns: LocalRunHarness。
    :raises Exception: 不主动抛出异常。
    """

    store = InMemoryRunEventStore()
    if case_name == "success":
        return LocalRunHarness(
            proxy=_ScriptedProxy(events=_success_events(request)),
            event_store=store,
            memory_store=SmokeInMemoryConversationMemoryStore(),
        )
    return LocalRunHarness(
        proxy=_FailingProxy(),
        event_store=store,
        memory_store=SmokeInMemoryConversationMemoryStore(),
    )


async def run_smoke(args: SmokeArgs) -> int:
    """运行 Host EventLog smoke。

    :param args: smoke 参数。
    :returns: 进程退出码。
    :raises Exception: smoke 运行失败时透传异常。
    """

    configure(level=args.log_level)
    request = _request(args.case_name)
    harness = _build_harness(case_name=args.case_name, request=request)
    print(
        f"{_SMOKE_PREFIX} case={args.case_name} run_id={request.run_id} "
        f"log_level={args.log_level.name}"
    )

    stream = await harness.start_run(request)
    last_cursor = stream.handle.event_cursor
    async for event in stream.events:
        last_cursor = event.cursor
        summary = _event_summary(prefix="STREAM", event=event)
        if summary:
            print(summary)

    replay_events = [
        event
        async for event in harness.stream_run_events(
            run_id=request.run_id,
            after=RunEventCursor(sequence=-1),
        )
    ]
    print(
        f"{_SMOKE_PREFIX} replay_count={len(replay_events)} "
        f"last_cursor={last_cursor.sequence}"
    )
    for event in replay_events:
        summary = _event_summary(prefix="REPLAY", event=event)
        if summary:
            print(summary)

    result = await harness.get_run_result(request.run_id)
    print(f"{_SMOKE_PREFIX} result={result!r}")
    return 0


def _event_summary(*, prefix: str, event: RunEvent) -> str:
    """构造 RunEvent 摘要输出。

    :param prefix: 输出前缀。
    :param event: RunEvent。
    :returns: 摘要字符串；高频 delta 事件返回空字符串。
    :raises Exception: 不主动抛出异常。
    """

    if event.type in (
        RunEventType.RUNNER_CONTENT_DELTA,
        RunEventType.RUNNER_REASONING_DELTA,
    ):
        return ""
    return (
        f"{_SMOKE_PREFIX} {prefix} cursor={event.cursor.sequence} "
        f"type={event.type.value} kind={event.kind.value} "
        f"source={event.source.value} engine_event_id="
        f"{event.source_engine_event_id}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """smoke 入口。

    :param argv: 可选参数序列；为 ``None`` 时读取 ``sys.argv``。
    :returns: 进程退出码。
    :raises Exception: smoke 运行失败时透传异常。
    """

    args = parse_args(sys.argv[1:] if argv is None else argv)
    return asyncio.run(run_smoke(args))


if __name__ == "__main__":
    raise SystemExit(main())
