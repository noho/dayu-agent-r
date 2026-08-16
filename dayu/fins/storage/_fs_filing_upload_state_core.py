"""文件系统 filing 上传 published-state 只读投影。"""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, cast

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import CompanyMeta
from dayu.fins.domain.enums import SourceKind
from dayu.fins.ticker_normalization import normalize_ticker
from dayu.runtime.filelock import RuntimeFileLockToken

from ._fs_storage_infra import _FsStorageInfra
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

    def _source_meta_path_for_read(
        self,
        external_ticker: str,
        external_document_id: str,
        source_kind: SourceKind,
    ) -> Path:
        """返回 caller-held guard 下 exact source meta locator。

        Args:
            external_ticker: 已规范化 exact external ticker。
            external_document_id: exact filing document ID。
            source_kind: filing 来源类型。

        Returns:
            published source meta locator。

        Raises:
            ValueError: identity 或 source kind 非法时抛出。
            OSError: identity descriptor 读取失败时抛出。
        """

        ...

    def _classify_source_integrity_unguarded(
        self,
        external_ticker: str,
        external_document_id: str,
        source_kind: SourceKind,
        *,
        meta_path: Path,
    ) -> SourceIntegrityClassification:
        """在 caller-held guard 下分类 exact source publication。

        Args:
            external_ticker: 已规范化 exact external ticker。
            external_document_id: exact filing document ID。
            source_kind: filing 来源类型。
            meta_path: storage owner 已解析的 source meta locator。

        Returns:
            exact target 的 typed integrity classification。

        Raises:
            ValueError: source identity、meta 或文件声明结构非法时抛出。
            OSError: published 文件系统读取失败时抛出。
        """

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
            同一 publication guard 下的 company meta、required integrity 与按状态可用的 source meta。

        Raises:
            CompanyTickerIdentityCorruptionError: published target、descriptor、meta
                或 identity durable state 损坏时抛出。
            ValueError: ticker/document identity 非法，或 published source directory、meta、
                identity descriptor 结构损坏（含 required meta/descriptor 缺失）时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: identity descriptor、meta 或其它 published state operational 读取失败时
                抛出 path-free 文件系统异常。
        """

        external_ticker = normalize_ticker(ticker).canonical
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
                    document_id=document_id,
                    revision=None,
                    status=SourceIntegrityStatus.MISSING,
                    reasons=(),
                ),
                source_meta=None,
            )
        if not stat.S_ISDIR(target_stat.st_mode):
            raise CompanyTickerIdentityCorruptionError(kind="invalid_descriptor")
        guard_token = core._acquire_publication_guard(external_ticker)
        try:
            try:
                company_meta = core._get_company_meta_unguarded(external_ticker)
            except FileNotFoundError:
                company_meta = None
            source_integrity = core._classify_source_integrity_unguarded(
                external_ticker,
                document_id,
                SourceKind.FILING,
                meta_path=core._source_meta_path_for_read(
                    external_ticker,
                    document_id,
                    SourceKind.FILING,
                ),
            )
            if source_integrity.status in {
                SourceIntegrityStatus.MISSING,
                SourceIntegrityStatus.UNSAFE,
            }:
                source_meta = None
            else:
                source_meta = dict(
                    core._get_source_meta_unguarded(
                        external_ticker,
                        document_id,
                        SourceKind.FILING,
                    )
                )
            return FilingUploadPublishedState(
                company_meta=company_meta,
                source_integrity=source_integrity,
                source_meta=source_meta,
            )
        finally:
            core._release_lock_token(guard_token)
