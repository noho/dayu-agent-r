"""``dayu.runtime.log`` 装配与诊断准入契约测试。

覆盖 canonical 等级映射、普通阈值、精确 stream 准入、
quiet 显式拒绝、logger/handler 前置门槛、root 装配与幂等性。
"""

from __future__ import annotations

import io
import logging
import re
import sys
import traceback
from collections.abc import Iterator
from pathlib import Path
from types import FrameType, TracebackType
from typing import NoReturn

import pytest
import dayu.runtime.log as runtime_log

from dayu.contracts.json_value import JsonValue
from dayu.runtime.log import (
    DiagnosticLogLevel,
    LogLevel,
    bounded_payload_keys,
    configure,
    configure_selected_diagnostics,
    log_verbose,
    safe_exception_trace,
)
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

_NAMESPACE = "dayu"
_MARKER_ATTR = "_dayu_runtime_log_marker"
_MARKER_VALUE = "dayu.runtime.log:diagnostic"
_CANONICAL_LEVEL_CASES: tuple[tuple[DiagnosticLogLevel, LogLevel], ...] = (
    (DiagnosticLogLevel.DEBUG, LogLevel.DEBUG),
    (DiagnosticLogLevel.VERBOSE, LogLevel.VERBOSE),
    (DiagnosticLogLevel.INFO, LogLevel.INFO),
    (DiagnosticLogLevel.WARNING, LogLevel.WARNING),
    (DiagnosticLogLevel.ERROR, LogLevel.ERROR),
    (DiagnosticLogLevel.CRITICAL, LogLevel.CRITICAL),
    (DiagnosticLogLevel.QUIET, LogLevel.QUIET),
)
_ORDINARY_RECORD_LEVELS: tuple[int, ...] = (
    DEBUG_LOG_LEVEL,
    VERBOSE_LOG_LEVEL,
    INFO_LOG_LEVEL,
    WARN_LOG_LEVEL,
    ERROR_LOG_LEVEL,
    CRITICAL_LOG_LEVEL,
)


def test_safe_exception_trace_keeps_verified_frame_and_hides_raw_exception() -> None:
    """安全诊断只保留可验证的包内帧、内建祖先和类型指纹。

    :returns: 无。
    :raises AssertionError: 原始异常、cause、外部绝对路径或受信行号丢失时抛出。
    """

    source_root = Path(runtime_log.__file__).parent.parent
    secret = "https://secret.invalid/?token=contact-canary /Users/private/report.pdf"
    try:
        configure(level=LogLevel.QUIET, debug_stream=True)
    except ValueError as exc:
        exc.args = (secret,)
        exc.__cause__ = RuntimeError(secret)
        trace = safe_exception_trace(exc, source_root=source_root)
    else:
        pytest.fail("expected a Dayu frame")
    assert "exception_type=ValueError custom_type=redacted" in trace
    assert re.search(r"log\.py:[1-9][0-9]*", trace)
    assert "[external]" in trace
    assert "truncated=false" in trace
    for forbidden in (secret, "token=", "https://", "/Users/", str(source_root), "quiet diagnostics"):
        assert forbidden not in trace


def test_safe_exception_trace_fingerprints_custom_types_without_names() -> None:
    """两个动态异常类型只以可区分的固定十六进制指纹出现。

    :returns: 无。
    :raises AssertionError: 指纹长度、区分能力或脱敏契约失效时抛出。
    """

    source_root = Path(runtime_log.__file__).parent.parent
    fingerprints: list[str] = []
    for name in ("SecretAlphaTokenError", "SecretBetaTokenError"):
        exception_class = type(name, (RuntimeError,), {"__module__": "secret.private.module"})
        try:
            raise exception_class("https://private.invalid/?token=contact-canary") from ValueError("/Users/private/cause")
        except RuntimeError as exc:
            trace = safe_exception_trace(exc, source_root=source_root)
        assert "exception_type=RuntimeError" in trace
        assert name not in trace
        assert "secret.private.module" not in trace
        assert "contact-canary" not in trace
        assert "/Users/private" not in trace
        match = re.search(r"custom_type=([0-9a-f]{16})\b", trace)
        assert match is not None
        fingerprints.append(match.group(1))
    assert fingerprints[0] != fingerprints[1]


