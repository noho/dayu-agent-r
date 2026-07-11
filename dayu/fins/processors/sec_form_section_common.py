"""SEC 表单专项章节处理器公共能力。

本模块聚合多个 SEC 表单专项处理器共享的能力，包括：
- 基于全文 marker 的虚拟章节切分混入 `_VirtualSectionProcessorMixin`；
- 文本规范化、章节 ref 生成、marker 去重等通用工具函数；
- 章节列表/读取/搜索的统一行为实现。

说明：
- 本模块仅包含“跨表单可复用”的实现；
- 各表单专属正则与 marker 策略应放在独立 processor 模块中。

维护说明(不拆分本模块):
    本模块虽近 3000 行, 但核心 mixin 与工具函数共同服务于虚拟章节
    切分这一个关注点, 且被 14 个下游处理器模块共同消费. 工具函数间
    存在密集调用链(heading extraction -> line splitting -> title
    normalization -> boundary detection), 拆分只会增加 import 复杂度
    而无法降低耦合.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional, Protocol, cast

from dayu.documents.processors.base import (
    SearchHit,
    SectionContent,
    SectionSummary,
    TableSummary,
)
from dayu.documents.processors.source import Source
from dayu.documents.processors.search_utils import (
    enrich_hits_by_section,
    enrich_hits_by_section_token_or,
)
from dayu.documents.processors.text_utils import (
    PREVIEW_MAX_CHARS as _PREVIEW_MAX_CHARS,
    TABLE_PLACEHOLDER_PATTERN as _TABLE_REF_PATTERN,
    extract_table_refs_from_text as _extract_table_refs,
    format_section_ref as _format_section_ref,
    infer_suffix_from_uri as _infer_suffix_from_uri,
    normalize_optional_string as _normalize_optional_string,
    normalize_whitespace as _normalize_whitespace,
)
from dayu.fins._log import Log
from dayu.fins.domain.filing_semantics import normalize_sec_form_type_for_matching as _parse_section_sec_form
from dayu.fins.processors.sec_processor import SecProcessor

# --- 跨 Form 共享的正则常量 ---

# 签名段标题模式，匹配 "SIGNATURE" 或 "SIGNATURES"（复数）
SIGNATURE_PATTERN = re.compile(r"(?i)\bsignatures?\b")

# SEC 法定 Part 标题模式（用于裁剪 section 尾部 Part 标题残留）
# 参考 SEC Regulation S-K: Part I–IV + 可选法定副标题
# 匹配位于文本末尾的 Part 标题（允许前后空白、可选副标题文本）
_TRAILING_PART_HEADING_RE = re.compile(
    r"\s*"  # 前导空白
    r"PART\s+(?:I{1,3}|IV)\b"  # "PART I" / "PART II" / "PART III" / "PART IV"
    r"(?:"  # 可选法定副标题组
    r"[\s\.\-—–:]*"  # 分隔符
    r"(?:FINANCIAL\s+(?:INFORMATION|STATEMENTS)"
    r"|OTHER\s+INFORMATION"
    r"|FINANCIAL\s+DATA\s+AND\s+SUPPLEMENTARY\s+DATA"
    r"|EXHIBITS(?:\s+AND)?"
    r"|EXHIBITS,?\s+FINANCIAL\s+STATEMENT\s+SCHEDULES"
    r")?"
    r")"
    r"[\s\.]*$",  # 尾部空白/句点直到文本结束
    re.IGNORECASE,
)
# 仅在 section 末尾 N 个字符内搜索，防止误剪正文中的 "Part" 引用
_TRAILING_PART_TRIM_WINDOW = 200
_SHORT_ITEM_SECTION_MAX_CHARS = 400
_SHORT_ITEM_SECTION_MAX_WORDS = 48
_PAGE_LOCATOR_TOKEN_PATTERN = r"(?:[A-Z]-\d{1,3}|\d{1,3})(?:\s*[—–-]\s*(?:[A-Z]-\d{1,3}|\d{1,3}))?"
_PAGE_LOCATOR_TAIL_RE = re.compile(
    rf"(?:\s*(?:,|/|;)?\s*{_PAGE_LOCATOR_TOKEN_PATTERN}){{1,6}}\s*$",
    re.IGNORECASE,
)
_PAGE_LOCATOR_CONTEXT_KEYWORDS = (
    "financial statements",
    "operating and financial review",
    "exhibits",
    "not applicable",
    "table of contents",
    "consolidated financial",
    "see ",
)
_CHILD_REF_WIDTH = 2
_MIN_CHILD_SECTION_CHARS = 80
_CHILD_HEADING_MIN_DISTANCE = 240
_MAX_VIRTUAL_SECTION_LEVEL = 4
_FALLBACK_HEADING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*([A-Z]\.\s+[^\n]{6,120})\s*$", re.MULTILINE),
    re.compile(r"^\s*((?:Note|NOTES?)\s+\d{1,2}[A-Z]?(?:\s*[:\.-]\s*[^\n]{3,120})?)\s*$", re.MULTILINE),
    re.compile(r"^\s*(\d+\.\s+[^\n]{6,120})\s*$", re.MULTILINE),
)
_FALLBACK_INLINE_HEADING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<![A-Za-z0-9\.])([A-Z]\.\s+[A-Z][^\.\n]{6,140})"),
    re.compile(
        r"(?<![A-Za-z0-9])((?:Note|NOTES?)\s+\d{1,2}[A-Z]?(?:\s*[:\.-]\s*[A-Z][^\.\n]{3,160})?)",
        re.IGNORECASE,
    ),
    re.compile(r"(?<![A-Za-z0-9])((?:[1-9]|1[0-9])\.\s+[A-Z][^\.\n]{6,140})"),
)
_INLINE_HEADING_CONTEXT_WINDOW = 96
_INLINE_HEADING_TITLE_MAX_WORDS = 14
_INLINE_HEADING_MAX_DASH_COUNT = 2
_INLINE_HEADING_MIN_WORDS = 2
_INLINE_HEADING_MAX_WORDS = 24
_TITLE_CASE_HEADING_MIN_PARENT_CHARS = 12000
_TITLE_CASE_HEADING_MIN_WORDS = 2
_TITLE_CASE_HEADING_MAX_WORDS = 10
_TITLE_CASE_HEADING_MAX_CHARS = 96
_TITLE_CASE_HEADING_MIN_ALPHA_CHARS = 10
_TITLE_CASE_HEADING_MIN_CAPITALIZED_RATIO = 0.75
_TITLE_CASE_HEADING_LOOKAHEAD_LINES = 6
_TITLE_CASE_HEADING_PROSE_WINDOW = 3
_TITLE_CASE_HEADING_MIN_PROSE_WORDS = 12
_TITLE_CASE_HEADING_ARTIFACT_TITLES = frozenset(
    {
        "table of contents",
    }
)
_FALLBACK_HEADING_TRAILING_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "into",
        "of",
        "on",
        "or",
        "per",
        "the",
        "to",
        "under",
        "upon",
        "with",
    }
)
_FALLBACK_HEADING_CAPITALIZATION_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "into",
        "of",
        "on",
        "or",
        "per",
        "the",
        "to",
        "under",
        "upon",
        "with",
    }
)
_FALLBACK_HEADING_MIN_CAPITALIZED_RATIO = 0.5
_NOTE_HEADING_ALLOWED_PARENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\bfinancial statements?\b"),
    re.compile(r"(?i)\bnotes?\s+to\b"),
    re.compile(r"(?i)\bconsolidated\s+(?:financial\s+)?statements?\b"),
    re.compile(r"(?i)\bselected\s+financial\s+data\b"),
)
_NOTE_HEADING_ALLOWED_CONTENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\bnotes?\s+to\s+(?:the\s+)?consolidated\s+financial\s+statements?\b"),
    re.compile(r"(?i)\bconsolidated\s+financial\s+statements?\b"),
)
_NOTE_HEADING_PARENT_CONTENT_WINDOW = 1600
_REFERENCE_GUIDE_PREFIX_WINDOW = 2600
_REFERENCE_GUIDE_SOURCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\bannual\s+report\b"),
    re.compile(r"(?i)\bannual\s+financial\s+report\b"),
    re.compile(r"(?i)\bintegrated\s+annual\s+report\b"),
    re.compile(r"(?i)\bfurther\s+information\b"),
    re.compile(r"(?i)\bsupplement\b"),
    re.compile(r"(?i)\bgovernance\s+and\s+remuneration\s+report\b"),
    re.compile(r"(?i)\bpresentation\s+of\s+financial\s+and\s+other\s+information\b"),
)
_REFERENCE_GUIDE_NOTE_PATTERN = re.compile(
    r"(?i)\bnote\s+\d{1,2}[a-z]?(?:\.\d+)?\s+"
    r"(?:to\s+each\s+set\s+of\s+)?"
    r"(?:the\s+)?(?:consolidated\s+)?financial\s+statements?\b"
)
_REFERENCE_GUIDE_CODE_PATTERN = re.compile(r"(?i)\b(?:AFR|IAR|GRR)\s+\d{1,3}(?:\s*[—–-]\s*\d{1,3})?\b")
_REFERENCE_GUIDE_PAGE_RANGE_PATTERN = re.compile(
    rf"(?i)\((?:{_PAGE_LOCATOR_TOKEN_PATTERN})" rf"(?:\s*(?:and|,)\s*(?:{_PAGE_LOCATOR_TOKEN_PATTERN}))*\)"
)
_REFERENCE_GUIDE_ACTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\bnot\s+applicable\b"),
    re.compile(r"(?i)\bnothing\s+to\s+disclose\b"),
    re.compile(r"(?i)\bsee\s+also\s+supplement\b"),
    re.compile(r"(?i)\bresponse\s+or\s+location\s+in\s+this\s+(?:filing|document)\b"),
)
_PARENT_DIRECTORY_CONTENT_LIMIT = 280000
_ANCHOR_TITLE_BACKTRACK_CHARS = 120
_ANCHOR_TITLE_LOOKAHEAD_CHARS = 240
_INLINE_REF_CONTEXT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:see|refer to|as discussed in|as described in|please see)\s+[\"“”'(\s-]*item\s+\d+[a-z]?\s*$",
        re.IGNORECASE,
    ),
    re.compile(r"item\s+\d+[a-z]?\.[^\.\n]{0,80}[—–-]\s*$", re.IGNORECASE),
    re.compile(r"item\s+$", re.IGNORECASE),
    # 检测 "Note X" 嵌入正文交叉引用中（如 "See discussion in Note 11 ..."）：
    # context 末尾为 "word in "（有非换行空格），而非换行后的独立标题行。
    re.compile(r"\b\w+\s+in[^\S\n]+$", re.IGNORECASE),
)


@dataclass
class _VirtualSection:
    """虚拟章节结构。"""

    ref: str
    title: Optional[str]
    content: str
    preview: str
    table_refs: list[str]
    level: int = 1
    parent_ref: Optional[str] = None
    child_refs: list[str] = field(default_factory=list)
    start: int = 0
    end: int = 0


@dataclass(frozen=True)
class _StructuredSplitCandidate:
    """用于章节子切分的结构候选项。"""

    title: str
    level: int
    anchor_text: str
    preview: str


class _VirtualSectionBaseProcessorProtocol(Protocol):
    """虚拟章节 mixin 下一跳处理器必须满足的最小协议。"""

    def list_sections(self) -> list[SectionSummary]:
        """返回底层章节摘要列表。"""

        ...

    def read_section(self, ref: str) -> SectionContent:
        """按 ref 读取底层章节内容。"""

        ...

    def list_tables(self) -> list[TableSummary]:
        """返回底层表格摘要列表。"""

        ...

    def get_section_title(self, ref: str) -> Optional[str]:
        """返回底层章节标题。"""

        ...

    def search(self, query: str, within_ref: Optional[str] = None) -> list[SearchHit]:
        """执行底层章节搜索。"""

        ...


class _VirtualSectionTextProviderProtocol(Protocol):
    """虚拟章节 mixin 所需的全文文本提供协议。"""

    def get_full_text(self) -> str:
        """返回文档全文。"""

        ...

    def get_full_text_with_table_markers(self) -> str:
        """返回带表格占位符的文档全文。"""

        ...


class _VirtualDocumentTextLike(Protocol):
    """虚拟章节切分所需的 edgartools 文档文本协议。"""

    def text(self) -> str:
        """读取文档全文。

        Args:
            无。

        Returns:
            文档全文文本。

        Raises:
            RuntimeError: 底层解析失败时可能抛出。
        """

        ...


class _VirtualDocumentOwner(Protocol):
    """持有 edgartools 文档对象的 processor 协议。"""

    _document: _VirtualDocumentTextLike


class _VirtualSectionProcessorMixin:
    """基于全文切分生成虚拟章节的复用混入。"""

    MODULE = "FINS.SEC_FORM_SECTION"

    _virtual_sections: list[_VirtualSection]
    _virtual_section_by_ref: dict[str, _VirtualSection]
    _table_ref_to_virtual_ref: dict[str, str]

    # 子类设为 True 时，search() 在精确匹配无结果后自动启用 token OR 回退。
    # 适用于短文档/非标准化术语的特殊表单（8-K/6-K/DEF 14A/SC 13D 等）。
    _ENABLE_TOKEN_FALLBACK_SEARCH: bool = False

    def _get_base_processor(self) -> _VirtualSectionBaseProcessorProtocol:
        """返回 mixin 在 MRO 中的下一跳处理器协议视图。

        该 mixin 的稳定装配前提是：具体处理器必须按
        ``VirtualSectionMixin -> BaseProcessor`` 的顺序继承，
        使 ``super()`` 下一跳具备标准 section/table/search 接口。

        Args:
            无。

        Returns:
            满足底层处理器协议的下一跳对象。

        Raises:
            RuntimeError: 仅当后续调用方执行底层方法失败时抛出。
        """

        return cast(_VirtualSectionBaseProcessorProtocol, super())

    def _get_text_provider(self) -> _VirtualSectionTextProviderProtocol:
        """返回当前处理器的全文读取协议视图。

        Args:
            无。

        Returns:
            满足全文读取协议的当前处理器对象。

        Raises:
            RuntimeError: 仅当后续调用方执行全文接口失败时抛出。
        """

        return cast(_VirtualSectionTextProviderProtocol, self)

    def _initialize_virtual_sections(self, *, min_sections: int) -> None:
        """初始化虚拟章节。

        优先使用 ``document.text()`` 全文作为切分基底——该文本保持文档原始
        章节顺序，避免因基类 ``_build_sections`` 排序导致 marker 检测顺序
        紊乱（如 Item 1C 被排到文末，cursor 越过 Items 2-15 的已知 bug）。

        若 ``document.text()`` 不可用，回退为拼接基类章节内容。

        Args:
            min_sections: 最小章节数；低于该阈值时回退父类章节。

        Returns:
            无。

        Raises:
            RuntimeError: 构建失败时抛出。
        """

        self._virtual_sections = []
        self._virtual_section_by_ref = {}
        self._table_ref_to_virtual_ref = {}
        # 优先使用 document.text()（保持文档原始顺序），
        # 回退拼接基类章节（兼容 document.text() 不可用场景）。
        full_text = self._collect_document_text()
        if not full_text:
            full_text = self._collect_full_text_from_base()
        if not full_text:
            return
        # 先由子类生成 marker，再统一执行切分，确保各表单行为一致。
        markers = self._build_markers(full_text)
        built_sections = _build_virtual_sections(full_text, markers)
        # marker 数量不足时，回退到父类章节作为一级节点，再尝试结构化子拆分。
        # 典型场景：部分 20-F 文档缺失规范 Item marker，但正文中仍有清晰子标题。
        if len(built_sections) < min_sections:
            built_sections = self._build_virtual_sections_from_base()
        if not built_sections:
            return
        self._virtual_sections = self._expand_virtual_sections_by_structure(built_sections)
        self._virtual_section_by_ref = {section.ref: section for section in self._virtual_sections}
        # 将底层表格分配到虚拟章节（需在虚拟章节构建完成后执行）
        self._assign_tables_to_virtual_sections()
        self._postprocess_virtual_sections(full_text)

    def _postprocess_virtual_sections(self, full_text: str) -> None:
        """对子类已构建的虚拟章节做可选后处理。

        默认实现为空操作。专项表单处理器可覆写该钩子，在不改变
        marker 骨架的前提下修正章节正文内容，例如：
        - 将目录页标题 stub 替换为真正正文；
        - 将 ``incorporated by reference`` 包装句扩展为同文档内被引用正文。

        Args:
            full_text: 用于构建虚拟章节的完整文本。

        Returns:
            无。

        Raises:
            RuntimeError: 后处理失败时抛出。
        """

        del full_text

    def _expand_virtual_sections_by_structure(
        self,
        sections: list[_VirtualSection],
    ) -> list[_VirtualSection]:
        """基于底层结构信息扩展虚拟章节为层级树。

        Args:
            sections: 一级虚拟章节列表。

        Returns:
            扩展后的虚拟章节列表（包含父/子节点，按文档顺序展开）。

        Raises:
            RuntimeError: 扩展失败时抛出。
        """

        candidates = self._collect_structured_split_candidates()
        candidates_by_level = _group_structured_candidates_by_level(candidates)

        expanded: list[_VirtualSection] = []
        for section in sections:
            expanded.extend(
                self._expand_section_tree(
                    section,
                    candidates=candidates,
                    candidates_by_level=candidates_by_level,
                )
            )
        return expanded

    def _collect_structured_split_candidates(self) -> list[_StructuredSplitCandidate]:
        """收集结构化切分候选项。

        候选项来自底层处理器章节树（`super().list_sections()`），
        不依赖字符阈值，仅依赖结构信号。该实现避免对底层章节执行
        全量 `read_section`，降低大文档下的初始化开销。

        Args:
            无。

        Returns:
            候选项列表（按底层章节顺序）。
        """

        try:
            base_sections = self._get_base_processor().list_sections()
        except Exception as exc:
            Log.warn(
                f"_collect_structured_split_candidates: 行基类 list_sections 失败，返回空列表: {exc}",
                module=self.MODULE,
            )
            return []

        candidates: list[_StructuredSplitCandidate] = []
        for section in base_sections:
            title = _normalize_optional_string(section.get("title"))
            if title is None:
                continue
            try:
                level = max(1, int(section.get("level", 1)))
            except Exception:
                level = 1
            if level <= 1:
                continue
            preview = _normalize_optional_string(section.get("preview")) or ""
            section_ref = _normalize_optional_string(section.get("ref"))
            anchor_text = self._build_structured_split_anchor(
                section_ref=section_ref,
                title=title,
                preview=preview,
            )
            if anchor_text is None:
                continue
            candidates.append(
                _StructuredSplitCandidate(
                    title=title,
                    level=level,
                    anchor_text=anchor_text,
                    preview=preview,
                )
            )
        return candidates

    def _build_virtual_sections_from_base(self) -> list[_VirtualSection]:
        """从父类章节构建一级虚拟章节。

        该路径用于 marker 切分不足时的降级初始化，保证后续仍可执行
        fallback 子标题拆分逻辑。

        Args:
            无。

        Returns:
            一级虚拟章节列表。

        Raises:
            RuntimeError: 构建失败时抛出。
        """

        try:
            base_sections = self._get_base_processor().list_sections()
        except Exception as exc:
            Log.warn(
                f"_build_virtual_sections_from_base: 行基类 list_sections 失败，返回空列表: {exc}", module=self.MODULE
            )
            return []

        virtual_sections: list[_VirtualSection] = []
        for index, base_section in enumerate(base_sections, start=1):
            ref = _normalize_optional_string(base_section.get("ref")) or _format_section_ref(index)
            title = _normalize_optional_string(base_section.get("title"))
            preview = _normalize_optional_string(base_section.get("preview")) or ""
            level_raw = base_section.get("level", 1)
            parent_ref = _normalize_optional_string(base_section.get("parent_ref"))
            try:
                level = max(1, int(level_raw))
            except Exception:
                level = 1
            try:
                payload = self._get_base_processor().read_section(ref)
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            content = str(payload.get("content", "") or "").strip()
            table_refs_raw = payload.get("tables")
            table_refs = (
                [str(item) for item in table_refs_raw if _normalize_optional_string(item) is not None]
                if isinstance(table_refs_raw, list)
                else []
            )
            if not content:
                continue
            content = _trim_trailing_part_heading(content)
            content = _trim_trailing_page_locator(content, title)
            if not preview:
                preview = _normalize_whitespace(content)[:_PREVIEW_MAX_CHARS]
            virtual_sections.append(
                _VirtualSection(
                    ref=ref,
                    title=title,
                    content=content,
                    preview=preview,
                    table_refs=table_refs,
                    level=level,
                    parent_ref=parent_ref,
                    child_refs=[],
                    start=0,
                    end=len(content),
                )
            )
        return virtual_sections

    def _build_structured_split_anchor(
        self,
        *,
        section_ref: str | None,
        title: str,
        preview: str,
    ) -> Optional[str]:
        """构建用于定位子章节的锚文本。

        Args:
            section_ref: 底层章节 ref。
            title: 底层章节标题。
            preview: 底层章节预览。

        Returns:
            锚文本；无法构建时返回 `None`。
        """

        normalized_preview = _normalize_whitespace(preview)
        if section_ref is None:
            return None
        # 优先使用 preview 作为锚点，避免触发底层 read_section 渲染成本。
        for candidate in (normalized_preview, title):
            if len(candidate) >= 16:
                return candidate[:160]
        return None

    def _expand_section_tree(
        self,
        section: _VirtualSection,
        *,
        candidates: list[_StructuredSplitCandidate],
        candidates_by_level: dict[int, list[tuple[int, _StructuredSplitCandidate]]],
    ) -> list[_VirtualSection]:
        """递归扩展单个章节为树结构。

        Args:
            section: 待扩展章节。
            candidates: 全局结构候选项。
            candidates_by_level: 候选项按标题层级分桶后的映射。

        Returns:
            展开的节点列表（父节点在前，后接所有后代）。

        Raises:
            RuntimeError: 扩展失败时抛出。
        """

        if section.level >= _MAX_VIRTUAL_SECTION_LEVEL:
            return [section]

        direct_children = _build_child_sections_from_candidates(
            parent_section=section,
            candidates=candidates,
            candidates_by_level=candidates_by_level,
        )
        if len(direct_children) < 2:
            return [section]

        section.child_refs = [child.ref for child in direct_children]
        section.table_refs.clear()
        if len(section.content) > _PARENT_DIRECTORY_CONTENT_LIMIT:
            section.content = _build_parent_directory_content(section=section, children=direct_children)
        section.preview = _normalize_whitespace(section.content)[:_PREVIEW_MAX_CHARS]

        expanded: list[_VirtualSection] = [section]
        for child in direct_children:
            expanded.extend(
                self._expand_section_tree(
                    child,
                    candidates=candidates,
                    candidates_by_level=candidates_by_level,
                )
            )
        return expanded

    def _collect_document_text(self) -> str:
        """通过 ``get_full_text()`` 协议方法获取文档完整全文。

        ``get_full_text()`` 是 ``DocumentProcessor`` 协议的标准能力，
        SecProcessor 和 BSProcessor 各自提供实现：
        - SecProcessor: 委托 edgartools ``document.text()``；
        - BSProcessor: 使用 BeautifulSoup ``root.get_text()``。

        两者都会保留表格内文本，确保虚拟章节 marker 检测准确。

        Args:
            无。

        Returns:
            文档全文字符串；不可用时返回空字符串。

        Raises:
            RuntimeError: 读取失败时抛出。
        """

        try:
            return self._get_text_provider().get_full_text()
        except Exception:
            return ""

    def _collect_full_text_from_base(self) -> str:
        """从父类章节读取拼接全文。

        Args:
            无。

        Returns:
            拼接后的全文字符串。

        Raises:
            RuntimeError: 读取失败时抛出。
        """

        base_sections = self._get_base_processor().list_sections()
        parts: list[str] = []
        for section in base_sections:
            ref = _normalize_optional_string(section.get("ref"))
            if ref is None:
                continue
            payload = self._get_base_processor().read_section(ref)
            content = str(payload.get("content", "") or "").strip()
            if content:
                parts.append(content)
        return "\n".join(parts).strip()

    def _collect_marked_text(self) -> str:
        """获取带 ``[[t_XXXX]]`` 占位符的全文。

        调用 ``DocumentProcessor`` 协议声明的
        ``get_full_text_with_table_markers()`` 方法。
        不支持该能力的处理器返回空字符串（协议约定），上层安全降级。

        Args:
            无。

        Returns:
            带表格占位符的全文；处理器不支持时返回空字符串。
        """

        try:
            return self._get_text_provider().get_full_text_with_table_markers()
        except Exception:
            return ""

    def _collect_available_table_refs_from_base(self) -> Optional[set[str]]:
        """读取底层处理器可用的表格引用集合。

        该集合用于在虚拟章节分配阶段过滤“仅存在于标记文本、但底层
        ``list_tables()`` 未产出”的表格引用，避免 ``read_section.tables``
        出现悬挂 ``table_ref``。

        Returns:
            可用表格引用集合；无法安全获取时返回 ``None``（表示不做过滤）。

        Raises:
            无。内部异常统一吞掉并降级为 ``None``。
        """

        try:
            base_tables = self._get_base_processor().list_tables()
        except Exception:
            return None
        refs: set[str] = set()
        for table in base_tables:
            ref = _normalize_optional_string(table.get("table_ref"))
            if ref is not None:
                refs.add(ref)
        return refs

    def _assign_tables_to_virtual_sections(self) -> None:
        """将底层表格分配到虚拟章节。

        通过在带 ``[[t_XXXX]]`` 占位符的全文中重新检测 marker 边界，
        确定每个占位符落入哪个虚拟章节范围，从而建立双向映射：

        1. 更新每个虚拟章节的 ``table_refs``（解决 ``read_section.tables``
           为空的问题——方向 A）；
        2. 构建 ``_table_ref_to_virtual_ref`` 反向映射，供 ``list_tables()``
           重写 ``section_ref``（解决悬挂引用问题——方向 B）。

        分配策略分两阶段：

        - **Phase 1（标题匹配）**：在标记文本中重新运行 ``_build_markers``
          检测 marker 边界，按标题精确匹配虚拟章节，将对应范围内的
          ``[[t_XXXX]]`` 分配到匹配的虚拟章节。
        - **Phase 2（位置回退）**：Phase 1 中未分配的 ``[[t_XXXX]]``
          （通常因标记文本与原文产生了不同的 marker 标题——如 Proposal
          编号在有/无表格内容时匹配不同），按位置回退分配到最近的前驱
          已匹配虚拟章节边界。

        位置回退确保即使 ``_build_markers`` 在标记文本上产生不同标题
        （TOC 检测阈值、重扫逻辑受 ``[[t_XXXX]]`` 占位符插入的位移
        影响），所有表格仍能映射到虚拟章节，彻底消除悬挂引用。

        降级策略：若底层处理器未提供带标记全文，或标记文本中检测到的
        marker 标题无法匹配虚拟章节标题，则跳过分配（保持现有行为）。

        Args:
            无。

        Returns:
            无。
        """

        if not self._virtual_sections:
            return

        marked_text = self._collect_marked_text()
        if not marked_text:
            return

        for section in self._virtual_sections:
            section.table_refs.clear()
        self._table_ref_to_virtual_ref.clear()
        available_table_refs = self._collect_available_table_refs_from_base()

        top_sections = [section for section in self._virtual_sections if section.parent_ref is None]
        top_section_by_ref = {section.ref: section for section in top_sections}
        if not top_sections:
            return

        # 在标记文本中重新检测 marker，按标题匹配虚拟章节
        marked_markers = self._build_markers(marked_text)
        title_ranges = _build_marker_title_ranges(marked_text, marked_markers)
        if not title_ranges:
            return

        # Cover Page 的范围：第一个 marker 之前的全部文本
        deduped_marked = _dedupe_markers(marked_markers)
        cover_end = deduped_marked[0][0] if deduped_marked else len(marked_text)

        # ----- Phase 1: 标题精确匹配 -----
        for vs in top_sections:
            if vs.title == "Cover Page":
                segment = marked_text[:cover_end]
            elif vs.title in title_ranges:
                start, end = title_ranges[vs.title]
                segment = marked_text[start:end]
            else:
                # 标题未匹配（Proposal 编号差异、SIGNATURE 未检测到等），跳过
                continue
            tbl_refs = _filter_table_refs_by_availability(
                _extract_table_refs(segment),
                available_table_refs,
            )
            # frozen dataclass 但 list 是可变对象，可就地更新
            vs.table_refs.clear()
            vs.table_refs.extend(tbl_refs)
            for tbl_ref in tbl_refs:
                self._table_ref_to_virtual_ref[tbl_ref] = vs.ref

        # ----- Phase 2: 位置回退——分配 Phase 1 未覆盖的表格 -----
        # 构建已匹配虚拟章节在标记文本中的有序边界列表
        _assign_unmapped_tables_by_position(
            marked_text=marked_text,
            title_ranges=title_ranges,
            cover_end=cover_end,
            virtual_sections=top_sections,
            virtual_section_by_ref=top_section_by_ref,
            table_ref_to_virtual_ref=self._table_ref_to_virtual_ref,
            available_table_refs=available_table_refs,
        )

        # 若存在子章节，按“最深命中”规则重分配
        if any(section.child_refs for section in top_sections):
            _remap_tables_to_deepest_virtual_sections(
                marked_text=marked_text,
                title_ranges=title_ranges,
                cover_end=cover_end,
                virtual_sections=top_sections,
                virtual_section_by_ref=self._virtual_section_by_ref,
                table_ref_to_virtual_ref=self._table_ref_to_virtual_ref,
            )

    def list_tables(self) -> list[TableSummary]:
        """读取表格列表，重映射 ``section_ref`` 到虚拟章节。

        当虚拟章节未启用时，直接透传底层表格列表。启用后：

        1. 若 ``table_ref`` 已命中 ``_table_ref_to_virtual_ref``，直接使用该映射；
        2. 否则若底层 ``section_ref`` 已是虚拟章节 ref，直接保留；
        3. 否则回退到“最近一次已确认的虚拟章节 ref”（初值为第一个虚拟章节），
           确保 ``section_ref`` 不会悬挂到虚拟章节集合之外。

        Args:
            无。

        Returns:
            表格摘要列表。

        Raises:
            RuntimeError: 读取失败时抛出。
        """

        if not self._virtual_sections:
            return self._get_base_processor().list_tables()
        tables = self._get_base_processor().list_tables()
        if not tables:
            return tables

        valid_virtual_refs = {section.ref for section in self._virtual_sections}
        fallback_ref = self._virtual_sections[0].ref if self._virtual_sections else None
        last_known_ref = fallback_ref

        for table in tables:
            tbl_ref = _normalize_optional_string(table.get("table_ref"))
            if tbl_ref and tbl_ref in self._table_ref_to_virtual_ref:
                mapped_ref = self._table_ref_to_virtual_ref[tbl_ref]
                table["section_ref"] = mapped_ref
                last_known_ref = mapped_ref
                continue

            current_ref = _normalize_optional_string(table.get("section_ref"))
            if current_ref is not None and current_ref in valid_virtual_refs:
                last_known_ref = current_ref
                continue

            if last_known_ref is not None:
                table["section_ref"] = last_known_ref
        return tables

    def list_sections(self) -> list[SectionSummary]:
        """读取章节列表。

        Args:
            无。

        Returns:
            章节摘要列表。

        Raises:
            RuntimeError: 读取失败时抛出。
        """

        if not self._virtual_sections:
            return self._get_base_processor().list_sections()
        return [
            {
                "ref": section.ref,
                "title": section.title,
                "level": section.level,
                "parent_ref": section.parent_ref,
                "preview": section.preview,
            }
            for section in self._virtual_sections
        ]

    def get_section_title(self, ref: str) -> Optional[str]:
        """根据 section ref 获取章节标题。

        虚拟章节优先查 ``_virtual_section_by_ref``，无虚拟章节时回退父类。

        Args:
            ref: 章节引用。

        Returns:
            章节标题字符串；ref 不存在时返回 None。
        """
        if not self._virtual_sections:
            return self._get_base_processor().get_section_title(ref)
        section = self._virtual_section_by_ref.get(ref)
        return section.title if section else None

    def read_section(self, ref: str) -> SectionContent:
        """按 ref 读取章节内容。

        Args:
            ref: 章节引用。

        Returns:
            章节内容。

        Raises:
            KeyError: 章节不存在时抛出。
            RuntimeError: 读取失败时抛出。
        """

        if not self._virtual_sections:
            return self._get_base_processor().read_section(ref)
        section = self._virtual_section_by_ref.get(ref)
        if section is None:
            raise KeyError(f"章节不存在: {ref}")
        children_payload: list[SectionSummary] = [
            {
                "ref": child.ref,
                "title": child.title,
                "level": child.level,
                "parent_ref": section.ref,
                "preview": child.preview,
            }
            for child_ref in section.child_refs
            for child in [self._virtual_section_by_ref.get(child_ref)]
            if child is not None
        ]
        return {
            "ref": section.ref,
            "title": section.title,
            "content": section.content,
            "tables": list(section.table_refs),
            "word_count": len(section.content.split()),
            "children": children_payload,
            "contains_full_text": len(self._virtual_sections) == 1 and not section.child_refs,
        }

    def search(self, query: str, within_ref: Optional[str] = None) -> list[SearchHit]:
        """在文档中搜索。

        两级搜索策略：
        1. 精确短语正则匹配（标准行为）；
        2. 若 ``_ENABLE_TOKEN_FALLBACK_SEARCH`` 为 True 且精确匹配无结果，
           自动启用 token OR 回退，提升短文档的搜索召回率。

        Args:
            query: 搜索词。
            within_ref: 可选章节范围。

        Returns:
            命中列表。

        Raises:
            RuntimeError: 搜索失败时抛出。
        """

        if not self._virtual_sections:
            return self._get_base_processor().search(query=query, within_ref=within_ref)
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return []
        if within_ref is not None and within_ref not in self._virtual_section_by_ref:
            return []

        target_sections = (
            [self._virtual_section_by_ref[within_ref]] if within_ref is not None else self._virtual_sections
        )
        hits_raw: list[SearchHit] = []
        section_content_map: dict[str, str] = {}
        # 循环外预编译正则，避免 re.search(re.escape(...)) 的重复编译/dict 查找开销
        query_pattern = re.compile(re.escape(normalized_query), flags=re.IGNORECASE)
        for section in target_sections:
            title_text = section.title or ""
            title_hit = bool(title_text) and query_pattern.search(title_text) is not None
            content_hit = query_pattern.search(section.content) is not None
            if not title_hit and not content_hit:
                continue
            # 若 title 命中而 content 无命中，将 title 前置进搜索文本，确保 snippet 能定位到匹配词。
            searchable_text = (
                (title_text + "\n" + section.content).strip() if title_hit and not content_hit else section.content
            )
            # enrich_hits_by_section 需要完整章节文本用于生成上下文 snippet。
            section_content_map[section.ref] = searchable_text
            hits_raw.append(
                {
                    "section_ref": section.ref,
                    "section_title": section.title,
                    "snippet": normalized_query,
                }
            )
        exact_hits = enrich_hits_by_section(
            hits_raw=hits_raw,
            section_content_map=section_content_map,
            query=normalized_query,
        )
        if exact_hits or not self._ENABLE_TOKEN_FALLBACK_SEARCH:
            return exact_hits
        # token OR 回退：将查询拆分为单词，每个单词独立匹配
        return _token_fallback_search(
            query=normalized_query,
            virtual_sections=self._virtual_sections,
            virtual_section_by_ref=self._virtual_section_by_ref,
            within_ref=within_ref,
        )

    def _build_markers(self, full_text: str) -> list[tuple[int, Optional[str]]]:
        """构建章节边界标记。

        Args:
            full_text: 文档全文。

        Returns:
            `(start_index, title)` 列表。

        Raises:
            RuntimeError: 构建失败时抛出。
        """

        raise NotImplementedError("子类必须实现 _build_markers")


def _find_marker_after(
    pattern: re.Pattern[str],
    full_text: str,
    start_at: int,
    title: str,
) -> Optional[tuple[int, Optional[str]]]:
    """在指定位置之后查找首个边界标记。

    Args:
        pattern: 正则模式。
        full_text: 文档全文。
        start_at: 起始位置。
        title: 标记标题。

    Returns:
        `(start_index, title)` 或 `None`。

    Raises:
        RuntimeError: 查找失败时抛出。
    """

    match = pattern.search(full_text, pos=max(0, start_at))
    if match is None:
        return None
    return int(match.start()), title


def _find_lettered_marker_after(
    pattern: re.Pattern[str],
    full_text: str,
    start_at: int,
    title_prefix: str,
) -> Optional[tuple[int, Optional[str]]]:
    """在指定位置之后查找带字母后缀的边界标记。

    例如：`Annex A`、`Appendix B`。

    Args:
        pattern: 正则模式（第一个捕获组应为字母后缀）。
        full_text: 文档全文。
        start_at: 起始位置。
        title_prefix: 标题前缀。

    Returns:
        `(start_index, title)` 或 `None`。

    Raises:
        RuntimeError: 查找失败时抛出。
    """

    match = pattern.search(full_text, pos=max(0, start_at))
    if match is None:
        return None
    suffix = _normalize_optional_string(match.group(1))
    if suffix is None:
        return int(match.start()), title_prefix
    return int(match.start()), f"{title_prefix} {suffix.upper()}"


def _safe_virtual_document_text(processor: _VirtualDocumentOwner) -> str:
    """安全读取专项切分可用的文档全文文本。

    Args:
        processor: 专项处理器实例。

    Returns:
        标准化后的全文文本；读取失败时返回空字符串。

    Raises:
        RuntimeError: 读取失败时抛出。
    """

    try:
        text = processor._document.text()
    except Exception:
        return ""
    return _normalize_whitespace(str(text or ""))


def _is_table_placeholder_dominant_text(
    content: str,
    *,
    min_placeholders: int = 3,
    max_non_placeholder_chars: int = 400,
) -> bool:
    """判断文本是否被表格占位符主导。

    Args:
        content: 待判定文本。
        min_placeholders: 判定为占位符主导所需的最小占位符数量。
        max_non_placeholder_chars: 去除占位符后的正文最大字符阈值。

    Returns:
        若文本几乎只剩占位符则返回 `True`，否则返回 `False`。

    Raises:
        RuntimeError: 判定失败时抛出。
    """

    normalized = _normalize_whitespace(content)
    if not normalized:
        return False
    placeholders = _TABLE_REF_PATTERN.findall(normalized)
    if len(placeholders) < min_placeholders:
        return False
    non_placeholder = _normalize_whitespace(_TABLE_REF_PATTERN.sub(" ", normalized))
    return len(non_placeholder) <= max_non_placeholder_chars


# 自适应 Cover Page 截断模式：匹配 "Table of Contents" 及其变体
_TOC_BOUNDARY_PATTERN = re.compile(
    r"\btable\s+of\s+contents\b",
    re.IGNORECASE,
)

# Cover Page 最大保留字符数上限（自适应，当无 TOC 标记时使用）
_COVER_PAGE_MAX_CHARS = 5000


def _trim_cover_page_content(prefix_content: str) -> str:
    """自适应收紧 Cover Page 内容边界。

    两层策略：

    1. 若前缀文本中存在 "Table of Contents" 标记，截断到该标记位置
       （TOC 之后的内容属于正文章节，不是封面）。
    2. 若无 TOC 标记，限制最大长度为 ``_COVER_PAGE_MAX_CHARS``
       以防止 Cover Page 包含过多正文。

    Args:
        prefix_content: 原始前缀文本（第一个 marker 之前的内容）。

    Returns:
        收紧后的 Cover Page 内容。

    Raises:
        RuntimeError: 处理失败时抛出。
    """
    if not prefix_content:
        return prefix_content

    # 策略 1: 在 TOC 标记处截断
    toc_match = _TOC_BOUNDARY_PATTERN.search(prefix_content)
    if toc_match is not None:
        # 包含 "Table of Contents" 全文，截断到其末尾
        return prefix_content[: toc_match.end()].strip()

    # 策略 2: 无 TOC 标记时限制最大长度
    if len(prefix_content) > _COVER_PAGE_MAX_CHARS:
        return prefix_content[:_COVER_PAGE_MAX_CHARS].strip()

    return prefix_content


def _strip_leading_title(content: str, title: Optional[str]) -> str:
    """自适应去除 content 开头与 title 重复的标题文本。

    虚拟章节的 content 以 marker 起始位置切分，因此正文开头通常包含
    标题文字（如 ``Item 7. Management's Discussion``）。
    而 ``title`` 字段已单独携带此信息，无需在 content 中重复。

    自适应匹配策略：

    1. 尝试整体前缀匹配（如 title="SIGNATURE" → content 以 "SIGNATURE" 开头）。
    2. 对复合标题（如 ``"Part II - Item 7"``），尝试匹配第二段
       （如 content 以 ``"Item 7."`` 开头）。

    Args:
        content: 章节原始内容。
        title: 章节标题。

    Returns:
        去除开头标题的内容文本；若无法匹配则原样返回。

    Raises:
        RuntimeError: 处理失败时抛出。
    """
    if not content or not title:
        return content

    content_lower = content.lower()
    title_lower = title.strip().lower()

    # 策略 1: 直接前缀匹配
    if content_lower.startswith(title_lower):
        remainder = content[len(title) :].lstrip(" .:;-\n\r\t")
        return remainder if remainder else content

    # 策略 2: 复合标题（如 "Part II - Item 7"），试匹配后半段
    if " - " in title:
        item_part = title.split(" - ", 1)[1].strip()
        item_part_lower = item_part.lower()
        if content_lower.startswith(item_part_lower):
            remainder = content[len(item_part) :].lstrip(" .:;-\n\r\t")
            return remainder if remainder else content

    return content


def _trim_trailing_part_heading(content: str) -> str:
    """裁剪 section 尾部残留的 Part 标题文本。

    SEC 文档按 Item heading 切分 section 时，Item N 与 Item N+1 之间
    可能夹杂 Part 标题（如 "PART II"、"PART III — OTHER INFORMATION"），
    这些结构标记不属于 Item N 的实质内容。

    仅在末尾 ``_TRAILING_PART_TRIM_WINDOW`` 字符范围内执行正则搜索，
    避免误剪正文中的 "Part" 引用。

    依据 SEC Regulation S-K §229.10(c)：Part 标题是法定格式结构标记，
    裁剪不影响信息完整性。

    Args:
        content: 章节内容文本。

    Returns:
        裁剪后的内容；若无匹配则原样返回。

    Raises:
        RuntimeError: 处理失败时抛出。
    """
    if not content:
        return content

    # 仅在尾部窗口内搜索（若内容短于窗口大小则搜索全文）
    window = min(_TRAILING_PART_TRIM_WINDOW, len(content))
    tail = content[-window:]
    match = _TRAILING_PART_HEADING_RE.search(tail)
    if match is None:
        return content

    # 计算在原始 content 中的裁剪位置
    trim_start_in_tail = match.start()
    trim_start = len(content) - window + trim_start_in_tail
    trimmed = content[:trim_start].rstrip()
    return trimmed if trimmed else content


def _trim_trailing_page_locator(content: str, title: Optional[str]) -> str:
    """裁剪短 Item 章节尾部的页码定位符噪声。

    部分 iXBRL/HTML 在文本抽取后会把目录行压平成正文片段，形成：
    ``Financial Statements F-1``、``See ... 163`` 等尾部页码定位符。
    这些定位符会触发 ToC 污染误判，但不提供实质语义信息。

    为避免误剪真实数字，本规则仅在“短 Item 章节 + 命中语义关键词”
    的条件下启用，并且仅剥离尾部页码 token 序列。

    Args:
        content: 章节内容文本。
        title: 章节标题。

    Returns:
        裁剪后的章节文本；若不满足条件则原样返回。

    Raises:
        RuntimeError: 处理失败时抛出。
    """

    if not content or not title:
        return content
    normalized_title = _normalize_optional_string(title) or ""
    if "item" not in normalized_title.lower():
        return content

    normalized_content = _normalize_whitespace(content)
    if not normalized_content:
        return content
    if len(normalized_content) > _SHORT_ITEM_SECTION_MAX_CHARS:
        return content
    if len(normalized_content.split()) > _SHORT_ITEM_SECTION_MAX_WORDS:
        return content

    lowered_content = normalized_content.lower()
    if not any(keyword in lowered_content for keyword in _PAGE_LOCATOR_CONTEXT_KEYWORDS):
        return content

    match = _PAGE_LOCATOR_TAIL_RE.search(normalized_content)
    if match is None:
        return content
    trimmed = normalized_content[: match.start()].rstrip(" .:;,-")
    if len(trimmed) < 8:
        return content
    return trimmed


def _build_virtual_sections(
    full_text: str,
    markers: list[tuple[int, Optional[str]]],
) -> list[_VirtualSection]:
    """按标记切分虚拟章节。

    Args:
        full_text: 文档全文。
        markers: 边界标记。

    Returns:
        虚拟章节列表。

    Raises:
        RuntimeError: 切分失败时抛出。
    """

    if not full_text:
        return []
    normalized_markers = _dedupe_markers(markers)
    if not normalized_markers:
        return []

    sections: list[_VirtualSection] = []
    first_start = normalized_markers[0][0]
    if first_start > 0:
        prefix_content = full_text[:first_start].strip()
        # Step 9: 自适应收紧 Cover Page 边界
        # 若前缀文本包含 Table of Contents，截断到该位置为止
        # （TOC 之后的文本实际属于正文，不是封面）
        prefix_content = _trim_cover_page_content(prefix_content)
        if _has_meaningful_text(prefix_content):
            # 第一个 marker 前若有有效正文，则保留为封面段，避免信息丢失。
            sections.append(
                _VirtualSection(
                    ref=_format_section_ref(1),
                    title="Cover Page",
                    content=prefix_content,
                    preview=_normalize_whitespace(prefix_content)[:_PREVIEW_MAX_CHARS],
                    table_refs=_extract_table_refs(prefix_content),
                    start=0,
                    end=first_start,
                )
            )

    next_index = len(sections) + 1
    for marker_index, (start, title) in enumerate(normalized_markers):
        end = normalized_markers[marker_index + 1][0] if marker_index + 1 < len(normalized_markers) else len(full_text)
        content = full_text[start:end].strip()
        allow_short = _allow_short_section(title)
        # 尾段章节（如 SIGNATURE）允许更短文本，其余章节保持较高信息密度阈值。
        min_len = 8 if allow_short else 24
        # 先判断原始 content 是否有意义（含标题文本），再剥离标题
        if not _has_meaningful_text(content, min_len=min_len):
            continue
        # Step 11: 去掉 content 开头的标题文本，避免 title/content 冗余
        content = _strip_leading_title(content, title)
        # Step 12: 裁剪 content 尾部残留的 Part 标题（如 "PART II"、"PART III"）
        # 这些法定结构标记不属于本 section 的实质内容
        content = _trim_trailing_part_heading(content)
        # Step 13: 裁剪短 Item 章节尾部页码定位符（目录压平噪声）。
        content = _trim_trailing_page_locator(content, title)
        sections.append(
            _VirtualSection(
                ref=_format_section_ref(next_index),
                title=title,
                content=content,
                preview=_normalize_whitespace(content)[:_PREVIEW_MAX_CHARS],
                table_refs=_extract_table_refs(content),
                start=start,
                end=end,
            )
        )
        next_index += 1
    return sections


def _build_child_sections_from_candidates(
    *,
    parent_section: _VirtualSection,
    candidates: list[_StructuredSplitCandidate],
    candidates_by_level: Optional[dict[int, list[tuple[int, _StructuredSplitCandidate]]]] = None,
) -> list[_VirtualSection]:
    """根据结构候选项构建直接子章节。

    Args:
        parent_section: 父章节。
        candidates: 全局结构候选项。
        candidates_by_level: 可选候选项分桶，用于减少全量扫描。

    Returns:
        直接子章节列表；无法可靠拆分时返回空列表。

    Raises:
        RuntimeError: 构建失败时抛出。
    """

    if parent_section.title == "Cover Page":
        return []
    parent_text = str(parent_section.content or "")
    if not _has_meaningful_text(parent_text, min_len=_MIN_CHILD_SECTION_CHARS * 2):
        return []
    if _looks_like_reference_guide_content(
        title=parent_section.title,
        content=parent_text,
    ):
        return []

    required_level = parent_section.level + 1
    normalized_parent = parent_text.lower()
    allow_note_headings = _parent_context_allows_note_headings(
        parent_title=parent_section.title,
        content=parent_text,
    )
    matches: list[tuple[int, _StructuredSplitCandidate]] = []
    cursor = 0
    for candidate in _iter_structured_candidates(
        required_level=required_level,
        candidates=candidates,
        candidates_by_level=candidates_by_level,
    ):
        if not allow_note_headings and re.match(r"^(?:Note|NOTES?)\s+", candidate.title) is not None:
            continue
        anchor_position = _find_anchor_position_in_text(
            text=parent_text,
            normalized_text=normalized_parent,
            anchor_text=candidate.anchor_text,
            title=candidate.title,
            start=cursor,
        )
        if anchor_position is None:
            continue
        matches.append((anchor_position, candidate))
        cursor = anchor_position + max(1, len(candidate.title))

    marker_pairs = [(start, candidate.title) for start, candidate in matches]
    sec_subitem_marker_pairs = _extract_fallback_heading_markers(
        parent_text,
        parent_title=parent_section.title,
        sec_subitems_only=True,
    )
    fallback_marker_pairs = sec_subitem_marker_pairs

    structured_children = (
        _build_child_sections_from_markers(
            parent_section=parent_section,
            markers=marker_pairs,
        )
        if len(marker_pairs) >= 2
        else []
    )
    fallback_children = (
        _build_child_sections_from_markers(
            parent_section=parent_section,
            markers=fallback_marker_pairs,
        )
        if len(fallback_marker_pairs) >= 2
        else []
    )
    if len(fallback_children) < 2:
        fallback_marker_pairs = _extract_fallback_heading_markers(
            parent_text,
            parent_title=parent_section.title,
            sec_subitems_only=False,
        )
        fallback_children = (
            _build_child_sections_from_markers(
                parent_section=parent_section,
                markers=fallback_marker_pairs,
            )
            if len(fallback_marker_pairs) >= 2
            else []
        )
    return _select_preferred_child_sections(
        structured_children=structured_children,
        fallback_children=fallback_children,
    )


def _build_child_sections_from_markers(
    *,
    parent_section: _VirtualSection,
    markers: list[tuple[int, str]],
) -> list[_VirtualSection]:
    """根据子标题 marker 构建子章节。"""

    sorted_markers = sorted(markers, key=lambda item: item[0])
    children: list[_VirtualSection] = []
    for index, (start, title) in enumerate(sorted_markers, start=1):
        end = sorted_markers[index][0] if index < len(sorted_markers) else len(parent_section.content)
        if end <= start:
            continue
        content = parent_section.content[start:end].strip()
        content = _strip_leading_title(content, title)
        content = _trim_trailing_part_heading(content)
        allow_short = _allow_short_section(title)
        min_len = 8 if allow_short else _MIN_CHILD_SECTION_CHARS
        if not _has_meaningful_text(content, min_len=min_len):
            continue
        child_ref = _format_child_section_ref(parent_ref=parent_section.ref, index=index)
        child_preview = _normalize_whitespace(content)[:_PREVIEW_MAX_CHARS]
        children.append(
            _VirtualSection(
                ref=child_ref,
                title=title,
                content=content,
                preview=child_preview,
                table_refs=[],
                level=parent_section.level + 1,
                parent_ref=parent_section.ref,
                child_refs=[],
                start=parent_section.start + start,
                end=parent_section.start + end,
            )
        )
    return children if len(children) >= 2 else []


def _select_preferred_child_sections(
    *,
    structured_children: list[_VirtualSection],
    fallback_children: list[_VirtualSection],
) -> list[_VirtualSection]:
    """在结构候选拆分与 fallback 拆分之间选择质量更好的结果。

    Args:
        structured_children: 基于底层结构候选生成的子章节。
        fallback_children: 基于正文 fallback heading 生成的子章节。

    Returns:
        更优的子章节列表；若两者都不可用则返回空列表。

    Raises:
        RuntimeError: 选择失败时抛出。
    """

    if not structured_children:
        return fallback_children
    if not fallback_children:
        return structured_children

    def _rank(children: list[_VirtualSection]) -> tuple[int, int, int]:
        max_child_len = max(len(str(child.content or "")) for child in children)
        total_len = sum(len(str(child.content or "")) for child in children)
        return (-max_child_len, len(children), total_len)

    structured_rank = _rank(structured_children)
    fallback_rank = _rank(fallback_children)
    if fallback_rank > structured_rank:
        return fallback_children
    return structured_children


def _find_anchor_position_in_text(
    *,
    text: str,
    normalized_text: str,
    anchor_text: str,
    title: str,
    start: int,
) -> Optional[int]:
    """在文本中定位章节锚点位置。

    Args:
        text: 原始文本。
        normalized_text: 小写文本缓存。
        anchor_text: 优先使用的锚文本。
        title: 章节标题（用于回退匹配）。
        start: 搜索起点。

    Returns:
        命中起始位置；未命中返回 `None`。

    Raises:
        RuntimeError: 定位失败时抛出。
    """

    lowered_anchor = anchor_text.lower()
    index = normalized_text.find(lowered_anchor, max(0, start))
    if index >= 0:
        if _is_anchor_fast_match_reliable(
            text=text,
            start=index,
            anchor_text=anchor_text,
        ):
            return index
        title_start = _find_title_position_with_boundaries(
            text=text,
            title=title,
            start=max(0, index - _ANCHOR_TITLE_BACKTRACK_CHARS),
            end=index + _ANCHOR_TITLE_LOOKAHEAD_CHARS,
        )
        if title_start is not None:
            return title_start
        return index
    return _find_title_position_with_boundaries(text=text, title=title, start=start)


def _group_structured_candidates_by_level(
    candidates: list[_StructuredSplitCandidate],
) -> dict[int, list[tuple[int, _StructuredSplitCandidate]]]:
    """按章节层级对结构候选项分桶。

    Args:
        candidates: 全局结构候选项（保持原始顺序）。

    Returns:
        `level -> candidates` 的映射，每个桶内顺序与输入一致。

    Raises:
        RuntimeError: 分桶失败时抛出。
    """

    buckets: dict[int, list[tuple[int, _StructuredSplitCandidate]]] = {}
    for index, candidate in enumerate(candidates):
        buckets.setdefault(candidate.level, []).append((index, candidate))
    return buckets


def _iter_structured_candidates(
    *,
    required_level: int,
    candidates: list[_StructuredSplitCandidate],
    candidates_by_level: Optional[dict[int, list[tuple[int, _StructuredSplitCandidate]]]],
) -> list[_StructuredSplitCandidate]:
    """按父章节要求返回可参与匹配的候选项。

    优先走 ``candidates_by_level``，仅遍历 `required_level` 及更深层级，
    避免每次对子章节切分都全量扫描全局候选。

    Args:
        required_level: 目标子章节最小层级。
        candidates: 全量候选（保底路径）。
        candidates_by_level: 候选分桶映射。

    Returns:
        参与匹配的候选项列表（保持原有顺序）。

    Raises:
        RuntimeError: 构建候选列表失败时抛出。
    """

    if not candidates_by_level:
        return [candidate for candidate in candidates if candidate.level >= required_level]
    merged: list[tuple[int, _StructuredSplitCandidate]] = []
    for level in sorted(candidates_by_level):
        if level < required_level:
            continue
        merged.extend(candidates_by_level[level])
    merged.sort(key=lambda item: item[0])
    return [candidate for _, candidate in merged]


def _is_anchor_fast_match_reliable(
    *,
    text: str,
    start: int,
    anchor_text: str,
) -> bool:
    """判断锚文本快速命中是否可直接采用。

    Args:
        text: 原始文本。
        start: `anchor_text` 在文本中的起始位置。
        anchor_text: 用于定位的锚文本。

    Returns:
        当锚文本在词边界上时返回 `True`，否则返回 `False`。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    if start < 0:
        return False
    anchor_len = len(anchor_text)
    if anchor_len <= 0:
        return False
    end = start + anchor_len
    if end > len(text):
        return False
    if start > 0 and not _is_token_boundary_char(text[start - 1]):
        return False
    if end < len(text) and not _is_token_boundary_char(text[end]):
        return False
    return True


