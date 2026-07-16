"""DoclingUploadService 行为测试。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import BinaryIO, Optional

import pytest

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
    _resolve_upsert_mode,
    build_cn_filing_ids,
    build_material_ids,
    build_sec_filing_ids,
    derive_report_kind,
    normalize_cn_fiscal_period,
    validate_material_upload_ids,
)
from dayu.fins.storage import (
    FsBatchingRepository,
    FsDocumentBlobRepository,
    FsSourceDocumentRepository,
)
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet, build_fs_repository_set


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

    def update_source_document(
        self,
        req: SourceDocumentUpsertRequest,
        source_kind: SourceKind,
        *,
        batch: BatchToken,
    ) -> DocumentHandle:
        """模拟 staging 后 final source update 失败。"""

        del req, source_kind, batch
        self._events.append("update_failed")
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


class _CancelOnNthCheck:
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


def _convert_docling_stub(raw_data: bytes, stream_name: str) -> dict[str, JsonValue]:
    """返回固定 Docling 转换结果。

    Args:
        raw_data: 输入原始字节。
        stream_name: 输入流名称。

    Returns:
        固定结构化结果。

    Raises:
        无。
    """

    del raw_data
    return {"name": stream_name, "source": "docling"}


def _publish_prepared_upload(
    *,
    service: DoclingUploadService,
    batching_repository: FsBatchingRepository,
    ticker: str,
    prepared: PreparedDoclingUpload,
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
    batch = batching_repository.begin_batch(ticker)
    try:
        result = service.publish_prepared_upload(prepared, batch=batch)
    except BaseException as operation_error:
        try:
            batching_repository.rollback_batch(batch)
        except Exception as rollback_error:
            operation_error.add_note(
                "rollback_batch failed; recovery evidence retained: "
                f"{rollback_error}"
            )
            raise operation_error from rollback_error
        raise
    if result.status == "cancelled":
        batching_repository.rollback_batch(batch)
    else:
        batching_repository.commit_batch(batch)
    return result


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
    cancellation_checker: Callable[[], bool] | None = None,
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

    prepared = service.prepare_upload(
        ticker=ticker,
        source_kind=source_kind,
        action=action,
        document_id=document_id,
        internal_document_id=internal_document_id,
        form_type=form_type,
        files=files,
        overwrite=overwrite,
        meta=meta,
        cancellation_checker=cancellation_checker,
    )
    return _publish_prepared_upload(
        service=service,
        batching_repository=batching_repository,
        ticker=ticker,
        prepared=prepared,
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
        convert_with_docling=_convert_docling_stub,
    )
    return _UploadServiceContext(
        batching_repository=batching_repository,
        source_repository=source_repository,
        blob_repository=blob_repository,
        service=service,
    )


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
    assert result.document_id == "mat_demo"
    assert len(result.file_events) == 3
    assert result.file_events[0].event_type == "conversion_started"
    meta = context.source_repository.get_source_meta("AAPL", "mat_demo", SourceKind.MATERIAL)
    assert str(meta["primary_document"]).endswith("_docling.json")
    assert meta["source_provider"] == "user_upload"
    assert len(meta["files"]) == 2


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
        convert_with_docling=_convert_docling_stub,
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
        convert_with_docling=_convert_docling_stub,
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
        convert_with_docling=_convert_docling_stub,
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
        convert_with_docling=_convert_docling_stub,
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
    batching_repository = FsBatchingRepository(tmp_path, repository_set=repository_set)
    source_repository = _FailingFinalUploadSourceRepository(tmp_path, repository_set, events)
    blob_repository = _BlobFirstUploadBlobRepository(tmp_path, repository_set, source_repository, events)
    service = DoclingUploadService(
        source_repository=source_repository,
        blob_repository=blob_repository,
        convert_with_docling=_convert_docling_stub,
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
    with pytest.raises(FileNotFoundError):
        source_repository.get_source_meta("AAPL", "mat_failed", SourceKind.MATERIAL)
    assert blob_repository.list_entries(handle) == []


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

    def counting_converter(raw_data: bytes, stream_name: str) -> dict[str, JsonValue]:
        """记录转换调用并返回固定结果。

        Args:
            raw_data: 输入原始字节。
            stream_name: 输入流名称。

        Returns:
            固定结构化结果。

        Raises:
            无。
        """

        del raw_data
        calls.append(stream_name)
        return {"name": stream_name, "source": "docling"}

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = FsBatchingRepository(tmp_path, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    service = DoclingUploadService(
        source_repository=source_repository,
        blob_repository=blob_repository,
        convert_with_docling=counting_converter,
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
    assert calls == ["deck.pdf"]
    assert all(event.event_type == "file_skipped" for event in second.file_events)


def test_execute_upload_overwrite_cancel_after_conversion_keeps_previous_document(tmp_path: Path) -> None:
    """overwrite 在转换后取消时应保留旧 source document。"""

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
    cancellation_checker = _CancelOnNthCheck(cancel_at=5)

    result = _execute_upload(
        service=context.service,
        batching_repository=context.batching_repository,
        ticker="AAPL",
        source_kind=SourceKind.MATERIAL,
        action="update",
        document_id="mat_demo",
        internal_document_id="mat_demo",
        form_type="MATERIAL_OTHER",
        files=[new_file],
        overwrite=True,
        cancellation_checker=cancellation_checker,
        meta={"material_name": "Deck", "ingest_method": "upload"},
    )

    assert result.status == "cancelled"
    assert context.source_repository.get_source_meta("AAPL", "mat_demo", SourceKind.MATERIAL) == old_meta
    assert {entry.name for entry in context.blob_repository.list_entries(handle)} == old_entries


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
        convert_with_docling=_convert_docling_stub,
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
    events: list[str] = []
    failing_source_repository = _FailingFinalUploadSourceRepository(tmp_path, repository_set, events)
    failing_service = DoclingUploadService(
        source_repository=failing_source_repository,
        blob_repository=seed_blob_repository,
        convert_with_docling=_convert_docling_stub,
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
    assert _resolve_upsert_mode("update", None, True) == "create"
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

    assert _build_upload_source_fingerprint(first) == _build_upload_source_fingerprint(second)
