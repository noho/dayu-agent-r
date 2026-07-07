"""财报业务 resolver 公共契约。

本子包承载财报分析所需的公司、证券或业务标识解析能力。包根
``dayu.fins`` 不重新导出这些业务符号，调用方应显式依赖本子包。
"""

from __future__ import annotations

from dayu.fins.resolver.fmp_company_info import (
    FmpCompanyInfo,
    FmpCompanyInfoResolutionError,
    FmpCompanyInfoResolver,
    FmpHttpClientProtocol,
)

__all__: tuple[str, ...] = (
    "FmpCompanyInfo",
    "FmpCompanyInfoResolutionError",
    "FmpCompanyInfoResolver",
    "FmpHttpClientProtocol",
)