def _is_token_boundary_char(value: str) -> bool:
    """判断字符是否可视作词边界。

    Args:
        value: 单字符字符串。

    Returns:
        是词边界时返回 `True`，否则返回 `False`。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    if not value:
        return True
    return not (value.isalnum() or value == "_")


def _find_title_position_with_boundaries(
    *,
    text: str,
    title: str,
    start: int,
    end: Optional[int] = None,
) -> Optional[int]:
    """带词边界约束地查找标题位置。

    Args:
        text: 原始文本。
        title: 标题文本。
        start: 起始位置。
        end: 可选结束位置（不包含）。

    Returns:
        命中起始位置；未命中返回 `None`。
    """

    normalized_title = _normalize_optional_string(title)
    if normalized_title is None:
        return None
    pattern = _compile_title_boundary_pattern(normalized_title)
    search_end = len(text) if end is None else min(len(text), max(0, end))
    match = pattern.search(text, pos=max(0, start), endpos=search_end)
    if match is None:
        return None
    return int(match.start())


@lru_cache(maxsize=2048)
def _compile_title_boundary_pattern(normalized_title: str) -> re.Pattern[str]:
    """编译标题边界匹配正则并缓存。

    Args:
        normalized_title: 已规范化标题文本。

    Returns:
        标题边界匹配正则对象。

    Raises:
        re.error: 正则编译失败时抛出。
    """

    return re.compile(rf"(?<!\w){re.escape(normalized_title)}(?!\w)", flags=re.IGNORECASE)


def _extract_fallback_heading_markers(
    content: str,
    *,
    parent_title: Optional[str] = None,
    sec_subitems_only: bool = False,
) -> list[tuple[int, str]]:
    """从父章节正文中回退提取 heading marker。

    回退策略分两路：
    1. 行级标题匹配（适配保留换行的文本）；
    2. 单行正文匹配（适配 SecProcessor 压平成单行的大章节）。

    Args:
        content: 父章节正文。
        sec_subitems_only: 是否只返回 SEC 法定子项标题。

    Returns:
        `(start, title)` 列表（按位置升序，应用最小间距去重）。

    Raises:
        RuntimeError: 提取失败时抛出。
    """

    if not content:
        return []
    if _looks_like_reference_guide_content(title=parent_title, content=content):
        return []
    markers: list[tuple[int, str]] = []
    sec_subitem_markers = _extract_sec_subitem_heading_markers(content)
    markers.extend(sec_subitem_markers)
    if not sec_subitems_only and len(sec_subitem_markers) < 2:
        markers.extend(_extract_line_based_heading_markers(content))
        markers.extend(
            _extract_title_case_line_heading_markers(
                content,
                parent_title=parent_title,
            )
        )
        markers.extend(_extract_inline_heading_markers(content))
    if not markers:
        return []
    if parent_title is not None:
        markers = [
            (pos, title)
            for pos, title in markers
            if not _is_redundant_title_case_heading(
                title=title,
                parent_title=parent_title,
                start=pos,
            )
        ]
    if not _parent_context_allows_note_headings(
        parent_title=parent_title,
        content=content,
    ):
        markers = [(pos, title) for pos, title in markers if re.match(r"^(?:Note|NOTES?)\s+", title) is None]
    if not markers:
        return []

    markers.sort(key=lambda item: item[0])
    deduped: list[tuple[int, str]] = []
    last_pos = -_CHILD_HEADING_MIN_DISTANCE
    for pos, title in markers:
        if pos - last_pos < _CHILD_HEADING_MIN_DISTANCE:
            continue
        deduped.append((pos, title))
        last_pos = pos
    return deduped


def _extract_sec_subitem_heading_markers(content: str) -> list[tuple[int, str]]:
    """提取 SEC 法定子项标题（如 ``ITEM 4.A.`` + 下一行标题）。

    Args:
        content: 父章节正文。

    Returns:
        `(start, title)` 列表。

    Raises:
        RuntimeError: 提取失败时抛出。
    """

    if not content:
        return []

    markers: list[tuple[int, str]] = []
    sec_subitem_pattern = re.compile(r"(?im)^(\s*ITEM\s+\d+\.\s*([A-Z])\.\s*)$")
    for match in sec_subitem_pattern.finditer(content):
        letter = _normalize_optional_string(match.group(2))
        if letter is None:
            continue
        next_start = int(match.end())
        next_line_match = re.search(r"(?m)^\s*([^\n]{3,160})\s*$", content[next_start:])
        if next_line_match is None:
            continue
        raw_title = _normalize_optional_string(next_line_match.group(1))
        if raw_title is None:
            continue
        title = f"{letter}. {raw_title}"
        if _looks_like_truncated_heading_fragment(title):
            continue
        markers.append((int(match.start()), title))
    return markers


def _parent_context_allows_note_headings(
    *,
    parent_title: Optional[str],
    content: str,
) -> bool:
    """判断父章节上下文是否允许 ``Note X`` 作为有效子标题。

    ``Note`` 子标题通常只应出现在财务报表 / 附注上下文中。若父章节是
    20-F Item 4/5 这类 narrative section，把正文中对附注的引用误拆成
    子标题会导致大段正文被错误吸附到 ``Note`` 伪章节。

    Args:
        parent_title: 父章节标题。
        content: 父章节正文。

    Returns:
        父章节确属财务报表/附注上下文时返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    normalized_parent_title = _normalize_optional_string(parent_title)
    if normalized_parent_title is not None:
        for pattern in _NOTE_HEADING_ALLOWED_PARENT_PATTERNS:
            if pattern.search(normalized_parent_title) is not None:
                return True

    content_prefix = str(content or "")[:_NOTE_HEADING_PARENT_CONTENT_WINDOW]
    for pattern in _NOTE_HEADING_ALLOWED_CONTENT_PATTERNS:
        if pattern.search(content_prefix) is not None:
            return True
    return False


