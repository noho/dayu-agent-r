"""基于 BeautifulSoup 的 DEF 14A 表单专项处理器。

DEF 14A (Definitive Proxy Statement) 是 SEC 要求上市公司在年度股东大会
前提交的委托投票声明书。典型内容包括：
- 董事选举与董事会治理信息
- 高管薪酬 (Executive Compensation)
- 股权结构 (Security Ownership)
- 审计委员会报告 (Audit Committee Report)
- 股东提案 (Shareholder Proposals)
- 投票程序 (Voting Procedures)
- 问答 (Q&A)

与 ``Def14AFormProcessor``（原始 BS 实现）平行：
- 共享同一套 ``_DEF14A_SECTION_MARKERS`` 关键词和
  ``_select_def14a_proposal_markers()`` Proposal 扫描逻辑；
- **新增 TOC 感知**：自动检测目录页（Table of Contents）区域，跳过 TOC
  条目中的关键词命中，避免在 TOC 区域产生微型虚拟章节；
- 搜索实现 token 级回退，提升治理类文档的搜索召回率。

设计决策：
- DEF 14A 不含 XBRL 标准化财务报表，不需要 XBRL 能力。
- TOC 感知策略：利用 **前导聚簇检测** (leading cluster detection)，
  当连续首批 marker 间距均低于文档长度的 0.5% 时，判定这些 marker 落在了
  目录页区域，随后在目录区域之后重新扫描关键词 marker。
  **支持迭代检测**——TOC 之后可能紧跟投票建议摘要 (vote recommendation
  summary) 等紧密区域，迭代检测会逐层跳过所有前导紧密区域。
  该策略在「TOC 在文档前部」（AAPL/AMZN/META 等）场景下跳过 TOC，
  在「TOC 在文档后部」（TDG 等）场景下保留原始 marker。
- 搜索使用两级回退策略：精确短语匹配 → token OR 匹配。
  DEF 14A 的治理类术语分布与 10-K/10-Q 差异大，token 回退可从局部单词
  匹配中提取上下文 snippet，提高搜索命中率。

SEC 规则依据：
- Securities Exchange Act of 1934, Section 14(a)
- SEC Regulation 14A (17 CFR §240.14a-101, Schedule 14A)
"""

from __future__ import annotations

import re
from typing import Optional

from dayu.documents.processors.source import Source

from .def14a_form_common import (
    _DEF14A_ANNEX_PATTERN,
    _DEF14A_APPENDIX_PATTERN,
    _DEF14A_SECTION_MARKERS,
    _build_def14a_markers,
    _select_def14a_proposal_markers,
)
from .fins_bs_processor import FinsBSProcessor
from .sec_form_section_common import (
    SIGNATURE_PATTERN as _SIGNATURE_PATTERN,
    _VirtualSectionProcessorMixin,
    _check_special_form_support,
    _dedupe_markers,
    _find_lettered_marker_after,
    _find_marker_after,
)

# ---------------------------------------------------------------------------
# DEF 14A 表单类型集合
# ---------------------------------------------------------------------------
_DEF14A_FORMS = frozenset({"DEF 14A"})

