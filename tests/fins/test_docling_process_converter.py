"""Fins 共享 Docling process converter 的 owner contract 测试。"""

from __future__ import annotations

import asyncio
import errno
import hashlib
import json
import logging
import multiprocessing
import multiprocessing.queues
import os
import pickle
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar, Literal, Protocol, TextIO, cast

import pytest
from docling.backend.abstract_backend import AbstractDocumentBackend
from docling.datamodel.base_models import ConversionStatus, DoclingComponentType, ErrorItem, InputFormat
from docling.datamodel.document import ConversionResult, InputDocument
from docling_core.types.doc.document import DoclingDocument

from dayu.documents.xbrl_config import PreparedXbrlInput
from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.documents.docling_runtime import DoclingRuntimeInitializationError
from dayu.documents import docling_runtime
from tests.documents.test_xbrl_config import _deployment, _loaded
from dayu.fins.pipelines import docling_process_converter
from dayu.runtime.interruptible_process import (
    InterruptibleProcessCompleted,
    InterruptibleProcessFailed,
    InterruptibleProcessHandle,
    InterruptibleProcessTarget,
    ProcessInterruptResult,
    ProcessWaitResult,
)

_INPUT_BYTES = b"immutable-filing-input"
_OUTPUT_BYTES = '{\n  "converted": true,\n  "name": "\u5e74\u62a5"\n}'.encode("utf-8")
_REQUESTED_AT = datetime(2026, 8, 12, tzinfo=timezone.utc)
_NESTED_MARKER_ROOT_ENV = "DAYU_TEST_SHARED_DOCLING_MARKER_ROOT"
_PARENT_PID_FILE = "parent.pid"
_NESTED_PID_FILE = "nested.pid"
_PROCESS_READY_DEADLINE_SECONDS = 5.0
_PROCESS_EXIT_DEADLINE_SECONDS = 5.0
_PROCESS_POLL_SECONDS = 0.02
_TEST_TERMINATE_GRACE_SECONDS = 0.05
_TEST_KILL_GRACE_SECONDS = 1.0
_EXIT_FLUSH_CALL_NUMBER = 2
_LAST_RESORT_CONTROL_MARKER = "owner-test-last-resort-control"
_RESTORED_STDERR_MARKER = b"owner-test-restored-stderr\n"
_NESTED_PROCESS_SCRIPT = """
import os
import signal
import sys

signal.signal(signal.SIGTERM, signal.SIG_IGN)
with open(sys.argv[1], "w", encoding="utf-8") as marker_file:
    marker_file.write(str(os.getpid()))
    marker_file.flush()
signal.pause()
"""


class _ExitFlushFailureStderr:
    """仅在隔离区退出 flush 时失败的 stderr 观察器。"""

    def __init__(self, delegate: TextIO) -> None:
        """初始化 stderr 观察器。

        :param delegate: 提供真实 FD2 的当前 stderr。
        :returns: ``None``。
        :raises Exception: 本构造函数不抛出异常。
        """

        self._delegate = delegate
        self.flush_calls = 0

    def flush(self) -> None:
        """入口 flush 正常，退出 flush 抛出次生异常。

        :returns: ``None``。
        :raises OSError: 隔离区退出 flush 时抛出。
        """

        self.flush_calls += 1
        if self.flush_calls == _EXIT_FLUSH_CALL_NUMBER:
            raise OSError("owner-test exit flush failure")
        self._delegate.flush()

    def fileno(self) -> int:
        """返回真实 stderr 文件描述符。

        :returns: delegate 拥有的 FD2。
        :raises OSError: delegate 无有效 descriptor 时抛出。
        """

        return self._delegate.fileno()


class _CleanupLogRecord(Protocol):
    """production cleanup logging extra 字段的 typed 观察面。"""

    cleanup_phase: str
    cleanup_outcome: str
    monotonic_elapsed_seconds: float


class _MutableCancellationToken:
    """可由 deterministic handle 推进状态的公共取消 token fake。"""

    def __init__(self, *, cancelled: bool = False) -> None:
        """初始化取消状态。

        :param cancelled: 初始是否已取消。
        :returns: ``None``。
        :raises Exception: 本构造函数不抛出异常。
        """

        self._cancelled = cancelled

    def cancel(self) -> None:
        """把 token 推进到首次取消状态。

        :returns: ``None``。
        :raises Exception: 本方法不抛出异常。
        """

        self._cancelled = True

    def is_cancelled(self) -> bool:
        """返回当前取消状态。

        :returns: 已取消返回 ``True``。
        :raises Exception: 本方法不抛出异常。
        """

        return self._cancelled

    def cancel_reason(self) -> str | None:
        """返回固定取消原因。

        :returns: 已取消返回固定原因，否则返回 ``None``。
        :raises Exception: 本方法不抛出异常。
        """

        return "test_cancelled" if self._cancelled else None

    def requested_at(self) -> datetime | None:
        """返回固定取消时间。

        :returns: 已取消返回固定 UTC 时间，否则返回 ``None``。
        :raises Exception: 本方法不抛出异常。
        """

        return _REQUESTED_AT if self._cancelled else None


class _MarkerCancellationToken:
    """以 spawned child readiness marker 为取消真源的 token。"""

    def __init__(self, marker_path: Path) -> None:
        """初始化 marker token。

        :param marker_path: child ready 后原子出现的 marker。
        :returns: ``None``。
        :raises Exception: 本构造函数不抛出异常。
        """

        self._marker_path = marker_path

    def is_cancelled(self) -> bool:
        """在 readiness marker 出现后返回已取消。

        :returns: marker 存在返回 ``True``。
        :raises Exception: 本方法不抛出异常。
        """

        return self._marker_path.exists()

    def cancel_reason(self) -> str | None:
        """返回 marker 对应的固定原因。

        :returns: 已取消返回固定原因，否则返回 ``None``。
        :raises Exception: 本方法不抛出异常。
        """

        return "nested_ready" if self.is_cancelled() else None

    def requested_at(self) -> datetime | None:
        """返回 marker 取消的固定时间。

        :returns: 已取消返回固定 UTC 时间，否则返回 ``None``。
        :raises Exception: 本方法不抛出异常。
        """

        return _REQUESTED_AT if self.is_cancelled() else None


@dataclass(frozen=True, slots=True)
class _FakeDocument:
    """返回固定 closed JSON mapping 的 Docling document fake。"""

    stream_name: str

    def export_to_dict(self) -> dict[str, JsonValue]:
        """返回包含非 ASCII 内容的固定 mapping。

        :returns: closed JSON mapping。
        :raises Exception: 本方法不抛出异常。
        """

        return {"converted": True, "name": "年报"}


@dataclass(frozen=True, slots=True)
class _FakeConversion:
    """Docling conversion result 的最小 fake。"""

    document: _FakeDocument


class _SerializationFailureDocument:
    """导出阶段抛出固定异常的 document fake。"""

    def export_to_dict(self) -> dict[str, JsonValue]:
        """抛出 deterministic serialization failure。

        :returns: 永不返回。
        :raises RuntimeError: 始终抛出。
        """

        raise RuntimeError("sensitive serialization path")


@dataclass(frozen=True, slots=True)
class _SerializationFailureConversion:
    """包含导出失败 document 的 conversion fake。"""

    document: _SerializationFailureDocument = _SerializationFailureDocument()


def _spawn_construction_failure_convert(
    raw_bytes: bytes,
    *,
    stream_name: str,
    do_ocr: bool,
    do_table_structure: bool,
    table_mode: str,
    do_cell_matching: bool,
) -> _FakeConversion:
    """在 spawned child 中产生 construction failure。

    :param raw_bytes: 输入字节。
    :param stream_name: 输入名。
    :param do_ocr: OCR 配置。
    :param do_table_structure: 表格结构配置。
    :param table_mode: 表格模式。
    :param do_cell_matching: 单元格匹配配置。
    :returns: 永不返回。
    :raises DoclingRuntimeInitializationError: 始终抛出。
    """

    _ = (
        raw_bytes,
        stream_name,
        do_ocr,
        do_table_structure,
        table_mode,
        do_cell_matching,
    )
    raise DoclingRuntimeInitializationError("spawned construction detail")


def _spawn_execution_failure_convert(
    raw_bytes: bytes,
    *,
    stream_name: str,
    do_ocr: bool,
    do_table_structure: bool,
    table_mode: str,
    do_cell_matching: bool,
) -> _FakeConversion:
    """在 spawned child 中产生 execution failure。

    :param raw_bytes: 输入字节。
    :param stream_name: 输入名。
    :param do_ocr: OCR 配置。
    :param do_table_structure: 表格结构配置。
    :param table_mode: 表格模式。
    :param do_cell_matching: 单元格匹配配置。
    :returns: 永不返回。
    :raises RuntimeError: 始终抛出。
    """

    _ = (
        raw_bytes,
        stream_name,
        do_ocr,
        do_table_structure,
        table_mode,
        do_cell_matching,
    )
    raise RuntimeError("spawned execution detail")


def _spawn_serialization_failure_convert(
    raw_bytes: bytes,
    *,
    stream_name: str,
    do_ocr: bool,
    do_table_structure: bool,
    table_mode: str,
    do_cell_matching: bool,
) -> _SerializationFailureConversion:
    """在 spawned child 中返回 export failure conversion。

    :param raw_bytes: 输入字节。
    :param stream_name: 输入名。
    :param do_ocr: OCR 配置。
    :param do_table_structure: 表格结构配置。
    :param table_mode: 表格模式。
    :param do_cell_matching: 单元格匹配配置。
    :returns: export 失败 conversion。
    :raises Exception: 本函数不抛出异常。
    """

    _ = (
        raw_bytes,
        stream_name,
        do_ocr,
        do_table_structure,
        table_mode,
        do_cell_matching,
    )
    return _SerializationFailureConversion()


