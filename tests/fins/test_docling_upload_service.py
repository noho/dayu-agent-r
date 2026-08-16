"""DoclingUploadService 行为测试。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Thread
from typing import BinaryIO, Literal, Optional, cast
from unittest.mock import patch

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import (
    BatchToken,
    DocumentHandle,
    FileObjectMeta,
    ProcessedHandle,
    SourceDocumentUpsertRequest,
    SourceDocumentRevision,
    SourceHandle,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.docling_upload_service import (
    DoclingUploadService,
    PreparedDoclingUpload,
    UploadOperationResult,
    _PendingFileAsset,
    _PreparedAssetMutation,
    _UploadSourceFingerprint,
    _build_filing_original_asset_identity,
    _build_upload_source_fingerprint,
    _can_skip_upload,
    _increment_document_version,
    _resolve_document_version,
    build_cn_filing_ids,
    build_material_ids,
    build_sec_filing_ids,
    commit_prepared_upload_batch,
    derive_report_kind,
    normalize_cn_fiscal_period,
    validate_material_upload_ids,
)
from dayu.fins.pipelines.docling_process_converter import (
    DoclingConversionCancelledError,
    DoclingConversionConfig,
    DoclingConversionError,
    DoclingConversionFailureKind,
    DoclingConversionResult,
)
from dayu.fins.storage import (
    FsBatchingRepository,
    FsDocumentBlobRepository,
    FsSourceDocumentRepository,
    SourceIntegrityClassification,
    SourceIntegrityPreflightError,
    SourceIntegrityRepairBlockedError,
    SourceIntegrityRepairBlockedReason,
    SourceIntegrityReason,
    SourceIntegrityStatus,
)
import dayu.fins.storage._fs_source_document_core as source_document_core_module
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet, build_fs_repository_set
from dayu.fins.upload_failure import (
    FinsUploadFailureCode,
    FinsUploadFailureError,
    FinsUploadFailureKind,
)
from dayu.fins.upload_format_contract import (
    FinsUploadFilingFiles,
    FinsUploadMaterialFiles,
)
from dayu.fins.upload_repair_contract import (
    ExistingSourceAutoRepair,
    ExistingSourceRepairDisposition,
    NoExistingSourceRepair,
)

from .upload_filing_test_support import published_tree_sha256

_INITIAL_CREATED_AT = "2020-01-01T00:00:00+00:00"
_REPLACEMENT_CREATED_AT = "2020-01-02T00:00:00+00:00"


def _build_filing_original_asset_for_test(file_path: Path) -> _PendingFileAsset:
    """从真实测试文件构造 filing original asset。

    Args:
        file_path: 已存在的绝对规范测试文件路径。

    Returns:
        与 production original projection 字段一致的待上传资产。

    Raises:
        OSError: 测试文件无法读取时抛出。
        ValueError: 路径不满足 filing identity contract 时抛出。
    """

    raw = file_path.read_bytes()
    return _PendingFileAsset(
        name=_build_filing_original_asset_identity(file_path),
        original_filename=file_path.name,
        derived_from=None,
        data=raw,
        content_type="application/pdf",
        sha256=hashlib.sha256(raw).hexdigest(),
        size=len(raw),
        source="original",
    )


def _require_original_filename_for_test(asset: _PendingFileAsset) -> str:
    """读取旧 fingerprint fixture 所需的 filing basename。

    Args:
        asset: 待投影的 filing original asset。

    Returns:
        非空 original filename。

    Raises:
        ValueError: 资产缺少 filing original filename 时抛出。
    """

    if asset.original_filename is None or not asset.original_filename:
        raise ValueError("旧 filing fingerprint fixture 要求 original_filename")
    return asset.original_filename


def _build_old_filing_fingerprint_for_test(assets: list[_PendingFileAsset]) -> str:
    """独立复现 amendment 前无角色 filing fingerprint 公式。

    Args:
        assets: filing original assets。

    Returns:
        旧单层 descriptor list 的 SHA-256 摘要。

    Raises:
        ValueError: 任一资产缺少 filing original filename 时抛出。
    """

    payload = [
        {
            "original_filename": _require_original_filename_for_test(asset),
            "sha256": asset.sha256,
            "size": asset.size,
            "source": asset.source,
        }
        for asset in sorted(
            assets,
            key=lambda item: (
                _require_original_filename_for_test(item),
                item.sha256,
                item.size,
                item.source,
            ),
        )
    ]
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _set_upload_clock(monkeypatch: pytest.MonkeyPatch, timestamp: str) -> None:
    """为上传 owner 与真实 FS 仓储设置同一个确定时钟。

    Args:
        monkeypatch: pytest 属性替换器。
        timestamp: 当前阶段应返回的 ISO8601 时间。

    Returns:
        无。

    Raises:
        AttributeError: 目标模块不再暴露时钟依赖时抛出。
    """

    monkeypatch.setattr(
        "dayu.fins.pipelines.docling_upload_service.now_iso8601",
        lambda: timestamp,
    )
    monkeypatch.setattr(
        "dayu.fins.storage._fs_source_document_core.now_iso8601",
        lambda: timestamp,
    )


@dataclass(frozen=True)
class _UploadServiceContext:
    """上传服务测试上下文。"""

    batching_repository: FsBatchingRepository
    source_repository: FsSourceDocumentRepository
    blob_repository: FsDocumentBlobRepository
    service: DoclingUploadService


class _SpyUploadSourceRepository(FsSourceDocumentRepository):
    """记录上传 final source mutation 的仓储 spy。"""

    def __init__(self, workspace_root: Path, repository_set: _FsRepositorySet, events: list[str]) -> None:
        """初始化 source 仓储 spy。"""

        super().__init__(workspace_root, repository_set=repository_set)
        self._events = events


class _FailingFinalUploadSourceRepository(_SpyUploadSourceRepository):
    """在 final create 阶段失败的 source 仓储 spy。"""

    def create_source_document(
        self,
        req: SourceDocumentUpsertRequest,
        source_kind: SourceKind,
        *,
        batch: BatchToken,
    ) -> DocumentHandle:
        """模拟 staging 后 final source commit 失败。"""

        del req, source_kind, batch
        self._events.append("create_failed")
        raise RuntimeError("forced final upsert failure")


class _BatchIdentityUploadBatchingRepository(FsBatchingRepository):
    """记录 upload 顶层 owner 计数与 invocation-time token 的 batching spy。"""

    def __init__(self, workspace_root: Path, repository_set: _FsRepositorySet, events: list[str]) -> None:
        """初始化 batch identity spy。"""

        super().__init__(workspace_root, repository_set=repository_set)
        self._events = events
        self.active_token: BatchToken | None = None
        self.phase_batch_ids: list[tuple[str, str]] = []
        self.begin_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0

    def begin_batch(self, ticker: str) -> BatchToken:
        """开启 batch 并记录唯一 token。"""

        token = super().begin_batch(ticker)
        self.begin_calls += 1
        self.active_token = token
        self.phase_batch_ids.append(("begin", token.transaction_id))
        return token

    def commit_batch(self, batch: BatchToken) -> None:
        """记录 caller 的唯一 commit 并转发 storage commit。"""

        self.record_phase("commit", batch)
        self.commit_calls += 1
        super().commit_batch(batch)
        self.active_token = None

    def rollback_batch(self, batch: BatchToken) -> None:
        """记录 caller rollback 并转发 storage rollback。"""

        self.record_phase("rollback", batch)
        self.rollback_calls += 1
        super().rollback_batch(batch)
        self.active_token = None

    def record_phase(self, phase: str, batch: BatchToken) -> None:
        """把阶段与显式 batch ID 一并记录。"""

        assert self.active_token == batch
        self.phase_batch_ids.append((phase, batch.transaction_id))


class _BatchIdentityUploadSourceRepository(_SpyUploadSourceRepository):
    """记录 upload final source 显式 batch identity 的 source 仓储 spy。"""

    def __init__(
        self,
        workspace_root: Path,
        repository_set: _FsRepositorySet,
        events: list[str],
        batching_repository: _BatchIdentityUploadBatchingRepository,
    ) -> None:
        """初始化 source batch identity spy。"""

        super().__init__(workspace_root, repository_set, events)
        self._batching_repository = batching_repository

    def create_source_document(
        self,
        req: SourceDocumentUpsertRequest,
        source_kind: SourceKind,
        *,
        batch: BatchToken,
    ) -> DocumentHandle:
        """记录 final meta 的 invocation-time token。"""

        self._batching_repository.record_phase("final_meta", batch)
        return super().create_source_document(req, source_kind, batch=batch)


class _BatchIdentityUploadBlobRepository(FsDocumentBlobRepository):
    """记录 upload blob 写入所处 batch identity 的仓储 spy。"""

    def __init__(
        self,
        workspace_root: Path,
        repository_set: _FsRepositorySet,
        batching_repository: _BatchIdentityUploadBatchingRepository,
    ) -> None:
        """初始化 blob batch identity spy。"""

        super().__init__(workspace_root, repository_set=repository_set)
        self._batching_repository = batching_repository

    def store_file(
        self,
        handle: SourceHandle | ProcessedHandle,
        filename: str,
        data: BinaryIO,
        *,
        batch: BatchToken,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> FileObjectMeta:
        """记录当前 token 后转发真实 blob 写入。"""

        self._batching_repository.record_phase(f"blob:{filename}", batch)
        return super().store_file(
            handle,
            filename,
            data,
            batch=batch,
            content_type=content_type,
            metadata=metadata,
        )


class _CommitFailingUploadBatchingRepository(FsBatchingRepository):
    """模拟 storage 已消费 token 后仍向 caller 抛出 commit 主异常。"""

    def __init__(self, workspace_root: Path, repository_set: _FsRepositorySet, events: list[str]) -> None:
        """初始化 commit failure spy。"""

        super().__init__(workspace_root, repository_set=repository_set)
        self._events = events
        self.caller_rollback_calls = 0

    def commit_batch(self, batch: BatchToken) -> None:
        """由 storage owner 回滚并消费 token，再抛出 commit 主异常。"""

        FsBatchingRepository.rollback_batch(self, batch)
        raise OSError("forced storage commit failure")

    def rollback_batch(self, batch: BatchToken) -> None:
        """记录不应发生的 caller 二次 rollback。"""

        self.caller_rollback_calls += 1
        super().rollback_batch(batch)


class _RollbackFailingUploadBatchingRepository(FsBatchingRepository):
    """模拟 operation 与 caller rollback 同时失败的 batching 仓储。"""

    def rollback_batch(self, batch: BatchToken) -> None:
        """抛出 rollback 次异常以验证双错误传播。"""

        del batch
        raise OSError("forced rollback failure")


class _CommitBarrierBatchingRepository(FsBatchingRepository):
    """在 ownership transfer 后阻塞 commit 的竞态测试仓储。"""

    def __init__(self, workspace_root: Path, repository_set: _FsRepositorySet) -> None:
        """初始化 commit barrier。

        Args:
            workspace_root: 测试工作区。
            repository_set: 共享仓储集合。

        Returns:
            无。
        """

        super().__init__(workspace_root, repository_set=repository_set)
        self.commit_entered = Event()
        self.allow_commit_return = Event()
        self.rollback_calls = 0

    def commit_batch(self, batch: BatchToken) -> None:
        """在真实 commit 前等待测试释放。

        Args:
            batch: 已转交 storage owner 的 capability。

        Returns:
            无。

        Raises:
            TimeoutError: 测试未释放 barrier 时抛出。
            OSError: 真实 commit 失败时抛出。
        """

        self.commit_entered.set()
        if not self.allow_commit_return.wait(timeout=1.0):
            raise TimeoutError("commit barrier was not released")
        super().commit_batch(batch)

    def rollback_batch(self, batch: BatchToken) -> None:
        """记录 caller rollback。

        Args:
            batch: caller-owned capability。

        Returns:
            无。

        Raises:
            OSError: 真实 rollback 失败时抛出。
        """

        self.rollback_calls += 1
        super().rollback_batch(batch)


class _MutableToken(CancellationToken):
    """由 Event 驱动并记录观察次数的 canonical token。"""

    def __init__(self) -> None:
        """初始化未取消状态。

        Returns:
            无。
        """

        self.cancelled = Event()
        self.read_count = 0

    def request_cancel(self) -> None:
        """请求取消。

        Returns:
            无。
        """

        self.cancelled.set()

    def is_cancelled(self) -> bool:
        """记录并返回取消状态。

        Returns:
            当前 Event 状态。
        """

        self.read_count += 1
        return self.cancelled.is_set()

    def cancel_reason(self) -> str | None:
        """返回测试取消原因。

        Returns:
            已取消时返回固定原因，否则返回 ``None``。
        """

        return "test_cancelled" if self.cancelled.is_set() else None

    def requested_at(self) -> datetime | None:
        """返回测试取消时间。

        Returns:
            已取消时返回固定 UTC 时间，否则返回 ``None``。
        """

        if not self.cancelled.is_set():
            return None
        return datetime(2026, 8, 12, tzinfo=timezone.utc)


class _BlobFirstUploadBlobRepository(FsDocumentBlobRepository):
    """证明 create blob 写入时 published source 仍不存在的仓储 spy。"""

    def __init__(
        self,
        workspace_root: Path,
        repository_set: _FsRepositorySet,
        source_repository: FsSourceDocumentRepository,
        events: list[str],
    ) -> None:
        """初始化 blob 仓储 spy。"""

        super().__init__(workspace_root, repository_set=repository_set)
        self._source_repository = source_repository
        self._events = events
        self.observed_source_absent: list[bool] = []

    def store_file(
        self,
        handle: SourceHandle | ProcessedHandle,
        filename: str,
        data: BinaryIO,
        *,
        batch: BatchToken,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> FileObjectMeta:
        """记录 published source 缺席事实后转发 batch blob 写入。"""

        if isinstance(handle, SourceHandle):
            try:
                self._source_repository.get_source_meta(
                    handle.ticker,
                    handle.document_id,
                    SourceKind(handle.source_kind),
                )
            except FileNotFoundError:
                self.observed_source_absent.append(True)
            else:
                self.observed_source_absent.append(False)
        self._events.append(f"store:{filename}")
        return super().store_file(
            handle,
            filename,
            data,
            batch=batch,
            content_type=content_type,
            metadata=metadata,
        )


class _FailingNthUploadBlobRepository(FsDocumentBlobRepository):
    """在指定次序的 staging blob 写入处注入失败。"""

    def __init__(
        self,
        workspace_root: Path,
        repository_set: _FsRepositorySet,
        *,
        fail_at: int,
    ) -> None:
        """初始化 blob failure injector。

        Args:
            workspace_root: 测试工作区。
            repository_set: 与 source/batch 共用的真实 FS core。
            fail_at: 从一开始计数的失败写入次序。

        Returns:
            无。

        Raises:
            ValueError: ``fail_at`` 不是正整数时抛出。
        """

        if fail_at <= 0:
            raise ValueError("fail_at 必须为正整数")
        super().__init__(workspace_root, repository_set=repository_set)
        self._fail_at = fail_at
        self._store_calls = 0

    def store_file(
        self,
        handle: SourceHandle | ProcessedHandle,
        filename: str,
        data: BinaryIO,
        *,
        batch: BatchToken,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> FileObjectMeta:
        """在目标写入次序抛出异常，否则转发真实 staging 写入。

        Args:
            handle: source 或 processed handle。
            filename: 待写文件名。
            data: 文件字节流。
            batch: caller-owned batch capability。
            content_type: 可选 MIME 类型。
            metadata: 可选文件元数据。

        Returns:
            成功写入的文件对象元数据。

        Raises:
            RuntimeError: 命中目标写入次序时抛出。
            OSError: 真实 staging 写入失败时抛出。
        """

        self._store_calls += 1
        if self._store_calls == self._fail_at:
            raise RuntimeError("forced replacement blob failure")
        return super().store_file(
            handle,
            filename,
            data,
            batch=batch,
            content_type=content_type,
            metadata=metadata,
        )


class _CancelOnNthCheck(CancellationToken):
    """第 N 次检查起返回取消的测试检查器。"""

    def __init__(self, cancel_at: int) -> None:
        """初始化检查器。

        Args:
            cancel_at: 从 1 开始计数的取消命中次数。

        Returns:
            无。

        Raises:
            ValueError: 取消次数不是正整数时抛出。
        """

        if cancel_at <= 0:
            raise ValueError("cancel_at 必须为正整数")
        self.cancel_at = cancel_at
        self.calls = 0

    def __call__(self) -> bool:
        """返回当前是否应取消。

        Args:
            无。

        Returns:
            达到指定检查次数后返回 ``True``。

        Raises:
            无。
        """

        self.calls += 1
        return self.calls >= self.cancel_at

    def is_cancelled(self) -> bool:
        """委托既有 checkpoint 计数。

        Returns:
            达到指定检查次数后返回 ``True``。
        """

        return self()

    def cancel_reason(self) -> str | None:
        """返回测试取消原因。

        Returns:
            已取消时返回固定原因，否则返回 ``None``。
        """

        return "test_cancelled" if self.calls >= self.cancel_at else None

    def requested_at(self) -> datetime | None:
        """返回测试取消时间。

        Returns:
            已取消时返回固定 UTC 时间，否则返回 ``None``。
        """

        if self.calls < self.cancel_at:
            return None
        return datetime(2026, 8, 12, tzinfo=timezone.utc)


class _FakeDoclingConverter:
    """记录调用并返回 typed Docling JSON bytes 的测试 converter。"""

    def __init__(self, calls: list[str] | None = None) -> None:
        """初始化 converter。

        Args:
            calls: 可选调用记录列表。

        Returns:
            无。
        """

        self.calls = calls

    async def convert_to_json_bytes(
        self,
        input_bytes: bytes,
        stream_name: str,
        *,
        config: DoclingConversionConfig,
        cancellation: CancellationToken | None,
    ) -> DoclingConversionResult:
        """返回与 public converter contract 一致的结果。

        Args:
            input_bytes: 输入字节。
            stream_name: 输入名称。
            config: 闭合转换配置。
            cancellation: canonical token。

        Returns:
            typed JSON bytes 结果。

        Raises:
            无。
        """

        del input_bytes, config, cancellation
        if self.calls is not None:
            self.calls.append(stream_name)
        data = ('{"name": "' + stream_name + '", "source": "docling"}').encode()
        return DoclingConversionResult(
            json_bytes=data,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )


class _CancelledDoclingConverter:
    """模拟 shared converter 已安全收口取消的 typed fake。"""

    async def convert_to_json_bytes(
        self,
        input_bytes: bytes,
        stream_name: str,
        *,
        config: DoclingConversionConfig,
        cancellation: CancellationToken | None,
    ) -> DoclingConversionResult:
        """抛出 shared converter cancellation。

        Args:
            input_bytes: 输入字节。
            stream_name: 输入名称。
            config: 闭合转换配置。
            cancellation: canonical token。

        Returns:
            不返回。

        Raises:
            DoclingConversionCancelledError: 始终抛出。
        """

        del input_bytes, stream_name, config, cancellation
        raise DoclingConversionCancelledError()


class _SelectiveFailingDoclingConverter:
    """按唯一文件名注入 typed Docling failure，并记录 fail-fast 顺序。"""

    def __init__(
        self,
        *,
        failing_name: str,
        error: DoclingConversionError,
        calls: list[str],
    ) -> None:
        """初始化逐文件 failure converter。

        Args:
            failing_name: 应抛出异常的 basename。
            error: 需要保留为 ``__cause__`` 的 typed Docling 异常。
            calls: 转换调用顺序记录。

        Returns:
            无。

        Raises:
            无。
        """

        self._failing_name = failing_name
        self._error = error
        self._calls = calls

    async def convert_to_json_bytes(
        self,
        input_bytes: bytes,
        stream_name: str,
        *,
        config: DoclingConversionConfig,
        cancellation: CancellationToken | None,
    ) -> DoclingConversionResult:
        """记录调用，在目标文件抛错，其余文件返回合法结果。

        Args:
            input_bytes: 原始文件字节。
            stream_name: 当前 basename。
            config: closed conversion config。
            cancellation: canonical cancellation token。

        Returns:
            非目标文件的合法 Docling JSON 结果。

        Raises:
            DoclingConversionError: 当前文件命中 failure fixture 时抛出。
        """

        del input_bytes, config, cancellation
        self._calls.append(stream_name)
        if stream_name == self._failing_name:
            raise self._error
        data = ('{"name": "' + stream_name + '"}').encode()
        return DoclingConversionResult(
            json_bytes=data,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )


def _publish_prepared_upload(
    *,
    service: DoclingUploadService,
    batching_repository: FsBatchingRepository,
    ticker: str,
    prepared: PreparedDoclingUpload,
    cancellation: CancellationToken | None = None,
) -> UploadOperationResult:
    """按 production top-level owner 规则发布 prepared upload。

    Args:
        service: 待测试的上传服务。
        batching_repository: 与 source/blob 共享 core 的 batching 仓储。
        ticker: 事务绑定 ticker。
        prepared: ``prepare_upload`` 返回的 typed plan。

    Returns:
        发布结果；无需 mutation 的结果直接返回。

    Raises:
        BaseException: mutation、rollback 或 commit 失败时按 owner 规则传播。
    """

    if isinstance(prepared, UploadOperationResult):
        return prepared
    return commit_prepared_upload_batch(
        service=service,
        batching_repository=batching_repository,
        batch=batching_repository.begin_batch(ticker),
        prepared=prepared,
        cancellation=cancellation,
    )


def _execute_upload(
    *,
    service: DoclingUploadService,
    batching_repository: FsBatchingRepository,
    ticker: str,
    source_kind: SourceKind,
    action: str,
    document_id: str,
    internal_document_id: str,
    form_type: str,
    files: list[Path],
    overwrite: bool,
    meta: dict[str, JsonValue],
    filing_primary: Path | None = None,
    cancellation_checker: CancellationToken | None = None,
) -> UploadOperationResult:
    """准备上传并由测试 top-level owner 执行短 publication transaction。

    Args:
        service: 待测试的上传服务。
        batching_repository: 与 source/blob 共享 core 的 batching 仓储。
        ticker: 股票代码。
        source_kind: source 类型。
        action: create/update/delete 动作。
        document_id: 文档 ID。
        internal_document_id: 内部文档 ID。
        form_type: 文档类型。
        files: 上传文件。
        overwrite: 是否覆盖。
        meta: source 业务元数据。
        filing_primary: filing upsert 的 explicit primary；其它请求为 ``None``。
        cancellation_checker: 可选取消检查器。

    Returns:
        完整上传结果。

    Raises:
        BaseException: prepare、publication、rollback 或 commit 失败时传播。
    """

    try:
        previous_meta = service._source_repository.get_source_meta(
            ticker,
            document_id,
            source_kind,
        )
    except FileNotFoundError:
        previous_meta = None
    selection = _selection_for_test(
        source_kind=source_kind,
        action=action,
        files=files,
        filing_primary=filing_primary,
    )
    prepared = asyncio.run(
        service.prepare_upload(
            ticker=ticker,
            source_kind=source_kind,
            action=action,
            document_id=document_id,
            internal_document_id=internal_document_id,
            form_type=form_type,
            selection=selection,
            overwrite=overwrite,
            previous_meta=previous_meta,
            meta=meta,
            repair_disposition=NoExistingSourceRepair(),
            cancellation=cancellation_checker,
        )
    )
    return _publish_prepared_upload(
        service=service,
        batching_repository=batching_repository,
        ticker=ticker,
        prepared=prepared,
        cancellation=cancellation_checker,
    )


def _selection_for_test(
    *,
    source_kind: SourceKind,
    action: str,
    files: list[Path],
    filing_primary: Path | None,
) -> FinsUploadFilingFiles | FinsUploadMaterialFiles:
    """按 production source/action contract 构造测试 selection。

    Args:
        source_kind: filing 或 material 来源类型。
        action: create、update 或 delete。
        files: 有序原始文件列表。
        filing_primary: filing upsert 的 explicit primary；其它请求为 ``None``。

    Returns:
        与 source kind 和 action 一致的 typed selection。

    Raises:
        ValueError: source kind 不受支持或 upsert 文件为空时抛出。
    """

    if source_kind is SourceKind.FILING:
        if action == "delete":
            return FinsUploadFilingFiles.for_delete()
        if filing_primary is None or filing_primary not in files:
            raise ValueError("filing upsert 测试必须显式提供集合内 primary")
        return FinsUploadFilingFiles.for_upsert(
            primary=filing_primary,
            companions=tuple(path for path in files if path != filing_primary),
        )
    if source_kind is SourceKind.MATERIAL:
        if action == "delete":
            return FinsUploadMaterialFiles.for_delete()
        return FinsUploadMaterialFiles.from_upsert_paths(tuple(files))
    raise ValueError(f"不支持的 source_kind: {source_kind}")


def _remove_published_filing_original(
    *,
    workspace_root: Path,
    source_repository: FsSourceDocumentRepository,
    document_id: str,
) -> None:
    """删除一个 storage 声明的 published filing original 以形成 repair target。

    Args:
        workspace_root: 当前测试工作区根。
        source_repository: published source owner。
        document_id: exact filing document ID。

    Returns:
        无。

    Raises:
        AssertionError: fixture 不含唯一可删除 original 时抛出。
        OSError: published original 删除失败时抛出。
        ValueError: persisted files contract 非法时抛出。
    """

    meta = source_repository.get_source_meta("AAPL", document_id, SourceKind.FILING)
    raw_files = meta.get("files")
    if not isinstance(raw_files, list):
        raise ValueError("repair fixture files 必须是数组")
    original_names: list[str] = []
    for raw_file in raw_files:
        if not isinstance(raw_file, dict) or raw_file.get("source") != "original":
            continue
        raw_name = raw_file.get("name")
        if not isinstance(raw_name, str):
            raise ValueError("repair fixture original name 必须是字符串")
        original_names.append(raw_name)
    if not original_names:
        raise AssertionError("repair fixture 必须至少包含一个 original")
    locator = source_repository.get_source_document_locator(
        "AAPL",
        document_id,
        SourceKind.FILING,
    )
    (workspace_root / locator / original_names[0]).unlink()


def _remove_published_material_declared_file(
    *,
    workspace_root: Path,
    source_repository: FsSourceDocumentRepository,
    document_id: str,
) -> None:
    """删除一个 storage 声明的 published material 文件以形成 non-target damage。

    Args:
        workspace_root: 当前测试工作区根。
        source_repository: published source owner。
        document_id: exact material document ID。

    Returns:
        无。

    Raises:
        AssertionError: fixture 不含可删除的 declared file 时抛出。
        OSError: published material 文件删除失败时抛出。
        ValueError: persisted files contract 非法时抛出。
    """

    meta = source_repository.get_source_meta("AAPL", document_id, SourceKind.MATERIAL)
    raw_files = meta.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise AssertionError("material repair blocker 必须包含 declared file")
    raw_file = raw_files[0]
    if not isinstance(raw_file, dict):
        raise ValueError("material repair blocker file entry 必须是对象")
    raw_name = raw_file.get("name")
    if not isinstance(raw_name, str):
        raise ValueError("material repair blocker file name 必须是字符串")
    locator = source_repository.get_source_document_locator(
        "AAPL",
        document_id,
        SourceKind.MATERIAL,
    )
    (workspace_root / locator / raw_name).unlink()


def _prepare_existing_filing_repair(
    *,
    service: DoclingUploadService,
    source_repository: FsSourceDocumentRepository,
    document_id: str,
    files: tuple[Path, ...],
    primary: Path,
) -> _PreparedAssetMutation:
    """用 published repair classification 准备 authoritative filing repair mutation。

    Args:
        service: 待测试的 Docling 上传服务。
        source_repository: published integrity 与 meta owner。
        document_id: exact filing document ID。
        files: 完整 authoritative original 输入。
        primary: files 中唯一 authoritative primary。

    Returns:
        已完成全部读取与唯一 primary 转换的 repair mutation。

    Raises:
        AssertionError: fixture 未产出 prepared asset mutation 时抛出。
        BaseException: preparation 的真实 typed failure 原样传播。
    """

    expected_integrity = source_repository.classify_source_integrity(
        "AAPL",
        document_id,
        SourceKind.FILING,
    )
    previous_meta = source_repository.get_source_meta(
        "AAPL",
        document_id,
        SourceKind.FILING,
    )
    prepared = asyncio.run(
        service.prepare_upload(
            ticker="AAPL",
            source_kind=SourceKind.FILING,
            action="update",
            document_id=document_id,
            internal_document_id=document_id,
            form_type="10-K",
            selection=FinsUploadFilingFiles.for_upsert(
                primary=primary,
                companions=tuple(file_path for file_path in files if file_path != primary),
            ),
            overwrite=False,
            previous_meta=previous_meta,
            meta={"ingest_method": "upload"},
            repair_disposition=ExistingSourceAutoRepair(
                expected_integrity=expected_integrity
            ),
            cancellation=None,
        )
    )
    if not isinstance(prepared, _PreparedAssetMutation):
        raise AssertionError("repair preparation 必须返回 asset mutation")
    return prepared


def _build_service_context(tmp_path: Path) -> _UploadServiceContext:
    """构建上传服务测试上下文。

    Args:
        tmp_path: 临时工作区目录。

    Returns:
        上传服务测试上下文。

    Raises:
        OSError: 底层仓储初始化失败时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = FsBatchingRepository(tmp_path, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    service = DoclingUploadService(
        source_repository=source_repository,
        blob_repository=blob_repository,
        docling_converter=_FakeDoclingConverter(),
    )
    return _UploadServiceContext(
        batching_repository=batching_repository,
        source_repository=source_repository,
        blob_repository=blob_repository,
        service=service,
    )


def _build_batch_tracking_service_context(tmp_path: Path) -> _UploadServiceContext:
    """构建可观察 prepare 阶段是否错误开启 batch 的测试上下文。

    Args:
        tmp_path: 临时工作区目录。

    Returns:
        batching repository 带调用计数的上传服务测试上下文。

    Raises:
        OSError: 底层仓储初始化失败时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _BatchIdentityUploadBatchingRepository(tmp_path, repository_set, [])
    source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    service = DoclingUploadService(
        source_repository=source_repository,
        blob_repository=blob_repository,
        docling_converter=_FakeDoclingConverter(),
    )
    return _UploadServiceContext(
        batching_repository=batching_repository,
        source_repository=source_repository,
        blob_repository=blob_repository,
        service=service,
    )


def _prepare_material_for_admission_test(
    *,
    service: DoclingUploadService,
    files: list[Path],
    cancellation: CancellationToken | None = None,
) -> PreparedDoclingUpload:
    """调用 material prepare owner，不进入 publication batch。

    Args:
        service: 使用目标 converter 的上传服务。
        files: 按用户请求顺序排列的 material 文件。
        cancellation: 可选公共取消观察 token。

    Returns:
        prepare 结果或 typed publication plan。

    Raises:
        DoclingConversionError: 任一 material 转换失败时原样抛出。
        OSError: 文件读取失败时抛出。
        ValueError: 测试输入不符合 upload contract 时抛出。
    """

    return asyncio.run(
        service.prepare_upload(
            ticker="AAPL",
            source_kind=SourceKind.MATERIAL,
            action="create",
            document_id="material_admission",
            internal_document_id="material_admission",
            form_type="MATERIAL_OTHER",
            selection=FinsUploadMaterialFiles.from_upsert_paths(tuple(files)),
            overwrite=False,
            previous_meta=None,
            meta={"ingest_method": "upload"},
            repair_disposition=NoExistingSourceRepair(),
            cancellation=cancellation,
        )
    )


def _prepare_filing_for_admission_test(
    *,
    service: DoclingUploadService,
    files: list[Path],
    primary: Path,
) -> PreparedDoclingUpload:
    """调用 filing prepare owner，不进入 publication batch。

    Args:
        service: 使用目标 converter 的上传服务。
        files: 按用户请求顺序排列的 filing 文件。
        primary: explicit filing primary。

    Returns:
        prepare 成功时返回 typed publication plan。

    Raises:
        FinsUploadFailureError: empty/corrupt filing 被内容 admission 拒绝时抛出。
        OSError: 文件读取失败时抛出。
        ValueError: 测试输入不符合 upload contract 时抛出。
    """

    return asyncio.run(
        service.prepare_upload(
            ticker="AAPL",
            source_kind=SourceKind.FILING,
            action="create",
            document_id="filing_admission",
            internal_document_id="filing_admission",
            form_type="Q1",
            selection=FinsUploadFilingFiles.for_upsert(
                primary=primary,
                companions=tuple(path for path in files if path != primary),
            ),
            overwrite=False,
            previous_meta=None,
            meta={"ingest_method": "upload"},
            repair_disposition=NoExistingSourceRepair(),
            cancellation=None,
        )
    )


@pytest.mark.parametrize(
    ("file_name", "expected_label"),
    (
        ("empty.pdf", "empty.pdf"),
        ("empty.docx", "empty.docx"),
        ("job_id_notes.pdf", "输入文件（文件名已隐藏）"),
        ("财报正文.pdf", "输入文件（文件名已隐藏）"),
        ("line\nbreak.pdf", "输入文件（文件名已隐藏）"),
        ("report\u202ename.pdf", "输入文件（文件名已隐藏）"),
        (f"{'a' * 241}.pdf", "输入文件（文件名已隐藏）"),
    ),
)
def test_empty_filing_is_rejected_before_converter_and_publication(
    tmp_path: Path,
    file_name: str,
    expected_label: str,
) -> None:
    """zero-byte filing 必须在 converter 与 publication 之前形成 typed failure。

    Args:
        tmp_path: pytest 临时目录。
        file_name: 覆盖普通与无法原样公开的合法 basename。
        expected_label: reason 应携带的 canonical public label。

    Returns:
        无。

    Raises:
        AssertionError: empty contract、调用顺序或 published tree 漂移时抛出。
    """

    calls: list[str] = []
    context = _build_batch_tracking_service_context(tmp_path)
    context.service._docling_converter = _FakeDoclingConverter(calls)
    empty_file = tmp_path / file_name
    empty_file.write_bytes(b"")

    with pytest.raises(FinsUploadFailureError) as exc_info:
        _prepare_filing_for_admission_test(
            service=context.service,
            files=[empty_file],
            primary=empty_file,
        )

    failure = exc_info.value.failure
    assert failure.kind is FinsUploadFailureKind.CONTENT
    assert failure.code is FinsUploadFailureCode.EMPTY_INPUT_FILE
    assert failure.message == "文件为空，无法上传"
    assert failure.retry_hint == "请提供非空文件后重试"
    assert failure.file_label == expected_label
    assert calls == []
    assert published_tree_sha256(tmp_path, "AAPL") == {}


@pytest.mark.parametrize(
    ("suffix", "kind", "safe_message"),
    (
        (".pdf", DoclingConversionFailureKind.CONVERTER_CONSTRUCTION, "Docling converter construction failed"),
        (".docx", DoclingConversionFailureKind.CONVERTER_EXECUTION, "Docling conversion execution failed"),
        (".pdf", DoclingConversionFailureKind.RESULT_SERIALIZATION, "Docling conversion result serialization failed"),
        (".docx", DoclingConversionFailureKind.IPC_PROTOCOL, "Docling conversion IPC protocol failed"),
        (".pdf", DoclingConversionFailureKind.CHILD_CRASH, "Docling conversion child crashed"),
        (".docx", DoclingConversionFailureKind.CLEANUP, "Docling conversion cleanup failed"),
    ),
)
def test_corrupt_filing_wraps_each_closed_docling_failure_with_label_and_cause(
    tmp_path: Path,
    suffix: str,
    kind: DoclingConversionFailureKind,
    safe_message: str,
) -> None:
    """逐文件 conversion owner 必须稳定映射 code、label 并保留原 cause。

    Args:
        tmp_path: pytest 临时目录。
        suffix: PDF/DOCX 代表性后缀。
        kind: Docling closed failure kind。
        safe_message: converter owner 对该 kind 的固定文案。

    Returns:
        无。

    Raises:
        AssertionError: typed projection、cause 或 publication 边界漂移时抛出。
    """

    context = _build_service_context(tmp_path)
    filing_file = tmp_path / f"corrupt{suffix}"
    filing_file.write_bytes(b"corrupt input")
    cause = DoclingConversionError(kind, safe_message, 17)
    calls: list[str] = []
    context.service._docling_converter = _SelectiveFailingDoclingConverter(
        failing_name=filing_file.name,
        error=cause,
        calls=calls,
    )

    with pytest.raises(FinsUploadFailureError) as exc_info:
        _prepare_filing_for_admission_test(
            service=context.service,
            files=[filing_file],
            primary=filing_file,
        )

    failure = exc_info.value.failure
    assert failure.kind is FinsUploadFailureKind.CONTENT
    assert failure.file_label == filing_file.name
    assert failure.message == "文件无法解析或已损坏，请检查文件后重试"
    assert safe_message not in str(failure)
    assert str(filing_file) not in str(failure)
    assert exc_info.value.__cause__ is cause
    assert calls == [filing_file.name]
    assert published_tree_sha256(tmp_path, "AAPL") == {}


def test_corrupt_primary_with_valid_companions_fails_without_publication(
    tmp_path: Path,
) -> None:
    """损坏 primary 必须只转换一次并在 companions 发布前失败。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: fail-fast 或 zero-publication 不变量漂移时抛出。
    """

    context = _build_batch_tracking_service_context(tmp_path)
    files = [tmp_path / name for name in ("bad.pdf", "later.docx")]
    for file_path in files:
        file_path.write_bytes(b"filing input")
    cause = DoclingConversionError(
        DoclingConversionFailureKind.CONVERTER_EXECUTION,
        "Docling conversion execution failed",
        None,
    )
    calls: list[str] = []
    context.service._docling_converter = _SelectiveFailingDoclingConverter(
        failing_name=files[0].name,
        error=cause,
        calls=calls,
    )

    with pytest.raises(FinsUploadFailureError):
        _prepare_filing_for_admission_test(
            service=context.service,
            files=files,
            primary=files[0],
        )

    assert calls == [files[0].name]
    assert isinstance(context.batching_repository, _BatchIdentityUploadBatchingRepository)
    assert context.batching_repository.begin_calls == 0
    assert published_tree_sha256(tmp_path, "AAPL") == {}


@pytest.mark.parametrize(
    ("names", "primary_index"),
    (
        (("report.xsd", "report.html"), 1),
        (("sheet.xlsx", "primary.docx", "appendix.docx"), 1),
    ),
)
def test_filing_converts_only_primary_and_publishes_all_companions(
    tmp_path: Path,
    names: tuple[str, ...],
    primary_index: int,
) -> None:
    """filing 只转换 primary，companions 作为 original 同批发布。

    Args:
        tmp_path: pytest 临时目录。
        names: 用户请求顺序中的文件名。
        primary_index: explicit primary 在请求中的位置。

    Returns:
        无。

    Raises:
        AssertionError: 转换、事件、计数或 primary contract 漂移时抛出。
    """

    calls: list[str] = []
    context = _build_service_context(tmp_path)
    context.service._docling_converter = _FakeDoclingConverter(calls)
    files = [(tmp_path / name).resolve(strict=False) for name in names]
    for file_path in files:
        file_path.write_bytes(f"original:{file_path.name}".encode())
    primary = files[primary_index]
    ordered_files = [primary, *(path for path in files if path != primary)]
    original_identities = [
        _build_filing_original_asset_identity(path)
        for path in ordered_files
    ]
    expected_primary = f"{original_identities[0]}_docling.json"

    result = _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="create",
        document_id="filing_roles",
        internal_document_id="filing_roles",
        form_type="10-K",
        files=files,
        filing_primary=primary,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    meta = context.source_repository.get_source_meta(
        "AAPL",
        "filing_roles",
        SourceKind.FILING,
    )
    entries = meta["files"]
    assert isinstance(entries, list)

    assert calls == [primary.name]
    assert result.stored_file_count == len(names)
    assert result.payload["primary_document"] == expected_primary
    assert meta["primary_document"] == expected_primary
    assert len(entries) == len(names) + 1
    assert [event.name for event in result.file_events if event.event_type == "conversion_started"] == [primary.name]
    original_uploads = [
        event.name
        for event in result.file_events
        if event.event_type == "file_uploaded" and event.payload["source"] == "original"
    ]
    assert original_uploads == [path.name for path in ordered_files]
    assert [entry["name"] for entry in entries] == [*original_identities, expected_primary]
    for entry, file_path in zip(entries[:-1], ordered_files, strict=True):
        assert entry["original_filename"] == file_path.name
        assert "derived_from" not in entry
        assert str(entry["uri"]).endswith(f"/{entry['name']}")
    derived_entry = entries[-1]
    assert derived_entry["original_filename"] == primary.name
    assert derived_entry["derived_from"] == original_identities[0]
    assert str(derived_entry["uri"]).endswith(f"/{expected_primary}")


def test_filing_same_basename_assets_are_collision_free_and_path_private(tmp_path: Path) -> None:
    """不同目录同 basename 必须产生不同且不泄漏绝对路径的 filing identity。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: identity、metadata 或 physical publication 发生碰撞时抛出。
    """

    first_dir = (tmp_path / "first").resolve(strict=False)
    second_dir = (tmp_path / "second").resolve(strict=False)
    first_dir.mkdir()
    second_dir.mkdir()
    first = first_dir / "report.pdf"
    second = second_dir / "report.pdf"
    first.write_bytes(b"first report")
    second.write_bytes(b"second report")
    context = _build_service_context(tmp_path)

    result = _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="create",
        document_id="same_basename",
        internal_document_id="same_basename",
        form_type="10-K",
        files=[first, second],
        filing_primary=second,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    meta = context.source_repository.get_source_meta("AAPL", "same_basename", SourceKind.FILING)
    entries = meta["files"]
    assert isinstance(entries, list)
    originals = [entry for entry in entries if entry["source"] == "original"]
    identities = [str(entry["name"]) for entry in originals]
    expected_primary_original = _build_filing_original_asset_identity(second)

    assert len(identities) == len(set(identities)) == 2
    assert [entry["original_filename"] for entry in originals] == ["report.pdf", "report.pdf"]
    assert all(str(tmp_path) not in identity for identity in identities)
    assert all(len(identity.removeprefix("original-").removesuffix(".pdf")) == 64 for identity in identities)
    assert result.payload["primary_document"] == f"{expected_primary_original}_docling.json"
    handle = SourceHandle("AAPL", "same_basename", SourceKind.FILING.value)
    assert {entry.uri.rsplit("/", maxsplit=1)[-1] for entry in context.blob_repository.list_files(handle)} == {
        *identities,
        f"{expected_primary_original}_docling.json",
    }
    with context.source_repository.read_source_snapshot(
        "AAPL",
        "same_basename",
        SourceKind.FILING,
        materialize_files=True,
    ) as snapshot:
        primary_source = snapshot.get_primary_source()
        with primary_source.open() as stream:
            assert stream.read() == b'{"name": "report.pdf", "source": "docling"}'
        assert primary_source.uri.endswith(f"/{expected_primary_original}_docling.json")


def test_filing_identity_is_stable_and_request_order_independent(tmp_path: Path) -> None:
    """同一 normalized path 的 filing identity 必须稳定且不依赖请求顺序。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: identity 不稳定、混入顺序或泄漏路径明文时抛出。
    """

    first = (tmp_path / "first.pdf").resolve(strict=False)
    second = (tmp_path / "second.pdf").resolve(strict=False)
    forward = {
        path: _build_filing_original_asset_identity(path)
        for path in (first, second)
    }
    reverse = {
        path: _build_filing_original_asset_identity(path)
        for path in (second, first)
    }

    assert forward == reverse
    assert forward[first] == _build_filing_original_asset_identity(first)
    assert forward[first] != forward[second]
    assert all(path.as_posix() not in identity for path, identity in forward.items())


def test_empty_filing_companion_fails_before_conversion_and_publication(tmp_path: Path) -> None:
    """空 companion 仍须在转换与 publication 前由 original 读取 owner 拒绝。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: companion 被跳过读取或产生副作用时抛出。
    """

    calls: list[str] = []
    context = _build_service_context(tmp_path)
    context.service._docling_converter = _FakeDoclingConverter(calls)
    primary = tmp_path / "primary.html"
    companion = tmp_path / "schema.xsd"
    primary.write_bytes(b"primary")
    companion.write_bytes(b"")

    with pytest.raises(FinsUploadFailureError) as exc_info:
        _prepare_filing_for_admission_test(
            service=context.service,
            files=[primary, companion],
            primary=primary,
        )

    assert exc_info.value.failure.code is FinsUploadFailureCode.EMPTY_INPUT_FILE
    assert exc_info.value.failure.file_label == companion.name
    assert calls == []
    assert published_tree_sha256(tmp_path, "AAPL") == {}


def test_filing_preparation_exactly_associates_derived_with_primary_original(tmp_path: Path) -> None:
    """filing preparation 必须在 typed plan 中保存 exact original/derived 关联。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: pending asset 三字段或 converter 绑定漂移时抛出。
    """

    calls: list[str] = []
    context = _build_service_context(tmp_path)
    context.service._docling_converter = _FakeDoclingConverter(calls)
    companion = (tmp_path / "report.xsd").resolve(strict=False)
    primary = (tmp_path / "report.html").resolve(strict=False)
    companion.write_bytes(b"companion")
    primary.write_bytes(b"primary")

    prepared = asyncio.run(
        context.service.prepare_upload(
            ticker="AAPL",
            source_kind=SourceKind.FILING,
            action="create",
            document_id="exact_association",
            internal_document_id="exact_association",
            form_type="10-K",
            selection=FinsUploadFilingFiles.for_upsert(
                primary=primary,
                companions=(companion,),
            ),
            overwrite=False,
            previous_meta=None,
            meta={"ingest_method": "upload"},
            repair_disposition=NoExistingSourceRepair(),
            cancellation=None,
        )
    )
    assert isinstance(prepared, _PreparedAssetMutation)
    primary_identity = _build_filing_original_asset_identity(primary)
    companion_identity = _build_filing_original_asset_identity(companion)

    assert calls == [primary.name]
    assert [(asset.name, asset.original_filename, asset.derived_from) for asset in prepared.pending_assets] == [
        (primary_identity, primary.name, None),
        (companion_identity, companion.name, None),
        (f"{primary_identity}_docling.json", primary.name, primary_identity),
    ]
    assert prepared.primary_document == f"{primary_identity}_docling.json"
    assert [event.name for event in prepared.conversion_events] == [primary.name]


def test_filing_generated_identity_collision_fails_before_converter_and_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """defensive filing identity collision 必须在 converter/publication 前 fail closed。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest 属性替换器。

    Returns:
        无。

    Raises:
        AssertionError: collision 越过 preparation owner 时抛出。
    """

    def collide(_: Path) -> str:
        """为两个不同路径返回同一合法形状 identity。

        Args:
            _: 忽略的 normalized path。

        Returns:
            固定 collision identity。

        Raises:
            无。
        """

        return f"original-{'0' * 64}.pdf"

    calls: list[str] = []
    context = _build_batch_tracking_service_context(tmp_path)
    context.service._docling_converter = _FakeDoclingConverter(calls)
    primary = (tmp_path / "primary.pdf").resolve(strict=False)
    companion = (tmp_path / "companion.pdf").resolve(strict=False)
    primary.write_bytes(b"primary")
    companion.write_bytes(b"companion")
    monkeypatch.setattr(
        "dayu.fins.pipelines.docling_upload_service._build_filing_original_asset_identity",
        collide,
    )

    with pytest.raises(RuntimeError, match="identity 必须唯一"):
        _prepare_filing_for_admission_test(
            service=context.service,
            files=[primary, companion],
            primary=primary,
        )

    assert calls == []
    assert isinstance(context.batching_repository, _BatchIdentityUploadBatchingRepository)
    assert context.batching_repository.begin_calls == 0
    assert published_tree_sha256(tmp_path, "AAPL") == {}


def test_execute_upload_create_material_success(tmp_path: Path) -> None:
    """create 上传应写入原文件与 Docling 主文件。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    context = _build_service_context(tmp_path)
    sample_file = tmp_path / "deck.pdf"
    sample_file.write_text("hello", encoding="utf-8")

    result = _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.MATERIAL,
        action="create",
        document_id="mat_demo",
        internal_document_id="mat_demo",
        form_type="MATERIAL_OTHER",
        files=[sample_file],
        overwrite=False,
        meta={"material_name": "Deck", "ingest_method": "upload"},
    )

    assert result.status == "uploaded"
    assert result.stored_file_count == 1
    assert result.document_id == "mat_demo"
    assert len(result.file_events) == 3
    assert result.file_events[0].event_type == "conversion_started"
    meta = context.source_repository.get_source_meta("AAPL", "mat_demo", SourceKind.MATERIAL)
    assert str(meta["primary_document"]).endswith("_docling.json")
    assert meta["source_provider"] == "user_upload"
    assert len(meta["files"]) == 2


