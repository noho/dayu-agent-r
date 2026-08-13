"""Fins 上传链路共享的 closed public failure 契约与异常分类 owner。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Final

from dayu.contracts.json_value import JsonValue
from dayu.fins.pipelines.docling_process_converter import (
    DoclingConversionError,
    DoclingConversionFailureKind,
)

_MAX_FAILURE_TEXT_CHARS: Final[int] = 240
_FAILURE_KEYS: Final[frozenset[str]] = frozenset({"kind", "code", "message", "retry_hint"})


class FinsUploadFailureKind(str, Enum):
    """上传失败的 closed public category。"""

    CONTENT = "content"
    STORAGE = "storage"
    RUNTIME = "runtime"


class FinsUploadFailureCode(str, Enum):
    """上传失败的 closed public reason code。"""

    DOCLING_CONVERTER_CONSTRUCTION = "docling_converter_construction"
    DOCLING_CONVERTER_EXECUTION = "docling_converter_execution"
    DOCLING_RESULT_SERIALIZATION = "docling_result_serialization"
    DOCLING_IPC_PROTOCOL = "docling_ipc_protocol"
    DOCLING_CHILD_CRASH = "docling_child_crash"
    DOCLING_CLEANUP = "docling_cleanup"
    STORAGE_IO = "storage_io"
    UNEXPECTED_RUNTIME = "unexpected_runtime"


class FinsUploadPrevalidationError(RuntimeError):
    """filing prevalidation 期间的 typed bounded operational failure。"""

    failure: FinsUploadFailureReason

    def __init__(self, failure: FinsUploadFailureReason) -> None:
        """初始化 prevalidation operational error。

        Args:
            failure: 已由 failure owner 产生的 path-free reason。

        Returns:
            无。

        Raises:
            无。
        """

        self.failure = failure
        super().__init__(failure.message)


@dataclass(frozen=True, slots=True)
class FinsUploadFailureReason:
    """上传失败的有界、安全且可行动 public reason。

    Attributes:
        kind: content、storage 或 runtime 分类。
        code: closed failure code。
        message: 不含路径或异常 repr 的安全文案。
        retry_hint: 可选安全重试建议。
    """

    kind: FinsUploadFailureKind
    code: FinsUploadFailureCode
    message: str
    retry_hint: str | None

    def __post_init__(self) -> None:
        """校验 failure reason 的长度与 path-free 边界。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: 文本为空、超长、含控制字符或路径分隔符时抛出。
        """

        _validate_failure_reason_text(self.message, "failure.message")
        if self.retry_hint is not None:
            _validate_failure_reason_text(self.retry_hint, "failure.retry_hint")

    def to_json(self) -> dict[str, JsonValue]:
        """投影为 pipeline/runtime 共用 JSON object。

        Args:
            无。

        Returns:
            exact-key JSON object。

        Raises:
            无。
        """

        return {
            "kind": self.kind.value,
            "code": self.code.value,
            "message": self.message,
            "retry_hint": self.retry_hint,
        }


_DOCLING_FAILURE_CODES: Final[Mapping[DoclingConversionFailureKind, FinsUploadFailureCode]] = {
    DoclingConversionFailureKind.CONVERTER_CONSTRUCTION: FinsUploadFailureCode.DOCLING_CONVERTER_CONSTRUCTION,
    DoclingConversionFailureKind.CONVERTER_EXECUTION: FinsUploadFailureCode.DOCLING_CONVERTER_EXECUTION,
    DoclingConversionFailureKind.RESULT_SERIALIZATION: FinsUploadFailureCode.DOCLING_RESULT_SERIALIZATION,
    DoclingConversionFailureKind.IPC_PROTOCOL: FinsUploadFailureCode.DOCLING_IPC_PROTOCOL,
    DoclingConversionFailureKind.CHILD_CRASH: FinsUploadFailureCode.DOCLING_CHILD_CRASH,
    DoclingConversionFailureKind.CLEANUP: FinsUploadFailureCode.DOCLING_CLEANUP,
}
_CONTENT_FAILURE_CODES: Final[frozenset[FinsUploadFailureCode]] = frozenset(_DOCLING_FAILURE_CODES.values())


def fins_upload_failure_from_exception(error: Exception) -> FinsUploadFailureReason:
    """按 typed exception 类别产生安全 public failure reason。

    Args:
        error: workflow 捕获的原始异常，仅用于类型分类。

    Returns:
        不包含原始异常文本的 closed failure reason。

    Raises:
        无。
    """

    if isinstance(error, DoclingConversionError):
        return FinsUploadFailureReason(
            kind=FinsUploadFailureKind.CONTENT,
            code=_DOCLING_FAILURE_CODES[error.kind],
            message="文件无法解析或已损坏，请检查文件后重试",
            retry_hint="请确认文件可正常打开并重新上传",
        )
    if isinstance(error, OSError):
        return FinsUploadFailureReason(
            kind=FinsUploadFailureKind.STORAGE,
            code=FinsUploadFailureCode.STORAGE_IO,
            message="上传产物读写失败，请稍后重试",
            retry_hint="若持续失败，请检查工作区存储状态",
        )
    return FinsUploadFailureReason(
        kind=FinsUploadFailureKind.RUNTIME,
        code=FinsUploadFailureCode.UNEXPECTED_RUNTIME,
        message="上传执行失败，请检查运行日志后重试",
        retry_hint=None,
    )


def fins_upload_prevalidation_io_failure() -> FinsUploadFailureReason:
    """构造 filing published-state I/O 的 bounded public reason。

    Args:
        无。

    Returns:
        不含路径或原始异常文本的 storage failure reason。

    Raises:
        无。
    """

    return FinsUploadFailureReason(
        kind=FinsUploadFailureKind.STORAGE,
        code=FinsUploadFailureCode.STORAGE_IO,
        message="上传状态读取失败，请检查工作区存储状态",
        retry_hint="修复工作区存储后重试",
    )


def fins_upload_prevalidation_corruption_failure() -> FinsUploadFailureReason:
    """构造 filing published-state corruption 的 bounded public reason。

    Args:
        无。

    Returns:
        不含路径或原始异常文本的 storage failure reason。

    Raises:
        无。
    """

    return FinsUploadFailureReason(
        kind=FinsUploadFailureKind.STORAGE,
        code=FinsUploadFailureCode.STORAGE_IO,
        message="上传状态已损坏，请检查工作区存储状态",
        retry_hint="修复工作区存储后重试",
    )


def upload_failure_reason_from_json(value: JsonValue | None) -> FinsUploadFailureReason | None:
    """从 pipeline JSON exact-key object 恢复 typed failure reason。

    Args:
        value: failure JSON value；缺失时为 ``None``。

    Returns:
        typed failure reason 或 ``None``。

    Raises:
        ValueError: failure 字段、枚举或文本不符合 contract 时抛出。
    """

    if value is None:
        return None
    if not isinstance(value, Mapping) or frozenset(value) != _FAILURE_KEYS:
        raise ValueError("upload failure 必须是 exact-key object")
    kind = FinsUploadFailureKind(_required_failure_text(value, "kind"))
    code = FinsUploadFailureCode(_required_failure_text(value, "code"))
    message = _required_failure_text(value, "message")
    retry_hint = _optional_failure_text(value, "retry_hint")
    expected_kind = (
        FinsUploadFailureKind.CONTENT
        if code in _CONTENT_FAILURE_CODES
        else (
            FinsUploadFailureKind.STORAGE if code is FinsUploadFailureCode.STORAGE_IO else FinsUploadFailureKind.RUNTIME
        )
    )
    if kind is not expected_kind:
        raise ValueError("upload failure kind 与 code 不一致")
    return FinsUploadFailureReason(kind=kind, code=code, message=message, retry_hint=retry_hint)


def _required_failure_text(value: Mapping[str, JsonValue], key: str) -> str:
    """读取 failure JSON 的必填字符串。

    Args:
        value: failure JSON object。
        key: 字段名。

    Returns:
        非空字符串。

    Raises:
        ValueError: 字段不是非空字符串时抛出。
    """

    item = value.get(key)
    if not isinstance(item, str) or item == "":
        raise ValueError(f"upload failure {key} 必须是非空字符串")
    return item


def _optional_failure_text(value: Mapping[str, JsonValue], key: str) -> str | None:
    """读取 failure JSON 的可选字符串。

    Args:
        value: failure JSON object。
        key: 字段名。

    Returns:
        字符串或 ``None``。

    Raises:
        ValueError: 字段不是字符串或 ``None`` 时抛出。
    """

    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str):
        raise ValueError(f"upload failure {key} 必须是字符串或 null")
    return item


def _validate_failure_reason_text(value: str, field_name: str) -> None:
    """校验 failure public text 的有界 path-free contract。

    Args:
        value: 待校验文本。
        field_name: 错误字段名。

    Returns:
        无。

    Raises:
        ValueError: 文本为空、超长、含控制字符或路径分隔符时抛出。
    """

    if value == "" or len(value) > _MAX_FAILURE_TEXT_CHARS:
        raise ValueError(f"{field_name} 必须为 1..240 字符")
    if any(ord(character) < 32 for character in value) or "/" in value or "\\" in value:
        raise ValueError(f"{field_name} 禁止控制字符或路径分隔符")