@dataclass(frozen=True, slots=True)
class _SpawnBoundaryProbeTarget:
    """在真实 runtime child 内调用 production target 的测试 target。"""

    input_path: str
    output_path: str
    failure_mode: Literal["construction", "execution", "serialization"]

    def __call__(self) -> JsonValue:
        """安装 child-local fake 后调用真实三段边界。

        :returns: production target 的 exact failure descriptor。
        :raises Exception: production target 未闭合的异常原样交给 runtime。
        """

        child_monkeypatch = pytest.MonkeyPatch()
        if self.failure_mode == "construction":
            replacement = _spawn_construction_failure_convert
        elif self.failure_mode == "execution":
            replacement = _spawn_execution_failure_convert
        else:
            replacement = _spawn_serialization_failure_convert
        child_monkeypatch.setattr(
            docling_process_converter,
            "convert_pdf_bytes_with_docling",
            replacement,
        )
        try:
            (Path(self.input_path).parent / "diagnostics").mkdir(mode=0o700)
            return docling_process_converter._DoclingProcessTarget(
                input_path=self.input_path,
                output_path=self.output_path,
                stream_name="annual-report.pdf",
                config=docling_process_converter.DEFAULT_FINS_DOCLING_CONVERSION_CONFIG,
            xbrl_input=None, sandbox_profile=None, diagnostics_directory=str(Path(self.input_path).parent / "diagnostics"))()
        finally:
            child_monkeypatch.undo()


class _RecordingHandle:
    """实现公共 handle 方法并精确控制 parent 状态机的 fake。"""

    instances: ClassVar[list[_RecordingHandle]] = []
    configured_wait_result: ClassVar[ProcessWaitResult | asyncio.CancelledError | None] = None
    cancellation_to_request: ClassVar[_MutableCancellationToken | None] = None
    terminate_exited: ClassVar[bool] = True
    kill_exited: ClassVar[bool] = True
    terminate_failure: ClassVar[Exception | None] = None
    kill_failure: ClassVar[Exception | None] = None
    close_failure: ClassVar[Exception | None] = None
    close_cancellation: ClassVar[asyncio.CancelledError | None] = None
    invoke_target: ClassVar[bool] = True

    def __init__(self, target: InterruptibleProcessTarget) -> None:
        """保存 invocation-local target 与调用记录。

        :param target: production converter 创建的 child target。
        :returns: ``None``。
        :raises Exception: 本构造函数不抛出异常。
        """

        self.target = target
        self.calls: list[str] = []
        self.wait_calls = 0
        self._target_result: JsonValue | None = None
        self._close_cancelled = False
        self.instances.append(self)

    def start(self) -> None:
        """记录启动，并按配置在当前测试进程执行 target。

        :returns: ``None``。
        :raises Exception: target 未闭合的异常原样抛出。
        """

        self.calls.append("start")
        if self.invoke_target:
            self._target_result = _run_target_spawn(cast(docling_process_converter._DoclingProcessTarget, self.target), "success")

    async def wait(self, timeout_seconds: float | None) -> ProcessWaitResult:
        """返回配置 terminal，或先推进 token 再返回 still-running。

        :param timeout_seconds: production poll interval。
        :returns: deterministic wait result。
        :raises asyncio.CancelledError: 配置为外层取消时抛出原对象。
        """

        assert timeout_seconds == docling_process_converter._DOCLING_PROCESS_POLL_SECONDS
        self.calls.append("wait")
        self.wait_calls += 1
        token = self.cancellation_to_request
        if token is not None and self.wait_calls == 1:
            token.cancel()
            return docling_process_converter.InterruptibleProcessStillRunning(elapsed_seconds=0.0)
        configured = self.configured_wait_result
        if configured is not None:
            if isinstance(configured, BaseException):
                raise configured
            return configured
        assert self._target_result is not None
        return InterruptibleProcessCompleted(
            value=self._target_result,
            exitcode=0,
        )

    async def terminate(self, grace_seconds: float) -> ProcessInterruptResult:
        """返回配置的 terminate 结果。

        :param grace_seconds: production terminate grace。
        :returns: deterministic interrupt result。
        :raises Exception: 配置的普通 terminate failure。
        """

        assert grace_seconds == docling_process_converter._DOCLING_TERMINATE_GRACE_SECONDS
        self.calls.append("terminate")
        if self.terminate_failure is not None:
            raise self.terminate_failure
        return ProcessInterruptResult(
            supported=True,
            exited=self.terminate_exited,
            exitcode=-signal.SIGTERM if self.terminate_exited else None,
            elapsed_seconds=0.0,
        )

    async def kill(self, grace_seconds: float) -> ProcessInterruptResult:
        """返回配置的 kill 结果。

        :param grace_seconds: production kill grace。
        :returns: deterministic interrupt result。
        :raises Exception: 配置的普通 kill failure。
        """

        assert grace_seconds == docling_process_converter._DOCLING_KILL_GRACE_SECONDS
        self.calls.append("kill")
        if self.kill_failure is not None:
            raise self.kill_failure
        return ProcessInterruptResult(
            supported=True,
            exited=self.kill_exited,
            exitcode=-signal.SIGKILL if self.kill_exited else None,
            elapsed_seconds=0.0,
        )

    async def close(self, *, kill_grace_seconds: float) -> None:
        """记录 close 并按配置抛出 cleanup failure 或一次外层取消。

        :param kill_grace_seconds: production close kill grace。
        :returns: ``None``。
        :raises asyncio.CancelledError: 配置时首次抛出原取消对象。
        :raises Exception: 配置的普通 close failure。
        """

        assert kill_grace_seconds == docling_process_converter._DOCLING_KILL_GRACE_SECONDS
        self.calls.append("close")
        if self.close_cancellation is not None and not self._close_cancelled:
            self._close_cancelled = True
            raise self.close_cancellation
        if self.close_failure is not None:
            raise self.close_failure

    @classmethod
    def reset(cls) -> None:
        """恢复每个测试的默认 deterministic 场景。

        :returns: ``None``。
        :raises Exception: 本方法不抛出异常。
        """

        cls.instances.clear()
        cls.configured_wait_result = None
        cls.cancellation_to_request = None
        cls.terminate_exited = True
        cls.kill_exited = True
        cls.terminate_failure = None
        cls.kill_failure = None
        cls.close_failure = None
        cls.close_cancellation = None
        cls.invoke_target = True


@dataclass(frozen=True, slots=True)
class _IgnoringTerminateNestedTarget:
    """启动嵌套进程并忽略 SIGTERM 的真实 spawn target。"""

    input_path: str
    output_path: str
    stream_name: str
    config: docling_process_converter.DoclingConversionConfig
    xbrl_input: PreparedXbrlInput | None
    sandbox_profile: str | None
    diagnostics_directory: str

    def __call__(self) -> JsonValue:
        """等待 nested child ready 后发布 parent PID 并阻塞。

        :returns: 永不正常返回。
        :raises RuntimeError: marker root 缺失或 nested child 未 ready 时抛出。
        :raises OSError: marker 读写或 nested process 启动失败时抛出。
        """

        _ = (self.input_path, self.output_path, self.stream_name, self.config)
        marker_root_text = os.environ.get(_NESTED_MARKER_ROOT_ENV)
        if marker_root_text is None:
            raise RuntimeError("test marker root is unavailable")
        marker_root = Path(marker_root_text)
        nested_marker = marker_root / _NESTED_PID_FILE
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        subprocess.Popen(
            [sys.executable, "-c", _NESTED_PROCESS_SCRIPT, str(nested_marker)],
            close_fds=True,
        )
        _wait_for_marker(
            nested_marker,
            deadline_seconds=_PROCESS_READY_DEADLINE_SECONDS,
        )
        (marker_root / _PARENT_PID_FILE).write_text(
            str(os.getpid()),
            encoding="utf-8",
        )
        signal.pause()
        raise RuntimeError("signal.pause returned unexpectedly")


class _RecordingRealHandle:
    """委托真实 runtime primitive并记录 converter 调用顺序。"""

    instances: ClassVar[list[_RecordingRealHandle]] = []

    def __init__(self, target: InterruptibleProcessTarget) -> None:
        """构造真实 handle。

        :param target: 可 pickle spawned child target。
        :returns: ``None``。
        :raises OSError: multiprocessing 资源初始化失败时抛出。
        """

        self._handle = InterruptibleProcessHandle(target)
        self.calls: list[str] = []
        self.instances.append(self)

    def start(self) -> None:
        """启动真实 child。

        :returns: ``None``。
        :raises RuntimeError: runtime 拒绝启动时抛出。
        """

        self.calls.append("start")
        self._handle.start()

    async def wait(self, timeout_seconds: float | None) -> ProcessWaitResult:
        """等待真实 child。

        :param timeout_seconds: 有界 poll timeout。
        :returns: runtime wait result。
        :raises ValueError: timeout 非法时抛出。
        """

        self.calls.append("wait")
        return await self._handle.wait(timeout_seconds)

    async def terminate(self, grace_seconds: float) -> ProcessInterruptResult:
        """terminate 真实 child/process group。

        :param grace_seconds: terminate grace。
        :returns: runtime interrupt result。
        :raises ValueError: grace 非法时抛出。
        """

        self.calls.append("terminate")
        return await self._handle.terminate(grace_seconds)

    async def kill(self, grace_seconds: float) -> ProcessInterruptResult:
        """kill 真实 child/process group。

        :param grace_seconds: kill grace。
        :returns: runtime interrupt result。
        :raises ValueError: grace 非法时抛出。
        """

        self.calls.append("kill")
        return await self._handle.kill(grace_seconds)

    async def close(self, *, kill_grace_seconds: float) -> None:
        """关闭真实 process 与 queue 资源。

        :param kill_grace_seconds: close kill grace。
        :returns: ``None``。
        :raises RuntimeError: runtime cleanup 未完成时抛出。
        """

        self.calls.append("close")
        await self._handle.close(kill_grace_seconds=kill_grace_seconds)


