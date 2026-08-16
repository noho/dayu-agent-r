"""Fins 上传链路共享的 closed public failure 契约与异常分类 owner。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Final

from dayu.contracts.json_value import JsonValue
from dayu.fins.direct_events import validate_fins_public_file_label
from dayu.fins.domain.company_meta_contract import CompanyMetaConcurrentUpdateError
from dayu.fins.pipelines.docling_process_converter import (
    DoclingConversionError,
    DoclingConversionFailureKind,
)
from dayu.fins.storage import (
    CompanyTickerAliasConflictError,
    CompanyTickerIdentityCorruptionError,
)
from dayu.fins.upload_format_contract import FinsUploadFormatError
from dayu.runtime.filelock import RuntimeFileLockError

_MAX_FAILURE_TEXT_CHARS: Final[int] = 240
_FAILURE_KEYS: Final[frozenset[str]] = frozenset({"kind", "code", "message", "retry_hint", "file_label"})


class FinsUploadFailureKind(str, Enum):
    """上传失败的 closed public category。"""

    USAGE = "usage"
    CONTENT = "content"
    STORAGE = "storage"
    RUNTIME = "runtime"


class FinsUploadFailureCode(str, Enum):
    """上传失败的 closed public reason code。"""

    UNSUPPORTED_UPLOAD_FORMAT = "unsupported_upload_format"
    DOCLING_CONVERTER_CONSTRUCTION = "docling_converter_construction"
    DOCLING_CONVERTER_EXECUTION = "docling_converter_execution"
    DOCLING_RESULT_SERIALIZATION = "docling_result_serialization"
    DOCLING_IPC_PROTOCOL = "docling_ipc_protocol"
    DOCLING_CHILD_CRASH = "docling_child_crash"
    DOCLING_CLEANUP = "docling_cleanup"
    EMPTY_INPUT_FILE = "empty_input_file"
    STORAGE_IO = "storage_io"
    TICKER_ALIAS_CONFLICT = "ticker_alias_conflict"
    SOURCE_INTEGRITY_UNSAFE = "source_integrity_unsafe"
    SOURCE_REVISION_STALE = "source_revision_stale"
    SOURCE_REPAIR_BLOCKED = "source_repair_blocked"
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
        kind: usage、content、storage 或 runtime 分类。
        code: closed failure code。
        message: 不含路径或异常 repr 的安全文案。
        retry_hint: 可选安全重试建议。
        file_label: 可选且已 canonicalize 的 public basename 标签。
    """

    kind: FinsUploadFailureKind
    code: FinsUploadFailureCode
    message: str
    retry_hint: str | None
    file_label: str | None

    def __post_init__(self) -> None:
        """校验 failure reason 的 closed kind/code 与 path-free 文本边界。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: kind 或 code 不是对应 enum 具体类型时抛出。
            ValueError: kind/code 错配，或文本/file label 不符合 public contract 时抛出。
        """

        if type(self.kind) is not FinsUploadFailureKind:
            raise TypeError("failure.kind 必须是 FinsUploadFailureKind")
        if type(self.code) is not FinsUploadFailureCode:
            raise TypeError("failure.code 必须是 FinsUploadFailureCode")
        expected_kind = _FAILURE_KIND_BY_CODE[self.code]
        if self.kind is not expected_kind:
            raise ValueError("failure.kind 与 failure.code 不一致")
        _validate_failure_reason_text(self.message, "failure.message")
        if self.retry_hint is not None:
            _validate_failure_reason_text(self.retry_hint, "failure.retry_hint")
        if self.file_label is not None:
            validate_fins_public_file_label(self.file_label)

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
            "file_label": self.file_label,
        }


class FinsUploadFailureError(RuntimeError):
    """携带唯一 owner 已校验 failure reason 的 typed 上传异常。"""

    failure: FinsUploadFailureReason

    def __init__(self, failure: FinsUploadFailureReason) -> None:
        """初始化 typed upload failure。

        Args:
            failure: 已由 upload failure owner 构造并校验的 public reason。

        Returns:
            无。

        Raises:
            无。
        """

        self.failure = failure
        super().__init__(failure.message)


