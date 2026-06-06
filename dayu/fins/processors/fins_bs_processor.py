"""fins 业务域 BS 处理器。

该处理器复用 engine ``BSProcessor`` 的通用解析能力，
并在业务域层补充：
- 表格金融语义标注（通过 ``relabel_tables``）
- SEC/EDGAR HTML 预处理与 layout 表格检测规则
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from dayu.documents.processors.bs_processor import BSProcessor
from dayu.documents.processors.source import Source

from .financial_enhancer import FinsProcessorMixin, relabel_tables
from .sec_html_rules import is_sec_layout_table, strip_edgar_sgml_envelope


class FinsBSProcessor(FinsProcessorMixin, BSProcessor):
    """fins 业务域 BS 处理器。

    继承链：``FinsBSProcessor → BSProcessor``

    在 engine 通用解析基础上补充：
    - 表格金融语义标注（``relabel_tables``）
    - SEC 特有的 layout 表格检测：

      * Section heading 横线表（如 ``Item 7. MD&A ────``）
      * SEC 封面页元数据表（法律声明 / 勾选框，≤5 行）
    """

    PARSER_VERSION = "fins_bs_processor_v1.0.0"

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
            ValueError: 源文件不存在或参数非法时抛出。
            RuntimeError: 解析失败时抛出。
        """

        super().__init__(source=source, form_type=form_type, media_type=media_type)
        relabel_tables(self._tables)

    def _load_html_content(self, source_path: Path) -> str:
        """读取并预处理 HTML 文件内容。

        Fins 路径在通用读取基础上补充 EDGAR SGML 信封剥离，以保证 exhibit
        HTML 在进入 BeautifulSoup 前就去掉外围元数据噪声。

        Args:
            source_path: HTML 文件路径。

        Returns:
            预处理后的 HTML 内容字符串。

        Raises:
            OSError: 读取失败时抛出。
        """

        raw = super()._load_html_content(source_path)
        return strip_edgar_sgml_envelope(raw)

    @staticmethod
    def _extra_layout_table_check(row_count: int, col_count: int, text: str) -> bool:
        """SEC 特有的 layout 表格检测。

        规则真源统一位于 ``sec_html_rules``。

        Args:
            row_count: 表格行数。
            col_count: 表格列数。
            text: 表格规范化后的纯文本。

        Returns:
            是否为 layout 表格。
        """
        del col_count
        return is_sec_layout_table(row_count, text)
