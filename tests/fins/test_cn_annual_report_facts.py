"""年度首页 facts owner：官方派生正例与明确合成 grammar/PDF 反例。"""

from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, NumberObject, DecodedStreamObject

from dayu.fins.pipelines.cn_annual_report_facts import (
    resolve_cn_annual_report_facts, _resolve_cn_annual_report_text_facts,
    CnAnnualReportFactsError, CnAnnualReportFactsReason,
)
from dayu.fins.pipelines.cn_download_models import CnAnnualReportFacts

FIXTURES = Path(__file__).parent / "fixtures" / "cninfo_annual_fulltext"
OFFICIAL_FACTS = {
    "1204545056": (2017, "full"), "1205110621": (2017, "full"), "1206005283": (2018, "full"),
    "1207678369": (2019, "full"), "1209875597": (2020, "summary"), "1209875598": (2020, "full"),
    "1213161682": (2021, "summary"), "1213161683": (2021, "full"), "1216619553": (2022, "full"),
    "1219815158": (2023, "full"), "1223301988": (2024, "full"), "1223301999": (2024, "summary"),
    "1225178190": (2025, "full"),
}


def build_synthetic_annual_pdf(year: int = 2024, *, summary: bool = False) -> bytes:
    """创建明确合成、可由真实 parser 提取的测试 PDF，不冒充官方证据。

    参数：year/summary 为测试事实。返回：合法 PDF bytes。异常：pypdf 构造失败原样传播。
    """
    text = f"{year}年年度报告" + ("摘要" if summary else "")
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    cmap = DecodedStreamObject()
    entries = "\n".join(f"<{i:04x}> <{ord(char):04x}>" for i, char in enumerate(text, 1))
    cmap.set_data(("/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
                   "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
                   "/CMapName /Test def /CMapType 2 def 1 begincodespacerange <0000> <FFFF> endcodespacerange\n"
                   f"{len(text)} beginbfchar\n{entries}\nendbfchar endcmap CMapName currentdict /CMap defineresource pop end end").encode())
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type0'),
                             NameObject('/BaseFont'): NameObject('/Test'), NameObject('/Encoding'): NameObject('/Identity-H'),
                             NameObject('/ToUnicode'): cmap})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
    content = DecodedStreamObject()
    content.set_data(('BT /F1 12 Tf 10 700 Td <'+''.join(f'{i:04x}' for i in range(1,len(text)+1))+'> Tj ET').encode())
    page[NameObject('/Contents')] = content
    output = BytesIO(); writer.write(output)
    return output.getvalue() + b'\n% synthetic padding ' + b'0' * 1024


@pytest.mark.parametrize('source_id', tuple(OFFICIAL_FACTS))
def test_official_first_page(source_id: str) -> None:
    """参数：官方来源 ID。返回：无。异常：事实偏差断言失败。"""
    year, kind = OFFICIAL_FACTS[source_id]
    facts = resolve_cn_annual_report_facts((FIXTURES / f'{source_id}.pdf').read_bytes())
    assert (facts.fiscal_year, facts.kind) == (year, kind)


@pytest.mark.parametrize('suffix', ('摘要','(摘要)','（摘要）','[摘要]','［摘要］','【摘要】',':摘要','：【摘要】'))
def test_summary_suffix(suffix: str) -> None:
    """参数：封闭后缀。返回：无。异常：摘要误判断言失败。"""
    assert _resolve_cn_annual_report_text_facts(f'公司 2024 年 年度报告 {suffix}') == CnAnnualReportFacts(2024, 'summary')


@pytest.mark.parametrize('text', ('2024年度报告\n公司2024年年报', '公司\u30002024年\t年度报告',
    '公司 2024 年 年度报告 全 文\n2024年年度报告', '2024年年报全文'))
def test_full_labels(text: str) -> None:
    """参数：重复/空白标签。返回：无。异常：合法事实误拒断言失败。"""
    assert _resolve_cn_annual_report_text_facts(text) == CnAnnualReportFacts(2024, 'full')


