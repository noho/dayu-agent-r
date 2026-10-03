"""独占一次性 worker 的双 fd 隔离及严格诊断文件传输。

只能在 worker 的第三方执行前进入一次；结构化 scope 结束恢复 logger 配置，
标准 fd 映射保持到进程退出。模块不拥有业务结果、日志选择或目的地语义。
"""
from __future__ import annotations

import json
import logging
import math
import os
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO, ClassVar, Final, Literal, TypeAlias, cast

from dayu.contracts.json_value import JsonValue

_STDOUT_FILE: Final[str] = "stdout.bin"
_STDERR_FILE: Final[str] = "stderr.bin"
_RECORDS_FILE: Final[str] = "records.jsonl"
_SCHEMA_VERSION: Final[int] = 1
_RAW_CHUNK_SIZE: Final[int] = 64 * 1024
_PRIVATE_FILE_MODE: Final[int] = 0o600
_SAFE_ERROR: Final[str] = "进程诊断隔离或传输失败"
_END: Final[dict[str, JsonValue]] = {"schema_version": _SCHEMA_VERSION, "kind": "end"}


@dataclass(frozen=True, slots=True)
class ProcessLogDiagnostic:
    """源 logger 已格式化的诊断，保留原名称、等级及时间。"""
    source_name: str
    source_level: int
    message: str
    created_at: float


@dataclass(frozen=True, slots=True)
class ProcessRawDiagnostic:
    """没有可信源等级的 fd 字节及 channel 内偏移。"""
    channel: Literal["stdout", "stderr"]
    data: bytes
    offset: int


class ProcessCaptureIncidentCode(StrEnum):
    """捕捉过程的封闭故障阶段，不代表业务失败。"""
    RECORD_VALIDATION = "record_validation"
    RECORD_FORMAT = "record_format"
    RECORD_ENCODING = "record_encoding"
    RECORD_WRITE = "record_write"
    RECURSIVE_RECORD = "recursive_record"
    SCOPE_SETUP = "scope_setup"
    SCOPE_FLUSH = "scope_flush"
    LOGGER_TEARDOWN = "logger_teardown"


@dataclass(frozen=True, slots=True)
class ProcessCaptureIncident:
    """仅携带安全阶段代码的捕捉故障。"""
    code: ProcessCaptureIncidentCode


ProcessDiagnostic: TypeAlias = ProcessLogDiagnostic | ProcessRawDiagnostic | ProcessCaptureIncident


class ProcessDiagnosticsFailureReason(StrEnum):
    """隔离与读侧传输错误的封闭原因。"""
    ISOLATION_SETUP = "isolation_setup"
    TRANSPORT_READ = "transport_read"
    TRANSPORT_INVALID = "transport_invalid"
    TRANSPORT_INCOMPLETE = "transport_incomplete"


class ProcessDiagnosticsError(RuntimeError):
    """固定安全文本的诊断边界错误。"""

    def __init__(self, reason: ProcessDiagnosticsFailureReason) -> None:
        """参数：封闭原因；返回：无；异常：不主动抛出。"""
        super().__init__(_SAFE_ERROR)
        self.reason = reason


class _ProjectionState(threading.local):
    """每个线程独立的投影递归深度。"""
    depth: int = 0


class _WriterState(StrEnum):
    """结构化媒体的收口状态。"""
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"


def _project_record(record: logging.LogRecord) -> ProcessLogDiagnostic:
    """参数：writer 已验证字段的源 record；返回：保等级投影；异常：格式化错误原样抛出。"""
    created = float(record.created)
    message = record.getMessage()
    formatter = logging.Formatter()
    if record.exc_info:
        message += "\n" + formatter.formatException(record.exc_info)
    if record.stack_info:
        message += "\n" + formatter.formatStack(record.stack_info)
    return ProcessLogDiagnostic(record.name, record.levelno, message, created)


