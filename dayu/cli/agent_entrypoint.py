"""CLI Agent entrypoint 共享辅助能力。

本模块提供 CLI entrypoint 共用的参数校验、路径解析、执行 override 映射和
运行阶段 SIGINT 观察基础实现。这里不承载 Service 语义，不调用 Host API，
也不访问 Fins storage。
"""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Callable
from contextlib import suppress
from enum import Enum, auto
from pathlib import Path
from types import FrameType
from typing import TypeAlias, TypeVar

from dayu.cli.arg_parsing import ParsedCliArgs
from dayu.service.host_assembly import ServiceRunOverrides

UsageErrorFactory = Callable[[str], ValueError]

BASE_OPTION_NAME: str = "--base"
CONFIG_DIR_OPTION_NAME: str = "--config"
FALLBACK_MODE_OPTION_NAME: str = "--fallback-mode"
FALLBACK_PROMPT_OPTION_NAME: str = "--fallback-prompt"
_TaskResult = TypeVar("_TaskResult")
_SignalHandler: TypeAlias = signal.Handlers | int | Callable[[int, FrameType | None], None]


class _CliSigintInstallationMode(Enum):
    """CLI SIGINT handler 的安装与恢复模式。"""

    NONE = auto()
    ASYNCIO = auto()
    SYNCHRONOUS = auto()


class CliSigintMonitor:
    """asyncio handler 优先、同步 handler fallback 的 SIGINT 观察器。

    观察器优先通过当前事件循环安装 ``SIGINT`` handler；平台不支持时，
    同步 handler 只把通知线程安全地投递回同一事件循环。具体收到第一次
    或第二次中断后如何取消 Host Run 或 direct operation，由调用方命令
    状态机决定。
    """

    count: int
    _event: asyncio.Event
    _loop: asyncio.AbstractEventLoop | None
    _installation_mode: _CliSigintInstallationMode
    _previous_handler: _SignalHandler | None

    def __init__(self) -> None:
        """初始化 SIGINT monitor。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.count = 0
        self._event = asyncio.Event()
        self._loop = None
        self._installation_mode = _CliSigintInstallationMode.NONE
        self._previous_handler = None

    def install(self) -> None:
        """在当前事件循环安装 SIGINT handler。

        :returns: ``None``。
        :raises RuntimeError: 当前进程的既有 SIGINT handler 无法读取时抛出。
        :raises OSError: 同步 fallback handler 安装失败时抛出。
        :raises ValueError: 当前线程不允许安装同步 signal handler 时抛出。
        """

        loop = asyncio.get_running_loop()
        previous_handler = signal.getsignal(signal.SIGINT)
        if previous_handler is None:
            raise RuntimeError("SIGINT previous handler is unavailable")
        try:
            loop.add_signal_handler(signal.SIGINT, self.notify)
        except (NotImplementedError, RuntimeError):
            self._installation_mode = _CliSigintInstallationMode.SYNCHRONOUS
            self._loop = loop
            self._previous_handler = previous_handler
            try:
                signal.signal(signal.SIGINT, self._notify_from_synchronous_handler)
            except BaseException:
                self._installation_mode = _CliSigintInstallationMode.NONE
                self._loop = None
                self._previous_handler = None
                raise
            return
        self._installation_mode = _CliSigintInstallationMode.ASYNCIO
        self._loop = loop
        self._previous_handler = previous_handler

    def close(self) -> None:
        """移除当前 monitor 安装的 SIGINT handler。

        :returns: ``None``。
        :raises OSError: 底层 SIGINT handler 恢复失败时抛出。
        :raises ValueError: 当前线程不允许恢复 signal handler 时抛出。
        :raises RuntimeError: 已安装模式缺少对应恢复状态时抛出。
        """

        if self._installation_mode is _CliSigintInstallationMode.ASYNCIO:
            if self._loop is None or self._previous_handler is None:
                raise RuntimeError("asyncio SIGINT installation state is incomplete")
            self._loop.remove_signal_handler(signal.SIGINT)
            signal.signal(signal.SIGINT, self._previous_handler)
        elif self._installation_mode is _CliSigintInstallationMode.SYNCHRONOUS:
            if self._loop is None or self._previous_handler is None:
                raise RuntimeError("synchronous SIGINT installation state is incomplete")
            signal.signal(signal.SIGINT, self._previous_handler)
        self._installation_mode = _CliSigintInstallationMode.NONE
        self._loop = None
        self._previous_handler = None

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

    def _notify_from_synchronous_handler(
        self,
        _signal_number: int,
        _frame: FrameType | None,
    ) -> None:
        """把同步 Python signal handler 通知投递回已捕获事件循环。

        :param _signal_number: ``signal.signal`` 传入的 SIGINT 编号。
        :param _frame: ``signal.signal`` 传入的当前栈帧。
        :returns: ``None``。
        :raises RuntimeError: 同步安装状态缺少事件循环时抛出。
        """

        loop = self._loop
        if self._installation_mode is not _CliSigintInstallationMode.SYNCHRONOUS or loop is None:
            raise RuntimeError("synchronous SIGINT installation state is incomplete")
        loop.call_soon_threadsafe(self.notify)

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
        raise error_factory(f"{CONFIG_DIR_OPTION_NAME} must stay inside workspace root: {resolved}") from exc
    if not resolved.is_dir():
        raise error_factory(f"{CONFIG_DIR_OPTION_NAME} is not a directory: {resolved}")
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
            max_consecutive_failed_tool_batches=(args.max_consecutive_failed_tool_batches),
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
)
