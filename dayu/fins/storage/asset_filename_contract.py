"""仓储 document 目录中 source 资产文件名的纯校验契约。"""

from __future__ import annotations

import unicodedata
from typing import Final

from ._fs_identity import _IDENTITY_DESCRIPTOR_FILENAME
from ._fs_storage_utils import _SOURCE_META_FILENAME, _normalize_filename

DOCUMENT_SOURCE_CONTROL_FILENAMES: Final[frozenset[str]] = frozenset(
    {_SOURCE_META_FILENAME, _IDENTITY_DESCRIPTOR_FILENAME}
)


def source_asset_name_collision_key(name: str) -> str:
    """返回用于转换前保守比较的文件名键。

    Args:
        name: 原样的单组件仓储文件名。

    Returns:
        NFC、casefold、再 NFC 后的比较键；不改变实际保存名。

    Raises:
        ValueError: 文件名不是原样合法的单组件时抛出。
    """

    if _normalize_filename(name) != name:
        raise ValueError("仓储资产名必须是原样单组件")
    return unicodedata.normalize(
        "NFC", unicodedata.normalize("NFC", name).casefold()
    )


def is_document_source_control_name(name: str) -> bool:
    """判断资产名是否保守撞到 document source 控制文件。

    Args:
        name: 原样合法的单组件仓储文件名。

    Returns:
        名称与控制文件的比较键相同时返回 ``True``。

    Raises:
        ValueError: 名称不是原样合法的单组件时抛出。
    """

    key = source_asset_name_collision_key(name)
    return key in {
        source_asset_name_collision_key(control)
        for control in DOCUMENT_SOURCE_CONTROL_FILENAMES
    }
