"""文件系统文档存储私有 core — 组合入口。

该模块通过 mixin 组合把各领域职责拆分到独立子模块：
- `_fs_storage_utils`   — 模块级工具函数与常量
- `_fs_storage_infra`   — 共享基础设施（batch / path / manifest / handle）
- `_fs_company_meta_core` — 公司级元数据操作
- `_fs_source_document_core` — 源文档 CRUD / 查询 / 文件访问
- `_fs_processed_core`  — 解析产物操作
- `_fs_blob_core`       — Blob / 文件条目操作
- `_fs_maintenance_core` — 拒绝注册表与清理
"""

from __future__ import annotations

from ._fs_blob_core import _FsBlobMixin
from ._fs_company_meta_core import _FsCompanyMetaMixin
from ._fs_maintenance_core import _FsMaintenanceMixin
from ._fs_processed_core import _FsProcessedMixin
from ._fs_source_document_core import _FsSourceDocumentMixin
from ._fs_storage_infra import _FsStorageInfra


class FsStorageCore(
    _FsCompanyMetaMixin,
    _FsSourceDocumentMixin,
    _FsProcessedMixin,
    _FsBlobMixin,
    _FsMaintenanceMixin,
    _FsStorageInfra,
):
    """基于本地文件系统的文档存储私有 core。

    通过 mixin 钻石继承把功能组合到单一类，对外保持原有 API 不变。
    """
