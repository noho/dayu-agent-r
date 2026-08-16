"""SecPipeline upload filing stream 测试。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import multiprocessing
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from threading import Barrier as ThreadBarrier, Event, Lock
from typing import Protocol, cast

import pytest

from tests.fins.company_meta_test_support import stage_company_meta_fixture

import dayu.fins.pipelines.sec_upload_workflow as sec_upload_workflow
import dayu.fins.pipelines._filing_upload_fresh_validation as fresh_validation_module
from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.company_meta_contract import CompanyMetaCommitIntent
from dayu.fins.domain.document_models import (
    BatchToken,
    CompanyMeta,
    CompanyMetaInventoryEntry,
    SourceDocumentRevision,
    now_iso8601,
)
from dayu.fins.ticker_normalization import build_company_ticker_identity
from dayu.fins.domain.enums import SourceKind
from dayu.fins.ingestion_runtime import (
    FinsUploadFilingRequest,
    FinsUploadUsageCode,
    FinsUploadUsageError,
    ValidatedFinsUploadFilingRequest,
)
from dayu.fins.pipelines.sec_pipeline import SecPipeline, SecPipelineUploadResult
from dayu.fins.pipelines.docling_upload_service import (
    DoclingUploadService,
    PreparedDoclingUpload,
    describe_prepared_filing_publication,
    _build_filing_original_asset_identity,
)
from dayu.fins.pipelines.docling_process_converter import (
    DoclingConversionConfig,
    DoclingConversionCancelledError,
    DoclingConversionError,
    DoclingConversionFailureKind,
    DoclingConversionResult,
    DoclingConverter,
)
from dayu.fins.pipelines.upload_filing_events import UploadFilingEvent, UploadFilingEventType
from dayu.fins.pipelines.upload_company_meta import (
    RESOLVER_VERSION,
    stage_company_meta_for_upload,
)
from dayu.fins.processors.registry import build_fins_processor_registry
from dayu.fins.service_runtime import prevalidate_fins_upload_filing_request_for_workspace
from dayu.fins.upload_failure import fins_upload_source_publication_conflict_failure
from dayu.fins.storage import (
    DocumentBlobRepositoryProtocol,
    FilingUploadPublicationIdentity,
    FilingUploadStateRepositoryProtocol,
    FilingUploadPublishedState,
    FsDocumentBlobRepository,
    FsFilingUploadStateRepository,
    SourceDocumentRepositoryProtocol,
    SourceIntegrityStatus,
)
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet, build_fs_repository_set
from dayu.fins.upload_format_contract import FinsUploadFilingFiles, FinsUploadMaterialFiles
from dayu.fins.upload_repair_contract import ExistingSourceRepairDisposition
from dayu.runtime.filelock import RuntimeFileLockError

from .upload_filing_test_support import (
    TrackingBatchingRepository,
    TrackingCompanyMetaRepository,
    TrackingSourceDocumentRepository,
    published_tree_sha256,
)


class _SpyCompanyMetaRepository:
    """记录 company meta 写入次数的测试仓储。"""

    def __init__(self) -> None:
        """初始化空仓储。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.writes: list[CompanyMetaCommitIntent] = []

    def scan_company_meta_inventory(self) -> list[CompanyMetaInventoryEntry]:
        """返回空盘点结果。

        Args:
            无。

        Returns:
            空列表。

        Raises:
            无。
        """

        return []

    def get_company_meta(self, ticker: str) -> CompanyMeta:
        """模拟 company meta 不存在。

        Args:
            ticker: 查询 ticker。

        Returns:
            不返回。

        Raises:
            FileNotFoundError: 始终抛出以模拟空仓储。
        """

        raise FileNotFoundError(ticker)

    def stage_company_meta_intent(
        self,
        intent: CompanyMetaCommitIntent,
        *,
        batch: BatchToken,
    ) -> None:
        """记录一次 company meta 提交意图。

        Args:
            intent: 待提交公司元数据意图。
            batch: 测试 batch capability。

        Returns:
            无。

        Raises:
            无。
        """

        del batch
        self.writes.append(intent)

    def resolve_company_ticker(self, ticker: str) -> str | None:
        """模拟无 ticker 已存在。

        Args:
            ticker: ticker 查询值。

        Returns:
            始终返回 ``None``。

        Raises:
            无。
        """

        del ticker
        return None


class _FakeDoclingConverter:
    """SEC filing 测试用 typed converter。"""

    def __init__(self, calls: list[str] | None = None) -> None:
        """初始化 converter。

        Args:
            calls: 可选转换调用记录。

        Returns:
            无。

        Raises:
            无。
        """

        self._calls = calls

    async def convert_to_json_bytes(
        self,
        input_bytes: bytes,
        stream_name: str,
        *,
        config: DoclingConversionConfig,
        cancellation: CancellationToken | None,
    ) -> DoclingConversionResult:
        """返回固定 typed JSON bytes。

        Args:
            input_bytes: 输入字节。
            stream_name: 输入名称。
            config: 闭合转换配置。
            cancellation: canonical token。

        Returns:
            typed conversion result。

        Raises:
            无。
        """

        del input_bytes, config, cancellation
        if self._calls is not None:
            self._calls.append(stream_name)
        data = ('{"name": "' + stream_name + '", "format": "docling"}').encode()
        return DoclingConversionResult(data, len(data), hashlib.sha256(data).hexdigest())


class _BarrierPort(Protocol):
    """线程/进程 barrier 的最小同步协议。"""

    def wait(self, timeout: float | None = None) -> int:
        """等待所有参与方到达。

        Args:
            timeout: 最长等待秒数。

        Returns:
            当前参与方的 barrier index。

        Raises:
            BaseException: barrier broken 或底层同步失败时抛出。
        """

        ...


class _BatchReadBarrierFilingUploadStateRepository(FsFilingUploadStateRepository):
    """在 writer-owned fresh read 边界证明不同 ticker batch 可同时进入。"""

    def __init__(
        self,
        workspace_root: Path,
        *,
        repository_set: _FsRepositorySet,
        barrier: _BarrierPort,
        entered_events: dict[str, Event],
    ) -> None:
        """初始化 batch fresh-read 同步包装仓储。

        Args:
            workspace_root: 真实 filesystem workspace。
            repository_set: 与 batch/company/source 共用的 storage core。
            barrier: 两个不同 ticker fresh read 共用的会合点。
            entered_events: 按 canonical ticker 记录进入 fresh read 的通知。

        Returns:
            无。

        Raises:
            OSError: 基类仓储初始化失败时抛出。
        """

        super().__init__(workspace_root, repository_set=repository_set)
        self._barrier = barrier
        self._entered_events = entered_events

    def read_filing_upload_state_in_batch(
        self,
        batch: BatchToken,
        document_id: str,
    ) -> FilingUploadPublishedState:
        """在已取得 ticker batch 后会合，再读取该 staging view 的 fresh state。

        Args:
            batch: 已取得的 ticker writer batch capability。
            document_id: exact filing document ID。

        Returns:
            基类从 batch staging view 投影的 typed published state。

        Raises:
            AssertionError: 测试未登记当前 ticker 的 fresh-read 事件时抛出。
            threading.BrokenBarrierError: 另一 ticker 未在期限内同时进入时抛出。
            OSError: 基类读取失败时抛出。
            RuntimeError: 基类无法投影可信 business state 时抛出。
            ValueError: batch 或 document identity 非法时抛出。
        """

        entered = self._entered_events.get(batch.ticker)
        if entered is None:
            raise AssertionError(f"未登记 batch fresh-read ticker: {batch.ticker}")
        entered.set()
        self._barrier.wait(timeout=10)
        return super().read_filing_upload_state_in_batch(batch, document_id)


class _PreparedIdentityRecordingDoclingUploadService(DoclingUploadService):
    """记录真实 preparation owner 已产生的 filing publication identity。"""

    def __init__(
        self,
        source_repository: SourceDocumentRepositoryProtocol,
        blob_repository: DocumentBlobRepositoryProtocol,
        *,
        docling_converter: DoclingConverter,
        identities: list[FilingUploadPublicationIdentity],
    ) -> None:
        """初始化真实 Docling service 与 test-only identity sink。

        Args:
            source_repository: pipeline 共用的 source repository。
            blob_repository: pipeline 共用的 blob repository。
            docling_converter: 真实 workflow 使用的确定性 converter。
            identities: 接收 production helper 产生的 prepared identity。

        Returns:
            无。

        Raises:
            ValueError: 基类依赖缺失时抛出。
        """

        super().__init__(
            source_repository,
            blob_repository,
            docling_converter=docling_converter,
        )
        self._identities = identities

    async def prepare_upload(
        self,
        *,
        ticker: str,
        source_kind: SourceKind,
        action: str,
        document_id: str,
        internal_document_id: str,
        form_type: str,
        selection: FinsUploadFilingFiles | FinsUploadMaterialFiles,
        overwrite: bool,
        previous_meta: Mapping[str, JsonValue] | None,
        meta: Mapping[str, JsonValue],
        repair_disposition: ExistingSourceRepairDisposition,
        cancellation: CancellationToken | None,
    ) -> PreparedDoclingUpload:
        """执行真实 preparation，并用 production descriptor 记录 filing candidate。

        Args:
            ticker: canonical ticker。
            source_kind: filing 或 material。
            action: validated upload action。
            document_id: external filing document ID。
            internal_document_id: internal filing document ID。
            form_type: filing form type。
            selection: validator-owned file role selection。
            overwrite: create overwrite 开关。
            previous_meta: preparation observation 的 source meta。
            meta: workflow 业务 meta。
            repair_disposition: validator-owned repair authorization。
            cancellation: canonical cancellation token。

        Returns:
            基类产生的原始 typed prepared outcome。

        Raises:
            BaseException: 基类 preparation 或 production descriptor 异常原样传播。
        """

        prepared = await super().prepare_upload(
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
            repair_disposition=repair_disposition,
            cancellation=cancellation,
        )
        if source_kind is SourceKind.FILING and action != "delete":
            self._identities.append(describe_prepared_filing_publication(prepared))
        return prepared


@dataclass(frozen=True, slots=True)
class _SourceCommitSnapshot:
    """一个真实 commit 后由公开 source snapshot owner 读取的 durable facts。"""

    document_id: str
    source_meta: dict[str, JsonValue]
    revision: SourceDocumentRevision


class _CommitSnapshotTrackingBatchingRepository(TrackingBatchingRepository):
    """在两个真实 commit 之间确定性记录公开 source snapshot。"""

    def __init__(
        self,
        workspace_root: Path,
        *,
        repository_set: _FsRepositorySet,
        source_repository: SourceDocumentRepositoryProtocol,
        snapshots: list[_SourceCommitSnapshot],
    ) -> None:
        """初始化 commit snapshot recorder。

        Args:
            workspace_root: 真实 filesystem workspace。
            repository_set: pipeline repositories 共用的 storage core。
            source_repository: commit 后唯一公开 source read owner。
            snapshots: 接收按 commit 顺序记录的 durable snapshots。

        Returns:
            无。

        Raises:
            OSError: 基类初始化失败时抛出。
        """

        super().__init__(workspace_root, repository_set=repository_set)
        self._source_repository = source_repository
        self._snapshots = snapshots
        self._begin_lock = Lock()
        self._begin_attempts = 0
        self._first_snapshot_recorded = Event()

    def begin_batch(self, ticker: str) -> BatchToken:
        """让第二个 writer 在第一个 durable snapshot 已记录后再取得 batch。

        Args:
            ticker: canonical ticker。

        Returns:
            基类取得的真实 batch capability。

        Raises:
            TimeoutError: 第一个 commit snapshot 未在期限内产生时抛出。
            OSError: 真实 batch 初始化失败时抛出。
            ValueError: ticker 非法时抛出。
            RuntimeError: writer reservation 失败时抛出。
        """

        with self._begin_lock:
            begin_index = self._begin_attempts
            self._begin_attempts += 1
        if begin_index > 0 and not self._first_snapshot_recorded.wait(timeout=10):
            raise TimeoutError("first commit source snapshot 未产生")
        return super().begin_batch(ticker)

    def commit_batch(self, batch: BatchToken) -> None:
        """执行真实 commit 后从公开仓储读取同版 meta 与 opaque revision。

        Args:
            batch: caller 转交的真实 batch capability。

        Returns:
            commit 与 snapshot 记录成功后返回 ``None``。

        Raises:
            AssertionError: 当前测试 ticker 不只包含一个 filing target 时抛出。
            OSError: commit 或 snapshot 读取失败时抛出。
            ValueError: capability 或 durable source 非法时抛出。
            RuntimeError: publication/snapshot owner 失败时抛出。
        """

        super().commit_batch(batch)
        document_ids = self._source_repository.list_source_document_ids(
            batch.ticker,
            SourceKind.FILING,
        )
        if len(document_ids) != 1:
            raise AssertionError("create-overwrite commit 必须只有一个 filing target")
        document_id = document_ids[0]
        with self._source_repository.read_source_snapshot(
            batch.ticker,
            document_id,
            SourceKind.FILING,
            materialize_files=False,
        ) as snapshot:
            self._snapshots.append(
                _SourceCommitSnapshot(
                    document_id=document_id,
                    source_meta=dict(snapshot.source_meta),
                    revision=snapshot.revision,
                )
            )
        if len(self._snapshots) == 1:
            self._first_snapshot_recorded.set()


