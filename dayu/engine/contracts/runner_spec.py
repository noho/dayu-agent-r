"""Provider 请求扩展、Runner 规约与调用选项契约。

本模块提供已知 provider 的强类型扩展：

- :class:`OpenAIReasoningExtension`
- :class:`AnthropicThinkingExtension`
- :class:`DeepSeekThinkingExtension`
- :class:`MimoThinkingExtension`
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

from dayu.engine.contracts.structured_output import StructuredOutputCapability


class OpenAIReasoningEffort(StrEnum):
    """OpenAI reasoning effort 枚举。

    成员：

    - ``MINIMAL`` / ``LOW`` / ``MEDIUM`` / ``HIGH`` / ``XHIGH``：
      推理强度。
    - ``NONE``：显式关闭推理（OLD ``llm_models.json`` 已使用
      ``"none"`` 字面量）。
    """

    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    NONE = "none"


class DeepSeekReasoningEffort(StrEnum):
    """DeepSeek thinking effort 枚举。

    成员：

    - ``HIGH``：默认较高推理强度。
    - ``MAX``：更高推理强度。
    """

    HIGH = "high"
    MAX = "max"


class GeminiThinkingLevel(StrEnum):
    """Gemini thinking level 枚举。

    成员：

    - ``MINIMAL`` / ``LOW`` / ``MEDIUM`` / ``HIGH``：Gemini 3 系列
      thinking level。
    """

    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ClientCorrelationPolicy(StrEnum):
    """客户端关联 id 的 provider 协议 outbound 映射策略。

    本枚举的成员值表示 provider-protocol-specific outbound mapping
    policies，用于声明 Runner 是否以及如何把本地
    ``RunnerRequestIdentity.client_correlation_id`` 映射到请求协议字段。
    它们不是 provider-name branches；Host / Agent 不得按 provider 字符串
    分支治理行为。

    成员：

    - ``DISABLED``：不发送客户端关联 id。
    - ``OPENAI_X_CLIENT_REQUEST_ID``：OpenAI-compatible 协议下发送
      ``X-Client-Request-Id``。
    """

    DISABLED = "disabled"
    OPENAI_X_CLIENT_REQUEST_ID = "openai_x_client_request_id"


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
    :param budget_tokens: Anthropic manual extended thinking 预算 token
        数；``enabled=False`` 时必须为 ``None``，表示不传该字段。
    """

    enabled: bool
    budget_tokens: int | None = None

    def __post_init__(self) -> None:
        """校验 Anthropic manual thinking 预算字段。

        :raises ValueError: enabled / budget_tokens 组合不合法时抛出。
        """

        if self.enabled and self.budget_tokens is None:
            raise ValueError(
                "AnthropicThinkingExtension enabled=True requires "
                "budget_tokens"
            )
        if self.budget_tokens is not None and self.budget_tokens <= 0:
            raise ValueError(
                "AnthropicThinkingExtension budget_tokens must be > 0"
            )
        if not self.enabled and self.budget_tokens is not None:
            raise ValueError(
                "AnthropicThinkingExtension enabled=False must not set "
                "budget_tokens"
            )


@dataclass(frozen=True, slots=True)
class DeepSeekThinkingExtension:
    """DeepSeek thinking 扩展。

    :param enabled: 是否启用 DeepSeek thinking 模式。
    :param reasoning_effort: thinking 模式下的推理强度；为 ``None``
        表示不传该字段，沿用 provider 默认。
    """

    enabled: bool
    reasoning_effort: DeepSeekReasoningEffort | None = None

    def __post_init__(self) -> None:
        """校验 DeepSeek thinking effort 字段。

        :raises ValueError: 关闭 thinking 时仍设置 effort 则抛出。
        """

        if not self.enabled and self.reasoning_effort is not None:
            raise ValueError(
                "DeepSeekThinkingExtension enabled=False must not set "
                "reasoning_effort"
            )


@dataclass(frozen=True, slots=True)
class MimoThinkingExtension:
    """MiMo thinking 扩展。

    :param enabled: 是否启用 MiMo thinking 模式。
    """

    enabled: bool


