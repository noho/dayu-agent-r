"""provider 私有 reasoning 协议探测。

部分 provider（典型为 Gemini）把推理链以 ``<thought>...</thought>``
XML 标签形式与正文混杂回传，需要在 Runner 侧探测开关并剥离。

本模块基于 :class:`RunnerSpec.provider_request` 中的
:class:`GeminiThinkingExtension.include_thoughts` 标志，决定是否启用
``<thought>`` 标签提取。其它 provider（OpenAI / Anthropic / Qwen）的
推理链统一走 OpenAI 协议原生 ``delta.reasoning_content`` 通道，本探测
返回「无标签」钩子。

返回 :class:`_ReasoningProtocolHook`：

- ``tag_name == "thought"``：调用方需用
  :class:`StreamingXMLTagExtractor` 剥离正文里的 ``<thought>`` 段。
- ``tag_name is None``：无私有协议钩子；正文与 ``reasoning_content``
  各走各路。
"""

from __future__ import annotations

from dayu.engine.contracts.runner_spec import (
    AnthropicThinkingExtension,
    GeminiThinkingExtension,
    OpenAIReasoningExtension,
    ProviderRequestExtension,
    QwenThinkingExtension,
)
from dayu.engine.runners.openai._types import _ReasoningProtocolHook

_THOUGHT_TAG_NAME: str = "thought"


def detect_reasoning_protocol_hook(
    provider_request: ProviderRequestExtension | None,
) -> _ReasoningProtocolHook:
    """根据 provider 请求扩展决定 reasoning 协议钩子。

    :param provider_request: ``RunnerSpec.provider_request``；为
        ``None`` 表示无 provider 私有扩展。
    :returns: :class:`_ReasoningProtocolHook` 钩子。

    - :class:`GeminiThinkingExtension(include_thoughts=True)` →
      ``tag_name="thought"``。
    - 其它一律 ``tag_name=None``。
    """

    if provider_request is None:
        return _ReasoningProtocolHook(tag_name=None)
    match provider_request:
        case GeminiThinkingExtension(include_thoughts=include_thoughts):
            if include_thoughts:
                return _ReasoningProtocolHook(tag_name=_THOUGHT_TAG_NAME)
            return _ReasoningProtocolHook(tag_name=None)
        case (
            OpenAIReasoningExtension()
            | AnthropicThinkingExtension()
            | QwenThinkingExtension()
        ):
            return _ReasoningProtocolHook(tag_name=None)


__all__ = ["detect_reasoning_protocol_hook"]
