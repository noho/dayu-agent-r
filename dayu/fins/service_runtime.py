"""Fins 读取工具运行时装配。

本模块只承载 S4 read tools provider 需要的仓储、处理器注册表与
``FinsToolService`` 装配。下载/预处理 ingestion job 语义不在本 slice 暴露。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

from dayu.documents.processors.processor_registry import ProcessorRegistry
from dayu.fins.processors.registry import build_fins_processor_registry
from dayu.fins.storage import (
    CompanyMetaRepositoryProtocol,
    FsCompanyMetaRepository,
    FsProcessedDocumentRepository,
    FsSourceDocumentRepository,
    ProcessedDocumentRepositoryProtocol,
    SourceDocumentRepositoryProtocol,
)
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from dayu.fins.tools.service import FinsToolService


@dataclass
class DefaultFinsRuntime:
    """默认 Fins 读取运行时实现。

    该运行时只装配 read tools 需要的仓储协议实现和处理器注册表，不持有
    Host、Service、EventLog 或 ingestion job manager。
    """

    workspace_root: Path
    company_repository: CompanyMetaRepositoryProtocol
    source_repository: SourceDocumentRepositoryProtocol
    processed_repository: ProcessedDocumentRepositoryProtocol
    processor_registry: ProcessorRegistry
    _tool_service: FinsToolService | None = field(init=False, default=None, repr=False)
    _tool_service_lock: Lock = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """初始化内部锁。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self._tool_service_lock = Lock()

    @classmethod
    def create(cls, *, workspace_root: Path) -> "DefaultFinsRuntime":
        """创建默认 Fins 读取运行时。

        Args:
            workspace_root: 已由 provider 显式解析的 Fins 工作区根目录。

        Returns:
            默认 Fins 读取运行时。

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
            processed_repository=FsProcessedDocumentRepository(
                workspace_root,
                repository_set=repository_set,
            ),
            processor_registry=build_fins_processor_registry(),
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

    def get_tool_service(self, *, processor_cache_max_entries: int = 128) -> FinsToolService:
        """返回共享的 FinsToolService 实例。

        Args:
            processor_cache_max_entries: Processor 缓存最大条目数，仅首次创建时生效。

        Returns:
            共享的 FinsToolService 实例。

        Raises:
            ValueError: 缓存容量非法时由 FinsToolService 抛出。
        """

        if self._tool_service is not None:
            return self._tool_service
        with self._tool_service_lock:
            if self._tool_service is not None:
                return self._tool_service
            service = FinsToolService(
                company_repository=self.company_repository,
                source_repository=self.source_repository,
                processed_repository=self.processed_repository,
                processor_registry=self.processor_registry,
                processor_cache_max_entries=processor_cache_max_entries,
            )
            self._tool_service = service
            return service
