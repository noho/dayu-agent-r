"""搜索数据模型与常量。

该模块定义搜索子系统的纯数据结构（dataclass）和词表/常量，
不包含任何业务逻辑，作为 search_engine 和 service 的共享基础。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# 搜索策略常量
# ---------------------------------------------------------------------------
_SEARCH_STRATEGY_EXACT = "exact"
_SEARCH_STRATEGY_PHRASE_VARIANT = "phrase_variant"
_SEARCH_STRATEGY_SYNONYM = "synonym"
_SEARCH_STRATEGY_TOKEN = "token"
_SEARCH_STRATEGY_PRIORITY: dict[str, int] = {
    _SEARCH_STRATEGY_EXACT: 0,
    _SEARCH_STRATEGY_PHRASE_VARIANT: 1,
    _SEARCH_STRATEGY_SYNONYM: 2,
    _SEARCH_STRATEGY_TOKEN: 3,
}
_SEARCH_RANKING_VERSION = "adaptive_bm25f_v1.0.0"

# ---------------------------------------------------------------------------
# 搜索模式常量
# ---------------------------------------------------------------------------
SEARCH_MODE_AUTO = "auto"
SEARCH_MODE_EXACT = "exact"
SEARCH_MODE_KEYWORD = "keyword"
SEARCH_MODE_SEMANTIC = "semantic"
_VALID_SEARCH_MODES = frozenset(
    {SEARCH_MODE_AUTO, SEARCH_MODE_EXACT, SEARCH_MODE_KEYWORD, SEARCH_MODE_SEMANTIC}
)

# ---------------------------------------------------------------------------
# 预编译正则（搜索子系统共用）
# ---------------------------------------------------------------------------
_WORD_SPLIT_PATTERN = re.compile(r"[a-z0-9]+")
_SPACE_NORMALIZE_PATTERN = re.compile(r"\s+")

# ---------------------------------------------------------------------------
# Token 停用词
# ---------------------------------------------------------------------------
_TOKEN_STOP_WORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "into",
        "about",
        "this",
        "that",
        "have",
        "has",
        "had",
        "are",
        "was",
        "were",
        "or",
        "but",
    }
)

# ---------------------------------------------------------------------------
# 同义词/术语映射组
# ---------------------------------------------------------------------------
_SEARCH_SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    ("revenue", "revenues", "sales", "营业收入", "營業收入"),
    ("net income", "net profit", "净利润", "淨利潤"),
    ("cash flow", "现金流", "現金流"),
    ("risk", "risks", "risk factors", "风险", "風險"),
    ("guidance", "outlook", "指引", "展望"),
    ("share repurchase", "repurchase", "buyback", "回购", "回購"),
    ("board of directors", "board", "董事会", "董事會"),
    ("management", "executive officers", "管理层", "管理層"),
    ("legal proceedings", "litigation", "诉讼", "訴訟"),
    # 竞争与市场
    ("compete", "competition", "competitor", "competitive", "competitiveness"),
    ("market share", "market position", "market penetration"),
    ("monopoly", "dominant position", "market dominance"),
    # 并购与交易
    ("acquisition", "merger", "deal", "buyout", "takeover"),
    # 产品与服务
    ("product", "offering", "solution", "service", "platform"),
    # 威胁与挑战
    ("threat", "headwind", "challenge", "pressure"),
    # 知识产权
    ("intellectual property", "patent", "proprietary"),
    # 供应链
    ("supply chain", "sourcing", "procurement", "vendor", "supplier"),
    # 客户留存
    ("customer retention", "churn", "loyalty"),
    # 盈利能力
    ("profit", "profitability", "margin", "earnings"),
    ("operating income", "operating profit", "ebit"),
    # 负债与资本
    ("debt", "borrowing", "leverage", "liabilities"),
    ("equity", "shareholders equity", "stockholders equity"),
    # 研发
    ("research and development", "r&d", "innovation"),
    # 监管
    ("regulation", "regulatory", "compliance"),
    # 股息
    ("dividend", "dividends", "distribution", "payout"),
)

# ---------------------------------------------------------------------------
# 高歧义 token 集合
# ---------------------------------------------------------------------------
_GENERIC_AMBIGUOUS_TOKENS = frozenset(
    {
        "competition",
        "competitor",
        "competitive",
        "market",
        "business",
        "strategy",
        "policy",
        "growth",
        "performance",
        "management",
        "risk",
        "compliance",
    }
)

# ---------------------------------------------------------------------------
# 意图关键词词表
# ---------------------------------------------------------------------------
_INTENT_KEYWORDS: dict[str, frozenset[str]] = {
    "business_competition": frozenset(
        {
            "competitor",
            "competition",
            "competitive",
            "market",
            "marketshare",
            "share",
            "customer",
            "industry",
            "peer",
            "supplier",
            "product",
            "service",
            "lithography",
            "semiconductor",
        }
    ),
    "financial": frozenset(
        {
            "revenue",
            "income",
            "earnings",
            "cash",
            "margin",
            "asset",
            "liability",
            "equity",
            "guidance",
            "profit",
        }
    ),
    "governance": frozenset(
        {
            "board",
            "director",
            "governance",
            "compensation",
            "executive",
            "committee",
            "ethics",
            "compliance",
            "anti",
            "bribery",
        }
    ),
    "people": frozenset(
        {
            "employee",
            "talent",
            "hiring",
            "students",
            "competition",
            "league",
            "recruit",
            "workforce",
            "training",
            "employer",
        }
    ),
    "risk": frozenset(
        {
            "risk",
            "threat",
            "uncertainty",
            "vulnerability",
            "cybersecurity",
            "litigation",
            "exposure",
        }
    ),
}

# ---------------------------------------------------------------------------
# 意图噪声/支持上下文词表
# ---------------------------------------------------------------------------
_NOISE_CONTEXT_TOKENS_BY_INTENT: dict[str, frozenset[str]] = {
    "business_competition": frozenset(
        {
            "antitrust",
            "compliance",
            "ethics",
            "students",
            "league",
            "robotics",
            "employer",
            "universum",
            "human",
            "rights",
        }
    ),
}

_SUPPORT_CONTEXT_TOKENS_BY_INTENT: dict[str, frozenset[str]] = {
    "business_competition": frozenset(
        {
            "market",
            "industry",
            "customer",
            "supplier",
            "peer",
            "product",
            "service",
            "technology",
            "lithography",
            "semiconductor",
        }
    ),
}


# ---------------------------------------------------------------------------
# 语义桶映射（自适应方案）
# ---------------------------------------------------------------------------

# ── Topic → Bucket 直接映射 ──────────────────────────────────
# SectionType.value → semantic bucket，涵盖 SEC 全表单的法定 Item 语义类型。
# 新增 SectionType 时只需在此表补充一行，无需修改匹配逻辑。
_TOPIC_TO_BUCKET: dict[str, str] = {
    # business 域：公司概况、主营业务、运营环境
    "business": "business",
    "company_information": "business",
    "properties": "business",
    "operating_review": "business",
    # risk 域：风险因素、市场风险、网络安全
    "risk_factors": "risk",
    "market_risk": "risk",
    "cybersecurity": "risk",
    # financial 域：财报、MD&A、定量披露
    "mda": "financial",
    "financial_statements": "financial",
    "financial_information": "financial",
    "selected_financial_data": "financial",
    "quantitative_disclosures": "financial",
    "key_information": "financial",
    # governance 域：治理、高管薪酬、控制程序
    "directors": "governance",
    "governance": "governance",
    "executive_compensation": "governance",
    "security_ownership": "governance",
    "certain_relationships": "governance",
    "principal_accountant": "governance",
    "controls_procedures": "governance",
    # people 域：员工、人力资本
    "directors_employees": "people",
    # legal 域：法律诉讼
    "legal_proceedings": "legal",
    # other 域：附录、签名、矿安等
    "exhibits": "other",
    "signature": "other",
    "mine_safety": "other",
    "other_information": "other",
    "unresolved_staff_comments": "other",
    "offer_listing": "other",
    "additional_information": "other",
    "market_for_equity": "financial",
    "securities_description": "other",
    "defaults_arrearages": "other",
    "material_modifications": "other",
    "changes_disagreements": "other",
}

# ── Bucket 关键词信号（fallback 专用）──────────────────────────
# 当 topic 不在 _TOPIC_TO_BUCKET 时，基于 title/path/item 的关键词评分。
# 每个 bucket 对应一组单词关键词（词集交集匹配），命中数量即得分。
# 取最高分桶；全部为零时返回 "other"。
_BUCKET_KEYWORD_SIGNALS: dict[str, frozenset[str]] = {
    "business": frozenset({
        "business", "operating", "market", "product", "service",
        "customer", "industry", "company", "overview", "operations",
    }),
    "risk": frozenset({
        "risk", "risks", "threat", "uncertainty", "cybersecurity",
    }),
    "financial": frozenset({
        "financial", "income", "revenue", "earnings", "assets",
        "liabilities", "equity", "cash", "mda", "discussion",
        "analysis", "quantitative",
    }),
    "governance": frozenset({
        "governance", "director", "directors", "compensation",
        "committee", "board", "audit", "shareholder", "ethics",
    }),
    "people": frozenset({
        "employee", "employees", "workforce", "personnel",
        "staff", "talent", "headcount",
    }),
    "legal": frozenset({
        "legal", "proceeding", "proceedings", "litigation",
        "lawsuit", "compliance",
    }),
}

# ── Intent → 期望 Bucket 集合 ──────────────────────────────────
# 查询意图对应的优先桶；命中时意图对齐分为 1.0，否则 0.0。
# 新增意图只需扩展此表。
_EXPECTED_BUCKETS_BY_INTENT: dict[str, frozenset[str]] = {
    "business_competition": frozenset({"business", "risk", "financial"}),
    "financial": frozenset({"financial", "business"}),
    "governance": frozenset({"governance", "legal", "people"}),
    "people": frozenset({"people", "governance"}),
    "risk": frozenset({"risk", "legal", "business"}),
}


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class QueryDiagnosis:
    """搜索查询诊断结果。

    Args:
        query: 标准化查询文本。
        tokens: 查询 token 列表。
        token_count: token 数量。
        ambiguity_score: 查询歧义分数，范围 0~1。
        is_high_ambiguity: 是否高歧义查询。
        intent: 查询意图分类。
        allow_direct_token_fallback: 是否允许直接 token 回退。

    Returns:
        无。

    Raises:
        无。
    """

    query: str
    tokens: tuple[str, ...]
    token_count: int
    ambiguity_score: float
    is_high_ambiguity: bool
    intent: str
    allow_direct_token_fallback: bool


@dataclass(frozen=True)
class SectionSemanticProfile:
    """章节语义画像。

    Args:
        section_ref: 章节 ref。
        topic: 章节语义 topic。
        path: 章节语义路径。
        title: 章节标题。
        item: 章节 item。
        bucket: 归一化语义桶。
        lexical_tokens: 章节可检索 token。

    Returns:
        无。

    Raises:
        无。
    """

    section_ref: str
    topic: str
    path: str
    title: str
    item: str
    bucket: str
    lexical_tokens: tuple[str, ...]


@dataclass(frozen=True)
class SearchPlan:
    """查询执行计划。

    Args:
        run_exact: 是否执行 exact 阶段。
        expansion_phases: 扩展阶段列表，每一阶段包含多个 expansion。
        fallback_gated: 是否启用了 token fallback gating。
        scoped_before_token: token 阶段前是否先走语义 scoped。

    Returns:
        无。

    Raises:
        无。
    """

    run_exact: bool
    expansion_phases: tuple[tuple[dict[str, str], ...], ...]
    fallback_gated: bool
    scoped_before_token: bool
