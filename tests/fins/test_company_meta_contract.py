"""CompanyMeta commit intent 与 authoritative merge owner 测试。"""

from __future__ import annotations

import pytest

from dayu.fins.domain.company_meta_contract import (
    CompanyMetaConcurrentUpdateError,
    build_company_meta_commit_intent,
    merge_company_meta_for_commit,
)
from dayu.fins.domain.document_models import CompanyMeta
from dayu.fins.ticker_normalization import build_company_ticker_identity


def test_preserve_published_unions_aliases_and_preserves_non_identity() -> None:
    """preserve 模式应只合并 aliases，并保留权威非身份事实。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: stable union、非身份字段或更新时间不符合契约时抛出。
    """

    observed = _meta(aliases=("MSFT",), version="resolver-v1", updated_at="old")
    intent = build_company_meta_commit_intent(
        proposed_identity=build_company_ticker_identity(
            "DELTA",
            ("msft.us", "delta.us", "DLET"),
        ),
        merge_mode="preserve_published",
        observed_meta=observed,
        proposed_company_id=None,
        proposed_company_name=None,
        resolver_version="upload-v1",
    )
    current = _meta(
        aliases=("MSFT", "DLTA"),
        version="resolver-v2",
        updated_at="concurrent",
    )

    merged = merge_company_meta_for_commit(
        current_published=current,
        intent=intent,
        committed_at="commit",
    )

    assert merged.ticker_identity.canonical_ticker == "DELTA"
    assert merged.ticker_identity.accepted_aliases == ("MSFT", "DLTA", "DLET")
    assert merged.company_id == current.company_id
    assert merged.company_name == current.company_name
    assert merged.resolver_version == "resolver-v2"
    assert merged.updated_at == "commit"


def test_preserve_published_without_identity_mutation_keeps_updated_at() -> None:
    """没有真实 mutation 时 preserve 模式应保留 published updated_at。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: updated_at 被无意义刷新时抛出。
    """

    current = _meta(aliases=("MSFT",), version="resolver-v1", updated_at="old")
    intent = build_company_meta_commit_intent(
        proposed_identity=build_company_ticker_identity("DELTA", ("MSFT",)),
        merge_mode="preserve_published",
        observed_meta=current,
        proposed_company_id=None,
        proposed_company_name=None,
        resolver_version="upload-v1",
    )

    merged = merge_company_meta_for_commit(
        current_published=current,
        intent=intent,
        committed_at="commit",
    )

    assert merged == current


def test_refresh_if_stale_creates_meta_for_absent_authoritative_state() -> None:
    """未观察到 meta 时 refresh 应可创建全新或 meta-less corpus 的 meta。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: create transition 未使用显式 refresh facts 时抛出。
    """

    identity = build_company_ticker_identity("V.BA", ("v.ba.us", "V-BA"))
    intent = build_company_meta_commit_intent(
        proposed_identity=identity,
        merge_mode="refresh_if_stale",
        observed_meta=None,
        proposed_company_id="visa",
        proposed_company_name="Visa",
        resolver_version="resolver-v2",
    )

    merged = merge_company_meta_for_commit(
        current_published=None,
        intent=intent,
        committed_at="commit",
    )

    assert merged.ticker_identity == identity
    assert merged.company_id == "visa"
    assert merged.company_name == "Visa"
    assert merged.updated_at == "commit"


def test_refresh_if_stale_refreshes_exact_snapshot_and_preserves_concurrent_aliases() -> None:
    """snapshot 未变化时 refresh 应更新事实并保留当前 aliases。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: refresh 或 alias union 不符合契约时抛出。
    """

    observed = _meta(aliases=("DLTA",), version="resolver-v1", updated_at="old")
    intent = build_company_meta_commit_intent(
        proposed_identity=build_company_ticker_identity("DELTA", ("MSFT",)),
        merge_mode="refresh_if_stale",
        observed_meta=observed,
        proposed_company_id="new-id",
        proposed_company_name="New Name",
        resolver_version="resolver-v2",
    )

    merged = merge_company_meta_for_commit(
        current_published=observed,
        intent=intent,
        committed_at="commit",
    )

    assert merged.company_id == "new-id"
    assert merged.company_name == "New Name"
    assert merged.ticker_identity.accepted_aliases == ("DLTA", "MSFT")
    assert merged.resolver_version == "resolver-v2"