@dataclass(frozen=True, slots=True)
class GeminiThinkingExtension:
    """Gemini thinking 扩展。

    :param thinking_budget: Gemini 2.5 thinking 预算；``None`` 表示不传。
    :param include_thoughts: 是否在响应中包含 thoughts summary；
        ``None`` 表示不传。
    :param thinking_level: Gemini 3 thinking level；``None`` 表示不传。
    """

    thinking_budget: int | None = None
    include_thoughts: bool | None = None
    thinking_level: GeminiThinkingLevel | None = None

    def __post_init__(self) -> None:
        """校验 Gemini thinking budget / level 互斥关系。

        :raises ValueError: 字段组合不合法时抛出。
        """

        if self.thinking_budget is None and self.thinking_level is None:
            if self.include_thoughts is None:
                raise ValueError(
                    "GeminiThinkingExtension requires at least one "
                    "thinking field"
                )
            return
        if self.thinking_budget is not None and self.thinking_level is not None:
            raise ValueError(
                "GeminiThinkingExtension cannot set both thinking_budget "
                "and thinking_level"
            )


@dataclass(frozen=True, slots=True)
class QwenThinkingExtension:
    """Qwen thinking 扩展。

    :param enable_thinking: 是否启用 thinking。
    :param thinking_budget: 思考过程最大 token 数；为 ``None`` 表示不传。
    """

    enable_thinking: bool
    thinking_budget: int | None = None

    def __post_init__(self) -> None:
        """校验 Qwen thinking 预算字段。

        :raises ValueError: 字段组合不合法时抛出。
        """

        if not self.enable_thinking and self.thinking_budget is not None:
            raise ValueError(
                "QwenThinkingExtension enable_thinking=False must not set "
                "thinking_budget"
            )
        if self.thinking_budget is not None and self.thinking_budget <= 0:
            raise ValueError("QwenThinkingExtension thinking_budget must be > 0")


ProviderRequestExtension: TypeAlias = (
    OpenAIReasoningExtension
    | AnthropicThinkingExtension
    | DeepSeekThinkingExtension
    | MimoThinkingExtension
    | GeminiThinkingExtension
    | QwenThinkingExtension
)
"""provider 请求扩展封闭联合。"""

OPENAI_CLIENT_REQUEST_ID_HEADER_NAME: str = "X-Client-Request-Id"
"""OpenAI-compatible 客户端关联 id header 名称。"""

_OPENAI_CLIENT_REQUEST_ID_HEADER_NAME_LOWER: str = (
    OPENAI_CLIENT_REQUEST_ID_HEADER_NAME.lower()
)


