"""人工验证 Host P1 EngineWorker 装配边界的 smoke 脚本。

本脚本只服务人工验证，不属于生产链路，也不做真实联网 pytest。它使用
真实 provider 加极小 fake ``add_numbers`` ToolExecutor，直接调用 Host
内部 ``EngineWorker`` wrapper，验证 Host ``StartRunRequest`` ->
``AgentRunRequest`` -> Engine 事件流的装配链路。

API key 只从环境变量读取，输出包含 case、事件类型、序号、工具名、长度
类摘要与固定 smoke prompt 的 final answer，避免泄漏 key、headers、完整
payload 或业务内容。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from dayu.engine import (
    AgentMessageRole,
    AgentPolicy,
    EngineEventType,
    FinalAnswerData,
    RunnerCallOptions,
    RunnerSpec,
    UserMessage,
)
from dayu.host import RunInput, RunOptions, StartRunRequest
from dayu.host._worker import EngineWorker
from dayu.runtime.log import LogLevel, configure
from utils.smoke_async_agent_tool_call import (
    AddNumbersToolExecutor,
    CASES,
    ProviderCase,
    add_numbers_schema,
    safe_event_summary,
)

_PROMPT: str = "请调用工具 add_numbers 计算 2+3，然后用一句话回答结果。"
_DEFAULT_TIMEOUT_SECONDS: float = 60.0
_DEFAULT_MAX_RETRIES: int = 0
_DEFAULT_MAX_TOKENS: int = 128
_RUN_ID_PREFIX: str = "smoke_engine_worker"
_SKIP_PREFIX: str = "SKIP"
_CASE_PREFIX: str = "CASE"
_SUMMARY_PREFIX: str = "SUMMARY"
_FINAL_SUMMARY_PREFIX: str = "FINAL_SUMMARY"


@dataclass(frozen=True, slots=True)
class SmokeArgs:
    """解析后的 smoke 参数。

    :param case_name: 指定 case；为 ``None`` 表示运行全部 case。
    :param run_all: 是否运行全部 case。
    :param stream: 是否启用流式。
    :param timeout_seconds: provider 默认超时秒数。
    """

    case_name: str | None
    run_all: bool
    stream: bool
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class CaseFinalAnswer:
    """单个 provider smoke 的最终回答摘要。

    :param provider: provider 名称。
    :param prompt: smoke prompt。
    :param final_answer: 最终回答；未产出 final answer 时为 ``None``。
    """

    provider: str
    prompt: str
    final_answer: str | None


@dataclass(slots=True)
class _SmokeCancellationToken:
    """smoke 脚本使用的未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 始终返回 ``False``。
        :raises Exception: 不主动抛出异常。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None


def parse_args(argv: Sequence[str]) -> SmokeArgs:
    """解析命令行参数。

    :param argv: 不含程序名的参数序列。
    :returns: 解析后的 smoke 参数。
    :raises SystemExit: 参数非法时由 argparse 抛出。
    """

    case_names = tuple(case.name for case in CASES)
    parser = argparse.ArgumentParser(
        description="Run manual Host EngineWorker smoke checks."
    )
    parser.add_argument("--case", choices=case_names, default=None)
    parser.add_argument("--all", action="store_true", dest="run_all")
    parser.add_argument("--stream", choices=("true", "false"), default="true")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=_DEFAULT_TIMEOUT_SECONDS,
    )
    namespace = parser.parse_args(list(argv))
    stream_value: Literal["true", "false"] = namespace.stream
    return SmokeArgs(
        case_name=namespace.case,
        run_all=namespace.run_all,
        stream=stream_value == "true",
        timeout_seconds=namespace.timeout_seconds,
    )


def select_cases(args: SmokeArgs) -> tuple[ProviderCase, ...]:
    """根据参数选择待运行 case。

    :param args: 解析后的 smoke 参数。
    :returns: 待运行 case 元组。
    :raises ValueError: 指定 case 不存在时抛出。
    """

    if args.case_name is None:
        return CASES
    for case in CASES:
        if case.name == args.case_name:
            return (case,)
    raise ValueError(f"unknown provider case: {args.case_name}")


