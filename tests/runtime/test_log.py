"""``dayu.runtime.log`` 装配测试。

覆盖 :func:`configure` 的级别设置、marker handler 幂等、propagate 控制、
``configure_root`` 行为，以及 :func:`set_level_from_flags` 的解析优先级。
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Iterator

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.runtime.log import (
    LogLevel,
    bounded_payload_keys,
    configure,
    log_verbose,
    set_level_from_flags,
)
from dayu.runtime.log_levels import (
    CRITICAL_LOG_LEVEL,
    DEBUG_LOG_LEVEL,
    ERROR_LOG_LEVEL,
    INFO_LOG_LEVEL,
    VERBOSE_LOG_LEVEL,
    WARN_LOG_LEVEL,
)

_NAMESPACE = "dayu"
_MARKER_ATTR = "_dayu_runtime_log_marker"
_MARKER_VALUE = "dayu.runtime.log:diagnostic"


@pytest.fixture(autouse=True)
def _restore_logging_state() -> Iterator[None]:
    """每个 case 跑完后恢复 ``dayu`` / root logger 的状态，避免互相污染。"""

    namespace_logger = logging.getLogger(_NAMESPACE)
    saved_ns_handlers = list(namespace_logger.handlers)
    saved_ns_level = namespace_logger.level
    saved_ns_propagate = namespace_logger.propagate

    root_logger = logging.getLogger()
    saved_root_handlers = list(root_logger.handlers)
    saved_root_level = root_logger.level

    try:
        yield
    finally:
        namespace_logger.handlers = saved_ns_handlers
        namespace_logger.setLevel(saved_ns_level)
        namespace_logger.propagate = saved_ns_propagate
        root_logger.handlers = saved_root_handlers
        root_logger.setLevel(saved_root_level)


def _marker_handlers(target: logging.Logger) -> list[logging.Handler]:
    """筛选目标 logger 上的自有 marker handler。"""

    return [
        h for h in target.handlers
        if getattr(h, _MARKER_ATTR, None) == _MARKER_VALUE
    ]


def test_configure_sets_namespace_level_and_marker_handler() -> None:
    """configure 后 dayu logger 应有期望级别 + 一个 marker handler。"""

    configure(level=LogLevel.DEBUG)

    namespace_logger = logging.getLogger(_NAMESPACE)
    assert namespace_logger.level == int(LogLevel.DEBUG)
    assert namespace_logger.propagate is False
    markers = _marker_handlers(namespace_logger)
    assert len(markers) == 1


def test_configure_is_idempotent() -> None:
    """重复 configure 不应堆叠 marker handler。"""

    configure(level=LogLevel.INFO)
    configure(level=LogLevel.WARN)

    namespace_logger = logging.getLogger(_NAMESPACE)
    markers = _marker_handlers(namespace_logger)
    assert len(markers) == 1
    assert namespace_logger.level == int(LogLevel.WARN)


def test_configure_does_not_touch_root_by_default() -> None:
    """默认不配置 root logger。"""

    root_logger = logging.getLogger()
    pre_handlers = list(root_logger.handlers)
    configure(level=LogLevel.INFO)
    assert _marker_handlers(root_logger) == []
    # 不应擦掉 root 原有 handler。
    assert all(h in root_logger.handlers for h in pre_handlers)


def test_configure_root_true_installs_marker_on_root() -> None:
    """configure_root=True 才安装 root marker handler。"""

    configure(level=LogLevel.INFO, configure_root=True)
    root_logger = logging.getLogger()
    markers = _marker_handlers(root_logger)
    assert len(markers) == 1
    assert root_logger.level == int(LogLevel.INFO)


def test_third_party_overrides_set_level_only() -> None:
    """third_party_overrides 只设置 level，不安装 handler。"""

    configure(
        level=LogLevel.INFO,
        third_party_overrides={"httpx": LogLevel.WARN},
    )
    httpx_logger = logging.getLogger("httpx")
    assert httpx_logger.level == int(LogLevel.WARN)
    assert _marker_handlers(httpx_logger) == []


def test_set_level_from_flags_priority_log_level_str() -> None:
    """显式 log_level 字符串优先级最高。"""

    resolved = set_level_from_flags(
        log_level="warn",
        debug=True,
        verbose=True,
        info=True,
        quiet=True,
    )
    assert resolved is LogLevel.WARN


def test_set_level_from_flags_quiet_beats_debug() -> None:
    """quiet 优先于 debug / verbose / info。"""

    resolved = set_level_from_flags(
        log_level=None,
        debug=True,
        verbose=True,
        info=True,
        quiet=True,
    )
    assert resolved is LogLevel.ERROR


def test_set_level_from_flags_debug_beats_verbose_info() -> None:
    """debug 优先于 verbose / info。"""

    resolved = set_level_from_flags(
        log_level=None,
        debug=True,
        verbose=True,
        info=True,
        quiet=False,
    )
    assert resolved is LogLevel.DEBUG


def test_set_level_from_flags_verbose_maps_to_verbose() -> None:
    """verbose 映射到 VERBOSE=15（迁移自 OLD ``VERBOSE``）。"""

    resolved = set_level_from_flags(
        log_level=None,
        debug=False,
        verbose=True,
        info=False,
        quiet=False,
    )
    assert resolved is LogLevel.VERBOSE
    assert int(resolved) == VERBOSE_LOG_LEVEL


def test_log_level_verbose_registered_with_stdlib() -> None:
    """``logging.getLevelName(15)`` 必须返回 ``VERBOSE``。"""

    assert logging.getLevelName(VERBOSE_LOG_LEVEL) == "VERBOSE"
    assert int(LogLevel.VERBOSE) == VERBOSE_LOG_LEVEL
    assert LogLevel.DEBUG < LogLevel.VERBOSE < LogLevel.INFO


def test_log_level_enum_uses_runtime_level_constants() -> None:
    """``LogLevel`` 枚举必须统一引用 runtime 日志级别常量。

    :returns: 无返回值。
    :raises AssertionError: ``LogLevel`` 与公共常量真源不一致时抛出。
    """

    assert int(LogLevel.DEBUG) == DEBUG_LOG_LEVEL
    assert int(LogLevel.VERBOSE) == VERBOSE_LOG_LEVEL
    assert int(LogLevel.INFO) == INFO_LOG_LEVEL
    assert int(LogLevel.WARN) == WARN_LOG_LEVEL
    assert int(LogLevel.ERROR) == ERROR_LOG_LEVEL
    assert int(LogLevel.CRITICAL) == CRITICAL_LOG_LEVEL


def test_set_level_from_flags_log_level_string_verbose_legal() -> None:
    """``log_level='verbose'`` 字符串解析合法。"""

    resolved = set_level_from_flags(
        log_level="verbose",
        debug=False,
        verbose=False,
        info=False,
        quiet=False,
    )
    assert resolved is LogLevel.VERBOSE


def test_set_level_from_flags_log_level_string_critical_legal() -> None:
    """``log_level='critical'`` 字符串解析为 stdlib CRITICAL 级别。"""

    resolved = set_level_from_flags(
        log_level="critical",
        debug=True,
        verbose=True,
        info=True,
        quiet=True,
    )
    assert resolved is LogLevel.CRITICAL
    assert int(resolved) == CRITICAL_LOG_LEVEL


def test_log_level_critical_matches_stdlib() -> None:
    """Dayu CRITICAL 级别必须沿用 stdlib logging.CRITICAL 语义。"""

    assert int(LogLevel.CRITICAL) == CRITICAL_LOG_LEVEL
    assert CRITICAL_LOG_LEVEL == logging.CRITICAL
    assert LogLevel.ERROR < LogLevel.CRITICAL


def test_configure_default_suppresses_third_party() -> None:
    """``configure()`` 默认把 aiohttp / asyncio / urllib3 调到 WARNING。"""

    # 先把目标 logger 调到 DEBUG，验证 configure 后被压回 WARNING。
    for name in ("aiohttp", "asyncio", "urllib3"):
        logging.getLogger(name).setLevel(logging.DEBUG)
    configure(level=LogLevel.DEBUG)
    for name in ("aiohttp", "asyncio", "urllib3"):
        assert (
            logging.getLogger(name).level == WARN_LOG_LEVEL
        ), f"third-party {name} should be suppressed to WARNING"


def test_configure_third_party_override_beats_default() -> None:
    """``third_party_overrides`` 必须覆盖默认抑制。"""

    configure(
        level=LogLevel.DEBUG,
        third_party_overrides={"aiohttp": LogLevel.DEBUG},
    )
    assert logging.getLogger("aiohttp").level == logging.DEBUG


def test_configure_suppress_disabled_keeps_third_party_level() -> None:
    """``suppress_default_third_party=False`` 时不动第三方 level。"""

    logging.getLogger("aiohttp").setLevel(logging.DEBUG)
    configure(level=LogLevel.DEBUG, suppress_default_third_party=False)
    assert logging.getLogger("aiohttp").level == logging.DEBUG


def test_set_level_from_flags_info_default() -> None:
    """全部 flag 关闭时默认 INFO。"""

    resolved = set_level_from_flags(
        log_level=None,
        debug=False,
        verbose=False,
        info=False,
        quiet=False,
    )
    assert resolved is LogLevel.INFO


def test_log_verbose_uses_call_site_logger(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """层中立 VERBOSE helper 必须保留调用点 logger 名称。

    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 输出 logger 名称或消息不符合预期时抛出。
    """

    configure(level=LogLevel.VERBOSE)
    logger = logging.getLogger("dayu.runtime_log_helper.case")

    log_verbose(logger, "helper-message=%s", "ok")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "helper-message=ok" in captured.err
    assert "dayu.runtime_log_helper.case" in captured.err


def test_bounded_payload_keys_exposes_only_sorted_keys() -> None:
    """payload key helper 只返回有界 key，不暴露 payload value。

    :returns: ``None``。
    :raises AssertionError: helper 暴露 value、未排序或未限制 key 数量时抛出。
    """

    payload: dict[str, JsonValue] = {
        "z": "secret-value",
        "a": "first",
        "m": 1,
        "b": True,
        "c": None,
        "d": "value-d",
        "e": "value-e",
        "f": "value-f",
        "g": "value-g",
    }

    keys = bounded_payload_keys(payload)

    assert keys == ("a", "b", "c", "d", "e", "f", "g", "m")
    assert "secret-value" not in keys


def test_set_level_from_flags_invalid_log_level_raises() -> None:
    """非法 log_level 字符串抛 ValueError。"""

    with pytest.raises(ValueError, match="unknown log_level"):
        set_level_from_flags(
            log_level="trace",
            debug=False,
            verbose=False,
            info=False,
            quiet=False,
        )


def test_logger_emits_to_stderr_by_default(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """configure 后 dayu.* logger 应按统一 prefix 写到 stderr。"""

    configure(level=LogLevel.INFO)
    logging.getLogger("dayu.test.subsystem").info("hello-runtime-log")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "hello-runtime-log" in captured.err
    assert "dayu.test.subsystem" in captured.err
    assert re.search(
        r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] "
        r"\[INFO\] \[dayu\.test\.subsystem\] hello-runtime-log$",
        captured.err.strip(),
    )


def test_configure_stream_override_keeps_diagnostics_redirectable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """调用方显式传入 stream 时，诊断日志应写入该流。

    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 日志没有写入指定流时抛出。
    """

    configure(level=LogLevel.INFO, stream=sys.stdout)
    logging.getLogger("dayu.test.override").info("override-runtime-log")

    captured = capsys.readouterr()
    assert "override-runtime-log" in captured.out
    assert captured.err == ""


def test_configure_disables_propagate_so_caplog_default_misses(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """configure 后 propagate=False，caplog 默认（绑 root）不再抓到 dayu.* 日志。

    这是有意行为：避免污染 root，调用方需要显式
    ``caplog.set_level(level, logger="dayu")`` 并把 caplog handler 挂到
    dayu logger 才能抓。这里只断言默认 caplog 不抓的契约。
    """

    configure(level=LogLevel.DEBUG)

    with caplog.at_level(logging.DEBUG):
        logging.getLogger("dayu.test.captured").info("not-captured-by-default")

    messages = [r.getMessage() for r in caplog.records]
    assert "not-captured-by-default" not in messages
    assert logging.getLogger("dayu").propagate is False


def test_caplog_can_attach_to_dayu_logger_explicitly(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """显式把 caplog.handler 挂到 dayu logger 后即可抓到。"""

    configure(level=LogLevel.DEBUG)
    namespace_logger = logging.getLogger("dayu")
    namespace_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.DEBUG, logger="dayu"):
            logging.getLogger("dayu.test.attached").info("captured-message")
    finally:
        namespace_logger.removeHandler(caplog.handler)

    messages = [r.getMessage() for r in caplog.records]
    assert "captured-message" in messages
