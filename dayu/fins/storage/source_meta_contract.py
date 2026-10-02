"""Fins storage 发布的 canonical source meta 字段读取契约。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from dayu.contracts.json_value import JsonValue

_IS_DELETED_FIELD: Final[str] = "is_deleted"
_AMENDED_FIELD: Final[str] = "amended"


def require_source_meta_is_deleted(source_meta: Mapping[str, JsonValue]) -> bool:
    """读取 canonical source meta 的精确 logical deletion 状态。

    Args:
        source_meta: storage 已发布的 canonical source meta。

    Returns:
        精确布尔 logical deletion 状态。

    Raises:
        KeyError: source meta 缺少 ``is_deleted`` 时抛出。
        ValueError: ``is_deleted`` 不是精确布尔值时抛出。
    """

    if _IS_DELETED_FIELD not in source_meta:
        raise KeyError("source meta 缺少 is_deleted")
    is_deleted = source_meta[_IS_DELETED_FIELD]
    if not isinstance(is_deleted, bool):
        raise ValueError("source meta is_deleted 必须为布尔值")
    return is_deleted


_PRIMARY_DOCUMENT_FIELD: Final[str] = "primary_document"


def require_material_source_meta_primary_document(meta: Mapping[str, JsonValue]) -> str:
    """参数：材料源元数据；返回：必填非空主文件名；异常：KeyError 缺字段，ValueError 表示类型或空值错误。"""
    primary = meta[_PRIMARY_DOCUMENT_FIELD]
    if not isinstance(primary, str) or not primary.strip():
        raise ValueError("material primary_document 必须是非空文本")
    return primary


def require_material_source_meta_amended(meta: Mapping[str, JsonValue]) -> bool:
    """读取材料源元数据的严格修订事实。

    Args:
        meta: 仓储产生的材料源元数据。

    Returns:
        精确布尔修订事实。

    Raises:
        KeyError: 缺少 amended 字段时抛出。
        ValueError: amended 不是布尔值时抛出。
    """
    amended = meta[_AMENDED_FIELD]
    if type(amended) is not bool:
        raise ValueError("material amended 必须为布尔值")
    return amended


__all__ = ["require_source_meta_is_deleted", "require_material_source_meta_primary_document", "require_material_source_meta_amended"]