# ---------------------------------------------------------------------------
# TOC 感知 — 前导聚簇检测参数
# ---------------------------------------------------------------------------
# 连续 marker 间距阈值：占文档总长的比例（0.5% = 150K 文档中 ~750 chars）
_TOC_CLUSTER_GAP_RATIO = 0.005
# 形成聚簇所需的最小连续 marker 数
_TOC_CLUSTER_MIN_SIZE = 3
# 在聚簇末尾追加的安全偏移量（跳过 TOC 残余行）
_TOC_CLUSTER_SKIP_CHARS = 200
# 迭代聚簇检测上限：TOC 之后可能还有投票建议摘要等紧密区域，需要多轮跳过
_MAX_CLUSTER_ITERATIONS = 3
# ---------------------------------------------------------------------------
# 小节重扫（undersized section rescan）参数
# ---------------------------------------------------------------------------
# 关键词 marker 对应的 section 若不足 min_section 阈值，可能是 TOC 条目匹配
# 而非正文标题——此时应搜索下一次出现并验证 section 大小。
# 策略：逐个尝试关键词的后续匹配（最多 _MAX_RESCAN_ATTEMPTS 次），
# 接受第一个能产生 ≥ 阈值 section 的匹配位置；若全部不满足则保留原位。
# ---------------------------------------------------------------------------
# 默认阈值（大多数关键词适用）
_DEFAULT_RESCAN_THRESHOLD = 500
# 关键词专属阈值——Executive Compensation 的 B_content 评估阈值为 2000，
# 需要 >= 1500 的 section 才能可靠覆盖正文，因此重扫阈值设为 1500。
_RESCAN_THRESHOLDS: dict[str, int] = {
    "Executive Compensation": 1500,
    # Pay Versus Performance 通常在高管薪酬表之后，但部分文档（如 AMZN）的
    # 第一次匹配落在文档前端（目录/摘要），产生 ~10K 的假阳性 section。
    # 20K 阈值确保只接受正文中的实质性 PvP 披露段落。
    "Pay Versus Performance": 20_000,
}
# 每个关键词最多尝试后续匹配的次数
_MAX_RESCAN_ATTEMPTS = 10
# ---------------------------------------------------------------------------
# 补充关键词标记 — 用于拆分超大 section
# ---------------------------------------------------------------------------
# DEF 14A 正文中，_DEF14A_SECTION_MARKERS 的治理关键词之间可能存在巨大的
# 距离（如 AMZN 的 Audit(25K) → Voting(498K) = 473K），导致中间存在一个超大
# section。补充以下 SEC Schedule 14A 标准小节标题，在正文中自然插入分割点。
# SEC 规则依据：
# - Schedule 14A Item 402(b): Compensation Discussion and Analysis (CD&A)
# - Schedule 14A Item 402(c): Summary Compensation Table
# - Schedule 14A Item 402(k): Director Compensation
# - Schedule 14A Item 402(v): Pay Versus Performance（2022 SEC 最终规则要求强制披露）
# - Reg S-K Item 201(d): Equity Compensation Plan Information
# - Schedule 14A Item 403: Security Ownership / Beneficial Ownership
# - Schedule 14A Item 404: Certain Relationships and Related Transactions
_SUPPLEMENTARY_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "Compensation Discussion and Analysis",
        re.compile(r"(?i)\bcompensation discussion and analysis\b"),
    ),
    (
        "Director Compensation",
        re.compile(r"(?i)\bdirector(?:s')? compensation\b"),
    ),
    (
        "Certain Relationships",
        re.compile(r"(?i)\bcertain relationships\b"),
    ),
    # Beneficial Ownership — 很多公司使用此标题而非 "Security Ownership"
    # 原始 _DEF14A_SECTION_MARKERS 只匹配 "security ownership"，
    # 但 AMZN/V/AXON/MSFT 等使用 "beneficial ownership" 作为章节标题。
    # 同时匹配 CI 评分的 section_keyword_map["Security Ownership"] 关键词。
    (
        "Beneficial Ownership",
        re.compile(r"(?i)\bbeneficial ownership\b"),
    ),
    # Pay Versus Performance — SEC 2022 最终规则（Item 402(v) of Reg S-K）
    # 要求强制披露，所有 21 份测试文档均包含此节。
    # 典型位于高管薪酬表后、股权结构前，能有效拆分超大 section。
    (
        "Pay Versus Performance",
        re.compile(r"(?i)\bpay versus performance\b"),
    ),
    # Equity Compensation Plan — Reg S-K Item 201(d)
    # V/AAPL/MSFT 等公司的代理声明中包含此标准披露节。
    # 通常位于 Beneficial Ownership 和 Other Matters 之间，
    # 可有效拆分 Beneficial Ownership 后的超大 section。
    (
        "Equity Compensation Plan",
        re.compile(r"(?i)\bequity compensation plan\b"),
    ),
)
# ---------------------------------------------------------------------------
# 合并关键词集合（原始 + 补充），用于重扫和标题匹配
# ---------------------------------------------------------------------------
_ALL_KEYWORD_MARKERS = _DEF14A_SECTION_MARKERS + _SUPPLEMENTARY_MARKERS
# 关键词 marker 标题集合（Proposal/尾段标记不参与重扫）
_KEYWORD_MARKER_TITLES = frozenset(
    title for title, _ in _ALL_KEYWORD_MARKERS
)
# 关键词标题 → 正则模式映射（用于小节重扫查找下一匹配）
_SECTION_PATTERN_MAP: dict[str, re.Pattern[str]] = {
    title: pattern for title, pattern in _ALL_KEYWORD_MARKERS
}
# Voting Procedures 增强搜索模式：比原始 `_DEF14A_SECTION_MARKERS` 更宽泛
_VOTING_ENHANCED_PATTERN = re.compile(
    r"(?i)\bvoting\s+(?:procedures|information|instructions|matters)\b"
)


