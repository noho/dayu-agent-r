"""公司元数据提交意图与权威合并契约。

本模块是 CompanyMeta 非身份字段乐观前置条件、提交意图与 commit-time 合并规则的
唯一 owner。pipeline 只构造意图，storage 只提供受锁保护的当前 published 真值与
提交时点；二者都不得自行复制或改写本模块的字段选择规则。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias
import unicodedata

from dayu.fins.domain.document_models import CompanyMeta
from dayu.fins.ticker_normalization import (
    CompanyTickerIdentity,
    build_company_ticker_identity,
)


CompanyMetaMergeMode: TypeAlias = Literal["preserve_published", "refresh_if_stale"]
"""CompanyMeta commit-time 非身份字段选择模式。"""

_PRESERVE_PUBLISHED: CompanyMetaMergeMode = "preserve_published"
_REFRESH_IF_STALE: CompanyMetaMergeMode = "refresh_if_stale"


class CompanyMetaConcurrentUpdateError(RuntimeError):
    """CompanyMeta 乐观前置条件在提交时已经失效。"""

    def __init__(self) -> None:
        """构造不携带路径或原始业务字段的并发更新异常。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__("公司元数据已被并发更新")


@dataclass(frozen=True, slots=True)
class CompanyMetaNonIdentitySnapshot:
    """CompanyMeta 非身份字段的精确乐观前置条件。"""

    company_id: str
    company_name: str
    resolver_version: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class CompanyMetaCommitIntent:
    """pipeline 交给 storage 的 CompanyMeta mutation intent。

    Attributes:
        proposed_identity: 本次拟议的 canonical ticker 与 accepted aliases。
        merge_mode: 非身份字段的提交时合并模式。
        expected_non_identity: 可选的已观察非身份字段乐观前置条件。
        proposed_company_id: refresh 模式拟采用的公司 ID。
        proposed_company_name: refresh 模式拟采用的公司名称。
        resolver_version: 本次 producer 的 resolver 版本。
        requested_company_name: 本次 upload 明确提交的公司名称；下载语义为 ``None``。
    """

    proposed_identity: CompanyTickerIdentity
    merge_mode: CompanyMetaMergeMode
    expected_non_identity: CompanyMetaNonIdentitySnapshot | None
    proposed_company_id: str | None
    proposed_company_name: str | None
    resolver_version: str
    requested_company_name: str | None = None


@dataclass(frozen=True, slots=True)
class CompanyNameIgnoredChange:
    """提交名称未成为最终 published 名称的业务事实。

    Attributes:
        requested_company_name: 本次 upload 明确提交且已去除首尾空白的名称。
        published_company_name: publication-lock 内最终保留的 canonical 名称。
    """

    requested_company_name: str
    published_company_name: str


@dataclass(frozen=True, slots=True)
class CompanyMetaCommitOutcome:
    """CompanyMeta 提交 owner 产生的最终结果。

    Attributes:
        company_meta: 用于本次物理发布的最终 CompanyMeta。
        ignored_company_name: 请求名称未被采用时的 typed fact；否则为 ``None``。
    """

    company_meta: CompanyMeta
    ignored_company_name: CompanyNameIgnoredChange | None


def build_company_meta_commit_intent(
    *,
    proposed_identity: CompanyTickerIdentity,
    merge_mode: CompanyMetaMergeMode,
    observed_meta: CompanyMeta | None,
    proposed_company_id: str | None,
    proposed_company_name: str | None,
    resolver_version: str,
    requested_company_name: str | None = None,
) -> CompanyMetaCommitIntent:
    """构造并校验 CompanyMeta 提交意图。

    Args:
        proposed_identity: 本次 canonical 与明确声明的 accepted aliases。
        merge_mode: 保留 published 非身份事实或在仍 stale 时刷新。
        observed_meta: prevalidation/producer 观察到的 published CompanyMeta。
        proposed_company_id: refresh 模式显式提供的公司 ID。
        proposed_company_name: refresh 模式显式提供的公司名称。
        resolver_version: 本次 producer 的 resolver 版本。
        requested_company_name: upload 明确提交的名称；下载调用保持 ``None``。

    Returns:
        已校验、不可变的提交意图。

    Raises:
        ValueError: mode、identity、字段组合或文本不满足契约时抛出。
    """

    _require_identity_matches_observed(proposed_identity, observed_meta)
    normalized_resolver_version = _require_non_empty_text(
        resolver_version,
        "resolver_version",
    )
    normalized_requested_company_name = _normalize_optional_requested_company_name(
        requested_company_name
    )
    expected_snapshot = _company_meta_non_identity_snapshot(observed_meta) if observed_meta is not None else None
    if merge_mode == _PRESERVE_PUBLISHED:
        if observed_meta is None:
            raise ValueError("preserve_published 必须基于已观察到的 CompanyMeta")
        if proposed_company_id is not None or proposed_company_name is not None:
            raise ValueError("preserve_published 禁止携带 proposed company fields")
    elif merge_mode == _REFRESH_IF_STALE:
        proposed_company_id = _require_non_empty_text(
            proposed_company_id,
            "proposed_company_id",
        )
        proposed_company_name = _require_non_empty_text(
            proposed_company_name,
            "proposed_company_name",
        )
    else:
        raise ValueError("未知 CompanyMeta merge mode")
    return CompanyMetaCommitIntent(
        proposed_identity=proposed_identity,
        merge_mode=merge_mode,
        expected_non_identity=expected_snapshot,
        proposed_company_id=proposed_company_id,
        proposed_company_name=proposed_company_name,
        resolver_version=normalized_resolver_version,
        requested_company_name=normalized_requested_company_name,
    )


