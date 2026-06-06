"""HTML 四段式流水线编排。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .html_extraction import ExtractedHtmlContent, extract_main_content
from .html_markdown import render_html_to_markdown
from .html_normalization import normalize_html_fragment


@dataclass(frozen=True)
class HtmlPipelineResult:
    """HTML 四段式流水线结果。"""

    title: str
    html: str
    markdown: str
    extractor_source: str
    renderer_source: str
    quality_flags: tuple[str, ...]
    content_stats: dict[str, Any]
    normalization_applied: bool


class HtmlPipelineStageError(RuntimeError):
    """HTML 四段式流水线阶段错误。"""

    def __init__(
        self,
        stage: str,
        message: str,
        *,
        extractor_source: str = "",
        quality_flags: tuple[str, ...] = (),
        content_stats: dict[str, Any] | None = None,
    ) -> None:
        """初始化阶段错误。"""

        super().__init__(message)
        self.stage = stage
        self.extractor_source = extractor_source
        self.quality_flags = quality_flags
        self.content_stats = content_stats or {}


def convert_html_to_llm_markdown(html: str, *, url: str = "") -> HtmlPipelineResult:
    """执行 HTML 四段式流水线。"""

    if not str(html or "").strip():
        raise HtmlPipelineStageError("extract", "HTML 为空，无法抽取正文")

    try:
        extracted = extract_main_content(html, url=url)
    except Exception as exc:
        raise HtmlPipelineStageError("extract", f"HTML 主体抽取失败: {exc}") from exc

    if not extracted.html.strip() or not extracted.text.strip():
        raise HtmlPipelineStageError(
            "extract",
            "HTML 主体抽取失败：正文为空",
            extractor_source=extracted.extractor_source,
            quality_flags=extracted.quality_report.quality_flags,
            content_stats=extracted.quality_report.content_stats,
        )

    try:
        normalized = normalize_html_fragment(extracted.html)
    except Exception as exc:
        raise HtmlPipelineStageError(
            "normalize",
            f"HTML 规范化失败: {exc}",
            extractor_source=extracted.extractor_source,
            quality_flags=extracted.quality_report.quality_flags,
            content_stats=extracted.quality_report.content_stats,
        ) from exc

    try:
        rendered = render_html_to_markdown(normalized.html)
    except Exception as exc:
        raise HtmlPipelineStageError(
            "render",
            f"HTML 渲染失败: {exc}",
            extractor_source=extracted.extractor_source,
            quality_flags=extracted.quality_report.quality_flags,
            content_stats={
                **extracted.quality_report.content_stats,
                **normalized.content_stats,
            },
        ) from exc

    markdown = _ensure_title_prefix(
        title=extracted.title,
        markdown=rendered.markdown,
    )
    return HtmlPipelineResult(
        title=extracted.title,
        html=normalized.html,
        markdown=markdown,
        extractor_source=extracted.extractor_source,
        renderer_source=rendered.renderer_source,
        quality_flags=extracted.quality_report.quality_flags,
        content_stats={
            **extracted.quality_report.content_stats,
            **normalized.content_stats,
            "markdown_length": len(markdown),
        },
        normalization_applied=normalized.normalization_applied,
    )


def _ensure_title_prefix(*, title: str, markdown: str) -> str:
    """确保 Markdown 顶部保留标题。"""

    normalized_markdown = str(markdown or "").strip()
    normalized_title = str(title or "").strip()
    if not normalized_title:
        return normalized_markdown
    if _markdown_heading_matches_title(markdown=normalized_markdown, title=normalized_title):
        return normalized_markdown
    if normalized_title.lower() in normalized_markdown[:120].lower():
        return normalized_markdown
    return f"# {normalized_title}\n\n{normalized_markdown}".strip()


def _markdown_heading_matches_title(*, markdown: str, title: str) -> bool:
    """判断 Markdown 首个标题是否已经表达页面标题。

    Args:
        markdown: 已渲染的 Markdown 文本。
        title: 页面标题。

    Returns:
        若首个 Markdown 标题与页面标题等价，返回 ``True``。

    Raises:
        无。
    """

    normalized_markdown = str(markdown or "").strip()
    normalized_title = str(title or "").strip()
    if not normalized_markdown.startswith("#") or not normalized_title:
        return False

    first_line = normalized_markdown.splitlines()[0].lstrip("#").strip().lower()
    return first_line == normalized_title.lower()
