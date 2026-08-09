"""CN Docling production process runner 的进程、完整性与 cleanup 测试。"""

from __future__ import annotations

import asyncio
import hashlib
import os
import pickle
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.fins.pipelines import cn_docling_process
from dayu.fins.pipelines.cn_download_models import CnDownloadCancelledError
from dayu.runtime.interruptible_process import (
    InterruptibleProcessHandle,
    InterruptibleProcessTarget,
    ProcessInterruptResult,
    ProcessWaitResult,
)

_MARKER_ROOT_ENV = "DAYU_TEST_CN_DOCLING_MARKER_ROOT"
_PARENT_PID_FILE = "parent.pid"
_NESTED_PID_FILE = "nested.pid"
_PROCESS_READY_DEADLINE_SECONDS = 5.0
_PROCESS_EXIT_DEADLINE_SECONDS = 5.0
_PROCESS_POLL_SECONDS = 0.02
_TEST_KILL_GRACE_SECONDS = 1.0
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


@dataclass(frozen=True, slots=True)
class _SuccessfulDoclingTarget:
    """写入固定 JSON 并返回真实 size/digest descriptor 的 spawn target。"""

    input_path: str
    output_path: str
    stream_name: str

    def __call__(self) -> JsonValue:
        """验证 parent input 并写入固定 child output。

        Returns:
            size/digest descriptor。

        Raises:
            AssertionError: parent input 或 stream name 不符合测试契约时抛出。
            OSError: 输入输出读写失败时抛出。
        """

        assert Path(self.input_path).read_bytes() == b"pdf-input"
        assert self.stream_name == "filing.pdf"
        output_bytes = b'{"converted":true}'
        Path(self.output_path).write_bytes(output_bytes)
        return {
            "size": len(output_bytes),
            "sha256": hashlib.sha256(output_bytes).hexdigest(),
        }


@dataclass(frozen=True, slots=True)
class _FailingDoclingTarget:
    """在真实 spawned child 中抛出固定异常的 target。"""

    input_path: str
    output_path: str
    stream_name: str

    def __call__(self) -> JsonValue:
        """抛出固定 conversion failure。

        Returns:
            永不返回。

        Raises:
            RuntimeError: 始终抛出。
        """

        _ = (self.input_path, self.output_path, self.stream_name)
        raise RuntimeError("child conversion failed")


@dataclass(frozen=True, slots=True)
class _DigestMismatchDoclingTarget:
    """写入输出但返回错误 digest 的 spawn target。"""

    input_path: str
    output_path: str
    stream_name: str

    def __call__(self) -> JsonValue:
        """写入 child output 并返回不匹配 descriptor。

        Returns:
            digest 故意错误的 descriptor。

        Raises:
            OSError: child output 写入失败时抛出。
        """

        _ = (self.input_path, self.stream_name)
        output_bytes = b'{"converted":true}'
        Path(self.output_path).write_bytes(output_bytes)
        return {"size": len(output_bytes), "sha256": "0" * 64}


@dataclass(frozen=True, slots=True)
class _IgnoringTerminateNestedTarget:
    """启动嵌套进程并忽略 SIGTERM 的 cancellation target。"""

    input_path: str
    output_path: str
    stream_name: str

    def __call__(self) -> JsonValue:
        """等待嵌套 child ready，发布 parent PID 后阻塞。

        Returns:
            永不正常返回。

        Raises:
            RuntimeError: marker root 缺失或 nested child 未在期限内 ready。
            OSError: marker 读写或 nested process 启动失败时抛出。
        """

        _ = (self.input_path, self.output_path, self.stream_name)
        marker_root_text = os.environ.get(_MARKER_ROOT_ENV)
        if marker_root_text is None:
            raise RuntimeError("test marker root is unavailable")
        marker_root = Path(marker_root_text)
        nested_marker = marker_root / _NESTED_PID_FILE
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        subprocess.Popen(
            [sys.executable, "-c", _NESTED_PROCESS_SCRIPT, str(nested_marker)],
            close_fds=True,
        )
        _wait_for_marker(nested_marker, deadline_seconds=_PROCESS_READY_DEADLINE_SECONDS)
        (marker_root / _PARENT_PID_FILE).write_text(str(os.getpid()), encoding="utf-8")
        signal.pause()
        raise RuntimeError("signal.pause returned unexpectedly")


