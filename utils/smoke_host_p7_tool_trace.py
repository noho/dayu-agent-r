"""人工验证 Host P7 tool trace JSONL 路径的 smoke 脚本。

本脚本通过 :func:`build_durable_harness` 装配 durable harness，使用
``DurableHarnessConfig(database_path=":memory:", tool_trace_path=<tmp>)``
打开 :class:`ToolTraceObserver`，并注入一个 stub :class:`WorkerProxy` 产
出预定义 EngineEvent 序列，覆盖以下 trace record:

- ``ITERATION_STARTED`` -> 不直接派生 trace，仅提供 iteration_id 上下文。
- ``TOOL_CALL_REQUESTED`` + ``TOOL_RESULT_ACCEPTED`` -> ``tool_call`` record。
- ``RUNNER_USAGE_RECORDED`` -> ``iteration_usage`` record。
- ``PROVIDER_PROTOCOL_ERROR`` -> ``provider_protocol_error`` record，
  验证 raw_payload 中的 provider secret 被 scrub 为 ``"***"``。
- ``FINAL_ANSWER`` -> ``final_response`` record。

注意：P8.5-S1 后 truncation / fetch_more 不再使用专用 canonical fact；
stub proxy 只能注入 EngineEvent，因此本 smoke 不覆盖真实 ToolRuntime 的
ordinary truncation payload 与 framework ``fetch_more`` 普通工具调用路径；
这条路径由 ToolRuntime smoke 或专属 truncation smoke 覆盖。

trace 根目录使用 ``tempfile.mkdtemp(prefix="dayu_p7_smoke_")`` 创建，
**脚本结束后不删除**，便于人工 inspect。脚本末尾会自动调用
:func:`utils.analyze_tool_trace_host.analyze_trace_root` 并打印诊断报告。

运行示例::

    source .venv/bin/activate
    python utils/smoke_host_p7_tool_trace.py
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
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

from dayu.contracts import (  # noqa: E402
    CancellationToken,
    ToolCompletedOutcome,
    ToolResultSuccess,
    ToolTruncationInfo,
)
from dayu.engine import (  # noqa: E402
    AgentMessageRole,
    AgentPolicy,
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    FinishReason,
    IterationStartedData,
    ProviderProtocolErrorData,
    RunnerCallOptions,
    RunnerSpec,
    RunnerUsageData,
    ToolCallRequestedData,
    ToolResultAcceptedData,
    UserMessage,
)
from dayu.host._durable_harness import (  # noqa: E402
    DurableHarnessConfig,
    build_durable_harness,
)
from dayu.host.contracts import (  # noqa: E402
    RunInput,
    RunOptions,
    StartRunRequest,
)
from dayu.runtime.log import LogLevel, configure  # noqa: E402
from utils.analyze_tool_trace_host import (  # noqa: E402
    analyze_trace_root,
)

_SMOKE_RUN_ID: str = "smoke_p7_run_1"
_SMOKE_SESSION_ID: str = "smoke_p7_session"
_SMOKE_USER_TEXT: str = "请帮我分析 AAPL 财报"
_SMOKE_FINAL_TEXT: str = "答案"
_SMOKE_ITERATION_ID: str = "iter-1"
_SMOKE_TOOL_CALL_ID: str = "tc-1"
_SMOKE_TOOL_NAME: str = "lookup_filing"
_TERMINAL_TIMEOUT_SECONDS: float = 5.0
_TMP_PREFIX: str = "dayu_p7_smoke_"


@dataclass(frozen=True, slots=True)
class _SmokeArgs:
    """P7 smoke 命令行参数。"""

    log_level: LogLevel


def _parse_args(argv: Sequence[str]) -> _SmokeArgs:
    """解析 smoke 命令行参数。

    :param argv: 不含程序名的命令行参数。
    :returns: 解析后的 smoke 参数。
    :raises SystemExit: 参数非法时由 argparse 抛出。
    """

    parser = argparse.ArgumentParser(
        description="Run manual Host P7 tool trace JSONL smoke checks."
    )
    parser.add_argument(
        "--log-level",
        choices=tuple(level.name for level in LogLevel),
        default=LogLevel.INFO.name,
        help="Dayu namespace log level; default: INFO.",
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
        """返回迭代器。

        :returns: 迭代器实例。
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
        """逐个产出预定义事件，耗尽后抛 StopAsyncIteration。

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


def _make_event(
    *,
    sequence: int,
    event_type: EngineEventType,
    data: object,
) -> EngineEvent:
    """构造单条 EngineEvent。

    :param sequence: run 内序号。
    :param event_type: 事件类型。
    :param data: 事件 data 对象。
    :returns: :class:`EngineEvent`。
    :raises Exception: 不主动抛出异常。
    """

    return EngineEvent(
        event_id=f"evt-{sequence}",
        sequence=sequence,
        occurred_at=_utc(),
        session_id=_SMOKE_SESSION_ID,
        run_id=_SMOKE_RUN_ID,
        type=event_type,
        data=data,  # pyright: ignore[reportArgumentType]
        metadata=None,
    )


def _build_engine_events() -> tuple[EngineEvent, ...]:
    """构造 stub 用 EngineEvent 序列。

    :returns: EngineEvent 元组。
    :raises Exception: 不主动抛出异常。
    """

    iteration_started = _make_event(
        sequence=1,
        event_type=EngineEventType.ITERATION_STARTED,
        data=IterationStartedData(
            iteration_id=_SMOKE_ITERATION_ID,
            iteration_index=0,
            message_count=2,
        ),
    )
    tool_call_requested = _make_event(
        sequence=2,
        event_type=EngineEventType.TOOL_CALL_REQUESTED,
        data=ToolCallRequestedData(
            iteration_id=_SMOKE_ITERATION_ID,
            tool_call_id=_SMOKE_TOOL_CALL_ID,
            name=_SMOKE_TOOL_NAME,
            arguments={"company": "AAPL"},
            index_in_iteration=0,
            provider_state=None,
        ),
    )
    tool_result_accepted = _make_event(
        sequence=3,
        event_type=EngineEventType.TOOL_RESULT_ACCEPTED,
        data=ToolResultAcceptedData(
            iteration_id=_SMOKE_ITERATION_ID,
            tool_call_id=_SMOKE_TOOL_CALL_ID,
            name=_SMOKE_TOOL_NAME,
            index_in_iteration=0,
            outcome=ToolCompletedOutcome(
                result=ToolResultSuccess(
                    ok=True,
                    value={"summary": "large doc..."},
                    truncation=ToolTruncationInfo(
                        cursor="cur-A",
                        scope_token="st-1",
                        scope_hash="sh-1",
                        has_more=True,
                        limit=10,
                        ttl_seconds=60,
                    ),
                    meta=None,
                )
            ),
        ),
    )
    runner_usage = _make_event(
        sequence=4,
        event_type=EngineEventType.RUNNER_USAGE_RECORDED,
        data=RunnerUsageData(
            iteration_id=_SMOKE_ITERATION_ID,
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=120,
        ),
    )
    provider_error = _make_event(
        sequence=5,
        event_type=EngineEventType.PROVIDER_PROTOCOL_ERROR,
        data=ProviderProtocolErrorData(
            iteration_id=_SMOKE_ITERATION_ID,
            error_code="rate_limited",
            message="429 Too Many Requests",
            provider_request_id="req-1",
            raw_payload={
                "Authorization": "Bearer sk-very-secret",
                "error": {"code": 429},
            },
        ),
    )
    final_answer = _make_event(
        sequence=6,
        event_type=EngineEventType.FINAL_ANSWER,
        data=FinalAnswerData(
            content=_SMOKE_FINAL_TEXT,
            filtered=False,
            degraded=False,
            finish_reason=FinishReason.STOP,
        ),
    )
    return (
        iteration_started,
        tool_call_requested,
        tool_result_accepted,
        runner_usage,
        provider_error,
        final_answer,
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


def _print_jsonl_summary(*, trace_root: Path) -> None:
    """打印 JSONL / raw_payloads 文件清单与按类型计数。

    :param trace_root: trace 根目录。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    sessions_dir = trace_root / "sessions"
    raw_dir = trace_root / "raw_payloads"
    jsonl_files = sorted(sessions_dir.rglob("*.jsonl")) if sessions_dir.exists() else []
    raw_files = sorted(raw_dir.rglob("*.json")) if raw_dir.exists() else []
    print(f"[trace] root={trace_root}")
    print(f"[trace] jsonl_files={len(jsonl_files)}:")
    for path in jsonl_files:
        print(f"  {path.relative_to(trace_root)} size={path.stat().st_size}")
    print(f"[trace] raw_payload_files={len(raw_files)}:")
    for path in raw_files:
        print(f"  {path.relative_to(trace_root)} size={path.stat().st_size}")


