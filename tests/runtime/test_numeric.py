"""``dayu.runtime.numeric`` 有限数值判断测试。"""

from __future__ import annotations

import pytest

from dayu.runtime.numeric import (
    is_finite_number,
    is_non_negative_finite_number,
    is_positive_finite_number,
)


@pytest.mark.parametrize("value", (0, 1, -1, 0.0, 1.5, -2.5))
def test_is_finite_number_accepts_finite_values(value: int | float) -> None:
    """有限整数与浮点数应被公共 helper 接受。

    :param value: 有限测试数值。
    :returns: ``None``。
    :raises AssertionError: 有限值被错误拒绝时抛出。
    """

    assert is_finite_number(value)


@pytest.mark.parametrize(
    "value",
    (True, False, float("nan"), float("inf"), float("-inf"), 10**1_000),
)
def test_is_finite_number_rejects_non_finite_or_non_json_number(
    value: int | float,
) -> None:
    """bool、非有限浮点数与无法安全转 float 的整数应被拒绝。

    :param value: 非法边界值。
    :returns: ``None``。
    :raises AssertionError: 非法值穿透公共 helper 时抛出。
    """

    assert not is_finite_number(value)


@pytest.mark.parametrize(
    ("value", "is_positive", "is_non_negative"),
    ((-1.0, False, False), (0.0, False, True), (1.0, True, True)),
)
def test_signed_finite_number_helpers_share_boundary(
    value: float,
    is_positive: bool,
    is_non_negative: bool,
) -> None:
    """正数与非负数 helper 应共享 finite-number 判断。

    :param value: 有限测试数值。
    :param is_positive: 预期严格正数判断。
    :param is_non_negative: 预期非负判断。
    :returns: ``None``。
    :raises AssertionError: 符号判断不符合公共契约时抛出。
    """

    assert is_positive_finite_number(value) is is_positive
    assert is_non_negative_finite_number(value) is is_non_negative