class BsDef14AFormProcessor(_VirtualSectionProcessorMixin, FinsBSProcessor):
    """基于 BeautifulSoup 的 DEF 14A 表单专项处理器。

    继承链：
    ``BsDef14AFormProcessor → _VirtualSectionProcessorMixin
    → FinsBSProcessor → BSProcessor``

    与 ``Def14AFormProcessor`` 平行，共享 marker 关键词定义。
    新增 TOC 感知和 token 回退搜索，显著提升治理类文档的 section 切分质量。

    搜索增强：
    - 第一级：精确短语匹配（继承 ``_VirtualSectionProcessorMixin``）。
    - 第二级：token OR 回退——多词查询拆分为 token，任一匹配即命中。
    """

    PARSER_VERSION = "bs_def14a_section_processor_v1.0.0"

    # DEF 14A 至少需要 3 个虚拟章节（治理关键词 + 尾段标记）
    _MIN_VIRTUAL_SECTIONS = 3
    _ENABLE_TOKEN_FALLBACK_SEARCH = True

    def __init__(
        self,
        source: Source,
        *,
        form_type: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> None:
        """初始化处理器。

        Args:
            source: 文档来源抽象。
            form_type: 可选表单类型。
            media_type: 可选媒体类型。

        Returns:
            无。

        Raises:
            ValueError: 参数非法时抛出。
            RuntimeError: 解析失败时抛出。
        """

        super().__init__(source=source, form_type=form_type, media_type=media_type)
        self._initialize_virtual_sections(min_sections=self._MIN_VIRTUAL_SECTIONS)

    @classmethod
    def supports(
        cls,
        source: Source,
        *,
        form_type: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> bool:
        """判断是否支持处理该文件。

        支持条件：表单类型为 DEF 14A，且文件可被 BSProcessor 解析
        （HTML/XML 格式）。

        Args:
            source: 文档来源抽象。
            form_type: 可选表单类型。
            media_type: 可选媒体类型。

        Returns:
            是否支持。

        Raises:
            OSError: 文件访问失败时可能抛出。
        """

        return _check_special_form_support(
            source,
            form_type=form_type,
            media_type=media_type,
            supported_forms=_DEF14A_FORMS,
            base_supports_fn=FinsBSProcessor.supports,
        )

    def _build_markers(self, full_text: str) -> list[tuple[int, Optional[str]]]:
        """构建 DEF 14A 专项边界（带 TOC 感知）。

        策略：
        1. 使用原始 ``_build_def14a_markers()`` 构建初始 marker 集合。
        2. 检测初始 marker 是否形成前导聚簇（TOC 模式）。
        3. 若检测到 TOC 聚簇，在聚簇之后重新扫描 marker。
        4. 若重建结果不优于初始，保留初始 marker。

        Args:
            full_text: 文档全文。

        Returns:
            ``(start_index, title)`` 列表。

        Raises:
            RuntimeError: 构建失败时抛出。
        """

        return _build_bs_def14a_markers(full_text)


# ---------------------------------------------------------------------------
# TOC 感知 marker 构建
# ---------------------------------------------------------------------------


def _build_bs_def14a_markers(
    full_text: str,
) -> list[tuple[int, Optional[str]]]:
    """构建 DEF 14A 专项边界（带 TOC 前导聚簇检测）。

    典型 DEF 14A 文档前部包含目录页 (Table of Contents)，治理关键词
    （"Directors"、"Executive Compensation" 等）在 TOC 条目中首次出现时
    间距极短（< 文档长度的 0.5%），导致 ``pattern.search()`` 命中 TOC
    而非正文标题，产生微型虚拟章节。

    本函数使用前导聚簇检测（支持迭代）+ 小节重扫：
    1. 先用原始逻辑构建初始 marker。
    2. 统计从首个 marker 开始的连续小间距 marker 数量。
    3. 若连续 ≥ 3 个小间距 marker → 判定为 TOC 聚簇。
    4. 在 TOC 聚簇之后重新扫描 marker。
    5. 对重建 marker **再次**进行聚簇检测——如果 TOC 之后紧跟
       投票建议摘要 (vote recommendation summary) 等紧密区域，
       会继续跳过，直到 marker 间距达到正文级别。
    6. 若最终重建 marker 数量不足，保留初始 marker。
    7. **小节重扫**：检查每个关键词 marker 产生的 section 是否过短
       （< 500 chars）；若是，搜索该关键词在文档后续位置的下一次出现，
       用更大的匹配替换，修复「关键词在 TOC 中首次出现」的问题。

    Args:
        full_text: 文档全文。

    Returns:
        标记列表。

    Raises:
        RuntimeError: 构建失败时抛出。
    """

    # Phase 1：使用原始逻辑构建初始 marker + 补充关键词
    initial_markers = _build_def14a_markers(full_text)
    # 追加补充关键词 marker（CD&A、Director Compensation 等）
    initial_markers = _append_supplementary_markers(initial_markers, full_text)
    if len(initial_markers) < _TOC_CLUSTER_MIN_SIZE:
        return initial_markers

    # Phase 2：前导聚簇检测
    toc_end = _detect_leading_toc_cluster(initial_markers, len(full_text))
    if toc_end == 0:
        # 未检测到 TOC 聚簇（如 TDG/MSFT/V），使用初始 marker
        # 但仍需执行 Phase 5 小节重扫
        final_markers = initial_markers
    else:
        # Phase 3：在 TOC 之后重新扫描 marker（迭代检测嵌套聚簇）
        # DEF 14A 文档中，TOC 之后可能紧跟投票建议摘要 (vote recommendation
        # summary)，其中关键词同样密集排列。迭代检测会跳过所有前导紧密区域，
        # 直到 marker 间距达到正文级别。
        body_start = toc_end + _TOC_CLUSTER_SKIP_CHARS
        rebuilt_markers: list[tuple[int, Optional[str]]] = []
        for _ in range(_MAX_CLUSTER_ITERATIONS):
            rebuilt_markers = _rebuild_markers_after_toc(full_text, body_start)
            if len(rebuilt_markers) < _TOC_CLUSTER_MIN_SIZE:
                # 重建 marker 太少，无法再次聚簇检测
                break
            nested_toc_end = _detect_leading_toc_cluster(
                rebuilt_markers, len(full_text)
            )
            if nested_toc_end == 0:
                # 无嵌套聚簇，rebuilt_markers 已是正文级别 marker
                break
            # 还有嵌套聚簇（如投票建议摘要），继续跳过
            body_start = nested_toc_end + _TOC_CLUSTER_SKIP_CHARS

        # Phase 4：安全兜底——若重建结果太少，保留初始 marker
        if len(rebuilt_markers) < _TOC_CLUSTER_MIN_SIZE:
            final_markers = initial_markers
        else:
            final_markers = rebuilt_markers

    # Phase 5：小节重扫——修复关键词 marker 因匹配 TOC 条目产生的微型章节
    # 对于 MSFT/V 等「TOC 在中部」的文档，聚簇检测不会触发（首个 marker 在
    # 致股东信中，与 TOC 区域间距大于阈值）。但 Executive Compensation
    # 等关键词的首次匹配仍可能落在 TOC 行上，导致 section 只有数百字符。
    # 此步骤检查每个关键词 marker 产生的 section 大小：若 < 500 chars，
    # 则在后续文本中搜索该关键词的下一次出现，用更大的匹配替换。
    final_markers = _rescan_undersized_keyword_markers(final_markers, full_text)

    return final_markers


def _append_supplementary_markers(
    markers: list[tuple[int, Optional[str]]],
    full_text: str,
    start_pos: int = 0,
) -> list[tuple[int, Optional[str]]]:
    """向现有 marker 列表追加补充关键词标记。

    在原始 ``_DEF14A_SECTION_MARKERS`` 基础上，追加 CD&A、Director
    Compensation、Certain Relationships 等 SEC 标准小节标题。这些补充标记
    帮助拆分超大 section（>300K chars），改善噪声评分（E_noise）。

    Args:
        markers: 当前 marker 列表（会被修改）。
        full_text: 文档全文。
        start_pos: 搜索起始位置。

    Returns:
        追加后的 marker 列表（已去重排序）。

    Raises:
        无。
    """

    extended = list(markers)
    for title, pattern in _SUPPLEMENTARY_MARKERS:
        match = pattern.search(full_text, pos=start_pos)
        if match is not None:
            extended.append((int(match.start()), title))
    return _dedupe_markers(extended)


def _detect_leading_toc_cluster(
    markers: list[tuple[int, Optional[str]]],
    text_len: int,
) -> int:
    """检测 marker 序列的前导聚簇（TOC 模式）。

    从首个 marker 开始，统计连续间距低于阈值的 marker 数量。
    若连续数量达到 ``_TOC_CLUSTER_MIN_SIZE``，返回聚簇末尾位置；
    否则返回 0 表示未检测到聚簇。

    阈值 = 文档长度 × ``_TOC_CLUSTER_GAP_RATIO``（默认 0.5%）。
    对于典型 300K 文档，阈值约为 1500 字符——TOC 条目间距通常远低于此值，
    而正文 section 间距通常在数千到数万字符。

    Args:
        markers: 标记列表。
        text_len: 文档总长度。

    Returns:
        TOC 聚簇末尾位置；未检测到返回 0。

    Raises:
        RuntimeError: 检测失败时抛出。
    """

    if len(markers) < _TOC_CLUSTER_MIN_SIZE or text_len == 0:
        return 0

    sorted_markers = sorted(markers, key=lambda x: x[0])
    max_gap = int(text_len * _TOC_CLUSTER_GAP_RATIO)
    # 确保最小间距阈值，避免超短文档误判
    max_gap = max(max_gap, 200)

    cluster_count = 1
    for i in range(len(sorted_markers) - 1):
        gap = sorted_markers[i + 1][0] - sorted_markers[i][0]
        if gap < max_gap:
            cluster_count += 1
        else:
            break

    if cluster_count >= _TOC_CLUSTER_MIN_SIZE:
        return sorted_markers[cluster_count - 1][0]

    return 0


def _rebuild_markers_after_toc(
    full_text: str,
    body_start: int,
) -> list[tuple[int, Optional[str]]]:
    """在 TOC 区域之后重新扫描所有 marker。

    扫描顺序：
    1. Proposal No. N 标记
    2. 治理关键词标记（Executive Compensation / Directors / ...）
    3. 尾段标记（Annex / Appendix / SIGNATURE）

    所有搜索均从 ``body_start`` 位置开始，确保跳过 TOC。

    Args:
        full_text: 文档全文。
        body_start: 正文起始位置（TOC 之后）。

    Returns:
        重建的标记列表。

    Raises:
        RuntimeError: 构建失败时抛出。
    """

    markers: list[tuple[int, Optional[str]]] = []

    # 1. Proposal 标记——使用全文扫描后过滤位置
    proposal_markers = _select_def14a_proposal_markers(full_text)
    for proposal_no, position in proposal_markers:
        if position >= body_start:
            markers.append((position, f"Proposal No. {proposal_no}"))

    # 2. 治理关键词标记——从 body_start 开始搜索
    for title, pattern in _DEF14A_SECTION_MARKERS:
        match = pattern.search(full_text, pos=body_start)
        if match is not None:
            markers.append((int(match.start()), title))

    # 2.1 补充关键词标记——拆分超大 section 的辅助分割点
    for title, pattern in _SUPPLEMENTARY_MARKERS:
        match = pattern.search(full_text, pos=body_start)
        if match is not None:
            markers.append((int(match.start()), title))

    # 2.2 增强 Voting Procedures 搜索（原始模式可能遗漏 "voting matters"）
    if not any(title == "Voting Procedures" for _, title in markers):
        match = _VOTING_ENHANCED_PATTERN.search(full_text, pos=body_start)
        if match is not None:
            markers.append((int(match.start()), "Voting Procedures"))

    # 3. 尾段标记——从已识别章节之后开始
    tail_cursor = max((pos for pos, _ in markers), default=body_start)
    annex_marker = _find_lettered_marker_after(
        _DEF14A_ANNEX_PATTERN, full_text, tail_cursor, "Annex"
    )
    appendix_marker = _find_lettered_marker_after(
        _DEF14A_APPENDIX_PATTERN, full_text, tail_cursor, "Appendix"
    )
    signature_marker = _find_marker_after(
        _SIGNATURE_PATTERN, full_text, tail_cursor, "SIGNATURE"
    )
    if annex_marker is not None:
        markers.append(annex_marker)
    if appendix_marker is not None:
        markers.append(appendix_marker)
    if signature_marker is not None:
        markers.append(signature_marker)

    deduped = _dedupe_markers(markers)
    if len(deduped) < _TOC_CLUSTER_MIN_SIZE:
        return []
    return deduped


def _rescan_undersized_keyword_markers(
    markers: list[tuple[int, Optional[str]]],
    full_text: str,
) -> list[tuple[int, Optional[str]]]:
    """对产生微型 section 的关键词 marker 重新搜索更优匹配位置。

    DEF 14A 文档中，治理关键词（"Executive Compensation"、"Directors" 等）
    可能首次出现在 TOC 行或投票建议摘要中，导致 marker 产生的 section
    仅数十到数百字符——远不足以覆盖实际正文内容。

    **扫描-验证策略**（scan-and-validate）：
    1. 计算每个关键词 marker 产生的 section 大小。
    2. 若 section < 关键词专属阈值（默认 500，Executive Compensation
       用 1500），逐个尝试该关键词在文档中的后续匹配。
    3. 对每个后续匹配，计算它与下一个**现有 marker** 之间的距离。
    4. 若距离 ≥ 阈值，接受该匹配位置（说明不是 TOC 条目）。
    5. 若所有后续匹配都无法产生足够大的 section（如每个匹配都紧邻
       另一个 marker），保留原始位置。

    此策略确保：
    - 在 TOC 中首次出现的关键词被跳到正文位置（MSFT/V/AXON）。
    - 已在正文中的关键词不会被误移（TDG 首段 Directors 536 chars
      不触发重扫，因为默认阈值 500 < 536）。
    - 即使触发重扫，后续匹配若紧邻其他 marker（section < 阈值），
      也不会被接受（防止"2 chars section"回退）。

    仅对 ``_KEYWORD_MARKER_TITLES`` 中的标题执行重扫（Proposal / Annex /
    Appendix / SIGNATURE 等结构性标记不参与）。

    Args:
        markers: 当前 marker 列表。
        full_text: 文档全文。

    Returns:
        修正后的 marker 列表。

    Raises:
        RuntimeError: 处理失败时抛出。
    """

    if not markers:
        return markers

    text_len = len(full_text)
    sorted_markers = sorted(markers, key=lambda x: x[0])
    # 预构建所有 marker 位置列表，用于计算后续匹配的 section 大小
    all_positions = sorted(pos for pos, _ in sorted_markers)
    result: list[tuple[int, Optional[str]]] = []

    for i, (pos, title) in enumerate(sorted_markers):
        # 计算当前 marker 到下一 marker 的距离（即 section 大小）
        next_pos = (
            sorted_markers[i + 1][0] if i + 1 < len(sorted_markers) else text_len
        )
        section_size = next_pos - pos

        # 确定此关键词的重扫阈值
        threshold = _RESCAN_THRESHOLDS.get(title, _DEFAULT_RESCAN_THRESHOLD) if title else 0

        # 仅对关键词 marker 且 section < 阈值时执行重扫
        if (
            section_size < threshold
            and title is not None
            and title in _KEYWORD_MARKER_TITLES
        ):
            pattern = _SECTION_PATTERN_MAP.get(title)
            if pattern is not None:
                better_pos = _find_adequate_keyword_match(
                    pattern, full_text, pos, all_positions, threshold
                )
                if better_pos is not None:
                    result.append((better_pos, title))
                    continue

        result.append((pos, title))

    return _dedupe_markers(result)


def _find_adequate_keyword_match(
    pattern: re.Pattern[str],
    full_text: str,
    current_pos: int,
    all_marker_positions: list[int],
    min_section: int,
) -> Optional[int]:
    """在文档中搜索关键词的后续匹配，返回第一个能产生足够大 section 的位置。

    从 ``current_pos + 1`` 开始，逐个尝试 ``pattern`` 的匹配。对每个匹配位置
    计算到下一个现有 marker 的距离（即假设 section 大小）。若距离 ≥
    ``min_section``，返回该位置作为更优匹配。

    最多尝试 ``_MAX_RESCAN_ATTEMPTS`` 次匹配以避免性能问题。

    Args:
        pattern: 关键词的正则模式。
        full_text: 文档全文。
        current_pos: 当前 marker 位置（从此之后开始搜索）。
        all_marker_positions: 所有 marker 位置的有序列表。
        min_section: section 大小下限。

    Returns:
        更优的匹配位置；若未找到返回 None。

    Raises:
        无。
    """

    text_len = len(full_text)
    search_pos = current_pos + 1

    for _ in range(_MAX_RESCAN_ATTEMPTS):
        match = pattern.search(full_text, pos=search_pos)
        if match is None:
            return None

        candidate_pos = int(match.start())
        # 找到 candidate_pos 之后的下一个现有 marker（排除自身原位置）
        next_marker = text_len
        for mp in all_marker_positions:
            if mp > candidate_pos and mp != current_pos:
                next_marker = mp
                break

        candidate_section = next_marker - candidate_pos
        if candidate_section >= min_section:
            return candidate_pos

        # 当前候选产生的 section 太小（可能又是 TOC/摘要），继续搜索
        search_pos = match.end()

    return None


__all__ = ["BsDef14AFormProcessor"]
