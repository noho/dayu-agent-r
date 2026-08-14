"""SEC company meta 与 ticker alias 真源。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Optional

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import BatchToken, CompanyMeta, now_iso8601
from dayu.fins.storage import CompanyMetaRepositoryProtocol
from dayu.fins.ticker_normalization import build_company_ticker_identity, try_normalize_ticker


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
        alias
        for alias in alias_list
        if isinstance(alias, str) and try_normalize_ticker(alias) is not None
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
) -> None:
    """写入 SEC 公司级元数据。

    Args:
        repository: 公司元数据仓储。
        ticker: 股票代码。
        company_id: 公司 ID。
        company_name: 公司名称。
        ticker_aliases: 可选 ticker alias。
        batch: caller 显式传入的 batch capability。

    Returns:
        无。

    Raises:
        OSError: 仓储写入失败时抛出。
        ValueError: batch capability 非法时抛出。
    """

    ticker_identity = build_company_ticker_identity(ticker, ticker_aliases or ())
    repository.upsert_company_meta(
        CompanyMeta(
            company_id=company_id,
            company_name=company_name or ticker,
            ticker_identity=ticker_identity,
            resolver_version="market_resolver_v1",
            updated_at=now_iso8601(),
        ),
        batch=batch,
    )


__all__ = [
    "extract_sec_ticker_aliases",
    "merge_ticker_aliases",
    "upsert_company_meta",
]
