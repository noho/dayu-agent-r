"""``dayu.runtime.diagnostic_text`` 层中立诊断文本测试。"""

from __future__ import annotations

import pytest

from dayu.runtime.diagnostic_text import (
    contains_sensitive_diagnostic_value,
    redact_sensitive_diagnostic_values,
    truncate_diagnostic_text,
)

_REDACTION_MARKER = "<redacted>"
_TRUNCATED_SUFFIX = "...[truncated]"


@pytest.mark.parametrize(
    "message",
    [
        "provider returned Bearer sk-live-secret",
        "provider returned bearer sk-live-secret",
        "provider returned api key sk-live-secret",
        "provider returned API key sk-live-secret",
        "provider returned api_key=sk-live-secret",
        "provider returned api-key:sk-live-secret",
        "provider returned api-key: sk-live-secret",
        "provider returned apikey=sk-live-secret",
        "provider returned authorization=sk-live-secret",
        "provider returned authorization: sk-live-secret",
        "provider returned password=sk-live-secret",
        "provider returned secret=sk-live-secret",
        "provider returned token=sk-live-secret",
        "provider returned token: sk-live-secret",
    ],
)
def test_contains_sensitive_diagnostic_value_detects_value_patterns(
    message: str,
) -> None:
    """敏感字段携带值时必须被识别。

    :param message: 待检测的敏感诊断文本。
    :returns: ``None``。
    """

    assert contains_sensitive_diagnostic_value(message)


@pytest.mark.parametrize(
    "message",
    [
        "",
        "JWT token has expired",
        "Content-Type header is invalid",
        "authorization header is missing",
        "token refresh failed before assignment",
    ],
)
def test_contains_sensitive_diagnostic_value_ignores_plain_diagnostics(
    message: str,
) -> None:
    """普通诊断文本不应被误判为携带敏感值。

    :param message: 待检测的普通诊断文本。
    :returns: ``None``。
    """

    assert not contains_sensitive_diagnostic_value(message)


def test_redact_sensitive_diagnostic_values_preserves_context_and_prefix() -> None:
    """局部脱敏只替换 value，保留字段名前缀和非敏感上下文。

    :returns: ``None``。
    """

    message = (
        "retry failed; api-key: sk-live-secret; "
        "authorization=auth-secret; password: pass-secret; "
        "secret=secret-value; token=token-value"
    )

    redacted = redact_sensitive_diagnostic_values(
        message,
        redaction_marker=_REDACTION_MARKER,
    )

    assert "retry failed" in redacted
    assert "api-key: <redacted>" in redacted
    assert "authorization=<redacted>" in redacted
    assert "password: <redacted>" in redacted
    assert "secret=<redacted>" in redacted
    assert "token=<redacted>" in redacted
    assert "sk-live-secret" not in redacted
    assert "auth-secret" not in redacted
    assert "pass-secret" not in redacted
    assert "secret-value" not in redacted
    assert "token-value" not in redacted


def test_redact_sensitive_diagnostic_values_normalizes_bearer_prefix() -> None:
    """Bearer 片段脱敏时统一保留标准 ``Bearer`` 前缀。

    :returns: ``None``。
    """

    redacted = redact_sensitive_diagnostic_values(
        "provider returned bearer sk-live-secret",
        redaction_marker=_REDACTION_MARKER,
    )

    assert redacted == "provider returned Bearer <redacted>"


def test_redaction_marker_is_used_as_literal_replacement_text() -> None:
    """marker 内的反斜杠和 group reference 文本必须按字面值进入结果。

    :returns: ``None``。
    """

    marker = r"literal-\1-\g<value>-\\"

    redacted = redact_sensitive_diagnostic_values(
        "api_key=sk-live-secret Bearer bearer-secret",
        redaction_marker=marker,
    )

    assert redacted == (
        r"api_key=literal-\1-\g<value>-\\ "
        r"Bearer literal-\1-\g<value>-\\"
    )
    assert "sk-live-secret" not in redacted
    assert "bearer-secret" not in redacted


