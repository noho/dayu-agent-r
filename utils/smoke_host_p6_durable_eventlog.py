"""人工验证 Host P6 durable EventLog 路径的 smoke 脚本。

本脚本通过 :func:`build_durable_harness` 装配真实 ``LocalRunHarness``,
注入一个 stub :class:`WorkerProxy` 产出预定义 EngineEvent 序列,然后调用
``harness.start_run`` 经过完整 ingress 路径(USER_INPUT_ACCEPTED ->
RunInputBuilder -> proxy -> append -> terminal -> coordinator.drain)。
观察:

- DurableRunEventStore 写入路径 + global position 顺序。
- attempt_state_store 在 attempt 起止处的写入。
- 终态自动持久化 RunResult 快照(由 _durable_event_store 在同事务写入)。
- ProjectionCoordinator drain + checkpoint 推进。
- memory required projection 写入用户输入 + assistant final。

运行示例::

    source .venv/bin/activate
    python utils/smoke_host_p6_durable_eventlog.py
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

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

from dayu.contracts import CancellationToken  # noqa: E402
from dayu.engine import (  # noqa: E402
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
from dayu.host._durable_harness import build_durable_harness  # noqa: E402
from dayu.host.contracts import (  # noqa: E402
    RunInput,
    RunOptions,
    StartRunRequest,
)
from dayu.runtime.log import LogLevel, configure  # noqa: E402

_SMOKE_RUN_ID: str = "smoke_run_1"
_SMOKE_SESSION_ID: str = "smoke_session"
_SMOKE_USER_TEXT: str = "问题1"
_SMOKE_FINAL_TEXT: str = "答案1"
_TERMINAL_TIMEOUT_SECONDS: float = 5.0


@dataclass(frozen=True, slots=True)
class _SmokeArgs:
    """P6 smoke 命令行参数。"""

    log_level: LogLevel


def _parse_args(argv: Sequence[str]) -> _SmokeArgs:
    """解析 smoke 命令行参数。

    :param argv: 不含程序名的命令行参数。
    :returns: 解析后的 smoke 参数。
    :raises SystemExit: 参数非法时由 argparse 抛出。
    """

    parser = argparse.ArgumentParser(
        description="Run manual Host P6 durable EventLog smoke checks."
    )
    parser.add_argument(
        "--log-level",
        choices=tuple(level.name for level in LogLevel),
        default=LogLevel.VERBOSE.name,
        help="Dayu namespace log level; default: VERBOSE.",
    )
    namespace = parser.parse_args(list(argv))
    log_level_name: str = namespace.log_level
    return _SmokeArgs(log_level=LogLevel[log_level_name])


def _utc() -> datetime:
    """返回当前 UTC 时间。

    :returns: 时区感知的 UTC datetime。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True, slots=True)
class _StubEngineEvents:
    """预定义 EngineEvent 异步流。"""

    events: tuple[EngineEvent, ...]

    def __aiter__(self) -> "_StubEngineEventsIterator":
        """返回异步迭代器。

        :returns: 内部迭代器实例。
        :raises Exception: 不主动抛出异常。
        """

        return _StubEngineEventsIterator(events=self.events)


@dataclass(slots=True)
class _StubEngineEventsIterator:
    """``_StubEngineEvents`` 的迭代器实现。"""

    events: tuple[EngineEvent, ...]
    index: int = 0

    def __aiter__(self) -> "_StubEngineEventsIterator":
        """返回自身。

        :returns: 自身。
        :raises Exception: 不主动抛出异常。
        """

        return self

    async def __anext__(self) -> EngineEvent:
        """逐个产出预定义事件,耗尽后抛 StopAsyncIteration。

        :returns: 下一个 EngineEvent。
        :raises StopAsyncIteration: 序列耗尽时抛出。
        """

        if self.index >= len(self.events):
            raise StopAsyncIteration
        event = self.events[self.index]
        self.index += 1
        return event


@dataclass(frozen=True, slots=True)
class _StubProxy:
    """注入预定义 EngineEvent 序列的 stub WorkerProxy。"""

    events: tuple[EngineEvent, ...]

    def stream_engine_events(
        self,
        request: StartRunRequest,
        cancellation_token: CancellationToken,
    ) -> AsyncIterator[EngineEvent]:
        """返回预定义事件流。

        :param request: start_run 请求。
        :param cancellation_token: 取消 token。
        :returns: 异步 EngineEvent 流。
        :raises Exception: 不主动抛出异常。
        """

        return _StubEngineEvents(events=self.events).__aiter__()


