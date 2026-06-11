"""doc_tools 专用的处理器工厂。

根据本地文件路径创建合适的 DocumentProcessor 实例。
支持 Markdown（*.md/*.markdown）、HTML（*.html/*.htm）、
Docling JSON（*_docling.json）三类文件。
其他格式返回 None，交由调用方降级处理。
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Optional

from .base import DocumentProcessor
from .local_file_source import LocalFileSource
from .processor_registry import ProcessorRegistry
from .registry import build_documents_processor_registry

# 模块级单例：避免每次调用都重新注册处理器
_DOCUMENTS_PROCESSOR_REGISTRY: ProcessorRegistry | None = None

# 文件后缀到 MIME 类型的映射
_SUFFIX_TO_MEDIA_TYPE: dict[str, str] = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
    ".xhtml": "text/html",
    ".json": "application/json",
}


def _get_documents_processor_registry() -> ProcessorRegistry:
    """获取/初始化 documents 处理器注册表（单例）。

    Args:
        无。

    Returns:
        ProcessorRegistry 实例。

    Raises:
        RuntimeError: 构建注册表失败时抛出。
    """
    global _DOCUMENTS_PROCESSOR_REGISTRY
    if _DOCUMENTS_PROCESSOR_REGISTRY is None:
        _DOCUMENTS_PROCESSOR_REGISTRY = build_documents_processor_registry()
    return _DOCUMENTS_PROCESSOR_REGISTRY


def create_doc_file_processor(file_path: Path) -> Optional[DocumentProcessor]:
    """根据本地文件路径创建合适的文档处理器。

    按优先级探测三个处理器：
    1. DoclingProcessor：命中 *_docling.json 文件
    2. MarkdownProcessor：命中 *.md/*.markdown
    3. BSProcessor：命中 *.html/*.htm

    其他格式返回 None，交由调用方降级处理。

    Args:
        file_path: 本地文件绝对路径。

    Returns:
        DocumentProcessor 实例，或 None（不支持的格式）。

    Raises:
        ValueError: 处理器创建失败时可能抛出。
        OSError: 文件不可读时可能抛出。
    """
    uri = str(file_path)
    suffix = file_path.suffix.lower()

    # 推断 media_type：优先查表，fallback 到 mimetypes
    media_type = _SUFFIX_TO_MEDIA_TYPE.get(suffix)
    if media_type is None:
        media_type, _ = mimetypes.guess_type(uri)

    # 构建 Source
    source = LocalFileSource(
        path=file_path,
        uri=uri,
        media_type=media_type,
    )

    # 通过 ProcessorRegistry 选择处理器
    registry = _get_documents_processor_registry()
    processor_cls = registry.resolve(source, media_type=media_type)
    if processor_cls is None:
        return None

    # 创建处理器实例
    return processor_cls(source=source, media_type=media_type)
