"""CN 年度报告原文首页事实的纯提取；不访问仓储、网络或 OCR。"""

from io import BytesIO
from enum import Enum
import re

from pypdf import PdfReader

from dayu.fins.pipelines.cn_download_models import CnAnnualReportFacts

_LABEL = re.compile(r"(?<![0-9])(?P<year>[1-9][0-9]{3})年?(?:年度报告|年报)")
_SUMMARY = re.compile(r"(?:[:：])?(?:摘要|\(摘要\)|（摘要）|\[摘要\]|［摘要］|【摘要】)")
_FULL_SUFFIXES = frozenset(("", "全文"))


class CnAnnualReportFactsReason(str, Enum):
    """首页事实 owner 产生的封闭安全拒绝原因。"""

    EXTRACTION_FAILED = "首页无法提取"
    MULTIPLE_LABELS = "同一行年度标签冲突"
    UNSUPPORTED_SUFFIX = "年度标签后缀不明确"
    MISSING_OR_CONFLICTING_FACTS = "首页年度事实缺失或冲突"


class CnAnnualReportFactsError(ValueError):
    """携带 owner 拒绝原因；底层 cause 只供开发取证，不投影到业务诊断。"""

    def __init__(self, reason: CnAnnualReportFactsReason) -> None:
        """构造拒绝。参数：reason 为封闭原因。返回：无。异常：无。"""
        self.reason = reason
        super().__init__(reason.value)


def resolve_cn_annual_report_facts(pdf_bytes: bytes) -> CnAnnualReportFacts:
    """读取实际 PDF 首页年度事实。

    参数：pdf_bytes 为官方原件字节。返回：唯一财年及全文性质。
    异常：CnAnnualReportFactsError 表示 PDF 提取失败或首页事实不足，保留原 cause。
    """
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        text = reader.pages[0].extract_text()
    except Exception as exc:
        raise CnAnnualReportFactsError(CnAnnualReportFactsReason.EXTRACTION_FAILED) from exc
    return _resolve_cn_annual_report_text_facts(text)


def _resolve_cn_annual_report_text_facts(text: str) -> CnAnnualReportFacts:
    """按物理行及封闭后缀确认年度事实。

    参数：text 为首页提取文字。返回：唯一一致年度事实。
    异常：CnAnnualReportFactsError 表示缺失、冲突或不支持的标签。
    """
    facts: set[CnAnnualReportFacts] = set()
    remaining: list[str] = []
    for line in text.splitlines():
        normalized = "".join(char for char in line if not char.isspace())
        labels = tuple(_LABEL.finditer(normalized))
        if len(labels) > 1:
            raise CnAnnualReportFactsError(CnAnnualReportFactsReason.MULTIPLE_LABELS)
        if not labels:
            remaining.append(normalized)
            continue
        label = labels[0]
        suffix = normalized[label.end():]
        if suffix in _FULL_SUFFIXES:
            kind = "full"
        elif _SUMMARY.fullmatch(suffix):
            kind = "summary"
        else:
            raise CnAnnualReportFactsError(CnAnnualReportFactsReason.UNSUPPORTED_SUFFIX)
        facts.add(CnAnnualReportFacts(int(label.group("year")), kind))
        remaining.append(normalized[:label.start()])
    if len(facts) != 1 or any("摘要" in line for line in remaining):
        raise CnAnnualReportFactsError(CnAnnualReportFactsReason.MISSING_OR_CONFLICTING_FACTS)
    return next(iter(facts))
