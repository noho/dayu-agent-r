"""文件系统 filing 上传 published-state 只读投影。"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, cast

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import CompanyMeta
from dayu.fins.domain.enums import SourceKind
from dayu.fins.ticker_normalization import normalize_ticker
from dayu.runtime.filelock import RuntimeFileLockToken

from ._fs_storage_infra import _FsStorageInfra
from .repository_protocols import FilingUploadPublishedState


class _FilingUploadStateCoreProtocol(Protocol):
    """snapshot mixin 依赖的 storage core 私有能力集合。"""

    def _ticker_dir_if_present_for_read(self, ticker: str) -> Path | None:
        """返回 ticker locator 是否存在。"""

        ...

    def _acquire_publication_guard(self, ticker: str) -> RuntimeFileLockToken:
        """获取 ticker publication guard。"""

        ...

    def _release_lock_token(self, token: RuntimeFileLockToken) -> None:
        """释放 publication guard。"""

        ...

    def _get_company_meta_unguarded(self, external_ticker: str) -> CompanyMeta:
        """在 caller 持 guard 时读取 company meta。"""

        ...

    def _get_source_meta_unguarded(
        self,
        external_ticker: str,
        external_document_id: str,
        normalized_source_kind: SourceKind,
    ) -> Mapping[str, JsonValue]:
        """在 caller 持 guard 时读取 source meta。"""

        ...


class _FsFilingUploadStateMixin(_FsStorageInfra):
    """在单一 publication guard 下读取 filing 上传校验状态。"""

    def read_filing_upload_state(
        self,
        ticker: str,
        document_id: str,
    ) -> FilingUploadPublishedState:
        """读取 company meta 与 filing source meta 的同版快照。

        Args:
            ticker: 待校验的公司代码。
            document_id: 待校验的 filing 文档 ID。

        Returns:
            同一 publication guard 下读取的两个独立可缺失成员。

        Raises:
            ValueError: ticker、document identity 或元数据不合法时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: published state 读取失败时抛出。
        """

        external_ticker = normalize_ticker(ticker).canonical
        core = cast(_FilingUploadStateCoreProtocol, self)
        if core._ticker_dir_if_present_for_read(external_ticker) is None:
            return FilingUploadPublishedState(company_meta=None, source_meta=None)

        guard_token = core._acquire_publication_guard(external_ticker)
        try:
            try:
                company_meta = core._get_company_meta_unguarded(external_ticker)
            except FileNotFoundError:
                company_meta = None
            try:
                source_meta = dict(
                    core._get_source_meta_unguarded(
                        external_ticker,
                        document_id,
                        SourceKind.FILING,
                    )
                )
            except FileNotFoundError:
                source_meta = None
            return FilingUploadPublishedState(
                company_meta=company_meta,
                source_meta=source_meta,
            )
        finally:
            core._release_lock_token(guard_token)
