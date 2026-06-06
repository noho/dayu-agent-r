"""fins 业务域 Markdown 处理器。

该处理器复用 engine `MarkdownProcessor` 的通用解析能力，
并在业务域层补充表格金融语义标注。
"""

from __future__ import annotations

from typing import Optional

from dayu.documents.processors.markdown_processor import MarkdownProcessor
from dayu.documents.processors.source import Source

from .financial_enhancer import FinsProcessorMixin, relabel_tables


class FinsMarkdownProcessor(FinsProcessorMixin, MarkdownProcessor):
    """fins 业务域 Markdown 处理器。"""

    PARSER_VERSION = "fins_markdown_processor_v1.0.0"

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