def _encode(value: dict[str, JsonValue]) -> bytes:
    """参数：闭合 JSON 对象；返回：UTF-8 完整行；异常：编码或 JSON 错误原样抛出。"""
    return (json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _log_value(diagnostic: ProcessLogDiagnostic) -> dict[str, JsonValue]:
    """参数：已验证投影；返回：exact schema；异常：不主动抛出。"""
    return {"schema_version": _SCHEMA_VERSION, "kind": "log",
            "source_name": diagnostic.source_name, "source_level": diagnostic.source_level,
            "message": diagnostic.message, "created_at": diagnostic.created_at}


class _DiagnosticWriter:
    """锁内同步追加，锁外投影；reservation 保证 footer 等待在途记录。"""

    def __init__(self, records_stream: BinaryIO | None) -> None:
        """参数：唯一持有的媒体或不可用；返回：无；异常：同步设施初始化错误原样抛出。"""
        self._stream = records_stream
        self._condition = threading.Condition(threading.Lock())
        self._state = _WriterState.OPEN
        self._active = 0
        self._projection = _ProjectionState()
        self.spool_faulted = records_stream is None

    def _append(self, data: bytes) -> None:
        """参数：完整编码行；返回：无；异常：控制流原样传播，普通写故障令媒体停写。"""
        if self.spool_faulted or self._stream is None:
            return
        try:
            if self._stream.write(data) != len(data):
                raise OSError(_SAFE_ERROR)
            self._stream.flush()
        except Exception:
            # 部分写入后不能追加 footer 冒充完整 spool。
            self.spool_faulted = True

    def note_incident(self, code: ProcessCaptureIncidentCode) -> None:
        """参数：封闭故障阶段；返回：无；异常：仅控制流传播，普通媒体故障包含。"""
        try:
            with self._condition:
                if self._state is not _WriterState.CLOSED:
                    self._append(_encode({"schema_version": _SCHEMA_VERSION,
                                          "kind": "capture_incident", "code": code.value}))
        except Exception:
            self.spool_faulted = True

    def try_capture(self, record: logging.LogRecord) -> bool:
        """参数：源 record；返回：接管/drop 为 True、未 reservation 为 False；异常：控制流原样传播。"""
        reserved = False
        entered = False
        stage = ProcessCaptureIncidentCode.RECORD_VALIDATION
        try:
            if self._projection.depth:
                self.note_incident(ProcessCaptureIncidentCode.RECURSIVE_RECORD)
                return True
            with self._condition:
                if self._state is not _WriterState.OPEN:
                    return False
                self._active += 1
                reserved = True
            self._projection.depth += 1
            entered = True
            # 验证阶段单独归类，投影中 Formatter/getMessage 的普通错误属于 format。
            if (not isinstance(record.name, str) or type(record.levelno) is not int
                    or isinstance(record.created, bool) or not isinstance(record.created, int | float)
                    or not math.isfinite(float(record.created))
                    or (record.stack_info is not None and not isinstance(record.stack_info, str))):
                raise ValueError(_SAFE_ERROR)
            stage = ProcessCaptureIncidentCode.RECORD_FORMAT
            diagnostic = _project_record(record)
            stage = ProcessCaptureIncidentCode.RECORD_ENCODING
            data = _encode(_log_value(diagnostic))
            stage = ProcessCaptureIncidentCode.RECORD_WRITE
            with self._condition:
                # healthy reservation 在 CLOSING 期间仍写；close 等它完成。
                self._append(data)
            return True
        except Exception:
            self.note_incident(stage)
            return True
        finally:
            try:
                if entered:
                    self._projection.depth -= 1
                if reserved:
                    with self._condition:
                        self._active -= 1
                        self._condition.notify_all()
            except Exception:
                self.note_incident(stage)

    def begin_closing(self) -> None:
        """参数：无；返回：无；异常：同步设施控制流原样传播。"""
        with self._condition:
            self._state = _WriterState.CLOSING

    def wait_for_reservations(self) -> None:
        """参数：无；返回：在途投影已收口；异常：同步等待控制流原样传播。"""
        with self._condition:
            while self._active:
                self._condition.wait()

    def close(self) -> None:
        """参数：无；返回：关闭 records；异常：普通错误包含，首个控制流回收后原样传播。"""
        control: BaseException | None = None
        try:
            with self._condition:
                if self._state is not _WriterState.CLOSED:
                    self._append(_encode(_END))
        except Exception:
            self.spool_faulted = True
        except BaseException as exc:
            control = exc
        finally:
            self._state = _WriterState.CLOSED
            if self._stream is not None:
                try:
                    self._stream.close()
                except Exception:
                    pass
                except BaseException as exc:
                    if control is None:
                        control = exc
        if control is not None:
            raise control


class _ExistingLoggerCaptureFilter(logging.Filter):
    """阻断进入既有源 logger 的记录，关闭后允许原 stdlib/raw 路由。"""

    def __init__(self, writer: _DiagnosticWriter) -> None:
        """参数：本 scope writer；返回：无；异常：不主动抛出。"""
        super().__init__()
        self._writer = writer

    def filter(self, record: logging.LogRecord) -> bool:
        """参数：源 record；返回：未接管才允许原路由；异常：控制流传播。"""
        return not self._writer.try_capture(record)


class _CapturingLogger(logging.Logger):
    """标准 manager 晚建 logger 的有限 handle 边界。"""
    writer: ClassVar[_DiagnosticWriter | None] = None

    def handle(self, record: logging.LogRecord) -> None:
        """参数：源 record；返回：无；异常：源 filter 与控制流原样传播。"""
        writer = self.writer
        if writer is None:
            super().handle(record)
        elif not self.disabled and self.filter(record):
            if not writer.try_capture(record):
                self.callHandlers(record)


def _open_private(path: Path) -> BinaryIO:
    """参数：worker 文件路径；返回：0600 独占二进制媒体；异常：文件系统错误传播。"""
    return os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _PRIVATE_FILE_MODE), "wb")


