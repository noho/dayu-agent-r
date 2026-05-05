"""模型完成终态原因枚举。

:class:`FinishReason` 用于 Runner / Engine 事件层标注 LLM 完成原因。
成员名 / 值表参考 OpenAI 风格协议；非 OpenAI provider 必须由 Runner 适配
后再向上提升为本枚举之一。
"""

from __future__ import annotations

from enum import StrEnum


class FinishReason(StrEnum):
    """LLM 完成原因。

    成员：

    - ``STOP``：自然结束。
    - ``LENGTH``：达到 max_tokens 等长度限制。
    - ``TOOL_CALLS``：因触发工具调用而结束。
    - ``CONTENT_FILTER``：被内容过滤器拦截。
    - ``ERROR``：因协议或运行时错误结束。
    """

    STOP = "stop"
    LENGTH = "length"
    TOOL_CALLS = "tool_calls"
    CONTENT_FILTER = "content_filter"
    ERROR = "error"


__all__ = ["FinishReason"]