@pytest.fixture(autouse=True)
def _reset_handle_state() -> None:
    """清空跨测试 fake/real handle 记录。

    :returns: ``None``。
    :raises Exception: 本 fixture 不抛出异常。
    """

    _RecordingHandle.reset()
    _RecordingRealHandle.instances.clear()


def _successful_convert(
    raw_bytes: bytes,
    *,
    stream_name: str,
    do_ocr: bool,
    do_table_structure: bool,
    table_mode: str,
    do_cell_matching: bool,
) -> _FakeConversion:
    """验证 production child 收到 immutable 输入与 config 后返回成功。

    :param raw_bytes: input temp 中读出的字节。
    :param stream_name: 原样传入的业务可读名称。
    :param do_ocr: OCR 配置。
    :param do_table_structure: 表格结构配置。
    :param table_mode: 表格模式。
    :param do_cell_matching: 单元格匹配配置。
    :returns: 固定 fake conversion。
    :raises AssertionError: 任一输入或配置漂移时抛出。
    """

    assert raw_bytes == _INPUT_BYTES
    assert stream_name in {"annual-report.pdf", "annual-report.docx"}
    assert do_ocr is True
    assert do_table_structure is True
    assert table_mode == "accurate"
    assert do_cell_matching is True
    return _FakeConversion(document=_FakeDocument(stream_name=stream_name))



@dataclass(frozen=True, slots=True)
class _TargetSpawnProbe:
    """在独立真实 spawn 内安装明确转换边界并回传观察。"""
    target: docling_process_converter._DoclingProcessTarget
    mode: str

    def __call__(self) -> JsonValue:
        """参数：无；返回：原 descriptor；异常：未闭合控制流传播。"""
        patch = pytest.MonkeyPatch()
        replacement = {"success": _successful_convert, "construction": _spawn_construction_failure_convert,
                       "execution": _spawn_execution_failure_convert, "serialization": _spawn_serialization_failure_convert,
                       "leak": _diagnostic_convert}.get(self.mode, _successful_convert)
        patch.setattr(docling_process_converter, "convert_pdf_bytes_with_docling", replacement)
        if self.mode == "flush":
            patch.setattr(sys, "stderr", _ExitFlushFailureStderr(sys.stderr))
            patch.setattr(docling_process_converter, "convert_pdf_bytes_with_docling", _spawn_construction_failure_convert)
        if self.mode == "isolation":
            patch.setattr(docling_process_converter.os, "dup2", _fail_dup2)
            patch.setattr(docling_process_converter, "convert_pdf_bytes_with_docling", _forbidden_xbrl_pdf_dispatch)
        try:
            return self.target()
        finally:
            patch.undo()


def _fail_dup2(fd: int, target: int) -> None:
    """参数：两个 fd；返回：永不返回；异常：模拟隔离无法建立。"""
    raise OSError("isolation setup")


def _diagnostic_convert(raw_bytes: bytes, *, stream_name: str, do_ocr: bool,
                        do_table_structure: bool, table_mode: str, do_cell_matching: bool) -> _FakeConversion:
    """参数：真实转换输入配置；返回：合成成功；异常：断言或控制流传播。"""
    # installed owner 在 capture 之后才 import，且强制添加 handler，避免 hasHandlers 偶然拒加。
    from docling_ibm_models.tableformer.settings import get_custom_logger
    logger = get_custom_logger("MatchingPostProcessor", logging.INFO)
    logger.addHandler(logging.StreamHandler(sys.stdout))
    logger.propagate = False
    logger.warning("installed late-created warning")
    logger.warning("%d", "invalid-format")
    os.write(1, b"native stdout WARNING\n")
    os.write(2, b"native stderr\n")
    return _successful_convert(raw_bytes, stream_name=stream_name, do_ocr=do_ocr,
                               do_table_structure=do_table_structure, table_mode=table_mode, do_cell_matching=do_cell_matching)


def _spawn_result_entry(probe: _TargetSpawnProbe, result: multiprocessing.queues.Queue[JsonValue]) -> None:
    """参数：worker probe/专用结果队列；返回：无；异常：未闭合异常使测试失败。"""
    result.put(probe())


def _run_target_spawn(target: docling_process_converter._DoclingProcessTarget, mode: str) -> JsonValue:
    """参数：真实 target/明确合成边界；返回：worker 原 descriptor；异常：超时/错误终态断言失败。"""
    context = multiprocessing.get_context("spawn")
    queue: multiprocessing.queues.Queue[JsonValue] = context.Queue()
    worker = context.Process(target=_spawn_result_entry, args=(_TargetSpawnProbe(target, mode), queue))
    worker.start()
    try:
        result = queue.get(timeout=30)
        worker.join(30)
        assert worker.exitcode == 0
        return result
    finally:
        if worker.is_alive():
            worker.kill(); worker.join()
        worker.close(); queue.close(); queue.join_thread()


@pytest.mark.parametrize("stream_name", ("annual-report.pdf", "annual-report.docx"))
def test_child_target_is_pickleable_and_preserves_input_name_config_without_suffix_branch(tmp_path: Path, stream_name: str) -> None:
    """参数：独占目录/输入名；返回：无；异常：真实 spawn/pickle/配置合同漂移时失败。"""
    target = _target_in_temp(tmp_path)
    from dataclasses import replace
    target = replace(target, stream_name=stream_name)
    restored = pickle.loads(pickle.dumps(target))
    assert restored == target
    descriptor = _run_target_spawn(restored, "success")
    assert (tmp_path / "output.json").read_bytes() == _OUTPUT_BYTES
    assert descriptor == docling_process_converter._success_descriptor(_OUTPUT_BYTES)


@pytest.mark.parametrize("mode,kind", [("construction", "converter_construction"), ("execution", "converter_execution"),
                                       ("serialization", "result_serialization"), ("flush", "converter_construction"),
                                       ("isolation", "converter_construction")])
def test_child_target_exact_failure_and_flush_secondary(tmp_path: Path, mode: str, kind: str, capfd: pytest.CaptureFixture[str]) -> None:
    """参数：目录/故障阶段/公开双流；返回：无；异常：原 descriptor 或隔离/flush 合同漂移时失败。"""
    descriptor = _run_target_spawn(_target_in_temp(tmp_path), mode)
    assert descriptor == docling_process_converter._failure_descriptor(docling_process_converter.DoclingConversionFailureKind(kind))
    public = capfd.readouterr()
    assert public.out == public.err == ""
    if mode == "flush":
        from dayu.runtime.process_diagnostics import ProcessCaptureIncident, ProcessCaptureIncidentCode, read_process_diagnostics
        assert ProcessCaptureIncident(ProcessCaptureIncidentCode.SCOPE_FLUSH) in list(read_process_diagnostics(tmp_path / "diagnostics", require_complete=True))


def test_child_installed_late_handler_and_native_diagnostics(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    """参数：独占目录/真实双流；返回：无；异常：installed owner 或 fd 诊断外泄/等级漂移时失败。"""
    from dayu.runtime.process_diagnostics import ProcessLogDiagnostic, ProcessCaptureIncident, ProcessRawDiagnostic, read_process_diagnostics
    result = _run_target_spawn(_target_in_temp(tmp_path), "leak")
    assert result == docling_process_converter._success_descriptor(_OUTPUT_BYTES)
    diagnostics = list(read_process_diagnostics(tmp_path / "diagnostics", require_complete=True))
    records = [value for value in diagnostics if isinstance(value, ProcessLogDiagnostic)]
    assert len(records) == 1 and records[0].source_name == "MatchingPostProcessor" and records[0].source_level == logging.WARNING
    assert any(isinstance(value, ProcessCaptureIncident) for value in diagnostics)
    assert any(isinstance(value, ProcessRawDiagnostic) and b"native stdout WARNING" in value.data for value in diagnostics)
    public = capfd.readouterr(); assert public.out == public.err == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure_mode", "expected_kind", "expected_message"),
    (
        (
            "construction",
            "converter_construction",
            "Docling converter construction failed",
        ),
        (
            "execution",
            "converter_execution",
            "Docling conversion execution failed",
        ),
        (
            "serialization",
            "result_serialization",
            "Docling conversion result serialization failed",
        ),
    ),
)
async def test_child_three_failures_are_runtime_completed_descriptors(
    tmp_path: Path,
    failure_mode: Literal["construction", "execution", "serialization"],
    expected_kind: str,
    expected_message: str,
) -> None:
    """三段已知业务失败必须让真实 runtime 观察到正常 completed。

    :param tmp_path: pytest 临时目录。
    :param failure_mode: 本例 child failure 阶段。
    :param expected_kind: descriptor failure kind。
    :param expected_message: descriptor 固定安全文本。
    :returns: ``None``。
    :raises Exception: spawn、wait、close 或断言失败时抛出。
    """

    input_path = tmp_path / "input.bin"
    output_path = tmp_path / "output.json"
    input_path.write_bytes(_INPUT_BYTES)
    handle = InterruptibleProcessHandle(
        _SpawnBoundaryProbeTarget(
            input_path=str(input_path),
            output_path=str(output_path),
            failure_mode=failure_mode,
        )
    )
    try:
        handle.start()
        terminal = await handle.wait(timeout_seconds=30.0)
    finally:
        await handle.close(kill_grace_seconds=_TEST_KILL_GRACE_SECONDS)

    assert isinstance(terminal, InterruptibleProcessCompleted)
    # runtime 可以先取到 queue message，再用 non-blocking join 观察尚未刷新
    # 的 exitcode；completed union 本身才是这里的可信 terminal 事实。
    assert terminal.exitcode in (0, None)
    assert terminal.value == {
        "schema_version": 1,
        "status": "failure",
        "failure_kind": expected_kind,
        "message": expected_message,
    }
    assert not output_path.exists()