def test_safe_exception_trace_redacts_external_filename_and_bad_type_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """外部伪造文件名不会进入诊断，非法类型元数据只产生固定遮盖词。

    :param monkeypatch: 注入非法类型元数据。
    :returns: 无。
    :raises AssertionError: 外部路径或自定义类型元数据泄漏时抛出。
    """

    source_root = Path(runtime_log.__file__).parent.parent
    code = compile(
        "raise RuntimeError('https://private.invalid/?token=secret')",
        "/Users/private/token_source.py",
        "exec",
    )
    try:
        exec(code)
    except RuntimeError as exc:
        trace = safe_exception_trace(exc, source_root=source_root)
    else:
        pytest.fail("expected an external traceback frame")
    assert trace.count("[external]") >= 2
    assert "/Users/private" not in trace
    assert "https://" not in trace
    assert "token=" not in trace

    class BadMetadataError(RuntimeError):
        """用于检验非法类型元数据降级。"""

    monkeypatch.setattr(BadMetadataError, "__module__", 42)
    bad_trace = safe_exception_trace(BadMetadataError("secret"), source_root=source_root)
    assert "exception_type=RuntimeError custom_type=redacted" in bad_trace
    assert "BadMetadataError" not in bad_trace


def test_safe_exception_trace_bounds_deep_stack_and_handles_missing_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """深栈只校验并输出末十六帧，无 traceback 使用固定缺失标记。

    :param monkeypatch: 观察受信帧校验调用而不改变校验结果。
    :returns: 无。
    :raises AssertionError: 校验范围、深栈边界或缺失 traceback 投影不符时抛出。
    """

    source_root = Path(runtime_log.__file__).parent.parent
    validated_frames: list[tuple[FrameType, int]] = []
    validate_frame = runtime_log._safe_trace_frame

    def record_validation(frame: FrameType, line_number: int, root: Path) -> str:
        """记录实际校验的帧并使用原校验规则生成诊断。

        :param frame: 待校验的 traceback 帧。
        :param line_number: traceback 记录的行号。
        :param root: 调用方传入的受信包根。
        :returns: 原校验规则生成的安全帧片段。
        :raises Exception: 遵循原校验函数的异常契约。
        """

        validated_frames.append((frame, line_number))
        return validate_frame(frame, line_number, root)

    def raise_deep(depth: int) -> NoReturn:
        """构造有界测试递归栈。

        :param depth: 剩余递归层数。
        :returns: 不返回。
        :raises RuntimeError: 到达底层时抛出。
        """

        if depth == 0:
            raise RuntimeError("token=hidden")
        raise_deep(depth - 1)
        raise AssertionError("unreachable")

    try:
        raise_deep(25)
    except RuntimeError as exc:
        original_frames = list(traceback.walk_tb(exc.__traceback__))
        with monkeypatch.context() as patch:
            patch.setattr(runtime_log, "_safe_trace_frame", record_validation)
            trace = safe_exception_trace(exc, source_root=source_root)
    assert len(original_frames) > 16
    assert validated_frames == original_frames[-16:]
    assert trace.count("[external]") == 16
    assert trace.endswith("truncated=true")
    assert "token=hidden" not in trace
    assert "stack=[unavailable]" in safe_exception_trace(RuntimeError("secret"), source_root=source_root)