_DOCLING_FAILURE_CODES: Final[Mapping[DoclingConversionFailureKind, FinsUploadFailureCode]] = {
    DoclingConversionFailureKind.CONVERTER_CONSTRUCTION: FinsUploadFailureCode.DOCLING_CONVERTER_CONSTRUCTION,
    DoclingConversionFailureKind.CONVERTER_EXECUTION: FinsUploadFailureCode.DOCLING_CONVERTER_EXECUTION,
    DoclingConversionFailureKind.RESULT_SERIALIZATION: FinsUploadFailureCode.DOCLING_RESULT_SERIALIZATION,
    DoclingConversionFailureKind.IPC_PROTOCOL: FinsUploadFailureCode.DOCLING_IPC_PROTOCOL,
    DoclingConversionFailureKind.CHILD_CRASH: FinsUploadFailureCode.DOCLING_CHILD_CRASH,
    DoclingConversionFailureKind.CLEANUP: FinsUploadFailureCode.DOCLING_CLEANUP,
}
_CONTENT_FAILURE_CODES: Final[frozenset[FinsUploadFailureCode]] = frozenset(
    (*_DOCLING_FAILURE_CODES.values(), FinsUploadFailureCode.EMPTY_INPUT_FILE)
)
_USAGE_FAILURE_CODES: Final[frozenset[FinsUploadFailureCode]] = frozenset(
    {FinsUploadFailureCode.UNSUPPORTED_UPLOAD_FORMAT}
)
_STORAGE_FAILURE_CODES: Final[frozenset[FinsUploadFailureCode]] = frozenset(
    {
        FinsUploadFailureCode.STORAGE_IO,
        FinsUploadFailureCode.TICKER_ALIAS_CONFLICT,
        FinsUploadFailureCode.SOURCE_INTEGRITY_UNSAFE,
        FinsUploadFailureCode.SOURCE_REVISION_STALE,
        FinsUploadFailureCode.SOURCE_REPAIR_BLOCKED,
    }
)
_RUNTIME_FAILURE_CODES: Final[frozenset[FinsUploadFailureCode]] = frozenset({FinsUploadFailureCode.UNEXPECTED_RUNTIME})
_FAILURE_CODES_BY_KIND: Final[Mapping[FinsUploadFailureKind, frozenset[FinsUploadFailureCode]]] = {
    FinsUploadFailureKind.USAGE: _USAGE_FAILURE_CODES,
    FinsUploadFailureKind.CONTENT: _CONTENT_FAILURE_CODES,
    FinsUploadFailureKind.STORAGE: _STORAGE_FAILURE_CODES,
    FinsUploadFailureKind.RUNTIME: _RUNTIME_FAILURE_CODES,
}
if frozenset(_FAILURE_CODES_BY_KIND) != frozenset(FinsUploadFailureKind):
    raise RuntimeError("upload failure kind 分组必须完整")
_GROUPED_FAILURE_CODE_COUNT: Final[int] = sum(len(codes) for codes in _FAILURE_CODES_BY_KIND.values())
_ALL_GROUPED_FAILURE_CODES: Final[frozenset[FinsUploadFailureCode]] = frozenset(
    code for codes in _FAILURE_CODES_BY_KIND.values() for code in codes
)
if _GROUPED_FAILURE_CODE_COUNT != len(_ALL_GROUPED_FAILURE_CODES):
    raise RuntimeError("upload failure code 分组必须互斥")
if _ALL_GROUPED_FAILURE_CODES != frozenset(FinsUploadFailureCode):
    raise RuntimeError("upload failure code 分组必须完整")
_FAILURE_KIND_BY_CODE: Final[Mapping[FinsUploadFailureCode, FinsUploadFailureKind]] = {
    code: kind for kind, codes in _FAILURE_CODES_BY_KIND.items() for code in codes
}


