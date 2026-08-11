"""CN/HK 下载链路对外 Protocol 边界。

本模块定义两类协议：

- :class:`CnReportDiscoveryClientProtocol`：discovery / 下载器对外稳定边界。
  巨潮 / 披露易 / 未来其他 CN/HK 实现均按此协议接入；workflow 层只依赖此协议，
  不假设具体实现细节。
- :class:`CnDownloadWorkflowHost`：CN download workflow 所需的最小宿主边界，
  仅暴露所需仓储以及 typed Docling runner。pipeline 通过实现该 Protocol 把仓储、
  runner 透传给 workflow，避免 workflow 反向依赖 ``CnPipeline``。

设计要点：

- 所有协议方法签名均使用明确类型；与第三方 SDK 的交互收敛到注入的
  Docling conversion runner。
- ``Protocol`` 用 ``runtime_checkable`` 修饰仅在确实有运行期 ``isinstance``
  检查时才使用；本模块仅做静态契约，不开 runtime check。
- raw ``cancel_checker`` 只由 workflow 解释；协议仅为 discovery 运输
  workflow 已收敛的无参、无返回值 cancellation checkpoint。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Optional, Protocol

from dayu.fins.pipelines.cn_download_pdf_gate import CnDownloadPdfGateProtocol
from dayu.fins.pipelines.cn_download_models import (
    CnCompanyProfile,
    CnReportCandidate,
    CnReportQuery,
    DownloadedReportAsset,
)
from dayu.fins.storage import (
    BatchingRepositoryProtocol,
    CompanyMetaRepositoryProtocol,
    DocumentBlobRepositoryProtocol,
    FilingMaintenanceRepositoryProtocol,
    ProcessedDocumentRepositoryProtocol,
    SourceDocumentRepositoryProtocol,
)


class CnDoclingConversionRunner(Protocol):
    """CN/HK 下载链路的可取消 Docling 转换协议。"""

    async def convert_pdf_to_docling_json(
        self,
        pdf_bytes: bytes,
        stream_name: str,
        *,
        cancellation_checker: Callable[[], bool],
    ) -> bytes:
        """把 PDF bytes 转换为 Docling JSON bytes。

        Args:
            pdf_bytes: 待转换的 PDF 原始字节。
            stream_name: 不含路径的输入流名称。
            cancellation_checker: operation-scoped 取消检查器。

        Returns:
            已完成转换并校验的 Docling JSON bytes。

        Raises:
            CnDownloadCancelledError: conversion 期间收到取消请求时抛出。
            RuntimeError: 子进程执行、输出校验或清理失败时抛出。
            OSError: 临时文件创建、读取或清理失败时抛出。
        """

        ...


class CnReportDiscoveryClientProtocol(Protocol):
    """CN/HK 报告发现 / 下载 Protocol。

    一个 ticker 一次 download 流程会先调用 ``resolve_company`` 拿
    :class:`CnCompanyProfile`，再按 ``discovery_periods`` 调
    ``list_report_candidates`` 拿候选列表，最后按 candidate 调
    ``download_report_pdf`` 落 PDF。

    实现约束：

    - 不写 workspace、不依赖 pipeline、不调 docling、不生成 ``document_id``。
    - HEAD/GET 失败、PDF magic bytes 校验失败等候选层失败仅影响该 candidate，
      不能让整个 ticker 流程崩。
    - HK 季度报告查无视为返回空列表（不抛异常），由 workflow 标 skipped。
    - discovery 请求失败 / JSON 解析失败必须抛 ``RuntimeError``，不能用空
      候选伪装成缺报告。
    """

    def resolve_company(self, query: CnReportQuery) -> CnCompanyProfile:
        """根据 ``CnReportQuery.normalized_ticker`` 解析公司基础元数据。

        Args:
            query: 单次 download 的查询参数。

        Returns:
            :class:`CnCompanyProfile`，``company_id`` 必须遵循 ``CNINFO:{orgId}``
            或 ``HKEX:{stockId}`` 前缀约定。

        Raises:
            ValueError: 公司映射响应合法但无法定位 ticker 时抛出。
            RuntimeError: 主源请求失败或响应无法解析时抛出。
        """

        ...

    def list_report_candidates(
        self,
        query: CnReportQuery,
        profile: CnCompanyProfile,
        *,
        cancellation_checkpoint: Callable[[], None] | None = None,
    ) -> tuple[CnReportCandidate, ...]:
        """列出符合 ``discovery_periods`` 与窗口约束的候选报告。

        实现层负责按白/黑名单与类别过滤、按 fiscal_period 去重；多版本仅保留
        最新有效全文，amended 优先。HK 季度报告查无返回空 tuple，**不**抛
        异常。

        Args:
            query: 单次 download 的查询参数。
            profile: ``resolve_company`` 返回的公司元数据。
            cancellation_checkpoint: 可选 workflow-owned 无参取消检查点；
                provider 只在真实 discovery I/O 边界调用并原样传播异常。

        Returns:
            候选报告 tuple；候选已经按 fiscal_period 收敛、amended 优先。

        Raises:
            ValueError: 查询参数或 profile 与当前 provider 不匹配时抛出。
            RuntimeError: 主源请求失败或响应无法解析时抛出。
        """

        ...

    def download_report_pdf(self, candidate: CnReportCandidate) -> DownloadedReportAsset:
        """下载单份候选 PDF 并返回强类型资产对象。

        实现层负责 ``%PDF-`` magic bytes 校验、最小长度校验、Content-Type
        校验、必要的 retry / sleep。返回值直接携带已校验的 ``pdf_bytes``，
        downloader 不创建临时文件。

        Args:
            candidate: 单份候选远端元数据。

        Returns:
            :class:`DownloadedReportAsset`。

        Raises:
            RuntimeError: 下载失败、PDF 校验失败、HTTP 状态码异常时抛出。
        """

        ...


class CnDownloadWorkflowHost(Protocol):
    """CN download workflow 所需的最小宿主边界。

    实现侧典型为 :class:`dayu.fins.pipelines.cn_pipeline.CnPipeline`，但
    workflow 不直接 import ``CnPipeline``，仅按本协议消费。

    协议只暴露：

    - 5 个仓储（company / source / blob / processed / filing_maintenance）。
    - CN/HK 两个 discovery client 注入点。
    - typed Docling conversion runner 注入点。

    其它横切（取消、日志）由 workflow 层显式接收 ``cancel_checker`` 等参数
    管理，不放进 host。
    """

    @property
    def batching_repository(self) -> BatchingRepositoryProtocol:
        """batch lifecycle 唯一仓储。"""

        ...

    @property
    def company_meta_repository(self) -> CompanyMetaRepositoryProtocol:
        """公司元数据仓储。"""

        ...

    @property
    def source_repository(self) -> SourceDocumentRepositoryProtocol:
        """源文档仓储。"""

        ...

    @property
    def blob_repository(self) -> DocumentBlobRepositoryProtocol:
        """文件对象仓储。"""

        ...

    @property
    def processed_repository(self) -> ProcessedDocumentRepositoryProtocol:
        """processed 仓储；download 链路在 commit 后按规则标 reprocess。"""

        ...

    @property
    def filing_maintenance_repository(self) -> FilingMaintenanceRepositoryProtocol:
        """filing 维护仓储；``overwrite=True`` 时做 ticker 级 ``clear_filing_documents``。"""

        ...

    @property
    def cn_discovery_client(self) -> CnReportDiscoveryClientProtocol:
        """A 股巨潮 discovery client。"""

        ...

    @property
    def hk_discovery_client(self) -> CnReportDiscoveryClientProtocol:
        """港股披露易 discovery client。"""

        ...

    @property
    def pdf_download_gate(self) -> CnDownloadPdfGateProtocol:
        """CN/HK PDF 下载段 gate。"""

        ...

    @property
    def docling_conversion_runner(self) -> CnDoclingConversionRunner:
        """返回 operation-scoped 可取消 Docling conversion runner。"""

        ...

    @property
    def user_agent(self) -> Optional[str]:
        """HTTP User-Agent，用于 downloader 透传。"""

        ...

    @property
    def sleep_seconds(self) -> float:
        """连续 HTTP 请求间隔秒数。"""

        ...

    @property
    def max_retries(self) -> int:
        """最大重试次数。"""

        ...


__all__ = [
    "CnDoclingConversionRunner",
    "CnDownloadWorkflowHost",
    "CnReportDiscoveryClientProtocol",
]