def _flush_standard_streams() -> None:
    """参数：无；返回：flush 双 Python 标准流；异常：首个故障在两流均尝试后传播。"""
    failure: BaseException | None = None
    for stream in (sys.stderr, sys.stdout):
        try:
            stream.flush()
        except BaseException as exc:
            if failure is None or isinstance(failure, Exception) and not isinstance(exc, Exception):
                failure = exc
    if failure is not None:
        raise failure


def _note_cleanup_incident(writer: _DiagnosticWriter, code: ProcessCaptureIncidentCode) -> BaseException | None:
    """参数：媒体 owner 与清理阶段；返回：报告中的控制流或 None；异常：不抛出，供清理保首对象后继续回收。"""
    try:
        writer.note_incident(code)
    except Exception:
        pass
    except BaseException as exc:
        return exc
    return None


def _close_raw_streams(streams: list[BinaryIO], writer: _DiagnosticWriter | None) -> BaseException | None:
    """参数：额外 raw 句柄与已建立媒体；返回：首个控制流或 None；异常：逐项回收，不向中途抛出。"""
    control: BaseException | None = None
    for stream in streams:
        try:
            stream.close()
        except Exception:
            if writer is not None:
                incident_control = _note_cleanup_incident(writer, ProcessCaptureIncidentCode.SCOPE_FLUSH)
                if control is None:
                    control = incident_control
        except BaseException as exc:
            if control is None:
                control = exc
    return control


def _teardown_capture_loggers(installed: list[logging.Logger], capture_filter: _ExistingLoggerCaptureFilter,
                              previous_class: type[logging.Logger] | None, writer: _DiagnosticWriter) -> BaseException | None:
    """参数：本 scope logger/filter/原 class/writer；返回：首个控制流；异常：普通撤销故障包含并继续。"""
    control: BaseException | None = None
    for logger in installed:
        try:
            logger.removeFilter(capture_filter)
        except Exception:
            incident_control = _note_cleanup_incident(writer, ProcessCaptureIncidentCode.LOGGER_TEARDOWN)
            if control is None:
                control = incident_control
        except BaseException as exc:
            if control is None:
                control = exc
    try:
        logging.getLogger().manager.loggerClass = previous_class
    except Exception:
        incident_control = _note_cleanup_incident(writer, ProcessCaptureIncidentCode.LOGGER_TEARDOWN)
        if control is None:
            control = incident_control
    except BaseException as exc:
        if control is None:
            control = exc
    finally:
        _CapturingLogger.writer = None
    return control


