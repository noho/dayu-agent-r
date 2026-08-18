"""CN/HK 下载链路的公司级元数据写入。

本模块只负责把 downloader 解析出的 :class:`CnCompanyProfile` 转换为
``CompanyMeta`` 并通过 ``CompanyMetaRepositoryProtocol`` 写入。它不依赖
downloader 具体实现、不写 source 文档、不参与 docling 转换。
"""

from __future__ import annotations

from dayu.fins.domain.company_meta_contract import (
    CompanyMetaCommitIntent,
    build_company_meta_commit_intent,
)
from dayu.fins.domain.document_models import BatchToken, CompanyMeta
from dayu.fins.pipelines.cn_download_models import CnCompanyProfile
from dayu.fins.storage import CompanyMetaRepositoryProtocol
from dayu.fins.ticker_normalization import (
    build_company_ticker_identity,
    normalize_ticker,
    ticker_to_company_id,
)

_RESOLVER_VERSION = "cn_download_v1"


def stage_company_meta_for_cn_download(
    *,
    repository: CompanyMetaRepositoryProtocol,
    profile: CnCompanyProfile,
    normalized_ticker: str,
    ticker_aliases: list[str] | None,
    batch: BatchToken,
) -> CompanyMetaCommitIntent | None:
    """为 CN/HK 下载链路 stage 公司元数据提交意图。

    Args:
        repository: 公司级元数据仓储。
        profile: downloader 解析得到的公司基础信息。
        normalized_ticker: 已归一化 ticker。
        ticker_aliases: CLI / Service 透传的 ticker alias 列表。
        batch: caller 显式传入的 batch capability。

    Returns:
        已 stage 的提交意图；fresh 且 identity 未变化时返回 ``None``。

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

    existing_meta = _load_existing_company_meta(
        repository,
        ticker_identity.canonical_ticker,
    )
    if existing_meta is not None and existing_meta.resolver_version == _RESOLVER_VERSION:
        merged_identity = build_company_ticker_identity(
            ticker_identity.canonical_ticker,
            (*existing_meta.ticker_identity.accepted_aliases, *ticker_identity.accepted_aliases),
        )
        if merged_identity == existing_meta.ticker_identity:
            return None
        intent = build_company_meta_commit_intent(
            proposed_identity=ticker_identity,
            merge_mode="preserve_published",
            observed_meta=existing_meta,
            proposed_company_id=None,
            proposed_company_name=None,
            resolver_version=_RESOLVER_VERSION,
        )
    else:
        intent = build_company_meta_commit_intent(
            proposed_identity=ticker_identity,
            merge_mode="refresh_if_stale",
            observed_meta=existing_meta,
            proposed_company_id=company_id,
            proposed_company_name=company_name,
            resolver_version=_RESOLVER_VERSION,
        )
    repository.stage_company_meta_intent(intent, batch=batch)
    return intent


def _load_existing_company_meta(
    repository: CompanyMetaRepositoryProtocol,
    ticker: str,
) -> CompanyMeta | None:
    """读取 CN/HK producer 当前可见的 CompanyMeta。

    Args:
        repository: 公司元数据仓储。
        ticker: canonical ticker。

    Returns:
        已发布 CompanyMeta；不存在时返回 ``None``。

    Raises:
        ValueError: 已发布元数据非法时抛出。
        OSError: 仓储读取失败时抛出。
    """

    try:
        return repository.get_company_meta(ticker)
    except FileNotFoundError:
        return None


__all__ = ["stage_company_meta_for_cn_download"]
