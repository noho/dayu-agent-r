"""Fins storage canonical source meta 公共契约测试。"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

import dayu.fins.storage as storage
from dayu.contracts.json_value import JsonValue
from dayu.fins.storage import require_source_meta_is_deleted


@pytest.mark.parametrize("is_deleted", (False, True))
def test_require_source_meta_is_deleted_returns_exact_boolean(is_deleted: bool) -> None:
    """canonical reader 必须返回 source meta 中的精确布尔删除状态。

    Args:
        is_deleted: 待读取的精确布尔值。

    Returns:
        无。

    Raises:
        AssertionError: reader 未保持 canonical 布尔值时抛出。
    """

    meta: Mapping[str, JsonValue] = {"is_deleted": is_deleted}

    assert require_source_meta_is_deleted(meta) is is_deleted


def test_require_source_meta_is_deleted_rejects_missing_field() -> None:
    """canonical reader 必须对缺失字段 fail closed。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: reader 使用默认值或异常文案漂移时抛出。
    """

    with pytest.raises(KeyError) as exc_info:
        require_source_meta_is_deleted({})

    assert exc_info.value.args == ("source meta 缺少 is_deleted",)


@pytest.mark.parametrize("invalid_value", (None, 0, 1, "false"))
def test_require_source_meta_is_deleted_rejects_non_boolean(invalid_value: JsonValue) -> None:
    """canonical reader 必须拒绝所有非精确 bool 值。

    Args:
        invalid_value: 待拒绝的 JSON 值。

    Returns:
        无。

    Raises:
        AssertionError: reader 接受 loose truthiness 或异常文案漂移时抛出。
    """

    with pytest.raises(ValueError, match="^source meta is_deleted 必须为布尔值$"):
        require_source_meta_is_deleted({"is_deleted": invalid_value})


def test_source_meta_deleted_reader_is_formal_storage_export() -> None:
    """canonical reader 必须从 storage 公共 contract boundary 正式导出。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: package export 与公共实现身份不一致时抛出。
    """

    assert "require_source_meta_is_deleted" in storage.__all__
    assert storage.require_source_meta_is_deleted is require_source_meta_is_deleted
