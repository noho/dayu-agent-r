"""测试通用工厂：构造 :class:`RunnerSpec` / :class:`RunnerCallOptions`。

本模块抽取测试中常用的 spec / options 构造逻辑，避免在每个测试文件
重复样板代码。所有工厂函数均提供必需字段的默认值，调用方可通过
``replace=...`` 覆写需要的字段。
"""

from __future__ import annotations

import dataclasses

from dayu.engine.contracts.runner_spec import (
    ProviderRequestExtension,
    RunnerCallOptions,
    RunnerSpec,
)


def make_spec(
    *,
    provider: str = "openai",
    model: str = "gpt-test",
    endpoint: str = "https://example.test/v1/chat/completions",
    api_key_ref: str = "TEST_KEY",
    headers: dict[str, str] | None = None,
    supports_tool_calling: bool = True,
    supports_streaming: bool = True,
    supports_stream_usage: bool = False,
    default_timeout_seconds: float = 30.0,
    max_retries: int = 0,
    provider_request: ProviderRequestExtension | None = None,
) -> RunnerSpec:
    """构造一个常规 :class:`RunnerSpec`。

    :param provider: provider 名称。
    :param model: 模型名。
    :param endpoint: 端点 URL。
    :param api_key_ref: API key 引用。
    :param headers: 请求头映射。
    :param supports_tool_calling: 是否支持工具调用。
    :param supports_streaming: 是否支持流式。
    :param supports_stream_usage: 是否支持 ``stream_options.include_usage``。
    :param default_timeout_seconds: 默认超时秒数。
    :param max_retries: 最大重试次数。
    :param provider_request: provider 请求扩展。
    :returns: :class:`RunnerSpec` 实例。
    """

    headers_value: dict[str, str] = {} if headers is None else dict(headers)
    return RunnerSpec(
        provider=provider,
        model=model,
        endpoint=endpoint,
        api_key_ref=api_key_ref,
        headers=headers_value,
        supports_tool_calling=supports_tool_calling,
        supports_streaming=supports_streaming,
        supports_stream_usage=supports_stream_usage,
        default_timeout_seconds=default_timeout_seconds,
        max_retries=max_retries,
        provider_request=provider_request,
    )


def make_options(
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    top_p: float | None = None,
    stream: bool = True,
) -> RunnerCallOptions:
    """构造 :class:`RunnerCallOptions`。

    :param temperature: 温度。
    :param max_tokens: 最大输出 tokens。
    :param top_p: top-p。
    :param stream: 是否流式。
    :returns: :class:`RunnerCallOptions` 实例。
    """

    return RunnerCallOptions(
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        stream=stream,
    )


def replace_spec(spec: RunnerSpec, **changes: object) -> RunnerSpec:
    """``dataclasses.replace`` 的薄封装，便于逐字段覆写。

    :param spec: 原 spec。
    :param changes: 待覆写字段。
    :returns: 新 :class:`RunnerSpec`。
    """

    return dataclasses.replace(spec, **changes)  # type: ignore[arg-type]


__all__ = ["make_spec", "make_options", "replace_spec"]
