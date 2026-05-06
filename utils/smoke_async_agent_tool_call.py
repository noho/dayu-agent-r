"""人工验证 AsyncAgent 普通 tool calling 闭环的 smoke 脚本。

本脚本只服务人工验证，不属于生产链路，也不做真实联网 pytest。它使用
真实 provider 加极小 fake ``add_numbers`` ToolExecutor，验证模型 tool
call -> 工具结果注入 -> 下一轮 final answer 的闭环。API key 只从环境变量
读取，输出包含 case、事件类型、序号、工具名、长度类摘要与固定 smoke
prompt 的 final answer，避免泄漏 key、headers、完整 payload 或业务内容。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import ToolExecutionRequest
from dayu.contracts.tool_outcome import (
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import ToolResultFailure, ToolResultSuccess
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
    ToolCallRequestedData,
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolResultAcceptedData,
    ToolSchema,
    UserMessage,
    run_agent_messages,
)
from dayu.runtime.log import LogLevel, configure

_LOGGER: logging.Logger = logging.getLogger("dayu.utils.smoke_async_agent_tool_call")
_PROMPT: str = "请调用工具 add_numbers 计算 2+3，然后用一句话回答结果。"
_DEFAULT_TIMEOUT_SECONDS: float = 60.0
_DEFAULT_MAX_RETRIES: int = 0
_DEFAULT_MAX_TOKENS: int = 128
_RUN_ID_PREFIX: str = "smoke_async_agent_tool_call"
_SKIP_PREFIX: str = "SKIP"
_CASE_PREFIX: str = "CASE"
_EVENT_PREFIX: str = "EVENT"
_SUMMARY_PREFIX: str = "SUMMARY"
_FINAL_SUMMARY_PREFIX: str = "FINAL_SUMMARY"
_GEMINI_DYNAMIC_THINKING_BUDGET: int = -1
_MAX_ARG_STR_LEN: int = 40
_MAX_COMPACT_ARGS_LEN: int = 120
_MAX_SUMMARY_STR_LEN: int = 40


@dataclass(frozen=True, slots=True)
class ProviderCase:
    """provider tool-call smoke case。

    :param name: case 名称。
    :param env_var: API key 环境变量名。
    :param provider: RunnerSpec provider 字段。
    :param endpoint: OpenAI-compatible chat completions endpoint。
    :param model: 模型名。
    :param supports_stream_usage: 是否支持 stream usage。
    :param provider_request: provider thinking 请求扩展；无扩展为 ``None``。
    """

    name: str
    env_var: str
    provider: str
    endpoint: str
    model: str
    supports_stream_usage: bool
    provider_request: ProviderRequestExtension | None


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
class AddNumbersToolExecutor:
    """极小 fake add_numbers ToolExecutor。

    该 executor 代表 EngineWorker 替 Host 代持的测试替身，不代表生产
    Host ToolRegistry 或 ToolRuntime 实现。
    """

    requests: list[ToolExecutionRequest] = field(default_factory=list)

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionOutcome:
        """执行 add_numbers fake 工具。

        :param request: 工具执行请求。
        :returns: completed 或 failed outcome。
        :raises Exception: 不主动抛出异常。
        """

        self.requests.append(request)
        start_time = time.monotonic()
        _LOGGER.info(
            "工具调用开始: name=%s arguments=%s tool_call_id=%s "
            "index_in_iteration=%s run_id=%s iteration_id=%s",
            request.call.name,
            _compact_tool_arguments(request.call.arguments),
            request.call.tool_call_id,
            request.call.index_in_iteration,
            request.context.run_id,
            request.context.iteration_id,
        )
        if request.call.name != "add_numbers":
            _log_tool_failure(
                tool_name=request.call.name,
                error="unknown_tool",
                message=request.call.name,
                request=request,
                start_time=start_time,
            )
            return _tool_failed("unknown_tool", request.call.name)
        arguments = request.call.arguments
        left = _number_argument(arguments, "a")
        right = _number_argument(arguments, "b")
        if left is None or right is None:
            _log_tool_failure(
                tool_name=request.call.name,
                error="invalid_arguments",
                message=(
                    "add_numbers requires numeric a and b "
                    f"a_type={_argument_type_name(arguments, 'a')} "
                    f"b_type={_argument_type_name(arguments, 'b')}"
                ),
                request=request,
                start_time=start_time,
            )
            return _tool_failed(
                "invalid_arguments",
                "add_numbers requires numeric a and b",
            )
        result = left + right
        result_value: Mapping[str, JsonValue] = {"sum": result}
        result_size = len(
            json.dumps(
                {"ok": True, "value": result_value},
                ensure_ascii=False,
            )
        )
        latency_ms = int((time.monotonic() - start_time) * 1000)
        _LOGGER.info(
            "工具调用完成: name=%s result=%s latency_ms=%s result_chars=%s "
            "tool_call_id=%s index_in_iteration=%s run_id=%s iteration_id=%s",
            request.call.name,
            _tool_result_summary(result_value),
            latency_ms,
            result_size,
            request.call.tool_call_id,
            request.call.index_in_iteration,
            request.context.run_id,
            request.context.iteration_id,
        )
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value=result_value,
                truncation=None,
                meta=None,
            )
        )


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


def _tool_failed(error: str, message: str) -> ToolFailedOutcome:
    """构造 fake 工具失败 outcome。

    :param error: 错误码。
    :param message: 错误描述。
    :returns: ToolFailedOutcome。
    :raises Exception: 不主动抛出异常。
    """

    return ToolFailedOutcome(
        result=ToolResultFailure(
            ok=False,
            error=error,
            message=message,
            hint=None,
            meta=None,
        )
    )


def _number_argument(
    arguments: Mapping[str, JsonValue], name: str
) -> int | float | None:
    """读取数字参数。

    :param arguments: 工具参数映射。
    :param name: 参数名。
    :returns: 数字参数；不存在或类型不符时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    value = arguments.get(name)
    if isinstance(value, bool):
        return None
    if isinstance(value, int) or isinstance(value, float):
        return value
    return None


