"""documents 处理器注册构建器。

本模块仅负责构建 documents 包默认共享的处理器注册表，不包含业务域扩展处理器。
调用方可在此基础上继续注册业务特化处理器。
"""

from __future__ import annotations

from .bs_processor import BSProcessor
from .docling_processor import DoclingProcessor
from .markdown_processor import MarkdownProcessor
from .processor_registry import ProcessorRegistry

_GENERIC_PROCESSOR_PRIORITY = 10


def build_documents_processor_registry() -> ProcessorRegistry:
    """构建 documents 默认处理器注册表。

    当前策略：
    - 注册 `DoclingProcessor`（优先处理 `*_docling.json`）。
    - 注册 `MarkdownProcessor`（处理 `*.md/*.markdown`）。
    - 注册 `BSProcessor` 作为 HTML 兜底处理器。
    - 当前新增的 `html_extraction/html_normalization/html_markdown/html_pipeline`
      仅作为可复用 HTML 原语，供 `web_tools` 与未来的 `HTMLProcessor`
      复用；本次不改变默认注册顺序。

    Args:
        无。

    Returns:
        新创建并完成注册的 `ProcessorRegistry` 实例。

    Raises:
        RuntimeError: 注册流程失败时抛出。
    """

    registry = ProcessorRegistry()
    registry.register(
        DoclingProcessor,
        name="docling_processor",
        priority=_GENERIC_PROCESSOR_PRIORITY,
        overwrite=True,
    )
    registry.register(
        MarkdownProcessor,
        name="markdown_processor",
        priority=_GENERIC_PROCESSOR_PRIORITY,
        overwrite=True,
    )
    registry.register(
        BSProcessor,
        name="bs_processor",
        priority=_GENERIC_PROCESSOR_PRIORITY,
        overwrite=True,
    )
    return registry
