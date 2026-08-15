"""Fins 上传 closed public failure owner 测试。"""

from __future__ import annotations

from typing import cast

import pytest

import dayu.fins.upload_failure as upload_failure
from dayu.contracts.json_value import JsonValue
from dayu.fins.upload_failure import (
    FinsUploadFailureCode,
    FinsUploadFailureKind,
    FinsUploadFailureReason,
    fins_upload_failure_from_exception,
    upload_failure_reason_from_json,
)
from dayu.fins.upload_format_contract import (
    FinsUploadFormatError,
    FinsUploadFormatFailureKind,
)


@pytest.mark.parametrize("format_kind", tuple(FinsUploadFormatFailureKind))
def test_upload_format_error_maps_to_closed_usage_failure(
    format_kind: FinsUploadFormatFailureKind,
) -> None:
    """三个 role-specific 格式错误必须投影为同一 closed usage reason。

    Args:
        format_kind: Fins 格式角色失败类别。

    Returns:
        无。

    Raises:
        AssertionError: kind、code 或安全文案投影漂移时抛出。
    """

    reason = fins_upload_failure_from_exception(
        FinsUploadFormatError(format_kind, "report.xsd"),
        file_label=None,
    )

    assert reason.kind is FinsUploadFailureKind.USAGE
    assert reason.code is FinsUploadFailureCode.UNSUPPORTED_UPLOAD_FORMAT
    assert reason.message == "文件格式不受支持，请选择支持的文件后重试"
    assert reason.retry_hint == "请查看上传帮助中的支持格式后重试"
    assert reason.file_label == "report.xsd"
    assert "/" not in reason.message
    assert "\\" not in reason.message


def test_unsupported_upload_format_reason_strict_json_round_trip() -> None:
    """新增 usage reason 必须 exact JSON 往返且保持 kind/code 一致。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: round-trip 丢字段或重分类时抛出。
    """

    reason = fins_upload_failure_from_exception(
        FinsUploadFormatError(
            FinsUploadFormatFailureKind.MATERIAL_SUFFIX_UNSUPPORTED,
            "deck.zip",
        ),
        file_label="ignored.pdf",
    )

    assert upload_failure_reason_from_json(reason.to_json()) == reason


@pytest.mark.parametrize(
    "payload",
    (
        {
            "kind": "content",
            "code": "unsupported_upload_format",
            "message": "文件格式不受支持，请选择支持的文件后重试",
            "retry_hint": "请查看上传帮助中的支持格式后重试",
            "file_label": "deck.zip",
        },
        {
            "kind": "usage",
            "code": "docling_converter_execution",
            "message": "文件格式不受支持，请选择支持的文件后重试",
            "retry_hint": "请查看上传帮助中的支持格式后重试",
            "file_label": "deck.zip",
        },
        {
            "kind": "usage",
            "code": "unknown_code",
            "message": "文件格式不受支持，请选择支持的文件后重试",
            "retry_hint": "请查看上传帮助中的支持格式后重试",
            "file_label": "deck.zip",
        },
    ),
)
def test_upload_failure_json_rejects_unknown_or_mismatched_kind_code(
    payload: dict[str, JsonValue],
) -> None:
    """新增 usage kind 不得放宽未知 code 或已知 kind/code 错配。

    Args:
        payload: 非法 failure JSON。

    Returns:
        无。

    Raises:
        AssertionError: parser 接受 open 或错配组合时抛出。
    """

    with pytest.raises(ValueError):
        upload_failure_reason_from_json(payload)


@pytest.mark.parametrize(
    ("kind", "code"),
    (
        (FinsUploadFailureKind.CONTENT, FinsUploadFailureCode.UNSUPPORTED_UPLOAD_FORMAT),
        (FinsUploadFailureKind.USAGE, FinsUploadFailureCode.DOCLING_CONVERTER_EXECUTION),
        (FinsUploadFailureKind.RUNTIME, FinsUploadFailureCode.STORAGE_IO),
    ),
)
def test_upload_failure_reason_direct_construction_rejects_kind_code_mismatch(
    kind: FinsUploadFailureKind,
    code: FinsUploadFailureCode,
) -> None:
    """reason owner 自身必须拒绝绕过 JSON parser 的已知 kind/code 错配。

    Args:
        kind: 故意错配的 closed failure kind。
        code: 故意错配的 closed failure code。

    Returns:
        无。

    Raises:
        AssertionError: direct construction 接受错配组合时抛出。
    """

    with pytest.raises(ValueError, match="failure.kind 与 failure.code 不一致"):
        FinsUploadFailureReason(
            kind=kind,
            code=code,
            message="安全失败文案",
            retry_hint=None,
            file_label=None,
        )


def test_upload_failure_reason_direct_construction_rejects_open_enum_values() -> None:
    """reason owner 自身必须拒绝伪装成 enum 的 open 字符串值。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: direct construction 接受 open kind/code 时抛出。
    """

    with pytest.raises(TypeError, match="failure.kind 必须是 FinsUploadFailureKind"):
        FinsUploadFailureReason(
            kind=cast(FinsUploadFailureKind, "usage"),
            code=FinsUploadFailureCode.UNSUPPORTED_UPLOAD_FORMAT,
            message="安全失败文案",
            retry_hint=None,
            file_label=None,
        )
    with pytest.raises(TypeError, match="failure.code 必须是 FinsUploadFailureCode"):
        FinsUploadFailureReason(
            kind=FinsUploadFailureKind.USAGE,
            code=cast(FinsUploadFailureCode, "unsupported_upload_format"),
            message="安全失败文案",
            retry_hint=None,
            file_label=None,
        )


def test_upload_failure_kind_code_mapping_is_disjoint_complete_and_single_source() -> None:
    """closed kind/code 分组与 parser 映射必须互斥、完整且同源。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: enum 覆盖、互斥或 mapper source of truth 漂移时抛出。
    """

    groups = upload_failure._FAILURE_CODES_BY_KIND
    grouped_codes = tuple(code for codes in groups.values() for code in codes)
    expected_mapping = {code: kind for kind, codes in groups.items() for code in codes}

    assert frozenset(groups) == frozenset(FinsUploadFailureKind)
    assert len(grouped_codes) == len(frozenset(grouped_codes))
    assert frozenset(grouped_codes) == frozenset(FinsUploadFailureCode)
    assert upload_failure._FAILURE_KIND_BY_CODE == expected_mapping