def test_safe_exception_trace_internal_failures_return_fixed_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """遍历或哈希故障都只返回同一个固定安全串。

    :param monkeypatch: 注入 helper 内部失败。
    :returns: 无。
    :raises AssertionError: 内部失败抛出或泄漏原始文本时抛出。
    """

    source_root = Path(runtime_log.__file__).parent.parent
    expected = "exception_type=redacted custom_type=redacted stack=[unavailable]"

    def broken_walk(_tb: TracebackType | None) -> Iterator[tuple[FrameType, int]]:
        """模拟 traceback 遍历故障。

        :param _tb: 未使用的 traceback 输入。
        :returns: 不返回。
        :raises RuntimeError: 始终抛出。
        """

        raise RuntimeError("token=walk-secret")

    with monkeypatch.context() as patch:
        patch.setattr(runtime_log.traceback, "walk_tb", broken_walk)
        assert safe_exception_trace(ValueError("/Users/private"), source_root=source_root) == expected

    def broken_hash(_data: bytes) -> NoReturn:
        """模拟指纹哈希故障。

        :param _data: 指纹原始字节。
        :returns: 不返回。
        :raises RuntimeError: 始终抛出。
        """

        raise RuntimeError("token=hash-secret")

    class CustomError(RuntimeError):
        """用于触发自定义类型指纹的异常。"""

    with monkeypatch.context() as patch:
        patch.setattr(runtime_log.hashlib, "sha256", broken_hash)
        assert safe_exception_trace(CustomError("https://private.invalid"), source_root=source_root) == expected


@pytest.fixture(autouse=True)
def _restore_logging_state() -> Iterator[None]:
    """每个 case 跑完后恢复 ``dayu`` 与 root logger 状态。

    :returns: 一个在测试后恢复 logging 状态的迭代器。
    :raises Exception: 不主动抛出异常。
    """

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
    """筛选目标 logger 上的自有 marker handler。

    :param target: 待检查的 stdlib logger。
    :returns: 只包含 Dayu runtime 自有 handler 的列表。
    :raises Exception: 不主动抛出异常。
    """

    return [
        handler
        for handler in target.handlers
        if getattr(handler, _MARKER_ATTR, None) == _MARKER_VALUE
    ]


def test_configure_sets_namespace_level_and_marker_handler() -> None:
    """普通装配应设置 namespace logger 与单个自有 handler。

    :returns: 无返回值。
    :raises AssertionError: logger 级别、传播或 handler 数量不符合契约时抛出。
    """

    configure(level=LogLevel.DEBUG)

    namespace_logger = logging.getLogger(_NAMESPACE)
    assert namespace_logger.level == int(LogLevel.DEBUG)
    assert namespace_logger.propagate is False
    assert len(_marker_handlers(namespace_logger)) == 1


@pytest.mark.parametrize(
    ("debug_stream", "expected_gate"),
    ((False, LogLevel.INFO), (True, LogLevel.STREAM_DEBUG)),
)
def test_logger_and_handler_share_required_gate(
    debug_stream: bool,
    expected_gate: LogLevel,
) -> None:
    """logger 与 handler 应共享能让候选记录到达 filter 的前置门槛。

    :param debug_stream: 是否开启 stream 诊断。
    :param expected_gate: 期望的 logger 与 handler 数值门槛。
    :returns: 无返回值。
    :raises AssertionError: 任一前置门槛不符合契约时抛出。
    """

    configure(level=LogLevel.INFO, debug_stream=debug_stream)

    namespace_logger = logging.getLogger(_NAMESPACE)
    marker = _marker_handlers(namespace_logger)[0]
    assert namespace_logger.level == int(expected_gate)
    assert marker.level == int(expected_gate)


@pytest.mark.parametrize(("selected", "expected"), _CANONICAL_LEVEL_CASES)
def test_configure_selected_diagnostics_maps_all_canonical_levels(
    selected: DiagnosticLogLevel,
    expected: LogLevel,
) -> None:
    """七个 canonical 公开等级应各自映射到唯一普通数值阈值。

    :param selected: 公开 canonical 诊断等级。
    :param expected: 期望的 runtime 普通阈值。
    :returns: 无返回值。
    :raises AssertionError: 映射结果或 logger 级别不正确时抛出。
    """

    resolved = configure_selected_diagnostics(
        level=selected,
        debug_stream=False,
        stream=io.StringIO(),
    )

    assert resolved is expected
    assert logging.getLogger(_NAMESPACE).level == int(expected)


