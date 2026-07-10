"""Web 搜索 provider 事实到 LLM-facing 工具输出的投影。

provider 只负责返回结构化检索事实；本模块负责把这些事实转换为
`search_web` 成功 outcome 中给 LLM 消费的摘要、下一步动作和提示。
"""

from __future__ import annotations

from typing import TypedDict

from .web_search_providers import SearchResultRow, SearchWebProviderResult
from .web_tool_projection_text import (
    SEARCH_WEB_NEXT_ACTION_FETCH_PAGE,
    SEARCH_WEB_NEXT_ACTION_REFINE_QUERY,
    SEARCH_WEB_NO_RESULT_HINT,
    SEARCH_WEB_NO_RESULT_SUMMARY,
)

_SEARCH_WEB_SNIPPET_PREVIEW_CHARS = 240


class SearchWebOutput(TypedDict):
    """`search_web` 对外返回给 LLM 的成功载荷。"""

    query: str
    domains: list[str]
    total: int
    preferred_result: SearchResultRow | None
    preferred_result_summary: str
    next_action: str
    next_action_args: dict[str, str]
    hint: str
    results: list[SearchResultRow]


def build_search_web_output(provider_result: SearchWebProviderResult) -> SearchWebOutput:
    """把 provider 检索事实投影为 `search_web` 的 LLM-facing 输出。

    Args:
        provider_result: provider 返回的结构化检索事实。

    Returns:
        保持既有 public JSON 形状的 `search_web` 成功载荷，其中
        `next_action` 是给 LLM 的工具使用指导，不是 provider 事实。

    Raises:
        无。
    """

    preferred_result = provider_result["preferred_result"]
    return {
        "query": provider_result["query"],
        "domains": provider_result["domains"],
        "total": provider_result["total"],
        "preferred_result": preferred_result,
        "preferred_result_summary": _build_search_web_preferred_summary(
            preferred_result=preferred_result,
        ),
        "next_action": _build_search_web_next_action(preferred_result=preferred_result),
        "next_action_args": _build_search_web_next_action_args(preferred_result=preferred_result),
        "hint": _build_search_web_hint(preferred_result=preferred_result),
        "results": provider_result["results"],
    }


def _normalize_whitespace(value: str) -> str:
    """规整投影文案中的空白。

    Args:
        value: 原始文本。

    Returns:
        合并连续空白后的文本。

    Raises:
        无。
    """

    return " ".join(value.split())


def _build_search_web_preferred_summary(
    *,
    preferred_result: SearchResultRow | None,
) -> str:
    """构建 `search_web` 的首选结果摘要。

    Args:
        preferred_result: 首选结果；无结果时为 `None`。

    Returns:
        面向 LLM 的单行摘要。

    Raises:
        无。
    """

    if preferred_result is None:
        return SEARCH_WEB_NO_RESULT_SUMMARY

    title = _normalize_whitespace(preferred_result["title"].strip())
    url = preferred_result["url"].strip()
    published_date = preferred_result["published_date"].strip()
    snippet = _normalize_whitespace(preferred_result["snippet"].strip())
    snippet_preview = snippet[:_SEARCH_WEB_SNIPPET_PREVIEW_CHARS]
    if len(snippet) > _SEARCH_WEB_SNIPPET_PREVIEW_CHARS:
        snippet_preview = f"{snippet_preview}..."

    summary_parts = ["首选结果"]
    if title:
        summary_parts.append(f"标题：{title}")
    if published_date:
        summary_parts.append(f"日期：{published_date}")
    if url:
        summary_parts.append(f"URL：{url}")
    if snippet_preview:
        summary_parts.append(f"摘要：{snippet_preview}")
    return "；".join(summary_parts)


def _build_search_web_next_action(*, preferred_result: SearchResultRow | None) -> str:
    """构建 `search_web` 的下一步动作。

    Args:
        preferred_result: 首选结果；无结果时为 `None`。

    Returns:
        下一步动作名称或动作标签。

    Raises:
        无。
    """

    if preferred_result is None:
        return SEARCH_WEB_NEXT_ACTION_REFINE_QUERY
    return SEARCH_WEB_NEXT_ACTION_FETCH_PAGE


def _build_search_web_next_action_args(
    *,
    preferred_result: SearchResultRow | None,
) -> dict[str, str]:
    """构建 `search_web` 的下一步动作参数。

    Args:
        preferred_result: 首选结果；无结果时为 `None`。

    Returns:
        下一步动作参数字典。

    Raises:
        无。
    """

    if preferred_result is None:
        return {}
    return {"url": preferred_result["url"].strip()}


def _build_search_web_hint(
    *,
    preferred_result: SearchResultRow | None,
) -> str:
    """构建 `search_web` 成功返回的下一步提示。

    Args:
        preferred_result: 首选结果；无结果时为 `None`。

    Returns:
        直接指向下一步动作的提示文案。

    Raises:
        无。
    """

    if preferred_result is None:
        return SEARCH_WEB_NO_RESULT_HINT

    url = preferred_result["url"].strip()
    title = _normalize_whitespace(preferred_result["title"].strip())
    target_label = f"《{title}》" if title else url
    return (
        f"优先抓取首选结果正文：下一步直接调用 fetch_web_page(url='{url}') 读取 {target_label}。"
        "只有当首选结果抓取失败或正文不相关时，再回看 results 中其他候选。"
    )
