"""Fins usage 文案 owner 的 closed code 与有界安全性测试。"""

from __future__ import annotations

import json
from typing import cast
from pathlib import Path

import pytest

from dayu.fins.upload_format_contract import MAX_MATERIAL_UPLOAD_FILES
from dayu.fins.domain.enums import SourceKind
from dayu.fins.upload_asset_plan import (
    FinsUploadAssetPlanError,
    FinsUploadAssetPlanReason,
    plan_upload_assets,
)
from dayu.fins.upload_format_contract import FinsUploadFormatFailureKind
from dayu.fins.upload_usage_contract import (
    FINS_UPLOAD_USAGE_TEXT_LIMIT,
    FinsUploadUsageCategory,
    FinsUploadUsageCode,
    FinsUploadUsageFailure,
    fins_upload_asset_plan_usage_failure,
    fins_upload_usage_failure,
)


def test_fins_upload_usage_failure_mapping_is_closed_bounded_and_path_free() -> None:
    """usage code 到可行动文案的 mapping 必须穷尽、短小且不泄漏路径。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: code 集合、精确文案或安全边界漂移时抛出。
    """

    expected_codes = {
        "empty_ticker",
        "invalid_ticker",
        "invalid_ticker_alias",
        "invalid_source_kind",
        "invalid_action",
        "too_many_files",
        "files_not_allowed_for_delete",
        "duplicate_file_path",
        "duplicate_original_basename",
        "asset_name_collision",
        "reserved_control_name",
        "invalid_asset_name",
        "multiple_primary_selectors",
        "missing_multi_file_primary",
        "primary_not_in_files",
        "primary_not_allowed_for_delete",
        "missing_fiscal_year",
        "invalid_fiscal_year",
        "missing_fiscal_period",
        "fiscal_period_too_long",
        "unsupported_fiscal_period",
        "invalid_filing_date",
        "invalid_report_date",
        "company_name_too_long",
        "too_many_ticker_aliases",
        "missing_files",
        "invalid_file_basename",
        "file_not_found",
        "file_not_regular",
        "company_name_required",
        "create_target_exists",
        "update_target_missing",
        "existing_source_repair_requires_auto",
        "missing_form_type",
        "missing_material_name",
        "material_name_too_long",
        "invalid_material_fiscal_year",
        "empty_document_id",
        "document_id_mismatch",

    }
    assert {code.value for code in FinsUploadUsageCode} == expected_codes
    exact_messages = {
        FinsUploadUsageCode.EMPTY_TICKER: "--ticker 不能为空，请提供公司代码",
        FinsUploadUsageCode.INVALID_TICKER: "--ticker 无法识别，请提供有效公司代码",
        FinsUploadUsageCode.MISSING_FISCAL_YEAR: "--fiscal-year 不能为空",
        FinsUploadUsageCode.MISSING_FISCAL_PERIOD: "--fiscal-period 不能为空",
        FinsUploadUsageCode.MISSING_FILES: "create/update 上传必须提供 --files",
        FinsUploadUsageCode.FILES_NOT_ALLOWED_FOR_DELETE: "delete 不得提供 --files",
        FinsUploadUsageCode.DUPLICATE_FILE_PATH: "--files 不能包含解析后相同的重复路径",
        FinsUploadUsageCode.MULTIPLE_PRIMARY_SELECTORS: "--primary 只能指定一次",
        FinsUploadUsageCode.MISSING_MULTI_FILE_PRIMARY: "多文件 filing 必须使用 --primary 明确指定主文件",
        FinsUploadUsageCode.PRIMARY_NOT_IN_FILES: "--primary 必须精确匹配 --files 中的一个文件",
        FinsUploadUsageCode.PRIMARY_NOT_ALLOWED_FOR_DELETE: "delete 不得提供 --primary",
        FinsUploadUsageCode.INVALID_FILE_BASENAME: "上传文件名无效；请提供单个非空文件名",
        FinsUploadUsageCode.COMPANY_NAME_REQUIRED: "当前公司缺少有效元数据；create/update 必须提供 --company-name",
        FinsUploadUsageCode.INVALID_FISCAL_YEAR: "财年（fiscal_year）必须是 1000..9999 的整数",
        FinsUploadUsageCode.INVALID_FILING_DATE: "披露日期（filing_date）必须是实际存在的 YYYY-MM-DD 日期",
        FinsUploadUsageCode.INVALID_REPORT_DATE: "报告期日期（report_date）必须是实际存在的 YYYY-MM-DD 日期",
        FinsUploadUsageCode.FISCAL_PERIOD_TOO_LONG: "--fiscal-period 长度不能超过 240 个字符",
        FinsUploadUsageCode.UNSUPPORTED_FISCAL_PERIOD: "--fiscal-period 仅支持 FY、H1、Q1、Q2、Q3、Q4",
        FinsUploadUsageCode.EXISTING_SOURCE_REPAIR_REQUIRES_AUTO: (
            "目标 filing 不完整；请使用 auto 并提供完整文件重新上传"
        ),
    }
    for code in FinsUploadUsageCode:
        if code in {
            FinsUploadUsageCode.FILE_NOT_FOUND,
            FinsUploadUsageCode.FILE_NOT_REGULAR,
            FinsUploadUsageCode.DUPLICATE_ORIGINAL_BASENAME,
            FinsUploadUsageCode.ASSET_NAME_COLLISION,
            FinsUploadUsageCode.RESERVED_CONTROL_NAME,
            FinsUploadUsageCode.INVALID_ASSET_NAME,
        }:
            failure = fins_upload_usage_failure(
                code,
                file_name="report.pdf",
                category=(
                    FinsUploadUsageCategory.ASSET_PLAN
                    if code in {
                        FinsUploadUsageCode.DUPLICATE_ORIGINAL_BASENAME,
                        FinsUploadUsageCode.ASSET_NAME_COLLISION,
                        FinsUploadUsageCode.RESERVED_CONTROL_NAME,
                        FinsUploadUsageCode.INVALID_ASSET_NAME,
                    }
                    else FinsUploadUsageCategory.REQUEST
                ),
            )
        elif code is FinsUploadUsageCode.TOO_MANY_FILES:
            failure = fins_upload_usage_failure(code, max_files=MAX_MATERIAL_UPLOAD_FILES)
        else:
            failure = fins_upload_usage_failure(code)
        assert failure.code is code
        assert 0 < len(failure.message) <= 240
        assert "/Users/" not in failure.message
        assert "\\" not in failure.message
        if code in exact_messages:
            assert failure.message == exact_messages[code]
    for code in (
        FinsUploadUsageCode.INVALID_FISCAL_YEAR,
        FinsUploadUsageCode.INVALID_FILING_DATE,
        FinsUploadUsageCode.INVALID_REPORT_DATE,
    ):
        assert "--" not in fins_upload_usage_failure(code).message

    assert (
        fins_upload_usage_failure(
            FinsUploadUsageCode.FILE_NOT_FOUND,
            file_name="report.pdf",
        ).message
        == "上传文件不存在：report.pdf"
    )
    assert (
        fins_upload_usage_failure(
            FinsUploadUsageCode.FILE_NOT_REGULAR,
            file_name="report.pdf",
        ).message
        == "上传路径不是普通文件：report.pdf"
    )


