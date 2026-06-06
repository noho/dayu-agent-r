"""工具输出语义模型定义。

该模块定义工具层统一使用的语义增强数据结构，包含：
- Citation: 统一引用/溯源对象
- SectionSemantic: 章节语义层字段
- NumericContext: 数值上下文（单位/精度/期间）
- SourceType / SectionType 枚举
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class SourceType(str, Enum):
    """文档来源类型枚举。"""

    SEC_EDGAR = "SEC_EDGAR"
    """SEC EDGAR 下载的美股 filing。"""

    UPLOADED = "UPLOADED"
    """用户上传的 filing（港A股等）。"""

    SUPPLEMENTARY = "SUPPLEMENTARY"
    """补充材料（earnings call, presentation 等）。"""


class SectionType(str, Enum):
    """SEC filing 章节语义类型枚举。

    基于 SEC Regulation S-K 法定 Item 体系，覆盖 10-K、10-Q、20-F 常见章节。
    非 SEC filing 或无法映射时值为 None（不使用此枚举）。
    """

    # ── 10-K / 10-Q 通用 ──
    BUSINESS = "business"
    RISK_FACTORS = "risk_factors"
    UNRESOLVED_STAFF_COMMENTS = "unresolved_staff_comments"
    CYBERSECURITY = "cybersecurity"
    PROPERTIES = "properties"
    LEGAL_PROCEEDINGS = "legal_proceedings"
    MINE_SAFETY = "mine_safety"
    MARKET_FOR_EQUITY = "market_for_equity"
    SELECTED_FINANCIAL_DATA = "selected_financial_data"
    MDA = "mda"
    """Management's Discussion and Analysis。"""
    QUANTITATIVE_DISCLOSURES = "quantitative_disclosures"
    FINANCIAL_STATEMENTS = "financial_statements"
    CHANGES_DISAGREEMENTS = "changes_disagreements"
    CONTROLS_PROCEDURES = "controls_procedures"
    OTHER_INFORMATION = "other_information"
    DIRECTORS = "directors"
    EXECUTIVE_COMPENSATION = "executive_compensation"
    SECURITY_OWNERSHIP = "security_ownership"
    CERTAIN_RELATIONSHIPS = "certain_relationships"
    PRINCIPAL_ACCOUNTANT = "principal_accountant"
    EXHIBITS = "exhibits"
    SIGNATURE = "signature"

    # ── 20-F 专有 ──
    KEY_INFORMATION = "key_information"
    COMPANY_INFORMATION = "company_information"
    OPERATING_REVIEW = "operating_review"
    DIRECTORS_EMPLOYEES = "directors_employees"
    MAJOR_SHAREHOLDERS = "major_shareholders"
    FINANCIAL_INFORMATION = "financial_information"
    OFFER_LISTING = "offer_listing"
    ADDITIONAL_INFORMATION = "additional_information"
    MARKET_RISK = "market_risk"
    SECURITIES_DESCRIPTION = "securities_description"
    DEFAULTS_ARREARAGES = "defaults_arrearages"
    MATERIAL_MODIFICATIONS = "material_modifications"

    # ── 治理类（16A-16J）──
    GOVERNANCE = "governance"


@dataclass(frozen=True)
class Citation:
    """统一引用/溯源对象。

    所有 fins 工具的输出均携带此对象，使 LLM 能在最终报告中生成
    精确的来源引用，无需额外查询文档元数据。

    Attributes:
        source_type: 文档来源类型。
        form_type: 表单类型（如 "10-K"），非 filing 时为 None。
        filing_date: 申报日期（ISO 格式），非 filing 时为 None。
        accession_no: SEC accession number，仅美股 filing 有值。
        document_id: 文档唯一标识。
        ticker: 股票代码。
        fiscal_year: 财年。
        fiscal_period: 财期。
        item: 章节 Item 编号（如 "Item 1A"），仅部分工具填充。
        heading: 章节标题（如 "Risk Factors"），仅部分工具填充。
    """

    source_type: str
    document_id: str
    ticker: str
    form_type: Optional[str] = None
    filing_date: Optional[str] = None
    accession_no: Optional[str] = None
    fiscal_year: Optional[int] = None
    fiscal_period: Optional[str] = None
    item: Optional[str] = None
    heading: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化字典，移除值为 None 的键。

        Returns:
            紧凑字典。
        """
        return {k: v for k, v in asdict(self).items() if v is not None}

    def with_section(self, *, item: Optional[str] = None, heading: Optional[str] = None) -> "Citation":
        """派生一个附带章节信息的 Citation 副本。

        Args:
            item: 章节 Item 编号。
            heading: 章节标题。

        Returns:
            新 Citation 实例。
        """
        return Citation(
            source_type=self.source_type,
            document_id=self.document_id,
            ticker=self.ticker,
            form_type=self.form_type,
            filing_date=self.filing_date,
            accession_no=self.accession_no,
            fiscal_year=self.fiscal_year,
            fiscal_period=self.fiscal_period,
            item=item or self.item,
            heading=heading or self.heading,
        )


@dataclass(frozen=True)
class SectionSemantic:
    """章节语义层字段。

    对 SectionSummary 的语义增强，由 service 层在返回时注入。

    Attributes:
        item: Item 编号（如 "Item 1A"），非 SEC filing 时为 None。
        item_title: Item 法定标题（如 "Risk Factors"）。
        topic: 章节主题标识（如 "risk_factors"、"mda"），基于 SectionType 枚举值。
        path: 层级路径（如 ["Part I", "Item 1A", "Risk Factors"]）。
    """

    item: Optional[str] = None
    item_title: Optional[str] = None
    topic: Optional[str] = None
    path: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化字典。

        Returns:
            字典。
        """
        return asdict(self)


@dataclass(frozen=True)
class NumericContext:
    """数值上下文信息。

    为 XBRL facts 和 financial statement 提供单位/精度/期间元数据，
    帮助 LLM 正确理解数值含义。

    Attributes:
        unit: 单位（如 "USD"、"shares"）。
        scale: 数量级（如 "thousands"、"millions"、"billions"、"units"）。
        decimals: XBRL decimals 精度值。
        period_type: 期间类型（"instant" / "duration"）。
        period_start: 期间起始日（ISO 格式）。
        period_end: 期间终止日（ISO 格式）。
    """

    unit: Optional[str] = None
    scale: Optional[str] = None
    decimals: Optional[int] = None
    period_type: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化字典，移除值为 None 的键。

        Returns:
            紧凑字典。
        """
        return {k: v for k, v in asdict(self).items() if v is not None}