def test_result_and_config_validate_owner_contract() -> None:
    """typed config/result 必须拒绝非法模式、size 与 digest。

    :returns: ``None``。
    :raises Exception: 断言失败时抛出。
    """

    digest = hashlib.sha256(_OUTPUT_BYTES).hexdigest()
    result = docling_process_converter.DoclingConversionResult(
        json_bytes=_OUTPUT_BYTES,
        size=len(_OUTPUT_BYTES),
        sha256=digest,
    )
    assert result.sha256 == digest
    with pytest.raises(ValueError, match="size"):
        docling_process_converter.DoclingConversionResult(
            json_bytes=_OUTPUT_BYTES,
            size=len(_OUTPUT_BYTES) + 1,
            sha256=digest,
        )
    with pytest.raises(ValueError, match="sha256"):
        docling_process_converter.DoclingConversionResult(
            json_bytes=_OUTPUT_BYTES,
            size=len(_OUTPUT_BYTES),
            sha256="0" * 64,
        )
    with pytest.raises(ValueError, match="table_mode"):
        docling_process_converter.DoclingConversionConfig(
            do_ocr=True,
            do_table_structure=True,
            table_mode=cast(Literal["accurate"], "fast"),
            do_cell_matching=True,
        )


@pytest.mark.asyncio
async def test_converter_success_closes_before_output_validation_and_cleans_independent_temps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同一 shared instance 每次使用独立资源，并在 output validation 前 close。

    :param monkeypatch: pytest 属性替换工具。
    :returns: ``None``。
    :raises Exception: conversion 或断言失败时抛出。
    """

    temp_paths = _install_recording_converter_dependencies(monkeypatch)
    real_reader = docling_process_converter._read_terminal_result
    validation_count = 0

    def read_after_close(
        *,
        output_path: Path,
        wait_result: ProcessWaitResult | None,
    ) -> docling_process_converter.DoclingConversionResult:
        """验证 handle close 已发生后委托真实 owner validator。

        :param output_path: child output path。
        :param wait_result: runtime terminal。
        :returns: 完整性验证结果。
        :raises docling_process_converter.DoclingConversionError: terminal 非法时抛出。
        """

        nonlocal validation_count
        validation_count += 1
        current_handle = _RecordingHandle.instances[validation_count - 1]
        assert current_handle.calls[-1] == "close"
        return real_reader(output_path=output_path, wait_result=wait_result)

    monkeypatch.setattr(
        docling_process_converter,
        "_read_terminal_result",
        read_after_close,
    )
    converter = docling_process_converter.ProcessDoclingConverter(xbrl_config=None)
    first, second = await asyncio.gather(
        converter.convert_to_json_bytes(
            _INPUT_BYTES,
            "annual-report.pdf",
            config=docling_process_converter.DEFAULT_FINS_DOCLING_CONVERSION_CONFIG,
            cancellation=None,
        ),
        converter.convert_to_json_bytes(
            _INPUT_BYTES,
            "annual-report.docx",
            config=docling_process_converter.DEFAULT_FINS_DOCLING_CONVERSION_CONFIG,
            cancellation=None,
        ),
    )

    assert first == second
    assert first.json_bytes == _OUTPUT_BYTES
    assert first.size == len(_OUTPUT_BYTES)
    assert first.sha256 == hashlib.sha256(_OUTPUT_BYTES).hexdigest()
    assert len(_RecordingHandle.instances) == 2
    target_paths = {
        cast(docling_process_converter._DoclingProcessTarget, handle.target).input_path
        for handle in _RecordingHandle.instances
    }
    assert len(target_paths) == 2
    assert validation_count == 2
    assert len(temp_paths) == 2
    assert all(not path.exists() for path in temp_paths)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "descriptor",
    (
        {"schema_version": 1, "status": "success", "size": True, "sha256": "0" * 64},
        {"schema_version": 1, "status": "success", "size": 0, "sha256": "0" * 64, "extra": 1},
        {"schema_version": 2, "status": "success", "size": 0, "sha256": "0" * 64},
        {"schema_version": 1, "status": "unknown", "size": 0, "sha256": "0" * 64},
        {
            "schema_version": 1,
            "status": "failure",
            "failure_kind": "cleanup",
            "message": "Docling conversion cleanup failed",
        },
    ),
)
async def test_converter_rejects_malformed_or_unknown_exact_descriptor(
    monkeypatch: pytest.MonkeyPatch,
    descriptor: dict[str, JsonValue],
) -> None:
    """未知 key/version/status/kind 与 bool-size 必须统一映射 IPC_PROTOCOL。

    :param monkeypatch: pytest 属性替换工具。
    :param descriptor: 本例非法 exact descriptor。
    :returns: ``None``。
    :raises Exception: conversion 断言失败时抛出。
    """

    _RecordingHandle.invoke_target = False
    _RecordingHandle.configured_wait_result = InterruptibleProcessCompleted(
        value=descriptor,
        exitcode=0,
    )
    _install_recording_converter_dependencies(monkeypatch)

    with pytest.raises(docling_process_converter.DoclingConversionError) as exc_info:
        await _convert_once()

    assert exc_info.value.kind is docling_process_converter.DoclingConversionFailureKind.IPC_PROTOCOL
    assert _only_recording_handle().calls[-1] == "close"


@pytest.mark.asyncio
async def test_converter_maps_exact_child_failure_after_runtime_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """child failure descriptor 必须在 runtime completed 后映射原 closed kind。

    :param monkeypatch: pytest 属性替换工具。
    :returns: ``None``。
    :raises Exception: conversion 断言失败时抛出。
    """

    _RecordingHandle.invoke_target = False
    _RecordingHandle.configured_wait_result = InterruptibleProcessCompleted(
        value={
            "schema_version": 1,
            "status": "failure",
            "failure_kind": "converter_execution",
            "message": "Docling conversion execution failed",
        },
        exitcode=0,
    )
    _install_recording_converter_dependencies(monkeypatch)

    with pytest.raises(docling_process_converter.DoclingConversionError) as exc_info:
        await _convert_once()

    assert exc_info.value.kind is docling_process_converter.DoclingConversionFailureKind.CONVERTER_EXECUTION
    assert exc_info.value.exit_code == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("terminal", "expected_kind", "expected_exit_code"),
    (
        (
            InterruptibleProcessFailed(
                error_type="process_exited_without_result",
                message="internal queue detail",
                exitcode=0,
            ),
            docling_process_converter.DoclingConversionFailureKind.IPC_PROTOCOL,
            0,
        ),
        (
            InterruptibleProcessFailed(
                error_type="process_exited_without_result",
                message="internal crash detail",
                exitcode=-signal.SIGKILL,
            ),
            docling_process_converter.DoclingConversionFailureKind.CHILD_CRASH,
            -signal.SIGKILL,
        ),
        (
            InterruptibleProcessCompleted(value={}, exitcode=-signal.SIGSEGV),
            docling_process_converter.DoclingConversionFailureKind.CHILD_CRASH,
            -signal.SIGSEGV,
        ),
    ),
)
async def test_converter_closes_clean_ipc_loss_and_abnormal_or_signal_crash_mapping(
    monkeypatch: pytest.MonkeyPatch,
    terminal: ProcessWaitResult,
    expected_kind: docling_process_converter.DoclingConversionFailureKind,
    expected_exit_code: int,
) -> None:
    """clean-exit IPC loss 与 abnormal/signal crash 只按可观察事实闭合。

    :param monkeypatch: pytest 属性替换工具。
    :param terminal: runtime terminal fact。
    :param expected_kind: 预期 public kind。
    :param expected_exit_code: 唯一保留的 child 诊断。
    :returns: ``None``。
    :raises Exception: conversion 断言失败时抛出。
    """

    _RecordingHandle.invoke_target = False
    _RecordingHandle.configured_wait_result = terminal
    _install_recording_converter_dependencies(monkeypatch)

    with pytest.raises(docling_process_converter.DoclingConversionError) as exc_info:
        await _convert_once()

    assert exc_info.value.kind is expected_kind
    assert exc_info.value.exit_code == expected_exit_code
    assert "internal" not in exc_info.value.safe_message


@pytest.mark.asyncio
async def test_converter_rejects_digest_mismatch_as_ipc_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """descriptor digest 与 output 不一致必须在 close 后映射 IPC_PROTOCOL。

    :param monkeypatch: pytest 属性替换工具。
    :returns: ``None``。
    :raises Exception: conversion 断言失败时抛出。
    """

    _install_recording_converter_dependencies(monkeypatch)
    _RecordingHandle.configured_wait_result = InterruptibleProcessCompleted(
        value={
            "schema_version": 1,
            "status": "success",
            "size": len(_OUTPUT_BYTES),
            "sha256": "0" * 64,
        },
        exitcode=0,
    )

    with pytest.raises(docling_process_converter.DoclingConversionError) as exc_info:
        await _convert_once()

    assert exc_info.value.kind is docling_process_converter.DoclingConversionFailureKind.IPC_PROTOCOL
    assert _only_recording_handle().calls[-1] == "close"


@pytest.mark.asyncio
@pytest.mark.parametrize("output_mode", ("missing", "size_mismatch"))
async def test_converter_rejects_missing_or_size_mismatched_output_as_ipc_protocol(
    monkeypatch: pytest.MonkeyPatch,
    output_mode: Literal["missing", "size_mismatch"],
) -> None:
    """success descriptor 的 output 缺失或 size 不符必须失败关闭。

    :param monkeypatch: pytest 属性替换工具。
    :param output_mode: 本例 output 故障类型。
    :returns: ``None``。
    :raises Exception: conversion 断言失败时抛出。
    """

    _install_recording_converter_dependencies(monkeypatch)
    if output_mode == "missing":
        _RecordingHandle.invoke_target = False
        descriptor_size = len(_OUTPUT_BYTES)
    else:
        descriptor_size = len(_OUTPUT_BYTES) + 1
    _RecordingHandle.configured_wait_result = InterruptibleProcessCompleted(
        value={
            "schema_version": 1,
            "status": "success",
            "size": descriptor_size,
            "sha256": hashlib.sha256(_OUTPUT_BYTES).hexdigest(),
        },
        exitcode=0,
    )

    with pytest.raises(docling_process_converter.DoclingConversionError) as exc_info:
        await _convert_once()

    assert exc_info.value.kind is docling_process_converter.DoclingConversionFailureKind.IPC_PROTOCOL
    assert exc_info.value.exit_code == 0
    assert _only_recording_handle().calls[-1] == "close"


@pytest.mark.asyncio
async def test_converter_mkdtemp_failure_is_ipc_without_handle_or_cleanup_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """temp 创建失败必须闭合为 IPC 且不创建可清理资源。

    :param monkeypatch: pytest 属性替换工具。
    :returns: ``None``。
    :raises Exception: conversion 断言失败时抛出。
    """

    creation_failure = OSError("temp root creation failed")
    cleanup_paths: list[Path] = []

    def failing_mkdtemp(*, prefix: str) -> str:
        """模拟 system temp 创建失败。

        :param prefix: production 固定 temp prefix。
        :returns: 永不返回。
        :raises OSError: 始终抛出固定创建异常。
        """

        assert prefix == docling_process_converter._DOCLING_TEMP_PREFIX
        raise creation_failure

    def recording_rmtree(path: Path) -> None:
        """记录理论上不应发生的 temp cleanup。

        :param path: production 尝试删除的 temp tree。
        :returns: ``None``。
        :raises Exception: 本函数不抛出异常。
        """

        cleanup_paths.append(path)

    monkeypatch.setattr(
        docling_process_converter,
        "InterruptibleProcessHandle",
        _RecordingHandle,
    )
    monkeypatch.setattr(docling_process_converter.tempfile, "mkdtemp", failing_mkdtemp)
    monkeypatch.setattr(docling_process_converter.shutil, "rmtree", recording_rmtree)

    with pytest.raises(docling_process_converter.DoclingConversionError) as exc_info:
        await _convert_once()

    assert exc_info.value.kind is docling_process_converter.DoclingConversionFailureKind.IPC_PROTOCOL
    assert exc_info.value.__cause__ is creation_failure
    assert _RecordingHandle.instances == []
    assert cleanup_paths == []


@pytest.mark.asyncio
async def test_converter_input_write_failure_is_ipc_and_removes_temp_without_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """input 写入失败必须闭合为 IPC 并删除已创建 temp。

    :param monkeypatch: pytest 属性替换工具。
    :returns: ``None``。
    :raises Exception: conversion 断言失败时抛出。
    """

    write_failure = OSError("input write failed")
    temp_paths = _install_recording_converter_dependencies(monkeypatch)

    def failing_write_bytes(path: Path, data: bytes) -> int:
        """模拟 invocation-local input 写入失败。

        :param path: production input path。
        :param data: 待写入的原始字节。
        :returns: 永不返回。
        :raises OSError: 始终抛出固定写入异常。
        """

        assert path.name == "input.bin"
        assert data == _INPUT_BYTES
        raise write_failure

    monkeypatch.setattr(Path, "write_bytes", failing_write_bytes)

    with pytest.raises(docling_process_converter.DoclingConversionError) as exc_info:
        await _convert_once()

    assert exc_info.value.kind is docling_process_converter.DoclingConversionFailureKind.IPC_PROTOCOL
    assert exc_info.value.__cause__ is write_failure
    assert _RecordingHandle.instances == []
    assert temp_paths and all(not path.exists() for path in temp_paths)


@pytest.mark.asyncio
async def test_converter_input_write_and_rmtree_failures_prioritize_cleanup_and_preserve_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """input 写入与 temp 删除同时失败时 CLEANUP 必须优先。

    :param monkeypatch: pytest 属性替换工具。
    :returns: ``None``。
    :raises Exception: conversion 断言失败时抛出。
    """

    write_failure = OSError("input write failed")
    cleanup_failure = OSError("temp cleanup failed after input write")
    temp_paths = _install_recording_converter_dependencies(monkeypatch)
    real_rmtree = docling_process_converter.shutil.rmtree

    def failing_write_bytes(path: Path, data: bytes) -> int:
        """模拟 invocation-local input 写入失败。

        :param path: production input path。
        :param data: 待写入的原始字节。
        :returns: 永不返回。
        :raises OSError: 始终抛出固定写入异常。
        """

        assert path.name == "input.bin"
        assert data == _INPUT_BYTES
        raise write_failure

    def failing_rmtree(path: Path) -> None:
        """模拟 input 写入失败后的 temp tree 删除失败。

        :param path: production temp tree。
        :returns: 永不返回。
        :raises OSError: 始终抛出固定 cleanup 异常。
        """

        assert path in temp_paths
        raise cleanup_failure

    monkeypatch.setattr(Path, "write_bytes", failing_write_bytes)
    monkeypatch.setattr(docling_process_converter.shutil, "rmtree", failing_rmtree)
    try:
        with pytest.raises(docling_process_converter.DoclingConversionError) as exc_info:
            await _convert_once()
    finally:
        for temp_path in temp_paths:
            if temp_path.exists():
                real_rmtree(temp_path)

    assert exc_info.value.kind is docling_process_converter.DoclingConversionFailureKind.CLEANUP
    assert exc_info.value.__cause__ is cleanup_failure
    ipc_failure = cleanup_failure.__cause__
    assert isinstance(ipc_failure, docling_process_converter.DoclingConversionError)
    assert ipc_failure.kind is docling_process_converter.DoclingConversionFailureKind.IPC_PROTOCOL
    assert ipc_failure.__cause__ is write_failure
    assert _RecordingHandle.instances == []
    assert temp_paths and all(not path.exists() for path in temp_paths)


@pytest.mark.asyncio
async def test_converter_very_early_cancel_creates_no_temp_or_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """入口处已取消必须在创建 temp/handle 前返回安全取消。

    :param monkeypatch: pytest 属性替换工具。
    :returns: ``None``。
    :raises Exception: conversion 断言失败时抛出。
    """

    temp_paths = _install_recording_converter_dependencies(monkeypatch)
    token = _MutableCancellationToken(cancelled=True)

    with pytest.raises(docling_process_converter.DoclingConversionCancelledError):
        await _convert_once(cancellation=token)

    assert temp_paths == []
    assert _RecordingHandle.instances == []


@pytest.mark.asyncio
async def test_converter_cancel_terminate_success_skips_kill_and_logs_closed_phases(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """terminate 成功时必须 close/temp-clean 后取消，并记录 kill_not_needed。

    :param monkeypatch: pytest 属性替换工具。
    :param caplog: pytest 日志捕获工具。
    :returns: ``None``。
    :raises Exception: conversion 断言失败时抛出。
    """

    token = _MutableCancellationToken()
    _RecordingHandle.cancellation_to_request = token
    temp_paths = _install_recording_converter_dependencies(monkeypatch)
    caplog.set_level(logging.INFO, logger=docling_process_converter.__name__)

    with pytest.raises(docling_process_converter.DoclingConversionCancelledError):
        await _convert_once(cancellation=token)

    handle = _only_recording_handle()
    assert "terminate" in handle.calls
    assert "kill" not in handle.calls
    assert handle.calls[-1] == "close"
    assert temp_paths and all(not path.exists() for path in temp_paths)
    phases = [
        cast(_CleanupLogRecord, record).cleanup_phase
        for record in caplog.records
        if record.name == docling_process_converter.__name__
    ]
    assert phases == [
        "child_started",
        "cancel_observed",
        "terminate_started",
        "terminate_completed",
        "kill_not_needed",
        "handle_close_started",
        "handle_close_completed",
        "temp_cleanup_completed",
        "cancelled_terminal_ready",
    ]
    for record in caplog.records:
        if record.name == docling_process_converter.__name__:
            assert cast(_CleanupLogRecord, record).monotonic_elapsed_seconds >= 0.0
            assert "input.bin" not in record.getMessage()


@pytest.mark.asyncio
async def test_converter_cancel_escalates_terminate_then_kill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """忽略 terminate 时必须按 terminate→kill→close 次序收口。

    :param monkeypatch: pytest 属性替换工具。
    :returns: ``None``。
    :raises Exception: conversion 断言失败时抛出。
    """

    token = _MutableCancellationToken()
    _RecordingHandle.cancellation_to_request = token
    _RecordingHandle.terminate_exited = False
    _install_recording_converter_dependencies(monkeypatch)

    with pytest.raises(docling_process_converter.DoclingConversionCancelledError):
        await _convert_once(cancellation=token)

    calls = _only_recording_handle().calls
    assert calls.index("terminate") < calls.index("kill") < calls.index("close")


@pytest.mark.asyncio
async def test_converter_terminate_failure_is_cleanup_with_failed_phase_and_full_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """terminate 普通异常必须记录 FAILED 并继续收口全部资源。

    :param monkeypatch: pytest 属性替换工具。
    :param caplog: pytest 日志捕获工具。
    :returns: ``None``。
    :raises Exception: conversion 断言失败时抛出。
    """

    token = _MutableCancellationToken()
    terminate_failure = RuntimeError("terminate primitive failed")
    _RecordingHandle.cancellation_to_request = token
    _RecordingHandle.terminate_failure = terminate_failure
    temp_paths = _install_recording_converter_dependencies(monkeypatch)
    caplog.set_level(logging.INFO, logger=docling_process_converter.__name__)

    with pytest.raises(docling_process_converter.DoclingConversionError) as exc_info:
        await _convert_once(cancellation=token)

    assert exc_info.value.kind is docling_process_converter.DoclingConversionFailureKind.CLEANUP
    assert exc_info.value.__cause__ is terminate_failure
    handle = _only_recording_handle()
    assert handle.calls.index("terminate") < handle.calls.index("close")
    assert "kill" not in handle.calls
    assert handle.calls[-1] == "close"
    assert temp_paths and all(not path.exists() for path in temp_paths)
    failed_phases = [
        cast(_CleanupLogRecord, record).cleanup_phase
        for record in caplog.records
        if record.name == docling_process_converter.__name__
        and cast(_CleanupLogRecord, record).cleanup_outcome == "failed"
    ]
    assert failed_phases == ["terminate_completed"]


@pytest.mark.asyncio
async def test_converter_kill_failure_is_cleanup_with_failed_phase_and_full_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """kill 普通异常必须记录 FAILED 并继续收口全部资源。

    :param monkeypatch: pytest 属性替换工具。
    :param caplog: pytest 日志捕获工具。
    :returns: ``None``。
    :raises Exception: conversion 断言失败时抛出。
    """

    token = _MutableCancellationToken()
    kill_failure = RuntimeError("kill primitive failed")
    _RecordingHandle.cancellation_to_request = token
    _RecordingHandle.terminate_exited = False
    _RecordingHandle.kill_failure = kill_failure
    temp_paths = _install_recording_converter_dependencies(monkeypatch)
    caplog.set_level(logging.INFO, logger=docling_process_converter.__name__)

    with pytest.raises(docling_process_converter.DoclingConversionError) as exc_info:
        await _convert_once(cancellation=token)

    assert exc_info.value.kind is docling_process_converter.DoclingConversionFailureKind.CLEANUP
    assert exc_info.value.__cause__ is kill_failure
    handle = _only_recording_handle()
    assert handle.calls.index("terminate") < handle.calls.index("kill")
    assert handle.calls.index("kill") < handle.calls.index("close")
    assert handle.calls[-1] == "close"
    assert temp_paths and all(not path.exists() for path in temp_paths)
    failed_phases = [
        cast(_CleanupLogRecord, record).cleanup_phase
        for record in caplog.records
        if record.name == docling_process_converter.__name__
        and cast(_CleanupLogRecord, record).cleanup_outcome == "failed"
    ]
    assert failed_phases == ["kill_completed"]


@pytest.mark.asyncio
async def test_converter_kill_still_alive_is_cleanup_not_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """kill 后仍存活的未知状态不得伪装成安全取消。

    :param monkeypatch: pytest 属性替换工具。
    :returns: ``None``。
    :raises Exception: conversion 断言失败时抛出。
    """

    token = _MutableCancellationToken()
    _RecordingHandle.cancellation_to_request = token
    _RecordingHandle.terminate_exited = False
    _RecordingHandle.kill_exited = False
    _install_recording_converter_dependencies(monkeypatch)

    with pytest.raises(docling_process_converter.DoclingConversionError) as exc_info:
        await _convert_once(cancellation=token)

    assert exc_info.value.kind is docling_process_converter.DoclingConversionFailureKind.CLEANUP


@pytest.mark.asyncio
async def test_converter_close_failure_overrides_success_and_temp_is_still_cleaned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """close 未完成必须覆盖成功，且 converter 仍尝试 temp cleanup。

    :param monkeypatch: pytest 属性替换工具。
    :returns: ``None``。
    :raises Exception: conversion 断言失败时抛出。
    """

    close_failure = RuntimeError("queue close failed")
    _RecordingHandle.close_failure = close_failure
    temp_paths = _install_recording_converter_dependencies(monkeypatch)

    with pytest.raises(docling_process_converter.DoclingConversionError) as exc_info:
        await _convert_once()

    assert exc_info.value.kind is docling_process_converter.DoclingConversionFailureKind.CLEANUP
    assert exc_info.value.__cause__ is close_failure
    assert temp_paths and all(not path.exists() for path in temp_paths)


@pytest.mark.asyncio
async def test_converter_temp_cleanup_failure_overrides_child_failure_and_preserves_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """temp cleanup 失败取得最高优先级，并保留此前 child failure 链。

    :param monkeypatch: pytest 属性替换工具。
    :returns: ``None``。
    :raises Exception: conversion 断言失败时抛出。
    """

    temp_paths = _install_recording_converter_dependencies(monkeypatch)
    _RecordingHandle.invoke_target = False
    _RecordingHandle.configured_wait_result = InterruptibleProcessFailed(
        error_type="crash",
        message="sensitive crash",
        exitcode=-signal.SIGKILL,
    )
    real_rmtree = docling_process_converter.shutil.rmtree
    cleanup_failure = OSError("temp cleanup failed")

    def failing_rmtree(path: Path) -> None:
        """模拟 temp tree 删除失败。

        :param path: production temp tree。
        :returns: 永不返回。
        :raises OSError: 始终抛出固定 cleanup failure。
        """

        _ = path
        raise cleanup_failure

    monkeypatch.setattr(docling_process_converter.shutil, "rmtree", failing_rmtree)
    try:
        with pytest.raises(docling_process_converter.DoclingConversionError) as exc_info:
            await _convert_once()
    finally:
        for temp_path in temp_paths:
            if temp_path.exists():
                real_rmtree(temp_path)

    assert exc_info.value.kind is docling_process_converter.DoclingConversionFailureKind.CLEANUP
    assert exc_info.value.__cause__ is cleanup_failure
    assert isinstance(cleanup_failure.__cause__, docling_process_converter.DoclingConversionError)
    assert cleanup_failure.__cause__.kind is docling_process_converter.DoclingConversionFailureKind.CHILD_CRASH


@pytest.mark.asyncio
async def test_converter_outer_cancellation_identity_survives_close_and_temp_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """wait 期间的外层取消必须完成 cleanup 后透传同一异常对象。

    :param monkeypatch: pytest 属性替换工具。
    :returns: ``None``。
    :raises Exception: conversion 断言失败时抛出。
    """

    outer_cancellation = asyncio.CancelledError("outer task cancelled")
    _RecordingHandle.invoke_target = False
    _RecordingHandle.configured_wait_result = outer_cancellation
    temp_paths = _install_recording_converter_dependencies(monkeypatch)

    with pytest.raises(asyncio.CancelledError) as exc_info:
        await _convert_once()

    assert exc_info.value is outer_cancellation
    assert _only_recording_handle().calls[-1] == "close"
    assert temp_paths and all(not path.exists() for path in temp_paths)


@pytest.mark.asyncio
async def test_converter_cancellation_during_close_preserves_identity_after_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """close waiter 被取消时必须继续等待同一 cleanup 并透传 identity。

    :param monkeypatch: pytest 属性替换工具。
    :returns: ``None``。
    :raises Exception: conversion 断言失败时抛出。
    """

    outer_cancellation = asyncio.CancelledError("cancel during close")
    _RecordingHandle.close_cancellation = outer_cancellation
    temp_paths = _install_recording_converter_dependencies(monkeypatch)

    with pytest.raises(asyncio.CancelledError) as exc_info:
        await _convert_once()

    assert exc_info.value is outer_cancellation
    assert _only_recording_handle().calls.count("close") == 2
    assert temp_paths and all(not path.exists() for path in temp_paths)


@pytest.mark.asyncio
async def test_converter_cleanup_failure_overrides_outer_cancellation_and_preserves_identity_in_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """outer cancellation 与 cleanup 同时发生时 CLEANUP 优先且保留取消 identity。

    :param monkeypatch: pytest 属性替换工具。
    :returns: ``None``。
    :raises Exception: conversion 断言失败时抛出。
    """

    outer_cancellation = asyncio.CancelledError("outer task cancelled")
    close_failure = RuntimeError("handle close failed")
    _RecordingHandle.invoke_target = False
    _RecordingHandle.configured_wait_result = outer_cancellation
    _RecordingHandle.close_failure = close_failure
    _install_recording_converter_dependencies(monkeypatch)

    with pytest.raises(docling_process_converter.DoclingConversionError) as exc_info:
        await _convert_once()

    assert exc_info.value.kind is docling_process_converter.DoclingConversionFailureKind.CLEANUP
    assert exc_info.value.__cause__ is close_failure
    assert close_failure.__cause__ is outer_cancellation


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="nested process-group cleanup requires POSIX")
async def test_converter_real_posix_group_kills_nested_descendant_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实 runtime terminate→kill 必须清理忽略 SIGTERM 的 nested group。

    :param tmp_path: marker 根目录。
    :param monkeypatch: pytest 属性与环境替换工具。
    :returns: ``None``。
    :raises Exception: process cleanup、marker 或断言失败时抛出。
    """

    monkeypatch.setenv(_NESTED_MARKER_ROOT_ENV, str(tmp_path))
    monkeypatch.setattr(
        docling_process_converter,
        "_DoclingProcessTarget",
        _IgnoringTerminateNestedTarget,
    )
    monkeypatch.setattr(
        docling_process_converter,
        "InterruptibleProcessHandle",
        _RecordingRealHandle,
    )
    monkeypatch.setattr(
        docling_process_converter,
        "_DOCLING_TERMINATE_GRACE_SECONDS",
        _TEST_TERMINATE_GRACE_SECONDS,
    )
    monkeypatch.setattr(
        docling_process_converter,
        "_DOCLING_KILL_GRACE_SECONDS",
        _TEST_KILL_GRACE_SECONDS,
    )
    temp_paths = _record_temp_paths(monkeypatch)
    parent_marker = tmp_path / _PARENT_PID_FILE
    nested_marker = tmp_path / _NESTED_PID_FILE
    token: CancellationToken = _MarkerCancellationToken(parent_marker)

    with pytest.raises(docling_process_converter.DoclingConversionCancelledError):
        await asyncio.wait_for(
            _convert_once(cancellation=token),
            timeout=_PROCESS_READY_DEADLINE_SECONDS,
        )

    parent_pid = int(parent_marker.read_text(encoding="utf-8"))
    nested_pid = int(nested_marker.read_text(encoding="utf-8"))
    calls = _only_real_handle().calls
    assert calls.index("terminate") < calls.index("kill") < calls.index("close")
    assert await _wait_for_pid_to_exit(parent_pid)
    assert await _wait_for_pid_to_exit(nested_pid)
    assert temp_paths and all(not path.exists() for path in temp_paths)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("input_bytes", "stream_name"),
    ((b"", "annual-report.pdf"), (_INPUT_BYTES, "   ")),
)
async def test_converter_rejects_invalid_contract_before_temp(
    monkeypatch: pytest.MonkeyPatch,
    input_bytes: bytes,
    stream_name: str,
) -> None:
    """空 bytes/name 必须在 child/IPC 之外直接 ValueError。

    :param monkeypatch: pytest 属性替换工具。
    :param input_bytes: 本例输入字节。
    :param stream_name: 本例输入名。
    :returns: ``None``。
    :raises Exception: 断言失败时抛出。
    """

    temp_paths = _install_recording_converter_dependencies(monkeypatch)
    with pytest.raises(ValueError):
        await docling_process_converter.ProcessDoclingConverter(xbrl_config=None).convert_to_json_bytes(
            input_bytes,
            stream_name,
            config=docling_process_converter.DEFAULT_FINS_DOCLING_CONVERSION_CONFIG,
            cancellation=None,
        )
    assert temp_paths == []
    assert _RecordingHandle.instances == []