def test_upload_usage_failure_fact_rejects_open_code_and_unbounded_message() -> None:
    """usage public fact 必须自身校验 closed code union 与 240 字符消息上界。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 直接 dataclass 构造可绕过 closed/bounded invariant 时抛出。
    """

    invalid_code = cast(
        FinsUploadUsageCode | FinsUploadFormatFailureKind,
        "open_code",
    )
    with pytest.raises(TypeError, match="closed contract"):
        FinsUploadUsageFailure(hint="请修正输入后重试", file_label=None, code=invalid_code, message="非法 code")
    with pytest.raises(ValueError, match="不能为空"):
        FinsUploadUsageFailure(hint="请修正输入后重试", file_label=None, code=FinsUploadUsageCode.EMPTY_TICKER, message="")
    with pytest.raises(ValueError, match="长度上限"):
        FinsUploadUsageFailure(hint="请修正输入后重试", file_label=None,
            code=FinsUploadFormatFailureKind.PRIMARY_SUFFIX_UNSUPPORTED,
            message="x" * 241,
        )
    invalid_category = cast(FinsUploadUsageCategory, "asset_plan_typo")
    with pytest.raises(TypeError, match="category"):
        FinsUploadUsageFailure(hint="请修正输入后重试", file_label=None,
            code=FinsUploadUsageCode.EMPTY_TICKER,
            message="非法类别",
            category=invalid_category,
        )
    with pytest.raises(ValueError, match="规划契约"):
        FinsUploadUsageFailure(hint="请修正输入后重试", file_label=None,
            code=FinsUploadUsageCode.INVALID_TICKER,
            message="非法组合",
            category=FinsUploadUsageCategory.ASSET_PLAN,
        )
    for code in (
        FinsUploadUsageCode.DUPLICATE_ORIGINAL_BASENAME,
        FinsUploadUsageCode.ASSET_NAME_COLLISION,
        FinsUploadUsageCode.RESERVED_CONTROL_NAME,
        FinsUploadUsageCode.INVALID_ASSET_NAME,
    ):
        with pytest.raises(ValueError, match="规划类别"):
            FinsUploadUsageFailure(hint="请修正输入后重试", file_label=None, code=code, message="规划专属错误")