class _SpawnResultQueue(Protocol):
    """spawn worker 与父进程交换闭合结果的最小协议。"""

    def put(self, item: tuple[str, int]) -> None:
        """写入 worker 终态。

        Args:
            item: status 与 stored file count。

        Returns:
            无。

        Raises:
            OSError: queue 写入失败时抛出。
        """

        ...

    def get(self, *, timeout: float) -> tuple[str, int]:
        """读取一个 worker 终态。

        Args:
            timeout: 最长等待秒数。

        Returns:
            status 与 stored file count。

        Raises:
            queue.Empty: 超时仍无结果时抛出。
            OSError: queue 读取失败时抛出。
        """

        ...


class _BarrierDoclingConverter:
    """用真实线程 barrier 固定两个 publication candidate 均已完成转换。"""

    def __init__(self, barrier: _BarrierPort, *, marker: str = "shared") -> None:
        """初始化 barrier converter。

        Args:
            barrier: 两个 upload worker 共用的线程 barrier。
            marker: 写入派生 JSON 的稳定内容标识。

        Returns:
            无。

        Raises:
            无。
        """

        self._barrier = barrier
        self._marker = marker

    async def convert_to_json_bytes(
        self,
        input_bytes: bytes,
        stream_name: str,
        *,
        config: DoclingConversionConfig,
        cancellation: CancellationToken | None,
    ) -> DoclingConversionResult:
        """在转换完成边界同步两个 worker 后返回 typed 结果。

        Args:
            input_bytes: 输入字节。
            stream_name: 输入名称。
            config: 闭合转换配置。
            cancellation: canonical token。

        Returns:
            包含 marker 的 typed conversion result。

        Raises:
            threading.BrokenBarrierError: 另一 worker 未在超时内到达时抛出。
        """

        del input_bytes, config, cancellation
        data = json.dumps(
            {"format": "docling", "marker": self._marker, "name": stream_name},
            sort_keys=True,
        ).encode()
        self._barrier.wait(timeout=10)
        return DoclingConversionResult(data, len(data), hashlib.sha256(data).hexdigest())


class _CheckpointCancellationToken(CancellationToken):
    """在指定观察次数开始稳定返回 cancelled 的测试 token。"""

    def __init__(self, cancel_at_observation: int) -> None:
        """初始化计数型取消 token。

        Args:
            cancel_at_observation: 第几次 ``is_cancelled`` 观察开始返回真。

        Returns:
            无。

        Raises:
            ValueError: 观察次数不是正整数时抛出。
        """

        if cancel_at_observation < 1:
            raise ValueError("cancel_at_observation 必须为正整数")
        self._cancel_at_observation = cancel_at_observation
        self.observations = 0

    def is_cancelled(self) -> bool:
        """递增观察次数并返回稳定取消状态。

        Args:
            无。

        Returns:
            达到指定观察次数后返回 ``True``。

        Raises:
            无。
        """

        self.observations += 1
        return self.observations >= self._cancel_at_observation

    def cancel_reason(self) -> str | None:
        """返回测试取消原因。

        Args:
            无。

        Returns:
            已取消时返回稳定原因，否则返回 ``None``。

        Raises:
            无。
        """

        if self.observations >= self._cancel_at_observation:
            return "checkpoint-test"
        return None

    def requested_at(self) -> datetime | None:
        """测试 token 不声明墙钟时间。

        Args:
            无。

        Returns:
            始终返回 ``None``。

        Raises:
            无。
        """

        return None


class _FailingDoclingConverter:
    """抛出指定 typed/runtime exception 的 converter 测试替身。"""

    def __init__(
        self,
        error: Exception,
        *,
        failing_name: str | None = None,
        calls: list[str] | None = None,
    ) -> None:
        """初始化 failure converter。

        Args:
            error: conversion 调用应抛出的异常。
            failing_name: 仅该 basename 抛错；``None`` 表示每次都抛错。
            calls: 可选 converter 调用顺序记录。

        Returns:
            无。

        Raises:
            无。
        """

        self.error = error
        self._failing_name = failing_name
        self._calls = calls

    async def convert_to_json_bytes(
        self,
        input_bytes: bytes,
        stream_name: str,
        *,
        config: DoclingConversionConfig,
        cancellation: CancellationToken | None,
    ) -> DoclingConversionResult:
        """抛出预设异常以验证 workflow typed catch 顺序。

        Args:
            input_bytes: 输入字节。
            stream_name: 输入名称。
            config: 闭合转换配置。
            cancellation: canonical cancellation token。

        Returns:
            不返回。

        Raises:
            Exception: 始终抛出构造时传入的异常。
        """

        del input_bytes, config, cancellation
        if self._calls is not None:
            self._calls.append(stream_name)
        if self._failing_name is None or stream_name == self._failing_name:
            raise self.error
        data = ('{"name": "' + stream_name + '", "format": "docling"}').encode()
        return DoclingConversionResult(data, len(data), hashlib.sha256(data).hexdigest())


def _validated_sec_filing_request(
    *,
    pipeline: SecPipeline,
    filing_file: Path,
    action: str | None,
    company_name: str | None,
    overwrite: bool = False,
    ticker_aliases: tuple[str, ...] = (),
    fiscal_year: int = 2025,
    fiscal_period: str = "Q1",
    filing_date: str | None = None,
    report_date: str | None = None,
    ticker: str = "AAPL",
    companion_files: tuple[Path, ...] = (),
) -> ValidatedFinsUploadFilingRequest:
    """使用 production validator 构造 SEC filing 测试请求。

    Args:
        pipeline: 持有当前 published state 的 SEC pipeline。
        filing_file: 上传文件。
        action: 请求动作；``None`` 表示 auto。
        company_name: 可选公司名称。
        overwrite: 是否覆盖既有 filing。
        ticker_aliases: 可选 ticker aliases。
        fiscal_year: 财年。
        fiscal_period: 财期。
        filing_date: 可选披露日期。
        report_date: 可选报告日期。
        ticker: SEC ticker。
        companion_files: 可选完整 authoritative companions。

    Returns:
        由 production storage/validator owner 产生的 validated request。

    Raises:
        FinsUploadUsageError: 请求不满足 filing usage contract 时抛出。
        OSError: published state 读取失败时抛出。
        ValueError: published state 损坏时抛出。
    """

    return prevalidate_fins_upload_filing_request_for_workspace(
        FinsUploadFilingRequest(
            ticker=ticker,
            action=action or "auto",
            files=() if action == "delete" else (filing_file, *companion_files),
            primary_selectors=(filing_file,) if companion_files else (),
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            filing_date=filing_date,
            report_date=report_date,
            company_name=company_name,
            ticker_aliases=ticker_aliases,
            overwrite=overwrite,
        ),
        workspace_root=pipeline._workspace_root,
    )


def _read_json_object(path: Path) -> dict[str, JsonValue]:
    """读取 workflow filesystem fixture 的 JSON 对象。

    Args:
        path: 已知 storage-owned JSON 文件。

    Returns:
        JSON object。

    Raises:
        OSError: 文件读取失败时抛出。
        ValueError: JSON 根不是对象时抛出。
    """

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("workflow repair fixture JSON 必须是对象")
    return payload


def _write_json_object(path: Path, payload: dict[str, JsonValue]) -> None:
    """确定性写回 workflow filesystem fixture JSON 对象。

    Args:
        path: 已知 storage-owned JSON 文件。
        payload: 单点损坏后的 JSON object。

    Returns:
        无。

    Raises:
        OSError: 文件写入失败时抛出。
    """

    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _corrupt_published_filing_for_repair(
    *,
    pipeline: SecPipeline,
    document_id: str,
    corruption: str,
) -> None:
    """对 SEC published filing 注入一个 repairable filesystem fact。

    Args:
        pipeline: 持有真实 filesystem repositories 的 SEC pipeline。
        document_id: exact filing document ID。
        corruption: repairable corruption case。

    Returns:
        无。

    Raises:
        OSError: fixture 文件读写失败时抛出。
        ValueError: persisted meta 或 corruption case 非法时抛出。
    """

    locator = pipeline._source_repository.get_source_document_locator(
        "AAPL",
        document_id,
        SourceKind.FILING,
    )
    source_dir = pipeline._workspace_root / locator
    meta_path = source_dir / "meta.json"
    meta = _read_json_object(meta_path)
    raw_files = meta.get("files")
    if not isinstance(raw_files, list):
        raise ValueError("workflow repair fixture files 必须是数组")
    files = [item for item in raw_files if isinstance(item, dict)]
    originals = [item for item in files if item.get("source") == "original"]
    derived = [item for item in files if item.get("source") == "docling"]
    if not originals or len(derived) != 1:
        raise ValueError("workflow repair fixture 角色不完整")
    original_name = originals[0].get("name")
    derived_name = derived[0].get("name")
    if not isinstance(original_name, str) or not isinstance(derived_name, str):
        raise ValueError("workflow repair fixture 文件名非法")
    if corruption == "original_missing":
        (source_dir / original_name).unlink()
        return
    if corruption == "original_digest":
        original_path = source_dir / original_name
        original_path.write_bytes(b"X" * len(original_path.read_bytes()))
        return
    if corruption == "docling_missing":
        (source_dir / derived_name).unlink()
        return
    if corruption == "meta_digest":
        originals[0]["sha256"] = "0" * 64
        _write_json_object(meta_path, meta)
        return
    if corruption == "manifest_missing":
        (source_dir.parent / "filing_manifest.json").unlink()
        return
    raise ValueError("未知 workflow repair corruption")


