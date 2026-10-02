"""仓储 source manifest 的唯一严格字段投影；模型不依赖仓储。"""

from collections.abc import Mapping

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import FilingManifestItem, MaterialManifestItem
from .source_meta_contract import require_material_source_meta_amended, require_material_source_meta_primary_document, require_source_meta_is_deleted


def project_material_manifest_item(meta: Mapping[str, JsonValue]) -> MaterialManifestItem:
    """参数：完整材料源元数据；返回：同源主文件 manifest；异常：KeyError/ValueError 表示必填事实缺失或非法。"""
    return MaterialManifestItem.from_source_meta(
        meta, primary_document=require_material_source_meta_primary_document(meta),
        amended=require_material_source_meta_amended(meta), is_deleted=require_source_meta_is_deleted(meta),
    )


def project_filing_manifest_item(meta: Mapping[str, JsonValue]) -> FilingManifestItem:
    """投影同一来源的财报 manifest 与严格删除事实。

    Args:
        meta: 仓储已经校验的完整财报源元数据。

    Returns:
        与源元数据同源的财报 manifest 项目。

    Raises:
        KeyError: 必填元数据字段缺失时抛出。
        ValueError: 必填字段或删除状态类型非法时抛出。
    """
    return FilingManifestItem.from_source_meta(meta, is_deleted=require_source_meta_is_deleted(meta))
