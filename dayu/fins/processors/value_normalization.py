"""Fins processor dataframe 标量归一化真源。

本模块只处理 dataframe/第三方表格边界中的可选字符串语义，统一区分
缺失标量与可转换为文本的有效值，避免各 processor 自行解释 pandas 空值。
"""

from __future__ import annotations

import math
from typing import Protocol

import pandas as pd


class StringConvertible(Protocol):
    """可稳定转换为字符串的标量协议。"""

    def __str__(self) -> str:
        """返回标量的字符串表示。

        Args:
            无。

        Returns:
            字符串表示。

        Raises:
            RuntimeError: 具体标量实现转换失败时可能抛出。
        """

        ...


def normalize_optional_dataframe_string(value: StringConvertible | None) -> str | None:
    """把 dataframe 标量归一化为可选字符串。

    ``None``、pandas ``NA``/``NaT``、浮点 NaN 与空白文本表示缺失；数字 0、
    bool ``False`` 和其它普通标量仍是有效值，转换后只移除首尾空白。

    Args:
        value: dataframe 或第三方表格 API 返回的可转字符串标量。

    Returns:
        去除首尾空白后的文本；缺失标量或空白文本返回 ``None``。

    Raises:
        RuntimeError: 标量自身的字符串转换失败时可能抛出。
    """

    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    normalized = str(value).strip()
    return normalized or None
