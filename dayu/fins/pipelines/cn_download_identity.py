"""下载来源的只读身份索引与查询；财期纠正保留既有来源身份。"""

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.cn_download_models import CnReportCandidate
from dayu.fins.pipelines.cn_form_utils import build_cn_filing_ids
from dayu.fins.storage import SourceDocumentRepositoryProtocol, SourceMetaReadView

_HK_PROVIDER: Final = "hkexnews"
_MISSING_INTERNAL_ID: Final = "既有下载来源缺少内部文档身份"
_DUPLICATE_SOURCE: Final = "同一下载来源对应多个文档，无法唯一绑定"


@dataclass(frozen=True, slots=True)
class CnDownloadIdentityIndex:
    """单次观察的身份索引，不含完整性结论或写入授权。

    ticker 标明观察公司；source_matches 保存每来源全部外部/内部身份，
    allocated_periods 保存实际在场文档的原 JSON 财期，allocated_internal_ids
    保存所有在场元数据显式声明的可信内部身份，read_error 保留
    首个原读取异常。内部身份 None 表示查询该来源时应拒绝。
    """

    ticker: str
    source_matches: Mapping[tuple[str, str], tuple[tuple[str, str | None], ...]]
    allocated_periods: Mapping[str, tuple[JsonValue, JsonValue]]
    allocated_internal_ids: frozenset[str]
    read_error: ValueError | OSError | None


def build_cn_download_identity_index(view: SourceMetaReadView) -> CnDownloadIdentityIndex:
    """一次遍历成功前缀建立身份索引，不提前裁决候选相关错误。

    参数：view 为 storage 同窗 FILING 元数据观察。
    返回：顶层只读、保留全部匹配及原异常的身份索引；嵌套 JSON 只读消费。
    异常：ValueError 表示传入非 FILING 观察。
    """
    if view.source_kind is not SourceKind.FILING:
        raise ValueError("下载身份索引只允许 filing 元数据观察")
    source_matches: dict[tuple[str, str], list[tuple[str, str | None]]] = {}
    allocated_periods: dict[str, tuple[JsonValue, JsonValue]] = {}
    allocated_internal_ids: set[str] = set()
    for entry in view.entries:
        meta = entry.source_meta
        allocated_periods[entry.document_id] = (meta.get("fiscal_period"), meta.get("fiscal_year"))
        internal = meta.get("internal_document_id")
        internal_id = internal if isinstance(internal, str) and internal else None
        # 内部身份占用独立于来源 key 是否已知；只消费 owner 显式声明，不从名字推导。
        if internal_id is not None:
            allocated_internal_ids.add(internal_id)
        provider = meta.get("source_provider")
        source_id = meta.get("source_id")
        if not isinstance(provider, str) or not isinstance(source_id, str):
            continue
        source_matches.setdefault((provider, source_id), []).append((entry.document_id, internal_id))
    return CnDownloadIdentityIndex(
        view.ticker,
        MappingProxyType({key: tuple(matches) for key, matches in source_matches.items()}),
        MappingProxyType(allocated_periods),
        frozenset(allocated_internal_ids),
        view.read_error,
    )


def read_cn_download_identity_index(
    ticker: str,
    candidates: tuple[CnReportCandidate, ...],
    repository: SourceDocumentRepositoryProtocol,
) -> CnDownloadIdentityIndex:
    """仅在候选包含 HK 或 CN 年度来源时读取一次本窗口身份观察。

    参数：ticker 为公司；candidates 为本窗口全部待查询候选；repository 为来源仓储。
    返回：新建身份索引；空集合或 CN 非年度集合返回空只读索引且零仓储读取。
    异常：仓储完整枚举、guard 或其它未声明读取异常原样透传。
    """
    if not any(candidate.provider == _HK_PROVIDER or (candidate.provider == "cninfo" and candidate.period_projection.identity_period == "FY") for candidate in candidates):
        return CnDownloadIdentityIndex(ticker, MappingProxyType({}), MappingProxyType({}), frozenset(), None)
    return build_cn_download_identity_index(repository.read_source_meta_view(ticker, SourceKind.FILING))


def resolve_cn_download_ids(
    ticker: str,
    candidate: CnReportCandidate,
    index: CnDownloadIdentityIndex,
) -> tuple[str, str]:
    """纯查询同来源既有身份，再按原 JSON 财期比较分配新身份。

    参数：ticker 为公司；candidate 为原始来源候选；index 为当前窗口身份索引。
    返回：外部及内部文档 ID；CN FY 的新 seed/fallback 均检查显式外部及内部占用；非年度保持原直接分配。
    异常：ValueError 表示索引 ticker 不符、来源重复、内部身份缺失或年度 fallback 任一身份已占用；
    read_error 按旧扫描优先序抛出同一原 ValueError/OSError 对象。
    """
    allocated = build_cn_filing_ids(
        ticker=ticker,
        form_type=candidate.period_projection.identity_period,
        fiscal_year=candidate.fiscal_year,
        fiscal_period=candidate.period_projection.identity_period,
        amended=candidate.amended,
    )
    if candidate.provider != _HK_PROVIDER and candidate.period_projection.identity_period != "FY":
        return allocated
    if index.ticker != ticker:
        raise ValueError("下载身份索引 ticker 与查询不一致")
    matches = index.source_matches.get((candidate.provider, candidate.source_id), ())
    # 旧扫描在匹配且缺身份处立即失败；合法 duplicate 则必须等所有 get 完成。
    for _, internal in matches:
        if internal is None:
            raise ValueError(_MISSING_INTERNAL_ID)
    if index.read_error is not None:
        raise index.read_error
    if len(matches) > 1:
        raise ValueError(_DUPLICATE_SOURCE)
    if matches:
        document_id, internal = matches[0]
        # 上面的缺身份裁决已成立，此断言只表达索引查询的类型不变量。
        assert internal is not None
        return document_id, internal
    if candidate.provider == "cninfo":
        if allocated[0] in index.allocated_periods or allocated[1] in index.allocated_internal_ids:
            digest = hashlib.sha1(f"{ticker}|{candidate.provider}|{candidate.source_id}".encode()).hexdigest()
            fallback = (f"fil_cn_{digest}", f"cn_{digest}")
            if fallback[0] in index.allocated_periods or fallback[1] in index.allocated_internal_ids:
                raise ValueError("年度来源身份已被其它源占用")
            return fallback
        return allocated
    if allocated[0] in index.allocated_periods:
        fiscal_period, fiscal_year = index.allocated_periods[allocated[0]]
        if fiscal_period != candidate.period_projection.identity_period or fiscal_year != candidate.fiscal_year:
            # HK 保留仅财期纠正后的原规则，不改变其分配语义。
            digest = hashlib.sha1(f"{ticker}|{candidate.provider}|{candidate.source_id}".encode()).hexdigest()
            fallback = (f"fil_cn_{digest}", f"cn_{digest}")
            return fallback
    return allocated