def _target_in_temp(tmp_path: Path) -> docling_process_converter._DoclingProcessTarget:
    """构造拥有真实 input/output 文件的 production target。

    :param tmp_path: pytest 临时目录。
    :returns: production child target。
    :raises OSError: 输入文件写入失败时抛出。
    """

    input_path = tmp_path / "input.bin"
    input_path.write_bytes(_INPUT_BYTES)
    (tmp_path / "diagnostics").mkdir(mode=0o700)
    return docling_process_converter._DoclingProcessTarget(
        input_path=str(input_path),
        output_path=str(tmp_path / "output.json"),
        stream_name="annual-report.pdf",
        config=docling_process_converter.DEFAULT_FINS_DOCLING_CONVERSION_CONFIG,
    xbrl_input=None, sandbox_profile=None, diagnostics_directory=str(tmp_path / "diagnostics"))


async def _convert_once(
    *,
    cancellation: CancellationToken | None = None,
) -> docling_process_converter.DoclingConversionResult:
    """用默认 typed config 执行一次 shared converter。

    :param cancellation: 公共取消 token。
    :returns: 成功转换结果。
    :raises docling_process_converter.DoclingConversionCancelledError: 请求取消时抛出。
    :raises docling_process_converter.DoclingConversionError: conversion/cleanup 失败时抛出。
    :raises asyncio.CancelledError: 外层取消时透传。
    """

    return await docling_process_converter.ProcessDoclingConverter(xbrl_config=None).convert_to_json_bytes(
        _INPUT_BYTES,
        "annual-report.pdf",
        config=docling_process_converter.DEFAULT_FINS_DOCLING_CONVERSION_CONFIG,
        cancellation=cancellation,
    )