def build_request(
    *,
    case: ProviderCase,
    api_key: str,
    stream: bool,
    timeout_seconds: float,
) -> StartRunRequest:
    """构造 Host StartRunRequest。

    :param case: provider case。
    :param api_key: API key 明文，仅进入请求头，不输出。
    :param stream: 是否启用流式。
    :param timeout_seconds: 默认请求超时秒数。
    :returns: Host StartRunRequest。
    :raises Exception: 不主动抛出异常。
    """

    spec = RunnerSpec(
        provider=case.provider,
        model=case.model,
        endpoint=case.endpoint,
        api_key_ref=case.env_var,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        supports_tool_calling=True,
        supports_streaming=True,
        supports_stream_usage=case.supports_stream_usage,
        default_timeout_seconds=timeout_seconds,
        max_retries=_DEFAULT_MAX_RETRIES,
        provider_request=case.provider_request,
    )
    return StartRunRequest(
        session_id=f"{_RUN_ID_PREFIX}_session",
        run_id=f"{_RUN_ID_PREFIX}_{case.name}",
        input=RunInput(
            messages=(UserMessage(role=AgentMessageRole.USER, content=_PROMPT),)
        ),
        options=RunOptions(
            runner_spec=spec,
            runner_options=RunnerCallOptions(
                temperature=None,
                max_tokens=_DEFAULT_MAX_TOKENS,
                top_p=None,
                stream=stream,
            ),
            agent_policy=AgentPolicy(
                max_iterations=2,
                continuation_max_attempts=0,
                allow_tool_calls=True,
            ),
            stream=stream,
            disable_tools=False,
            tool_schemas=(add_numbers_schema(),),
        ),
    )


async def run_case(
    *,
    case: ProviderCase,
    api_key: str,
    stream: bool,
    timeout_seconds: float,
) -> str | None:
    """运行单个 EngineWorker smoke case。

    :param case: provider case。
    :param api_key: API key 明文，仅进入请求头，不输出。
    :param stream: 是否启用流式。
    :param timeout_seconds: 默认请求超时秒数。
    :returns: final answer 文本；未收到 final answer 时返回 ``None``。
    :raises Exception: provider 请求、EngineWorker 或 Engine 运行异常时透传。
    """

    tool_executor = AddNumbersToolExecutor()
    worker = EngineWorker(tool_executor=tool_executor)
    request = build_request(
        case=case,
        api_key=api_key,
        stream=stream,
        timeout_seconds=timeout_seconds,
    )
    final_answer: str | None = None
    print(f"{_CASE_PREFIX} {case.name} worker=EngineWorker stream={stream}")
    async for event in worker.run_agent_messages(
        request=request,
        cancellation_token=_SmokeCancellationToken(),
    ):
        print(safe_event_summary(event))
        data = event.data
        if event.type is EngineEventType.FINAL_ANSWER and isinstance(
            data, FinalAnswerData
        ):
            final_answer = data.content
    print(
        f"{_SUMMARY_PREFIX} {case.name} "
        f"final_seen={final_answer is not None} "
        f"tool_calls={len(tool_executor.requests)}"
    )
    return final_answer


def print_final_answers(records: Sequence[CaseFinalAnswer]) -> None:
    """打印全部 provider 的最终回答汇总。

    :param records: 最终回答记录序列。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    if not records:
        return
    print(f"{_FINAL_SUMMARY_PREFIX} begin")
    for record in records:
        print(
            f"{_FINAL_SUMMARY_PREFIX} provider={record.provider} "
            f"prompt={record.prompt!r} "
            f"final_answer={record.final_answer!r}"
        )
    print(f"{_FINAL_SUMMARY_PREFIX} end")


async def run_selected_cases(
    *, args: SmokeArgs, env: Mapping[str, str]
) -> int:
    """运行选中的 EngineWorker smoke cases。

    :param args: smoke 参数。
    :param env: 环境变量映射。
    :returns: 进程退出码。
    :raises Exception: 不主动抛出异常；单 case 异常会转为返回码。
    """

    exit_code = 0
    final_answers: list[CaseFinalAnswer] = []
    for case in select_cases(args):
        api_key = env.get(case.env_var)
        if not api_key:
            print(f"{_SKIP_PREFIX} {case.name} missing_env={case.env_var}")
            print()
            continue
        try:
            final_answer = await run_case(
                case=case,
                api_key=api_key,
                stream=args.stream,
                timeout_seconds=args.timeout_seconds,
            )
            final_answers.append(
                CaseFinalAnswer(
                    provider=case.provider,
                    prompt=_PROMPT,
                    final_answer=final_answer,
                )
            )
        except Exception as exc:
            print(
                f"{_SUMMARY_PREFIX} {case.name} failed "
                f"exc_type={type(exc).__name__}"
            )
            exit_code = 1
            print()
            continue
        if final_answer is None:
            exit_code = 1
        print()
    print_final_answers(final_answers)
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    """脚本入口。

    :param argv: 不含程序名的参数；为 ``None`` 时读取 ``sys.argv``。
    :returns: 进程退出码。
    :raises SystemExit: 参数解析错误时由 argparse 抛出。
    """

    configure(level=LogLevel.DEBUG)
    args = parse_args(tuple(sys.argv[1:] if argv is None else argv))
    return asyncio.run(run_selected_cases(args=args, env=os.environ))


if __name__ == "__main__":
    raise SystemExit(main())
