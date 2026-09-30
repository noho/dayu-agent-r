"""仓储 document source 控制文件名真源与保守比较测试。"""

from __future__ import annotations

import pytest

from dayu.fins.storage import DOCUMENT_SOURCE_CONTROL_FILENAMES
from dayu.fins.storage.asset_filename_contract import (
    is_document_source_control_name,
    source_asset_name_collision_key,
)


def test_document_control_names_and_case_variants() -> None:
    """唯一集合只包含同层控制名，大小写变体保守拒绝。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 控制名布局或碰撞键漂移时抛出。
    """

    assert DOCUMENT_SOURCE_CONTROL_FILENAMES == frozenset({"meta.json", ".identity.json"})
    assert is_document_source_control_name("meta.json")
    assert is_document_source_control_name("META.JSON")
    assert is_document_source_control_name(".identity.json")
    assert not is_document_source_control_name("material_manifest.json")
    assert source_asset_name_collision_key("Deck.txt") == source_asset_name_collision_key("deck.txt")


@pytest.mark.parametrize("name", ("", "../meta.json", " meta.json ", "a/b.pdf"))
def test_asset_name_requires_unchanged_single_component(name: str) -> None:
    """仓储纯入口拒绝会被 normalize 改写或跨组件的名称。

    Args:
        name: 非法的原样资产名。

    Returns:
        无。

    Raises:
        AssertionError: 非法名称未被拒绝时抛出。
    """

    with pytest.raises(ValueError):
        source_asset_name_collision_key(name)
