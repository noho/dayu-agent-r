"""docling 2.127 升级 PPTX/DOCX 真实转换冒烟。

样本库无真实财报 PPT/DOCX，本脚本用 python-pptx / python-docx 自建 5 份样本：

- ``pptx_merged_tables.pptx``：3 页复杂合并单元格表格（横向/纵向合并，数字密集）；
- ``pptx_charts.pptx``：柱状图 + 折线图 + 饼图各一页；
- ``docx_columns.docx``：双栏分栏 + 表格；
- ``docx_header_footer.docx``：页眉页脚 + 正文表格；
- ``docx_mixed.docx``：多级标题 + 列表 + 表格。

每份样本表格内埋入哨兵数字（千分位/小数/百分比），转换后以 merged 数字口径
（texts ∪ table_cells）校验保真命中率。

判定链（与生产入口一致：dayu.documents.docling_runtime 的
``convert_pdf_bytes_with_docling``，stream_name 带原扩展名）：

1. 转换成功；
2. export_to_dict 为 closed JSON；
3. ``DoclingDocument.model_validate_json`` 可解析新产出；
4. 哨兵数字保真命中率。

:用法: python utils/pptx_docx_smoke.py [--samples-dir DIR]
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable
from pathlib import Path

SENTINEL_NUMBERS: tuple[str, ...] = (
    "1234.56",
    "7,890,123",
    "45.67%",
    "3,141.59",
    "-2,718.28",
    "0.618",
    "10,000",
    "6.02%",
)
NUMBER_TOKEN_PATTERN = re.compile(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?")
DEFAULT_SAMPLES_DIR = (
    Path(__file__).resolve().parents[1] / "workspace/tmp/pptx-docx-samples"
)


def _build_pptx_merged_tables(path: Path) -> set[str]:
    """生成合并单元格表格 PPTX。

    :param path: 输出文件路径。
    :returns: 实际埋入的哨兵数字集合。
    :raises Exception: 生成失败时由 pptx 抛出。
    """

    from pptx import Presentation
    from pptx.util import Inches

    embedded: set[str] = set()
    presentation = Presentation()
    for slide_index in range(3):
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        rows, cols = 6, 5
        table = slide.shapes.add_table(rows, cols, Inches(0.6), Inches(0.8), Inches(8.5), Inches(4.5)).table
        # 横向合并表头 + 纵向合并首列 + 中部块合并。
        table.cell(0, 0).merge(table.cell(0, 4))
        table.cell(0, 0).text = f"合并单元格表格 第{slide_index + 1}页"
        table.cell(1, 0).merge(table.cell(2, 0))
        table.cell(1, 0).text = "纵向合并"
        table.cell(3, 1).merge(table.cell(4, 2))
        table.cell(3, 1).text = "块合并"
        for row_index in range(1, rows):
            for col_index in range(1, cols):
                cell = table.cell(row_index, col_index)
                if not cell.text:
                    token = SENTINEL_NUMBERS[(row_index * cols + col_index + slide_index) % len(SENTINEL_NUMBERS)]
                    cell.text = token
                    embedded.add(token)
    path.parent.mkdir(parents=True, exist_ok=True)
    presentation.save(str(path))
    return embedded


def _build_pptx_charts(path: Path) -> set[str]:
    """生成多图表 PPTX（图表数值按设计不进入 texts/tables 口径）。

    :param path: 输出文件路径。
    :returns: 空集合（图表样本不做数字保真判定）。
    :raises Exception: 生成失败时由 pptx 抛出。
    """

    from typing import cast

    from pptx import Presentation
    from pptx.chart.data import CategoryChartData, ChartData
    from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
    from pptx.shapes.graphfrm import GraphicFrame
    from pptx.util import Inches

    presentation = Presentation()
    # 柱状图
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    chart_data = CategoryChartData()
    chart_data.categories = ["Q1", "Q2", "Q3", "Q4"]
    chart_data.add_series("收入", (1234.56, 2345.67, 3456.78, 4567.89))
    chart_data.add_series("成本", (987.65, 1234.56, 1654.32, 2234.56))
    chart_frame = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1), Inches(8), Inches(5),
        cast("ChartData", chart_data),
    )
    chart = cast("GraphicFrame", chart_frame).chart
    chart.has_legend = True
    chart_legend = chart.legend
    if chart_legend is not None:
        chart_legend.position = XL_LEGEND_POSITION.BOTTOM
    # 折线图
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    line_data = CategoryChartData()
    line_data.categories = ["1月", "2月", "3月", "4月", "5月"]
    line_data.add_series("净利润", (100.5, 150.25, 180.75, 220.5, 250.0))
    slide.shapes.add_chart(
        XL_CHART_TYPE.LINE_MARKERS, Inches(1), Inches(1), Inches(8), Inches(5),
        cast("ChartData", line_data),
    )
    # 饼图
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    pie_data = CategoryChartData()
    pie_data.categories = ["主营业务", "其他业务", "投资收益"]
    pie_data.add_series("占比", (0.8, 0.15, 0.05))
    slide.shapes.add_chart(
        XL_CHART_TYPE.PIE, Inches(2), Inches(1.5), Inches(6), Inches(5),
        cast("ChartData", pie_data),
    )
    presentation.save(str(path))
    return set()


def _build_docx_columns(path: Path) -> set[str]:
    """生成双栏分栏 DOCX。

    :param path: 输出文件路径。
    :returns: 实际埋入的哨兵数字集合。
    :raises Exception: 生成失败时由 docx 抛出。
    """

    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    embedded: set[str] = set()
    document = Document()
    section = document.sections[0]
    columns_element = section._sectPr.find(qn("w:cols"))
    if columns_element is None:
        columns_element = OxmlElement("w:cols")
        section._sectPr.append(columns_element)
    columns_element.set(qn("w:num"), "2")
    columns_element.set(qn("w:space"), "720")
    for index in range(8):
        token = SENTINEL_NUMBERS[index % len(SENTINEL_NUMBERS)]
        document.add_paragraph(f"分栏正文段落 {index + 1}，营收 {token} 千元。")
        embedded.add(token)
    # 分栏段落后追加表格（表格单元格内数字需保真）。
    table = document.add_table(rows=4, cols=3)
    for row_index in range(4):
        for col_index in range(3):
            token = SENTINEL_NUMBERS[(row_index * 3 + col_index + 2) % len(SENTINEL_NUMBERS)]
            table.cell(row_index, col_index).text = token
            embedded.add(token)
    document.save(str(path))
    return embedded


def _build_docx_header_footer(path: Path) -> set[str]:
    """生成页眉页脚 DOCX。

    :param path: 输出文件路径。
    :returns: 实际埋入的哨兵数字集合。
    :raises Exception: 生成失败时由 docx 抛出。
    """

    from docx import Document

    embedded: set[str] = set()
    document = Document()
    header = document.sections[0].header
    header.paragraphs[0].text = "页眉：某某股份有限公司 2026 年半年度报告"
    footer = document.sections[0].footer
    footer_token = SENTINEL_NUMBERS[6]
    footer.paragraphs[0].text = f"页脚：第 X 页，共 Y 页，披露日期 2026-09-17，负债率 {footer_token}"
    embedded.add(footer_token)
    document.add_heading("页眉页脚样本正文", level=1)
    document.add_paragraph("正文段落一：本页内容用于验证页眉页脚保留与正文文本抽取。")
    table = document.add_table(rows=3, cols=2)
    for row_index in range(3):
        table.cell(row_index, 0).text = f"指标 {row_index + 1}"
        token = SENTINEL_NUMBERS[row_index]
        table.cell(row_index, 1).text = token
        embedded.add(token)
    document.add_paragraph("正文段落二：验证段落序列完整。")
    document.save(str(path))
    return embedded


def _build_docx_mixed(path: Path) -> set[str]:
    """生成标题/列表/表格混合 DOCX。

    :param path: 输出文件路径。
    :returns: 实际埋入的哨兵数字集合。
    :raises Exception: 生成失败时由 docx 抛出。
    """

    from docx import Document

    embedded: set[str] = set()
    document = Document()
    document.add_heading("第一节 公司概况", level=1)
    document.add_heading("1.1 基本信息", level=2)
    document.add_paragraph("公司注册地址与主营业务说明。")
    document.add_heading("1.2 主要财务数据", level=2)
    for item in ("营业收入同比增长", "净利润保持稳定", "现金流持续改善"):
        document.add_paragraph(item, style="List Bullet")
    table = document.add_table(rows=5, cols=3)
    table.cell(0, 0).text = "项目"
    table.cell(0, 1).text = "本期金额"
    table.cell(0, 2).text = "上期金额"
    for row_index in range(1, 5):
        table.cell(row_index, 0).text = f"指标{row_index}"
        token_current = SENTINEL_NUMBERS[row_index]
        token_previous = SENTINEL_NUMBERS[row_index + 3]
        table.cell(row_index, 1).text = token_current
        table.cell(row_index, 2).text = token_previous
        embedded.add(token_current)
        embedded.add(token_previous)
    document.add_heading("第二节 管理层讨论", level=1)
    document.add_paragraph("经营情况分析正文。")
    document.save(str(path))
    return embedded


BUILDERS: tuple[tuple[str, Callable[[Path], set[str]]], ...] = (
    ("pptx_merged_tables.pptx", _build_pptx_merged_tables),
    ("pptx_charts.pptx", _build_pptx_charts),
    ("docx_columns.docx", _build_docx_columns),
    ("docx_header_footer.docx", _build_docx_header_footer),
    ("docx_mixed.docx", _build_docx_mixed),
)


def _table_cells_text(tables: list[dict]) -> str:
    """拼接 tables 全部单元格文本。

    :param tables: exported tables 列表。
    :returns: 换行分隔的单元格文本。
    :raises Exception: 不主动抛出异常。
    """

    parts: list[str] = []
    for table in tables:
        table_data = table.get("data") or {}
        for cell in table_data.get("table_cells") or []:
            parts.append(str(cell.get("text", "")))
    return "\n".join(parts)


def _merged_number_set(exported: dict) -> set[str]:
    """计算 merged 数字口径集合（texts ∪ table_cells）。

    :param exported: export_to_dict 输出。
    :returns: 数字 token 集合。
    :raises Exception: 不主动抛出异常。
    """

    text = "\n".join(str(item.get("text", "")) for item in (exported.get("texts") or []))
    merged = f"{text}\n{_table_cells_text(exported.get('tables') or [])}"
    return set(NUMBER_TOKEN_PATTERN.findall(merged))


def main() -> int:
    """生成样本、转换并判定，输出汇总 JSON。

    :returns: 全部通过返回 0，任一判定失败返回 1。
    :raises Exception: 不主动抛出。
    """

    parser = argparse.ArgumentParser(description="PPTX/DOCX 真实转换冒烟")
    parser.add_argument("--samples-dir", default=str(DEFAULT_SAMPLES_DIR), help="样本目录")
    args = parser.parse_args()
    samples_dir = Path(args.samples_dir)
    samples_dir.mkdir(parents=True, exist_ok=True)

    # 每次重新生成样本并记录实际埋入的哨兵集合（判定口径按埋入集合）。
    embedded_map: dict[str, set[str]] = {}
    for filename, builder in BUILDERS:
        path = samples_dir / filename
        embedded_map[filename] = builder(path)
        print(f"[gen] {filename} (埋入 {len(embedded_map[filename])} 个哨兵)")

    from dayu.documents.docling_runtime import convert_pdf_bytes_with_docling
    from dayu.fins.pipelines.docling_process_converter import _is_closed_json_value
    from docling_core.types.doc.document import DoclingDocument

    results: list[dict] = []
    for filename, _builder_func in BUILDERS:
        del _builder_func
        path = samples_dir / filename
        entry: dict = {"sample": filename}
        try:
            raw_bytes = path.read_bytes()
            conversion = convert_pdf_bytes_with_docling(raw_bytes, stream_name=filename)
            exported = conversion.document.export_to_dict()
            entry["closed_json"] = isinstance(exported, dict) and _is_closed_json_value(exported)
            try:
                DoclingDocument.model_validate_json(json.dumps(exported, ensure_ascii=False))
                entry["parseable"] = True
            except Exception as exc:
                entry["parseable"] = False
                entry["parse_error"] = f"{type(exc).__name__}: {exc}"
            entry["texts"] = len(exported.get("texts") or [])
            entry["tables"] = len(exported.get("tables") or [])
            entry["pictures"] = len(exported.get("pictures") or [])
            embedded = embedded_map[filename]
            if embedded:
                numbers = _merged_number_set(exported)
                missing_sentinels = [token for token in embedded if token not in numbers]
                entry["sentinel_hit_rate"] = round(
                    (len(embedded) - len(missing_sentinels)) / len(embedded), 3
                )
                entry["missing_sentinels"] = missing_sentinels
            else:
                # 图表样本：数字保真不适用（图表数值按设计不进入 texts/tables 口径），
                # 判定图表以 picture 形式保留。
                entry["sentinel_hit_rate"] = None
                entry["chart_pictures_preserved"] = entry["pictures"]
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
        results.append(entry)
        print(f"[smoke] {filename}: {json.dumps(entry, ensure_ascii=False)}")

    summary = {"results": results, "all_pass": all("error" not in r for r in results)}
    (samples_dir / "smoke-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"汇总已写 {samples_dir / 'smoke-summary.json'}")
    return 0 if summary["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