def _tracking_sec_pipeline(
    workspace_root: Path,
    *,
    converter_calls: list[str] | None = None,
    converter: DoclingConverter | None = None,
    batch_read_barrier: _BarrierPort | None = None,
    batch_read_events: dict[str, Event] | None = None,
    prepared_identities: list[FilingUploadPublicationIdentity] | None = None,
    commit_snapshots: list[_SourceCommitSnapshot] | None = None,
) -> tuple[
    SecPipeline,
    TrackingBatchingRepository,
    TrackingCompanyMetaRepository,
    TrackingSourceDocumentRepository,
]:
    """构造共享同一 FS core 的 SEC upload tracking composition。

    Args:
        workspace_root: 测试工作区根目录。
        converter_calls: 可选转换调用记录。
        converter: 可选 typed converter；未提供时构造默认 fake。
        batch_read_barrier: 可选 writer-owned fresh read 会合点。
        batch_read_events: 与会合点配套的 canonical ticker 进入通知。
        prepared_identities: 可选真实 filing preparation identity 记录 sink。
        commit_snapshots: 可选 create-overwrite commit 后 durable snapshot 记录 sink。

    Returns:
        pipeline、batch、company 与 source tracking repositories。

    Raises:
        OSError: storage composition 初始化失败时抛出。
        ValueError: fresh-read barrier 与事件未成对提供时抛出。
    """

    repository_set = build_fs_repository_set(
        workspace_root=workspace_root,
        create_directories=False,
    )
    company = TrackingCompanyMetaRepository(workspace_root, repository_set=repository_set)
    source = TrackingSourceDocumentRepository(workspace_root, repository_set=repository_set)
    batching: TrackingBatchingRepository
    if commit_snapshots is None:
        batching = TrackingBatchingRepository(workspace_root, repository_set=repository_set)
    else:
        batching = _CommitSnapshotTrackingBatchingRepository(
            workspace_root,
            repository_set=repository_set,
            source_repository=source,
            snapshots=commit_snapshots,
        )
    if (batch_read_barrier is None) is not (batch_read_events is None):
        raise ValueError("batch_read_barrier 与 batch_read_events 必须成对提供")
    filing_state_repository: FilingUploadStateRepositoryProtocol
    if batch_read_barrier is not None and batch_read_events is not None:
        filing_state_repository = _BatchReadBarrierFilingUploadStateRepository(
            workspace_root,
            repository_set=repository_set,
            barrier=batch_read_barrier,
            entered_events=batch_read_events,
        )
    else:
        filing_state_repository = FsFilingUploadStateRepository(
            workspace_root,
            repository_set=repository_set,
        )
    effective_converter = converter or _FakeDoclingConverter(converter_calls)
    blob_repository = FsDocumentBlobRepository(
        workspace_root,
        repository_set=repository_set,
    )
    pipeline = SecPipeline(
        workspace_root=workspace_root,
        processor_registry=build_fins_processor_registry(),
        batching_repository=batching,
        company_repository=company,
        source_repository=source,
        blob_repository=blob_repository,
        filing_upload_state_repository=filing_state_repository,
        docling_converter=effective_converter,
    )
    if prepared_identities is not None:
        pipeline._upload_service = _PreparedIdentityRecordingDoclingUploadService(
            source,
            blob_repository,
            docling_converter=effective_converter,
            identities=prepared_identities,
        )
    return pipeline, batching, company, source


def _run_two_sec_uploads(
    *,
    first_pipeline: SecPipeline,
    first_request: ValidatedFinsUploadFilingRequest,
    second_pipeline: SecPipeline,
    second_request: ValidatedFinsUploadFilingRequest,
) -> tuple[SecPipelineUploadResult, SecPipelineUploadResult]:
    """在两个真实 OS 线程中同时执行 SEC upload。

    Args:
        first_pipeline: 第一条 workflow composition。
        first_request: 第一条已验证请求。
        second_pipeline: 第二条 workflow composition。
        second_request: 第二条已验证请求。

    Returns:
        与输入顺序一致的两个聚合终态。

    Raises:
        BaseException: 任一 worker 未被 workflow 封闭的异常或超时时抛出。
    """

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(first_pipeline.upload_filing, first_request)
        second_future = executor.submit(second_pipeline.upload_filing, second_request)
        return first_future.result(timeout=20), second_future.result(timeout=20)


async def _collect_sec_upload_stream(
    pipeline: SecPipeline,
    request: ValidatedFinsUploadFilingRequest,
) -> tuple[UploadFilingEvent, ...]:
    """完整收集一条真实 SEC upload stream。

    Args:
        pipeline: SEC workflow composition。
        request: 已验证 filing request。

    Returns:
        按真实 yield 顺序排列的 typed events。

    Raises:
        BaseException: stream 未封闭的异常原样传播。
    """

    return tuple([event async for event in pipeline.upload_filing_stream(request)])


def _collect_sec_upload_stream_sync(
    pipeline: SecPipeline,
    request: ValidatedFinsUploadFilingRequest,
) -> tuple[UploadFilingEvent, ...]:
    """在线程 worker 内运行并完整收集一条 SEC upload stream。

    Args:
        pipeline: SEC workflow composition。
        request: 已验证 filing request。

    Returns:
        按真实 yield 顺序排列的 typed events。

    Raises:
        BaseException: event loop 或 stream 异常原样传播。
    """

    return asyncio.run(_collect_sec_upload_stream(pipeline, request))


def _run_two_sec_upload_streams(
    *,
    first_pipeline: SecPipeline,
    first_request: ValidatedFinsUploadFilingRequest,
    second_pipeline: SecPipeline,
    second_request: ValidatedFinsUploadFilingRequest,
) -> tuple[tuple[UploadFilingEvent, ...], tuple[UploadFilingEvent, ...]]:
    """在两个真实线程中并发收集完整 SEC upload streams。

    Args:
        first_pipeline: 第一条 workflow composition。
        first_request: 第一条已验证请求。
        second_pipeline: 第二条 workflow composition。
        second_request: 第二条已验证请求。

    Returns:
        与输入顺序一致的两条完整 event tuples。

    Raises:
        BaseException: 任一 worker 未封闭异常或 future 超时时原样传播。
    """

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(
            _collect_sec_upload_stream_sync,
            first_pipeline,
            first_request,
        )
        second_future = executor.submit(
            _collect_sec_upload_stream_sync,
            second_pipeline,
            second_request,
        )
        return first_future.result(timeout=20), second_future.result(timeout=20)


def _sec_upload_stream_result(
    events: tuple[UploadFilingEvent, ...],
) -> SecPipelineUploadResult:
    """从完整 SEC upload stream 的唯一末事件读取聚合结果。

    Args:
        events: 一条完整真实 upload stream。

    Returns:
        terminal payload 中的 JSON result object。

    Raises:
        AssertionError: stream 为空、末事件非完成终态或 result 非 object 时抛出。
    """

    if not events or events[-1].event_type is not UploadFilingEventType.UPLOAD_COMPLETED:
        raise AssertionError("SEC upload stream 必须以 UPLOAD_COMPLETED 终结")
    result = events[-1].payload.get("result")
    if not isinstance(result, dict):
        raise AssertionError("SEC upload completed event 必须携带 result object")
    return result


def _spawn_identical_sec_upload_worker(
    workspace_root_text: str,
    filing_file_text: str,
    barrier: _BarrierPort,
    result_queue: _SpawnResultQueue,
) -> None:
    """在 spawn 子进程中执行一条 identical auto SEC upload。

    Args:
        workspace_root_text: 共享真实 filesystem workspace 路径。
        filing_file_text: 共享 authoritative primary 路径。
        barrier: 跨进程 conversion barrier。
        result_queue: 返回闭合终态的跨进程 queue。

    Returns:
        无。

    Raises:
        BaseException: pipeline 初始化、prevalidation 或 workflow 异常时原样抛出。
    """

    workspace_root = Path(workspace_root_text)
    filing_file = Path(filing_file_text)
    pipeline = SecPipeline(
        workspace_root=workspace_root,
        processor_registry=build_fins_processor_registry(),
        docling_converter=_BarrierDoclingConverter(barrier),
    )
    request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=filing_file,
        action=None,
        company_name="Apple Inc.",
    )
    result = pipeline.upload_filing(request)
    status = result["status"]
    stored_file_count = result["stored_file_count"]
    if not isinstance(status, str) or not isinstance(stored_file_count, int):
        raise TypeError("spawn upload result 必须携带 string status 与 int stored_file_count")
    result_queue.put((status, stored_file_count))


def _seed_sec_upload_company_meta(
    *,
    pipeline: SecPipeline,
    company_name: str,
    resolver_version: str,
    ticker_aliases: list[str],
) -> None:
    """写入 SEC upload 测试用公司元数据。

    Args:
        pipeline: SEC pipeline 实例。
        company_name: 公司名称。
        resolver_version: 元数据 resolver 版本。
        ticker_aliases: ticker alias 列表。

    Returns:
        无。

    Raises:
        OSError: 仓储写入失败时抛出。
    """

    batch = pipeline._batching_repository.begin_batch("AAPL")
    stage_company_meta_fixture(
        pipeline._company_repository,
        CompanyMeta(
            company_id="AAPL_US",
            company_name=company_name,
            ticker_identity=build_company_ticker_identity("AAPL", ticker_aliases),
            resolver_version=resolver_version,
            updated_at=now_iso8601(),
        ),
        batch=batch,
    )
    pipeline._batching_repository.commit_batch(batch)


def test_upload_company_meta_invalid_ticker_alias_fails_before_repository_write() -> None:
    """非 ticker alias 必须在 company meta 仓储写入前失败关闭。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 非法 alias 被写入或未抛 ``ValueError`` 时抛出。
    """

    repository = _SpyCompanyMetaRepository()

    with pytest.raises(ValueError, match="无法识别的 ticker"):
        stage_company_meta_for_upload(
            repository=repository,
            ticker="AAPL",
            action="create",
            company_name="Apple Inc.",
            ticker_aliases=["AAPL", "Apple Inc."],
            batch=BatchToken(transaction_id="invalid-alias", ticker="AAPL"),
        )

    assert repository.writes == []


@pytest.mark.asyncio
async def test_upload_filing_stream_uploads_docling_files(tmp_path: Path) -> None:
    """SEC filing upload stream 应完成上传并生成 Docling 主文件。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    pipeline, batching, company, source = _tracking_sec_pipeline(tmp_path)
    filing_file = tmp_path / "filing.pdf"
    filing_file.write_text("demo filing", encoding="utf-8")
    before_tree = published_tree_sha256(tmp_path, "AAPL")

    events = [
        event
        async for event in pipeline.upload_filing_stream(
            _validated_sec_filing_request(
                pipeline=pipeline,
                filing_file=filing_file,
                action="create",
                company_name="Apple Inc.",
                ticker_aliases=("AAPL", "APC"),
                filing_date="2025-05-01",
                report_date="2025-03-31",
            )
        )
    ]

    assert [event.event_type for event in events] == [
        UploadFilingEventType.UPLOAD_STARTED,
        UploadFilingEventType.CONVERSION_STARTED,
        UploadFilingEventType.FILE_UPLOADED,
        UploadFilingEventType.FILE_UPLOADED,
        UploadFilingEventType.UPLOAD_COMPLETED,
    ]
    result_value = events[-1].payload["result"]
    assert isinstance(result_value, dict)
    assert result_value["action"] == "upload_filing"
    assert result_value["ticker"] == "AAPL"
    assert result_value["status"] == "ok"
    assert result_value["stored_file_count"] == 1
    assert str(result_value["document_id"]).startswith("fil_sec_")
    assert result_value["filing_action"] == "create"
    company_meta = pipeline._company_repository.get_company_meta("AAPL")
    assert company_meta.ticker_identity.accepted_aliases == ("APC",)
    meta = pipeline._source_repository.get_source_meta(
        "AAPL",
        str(result_value["document_id"]),
        SourceKind.FILING,
    )
    assert str(meta["primary_document"]).endswith("_docling.json")
    assert str(meta["form_type"]) == "Q1"
    after_tree = published_tree_sha256(tmp_path, "AAPL")
    assert before_tree == {}
    assert after_tree
    assert len(batching.begin_tokens) == 1
    assert batching.commit_tokens == batching.begin_tokens
    assert batching.rollback_tokens == []
    assert company.stage_tokens == batching.begin_tokens
    assert source.stage_tokens == batching.begin_tokens


@pytest.mark.asyncio
async def test_upload_filing_stream_preserves_same_version_company_meta(tmp_path: Path) -> None:
    """SEC filing upload 遇到同版本公司元数据时应保留既有值。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        processor_registry=build_fins_processor_registry(),
        docling_converter=_FakeDoclingConverter(),
    )
    _seed_sec_upload_company_meta(
        pipeline=pipeline,
        company_name="Existing Apple",
        resolver_version=RESOLVER_VERSION,
        ticker_aliases=["AAPL", "OLD"],
    )
    filing_file = tmp_path / "filing.pdf"
    filing_file.write_text("demo filing", encoding="utf-8")

    events = [
        event
        async for event in pipeline.upload_filing_stream(
            _validated_sec_filing_request(
                pipeline=pipeline,
                filing_file=filing_file,
                action="create",
                company_name="Ignored Apple",
                ticker_aliases=("AAPL", "NEW"),
            )
        )
    ]

    assert events[-1].event_type == UploadFilingEventType.UPLOAD_COMPLETED
    company_meta = pipeline._company_repository.get_company_meta("AAPL")
    assert company_meta.company_name == "Existing Apple"
    assert company_meta.resolver_version == RESOLVER_VERSION
    assert company_meta.ticker_identity.accepted_aliases == ("OLD", "NEW")


