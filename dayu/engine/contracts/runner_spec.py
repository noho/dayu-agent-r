"""Provider 请求扩展、Runner 规约与调用选项契约。

本模块提供四种已知 provider 的强类型扩展：

- :class:`OpenAIReasoningExtension`
- :class:`AnthropicThinkingExtension`
- :class:`GeminiThinkingExtension`
- :class:`QwenThinkingExtension`

并以 :data:`ProviderRequestExtension` 联合统一暴露。Phase 0 不引入
``ValidatedProviderRequestExtension`` / ``FallbackStrategy`` /
``ResponseFormat`` 等暂无消费方的辅助类型。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias


class OpenAIReasoningEffort(StrEnum):
    """OpenAI reasoning effort 枚举。

    成员：

    - ``LOW`` / ``MEDIUM`` / ``HIGH``：标准三档推理强度。
    - ``NONE``：显式关闭推理（OLD ``llm_models.json`` 已使用
      ``"none"`` 字面量）。
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class OpenAIReasoningExtension:
    """OpenAI 推理强度扩展。

    :param reasoning_effort: 推理强度等级。
    """

    reasoning_effort: OpenAIReasoningEffort


@dataclass(frozen=True, slots=True)
class AnthropicThinkingExtension:
    """Anthropic thinking 扩展。

    :param enabled: 是否启用 thinking。
    :param budget_tokens: thinking 预算 token 数。
    """

    enabled: bool
    budget_tokens: int


@dataclass(frozen=True, slots=True)
class GeminiThinkingExtension:
    """Gemini thinking 扩展。

    :param thinking_budget: thinking 预算。
    :param include_thoughts: 是否在响应中包含 thoughts。
    """

    thinking_budget: int
    include_thoughts: bool


@dataclass(frozen=True, slots=True)
class QwenThinkingExtension:
    """Qwen thinking 扩展。

    :param enable_thinking: 是否启用 thinking。
    """

    enable_thinking: bool


ProviderRequestExtension: TypeAlias = (
    OpenAIReasoningExtension
    | AnthropicThinkingExtension
    | GeminiThinkingExtension
    | QwenThinkingExtension
)
"""provider 请求扩展封闭联合。"""


@dataclass(frozen=True, slots=True)
class RunnerSpec:
    """Runner 规约。

    Engine 用本规约创建 / 选择 Runner；具体实现 / 装配由 Host / 配置 adapter
    负责。

    :param provider: provider 名称（中性字符串，由 Host 与 Runner 实现
        约定）。
    :param model: 模型名。
    :param endpoint: provider 端点 URL。
    :param api_key_ref: API key 引用名（不直接落 key 明文）。
    :param headers: 附加头映射。
    :param supports_tool_calling: 该 Runner 是否支持工具调用。
    :param supports_streaming: 该 Runner 是否支持流式输出。
    :param supports_stream_usage: 该 Runner 在流式协议下是否支持
        ``stream_options.include_usage``。仅当为 ``True`` 时 Runner
        会在请求中追加 ``stream_options.include_usage=True``；为
        ``False`` 时**不**写入该字段。
    :param default_timeout_seconds: 默认请求超时秒数。
    :param max_retries: 最大重试次数。
    :param provider_request: provider 请求扩展；为 ``None`` 表示不带扩展。
    """

    provider: str
    model: str
    endpoint: str
    api_key_ref: str
    headers: Mapping[str, str]
    supports_tool_calling: bool
    supports_streaming: bool
    supports_stream_usage: bool
    default_timeout_seconds: float
    max_retries: int
    provider_request: ProviderRequestExtension | None


@dataclass(frozen=True, slots=True)
class RunnerCallOptions:
    """Runner 单次调用参数。

    :param temperature: 温度参数；为 ``None`` 表示沿用 Runner 默认。
    :param max_tokens: 最大输出 token 数；为 ``None`` 表示沿用默认。
    :param top_p: top-p 采样；为 ``None`` 表示沿用默认。
    :param stream: 是否流式输出。
    """

    temperature: float | None
    max_tokens: int | None
    top_p: float | None
    stream: bool


__all__ = [
    "OpenAIReasoningEffort",
    "OpenAIReasoningExtension",
    "AnthropicThinkingExtension",
    "GeminiThinkingExtension",
    "QwenThinkingExtension",
    "ProviderRequestExtension",
    "RunnerSpec",
    "RunnerCallOptions",
]