class _RecordingInterruptibleProcessHandle:
    """委托真实 helper 并记录 runner 调用顺序的测试 handle。"""

    instances: ClassVar[list[_RecordingInterruptibleProcessHandle]] = []

    def __init__(self, target: InterruptibleProcessTarget) -> None:
        """初始化真实 handle 与调用记录。

        Args:
            target: 可 pickle 的 spawned child target。

        Returns:
            无。

        Raises:
            OSError: multiprocessing queue/process 初始化失败时抛出。
        """

        self._handle = InterruptibleProcessHandle(target)
        self.calls: list[str] = []
        self.instances.append(self)

    def start(self) -> None:
        """记录并启动真实 child。

        Returns:
            无。

        Raises:
            RuntimeError: helper 拒绝启动时抛出。
        """

        self.calls.append("start")
        self._handle.start()

    async def wait(self, timeout_seconds: float | None) -> ProcessWaitResult:
        """记录并等待真实 child。

        Args:
            timeout_seconds: 有界等待时间。

        Returns:
            helper wait result。

        Raises:
            ValueError: timeout 非法时抛出。
        """

        self.calls.append("wait")
        return await self._handle.wait(timeout_seconds)

    async def terminate(self, grace_seconds: float) -> ProcessInterruptResult:
        """记录并 terminate 真实 child/process group。

        Args:
            grace_seconds: terminate 后的有界宽限。

        Returns:
            helper interrupt result。

        Raises:
            ValueError: grace 非法时抛出。
        """

        self.calls.append("terminate")
        return await self._handle.terminate(grace_seconds)

    async def kill(self, grace_seconds: float) -> ProcessInterruptResult:
        """记录并 kill 真实 child/process group。

        Args:
            grace_seconds: kill 后的有界宽限。

        Returns:
            helper interrupt result。

        Raises:
            ValueError: grace 非法时抛出。
        """

        self.calls.append("kill")
        return await self._handle.kill(grace_seconds)

    async def close(self, *, kill_grace_seconds: float) -> None:
        """记录并关闭真实 handle/queue。

        Args:
            kill_grace_seconds: close 的有界 kill 宽限。

        Returns:
            无。

        Raises:
            RuntimeError: helper 未能完成 cleanup 时抛出。
        """

        self.calls.append("close")
        await self._handle.close(kill_grace_seconds=kill_grace_seconds)


@pytest.fixture(autouse=True)
def _reset_recording_handles() -> None:
    """每个测试前清空 process handle 调用证据。

    Returns:
        无。

    Raises:
        无。
    """

    _RecordingInterruptibleProcessHandle.instances.clear()


@pytest.mark.asyncio
async def test_process_runner_success_uses_real_start_closes_before_validation_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """成功路径必须真实 spawn，close 后验证并删除每次 temp tree。"""

    temp_paths = _install_process_fakes(
        monkeypatch,
        target_type=_SuccessfulDoclingTarget,
    )
    result = await cn_docling_process.ProcessCnDoclingConversionRunner().convert_pdf_to_docling_json(
        b"pdf-input",
        "filing.pdf",
        cancellation_checker=_never_cancelled,
    )

    assert result == b'{"converted":true}'
    handle = _only_recorded_handle()
    assert handle.calls[0] == "start"
    assert handle.calls[-1] == "close"
    assert temp_paths and all(not path.exists() for path in temp_paths)
    assert tmp_path.exists()


@pytest.mark.asyncio
async def test_process_runner_child_failure_closes_and_cleans_temp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """child failure 必须映射安全异常并仍完成 close/temp cleanup。"""

    temp_paths = _install_process_fakes(monkeypatch, target_type=_FailingDoclingTarget)

    with pytest.raises(RuntimeError, match="child conversion failed"):
        await cn_docling_process.ProcessCnDoclingConversionRunner().convert_pdf_to_docling_json(
            b"pdf-input",
            "filing.pdf",
            cancellation_checker=_never_cancelled,
        )

    handle = _only_recorded_handle()
    assert handle.calls[0] == "start"
    assert handle.calls[-1] == "close"
    assert temp_paths and all(not path.exists() for path in temp_paths)


