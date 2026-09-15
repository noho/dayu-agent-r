"""下载来源与既有文档身份的绑定；财期纠正不会重新分配已存在的文档 ID。"""

import hashlib

from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.cn_download_models import CnReportCandidate
from dayu.fins.pipelines.cn_form_utils import build_cn_filing_ids
from dayu.fins.storage import SourceDocumentRepositoryProtocol


def resolve_cn_download_ids(
    ticker: str,
    candidate: CnReportCandidate,
    repository: SourceDocumentRepositoryProtocol,
) -> tuple[str, str]:
    """优先绑定同 provider/source_id 的既有文档，再分配新身份。

    参数：ticker 为公司，candidate 为原始来源候选，repository 为来源仓储。
    返回：外部及内部文档 ID。异常：ValueError 表示来源重复或身份缺失；仓储异常透传。
    """
    allocated = build_cn_filing_ids(
        ticker=ticker,
        form_type=candidate.period_projection.identity_period,
        fiscal_year=candidate.fiscal_year,
        fiscal_period=candidate.period_projection.identity_period,
        amended=candidate.amended,
    )
    if candidate.provider != "hkexnews":
        return allocated
    matches: list[tuple[str, str]] = []
    allocated_period_changed = False
    for document_id in repository.list_source_document_ids(ticker, SourceKind.FILING):
        meta = repository.get_source_meta(ticker, document_id, SourceKind.FILING)
        if document_id == allocated[0]:
            allocated_period_changed = (
                meta.get("fiscal_period") != candidate.period_projection.identity_period
                or meta.get("fiscal_year") != candidate.fiscal_year
            )
        if meta.get("source_provider") != candidate.provider or meta.get("source_id") != candidate.source_id:
            continue
        internal = meta.get("internal_document_id")
        if not isinstance(internal, str) or not internal:
            raise ValueError("既有下载来源缺少内部文档身份")
        matches.append((document_id, internal))
    if len(matches) > 1:
        raise ValueError("同一下载来源对应多个文档，无法唯一绑定")
    if matches:
        return matches[0]
    if allocated_period_changed:
        # 旧 Q1 ID 已被纠正为 Q3 时，真正的 Q1 必须有自己的身份，不能覆盖纠正后的来源。
        digest = hashlib.sha1(f"{ticker}|{candidate.provider}|{candidate.source_id}".encode()).hexdigest()
        return f"fil_cn_{digest}", f"cn_{digest}"
    return allocated
