"""P8.5 ordinary tool result truncation helper 单元测试。"""

from __future__ import annotations

import pytest

from dayu.contracts import JsonValue
from dayu.host._tool_result_truncation import (
    ToolResultTruncationHint,
    extract_truncation_hint,
    inject_truncation_hint,
)


def _hint() -> ToolResultTruncationHint:
    """构造测试用截断 hint。

    :returns: 截断 hint。
    :raises Exception: 不主动抛出异常。
    """

    return ToolResultTruncationHint(
        cursor="cursor-1",
        scope_token="scope-1",
        has_more=True,
        limit=10,
        ttl_seconds=30,
    )


def test_inject_truncation_hint_preserves_business_truncation_field() -> None:
    """业务 payload 已有 truncation 字段时包装 content，不能覆盖原字段。"""

    original: JsonValue = {
        "content": "business",
        "truncation": {"business": "keep"},
    }

    injected = inject_truncation_hint(value=original, hint=_hint())

    assert isinstance(injected, dict)
    assert injected["content"] == original
    host_hint = injected["truncation"]
    assert isinstance(host_hint, dict)
    assert host_hint["fetch_more_args"] == {
        "cursor": "cursor-1",
        "limit": 10,
        "scope_token": "scope-1",
    }


@pytest.mark.parametrize(
    "value",
    [
        "plain",
        {"truncation": "not-object"},
        {"truncation": {"has_more": "yes"}},
        {"truncation": {"has_more": True}},
        {
            "truncation": {
                "has_more": True,
                "fetch_more_args": {"cursor": "cursor-1"},
            }
        },
        {
            "truncation": {
                "has_more": True,
                "fetch_more_args": {"scope_token": "scope-1"},
            }
        },
        {
            "truncation": {
                "has_more": True,
                "fetch_more_args": {
                    "cursor": 123,
                    "scope_token": "scope-1",
                },
            }
        },
        {
            "truncation": {
                "has_more": True,
                "fetch_more_args": {
                    "cursor": "cursor-1",
                    "scope_token": False,
                },
            }
        },
    ],
)
def test_extract_truncation_hint_returns_none_for_malformed_payload(
    value: JsonValue,
) -> None:
    """malformed 截断 payload 命中 guard 分支时返回 ``None``。"""

    assert extract_truncation_hint(value) is None