def _install_recording_converter_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> list[Path]:
    """安装 deterministic helper、handle 与 temp path observer。

    :param monkeypatch: pytest 属性替换工具。
    :returns: converter 创建的 temp tree 路径列表。
    :raises Exception: monkeypatch 或 temp 初始化失败时抛出。
    """

    monkeypatch.setattr(
        docling_process_converter,
        "convert_pdf_bytes_with_docling",
        _successful_convert,
    )
    monkeypatch.setattr(
        docling_process_converter,
        "InterruptibleProcessHandle",
        _RecordingHandle,
    )
    return _record_temp_paths(monkeypatch)


def _record_temp_paths(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """记录 converter 每次创建的真实 system-temp tree。

    :param monkeypatch: pytest 属性替换工具。
    :returns: 已创建 temp tree 路径列表。
    :raises OSError: system temp 创建失败时抛出。
    """

    temp_paths: list[Path] = []
    real_mkdtemp = docling_process_converter.tempfile.mkdtemp

    def recording_mkdtemp(*, prefix: str) -> str:
        """创建并记录一个真实 system-temp tree。

        :param prefix: production 固定 temp prefix。
        :returns: 创建后的绝对路径文本。
        :raises OSError: system temp 创建失败时抛出。
        """

        created = Path(real_mkdtemp(prefix=prefix))
        temp_paths.append(created.resolve(strict=True))
        return str(created)

    monkeypatch.setattr(
        docling_process_converter.tempfile,
        "mkdtemp",
        recording_mkdtemp,
    )
    return temp_paths


def _only_recording_handle() -> _RecordingHandle:
    """返回本测试唯一 deterministic handle。

    :returns: 唯一 handle。
    :raises AssertionError: handle 数量不是 1 时抛出。
    """

    assert len(_RecordingHandle.instances) == 1
    return _RecordingHandle.instances[0]


def _only_real_handle() -> _RecordingRealHandle:
    """返回本测试唯一真实 runtime handle wrapper。

    :returns: 唯一 handle wrapper。
    :raises AssertionError: handle 数量不是 1 时抛出。
    """

    assert len(_RecordingRealHandle.instances) == 1
    return _RecordingRealHandle.instances[0]


def _wait_for_marker(marker_path: Path, *, deadline_seconds: float) -> int:
    """在有界期限内等待 child readiness marker。

    :param marker_path: PID marker。
    :param deadline_seconds: 最长等待秒数。
    :returns: marker 中的 PID。
    :raises RuntimeError: marker 未按期出现时抛出。
    :raises OSError: marker 读取失败时抛出。
    :raises ValueError: marker 内容不是整数时抛出。
    """

    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        if marker_path.exists():
            marker_text = marker_path.read_text(encoding="utf-8").strip()
            if marker_text:
                return int(marker_text)
        time.sleep(_PROCESS_POLL_SECONDS)
    raise RuntimeError("process marker was not written before deadline")


async def _wait_for_pid_to_exit(pid: int) -> bool:
    """在有界期限内等待 PID 消失。

    :param pid: 待观察 PID。
    :returns: PID 已不存在返回 ``True``。
    :raises Exception: 本函数不抛出异常。
    """

    deadline = time.monotonic() + _PROCESS_EXIT_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        if not _pid_exists(pid):
            return True
        await asyncio.sleep(_PROCESS_POLL_SECONDS)
    return not _pid_exists(pid)


def _pid_exists(pid: int) -> bool:
    """判断 PID 是否仍存在。

    :param pid: 待检查 PID。
    :returns: PID 存在或无权确认时返回 ``True``。
    :raises Exception: 本函数闭合系统查询异常。
    """

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@dataclass
class _XbrlBackendObservation:
    """合成 backend 生命周期计数；不证明 Arelle 模型关闭。"""

    unload_calls: int = 0

    def unload(self) -> None:
        """参数：无；返回：无；异常：无，记录 owner 调用。"""
        self.unload_calls += 1


@dataclass
class _XbrlWorkerObservation:
    """用真实结果类型注入合成状态，仅证明 worker 控制流。"""

    result: ConversionResult
    prepared: PreparedXbrlInput
    raise_execution: bool
    dispatch_calls: int = 0
    release_calls: int = 0

    def convert(self, input_bytes: bytes, *, stream_name: str, xbrl_input: PreparedXbrlInput) -> ConversionResult:
        """参数：输入/名称/快照；返回：注入结果；异常：指定 execution 场景时抛出。"""
        assert input_bytes == _INPUT_BYTES and stream_name == 'synthetic.xml'
        assert xbrl_input is self.prepared
        self.dispatch_calls += 1
        if self.raise_execution:
            raise RuntimeError('synthetic execution failure before result ownership')
        return self.result

    def release(self, result: ConversionResult) -> None:
        """参数：持有结果；返回：无；异常：错结果或真实 helper 失败时透传。"""
        assert result is self.result
        self.release_calls += 1
        docling_runtime.unload_xbrl_conversion(result)


def _forbidden_xbrl_pdf_dispatch(
    raw_bytes: bytes, *, stream_name: str, do_ocr: bool, do_table_structure: bool,
    table_mode: str, do_cell_matching: bool,
) -> ConversionResult:
    """参数：PDF 调用参数；返回：永不返回；异常：XBRL 路由误调用 PDF 时失败。"""
    raise AssertionError('XBRL must not dispatch PDF')


def _xbrl_export_failure(document: DoclingDocument) -> dict[str, JsonValue]:
    """参数：真实 document 类型；返回：永不返回；异常：合成 export 故障。"""
    raise RuntimeError('synthetic export failure')


@pytest.mark.parametrize('case', ['success', 'status', 'errors', 'export', 'raises'])
def test_xbrl_worker_dispatch_classification_and_owned_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    case: Literal['success', 'status', 'errors', 'export', 'raises'],
) -> None:
    """参数：独占根/注入工具/合成场景；返回：无；异常：dispatch、分类、释放次数错误时失败。"""
    config, _, _ = _deployment(tmp_path)
    prepared = docling_process_converter.prepare_xbrl_input(
        _loaded(config, tmp_path / 'workspace'), snapshot_root=tmp_path / 'snapshot',
        writable_root=tmp_path / 'work', stream_name='synthetic.xml',
    )
    input_path = tmp_path / 'input.bin'
    output_path = prepared.writable_root / 'output.json'
    input_path.write_bytes(_INPUT_BYTES)
    diagnostics = prepared.writable_root / 'diagnostics'; diagnostics.mkdir(mode=0o700)
    target = docling_process_converter._DoclingProcessTarget(str(input_path), str(output_path), 'synthetic.xml',
        docling_process_converter.DEFAULT_FINS_DOCLING_CONVERSION_CONFIG, prepared, 'synthetic-profile', str(diagnostics))
    observation_path = tmp_path / 'observation.json'
    descriptor = _run_xbrl_spawn(_XbrlSpawnProbe(target, case, str(observation_path)))
    observation = json.loads(observation_path.read_text())
    assert observation == {'dispatch': 1, 'release': 0 if case == 'raises' else 1, 'unload': 0 if case == 'raises' else 1}
    terminal = InterruptibleProcessCompleted(value=descriptor, exitcode=0)
    if case == 'success':
        public = docling_process_converter._read_terminal_result(output_path=output_path, wait_result=terminal)
        assert public.json_bytes == output_path.read_bytes()
    else:
        kind = (docling_process_converter.DoclingConversionFailureKind.RESULT_SERIALIZATION
                if case == 'export' else docling_process_converter.DoclingConversionFailureKind.CONVERTER_EXECUTION)
        assert descriptor == docling_process_converter._failure_descriptor(kind)
        assert not output_path.exists()
        with pytest.raises(docling_process_converter.DoclingConversionError) as error:
            docling_process_converter._read_terminal_result(output_path=output_path, wait_result=terminal)
        assert error.value.kind is kind and error.value.exit_code == 0


