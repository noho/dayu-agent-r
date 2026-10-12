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

import hashlib
from dataclasses import dataclass
from typing import Final, Literal, Optional, TypeAlias

from dayu.fins.domain.document_models import SourceDocumentRevision
from dayu.fins.domain.filing_semantics import FiscalPeriod
from dayu.fins.download_contract import FinsDownloadUncertainReport

CnMarketKind = Literal["CN", "HK"]
"""CN 下载链路覆盖的市场标识。``ticker_normalization.NormalizedTicker.market``
取值 ``"CN"`` / ``"HK"`` / ``"US"``，本字面量是 CN 链路允许的子集。"""

CnDownloadTerminalStatus: TypeAlias = Literal["ok", "cancelled", "integrity_failed"]
"""CN/HK 下载与本地重建共享的 pipeline 终态；不表示每文档状态。"""

CN_DOWNLOAD_TERMINAL_OK: Final[CnDownloadTerminalStatus] = "ok"
"""普通下载或重建完成；文档是否成功由各行结果表达。"""

CN_DOWNLOAD_TERMINAL_CANCELLED: Final[CnDownloadTerminalStatus] = "cancelled"
"""普通下载或重建已取消，保留已处理文档摘要。"""

CN_DOWNLOAD_TERMINAL_INTEGRITY_FAILED: Final[CnDownloadTerminalStatus] = "integrity_failed"
"""私有完整性中止快照的终态，仅由完整性快照入口消费。"""

CN_DOWNLOAD_NORMAL_TERMINAL_STATUSES: Final[tuple[CnDownloadTerminalStatus, ...]] = (
    CN_DOWNLOAD_TERMINAL_OK,
    CN_DOWNLOAD_TERMINAL_CANCELLED,
)
"""普通结果入口的合法终态子集，直接派生自同一词表。"""

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


@dataclass(frozen=True, slots=True)
class CnReportPeriodProjection:
    """单份 CN/HK 报告的身份财期与覆盖财期投影。

    Attributes:
        identity_period: 报告自身唯一身份财期；用于 ID、窗口、missing、form 与
            report kind。
        covered_periods: 报告内容覆盖的 canonical 财期；仅用于向外投影，不能
            代替独立报告满足 missing baseline。

    Raises:
        TypeError: 字段类型非法时抛出。
        ValueError: 覆盖集合为空、重复、顺序非法或不含身份财期时抛出。
    """

    identity_period: CnFiscalPeriod
    covered_periods: tuple[CnFiscalPeriod, ...]

    def __post_init__(self) -> None:
        """校验身份与覆盖财期的 canonical contract。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 字段类型非法时抛出。
            ValueError: 覆盖集合为空、重复、顺序非法或不含身份财期时抛出。
        """

        if not isinstance(self.identity_period, str) or self.identity_period not in CN_FISCAL_PERIOD_ORDER:
            raise TypeError("identity_period 必须是 canonical CN/HK 财期")
        if not isinstance(self.covered_periods, tuple):
            raise TypeError("covered_periods 必须是 tuple")
        if not self.covered_periods:
            raise ValueError("covered_periods 不能为空")
        if any(not isinstance(period, str) or period not in CN_FISCAL_PERIOD_ORDER for period in self.covered_periods):
            raise TypeError("covered_periods 必须只包含 canonical CN/HK 财期")
        if len(set(self.covered_periods)) != len(self.covered_periods):
            raise ValueError("covered_periods 不能重复")
        canonical = tuple(period for period in CN_FISCAL_PERIOD_ORDER if period in self.covered_periods)
        if self.covered_periods != canonical:
            raise ValueError("covered_periods 必须采用 canonical 财期顺序")
        if self.identity_period not in self.covered_periods:
            raise ValueError("covered_periods 必须包含 identity_period")