@pytest.mark.parametrize('text', ('2024年度报告摘要版','2024年度报告说明','2024年度报告补充','2024年度报告（未知）',
 '2024年度报告（摘要]','2024年度报告：','2024年度报告\n摘要','2024年度报告\n（摘要）',
 '2024年度报告\n2023年报','2024年度报告\n2024年报摘要','2024年报2024年报','12024年度报告','２０２４年度报告','', '无标签',
 '2024年度报告全文摘要', '2024年度报告全文说明', '2024年度报告全文（未知）',
 '2024年度报告全文\n2023年度报告', '2024年度报告全文\n2024年度报告摘要'))
def test_unsupported_text(text: str) -> None:
    """参数：明确反例。返回：无。异常：错误接受反例断言失败。"""
    with pytest.raises(ValueError): _resolve_cn_annual_report_text_facts(text)


@pytest.mark.parametrize('payload', (b'', b'broken', build_synthetic_annual_pdf(), build_synthetic_annual_pdf(2023, summary=True)))
def test_pdf_boundary(payload: bytes) -> None:
    """参数：坏或明确合成 PDF。返回：无。异常：真实提取边界漂移断言失败。"""
    if not payload.startswith(b'%PDF'):
        with pytest.raises(ValueError): resolve_cn_annual_report_facts(payload)
    else:
        assert resolve_cn_annual_report_facts(payload).fiscal_year in (2023,2024)


def test_empty_encrypted_pdf() -> None:
    """参数：无。返回：无。异常：零页、无标签或加密页面未被拒绝断言失败。"""
    writer = PdfWriter(); stream = BytesIO(); writer.write(stream)
    with pytest.raises(CnAnnualReportFactsError) as empty:
        resolve_cn_annual_report_facts(stream.getvalue())
    assert empty.value.reason is CnAnnualReportFactsReason.EXTRACTION_FAILED
    writer.add_blank_page(width=300,height=300); stream=BytesIO();writer.write(stream)
    with pytest.raises(CnAnnualReportFactsError) as blank:
        resolve_cn_annual_report_facts(stream.getvalue())
    assert blank.value.reason is CnAnnualReportFactsReason.MISSING_OR_CONFLICTING_FACTS
    writer.encrypt('secret'); stream=BytesIO();writer.write(stream)
    with pytest.raises(CnAnnualReportFactsError) as encrypted:
        resolve_cn_annual_report_facts(stream.getvalue())
    assert encrypted.value.reason is CnAnnualReportFactsReason.EXTRACTION_FAILED


@pytest.mark.parametrize('text,reason', (
    ('2024年报2024年报', CnAnnualReportFactsReason.MULTIPLE_LABELS),
    ('2024年报全文摘要', CnAnnualReportFactsReason.UNSUPPORTED_SUFFIX),
    ('2024年报全文\n2023年报', CnAnnualReportFactsReason.MISSING_OR_CONFLICTING_FACTS),
    ('', CnAnnualReportFactsReason.MISSING_OR_CONFLICTING_FACTS),
))
def test_rejection_reason_owned_by_facts(text: str, reason: CnAnnualReportFactsReason) -> None:
    """断言拒绝原因是 owner 合同。参数：文本/封闭原因。返回：无。异常：原因漂移断言失败。"""
    with pytest.raises(CnAnnualReportFactsError) as raised:
        _resolve_cn_annual_report_text_facts(text)
    assert raised.value.reason is reason


def test_extraction_reason_preserves_private_cause() -> None:
    """坏 PDF 有封闭原因和私有 cause。参数：无。返回：无。异常：拒绝合同漂移断言失败。"""
    with pytest.raises(CnAnnualReportFactsError) as raised:
        resolve_cn_annual_report_facts(b'broken')
    assert raised.value.reason is CnAnnualReportFactsReason.EXTRACTION_FAILED
    assert raised.value.__cause__ is not None