@pytest.mark.asyncio
async def test_upload_filing_stream_refreshes_stale_company_meta(tmp_path: Path) -> None:
    """SEC filing upload 遇到旧 resolver 版本公司元数据时应刷新。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        processor_registry=build_fins_processor_registry(),
        docling_converter=_FakeDoclingConverter(),
    )
    _seed_sec_upload_company_meta(
        pipeline=pipeline,
        company_name="Stale Apple",
        resolver_version="market_resolver_v0.9.0",
        ticker_aliases=["AAPL", "STALE"],
    )
    filing_file = tmp_path / "filing.pdf"
    filing_file.write_text("demo filing", encoding="utf-8")

    events = [
        event
        async for event in pipeline.upload_filing_stream(
            _validated_sec_filing_request(
                pipeline=pipeline,
                filing_file=filing_file,
                action="create",
                company_name="Apple Refreshed",
                ticker_aliases=("AAPL", "APC"),
            )
        )
    ]

    assert events[-1].event_type == UploadFilingEventType.UPLOAD_COMPLETED
    company_meta = pipeline._company_repository.get_company_meta("AAPL")
    assert company_meta.company_id == "AAPL_US"
    assert company_meta.company_name == "Apple Refreshed"
    assert company_meta.resolver_version == RESOLVER_VERSION
    assert company_meta.ticker_identity.accepted_aliases == ("STALE", "APC")


@pytest.mark.asyncio
async def test_upload_filing_stream_stale_company_meta_requires_company_name(tmp_path: Path) -> None:
    """SEC filing upload 遇到旧 resolver 版本且缺少公司名时应失败关闭。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        processor_registry=build_fins_processor_registry(),
        docling_converter=_FakeDoclingConverter(),
    )
    _seed_sec_upload_company_meta(
        pipeline=pipeline,
        company_name="Stale Apple",
        resolver_version="market_resolver_v0.9.0",
        ticker_aliases=["AAPL", "STALE"],
    )
    filing_file = tmp_path / "filing.pdf"
    filing_file.write_text("demo filing", encoding="utf-8")

    with pytest.raises(FinsUploadUsageError) as exc_info:
        _validated_sec_filing_request(
            pipeline=pipeline,
            filing_file=filing_file,
            action="create",
            company_name=None,
        )

    assert exc_info.value.failure.code is FinsUploadUsageCode.COMPANY_NAME_REQUIRED
    assert exc_info.value.failure.message == ("当前公司缺少有效元数据；create/update 必须提供 --company-name")
    company_meta = pipeline._company_repository.get_company_meta("AAPL")
    assert company_meta.company_name == "Stale Apple"
    assert company_meta.resolver_version == "market_resolver_v0.9.0"


@pytest.mark.asyncio
async def test_upload_filing_stream_renamed_update_without_overwrite_replaces_complete_set(
    tmp_path: Path,
) -> None:
    """SEC renamed update 不依赖 overwrite，并只发布新完整文件集合。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        processor_registry=build_fins_processor_registry(),
        docling_converter=_FakeDoclingConverter(),
    )
    old_file = tmp_path / "q1_old.pdf"
    new_file = tmp_path / "q1_renamed.pdf"
    sibling_file = tmp_path / "q2_sibling.pdf"
    old_file.write_text("old filing", encoding="utf-8")
    new_file.write_text("new filing", encoding="utf-8")
    sibling_file.write_text("sibling filing", encoding="utf-8")

    create_events = [
        event
        async for event in pipeline.upload_filing_stream(
            _validated_sec_filing_request(
                pipeline=pipeline,
                filing_file=old_file,
                action=None,
                company_name="Apple Inc.",
            )
        )
    ]
    create_result = create_events[-1].payload["result"]
    assert isinstance(create_result, dict)
    assert create_result["filing_action"] == "create"

    skip_events = [
        event
        async for event in pipeline.upload_filing_stream(
            _validated_sec_filing_request(
                pipeline=pipeline,
                filing_file=old_file,
                action=None,
                company_name="Apple Inc.",
            )
        )
    ]
    skip_result = skip_events[-1].payload["result"]
    assert isinstance(skip_result, dict)
    assert skip_result["status"] == "skipped"
    assert skip_result["stored_file_count"] == 0
    assert skip_result["filing_action"] == "update"
    sibling_events = [
        event
        async for event in pipeline.upload_filing_stream(
            _validated_sec_filing_request(
                pipeline=pipeline,
                filing_file=sibling_file,
                action=None,
                company_name="Apple Inc.",
                fiscal_period="Q2",
            )
        )
    ]
    sibling_result = sibling_events[-1].payload["result"]
    assert isinstance(sibling_result, dict)
    sibling_document_id = str(sibling_result["document_id"])
    sibling_meta = pipeline._source_repository.get_source_meta(
        "AAPL",
        sibling_document_id,
        SourceKind.FILING,
    )
    sibling_handle = pipeline._source_repository.get_source_handle(
        "AAPL",
        sibling_document_id,
        SourceKind.FILING,
    )
    sibling_files = pipeline._blob_repository.list_files(sibling_handle)
    company_meta = pipeline._company_repository.get_company_meta("AAPL")

    update_events = [
        event
        async for event in pipeline.upload_filing_stream(
            _validated_sec_filing_request(
                pipeline=pipeline,
                filing_file=new_file,
                action=None,
                company_name="Apple Inc.",
            )
        )
    ]
    update_result = update_events[-1].payload["result"]
    assert isinstance(update_result, dict)
    assert update_result["status"] == "ok"
    assert update_result["filing_action"] == "update"
    assert update_result["document_id"] == create_result["document_id"]

    handle = pipeline._source_repository.get_source_handle(
        "AAPL",
        str(update_result["document_id"]),
        SourceKind.FILING,
    )
    file_names = sorted(meta.uri.split("/")[-1] for meta in pipeline._blob_repository.list_files(handle))
    original_identity = _build_filing_original_asset_identity(new_file.resolve(strict=False))
    assert file_names == sorted((original_identity, f"{original_identity}_docling.json"))
    assert pipeline._company_repository.get_company_meta("AAPL") == company_meta
    assert (
        pipeline._source_repository.get_source_meta(
            "AAPL",
            sibling_document_id,
            SourceKind.FILING,
        )
        == sibling_meta
    )
    assert pipeline._blob_repository.list_files(sibling_handle) == sibling_files


@pytest.mark.asyncio
async def test_upload_filing_fresh_create_existing_fails_before_conversion_and_batch(
    tmp_path: Path,
) -> None:
    """SEC fresh recheck 必须让 stale create-existing 在 conversion 前 typed fail。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: stale action 被消费、converter/batch 被调用或 tree 漂移时抛出。
    """

    calls: list[str] = []
    pipeline, batching, company, source = _tracking_sec_pipeline(
        tmp_path,
        converter_calls=calls,
    )
    filing_file = tmp_path / "filing.pdf"
    filing_file.write_text("published filing", encoding="utf-8")
    stale_create = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=filing_file,
        action="create",
        company_name="Apple Inc.",
    )
    published_events = [
        event
        async for event in pipeline.upload_filing_stream(
            _validated_sec_filing_request(
                pipeline=pipeline,
                filing_file=filing_file,
                action=None,
                company_name="Apple Inc.",
            )
        )
    ]
    assert published_events[-1].event_type is UploadFilingEventType.UPLOAD_COMPLETED
    calls.clear()
    batching.begin_tokens.clear()
    batching.commit_tokens.clear()
    batching.rollback_tokens.clear()
    company.stage_tokens.clear()
    source.stage_tokens.clear()
    published_tree = published_tree_sha256(tmp_path, "AAPL")

    with pytest.raises(FinsUploadUsageError) as exc_info:
        _ = [event async for event in pipeline.upload_filing_stream(stale_create)]

    assert exc_info.value.failure.code is FinsUploadUsageCode.CREATE_TARGET_EXISTS
    assert calls == []
    assert batching.begin_tokens == []
    assert company.stage_tokens == []
    assert source.stage_tokens == []
    assert published_tree_sha256(tmp_path, "AAPL") == published_tree


@pytest.mark.parametrize("changed_input", (False, True))
@pytest.mark.asyncio
async def test_upload_filing_auto_after_delete_republishes_active_source(
    tmp_path: Path,
    changed_input: bool,
) -> None:
    """SEC delete 后 equal/changed 完整输入 auto 必须发布 uploaded/update active source。

    Args:
        tmp_path: pytest 临时目录。
        changed_input: logical delete 后是否改变完整输入内容。

    Returns:
        无。

    Raises:
        AssertionError: restore 被 skip 或 source 仍处于 logical deleted 时抛出。
    """

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        processor_registry=build_fins_processor_registry(),
        docling_converter=_FakeDoclingConverter(),
    )
    filing_file = tmp_path / "restore.pdf"
    filing_file.write_text("same filing", encoding="utf-8")
    create_request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=filing_file,
        action=None,
        company_name="Apple Inc.",
    )
    create_events = [event async for event in pipeline.upload_filing_stream(create_request)]
    create_result = create_events[-1].payload["result"]
    assert isinstance(create_result, dict)
    document_id = str(create_result["document_id"])
    delete_events = [
        event
        async for event in pipeline.upload_filing_stream(
            _validated_sec_filing_request(
                pipeline=pipeline,
                filing_file=filing_file,
                action="delete",
                company_name="Apple Inc.",
            )
        )
    ]
    assert delete_events[-1].event_type is UploadFilingEventType.UPLOAD_COMPLETED
    if changed_input:
        filing_file.write_text("changed filing", encoding="utf-8")

    restore_events = [
        event
        async for event in pipeline.upload_filing_stream(
            _validated_sec_filing_request(
                pipeline=pipeline,
                filing_file=filing_file,
                action=None,
                company_name="Apple Inc.",
            )
        )
    ]
    restore_result = restore_events[-1].payload["result"]
    state = pipeline._filing_upload_state_repository.read_filing_upload_state("AAPL", document_id)

    assert isinstance(restore_result, dict)
    assert restore_result["status"] == "ok"
    assert restore_result["filing_action"] == "update"
    assert state.source_meta is not None
    assert state.source_meta["is_deleted"] is False
    assert state.source_meta["deleted_at"] is None


@pytest.mark.parametrize("failure_point", ("company", "source"))
@pytest.mark.asyncio
async def test_upload_filing_stage_failure_rolls_back_one_batch_and_preserves_published_tree(
    tmp_path: Path,
    failure_point: str,
) -> None:
    """SEC company/source stage failure 必须回滚同一 batch 且 published SHA 不变。

    Args:
        tmp_path: 临时目录。
        failure_point: 注入 company 或 source stage failure。

    Returns:
        无。

    Raises:
        AssertionError: batch 计数、token identity 或 published tree 漂移时抛出。
    """

    pipeline, batching, company, source = _tracking_sec_pipeline(tmp_path)
    filing_file = tmp_path / "filing.pdf"
    filing_file.write_text("demo filing", encoding="utf-8")
    request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=filing_file,
        action="create",
        company_name="Apple Inc.",
    )
    company.fail_after_stage = failure_point == "company"
    source.fail_after_stage = failure_point == "source"
    before_tree = published_tree_sha256(tmp_path, "AAPL")

    events = [event async for event in pipeline.upload_filing_stream(request)]

    assert events[-1].event_type is UploadFilingEventType.UPLOAD_FAILED
    assert published_tree_sha256(tmp_path, "AAPL") == before_tree == {}
    assert len(batching.begin_tokens) == 1
    assert batching.commit_tokens == []
    assert batching.rollback_tokens == batching.begin_tokens
    assert company.stage_tokens == batching.begin_tokens
    if failure_point == "source":
        assert source.stage_tokens == batching.begin_tokens
    else:
        assert source.stage_tokens == []


@pytest.mark.asyncio
async def test_upload_filing_fresh_recheck_discards_stale_action_and_company_decision(
    tmp_path: Path,
) -> None:
    """SEC workflow 必须丢弃 preflight 后失效的 action/company decision。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: fresh recheck 未成为唯一 prepare/stage authority 时抛出。
    """

    pipeline, batching, company, source = _tracking_sec_pipeline(tmp_path)
    filing_file = tmp_path / "filing.pdf"
    filing_file.write_text("demo filing", encoding="utf-8")
    stale_preflight = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=filing_file,
        action=None,
        company_name="Stale Decision Name",
    )
    assert stale_preflight.resolved_action == "create"
    assert stale_preflight.company_meta_decision.disposition == "stage"
    published_request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=filing_file,
        action=None,
        company_name="Published Company Name",
    )
    published_events = [event async for event in pipeline.upload_filing_stream(published_request)]
    assert published_events[-1].event_type is UploadFilingEventType.UPLOAD_COMPLETED
    batching.begin_tokens.clear()
    batching.commit_tokens.clear()
    batching.rollback_tokens.clear()
    company.stage_tokens.clear()
    source.stage_tokens.clear()
    published_tree = published_tree_sha256(tmp_path, "AAPL")

    stale_events = [event async for event in pipeline.upload_filing_stream(stale_preflight)]

    stale_result = stale_events[-1].payload["result"]
    assert isinstance(stale_result, dict)
    assert stale_result["filing_action"] == "update"
    assert stale_result["status"] == "skipped"
    assert stale_result["stored_file_count"] == 0
    assert pipeline._company_repository.get_company_meta("AAPL").company_name == ("Published Company Name")
    assert len(batching.begin_tokens) == 1
    assert batching.commit_tokens == []
    assert batching.rollback_tokens == batching.begin_tokens
    assert company.stage_tokens == []
    assert source.stage_tokens == []
    assert published_tree_sha256(tmp_path, "AAPL") == published_tree


@pytest.mark.asyncio
async def test_upload_filing_consumes_fresh_authoritative_file_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEC workflow 必须原样消费 fresh validator 产生的 typed selection。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: fresh validator selection 注入夹具。

    Returns:
        无。

    Raises:
        AssertionError: workflow 从 raw files 重建 selection 时抛出。
    """

    calls: list[str] = []
    pipeline, _batching, _company, _source = _tracking_sec_pipeline(
        tmp_path,
        converter_calls=calls,
    )
    authoritative_file = tmp_path / "authoritative.docx"
    authoritative_file.write_bytes(b"authoritative")
    request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=authoritative_file,
        action="create",
        company_name="Apple Inc.",
    )
    owner_validator = fresh_validation_module.validate_fins_upload_filing_request
    validator_calls: list[FinsUploadFilingRequest] = []

    def authoritative_validator(
        raw_request: FinsUploadFilingRequest,
        *,
        published_state: FilingUploadPublishedState,
    ) -> ValidatedFinsUploadFilingRequest:
        """保留 fresh identity，仅替换 owner 产生的 typed selection。

        Args:
            raw_request: immutable raw request。
            published_state: fresh published snapshot。

        Returns:
            携带 authoritative file selection 的 validated request。

        Raises:
            FinsUploadUsageError: owner validator 拒绝请求时抛出。
        """

        validator_calls.append(raw_request)
        return owner_validator(raw_request, published_state=published_state)

    monkeypatch.setattr(
        fresh_validation_module,
        "validate_fins_upload_filing_request",
        authoritative_validator,
    )

    events = [event async for event in pipeline.upload_filing_stream(request)]
    result = events[-1].payload["result"]
    assert isinstance(result, dict)
    handle = pipeline._source_repository.get_source_handle(
        "AAPL",
        str(result["document_id"]),
        SourceKind.FILING,
    )
    stored_names = sorted(item.uri.rsplit("/", maxsplit=1)[-1] for item in pipeline._blob_repository.list_files(handle))

    assert validator_calls == [request.request]
    assert calls == ["authoritative.docx"]
    original_identity = _build_filing_original_asset_identity(authoritative_file.resolve(strict=False))
    assert stored_names == sorted((original_identity, f"{original_identity}_docling.json"))


