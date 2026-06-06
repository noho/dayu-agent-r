"""处理器层包。

该包提供面向文档读取的处理器协议与通用实现骨架。
"""

from .base import DocumentProcessor, PageAwareProcessor
from .html_extraction import ExtractedHtmlContent, ExtractionQualityReport, extract_main_content
from .html_markdown import RenderedMarkdownResult, render_html_to_markdown
from .html_normalization import NormalizedHtmlResult, normalize_html_fragment
from .html_pipeline import HtmlPipelineResult, HtmlPipelineStageError, convert_html_to_llm_markdown
from .processor_registry import ProcessorRegistry
from .registry import build_engine_processor_registry
from .search_utils import SEARCH_PER_SECTION_LIMIT, SEARCH_SNIPPET_MAX_CHARS
from .source import Source
from .table_utils import parse_html_table_dataframe
from .text_utils import PREVIEW_MAX_CHARS, infer_suffix_from_uri, normalize_whitespace

__all__ = [
    "Source",
    "DocumentProcessor",
    "PageAwareProcessor",
    "ProcessorRegistry",
    "build_engine_processor_registry",
    "ExtractedHtmlContent",
    "ExtractionQualityReport",
    "extract_main_content",
    "NormalizedHtmlResult",
    "normalize_html_fragment",
    "RenderedMarkdownResult",
    "render_html_to_markdown",
    "HtmlPipelineResult",
    "HtmlPipelineStageError",
    "convert_html_to_llm_markdown",
    "infer_suffix_from_uri",
    "parse_html_table_dataframe",
    "normalize_whitespace",
    "PREVIEW_MAX_CHARS",
    "SEARCH_PER_SECTION_LIMIT",
    "SEARCH_SNIPPET_MAX_CHARS",
]