@pytest.mark.parametrize(("selected", "threshold"), _CANONICAL_LEVEL_CASES)
@pytest.mark.parametrize("record_level", _ORDINARY_RECORD_LEVELS)
def test_ordinary_threshold_admission_matrix(
    selected: DiagnosticLogLevel,
    threshold: LogLevel,
    record_level: int,
) -> None:
    """普通日志应只在非 quiet 且不低于选中阈值时输出。

    :param selected: 公开 canonical 诊断等级。
    :param threshold: 该等级的 runtime 普通阈值。
    :param record_level: 候选普通日志记录的数值级别。
    :returns: 无返回值。
    :raises AssertionError: 记录准入结果不符合阈值契约时抛出。
    """

    stream = io.StringIO()
    configure_selected_diagnostics(
        level=selected,
        debug_stream=False,
        stream=stream,
    )

    logging.getLogger("dayu.test.ordinary_matrix").log(
        record_level,
        "ordinary-matrix-record",
    )

    expected = threshold is not LogLevel.QUIET and record_level >= int(threshold)
    assert ("ordinary-matrix-record" in stream.getvalue()) is expected


@pytest.mark.parametrize(
    ("selected", "threshold"),
    _CANONICAL_LEVEL_CASES[:-1],
)
@pytest.mark.parametrize(
    "record_level",
    (STREAM_DEBUG_LOG_LEVEL, *_ORDINARY_RECORD_LEVELS),
)
def test_debug_stream_exact_admission_matrix(
    selected: DiagnosticLogLevel,
    threshold: LogLevel,
    record_level: int,
) -> None:
    """stream 开关应额外放出精确 stream 级别而不改变普通阈值。

    :param selected: 非 quiet 的公开 canonical 诊断等级。
    :param threshold: 该等级的 runtime 普通阈值。
    :param record_level: 候选日志记录的数值级别。
    :returns: 无返回值。
    :raises AssertionError: stream 或普通记录准入结果不正确时抛出。
    """

    stream = io.StringIO()
    configure_selected_diagnostics(
        level=selected,
        debug_stream=True,
        stream=stream,
    )

    logging.getLogger("dayu.test.stream_matrix").log(
        record_level,
        "stream-matrix-record",
    )

    expected = (
        record_level == STREAM_DEBUG_LOG_LEVEL
        or record_level >= int(threshold)
    )
    assert ("stream-matrix-record" in stream.getvalue()) is expected


def test_info_with_debug_stream_does_not_emit_debug_or_verbose() -> None:
    """INFO 与 stream 组合不应泄漏普通 DEBUG 或 VERBOSE 记录。

    :returns: 无返回值。
    :raises AssertionError: 低于 INFO 的普通记录被输出时抛出。
    """

    stream = io.StringIO()
    configure(
        level=LogLevel.INFO,
        debug_stream=True,
        stream=stream,
    )
    logger = logging.getLogger("dayu.test.info_stream")

    logger.debug("ordinary-debug-hidden")
    logger.log(VERBOSE_LOG_LEVEL, "ordinary-verbose-hidden")
    logger.log(STREAM_DEBUG_LOG_LEVEL, "stream-debug-visible")

    output = stream.getvalue()
    assert "ordinary-debug-hidden" not in output
    assert "ordinary-verbose-hidden" not in output
    assert "stream-debug-visible" in output


