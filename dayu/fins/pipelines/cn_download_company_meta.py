"""CN/HK 下载链路的公司级元数据写入。

本模块只负责把 downloader 解析出的 :class:`CnCompanyProfile` 转换为
``CompanyMeta`` 并通过 ``CompanyMetaRepositoryProtocol`` 写入。它不依赖
downloader 具体实现、不写 source 文档、不参与 docling 转换。
"""

from __future__ import annotations

from dayu.fins.domain.document_models import BatchToken, CompanyMeta, now_iso8601
from dayu.fins.pipelines.cn_download_models import CnCompanyProfile
from dayu.fins.storage import CompanyMetaRepositoryProtocol
from dayu.fins.ticker_normalization import (
    build_company_ticker_identity,
    normalize_ticker,
    ticker_to_company_id,
)

_RESOLVER_VERSION = "cn_download_v1"


def upsert_company_meta_for_cn_download(
    *,
    repository: CompanyMetaRepositoryProtocol,
    profile: CnCompanyProfile,
    normalized_ticker: str,
    ticker_aliases: list[str] | None,
    batch: BatchToken,
) -> CompanyMeta:
    """写入 CN/HK 下载链路的公司级元数据。

    Args:
        repository: 公司级元数据仓储。
        profile: downloader 解析得到的公司基础信息。
        normalized_ticker: 已归一化 ticker。
        ticker_aliases: CLI / Service 透传的 ticker alias 列表。
        batch: caller 显式传入的 batch capability。

    Returns:
        已写入的 ``CompanyMeta``。

    Raises:
        ValueError: ``normalized_ticker``、``profile.company_id`` 或
            ``profile.company_name`` 为空时抛出。
        OSError: 仓储写入失败时抛出。
    """

    ticker = normalized_ticker.strip()
    if not ticker:
        raise ValueError("normalized_ticker 不能为空")
    ticker_identity = build_company_ticker_identity(ticker, ticker_aliases or ())
    company_id = ticker_to_company_id(normalize_ticker(ticker_identity.canonical_ticker))
    company_name = profile.company_name.strip()
    if not company_name:
        raise ValueError("profile.company_name 不能为空")

    meta = CompanyMeta(
        company_id=company_id,
        company_name=company_name,
        ticker_identity=ticker_identity,
        resolver_version=_RESOLVER_VERSION,
        updated_at=now_iso8601(),
    )
    repository.upsert_company_meta(meta, batch=batch)
    return meta

__all__ = ["upsert_company_meta_for_cn_download"]
