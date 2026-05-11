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
import hashlib
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

_REPO_ROOT_PARENT_INDEX: int = 1


def _ensure_repo_root_on_path() -> None:
    """确保按文件路径运行脚本时也能导入仓库顶层包。

    ``python utils/smoke_engine_worker.py`` 会把 ``utils/`` 放在
    ``sys.path[0]``，导致顶层 ``utils`` 包不可见。本函数只在直接按文件
    路径执行时把仓库根目录补入 ``sys.path``；``python -m`` 运行时不改动。

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

from dayu.engine import (
    AgentRunRequest,
    AgentMessageRole,
    AgentPolicy,
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    RunnerCallOptions,
    RunnerSpec,
    UserMessage,
)
from dayu.engine.runners.openai.payload import build_request_payload
from dayu.host import RunInput, RunOptions, StartRunRequest
import dayu.host._worker as worker_module
from dayu.host._worker import EngineWorker
from dayu.runtime.log import LogLevel, configure
from utils.smoke_async_agent_tool_call import (
    AddNumbersToolExecutor,
    CASES,
    ProviderCase,
    add_numbers_schema,
    build_request as build_agent_smoke_request,
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
_DEBUG_PREFIX: str = "DEBUG_COMPARE"
_DEBUG_API_KEY: str = "DEBUG_ONLY_API_KEY"
_AUTHORIZATION_HEADER: str = "Authorization"
_REDACTED_VALUE: str = "<redacted>"


@dataclass(frozen=True, slots=True)
class SmokeArgs:
    """解析后的 smoke 参数。

    :param case_name: 指定 case；为 ``None`` 表示运行全部 case。
    :param run_all: 是否运行全部 case。
    :param stream: 是否启用流式。
    :param timeout_seconds: provider 默认超时秒数。
    :param debug_compare_agent_smoke: 是否只做本地请求构造对比，不发网络。
    """

    case_name: str | None
    run_all: bool
    stream: bool
    timeout_seconds: float
    debug_compare_agent_smoke: bool


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


@dataclass(frozen=True, slots=True)
class _EmptyEngineEventStream:
    """用于捕获 EngineWorker 装配请求的空 EngineEvent 流。"""

    def __aiter__(self) -> "_EmptyEngineEventStream":
        """返回自身作为异步迭代器。

        :returns: 自身。
        :raises Exception: 不主动抛出异常。
        """

        return self

    async def __anext__(self) -> EngineEvent:
        """结束空事件流。

        :returns: 不会正常返回。
        :raises StopAsyncIteration: 始终抛出以结束迭代。
        """

        raise StopAsyncIteration


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
    parser.add_argument(
        "--debug-compare-agent-smoke",
        action="store_true",
        help=(
            "compare local EngineWorker AgentRunRequest construction with "
            "utils.smoke_async_agent_tool_call without sending network requests"
        ),
    )
    namespace = parser.parse_args(list(argv))
    stream_value: Literal["true", "false"] = namespace.stream
    return SmokeArgs(
        case_name=namespace.case,
        run_all=namespace.run_all,
        stream=stream_value == "true",
        timeout_seconds=namespace.timeout_seconds,
        debug_compare_agent_smoke=namespace.debug_compare_agent_smoke,
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


async def _capture_engine_worker_request(
    *,
    worker: EngineWorker,
    request: StartRunRequest,
) -> AgentRunRequest:
    """捕获 EngineWorker 实际装配出的 AgentRunRequest。

    本函数临时替换 ``dayu.host._worker.run_agent_messages``，只捕获
    EngineWorker 传入 Engine 的请求，不发起 provider 网络请求。

    :param worker: 待验证的 EngineWorker。
    :param request: Host StartRunRequest。
    :returns: EngineWorker 装配出的 AgentRunRequest。
    :raises AssertionError: 未捕获到请求时抛出。
    """

    captured: list[AgentRunRequest] = []
    original = worker_module.run_agent_messages

    def capture_run_agent_messages(
        engine_request: AgentRunRequest,
    ) -> _EmptyEngineEventStream:
        """捕获 AgentRunRequest 并返回空事件流。

        :param engine_request: EngineWorker 装配出的请求。
        :returns: 空 EngineEvent 流。
        :raises Exception: 不主动抛出异常。
        """

        captured.append(engine_request)
        return _EmptyEngineEventStream()

    worker_module.run_agent_messages = capture_run_agent_messages
    try:
        async for _event in worker.run_agent_messages(
            request=request,
            tool_schemas=request.options.tool_schemas,
            cancellation_token=_SmokeCancellationToken(),
        ):
            pass
    finally:
        worker_module.run_agent_messages = original
    if not captured:
        raise AssertionError("EngineWorker did not build AgentRunRequest")
    return captured[0]


def _redacted_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """返回脱敏 headers。

    :param headers: 原始 headers。
    :returns: Authorization 已脱敏的 headers。
    :raises Exception: 不主动抛出异常。
    """

    redacted: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() == _AUTHORIZATION_HEADER.lower():
            redacted[key] = _REDACTED_VALUE
        else:
            redacted[key] = value
    return redacted


def _payload_json(request: AgentRunRequest) -> str:
    """构造 Runner HTTP payload JSON 字符串。

    :param request: AgentRunRequest。
    :returns: 排序后的 JSON 字符串。
    :raises TypeError: payload 无法 JSON 序列化时由 json 抛出。
    """

    payload = build_request_payload(
        messages=request.messages,
        options=request.runner_options,
        tools=request.tool_schemas,
        spec=request.runner_spec,
    )
    return json.dumps(dict(payload), ensure_ascii=False, sort_keys=True)


def _sha256_text(value: str) -> str:
    """计算文本 SHA256。

    :param value: 输入文本。
    :returns: SHA256 十六进制摘要。
    :raises Exception: 不主动抛出异常。
    """

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _request_debug_lines(
    *, label: str, request: AgentRunRequest
) -> tuple[str, ...]:
    """生成脱敏 AgentRunRequest 摘要行。

    :param label: 摘要标签。
    :param request: AgentRunRequest。
    :returns: 摘要行元组。
    :raises Exception: 不主动抛出异常。
    """

    payload_json = _payload_json(request)
    tool_names = tuple(schema.function.name for schema in request.tool_schemas)
    message_roles = tuple(message.role.value for message in request.messages)
    headers = _redacted_headers(request.runner_spec.headers)
    return (
        f"{_DEBUG_PREFIX} {label}.run_id={request.run_id}",
        f"{_DEBUG_PREFIX} {label}.session_id={request.session_id}",
        f"{_DEBUG_PREFIX} {label}.stream={request.stream}",
        f"{_DEBUG_PREFIX} {label}.disable_tools={request.disable_tools}",
        f"{_DEBUG_PREFIX} {label}.message_roles={message_roles!r}",
        f"{_DEBUG_PREFIX} {label}.tool_names={tool_names!r}",
        f"{_DEBUG_PREFIX} {label}.executor={type(request.tool_executor).__name__}",
        f"{_DEBUG_PREFIX} {label}.cancel_token={type(request.cancellation_token).__name__}",
        f"{_DEBUG_PREFIX} {label}.provider={request.runner_spec.provider}",
        f"{_DEBUG_PREFIX} {label}.model={request.runner_spec.model}",
        f"{_DEBUG_PREFIX} {label}.endpoint={request.runner_spec.endpoint}",
        f"{_DEBUG_PREFIX} {label}.api_key_ref={request.runner_spec.api_key_ref}",
        f"{_DEBUG_PREFIX} {label}.headers={headers!r}",
        f"{_DEBUG_PREFIX} {label}.provider_request={request.runner_spec.provider_request!r}",
        f"{_DEBUG_PREFIX} {label}.payload_bytes={len(payload_json.encode('utf-8'))}",
        f"{_DEBUG_PREFIX} {label}.payload_sha256={_sha256_text(payload_json)}",
    )


def _compare_field(
    *, field_name: str, direct_value: str, worker_value: str
) -> str | None:
    """比较单个字符串字段。

    :param field_name: 字段名。
    :param direct_value: direct Agent smoke 字段值。
    :param worker_value: EngineWorker smoke 字段值。
    :returns: 差异摘要；相同返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if direct_value == worker_value:
        return None
    return (
        f"{_DEBUG_PREFIX} diff.{field_name} "
        f"agent={direct_value!r} worker={worker_value!r}"
    )


