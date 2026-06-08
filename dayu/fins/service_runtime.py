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
from dayu.fins.ingestion_runtime import FinsIngestionRuntime, FsFinsIngestionJobStore
from dayu.fins.processors.registry import build_fins_processor_registry
from dayu.fins.storage import (
    CompanyMetaRepositoryProtocol,
    DocumentBlobRepositoryProtocol,
    FilingMaintenanceRepositoryProtocol,
    FsCompanyMetaRepository,
    FsDocumentBlobRepository,
    FsFilingMaintenanceRepository,
    FsProcessedDocumentRepository,
    FsSourceDocumentRepository,
    ProcessedDocumentRepositoryProtocol,
    SourceDocumentRepositoryProtocol,
)
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set

if TYPE_CHECKING:
    from dayu.fins.tools.read_runtime import FinsReadRuntime


@dataclass
class DefaultFinsRuntime:
    """默认 Fins 共享运行时实现。

    该运行时装配 read tools 与 ingestion foundation 共享的仓储协议实现、
    处理器注册表和 workspace-scoped job store，不持有 Host、Service 或
    EventLog。
    """

    workspace_root: Path
    company_repository: CompanyMetaRepositoryProtocol
    source_repository: SourceDocumentRepositoryProtocol
    blob_repository: DocumentBlobRepositoryProtocol
    filing_maintenance_repository: FilingMaintenanceRepositoryProtocol
    processed_repository: ProcessedDocumentRepositoryProtocol
    processor_registry: ProcessorRegistry
    ingestion_job_store: FsFinsIngestionJobStore
    _read_runtime: FinsReadRuntime | None = field(init=False, default=None, repr=False)
    _read_runtime_lock: Lock = field(init=False, repr=False)
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

        repository_set = build_fs_repository_set(workspace_root=workspace_root)
        return cls(
            workspace_root=workspace_root,
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
        """

        if self._read_runtime is not None:
            return self._read_runtime
        with self._read_runtime_lock:
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
            runtime = FinsIngestionRuntime.create(
                source_repository=self.source_repository,
                blob_repository=self.blob_repository,
                filing_maintenance_repository=self.filing_maintenance_repository,
                processed_repository=self.processed_repository,
                processor_registry=self.processor_registry,
                job_store=self.ingestion_job_store,
            )
            self._ingestion_runtime = runtime
            return runtime
