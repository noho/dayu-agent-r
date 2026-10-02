"""仓储材料 manifest 的唯一严格字段投影；模型不依赖仓储。"""

from collections.abc import Mapping

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import MaterialManifestItem
from .source_meta_contract import require_material_source_meta_primary_document


def project_material_manifest_item(meta: Mapping[str, JsonValue]) -> MaterialManifestItem:
    """参数：完整材料源元数据；返回：同源主文件 manifest；异常：KeyError/ValueError 表示必填事实缺失或非法。"""
    return MaterialManifestItem.from_source_meta(meta, primary_document=require_material_source_meta_primary_document(meta))