@pytest.mark.asyncio
async def test_upload_filing_rollback_failure_logs_primary_and_recovery_evidence(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SEC rollback failure 必须保留 stage 主因与 recovery evidence 给 operator。

    Args:
        tmp_path: 临时目录。
        caplog: operator log 捕获夹具。

    Returns:
        无。

    Raises:
        AssertionError: 主因被 rollback failure 覆盖或 public reason 泄漏时抛出。
    """

    pipeline, batching, company, _source = _tracking_sec_pipeline(tmp_path)
    filing_file = tmp_path / "filing.pdf"
    filing_file.write_text("demo filing", encoding="utf-8")
    request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=filing_file,
        action="create",
        company_name="Apple Inc.",
    )
    company.fail_after_stage = True
    batching.fail_rollback = True

    with caplog.at_level("ERROR"):
        events = [event async for event in pipeline.upload_filing_stream(request)]

    failed_result = events[-1].payload["result"]
    assert isinstance(failed_result, dict)
    assert failed_result["stored_file_count"] == 0
    assert failed_result["message"] == "上传执行失败，请检查运行日志后重试"
    assert "injected company stage primary failure" not in str(failed_result)
    assert "injected rollback evidence failure" not in str(failed_result)
    assert "injected company stage primary failure" in caplog.text
    assert "injected rollback evidence failure" in caplog.text
    assert batching.commit_tokens == []
    assert batching.rollback_tokens == batching.begin_tokens
    assert published_tree_sha256(tmp_path, "AAPL") == {}


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code", "operator_marker"),
    (
        (DoclingConversionCancelledError(), "cancelled", None, None),
        (
            DoclingConversionError(
                DoclingConversionFailureKind.CONVERTER_EXECUTION,
                "Docling conversion execution failed",
                7,
            ),
            "failed",
            "docling_converter_execution",
            "typed content admission failed",
        ),
        (OSError("private storage cause"), "failed", "storage_io", "storage operation failed"),
        (
            RuntimeError("private runtime cause"),
            "failed",
            "unexpected_runtime",
            "runtime operation failed",
        ),
    ),
)
@pytest.mark.asyncio
async def test_upload_filing_observably_classifies_cancelled_docling_storage_and_generic(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    expected_status: str,
    expected_code: str | None,
    operator_marker: str | None,
) -> None:
    """SEC filing failure path 必须按 frozen typed priority 分类并保留 operator cause。

    Args:
        tmp_path: 临时目录。
        caplog: operator log 捕获夹具。
        error: converter 注入异常。
        expected_status: pipeline 预期终态。
        expected_code: failed 终态的 closed code；取消时为空。
        operator_marker: 对应 typed catch 的 operator marker；取消时为空。

    Returns:
        无。

    Raises:
        AssertionError: typed failure 落入错误分类或 public/internal cause 边界漂移时抛出。
    """

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        processor_registry=build_fins_processor_registry(),
        docling_converter=_FailingDoclingConverter(error),
    )
    filing_file = tmp_path / "filing.pdf"
    filing_file.write_text("demo filing", encoding="utf-8")
    request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=filing_file,
        action="create",
        company_name="Apple Inc.",
    )

    with caplog.at_level("ERROR"):
        events = [event async for event in pipeline.upload_filing_stream(request)]

    result = events[-1].payload["result"]
    assert isinstance(result, dict)
    assert result["status"] == expected_status
    assert result["stored_file_count"] == 0
    if expected_code is None:
        assert events[-1].event_type is UploadFilingEventType.UPLOAD_COMPLETED
        assert "failure" not in result
        assert operator_marker is None
        assert caplog.text == ""
    else:
        assert events[-1].event_type is UploadFilingEventType.UPLOAD_FAILED
        failure = result["failure"]
        assert isinstance(failure, dict)
        assert failure["code"] == expected_code
        assert operator_marker is not None
        assert operator_marker in caplog.text
        assert str(error) in caplog.text
        assert str(error) not in str(result)


@pytest.mark.asyncio
async def test_upload_filing_empty_fails_before_batch_with_typed_label(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SEC empty filing 必须在 converter/batch/company/source publication 前失败。

    Args:
        tmp_path: pytest 临时目录。
        caplog: operator log 捕获夹具。

    Returns:
        无。

    Raises:
        AssertionError: typed reason 或 zero-publication 原子性漂移时抛出。
    """

    calls: list[str] = []
    pipeline, batching, company, source = _tracking_sec_pipeline(tmp_path, converter_calls=calls)
    filing_file = tmp_path / "empty.pdf"
    filing_file.write_bytes(b"")
    request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=filing_file,
        action="create",
        company_name="Apple Inc.",
    )

    with caplog.at_level("ERROR"):
        events = [event async for event in pipeline.upload_filing_stream(request)]

    result = events[-1].payload["result"]
    assert isinstance(result, dict)
    failure = result["failure"]
    assert isinstance(failure, dict)
    assert result["status"] == "failed"
    assert result["stored_file_count"] == 0
    assert failure == {
        "kind": "content",
        "code": "empty_input_file",
        "message": "文件为空，无法上传",
        "retry_hint": "请提供非空文件后重试",
        "file_label": "empty.pdf",
    }
    assert "typed content admission failed" in caplog.text
    assert calls == []
    assert batching.begin_tokens == []
    assert batching.commit_tokens == []
    assert batching.rollback_tokens == []
    assert company.stage_tokens == []
    assert source.stage_tokens == []
    assert published_tree_sha256(tmp_path, "AAPL") == {}


