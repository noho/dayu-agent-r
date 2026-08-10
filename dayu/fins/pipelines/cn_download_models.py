"""CN/HK 下载链路 typed model 与版本常量。

本模块仅定义 frozen dataclass、字面量类型与版本常量，**不做** I/O、**不依赖**
仓储/下载器实现。CN downloader（巨潮）、HK downloader（披露易）以及
``cn_download_*`` 系列 workflow 共享这些类型，确保跨模块字段语义稳定。

设计要点：

- 所有 dataclass 均 ``frozen=True``，避免下载链路把可变状态散落到不同阶段。
- CN/HK 专属字面量集中在本模块；共享财报语义值必须消费
  ``dayu.fins.domain`` 真源，禁止再定义同义字面量。
- ``CN_PIPELINE_DOWNLOAD_VERSION`` 为常量字符串：commit 时写入 source meta
  的 ``download_version`` 字段；skip 路径必须做版本相等性校验。版本不一致
  视同新候选，必须重新走完整下载流程。该常量随 CN 下载链路语义版本一起
  演进，例如 fingerprint 拆分策略变化、staging 字段语义变化时同步递增。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, Optional, TypeAlias

from dayu.fins.domain.filing_semantics import FiscalPeriod

CnMarketKind = Literal["CN", "HK"]
"""CN 下载链路覆盖的市场标识。``ticker_normalization.NormalizedTicker.market``
取值 ``"CN"`` / ``"HK"`` / ``"US"``，本字面量是 CN 链路允许的子集。"""

CnFiscalPeriod: TypeAlias = FiscalPeriod
"""CN/HK 财期类型别名，消费共享 domain 财期真源。

- ``FY``：年报。
- ``H1``：半年报。
- ``Q1`` / ``Q2`` / ``Q3`` / ``Q4``：独立季度报告或季度业绩。

这些值表示互不折叠的业务期间：``Q2`` 不归一为 ``H1``，``Q4`` 不归一
为 ``FY``。主源缺少某个独立期间报告时由 workflow 统一标记为 skipped，而
不是用相邻累计期间冒充。
"""

CN_FISCAL_PERIOD_ORDER: Final[tuple[CnFiscalPeriod, ...]] = (
    "FY",
    "H1",
    "Q1",
    "Q2",
    "Q3",
    "Q4",
)
"""CN/HK 下载链路唯一的 canonical 财期顺序。"""

CnSourceProvider = Literal["cninfo", "hkexnews"]
"""CN/HK 报告来源 provider 字面量。"""

CnFilingStage = Literal[
    "remote_selected",
    "pdf_downloaded",
    "docling_converted",
    "source_committed",
]
"""单 filing 下载阶段机字面量。

- ``remote_selected``：候选已选定，PDF 尚未落盘。
- ``pdf_downloaded``：PDF 已写入 blob 仓储但 docling 尚未完成。
- ``docling_converted``：docling JSON 已落盘但 source commit 尚未切换 primary。
- ``source_committed``：``ingest_complete=True``、``primary_document`` 切到
  ``_docling.json``，下载闭环完成。
"""

CnLanguage = Literal["zh", "en"]
"""CN/HK 候选语言字面量；副语言不入主 candidate 避免重复。"""


CN_PIPELINE_DOWNLOAD_VERSION: Final[str] = "cn_pipeline_download_v1.0.0"
"""CN 下载链路语义版本号。

写入 source meta 的 ``download_version`` 字段。skip / PDF skip 路径必须做版本
相等性校验：``previous_meta.download_version == CN_PIPELINE_DOWNLOAD_VERSION``
不成立时禁止 skip，强制走完整下载流程。版本号在以下情形递增：

- fingerprint 拆分策略发生变化（例如新增 ``content_fingerprint`` 子字段）；
- staging 字段含义变化（例如 ``staging_pdf_sha256`` 由 SHA-1 换 SHA-256）；
- 任何会影响"已完成态是否仍可被 skip 命中"的语义变更。