def _build_engine_events() -> tuple[EngineEvent, ...]:
    """构造 stub 用 EngineEvent 序列(单事件 final answer)。

    :returns: 事件元组。
    :raises Exception: 不主动抛出异常。
    """

    occurred_at = _utc()
    return (
        EngineEvent(
            event_id="engine_smoke_final",
            sequence=1,
            occurred_at=occurred_at,
            session_id=_SMOKE_SESSION_ID,
            run_id=_SMOKE_RUN_ID,
            type=EngineEventType.FINAL_ANSWER,
            data=FinalAnswerData(
                content=_SMOKE_FINAL_TEXT,
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
            metadata=None,
        ),
    )


def _build_request() -> StartRunRequest:
    """构造最小 StartRunRequest。

    :returns: StartRunRequest。
    :raises Exception: 不主动抛出异常。
    """

    return StartRunRequest(
        session_id=_SMOKE_SESSION_ID,
        run_id=_SMOKE_RUN_ID,
        input=RunInput(
            messages=(
                UserMessage(role=AgentMessageRole.USER, content=_SMOKE_USER_TEXT),
            )
        ),
        options=RunOptions(
            runner_spec=RunnerSpec(
                provider="openai",
                model="model",
                endpoint="https://example.test/v1/chat/completions",
                api_key_ref="TEST_KEY",
                headers={},
                supports_tool_calling=True,
                supports_streaming=True,
                supports_stream_usage=False,
                default_timeout_seconds=30.0,
                max_retries=0,
                provider_request=None,
            ),
            runner_options=RunnerCallOptions(
                temperature=None,
                max_tokens=None,
                top_p=None,
                stream=True,
            ),
            agent_policy=AgentPolicy(
                max_iterations=3,
                continuation_max_attempts=1,
                allow_tool_calls=True,
            ),
            stream=True,
            disable_tools=True,
            tool_schemas=(),
        ),
    )


async def _run_smoke() -> None:
    """驱动一次完整 start_run -> terminal -> drain 路径,并打印 read model。

    :returns: 无返回值。
    :raises Exception: 子组件异常时透传。
    """

    bundle = build_durable_harness(
        database_path=":memory:",
        proxy=_StubProxy(events=_build_engine_events()),
    )
    try:
        request = _build_request()
        stream = await bundle.harness.start_run(request)
        # 等待终态出现(后台 task 串行 append + drain)。
        deadline = asyncio.get_running_loop().time() + _TERMINAL_TIMEOUT_SECONDS
        result = None
        while asyncio.get_running_loop().time() < deadline:
            result = await bundle.harness.get_run_result(request.run_id)
            if result is not None:
                break
            await asyncio.sleep(0.02)
        if result is None:
            raise RuntimeError("smoke timed out waiting for terminal RunResult")
        print(f"[handle] state={stream.handle.state.value}")
        print(f"[run_result] {type(result).__name__}")
        # 终态后再驱动一次 drain 让 read model 完全追平(harness 自身已 drain)。
        snapshots = await bundle.coordinator.drain()
        for cp in snapshots:
            last = (
                cp.last_success_position.value
                if cp.last_success_position is not None
                else None
            )
            print(
                f"[checkpoint] observer={cp.observer_id} "
                f"status={cp.status.value} "
                f"last_success_position={last} "
                f"lag={cp.lag_events}"
            )

        memory_snapshot = await bundle.memory_store.get_snapshot(
            _SMOKE_SESSION_ID
        )
        print("[memory] recent_raw_turns:")
        for turn in memory_snapshot.recent_raw_turns:
            print(
                f"  user_text={turn.user_text!r} "
                f"assistant_final={turn.assistant_final!r} "
                f"terminal_summary={turn.terminal_summary!r}"
            )

        timeline = bundle.timeline_observer.get_timeline(_SMOKE_RUN_ID)
        print(f"[timeline] {len(timeline)} canonical events:")
        for evt in timeline:
            print(f"  seq={evt.cursor.sequence} type={evt.type.value}")

        audit = bundle.audit_observer.list_records()
        print(f"[audit] {len(audit)} records:")
        for record in audit:
            print(
                f"  position={record.position.value} "
                f"run={record.run_id} type={record.event_type.value}"
            )

        run_record = bundle.run_state_store.get(_SMOKE_RUN_ID)
        run_state_value = (
            run_record.state.value if run_record is not None else "missing"
        )
        terminal_result = bundle.run_state_store.get_terminal_result(
            _SMOKE_RUN_ID
        )
        print(
            f"[run_state] run_id={_SMOKE_RUN_ID} state={run_state_value} "
            f"terminal_result={type(terminal_result).__name__ if terminal_result else None}"
        )
    finally:
        bundle.close()


def main(argv: Sequence[str] | None = None) -> None:
    """脚本入口。

    :param argv: 不含程序名的命令行参数；为 ``None`` 时读取 ``sys.argv``。
    :returns: 无返回值。
    :raises Exception: 子组件异常时透传。
    """

    args = _parse_args(sys.argv[1:] if argv is None else argv)
    configure(level=args.log_level)
    asyncio.run(_run_smoke())


if __name__ == "__main__":
    main()
