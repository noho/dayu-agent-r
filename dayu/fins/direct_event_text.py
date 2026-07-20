"""Fins direct stream 与等待恢复的可见文案投影。

本模块只根据 direct/wait 边界已经产生的 typed 事实选择用户或 LLM 可见
中文文案。它不构造 direct event 契约对象，不读取 ingestion runtime，
也不理解 Host wait outcome 的持久化或状态迁移。
"""

from __future__ import annotations

from typing import Final, assert_never

from dayu.fins.direct_events import FinsErrorKind, FinsOperationKind, FinsResultStatus

_DIRECT_SUCCESS_TITLE: Final[str] = "操作完成"
_DIRECT_CANCELLED_TITLE: Final[str] = "操作已取消"
_DIRECT_DOWNLOAD_FAILURE_TITLE: Final[str] = "下载失败"
_DIRECT_PREPROCESS_FAILURE_TITLE: Final[str] = "预处理失败"
_DIRECT_UPLOAD_FAILURE_TITLE: Final[str] = "上传失败"

_DIRECT_GENERIC_FAILURE_MESSAGE: Final[str] = "执行失败"
_DIRECT_USER_INPUT_FAILURE_MESSAGE: Final[str] = "请求参数不符合财报处理要求"
_DIRECT_STORAGE_FAILURE_MESSAGE: Final[str] = "财报资料读写失败"
_DIRECT_PROVIDER_FAILURE_MESSAGE: Final[str] = "财报来源返回失败"
_DIRECT_EXECUTION_FAILURE_MESSAGE: Final[str] = "财报处理执行失败"
_DIRECT_CANCELLED_MESSAGE: Final[str] = "操作已取消"

_DIRECT_DOWNLOAD_EMPTY_MESSAGE: Final[str] = "下载请求未写入任何源文档"
_DIRECT_PREPROCESS_EMPTY_MESSAGE: Final[str] = "没有任何请求文档完成预处理"
_DIRECT_UPLOAD_FAILED_STATUS_MESSAGE: Final[str] = "上传运行时返回失败状态"
_DIRECT_UPLOAD_UNAVAILABLE_MESSAGE: Final[str] = "当前环境未装配财报上传能力"

_PROGRESS_UNKNOWN_MESSAGE: Final[str] = "财报处理进度已更新"
_PROGRESS_MESSAGES: Final[dict[str, str]] = {
    "download.preparing": "下载准备中",
    "download.started": "下载已开始",
    "download.completed": "下载已完成",
    "download.completed_with_failures": "下载已完成，存在失败候选",
    "preprocess.preparing": "预处理准备中",
    "preprocess.selected": "预处理已选择源文档",
    "preprocess.document_started": "预处理源文档已开始",
    "preprocess.document_processed": "预处理源文档已完成",
    "preprocess.document_skipped": "预处理源文档已跳过",
    "preprocess.document_failed": "预处理源文档失败",
    "preprocess.document_not_supported": "预处理源文档不支持",
    "preprocess.completed": "预处理请求已完成",
    "upload.preparing": "上传准备中",
    "upload.started": "上传已开始",
    "upload.completed": "上传已完成",
    "upload.completed_with_failures": "上传已完成，存在失败",
}

_WAIT_FAILED_HINT: Final[str] = "请检查财报处理摘要，必要时重新发起对应操作。"
_WAIT_CANCELLED_MESSAGE: Final[str] = "财报处理已取消。"
_WAIT_CANCELLED_HINT: Final[str] = "如仍需要该财报资料，请重新发起对应操作。"


def direct_result_title(
    *,
    operation_kind: FinsOperationKind,
    status: FinsResultStatus,
) -> str:
    """根据 direct 操作和终态状态选择结果标题。

    Args:
        operation_kind: direct 业务操作类型。
        status: direct 终态状态。

    Returns:
        用户可读 direct result 标题。

    Raises:
        AssertionError: operation_kind 或 status 出现未覆盖枚举值时抛出。
    """

    if status is FinsResultStatus.SUCCESS:
        return _DIRECT_SUCCESS_TITLE
    if status is FinsResultStatus.CANCELLED:
        return _DIRECT_CANCELLED_TITLE
    if status is FinsResultStatus.FAILURE:
        return _failure_title_for_operation(operation_kind)
    assert_never(status)