def company_names_are_equivalent(left: str, right: str) -> bool:
    """判断两个公司名称是否仅存在表现形式差异。

    Args:
        left: 左侧公司名称。
        right: 右侧公司名称。

    Returns:
        两侧经 Unicode NFKC、空白折叠与大小写折叠后相同时返回 ``True``。

    Raises:
        无。
    """

    return _normalize_company_name_for_comparison(left) == _normalize_company_name_for_comparison(right)


def merge_company_meta_for_commit(
    *,
    current_published: CompanyMeta | None,
    intent: CompanyMetaCommitIntent,
    committed_at: str,
) -> CompanyMetaCommitOutcome:
    """用 commit-time published 真值与 intent 生成最终 CompanyMeta。

    Args:
        current_published: storage 在完整锁保护下重读的 authoritative CompanyMeta。
        intent: pipeline 已构造的 mutation intent。
        committed_at: storage 提供的单次提交时点。

    Returns:
        含可写入 staging 的最终 CompanyMeta 与名称采用事实的 typed outcome。

    Raises:
        CompanyMetaConcurrentUpdateError: 乐观前置条件失效且无法安全合并时抛出。
        ValueError: current identity、intent 或提交时点违反 owner contract 时抛出。
    """

    normalized_committed_at = _require_non_empty_text(committed_at, "committed_at")
    if current_published is not None:
        _require_identity_matches_observed(intent.proposed_identity, current_published)
        final_identity = build_company_ticker_identity(
            intent.proposed_identity.canonical_ticker,
            (
                *current_published.ticker_identity.accepted_aliases,
                *intent.proposed_identity.accepted_aliases,
            ),
        )
    else:
        final_identity = intent.proposed_identity

    if intent.merge_mode == _PRESERVE_PUBLISHED:
        if current_published is None:
            raise CompanyMetaConcurrentUpdateError()
        final_meta = _company_meta_from_published(
            current_published=current_published,
            final_identity=final_identity,
            committed_at=normalized_committed_at,
        )
    elif intent.merge_mode != _REFRESH_IF_STALE:
        raise ValueError("未知 CompanyMeta merge mode")
    elif current_published is None:
        if intent.expected_non_identity is not None:
            raise CompanyMetaConcurrentUpdateError()
        final_meta = _company_meta_from_refresh(
            intent=intent,
            final_identity=final_identity,
            committed_at=normalized_committed_at,
        )
    elif _company_meta_non_identity_snapshot(current_published) == intent.expected_non_identity:
        final_meta = _company_meta_from_refresh(
            intent=intent,
            final_identity=final_identity,
            committed_at=normalized_committed_at,
        )
    elif current_published.resolver_version == intent.resolver_version:
        final_meta = _company_meta_from_published(
            current_published=current_published,
            final_identity=final_identity,
            committed_at=normalized_committed_at,
        )
    else:
        raise CompanyMetaConcurrentUpdateError()
    return _build_company_meta_commit_outcome(company_meta=final_meta, intent=intent)


def _build_company_meta_commit_outcome(
    *,
    company_meta: CompanyMeta,
    intent: CompanyMetaCommitIntent,
) -> CompanyMetaCommitOutcome:
    """依据最终 CompanyMeta 生成唯一名称采用事实。

    Args:
        company_meta: 即将写入 staging 并物理发布的最终 CompanyMeta。
        intent: 携带可选 upload 请求名称的提交意图。

    Returns:
        与最终 CompanyMeta 同源的 typed commit outcome。

    Raises:
        无。
    """

    requested_company_name = intent.requested_company_name
    ignored_company_name = None
    if requested_company_name is not None and not company_names_are_equivalent(
        requested_company_name,
        company_meta.company_name,
    ):
        ignored_company_name = CompanyNameIgnoredChange(
            requested_company_name=requested_company_name,
            published_company_name=company_meta.company_name,
        )
    return CompanyMetaCommitOutcome(
        company_meta=company_meta,
        ignored_company_name=ignored_company_name,
    )


