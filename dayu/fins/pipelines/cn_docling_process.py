"""CN/HK 下载链路的 production Docling 子进程边界。

本模块只拥有单次 Docling conversion 的子进程、system-temp 目录、输出完整性
校验与有界 cleanup。业务 workflow 只消费 typed runner，不接触进程 handle、
临时路径或第三方 Docling 对象。
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from dayu.contracts.json_value import JsonValue
from dayu.documents.docling_runtime import (
    DoclingRuntimeInitializationError,
    convert_pdf_bytes_with_docling,
)
from dayu.fins.pipelines.cn_download_models import CnDownloadCancelledError
from dayu.runtime.interruptible_process import (
    InterruptibleProcessCompleted,
    InterruptibleProcessFailed,
    InterruptibleProcessHandle,
    InterruptibleProcessStillRunning,
    ProcessWaitResult,
)

_DOCLING_PROCESS_POLL_SECONDS: Final[float] = 0.05
_DOCLING_TERMINATE_GRACE_SECONDS: Final[float] = 2.0
_DOCLING_KILL_GRACE_SECONDS: Final[float] = 1.0
_DOCLING_TEMP_PREFIX: Final[str] = "dayu-cn-docling-"
_DOCLING_INPUT_FILE_NAME: Final[str] = "input.pdf"
_DOCLING_OUTPUT_FILE_NAME: Final[str] = "output.json"
_RESULT_SIZE_KEY: Final[str] = "size"
_RESULT_DIGEST_KEY: Final[str] = "sha256"
_SHA256_HEX_LENGTH: Final[int] = 64
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _CnDoclingProcessTarget:
    """可 pickle 的单次 Docling conversion 子进程目标。"""

    input_path: str
    output_path: str
    stream_name: str

    def __call__(self) -> JsonValue:
        """执行真实 Docling conversion 并写入 child-owned 输出文件。

        Returns:
            仅含输出大小与 SHA-256 的小型 JSON-like 结果。

        Raises:
            DoclingRuntimeInitializationError: Docling 依赖缺失或装配失败时抛出。
            RuntimeError: Docling conversion 或导出结构非法时抛出。
            OSError: 临时输入或输出读写失败时抛出。
        """

        pdf_bytes = Path(self.input_path).read_bytes()
        try:
            result = convert_pdf_bytes_with_docling(
                pdf_bytes,
                stream_name=self.stream_name,
                do_ocr=True,
                do_table_structure=True,
                table_mode="accurate",
                do_cell_matching=True,
            )
        except DoclingRuntimeInitializationError:
            raise
        except Exception as exc:
            raise RuntimeError("Docling conversion failed") from exc
        payload = cast(JsonValue, result.document.export_to_dict())
        if not isinstance(payload, Mapping):
            raise RuntimeError("Docling export payload is invalid")
        output_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        Path(self.output_path).write_bytes(output_bytes)
        return {
            _RESULT_SIZE_KEY: len(output_bytes),
            _RESULT_DIGEST_KEY: hashlib.sha256(output_bytes).hexdigest(),
        }


class ProcessCnDoclingConversionRunner:
    """使用 ``InterruptibleProcessHandle`` 的 production conversion runner。"""

    async def convert_pdf_to_docling_json(
        self,
        pdf_bytes: bytes,
        stream_name: str,
        *,
        cancellation_checker: Callable[[], bool],
    ) -> bytes:
        """在独立子进程中完成 PDF 到 Docling JSON 的转换。

        Args:
            pdf_bytes: 待转换 PDF 字节。
            stream_name: 不含目录的输入流名称。
            cancellation_checker: operation-scoped 取消检查器。

        Returns:
            child 退出、handle 关闭且 size/digest 校验通过后的 JSON bytes。

        Raises:
            CnDownloadCancelledError: 启动前或等待期间收到取消请求时抛出。
            ValueError: stream name 为空或包含路径分隔符时抛出。
            RuntimeError: child、handle cleanup 或输出校验失败时抛出。
            OSError: system-temp 输入或输出读写失败时抛出。
        """

        _validate_stream_name(stream_name)
        if cancellation_checker():
            raise CnDownloadCancelledError("操作已被取消")
        temp_root = Path(tempfile.mkdtemp(prefix=_DOCLING_TEMP_PREFIX))
        input_path = temp_root / _DOCLING_INPUT_FILE_NAME
        output_path = temp_root / _DOCLING_OUTPUT_FILE_NAME
        handle: InterruptibleProcessHandle | None = None
        handle_closed = False
        primary_error: BaseException | None = None
        result_bytes: bytes | None = None
        try:
            input_path.write_bytes(pdf_bytes)
            handle = InterruptibleProcessHandle(
                _CnDoclingProcessTarget(
                    input_path=str(input_path),
                    output_path=str(output_path),
                    stream_name=stream_name,
                )
            )
            handle.start()
            wait_result = await _wait_for_conversion(
                handle,
                cancellation_checker=cancellation_checker,
            )
            await handle.close(
                kill_grace_seconds=_DOCLING_KILL_GRACE_SECONDS,
            )
            handle_closed = True
            result_bytes = _read_and_validate_output(
                output_path=output_path,
                wait_result=wait_result,
            )
            if cancellation_checker():
                raise CnDownloadCancelledError("操作已被取消")
        except BaseException as exc:
            primary_error = exc
        finally:
            if handle is not None and not handle_closed:
                try:
                    await handle.close(
                        kill_grace_seconds=_DOCLING_KILL_GRACE_SECONDS,
                    )
                except BaseException as cleanup_error:
                    if primary_error is None:
                        primary_error = cleanup_error
                    else:
                        _log_cleanup_warning("handle_close", cleanup_error)
            try:
                shutil.rmtree(temp_root)
            except OSError as cleanup_error:
                _log_cleanup_warning("temp_tree", cleanup_error)
        if primary_error is not None:
            raise primary_error.with_traceback(primary_error.__traceback__)
        if result_bytes is None:
            raise RuntimeError("Docling conversion produced no validated output")
        return result_bytes


async def _wait_for_conversion(
    handle: InterruptibleProcessHandle,
    *,
    cancellation_checker: Callable[[], bool],
) -> ProcessWaitResult:
    """轮询 conversion child，并在取消时执行 terminate/kill 升级。

    Args:
        handle: 已启动的 interruptible process handle。
        cancellation_checker: operation-scoped 取消检查器。

    Returns:
        child 的 completed 或 failed 结果。

    Raises:
        CnDownloadCancelledError: 取消检查命中且 child cleanup 已执行时抛出。
        RuntimeError: terminate/kill 后 child 仍未退出时抛出。
    """

    while True:
        if cancellation_checker():
            terminate_result = await handle.terminate(
                grace_seconds=_DOCLING_TERMINATE_GRACE_SECONDS,
            )
            if not terminate_result.exited:
                kill_result = await handle.kill(
                    grace_seconds=_DOCLING_KILL_GRACE_SECONDS,
                )
                if not kill_result.exited:
                    raise RuntimeError("Docling child did not exit after kill")
            raise CnDownloadCancelledError("操作已被取消")
        wait_result = await handle.wait(
            timeout_seconds=_DOCLING_PROCESS_POLL_SECONDS,
        )
        if isinstance(wait_result, InterruptibleProcessStillRunning):
            continue
        return wait_result


def _read_and_validate_output(
    *,
    output_path: Path,
    wait_result: ProcessWaitResult,
) -> bytes:
    """读取 child 输出并验证 queue descriptor 的 size/digest。

    Args:
        output_path: parent 独占 temp tree 内的输出文件。
        wait_result: child wait 结果。

    Returns:
        size 与 SHA-256 均匹配的输出 bytes。

    Raises:
        RuntimeError: child 失败、descriptor 非法或完整性不匹配时抛出。
        OSError: 输出文件读取失败时抛出。
    """

    if isinstance(wait_result, InterruptibleProcessFailed):
        _LOGGER.warning(
            "cn_docling_process.child_failed error_type=%s exitcode=%s",
            wait_result.error_type,
            wait_result.exitcode,
        )
        raise RuntimeError("Docling child conversion failed")
    if not isinstance(wait_result, InterruptibleProcessCompleted):
        raise RuntimeError("Docling child returned an invalid terminal state")
    descriptor = wait_result.value
    if not isinstance(descriptor, dict):
        raise RuntimeError("Docling child result descriptor is invalid")
    expected_size = descriptor.get(_RESULT_SIZE_KEY)
    expected_digest = descriptor.get(_RESULT_DIGEST_KEY)
    if isinstance(expected_size, bool) or not isinstance(expected_size, int) or expected_size < 0:
        raise RuntimeError("Docling child result size is invalid")
    if (
        not isinstance(expected_digest, str)
        or len(expected_digest) != _SHA256_HEX_LENGTH
        or any(character not in "0123456789abcdef" for character in expected_digest)
    ):
        raise RuntimeError("Docling child result digest is invalid")
    output_bytes = output_path.read_bytes()
    if len(output_bytes) != expected_size:
        raise RuntimeError("Docling child output size mismatch")
    if hashlib.sha256(output_bytes).hexdigest() != expected_digest:
        raise RuntimeError("Docling child output digest mismatch")
    return output_bytes


def _validate_stream_name(stream_name: str) -> None:
    """校验 child 可见的 stream name 不含路径。

    Args:
        stream_name: 待校验 stream name。

    Returns:
        无。

    Raises:
        ValueError: stream name 为空或包含路径分隔符时抛出。
    """

    if not stream_name.strip():
        raise ValueError("stream_name must not be empty")
    if Path(stream_name).name != stream_name or "/" in stream_name or "\\" in stream_name:
        raise ValueError("stream_name must not contain path separators")


def _log_cleanup_warning(stage: str, error: BaseException) -> None:
    """记录不含临时路径或原始内容的 bounded cleanup warning。

    Args:
        stage: 固定 cleanup 阶段标签。
        error: cleanup 异常，仅记录类型。

    Returns:
        无。

    Raises:
        无。
    """

    _LOGGER.warning(
        "cn_docling_process.cleanup_failed stage=%s error_type=%s",
        stage,
        type(error).__name__,
    )


__all__ = ["ProcessCnDoclingConversionRunner"]