@pytest.mark.asyncio
async def test_process_runner_rejects_digest_mismatch_after_handle_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """size/digest 完整性验证必须发生在 handle close 之后。"""

    temp_paths = _install_process_fakes(
        monkeypatch,
        target_type=_DigestMismatchDoclingTarget,
    )
    validation_observed = False
    real_validator = cn_docling_process._read_and_validate_output

    def validate_after_close(
        *,
        output_path: Path,
        wait_result: ProcessWaitResult,
    ) -> bytes:
        """在真实完整性验证前断言 handle 已 close。

        Args:
            output_path: child output 路径。
            wait_result: helper terminal wait result。

        Returns:
            验证通过的 bytes。

        Raises:
            RuntimeError: 顺序或完整性校验失败时抛出。
            OSError: output 读取失败时抛出。
        """

        nonlocal validation_observed
        validation_observed = True
        assert _only_recorded_handle().calls[-1] == "close"
        return real_validator(output_path=output_path, wait_result=wait_result)

    monkeypatch.setattr(cn_docling_process, "_read_and_validate_output", validate_after_close)

    with pytest.raises(RuntimeError, match="digest mismatch"):
        await cn_docling_process.ProcessCnDoclingConversionRunner().convert_pdf_to_docling_json(
            b"pdf-input",
            "filing.pdf",
            cancellation_checker=_never_cancelled,
        )

    assert validation_observed
    assert temp_paths and all(not path.exists() for path in temp_paths)


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="nested process-group cleanup requires POSIX")
async def test_process_runner_cancel_escalates_terminate_to_kill_and_removes_nested_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """取消必须 terminate→kill 整个 nested group，close 后无 PID/temp/late output。"""

    monkeypatch.setenv(_MARKER_ROOT_ENV, str(tmp_path))
    monkeypatch.setattr(cn_docling_process, "_DOCLING_TERMINATE_GRACE_SECONDS", 0.05)
    monkeypatch.setattr(
        cn_docling_process,
        "_DOCLING_KILL_GRACE_SECONDS",
        _TEST_KILL_GRACE_SECONDS,
    )
    temp_paths = _install_process_fakes(
        monkeypatch,
        target_type=_IgnoringTerminateNestedTarget,
    )
    parent_marker = tmp_path / _PARENT_PID_FILE
    nested_marker = tmp_path / _NESTED_PID_FILE

    with pytest.raises(CnDownloadCancelledError):
        await asyncio.wait_for(
            cn_docling_process.ProcessCnDoclingConversionRunner().convert_pdf_to_docling_json(
                b"pdf-input",
                "filing.pdf",
                cancellation_checker=lambda: parent_marker.exists(),
            ),
            timeout=_PROCESS_READY_DEADLINE_SECONDS,
        )

    parent_pid = int(parent_marker.read_text(encoding="utf-8"))
    nested_pid = int(nested_marker.read_text(encoding="utf-8"))
    handle = _only_recorded_handle()
    assert "terminate" in handle.calls
    assert "kill" in handle.calls
    assert handle.calls.index("terminate") < handle.calls.index("kill") < handle.calls.index("close")
    assert await _wait_for_pid_to_exit(parent_pid)
    assert await _wait_for_pid_to_exit(nested_pid)
    assert temp_paths and all(not path.exists() for path in temp_paths)


@pytest.mark.asyncio
async def test_process_runner_very_early_cancel_does_not_create_temp_or_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """启动前取消必须在 temp tree 和 process handle 创建前收口。"""

    temp_paths = _install_process_fakes(monkeypatch, target_type=_SuccessfulDoclingTarget)

    with pytest.raises(CnDownloadCancelledError):
        await cn_docling_process.ProcessCnDoclingConversionRunner().convert_pdf_to_docling_json(
            b"pdf-input",
            "filing.pdf",
            cancellation_checker=_always_cancelled,
        )

    assert temp_paths == []
    assert _RecordingInterruptibleProcessHandle.instances == []


def test_production_process_target_is_pickleable_and_exports_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """production target 必须可 pickle，且 queue 结果只含 size/digest。"""

    input_path = tmp_path / "input.pdf"
    output_path = tmp_path / "output.json"
    input_path.write_bytes(b"pdf-input")
    target = cn_docling_process._CnDoclingProcessTarget(
        input_path=str(input_path),
        output_path=str(output_path),
        stream_name="filing.pdf",
    )
    converter = _FakeDoclingConversion()

    def fake_convert(
        raw_bytes: bytes,
        *,
        stream_name: str,
        do_ocr: bool,
        do_table_structure: bool,
        table_mode: str,
        do_cell_matching: bool,
    ) -> _FakeDoclingConversion:
        """记录 production target 传给 Docling runtime 的参数。

        Args:
            raw_bytes: input PDF bytes。
            stream_name: 文件名。
            do_ocr: OCR 开关。
            do_table_structure: 表格结构开关。
            table_mode: 表格模式。
            do_cell_matching: 单元格匹配开关。

        Returns:
            固定 fake conversion。

        Raises:
            AssertionError: target 参数漂移时抛出。
        """

        assert raw_bytes == b"pdf-input"
        assert stream_name == "filing.pdf"
        assert do_ocr and do_table_structure and do_cell_matching
        assert table_mode == "accurate"
        return converter

    monkeypatch.setattr(cn_docling_process, "convert_pdf_bytes_with_docling", fake_convert)

    assert pickle.loads(pickle.dumps(target)) == target
    descriptor = target()
    output_bytes = output_path.read_bytes()
    assert descriptor == {
        "size": len(output_bytes),
        "sha256": hashlib.sha256(output_bytes).hexdigest(),
    }


