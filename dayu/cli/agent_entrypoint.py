"""CLI Agent entrypoint 共享辅助能力。

本模块只服务 ``dayu-cli prompt`` 与 ``dayu-cli interactive`` 这两个
Agent entrypoint UI adapter。这里不承载 Service 语义，不调用 Host API，
也不访问 Fins storage；只抽取两类命令在 CLI 层内完全相同的参数校验、
路径解析、执行 override 映射和运行阶段 SIGINT 观察基础实现。
"""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from types import FrameType
from typing import TypeVar

from dayu.cli.arg_parsing import ParsedCliArgs
from dayu.service.host_assembly import ServiceRunOverrides

UsageErrorFactory = Callable[[str], ValueError]

BASE_OPTION_NAME: str = "--base"
CONFIG_DIR_OPTION_NAME: str = "--config"
FALLBACK_MODE_OPTION_NAME: str = "--fallback-mode"
FALLBACK_PROMPT_OPTION_NAME: str = "--fallback-prompt"
_TaskResult = TypeVar("_TaskResult")


class CliSigintMonitor:
    """CLI Agent Run 阶段的 SIGINT 观察器。

    观察器只负责在当前 asyncio 事件循环安装和移除 ``SIGINT`` handler，
    并把用户中断转换为可等待的本地计数。具体收到第一次或第二次中断后
    如何取消 Host Run，由调用方命令状态机决定。
    """

    count: int
    _event: asyncio.Event
    _loop: asyncio.AbstractEventLoop | None
    _installed: bool

    def __init__(self) -> None:
        """初始化 SIGINT monitor。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.count = 0
        self._event = asyncio.Event()
        self._loop = None
        self._installed = False

    def install(self) -> None:
        """在当前事件循环安装 SIGINT handler。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常；不支持 loop signal handler 时保留
            默认 ``KeyboardInterrupt`` 行为。
        """

        loop = asyncio.get_running_loop()
        try:
            loop.add_signal_handler(signal.SIGINT, self.notify)
        except (NotImplementedError, RuntimeError):
            self._installed = False
            self._loop = None
            return
        self._installed = True
        self._loop = loop

    def close(self) -> None:
        """移除当前 monitor 安装的 SIGINT handler。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if self._installed and self._loop is not None:
            self._loop.remove_signal_handler(signal.SIGINT)
        self._installed = False
        self._loop = None

    def notify(
        self,
        _signal_number: int | None = None,
        _frame: FrameType | None = None,
    ) -> None:
        """记录一次 SIGINT。

        :param _signal_number: ``signal.signal`` 风格 handler 兼容参数。
        :param _frame: ``signal.signal`` 风格 handler 兼容参数。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.count += 1
        self._event.set()

    async def wait_next(self, observed_count: int) -> int:
        """等待下一次 SIGINT。

        :param observed_count: 调用方已经观察到的 SIGINT 计数。
        :returns: 新的 SIGINT 计数。
        :raises asyncio.CancelledError: 等待任务被取消时透传。
        """

        while self.count <= observed_count:
            await self._event.wait()
            self._event.clear()
        return self.count


async def cancel_and_await_task(task: asyncio.Task[_TaskResult]) -> None:
    """取消并回收 asyncio task。

    :param task: 待取消或已结束的 task。
    :returns: ``None``。
    :raises Exception: task 已经以非取消异常结束时向上透传，避免吞掉异步
        状态机错误。
    """

    if not task.done():
        task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def resolve_workspace_root(value: str, *, error_factory: UsageErrorFactory) -> Path:
    """解析 CLI workspace root。

    :param value: argparse 解析到的 workspace root 文本。
    :param error_factory: 用于构造当前命令用法错误的异常工厂。
    :returns: 解析后的绝对路径。
    :raises ValueError: workspace root 为空时通过 ``error_factory`` 抛出。
    """

    stripped = require_cli_text(
        value,
        field_name=BASE_OPTION_NAME,
        error_factory=error_factory,
    )
    return Path(stripped).expanduser().resolve(strict=False)


def resolve_explicit_config_dir(
    *,
    config_dir: str | None,
    workspace_root: Path,
    error_factory: UsageErrorFactory,
) -> Path | None:
    """解析并校验显式 ``--config`` 目录。

    :param config_dir: 用户显式传入的配置目录；未提供时为 ``None``。
    :param workspace_root: 已解析的 workspace root。
    :param error_factory: 用于构造当前命令用法错误的异常工厂。
    :returns: 解析后的显式配置目录；未提供时为 ``None``。
    :raises ValueError: 路径为空、逃逸 workspace 或不是目录时通过
        ``error_factory`` 抛出。
    """

    if config_dir is None:
        return None
    stripped = require_cli_text(
        config_dir,
        field_name=CONFIG_DIR_OPTION_NAME,
        error_factory=error_factory,
    )
    raw_path = Path(stripped).expanduser()
    candidate = raw_path if raw_path.is_absolute() else workspace_root / raw_path
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(workspace_root)
    except ValueError as exc:
        raise error_factory(
            f"{CONFIG_DIR_OPTION_NAME} must stay inside workspace root: {resolved}"
        ) from exc
    if not resolved.is_dir():
        raise error_factory(
            f"{CONFIG_DIR_OPTION_NAME} is not a directory: {resolved}"
        )
    return resolved


def optional_stripped_text(
    value: str | None,
    *,
    field_name: str,
    error_factory: UsageErrorFactory,
) -> str | None:
    """校验并裁剪可选 CLI 文本。

    :param value: 待校验文本。
    :param field_name: 错误消息字段名。
    :param error_factory: 用于构造当前命令用法错误的异常工厂。
    :returns: 裁剪后的文本；未提供时返回 ``None``。
    :raises ValueError: 文本为空或仅包含空白时通过 ``error_factory`` 抛出。
    """

    if value is None:
        return None
    return require_cli_text(
        value,
        field_name=field_name,
        error_factory=error_factory,
    )


def require_cli_text(
    value: str,
    *,
    field_name: str,
    error_factory: UsageErrorFactory,
) -> str:
    """校验 CLI 文本参数非空并裁剪。

    :param value: 待校验文本。
    :param field_name: 错误消息字段名。
    :param error_factory: 用于构造当前命令用法错误的异常工厂。
    :returns: 裁剪后的文本。
    :raises ValueError: 文本为空或仅包含空白时通过 ``error_factory`` 抛出。
    """

    stripped = value.strip()
    if stripped == "":
        raise error_factory(f"{field_name} must not be empty")
    return stripped


def unsupported_execution_option_names(args: ParsedCliArgs) -> tuple[str, ...]:
    """返回用户显式使用但当前 Agent entrypoint 不支持的旧执行选项名。

    :param args: prompt 或 interactive 命令参数。
    :returns: unsupported option 名称元组。
    :raises Exception: 不主动抛出异常。
    """

    names: list[str] = []
    if args.thinking is not None:
        names.append("--thinking/--no-thinking")
    if args.web_provider is not None:
        names.append("--web-provider")
    if args.debug_sse:
        names.append("--debug-sse")
    if args.debug_tool_delta:
        names.append("--debug-tool-delta")
    if args.debug_sse_sample_rate is not None:
        names.append("--debug-sse-sample-rate")
    if args.debug_sse_throttle_sec is not None:
        names.append("--debug-sse-throttle-sec")
    if args.enable_tool_trace:
        names.append("--enable-tool-trace")
    if args.tool_trace_dir is not None:
        names.append("--tool-trace-dir")
    if args.max_duplicate_tool_calls is not None:
        names.append("--max-duplicate-tool-calls")
    if args.duplicate_tool_hint_prompt is not None:
        names.append("--duplicate-tool-hint-prompt")
    if args.doc_limits_json is not None:
        names.append("--doc-limits-json")
    if args.fins_limits_json is not None:
        names.append("--fins-limits-json")
    return tuple(names)


def service_run_overrides_from_args(
    args: ParsedCliArgs,
    *,
    error_factory: UsageErrorFactory,
) -> ServiceRunOverrides:
    """把 Agent entrypoint 可映射执行参数转换为 ServiceRunOverrides。

    :param args: prompt 或 interactive 命令参数。
    :param error_factory: 用于构造当前命令用法错误的异常工厂。
    :returns: ServiceRunOverrides。
    :raises ValueError: 数值或枚举 override 非法时通过 ``error_factory`` 抛出。
    """

    try:
        return ServiceRunOverrides(
            temperature=args.temperature,
            tool_execution_timeout_seconds=args.tool_timeout_seconds,
            max_iterations=args.max_iterations,
            fallback_mode=optional_stripped_text(
                args.fallback_mode,
                field_name=FALLBACK_MODE_OPTION_NAME,
                error_factory=error_factory,
            ),
            fallback_prompt=optional_stripped_text(
                args.fallback_prompt,
                field_name=FALLBACK_PROMPT_OPTION_NAME,
                error_factory=error_factory,
            ),
            max_consecutive_failed_tool_batches=(
                args.max_consecutive_failed_tool_batches
            ),
        )
    except ValueError as exc:
        raise error_factory(str(exc)) from exc


def package_config_root() -> Path:
    """返回包内默认配置根目录。

    :returns: ``dayu/config`` 绝对路径。
    :raises Exception: 不主动抛出异常。
    """

    return Path(__file__).resolve().parents[1] / "config"


__all__: tuple[str, ...] = (
    "CliSigintMonitor",
    "cancel_and_await_task",
    "package_config_root",
    "optional_stripped_text",
    "resolve_explicit_config_dir",
    "resolve_workspace_root",
    "service_run_overrides_from_args",
    "unsupported_execution_option_names",
)