格式约束：``cn_pipeline_download_v{semver}``；与 SEC 链路保持一致的常量风格，
不在递增过程中写入 ``previous_meta.download_version + 1``。
"""


class CnDownloadCancelledError(RuntimeError):
    """CN/HK 下载工作流内部取消控制流异常。"""


@dataclass(frozen=True)
class CnCompanyProfile:
    """CN/HK 公司基础元数据。

    由 downloader 的 ``resolve_company`` 返回，供 company meta upsert 与
    source upsert 共同消费。``company_id`` 字段命名规则：

    - CN: ``"CNINFO:{orgId}"``，``orgId`` 来自巨潮全市场 stockList。
    - HK: ``"HKEX:{stockId}"``，``stockId`` 来自披露易
      ``activestock_sehk_*.json`` / ``inactivestock_sehk_*.json``。

    Attributes:
        provider: 报告来源 provider，与 ``CnSourceProvider`` 字面量一致。
        company_id: 公司主体 ID，遵循上述前缀约定。
        company_name: 公司名称（中文优先；HK 主板可能含 ``\\r\\n`` 已清洗）。
        ticker: 已归一化的 canonical ticker。
    """

    provider: CnSourceProvider
    company_id: str
    company_name: str
    ticker: str


@dataclass(frozen=True)
class CnReportQuery:
    """单 ticker 单次 download 的查询参数集合。

    Attributes:
        market: 市场标识。
        normalized_ticker: 已归一化的 canonical ticker（``NormalizedTicker.canonical``）。
        start_date: 窗口起点，``YYYY-MM-DD``。
        end_date: 窗口终点，``YYYY-MM-DD``，包含。
        discovery_periods: provider 必须发现的 canonical 财期集合；空集合已在
            policy 解析阶段被拒绝或替换为市场默认 discovery 范围。
    """

    market: CnMarketKind
    normalized_ticker: str
    start_date: str
    end_date: str
    discovery_periods: tuple[CnFiscalPeriod, ...]


@dataclass(frozen=True)
class CnReportCandidate:
    """单份候选报告的远端元数据。

    downloader 返回此对象，但**不**生成 ``document_id``（document_id 由
    ``build_cn_filing_ids`` 在 pipeline 层统一生成）。``content_length`` /
    ``etag`` / ``last_modified`` 用于参与 ``remote_fingerprint`` 计算。

    Attributes:
        provider: 报告来源 provider。
        source_id: provider 内部唯一 ID（CN 巨潮 announcementId、HK 披露易
            ``DOC_ID``）。
        source_url: 直接可下载 PDF 的绝对 URL。
        title: 公告标题（用于诊断、白/黑名单匹配）。
        language: 候选语言；副语言不入主 candidate。
        filing_date: 公告披露日期，``YYYY-MM-DD``。
        fiscal_year: 推断财年；``fiscal_year_source`` 在 source meta 标记为
            ``"title_or_category_inferred"``。
        fiscal_period: 推断财期；季度、半年报与年报互不折叠。
        amended: 是否修订/更正版本。
        content_length: HEAD 返回的 ``Content-Length``；为 ``None`` 表示
            HEAD 不可用或服务端未返回。
        etag: HEAD 返回的 ``ETag``；用于 fingerprint 比对。
        last_modified: HEAD 返回的 ``Last-Modified``；用于 fingerprint 比对。
    """

    provider: CnSourceProvider
    source_id: str
    source_url: str
    title: str
    language: CnLanguage
    filing_date: str
    fiscal_year: int
    fiscal_period: CnFiscalPeriod
    amended: bool
    content_length: Optional[int]
    etag: Optional[str]
    last_modified: Optional[str]


@dataclass(frozen=True)
class CnReportHeadMeta:
    """候选 PDF HEAD 响应元数据。

    Attributes:
        content_length: HEAD 返回的 ``Content-Length``；不可用时为 ``None``。
        etag: HEAD 返回的 ``ETag``。
        last_modified: HEAD 返回的 ``Last-Modified``。
    """

    content_length: Optional[int]
    etag: Optional[str]
    last_modified: Optional[str]


@dataclass(frozen=True)
class CninfoRawAnnouncement:
    """巨潮 raw announcement DTO。

    downloader 只负责 provider JSON 字段解析和 URL 归一，不在此对象上执行
    财报业务筛选、财期推断或 candidate 去重。

    Attributes:
        sec_code: 巨潮证券代码。
        announcement_id: 巨潮公告 ID。
        title: 清洗后的公告标题。
        announcement_date: 公告披露日期，``YYYY-MM-DD``。
        adjunct_url: 巨潮 PDF 相对路径。
        source_url: PDF 绝对 URL。
    """

    sec_code: str
    announcement_id: str
    title: str
    announcement_date: str
    adjunct_url: str
    source_url: str


@dataclass(frozen=True)
class HkexnewsRawAnnouncement:
    """披露易 raw announcement DTO。

    downloader 只负责 provider 字段解析、股票代码匹配前的 raw 字段清洗和
    PDF URL 归一，不在此对象上执行语言过滤、财期推断或 candidate 去重。

    Attributes:
        document_id: 披露易文档 ID。
        title: 清洗后的公告标题。
        source_url: PDF 绝对 URL。
        stock_code_payload: 披露易 ``STOCK_CODE`` 原始多代码字段。
        category_text: 披露易分类文本。
        filing_date: 披露日期，``YYYY-MM-DD``。
        language: 查询语言。
    """

    document_id: str
    title: str
    source_url: str
    stock_code_payload: str
    category_text: str
    filing_date: str
    language: CnLanguage


@dataclass(frozen=True)
class DownloadedReportAsset:
    """downloader 完成 PDF 下载后返回的强类型资产对象。

    与 ``CnReportCandidate`` 相比新增"已下载内容"事实：sha256、字节数、
    PDF 字节、下载时间戳。``sha256`` 是 PDF 字节内容的 SHA-256，与
    ``previous_meta.pdf_sha256`` 比对即可决定是否走 PDF skip。

    Attributes:
        candidate: 对应的远端候选元数据。
        pdf_bytes: 已下载并完成 PDF 校验的原始字节。
        sha256: PDF 字节内容的 SHA-256（小写 hex）。
        content_length: 实际写入的字节数。
        downloaded_at: ISO-8601 ``YYYY-MM-DDTHH:MM:SS+00:00`` UTC 时间戳。
    """

    candidate: CnReportCandidate
    pdf_bytes: bytes
    sha256: str
    content_length: int
    downloaded_at: str


__all__ = [
    "CN_FISCAL_PERIOD_ORDER",
    "CN_PIPELINE_DOWNLOAD_VERSION",
    "CnDownloadCancelledError",
    "CnCompanyProfile",
    "CnFilingStage",
    "CnFiscalPeriod",
    "CnLanguage",
    "CnMarketKind",
    "CnReportCandidate",
    "CnReportHeadMeta",
    "CnReportQuery",
    "CnSourceProvider",
    "CninfoRawAnnouncement",
    "DownloadedReportAsset",
    "HkexnewsRawAnnouncement",
]
