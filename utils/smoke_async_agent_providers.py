"""人工验证 AsyncAgent 与 OpenAI-compatible provider 的 smoke 脚本。

本脚本只服务人工验证，不属于生产链路，也不做真实联网 pytest。它只从
环境变量读取 API key，输出 case 名、事件类型、长度类摘要以及固定 smoke
prompt 的 final answer，避免泄漏 key、headers、完整 payload 或业务内容。
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

from dayu.contracts.tool_call import BatchToolExecutionRequest
from dayu.contracts.tool_outcome import (
    BatchToolExecutionOutcome,
    BatchToolExecutionRecord,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import ToolResultFailure
from dayu.engine import (
    AgentMessageRole,
    AgentPolicy,
    AgentRunRequest,
    DeepSeekThinkingExtension,
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    GeminiThinkingExtension,
    MimoThinkingExtension,
    ProviderRequestExtension,
    QwenThinkingExtension,
    RunnerCallOptions,
    RunnerSpec,
    ToolExecutor,
    UserMessage,
    run_agent_messages,
)
from dayu.engine.contracts.runner_spec import ClientCorrelationPolicy
from dayu.runtime.log import LogLevel, configure

_PROMPT: str = "用一句话回答：2+2 等于几？"
_DEFAULT_TIMEOUT_SECONDS: float = 60.0
_TOOL_EXECUTION_TIMEOUT_SECONDS: float = 5.0
_DEFAULT_MAX_RETRIES: int = 0
_DEFAULT_MAX_TOKENS: int = 64
_MAX_ITERATIONS_WITHOUT_TOOLS: int = 1
_CONTINUATION_MAX_ATTEMPTS_WITHOUT_TOOLS: int = 0
_RUN_ID_PREFIX: str = "smoke_async_agent"
_SKIP_PREFIX: str = "SKIP"
_CASE_PREFIX: str = "CASE"
_EVENT_PREFIX: str = "EVENT"
_SUMMARY_PREFIX: str = "SUMMARY"
_FINAL_SUMMARY_PREFIX: str = "FINAL_SUMMARY"
_GEMINI_DYNAMIC_THINKING_BUDGET: int = -1


@dataclass(frozen=True, slots=True)
class ProviderCase:
    """provider smoke case。

    :param name: case 名称。
    :param env_var: API key 环境变量名。
    :param provider: RunnerSpec provider 字段。
    :param endpoint: OpenAI-compatible chat completions endpoint。
    :param model: 模型名。
    :param supports_stream_usage: 是否支持 stream usage。
    :param provider_request: provider thinking 请求扩展。
    """

    name: str
    env_var: str
    provider: str
    endpoint: str
    model: str
    supports_stream_usage: bool
    provider_request: ProviderRequestExtension


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


class _NoopToolExecutor:
    """Phase 2 smoke 的 no-op ToolExecutor。

    该 executor 不应被调用；若 Phase 2 边界误触发工具执行，返回失败
    outcome 以便 smoke 显示异常终态。
    """

    async def execute(
        self, request: BatchToolExecutionRequest
    ) -> BatchToolExecutionOutcome:
        """返回工具误调用失败 outcome 批次。

        :param request: 批式工具执行请求。
        :returns: 与输入 ``calls`` 一一对应的失败 outcome 批次。
        :raises Exception: 不主动抛出异常。
        """

        records = tuple(
            BatchToolExecutionRecord(
                tool_call_id=call.tool_call_id,
                outcome=ToolFailedOutcome(
                    result=ToolResultFailure(
                        ok=False,
                        error="tool_executor_not_expected_in_phase2_smoke",
                        message=f"unexpected tool execution: {call.name}",
                        hint=None,
                        meta=None,
                    )
                ),
            )
            for call in request.calls
        )
        return BatchToolExecutionOutcome(records=records)


CASES: tuple[ProviderCase, ...] = (
    ProviderCase(
        name="mimo-v2.5-pro-plan",
        env_var="MIMO_PLAN_API_KEY",
        provider="mimo",
        endpoint="https://token-plan-cn.xiaomimimo.com/v1/chat/completions",
        model="mimo-v2.5-pro",
        supports_stream_usage=False,
        provider_request=MimoThinkingExtension(enabled=True),
    ),
    ProviderCase(
        name="deepseek-v4-flash",
        env_var="DEEPSEEK_API_KEY",
        provider="deepseek",
        endpoint="https://api.deepseek.com/chat/completions",
        model="deepseek-v4-flash",
        supports_stream_usage=True,
        provider_request=DeepSeekThinkingExtension(enabled=True),
    ),
    ProviderCase(
        name="gemini-2.5-flash",
        env_var="GEMINI_API_KEY",
        provider="gemini",
        endpoint=(
            "https://generativelanguage.googleapis.com/v1beta/openai/"
            "chat/completions"
        ),
        model="gemini-2.5-flash",
        supports_stream_usage=False,
        provider_request=GeminiThinkingExtension(
            thinking_budget=_GEMINI_DYNAMIC_THINKING_BUDGET,
            include_thoughts=True,
        ),
    ),
    ProviderCase(
        name="qwen-plus",
        env_var="QWEN_API_KEY",
        provider="qwen",
        endpoint=(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/"
            "chat/completions"
        ),
        model="qwen3.6-plus",
        supports_stream_usage=True,
        provider_request=QwenThinkingExtension(enable_thinking=True),
    ),
)


def parse_args(argv: Sequence[str]) -> SmokeArgs:
    """解析命令行参数。

    :param argv: 不含程序名的参数序列。
    :returns: 解析后的 :class:`SmokeArgs`。
    :raises SystemExit: 参数非法时由 argparse 抛出。
    """

    case_names = tuple(case.name for case in CASES)
    parser = argparse.ArgumentParser(
        description="Run manual AsyncAgent provider smoke checks."
    )
    parser.add_argument("--case", choices=case_names, default=None)
    parser.add_argument("--all", action="store_true", dest="run_all")
    parser.add_argument(
        "--stream",
        choices=("true", "false"),
        default="true",
    )
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
) -> AgentRunRequest:
    """构造 AgentRunRequest。

    :param case: provider case。
    :param api_key: API key 明文，仅进入请求头，不输出。
    :param stream: 是否启用流式。
    :param timeout_seconds: 默认请求超时秒数。
    :returns: AgentRunRequest。
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
        client_correlation_policy=ClientCorrelationPolicy.DISABLED,
        supports_tool_calling=False,
        supports_streaming=True,
        supports_stream_usage=case.supports_stream_usage,
        default_timeout_seconds=timeout_seconds,
        max_retries=_DEFAULT_MAX_RETRIES,
        provider_request=case.provider_request,
    )
    return AgentRunRequest(
        run_id=f"{_RUN_ID_PREFIX}_{case.name}",
        session_id=f"{_RUN_ID_PREFIX}_session",
        messages=(
            UserMessage(role=AgentMessageRole.USER, content=_PROMPT),
        ),
        disable_tools=True,
        runner_spec=spec,
        runner_options=RunnerCallOptions(
            temperature=None,
            max_tokens=_DEFAULT_MAX_TOKENS,
            top_p=None,
            stream=stream,
        ),
        agent_policy=AgentPolicy(
            max_iterations=_MAX_ITERATIONS_WITHOUT_TOOLS,
            continuation_max_attempts=_CONTINUATION_MAX_ATTEMPTS_WITHOUT_TOOLS,
            allow_tool_calls=False,
            tool_execution_timeout_seconds=_TOOL_EXECUTION_TIMEOUT_SECONDS,
        ),
        tool_schemas=(),
        tool_executor=_NoopToolExecutor(),
        cancellation_token=_SmokeCancellationToken(),
    )


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