@contextmanager
def capture_process_diagnostics(directory: Path) -> Iterator[None]:
    """参数：独占 worker 请求目录；返回：同步 scope；异常：隔离 setup typed error，body/控制流原样传播。

    不恢复 fd1/2；调用者必须是一次性 worker，禁止在 parent、嵌套 scope 或下一请求使用。
    """
    raw_streams: list[BinaryIO] = []
    initial_flush_fault = False
    try:
        try:
            _flush_standard_streams()
        except Exception:
            initial_flush_fault = True
        for fd, filename in ((2, _STDERR_FILE), (1, _STDOUT_FILE)):
            stream = _open_private(directory / filename)
            raw_streams.append(stream)
            os.dup2(stream.fileno(), fd)
    except BaseException as exc:
        close_control = _close_raw_streams(raw_streams, None)
        if not isinstance(exc, Exception):
            raise
        if close_control is not None:
            raise close_control
        raise ProcessDiagnosticsError(ProcessDiagnosticsFailureReason.ISOLATION_SETUP) from exc

    records_stream: BinaryIO | None = None
    records_control: BaseException | None = None
    try:
        records_stream = _open_private(directory / _RECORDS_FILE)
    except Exception:
        pass
    except BaseException as exc:
        records_control = exc
    writer = _DiagnosticWriter(records_stream)
    capture_filter = _ExistingLoggerCaptureFilter(writer)
    installed: list[logging.Logger] = []
    manager = logging.getLogger().manager
    previous_class = manager.loggerClass
    cleanup_control: BaseException | None = None
    scope_error: BaseException | None = None
    try:
        if records_control is not None:
            raise records_control
        try:
            if initial_flush_fault:
                writer.note_incident(ProcessCaptureIncidentCode.SCOPE_FLUSH)
            for logger in (logging.getLogger(), *tuple(manager.loggerDict.values())):
                if isinstance(logger, logging.Logger):
                    logger.addFilter(capture_filter)
                    installed.append(logger)
            _CapturingLogger.writer = writer
            manager.setLoggerClass(_CapturingLogger)
        except Exception:
            writer.note_incident(ProcessCaptureIncidentCode.SCOPE_SETUP)
            cleanup_control = _teardown_capture_loggers(installed, capture_filter, previous_class, writer)
            installed.clear()
            if cleanup_control is not None:
                raise cleanup_control
        yield
    except BaseException as exc:
        # 只记录真正穿过本 scope 的异常，外层 except 的活跃异常不属于本次调用。
        # 覆盖 records-open、logger setup 和 body，清理仍须完成后保首控制流。
        scope_error = exc
        raise
    finally:
        try:
            writer.begin_closing()
        except Exception:
            incident_control = _note_cleanup_incident(writer, ProcessCaptureIncidentCode.SCOPE_FLUSH)
            if cleanup_control is None:
                cleanup_control = incident_control
        except BaseException as exc:
            if cleanup_control is None:
                cleanup_control = exc
        teardown_control = _teardown_capture_loggers(installed, capture_filter, previous_class, writer)
        if cleanup_control is None:
            cleanup_control = teardown_control
        try:
            writer.wait_for_reservations()
        except Exception:
            incident_control = _note_cleanup_incident(writer, ProcessCaptureIncidentCode.SCOPE_FLUSH)
            if cleanup_control is None:
                cleanup_control = incident_control
        except BaseException as exc:
            if cleanup_control is None:
                cleanup_control = exc
        try:
            _flush_standard_streams()
        except Exception:
            incident_control = _note_cleanup_incident(writer, ProcessCaptureIncidentCode.SCOPE_FLUSH)
            if cleanup_control is None:
                cleanup_control = incident_control
        except BaseException as exc:
            if cleanup_control is None:
                cleanup_control = exc
        raw_control = _close_raw_streams(raw_streams, writer)
        if cleanup_control is None:
            cleanup_control = raw_control
        try:
            writer.close()
        except BaseException as exc:
            if cleanup_control is None:
                cleanup_control = exc
        if scope_error is not None and not isinstance(scope_error, Exception):
            raise scope_error
        if cleanup_control is not None:
            raise cleanup_control


