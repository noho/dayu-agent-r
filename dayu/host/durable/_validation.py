"""Host durable 私有标量校验 helper。

本模块只承载 durable 层内部可复用的基础标量校验，不表达 EventLog、
payload、idempotency 或 liveness 的业务语义，也不作为公共导出面。
"""

from __future__ import annotations

from dayu.host.durable.codec import is_sha256_digest
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.transaction import SQLiteScalar


def require_non_empty_text(value: str, *, field_name: str) -> None:
    """校验必填文本非空。

    :param value: 待校验文本。
    :param field_name: 错误消息中的字段名。
    :returns: ``None``。
    :raises HostDurableError: 文本为空时抛出。
    """

    if value == "" or value.isspace():
        raise HostDurableError(f"{field_name} must be non-empty")


def require_optional_non_empty_text(
    value: str | None, *, field_name: str
) -> None:
    """校验 optional 文本如果存在则非空。

    :param value: 待校验文本。
    :param field_name: 错误消息中的字段名。
    :returns: ``None``。
    :raises HostDurableError: 文本为空字符串或纯空白字符串时抛出。
    """

    if value is not None and (value == "" or value.isspace()):
        raise HostDurableError(f"{field_name} must be non-empty when provided")


def require_sha256_digest(value: str, *, field_name: str) -> None:
    """校验必填 digest 字符串格式。

    :param value: 待校验 digest。
    :param field_name: 错误消息中的字段名。
    :returns: ``None``。
    :raises HostDurableError: digest 格式无效时抛出。
    """

    if not is_sha256_digest(value):
        raise HostDurableError(f"{field_name} must be sha256 digest")


def require_optional_sha256_digest(
    value: str | None, *, field_name: str
) -> None:
    """校验 optional digest 格式。

    :param value: digest 字符串；无值时为 ``None``。
    :param field_name: 错误消息中的字段名。
    :returns: ``None``。
    :raises HostDurableError: digest 格式无效时抛出。
    """

    if value is not None:
        require_sha256_digest(value, field_name=field_name)


def require_text(value: SQLiteScalar, *, field_name: str) -> str:
    """把 SQLite scalar 校验并转换为必填文本。

    :param value: SQLite scalar 值。
    :param field_name: 错误消息中的字段名。
    :returns: 文本值。
    :raises HostDurableError: 值不是文本时抛出。
    """

    if isinstance(value, str):
        return value
    raise HostDurableError(f"{field_name} must be stored as text")


def optional_text(value: SQLiteScalar, *, field_name: str) -> str | None:
    """把 SQLite scalar 校验并转换为 optional 文本。

    :param value: SQLite scalar 值。
    :param field_name: 错误消息中的字段名。
    :returns: 文本值或 ``None``。
    :raises HostDurableError: 值不是文本且不是 ``None`` 时抛出。
    """

    if value is None:
        return None
    return require_text(value, field_name=field_name)


def require_int(value: SQLiteScalar, *, field_name: str) -> int:
    """把 SQLite scalar 校验并转换为整数。

    :param value: SQLite scalar 值。
    :param field_name: 错误消息中的字段名。
    :returns: 整数值。
    :raises HostDurableError: 值不是整数时抛出。
    """

    if isinstance(value, int):
        return value
    raise HostDurableError(f"{field_name} must be stored as integer")


def optional_int(value: SQLiteScalar, *, field_name: str) -> int | None:
    """把 SQLite scalar 校验并转换为 optional 整数。

    :param value: SQLite scalar 值。
    :param field_name: 错误消息中的字段名。
    :returns: 整数值或 ``None``。
    :raises HostDurableError: 值不是整数且不是 ``None`` 时抛出。
    """

    if value is None:
        return None
    return require_int(value, field_name=field_name)
