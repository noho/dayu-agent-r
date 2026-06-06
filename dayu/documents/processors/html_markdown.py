"""HTML 到 Markdown 渲染工具。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RenderedMarkdownResult:
    """HTML 渲染为 Markdown 的结果。"""

    markdown: str
    renderer_source: str


def render_html_to_markdown(html: str, *, preferred_renderer: str = "markdownify") -> RenderedMarkdownResult:
    """将正文 HTML 渲染为 Markdown。"""

    renderers = _resolve_renderer_order(preferred_renderer)
    last_error: Exception | None = None
    for renderer_name in renderers:
        try:
            if renderer_name == "markdownify":
                markdown = _render_with_markdownify(html)
            else:
                markdown = _render_with_html2text(html)
        except Exception as exc:
            last_error = exc
            continue
        if markdown.strip():
            return RenderedMarkdownResult(
                markdown=markdown.strip(),
                renderer_source=renderer_name,
            )
    if last_error is not None:
        raise RuntimeError(f"HTML 渲染失败: {last_error}") from last_error
    raise RuntimeError("HTML 渲染失败：未产出 Markdown")


def _resolve_renderer_order(preferred_renderer: str) -> tuple[str, ...]:
    """解析渲染器尝试顺序。"""

    normalized = str(preferred_renderer or "markdownify").strip().lower()
    if normalized == "html2text":
        return ("html2text", "markdownify")
    return ("markdownify", "html2text")


def _render_with_markdownify(html: str) -> str:
    """使用 markdownify 渲染 HTML。"""

    from markdownify import markdownify

    return markdownify(
        html,
        heading_style="ATX",
        bullets="-",
        escape_underscores=False,
        escape_asterisks=False,
        strong_em_symbol="*",
    ).strip()


def _render_with_html2text(html: str) -> str:
    """使用 html2text 渲染 HTML。"""

    import html2text

    parser = html2text.HTML2Text()
    parser.body_width = 0
    parser.ignore_images = True
    parser.ignore_emphasis = False
    parser.ignore_links = False
    parser.unicode_snob = True
    return parser.handle(html).strip()