def test_execute_upload_material_converts_every_selected_file(tmp_path: Path) -> None:
    """material 多文件必须全部转换并保持首项 Docling primary。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: material 被 filing 单转换语义误伤时抛出。
    """

    calls: list[str] = []
    context = _build_service_context(tmp_path)
    context.service._docling_converter = _FakeDoclingConverter(calls)
    files = [tmp_path / "first.pdf", tmp_path / "second.docx"]
    for file_path in files:
        file_path.write_bytes(file_path.name.encode())

    result = _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.MATERIAL,
        action="create",
        document_id="material_multiple",
        internal_document_id="material_multiple",
        form_type="MATERIAL_OTHER",
        files=files,
        overwrite=False,
        meta={"material_name": "Deck", "ingest_method": "upload"},
    )

    assert calls == ["first.pdf", "second.docx"]
    assert result.stored_file_count == 2
    assert result.payload["primary_document"] == "first_docling.json"
    assert len(result.file_events) == 6
    meta = context.source_repository.get_source_meta(
        "AAPL",
        "material_multiple",
        SourceKind.MATERIAL,
    )
    entries = meta["files"]
    assert isinstance(entries, list)
    assert [entry["name"] for entry in entries] == [
        "first.pdf",
        "second.docx",
        "first_docling.json",
        "second_docling.json",
    ]
    assert all("original_filename" not in entry for entry in entries)
    assert all("derived_from" not in entry for entry in entries)
    assert [event.name for event in result.file_events if event.event_type == "file_uploaded"] == [
        "first.pdf",
        "second.docx",
        "first_docling.json",
        "second_docling.json",
    ]