def _observe_synthetic_policy(profile: str) -> None:
    """参数：合成策略标签；返回：无；异常：非预期标签时断言失败；不施加内核策略。"""
    assert profile == 'synthetic-profile'


@dataclass(frozen=True, slots=True)
class _XbrlSpawnProbe:
    """独立 worker 内合成 XBRL 状态与真实 owner 释放观察。"""
    target: docling_process_converter._DoclingProcessTarget
    case: str
    observation_path: str

    def __call__(self) -> JsonValue:
        """参数：无；返回：原 descriptor；异常：owner 断言失败传播。"""
        patch = pytest.MonkeyPatch()
        backend = _XbrlBackendObservation()
        in_doc = InputDocument.model_construct(file=Path(self.target.input_path), document_hash=hashlib.sha256(_INPUT_BYTES).hexdigest(), valid=True, format=InputFormat.XML_XBRL)
        in_doc._backend = cast(AbstractDocumentBackend, backend)
        errors = [ErrorItem(component_type=DoclingComponentType.DOCUMENT_BACKEND, module_name='synthetic', error_message='synthetic content error')] if self.case == 'errors' else []
        result = ConversionResult(input=in_doc, status=ConversionStatus.FAILURE if self.case == 'status' else ConversionStatus.SUCCESS, errors=errors, document=DoclingDocument(name='synthetic-control-flow'))
        assert self.target.xbrl_input is not None
        observed = _XbrlWorkerObservation(result, self.target.xbrl_input, self.case == 'raises')
        patch.setattr(docling_process_converter, 'convert_xbrl_bytes_with_docling', observed.convert)
        patch.setattr(docling_process_converter, 'convert_pdf_bytes_with_docling', _forbidden_xbrl_pdf_dispatch)
        patch.setattr(docling_process_converter, 'unload_xbrl_conversion', observed.release)
        patch.setattr(docling_process_converter, 'apply_macos_sandbox', _observe_synthetic_policy)
        if self.case == 'export': patch.setattr(DoclingDocument, 'export_to_dict', _xbrl_export_failure)
        try:
            descriptor = self.target()
            Path(self.observation_path).write_text(json.dumps({'dispatch': observed.dispatch_calls, 'release': observed.release_calls, 'unload': backend.unload_calls}))
            return descriptor
        finally:
            patch.undo()


