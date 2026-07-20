"""层中立运行时数值边界校验。

本模块集中定义 runtime/config 公共边界对有限数值的判断语义，避免各消费层
分别用大小比较而让 ``NaN``、正负无穷或无法转换为 float 的超大整数穿透。
它不抛业务层异常；owner boundary 根据自身公共契约翻译错误类型与文本。
"""

from __future__ import annotations

import math


def is_finite_number(value: int | float) -> bool:
    """判断值是否为非 bool 的有限 JSON 数值。

    :param value: 待判断的整数或浮点数。
    :returns: 值不是 bool、可表示为有限浮点数且非 NaN/无穷时返回 ``True``。
    :raises Exception: 不主动抛出异常；超大整数转换溢出时返回 ``False``。
    """

    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def is_positive_finite_number(value: int | float) -> bool:
    """判断值是否为严格正的有限数值。

    :param value: 待判断的整数或浮点数。
    :returns: 值有限且严格大于零时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return is_finite_number(value) and value > 0


def is_non_negative_finite_number(value: int | float) -> bool:
    """判断值是否为非负有限数值。

    :param value: 待判断的整数或浮点数。
    :returns: 值有限且大于或等于零时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return is_finite_number(value) and value >= 0


__all__: tuple[str, ...] = (
    "is_finite_number",
    "is_non_negative_finite_number",
    "is_positive_finite_number",
)
