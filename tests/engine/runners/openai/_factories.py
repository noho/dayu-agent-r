"""测试通用工厂：构造 :class:`RunnerSpec` / :class:`RunnerCallOptions`。

本模块抽取测试中常用的 spec / options 构造逻辑，避免在每个测试文件
重复样板代码。所有工厂函数均提供必需字段的默认值，调用方可通过
``replace=...`` 覆写需要的字段。
"""

from __future__ import annotations

import dataclasses
from typing import TypedDict, Unpack

from dayu.engine.contracts.runner_spec import (
    ClientCorrelationPolicy,
    ProviderRequestExtension,
    RunnerCallOptions,
    RunnerSpec,
)


class _RunnerSpecChanges(TypedDict, total=False):
    """``replace_spec`` 支持的 RunnerSpec 字段覆写集合。"""

    provider: str
    model: str
    endpoint: str
    api_key_ref: str | None
    headers: dict[str, str]
    client_correlation_policy: ClientCorrelationPolicy
    supports_tool_calling: bool
    supports_streaming: bool
    supports_stream_usage: bool
    default_timeout_seconds: float
    max_retries: int
    provider_request: ProviderRequestExtension | None
    stream_idle_timeout_seconds: float | None
    stream_idle_heartbeat_seconds: float | None


def make_spec(
    *,
    provider: str = "openai",
    model: str = "gpt-test",
    endpoint: str = "https://example.test/v1/chat/completions",
    api_key_ref: str = "TEST_KEY",
    headers: dict[str, str] | None = None,
    client_correlation_policy: ClientCorrelationPolicy = (
        ClientCorrelationPolicy.DISABLED
    ),
    supports_tool_calling: bool = True,
    supports_streaming: bool = True,
    supports_stream_usage: bool = False,
    default_timeout_seconds: float = 30.0,
    max_retries: int = 0,
    provider_request: ProviderRequestExtension | None = None,
    stream_idle_timeout_seconds: float | None = None,
    stream_idle_heartbeat_seconds: float | None = None,
) -> RunnerSpec:
    """构造一个常规 :class:`RunnerSpec`。"""

    headers_value: dict[str, str] = {} if headers is None else dict(headers)
    return RunnerSpec(
        provider=provider,
        model=model,
        endpoint=endpoint,
        api_key_ref=api_key_ref,
        headers=headers_value,
        client_correlation_policy=client_correlation_policy,
        supports_tool_calling=supports_tool_calling,
        supports_streaming=supports_streaming,
        supports_stream_usage=supports_stream_usage,
        default_timeout_seconds=default_timeout_seconds,
        max_retries=max_retries,
        provider_request=provider_request,
        stream_idle_timeout_seconds=stream_idle_timeout_seconds,
        stream_idle_heartbeat_seconds=stream_idle_heartbeat_seconds,
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


def replace_spec(spec: RunnerSpec, **changes: Unpack[_RunnerSpecChanges]) -> RunnerSpec:
    """``dataclasses.replace`` 的薄封装，便于逐字段覆写。

    :param spec: 原 spec。
    :param changes: 待覆写字段。
    :returns: 新 :class:`RunnerSpec`。
    """

    return dataclasses.replace(spec, **changes)  # type: ignore[arg-type]


__all__ = ["make_spec", "make_options", "replace_spec"]