def test_prepare_material_cancellation_before_second_conversion_discards_partial_work(
    tmp_path: Path,
) -> None:
    """第二项转换前取消必须丢弃首项 partial plan 且不得开启 publication batch。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 取消结果、事件丢弃或零发布边界漂移时抛出。
    """

    calls: list[str] = []
    context = _build_batch_tracking_service_context(tmp_path)
    context.service._docling_converter = _FakeDoclingConverter(calls)
    files = [tmp_path / "first.pdf", tmp_path / "second.docx"]
    for file_path in files:
        file_path.write_bytes(file_path.name.encode())
    cancellation = _CancelOnNthCheck(cancel_at=4)

    prepared = _prepare_material_for_admission_test(
        service=context.service,
        files=files,
        cancellation=cancellation,
    )

    assert isinstance(prepared, UploadOperationResult)
    assert prepared.status == "cancelled"
    assert prepared.file_events == []
    assert prepared.stored_file_count == 0
    assert calls == ["first.pdf"]
    assert isinstance(context.batching_repository, _BatchIdentityUploadBatchingRepository)
    assert context.batching_repository.begin_calls == 0
    assert published_tree_sha256(tmp_path, "AAPL") == {}
    with pytest.raises(FileNotFoundError):
        context.source_repository.get_source_meta(
            "AAPL",
            "material_admission",
            SourceKind.MATERIAL,
        )


def test_prepare_material_nth_conversion_failure_discards_partial_work(
    tmp_path: Path,
) -> None:
    """material 第 N 项 typed conversion failure 必须原样传播且零发布。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: fail-fast、异常身份或零发布边界漂移时抛出。
    """

    calls: list[str] = []
    context = _build_batch_tracking_service_context(tmp_path)
    files = [tmp_path / "ok.pdf", tmp_path / "corrupt.docx"]
    for file_path in files:
        file_path.write_bytes(file_path.name.encode())
    cause = DoclingConversionError(
        DoclingConversionFailureKind.CONVERTER_EXECUTION,
        "Docling conversion execution failed",
        19,
    )
    context.service._docling_converter = _SelectiveFailingDoclingConverter(
        failing_name="corrupt.docx",
        error=cause,
        calls=calls,
    )

    with pytest.raises(DoclingConversionError) as exc_info:
        _prepare_material_for_admission_test(service=context.service, files=files)

    assert exc_info.value is cause
    assert calls == ["ok.pdf", "corrupt.docx"]
    assert isinstance(context.batching_repository, _BatchIdentityUploadBatchingRepository)
    assert context.batching_repository.begin_calls == 0
    assert published_tree_sha256(tmp_path, "AAPL") == {}
    with pytest.raises(FileNotFoundError):
        context.source_repository.get_source_meta(
            "AAPL",
            "material_admission",
            SourceKind.MATERIAL,
        )


@pytest.mark.parametrize(
    ("source_kind", "selection"),
    (
        (
            SourceKind.FILING,
            FinsUploadMaterialFiles.from_upsert_paths((Path("material.pdf"),)),
        ),
        (
            SourceKind.MATERIAL,
            FinsUploadFilingFiles.for_upsert(
                primary=Path("filing.pdf"),
                companions=(),
            ),
        ),
    ),
)
def test_prepare_upload_rejects_source_kind_selection_mismatch_before_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_kind: SourceKind,
    selection: FinsUploadFilingFiles | FinsUploadMaterialFiles,
) -> None:
    """source kind 与 selection 类型错配必须在任何文件读取和转换前拒绝。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: 文件读取禁用夹具。
        source_kind: 当前 source kind。
        selection: 与 source kind 故意错配的 typed selection。

    Returns:
        无。

    Raises:
        AssertionError: 非法组合越过入口边界时抛出。
    """

    calls: list[str] = []
    context = _build_service_context(tmp_path)
    context.service._docling_converter = _FakeDoclingConverter(calls)

    def reject_read(path: Path) -> bytes:
        """拒绝任何意外文件读取。

        Args:
            path: 意外读取的路径。

        Returns:
            不返回。

        Raises:
            AssertionError: 始终抛出。
        """

        raise AssertionError(f"非法 selection 触发文件读取: {path.name}")

    monkeypatch.setattr(Path, "read_bytes", reject_read)

    with pytest.raises(ValueError, match="selection"):
        asyncio.run(
            context.service.prepare_upload(
                ticker="AAPL",
                source_kind=source_kind,
                action="create",
                document_id="invalid_selection",
                internal_document_id="invalid_selection",
                form_type="TEST",
                selection=selection,
                overwrite=False,
                previous_meta=None,
                meta={},
                repair_disposition=NoExistingSourceRepair(),
                cancellation=None,
            )
        )

    assert calls == []
    assert published_tree_sha256(tmp_path, "AAPL") == {}