class _FakeDoclingDocument:
    """production target 单元测试用 Docling document。"""

    def export_to_dict(self) -> dict[str, JsonValue]:
        """返回固定 JSON-like 文档。

        Returns:
            固定文档字典。

        Raises:
            无。
        """

        return {"converted": True}


@dataclass(frozen=True, slots=True)
class _FakeDoclingConversion:
    """production target 单元测试用 conversion result。"""

    document: _FakeDoclingDocument = _FakeDoclingDocument()


def _install_process_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    target_type: type[
        _SuccessfulDoclingTarget | _FailingDoclingTarget | _DigestMismatchDoclingTarget | _IgnoringTerminateNestedTarget
    ],
) -> list[Path]:
    """安装可真实 spawn 的 target、记录 handle 与 temp path observer。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
        target_type: 本次 runner 需要构造的 top-level target 类型。

    Returns:
        runner 已创建的 temp tree 路径列表。

    Raises:
        OSError: system temp 目录创建失败时抛出。
    """

    temp_paths: list[Path] = []
    real_mkdtemp = cn_docling_process.tempfile.mkdtemp

    def recording_mkdtemp(*, prefix: str) -> str:
        """创建真实 system-temp 目录并记录路径。

        Args:
            prefix: production runner 传入的固定前缀。

        Returns:
            真实 temp 目录路径。

        Raises:
            OSError: temp 目录创建失败时抛出。
        """

        created = Path(real_mkdtemp(prefix=prefix))
        temp_paths.append(created)
        return str(created)

    monkeypatch.setattr(cn_docling_process, "_CnDoclingProcessTarget", target_type)
    monkeypatch.setattr(
        cn_docling_process,
        "InterruptibleProcessHandle",
        _RecordingInterruptibleProcessHandle,
    )
    monkeypatch.setattr(cn_docling_process.tempfile, "mkdtemp", recording_mkdtemp)
    return temp_paths


def _only_recorded_handle() -> _RecordingInterruptibleProcessHandle:
    """返回本测试唯一的记录 handle。

    Returns:
        唯一 handle。

    Raises:
        AssertionError: handle 数量不是 1 时抛出。
    """

    assert len(_RecordingInterruptibleProcessHandle.instances) == 1
    return _RecordingInterruptibleProcessHandle.instances[0]


def _never_cancelled() -> bool:
    """返回未取消。

    Returns:
        始终返回 ``False``。

    Raises:
        无。
    """

    return False


def _always_cancelled() -> bool:
    """返回已取消。

    Returns:
        始终返回 ``True``。

    Raises:
        无。
    """

    return True


def _wait_for_marker(marker_path: Path, *, deadline_seconds: float) -> int:
    """在有界期限内等待跨进程 PID marker。

    Args:
        marker_path: PID marker 路径。
        deadline_seconds: 最长等待秒数。

    Returns:
        marker 中的 PID。

    Raises:
        RuntimeError: marker 未在期限内出现。
        OSError: marker 读取失败时抛出。
        ValueError: marker 不是整数时抛出。
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

    Args:
        pid: 待观察的进程 PID。

    Returns:
        PID 已不存在返回 ``True``。

    Raises:
        无。
    """

    deadline = time.monotonic() + _PROCESS_EXIT_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        if not _pid_exists(pid):
            return True
        await asyncio.sleep(_PROCESS_POLL_SECONDS)
    return not _pid_exists(pid)


def _pid_exists(pid: int) -> bool:
    """判断 PID 是否仍存在。

    Args:
        pid: 待检查 PID。

    Returns:
        PID 存在或无权确认时返回 ``True``。

    Raises:
        无。
    """

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
