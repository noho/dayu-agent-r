"""财报领域枚举定义。"""

from __future__ import annotations

from enum import Enum


class Market(str, Enum):
    """市场枚举。"""

    US = "US"
    HK = "HK"
    CN = "CN"


class SourceKind(str, Enum):
    """文档来源枚举。"""

    FILING = "filing"
    MATERIAL = "material"