def test_planner_reasons_share_usage_message_with_public_failure(tmp_path: Path) -> None:
    """每个规划原因在 CLI usage 与独立 pipeline failure 中保持同源文案。

    Args:
        tmp_path: 用于确认本地绝对路径不进入文案的隔离根。

    Returns:
        无。

    Raises:
        AssertionError: closed code、hint、长度或路径安全边界漂移时抛出。
    """

    from dayu.fins.upload_asset_plan import FinsUploadAssetPlanError, FinsUploadAssetPlanReason
    from dayu.fins.upload_failure import (
        FinsUploadFailureCode,
        FinsUploadFailureKind,
        fins_upload_failure_from_exception,
    )
    from dayu.fins.upload_usage_contract import fins_upload_asset_plan_usage_failure

    for reason in FinsUploadAssetPlanReason:
        error = FinsUploadAssetPlanError(
            reason,
            None if reason in {
                FinsUploadAssetPlanReason.MISSING_FILES,
                FinsUploadAssetPlanReason.TOO_MANY_FILES,
            } else tmp_path / "deck.pdf",
        )
        usage = fins_upload_asset_plan_usage_failure(
            error, max_files=MAX_MATERIAL_UPLOAD_FILES
        )
        public = fins_upload_failure_from_exception(error, file_label=None)
        assert usage.code.value == reason.value
        assert usage.category is FinsUploadUsageCategory.ASSET_PLAN
        assert public.kind is FinsUploadFailureKind.USAGE
        assert public.code is FinsUploadFailureCode(reason.value)
        assert public.message == usage.message
        assert public.retry_hint == usage.hint
        assert public.file_label == error.file_label
        assert 0 < len(usage.message) <= FINS_UPLOAD_USAGE_TEXT_LIMIT
        assert str(tmp_path) not in usage.message
        assert str(tmp_path) not in usage.hint
        if reason in {
            FinsUploadAssetPlanReason.DUPLICATE_ORIGINAL_BASENAME,
            FinsUploadAssetPlanReason.ASSET_NAME_COLLISION,
            FinsUploadAssetPlanReason.RESERVED_CONTROL_NAME,
            FinsUploadAssetPlanReason.INVALID_ASSET_NAME,
        }:
            assert "deck.pdf" in usage.message


@pytest.mark.parametrize(
    "code",
    (FinsUploadUsageCode.MISSING_FILES, FinsUploadUsageCode.DUPLICATE_FILE_PATH),
)
def test_shared_usage_code_retains_distinct_typed_category(code: FinsUploadUsageCode) -> None:
    """同一 closed code 在普通请求与规划来源中保留独立分类。

    Args:
        code: 两个入口共用的 usage code。

    Returns:
        无。

    Raises:
        AssertionError: owner 丢失来源或修改既有文案时抛出。
    """

    request_failure = fins_upload_usage_failure(code)
    plan_error = FinsUploadAssetPlanError(FinsUploadAssetPlanReason(code.value))
    plan_failure = fins_upload_asset_plan_usage_failure(
        plan_error, max_files=MAX_MATERIAL_UPLOAD_FILES
    )
    assert request_failure.code is plan_failure.code
    assert request_failure.message == plan_failure.message
    assert request_failure.category is FinsUploadUsageCategory.REQUEST
    assert plan_failure.category is FinsUploadUsageCategory.ASSET_PLAN


@pytest.mark.parametrize(
    "code",
    (
        FinsUploadUsageCode.DUPLICATE_ORIGINAL_BASENAME,
        FinsUploadUsageCode.ASSET_NAME_COLLISION,
        FinsUploadUsageCode.RESERVED_CONTROL_NAME,
        FinsUploadUsageCode.INVALID_ASSET_NAME,
    ),
)
def test_new_planner_usage_requires_safe_basename(code: FinsUploadUsageCode) -> None:
    """新增冲突文案必须拒绝缺失和带路径的文件标签。

    Args:
        code: 新增 planner 文件错误类别。

    Returns:
        无。

    Raises:
        AssertionError: 文案允许无定位标签或路径泄漏时抛出。
    """

    with pytest.raises(ValueError, match="basename"):
        fins_upload_usage_failure(code)
    with pytest.raises(ValueError, match="basename"):
        fins_upload_usage_failure(code, file_name="/private/tmp/deck.pdf")


