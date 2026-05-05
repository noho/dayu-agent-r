"""``RunnerSpec`` / ``OpenAIReasoningEffort`` 契约补丁测试。

覆盖 Phase 1 contract 补丁（``docs/engine/phase1-plan.md`` §0.1）：

- ``OpenAIReasoningEffort`` 包含 ``NONE = "none"`` 成员。
- ``RunnerSpec`` 字段集合包含 ``supports_stream_usage``。
- ``RunnerSpec`` 可在 ``supports_stream_usage`` 双值下完整构造。
- Phase 1.5 流空闲字段 ``stream_idle_timeout_seconds`` /
  ``stream_idle_heartbeat_seconds`` 的语义校验。
"""

from __future__ import annotations

import dataclasses

import pytest

from dayu.engine.contracts.runner_spec import (
    OpenAIReasoningEffort,
    OpenAIReasoningExtension,
    RunnerSpec,
)


def _base_spec_kwargs() -> dict[str, object]:
    """构造一份基础合法的 RunnerSpec 关键字参数。"""

    return {
        "provider": "openai",
        "model": "gpt-x",
        "endpoint": "https://example.com",
        "api_key_ref": "key",
        "headers": {},
        "supports_tool_calling": False,
        "supports_streaming": True,
        "supports_stream_usage": False,
        "default_timeout_seconds": 30.0,
        "max_retries": 0,
        "provider_request": None,
    }


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
    """``RunnerSpec`` 字段集合必须包含 ``supports_stream_usage`` 与 stream idle 字段。"""

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
        "stream_idle_timeout_seconds",
        "stream_idle_heartbeat_seconds",
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


def test_runner_spec_stream_idle_defaults_to_none() -> None:
    """两个 stream idle 字段默认 ``None``。"""

    spec = RunnerSpec(**_base_spec_kwargs())  # type: ignore[arg-type]
    assert spec.stream_idle_timeout_seconds is None
    assert spec.stream_idle_heartbeat_seconds is None


def test_runner_spec_stream_idle_timeout_only_is_legal() -> None:
    """仅设置 timeout、不设置 heartbeat 合法。"""

    spec = RunnerSpec(
        **_base_spec_kwargs(),  # type: ignore[arg-type]
        stream_idle_timeout_seconds=10.0,
    )
    assert spec.stream_idle_timeout_seconds == 10.0
    assert spec.stream_idle_heartbeat_seconds is None


def test_runner_spec_stream_idle_heartbeat_without_timeout_raises() -> None:
    """只设置 heartbeat、不设置 timeout 必须报错。"""

    with pytest.raises(ValueError, match="requires"):
        RunnerSpec(
            **_base_spec_kwargs(),  # type: ignore[arg-type]
            stream_idle_heartbeat_seconds=1.0,
        )


def test_runner_spec_stream_idle_timeout_must_be_positive() -> None:
    """``stream_idle_timeout_seconds`` 非正数必须报错。"""

    for value in (0.0, -1.0):
        with pytest.raises(ValueError, match="must be > 0"):
            RunnerSpec(
                **_base_spec_kwargs(),  # type: ignore[arg-type]
                stream_idle_timeout_seconds=value,
            )


def test_runner_spec_stream_idle_heartbeat_must_be_positive() -> None:
    """``stream_idle_heartbeat_seconds`` 非正数必须报错。"""

    for value in (0.0, -0.1):
        with pytest.raises(ValueError, match="must be > 0"):
            RunnerSpec(
                **_base_spec_kwargs(),  # type: ignore[arg-type]
                stream_idle_timeout_seconds=10.0,
                stream_idle_heartbeat_seconds=value,
            )


def test_runner_spec_stream_idle_heartbeat_must_not_exceed_timeout() -> None:
    """heartbeat > timeout 必须报错；heartbeat == timeout 合法。"""

    with pytest.raises(ValueError, match="<= "):
        RunnerSpec(
            **_base_spec_kwargs(),  # type: ignore[arg-type]
            stream_idle_timeout_seconds=10.0,
            stream_idle_heartbeat_seconds=11.0,
        )
    # heartbeat == timeout 合法（plan 允许）
    spec = RunnerSpec(
        **_base_spec_kwargs(),  # type: ignore[arg-type]
        stream_idle_timeout_seconds=10.0,
        stream_idle_heartbeat_seconds=10.0,
    )
    assert spec.stream_idle_heartbeat_seconds == 10.0


def test_runner_spec_stream_idle_full_construction_legal() -> None:
    """合法 (timeout, heartbeat) 组合可构造。"""

    spec = RunnerSpec(
        **_base_spec_kwargs(),  # type: ignore[arg-type]
        stream_idle_timeout_seconds=10.0,
        stream_idle_heartbeat_seconds=2.0,
    )
    assert spec.stream_idle_timeout_seconds == 10.0
    assert spec.stream_idle_heartbeat_seconds == 2.0
