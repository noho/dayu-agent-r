"""上传场景公司元数据写入助手。

本模块聚合 upload 相关的 company meta 写入逻辑，以 upload resolver
版本作为既有元数据 freshness 真源。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from dayu.fins.domain.company_meta_contract import (
    CompanyMetaCommitIntent,
    build_company_meta_commit_intent,
)
from dayu.fins.domain.document_models import BatchToken, CompanyMeta
from dayu.fins.storage import CompanyMetaRepositoryProtocol
from dayu.fins.ticker_normalization import (
    build_company_ticker_identity,
    normalize_ticker,
    ticker_to_company_id,
)

UPLOAD_ACTIONS_REQUIRING_COMPANY_META: Final[frozenset[str]] = frozenset({"create", "update"})
RESOLVER_VERSION: Final[str] = "market_resolver_v1.0.0"


class UploadCompanyNameRequiredError(ValueError):
    """upload company meta 缺少必填公司名称。"""


@dataclass(frozen=True, slots=True)
class UploadCompanyMetaDecision:
    """upload workflow 的纯 company meta 决策。

    Attributes:
        disposition: 保留既有 meta、不处理或在 batch 中 stage 新 meta。
        company_meta_intent: stage 时的提交意图；其它 disposition 为 ``None``。
    """

    disposition: Literal["keep", "skip", "stage"]
    company_meta_intent: CompanyMetaCommitIntent | None


def resolve_upload_company_meta_decision(
    *,
    existing_meta: CompanyMeta | None,
    ticker: str,
    action: str,
    company_name: str | None,
    ticker_aliases: tuple[str, ...],
) -> UploadCompanyMetaDecision:
    """按 upload resolver freshness 产生不含 I/O 的 company meta 决策。

    Args:
        existing_meta: published company meta；不存在时为 ``None``。
        ticker: canonical ticker。
        action: 已解析上传动作。
        company_name: 可选公司名称。
        ticker_aliases: 用户提供的 ticker aliases。

    Returns:
        供 validation 与 workflow 共用的纯决策。

    Raises:
        UploadCompanyNameRequiredError: create/update 需要 stage 但缺少公司名称时抛出。
        ValueError: ticker/alias 非法或既有 identity 与请求不一致时抛出。
    """

    if action not in UPLOAD_ACTIONS_REQUIRING_COMPANY_META:
        return UploadCompanyMetaDecision(disposition="skip", company_meta_intent=None)
    proposed_identity = build_company_ticker_identity(ticker, ticker_aliases)
    if existing_meta is not None:
        existing_identity = existing_meta.ticker_identity
        if (
            existing_identity.canonical_ticker != proposed_identity.canonical_ticker
            or existing_identity.market != proposed_identity.market
            or existing_identity.exchange != proposed_identity.exchange
        ):
            raise ValueError("既有 CompanyMeta 与本次 canonical ticker identity 不一致")
        merged_identity = build_company_ticker_identity(
            proposed_identity.canonical_ticker,
            (
                *existing_identity.accepted_aliases,
                *proposed_identity.accepted_aliases,
            ),
        )
        if _existing_company_meta_is_fresh(
            existing_meta=existing_meta,
            resolver_version=RESOLVER_VERSION,
        ):
            if merged_identity == existing_identity:
                return UploadCompanyMetaDecision(disposition="keep", company_meta_intent=None)
            return UploadCompanyMetaDecision(
                disposition="stage",
                company_meta_intent=build_company_meta_commit_intent(
                    proposed_identity=proposed_identity,
                    merge_mode="preserve_published",
                    observed_meta=existing_meta,
                    proposed_company_id=None,
                    proposed_company_name=None,
                    resolver_version=RESOLVER_VERSION,
                ),
            )
    return UploadCompanyMetaDecision(
        disposition="stage",
        company_meta_intent=build_company_meta_commit_intent(
            proposed_identity=proposed_identity,
            merge_mode="refresh_if_stale",
            observed_meta=existing_meta,
            proposed_company_id=ticker_to_company_id(normalize_ticker(proposed_identity.canonical_ticker)),
            proposed_company_name=_require_upload_company_name(company_name),
            resolver_version=RESOLVER_VERSION,
        ),
    )


def stage_upload_company_meta_decision(
    *,
    repository: CompanyMetaRepositoryProtocol,
    decision: UploadCompanyMetaDecision,
    batch: BatchToken,
) -> None:
    """在 caller-owned batch 中 stage 已裁决的 company meta。

    Args:
        repository: company meta 仓储 owner。
        decision: pure resolver 决策。
        batch: caller 持有的 publication capability。

    Returns:
        无。

    Raises:
        ValueError: stage 决策缺少 company meta 时抛出。
        OSError: company meta staging 失败时抛出。
    """

    if decision.disposition != "stage":
        return
    if decision.company_meta_intent is None:
        raise ValueError("stage company meta decision 缺少 company_meta_intent")
    repository.stage_company_meta_intent(decision.company_meta_intent, batch=batch)


def stage_company_meta_for_upload(
    *,
    repository: CompanyMetaRepositoryProtocol,
    ticker: str,
    action: str,
    company_name: str | None,
    ticker_aliases: Sequence[str] | None = None,
    batch: BatchToken,
) -> None:
    """在 caller-owned batch 中读取、裁决并 stage 公司元数据。

    Args:
        repository: 公司元数据仓储实现。
        ticker: 股票代码。
        action: 上传动作。
        company_name: 公司名称。
        ticker_aliases: 可选 ticker alias 列表。
        batch: caller 显式传入的 batch capability。

    Returns:
        无。

    Raises:
        UploadCompanyNameRequiredError: create/update 场景在缺少公司名称时抛出。
        ValueError: ticker/alias 非法或既有 identity 与请求不一致时抛出。
        OSError: 仓储写入失败时抛出。
    """

    existing_meta = _load_existing_company_meta(repository=repository, ticker=ticker)
    decision = resolve_upload_company_meta_decision(
        existing_meta=existing_meta,
        ticker=ticker,
        action=action.strip().lower(),
        company_name=company_name,
        ticker_aliases=tuple(ticker_aliases or ()),
    )
    stage_upload_company_meta_decision(
        repository=repository,
        decision=decision,
        batch=batch,
    )


def build_upload_company_id(ticker: str) -> str:
    """按上传链路稳定规则生成公司 ID。

    Args:
        ticker: 股票代码，可为原始输入或 canonical ticker。

    Returns:
        由 ``ticker_to_company_id`` 推导出的公司 ID。

    Raises:
        ValueError: ticker 为空或无法归一化时抛出。
    """

    return ticker_to_company_id(normalize_ticker(ticker))


def _require_upload_company_name(value: str | None) -> str:
    """校验并返回 upload company meta 的公司名称。

    Args:
        value: 原始公司名称。

    Returns:
        去除首尾空白后的字段值。

    Raises:
        UploadCompanyNameRequiredError: 公司名称为空时抛出。
    """

    normalized_value = str(value or "").strip()
    if not normalized_value:
        raise UploadCompanyNameRequiredError("create/update 时必须提供 --company-name")
    return normalized_value


def _load_existing_company_meta(
    *,
    repository: CompanyMetaRepositoryProtocol,
    ticker: str,
) -> CompanyMeta | None:
    """读取现有公司元数据。

    Args:
        repository: 公司元数据仓储实现。
        ticker: 股票代码。

    Returns:
        若仓储中已存在公司元数据则返回该对象，否则返回 ``None``。

    Raises:
        ValueError: 现有元数据格式非法时抛出。
        OSError: 仓储读取失败时抛出。
    """

    try:
        return repository.get_company_meta(ticker)
    except FileNotFoundError:
        return None


def _existing_company_meta_is_fresh(*, existing_meta: CompanyMeta, resolver_version: str) -> bool:
    """判断既有 upload company meta 是否由当前 resolver 语义产生。

    Args:
        existing_meta: 仓储中已存在的公司元数据。
        resolver_version: 当前 upload company identity resolver 版本。

    Returns:
        当既有元数据的 resolver 版本与当前版本一致时返回 ``True``。

    Raises:
        无。
    """

    return existing_meta.resolver_version == resolver_version


__all__ = [
    "RESOLVER_VERSION",
    "UPLOAD_ACTIONS_REQUIRING_COMPANY_META",
    "UploadCompanyNameRequiredError",
    "UploadCompanyMetaDecision",
    "build_upload_company_id",
    "resolve_upload_company_meta_decision",
    "stage_company_meta_for_upload",
    "stage_upload_company_meta_decision",
]