def test_quiet_rejects_even_critical_records() -> None:
    """quiet 应显式拒绝 CRITICAL，而非依赖某个偶然高阈值。

    :returns: 无返回值。
    :raises AssertionError: quiet 仍输出 CRITICAL 记录时抛出。
    """

    stream = io.StringIO()
    configure(level=LogLevel.QUIET, stream=stream)
    marker = _marker_handlers(logging.getLogger(_NAMESPACE))[0]
    critical_record = logging.LogRecord(
        name="dayu.test.quiet",
        level=CRITICAL_LOG_LEVEL,
        pathname=__file__,
        lineno=0,
        msg="critical-hidden",
        args=(),
        exc_info=None,
    )

    logging.getLogger("dayu.test.quiet").critical("critical-hidden")

    admission_filter = marker.filters[0]
    assert isinstance(admission_filter, logging.Filter)
    assert admission_filter.filter(critical_record) is False
    assert "critical-hidden" not in stream.getvalue()


def test_critical_emits_only_critical_ordinary_records() -> None:
    """CRITICAL 阈值应拒绝 ERROR 并放出 CRITICAL。

    :returns: 无返回值。
    :raises AssertionError: CRITICAL 阈值的普通准入不正确时抛出。
    """

    stream = io.StringIO()
    configure(level=LogLevel.CRITICAL, stream=stream)
    logger = logging.getLogger("dayu.test.critical")

    logger.error("error-hidden")
    logger.critical("critical-visible")

    output = stream.getvalue()
    assert "error-hidden" not in output
    assert "critical-visible" in output


def test_quiet_with_debug_stream_fails_closed() -> None:
    """runtime 装配应拒绝 quiet 与 stream 诊断的自相矛盾组合。

    :returns: 无返回值。
    :raises AssertionError: 自相矛盾组合未抛出 ``ValueError`` 时抛出。
    """

    with pytest.raises(ValueError, match="quiet diagnostics"):
        configure_selected_diagnostics(
            level=DiagnosticLogLevel.QUIET,
            debug_stream=True,
            stream=io.StringIO(),
        )


def test_configure_root_uses_same_admission_rule() -> None:
    """root handler 应与 namespace handler 共用同一 INFO+stream 准入语义。

    :returns: 无返回值。
    :raises AssertionError: root 门槛、handler 或准入结果不一致时抛出。
    """

    stream = io.StringIO()
    configure(
        level=LogLevel.INFO,
        debug_stream=True,
        configure_root=True,
        stream=stream,
    )
    root_logger = logging.getLogger()
    root_markers = _marker_handlers(root_logger)
    logger = logging.getLogger("external.runtime_log_case")

    logger.debug("root-debug-hidden")
    logger.log(STREAM_DEBUG_LOG_LEVEL, "root-stream-visible")
    logger.info("root-info-visible")

    output = stream.getvalue()
    assert root_logger.level == STREAM_DEBUG_LOG_LEVEL
    assert len(root_markers) == 1
    assert root_markers[0].level == STREAM_DEBUG_LOG_LEVEL
    assert "root-debug-hidden" not in output
    assert "root-stream-visible" in output
    assert "root-info-visible" in output


def test_configure_is_idempotent_across_stream_modes() -> None:
    """重复装配不应堆叠 handler，且应只保留最后一次的准入语义。

    :returns: 无返回值。
    :raises AssertionError: handler 堆叠或旧 stream 准入仍生效时抛出。
    """

    first_stream = io.StringIO()
    final_stream = io.StringIO()
    configure(level=LogLevel.INFO, debug_stream=True, stream=first_stream)
    configure(level=LogLevel.WARNING, debug_stream=False, stream=final_stream)
    logger = logging.getLogger("dayu.test.idempotence")

    logger.log(STREAM_DEBUG_LOG_LEVEL, "stream-hidden")
    logger.info("info-hidden")
    logger.warning("warning-visible")

    namespace_logger = logging.getLogger(_NAMESPACE)
    assert len(_marker_handlers(namespace_logger)) == 1
    assert namespace_logger.level == WARN_LOG_LEVEL
    assert first_stream.getvalue() == ""
    assert "stream-hidden" not in final_stream.getvalue()
    assert "info-hidden" not in final_stream.getvalue()
    assert "warning-visible" in final_stream.getvalue()