def _print_record_breakdown(*, trace_root: Path) -> None:
    """读 JSONL 行，按 trace_type 打印数量与关键字段，并校验 secret scrub。

    :param trace_root: trace 根目录。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    import json

    sessions_dir = trace_root / "sessions"
    if not sessions_dir.exists():
        print("[trace] no sessions directory; nothing to read")
        return
    counts: dict[str, int] = {}
    tool_call_summaries: list[str] = []
    provider_error_payloads: list[str] = []
    for jsonl_path in sorted(sessions_dir.rglob("tool_calls_*.jsonl")):
        with jsonl_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                stripped = raw_line.strip()
                if stripped == "":
                    continue
                record = json.loads(stripped)
                if not isinstance(record, dict):
                    continue
                trace_type_value = record.get("trace_type")
                if not isinstance(trace_type_value, str):
                    continue
                counts[trace_type_value] = counts.get(trace_type_value, 0) + 1
                if trace_type_value == "tool_call":
                    tool_name = record.get("tool_name")
                    outcome_kind = record.get("outcome_kind")
                    tool_call_summaries.append(
                        f"tool={tool_name} outcome={outcome_kind}"
                    )
                if trace_type_value == "provider_protocol_error":
                    raw_payload_json = record.get("raw_payload_json")
                    if isinstance(raw_payload_json, str):
                        provider_error_payloads.append(raw_payload_json)
    print("[trace] record_counts_by_type:")
    for trace_type, count in sorted(counts.items()):
        print(f"  {trace_type}: {count}")
    print(f"[trace] tool_call_summary: {tool_call_summaries}")
    for payload in provider_error_payloads:
        contains_scrub = "***" in payload
        print(
            f"[trace] provider_error raw_payload_json scrubbed={contains_scrub} "
            f"text={payload}"
        )


async def _run_smoke(*, trace_root: Path) -> None:
    """驱动一次完整 start_run -> terminal -> drain 路径，并在结束后调 analyzer。

    :param trace_root: trace 输出根目录（已由 caller 创建）。
    :returns: 无返回值。
    :raises Exception: 子组件异常时透传。
    """

    bundle = build_durable_harness(
        config=DurableHarnessConfig(
            database_path=":memory:",
            tool_trace_path=str(trace_root),
        ),
        proxy=_StubProxy(events=_build_engine_events()),
    )
    try:
        request = _build_request()
        stream = await bundle.harness.start_run(request)
        deadline = asyncio.get_running_loop().time() + _TERMINAL_TIMEOUT_SECONDS
        result = None
        while asyncio.get_running_loop().time() < deadline:
            result = await bundle.harness.get_run_result(request.run_id)
            if result is not None:
                break
            await asyncio.sleep(0.02)
        if result is None:
            raise RuntimeError("smoke timed out waiting for terminal RunResult")
        await bundle.coordinator.drain()
        print(f"[handle] state={stream.handle.state.value}")
        print(f"[run_result] {type(result).__name__}")
        _print_jsonl_summary(trace_root=trace_root)
        _print_record_breakdown(trace_root=trace_root)
        print("[analyzer] running analyze_trace_root ...")
        report = analyze_trace_root(trace_root=trace_root)
        print(
            f"[analyzer] total_lines_read={report.total_lines_read} "
            f"deduped_record_count={report.deduped_record_count} "
            f"duplicate_keys={len(report.duplicate_idempotency_keys)}"
        )
        print(
            f"[analyzer] provider_protocol_error_count="
            f"{report.provider_protocol_error_count} "
            f"final_response_present={report.final_response_present}"
        )
        print(
            f"[analyzer] repeated_tool_calls={len(report.repeated_tool_calls)} "
            f"truncation_without_fetch_more="
            f"{len(report.truncation_without_fetch_more)} "
            f"fetch_more_unknown_cursor="
            f"{len(report.fetch_more_with_unknown_scope_token)} "
            f"position_gaps={len(report.source_event_position_gaps)}"
        )
        print(
            f"[analyzer] record_counts_by_type={dict(report.record_counts_by_type)}"
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
    trace_root = Path(tempfile.mkdtemp(prefix=_TMP_PREFIX))
    print(f"[smoke] trace tmp dir (NOT cleaned up): {trace_root}")
    asyncio.run(_run_smoke(trace_root=trace_root))


if __name__ == "__main__":
    main()