@pytest.mark.asyncio
async def test_upload_filing_corrupt_primary_with_valid_companions_fails_atomically(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEC corrupt primary 必须只转换一次且整批不开始 publication。

    Args:
        tmp_path: pytest 临时目录。
        caplog: operator log 捕获夹具。
        monkeypatch: workflow generic mapper 禁用夹具。

    Returns:
        无。

    Raises:
        AssertionError: conversion 顺序、typed label 或原子 publication 漂移时抛出。
    """

    pipeline, batching, company, source = _tracking_sec_pipeline(tmp_path)

    def reject_workflow_reclassification(
        error: Exception,
        *,
        file_label: str | None,
    ) -> None:
        """若 typed exception 被 workflow 重新分类则立即失败。

        Args:
            error: 意外进入 generic mapper 的异常。
            file_label: 意外进入 generic mapper 的 label。

        Returns:
            不返回。

        Raises:
            AssertionError: 始终抛出。
        """

        del error, file_label
        raise AssertionError("typed filing failure 禁止 workflow 字符串重分类")

    monkeypatch.setattr(
        sec_upload_workflow,
        "fins_upload_failure_from_exception",
        reject_workflow_reclassification,
    )
    corrupt_file = tmp_path / "corrupt.pdf"
    companion_file = tmp_path / "companion.docx"
    later_file = tmp_path / "later.xlsx"
    for file_path in (corrupt_file, companion_file, later_file):
        file_path.write_bytes(b"filing input")
    calls: list[str] = []
    cause = DoclingConversionError(
        DoclingConversionFailureKind.CONVERTER_EXECUTION,
        "Docling conversion execution failed",
        23,
    )
    pipeline._upload_service._docling_converter = _FailingDoclingConverter(
        cause,
        failing_name=corrupt_file.name,
        calls=calls,
    )
    first_request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=corrupt_file,
        action="create",
        company_name="Apple Inc.",
    )
    request = fresh_validation_module.validate_fins_upload_filing_request(
        replace(
            first_request.request,
            files=(corrupt_file, companion_file, later_file),
            primary_selectors=(corrupt_file,),
        ),
        published_state=first_request.published_state,
    )

    with caplog.at_level("ERROR"):
        events = [event async for event in pipeline.upload_filing_stream(request)]

    result = events[-1].payload["result"]
    assert isinstance(result, dict)
    failure = result["failure"]
    assert isinstance(failure, dict)
    assert result["stored_file_count"] == 0
    assert failure["code"] == "docling_converter_execution"
    assert failure["file_label"] == "corrupt.pdf"
    assert calls == ["corrupt.pdf"]
    assert "typed content admission failed" in caplog.text
    assert str(cause) in caplog.text
    assert str(cause) not in str(result)
    assert batching.begin_tokens == []
    assert batching.commit_tokens == []
    assert batching.rollback_tokens == []
    assert company.stage_tokens == []
    assert source.stage_tokens == []
    assert published_tree_sha256(tmp_path, "AAPL") == {}


@pytest.mark.parametrize(
    ("commit_error", "expected_kind", "expected_code"),
    (
        (OSError("commit storage failure"), "storage", "storage_io"),
        (RuntimeError("commit runtime failure"), "runtime", "unexpected_runtime"),
    ),
)
@pytest.mark.asyncio
async def test_upload_filing_commit_failure_never_publishes_staged_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    commit_error: Exception,
    expected_kind: str,
    expected_code: str,
) -> None:
    """commit 失败时 staged original count 不得成为 terminal stored fact。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: commit failure 注入夹具。
        commit_error: ``commit_batch`` 应抛出的异常。
        expected_kind: 既有 failure kind。
        expected_code: 既有 failure code。

    Returns:
        无。

    Raises:
        AssertionError: terminal count、分类或 published tree 漂移时抛出。
    """

    pipeline, batching, _company, _source = _tracking_sec_pipeline(tmp_path)
    filing_file = tmp_path / "filing.pdf"
    filing_file.write_text("demo filing", encoding="utf-8")
    request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=filing_file,
        action="create",
        company_name="Apple Inc.",
    )
    before_tree = published_tree_sha256(tmp_path, "AAPL")

    def fail_commit(batch: BatchToken) -> None:
        """在 storage commit owner 入口注入指定异常。

        Args:
            batch: 当前 publication batch。

        Returns:
            不返回。

        Raises:
            Exception: 始终抛出测试参数提供的 commit 异常。
        """

        del batch
        raise commit_error

    monkeypatch.setattr(batching, "commit_batch", fail_commit)
    events = [event async for event in pipeline.upload_filing_stream(request)]

    result = events[-1].payload["result"]
    assert isinstance(result, dict)
    failure = result["failure"]
    assert isinstance(failure, dict)
    assert events[-1].event_type is UploadFilingEventType.UPLOAD_FAILED
    assert result["stored_file_count"] == 0
    assert failure["kind"] == expected_kind
    assert failure["code"] == expected_code
    assert published_tree_sha256(tmp_path, "AAPL") == before_tree == {}
    assert batching.rollback_tokens == []


@pytest.mark.asyncio
async def test_upload_filing_alias_conflict_projects_exact_typed_terminal(tmp_path: Path) -> None:
    """SEC filing alias conflict 必须原子拒绝并投影 exact failure JSON。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: conflict 类型、count 或 durable tree 漂移时抛出。
    """

    pipeline, batching, _company, _source = _tracking_sec_pipeline(tmp_path)
    existing = batching.begin_batch("MSFT")
    batching.commit_batch(existing)
    filing_file = tmp_path / "filing.pdf"
    filing_file.write_text("demo filing", encoding="utf-8")
    request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=filing_file,
        action="create",
        company_name="Apple Inc.",
        ticker_aliases=("MSFT",),
    )

    events = [event async for event in pipeline.upload_filing_stream(request)]

    result = events[-1].payload["result"]
    assert isinstance(result, dict)
    assert events[-1].event_type is UploadFilingEventType.UPLOAD_FAILED
    assert result["stored_file_count"] == 0
    assert result["failure"] == {
        "kind": "storage",
        "code": "ticker_alias_conflict",
        "message": "股票代码别名已属于当前工作区中的其他公司，请移除冲突别名后重试",
        "retry_hint": "请确认公司的主代码与别名声明后重新上传",
        "file_label": None,
    }
    assert not (tmp_path / "portfolio" / "AAPL").exists()


@pytest.mark.asyncio
async def test_upload_filing_authoritative_identity_mismatch_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEC fresh validator identity 漂移必须在 prepare/mutation 前失败关闭。

    Args:
        tmp_path: 临时目录。
        monkeypatch: authoritative validator 输出注入夹具。

    Returns:
        无。

    Raises:
        AssertionError: identity mismatch 未失败关闭或产生 published mutation 时抛出。
    """

    pipeline, batching, _company, _source = _tracking_sec_pipeline(tmp_path)
    filing_file = tmp_path / "filing.pdf"
    filing_file.write_text("demo filing", encoding="utf-8")
    request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=filing_file,
        action="create",
        company_name="Apple Inc.",
    )
    owner_validator = fresh_validation_module.validate_fins_upload_filing_request

    def mismatched_validator(
        raw_request: FinsUploadFilingRequest,
        *,
        published_state: FilingUploadPublishedState,
    ) -> ValidatedFinsUploadFilingRequest:
        """返回仅 internal document identity 漂移的 validator 结果。

        Args:
            raw_request: immutable raw filing request。
            published_state: workflow fresh snapshot。

        Returns:
            internal document ID 被注入漂移的 validated request。

        Raises:
            FinsUploadUsageError: owner validator 拒绝请求时抛出。
        """

        validated = owner_validator(raw_request, published_state=published_state)
        return replace(
            validated,
            internal_document_id=f"{validated.internal_document_id}-mismatch",
        )

    monkeypatch.setattr(
        fresh_validation_module,
        "validate_fins_upload_filing_request",
        mismatched_validator,
    )

    with pytest.raises(RuntimeError, match="filing authoritative identity mismatch"):
        _ = [event async for event in pipeline.upload_filing_stream(request)]

    assert batching.begin_tokens == []
    assert published_tree_sha256(tmp_path, "AAPL") == {}


@pytest.mark.parametrize(
    "corruption",
    (
        "original_missing",
        "original_digest",
        "docling_missing",
        "meta_digest",
        "manifest_missing",
    ),
)
@pytest.mark.asyncio
async def test_upload_filing_repairs_real_filesystem_and_atomically_publishes_company_source(
    tmp_path: Path,
    corruption: str,
) -> None:
    """SEC auto repair 必须原子发布完整新 source 与同批 company decision。

    Args:
        tmp_path: 临时 workspace。
        corruption: original、Docling、meta 或 manifest repair case。

    Returns:
        无。

    Raises:
        AssertionError: fresh disposition、原子 publication 或新 snapshot 漂移时抛出。
        OSError: 真实 filesystem fixture 读写失败时抛出。
        ValueError: persisted source contract 非法时抛出。
    """

    calls: list[str] = []
    pipeline, batching, company, source = _tracking_sec_pipeline(
        tmp_path,
        converter_calls=calls,
    )
    primary = tmp_path / "repair-primary.pdf"
    companion = tmp_path / "repair-companion.xlsx"
    primary.write_bytes(b"authoritative-primary")
    companion.write_bytes(b"authoritative-companion")
    create_request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=primary,
        companion_files=(companion,),
        action="create",
        company_name="Apple Original",
    )
    create_events = [event async for event in pipeline.upload_filing_stream(create_request)]
    create_result = create_events[-1].payload["result"]
    assert isinstance(create_result, dict)
    document_id = str(create_result["document_id"])
    old_integrity = source.classify_source_integrity("AAPL", document_id, SourceKind.FILING)
    assert old_integrity.status is SourceIntegrityStatus.COMPLETE
    _seed_sec_upload_company_meta(
        pipeline=pipeline,
        company_name="Apple Stale",
        resolver_version="market_resolver_v0.9.0",
        ticker_aliases=[],
    )
    batching.begin_tokens.clear()
    batching.commit_tokens.clear()
    batching.rollback_tokens.clear()
    company.stage_tokens.clear()
    source.stage_tokens.clear()
    _corrupt_published_filing_for_repair(
        pipeline=pipeline,
        document_id=document_id,
        corruption=corruption,
    )
    repair_request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=primary,
        companion_files=(companion,),
        action=None,
        company_name="Apple Repaired",
    )
    assert repair_request.published_state.source_integrity.status is (SourceIntegrityStatus.REPAIR_REQUIRED)

    events = [event async for event in pipeline.upload_filing_stream(repair_request)]

    result = events[-1].payload["result"]
    assert isinstance(result, dict)
    assert events[-1].event_type is UploadFilingEventType.UPLOAD_COMPLETED
    assert result["status"] == "ok"
    assert result["filing_action"] == "update"
    assert result["stored_file_count"] == len(repair_request.request.files) == 2
    assert result["files"] == [str(primary), str(companion)]
    repaired = source.classify_source_integrity("AAPL", document_id, SourceKind.FILING)
    assert repaired.status is SourceIntegrityStatus.COMPLETE
    assert repaired.revision is not None
    assert repaired.revision != old_integrity.revision
    repaired_meta = source.get_source_meta("AAPL", document_id, SourceKind.FILING)
    raw_files = repaired_meta.get("files")
    assert isinstance(raw_files, list)
    assert sum(isinstance(item, dict) and item.get("source") == "original" for item in raw_files) == 2
    assert sum(isinstance(item, dict) and item.get("source") == "docling" for item in raw_files) == 1
    primary_document = repaired_meta.get("primary_document")
    assert isinstance(primary_document, str)
    locator = source.get_source_document_locator("AAPL", document_id, SourceKind.FILING)
    source_dir = tmp_path / locator
    declared_names: set[str] = set()
    for raw_file in raw_files:
        assert isinstance(raw_file, dict)
        name = raw_file.get("name")
        size = raw_file.get("size")
        digest = raw_file.get("sha256")
        assert isinstance(name, str)
        assert isinstance(size, int) and not isinstance(size, bool)
        assert isinstance(digest, str)
        payload = (source_dir / name).read_bytes()
        assert len(payload) == size
        assert hashlib.sha256(payload).hexdigest() == digest
        declared_names.add(name)
    assert primary_document in declared_names
    assert (source_dir.parent / "filing_manifest.json").is_file()
    with source.read_source_snapshot(
        "AAPL",
        document_id,
        SourceKind.FILING,
        materialize_files=True,
    ) as snapshot:
        assert snapshot.revision == repaired.revision
        assert snapshot.primary_filename == primary_document
        with snapshot.get_primary_source().open() as stream:
            assert stream.read() == (b'{"name": "repair-primary.pdf", "format": "docling"}')
    assert calls == [primary.name, primary.name]
    assert len(batching.begin_tokens) == 1
    assert batching.commit_tokens == batching.begin_tokens
    assert batching.rollback_tokens == []
    assert company.stage_tokens == batching.begin_tokens
    assert source.stage_tokens == batching.begin_tokens
    assert pipeline._company_repository.get_company_meta("AAPL").company_name == "Apple Repaired"