def _material_differences(
    *, direct_request: AgentRunRequest, worker_request: AgentRunRequest
) -> tuple[str, ...]:
    """返回可能影响 provider payload 的字段差异。

    :param direct_request: 原 Agent smoke 请求。
    :param worker_request: EngineWorker 装配请求。
    :returns: 差异摘要元组。
    :raises Exception: 不主动抛出异常。
    """

    direct_payload = _payload_json(direct_request)
    worker_payload = _payload_json(worker_request)
    differences: list[str] = []
    payload_diff = _compare_field(
        field_name="payload_sha256",
        direct_value=_sha256_text(direct_payload),
        worker_value=_sha256_text(worker_payload),
    )
    if payload_diff is not None:
        differences.append(payload_diff)
    for field_name, direct_value, worker_value in (
        ("stream", str(direct_request.stream), str(worker_request.stream)),
        (
            "disable_tools",
            str(direct_request.disable_tools),
            str(worker_request.disable_tools),
        ),
        (
            "runner_options",
            repr(direct_request.runner_options),
            repr(worker_request.runner_options),
        ),
        (
            "agent_policy",
            repr(direct_request.agent_policy),
            repr(worker_request.agent_policy),
        ),
        (
            "runner_spec",
            repr(direct_request.runner_spec),
            repr(worker_request.runner_spec),
        ),
        (
            "messages",
            repr(direct_request.messages),
            repr(worker_request.messages),
        ),
        (
            "tool_schemas",
            repr(direct_request.tool_schemas),
            repr(worker_request.tool_schemas),
        ),
    ):
        diff = _compare_field(
            field_name=field_name,
            direct_value=direct_value,
            worker_value=worker_value,
        )
        if diff is not None:
            differences.append(diff)
    return tuple(differences)