def fins_upload_failure_from_exception(
    error: Exception,
    *,
    file_label: str | None,
) -> FinsUploadFailureReason:
    """按 typed exception 类别产生安全 public failure reason。

    Args:
        error: workflow 捕获的原始异常，仅用于类型分类。
        file_label: 当前 original 的 canonical public label；无法归属文件时为 ``None``。

    Returns:
        不包含原始异常文本的 closed failure reason。

    Raises:
        ValueError: ``file_label`` 未经过唯一 canonicalizer 时抛出。
    """

    if isinstance(error, FinsUploadFormatError):
        return FinsUploadFailureReason(
            kind=FinsUploadFailureKind.USAGE,
            code=FinsUploadFailureCode.UNSUPPORTED_UPLOAD_FORMAT,
            message="文件格式不受支持，请选择支持的文件后重试",
            retry_hint="请查看上传帮助中的支持格式后重试",
            file_label=error.file_label,
        )
    if isinstance(error, DoclingConversionError):
        return FinsUploadFailureReason(
            kind=FinsUploadFailureKind.CONTENT,
            code=_DOCLING_FAILURE_CODES[error.kind],
            message="文件无法解析或已损坏，请检查文件后重试",
            retry_hint="请确认文件可正常打开并重新上传",
            file_label=file_label,
        )
    if isinstance(error, CompanyTickerAliasConflictError):
        return FinsUploadFailureReason(
            kind=FinsUploadFailureKind.STORAGE,
            code=FinsUploadFailureCode.TICKER_ALIAS_CONFLICT,
            message="股票代码别名已属于当前工作区中的其他公司，请移除冲突别名后重试",
            retry_hint="请确认公司的主代码与别名声明后重新上传",
            file_label=None,
        )
    if isinstance(error, CompanyTickerIdentityCorruptionError):
        return FinsUploadFailureReason(
            kind=FinsUploadFailureKind.STORAGE,
            code=FinsUploadFailureCode.STORAGE_IO,
            message="工作区公司代码身份数据损坏，无法安全提交",
            retry_hint="请修复工作区公司元数据后重试",
            file_label=None,
        )
    if isinstance(error, CompanyMetaConcurrentUpdateError):
        return FinsUploadFailureReason(
            kind=FinsUploadFailureKind.STORAGE,
            code=FinsUploadFailureCode.STORAGE_IO,
            message="公司元数据已被并发更新，本次上传未提交",
            retry_hint="请基于最新公司元数据重试",
            file_label=None,
        )
    if isinstance(error, (OSError, RuntimeFileLockError)):
        return FinsUploadFailureReason(
            kind=FinsUploadFailureKind.STORAGE,
            code=FinsUploadFailureCode.STORAGE_IO,
            message="上传产物读写失败，请稍后重试",
            retry_hint="若持续失败，请检查工作区存储状态",
            file_label=file_label,
        )
    return FinsUploadFailureReason(
        kind=FinsUploadFailureKind.RUNTIME,
        code=FinsUploadFailureCode.UNEXPECTED_RUNTIME,
        message="上传执行失败，请检查运行日志后重试",
        retry_hint=None,
        file_label=file_label,
    )


def fins_upload_empty_input_failure(file_label: str) -> FinsUploadFailureReason:
    """构造 filing 空文件的 closed bounded public reason。

    Args:
        file_label: 当前 original 的 canonical public file label。

    Returns:
        固定 content kind/code/message/retry hint 的 failure reason。

    Raises:
        ValueError: ``file_label`` 未经过唯一 canonicalizer 时抛出。
    """

    return FinsUploadFailureReason(
        kind=FinsUploadFailureKind.CONTENT,
        code=FinsUploadFailureCode.EMPTY_INPUT_FILE,
        message="文件为空，无法上传",
        retry_hint="请提供非空文件后重试",
        file_label=file_label,
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
        file_label=None,
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
        file_label=None,
    )


def fins_upload_source_integrity_unsafe_failure() -> FinsUploadFailureReason:
    """构造目标 filing 无法安全自动修复的 closed public reason。

    Args:
        无。

    Returns:
        不含路径、revision 或内部 reason 的 storage failure reason。

    Raises:
        无。
    """

    return FinsUploadFailureReason(
        kind=FinsUploadFailureKind.STORAGE,
        code=FinsUploadFailureCode.SOURCE_INTEGRITY_UNSAFE,
        message="工作区中的目标 filing 状态不完整且无法安全自动修复",
        retry_hint="请先修复工作区 source 状态后再重试",
        file_label=None,
    )


def fins_upload_source_revision_stale_failure() -> FinsUploadFailureReason:
    """构造 repair 准备期间目标 revision 漂移的 closed public reason。

    Args:
        无。

    Returns:
        不含路径、revision 或内部异常文本的 storage failure reason。

    Raises:
        无。
    """

    return FinsUploadFailureReason(
        kind=FinsUploadFailureKind.STORAGE,
        code=FinsUploadFailureCode.SOURCE_REVISION_STALE,
        message="目标 filing 在上传准备期间已发生变化，本次上传未提交",
        retry_hint="请基于最新目标状态重新发起上传",
        file_label=None,
    )


def fins_upload_source_repair_blocked_failure() -> FinsUploadFailureReason:
    """构造其它 source 阻断本次 repair 的 closed public reason。

    Args:
        无。

    Returns:
        不含路径、target 或内部 reason 的 storage failure reason。

    Raises:
        无。
    """

    return FinsUploadFailureReason(
        kind=FinsUploadFailureKind.STORAGE,
        code=FinsUploadFailureCode.SOURCE_REPAIR_BLOCKED,
        message="工作区中存在本次上传无法安全重建的其它 source，本次上传未提交",
        retry_hint="请先修复工作区中的其它 source 状态后再重试",
        file_label=None,
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
    file_label = _optional_failure_text(value, "file_label")
    expected_kind = _FAILURE_KIND_BY_CODE[code]
    if kind is not expected_kind:
        raise ValueError("upload failure kind 与 code 不一致")
    return FinsUploadFailureReason(
        kind=kind,
        code=code,
        message=message,
        retry_hint=retry_hint,
        file_label=file_label,
    )


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