def _xbrl_result_entry(probe: InterruptibleProcessTarget, queue: multiprocessing.queues.Queue[JsonValue]) -> None:
    """参数：probe/测试队列；返回：无；异常：owner 失败传播。"""
    queue.put(probe())


def _run_xbrl_spawn(probe: InterruptibleProcessTarget) -> JsonValue:
    """参数：显式合成状态 probe；返回：真实 spawn descriptor；异常：timeout 或异常终态失败。"""
    context = multiprocessing.get_context('spawn')
    queue: multiprocessing.queues.Queue[JsonValue] = context.Queue()
    worker = context.Process(target=_xbrl_result_entry, args=(probe, queue))
    worker.start()
    try:
        result = queue.get(timeout=30); worker.join(30); assert worker.exitcode == 0
        return result
    finally:
        if worker.is_alive(): worker.kill(); worker.join()
        worker.close(); queue.close(); queue.join_thread()


class _DiagnosticRecordingHandle(_RecordingHandle):
    """父状态机替身仍在真实 spawn 内产生 installed/native 诊断。"""
    def start(self) -> None:
        """参数：无；返回：记录原 descriptor；异常：真实 spawn 失败传播。"""
        self.calls.append('start')
        self._target_result = _run_target_spawn(cast(docling_process_converter._DoclingProcessTarget, self.target), 'leak')


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['missing', 'json', 'footer', 'read', 'projection', 'write', 'flush', 'format', 'missing_format'])
@pytest.mark.parametrize('outcome', ['success', 'failure', 'cancel'])
async def test_diagnostic_failure_never_rewrites_verified_outcome(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        fault: str, outcome: str, capfd: pytest.CaptureFixture[str]) -> None:
    """参数：诊断坏路径/原终态/双流；返回：无；异常：普通 sidecar/真实投递错误覆盖业务时失败。"""
    import io
    from tests.runtime.test_log import _DiagnosticFaultStream, _DiagnosticFaultFormatter
    from dayu.runtime.log import LogLevel, configure
    temp_paths = _install_recording_converter_dependencies(monkeypatch)
    monkeypatch.setattr(docling_process_converter, 'InterruptibleProcessHandle', _DiagnosticRecordingHandle)
    error = OSError('diagnostic only')
    stream = _DiagnosticFaultStream(fault, error) if fault in ('write', 'flush') else io.StringIO()
    # WARNING owner 的准入保留真实源 WARNING，cleanup INFO 属既有 ordinary policy 被拒绝。
    configure(level=LogLevel.WARNING, stream=stream)
    if fault == 'format': logging.getLogger('dayu').handlers[0].setFormatter(_DiagnosticFaultFormatter(error))
    if fault == 'missing_format': logging.getLogger('dayu').handlers[0].setFormatter(logging.Formatter('%(missing_required_field)s'))
    original_close = _RecordingHandle.close
    async def close_and_fault(self: _RecordingHandle, kill_grace_seconds: float) -> None:
        """参数：handle/预算；返回：关闭后注入媒体缺口；异常：原 cleanup 错误传播。"""
        await original_close(self, kill_grace_seconds=kill_grace_seconds)
        target = cast(docling_process_converter._DoclingProcessTarget, self.target)
        records = Path(target.diagnostics_directory) / 'records.jsonl'
        if fault == 'missing': records.unlink()
        elif fault == 'json': records.write_bytes(b'bad\n')
        elif fault == 'footer': records.write_bytes(records.read_bytes().rsplit(b'\n', 2)[0] + b'\n')
    monkeypatch.setattr(_DiagnosticRecordingHandle, 'close', close_and_fault)
    if fault == 'read':
        def fail_read(directory: Path, *, require_complete: bool) -> list[JsonValue]:
            """参数：目录/策略；返回：永不返回；异常：普通 read fault。"""
            raise OSError('read fault')
        monkeypatch.setattr(docling_process_converter, 'read_process_diagnostics', fail_read)
    if fault == 'projection':
        def fail_projection(diagnostic: JsonValue) -> bool:
            """参数：投影；返回：永不返回；异常：普通投影 fault。"""
            raise ValueError('projection fault')
        monkeypatch.setattr(docling_process_converter, 'emit_process_log_diagnostic', fail_projection)
    token: _MutableCancellationToken | None = None
    if outcome == 'failure':
        _RecordingHandle.configured_wait_result = InterruptibleProcessCompleted(value=docling_process_converter._failure_descriptor(docling_process_converter.DoclingConversionFailureKind.CONVERTER_EXECUTION), exitcode=0)
    if outcome == 'cancel':
        token = _MutableCancellationToken(); _RecordingHandle.cancellation_to_request = token
    try:
        if outcome == 'success': assert (await _convert_once()).json_bytes == _OUTPUT_BYTES
        elif outcome == 'failure':
            with pytest.raises(docling_process_converter.DoclingConversionError) as caught: await _convert_once()
            assert caught.value.kind is docling_process_converter.DoclingConversionFailureKind.CONVERTER_EXECUTION
        else:
            with pytest.raises(docling_process_converter.DoclingConversionCancelledError): await _convert_once(cancellation=token)
    finally:
        if isinstance(stream, _DiagnosticFaultStream): stream.phase = 'none'
    assert temp_paths and all(not path.exists() for path in temp_paths)
    public = capfd.readouterr(); assert public.out == public.err == ''


@pytest.mark.asyncio
@pytest.mark.parametrize('control', ['keyboard', 'exit', 'cancel', 'generator'])
@pytest.mark.parametrize('phase', ['format', 'write', 'flush', 'release'])
async def test_forward_control_flow_cleanup_preserves_object(monkeypatch: pytest.MonkeyPatch, control: str, phase: str) -> None:
    """参数：原控制流；返回：无；异常：诊断控制流吞掉/替换对象或 temp 未清理失败。"""
    from tests.runtime.test_log import _DiagnosticFaultFormatter, _DiagnosticFaultStream, _DiagnosticReleaseFaultHandler
    from dayu.runtime.log import LogLevel, configure
    import io
    error = {'keyboard': KeyboardInterrupt(), 'exit': SystemExit(8), 'cancel': asyncio.CancelledError(), 'generator': GeneratorExit()}[control]
    temp_paths = _install_recording_converter_dependencies(monkeypatch)
    monkeypatch.setattr(docling_process_converter, 'InterruptibleProcessHandle', _DiagnosticRecordingHandle)
    stream = _DiagnosticFaultStream(phase, error) if phase in ('write', 'flush') else io.StringIO()
    configure(level=LogLevel.WARNING, stream=stream)
    namespace = logging.getLogger('dayu'); owner = namespace.handlers[0]
    release_owner: _DiagnosticReleaseFaultHandler | None = None
    if phase == 'format': owner.setFormatter(_DiagnosticFaultFormatter(error))
    if phase == 'release':
        release_owner = _DiagnosticReleaseFaultHandler(stream=stream)
        release_owner.setLevel(owner.level)
        for admission in owner.filters: release_owner.addFilter(admission)
        release_owner.setFormatter(owner.formatter); release_owner.release_error = error
        namespace.handlers[:] = [release_owner]
    try:
        with pytest.raises(BaseException) as caught: await _convert_once()
        assert caught.value is error and all(not path.exists() for path in temp_paths)
    finally:
        if isinstance(stream, _DiagnosticFaultStream): stream.phase = 'none'
        if release_owner is not None: release_owner.release_error = None
