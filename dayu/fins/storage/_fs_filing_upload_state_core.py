"""文件系统 filing 上传 published-state 只读投影。"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Protocol, cast

from dayu.fins.domain.document_models import BatchToken, CompanyMeta
from dayu.fins.domain.enums import SourceKind
from dayu.fins.ticker_normalization import normalize_ticker
from dayu.runtime.filelock import RuntimeFileLockToken

from ._fs_source_integrity import _inspect_source_kind_unguarded
from ._fs_identity import _require_external_identity
from ._fs_storage_infra import _ActiveBatchState, _FsStorageInfra
from ._fs_storage_utils import _source_dir_name
from .repository_protocols import (
    CompanyTickerIdentityCorruptionError,
    FilingUploadPublishedState,
)
from .source_integrity import SourceIntegrityClassification, SourceIntegrityStatus


class _FilingUploadStateCoreProtocol(Protocol):
    """filing upload state mixin 依赖的 storage core 私有能力集合。"""

    def _target_ticker_dir(self, ticker: str) -> Path:
        """返回 canonical ticker 的 published locator。"""

        ...

    def _lstat_optional_storage_path(
        self,
        path: Path,
        *,
        action: str,
    ) -> os.stat_result | None:
        """显式区分 missing、结构状态与 operational I/O。"""

        ...

    def _acquire_publication_guard(self, ticker: str) -> RuntimeFileLockToken:
        """获取 ticker publication guard。"""

        ...

    def _release_lock_token(self, token: RuntimeFileLockToken) -> None:
        """释放 publication guard。"""

        ...

    def _read_company_meta_from_ticker_dir_unguarded(
        self,
        external_ticker: str,
        ticker_dir: Path,
    ) -> CompanyMeta | None:
        """从 caller 指定稳定 ticker root 读取 strict company meta。"""

        ...

    def _resolve_active_batch(
        self,
        batch: BatchToken,
        ticker: str,
    ) -> _ActiveBatchState:
        """解析同 core、同 ticker 且仍 open 的 batch capability。"""

        ...


def _read_filing_upload_state_from_ticker_dir_unguarded(
    *,
    core: _FilingUploadStateCoreProtocol,
    external_ticker: str,
    external_document_id: str,
    ticker_dir: Path,
) -> FilingUploadPublishedState:
    """从 caller-owned 稳定 ticker view 读取同版 company/source state。

    Args:
        core: 提供 strict company parser 的共享 storage core。
        external_ticker: exact canonical ticker。
        external_document_id: exact filing document ID。
        ticker_dir: published guard 或 open batch writer 保护的稳定 ticker root。

    Returns:
        同一次稳定 view 中的 company meta、source state 与 publication identity。

    Raises:
        CompanyTickerIdentityCorruptionError: ticker descriptor、company meta 或 identity
            durable state 损坏时抛出。
        ValueError: ticker、document 或 source state contract 非法时抛出。
        OSError: company/source operational 读取失败时抛出 path-free 异常。
        RuntimeError: exact inspector 缺少 target 或可信状态缺少 business meta 时抛出。
    """

    company_meta = core._read_company_meta_from_ticker_dir_unguarded(
        external_ticker,
        ticker_dir,
    )
    inspection = _inspect_source_kind_unguarded(
        ticker=external_ticker,
        source_kind=SourceKind.FILING,
        ticker_dir=ticker_dir,
        source_root=ticker_dir / _source_dir_name(SourceKind.FILING),
        requested_document_id=external_document_id,
    )
    inspected_target = inspection.target
    if inspected_target is None:
        raise RuntimeError("exact filing upload-state inspection 缺少 target")
    source_integrity = inspected_target.classification
    if source_integrity.status in {
        SourceIntegrityStatus.MISSING,
        SourceIntegrityStatus.UNSAFE,
    }:
        source_meta = None
    else:
        if inspected_target.business_meta is None:
            raise RuntimeError("可信 filing upload-state inspection 缺少 business meta")
        source_meta = dict(inspected_target.business_meta)
    publication_identity = (
        inspected_target.filing_upload_publication_identity
        if source_integrity.status is SourceIntegrityStatus.COMPLETE
        else None
    )
    return FilingUploadPublishedState(
        company_meta=company_meta,
        source_integrity=source_integrity,
        source_meta=source_meta,
        publication_identity=publication_identity,
    )


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
            同一 publication guard 下的 company meta、required integrity 与按状态可用的 source meta。

        Raises:
            CompanyTickerIdentityCorruptionError: published target、descriptor、meta
                或 identity durable state 损坏时抛出。
            ValueError: ticker 或 document identity 非法时抛出；source directory、meta、
                identity descriptor 等可归属 target 的结构损坏返回 ``UNSAFE`` typed state。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: identity descriptor、meta 或其它 published state operational 读取失败时
                抛出 path-free 文件系统异常。
            RuntimeError: exact inspector 未返回 target，或可信状态缺少 business meta 时抛出。
        """

        external_ticker = normalize_ticker(ticker).canonical
        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        core = cast(_FilingUploadStateCoreProtocol, self)
        target_dir = core._target_ticker_dir(external_ticker)
        target_stat = core._lstat_optional_storage_path(
            target_dir,
            action="检查 filing upload published ticker directory",
        )
        if target_stat is None:
            return FilingUploadPublishedState(
                company_meta=None,
                source_integrity=SourceIntegrityClassification(
                    ticker=external_ticker,
                    source_kind=SourceKind.FILING,
                    document_id=external_document_id,
                    revision=None,
                    status=SourceIntegrityStatus.MISSING,
                    reasons=(),
                ),
                source_meta=None,
                publication_identity=None,
            )
        if not stat.S_ISDIR(target_stat.st_mode):
            raise CompanyTickerIdentityCorruptionError(kind="invalid_descriptor")
        guard_token = core._acquire_publication_guard(external_ticker)
        try:
            return _read_filing_upload_state_from_ticker_dir_unguarded(
                core=core,
                external_ticker=external_ticker,
                external_document_id=external_document_id,
                ticker_dir=target_dir,
            )
        finally:
            core._release_lock_token(guard_token)

    def read_filing_upload_state_in_batch(
        self,
        batch: BatchToken,
        document_id: str,
    ) -> FilingUploadPublishedState:
        """读取 writer-owned staging view 中的同版 filing 上传状态。

        Args:
            batch: 同一 core、ticker 且仍 open 的 batch capability。
            document_id: 待校验的 exact filing 文档 ID。

        Returns:
            staging view 中同版 company meta、source state 与 publication identity。

        Raises:
            CompanyTickerIdentityCorruptionError: staging ticker descriptor、meta 或 identity
                durable state 损坏时抛出。
            ValueError: capability、ticker 或 document identity 非法时抛出。
            OSError: staging state operational 读取失败时抛出 path-free 异常。
            RuntimeError: exact inspector 缺少 target 或可信状态缺少 business meta 时抛出。
        """

        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        core = cast(_FilingUploadStateCoreProtocol, self)
        state = core._resolve_active_batch(batch, batch.ticker)
        return _read_filing_upload_state_from_ticker_dir_unguarded(
            core=core,
            external_ticker=state.token.ticker,
            external_document_id=external_document_id,
            ticker_dir=state.staging_ticker_dir,
        )
