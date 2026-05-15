"""Host 公共契约字符串校验辅助函数。

本模块是 Host 层 public dataclass 与 construction option 共享的输入
校验真源，只处理层内通用字符串字段，不承载 durable / Engine 语义。
"""

from __future__ import annotations


def require_non_empty(value: str, *, field_name: str) -> None:
    """校验必填字符串字段非空。

    :param value: 待校验的字符串值。
    :param field_name: 错误消息中使用的字段名。
    :returns: ``None``。
    :raises ValueError: 字符串为空或仅包含空白字符时抛出。
    """

    if value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty")


def require_optional_non_empty(
    value: str | None, *, field_name: str
) -> None:
    """校验可选字符串字段在存在时非空。

    :param value: 待校验的可选字符串值。
    :param field_name: 错误消息中使用的字段名。
    :returns: ``None``。
    :raises ValueError: 字符串存在但为空或仅包含空白字符时抛出。
    """

    if value is not None:
        require_non_empty(value, field_name=field_name)
