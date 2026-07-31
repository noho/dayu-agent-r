"""Dayu 日志装配入口。

本模块是 Dayu 进程内**唯一**的 logger 装配入口，由上层（Host / CLI）调用。
各业务层模块一律使用 stdlib ``logging.getLogger(__name__)`` 获取层内
logger，由本模块通过 ``dayu`` namespace logger 统一配置 level 与
handler。若业务层需要层中立日志辅助函数，辅助函数必须显式接收调用点的
stdlib logger，避免把模块归属收敛到 runtime。

本模块不实现业务语义、不持有运行期状态；configure 之外不暴露任何全局
副作用。设计要点：

- :func:`configure` 默认**只**配置 ``logging.getLogger("dayu")`` 这个
  namespace logger，**不**触动 root logger，**不**默认污染
  pytest ``caplog``（caplog 默认抓 root；当 ``configure()`` 设置
  ``propagate=False`` 后，调用方需要显式
  ``caplog.set_level(level, logger="dayu")`` 才能抓到）。
- 自有 diagnostic handler 通过 ``_HANDLER_MARKER_ATTR`` 标记，重复
  :func:`configure` 调用先移除自有 marker handler 再重新安装，保证
  幂等且不堆叠。
- ``configure_root=True`` 才允许配置 root logger；默认 ``False``。
- :func:`configure_selected_diagnostics` 把公开 canonical 日志等级映射为
  stdlib 数值阈值，并与 stream 诊断开关正交地调用
  :func:`configure`。
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping
from enum import IntEnum, StrEnum
from typing import Final, TextIO, TypeAlias

from dayu.contracts.json_value import JsonValue
from dayu.runtime.log_levels import (
    CRITICAL_LOG_LEVEL,
    DEBUG_LOG_LEVEL,
    ERROR_LOG_LEVEL,
    INFO_LOG_LEVEL,
    QUIET_LOG_LEVEL,
    STREAM_DEBUG_LOG_LEVEL,
    VERBOSE_LOG_LEVEL,
    WARN_LOG_LEVEL,
)

_NAMESPACE_LOGGER_NAME: Final[str] = "dayu"
_HANDLER_MARKER_ATTR: Final[str] = "_dayu_runtime_log_marker"
_HANDLER_MARKER_VALUE: Final[str] = "dayu.runtime.log:diagnostic"
_LOG_FORMAT: Final[str] = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
_LOG_DATE_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"
_STREAM_DEBUG_LEVEL_NAME: Final[str] = "STREAM_DEBUG"
_VERBOSE_LEVEL_NAME: Final[str] = "VERBOSE"
_QUIET_STREAM_CONFLICT_DIAGNOSTIC: Final[str] = (
    "quiet diagnostics cannot be combined with debug stream"
)
DEFAULT_LOG_PAYLOAD_KEY_LIMIT: Final[int] = 8
LogArgument: TypeAlias = str | int | float | bool | None

# 默认静默的第三方 logger（迁移自 OLD 行为）：避免 aiohttp / asyncio /
# urllib3 等库在 DEBUG 下淹没 dayu 输出。configure() 会把这些 logger
# 的级别提升到 WARNING，调用方可通过 third_party_overrides 再覆盖。
_DEFAULT_THIRD_PARTY_SUPPRESSIONS: Final[tuple[str, ...]] = (
    "aiohttp",
    "aiohttp.access",
    "aiohttp.client",
    "aiohttp.internal",
    "aiohttp.server",
    "aiohttp.web",
    "aiohttp.websocket",
    "asyncio",
    "urllib3",
    "httpx",
    "httpcore",
)
_DEFAULT_THIRD_PARTY_LEVEL: Final[int] = WARN_LOG_LEVEL


# 在模块导入时注册 Dayu 自定义 level 到 stdlib logging，确保
# logging.getLevelName(...) 返回稳定名称。
logging.addLevelName(STREAM_DEBUG_LOG_LEVEL, _STREAM_DEBUG_LEVEL_NAME)
logging.addLevelName(VERBOSE_LOG_LEVEL, _VERBOSE_LEVEL_NAME)


class LogLevel(IntEnum):
    """Dayu 日志级别枚举。

    数值由 :mod:`dayu.runtime.log_levels` 统一提供，标准级别与 stdlib
    ``logging`` 保持一致以便直接传入 ``setLevel``：

    - :attr:`STREAM_DEBUG` 对应 ``STREAM_DEBUG_LOG_LEVEL``，低于 stdlib
      DEBUG；用于高频 stream delta / SSE / per-delta ingest 诊断。
    - :attr:`DEBUG` 对应 ``DEBUG_LOG_LEVEL``。
    - :attr:`VERBOSE` 对应 ``VERBOSE_LOG_LEVEL``，介于 DEBUG 与 INFO
      之间；CLI ``--verbose`` 映射到此级别。
    - :attr:`INFO` 对应 ``INFO_LOG_LEVEL``。
    - :attr:`WARNING` 对应 ``WARN_LOG_LEVEL``。
    - :attr:`ERROR` 对应 ``ERROR_LOG_LEVEL``。
    - :attr:`CRITICAL` 对应 ``CRITICAL_LOG_LEVEL``。
    - :attr:`QUIET` 对应 ``QUIET_LOG_LEVEL``，表示关闭普通诊断。
    """

    STREAM_DEBUG = STREAM_DEBUG_LOG_LEVEL
    DEBUG = DEBUG_LOG_LEVEL
    VERBOSE = VERBOSE_LOG_LEVEL
    INFO = INFO_LOG_LEVEL
    WARNING = WARN_LOG_LEVEL
    ERROR = ERROR_LOG_LEVEL
    CRITICAL = CRITICAL_LOG_LEVEL
    QUIET = QUIET_LOG_LEVEL


class DiagnosticLogLevel(StrEnum):
    """CLI 与 runtime 共享的公开诊断等级语义。

    该枚举只表达用户可选的普通诊断阈值；``STREAM_DEBUG``
    是内部记录级别，不属于公开 selector。
    """

    DEBUG = "debug"
    VERBOSE = "verbose"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    QUIET = "quiet"


_ORDINARY_LEVEL_BY_DIAGNOSTIC: Final[dict[DiagnosticLogLevel, LogLevel]] = {
    DiagnosticLogLevel.DEBUG: LogLevel.DEBUG,
    DiagnosticLogLevel.VERBOSE: LogLevel.VERBOSE,
    DiagnosticLogLevel.INFO: LogLevel.INFO,
    DiagnosticLogLevel.WARNING: LogLevel.WARNING,
    DiagnosticLogLevel.ERROR: LogLevel.ERROR,
    DiagnosticLogLevel.CRITICAL: LogLevel.CRITICAL,
    DiagnosticLogLevel.QUIET: LogLevel.QUIET,
}


class _DiagnosticAdmissionFilter(logging.Filter):
    """按普通阈值与 stream 开关投影唯一的 handler 准入规则。"""

    def __init__(self, *, ordinary_level: LogLevel, debug_stream: bool) -> None:
        """保存当前诊断选择对应的准入事实。

        :param ordinary_level: 普通诊断记录的数值阈值。
        :param debug_stream: 是否允许精确 ``STREAM_DEBUG`` 记录。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__()
        self._ordinary_level = ordinary_level
        self._debug_stream = debug_stream

    def filter(self, record: logging.LogRecord) -> bool:
        """判断单条日志是否符合当前诊断选择。

        :param record: stdlib logging 传入的候选日志记录。
        :returns: 允许 handler 输出时返回 ``True``，否则返回 ``False``。
        :raises Exception: 不主动抛出异常。
        """

        if record.levelno == STREAM_DEBUG_LOG_LEVEL:
            return self._debug_stream
        if self._ordinary_level is LogLevel.QUIET:
            return False
        return record.levelno >= int(self._ordinary_level)


