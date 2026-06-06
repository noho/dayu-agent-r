"""处理器层通用表格工具。

本模块提供所有处理器共享的低层级 HTML 表格解析函数，
避免业务域或具体处理器直接依赖某个 processor 模块的私有实现。
"""

from __future__ import annotations

from io import StringIO
from typing import Optional

import pandas as pd
from bs4 import Tag


def parse_html_table_dataframe(table_tag: Tag) -> Optional[pd.DataFrame]:
    """使用 pandas 解析 HTML 表格为 DataFrame。

    显式禁用 ``thousands`` 参数以避免 pandas 内部对含大量逗号的长字符串
    执行病态正则替换（``_search_replace_num_columns``），该场景会导致进程
    卡死数小时。下游数值解析由各自处理器独立处理，不依赖 pandas 预清理
    千位分隔符。

    Args:
        table_tag: 待解析的 HTML ``table`` 标签。

    Returns:
        解析得到的 ``DataFrame``；解析失败或无表格时返回 ``None``。

    Raises:
        RuntimeError: 解析过程中出现不可恢复错误时抛出。
    """

    try:
        dataframes = pd.read_html(StringIO(str(table_tag)), thousands=None)
    except Exception:
        return None
    if not dataframes:
        return None
    return dataframes[0]


__all__ = ["parse_html_table_dataframe"]