def _compact_tool_arguments(
    arguments: Mapping[str, JsonValue],
    max_len: int = _MAX_COMPACT_ARGS_LEN,
) -> str:
    """将工具调用参数格式化为 OLD 风格的紧凑单行字符串。

    :param arguments: 工具参数映射。
    :param max_len: 输出最大字符数。
    :returns: 形如 ``a=2, b=3`` 的参数摘要。
    :raises Exception: 不主动抛出异常。
    """

    parts: list[str] = []
    for key, value in arguments.items():
        if value is None:
            continue
        if isinstance(value, str) and len(value) > _MAX_ARG_STR_LEN:
            value_text = repr(value[:_MAX_ARG_STR_LEN]) + "..."
        else:
            value_text = repr(value)
        parts.append(f"{key}={value_text}")
    result = ", ".join(parts)
    if len(result) > max_len:
        return result[:max_len] + "..."
    return result


def _tool_result_summary(value: Mapping[str, JsonValue]) -> str:
    """返回 OLD 风格的工具成功结果摘要。

    :param value: 工具结果 value。
    :returns: 紧凑结果摘要；无可展示字段时返回 ``ok``。
    :raises Exception: 不主动抛出异常。
    """

    parts: list[str] = []
    for key, item in value.items():
        if len(parts) >= 4:
            break
        if isinstance(item, bool):
            parts.append(f"{key}={item}")
        elif isinstance(item, str):
            rendered = item[:_MAX_SUMMARY_STR_LEN]
            suffix = "..." if len(item) > _MAX_SUMMARY_STR_LEN else ""
            parts.append(f"{key}={rendered!r}{suffix}")
        elif isinstance(item, int) or isinstance(item, float):
            parts.append(f"{key}={item!r}")
    if not parts:
        return "ok"
    return " ".join(parts)


