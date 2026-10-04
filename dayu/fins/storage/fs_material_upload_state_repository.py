"""文件系统 material 上传 published-state 只读仓储实现。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from dayu.fins.domain.document_models import BatchToken, CompanyMeta
from dayu.fins.domain.company_meta_contract import CompanyMetaCommitOutcome

from ._fs_repository_factory import _FsRepositorySet, build_fs_repository_set
from .file_store import FileStore
from .repository_protocols import (
    MaterialUploadPublishedState,
    MaterialUploadStateRepositoryProtocol,
)


class FsMaterialUploadStateRepository(MaterialUploadStateRepositoryProtocol):
    """基于文件系统的 material 上传校验状态仓储。"""

    def __init__(
        self,
        workspace_root: Path,
        *,
        file_store: Optional[FileStore] = None,
        repository_set: Optional[_FsRepositorySet] = None,
        create_directories: bool = False,
    ) -> None:
        """初始化只读 material 上传状态仓储。

        Args:
            workspace_root: Fins 工作区根目录。
            file_store: 可选文件存储实现。
            repository_set: 可选共享仓储 core 集合。
            create_directories: 是否在独立构造时创建 storage 目录；默认关闭。

        Returns:
            无。

        Raises:
            OSError: storage core 初始化失败时抛出。
        """

        self._repository_set = build_fs_repository_set(
            workspace_root=workspace_root,
            file_store=file_store,
            repository_set=repository_set,
            create_directories=create_directories,
        )

    def read_material_upload_state(
        self,
        ticker: str,
        document_id: str,
    ) -> MaterialUploadPublishedState:
        """读取同一 publication guard 下的上传校验状态。

        Args:
            ticker: 待校验的公司代码。
            document_id: 待校验的 material 文档 ID。

        Returns:
            company/source 的同版 published state。

        Raises:
            CompanyTickerIdentityCorruptionError: published ticker durable identity 损坏时抛出。
            ValueError: ticker 或 document identity 非法时抛出；可归属 material target 的
                source descriptor/meta 结构损坏返回 ``UNSAFE`` typed state。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published state 读取失败时抛出。
        """

        return self._repository_set.core.read_material_upload_state(ticker, document_id)

    def read_material_upload_state_in_batch(
        self,
        batch: BatchToken,
        document_id: str,
    ) -> MaterialUploadPublishedState:
        """读取 open batch writer-owned staging 中的上传校验状态。

        Args:
            batch: 同一共享 core、ticker 且仍 open 的 batch capability。
            document_id: 待校验的 exact material 文档 ID。

        Returns:
            staging company/source 的同版 state。

        Raises:
            CompanyTickerIdentityCorruptionError: staging ticker durable identity 损坏时抛出。
            ValueError: capability、ticker 或 document identity 非法时抛出。
            OSError: staging state 读取失败时抛出。
            RuntimeError: exact inspector payload 不完整时抛出。
        """

        return self._repository_set.core.read_material_upload_state_in_batch(
            batch,
            document_id,
        )


    def validate_material_upload_state(self, *, ticker: str, document_id: str, expected_source_state: MaterialUploadPublishedState | None, expected_company_meta: CompanyMeta | None) -> MaterialUploadPublishedState:
        """校验严格公司快照、alias 与可显式免除的材料条件。

        Args:
            ticker: 目标公司代码。
            document_id: 目标材料身份。
            expected_source_state: 必填，None 仅要求公司/alias 条件，不表示材料缺席。
            expected_company_meta: 必填的严格公司快照，None 表示公司缺席。
        Returns:
            guard 内的完整当前材料状态。
        Raises:
            CompanyMetaConcurrentUpdateError: 公司快照漂移。
            SourceIntegrityRevisionConflictError: 非 None 的材料条件漂移。
            CompanyTickerAliasConflictError: alias 占用。
            OSError: 真实读取、锁或释放失败。
        """
        return self._repository_set.core.validate_material_upload_state(ticker=ticker, document_id=document_id, expected_source_state=expected_source_state, expected_company_meta=expected_company_meta)

    def register_material_upload_preconditions(self, *, batch: BatchToken, expected_source_state: MaterialUploadPublishedState, expected_company_meta: CompanyMeta | None) -> None:
        """为材料写入登记完整的源与公司条件。

        Args:
            batch: 同一仓储且仍 open 的材料写入 batch。
            expected_source_state: 必填的 MaterialUploadPublishedState 完整材料状态，不允许 None。
            expected_company_meta: 严格公司快照，None 表示公司缺席。
        Returns:
            无返回值；校验成功后登记条件。
        Raises:
            TypeError: expected_source_state 不是 MaterialUploadPublishedState 类型。
            ValueError: batch capability 非法、重复登记或材料身份非法。
            CompanyMetaConcurrentUpdateError: 公司快照漂移。
            SourceIntegrityRevisionConflictError: 材料条件漂移。
            CompanyTickerIdentityCorruptionError: staging 公司身份或元数据损坏。
            OSError: staging 状态读取失败。
            RuntimeError: 材料检查结果缺少目标或可信业务元数据。
        """
        self._repository_set.core.register_material_upload_preconditions(batch=batch, expected_source_state=expected_source_state, expected_company_meta=expected_company_meta)

    def commit_material_upload_batch(self, batch: BatchToken) -> MaterialUploadPublishedState:
        """参数：材料 batch；返回：提交 final；异常：提交、cleanup 或 release 失败。"""
        return self._repository_set.core.commit_material_upload_batch(batch)

    def commit_material_upload_company_batch(self, batch: BatchToken) -> CompanyMetaCommitOutcome:
        """参数：独立公司 batch；返回：严格公司 final；异常：冲突或操作失败。"""
        return self._repository_set.core.commit_material_upload_company_batch(batch)