@pytest.mark.parametrize(
    "reason",
    (
        "duplicate_original_basename",
        "asset_name_collision",
        "reserved_control_name",
        "invalid_asset_name",
    ),
)
def test_long_planner_file_label_preserves_closed_bounded_usage(
    tmp_path: Path, reason: str
) -> None:
    """所有新增带标签的规划失败都在完整文案预算内保持 closed reason。

    Args:
        tmp_path: 构造带绝对路径的安全长 basename。
        reason: 规划 owner 的文件相关 closed reason 值。

    Returns:
        无。

    Raises:
        AssertionError: 类型、预算、可修正提示或路径安全边界漂移时抛出。
    """

    from dayu.fins.upload_asset_plan import FinsUploadAssetPlanError, FinsUploadAssetPlanReason
    from dayu.fins.upload_failure import fins_upload_failure_from_exception
    from dayu.fins.upload_usage_contract import fins_upload_asset_plan_usage_failure

    basename = "a" * 222 + ".txt"
    error = FinsUploadAssetPlanError(FinsUploadAssetPlanReason(reason), tmp_path / basename)
    usage = fins_upload_asset_plan_usage_failure(error, max_files=MAX_MATERIAL_UPLOAD_FILES)
    public = fins_upload_failure_from_exception(error, file_label=None)

    assert usage.code is FinsUploadUsageCode(reason)
    assert public.code.value == reason
    assert public.message == usage.message
    assert public.retry_hint == usage.hint
    assert error.file_label == basename
    assert 0 < len(usage.message) <= FINS_UPLOAD_USAGE_TEXT_LIMIT
    assert "…" in usage.message
    assert ".txt" in usage.message
    assert "请" in usage.message
    assert str(tmp_path) not in usage.message
    assert str(tmp_path) not in usage.hint


def test_multibyte_planner_basename_keeps_complete_usage_bounded(tmp_path: Path) -> None:
    """长多字节原件名经规划拒绝后，完整 usage 保留首尾且恰好占满字符预算。

    Args:
        tmp_path: 隔离的绝对路径根。

    Returns:
        无。

    Raises:
        AssertionError: closed 原因、文案预算或路径安全边界漂移时抛出。
    """

    from dayu.fins.upload_failure import fins_upload_failure_from_exception
    from dayu.fins.upload_usage_contract import fins_upload_asset_plan_usage_failure

    basename = "名" * 230 + ".txt"
    with pytest.raises(FinsUploadAssetPlanError) as exc_info:
        plan_upload_assets(material_primary_selectors=(),
            source_kind=SourceKind.MATERIAL,
            operation="upsert",
            files=(tmp_path / basename,),
        )
    error = exc_info.value
    assert error.reason is FinsUploadAssetPlanReason.INVALID_ASSET_NAME
    usage = fins_upload_asset_plan_usage_failure(error, max_files=MAX_MATERIAL_UPLOAD_FILES)
    public = fins_upload_failure_from_exception(error, file_label=None)

    assert usage.code is FinsUploadUsageCode.INVALID_ASSET_NAME
    assert public.code.value == error.reason.value
    assert public.message == usage.message
    assert public.retry_hint == usage.hint
    assert len(usage.message) == FINS_UPLOAD_USAGE_TEXT_LIMIT
    assert "…" in usage.message
    leading, trailing = usage.message.split("…", maxsplit=1)
    assert "名" in leading
    assert ".txt" in trailing
    assert "请" in trailing
    assert str(tmp_path) not in usage.message
    assert str(tmp_path) not in usage.hint


def test_control_character_basename_uses_readable_hidden_usage_label(tmp_path: Path) -> None:
    """含 Cc 的同名原件在完整 usage 中只暴露可读的固定隐藏标签。

    Args:
        tmp_path: 生成不同目录中同名原件的绝对路径根。

    Returns:
        无。

    Raises:
        AssertionError: closed 原因、隐藏标签或路径安全边界漂移时抛出。
    """

    from dayu.fins.upload_failure import fins_upload_failure_from_exception
    from dayu.fins.upload_usage_contract import fins_upload_asset_plan_usage_failure

    basename = "隐\x01藏.txt"
    with pytest.raises(FinsUploadAssetPlanError) as exc_info:
        plan_upload_assets(material_primary_selectors=(),
            source_kind=SourceKind.MATERIAL,
            operation="upsert",
            files=(tmp_path / "first" / basename, tmp_path / "second" / basename),
        )
    error = exc_info.value
    assert error.reason is FinsUploadAssetPlanReason.DUPLICATE_ORIGINAL_BASENAME
    usage = fins_upload_asset_plan_usage_failure(error, max_files=MAX_MATERIAL_UPLOAD_FILES)
    public = fins_upload_failure_from_exception(error, file_label=None)

    assert usage.code is FinsUploadUsageCode.DUPLICATE_ORIGINAL_BASENAME
    assert public.code.value == error.reason.value
    assert public.message == usage.message
    assert public.retry_hint == usage.hint
    assert error.file_label == "输入文件（文件名已隐藏）"
    assert "输入文件（文件名已隐藏）" in usage.message
    assert 0 < len(usage.message) <= FINS_UPLOAD_USAGE_TEXT_LIMIT
    assert basename not in usage.message
    assert str(tmp_path) not in usage.message
    assert str(tmp_path) not in usage.hint