def _decode_line(line: bytes) -> ProcessLogDiagnostic | ProcessCaptureIncident | None:
    """参数：完整 JSONL 行；返回：typed record/incident 或 end None；异常：非法 schema 为 typed error。"""
    try:
        value = cast(JsonValue, json.loads(line))
        if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != _SCHEMA_VERSION:
            raise ValueError(_SAFE_ERROR)
        kind = value.get("kind")
        if kind == "end" and value == _END:
            return None
        if kind == "capture_incident" and set(value) == {"schema_version", "kind", "code"}:
            code = value["code"]
            if isinstance(code, str):
                return ProcessCaptureIncident(ProcessCaptureIncidentCode(code))
        if kind == "log" and set(value) == {"schema_version", "kind", "source_name", "source_level", "message", "created_at"}:
            name, level, message, created = value["source_name"], value["source_level"], value["message"], value["created_at"]
            if (isinstance(name, str) and type(level) is int and isinstance(message, str)
                    and not isinstance(created, bool) and isinstance(created, int | float) and math.isfinite(float(created))):
                return ProcessLogDiagnostic(name, level, message, float(created))
        raise ValueError(_SAFE_ERROR)
    except Exception as exc:
        raise ProcessDiagnosticsError(ProcessDiagnosticsFailureReason.TRANSPORT_INVALID) from exc


def _read_records(path: Path) -> Iterator[ProcessLogDiagnostic | ProcessCaptureIncident]:
    """参数：records 文件；返回：严格合法前缀；异常：缺 end/半行 incomplete，错行 invalid，IO read。"""
    try:
        with path.open("rb") as stream:
            for line in stream:
                if not line.endswith(b"\n"):
                    raise ProcessDiagnosticsError(ProcessDiagnosticsFailureReason.TRANSPORT_INCOMPLETE)
                record = _decode_line(line)
                if record is None:
                    if stream.read(1):
                        raise ProcessDiagnosticsError(ProcessDiagnosticsFailureReason.TRANSPORT_INVALID)
                    return
                yield record
        raise ProcessDiagnosticsError(ProcessDiagnosticsFailureReason.TRANSPORT_INCOMPLETE)
    except OSError as exc:
        raise ProcessDiagnosticsError(ProcessDiagnosticsFailureReason.TRANSPORT_READ) from exc


def read_process_diagnostics(directory: Path, *, require_complete: bool) -> Iterator[ProcessDiagnostic]:
    """参数：已 join/close 的目录、完整性读取策略；返回：固定内存迭代器；异常：typed 传输错误/控制流传播。

    True 先完整流式校验再回读；False 先 yield 合法前缀再通知残缺。两者不决定业务成功。
    """
    records_path = directory / _RECORDS_FILE
    if require_complete:
        for _ in _read_records(records_path):
            pass
    yield from _read_records(records_path)
    for channel, filename in (("stdout", _STDOUT_FILE), ("stderr", _STDERR_FILE)):
        try:
            with (directory / filename).open("rb") as stream:
                offset = 0
                while data := stream.read(_RAW_CHUNK_SIZE):
                    yield ProcessRawDiagnostic(cast(Literal["stdout", "stderr"], channel), data, offset)
                    offset += len(data)
        except OSError as exc:
            raise ProcessDiagnosticsError(ProcessDiagnosticsFailureReason.TRANSPORT_READ) from exc
