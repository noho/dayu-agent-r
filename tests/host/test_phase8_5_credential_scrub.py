"""P8.5 显式凭证清洗单元测试。"""

from __future__ import annotations

from dayu.contracts import JsonValue
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolFailedOutcome
from dayu.contracts.tool_result import ToolResultFailure, ToolResultSuccess
from dayu.host._credential_scrub import (
    scrub_explicit_credentials,
    scrub_tool_arguments,
    scrub_tool_execution_outcome,
)


def test_scrub_explicit_credentials_recurses_nested_payload() -> None:
    """嵌套 JSON 中只清洗显式凭证字段。"""

    payload: JsonValue = {
        "api_key": "sk-api",
        "API key": "sk-api-space",
        "headers": {
            "Authorization": "Bearer sk-auth",
            "x-api-key": "sk-x",
            "Cookie": "sid=secret",
        },
        "items": [
            {"client_secret": "client-secret"},
            {"private_key": "private-key"},
            {"password": "password"},
        ],
    }
    scrubbed = scrub_explicit_credentials(payload)
    assert isinstance(scrubbed, dict)
    assert scrubbed["api_key"] == "***"
    assert scrubbed["API key"] == "***"
    headers = scrubbed["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "***"
    assert headers["x-api-key"] == "***"
    assert headers["Cookie"] == "***"
    items = scrubbed["items"]
    assert isinstance(items, list)
    assert items == [
        {"client_secret": "***"},
        {"private_key": "***"},
        {"password": "***"},
    ]


def test_scrub_explicit_credentials_keeps_runtime_capabilities_and_plain_fields() -> None:
    """cursor、scope_token、普通 token 与非凭证 provider 字段不被误清洗。"""

    payload: JsonValue = {
        "cursor": "cursor-raw",
        "scope_token": "scope-raw",
        "token": "business-token",
        "anthropic-version": "2023-06-01",
        "openai-organization": "org-public-id",
    }
    scrubbed = scrub_explicit_credentials(payload)
    assert scrubbed == payload


def test_scrub_explicit_credentials_scrubs_header_text() -> None:
    """字符串中的 Authorization / x-api-key / cookie header 会被清洗。"""

    text: JsonValue = (
        "Authorization: Bearer sk-live\n"
        "x-api-key = sk-x\n"
        "API key: sk-api-space\n"
        "cookie: sid=secret; theme=dark\n"
        "cursor: cursor-raw\n"
        "token: ordinary-token"
    )
    scrubbed = scrub_explicit_credentials(text)
    assert isinstance(scrubbed, str)
    assert "Authorization: ***" in scrubbed
    assert "x-api-key = ***" in scrubbed
    assert "API key: ***" in scrubbed
    assert "cookie: ***" in scrubbed
    assert "cursor: cursor-raw" in scrubbed
    assert "token: ordinary-token" in scrubbed
    assert "sk-live" not in scrubbed
    assert "sk-x" not in scrubbed
    assert "sk-api-space" not in scrubbed
    assert "sid=secret" not in scrubbed


def test_scrub_tool_arguments_returns_mapping_with_same_policy() -> None:
    """工具参数清洗保持映射结构并沿用窄凭证策略。"""

    scrubbed = scrub_tool_arguments(
        {
            "anthropic-api-key": "sk-anthropic",
            "cursor": "cursor-raw",
        }
    )
    assert scrubbed["anthropic-api-key"] == "***"
    assert scrubbed["cursor"] == "cursor-raw"


def test_scrub_tool_execution_outcome_scrubs_success_and_failure_text() -> None:
    """工具 outcome 的成功值与失败文本都清洗显式凭证。"""

    success = scrub_tool_execution_outcome(
        ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value={"password": "pw", "scope_token": "scope"},
                truncation=None,
                meta=None,
            )
        )
    )
    assert isinstance(success, ToolCompletedOutcome)
    assert success.result.value == {"password": "***", "scope_token": "scope"}

    failure = scrub_tool_execution_outcome(
        ToolFailedOutcome(
            result=ToolResultFailure(
                ok=False,
                error="Authorization: Bearer sk-error",
                message="x-api-key: sk-message",
                hint="client_secret=sk-hint",
                meta=None,
            )
        )
    )
    assert isinstance(failure, ToolFailedOutcome)
    assert failure.result.error == "Authorization: ***"
    assert failure.result.message == "x-api-key: ***"
    assert failure.result.hint == "client_secret=***"