@pytest.mark.parametrize(
    ("source_kind", "action", "use_empty"),
    (
        (SourceKind.FILING, "create", True),
        (SourceKind.FILING, "update", True),
        (SourceKind.FILING, "delete", False),
        (SourceKind.MATERIAL, "create", True),
        (SourceKind.MATERIAL, "update", True),
        (SourceKind.MATERIAL, "delete", False),
    ),
)
def test_prepare_upload_rejects_action_emptiness_mismatch_before_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_kind: SourceKind,
    action: str,
    use_empty: bool,
) -> None:
    """create/update 与 delete 的 selection 空性必须双向严格一致。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: 文件读取禁用夹具。
        source_kind: filing 或 material。
        action: 当前动作。
        use_empty: 是否构造 delete empty selection。

    Returns:
        无。

    Raises:
        AssertionError: 非法组合触发文件读取、转换或 publication 时抛出。
    """

    calls: list[str] = []
    context = _build_service_context(tmp_path)
    context.service._docling_converter = _FakeDoclingConverter(calls)
    candidate = Path("candidate.pdf")
    if source_kind is SourceKind.FILING:
        selection: FinsUploadFilingFiles | FinsUploadMaterialFiles = (
            FinsUploadFilingFiles.for_delete()
            if use_empty
            else FinsUploadFilingFiles.for_upsert(primary=candidate, companions=())
        )
    else:
        selection = (
            FinsUploadMaterialFiles.for_delete()
            if use_empty
            else FinsUploadMaterialFiles.from_upsert_paths((candidate,))
        )

    def reject_read(path: Path) -> bytes:
        """拒绝任何意外文件读取。

        Args:
            path: 意外读取的路径。

        Returns:
            不返回。

        Raises:
            AssertionError: 始终抛出。
        """

        raise AssertionError(f"非法 action/selection 触发文件读取: {path.name}")

    monkeypatch.setattr(Path, "read_bytes", reject_read)

    with pytest.raises(ValueError, match="selection"):
        asyncio.run(
            context.service.prepare_upload(
                ticker="AAPL",
                source_kind=source_kind,
                action=action,
                document_id="invalid_emptiness",
                internal_document_id="invalid_emptiness",
                form_type="TEST",
                selection=selection,
                overwrite=False,
                previous_meta=None,
                meta={},
                repair_disposition=NoExistingSourceRepair(),
                cancellation=None,
            )
        )

    assert calls == []
    assert published_tree_sha256(tmp_path, "AAPL") == {}


def test_prepare_maps_shared_converter_cancel_without_starting_publication(tmp_path: Path) -> None:
    """converter cancel 必须收敛为 cancelled plan 且不创建 document batch。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: converter cancel 被投影为失败或产生 publication 时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _BatchIdentityUploadBatchingRepository(tmp_path, repository_set, [])
    source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    service = DoclingUploadService(
        source_repository=source_repository,
        blob_repository=FsDocumentBlobRepository(tmp_path, repository_set=repository_set),
        docling_converter=_CancelledDoclingConverter(),
    )
    sample_file = tmp_path / "deck.pdf"
    sample_file.write_text("cancelled", encoding="utf-8")

    prepared = asyncio.run(
        service.prepare_upload(
            ticker="AAPL",
            source_kind=SourceKind.MATERIAL,
            action="create",
            document_id="mat_cancelled",
            internal_document_id="mat_cancelled",
            form_type="MATERIAL_OTHER",
            selection=FinsUploadMaterialFiles.from_upsert_paths((sample_file,)),
            overwrite=False,
            previous_meta=None,
            meta={"material_name": "Deck", "ingest_method": "upload"},
            repair_disposition=NoExistingSourceRepair(),
            cancellation=None,
        )
    )

    assert isinstance(prepared, UploadOperationResult)
    assert prepared.status == "cancelled"
    assert prepared.stored_file_count == 0
    assert batching_repository.begin_calls == 0
    with pytest.raises(FileNotFoundError):
        source_repository.get_source_meta("AAPL", "mat_cancelled", SourceKind.MATERIAL)


def test_execute_upload_writes_blobs_before_single_complete_source(tmp_path: Path) -> None:
    """上传 create 必须 blob-first，写 blob 时 published source 尚不存在。"""

    events: list[str] = []
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = FsBatchingRepository(tmp_path, repository_set=repository_set)
    source_repository = _SpyUploadSourceRepository(tmp_path, repository_set, events)
    blob_repository = _BlobFirstUploadBlobRepository(tmp_path, repository_set, source_repository, events)
    service = DoclingUploadService(
        source_repository=source_repository,
        blob_repository=blob_repository,
        docling_converter=_FakeDoclingConverter(),
    )
    sample_file = tmp_path / "deck.pdf"
    sample_file.write_text("hello", encoding="utf-8")

    result = _execute_upload(
        service=service,
        batching_repository=batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.MATERIAL,
        action="create",
        document_id="mat_staged",
        internal_document_id="mat_staged",
        form_type="MATERIAL_OTHER",
        files=[sample_file],
        overwrite=False,
        meta={"material_name": "Deck", "ingest_method": "upload"},
    )
    meta = source_repository.get_source_meta("AAPL", "mat_staged", SourceKind.MATERIAL)

    assert result.status == "uploaded"
    assert result.stored_file_count == 1
    assert events == ["store:deck.pdf", "store:deck_docling.json"]
    assert blob_repository.observed_source_absent == [True, True]
    assert meta["ingest_complete"] is True


def test_execute_upload_uses_one_caller_batch_for_blobs_and_final_meta(tmp_path: Path) -> None:
    """upload create 的 blobs 与唯一 final meta 必须共享 caller token。"""

    events: list[str] = []
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _BatchIdentityUploadBatchingRepository(tmp_path, repository_set, events)
    source_repository = _BatchIdentityUploadSourceRepository(
        tmp_path,
        repository_set,
        events,
        batching_repository,
    )
    blob_repository = _BatchIdentityUploadBlobRepository(
        tmp_path,
        repository_set,
        batching_repository,
    )
    service = DoclingUploadService(
        source_repository=source_repository,
        blob_repository=blob_repository,
        docling_converter=_FakeDoclingConverter(),
    )
    sample_file = tmp_path / "deck.pdf"
    sample_file.write_text("hello", encoding="utf-8")

    result = _execute_upload(
        service=service,
        batching_repository=batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.MATERIAL,
        action="create",
        document_id="mat_identity",
        internal_document_id="mat_identity",
        form_type="MATERIAL_OTHER",
        files=[sample_file],
        overwrite=False,
        meta={"material_name": "Deck", "ingest_method": "upload"},
    )

    batch_ids = {batch_id for _, batch_id in batching_repository.phase_batch_ids}
    phases = [phase for phase, _ in batching_repository.phase_batch_ids]
    assert result.status == "uploaded"
    assert result.stored_file_count == 1
    assert batch_ids and len(batch_ids) == 1
    assert phases == [
        "begin",
        "blob:deck.pdf",
        "blob:deck_docling.json",
        "final_meta",
        "commit",
    ]
    assert batching_repository.begin_calls == 1
    assert batching_repository.commit_calls == 1
    assert batching_repository.rollback_calls == 0


def test_execute_upload_commit_failure_does_not_call_caller_rollback(tmp_path: Path) -> None:
    """commit_batch 开始后 token 归 storage owner，失败不得触发二次 rollback。"""

    events: list[str] = []
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _CommitFailingUploadBatchingRepository(tmp_path, repository_set, events)
    source_repository = _SpyUploadSourceRepository(tmp_path, repository_set, events)
    blob_repository = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    service = DoclingUploadService(
        source_repository=source_repository,
        blob_repository=blob_repository,
        docling_converter=_FakeDoclingConverter(),
    )
    sample_file = tmp_path / "deck.pdf"
    sample_file.write_text("hello", encoding="utf-8")

    with pytest.raises(OSError, match="forced storage commit failure"):
        _execute_upload(
            service=service,
            batching_repository=batching_repository,
            ticker="AAPL",
            source_kind=SourceKind.MATERIAL,
            action="create",
            document_id="mat_commit_failed",
            internal_document_id="mat_commit_failed",
            form_type="MATERIAL_OTHER",
            files=[sample_file],
            overwrite=False,
            meta={"material_name": "Deck", "ingest_method": "upload"},
        )

    assert batching_repository.caller_rollback_calls == 0
    with pytest.raises(FileNotFoundError):
        source_repository.get_source_meta(
            "AAPL",
            "mat_commit_failed",
            SourceKind.MATERIAL,
        )


def test_filing_final_source_failure_rolls_back_once_with_zero_publication(tmp_path: Path) -> None:
    """filing final source failure 必须恰好一次 rollback 且 fresh target 零发布。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: rollback 次数或 published tree 原子性漂移时抛出。
    """

    events: list[str] = []
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _BatchIdentityUploadBatchingRepository(tmp_path, repository_set, events)
    source_repository = _FailingFinalUploadSourceRepository(tmp_path, repository_set, events)
    service = DoclingUploadService(
        source_repository=source_repository,
        blob_repository=FsDocumentBlobRepository(tmp_path, repository_set=repository_set),
        docling_converter=_FakeDoclingConverter(),
    )
    sample_file = (tmp_path / "report.pdf").resolve(strict=False)
    sample_file.write_bytes(b"filing")

    with pytest.raises(RuntimeError, match="forced final upsert failure"):
        _execute_upload(
            service=service,
            batching_repository=batching_repository,
            ticker="AAPL",
            source_kind=SourceKind.FILING,
            action="create",
            document_id="filing_final_failure",
            internal_document_id="filing_final_failure",
            form_type="10-K",
            files=[sample_file],
            filing_primary=sample_file,
            overwrite=False,
            meta={"ingest_method": "upload"},
        )

    assert batching_repository.begin_calls == 1
    assert batching_repository.commit_calls == 0
    assert batching_repository.rollback_calls == 1
    assert published_tree_sha256(tmp_path, "AAPL") == {}
    with pytest.raises(FileNotFoundError):
        source_repository.get_source_meta(
            "AAPL",
            "filing_final_failure",
            SourceKind.FILING,
        )


@pytest.mark.parametrize("fail_at", (1, 2, 3))
def test_filing_fresh_blob_store_failure_rolls_back_once_with_zero_publication(
    tmp_path: Path,
    fail_at: int,
) -> None:
    """fresh filing 第 N 次 blob store 失败必须恰好回滚一次且零发布。

    Args:
        tmp_path: pytest 临时目录。
        fail_at: original/derived staging 中需要失败的写入次序。

    Returns:
        无。

    Raises:
        AssertionError: batch 计数、零发布或 source 不存在契约漂移时抛出。
    """

    events: list[str] = []
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _BatchIdentityUploadBatchingRepository(tmp_path, repository_set, events)
    source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    service = DoclingUploadService(
        source_repository=source_repository,
        blob_repository=_FailingNthUploadBlobRepository(
            tmp_path,
            repository_set,
            fail_at=fail_at,
        ),
        docling_converter=_FakeDoclingConverter(),
    )
    companion = (tmp_path / "companion.pdf").resolve(strict=False)
    primary = (tmp_path / "primary.pdf").resolve(strict=False)
    companion.write_bytes(b"companion")
    primary.write_bytes(b"primary")

    with pytest.raises(RuntimeError, match="forced replacement blob failure"):
        _execute_upload(
            service=service,
            batching_repository=batching_repository,
            ticker="AAPL",
            source_kind=SourceKind.FILING,
            action="create",
            document_id="filing_fresh_blob_failure",
            internal_document_id="filing_fresh_blob_failure",
            form_type="10-K",
            files=[companion, primary],
            filing_primary=primary,
            overwrite=False,
            meta={"ingest_method": "upload"},
        )

    assert batching_repository.begin_calls == 1
    assert batching_repository.commit_calls == 0
    assert batching_repository.rollback_calls == 1
    assert published_tree_sha256(tmp_path, "AAPL") == {}
    with pytest.raises(FileNotFoundError):
        source_repository.get_source_meta(
            "AAPL",
            "filing_fresh_blob_failure",
            SourceKind.FILING,
        )


def test_filing_commit_failure_leaves_fresh_target_unpublished(tmp_path: Path) -> None:
    """storage-owned filing commit failure 必须清空 staging 且不触发 caller 二次 rollback。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: commit ownership 或零发布不变量漂移时抛出。
    """

    events: list[str] = []
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _CommitFailingUploadBatchingRepository(tmp_path, repository_set, events)
    source_repository = _SpyUploadSourceRepository(tmp_path, repository_set, events)
    service = DoclingUploadService(
        source_repository=source_repository,
        blob_repository=FsDocumentBlobRepository(tmp_path, repository_set=repository_set),
        docling_converter=_FakeDoclingConverter(),
    )
    sample_file = (tmp_path / "report.pdf").resolve(strict=False)
    sample_file.write_bytes(b"filing")

    with pytest.raises(OSError, match="forced storage commit failure"):
        _execute_upload(
            service=service,
            batching_repository=batching_repository,
            ticker="AAPL",
            source_kind=SourceKind.FILING,
            action="create",
            document_id="filing_commit_failure",
            internal_document_id="filing_commit_failure",
            form_type="10-K",
            files=[sample_file],
            filing_primary=sample_file,
            overwrite=False,
            meta={"ingest_method": "upload"},
        )

    assert batching_repository.caller_rollback_calls == 0
    assert published_tree_sha256(tmp_path, "AAPL") == {}
    with pytest.raises(FileNotFoundError):
        source_repository.get_source_meta(
            "AAPL",
            "filing_commit_failure",
            SourceKind.FILING,
        )


def test_commit_winner_ignores_cancel_after_ownership_transfer(tmp_path: Path) -> None:
    """commit ownership transfer 后的取消不得触发读取、rollback 或结果改写。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: commit winner 线性化语义漂移时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _CommitBarrierBatchingRepository(tmp_path, repository_set)
    source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    service = DoclingUploadService(
        source_repository=source_repository,
        blob_repository=blob_repository,
        docling_converter=_FakeDoclingConverter(),
    )
    token = _MutableToken()
    sample_file = tmp_path / "deck.pdf"
    sample_file.write_text("commit winner", encoding="utf-8")
    prepared = asyncio.run(
        service.prepare_upload(
            ticker="AAPL",
            source_kind=SourceKind.MATERIAL,
            action="create",
            document_id="mat_commit_winner",
            internal_document_id="mat_commit_winner",
            form_type="MATERIAL_OTHER",
            selection=FinsUploadMaterialFiles.from_upsert_paths((sample_file,)),
            overwrite=False,
            previous_meta=None,
            meta={"material_name": "Deck", "ingest_method": "upload"},
            repair_disposition=NoExistingSourceRepair(),
            cancellation=token,
        )
    )
    assert not isinstance(prepared, UploadOperationResult)
    results: list[UploadOperationResult] = []

    def commit_from_worker() -> None:
        """在工作线程执行 publication helper。

        Returns:
            无。
        """

        results.append(
            commit_prepared_upload_batch(
                service=service,
                batching_repository=batching_repository,
                batch=batching_repository.begin_batch("AAPL"),
                prepared=prepared,
                cancellation=token,
            )
        )

    worker = Thread(target=commit_from_worker)
    worker.start()
    assert batching_repository.commit_entered.wait(timeout=1.0)
    reads_at_transfer = token.read_count
    token.request_cancel()
    batching_repository.allow_commit_return.set()
    worker.join(timeout=1.0)

    assert not worker.is_alive()
    assert [result.status for result in results] == ["uploaded"]
    assert token.read_count == reads_at_transfer
    assert batching_repository.rollback_calls == 0
    assert (
        source_repository.get_source_meta(
            "AAPL",
            "mat_commit_winner",
            SourceKind.MATERIAL,
        )["ingest_complete"]
        is True
    )


def test_execute_upload_operation_and_rollback_failure_preserve_both_errors(tmp_path: Path) -> None:
    """operation 与 rollback 双失败时 primary、note 与 cause 必须同时保留。"""

    events: list[str] = []
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _RollbackFailingUploadBatchingRepository(
        tmp_path,
        repository_set=repository_set,
    )
    source_repository = _FailingFinalUploadSourceRepository(tmp_path, repository_set, events)
    blob_repository = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    service = DoclingUploadService(
        source_repository=source_repository,
        blob_repository=blob_repository,
        docling_converter=_FakeDoclingConverter(),
    )
    sample_file = tmp_path / "deck.pdf"
    sample_file.write_text("hello", encoding="utf-8")

    with pytest.raises(RuntimeError, match="forced final upsert failure") as exc_info:
        _execute_upload(
            service=service,
            batching_repository=batching_repository,
            ticker="AAPL",
            source_kind=SourceKind.MATERIAL,
            action="create",
            document_id="mat_dual_failure",
            internal_document_id="mat_dual_failure",
            form_type="MATERIAL_OTHER",
            files=[sample_file],
            overwrite=False,
            meta={"material_name": "Deck", "ingest_method": "upload"},
        )

    assert isinstance(exc_info.value.__cause__, OSError)
    assert "forced rollback failure" in str(exc_info.value.__cause__)
    assert any("recovery evidence retained" in note for note in exc_info.value.__notes__)


def test_execute_upload_create_final_failure_leaves_document_absent(tmp_path: Path) -> None:
    """create final upsert 失败时 batch 回滚应隐藏 source 与全部 blob。"""

    events: list[str] = []
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _BatchIdentityUploadBatchingRepository(tmp_path, repository_set, events)
    source_repository = _FailingFinalUploadSourceRepository(tmp_path, repository_set, events)
    blob_repository = _BlobFirstUploadBlobRepository(tmp_path, repository_set, source_repository, events)
    service = DoclingUploadService(
        source_repository=source_repository,
        blob_repository=blob_repository,
        docling_converter=_FakeDoclingConverter(),
    )
    sample_file = tmp_path / "deck.pdf"
    sample_file.write_text("hello", encoding="utf-8")

    with pytest.raises(RuntimeError, match="forced final upsert failure"):
        _execute_upload(
            service=service,
            batching_repository=batching_repository,
            ticker="AAPL",
            source_kind=SourceKind.MATERIAL,
            action="create",
            document_id="mat_failed",
            internal_document_id="mat_failed",
            form_type="MATERIAL_OTHER",
            files=[sample_file],
            overwrite=False,
            meta={"material_name": "Deck", "ingest_method": "upload"},
        )
    handle = SourceHandle(ticker="AAPL", document_id="mat_failed", source_kind=SourceKind.MATERIAL.value)

    assert events[0].startswith("store:")
    assert events[-1] == "create_failed"
    assert blob_repository.observed_source_absent == [True, True]
    assert batching_repository.rollback_calls == 1
    assert batching_repository.commit_calls == 0
    with pytest.raises(FileNotFoundError):
        source_repository.get_source_meta("AAPL", "mat_failed", SourceKind.MATERIAL)
    assert blob_repository.list_entries(handle) == []


