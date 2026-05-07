"""Host P4 token estimator 测试。"""

from __future__ import annotations

from dayu.host._token_estimator import (
    FULL_WIDTH_TOKEN_UNIT,
    HALF_WIDTH_TOKEN_UNIT,
    TOKEN_ESTIMATOR_ALGORITHM_ID,
    TOKEN_UNITS_PER_ESTIMATED_TOKEN,
    estimate_text_token_units,
    estimate_text_tokens,
)


def test_token_estimator_uses_old_conservative_denominator() -> None:
    """Host estimator 继承 OLD 2 units/token 的保守换算。"""

    assert TOKEN_ESTIMATOR_ALGORITHM_ID == "host_wide_narrow_units_v1"
    assert TOKEN_UNITS_PER_ESTIMATED_TOKEN == 2


def test_token_estimator_counts_chinese_financial_text_like_old_key_sample() -> None:
    """纯中文财报文本按宽字符约 1 token/字估算。"""

    text = "营收增长"

    assert estimate_text_token_units(text) == 4 * FULL_WIDTH_TOKEN_UNIT
    assert estimate_text_tokens(text) == 4


def test_token_estimator_counts_ascii_financial_text_like_old_key_sample() -> None:
    """纯 ASCII 财报文本按约 0.5 token/字符估算。"""

    text = "FY2024 revenue"

    assert estimate_text_token_units(text) == len(text) * HALF_WIDTH_TOKEN_UNIT
    assert estimate_text_tokens(text) == 7


def test_token_estimator_counts_mixed_financial_text_like_old_key_sample() -> None:
    """中英文混合财报文本按半角 1 unit、宽字符 2 unit 估算。"""

    text = "FY2024 营收增长 12%"
    expected_units = 11 * HALF_WIDTH_TOKEN_UNIT + 4 * FULL_WIDTH_TOKEN_UNIT

    assert estimate_text_token_units(text) == expected_units
    assert estimate_text_tokens(text) == 10