def test_refresh_if_stale_preserves_newer_same_version_authoritative_facts() -> None:
    """同 resolver version 的并发刷新应保留较新的 authoritative facts。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: commit 用旧 snapshot 覆盖新事实时抛出。
    """

    observed = _meta(aliases=(), version="resolver-v1", updated_at="old")
    intent = build_company_meta_commit_intent(
        proposed_identity=build_company_ticker_identity("DELTA", ("MSFT",)),
        merge_mode="refresh_if_stale",
        observed_meta=observed,
        proposed_company_id="stale-id",
        proposed_company_name="Stale Name",
        resolver_version="resolver-v2",
    )
    current = CompanyMeta(
        company_id="newer-id",
        company_name="Newer Name",
        ticker_identity=build_company_ticker_identity("DELTA", ("DLTA",)),
        resolver_version="resolver-v2",
        updated_at="newer",
    )

    merged = merge_company_meta_for_commit(
        current_published=current,
        intent=intent,
        committed_at="commit",
    )

    assert merged.company_id == "newer-id"
    assert merged.company_name == "Newer Name"
    assert merged.ticker_identity.accepted_aliases == ("DLTA", "MSFT")
    assert merged.updated_at == "commit"


@pytest.mark.parametrize("current", (None, "different-version"))
def test_refresh_if_stale_rejects_lost_authoritative_precondition(
    current: str | None,
) -> None:
    """meta 消失或仍为不同版本时 refresh 应拒绝 lost update。

    Args:
        current: ``None`` 表示 meta 消失，否则表示另一 stale version。

    Returns:
        无。

    Raises:
        AssertionError: 乐观前置条件失效后仍允许覆盖时抛出。
    """

    observed = _meta(aliases=(), version="resolver-v1", updated_at="old")
    intent = build_company_meta_commit_intent(
        proposed_identity=build_company_ticker_identity("DELTA", ("MSFT",)),
        merge_mode="refresh_if_stale",
        observed_meta=observed,
        proposed_company_id="new-id",
        proposed_company_name="New Name",
        resolver_version="resolver-v2",
    )
    current_meta = None if current is None else _meta(aliases=("DLTA",), version=current, updated_at="newer")

    with pytest.raises(CompanyMetaConcurrentUpdateError):
        merge_company_meta_for_commit(
            current_published=current_meta,
            intent=intent,
            committed_at="commit",
        )


def test_intent_builder_rejects_identity_and_field_mode_mismatch() -> None:
    """intent owner 应拒绝 canonical mismatch 与非法字段组合。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 非法 intent 被构造成功时抛出。
    """

    observed = _meta(aliases=(), version="resolver-v1", updated_at="old")
    with pytest.raises(ValueError, match="不一致"):
        build_company_meta_commit_intent(
            proposed_identity=build_company_ticker_identity("MSFT", ()),
            merge_mode="preserve_published",
            observed_meta=observed,
            proposed_company_id=None,
            proposed_company_name=None,
            resolver_version="resolver-v1",
        )
    with pytest.raises(ValueError, match="禁止携带"):
        build_company_meta_commit_intent(
            proposed_identity=observed.ticker_identity,
            merge_mode="preserve_published",
            observed_meta=observed,
            proposed_company_id="forbidden",
            proposed_company_name=None,
            resolver_version="resolver-v1",
        )


def _meta(
    *,
    aliases: tuple[str, ...],
    version: str,
    updated_at: str,
) -> CompanyMeta:
    """构造 DELTA owner 测试 CompanyMeta。

    Args:
        aliases: accepted aliases。
        version: resolver version。
        updated_at: 更新时间。

    Returns:
        严格 CompanyMeta。

    Raises:
        ValueError: 测试 alias 不符合 ticker grammar 时抛出。
    """

    return CompanyMeta(
        company_id="company-delta",
        company_name="Delta Inc.",
        ticker_identity=build_company_ticker_identity("DELTA", aliases),
        resolver_version=version,
        updated_at=updated_at,
    )