@pytest.mark.parametrize("source_kind", (SourceKind.FILING, SourceKind.MATERIAL))
@pytest.mark.parametrize("overwrite", (False, True))
def test_prepare_upload_rejects_missing_update_before_shared_conversion(
    tmp_path: Path,
    source_kind: SourceKind,
    overwrite: bool,
) -> None:
    """filing/material update-missing 均须在 shared converter 前失败。

    Args:
        tmp_path: pytest 临时目录。
        source_kind: 当前 shared owner 的 source 类型。
        overwrite: 是否请求覆盖。

    Returns:
        无。

    Raises:
        AssertionError: overwrite 获得 upsert 权限或 converter 被调用时抛出。
    """

    calls: list[str] = []
    context = _build_service_context(tmp_path)
    service = DoclingUploadService(
        source_repository=context.source_repository,
        blob_repository=context.blob_repository,
        docling_converter=_FakeDoclingConverter(calls),
    )
    sample_file = tmp_path / "missing.txt"
    sample_file.write_text("missing target", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="Document not found for update"):
        asyncio.run(
            service.prepare_upload(
                ticker="AAPL",
                source_kind=source_kind,
                action="update",
                document_id="missing_document",
                internal_document_id="missing_document",
                form_type="10-K" if source_kind is SourceKind.FILING else "MATERIAL_OTHER",
                selection=_selection_for_test(
                    source_kind=source_kind,
                    action="update",
                    files=[sample_file],
                    filing_primary=sample_file if source_kind is SourceKind.FILING else None,
                ),
                overwrite=overwrite,
                previous_meta=None,
                meta={"ingest_method": "upload"},
                repair_disposition=NoExistingSourceRepair(),
                cancellation=None,
            )
        )

    assert calls == []


def test_prepare_upload_rejects_existing_filing_create_before_conversion(tmp_path: Path) -> None:
    """filing create-existing 且未 overwrite 时必须在 converter 前失败。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: precondition 晚于 converter 或未拒绝时抛出。
    """

    calls: list[str] = []
    context = _build_service_context(tmp_path)
    service = DoclingUploadService(
        source_repository=context.source_repository,
        blob_repository=context.blob_repository,
        docling_converter=_FakeDoclingConverter(calls),
    )
    sample_file = tmp_path / "report.txt"
    sample_file.write_text("published", encoding="utf-8")
    _execute_upload(
        service=service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="create",
        document_id="filing_existing",
        internal_document_id="filing_existing",
        form_type="10-K",
        files=[sample_file],
        filing_primary=sample_file,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    calls.clear()
    previous_meta = context.source_repository.get_source_meta(
        "AAPL",
        "filing_existing",
        SourceKind.FILING,
    )

    with pytest.raises(FileExistsError, match="Document already exists for create"):
        asyncio.run(
            service.prepare_upload(
                ticker="AAPL",
                source_kind=SourceKind.FILING,
                action="create",
                document_id="filing_existing",
                internal_document_id="filing_existing",
                form_type="10-K",
                selection=FinsUploadFilingFiles.for_upsert(
                    primary=sample_file,
                    companions=(),
                ),
                overwrite=False,
                previous_meta=previous_meta,
                meta={"ingest_method": "upload"},
                repair_disposition=NoExistingSourceRepair(),
                cancellation=None,
            )
        )

    assert calls == []


@pytest.mark.parametrize("deleted_value", (None, "false"))
def test_prepare_upload_requires_canonical_boolean_deleted_state(
    tmp_path: Path,
    deleted_value: str | None,
) -> None:
    """skip owner 必须直接校验 canonical source_meta 的确定 bool。

    Args:
        tmp_path: pytest 临时目录。
        deleted_value: ``None`` 表示字段缺失，否则为非法非布尔值。

    Returns:
        无。

    Raises:
        AssertionError: owner 使用默认值或 loose truthiness 时抛出。
    """

    calls: list[str] = []
    context = _build_service_context(tmp_path)
    service = DoclingUploadService(
        source_repository=context.source_repository,
        blob_repository=context.blob_repository,
        docling_converter=_FakeDoclingConverter(calls),
    )
    sample_file = tmp_path / "report.txt"
    raw = b"same input"
    sample_file.write_bytes(raw)
    fingerprint = _build_upload_source_fingerprint(
        [
            _PendingFileAsset(
                name=_build_filing_original_asset_identity(sample_file),
                original_filename=sample_file.name,
                derived_from=None,
                data=raw,
                content_type="text/plain",
                sha256=hashlib.sha256(raw).hexdigest(),
                size=len(raw),
                source="original",
            )
        ],
        source_kind=SourceKind.FILING,
        filing_primary=sample_file,
    )
    previous_meta: dict[str, JsonValue] = {"source_fingerprint": fingerprint.value}
    expected_error: type[KeyError] | type[ValueError]
    if deleted_value is None:
        expected_error = KeyError
    else:
        previous_meta["is_deleted"] = deleted_value
        expected_error = ValueError

    with pytest.raises(expected_error):
        asyncio.run(
            service.prepare_upload(
                ticker="AAPL",
                source_kind=SourceKind.FILING,
                action="update",
                document_id="filing_corrupt_meta",
                internal_document_id="filing_corrupt_meta",
                form_type="10-K",
                selection=FinsUploadFilingFiles.for_upsert(
                    primary=sample_file,
                    companions=(),
                ),
                overwrite=False,
                previous_meta=previous_meta,
                meta={"ingest_method": "upload"},
                repair_disposition=NoExistingSourceRepair(),
                cancellation=None,
            )
        )

    assert calls == []


@pytest.mark.parametrize(
    ("source_kind", "changed_input"),
    (
        (SourceKind.FILING, False),
        (SourceKind.FILING, True),
        (SourceKind.MATERIAL, False),
    ),
)
def test_execute_upload_deleted_input_republishes_complete_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_kind: SourceKind,
    changed_input: bool,
) -> None:
    """shared owner 必须把 deleted equal/changed input 重新发布为完整 active source。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest 属性替换器。
        source_kind: 当前验证的 shared source 类型。
        changed_input: logical delete 后是否改变完整输入内容。

    Returns:
        无。

    Raises:
        AssertionError: deleted source 被 skip、版本/首次创建事实漂移或未恢复完整性时抛出。
    """

    calls: list[str] = []
    context = _build_service_context(tmp_path)
    service = DoclingUploadService(
        source_repository=context.source_repository,
        blob_repository=context.blob_repository,
        docling_converter=_FakeDoclingConverter(calls),
    )
    sample_file = tmp_path / ("report.txt" if source_kind is SourceKind.FILING else "deck.txt")
    sample_file.write_text("same input", encoding="utf-8")
    form_type = "10-K" if source_kind is SourceKind.FILING else "MATERIAL_OTHER"
    document_id = "filing_deleted" if source_kind is SourceKind.FILING else "material_deleted"
    base_meta: dict[str, JsonValue] = {"ingest_method": "upload"}
    if source_kind is SourceKind.MATERIAL:
        base_meta["material_name"] = "Deck"
    _set_upload_clock(monkeypatch, _INITIAL_CREATED_AT)
    created = _execute_upload(
        service=service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=source_kind,
        action="create",
        document_id=document_id,
        internal_document_id=document_id,
        form_type=form_type,
        files=[sample_file],
        filing_primary=sample_file if source_kind is SourceKind.FILING else None,
        overwrite=False,
        meta=base_meta,
    )
    created_meta = context.source_repository.get_source_meta("AAPL", document_id, source_kind)
    _set_upload_clock(monkeypatch, _REPLACEMENT_CREATED_AT)
    deleted = _execute_upload(
        service=service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=source_kind,
        action="delete",
        document_id=document_id,
        internal_document_id=document_id,
        form_type=form_type,
        files=[],
        overwrite=False,
        meta={},
    )
    if changed_input:
        sample_file.write_text("changed input", encoding="utf-8")
    restored = _execute_upload(
        service=service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=source_kind,
        action="update",
        document_id=document_id,
        internal_document_id=document_id,
        form_type=form_type,
        files=[sample_file],
        filing_primary=sample_file if source_kind is SourceKind.FILING else None,
        overwrite=False,
        meta=base_meta,
    )
    restored_meta = context.source_repository.get_source_meta("AAPL", document_id, source_kind)
    integrity = context.source_repository.classify_source_integrity("AAPL", document_id, source_kind)

    assert created.status == "uploaded"
    assert deleted.status == "deleted"
    assert restored.status == "uploaded"
    assert created.stored_file_count == 1
    assert deleted.stored_file_count == 0
    assert restored.stored_file_count == 1
    assert calls == [sample_file.name, sample_file.name]
    assert restored_meta["is_deleted"] is False
    assert restored_meta["deleted_at"] is None
    expected_version = "v2" if changed_input else created_meta["document_version"]
    assert restored_meta["document_version"] == expected_version
    assert restored_meta["first_ingested_at"] == created_meta["first_ingested_at"]
    assert restored_meta["created_at"] == created_meta["created_at"]
    assert integrity.status is SourceIntegrityStatus.COMPLETE


@pytest.mark.parametrize(
    ("source_kind", "action", "overwrite", "old_name", "new_name"),
    (
        (SourceKind.FILING, "update", False, "report.txt", "report.txt"),
        (SourceKind.FILING, "update", False, "old-report.txt", "renamed-report.txt"),
        (SourceKind.MATERIAL, "create", True, "old-deck.txt", "new-deck.txt"),
    ),
)
def test_execute_upload_existing_full_input_replaces_exact_complete_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_kind: SourceKind,
    action: str,
    overwrite: bool,
    old_name: str,
    new_name: str,
) -> None:
    """existing update/create-overwrite 必须以 reset 前 meta 派生完整新集合。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest 属性替换器。
        source_kind: filing 或 material shared owner 输入。
        action: 第二次完整输入动作。
        overwrite: 第二次动作的覆盖标志。
        old_name: 初次发布的文件名。
        new_name: 替换发布的文件名。

    Returns:
        无。

    Raises:
        AssertionError: 旧文件残留、版本/首次创建事实漂移或完整性异常时抛出。
    """

    context = _build_service_context(tmp_path)
    old_dir = (tmp_path / "old-input").resolve(strict=False)
    new_dir = (tmp_path / "new-input").resolve(strict=False)
    old_dir.mkdir()
    new_dir.mkdir()
    old_file = old_dir / old_name
    new_file = new_dir / new_name
    old_file.write_text("old bytes", encoding="utf-8")
    new_file.write_text("new bytes", encoding="utf-8")
    form_type = "10-K" if source_kind is SourceKind.FILING else "MATERIAL_OTHER"
    document_id = "filing_replace" if source_kind is SourceKind.FILING else "material_replace"
    base_meta: dict[str, JsonValue] = {"ingest_method": "upload"}
    if source_kind is SourceKind.MATERIAL:
        base_meta["material_name"] = "Deck"
    _set_upload_clock(monkeypatch, _INITIAL_CREATED_AT)
    _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=source_kind,
        action="create",
        document_id=document_id,
        internal_document_id=document_id,
        form_type=form_type,
        files=[old_file],
        filing_primary=old_file if source_kind is SourceKind.FILING else None,
        overwrite=False,
        meta=base_meta,
    )
    initial_meta = context.source_repository.get_source_meta("AAPL", document_id, source_kind)

    _set_upload_clock(monkeypatch, _REPLACEMENT_CREATED_AT)
    result = _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=source_kind,
        action=action,
        document_id=document_id,
        internal_document_id=document_id,
        form_type=form_type,
        files=[new_file],
        filing_primary=new_file if source_kind is SourceKind.FILING else None,
        overwrite=overwrite,
        meta=base_meta,
    )

    final_meta = context.source_repository.get_source_meta("AAPL", document_id, source_kind)
    handle = SourceHandle(ticker="AAPL", document_id=document_id, source_kind=source_kind.value)
    published_names = sorted(
        item.uri.rsplit("/", maxsplit=1)[-1] for item in context.blob_repository.list_files(handle)
    )
    published_original_name = (
        _build_filing_original_asset_identity(new_file)
        if source_kind is SourceKind.FILING
        else new_name
    )
    published_derived_name = (
        f"{published_original_name}_docling.json"
        if source_kind is SourceKind.FILING
        else f"{Path(new_name).stem}_docling.json"
    )
    expected_names = sorted((published_original_name, published_derived_name))
    integrity = context.source_repository.classify_source_integrity("AAPL", document_id, source_kind)

    assert result.status == "uploaded"
    assert result.stored_file_count == 1
    assert published_names == expected_names
    assert context.blob_repository.read_file_bytes(handle, published_original_name) == b"new bytes"
    assert final_meta["document_version"] == "v2"
    assert final_meta["first_ingested_at"] == initial_meta["first_ingested_at"]
    assert final_meta["created_at"] == initial_meta["created_at"]
    assert final_meta["is_deleted"] is False
    assert integrity.status is SourceIntegrityStatus.COMPLETE


def test_prepare_upload_rejects_invalid_repair_disposition(tmp_path: Path) -> None:
    """prepare owner 必须以固定 ValueError 拒绝封闭 union 之外的 disposition。

    Args:
        tmp_path: 上传 preparation 测试工作区。

    Returns:
        无。

    Raises:
        AssertionError: 非法 disposition 未在 preparation 边界被固定拒绝时抛出。
        OSError: fixture 文件写入失败时抛出。
    """

    context = _build_service_context(tmp_path)
    source_file = tmp_path / "invalid-repair.pdf"
    source_file.write_bytes(b"invalid repair disposition")

    with pytest.raises(
        ValueError,
        match="^repair_disposition 必须是封闭 repair contract$",
    ):
        asyncio.run(
            context.service.prepare_upload(
                ticker="AAPL",
                source_kind=SourceKind.FILING,
                action="update",
                document_id="invalid-repair",
                internal_document_id="invalid-repair",
                form_type="10-K",
                selection=FinsUploadFilingFiles.for_upsert(
                    primary=source_file,
                    companions=(),
                ),
                overwrite=False,
                previous_meta=None,
                meta={"ingest_method": "upload"},
                repair_disposition=cast(
                    ExistingSourceRepairDisposition,
                    "invalid-repair-disposition",
                ),
                cancellation=None,
            )
        )


def test_prepare_upload_rejects_delete_with_existing_repair(tmp_path: Path) -> None:
    """delete mutation 与 existing repair authorization 必须固定 fail closed。

    Args:
        tmp_path: 上传 preparation 测试工作区。

    Returns:
        无。

    Raises:
        AssertionError: delete 与 repair 矛盾输入未抛固定 ValueError 时抛出。
    """

    context = _build_service_context(tmp_path)
    expected = SourceIntegrityClassification(
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        document_id="delete-repair",
        revision=SourceDocumentRevision("delete-repair-revision"),
        status=SourceIntegrityStatus.REPAIR_REQUIRED,
        reasons=(SourceIntegrityReason.ORIGINAL_FILE_MISSING,),
    )

    with pytest.raises(
        ValueError,
        match="^delete 上传不得携带 existing source repair 授权$",
    ):
        asyncio.run(
            context.service.prepare_upload(
                ticker="AAPL",
                source_kind=SourceKind.FILING,
                action="delete",
                document_id="delete-repair",
                internal_document_id="delete-repair",
                form_type="10-K",
                selection=FinsUploadFilingFiles.for_delete(),
                overwrite=False,
                previous_meta=None,
                meta={"ingest_method": "upload"},
                repair_disposition=ExistingSourceAutoRepair(
                    expected_integrity=expected
                ),
                cancellation=None,
            )
        )


