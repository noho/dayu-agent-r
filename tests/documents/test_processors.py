"""共享文档处理器的轻量确定性 fixture 测试。"""

from __future__ import annotations

from pathlib import Path

from docling_core.types.doc.document import (
    DoclingDocument,
    RefItem,
    SectionHeaderItem,
    TableCell,
    TableData,
    TableItem,
    TextItem,
)
from docling_core.types.doc.labels import DocItemLabel

from dayu.documents.processors import build_documents_processor_registry
from dayu.documents.processors.bs_processor import BSProcessor
from dayu.documents.processors.docling_processor import DoclingProcessor
from dayu.documents.processors.local_file_source import LocalFileSource
from dayu.documents.processors.markdown_processor import MarkdownProcessor


def _source_for(path: Path, media_type: str) -> LocalFileSource:
    """构造本地文件 Source。

    :param path: fixture 文件路径。
    :param media_type: 文件媒体类型。
    :returns: 本地文件 Source。
    """

    return LocalFileSource(path=path, uri=str(path), media_type=media_type)


def _ref_item(ref: str) -> RefItem:
    """按 Docling JSON alias 构造引用对象。

    :param ref: Docling 内部引用，例如 ``#/body``。
    :returns: 引用对象。
    """

    return RefItem.model_validate({"$ref": ref})


def test_documents_processor_registry_registers_default_processors() -> None:
    """documents 默认注册表应保持通用处理器注册行为不变。"""

    registry = build_documents_processor_registry()

    assert registry.list_processors() == [
        {"name": "docling_processor", "class": "DoclingProcessor", "priority": 10},
        {"name": "markdown_processor", "class": "MarkdownProcessor", "priority": 10},
        {"name": "bs_processor", "class": "BSProcessor", "priority": 10},
    ]


def test_markdown_processor_sections_tables_and_search(tmp_path: Path) -> None:
    """Markdown 处理器应稳定产出章节、表格与搜索片段。"""

    markdown_path = tmp_path / "sample.md"
    markdown_path.write_text(
        "\n".join(
            [
                "# Overview",
                "Revenue grew quickly.",
                "",
                "| Metric | Value |",
                "| --- | ---: |",
                "| Revenue | 100 |",
                "",
                "## Details",
                "Margin improved.",
            ]
        ),
        encoding="utf-8",
    )

    processor = MarkdownProcessor(_source_for(markdown_path, "text/markdown"))

    sections = processor.list_sections()
    assert [section["ref"] for section in sections] == ["s_0001", "s_0002"]
    assert sections[0]["title"] == "Overview"
    assert sections[1]["parent_ref"] == "s_0001"

    tables = processor.list_tables()
    assert tables[0]["table_ref"] == "t_0001"
    assert tables[0]["headers"] == ["Metric", "Value"]

    section = processor.read_section("s_0001")
    assert "Revenue grew quickly." in section["content"]
    assert section["tables"] == ["t_0001"]

    table = processor.read_table("t_0001")
    assert table["columns"] == ["Metric", "Value"]
    assert table["data"] == [{"Metric": "Revenue", "Value": "100"}]

    hits = processor.search("Revenue")
    assert hits
    assert hits[0].get("section_ref") == "s_0001"
    assert "Revenue" in str(hits[0].get("snippet", ""))


def test_html_processor_sections_tables_and_search(tmp_path: Path) -> None:
    """HTML 处理器应稳定产出章节、表格 records 与搜索片段。"""

    html_path = tmp_path / "sample.html"
    html_path.write_text(
        (
            "<html><body>"
            "<h1>Overview</h1>"
            "<p>Revenue grew quickly.</p>"
            "<table>"
            "<tr><th>Metric</th><th>Value</th></tr>"
            "<tr><td>Revenue</td><td>100</td></tr>"
            "</table>"
            "</body></html>"
        ),
        encoding="utf-8",
    )

    processor = BSProcessor(_source_for(html_path, "text/html"))

    sections = processor.list_sections()
    assert sections[0]["ref"] == "s_0001"
    assert sections[0]["title"] == "Overview"

    section = processor.read_section("s_0001")
    assert section["tables"] == ["t_0001"]
    assert "[[t_0001]]" in section["content"]

    table = processor.read_table("t_0001")
    assert table["data_format"] == "records"
    assert table["columns"] == ["Metric", "Value"]
    assert table["data"] == [{"Metric": "Revenue", "Value": 100}]

    hits = processor.search("Revenue")
    assert hits
    assert hits[0].get("section_ref") == "s_0001"
    assert "Revenue" in str(hits[0].get("snippet", ""))


def test_docling_json_processor_sections_tables_and_search(tmp_path: Path) -> None:
    """Docling JSON 处理器应读取真实 JSON 并产出章节、表格与搜索片段。"""

    docling_path = tmp_path / "sample_docling.json"
    parent_ref = _ref_item("#/body")
    header = SectionHeaderItem(
        self_ref="#/texts/0",
        parent=parent_ref,
        orig="Overview",
        text="Overview",
        level=1,
    )
    paragraph = TextItem(
        self_ref="#/texts/1",
        parent=parent_ref,
        orig="Revenue grew quickly.",
        text="Revenue grew quickly.",
        label=DocItemLabel.TEXT,
    )
    table = TableItem(
        self_ref="#/tables/0",
        parent=parent_ref,
        data=TableData(
            num_rows=2,
            num_cols=2,
            table_cells=[
                TableCell(
                    start_row_offset_idx=0,
                    end_row_offset_idx=1,
                    start_col_offset_idx=0,
                    end_col_offset_idx=1,
                    text="Metric",
                    column_header=True,
                ),
                TableCell(
                    start_row_offset_idx=0,
                    end_row_offset_idx=1,
                    start_col_offset_idx=1,
                    end_col_offset_idx=2,
                    text="Value",
                    column_header=True,
                ),
                TableCell(
                    start_row_offset_idx=1,
                    end_row_offset_idx=2,
                    start_col_offset_idx=0,
                    end_col_offset_idx=1,
                    text="Revenue",
                ),
                TableCell(
                    start_row_offset_idx=1,
                    end_row_offset_idx=2,
                    start_col_offset_idx=1,
                    end_col_offset_idx=2,
                    text="100",
                ),
            ],
        ),
    )
    document = DoclingDocument(
        name="sample",
        texts=[header, paragraph],
        tables=[table],
    )
    document.body.children = [
        _ref_item("#/texts/0"),
        _ref_item("#/texts/1"),
        _ref_item("#/tables/0"),
    ]
    document.save_as_json(docling_path)

    processor = DoclingProcessor(_source_for(docling_path, "application/json"))

    sections = processor.list_sections()
    assert sections[0]["ref"] == "s_0001"
    assert sections[0]["title"] == "Overview"
    assert sections[0].get("internal_ref") == "#/texts/0"

    section = processor.read_section("s_0001")
    assert section["tables"] == ["t_0001"]
    assert "[[t_0001]]" in section["content"]

    table_content = processor.read_table("t_0001")
    assert table_content.get("internal_ref") == "#/tables/0"
    assert table_content["columns"] == ["Metric", "Value"]
    assert table_content["data"] == [{"Metric": "Revenue", "Value": "100"}]

    hits = processor.search("Revenue")
    assert hits
    assert hits[0].get("section_ref") == "s_0001"
    assert "Revenue" in str(hits[0].get("snippet", ""))
