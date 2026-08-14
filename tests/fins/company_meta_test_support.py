"""CompanyMeta storage contract 的测试装配辅助。"""

from __future__ import annotations

from dayu.fins.domain.company_meta_contract import build_company_meta_commit_intent
from dayu.fins.domain.document_models import BatchToken, CompanyMeta
from dayu.fins.storage import CompanyMetaRepositoryProtocol


def stage_company_meta_fixture(
    repository: CompanyMetaRepositoryProtocol,
    meta: CompanyMeta,
    *,
    batch: BatchToken,
) -> None:
    """把测试声明的完整 CompanyMeta 转成真实 refresh intent 并 stage。

    Args:
        repository: 被测 CompanyMeta 仓储。
        meta: 测试明确声明的目标业务事实。
        batch: caller-owned batch capability。

    Returns:
        无。

    Raises:
        ValueError: identity、intent 或 batch 不满足 contract 时抛出。
        OSError: published 读取或 staging 失败时抛出。
    """

    try:
        observed_meta = repository.get_company_meta(meta.ticker_identity.canonical_ticker)
    except FileNotFoundError:
        observed_meta = None
    intent = build_company_meta_commit_intent(
        proposed_identity=meta.ticker_identity,
        merge_mode="refresh_if_stale",
        observed_meta=observed_meta,
        proposed_company_id=meta.company_id,
        proposed_company_name=meta.company_name,
        resolver_version=meta.resolver_version,
    )
    repository.stage_company_meta_intent(intent, batch=batch)


__all__ = ["stage_company_meta_fixture"]
