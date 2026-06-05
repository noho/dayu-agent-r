"""公共契约层中立标量校验 helper。

本模块只承载 ``dayu.contracts`` 与下游层中立 runtime 可共享、且错误
类型和返回语义完全一致的基础标量校验；不表达 Host、Engine 或业务语义。
"""

from __future__ import annotations


def require_non_empty_text(value: str, *, field_name: str) -> None:
    """校验字符串存在非空白内容。

    :param value: 待校验字符串。
    :param field_name: 错误消息中的字段名。
    :returns: ``None``。
    :raises ValueError: 字符串为空或只包含空白时抛出。
    """

    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def require_optional_non_empty_text(
    value: str | None, *, field_name: str
) -> None:
    """校验可选字符串在存在时包含非空白内容。

    :param value: 待校验字符串；``None`` 表示未提供。
    :param field_name: 错误消息中的字段名。
    :returns: ``None``。
    :raises ValueError: 字符串存在但为空或只包含空白时抛出。
    """

    if value is not None:
        require_non_empty_text(value, field_name=field_name)
