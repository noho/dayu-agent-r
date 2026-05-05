"""OpenAI-compatible Runner 实现包。

本包提供 :class:`~dayu.engine.runners.openai.runner.AsyncOpenAIRunner`，
是 :class:`~dayu.engine.contracts.runner.AsyncRunner` 协议在 OpenAI
兼容协议（OpenAI / DeepSeek / Anthropic OpenAI gateway / Gemini OpenAI
gateway / Qwen OpenAI gateway 等）下的实现。

包内分模块按职责分离：

- :mod:`._types`：私有 ``TypedDict`` / dataclass / 枚举（不出包）。
- :mod:`.payload`：请求 payload 构建与 ProviderRequestExtension 投影。
- :mod:`.error_classifier`：HTTP / 异常 → :class:`RunnerHTTPErrorCode`。
- :mod:`.retry_policy`：``Retry-After`` / 指数退避决策。
- :mod:`.cancellation_helpers`：``await_or_cancel`` 协作式取消辅助。
- :mod:`.http_client`：``aiohttp.ClientSession`` 持有与幂等关闭。
- :mod:`.xml_tag_extractor`：流式 ``<thought>`` 标签状态机。
- :mod:`.reasoning_protocol`：Gemini reasoning 协议探测。
- :mod:`.tool_call_aggregator`：流式 tool call delta 聚合。
- :mod:`.sse_parser`：SSE 行解析与事件归一。
- :mod:`.non_stream_parser`：非流式 JSON 响应解析。
- :mod:`.runner`：组合上述模块的 :class:`AsyncOpenAIRunner` 顶层实现。

实现类**不**在 :mod:`dayu.engine` re-export，需要时由调用方显式从
:mod:`.runner` 子模块导入。
"""

from __future__ import annotations

__all__: list[str] = []