def test_configure_does_not_touch_root_by_default() -> None:
    """默认装配不应修改 root logger 或擦除其原有 handler。

    :returns: 无返回值。
    :raises AssertionError: root logger 被默认装配修改时抛出。
    """

    root_logger = logging.getLogger()
    pre_handlers = list(root_logger.handlers)

    configure(level=LogLevel.INFO)

    assert _marker_handlers(root_logger) == []
    assert all(handler in root_logger.handlers for handler in pre_handlers)


def test_third_party_overrides_set_level_only() -> None:
    """第三方 override 应只设置 WARNING 级别，不安装 Dayu handler。

    :returns: 无返回值。
    :raises AssertionError: 第三方 logger 级别或 handler 不符合契约时抛出。
    """

    configure(
        level=LogLevel.INFO,
        third_party_overrides={"httpx": LogLevel.WARNING},
    )

    httpx_logger = logging.getLogger("httpx")
    assert httpx_logger.level == WARN_LOG_LEVEL
    assert _marker_handlers(httpx_logger) == []


def test_configure_default_suppresses_third_party_at_warning() -> None:
    """默认第三方抑制应继续使用 stdlib WARNING 数值。

    :returns: 无返回值。
    :raises AssertionError: 任一默认第三方 logger 未被设为 WARNING 时抛出。
    """

    for name in ("aiohttp", "asyncio", "urllib3"):
        logging.getLogger(name).setLevel(logging.DEBUG)

    configure(level=LogLevel.DEBUG)

    for name in ("aiohttp", "asyncio", "urllib3"):
        assert logging.getLogger(name).level == WARN_LOG_LEVEL


def test_configure_third_party_override_beats_default() -> None:
    """显式第三方 override 应覆盖默认 WARNING 抑制。

    :returns: 无返回值。
    :raises AssertionError: 显式 override 没有最终生效时抛出。
    """

    configure(
        level=LogLevel.DEBUG,
        third_party_overrides={"aiohttp": LogLevel.DEBUG},
    )

    assert logging.getLogger("aiohttp").level == logging.DEBUG


def test_configure_suppress_disabled_keeps_third_party_level() -> None:
    """禁用默认抑制时不应改变第三方 logger 级别。

    :returns: 无返回值。
    :raises AssertionError: 第三方 logger 级别被意外修改时抛出。
    """

    logging.getLogger("aiohttp").setLevel(logging.DEBUG)

    configure(level=LogLevel.DEBUG, suppress_default_third_party=False)

    assert logging.getLogger("aiohttp").level == logging.DEBUG


def test_log_level_enum_uses_runtime_level_constants() -> None:
    """``LogLevel`` 应统一引用 runtime 日志级别常量。

    :returns: 无返回值。
    :raises AssertionError: 任一枚举值与公共常量不一致时抛出。
    """

    assert int(LogLevel.STREAM_DEBUG) == STREAM_DEBUG_LOG_LEVEL
    assert int(LogLevel.DEBUG) == DEBUG_LOG_LEVEL
    assert int(LogLevel.VERBOSE) == VERBOSE_LOG_LEVEL
    assert int(LogLevel.INFO) == INFO_LOG_LEVEL
    assert int(LogLevel.WARNING) == WARN_LOG_LEVEL
    assert int(LogLevel.ERROR) == ERROR_LOG_LEVEL
    assert int(LogLevel.CRITICAL) == CRITICAL_LOG_LEVEL
    assert int(LogLevel.QUIET) == QUIET_LOG_LEVEL
    assert "WARN" not in LogLevel.__members__


