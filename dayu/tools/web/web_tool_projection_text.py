"""Web 工具投影给 LLM 的共享文案。

本模块只承载 Web 工具边界生成 outcome、恢复提示和搜索下一步指导时
需要复用的业务可读文本。provider、HTTP 抓取和浏览器执行路径只应返回
结构化事实或中性执行状态，不应自行生成这些 LLM-facing 文案。
"""

from __future__ import annotations

from typing import Final

WEB_SEARCH_CANCELLED_MESSAGE: Final[str] = "网页搜索工具调用已停止。"
"""search_web 被 Host 取消后投影给 LLM 的安全说明。"""

WEB_FETCH_CANCELLED_MESSAGE: Final[str] = "网页抓取工具调用已停止。"
"""fetch_web_page 被 Host 取消后投影给 LLM 的安全说明。"""

WEB_CANCELLED_HINT: Final[str] = "当前工具调用已停止；如仍需要该结果，请等待用户确认后再重新发起。"
"""Web 工具取消后投影给 LLM 的业务可读恢复提示。"""

WEB_SEARCH_PROVIDER_UNAVAILABLE_HINT: Final[str] = (
    "[retry_later_or_use_known_source] Search providers are currently unavailable; "
    "retry later, refine the query, or continue with a known source URL."
)
"""search_web provider 不可用时投影给 LLM 的恢复提示。"""

WEB_SEARCH_PROVIDER_RESPONSE_INVALID_HINT: Final[str] = (
    "[change_source] The search provider returned an unrecognized response shape; "
    "use another provider or continue with a known source URL."
)
"""search_web provider response 漂移时投影给 LLM 的换源提示。"""

WEB_SEARCH_RESPONSE_BODY_TOO_LARGE_HINT: Final[str] = (
    "[change_source] The search provider response exceeded the safe processing limit; "
    "use another provider or continue with a known source URL."
)
"""search_web provider response 超限时投影给 LLM 的换源提示。"""

SEARCH_WEB_NEXT_ACTION_FETCH_PAGE: Final[str] = "fetch_web_page"
"""search_web 找到首选结果时投影给 LLM 的下一步工具名。"""

SEARCH_WEB_NEXT_ACTION_REFINE_QUERY: Final[str] = "refine_query"
"""search_web 未找到首选结果时投影给 LLM 的下一步动作标签。"""

SEARCH_WEB_NO_RESULT_SUMMARY: Final[str] = "未找到可直接抓取正文的公开网页结果。"
"""search_web 无首选结果时投影给 LLM 的摘要。"""

SEARCH_WEB_NO_RESULT_HINT: Final[str] = (
    "当前没有可直接抓取的网页正文。下一步应改写 query，或放宽 domains/recency_days 后重新调用 "
    "search_web；不要对空结果调用 fetch_web_page。"
)
"""search_web 无首选结果时投影给 LLM 的恢复指导。"""