def test_redact_sensitive_diagnostic_values_is_idempotent_for_same_marker() -> None:
    """无空白 marker 的局部脱敏重复执行不会继续改变结果。

    :returns: ``None``。
    """

    once = redact_sensitive_diagnostic_values(
        "error api_key=sk-live-secret token=token-secret",
        redaction_marker=_REDACTION_MARKER,
    )

    twice = redact_sensitive_diagnostic_values(
        once,
        redaction_marker=_REDACTION_MARKER,
    )

    assert twice == once


def test_empty_string_paths_are_noops() -> None:
    """空字符串在检测、脱敏和合法截断参数下均保持空文本语义。

    :returns: ``None``。
    """

    assert not contains_sensitive_diagnostic_value("")
    assert (
        redact_sensitive_diagnostic_values(
            "",
            redaction_marker=_REDACTION_MARKER,
        )
        == ""
    )
    assert (
        truncate_diagnostic_text(
            "",
            max_chars=20,
            truncated_suffix=_TRUNCATED_SUFFIX,
        )
        == ""
    )


def test_truncate_diagnostic_text_short_message_returns_original() -> None:
    """短于上限的文本必须原样返回。

    :returns: ``None``。
    """

    message = "short"

    truncated = truncate_diagnostic_text(
        message,
        max_chars=20,
        truncated_suffix=_TRUNCATED_SUFFIX,
    )

    assert truncated == message
    assert truncated is message


def test_truncate_diagnostic_text_exact_boundary_returns_original() -> None:
    """长度等于上限的文本必须原样返回。

    :returns: ``None``。
    """

    message = "1234567890"

    truncated = truncate_diagnostic_text(
        message,
        max_chars=10,
        truncated_suffix="...",
    )

    assert truncated == message
    assert truncated is message


def test_truncate_diagnostic_text_over_limit_uses_suffix_and_exact_length() -> None:
    """超限文本必须截断到精确上限并追加显式 suffix。

    :returns: ``None``。
    """

    truncated = truncate_diagnostic_text(
        "abcdefghijklmnopqrstuvwxyz",
        max_chars=18,
        truncated_suffix=_TRUNCATED_SUFFIX,
    )

    assert truncated == "abcd" + _TRUNCATED_SUFFIX
    assert len(truncated) == 18


def test_redact_then_truncate_does_not_leak_secret_value() -> None:
    """先脱敏再截断的组合路径不得泄漏敏感原值。

    :returns: ``None``。
    """

    secret = "sk-live-secret-value"
    message = (
        "compactor failed with api_key="
        + secret
        + " and ordinary diagnostic context that is long"
    )

    redacted = redact_sensitive_diagnostic_values(
        message,
        redaction_marker=_REDACTION_MARKER,
    )
    truncated = truncate_diagnostic_text(
        redacted,
        max_chars=48,
        truncated_suffix=_TRUNCATED_SUFFIX,
    )

    assert secret not in truncated
    assert len(truncated) == 48
    assert truncated.endswith(_TRUNCATED_SUFFIX)


@pytest.mark.parametrize("max_chars", [0, -1])
def test_truncate_diagnostic_text_rejects_non_positive_max_chars(
    max_chars: int,
) -> None:
    """非正 ``max_chars`` 必须 fail fast。

    :param max_chars: 非法最大字符数。
    :returns: ``None``。
    """

    with pytest.raises(ValueError, match="max_chars"):
        truncate_diagnostic_text(
            "message",
            max_chars=max_chars,
            truncated_suffix="...",
        )


@pytest.mark.parametrize(
    ("max_chars", "suffix"),
    [
        (3, "..."),
        (2, "..."),
    ],
)
def test_truncate_diagnostic_text_rejects_suffix_that_hides_body(
    max_chars: int,
    suffix: str,
) -> None:
    """后缀长度大于等于上限时必须 fail fast。

    :param max_chars: 最大字符数。
    :param suffix: 非法截断后缀。
    :returns: ``None``。
    """

    with pytest.raises(ValueError, match="truncated_suffix length"):
        truncate_diagnostic_text(
            "message",
            max_chars=max_chars,
            truncated_suffix=suffix,
        )