def _count_reference_guide_signals(content: str) -> tuple[int, int, int, int, int]:
    """统计 cross-reference guide / page locator 的特征信号数量。

    Args:
        content: 待分析文本。

    Returns:
        ``(source_hits, note_hits, code_hits, page_hits, action_hits)``。

    Raises:
        RuntimeError: 统计失败时抛出。
    """

    normalized_prefix = _normalize_whitespace(str(content or ""))[:_REFERENCE_GUIDE_PREFIX_WINDOW]
    source_hits = sum(1 for pattern in _REFERENCE_GUIDE_SOURCE_PATTERNS for _ in pattern.finditer(normalized_prefix))
    note_hits = len(list(_REFERENCE_GUIDE_NOTE_PATTERN.finditer(normalized_prefix)))
    code_hits = len(list(_REFERENCE_GUIDE_CODE_PATTERN.finditer(normalized_prefix)))
    page_hits = len(list(_REFERENCE_GUIDE_PAGE_RANGE_PATTERN.finditer(normalized_prefix)))
    action_hits = sum(1 for pattern in _REFERENCE_GUIDE_ACTION_PATTERNS for _ in pattern.finditer(normalized_prefix))
    return source_hits, note_hits, code_hits, page_hits, action_hits


def _looks_like_reference_guide_content(
    *,
    title: Optional[str],
    content: str,
) -> bool:
    """判断文本是否更像 cross-reference guide，而非正文段落。

    这类内容通常由多个报告来源标签、页码定位符、``Note X`` 引用和
    ``not applicable`` / ``see also supplement`` 等指示语拼接而成。
    若把它当作正文再做子切分，极易把 ``Note`` 或报告标题误吸成伪章节。

    Args:
        title: 可选标题，仅用于保守过滤 ``Cover Page`` 等明显非目标段落。
        content: 待分析正文。

    Returns:
        命中 cross-reference guide 特征时返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    normalized_title = _normalize_optional_string(title)
    if normalized_title is not None and normalized_title.lower() == "cover page":
        return False

    source_hits, note_hits, code_hits, page_hits, action_hits = _count_reference_guide_signals(content)
    locator_hits = code_hits + page_hits
    if source_hits >= 3 and locator_hits >= 2:
        return True
    if source_hits >= 2 and note_hits >= 1 and locator_hits >= 1:
        return True
    if note_hits >= 2 and locator_hits >= 2:
        return True
    # `not applicable` / `see also supplement` 这类动作词在 20-F 正文中也会自然出现。
    # 仅凭 “Annual Report” + “Not applicable” 这种正文常见组合不足以证明
    # 当前段落是 cross-reference guide；必须同时出现更直接的 locator / note
    # 证据，才能安全地短路掉 fallback 子标题切分。
    if action_hits >= 2 and (locator_hits >= 1 or note_hits >= 1):
        return True
    return False


def _extract_line_based_heading_markers(content: str) -> list[tuple[int, str]]:
    """提取基于换行边界的 fallback heading。

    Args:
        content: 父章节正文。

    Returns:
        `(start, title)` 列表。

    Raises:
        RuntimeError: 提取失败时抛出。
    """

    markers: list[tuple[int, str]] = []
    lowered_content = content.lower()
    for pattern in _FALLBACK_HEADING_PATTERNS:
        for match in pattern.finditer(content):
            title = _normalize_optional_string(match.group(1))
            if title is None:
                continue
            if not _is_valid_inline_heading(
                lowered_content=lowered_content,
                start=int(match.start()),
                title=title,
            ):
                continue
            markers.append((int(match.start()), title))
    return markers


def _extract_title_case_line_heading_markers(
    content: str,
    *,
    parent_title: Optional[str] = None,
) -> list[tuple[int, str]]:
    """提取“独立 Title Case 行”形式的子标题 marker。

    该规则只用于超长父章节，目标场景是 20-F 等 narrative section 中的
    二级/三级自然段标题，例如 ``Deposit-Taking Activities``、
    ``Retail Banking Services``。为避免把表格公司名、目录残片或页码
    误判为标题，候选行除标题形态外，还必须在后续窗口中观察到 prose。

    Args:
        content: 父章节正文。

    Returns:
        `(start, title)` 列表。

    Raises:
        RuntimeError: 提取失败时抛出。
    """

    if len(content) < _TITLE_CASE_HEADING_MIN_PARENT_CHARS:
        return []

    markers: list[tuple[int, str]] = []
    lines = _split_content_lines_with_offsets(content)
    for index, (start, raw_line) in enumerate(lines):
        title = _normalize_optional_string(raw_line)
        if title is None:
            continue
        if not _looks_like_title_case_heading(title):
            continue
        if _is_redundant_title_case_heading(
            title=title,
            parent_title=parent_title,
            start=start,
        ):
            continue
        if not _has_title_case_heading_prose_context(lines=lines, index=index):
            continue
        markers.append((start, title))
    return markers


def _extract_inline_heading_markers(content: str) -> list[tuple[int, str]]:
    """提取单行正文中的 fallback heading。

    Args:
        content: 父章节正文。

    Returns:
        `(start, title)` 列表。

    Raises:
        RuntimeError: 提取失败时抛出。
    """

    if not content:
        return []
    markers: list[tuple[int, str]] = []
    lowered_content = content.lower()
    for pattern in _FALLBACK_INLINE_HEADING_PATTERNS:
        for match in pattern.finditer(content):
            start = int(match.start())
            normalized_title = _normalize_inline_heading_title(match.group(1))
            if normalized_title is None:
                continue
            if not _is_valid_inline_heading(
                lowered_content=lowered_content,
                start=start,
                title=normalized_title,
            ):
                continue
            markers.append((start, normalized_title))
    return markers


def _split_content_lines_with_offsets(content: str) -> list[tuple[int, str]]:
    """按行切分正文，并保留每行在原文中的偏移量。

    Args:
        content: 原始正文。

    Returns:
        `(offset, raw_line)` 列表，顺序与正文一致。

    Raises:
        RuntimeError: 切分失败时抛出。
    """

    lines: list[tuple[int, str]] = []
    offset = 0
    for raw_line in content.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        lines.append((offset, line))
        offset += len(raw_line)
    if content and not content.endswith(("\n", "\r")) and not lines:
        lines.append((0, content))
    return lines


def _normalize_inline_heading_title(raw_title: str) -> Optional[str]:
    """标准化单行 heading 文本。

    Args:
        raw_title: 原始匹配文本。

    Returns:
        标准化标题；无效时返回 `None`。

    Raises:
        RuntimeError: 处理失败时抛出。
    """

    normalized = _normalize_optional_string(raw_title)
    if normalized is None:
        return None
    # 去掉尾部配对符号，避免正文引号粘连到标题。
    normalized = normalized.rstrip("\"'”’`.,;:)]} ")
    words = normalized.split()
    if len(words) > _INLINE_HEADING_TITLE_MAX_WORDS:
        normalized = " ".join(words[:_INLINE_HEADING_TITLE_MAX_WORDS])
    return _normalize_optional_string(normalized)


def _looks_like_title_case_heading(title: str) -> bool:
    """判断一行文本是否具备独立 Title Case 标题特征。

    Args:
        title: 候选标题文本。

    Returns:
        符合标题特征时返回 `True`。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    normalized_title = _normalize_optional_string(title)
    if normalized_title is None:
        return False
    lowered_title = normalized_title.lower()
    if lowered_title in _TITLE_CASE_HEADING_ARTIFACT_TITLES:
        return False
    if lowered_title.startswith("see "):
        return False
    if len(normalized_title) < 12 or len(normalized_title) > _TITLE_CASE_HEADING_MAX_CHARS:
        return False
    if any(char.isdigit() for char in normalized_title):
        return False
    if normalized_title.endswith((".", ":", ";", ",", "?", "!")):
        return False
    if normalized_title[:1] in {"•", "-", "—", "–", "*"}:
        return False
    if normalized_title.count("|") > 0:
        return False
    if _looks_like_truncated_heading_fragment(normalized_title):
        return False

    words = re.findall(r"[A-Za-z][A-Za-z'&/\-]*", normalized_title)
    if len(words) < _TITLE_CASE_HEADING_MIN_WORDS or len(words) > _TITLE_CASE_HEADING_MAX_WORDS:
        return False
    alpha_chars = sum(len(word) for word in words)
    if alpha_chars < _TITLE_CASE_HEADING_MIN_ALPHA_CHARS:
        return False
    if words[-1].lower() in _FALLBACK_HEADING_TRAILING_STOPWORDS:
        return False

    significant_words = [word for word in words if word.lower() not in _FALLBACK_HEADING_CAPITALIZATION_STOPWORDS]
    if len(significant_words) < 2:
        return False
    capitalized_ratio = sum(1 for word in significant_words if word.isupper() or word[:1].isupper()) / len(
        significant_words
    )
    if capitalized_ratio < _TITLE_CASE_HEADING_MIN_CAPITALIZED_RATIO:
        return False
    return True


