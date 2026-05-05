"""``RunnerSpec`` / ``OpenAIReasoningEffort`` 契约补丁测试。

覆盖 Phase 1 contract 补丁（``docs/engine/phase1-plan.md`` §0.1）：

- ``OpenAIReasoningEffort`` 包含 ``NONE = "none"`` 成员。
- ``RunnerSpec`` 字段集合包含 ``supports_stream_usage``。
- ``RunnerSpec`` 可在 ``supports_stream_usage`` 双值下完整构造。
"""

from __future__ import annotations

import dataclasses

from dayu.engine.contracts.runner_spec import (
    OpenAIReasoningEffort,
    OpenAIReasoningExtension,
    RunnerSpec,
)


def test_openai_reasoning_effort_includes_none() -> None:
    """``OpenAIReasoningEffort`` 必须含 ``NONE`` 成员且值为 ``"none"``。"""

    assert OpenAIReasoningEffort.NONE.value == "none"
    assert {m.value for m in OpenAIReasoningEffort} == {
        "low",
        "medium",
        "high",
        "none",
    }


def test_runner_spec_field_set_includes_supports_stream_usage() -> None:
    """``RunnerSpec`` 字段集合必须包含 ``supports_stream_usage``。"""

    fields = {f.name for f in dataclasses.fields(RunnerSpec)}
    assert fields == {
        "provider",
        "model",
        "endpoint",
        "api_key_ref",
        "headers",
        "supports_tool_calling",
        "supports_streaming",
        "supports_stream_usage",
        "default_timeout_seconds",
        "max_retries",
        "provider_request",
    }


def test_runner_spec_supports_stream_usage_true_construction() -> None:
    """``supports_stream_usage=True`` 时 ``RunnerSpec`` 完整构造合法。"""

    spec = RunnerSpec(
        provider="openai",
        model="gpt-x",
        endpoint="https://example.com",
        api_key_ref="key",
        headers={},
        supports_tool_calling=True,
        supports_streaming=True,
        supports_stream_usage=True,
        default_timeout_seconds=30.0,
        max_retries=2,
        provider_request=OpenAIReasoningExtension(
            reasoning_effort=OpenAIReasoningEffort.NONE
        ),
    )
    assert spec.supports_stream_usage is True
    assert spec.provider_request is not None


def test_runner_spec_supports_stream_usage_false_construction() -> None:
    """``supports_stream_usage=False`` 时 ``RunnerSpec`` 完整构造合法。"""

    spec = RunnerSpec(
        provider="openai",
        model="gpt-x",
        endpoint="https://example.com",
        api_key_ref="key",
        headers={},
        supports_tool_calling=False,
        supports_streaming=False,
        supports_stream_usage=False,
        default_timeout_seconds=30.0,
        max_retries=0,
        provider_request=None,
    )
    assert spec.supports_stream_usage is False