def test_existing_filing_repair_bypasses_identical_skip_and_rebuilds_full_input(
    tmp_path: Path,
) -> None:
    """repair 必须转换 authoritative primary 并全量重建 originals/Docling/meta/manifest。

    Args:
        tmp_path: 上传 publication 测试工作区。

    Returns:
        无。

    Raises:
        AssertionError: identical skip 未绕过、完整输入丢失或新 publication 不完整时抛出。
        OSError: fixture 文件或 published corruption 写入失败时抛出。
    """

    calls: list[str] = []
    context = _build_service_context(tmp_path)
    service = DoclingUploadService(
        source_repository=context.source_repository,
        blob_repository=context.blob_repository,
        docling_converter=_FakeDoclingConverter(calls),
    )
    primary = tmp_path / "repair-primary.pdf"
    companion = tmp_path / "repair-companion.xlsx"
    primary.write_bytes(b"authoritative-primary")
    companion.write_bytes(b"authoritative-companion")
    document_id = "filing_repair_success"
    _execute_upload(
        service=service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="create",
        document_id=document_id,
        internal_document_id=document_id,
        form_type="10-K",
        files=[primary, companion],
        filing_primary=primary,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    complete = context.source_repository.classify_source_integrity(
        "AAPL",
        document_id,
        SourceKind.FILING,
    )
    _remove_published_filing_original(
        workspace_root=tmp_path,
        source_repository=context.source_repository,
        document_id=document_id,
    )
    expected = context.source_repository.classify_source_integrity(
        "AAPL",
        document_id,
        SourceKind.FILING,
    )
    assert expected.status is SourceIntegrityStatus.REPAIR_REQUIRED
    assert SourceIntegrityReason.ORIGINAL_FILE_MISSING in expected.reasons

    prepared = _prepare_existing_filing_repair(
        service=service,
        source_repository=context.source_repository,
        document_id=document_id,
        files=(primary, companion),
        primary=primary,
    )
    assert calls == [primary.name, primary.name]
    assert sum(asset.source == "original" for asset in prepared.pending_assets) == 2
    assert sum(asset.source == "docling" for asset in prepared.pending_assets) == 1

    result = _publish_prepared_upload(
        service=service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        prepared=prepared,
    )
    repaired = context.source_repository.classify_source_integrity(
        "AAPL",
        document_id,
        SourceKind.FILING,
    )
    repaired_meta = context.source_repository.get_source_meta(
        "AAPL",
        document_id,
        SourceKind.FILING,
    )
    raw_files = repaired_meta.get("files")
    assert result.status == "uploaded"
    assert result.stored_file_count == 2
    assert repaired.status is SourceIntegrityStatus.COMPLETE
    assert repaired.revision != complete.revision
    assert isinstance(raw_files, list)
    assert len(raw_files) == 3


@pytest.mark.parametrize(
    ("failure_case", "expected_code"),
    (
        ("stale", FinsUploadFailureCode.SOURCE_REVISION_STALE),
        ("target_unsafe", FinsUploadFailureCode.SOURCE_REVISION_STALE),
        ("shared_untrusted", FinsUploadFailureCode.SOURCE_REVISION_STALE),
        ("blocked", FinsUploadFailureCode.SOURCE_REPAIR_BLOCKED),
    ),
)
def test_existing_filing_repair_maps_real_staged_failures_and_rolls_back_once(
    tmp_path: Path,
    failure_case: Literal[
        "stale",
        "target_unsafe",
        "shared_untrusted",
        "blocked",
    ],
    expected_code: FinsUploadFailureCode,
) -> None:
    """真实 core stale/blocked 必须精确映射且恰好回滚一次、旧树不变。

    Args:
        tmp_path: 上传 publication 测试工作区。
        failure_case: revision stale、target unsafe、shared manifest untrusted 或
            non-target repair blocked。
        expected_code: public failure owner 的精确 closed code。

    Returns:
        无。

    Raises:
        AssertionError: failure 映射、rollback 次数或 published 原子性漂移时抛出。
        OSError: fixture 文件、published corruption 或 staged drift 写入失败时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    seed_batching = FsBatchingRepository(tmp_path, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    seed_service = DoclingUploadService(
        source_repository=source_repository,
        blob_repository=blob_repository,
        docling_converter=_FakeDoclingConverter(),
    )
    target_file = tmp_path / "repair-target.pdf"
    sibling_file = tmp_path / "repair-sibling.pdf"
    target_file.write_bytes(b"target")
    sibling_file.write_bytes(b"sibling")
    target_id = "filing_repair_failure"
    sibling_id = "filing_repair_sibling"
    for document_id, file_path in (
        (target_id, target_file),
        (sibling_id, sibling_file),
    ):
        _execute_upload(
            service=seed_service,
            batching_repository=seed_batching,
            ticker="AAPL",
            source_kind=SourceKind.FILING,
            action="create",
            document_id=document_id,
            internal_document_id=document_id,
            form_type="10-K",
            files=[file_path],
            filing_primary=file_path,
            overwrite=False,
            meta={"ingest_method": "upload"},
        )
    _remove_published_filing_original(
        workspace_root=tmp_path,
        source_repository=source_repository,
        document_id=target_id,
    )
    prepared = _prepare_existing_filing_repair(
        service=seed_service,
        source_repository=source_repository,
        document_id=target_id,
        files=(target_file,),
        primary=target_file,
    )
    old_tree = published_tree_sha256(tmp_path, "AAPL")
    batching = _BatchIdentityUploadBatchingRepository(tmp_path, repository_set, [])
    batch = batching.begin_batch("AAPL")
    state = repository_set.core._active_batches[batch.transaction_id]
    drift_document_id = target_id if failure_case != "blocked" else sibling_id
    staged_meta_path = repository_set.core._source_meta_path(
        "AAPL",
        drift_document_id,
        SourceKind.FILING,
        state,
    )
    if failure_case == "shared_untrusted":
        (state.staging_ticker_dir / "filings" / "filing_manifest.json").write_text(
            "{",
            encoding="utf-8",
        )
    else:
        staged_meta = json.loads(staged_meta_path.read_text(encoding="utf-8"))
        if not isinstance(staged_meta, dict):
            raise AssertionError("staged repair meta 必须是 object")
        if failure_case == "stale":
            staged_meta["_published_source_revision"] = "staged-revision-drift"
            staged_meta_path.write_text(json.dumps(staged_meta), encoding="utf-8")
        elif failure_case == "target_unsafe":
            del staged_meta["_published_source_revision"]
            staged_meta_path.write_text(json.dumps(staged_meta), encoding="utf-8")
        else:
            raw_files = staged_meta.get("files")
            if not isinstance(raw_files, list):
                raise AssertionError("staged sibling files 必须是数组")
            original_name = next(
                raw_file.get("name")
                for raw_file in raw_files
                if isinstance(raw_file, dict) and raw_file.get("source") == "original"
            )
            if not isinstance(original_name, str):
                raise AssertionError("staged sibling original name 必须是字符串")
            (staged_meta_path.parent / original_name).unlink()

    with pytest.raises(FinsUploadFailureError) as exc_info:
        commit_prepared_upload_batch(
            service=seed_service,
            batching_repository=batching,
            batch=batch,
            prepared=prepared,
            cancellation=None,
        )

    assert exc_info.value.failure.kind is FinsUploadFailureKind.STORAGE
    assert exc_info.value.failure.code is expected_code
    assert exc_info.value.failure.code is not FinsUploadFailureCode.UNEXPECTED_RUNTIME
    assert batching.rollback_calls == 1
    assert batching.commit_calls == 0
    assert published_tree_sha256(tmp_path, "AAPL") == old_tree
    assert repository_set.core._active_batches == {}
    assert not repository_set.core.batch_root.exists() or not tuple(
        repository_set.core.batch_root.iterdir()
    )


@pytest.mark.parametrize(
    ("material_corruption", "expected_reason"),
    (
        (
            "content_missing",
            SourceIntegrityRepairBlockedReason.CANONICAL_MANIFEST_UNAVAILABLE,
        ),
        (
            "manifest_missing",
            SourceIntegrityRepairBlockedReason.CANONICAL_MANIFEST_UNAVAILABLE,
        ),
        (
            "structural_unsafe",
            SourceIntegrityRepairBlockedReason.CROSS_SOURCE_PUBLICATION_UNSAFE,
        ),
    ),
)
def test_existing_filing_repair_maps_material_damage_to_blocked_and_rolls_back_once(
    tmp_path: Path,
    material_corruption: Literal[
        "content_missing",
        "manifest_missing",
        "structural_unsafe",
    ],
    expected_reason: SourceIntegrityRepairBlockedReason,
) -> None:
    """真实 material whole-kind damage 必须在 reset 前投影为 repair blocked。

    Args:
        tmp_path: 上传 publication 测试工作区。
        material_corruption: material content、manifest 或 root structural 损坏。
        expected_reason: integrity owner 应产生的封闭阻断原因。

    Returns:
        无。

    Raises:
        AssertionError: typed failure、rollback 次数或 old-tree 原子性漂移时抛出。
        OSError: fixture publication 或 corruption 写入失败时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    seed_batching = FsBatchingRepository(tmp_path, repository_set=repository_set)
    source = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    blob = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    service = DoclingUploadService(
        source_repository=source,
        blob_repository=blob,
        docling_converter=_FakeDoclingConverter(),
    )
    filing_file = tmp_path / "material-blocked-filing.pdf"
    material_file = tmp_path / "material-blocked-deck.pdf"
    filing_file.write_bytes(b"filing repair input")
    material_file.write_bytes(b"material publication")
    filing_id = "filing_material_blocked"
    material_id = "material_repair_blocker"
    _execute_upload(
        service=service,
        batching_repository=seed_batching,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="create",
        document_id=filing_id,
        internal_document_id=filing_id,
        form_type="10-K",
        files=[filing_file],
        filing_primary=filing_file,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    _execute_upload(
        service=service,
        batching_repository=seed_batching,
        ticker="AAPL",
        source_kind=SourceKind.MATERIAL,
        action="create",
        document_id=material_id,
        internal_document_id=material_id,
        form_type="MATERIAL_OTHER",
        files=[material_file],
        overwrite=False,
        meta={"material_name": "Repair blocker", "ingest_method": "upload"},
    )
    _remove_published_filing_original(
        workspace_root=tmp_path,
        source_repository=source,
        document_id=filing_id,
    )
    prepared = _prepare_existing_filing_repair(
        service=service,
        source_repository=source,
        document_id=filing_id,
        files=(filing_file,),
        primary=filing_file,
    )
    if material_corruption == "content_missing":
        _remove_published_material_declared_file(
            workspace_root=tmp_path,
            source_repository=source,
            document_id=material_id,
        )
    else:
        material_manifest = repository_set.core._material_manifest_path_for_read(
            "AAPL"
        )
        if material_corruption == "manifest_missing":
            material_manifest.unlink()
        else:
            (material_manifest.parent / "unsafe-root-entry.bin").write_bytes(
                b"unsafe"
            )

    old_filing_meta = source.get_source_meta("AAPL", filing_id, SourceKind.FILING)
    old_material_meta = source.get_source_meta("AAPL", material_id, SourceKind.MATERIAL)
    company_meta_path = repository_set.core._company_meta_path_for_read("AAPL")
    assert not company_meta_path.exists()
    old_tree = published_tree_sha256(tmp_path, "AAPL")
    batching = _BatchIdentityUploadBatchingRepository(tmp_path, repository_set, [])

    with pytest.raises(FinsUploadFailureError) as exc_info:
        _publish_prepared_upload(
            service=service,
            batching_repository=batching,
            ticker="AAPL",
            prepared=prepared,
        )

    assert exc_info.value.failure.kind is FinsUploadFailureKind.STORAGE
    assert exc_info.value.failure.code is FinsUploadFailureCode.SOURCE_REPAIR_BLOCKED
    blocked_error = exc_info.value.__cause__
    assert isinstance(blocked_error, SourceIntegrityRepairBlockedError)
    assert blocked_error.reason is expected_reason
    if material_corruption == "structural_unsafe":
        assert isinstance(blocked_error.__cause__, SourceIntegrityPreflightError)
    assert batching.rollback_calls == 1
    assert batching.commit_calls == 0
    assert published_tree_sha256(tmp_path, "AAPL") == old_tree
    assert source.get_source_meta("AAPL", filing_id, SourceKind.FILING) == old_filing_meta
    assert source.get_source_meta("AAPL", material_id, SourceKind.MATERIAL) == old_material_meta
    assert not company_meta_path.exists()
    assert repository_set.core._active_batches == {}
    assert not repository_set.core.batch_root.exists() or not tuple(
        repository_set.core.batch_root.iterdir()
    )


def test_existing_filing_repair_manifest_rewrite_failure_rolls_back_once(
    tmp_path: Path,
) -> None:
    """target reset 后 manifest rewrite OSError 必须恰好回滚并保留 old tree。

    Args:
        tmp_path: 上传 publication 测试工作区。

    Returns:
        无。

    Raises:
        AssertionError: OSError、rollback 次数或 published 原子性漂移时抛出。
        OSError: fixture publication 或 corruption 写入失败时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    seed_batching = FsBatchingRepository(tmp_path, repository_set=repository_set)
    source = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    blob = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    service = DoclingUploadService(
        source_repository=source,
        blob_repository=blob,
        docling_converter=_FakeDoclingConverter(),
    )
    original = tmp_path / "repair-manifest-rewrite.pdf"
    original.write_bytes(b"repair manifest rewrite")
    document_id = "filing_repair_manifest_rewrite"
    _execute_upload(
        service=service,
        batching_repository=seed_batching,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="create",
        document_id=document_id,
        internal_document_id=document_id,
        form_type="10-K",
        files=[original],
        filing_primary=original,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    _remove_published_filing_original(
        workspace_root=tmp_path,
        source_repository=source,
        document_id=document_id,
    )
    prepared = _prepare_existing_filing_repair(
        service=service,
        source_repository=source,
        document_id=document_id,
        files=(original,),
        primary=original,
    )
    old_meta = source.get_source_meta("AAPL", document_id, SourceKind.FILING)
    company_meta_path = repository_set.core._company_meta_path_for_read("AAPL")
    assert not company_meta_path.exists()
    old_tree = published_tree_sha256(tmp_path, "AAPL")
    batching = _BatchIdentityUploadBatchingRepository(tmp_path, repository_set, [])

    with patch.object(
        source_document_core_module,
        "_write_json",
        side_effect=OSError("forced repair manifest rewrite failure"),
    ):
        with pytest.raises(
            OSError,
            match="^forced repair manifest rewrite failure$",
        ):
            _publish_prepared_upload(
                service=service,
                batching_repository=batching,
                ticker="AAPL",
                prepared=prepared,
            )

    assert batching.rollback_calls == 1
    assert batching.commit_calls == 0
    assert published_tree_sha256(tmp_path, "AAPL") == old_tree
    assert source.get_source_meta("AAPL", document_id, SourceKind.FILING) == old_meta
    assert not company_meta_path.exists()
    assert repository_set.core._active_batches == {}
    assert not repository_set.core.batch_root.exists() or not tuple(
        repository_set.core.batch_root.iterdir()
    )


@pytest.mark.parametrize("failure_case", ("blob", "final"))
def test_existing_filing_repair_blob_and_final_failures_keep_old_tree(
    tmp_path: Path,
    failure_case: Literal["blob", "final"],
) -> None:
    """repair reset 后 blob/final failure 必须回滚 staged mutation并保留旧树。

    Args:
        tmp_path: 上传 publication 测试工作区。
        failure_case: 第二个 blob 写入或 final source mutation 失败。

    Returns:
        无。

    Raises:
        AssertionError: primary failure、rollback 或 old-tree 原子性漂移时抛出。
        OSError: fixture 文件或 published corruption 写入失败时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    seed_batching = FsBatchingRepository(tmp_path, repository_set=repository_set)
    seed_source = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    seed_blob = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    seed_service = DoclingUploadService(
        source_repository=seed_source,
        blob_repository=seed_blob,
        docling_converter=_FakeDoclingConverter(),
    )
    original = tmp_path / "repair-failure.pdf"
    original.write_bytes(b"repair failure input")
    document_id = "filing_repair_io_failure"
    _execute_upload(
        service=seed_service,
        batching_repository=seed_batching,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="create",
        document_id=document_id,
        internal_document_id=document_id,
        form_type="10-K",
        files=[original],
        filing_primary=original,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    _remove_published_filing_original(
        workspace_root=tmp_path,
        source_repository=seed_source,
        document_id=document_id,
    )
    events: list[str] = []
    source_repository = (
        _FailingFinalUploadSourceRepository(tmp_path, repository_set, events)
        if failure_case == "final"
        else seed_source
    )
    blob_repository = (
        _FailingNthUploadBlobRepository(tmp_path, repository_set, fail_at=2)
        if failure_case == "blob"
        else seed_blob
    )
    failing_service = DoclingUploadService(
        source_repository=source_repository,
        blob_repository=blob_repository,
        docling_converter=_FakeDoclingConverter(),
    )
    prepared = _prepare_existing_filing_repair(
        service=failing_service,
        source_repository=source_repository,
        document_id=document_id,
        files=(original,),
        primary=original,
    )
    old_tree = published_tree_sha256(tmp_path, "AAPL")
    batching = _BatchIdentityUploadBatchingRepository(tmp_path, repository_set, events)

    expected_message = (
        "forced replacement blob failure"
        if failure_case == "blob"
        else "forced final upsert failure"
    )
    with pytest.raises(RuntimeError, match=expected_message):
        _publish_prepared_upload(
            service=failing_service,
            batching_repository=batching,
            ticker="AAPL",
            prepared=prepared,
        )

    assert batching.rollback_calls == 1
    assert published_tree_sha256(tmp_path, "AAPL") == old_tree
    assert repository_set.core._active_batches == {}
    assert not repository_set.core.batch_root.exists() or not tuple(
        repository_set.core.batch_root.iterdir()
    )


def test_existing_filing_repair_conversion_failure_starts_no_publication(
    tmp_path: Path,
) -> None:
    """repair conversion failure 必须发生在 batch 前并保留 damaged old publication。

    Args:
        tmp_path: 上传 publication 测试工作区。

    Returns:
        无。

    Raises:
        AssertionError: typed conversion failure、零 batch 或 old-tree 原子性漂移时抛出。
        OSError: fixture 文件或 published corruption 写入失败时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching = _BatchIdentityUploadBatchingRepository(tmp_path, repository_set, [])
    source = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    blob = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    original = tmp_path / "repair-conversion.pdf"
    original.write_bytes(b"repair conversion")
    document_id = "filing_repair_conversion_failure"
    seed_service = DoclingUploadService(
        source_repository=source,
        blob_repository=blob,
        docling_converter=_FakeDoclingConverter(),
    )
    _execute_upload(
        service=seed_service,
        batching_repository=batching,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="create",
        document_id=document_id,
        internal_document_id=document_id,
        form_type="10-K",
        files=[original],
        filing_primary=original,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    _remove_published_filing_original(
        workspace_root=tmp_path,
        source_repository=source,
        document_id=document_id,
    )
    old_tree = published_tree_sha256(tmp_path, "AAPL")
    calls: list[str] = []
    cause = DoclingConversionError(
        DoclingConversionFailureKind.CONVERTER_EXECUTION,
        "Docling conversion execution failed",
        None,
    )
    failing_service = DoclingUploadService(
        source_repository=source,
        blob_repository=blob,
        docling_converter=_SelectiveFailingDoclingConverter(
            failing_name=original.name,
            error=cause,
            calls=calls,
        ),
    )
    begin_calls_before = batching.begin_calls

    with pytest.raises(FinsUploadFailureError) as exc_info:
        _prepare_existing_filing_repair(
            service=failing_service,
            source_repository=source,
            document_id=document_id,
            files=(original,),
            primary=original,
        )

    assert exc_info.value.failure.kind is FinsUploadFailureKind.CONTENT
    assert exc_info.value.__cause__ is cause
    assert calls == [original.name]
    assert batching.begin_calls == begin_calls_before
    assert published_tree_sha256(tmp_path, "AAPL") == old_tree
    assert not repository_set.core.batch_root.exists() or not tuple(
        repository_set.core.batch_root.iterdir()
    )


def test_existing_filing_repair_rollback_secondary_failure_preserves_primary(
    tmp_path: Path,
) -> None:
    """repair final 与 rollback 同时失败时必须保留 final 主异常和旧 publication。

    Args:
        tmp_path: 上传 publication 测试工作区。

    Returns:
        无。

    Raises:
        AssertionError: 主次异常、old-tree 原子性或测试清理漂移时抛出。
        OSError: fixture 文件、published corruption 或最终测试清理失败时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    seed_batching = FsBatchingRepository(tmp_path, repository_set=repository_set)
    seed_source = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    blob = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    original = tmp_path / "repair-rollback.pdf"
    original.write_bytes(b"repair rollback")
    document_id = "filing_repair_rollback_failure"
    seed_service = DoclingUploadService(
        source_repository=seed_source,
        blob_repository=blob,
        docling_converter=_FakeDoclingConverter(),
    )
    _execute_upload(
        service=seed_service,
        batching_repository=seed_batching,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="create",
        document_id=document_id,
        internal_document_id=document_id,
        form_type="10-K",
        files=[original],
        filing_primary=original,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    _remove_published_filing_original(
        workspace_root=tmp_path,
        source_repository=seed_source,
        document_id=document_id,
    )
    old_tree = published_tree_sha256(tmp_path, "AAPL")
    events: list[str] = []
    failing_source = _FailingFinalUploadSourceRepository(tmp_path, repository_set, events)
    failing_service = DoclingUploadService(
        source_repository=failing_source,
        blob_repository=blob,
        docling_converter=_FakeDoclingConverter(),
    )
    prepared = _prepare_existing_filing_repair(
        service=failing_service,
        source_repository=failing_source,
        document_id=document_id,
        files=(original,),
        primary=original,
    )
    batching = _RollbackFailingUploadBatchingRepository(
        tmp_path,
        repository_set=repository_set,
    )
    batch = batching.begin_batch("AAPL")

    with pytest.raises(RuntimeError, match="forced final upsert failure") as exc_info:
        commit_prepared_upload_batch(
            service=failing_service,
            batching_repository=batching,
            batch=batch,
            prepared=prepared,
            cancellation=None,
        )

    assert isinstance(exc_info.value.__cause__, OSError)
    assert "forced rollback failure" in str(exc_info.value.__cause__)
    assert any("rollback_batch failed" in note for note in exc_info.value.__notes__)
    assert published_tree_sha256(tmp_path, "AAPL") == old_tree
    FsBatchingRepository.rollback_batch(batching, batch)
    assert repository_set.core._active_batches == {}


def test_execute_upload_skips_when_source_fingerprint_matches(tmp_path: Path) -> None:
    """相同源文件重复上传时应在转换前跳过。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    calls: list[str] = []

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = FsBatchingRepository(tmp_path, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    service = DoclingUploadService(
        source_repository=source_repository,
        blob_repository=blob_repository,
        docling_converter=_FakeDoclingConverter(calls),
    )
    sample_file = tmp_path / "deck.pdf"
    sample_file.write_text("hello", encoding="utf-8")

    first = _execute_upload(
        service=service,
        batching_repository=batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.MATERIAL,
        action="create",
        document_id="mat_demo",
        internal_document_id="mat_demo",
        form_type="MATERIAL_OTHER",
        files=[sample_file],
        overwrite=False,
        meta={"material_name": "Deck", "ingest_method": "upload"},
    )
    second = _execute_upload(
        service=service,
        batching_repository=batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.MATERIAL,
        action="create",
        document_id="mat_demo",
        internal_document_id="mat_demo",
        form_type="MATERIAL_OTHER",
        files=[sample_file],
        overwrite=False,
        meta={"material_name": "Deck", "ingest_method": "upload"},
    )

    assert first.status == "uploaded"
    assert second.status == "skipped"
    assert first.stored_file_count == 1
    assert second.stored_file_count == 0
    assert calls == ["deck.pdf"]
    assert all(event.event_type == "file_skipped" for event in second.file_events)


def test_distinguishable_filing_primary_flip_updates_v2_then_skips_replay(tmp_path: Path) -> None:
    """可区分 multi-file primary 翻转必须更新下游主文档并允许 v2 重放 skip。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: role-aware fingerprint、版本或 downstream primary 漂移时抛出。
    """

    calls: list[str] = []
    context = _build_service_context(tmp_path)
    context.service._docling_converter = _FakeDoclingConverter(calls)
    first = (tmp_path / "first.pdf").resolve(strict=False)
    second = (tmp_path / "second.pdf").resolve(strict=False)
    third = (tmp_path / "third.xsd").resolve(strict=False)
    first.write_bytes(b"first primary")
    second.write_bytes(b"second primary")
    third.write_bytes(b"companion")

    created = _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="create",
        document_id="primary_flip",
        internal_document_id="primary_flip",
        form_type="10-K",
        files=[first, second, third],
        filing_primary=first,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    created_meta = context.source_repository.get_source_meta("AAPL", "primary_flip", SourceKind.FILING)
    flipped = _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="update",
        document_id="primary_flip",
        internal_document_id="primary_flip",
        form_type="10-K",
        files=[third, first, second],
        filing_primary=second,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    flipped_meta = context.source_repository.get_source_meta("AAPL", "primary_flip", SourceKind.FILING)
    replayed = _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="update",
        document_id="primary_flip",
        internal_document_id="primary_flip",
        form_type="10-K",
        files=[first, third, second],
        filing_primary=second,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    replayed_meta = context.source_repository.get_source_meta("AAPL", "primary_flip", SourceKind.FILING)
    first_derived = f"{_build_filing_original_asset_identity(first)}_docling.json"
    second_original = _build_filing_original_asset_identity(second)
    second_derived = f"{second_original}_docling.json"
    entries = flipped_meta["files"]
    assert isinstance(entries, list)
    second_derived_entry = next(
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("name") == second_derived
    )

    assert created.status == "uploaded"
    assert created_meta["document_version"] == "v1"
    assert flipped.status == "uploaded"
    assert flipped_meta["document_version"] == "v2"
    assert flipped_meta["source_fingerprint"] != created_meta["source_fingerprint"]
    assert flipped_meta["primary_document"] == second_derived
    assert second_derived_entry["derived_from"] == second_original
    assert first_derived != second_derived
    assert replayed.status == "skipped"
    assert replayed_meta["document_version"] == "v2"
    assert replayed_meta["source_fingerprint"] == flipped_meta["source_fingerprint"]
    assert calls == [first.name, second.name]
    with context.source_repository.read_source_snapshot(
        "AAPL",
        "primary_flip",
        SourceKind.FILING,
        materialize_files=True,
    ) as snapshot:
        primary_source = snapshot.get_primary_source()
        with primary_source.open() as stream:
            assert stream.read() == b'{"name": "second.pdf", "source": "docling"}'
        assert primary_source.uri.endswith(f"/{second_derived}")


def test_ambiguous_filing_primary_forces_versions_then_recovers_safe_skip(tmp_path: Path) -> None:
    """不可区分 primary 等价类必须 v1→v2→v3，并在恢复可区分后 v4+skip。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: conservative unsafe、角色指针或恢复边界漂移时抛出。
    """

    calls: list[str] = []
    context = _build_service_context(tmp_path)
    context.service._docling_converter = _FakeDoclingConverter(calls)
    first_dir = (tmp_path / "first").resolve(strict=False)
    second_dir = (tmp_path / "second").resolve(strict=False)
    third_dir = (tmp_path / "third").resolve(strict=False)
    first_dir.mkdir()
    second_dir.mkdir()
    third_dir.mkdir()
    first = first_dir / "report.pdf"
    second = second_dir / "report.pdf"
    unique = third_dir / "primary.pdf"
    duplicate_companion = third_dir / "report.pdf"
    first.write_bytes(b"identical")
    second.write_bytes(b"identical")
    unique.write_bytes(b"unique")
    duplicate_companion.write_bytes(b"identical")
    first_asset = _build_filing_original_asset_for_test(first)
    second_asset = _build_filing_original_asset_for_test(second)
    first_primary_fingerprint = _build_upload_source_fingerprint(
        [first_asset, second_asset],
        source_kind=SourceKind.FILING,
        filing_primary=first,
    )
    second_primary_fingerprint = _build_upload_source_fingerprint(
        [second_asset, first_asset],
        source_kind=SourceKind.FILING,
        filing_primary=second,
    )
    companions_only_duplicate = _build_upload_source_fingerprint(
        [
            _build_filing_original_asset_for_test(unique),
            first_asset,
            _build_filing_original_asset_for_test(duplicate_companion),
        ],
        source_kind=SourceKind.FILING,
        filing_primary=unique,
    )

    assert first_primary_fingerprint.value == second_primary_fingerprint.value
    assert first_primary_fingerprint.identical_skip_safe is False
    assert second_primary_fingerprint.identical_skip_safe is False
    assert companions_only_duplicate.identical_skip_safe is True

    created = _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="create",
        document_id="ambiguous_primary",
        internal_document_id="ambiguous_primary",
        form_type="10-K",
        files=[first, second],
        filing_primary=first,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    created_meta = context.source_repository.get_source_meta(
        "AAPL", "ambiguous_primary", SourceKind.FILING
    )
    replayed_ambiguous = _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="update",
        document_id="ambiguous_primary",
        internal_document_id="ambiguous_primary",
        form_type="10-K",
        files=[first, second],
        filing_primary=first,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    replayed_meta = context.source_repository.get_source_meta(
        "AAPL", "ambiguous_primary", SourceKind.FILING
    )
    flipped = _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="update",
        document_id="ambiguous_primary",
        internal_document_id="ambiguous_primary",
        form_type="10-K",
        files=[first, second],
        filing_primary=second,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    flipped_meta = context.source_repository.get_source_meta(
        "AAPL", "ambiguous_primary", SourceKind.FILING
    )
    second_original = _build_filing_original_asset_identity(second)
    second_derived = f"{second_original}_docling.json"
    flipped_entries = flipped_meta["files"]
    assert isinstance(flipped_entries, list)
    flipped_derived_entry = next(
        entry
        for entry in flipped_entries
        if isinstance(entry, dict) and entry.get("name") == second_derived
    )

    assert created.status == "uploaded"
    assert created_meta["document_version"] == "v1"
    assert replayed_ambiguous.status == "uploaded"
    assert replayed_meta["document_version"] == "v2"
    assert flipped.status == "uploaded"
    assert flipped_meta["document_version"] == "v3"
    assert flipped_meta["primary_document"] == second_derived
    assert flipped_derived_entry["derived_from"] == second_original
    assert "identical_skip_safe" not in flipped_meta
    assert "filing_primary" not in flipped_meta
    with context.source_repository.read_source_snapshot(
        "AAPL",
        "ambiguous_primary",
        SourceKind.FILING,
        materialize_files=True,
    ) as snapshot:
        primary_source = snapshot.get_primary_source()
        with primary_source.open() as stream:
            assert stream.read() == b'{"name": "report.pdf", "source": "docling"}'
        assert primary_source.uri.endswith(f"/{second_derived}")

    first.write_bytes(b"now distinguishable")
    recovered = _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="update",
        document_id="ambiguous_primary",
        internal_document_id="ambiguous_primary",
        form_type="10-K",
        files=[first, second],
        filing_primary=second,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    recovered_meta = context.source_repository.get_source_meta(
        "AAPL", "ambiguous_primary", SourceKind.FILING
    )
    safe_replay = _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="update",
        document_id="ambiguous_primary",
        internal_document_id="ambiguous_primary",
        form_type="10-K",
        files=[second, first],
        filing_primary=second,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    safe_replay_meta = context.source_repository.get_source_meta(
        "AAPL", "ambiguous_primary", SourceKind.FILING
    )

    assert recovered.status == "uploaded"
    assert recovered_meta["document_version"] == "v4"
    assert safe_replay.status == "skipped"
    assert safe_replay_meta["document_version"] == "v4"
    assert calls == [first.name, first.name, second.name, second.name]


def test_safe_multifile_whole_set_move_keeps_v1_and_published_tree(tmp_path: Path) -> None:
    """可安全比较的 multi-file 整组移动必须命中相同 v2 fingerprint 并 skip。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: role association 混入路径或 skip 错误发布新 identity 时抛出。
    """

    calls: list[str] = []
    context = _build_service_context(tmp_path)
    context.service._docling_converter = _FakeDoclingConverter(calls)
    old_dir = (tmp_path / "old").resolve(strict=False)
    new_dir = (tmp_path / "new").resolve(strict=False)
    old_dir.mkdir()
    new_dir.mkdir()
    old_primary = old_dir / "main.pdf"
    old_companion = old_dir / "appendix.xlsx"
    new_primary = new_dir / "main.pdf"
    new_companion = new_dir / "appendix.xlsx"
    old_primary.write_bytes(b"main")
    old_companion.write_bytes(b"appendix")
    new_primary.write_bytes(b"main")
    new_companion.write_bytes(b"appendix")
    old_fingerprint = _build_upload_source_fingerprint(
        [
            _build_filing_original_asset_for_test(old_primary),
            _build_filing_original_asset_for_test(old_companion),
        ],
        source_kind=SourceKind.FILING,
        filing_primary=old_primary,
    )
    new_fingerprint = _build_upload_source_fingerprint(
        [
            _build_filing_original_asset_for_test(new_primary),
            _build_filing_original_asset_for_test(new_companion),
        ],
        source_kind=SourceKind.FILING,
        filing_primary=new_primary,
    )
    old_identities = {
        _build_filing_original_asset_identity(old_primary),
        _build_filing_original_asset_identity(old_companion),
    }
    new_identities = {
        _build_filing_original_asset_identity(new_primary),
        _build_filing_original_asset_identity(new_companion),
    }

    created = _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="create",
        document_id="whole_set_move",
        internal_document_id="whole_set_move",
        form_type="10-K",
        files=[old_primary, old_companion],
        filing_primary=old_primary,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    moved = _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="update",
        document_id="whole_set_move",
        internal_document_id="whole_set_move",
        form_type="10-K",
        files=[new_companion, new_primary],
        filing_primary=new_primary,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    meta = context.source_repository.get_source_meta("AAPL", "whole_set_move", SourceKind.FILING)
    entries = meta["files"]
    assert isinstance(entries, list)
    published_originals = {
        str(entry["name"])
        for entry in entries
        if isinstance(entry, dict) and entry.get("source") == "original"
    }

    assert old_identities.isdisjoint(new_identities)
    assert old_fingerprint.value == new_fingerprint.value
    assert old_fingerprint.identical_skip_safe is True
    assert new_fingerprint.identical_skip_safe is True
    assert created.status == "uploaded"
    assert moved.status == "skipped"
    assert meta["document_version"] == "v1"
    assert published_originals == old_identities
    assert calls == [old_primary.name]


def test_old_v1_multifile_fingerprint_transitions_once_to_v2_and_then_skips(tmp_path: Path) -> None:
    """旧无角色 multi-file digest 必须 fail-safe 更新到 v2，随后同角色重放 skip。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: legacy fixture、版本 transition 或 replay contract 漂移时抛出。
    """

    calls: list[str] = []
    context = _build_service_context(tmp_path)
    context.service._docling_converter = _FakeDoclingConverter(calls)
    primary = (tmp_path / "main.pdf").resolve(strict=False)
    companion = (tmp_path / "appendix.xlsx").resolve(strict=False)
    primary.write_bytes(b"main")
    companion.write_bytes(b"appendix")
    assets = [
        _build_filing_original_asset_for_test(primary),
        _build_filing_original_asset_for_test(companion),
    ]
    old_digest = _build_old_filing_fingerprint_for_test(assets)
    current_fingerprint = _build_upload_source_fingerprint(
        assets,
        source_kind=SourceKind.FILING,
        filing_primary=primary,
    )
    old_meta: dict[str, JsonValue] = {
        "document_version": "v1",
        "source_fingerprint": old_digest,
        "is_deleted": False,
    }

    assert current_fingerprint.value != old_digest
    assert current_fingerprint.identical_skip_safe is True
    assert _can_skip_upload(
        old_meta,
        current_fingerprint,
        False,
        repair_disposition=NoExistingSourceRepair(),
    ) is False
    prepared = asyncio.run(
        context.service.prepare_upload(
            ticker="AAPL",
            source_kind=SourceKind.FILING,
            action="update",
            document_id="old_v1_transition",
            internal_document_id="old_v1_transition",
            form_type="10-K",
            selection=FinsUploadFilingFiles.for_upsert(primary=primary, companions=(companion,)),
            overwrite=False,
            previous_meta=old_meta,
            meta={"ingest_method": "upload"},
            repair_disposition=NoExistingSourceRepair(),
            cancellation=None,
        )
    )
    assert isinstance(prepared, _PreparedAssetMutation)
    assert prepared.document_version == "v2"
    assert prepared.source_fingerprint == current_fingerprint.value
    assert isinstance(prepared.source_fingerprint, str)
    replayed = asyncio.run(
        context.service.prepare_upload(
            ticker="AAPL",
            source_kind=SourceKind.FILING,
            action="update",
            document_id="old_v1_transition",
            internal_document_id="old_v1_transition",
            form_type="10-K",
            selection=FinsUploadFilingFiles.for_upsert(primary=primary, companions=(companion,)),
            overwrite=False,
            previous_meta=prepared.meta,
            meta={"ingest_method": "upload"},
            repair_disposition=NoExistingSourceRepair(),
            cancellation=None,
        )
    )
    assert isinstance(replayed, UploadOperationResult)
    assert replayed.status == "skipped"
    assert prepared.meta["document_version"] == "v2"
    assert calls == [primary.name]

    single_assets = [_build_filing_original_asset_for_test(primary)]
    old_single_digest = _build_old_filing_fingerprint_for_test(single_assets)
    current_single = _build_upload_source_fingerprint(
        single_assets,
        source_kind=SourceKind.FILING,
        filing_primary=primary,
    )
    assert current_single.value == old_single_digest
    assert current_single.identical_skip_safe is True


def test_filing_fingerprint_excludes_path_identity_but_tracks_filename_and_content(tmp_path: Path) -> None:
    """filing fingerprint 必须忽略目录 identity，同时保留 basename 与内容语义。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: move/rename/content change 的 skip/version 语义漂移时抛出。
    """

    calls: list[str] = []
    context = _build_service_context(tmp_path)
    context.service._docling_converter = _FakeDoclingConverter(calls)
    first_dir = (tmp_path / "first").resolve(strict=False)
    moved_dir = (tmp_path / "moved").resolve(strict=False)
    first_dir.mkdir()
    moved_dir.mkdir()
    first = first_dir / "report.pdf"
    moved = moved_dir / "report.pdf"
    renamed = moved_dir / "renamed.pdf"
    first.write_bytes(b"same content")
    moved.write_bytes(b"same content")
    renamed.write_bytes(b"same content")

    created = _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="create",
        document_id="fingerprint_contract",
        internal_document_id="fingerprint_contract",
        form_type="10-K",
        files=[first],
        filing_primary=first,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    created_meta = context.source_repository.get_source_meta(
        "AAPL",
        "fingerprint_contract",
        SourceKind.FILING,
    )
    moved_result = _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="update",
        document_id="fingerprint_contract",
        internal_document_id="fingerprint_contract",
        form_type="10-K",
        files=[moved],
        filing_primary=moved,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    moved_meta = context.source_repository.get_source_meta(
        "AAPL",
        "fingerprint_contract",
        SourceKind.FILING,
    )
    renamed_result = _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="update",
        document_id="fingerprint_contract",
        internal_document_id="fingerprint_contract",
        form_type="10-K",
        files=[renamed],
        filing_primary=renamed,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    renamed_meta = context.source_repository.get_source_meta(
        "AAPL",
        "fingerprint_contract",
        SourceKind.FILING,
    )
    renamed.write_bytes(b"changed content")
    changed_result = _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="update",
        document_id="fingerprint_contract",
        internal_document_id="fingerprint_contract",
        form_type="10-K",
        files=[renamed],
        filing_primary=renamed,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    changed_meta = context.source_repository.get_source_meta(
        "AAPL",
        "fingerprint_contract",
        SourceKind.FILING,
    )

    assert _build_filing_original_asset_identity(first) != _build_filing_original_asset_identity(moved)
    assert created.status == "uploaded"
    assert created_meta["source_fingerprint"] == "e7d70a19bec88c733e519eace405aea9e0a357db2f7a53cdc9450d545c430848"
    assert moved_result.status == "skipped"
    assert moved_meta["source_fingerprint"] == created_meta["source_fingerprint"]
    assert moved_meta["document_version"] == "v1"
    assert renamed_result.status == "uploaded"
    assert renamed_meta["document_version"] == "v2"
    assert renamed_meta["source_fingerprint"] != created_meta["source_fingerprint"]
    assert changed_result.status == "uploaded"
    assert changed_meta["document_version"] == "v3"
    assert changed_meta["source_fingerprint"] != renamed_meta["source_fingerprint"]
    assert calls == ["report.pdf", "renamed.pdf", "renamed.pdf"]


def test_filing_one_hundred_originals_publish_with_one_conversion(tmp_path: Path) -> None:
    """100 个 filing inputs 必须发布 N+1 资产且只转换 explicit primary 一次。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: inclusive 上限、守恒计数或单转换语义漂移时抛出。
    """

    calls: list[str] = []
    context = _build_service_context(tmp_path)
    context.service._docling_converter = _FakeDoclingConverter(calls)
    files = [
        (tmp_path / f"input-{index:03d}.pdf").resolve(strict=False)
        for index in range(100)
    ]
    for index, file_path in enumerate(files):
        file_path.write_bytes(f"content:{index}".encode())
    primary = files[73]

    result = _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="create",
        document_id="hundred_inputs",
        internal_document_id="hundred_inputs",
        form_type="10-K",
        files=files,
        filing_primary=primary,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    meta = context.source_repository.get_source_meta("AAPL", "hundred_inputs", SourceKind.FILING)
    entries = meta["files"]
    assert isinstance(entries, list)

    assert result.stored_file_count == 100
    assert len(entries) == 101
    assert len({str(entry["name"]) for entry in entries}) == 101
    assert calls == [primary.name]
    assert meta["primary_document"] == f"{_build_filing_original_asset_identity(primary)}_docling.json"


@pytest.mark.parametrize("cancel_at", (2, 4, 5))
def test_existing_replacement_cancellation_keeps_entire_published_tree(
    tmp_path: Path,
    cancel_at: int,
) -> None:
    """reset 后 blob/final/precommit checkpoint 取消必须回滚整棵 ticker tree。

    Args:
        tmp_path: pytest 临时目录。
        cancel_at: publication 内命中的取消检查次序。

    Returns:
        无。

    Raises:
        AssertionError: 取消未回滚或 published tree 发生任何漂移时抛出。
    """

    context = _build_service_context(tmp_path)
    old_file = tmp_path / "deck.pdf"
    old_file.write_text("old", encoding="utf-8")
    _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.MATERIAL,
        action="create",
        document_id="mat_demo",
        internal_document_id="mat_demo",
        form_type="MATERIAL_OTHER",
        files=[old_file],
        overwrite=False,
        meta={"material_name": "Deck", "ingest_method": "upload"},
    )
    old_meta = context.source_repository.get_source_meta("AAPL", "mat_demo", SourceKind.MATERIAL)
    handle = SourceHandle(ticker="AAPL", document_id="mat_demo", source_kind=SourceKind.MATERIAL.value)
    old_entries = {entry.name for entry in context.blob_repository.list_entries(handle)}
    new_file = tmp_path / "deck-new.pdf"
    new_file.write_text("new", encoding="utf-8")
    prepared = asyncio.run(
        context.service.prepare_upload(
            ticker="AAPL",
            source_kind=SourceKind.MATERIAL,
            action="update",
            document_id="mat_demo",
            internal_document_id="mat_demo",
            form_type="MATERIAL_OTHER",
            selection=FinsUploadMaterialFiles.from_upsert_paths((new_file,)),
            overwrite=False,
            previous_meta=old_meta,
            meta={"material_name": "Deck", "ingest_method": "upload"},
            repair_disposition=NoExistingSourceRepair(),
            cancellation=None,
        )
    )
    assert not isinstance(prepared, UploadOperationResult)
    old_tree = published_tree_sha256(tmp_path, "AAPL")

    result = _publish_prepared_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        prepared=prepared,
        cancellation=_CancelOnNthCheck(cancel_at=cancel_at),
    )

    assert result.status == "cancelled"
    assert result.stored_file_count == 0
    assert published_tree_sha256(tmp_path, "AAPL") == old_tree
    assert context.source_repository.get_source_meta("AAPL", "mat_demo", SourceKind.MATERIAL) == old_meta
    assert {entry.name for entry in context.blob_repository.list_entries(handle)} == old_entries


@pytest.mark.parametrize("fail_at", (1, 2))
def test_existing_replacement_blob_failure_keeps_entire_published_tree(
    tmp_path: Path,
    fail_at: int,
) -> None:
    """reset 后任一 blob 写入失败必须丢弃 staging 并保留旧发布树。

    Args:
        tmp_path: pytest 临时目录。
        fail_at: 失败的 blob 写入次序。

    Returns:
        无。

    Raises:
        AssertionError: 失败未传播或 published tree 漂移时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = FsBatchingRepository(tmp_path, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    seed_blob_repository = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    seed_service = DoclingUploadService(
        source_repository=source_repository,
        blob_repository=seed_blob_repository,
        docling_converter=_FakeDoclingConverter(),
    )
    old_file = tmp_path / "old.txt"
    new_file = tmp_path / "renamed.txt"
    old_file.write_text("old", encoding="utf-8")
    new_file.write_text("new", encoding="utf-8")
    _execute_upload(
        service=seed_service,
        batching_repository=batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="create",
        document_id="filing_blob_failure",
        internal_document_id="filing_blob_failure",
        form_type="10-K",
        files=[old_file],
        filing_primary=old_file,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    old_tree = published_tree_sha256(tmp_path, "AAPL")
    failing_service = DoclingUploadService(
        source_repository=source_repository,
        blob_repository=_FailingNthUploadBlobRepository(
            tmp_path,
            repository_set,
            fail_at=fail_at,
        ),
        docling_converter=_FakeDoclingConverter(),
    )

    with pytest.raises(RuntimeError, match="forced replacement blob failure"):
        _execute_upload(
            service=failing_service,
            batching_repository=batching_repository,
            ticker="AAPL",
            source_kind=SourceKind.FILING,
            action="update",
            document_id="filing_blob_failure",
            internal_document_id="filing_blob_failure",
            form_type="10-K",
            files=[new_file],
            filing_primary=new_file,
            overwrite=False,
            meta={"ingest_method": "upload"},
        )

    assert published_tree_sha256(tmp_path, "AAPL") == old_tree


@pytest.mark.parametrize("overwrite", [False, True])
def test_execute_upload_update_failure_keeps_previous_document(
    tmp_path: Path,
    overwrite: bool,
) -> None:
    """update/overwrite final upsert 失败时 batch rollback 均保留旧文档。"""

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = FsBatchingRepository(tmp_path, repository_set=repository_set)
    seed_source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    seed_blob_repository = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    seed_service = DoclingUploadService(
        source_repository=seed_source_repository,
        blob_repository=seed_blob_repository,
        docling_converter=_FakeDoclingConverter(),
    )
    old_file = tmp_path / "deck.pdf"
    old_file.write_text("old", encoding="utf-8")
    _execute_upload(
        service=seed_service,
        batching_repository=batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.MATERIAL,
        action="create",
        document_id="mat_demo",
        internal_document_id="mat_demo",
        form_type="MATERIAL_OTHER",
        files=[old_file],
        overwrite=False,
        meta={"material_name": "Deck", "ingest_method": "upload"},
    )
    old_meta = seed_source_repository.get_source_meta("AAPL", "mat_demo", SourceKind.MATERIAL)
    handle = SourceHandle(ticker="AAPL", document_id="mat_demo", source_kind=SourceKind.MATERIAL.value)
    old_entries = {entry.name for entry in seed_blob_repository.list_entries(handle)}
    old_tree = published_tree_sha256(tmp_path, "AAPL")
    events: list[str] = []
    failing_source_repository = _FailingFinalUploadSourceRepository(tmp_path, repository_set, events)
    failing_service = DoclingUploadService(
        source_repository=failing_source_repository,
        blob_repository=seed_blob_repository,
        docling_converter=_FakeDoclingConverter(),
    )
    new_file = tmp_path / "deck-new.pdf"
    new_file.write_text("new", encoding="utf-8")

    with pytest.raises(RuntimeError, match="forced final upsert failure"):
        _execute_upload(
            service=failing_service,
            batching_repository=batching_repository,
            ticker="AAPL",
            source_kind=SourceKind.MATERIAL,
            action="update",
            document_id="mat_demo",
            internal_document_id="mat_demo",
            form_type="MATERIAL_OTHER",
            files=[new_file],
            overwrite=overwrite,
            meta={"material_name": "Deck", "ingest_method": "upload"},
        )

    assert failing_source_repository.get_source_meta("AAPL", "mat_demo", SourceKind.MATERIAL) == old_meta
    assert {entry.name for entry in seed_blob_repository.list_entries(handle)} == old_entries
    assert published_tree_sha256(tmp_path, "AAPL") == old_tree
    assert events[-1] == "create_failed"


def test_execute_upload_delete_material(tmp_path: Path) -> None:
    """delete 动作应执行逻辑删除且不要求文件。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    context = _build_service_context(tmp_path)
    sample_file = tmp_path / "deck.pdf"
    sample_file.write_text("hello", encoding="utf-8")
    _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.MATERIAL,
        action="create",
        document_id="mat_demo",
        internal_document_id="mat_demo",
        form_type="MATERIAL_OTHER",
        files=[sample_file],
        overwrite=False,
        meta={"material_name": "Deck", "ingest_method": "upload"},
    )

    result = _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.MATERIAL,
        action="delete",
        document_id="mat_demo",
        internal_document_id="mat_demo",
        form_type="MATERIAL_OTHER",
        files=[],
        overwrite=False,
        meta={},
    )

    meta = context.source_repository.get_source_meta("AAPL", "mat_demo", SourceKind.MATERIAL)
    assert result.status == "deleted"
    assert result.stored_file_count == 0
    assert meta["is_deleted"] is True


def test_upload_helper_id_and_version_rules() -> None:
    """上传 helper 应保留 OLD ID、版本与财期规则。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    cn_document_id, cn_internal_id = build_cn_filing_ids(
        ticker="600519",
        form_type="FY",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )
    sec_document_id, sec_internal_id = build_sec_filing_ids(
        ticker="AAPL",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=True,
    )
    material_id, material_internal_id = build_material_ids(
        form_type="MATERIAL_OTHER",
        material_name="Deck",
        fiscal_year=2024,
        fiscal_period="FY",
    )

    assert cn_document_id.startswith("fil_cn_")
    assert cn_internal_id.startswith("cn_")
    assert sec_document_id.startswith("fil_sec_")
    assert sec_internal_id.startswith("sec_")
    assert material_id == material_internal_id
    assert material_id.startswith("mat_")
    assert normalize_cn_fiscal_period("h1") == "H1"
    assert derive_report_kind("FY") == "annual"
    assert _increment_document_version("v2") == "v3"
    safe_fingerprint = _UploadSourceFingerprint(value="new", identical_skip_safe=True)
    unsafe_fingerprint = _UploadSourceFingerprint(value="same", identical_skip_safe=False)
    assert _resolve_document_version(None, safe_fingerprint) == "v1"
    assert _resolve_document_version(
        {"document_version": "v1", "source_fingerprint": "old"},
        safe_fingerprint,
    ) == "v2"
    assert _resolve_document_version(None, unsafe_fingerprint) == "v1"
    assert _resolve_document_version({"document_version": "v7"}, unsafe_fingerprint) == "v8"
    assert _can_skip_upload(
        {"is_deleted": False, "source_fingerprint": "same"},
        unsafe_fingerprint,
        False,
        repair_disposition=NoExistingSourceRepair(),
    ) is False
    assert validate_material_upload_ids(
        stable_document_id="mat_a",
        stable_internal_document_id="mat_a",
        document_id=None,
        internal_document_id=None,
    ) == ("mat_a", "mat_a")
    with pytest.raises(ValueError, match="document_id"):
        validate_material_upload_ids(
            stable_document_id="mat_a",
            stable_internal_document_id="mat_a",
            document_id="mat_b",
            internal_document_id=None,
        )


def test_upload_source_fingerprint_is_stable() -> None:
    """上传源指纹应按文件名排序保持稳定。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    first = [
        _PendingFileAsset("b.pdf", None, None, b"b", "application/pdf", "sha-b", 1, "original"),
        _PendingFileAsset("a.pdf", None, None, b"a", "application/pdf", "sha-a", 1, "original"),
    ]
    second = [
        _PendingFileAsset("a.pdf", None, None, b"a", "application/pdf", "sha-a", 1, "original"),
        _PendingFileAsset("b.pdf", None, None, b"b", "application/pdf", "sha-b", 1, "original"),
    ]

    expected_digest = "099dc9636e306c75f1d5d64dd0210123956ba73888e968088c7279baab1d7fdd"

    first_fingerprint = _build_upload_source_fingerprint(
        first,
        source_kind=SourceKind.MATERIAL,
        filing_primary=None,
    )
    second_fingerprint = _build_upload_source_fingerprint(
        second,
        source_kind=SourceKind.MATERIAL,
        filing_primary=None,
    )

    assert first_fingerprint.value == expected_digest
    assert second_fingerprint.value == expected_digest
    assert first_fingerprint.identical_skip_safe is True
    assert second_fingerprint.identical_skip_safe is True


def test_filing_fingerprint_rejects_empty_original_assets(tmp_path: Path) -> None:
    """filing fingerprint 必须拒绝空 original assets。

    Args:
        tmp_path: pytest 临时目录，用于提供合法绝对 primary 路径。

    Returns:
        无。

    Raises:
        AssertionError: owner 未以安全有界 ValueError fail closed 时抛出。
    """

    primary = (tmp_path / "report.pdf").resolve(strict=False)

    with pytest.raises(ValueError, match="^filing fingerprint 必须携带非空 originals$"):
        _build_upload_source_fingerprint(
            [],
            source_kind=SourceKind.FILING,
            filing_primary=primary,
        )


def test_filing_fingerprint_rejects_missing_authoritative_primary(tmp_path: Path) -> None:
    """filing fingerprint 必须拒绝缺失的 authoritative primary。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: owner 未以安全有界 ValueError fail closed 时抛出。
    """

    original = (tmp_path / "report.pdf").resolve(strict=False)
    original.write_bytes(b"report")
    asset = _build_filing_original_asset_for_test(original)

    with pytest.raises(ValueError, match="^filing fingerprint 必须携带 authoritative primary$"):
        _build_upload_source_fingerprint(
            [asset],
            source_kind=SourceKind.FILING,
            filing_primary=None,
        )


def test_filing_fingerprint_rejects_primary_without_exact_original_match(tmp_path: Path) -> None:
    """filing primary identity 未 exact 命中 original asset 时必须 fail closed。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: owner 接受不匹配 identity 或泄漏无界错误时抛出。
    """

    original = (tmp_path / "original.pdf").resolve(strict=False)
    unmatched_primary = (tmp_path / "other.pdf").resolve(strict=False)
    original.write_bytes(b"original")
    unmatched_primary.write_bytes(b"other")
    asset = _build_filing_original_asset_for_test(original)

    with pytest.raises(
        ValueError,
        match="^filing primary identity 必须 exact 命中一个 original asset$",
    ):
        _build_upload_source_fingerprint(
            [asset],
            source_kind=SourceKind.FILING,
            filing_primary=unmatched_primary,
        )


def test_material_fingerprint_rejects_filing_primary(tmp_path: Path) -> None:
    """material fingerprint 必须拒绝非法携带的 filing primary。

    Args:
        tmp_path: pytest 临时目录，用于提供合法绝对 primary 路径。

    Returns:
        无。

    Raises:
        AssertionError: owner 未以安全有界 ValueError fail closed 时抛出。
    """

    illegal_primary = (tmp_path / "report.pdf").resolve(strict=False)
    asset = _PendingFileAsset(
        name="deck.pdf",
        original_filename=None,
        derived_from=None,
        data=b"deck",
        content_type="application/pdf",
        sha256=hashlib.sha256(b"deck").hexdigest(),
        size=4,
        source="original",
    )

    with pytest.raises(ValueError, match="^material fingerprint 不得携带 filing primary$"):
        _build_upload_source_fingerprint(
            [asset],
            source_kind=SourceKind.MATERIAL,
            filing_primary=illegal_primary,
        )


def test_execute_upload_counts_only_successful_original_stores(tmp_path: Path) -> None:
    """多个 original 与 derived 资产落盘时只累计 original publication count。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: count 使用总资产数或 payload 保留旧字段时抛出。
    """

    context = _build_service_context(tmp_path)
    first_file = tmp_path / "first.pdf"
    second_file = tmp_path / "second.pdf"
    first_file.write_text("first", encoding="utf-8")
    second_file.write_text("second", encoding="utf-8")

    result = _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="create",
        document_id="filing_two_originals",
        internal_document_id="filing_two_originals",
        form_type="10-K",
        files=[first_file, second_file],
        filing_primary=first_file,
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    meta = context.source_repository.get_source_meta(
        "AAPL",
        "filing_two_originals",
        SourceKind.FILING,
    )

    assert len(meta["files"]) == 3
    assert result.stored_file_count == 2