def _normalize_company_name_for_comparison(value: str) -> str:
    """把公司名称规范化为只用于等价比较的文本。

    Args:
        value: 原始公司名称。

    Returns:
        经 NFKC、Unicode 空白折叠与 casefold 处理的比较值。

    Raises:
        无。
    """

    normalized_unicode = unicodedata.normalize("NFKC", value)
    return " ".join(normalized_unicode.split()).casefold()


def _normalize_optional_requested_company_name(value: str | None) -> str | None:
    """校验并规范 upload 明确提交的可选公司名称。

    Args:
        value: 可选原始请求名称。

    Returns:
        ``None`` 或仅去除首尾空白后的非空名称。

    Raises:
        ValueError: 非 ``None`` 名称去除首尾空白后为空时抛出。
    """

    if value is None:
        return None
    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError("requested_company_name 必须为非空字符串")
    return normalized_value


def _company_meta_non_identity_snapshot(
    meta: CompanyMeta,
) -> CompanyMetaNonIdentitySnapshot:
    """投影 CompanyMeta 的精确非身份字段快照。

    Args:
        meta: 已严格校验的 CompanyMeta。

    Returns:
        不含 ticker identity 的不可变快照。

    Raises:
        无。
    """

    return CompanyMetaNonIdentitySnapshot(
        company_id=meta.company_id,
        company_name=meta.company_name,
        resolver_version=meta.resolver_version,
        updated_at=meta.updated_at,
    )


def _company_meta_from_published(
    *,
    current_published: CompanyMeta,
    final_identity: CompanyTickerIdentity,
    committed_at: str,
) -> CompanyMeta:
    """保留 published 非身份事实并按真实 identity mutation 选择时点。

    Args:
        current_published: authoritative CompanyMeta。
        final_identity: stable union 后的最终 identity。
        committed_at: 本次提交时点。

    Returns:
        保留 published 非身份事实的最终 CompanyMeta。

    Raises:
        无。
    """

    updated_at = current_published.updated_at if final_identity == current_published.ticker_identity else committed_at
    return CompanyMeta(
        company_id=current_published.company_id,
        company_name=current_published.company_name,
        ticker_identity=final_identity,
        resolver_version=current_published.resolver_version,
        updated_at=updated_at,
    )


def _company_meta_from_refresh(
    *,
    intent: CompanyMetaCommitIntent,
    final_identity: CompanyTickerIdentity,
    committed_at: str,
) -> CompanyMeta:
    """把显式 refresh 字段投影为最终 CompanyMeta。

    Args:
        intent: 已校验的 refresh intent。
        final_identity: stable union 后的最终 identity。
        committed_at: 本次提交时点。

    Returns:
        使用显式 refresh facts 的最终 CompanyMeta。

    Raises:
        ValueError: intent 缺少 refresh fields 时抛出。
    """

    company_id = _require_non_empty_text(intent.proposed_company_id, "proposed_company_id")
    company_name = _require_non_empty_text(
        intent.proposed_company_name,
        "proposed_company_name",
    )
    return CompanyMeta(
        company_id=company_id,
        company_name=company_name,
        ticker_identity=final_identity,
        resolver_version=intent.resolver_version,
        updated_at=committed_at,
    )


def _require_identity_matches_observed(
    proposed_identity: CompanyTickerIdentity,
    observed_meta: CompanyMeta | None,
) -> None:
    """校验 proposed 与 observed CompanyMeta 的 corpus identity 一致。

    Args:
        proposed_identity: 本次拟议 identity。
        observed_meta: 可选已发布 CompanyMeta。

    Returns:
        无。

    Raises:
        ValueError: canonical、market 或 exchange 不一致时抛出。
    """

    if observed_meta is None:
        return
    observed_identity = observed_meta.ticker_identity
    if (
        proposed_identity.canonical_ticker != observed_identity.canonical_ticker
        or proposed_identity.market != observed_identity.market
        or proposed_identity.exchange != observed_identity.exchange
    ):
        raise ValueError("CompanyMeta 与 proposed ticker identity 不一致")


def _require_non_empty_text(value: str | None, field_name: str) -> str:
    """校验并返回不改变内容的非空字符串。

    Args:
        value: 待校验文本。
        field_name: 错误字段名。

    Returns:
        原始非空字符串。

    Raises:
        ValueError: 值不是非空字符串时抛出。
    """

    if not isinstance(value, str) or value == "":
        raise ValueError(f"{field_name} 必须为非空字符串")
    return value


__all__ = [
    "CompanyMetaCommitIntent",
    "CompanyMetaCommitOutcome",
    "CompanyMetaConcurrentUpdateError",
    "CompanyMetaMergeMode",
    "CompanyNameIgnoredChange",
    "CompanyMetaNonIdentitySnapshot",
    "build_company_meta_commit_intent",
    "company_names_are_equivalent",
    "merge_company_meta_for_commit",
]
