"""基于 BeautifulSoup 的 8-K 表单专项处理器。

8-K 是美国上市公司向 SEC 提交的当期报告 (Current Report)，
用于披露重大事件（Material Events）。典型 8-K 内容为简短事件通知
加 Exhibit 附件引用。

与 ``EightKFormProcessor``（基于 edgartools/SecProcessor）平行：
- HTML 解析完全由 BeautifulSoup 驱动，无 edgartools 黑箱；
- 共享同一套 ``Item X.XX + SIGNATURE`` marker 扫描逻辑；
- 搜索实现 token 级回退，提升短文档的搜索召回率。

设计决策：
- 不需要 XBRL 能力（8-K 不含标准化财务报表）。
- 搜索使用两级回退策略：精确短语匹配→token OR 匹配。
  8-K 事件文档通常简短，标准化财务术语稀少，token 回退可
  从局部单词匹配中提取上下文 snippet，提高搜索命中率。
- 继承 ``FinsBSProcessor`` 而非 ``_BaseBsReportFormProcessor``，
  因为后者包含 XBRL 延迟加载逻辑（8-K 不需要）。

SEC 相关规则依据：
- SEC Form 8-K (17 CFR §249.308)
- SEC Release No. 33-8400 (Additional Form 8-K Disclosure Requirements)
"""

from __future__ import annotations

from typing import Optional

from dayu.documents.processors.source import Source

from .eight_k_form_common import _EIGHT_K_FORMS, _build_eight_k_markers
from .fins_bs_processor import FinsBSProcessor
from .sec_form_section_common import (
    _VirtualSectionProcessorMixin,
    _check_special_form_support,
)


class BsEightKFormProcessor(_VirtualSectionProcessorMixin, FinsBSProcessor):
    """基于 BeautifulSoup 的 8-K 表单专项处理器。

    继承链：
    ``BsEightKFormProcessor → _VirtualSectionProcessorMixin → FinsBSProcessor → BSProcessor``

    与 ``EightKFormProcessor``（基于 SecProcessor）平行，
    共享 ``_build_eight_k_markers()`` marker 策略。
    不包含 XBRL 能力（8-K 不含标准化财务报表）。

    搜索增强：
    - 第一级：精确短语匹配（继承 ``_VirtualSectionProcessorMixin``）。
    - 第二级：token OR 回退——多词查询拆分为 token，任一匹配即命中。
    """

    PARSER_VERSION = "bs_eight_k_section_processor_v1.0.0"

    # 虚拟章节最少数量阈值（8-K 通常只有 2-4 个 Item + SIGNATURE）
    _MIN_VIRTUAL_SECTIONS = 2
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

        支持条件：表单类型为 8-K 或 8-K/A，且文件可被 BSProcessor 解析
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
            supported_forms=_EIGHT_K_FORMS,
            base_supports_fn=FinsBSProcessor.supports,
        )

    def _build_markers(self, full_text: str) -> list[tuple[int, Optional[str]]]:
        """构建 8-K Item + Signature 边界标记。

        复用 ``_build_eight_k_markers()``，该函数仅依赖纯文本正则扫描，
        与底层 HTML 解析引擎无关。

        Args:
            full_text: 文档全文。

        Returns:
            ``(start_index, title)`` 列表。

        Raises:
            RuntimeError: 构建失败时抛出。
        """

        return _build_eight_k_markers(full_text)


__all__ = ["BsEightKFormProcessor"]