@dataclass(frozen=True)
class CnReportCandidate:
    """单份候选报告的远端元数据。

    downloader 返回此对象，但**不**生成 ``document_id``（document_id 由
    pipeline 的来源身份绑定规则统一分配或复用）。``content_length`` /
    ``etag`` / ``last_modified`` 用于参与 ``remote_fingerprint`` 计算。

    Attributes:
        provider: 报告来源 provider。
        source_id: provider 内部唯一 ID（CN 巨潮 announcementId、HK 披露易
            ``DOC_ID``）。
        source_url: 直接可下载 PDF 的绝对 URL。
        title: 公告标题（用于诊断、白/黑名单匹配）。
        category_text: 原始 provider 分类；缺少时为空。
        report_date: 从原始标题识别的截止日；缺少时为 None。
        language: 候选语言；副语言不入主 candidate。
        filing_date: 公告披露日期，``YYYY-MM-DD``。
        fiscal_year: 已确认财年。
        fiscal_year_source: 财年事实来源；CN FY 必须来自原文。
        period_projection: 身份财期与覆盖财期投影。
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
    fiscal_year_source: Literal["title_or_category_inferred", "source_document"]
    period_projection: CnReportPeriodProjection
    amended: bool
    content_length: Optional[int]
    etag: Optional[str]
    last_modified: Optional[str]

    category_text: str = ""
    report_date: str | None = None


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
    "CnReportDiscoveryResult",
    "CnAnnualReportFacts",
    "CnAnnualReportPublication",
    "CnAnnualReportPdf",
    "require_matching_cn_annual_asset",
    "CN_DOWNLOAD_NORMAL_TERMINAL_STATUSES",
    "CN_DOWNLOAD_TERMINAL_OK",
    "CN_DOWNLOAD_TERMINAL_CANCELLED",
    "CN_DOWNLOAD_TERMINAL_INTEGRITY_FAILED",
    "CN_FISCAL_PERIOD_ORDER",
    "CN_PIPELINE_DOWNLOAD_VERSION",
    "CnDownloadCancelledError",
    "CnDownloadTerminalStatus",
    "CnCompanyProfile",
    "CnFilingStage",
    "CnFiscalPeriod",
    "CnLanguage",
    "CnMarketKind",
    "CnReportCandidate",
    "CnReportHeadMeta",
    "CnReportPeriodProjection",
    "CnReportQuery",
    "CnSourceProvider",
    "CninfoRawAnnouncement",
    "DownloadedReportAsset",
    "HkexnewsRawAnnouncement",
]


@dataclass(frozen=True, slots=True)
class CnReportDiscoveryResult:
    """完整发现的确定候选与独立未知来源；两个集合均必填，不做身份分配。"""

    candidates: tuple[CnReportCandidate, ...]
    uncertain_reports: tuple[FinsDownloadUncertainReport, ...]
    prepared_assets: tuple[DownloadedReportAsset, ...]
    local_annual_publications: tuple[CnAnnualReportPublication, ...]

    def __post_init__(self) -> None:
        """校验所选来源与同次资产、只读见证的唯一绑定。

        参数：无。返回：无。异常：ValueError 表示重复或错配来源。
        """
        by_source = {(c.provider, c.source_id): c for c in self.candidates}
        if len(by_source) != len(self.candidates):
            raise ValueError("候选来源必须唯一")
        handed: set[tuple[str, str]] = set()
        for asset in self.prepared_assets:
            key = (asset.candidate.provider, asset.candidate.source_id)
            if key in handed or key not in by_source:
                raise ValueError("prepared 来源重复或未被选择")
            require_matching_cn_annual_asset(by_source[key], asset)
            handed.add(key)
        for publication in self.local_annual_publications:
            key = (publication.provider, publication.source_id)
            if key in handed or key not in by_source:
                raise ValueError("本地见证来源重复或未被选择")
            candidate = by_source[key]
            if candidate.provider != "cninfo" or candidate.period_projection.identity_period != "FY":
                raise ValueError("本地见证仅允许 CN FY")
            handed.add(key)


@dataclass(frozen=True, slots=True)
class CnAnnualReportFacts:
    """官方原文年度事实，不含推断或来源治理状态。"""

    fiscal_year: int
    kind: Literal["full", "summary"]

    def __post_init__(self) -> None:
        """校验封闭事实。参数：无。返回：无。异常：TypeError/ValueError 为非法事实。"""
        if type(self.fiscal_year) is not int or type(self.kind) is not str:
            raise TypeError("年度事实字段类型非法")
        if not 1000 <= self.fiscal_year <= 9999 or self.kind not in ("full", "summary"):
            raise ValueError("年度事实值非法")


@dataclass(frozen=True, slots=True)
class CnAnnualReportPublication:
    """已确认原件的 exact publication 只读见证，不授予写权限。"""

    provider: Literal["cninfo"]
    source_id: str
    document_id: str
    revision: SourceDocumentRevision

    def __post_init__(self) -> None:
        """校验来源见证。参数：无。返回：无。异常：TypeError/ValueError 为非法身份。"""
        if any(type(v) is not str for v in (self.provider, self.source_id, self.document_id)):
            raise TypeError("来源身份必须为字符串")
        if not isinstance(self.revision, SourceDocumentRevision):
            raise TypeError("revision 必须为仓储版本")
        if self.provider != "cninfo" or not self.source_id or not self.document_id:
            raise ValueError("来源身份不能为空或跨 provider")


@dataclass(frozen=True, slots=True)
class CnAnnualReportPdf:
    """同一 snapshot 的原件 bytes、实际 locator 与见证。"""

    publication: CnAnnualReportPublication
    source_url: str
    pdf_bytes: bytes

    def __post_init__(self) -> None:
        """校验原件输入。参数：无。返回：无。异常：TypeError/ValueError 为非法输入。"""
        if not isinstance(self.publication, CnAnnualReportPublication):
            raise TypeError("publication 类型非法")
        if type(self.source_url) is not str or type(self.pdf_bytes) is not bytes:
            raise TypeError("原件 locator/bytes 类型非法")
        if self.source_url == "" or not self.pdf_bytes:
            raise ValueError("原件 locator/bytes 不能为空")


def require_matching_cn_annual_asset(candidate: CnReportCandidate, asset: DownloadedReportAsset) -> None:
    """校验同次年度原件资产。参数：candidate、asset 为所选来源及资产。返回：无。

    异常：ValueError 表示候选、来源、字节长度或摘要不匹配。
    """
    if candidate.provider != "cninfo" or candidate.period_projection.identity_period != "FY":
        raise ValueError("年度资产仅允许 CN FY")
    if candidate.fiscal_year_source != "source_document" or asset.candidate != candidate:
        raise ValueError("年度资产候选或事实来源不匹配")
    if type(asset.pdf_bytes) is not bytes or not asset.pdf_bytes:
        raise ValueError("年度资产原件不能为空")
    if type(asset.content_length) is not int or asset.content_length != len(asset.pdf_bytes):
        raise ValueError("年度资产长度不匹配")
    if asset.sha256 != hashlib.sha256(asset.pdf_bytes).hexdigest() or not asset.downloaded_at:
        raise ValueError("年度资产摘要或取得时间不匹配")