def _is_redundant_title_case_heading(
    *,
    title: str,
    parent_title: Optional[str],
    start: int,
) -> bool:
    """判断候选 Title Case 行是否只是父章节标题的重复展示。

    Args:
        title: 候选标题文本。
        parent_title: 父章节标题。
        start: 候选在父章节正文中的起始偏移。

    Returns:
        若只是父标题在正文开头的重复展示则返回 `True`。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    normalized_title = _normalize_optional_string(title)
    normalized_parent_title = _normalize_optional_string(parent_title)
    if normalized_title is None or normalized_parent_title is None:
        return False
    if start > _CHILD_HEADING_MIN_DISTANCE:
        return False

    candidate_key = _normalize_heading_similarity_key(normalized_title)
    parent_key = _normalize_heading_similarity_key(normalized_parent_title)
    if not candidate_key or not parent_key:
        return False
    return candidate_key in parent_key


def _normalize_heading_similarity_key(title: str) -> str:
    """将标题规范化为便于相似度比较的 key。

    Args:
        title: 原始标题文本。

    Returns:
        仅保留语义主体的比较 key。

    Raises:
        RuntimeError: 处理失败时抛出。
    """

    normalized_title = _normalize_optional_string(title)
    if normalized_title is None:
        return ""
    normalized_title = re.sub(r"^[A-Z]\.\s+", "", normalized_title)
    normalized_title = re.sub(
        r"^(?:part\s+[ivx]+\s*-\s*)?item\s+\d+[a-z]?(?:\.\d+)?\s*[-:]\s*",
        "",
        normalized_title,
        flags=re.IGNORECASE,
    )
    normalized_title = re.sub(r"^item\s+\d+\.[A-Z]\.\s*", "", normalized_title, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", normalized_title).strip().lower()


def _has_title_case_heading_prose_context(
    *,
    lines: list[tuple[int, str]],
    index: int,
) -> bool:
    """判断 Title Case 标题候选后方是否存在叙述性正文。

    Args:
        lines: `(offset, raw_line)` 列表。
        index: 当前标题候选行索引。

    Returns:
        候选后方存在 prose 时返回 `True`。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    following_lines: list[str] = []
    for _, raw_line in lines[index + 1 : index + 1 + _TITLE_CASE_HEADING_LOOKAHEAD_LINES]:
        normalized_line = _normalize_optional_string(raw_line)
        if normalized_line is None:
            continue
        lowered_line = normalized_line.lower()
        if lowered_line in _TITLE_CASE_HEADING_ARTIFACT_TITLES:
            continue
        if _is_page_locator_only_line(normalized_line):
            continue
        following_lines.append(normalized_line)
        if len(following_lines) >= _TITLE_CASE_HEADING_LOOKAHEAD_LINES:
            break
    if not following_lines:
        return False

    prose_lines = [
        line for line in following_lines[:_TITLE_CASE_HEADING_PROSE_WINDOW] if _looks_like_prose_followup_line(line)
    ]
    if not prose_lines:
        return False
    prose_word_count = sum(len(re.findall(r"[A-Za-z][A-Za-z'&/\-]*", line)) for line in prose_lines)
    return prose_word_count >= _TITLE_CASE_HEADING_MIN_PROSE_WORDS


