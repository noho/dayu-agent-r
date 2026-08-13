"""Fins 工具与 ingestion 运行时装配。

本模块承载 Fins 共享 assembly root：read tools 使用的仓储、处理器注册表、
``FinsReadRuntime``，以及下载/预处理 ingestion runtime foundation。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING

from dayu.documents.processors.processor_registry import ProcessorRegistry
from dayu.fins.ingestion_runtime import (
    FinsIngestionRuntime,
    FinsJobCancellationChecker,
    FinsUploadFilingRequest,
    FinsUploadMaterialRequest,
    FinsUploadPipelineResult,
    FinsUploadRequest,
    FinsUploadResultSummary,
    FinsUploadRunner,
    FsFinsIngestionJobStore,
    ValidatedFinsUploadFilingRequest,
    _filing_upload_request_identity,
    validate_fins_upload_filing_request,
)
from dayu.fins.processors.registry import build_fins_processor_registry
from dayu.fins.storage import (
    BatchingRepositoryProtocol,
    CompanyMetaRepositoryProtocol,
    DocumentBlobRepositoryProtocol,
    FilingMaintenanceRepositoryProtocol,
    FilingUploadStateRepositoryProtocol,
    FsBatchingRepository,
    FsCompanyMetaRepository,
    FsDocumentBlobRepository,
    FsFilingMaintenanceRepository,
    FsFilingUploadStateRepository,
    FsProcessedDocumentRepository,
    FsSourceDocumentRepository,
    ProcessedDocumentRepositoryProtocol,
    SourceDocumentRepositoryProtocol,
)
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from dayu.fins.ticker_normalization import normalize_ticker
from dayu.fins.upload_failure import (
    FinsUploadPrevalidationError,
    fins_upload_prevalidation_corruption_failure,
    fins_upload_prevalidation_io_failure,
)
from dayu.runtime.filelock import RuntimeFileLockError

if TYPE_CHECKING:
    from dayu.fins.pipelines.cn_pipeline import CnPipeline
    from dayu.fins.pipelines.sec_pipeline import SecPipeline
    from dayu.fins.tools.read_runtime import FinsReadRuntime


def prevalidate_fins_upload_filing_request_for_workspace(
    request: FinsUploadFilingRequest,
    *,
    workspace_root: Path,
) -> ValidatedFinsUploadFilingRequest:
    """在 production runtime bootstrap 前验证 filing upload request。

    Args:
        request: CLI 或其它入口构造的 raw filing request。
        workspace_root: Fins 工作区根目录。

    Returns:
        同一 storage snapshot 与 pure validator 产生的 validated request。

    Raises:
        FinsUploadUsageError: 请求违反调用方可修正契约时抛出。
        FinsUploadPrevalidationError: published state 损坏或读取失败时抛出。
    """

    ticker, document_id = _filing_upload_request_identity(request)
    try:
        repository = FsFilingUploadStateRepository(
            workspace_root,
            create_directories=False,
        )
        published_state = repository.read_filing_upload_state(ticker, document_id)
    except (OSError, RuntimeFileLockError) as exc:
        raise FinsUploadPrevalidationError(fins_upload_prevalidation_io_failure()) from exc
    except ValueError as exc:
        raise FinsUploadPrevalidationError(fins_upload_prevalidation_corruption_failure()) from exc
    return validate_fins_upload_filing_request(
        request,
        published_state=published_state,
    )


@dataclass(frozen=True)
class ProductionFinsUploadRunner(FinsUploadRunner):
    """production Fins upload runner。

    该 runner 只负责 runtime upload request 到 SEC/CN pipeline upload facade
    的业务 handoff 与结果摘要收敛，不在 ingestion runtime 内嵌上传规则。
    """

    sec_pipeline: "SecPipeline"
    cn_pipeline: "CnPipeline"

    def run_upload(
        self,
        request: ValidatedFinsUploadFilingRequest | FinsUploadMaterialRequest,
        *,
        cancellation_checker: FinsJobCancellationChecker,
    ) -> FinsUploadResultSummary:
        """执行 production 上传业务。

        Args:
            request: 已通过 runtime 启动边界校验的上传请求。
            cancellation_checker: runtime 提供的协作式取消检查器。

        Returns:
            有界上传结果摘要。

        Raises:
            ValueError: 请求缺少业务必填字段或 market 不支持时抛出。
            RuntimeError: pipeline 上传失败时抛出。
            OSError: 仓储读写失败时抛出。
        """

        raw_request = request.request if isinstance(request, ValidatedFinsUploadFilingRequest) else request
        if cancellation_checker():
            return FinsUploadResultSummary(
                source_kind=raw_request.source_kind,
                status="cancelled",
                requested_file_count=len(raw_request.files),
                stored_file_count=0,
                skip_reason="cancelled",
            )
        normalized = normalize_ticker(raw_request.ticker)
        if isinstance(request, ValidatedFinsUploadFilingRequest):
            result = self._run_filing_upload(
                request=request,
                market=normalized.market,
                cancellation_checker=cancellation_checker,
            )
            return _upload_summary_from_result(request=raw_request, result=result)
        if isinstance(request, FinsUploadMaterialRequest):
            result = self._run_material_upload(
                request=request,
                ticker=normalized.canonical,
                market=normalized.market,
                cancellation_checker=cancellation_checker,
            )
            return _upload_summary_from_result(request=request, result=result)
        raise ValueError("未知上传请求类型")

    def _run_filing_upload(
        self,
        *,
        request: ValidatedFinsUploadFilingRequest,
        market: str,
        cancellation_checker: FinsJobCancellationChecker,
    ) -> FinsUploadPipelineResult:
        """执行 filing 上传 handoff。

        Args:
            request: filing 上传请求。
            market: 归一化市场。
            cancellation_checker: 协作式取消检查器。

        Returns:
            typed pipeline 上传结果。

        Raises:
            ValueError: 必填字段缺失或市场不支持时抛出。
            RuntimeError: pipeline 上传失败时抛出。
            OSError: 仓储读写失败时抛出。
        """

        if market == "US":
            return FinsUploadPipelineResult.from_pipeline_json(
                self.sec_pipeline.upload_filing(
                    request,
                    cancellation_checker=cancellation_checker,
                )
            )
        if market in {"CN", "HK"}:
            return FinsUploadPipelineResult.from_pipeline_json(
                self.cn_pipeline.upload_filing(
                    request,
                    cancellation_checker=cancellation_checker,
                )
            )
        raise ValueError(f"不支持的上传市场: {market}")

    def _run_material_upload(
        self,
        *,
        request: FinsUploadMaterialRequest,
        ticker: str,
        market: str,
        cancellation_checker: FinsJobCancellationChecker,
    ) -> FinsUploadPipelineResult:
        """执行 material 上传 handoff。

        Args:
            request: material 上传请求。
            ticker: canonical ticker。
            market: 归一化市场。
            cancellation_checker: 协作式取消检查器。

        Returns:
            typed pipeline 上传结果。

        Raises:
            ValueError: 必填字段缺失或市场不支持时抛出。
            RuntimeError: pipeline 上传失败时抛出。
            OSError: 仓储读写失败时抛出。
        """

        if request.form_type is None:
            raise ValueError("material 上传必须提供 form_type")
        if request.material_name is None:
            raise ValueError("material 上传必须提供 material_name")
        action = _pipeline_upload_action(request.action)
        if market == "US":
            return FinsUploadPipelineResult.from_pipeline_json(
                self.sec_pipeline.upload_material(
                    ticker=ticker,
                    action=action,
                    form_type=request.form_type,
                    material_name=request.material_name,
                    files=list(request.files),
                    document_id=request.document_id,
                    internal_document_id=request.internal_document_id,
                    fiscal_year=request.fiscal_year,
                    fiscal_period=request.fiscal_period,
                    filing_date=request.filing_date,
                    report_date=request.report_date,
                    company_name=request.company_name,
                    ticker_aliases=list(request.ticker_aliases),
                    overwrite=request.overwrite,
                    cancellation_checker=cancellation_checker,
                )
            )
        if market in {"CN", "HK"}:
            return FinsUploadPipelineResult.from_pipeline_json(
                self.cn_pipeline.upload_material(
                    ticker=ticker,
                    action=action,
                    form_type=request.form_type,
                    material_name=request.material_name,
                    files=list(request.files),
                    document_id=request.document_id,
                    internal_document_id=request.internal_document_id,
                    fiscal_year=request.fiscal_year,
                    fiscal_period=request.fiscal_period,
                    filing_date=request.filing_date,
                    report_date=request.report_date,
                    company_name=request.company_name,
                    ticker_aliases=list(request.ticker_aliases),
                    overwrite=request.overwrite,
                    cancellation_checker=cancellation_checker,
                )
            )
        raise ValueError(f"不支持的上传市场: {market}")


def _pipeline_upload_action(action: str) -> str | None:
    """把 runtime upload action 转换为 pipeline action。

    Args:
        action: runtime action。

    Returns:
        pipeline action；``auto`` 返回 ``None``。

    Raises:
        无。
    """

    normalized = action.strip().lower()
    if normalized == "auto":
        return None
    return normalized


def _upload_summary_from_result(
    *,
    request: FinsUploadRequest,
    result: FinsUploadPipelineResult,
) -> FinsUploadResultSummary:
    """从 typed pipeline 上传结果构建 runtime 摘要。

    Args:
        request: 上传请求。
        result: typed pipeline 上传结果。

    Returns:
        runtime 有界上传摘要。

    Raises:
        无。
    """

    return FinsUploadResultSummary(
        source_kind=request.source_kind,
        status=result.status,
        requested_file_count=len(request.files),
        stored_file_count=result.stored_file_count,
        document_id=result.document_id,
        internal_document_id=result.internal_document_id,
        primary_document=result.primary_document,
        deleted=result.deleted,
        skip_reason=result.skip_reason,
        document_version=result.document_version,
        source_fingerprint=result.source_fingerprint,
        failure_reason=result.failure_reason,
    )


@dataclass
class DefaultFinsRuntime:
    """默认 Fins 共享运行时实现。

    该运行时装配 read tools 与 ingestion foundation 共享的仓储协议实现、
    处理器注册表和 workspace-scoped job store，不持有 Host、Service 或
    EventLog。
    """

    workspace_root: Path
    batching_repository: BatchingRepositoryProtocol
    company_repository: CompanyMetaRepositoryProtocol
    source_repository: SourceDocumentRepositoryProtocol
    blob_repository: DocumentBlobRepositoryProtocol
    filing_maintenance_repository: FilingMaintenanceRepositoryProtocol
    filing_upload_state_repository: FilingUploadStateRepositoryProtocol
    processed_repository: ProcessedDocumentRepositoryProtocol
    processor_registry: ProcessorRegistry
    ingestion_job_store: FsFinsIngestionJobStore
    _read_runtime: FinsReadRuntime | None = field(init=False, default=None, repr=False)
    _read_runtime_lock: Lock = field(init=False, repr=False)
    _closed: bool = field(init=False, default=False, repr=False)
    _ingestion_runtime: FinsIngestionRuntime | None = field(init=False, default=None, repr=False)
    _ingestion_runtime_lock: Lock = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """初始化内部锁。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self._read_runtime_lock = Lock()
        self._ingestion_runtime_lock = Lock()

    @classmethod
    def create(cls, *, workspace_root: Path) -> "DefaultFinsRuntime":
        """创建默认 Fins 共享运行时。

        Args:
            workspace_root: 已由 provider 显式解析的 Fins 工作区根目录。

        Returns:
            默认 Fins 共享运行时。

        Raises:
            OSError: 仓储根目录创建或读取失败时抛出。
        """

        repository_set = build_fs_repository_set(
            workspace_root=workspace_root,
            create_directories=False,
        )
        return cls(
            workspace_root=workspace_root,
            batching_repository=FsBatchingRepository(
                workspace_root,
                repository_set=repository_set,
            ),
            company_repository=FsCompanyMetaRepository(
                workspace_root,
                repository_set=repository_set,
            ),
            source_repository=FsSourceDocumentRepository(
                workspace_root,
                repository_set=repository_set,
            ),
            blob_repository=FsDocumentBlobRepository(
                workspace_root,
                repository_set=repository_set,
            ),
            filing_maintenance_repository=FsFilingMaintenanceRepository(
                workspace_root,
                repository_set=repository_set,
            ),
            filing_upload_state_repository=FsFilingUploadStateRepository(
                workspace_root,
                repository_set=repository_set,
            ),
            processed_repository=FsProcessedDocumentRepository(
                workspace_root,
                repository_set=repository_set,
            ),
            processor_registry=build_fins_processor_registry(),
            ingestion_job_store=FsFinsIngestionJobStore.from_workspace_root(workspace_root),
        )

    def get_processor_registry(self) -> ProcessorRegistry:
        """返回处理器注册表。

        Args:
            无。

        Returns:
            Fins 文档处理器注册表。

        Raises:
            无。
        """

        return self.processor_registry

    def get_read_runtime(self, *, processor_cache_max_entries: int = 128) -> FinsReadRuntime:
        """返回共享的 FinsReadRuntime 实例。

        Args:
            processor_cache_max_entries: Processor 缓存最大条目数，仅首次创建时生效。

        Returns:
            共享的 FinsReadRuntime 实例。

        Raises:
            ValueError: 缓存容量非法时由 FinsReadRuntime 抛出。
            RuntimeError: runtime 已关闭时抛出。
        """

        with self._read_runtime_lock:
            if self._closed:
                raise RuntimeError("DefaultFinsRuntime 已关闭")
            if self._read_runtime is not None:
                return self._read_runtime
            # dayu.fins.tools 包初始化会导入 provider，provider 又需要本模块；
            # 因此这里在运行时完成窄导入，避免直接 import service_runtime 时形成环。
            from dayu.fins.tools.read_runtime import FinsReadRuntime

            read_runtime = FinsReadRuntime(
                company_repository=self.company_repository,
                source_repository=self.source_repository,
                processed_repository=self.processed_repository,
                processor_registry=self.processor_registry,
                processor_cache_max_entries=processor_cache_max_entries,
            )
            self._read_runtime = read_runtime
            return read_runtime

    def close(self) -> None:
        """幂等关闭已经按需创建的 read runtime。

        close 不会为了清理而创建 read runtime，因此仅使用 ingestion 能力的
        ``DefaultFinsRuntime`` 仍保持 read path 的惰性装配。

        Args:
            无。

        Returns:
            无。

        Raises:
            BaseException: 已创建 read runtime 的 snapshot cleanup 失败时抛出。
        """

        with self._read_runtime_lock:
            self._closed = True
            read_runtime = self._read_runtime
        if read_runtime is not None:
            read_runtime.close()

    def get_ingestion_runtime(self) -> FinsIngestionRuntime:
        """返回共享的 Fins ingestion runtime 实例。

        Args:
            无。

        Returns:
            共享的 Fins ingestion runtime。

        Raises:
            无。
        """

        if self._ingestion_runtime is not None:
            return self._ingestion_runtime
        with self._ingestion_runtime_lock:
            if self._ingestion_runtime is not None:
                return self._ingestion_runtime
            from dayu.fins.pipelines.cn_pipeline import (
                CN_DOWNLOAD_SOURCE,
                HK_DOWNLOAD_SOURCE,
                CnPipeline,
                build_cn_download_adapter,
                build_hk_download_adapter,
            )
            from dayu.fins.pipelines.sec_pipeline import SEC_DOWNLOAD_SOURCE, SecPipeline, build_sec_download_adapter
            from dayu.fins.pipelines.docling_process_converter import ProcessDoclingConverter

            docling_converter = ProcessDoclingConverter()

            sec_download_adapter = build_sec_download_adapter(
                workspace_root=self.workspace_root,
                processor_registry=self.processor_registry,
                batching_repository=self.batching_repository,
                company_repository=self.company_repository,
                source_repository=self.source_repository,
                processed_repository=self.processed_repository,
                blob_repository=self.blob_repository,
                filing_maintenance_repository=self.filing_maintenance_repository,
            )
            cn_download_adapter = build_cn_download_adapter(
                workspace_root=self.workspace_root,
                batching_repository=self.batching_repository,
                company_repository=self.company_repository,
                source_repository=self.source_repository,
                processed_repository=self.processed_repository,
                blob_repository=self.blob_repository,
                filing_maintenance_repository=self.filing_maintenance_repository,
                docling_converter=docling_converter,
            )
            hk_download_adapter = build_hk_download_adapter(
                workspace_root=self.workspace_root,
                batching_repository=self.batching_repository,
                company_repository=self.company_repository,
                source_repository=self.source_repository,
                processed_repository=self.processed_repository,
                blob_repository=self.blob_repository,
                filing_maintenance_repository=self.filing_maintenance_repository,
                docling_converter=docling_converter,
            )
            # 下载 adapter 保留 source-specific downloader defaults 与 adapter identity；
            # upload runner 使用 production facade，但共享同一组 repository/job store。
            sec_upload_pipeline = SecPipeline(
                workspace_root=self.workspace_root,
                processor_registry=self.processor_registry,
                batching_repository=self.batching_repository,
                company_repository=self.company_repository,
                source_repository=self.source_repository,
                processed_repository=self.processed_repository,
                blob_repository=self.blob_repository,
                filing_maintenance_repository=self.filing_maintenance_repository,
                filing_upload_state_repository=self.filing_upload_state_repository,
                docling_converter=docling_converter,
            )
            cn_upload_pipeline = CnPipeline(
                workspace_root=self.workspace_root,
                batching_repository=self.batching_repository,
                company_repository=self.company_repository,
                source_repository=self.source_repository,
                processed_repository=self.processed_repository,
                blob_repository=self.blob_repository,
                filing_maintenance_repository=self.filing_maintenance_repository,
                filing_upload_state_repository=self.filing_upload_state_repository,
                docling_converter=docling_converter,
            )
            upload_runner = ProductionFinsUploadRunner(
                sec_pipeline=sec_upload_pipeline,
                cn_pipeline=cn_upload_pipeline,
            )
            runtime = FinsIngestionRuntime.create(
                batching_repository=self.batching_repository,
                source_repository=self.source_repository,
                blob_repository=self.blob_repository,
                filing_maintenance_repository=self.filing_maintenance_repository,
                filing_upload_state_repository=self.filing_upload_state_repository,
                processed_repository=self.processed_repository,
                processor_registry=self.processor_registry,
                job_store=self.ingestion_job_store,
                download_adapters={
                    (SEC_DOWNLOAD_SOURCE, "US"): sec_download_adapter,
                    ("auto", "US"): sec_download_adapter,
                    (CN_DOWNLOAD_SOURCE, "CN"): cn_download_adapter,
                    ("auto", "CN"): cn_download_adapter,
                    (HK_DOWNLOAD_SOURCE, "HK"): hk_download_adapter,
                    ("auto", "HK"): hk_download_adapter,
                },
                upload_runner=upload_runner,
            )
            self._ingestion_runtime = runtime
            return runtime