def configure(
    *,
    level: LogLevel,
    debug_stream: bool = False,
    third_party_overrides: Mapping[str, LogLevel] | None = None,
    configure_root: bool = False,
    suppress_default_third_party: bool = True,
    stream: TextIO | None = None,
) -> None:
    """装配 Dayu 日志输出。

    :param level: 期望的 ``dayu`` namespace logger 级别。
    :param debug_stream: 是否额外输出精确 ``STREAM_DEBUG`` 记录；
        该开关不改变普通诊断阈值。
    :param third_party_overrides: 第三方 logger 的级别映射；仅设置 level，
        不安装 handler；为 ``None`` 表示不调整。
    :param configure_root: 是否同时配置 root logger（默认 ``False``）。
        仅在调用方明确需要让非 ``dayu.*`` 的库日志也输出到诊断流时启用。
    :param suppress_default_third_party: 是否对默认第三方 logger（aiohttp /
        asyncio / urllib3 等）设置为 WARNING。迁移自 OLD 行为，避免在
        DEBUG 下被淹没；``third_party_overrides`` 中的同名 logger 会
        **覆盖**该默认。
    :param stream: 诊断日志输出流；``None`` 表示使用当前 ``sys.stderr``。
    :returns: 无返回值。
    :raises ValueError: ``quiet`` 与 stream 诊断同时开启时抛出。
    """

    if level is LogLevel.QUIET and debug_stream:
        raise ValueError(_QUIET_STREAM_CONFLICT_DIAGNOSTIC)

    effective_stream = sys.stderr if stream is None else stream
    gate_level = LogLevel.STREAM_DEBUG if debug_stream else level
    namespace_logger = logging.getLogger(_NAMESPACE_LOGGER_NAME)
    _reset_marker_handlers(namespace_logger)
    namespace_logger.setLevel(int(gate_level))
    namespace_logger.propagate = False
    namespace_logger.addHandler(
        _build_marker_handler(
            gate_level=gate_level,
            ordinary_level=level,
            debug_stream=debug_stream,
            stream=effective_stream,
        )
    )

    if configure_root:
        root_logger = logging.getLogger()
        _reset_marker_handlers(root_logger)
        root_logger.setLevel(int(gate_level))
        root_logger.addHandler(
            _build_marker_handler(
                gate_level=gate_level,
                ordinary_level=level,
                debug_stream=debug_stream,
                stream=effective_stream,
            )
        )

    if suppress_default_third_party:
        for name in _DEFAULT_THIRD_PARTY_SUPPRESSIONS:
            logging.getLogger(name).setLevel(_DEFAULT_THIRD_PARTY_LEVEL)

    if third_party_overrides is not None:
        for name, override_level in third_party_overrides.items():
            logging.getLogger(name).setLevel(int(override_level))