def _is_page_locator_only_line(line: str) -> bool:
    """判断一行文本是否只是页码/页脚定位符。

    Args:
        line: 已规范化单行文本。

    Returns:
        仅含页码定位符时返回 `True`。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    normalized_line = _normalize_optional_string(line)
    if normalized_line is None:
        return False
    if normalized_line.isdigit():
        return True
    if re.fullmatch(_PAGE_LOCATOR_TOKEN_PATTERN, normalized_line) is not None:
        return True
    return False


def _looks_like_prose_followup_line(line: str) -> bool:
    """判断标题候选后的单行是否更像正文段落而非表格行。

    Args:
        line: 已规范化单行文本。

    Returns:
        看起来像正文时返回 `True`。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    normalized_line = _normalize_optional_string(line)
    if normalized_line is None:
        return False
    if normalized_line == "•":
        return False
    if len(normalized_line) < 48:
        return False

    words = re.findall(r"[A-Za-z][A-Za-z'&/\-]*", normalized_line)
    if len(words) < 10:
        return False
    lowercase_words = sum(1 for word in words if word[:1].islower())
    if lowercase_words < max(3, len(words) // 4):
        return False

    alpha_chars = sum(char.isalpha() for char in normalized_line)
    digit_chars = sum(char.isdigit() for char in normalized_line)
    if alpha_chars <= digit_chars * 2:
        return False
    return True


def _is_valid_inline_heading(
    *,
    lowered_content: str,
    start: int,
    title: str,
) -> bool:
    """校验单行 heading 候选是否可用于切分。

    Args:
        lowered_content: 小写正文缓存。
        start: heading 起始位置。
        title: 标准化标题。

    Returns:
        候选可用时返回 `True`。

    Raises:
        RuntimeError: 校验失败时抛出。
    """

    words = title.split()
    if len(words) < _INLINE_HEADING_MIN_WORDS or len(words) > _INLINE_HEADING_MAX_WORDS:
        return False
    dash_count = title.count("—") + title.count("–") + title.count("-")
    if dash_count > _INLINE_HEADING_MAX_DASH_COUNT:
        return False
    if _looks_like_truncated_heading_fragment(title):
        return False
    context = lowered_content[max(0, start - _INLINE_HEADING_CONTEXT_WINDOW) : start]
    for pattern in _INLINE_REF_CONTEXT_PATTERNS:
        if pattern.search(context):
            return False
    return True


def _looks_like_truncated_heading_fragment(title: str) -> bool:
    """判断 fallback heading 是否更像被截断的正文句子片段。

    误判高发场景：
    - 表格行被提取成 ``9. Corporate loans include ...`` 这类句子片段；
    - 正文中的说明句因换行/单元格边界被拆成看似标题的独立行。

    这些片段通常具备两个信号：
    1. 尾词是 ``of`` / ``in`` / ``to`` 等悬挂介词；
    2. 显著词中大写开头比例很低，更像普通句子而非标题。

    Args:
        title: 候选标题文本。

    Returns:
        看起来像截断句子时返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    normalized_title = _normalize_optional_string(title)
    if normalized_title is None:
        return False
    if re.match(r"^[A-Z]\.", normalized_title) is not None:
        return False
    if (
        re.match(r"^(?:Note|NOTES?)\s+", normalized_title) is None
        and re.match(
            r"^\d+\.",
            normalized_title,
        )
        is None
    ):
        return False

    words = re.findall(r"[A-Za-z][A-Za-z'&/\-]*", normalized_title)
    if not words:
        return False

    last_word = words[-1].lower()
    if last_word in _FALLBACK_HEADING_TRAILING_STOPWORDS:
        return True

    significant_words = [
        word for word in words if len(word) > 2 and word.lower() not in _FALLBACK_HEADING_CAPITALIZATION_STOPWORDS
    ]
    if len(significant_words) < 4:
        return False

    capitalized_count = sum(1 for word in significant_words if word.isupper() or word[0].isupper())
    capitalized_ratio = capitalized_count / len(significant_words)
    return capitalized_ratio < _FALLBACK_HEADING_MIN_CAPITALIZED_RATIO


def _build_parent_directory_content(
    *,
    section: _VirtualSection,
    children: list[_VirtualSection],
) -> str:
    """构建父章节目录内容。

    Args:
        section: 父章节。
        children: 直接子章节列表。

    Returns:
        目录文本。
    """

    title = _normalize_optional_string(section.title) or section.ref
    lines = [
        f"{title} is split into {len(children)} child sections.",
        "Read child sections for full content:",
    ]
    for child in children:
        child_title = _normalize_optional_string(child.title) or child.ref
        preview = _normalize_whitespace(child.preview)[:80]
        lines.append(f"- {child.ref} | {child_title} | {preview}")
    return "\n".join(lines)


def _format_child_section_ref(*, parent_ref: str, index: int) -> str:
    """生成子章节 ref。"""

    if index <= 0:
        raise ValueError("child section index 必须大于 0")
    return f"{parent_ref}_c{index:0{_CHILD_REF_WIDTH}d}"


def _dedupe_markers(markers: list[tuple[int, Optional[str]]]) -> list[tuple[int, Optional[str]]]:
    """对边界标记去重并按位置排序。

    Args:
        markers: 原始标记列表。

    Returns:
        去重后的标记列表。

    Raises:
        RuntimeError: 处理失败时抛出。
    """

    valid_items = [(int(position), title) for position, title in markers if int(position) >= 0]
    valid_items.sort(key=lambda item: item[0])
    deduped: list[tuple[int, Optional[str]]] = []
    seen_positions: set[int] = set()
    for position, title in valid_items:
        if position in seen_positions:
            continue
        seen_positions.add(position)
        deduped.append((position, title))
    return deduped


def _build_marker_title_ranges(
    text: str,
    markers: list[tuple[int, Optional[str]]],
) -> dict[str, tuple[int, int]]:
    """按标记构建标题→文本范围映射。

    将去重后的 marker 列表转为 ``{title: (start, end)}`` 映射，
    用于在带表格占位符的全文中按标题查找对应文本段，提取表格引用。

    Args:
        text: 全文文本。
        markers: 边界标记列表。

    Returns:
        标题到文本范围 ``(start, end)`` 的映射；
        无标题的标记会被跳过。
    """

    deduped = _dedupe_markers(markers)
    if not deduped:
        return {}
    ranges: dict[str, tuple[int, int]] = {}
    for i, (start, title) in enumerate(deduped):
        end = deduped[i + 1][0] if i + 1 < len(deduped) else len(text)
        if title:
            ranges[title] = (start, end)
    return ranges


def _filter_table_refs_by_availability(
    refs: list[str],
    available_table_refs: Optional[set[str]],
) -> list[str]:
    """按底层可用表格集合过滤章节内的 ``table_ref``。

    Args:
        refs: 原始表格引用列表（保持原顺序）。
        available_table_refs: 底层 ``list_tables()`` 可见的引用集合；
            ``None`` 表示无法获取，直接透传 ``refs``。

    Returns:
        过滤后的表格引用列表。

    Raises:
        无。
    """

    if available_table_refs is None:
        return refs
    return [ref for ref in refs if ref in available_table_refs]


def _assign_unmapped_tables_by_position(
    *,
    marked_text: str,
    title_ranges: dict[str, tuple[int, int]],
    cover_end: int,
    virtual_sections: list[_VirtualSection],
    virtual_section_by_ref: dict[str, _VirtualSection],
    table_ref_to_virtual_ref: dict[str, str],
    available_table_refs: Optional[set[str]] = None,
) -> None:
    """将 Phase 1 未分配的 ``[[t_XXXX]]`` 回退分配到最近的前驱虚拟章节。

    Phase 1（标题精确匹配）可能遗漏部分表格——当标记文本（带 ``[[t_XXXX]]``
    占位符）上重新运行 ``_build_markers`` 产生与原虚拟章节不同的 marker 标题
    时，对应 title_range 无法匹配任何虚拟章节，范围内的 ``[[t_XXXX]]`` 不会
    被分配。典型场景：DEF 14A 的 Proposal 编号在有/无表格文本时正则匹配不同。

    本函数作为 Phase 2 回退：

    1. 收集 Phase 1 已分配的 ``tbl_ref`` 集合。
    2. 构建"已匹配虚拟章节"在标记文本中的有序边界列表（Cover Page 用 0，
       其余用 ``title_ranges`` 中对应标题的起始位置）。
    3. 扫描标记文本中所有 ``[[t_XXXX]]``，对未分配的 ref 按位置查找
       最近的前驱边界，将其分配到对应虚拟章节。

    Args:
        marked_text: 带 ``[[t_XXXX]]`` 占位符的文档全文。
        title_ranges: ``_build_marker_title_ranges`` 返回的标题→范围映射。
        cover_end: Cover Page 在标记文本中的结束位置。
        virtual_sections: 虚拟章节列表。
        virtual_section_by_ref: ref→虚拟章节 映射。
        table_ref_to_virtual_ref: 已有的 tbl_ref→vs_ref 映射（会被更新）。
        available_table_refs: 底层可用表格引用集合；为 ``None`` 时不做过滤。

    Returns:
        无（就地更新 ``table_ref_to_virtual_ref`` 和虚拟章节的 ``table_refs``）。
    """

    assigned_refs = set(table_ref_to_virtual_ref.keys())

    # 构建已匹配虚拟章节的有序边界：(position_in_marked_text, vs_ref)
    matched_boundaries: list[tuple[int, str]] = []
    for vs in virtual_sections:
        if vs.title == "Cover Page":
            matched_boundaries.append((0, vs.ref))
        elif vs.title in title_ranges:
            start, _ = title_ranges[vs.title]
            matched_boundaries.append((start, vs.ref))
    matched_boundaries.sort(key=lambda x: x[0])

    if not matched_boundaries:
        return

    # 扫描所有 [[t_XXXX]]，对未分配的 ref 按位置回退分配
    for match in _TABLE_REF_PATTERN.finditer(marked_text):
        tbl_ref = match.group(1)
        if available_table_refs is not None and tbl_ref not in available_table_refs:
            continue
        if tbl_ref in assigned_refs:
            continue

        pos = match.start()
        # 查找最近的前驱已匹配虚拟章节边界
        target_vs_ref: Optional[str] = None
        for boundary_pos, vs_ref in reversed(matched_boundaries):
            if boundary_pos <= pos:
                target_vs_ref = vs_ref
                break
        # 位于所有边界之前的表格（极罕见），分配到第一个虚拟章节
        if target_vs_ref is None:
            target_vs_ref = matched_boundaries[0][1]

        table_ref_to_virtual_ref[tbl_ref] = target_vs_ref
        target_vs = virtual_section_by_ref.get(target_vs_ref)
        if target_vs is not None:
            target_vs.table_refs.append(tbl_ref)


def _remap_tables_to_deepest_virtual_sections(
    *,
    marked_text: str,
    title_ranges: dict[str, tuple[int, int]],
    cover_end: int,
    virtual_sections: list[_VirtualSection],
    virtual_section_by_ref: dict[str, _VirtualSection],
    table_ref_to_virtual_ref: dict[str, str],
) -> None:
    """将表格映射从父章节下钻到最深命中子章节。

    Args:
        marked_text: 带表格占位符的全文。
        title_ranges: 一级 marker 标题范围映射。
        cover_end: Cover Page 的结束位置。
        virtual_sections: 顶层虚拟章节列表。
        virtual_section_by_ref: 全量 ref→章节映射。
        table_ref_to_virtual_ref: 当前 tbl_ref→章节映射（会被就地更新）。

    Returns:
        无。
    """

    section_ranges = _build_virtual_section_ranges_in_marked_text(
        marked_text=marked_text,
        title_ranges=title_ranges,
        cover_end=cover_end,
        top_sections=virtual_sections,
        virtual_section_by_ref=virtual_section_by_ref,
    )
    if not section_ranges:
        return

    table_positions = {match.group(1): int(match.start()) for match in _TABLE_REF_PATTERN.finditer(marked_text)}

    for tbl_ref, current_ref in list(table_ref_to_virtual_ref.items()):
        position = table_positions.get(tbl_ref)
        if position is None:
            continue
        deepest_ref = _find_deepest_virtual_section_ref(
            start_ref=current_ref,
            position=position,
            section_ranges=section_ranges,
            virtual_section_by_ref=virtual_section_by_ref,
        )
        if deepest_ref == current_ref:
            continue
        current_section = virtual_section_by_ref.get(current_ref)
        if current_section is not None and tbl_ref in current_section.table_refs:
            current_section.table_refs.remove(tbl_ref)
        target_section = virtual_section_by_ref.get(deepest_ref)
        if target_section is not None and tbl_ref not in target_section.table_refs:
            target_section.table_refs.append(tbl_ref)
        table_ref_to_virtual_ref[tbl_ref] = deepest_ref


def _build_virtual_section_ranges_in_marked_text(
    *,
    marked_text: str,
    title_ranges: dict[str, tuple[int, int]],
    cover_end: int,
    top_sections: list[_VirtualSection],
    virtual_section_by_ref: dict[str, _VirtualSection],
) -> dict[str, tuple[int, int]]:
    """构建虚拟章节在标记文本中的范围映射。

    Args:
        marked_text: 带表格占位符的全文。
        title_ranges: 一级 marker 标题范围映射。
        cover_end: Cover Page 的结束位置。
        top_sections: 顶层章节列表。
        virtual_section_by_ref: ref→章节映射。

    Returns:
        `section_ref -> (start, end)` 映射。
    """

    ranges: dict[str, tuple[int, int]] = {}
    for section in top_sections:
        if section.title == "Cover Page":
            ranges[section.ref] = (0, max(0, cover_end))
        elif section.title in title_ranges:
            ranges[section.ref] = title_ranges[section.title]

    for section in top_sections:
        if section.ref not in ranges or not section.child_refs:
            continue
        _build_child_ranges_within_parent(
            marked_text=marked_text,
            parent_section=section,
            parent_range=ranges[section.ref],
            ranges=ranges,
            virtual_section_by_ref=virtual_section_by_ref,
        )
    return ranges


def _build_child_ranges_within_parent(
    *,
    marked_text: str,
    parent_section: _VirtualSection,
    parent_range: tuple[int, int],
    ranges: dict[str, tuple[int, int]],
    virtual_section_by_ref: dict[str, _VirtualSection],
) -> None:
    """在父章节范围内定位子章节范围。"""

    parent_start, parent_end = parent_range
    if parent_end <= parent_start:
        return

    located_children: list[tuple[str, int]] = []
    cursor = parent_start
    for child_ref in parent_section.child_refs:
        child_section = virtual_section_by_ref.get(child_ref)
        if child_section is None:
            continue
        child_title = _normalize_optional_string(child_section.title)
        if child_title is None:
            continue
        position = _find_title_position_with_boundaries(
            text=marked_text,
            title=child_title,
            start=cursor,
        )
        if position is None or position < parent_start or position >= parent_end:
            continue
        located_children.append((child_ref, position))
        cursor = position + len(child_title)

    for index, (child_ref, start) in enumerate(located_children):
        end = located_children[index + 1][1] if index + 1 < len(located_children) else parent_end
        if end <= start:
            continue
        ranges[child_ref] = (start, end)
        child_section = virtual_section_by_ref.get(child_ref)
        if child_section is None or not child_section.child_refs:
            continue
        _build_child_ranges_within_parent(
            marked_text=marked_text,
            parent_section=child_section,
            parent_range=(start, end),
            ranges=ranges,
            virtual_section_by_ref=virtual_section_by_ref,
        )


def _find_deepest_virtual_section_ref(
    *,
    start_ref: str,
    position: int,
    section_ranges: dict[str, tuple[int, int]],
    virtual_section_by_ref: dict[str, _VirtualSection],
) -> str:
    """查找命中位置对应的最深章节 ref。"""

    current_ref = start_ref
    while True:
        current_section = virtual_section_by_ref.get(current_ref)
        if current_section is None:
            return current_ref
        matched_child_ref: Optional[str] = None
        matched_start = -1
        for child_ref in current_section.child_refs:
            child_range = section_ranges.get(child_ref)
            if child_range is None:
                continue
            start, end = child_range
            if start <= position < end and start >= matched_start:
                matched_child_ref = child_ref
                matched_start = start
        if matched_child_ref is None:
            return current_ref
        current_ref = matched_child_ref


def _has_meaningful_text(content: str, min_len: int = 24) -> bool:
    """判断文本是否具备有效信息量。

    Args:
        content: 候选文本。
        min_len: 最小长度阈值。

    Returns:
        文本有效时返回 `True`。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    return len(_normalize_whitespace(content)) >= min_len


def _allow_short_section(title: Optional[str]) -> bool:
    """判断标题对应章节是否允许短文本通过。

    Args:
        title: 章节标题。

    Returns:
        允许短文本时返回 `True`。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    normalized_title = _normalize_optional_string(title)
    if normalized_title is None:
        return False
    return normalized_title in {
        "SIGNATURE",
        "Schedule A",
        "Exhibit",
        "Conference Call",
        "Safe Harbor",
        "About Non-GAAP",
        "Key Highlights",
    } or normalized_title.startswith(("Annex", "Appendix", "Proposal"))


# ---------------------------------------------------------------------------
# token 级搜索回退（跨表单共享）
# ---------------------------------------------------------------------------

# 单词最短有效长度——过短的 token（如 "of", "in"）无分析价值
_MIN_SEARCH_TOKEN_LEN = 3


def _tokenize_query(query: str) -> list[str]:
    """将查询字符串拆分为有效搜索 token。

    过滤掉过短的 token（长度 < ``_MIN_SEARCH_TOKEN_LEN``），
    避免 "of"、"in" 等停用词产生大量无意义命中。

    Args:
        query: 原始查询字符串。

    Returns:
        有效 token 列表（全部小写）。
    """

    return [token for token in re.split(r"\W+", query.strip().lower()) if len(token) >= _MIN_SEARCH_TOKEN_LEN]


def _token_fallback_search(
    *,
    query: str,
    virtual_sections: list,
    virtual_section_by_ref: dict,
    within_ref: Optional[str],
) -> list[SearchHit]:
    """Token OR 回退搜索。

    将多词查询拆分为 token，在虚拟章节中搜索任一 token 出现的章节。
    仅当精确短语匹配无结果且查询包含多个有效 token 时才被调用。

    Args:
        query: 原始查询字符串。
        virtual_sections: 虚拟章节列表。
        virtual_section_by_ref: ref → 虚拟章节映射。
        within_ref: 可选，限定搜索范围。

    Returns:
        命中列表。
    """

    tokens = _tokenize_query(query)
    # 仅当查询可拆分为多个有效 token 时才启用回退
    if len(tokens) < 2:
        return []

    normalized_query = str(query or "").strip()
    # 构建 token OR 正则：任一 token 出现即匹配
    token_pattern = re.compile(
        "|".join(re.escape(t) for t in tokens),
        re.IGNORECASE,
    )

    target_sections = (
        [virtual_section_by_ref[within_ref]]
        if within_ref is not None and within_ref in virtual_section_by_ref
        else virtual_sections
    )

    hits_raw: list[SearchHit] = []
    section_content_map: dict[str, str] = {}
    for section in target_sections:
        if token_pattern.search(section.content) is None:
            continue
        section_content_map[section.ref] = section.content
        hits_raw.append(
            {
                "section_ref": section.ref,
                "section_title": section.title,
                "snippet": normalized_query,
            }
        )

    if not hits_raw:
        return []

    # 使用 token 共现窗口生成 snippet，优先展示多 token 共现区域。
    # 返回的 hit 带 _token_fallback=True 标记，供搜索引擎区分精确/回退命中。
    return enrich_hits_by_section_token_or(
        hits_raw=hits_raw,
        section_content_map=section_content_map,
        tokens=tokens,
        original_query=normalized_query,
    )


# ---------------------------------------------------------------------------
# BS 特殊表单通用 supports 检查
# ---------------------------------------------------------------------------


def _check_special_form_support(
    source: "Source",
    *,
    form_type: Optional[str],
    media_type: Optional[str],
    supported_forms: frozenset[str],
    base_supports_fn: Callable[..., bool],
    extra_media_keywords: frozenset[str] = frozenset(),
    extra_suffixes: frozenset[str] = frozenset(),
) -> bool:
    """BS 特殊表单处理器通用 supports() 逻辑。

    统一的判定流程：
    1. 标准化 form_type → 检查是否在支持列表中
    2. 委托 base_supports_fn（通常为 FinsBSProcessor.supports）做原生判断
    3. XML 媒体类型兜底
    4. 额外媒体类型关键词兜底（如 ``text/plain``）
    5. URI 后缀兜底（``.xml`` + 额外后缀）

    Args:
        source: 文档来源。
        form_type: 原始表单类型。
        media_type: 媒体类型。
        supported_forms: 该处理器支持的标准化表单类型集合。
        base_supports_fn: 基底处理器的 supports 方法（接受 source, form_type, media_type）。
        extra_media_keywords: 额外匹配的媒体类型关键词（如 ``"text/plain"``）。
        extra_suffixes: 除 ``.xml`` 外的额外文件后缀（如 ``".txt"``）。

    Returns:
        该处理器是否支持此文档。
    """
    normalized_form = _parse_section_sec_form(form_type)
    if normalized_form not in supported_forms:
        return False
    if base_supports_fn(source, form_type=form_type, media_type=media_type):
        return True
    resolved_media_type = str(media_type or source.media_type or "").lower()
    if "xml" in resolved_media_type:
        return True
    # 额外媒体类型关键词（如 SC 13 需要 text/plain）
    for keyword in extra_media_keywords:
        if keyword in resolved_media_type:
            return True
    allowed_suffixes = {".xml"} | set(extra_suffixes)
    return _infer_suffix_from_uri(source.uri) in allowed_suffixes


__all__ = [
    "_VirtualSectionProcessorMixin",
    "_build_marker_title_ranges",
    "_check_special_form_support",
    "_dedupe_markers",
    "_find_marker_after",
    "_find_lettered_marker_after",
    "_safe_virtual_document_text",
    "_is_table_placeholder_dominant_text",
    "_infer_suffix_from_uri",
    "_normalize_optional_string",
    "_normalize_whitespace",
]
