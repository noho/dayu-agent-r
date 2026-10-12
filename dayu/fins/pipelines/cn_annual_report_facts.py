"""CN 年度报告原文首页事实的纯提取；不访问仓储、网络或 OCR。"""

from io import BytesIO
import re

from pypdf import PdfReader

from dayu.fins.pipelines.cn_download_models import CnAnnualReportFacts

_LABEL = re.compile(r"(?<![0-9])(?P<year>[1-9][0-9]{3})年?(?:年度报告|年报)")
_SUMMARY = re.compile(r"(?:[:：])?(?:摘要|\(摘要\)|（摘要）|\[摘要\]|［摘要］|【摘要】)")


def resolve_cn_annual_report_facts(pdf_bytes: bytes) -> CnAnnualReportFacts:
    """读取实际 PDF 首页年度事实。

    参数：pdf_bytes 为官方原件字节。返回：唯一财年及全文性质。
    异常：ValueError 表示 PDF 提取失败或首页事实不足，保留原 cause。
    """
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        text = reader.pages[0].extract_text()
    except Exception as exc:
        raise ValueError("年度报告首页无法提取") from exc
    return _resolve_cn_annual_report_text_facts(text)


def _resolve_cn_annual_report_text_facts(text: str) -> CnAnnualReportFacts:
    """按物理行及封闭后缀确认年度事实。

    参数：text 为首页提取文字。返回：唯一一致年度事实。
    异常：ValueError 表示缺失、冲突或不支持的标签。
    """
    facts: set[CnAnnualReportFacts] = set()
    remaining: list[str] = []
    for line in text.splitlines():
        normalized = "".join(char for char in line if not char.isspace())
        labels = tuple(_LABEL.finditer(normalized))
        if len(labels) > 1:
            raise ValueError("同一行年度标签冲突")
        if not labels:
            remaining.append(normalized)
            continue
        label = labels[0]
        suffix = normalized[label.end():]
        if suffix == "":
            kind = "full"
        elif _SUMMARY.fullmatch(suffix):
            kind = "summary"
        else:
            raise ValueError("年度标签后缀不明确")
        facts.add(CnAnnualReportFacts(int(label.group("year")), kind))
        remaining.append(normalized[:label.start()])
    if len(facts) != 1 or any("摘要" in line for line in remaining):
        raise ValueError("首页年度事实缺失或冲突")
    return next(iter(facts))