def test_custom_log_levels_are_registered_with_stdlib() -> None:
    """runtime 装配模块应注册 VERBOSE 与 STREAM_DEBUG 稳定名称。

    :returns: 无返回值。
    :raises AssertionError: 任一自定义级别名称未注册时抛出。
    """

    assert logging.getLevelName(VERBOSE_LOG_LEVEL) == "VERBOSE"
    assert logging.getLevelName(STREAM_DEBUG_LOG_LEVEL) == "STREAM_DEBUG"
    assert LogLevel.STREAM_DEBUG < LogLevel.DEBUG < LogLevel.VERBOSE < LogLevel.INFO


def test_log_verbose_uses_call_site_logger() -> None:
    """层中立 VERBOSE helper 应保留调用点 logger 名称。

    :returns: 无返回值。
    :raises AssertionError: 输出消息或 logger 名称不正确时抛出。
    """

    stream = io.StringIO()
    configure(level=LogLevel.VERBOSE, stream=stream)

    log_verbose(
        logging.getLogger("dayu.runtime_log_helper.case"),
        "helper-message=%s",
        "ok",
    )

    output = stream.getvalue()
    assert "helper-message=ok" in output
    assert "dayu.runtime_log_helper.case" in output


def test_bounded_payload_keys_exposes_only_sorted_keys() -> None:
    """payload key helper 应只返回有界排序 key，不暴露 value。

    :returns: 无返回值。
    :raises AssertionError: helper 暴露 value、未排序或未限制数量时抛出。
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


def test_logger_emits_to_stderr_by_default(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """默认诊断流应使用当前 stderr 与统一前缀。

    :param capsys: pytest 标准流捕获夹具。
    :returns: 无返回值。
    :raises AssertionError: 日志流向或格式不符合契约时抛出。
    """

    configure(level=LogLevel.INFO)
    logging.getLogger("dayu.test.subsystem").info("hello-runtime-log")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert re.search(
        r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] "
        r"\[INFO\] \[dayu\.test\.subsystem\] hello-runtime-log$",
        captured.err.strip(),
    )


def test_configure_stream_override_keeps_diagnostics_redirectable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """显式 stream 应让诊断日志可重定向。

    :param capsys: pytest 标准流捕获夹具。
    :returns: 无返回值。
    :raises AssertionError: 日志没有写入指定 stream 时抛出。
    """

    configure(level=LogLevel.INFO, stream=sys.stdout)
    logging.getLogger("dayu.test.override").info("override-runtime-log")

    captured = capsys.readouterr()
    assert "override-runtime-log" in captured.out
    assert captured.err == ""


def test_configure_disables_propagate_so_caplog_default_misses(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """关闭 namespace 传播后，绑定 root 的默认 caplog 不应捕获 Dayu 日志。

    :param caplog: pytest 日志捕获夹具。
    :returns: 无返回值。
    :raises AssertionError: 默认 caplog 捕获到已禁止传播的记录时抛出。
    """

    configure(level=LogLevel.DEBUG)

    with caplog.at_level(logging.DEBUG):
        logging.getLogger("dayu.test.captured").info("not-captured-by-default")

    assert "not-captured-by-default" not in [
        record.getMessage() for record in caplog.records
    ]
    assert logging.getLogger(_NAMESPACE).propagate is False


def test_caplog_can_attach_to_dayu_logger_explicitly(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """显式把 caplog handler 挂到 Dayu namespace 后应可捕获日志。

    :param caplog: pytest 日志捕获夹具。
    :returns: 无返回值。
    :raises AssertionError: 显式挂载后仍未捕获日志时抛出。
    """

    configure(level=LogLevel.DEBUG)
    namespace_logger = logging.getLogger(_NAMESPACE)
    namespace_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.DEBUG, logger=_NAMESPACE):
            logging.getLogger("dayu.test.attached").info("captured-message")
    finally:
        namespace_logger.removeHandler(caplog.handler)

    assert "captured-message" in [record.getMessage() for record in caplog.records]