def configure_selected_diagnostics(
    *,
    level: DiagnosticLogLevel,
    debug_stream: bool,
    stream: TextIO | None = None,
) -> LogLevel:
    """把公开诊断选择映射为 runtime 阈值并完成装配。

    :param level: 已由输入 owner 归一化的 canonical 诊断等级。
    :param debug_stream: 是否额外输出精确 ``STREAM_DEBUG`` 记录。
    :param stream: 诊断日志输出流；``None`` 表示使用当前 ``sys.stderr``。
    :returns: 最终生效的普通诊断数值阈值。
    :raises ValueError: ``quiet`` 与 stream 诊断同时开启时抛出。
    """

    resolved = _ORDINARY_LEVEL_BY_DIAGNOSTIC[level]
    configure(level=resolved, debug_stream=debug_stream, stream=stream)
    return resolved


def log_verbose(
    logger: logging.Logger,
    message: str,
    *args: LogArgument,
) -> None:
    """使用已注册的 stdlib VERBOSE level 记录执行骨架。

    :param logger: 调用点所属模块的 stdlib logger。
    :param message: logging 格式字符串。
    :param args: 格式化参数，只允许当前日志使用的简单标量。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    verbose_level = logging.getLevelName(_VERBOSE_LEVEL_NAME)
    if isinstance(verbose_level, int):
        logger.log(verbose_level, message, *args)


def bounded_payload_keys(payload: Mapping[str, JsonValue]) -> tuple[str, ...]:
    """返回用于日志的有界 payload key 列表。

    本函数只返回排序后的 key，不读取、不格式化、不暴露 payload value。

    :param payload: 已由业务层提供的 JSON-compatible 摘要。
    :returns: 排序且数量受限的 key 元组。
    :raises Exception: 不主动抛出异常。
    """

    return tuple(sorted(payload.keys()))[:DEFAULT_LOG_PAYLOAD_KEY_LIMIT]


def _build_marker_handler(
    *,
    gate_level: LogLevel,
    ordinary_level: LogLevel,
    debug_stream: bool,
    stream: TextIO,
) -> logging.Handler:
    """构造带 marker 的诊断日志 handler。

    :param gate_level: logger 与 handler 共享的前置数值门槛。
    :param ordinary_level: 普通诊断记录的数值阈值。
    :param debug_stream: 是否允许精确 ``STREAM_DEBUG`` 记录。
    :param stream: 诊断日志输出流。
    :returns: 已 setLevel + setFormatter + 打 marker 的 handler。
    :raises Exception: 不主动抛出异常。
    """

    handler = logging.StreamHandler(stream=stream)
    handler.setLevel(int(gate_level))
    handler.addFilter(
        _DiagnosticAdmissionFilter(
            ordinary_level=ordinary_level,
            debug_stream=debug_stream,
        )
    )
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT))
    setattr(handler, _HANDLER_MARKER_ATTR, _HANDLER_MARKER_VALUE)
    return handler


def _reset_marker_handlers(target_logger: logging.Logger) -> None:
    """从目标 logger 中移除所有自有 marker handler。

    :param target_logger: 目标 logger。
    :returns: 无返回值。
    """

    existing = list(target_logger.handlers)
    for handler in existing:
        if getattr(handler, _HANDLER_MARKER_ATTR, None) == _HANDLER_MARKER_VALUE:
            target_logger.removeHandler(handler)


__all__ = [
    "DEFAULT_LOG_PAYLOAD_KEY_LIMIT",
    "DiagnosticLogLevel",
    "LogArgument",
    "LogLevel",
    "bounded_payload_keys",
    "configure",
    "configure_selected_diagnostics",
    "log_verbose",
]
