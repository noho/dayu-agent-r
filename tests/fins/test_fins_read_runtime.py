"""Fins read runtime focused tests。"""

from __future__ import annotations

from dayu.fins.tools.read_runtime_helpers import _normalize_form_type_for_matching


def test_read_runtime_form_matching_consumes_domain_sec_aliases() -> None:
    """验证 read runtime form 匹配消费 domain SEC form 归一结果。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    assert _normalize_form_type_for_matching("10K") == "10-K"
    assert _normalize_form_type_for_matching("SCHEDULE 13D/A") == "SC 13D/A"
    assert _normalize_form_type_for_matching("def 14a") == "DEF 14A"