async def debug_compare_agent_smoke_case(
    *,
    case: ProviderCase,
    api_key: str,
    stream: bool,
    timeout_seconds: float,
) -> bool:
    """对比原 Agent smoke 与 EngineWorker smoke 的本地请求构造。

    :param case: provider case。
    :param api_key: API key 明文，仅用于构造等价 headers，不会输出。
    :param stream: 是否启用流式。
    :param timeout_seconds: 默认请求超时秒数。
    :returns: 关键 provider payload 与运行参数一致返回 ``True``。
    :raises Exception: 本地构造异常时透传。
    """

    direct_request = build_agent_smoke_request(
        case=case,
        api_key=api_key,
        stream=stream,
        timeout_seconds=timeout_seconds,
        tool_executor=AddNumbersToolExecutor(),
    )
    host_request = build_request(
        case=case,
        api_key=api_key,
        stream=stream,
        timeout_seconds=timeout_seconds,
    )
    worker_request = await _capture_engine_worker_request(
        worker=EngineWorker(tool_executor=AddNumbersToolExecutor()),
        request=host_request,
    )
    print(f"{_DEBUG_PREFIX} case={case.name} stream={stream}")
    for line in _request_debug_lines(label="agent", request=direct_request):
        print(line)
    for line in _request_debug_lines(label="worker", request=worker_request):
        print(line)
    differences = _material_differences(
        direct_request=direct_request,
        worker_request=worker_request,
    )
    for difference in differences:
        print(difference)
    print(f"{_DEBUG_PREFIX} material_diff_count={len(differences)}")
    return len(differences) == 0


async def debug_compare_agent_smoke(
    *, args: SmokeArgs, env: Mapping[str, str]
) -> int:
    """运行本地构造对比，不发送网络请求。

    :param args: smoke 参数。
    :param env: 环境变量映射。
    :returns: 全部 case 关键字段一致返回 0，否则返回 1。
    :raises Exception: 不主动抛出异常；单 case 异常会转为返回码。
    """

    exit_code = 0
    for case in select_cases(args):
        api_key = env.get(case.env_var, _DEBUG_API_KEY)
        try:
            matched = await debug_compare_agent_smoke_case(
                case=case,
                api_key=api_key,
                stream=args.stream,
                timeout_seconds=args.timeout_seconds,
            )
        except Exception as exc:
            print(
                f"{_DEBUG_PREFIX} {case.name} failed "
                f"exc_type={type(exc).__name__}"
            )
            exit_code = 1
            continue
        if not matched:
            exit_code = 1
    return exit_code


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
        tool_schemas=request.options.tool_schemas,
        cancellation_token=_SmokeCancellationToken(),
    ):
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
    """运行选中的 EngineWorker smoke cases。

    :param args: smoke 参数。
    :param env: 环境变量映射。
    :returns: 进程退出码。
    :raises Exception: 不主动抛出异常；单 case 异常会转为返回码。
    """

    if args.debug_compare_agent_smoke:
        return await debug_compare_agent_smoke(args=args, env=env)
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
