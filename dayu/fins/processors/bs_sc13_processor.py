"""基于 BeautifulSoup 的 SC 13 系列表单专项处理器。

SC 13D/SC 13G 是 SEC 要求大额持股者提交的披露表单：
- **Schedule 13D** (17 CFR §240.13d-101)：取得 5% 以上有表决权证券
  时需在 10 日内提交的详细披露声明，内含 7 个标准 Item。
- **Schedule 13G** (17 CFR §240.13d-102)：符合豁免条件的简化披露报告，
  包含 10 个标准 Item（多数仅需简短回答或勾选"不适用"）。

与 ``Sc13FormProcessor``（基于 edgartools/SecProcessor）平行：
- HTML 解析完全由 BeautifulSoup 驱动，无 edgartools 黑箱；
- 共享同一套 ``Item N + SIGNATURE + Schedule A + Exhibit`` marker 扫描逻辑；
- 搜索实现 token 级回退，提升短文档的搜索召回率。

设计决策：
- 不需要 XBRL 能力（SC 13D/G 不含标准化财务报表）。
- 搜索使用两级回退策略：精确短语匹配 → token OR 匹配。
  SC 13 表单通常极短且模板化，标准化财务术语稀少，
  token 回退可从局部单词匹配中提取上下文 snippet，提高搜索命中率。
- 继承 ``FinsBSProcessor`` 而非 ``_BaseBsReportFormProcessor``，
  因 SC 13 不需要 XBRL 延迟加载逻辑。

SEC 规则依据：
- Securities Exchange Act of 1934, Section 13(d)
- SEC Rule 13d-1, 13d-2 (17 CFR §240.13d-1, §240.13d-2)
- Schedule 13D (17 CFR §240.13d-101)
- Schedule 13G (17 CFR §240.13d-102)
"""

from __future__ import annotations

from typing import Optional

from dayu.documents.processors.source import Source

from .fins_bs_processor import FinsBSProcessor
from .sc13_form_common import _SC13_FORMS, _build_sc13_markers
from .sec_form_section_common import (
    _VirtualSectionProcessorMixin,
    _check_special_form_support,
)


class BsSc13FormProcessor(_VirtualSectionProcessorMixin, FinsBSProcessor):
    """基于 BeautifulSoup 的 SC 13 系列表单专项处理器。

    继承链：
    ``BsSc13FormProcessor → _VirtualSectionProcessorMixin → FinsBSProcessor → BSProcessor``

    与 ``Sc13FormProcessor``（基于 SecProcessor）平行，
    共享 ``_build_sc13_markers()`` marker 策略。
    不包含 XBRL 能力（SC 13D/G 不含标准化财务报表）。

    搜索增强：
    - 第一级：精确短语匹配（继承 ``_VirtualSectionProcessorMixin``）。
    - 第二级：token OR 回退——多词查询拆分为 token，任一匹配即命中。
    """

    PARSER_VERSION = "bs_sc13_section_processor_v1.0.0"
    _ENABLE_TOKEN_FALLBACK_SEARCH = True

    # SC 13 至少需要 3 个虚拟章节（Item 序列 + 尾段标记）
    _MIN_VIRTUAL_SECTIONS = 3

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

        支持条件：表单类型为 SC 13D/G 系列，且文件可被 BSProcessor 解析
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
            supported_forms=_SC13_FORMS,
            base_supports_fn=FinsBSProcessor.supports,
            extra_media_keywords=frozenset({"text/plain"}),
            extra_suffixes=frozenset({".txt"}),
        )

    def _build_markers(self, full_text: str) -> list[tuple[int, Optional[str]]]:
        """构建 SC 13 Item + 尾段边界标记。

        复用 ``_build_sc13_markers()``，该函数仅依赖纯文本正则扫描，
        与底层 HTML 解析引擎无关。

        Args:
            full_text: 文档全文。

        Returns:
            ``(start_index, title)`` 列表。

        Raises:
            RuntimeError: 构建失败时抛出。
        """

        return _build_sc13_markers(full_text)


__all__ = ["BsSc13FormProcessor"]