@pytest.mark.parametrize("basename", ("a\\b.txt", "a\ud800b.txt", "a\udc80b.txt"))
def test_rejected_basename_has_utf8_safe_usage_and_public_failure(
    tmp_path: Path, basename: str
) -> None:
    """非法组件与代理字符经唯一标签投影后仍可编码且保持封闭原因。

    Args:
        tmp_path: 隔离的绝对路径根。
        basename: 无法安全公开的原始文件名。

    Returns:
        无。

    Raises:
        AssertionError: typed 原因、标签或 UTF-8 投影漂移时抛出。
    """

    from dayu.fins.upload_failure import fins_upload_failure_from_exception
    from dayu.fins.upload_usage_contract import fins_upload_asset_plan_usage_failure

    with pytest.raises(FinsUploadAssetPlanError) as exc_info:
        plan_upload_assets(material_primary_selectors=(),
            source_kind=SourceKind.MATERIAL,
            operation="upsert",
            files=(tmp_path / basename,),
        )
    error = exc_info.value
    usage = fins_upload_asset_plan_usage_failure(error, max_files=MAX_MATERIAL_UPLOAD_FILES)
    public = fins_upload_failure_from_exception(error, file_label=None)

    assert error.reason is FinsUploadAssetPlanReason.INVALID_ASSET_NAME
    assert error.file_label == "输入文件（文件名已隐藏）"
    assert usage.code is FinsUploadUsageCode.INVALID_ASSET_NAME
    assert public.message == usage.message
    assert public.retry_hint == usage.hint
    assert public.file_label == error.file_label
    assert 0 < len(usage.message) <= FINS_UPLOAD_USAGE_TEXT_LIMIT
    assert str(tmp_path) not in usage.message
    assert basename not in usage.message
    usage.message.encode("utf-8")
    json.dumps(public.to_json(), ensure_ascii=False).encode("utf-8")


@pytest.mark.parametrize("names", (("a\ud800b.txt", "META.JSON"), ("META.JSON", "a\ud800b.txt")))
def test_unresolvable_name_keeps_reserved_reason_and_utf8_safe_failure(
    tmp_path: Path, names: tuple[str, str]
) -> None:
    """规范化失败与控制名混批时，控制名优先且公开失败可编码。

    Args:
        tmp_path: 构造隔离的原件路径根。
        names: 高代理名与控制名的正序或逆序。

    Returns:
        无。

    Raises:
        AssertionError: 控制名优先级或公开编码安全漂移时抛出。
    """

    from dayu.fins.upload_failure import fins_upload_failure_from_exception
    from dayu.fins.upload_usage_contract import fins_upload_asset_plan_usage_failure

    paths = tuple(tmp_path / str(index) / name for index, name in enumerate(names))
    with pytest.raises(FinsUploadAssetPlanError) as exc_info:
        plan_upload_assets(material_primary_selectors=(),
            source_kind=SourceKind.MATERIAL, operation="upsert", files=paths
        )
    error = exc_info.value
    usage = fins_upload_asset_plan_usage_failure(error, max_files=MAX_MATERIAL_UPLOAD_FILES)
    public = fins_upload_failure_from_exception(error, file_label=None)

    assert error.reason is FinsUploadAssetPlanReason.RESERVED_CONTROL_NAME
    assert usage.code is FinsUploadUsageCode.RESERVED_CONTROL_NAME
    assert public.message == usage.message
    assert public.retry_hint == usage.hint
    assert 0 < len(usage.message) <= FINS_UPLOAD_USAGE_TEXT_LIMIT
    assert str(tmp_path) not in usage.message
    assert "\ud800" not in usage.message
    usage.message.encode("utf-8")
    json.dumps(public.to_json(), ensure_ascii=False).encode("utf-8")
