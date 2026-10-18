"""CN 年度拒绝的窄日志投影；不解释原件、异常文本或来源 locator。"""

import hashlib
import json
import re
from typing import Literal

from dayu.fins._log import Log
from dayu.fins.pipelines.cn_annual_report_facts import CnAnnualReportFactsReason
from dayu.fins.pipelines.cn_annual_report_source import CnAnnualReportSourceReason

CnAnnualReportRejectionStage = Literal[
    "remote_discovery", "local_discovery", "download_review", "complete_original_review", "local_declaration_read",
]
_SOURCE_REFERENCE = re.compile(r"[0-9]{1,64}")
_DOCUMENT_REFERENCE = re.compile(r"[A-Za-z0-9_-]{1,240}")
_MODULE = "FINS.CN_ANNUAL_REPORT"


def _safe_reference(value: str, pattern: re.Pattern[str]) -> str:
    """投影有界引用。参数：value 为身份，pattern 为允许格式。返回：转义引用或不可展示标记和摘要。异常：无。"""
    if pattern.fullmatch(value):
        return json.dumps(value, ensure_ascii=True)
    digest = hashlib.sha256(value.encode("utf-8", errors="surrogatepass")).hexdigest()
    return f"<不可展示;sha256={digest}>"


def log_cn_annual_report_rejection(
    *,
    source_id: str,
    stage: CnAnnualReportRejectionStage,
    reason: CnAnnualReportFactsReason | CnAnnualReportSourceReason | Literal["source_document_facts_mismatch"],
    document_id: str | None = None,
) -> None:
    """在默认日志记录 owner 原因和调用边界引用，不记录底层异常。

    参数：source_id 为已知公告引用；stage 为实际输入阶段；reason 由事实/声明/比对 owner 产生；
    document_id 仅在已有真实文档身份时提供。返回：无。异常：日志系统原异常透传。
    """
    safe_reason = reason.value if isinstance(reason, (CnAnnualReportFactsReason, CnAnnualReportSourceReason)) else reason
    message = (f"CN年度原件拒绝 provider=cninfo source_id={_safe_reference(source_id, _SOURCE_REFERENCE)} "
               f"stage={stage} reason={safe_reason}")
    if document_id is not None:
        message += f" document_id={_safe_reference(document_id, _DOCUMENT_REFERENCE)}"
    Log.warn(message, module=_MODULE)
