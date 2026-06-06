"""SEC 表单类型标准化工具。

本模块提供 SEC 表单类型的统一标准化函数，是所有处理器共享的叶模块：
- 无处理器依赖（不导入任何 processor），避免循环导入；
- 涵盖所有已支持的 SEC 表单类型（10-K/10-Q/20-F/8-K/6-K/DEF 14A/SC 13D/SC 13G 及修正案）。

使用方式::

    from .form_type_utils import normalize_form_type
"""

from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# SEC 表单类型标准化映射
# ---------------------------------------------------------------------------
# 去除空白后的大写字符串 → 标准格式。
# 涵盖报告类表单（10-K/10-Q/20-F）和特殊表单（8-K/6-K/DEF 14A/SC 13D/SC 13G）。
_FORM_TYPE_MAPPING: dict[str, str] = {
    # 报告类表单
    "10K": "10-K",
    "10Q": "10-Q",
    "20F": "20-F",
    # 特殊表单
    "6K": "6-K",
    "8K": "8-K",
    "8KA": "8-K/A",
    "8K/A": "8-K/A",
    "DEF14A": "DEF 14A",
    # SC 13D 系列
    "SC13D": "SC 13D",
    "SC13DA": "SC 13D/A",
    "SC13D/A": "SC 13D/A",
    "SCHEDULE13D": "SC 13D",
    "SCHEDULE13DA": "SC 13D/A",
    "SCHEDULE13D/A": "SC 13D/A",
    # SC 13G 系列
    "SC13G": "SC 13G",
    "SC13GA": "SC 13G/A",
    "SC13G/A": "SC 13G/A",
    "SCHEDULE13G": "SC 13G",
    "SCHEDULE13GA": "SC 13G/A",
    "SCHEDULE13G/A": "SC 13G/A",
}


def normalize_form_type(form_type: Optional[str]) -> Optional[str]:
    """标准化 SEC 表单类型。

    接受任意格式的表单类型字符串，返回统一的标准格式。
    涵盖所有已支持的 SEC 表单类型（报告类 + 特殊表单）。

    标准化规则：
    1. ``None`` / 纯空白 → 返回 ``None``
    2. 去除所有空白后查表映射
    3. 未匹配到映射 → 返回去前后空白并大写的原始值

    Args:
        form_type: 原始表单类型字符串。

    Returns:
        标准化后的表单类型；输入为空时返回 ``None``。

    Examples:
        >>> normalize_form_type("10K")
        '10-K'
        >>> normalize_form_type(" def 14a ")
        'DEF 14A'
        >>> normalize_form_type(None) is None
        True
    """
    if form_type is None:
        return None
    stripped = str(form_type).strip()
    if not stripped:
        return None
    # 去除所有内部空白后大写，用于映射查找
    compact = re.sub(r"\s+", "", stripped.upper())
    return _FORM_TYPE_MAPPING.get(compact, stripped.upper())
