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
- :func:`set_level_from_flags` 解析 CLI 风格 flag 集合并调用
  :func:`configure`；返回最终 :class:`LogLevel`。
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping
from enum import IntEnum
from typing import Final, TextIO, TypeAlias

from dayu.contracts.json_value import JsonValue
from dayu.runtime.log_levels import (
    CRITICAL_LOG_LEVEL,
    DEBUG_LOG_LEVEL,
    ERROR_LOG_LEVEL,
    INFO_LOG_LEVEL,
    VERBOSE_LOG_LEVEL,
    WARN_LOG_LEVEL,
)

_NAMESPACE_LOGGER_NAME: Final[str] = "dayu"
_HANDLER_MARKER_ATTR: Final[str] = "_dayu_runtime_log_marker"
_HANDLER_MARKER_VALUE: Final[str] = "dayu.runtime.log:diagnostic"
_LOG_FORMAT: Final[str] = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
_LOG_DATE_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"
_VERBOSE_LEVEL_NAME: Final[str] = "VERBOSE"
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


# 在模块导入时注册 VERBOSE level 到 stdlib logging，确保
# logging.getLevelName(15) 返回 "VERBOSE"。
logging.addLevelName(VERBOSE_LOG_LEVEL, _VERBOSE_LEVEL_NAME)


class LogLevel(IntEnum):
    """Dayu 日志级别枚举。

    数值由 :mod:`dayu.runtime.log_levels` 统一提供，标准级别与 stdlib
    ``logging`` 保持一致以便直接传入 ``setLevel``：

    - :attr:`DEBUG` 对应 ``DEBUG_LOG_LEVEL``。
    - :attr:`VERBOSE` 对应 ``VERBOSE_LOG_LEVEL``，介于 DEBUG 与 INFO
      之间；CLI ``--verbose`` 映射到此级别。
    - :attr:`INFO` 对应 ``INFO_LOG_LEVEL``。
    - :attr:`WARN` 对应 ``WARN_LOG_LEVEL``。
    - :attr:`ERROR` 对应 ``ERROR_LOG_LEVEL``。
    - :attr:`CRITICAL` 对应 ``CRITICAL_LOG_LEVEL``。
    """

    DEBUG = DEBUG_LOG_LEVEL
    VERBOSE = VERBOSE_LOG_LEVEL
    INFO = INFO_LOG_LEVEL
    WARN = WARN_LOG_LEVEL
    ERROR = ERROR_LOG_LEVEL
    CRITICAL = CRITICAL_LOG_LEVEL


def configure(
    *,
    level: LogLevel,
    third_party_overrides: Mapping[str, LogLevel] | None = None,
    configure_root: bool = False,
    suppress_default_third_party: bool = True,
    stream: TextIO | None = None,
) -> None:
    """装配 Dayu 日志输出。

    :param level: 期望的 ``dayu`` namespace logger 级别。
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
    """

    effective_stream = sys.stderr if stream is None else stream
    namespace_logger = logging.getLogger(_NAMESPACE_LOGGER_NAME)
    _reset_marker_handlers(namespace_logger)
    namespace_logger.setLevel(int(level))
    namespace_logger.propagate = False
    namespace_logger.addHandler(_build_marker_handler(level, effective_stream))

    if configure_root:
        root_logger = logging.getLogger()
        _reset_marker_handlers(root_logger)
        root_logger.setLevel(int(level))
        root_logger.addHandler(_build_marker_handler(level, effective_stream))

    if suppress_default_third_party:
        for name in _DEFAULT_THIRD_PARTY_SUPPRESSIONS:
            logging.getLogger(name).setLevel(_DEFAULT_THIRD_PARTY_LEVEL)

    if third_party_overrides is not None:
        for name, override_level in third_party_overrides.items():
            logging.getLogger(name).setLevel(int(override_level))


def set_level_from_flags(
    *,
    log_level: str | None,
    debug: bool,
    verbose: bool,
    info: bool,
    quiet: bool,
    stream: TextIO | None = None,
) -> LogLevel:
    """根据 CLI 风格的 flag 集合解析最终级别并调用 :func:`configure`。

    优先级（高 -> 低）：

    1. ``log_level`` 显式字符串（不区分大小写，必须为 :class:`LogLevel` 名）。
    2. ``quiet`` -> :attr:`LogLevel.ERROR`。
    3. ``debug`` -> :attr:`LogLevel.DEBUG`。
    4. ``verbose`` -> :attr:`LogLevel.VERBOSE`（迁移自 OLD ``VERBOSE=15``）。
    5. ``info`` -> :attr:`LogLevel.INFO`。
    6. 默认 :attr:`LogLevel.INFO`。

    :param log_level: 显式级别字符串；为 ``None`` 表示不指定。
    :param debug: 是否启用 ``--debug``。
    :param verbose: 是否启用 ``--verbose``。
    :param info: 是否启用 ``--info``。
    :param quiet: 是否启用 ``--quiet``。
    :param stream: 诊断日志输出流；``None`` 表示使用当前 ``sys.stderr``。
    :returns: 最终生效的 :class:`LogLevel`。

    :raises ValueError: 当 ``log_level`` 非合法 :class:`LogLevel` 名时抛出。
    """

    resolved = _resolve_level(
        log_level=log_level,
        debug=debug,
        verbose=verbose,
        info=info,
        quiet=quiet,
    )
    configure(level=resolved, stream=stream)
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


def _resolve_level(
    *,
    log_level: str | None,
    debug: bool,
    verbose: bool,
    info: bool,
    quiet: bool,
) -> LogLevel:
    """按优先级解析 :class:`LogLevel`。"""

    if log_level is not None:
        normalized = log_level.strip().upper()
        try:
            return LogLevel[normalized]
        except KeyError as exc:
            raise ValueError(
                f"unknown log_level: {log_level!r}; expected one of "
                f"{[member.name for member in LogLevel]}"
            ) from exc
    if quiet:
        return LogLevel.ERROR
    if debug:
        return LogLevel.DEBUG
    if verbose:
        return LogLevel.VERBOSE
    if info:
        return LogLevel.INFO
    return LogLevel.INFO


def _build_marker_handler(level: LogLevel, stream: TextIO) -> logging.Handler:
    """构造带 marker 的诊断日志 handler。

    :param level: 该 handler 的级别。
    :param stream: 诊断日志输出流。
    :returns: 已 setLevel + setFormatter + 打 marker 的 handler。
    """

    handler = logging.StreamHandler(stream=stream)
    handler.setLevel(int(level))
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
    "LogArgument",
    "LogLevel",
    "bounded_payload_keys",
    "configure",
    "log_verbose",
    "set_level_from_flags",
]
