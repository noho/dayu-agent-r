"""公司元数据提交警告的封闭公共投影。

本模块只拥有“提交的公司名称未被采用”这一业务事实的稳定公开文案、
typed JSON 编解码与 domain fact 投影，不承载其他 warning 语义。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Final

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.company_meta_contract import CompanyNameIgnoredChange


COMPANY_NAME_IGNORED_WARNING_MESSAGE: Final[str] = (
    "本次提交的公司名称未生效；已保留现有公司名称。请核对上传目标公司是否正确。"
)


class CompanyMetadataWarningKind(str, Enum):
    """公司元数据警告的封闭类型。"""

    COMPANY_NAME_IGNORED = "company_name_ignored"


@dataclass(frozen=True, slots=True)
class CompanyMetadataWarning:
    """可投影给用户与 LLM 的公司元数据警告。

    Attributes:
        kind: 封闭警告类型。
        message: 与警告类型绑定的规范固定文案。
    """

    kind: CompanyMetadataWarningKind
    message: str

    def __post_init__(self) -> None:
        """校验 typed warning 只表达规范闭集。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: kind 或 message 类型非法时抛出。
            ValueError: message 不是该 kind 的规范文案时抛出。
        """

        if type(self.kind) is not CompanyMetadataWarningKind:
            raise TypeError("company metadata warning kind 必须是封闭枚举")
        if not isinstance(self.message, str):
            raise TypeError("company metadata warning message 必须是字符串")
        if (
            self.kind is CompanyMetadataWarningKind.COMPANY_NAME_IGNORED
            and self.message != COMPANY_NAME_IGNORED_WARNING_MESSAGE
        ):
            raise ValueError("company_name_ignored warning message 必须使用规范文案")

    def to_json(self) -> dict[str, JsonValue]:
        """序列化为 closed-shape JSON object。

        Args:
            无。

        Returns:
            仅包含 ``kind`` 与 ``message`` 的规范 JSON object。

        Raises:
            无。
        """

        return {"kind": self.kind.value, "message": self.message}


def company_metadata_warning_from_json(
    value: JsonValue,
) -> CompanyMetadataWarning:
    """从 closed-shape JSON object 解析公司元数据警告。

    Args:
        value: 待解析的 JSON 值。

    Returns:
        已校验的 typed warning。

    Raises:
        ValueError: 值不是 exact object、字段类型非法、kind 未知或文案不规范时抛出。
    """

    if not isinstance(value, Mapping):
        raise ValueError("company metadata warning 必须是 JSON object")
    if set(value) != {"kind", "message"}:
        raise ValueError("company metadata warning 必须仅包含 kind 与 message")
    raw_kind = value["kind"]
    raw_message = value["message"]
    if not isinstance(raw_kind, str) or not isinstance(raw_message, str):
        raise ValueError("company metadata warning 字段必须是字符串")
    try:
        kind = CompanyMetadataWarningKind(raw_kind)
    except ValueError as error:
        raise ValueError("未知 company metadata warning kind") from error
    try:
        return CompanyMetadataWarning(kind=kind, message=raw_message)
    except (TypeError, ValueError) as error:
        raise ValueError("company metadata warning 不符合规范闭集") from error


def company_metadata_warnings_from_json(
    value: JsonValue,
) -> tuple[CompanyMetadataWarning, ...]:
    """解析当前业务允许的零或一个公司元数据警告。

    Args:
        value: filing terminal result 的 ``warnings`` JSON 值。

    Returns:
        空 tuple 或含唯一 typed warning 的 tuple。

    Raises:
        ValueError: 值不是数组、超过一个警告或对象不符合闭集时抛出。
    """

    if not isinstance(value, list):
        raise ValueError("warnings 必须是 JSON array")
    if len(value) > 1:
        raise ValueError("company metadata warnings 最多允许一个元素")
    warnings = tuple(company_metadata_warning_from_json(item) for item in value)
    if len({warning.kind for warning in warnings}) != len(warnings):
        raise ValueError("company metadata warning kind 不得重复")
    return warnings


def company_metadata_warnings_to_json(
    warnings: Sequence[CompanyMetadataWarning],
) -> list[JsonValue]:
    """把 typed warning collection 序列化为规范 JSON array。

    Args:
        warnings: 当前业务产生的零或一个 typed warning。

    Returns:
        与输入顺序一致的规范 JSON object 数组。

    Raises:
        TypeError: 元素不是精确 typed warning 时抛出。
        ValueError: 元素超过一个或 kind 重复时抛出。
    """

    if len(warnings) > 1:
        raise ValueError("company metadata warnings 最多允许一个元素")
    if any(type(warning) is not CompanyMetadataWarning for warning in warnings):
        raise TypeError("warnings 元素必须是 CompanyMetadataWarning")
    if len({warning.kind for warning in warnings}) != len(warnings):
        raise ValueError("company metadata warning kind 不得重复")
    return [warning.to_json() for warning in warnings]


def project_company_name_ignored_warning(
    ignored_change: CompanyNameIgnoredChange,
) -> CompanyMetadataWarning:
    """把 commit owner 的名称未采用事实投影为唯一公开 warning。

    Args:
        ignored_change: publication-lock 内产生的名称未采用 typed fact。

    Returns:
        固定 kind 与固定文案的公开 warning。

    Raises:
        TypeError: 输入不是精确 domain fact 时抛出。
    """

    if type(ignored_change) is not CompanyNameIgnoredChange:
        raise TypeError("ignored_change 必须是 CompanyNameIgnoredChange")
    return CompanyMetadataWarning(
        kind=CompanyMetadataWarningKind.COMPANY_NAME_IGNORED,
        message=COMPANY_NAME_IGNORED_WARNING_MESSAGE,
    )


__all__ = [
    "COMPANY_NAME_IGNORED_WARNING_MESSAGE",
    "CompanyMetadataWarning",
    "CompanyMetadataWarningKind",
    "company_metadata_warning_from_json",
    "company_metadata_warnings_from_json",
    "company_metadata_warnings_to_json",
    "project_company_name_ignored_warning",
]