def direct_failure_message(
    *,
    error_kind: FinsErrorKind | None,
    fallback_message: str | None,
) -> str:
    """根据失败分类和可选业务失败说明选择 direct 失败文案。

    Args:
        error_kind: direct 失败分类；未知时为 ``None``。
        fallback_message: 上游已经清洗过的业务失败说明；为空时按分类生成默认说明。

    Returns:
        用户可读 direct 失败说明。

    Raises:
        AssertionError: error_kind 出现未覆盖枚举值时抛出。
    """

    if fallback_message is not None:
        stripped = fallback_message.strip()
        if stripped:
            return stripped
    if error_kind is None:
        return _DIRECT_GENERIC_FAILURE_MESSAGE
    if error_kind is FinsErrorKind.USER_INPUT:
        return _DIRECT_USER_INPUT_FAILURE_MESSAGE
    if error_kind is FinsErrorKind.STORAGE:
        return _DIRECT_STORAGE_FAILURE_MESSAGE
    if error_kind is FinsErrorKind.PROVIDER:
        return _DIRECT_PROVIDER_FAILURE_MESSAGE
    if error_kind is FinsErrorKind.EXECUTION:
        return _DIRECT_EXECUTION_FAILURE_MESSAGE
    if error_kind is FinsErrorKind.CANCELLED:
        return _DIRECT_CANCELLED_MESSAGE
    if error_kind is FinsErrorKind.UNKNOWN:
        return _DIRECT_GENERIC_FAILURE_MESSAGE
    assert_never(error_kind)


def direct_progress_message(*, stage: str) -> str:
    """根据 direct progress 阶段选择用户可见进度文案。

    Args:
        stage: runtime 已产生的 progress 阶段标签。

    Returns:
        用户可读 direct progress 文案；未知阶段返回通用进度说明。

    Raises:
        无。
    """

    return _PROGRESS_MESSAGES.get(stage, _PROGRESS_UNKNOWN_MESSAGE)


def direct_download_no_source_documents_message() -> str:
    """返回下载没有写入源文档时的 direct 失败说明。

    Args:
        无。

    Returns:
        用户可读下载失败说明。

    Raises:
        无。
    """

    return _DIRECT_DOWNLOAD_EMPTY_MESSAGE


def direct_preprocess_no_requested_documents_message() -> str:
    """返回预处理没有完成任何请求文档时的 direct 失败说明。

    Args:
        无。

    Returns:
        用户可读预处理失败说明。

    Raises:
        无。
    """

    return _DIRECT_PREPROCESS_EMPTY_MESSAGE


def direct_upload_failed_status_message() -> str:
    """返回上传执行结果为失败状态时的 direct 失败说明。

    Args:
        无。

    Returns:
        用户可读上传失败说明。

    Raises:
        无。
    """

    return _DIRECT_UPLOAD_FAILED_STATUS_MESSAGE


def direct_upload_runtime_unavailable_message() -> str:
    """返回当前环境无法执行上传 direct 操作时的失败说明。

    Args:
        无。

    Returns:
        用户可读上传能力不可用说明。

    Raises:
        无。
    """

    return _DIRECT_UPLOAD_UNAVAILABLE_MESSAGE


def wait_failed_hint() -> str:
    """返回 Fins 等待恢复失败时给 LLM 的下一步提示。

    Args:
        无。

    Returns:
        LLM 可读、业务可理解的失败恢复提示。

    Raises:
        无。
    """

    return _WAIT_FAILED_HINT


def wait_cancelled_message() -> str:
    """返回 Fins 等待恢复取消时的工具结果消息。

    Args:
        无。

    Returns:
        LLM 可读、业务可理解的取消消息。

    Raises:
        无。
    """

    return _WAIT_CANCELLED_MESSAGE


def wait_cancelled_hint() -> str:
    """返回 Fins 等待恢复取消时给 LLM 的下一步提示。

    Args:
        无。

    Returns:
        LLM 可读、业务可理解的取消恢复提示。

    Raises:
        无。
    """

    return _WAIT_CANCELLED_HINT


def _failure_title_for_operation(operation_kind: FinsOperationKind) -> str:
    """根据 direct 操作选择失败标题。

    Args:
        operation_kind: direct 业务操作类型。

    Returns:
        用户可读失败标题。

    Raises:
        AssertionError: operation_kind 出现未覆盖枚举值时抛出。
    """

    if operation_kind is FinsOperationKind.DOWNLOAD:
        return _DIRECT_DOWNLOAD_FAILURE_TITLE
    if operation_kind is FinsOperationKind.PREPROCESS:
        return _DIRECT_PREPROCESS_FAILURE_TITLE
    if operation_kind is FinsOperationKind.UPLOAD:
        return _DIRECT_UPLOAD_FAILURE_TITLE
    if operation_kind is FinsOperationKind.UPLOAD_FILING:
        return _DIRECT_UPLOAD_FAILURE_TITLE
    if operation_kind is FinsOperationKind.UPLOAD_MATERIAL:
        return _DIRECT_UPLOAD_FAILURE_TITLE
    if operation_kind is FinsOperationKind.PROCESS_FILING:
        return _DIRECT_PREPROCESS_FAILURE_TITLE
    if operation_kind is FinsOperationKind.PROCESS_MATERIAL:
        return _DIRECT_PREPROCESS_FAILURE_TITLE
    assert_never(operation_kind)
