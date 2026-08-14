"""SEC company meta 与 ticker alias 真源。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Optional

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.company_meta_contract import (
    CompanyMetaCommitIntent,
    build_company_meta_commit_intent,
)
from dayu.fins.domain.document_models import BatchToken, CompanyMeta
from dayu.fins.storage import CompanyMetaRepositoryProtocol
from dayu.fins.ticker_normalization import build_company_ticker_identity, try_normalize_ticker

_SEC_RESOLVER_VERSION = "market_resolver_v1"


def extract_sec_ticker_aliases(
    *,
    submissions: dict[str, JsonValue],
    primary_ticker: str,
) -> tuple[str, ...]:
    """从 SEC submissions 中提取 ticker alias。

    Args:
        submissions: SEC submissions JSON。
        primary_ticker: 主 ticker。

    Returns:
        经唯一 identity builder 规范化、去重且不重复 canonical 的 aliases。

    Raises:
        ValueError: ``primary_ticker`` 归一化后仍为空时抛出。
    """

    raw_aliases = submissions.get("tickers")
    alias_list = raw_aliases if isinstance(raw_aliases, list) else []
    valid_external_aliases = tuple(
        alias for alias in alias_list if isinstance(alias, str) and try_normalize_ticker(alias) is not None
    )
    return build_company_ticker_identity(
        primary_ticker,
        valid_external_aliases,
    ).accepted_aliases


def merge_ticker_aliases(
    *,
    primary_ticker: str,
    alias_groups: Sequence[Optional[Sequence[str]]],
) -> tuple[str, ...]:
    """按顺序合并多组 ticker alias。

    每个 alias 都由唯一 identity builder 严格归一化并稳定去重。

    Args:
        primary_ticker: 主 ticker。
        alias_groups: 待合并的 alias 组；顺序决定进入 meta 的先后。

    Returns:
        不重复 canonical 的 accepted aliases。

    Raises:
        ValueError: ``primary_ticker`` 归一化后仍为空时抛出。
    """

    declared_aliases: list[str] = []
    for alias_group in alias_groups:
        declared_aliases.extend(alias_group or ())
    return build_company_ticker_identity(
        primary_ticker,
        declared_aliases,
    ).accepted_aliases


def upsert_company_meta(
    *,
    repository: CompanyMetaRepositoryProtocol,
    ticker: str,
    company_id: str,
    company_name: str,
    ticker_aliases: Optional[Sequence[str]] = None,
    batch: BatchToken,
) -> CompanyMetaCommitIntent | None:
    """写入 SEC 公司级元数据。

    Args:
        repository: 公司元数据仓储。
        ticker: 股票代码。
        company_id: 公司 ID。
        company_name: 公司名称。
        ticker_aliases: 可选 ticker alias。
        batch: caller 显式传入的 batch capability。

    Returns:
        已 stage 的提交意图；fresh 且 identity 未变化时返回 ``None``。

    Raises:
        OSError: 仓储写入失败时抛出。
        ValueError: batch capability 非法时抛出。
    """

    ticker_identity = build_company_ticker_identity(ticker, ticker_aliases or ())
    existing_meta = _load_existing_company_meta(repository, ticker_identity.canonical_ticker)
    if existing_meta is not None and existing_meta.resolver_version == _SEC_RESOLVER_VERSION:
        merged_identity = build_company_ticker_identity(
            ticker_identity.canonical_ticker,
            (*existing_meta.ticker_identity.accepted_aliases, *ticker_identity.accepted_aliases),
        )
        if merged_identity == existing_meta.ticker_identity:
            return None
        merge_mode = "preserve_published"
        proposed_company_id: str | None = None
        proposed_company_name: str | None = None
    else:
        merge_mode = "refresh_if_stale"
        proposed_company_id = company_id
        proposed_company_name = company_name or ticker
    intent = build_company_meta_commit_intent(
        proposed_identity=ticker_identity,
        merge_mode=merge_mode,
        observed_meta=existing_meta,
        proposed_company_id=proposed_company_id,
        proposed_company_name=proposed_company_name,
        resolver_version=_SEC_RESOLVER_VERSION,
    )
    repository.stage_company_meta_intent(intent, batch=batch)
    return intent


def _load_existing_company_meta(
    repository: CompanyMetaRepositoryProtocol,
    ticker: str,
) -> CompanyMeta | None:
    """读取 SEC producer 当前可见的 CompanyMeta。

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


__all__ = [
    "extract_sec_ticker_aliases",
    "merge_ticker_aliases",
    "upsert_company_meta",
]
