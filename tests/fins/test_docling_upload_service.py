"""DoclingUploadService 行为测试。"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Thread
from typing import BinaryIO, Optional

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import (
    BatchToken,
    DocumentHandle,
    FileObjectMeta,
    ProcessedHandle,
    SourceDocumentUpsertRequest,
    SourceHandle,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.docling_upload_service import (
    DoclingUploadService,
    PreparedDoclingUpload,
    UploadOperationResult,
    _PendingFileAsset,
    _build_upload_source_fingerprint,
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
    SourceIntegrityStatus,
)
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet, build_fs_repository_set
from dayu.fins.upload_failure import (
    FinsUploadFailureCode,
    FinsUploadFailureError,
    FinsUploadFailureKind,
)

from .upload_filing_test_support import published_tree_sha256


_INITIAL_CREATED_AT = "2020-01-01T00:00:00+00:00"
_REPLACEMENT_CREATED_AT = "2020-01-02T00:00:00+00:00"


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
    prepared = asyncio.run(
        service.prepare_upload(
            ticker=ticker,
            source_kind=source_kind,
            action=action,
            document_id=document_id,
            internal_document_id=internal_document_id,
            form_type=form_type,
            files=files,
            overwrite=overwrite,
            previous_meta=previous_meta,
            meta=meta,
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


def _prepare_filing_for_admission_test(
    *,
    service: DoclingUploadService,
    files: list[Path],
) -> PreparedDoclingUpload:
    """调用 filing prepare owner，不进入 publication batch。

    Args:
        service: 使用目标 converter 的上传服务。
        files: 按用户请求顺序排列的 filing 文件。

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
            files=files,
            overwrite=False,
            previous_meta=None,
            meta={"ingest_method": "upload"},
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
    context = _build_service_context(tmp_path)
    context.service._docling_converter = _FakeDoclingConverter(calls)
    empty_file = tmp_path / file_name
    empty_file.write_bytes(b"")

    with pytest.raises(FinsUploadFailureError) as exc_info:
        _prepare_filing_for_admission_test(service=context.service, files=[empty_file])

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
        _prepare_filing_for_admission_test(service=context.service, files=[filing_file])

    failure = exc_info.value.failure
    assert failure.kind is FinsUploadFailureKind.CONTENT
    assert failure.file_label == filing_file.name
    assert failure.message == "文件无法解析或已损坏，请检查文件后重试"
    assert safe_message not in str(failure)
    assert str(filing_file) not in str(failure)
    assert exc_info.value.__cause__ is cause
    assert calls == [filing_file.name]
    assert published_tree_sha256(tmp_path, "AAPL") == {}


@pytest.mark.parametrize(
    ("names", "failing_name", "expected_calls"),
    (
        (("bad.pdf", "later.docx"), "bad.pdf", ("bad.pdf",)),
        (("valid.pdf", "bad.docx", "later.pdf"), "bad.docx", ("valid.pdf", "bad.docx")),
    ),
)
def test_corrupt_mixed_filing_fails_fast_without_publication(
    tmp_path: Path,
    names: tuple[str, ...],
    failing_name: str,
    expected_calls: tuple[str, ...],
) -> None:
    """mixed filing 必须在首个损坏文件 fail-fast 且不产生 partial publication。

    Args:
        tmp_path: pytest 临时目录。
        names: 用户输入顺序。
        failing_name: 首个损坏文件 basename。
        expected_calls: 截止首个损坏文件的 converter 调用顺序。

    Returns:
        无。

    Raises:
        AssertionError: fail-fast 或 zero-publication 不变量漂移时抛出。
    """

    context = _build_service_context(tmp_path)
    files = [tmp_path / name for name in names]
    for file_path in files:
        file_path.write_bytes(b"filing input")
    cause = DoclingConversionError(
        DoclingConversionFailureKind.CONVERTER_EXECUTION,
        "Docling conversion execution failed",
        None,
    )
    calls: list[str] = []
    context.service._docling_converter = _SelectiveFailingDoclingConverter(
        failing_name=failing_name,
        error=cause,
        calls=calls,
    )

    with pytest.raises(FinsUploadFailureError):
        _prepare_filing_for_admission_test(service=context.service, files=files)

    assert calls == list(expected_calls)
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
            files=[sample_file],
            overwrite=False,
            previous_meta=None,
            meta={"material_name": "Deck", "ingest_method": "upload"},
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
            files=[sample_file],
            overwrite=False,
            previous_meta=None,
            meta={"material_name": "Deck", "ingest_method": "upload"},
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
                files=[sample_file],
                overwrite=overwrite,
                previous_meta=None,
                meta={"ingest_method": "upload"},
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
                files=[sample_file],
                overwrite=False,
                previous_meta=previous_meta,
                meta={"ingest_method": "upload"},
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
                name=sample_file.name,
                data=raw,
                content_type="text/plain",
                sha256=hashlib.sha256(raw).hexdigest(),
                size=len(raw),
                source="original",
            )
        ]
    )
    previous_meta: dict[str, JsonValue] = {"source_fingerprint": fingerprint}
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
                files=[sample_file],
                overwrite=False,
                previous_meta=previous_meta,
                meta={"ingest_method": "upload"},
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
    old_dir = tmp_path / "old-input"
    new_dir = tmp_path / "new-input"
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
        overwrite=overwrite,
        meta=base_meta,
    )

    final_meta = context.source_repository.get_source_meta("AAPL", document_id, source_kind)
    handle = SourceHandle(ticker="AAPL", document_id=document_id, source_kind=source_kind.value)
    published_names = sorted(item.uri.rsplit("/", maxsplit=1)[-1] for item in context.blob_repository.list_files(handle))
    expected_names = sorted((new_name, f"{Path(new_name).stem}_docling.json"))
    integrity = context.source_repository.classify_source_integrity("AAPL", document_id, source_kind)

    assert result.status == "uploaded"
    assert result.stored_file_count == 1
    assert published_names == expected_names
    assert context.blob_repository.read_file_bytes(handle, new_name) == b"new bytes"
    assert final_meta["document_version"] == "v2"
    assert final_meta["first_ingested_at"] == initial_meta["first_ingested_at"]
    assert final_meta["created_at"] == initial_meta["created_at"]
    assert final_meta["is_deleted"] is False
    assert integrity.status is SourceIntegrityStatus.COMPLETE


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
            files=[new_file],
            overwrite=False,
            previous_meta=old_meta,
            meta={"material_name": "Deck", "ingest_method": "upload"},
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
    assert _resolve_document_version(None, "fp") == "v1"
    assert _resolve_document_version({"document_version": "v1", "source_fingerprint": "old"}, "new") == "v2"
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
        _PendingFileAsset("b.pdf", b"b", "application/pdf", "sha-b", 1, "original"),
        _PendingFileAsset("a.pdf", b"a", "application/pdf", "sha-a", 1, "original"),
    ]
    second = [
        _PendingFileAsset("a.pdf", b"a", "application/pdf", "sha-a", 1, "original"),
        _PendingFileAsset("b.pdf", b"b", "application/pdf", "sha-b", 1, "original"),
    ]

    expected_digest = "099dc9636e306c75f1d5d64dd0210123956ba73888e968088c7279baab1d7fdd"

    assert _build_upload_source_fingerprint(first) == expected_digest
    assert _build_upload_source_fingerprint(second) == expected_digest


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
        overwrite=False,
        meta={"ingest_method": "upload"},
    )
    meta = context.source_repository.get_source_meta(
        "AAPL",
        "filing_two_originals",
        SourceKind.FILING,
    )

    assert len(meta["files"]) == 4
    assert result.stored_file_count == 2