def safe_event_summary(event: EngineEvent) -> str:
    """返回不含敏感载荷的事件摘要。

    :param event: EngineEvent。
    :returns: 安全摘要字符串。
    :raises Exception: 不主动抛出异常。
    """

    data = event.data
    if event.type is EngineEventType.CONTENT_DELTA:
        return f"{_EVENT_PREFIX} {event.type.value}"
    if event.type is EngineEventType.FINAL_ANSWER and isinstance(
        data, FinalAnswerData
    ):
        return (
            f"{_EVENT_PREFIX} {event.type.value} "
            f"content_len={len(data.content)} filtered={data.filtered} "
            f"content={data.content!r}"
        )
    return f"{_EVENT_PREFIX} {event.type.value}"


async def run_case(
    *,
    case: ProviderCase,
    api_key: str,
    stream: bool,
    timeout_seconds: float,
) -> str | None:
    """运行单个 provider smoke case。

    :param case: provider case。
    :param api_key: API key 明文，仅进入请求头，不输出。
    :param stream: 是否启用流式。
    :param timeout_seconds: 默认请求超时秒数。
    :returns: final answer 文本；未收到 final answer 时返回 ``None``。
    :raises Exception: provider 请求或 Agent 运行异常时透传。
    """

    request = build_request(
        case=case,
        api_key=api_key,
        stream=stream,
        timeout_seconds=timeout_seconds,
    )
    final_answer: str | None = None
    print(f"{_CASE_PREFIX} {case.name} start stream={stream}")
    async for event in run_agent_messages(request):
        print(safe_event_summary(event))
        data = event.data
        if event.type is EngineEventType.FINAL_ANSWER and isinstance(
            data, FinalAnswerData
        ):
            final_answer = data.content
    print(
        f"{_SUMMARY_PREFIX} {case.name} "
        f"final_seen={final_answer is not None}"
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
    print()
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
    """运行选中的 provider smoke cases。

    :param args: smoke 参数。
    :param env: 环境变量映射。
    :returns: 进程退出码。
    :raises Exception: 不主动抛出异常；单 case 异常会转为返回码。
    """

    exit_code = 0
    first_case = True
    final_answers: list[CaseFinalAnswer] = []
    for case in select_cases(args):
        if first_case:
            first_case = False
        else:
            print()
        api_key = env.get(case.env_var)
        if not api_key:
            print(f"{_SKIP_PREFIX} {case.name} missing_env={case.env_var}")
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
            continue
        if final_answer is None:
            exit_code = 1
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