def _log_tool_failure(
    *,
    tool_name: str,
    error: str,
    message: str,
    request: ToolExecutionRequest,
    start_time: float,
) -> None:
    """使用项目日志系统记录工具失败。

    :param tool_name: 工具名称。
    :param error: 工具失败错误码。
    :param message: 工具失败消息。
    :param request: 工具执行请求。
    :param start_time: 工具开始执行时的单调时钟。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    latency_ms = int((time.monotonic() - start_time) * 1000)
    _LOGGER.warning(
        "工具调用失败: name=%s error=%s message=%s latency_ms=%s "
        "tool_call_id=%s index_in_iteration=%s run_id=%s iteration_id=%s",
        tool_name,
        error,
        message,
        latency_ms,
        request.call.tool_call_id,
        request.call.index_in_iteration,
        request.context.run_id,
        request.context.iteration_id,
    )


def _argument_type_name(arguments: Mapping[str, JsonValue], name: str) -> str:
    """返回工具参数类型名称。

    :param arguments: 工具参数映射。
    :param name: 参数名。
    :returns: 参数缺失时返回 ``missing``，否则返回运行时类型名。
    :raises Exception: 不主动抛出异常。
    """

    value = arguments.get(name)
    if value is None:
        return "missing"
    return type(value).__name__


def add_numbers_schema() -> ToolSchema:
    """返回 fake add_numbers schema。

    :returns: ToolSchema。
    :raises Exception: 不主动抛出异常。
    """

    return ToolSchema(
        type="function",
        function=ToolFunctionSchema(
            name="add_numbers",
            description="Add two numbers and return their sum.",
            parameters=ToolParametersSchema(
                type="object",
                properties={
                    "a": {"type": "number"},
                    "b": {"type": "number"},
                },
                required=("a", "b"),
                additional_properties=False,
            ),
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
        description="Run manual AsyncAgent tool-call smoke checks."
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
    tool_executor: AddNumbersToolExecutor,
) -> AgentRunRequest:
    """构造 AgentRunRequest。

    :param case: provider case。
    :param api_key: API key 明文，仅进入请求头，不输出。
    :param stream: 是否启用流式。
    :param timeout_seconds: 默认请求超时秒数。
    :param tool_executor: fake ToolExecutor。
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
        supports_tool_calling=True,
        supports_streaming=True,
        supports_stream_usage=case.supports_stream_usage,
        default_timeout_seconds=timeout_seconds,
        max_retries=_DEFAULT_MAX_RETRIES,
        provider_request=case.provider_request,
    )
    return AgentRunRequest(
        run_id=f"{_RUN_ID_PREFIX}_{case.name}",
        session_id=f"{_RUN_ID_PREFIX}_session",
        messages=(UserMessage(role=AgentMessageRole.USER, content=_PROMPT),),
        stream=stream,
        disable_tools=False,
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
        tool_schemas=(add_numbers_schema(),),
        tool_executor=tool_executor,
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
    """返回不含 key、prompt 与工具参数的事件摘要。

    :param event: EngineEvent。
    :returns: 安全摘要字符串；高频 delta 事件返回空字符串。
    :raises Exception: 不主动抛出异常。
    """

    data = event.data
    if event.type in (
        EngineEventType.RUNNER_CONTENT_DELTA,
        EngineEventType.RUNNER_REASONING_DELTA,
    ):
        return ""
    if event.type is EngineEventType.TOOL_CALL_REQUESTED and isinstance(
        data, ToolCallRequestedData
    ):
        return (
            f"{_EVENT_PREFIX} {event.type.value} sequence={event.sequence} "
            f"tool={data.name}"
        )
    if event.type is EngineEventType.TOOL_RESULT_ACCEPTED and isinstance(
        data, ToolResultAcceptedData
    ):
        return (
            f"{_EVENT_PREFIX} {event.type.value} sequence={event.sequence} "
            f"tool={data.name} outcome={type(data.outcome).__name__}"
        )
    if event.type is EngineEventType.FINAL_ANSWER and isinstance(
        data, FinalAnswerData
    ):
        return (
            f"{_EVENT_PREFIX} {event.type.value} sequence={event.sequence} "
            f"content_len={len(data.content)} degraded={data.degraded} "
            f"filtered={data.filtered} "
            f"finish_reason={data.finish_reason.value} "
            f"content={data.content!r}"
        )
    return f"{_EVENT_PREFIX} {event.type.value} sequence={event.sequence}"


async def run_case(
    *,
    case: ProviderCase,
    api_key: str,
    stream: bool,
    timeout_seconds: float,
) -> str | None:
    """运行单个 provider tool-call smoke case。

    :param case: provider case。
    :param api_key: API key 明文，仅进入请求头，不输出。
    :param stream: 是否启用流式。
    :param timeout_seconds: 默认请求超时秒数。
    :returns: final answer 文本；未收到 final answer 时返回 ``None``。
    :raises Exception: provider 请求或 Agent 运行异常时透传。
    """

    tool_executor = AddNumbersToolExecutor()
    request = build_request(
        case=case,
        api_key=api_key,
        stream=stream,
        timeout_seconds=timeout_seconds,
        tool_executor=tool_executor,
    )
    final_answer: str | None = None
    print(f"{_CASE_PREFIX} {case.name} start stream={stream}")
    async for event in run_agent_messages(request):
        summary = safe_event_summary(event)
        if summary:
            print(summary)
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
    """运行选中的 provider smoke cases。

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
