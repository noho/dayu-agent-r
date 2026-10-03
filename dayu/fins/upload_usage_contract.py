"""Fins 上传调用方可修正失败的 closed code 与统一文案 owner。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final

from dayu.fins.direct_events import canonicalize_fins_rejected_file_label
from dayu.fins.domain.enums import SourceKind
from dayu.fins.upload_asset_plan import (
    FinsUploadAssetPlanError, FinsUploadAssetPlanReason,
    UploadPrimarySelectionError, UploadPrimarySelectionPathError,
)
from dayu.fins.upload_format_contract import FinsUploadFormatFailureKind, FinsUploadFormatError

FINS_UPLOAD_USAGE_TEXT_LIMIT: Final[int] = 240
_FILE_LABEL_PLACEHOLDER: Final[str] = "{file_name}"
_FILE_LABEL_ELLIPSIS: Final[str] = "…"

class FinsUploadUsageCode(str, Enum):
    """上传调用方可修正的 closed usage failure code。"""

    MISSING_FORM_TYPE = "missing_form_type"
    MISSING_MATERIAL_NAME = "missing_material_name"
    MATERIAL_NAME_TOO_LONG = "material_name_too_long"
    INVALID_MATERIAL_FISCAL_YEAR = "invalid_material_fiscal_year"
    EMPTY_DOCUMENT_ID = "empty_document_id"
    DOCUMENT_ID_MISMATCH = "document_id_mismatch"
    EMPTY_TICKER = "empty_ticker"
    INVALID_TICKER = "invalid_ticker"
    INVALID_TICKER_ALIAS = "invalid_ticker_alias"
    INVALID_SOURCE_KIND = "invalid_source_kind"
    INVALID_ACTION = "invalid_action"
    TOO_MANY_FILES = "too_many_files"
    FILES_NOT_ALLOWED_FOR_DELETE = "files_not_allowed_for_delete"
    DUPLICATE_FILE_PATH = "duplicate_file_path"
    DUPLICATE_ORIGINAL_BASENAME = "duplicate_original_basename"
    ASSET_NAME_COLLISION = "asset_name_collision"
    RESERVED_CONTROL_NAME = "reserved_control_name"
    INVALID_ASSET_NAME = "invalid_asset_name"
    MULTIPLE_PRIMARY_SELECTORS = "multiple_primary_selectors"
    MISSING_MULTI_FILE_PRIMARY = "missing_multi_file_primary"
    PRIMARY_NOT_IN_FILES = "primary_not_in_files"
    PRIMARY_NOT_ALLOWED_FOR_DELETE = "primary_not_allowed_for_delete"
    MISSING_FISCAL_YEAR = "missing_fiscal_year"
    INVALID_FISCAL_YEAR = "invalid_fiscal_year"
    MISSING_FISCAL_PERIOD = "missing_fiscal_period"
    FISCAL_PERIOD_TOO_LONG = "fiscal_period_too_long"
    UNSUPPORTED_FISCAL_PERIOD = "unsupported_fiscal_period"
    INVALID_FILING_DATE = "invalid_filing_date"
    INVALID_REPORT_DATE = "invalid_report_date"
    COMPANY_NAME_TOO_LONG = "company_name_too_long"
    TOO_MANY_TICKER_ALIASES = "too_many_ticker_aliases"
    MISSING_FILES = "missing_files"
    INVALID_FILE_BASENAME = "invalid_file_basename"
    FILE_NOT_FOUND = "file_not_found"
    FILE_NOT_REGULAR = "file_not_regular"
    COMPANY_NAME_REQUIRED = "company_name_required"
    CREATE_TARGET_EXISTS = "create_target_exists"
    UPDATE_TARGET_MISSING = "update_target_missing"
    DELETE_TARGET_MISSING = "delete_target_missing"
    EXISTING_SOURCE_REPAIR_REQUIRES_AUTO = "existing_source_repair_requires_auto"


class FinsUploadUsageCategory(str, Enum):
    """区分普通请求用法失败与资产规划失败的公开语义来源。"""

    REQUEST = "request"
    ASSET_PLAN = "asset_plan"


@dataclass(frozen=True, slots=True)
class FinsUploadUsageFailure:
    """上传 usage failure 的 typed public fact。

    Attributes:
        code: closed usage failure code；格式错误直接使用角色 owner 的 failure kind。
        message: 最大 240 字符的可行动中文文案。
        category: 失败的 typed 语义来源，由 usage owner 校验。
        hint: 必填、同源且可行动的恢复建议。
        file_label: 已规范的安全文件标签；无法归属文件时为 None。
    """

    code: FinsUploadUsageCode | FinsUploadFormatFailureKind
    message: str
    hint: str
    file_label: str | None
    category: FinsUploadUsageCategory = FinsUploadUsageCategory.REQUEST

    def __post_init__(self) -> None:
        """校验 usage public fact 的 closed code 与消息边界。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: code、category 不属于 closed enum 或 message 不是字符串时抛出。
            ValueError: message 越界或类别与 code 双向约束不符时抛出。
        """

        if not isinstance(self.code, (FinsUploadUsageCode, FinsUploadFormatFailureKind)):
            raise TypeError("upload usage failure code 不属于 closed contract")
        if not isinstance(self.category, FinsUploadUsageCategory):
            raise TypeError("upload usage failure category 不属于 closed contract")
        if self.category is FinsUploadUsageCategory.ASSET_PLAN and self.code not in _PLANNER_USAGE_CODES.values():
            raise ValueError("资产规划 usage failure code 不属于规划契约")
        if self.category is FinsUploadUsageCategory.REQUEST and self.code in _PLANNER_EXCLUSIVE_USAGE_CODES:
            raise ValueError("资产规划专属 usage failure code 必须标记规划类别")
        if not isinstance(self.hint, str) or not self.hint or len(self.hint) > FINS_UPLOAD_USAGE_TEXT_LIMIT:
            raise ValueError("upload usage hint 必须是有界非空文本")
        if self.file_label is not None and self.file_label != canonicalize_fins_rejected_file_label(self.file_label):
            raise ValueError("upload usage file label 未规范化")
        if not isinstance(self.message, str):
            raise TypeError("upload usage failure message 必须是字符串")
        if not self.message:
            raise ValueError("upload usage failure message 不能为空")
        if len(self.message) > FINS_UPLOAD_USAGE_TEXT_LIMIT:
            raise ValueError("upload usage failure message 超出长度上限")


class FinsUploadUsageError(ValueError):
    """上传请求违反调用方可修正契约。"""

    failure: FinsUploadUsageFailure

    def __init__(self, failure: FinsUploadUsageFailure) -> None:
        """初始化 typed usage error。

        Args:
            failure: owner 已产生的 usage failure。

        Returns:
            无。

        Raises:
            无。
        """

        self.failure = failure
        super().__init__(failure.message)


_FILE_USAGE_CODES: Final[frozenset[FinsUploadUsageCode]] = frozenset(
    {
        FinsUploadUsageCode.FILE_NOT_FOUND,
        FinsUploadUsageCode.FILE_NOT_REGULAR,
        FinsUploadUsageCode.DUPLICATE_ORIGINAL_BASENAME,
        FinsUploadUsageCode.ASSET_NAME_COLLISION,
        FinsUploadUsageCode.RESERVED_CONTROL_NAME,
        FinsUploadUsageCode.INVALID_ASSET_NAME,
    }
)
_USAGE_MESSAGES: Final[Mapping[FinsUploadUsageCode, str]] = {
    FinsUploadUsageCode.MISSING_FORM_TYPE: "材料每个动作都必须提供非空 form_type",
    FinsUploadUsageCode.MISSING_MATERIAL_NAME: "材料每个动作都必须提供非空 material_name",
    FinsUploadUsageCode.MATERIAL_NAME_TOO_LONG: "材料名称去除首尾空白后不能超过 240 个 Unicode 码点",
    FinsUploadUsageCode.INVALID_MATERIAL_FISCAL_YEAR: "材料财年必须是 1800..2100 的整数，不能是布尔值",
    FinsUploadUsageCode.EMPTY_DOCUMENT_ID: "document_id 不能是空文本；可省略以使用生成的材料身份",
    FinsUploadUsageCode.DOCUMENT_ID_MISMATCH: "document_id 仅用于验证生成身份一致，不能覆盖材料身份",

    FinsUploadUsageCode.EMPTY_TICKER: "--ticker 不能为空，请提供公司代码",
    FinsUploadUsageCode.INVALID_TICKER: "--ticker 无法识别，请提供有效公司代码",
    FinsUploadUsageCode.INVALID_TICKER_ALIAS: "--ticker 别名无法识别，请提供有效公司代码",
    FinsUploadUsageCode.INVALID_SOURCE_KIND: "upload_filing 必须使用 filing source kind",
    FinsUploadUsageCode.INVALID_ACTION: "--action 仅支持 auto、create、update、delete",
    FinsUploadUsageCode.TOO_MANY_FILES: "--files 数量不能超过 {max_files} 个",
    FinsUploadUsageCode.FILES_NOT_ALLOWED_FOR_DELETE: "delete 不得提供 --files",
    FinsUploadUsageCode.DUPLICATE_FILE_PATH: "--files 不能包含解析后相同的重复路径",
    FinsUploadUsageCode.DUPLICATE_ORIGINAL_BASENAME: "原件文件名重复：{file_name}；请重命名后重试",
    FinsUploadUsageCode.ASSET_NAME_COLLISION: "文件名与派生资产名冲突：{file_name}；请重命名后重试",
    FinsUploadUsageCode.RESERVED_CONTROL_NAME: "文件名与仓储控制文件冲突：{file_name}；请重命名后重试",
    FinsUploadUsageCode.INVALID_ASSET_NAME: "文件名无法安全保存：{file_name}；请缩短或重命名后重试",
    FinsUploadUsageCode.MULTIPLE_PRIMARY_SELECTORS: "--primary 只能指定一次",
    FinsUploadUsageCode.MISSING_MULTI_FILE_PRIMARY: "多文件 filing 必须使用 --primary 明确指定主文件",
    FinsUploadUsageCode.PRIMARY_NOT_IN_FILES: "--primary 必须精确匹配 --files 中的一个文件",
    FinsUploadUsageCode.PRIMARY_NOT_ALLOWED_FOR_DELETE: "delete 不得提供 --primary",
    FinsUploadUsageCode.MISSING_FISCAL_YEAR: "--fiscal-year 不能为空",
    FinsUploadUsageCode.INVALID_FISCAL_YEAR: "财年（fiscal_year）必须是 1000..9999 的整数",
    FinsUploadUsageCode.MISSING_FISCAL_PERIOD: "--fiscal-period 不能为空",
    FinsUploadUsageCode.FISCAL_PERIOD_TOO_LONG: "--fiscal-period 长度不能超过 240 个字符",
    FinsUploadUsageCode.UNSUPPORTED_FISCAL_PERIOD: "--fiscal-period 仅支持 FY、H1、Q1、Q2、Q3、Q4",
    FinsUploadUsageCode.INVALID_FILING_DATE: "披露日期（filing_date）必须是实际存在的 YYYY-MM-DD 日期",
    FinsUploadUsageCode.INVALID_REPORT_DATE: "报告期日期（report_date）必须是实际存在的 YYYY-MM-DD 日期",
    FinsUploadUsageCode.COMPANY_NAME_TOO_LONG: "--company-name 长度不能超过 240 个字符",
    FinsUploadUsageCode.TOO_MANY_TICKER_ALIASES: "--ticker 别名数量不能超过 100 个",
    FinsUploadUsageCode.MISSING_FILES: "create/update 上传必须提供 --files",
    FinsUploadUsageCode.INVALID_FILE_BASENAME: "上传文件名无效；请提供单个非空文件名",
    FinsUploadUsageCode.FILE_NOT_FOUND: "上传文件不存在：{file_name}",
    FinsUploadUsageCode.FILE_NOT_REGULAR: "上传路径不是普通文件：{file_name}",
    FinsUploadUsageCode.COMPANY_NAME_REQUIRED: "当前公司缺少有效元数据；create/update 必须提供 --company-name",
    FinsUploadUsageCode.CREATE_TARGET_EXISTS: "create 目标已存在；请改用 update 或允许覆盖",
    FinsUploadUsageCode.UPDATE_TARGET_MISSING: "update 目标不存在；请改用 create",
    FinsUploadUsageCode.DELETE_TARGET_MISSING: "delete 材料目标不存在；请确认材料身份",
    FinsUploadUsageCode.EXISTING_SOURCE_REPAIR_REQUIRES_AUTO: (
        "目标 filing 不完整；请使用 auto 并提供完整文件重新上传"
    ),
}


def _bounded_file_usage_message(template: str, file_name: str) -> str:
    """按完整文案预算稳定缩短安全文件标签。

    Args:
        template: 含唯一文件名占位符的 closed usage 文案模板。
        file_name: 已验证不含路径的安全 basename。

    Returns:
        保留短标签原文、长标签首尾片段的有界文案。

    Raises:
        ValueError: 模板缺少文件标签占位符或固定文本已耗尽预算时抛出。
    """

    prefix, placeholder, suffix = template.partition(_FILE_LABEL_PLACEHOLDER)
    if not placeholder or _FILE_LABEL_PLACEHOLDER in suffix:
        raise ValueError("文件 usage 模板必须有且只有一个标签占位符")
    label_budget = FINS_UPLOAD_USAGE_TEXT_LIMIT - len(prefix) - len(suffix)
    if label_budget < len(_FILE_LABEL_ELLIPSIS) + 2:
        raise ValueError("文件 usage 模板没有足够的标签预算")
    if len(file_name) <= label_budget:
        return prefix + file_name + suffix
    # 首尾同时保留，方便用户识别同名前缀及扩展名；省略号只表示展示裁剪。
    visible_budget = label_budget - len(_FILE_LABEL_ELLIPSIS)
    leading_chars = visible_budget // 2
    trailing_chars = visible_budget - leading_chars
    return (
        prefix
        + file_name[:leading_chars]
        + _FILE_LABEL_ELLIPSIS
        + file_name[-trailing_chars:]
        + suffix
    )


def fins_upload_usage_failure(
    code: FinsUploadUsageCode,
    *,
    file_name: str | None = None,
    max_files: int | None = None,
    category: FinsUploadUsageCategory = FinsUploadUsageCategory.REQUEST,
) -> FinsUploadUsageFailure:
    """由 closed code 构造唯一 usage failure 文案。

    Args:
        code: closed usage failure code。
        file_name: 文件相关 code 使用的已去路径化 basename。
        max_files: 数量上限 code 由已判来源传入的上限。
        category: 失败的 typed 语义来源；仅规划投影指定资产规划类别。

    Returns:
        code 与 bounded actionable message 组成的 failure。

    Raises:
        ValueError: 文件 code 缺 basename、basename 含路径，或非文件 code 收到 basename 时抛出。
    """

    template = _USAGE_MESSAGES[code]
    if code is FinsUploadUsageCode.TOO_MANY_FILES:
        if max_files is None:
            raise ValueError("文件数量上限必须由调用方传入")
        template = template.format(max_files=max_files)
    elif max_files is not None:
        raise ValueError("非文件数量失败不接受上限")
    if code in _FILE_USAGE_CODES:
        if (
            file_name is None
            or file_name == ""
            or Path(file_name).name != file_name
            or "/" in file_name
            or "\\" in file_name
        ):
            raise ValueError("文件 usage failure 必须提供不含路径的 basename")
        message = _bounded_file_usage_message(template, file_name)
    else:
        if file_name is not None:
            raise ValueError("非文件 usage failure 不接受 file_name")
        message = template
    if len(message) > FINS_UPLOAD_USAGE_TEXT_LIMIT:
        raise ValueError("usage failure message 超出长度上限")
    return FinsUploadUsageFailure(code=code, message=message, category=category, hint=message, file_label=canonicalize_fins_rejected_file_label(file_name) if file_name is not None else None)



_PLANNER_USAGE_CODES: Final[Mapping[FinsUploadAssetPlanReason, FinsUploadUsageCode]] = {
    reason: FinsUploadUsageCode(reason.value) for reason in FinsUploadAssetPlanReason
}
_SHARED_PLANNER_USAGE_CODES: Final[frozenset[FinsUploadUsageCode]] = frozenset(
    {
        FinsUploadUsageCode.MISSING_FILES,
        FinsUploadUsageCode.TOO_MANY_FILES,
        FinsUploadUsageCode.DUPLICATE_FILE_PATH,
    }
)
_PLANNER_EXCLUSIVE_USAGE_CODES: Final[frozenset[FinsUploadUsageCode]] = frozenset(
    _PLANNER_USAGE_CODES.values()
) - _SHARED_PLANNER_USAGE_CODES
_PLANNER_RETRY_HINTS: Final[Mapping[FinsUploadAssetPlanReason, str]] = {
    FinsUploadAssetPlanReason.MISSING_FILES: "请提供至少一个文件后重试",
    FinsUploadAssetPlanReason.TOO_MANY_FILES: "请减少本次上传文件数量后重试",
    FinsUploadAssetPlanReason.DUPLICATE_FILE_PATH: "请移除重复的文件路径后重试",
    FinsUploadAssetPlanReason.DUPLICATE_ORIGINAL_BASENAME: "请重命名同名原件后重试",
    FinsUploadAssetPlanReason.ASSET_NAME_COLLISION: "请重命名冲突文件后重试",
    FinsUploadAssetPlanReason.RESERVED_CONTROL_NAME: "请避开仓储控制文件名后重试",
    FinsUploadAssetPlanReason.INVALID_ASSET_NAME: "请缩短或重命名文件后重试",
}


def fins_upload_asset_plan_usage_failure(
    error: FinsUploadAssetPlanError, *, max_files: int
) -> FinsUploadUsageFailure:
    """将规划失败投影为唯一有界 usage 文案与重试建议。

    Args:
        error: 资产规划 owner 产生的封闭错误。
        max_files: 已判来源的文件数量上限。

    Returns:
        携带 code/category/message/hint/file_label 的同源 usage fact。

    Raises:
        ValueError: 数量上限或文件标签不符合文案契约时抛出。
    """

    code = _PLANNER_USAGE_CODES[error.reason]
    failure = fins_upload_usage_failure(
        code,
        file_name=error.file_label if code in _FILE_USAGE_CODES else None,
        max_files=max_files if code is FinsUploadUsageCode.TOO_MANY_FILES else None,
        category=FinsUploadUsageCategory.ASSET_PLAN,
    )
    return FinsUploadUsageFailure(code=failure.code, message=failure.message, category=failure.category, hint=_PLANNER_RETRY_HINTS[error.reason], file_label=error.file_label)


def fins_upload_primary_selection_usage_failure(
    error: UploadPrimarySelectionError | UploadPrimarySelectionPathError, *, source_kind: SourceKind,
) -> FinsUploadUsageFailure:
    """参数：资产 owner 的选择错误与来源；返回：唯一公开用法事实；异常：ValueError 表示来源或文案契约错误。"""
    if source_kind not in (SourceKind.FILING, SourceKind.MATERIAL):
        raise ValueError("主文件选择来源不支持")
    if isinstance(error, UploadPrimarySelectionPathError):
        return fins_upload_usage_failure(FinsUploadUsageCode.FILE_NOT_FOUND, file_name=canonicalize_fins_rejected_file_label(error.input_path.name))
    code = FinsUploadUsageCode(error.reason.value)
    failure = fins_upload_usage_failure(code)
    if code is FinsUploadUsageCode.MISSING_MULTI_FILE_PRIMARY and source_kind is SourceKind.MATERIAL:
        message = "多文件材料必须明确指定唯一主文件"
        return FinsUploadUsageFailure(code=code, message=message, hint=message, file_label=None)
    return failure


def fins_upload_format_usage_failure(error: FinsUploadFormatError) -> FinsUploadUsageFailure:
    """参数：格式 owner 失败；返回：同源用法事实；异常：ValueError 表示公开事实非法。"""
    return FinsUploadUsageFailure(code=error.kind, message=str(error), hint=error.retry_hint, file_label=error.file_label)


def fins_upload_target_usage_failure(
    code: FinsUploadUsageCode, *, source_kind: SourceKind,
) -> FinsUploadUsageFailure:
    """参数：目标错误与显式来源；返回：同源用法事实；异常：非目标代码或来源不合法。"""
    if source_kind not in {SourceKind.FILING, SourceKind.MATERIAL}:
        raise ValueError("目标错误必须声明来源")
    if code not in {FinsUploadUsageCode.CREATE_TARGET_EXISTS, FinsUploadUsageCode.UPDATE_TARGET_MISSING, FinsUploadUsageCode.DELETE_TARGET_MISSING}:
        raise ValueError("不是目标前置条件代码")
    if code is FinsUploadUsageCode.DELETE_TARGET_MISSING and source_kind is not SourceKind.MATERIAL:
        raise ValueError("filing 不新增删除前置条件")
    return fins_upload_usage_failure(code)