@dataclass(frozen=True, slots=True)
class RunnerSpec:
    """Runner 规约。

    Engine 用本规约创建 / 选择 Runner；具体实现 / 装配由 Host / 配置 adapter
    负责。

    :param provider: provider 名称（中性字符串，由 Host 与 Runner 实现
        约定）。
    :param model: 模型名。
    :param endpoint: provider 端点 URL。
    :param api_key_ref: API key 引用名（不直接落 key 明文）；``None`` 表示
        本地或免鉴权 provider 不需要 API key header。
    :param headers: 附加头映射。
    :param client_correlation_policy: 客户端关联 id 的 provider 协议 outbound
        映射策略。
    :param supports_tool_calling: 该 Runner 是否支持工具调用。
    :param supports_streaming: 该 Runner 是否支持流式输出。
    :param supports_stream_usage: 该 Runner 在流式协议下是否支持
        ``stream_options.include_usage``。仅当为 ``True`` 时 Runner
        会在请求中追加 ``stream_options.include_usage=True``；为
        ``False`` 时**不**写入该字段。
    :param structured_output_capability: Runner 支持的最高 structured-output
        capability。
    :param default_timeout_seconds: 默认请求超时秒数，必须为正数。
    :param max_retries: 最大重试次数，必须为非负整数。
    :param provider_request: provider 请求扩展；为 ``None`` 表示不带扩展。
    :param stream_idle_timeout_seconds: SSE 流字节空闲 timeout 秒数；
        为 ``None`` 表示不启用流空闲检测。Runner 在两个连续 byte chunk
        之间等待超过该秒数仍无新字节时，按 retriable timeout 处理。
    :param stream_idle_heartbeat_seconds: 流空闲心跳间隔秒数；只有在
        ``stream_idle_timeout_seconds`` 已启用时才允许设置；用于上层
        诊断日志的节流间隔，必须 ``<= stream_idle_timeout_seconds``。
        为 ``None`` 表示不输出心跳日志。
    """

    provider: str
    model: str
    endpoint: str
    api_key_ref: str | None
    headers: Mapping[str, str]
    client_correlation_policy: ClientCorrelationPolicy
    supports_tool_calling: bool
    supports_streaming: bool
    supports_stream_usage: bool
    structured_output_capability: StructuredOutputCapability
    default_timeout_seconds: float
    max_retries: int
    provider_request: ProviderRequestExtension | None
    stream_idle_timeout_seconds: float | None = None
    stream_idle_heartbeat_seconds: float | None = None

    def __post_init__(self) -> None:
        """校验 RunnerSpec 字段的语义一致性。

        - ``default_timeout_seconds`` 必须为正数（> 0）。
        - ``max_retries`` 必须为非负整数（>= 0）。
        - ``stream_idle_heartbeat_seconds`` 启用时 ``stream_idle_timeout_seconds``
          必须同时启用。
        - 两者都必须为正数（> 0）。
        - 心跳不得大于 timeout。
        - OpenAI-compatible 客户端关联策略启用时，静态 headers 不得包含
          ``X-Client-Request-Id``。

        :raises ValueError: 当字段语义不一致时抛出。
        """

        timeout = self.stream_idle_timeout_seconds
        heartbeat = self.stream_idle_heartbeat_seconds
        if not isinstance(
            self.structured_output_capability, StructuredOutputCapability
        ):
            raise TypeError(
                "structured_output_capability must be "
                "StructuredOutputCapability"
            )
        if self.default_timeout_seconds <= 0:
            raise ValueError(
                "default_timeout_seconds must be > 0; "
                f"got {self.default_timeout_seconds!r}"
            )
        if self.max_retries < 0:
            raise ValueError(
                "max_retries must be >= 0; "
                f"got {self.max_retries!r}"
            )
        if timeout is None and heartbeat is not None:
            raise ValueError(
                "stream_idle_heartbeat_seconds requires "
                "stream_idle_timeout_seconds to be set"
            )
        if timeout is not None and timeout <= 0:
            raise ValueError(
                "stream_idle_timeout_seconds must be > 0; "
                f"got {timeout!r}"
            )
        if heartbeat is not None and heartbeat <= 0:
            raise ValueError(
                "stream_idle_heartbeat_seconds must be > 0; "
                f"got {heartbeat!r}"
            )
        if (
            timeout is not None
            and heartbeat is not None
            and heartbeat > timeout
        ):
            raise ValueError(
                "stream_idle_heartbeat_seconds must be <= "
                "stream_idle_timeout_seconds; got "
                f"heartbeat={heartbeat!r}, timeout={timeout!r}"
            )
        if (
            self.client_correlation_policy
            is ClientCorrelationPolicy.OPENAI_X_CLIENT_REQUEST_ID
            and _has_openai_client_request_id_header(self.headers)
        ):
            raise ValueError(
                "RunnerSpec.headers must not include X-Client-Request-Id "
                "when client_correlation_policy is "
                "OPENAI_X_CLIENT_REQUEST_ID"
            )


def _has_openai_client_request_id_header(headers: Mapping[str, str]) -> bool:
    """判断静态 headers 是否包含 OpenAI-compatible client request id。

    :param headers: RunnerSpec 静态 header 映射。
    :returns: 存在大小写不敏感匹配的 header 时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    for name in headers:
        if name.lower() == _OPENAI_CLIENT_REQUEST_ID_HEADER_NAME_LOWER:
            return True
    return False


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
    "DeepSeekReasoningEffort",
    "GeminiThinkingLevel",
    "ClientCorrelationPolicy",
    "OpenAIReasoningExtension",
    "AnthropicThinkingExtension",
    "DeepSeekThinkingExtension",
    "MimoThinkingExtension",
    "GeminiThinkingExtension",
    "QwenThinkingExtension",
    "ProviderRequestExtension",
    "OPENAI_CLIENT_REQUEST_ID_HEADER_NAME",
    "RunnerSpec",
    "RunnerCallOptions",
]