@pytest.mark.parametrize(
    ("read_error", "expected_message"),
    (
        (FileNotFoundError("private published path"), "上传状态读取失败，请检查工作区存储状态"),
        (RuntimeFileLockError("private lock detail"), "上传状态读取失败，请检查工作区存储状态"),
        (ValueError("private structural detail"), "上传状态已损坏，请检查工作区存储状态"),
    ),
)
@pytest.mark.asyncio
async def test_upload_filing_fresh_read_failures_use_prevalidation_failure_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    read_error: Exception,
    expected_message: str,
) -> None:
    """SEC fresh state path-free failures 必须投影唯一 typed failed event。

    Args:
        tmp_path: 临时 workspace。
        monkeypatch: fresh state failure 注入夹具。
        read_error: fresh repository read 抛出的异常。
        expected_message: upload-failure owner 的固定 public message。

    Returns:
        无。

    Raises:
        AssertionError: raw exception、generic runtime 或 mutation 泄漏时抛出。
    """

    converter_calls: list[str] = []
    pipeline, batching, company, source = _tracking_sec_pipeline(
        tmp_path,
        converter_calls=converter_calls,
    )
    filing_file = tmp_path / "fresh-read.pdf"
    filing_file.write_bytes(b"fresh read")
    request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=filing_file,
        action="create",
        company_name="Apple Inc.",
    )

    def fail_fresh_read(ticker: str, document_id: str) -> FilingUploadPublishedState:
        """在 workflow fresh read boundary 抛出指定 path-free failure。

        Args:
            ticker: canonical ticker。
            document_id: exact filing document ID。

        Returns:
            不返回。

        Raises:
            Exception: 始终抛出参数化异常。
        """

        del ticker, document_id
        raise read_error

    monkeypatch.setattr(
        pipeline._filing_upload_state_repository,
        "read_filing_upload_state",
        fail_fresh_read,
    )
    events = [event async for event in pipeline.upload_filing_stream(request)]

    assert [event.event_type for event in events] == [UploadFilingEventType.UPLOAD_FAILED]
    result = events[0].payload["result"]
    assert isinstance(result, dict)
    failure = result["failure"]
    assert isinstance(failure, dict)
    assert failure["kind"] == "storage"
    assert failure["code"] == "storage_io"
    assert failure["message"] == expected_message
    assert str(read_error) not in str(result)
    assert converter_calls == []
    assert batching.begin_tokens == []
    assert company.stage_tokens == []
    assert source.stage_tokens == []
    assert published_tree_sha256(tmp_path, "AAPL") == {}


@pytest.mark.parametrize("with_companion", [False, True])
def test_concurrent_identical_auto_upload_has_one_publish_and_one_canonical_skip(
    tmp_path: Path,
    with_companion: bool,
) -> None:
    """同 ticker 同 filing 的真实线程竞争只允许一个 publish。

    Args:
        tmp_path: 真实 filesystem workspace。
        with_companion: 是否覆盖多文件 authoritative set。

    Returns:
        无。

    Raises:
        AssertionError: winner/loser 终态、mutation 次数或 durable state 漂移时抛出。
    """

    barrier = ThreadBarrier(2)
    prepared_identities: list[FilingUploadPublicationIdentity] = []
    pipeline, batching, company, source = _tracking_sec_pipeline(
        tmp_path,
        converter=_BarrierDoclingConverter(barrier),
        prepared_identities=prepared_identities,
    )
    primary = tmp_path / "q1.pdf"
    companion = tmp_path / "q1.xlsx"
    primary.write_bytes(b"same-primary")
    companion.write_bytes(b"same-companion")
    companions = (companion,) if with_companion else ()
    first_request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=primary,
        companion_files=companions,
        action=None,
        company_name="Apple Inc.",
    )
    second_request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=primary,
        companion_files=companions,
        action=None,
        company_name="Apple Inc.",
    )

    streams = _run_two_sec_upload_streams(
        first_pipeline=pipeline,
        first_request=first_request,
        second_pipeline=pipeline,
        second_request=second_request,
    )
    results = tuple(_sec_upload_stream_result(events) for events in streams)

    assert sorted(str(result["status"]) for result in results) == ["ok", "skipped"]
    first_count = results[0]["stored_file_count"]
    second_count = results[1]["stored_file_count"]
    assert isinstance(first_count, int)
    assert isinstance(second_count, int)
    assert sorted((first_count, second_count)) == [0, 1 + len(companions)]
    assert len(batching.begin_tokens) == 2
    assert len(batching.commit_tokens) == 1
    assert len(batching.rollback_tokens) == 1
    assert company.stage_tokens == batching.commit_tokens
    assert source.stage_tokens == batching.commit_tokens
    durable = pipeline._filing_upload_state_repository.read_filing_upload_state(
        "AAPL",
        first_request.document_id,
    )
    assert durable.source_integrity.status is SourceIntegrityStatus.COMPLETE
    assert len(prepared_identities) == 2
    assert prepared_identities[0] == prepared_identities[1]
    prepared_identity = prepared_identities[0]
    assert durable.publication_identity == prepared_identity
    assert durable.source_meta is not None

    loser_index = next(index for index, result in enumerate(results) if result["status"] == "skipped")
    loser_events = streams[loser_index]
    assert [event.event_type for event in loser_events] == [
        UploadFilingEventType.UPLOAD_STARTED,
        *(UploadFilingEventType.FILE_SKIPPED for _path in (primary, *companions)),
        UploadFilingEventType.UPLOAD_COMPLETED,
    ]
    assert [
        event.payload["name"] for event in loser_events if event.event_type is UploadFilingEventType.FILE_SKIPPED
    ] == [path.name for path in (primary, *companions)]
    assert all(event.event_type is not UploadFilingEventType.CONVERSION_STARTED for event in loser_events)

    with source.read_source_snapshot(
        "AAPL",
        first_request.document_id,
        SourceKind.FILING,
        materialize_files=False,
    ) as snapshot:
        assert snapshot.revision == durable.source_integrity.revision
        assert snapshot.source_meta == durable.source_meta
        assert snapshot.primary_filename == prepared_identity.primary_document
        snapshot_asset_names = tuple(file.name for file in snapshot.files)
        assert len(snapshot_asset_names) == len(prepared_identity.assets)
        assert frozenset(snapshot_asset_names) == frozenset(asset.name for asset in prepared_identity.assets)


@pytest.mark.parametrize(
    ("overwrite", "expected_statuses", "expected_commits", "expected_rollbacks"),
    [
        (False, ["failed", "ok"], 1, 1),
        (True, ["ok", "ok"], 2, 0),
    ],
)
def test_concurrent_explicit_create_obeys_overwrite_rebase_contract(
    tmp_path: Path,
    overwrite: bool,
    expected_statuses: list[str],
    expected_commits: int,
    expected_rollbacks: int,
) -> None:
    """显式 create 竞争分别产生 no-overwrite conflict 或 overwrite rebase。

    Args:
        tmp_path: 真实 filesystem workspace。
        overwrite: 显式 create overwrite 开关。
        expected_statuses: 两个终态的稳定排序。
        expected_commits: 预期 commit 数。
        expected_rollbacks: 预期 rollback 数。

    Returns:
        无。

    Raises:
        AssertionError: 显式 create 的 fresh arbitration 漂移时抛出。
    """

    commit_snapshots: list[_SourceCommitSnapshot] = []
    pipeline, batching, _company, _source = _tracking_sec_pipeline(
        tmp_path,
        converter=_BarrierDoclingConverter(ThreadBarrier(2)),
        commit_snapshots=commit_snapshots if overwrite else None,
    )
    primary = tmp_path / "q1.pdf"
    primary.write_bytes(b"same-primary")
    requests = tuple(
        _validated_sec_filing_request(
            pipeline=pipeline,
            filing_file=primary,
            action="create",
            company_name="Apple Inc.",
            overwrite=overwrite,
        )
        for _index in range(2)
    )

    results = _run_two_sec_uploads(
        first_pipeline=pipeline,
        first_request=requests[0],
        second_pipeline=pipeline,
        second_request=requests[1],
    )

    assert sorted(str(result["status"]) for result in results) == expected_statuses
    assert len(batching.commit_tokens) == expected_commits
    assert len(batching.rollback_tokens) == expected_rollbacks
    if overwrite is False:
        failed = next(result for result in results if result["status"] == "failed")
        failure = failed["failure"]
        assert isinstance(failure, dict)
        assert failure == fins_upload_source_publication_conflict_failure().to_json()
        assert failed["requested_action"] == "create"
        assert failed["resolved_action"] == "create"
        assert failed["filing_action"] == "create"
        assert failed["stored_file_count"] == 0
        assert failed["status"] != "skipped"
        assert failure["code"] != "unexpected_runtime"
    else:
        assert len(commit_snapshots) == 2
        first_commit, second_commit = commit_snapshots
        assert first_commit.document_id == requests[0].document_id
        assert second_commit.document_id == requests[0].document_id
        for timestamp_field in ("first_ingested_at", "created_at"):
            assert second_commit.source_meta[timestamp_field] == (first_commit.source_meta[timestamp_field])
        assert second_commit.source_meta["source_fingerprint"] == (first_commit.source_meta["source_fingerprint"])
        assert second_commit.source_meta["document_version"] == (first_commit.source_meta["document_version"])
        assert second_commit.source_meta["document_version"] == "v1"
        assert second_commit.revision != first_commit.revision


@pytest.mark.parametrize("mismatch", ["derived", "company"])
def test_concurrent_auto_rejects_nonidentical_candidate_or_company_intent(
    tmp_path: Path,
    mismatch: str,
) -> None:
    """auto loser 仅在 candidate 与 company 都 exact equal 时允许 skip。

    Args:
        tmp_path: 真实 filesystem workspace。
        mismatch: 派生资产或 company intent 不一致。

    Returns:
        无。

    Raises:
        AssertionError: 非 identical loser 被错误跳过或覆盖时抛出。
    """

    barrier = ThreadBarrier(2)
    first_pipeline, _first_batching, _first_company, _first_source = _tracking_sec_pipeline(
        tmp_path,
        converter=_BarrierDoclingConverter(barrier, marker="first"),
    )
    second_marker = "second" if mismatch == "derived" else "first"
    second_pipeline, _second_batching, _second_company, _second_source = _tracking_sec_pipeline(
        tmp_path,
        converter=_BarrierDoclingConverter(barrier, marker=second_marker),
    )
    primary = tmp_path / "q1.pdf"
    primary.write_bytes(b"same-primary")
    first_request = _validated_sec_filing_request(
        pipeline=first_pipeline,
        filing_file=primary,
        action=None,
        company_name="Apple First",
        ticker_aliases=("MSFT",) if mismatch == "company" else (),
    )
    second_request = _validated_sec_filing_request(
        pipeline=second_pipeline,
        filing_file=primary,
        action=None,
        company_name="Apple First",
        ticker_aliases=("GOOG",) if mismatch == "company" else (),
    )

    results = _run_two_sec_uploads(
        first_pipeline=first_pipeline,
        first_request=first_request,
        second_pipeline=second_pipeline,
        second_request=second_request,
    )

    assert sorted(str(result["status"]) for result in results) == ["failed", "ok"]
    failed = next(result for result in results if result["status"] == "failed")
    failure = failed["failure"]
    assert isinstance(failure, dict)
    assert failure["code"] == "source_publication_conflict"


