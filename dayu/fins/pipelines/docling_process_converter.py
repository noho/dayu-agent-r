"""Fins 共享 Docling 子进程转换边界。

本模块拥有单次 Docling 转换的闭合配置、结果、IPC descriptor、错误映射、
轮询与临时目录策略。通用进程启动、进程组信号和资源回收继续由
``dayu.runtime.interruptible_process`` 唯一负责。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import shutil
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final, Literal, Protocol, cast

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.documents.docling_runtime import (
    DoclingRuntimeInitializationError,
    convert_pdf_bytes_with_docling,
)
from dayu.runtime.interruptible_process import (
    InterruptibleProcessCompleted,
    InterruptibleProcessFailed,
    InterruptibleProcessHandle,
    InterruptibleProcessStillRunning,
    ProcessInterruptResult,
    ProcessWaitResult,
)

_DOCLING_PROCESS_POLL_SECONDS: Final[float] = 0.05
_DOCLING_TERMINATE_GRACE_SECONDS: Final[float] = 2.0
_DOCLING_KILL_GRACE_SECONDS: Final[float] = 1.0
_DOCLING_TEMP_PREFIX: Final[str] = "dayu-docling-"
_DOCLING_INPUT_FILE_NAME: Final[str] = "input.bin"
_DOCLING_OUTPUT_FILE_NAME: Final[str] = "output.json"
_DESCRIPTOR_SCHEMA_VERSION: Final[int] = 1
_SCHEMA_VERSION_KEY: Final[str] = "schema_version"
_STATUS_KEY: Final[str] = "status"
_STATUS_SUCCESS: Final[str] = "success"
_STATUS_FAILURE: Final[str] = "failure"
_SIZE_KEY: Final[str] = "size"
_SHA256_KEY: Final[str] = "sha256"
_FAILURE_KIND_KEY: Final[str] = "failure_kind"
_MESSAGE_KEY: Final[str] = "message"
_SHA256_HEX_LENGTH: Final[int] = 64
_LOWERCASE_HEX_DIGITS: Final[frozenset[str]] = frozenset("0123456789abcdef")
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DoclingConversionConfig:
    """Docling 转换的闭合配置。

    :param do_ocr: 是否启用 OCR。
    :param do_table_structure: 是否启用表格结构识别。
    :param table_mode: 表格识别模式，本契约只允许 ``accurate``。
    :param do_cell_matching: 是否启用表格单元格匹配。
    """

    do_ocr: bool
    do_table_structure: bool
    table_mode: Literal["accurate"]
    do_cell_matching: bool

    def __post_init__(self) -> None:
        """校验配置字段均属于闭合集合。

        :returns: ``None``。
        :raises ValueError: 布尔字段或表格模式不符合闭合契约时抛出。
        """

        boolean_values = (
            self.do_ocr,
            self.do_table_structure,
            self.do_cell_matching,
        )
        if not all(isinstance(value, bool) for value in boolean_values):
            raise ValueError("Docling conversion boolean config is invalid")
        if self.table_mode != "accurate":
            raise ValueError("Docling conversion table_mode must be accurate")


DEFAULT_FINS_DOCLING_CONVERSION_CONFIG: Final[DoclingConversionConfig] = DoclingConversionConfig(
    do_ocr=True,
    do_table_structure=True,
    table_mode="accurate",
    do_cell_matching=True,
)


@dataclass(frozen=True, slots=True)
class DoclingConversionResult:
    """完成回收与完整性校验后的 Docling JSON 结果。

    :param json_bytes: UTF-8 JSON 字节。
    :param size: 字节长度。
    :param sha256: 字节内容的 lowercase SHA-256。
    """

    json_bytes: bytes
    size: int
    sha256: str

    def __post_init__(self) -> None:
        """校验成功结果只承诺一份同源事实。

        :returns: ``None``。
        :raises ValueError: size 或 SHA-256 与 ``json_bytes`` 不一致时抛出。
        """

        if isinstance(self.size, bool) or self.size != len(self.json_bytes):
            raise ValueError("Docling conversion result size is invalid")
        if not _is_lowercase_sha256(self.sha256):
            raise ValueError("Docling conversion result sha256 is invalid")
        if hashlib.sha256(self.json_bytes).hexdigest() != self.sha256:
            raise ValueError("Docling conversion result sha256 does not match bytes")


class DoclingConverter(Protocol):
    """Fins Docling 转换器公共协议。"""

    async def convert_to_json_bytes(
        self,
        input_bytes: bytes,
        stream_name: str,
        *,
        config: DoclingConversionConfig,
        cancellation: CancellationToken | None,
    ) -> DoclingConversionResult:
        """把输入字节转换为完成校验的 Docling JSON。

        :param input_bytes: 不可变原始文档字节。
        :param stream_name: Docling 可读输入名。
        :param config: 闭合转换配置。
        :param cancellation: 公共取消观察 token；``None`` 表示无取消源。
        :returns: 完成进程与临时资源收口后的 JSON 结果。
        :raises ValueError: 输入、名称或配置非法时抛出。
        :raises DoclingConversionCancelledError: 请求取消且 cleanup 完成时抛出。
        :raises DoclingConversionError: 子进程、IPC 或 cleanup 失败时抛出。
        :raises asyncio.CancelledError: 外层 task 取消且 cleanup 完成时透传。
        """

        ...


class DoclingConversionFailureKind(Enum):
    """Docling 转换的闭合失败种类。"""

    CONVERTER_CONSTRUCTION = "converter_construction"
    CONVERTER_EXECUTION = "converter_execution"
    RESULT_SERIALIZATION = "result_serialization"
    IPC_PROTOCOL = "ipc_protocol"
    CHILD_CRASH = "child_crash"
    CLEANUP = "cleanup"


_SAFE_FAILURE_MESSAGES: Final[dict[DoclingConversionFailureKind, str]] = {
    DoclingConversionFailureKind.CONVERTER_CONSTRUCTION: ("Docling converter construction failed"),
    DoclingConversionFailureKind.CONVERTER_EXECUTION: ("Docling conversion execution failed"),
    DoclingConversionFailureKind.RESULT_SERIALIZATION: ("Docling conversion result serialization failed"),
    DoclingConversionFailureKind.IPC_PROTOCOL: ("Docling conversion IPC protocol failed"),
    DoclingConversionFailureKind.CHILD_CRASH: "Docling conversion child crashed",
    DoclingConversionFailureKind.CLEANUP: "Docling conversion cleanup failed",
}
_CANCELLED_MESSAGE: Final[str] = "Docling conversion cancelled"


class DoclingConversionError(RuntimeError):
    """Docling 转换的唯一公开非取消异常。"""

    def __init__(
        self,
        kind: DoclingConversionFailureKind,
        safe_message: str,
        exit_code: int | None,
    ) -> None:
        """初始化闭合转换异常。

        :param kind: 失败种类。
        :param safe_message: 有界安全文本。
        :param exit_code: 子进程退出码；不可用时为 ``None``。
        :returns: ``None``。
        :raises ValueError: 文本不是该 kind 的固定安全文本时抛出。
        """

        if safe_message != _SAFE_FAILURE_MESSAGES[kind]:
            raise ValueError("Docling conversion safe message is invalid")
        super().__init__(safe_message)
        self.kind = kind
        self.safe_message = safe_message
        self.exit_code = exit_code


class DoclingConversionCancelledError(RuntimeError):
    """请求取消且子进程与临时资源已完整收口。"""

    def __init__(self) -> None:
        """初始化已安全收口的取消异常。

        :returns: ``None``。
        :raises Exception: 本构造函数不抛出异常。
        """

        super().__init__(_CANCELLED_MESSAGE)


@dataclass(frozen=True, slots=True)
class _DoclingProcessTarget:
    """可 pickle 的单次 Docling conversion 子进程目标。

    :param input_path: 父进程独占临时输入文件。
    :param output_path: 父进程独占临时输出文件。
    :param stream_name: Docling 业务可读输入名。
    :param config: 闭合转换配置。
    """

    input_path: str
    output_path: str
    stream_name: str
    config: DoclingConversionConfig

    def __call__(self) -> JsonValue:
        """执行 Docling 并返回闭合小型 descriptor。

        :returns: exact success 或 failure descriptor。
        :raises Exception: descriptor queue 传输等目标外故障可由 runtime 捕获。
        """

        try:
            input_bytes = Path(self.input_path).read_bytes()
            conversion = convert_pdf_bytes_with_docling(
                input_bytes,
                stream_name=self.stream_name,
                do_ocr=self.config.do_ocr,
                do_table_structure=self.config.do_table_structure,
                table_mode=self.config.table_mode,
                do_cell_matching=self.config.do_cell_matching,
            )
        except DoclingRuntimeInitializationError:
            return _failure_descriptor(DoclingConversionFailureKind.CONVERTER_CONSTRUCTION)
        except Exception:
            return _failure_descriptor(DoclingConversionFailureKind.CONVERTER_EXECUTION)

        try:
            exported = cast(JsonValue, conversion.document.export_to_dict())
            if not isinstance(exported, Mapping) or not _is_closed_json_value(exported):
                raise ValueError("Docling export is not a closed JSON mapping")
            output_bytes = json.dumps(
                exported,
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8")
            Path(self.output_path).write_bytes(output_bytes)
        except Exception:
            return _failure_descriptor(DoclingConversionFailureKind.RESULT_SERIALIZATION)
        return _success_descriptor(output_bytes)


@dataclass(frozen=True, slots=True)
class _ValidatedSuccessDescriptor:
    """父进程已验证的 success descriptor。

    :param size: 预期输出字节数。
    :param sha256: 预期输出 digest。
    """

    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class _WaitOutcome:
    """轮询结束后的 child 或请求取消事实。

    :param wait_result: child terminal；请求取消时为 ``None``。
    :param request_cancelled: 是否观察到公共 token 取消。
    :param child_pid: runtime cleanup 可观察到的 PID。
    :param child_pgid: runtime cleanup 可观察到的 PGID。
    """

    wait_result: ProcessWaitResult | None
    request_cancelled: bool
    child_pid: int | None
    child_pgid: int | None


@dataclass(frozen=True, slots=True)
class _CloseOutcome:
    """handle close 的收口结果。

    :param failure: 普通 cleanup 异常；成功时为 ``None``。
    :param outer_cancellation: close 期间观察到的外层取消原对象。
    """

    failure: Exception | None
    outer_cancellation: asyncio.CancelledError | None


class _CleanupPhase(Enum):
    """production cleanup 结构化诊断阶段。"""

    CHILD_STARTED = "child_started"
    CANCEL_OBSERVED = "cancel_observed"
    TERMINATE_STARTED = "terminate_started"
    TERMINATE_COMPLETED = "terminate_completed"
    KILL_STARTED = "kill_started"
    KILL_COMPLETED = "kill_completed"
    KILL_NOT_NEEDED = "kill_not_needed"
    HANDLE_CLOSE_STARTED = "handle_close_started"
    HANDLE_CLOSE_COMPLETED = "handle_close_completed"
    TEMP_CLEANUP_COMPLETED = "temp_cleanup_completed"
    CANCELLED_TERMINAL_READY = "cancelled_terminal_ready"


class _CleanupOutcome(Enum):
    """production cleanup 结构化诊断结果。"""

    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    NOT_NEEDED = "not_needed"
    READY = "ready"


class ProcessDoclingConverter:
    """基于公共 interruptible process primitive 的共享转换器。"""

    async def convert_to_json_bytes(
        self,
        input_bytes: bytes,
        stream_name: str,
        *,
        config: DoclingConversionConfig,
        cancellation: CancellationToken | None,
    ) -> DoclingConversionResult:
        """在 invocation-local 子进程与临时目录中执行转换。

        :param input_bytes: 不可变原始文档字节。
        :param stream_name: Docling 可读输入名。
        :param config: 闭合转换配置。
        :param cancellation: 公共取消观察 token；``None`` 表示无取消源。
        :returns: close 后通过 descriptor、size 与 digest 校验的 JSON 结果。
        :raises ValueError: 输入、名称或配置非法时抛出。
        :raises DoclingConversionCancelledError: 请求取消且 cleanup 完成时抛出。
        :raises DoclingConversionError: construction、execution、serialization、IPC、
            child crash 或 cleanup 失败时抛出。
        :raises asyncio.CancelledError: 外层 task 取消且 cleanup 完成时透传原异常。
        """

        _validate_conversion_request(input_bytes, stream_name, config)
        if cancellation is not None and cancellation.is_cancelled():
            raise DoclingConversionCancelledError()

        started_at = time.monotonic()
        temp_root: Path | None = None
        handle: InterruptibleProcessHandle | None = None
        primary_error: BaseException | None = None
        wait_outcome: _WaitOutcome | None = None
        result: DoclingConversionResult | None = None
        child_pid: int | None = None
        child_pgid: int | None = None

        try:
            temp_root = Path(tempfile.mkdtemp(prefix=_DOCLING_TEMP_PREFIX))
            input_path = temp_root / _DOCLING_INPUT_FILE_NAME
            output_path = temp_root / _DOCLING_OUTPUT_FILE_NAME
            input_path.write_bytes(input_bytes)
        except Exception as exc:
            primary_error = _public_error(
                DoclingConversionFailureKind.IPC_PROTOCOL,
                exit_code=None,
                cause=exc,
            )
        else:
            try:
                handle = InterruptibleProcessHandle(
                    _DoclingProcessTarget(
                        input_path=str(input_path),
                        output_path=str(output_path),
                        stream_name=stream_name,
                        config=config,
                    )
                )
                handle.start()
                _log_cleanup_phase(
                    _CleanupPhase.CHILD_STARTED,
                    started_at=started_at,
                    child_pid=None,
                    child_pgid=None,
                    outcome=_CleanupOutcome.STARTED,
                )
                wait_outcome = await _wait_for_terminal(
                    handle,
                    cancellation=cancellation,
                    started_at=started_at,
                )
                child_pid = wait_outcome.child_pid
                child_pgid = wait_outcome.child_pgid
            except asyncio.CancelledError as exc:
                primary_error = exc
            except DoclingConversionError as exc:
                primary_error = exc
            except Exception as exc:
                primary_error = _public_error(
                    DoclingConversionFailureKind.CHILD_CRASH,
                    exit_code=None,
                    cause=exc,
                )

        if handle is not None:
            close_outcome = await _close_handle(
                handle,
                started_at=started_at,
                child_pid=child_pid,
                child_pgid=child_pgid,
            )
            if close_outcome.outer_cancellation is not None:
                primary_error = close_outcome.outer_cancellation
            if close_outcome.failure is not None:
                primary_error = _cleanup_error(
                    close_outcome.failure,
                    previous=primary_error,
                )

        if primary_error is None and wait_outcome is not None:
            if not wait_outcome.request_cancelled:
                try:
                    assert temp_root is not None
                    result = _read_terminal_result(
                        output_path=temp_root / _DOCLING_OUTPUT_FILE_NAME,
                        wait_result=wait_outcome.wait_result,
                    )
                except DoclingConversionError as exc:
                    primary_error = exc

        if temp_root is not None:
            try:
                shutil.rmtree(temp_root)
            except Exception as exc:
                primary_error = _cleanup_error(exc, previous=primary_error)
            else:
                _log_cleanup_phase(
                    _CleanupPhase.TEMP_CLEANUP_COMPLETED,
                    started_at=started_at,
                    child_pid=child_pid,
                    child_pgid=child_pgid,
                    outcome=_CleanupOutcome.COMPLETED,
                )

        if primary_error is not None:
            raise primary_error.with_traceback(primary_error.__traceback__)
        if wait_outcome is not None and wait_outcome.request_cancelled:
            _log_cleanup_phase(
                _CleanupPhase.CANCELLED_TERMINAL_READY,
                started_at=started_at,
                child_pid=child_pid,
                child_pgid=child_pgid,
                outcome=_CleanupOutcome.READY,
            )
            raise DoclingConversionCancelledError()
        if result is None:
            raise _public_error(
                DoclingConversionFailureKind.IPC_PROTOCOL,
                exit_code=None,
            )
        return result


async def _wait_for_terminal(
    handle: InterruptibleProcessHandle,
    *,
    cancellation: CancellationToken | None,
    started_at: float,
) -> _WaitOutcome:
    """轮询 child，并在请求取消时执行 terminate/kill 升级。

    :param handle: 已启动的 invocation-local process handle。
    :param cancellation: 公共取消 token；``None`` 表示无取消源。
    :param started_at: 本次调用的 monotonic 起点。
    :returns: child terminal 或已完成 signal 的请求取消事实。
    :raises DoclingConversionError: terminate/kill 失败或 child 未退出时抛出。
    :raises asyncio.CancelledError: 外层 task 取消时透传。
    """

    while True:
        if cancellation is not None and cancellation.is_cancelled():
            _log_cleanup_phase(
                _CleanupPhase.CANCEL_OBSERVED,
                started_at=started_at,
                child_pid=None,
                child_pgid=None,
                outcome=_CleanupOutcome.STARTED,
            )
            terminate_result = await _interrupt_child(
                handle,
                started_phase=_CleanupPhase.TERMINATE_STARTED,
                completed_phase=_CleanupPhase.TERMINATE_COMPLETED,
                grace_seconds=_DOCLING_TERMINATE_GRACE_SECONDS,
                started_at=started_at,
                use_kill=False,
            )
            child_pid = terminate_result.cleanup.child_pid
            child_pgid = terminate_result.cleanup.child_pgid
            if terminate_result.exited:
                _log_cleanup_phase(
                    _CleanupPhase.KILL_NOT_NEEDED,
                    started_at=started_at,
                    child_pid=child_pid,
                    child_pgid=child_pgid,
                    outcome=_CleanupOutcome.NOT_NEEDED,
                )
                return _WaitOutcome(
                    wait_result=None,
                    request_cancelled=True,
                    child_pid=child_pid,
                    child_pgid=child_pgid,
                )
            kill_result = await _interrupt_child(
                handle,
                started_phase=_CleanupPhase.KILL_STARTED,
                completed_phase=_CleanupPhase.KILL_COMPLETED,
                grace_seconds=_DOCLING_KILL_GRACE_SECONDS,
                started_at=started_at,
                use_kill=True,
            )
            if not kill_result.exited:
                raise _public_error(
                    DoclingConversionFailureKind.CLEANUP,
                    exit_code=kill_result.exitcode,
                )
            return _WaitOutcome(
                wait_result=None,
                request_cancelled=True,
                child_pid=kill_result.cleanup.child_pid,
                child_pgid=kill_result.cleanup.child_pgid,
            )

        wait_result = await handle.wait(timeout_seconds=_DOCLING_PROCESS_POLL_SECONDS)
        if isinstance(wait_result, InterruptibleProcessStillRunning):
            continue
        return _WaitOutcome(
            wait_result=wait_result,
            request_cancelled=False,
            child_pid=None,
            child_pgid=None,
        )


async def _interrupt_child(
    handle: InterruptibleProcessHandle,
    *,
    started_phase: _CleanupPhase,
    completed_phase: _CleanupPhase,
    grace_seconds: float,
    started_at: float,
    use_kill: bool,
) -> ProcessInterruptResult:
    """调用 runtime interrupt primitive 并记录结构化诊断。

    :param handle: 已启动的 process handle。
    :param started_phase: signal 启动阶段。
    :param completed_phase: signal 返回阶段。
    :param grace_seconds: 有界等待预算。
    :param started_at: 本次调用 monotonic 起点。
    :param use_kill: ``True`` 调用 kill，否则调用 terminate。
    :returns: runtime interrupt 结果。
    :raises DoclingConversionError: signal primitive 普通失败时抛出 cleanup 错误。
    :raises asyncio.CancelledError: 外层 task 取消时透传。
    """

    _log_cleanup_phase(
        started_phase,
        started_at=started_at,
        child_pid=None,
        child_pgid=None,
        outcome=_CleanupOutcome.STARTED,
    )
    try:
        if use_kill:
            result = await handle.kill(grace_seconds=grace_seconds)
        else:
            result = await handle.terminate(grace_seconds=grace_seconds)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _log_cleanup_phase(
            completed_phase,
            started_at=started_at,
            child_pid=None,
            child_pgid=None,
            outcome=_CleanupOutcome.FAILED,
        )
        raise _public_error(
            DoclingConversionFailureKind.CLEANUP,
            exit_code=None,
            cause=exc,
        ) from exc
    _log_cleanup_phase(
        completed_phase,
        started_at=started_at,
        child_pid=result.cleanup.child_pid,
        child_pgid=result.cleanup.child_pgid,
        outcome=_CleanupOutcome.COMPLETED,
    )
    return result


async def _close_handle(
    handle: InterruptibleProcessHandle,
    *,
    started_at: float,
    child_pid: int | None,
    child_pgid: int | None,
) -> _CloseOutcome:
    """完成 shielded handle close，并保留外层取消 identity。

    :param handle: invocation-local process handle。
    :param started_at: 本次调用 monotonic 起点。
    :param child_pid: 已观察到的 child PID。
    :param child_pgid: 已观察到的 child PGID。
    :returns: close 普通失败与期间首个外层取消对象。
    :raises Exception: 本函数把普通 close 异常收进返回值，不主动抛出。
    """

    _log_cleanup_phase(
        _CleanupPhase.HANDLE_CLOSE_STARTED,
        started_at=started_at,
        child_pid=child_pid,
        child_pgid=child_pgid,
        outcome=_CleanupOutcome.STARTED,
    )
    outer_cancellation: asyncio.CancelledError | None = None
    while True:
        try:
            await handle.close(kill_grace_seconds=_DOCLING_KILL_GRACE_SECONDS)
        except asyncio.CancelledError as exc:
            if outer_cancellation is None:
                outer_cancellation = exc
            continue
        except Exception as exc:
            _log_cleanup_phase(
                _CleanupPhase.HANDLE_CLOSE_COMPLETED,
                started_at=started_at,
                child_pid=child_pid,
                child_pgid=child_pgid,
                outcome=_CleanupOutcome.FAILED,
            )
            return _CloseOutcome(failure=exc, outer_cancellation=outer_cancellation)
        _log_cleanup_phase(
            _CleanupPhase.HANDLE_CLOSE_COMPLETED,
            started_at=started_at,
            child_pid=child_pid,
            child_pgid=child_pgid,
            outcome=_CleanupOutcome.COMPLETED,
        )
        return _CloseOutcome(
            failure=None,
            outer_cancellation=outer_cancellation,
        )


def _read_terminal_result(
    *,
    output_path: Path,
    wait_result: ProcessWaitResult | None,
) -> DoclingConversionResult:
    """映射 child terminal，并验证 success output。

    :param output_path: invocation-local 输出文件。
    :param wait_result: runtime terminal；缺失时视为 IPC 协议失败。
    :returns: 完整性验证通过的唯一成功结果。
    :raises DoclingConversionError: descriptor、output、child 或 closed failure 映射失败。
    """

    if wait_result is None:
        raise _public_error(
            DoclingConversionFailureKind.IPC_PROTOCOL,
            exit_code=None,
        )
    if isinstance(wait_result, InterruptibleProcessFailed):
        failure_kind = (
            DoclingConversionFailureKind.IPC_PROTOCOL
            if wait_result.exitcode == 0
            else DoclingConversionFailureKind.CHILD_CRASH
        )
        raise _public_error(failure_kind, exit_code=wait_result.exitcode)
    if not isinstance(wait_result, InterruptibleProcessCompleted):
        raise _public_error(
            DoclingConversionFailureKind.IPC_PROTOCOL,
            exit_code=None,
        )
    if wait_result.exitcode not in (0, None):
        raise _public_error(
            DoclingConversionFailureKind.CHILD_CRASH,
            exit_code=wait_result.exitcode,
        )

    descriptor = wait_result.value
    if not isinstance(descriptor, dict):
        raise _public_error(
            DoclingConversionFailureKind.IPC_PROTOCOL,
            exit_code=wait_result.exitcode,
        )
    status = descriptor.get(_STATUS_KEY)
    if status == _STATUS_FAILURE:
        failure_kind = _validate_failure_descriptor(
            descriptor,
            exit_code=wait_result.exitcode,
        )
        raise _public_error(failure_kind, exit_code=wait_result.exitcode)
    success = _validate_success_descriptor(
        descriptor,
        exit_code=wait_result.exitcode,
    )
    try:
        output_bytes = output_path.read_bytes()
    except OSError as exc:
        raise _public_error(
            DoclingConversionFailureKind.IPC_PROTOCOL,
            exit_code=wait_result.exitcode,
            cause=exc,
        ) from exc
    if len(output_bytes) != success.size:
        raise _public_error(
            DoclingConversionFailureKind.IPC_PROTOCOL,
            exit_code=wait_result.exitcode,
        )
    if hashlib.sha256(output_bytes).hexdigest() != success.sha256:
        raise _public_error(
            DoclingConversionFailureKind.IPC_PROTOCOL,
            exit_code=wait_result.exitcode,
        )
    return DoclingConversionResult(
        json_bytes=output_bytes,
        size=success.size,
        sha256=success.sha256,
    )


def _validate_success_descriptor(
    descriptor: dict[str, JsonValue],
    *,
    exit_code: int | None,
) -> _ValidatedSuccessDescriptor:
    """严格校验 exact success descriptor。

    :param descriptor: child 回传 JSON 对象。
    :param exit_code: child 正常 terminal 的退出码。
    :returns: typed success descriptor。
    :raises DoclingConversionError: key、类型、版本或 digest 非法时抛出。
    """

    expected_keys = {
        _SCHEMA_VERSION_KEY,
        _STATUS_KEY,
        _SIZE_KEY,
        _SHA256_KEY,
    }
    schema_version = descriptor.get(_SCHEMA_VERSION_KEY)
    status = descriptor.get(_STATUS_KEY)
    size = descriptor.get(_SIZE_KEY)
    sha256 = descriptor.get(_SHA256_KEY)
    if (
        set(descriptor) != expected_keys
        or isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != _DESCRIPTOR_SCHEMA_VERSION
        or status != _STATUS_SUCCESS
        or isinstance(size, bool)
        or not isinstance(size, int)
        or size < 0
        or not isinstance(sha256, str)
        or not _is_lowercase_sha256(sha256)
    ):
        raise _public_error(
            DoclingConversionFailureKind.IPC_PROTOCOL,
            exit_code=exit_code,
        )
    return _ValidatedSuccessDescriptor(size=size, sha256=sha256)


def _validate_failure_descriptor(
    descriptor: dict[str, JsonValue],
    *,
    exit_code: int | None,
) -> DoclingConversionFailureKind:
    """严格校验 exact child failure descriptor。

    :param descriptor: child 回传 JSON 对象。
    :param exit_code: child 正常 terminal 的退出码。
    :returns: child 可产生的闭合失败 kind。
    :raises DoclingConversionError: key、类型、版本、kind 或文本非法时抛出。
    """

    expected_keys = {
        _SCHEMA_VERSION_KEY,
        _STATUS_KEY,
        _FAILURE_KIND_KEY,
        _MESSAGE_KEY,
    }
    schema_version = descriptor.get(_SCHEMA_VERSION_KEY)
    failure_kind_value = descriptor.get(_FAILURE_KIND_KEY)
    message = descriptor.get(_MESSAGE_KEY)
    if (
        set(descriptor) != expected_keys
        or isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != _DESCRIPTOR_SCHEMA_VERSION
        or descriptor.get(_STATUS_KEY) != _STATUS_FAILURE
        or not isinstance(failure_kind_value, str)
        or not isinstance(message, str)
    ):
        raise _public_error(
            DoclingConversionFailureKind.IPC_PROTOCOL,
            exit_code=exit_code,
        )
    child_kinds = {
        DoclingConversionFailureKind.CONVERTER_CONSTRUCTION,
        DoclingConversionFailureKind.CONVERTER_EXECUTION,
        DoclingConversionFailureKind.RESULT_SERIALIZATION,
    }
    try:
        failure_kind = DoclingConversionFailureKind(failure_kind_value)
    except ValueError as exc:
        raise _public_error(
            DoclingConversionFailureKind.IPC_PROTOCOL,
            exit_code=exit_code,
            cause=exc,
        ) from exc
    if failure_kind not in child_kinds or message != _SAFE_FAILURE_MESSAGES[failure_kind]:
        raise _public_error(
            DoclingConversionFailureKind.IPC_PROTOCOL,
            exit_code=exit_code,
        )
    return failure_kind


def _success_descriptor(output_bytes: bytes) -> dict[str, JsonValue]:
    """构造 exact success descriptor。

    :param output_bytes: 已写入 output 的 JSON bytes。
    :returns: versioned exact descriptor。
    :raises Exception: 本函数不抛出异常。
    """

    return {
        _SCHEMA_VERSION_KEY: _DESCRIPTOR_SCHEMA_VERSION,
        _STATUS_KEY: _STATUS_SUCCESS,
        _SIZE_KEY: len(output_bytes),
        _SHA256_KEY: hashlib.sha256(output_bytes).hexdigest(),
    }


def _failure_descriptor(
    failure_kind: DoclingConversionFailureKind,
) -> dict[str, JsonValue]:
    """构造 exact child failure descriptor。

    :param failure_kind: child 边界可产生的失败 kind。
    :returns: versioned exact descriptor。
    :raises ValueError: 非 child-owned kind 被误用时抛出。
    """

    if failure_kind not in {
        DoclingConversionFailureKind.CONVERTER_CONSTRUCTION,
        DoclingConversionFailureKind.CONVERTER_EXECUTION,
        DoclingConversionFailureKind.RESULT_SERIALIZATION,
    }:
        raise ValueError("failure kind is not child-owned")
    return {
        _SCHEMA_VERSION_KEY: _DESCRIPTOR_SCHEMA_VERSION,
        _STATUS_KEY: _STATUS_FAILURE,
        _FAILURE_KIND_KEY: failure_kind.value,
        _MESSAGE_KEY: _SAFE_FAILURE_MESSAGES[failure_kind],
    }


def _validate_conversion_request(
    input_bytes: bytes,
    stream_name: str,
    config: DoclingConversionConfig,
) -> None:
    """校验进入 temp/process 边界前的直接 contract。

    :param input_bytes: 原始文档字节。
    :param stream_name: Docling 可读输入名。
    :param config: 闭合转换配置。
    :returns: ``None``。
    :raises ValueError: 空字节、空名称或非法配置时抛出。
    """

    if not input_bytes:
        raise ValueError("input_bytes must not be empty")
    if not stream_name.strip():
        raise ValueError("stream_name must not be empty")
    # dataclass 构造后仍在 owner boundary 复核，避免绕过初始化得到非法实例。
    config.__post_init__()


def _is_lowercase_sha256(value: str) -> bool:
    """判断字符串是否为 64 位 lowercase SHA-256。

    :param value: 候选 digest。
    :returns: 格式合法返回 ``True``。
    :raises Exception: 本函数不抛出异常。
    """

    return len(value) == _SHA256_HEX_LENGTH and all(character in _LOWERCASE_HEX_DIGITS for character in value)


def _is_closed_json_value(value: JsonValue) -> bool:
    """递归验证 Docling export 只含标准 JSON 值。

    :param value: 候选 JSON value。
    :returns: 值与所有后代均属于闭合 JSON 类型时返回 ``True``。
    :raises Exception: 本函数不抛出异常。
    """

    if value is None or isinstance(value, str | bool | int):
        return True
    if isinstance(value, float):
        return value == value and value not in (float("inf"), float("-inf"))
    if isinstance(value, list):
        return all(_is_closed_json_value(item) for item in value)
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _is_closed_json_value(item) for key, item in value.items())
    return False


def _public_error(
    failure_kind: DoclingConversionFailureKind,
    *,
    exit_code: int | None,
    cause: BaseException | None = None,
) -> DoclingConversionError:
    """构造固定安全文本的公开转换异常。

    :param failure_kind: 闭合失败种类。
    :param exit_code: 子进程退出码。
    :param cause: 可选内部首因，仅保留在异常链中。
    :returns: 公开转换异常。
    :raises Exception: 本函数不主动抛出异常。
    """

    error = DoclingConversionError(
        failure_kind,
        _SAFE_FAILURE_MESSAGES[failure_kind],
        exit_code,
    )
    if cause is not None:
        error.__cause__ = cause
    return error


def _cleanup_error(
    cleanup_failure: BaseException,
    *,
    previous: BaseException | None,
) -> DoclingConversionError:
    """让 cleanup 失败取得最高优先级并保留完整异常链。

    :param cleanup_failure: 当前 cleanup 失败。
    :param previous: cleanup 前的业务失败或外层取消。
    :returns: 以 cleanup 为公开 kind 的异常。
    :raises Exception: 本函数不主动抛出异常。
    """

    if previous is not None and cleanup_failure is not previous:
        cleanup_failure.__cause__ = previous
    return _public_error(
        DoclingConversionFailureKind.CLEANUP,
        exit_code=None,
        cause=cleanup_failure,
    )


def _log_cleanup_phase(
    phase: _CleanupPhase,
    *,
    started_at: float,
    child_pid: int | None,
    child_pgid: int | None,
    outcome: _CleanupOutcome,
) -> None:
    """记录不含输入路径或 traceback 的 production cleanup 诊断。

    :param phase: cleanup 状态机阶段。
    :param started_at: 本次调用 monotonic 起点。
    :param child_pid: 当前可观察 child PID。
    :param child_pgid: 当前可观察 child PGID。
    :param outcome: 当前阶段结果。
    :returns: ``None``。
    :raises Exception: logging 后端异常由标准库自行处理，不向调用方传播。
    """

    elapsed_seconds = time.monotonic() - started_at
    _LOGGER.info(
        (
            "docling_process_converter.cleanup_phase phase=%s "
            "monotonic_elapsed_seconds=%.6f pid=%s pgid=%s outcome=%s"
        ),
        phase.value,
        elapsed_seconds,
        child_pid,
        child_pgid,
        outcome.value,
        extra={
            "cleanup_phase": phase.value,
            "monotonic_elapsed_seconds": elapsed_seconds,
            "child_pid": child_pid,
            "child_pgid": child_pgid,
            "cleanup_outcome": outcome.value,
        },
    )


__all__ = [
    "DEFAULT_FINS_DOCLING_CONVERSION_CONFIG",
    "DoclingConversionCancelledError",
    "DoclingConversionConfig",
    "DoclingConversionError",
    "DoclingConversionFailureKind",
    "DoclingConversionResult",
    "DoclingConverter",
    "ProcessDoclingConverter",
]