@pytest.mark.parametrize("same_ticker", [True, False])
def test_concurrent_distinct_targets_preserve_exact_union(
    tmp_path: Path,
    same_ticker: bool,
) -> None:
    """不同 filing 或不同 ticker 的竞争均保留两个独立 durable target。

    Args:
        tmp_path: 真实 filesystem workspace。
        same_ticker: 为真时使用同 ticker 不同 fiscal period。

    Returns:
        无。

    Raises:
        AssertionError: per-target union 丢失或错误冲突时抛出。
    """

    batch_read_events = None if same_ticker else {"AAPL": Event(), "MSFT": Event()}
    pipeline, batching, company, source = _tracking_sec_pipeline(
        tmp_path,
        converter=_BarrierDoclingConverter(ThreadBarrier(2)),
        batch_read_barrier=None if same_ticker else ThreadBarrier(2),
        batch_read_events=batch_read_events,
    )
    first_file = tmp_path / "first.pdf"
    second_file = tmp_path / "second.pdf"
    first_file.write_bytes(b"first")
    second_file.write_bytes(b"second")
    first_request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=first_file,
        action=None,
        company_name="Apple Inc.",
        fiscal_period="Q1",
        ticker="AAPL",
        ticker_aliases=("MSFT",) if same_ticker else (),
    )
    second_ticker = "AAPL" if same_ticker else "MSFT"
    second_request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=second_file,
        action=None,
        company_name="Apple Inc." if same_ticker else "Microsoft Corp.",
        fiscal_period="Q2" if same_ticker else "Q1",
        ticker=second_ticker,
        ticker_aliases=("GOOG",) if same_ticker else (),
    )

    results = _run_two_sec_uploads(
        first_pipeline=pipeline,
        first_request=first_request,
        second_pipeline=pipeline,
        second_request=second_request,
    )

    assert [result["status"] for result in results] == ["ok", "ok"]
    assert len(batching.commit_tokens) == 2
    first_state = pipeline._filing_upload_state_repository.read_filing_upload_state(
        "AAPL",
        first_request.document_id,
    )
    second_state = pipeline._filing_upload_state_repository.read_filing_upload_state(
        second_ticker,
        second_request.document_id,
    )
    assert first_state.source_integrity.status is SourceIntegrityStatus.COMPLETE
    assert second_state.source_integrity.status is SourceIntegrityStatus.COMPLETE
    if same_ticker:
        company_meta = company.get_company_meta("AAPL")
        aliases = company_meta.ticker_identity.accepted_aliases
        assert len(aliases) == 2
        assert frozenset(aliases) == frozenset({"MSFT", "GOOG"})
        expected_document_ids = tuple(sorted((first_request.document_id, second_request.document_id)))
        assert tuple(source.list_source_document_ids("AAPL", SourceKind.FILING)) == (expected_document_ids)
        states = (first_state, second_state)
        publication_identities = tuple(state.publication_identity for state in states)
        assert all(identity is not None for identity in publication_identities)
        expected_asset_union = {
            (identity.document_id, asset.name)
            for identity in publication_identities
            if identity is not None
            for asset in identity.assets
        }
        actual_asset_union: set[tuple[str, str]] = set()
        for document_id, state in zip(
            (first_request.document_id, second_request.document_id),
            states,
            strict=True,
        ):
            identity = state.publication_identity
            assert identity is not None
            with source.read_source_snapshot(
                "AAPL",
                document_id,
                SourceKind.FILING,
                materialize_files=False,
            ) as snapshot:
                assert snapshot.document_id == document_id
                assert snapshot.revision == state.source_integrity.revision
                assert snapshot.primary_filename == identity.primary_document
                snapshot_asset_names = tuple(file.name for file in snapshot.files)
                assert len(snapshot_asset_names) == len(identity.assets)
                assert frozenset(snapshot_asset_names) == frozenset(asset.name for asset in identity.assets)
                actual_asset_union.update((document_id, asset_name) for asset_name in snapshot_asset_names)
        assert actual_asset_union == expected_asset_union
    else:
        assert batch_read_events is not None
        assert all(entered.is_set() for entered in batch_read_events.values())


@pytest.mark.asyncio
async def test_explicit_update_identical_stable_retransmission_is_canonical_skip(
    tmp_path: Path,
) -> None:
    """explicit update 的 stable identical 重传保持 revision/version/tree 不变。

    Args:
        tmp_path: 真实 filesystem workspace。

    Returns:
        无。

    Raises:
        AssertionError: explicit update 被发布、改版或泄露 conversion event 时抛出。
    """

    converter_calls: list[str] = []
    pipeline, batching, company, source = _tracking_sec_pipeline(
        tmp_path,
        converter_calls=converter_calls,
    )
    primary = tmp_path / "q1.pdf"
    primary.write_bytes(b"explicit-update-stable")
    create_request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=primary,
        action=None,
        company_name="Apple Inc.",
    )
    create_events = [event async for event in pipeline.upload_filing_stream(create_request)]
    created = create_events[-1].payload["result"]
    assert isinstance(created, dict)
    assert created["status"] == "ok"
    initial_state = pipeline._filing_upload_state_repository.read_filing_upload_state(
        "AAPL",
        str(created["document_id"]),
    )
    initial_tree = published_tree_sha256(tmp_path, "AAPL")
    batching.begin_tokens.clear()
    batching.commit_tokens.clear()
    batching.rollback_tokens.clear()
    company.stage_tokens.clear()
    source.stage_tokens.clear()
    converter_calls.clear()
    request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=primary,
        action="update",
        company_name="Apple Inc.",
    )

    events = [event async for event in pipeline.upload_filing_stream(request)]

    result = events[-1].payload["result"]
    assert isinstance(result, dict)
    assert result["status"] == "skipped"
    assert result["requested_action"] == "update"
    assert result["resolved_action"] == "update"
    assert result["filing_action"] == "update"
    assert result["stored_file_count"] == 0
    assert [event.event_type for event in events] == [
        UploadFilingEventType.UPLOAD_STARTED,
        UploadFilingEventType.FILE_SKIPPED,
        UploadFilingEventType.UPLOAD_COMPLETED,
    ]
    assert converter_calls == [primary.name]
    final_state = pipeline._filing_upload_state_repository.read_filing_upload_state(
        "AAPL",
        request.document_id,
    )
    assert final_state.source_integrity.revision == initial_state.source_integrity.revision
    assert final_state.source_meta == initial_state.source_meta
    assert published_tree_sha256(tmp_path, "AAPL") == initial_tree
    assert len(batching.begin_tokens) == 1
    assert batching.commit_tokens == []
    assert batching.rollback_tokens == batching.begin_tokens
    assert company.stage_tokens == []
    assert source.stage_tokens == []


def test_concurrent_explicit_updates_conflict_after_source_observation_changes(
    tmp_path: Path,
) -> None:
    """两个 explicit update 中后 writer 看到 revision 变化必须 typed conflict。

    Args:
        tmp_path: 真实 filesystem workspace。

    Returns:
        无。

    Raises:
        AssertionError: changed observation 被近似 skip、fallback publish 或丢失 action 时抛出。
    """

    seed_pipeline = SecPipeline(
        workspace_root=tmp_path,
        processor_registry=build_fins_processor_registry(),
        docling_converter=_FakeDoclingConverter(),
    )
    seed_file = tmp_path / "seed.pdf"
    seed_file.write_bytes(b"seed")
    seeded = seed_pipeline.upload_filing(
        _validated_sec_filing_request(
            pipeline=seed_pipeline,
            filing_file=seed_file,
            action=None,
            company_name="Apple Inc.",
        )
    )
    assert seeded["status"] == "ok"
    pipeline, batching, _company, _source = _tracking_sec_pipeline(
        tmp_path,
        converter=_BarrierDoclingConverter(ThreadBarrier(2)),
    )
    first_file = tmp_path / "update-a.pdf"
    second_file = tmp_path / "update-b.pdf"
    first_file.write_bytes(b"update-a")
    second_file.write_bytes(b"update-b")
    first_request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=first_file,
        action="update",
        company_name="Apple Inc.",
    )
    second_request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=second_file,
        action="update",
        company_name="Apple Inc.",
    )

    results = _run_two_sec_uploads(
        first_pipeline=pipeline,
        first_request=first_request,
        second_pipeline=pipeline,
        second_request=second_request,
    )

    assert sorted(str(result["status"]) for result in results) == ["failed", "ok"]
    failed = next(result for result in results if result["status"] == "failed")
    failure = failed["failure"]
    assert isinstance(failure, dict)
    assert failure["code"] == "source_publication_conflict"
    assert failed["requested_action"] == "update"
    assert failed["resolved_action"] == "update"
    assert failed["filing_action"] == "update"
    assert failed["stored_file_count"] == 0
    assert len(batching.commit_tokens) == 1
    assert len(batching.rollback_tokens) == 1


@pytest.mark.parametrize("cancel_at_observation", [5, 6])
def test_shared_publication_cancellation_checkpoints_rollback_without_mutation(
    tmp_path: Path,
    cancel_at_observation: int,
) -> None:
    """shared owner 的 begin 后与 fresh arbitration 后 checkpoint 都原子回滚。

    Args:
        tmp_path: 真实 filesystem workspace。
        cancel_at_observation: 覆盖第一或第二 publication checkpoint 的观察序号。

    Returns:
        无。

    Raises:
        AssertionError: 取消终态、rollback 次数或 durable tree 漂移时抛出。
    """

    pipeline, batching, company, source = _tracking_sec_pipeline(tmp_path)
    primary = tmp_path / "q1.pdf"
    primary.write_bytes(b"cancel-candidate")
    request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=primary,
        action=None,
        company_name="Apple Inc.",
    )
    token = _CheckpointCancellationToken(cancel_at_observation)

    result = pipeline.upload_filing(request, cancellation_checker=token)

    assert result["status"] == "cancelled"
    assert result["stored_file_count"] == 0
    assert len(batching.begin_tokens) == 1
    assert batching.commit_tokens == []
    assert batching.rollback_tokens == batching.begin_tokens
    assert company.stage_tokens == []
    assert source.stage_tokens == []
    assert published_tree_sha256(tmp_path, "AAPL") == {}


def test_shared_publication_cancel_rollback_failure_is_typed_storage_terminal(
    tmp_path: Path,
) -> None:
    """取消 rollback 失败必须产生 path-free storage_io，而非假 cancelled。

    Args:
        tmp_path: 真实 filesystem workspace。

    Returns:
        无。

    Raises:
        AssertionError: rollback failure 分类、证据或 mutation 边界漂移时抛出。
    """

    pipeline, batching, company, source = _tracking_sec_pipeline(tmp_path)
    batching.fail_rollback = True
    primary = tmp_path / "q1.pdf"
    primary.write_bytes(b"cancel-rollback-failure")
    request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=primary,
        action=None,
        company_name="Apple Inc.",
    )

    result = pipeline.upload_filing(
        request,
        cancellation_checker=_CheckpointCancellationToken(5),
    )

    assert result["status"] == "failed"
    assert result["stored_file_count"] == 0
    failure = result["failure"]
    assert isinstance(failure, dict)
    assert failure["code"] == "storage_io"
    assert len(batching.begin_tokens) == 1
    assert batching.commit_tokens == []
    assert batching.rollback_tokens == batching.begin_tokens
    assert company.stage_tokens == []
    assert source.stage_tokens == []


def test_spawn_process_identical_auto_has_one_publish_and_one_skip(tmp_path: Path) -> None:
    """spawn 进程竞争也由 filesystem per-ticker writer 线性化。

    Args:
        tmp_path: 父子进程共享的真实 filesystem workspace。

    Returns:
        无。

    Raises:
        AssertionError: 子进程退出、终态或 durable state 漂移时抛出。
        queue.Empty: 任一子进程未返回闭合结果时抛出。
    """

    # 父进程先完成 workspace 初始化，避免把目录创建竞争混入 publication 断言。
    observer = SecPipeline(
        workspace_root=tmp_path,
        processor_registry=build_fins_processor_registry(),
        docling_converter=_FakeDoclingConverter(),
    )
    primary = tmp_path / "spawn-q1.pdf"
    primary.write_bytes(b"spawn-identical")
    observed_request = _validated_sec_filing_request(
        pipeline=observer,
        filing_file=primary,
        action=None,
        company_name="Apple Inc.",
    )
    context = multiprocessing.get_context("spawn")
    barrier = cast(_BarrierPort, context.Barrier(2))
    result_queue = cast(_SpawnResultQueue, context.Queue(maxsize=2))
    processes = tuple(
        context.Process(
            target=_spawn_identical_sec_upload_worker,
            args=(str(tmp_path), str(primary), barrier, result_queue),
        )
        for _index in range(2)
    )

    try:
        for process in processes:
            process.start()
        results = (result_queue.get(timeout=30), result_queue.get(timeout=30))
        for process in processes:
            process.join(timeout=30)
        assert [process.exitcode for process in processes] == [0, 0]
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=10)

    assert sorted(results) == [("ok", 1), ("skipped", 0)]
    durable = observer._filing_upload_state_repository.read_filing_upload_state(
        "AAPL",
        observed_request.document_id,
    )
    assert durable.source_integrity.status is SourceIntegrityStatus.COMPLETE
